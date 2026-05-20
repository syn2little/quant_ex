# Phase 8 Backtest Attribution Export Integration - 2026-05-19

## Scope

This iteration only wired the local attribution input exporter into the ordinary `run_backtest.py` flow behind an opt-in flag.

No full WFV was run. No data refresh was run. No rebalance or live-trading action was performed.

## Completed

- Added `run_backtest.py --export-attribution-inputs`.
- Added optional `run_backtest.py --run-id <id>` for deterministic attribution artifact names.
- Kept attribution export disabled by default.
- Export path: `backtest_results/agent_runs/`.
- Exported files when enabled:
  - `<run_id>_portfolio_returns.csv`
  - `<run_id>_risk_exposures.csv`
  - `<run_id>_candidate_events.csv` when signal and price data produce forward-return events
- Added `test/test_run_backtest_attribution_export.py` to cover the opt-in backtest integration.

## Current Status

```text
backtest_export_path_ready_but_not_run_on_real_artifacts_yet
```

The exporter is now reachable from the normal local backtest path, but this iteration still did not run a real narrow same-model backtest. Therefore the repository's current contract status is expected to remain unchanged until a real run writes artifacts under `backtest_results/agent_runs/`.

## Verification

Passed:

```text
./.venv/bin/python -m pytest test/test_run_backtest_attribution_export.py::test_run_backtest_exports_attribution_inputs_when_enabled -q
./.venv/bin/python -m pytest test/test_run_backtest_attribution_export.py test/test_phase8_attribution_input_export.py test/test_phase8_attribution_input_contract.py -q
./.venv/bin/python -m compileall run_backtest.py agent/strategy_iteration/attribution_input_export.py test/test_run_backtest_attribution_export.py
PYTHONHASHSEED=42 ./.venv/bin/python run_backtest.py --help | rg -- '--export-attribution-inputs|--run-id'
git diff --check -- run_backtest.py test/test_run_backtest_attribution_export.py
```

Full local test suite result:

```text
483 passed, 12 skipped, 2 failed, 1 warning
```

The two failures are existing web route expectations unrelated to this iteration:

```text
test/test_web_console_data.py::test_data_explorer_page_serves -> 404 != 200
test/test_web_console_models.py::test_models_page_serves -> 404 != 200
```

Repository-wide `git diff --check` is blocked by an unrelated pre-existing whitespace issue:

```text
docs/strategy_log/agent_memory.md:167: new blank line at EOF.
```

The scoped diff check for files touched in this iteration passed.

## Next Action

Run a narrow same-model local backtest with attribution export enabled, for example:

```bash
./.venv/bin/python run_backtest.py \
  --model-path models/<candidate_model>.pkl \
  --market csi300 \
  --topk 15 \
  --n-drop 3 \
  --hold-thresh 8 \
  --grid-workers 1 \
  --export-attribution-inputs \
  --run-id phase8_same_model_attribution_20260519
```

If this produces real `*_portfolio_returns.csv`, `*_risk_exposures.csv`, and `*_candidate_events.csv`, the contract should be eligible to move from `blocked_missing_contract` toward `ready_for_transient_diagnostic`.
