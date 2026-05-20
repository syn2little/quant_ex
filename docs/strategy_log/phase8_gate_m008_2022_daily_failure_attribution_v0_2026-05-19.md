# Daily Failure Attribution: wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519

- Guardrail: `diagnostic_only_not_trading_signal`
- Next action: `portfolio_risk_cap_over_signal_tuning`

## Summary
- days: 242
- mean_portfolio_return: 0.000145
- mean_benchmark_return: -0.000924
- mean_residual_return: 0.001070
- hit_rate: 0.466942
- worst_drawdown: -0.291492
- worst_portfolio_return: -0.068108

## Stress Regime
- threshold: -0.050000
- days: 196
- mean_portfolio_return: -0.000452
- mean_residual_return: 0.000404
- accepted_loser_count: 1496
- missed_winner_count: 22961

## Event Summary
- events: 60542
- accepted_count: 3615
- rejected_count: 56927
- accepted_loser_count: 1865
- missed_winner_count: 26270
- accepted_mean_forward_return: 0.000185
- rejected_mean_forward_return: -0.000653
- accepted_loser_mean_forward_return: -0.020165
- missed_winner_mean_forward_return: 0.018927

## Worst Drawdown Days
| date | portfolio_return | benchmark_return | residual_return | drawdown | accepted_losers | missed_winners | events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-04-26 | -0.031677 | -0.008071 | -0.023607 | -0.291492 | 2 | 227 | 278 |
| 2022-04-25 | -0.068108 | -0.049421 | -0.018687 | -0.268314 | 12 | 82 | 278 |
| 2022-04-28 | -0.007729 | 0.006564 | -0.014293 | -0.261996 | 1 | 223 | 278 |
| 2022-10-11 | -0.000662 | 0.001814 | -0.002476 | -0.259588 | 0 | 227 | 281 |
| 2022-10-10 | -0.042844 | -0.022064 | -0.020781 | -0.259097 | 6 | 125 | 281 |
| 2022-10-28 | -0.041812 | -0.024733 | -0.017079 | -0.258834 | 11 | 93 | 281 |
| 2022-04-27 | 0.049744 | 0.029444 | 0.020300 | -0.256248 | 11 | 133 | 278 |
| 2022-10-31 | 0.007544 | -0.009214 | 0.016758 | -0.253243 | 0 | 235 | 281 |
| 2022-10-12 | 0.020438 | 0.015189 | 0.005249 | -0.244455 | 8 | 104 | 281 |
| 2022-10-25 | -0.004649 | -0.001629 | -0.003019 | -0.240393 | 4 | 184 | 280 |

## Diagnostic Flags
- `absolute_risk_survival_issue`
- `missed_winners_exceed_accepted_losers`
- `accepted_losers_present`
