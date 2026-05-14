# Dashboard Console Product Iteration Plan

**Goal:** 把 Dashboard 从“参数表单 + artifact 列表”升级为专业量化研究工作台。用户进入任一页面后，应能立刻判断当前状态、知道能安全执行什么、并用图表/历史追踪结果变化。

**Iteration Principle:** 系统性改造，不做孤立补丁。所有主页面统一采用“状态概览 / 参数执行 / 结果观察 / 历史追踪”的研究闭环。

**Implementation Status (2026-05-14):** Stage 0-5 已完成。全局 shell 固定左栏并降白；Backtest 补净值/基准/回撤/对比工作台；Signals 补 rebalance cache 历史和持仓/市值可视化；Models 训练配置扩展为研究参数面板；Data Explorer 补数据健康和缓存控制；Factor Research 重构为“因子是否值得入模”的验证流程。

## UX Contract

每个页面必须回答四个问题：

1. **当前状态是什么？** 数据 freshness、模型配置、回测表现、信号/持仓历史。
2. **我能做什么？** 明确 action、参数分组、dry-run 影响摘要、真实执行风险。
3. **结果怎么看？** 关键指标、曲线、对比、表格、产物路径。
4. **历史如何延续？** Task history、缓存/artifact、可追溯 result paths。

## Stage 0: Global Product Shell

- [x] 固定左侧导航，不再 hover 自动收缩。
- [x] 全局视觉调成“简约商务 + 专业量化终端”：低饱和背景、深色导航、克制强调色、表格/图表优先。
- [x] 改造 `ConsolePageLayout`：页面头部、任务入口、tab、内容宽度和密度统一。
- [x] 清理过度白色卡片观感，减少页面嵌套卡片。

## Stage 1: Backtest Workbench

- [x] Grid/WFV 表单增加 benchmark 选择/输入、deal price、交易成本参数，并展示当前生效设置。
- [x] Results/Detail 默认可见 portfolio vs benchmark 净值曲线、excess、drawdown、指标卡。
- [x] 历史结果支持选择 CSV 后直接渲染图表；grid summary 无曲线时给出明确空状态和下一步。
- [x] Compare 支持多结果基准/净值/回撤对比，主排序仍以 information_ratio 为核心。

## Stage 2: Signals Workbench

- [x] 后端补 `signals/daily_rebalance_cache/*.json` 历史读取与解析接口。
- [x] 历史页同时展示 signal txt 和 rebalance cache。
- [x] 可视化组合市值、持仓数量、Top holdings 权重、买卖金额变化。
- [x] 任务 result_paths 可跳转/关联到历史记录。

## Stage 3: Models Workbench

- [x] 训练参数从极简表单扩展为研究员视角分组：数据窗口、market、模型、config、factor pipeline、ensemble、LightGBM 高级摘要。
- [x] dry-run preview 展示最终 market、训练窗口、配置来源、关键参数、预估产物。
- [x] 模型详情强化：meta 摘要、feature importance、训练任务血缘、相关回测/信号产物。

## Stage 4: Data Explorer Workbench

- [x] 数据状态总览：qlib 路径、cache 类型、文件数、更新时间、大小、过期提示。
- [x] 数据操作区重排：fetch、force refresh、purge expired，dry-run 影响转成人类可读摘要。
- [x] 数据观察区强化：行情、板块/行业、替代数据缓存覆盖率。
- [x] 历史区展示最近抓取/清理任务及失败原因。

## Stage 5: Factor Research Workbench

- [x] 明确页面目的：验证因子是否值得进入训练或候选研究。
- [x] 因子库：注册因子、数据依赖、可用状态。
- [x] 因子评估：IC / RankIC / ICIR / coverage / rolling IC 图。
- [x] 因子挖掘：候选生成、评估、通过/拒绝的流程式 UI。
- [x] 空状态和文案解释下一步动作，而不是裸露 JSON/表格。

## Parallel Workstreams

| Workstream | Owner | Write Scope |
|---|---|---|
| Global shell | Main agent | `Sidebar`, `Layout`, `ConsolePageLayout`, global CSS, shared i18n |
| Backtest | Worker B | `pages/BacktestPage.tsx`, `pages/backtest/*`, `api/backtest.ts`, `schemas/backtest.ts`, backtest router if needed |
| Signals | Worker C | `SignalsPage`, `api/signals.ts`, `schemas/signals.ts`, signals router/cache parsing |
| Models | Worker D | `ModelsPage`, `api/models.ts`, `schemas/train.ts`, models router preview if needed |
| Data + Factors | Worker E | `DataExplorerPage`, `ResearchPage`, `api/data.ts`, factor/data front-end and related router read-only endpoints if needed |

Main agent owns final integration, i18n reconciliation, visual pass, full tests, build, and commit.

## Acceptance Gate

```bash
./.venv/bin/python -m pytest test/ -q
cd web/frontend && npx tsc --noEmit && npm run build
./.venv/bin/python -m pytest test/test_web_console_e2e.py -q
```

Manual/visual checks:

- 左侧栏固定且所有主页面可导航。
- 页面不再大面积纯白，整体像专业量化研究台。
- Backtest 可选择/查看 benchmark，并能看到净值、基准、回撤和指标。
- Signals 可看到历史缓存，并可视化持仓/市值变化。
- Models 训练参数足够覆盖常用研究配置。
- Data Explorer 能判断数据健康与缓存状态。
- Factor Research 能让用户理解并执行因子有效性验证流程。
