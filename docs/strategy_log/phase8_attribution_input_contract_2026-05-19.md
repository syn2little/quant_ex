# Attribution Input Contract Report

- Overall status: blocked_missing_contract
- Next action: define_or_generate_attribution_inputs

## Requirements
### portfolio_returns
- Status: missing_artifact
- Description: Daily portfolio and benchmark returns for residual attribution.
- Candidate path: none
- Missing columns: benchmark_return, date, portfolio_return
- Available columns:

### risk_exposures
- Status: missing_artifact
- Description: Date-level risk exposures or risk model inputs for transient factor diagnostics.
- Candidate path: none
- Missing columns: benchmark_return, date, portfolio_return
- Available columns:

### candidate_events
- Status: missing_artifact
- Description: Generated/accepted/rejected candidate events for missed-winner and avoided-loser attribution.
- Candidate path: none
- Missing columns: date, decision, forward_return, instrument
- Available columns:

## Guardrails
- Use only local artifacts; do not refresh market data automatically.
- Do not run full WFV, live notifications, or trading-like actions from this diagnostic.
- Transient factors are attribution evidence, not trading signals.
