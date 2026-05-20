# Phase 8 regime-gated SVS full WFV conclusion — 2026-05-19

## Scope
- Full default WFV schedule: 2020-2026, 7 folds.
- Single candidate: `config/csi1000_transient_repair_regime_gated_svs.yaml`.
- No data refresh.
- No rebalance, trading action, or live notification.

## Candidate
Regime-gated SVS keeps the soft SVS repair in normal markets and falls back to the base signal when the equal-weight market drawdown breaches the configured gate.

```yaml
stock_vs_sector_filter:
  enabled: true
  window: 20
  keep_top_pct: 0.4
  soft_keep_top_pct_floor: 0.5
  drawdown_threshold: -0.10
  drawdown_window: 120
```

## Artifacts
- WFV report: `optimization_results/walk_forward_phase8_regime_gated_svs_full_wfv_20260519/walk_forward_report.md`
- WFV summary: `optimization_results/walk_forward_phase8_regime_gated_svs_full_wfv_20260519/walk_forward_summary.csv`
- Fold rows: `optimization_results/walk_forward_phase8_regime_gated_svs_full_wfv_20260519/walk_forward_all_results.csv`
- Promotion report: `docs/strategy_log/phase8_regime_gated_svs_full_wfv_promotion_report_2026-05-19.md`

## Aggregate result
- folds: 7
- mean annual return: 18.28%
- mean Sharpe: 0.8466
- median Sharpe: 1.1262
- min Sharpe: -0.5565
- Sharpe std: 0.9636
- worst max drawdown: -29.20%
- positive Sharpe folds: 5/7
- mean rank IC: 0.0491
- mean rank ICIR: 0.3547
- Sharpe t-test p-value: 0.0749

## Fold rows
| fold | annual_return | sharpe | max_drawdown | information_ratio | rank_ic | rank_icir |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2020 | 36.80% | 1.3105 | -20.94% | 0.4904 | 0.0704 | 0.4908 |
| 2021 | 16.79% | 0.5913 | -21.15% | 1.2740 | 0.0381 | 0.3156 |
| 2022 | -11.90% | -0.4017 | -29.20% | 0.9087 | 0.0557 | 0.4064 |
| 2023 | -10.17% | -0.5565 | -23.44% | 0.2309 | 0.0256 | 0.2402 |
| 2024 | 30.62% | 1.1262 | -16.14% | 0.9479 | 0.0763 | 0.4489 |
| 2025 | 36.48% | 2.2986 | -8.32% | 1.1684 | 0.0386 | 0.3049 |
| 2026 | 29.33% | 1.5578 | -7.24% | 1.0055 | 0.0388 | 0.2758 |

## Comparison vs ungated soft SVS full WFV
| metric | soft SVS | regime-gated SVS | read |
| --- | ---: | ---: | --- |
| mean annual return | 14.60% | 18.28% | better |
| mean Sharpe | 0.6066 | 0.8466 | better, but below 0.9 gate |
| min Sharpe | -0.8828 | -0.5565 | better, but still negative |
| worst max drawdown | -22.54% | -29.20% | worse |
| positive Sharpe folds | 5/7 | 5/7 | unchanged |
| mean rank IC | 0.0471 | 0.0491 | slightly better |
| mean rank ICIR | 0.3308 | 0.3547 | better |
| Sharpe p-value | 0.1395 | 0.0749 | better |

## Gate read
`regime_gated_svs_improves_but_not_promotable`

The promotion report is `compare_next` / `not_promotable`. The candidate improves mean Sharpe, min Sharpe, annual return, rank IC, and p-value versus ungated soft SVS, but it still fails the promotion gates:

- `wfv_mean_sharpe` blocks: mean Sharpe is 0.8466, below the 0.9 gate.
- `wfv_min_sharpe` blocks: min Sharpe is -0.5565.
- worst max drawdown worsened to -29.20%.
- 2022 and 2023 remain negative Sharpe years.

## Interpretation
The drawdown gate direction is useful but the current threshold/window is not enough. It reduces the depth of the negative Sharpe folds, but increases worst drawdown and remains below promotion quality.

## Next action
Do not promote this config. The next bounded iteration should tune the regime gate itself rather than the SVS strength: test a tiny grid over `drawdown_threshold` values such as `-0.05`, `-0.08`, and `-0.12`, while keeping `soft_keep_top_pct_floor: 0.5` fixed.
