"""Pure helpers for diagnostic-only portfolio risk-cap experiments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import stdev
from typing import Mapping, Sequence, cast


VALID_STATES = {"inactive", "watch", "cut", "recover", "blocked"}


@dataclass(frozen=True)
class RiskCapPolicy:
    """Deterministic thresholds for the v0 risk-cap state machine."""

    watch_vol: float = 0.18
    cut_vol: float = 0.25
    watch_drawdown: float = -0.05
    cut_drawdown: float = -0.10
    recover_vol: float = 0.16
    recover_drawdown: float = -0.03
    cut_multiplier: float = 0.5
    recover_multiplier: float = 0.75
    missing_input_state: str = "blocked"


def _is_valid_number(value: float | None) -> bool:
    return value is not None and isfinite(float(value))


def compute_drawdown(nav: Sequence[float]) -> list[float]:
    """Return peak-to-trough drawdown series as negative fractions."""

    drawdowns: list[float] = []
    peak: float | None = None
    for value in nav:
        if not _is_valid_number(value) or float(value) <= 0:
            raise ValueError("nav values must be positive finite numbers")
        current = float(value)
        peak = current if peak is None else max(peak, current)
        drawdowns.append(current / peak - 1.0)
    return drawdowns


def compute_rolling_vol(
    returns: Sequence[float],
    window: int,
    annualization: float = 252.0,
) -> list[float | None]:
    """Return annualized rolling sample volatility; early windows are None."""

    if window < 2:
        raise ValueError("window must be at least 2")
    if annualization <= 0:
        raise ValueError("annualization must be positive")

    vols: list[float | None] = []
    for idx in range(len(returns)):
        if idx + 1 < window:
            vols.append(None)
            continue
        sample = [float(v) for v in returns[idx + 1 - window : idx + 1]]
        if not all(_is_valid_number(v) for v in sample):
            vols.append(None)
            continue
        vols.append(stdev(sample) * sqrt(annualization))
    return vols


def compute_cap_state(
    lagged_vol: float | None,
    lagged_drawdown: float | None,
    previous_state: str,
    policy: RiskCapPolicy | None = None,
) -> str:
    """Compute next cap state from lagged risk inputs only."""

    policy = policy or RiskCapPolicy()
    if previous_state not in VALID_STATES:
        raise ValueError(f"unknown previous_state: {previous_state}")
    if policy.missing_input_state not in {"blocked", "inactive"}:
        raise ValueError("missing_input_state must be 'blocked' or 'inactive'")
    if not _is_valid_number(lagged_vol) or not _is_valid_number(lagged_drawdown):
        return policy.missing_input_state

    assert lagged_vol is not None
    assert lagged_drawdown is not None
    vol = float(lagged_vol)
    drawdown = float(lagged_drawdown)
    if vol >= policy.cut_vol or drawdown <= policy.cut_drawdown:
        return "cut"
    if previous_state in {"cut", "recover"}:
        if vol <= policy.recover_vol and drawdown >= policy.recover_drawdown:
            return "recover"
        return "cut"
    if vol >= policy.watch_vol or drawdown <= policy.watch_drawdown:
        return "watch"
    return "inactive"


def cap_multiplier_for_state(state: str, policy: RiskCapPolicy | None = None) -> float:
    policy = policy or RiskCapPolicy()
    if state == "cut":
        return policy.cut_multiplier
    if state == "recover":
        return policy.recover_multiplier
    if state in {"inactive", "watch"}:
        return 1.0
    if state == "blocked":
        return 1.0
    raise ValueError(f"unknown cap state: {state}")


def apply_cap_multiplier(weights: Mapping[str, float], multiplier: float) -> dict[str, float]:
    """Scale instrument weights without changing ranking or membership."""

    if not _is_valid_number(multiplier) or not 0.0 <= float(multiplier) <= 1.0:
        raise ValueError("multiplier must be finite and in [0, 1]")
    return {instrument: float(weight) * float(multiplier) for instrument, weight in weights.items()}


def compute_pre_post_counterfactual_returns(
    pre_cap_returns: Sequence[float],
    multipliers: Sequence[float],
    cash_return: float = 0.0,
) -> list[dict[str, float]]:
    """Compute post-cap returns from baseline returns and same-day multipliers."""

    if len(pre_cap_returns) != len(multipliers):
        raise ValueError("pre_cap_returns and multipliers must have the same length")
    if not _is_valid_number(cash_return):
        raise ValueError("cash_return must be finite")

    rows: list[dict[str, float]] = []
    for pre_return, multiplier in zip(pre_cap_returns, multipliers):
        if not _is_valid_number(pre_return) or not _is_valid_number(multiplier):
            raise ValueError("returns and multipliers must be finite")
        if not 0.0 <= float(multiplier) <= 1.0:
            raise ValueError("multipliers must be in [0, 1]")
        post_return = float(pre_return) * float(multiplier) + float(cash_return) * (1.0 - float(multiplier))
        rows.append({"pre_cap_return": float(pre_return), "post_cap_return": post_return})
    return rows


def compute_turnover_delta(
    pre_weights: Mapping[str, float],
    post_weights: Mapping[str, float],
) -> float:
    """Return absolute weight turnover induced by moving from pre to post weights."""

    instruments = set(pre_weights) | set(post_weights)
    return sum(abs(float(post_weights.get(inst, 0.0)) - float(pre_weights.get(inst, 0.0))) for inst in instruments)


def compute_risk_cap_counterfactual_series(
    pre_cap_returns: Sequence[float],
    lagged_vol: Sequence[float | None],
    lagged_drawdown: Sequence[float | None],
    policy: RiskCapPolicy | None = None,
    cash_return: float = 0.0,
) -> list[dict[str, float | str | None]]:
    """Simulate a diagnostic pre/post-cap return path from lagged risk inputs."""

    if not (len(pre_cap_returns) == len(lagged_vol) == len(lagged_drawdown)):
        raise ValueError("pre_cap_returns, lagged_vol, and lagged_drawdown must have the same length")
    if not _is_valid_number(cash_return):
        raise ValueError("cash_return must be finite")

    policy = policy or RiskCapPolicy()
    previous_state = "inactive"
    pre_cap_nav = 1.0
    post_cap_nav = 1.0
    rows: list[dict[str, float | str | None]] = []

    for pre_return, vol, drawdown in zip(pre_cap_returns, lagged_vol, lagged_drawdown):
        if not _is_valid_number(pre_return):
            raise ValueError("pre_cap_returns must be finite")
        state = compute_cap_state(vol, drawdown, previous_state, policy)
        multiplier = cap_multiplier_for_state(state, policy)
        post_return = float(pre_return) * multiplier + float(cash_return) * (1.0 - multiplier)
        pre_cap_nav *= 1.0 + float(pre_return)
        post_cap_nav *= 1.0 + post_return
        rows.append(
            {
                "state": state,
                "lagged_vol": None if vol is None else float(vol),
                "lagged_drawdown": None if drawdown is None else float(drawdown),
                "multiplier": multiplier,
                "pre_cap_return": float(pre_return),
                "post_cap_return": post_return,
                "pre_cap_nav": pre_cap_nav,
                "post_cap_nav": post_cap_nav,
            }
        )
        previous_state = state
    return rows


def summarize_risk_cap_counterfactual(
    rows: Sequence[Mapping[str, float | str | None]],
    fold_id: str,
    candidate_id: str = "gate_m008",
    decision_label: str = "diagnostic_only",
    periods_per_year: float = 252.0,
    benchmark_returns: Sequence[float] | None = None,
    pre_cap_turnover: Sequence[float] | None = None,
    post_cap_turnover: Sequence[float] | None = None,
) -> dict[str, float | int | str]:
    """Summarize a toy/precomputed risk-cap path without backtest integration."""

    if not rows:
        raise ValueError("rows must not be empty")
    if decision_label != "diagnostic_only":
        raise ValueError("risk-cap counterfactual summaries must be diagnostic_only")
    if not _is_valid_number(periods_per_year) or float(periods_per_year) <= 0:
        raise ValueError("periods_per_year must be positive")

    pre_returns: list[float] = []
    post_returns: list[float] = []
    pre_nav: list[float] = []
    post_nav: list[float] = []
    multipliers: list[float] = []
    state_counts = {state: 0 for state in VALID_STATES}

    for row in rows:
        state = str(row.get("state"))
        if state not in VALID_STATES:
            raise ValueError(f"unknown cap state in row: {state}")
        state_counts[state] += 1
        multiplier = row.get("multiplier")
        pre_return = row.get("pre_cap_return")
        post_return = row.get("post_cap_return")
        pre_value = row.get("pre_cap_nav")
        post_value = row.get("post_cap_nav")
        numeric_values = [multiplier, pre_return, post_return, pre_value, post_value]
        if not all(isinstance(value, (float, int)) and _is_valid_number(value) for value in numeric_values):
            raise ValueError("rows must contain finite multiplier, return, and nav fields")
        multiplier_value = cast(float | int, multiplier)
        pre_return_value = cast(float | int, pre_return)
        post_return_value = cast(float | int, post_return)
        pre_nav_value = cast(float | int, pre_value)
        post_nav_value = cast(float | int, post_value)
        multipliers.append(float(multiplier_value))
        pre_returns.append(float(pre_return_value))
        post_returns.append(float(post_return_value))
        pre_nav.append(float(pre_nav_value))
        post_nav.append(float(post_nav_value))

    if benchmark_returns is None:
        benchmark_values = [0.0] * len(rows)
    else:
        if len(benchmark_returns) != len(rows):
            raise ValueError("benchmark_returns must have the same length as rows")
        benchmark_values = [float(value) for value in benchmark_returns]
        if not all(_is_valid_number(value) for value in benchmark_values):
            raise ValueError("benchmark_returns must be finite")

    def _validated_average_turnover(values: Sequence[float] | None, label: str) -> float:
        if values is None:
            return 0.0
        if len(values) != len(rows):
            raise ValueError(f"{label} must have the same length as rows")
        turnover_values = [float(value) for value in values]
        if not all(_is_valid_number(value) and value >= 0.0 for value in turnover_values):
            raise ValueError(f"{label} must contain non-negative finite values")
        return sum(turnover_values) / len(turnover_values)

    pre_drawdowns = compute_drawdown(pre_nav)
    post_drawdowns = compute_drawdown(post_nav)
    baseline_active_returns = [pre - benchmark for pre, benchmark in zip(pre_returns, benchmark_values)]
    capped_active_returns = [post - benchmark for post, benchmark in zip(post_returns, benchmark_values)]
    baseline_active_stdev = stdev(baseline_active_returns) if len(baseline_active_returns) >= 2 else 0.0
    capped_active_stdev = stdev(capped_active_returns) if len(capped_active_returns) >= 2 else 0.0
    periods = len(rows)
    annualization_power = float(periods_per_year) / periods
    baseline_positive_capture = sum(max(0.0, value) for value in pre_returns)
    capped_positive_capture = sum(max(0.0, value) for value in post_returns)
    baseline_negative_capture = sum(min(0.0, value) for value in pre_returns)
    capped_negative_capture = sum(min(0.0, value) for value in post_returns)
    summary = {
        "candidate_id": candidate_id,
        "fold_id": fold_id,
        "baseline_total_return": pre_nav[-1] - 1.0,
        "capped_total_return": post_nav[-1] - 1.0,
        "baseline_annualized_return": pre_nav[-1] ** annualization_power - 1.0,
        "capped_annualized_return": post_nav[-1] ** annualization_power - 1.0,
        "total_return_delta": post_nav[-1] - pre_nav[-1],
        "baseline_max_drawdown": min(pre_drawdowns),
        "capped_max_drawdown": min(post_drawdowns),
        "max_drawdown_delta": min(post_drawdowns) - min(pre_drawdowns),
        "baseline_vol": stdev(pre_returns) if len(pre_returns) >= 2 else 0.0,
        "capped_vol": stdev(post_returns) if len(post_returns) >= 2 else 0.0,
        "baseline_ir": 0.0 if baseline_active_stdev == 0.0 else sum(baseline_active_returns) / len(baseline_active_returns) / baseline_active_stdev,
        "capped_ir": 0.0 if capped_active_stdev == 0.0 else sum(capped_active_returns) / len(capped_active_returns) / capped_active_stdev,
        "baseline_turnover": _validated_average_turnover(pre_cap_turnover, "pre_cap_turnover"),
        "capped_turnover": _validated_average_turnover(post_cap_turnover, "post_cap_turnover"),
        "tail_loss_delta": sum(sorted(post_returns)[: min(5, len(post_returns))])
        - sum(sorted(pre_returns)[: min(5, len(pre_returns))]),
        "baseline_positive_return_capture": baseline_positive_capture,
        "capped_positive_return_capture": capped_positive_capture,
        "positive_return_capture_delta": capped_positive_capture - baseline_positive_capture,
        "baseline_negative_return_capture": baseline_negative_capture,
        "capped_negative_return_capture": capped_negative_capture,
        "negative_return_capture_delta": capped_negative_capture - baseline_negative_capture,
        "cap_active_days": sum(1 for value in multipliers if value < 1.0),
        "cap_cut_days": state_counts["cut"],
        "cap_recover_days": state_counts["recover"],
        "cut_to_recover_ratio": state_counts["cut"] / state_counts["recover"] if state_counts["recover"] else 0.0,
        "cap_blocked_days": state_counts["blocked"],
        "avg_cap_multiplier": sum(multipliers) / len(multipliers),
        "worst_5_day_pre_cap": sum(sorted(pre_returns)[: min(5, len(pre_returns))]),
        "worst_5_day_post_cap": sum(sorted(post_returns)[: min(5, len(post_returns))]),
        "decision_label": decision_label,
    }
    return summary
