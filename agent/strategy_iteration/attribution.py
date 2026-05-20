from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any


def build_strategy_attribution_report(
    *,
    run_id: str,
    control_csv: str | Path,
    candidate_csv: str | Path,
    control_id: str,
    candidate_id: str,
) -> dict[str, Any]:
    """Compare two WFV-style CSVs and summarize where the candidate helps or hurts."""

    control_rows = _read_rows(control_csv)
    candidate_rows = _read_rows(candidate_csv)
    control_by_fold = {_fold_id(row, index): row for index, row in enumerate(control_rows)}
    candidate_by_fold = {_fold_id(row, index): row for index, row in enumerate(candidate_rows)}
    common_folds = [fold for fold in candidate_by_fold if fold in control_by_fold]
    fold_deltas = {
        fold: _fold_delta(control_by_fold[fold], candidate_by_fold[fold])
        for fold in common_folds
    }
    improved = [fold for fold, delta in fold_deltas.items() if delta.get("mean_sharpe_delta", 0.0) > 0]
    hurt = [fold for fold, delta in fold_deltas.items() if delta.get("mean_sharpe_delta", 0.0) < 0]
    summary = {
        "folds_compared": len(common_folds),
        "improved_folds": improved,
        "hurt_folds": hurt,
        "mean_sharpe_delta": _average(delta.get("mean_sharpe_delta", 0.0) for delta in fold_deltas.values()),
        "worst_drawdown_delta": _average(delta.get("worst_max_drawdown_delta", 0.0) for delta in fold_deltas.values()),
        "turnover_delta": _average(delta.get("turnover_delta", 0.0) for delta in fold_deltas.values()),
    }
    bottleneck = _classify_bottleneck(summary)
    return {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "control_id": control_id,
        "candidate_id": candidate_id,
        "control_csv": str(control_csv),
        "candidate_csv": str(candidate_csv),
        "fold_deltas": fold_deltas,
        "summary": summary,
        "bottleneck": bottleneck,
        "recommended_primary_experiment": _recommend_primary_experiment(candidate_id, bottleneck),
        "kill_criteria": [
            "Reject if the candidate worsens more folds than it improves.",
            "Reject if worst drawdown deteriorates by more than 5 percentage points.",
            "Reject if any same-model gain cannot be tied to WFV-grade fold evidence.",
        ],
    }


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Strategy Attribution Report: {report.get('run_id')}",
        "",
        f"- Control: {report.get('control_id')}",
        f"- Candidate: {report.get('candidate_id')}",
        f"- Bottleneck: {report.get('bottleneck')}",
        f"- Recommended primary experiment: {report.get('recommended_primary_experiment')}",
        "",
        "## Summary",
    ]
    summary = report.get("summary") or {}
    for key in ("folds_compared", "improved_folds", "hurt_folds", "mean_sharpe_delta", "worst_drawdown_delta", "turnover_delta"):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Kill Criteria"])
    lines.extend(f"- {item}" for item in report.get("kill_criteria") or [])
    lines.extend(["", "## Fold Deltas"])
    for fold, delta in (report.get("fold_deltas") or {}).items():
        lines.append(
            f"- {fold}: mean_sharpe_delta={delta.get('mean_sharpe_delta')}, "
            f"worst_max_drawdown_delta={delta.get('worst_max_drawdown_delta')}, "
            f"turnover_delta={delta.get('turnover_delta')}"
        )
    return "\n".join(lines) + "\n"


def _read_rows(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _fold_id(row: dict[str, Any], index: int) -> str:
    for key in ("fold", "year", "test_year", "name"):
        if row.get(key):
            return str(row[key])
    return str(index)


def _metric(row: dict[str, Any], *names: str) -> float:
    for name in names:
        if name in row and row.get(name) not in ("", None):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _fold_delta(control: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    return {
        "mean_sharpe_delta": round(_metric(candidate, "mean_sharpe", "sharpe") - _metric(control, "mean_sharpe", "sharpe"), 6),
        "min_sharpe_delta": round(_metric(candidate, "min_sharpe", "sharpe") - _metric(control, "min_sharpe", "sharpe"), 6),
        "worst_max_drawdown_delta": round(
            _metric(candidate, "worst_max_drawdown", "max_drawdown") - _metric(control, "worst_max_drawdown", "max_drawdown"),
            6,
        ),
        "turnover_delta": round(_metric(candidate, "turnover", "mean_turnover") - _metric(control, "turnover", "mean_turnover"), 6),
    }


def _average(values) -> float:
    items = list(values)
    if not items:
        return 0.0
    return round(sum(items) / len(items), 6)


def _classify_bottleneck(summary: dict[str, Any]) -> str:
    mean_delta = summary.get("mean_sharpe_delta", 0.0)
    dd_delta = summary.get("worst_drawdown_delta", 0.0)
    if mean_delta < -0.1 and dd_delta >= 0:
        return "return_repair"
    if mean_delta >= 0 and dd_delta < -0.05:
        return "stability_repair"
    return "mixed_tradeoff"


def _recommend_primary_experiment(candidate_id: str, bottleneck: str) -> str:
    if bottleneck == "return_repair":
        return f"Use {candidate_id} as the stability base and test a narrow exposure-scaling return repair."
    if bottleneck == "stability_repair":
        return f"Keep {candidate_id} only if a drawdown guard repairs the stability regression."
    return f"Compare {candidate_id} against the return control with one cheap diagnostic before any WFV spend."
