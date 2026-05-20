# Risk Transient Factor Attribution: phase8_transient_repair_soft_svs_20260519

- Guardrail: diagnostic_only_not_trading_signal
- Next action: review_transient_bottlenecks_before_any_strategy_change

## Summary
- days: 572
- mean_portfolio_return: 0.001243
- mean_benchmark_return: 0.000684
- mean_residual_return: 0.000559
- hit_rate: 0.533217
- worst_drawdown: -0.117744

## Risk Regimes
- all_days: days=572, mean_residual_return=0.000559, mean_drawdown=-0.026154, residual_share=0.31951
- positive_residual: days=305, mean_residual_return=0.006283, mean_drawdown=-0.022937, residual_share=1.91618
- negative_residual: days=265, mean_residual_return=-0.006025, mean_drawdown=-0.029951, residual_share=-1.59667
- drawdown_stress: days=273, mean_residual_return=-0.000828, mean_drawdown=-0.048032, residual_share=-0.225988

## Event Attribution
- events: 75509
- accepted_count: 8220
- rejected_count: 67289
- missed_winner_count: 31311
- accepted_loser_count: 4010
- accepted_mean_forward_return: 0.001164
- rejected_mean_forward_return: 0.000456
- missed_winner_mean_forward_return: 0.017895

## Diagnostic Flags
- residual_underperforms_during_drawdown_stress
- missed_winners_exceed_accepted_losers
