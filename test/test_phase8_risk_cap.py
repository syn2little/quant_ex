import pytest

from agent.strategy_iteration.risk_cap import (
    RiskCapPolicy,
    apply_cap_multiplier,
    cap_multiplier_for_state,
    compute_cap_state,
    compute_drawdown,
    compute_pre_post_counterfactual_returns,
    compute_rolling_vol,
    compute_risk_cap_counterfactual_series,
    compute_turnover_delta,
    summarize_risk_cap_counterfactual,
)


def test_compute_drawdown_handles_flat_nav_and_one_day_crash():
    assert compute_drawdown([1.0, 1.0, 1.0]) == [0.0, 0.0, 0.0]

    drawdown = compute_drawdown([1.0, 1.1, 0.88, 0.99])
    assert drawdown == pytest.approx([0.0, 0.0, -0.2, -0.1])


@pytest.mark.parametrize("bad_nav", [[1.0, 0.0], [1.0, -0.2]])
def test_compute_drawdown_rejects_invalid_nav(bad_nav):
    with pytest.raises(ValueError):
        compute_drawdown(bad_nav)


def test_compute_rolling_vol_annualizes_after_complete_window():
    returns = [0.01, -0.01, 0.03]

    vol = compute_rolling_vol(returns, window=2, annualization=1.0)

    assert vol[0] is None
    assert vol[1] == pytest.approx(0.0141421356)
    assert vol[2] == pytest.approx(0.0282842712)


def test_compute_cap_state_uses_lagged_inputs_for_watch_cut_and_recover():
    policy = RiskCapPolicy(
        watch_vol=0.10,
        cut_vol=0.20,
        watch_drawdown=-0.05,
        cut_drawdown=-0.12,
        recover_vol=0.08,
        recover_drawdown=-0.02,
    )

    assert compute_cap_state(0.07, -0.01, "inactive", policy) == "inactive"
    assert compute_cap_state(0.11, -0.01, "inactive", policy) == "watch"
    assert compute_cap_state(0.07, -0.13, "watch", policy) == "cut"
    assert compute_cap_state(0.09, -0.04, "cut", policy) == "cut"
    assert compute_cap_state(0.07, -0.01, "cut", policy) == "recover"


def test_compute_cap_state_blocks_missing_inputs_without_fail_open():
    assert compute_cap_state(None, -0.01, "inactive") == "blocked"
    assert compute_cap_state(0.10, None, "watch") == "blocked"


def test_cap_multiplier_and_weight_scaling_preserve_membership():
    weights = {"AAA": 0.40, "BBB": 0.30, "CCC": 0.10}
    policy = RiskCapPolicy(cut_multiplier=0.50, recover_multiplier=0.75)

    assert cap_multiplier_for_state("cut", policy) == 0.50
    assert cap_multiplier_for_state("recover", policy) == 0.75
    assert cap_multiplier_for_state("watch", policy) == 1.0
    assert apply_cap_multiplier(weights, 0.5) == {"AAA": 0.20, "BBB": 0.15, "CCC": 0.05}


@pytest.mark.parametrize("multiplier", [-0.1, 1.1])
def test_apply_cap_multiplier_rejects_invalid_multiplier(multiplier):
    with pytest.raises(ValueError):
        apply_cap_multiplier({"AAA": 0.2}, multiplier)


def test_compute_pre_post_counterfactual_returns_scales_exposure_not_signal():
    rows = compute_pre_post_counterfactual_returns(
        pre_cap_returns=[0.02, -0.04, 0.01],
        multipliers=[1.0, 0.5, 0.0],
        cash_return=0.001,
    )

    assert rows == pytest.approx(
        [
            {"pre_cap_return": 0.02, "post_cap_return": 0.02},
            {"pre_cap_return": -0.04, "post_cap_return": -0.0195},
            {"pre_cap_return": 0.01, "post_cap_return": 0.001},
        ]
    )


def test_compute_pre_post_counterfactual_returns_rejects_length_mismatch():
    with pytest.raises(ValueError):
        compute_pre_post_counterfactual_returns([0.01], [1.0, 0.5])


def test_compute_turnover_delta_counts_derisk_and_rerisk_weight_changes():
    pre = {"AAA": 0.40, "BBB": 0.30}
    post = {"AAA": 0.20, "CCC": 0.10}

    assert compute_turnover_delta(pre, post) == pytest.approx(0.60)


def test_compute_risk_cap_counterfactual_series_uses_prior_day_risk_inputs():
    policy = RiskCapPolicy(
        watch_vol=0.10,
        cut_vol=0.20,
        watch_drawdown=-0.05,
        cut_drawdown=-0.10,
        recover_vol=0.08,
        recover_drawdown=-0.02,
        cut_multiplier=0.50,
        recover_multiplier=0.75,
    )

    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.02, -0.04, -0.03, 0.05],
        lagged_vol=[None, 0.11, 0.22, 0.07],
        lagged_drawdown=[None, -0.03, -0.11, -0.01],
        policy=policy,
    )

    assert [row["state"] for row in rows] == ["blocked", "watch", "cut", "recover"]
    assert [row["multiplier"] for row in rows] == pytest.approx([1.0, 1.0, 0.5, 0.75])
    assert [row["post_cap_return"] for row in rows] == pytest.approx([0.02, -0.04, -0.015, 0.0375])
    assert rows[2]["pre_cap_nav"] == pytest.approx(0.949824)
    assert rows[2]["post_cap_nav"] == pytest.approx(0.964512)


def test_compute_risk_cap_counterfactual_series_rejects_misaligned_inputs():
    with pytest.raises(ValueError):
        compute_risk_cap_counterfactual_series(
            pre_cap_returns=[0.01, -0.02],
            lagged_vol=[0.10],
            lagged_drawdown=[-0.01, -0.02],
        )


def test_summarize_risk_cap_counterfactual_keeps_report_only_label():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.02, -0.04, -0.03, 0.05],
        lagged_vol=[None, 0.11, 0.22, 0.07],
        lagged_drawdown=[None, -0.03, -0.11, -0.01],
        policy=RiskCapPolicy(
            watch_vol=0.10,
            cut_vol=0.20,
            watch_drawdown=-0.05,
            cut_drawdown=-0.10,
            recover_vol=0.08,
            recover_drawdown=-0.02,
            cut_multiplier=0.50,
            recover_multiplier=0.75,
        ),
    )

    summary = summarize_risk_cap_counterfactual(rows, fold_id="toy_fold_001", periods_per_year=4.0)

    assert summary["candidate_id"] == "gate_m008"
    assert summary["fold_id"] == "toy_fold_001"
    assert summary["decision_label"] == "diagnostic_only"
    assert summary["cap_active_days"] == 2
    assert summary["cap_cut_days"] == 1
    assert summary["cap_recover_days"] == 1
    assert summary["cut_to_recover_ratio"] == pytest.approx(1.0)
    assert summary["cap_blocked_days"] == 1
    assert summary["avg_cap_multiplier"] == pytest.approx(0.8125)
    assert summary["baseline_total_return"] == pytest.approx(-0.0026848)
    assert summary["capped_total_return"] == pytest.approx(0.0006812)
    assert summary["baseline_annualized_return"] == pytest.approx(-0.0026848)
    assert summary["capped_annualized_return"] == pytest.approx(0.0006812)
    assert summary["total_return_delta"] == pytest.approx(0.003366)
    assert summary["max_drawdown_delta"] == pytest.approx(0.0144)
    assert summary["baseline_ir"] == pytest.approx(0.0)
    assert summary["capped_ir"] == pytest.approx(0.01796826015)
    assert float(summary["capped_max_drawdown"]) > float(summary["baseline_max_drawdown"])


def test_summarize_risk_cap_counterfactual_uses_benchmark_for_active_ir():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.02, -0.02, 0.01],
        lagged_vol=[0.05, 0.05, 0.05],
        lagged_drawdown=[0.0, -0.01, -0.01],
    )

    summary = summarize_risk_cap_counterfactual(
        rows,
        fold_id="toy_ir",
        periods_per_year=3.0,
        benchmark_returns=[0.01, -0.01, 0.0],
    )

    assert summary["baseline_ir"] == pytest.approx(0.28867513459)
    assert summary["capped_ir"] == pytest.approx(0.28867513459)


def test_summarize_risk_cap_counterfactual_materializes_turnover_fields():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.01, -0.02, 0.03],
        lagged_vol=[0.05, 0.22, 0.07],
        lagged_drawdown=[0.0, -0.12, -0.01],
    )

    summary = summarize_risk_cap_counterfactual(
        rows,
        fold_id="toy_turnover",
        pre_cap_turnover=[0.10, 0.20, 0.30],
        post_cap_turnover=[0.10, 0.35, 0.45],
    )

    assert summary["baseline_turnover"] == pytest.approx(0.20)
    assert summary["capped_turnover"] == pytest.approx(0.30)


def test_summarize_risk_cap_counterfactual_materializes_tail_loss_delta():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.01, -0.03, 0.02, -0.01],
        lagged_vol=[0.05, 0.26, 0.07, 0.05],
        lagged_drawdown=[0.0, -0.12, -0.01, -0.01],
        policy=RiskCapPolicy(cut_multiplier=0.50, recover_multiplier=0.75),
    )

    summary = summarize_risk_cap_counterfactual(rows, fold_id="toy_tail")

    assert summary["worst_5_day_pre_cap"] == pytest.approx(-0.01)
    assert summary["worst_5_day_post_cap"] == pytest.approx(0.0025)
    assert summary["tail_loss_delta"] == pytest.approx(0.0125)


def test_summarize_risk_cap_counterfactual_materializes_upside_capture_delta():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.03, -0.08, 0.04, -0.05, 0.02],
        lagged_vol=[0.05, 0.28, 0.07, 0.06, 0.05],
        lagged_drawdown=[0.0, -0.13, -0.01, -0.01, 0.0],
        policy=RiskCapPolicy(cut_multiplier=0.50, recover_multiplier=0.75),
    )

    summary = summarize_risk_cap_counterfactual(rows, fold_id="toy_positive_capture")

    assert summary["baseline_positive_return_capture"] == pytest.approx(0.09)
    assert summary["capped_positive_return_capture"] == pytest.approx(0.075)
    assert summary["positive_return_capture_delta"] == pytest.approx(-0.015)


def test_summarize_risk_cap_counterfactual_materializes_downside_capture_delta():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[-0.02, -0.04, 0.03, 0.01, -0.01],
        lagged_vol=[0.05, 0.28, 0.07, 0.06, 0.05],
        lagged_drawdown=[0.0, -0.13, -0.01, -0.01, 0.0],
        policy=RiskCapPolicy(cut_multiplier=0.50, recover_multiplier=0.75),
    )

    summary = summarize_risk_cap_counterfactual(rows, fold_id="toy_downside_capture")

    assert summary["baseline_negative_return_capture"] == pytest.approx(-0.07)
    assert summary["capped_negative_return_capture"] == pytest.approx(-0.0475)
    assert summary["negative_return_capture_delta"] == pytest.approx(0.0225)


def test_summarize_risk_cap_counterfactual_materializes_cut_to_recover_ratio():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.03, -0.06, 0.02, -0.04, 0.05, 0.01],
        lagged_vol=[0.05, 0.28, 0.07, 0.06, 0.05, 0.05],
        lagged_drawdown=[0.0, -0.13, -0.01, -0.04, -0.01, 0.0],
        policy=RiskCapPolicy(cut_multiplier=0.50, recover_multiplier=0.75),
    )

    summary = summarize_risk_cap_counterfactual(rows, fold_id="toy_reentry_ratio")

    assert summary["cap_cut_days"] == 2
    assert summary["cap_recover_days"] == 3
    assert summary["cut_to_recover_ratio"] == pytest.approx(2 / 3)


def test_summarize_risk_cap_counterfactual_rejects_misaligned_turnover():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.01, -0.01],
        lagged_vol=[0.05, 0.05],
        lagged_drawdown=[0.0, -0.01],
    )

    with pytest.raises(ValueError):
        summarize_risk_cap_counterfactual(rows, fold_id="toy", pre_cap_turnover=[0.10])


def test_summarize_risk_cap_counterfactual_rejects_misaligned_benchmark_returns():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.01, -0.01],
        lagged_vol=[0.05, 0.05],
        lagged_drawdown=[0.0, -0.01],
    )

    with pytest.raises(ValueError):
        summarize_risk_cap_counterfactual(rows, fold_id="toy", benchmark_returns=[0.0])


def test_summarize_risk_cap_counterfactual_rejects_invalid_annualization():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.01, -0.01],
        lagged_vol=[0.05, 0.05],
        lagged_drawdown=[0.0, -0.01],
    )

    with pytest.raises(ValueError):
        summarize_risk_cap_counterfactual(rows, fold_id="toy", periods_per_year=0.0)


def test_summarize_risk_cap_counterfactual_rejects_promotion_label():
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=[0.01, -0.01],
        lagged_vol=[0.05, 0.05],
        lagged_drawdown=[0.0, -0.01],
    )

    with pytest.raises(ValueError):
        summarize_risk_cap_counterfactual(rows, fold_id="toy", decision_label="promotable_pending_human_review")
