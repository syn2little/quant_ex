# Phase 8 Risk-Cap Exporter Review 2026-05-22

## Scope

Reviewed the diagnostic-only risk-cap exporter and attribution input contract surface:

- `agent/strategy_iteration/risk_cap.py`
- `agent/strategy_iteration/attribution_input_export.py`
- `agent/strategy_iteration/attribution_inputs.py`
- `run_backtest.py`
- Phase 8 attribution/risk-cap tests

## Finding Fixed

The optional risk-cap contract validator ignored blank `decision_label` cells when checking whether all risk-cap diagnostics were `diagnostic_only`. This meant a mixed file containing `diagnostic_only` rows plus blank labels could be marked ready.

Fix: `_csv_column_values()` now includes blank stripped values, so blank labels make the optional risk-cap capability `invalid_decision_label`.

Regression: added `test_attribution_input_contract_rejects_blank_risk_cap_labels`.

## Contract Notes

- Risk-cap diagnostics remain disabled by default.
- CLI guardrail is present: `--export-risk-cap-diagnostics` requires `--export-attribution-inputs`.
- Exported risk-cap rows and summary use `decision_label=diagnostic_only`.
- The exporter uses lagged volatility and lagged drawdown inputs for the counterfactual state machine.
- The contract marks optional risk-cap artifacts as non-promotion evidence.

## Validation

- Requested command with `./.venv/bin/python` could not run because this isolated worktree has no `.venv`.
- Fallback command with `/Users/weidian/code/quant_ex/.venv/bin/python` initially exposed the worktree import-name issue.
- Final validation used a temporary `/private/tmp/quant_ex` symlink to make this worktree importable as `quant_ex`.

Result:

```text
16 passed in 0.81s
```

`git diff --check` passed.

## Residual Risk

No WFV, data refresh, rebalance, notifications, strategy promotion, or default/daily config edits were run or changed.
