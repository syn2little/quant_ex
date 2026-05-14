import logging
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from web.api.deps import get_config, BACKTEST_RESULTS_DIR
from web.api.services.task_manager import get_task_manager
from web.api.services.chart_service import parse_equity_curve, parse_metrics, parse_drawdown, compare_runs
from web.api.routers.system import stream_task

logger = logging.getLogger(__name__)

router = APIRouter()


def _safe_path(base_dir: Path, filename: str) -> Path:
    """Prevent path traversal — reject filenames containing '..' or starting with '/'."""
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid filename")
    return base_dir / filename


class GridSearchRequest(BaseModel):
    model_path: str
    topk: list[int] = [5, 10, 15, 20]
    topk_list: Optional[list[int]] = None
    n_drop: list[int] = [1, 3, 5]
    n_drop_list: Optional[list[int]] = None
    hold_thresh: list[int] = [3, 5, 10]
    hold_thresh_list: Optional[list[int]] = None
    start: Optional[str] = None
    start_date: Optional[str] = None
    end: Optional[str] = None
    end_date: Optional[str] = None
    market: str = "csi300"
    benchmark: Optional[str] = None
    deal_price: str = "close"
    open_cost: float = 0.0005
    close_cost: float = 0.0015
    min_cost: float = 5.0
    slippage: float = 0.0
    multi_seed: bool = False
    optimize: bool = False
    n_iters: int = 3
    grid_workers: int = 1
    output_csv: Optional[str] = None
    slippage_multipliers: Optional[list[float]] = None
    slippage_sensitivity: bool = False
    markets: Optional[list[str]] = None
    explore_markets: bool = False
    dry_run: bool = True

    @field_validator("model_path", "market", "benchmark", "deal_price", "start", "start_date", "end", "end_date", "output_csv")
    @classmethod
    def strings_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("string fields must not be blank")
        return value

    @field_validator("topk", "topk_list", "n_drop", "n_drop_list", "hold_thresh", "hold_thresh_list", "slippage_multipliers", "markets")
    @classmethod
    def lists_must_not_be_empty_when_provided(cls, value):
        if value is not None and len(value) == 0:
            raise ValueError("list fields must not be empty")
        return value


def _grid_topk(req: GridSearchRequest) -> list[int]:
    return req.topk_list or req.topk


def _grid_n_drop(req: GridSearchRequest) -> list[int]:
    return req.n_drop_list or req.n_drop


def _grid_hold_thresh(req: GridSearchRequest) -> list[int]:
    return req.hold_thresh_list or req.hold_thresh


def _build_grid_cmd(req: GridSearchRequest) -> list[str]:
    argv = [
        sys.executable,
        "run_backtest.py",
        "--model-path",
        req.model_path,
        "--topk",
        ",".join(str(x) for x in _grid_topk(req)),
        "--n-drop",
        ",".join(str(x) for x in _grid_n_drop(req)),
        "--hold-thresh",
        ",".join(str(x) for x in _grid_hold_thresh(req)),
        "--market",
        req.market,
    ]
    start = req.start_date or req.start
    end = req.end_date or req.end
    if start:
        argv.extend(["--start", start])
    if end:
        argv.extend(["--end", end])
    if req.multi_seed:
        argv.append("--seeds")
    if req.optimize:
        argv.append("--optimize")
    if req.n_iters != 3:
        argv.extend(["--n-iters", str(req.n_iters)])
    if req.grid_workers != 1:
        argv.extend(["--grid-workers", str(req.grid_workers)])
    if req.output_csv:
        argv.extend(["--output-csv", req.output_csv])
    if req.slippage_sensitivity:
        argv.append("--slippage-sensitivity")
    if req.slippage_multipliers:
        argv.extend(["--slippage-multipliers", ",".join(str(x) for x in req.slippage_multipliers)])
    if req.markets:
        argv.extend(["--markets", ",".join(req.markets)])
    if req.explore_markets:
        argv.append("--explore-markets")
    return argv


@router.post("/grid")
async def start_grid_search(req: GridSearchRequest):
    tm = get_task_manager()
    topk = _grid_topk(req)
    n_drop = _grid_n_drop(req)
    hold_thresh = _grid_hold_thresh(req)
    candidate_count = len(topk) * len(n_drop) * len(hold_thresh)
    if req.dry_run:
        preview = {
            "model_path": req.model_path,
            "market": req.market,
            "benchmark": req.benchmark,
            "candidate_count": candidate_count,
            "estimated_minutes": round(candidate_count * 0.5, 1),
            "deal_price": req.deal_price,
            "rank_metric": "information_ratio",
            "warning": "candidate_count_gt_200" if candidate_count > 200 else None,
        }
        task_id = await tm.start_sync_task(
            "grid_search_dry_run",
            lambda: preview,
            page_key="backtest",
            action_key="backtest.grid",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _grid():
        import subprocess
        argv = _build_grid_cmd(req)
        result = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Grid search failed (exit {result.returncode}): {result.stderr[-500:]}")
        result_paths = [req.output_csv] if req.output_csv else []
        return {"status": "completed", "result_paths": result_paths}

    task_id = await tm.start_sync_task(
        "grid_search",
        _grid,
        page_key="backtest",
        action_key="backtest.grid",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.get("/grid/{task_id}/stream")
async def stream_grid(task_id: str):
    return await stream_task(task_id)


@router.get("/results")
async def list_results():
    if not BACKTEST_RESULTS_DIR.exists():
        return []
    results = []
    for f in sorted(BACKTEST_RESULTS_DIR.glob("*.csv"), reverse=True):
        results.append({
            "filename": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return results


@router.get("/results/{filename}")
async def get_result(filename: str):
    import pandas as pd
    path = _safe_path(BACKTEST_RESULTS_DIR, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    df = pd.read_csv(path)
    return {"columns": list(df.columns), "rows": df.to_dict(orient="records")[:200]}


@router.get("/charts/{filename}")
async def get_chart(filename: str):
    path = _safe_path(BACKTEST_RESULTS_DIR, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chart file not found")
    return FileResponse(str(path), media_type="image/png")


class WFVRequest(BaseModel):
    train_universes: list[str] = ["csi300"]
    eval_market: str = "csi300"
    topk: list[int] = [5, 15, 20]
    topk_list: Optional[list[int]] = None
    n_drop: list[int] = [1, 3]
    n_drop_list: Optional[list[int]] = None
    hold_thresh: list[int] = [5, 8, 10]
    hold_thresh_list: Optional[list[int]] = None
    rolling_window_days: int = 252
    step_days: int = 63
    rank_metric: str = "information_ratio"
    workers: int = 1
    seeds: bool = False
    run_id: Optional[str] = None
    grid_workers: int = 1
    robust_weights: Optional[dict] = None
    folds_config: Optional[str] = None
    train_config: Optional[str] = None
    dry_run: bool = True

    @field_validator("eval_market", "rank_metric", "run_id", "folds_config", "train_config")
    @classmethod
    def strings_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("string fields must not be blank")
        return value

    @field_validator("train_universes", "topk", "topk_list", "n_drop", "n_drop_list", "hold_thresh", "hold_thresh_list")
    @classmethod
    def lists_must_not_be_empty(cls, value):
        if value is not None and len(value) == 0:
            raise ValueError("list fields must not be empty")
        return value


def _wfv_topk(req: WFVRequest) -> list[int]:
    return req.topk_list or req.topk


def _wfv_n_drop(req: WFVRequest) -> list[int]:
    return req.n_drop_list or req.n_drop


def _wfv_hold_thresh(req: WFVRequest) -> list[int]:
    return req.hold_thresh_list or req.hold_thresh


def _build_wfv_cmd(req: WFVRequest) -> list[str]:
    cmd = [
        sys.executable,
        "run_walk_forward_validation.py",
        "--train-universes",
        ",".join(req.train_universes),
        "--eval-market",
        req.eval_market,
        "--topk",
        ",".join(str(x) for x in _wfv_topk(req)),
        "--n-drop",
        ",".join(str(x) for x in _wfv_n_drop(req)),
        "--hold-thresh",
        ",".join(str(x) for x in _wfv_hold_thresh(req)),
        "--workers",
        str(req.workers),
    ]
    if req.seeds:
        cmd.append("--seeds")
    if req.run_id:
        cmd.extend(["--run-id", req.run_id])
    if req.grid_workers != 1:
        cmd.extend(["--grid-workers", str(req.grid_workers)])
    if req.robust_weights:
        cmd.extend(["--robust-weights", json.dumps(req.robust_weights)])
    if req.folds_config:
        cmd.extend(["--folds-config", req.folds_config])
    if req.train_config:
        cmd.extend(["--train-config", req.train_config])
    return cmd


@router.post("/walk-forward")
async def start_wfv(req: WFVRequest):
    if req.rank_metric != "information_ratio":
        raise HTTPException(status_code=400, detail="rank_metric is locked to information_ratio")
    tm = get_task_manager()
    topk = _wfv_topk(req)
    n_drop = _wfv_n_drop(req)
    hold_thresh = _wfv_hold_thresh(req)
    candidate_count = len(topk) * len(n_drop) * len(hold_thresh)
    window_count = max(1, req.rolling_window_days // max(1, req.step_days))

    if req.dry_run:
        preview = {
            "train_universes": req.train_universes,
            "eval_market": req.eval_market,
            "candidate_count": candidate_count,
            "window_count": window_count,
            "total_runs": candidate_count * window_count * len(req.train_universes),
            "estimated_minutes": candidate_count * window_count * max(1, len(req.train_universes)) * 20,
            "rank_metric": "information_ratio",
        }
        task_id = await tm.start_sync_task(
            "wfv_dry_run",
            lambda: preview,
            page_key="backtest",
            action_key="backtest.walk_forward",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _wfv():
        import subprocess
        cmd = _build_wfv_cmd(req)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Walk-forward validation failed (exit {result.returncode}): {result.stderr[-500:]}")
        return {"status": "completed", "result_paths": []}

    task_id = await tm.start_sync_task(
        "wfv",
        _wfv,
        page_key="backtest",
        action_key="backtest.walk_forward",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.get("/results/{filename}/equity-curve")
async def get_equity_curve(filename: str):
    _safe_path(BACKTEST_RESULTS_DIR, filename)
    try:
        return parse_equity_curve(filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/results/{filename}/metrics")
async def get_metrics(filename: str):
    _safe_path(BACKTEST_RESULTS_DIR, filename)
    result = parse_metrics(filename)
    if not result:
        raise HTTPException(status_code=404, detail="Metrics not found")
    return result


@router.get("/results/{filename}/drawdown")
async def get_drawdown(filename: str):
    _safe_path(BACKTEST_RESULTS_DIR, filename)
    try:
        return parse_drawdown(filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class CompareRequest(BaseModel):
    filenames: list[str] = []
    result_files: Optional[list[str]] = None
    dry_run: bool = True

    @field_validator("filenames", "result_files")
    @classmethod
    def result_files_must_not_be_blank(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        if len(value) == 0:
            return value
        if any(not item.strip() for item in value):
            raise ValueError("result files must not contain blank values")
        return value


def _compare_files(req: CompareRequest) -> list[str]:
    return req.result_files or req.filenames


@router.post("/compare")
async def compare_backtest_runs(req: CompareRequest):
    files = _compare_files(req)
    if len(files) < 2:
        raise HTTPException(status_code=422, detail="At least two result files are required")
    tm = get_task_manager()

    if req.dry_run:
        preview = {
            "result_files": files,
            "file_count": len(files),
            "available_files": [f for f in files if _safe_path(BACKTEST_RESULTS_DIR, f).exists()],
        }
        task_id = await tm.start_sync_task(
            "compare_dry_run",
            lambda: preview,
            page_key="backtest",
            action_key="backtest.compare",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _compare() -> dict:
        try:
            result = compare_runs(files)
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        return {"result": result, "result_paths": []}

    task_id = await tm.start_sync_task(
        "compare",
        _compare,
        page_key="backtest",
        action_key="backtest.compare",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
