from pathlib import Path

from agent.strategy_iteration.attribution_inputs import (
    assess_attribution_input_contract,
    contract_to_markdown,
)
from agent.strategy_iteration.context import build_project_context


def write_csv(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_attribution_input_contract_detects_ready_local_artifacts(tmp_path):
    write_csv(
        tmp_path / "backtest_results" / "portfolio_returns.csv",
        "date,portfolio_return,benchmark_return,position_count\n2026-01-01,0.01,0.004,15\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "risk_exposures.csv",
        "date,portfolio_return,benchmark_return,market_exposure,size_exposure,value_exposure\n2026-01-01,0.01,0.004,0.8,0.1,-0.2\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "candidate_events.csv",
        "date,instrument,decision,rejection_reason,forward_return\n2026-01-01,SH600000,rejected,risk_limit,-0.03\n",
    )

    report = assess_attribution_input_contract(tmp_path)

    assert report["overall_status"] == "ready_for_transient_diagnostic"
    assert report["requirements"]["portfolio_returns"]["status"] == "ready"
    assert report["requirements"]["risk_exposures"]["status"] == "ready"
    assert report["requirements"]["candidate_events"]["status"] == "ready"
    assert report["requirements"]["risk_cap_counterfactual"]["status"] == "missing_artifact"
    assert report["optional_capabilities"]["risk_cap_counterfactual"]["status"] == "missing_optional_artifact"
    assert report["next_action"] == "implement_risk_transient_factor_attribution_v0"


def test_attribution_input_contract_detects_optional_risk_cap_diagnostics(tmp_path):
    write_csv(
        tmp_path / "backtest_results" / "portfolio_returns.csv",
        "date,portfolio_return,benchmark_return\n2026-01-01,0.01,0.004\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "risk_exposures.csv",
        "date,portfolio_return,benchmark_return\n2026-01-01,0.01,0.004\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "unit_risk_cap_counterfactual.csv",
        "date,state,multiplier,pre_cap_return,post_cap_return,decision_label\n2026-01-01,cut,0.5,-0.02,-0.01,diagnostic_only\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "unit_risk_cap_summary.csv",
        "fold_id,candidate_id,decision_label,baseline_max_drawdown,capped_max_drawdown\nunit,unit,diagnostic_only,-0.2,-0.1\n",
    )

    report = assess_attribution_input_contract(tmp_path)
    markdown = contract_to_markdown(report)

    assert report["overall_status"] == "ready_for_transient_only"
    assert report["requirements"]["risk_cap_counterfactual"]["status"] == "ready"
    assert report["requirements"]["risk_cap_summary"]["status"] == "ready"
    assert report["optional_capabilities"]["risk_cap_counterfactual"] == {
        "status": "ready",
        "decision_label": "diagnostic_only",
        "promotion_evidence": False,
    }
    assert report["next_action"] == "review_risk_cap_counterfactual_diagnostic"
    assert "Promotion evidence: False" in markdown


def test_attribution_input_contract_rejects_non_diagnostic_risk_cap_labels(tmp_path):
    write_csv(
        tmp_path / "backtest_results" / "portfolio_returns.csv",
        "date,portfolio_return,benchmark_return\n2026-01-01,0.01,0.004\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "risk_exposures.csv",
        "date,portfolio_return,benchmark_return\n2026-01-01,0.01,0.004\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "unit_risk_cap_counterfactual.csv",
        "date,state,multiplier,pre_cap_return,post_cap_return,decision_label\n2026-01-01,cut,0.5,-0.02,-0.01,compare_next\n",
    )
    write_csv(
        tmp_path / "backtest_results" / "unit_risk_cap_summary.csv",
        "fold_id,candidate_id,decision_label,baseline_max_drawdown,capped_max_drawdown\nunit,unit,compare_next,-0.2,-0.1\n",
    )

    report = assess_attribution_input_contract(tmp_path)

    assert report["requirements"]["risk_cap_counterfactual"]["status"] == "ready"
    assert report["requirements"]["risk_cap_summary"]["status"] == "ready"
    assert report["optional_capabilities"]["risk_cap_counterfactual"]["status"] == "invalid_decision_label"
    assert report["next_action"] == "implement_risk_transient_factor_attribution_v0"


def test_attribution_input_contract_blocks_when_required_columns_are_missing(tmp_path):
    write_csv(
        tmp_path / "backtest_results" / "portfolio_returns.csv",
        "date,portfolio_return\n2026-01-01,0.01\n",
    )

    report = assess_attribution_input_contract(tmp_path)
    markdown = contract_to_markdown(report)

    assert report["overall_status"] == "blocked_missing_contract"
    assert "benchmark_return" in report["requirements"]["portfolio_returns"]["missing_columns"]
    assert report["next_action"] == "define_or_generate_attribution_inputs"
    assert "blocked_missing_contract" in markdown
    assert "benchmark_return" in markdown


def test_project_context_includes_attribution_input_contract(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "docs" / "strategy_log").mkdir(parents=True)
    write_csv(
        tmp_path / "docs" / "strategy_log" / "strategy_iteration_log.csv",
        "iteration_date,strategy_id,decision,notes\n2026-05-19,test,keep,unit\n",
    )
    write_csv(
        tmp_path / "docs" / "strategy_log" / "system_iteration_log.csv",
        "iteration_date,iteration_num,decision,notes\n2026-05-19,1,continue,unit\n",
    )

    context = build_project_context("Phase 8 attribution input contract", root=tmp_path)

    contract = context.artifact_summaries["attribution_input_contract"]
    assert contract["overall_status"] == "blocked_missing_contract"
    assert "portfolio_returns" in contract["requirements"]
