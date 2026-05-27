from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


GUARDRAIL = "diagnostic_only_not_trading_signal"


def _limit_count(value: int) -> int:
    return max(int(value), 0)


def build_factor_crowding_diagnostic(
    *,
    run_id: str,
    portfolio_returns_csv: str | Path,
    risk_exposures_csv: str | Path,
    candidate_events_csv: str | Path,
    stress_drawdown_threshold: float = -0.05,
    residual_quantile: float = 0.75,
    event_cluster_min_count: int = 5,
    top_days: int = 10,
) -> dict[str, Any]:
    """Build a diagnostic-only factor crowding / co-movement proxy report.

    The report intentionally uses only local attribution CSV contracts:
    portfolio returns, residual/drawdown risk exposures, and candidate events.
    It does not create a factor, trading signal, or data-ingestion path.
    """

    day_limit = _limit_count(top_days)
    portfolio = _load_csv(portfolio_returns_csv)
    risk = _load_csv(risk_exposures_csv)
    events = _load_csv(candidate_events_csv)

    portfolio_by_date = {_date_str(row["date"]): row for row in portfolio if row.get("date")}
    risk_by_date = {_date_str(row["date"]): row for row in risk if row.get("date")}
    event_by_date = _event_stats_by_date(events)
    dates = sorted(set(portfolio_by_date) | set(risk_by_date))
    orphan_event_dates = sorted(set(event_by_date) - set(dates))

    daily = _daily_rows(dates, portfolio_by_date, risk_by_date, event_by_date)
    abs_residuals = [row["abs_residual_return"] for row in daily]
    residual_cutoff = _quantile(abs_residuals, residual_quantile)

    stress_cluster_all = [
        row
        for row in daily
        if row["drawdown"] <= stress_drawdown_threshold
        and row["residual_return"] < 0
        and row["abs_residual_return"] >= residual_cutoff
    ]
    event_concentration_all = [
        row
        for row in daily
        if row["accepted_loser_count"] >= event_cluster_min_count
    ]
    missed_winner_cluster_all = [
        row
        for row in daily
        if row["missed_winner_count"] >= event_cluster_min_count
    ]

    stress_cluster_days = _rank_days(stress_cluster_all, "drawdown", reverse=False, limit=day_limit)
    event_concentration_days = _rank_days(
        event_concentration_all,
        "accepted_loser_count",
        reverse=True,
        limit=day_limit,
    )
    missed_winner_cluster_days = _rank_days(
        missed_winner_cluster_all,
        "missed_winner_count",
        reverse=True,
        limit=day_limit,
    )

    summary = _summary(
        daily=daily,
        residual_cutoff=residual_cutoff,
        stress_drawdown_threshold=stress_drawdown_threshold,
        stress_cluster_days=stress_cluster_all,
        event_concentration_days=event_concentration_all,
        missed_winner_cluster_days=missed_winner_cluster_all,
    )
    crowding_buckets = {
        "stress_cluster_days": stress_cluster_days,
        "event_concentration_days": event_concentration_days,
        "missed_winner_cluster_days": missed_winner_cluster_days,
    }
    flags = _diagnostic_flags(crowding_buckets)

    return {
        "run_id": run_id,
        "guardrail": GUARDRAIL,
        "inputs": {
            "portfolio_returns_csv": str(portfolio_returns_csv),
            "risk_exposures_csv": str(risk_exposures_csv),
            "candidate_events_csv": str(candidate_events_csv),
        },
        "summary": summary,
        "orphan_event_dates": orphan_event_dates,
        "crowding_buckets": crowding_buckets,
        "diagnostic_flags": flags,
        "next_action": "review_crowding_proxy_with_risk_memory_without_signal_promotion",
    }


def render_factor_crowding_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Factor Crowding Diagnostic: {report['run_id']}",
        "",
        "## Factor Crowding / Co-movement Diagnostic",
        f"- Guardrail: `{report['guardrail']}`",
        f"- Next action: `{report['next_action']}`",
        "",
        "This is a diagnostic-only read of local attribution artifacts. It is not alpha evidence, "
        "not a portfolio rule, and not a trading signal.",
        "",
        "## Summary",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {_fmt(value)}")

    lines.extend(["", "## Crowding Buckets"])
    _append_day_table(lines, "Stress Cluster Days", report["crowding_buckets"]["stress_cluster_days"])
    _append_day_table(lines, "Event Concentration Days", report["crowding_buckets"]["event_concentration_days"])
    _append_day_table(lines, "Missed Winner Cluster Days", report["crowding_buckets"]["missed_winner_cluster_days"])

    lines.extend(["", "## Diagnostic Flags"])
    for flag in report["diagnostic_flags"]:
        lines.append(f"- `{flag}`")

    orphan_dates = report.get("orphan_event_dates", [])
    if orphan_dates:
        lines.extend(["", "## Excluded Event-Only Dates"])
        lines.append(
            "These candidate-event dates were excluded because no portfolio/risk attribution row exists for the date."
        )
        for date in orphan_dates[:20]:
            lines.append(f"- {date}")

    lines.extend(["", "## Inputs"])
    for key, value in report.get("inputs", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _load_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _daily_rows(
    dates: list[str],
    portfolio_by_date: dict[str, dict[str, str]],
    risk_by_date: dict[str, dict[str, str]],
    event_by_date: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    nav = 1.0
    peak = 1.0
    for date in dates:
        portfolio = portfolio_by_date.get(date, {})
        risk = risk_by_date.get(date, {})
        portfolio_return = _float_from(risk, "portfolio_return", _float_from(portfolio, "portfolio_return"))
        benchmark_return = _float_from(risk, "benchmark_return", _float_from(portfolio, "benchmark_return"))
        residual_return = _float_from(
            risk,
            "residual_return",
            portfolio_return - benchmark_return,
        )
        nav *= 1.0 + portfolio_return
        peak = max(peak, nav)
        drawdown = _float_from(risk, "drawdown", (nav - peak) / peak if peak else 0.0)
        abs_residual_return = _float_from(risk, "abs_residual_return", abs(residual_return))
        event_stats = event_by_date.get(date, _empty_event_stats())
        row = {
            "date": date,
            "portfolio_return": _round(portfolio_return),
            "benchmark_return": _round(benchmark_return),
            "residual_return": _round(residual_return),
            "drawdown": _round(drawdown),
            "abs_residual_return": _round(abs_residual_return),
            "co_movement_proxy": int(_same_direction(portfolio_return, benchmark_return)),
            **_public_event_stats(event_stats),
        }
        rows.append(row)
    return rows


def _event_stats_by_date(events: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        if not event.get("date"):
            continue
        date = _date_str(event["date"])
        stats = grouped.setdefault(date, _empty_event_stats())
        decision = str(event.get("decision", "")).lower()
        forward_return = _float_from(event, "forward_return")
        stats["events"] += 1
        if decision == "accepted":
            stats["accepted_count"] += 1
            if forward_return < 0:
                stats["accepted_loser_count"] += 1
                stats["accepted_loser_forward_return_sum"] += forward_return
        else:
            stats["rejected_count"] += 1
            if forward_return > 0:
                stats["missed_winner_count"] += 1
                stats["missed_winner_forward_return_sum"] += forward_return
    for stats in grouped.values():
        stats["accepted_loser_mean_forward_return"] = _mean_from_sum(
            stats["accepted_loser_forward_return_sum"],
            stats["accepted_loser_count"],
        )
        stats["missed_winner_mean_forward_return"] = _mean_from_sum(
            stats["missed_winner_forward_return_sum"],
            stats["missed_winner_count"],
        )
        del stats["accepted_loser_forward_return_sum"]
        del stats["missed_winner_forward_return_sum"]
    return grouped


def _empty_event_stats() -> dict[str, Any]:
    return {
        "events": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "accepted_loser_count": 0,
        "missed_winner_count": 0,
        "accepted_loser_forward_return_sum": 0.0,
        "missed_winner_forward_return_sum": 0.0,
        "accepted_loser_mean_forward_return": 0.0,
        "missed_winner_mean_forward_return": 0.0,
    }


def _public_event_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "events": stats["events"],
        "accepted_count": stats["accepted_count"],
        "rejected_count": stats["rejected_count"],
        "accepted_loser_count": stats["accepted_loser_count"],
        "missed_winner_count": stats["missed_winner_count"],
        "accepted_loser_mean_forward_return": stats["accepted_loser_mean_forward_return"],
        "missed_winner_mean_forward_return": stats["missed_winner_mean_forward_return"],
    }


def _summary(
    *,
    daily: list[dict[str, Any]],
    residual_cutoff: float,
    stress_drawdown_threshold: float,
    stress_cluster_days: list[dict[str, Any]],
    event_concentration_days: list[dict[str, Any]],
    missed_winner_cluster_days: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted_loser_count = sum(row["accepted_loser_count"] for row in daily)
    missed_winner_count = sum(row["missed_winner_count"] for row in daily)
    return {
        "days": len(daily),
        "events": sum(row["events"] for row in daily),
        "accepted_count": sum(row["accepted_count"] for row in daily),
        "rejected_count": sum(row["rejected_count"] for row in daily),
        "accepted_loser_count": accepted_loser_count,
        "missed_winner_count": missed_winner_count,
        "mean_residual_return": _mean(row["residual_return"] for row in daily),
        "worst_drawdown": min((row["drawdown"] for row in daily), default=0.0),
        "stress_drawdown_threshold": _round(stress_drawdown_threshold),
        "high_abs_residual_cutoff": _round(residual_cutoff),
        "stress_days": sum(1 for row in daily if row["drawdown"] <= stress_drawdown_threshold),
        "stress_cluster_days": len(stress_cluster_days),
        "event_concentration_days": len(event_concentration_days),
        "missed_winner_cluster_days": len(missed_winner_cluster_days),
        "accepted_loser_top_day_share": _top_day_share(
            daily,
            "accepted_loser_count",
            accepted_loser_count,
        ),
        "missed_winner_top_day_share": _top_day_share(
            daily,
            "missed_winner_count",
            missed_winner_count,
        ),
    }


def _diagnostic_flags(crowding_buckets: dict[str, list[dict[str, Any]]]) -> list[str]:
    flags: list[str] = []
    if crowding_buckets["stress_cluster_days"]:
        flags.append("factor_crowding_proxy_stress_cluster")
    if crowding_buckets["event_concentration_days"]:
        flags.append("event_concentration_cluster")
    if crowding_buckets["missed_winner_cluster_days"]:
        flags.append("missed_winner_cluster")
    if not flags:
        flags.append("no_primary_crowding_proxy_detected")
    return flags


def _append_day_table(lines: list[str], title: str, rows: list[dict[str, Any]]) -> None:
    lines.extend(
        [
            "",
            f"### {title}",
            "| date | residual_return | drawdown | abs_residual | accepted_losers | missed_winners | events | co_movement_proxy |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if not rows:
        lines.append("| none | 0.000000 | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |")
        return
    for row in rows:
        lines.append(
            "| {date} | {residual_return:.6f} | {drawdown:.6f} | {abs_residual_return:.6f} | "
            "{accepted_loser_count} | {missed_winner_count} | {events} | {co_movement_proxy} |".format(**row)
        )


def _rank_days(
    rows: list[dict[str, Any]],
    key: str,
    *,
    reverse: bool,
    limit: int,
) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row[key], row["date"]), reverse=reverse)[:limit]


def _top_day_share(rows: list[dict[str, Any]], key: str, total: int) -> float:
    if total <= 0:
        return 0.0
    return _round(max((row[key] for row in rows), default=0) / total)


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    clipped = min(max(float(quantile), 0.0), 1.0)
    ordered = sorted(values)
    index = int((len(ordered) - 1) * clipped)
    return ordered[index]


def _same_direction(left: float, right: float) -> bool:
    if left == 0 or right == 0:
        return False
    return (left > 0 and right > 0) or (left < 0 and right < 0)


def _date_str(value: Any) -> str:
    return str(value)[:10]


def _float_from(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    if value in ("", None):
        return float(default)
    return float(value)


def _mean(values: Any) -> float:
    materialized = list(values)
    if not materialized:
        return 0.0
    return _round(sum(materialized) / len(materialized))


def _mean_from_sum(total: float, count: int) -> float:
    return _round(total / count) if count else 0.0


def _round(value: float) -> float:
    return round(float(value), 6)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)
