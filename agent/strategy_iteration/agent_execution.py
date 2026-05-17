from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

from .schemas import (
    AgentTaskApproval,
    AgentTaskPlan,
    AgentTaskProposal,
    AgentTaskResult,
    ExperimentArm,
    StrategyIterationPlan,
)

AGENT_MODE_READONLY = "readonly"
AGENT_MODE_PATCH = "patch"
AGENT_MODE_DANGER_FULL_ACCESS = "danger-full-access"
SUPPORTED_AGENT_MODES = {AGENT_MODE_READONLY, AGENT_MODE_PATCH, AGENT_MODE_DANGER_FULL_ACCESS}

AGENT_PROVIDER_CODEX = "codex"

POLICY = (
    "Agent tasks delegate bounded work to a local coding-agent CLI. "
    "readonly tasks use a read-only sandbox. patch tasks run in an isolated git worktree and produce a diff. "
    "danger-full-access is reserved for exceptional local-only use, must be explicitly approved, and emits a high-risk warning."
)

DANGER_WARNING = (
    "DANGER: this task requests danger-full-access. It can modify the workspace and run commands without sandboxing. "
    "Use only for trusted local experiments after reviewing the prompt and target paths."
)


def build_agent_task_plan(
    plan: StrategyIterationPlan,
    *,
    provider: str = AGENT_PROVIDER_CODEX,
    mode: str = AGENT_MODE_READONLY,
    max_tasks: int = 2,
    allowed_paths: Iterable[str] | None = None,
) -> AgentTaskPlan:
    """Build bounded coding-agent task proposals from experiment arms."""

    mode = _normalize_mode(mode)
    allowed = list(allowed_paths or ["agent/", "web/", "test/", "config/", "docs/"])
    tasks: list[AgentTaskProposal] = []
    candidate_arms = [arm for arm in plan.experiment_arms if arm.change_type != "control"]
    for arm in candidate_arms[: max(1, max_tasks)]:
        task_id = f"agent_{len(tasks) + 1:03d}_{_slug(arm.arm_id)}"
        tasks.append(
            AgentTaskProposal(
                task_id=task_id,
                title=f"Implement or analyze {arm.arm_id}",
                prompt=_build_task_prompt(plan, arm, mode=mode),
                provider=provider,
                mode=mode,
                source=f"experiment_arm:{arm.arm_id}",
                target_files=list(arm.target_files),
                allowed_paths=allowed,
                requires_approval=True,
                approval_reason=_approval_reason(mode),
                timeout_seconds=2400 if mode == AGENT_MODE_DANGER_FULL_ACCESS else 1800,
            )
        )
    return AgentTaskPlan(
        run_id=plan.run_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        policy=POLICY,
        tasks=tasks,
    )


def save_agent_task_plan(agent_plan: AgentTaskPlan, run_dir: Path | str) -> None:
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "agent_tasks.json").write_text(
        json.dumps(agent_plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (path / "agent_tasks.md").write_text(agent_plan.to_markdown(), encoding="utf-8")


def save_agent_approval_template(agent_plan: AgentTaskPlan, run_dir: Path | str) -> Path:
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": agent_plan.run_id,
        "instructions": [
            "Set approved: true only for agent tasks you explicitly want to delegate.",
            "Keep prompt_sha256 unchanged; a mismatch means the task prompt changed after approval.",
            "Prefer readonly or patch mode. danger-full-access is high risk and should rarely be approved.",
        ],
        "approvals": [
            {
                "task_id": task.task_id,
                "prompt_sha256": task.prompt_sha256,
                "approved": False,
                "approved_by": "",
                "reason": "",
                "approved_at": "",
                "provider": task.provider,
                "mode": task.mode,
                "warning": DANGER_WARNING if task.mode == AGENT_MODE_DANGER_FULL_ACCESS else "",
                "title": task.title,
            }
            for task in agent_plan.tasks
        ],
    }
    output = path / "agent_approval_template.yaml"
    output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output


def execute_approved_agent_tasks(
    agent_plan: AgentTaskPlan,
    *,
    approval_file: Path | str,
    root: Path | str,
    worktree_base: Path | str = ".agent_worktrees",
    codex_bin: str = "codex",
) -> AgentTaskPlan:
    approvals = load_agent_approval_file(approval_file, expected_run_id=agent_plan.run_id)
    root_path = Path(root).resolve()
    results: list[AgentTaskResult] = []
    for task in agent_plan.tasks:
        approval = approvals.get(task.task_id)
        if not approval:
            results.append(_skip_result(task, "No approval entry for task_id."))
            continue
        if not approval.approved:
            results.append(_skip_result(task, "Approval entry is present but approved=false.", approval.reason))
            continue
        if approval.prompt_sha256 != task.prompt_sha256:
            results.append(_skip_result(task, "Approval prompt_sha256 does not match the current task.", approval.reason))
            continue
        if task.provider != AGENT_PROVIDER_CODEX:
            results.append(_skip_result(task, f"Unsupported provider: {task.provider}.", approval.reason))
            continue
        if not shutil.which(codex_bin):
            results.append(_skip_result(task, f"Codex CLI not found: {codex_bin}.", approval.reason))
            continue
        results.append(
            _run_codex_task(
                task,
                root=root_path,
                worktree_base=Path(worktree_base),
                codex_bin=codex_bin,
                approval_reason=approval.reason,
            )
        )
    agent_plan.results = results
    return agent_plan


def load_agent_approval_file(path: Path | str, *, expected_run_id: str | None = None) -> dict[str, AgentTaskApproval]:
    approval_path = Path(path)
    if not approval_path.exists():
        raise FileNotFoundError(f"Agent approval file not found: {approval_path}")
    payload = yaml.safe_load(approval_path.read_text(encoding="utf-8")) or {}
    run_id = str(payload.get("run_id") or "")
    if expected_run_id and run_id and run_id != expected_run_id:
        raise ValueError(f"Agent approval file run_id {run_id!r} does not match plan {expected_run_id!r}")
    approvals = payload.get("approvals") or []
    return {
        approval.task_id: approval
        for approval in (AgentTaskApproval.from_dict(item) for item in approvals)
        if approval.task_id
    }


def _run_codex_task(
    task: AgentTaskProposal,
    *,
    root: Path,
    worktree_base: Path,
    codex_bin: str,
    approval_reason: str,
) -> AgentTaskResult:
    started = datetime.now().isoformat(timespec="seconds")
    mode = _normalize_mode(task.mode)
    worktree_path = _prepare_worktree(root, worktree_base, task)
    artifacts_dir = worktree_path / ".agent_task_artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = artifacts_dir / f"{task.task_id}_prompt.md"
    result_path = artifacts_dir / f"{task.task_id}_result.md"
    stdout_path = artifacts_dir / f"{task.task_id}_stdout.jsonl"
    diff_path = artifacts_dir / f"{task.task_id}.diff"
    prompt_path.write_text(task.prompt, encoding="utf-8")

    argv = [
        codex_bin,
        "exec",
        "-C",
        str(worktree_path),
        "--ask-for-approval",
        "never",
        "--output-last-message",
        str(result_path),
        "--json",
    ]
    if mode == AGENT_MODE_READONLY:
        argv.extend(["--sandbox", "read-only"])
    elif mode == AGENT_MODE_PATCH:
        argv.extend(["--sandbox", "workspace-write"])
    else:
        argv.append("--dangerously-bypass-approvals-and-sandbox")
    argv.append(task.prompt)

    completed = subprocess.run(
        argv,
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=task.timeout_seconds,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    if mode in {AGENT_MODE_PATCH, AGENT_MODE_DANGER_FULL_ACCESS}:
        diff = subprocess.run(
            ["git", "diff", "--binary"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        diff_path.write_text(diff.stdout or "", encoding="utf-8")
    ended = datetime.now().isoformat(timespec="seconds")
    return AgentTaskResult(
        task_id=task.task_id,
        provider=task.provider,
        mode=mode,
        skipped=False,
        returncode=completed.returncode,
        started_at=started,
        ended_at=ended,
        worktree_path=str(worktree_path),
        result_path=str(result_path),
        diff_path=str(diff_path) if diff_path.exists() else "",
        stdout_tail=_tail(completed.stdout),
        stderr_tail=_tail(completed.stderr),
        approval_reason=approval_reason,
        warning=DANGER_WARNING if mode == AGENT_MODE_DANGER_FULL_ACCESS else "",
    )


def _prepare_worktree(root: Path, worktree_base: Path, task: AgentTaskProposal) -> Path:
    if task.mode == AGENT_MODE_DANGER_FULL_ACCESS:
        return root
    base = worktree_base if worktree_base.is_absolute() else root / worktree_base
    base.mkdir(parents=True, exist_ok=True)
    worktree = (base / task.task_id).resolve()
    if worktree.exists():
        return worktree
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return worktree


def _build_task_prompt(plan: StrategyIterationPlan, arm: ExperimentArm, *, mode: str) -> str:
    return "\n".join(
        [
            "You are a local coding agent working inside quant_ex.",
            "Follow AGENTS.md and preserve unrelated user changes.",
            f"Mode: {mode}.",
            "Do not run full training, full WFV, network crawls, real notifications, or trading-like commands.",
            "If implementation is risky or underspecified, produce an analysis and stop rather than guessing.",
            "",
            f"Run id: {plan.run_id}",
            f"Objective: {plan.objective}",
            f"Source arm: {arm.arm_id}",
            f"Change type: {arm.change_type}",
            f"Hypothesis: {arm.hypothesis}",
            f"Target files: {', '.join(arm.target_files) or 'not specified'}",
            "",
            "Success criteria:",
            *[f"- {item}" for item in arm.success_criteria],
            "",
            "Risk notes:",
            *[f"- {item}" for item in arm.risk_notes],
            "",
            "Expected final response:",
            "- Summarize what you changed or why no change was made.",
            "- List files changed.",
            "- List validation commands run and their outcomes.",
            "- Mention residual risks.",
        ]
    )


def _approval_reason(mode: str) -> str:
    if mode == AGENT_MODE_DANGER_FULL_ACCESS:
        return DANGER_WARNING
    if mode == AGENT_MODE_PATCH:
        return "Patch-mode coding agent can edit files in an isolated worktree and requires approval."
    return "Readonly coding-agent analysis requires approval because it can spend model/tool budget."


def _normalize_mode(mode: str) -> str:
    normalized = (mode or AGENT_MODE_READONLY).strip().lower().replace("_", "-")
    if normalized not in SUPPORTED_AGENT_MODES:
        return AGENT_MODE_READONLY
    return normalized


def _skip_result(task: AgentTaskProposal, reason: str, approval_reason: str = "") -> AgentTaskResult:
    return AgentTaskResult(
        task_id=task.task_id,
        provider=task.provider,
        mode=task.mode,
        skipped=True,
        skip_reason=reason,
        approval_reason=approval_reason,
        warning=DANGER_WARNING if task.mode == AGENT_MODE_DANGER_FULL_ACCESS else "",
    )


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in value)
    return "_".join(part for part in cleaned.split("_") if part)[:48] or "task"


def _tail(value: str, limit: int = 4000) -> str:
    if not value:
        return ""
    return value[-limit:]
