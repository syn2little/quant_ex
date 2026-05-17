from __future__ import annotations

import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import yaml

from .schemas import (
    CommandApproval,
    CommandExecutionPlan,
    CommandExecutionResult,
    CommandProposal,
    FeedbackCandidate,
    StrategyIterationPlan,
)

SAFE_LOCAL_TAG = "safe_local"
DRY_RUN_TAG = "dry_run"
EXPENSIVE_TAG = "expensive"
NETWORK_TAG = "network"
EXTERNAL_EFFECT_TAG = "external_effect"
TRADING_LIKE_TAG = "trading_like"
TEMPLATE_PLACEHOLDER_TAG = "template_placeholder"
UNKNOWN_TAG = "unknown"

PROTECTED_TAGS = {
    EXPENSIVE_TAG,
    NETWORK_TAG,
    EXTERNAL_EFFECT_TAG,
    TRADING_LIKE_TAG,
    TEMPLATE_PLACEHOLDER_TAG,
    UNKNOWN_TAG,
}

POLICY = (
    "Commands are proposed from the agent plan and classified by risk. "
    "Only commands tagged safe_local and not requiring approval are eligible for --execute-safe. "
    "Protected commands need an explicit approval file entry with matching command_id and command_sha256."
)


def classify_command(command: str) -> tuple[list[str], bool, str, int]:
    """Classify one shell-like command without executing it."""

    lowered = command.lower()
    tags: set[str] = set()
    timeout = 120

    if "--dry-run" in lowered or "--mock" in lowered:
        tags.add(DRY_RUN_TAG)
    if "run_walk_forward_validation.py" in lowered or "wfv" in lowered:
        tags.add(EXPENSIVE_TAG)
        timeout = 900
    if "run_backtest.py" in lowered:
        tags.add(EXPENSIVE_TAG)
        timeout = 600
    if "run_train.py" in lowered and "--list-registry" not in lowered:
        tags.add(EXPENSIVE_TAG)
        timeout = 900
    if any(token in lowered for token in ["run_fetch_data.py", "crawler/", "fetch_", "qlib update", "pip install"]):
        tags.add(NETWORK_TAG)
    if any(token in lowered for token in ["notify", "bark", "--remind", "notification"]):
        tags.add(EXTERNAL_EFFECT_TAG)
    if any(token in lowered for token in ["run_daily.py", "run_scheduled_rebalance.py", "rebalance", "positions"]):
        tags.add(TRADING_LIKE_TAG)
    if _has_template_placeholder(command):
        tags.add(TEMPLATE_PLACEHOLDER_TAG)

    is_known_safe = (
        command.startswith("./.venv/bin/python -c ")
        or command.startswith(".venv/bin/python -c ")
        or " -m pytest " in command
        or command.startswith("./.venv/bin/python -m pytest ")
        or command.startswith(".venv/bin/python -m pytest ")
        or ("run_train.py --list-registry" in command)
        or ("run_agent_strategy_iteration.py" in command and "--no-llm" in command)
    )
    if is_known_safe:
        tags.add(SAFE_LOCAL_TAG)

    if not tags:
        tags.add(UNKNOWN_TAG)

    requires_approval = bool(tags & PROTECTED_TAGS)
    reason = ""
    if requires_approval:
        reason = f"Protected risk tag(s): {', '.join(sorted(tags & PROTECTED_TAGS))}."
    elif SAFE_LOCAL_TAG in tags:
        reason = "Eligible for --execute-safe under the local-only policy."
    return sorted(tags), requires_approval, reason, timeout


def build_command_plan(plan: StrategyIterationPlan) -> CommandExecutionPlan:
    """Convert a strategy iteration plan into an auditable command proposal plan."""

    seen: set[str] = set()
    proposals: list[CommandProposal] = []

    for command in plan.validation_ladder:
        _add_command(
            proposals,
            seen,
            command=command,
            source="validation_ladder",
            purpose="Run a baseline validation ladder step from the synthesized plan.",
        )

    for arm in plan.experiment_arms:
        for command in arm.validation_commands:
            _add_command(
                proposals,
                seen,
                command=command,
                source=f"experiment_arm:{arm.arm_id}",
                purpose=f"Validate experiment arm {arm.arm_id}.",
            )

    _add_guarded_templates(proposals, seen, plan.run_id)

    return CommandExecutionPlan(
        run_id=plan.run_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        policy=POLICY,
        commands=proposals,
    )


ProgressCallback = Callable[..., None]


def execute_safe_commands(
    command_plan: CommandExecutionPlan,
    *,
    root: Path | str = ".",
    progress_callback: ProgressCallback | None = None,
) -> CommandExecutionPlan:
    """Execute only approved-by-policy safe local commands and capture compact results."""

    root_path = Path(root)
    results: list[CommandExecutionResult] = []
    total = len(command_plan.commands)
    for index, proposal in enumerate(command_plan.commands, start=1):
        _emit_progress(progress_callback, "command_start", proposal, index=index, total=total)
        if proposal.requires_approval:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason=proposal.approval_reason or "Command requires approval.",
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue
        placeholder_reason = _unresolved_placeholder_reason(proposal)
        if placeholder_reason:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason=placeholder_reason,
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue
        if SAFE_LOCAL_TAG not in proposal.risk_tags:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason="Command is not tagged safe_local.",
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue

        result = _run_local_command(
            proposal,
            root_path,
            progress_callback=progress_callback,
            index=index,
            total=total,
        )
        results.append(result)
        _emit_progress(progress_callback, "command_done", proposal, index=index, total=total, result=result)

    command_plan.results = results
    return command_plan


def execute_approved_commands(
    command_plan: CommandExecutionPlan,
    *,
    approval_file: Path | str,
    root: Path | str = ".",
    include_safe: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> CommandExecutionPlan:
    """Execute commands approved by file; optionally include safe-local commands."""

    approvals = load_approval_file(approval_file, expected_run_id=command_plan.run_id)
    root_path = Path(root)
    results: list[CommandExecutionResult] = []
    total = len(command_plan.commands)
    for index, proposal in enumerate(command_plan.commands, start=1):
        _emit_progress(progress_callback, "command_start", proposal, index=index, total=total)
        approval = approvals.get(proposal.command_id)
        placeholder_reason = _unresolved_placeholder_reason(proposal)
        if placeholder_reason:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason=placeholder_reason,
                approval_reason=approval.reason if approval else "",
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue
        if include_safe and not proposal.requires_approval and SAFE_LOCAL_TAG in proposal.risk_tags:
            result = _run_local_command(
                proposal,
                root_path,
                approval_reason="safe_local via include_safe",
                progress_callback=progress_callback,
                index=index,
                total=total,
            )
            results.append(result)
            _emit_progress(progress_callback, "command_done", proposal, index=index, total=total, result=result)
            continue
        if not approval:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason="No approval entry for command_id.",
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue
        if not approval.approved:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason="Approval entry is present but approved=false.",
                approval_reason=approval.reason,
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue
        if approval.command_sha256 != proposal.command_sha256:
            result = CommandExecutionResult(
                command_id=proposal.command_id,
                command=proposal.command,
                skipped=True,
                skip_reason="Approval command_sha256 does not match the current command.",
                approval_reason=approval.reason,
            )
            results.append(result)
            _emit_progress(progress_callback, "command_skipped", proposal, index=index, total=total, result=result)
            continue
        result = _run_local_command(
            proposal,
            root_path,
            approval_reason=approval.reason,
            progress_callback=progress_callback,
            index=index,
            total=total,
        )
        results.append(result)
        _emit_progress(progress_callback, "command_done", proposal, index=index, total=total, result=result)

    command_plan.results = results
    return command_plan


def _emit_progress(
    progress_callback: ProgressCallback | None,
    stage: str,
    proposal: CommandProposal,
    *,
    index: int,
    total: int,
    result: CommandExecutionResult | None = None,
    **extra,
) -> None:
    if not progress_callback:
        return
    payload = {
        "stage": stage,
        "command_id": proposal.command_id,
        "command": proposal.command,
        "risk_tags": proposal.risk_tags,
        "requires_approval": proposal.requires_approval,
        "index": index,
        "total": total,
    }
    if result:
        payload.update(
            {
                "skipped": result.skipped,
                "returncode": result.returncode,
                "skip_reason": result.skip_reason,
                "started_at": result.started_at,
                "ended_at": result.ended_at,
                "stdout_tail": result.stdout_tail,
                "stderr_tail": result.stderr_tail,
            }
        )
    payload.update(extra)
    try:
        progress_callback("progress", **payload)
    except Exception:
        pass


def load_approval_file(path: Path | str, *, expected_run_id: str | None = None) -> dict[str, CommandApproval]:
    """Load an approval YAML/JSON file and validate the run id when supplied."""

    approval_path = Path(path)
    if not approval_path.exists():
        raise FileNotFoundError(f"Approval file not found: {approval_path}")
    payload = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
    payload = payload or {}
    run_id = str(payload.get("run_id") or "")
    if expected_run_id and run_id and run_id != expected_run_id:
        raise ValueError(f"Approval file run_id {run_id!r} does not match command plan {expected_run_id!r}")
    approvals = payload.get("approvals") or payload.get("approved_commands") or []
    return {
        approval.command_id: approval
        for approval in (CommandApproval.from_dict(item) for item in approvals)
        if approval.command_id
    }


def save_command_plan(command_plan: CommandExecutionPlan, run_dir: Path | str) -> None:
    """Persist command plan and optional execution results next to an agent run."""

    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "commands.json").write_text(
        json.dumps(command_plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (path / "commands.md").write_text(command_plan.to_markdown(), encoding="utf-8")
    (path / "execution_summary.md").write_text(build_execution_summary(command_plan), encoding="utf-8")


def save_approval_template(command_plan: CommandExecutionPlan, run_dir: Path | str) -> Path:
    """Write an editable approval template next to command proposals."""

    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": command_plan.run_id,
        "instructions": [
            "Set approved: true only for commands you explicitly want to execute.",
            "Keep command_sha256 unchanged; a mismatch means the command changed after approval.",
            "Protected commands may be expensive, use network/cache, send notifications, or have trading-like semantics.",
            "Commands containing placeholders like <candidate_model> must be edited into concrete commands before execution.",
        ],
        "approvals": [
            {
                "command_id": item.command_id,
                "command_sha256": item.command_sha256,
                "approved": False,
                "approved_by": "",
                "reason": "",
                "approved_at": "",
                "risk_tags": item.risk_tags,
                "command": item.command,
            }
            for item in command_plan.commands
        ],
    }
    output = path / "approval_template.yaml"
    output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output


def attach_feedback_candidates(command_plan: CommandExecutionPlan, *, root: Path | str = ".") -> CommandExecutionPlan:
    """Attach result CSV candidates that can be converted into StrategyFeedback."""

    root_path = Path(root)
    result_by_command = {result.command_id: result for result in command_plan.results}
    candidates: list[FeedbackCandidate] = []
    for proposal in command_plan.commands:
        result = result_by_command.get(proposal.command_id)
        if result and (result.skipped or result.returncode not in (0, None)):
            continue
        candidate = _candidate_from_command(command_plan.run_id, proposal, root_path)
        if candidate:
            candidates.append(candidate)
    command_plan.feedback_candidates = candidates
    return command_plan


def build_execution_summary(command_plan: CommandExecutionPlan) -> str:
    """Build a compact Markdown summary for command execution results."""

    total = len(command_plan.commands)
    executed = [item for item in command_plan.results if not item.skipped]
    passed = [item for item in executed if item.returncode == 0]
    failed = [item for item in executed if item.returncode not in (0, None)]
    skipped = [item for item in command_plan.results if item.skipped]
    lines = [
        f"# Agent Execution Summary: {command_plan.run_id}",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Commands proposed: {total}",
        f"- Executed: {len(executed)}",
        f"- Passed: {len(passed)}",
        f"- Failed: {len(failed)}",
        f"- Skipped: {len(skipped)}",
        "",
        "## Result Table",
        "| Command | Status | Return Code | Reason |",
        "|---|---:|---:|---|",
    ]
    if command_plan.results:
        result_map = {item.command_id: item for item in command_plan.results}
        for proposal in command_plan.commands:
            result = result_map.get(proposal.command_id)
            if not result:
                status = "not_run"
                returncode = ""
                reason = "No execution requested."
            elif result.skipped:
                status = "skipped"
                returncode = ""
                reason = result.skip_reason
            else:
                status = "passed" if result.returncode == 0 else "failed"
                returncode = str(result.returncode)
                reason = result.approval_reason or "executed"
            lines.append(f"| `{proposal.command_id}` | {status} | {returncode} | {reason} |")
    else:
        lines.append("| all | not_run |  | No execution requested. |")

    if failed:
        lines.extend(["", "## Failures"])
        for item in failed:
            lines.extend(
                [
                    "",
                    f"### {item.command_id}",
                    f"- Command: `{item.command}`",
                    f"- stderr tail: `{_one_line(item.stderr_tail)}`",
                    f"- stdout tail: `{_one_line(item.stdout_tail)}`",
                ]
            )

    if command_plan.feedback_candidates:
        ready = [item for item in command_plan.feedback_candidates if item.ready]
        pending = [item for item in command_plan.feedback_candidates if not item.ready]
        lines.extend(["", "## Feedback Handoff", f"- Ready: {len(ready)}", f"- Pending: {len(pending)}"])
        for item in command_plan.feedback_candidates:
            state = "ready" if item.ready else "pending"
            lines.append(f"- `{item.command_id}` {state} {item.result_kind}: `{item.result_csv}`")
            if item.feedback_command:
                lines.append(f"  - `{item.feedback_command}`")
    else:
        lines.extend(["", "## Feedback Handoff", "- No result CSV candidates were detected."])
    return "\n".join(lines) + "\n"


def _candidate_from_command(run_id: str, proposal: CommandProposal, root: Path) -> FeedbackCandidate | None:
    argv = shlex.split(proposal.command)
    result_kind = ""
    result_csv = ""
    if "run_backtest.py" in proposal.command:
        result_kind = "backtest"
        result_csv = _option_value(argv, "--output-csv")
    elif "run_walk_forward_validation.py" in proposal.command:
        result_kind = "walk_forward"
        candidate_run_id = _option_value(argv, "--run-id") or run_id
        result_csv = f"optimization_results/walk_forward_{candidate_run_id}/walk_forward_summary.csv"
    if not result_kind or not result_csv:
        return None

    result_path = Path(result_csv)
    if not result_path.is_absolute():
        result_path = root / result_path
    ready = result_path.exists()
    feedback_command = ""
    reason = "Result CSV exists and can be parsed." if ready else "Result CSV is not present yet."
    if ready:
        feedback_command = (
            f"./.venv/bin/python run_agent_strategy_iteration.py --feedback-run-id {run_id} "
            f"--result-csv {result_csv} --result-kind {result_kind}"
        )
    return FeedbackCandidate(
        command_id=proposal.command_id,
        result_kind=result_kind,
        result_csv=result_csv,
        ready=ready,
        feedback_command=feedback_command,
        reason=reason,
    )


def _option_value(argv: list[str], option: str) -> str:
    if option not in argv:
        return ""
    index = argv.index(option)
    if index + 1 >= len(argv):
        return ""
    return argv[index + 1]


def _has_template_placeholder(command: str) -> bool:
    return bool(re.search(r"<[A-Za-z0-9_.:/-]+>", command))


def _unresolved_placeholder_reason(proposal: CommandProposal) -> str:
    if _has_template_placeholder(proposal.command):
        return (
            "Command contains unresolved template placeholder(s), such as <candidate_model>. "
            "Edit the command to concrete paths/values before execution."
        )
    return ""


def _one_line(value: str, limit: int = 240) -> str:
    compact = " ".join((value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[-limit:]


def _add_guarded_templates(proposals: list[CommandProposal], seen: set[str], run_id: str) -> None:
    templates = [
        (
            "./.venv/bin/python run_backtest.py --model-path models/<candidate_model>.pkl "
            f"--topk 15 --n-drop 3 --hold-thresh 8 --output-csv backtest_results/agent_runs/{run_id}_same_model.csv",
            "guarded_template:same_model_backtest",
            "Draft same-model backtest command. Fill model path and approve before execution.",
        ),
        (
            "./.venv/bin/python run_walk_forward_validation.py --train-universes csi1000 --eval-market csi300 "
            f"--topk 15 --n-drop 3 --hold-thresh 8 --run-id {run_id}_wfv --workers 2",
            "guarded_template:walk_forward",
            "Draft WFV command. Requires explicit user approval because it is expensive.",
        ),
        (
            "./.venv/bin/python run_scheduled_rebalance.py --config config/daily_csi1000.yaml --dry-run",
            "guarded_template:rebalance_dry_run",
            "Draft scheduled rebalance dry-run. Kept behind approval because it has trading-like semantics.",
        ),
        (
            "./.venv/bin/python run_fetch_data.py --type fundamental",
            "guarded_template:data_fetch",
            "Draft data refresh command. Requires approval because it may use network and mutate cache.",
        ),
    ]
    for command, source, purpose in templates:
        _add_command(proposals, seen, command=command, source=source, purpose=purpose)


def _add_command(
    proposals: list[CommandProposal],
    seen: set[str],
    *,
    command: str,
    source: str,
    purpose: str,
) -> None:
    normalized = " ".join(str(command).strip().split())
    if not _looks_like_command(normalized) or normalized in seen:
        return
    seen.add(normalized)
    tags, requires_approval, reason, timeout = classify_command(normalized)
    proposals.append(
        CommandProposal(
            command_id=f"cmd_{len(proposals) + 1:03d}",
            command=normalized,
            purpose=purpose,
            source=source,
            risk_tags=tags,
            requires_approval=requires_approval,
            approval_reason=reason,
            timeout_seconds=timeout,
        )
    )


def _looks_like_command(value: str) -> bool:
    prefixes = (
        "./.venv/bin/python ",
        ".venv/bin/python ",
        "python ",
        "bash ",
        "pytest ",
    )
    return value.startswith(prefixes)


def _run_local_command(
    proposal: CommandProposal,
    root: Path,
    *,
    approval_reason: str = "",
    progress_callback: ProgressCallback | None = None,
    index: int = 1,
    total: int = 1,
) -> CommandExecutionResult:
    started = datetime.now().isoformat(timespec="seconds")
    try:
        argv = _safe_argv(proposal.command)
        process = subprocess.Popen(
            argv,
            cwd=root,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        output_events: "queue.Queue[tuple[str, str]]" = queue.Queue()

        def _reader(stream_name: str, pipe) -> None:
            try:
                for line in iter(pipe.readline, ""):
                    output_events.put((stream_name, line))
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        threads = [
            threading.Thread(target=_reader, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=_reader, args=("stderr", process.stderr), daemon=True),
        ]
        for thread in threads:
            thread.start()

        deadline = time.monotonic() + max(1, int(proposal.timeout_seconds or 120))
        timed_out = False

        while True:
            _drain_output_events(
                output_events,
                proposal,
                stdout_chunks,
                stderr_chunks,
                progress_callback=progress_callback,
                index=index,
                total=total,
            )
            if process.poll() is not None:
                break
            if time.monotonic() > deadline:
                timed_out = True
                process.kill()
                break
            time.sleep(0.1)

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=1)
        _drain_output_events(
            output_events,
            proposal,
            stdout_chunks,
            stderr_chunks,
            progress_callback=progress_callback,
            index=index,
            total=total,
        )
        if timed_out:
            stderr_chunks.append(f"\nCommand timed out after {proposal.timeout_seconds} seconds.\n")
        return CommandExecutionResult(
            command_id=proposal.command_id,
            command=proposal.command,
            skipped=False,
            returncode=124 if timed_out else process.returncode,
            started_at=started,
            ended_at=datetime.now().isoformat(timespec="seconds"),
            stdout_tail=_tail("".join(stdout_chunks)),
            stderr_tail=_tail("".join(stderr_chunks)),
            approval_reason=approval_reason,
        )
    except Exception as exc:  # pragma: no cover - defensive capture for command execution
        return CommandExecutionResult(
            command_id=proposal.command_id,
            command=proposal.command,
            skipped=False,
            returncode=1,
            started_at=started,
            ended_at=datetime.now().isoformat(timespec="seconds"),
            stderr_tail=str(exc),
            approval_reason=approval_reason,
        )


def _drain_output_events(
    output_events: "queue.Queue[tuple[str, str]]",
    proposal: CommandProposal,
    stdout_chunks: list[str],
    stderr_chunks: list[str],
    *,
    progress_callback: ProgressCallback | None,
    index: int,
    total: int,
) -> None:
    while True:
        try:
            stream_name, line = output_events.get_nowait()
        except queue.Empty:
            return

        if stream_name == "stderr":
            stderr_chunks.append(line)
        else:
            stdout_chunks.append(line)

        _emit_progress(
            progress_callback,
            "command_output",
            proposal,
            index=index,
            total=total,
            stream=stream_name,
            line=_tail(line, limit=2000),
            stdout_tail=_tail("".join(stdout_chunks), limit=2000),
            stderr_tail=_tail("".join(stderr_chunks), limit=2000),
        )


def _safe_argv(command: str) -> list[str]:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("Empty command")
    executable = argv[0]
    allowed = {"./.venv/bin/python", ".venv/bin/python", "python", "pytest"}
    if executable not in allowed:
        raise ValueError(f"Executable is not allowed by safe runner: {executable}")
    if _contains_shell_control(argv):
        raise ValueError("Shell control tokens are not allowed by safe runner")
    return argv


def _contains_shell_control(argv: Iterable[str]) -> bool:
    controls = {";", "&&", "||", "|", ">", ">>", "<", "$(", "`"}
    return any(token in controls or any(marker in token for marker in ["$(", "`"]) for token in argv)


def _tail(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]
