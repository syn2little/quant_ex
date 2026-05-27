# Daily Failure Attribution: phase8_gate_m008_2022_risk_memory_20260526

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

## Risk Memory / Roughness / Persistence

### Config
- memory_window: 20
- roughness_window: 10
- persistence_window: 10
- high_quantile: 0.750000

### Summary
- max_stress_memory_score: 0.229211
- mean_stress_memory_score: 0.112013
- max_residual_roughness: 0.024589
- mean_residual_roughness: 0.009354
- max_residual_volatility: 0.025201
- mean_residual_volatility: 0.010685
- max_consecutive_negative_portfolio_days: 7
- max_consecutive_negative_residual_days: 6
- max_rolling_negative_portfolio_share: 0.900000
- max_rolling_negative_residual_share: 0.800000

### Bucket Comparison
| bucket | days | mean_portfolio_return | mean_residual_return | worst_drawdown | mean_stress_memory_score | mean_residual_roughness | mean_rolling_negative_portfolio_share | accepted_losers | missed_winners |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| high_memory | 61 | 0.005746 | 0.004967 | -0.291492 | 0.197082 | 0.011562 | 0.449180 | 430 | 7941 |
| other_memory | 181 | -0.001742 | -0.000244 | -0.268314 | 0.083344 | 0.008609 | 0.565702 | 1435 | 18329 |
| high_roughness | 61 | 0.005842 | 0.004843 | -0.291492 | 0.133938 | 0.015201 | 0.480328 | 469 | 7286 |
| other_roughness | 181 | -0.001775 | -0.000202 | -0.259588 | 0.104625 | 0.007383 | 0.555205 | 1396 | 18984 |
| high_persistence | 76 | -0.004975 | -0.002097 | -0.291492 | 0.097965 | 0.008185 | 0.722703 | 533 | 8837 |
| other_persistence | 166 | 0.002490 | 0.002519 | -0.268314 | 0.118445 | 0.009889 | 0.451004 | 1332 | 17433 |

### Highest Risk-Memory Days
| date | portfolio_return | residual_return | drawdown | stress_memory_score | residual_roughness | residual_volatility | consecutive_negative_portfolio_days | rolling_negative_portfolio_share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-11-02 | 0.035404 | 0.023396 | -0.199058 | 0.229211 | 0.011160 | 0.012097 | 0 | 0.500000 |
| 2022-11-03 | -0.005302 | 0.002831 | -0.203304 | 0.228395 | 0.010166 | 0.011818 | 1 | 0.600000 |
| 2022-11-04 | 0.039608 | 0.006913 | -0.171748 | 0.227910 | 0.009763 | 0.010731 | 0 | 0.500000 |
| 2022-11-01 | 0.035885 | 0.000126 | -0.226445 | 0.227351 | 0.009368 | 0.010447 | 0 | 0.600000 |
| 2022-11-07 | 0.011161 | 0.009003 | -0.162504 | 0.225201 | 0.009642 | 0.010687 | 0 | 0.400000 |
| 2022-10-31 | 0.007544 | 0.016758 | -0.253243 | 0.225136 | 0.010026 | 0.010838 | 0 | 0.700000 |
| 2022-10-28 | -0.041812 | -0.017079 | -0.258834 | 0.222900 | 0.008372 | 0.009739 | 2 | 0.700000 |
| 2022-10-27 | -0.003025 | 0.004019 | -0.226492 | 0.222062 | 0.009300 | 0.010446 | 1 | 0.600000 |
| 2022-10-26 | 0.021391 | 0.013272 | -0.224145 | 0.220742 | 0.010302 | 0.010764 | 0 | 0.500000 |
| 2022-11-08 | -0.007509 | -0.000630 | -0.168792 | 0.220371 | 0.009403 | 0.010516 | 1 | 0.400000 |
| 2022-10-25 | -0.004649 | -0.003019 | -0.240393 | 0.218244 | 0.009500 | 0.010500 | 3 | 0.500000 |
| 2022-10-24 | -0.019042 | 0.010218 | -0.236846 | 0.216235 | 0.009446 | 0.010458 | 2 | 0.500000 |

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
| 2022-10-13 | 0.005682 | -0.008361 | 0.014043 | -0.240162 | 1 | 233 | 281 |
| 2022-10-24 | -0.019042 | -0.029261 | 0.010218 | -0.236846 | 9 | 109 | 281 |

## Diagnostic Flags
- `absolute_risk_survival_issue`
- `missed_winners_exceed_accepted_losers`
- `accepted_losers_present`
- `loss_persistence_cluster`
