# Phase 8 WFV fold attribution export conclusion — 2026-05-19

## Scope
- Added capability only.
- No full WFV run.
- No data refresh.
- No rebalance, trading action, promotion, or live notification.

## Problem
The `gate_m008` failure attribution showed that existing WFV artifacts only persisted fold-level metrics. That was enough to localize the blocker to 2022, but not enough to inspect real daily drawdown segments, candidate events, accepted losers, missed winners, or gate-switch whipsaw.

## Change
`run_walk_forward_validation.py` now supports an opt-in flag:

```bash
--export-attribution-inputs
```

When enabled, each fold backtest receives:

```bash
--export-attribution-inputs --run-id <fold_tag>
```

The fold tag is deterministic and already used by WFV:

```text
wf_<train_universe>_<fold_name>_<run_id>
```

Example for a future run:

```text
wf_csi1000_test_2022_phase8_regime_gate_grid_m008_full_wfv_20260519
```

## Guardrails
- Default behavior is unchanged: WFV does not export attribution inputs unless explicitly requested.
- The new flag only passes through to `run_backtest.py`; it does not change training, model selection, strategy ranking, costs, or WFV summary logic.
- This does not promote `gate_m008` and does not alter any daily/default config.

## Tests
Added focused TDD coverage in:

```text
test/test_walk_forward_attribution_export.py
```

Covered behavior:
- export enabled: fold backtest command contains `--export-attribution-inputs` and deterministic `--run-id`.
- export disabled: fold backtest command does not contain either flag.

## Current status
`capability_ready_not_materialized`

The capability is now wired and tested, but no new WFV run was launched in this iteration. The next real use should be a narrow or already-approved WFV rerun with this flag enabled, specifically to materialize fold-level attribution inputs for failure analysis.

## Next recommended action
Run only if explicitly approved:

```bash
PYTHONHASHSEED=42 ./.venv/bin/python run_walk_forward_validation.py \
  --train-universes csi1000 \
  --eval-market csi300 \
  --topk 15 \
  --n-drop 3 \
  --hold-thresh 8 \
  --workers 1 \
  --grid-workers 1 \
  --train-config config/csi1000_transient_repair_regime_gated_svs_m008.yaml \
  --with-extra-factors \
  --export-attribution-inputs \
  --run-id <approved_run_id>
```

Then analyze the real per-fold CSVs under `backtest_results/agent_runs/`.
