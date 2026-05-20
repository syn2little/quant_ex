from pathlib import Path

from agent.strategy_iteration.attribution import build_strategy_attribution_report
from agent.strategy_iteration.context import build_project_context
from agent.strategy_iteration.orchestrator import StrategyIterationOrchestrator


def test_build_strategy_attribution_report_compares_control_and_candidate(tmp_path: Path):
    control = tmp_path / "control.csv"
    treatment = tmp_path / "treatment.csv"
    control.write_text(
        "fold,mean_sharpe,min_sharpe,worst_max_drawdown,positive_sharpe_folds,turnover\n"
        "2021,1.10,1.10,-0.20,1,0.40\n"
        "2022,-0.40,-0.40,-0.32,0,0.60\n",
        encoding="utf-8",
    )
    treatment.write_text(
        "fold,mean_sharpe,min_sharpe,worst_max_drawdown,positive_sharpe_folds,turnover\n"
        "2021,0.80,0.80,-0.18,1,0.35\n"
        "2022,0.10,0.10,-0.22,1,0.42\n",
        encoding="utf-8",
    )

    report = build_strategy_attribution_report(
        run_id="phase7_unit",
        control_csv=control,
        candidate_csv=treatment,
        control_id="adaptive_baseline_wf",
        candidate_id="adaptive_dd20_wf",
    )

    assert report["run_id"] == "phase7_unit"
    assert report["control_id"] == "adaptive_baseline_wf"
    assert report["candidate_id"] == "adaptive_dd20_wf"
    assert report["fold_deltas"]["2022"]["mean_sharpe_delta"] == 0.5
    assert report["summary"]["improved_folds"] == ["2022"]
    assert report["summary"]["hurt_folds"] == ["2021"]
    assert report["bottleneck"] in {"return_repair", "stability_repair", "mixed_tradeoff"}
    assert "adaptive_dd20_wf" in report["recommended_primary_experiment"]


def test_project_context_includes_performance_evidence():
    context = build_project_context("phase7 performance context check")

    assert "performance_attribution" in context.artifact_summaries
    attribution = context.artifact_summaries["performance_attribution"]
    assert attribution["control_id"] == "adaptive_baseline_wf"
    assert attribution["candidate_id"] == "adaptive_dd20_wf"
    assert "recommended_primary_experiment" in attribution


def test_phase7_budget_gate_limits_experiment_arms():
    orchestrator = StrategyIterationOrchestrator(root=Path("."))

    run = orchestrator.build_run(
        "Phase 7: Agent Performance Attribution and Experiment Budgeting",
        use_llm=False,
        run_id="phase7_budget_unit",
        discussion_mode="meeting",
        meeting_max_rounds=3,
        meeting_max_roles_per_round=2,
    )

    arms = run.plan.experiment_arms
    assert 1 <= len(arms) <= 2
    assert [arm.change_type for arm in arms].count("primary_experiment") == 1
    assert any("kill" in " ".join(arm.success_criteria + arm.risk_notes).lower() for arm in arms)
    assert "attribution_report" in run.plan.to_markdown()
