import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from web.api.deps import get_config
from web.api.services.factor_service import compute_factor_values, compute_ic_analysis
from web.api.services.task_manager import get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class EvaluateRequest(BaseModel):
    name: Optional[str] = None
    factor: Optional[str] = None
    dry_run: bool = True


class MineRequest(BaseModel):
    min_ic: float = 0.03
    min_icir: float = 0.4
    top_n: int = 30
    dry_run: bool = True


@router.get("")
async def list_factors():
    from quant_ex.features.base import FactorRegistry
    try:
        from quant_ex.models import trainer  # noqa: F401 — triggers model registration
    except Exception as exc:
        logger.warning("Failed to import trainer (model registration may be incomplete): %s", exc)
    factors = []
    for name in FactorRegistry.list():
        cls = FactorRegistry.get(name)
        factors.append({"name": name, "class": cls.__name__})
    return factors


@router.get("/library")
async def factor_library():
    from quant_ex.features.base import FactorRegistry
    config = get_config()
    try:
        from quant_ex.models import trainer  # noqa: F401
    except Exception as exc:
        logger.warning("Failed to import trainer: %s", exc)

    enabled = set()
    for fc in config.get("model", {}).get("features", {}).get("factors", []):
        enabled.add(fc.get("name"))

    result = []
    for name in FactorRegistry.list():
        cls = FactorRegistry.get(name)
        result.append({"name": name, "class": cls.__name__, "enabled": name in enabled})
    return result


@router.post("/evaluate")
async def evaluate_factor(req: EvaluateRequest):
    tm = get_task_manager()
    factor_name = req.factor or req.name
    if not factor_name:
        raise HTTPException(status_code=422, detail="factor is required")

    if req.dry_run:
        preview = {
            "factor": factor_name,
            "estimated_minutes": 3,
            "writes_files": False,
        }
        task_id = await tm.start_sync_task(
            "factor_eval_dry_run",
            lambda: preview,
            page_key="factors",
            action_key="factors.evaluate",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _eval():
        return {
            "factor": factor_name,
            "message": "evaluation not yet implemented in web mode",
            "result_paths": [],
        }

    task_id = await tm.start_sync_task(
        "factor_eval",
        _eval,
        page_key="factors",
        action_key="factors.evaluate",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.post("/mine")
async def mine_factors(req: MineRequest):
    tm = get_task_manager()
    if req.dry_run:
        preview = {
            "min_ic": req.min_ic,
            "min_icir": req.min_icir,
            "top_n": req.top_n,
            "estimated_minutes": 10,
            "writes_files": False,
        }
        task_id = await tm.start_sync_task(
            "factor_mine_dry_run",
            lambda: preview,
            page_key="factors",
            action_key="factors.mine",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _mine():
        import subprocess, sys
        cmd = [sys.executable, "run_factor_mining.py",
               "--min-ic", str(req.min_ic),
               "--min-icir", str(req.min_icir),
               "--top-n", str(req.top_n)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Factor mining failed (exit {result.returncode}): {result.stderr[-500:]}")
        return {"status": "completed", "result_paths": []}

    task_id = await tm.start_sync_task(
        "factor_mine",
        _mine,
        page_key="factors",
        action_key="factors.mine",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.get("/values")
async def factor_values(
    factors: str = Query(..., description="Comma-separated factor names"),
    symbols: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    factor_list = [f.strip() for f in factors.split(",")]
    symbol_list = [s.strip() for s in symbols.split(",")] if symbols else None
    return compute_factor_values(factor_list, symbol_list, start, end)


@router.get("/ic-analysis")
async def ic_analysis(
    factor: str = Query(...),
    horizon: int = Query(5, ge=1, le=60),
    window: int = Query(20, ge=5, le=120),
):
    return compute_ic_analysis(factor, horizon, window)


@router.get("/heatmap")
async def factor_heatmap(
    factors: str = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    factor_list = [f.strip() for f in factors.split(",")]
    result = compute_factor_values(factor_list, symbols=None, start=start, end=end)
    if not result["data"]:
        return {"factors": factor_list, "matrix": []}
    df = pd.DataFrame(result["data"])
    numeric_cols = [c for c in df.columns if c not in ("symbol", "date", "instrument")]
    if len(numeric_cols) < 2:
        return {"factors": factor_list, "matrix": [[1.0]]}
    corr = df[numeric_cols].corr().fillna(0).values.tolist()
    corr = [[round(float(v), 4) for v in row] for row in corr]
    return {"factors": numeric_cols, "matrix": corr}


def _safe_path(base_dir, filename: str):
    """Prevent path traversal — reject filenames containing '..' or starting with '/'."""
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid filename")
    return base_dir / filename
