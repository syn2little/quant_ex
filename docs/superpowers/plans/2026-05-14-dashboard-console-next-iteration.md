# Dashboard Console Next Iteration Plan

**Goal:** 在 4 主流程 console 化完成后,进入第一阶段硬化迭代:把验收防回归、研究参数一致性、产物血缘和操作观测性补到可长期维护的水平。

**Stage 1 Scope:** Acceptance hardening + contract parity。保持当前 console 功能稳定,优先修复会造成“预览与真实执行不一致”或“测试污染验收环境”的问题。

## Stage 1 Tasks

- [x] **Task 1: 固化本轮验收防回归基线**
  - 完成公共 i18n 防回归断言:console 标题/tab/dialog 不再直接显示 `console.*` key。
  - 完成 Chrome CDP e2e:4 页覆盖“提交 dry-run → 任务抽屉 → 历史 tab”。
  - 修复旧 Signals 页面测试覆写 `web/frontend/dist/index.html` 的测试污染。
  - 验收命令已通过:`./.venv/bin/python -m pytest test/ -q`、`cd web/frontend && npx tsc --noEmit && npm run build`。

- [ ] **Task 2: Backtest CLI 参数 parity**
  - 现状:Web real-run 对 `benchmark/deal_price/open_cost/close_cost/min_cost/slippage` 的非默认值显式 422,避免静默吞参。
  - 下一步:给 `run_backtest.py` 增加这些 CLI 参数并传入 `BacktestEngine/GridSearchBacktest`;完成后取消 Web 端 422 限制。
  - 测试:新增 `_build_grid_cmd` / CLI parse / engine 参数传递单测。

- [ ] **Task 3: 产物血缘补齐**
  - Models:训练任务尽量回填模型 pkl/meta/feature importance 路径。
  - Signals:generate/rebalance 回填 signal 文件或 rebalance report 路径。
  - Backtest:继续保持 Grid/WFV `result_paths` 可预测,并在历史页高亮关联产物。

- [ ] **Task 4: TaskDrawer 可观测性增强**
  - 把 SSE event log 从仅运行中捕获扩展为“历史事件 + 当前状态快照”。
  - 增加复制 task_id/result_paths、按 status/action 过滤和失败详情展开。

- [ ] **Task 5: Browser e2e 稳定性**
  - 让 e2e fixture 自启动/自关闭 FastAPI server,减少对外部 server 的依赖。
  - 保留 `WEB_BASE_URL` 覆盖以便 CI/本地复用。

## Stage 1 Gate

```bash
./.venv/bin/python -m pytest test/ -q
cd web/frontend && npx tsc --noEmit && npm run build
./.venv/bin/python web/run_web.py &
SERVER_PID=$!
./.venv/bin/python -m pytest test/test_web_console_e2e.py -q
kill $SERVER_PID
```

Expected:全 PASS;Vite chunk-size warning 可接受。
