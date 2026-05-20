# Phase 8 soft SVS WFV + diagnostic conclusion — 2026-05-19

## Scope
- Ran a narrow WFV gate only: 2024, 2025, 2026 folds.
- Did not run full WFV.
- Did not refresh data.
- Did not rebalance, trade, or send live notifications.

## Diagnostic comparison
- Report: `docs/strategy_log/phase8_three_way_transient_diagnostic_2026-05-19.md`
- Arms: baseline/no SVS, hard SVS, soft SVS.
- Soft SVS had the best same-model Sharpe, IR, alpha, hit rate, and drawdown.
- Hard SVS had the lowest missed-winner count, but worse drawdown than soft SVS.
- Stress-regime residual remained negative across all arms.

## Narrow WFV gate
- Run id: `phase8_soft_svs_narrow_wfv_20260519`
- Report: `optimization_results/walk_forward_phase8_soft_svs_narrow_wfv_20260519/walk_forward_report.md`
- Summary: `optimization_results/walk_forward_phase8_soft_svs_narrow_wfv_20260519/walk_forward_summary.csv`
- All fold rows: `optimization_results/walk_forward_phase8_soft_svs_narrow_wfv_20260519/walk_forward_all_results.csv`
- Promotion report: `docs/strategy_log/phase8_soft_svs_narrow_wfv_promotion_report_2026-05-19.md`

## WFV aggregate result
- folds: 3
- mean annual return: 26.36%
- mean Sharpe: 1.2863
- min Sharpe: 1.0906
- Sharpe std: 0.1595
- worst max drawdown: -14.01%
- positive Sharpe folds: 3/3
- mean rank IC: 0.0481
- mean rank ICIR: 0.3022
- Sharpe t-test p-value: 0.0076

## Fold rows
| fold | annual_return | sharpe | max_drawdown | information_ratio | rank_ic | rank_icir |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024 | 39.27% | 1.4812 | -14.01% | 1.4460 | 0.0738 | 0.3958 |
| 2025 | 20.33% | 1.2871 | -9.67% | 0.0963 | 0.0358 | 0.2719 |
| 2026 | 19.47% | 1.0906 | -7.24% | 0.2884 | 0.0346 | 0.2389 |

## Gate read
`narrow_wfv_passed_promotable_for_manual_review`

The generated promotion report says `promote` because the narrow WFV summary clears the configured WFV gates. Treat this as promotion-grade evidence for manual review, not an automatic live-config update.

## Recommendation
Keep `config/csi1000_transient_repair_soft_svs.yaml` as the leading candidate. Before changing daily rebalance defaults, run either:

1. a full 2020-2026 WFV on only this config, or
2. a control-matched WFV against the current practical baseline and hard SVS.
