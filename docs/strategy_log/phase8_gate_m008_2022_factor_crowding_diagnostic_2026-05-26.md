# Factor Crowding Diagnostic: phase8_gate_m008_2022_factor_crowding_20260526

## Factor Crowding / Co-movement Diagnostic
- Guardrail: `diagnostic_only_not_trading_signal`
- Next action: `review_crowding_proxy_with_risk_memory_without_signal_promotion`

This is a diagnostic-only read of local attribution artifacts. It is not alpha evidence, not a portfolio rule, and not a trading signal.

## Summary
- days: 242
- events: 60542
- accepted_count: 3615
- rejected_count: 56927
- accepted_loser_count: 1865
- missed_winner_count: 26270
- mean_residual_return: 0.001070
- worst_drawdown: -0.291492
- stress_drawdown_threshold: -0.050000
- high_abs_residual_cutoff: 0.012776
- stress_days: 196
- stress_cluster_days: 23
- event_concentration_days: 181
- missed_winner_cluster_days: 241
- accepted_loser_top_day_share: 0.008043
- missed_winner_top_day_share: 0.009669

## Crowding Buckets

### Stress Cluster Days
| date | residual_return | drawdown | abs_residual | accepted_losers | missed_winners | events | co_movement_proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-04-26 | -0.023607 | -0.291492 | 0.023607 | 2 | 227 | 278 | 1 |
| 2022-04-25 | -0.018687 | -0.268314 | 0.018687 | 12 | 82 | 278 | 1 |
| 2022-04-28 | -0.014293 | -0.261996 | 0.014293 | 1 | 223 | 278 | 0 |
| 2022-10-10 | -0.020781 | -0.259097 | 0.020781 | 6 | 125 | 281 | 1 |
| 2022-10-28 | -0.017079 | -0.258834 | 0.017079 | 11 | 93 | 281 | 1 |
| 2022-09-28 | -0.015897 | -0.215375 | 0.015897 | 6 | 101 | 281 | 1 |
| 2022-04-22 | -0.017008 | -0.214838 | 0.017008 | 15 | 8 | 278 | 0 |
| 2022-04-13 | -0.013213 | -0.195551 | 0.013213 | 0 | 203 | 279 | 1 |
| 2022-04-19 | -0.019369 | -0.170725 | 0.019369 | 10 | 66 | 279 | 1 |
| 2022-03-16 | -0.013625 | -0.159602 | 0.013625 | 0 | 199 | 279 | 1 |
| 2022-09-13 | -0.018563 | -0.158725 | 0.018563 | 12 | 35 | 281 | 0 |
| 2022-05-26 | -0.023281 | -0.155180 | 0.023281 | 10 | 104 | 278 | 0 |

### Event Concentration Days
| date | residual_return | drawdown | abs_residual | accepted_losers | missed_winners | events | co_movement_proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-09-30 | -0.010605 | -0.225932 | 0.010605 | 15 | 57 | 281 | 1 |
| 2022-09-27 | 0.010421 | -0.189241 | 0.010421 | 15 | 35 | 281 | 1 |
| 2022-08-23 | -0.010728 | -0.125487 | 0.010728 | 15 | 21 | 280 | 1 |
| 2022-05-05 | 0.012169 | -0.204373 | 0.012169 | 15 | 32 | 279 | 0 |
| 2022-04-22 | -0.017008 | -0.214838 | 0.017008 | 15 | 8 | 278 | 0 |
| 2022-04-08 | -0.006885 | -0.147108 | 0.006885 | 15 | 26 | 277 | 0 |
| 2022-03-28 | -0.008966 | -0.155535 | 0.008966 | 15 | 90 | 279 | 1 |
| 2022-03-14 | -0.007777 | -0.139153 | 0.007777 | 15 | 13 | 279 | 1 |
| 2022-03-11 | 0.023996 | -0.104802 | 0.023996 | 15 | 18 | 279 | 1 |
| 2022-03-04 | 0.006879 | -0.075111 | 0.006879 | 15 | 25 | 279 | 1 |
| 2022-03-02 | -0.005436 | -0.049036 | 0.005436 | 15 | 120 | 279 | 1 |
| 2022-02-10 | -0.012711 | -0.100506 | 0.012711 | 15 | 72 | 279 | 1 |

### Missed Winner Cluster Days
| date | residual_return | drawdown | abs_residual | accepted_losers | missed_winners | events | co_movement_proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-11-03 | 0.002831 | -0.203304 | 0.002831 | 0 | 254 | 281 | 1 |
| 2022-03-15 | -0.006097 | -0.183776 | 0.006097 | 0 | 253 | 279 | 1 |
| 2022-08-10 | -0.000796 | -0.101585 | 0.000796 | 1 | 238 | 280 | 1 |
| 2022-10-31 | 0.016758 | -0.253243 | 0.016758 | 0 | 235 | 281 | 0 |
| 2022-11-10 | 0.015986 | -0.138417 | 0.015986 | 1 | 234 | 281 | 0 |
| 2022-11-28 | 0.006204 | -0.095213 | 0.006204 | 1 | 233 | 281 | 1 |
| 2022-10-13 | 0.014043 | -0.240162 | 0.014043 | 1 | 233 | 281 | 0 |
| 2022-03-29 | -0.009497 | -0.166473 | 0.009497 | 0 | 233 | 279 | 1 |
| 2022-11-14 | 0.052156 | -0.035138 | 0.052156 | 0 | 228 | 281 | 1 |
| 2022-10-11 | -0.002476 | -0.259588 | 0.002476 | 0 | 227 | 281 | 0 |
| 2022-04-26 | -0.023607 | -0.291492 | 0.023607 | 2 | 227 | 278 | 1 |
| 2022-06-22 | -0.012042 | -0.106602 | 0.012042 | 3 | 225 | 279 | 1 |

## Diagnostic Flags
- `factor_crowding_proxy_stress_cluster`
- `event_concentration_cluster`
- `missed_winner_cluster`

## Inputs
- portfolio_returns_csv: `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_portfolio_returns.csv`
- risk_exposures_csv: `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_risk_exposures.csv`
- candidate_events_csv: `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_candidate_events.csv`
