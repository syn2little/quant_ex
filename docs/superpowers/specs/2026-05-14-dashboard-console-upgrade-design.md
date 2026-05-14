# Dashboard Console Upgrade Design

**Date:** 2026-05-14
**Status:** approved (brainstorming phase)
**Scope:** Web Dashboard 4 主流程页 (Data / Models / Backtest / Signals) 从"只读 artifact 浏览器"升级为"参数化执行 + 任务追踪 + 历史回溯"的研究控制台。AgentRuns 页本轮不动。

## 1. 背景与目标

### 1.1 现状

Web Dashboard 后端 (`web/api/`) 已有 7 个 router、50+ endpoint,`TaskManager + SSE` 基础设施可用,触发型 endpoint(`/data/fetch`, `/models/train`, `/backtest/grid`, `/backtest/walk-forward`, `/signals/generate`, `/signals/rebalance`, `/factors/evaluate`, `/factors/mine`)均已存在。

前端 (`web/frontend/`) 9 页中,AgentRuns 已在迭代;其余多数仍停留在"列表 + 详情查看"形态:执行表单参数覆盖不全,任务追踪零散,无统一历史聚���,部分 action 完全靠命令行手跑。

前期 `2026-05-06-dashboard-v2-iteration.md` 已修过 SPA 404、参数 fidelity、bundle 拆分等局部问题,但未做"per-page console 化"的整体升级。

### 1.2 目标

- 每页采用统一 console 骨架:`概览 / 执行 / 历史 / 详情`
- 所有触发动作默认 `dry_run=true`,显示影响范围预览,二次确认后才真跑
- 任务追踪通过页内侧抽屉 + 全局 System 页总表双轨呈现,SSE 流实时刷新
- 4 个 subagent 并行实现,彼此文件边界清晰,合并成本可控
- 退出标准:7 项验收门禁全部通过,无回归 AgentRuns,无引入新依赖

### 1.3 非目标

- 本轮不重做 Research(因子)、Config、System、Overview 页面
- 不引入新前端测试框架(若 vitest 未装,前端组件单测层跳过)
- 不引入新生产依赖(echarts、tailwind 等保持当前版本)
- 不修改 qlib 数据源接入逻辑,不改 ModelTrainer/BacktestEngine 内部

## 2. 架构

### 2.1 前端文件布局(新增 / 改动)

```
web/frontend/src/
├── components/console/         # Phase 0 新建,Phase 1 不许改
│   ├── ExecutionForm.tsx
│   ├── DryRunPreview.tsx
│   ├── ConfirmDialog.tsx
│   ├── TaskDrawer.tsx
│   ├── TaskChip.tsx
│   ├── ConsolePageLayout.tsx
│   └── index.ts
├── hooks/
│   ├── useTaskTracking.ts      # 新建
│   ├── useDryRunPreview.ts     # 新建
│   └── useSSE.ts               # 复用,按需扩展
├── api/
│   ├── tasks.ts                # 新建,封装 /system/tasks + SSE
│   ├── data.ts                 # 改 (subagent A)
│   ├── models.ts               # 改 (subagent B)
│   ├── backtest.ts             # 改 (subagent C)
│   └── signals.ts              # 改 (subagent D)
├── pages/
│   ├── DataExplorerPage.tsx    # 改 (subagent A)
│   ├── ModelsPage.tsx          # 改 (subagent B)
│   ├── BacktestPage.tsx        # 重构外壳 (subagent C)
│   ├── backtest/               # 新建子组件目录 (subagent C)
│   │   ├── GridConsole.tsx
│   │   ├── WFVConsole.tsx
│   │   ├── CompareConsole.tsx
│   │   ├── ResultsHistory.tsx
│   │   └── ResultDetail.tsx
│   └── SignalsPage.tsx         # 改 (subagent D)
├── schemas/                    # 新建,zod 表单 schema
│   ├── data.ts
│   ├── train.ts
│   ├── backtest.ts
│   └── signals.ts
└── i18n/
    ├── en.json                 # 加 console.* 命名空间
    └── zh.json                 # 同步
```

### 2.2 后端改动范围

`web/api/routers/` 与 `web/api/services/task_manager.py` 由 Phase 0 主 agent 一次性改造,Phase 1 subagent 不允许动 router 与 service。

## 3. 公共组件契约

### 3.1 后端 `{task_id, dry_run, preview}` 统一返回

所有触发任务的端点(POST 与具备副作用的 DELETE)必须返回:

```json
{
  "task_id": "string",
  "dry_run": true,
  "preview": { "...": "任务类型特定" }
}
```

- `dry_run=true` 时 `preview` 非空,**不能产生副作用**(不写磁盘、不发网络、不动 cache)
- `dry_run=false` 时 `preview=null`,正常排队执行,后续 SSE 推送状态
- `task_id` 始终非空,即使 dry-run 也产生一条 `TaskManager` 记录,状态直接 `completed`,`result_paths=[]`

影响 endpoint:`/data/fetch`、`/data/cache/{type}/expired` (DELETE)、`/models/train`、`/models/{f}` (DELETE)、`/backtest/grid`、`/backtest/walk-forward`、`/backtest/compare`、`/signals/generate`、`/signals/rebalance`、`/signals/notify-test`、`/factors/evaluate`、`/factors/mine`。

`/signals/rebalance` 与 `/signals/notify-test` 已部分符合,核对字段名后微调即可。

### 3.2 TaskManager schema 扩展

`web/api/services/task_manager.py` 中 Task 记录新增三个可选字段:

| 字段 | 类型 | 用途 |
|---|---|---|
| `page_key` | `Optional[Literal['data','models','backtest','signals','agents']]` | 前端按页过滤 |
| `action_key` | `Optional[str]` | 历史聚合 key,例:`models.train`, `backtest.grid` |
| `result_paths` | `list[str]` | 产物文件路径,任务结束时由 router 回填 |

`/api/system/tasks` 与 `/system/tasks/{id}/stream` 输出包含这些字段。

### 3.3 前端组件 props 契约(冻结)

#### `<ExecutionForm>`

```tsx
type ExecutionFormProps<TParams> = {
  pageKey: 'data' | 'models' | 'backtest' | 'signals';
  actionKey: string;
  schema: ZodSchema<TParams>;
  defaults: Partial<TParams>;
  dryRunDefault: boolean;
  onDryRun: (p: TParams) => Promise<DryRunResult>;
  onSubmit: (p: TParams) => Promise<{ task_id: string }>;
  renderFields: (form: UseFormReturn<TParams>) => ReactNode;
};
```

#### `<TaskDrawer>`

```tsx
type TaskDrawerProps = {
  pageKey: PageKey;
  taskTypeFilter: string[];
  open: boolean;
  onClose: () => void;
};
```

#### `<ConsolePageLayout>`

```tsx
type ConsolePageLayoutProps = {
  pageKey: PageKey;
  titleKey: string;
  tabs: {
    overview?: ReactNode;
    execute: ReactNode;
    history: ReactNode;
    inspect?: ReactNode;
  };
  taskTypeFilter: string[];
};
```

#### `<ConfirmDialog>`

```tsx
type ConfirmDialogProps = {
  open: boolean;
  titleKey: string;
  impactSummary: ReactNode;       // dry-run preview 的关键字段摘要
  confirmLabelKey: string;
  destructive?: boolean;          // 显示红色按钮 + 关键字勾选(可选)
  onConfirm: () => void;
  onCancel: () => void;
};
```

二次确认采用**纯按钮**模式,不加倒计时。对调仓 / 删除等高风险操作勾选 `destructive=true`。

### 3.4 i18n 命名空间

```
console.common.*    # 公共组件文案 (dryRun, confirm, cancel, retry, preview...)
console.tasks.*     # 任务抽屉 / 状态 / 进度
console.data.*      # subagent A 独占
console.models.*    # subagent B 独占
console.backtest.*  # subagent C 独占
console.signals.*   # subagent D 独占
```

`en.json` 与 `zh.json` 同步修改是硬规则(CLAUDE.md 既有约束)。

## 4. 每页 console 设计

### 4.1 Data Explorer

**执行 tab — 3 个 action 卡片**

| Action | API | 关键参数 | dry-run preview |
|---|---|---|---|
| 数据抓取 | `POST /data/fetch` | `data_types[]`, `date_range`, `force_refresh`, `dry_run` | 计划抓取条数、估算耗时、磁盘占用、跳过项 |
| 过期清理 | `DELETE /data/cache/{type}/expired?dry_run` | `data_type`, `dry_run` | 列出 N 个将删文件 + 释放空间 |
| qlib 增量更新 | `POST /data/update-qlib`(Phase 0 新增) | `region`, `date_range`, `dry_run` | `run_update_qlib_data.py --dry-run` 等价输出 |

`force_refresh=true` 与"过期清理"必须经 `<ConfirmDialog>` 且 `destructive=true`。

若 Phase 0 评估 `run_update_qlib_data.py` 不便包装,本表第 3 行整体跳过(subagent A 不在前端实现该卡片)。

**历史 tab**: TaskManager `page_key=data` + cache 文件 mtime,展示最近 30 天数据任务 + 当前 cache 文件指纹。

**详情 tab**(只读复用):个股查找/行情、板块/轮动、替代数据。

**Subagent A 边界**:仅改 `pages/DataExplorerPage.tsx`、`api/data.ts`、`schemas/data.ts`、`i18n` 中 `console.data.*`。后端缺口(若 `run_update_qlib_data` 接口不便)由 Phase 0 主 agent 处理。

### 4.2 Models

**执行 tab — 2 个 action 卡片**

| Action | API | 关键参数 | dry-run preview |
|---|---|---|---|
| 训练 | `POST /models/train` | `model_type`, `tag`, `config_override`, `market`, `train_start_date`, `train_end_date`, `dry_run` | 展开后完整命令、目标 `_meta.json` 字段、估算耗时、**实际生效 market** |
| 删除 | `DELETE /models/{f}?dry_run` | `filename`, `dry_run` | 列出将删除文件(.pkl + meta + 索引) |

**关键校验**:训练 dry-run preview 必须显式打印 `final_market`,防止 `config/daily_csi1000.yaml` 类配置陷阱(`market.name: csi300` 写错)。这是 subagent B 的硬性验收点。

**历史 tab**:训练任务记录(`action_key=models.train`)+ 模型文件 + `_meta.json` 字段统一表。

**详情 tab**:模型 meta、registry、特征重要性图表(复用已有)。

**Subagent B 边界**:`pages/ModelsPage.tsx`、`api/models.ts`、`schemas/train.ts`、`console.models.*`。

### 4.3 Backtest

**执行 tab — 3 个 action 卡片**

| Action | API | 关键参数 | dry-run preview |
|---|---|---|---|
| Grid Search | `POST /backtest/grid` | `model_path`, `market`, `benchmark`, `topk_list`, `n_drop_list`, `hold_thresh_list`, `deal_price`, costs/slippage, `start_date`, `end_date`, `output_csv`, `dry_run` | 候选数 = ∏ 列表长度、估算总耗时;>200 候选时红字警告 |
| WFV | `POST /backtest/walk-forward` | `train_universes[]`, `eval_market`, `rolling_window_days`, `step_days`, 3 个候选列表, `rank_metric`(默认 `information_ratio`), `dry_run` | 窗口数 × 候选数;耗时数量级警告 |
| 对比 | `POST /backtest/compare` | `result_files[]`(2-5) | 并排 equity / drawdown / 指标表 |

**研究规则约束**(CLAUDE.md):
- `rank_metric` 默认 `information_ratio`,UI 不能让用户在主排序里偷偷换成 Sharpe
- 历史 tab 默认按 IR 列降序;可加副排序,但主排序 freeze 为 IR

**历史 tab**:`backtest_results/*.csv` + TaskManager `grid_search`/`wfv` + chart 文件合并。列含市场、模型、IR、Sharpe、deal_price、状态、task_id、artifact 链接。

**详情 tab**:已有的 equity curve / drawdown / metrics(直接复用)。

**Subagent C 边界**:重构 `pages/BacktestPage.tsx` 为组合外壳 + 新建 `pages/backtest/` 5 个子组件。允许在工时严重超支时**进一步拆给 2 个 sub-subagent**(Grid+WFV 一组,Compare+History+Detail 一组),由主 agent 在 Phase 1 中段评估决定。

### 4.4 Signals

**执行 tab — 3 个 action 卡片**

| Action | API | 关键参数 | dry-run preview |
|---|---|---|---|
| 每日信号 | `POST /signals/generate` | `model_path`, `config_override`, `dry_run` | 目标日期、universe、生成 topN、是否写 `signals/*.txt` |
| 调仓 | `POST /signals/rebalance` | `config`, `positions`, `position_date`, `min_action_value`, `skip_update`(默认 true), `force`(默认 false), `notify_channel`, `dry_run`(默认 true), `confirm_send`(仅 `dry_run=false` 时启用) | 当前 → 目标持仓 diff(买/卖/金额/影响)、通知模板字段 |
| 通知测试 | `POST /signals/notify-test` | `channel`, `message`, `dry_run`(默认 true), `confirm_send` | 渠道、目标(脱敏)、模板渲染 |

调仓 + 通知测试在 `dry_run=false` 时**强制** `confirm_send=true` 才放行,UI 通过 `<ConfirmDialog destructive>` 控制。

**历史 tab**:`signals/*.txt` + TaskManager `signal_generate`/`rebalance`/`notify_test`。rebalance 历史多一列"是否真发"。

**详情 tab**:regime 状态、单文件信号查看(复用)。

**Subagent D 边界**:`pages/SignalsPage.tsx`、`api/signals.ts`、`schemas/signals.ts`、`console.signals.*`。

## 5. 并行 subagent 调度

### 5.1 阶段拆分

#### Phase 0 — 公共基础(主 agent,串行)

分支 `dashboard-console-base`(不开 worktree,作为后续 worktree 的分叉点)。

1. 后端契约统一(§3.1, §3.2):12 个 endpoint 改返回格式 + TaskManager 扩展 3 字段
2. 后端新增 endpoint:`POST /data/update-qlib` 包装 `run_update_qlib_data.py`(若该脚本接口实际不便包装,则在本计划范围内**放弃该 action**,subagent A 在 §4.1 表中删除"qlib 增量更新"卡片并在 plan checklist 中标注 skip)、`DELETE /models/{f}` 支持 `?dry_run`
3. 前端 `components/console/`、`hooks/useTaskTracking`、`hooks/useDryRunPreview`、`api/tasks.ts`
4. i18n `console.common.*` + `console.tasks.*`,每页命名空间留 stub
5. 后端测试 `test/test_web_console_contract.py` 覆盖每个 endpoint 的 dry-run + 实跑 + 校验失败三个分支
6. Phase 0 门禁:`pytest test/test_web_dashboard.py test/test_agent_strategy_iteration.py test/test_web_console_contract.py` 全过 + `npm run build` 过 + AgentRuns 页冒烟 OK

#### Phase 1 — 4 subagent 并行

主 agent 创建 4 个 worktree 从 `dashboard-console-base` 分叉:

```
.claude/worktrees/console-data/
.claude/worktrees/console-models/
.claude/worktrees/console-backtest/
.claude/worktrees/console-signals/
```

每个 subagent 输入 prompt 包含:
- 本 spec 路径
- 对应 §4.x 子节摘录
- 文件边界表(§5.2)
- 验收门禁(`npm run build` + `pytest test/test_web_console_<page>.py` + 自跑 dev 截图)
- 强制使用 `superpowers:test-driven-development` 与 `superpowers:verification-before-completion`

#### Phase 2 — 主 agent 集成(串行)

按 `A → D → B → C` 顺序 merge 到 `dashboard-console-base`(C 最晚,降低 rebase 成本)。每次 merge 后跑前端 build + 后端 pytest。冲突主要落在 `i18n/*.json`,人工合并 + en/zh 同步校验。

### 5.2 文件边界(冲突防御)

| Subagent | 允许改 | 严禁碰 |
|---|---|---|
| A (Data) | `pages/DataExplorerPage.tsx`, `api/data.ts`, `schemas/data.ts`, `i18n.console.data.*` | `components/console/`, 其他 page, 其他 i18n 命名空间, 任何 router |
| B (Models) | `pages/ModelsPage.tsx`, `api/models.ts`, `schemas/train.ts`, `i18n.console.models.*` | 同上 |
| C (Backtest) | `pages/BacktestPage.tsx`, `pages/backtest/*`, `api/backtest.ts`, `schemas/backtest.ts`, `i18n.console.backtest.*` | 同上 |
| D (Signals) | `pages/SignalsPage.tsx`, `api/signals.ts`, `schemas/signals.ts`, `i18n.console.signals.*` | 同上 |

发现 Phase 0 漏洞或后端 bug,subagent 必须停下并上报主 agent,由主 agent 修后 rebase 各 worktree。Subagent 可新增 `test/test_web_console_<page>.py` 但不许改 router。

## 6. 集成测试与验收

### 6.1 三层测试

**第 1 层 — 后端 pytest**

`test/test_web_console_integration.py` 与 `test/test_web_console_contract.py`,每个 action 覆盖三个分支:

| 分支 | 断言 |
|---|---|
| dry-run 默认 | 返回 `{task_id, dry_run: true, preview: 非空}`;TaskManager `result_paths=[]`;无副作用文件产生 |
| 实跑(最小参数 + mock) | 返回 `{task_id, dry_run: false, preview: null}`;TaskManager 中 `page_key/action_key` 正确;`run_train.main` 等被 monkeypatch |
| 参数校验失败 | 4xx,字段位置正确 |

实跑分支用 monkeypatch 替换重操作入口,**禁止**直接调用 `run_train.main` / `run_backtest.main` 实际跑训练或全 WFV。

**第 2 层 — 前端组件单测(条件)**

若仓库已配置 vitest,则覆盖 `<ExecutionForm>` / `<ConfirmDialog>` / `useTaskTracking`;未配置则**跳过**,不引入框架。

**第 3 层 — 浏览器 e2e**

`test/test_web_console_e2e.py` 复用前次 SPA 404 检测的 CDP 方案,不引入 Playwright。每页脚本流:

1. 打开页面 URL
2. 切到"执行" tab
3. 找第一个 action 卡片
4. 表单填默认参数(dry-run 默认勾选)
5. 点"预览" → 等待 `data-testid="dry-run-preview"`
6. 点"提交" → 等待 `data-testid="task-drawer"` 出现 + 任务 `pending → completed`
7. 切"历史" tab → 验证任务出现在表中

加反向测试:取消 dry-run、不勾 confirm,提交按钮应 disabled。

### 6.2 验收门禁(必须全过)

```bash
./.venv/bin/python -m pytest test/ -v
./.venv/bin/python -c "from web.api.app import app; print(len(app.routes))"
cd web/frontend && npm run build
cd web/frontend && npx tsc --noEmit
./.venv/bin/python -m pytest test/test_web_console_e2e.py -v
./.venv/bin/python web/run_web.py    # 人肉跑完 4 页 dry-run
```

### 6.3 退出标准

1. 6.2 门禁全过
2. plan md 中所有 task checkbox `[x]`
3. 干净 `git status` 上 `python web/run_web.py` 浏览器手测 4 页通过
4. `MEMORY.md` 短记本轮变更
5. 不破坏 AgentRuns;不引入新生产依赖

## 7. 风险与回滚

### 7.1 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Phase 0 后端契约改动破坏 AgentRuns | 中 | 高 | Phase 0 必跑 `test_agent_strategy_iteration.py` + AgentRuns 页冒烟 |
| `i18n/*.json` 4 个 subagent 合并冲突 | 高 | 中 | 严格命名空间 + 主 agent diff 工具校验 en/zh 同步 |
| Backtest C 工时超预算 | 中 | 高 | 允许进一步拆分 sub-subagent;保留旧 BacktestPage.tsx 作 fallback |
| Subagent 误判完成 | 中 | 高 | 第 3 层 e2e 是硬门禁 |
| 真实 `run_train`/`run_backtest` 被错误触发 | 低 | 极高 | 后端 mock + 前端 dry-run 默认 + confirm |
| 浏览器缓存导致旧 bundle 撞新 API | 低 | 中 | nav 显示 build hash + 文档说明清缓存 |

### 7.2 回滚

- **Phase 0 出错**:`git revert` Phase 0 commit
- **Phase 1 某 subagent 不达标**:不 merge,其他 3 个照常发布,该页保留旧版下一轮重做
- **Phase 2 e2e 卡住**:基础设施 bug 回滚 Phase 0;业务 bug 卡对应 subagent 重做
- **上线后严重问题**:`git revert` merge commit;FastAPI 静态资源自动回旧 bundle

## 8. 范围之外

- Research / Config / System / Overview 页的 console 化(下一轮)
- AgentRuns 页(已在独立迭代)
- 新前端测试框架引入
- 任何 ModelTrainer / BacktestEngine 内部逻辑改动
- qlib 数据源接入方式改动
