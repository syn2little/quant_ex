# System Diagnostic: 2026-05-17 Validation Contract Promotion Report

## Layer Scores
| Layer | Score | Weakest Link | Highest Leverage Fix |
|---|---:|---|---|
| Data | 4 | Result CSVs can come from different generations with different field sets. | Detect result kind and surface missing contract fields before interpretation. |
| Factors | 4 | Factor/postprocess candidates can look promising on same-model backtests. | Block promotion from backtest-only evidence and require WFV-grade gates. |
| Model | 5 | No model-path change in this iteration. | Keep model changes evaluated only through validated result contracts. |
| Backtest | 5 | IR-ranked and Sharpe-only artifacts could still be mixed silently. | Add explicit rank-metric fallback warnings and benchmark-aware contract checks. |
| Execution | 5 | Agent feedback produced a decision but not a promotion-grade gate report. | Generate `promotion_report.json/md` beside feedback and next-iteration artifacts. |
| Web | 5 | AgentRuns could not display promotion evidence separately from feedback prose. | Add Promotion Report artifact flag and tab in AgentRuns. |

## Key Findings
1. Existing feedback parsing was useful but too permissive for promotion decisions: old backtest CSVs without `information_ratio` could silently fall back to Sharpe.
2. Backtest-only evidence should never produce a promote decision; it can at most justify `compare_next`.
3. WFV promotion needs explicit gates for mean Sharpe, minimum fold Sharpe, p-value when present, drawdown, and control deltas when a control CSV exists.
4. Promotion reports belong in the agent artifact chain, not the raw backtest result browser, because they are research conclusions rather than execution outputs.
5. This iteration did not run training, full WFV, data updates, notifications, or trading-like workflows.

## Decision
Keep the validation contract and promotion report layer as the system's candidate-upgrade gate. It improves conclusion quality without changing strategy candidates.

## Validation
- `./.venv/bin/python -m compileall agent/strategy_iteration web/api/routers/agents.py web/api/services/agent_service.py run_agent_strategy_iteration.py`
- `./.venv/bin/python -m pytest test/test_agent_strategy_iteration.py test/test_web_dashboard.py`
- `cd web/frontend && npm run build`
- CLI smoke wrote `feedback.json`, `feedback.md`, `promotion_report.json`, and `promotion_report.md` under `/tmp/quant_ex_agent_runs/promotion_smoke`.
