# Risk Transient Factor Attribution: phase8_same_model_attribution_20260519

- Guardrail: diagnostic_only_not_trading_signal
- Next action: review_transient_bottlenecks_before_any_strategy_change

## Summary
- days: 572
- mean_portfolio_return: 0.000658
- mean_benchmark_return: 0.000684
- mean_residual_return: -2.6e-05
- hit_rate: 0.465035
- worst_drawdown: -0.219993

## Risk Regimes
- all_days: days=572, mean_residual_return=-2.6e-05, mean_drawdown=-0.09914, residual_share=-0.014843
- positive_residual: days=266, mean_residual_return=0.006774, mean_drawdown=-0.092704, residual_share=1.801944
- negative_residual: days=304, mean_residual_return=-0.005976, mean_drawdown=-0.10496, residual_share=-1.816788
- drawdown_stress: days=506, mean_residual_return=-0.000509, mean_drawdown=-0.111291, residual_share=-0.257594

## Event Attribution
- events: 157562
- accepted_count: 8520
- rejected_count: 149042
- missed_winner_count: 69682
- accepted_loser_count: 4115
- accepted_mean_forward_return: 0.001858
- rejected_mean_forward_return: 0.000469
- missed_winner_mean_forward_return: 0.01715

## Diagnostic Flags
- negative_average_residual_return
- residual_underperforms_during_drawdown_stress
- missed_winners_exceed_accepted_losers
