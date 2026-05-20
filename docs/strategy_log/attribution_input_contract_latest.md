# Attribution Input Contract Report

- Overall status: ready_for_transient_diagnostic
- Next action: implement_risk_transient_factor_attribution_v0

## Requirements
### portfolio_returns
- Status: ready
- Description: Daily portfolio and benchmark returns for residual attribution.
- Candidate path: `backtest_results/agent_runs/phase8_same_model_attribution_20260519_portfolio_returns.csv`
- Missing columns:
- Available columns: date, portfolio_return, benchmark_return, cost, excess_return

### risk_exposures
- Status: ready
- Description: Date-level risk exposures or risk model inputs for transient factor diagnostics.
- Candidate path: `backtest_results/agent_runs/phase8_same_model_attribution_20260519_risk_exposures.csv`
- Missing columns:
- Available columns: date, portfolio_return, benchmark_return, residual_return, drawdown, abs_residual_return

### candidate_events
- Status: ready
- Description: Generated/accepted/rejected candidate events for missed-winner and avoided-loser attribution.
- Candidate path: `backtest_results/agent_runs/phase8_same_model_attribution_20260519_candidate_events.csv`
- Missing columns:
- Available columns: date, instrument, decision, rejection_reason, score, rank, forward_return

## Guardrails
- Use only local artifacts; do not refresh market data automatically.
- Do not run full WFV, live notifications, or trading-like actions from this diagnostic.
- Transient factors are attribution evidence, not trading signals.
