import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_ex.agent.strategy_iteration.execution import SAFE_LOCAL_TAG, save_command_plan
from quant_ex.agent.strategy_iteration.schemas import CommandExecutionPlan, CommandExecutionResult, CommandProposal
from web.api.app import create_app
from web.api.routers import agents as agents_router
from web.api.routers import backtest as backtest_router
from web.api.routers import data as data_router
from web.api.routers import signals as signals_router
from web.api.services import agent_service
from web.api.services import chart_service
from web.api.services.data_service import _json_safe_quote_records


def test_spa_deep_link_falls_back_to_index():
    client = TestClient(create_app())

    response = client.get("/models")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<div id="root">' in response.text


def test_api_routes_are_not_intercepted_by_spa_fallback():
    client = TestClient(create_app())

    response = client.get("/api/system/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sector_list_uses_sector_map_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "sector_map.json").write_text(
        '{"SH600000": "Banks", "SZ000001": "Banks", "SH600519": "Liquor"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(data_router, "CACHE_DIR", cache_dir)

    client = TestClient(create_app())
    response = client.get("/api/data/sectors")

    assert response.status_code == 200
    assert response.json() == [
        {"sector_id": "Banks", "sector_name": "Banks", "stock_count": 2},
        {"sector_id": "Liquor", "sector_name": "Liquor", "stock_count": 1},
    ]


def test_stock_quote_records_are_strict_json_safe():
    df = pd.DataFrame(
        {
            "open": [1.0, float("nan")],
            "close": [float("inf"), float("-inf")],
            "volume": [100, pd.NA],
        },
        index=pd.to_datetime(["2026-05-11", "2026-05-12"]),
    )

    records = _json_safe_quote_records(df)

    assert records == [
        {"date": "2026-05-11", "open": 1.0, "close": None, "volume": 100},
        {"date": "2026-05-12", "open": None, "close": None, "volume": None},
    ]
    json.dumps(records, allow_nan=False)


def test_equity_curve_accepts_qlib_bench_column(monkeypatch, tmp_path):
    result_dir = tmp_path / "backtest_results"
    result_dir.mkdir()
    (result_dir / "daily.csv").write_text(
        "date,return,bench\n2026-01-01,0.1,0.05\n2026-01-02,-0.1,0.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(chart_service, "BACKTEST_RESULTS_DIR", result_dir)

    curve = chart_service.parse_equity_curve("daily.csv")

    assert curve["portfolio"] == [1.1, 0.99]
    assert curve["benchmark"] == [1.05, 1.05]
    assert curve["excess"] == [0.05, -0.06]


def test_notify_test_defaults_to_dry_run_without_sending():
    client = TestClient(create_app())

    response = client.post(
        "/api/signals/notify-test",
        json={"title": "Test", "content": "Preview only"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["dry_run"] is True
    assert payload["sent"] is False


def test_notify_test_requires_confirmation_for_real_send():
    client = TestClient(create_app())

    response = client.post(
        "/api/signals/notify-test",
        json={
            "title": "Test",
            "content": "Should not send",
            "dry_run": False,
            "confirm_send": False,
        },
    )

    assert response.status_code == 400
    assert "confirm_send=true" in response.json()["detail"]


def test_rebalance_command_includes_web_supported_safety_flags():
    req = signals_router.RebalanceRequest(
        mock=False,
        dry_run=True,
        config="config/daily_csi1000.yaml",
        positions="SH600489:900",
        position_date="2026-05-08",
        min_action_value=1000,
        skip_update=True,
        force=True,
        notify_channel="bark",
    )

    cmd = signals_router._build_rebalance_cmd(req)

    assert "--dry-run" in cmd
    assert "--skip-update" in cmd
    assert "--force" in cmd
    assert cmd[cmd.index("--config") + 1] == "config/daily_csi1000.yaml"
    assert cmd[cmd.index("--positions") + 1] == "SH600489:900"
    assert cmd[cmd.index("--position-date") + 1] == "2026-05-08"
    assert cmd[cmd.index("--min-action-value") + 1] == "1000.0"
    assert cmd[cmd.index("--notify-channel") + 1] == "bark"


def test_grid_command_includes_advanced_web_params():
    req = backtest_router.GridSearchRequest(
        model_path="models/demo.pkl",
        topk=[5, 15],
        n_drop=[1, 3],
        hold_thresh=[5, 8],
        start="2024-01-01",
        end="2026-05-11",
        market="csi300",
        multi_seed=True,
        optimize=True,
        n_iters=5,
        grid_workers=4,
        output_csv="backtest_results/demo.csv",
        benchmark="SH000905",
        deal_price="open",
        open_cost=0.0007,
        close_cost=0.0017,
        min_cost=3.5,
        slippage_sensitivity=True,
        slippage_multipliers=[0.0, 1.0, 2.0],
        markets=["csi300", "csi1000"],
        explore_markets=True,
    )

    cmd = backtest_router._build_grid_cmd(req)

    assert "--seeds" in cmd
    assert "--optimize" in cmd
    assert "--slippage-sensitivity" in cmd
    assert "--explore-markets" in cmd
    assert cmd[cmd.index("--model-path") + 1] == "models/demo.pkl"
    assert cmd[cmd.index("--topk") + 1] == "5,15"
    assert cmd[cmd.index("--n-drop") + 1] == "1,3"
    assert cmd[cmd.index("--hold-thresh") + 1] == "5,8"
    assert cmd[cmd.index("--n-iters") + 1] == "5"
    assert cmd[cmd.index("--grid-workers") + 1] == "4"
    assert cmd[cmd.index("--output-csv") + 1] == "backtest_results/demo.csv"
    assert cmd[cmd.index("--benchmark") + 1] == "SH000905"
    assert cmd[cmd.index("--deal-price") + 1] == "open"
    assert cmd[cmd.index("--open-cost") + 1] == "0.0007"
    assert cmd[cmd.index("--close-cost") + 1] == "0.0017"
    assert cmd[cmd.index("--min-cost") + 1] == "3.5"
    assert cmd[cmd.index("--slippage-multipliers") + 1] == "0.0,1.0,2.0"
    assert cmd[cmd.index("--markets") + 1] == "csi300,csi1000"


def test_agent_runs_list_and_detail_are_read_only(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    run_dir = runs_dir / "demo_run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "demo_run",
                "objective": "inspect artifacts",
                "generated_at": "2026-05-13T10:00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    (run_dir / "commands.json").write_text(
        json.dumps(
            {
                "run_id": "demo_run",
                "commands": [{"command_id": "cmd_001"}],
                "results": [],
                "feedback_candidates": [{}],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "commands.md").write_text("# commands\n", encoding="utf-8")
    (run_dir / "execution_summary.md").write_text("# summary\n", encoding="utf-8")
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)

    client = TestClient(create_app())
    list_response = client.get("/api/agents/runs")
    detail_response = client.get("/api/agents/runs/demo_run")
    traversal_response = client.get("/api/agents/runs/../secret")

    assert list_response.status_code == 200
    assert list_response.json()[0]["run_id"] == "demo_run"
    assert list_response.json()[0]["status"] == "planned"
    assert list_response.json()[0]["commands_count"] == 1
    assert list_response.json()[0]["feedback_candidates_count"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "planned"
    assert detail_response.json()["artifacts"]["plan.md"] == "# plan\n"
    assert detail_response.json()["artifacts"]["commands.json"]["run_id"] == "demo_run"
    assert traversal_response.status_code in {400, 404, 405}


def test_agent_run_delete_removes_saved_run(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    run_dir = runs_dir / "delete_me"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"run_id": "delete_me"}), encoding="utf-8")
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)

    client = TestClient(create_app())
    response = client.delete("/api/agents/runs/delete_me")
    missing_response = client.get("/api/agents/runs/delete_me")
    traversal_response = client.delete("/api/agents/runs/../secret")

    assert response.status_code == 200
    assert response.json() == {"run_id": "delete_me", "deleted": True}
    assert not run_dir.exists()
    assert missing_response.status_code == 404
    assert traversal_response.status_code in {400, 404, 405}


def test_agent_runs_status_is_derived_from_artifacts(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    feedback_dir = runs_dir / "feedback_run"
    feedback_dir.mkdir(parents=True)
    (feedback_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "feedback_run",
                "objective": "evaluate result",
                "generated_at": "2026-05-13T10:00:00",
            }
        ),
        encoding="utf-8",
    )
    (feedback_dir / "feedback.json").write_text(
        json.dumps({"run_id": "feedback_run", "decision": "reject"}),
        encoding="utf-8",
    )

    approval_dir = runs_dir / "approval_run"
    approval_dir.mkdir()
    (approval_dir / "run.json").write_text(
        json.dumps({"run_id": "approval_run", "objective": "approve commands"}),
        encoding="utf-8",
    )
    (approval_dir / "commands.json").write_text(
        json.dumps(
            {
                "run_id": "approval_run",
                "commands": [{"command_id": "cmd_001", "requires_approval": True}],
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)

    client = TestClient(create_app())

    feedback_response = client.get("/api/agents/runs/feedback_run")
    approval_response = client.get("/api/agents/runs/approval_run")

    assert feedback_response.status_code == 200
    assert feedback_response.json()["status"] == "completed"
    assert feedback_response.json()["feedback_decision"] == "reject"
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "needs_approval"


def test_agent_create_run_writes_plan_and_command_artifacts(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)
    monkeypatch.setattr(agent_service, "PROJECT_ROOT", tmp_path)

    client = TestClient(create_app())
    response = client.post(
        "/api/agents/runs",
        json={
            "objective": "phase5 dashboard smoke",
            "run_id": "phase5_api_smoke",
            "discussion_mode": "meeting",
            "meeting_max_rounds": 3,
            "meeting_max_roles_per_round": 2,
            "use_agent": True,
            "agent_mode": "readonly",
            "agent_max_tasks": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "phase5_api_smoke"
    assert payload["has_plan"] is True
    assert payload["has_commands"] is True
    assert payload["has_approval_template"] is True
    assert (runs_dir / "phase5_api_smoke" / "run.json").exists()
    assert (runs_dir / "phase5_api_smoke" / "commands.json").exists()
    assert (runs_dir / "phase5_api_smoke" / "agent_tasks.json").exists()
    assert (runs_dir / "phase5_api_smoke" / "agent_approval_template.yaml").exists()
    detail = client.get("/api/agents/runs/phase5_api_smoke").json()
    assert detail["discussion_mode"] == "meeting"
    assert detail["discussion_settings"]["max_rounds"] == 3
    assert detail["discussion_settings"]["max_roles_per_round"] == 2
    assert detail["artifacts"]["run.json"]["discussion_mode"] == "meeting"
    assert "agent_tasks.json" in detail["artifacts"]
    assert "agent_approval_template.yaml" in detail["artifacts"]
    assert "discussion_trace.md" in detail["artifacts"]


def test_agent_create_with_llm_returns_background_task(monkeypatch):
    task_calls = []

    def fake_create_agent_run(**kwargs):
        return {"run_id": kwargs["run_id"] or "fake_agent_run", "status": "completed"}

    class FakeTaskManager:
        async def start_sync_task(self, task_type, fn, *args, **kwargs):
            task_calls.append({"task_type": task_type, "args": args, "kwargs": kwargs})
            return "agent_create_task"

    monkeypatch.setattr(agents_router, "create_agent_run", fake_create_agent_run)
    monkeypatch.setattr(agents_router, "get_task_manager", lambda: FakeTaskManager())

    client = TestClient(create_app())
    response = client.post(
        "/api/agents/runs",
        json={"objective": "async llm create", "run_id": "async_agent_run", "use_llm": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"]
    assert payload["run_id"] == "async_agent_run"
    assert task_calls[-1]["task_type"] == "agent_create"
    assert task_calls[-1]["kwargs"]["discussion_mode"] == "sequential"
    assert task_calls[-1]["kwargs"]["meeting_max_rounds"] is None
    assert task_calls[-1]["kwargs"]["meeting_max_roles_per_round"] is None
    assert task_calls[-1]["kwargs"]["use_agent"] is False
    assert task_calls[-1]["kwargs"]["page_key"] == "agents"
    assert task_calls[-1]["kwargs"]["action_key"] == "agents.create"


def test_agent_approval_template_regenerates_from_saved_plan(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)
    monkeypatch.setattr(agent_service, "PROJECT_ROOT", tmp_path)

    client = TestClient(create_app())
    create_response = client.post(
        "/api/agents/runs",
        json={
            "objective": "approval regeneration",
            "run_id": "approval_regen",
            "propose_actions": False,
            "write_approval_template": False,
        },
    )
    assert create_response.status_code == 200

    response = client.post("/api/agents/runs/approval_regen/approval-template")

    assert response.status_code == 200
    assert response.json()["has_approval_template"] is True
    assert (runs_dir / "approval_regen" / "approval_template.yaml").exists()


def test_agent_approval_update_and_execute_safe_task(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)
    monkeypatch.setattr(agent_service, "PROJECT_ROOT", tmp_path)
    task_calls = []

    class FakeTaskManager:
        async def start_sync_task(self, task_type, fn, *args, **kwargs):
            task_calls.append({"task_type": task_type, "args": args, "kwargs": kwargs})
            return "selective_task"

    monkeypatch.setattr(agents_router, "get_task_manager", lambda: FakeTaskManager())

    client = TestClient(create_app())
    create_response = client.post(
        "/api/agents/runs",
        json={"objective": "approval update", "run_id": "approval_update"},
    )
    assert create_response.status_code == 200

    approve_response = client.post(
        "/api/agents/runs/approval_update/approvals/cmd_007",
        json={"approved": True, "approved_by": "test", "reason": "unit approval"},
    )
    assert approve_response.status_code == 200
    assert any(
        item["command_id"] == "cmd_007" and item["approved"] is True
        for item in approve_response.json()["approval_entries"]
    )

    execute_response = client.post(
        "/api/agents/runs/approval_update/execute-safe",
        json={"command_ids": ["cmd_007"]},
    )

    assert execute_response.status_code == 200
    assert execute_response.json()["task_id"]
    assert execute_response.json()["run_id"] == "approval_update"
    assert task_calls[-1]["task_type"] == "agent_execute_safe"
    assert task_calls[-1]["args"] == ("approval_update",)
    assert task_calls[-1]["kwargs"]["command_ids"] == ["cmd_007"]
    assert task_calls[-1]["kwargs"]["skip_successful"] is True
    assert task_calls[-1]["kwargs"]["page_key"] == "agents"
    assert task_calls[-1]["kwargs"]["action_key"] == "agents.execute_safe"

    approved_response = client.post(
        "/api/agents/runs/approval_update/execute-approved",
        json={"include_safe": True, "command_ids": ["cmd_007"]},
    )

    assert approved_response.status_code == 200
    assert task_calls[-1]["task_type"] == "agent_execute_approved"
    assert task_calls[-1]["kwargs"]["include_safe"] is True
    assert task_calls[-1]["kwargs"]["command_ids"] == ["cmd_007"]
    assert task_calls[-1]["kwargs"]["skip_successful"] is True
    assert task_calls[-1]["kwargs"]["page_key"] == "agents"
    assert task_calls[-1]["kwargs"]["action_key"] == "agents.execute_approved"

    feedback_response = client.post(
        "/api/agents/runs/approval_update/feedback/cmd_007",
        json={"control_csv": "control.csv", "rank_metric": "information_ratio"},
    )

    assert feedback_response.status_code == 200
    assert task_calls[-1]["task_type"] == "agent_feedback"
    assert task_calls[-1]["kwargs"]["control_csv"] == "control.csv"
    assert task_calls[-1]["kwargs"]["rank_metric"] == "information_ratio"
    assert task_calls[-1]["kwargs"]["page_key"] == "agents"
    assert task_calls[-1]["kwargs"]["action_key"] == "agents.feedback"


def test_agent_task_approval_update_and_execute(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)
    monkeypatch.setattr(agent_service, "PROJECT_ROOT", tmp_path)
    task_calls = []

    class FakeTaskManager:
        async def start_sync_task(self, task_type, fn, *args, **kwargs):
            task_calls.append({"task_type": task_type, "args": args, "kwargs": kwargs})
            return "agent_task_exec"

    monkeypatch.setattr(agents_router, "get_task_manager", lambda: FakeTaskManager())

    client = TestClient(create_app())
    create_response = client.post(
        "/api/agents/runs",
        json={
            "objective": "agent task approval update",
            "run_id": "agent_task_web",
            "use_agent": True,
            "agent_max_tasks": 1,
        },
    )
    assert create_response.status_code == 200
    detail = client.get("/api/agents/runs/agent_task_web").json()
    task_id = detail["artifacts"]["agent_tasks.json"]["tasks"][0]["task_id"]

    approve_response = client.post(
        f"/api/agents/runs/agent_task_web/agent-task-approvals/{task_id}",
        json={"approved": True, "approved_by": "test", "reason": "unit approval"},
    )
    assert approve_response.status_code == 200
    assert any(
        item["task_id"] == task_id and item["approved"] is True
        for item in approve_response.json()["agent_approval_entries"]
    )

    execute_response = client.post(
        "/api/agents/runs/agent_task_web/execute-agent-tasks",
        json={"task_ids": [task_id]},
    )
    assert execute_response.status_code == 200
    assert task_calls[-1]["task_type"] == "agent_execute_tasks"
    assert task_calls[-1]["args"] == ("agent_task_web",)
    assert task_calls[-1]["kwargs"]["task_ids"] == [task_id]
    assert task_calls[-1]["kwargs"]["skip_successful"] is True
    assert task_calls[-1]["kwargs"]["page_key"] == "agents"
    assert task_calls[-1]["kwargs"]["action_key"] == "agents.execute_tasks"


def test_agent_execute_safe_skips_successful_commands_by_default(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    run_dir = runs_dir / "skip_success"
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)
    monkeypatch.setattr(agent_service, "PROJECT_ROOT", tmp_path)

    proposal = CommandProposal(
        command_id="cmd_done",
        command="./.venv/bin/python -c \"raise SystemExit(7)\"",
        purpose="should not rerun by default",
        source="unit",
        risk_tags=[SAFE_LOCAL_TAG],
        requires_approval=False,
    )
    command_plan = CommandExecutionPlan(
        run_id="skip_success",
        generated_at="2026-05-15T00:00:00",
        policy="unit",
        commands=[proposal],
        results=[
            CommandExecutionResult(
                command_id="cmd_done",
                command=proposal.command,
                skipped=False,
                returncode=0,
            )
        ],
    )
    save_command_plan(command_plan, run_dir)

    result = agent_service.execute_agent_run_safe("skip_success", command_ids=["cmd_done"])
    saved = json.loads((run_dir / "commands.json").read_text(encoding="utf-8"))

    assert result["status"] == "completed"
    assert saved["results"][0]["command_id"] == "cmd_done"
    assert saved["results"][0]["returncode"] == 0


def test_agent_command_selection_distinguishes_empty_from_all():
    command_plan = CommandExecutionPlan(
        run_id="selective_run",
        generated_at="2026-05-14T10:00:00",
        policy="unit",
        commands=[
            CommandProposal(command_id="cmd_001", command="echo one", purpose="one", source="unit"),
            CommandProposal(command_id="cmd_002", command="echo two", purpose="two", source="unit"),
        ],
    )

    all_plan = agent_service._select_commands(command_plan, None)
    empty_plan = agent_service._select_commands(command_plan, [])
    one_plan = agent_service._select_commands(command_plan, ["cmd_002"])

    assert [item.command_id for item in all_plan.commands] == ["cmd_001", "cmd_002"]
    assert empty_plan.commands == []
    assert [item.command_id for item in one_plan.commands] == ["cmd_002"]
    with pytest.raises(Exception, match="Command not found: missing"):
        agent_service._select_commands(command_plan, ["missing"])


def test_agent_feedback_generation_from_ready_candidate(monkeypatch, tmp_path):
    runs_dir = tmp_path / "agent_runs"
    run_dir = runs_dir / "feedback_ready"
    result_dir = tmp_path / "backtest_results" / "agent_runs"
    run_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    result_csv = result_dir / "feedback_ready_same_model.csv"
    result_csv.write_text(
        "market,topk,information_ratio,sharpe,max_drawdown\ncsi300,15,0.5,1.2,-0.1\n",
        encoding="utf-8",
    )
    (run_dir / "commands.json").write_text(
        json.dumps(
            {
                "run_id": "feedback_ready",
                "generated_at": "2026-05-14T10:00:00",
                "commands": [
                    {
                        "command_id": "cmd_001",
                        "command": "./.venv/bin/python run_backtest.py --model-path models/demo.pkl --output-csv backtest_results/agent_runs/feedback_ready_same_model.csv",
                        "purpose": "test feedback",
                        "source": "unit",
                        "risk_tags": ["expensive"],
                        "requires_approval": True,
                        "approval_reason": "unit",
                        "timeout_seconds": 600,
                        "command_sha256": "abc",
                    }
                ],
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_service, "AGENT_RUNS_DIR", runs_dir)
    monkeypatch.setattr(agent_service, "PROJECT_ROOT", tmp_path)

    payload = agent_service.generate_agent_run_feedback("feedback_ready", "cmd_001")

    assert payload["feedback_decision"] == "hold"
    assert (run_dir / "feedback.json").exists()
    assert (run_dir / "feedback.md").exists()


def test_wfv_command_includes_advanced_web_params():
    req = backtest_router.WFVRequest(
        train_universes=["csi300", "csi800"],
        eval_market="csi1000",
        topk=[5, 20],
        n_drop=[1, 5],
        hold_thresh=[5, 10],
        workers=2,
        seeds=True,
        run_id="wfv_demo",
        grid_workers=3,
        robust_weights={"mean_sharpe": 1.0, "sharpe_std": -0.3},
        folds_config="config/walk_forward_folds.yaml",
        train_config="config/model.yaml",
    )

    cmd = backtest_router._build_wfv_cmd(req)

    assert "--seeds" in cmd
    assert cmd[cmd.index("--train-universes") + 1] == "csi300,csi800"
    assert cmd[cmd.index("--eval-market") + 1] == "csi1000"
    assert cmd[cmd.index("--topk") + 1] == "5,20"
    assert cmd[cmd.index("--n-drop") + 1] == "1,5"
    assert cmd[cmd.index("--hold-thresh") + 1] == "5,10"
    assert cmd[cmd.index("--workers") + 1] == "2"
    assert cmd[cmd.index("--run-id") + 1] == "wfv_demo"
    assert cmd[cmd.index("--grid-workers") + 1] == "3"
    assert cmd[cmd.index("--folds-config") + 1] == "config/walk_forward_folds.yaml"
    assert cmd[cmd.index("--train-config") + 1] == "config/model.yaml"
    assert '"sharpe_std": -0.3' in cmd[cmd.index("--robust-weights") + 1]
