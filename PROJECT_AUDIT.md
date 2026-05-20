# quant_ex 项目审计报告（2026-05-20 更新版）

> 复核时间：2026-05-20
> 复核基线：当前工作区 `dashboard-console-base` 分支，HEAD `edf7d4ed fix daily rebalance initial position replay`，包含大量未提交 Phase 8 / knowledge scout / attribution / daily rebalance 改动
> 复核范围：`models/`、`features/`、`data/`、`backtest/`、`signals/`、`agent/strategy_iteration/`、`knowledge_scout/`、`run_*.py`、`config/`、`test/`、`web/`、`docs/strategy_log/`
> 复核验证：`run_train.py --list-registry`；Phase 8、knowledge scout、scheduled rebalance、signal postprocess 相关 78 个测试通过

---

## 目录

1. [复核摘要](#1-复核摘要)
2. [当前代码与研究状态](#2-当前代码与研究状态)
3. [已关闭或过时的旧结论](#3-已关闭或过时的旧结论)
4. [当前仍然成立的缺陷与风险](#4-当前仍然成立的缺陷与风险)
5. [新增 Phase 8 审计结论](#5-新增-phase-8-审计结论)
6. [优化机会（按收益/成本排序）](#6-优化机会按收益成本排序)
7. [能力盘点：已具备 / 部分具备 / 缺失](#7-能力盘点已具备--部分具备--缺失)
8. [与量化盈利目标的主要差距](#8-与量化盈利目标的主要差距)
9. [建议的下一轮工作顺序](#9-建议的下一轮工作顺序)
10. [验证记录](#10-验证记录)

---

## 1. 复核摘要

与 2026-05-13 版相比，本次复核的核心变化：

- **研究框架进入 Phase 8 诊断阶段**：重点从“生成新策略候选”转向“解释弱折、限制过拟合、补齐风险层证据”。
- **External Knowledge Scout 已落地为研究提示层**：`knowledge_scout/` 可抓取外部研究元数据、筛选、生成 brief/synthesis，并通过 `agent/strategy_iteration/context.py` 作为假设输入；它不应被视为市场数据源或直接交易信号。
- **Attribution input contract 已从设计走到导出链路**：`agent/strategy_iteration/attribution_input_export.py`、`run_backtest.py --export-attribution-inputs`、WFV 折叠 attribution export 测试已存在；默认关闭，符合安全边界。
- **Transient attribution 已完成首轮诊断**：同模型 attribution 显示 residual 均值略负、drawdown stress 下更弱、missed winners 较多，但这仍是诊断证据，不是信号放宽或 promotion 证据。
- **gate_m008 是 Phase 8 当前最强研究候选，但不可推广**：完整 WFV 中 `gate_m008` 平均 Sharpe `1.1248`、6/7 正 Sharpe、p-value `0.0079`，但 2022 fold Sharpe `-0.0424`、最大回撤 `-29.15%`，当前 promotion report 为 `compare_next / not_promotable`。
- **2022 弱折归因把问题从阈值微调转向组合风险层**：daily failure attribution 显示 stress residual 平均仍为正，但 absolute portfolio return 和 drawdown 很差；继续调 SVS/gate threshold 有过拟合风险，下一步应偏向 portfolio risk-cap 诊断。
- **Risk-cap 当前仍是纯函数/合成测试脚手架**：`agent/strategy_iteration/risk_cap.py` 已提供状态机、pre/post counterfactual、fold summary 字段，但未接入 backtest/WFV/exporter，也未推广任何配置。
- **Daily rebalance 初始持仓 replay 修复正在工作区内**：`run_scheduled_rebalance.py` 和 `test/test_scheduled_rebalance.py` 有未提交改动，相关测试通过；仍需注意真实推送/launchd/实盘语义操作要先 dry-run 或确认。
- **工作区很脏**：存在大量未提交和未跟踪文件，本审计只更新本文件，不清理、不回滚、不推广任何候选。

整体判断：项目已从“基础设施补齐”进入“研究证据治理 + 组合风险控制 + 实盘口径一致性”阶段。当前最大的收益不来自继续搜索更细阈值，而来自把已发现的弱折风险转成可复验、低前视、低过拟合的风险层实验。

---

## 2. 当前代码与研究状态

### 2.1 工作区状态

- 当前分支：`dashboard-console-base...origin/dashboard-console-base`。
- 当前 HEAD：`edf7d4ed fix daily rebalance initial position replay`。
- 当前存在大量未提交修改与未跟踪文件，集中在：
  - `agent/strategy_iteration/*`：attribution、risk cap、transient attribution、daily failure attribution。
  - `knowledge_scout/*`：外部研究 scout 模块。
  - `run_backtest.py`、`run_walk_forward_validation.py`、`run_agent_strategy_iteration.py`、`run_scheduled_rebalance.py`。
  - `config/phase8_*`、`config/csi1000_transient_repair_*`、`config/knowledge_scout.yaml`。
  - `docs/strategy_log/phase8_*` 与 `docs/strategy_log/knowledge_scout/`。
  - 多个 Phase 8 测试文件。

审计含义：当前报告反映的是“工作区真实状态”，不是干净提交状态。后续提交前应拆分为若干主题 commit，避免把诊断脚手架、研究报告、运行产物和 daily rebalance 修复混在一起。

### 2.2 规模与注册表

轻量统计（排除 `.git`、`.venv`、`logs`、`qlib_data`、`models`、`backtest_results`、`optimization_results`、`.codegraph`、signal cache 等运行产物）显示：

- 源码/文档/配置类文件约 `496` 个，约 `300,818` 行。
- 其中 `.py`：`219` 个，约 `46,938` 行。
- `.md`：`135` 个，约 `25,453` 行。
- `.tsx`：`39` 个，约 `10,193` 行。
- `.yaml`：`40` 个，约 `2,477` 行。
- `.json` 行数很高，主要受文档/配置/前端/缓存类 JSON 影响，不等同于核心代码规模。

`run_train.py --list-registry` 当前可注册：

- 模型：`lasso`、`lgbm`、`mlp`、`ridge`、`xgb`。
- 因子：`analyst`、`balance_sheet`、`csv`、`dividend`、`earnings_guidance`、`fundamental`、`insider`、`institutional`、`margin`、`mined`、`northbound`、`pledge`、`regime`、`repurchase`、`sector`、`shareholder`、`technical`、`valuation`、`visit`。

---

## 3. 已关闭或过时的旧结论

| 旧编号 | 当前状态 | 复核结论 |
|---|---|---|
| BUG-01 | 已修复 | 股票代码转换已统一到 `data/utils.py:code_to_qlib_instrument()`。 |
| BUG-02 | 已修复 | `features/technical_factors.py` 中 ATR 死代码已删除。 |
| BUG-03 | 已修复 | Walk-forward 已通过 `--output-csv` 写入折叠隔离路径。 |
| BUG-05 | 已修复 | `features/sector_factors.py:_map_sector_stat()` 已改为向量化 `groupby + reindex`。 |
| BUG-06 | 已修复 | `sector_reversal` 已改为短窗动量减长窗动量。 |
| BUG-07 | 已修复 | `signals/generator.py` 用 `$volume` 识别停牌股票并跳过。 |
| BUG-10 | 误报 | `_merge_extra()` 存在于 `models/base.py`，调用链成立。 |
| BUG-A01 | 已修复 | benchmark 已从配置传入 qlib 回测报告，指标与排序默认使用 IR。 |
| BUG-A06 | 已修复 | `run_scheduled_rebalance.py` 已改用 `data.utils.load_stock_names()`。 |
| OPT-03 | 已完成 | CSV 输出路径隔离已实现。 |
| OPT-05 | 已完成 | Top-N 特征重要性写入 `models/*_feature_importance.json`。 |
| OPT-06 | 已完成 | `LGBMAlphaModel` 支持 `bagging_fraction` bootstrap bagging。 |
| OPT-08 | 已完成 | `--folds-config` + `config/walk_forward_folds.yaml.example`。 |
| OPT-A01 | 已完成 | qlib report `bench` → `compute_metrics()` → grid CSV → `information_ratio` 默认排序。 |
| OPT-A03 | 已完成 | `run_scheduled_rebalance.py` 已复用共享股票名称加载逻辑。 |
| OPT-A05 | 已完成 | `SectorDataProvider._fetch_akshare()` 已使用并发抓取。 |
| CAP-03 | 已完成 | `backtest/signal_diagnostics.py` 已有 `compute_ic_decay()`。 |
| CAP-05 | 部分完成 | `avg_turnover`、`--slippage-sensitivity` 已有，但仍未系统纳入候选准入门槛。 |
| CAP-06 | 已完成 | `features/regime_features.py` + `strategy/regime_switch.py` 已完整落地。 |
| CAP-08 | 部分完成 | Brinson 板块归因已有；Phase 8 已补 attribution input / transient / daily failure 诊断，但还不是稳定产品化归因闭环。 |
| CAP-09 | 部分完成 | `compute_rolling_ic()` 已有，自动告警、持久化、阈值治理未接通。 |
| GAP-04 | 部分缓解 | WFV 汇总含 t-test p-value，但折叠数量偏少，且 Phase 8 已暴露弱折对 promotion 的决定性影响。 |
| GAP-08 | 部分缓解 | `size_neutralize` 已有，未默认启用。 |

---

## 4. 当前仍然成立的缺陷与风险

### BUG-A02 🟡 回测成交假设已可配置，但默认仍保持 `deal_price="close"`

**位置：** `backtest/engine.py`、`run_backtest.py`、`backtest/grid_search.py`

**现状：** `backtest.deal_price` 已接入 `SimulatorExecutor`，可通过配置或 CLI 切换到 `open` 等 qlib 支持字段；为了兼容历史结果，默认值仍是 `close`。

**影响：** 如果正式研究仍沿用默认 `close`，回测与次日调仓执行之间仍存在乐观偏差。Phase 8 的策略比较若混用 close/open 口径，会污染 promotion 判断。

**建议：**
1. 正式候选必须同时记录 `deal_price`、成本、滑点、benchmark、rank metric。
2. 对接近日常使用的候选建立 `open` 或更保守口径复跑模板。
3. promotion report 必须拒绝成交价/成本/benchmark 口径不一致的对照。

---

### BUG-A03 🔴 历史板块/ST/名称过滤仍存在前视偏差与幸存者偏差风险

**位置：** `data/utils.py`、`data/sector.py`、`data/universe.py`

**现状：** 股票名称和部分行业映射仍依赖当前 `crawler/data/sector_stocks.json` 与 `cache/stock_name_map.json` 一类快照；`data/sector.py` 明确有 akshare 实时、crawler 离线、local cache fallback。

**影响：** 历史回测可能使用“今天知道的 ST 名称/板块归属/证券状态”，这会隐性抬高研究可信度，尤其影响小盘股和历史行业轮动结论。

**建议：**
1. 为行业归属、ST 状态、上市/退市状态引入按日期索引的历史快照。
2. 在 WFV 与 backtest metadata 中显式记录行业/名称数据版本和是否时间一致。
3. 在历史快照补齐前，所有行业/ST 相关结论都应标记为“可能含当前快照偏差”。

---

### BUG-A04 ⚠️ `factor_mining.py` 失败时仍偏静默

**位置：** `features/factor_mining.py:_compute()`

**现状：** 表达式失败更多依赖 debug/log 观察，没有形成标准研究报告字段。

**影响：** 自动挖因子时可能把“大量表达式失败后剩下的少数结果”误认为稳健 alpha。

**建议：** 将失败表达式计数、失败率、样本规模、缺失率、fallback 次数写入最终摘要，并纳入候选准入门槛。

---

### BUG-A05 ⚠️ `min_price` 过滤跨时间步 fallback 增加理解成本

**位置：** `data/universe.py`

**现状：** 当前口径可能在不同交易日之间 fallback，行为不够显式。

**影响：** 历史 universe membership 与实际可交易性可能不完全一致。

**建议：** 明确过滤口径，优先逐交易日局部对齐，增加专门单测覆盖缺价、停牌、上市初期等场景。

---

### BUG-A07 ⚠️ 回测侧仍缺真正的持仓/组合风险硬约束执行

**位置：** `backtest/engine.py`、`signals/postprocess.py`、`agent/strategy_iteration/risk_cap.py`

**现状：** 信号侧已有集中度检查与 size neutralization；Phase 8 新增 risk-cap 纯函数脚手架，但尚未接入 backtest/WFV，也没有真正执行组合层硬约束。

**影响：** 研究端可能选出“指标最优但不可执行/不可承受回撤”的参数。Phase 8 `gate_m008` 的 2022 弱折已经说明：alpha/residual 不是唯一问题，absolute risk survival 是关键 blocker。

**建议：** 先保持 `risk_cap.py` 诊断属性，下一步只做 toy exporter 或窄范围 same-model replay；在没有 holdout/WFV 证据前，不要接入 daily/default config。

---

### BUG-A08 🟡 Agent memory / docs 可能积累重复结论

**位置：** `docs/strategy_log/agent_memory.md`、`docs/strategy_log/phase8_*`

**现状：** `agent_memory.md` 中可见多段相似 DECISION 文本；Phase 8 文档数量快速增长。

**影响：** Agent context 可能被重复结论稀释，后续 planner 更容易“看见很多文档”但抓不住当前有效边界。

**建议：** 给 `docs/strategy_log/README.md` 或 agent context 增加“当前有效结论索引”，区分 latest decision、superseded decision、diagnostic-only artifact。

---

## 5. 新增 Phase 8 审计结论

### 5.1 Knowledge Scout：已可用，但只能作为假设输入

**位置：** `knowledge_scout/`、`run_knowledge_scout.py`、`config/knowledge_scout.yaml`、`docs/external_knowledge_scout_design_2026-05-18.md`

**结论：** 模块边界设计正确：抓取外部研究思想、筛选和生成 guidance docs，但不摄取市场/基本面时间序列，不产生直接交易信号。

**风险：** 如果 future agent 把 scout 输出当作 promotion evidence，会绕过本项目最重要的 backtest/WFV/holdout 证据链。

**建议：** 在 agent context 中继续强制标注 `external_knowledge_scout = hypothesis only`，并在 promotion report 中禁止引用 scout 作为直接推广证据。

---

### 5.2 Attribution input export：基础打通，默认关闭是正确边界

**位置：** `agent/strategy_iteration/attribution_input_export.py`、`run_backtest.py --export-attribution-inputs`、`run_walk_forward_validation.py`、`test/test_*attribution*`

**结论：** 当前 exporter 可生成：

- `portfolio_returns`：`date`、`portfolio_return`、`benchmark_return`、可选 `cost`、`excess_return`。
- `risk_exposures`：`residual_return`、`drawdown`、`abs_residual_return`。
- `candidate_events`：accepted/rejected、score、rank、forward_return。

**风险：** 当前 risk exposure 只是 residual/drawdown 最小合同，不是 Barra/行业/风格风险模型。若报告中称为完整风险模型，会过度解释。

**建议：** 继续保持 disabled-by-default；真实 backtest/WFV 导出应带 run_id、config snapshot、deal_price/cost/benchmark metadata。

---

### 5.3 Transient attribution：能解释失败模式，但不能直接改信号

**位置：** `agent/strategy_iteration/transient_attribution.py`、`run_transient_attribution.py`、`docs/strategy_log/phase8_risk_transient_factor_attribution_v0_conclusion_2026-05-19.md`

**关键读数：**

- days：`572`。
- mean portfolio return：`0.000658`。
- mean benchmark return：`0.000684`。
- mean residual return：`-0.000026`。
- hit rate：`0.465035`。
- worst drawdown：`-0.219993`。
- drawdown stress mean residual return：`-0.000509`。
- missed winner count：`69,682`；accepted loser count：`4,115`。

**结论：** 诊断指出 drawdown stress 下 residual 更弱、missed winners 较多，但并不能推出“放宽阈值”就是正确策略。它更适合作为下一轮实验设计输入。

---

### 5.4 gate_m008：当前最强 Phase 8 候选，但不满足推广门槛

**位置：** `docs/strategy_log/phase8_regime_gate_grid_full_wfv_conclusion_2026-05-19.md`、`config/csi1000_transient_repair_regime_gated_svs_m008.yaml`

**完整 WFV 读数：**

| arm | threshold | mean annual | mean Sharpe | min Sharpe | worst DD | positive Sharpe folds | rank ICIR | Sharpe p | robust score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| soft_no_gate | none | 14.60% | 0.6066 | -0.8828 | -22.54% | 5/7 | 0.3308 | 0.1395 | 0.2437 |
| gate_m005 | -0.05 | 21.72% | 0.8848 | -0.4998 | -32.93% | 5/7 | 0.3642 | 0.0417 | 0.6151 |
| gate_m008 | -0.08 | 25.40% | 1.1248 | -0.0424 | -29.15% | 6/7 | 0.3547 | 0.0079 | 1.0636 |
| gate_m012 | -0.12 | 20.54% | 0.8463 | -0.5370 | -33.46% | 5/7 | 0.3470 | 0.0431 | 0.5836 |

**结论：** `gate_m008` 是当前最值得继续诊断的候选，但 `wfv_min_sharpe` 仍为负，2022 最大回撤仍不可接受，不能替换 daily/default 策略。

---

### 5.5 2022 daily failure attribution：问题更像组合风险生存问题

**位置：** `agent/strategy_iteration/daily_failure_attribution.py`、`run_daily_failure_attribution.py`、`docs/strategy_log/phase8_gate_m008_2022_daily_failure_attribution_conclusion_2026-05-19.md`

**关键读数：**

- days：`242`。
- mean portfolio return：`0.000145`。
- mean benchmark return：`-0.000924`。
- mean residual return：`0.001070`。
- worst drawdown：`-29.15%`。
- worst daily portfolio return：`-6.81%`。
- stress days：`196`；stress mean portfolio return：`-0.000452`；stress mean residual return：`0.000404`。
- rejected events 平均 forward return 为负，说明简单放宽 selection threshold 不是干净修复。

**结论：** 2022 blocker 不主要是 alpha/ranking 失败，而是 absolute risk survival 问题。继续 threshold micro-tuning 很容易过拟合弱折。

---

### 5.6 Risk-cap：纯函数脚手架健康，但尚未进入策略验证

**位置：** `agent/strategy_iteration/risk_cap.py`、`test/test_phase8_risk_cap.py`、`docs/strategy_log/phase8_risk_cap_diagnostic_inputs_2026-05-19.md`

**已具备：**

- `RiskCapPolicy` 与 `inactive/watch/cut/recover/blocked` 状态机。
- `compute_drawdown()`、`compute_rolling_vol()`、`compute_cap_state()`。
- `apply_cap_multiplier()`、`compute_pre_post_counterfactual_returns()`、`compute_turnover_delta()`。
- `compute_risk_cap_counterfactual_series()`。
- `summarize_risk_cap_counterfactual()`，包含 return/drawdown/vol/IR/turnover/tail/capture 等 report-only 字段。

**边界：** 当前仍是 pure/synthetic diagnostic scaffolding：未接 backtest，未接 WFV，未导出真实 fold artifact，未修改 daily config，未 promotion。

**建议：** 下一步若继续，应先做 toy artifact exporter 或使用已有 attribution artifacts 做 narrow same-model replay；不要直接全量 WFV 或 daily 接入。

---

## 6. 优化机会（按收益/成本排序）

### OPT-B01 高收益中成本：建立“实盘口径候选准入模板”

将以下字段作为所有候选 report 的必填 metadata：`benchmark`、`rank_metric`、`deal_price`、`open_cost`、`close_cost`、`min_cost`、slippage、market、train_universe、eval_market、topk、n_drop、hold_thresh、SVS/risk overlay 参数、数据版本。

收益：防止 close/open、成本、benchmark、rank_metric 混用，直接提升研究结论可信度。

---

### OPT-B02 高收益中成本：把 risk-cap 从纯函数推进到 toy exporter / narrow replay

当前风险层方向比阈值微调更符合证据。建议顺序：

1. toy artifact exporter：只生成 5-10 日合成 daily state / holdings / trade detail / fold summary。
2. 使用已有 attribution artifacts 做 `gate_m008` narrow same-model replay。
3. 只有当 replay 证明确实改善 2022 tail 且不明显牺牲正常年份，再设计 holdout 或 WFV。

---

### OPT-B03 高收益高成本：补历史快照式行业/ST/证券状态

这是当前最影响历史回测可信度的数据层缺口。已有 SW1/行业 fetcher，但缺“按日期有效”的历史状态表和回测时点一致读取。

---

### OPT-B04 中收益中成本：建立 strategy_log 的 current-decision index

新增或强化 `docs/strategy_log/README.md`：

- 当前可推广策略。
- 当前 near-promotable 但 blocked 策略。
- 当前 diagnostic-only artifacts。
- 已 superseded 的结论。
- 需要人工确认的下一步。

收益：降低 agent context 噪音，减少重复探索。

---

### OPT-B05 中收益中成本：失败可观测性进入标准报告

将以下指标标准化：表达式失败率、因子缺失率、候选过滤原因分布、数据源 fallback 次数、缓存命中率、attribution artifact 覆盖率、回测导出合同状态。

---

### OPT-B06 中收益中成本：FactorPipeline 可控并行

前提：确认各因子 `compute()` 无共享可变状态，且 qlib 数据读取不会引入隐性全局状态冲突。该项仍不是当前最高优先级。

---

## 7. 能力盘点：已具备 / 部分具备 / 缺失

### 7.1 已具备

- 多模型注册：LGBM / XGB / Ridge / Lasso / MLP。
- 多因子注册：technical / sector / mined / regime / northbound / fundamental / csv / analyst / balance_sheet / dividend / earnings_guidance / insider / institutional / margin / pledge / repurchase / shareholder / valuation / visit。
- 因子 IC 衰减分析：`compute_ic_decay()`。
- 滚动 IC 监控基础函数：`compute_rolling_ic()`。
- Brinson 板块归因：`backtest/attribution.py`。
- 市值中性化：`signals/postprocess.py` 的 `size_neutralize`。
- 市场状态切换：`strategy/regime_switch.py`，已接入 `run_daily.py` 与 `run_scheduled_rebalance.py`。
- Walk-forward 自定义折叠：`--folds-config`。
- 统计显著性：`sharpe_ttest_pvalue` / `return_ttest_pvalue`。
- 换手率与滑点敏感性：`avg_turnover`、`--slippage-sensitivity`。
- 基础与扩展外部数据 fetcher：financial、northbound、analyst、balance_sheet、dividend、earnings_guidance、insider、institutional、margin、pledge、repurchase、shareholder、valuation、visit、sw1_industry。
- FactorScreener：基于 IC / ICIR / 相关性去重的因子筛选。
- Web Dashboard：React + FastAPI，本地管理面板、任务与 SSE 能力。
- Benchmark 超额收益主链路：回测报告默认带 `bench`，指标输出 IR/alpha/tracking error，网格搜索默认按 IR 排序。
- 回测成交价配置：`backtest.deal_price` 可控制 qlib 成交价字段。
- Agent 策略迭代：多角色 planner、prompt/context/trace、命令审批模板、feedback 回灌、append-only memory。
- Knowledge Scout：外部研究 hypothesis input 层。
- Attribution input export：portfolio returns / residual risk exposures / candidate events 的最小合同导出。
- Transient attribution / daily failure attribution：Phase 8 诊断工具。
- Risk-cap pure helper：状态机、counterfactual series、fold summary 合成测试脚手架。

### 7.2 部分具备

#### CAP-B02 基本面因子库

已有估值类和扩展财务因子，仍缺更完整的质量/成长因子框架、财报滞后处理和财报发布日期时点一致性。

#### CAP-B03 归因分析

板块级 Brinson 已有，Phase 8 已补 residual/candidate/daily failure attribution；但尚未形成按月稳定输出、可审计、可产品化的多层归因报告。

#### CAP-B04 模型退化监控

已有滚动 IC 计算函数，定时任务、阈值治理、告警通知未接通。

#### CAP-B05 风险控制

信号侧已有集中度检查，Phase 8 risk-cap 有纯函数脚手架；但回测/执行侧未形成统一硬约束。

#### CAP-B06 自动研究闭环

Agent 可以提出计划、写审批模板、吸收 feedback；但 promotion 仍需要人工审查，且当前 Phase 8 证明 agent/scout 不能替代 WFV/holdout 证据。

### 7.3 仍然缺失或明显不足

#### CAP-C01 历史快照式行业/ST/证券状态数据

当前最影响研究可信度的数据层能力缺口。

#### CAP-C02 多标签或多持有期训练框架

主标签仍偏向单一持有期。已有 IC 衰减分析能力，但还没落实到训练与选参制度里。

#### CAP-C03 实盘口径统一模板

“研究回测”“日常信号”“定时调仓提醒”三条链路在价格口径、风险约束、执行口径上仍不完全统一。

#### CAP-C04 压力测试与极端成交情景模拟

缺跌停无法卖出、开盘跳空、流动性骤降、连续停牌、极端小盘流动性塌缩等情景压力测试。

#### CAP-C05 组合风险层验证

Risk-cap 目前只有纯函数/合成数据；缺真实 backtest artifact replay、holdout、WFV 证据。

#### CAP-C06 统一研究可观测性与失败审计

表达式失败率、因子缺失率、数据源 fallback 次数、缓存命中率、导出合同状态等尚未成为所有报告的标准字段。

---

## 8. 与量化盈利目标的主要差距

### GAP-B01 🔴 研究结果仍可能高估真实 Alpha

benchmark 链路已接通；剩余主要风险是默认 `deal_price="close"` 偏理想化，以及历史行业/ST/证券状态仍使用当前快照或非时点一致数据。

### GAP-B02 🔴 回测风险约束与实盘约束仍未统一

`gate_m008` 的 2022 弱折说明：即使 residual/alpha 相对 benchmark 不差，absolute drawdown 仍可能让策略不可承受。组合风险层必须成为 promotion 的硬门槛。

### GAP-B03 🟡 Phase 8 候选接近但仍不可推广

`gate_m008` 是明显进步，但仍被 2022 fold 和最大回撤拦住。继续微调阈值的边际收益低、过拟合风险高。

### GAP-B04 🟡 持有期与标签期协同还没形成闭环

已有 IC 衰减分析和 candidate event attribution，但还没系统反哺训练标签、持有期、topk/n_drop/hold_thresh 的联合设计。

### GAP-B05 🟡 基本面与非价格 Alpha 仍不够厚

外部数据 fetcher 丰富，但财报滞后、质量/成长、稳定性筛选、跨年份鲁棒性仍需要更严格证据。

### GAP-B06 🟡 自动化研究闭环还不够强

网格搜索、WFV、显著性检验、IC 衰减、滑点敏感性、attribution、risk-cap 诊断尚未汇总为统一“研究准入门槛”。

---

## 9. 建议的下一轮工作顺序

1. **冻结 Phase 8 阈值微调**：保留 `gate_m008` 为 near-promotable reference，但不要继续围绕 -0.08 做更细阈值搜索。
2. **补 risk-cap toy exporter**：先生成合成 daily state / holdings / trade detail / fold summary，验证合同与状态机，不接真实策略。
3. **做 narrow same-model risk-cap replay**：只用已有 attribution/backtest artifacts 评估 `gate_m008` 的 2022 tail 是否改善；输出必须标记 `diagnostic_only`。
4. **建立实盘口径 metadata 模板**：所有 backtest/WFV/promotion report 必填 `deal_price`、成本、benchmark、rank_metric、数据版本。
5. **整理 strategy_log current-decision index**：明确 `gate_m008`、risk-cap、transient attribution、knowledge scout 的当前状态和边界。
6. **补历史快照数据设计**：先从行业/ST/上市状态最小合同开始，不急于大规模重跑。
7. **再考虑 holdout/WFV**：只有当 risk-cap replay 有清晰改善且不牺牲正常年份，再请求人工批准更广验证。

---

## 10. 验证记录

本次审计实际执行：

```bash
git status --short --branch
git rev-parse --show-toplevel
git log -1 --oneline
./.venv/bin/python run_train.py --list-registry
./.venv/bin/python -m pytest \
  test/test_knowledge_scout.py \
  test/test_phase8_attribution_input_contract.py \
  test/test_phase8_attribution_input_export.py \
  test/test_phase8_daily_failure_attribution.py \
  test/test_phase8_risk_cap.py \
  test/test_phase8_transient_attribution.py \
  test/test_run_backtest_attribution_export.py \
  test/test_walk_forward_attribution_export.py \
  test/test_scheduled_rebalance.py \
  test/test_signal_postprocess.py
```

结果：

- `run_train.py --list-registry` 正常输出 5 个模型与 19 个因子注册项。
- Pytest 收集 `78` 个测试，结果 `78 passed in 2.58s`。
- 本次未运行 full WFV、未刷新市场数据、未执行 rebalance、未发送通知、未推广任何策略配置。

---

## 结论

截至 2026-05-20，`quant_ex` 的核心短板已经不是“没有工具”，而是“如何防止工具链把诊断结果误用为推广证据”。Phase 8 的主线很清楚：`gate_m008` 值得继续研究，但弱折显示问题更偏组合风险层，而不是继续信号阈值微调。

下一轮最稳妥的方向是：用严格 metadata 和 artifact contract 固化研究口径，用 risk-cap 的 toy/replay 诊断验证 absolute risk survival 是否能改善，再决定是否值得人工批准更大范围验证。

*本报告为当前工作区审计更新版。后续如果 risk-cap 从纯函数进入真实 replay、或历史快照数据补齐，应继续更新本文件。*
