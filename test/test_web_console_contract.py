"""Phase 0 contract regression tests for the dashboard console upgrade."""
from __future__ import annotations

from fastapi.testclient import TestClient

from web.api.app import create_app
from web.api.services.task_manager import TaskState


def test_task_state_has_console_fields():
    state = TaskState(task_id="abc", task_type="model_train")

    assert hasattr(state, "page_key")
    assert hasattr(state, "action_key")
    assert hasattr(state, "result_paths")
    assert state.page_key is None
    assert state.action_key is None
    assert state.result_paths == []


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
