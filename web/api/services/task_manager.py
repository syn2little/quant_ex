"""Background task orchestrator with SSE event streaming."""
from __future__ import annotations

import asyncio
import logging
import uuid
import traceback
import json
from functools import partial
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskState:
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    result: Optional[Any] = None
    error: Optional[str] = None


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, TaskState] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._bg_tasks: dict[str, asyncio.Task] = {}
        self._list_call_count = 0

    async def start_task(
        self,
        task_type: str,
        coro: Awaitable,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        state = TaskState(task_id=task_id, task_type=task_type)
        self._tasks[task_id] = state
        self._queues[task_id] = asyncio.Queue()

        bg = asyncio.create_task(self._run(task_id, coro))
        self._bg_tasks[task_id] = bg
        return task_id

    async def start_sync_task(
        self,
        task_type: str,
        fn: Callable,
        *args,
        **kwargs,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        state = TaskState(task_id=task_id, task_type=task_type)
        self._tasks[task_id] = state
        self._queues[task_id] = asyncio.Queue()

        async def _wrapper():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

        bg = asyncio.create_task(self._run(task_id, _wrapper()))
        self._bg_tasks[task_id] = bg
        return task_id

    async def _run(self, task_id: str, coro: Awaitable):
        state = self._tasks[task_id]
        state.status = TaskStatus.RUNNING
        try:
            result = await coro
            state.status = TaskStatus.DONE
            state.result = result
            try:
                json.dumps(result)
                event_result = result
            except TypeError:
                event_result = str(result)[:500]
            await self._queues[task_id].put({"type": "done", "data": {"result": event_result}})
        except asyncio.CancelledError:
            state.status = TaskStatus.CANCELLED
            await self._queues[task_id].put({"type": "done", "data": {"status": "cancelled"}})
        except Exception as exc:
            state.status = TaskStatus.FAILED
            state.error = str(exc)
            logger.exception(f"Task {task_id} failed")
            await self._queues[task_id].put({"type": "error", "data": {"message": str(exc), "traceback": traceback.format_exc()}})
        finally:
            try:
                await self._queues[task_id].put(None)  # sentinel
            except Exception:
                pass

    def emit(self, task_id: str, event_type: str, data: dict):
        if task_id in self._queues:
            self._queues[task_id].put_nowait({"type": event_type, "data": data})

    async def stream_events(self, task_id: str):
        if task_id not in self._queues:
            yield {"type": "error", "data": {"message": f"Task {task_id} not found"}}
            return
        q = self._queues[task_id]
        while True:
            event = await q.get()
            if event is None:
                break
            yield event

    def get_state(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskState]:
        self._list_call_count += 1
        if self._list_call_count % 10 == 0:
            self._cleanup()
        return list(self._tasks.values())

    async def cancel(self, task_id: str) -> bool:
        bg = self._bg_tasks.get(task_id)
        if bg and not bg.done():
            bg.cancel()
            state = self._tasks.get(task_id)
            if state:
                state.status = TaskStatus.CANCELLED
            return True
        return False

    def _cleanup(self, max_age_hours: int = 24):
        """Remove DONE/FAILED/CANCELLED tasks older than max_age_hours."""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_remove = []
        for tid, state in self._tasks.items():
            if state.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                try:
                    created = datetime.fromisoformat(state.created_at)
                    if created < cutoff:
                        to_remove.append(tid)
                except (ValueError, TypeError):
                    pass
        for tid in to_remove:
            self._tasks.pop(tid, None)
            self._queues.pop(tid, None)
            self._bg_tasks.pop(tid, None)
        if to_remove:
            logger.info("Cleaned up %d old tasks", len(to_remove))


_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager
