import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from web.api.deps import MODELS_DIR, get_config
from web.api.services.task_manager import get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _safe_model_path(filename: str, suffix: str) -> Path:
    """Build sidecar path and prevent traversal. Returns the full Path."""
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid filename")
    stem = Path(filename).stem
    return MODELS_DIR / f"{stem}{suffix}"


def _safe_model_file(filename: str) -> Path:
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid filename")
    return MODELS_DIR / Path(filename).name


def _resolve_final_market(config_override: Optional[str], market: Optional[str]) -> str:
    if market:
        return market
    if config_override:
        config_path = Path(config_override)
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            config_market = data.get("market", {})
            if isinstance(config_market, dict) and config_market.get("name"):
                return str(config_market["name"])
            if isinstance(config_market, str):
                return config_market
        except FileNotFoundError:
            return "unknown_config_missing"
        except Exception as exc:
            logger.warning("Failed to resolve market from %s: %s", config_override, exc)
            return "unknown_config_error"
    config = get_config()
    config_market = config.get("market", {})
    if isinstance(config_market, dict):
        return str(config_market.get("name") or "csi300")
    if isinstance(config_market, str):
        return config_market
    return "csi300"


def _estimate_train_minutes(req: "TrainRequest") -> int:
    base = 20 if (req.model_type or req.model) == "lgbm" else 30
    if req.qlib_native:
        base += 10
    if req.ensemble_seeds:
        base *= max(1, len(req.ensemble_seeds))
    return base


@router.get("")
async def list_models():
    if not MODELS_DIR.exists():
        return []
    models = []
    for pkl in sorted(MODELS_DIR.glob("*.pkl")):
        meta_path = MODELS_DIR / f"{pkl.stem}_meta.json"
        meta = {}
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
        models.append({
            "filename": pkl.name,
            "size_mb": round(pkl.stat().st_size / 1024 / 1024, 2),
            "modified": datetime.fromtimestamp(pkl.stat().st_mtime).isoformat(),
            "meta": meta,
        })
    return models


@router.get("/registry")
async def model_registry():
    from quant_ex.models.base import ModelRegistry
    from quant_ex.features.base import FactorRegistry

    try:
        from quant_ex.models import trainer  # noqa: F401
    except Exception as exc:
        logger.warning("Failed to import trainer: %s", exc)

    return {
        "models": [{"name": n} for n in ModelRegistry.list()],
        "factors": [{"name": n} for n in FactorRegistry.list()],
    }


@router.get("/{filename}/meta")
async def get_meta(filename: str):
    meta_path = _safe_model_path(filename, "_meta.json")
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Meta file not found")
    with open(meta_path) as f:
        return json.load(f)


@router.get("/{filename}/importance")
async def get_importance(filename: str):
    imp_path = _safe_model_path(filename, "_feature_importance.json")
    if not imp_path.exists():
        raise HTTPException(status_code=404, detail="Importance file not found")
    with open(imp_path) as f:
        return json.load(f)


class TrainRequest(BaseModel):
    model: str = "lgbm"
    model_type: Optional[str] = None
    tag: Optional[str] = None
    config_override: Optional[str] = None
    market: Optional[str] = None
    train_start_date: Optional[str] = None
    train_end_date: Optional[str] = None
    factors: list[str] = []
    fit_start: Optional[str] = None
    fit_end: Optional[str] = None
    qlib_native: bool = False
    with_sector: bool = False
    no_extra_factors: bool = False
    skip_factor_pipeline: bool = False
    bagging_fraction: Optional[float] = None
    ensemble_seeds: Optional[list[int]] = None
    dry_run: bool = True


def _train_model(req: TrainRequest) -> dict:
    from quant_ex.utils.config import load_config
    from quant_ex.data.loader import DataLoader
    from quant_ex.models.trainer import ModelTrainer
    from quant_ex.features.base import FactorPipeline

    cfg = load_config(req.config_override) if req.config_override else load_config()
    loader = DataLoader(cfg)
    trainer = ModelTrainer(cfg, loader)

    factor_pipeline = None
    if req.factors:
        factor_configs = [{"name": f} for f in req.factors]
        factor_pipeline = FactorPipeline.from_config(factor_configs)

    kwargs = {}
    fit_start = req.train_start_date or req.fit_start
    fit_end = req.train_end_date or req.fit_end
    if fit_start:
        kwargs["fit_start"] = fit_start
    if fit_end:
        kwargs["fit_end"] = fit_end
    if req.with_sector:
        kwargs["with_sector"] = req.with_sector
    if req.no_extra_factors:
        kwargs["no_extra_factors"] = req.no_extra_factors
    if req.skip_factor_pipeline:
        kwargs["skip_factor_pipeline"] = req.skip_factor_pipeline
    if req.bagging_fraction is not None:
        kwargs["bagging_fraction"] = req.bagging_fraction
    if req.ensemble_seeds is not None:
        kwargs["ensemble_seeds"] = req.ensemble_seeds

    model_name = req.model_type or req.model
    _model, _dataset, recorder_id = trainer.train(
        model_name=model_name,
        tag=req.tag,
        factor_pipeline=factor_pipeline,
        qlib_native=req.qlib_native,
        **kwargs,
    )
    return {"recorder_id": recorder_id, "result_paths": []}


@router.post("/train")
async def start_training(req: TrainRequest):
    tm = get_task_manager()
    model_name = req.model_type or req.model
    final_market = _resolve_final_market(req.config_override, req.market)

    if req.dry_run:
        preview = {
            "model_type": model_name,
            "tag": req.tag,
            "final_market": final_market,
            "train_window": {
                "start": req.train_start_date or req.fit_start,
                "end": req.train_end_date or req.fit_end,
            },
            "config_override": req.config_override,
            "estimated_minutes": _estimate_train_minutes(req),
            "output_path": f"models/{model_name}_{req.tag or 'web'}.pkl",
        }
        task_id = await tm.start_sync_task(
            "model_train_dry_run",
            lambda: preview,
            page_key="models",
            action_key="models.train",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    task_id = await tm.start_sync_task(
        "model_train",
        _train_model,
        req,
        page_key="models",
        action_key="models.train",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.delete("/{filename}")
async def delete_model(filename: str, dry_run: bool = Query(True)):
    target = _safe_model_file(filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"model not found: {filename}")

    candidates = [
        target,
        MODELS_DIR / f"{target.stem}_meta.json",
        MODELS_DIR / f"{target.stem}_feature_importance.json",
    ]
    files = [str(path) for path in candidates if path.exists()]
    tm = get_task_manager()

    if dry_run:
        preview = {"filename": filename, "files": files, "count": len(files)}
        task_id = await tm.start_sync_task(
            "model_delete_dry_run",
            lambda: preview,
            page_key="models",
            action_key="models.delete",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _delete() -> dict:
        removed = []
        for path in candidates:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        return {"removed": removed, "result_paths": []}

    task_id = await tm.start_sync_task(
        "model_delete",
        _delete,
        page_key="models",
        action_key="models.delete",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
