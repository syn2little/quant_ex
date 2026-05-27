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


def _consecutive_true(values: pd.Series) -> pd.Series:
    streak = 0
    streaks: list[int] = []
    for value in values.fillna(False).astype(bool):
        streak = streak + 1 if value else 0
        streaks.append(streak)
    return pd.Series(streaks, index=values.index, dtype="int64")


def _high_mask(series: pd.Series, quantile: float, require_positive: bool = True) -> pd.Series:
    if series.empty:
        return pd.Series(False, index=series.index)
    threshold = float(series.quantile(quantile))
    mask = series >= threshold
    if require_positive:
        mask &= series > 0
    return mask.fillna(False)


def _limit_count(value: int) -> int:
    return max(int(value), 0)


def _bucket_stats(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "days": int(len(frame)),
        "mean_portfolio_return": _safe_mean(frame["portfolio_return"]),
        "mean_residual_return": _safe_mean(frame["residual_return"]),
        "worst_drawdown": float(frame["drawdown"].min()) if len(frame) else 0.0,
        "mean_stress_memory_score": _safe_mean(frame["stress_memory_score"]),
        "mean_residual_roughness": _safe_mean(frame["residual_roughness"]),
        "mean_rolling_negative_portfolio_share": _safe_mean(frame["rolling_negative_portfolio_share"]),
        "accepted_loser_count": int(frame["accepted_loser_count"].sum()) if len(frame) else 0,
        "missed_winner_count": int(frame["missed_winner_count"].sum()) if len(frame) else 0,
    }


def _build_risk_memory_diagnostics(
    daily: pd.DataFrame,
    stress_drawdown_threshold: float,
    risk_memory_window: int,
    roughness_window: int,
    persistence_window: int,
    diagnostic_high_quantile: float,
    top_loss_days: int,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]], list[str]]:
    daily = daily.sort_values("date").reset_index(drop=True).copy()
    memory_window = max(int(risk_memory_window), 1)
    rough_window = max(int(roughness_window), 1)
    persist_window = max(int(persistence_window), 1)
    high_quantile = min(max(float(diagnostic_high_quantile), 0.0), 1.0)
    day_limit = _limit_count(top_loss_days)

    prior_drawdown = daily["drawdown"].shift(1).fillna(0.0)
    daily["prior_drawdown"] = prior_drawdown
    daily["rolling_drawdown_mean"] = prior_drawdown.rolling(memory_window, min_periods=1).mean()
    daily["rolling_drawdown_min"] = prior_drawdown.rolling(memory_window, min_periods=1).min()
    daily["stress_memory_score"] = (-daily["rolling_drawdown_mean"]).clip(lower=0.0)

    if "abs_residual_return" not in daily.columns:
        daily["abs_residual_return"] = daily["residual_return"].abs()
    daily["residual_roughness"] = daily["abs_residual_return"].rolling(rough_window, min_periods=1).mean()
    daily["residual_volatility"] = daily["residual_return"].rolling(rough_window, min_periods=1).std(ddof=0).fillna(0.0)

    negative_portfolio = daily["portfolio_return"] < 0
    negative_residual = daily["residual_return"] < 0
    daily["consecutive_negative_portfolio_days"] = _consecutive_true(negative_portfolio)
    daily["consecutive_negative_residual_days"] = _consecutive_true(negative_residual)
    daily["rolling_negative_portfolio_share"] = negative_portfolio.astype(float).rolling(persist_window, min_periods=1).mean()
    daily["rolling_negative_residual_share"] = negative_residual.astype(float).rolling(persist_window, min_periods=1).mean()

    high_memory_mask = _high_mask(daily["stress_memory_score"], high_quantile)
    high_roughness_mask = _high_mask(daily["residual_roughness"], high_quantile)
    high_persistence_mask = _high_mask(daily["rolling_negative_portfolio_share"], high_quantile)

    bucket_comparison = {
        "high_memory": _bucket_stats(daily[high_memory_mask]),
        "other_memory": _bucket_stats(daily[~high_memory_mask]),
        "high_roughness": _bucket_stats(daily[high_roughness_mask]),
        "other_roughness": _bucket_stats(daily[~high_roughness_mask]),
        "high_persistence": _bucket_stats(daily[high_persistence_mask]),
        "other_persistence": _bucket_stats(daily[~high_persistence_mask]),
    }
    summary = {
        "max_stress_memory_score": float(daily["stress_memory_score"].max()) if len(daily) else 0.0,
        "mean_stress_memory_score": _safe_mean(daily["stress_memory_score"]),
        "max_residual_roughness": float(daily["residual_roughness"].max()) if len(daily) else 0.0,
        "mean_residual_roughness": _safe_mean(daily["residual_roughness"]),
        "max_residual_volatility": float(daily["residual_volatility"].max()) if len(daily) else 0.0,
        "mean_residual_volatility": _safe_mean(daily["residual_volatility"]),
        "max_consecutive_negative_portfolio_days": int(daily["consecutive_negative_portfolio_days"].max()) if len(daily) else 0,
        "max_consecutive_negative_residual_days": int(daily["consecutive_negative_residual_days"].max()) if len(daily) else 0,
        "max_rolling_negative_portfolio_share": float(daily["rolling_negative_portfolio_share"].max()) if len(daily) else 0.0,
        "max_rolling_negative_residual_share": float(daily["rolling_negative_residual_share"].max()) if len(daily) else 0.0,
    }
    risk_memory_days_frame = daily.sort_values(
        ["stress_memory_score", "residual_roughness", "rolling_negative_portfolio_share", "drawdown"],
        ascending=[False, False, False, True],
    ).head(day_limit)
    risk_memory_days = [
        {
            "date": _to_date_str(row.date),
            "portfolio_return": float(row.portfolio_return),
            "residual_return": float(row.residual_return),
            "drawdown": float(row.drawdown),
            "stress_memory_score": float(row.stress_memory_score),
            "residual_roughness": float(row.residual_roughness),
            "residual_volatility": float(row.residual_volatility),
            "consecutive_negative_portfolio_days": int(row.consecutive_negative_portfolio_days),
            "rolling_negative_portfolio_share": float(row.rolling_negative_portfolio_share),
        }
        for row in risk_memory_days_frame.itertuples(index=False)
    ]

    flags = []
    high_memory = bucket_comparison["high_memory"]
    other_memory = bucket_comparison["other_memory"]
    if (
        high_memory["days"] > 0
        and high_memory["worst_drawdown"] <= stress_drawdown_threshold
        and high_memory["mean_portfolio_return"] < other_memory["mean_portfolio_return"]
    ):
        flags.append("risk_memory_stress_cluster")

    high_roughness = bucket_comparison["high_roughness"]
    other_roughness = bucket_comparison["other_roughness"]
    if (
        high_roughness["days"] > 0
        and high_roughness["mean_residual_return"] < 0
        and high_roughness["mean_residual_return"] < other_roughness["mean_residual_return"]
    ):
        flags.append("residual_roughness_loss_cluster")

    high_persistence = bucket_comparison["high_persistence"]
    other_persistence = bucket_comparison["other_persistence"]
    if (
        high_persistence["days"] > 0
        and high_persistence["worst_drawdown"] <= stress_drawdown_threshold
        and high_persistence["mean_portfolio_return"] < other_persistence["mean_portfolio_return"]
    ):
        flags.append("loss_persistence_cluster")

    diagnostics = {
        "config": {
            "memory_window": memory_window,
            "roughness_window": rough_window,
            "persistence_window": persist_window,
            "high_quantile": high_quantile,
        },
        "summary": summary,
        "bucket_comparison": bucket_comparison,
    }
    return daily, diagnostics, risk_memory_days, flags


def build_daily_failure_attribution(
    run_id: str,
    portfolio_returns_csv: str | Path,
    risk_exposures_csv: str | Path,
    candidate_events_csv: str | Path,
    stress_drawdown_threshold: float = -0.05,
    top_loss_days: int = 10,
    risk_memory_window: int = 20,
    roughness_window: int = 10,
    persistence_window: int = 10,
    diagnostic_high_quantile: float = 0.75,
) -> dict[str, Any]:
    day_limit = _limit_count(top_loss_days)
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
    daily, risk_memory_diagnostics, risk_memory_days, risk_memory_flags = _build_risk_memory_diagnostics(
        daily=daily,
        stress_drawdown_threshold=stress_drawdown_threshold,
        risk_memory_window=risk_memory_window,
        roughness_window=roughness_window,
        persistence_window=persistence_window,
        diagnostic_high_quantile=diagnostic_high_quantile,
        top_loss_days=top_loss_days,
    )

    worst_days_frame = daily.sort_values(
        ["drawdown", "portfolio_return", "residual_return"],
        ascending=[True, True, True],
    ).head(day_limit)
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
    diagnostic_flags.extend(flag for flag in risk_memory_flags if flag not in diagnostic_flags)
    if not diagnostic_flags:
        diagnostic_flags.append("no_primary_daily_bottleneck_detected")

    return {
        "run_id": run_id,
        "guardrail": "diagnostic_only_not_trading_signal",
        "summary": summary,
        "stress_regime": stress_regime,
        "event_summary": event_summary,
        "risk_memory_diagnostics": risk_memory_diagnostics,
        "worst_days": worst_days,
        "risk_memory_days": risk_memory_days,
        "diagnostic_flags": diagnostic_flags,
        "next_action": "portfolio_risk_cap_over_signal_tuning",
    }


def _fmt(value: float) -> str:
    return f"{value:.6f}"


def _append_key_values(lines: list[str], values: dict[str, Any]) -> None:
    for key, value in values.items():
        lines.append(f"- {key}: {_fmt(value) if isinstance(value, float) else value}")


def render_daily_failure_attribution_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Daily Failure Attribution: {report['run_id']}",
        "",
        f"- Guardrail: `{report['guardrail']}`",
        f"- Next action: `{report['next_action']}`",
        "",
        "## Summary",
    ]
    _append_key_values(lines, report["summary"])

    lines.extend(["", "## Stress Regime"])
    _append_key_values(lines, report["stress_regime"])

    lines.extend(["", "## Event Summary"])
    _append_key_values(lines, report["event_summary"])

    diagnostics = report.get("risk_memory_diagnostics")
    if diagnostics:
        lines.extend(["", "## Risk Memory / Roughness / Persistence", "", "### Config"])
        _append_key_values(lines, diagnostics["config"])

        lines.extend(["", "### Summary"])
        _append_key_values(lines, diagnostics["summary"])

        lines.extend(
            [
                "",
                "### Bucket Comparison",
                "| bucket | days | mean_portfolio_return | mean_residual_return | worst_drawdown | "
                "mean_stress_memory_score | mean_residual_roughness | mean_rolling_negative_portfolio_share | "
                "accepted_losers | missed_winners |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, row in diagnostics["bucket_comparison"].items():
            lines.append(
                "| {name} | {days} | {mean_portfolio_return:.6f} | {mean_residual_return:.6f} | "
                "{worst_drawdown:.6f} | {mean_stress_memory_score:.6f} | {mean_residual_roughness:.6f} | "
                "{mean_rolling_negative_portfolio_share:.6f} | {accepted_loser_count} | "
                "{missed_winner_count} |".format(name=name, **row)
            )

        lines.extend(
            [
                "",
                "### Highest Risk-Memory Days",
                "| date | portfolio_return | residual_return | drawdown | stress_memory_score | "
                "residual_roughness | residual_volatility | consecutive_negative_portfolio_days | "
                "rolling_negative_portfolio_share |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in report.get("risk_memory_days", []):
            lines.append(
                "| {date} | {portfolio_return:.6f} | {residual_return:.6f} | {drawdown:.6f} | "
                "{stress_memory_score:.6f} | {residual_roughness:.6f} | {residual_volatility:.6f} | "
                "{consecutive_negative_portfolio_days} | {rolling_negative_portfolio_share:.6f} |".format(**row)
            )

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
