from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _to_date_str(value: Any) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _safe_mean(series: pd.Series) -> float:
    return float(series.mean()) if not series.empty else 0.0


def _load_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def build_daily_failure_attribution(
    run_id: str,
    portfolio_returns_csv: str | Path,
    risk_exposures_csv: str | Path,
    candidate_events_csv: str | Path,
    stress_drawdown_threshold: float = -0.05,
    top_loss_days: int = 10,
) -> dict[str, Any]:
    portfolio = _load_csv(portfolio_returns_csv)
    risk = _load_csv(risk_exposures_csv)
    events = _load_csv(candidate_events_csv)

    accepted = events[events["decision"].astype(str).str.lower() == "accepted"].copy()
    rejected = events[events["decision"].astype(str).str.lower() != "accepted"].copy()
    accepted_losers = accepted[accepted["forward_return"] < 0]
    missed_winners = rejected[rejected["forward_return"] > 0]

    event_by_day = events.groupby("date").agg(events=("instrument", "count")).reset_index()
    accepted_losers_by_day = accepted_losers.groupby("date").agg(
        accepted_loser_count=("instrument", "count"),
        accepted_loser_mean_forward_return=("forward_return", "mean"),
    ).reset_index()
    missed_winners_by_day = missed_winners.groupby("date").agg(
        missed_winner_count=("instrument", "count"),
        missed_winner_mean_forward_return=("forward_return", "mean"),
    ).reset_index()

    daily = risk.merge(portfolio[["date", "cost", "excess_return"]], on="date", how="left")
    daily = daily.merge(event_by_day, on="date", how="left")
    daily = daily.merge(accepted_losers_by_day, on="date", how="left")
    daily = daily.merge(missed_winners_by_day, on="date", how="left")
    for column in ["events", "accepted_loser_count", "missed_winner_count"]:
        daily[column] = daily[column].fillna(0).astype(int)
    for column in ["accepted_loser_mean_forward_return", "missed_winner_mean_forward_return"]:
        daily[column] = daily[column].fillna(0.0)

    worst_days_frame = daily.sort_values(
        ["drawdown", "portfolio_return", "residual_return"],
        ascending=[True, True, True],
    ).head(top_loss_days)
    worst_days = [
        {
            "date": _to_date_str(row.date),
            "portfolio_return": float(row.portfolio_return),
            "benchmark_return": float(row.benchmark_return),
            "residual_return": float(row.residual_return),
            "drawdown": float(row.drawdown),
            "accepted_loser_count": int(row.accepted_loser_count),
            "missed_winner_count": int(row.missed_winner_count),
            "events": int(row.events),
        }
        for row in worst_days_frame.itertuples(index=False)
    ]

    stress = daily[daily["drawdown"] <= stress_drawdown_threshold]
    event_summary = {
        "events": int(len(events)),
        "accepted_count": int(len(accepted)),
        "rejected_count": int(len(rejected)),
        "accepted_loser_count": int(len(accepted_losers)),
        "missed_winner_count": int(len(missed_winners)),
        "accepted_mean_forward_return": _safe_mean(accepted["forward_return"]),
        "rejected_mean_forward_return": _safe_mean(rejected["forward_return"]),
        "accepted_loser_mean_forward_return": _safe_mean(accepted_losers["forward_return"]),
        "missed_winner_mean_forward_return": _safe_mean(missed_winners["forward_return"]),
    }
    summary = {
        "days": int(len(daily)),
        "mean_portfolio_return": _safe_mean(daily["portfolio_return"]),
        "mean_benchmark_return": _safe_mean(daily["benchmark_return"]),
        "mean_residual_return": _safe_mean(daily["residual_return"]),
        "hit_rate": float((daily["portfolio_return"] > 0).mean()) if len(daily) else 0.0,
        "worst_drawdown": float(daily["drawdown"].min()) if len(daily) else 0.0,
        "worst_portfolio_return": float(daily["portfolio_return"].min()) if len(daily) else 0.0,
    }
    stress_regime = {
        "threshold": float(stress_drawdown_threshold),
        "days": int(len(stress)),
        "mean_portfolio_return": _safe_mean(stress["portfolio_return"]),
        "mean_residual_return": _safe_mean(stress["residual_return"]),
        "accepted_loser_count": int(stress["accepted_loser_count"].sum()) if not stress.empty else 0,
        "missed_winner_count": int(stress["missed_winner_count"].sum()) if not stress.empty else 0,
    }

    diagnostic_flags = []
    if summary["worst_drawdown"] <= stress_drawdown_threshold:
        diagnostic_flags.append("absolute_risk_survival_issue")
    if stress_regime["mean_residual_return"] < 0:
        diagnostic_flags.append("stress_residual_underperformance")
    if event_summary["missed_winner_count"] > event_summary["accepted_loser_count"]:
        diagnostic_flags.append("missed_winners_exceed_accepted_losers")
    if event_summary["accepted_loser_count"] > 0:
        diagnostic_flags.append("accepted_losers_present")
    if not diagnostic_flags:
        diagnostic_flags.append("no_primary_daily_bottleneck_detected")

    return {
        "run_id": run_id,
        "guardrail": "diagnostic_only_not_trading_signal",
        "summary": summary,
        "stress_regime": stress_regime,
        "event_summary": event_summary,
        "worst_days": worst_days,
        "diagnostic_flags": diagnostic_flags,
        "next_action": "portfolio_risk_cap_over_signal_tuning",
    }


def _fmt(value: float) -> str:
    return f"{value:.6f}"


def render_daily_failure_attribution_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Daily Failure Attribution: {report['run_id']}",
        "",
        f"- Guardrail: `{report['guardrail']}`",
        f"- Next action: `{report['next_action']}`",
        "",
        "## Summary",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {_fmt(value) if isinstance(value, float) else value}")

    lines.extend(["", "## Stress Regime"])
    for key, value in report["stress_regime"].items():
        lines.append(f"- {key}: {_fmt(value) if isinstance(value, float) else value}")

    lines.extend(["", "## Event Summary"])
    for key, value in report["event_summary"].items():
        lines.append(f"- {key}: {_fmt(value) if isinstance(value, float) else value}")

    lines.extend([
        "",
        "## Worst Drawdown Days",
        "| date | portfolio_return | benchmark_return | residual_return | drawdown | accepted_losers | missed_winners | events |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in report["worst_days"]:
        lines.append(
            "| {date} | {portfolio_return:.6f} | {benchmark_return:.6f} | {residual_return:.6f} | "
            "{drawdown:.6f} | {accepted_loser_count} | {missed_winner_count} | {events} |".format(**row)
        )

    lines.extend(["", "## Diagnostic Flags"])
    for flag in report["diagnostic_flags"]:
        lines.append(f"- `{flag}`")
    lines.append("")
    return "\n".join(lines)
