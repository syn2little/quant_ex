from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .evaluator import COMPARISON_METRICS
from .schemas import MetricSnapshot, PromotionReport
from .validation_contract import parse_validated_snapshot, to_float, validate_result_contract


def build_promotion_report(
    *,
    run_id: str,
    result_csv: str | Path,
    control_csv: str | Path | None = None,
    result_kind: str = "auto",
    rank_metric: str = "information_ratio",
    require_wfv_for_promotion: bool = True,
) -> PromotionReport:
    result_contract = validate_result_contract(result_csv, result_kind=result_kind, rank_metric=rank_metric)
    result = parse_validated_snapshot(result_csv, result_kind=result_kind, rank_metric=rank_metric)
    control_contract = (
        validate_result_contract(control_csv, result_kind="auto", rank_metric=rank_metric)
        if control_csv
        else None
    )
    control = (
        parse_validated_snapshot(control_csv, result_kind="auto", rank_metric=rank_metric)
        if control_csv
        else None
    )
    deltas = _deltas(result, control)
    gates = _build_gates(
        result,
        result_contract=result_contract,
        control=control,
        control_contract=control_contract,
        deltas=deltas,
        require_wfv_for_promotion=require_wfv_for_promotion,
    )
    promotion_blocked = any(not gate["passed"] for gate in gates if gate.get("severity") == "blocker")
    decision = _decision(result, result_contract, deltas, promotion_blocked)
    warnings = list(result_contract.warnings)
    if control_contract:
        warnings.extend([f"Control: {item}" for item in control_contract.warnings])
    warnings.extend(_comparability_warnings(result_contract, control_contract))
    status = "promotable" if decision == "promote" else "not_promotable" if promotion_blocked else decision
    return PromotionReport(
        run_id=run_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        decision=decision,
        promotion_status=status,
        evidence_level="wfv" if result_contract.result_kind == "walk_forward_summary" else "backtest_filter",
        result=result,
        result_contract=result_contract,
        control=control,
        control_contract=control_contract,
        deltas=deltas,
        gates=gates,
        warnings=warnings,
        recommendation=_recommendation(decision, result_contract),
    )


def _deltas(result: MetricSnapshot, control: MetricSnapshot | None) -> dict[str, float]:
    if not control:
        return {}
    deltas: dict[str, float] = {}
    for metric in COMPARISON_METRICS:
        if metric in result.best_row and metric in control.best_row:
            deltas[metric] = to_float(result.best_row.get(metric)) - to_float(control.best_row.get(metric))
    return deltas


def _build_gates(
    result: MetricSnapshot,
    *,
    result_contract,
    control: MetricSnapshot | None,
    control_contract,
    deltas: dict[str, float],
    require_wfv_for_promotion: bool,
) -> list[dict[str, Any]]:
    gates = [
        _gate(
            "contract_complete",
            result_contract.ok,
            "CSV classified and required fields are present.",
            severity="blocker",
        ),
        _gate(
            "rank_metric_policy",
            result.rank_metric == "information_ratio" or result_contract.result_kind == "walk_forward_summary",
            f"Rank metric used: {result.rank_metric}.",
            severity="warning",
        ),
    ]
    is_wfv = result_contract.result_kind == "walk_forward_summary"
    gates.append(
        _gate(
            "wfv_required_for_promotion",
            is_wfv or not require_wfv_for_promotion,
            "Only WFV summary evidence can produce a promote decision.",
            severity="blocker",
        )
    )
    if is_wfv:
        mean_sharpe = _metric(result, "mean_sharpe", "sharpe") or 0.0
        min_sharpe = _metric(result, "min_sharpe")
        pvalue = _metric(result, "sharpe_ttest_pvalue")
        worst_dd = _metric(result, "worst_max_drawdown")
        gates.extend(
            [
                _gate("wfv_mean_sharpe", mean_sharpe >= 0.9, f"mean_sharpe={mean_sharpe:.4f}", severity="blocker"),
                _gate(
                    "wfv_min_sharpe",
                    min_sharpe is None or min_sharpe >= 0,
                    f"min_sharpe={min_sharpe if min_sharpe is not None else 'missing'}",
                    severity="blocker",
                ),
                _gate(
                    "wfv_pvalue",
                    pvalue is None or pvalue <= 0.3,
                    f"sharpe_ttest_pvalue={pvalue if pvalue is not None else 'missing'}",
                    severity="warning" if pvalue is None else "blocker",
                ),
                _gate(
                    "wfv_drawdown",
                    worst_dd is None or worst_dd >= -0.35,
                    f"worst_max_drawdown={worst_dd if worst_dd is not None else 'missing'}",
                    severity="blocker",
                ),
            ]
        )
    if control:
        rank_delta = deltas.get(result.rank_metric)
        sharpe_delta = deltas.get("sharpe", deltas.get("mean_sharpe"))
        drawdown_delta = deltas.get("max_drawdown", deltas.get("worst_max_drawdown"))
        gates.extend(
            [
                _gate(
                    "control_rank_delta",
                    rank_delta is None or rank_delta >= -0.02,
                    f"{result.rank_metric} delta={rank_delta if rank_delta is not None else 'n/a'}",
                    severity="blocker",
                ),
                _gate(
                    "control_sharpe_delta",
                    sharpe_delta is None or sharpe_delta >= -0.1,
                    f"sharpe delta={sharpe_delta if sharpe_delta is not None else 'n/a'}",
                    severity="blocker",
                ),
                _gate(
                    "control_drawdown_delta",
                    drawdown_delta is None or drawdown_delta >= -0.05,
                    f"drawdown delta={drawdown_delta if drawdown_delta is not None else 'n/a'}",
                    severity="blocker",
                ),
            ]
        )
    if control_contract:
        gates.append(
            _gate(
                "control_contract_complete",
                control_contract.ok,
                "Control CSV classified and required fields are present.",
                severity="blocker",
            )
        )
    return gates


def _decision(result: MetricSnapshot, result_contract, deltas: dict[str, float], promotion_blocked: bool) -> str:
    if result.row_count == 0 or not result_contract.ok:
        return "reject"
    if result_contract.result_kind != "walk_forward_summary":
        rank_delta = deltas.get(result.rank_metric, 0.0)
        sharpe_delta = deltas.get("sharpe", 0.0)
        if deltas and (rank_delta < -0.1 or sharpe_delta < -0.1):
            return "reject"
        return "compare_next"
    if promotion_blocked:
        return "compare_next"
    return "promote"


def _metric(snapshot: MetricSnapshot, *names: str) -> float | None:
    for name in names:
        if name in snapshot.best_row:
            return to_float(snapshot.best_row.get(name))
    return None


def _gate(name: str, passed: bool, detail: str, *, severity: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail, "severity": severity}


def _comparability_warnings(result_contract, control_contract) -> list[str]:
    if not control_contract:
        return ["No control CSV supplied; promotion decision is conservative."]
    warnings: list[str] = []
    result_fields = result_contract.comparability_fields
    control_fields = control_contract.comparability_fields
    for key in ("market", "train_universe", "eval_market", "benchmark", "deal_price", "open_cost", "close_cost", "min_cost"):
        if key in result_fields and key in control_fields and str(result_fields[key]) != str(control_fields[key]):
            warnings.append(f"Comparability mismatch for {key}: result={result_fields[key]} control={control_fields[key]}.")
    return warnings


def _recommendation(decision: str, result_contract) -> str:
    if decision == "promote":
        return "WFV-grade evidence clears the configured gates; review manually before updating strategy candidates."
    if decision == "compare_next":
        if result_contract.result_kind != "walk_forward_summary":
            return "Backtest evidence is useful as a filter only; run control-matched WFV before promotion."
        return "WFV evidence is mixed; keep as compare_next and inspect blocked gates before spending more budget."
    return "Reject or redesign this candidate before rerunning; do not promote from the current evidence."
