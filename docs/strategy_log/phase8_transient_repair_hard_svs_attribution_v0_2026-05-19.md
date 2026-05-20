# Risk Transient Factor Attribution: phase8_transient_repair_hard_svs_20260519

- Guardrail: diagnostic_only_not_trading_signal
- Next action: review_transient_bottlenecks_before_any_strategy_change

## Summary
- days: 572
- mean_portfolio_return: 0.001223
- mean_benchmark_return: 0.000684
- mean_residual_return: 0.000539
- hit_rate: 0.515734
- worst_drawdown: -0.151996

## Risk Regimes
- all_days: days=572, mean_residual_return=0.000539, mean_drawdown=-0.043806, residual_share=0.308517
- positive_residual: days=295, mean_residual_return=0.006424, mean_drawdown=-0.039651, residual_share=1.895211
- negative_residual: days=275, mean_residual_return=-0.00577, mean_drawdown=-0.048262, residual_share=-1.586694
- drawdown_stress: days=405, mean_residual_return=-0.000746, mean_drawdown=-0.059288, residual_share=-0.30213

## Event Attribution
- events: 59963
- accepted_count: 8220
- rejected_count: 51743
- missed_winner_count: 23987
- accepted_loser_count: 4016
- accepted_mean_forward_return: 0.001047
- rejected_mean_forward_return: 0.000446
- missed_winner_mean_forward_return: 0.018529

## Diagnostic Flags
- residual_underperforms_during_drawdown_stress
- missed_winners_exceed_accepted_losers
