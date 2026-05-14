"""Cross-page web console integration tests.

These tests cover the console contract across Data, Models, Backtest, and
Signals: dry-run previews, mocked real execution, task metadata, and request
validation failures.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import types
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.api.app import create_app
from web.api.routers import backtest as backtest_router
from web.api.routers import data as data_router
from web.api.routers import models as models_router
from web.api.services import task_manager as task_manager_module
from web.api.services.task_manager import TaskManager


@pytest.fixture(autouse=True)
def isolated_task_manager(monkeypatch):
    manager = TaskManager()
    monkeypatch.setattr(task_manager_module, "_manager", manager)
    return manager


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _task(client: TestClient, task_id: str) -> dict:
    tasks = client.get("/api/system/tasks").json()
    matches = [task for task in tasks if task["task_id"] == task_id]
    assert len(matches) == 1
    return matches[0]


def _wait_for_terminal_task(client: TestClient, task_id: str) -> dict:
    terminal = {"done", "failed", "cancelled"}
    for _ in range(50):
        task = _task(client, task_id)
        if task["status"] in terminal:
            return task
        time.sleep(0.02)
    return _task(client, task_id)


def _assert_task_metadata(client: TestClient, body: dict, page_key: str, action_key: str) -> None:
    task = _task(client, body["task_id"])
    assert task["page_key"] == page_key
    assert task["action_key"] == action_key


# ---------- Data ----------


def test_data_fetch_dry_run_and_validation(client):
    response = client.post("/api/data/fetch", json={"data_types": ["prices"], "dry_run": True})
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["data_types"] == ["prices"]
    _assert_task_metadata(client, body, "data", "data.fetch")

    invalid = client.post("/api/data/fetch", json={"data_types": []})
    assert invalid.status_code == 422


def test_data_fetch_real_run_mocked(client, monkeypatch):
    monkeypatch.setattr(data_router, "_do_fetch", lambda **_kwargs: {"ok": True})
    response = client.post("/api/data/fetch", json={"data_types": ["prices"], "dry_run": False})

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is False
    assert body["preview"] is None
    task = _wait_for_terminal_task(client, body["task_id"])
    assert task["status"] == "done"
    assert task["result"] == {"ok": True}
    assert task["page_key"] == "data"
    assert task["action_key"] == "data.fetch"


def test_data_purge_dry_run_real_run_and_validation(client, monkeypatch, tmp_path):
    cache_file = tmp_path / "old.csv"
    cache_file.write_text("date,value\n2020-01-01,1\n", encoding="utf-8")
    old_time = time.time() - 2 * 24 * 60 * 60
    os.utime(cache_file, (old_time, old_time))
    monkeypatch.setattr(
        data_router,
        "_get_fetcher_registry",
        lambda: {"prices": ("Fetcher", str(tmp_path), 0)},
    )

    dry = client.delete("/api/data/cache/prices/expired?dry_run=true")
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["preview"]["count"] == 1
    _assert_task_metadata(client, dry_body, "data", "data.purge_expired")

    real = client.delete("/api/data/cache/prices/expired?dry_run=false")
    assert real.status_code == 200
    real_body = real.json()
    assert real_body["dry_run"] is False
    task = _wait_for_terminal_task(client, real_body["task_id"])
    assert task["status"] == "done"
    assert task["result"]["deleted"] == 1
    assert not cache_file.exists()

    invalid = client.delete("/api/data/cache/unknown/expired?dry_run=true")
    assert invalid.status_code == 400


# ---------- Models ----------


def test_models_train_dry_run_and_validation(client):
    response = client.post(
        "/api/models/train",
        json={"model_type": "lgbm", "tag": "ci", "dry_run": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["model_type"] == "lgbm"
    _assert_task_metadata(client, body, "models", "models.train")

    invalid = client.post("/api/models/train", json={})
    assert invalid.status_code == 422


def test_models_train_real_run_mocked(client, monkeypatch):
    model_path = "models/lgbm_ci_20260514_120000.pkl"
    monkeypatch.setattr(models_router, "_train_model", lambda _req: {"ok": True, "result_paths": [model_path]})
    response = client.post(
        "/api/models/train",
        json={"model_type": "lgbm", "tag": "ci", "dry_run": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is False
    task = _wait_for_terminal_task(client, body["task_id"])
    assert task["status"] == "done"
    assert task["result"] == {"ok": True, "result_paths": [model_path]}
    assert task["result_paths"] == [model_path]
    assert task["page_key"] == "models"
    assert task["action_key"] == "models.train"


def test_models_delete_dry_run_real_run_and_validation(client, monkeypatch, tmp_path):
    monkeypatch.setattr(models_router, "MODELS_DIR", tmp_path)
    model_file = tmp_path / "demo.pkl"
    meta_file = tmp_path / "demo_meta.json"
    importance_file = tmp_path / "demo_feature_importance.json"
    model_file.write_bytes(b"model")
    meta_file.write_text("{}", encoding="utf-8")
    importance_file.write_text("{}", encoding="utf-8")

    dry = client.delete("/api/models/demo.pkl?dry_run=true")
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["preview"]["count"] == 3
    _assert_task_metadata(client, dry_body, "models", "models.delete")

    real = client.delete("/api/models/demo.pkl?dry_run=false")
    assert real.status_code == 200
    real_body = real.json()
    task = _wait_for_terminal_task(client, real_body["task_id"])
    assert task["status"] == "done"
    assert sorted(Path(path).name for path in task["result"]["removed"]) == [
        "demo.pkl",
        "demo_feature_importance.json",
        "demo_meta.json",
    ]
    assert not model_file.exists()

    invalid = client.delete("/api/models/missing.pkl?dry_run=true")
    assert invalid.status_code == 404


# ---------- Backtest ----------


def test_backtest_grid_dry_run_real_run_and_validation(client, monkeypatch):
    captured = {}

    def _fake_grid_run(argv, **_kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    payload = {
        "model_path": "models/dummy.pkl",
        "topk_list": [5],
        "n_drop_list": [1],
        "hold_thresh_list": [5],
    }
    dry = client.post("/api/backtest/grid", json={**payload, "dry_run": True})
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["preview"]["candidate_count"] == 1
    _assert_task_metadata(client, dry_body, "backtest", "backtest.grid")

    monkeypatch.setattr(subprocess, "run", _fake_grid_run)
    real = client.post(
        "/api/backtest/grid",
        json={
            **payload,
            "benchmark": "SH000905",
            "deal_price": "open",
            "open_cost": 0.0007,
            "close_cost": 0.0017,
            "min_cost": 3.5,
            "dry_run": False,
        },
    )
    assert real.status_code == 200
    task = _wait_for_terminal_task(client, real.json()["task_id"])
    assert task["status"] == "done"
    assert task["action_key"] == "backtest.grid"
    assert task["result_paths"]
    assert task["result_paths"][0].endswith(".csv")
    assert captured["argv"][captured["argv"].index("--benchmark") + 1] == "SH000905"
    assert captured["argv"][captured["argv"].index("--deal-price") + 1] == "open"
    assert captured["argv"][captured["argv"].index("--open-cost") + 1] == "0.0007"
    assert captured["argv"][captured["argv"].index("--close-cost") + 1] == "0.0017"
    assert captured["argv"][captured["argv"].index("--min-cost") + 1] == "3.5"

    invalid = client.post("/api/backtest/grid", json={"model_path": ""})
    assert invalid.status_code == 422

    invalid_empty_list = client.post(
        "/api/backtest/grid",
        json={**payload, "topk_list": []},
    )
    assert invalid_empty_list.status_code == 422

    unsupported_real = client.post(
        "/api/backtest/grid",
        json={**payload, "slippage": 0.01, "dry_run": False},
    )
    assert unsupported_real.status_code == 422


def test_backtest_wfv_dry_run_real_run_and_validation(client, monkeypatch):
    payload = {
        "train_universes": ["csi300"],
        "eval_market": "csi300",
        "topk_list": [5],
        "n_drop_list": [1],
        "hold_thresh_list": [5],
        "rank_metric": "information_ratio",
    }
    dry = client.post("/api/backtest/walk-forward", json={**payload, "dry_run": True})
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["preview"]["rank_metric"] == "information_ratio"
    _assert_task_metadata(client, dry_body, "backtest", "backtest.walk_forward")

    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "", ""))
    real = client.post("/api/backtest/walk-forward", json={**payload, "dry_run": False})
    assert real.status_code == 200
    task = _wait_for_terminal_task(client, real.json()["task_id"])
    assert task["status"] == "done"
    assert task["action_key"] == "backtest.walk_forward"
    assert any(path.endswith("walk_forward_summary.csv") for path in task["result_paths"])

    invalid = client.post("/api/backtest/walk-forward", json={**payload, "rank_metric": "sharpe"})
    assert invalid.status_code == 400

    invalid_empty_list = client.post(
        "/api/backtest/walk-forward",
        json={**payload, "train_universes": []},
    )
    assert invalid_empty_list.status_code == 422

    unsupported_real = client.post(
        "/api/backtest/walk-forward",
        json={**payload, "rolling_window_days": 126, "dry_run": False},
    )
    assert unsupported_real.status_code == 422


def test_backtest_compare_dry_run_real_run_and_validation(client, monkeypatch):
    payload = {"result_files": ["a.csv", "b.csv"]}
    dry = client.post("/api/backtest/compare", json={**payload, "dry_run": True})
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["preview"]["file_count"] == 2
    _assert_task_metadata(client, dry_body, "backtest", "backtest.compare")

    monkeypatch.setattr(backtest_router, "compare_runs", lambda _files: {"rows": []})
    real = client.post("/api/backtest/compare", json={**payload, "dry_run": False})
    assert real.status_code == 200
    task = _wait_for_terminal_task(client, real.json()["task_id"])
    assert task["status"] == "done"
    assert task["result"]["result"] == {"rows": []}

    invalid = client.post("/api/backtest/compare", json={"result_files": ["a.csv"]})
    assert invalid.status_code == 422

    invalid_blank = client.post("/api/backtest/compare", json={"result_files": ["a.csv", ""]})
    assert invalid_blank.status_code == 422


# ---------- Signals ----------


def test_signals_generate_dry_run_real_run_and_validation(client, monkeypatch, tmp_path):
    dry = client.post("/api/signals/generate", json={"model_path": "models/dummy.pkl", "dry_run": True})
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["preview"]["model_path"] == "models/dummy.pkl"
    _assert_task_metadata(client, dry_body, "signals", "signals.generate")

    run_daily = types.ModuleType("quant_ex.run_daily")
    signal_path = tmp_path / f"signal_{date.today().isoformat()}.txt"
    run_daily.main = lambda **_kwargs: signal_path
    monkeypatch.setitem(sys.modules, "quant_ex.run_daily", run_daily)
    real = client.post("/api/signals/generate", json={"model_path": "models/dummy.pkl", "dry_run": False})
    assert real.status_code == 200
    task = _wait_for_terminal_task(client, real.json()["task_id"])
    assert task["status"] == "done"
    assert task["action_key"] == "signals.generate"
    assert task["result_paths"] == [str(signal_path)]

    invalid = client.post("/api/signals/generate", json={"model_path": ""})
    assert invalid.status_code == 422


def test_signals_rebalance_dry_run_real_run_and_validation(client, monkeypatch, tmp_path):
    payload = {"skip_update": True}
    cache_dir = tmp_path / "rebalance_cache"
    monkeypatch.setattr(
        "web.api.routers.signals.get_config",
        lambda: {"daily_rebalance": {"cache_dir": str(cache_dir)}},
    )
    dry = client.post("/api/signals/rebalance", json={**payload, "dry_run": True})
    assert dry.status_code == 200
    dry_body = dry.json()
    assert "diff" in dry_body["preview"]
    _assert_task_metadata(client, dry_body, "signals", "signals.rebalance")

    def _fake_rebalance_run(*_args, **_kwargs):
        cache_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        (cache_dir / f"rebalance_{today}.json").write_text("{}", encoding="utf-8")
        (cache_dir / "latest.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([], 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", _fake_rebalance_run)
    real = client.post(
        "/api/signals/rebalance",
        json={**payload, "dry_run": False, "confirm_send": True},
    )
    assert real.status_code == 200
    task = _wait_for_terminal_task(client, real.json()["task_id"])
    assert task["status"] == "done"
    assert task["action_key"] == "signals.rebalance"
    assert {Path(path).name for path in task["result_paths"]} == {
        f"rebalance_{date.today().isoformat()}.json",
        "latest.json",
    }

    invalid = client.post("/api/signals/rebalance", json={**payload, "dry_run": False, "confirm_send": False})
    assert invalid.status_code == 400


def test_signals_notify_test_dry_run_real_run_and_validation(client, monkeypatch):
    payload = {"channel": "bark", "message": "hello"}
    dry = client.post("/api/signals/notify-test", json={**payload, "dry_run": True})
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["dry_run"] is True
    _assert_task_metadata(client, dry_body, "signals", "signals.notify_test")

    notify_pkg = types.ModuleType("quant_ex.notify")
    pusher_mod = types.ModuleType("quant_ex.notify.pusher")

    class FakeNotificationPusher:
        def __init__(self, _config):
            pass

        def send(self, title: str, content: str) -> dict[str, bool]:
            return {"bark": bool(title and content)}

    pusher_mod.NotificationPusher = FakeNotificationPusher
    monkeypatch.setitem(sys.modules, "quant_ex.notify", notify_pkg)
    monkeypatch.setitem(sys.modules, "quant_ex.notify.pusher", pusher_mod)

    real = client.post(
        "/api/signals/notify-test",
        json={**payload, "dry_run": False, "confirm_send": True},
    )
    assert real.status_code == 200
    task = _wait_for_terminal_task(client, real.json()["task_id"])
    assert task["status"] == "done"
    assert task["action_key"] == "signals.notify_test"

    invalid = client.post(
        "/api/signals/notify-test",
        json={**payload, "dry_run": False, "confirm_send": False},
    )
    assert invalid.status_code == 400
