import pandas as pd

from scripts.analyze_phase8_gate_m008_risk_cap_counterfactual import build_report, build_sensitivity
from agent.strategy_iteration.risk_cap import RiskCapPolicy


def test_gate_m008_counterfactual_report_stays_diagnostic_only():
    frame = pd.DataFrame(
        {
            "date": ["2022-01-01", "2022-01-02", "2022-01-03", "2022-01-04"],
            "portfolio_return": [0.02, -0.04, 0.03, -0.02],
            "benchmark_return": [0.01, -0.01, 0.0, -0.005],
        }
    )

    summary, markdown = build_report(frame, "unit_run", 2, RiskCapPolicy())

    assert summary["decision_label"] == "diagnostic_only"
    assert summary["run_id"] == "unit_run"
    assert "Status: `diagnostic_only_not_trading_signal`." in markdown
    assert "it is not WFV evidence and not a trading signal" in markdown


def test_gate_m008_sensitivity_presets_have_stable_contract():
    frame = pd.DataFrame(
        {
            "date": ["2022-01-01", "2022-01-02", "2022-01-03", "2022-01-04"],
            "portfolio_return": [0.02, -0.04, 0.03, -0.02],
            "benchmark_return": [0.01, -0.01, 0.0, -0.005],
        }
    )

    rows = build_sensitivity(frame, "unit_run", 2)

    assert {row["preset"] for row in rows} == {
        "default_v0",
        "drawdown_15_cut",
        "drawdown_20_cut",
        "soft_dd15",
        "vol_only_high",
    }
    required = {
        "preset",
        "capped_total_return",
        "total_return_delta",
        "capped_max_drawdown",
        "max_drawdown_delta",
        "capped_ir",
        "tail_loss_delta",
        "positive_return_capture_delta",
        "negative_return_capture_delta",
        "cap_active_days",
        "avg_cap_multiplier",
    }
    assert all(required.issubset(row) for row in rows)
