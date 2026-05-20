# Phase 7 Agent Performance Attribution and Experiment Budgeting

Date: 2026-05-18

## Goal

Move the strategy agent from infrastructure planning toward evidence-bound performance diagnosis. Phase 7 makes every agent run carry a compact attribution report and limits Phase 7 planning to one primary experiment plus one cheap diagnostic.

## Implemented

- Added `agent/strategy_iteration/attribution.py`.
- Added `test/test_phase7_agent_attribution.py` with TDD coverage for:
  - fold-level control/candidate attribution,
  - performance evidence in the project context pack,
  - Phase 7 experiment budget gating.
- Extended `agent/strategy_iteration/context.py` to attach `artifact_summaries.performance_attribution`.
- Extended `agent/strategy_iteration/orchestrator.py` to:
  - save `attribution_report.json`,
  - save `attribution_report.md`,
  - emit Phase 7 arms only when the objective is attribution/budgeting oriented.
- Installed missing local test dependency `pytest` into `.venv`.

## Current Attribution Signal

The repo does not currently contain fold-level `walk_forward_summary.csv` artifacts for `adaptive_baseline_wf` and `adaptive_dd20_wf`, so the context pack falls back to `config/strategy_candidates.yaml`.

Current fallback comparison:

- Control: `adaptive_baseline_wf`
- Candidate: `adaptive_dd20_wf`
- Bottleneck: `return_repair`
- Mean Sharpe delta: `-0.0458`
- Worst drawdown delta: `+0.0437`
- Positive folds: `7`

Interpretation: `adaptive_dd20_wf` remains a stability base, not a return upgrade. The next approved research budget should focus on narrow return repair without damaging the all-positive-fold stability property.

## Budget Gate

For Phase 7 objectives, the planner now emits at most:

1. `phase7_primary_attribution_experiment`
2. `phase7_cheap_diagnostic`

Kill criteria are explicit in the generated plan. Full WFV remains outside the automatic planning loop and requires approval.

## Verification

Commands run:

```bash
./.venv/bin/python -m pytest test/test_phase7_agent_attribution.py -q
./.venv/bin/python -m pytest test/test_agent_strategy_iteration.py test/test_phase7_agent_attribution.py -q
./.venv/bin/python run_agent_strategy_iteration.py --objective "Phase 7: Agent Performance Attribution and Experiment Budgeting" --run-id phase7_agent_attribution_smoke --no-llm --no-memory --discussion-mode meeting --meeting-max-rounds 3 --meeting-max-roles-per-round 2
```

Results:

- Phase 7 focused tests: `3 passed`
- Agent suite plus Phase 7 tests: `47 passed`
- Smoke run written to `docs/strategy_log/agent_runs/phase7_agent_attribution_smoke`

## Next Research Step

Do not start by adding more roles or UI. The next research step is a narrow return-repair diagnostic around `adaptive_dd20_wf`, then decide whether a full WFV spend is justified.
