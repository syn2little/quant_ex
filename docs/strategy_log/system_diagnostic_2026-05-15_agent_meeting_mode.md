# System Diagnostic: 2026-05-15 Agent Meeting Mode

## Layer Scores
| Layer | Score | Weakest Link | Highest Leverage Fix |
|---|---:|---|---|
| Data | 4 | No data-path change in this iteration. | Keep data refresh and fetch commands approval-gated. |
| Factors | 4 | Factor ideation can still overrun evidence if all roles always speak. | Let the meeting chair call data/factor review only when the objective needs it. |
| Model | 5 | No model-path change in this iteration. | Keep model training outside automatic agent execution. |
| Backtest | 5 | Validation discipline depends on the right roles entering at the right time. | Allow chair-selected backtest/risk roles and record the rationale. |
| Execution | 5 | Re-running completed commands, mechanical role order, and unconstrained coding-agent delegation can make audit trails noisy or risky. | Default command execution skips already-successful commands; meeting mode records participation reasons; coding-agent work is proposal-only until approved. |
| Web | 5 | Agent Run creation previously exposed only fixed-order role flow and no coding-agent task proposal layer. | Add selectable sequential/meeting discussion mode and optional Codex task proposal generation in the dashboard. |

## Key Findings
1. The prior agent flow was auditable but mechanically sequential, so every configured role participated whether or not the objective needed that perspective.
2. A lightweight virtual-chair layer is enough for the next step: it chooses the next useful role or role group, supplies a role-specific focus, and decides when discussion has enough coverage.
3. The legacy sequential path should remain the default for compatibility and deterministic runs; meeting mode is opt-in through CLI, API, and Web.
4. Meeting runs enforce configurable caps for `max_rounds` and `max_roles_per_round`, both available from the dashboard at run creation time.
5. `--use-agent` adds a separate local coding-agent proposal layer with `agent_tasks.json`, `agent_tasks.md`, and `agent_approval_template.yaml`.
6. `danger-full-access` is deliberately reserved rather than hidden; selecting it writes explicit high-risk warnings and still requires approval.
7. The run bundle now carries `discussion_trace.json` and `discussion_trace.md`, while `plan.md` includes chair decisions for review.

## Decision
This is an infrastructure/product iteration only. No strategy candidate was promoted, no training or backtest was run for alpha validation, and durable strategy metrics remain unchanged.

## Validation
- `./.venv/bin/python -m pytest test/test_agent_strategy_iteration.py test/test_web_dashboard.py`
- `./.venv/bin/python -m compileall agent/strategy_iteration web/api/routers/agents.py web/api/services/agent_service.py run_agent_strategy_iteration.py`
- `cd web/frontend && npm run build`
- `./.venv/bin/python run_agent_strategy_iteration.py --objective "meeting mode smoke" --run-id meeting_mode_smoke --output-dir /tmp/quant_ex_agent_runs --no-llm --no-memory --discussion-mode meeting --meeting-max-rounds 3 --meeting-max-roles-per-round 2 --propose-actions`
- `./.venv/bin/python run_agent_strategy_iteration.py --objective "use agent smoke" --run-id use_agent_smoke --output-dir /tmp/quant_ex_agent_runs --no-llm --no-memory --discussion-mode meeting --meeting-max-rounds 2 --meeting-max-roles-per-round 2 --use-agent --agent-mode danger-full-access --agent-max-tasks 1 --write-agent-approval-template`
