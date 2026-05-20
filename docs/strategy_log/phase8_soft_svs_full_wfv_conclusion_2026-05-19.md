# Phase 8 soft SVS full WFV conclusion — 2026-05-19

## Scope
- Full default WFV schedule: 2020-2026, 7 folds.
- Single candidate only: `config/csi1000_transient_repair_soft_svs.yaml`.
- No data refresh.
- No rebalance, trading action, or live notification.

## Artifacts
- WFV report: `optimization_results/walk_forward_phase8_soft_svs_full_wfv_20260519/walk_forward_report.md`
- WFV summary: `optimization_results/walk_forward_phase8_soft_svs_full_wfv_20260519/walk_forward_summary.csv`
- Fold rows: `optimization_results/walk_forward_phase8_soft_svs_full_wfv_20260519/walk_forward_all_results.csv`
- Promotion report: `docs/strategy_log/phase8_soft_svs_full_wfv_promotion_report_2026-05-19.md`

## Aggregate result
- folds: 7
- mean annual return: 14.60%
- mean Sharpe: 0.6066
- median Sharpe: 1.0906
- min Sharpe: -0.8828
- Sharpe std: 0.8727
- worst max drawdown: -22.54%
- positive Sharpe folds: 5/7
- mean rank IC: 0.0471
- mean rank ICIR: 0.3308
- Sharpe t-test p-value: 0.1395

## Fold rows
| fold | annual_return | sharpe | max_drawdown | information_ratio | rank_ic | rank_icir |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2020 | 36.12% | 1.2963 | -17.91% | 0.5135 | 0.0697 | 0.4911 |
| 2021 | 11.75% | 0.4382 | -20.19% | 1.0119 | 0.0314 | 0.2608 |
| 2022 | -11.35% | -0.4643 | -22.54% | 0.9328 | 0.0566 | 0.4189 |
| 2023 | -13.39% | -0.8828 | -21.80% | -0.1453 | 0.0276 | 0.2383 |
| 2024 | 39.27% | 1.4812 | -14.01% | 1.4460 | 0.0738 | 0.3958 |
| 2025 | 20.33% | 1.2871 | -9.67% | 0.0963 | 0.0358 | 0.2719 |
| 2026 | 19.47% | 1.0906 | -7.24% | 0.2884 | 0.0346 | 0.2389 |

## Gate read
`full_wfv_mixed_not_promotable`

The full WFV did not confirm the narrow 2024-2026 gate. The promotion report is `compare_next` / `not_promotable` because:

- `wfv_mean_sharpe` blocks: mean Sharpe is 0.6066, below the 0.9 gate.
- `wfv_min_sharpe` blocks: min Sharpe is -0.8828.
- 2022 and 2023 are negative Sharpe years.

## Interpretation
Soft SVS is still useful as a diagnostic repair idea and performs strongly in 2024-2026, but the 2020-2026 WFV exposes unstable regime behavior. It should not replace the current practical/default candidate.

## Next action
Do not promote this exact config. The next bounded step is a control-matched WFV across practical baseline, hard SVS, and soft SVS, or a regime-gated variant that disables or softens SVS specifically around 2022-2023-like stress regimes.
