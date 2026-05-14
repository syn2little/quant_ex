"""Parameter grid search over TopkDropout strategy."""
from __future__ import annotations
import concurrent.futures as _cf
import logging
import multiprocessing
import os
from itertools import product
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .metrics import compute_metrics

logger = logging.getLogger(__name__)


def _combo_worker_parallel(
    engine_config: dict,
    pred: "pd.Series",
    params: dict,
    start_time: Optional[str],
    end_time: Optional[str],
    universe_filter,
    seed: int,
    backtest_kwargs: Optional[dict] = None,
) -> dict:
    """Top-level worker for parallel combo execution (single fixed seed).

    Each worker runs in a freshly-spawned subprocess that inherits
    PYTHONHASHSEED=42 from the parent, ensuring determinism.
    """
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

    import qlib
    from quant_ex.backtest.engine import BacktestEngine
    from quant_ex.backtest.metrics import compute_metrics as _compute_metrics

    qlib.init(
        provider_uri=engine_config["qlib"]["provider_uri"],
        region=engine_config["qlib"]["region"],
    )
    engine = BacktestEngine(engine_config)
    try:
        report, _ = engine.run(
            pred=pred,
            strategy_params=params,
            start_time=start_time,
            end_time=end_time,
            universe_filter=universe_filter,
            seed=seed,
            **(backtest_kwargs or {}),
        )
        return _compute_metrics(report)
    except Exception as e:
        return {"_error": str(e)}


def _seed_worker(engine_config: dict, pred: pd.Series, params: dict,
                 start_time: Optional[str], end_time: Optional[str],
                 seed: int, result_queue, backtest_kwargs: Optional[dict] = None) -> None:
    """Top-level worker executed in a fresh subprocess (spawn).

    PYTHONHASHSEED is already set in the environment by the parent process
    before spawning, so Python's hash randomization matches ``seed``.
    """
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

    import qlib
    from quant_ex.backtest.engine import BacktestEngine
    from quant_ex.backtest.metrics import compute_metrics as _compute_metrics

    qlib.init(
        provider_uri=engine_config["qlib"]["provider_uri"],
        region=engine_config["qlib"]["region"],
    )
    engine = BacktestEngine(engine_config)
    try:
        report, _ = engine.run(
            pred=pred,
            strategy_params=params,
            start_time=start_time,
            end_time=end_time,
            seed=seed,
            **(backtest_kwargs or {}),
        )
        result_queue.put(_compute_metrics(report))
    except Exception as e:
        result_queue.put({"_error": str(e)})


class GridSearchBacktest:
    """
    Enumerate (topk × n_drop × hold_thresh) combinations,
    run a backtest for each, and collect metrics.

    Example:
        searcher = GridSearchBacktest(engine, pred, config)
        results  = searcher.run({"topk": [5, 10, 15], "n_drop": [1, 3], "hold_thresh": [3, 5]})
        best     = searcher.best_params(results)
    """

    DEFAULT_GRID: Dict[str, List[Any]] = {
        "topk":        [5, 10, 15, 20],
        "n_drop":      [1, 3, 5],
        "hold_thresh": [3, 5, 10],
    }

    MULTI_SEEDS: List[int] = [42, 123, 2024, 7, 999]

    def __init__(self, engine, pred: pd.Series, config: dict):
        self.engine = engine
        self.pred = pred
        self.config = config
        bt_cfg = config.get("backtest", {})
        self.rank_metric = bt_cfg.get("rank_metric", "information_ratio")

    # ── public ────────────────────────────────────────────────────────────────

    def run(
        self,
        param_grid: Optional[Dict[str, List[Any]]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        universe_filter=None,
        multi_seed: bool = False,
        n_jobs: int = -1,
        open_cost: Optional[float] = None,
        close_cost: Optional[float] = None,
        min_cost: Optional[float] = None,
        deal_price: Optional[str] = None,
        benchmark: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Run all parameter combinations.

        Args:
            multi_seed: If True, run each combo with 5 built-in seeds in
                        separate subprocesses (so PYTHONHASHSEED differs per
                        seed) and report averaged metrics.
            n_jobs: Number of parallel workers for single-seed combo search.
                    -1 (default) uses all CPU cores. 1 disables parallelism.
                    Ignored when multi_seed=True (seeds are already subprocesses).

        Returns:
            DataFrame sorted by configured ranking metric descending.
        """
        grid = param_grid or self.DEFAULT_GRID
        backtest_kwargs = {
            key: value
            for key, value in {
                "open_cost": open_cost,
                "close_cost": close_cost,
                "min_cost": min_cost,
                "deal_price": deal_price,
                "benchmark": benchmark,
            }.items()
            if value is not None
        }
        keys = list(grid.keys())
        combos = list(product(*[grid[k] for k in keys]))
        seeds = self.MULTI_SEEDS if multi_seed else [42]
        message = f"Grid search: {len(combos)} combinations"
        if multi_seed:
            message += f" × {len(seeds)} seeds"
        message += f" (rank_metric={self.rank_metric})"
        logger.info(message)

        # ── parallel single-seed path ──────────────────────────────────────
        if not multi_seed and n_jobs != 1 and len(combos) > 1:
            return self._run_parallel(
                combos, keys, start_time, end_time, universe_filter, n_jobs, backtest_kwargs
            )

        # ── serial / multi-seed path ───────────────────────────────────────
        rows = []
        for i, combo in enumerate(combos, 1):
            params = dict(zip(keys, combo))
            logger.info(f"  [{i}/{len(combos)}] {params}")
            seed_metrics: List[Dict] = []
            for seed in seeds:
                try:
                    if multi_seed:
                        metrics = self._run_seed_subprocess(
                            params, start_time, end_time, seed, backtest_kwargs
                        )
                    else:
                        report, _ = self.engine.run(
                            pred=self.pred,
                            strategy_params=params,
                            start_time=start_time,
                            end_time=end_time,
                            universe_filter=universe_filter,
                            seed=seed,
                            **backtest_kwargs,
                        )
                        metrics = compute_metrics(report)
                    seed_metrics.append(metrics)
                except Exception as e:
                    logger.warning(f"    seed={seed} FAILED: {e}")

            if not seed_metrics:
                rows.append({**params, "error": "all seeds failed"})
                continue

            # Average numeric metrics across seeds
            numeric_keys = [k for k, v in seed_metrics[0].items()
                            if isinstance(v, (int, float))]
            m = {k: float(np.mean([sm[k] for sm in seed_metrics if k in sm]))
                 for k in numeric_keys}
            if multi_seed:
                m["sharpe_std"] = float(np.std([sm.get("sharpe", 0) for sm in seed_metrics]))
            rows.append({**params, **m})
            logger.info(
                f"    Sharpe={m.get('sharpe', 0):.3f}"
                + (f"±{m.get('sharpe_std', 0):.3f}" if multi_seed else "")
                + f"  Ret={m.get('annual_return', 0):.2%}"
                + (
                    f"  IR={m.get('information_ratio', 0):.3f}"
                    if "information_ratio" in m else ""
                )
                + f"  DD={m.get('max_drawdown', 0):.2%}"
            )

        df = pd.DataFrame(rows)
        return self._sort_results(df)

    def _run_parallel(
        self,
        combos: list,
        keys: list,
        start_time: Optional[str],
        end_time: Optional[str],
        universe_filter,
        n_jobs: int,
        backtest_kwargs: Optional[dict] = None,
    ) -> pd.DataFrame:
        """Run combos in parallel using spawned subprocesses (PYTHONHASHSEED=42)."""
        max_workers = os.cpu_count() if n_jobs == -1 else max(1, n_jobs)
        max_workers = min(max_workers, len(combos))
        logger.info(f"  Running {len(combos)} combos in parallel with {max_workers} workers")

        ctx = multiprocessing.get_context("spawn")
        combo_results: Dict[tuple, dict] = {}

        with _cf.ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
            future_to_combo = {
                executor.submit(
                    _combo_worker_parallel,
                    self.config,
                    self.pred,
                    dict(zip(keys, combo)),
                    start_time,
                    end_time,
                    universe_filter,
                    42,
                    backtest_kwargs,
                ): combo
                for combo in combos
            }
            done = 0
            for future in _cf.as_completed(future_to_combo):
                combo = future_to_combo[future]
                params = dict(zip(keys, combo))
                done += 1
                try:
                    metrics = future.result()
                except Exception as e:
                    metrics = {"_error": str(e)}
                if "_error" in metrics:
                    logger.warning(f"  [{done}/{len(combos)}] {params} FAILED: {metrics['_error']}")
                else:
                    logger.info(
                        f"  [{done}/{len(combos)}] {params}"
                        f"  Sharpe={metrics.get('sharpe', 0):.3f}"
                        f"  Ret={metrics.get('annual_return', 0):.2%}"
                        + (
                            f"  IR={metrics.get('information_ratio', 0):.3f}"
                            if "information_ratio" in metrics else ""
                        )
                        + f"  DD={metrics.get('max_drawdown', 0):.2%}"
                    )
                combo_results[combo] = (params, metrics)

        rows = []
        for combo in combos:
            params, metrics = combo_results[combo]
            if "_error" in metrics:
                rows.append({**params, "error": metrics["_error"]})
            else:
                rows.append({**params, **metrics})

        df = pd.DataFrame(rows)
        return self._sort_results(df)

    # ── private ───────────────────────────────────────────────────────────────

    def _run_seed_subprocess(
        self,
        params: dict,
        start_time: Optional[str],
        end_time: Optional[str],
        seed: int,
        backtest_kwargs: Optional[dict] = None,
    ) -> dict:
        """Run one backtest in a fresh subprocess with PYTHONHASHSEED=seed.

        Setting os.environ["PYTHONHASHSEED"] here (in the parent) before
        calling ctx.Process() causes the spawned child to inherit that value.
        The child's Python interpreter reads PYTHONHASHSEED at startup, before
        any user code runs, so hash randomization is truly seeded to ``seed``.
        """
        os.environ["PYTHONHASHSEED"] = str(seed)
        os.environ["_QUANT_EX_SEED_WORKER"] = "1"  # suppress re-exec in child
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(
            target=_seed_worker,
            args=(self.config, self.pred, params, start_time, end_time, seed, q, backtest_kwargs),
        )
        p.start()
        p.join()

        if q.empty():
            raise RuntimeError(f"subprocess for seed={seed} returned no result")
        result = q.get_nowait()
        if isinstance(result, dict) and "_error" in result:
            raise RuntimeError(result["_error"])
        return result

    @staticmethod
    def best_params(results: pd.DataFrame) -> Dict[str, Any]:
        """Extract best parameter set from grid search DataFrame."""
        valid = results.dropna(subset=["sharpe"]) if "sharpe" in results.columns else results
        if valid.empty:
            return {}
        row = valid.iloc[0]
        return {
            "topk":        int(row.get("topk", 10)),
            "n_drop":      int(row.get("n_drop", 3)),
            "hold_thresh": int(row.get("hold_thresh", 5)),
        }

    def _sort_results(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort by configured research ranking metric, falling back to Sharpe."""
        if df.empty:
            return df
        rank_metric = self.rank_metric if self.rank_metric in df.columns else "sharpe"
        if rank_metric not in df.columns:
            return df
        sort_cols = [rank_metric]
        ascending = [False]
        if "sharpe_std" in df.columns:
            sort_cols.append("sharpe_std")
            ascending.append(True)
        return df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
