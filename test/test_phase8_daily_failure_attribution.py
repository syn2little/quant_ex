from pathlib import Path

import pandas as pd

from agent.strategy_iteration.daily_failure_attribution import (
    build_daily_failure_attribution,
    render_daily_failure_attribution_markdown,
)


def _write_csvs(tmp_path: Path):
    portfolio = tmp_path / "portfolio_returns.csv"
    risk = tmp_path / "risk_exposures.csv"
    events = tmp_path / "candidate_events.csv"

    pd.DataFrame(
        [
            {"date": "2022-01-03", "portfolio_return": 0.01, "benchmark_return": 0.0, "cost": 0.0, "excess_return": 0.01},
            {"date": "2022-01-04", "portfolio_return": -0.03, "benchmark_return": -0.01, "cost": 0.0, "excess_return": -0.02},
            {"date": "2022-01-05", "portfolio_return": -0.04, "benchmark_return": -0.01, "cost": 0.0, "excess_return": -0.03},
            {"date": "2022-01-06", "portfolio_return": 0.02, "benchmark_return": 0.0, "cost": 0.0, "excess_return": 0.02},
        ]
    ).to_csv(portfolio, index=False)
    pd.DataFrame(
        [
            {"date": "2022-01-03", "portfolio_return": 0.01, "benchmark_return": 0.0, "residual_return": 0.01, "drawdown": 0.0, "abs_residual_return": 0.01},
            {"date": "2022-01-04", "portfolio_return": -0.03, "benchmark_return": -0.01, "residual_return": -0.02, "drawdown": -0.03, "abs_residual_return": 0.02},
            {"date": "2022-01-05", "portfolio_return": -0.04, "benchmark_return": -0.01, "residual_return": -0.03, "drawdown": -0.07, "abs_residual_return": 0.03},
            {"date": "2022-01-06", "portfolio_return": 0.02, "benchmark_return": 0.0, "residual_return": 0.02, "drawdown": -0.05, "abs_residual_return": 0.02},
        ]
    ).to_csv(risk, index=False)
    pd.DataFrame(
        [
            {"date": "2022-01-04", "instrument": "AAA", "decision": "accepted", "rejection_reason": "", "score": 0.9, "rank": 1, "forward_return": -0.05},
            {"date": "2022-01-04", "instrument": "BBB", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.3, "rank": 50, "forward_return": 0.06},
            {"date": "2022-01-05", "instrument": "CCC", "decision": "accepted", "rejection_reason": "", "score": 0.8, "rank": 2, "forward_return": -0.04},
            {"date": "2022-01-05", "instrument": "DDD", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.4, "rank": 40, "forward_return": 0.03},
            {"date": "2022-01-06", "instrument": "EEE", "decision": "accepted", "rejection_reason": "", "score": 0.7, "rank": 3, "forward_return": 0.02},
        ]
    ).to_csv(events, index=False)
    return portfolio, risk, events


def _write_risk_memory_csvs(tmp_path: Path):
    portfolio = tmp_path / "memory_portfolio_returns.csv"
    risk = tmp_path / "memory_risk_exposures.csv"
    events = tmp_path / "memory_candidate_events.csv"

    pd.DataFrame(
        [
            {"date": "2022-01-03", "portfolio_return": 0.01, "benchmark_return": 0.0, "cost": 0.0, "excess_return": 0.01},
            {"date": "2022-01-04", "portfolio_return": -0.02, "benchmark_return": -0.005, "cost": 0.0, "excess_return": -0.015},
            {"date": "2022-01-05", "portfolio_return": -0.03, "benchmark_return": -0.005, "cost": 0.0, "excess_return": -0.025},
            {"date": "2022-01-06", "portfolio_return": -0.04, "benchmark_return": -0.005, "cost": 0.0, "excess_return": -0.035},
            {"date": "2022-01-07", "portfolio_return": -0.03, "benchmark_return": -0.005, "cost": 0.0, "excess_return": -0.025},
            {"date": "2022-01-10", "portfolio_return": -0.02, "benchmark_return": 0.0, "cost": 0.0, "excess_return": -0.02},
        ]
    ).to_csv(portfolio, index=False)
    pd.DataFrame(
        [
            {"date": "2022-01-03", "portfolio_return": 0.01, "benchmark_return": 0.0, "residual_return": 0.01, "drawdown": 0.0, "abs_residual_return": 0.01},
            {"date": "2022-01-04", "portfolio_return": -0.02, "benchmark_return": -0.005, "residual_return": -0.015, "drawdown": -0.02, "abs_residual_return": 0.015},
            {"date": "2022-01-05", "portfolio_return": -0.03, "benchmark_return": -0.005, "residual_return": -0.025, "drawdown": -0.05, "abs_residual_return": 0.025},
            {"date": "2022-01-06", "portfolio_return": -0.04, "benchmark_return": -0.005, "residual_return": -0.035, "drawdown": -0.09, "abs_residual_return": 0.035},
            {"date": "2022-01-07", "portfolio_return": -0.03, "benchmark_return": -0.005, "residual_return": -0.025, "drawdown": -0.12, "abs_residual_return": 0.025},
            {"date": "2022-01-10", "portfolio_return": -0.02, "benchmark_return": 0.0, "residual_return": -0.02, "drawdown": -0.14, "abs_residual_return": 0.02},
        ]
    ).to_csv(risk, index=False)
    pd.DataFrame(
        [
            {"date": "2022-01-06", "instrument": "AAA", "decision": "accepted", "rejection_reason": "", "score": 0.9, "rank": 1, "forward_return": -0.05},
            {"date": "2022-01-07", "instrument": "BBB", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.3, "rank": 50, "forward_return": 0.04},
            {"date": "2022-01-10", "instrument": "CCC", "decision": "accepted", "rejection_reason": "", "score": 0.8, "rank": 2, "forward_return": -0.03},
        ]
    ).to_csv(events, index=False)
    return portfolio, risk, events


def test_daily_failure_attribution_identifies_worst_drawdown_and_event_losses(tmp_path):
    portfolio, risk, events = _write_csvs(tmp_path)

    report = build_daily_failure_attribution(
        run_id="unit_failure",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        stress_drawdown_threshold=-0.05,
        top_loss_days=2,
    )

    assert report["guardrail"] == "diagnostic_only_not_trading_signal"
    assert report["summary"]["days"] == 4
    assert report["summary"]["worst_drawdown"] == -0.07
    assert report["worst_days"][0]["date"] == "2022-01-05"
    assert report["worst_days"][0]["accepted_loser_count"] == 1
    assert report["worst_days"][0]["missed_winner_count"] == 1
    assert report["stress_regime"]["days"] == 2
    assert report["event_summary"]["accepted_loser_count"] == 2
    assert report["event_summary"]["missed_winner_count"] == 2
    assert "absolute_risk_survival_issue" in report["diagnostic_flags"]
    assert report["next_action"] == "portfolio_risk_cap_over_signal_tuning"

    markdown = render_daily_failure_attribution_markdown(report)
    assert "diagnostic_only_not_trading_signal" in markdown
    assert "2022-01-05" in markdown
    assert "portfolio_risk_cap_over_signal_tuning" in markdown


def test_daily_failure_attribution_clamps_negative_top_loss_days(tmp_path):
    portfolio, risk, events = _write_csvs(tmp_path)

    report = build_daily_failure_attribution(
        run_id="unit_negative_top_loss_days",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        stress_drawdown_threshold=-0.05,
        top_loss_days=-1,
    )

    assert report["worst_days"] == []
    assert report["risk_memory_days"] == []


def test_daily_failure_attribution_adds_risk_memory_roughness_and_persistence(tmp_path):
    portfolio, risk, events = _write_risk_memory_csvs(tmp_path)

    report = build_daily_failure_attribution(
        run_id="unit_risk_memory",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        stress_drawdown_threshold=-0.05,
        top_loss_days=3,
        risk_memory_window=2,
        roughness_window=2,
        persistence_window=3,
        diagnostic_high_quantile=0.5,
    )

    diagnostics = report["risk_memory_diagnostics"]
    assert diagnostics["config"]["memory_window"] == 2
    assert diagnostics["summary"]["max_stress_memory_score"] > 0.09
    assert diagnostics["summary"]["max_consecutive_negative_portfolio_days"] == 5
    assert diagnostics["summary"]["max_rolling_negative_residual_share"] == 1.0
    assert diagnostics["bucket_comparison"]["high_memory"]["days"] == 3
    assert diagnostics["bucket_comparison"]["high_memory"]["mean_portfolio_return"] < diagnostics["bucket_comparison"]["other_memory"]["mean_portfolio_return"]
    assert diagnostics["bucket_comparison"]["high_roughness"]["mean_residual_return"] < 0
    assert diagnostics["bucket_comparison"]["high_persistence"]["worst_drawdown"] <= -0.12
    assert report["risk_memory_days"][0]["date"] == "2022-01-10"
    assert "risk_memory_stress_cluster" in report["diagnostic_flags"]
    assert "residual_roughness_loss_cluster" in report["diagnostic_flags"]
    assert "loss_persistence_cluster" in report["diagnostic_flags"]

    markdown = render_daily_failure_attribution_markdown(report)
    assert "## Risk Memory / Roughness / Persistence" in markdown
    assert "stress_memory_score" in markdown
    assert "risk_memory_stress_cluster" in markdown
