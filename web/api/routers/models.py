import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

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


def _model_result_paths(stem: str) -> list[str]:
    candidates = [
        MODELS_DIR / f"{stem}.pkl",
        MODELS_DIR / f"{stem}_meta.json",
        MODELS_DIR / f"{stem}_feature_importance.json",
    ]
    return [str(path) for path in candidates if path.exists()]


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


def _train_window(req: "TrainRequest") -> dict[str, Optional[str]]:
    return {
        "start": req.train_start_date or req.fit_start,
        "end": req.train_end_date or req.fit_end,
    }


def _config_source(req: "TrainRequest") -> dict[str, Any]:
    if req.config_override:
        path = Path(req.config_override)
        resolved = path if path.is_absolute() else Path.cwd() / path
        return {
            "type": "override",
            "path": req.config_override,
            "exists": resolved.exists(),
        }
    return {"type": "default", "path": "config/base.yaml", "exists": (Path.cwd() / "config/base.yaml").exists()}


def _effective_params(req: "TrainRequest") -> dict[str, Any]:
    return {
        "training_mode": "qlib_native" if req.qlib_native else "custom",
        "factor_pipeline_enabled": not (req.no_extra_factors or req.skip_factor_pipeline),
        "custom_factors": req.factors,
        "with_sector": req.with_sector,
        "no_extra_factors": req.no_extra_factors,
        "skip_factor_pipeline": req.skip_factor_pipeline,
        "ensemble_seeds": req.ensemble_seeds,
        "bagging_fraction": req.bagging_fraction,
        "lightgbm": req.lgbm_params or {},
    }


def _apply_training_overrides(cfg: dict, req: "TrainRequest") -> None:
    if req.market:
        cfg.setdefault("market", {})["name"] = req.market

    training = cfg.setdefault("training", {})
    window = _train_window(req)
    if window["start"]:
        training["fit_start"] = window["start"]
    if window["end"]:
        training["fit_end"] = window["end"]

    if req.lgbm_params:
        cfg.setdefault("model", {}).setdefault("lightgbm", {}).update(req.lgbm_params)

    if req.ensemble_seeds is not None or req.bagging_fraction is not None:
        ensemble = cfg.setdefault("model", {}).setdefault("ensemble", {})
        ensemble["enabled"] = True
        if req.ensemble_seeds is not None:
            ensemble["seeds"] = req.ensemble_seeds
        if req.bagging_fraction is not None:
            ensemble["bagging_fraction"] = req.bagging_fraction


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
            "result_paths": _model_result_paths(pkl.stem),
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
    model: Optional[str] = None
    model_type: Optional[str] = None
    tag: Optional[str] = Field(default=None, min_length=1)
    config_override: Optional[str] = None
    market: Optional[str] = None
    train_start_date: Optional[str] = None
    train_end_date: Optional[str] = None
    factors: list[str] = Field(default_factory=list)
    fit_start: Optional[str] = None
    fit_end: Optional[str] = None
    qlib_native: bool = False
    with_sector: bool = False
    no_extra_factors: bool = False
    skip_factor_pipeline: bool = False
    bagging_fraction: Optional[float] = Field(default=None, gt=0, le=1)
    ensemble_seeds: Optional[list[int]] = None
    lgbm_params: Optional[dict[str, Any]] = None
    dry_run: bool = True

    @field_validator("model", "model_type", "market", "config_override", "train_start_date", "train_end_date", "fit_start", "fit_end")
    @classmethod
    def strings_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("string fields must not be blank")
        return value

    @field_validator("factors")
    @classmethod
    def factors_must_not_be_empty_when_provided(cls, value: list[str]) -> list[str]:
        if value is not None and len(value) == 0:
            return value
        if any(not item.strip() for item in value):
            raise ValueError("factors must not contain blank values")
        return value

    @field_validator("ensemble_seeds")
    @classmethod
    def ensemble_seeds_must_not_be_empty(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is not None and len(value) == 0:
            raise ValueError("ensemble_seeds must not be empty")
        return value

    @field_validator("lgbm_params")
    @classmethod
    def lgbm_params_must_be_object(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is not None and any(not str(key).strip() for key in value):
            raise ValueError("lgbm_params keys must not be blank")
        return value

    @model_validator(mode="after")
    def model_name_is_required(self) -> "TrainRequest":
        if not (self.model_type or self.model):
            raise ValueError("model_type is required")
        return self


def _train_model(req: TrainRequest) -> dict:
    from quant_ex.utils.config import load_config
    from quant_ex.data.loader import DataLoader
    from quant_ex.models.trainer import ModelTrainer
    from quant_ex.features.base import FactorPipeline

    cfg = load_config(req.config_override) if req.config_override else load_config()
    _apply_training_overrides(cfg, req)
    loader = DataLoader(cfg)
    trainer = ModelTrainer(cfg, loader)

    factor_pipeline = None
    if req.factors:
        factor_configs = [{"name": f} for f in req.factors]
        factor_pipeline = FactorPipeline.from_config(factor_configs)

    model_name = req.model_type or req.model
    _model, _dataset, recorder_id = trainer.train(
        model_name=model_name,
        tag=req.tag,
        factor_pipeline=factor_pipeline,
        qlib_native=req.qlib_native,
        skip_factor_pipeline=req.no_extra_factors or req.skip_factor_pipeline,
        use_sector_factors=req.with_sector,
    )
    return {"recorder_id": recorder_id, "result_paths": trainer.last_result_paths}


@router.post("/train")
async def start_training(req: TrainRequest):
    tm = get_task_manager()
    model_name = req.model_type or req.model
    final_market = _resolve_final_market(req.config_override, req.market)

    if req.dry_run:
        if req.qlib_native:
            output_path = "qlib_workflow/<experiment>/<recorder_id>"
            estimated_outputs = [
                "qlib_workflow/<experiment>/<recorder_id>/trained_model",
                "mlruns/<experiment>/<run_id>",
            ]
        else:
            output_path = f"models/{model_name}_{req.tag or 'web'}_<timestamp>.pkl"
            estimated_outputs = [
                output_path,
                f"models/{model_name}_{req.tag or 'web'}_<timestamp>_meta.json",
            ]
            estimated_outputs.append(f"models/{model_name}_{req.tag or 'web'}_<timestamp>_feature_importance.json")
        preview = {
            "model_type": model_name,
            "tag": req.tag,
            "final_market": final_market,
            "train_window": _train_window(req),
            "config_override": req.config_override,
            "config_source": _config_source(req),
            "estimated_minutes": _estimate_train_minutes(req),
            "output_path": output_path,
            "estimated_outputs": estimated_outputs,
            "effective_params": _effective_params(req),
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
