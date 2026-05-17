# Dashboard Console Upgrade — Code Review

**Date:** 2026-05-14
**Branch reviewed:** `dashboard-console-base` vs `main`
**Diff size:** 62 files, +9501 / −2678, 26 commits
**Spec:** [docs/superpowers/specs/2026-05-14-dashboard-console-upgrade-design.md](../specs/2026-05-14-dashboard-console-upgrade-design.md)
**Plan:** [docs/superpowers/plans/2026-05-14-dashboard-console-upgrade.md](../plans/2026-05-14-dashboard-console-upgrade.md)

---

## Verification status at review time

| Gate | Result |
|---|---|
| `./.venv/bin/python -m pytest test/test_web_console_* test/test_web_dashboard.py test/test_agent_strategy_iteration.py -q` | **99 passed / 0 failed** |
| `cd web/frontend && npx tsc --noEmit` | **clean(无错误)** |
| AgentRuns 回归 | **未破坏** |

## Overview

按 spec 三阶段实现:

- **Phase 0**:后端 12 个触发型 endpoint 统一返回 `{task_id, dry_run, preview}`;`TaskState` 加 `page_key` / `action_key` / `result_paths`;`/api/system/tasks` 序列化包含新字段
- **Phase 1**:4 页前端 console 化(Data / Models / Backtest / Signals)+ 公共组件 `components/console/` + hooks `useTaskTracking` / `useDryRunPreview`
- **Phase 2**:集成测试 + e2e + 任务抽屉 / 历史接入

后端契约与测试覆盖扎实;前端在共享组件落地上**贯彻不一致**,造成若干安全门槛弱化。

---

## 🟥 Blocking issues(合并前必须修)

### B1. Models 删除模型走的是 `window.confirm()`

**位置**:`web/frontend/src/pages/ModelsPage.tsx:483`

`window.confirm` 删 `.pkl`,**不是**项目共享的 `<ConfirmDialog destructive>`。无文件清单回显、无 i18n、无影响摘要。违反 spec §4.2 与 §3.3。Backtest / Signals / Data 的删除型动作全部经过 `ConfirmDialog`,唯独 Models 例外,体验和安全都裂开。

**修法**:换成 `<ConfirmDialog destructive={true} impactSummary={preview.files}>`,显示后端 dry-run 返回的待删文件列表。

### B2. Models 训练无 ConfirmDialog 二次门槛

**位置**:`web/frontend/src/pages/ModelsPage.tsx:255-286`

取消勾选 dry-run + 一键 Submit 就能启动**几小时**级训练任务。Backtest grid/wfv 都有 ConfirmDialog 包真跑,Models train 缺失。

**修法**:实跑分支(`dry_run=false`)经过 `<ConfirmDialog>`,impactSummary 显示 `final_market`、输出路径、估算耗时。

### B3. Models + Signals 全部 action 绕开 `<ExecutionForm>`

**位置**:
- Models:`ModelsPage.tsx:255-286, 482-498`
- Signals:`SignalsPage.tsx:282-292, 353-371, 475-493`

5 个 action 卡片均**手写** `useState` 表单 + 命令式 submit,而 Data / Backtest 用了 `<ExecutionForm>`。代价:

- 没有 `data-testid="execution-form-${actionKey}"`,e2e 与未来浏览器测试无法按 spec §3.3 选择器定位
- Zod 校验只在 submit 时跑,丢失 form-edit-time 校验
- `console:task-created` 事件可能不被派发(Models / Signals 抽屉自动弹起依赖此事件)

**修法**:重构 5 个 action 卡片到 `<ExecutionForm>`,与 Data / Backtest 拉齐。

### B4. TaskDrawer 只对"被选中"的任务订阅 SSE

**位置**:`web/frontend/src/hooks/useTaskTracking.ts:35-70`(`trackTask` 是死代码) + `web/frontend/src/components/console/TaskDrawer.tsx:69-91`

抽屉里其他运行中行只靠 5s 轮询,只有用户点击展开的那一行接 SSE。spec §3.3 的隐含语义是抽屉应订阅所有 active 任务。

**修法**:抽屉 mount 时遍历 `tasks.filter(t => t.status === 'running' || t.status === 'pending')` 调用 `trackTask(id)`,task 终态时清理。

### B5. `ExecutionForm` 用字符串哨兵

**位置**:`web/frontend/src/components/console/ExecutionForm.tsx:40`

用 `"awaiting-confirmation"` / `"pending-confirmation"` 这种 magic string 决定是否派发 `console:task-created` 事件。没有写进类型,任何消费者用别的字符串会触发误判抽屉自动弹出。

**修法**:换成显式 `onSubmit` 返回 `null`(跳过事件),或定义 `enum` / 联合类型常量并导出。

---

## 🟧 Non-blocking but should fix

| # | 位置 | 问题 | 修法 |
|---|---|---|---|
| N1 | `web/api/routers/backtest.py:345` WFV preview | `window_count` / `total_runs` / `estimated_minutes` 与真实 fold 实现不一致,**误导用户** | folds_config 路径下省略,或标注 `approximate=true` |
| N2 | `web/api/routers/signals.py:573` notify-test 实跑 | 返回 `sent: True` 但真实推送在 executor 中异步执行,语义错位 | 改成 `sent=False` 并通过 SSE 终态上报真实结果 |
| N3 | `web/api/routers/models.py:21,28` 路径校验 | `".." in filename` 会拒合法名(如 `model..draft.pkl`)| 改 `Path.resolve()` 校验父目录 |
| N4 | `web/frontend/src/pages/SignalsPage.tsx:430,526` confirm_send 门槛 | 当前允许"不跑 dry-run → 直接勾 confirm_send → 真发",spec 意图是先看 diff | 加"必须有一次成功 dry-run"前置(可通过 `lastDryRunAt` state) |
| N5 | `web/frontend/src/hooks/useTaskTracking.ts:6` | `pageKey: string` 类型太宽 | 改 `PageKey` union,与 ConsolePageLayout 对齐 |
| N6 | `web/api/routers/data.py:326` | `daily_main(..., dry_run=req.dry_run)` 这条路径 `req.dry_run` 永远 False | 写成字面量 `False` 更诚实 |
| N7 | `web/api/routers/factors.py:180` `_safe_path` | 死代码 | 删除 |
| N8 | `web/api/routers/agents.py` 4 处 `start_sync_task` | 未传 `page_key="agents"` / `action_key` | 补上,使 AgentRuns 任务也能在 console TaskDrawer 出现 |
| N9 | `TaskDrawer.tsx` 内部 `events` 字典 | `events[selectedTask.task_id]` 永不 GC,长会话累积 | 任务 done 后 `delete events[id]` |

---

## 测试覆盖缺口

- 没有断言 `page_key` / `action_key` 出现在 SSE 流(只在 REST list 中验过)
- `factors.py` 的 `evaluate` / `mine` 缺真跑 mock 测试
- 缺 path-traversal 负例(`DELETE /api/models/..%2Fetc%2Fpasswd` 应 400)
- WFV 测试用全局 `monkeypatch.setattr(subprocess, "run", ...)`,改 patch `web.api.routers.backtest.subprocess.run` 更安全
- 缺 `data_purge` dry-run 后文件未被删除的显式 fs 断言

---

## 安全审查

- **未引入新风险**:无命令注入、未引入未授权写盘路径、无 cred 泄漏
- **路径相关**:Models DELETE 的 `_safe_model_file` 文件名级别检查,运行中安全;N3 是改进点
- **副作用**:扫了 12 个端点,所有 dry-run 路径均闭包返回 dict、未触发真实 IO

---

## 风格 / 项目惯例

- 后端契约改造非常一致,12 个端点同一模式,易读易维护
- 前端 Data / Backtest 是模板级实现,Models / Signals 落后一档(B3)
- i18n `en.json` / `zh.json` 跨 5 个命名空间完全同步,无 orphan key
- BacktestPage.tsx 从 1117 行重构到 55 行的外壳 + 5 个子组件,可读性大幅提升

---

## 验收门禁(修完后必须全部重跑通过)

```bash
# 后端
./.venv/bin/python -m pytest test/test_web_console_contract.py \
                              test/test_web_console_data.py \
                              test/test_web_console_models.py \
                              test/test_web_console_backtest.py \
                              test/test_web_console_signals.py \
                              test/test_web_console_integration.py \
                              test/test_web_console_e2e.py \
                              test/test_web_dashboard.py \
                              test/test_agent_strategy_iteration.py -v

# 前端
cd web/frontend && npx tsc --noEmit && npm run build

# e2e 跑前要起服务
./.venv/bin/python web/run_web.py &
sleep 5
./.venv/bin/python -m pytest test/test_web_console_e2e.py -v
kill %1
```

人肉验收 4 页 console 链路(执行 tab → 表单 → dry-run preview → confirm → 任务抽屉 → 历史 tab)。

---

## Verdict

**🟧 同意合并 — 但 5 个 blocker(B1–B5)必须先修。** 后端契约与测试已达到生产标准;集成测试 99/99 + AgentRuns 无回归证明不会破坏既有功能。但 Models / Signals 绕开 `<ExecutionForm>`、`window.confirm` 删模型、train 无 confirm、抽屉只订阅选中任务这 5 项把 spec 设计意图打了折扣,违反"统一 console 体验"的根本目标。N1 / N2 也建议在同一轮一并修(误导性 preview 比缺失 preview 更糟)。

修完 B1–B5 + N1 / N2,重跑全部验收命令通过,可合并 `main`。
