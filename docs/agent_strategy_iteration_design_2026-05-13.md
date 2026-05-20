# Agent Strategy Iteration Design: RD-Agent + TradingAgents-ex Lessons for quant_ex

Date: 2026-05-13

## 1. Executive Summary

本报告分析 `/Users/weidian/code/RD-Agent` 与 `/Users/weidian/code/TradingAgents-ex` 的设计和实现，并给出 `quant_ex` 的 agent 化策略迭代改造方案。

核心判断：

1. `quant_ex` 不应该直接复制两个项目的完整框架。RD-Agent 的 workspace/codegen/session 体系太重，TradingAgents-ex 的 LangGraph 单票交易流程也不适合直接放进低频 A 股策略研发。
2. 真正应该吸收的是 RD-Agent 的“科学研发闭环”和 TradingAgents-ex 的“角色化审议机制”。
3. 改造目标不是让 LLM 直接替代回测或交易，而是增加一个可审计、可复用、可扩展的 agent research layer。这个 layer 负责提出假设、设计对照实验、组织多角色辩论、定义验证门槛、沉淀知识，再交给现有 `quant_ex` 的训练、回测、WFV、信号、调仓模块执行。
4. 第一阶段应先实现设计与提示词协议，再做轻量 orchestrator。不要一开始就做自动代码生成、自动训练、自动调仓。

推荐的最小闭环：

```text
Research Brief
  -> Context Pack
  -> Hypothesis Generation
  -> Experiment Design
  -> Analyst Reports
  -> Bull/Bear Debate
  -> Risk Debate
  -> Research Portfolio Manager Decision
  -> Validation Plan
  -> Execution by existing quant_ex commands
  -> Evaluation Feedback
  -> Memory/Trace Update
```

## 1.1 Implementation Status: 2026-05-13

The proposed design has been implemented as a lightweight module rather than a direct import of RD-Agent or TradingAgents-ex.

Implemented modules:

- `agent/strategy_iteration/schemas.py`: role reports, plans, run bundles, command proposals, feedback objects
- `agent/strategy_iteration/context.py`: local context pack from strategy/system logs, candidates, configs, artifacts, and memory
- `agent/strategy_iteration/roles.py`: offline and LLM role execution with upstream role carry-over plus optional virtual-chair meeting mode
- `agent/strategy_iteration/llm.py`: OpenAI-compatible quick/deep tier client, including streaming responses
- `agent/strategy_iteration/execution.py`: command proposals, risk tags, approval templates, command hash matching, execution summaries
- `agent/strategy_iteration/agent_execution.py`: approved local coding-agent task proposals and Codex CLI execution scaffolding
- `agent/strategy_iteration/evaluator.py`: backtest/WFV CSV feedback parsing
- `agent/strategy_iteration/attribution.py`: Phase7 performance attribution report for control/candidate comparison and experiment-budget guidance
- `run_agent_strategy_iteration.py`: CLI for planning, command proposal, approved execution, and feedback handoff
- `/api/agents` and Web `Agent Runs` page: browse/create agent runs and regenerate approval templates
- Discussion modes: default `sequential` preserves fixed role order; optional `meeting` lets a virtual chair select necessary roles and stop the discussion when enough evidence exists. Meeting runs have configurable caps for total rounds and roles per round.
- Coding-agent layer: optional `--use-agent` writes `agent_tasks.*` and `agent_approval_template.yaml`; `readonly` / `patch` / reserved `danger-full-access` modes remain approval-gated before any local Codex CLI execution.

Full-cycle validation:

- Run id: `full_agent_train_backtest_20260513`
- Path: `docs/strategy_log/agent_runs/full_agent_train_backtest_20260513/`
- Real LLM roles: 12/12, with `gpt-5.4-mini` quick tier and `gpt-5.5` deep tier
- Strict training config: `train_csi1000_eval_csi300.yaml`
- Strict model: `models/lgbm_agent_full_iter_csi1000_20260513_20260513_210545.pkl`
- Backtest result: Sharpe `1.2490`, IR `0.5774`, MaxDD `-20.86%`
- Feedback decision: `reject/refuted` versus `fundamental_control_15_3_8_20260511`

Interpretation:

- The agent workflow is operational end-to-end: role discussion, trace, training, backtest CSV, feedback, and memory reflection.
- The strict csi1000 retrain candidate itself is not a promotion candidate.
- The correct next use of the framework is a smaller, control-matched ablation or a return to the existing baseline control.
- `docs/strategy_log/agent_runs/` is local/generated and ignored by default; durable conclusions belong in `strategy_iteration_log.csv`, `system_iteration_log.csv`, `config/strategy_candidates.yaml`, and concise Markdown summaries.

## 1.2 Phase7 Status: 2026-05-18

Phase7 adds performance attribution and experiment-budget control. The agent layer now has to diagnose the current bottleneck before proposing research spend.

Implemented additions:

- `agent/strategy_iteration/attribution.py` builds `attribution_report.json/md` for control/candidate comparisons.
- `context.py` injects `artifact_summaries.performance_attribution` into every context pack when evidence is available.
- `orchestrator.py` recognizes Phase7-style objectives and emits only one `primary_experiment` plus one `cheap_diagnostic`.
- Run bundles save `attribution_report.*` next to `plan.md`.

Current interpretation:

- `adaptive_dd20_wf` is a stability base, not a return upgrade.
- The current bottleneck is `return_repair`: recover return without losing 7/7 positive folds or drawdown advantage.
- Phase7 is not itself alpha. Its contribution is valid only if it reduces wasted experiments and improves the next experiment choice.

Contribution test:

1. Compare a pre-Phase7 run and a Phase7 run for the same objective.
2. Phase7 should remove broad infrastructure arms and repeated failed routes.
3. Phase7 should identify the control, candidate, bottleneck, recommended primary experiment, and kill criteria.
4. The following real experiment must either improve WFV metrics or be killed faster with less compute/research spend.

## 2. RD-Agent Design Analysis

### 2.1 Core Philosophy

RD-Agent 的主线不是“聊天式多 agent”，而是将研发活动抽象成可迭代的科学流程：

```text
Hypothesis
  -> Experiment
  -> Implementation
  -> Execution
  -> Feedback
  -> Trace / Knowledge
  -> New Hypothesis
```

对 `quant_ex` 最有价值的思想有四个：

1. **每轮必须有明确 hypothesis**
   不是“调一下 topk 看看”，而是说明为什么调、预期改善什么指标、可能失败在哪里。

2. **实验对象与反馈对象结构化**
   `Hypothesis`, `Experiment`, `ExperimentFeedback`, `Trace` 是核心抽象。反馈不只是 metrics，还包括 observation、hypothesis evaluation、new hypothesis、decision。

3. **last result 与 SOTA result 分开注入**
   RD-Agent 的 prompt 不只看最近一次实验，还显式注入最后一次实验和当前 SOTA。这避免 agent 被最近结果带偏。

4. **trace 是下一轮研究的知识源**
   失败实验不是垃圾，失败原因会进入下一轮 prompt。

### 2.2 Key Workflow Classes

RD-Agent 的关键类和职责：

| Component | File | Responsibility |
|---|---|---|
| `RDLoop` | `rdagent/components/workflow/rd_loop.py` | 组织 propose, coding, running, feedback, record steps |
| `LoopBase` | `rdagent/utils/workflow/loop.py` | step 级可恢复流程、并发限制、session dump/load |
| `Trace` | `rdagent/core/proposal.py` | 存储实验历史、DAG parent、SOTA selection |
| `Hypothesis` | `rdagent/core/proposal.py` | 研究假设及原因 |
| `ExperimentFeedback` / `HypothesisFeedback` | `rdagent/core/proposal.py` | 反馈、决策、新假设 |
| `EvolvingStrategy` / `RAGEvoAgent` | `rdagent/core/evolving_framework.py`, `evolving_agent.py` | 更通用的 evolution + RAG + feedback 机制 |
| `QlibQuantHypothesisGen` | `rdagent/scenarios/qlib/proposal/quant_proposal.py` | 在 factor/model 之间选择下一步方向 |

RDLoop 的 step 设计非常清晰：

```text
direct_exp_gen:
  hypothesis_gen.gen(trace, plan)
  hypothesis2experiment.convert(hypothesis, trace)

coding:
  coder.develop(experiment)

running:
  runner.develop(coded_experiment)

feedback:
  summarizer.generate_feedback(running_result, trace)

record:
  trace.sync_dag_parent_and_hist((experiment, feedback), loop_id)
```

对 `quant_ex` 的启发：

```text
proposal:
  生成策略/因子/模型/执行假设

experiment_design:
  生成对照臂和处理臂，不直接改代码

validation_planning:
  给出轻量测试、same-model backtest、WFV、风险检查

evaluation:
  解析 quant_ex 已有 CSV/日志/sidecar，生成 HypothesisFeedback

record:
  写 agent trace 和必要时追加 strategy_iteration_log
```

### 2.3 RD-Agent Prompt Design Worth Absorbing

RD-Agent 的 qlib prompt 文件是精华之一。关键 prompt 结构如下。

#### 2.3.1 Trace Prompt

`hypothesis_and_feedback` 模板包含：

```text
Trial N
  Hypothesis
  Specific task
  Backtest Result
  Observation
  Hypothesis Evaluation
  Decision
```

这个结构很适合 `quant_ex`。建议 `quant_ex` 的 agent trace 每轮至少包含：

```yaml
trial_id:
parent_trial_id:
hypothesis:
experiment_arms:
changed_variables:
config_paths:
model_paths:
metrics:
observations:
hypothesis_evaluation:
decision:
new_hypothesis:
failure_modes:
next_ablation:
```

#### 2.3.2 Last + SOTA Prompt

RD-Agent 分别提供：

- `last_hypothesis_and_feedback`
- `sota_hypothesis_and_feedback`

这对 `quant_ex` 很重要。因为当前项目已经多次出现“same-model 好看但 WFV 失败”的情况，下一轮 agent 不能只看最新实验，必须同时看：

1. 最近实验，避免重复踩坑。
2. 当前 SOTA/基线，避免忘记主要对照。
3. 被拒绝但有启发的实验，避免错误泛化。

#### 2.3.3 Factor Hypothesis Prompt

RD-Agent 的 factor prompt 有几个原则：

1. 每轮 1 到 5 个 factor。
2. 先简单有效，再逐步复杂。
3. 连续失败后切换方向。
4. 避免重新实现已进入 SOTA library 的因子。
5. 每个 factor 必须有 name, description, formulation, variables。

映射到 `quant_ex`：

```text
新因子/数据源 proposal 必须写清：
  - factor family
  - point-in-time lag policy
  - required cache/fetcher
  - expected alpha channel
  - expected redundancy with Alpha158 or existing factors
  - IC/ICIR target
  - correlation de-dup rule
  - failure criterion
```

#### 2.3.4 Model Hypothesis Prompt

RD-Agent 的 model prompt 强调：

1. 先分析前序模型不足：参数、结构、缺乏新意。
2. 关注 last 与 SOTA。
3. 训练差时先考虑超参，而不是盲目换复杂模型。
4. 控制模型规模。
5. 明确 model_type 和训练超参。

映射到 `quant_ex`：

模型 agent 不应该频繁推荐深度模型。应先问：

```text
是否有证据显示当前 LGBM 的错误来自模型容量，而不是数据噪声或因子冗余？
是否可以通过 rank objective、sample weighting、rolling retrain、seed robustness 解决？
是否会破坏可解释性、训练时间、WFV 成本？
```

#### 2.3.5 Feedback Prompt

RD-Agent 的 feedback prompt 强制输出：

```json
{
  "Observations": "...",
  "Feedback for Hypothesis": "...",
  "New Hypothesis": "...",
  "Reasoning": "...",
  "Decision": true
}
```

对 `quant_ex` 应改成：

```json
{
  "observations": "...",
  "hypothesis_evaluation": "supported | refuted | mixed | inconclusive",
  "metric_comparison": {
    "control": {},
    "treatment": {},
    "delta": {}
  },
  "risk_comparison": {},
  "decision": "promote | compare_next | reject | revisit_later",
  "new_hypothesis": "...",
  "next_ablation": "...",
  "do_not_repeat": ["..."]
}
```

### 2.4 RD-Agent Features Not to Import Directly

不建议第一阶段引入：

1. 自动 workspace 注入和代码生成。`quant_ex` 已经有稳定模块边界，自动代码生成风险高。
2. RD-Agent 的完整 Docker/session/UI 框架。对当前目标过重。
3. qlib 模板体系。会和 `quant_ex` 已有 pipeline 重叠。
4. “小幅 annual_return 改善即可替换 SOTA”的判断规则。`quant_ex` 更重视 WFV、IR、drawdown、成本和稳定性，不应照搬。

## 3. TradingAgents-ex Design Analysis

### 3.1 Core Philosophy

TradingAgents-ex 的精华是“角色化审议”，而不是单一 LLM 直接给交易建议。

其流程：

```text
Analyst Team
  Market Analyst
  Sentiment Analyst
  News Analyst
  Fundamentals Analyst
    -> Bull Researcher
    -> Bear Researcher
    -> Research Manager
    -> Trader
    -> Aggressive Risk Analyst
    -> Conservative Risk Analyst
    -> Neutral Risk Analyst
    -> Portfolio Manager
```

对 `quant_ex` 的映射：

```text
Analyst Team
  Data/Factor Analyst
  Model Analyst
  Backtest/Metric Analyst
  Execution/Risk Analyst
    -> Bull Researcher
    -> Bear Researcher
    -> Research Manager
    -> Experiment Designer
    -> Aggressive Research Risk
    -> Conservative Research Risk
    -> Neutral Research Risk
    -> Research Portfolio Manager
```

这里的 Portfolio Manager 不应输出 Buy/Sell，而应输出研究资源分配决策：

```text
Promote
Compare Next
Hold
Reject
Retire
```

### 3.2 LangGraph Flow and State

TradingAgents-ex 使用 `StateGraph(AgentState)`，状态包含：

- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`
- `investment_debate_state`
- `investment_plan`
- `trader_investment_plan`
- `risk_debate_state`
- `final_trade_decision`
- `past_context`

关键设计点：

1. 每个 analyst 只负责一个视角。
2. report 写入共享 state，后续角色消费。
3. debate state 单独维护 bull/bear 或 risk 三方历史。
4. manager 节点使用结构化输出。
5. memory log 把过去决策和未来 outcome/reflection 重新注入。
6. checkpoint resume 用于长流程恢复。

`quant_ex` 不一定需要 LangGraph，但需要类似 state。

建议状态结构：

```yaml
StrategyAgentState:
  objective:
  run_id:
  date:
  context_pack:
    strategy_candidates:
    recent_strategy_log:
    recent_system_log:
    available_artifacts:
    constraints:
  analyst_reports:
    data_factor_report:
    model_report:
    backtest_report:
    execution_report:
  debate_state:
    bull_history:
    bear_history:
    judge_decision:
    count:
  experiment_plan:
    control_arm:
    treatment_arms:
    validation_ladder:
  risk_debate_state:
    aggressive_history:
    neutral_history:
    conservative_history:
    judge_decision:
    count:
  final_research_decision:
  memory_context:
```

### 3.3 TradingAgents Prompt Design Worth Absorbing

#### 3.3.1 Analyst Prompts

Analyst prompt 的共同模式：

```text
You are a specialized analyst.
Use available tools/data.
Produce a comprehensive report.
Provide specific, actionable insights with evidence.
Append a Markdown table.
```

`quant_ex` 可改成：

```text
你是 {data/model/backtest/execution} analyst。
只能基于 context pack 中的证据提出结论。
必须输出：
  1. Findings
  2. Evidence
  3. Candidate hypotheses
  4. What would falsify them
  5. Markdown table of proposed experiments
```

#### 3.3.2 Sentiment Analyst Redesign

TradingAgents-ex 的 sentiment analyst 有一个重要演进：旧 prompt 要求 social-media analysis，但工具只给 Yahoo Finance news，导致模型编造 Reddit/X/StockTwits。新版改成 pre-fetch 多源数据，并用 `<start_of_x>` block 注入。

这对 `quant_ex` 很关键：

1. 不要让 agent 在没有数据时假装分析。
2. 若未来接入新闻、公告、研报、问董秘、产业链数据，应先 fetch/cache，然后把数据块注入 prompt。
3. prompt 必须要求“数据不可用就说不可用”。

建议设计：

```text
<start_of_factor_importance>
...
<end_of_factor_importance>

<start_of_wfv_summary>
...
<end_of_wfv_summary>

<start_of_rejected_experiments>
...
<end_of_rejected_experiments>
```

#### 3.3.3 Bull/Bear Debate

TradingAgents-ex 的 bull/bear prompt 不是静态正反观点，而是要求：

- 直接回应对方观点。
- 用具体证据反驳。
- 保持 debate engagement。
- 不只是列数据。

映射到 `quant_ex`：

Bull Researcher：

```text
为实验 arm 提出最强支持理由：
  - 为什么该假设可能带来真实 alpha 或稳定性提升
  - 哪些历史证据支持它
  - 预期改善哪些指标
  - 为什么值得消耗一次 WFV 预算
```

Bear Researcher：

```text
攻击该实验 arm：
  - 是否只是 same-model 过拟合
  - 是否与 Alpha158 或已有因子冗余
  - 是否有 leakage/lag 风险
  - 是否增加集中度、换手、成本、执行复杂度
  - 哪些 kill tests 能快速否决
```

#### 3.3.4 Research Manager

TradingAgents-ex 的 Research Manager 使用固定五档 rating：

```text
Buy / Overweight / Hold / Underweight / Sell
```

对 `quant_ex` 应改成研究评级：

```text
Promote:
  WFV/稳定性/风险均过关，可进入候选配置。

CompareNext:
  有启发或局部改善，但证据不足，需要下一轮对照。

Hold:
  暂不动，保留当前基线。

Reject:
  证据不足或明显退化，不进入长期候选。

Retire:
  已被多轮证伪，写入 do_not_repeat。
```

#### 3.3.5 Trader Prompt

TradingAgents-ex 的 Trader 把 Research Manager 的 investment plan 转成 transaction proposal。

对 `quant_ex`，Trader 应改名为 Experiment Designer 或 Research Trader，职责是：

```text
把研究裁决转成可运行实验：
  - arm_id
  - parent_strategy_id
  - changed variable
  - config changes
  - commands
  - expected artifacts
  - approval requirements
```

#### 3.3.6 Risk Debate

TradingAgents-ex 的风险三角色非常有价值：

- Aggressive Risk Analyst: 强调高收益机会，反驳保守观点。
- Conservative Risk Analyst: 强调保本、低波动、长期稳健。
- Neutral Risk Analyst: 平衡两方，指出各自偏误。

对 `quant_ex`，可设计成：

| Role | quant_ex Question |
|---|---|
| Aggressive Research Risk | 这个实验是否值得冒 WFV 和复杂度成本追求更高收益？ |
| Conservative Research Risk | 它是否增加过拟合、回撤、集中度、执行风险？ |
| Neutral Research Risk | 有没有更小的变体或更便宜的验证路径？ |

#### 3.3.7 Portfolio Manager Prompt

TradingAgents-ex 的 PM prompt 重点：

1. 综合 risk debate。
2. 必须在固定 rating scale 中选择。
3. 引入 past_context。
4. 要 account for market-structure constraints。

对 `quant_ex`：

```text
Research Portfolio Manager 必须：
  - 综合 analyst reports, bull/bear debate, risk debate
  - 输出固定 research decision
  - 指定 promotion gate
  - 指定 cheapest next validation
  - 对 A 股约束、成本、流动性、T+1、涨跌停、停牌、调仓频率做约束说明
```

## 4. Recommended quant_ex Agent Architecture

### 4.1 Design Principles

1. **Agent layer 只做研究设计和审议，不绕过验证链路。**
2. **每个 agent 输出结构化 JSON，同时可渲染成 Markdown。**
3. **所有实验必须有 control arm。**
4. **每个 treatment arm 只改变一个主要变量。**
5. **任何耗时、联网、真实通知、实盘语义操作都只生成计划，不自动执行。**
6. **保留扩展点，未来可吸收 RD-Agent 或 TradingAgents-ex 的更新。**

### 4.2 Proposed Package Layout

```text
agent/
  strategy_iteration/
    prompts/
      analyst_data_factor.md
      analyst_model.md
      analyst_backtest.md
      analyst_execution.md
      debate_bull.md
      debate_bear.md
      manager_research.md
      experiment_designer.md
      risk_aggressive.md
      risk_conservative.md
      risk_neutral.md
      portfolio_manager.md
      feedback_evaluator.md
    schemas.py
    context_builder.py
    memory.py
    llm_client.py
    role_runner.py
    debate.py
    experiment_designer.py
    evaluator.py
    orchestrator.py
run_agent_strategy_iteration.py
config/agent_strategy_iteration.yaml
docs/strategy_log/agent_runs/
```

### 4.3 Role Topology

```text
Context Builder
  |
  +-> DataFactorAnalyst
  +-> ModelAnalyst
  +-> BacktestAnalyst
  +-> ExecutionAnalyst
       |
       v
  BullResearcher <-> BearResearcher
       |
       v
  ResearchManager
       |
       v
  ExperimentDesigner
       |
       v
  AggressiveRiskReviewer -> ConservativeRiskReviewer -> NeutralRiskReviewer
       ^                                                     |
       |-----------------------------------------------------|
       |
       v
  ResearchPortfolioManager
       |
       v
  ValidationPlan + MemoryTrace
```

### 4.4 Role Definitions

#### DataFactorAnalyst

职责：

- 审查数据覆盖、时点安全、缓存、lag policy。
- 分析因子冗余、IC/ICIR、相关性。
- 提出新数据或因子方向。

输出：

```json
{
  "role": "data_factor_analyst",
  "findings": [],
  "hypotheses": [],
  "data_requirements": [],
  "leakage_risks": [],
  "screening_plan": [],
  "do_not_repeat": []
}
```

#### ModelAnalyst

职责：

- 判断是否值得改模型。
- 区分模型容量不足、训练参数不佳、数据噪声、因子冗余。
- 推荐最小模型实验。

输出：

```json
{
  "role": "model_analyst",
  "diagnosis": [],
  "model_hypotheses": [],
  "training_risks": [],
  "expected_cost": "low | medium | high",
  "validation_plan": []
}
```

#### BacktestAnalyst

职责：

- 检查 benchmark、rank_metric、deal_price、成本滑点、时间窗一致性。
- 设计 same-model backtest 和 WFV。
- 防止不可比实验。

输出：

```json
{
  "role": "backtest_analyst",
  "comparability_checks": [],
  "control_arm": {},
  "phase1_backtest_plan": [],
  "wfv_plan": [],
  "metric_priority": []
}
```

#### ExecutionAnalyst

职责：

- 检查调仓、持仓保护、交易成本、集中度、流动性。
- 给出 scheduled rebalance/dry-run 约束。

输出：

```json
{
  "role": "execution_analyst",
  "execution_constraints": [],
  "risk_controls": [],
  "approval_required": [],
  "operational_blockers": []
}
```

#### BullResearcher

职责：

- 对候选实验提出最强支持理由。
- 说明为什么值得验证。

#### BearResearcher

职责：

- 提出最强反对理由。
- 设计 kill tests。

#### ResearchManager

职责：

- 综合 bull/bear。
- 输出初步 research rating。

评级：

```text
PromoteCandidate
CompareNext
NeedsCheaperTest
Reject
Retire
```

#### ExperimentDesigner

职责：

- 将 research plan 转换为可执行实验臂。
- 确保 one-variable-at-a-time。

输出：

```json
{
  "control_arm": {},
  "treatment_arms": [
    {
      "arm_id": "",
      "hypothesis": "",
      "changed_variable": "",
      "config_patch_plan": {},
      "commands": [],
      "artifacts": [],
      "approval_required": false
    }
  ]
}
```

#### Risk Reviewers

Aggressive:

- 说明为什么值得承担研究风险。

Conservative:

- 说明为什么应拒绝或降级。

Neutral:

- 设计折中路径和更便宜验证。

#### ResearchPortfolioManager

职责：

- 最终决策。
- 指定下一步验证 ladder。
- 指定是否写长期 strategy log。

输出：

```json
{
  "decision": "promote | compare_next | hold | reject | retire",
  "executive_summary": "",
  "approved_arms": [],
  "blocked_arms": [],
  "validation_ladder": [],
  "promotion_criteria": [],
  "memory_updates": [],
  "requires_user_approval": []
}
```

## 5. Prompt System Design for quant_ex

### 5.1 Shared System Prompt

```text
你是 quant_ex 的量化研究 agent。你不能把口头推理当成证据。
你必须基于提供的 context pack、实验日志、配置、指标和代码结构提出结论。

硬性规则：
1. 每个实验必须有明确 hypothesis。
2. 每个 treatment arm 只能改变一个主要变量。
3. 必须指定 control arm。
4. 必须写清 benchmark, rank_metric, deal_price, cost, slippage。
5. same-model backtest 只能作为过滤器，不能作为 promotion 证据。
6. WFV 是 promotion 的主要证据。
7. 不得建议真实通知、真实资金、实盘交易或完整数据更新，除非用户明确授权。
8. 数据不可用时必须说不可用，不得编造。
9. 输出必须是严格 JSON。
```

### 5.2 Context Pack Template

```text
<objective>
{{ user_objective }}
</objective>

<repo_capabilities>
{{ capabilities }}
</repo_capabilities>

<candidate_index>
{{ config_strategy_candidates_yaml }}
</candidate_index>

<recent_strategy_trace>
{{ strategy_iteration_log_tail }}
</recent_strategy_trace>

<recent_system_trace>
{{ system_iteration_log_tail }}
</recent_system_trace>

<available_artifacts>
{{ models, result csvs, configs }}
</available_artifacts>

<constraints>
{{ approval gates, environment, qlib path }}
</constraints>
```

### 5.3 Hypothesis Prompt

借鉴 RD-Agent：

```text
请基于 previous trace、last trial、SOTA/current baseline 生成一个精确、可测试、可证伪的策略研究假设。

必须输出：
{
  "hypothesis": "...",
  "reason": "...",
  "expected_metric_movement": {
    "information_ratio": "...",
    "sharpe": "...",
    "max_drawdown": "...",
    "turnover": "..."
  },
  "changed_variable": "...",
  "why_not_redundant": "...",
  "falsification_test": "..."
}
```

### 5.4 Experiment Design Prompt

```text
把研究假设转换为实验设计。必须包括一个 control arm 和最多三个 treatment arms。
每个 treatment arm 只能改变一个主要变量。

输出：
{
  "control_arm": {
    "arm_id": "...",
    "config": "...",
    "model_path": "...",
    "commands": []
  },
  "treatment_arms": [
    {
      "arm_id": "...",
      "parent_arm": "...",
      "changed_variable": "...",
      "config_patch": {},
      "commands": [],
      "metrics_to_collect": [],
      "success_criteria": [],
      "kill_criteria": [],
      "approval_required": []
    }
  ]
}
```

### 5.5 Bull/Bear Debate Prompt

Bull:

```text
你是 Bull Researcher。请为该实验设计提出最强支持理由。
必须直接回应 bear_history 中的反对意见。
不要泛泛而谈，必须引用 context pack 或已知实验证据。
```

Bear:

```text
你是 Bear Researcher。请攻击该实验设计。
必须直接回应 bull_history 中的支持意见。
重点检查：
  - same-model overfit
  - WFV fragility
  - data leakage
  - Alpha158 redundancy
  - concentration
  - turnover/cost/slippage
  - implementation complexity
  - live workflow risk
```

### 5.6 Risk Debate Prompt

Aggressive:

```text
站在愿意承担研究风险的角度，说明该实验为什么值得推进到下一验证阶段。
```

Conservative:

```text
站在保护研究预算和避免错误推广的角度，说明为什么应该拒绝、降级或先做更便宜测试。
```

Neutral:

```text
综合双方观点，提出最小可行验证路径。优先减少变量、减少成本、减少不可比风险。
```

### 5.7 Final Decision Prompt

```text
你是 Research Portfolio Manager。请综合：
  - analyst reports
  - bull/bear debate
  - experiment design
  - risk debate
  - past memory

在固定决策中选择一个：
  Promote
  CompareNext
  Hold
  Reject
  Retire

必须输出：
{
  "decision": "...",
  "executive_summary": "...",
  "approved_arms": [],
  "blocked_arms": [],
  "why": [],
  "validation_ladder": [],
  "promotion_criteria": [],
  "approval_required": [],
  "memory_update": [],
  "next_prompt_seed": "..."
}
```

## 6. Memory and Trace Design

### 6.1 RD-Agent Style Trace

保存到：

```text
docs/strategy_log/agent_runs/{run_id}/run.json
docs/strategy_log/agent_runs/{run_id}/plan.md
docs/strategy_log/agent_runs/{run_id}/role_traces.json
docs/strategy_log/agent_runs/{run_id}/role_traces.md
docs/strategy_log/agent_runs/{run_id}/commands.json
docs/strategy_log/agent_runs/{run_id}/feedback.md
```

trace 结构：

```json
{
  "run_id": "",
  "objective": "",
  "context_digest": "",
  "nodes": [
    {
      "node_id": "",
      "parent_node_ids": [],
      "type": "hypothesis | experiment | feedback | decision",
      "payload": {},
      "created_at": ""
    }
  ],
  "sota_reference": "",
  "last_decision": "",
  "do_not_repeat": []
}
```

### 6.2 TradingAgents Style Memory Log

保存为 append-only markdown：

```text
docs/strategy_log/agent_memory.md
```

entry:

```text
[2026-05-13 | agent_strategy | CompareNext | pending]

DECISION:
...

EXPERIMENTS:
...

<!-- ENTRY_END -->
```

当 WFV 或 backtest outcome 后，再追加：

```text
OUTCOME:
...

REFLECTION:
...
```

### 6.3 Reflection Prompt

借鉴 TradingAgents-ex 的 deferred reflection：

```text
现在结果已知，请用 2 到 4 句总结：
1. 当初的方向判断是否正确？
2. 哪个 hypothesis 成立或失败？
3. 下一次相似实验应避免或优先什么？
```

## 7. Execution Integration with quant_ex

Agent layer 只生成 plan，不直接运行昂贵命令。执行仍由现有脚本承担。

### 7.1 Cheap Validation

```bash
./.venv/bin/python -c "from web.api.app import app; print('OK')"
./.venv/bin/python run_train.py --list-registry
./.venv/bin/python -m pytest test/test_backtest_metrics.py test/test_grid_search.py
```

### 7.2 Same-model Backtest

由 ExperimentDesigner 生成：

```bash
./.venv/bin/python run_backtest.py \
  --model-path {model_path} \
  --topk {topk} \
  --n-drop {n_drop} \
  --hold-thresh {hold_thresh} \
  --output-csv {csv}
```

### 7.3 WFV

只有用户授权后：

```bash
./.venv/bin/python run_walk_forward_validation.py \
  --train-universes {universe} \
  --eval-market {market} \
  --topk ... --n-drop ... --hold-thresh ...
```

### 7.4 Promotion Logging

只有 durable candidate 才写：

```text
docs/strategy_log/strategy_iteration_log.csv
config/strategy_candidates.yaml
```

Agent planning 本身写：

```text
docs/strategy_log/agent_runs/
docs/strategy_log/agent_memory.md
```

## 8. Extension Strategy for Future RD-Agent / TradingAgents-ex Updates

### 8.1 Adapter Layer

保留 source project adapter：

```python
class SourceProjectAdapter:
    name: str
    version: str
    def extract_prompt_patterns() -> PromptPatternPack: ...
    def extract_role_topology() -> RoleTopology: ...
    def extract_schema_updates() -> SchemaPatch: ...
```

第一阶段不自动从外部项目 import，只做人工同步或脚本检查。

### 8.2 Prompt Pattern Registry

```yaml
prompt_patterns:
  rd_agent:
    hypothesis_trace: ...
    last_and_sota: ...
    feedback_json: ...
  tradingagents:
    analyst_report: ...
    bull_bear_debate: ...
    risk_triangle: ...
    structured_decision: ...
```

以后两个项目更新时，只需要更新 prompt pattern，而不是重写 orchestrator。

### 8.3 Role Plugin System

新增角色只需实现：

```python
RoleSpec:
  name
  input_keys
  output_schema
  prompt_template
  model_tier
  enabled
```

例如未来可加：

- NewsSentimentAnalyst
- AnnouncementAnalyst
- AlternativeDataScout
- FactorLeakageAuditor
- WFVStatistician
- ExecutionSimulator
- DashboardReporter

## 9. Implementation Phases

### Phase 0: Design Freeze

产出：

- 本设计报告。
- prompt templates 草案。
- schema 草案。

不做：

- 自动代码生成。
- 自动训练。
- 自动 WFV。

### Phase 1: Offline Agent Planner

能力：

- 读取本地 context pack。
- 无 LLM fallback 生成结构化 planning report。
- 可选 LLM 生成 role reports。
- 保存 JSON + Markdown。

验证：

```bash
./.venv/bin/python -m pytest test/test_agent_strategy_iteration.py
./.venv/bin/python run_agent_strategy_iteration.py --objective "..." --no-llm
```

### Phase 2: LLM Role Runner

能力：

- OpenAI-compatible client。
- quick/deep model tier。
- structured JSON parse + fallback。
- prompt cache 可选。

要求：

- API key 只读环境变量。
- 不写入文件。
- LLM 调用必须显式 `--use-llm`。

### Phase 3: Evaluation Feedback Loop

能力：

- 解析 backtest CSV/WFV summary。
- 生成 HypothesisFeedback。
- 更新 agent memory。

### Phase 4: Semi-automated Experiment Execution

能力：

- 只运行 cheap validation 和用户授权的命令。
- 接入 Web Dashboard task/SSE。

不做：

- 不自动真实通知。
- 不自动下单。
- 不绕过用户批准跑完整 WFV。

## 10. Key Design Decisions

### Decision 1: 不引入 LangGraph 作为第一阶段依赖

原因：

- 当前工作流是线性加少量 debate loop，小型 orchestrator 足够。
- 减少依赖复杂度。
- 保留未来 adapter 扩展。

### Decision 2: 不复制 RD-Agent 的 codegen workspace

原因：

- `quant_ex` 已有清晰模块。
- 自动代码生成在金融策略中风险更高。
- 第一阶段更需要高质量实验设计。

### Decision 3: Prompt 与 schema 先行

原因：

- 你的目标是吸收两个项目的精华，而不是跑通一个浅层流程。
- agent 质量主要来自 prompt、state、feedback、decision gate。

### Decision 4: Promotion 必须交给 quant_ex validation

原因：

- LLM 不能替代 WFV。
- 现有历史已经证明 same-model uplift 容易误导。

## 11. Immediate Next Step

建议下一步不是继续扩代码，而是先评审以下四个设计点：

1. 研究评级是否采用 `Promote / CompareNext / Hold / Reject / Retire`。
2. 第一批角色是否采用 `DataFactor / Model / Backtest / Execution / Bull / Bear / Risk3 / PM`。
3. agent memory 是否单独写 `agent_memory.md`，不直接污染 `strategy_iteration_log.csv`。
4. 是否允许 Phase 1 做 LLM role runner，还是先只做 offline planner 和 prompt templates。

确认后，再开始实现 Phase 1。
