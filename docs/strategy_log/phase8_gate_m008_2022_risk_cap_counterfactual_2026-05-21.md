# Phase8 gate_m008 2022 risk-cap counterfactual

Status: `diagnostic_only_not_trading_signal`.

This report keeps the fixed `gate_m008` signal path and applies only a lagged portfolio-level exposure cap to realized daily returns. It does not change ranking, topk, n_drop, hold threshold, data, WFV, or any daily rebalance/live configuration.

## Inputs
- run_id: `wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519`
- rows: 242
- date_range: 2022-01-04 to 2022-12-30
- vol_window: 20
- policy: `{"cut_drawdown": -0.1, "cut_multiplier": 0.5, "cut_vol": 0.25, "missing_input_state": "blocked", "recover_drawdown": -0.03, "recover_multiplier": 0.75, "recover_vol": 0.16, "watch_drawdown": -0.05, "watch_vol": 0.18}`

## Summary metrics
- baseline_total_return: -0.012938
- capped_total_return: -0.046823
- total_return_delta: -0.033884
- baseline_annualized_return: -0.013470
- capped_annualized_return: -0.048710
- baseline_max_drawdown: -0.291492
- capped_max_drawdown: -0.198393
- max_drawdown_delta: 0.093099
- baseline_vol: 0.020032
- capped_vol: 0.010620
- baseline_ir: 0.084402
- capped_ir: 0.098429
- worst_5_day_pre_cap: -0.246430
- worst_5_day_post_cap: -0.133345
- tail_loss_delta: 0.113085
- baseline_positive_return_capture: 1.842543
- capped_positive_return_capture: 0.955329
- positive_return_capture_delta: -0.887214
- baseline_negative_return_capture: -1.807380
- capped_negative_return_capture: -0.989696
- negative_return_capture_delta: 0.817684
- cap_active_days: 219
- cap_cut_days: 219
- cap_recover_days: 0
- cap_blocked_days: 20
- avg_cap_multiplier: 0.547521

## State counts
- blocked: 20
- cut: 219
- watch: 3

## Interpretation
- decision: `diagnostic_only`
- next_action: `diagnostic_refine: risk survival improves, but upside capture loss is too large for replay readiness.`
- guardrail: improvement here is post-hoc diagnostic evidence only; it is not WFV evidence and not a trading signal.

## Coarse sensitivity
- preset: default_v0, capped_total_return: -0.046823, total_return_delta: -0.033884, capped_max_drawdown: -0.198393, max_drawdown_delta: 0.093099, capped_ir: 0.098429, tail_loss_delta: 0.113085, positive_return_capture_delta: -0.887214, negative_return_capture_delta: 0.817684, cap_active_days: 219, avg_cap_multiplier: 0.547521
- preset: drawdown_15_cut, capped_total_return: -0.079503, total_return_delta: -0.066565, capped_max_drawdown: -0.227060, max_drawdown_delta: 0.064432, capped_ir: 0.076057, tail_loss_delta: 0.080619, positive_return_capture_delta: -0.823921, negative_return_capture_delta: 0.722792, cap_active_days: 200, avg_cap_multiplier: 0.587810
- preset: drawdown_20_cut, capped_total_return: -0.123465, total_return_delta: -0.110527, capped_max_drawdown: -0.248807, max_drawdown_delta: 0.042685, capped_ir: 0.052132, tail_loss_delta: 0.036317, positive_return_capture_delta: -0.667242, negative_return_capture_delta: 0.524693, cap_active_days: 171, avg_cap_multiplier: 0.672521
- preset: soft_dd15, capped_total_return: -0.051069, total_return_delta: -0.038131, capped_max_drawdown: -0.252960, max_drawdown_delta: 0.038532, capped_ir: 0.087568, tail_loss_delta: 0.054403, positive_return_capture_delta: -0.494353, negative_return_capture_delta: 0.433675, cap_active_days: 200, avg_cap_multiplier: 0.752686
- preset: vol_only_high, capped_total_return: -0.068281, total_return_delta: -0.055342, capped_max_drawdown: -0.211975, max_drawdown_delta: 0.079517, capped_ir: 0.081592, tail_loss_delta: 0.080619, positive_return_capture_delta: -0.769516, negative_return_capture_delta: 0.681937, cap_active_days: 199, avg_cap_multiplier: 0.612603

Sensitivity is coarse diagnostic triage, not parameter tuning evidence. The dominant finding is whether fixed risk-budget families are worth a follow-up replay, not which threshold is best.
