# Strategy Iteration Log

本目录用于长期保存**策略配置迭代表格日志**，服务两个目标：

1. 方便人工按时间回看每一轮策略迭代、参数变化、模型来源和结果变化。
2. 方便代码代理或模型在下一轮做 ablation / overlay / 稳健性决策时，直接读取结构化历史，而不是只翻散落的 markdown 和 csv 产物。

## 主文件

- `strategy_iteration_log.csv`：主表，按 `iteration_date` 升序维护。
- `system_iteration_log.csv`：系统级迭代主表，记录全系统能力变化、基线范围、诊断评分和收敛状态。
- `agent_memory.md`：多角色 agent 策略迭代的追加式 memory，用于保留计划摘要和 delayed feedback。
- `agent_runs/`：agent run 的本地生成目录，包含 `run.json`、`plan.md`、`role_traces.*`、`commands.*`、`approval_template.yaml`、`feedback.*`、`attribution_report.*` 等。该目录默认 gitignored，不作为长期表格日志提交。
- `system_diagnostic_YYYY-MM-DD_*.md`：系统级诊断与阶段总结。Phase7 之后，若 agent 改动只改善研究流程而未产生新策略读数，应记录在这里，而不是写入 `strategy_iteration_log.csv`。

## 维护规则

- 每新增一个长期保留的策略配置，或对某个候选做出明确迭代结论，都应追加一行。
- 不记录一次性的临时调试参数；只记录“值得后续比较或复用”的策略版本。
- Agent planning 本身不等于策略结论。只有当训练/回测/WFV 结果改变长期决策面时，才追加 `strategy_iteration_log.csv`；否则保留在 `agent_memory.md`、`system_diagnostic_*.md` 和 run-local summary。
- Phase7 起，agent 的贡献先按“研究预算贡献”验证：是否减少无效 arms、是否避免重复失败路线、是否把下一次实验限定为一个可 kill 的 primary experiment；不能把 planner 改动直接记作策略收益。
- `config_path` 填相对路径；如果该策略没有独立配置文件，可填 `-`，并在 `notes` 中说明。
- `result_source` 填支撑该条记录的文件，如 `optimization_results/...csv`、`...md`、`config/strategy_candidates.yaml`。
- `next_ablation` 只写下一步最重要的一条，不要堆太多待办。

## 推荐字段解释

- `strategy_id`：稳定的策略标识，便于后续引用。
- `parent_strategy_id`：本次迭代基于哪个父策略演化而来。
- `iteration_date`：做出本轮结论的日期，而不是训练开始日期。
- `stage`：如 `baseline`、`overlay`、`candidate`、`retired`、`promoted`。
- `decision`：如 `keep`、`compare_next`、`fallback`、`do_not_promote`。
- `notes`：一句话总结本轮读数。
- `next_ablation`：下一轮最关键的对照实验方向。

## 使用建议

- 先读 `strategy_iteration_log.csv` 再决定跑哪些回测。
- 做新策略时，优先和 `decision=compare_next` 或 `decision=keep` 的条目比较。
- 若某条策略已经失效或被更优版本替代，不删除旧记录，只新增一条更新状态的记录。
- 对 agent run，优先读 `feedback.md` 和 `full_cycle_summary.md`；再决定是否需要把结果提升到 CSV 主表。

## Current Decision Index

本索引用于降低后续 agent / human review 的上下文噪音。它只描述当前决策状态，不替代原始回测、WFV、归因或审计报告。

### Promotable / daily-default eligible

- 当前没有新的 Phase 8 候选可自动进入 daily/default 配置。
- `config/strategy_candidates.yaml` 中的稳定基线仍是研究参考；任何 daily/default 替换都需要人工审查。

### Compare-next but blocked

- `gate_m008`：完整 WFV 平均 Sharpe 与 positive-fold 数较强，但 2022 fold Sharpe 仍为负且最大回撤约 `-29.15%`；状态是 `compare_next / not_promotable`。
- 下一步只允许 read-only 或 narrow replay 诊断，优先验证 portfolio risk-layer / risk-cap 是否改善 absolute drawdown survival。

### Diagnostic-only artifacts

- External Knowledge Scout：只提供 hypothesis input，不能作为 promotion evidence。
- Attribution input export：默认关闭；用于生成 portfolio returns / risk exposures / candidate events 的本地 artifact contract。
- Risk-cap diagnostics：默认关闭；`--export-risk-cap-diagnostics` 只随 attribution export 生成 counterfactual rows / summary，状态为 `diagnostic_only`。
- `phase8_gate_m008_2022_risk_cap_counterfactual_2026-05-21.md`：固定 `gate_m008` 信号路径的 2022 post-hoc risk-cap counterfactual；改善 drawdown/tail，但牺牲 upside capture，不能视为 replay 或 WFV 证据。

### Superseded / do-not-repeat

- 继续围绕 `gate_m008` 或 SVS threshold 做细粒度微调：当前视为高过拟合风险路线，不应作为下一轮主线。
- 仅凭同模型或单折读数推广策略：不满足项目 promotion 证据标准。

### Manual approval required

- 完整 WFV、市场数据刷新、daily/default 配置替换、launchd/定时任务修改、真实通知或任何 rebalance-like side effect。

## 近期 Agent 结论

### 2026-05-13 full-cycle validation

- `full_agent_train_backtest_20260513` 已验证 agent→训练→回测→feedback 完整通路。
- 严格主线为 csi1000 训练、csi300 评估、`topk=15/n_drop=3/hold_thresh=8`。
- 回测结果为 Sharpe `1.2490`、IR `0.5774`、MaxDD `-20.86%`，弱于 `fundamental_control_15_3_8_20260511`。
- Feedback decision 为 `reject/refuted`。该 run 是工作流验证，不是 durable strategy candidate，不应提升到 `strategy_iteration_log.csv`。
- 同一 run 中较早的 `full_agent_train_backtest_20260513_same_model.csv` 使用了 `config/daily_csi1000.yaml`，而该文件当前 `market.name` 实际为 `csi300`；它是 superseded diagnostic，不作为主结论。

### 2026-05-18 Phase7 attribution/budgeting

- `phase7_agent_attribution_smoke` 验证 agent run bundle 会生成 `attribution_report.json/md`。
- 当前 fallback attribution 来自 `config/strategy_candidates.yaml`：`adaptive_dd20_wf` 相对 `adaptive_baseline_wf` 的 mean Sharpe delta 为 `-0.0458`，worst drawdown delta 为 `+0.0437`，说明它是 stability base，不是 return upgrade。
- 下一轮核心研究应是围绕 `adaptive_dd20_wf` 的 narrow return repair，并保持 7/7 positive folds 与 drawdown 优势。
- Phase7 贡献必须用后续实验验证：如果它只是生成更漂亮的计划但没有减少无效实验或改善下一次实验选择，就不能算策略贡献。
