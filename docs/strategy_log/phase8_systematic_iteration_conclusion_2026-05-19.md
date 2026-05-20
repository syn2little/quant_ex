# Phase8 Systematic Iteration Conclusion: Transient Risk Attribution

## Scope

This iteration follows the Knowledge Scout recommendation to evaluate `risk_transient_factor_attribution_v0` before spending any WFV or trading-like budget.

Guardrails used in this run:

- Local-only dry-run and no LLM planner execution.
- No full WFV, no data refresh, no live notification, no rebalance command.
- Transient statistical factors are treated as attribution diagnostics, not trading signals.
- `rejected_candidate_attribution_v0` is only a feasibility inventory in this cycle.

## What Ran

1. Planner run:
   - `docs/strategy_log/agent_runs/phase8_risk_transient_system_iteration`
   - Objective explicitly requested a transient factor attribution primary experiment and rejected-candidate feasibility diagnostic.

2. Evidence audit:
   - `docs/strategy_log/phase8_systematic_iteration_evidence_audit_2026-05-19.md`

3. Attribution input contract:
   - `docs/strategy_log/phase8_attribution_input_contract_2026-05-19.md`
   - New pure-local detector: `agent/strategy_iteration/attribution_inputs.py`
   - Context integration: `agent/strategy_iteration/context.py`
   - Tests: `test/test_phase8_attribution_input_contract.py`

## Key Finding

`risk_transient_factor_attribution_v0` should not proceed directly to PCA/ICA/sparse-PCA implementation yet.

Reason: the repository does not currently expose the minimum durable local artifacts required for reliable transient risk attribution:

- `portfolio_returns`: missing artifact with required columns `date`, `portfolio_return`, `benchmark_return`.
- `risk_exposures`: missing artifact with required columns `date`, `portfolio_return`, `benchmark_return`.
- `candidate_events`: missing artifact with required columns `date`, `instrument`, `decision`, `forward_return`.

The current Phase7 fallback can compare candidate-level WFV summaries from `config/strategy_candidates.yaml`, but it is not enough for residual-return transient factor diagnostics.

## Planner Quality Finding

The no-LLM planner accepted the budget discipline, but the offline role templates reverted to generic Phase7 attribution arms instead of producing transient-factor-specific steps. This is acceptable as a safety gate, but insufficient as implementation evidence.

Therefore the system iteration had to add a concrete input-contract detector before any model work.

## Decision

Status: `blocked_missing_contract`

Next action: `define_or_generate_attribution_inputs`

This is a useful stop, not a failure. It prevents a premature transient-factor implementation from fitting noise or inventing unavailable inputs.

## Next Iteration

Primary task: `attribution_input_export_v0`

Goal: add a disabled-by-default local exporter that can create the following artifacts from existing backtest/strategy outputs when available:

1. `backtest_results/agent_runs/<run_id>_portfolio_returns.csv`
   - Required columns: `date`, `portfolio_return`, `benchmark_return`.
   - Optional columns: `position_count`, `turnover`, `strategy_return`.

2. `backtest_results/agent_runs/<run_id>_risk_exposures.csv`
   - Required columns: `date`, `portfolio_return`, `benchmark_return`.
   - Optional columns: `market_exposure`, `size_exposure`, `value_exposure`, `industry_exposure`.

3. `backtest_results/agent_runs/<run_id>_candidate_events.csv`
   - Required columns: `date`, `instrument`, `decision`, `forward_return`.
   - Optional columns: `rejection_reason`, `score`, `rank`, `weight`.

Cheap diagnostic: extend the contract detector to point to the exact missing upstream command or source file instead of only reporting missing artifacts.

Stop condition: if these artifacts cannot be reconstructed from existing outputs without a full WFV or data refresh, request explicit approval for the narrowest local generation command.

## Verification

Run locally:

```bash
./.venv/bin/python -m pytest test/test_phase8_attribution_input_contract.py -q
./.venv/bin/python -m compileall agent/strategy_iteration run_agent_strategy_iteration.py
```

Expected result: contract tests pass and the context pack includes `artifact_summaries.attribution_input_contract`.
