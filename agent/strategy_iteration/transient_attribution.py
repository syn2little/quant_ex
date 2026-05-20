from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def build_risk_transient_factor_attribution(
    *,
    run_id: str,
    portfolio_returns_csv: str | Path,
    risk_exposures_csv: str | Path,
    candidate_events_csv: str | Path | None = None,
) -> dict[str, Any]:
    """Build a diagnostic-only transient attribution report from local artifacts."""

    portfolio = pd.read_csv(portfolio_returns_csv)
    risk = pd.read_csv(risk_exposures_csv)
    merged = _merge_returns_and_risk(portfolio, risk)
    events = pd.read_csv(candidate_events_csv) if candidate_events_csv else pd.DataFrame()
    summary = _summary(merged)
    regimes = _risk_regimes(merged)
    event_attribution = _event_attribution(events)
    flags = _diagnostic_flags(summary, regimes, event_attribution)
    return {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "guardrail": "diagnostic_only_not_trading_signal",
        "inputs": {
            "portfolio_returns_csv": str(portfolio_returns_csv),
            "risk_exposures_csv": str(risk_exposures_csv),
            "candidate_events_csv": str(candidate_events_csv or ""),
        },
        "summary": summary,
        "risk_regimes": regimes,
        "event_attribution": event_attribution,
        "diagnostic_flags": flags,
        "next_action": "review_transient_bottlenecks_before_any_strategy_change",
    }


def transient_attribution_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Risk Transient Factor Attribution: {report.get('run_id')}",
        "",
        f"- Guardrail: {report.get('guardrail')}",
        f"- Next action: {report.get('next_action')}",
        "",
        "## Summary",
    ]
    for key, value in (report.get("summary") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Risk Regimes"])
    for name, values in (report.get("risk_regimes") or {}).items():
        stats = ", ".join(f"{key}={value}" for key, value in values.items())
        lines.append(f"- {name}: {stats}")
    lines.extend(["", "## Event Attribution"])
    for key, value in (report.get("event_attribution") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Diagnostic Flags"])
    lines.extend(f"- {item}" for item in report.get("diagnostic_flags") or [])
    return "\n".join(lines) + "\n"


def _merge_returns_and_risk(portfolio: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "portfolio_return", "benchmark_return"}
    missing = required - set(portfolio.columns)
    if missing:
        raise ValueError(f"portfolio returns missing required columns: {sorted(missing)}")
    missing = required - set(risk.columns)
    if missing:
        raise ValueError(f"risk exposures missing required columns: {sorted(missing)}")
    risk_cols = [col for col in risk.columns if col not in {"portfolio_return", "benchmark_return"}]
    merged = portfolio.merge(risk[risk_cols], on="date", how="left")
    merged["portfolio_return"] = merged["portfolio_return"].astype(float)
    merged["benchmark_return"] = merged["benchmark_return"].astype(float)
    if "residual_return" not in merged.columns:
        merged["residual_return"] = merged["portfolio_return"] - merged["benchmark_return"]
    merged["residual_return"] = merged["residual_return"].fillna(0.0).astype(float)
    if "drawdown" not in merged.columns:
        nav = (1.0 + merged["portfolio_return"]).cumprod()
        merged["drawdown"] = (nav - nav.cummax()) / nav.cummax()
    merged["drawdown"] = merged["drawdown"].fillna(0.0).astype(float)
    return merged


def _summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"days": 0, "mean_residual_return": 0.0, "hit_rate": 0.0, "worst_drawdown": 0.0}
    return {
        "days": int(len(frame)),
        "mean_portfolio_return": _round(frame["portfolio_return"].mean()),
        "mean_benchmark_return": _round(frame["benchmark_return"].mean()),
        "mean_residual_return": _round(frame["residual_return"].mean()),
        "hit_rate": _round((frame["residual_return"] > 0).mean()),
        "worst_drawdown": _round(frame["drawdown"].min()),
    }


def _risk_regimes(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame.empty:
        return {}
    stress_cutoff = -0.02
    regimes = {
        "all_days": frame,
        "positive_residual": frame[frame["residual_return"] > 0],
        "negative_residual": frame[frame["residual_return"] < 0],
        "drawdown_stress": frame[frame["drawdown"] <= stress_cutoff],
    }
    return {name: _regime_stats(subset) for name, subset in regimes.items()}


def _regime_stats(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"days": 0, "mean_residual_return": 0.0, "mean_drawdown": 0.0}
    return {
        "days": int(len(frame)),
        "mean_residual_return": _round(frame["residual_return"].mean()),
        "mean_drawdown": _round(frame["drawdown"].mean()),
        "residual_share": _round(frame["residual_return"].sum()),
    }


def _event_attribution(events: pd.DataFrame) -> dict[str, Any]:
    if events is None or events.empty:
        return {
            "events": 0,
            "missed_winner_count": 0,
            "accepted_loser_count": 0,
            "accepted_mean_forward_return": 0.0,
            "rejected_mean_forward_return": 0.0,
            "missed_winner_mean_forward_return": 0.0,
        }
    frame = events.copy()
    frame["decision"] = frame["decision"].astype(str)
    frame["forward_return"] = frame["forward_return"].fillna(0.0).astype(float)
    accepted = frame[frame["decision"] == "accepted"]
    rejected = frame[frame["decision"] == "rejected"]
    missed_winners = rejected[rejected["forward_return"] > 0]
    accepted_losers = accepted[accepted["forward_return"] < 0]
    return {
        "events": int(len(frame)),
        "accepted_count": int(len(accepted)),
        "rejected_count": int(len(rejected)),
        "missed_winner_count": int(len(missed_winners)),
        "accepted_loser_count": int(len(accepted_losers)),
        "accepted_mean_forward_return": _round(accepted["forward_return"].mean() if not accepted.empty else 0.0),
        "rejected_mean_forward_return": _round(rejected["forward_return"].mean() if not rejected.empty else 0.0),
        "missed_winner_mean_forward_return": _round(
            missed_winners["forward_return"].mean() if not missed_winners.empty else 0.0
        ),
    }


def _diagnostic_flags(
    summary: dict[str, Any],
    regimes: dict[str, dict[str, Any]],
    events: dict[str, Any],
) -> list[str]:
    flags: list[str] = []
    if summary.get("mean_residual_return", 0.0) < 0:
        flags.append("negative_average_residual_return")
    if regimes.get("drawdown_stress", {}).get("mean_residual_return", 0.0) < 0:
        flags.append("residual_underperforms_during_drawdown_stress")
    if events.get("missed_winner_count", 0) > events.get("accepted_loser_count", 0):
        flags.append("missed_winners_exceed_accepted_losers")
    if not flags:
        flags.append("no_primary_transient_bottleneck_detected")
    return flags


def _round(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    return round(float(value), 6)
