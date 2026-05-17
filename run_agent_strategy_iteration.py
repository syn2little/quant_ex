from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.strategy_iteration import StrategyIterationOrchestrator
from agent.strategy_iteration.agent_execution import (
    build_agent_task_plan,
    execute_approved_agent_tasks,
    save_agent_approval_template,
    save_agent_task_plan,
)
from agent.strategy_iteration.evaluator import generate_feedback
from agent.strategy_iteration.execution import (
    attach_feedback_candidates,
    build_command_plan,
    execute_approved_commands,
    execute_safe_commands,
    save_approval_template,
    save_command_plan,
)
from agent.strategy_iteration.memory import StrategyAgentMemoryLog
from agent.strategy_iteration.schemas import AgentTaskPlan, AgentTaskProposal, AgentTaskResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a multi-role strategy iteration planning bundle.")
    parser.add_argument("--objective", help="Research objective for this planning run.")
    parser.add_argument("--config", default="config/agent_strategy_iteration.yaml", help="Planner config YAML path.")
    parser.add_argument("--run-id", default=None, help="Optional explicit run id.")
    parser.add_argument("--output-dir", default=None, help="Optional output directory override.")
    parser.add_argument(
        "--discussion-mode",
        choices=["sequential", "meeting"],
        default=None,
        help="Role discussion mode. sequential preserves the legacy fixed order; meeting lets a virtual chair select roles.",
    )
    parser.add_argument("--meeting-max-rounds", type=int, default=None, help="Maximum virtual-chair meeting rounds.")
    parser.add_argument(
        "--meeting-max-roles-per-round",
        type=int,
        default=None,
        help="Maximum roles the virtual chair may call in one meeting round.",
    )
    parser.add_argument("--use-llm", action="store_true", help="Enable optional OpenAI-compatible role execution.")
    parser.add_argument("--no-llm", action="store_true", help="Force offline role execution.")
    parser.add_argument("--no-memory", action="store_true", help="Do not append the memory log.")
    parser.add_argument("--propose-actions", action="store_true", help="Write commands.json/md with gated action proposals.")
    parser.add_argument(
        "--write-approval-template",
        action="store_true",
        help="Write approval_template.yaml with command ids and hashes.",
    )
    parser.add_argument(
        "--execute-safe",
        action="store_true",
        help="Execute only commands classified as safe_local and not requiring approval.",
    )
    parser.add_argument(
        "--execute-approved",
        action="store_true",
        help="Execute only commands explicitly approved by --approval-file.",
    )
    parser.add_argument("--approval-file", help="Approval YAML/JSON with matching command_id and command_sha256 entries.")
    parser.add_argument("--use-agent", action="store_true", help="Write local coding-agent task proposals.")
    parser.add_argument("--agent-provider", default="codex", help="Local coding-agent provider. Currently supports codex.")
    parser.add_argument(
        "--agent-mode",
        default="readonly",
        choices=["readonly", "patch", "danger-full-access"],
        help="Coding-agent execution mode. danger-full-access is reserved and high risk.",
    )
    parser.add_argument("--agent-max-tasks", type=int, default=2, help="Maximum coding-agent task proposals.")
    parser.add_argument(
        "--write-agent-approval-template",
        action="store_true",
        help="Write agent_approval_template.yaml for coding-agent tasks.",
    )
    parser.add_argument(
        "--execute-approved-agent-tasks",
        action="store_true",
        help="Execute approved coding-agent tasks from agent_approval_template.yaml.",
    )
    parser.add_argument("--agent-approval-file", help="Approval YAML/JSON for coding-agent tasks.")
    parser.add_argument("--agent-run-id", help="Existing run id whose agent_tasks.json should be executed.")
    parser.add_argument("--agent-worktree-dir", default=".agent_worktrees", help="Base directory for isolated agent worktrees.")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable name or path.")
    parser.add_argument("--feedback-run-id", help="Generate feedback for an existing agent run id.")
    parser.add_argument("--result-csv", help="CSV result to parse for feedback.")
    parser.add_argument("--control-csv", help="Optional control CSV for deltas.")
    parser.add_argument("--result-kind", default="auto", help="Result kind label, e.g. backtest or walk_forward.")
    parser.add_argument("--rank-metric", default=None, help="Optional rank metric override.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    orchestrator = StrategyIterationOrchestrator.from_config(args.config)
    if args.output_dir:
        orchestrator.output_dir = Path(args.output_dir)
        if not orchestrator.output_dir.is_absolute():
            orchestrator.output_dir = orchestrator.root / orchestrator.output_dir

    if args.feedback_run_id:
        if not args.result_csv:
            raise SystemExit("--result-csv is required with --feedback-run-id")
        feedback = generate_feedback(
            run_id=args.feedback_run_id,
            result_csv=args.result_csv,
            result_kind=args.result_kind,
            control_csv=args.control_csv,
            rank_metric=args.rank_metric,
        )
        run_dir = orchestrator.output_dir / args.feedback_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "feedback.json").write_text(
            json.dumps(feedback.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "feedback.md").write_text(feedback.to_markdown(), encoding="utf-8")
        if not args.no_memory:
            StrategyAgentMemoryLog(orchestrator.memory_log_path).append_feedback(feedback)
        print(run_dir / "feedback.json")
        return 0

    if args.execute_approved_agent_tasks and args.agent_run_id:
        if not args.agent_approval_file:
            raise SystemExit("--agent-approval-file is required with --execute-approved-agent-tasks")
        run_dir = orchestrator.output_dir / args.agent_run_id
        agent_plan_path = run_dir / "agent_tasks.json"
        if not agent_plan_path.exists():
            raise SystemExit(f"agent_tasks.json not found for run {args.agent_run_id}")
        agent_plan = _agent_task_plan_from_dict(json.loads(agent_plan_path.read_text(encoding="utf-8")))
        agent_plan = execute_approved_agent_tasks(
            agent_plan,
            approval_file=args.agent_approval_file,
            root=orchestrator.root,
            worktree_base=args.agent_worktree_dir,
            codex_bin=args.codex_bin,
        )
        save_agent_task_plan(agent_plan, run_dir)
        print(run_dir / "agent_tasks.json")
        return 0

    if not args.objective:
        raise SystemExit("--objective is required unless --feedback-run-id is used")

    use_llm = bool(args.use_llm and not args.no_llm)
    run = orchestrator.build_run(
        args.objective,
        use_llm=use_llm,
        run_id=args.run_id,
        discussion_mode=args.discussion_mode,
        meeting_max_rounds=args.meeting_max_rounds,
        meeting_max_roles_per_round=args.meeting_max_roles_per_round,
    )
    run_dir = orchestrator.save_run(run, append_memory=not args.no_memory)
    if args.execute_approved and not args.approval_file:
        raise SystemExit("--approval-file is required with --execute-approved")
    if args.execute_approved_agent_tasks and not args.agent_approval_file:
        raise SystemExit("--agent-approval-file is required with --execute-approved-agent-tasks")

    if args.propose_actions or args.execute_safe or args.write_approval_template or args.execute_approved:
        command_plan = build_command_plan(run.plan)
        if args.execute_safe:
            command_plan = execute_safe_commands(command_plan, root=orchestrator.root)
        if args.execute_approved:
            command_plan = execute_approved_commands(
                command_plan,
                approval_file=args.approval_file,
                root=orchestrator.root,
                include_safe=args.execute_safe,
            )
        command_plan = attach_feedback_candidates(command_plan, root=orchestrator.root)
        save_command_plan(command_plan, run_dir)
        if args.write_approval_template:
            save_approval_template(command_plan, run_dir)
    if args.use_agent or args.write_agent_approval_template or args.execute_approved_agent_tasks:
        agent_plan = build_agent_task_plan(
            run.plan,
            provider=args.agent_provider,
            mode=args.agent_mode,
            max_tasks=args.agent_max_tasks,
        )
        if args.execute_approved_agent_tasks:
            agent_plan = execute_approved_agent_tasks(
                agent_plan,
                approval_file=args.agent_approval_file,
                root=orchestrator.root,
                worktree_base=args.agent_worktree_dir,
                codex_bin=args.codex_bin,
            )
        save_agent_task_plan(agent_plan, run_dir)
        if args.write_agent_approval_template:
            save_agent_approval_template(agent_plan, run_dir)
    print(run_dir)
    return 0


def _agent_task_plan_from_dict(payload: dict) -> AgentTaskPlan:
    return AgentTaskPlan(
        run_id=str(payload.get("run_id") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        policy=str(payload.get("policy") or ""),
        tasks=[AgentTaskProposal(**item) for item in payload.get("tasks") or []],
        results=[AgentTaskResult(**item) for item in payload.get("results") or []],
    )


if __name__ == "__main__":
    raise SystemExit(main())
