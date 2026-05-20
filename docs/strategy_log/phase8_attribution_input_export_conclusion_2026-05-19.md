# Phase8 Systematic Iteration Conclusion: Attribution Input Export v0

## Scope

This iteration continued from `phase8_systematic_iteration_conclusion_2026-05-19.md`.

Goal: implement a disabled-by-default local exporter for attribution input artifacts, without running full WFV, refreshing data, notifying, or changing trading/rebalance behavior.

## What Changed

- Added `agent/strategy_iteration/attribution_input_export.py`.
- Added tests in `test/test_phase8_attribution_input_export.py`.
- Added a CLI contract writer to `run_agent_strategy_iteration.py`:

```bash
./.venv/bin/python run_agent_strategy_iteration.py --write-attribution-input-contract
```

The CLI exits with code `2` when the contract remains blocked, which makes missing artifacts visible in automation.

## Exporter Capabilities

### `portfolio_returns`

Input: qlib-style report DataFrame with `return`, optional `cost`, optional `bench`.

Output columns:

- `date`
- `portfolio_return`
- `benchmark_return`
- `cost` when present
- `excess_return`

### `risk_exposures`

Input: normalized portfolio returns.

Output columns:

- `date`
- `portfolio_return`
- `benchmark_return`
- `residual_return`
- `drawdown`
- `abs_residual_return`

This is intentionally minimal. It does not claim to be a full Barra-like risk model; it creates the minimum residual series required before transient factor attribution can be considered.

### `candidate_events`

Input: signal Series plus price data.

Output columns:

- `date`
- `instrument`
- `decision`
- `rejection_reason`
- `score`
- `rank`
- `forward_return`

Accepted rows are top-k by score; rejected rows are marked `score_threshold`. This supports the first feasibility layer for missed-winner / avoided-loser attribution.

## Current Repository Status

The exporter functions are implemented and tested, but no real backtest run was executed in this iteration. Therefore the live repository contract still reports:

```text
blocked_missing_contract
next_action: define_or_generate_attribution_inputs
```

This is expected because the exporter needs to be called from a completed local backtest/report object before files exist under `backtest_results/agent_runs/`.

## Decision

Status: `exporter_ready_but_no_real_artifacts_yet`

The system is now ready for the next narrow iteration: wire the exporter into a safe local backtest path behind an explicit flag, e.g.:

```bash
./.venv/bin/python run_backtest.py ... --export-attribution-inputs --run-id <id>
```

That wiring should export artifacts only after a normal local backtest completes. It must remain disabled by default.

## Guardrails

- Do not run full WFV from this path.
- Do not refresh market data.
- Do not mutate launchd or rebalance scripts.
- Do not treat residual/transient diagnostics as alpha or promotion evidence.
- Candidate events are diagnostic only; they are not trading instructions.

## Verification

```bash
./.venv/bin/python -m pytest test/test_phase8_attribution_input_contract.py test/test_phase8_attribution_input_export.py -q
./.venv/bin/python -m compileall agent/strategy_iteration run_agent_strategy_iteration.py
./.venv/bin/python run_agent_strategy_iteration.py --write-attribution-input-contract
```

Expected:

- tests pass;
- compile succeeds;
- contract writer emits `docs/strategy_log/attribution_input_contract_latest.md` and exits `2` while real artifacts are absent.
