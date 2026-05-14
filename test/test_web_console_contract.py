"""Phase 0 contract regression tests for the dashboard console upgrade."""
from __future__ import annotations

from web.api.services.task_manager import TaskState


def test_task_state_has_console_fields():
    state = TaskState(task_id="abc", task_type="model_train")

    assert hasattr(state, "page_key")
    assert hasattr(state, "action_key")
    assert hasattr(state, "result_paths")
    assert state.page_key is None
    assert state.action_key is None
    assert state.result_paths == []
