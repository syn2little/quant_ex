# Phase 8 Risk Transient Factor Attribution v0 Conclusion - 2026-05-19

## Scope

This iteration implemented and ran a diagnostic-only transient attribution pass using existing local artifacts.

No full WFV was run. No data refresh was run. No rebalance, notification, or trading-like action was performed.

## Implemented

- New module: `agent/strategy_iteration/transient_attribution.py`
- New CLI: `run_transient_attribution.py`
- New tests: `test/test_phase8_transient_attribution.py`
- Generated diagnostic report: `docs/strategy_log/phase8_risk_transient_factor_attribution_v0_2026-05-19.md`

## Inputs

```text
backtest_results/agent_runs/phase8_same_model_attribution_20260519_portfolio_returns.csv
backtest_results/agent_runs/phase8_same_model_attribution_20260519_risk_exposures.csv
backtest_results/agent_runs/phase8_same_model_attribution_20260519_candidate_events.csv
```

## Diagnostic Findings

```text
days: 572
mean_portfolio_return: 0.000658
mean_benchmark_return: 0.000684
mean_residual_return: -0.000026
hit_rate: 0.465035
worst_drawdown: -0.219993
```

Risk regimes:

```text
all_days: residual_share=-0.014843
positive_residual: days=266, residual_share=1.801944
negative_residual: days=304, residual_share=-1.816788
drawdown_stress: days=506, mean_residual_return=-0.000509, residual_share=-0.257594
```

Candidate event attribution:

```text
events: 157562
accepted_count: 8520
rejected_count: 149042
missed_winner_count: 69682
accepted_loser_count: 4115
accepted_mean_forward_return: 0.001858
rejected_mean_forward_return: 0.000469
missed_winner_mean_forward_return: 0.017150
```

Diagnostic flags:

```text
negative_average_residual_return
residual_underperforms_during_drawdown_stress
missed_winners_exceed_accepted_losers
```

## Interpretation

The same-model run still has a small negative residual versus benchmark, with underperformance concentrated during drawdown-stress days. Candidate-event evidence indicates many rejected names later had positive forward returns, so the current selection threshold/ranking filter may be discarding upside; however, this is attribution evidence only and must not be used as a trading signal.

## Verification

Passed:

```text
./.venv/bin/python -m pytest test/test_phase8_transient_attribution.py test/test_run_backtest_attribution_export.py test/test_phase8_attribution_input_export.py test/test_phase8_attribution_input_contract.py -q
./.venv/bin/python -m compileall agent/strategy_iteration/transient_attribution.py run_transient_attribution.py test/test_phase8_transient_attribution.py
git diff --check -- agent/strategy_iteration/transient_attribution.py run_transient_attribution.py test/test_phase8_transient_attribution.py docs/strategy_log/phase8_risk_transient_factor_attribution_v0_2026-05-19.md
```

## Next Action

Use this diagnostic to design one narrow, cheap experiment before any WFV spend. Candidate direction: test whether a softer selection threshold or stress-regime filter reduces missed-winner loss without worsening drawdown. Any experiment must still be validated by same-model backtest first, then WFV before promotion.
