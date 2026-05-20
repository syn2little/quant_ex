import pandas as pd

from agent.strategy_iteration.transient_attribution import (
    build_risk_transient_factor_attribution,
    transient_attribution_to_markdown,
)


def test_build_risk_transient_factor_attribution_splits_regime_and_candidate_events(tmp_path):
    portfolio = tmp_path / "portfolio_returns.csv"
    risk = tmp_path / "risk_exposures.csv"
    events = tmp_path / "candidate_events.csv"
    pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "portfolio_return": [0.02, -0.03, 0.01, -0.01],
            "benchmark_return": [0.01, -0.01, 0.0, 0.0],
        }
    ).to_csv(portfolio, index=False)
    pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "portfolio_return": [0.02, -0.03, 0.01, -0.01],
            "benchmark_return": [0.01, -0.01, 0.0, 0.0],
            "residual_return": [0.01, -0.02, 0.01, -0.01],
            "drawdown": [0.0, -0.03, -0.02, -0.04],
        }
    ).to_csv(risk, index=False)
    pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"],
            "instrument": ["A", "B", "A", "B"],
            "decision": ["accepted", "rejected", "accepted", "rejected"],
            "rejection_reason": ["", "score_threshold", "", "score_threshold"],
            "score": [0.9, 0.2, 0.7, 0.6],
            "rank": [1, 2, 1, 2],
            "forward_return": [0.05, 0.08, -0.04, 0.02],
        }
    ).to_csv(events, index=False)

    report = build_risk_transient_factor_attribution(
        run_id="unit_transient",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
    )

    assert report["run_id"] == "unit_transient"
    assert report["guardrail"] == "diagnostic_only_not_trading_signal"
    assert report["summary"]["days"] == 4
    assert report["summary"]["mean_residual_return"] == -0.0025
    assert report["risk_regimes"]["drawdown_stress"]["days"] == 3
    assert report["event_attribution"]["missed_winner_count"] == 2
    assert report["event_attribution"]["accepted_loser_count"] == 1
    assert report["diagnostic_flags"]

    markdown = transient_attribution_to_markdown(report)
    assert "diagnostic_only_not_trading_signal" in markdown
    assert "missed_winner_count" in markdown
    assert "drawdown_stress" in markdown
