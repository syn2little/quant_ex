import json
import sys
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from web.api.services.task_manager import TaskState, get_task_manager
from web.api.deps import CACHE_DIR, MODELS_DIR, LOGS_DIR, get_config

router = APIRouter()


def _serialize_task(state: TaskState) -> dict:
    return {
        "task_id": state.task_id,
        "task_type": state.task_type,
        "status": state.status.value,
        "created_at": state.created_at,
        "result": state.result,
        "error": state.error,
        "page_key": state.page_key,
        "action_key": state.action_key,
        "result_paths": state.result_paths,
    }


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/runtime")
async def runtime_info():
    config = get_config()
    cache_types = {}
    if CACHE_DIR.exists():
        for d in sorted(CACHE_DIR.iterdir()):
            if d.is_dir():
                files = list(d.glob("*.csv"))
                total_size = sum(f.stat().st_size for f in files) if files else 0
                latest = max((f.stat().st_mtime for f in files), default=0)
                cache_types[d.name] = {
                    "file_count": len(files),
                    "total_size_mb": round(total_size / 1024 / 1024, 2),
                    "latest": datetime.fromtimestamp(latest).isoformat() if latest else None,
                }

    return {
        "python_version": sys.version,
        "qlib_data_path": config.get("qlib", {}).get("provider_uri", ""),
        "models_count": len(list(MODELS_DIR.glob("*.pkl"))) if MODELS_DIR.exists() else 0,
        "cache_types": cache_types,
    }


@router.get("/tasks")
async def list_tasks():
    tm = get_task_manager()
    return [_serialize_task(t) for t in tm.list_tasks()]


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    tm = get_task_manager()
    state = tm.get_state(task_id)
    if not state:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'data': {'message': 'Task not found'}})}\n\n"]),
            media_type="text/event-stream",
        )

    async def event_generator():
        async for event in tm.stream_events(task_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    tm = get_task_manager()
    cancelled = await tm.cancel(task_id)
    return {"cancelled": cancelled}


@router.get("/logs")
async def get_logs(lines: int = Query(200, ge=1, le=2000), level: Optional[str] = None):
    if not LOGS_DIR.exists():
        return {"lines": [], "file": None}
    log_files = sorted(LOGS_DIR.glob("quant_ex_*.log"), reverse=True)
    if not log_files:
        return {"lines": [], "file": None}
    latest = log_files[0]
    all_lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
    filtered = all_lines[-lines:]
    if level:
        level_upper = level.upper()
        filtered = [l for l in filtered if level_upper in l]
    return {"lines": filtered, "file": latest.name}
