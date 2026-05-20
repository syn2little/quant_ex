# Phase 8 gate_m008 2022 daily failure attribution conclusion — 2026-05-19

## Scope
- Read-only diagnostic on already materialized WFV fold attribution inputs.
- No new backtest, no WFV, no data refresh, no rebalance, no trading action, no promotion.
- Candidate: `gate_m008`, fold: 2022.

## Artifacts
- Library: `agent/strategy_iteration/daily_failure_attribution.py`
- CLI: `run_daily_failure_attribution.py`
- Test: `test/test_phase8_daily_failure_attribution.py`
- Report: `docs/strategy_log/phase8_gate_m008_2022_daily_failure_attribution_v0_2026-05-19.md`

Input CSVs:
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_portfolio_returns.csv`
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_risk_exposures.csv`
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_candidate_events.csv`

## Key read
- days: 242
- mean portfolio return: 0.000145
- mean benchmark return: -0.000924
- mean residual return: 0.001070
- hit rate: 0.466942
- worst drawdown: -29.15%
- worst daily portfolio return: -6.81%

## Stress regime
Stress threshold: drawdown <= -5%.

- stress days: 196
- stress mean portfolio return: -0.000452
- stress mean residual return: 0.000404
- stress accepted loser count: 1496
- stress missed winner count: 22961

The stress residual remains positive on average, but absolute portfolio return is negative. This reinforces that the 2022 blocker is not mainly an alpha/ranking failure.

## Event attribution
- events: 60542
- accepted count: 3615
- rejected count: 56927
- accepted loser count: 1865
- missed winner count: 26270
- accepted mean forward return: 0.000185
- rejected mean forward return: -0.000653
- accepted loser mean forward return: -0.020165
- missed winner mean forward return: 0.018927

Missed winners are numerous, but rejected events are negative on average. That means simply loosening the selection threshold is not a clean fix.

## Worst drawdown dates
The deepest drawdown cluster is concentrated around late April and October 2022.

Top observed stress dates include:
- 2022-04-26: drawdown -29.15%, residual -0.023607, missed winners 227
- 2022-04-25: drawdown -26.83%, portfolio return -6.81%, residual -0.018687, accepted losers 12
- 2022-10-10: drawdown -25.91%, portfolio return -4.28%, residual -0.020781, accepted losers 6
- 2022-10-28: drawdown -25.88%, portfolio return -4.18%, residual -0.017079, accepted losers 11

## Diagnostic flags
- `absolute_risk_survival_issue`
- `missed_winners_exceed_accepted_losers`
- `accepted_losers_present`

## Conclusion
`portfolio_risk_cap_over_signal_tuning`

Do not continue threshold fitting and do not promote `gate_m008`. The daily evidence says 2022 remains an absolute-risk survival problem: alpha/residual behavior is not the primary blocker, while drawdown depth and high-volatility stress days are.

## Next action
If continuing, test a portfolio-layer risk cap with `gate_m008` fixed, not another signal threshold. The experiment should cap risk exposure during drawdown stress and verify whether it reduces April/October 2022 drawdown without damaging 2024-2026 performance.
