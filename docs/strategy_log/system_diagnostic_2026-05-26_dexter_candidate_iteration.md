# Dexter 可借鉴结构与 quant_ex 候选迭代报告

日期：2026-05-26
状态：diagnostic_only / research_candidate planning
来源项目：`/Users/weidian/code/dexter`
目标项目：`/Users/weidian/code/quant_ex`

## 0. 结论摘要

Dexter 对 quant_ex 的价值不在于替代训练、回测、WFV 或每日调仓链路，而在于提供一套已经产品化的“金融研究 Agent 外围结构”：金融工具路由、SEC/网页证据读取、研究 skill、scratchpad、上下文预算、memo/report artifact、cron/heartbeat 监控、gateway/session 产品化。

建议把 Dexter 借鉴点放在 quant_ex 的 `agent/strategy_iteration/` 和 `docs/strategy_log/` 层，作为 diagnostic_only / research_candidate 的研究增强，不进入 `run_daily.py`、`run_scheduled_rebalance.py` 或 `config/strategy_candidates.yaml` 的默认 selected/promoted 配置。

优先级最高的候选迭代：

1. `P0`：新增结构化 run scratchpad 与 result budget，提升 agent run 的可审计性和大结果治理。
2. `P0`：建立 quant_ex 版候选报告 workflow，输出 markdown + json，带 thesis、evidence、tripwire、monitor KPI、状态建议。
3. `P1`：自然语言筛选条件到离线候选池/诊断 filter DSL，作为 research_candidate，不自动交易。
4. `P1`：公告/事件证据两阶段读取计划，用于失败归因和候选解释，严格避免 look-ahead。
5. `P1`：heartbeat-style 监控，只在 tripwire、数据异常、候选状态变化时提醒，常态静默。
6. `P2`：eval harness 与 skill schema 化，让研究 workflow 可测试、可版本化。

## 1. 研究范围与方法

本次通过并行只读子任务研究 Dexter 与 quant_ex：

- 子任务 A：Agent 核心、工具执行、scratchpad、上下文压缩、memory。
- 子任务 B：金融工具层、Financial Datasets API、search/fetch/browser、formatter/cache。
- 子任务 C：skills、investment memo、evals、cron、gateway 产品化结构。
- 子任务 D：quant_ex 当前 agent/策略迭代边界、可承接位置和 guardrails。

约束：

- 未修改 Dexter。
- 未运行网络请求、gateway、cron、训练、回测、WFV、数据刷新。
- quant_ex 当前工作树已有未提交改动，本报告仅新增一个 docs artifact，不覆盖已有代码。
- CodeGraph 在 Dexter 未初始化，子任务使用本地文件读取和搜索完成。

## 2. Dexter 架构观察

### 2.1 Agent 主循环与事件流

关键文件：

- `src/agent/agent.ts`
- `src/agent/tool-executor.ts`
- `src/agent/run-context.ts`
- `src/agent/scratchpad.ts`
- `src/agent/microcompact.ts`
- `src/agent/compact.ts`

Dexter 的主循环是迭代式 tool-calling agent：

1. 构建 system prompt、history、current query。
2. 每轮 microcompact，剥离旧 reasoning。
3. 流式调用 LLM。
4. 若无 tool call，直接输出 final answer。
5. 若有 tool call，按 concurrencySafe 分组执行工具。
6. 大结果落盘，tool messages 进入上下文。
7. 接近阈值时 full compaction，必要时 overflow hard truncate。
8. 通过 async generator 输出 typed events。

事件类型包括：`thinking`、`tool_start`、`tool_progress`、`tool_end`、`tool_error`、`microcompact`、`compaction`、`context_cleared`、`memory_flush`、`queue_drain`、`done`。

可借鉴点：quant_ex 的 `agent/strategy_iteration/orchestrator.py` 目前更偏同步 build/save，可引入 typed event stream 表达 context collection、role start/end、artifact write、proposed action、approval wait、feedback ingest、diagnostic output。这样 Web dashboard、CLI 和未来通知层可以共享同一事件协议。

### 2.2 工具注册与并发安全

关键文件：

- `src/tools/registry.ts`
- `src/agent/tool-executor.ts`

Dexter 的 `RegisteredTool` 同时保存：

- tool name
- LangChain tool instance
- rich description
- compactDescription
- concurrencySafe

工具执行器会将连续的并发安全工具 batch parallel 执行，非安全工具串行；写文件/改文件需要 approval。并发结果最终按原始 tool_calls 顺序回填，避免上下文乱序。

可借鉴点：quant_ex 可以做 `ActionRegistry`，把已有 agent action 分为：

- read-only context summary / diagnostics：concurrency_safe=true
- lightweight pytest / compile / static scan：concurrency_safe=false 或 bounded
- training/backtest/WFV/data refresh/notification/rebalance-like：requires_approval=true，默认不执行
- write proposal / approval template：requires_review=true

### 2.3 Scratchpad 与审计日志

关键文件：`src/agent/scratchpad.ts`

Dexter 每个 query 创建 `.dexter/scratchpad/*.jsonl`，记录：

- init query
- thinking
- tool_result，包括 args、result、summary、source path
- compaction boundary
- tool usage warnings

这既是调试证据，也是 agent 的过程审计。

quant_ex 当前已有 `docs/strategy_log/agent_runs/`、`agent_memory.md`、run bundle，但缺一个轻量 append-only scratchpad 作为单次 run 的事件事实源。建议新增：

- `agent/strategy_iteration/scratchpad.py`
- 输出到 gitignored 或 run-local 目录，例如 `docs/strategy_log/agent_runs/<run_id>/scratchpad.jsonl`

建议事件字段：

```json
{
  "type": "role_report | artifact_summary | proposed_command | approval_decision | diagnostic_result | feedback | error",
  "timestamp": "...",
  "run_id": "...",
  "role": "...",
  "action": "...",
  "args_preview": "...",
  "result_preview": "...",
  "artifact_path": "...",
  "status": "ok | error | skipped",
  "decision_label": "diagnostic_only | research_candidate | not_promotable"
}
```

### 2.4 上下文与大结果预算

关键文件：

- `src/utils/tool-result-storage.ts`
- `src/utils/tool-result-budget.ts`
- `src/agent/microcompact.ts`
- `src/agent/compact.ts`

Dexter 的治理模式：

- 单个工具结果超过阈值，完整内容落盘，prompt 中只放 preview + path。
- 单轮工具结果总预算超过阈值，优先持久化最大结果。
- microcompact 清旧 tool message 内容。
- full compact 使用 fast model 生成结构化摘要。

quant_ex 的 backtest/WFV/attribution CSV、factor diagnostic、daily failure attribution 很容易超过 prompt 预算。建议新增：

- `agent/strategy_iteration/result_budget.py`
- `agent/strategy_iteration/compact.py`

要求：

- 原始 CSV/JSON/报告路径是事实源。
- prompt 只注入 metric summary、top rows、control comparison、risk notes、artifact path。
- LLM summary 只能辅助解释，不能替代原始指标。

### 2.5 Memory 系统

关键文件：`src/memory/`

Dexter 有较完整的持久记忆：markdown memory、daily memory、SQLite/FTS、embedding indexer、hybrid search、temporal decay、MMR、session context load、memory flush。

quant_ex 已有 `agent/strategy_iteration/memory.py` 与 `docs/strategy_log/agent_memory.md`，更适合先做轻量结构化检索，而不是一步到位引入 embedding：

- 按 strategy_id、run_id、decision、market、metric、date 建 keyword index。
- 结合 recency 与 decision label 过滤。
- 每次 agent run 加载与 objective 最相关的 5-10 条长期记忆。
- 自动写入长期策略结论仍需严格 gate，不允许 compaction 自动晋升为策略结论。

## 3. Dexter 金融工具层观察

### 3.1 能力矩阵

| Dexter 工具 | 作用 | 可借鉴结构 | quant_ex 借鉴方式 |
|---|---|---|---|
| `get_financials` | 自然语言路由到财报、key ratios、segments、earnings | meta-tool + 子工具 schema + formatter | 自然语言到本地因子/财务字段诊断计划 |
| `get_market_data` | 价格、新闻、insider、13F、crypto | price + event explanation | 日度失败归因增强，解释而非预测 |
| `read_filings` | 两阶段读取 SEC filings：plan -> item selection | 最小证据读取计划 | A 股公告/年报/业绩预告证据读取器 |
| `stock_screener` | 自然语言转 screener filters | schema discovery + LLM structured output | 自然语言筛选条件 -> 离线候选池 filter DSL |
| `web_search` | Exa/Perplexity/Tavily/LangSearch fallback | provider chain | 增强 knowledge scout 来源鲁棒性 |
| `web_fetch` | Readability + cache + truncation | one-shot page reader | 外部资料读取与缓存，默认研究阶段使用 |
| `browser` | JS 页面和交互式读取 | snapshot/action/read | 仅用于少量不可静态读取页面，不进默认链路 |

### 3.2 数据源边界

Dexter 的金融数据主要是 Financial Datasets API、SEC、Exa/Tavily/Perplexity 等，偏美股。quant_ex 是 A 股低频 qlib 框架，所以不能直接迁移数据源语义：

- SEC filing 不等于 A 股公告。
- insider/13F 不等于 A 股董监高、股东户数、机构/北向持仓。
- 美股 ticker 与 A 股代码、交易日历、公告披露时点不同。
- 最新 snapshot 回测历史时存在 look-ahead 风险。

因此迁移对象应该是 workflow 和工具协议，而不是直接搬 API。

### 3.3 可落地金融研究候选

#### Candidate F1：自然语言因子/财务诊断路由

状态：diagnostic_only

设计：

- 输入：“检查近期失败是否和高估值、高拥挤、盈利质量恶化有关”。
- 读取本地可用 factor/fetcher schema。
- 输出诊断计划：需要的字段、时间窗、对照组、统计指标。
- 执行只读诊断，生成 artifact summary。

落点：

- `agent/strategy_iteration/action_registry.py`
- `agent/strategy_iteration/context.py`
- `agent/strategy_iteration/factor_diagnostic_router.py`

不可做：自动修改因子配置、自动加入训练、自动推广策略。

#### Candidate F2：自然语言筛选条件到候选池 filter DSL

状态：research_candidate

设计：

- 仿 `stock_screener`。
- 先枚举 quant_ex 可用字段 schema：Alpha158 因子、基本面缓存、北向/行业/流动性/风险字段。
- LLM 只生成结构化 filter DSL。
- deterministic validator 检查字段存在、缩放、滞后、point-in-time。
- 输出候选 universe CSV 或 diagnostic report，默认 disabled。

示例 DSL：

```yaml
filters:
  - field: valuation.pe_ttm_rank_industry
    op: lt
    value: 0.3
  - field: quality.roe_ttm
    op: gt
    value: 0.12
  - field: liquidity.avg_turnover_20d
    op: gt
    value: 100000000
window:
  asof_date: signal_date
  lag_days: 1
output:
  kind: candidate_universe
  max_names: 200
```

#### Candidate F3：公告/事件证据两阶段读取

状态：diagnostic_only -> research_candidate

设计：

- 阶段 1：根据 objective 规划股票、公告类型、时间窗、最大读取数。
- 阶段 2：选择最小证据片段，摘要成 event card。
- 与 daily failure attribution 或候选报告结合。

核心 guardrail：所有事件必须使用公告发布日期/可得日期，禁止用报告期或最新摘要回填历史。

#### Candidate F4：价格 + 新闻/公告解释型失败归因

状态：diagnostic_only

设计：

- 读取 top loss days、持仓变动、行业暴露、价格异常。
- 查询对应日期附近公告/新闻/市场事件摘要。
- 输出“解释卡片”：可能事件、证据、是否可交易、是否只是事后叙事。

不可做：把新闻解释直接作为 alpha，或在无 WFV 情况下改模型。

## 4. Dexter 产品化结构观察

### 4.1 Skills / SOP

关键目录：`src/skills/`

Dexter 的 skill 是 markdown SOP，带 frontmatter 与 workflow checklist。代表 `write-memo` 把 investment memo 固化成：

1. frame trade
2. gather data
3. build scenarios
4. optional DCF
5. draft content
6. self-critique
7. render artifact
8. return short header

quant_ex 可建立类似 SOP，但要更偏量化候选：

- `candidate-review`
- `pool-refresh`
- `factor-drift-monitor`
- `daily-failure-explain`
- `risk-tripwire-check`
- `promotion-readiness-review`

建议不要只写 prompt，要配 input_schema、output_schema、eval_cases。

### 4.2 Report artifact

Dexter memo 的重要思想：交付物是文件，不是聊天长文。quant_ex 借鉴时建议双输出：

- `*.md`：给人读，可进入 `docs/strategy_log/`。
- `*.json`：给系统复盘、候选池状态机和 eval 使用。

候选报告建议字段：

```json
{
  "candidate_id": "...",
  "status_recommendation": "raw | research_pending | watchlist | actionable | rejected | expired",
  "decision_label": "diagnostic_only | research_candidate | not_promotable | compare_next | promotable_pending_human_review",
  "signal_evidence": [],
  "data_quality_notes": [],
  "scenario": {
    "bear": {},
    "base": {},
    "bull": {}
  },
  "tripwires": [],
  "monitoring_kpis": [],
  "required_validation": [],
  "artifact_paths": []
}
```

### 4.3 Cron / heartbeat

关键目录：`src/cron/` 与 `src/gateway/heartbeat/`

Dexter 的 cron executor 要求无事返回 OK，有 actionable event 才发送；heartbeat suppression 会过滤 “nothing to report” 类噪音。

quant_ex 可借鉴为：

- 候选池 tripwire monitor。
- 模型/数据健康 monitor。
- 每日失败归因 monitor。
- WFV candidate watch monitor。

原则：常态静默，只在状态变化、tripwire、异常、数据缺口、验证失败时提醒。

### 4.4 Evals

Dexter eval 主要是 finance QA + LLM-as-judge + LangSmith。quant_ex 更适合混合 eval：

- deterministic checks：字段完整性、JSON schema、状态转移合法性、无空 tripwire、无 forbidden decision。
- fact checks：关键指标是否来自 artifact path，是否带 benchmark/control。
- LLM judge：报告是否解释清楚、风险是否充分、bear case 是否 steelman。
- historical checks：候选状态变化是否与后续验证结果冲突。

## 5. quant_ex 当前承接边界

### 5.1 现有能力

quant_ex 已有：

- `agent/strategy_iteration/` 多角色策略迭代。
- `run_agent_strategy_iteration.py` 生成计划、命令提案、审批模板、feedback、promotion report。
- `docs/strategy_log/` 长期策略与系统日志。
- `agent_execution.py` approval/worktree/coding-agent 任务提案。
- performance attribution 与 diagnostic-only 工具。
- `run_daily.py`、`run_scheduled_rebalance.py` 日常信号/调仓辅助链路。

### 5.2 不应触碰的位置

Dexter 借鉴点初期不应直接接入：

- `run_daily.py`
- `run_scheduled_rebalance.py`
- launchd / real notification
- `config/daily_*.yaml`
- selected/promoted strategy configs
- live rebalance action

### 5.3 应该承接的位置

优先承接：

- `agent/strategy_iteration/`
- `docs/strategy_log/system_diagnostic_*.md`
- `docs/strategy_log/agent_runs/<run_id>/`
- report-only CLI scripts
- lightweight tests under `test/test_agent_strategy_iteration*.py`

## 6. 推荐迭代路线图

### P0-1：Run Scratchpad + Result Budget

状态：diagnostic_only infrastructure

目标：为 agent run 建立 append-only 审计日志和大结果预算治理。

建议新增：

- `agent/strategy_iteration/scratchpad.py`
- `agent/strategy_iteration/result_budget.py`
- `test/test_agent_strategy_iteration_scratchpad.py`

验收：

- 可 append/read JSONL。
- 同一 run 的角色输出、诊断结果、approval 决策可追溯。
- 大 payload 持久化为 artifact，prompt preview 带 path、size、hash、top rows。
- 不修改任何策略配置。

### P0-2：Candidate Report Workflow

状态：diagnostic_only / research_candidate artifact

目标：把一次候选研究输出为结构化报告，而不是聊天摘要。

建议新增：

- `agent/strategy_iteration/candidate_report.py`
- `docs/strategy_log/candidate_reports/` 或 agent run-local 目录
- JSON schema 与 markdown renderer

报告章节：

1. Candidate identity：股票/组合/策略臂/日期/来源。
2. Signal evidence：量化信号、因子、价格、成交、行业、风险暴露。
3. Data quality：缺失、滞后、可得日期、异常值。
4. Scenario：bear/base/bull，不用于交易定价，只用于研究审议。
5. Tripwires：可观察否证条件。
6. Monitoring KPIs：后续跟踪字段。
7. Decision label：diagnostic_only / research_candidate / not_promotable / compare_next。
8. Required validation：回测、WFV、control、成本口径。

### P1-1：Filter DSL Compiler

状态：research_candidate

目标：将自然语言筛选条件编译为可验证 filter DSL，输出候选 universe 或诊断报告。

关键防线：

- 字段必须来自 schema registry。
- 所有字段必须声明 asof/lag。
- LLM 输出必须通过 deterministic validator。
- 默认只生成候选，不触发训练。

### P1-2：Announcement/Event Evidence Planner

状态：diagnostic_only

目标：借鉴 Dexter `read_filings` 两阶段计划，为 A 股公告/事件建立最小证据读取 workflow。

建议先只做报告层：

- 输入失败日期/候选股票/时间窗。
- 输出事件卡片和证据路径。
- 不进入特征工程。

后续若做因子，必须先补 point-in-time 数据合同。

### P1-3：Heartbeat-style Tripwire Monitor

状态：diagnostic_only monitor

目标：定期检查候选报告里的 tripwires 和 monitoring KPIs。

规则：

- 无变化静默。
- 状态变化才写 report/通知。
- consecutive error/backoff。
- delivery target 与真实通知需显式配置与确认。

### P2-1：Research Workflow Eval Harness

状态：quality infrastructure

目标：让 candidate report / filter DSL / event planner 可回归测试。

测试层：

- schema validity
- decision label allowed values
- no forbidden promotion
- required fields not empty
- artifact paths exist
- LLM judge optional

### P2-2：Skill Schema 化

状态：workflow governance

目标：把研究 SOP 从纯 markdown 升级为可测试 workflow spec。

每个 skill/workflow 包含：

- name/version/owner
- input_schema
- output_schema
- guardrails
- required artifacts
- eval cases
- allowed actions

## 7. Guardrails

必须保留以下边界：

- `diagnostic_only`：Dexter 借鉴初期只做诊断、解释、候选生成、报告，不生成交易信号。
- `research_candidate`：候选需要独立回测/WFV 才能进入策略记录或配置。
- `not_promotable`：backtest-only、same-model、局部窗口、无 control、无 WFV、无成本/滑点口径，均不可推广。
- `approval_required`：完整 WFV、训练、数据刷新、真实通知、daily/default 配置替换、调仓相关 side effect 都需用户显式批准。
- `one_major_variable_per_arm`：每轮实验只改一个主变量，保留稳定对照臂。
- `no_daily_boundary_crossing`：不得自动修改 `run_daily.py`、`run_scheduled_rebalance.py` 或日常配置。
- `point_in_time_required`：公告/新闻/财务/事件数据必须有可得日期，不允许未来函数。
- `artifact_is_source_of_truth`：LLM 摘要不是事实源，原始 artifact path 和 deterministic metrics 才是事实源。

## 8. 建议的报告/产物位置

本报告位置：

- `docs/strategy_log/system_diagnostic_2026-05-26_dexter_candidate_iteration.md`

未来建议：

- 单次 agent run：`docs/strategy_log/agent_runs/<run_id>/`
- 系统级设计结论：`docs/strategy_log/system_diagnostic_YYYY-MM-DD_<topic>.md`
- 候选报告：`docs/strategy_log/candidate_reports/<date>_<candidate_id>.md`
- 机器可读候选状态：`docs/strategy_log/candidate_reports/<date>_<candidate_id>.json`

除非通过 WFV promotion gates，不建议更新：

- `config/strategy_candidates.yaml` selected/promoted 区
- daily rebalance configs
- launchd/notification configs

## 9. 建议下一步

推荐下一步只做 P0 小切片：

1. 实现 `Run Scratchpad + Result Budget`，只影响 agent run 审计与上下文治理。
2. 实现一个 report-only `Candidate Report Workflow` 原型，输入本地已有 signal/attribution artifact，输出 markdown + json。
3. 为上述两项加轻量单测，不运行训练/WFV。

建议不要马上做：

- 自动候选池筛选并接入训练。
- 公告/新闻入模。
- WhatsApp/gateway 搬迁。
- 自动通知或 daily 调仓集成。

## 10. 子任务摘要

- Agent 核心子任务结论：最值得迁移的是 event stream、scratchpad、action registry、result budget、deterministic compaction，避免照搬 LangChain/TypeScript runtime。
- 金融工具子任务结论：最值得迁移的是 meta-tool 路由、filter DSL、两阶段证据读取、formatter/cache/source URL，不直接迁移美股 API。
- 产品化子任务结论：最值得迁移的是 skill/SOP、file artifact、heartbeat-style monitor、eval harness，gateway 需改造后再考虑。
- quant_ex 边界子任务结论：承接位置是 `agent/strategy_iteration/` 与 `docs/strategy_log/`，不得越过 WFV/审批/daily 边界。
