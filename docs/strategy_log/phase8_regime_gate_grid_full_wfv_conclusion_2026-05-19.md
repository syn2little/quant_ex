# Phase 8 regime gate threshold grid full WFV conclusion — 2026-05-19

## Scope
- Full default WFV schedule: 2020-2026, 7 folds per arm.
- Fixed model family and strategy params: csi1000 training, csi300 evaluation, topk=15, n_drop=3, hold_thresh=8.
- Fixed SVS repair strength: `keep_top_pct: 0.4`, `soft_keep_top_pct_floor: 0.5`, `drawdown_window: 120`.
- Swept only `drawdown_threshold`: -0.05, -0.08, -0.12.
- No data refresh, no rebalance, no trading action, no live notification.

## Artifacts
- Runner: `scripts/run_phase8_regime_gate_grid.py`
- Configs:
  - `config/csi1000_transient_repair_regime_gated_svs_m005.yaml`
  - `config/csi1000_transient_repair_regime_gated_svs_m008.yaml`
  - `config/csi1000_transient_repair_regime_gated_svs_m012.yaml`
- WFV outputs:
  - `optimization_results/walk_forward_phase8_regime_gate_grid_m005_full_wfv_20260519/`
  - `optimization_results/walk_forward_phase8_regime_gate_grid_m008_full_wfv_20260519/`
  - `optimization_results/walk_forward_phase8_regime_gate_grid_m012_full_wfv_20260519/`

## Summary comparison
| arm | threshold | mean annual | mean Sharpe | min Sharpe | sharpe std | worst DD | positive Sharpe folds | rank IC | rank ICIR | Sharpe p | robust score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| soft_no_gate | none | 14.60% | 0.6066 | -0.8828 | 0.8727 | -22.54% | 5/7 | 0.0471 | 0.3308 | 0.1395 | 0.2437 |
| gate_m005 | -0.05 | 21.72% | 0.8848 | -0.4998 | 0.8394 | -32.93% | 5/7 | 0.0487 | 0.3642 | 0.0417 | 0.6151 |
| gate_m008 | -0.08 | 25.40% | 1.1248 | -0.0424 | 0.7055 | -29.15% | 6/7 | 0.0488 | 0.3547 | 0.0079 | 1.0636 |
| gate_m010 | -0.10 | 18.28% | 0.8466 | -0.5565 | 0.9636 | -29.20% | 5/7 | 0.0491 | 0.3547 | 0.0749 | 0.5035 |
| gate_m012 | -0.12 | 20.54% | 0.8463 | -0.5370 | 0.8105 | -33.46% | 5/7 | 0.0485 | 0.3470 | 0.0431 | 0.5836 |

## Fold Sharpe comparison
| arm | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| soft_no_gate | 1.2963 | 0.4382 | -0.4643 | -0.8828 | 1.4812 | 1.2871 | 1.0906 |
| gate_m005 | 1.7197 | 1.4863 | -0.4998 | -0.2892 | 0.9427 | 1.3507 | 1.4831 |
| gate_m008 | 1.0473 | 1.3195 | -0.0424 | 0.6985 | 0.7400 | 2.1443 | 1.9667 |
| gate_m010 | 1.3105 | 0.5913 | -0.4017 | -0.5565 | 1.1262 | 2.2986 | 1.5578 |
| gate_m012 | 1.7008 | 1.1241 | -0.2523 | -0.5370 | 1.4150 | 1.3828 | 1.0906 |

## Best arm
`gate_m008` is the best threshold in this grid.

Why:
- Highest mean Sharpe: 1.1248.
- Best min Sharpe: -0.0424, near break-even in the weakest fold.
- Only arm with 6/7 positive Sharpe folds.
- Lowest Sharpe std among the grid arms: 0.7055.
- Strong p-value: 0.0079.
- Highest robust score: 1.0636.
- Fixes 2023 from negative to positive Sharpe.

## Remaining blocker
`gate_m008` is still not promotable under the current gate because `wfv_min_sharpe` remains slightly negative:

- 2022 Sharpe: -0.0424.
- Worst max drawdown: -29.15%.

Generated promotion report for `gate_m008` says `compare_next` / `not_promotable`.

## Gate read
`threshold_grid_identifies_m008_near_promotable_but_blocked`

The `-0.08` drawdown gate is a strong improvement and becomes the leading research candidate, but it should not replace the daily/default strategy yet.

## Next action
Do not promote directly. The next bounded iteration should target the residual 2022 weakness specifically, without changing the whole SVS mechanism:

1. Test a very small local threshold refinement around -0.08, such as -0.07 and -0.09, or
2. Add a second drawdown guard for maximum drawdown exposure / portfolio concentration during gated regimes, then rerun full WFV.
