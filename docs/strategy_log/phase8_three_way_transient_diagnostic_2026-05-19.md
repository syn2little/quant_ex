# Phase 8 three-way transient diagnostic — 2026-05-19

## Scope
- Diagnostic-only comparison.
- No full WFV in this step.
- No data refresh, no rebalance, no live notifications.

## Arms
| arm | run_id | config | note |
| --- | --- | --- | --- |
| baseline | `phase8_same_model_attribution_20260519` | baseline/no SVS | prior same-model attribution artifacts |
| hard_svs | `phase8_transient_repair_hard_svs_20260519` | `config/csi1000_transient_repair_hard_svs.yaml` | `keep_top_pct: 0.4` |
| soft_svs | `phase8_transient_repair_soft_svs_20260519` | `config/csi1000_transient_repair_soft_svs.yaml` | `keep_top_pct: 0.4`, `soft_keep_top_pct_floor: 0.5` |

## Backtest summary
| arm | cumulative_return | sharpe | max_drawdown | information_ratio | alpha |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 36.90% | 0.6306 | -22.00% | -0.0471 | -2.81% |
| hard_svs | 92.17% | 1.6497 | -15.20% | 1.0379 | 18.85% |
| soft_svs | 94.13% | 1.6663 | -11.77% | 1.0973 | 19.11% |

## Attribution summary
| arm | mean_residual_return | hit_rate | worst_drawdown | stress_mean_residual | missed_winner_count | accepted_loser_count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | -0.000026 | 0.465035 | -0.219993 | -0.000509 | 69682 | 4115 |
| hard_svs | 0.000539 | 0.515734 | -0.151996 | -0.000746 | 23987 | 4016 |
| soft_svs | 0.000559 | 0.533217 | -0.117744 | -0.000828 | 31311 | 4010 |

## Readout
- Both SVS arms materially improve same-model IR, Sharpe, alpha, drawdown, hit rate, and mean residual versus baseline.
- Hard SVS produces the lowest missed-winner count, but still has worse drawdown than soft SVS.
- Soft SVS has the best same-model IR, Sharpe, hit rate, alpha, and drawdown, but it admits more candidate events and more missed winners than hard SVS.
- Stress-period residual remains negative for all arms; soft SVS improves aggregate drawdown but does not solve stress-regime underperformance.

## Diagnostic conclusion
`soft_svs_wins_same_model_but_stress_regime_unresolved`

Soft SVS is the better same-model repair candidate for a narrow WFV gate. It should remain research-only until WFV results are available.
