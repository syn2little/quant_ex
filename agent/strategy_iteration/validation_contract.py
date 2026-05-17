from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from .schemas import MetricSnapshot, ValidationContractResult


METRIC_PRIORITY = (
    "robust_score",
    "information_ratio",
    "sharpe",
    "mean_sharpe",
    "annual_return",
)

BACKTEST_REQUIRED_FIELDS = ("topk", "n_drop", "hold_thresh", "sharpe", "max_drawdown")
BACKTEST_BENCHMARK_FIELDS = ("information_ratio", "tracking_error", "alpha", "beta")
WFV_SUMMARY_REQUIRED_FIELDS = (
    "folds",
    "mean_sharpe",
    "min_sharpe",
    "worst_max_drawdown",
    "positive_sharpe_folds",
)
WFV_ALL_RESULTS_REQUIRED_FIELDS = ("fold", "train_universe", "eval_market", "topk", "n_drop", "hold_thresh", "sharpe")


def read_csv_rows(csv_path: str | Path) -> list[dict[str, Any]]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def choose_rank_metric(columns: Iterable[str], requested: str | None = None) -> str:
    column_set = set(columns)
    if requested and requested in column_set:
        return requested
    for metric in METRIC_PRIORITY:
        if metric in column_set:
            return metric
    return next(iter(column_set), "")


def detect_result_kind(columns: Iterable[str], path: str | Path | None = None) -> str:
    column_set = set(columns)
    name = Path(path).name.lower() if path else ""
    if name == "walk_forward_summary.csv":
        return "walk_forward_summary"
    if "walk_forward" in name and "summary" in name:
        return "walk_forward_summary"
    if {"fold", "train_universe", "eval_market"} <= column_set:
        return "walk_forward_all_results"
    if {"folds", "mean_sharpe"} & column_set and {"min_sharpe", "worst_max_drawdown"} & column_set:
        return "walk_forward_summary"
    if {"topk", "n_drop", "hold_thresh"} & column_set and {"sharpe", "information_ratio"} & column_set:
        return "backtest"
    return "unknown"


def validate_result_contract(
    csv_path: str | Path,
    *,
    result_kind: str = "auto",
    rank_metric: str = "information_ratio",
) -> ValidationContractResult:
    path = Path(csv_path)
    rows = read_csv_rows(path)
    columns = list(rows[0].keys()) if rows else _read_header(path)
    detected_kind = detect_result_kind(columns, path)
    kind = detected_kind if result_kind in {"", "auto"} else result_kind
    if kind == "walk_forward":
        kind = "walk_forward_summary"

    required_fields = _required_fields(kind)
    missing = [field for field in required_fields if field not in columns]
    metric_used = choose_rank_metric(columns, rank_metric)
    warnings: list[str] = []

    if rows == []:
        warnings.append("CSV contains no data rows.")
    if detected_kind != "unknown" and result_kind not in {"", "auto", detected_kind, "walk_forward"}:
        warnings.append(f"Requested result_kind={result_kind} but detected {detected_kind}.")
    if rank_metric and rank_metric not in columns:
        warnings.append(f"Requested rank_metric={rank_metric} is absent; using {metric_used or 'none'}.")
    if kind == "backtest" and "information_ratio" not in columns:
        warnings.append("Backtest CSV is not benchmark-aware; promotion decisions cannot rely on IR.")
    if kind == "walk_forward_summary":
        for optional in ("sharpe_ttest_pvalue", "pareto_front", "robust_score"):
            if optional not in columns:
                warnings.append(f"WFV summary lacks optional promotion field: {optional}.")
    if kind == "unknown":
        warnings.append("Could not classify result CSV kind.")

    return ValidationContractResult(
        source_path=str(path),
        result_kind=kind,
        row_count=len(rows),
        columns=columns,
        rank_metric_requested=rank_metric,
        rank_metric_used=metric_used,
        required_fields=list(required_fields),
        missing_required_fields=missing,
        warnings=warnings,
        is_benchmark_aware=all(field in columns for field in BACKTEST_BENCHMARK_FIELDS),
        comparability_fields=_comparability_fields(rows[0] if rows else {}),
    )


def parse_validated_snapshot(
    csv_path: str | Path,
    *,
    result_kind: str = "auto",
    rank_metric: str = "information_ratio",
) -> MetricSnapshot:
    contract = validate_result_contract(csv_path, result_kind=result_kind, rank_metric=rank_metric)
    rows = read_csv_rows(csv_path)
    best_row = max(rows, key=lambda row: to_float(row.get(contract.rank_metric_used))) if rows and contract.rank_metric_used else {}
    return MetricSnapshot(
        source_path=str(Path(csv_path)),
        result_kind=contract.result_kind,
        rank_metric=contract.rank_metric_used,
        row_count=len(rows),
        best_row=dict(best_row),
    )


def _read_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _required_fields(result_kind: str) -> tuple[str, ...]:
    if result_kind == "backtest":
        return BACKTEST_REQUIRED_FIELDS
    if result_kind == "walk_forward_summary":
        return WFV_SUMMARY_REQUIRED_FIELDS
    if result_kind == "walk_forward_all_results":
        return WFV_ALL_RESULTS_REQUIRED_FIELDS
    return ()


def _comparability_fields(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "market",
        "train_universe",
        "eval_market",
        "benchmark",
        "deal_price",
        "open_cost",
        "close_cost",
        "min_cost",
        "topk",
        "n_drop",
        "hold_thresh",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in ("", None)}
