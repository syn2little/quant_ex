"""Phase 0 contract regression tests for the dashboard console upgrade."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from web.api.app import create_app
from web.api.services.task_manager import TaskState


FRONTEND_SRC = Path(__file__).resolve().parents[1] / "web" / "frontend" / "src"


def test_task_state_has_console_fields():
    state = TaskState(task_id="abc", task_type="model_train")

    assert hasattr(state, "page_key")
    assert hasattr(state, "action_key")
    assert hasattr(state, "result_paths")
    assert state.page_key is None
    assert state.action_key is None
    assert state.result_paths == []


def test_console_layout_translates_title_tabs_and_drawer_label():
    source = (FRONTEND_SRC / "components" / "console" / "ConsolePageLayout.tsx").read_text(encoding="utf-8")

    assert "useTranslation" in source
    assert "{t(titleKey)}" in source
    assert '{t("console.tasks.drawerTitle")}' in source
    assert "{t(tab.labelKey)}" in source


def test_console_dialog_and_drawer_translate_labels_and_show_details():
    dialog = (FRONTEND_SRC / "components" / "console" / "ConfirmDialog.tsx").read_text(encoding="utf-8")
    drawer = (FRONTEND_SRC / "components" / "console" / "TaskDrawer.tsx").read_text(encoding="utf-8")

    assert "{t(titleKey)}" in dialog
    assert '{t("console.common.cancel")}' in dialog
    assert "{t(confirmLabelKey)}" in dialog
    assert 'data-testid="task-drawer-detail"' in drawer
    assert "subscribeTask" in drawer
    assert 't("console.tasks.events")' in drawer


def test_data_fetch_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/data/fetch", json={
        "data_types": ["prices"],
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is True
    assert body["preview"] is not None


def test_data_fetch_returns_unified_envelope_for_real_run(monkeypatch):
    client = TestClient(create_app())

    monkeypatch.setattr("web.api.routers.data._do_fetch", lambda **kwargs: {"ok": True})

    response = client.post("/api/data/fetch", json={
        "data_types": ["prices"],
        "dry_run": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is False
    assert body["preview"] is None


def test_models_train_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/models/train", json={
        "model_type": "lgbm",
        "tag": "ci_test",
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is True
    assert body["preview"] is not None
    assert "final_market" in body["preview"]


def test_models_delete_dry_run_lists_files():
    client = TestClient(create_app())

    response = client.delete("/api/models/nonexistent.pkl?dry_run=true")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        body = response.json()
        assert body["dry_run"] is True
        assert "files" in body["preview"]


def test_backtest_grid_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/backtest/grid", json={
        "model_path": "models/dummy.pkl",
        "topk_list": [5, 10],
        "n_drop_list": [1, 3],
        "hold_thresh_list": [5, 8],
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["candidate_count"] == 2 * 2 * 2


def test_backtest_wfv_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/backtest/walk-forward", json={
        "train_universes": ["csi300", "csi1000"],
        "eval_market": "csi300",
        "topk_list": [5],
        "n_drop_list": [1],
        "hold_thresh_list": [5],
        "rank_metric": "information_ratio",
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["rank_metric"] == "information_ratio"


def test_signals_generate_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())
    response = client.post("/api/signals/generate", json={
        "model_path": "models/dummy.pkl",
        "dry_run": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"] is not None


def test_signals_rebalance_dry_run_preview_includes_diff():
    client = TestClient(create_app())
    response = client.post("/api/signals/rebalance", json={
        "config": "config/daily_csi1000.yaml",
        "dry_run": True,
        "skip_update": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert "diff" in body["preview"]


def test_factors_evaluate_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())
    response = client.post("/api/factors/evaluate", json={
        "factor": "technical",
        "dry_run": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is True
