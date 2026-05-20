# Phase 8 WFV fold attribution export materialized — 2026-05-19

## Scope
- Materialized one WFV fold only: `test_2022`.
- Candidate fixed to `gate_m008`.
- No parameter search beyond the fixed topk/n_drop/hold row.
- No data refresh.
- No rebalance, trading action, promotion, or live notification.

## Command
```bash
PYTHONHASHSEED=42 ./.venv/bin/python run_walk_forward_validation.py \
  --train-universes csi1000 \
  --eval-market csi300 \
  --topk 15 \
  --n-drop 3 \
  --hold-thresh 8 \
  --workers 1 \
  --grid-workers 1 \
  --folds-config config/phase8_single_fold_2022_wfv.yaml \
  --train-config config/csi1000_transient_repair_regime_gated_svs_m008.yaml \
  --with-extra-factors \
  --export-attribution-inputs \
  --run-id phase8_gate_m008_single_fold_2022_attr_20260519
```

## WFV result
- report: `optimization_results/walk_forward_phase8_gate_m008_single_fold_2022_attr_20260519/walk_forward_report.md`
- fold rows: `optimization_results/walk_forward_phase8_gate_m008_single_fold_2022_attr_20260519/walk_forward_all_results.csv`
- fold: 2022
- annual return: -1.35%
- Sharpe: -0.0424
- max drawdown: -29.15%
- information ratio: 1.3398
- alpha: 26.19%

## Attribution artifacts
Run id:

```text
wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519
```

Generated files:

| artifact | rows | columns |
| --- | ---: | --- |
| `portfolio_returns` | 242 | `date`, `portfolio_return`, `benchmark_return`, `cost`, `excess_return` |
| `risk_exposures` | 242 | `date`, `portfolio_return`, `benchmark_return`, `residual_return`, `drawdown`, `abs_residual_return` |
| `candidate_events` | 60542 | `date`, `instrument`, `decision`, `rejection_reason`, `score`, `rank`, `forward_return` |

Paths:
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_portfolio_returns.csv`
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_risk_exposures.csv`
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_candidate_events.csv`

## Status
`wfv_fold_attribution_inputs_materialized`

The WFV fold export capability is verified end-to-end. The next diagnostic can now use real 2022 daily returns and candidate events instead of fold-level approximations.

## Next action
Run a read-only daily failure attribution on these three materialized CSVs. Do not tune thresholds or promote the config from this materialization run.
