# System Diagnostic: 2026-05-17 Agent Evidence-Bound Loop

## Layer Scores
| Layer | Score | Weakest Link | Highest Leverage Fix |
|---|---:|---|---|
| Data | 4 | Agent plans could previously ignore known data/cache caveats. | Carry durable rejected paths, lag warnings, and default controls into every run context. |
| Factors | 4 | Factor ideas can repeat recently refuted fundamental/SVS paths. | Add a structured `research_constraints.do_not_repeat` list from candidate and strategy logs. |
| Model | 5 | No model-path change in this iteration. | Keep model execution behind approval and require model meta checks for strict csi1000 runs. |
| Backtest | 5 | Meeting mode could finish before all comparability roles spoke. | Add chair coverage gates for data/factor, validation, risk, experiment, and decision. |
| Execution | 5 | Codex task proposals existed but Web approval/execution lifecycle was incomplete. | Add agent task approval, selected execution, result/diff surfacing, and task status counts. |
| Web | 5 | AgentRuns did not expose `agent_tasks` as a first-class artifact. | Add Agent Tasks tab plus dashboard approval and execution controls. |

## Key Findings
1. The agent layer had enough mechanics, but not enough evidence binding: future prompts needed explicit default controls, metric policy, known traps, and do-not-repeat constraints.
2. Meeting mode now has a quality gate instead of just a turn cap; final synthesis records coverage and missing requirements.
3. Feedback now writes `next_iteration.json` and `next_iteration.md`, so a result can seed the next objective without losing comparability assumptions.
4. Web/API now support coding-agent task approvals and selected execution through `TaskManager` + SSE, while preserving explicit approval and isolated worktree defaults.
5. This iteration is infrastructure/product only. No training, full WFV, data update, notification, or trading-like workflow was executed.

## Decision
Keep the change as the next agent-loop baseline. It improves research discipline and dashboard operability without changing strategy candidates or live execution semantics.

## Validation
- `./.venv/bin/python -m compileall agent/strategy_iteration web/api/routers/agents.py web/api/services/agent_service.py run_agent_strategy_iteration.py`
- `./.venv/bin/python -m pytest test/test_agent_strategy_iteration.py test/test_web_dashboard.py`
- `cd web/frontend && npm run build`
- `./.venv/bin/python run_agent_strategy_iteration.py --objective "phase6 evidence-bound agent loop smoke" --run-id phase6_evidence_bound_smoke2 --output-dir /tmp/quant_ex_agent_runs --no-llm --no-memory --discussion-mode meeting --meeting-max-rounds 3 --meeting-max-roles-per-round 2 --propose-actions --use-agent --agent-mode readonly --agent-max-tasks 1 --write-agent-approval-template`
