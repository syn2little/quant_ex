# Phase7 Contribution Validation

Date: 2026-05-18

## Core Question

Phase7 should not be treated as strategy alpha by default. It is useful only if it improves research allocation: fewer repeated dead ends, clearer bottleneck diagnosis, and a better next experiment.

## What Phase7 Can Contribute

Phase7 can contribute at three levels:

1. Research discipline: the agent must name control, candidate, bottleneck, primary experiment, cheap diagnostic, and kill criteria.
2. Budget efficiency: the plan should shrink from broad multi-arm exploration to one major experiment plus one diagnostic.
3. Indirect strategy improvement: later WFV experiments should focus on `adaptive_dd20_wf` return repair without destroying its stability edge.

Phase7 does not directly contribute:

- A new factor.
- A new model.
- A live trading decision.
- A promoted strategy candidate.

## Minimal Validation Protocol

### 1. Smoke-test the planner output

```bash
./.venv/bin/python run_agent_strategy_iteration.py \
  --objective "Phase 7: Agent Performance Attribution and Experiment Budgeting" \
  --run-id phase7_agent_attribution_smoke \
  --no-llm \
  --no-memory \
  --discussion-mode meeting \
  --meeting-max-rounds 3 \
  --meeting-max-roles-per-round 2
```

Pass criteria:

- `docs/strategy_log/agent_runs/phase7_agent_attribution_smoke/attribution_report.md` exists.
- `plan.md` contains exactly one `primary_experiment` and one `cheap_diagnostic`.
- The plan includes explicit kill criteria.

### 2. Compare pre/post plan quality

Run or inspect a pre-Phase7-style objective and compare:

- Does the old plan emit broad Phase1 infrastructure arms?
- Does the new plan focus on `adaptive_dd20_wf` return repair?
- Does the new plan explicitly avoid refuted routes such as always-on SVS, fundamental top70, or broad model changes?

Pass criteria:

- Phase7 narrows the next action to a single testable research question.
- Phase7 does not claim promotion without WFV evidence.

### 3. Run one cheap diagnostic before WFV

The next experiment should be a narrow return-repair diagnostic around `adaptive_dd20_wf`.

Pass criteria:

- The diagnostic preserves the stability hypothesis before any full WFV spend.
- If it cannot preserve 7/7 positive folds or drawdown advantage, stop early.

### 4. Only then judge strategy contribution

Phase7 contributes to the strategy only if the following downstream result appears:

- Full WFV improves IR or Sharpe versus the chosen control, and
- MaxDD, turnover, concentration, and cost do not materially regress, and
- The improvement can be traced back to the Phase7-selected experiment rather than unrelated manual exploration.

If these are not true, Phase7 is still acceptable as infrastructure if it prevented wasted experiments, but it should not be credited as alpha.

## Current Baseline Reading

Current fallback attribution uses `config/strategy_candidates.yaml` because fold-level `walk_forward_summary.csv` artifacts for the default pair are not present.

- Control: `adaptive_baseline_wf`
- Candidate: `adaptive_dd20_wf`
- Bottleneck: `return_repair`
- Mean Sharpe delta: `-0.0458`
- Worst drawdown delta: `+0.0437`

Interpretation: `adaptive_dd20_wf` is a stability base. The next strategy experiment should try to repair return while preserving stability, not replace the agent layer again.
