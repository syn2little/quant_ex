import pandas as pd

from agent.strategy_iteration.attribution_input_export import (
    build_candidate_events,
    build_portfolio_returns,
    build_risk_cap_diagnostics,
    build_risk_exposures,
    export_attribution_inputs,
)
from agent.strategy_iteration.attribution_inputs import assess_attribution_input_contract


def test_build_portfolio_returns_from_qlib_report():
    report = pd.DataFrame(
        {
            "return": [0.02, -0.01],
            "cost": [0.001, 0.002],
            "bench": [0.01, -0.005],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )

    output = build_portfolio_returns(report)

    assert list(output.columns) == ["date", "portfolio_return", "benchmark_return", "cost", "excess_return"]
    assert output.loc[0, "portfolio_return"] == 0.019
    assert output.loc[1, "benchmark_return"] == -0.005


def test_build_risk_exposures_adds_residual_and_drawdown_state():
    portfolio_returns = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "portfolio_return": [0.02, -0.05, 0.01],
            "benchmark_return": [0.01, -0.02, 0.0],
        }
    )

    output = build_risk_exposures(portfolio_returns)

    assert {"date", "portfolio_return", "benchmark_return", "residual_return", "drawdown"}.issubset(output.columns)
    assert output.loc[1, "residual_return"] == -0.03
    assert output["drawdown"].min() < 0


def test_build_candidate_events_from_signal_and_prices():
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-01-01")], ["SH600000", "SZ000001", "SH600519"]],
        names=["datetime", "instrument"],
    )
    signal = pd.Series([0.9, 0.6, 0.1], index=index, name="score")
    price_index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")], ["SH600000", "SZ000001", "SH600519"]],
        names=["datetime", "instrument"],
    )
    prices = pd.DataFrame({"real_close": [10, 20, 30, 11, 18, 27]}, index=price_index)

    events = build_candidate_events(signal, prices, topk=2, horizon=1)

    assert set(events["decision"]) == {"accepted", "rejected"}
    assert events.loc[events["instrument"] == "SH600000", "decision"].item() == "accepted"
    assert events.loc[events["instrument"] == "SH600519", "rejection_reason"].item() == "score_threshold"
    assert "forward_return" in events.columns


def test_build_candidate_events_preserves_instrument_datetime_index_order():
    index = pd.MultiIndex.from_product(
        [["SH600000", "SZ000001"], [pd.Timestamp("2026-01-01")]],
        names=["instrument", "datetime"],
    )
    signal = pd.Series([0.9, 0.1], index=index, name="score")
    price_index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")], ["SH600000", "SZ000001"]],
        names=["datetime", "instrument"],
    )
    prices = pd.DataFrame({"real_close": [10, 20, 11, 18]}, index=price_index)

    events = build_candidate_events(signal, prices, topk=1, horizon=1)

    assert set(events["instrument"]) == {"SH600000", "SZ000001"}
    assert events.loc[events["instrument"] == "SH600000", "decision"].item() == "accepted"


def test_build_risk_cap_diagnostics_uses_lagged_inputs_only():
    portfolio_returns = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "portfolio_return": [0.02, -0.04, 0.03, -0.02],
            "benchmark_return": [0.01, -0.01, 0.0, -0.005],
        }
    )

    rows, summary = build_risk_cap_diagnostics(portfolio_returns, run_id="unit", rolling_window=2)

    assert list(rows["date"]) == list(portfolio_returns["date"])
    assert rows.loc[0, "lagged_vol"] != rows.loc[0, "lagged_vol"]
    assert rows.loc[0, "lagged_drawdown"] != rows.loc[0, "lagged_drawdown"]
    assert rows.loc[2, "lagged_drawdown"] == (1.02 * 0.96) / 1.02 - 1.0
    assert set(["state", "multiplier", "pre_cap_return", "post_cap_return", "decision_label"]).issubset(rows.columns)
    assert set(summary["decision_label"]) == {"diagnostic_only"}
    assert summary.loc[0, "candidate_id"] == "unit"


def test_export_attribution_inputs_writes_contract_ready_files(tmp_path):
    report = pd.DataFrame(
        {"return": [0.02, -0.01], "cost": [0.0, 0.0], "bench": [0.01, -0.005]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )

    written = export_attribution_inputs(run_id="unit", output_dir=tmp_path / "backtest_results" / "agent_runs", report=report)
    contract = assess_attribution_input_contract(tmp_path)

    assert written["portfolio_returns"].exists()
    assert written["risk_exposures"].exists()
    assert "risk_cap_counterfactual" not in written
    assert contract["requirements"]["portfolio_returns"]["status"] == "ready"
    assert contract["requirements"]["risk_exposures"]["status"] == "ready"


def test_export_attribution_inputs_optionally_writes_risk_cap_diagnostics(tmp_path):
    report = pd.DataFrame(
        {
            "return": [0.02, -0.04, 0.03, -0.02],
            "cost": [0.0, 0.0, 0.0, 0.0],
            "bench": [0.01, -0.01, 0.0, -0.005],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
    )

    written = export_attribution_inputs(
        run_id="unit",
        output_dir=tmp_path / "backtest_results" / "agent_runs",
        report=report,
        export_risk_cap_diagnostics=True,
        risk_cap_rolling_window=2,
    )

    assert written["risk_cap_counterfactual"].exists()
    assert written["risk_cap_summary"].exists()
    rows = pd.read_csv(written["risk_cap_counterfactual"])
    summary = pd.read_csv(written["risk_cap_summary"])
    assert set(["state", "multiplier", "pre_cap_return", "post_cap_return", "decision_label"]).issubset(rows.columns)
    assert set(summary["decision_label"]) == {"diagnostic_only"}
