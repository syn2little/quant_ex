# System Diagnostic: 2026-05-14 Dashboard Console Stage 1

## Layer Scores

| Layer | Score | Weakest Link | Highest Leverage Fix |
|---|---:|---|---|
| Data | 3 | Console task artifacts were visible only through task result payloads. | Keep task `result_paths` as the common lineage contract. |
| Factors | 3 | Not in scope for this infrastructure iteration. | No factor changes. |
| Model | 4 | Web training tasks did not expose saved model artifacts. | Return custom trainer `.pkl`, meta, and feature-importance paths. |
| Backtest | 5 | Web real-run rejected research-cost/benchmark overrides that the engine already supported. | Add CLI/GridSearch parity for benchmark, deal price, and costs. |
| Execution | 5 | Signals and rebalance real-runs did not attach output paths to task history. | Return signal files and fresh rebalance cache artifacts. |
| Web | 5 | Browser e2e depended on an externally started server; task drawer history was hard to inspect. | Self-start FastAPI in e2e and add drawer filters, copy actions, snapshots, and failure details. |

## Key Findings

1. Backtest engine already supported benchmark, deal price, and transaction costs, but `run_backtest.py`, grid search, and Web command construction were not aligned.
2. TaskManager already persisted `result_paths`; the missing piece was worker return values for model training, signal generation, and rebalance runs.
3. Console e2e coverage existed but skipped unless an external server was running, weakening local and CI acceptance.
4. TaskDrawer could show live events, but historical task inspection needed status/action filtering, copyable identifiers/artifacts, and a status snapshot when SSE events were no longer available.
