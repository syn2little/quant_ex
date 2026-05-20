# Phase 8 Same-Model Attribution Inputs Ready - 2026-05-19

## Scope

This iteration ran one narrow local same-model backtest to materialize real attribution input artifacts.

No full WFV was run. No data refresh was run. No rebalance or live-trading action was performed.

## Command

```bash
PYTHONHASHSEED=42 ./.venv/bin/python run_backtest.py \
  --model-path models/lgbm_csi1000_balanced_20260429_002424.pkl \
  --market csi300 \
  --topk 15 \
  --n-drop 3 \
  --hold-thresh 8 \
  --grid-workers 1 \
  --export-attribution-inputs \
  --run-id phase8_same_model_attribution_20260519
```

## Backtest Metrics

```text
market: csi300
topk: 15
n_drop: 3
hold_thresh: 8
cum_return: 0.369
annual_return: 0.1484
annual_vol: 0.2353
sharpe: 0.6306
max_drawdown: -0.22
calmar: 0.6745
win_rate: 0.4825
sortino: 0.9397
n_days: 572
excess_annual_return: -0.0203
information_ratio: -0.0471
tracking_error: 0.1389
beta: 1.0462
alpha: -0.0281
ic: 0.0427
icir: 0.3316
rank_ic: 0.0536
rank_icir: 0.4024
ic_days: 564
```

Interpretation: this run is for attribution-input materialization only. The same-model backtest has positive absolute Sharpe but negative annual alpha / IR versus benchmark, so it is not a promotion signal.

## Generated Artifacts

```text
backtest_results/agent_runs/phase8_same_model_attribution_20260519_portfolio_returns.csv
rows: 572
columns: date, portfolio_return, benchmark_return, cost, excess_return

backtest_results/agent_runs/phase8_same_model_attribution_20260519_risk_exposures.csv
rows: 572
columns: date, portfolio_return, benchmark_return, residual_return, drawdown, abs_residual_return

backtest_results/agent_runs/phase8_same_model_attribution_20260519_candidate_events.csv
rows: 157562
columns: date, instrument, decision, rejection_reason, score, rank, forward_return
```

## Contract Status

Contract report refreshed:

```text
docs/strategy_log/attribution_input_contract_latest.md
```

Current contract:

```text
overall_status: ready_for_transient_diagnostic
next_action: implement_risk_transient_factor_attribution_v0
```

This completes the transition from `blocked_missing_contract` to `ready_for_transient_diagnostic`.

## Verification

Passed:

```text
./.venv/bin/python -m pytest test/test_run_backtest_attribution_export.py test/test_phase8_attribution_input_export.py test/test_phase8_attribution_input_contract.py -q
./.venv/bin/python -m compileall run_backtest.py agent/strategy_iteration/attribution_input_export.py test/test_run_backtest_attribution_export.py
git diff --check -- run_backtest.py test/test_run_backtest_attribution_export.py docs/strategy_log/attribution_input_contract_latest.md
```

## Next Action

Implement `risk_transient_factor_attribution_v0` using only the generated local artifacts. Guardrail: transient factors are diagnostic evidence, not trading signals.
