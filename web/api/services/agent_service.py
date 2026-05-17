"""Read-mostly helpers for agent strategy iteration run artifacts."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

from quant_ex.agent.strategy_iteration import (
    StrategyIterationOrchestrator,
    attach_feedback_candidates,
    build_agent_task_plan,
    build_command_plan,
    execute_approved_agent_tasks,
    execute_approved_commands,
    execute_safe_commands,
    generate_feedback,
    build_promotion_report,
    save_agent_approval_template,
    save_agent_task_plan,
    save_approval_template,
    save_command_plan,
)
from quant_ex.agent.strategy_iteration.schemas import (
    AgentTaskPlan,
    AgentTaskProposal,
    AgentTaskResult,
    CommandExecutionPlan,
    CommandExecutionResult,
    CommandProposal,
    ExperimentArm,
    FeedbackCandidate,
    RoleReport,
    StrategyIterationPlan,
)
from web.api.deps import AGENT_RUNS_DIR, PROJECT_ROOT

TEXT_ARTIFACTS = (
    "plan.md",
    "commands.md",
    "execution_summary.md",
    "agent_tasks.md",
    "discussion_trace.md",
    "feedback.md",
    "next_iteration.md",
    "promotion_report.md",
    "agent_approval_template.yaml",
    "approval_template.yaml",
)
JSON_ARTIFACTS = (
    "run.json",
    "commands.json",
    "agent_tasks.json",
    "discussion_trace.json",
    "feedback.json",
    "next_iteration.json",
    "promotion_report.json",
)


def list_agent_runs() -> list[dict[str, Any]]:
    runs_dir = AGENT_RUNS_DIR
    if not runs_dir.exists():
        return []
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
    run_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [_summarize_run(path) for path in run_dirs]


def get_agent_run(run_id: str) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    summary = _summarize_run(run_dir)
    payload: dict[str, Any] = {
        **summary,
        "approval_entries": _read_approval_entries(run_dir),
        "agent_approval_entries": _read_agent_approval_entries(run_dir),
        "artifacts": {},
    }

    for name in JSON_ARTIFACTS:
        parsed = _read_json(run_dir / name)
        if parsed is not None:
            payload["artifacts"][name] = parsed

    for name in TEXT_ARTIFACTS:
        path = run_dir / name
        if path.exists():
            payload["artifacts"][name] = path.read_text(encoding="utf-8")

    return payload


def delete_agent_run(run_id: str) -> dict[str, Any]:
    """Delete one saved agent run directory after path validation."""

    run_dir = _safe_run_dir(run_id)
    shutil.rmtree(run_dir)
    return {"run_id": run_id, "deleted": True}


def create_agent_run(
    *,
    objective: str,
    run_id: str | None = None,
    discussion_mode: str = "sequential",
    meeting_max_rounds: int | None = None,
    meeting_max_roles_per_round: int | None = None,
    use_llm: bool = False,
    propose_actions: bool = True,
    write_approval_template: bool = True,
    use_agent: bool = False,
    agent_provider: str = "codex",
    agent_mode: str = "readonly",
    agent_max_tasks: int = 2,
    write_agent_approval_template: bool = True,
    append_memory: bool = False,
    progress_callback=None,
) -> dict[str, Any]:
    if not objective.strip():
        raise HTTPException(status_code=400, detail="objective is required")
    if run_id:
        _validate_run_id(run_id)
        if (AGENT_RUNS_DIR / run_id).exists():
            raise HTTPException(status_code=409, detail="Agent run already exists")

    _emit_progress(progress_callback, "create_start", message="Loading agent iteration configuration.")
    orchestrator = StrategyIterationOrchestrator.from_config(PROJECT_ROOT / "config" / "agent_strategy_iteration.yaml")
    orchestrator.root = PROJECT_ROOT
    orchestrator.output_dir = AGENT_RUNS_DIR
    if not orchestrator.memory_log_path.is_absolute():
        orchestrator.memory_log_path = PROJECT_ROOT / orchestrator.memory_log_path
    _emit_progress(
        progress_callback,
        "plan_start",
        message="Building project context and running agent discussion.",
        discussion_mode=discussion_mode,
        use_llm=use_llm,
    )
    run = orchestrator.build_run(
        objective.strip(),
        use_llm=use_llm,
        run_id=run_id,
        discussion_mode=discussion_mode,
        meeting_max_rounds=meeting_max_rounds,
        meeting_max_roles_per_round=meeting_max_roles_per_round,
        progress_callback=progress_callback,
    )
    _emit_progress(
        progress_callback,
        "plan_done",
        message="Agent discussion completed; saving run artifacts.",
        run_id=run.run_id,
        role_count=len(run.plan.role_reports),
        arm_count=len(run.plan.experiment_arms),
    )
    run_dir = orchestrator.save_run(run, append_memory=append_memory)
    _emit_progress(progress_callback, "artifacts_done", message="Saved agent run artifacts.", run_id=run.run_id)

    if propose_actions:
        _emit_progress(progress_callback, "commands_start", message="Generating command proposals.", run_id=run.run_id)
        command_plan = build_command_plan(run.plan)
        command_plan = attach_feedback_candidates(command_plan, root=orchestrator.root)
        save_command_plan(command_plan, run_dir)
        if write_approval_template:
            save_approval_template(command_plan, run_dir)
        _emit_progress(
            progress_callback,
            "commands_done",
            message="Command proposals are ready.",
            run_id=run.run_id,
            command_count=len(command_plan.commands),
        )

    if use_agent:
        _emit_progress(progress_callback, "agent_tasks_start", message="Generating Codex task proposals.", run_id=run.run_id)
        agent_plan = build_agent_task_plan(
            run.plan,
            provider=agent_provider,
            mode=agent_mode,
            max_tasks=agent_max_tasks,
        )
        save_agent_task_plan(agent_plan, run_dir)
        if write_agent_approval_template:
            save_agent_approval_template(agent_plan, run_dir)
        _emit_progress(
            progress_callback,
            "agent_tasks_done",
            message="Codex task proposals are ready.",
            run_id=run.run_id,
            task_count=len(agent_plan.tasks),
        )

    summary = _summarize_run(run_dir)
    _emit_progress(progress_callback, "create_done", message="Agent run creation completed.", run_id=run.run_id)
    return {"run_id": run.run_id, "status": summary["status"], **_artifact_flags(summary)}


def _emit_progress(progress_callback, stage: str, **payload) -> None:
    if not progress_callback:
        return
    try:
        progress_callback("progress", stage=stage, **payload)
    except Exception:
        pass


def regenerate_approval_template(run_id: str) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    command_plan = _load_command_plan(run_dir)
    save_approval_template(command_plan, run_dir)
    summary = _summarize_run(run_dir)
    return {"run_id": summary["run_id"], "status": summary["status"], **_artifact_flags(summary)}


def update_command_approval(
    run_id: str,
    command_id: str,
    *,
    approved: bool,
    approved_by: str = "web",
    reason: str = "",
) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    command_plan = _load_command_plan(run_dir)
    proposal = next((item for item in command_plan.commands if item.command_id == command_id), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Command not found")

    template_path = run_dir / "approval_template.yaml"
    if not template_path.exists():
        save_approval_template(command_plan, run_dir)
    payload = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
    payload["run_id"] = command_plan.run_id
    approvals = payload.get("approvals") or []
    by_id = {str(item.get("command_id") or ""): item for item in approvals if isinstance(item, dict)}
    entry = by_id.get(command_id)
    if entry is None:
        entry = {
            "command_id": proposal.command_id,
            "command_sha256": proposal.command_sha256,
            "risk_tags": proposal.risk_tags,
            "command": proposal.command,
        }
        approvals.append(entry)
    entry.update(
        {
            "command_sha256": proposal.command_sha256,
            "approved": approved,
            "approved_by": approved_by if approved else "",
            "reason": reason,
            "approved_at": datetime.now().isoformat(timespec="seconds") if approved else "",
            "risk_tags": proposal.risk_tags,
            "command": proposal.command,
        }
    )
    payload["approvals"] = approvals
    template_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    summary = _summarize_run(run_dir)
    return {"run_id": summary["run_id"], "status": summary["status"], "approval_entries": _read_approval_entries(run_dir)}


def update_agent_task_approval(
    run_id: str,
    task_id: str,
    *,
    approved: bool,
    approved_by: str = "web",
    reason: str = "",
) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    agent_plan = _load_agent_task_plan(run_dir)
    proposal = next((item for item in agent_plan.tasks if item.task_id == task_id), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Agent task not found")

    template_path = run_dir / "agent_approval_template.yaml"
    if not template_path.exists():
        save_agent_approval_template(agent_plan, run_dir)
    payload = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
    payload["run_id"] = agent_plan.run_id
    approvals = payload.get("approvals") or []
    by_id = {str(item.get("task_id") or ""): item for item in approvals if isinstance(item, dict)}
    entry = by_id.get(task_id)
    if entry is None:
        entry = {
            "task_id": proposal.task_id,
            "prompt_sha256": proposal.prompt_sha256,
            "provider": proposal.provider,
            "mode": proposal.mode,
            "title": proposal.title,
        }
        approvals.append(entry)
    entry.update(
        {
            "prompt_sha256": proposal.prompt_sha256,
            "approved": approved,
            "approved_by": approved_by if approved else "",
            "reason": reason,
            "approved_at": datetime.now().isoformat(timespec="seconds") if approved else "",
            "provider": proposal.provider,
            "mode": proposal.mode,
            "title": proposal.title,
        }
    )
    payload["approvals"] = approvals
    template_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    summary = _summarize_run(run_dir)
    return {
        "run_id": summary["run_id"],
        "status": summary["status"],
        "agent_approval_entries": _read_agent_approval_entries(run_dir),
    }


def execute_agent_run_safe(
    run_id: str,
    *,
    command_ids: list[str] | None = None,
    skip_successful: bool = True,
    progress_callback=None,
) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    command_plan = _load_command_plan(run_dir)
    selected_plan = _select_commands(command_plan, command_ids)
    if skip_successful:
        selected_plan = _skip_successful_commands(selected_plan, command_plan.results)
    selected_plan = execute_safe_commands(selected_plan, root=PROJECT_ROOT, progress_callback=progress_callback)
    command_plan.results = _merge_results(command_plan.results, selected_plan.results)
    command_plan = attach_feedback_candidates(command_plan, root=PROJECT_ROOT)
    save_command_plan(command_plan, run_dir)
    summary = _summarize_run(run_dir)
    return {"run_id": summary["run_id"], "status": summary["status"], **_artifact_flags(summary)}


def execute_agent_run_approved(
    run_id: str,
    *,
    include_safe: bool = False,
    command_ids: list[str] | None = None,
    skip_successful: bool = True,
    progress_callback=None,
) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    approval_file = run_dir / "approval_template.yaml"
    if not approval_file.exists():
        raise HTTPException(status_code=404, detail="Approval template not found")
    command_plan = _load_command_plan(run_dir)
    selected_plan = _select_commands(command_plan, command_ids)
    if skip_successful:
        selected_plan = _skip_successful_commands(selected_plan, command_plan.results)
    selected_plan = execute_approved_commands(
        selected_plan,
        approval_file=approval_file,
        root=PROJECT_ROOT,
        include_safe=include_safe,
        progress_callback=progress_callback,
    )
    command_plan.results = _merge_results(command_plan.results, selected_plan.results)
    command_plan = attach_feedback_candidates(command_plan, root=PROJECT_ROOT)
    save_command_plan(command_plan, run_dir)
    summary = _summarize_run(run_dir)
    return {"run_id": summary["run_id"], "status": summary["status"], **_artifact_flags(summary)}


def execute_agent_run_tasks(
    run_id: str,
    *,
    task_ids: list[str] | None = None,
    skip_successful: bool = True,
    worktree_base: str = ".agent_worktrees",
    codex_bin: str = "codex",
    progress_callback=None,
) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    approval_file = run_dir / "agent_approval_template.yaml"
    if not approval_file.exists():
        raise HTTPException(status_code=404, detail="Agent approval template not found")
    agent_plan = _load_agent_task_plan(run_dir)
    selected_plan = _select_agent_tasks(agent_plan, task_ids)
    if skip_successful:
        selected_plan = _skip_successful_agent_tasks(selected_plan, agent_plan.results)
    _emit_progress(
        progress_callback,
        "agent_tasks_start",
        message="Executing approved coding-agent tasks.",
        run_id=run_id,
        task_count=len(selected_plan.tasks),
    )
    selected_plan = execute_approved_agent_tasks(
        selected_plan,
        approval_file=approval_file,
        root=PROJECT_ROOT,
        worktree_base=worktree_base,
        codex_bin=codex_bin,
    )
    agent_plan.results = _merge_agent_results(agent_plan.results, selected_plan.results)
    save_agent_task_plan(agent_plan, run_dir)
    _emit_progress(
        progress_callback,
        "agent_tasks_done",
        message="Approved coding-agent tasks completed.",
        run_id=run_id,
        result_count=len(selected_plan.results),
    )
    summary = _summarize_run(run_dir)
    return {"run_id": summary["run_id"], "status": summary["status"], **_artifact_flags(summary)}


def generate_agent_run_feedback(
    run_id: str,
    command_id: str,
    *,
    control_csv: str | None = None,
    rank_metric: str | None = None,
) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id)
    command_plan = attach_feedback_candidates(_load_command_plan(run_dir), root=PROJECT_ROOT)
    candidate = next((item for item in command_plan.feedback_candidates if item.command_id == command_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Feedback candidate not found")
    if not candidate.ready:
        raise HTTPException(status_code=400, detail="Feedback candidate result CSV is not ready")
    result_csv = Path(candidate.result_csv)
    if not result_csv.is_absolute():
        result_csv = PROJECT_ROOT / result_csv
    feedback = generate_feedback(
        run_id=run_id,
        result_csv=result_csv,
        result_kind=candidate.result_kind,
        control_csv=control_csv,
        rank_metric=rank_metric,
    )
    (run_dir / "feedback.json").write_text(
        json.dumps(feedback.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "feedback.md").write_text(feedback.to_markdown(), encoding="utf-8")
    promotion_report = build_promotion_report(
        run_id=run_id,
        result_csv=result_csv,
        control_csv=control_csv,
        result_kind=candidate.result_kind,
        rank_metric=rank_metric or "information_ratio",
    )
    (run_dir / "promotion_report.json").write_text(
        json.dumps(promotion_report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "promotion_report.md").write_text(promotion_report.to_markdown(), encoding="utf-8")
    next_iteration = _build_next_iteration_payload(feedback)
    (run_dir / "next_iteration.json").write_text(
        json.dumps(next_iteration, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "next_iteration.md").write_text(_next_iteration_to_markdown(next_iteration), encoding="utf-8")
    save_command_plan(command_plan, run_dir)
    summary = _summarize_run(run_dir)
    return {"run_id": summary["run_id"], "status": summary["status"], "feedback_decision": feedback.decision}


def _safe_run_dir(run_id: str) -> Path:
    _validate_run_id(run_id)
    base = AGENT_RUNS_DIR.resolve()
    run_dir = (base / run_id).resolve()
    if not run_dir.is_relative_to(base) or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run_dir


def _validate_run_id(run_id: str) -> None:
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    candidate = (AGENT_RUNS_DIR.resolve() / run_id).resolve()
    if not candidate.is_relative_to(AGENT_RUNS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid run_id")


def _summarize_run(run_dir: Path) -> dict[str, Any]:
    run_payload = _read_json(run_dir / "run.json") or {}
    commands_payload = _read_json(run_dir / "commands.json") or {}
    agent_tasks_payload = _read_json(run_dir / "agent_tasks.json") or {}
    feedback_payload = _read_json(run_dir / "feedback.json")
    commands = commands_payload.get("commands") or []
    results = commands_payload.get("results") or []
    feedback_candidates = commands_payload.get("feedback_candidates") or []
    agent_tasks = agent_tasks_payload.get("tasks") or []
    agent_results = agent_tasks_payload.get("results") or []
    approvals = _read_approval_entries(run_dir)
    agent_approvals = _read_agent_approval_entries(run_dir)
    stat = run_dir.stat()

    return {
        "run_id": run_dir.name,
        "objective": run_payload.get("objective"),
        "discussion_mode": run_payload.get("discussion_mode"),
        "discussion_settings": run_payload.get("discussion_settings") or {},
        "status": _derive_run_status(run_payload, commands_payload, feedback_payload, run_dir),
        "feedback_decision": (feedback_payload or {}).get("decision"),
        "generated_at": run_payload.get("generated_at"),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "has_plan": (run_dir / "plan.md").exists(),
        "has_commands": (run_dir / "commands.json").exists(),
        "has_feedback": feedback_payload is not None or (run_dir / "feedback.md").exists(),
        "has_next_iteration": (run_dir / "next_iteration.json").exists() or (run_dir / "next_iteration.md").exists(),
        "has_promotion_report": (run_dir / "promotion_report.json").exists() or (run_dir / "promotion_report.md").exists(),
        "has_execution_summary": (run_dir / "execution_summary.md").exists(),
        "has_approval_template": (run_dir / "approval_template.yaml").exists(),
        "has_agent_tasks": (run_dir / "agent_tasks.json").exists(),
        "has_agent_approval_template": (run_dir / "agent_approval_template.yaml").exists(),
        "commands_count": len(commands),
        "results_count": len(results),
        "feedback_candidates_count": len(feedback_candidates),
        "approved_commands_count": len([item for item in approvals if item.get("approved")]),
        "agent_tasks_count": len(agent_tasks),
        "agent_task_results_count": len(agent_results),
        "approved_agent_tasks_count": len([item for item in agent_approvals if item.get("approved")]),
    }


def _derive_run_status(
    run_payload: dict[str, Any],
    commands_payload: dict[str, Any],
    feedback_payload: dict[str, Any] | None,
    run_dir: Path,
) -> str:
    """Derive a display status for historical agent runs that predate status persistence."""
    if feedback_payload is not None:
        return "completed"

    results = commands_payload.get("results") or []
    if any(not item.get("skipped") and item.get("returncode") not in {0, None} for item in results):
        return "failed"

    commands = commands_payload.get("commands") or []
    agent_tasks_payload = _read_json(run_dir / "agent_tasks.json") or {}
    agent_tasks = agent_tasks_payload.get("tasks") or []
    agent_results = agent_tasks_payload.get("results") or []
    successful_agent_ids = {
        str(item.get("task_id") or "")
        for item in agent_results
        if not item.get("skipped") and item.get("returncode") == 0
    }
    pending_agent_tasks = [
        item
        for item in agent_tasks
        if item.get("requires_approval") and str(item.get("task_id") or "") not in successful_agent_ids
    ]
    if pending_agent_tasks:
        return "needs_approval"
    if commands:
        successful_ids = {
            str(item.get("command_id") or "")
            for item in results
            if not item.get("skipped") and item.get("returncode") == 0
        }
        pending_protected = [
            item
            for item in commands
            if item.get("requires_approval") and str(item.get("command_id") or "") not in successful_ids
        ]
        if pending_protected:
            return "needs_approval"
        if results and all(item.get("returncode") == 0 for item in results if not item.get("skipped")):
            return "completed"
        return "planned"

    if run_payload or (run_dir / "plan.md").exists():
        return "planned"
    return "artifact_only"


def _artifact_flags(summary: dict[str, Any]) -> dict[str, bool]:
    return {
        "has_plan": bool(summary["has_plan"]),
        "has_commands": bool(summary["has_commands"]),
        "has_feedback": bool(summary["has_feedback"]),
        "has_next_iteration": bool(summary.get("has_next_iteration")),
        "has_promotion_report": bool(summary.get("has_promotion_report")),
        "has_execution_summary": bool(summary["has_execution_summary"]),
        "has_approval_template": bool(summary["has_approval_template"]),
        "has_agent_tasks": bool(summary.get("has_agent_tasks")),
        "has_agent_approval_template": bool(summary.get("has_agent_approval_template")),
    }


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON artifact: {path.name}") from exc


def _read_approval_entries(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "approval_template.yaml"
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    approvals = payload.get("approvals") or []
    return [item for item in approvals if isinstance(item, dict)]


def _read_agent_approval_entries(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "agent_approval_template.yaml"
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    approvals = payload.get("approvals") or []
    return [item for item in approvals if isinstance(item, dict)]


def _select_commands(command_plan: CommandExecutionPlan, command_ids: list[str] | None) -> CommandExecutionPlan:
    if command_ids is None:
        return command_plan
    requested = {str(item) for item in command_ids if str(item)}
    known = {item.command_id for item in command_plan.commands}
    missing = sorted(requested - known)
    if missing:
        raise HTTPException(status_code=404, detail=f"Command not found: {', '.join(missing)}")
    return CommandExecutionPlan(
        run_id=command_plan.run_id,
        generated_at=command_plan.generated_at,
        policy=command_plan.policy,
        commands=[item for item in command_plan.commands if item.command_id in requested],
        results=[item for item in command_plan.results if item.command_id in requested],
        feedback_candidates=[item for item in command_plan.feedback_candidates if item.command_id in requested],
    )


def _skip_successful_commands(
    command_plan: CommandExecutionPlan,
    previous_results: list[CommandExecutionResult],
) -> CommandExecutionPlan:
    successful = {
        item.command_id
        for item in previous_results
        if not item.skipped and item.returncode == 0
    }
    if not successful:
        return command_plan
    return CommandExecutionPlan(
        run_id=command_plan.run_id,
        generated_at=command_plan.generated_at,
        policy=command_plan.policy,
        commands=[item for item in command_plan.commands if item.command_id not in successful],
        results=[item for item in command_plan.results if item.command_id not in successful],
        feedback_candidates=[
            item for item in command_plan.feedback_candidates if item.command_id not in successful
        ],
    )


def _merge_results(
    existing: list[CommandExecutionResult],
    updates: list[CommandExecutionResult],
) -> list[CommandExecutionResult]:
    by_id = {item.command_id: item for item in existing}
    for item in updates:
        by_id[item.command_id] = item
    return list(by_id.values())


def _select_agent_tasks(agent_plan: AgentTaskPlan, task_ids: list[str] | None) -> AgentTaskPlan:
    if task_ids is None:
        return agent_plan
    requested = {str(item) for item in task_ids if str(item)}
    known = {item.task_id for item in agent_plan.tasks}
    missing = sorted(requested - known)
    if missing:
        raise HTTPException(status_code=404, detail=f"Agent task not found: {', '.join(missing)}")
    return AgentTaskPlan(
        run_id=agent_plan.run_id,
        generated_at=agent_plan.generated_at,
        policy=agent_plan.policy,
        tasks=[item for item in agent_plan.tasks if item.task_id in requested],
        results=[item for item in agent_plan.results if item.task_id in requested],
    )


def _skip_successful_agent_tasks(
    agent_plan: AgentTaskPlan,
    previous_results: list[AgentTaskResult],
) -> AgentTaskPlan:
    successful = {
        item.task_id
        for item in previous_results
        if not item.skipped and item.returncode == 0
    }
    if not successful:
        return agent_plan
    return AgentTaskPlan(
        run_id=agent_plan.run_id,
        generated_at=agent_plan.generated_at,
        policy=agent_plan.policy,
        tasks=[item for item in agent_plan.tasks if item.task_id not in successful],
        results=[item for item in agent_plan.results if item.task_id not in successful],
    )


def _merge_agent_results(
    existing: list[AgentTaskResult],
    updates: list[AgentTaskResult],
) -> list[AgentTaskResult]:
    by_id = {item.task_id: item for item in existing}
    for item in updates:
        by_id[item.task_id] = item
    return list(by_id.values())


def _load_command_plan(run_dir: Path) -> CommandExecutionPlan:
    commands_payload = _read_json(run_dir / "commands.json")
    if commands_payload:
        return _command_plan_from_dict(commands_payload)

    run_payload = _read_json(run_dir / "run.json")
    plan_payload = (run_payload or {}).get("plan")
    if not plan_payload:
        raise HTTPException(status_code=404, detail="No saved plan or command plan for this run")
    return build_command_plan(_strategy_plan_from_dict(plan_payload))


def _load_agent_task_plan(run_dir: Path) -> AgentTaskPlan:
    payload = _read_json(run_dir / "agent_tasks.json")
    if not payload:
        run_payload = _read_json(run_dir / "run.json")
        plan_payload = (run_payload or {}).get("plan")
        if not plan_payload:
            raise HTTPException(status_code=404, detail="No saved plan or agent task plan for this run")
        plan = _strategy_plan_from_dict(plan_payload)
        return build_agent_task_plan(plan)
    return _agent_task_plan_from_dict(payload)


def _command_plan_from_dict(payload: dict[str, Any]) -> CommandExecutionPlan:
    return CommandExecutionPlan(
        run_id=str(payload.get("run_id") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        policy=str(payload.get("policy") or ""),
        commands=[CommandProposal(**item) for item in payload.get("commands") or []],
        results=[CommandExecutionResult(**item) for item in payload.get("results") or []],
        feedback_candidates=[FeedbackCandidate(**item) for item in payload.get("feedback_candidates") or []],
    )


def _agent_task_plan_from_dict(payload: dict[str, Any]) -> AgentTaskPlan:
    return AgentTaskPlan(
        run_id=str(payload.get("run_id") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        policy=str(payload.get("policy") or ""),
        tasks=[AgentTaskProposal(**item) for item in payload.get("tasks") or []],
        results=[AgentTaskResult(**item) for item in payload.get("results") or []],
    )


def _strategy_plan_from_dict(payload: dict[str, Any]) -> StrategyIterationPlan:
    return StrategyIterationPlan(
        run_id=str(payload.get("run_id") or ""),
        objective=str(payload.get("objective") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        role_reports=[RoleReport(**item) for item in payload.get("role_reports") or []],
        experiment_arms=[ExperimentArm(**item) for item in payload.get("experiment_arms") or []],
        validation_ladder=[str(item) for item in payload.get("validation_ladder") or []],
        decision_gates=[str(item) for item in payload.get("decision_gates") or []],
        synthesis=str(payload.get("synthesis") or ""),
        next_actions=[str(item) for item in payload.get("next_actions") or []],
        research_constraints=dict(payload.get("research_constraints") or {}),
    )


def _build_next_iteration_payload(feedback) -> dict[str, Any]:
    decision = str(feedback.decision or "hold")
    if decision in {"reject", "downgrade"}:
        objective = (
            f"Design a smaller orthogonal ablation after {feedback.run_id} was {decision}; "
            "keep adaptive_baseline_wf/adaptive_dd20_wf controls and avoid repeating the refuted configuration."
        )
    elif decision in {"compare_next", "hold"}:
        objective = (
            f"Escalate {feedback.run_id} only one validation rung with unchanged benchmark, rank_metric, "
            "deal_price, cost, and slippage assumptions."
        )
    else:
        objective = (
            f"Review whether {feedback.run_id} has enough WFV-grade evidence for candidate-index promotion."
        )
    return {
        "run_id": feedback.run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "feedback_decision": feedback.decision,
        "hypothesis_evaluation": feedback.hypothesis_evaluation,
        "recommended_objective": objective,
        "recommended_controls": ["adaptive_baseline_wf", "adaptive_dd20_wf"],
        "rank_metric": feedback.result.rank_metric or "information_ratio",
        "next_ablation": feedback.next_ablation,
        "do_not_repeat": feedback.do_not_repeat,
        "validation_ladder": [
            "Run import/registry/focused tests first.",
            "Run same-model backtest only as a cheap filter.",
            "Escalate to WFV only after explicit user approval.",
            "Append strategy_iteration_log.csv only for durable conclusions.",
        ],
    }


def _next_iteration_to_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Next Agent Iteration: {payload.get('run_id')}",
        "",
        f"- Generated: {payload.get('generated_at')}",
        f"- Feedback decision: {payload.get('feedback_decision')}",
        f"- Hypothesis evaluation: {payload.get('hypothesis_evaluation')}",
        f"- Rank metric: {payload.get('rank_metric')}",
        "",
        "## Recommended Objective",
        str(payload.get("recommended_objective") or ""),
        "",
        "## Controls",
        *[f"- {item}" for item in payload.get("recommended_controls") or []],
        "",
        "## Validation Ladder",
        *[f"- {item}" for item in payload.get("validation_ladder") or []],
    ]
    if payload.get("next_ablation"):
        lines.extend(["", "## Next Ablation", str(payload.get("next_ablation"))])
    if payload.get("do_not_repeat"):
        lines.extend(["", "## Do Not Repeat", *[f"- {item}" for item in payload.get("do_not_repeat") or []]])
    return "\n".join(lines) + "\n"
