"""
Model training orchestrator.

Now model-agnostic: uses ModelRegistry to instantiate any registered model
and FactorPipeline to compose extra features.

Two execution paths:
1. qlib_native=True  — uses qlib's LGBModel + MLflow experiment tracking.
2. qlib_native=False — uses any BaseAlphaModel from ModelRegistry with
                       FactorPipeline-computed extra features.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .base import ModelRegistry
from ..features.base import FactorPipeline, FactorRegistry

logger = logging.getLogger(__name__)

# Ensure all models and factors are registered by importing them
import importlib as _il
for _m in ("lgbm_model", "linear_model", "xgb_model", "nn_model"):
    _il.import_module(f".{_m}", package=__name__.rsplit(".", 1)[0])
for _f in ("sector_factors", "technical_factors", "factor_mining", "regime_features",
           "csv_factor", "fundamental_factor", "northbound_factor", "valuation_factor",
           "pledge_factor", "margin_factor", "insider_factor", "analyst_factor",
           "shareholder_factor", "dividend_factor", "balance_sheet_factor",
           "earnings_guidance_factor", "institutional_factor",
           "repurchase_factor", "visit_factor"):
    try:
        _il.import_module(f"..features.{_f}", package=__name__.rsplit(".", 1)[0])
    except ImportError as _e:
        import logging as _logging
        _logging.getLogger(__name__).debug("Optional factor module skipped: %s (%s)", _f, _e)


def _sanitize_artifact_tag(tag: Optional[str]) -> Optional[str]:
    if not tag:
        return None
    safe_tag = re.sub(r"[^0-9A-Za-z._-]+", "_", tag).strip("._-")
    return safe_tag or None


class ModelTrainer:
    """
    Orchestrates model training.

    Parameters
    ----------
    config          : merged configuration dict (base + model yaml)
    data_loader     : DataLoader instance
    sector_provider : optional SectorDataProvider (needed for sector factors)
    """

    def __init__(self, config: dict, data_loader, sector_provider=None):
        self.config = config
        self.data_loader = data_loader
        self.sector_provider = sector_provider
        self.model_dir = Path(config.get("paths", {}).get("model_dir", "./models"))
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.last_result_paths: list[str] = []

    # ── public API ────────────────────────────────────────────────────────────

    def train(
        self,
        model_name: str = "lgbm",
        qlib_native: bool = False,
        price_data: Optional[pd.DataFrame] = None,
        factor_pipeline: Optional[FactorPipeline] = None,
        experiment_name: Optional[str] = None,
        tag: Optional[str] = None,
        skip_factor_pipeline: bool = False,
        # legacy compat
        use_sector_factors: bool = False,
    ) -> Tuple:
        """
        Train a model.

        Parameters
        ----------
        model_name      : registry key for the model (e.g. "lgbm", "xgb", "ridge")
        qlib_native     : if True, use qlib's built-in LGBModel with MLflow tracking
        price_data      : OHLCV DataFrame required when factor_pipeline is provided
        factor_pipeline : FactorPipeline instance (or built from config below)
        experiment_name : MLflow experiment name (qlib_native mode only)
        use_sector_factors: legacy flag – adds a SectorFactor to the pipeline

        Returns
        -------
        (model, dataset, recorder_id_or_None)
        """
        self.last_result_paths = []
        exp_name = experiment_name or self.config.get("experiment", {}).get("name", "quant_ex_exp")
        training_cfg = self.config.get("training", {})
        today = datetime.now().strftime("%Y-%m-%d")
        market = self.config.get("market", {}).get("name", "csi300")

        segments = {
            "train": (training_cfg.get("fit_start", "2015-01-01"),
                      training_cfg.get("fit_end",   "2021-12-31")),
            "valid": (training_cfg.get("valid_start", "2022-01-01"),
                      training_cfg.get("valid_end",   "2023-12-31")),
            "test":  (training_cfg.get("test_start", "2024-01-01"), today),
        }

        dataset = self.data_loader.build_dataset(segments=segments, instruments=market)

        if qlib_native:
            return self._train_qlib(dataset, exp_name)

        # Build factor pipeline if not provided
        if not skip_factor_pipeline and factor_pipeline is None:
            factor_pipeline = self._build_factor_pipeline(
                price_data=price_data,
                use_sector_factors=use_sector_factors,
            )

        # Compute extra features
        extra_factors: Optional[pd.DataFrame] = None
        if factor_pipeline is not None and price_data is not None:
            logger.info(f"Running FactorPipeline: {factor_pipeline}")
            extra_factors = factor_pipeline.compute(price_data)
            if extra_factors is not None:
                logger.info(
                    f"Extra features: {len(extra_factors.columns)} columns, "
                    f"{len(extra_factors)} rows"
                )

        return self._train_custom(
            dataset, model_name, extra_factors,
            factor_pipeline=factor_pipeline, tag=tag,
            use_sector_factors=use_sector_factors,
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _train_qlib(self, dataset, exp_name: str):
        from qlib.workflow import R
        from qlib.utils import init_instance_by_config

        lgb_cfg = self.config.get("model", {}).get("lightgbm", {})
        model_conf = {
            "class": "LGBModel",
            "module_path": "qlib.contrib.model.gbdt",
            "kwargs": {
                "loss": "mse",
                "colsample_bytree": lgb_cfg.get("colsample_bytree", 0.8),
                "learning_rate":    lgb_cfg.get("learning_rate", 0.05),
                "subsample":        lgb_cfg.get("subsample", 0.8),
                "lambda_l1":        lgb_cfg.get("reg_alpha", 0.1),
                "lambda_l2":        lgb_cfg.get("reg_lambda", 0.1),
                "max_depth":        lgb_cfg.get("max_depth", 8),
                "num_leaves":       lgb_cfg.get("num_leaves", 64),
                "num_threads":      20,
                "n_estimators":     lgb_cfg.get("n_estimators", 1000),
                "seed":             lgb_cfg.get("seed", 42),
                "feature_fraction_seed": lgb_cfg.get("feature_fraction_seed", 42),
                "bagging_seed":     lgb_cfg.get("bagging_seed", 42),
                "data_random_seed": lgb_cfg.get("data_random_seed", 42),
                "extra_seed":       lgb_cfg.get("extra_seed", 42),
                "deterministic":    lgb_cfg.get("deterministic", True),
                "force_col_wise":   lgb_cfg.get("force_col_wise", True),
                "verbose":          -1,
                "early_stopping_rounds": lgb_cfg.get("early_stopping_rounds", 50),
                "eval_set_key":     ["valid"],
            },
        }

        with R.start(experiment_name=exp_name):
            model = init_instance_by_config(model_conf)
            model.fit(dataset)
            R.save_objects(trained_model=model)
            rid = R.get_recorder().id

        logger.info(f"qlib model trained. Recorder ID: {rid}")
        logger.info(f"→ Set experiment.latest_recorder_id = \"{rid}\" in base.yaml")
        return model, dataset, rid

    def _train_custom(
        self,
        dataset,
        model_name: str,
        extra_factors: Optional[pd.DataFrame],
        factor_pipeline: Optional[FactorPipeline] = None,
        tag: Optional[str] = None,
        use_sector_factors: bool = False,
    ):
        """Instantiate and train any model from the registry."""
        import json as _json

        model_cfg = self.config.get("model", {})

        # Build model-specific kwargs from config
        kwargs = self._model_kwargs(model_name, model_cfg, extra_factors, factor_pipeline)

        logger.info(f"Training model '{model_name}' …")
        model = ModelRegistry.build(model_name, **kwargs)
        model.fit(dataset)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_tag = _sanitize_artifact_tag(tag)
        stem = f"{model_name}_{safe_tag}_{ts}" if safe_tag else f"{model_name}_{ts}"
        path = self.model_dir / f"{stem}.pkl"
        model.save(str(path))

        # Save sidecar metadata for experiment tracking
        meta = {
            "model": model_name,
            "tag": tag,
            "safe_tag": safe_tag,
            "ts": ts,
            "extra_factor_cols": list(extra_factors.columns) if extra_factors is not None else [],
            "runtime_flags": {
                "use_sector_factors": use_sector_factors,
            },
            "config_snapshot": {
                "training": self.config.get("training", {}),
                "market": self.config.get("market", {}),
                "features": self.config.get("model", {}).get("features", {}),
            },
        }
        meta_path = self.model_dir / f"{stem}_meta.json"
        meta_path.write_text(
            _json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Metadata saved → {stem}_meta.json")

        # Persist feature importance for trend analysis
        result_paths = [path, meta_path]
        try:
            imp_df = model.feature_importance(top_n=50)
            if not imp_df.empty:
                imp_path = self.model_dir / f"{stem}_feature_importance.json"
                imp_records = imp_df.to_dict(orient="records")
                imp_path.write_text(
                    _json.dumps(
                        {"model": model_name, "tag": tag, "ts": ts, "importance": imp_records},
                        ensure_ascii=False, indent=2,
                    ),
                    encoding="utf-8",
                )
                logger.info(f"Feature importance saved → {imp_path.name}")
                result_paths.append(imp_path)
        except Exception as exc:
            logger.debug(f"Feature importance export skipped: {exc}")

        self.last_result_paths = [str(p) for p in result_paths]
        return model, dataset, None

    def _model_kwargs(
        self,
        model_name: str,
        model_cfg: dict,
        extra_factors: Optional[pd.DataFrame],
        factor_pipeline: Optional[FactorPipeline] = None,
    ) -> dict:
        """Derive __init__ kwargs for the chosen model from config."""
        base = {"extra_factors": extra_factors}

        if model_name == "lgbm":
            base["lgbm_params"] = model_cfg.get("lightgbm", {})
            ensemble_cfg = model_cfg.get("ensemble", {})
            if ensemble_cfg.get("enabled", False):
                base["ensemble_seeds"] = ensemble_cfg.get("seeds", [42, 123, 2024])
            bagging_fraction = ensemble_cfg.get("bagging_fraction", None)
            if bagging_fraction is not None:
                base["bagging_fraction"] = float(bagging_fraction)
            if factor_pipeline is not None:
                base["factor_pipeline"] = factor_pipeline

        elif model_name == "xgb":
            base["xgb_params"] = model_cfg.get("xgboost", {})

        elif model_name == "mlp":
            base["mlp_params"] = model_cfg.get("mlp", {})

        elif model_name in ("ridge", "lasso"):
            linear_cfg = model_cfg.get("linear", {})
            base["alpha"] = linear_cfg.get("alpha", 1.0 if model_name == "ridge" else 0.01)

        # Generic: pass any model-specific section matching model_name
        elif model_name in model_cfg:
            base.update(model_cfg[model_name])

        return base

    def _build_factor_pipeline(
        self,
        price_data: Optional[pd.DataFrame],
        use_sector_factors: bool,
    ) -> Optional[FactorPipeline]:
        """
        Build FactorPipeline from config or legacy flags.

        Priority:
        1. model.factors list in config (explicit pipeline)
        2. Legacy --with-sector flag
        3. None (no extra factors)
        """
        feat_cfg = self.config.get("model", {}).get("features", {})
        factor_list = feat_cfg.get("factors", None)

        if factor_list:
            # Build from explicit config list.
            # If --with-sector is active and "sector" is not already listed, inject it.
            factor_list = list(factor_list)
            has_sector = any(f.get("name") == "sector" for f in factor_list)
            if use_sector_factors and not has_sector and self.sector_provider is not None:
                factor_list.append({"name": "sector"})
                logger.info("--with-sector: 动态注入 sector 因子到 pipeline")
            shared = {}
            if self.sector_provider is not None:
                shared["sector_map"] = self.sector_provider.get_map()
                concept_map = self.sector_provider.get_concept_map()
                if concept_map:
                    shared["concept_map"] = concept_map
            return FactorPipeline.from_config(factor_list, **shared)

        # Legacy: use_sector_factors flag
        if use_sector_factors and self.sector_provider is not None:
            sector_map = self.sector_provider.get_map()
            concept_map = self.sector_provider.get_concept_map()
            cfg = feat_cfg
            from ..features.sector_factors import SectorFactorEngine
            engine = SectorFactorEngine(
                sector_map=sector_map,
                concept_map=concept_map or None,
                momentum_windows=cfg.get("sector_momentum_windows", [5, 10, 20, 60]),
                reversal_windows=cfg.get("sector_reversal_windows", [5, 20]),
            )
            factors = [engine]

            if feat_cfg.get("use_mined_factors", False):
                from ..features.factor_mining import MinedFactorLoader
                factors.append(
                    MinedFactorLoader(path=feat_cfg.get("mined_factors_path",
                                                        "./cache/mined_factors.json"))
                )
            return FactorPipeline(factors)

        return None
