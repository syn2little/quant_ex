"""HTTP-driven e2e coverage for dashboard console task wiring.

The test expects the built FastAPI dashboard to be running. Start it with:

    ./.venv/bin/python -m uvicorn web.api.app:app --host 127.0.0.1 --port 8000

This intentionally avoids adding a browser automation dependency while still
checking the deployed SPA routes and the submit -> task history contract.
"""
from __future__ import annotations

import os
import time

import pytest
import requests


SERVER_URL = os.environ.get("WEB_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.fixture(scope="module")
def server_url() -> str:
    for _ in range(30):
        try:
            response = requests.get(f"{SERVER_URL}/api/system/health", timeout=1)
            if response.status_code == 200:
                return SERVER_URL
        except requests.RequestException:
            time.sleep(0.5)
    pytest.skip(f"Web server not running at {SERVER_URL}")


@pytest.mark.parametrize("path", ["/data-explorer", "/models", "/backtest", "/signals"])
def test_console_spa_routes_render(server_url: str, path: str):
    response = requests.get(f"{server_url}{path}", timeout=5)

    assert response.status_code == 200
    assert '<div id="root">' in response.text


@pytest.mark.parametrize(
    ("page_key", "action_key", "endpoint", "payload"),
    [
        ("data", "data.fetch", "/api/data/fetch", {"data_types": ["prices"], "dry_run": True}),
        (
            "models",
            "models.train",
            "/api/models/train",
            {"model_type": "lgbm", "tag": "e2e", "dry_run": True},
        ),
        (
            "backtest",
            "backtest.grid",
            "/api/backtest/grid",
            {
                "model_path": "models/dummy.pkl",
                "topk_list": [5],
                "n_drop_list": [1],
                "hold_thresh_list": [5],
                "dry_run": True,
            },
        ),
        (
            "signals",
            "signals.generate",
            "/api/signals/generate",
            {"model_path": "models/dummy.pkl", "dry_run": True},
        ),
    ],
)
def test_dry_run_submit_creates_history_task(
    server_url: str,
    page_key: str,
    action_key: str,
    endpoint: str,
    payload: dict,
):
    response = requests.post(f"{server_url}{endpoint}", json=payload, timeout=10)

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"] is not None
    task_id = body["task_id"]

    tasks_response = requests.get(f"{server_url}/api/system/tasks", timeout=5)
    assert tasks_response.status_code == 200
    matching = [task for task in tasks_response.json() if task["task_id"] == task_id]
    assert len(matching) == 1
    assert matching[0]["page_key"] == page_key
    assert matching[0]["action_key"] == action_key
