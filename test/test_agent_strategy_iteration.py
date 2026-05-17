import json
from pathlib import Path

import requests
import yaml

from agent.strategy_iteration.agent_execution import (
    AGENT_MODE_DANGER_FULL_ACCESS,
    build_agent_task_plan,
    execute_approved_agent_tasks,
    save_agent_approval_template,
    save_agent_task_plan,
)
from agent.strategy_iteration.context import build_project_context
from agent.strategy_iteration.evaluator import generate_feedback, parse_metric_snapshot
from agent.strategy_iteration.llm import OpenAICompatibleChatClient, _repair_mojibake
from agent.strategy_iteration.execution import (
    EXPENSIVE_TAG,
    SAFE_LOCAL_TAG,
    attach_feedback_candidates,
    build_execution_summary,
    build_command_plan,
    classify_command,
    execute_approved_commands,
    execute_safe_commands,
    save_approval_template,
)
from agent.strategy_iteration.schemas import CommandExecutionPlan, CommandProposal, ExperimentArm, RoleReport
from agent.strategy_iteration.memory import StrategyAgentMemoryLog
from agent.strategy_iteration.orchestrator import StrategyIterationOrchestrator
from agent.strategy_iteration.prompt_loader import load_prompt_catalog
from agent.strategy_iteration.roles import DEFAULT_ROLES, RoleRunner
from agent.strategy_iteration.validation import ROLE_REQUIRED_FIELDS
from run_agent_strategy_iteration import main as run_agent_main


def test_build_project_context_collects_local_artifacts():
    context = build_project_context("phase1 context check")
    assert context.candidate_summary
    assert "recent_models" in context.available_artifacts
    assert context.available_artifacts["config_candidates"]
    assert "recent_backtests" in context.artifact_summaries
    assert context.config_summaries


def test_prompt_catalog_loads_all_role_prompts():
    catalog = load_prompt_catalog()
    assert "shared_system" in catalog
    assert "research_portfolio_manager" in catalog
    assert "same-model replay is a filter" in catalog["shared_system"].lower()
    for role in DEFAULT_ROLES:
        assert role.name in catalog
        assert "Mission:" in catalog[role.name]


def test_orchestrator_saves_run_bundle(tmp_path: Path):
    orchestrator = StrategyIterationOrchestrator(
        root=Path("."),
        output_dir=tmp_path / "agent_runs",
        memory_log_path=tmp_path / "agent_memory.md",
    )
    run = orchestrator.build_run("phase1 bundle check", use_llm=False, run_id="unit_phase1")
    run_dir = orchestrator.save_run(run, append_memory=True)

    assert (run_dir / "run.json").exists()
    assert (run_dir / "plan.md").exists()
    assert (run_dir / "context.json").exists()
    assert (run_dir / "prompts.json").exists()
    assert (run_dir / "role_traces.json").exists()
    assert (run_dir / "role_traces.md").exists()
    assert (run_dir / "discussion_trace.json").exists()
    assert (run_dir / "discussion_trace.md").exists()
    assert (tmp_path / "agent_memory.md").exists()
    assert run.discussion_mode == "sequential"
    assert run.discussion_trace == []
    assert run.plan.role_reports[-1].upstream_roles
    assert all(report.required_outputs for report in run.plan.role_reports)
    assert run.role_traces
    assert run.role_traces[0]["role"] == run.plan.role_reports[0].role
    assert "system_prompt" in run.role_traces[0]


def test_synthesis_counts_tradingagents_style_verdicts():
    reports = [
        RoleReport(role="data_factor_analyst", thesis="x", verdict="hold"),
        RoleReport(role="research_manager", thesis="x", verdict="CompareNext"),
        RoleReport(role="risk_reviewer", thesis="x", verdict="research_budget_worthy"),
        RoleReport(role="portfolio_manager", thesis="x", verdict="do_not_promote"),
    ]
    arms = [
        ExperimentArm(
            arm_id="control",
            hypothesis="x",
            change_type="control",
            owner_role="backtest_analyst",
        )
    ]

    synthesis = StrategyIterationOrchestrator._synthesize(reports, arms)

    assert "3 roles support continued research" in synthesis
    assert "1 roles recommend rejection" in synthesis


def test_memory_log_appends_entries(tmp_path: Path):
    memory = StrategyAgentMemoryLog(tmp_path / "memory.md")
    orchestrator = StrategyIterationOrchestrator(
        root=Path("."),
        output_dir=tmp_path / "runs",
        memory_log_path=tmp_path / "memory.md",
    )
    run = orchestrator.build_run("memory append check", use_llm=False, run_id="memory_case")
    memory.append_plan(run.plan, ["phase1_control_bundle"])
    entries = memory.load_entries()
    assert len(entries) == 1
    assert "phase1_control_bundle" in entries[0]


def test_cli_main_writes_run_bundle(tmp_path: Path):
    exit_code = run_agent_main(
        [
            "--objective",
            "cli phase1 check",
            "--run-id",
            "cli_case",
            "--output-dir",
            str(tmp_path / "cli_runs"),
            "--no-llm",
            "--no-memory",
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "cli_runs" / "cli_case" / "run.json").exists()


def test_role_runner_attaches_schema_and_carryover():
    context = build_project_context("phase2 carryover check")
    reports = RoleRunner().run_all(context, use_llm=False)
    assert reports[0].upstream_roles == []
    assert reports[1].upstream_roles == [reports[0].role]
    assert reports[-1].upstream_roles[-1] == reports[-2].role
    assert all(isinstance(report.schema_warnings, list) for report in reports)


def test_meeting_mode_runs_adaptive_offline_agenda():
    context = build_project_context("meeting mode offline check")
    runner = RoleRunner()

    reports = runner.run_meeting(context, use_llm=False, min_turns=4, max_turns=6)

    assert [report.role for report in reports] == [
        "data_factor_analyst",
        "backtest_analyst",
        "bear_researcher",
        "experiment_designer",
        "research_portfolio_manager",
    ]
    assert runner.chair_decisions[-1].action == "final"
    assert runner.discussion_trace
    assert runner.traces[0]["chair_focus"]


def test_meeting_mode_respects_roles_per_round_limit():
    context = build_project_context("meeting mode round limit check")
    runner = RoleRunner()

    reports = runner.run_meeting(context, use_llm=False, min_turns=4, max_turns=3, max_roles_per_turn=2)

    assert len(reports) == 6
    called_rounds = [item.get("called_roles") or [] for item in runner.discussion_trace if item.get("called_roles")]
    assert called_rounds[0] == ["data_factor_analyst", "backtest_analyst"]
    assert all(len(roles) <= 2 for roles in called_rounds)
    assert runner.chair_decisions[-1].missing_requirements == []


def test_orchestrator_meeting_settings_override_config():
    orchestrator = StrategyIterationOrchestrator(root=Path("."))

    run = orchestrator.build_run(
        "meeting settings check",
        use_llm=False,
        run_id="meeting_settings",
        discussion_mode="meeting",
        meeting_max_rounds=3,
        meeting_max_roles_per_round=2,
    )

    assert run.discussion_mode == "meeting"
    assert run.discussion_settings["max_rounds"] == 3
    assert run.discussion_settings["max_roles_per_round"] == 2
    assert len(run.plan.role_reports) == 6
    assert run.plan.research_constraints["default_controls"] == ["adaptive_baseline_wf", "adaptive_dd20_wf"]
    assert run.plan.discussion_decisions[-1].missing_requirements == []


def test_meeting_mode_uses_llm_chair_to_select_roles(monkeypatch):
    class FakeClient:
        model = "fake-deep"
        reasoning_effort = "low"
        temperature = 0.0
        max_tokens = 1200
        stream = False
        is_configured = True
        chair_calls = 0

        def complete_json(self, *, system, user, max_tokens=None):
            del user, max_tokens
            if "virtual meeting chair" in system:
                FakeClient.chair_calls += 1
                if FakeClient.chair_calls == 1:
                    return {
                        "action": "call_role",
                        "next_role": "bear_researcher",
                        "rationale": "Start with adversarial pressure.",
                        "focus": "Find kill tests first.",
                        "confidence": 0.8,
                    }
                return {
                    "action": "final",
                    "decision": "continue",
                    "final_summary": "Enough for the unit meeting.",
                    "confidence": 0.7,
                }
            return {
                "role": "bear_researcher",
                "thesis": "The proposal needs kill tests before execution.",
                "evidence": ["chair called bear first"],
                "proposals": ["define kill tests"],
                "risks": ["overfit"],
                "verdict": "continue_with_gates",
                "confidence": 0.8,
                "next_actions": ["call validation role if needed"],
                "prompt_name": "bear_researcher",
            }

    monkeypatch.setattr(
        "agent.strategy_iteration.roles.OpenAICompatibleChatClient.from_env",
        lambda **kwargs: FakeClient(),
    )
    context = build_project_context("meeting mode llm chair check")
    runner = RoleRunner()

    reports = runner.run_meeting(context, use_llm=True, min_turns=1, max_turns=3)

    assert reports[0].role == "bear_researcher"
    assert runner.chair_decisions[0].next_role == "bear_researcher"
    assert runner.chair_decisions[-1].action == "final"


def test_role_report_preserves_dict_proposals_as_readable_json():
    report = RoleReport.from_dict(
        "data_factor_analyst",
        {
            "role": "data_factor_analyst",
            "thesis": "x",
            "proposals": [
                {
                    "name": "northbound",
                    "description": "ååèµé",
                }
            ],
        },
    )

    assert report.proposals == ['{"name": "northbound", "description": "北向资金"}']


def test_role_schema_registry_covers_default_roles():
    missing = [role.name for role in DEFAULT_ROLES if role.name not in ROLE_REQUIRED_FIELDS]
    assert missing == []


def test_llm_client_uses_tiered_config(monkeypatch):
    monkeypatch.delenv("OPENAI_APIKEY", raising=False)
    monkeypatch.delenv("OPENAI_BASEURL", raising=False)
    monkeypatch.delenv("QUANT_EX_AGENT_DEEP_MODEL", raising=False)
    monkeypatch.delenv("QUANT_EX_AGENT_QUICK_MODEL", raising=False)
    config = {
        "api_key": "config-key",
        "base_url": "https://config.example.test/openai",
        "stream": True,
        "tiers": {
            "quick": {
                "model": "quick-model",
                "reasoning_effort": "low",
                "temperature": 0.1,
                "max_tokens": 1000,
            },
            "deep": {
                "model": "deep-model",
                "reasoning_effort": "high",
                "temperature": 0.2,
                "max_tokens": 2400,
            },
        }
    }

    quick = OpenAICompatibleChatClient.from_env(model_tier="quick", llm_config=config)
    deep = OpenAICompatibleChatClient.from_env(model_tier="deep", llm_config=config)

    assert quick.model == "quick-model"
    assert quick.reasoning_effort == "low"
    assert quick.max_tokens == 1000
    assert deep.model == "deep-model"
    assert deep.reasoning_effort == "high"
    assert deep.max_tokens == 2400
    assert deep.api_key == "config-key"
    assert deep.base_url == "https://config.example.test/openai"
    assert deep.stream is True
    assert deep.is_configured


def test_role_runner_falls_back_when_llm_request_fails(monkeypatch):
    class FailingClient:
        model = "failing-model"
        reasoning_effort = "low"
        temperature = 0.0
        max_tokens = 1200
        stream = False
        is_configured = True

        def complete_json(self, *, system, user, max_tokens=None):
            del system, user, max_tokens
            raise requests.exceptions.SSLError("unexpected eof")

    monkeypatch.setattr(
        "agent.strategy_iteration.roles.OpenAICompatibleChatClient.from_env",
        lambda **kwargs: FailingClient(),
    )

    context = build_project_context("llm failure fallback check")
    runner = RoleRunner(roles=DEFAULT_ROLES[:1])
    reports = runner.run_all(context, use_llm=True)

    assert len(reports) == 1
    assert reports[0].role == DEFAULT_ROLES[0].name
    assert runner.traces[0]["used_llm"] is False


def test_llm_client_falls_back_to_env_when_strings_absent(monkeypatch):
    monkeypatch.setenv("OPENAI_APIKEY", "env-key")
    monkeypatch.setenv("OPENAI_BASEURL", "https://env.example.test/openai")
    config = {"tiers": {"quick": {"model": "quick-model"}}}

    client = OpenAICompatibleChatClient.from_env(model_tier="quick", llm_config=config)

    assert client.api_key == "env-key"
    assert client.base_url == "https://env.example.test/openai"


def test_llm_stream_content_parser():
    class FakeResponse:
        @staticmethod
        def iter_lines(decode_unicode=True):
            del decode_unicode
            yield 'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"true}"}}]}'
            yield "data: [DONE]"

    assert OpenAICompatibleChatClient._read_stream_content(FakeResponse()) == '{"ok":true}'


def test_llm_parse_repairs_utf8_mojibake():
    payload = {
        "thesis": "ååèµéç ç©¶å¯ä»¥ç»§ç»­",
        "evidence": ["ç¹ä½é£é©"],
        "plain": "northbound research",
    }

    repaired = _repair_mojibake(payload)

    assert repaired["thesis"] == "北向资金研究可以继续"
    assert repaired["evidence"] == ["点位风险"]
    assert repaired["plain"] == "northbound research"


def test_llm_tier_model_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_APIKEY", "test-key")
    monkeypatch.setenv("OPENAI_BASEURL", "https://example.test/openai")
    monkeypatch.setenv("QUANT_EX_AGENT_DEEP_MODEL", "env-deep-model")
    config = {"tiers": {"deep": {"model": "config-deep-model"}}}

    client = OpenAICompatibleChatClient.from_env(model_tier="deep", llm_config=config)

    assert client.model == "env-deep-model"


def test_orchestrator_loads_llm_tier_config():
    orchestrator = StrategyIterationOrchestrator.from_config("config/agent_strategy_iteration.yaml")

    assert orchestrator.llm_config["base_url"] == "https://www.zwddd.com/openai"
    assert orchestrator.llm_config["tiers"]["quick"]["model"] == "gpt-5.4-mini"
    assert orchestrator.llm_config["tiers"]["deep"]["model"] == "gpt-5.5"
    assert orchestrator.llm_config["tiers"]["deep"]["reasoning_effort"] == "high"


def test_parse_metric_snapshot_selects_best_information_ratio(tmp_path: Path):
    result = tmp_path / "result.csv"
    result.write_text(
        "topk,information_ratio,sharpe,max_drawdown\n"
        "5,0.1,2.0,-0.2\n"
        "10,0.5,1.0,-0.1\n",
        encoding="utf-8",
    )
    snapshot = parse_metric_snapshot(result, result_kind="backtest")
    assert snapshot.rank_metric == "information_ratio"
    assert snapshot.best_row["topk"] == "10"


def test_generate_feedback_compares_control(tmp_path: Path):
    treatment = tmp_path / "treatment.csv"
    control = tmp_path / "control.csv"
    treatment.write_text(
        "topk,information_ratio,sharpe,max_drawdown\n"
        "10,0.6,1.4,-0.12\n",
        encoding="utf-8",
    )
    control.write_text(
        "topk,information_ratio,sharpe,max_drawdown\n"
        "15,0.4,1.2,-0.10\n",
        encoding="utf-8",
    )
    feedback = generate_feedback(
        run_id="feedback_case",
        result_csv=treatment,
        result_kind="backtest",
        control_csv=control,
    )
    assert feedback.deltas["information_ratio"] > 0
    assert feedback.decision == "compare_next"
    assert feedback.hypothesis_evaluation == "supported"


def test_generate_feedback_reads_walk_forward_summary(tmp_path: Path):
    summary = tmp_path / "walk_forward_summary.csv"
    summary.write_text(
        "topk,n_drop,hold_thresh,mean_sharpe,min_sharpe,sharpe_ttest_pvalue,robust_score\n"
        "15,3,8,1.0,0.1,0.05,0.9\n",
        encoding="utf-8",
    )
    feedback = generate_feedback(
        run_id="wf_case",
        result_csv=summary,
        result_kind="walk_forward",
    )
    assert feedback.result.rank_metric == "robust_score"
    assert feedback.decision == "compare_next"


def test_cli_feedback_writes_feedback_bundle(tmp_path: Path):
    result = tmp_path / "result.csv"
    result.write_text(
        "topk,information_ratio,sharpe,max_drawdown\n"
        "10,0.5,1.3,-0.1\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "runs"
    exit_code = run_agent_main(
        [
            "--feedback-run-id",
            "feedback_cli",
            "--result-csv",
            str(result),
            "--result-kind",
            "backtest",
            "--output-dir",
            str(output_dir),
            "--no-memory",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "feedback_cli" / "feedback.json").exists()
    assert (output_dir / "feedback_cli" / "feedback.md").exists()


def test_command_classifier_requires_approval_for_expensive_commands():
    tags, requires_approval, reason, timeout = classify_command(
        "./.venv/bin/python run_walk_forward_validation.py --topk 15"
    )
    assert EXPENSIVE_TAG in tags
    assert requires_approval
    assert "Protected risk" in reason
    assert timeout >= 900


def test_command_plan_collects_and_gates_validation_commands():
    orchestrator = StrategyIterationOrchestrator(root=Path("."))
    run = orchestrator.build_run("phase4 command proposal check", use_llm=False, run_id="phase4_unit")
    command_plan = build_command_plan(run.plan)
    commands = [item.command for item in command_plan.commands]

    assert any("test/test_agent_strategy_iteration.py" in command for command in commands)
    assert any("run_train.py --list-registry" in command for command in commands)
    assert len(commands) == len(set(commands))
    registry = next(item for item in command_plan.commands if "run_train.py --list-registry" in item.command)
    assert SAFE_LOCAL_TAG in registry.risk_tags
    assert not registry.requires_approval
    wfv = next(item for item in command_plan.commands if "run_walk_forward_validation.py" in item.command)
    assert EXPENSIVE_TAG in wfv.risk_tags
    assert wfv.requires_approval


def test_execute_safe_commands_skips_protected_commands():
    orchestrator = StrategyIterationOrchestrator(root=Path("."))
    run = orchestrator.build_run("phase4 execute safe check", use_llm=False, run_id="phase4_exec")
    command_plan = build_command_plan(run.plan)
    command_plan.commands = [
        item
        for item in command_plan.commands
        if "from agent.strategy_iteration" in item.command or "run_walk_forward_validation.py" in item.command
    ]
    command_plan.commands.append(
        command_plan.commands[0].__class__(
            command_id="cmd_wfv",
            command="./.venv/bin/python run_walk_forward_validation.py --topk 15",
            purpose="Protected WFV smoke proposal.",
            source="unit",
            risk_tags=[EXPENSIVE_TAG],
            requires_approval=True,
            approval_reason="Protected risk tag(s): expensive.",
            timeout_seconds=900,
        )
    )

    executed = execute_safe_commands(command_plan, root=Path("."))
    assert any(result.returncode == 0 and not result.skipped for result in executed.results)
    assert any(result.command_id == "cmd_wfv" and result.skipped for result in executed.results)


def test_execute_safe_commands_streams_command_output():
    proposal = CommandProposal(
        command_id="cmd_stream",
        command="./.venv/bin/python -c \"import sys; print('hello stdout'); print('hello stderr', file=sys.stderr)\"",
        purpose="stream smoke",
        source="unit",
        risk_tags=[SAFE_LOCAL_TAG],
        requires_approval=False,
    )
    command_plan = CommandExecutionPlan(
        run_id="stream_case",
        generated_at="2026-05-15T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    events = []

    def collect(event_type, **payload):
        events.append((event_type, payload))

    executed = execute_safe_commands(command_plan, root=Path("."), progress_callback=collect)

    assert executed.results[0].returncode == 0
    output_events = [payload for event_type, payload in events if payload.get("stage") == "command_output"]
    assert any(payload.get("stream") == "stdout" and "hello stdout" in payload.get("line", "") for payload in output_events)
    assert any(payload.get("stream") == "stderr" and "hello stderr" in payload.get("line", "") for payload in output_events)
    assert any(payload.get("stage") == "command_done" and payload.get("stdout_tail") for _, payload in events)


def test_execute_approved_commands_skip_unresolved_template_placeholders(tmp_path: Path):
    proposal = CommandProposal(
        command_id="cmd_template",
        command="./.venv/bin/python run_backtest.py --model-path models/<candidate_model>.pkl --output-csv backtest_results/demo.csv",
        purpose="template backtest",
        source="unit",
        risk_tags=[EXPENSIVE_TAG, "template_placeholder"],
        requires_approval=True,
        approval_reason="Protected risk tag(s): expensive, template_placeholder.",
    )
    command_plan = CommandExecutionPlan(
        run_id="template_guard",
        generated_at="2026-05-15T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    approval_file = tmp_path / "approval.yaml"
    approval_file.write_text(
        yaml.safe_dump(
            {
                "run_id": command_plan.run_id,
                "approvals": [
                    {
                        "command_id": proposal.command_id,
                        "command_sha256": proposal.command_sha256,
                        "approved": True,
                        "reason": "unit approval should still not execute placeholders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    executed = execute_approved_commands(command_plan, approval_file=approval_file, root=Path("."))

    assert executed.results[0].skipped
    assert "unresolved template placeholder" in executed.results[0].skip_reason
    assert executed.results[0].returncode is None


def test_cli_propose_actions_writes_command_bundle(tmp_path: Path):
    output_dir = tmp_path / "runs"
    exit_code = run_agent_main(
        [
            "--objective",
            "cli phase4 actions check",
            "--run-id",
            "actions_cli",
            "--output-dir",
            str(output_dir),
            "--no-llm",
            "--no-memory",
            "--propose-actions",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "actions_cli" / "commands.json").exists()
    assert (output_dir / "actions_cli" / "commands.md").exists()
    assert (output_dir / "actions_cli" / "execution_summary.md").exists()


def test_agent_task_plan_and_danger_warning(tmp_path: Path):
    orchestrator = StrategyIterationOrchestrator(root=Path("."))
    run = orchestrator.build_run("agent task planning check", use_llm=False, run_id="agent_task_plan")

    agent_plan = build_agent_task_plan(
        run.plan,
        mode=AGENT_MODE_DANGER_FULL_ACCESS,
        max_tasks=1,
    )
    approval_path = save_agent_approval_template(agent_plan, tmp_path)
    payload = yaml.safe_load(approval_path.read_text(encoding="utf-8"))

    assert len(agent_plan.tasks) == 1
    assert agent_plan.tasks[0].requires_approval
    assert agent_plan.tasks[0].mode == "danger-full-access"
    assert "DANGER" in agent_plan.tasks[0].approval_reason
    assert payload["approvals"][0]["approved"] is False
    assert "DANGER" in payload["approvals"][0]["warning"]


def test_agent_task_execution_requires_approval(tmp_path: Path):
    orchestrator = StrategyIterationOrchestrator(root=Path("."))
    run = orchestrator.build_run("agent task approval check", use_llm=False, run_id="agent_task_approval")
    agent_plan = build_agent_task_plan(run.plan, mode="readonly", max_tasks=1)
    approval_file = tmp_path / "approval.yaml"
    approval_file.write_text(
        yaml.safe_dump(
            {
                "run_id": agent_plan.run_id,
                "approvals": [
                    {
                        "task_id": agent_plan.tasks[0].task_id,
                        "prompt_sha256": agent_plan.tasks[0].prompt_sha256,
                        "approved": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    executed = execute_approved_agent_tasks(
        agent_plan,
        approval_file=approval_file,
        root=Path("."),
        codex_bin="definitely_missing_codex_for_unit_test",
    )

    assert executed.results[0].skipped
    assert "approved=false" in executed.results[0].skip_reason


def test_cli_use_agent_writes_task_bundle(tmp_path: Path):
    output_dir = tmp_path / "runs"
    exit_code = run_agent_main(
        [
            "--objective",
            "cli agent task check",
            "--run-id",
            "agent_cli",
            "--output-dir",
            str(output_dir),
            "--no-llm",
            "--no-memory",
            "--use-agent",
            "--agent-mode",
            "patch",
            "--agent-max-tasks",
            "1",
            "--write-agent-approval-template",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "agent_cli" / "agent_tasks.json").exists()
    assert (output_dir / "agent_cli" / "agent_tasks.md").exists()
    assert (output_dir / "agent_cli" / "agent_approval_template.yaml").exists()


def test_save_approval_template_includes_command_hashes(tmp_path: Path):
    orchestrator = StrategyIterationOrchestrator(root=Path("."))
    run = orchestrator.build_run("phase4 approval template check", use_llm=False, run_id="approval_template")
    command_plan = build_command_plan(run.plan)
    output = save_approval_template(command_plan, tmp_path)
    content = output.read_text(encoding="utf-8")

    assert "run_id: approval_template" in content
    assert "command_sha256:" in content
    assert "approved: false" in content


def test_execute_approved_commands_requires_hash_match(tmp_path: Path):
    proposal = CommandProposal(
        command_id="cmd_approved",
        command="./.venv/bin/python -c \"print('APPROVED_OK')\"",
        purpose="Approved protected command smoke test.",
        source="unit",
        risk_tags=[EXPENSIVE_TAG],
        requires_approval=True,
        approval_reason="Protected risk tag(s): expensive.",
    )
    command_plan = CommandExecutionPlan(
        run_id="approval_exec",
        generated_at="2026-05-13T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "run_id": "approval_exec",
                "approvals": [
                    {
                        "command_id": "cmd_approved",
                        "command_sha256": proposal.command_sha256,
                        "approved": True,
                        "approved_by": "unit",
                        "reason": "bounded unit smoke command",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    executed = execute_approved_commands(command_plan, approval_file=approval_file, root=Path("."))
    assert executed.results[0].returncode == 0
    assert "APPROVED_OK" in executed.results[0].stdout_tail


def test_execute_approved_commands_skips_hash_mismatch(tmp_path: Path):
    proposal = CommandProposal(
        command_id="cmd_mismatch",
        command="./.venv/bin/python -c \"print('SHOULD_NOT_RUN')\"",
        purpose="Hash mismatch smoke test.",
        source="unit",
        risk_tags=[EXPENSIVE_TAG],
        requires_approval=True,
    )
    command_plan = CommandExecutionPlan(
        run_id="approval_mismatch",
        generated_at="2026-05-13T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "run_id": "approval_mismatch",
                "approvals": [
                    {
                        "command_id": "cmd_mismatch",
                        "command_sha256": "wrong_hash",
                        "approved": True,
                        "reason": "stale approval",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    executed = execute_approved_commands(command_plan, approval_file=approval_file, root=Path("."))
    assert executed.results[0].skipped
    assert "sha256" in executed.results[0].skip_reason


def test_cli_write_approval_template(tmp_path: Path):
    output_dir = tmp_path / "runs"
    exit_code = run_agent_main(
        [
            "--objective",
            "cli phase4 approval template check",
            "--run-id",
            "approval_cli",
            "--output-dir",
            str(output_dir),
            "--no-llm",
            "--no-memory",
            "--propose-actions",
            "--write-approval-template",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "approval_cli" / "approval_template.yaml").exists()


def test_cli_execute_approved_uses_approval_file(tmp_path: Path):
    orchestrator = StrategyIterationOrchestrator(root=Path("."))
    run = orchestrator.build_run("cli phase4 approved execution check", use_llm=False, run_id="approved_cli")
    command_plan = build_command_plan(run.plan)
    approved = command_plan.commands[0]
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "run_id": "approved_cli",
                "approvals": [
                    {
                        "command_id": approved.command_id,
                        "command_sha256": approved.command_sha256,
                        "approved": True,
                        "reason": "unit approval",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "runs"

    exit_code = run_agent_main(
        [
            "--objective",
            "cli phase4 approved execution check",
            "--run-id",
            "approved_cli",
            "--output-dir",
            str(output_dir),
            "--no-llm",
            "--no-memory",
            "--propose-actions",
            "--execute-approved",
            "--approval-file",
            str(approval_file),
        ]
    )
    command_results = json.loads((output_dir / "approved_cli" / "commands.json").read_text(encoding="utf-8"))[
        "results"
    ]
    assert exit_code == 0
    assert command_results[0]["returncode"] == 0
    assert any(item["skipped"] for item in command_results[1:])
    assert (output_dir / "approved_cli" / "execution_summary.md").exists()


def test_execution_summary_counts_results():
    proposal = CommandProposal(
        command_id="cmd_summary",
        command="./.venv/bin/python -c \"print('OK')\"",
        purpose="summary smoke",
        source="unit",
        risk_tags=[SAFE_LOCAL_TAG],
        requires_approval=False,
    )
    command_plan = CommandExecutionPlan(
        run_id="summary_case",
        generated_at="2026-05-13T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    command_plan = execute_safe_commands(command_plan, root=Path("."))
    summary = build_execution_summary(command_plan)
    assert "Passed: 1" in summary
    assert "`cmd_summary`" in summary


def test_feedback_candidates_detect_ready_backtest_csv(tmp_path: Path):
    result_csv = tmp_path / "backtest.csv"
    result_csv.write_text("topk,information_ratio,sharpe\n15,0.4,1.2\n", encoding="utf-8")
    proposal = CommandProposal(
        command_id="cmd_backtest",
        command=f"./.venv/bin/python run_backtest.py --model-path models/demo.pkl --output-csv {result_csv}",
        purpose="backtest candidate",
        source="unit",
        risk_tags=[EXPENSIVE_TAG],
        requires_approval=True,
    )
    command_plan = CommandExecutionPlan(
        run_id="feedback_ready",
        generated_at="2026-05-13T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    command_plan = attach_feedback_candidates(command_plan, root=Path("."))
    candidate = command_plan.feedback_candidates[0]
    assert candidate.ready
    assert candidate.result_kind == "backtest"
    assert "--feedback-run-id feedback_ready" in candidate.feedback_command


def test_feedback_candidates_detect_pending_walk_forward_summary():
    proposal = CommandProposal(
        command_id="cmd_wfv_candidate",
        command="./.venv/bin/python run_walk_forward_validation.py --run-id missing_wfv",
        purpose="wfv candidate",
        source="unit",
        risk_tags=[EXPENSIVE_TAG],
        requires_approval=True,
    )
    command_plan = CommandExecutionPlan(
        run_id="feedback_pending",
        generated_at="2026-05-13T00:00:00",
        policy="unit",
        commands=[proposal],
    )
    command_plan = attach_feedback_candidates(command_plan, root=Path("."))
    candidate = command_plan.feedback_candidates[0]
    assert not candidate.ready
    assert candidate.result_kind == "walk_forward"
    assert "walk_forward_missing_wfv" in candidate.result_csv
