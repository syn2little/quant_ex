# System Diagnostic: 2026-05-14 Dashboard Console Product Iteration

## Layer Scores

| Layer | Score | Weakest Link | Highest Leverage Fix |
|---|---:|---|---|
| Data | 4 | Data Explorer did not communicate cache health or freshness. | Add qlib/cache status, stale warnings, and recent task history. |
| Factors | 4 | Factor Research lacked a clear user purpose. | Reframe around factor inclusion validation with IC/RankIC/coverage workflow. |
| Model | 5 | Training UI exposed too few research parameters. | Add market/window/config/factor/ensemble/LightGBM controls and richer dry-run preview. |
| Backtest | 5 | Users could not see equity vs benchmark or choose benchmark assumptions clearly. | Add benchmark/deal/cost controls, curve/benchmark/excess/drawdown views, and IR-first compare/history. |
| Execution | 5 | Signals history was text-heavy and did not show portfolio evolution. | Parse rebalance caches and visualize target value, holdings count, top weights, and buy/sell amounts. |
| Web | 5 | The dashboard felt too white, sparse, and page-specific. | Fixed sidebar, lower-white professional shell, and unified workbench page structure. |

## Key Findings

1. The main product gap was not endpoint coverage but user comprehension: each page needed to show current state, safe actions, result interpretation, and historical continuity.
2. Backtest and Signals required visual result surfaces, not only task/artifact tables.
3. Models needed research-grade training configuration without forcing users into raw YAML.
4. Data and Factor pages needed clearer purpose and empty states so users understand when to fetch data, inspect freshness, or evaluate factor inclusion.

## Validation

- `./.venv/bin/python -m pytest test/test_web_console_backtest.py test/test_web_console_contract.py test/test_web_console_data.py test/test_web_console_integration.py test/test_web_console_models.py test/test_web_console_signals.py -q`
- `./.venv/bin/python -m pytest test/ -q`
- `cd web/frontend && npx tsc --noEmit`
- `cd web/frontend && npm run build`
- `./.venv/bin/python -m pytest test/test_web_console_e2e.py -q`
- Local Chrome headless screenshots for `/backtest`, `/signals`, `/data-explorer`, `/models`, and `/research`.
