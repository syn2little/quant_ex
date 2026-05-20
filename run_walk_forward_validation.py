#!/usr/bin/env python3
"""Run walk-forward model training and strategy validation.

This script retrains models for each chronological fold, backtests only the
fold's future test window, and writes fold CSVs plus an aggregate report under
optimization_results/walk_forward_*.
"""
from __future__ import annotations

import argparse
import concurrent.futures as _cf
import json
import logging
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
import yaml

from utils.config import deep_merge

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


@dataclass(frozen=True)
class Fold:
    name: str
    fit_start: str
    fit_end: str
    valid_start: str
    valid_end: str
    test_start: str
    test_end: str


DEFAULT_FOLDS = [
    Fold("test_2020", "2015-01-01", "2018-12-31", "2019-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    Fold("test_2021", "2015-01-01", "2019-12-31", "2020-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    Fold("test_2022", "2015-01-01", "2020-12-31", "2021-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    Fold("test_2023", "2015-01-01", "2021-12-31", "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    Fold("test_2024", "2015-01-01", "2021-12-31", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    Fold("test_2025", "2015-01-01", "2022-12-31", "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    Fold("test_2026", "2015-01-01", "2023-12-31", "2024-01-01", "2025-12-31", "2026-01-01", datetime.now().strftime("%Y-%m-%d")),
]


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_csv(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _copy_dict(d: dict) -> dict:
    """Recursively shallow-copy a dict so mutations don't touch the original."""
    out = {}
    for k, v in d.items():
        out[k] = _copy_dict(v) if isinstance(v, dict) else v
    return out


def newest_model_for_tag(tag: str, before_ts: float) -> Path:
    """Find the newest .pkl model for *tag* created before *before_ts*.

    Model files follow the pattern: ``lgbm_{tag}_{YYYYMMDD_HHMMSS}.pkl``.
    """
    models_dir = REPO_ROOT / "models"
    candidates = sorted(models_dir.glob(f"lgbm_{tag}_*.pkl"))
    if not candidates:
        raise FileNotFoundError(f"No model found for tag '{tag}' in {models_dir}")
    # Filter to models created before the training started (avoid picking up stale ones)
    valid = [p for p in candidates if p.stat().st_mtime <= before_ts + 5]
    if not valid:
        # Fallback: just return the newest one regardless
        valid = candidates
    return valid[-1]


def run_command(command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write("$ " + " ".join(command) + "\n\n")
        log_file.flush()
        subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=True,
        )


def write_fold_config(
    path: Path,
    fold: Fold,
    train_universe: str,
    train_config: Optional[dict] = None,
) -> None:
    """Write a fold-specific training config YAML.

    If *train_config* is provided it is deep-merged first, then the
    fold-specific keys (market, dates) are merged on top so they always win.
    """
    # Start with the user-supplied train-config (if any) as the base.
    config: dict = {}
    if train_config:
        config = _copy_dict(train_config)

    # Fold-specific keys always take precedence over the train-config.
    fold_overrides = {
        "market": {
            "name": train_universe,
        },
        "training": {
            "fit_start": fold.fit_start,
            "fit_end": fold.fit_end,
            "valid_start": fold.valid_start,
            "valid_end": fold.valid_end,
            "test_start": fold.test_start,
        },
    }
    deep_merge(config, fold_overrides)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_folds(folds_config: Optional[str]) -> list:
    """Return fold list from a YAML file, or DEFAULT_FOLDS if not provided.

    YAML format::

        folds:
          - name: custom_2023
            fit_start:   "2015-01-01"
            fit_end:     "2021-12-31"
            valid_start: "2022-01-01"
            valid_end:   "2022-12-31"
            test_start:  "2023-01-01"
            test_end:    "2023-12-31"
    """
    if not folds_config:
        return list(DEFAULT_FOLDS)
    path = Path(folds_config)
    if not path.exists():
        raise FileNotFoundError(f"--folds-config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    raw = data.get("folds", data)  # allow top-level list or dict with 'folds' key
    if not isinstance(raw, list):
        raise ValueError("folds_config YAML must contain a 'folds' list")
    return [Fold(**f) for f in raw]





def summarize(
    results: pd.DataFrame,
    robust_weights: Optional[dict] = None,
) -> pd.DataFrame:
    """Aggregate fold results.

    Args:
        results:        All-fold results DataFrame.
        robust_weights: Optional dict of scoring weights, e.g.
                        {"mean_sharpe": 1.0, "sharpe_std": -0.5,
                         "min_sharpe": 0.2, "positive_sharpe_folds": 0.05}.
                        Defaults to the historically chosen values.

    Statistical significance (GAP-04):
        ``sharpe_ttest_pvalue`` — one-sample t-test H0: mean(sharpe) = 0.
        ``return_ttest_pvalue`` — one-sample t-test H0: mean(annual_return) = 0.
        Both are NaN when fewer than 2 folds are available.
    """
    from scipy import stats as _stats

    w = robust_weights or {
        "mean_sharpe": 1.0,
        "sharpe_std": -0.5,
        "min_sharpe": 0.2,
        "positive_sharpe_folds": 0.05,
    }
    group_cols = ["train_universe", "eval_market", "topk", "n_drop", "hold_thresh"]
    rows = []
    for keys, group in results.groupby(group_cols, dropna=False):
        row = dict(zip(group_cols, keys))

        sharpe_vals = group["sharpe"].dropna()
        ret_vals    = group["annual_return"].dropna()

        # One-sample t-test: H0 = 0
        if len(sharpe_vals) >= 2:
            _, sharpe_p = _stats.ttest_1samp(sharpe_vals, popmean=0.0)
        else:
            sharpe_p = float("nan")

        if len(ret_vals) >= 2:
            _, ret_p = _stats.ttest_1samp(ret_vals, popmean=0.0)
        else:
            ret_p = float("nan")

        row.update(
            folds=int(group["fold"].nunique()),
            mean_annual_return=ret_vals.mean(),
            median_annual_return=ret_vals.median(),
            mean_sharpe=sharpe_vals.mean(),
            median_sharpe=sharpe_vals.median(),
            min_sharpe=sharpe_vals.min(),
            sharpe_std=sharpe_vals.std(ddof=0),
            mean_max_drawdown=group["max_drawdown"].mean(),
            worst_max_drawdown=group["max_drawdown"].min(),
            positive_return_folds=int((group["annual_return"] > 0).sum()),
            positive_sharpe_folds=int((group["sharpe"] > 0).sum()),
            mean_rank_ic=group["rank_ic"].mean() if "rank_ic" in group else float("nan"),
            mean_rank_icir=group["rank_icir"].mean() if "rank_icir" in group else float("nan"),
            sharpe_ttest_pvalue=sharpe_p,
            return_ttest_pvalue=ret_p,
        )
        row["robust_score"] = (
            w.get("mean_sharpe", 1.0)           * row["mean_sharpe"]
            + w.get("sharpe_std", -0.5)         * row["sharpe_std"]
            + w.get("min_sharpe", 0.2)          * row["min_sharpe"]
            + w.get("positive_sharpe_folds", 0.05) * row["positive_sharpe_folds"]
        )
        rows.append(row)
    df = pd.DataFrame(rows).sort_values(
        ["robust_score", "mean_sharpe", "worst_max_drawdown"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    # GAP-05: Pareto front on (mean_sharpe, min_sharpe) — both higher is better
    df["pareto_front"] = _compute_pareto_front(df, ["mean_sharpe", "min_sharpe"])
    return df


def _compute_pareto_front(df: pd.DataFrame, objectives: list) -> pd.Series:
    """Mark configs on the Pareto-optimal front (all objectives higher-is-better).

    A row is dominated if another row is >= in ALL objectives and > in at least one.
    Returns a boolean Series; True = Pareto-optimal.
    """
    values = df[objectives].to_numpy(dtype=float, na_value=float("-inf"))
    n = len(values)
    pareto = [True] * n
    for i in range(n):
        if not pareto[i]:
            continue
        for j in range(n):
            if i == j or not pareto[j]:
                continue
            # j dominates i?
            if all(values[j] >= values[i]) and any(values[j] > values[i]):
                pareto[i] = False
                break
    return pd.Series(pareto, index=df.index)


def pct(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value:.2%}"


def write_report(path: Path, summary: pd.DataFrame, results: pd.DataFrame, args: argparse.Namespace) -> None:
    top = summary.head(12).copy()
    lines = [
        "# Walk-forward Validation Report",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Train universes: `{args.train_universes}`",
        f"- Eval market: `{args.eval_market}`",
        f"- Strategy grid: topk=`{args.topk}`, n_drop=`{args.n_drop}`, hold_thresh=`{args.hold_thresh}`",
        f"- Folds: {results['fold'].nunique()}",
        "",
        "## Best Robust Configurations",
        "",
        "| rank | train_universe | topk | n_drop | hold | mean annual | mean sharpe | min sharpe | sharpe std | worst drawdown | positive folds | rank_ic | rank_icir | sharpe_p | pareto |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, (_, row) in enumerate(top.iterrows(), start=1):
        lines.append(
            "| {rank} | {universe} | {topk} | {n_drop} | {hold} | {annual} | {sharpe:.3f} | "
            "{min_sharpe:.3f} | {sharpe_std:.3f} | {dd} | {pos}/{folds} | {rank_ic:.4f} | {rank_icir:.4f} | {sharpe_p} | {pareto} |".format(
                rank=idx,
                universe=row["train_universe"],
                topk=int(row["topk"]),
                n_drop=int(row["n_drop"]),
                hold=int(row["hold_thresh"]),
                annual=pct(row["mean_annual_return"]),
                sharpe=row["mean_sharpe"],
                min_sharpe=row["min_sharpe"],
                sharpe_std=row["sharpe_std"],
                dd=pct(row["worst_max_drawdown"]),
                pos=int(row["positive_sharpe_folds"]),
                folds=int(row["folds"]),
                rank_ic=row["mean_rank_ic"],
                rank_icir=row["mean_rank_icir"],
                sharpe_p=f"{row['sharpe_ttest_pvalue']:.3f}" if not pd.isna(row.get("sharpe_ttest_pvalue", float("nan"))) else "nan",
                pareto="✓" if row.get("pareto_front", False) else "",
            )
        )

    best = summary.iloc[0]
    lines.extend(
        [
            "",
            "## Current Read",
            "",
            (
                f"The current robust winner is `{best['train_universe']}` training with "
                f"`topk={int(best['topk'])}, n_drop={int(best['n_drop'])}, "
                f"hold_thresh={int(best['hold_thresh'])}`. "
                f"It has mean Sharpe `{best['mean_sharpe']:.3f}`, min Sharpe `{best['min_sharpe']:.3f}`, "
                f"and worst drawdown `{pct(best['worst_max_drawdown'])}` across folds."
            ),
            "",
            "Treat this as a research candidate, not proof of live profitability. The decisive checks are fold stability, drawdown tolerance, and whether the same parameters remain good without re-optimizing each year.",
            "",
            "## Artifacts",
            "",
            f"- All fold rows: `{path.parent / 'walk_forward_all_results.csv'}`",
            f"- Aggregated summary: `{path.parent / 'walk_forward_summary.csv'}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_one_fold_universe(
    fold: "Fold",
    train_universe: str,
    args: "argparse.Namespace",
    out_dir: Path,
    run_id: str,
) -> "pd.DataFrame":
    """Train + backtest one (fold, train_universe) combination.

    Each fold writes its backtest CSV to an isolated path (no global file race).
    Returns a DataFrame with result rows annotated with fold metadata.
    """
    python = Path(args.python)
    configs_dir = out_dir / "configs"
    logs_dir = out_dir / "logs"
    fold_results_dir = out_dir / "fold_results"

    tag = f"wf_{train_universe}_{fold.name}_{run_id}"
    cfg_path = configs_dir / f"{tag}.yaml"
    train_config = getattr(args, "_train_config_dict", None)
    write_fold_config(cfg_path, fold, train_universe, train_config=train_config)
    if train_config:
        print(f"    (train-config: {args.train_config} merged into {cfg_path.name})", flush=True)

    print(f"\n=== Train {tag} ===", flush=True)
    before_train = datetime.now().timestamp()
    train_cmd = [
        str(python),
        "run_train.py",
        "--config",
        str(cfg_path),
        "--model",
        "lgbm",
        "--tag",
        tag,
    ]
    if not getattr(args, "with_extra_factors", False):
        train_cmd.append("--no-extra-factors")
    run_command(train_cmd, logs_dir / f"{tag}_train.log")
    model_path = newest_model_for_tag(tag, before_train)

    print(
        f"=== Backtest {tag} on {args.eval_market} {fold.test_start}..{fold.test_end} ===",
        flush=True,
    )
    fold_results_dir.mkdir(parents=True, exist_ok=True)
    dest = fold_results_dir / f"{tag}_on_{args.eval_market}.csv"

    backtest_cmd = [
        str(python),
        "run_backtest.py",
        "--config",
        str(cfg_path),
        "--model-path",
        str(model_path),
        "--market",
        args.eval_market,
        "--topk",
        args.topk,
        "--n-drop",
        args.n_drop,
        "--hold-thresh",
        args.hold_thresh,
        "--start",
        fold.test_start,
        "--end",
        fold.test_end,
        "--grid-workers",
        str(args.grid_workers),
        "--output-csv",       # ← isolated path avoids parallel race condition
        str(dest),
    ]
    if args.seeds:
        backtest_cmd.append("--seeds")
    if getattr(args, "export_attribution_inputs", False):
        backtest_cmd.extend(["--export-attribution-inputs", "--run-id", tag])
    run_command(backtest_cmd, logs_dir / f"{tag}_backtest.log")

    # run_backtest.py wrote directly to `dest` via --output-csv; read it.
    if not dest.exists():
        raise FileNotFoundError(
            f"Expected backtest CSV at {dest} but it was not created. "
            "Check the backtest log for errors."
        )

    frame = pd.read_csv(dest)
    frame.insert(0, "model_path", str(model_path.relative_to(REPO_ROOT)))
    frame.insert(0, "eval_market", args.eval_market)
    frame.insert(0, "train_universe", train_universe)
    frame.insert(0, "fold", fold.name)
    frame.insert(0, "test_end", fold.test_end)
    frame.insert(0, "test_start", fold.test_start)
    return frame


def run_validation(args: argparse.Namespace) -> Path:
    # Keep the venv launcher path intact. Resolving it follows the symlink to
    # the base interpreter and can drop the virtualenv's site-packages.
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "optimization_results" / f"walk_forward_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    folds: List[Fold] = load_folds(getattr(args, "folds_config", None))

    metadata = {
        "run_id": run_id,
        "args": vars(args),
        "folds": [fold.__dict__ for fold in folds],
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    all_results_path = out_dir / "walk_forward_all_results.csv"
    all_frames = []
    done_keys = set()
    if all_results_path.exists():
        existing = pd.read_csv(all_results_path)
        if not existing.empty:
            all_frames.append(existing)
            done_keys = {
                (str(row.fold), str(row.train_universe))
                for row in existing[["fold", "train_universe"]].drop_duplicates().itertuples(index=False)
            }
            print(f"Resuming from {all_results_path}: {len(done_keys)} fold×universe pairs already done", flush=True)
    train_universes = parse_csv(args.train_universes)
    combos = [
        (fold, universe)
        for fold in folds
        for universe in train_universes
        if (fold.name, universe) not in done_keys
    ]

    workers = max(1, args.workers)
    _write_lock = threading.Lock()

    def _save_partial(frames: list) -> None:
        """Persist partial results (called under lock)."""
        if not frames:
            return
        combined = pd.concat(frames, ignore_index=True)
        combined.to_csv(out_dir / "walk_forward_all_results.csv", index=False)
        summarize(combined).to_csv(out_dir / "walk_forward_summary.csv", index=False)

    if not combos:
        print("All requested fold×universe pairs are already complete; regenerating summary/report.", flush=True)
    elif workers == 1:
        for fold, train_universe in combos:
            frame = _run_one_fold_universe(fold, train_universe, args, out_dir, run_id)
            all_frames.append(frame)
            with _write_lock:
                _save_partial(all_frames)
    else:
        print(
            f"\nRunning {len(combos)} fold×universe combinations with {workers} parallel workers",
            flush=True,
        )
        with _cf.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_combo = {
                executor.submit(
                    _run_one_fold_universe, fold, universe, args, out_dir, run_id
                ): (fold, universe)
                for fold, universe in combos
            }
            for future in _cf.as_completed(future_to_combo):
                fold, universe = future_to_combo[future]
                try:
                    frame = future.result()
                    with _write_lock:
                        all_frames.append(frame)
                        _save_partial(all_frames)
                except Exception as exc:
                    print(
                        f"WARNING: fold={fold.name} universe={universe} FAILED: {exc}",
                        flush=True,
                    )

    results = pd.concat(all_frames, ignore_index=True)
    robust_weights = None
    if getattr(args, "robust_weights", None):
        import json as _json
        try:
            robust_weights = _json.loads(args.robust_weights)
        except Exception as exc:
            print(f"WARNING: could not parse --robust-weights JSON: {exc}", flush=True)
    summary = summarize(results, robust_weights=robust_weights)
    all_path = out_dir / "walk_forward_all_results.csv"
    summary_path = out_dir / "walk_forward_summary.csv"
    report_path = out_dir / "walk_forward_report.md"
    results.to_csv(all_path, index=False)
    summary.to_csv(summary_path, index=False)
    write_report(report_path, summary, results, args)
    print(f"\nReport saved: {report_path}", flush=True)
    return report_path


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Walk-forward validation for quant_ex")
    parser.add_argument("--python", default=str(DEFAULT_PYTHON if DEFAULT_PYTHON.exists() else sys.executable))
    parser.add_argument("--train-universes", default="csi300,csi800,csi1000")
    parser.add_argument("--eval-market", default="csi300")
    parser.add_argument("--topk", default="5,15,20")
    parser.add_argument("--n-drop", default="1,3")
    parser.add_argument("--hold-thresh", default="5,8,10")
    parser.add_argument("--seeds", action="store_true", help="Run multi-seed backtests for every strategy row")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of fold×universe pairs to run in parallel (default: 1 serial). "
             "Set to 2-3 on M3; each worker runs a full train+backtest subprocess chain.",
    )
    parser.add_argument(
        "--grid-workers",
        type=int,
        default=-1,
        help="Parallel workers for the backtest grid search inside each fold "
             "(-1 = all CPU cores, 1 = serial). Passed through to run_backtest.py.",
    )
    parser.add_argument(
        "--robust-weights",
        type=str,
        default=None,
        help="JSON string overriding robust_score coefficients, e.g. "
             "'{\"mean_sharpe\": 1.0, \"sharpe_std\": -0.3, \"min_sharpe\": 0.3, "
             "\"positive_sharpe_folds\": 0.1}'",
    )
    parser.add_argument(
        "--folds-config",
        type=str,
        default=None,
        help="Path to a YAML file defining custom fold definitions. "
             "Defaults to the built-in 7-fold schedule (2020-2026). "
             "See config/walk_forward_folds.yaml.example for the format.",
    )
    parser.add_argument(
        "--train-config",
        type=str,
        default=None,
        help="Path to a YAML config file whose contents are deep-merged into each "
             "fold's generated training config. Useful for injecting factor definitions "
             "(e.g. config/ablation_northbound.yaml). Fold-specific keys (market, dates) "
             "always take precedence over this file.",
    )
    parser.add_argument(
        "--with-extra-factors",
        action="store_true",
        help="Allow run_train.py to compute factors from the generated fold config. "
             "Default keeps historical WFV behavior by passing --no-extra-factors.",
    )
    parser.add_argument(
        "--export-attribution-inputs",
        action="store_true",
        help="Opt-in: ask each fold backtest to export attribution inputs using a fold-scoped run id.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Validate early so typos fail before the first long train.
    parse_csv(args.train_universes)
    parse_int_csv(args.topk)
    parse_int_csv(args.n_drop)
    parse_int_csv(args.hold_thresh)

    # Load --train-config once so every fold shares the same parsed dict.
    if args.train_config:
        tc_path = Path(args.train_config)
        if not tc_path.exists():
            parser.error(f"--train-config file not found: {tc_path}")
        with tc_path.open(encoding="utf-8") as fh:
            args._train_config_dict = yaml.safe_load(fh) or {}
        logger.info("--train-config loaded from %s (keys: %s)", tc_path, list(args._train_config_dict.keys()))
    else:
        args._train_config_dict = None

    run_validation(args)


if __name__ == "__main__":
    main()
