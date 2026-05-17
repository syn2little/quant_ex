# quant_ex

`quant_ex` 是一个基于 **qlib** 的 A 股低频量化选股研究框架，用于训练选股模型、做 walk-forward 验证、生成每日候选股和调仓动作，并沉淀可复用的研究配置。

项目定位偏向 **研究与辅助决策**，不是自动实盘交易系统。

当前核心能力：

- qlib数据集构建与模型训练
- LightGBM / XGBoost / Ridge / Lasso / MLP 多模型训练
- LightGBM bootstrap ensemble / bagging
- TopkDropout 策略回测、参数网格搜索、多 seed 稳健性评估
- Benchmark 超额收益指标（IR / alpha / tracking error）与默认 IR 排序
- 回测成交价口径配置（`backtest.deal_price`，支持 close/open 等 qlib 字段）
- Walk-forward 时间交叉验证，支持自定义折叠 YAML
- 因子流水线：technical / sector / mined / regime / northbound / fundamental / csv 自定义因子
- FactorScreener：基于 IC / ICIR / 相关性去重的因子筛选
- 信号后处理：rank / zscore、行业中性化、市值中性化
- 市场状态识别与策略参数切换（regime switch）
- 流动性过滤、停牌过滤、集中度风险检查
- 每日信号生成、目标持仓与买卖差分
- IC 衰减分析、滚动 IC 监控、Brinson 绩效归因
- qlib bin 数据更新与缺口补数
- Bark / PushPlus / 钉钉 / Server 酱 / 微信模板消息通知
- 东方财富行业与概念数据缓存
- Claude API 辅助参数优化
- Agent 策略迭代：多角色 LLM/离线 planner、prompt/context/trace 记录、命令审批模板、回测/WFV feedback 回灌
- Web Dashboard：本地可视化面板（数据管理、模型训练/浏览、回测、信号生成、因子分析、配置编辑、Agent Runs），中英文切换

> 本项目仅用于研究和辅助决策，不构成投资建议。

---

## 目录

- [环境说明](#环境说明)
- [快速开始](#快速开始)
- [数据更新](#数据更新)
- [训练模型](#训练模型)
- [回测与网格搜索](#回测与网格搜索)
- [Walk-forward 验证](#walk-forward-验证)
- [Agent 策略迭代](#agent-策略迭代)
- [每日信号与调仓](#每日信号与调仓)
- [定时任务](#定时任务)
- [因子与信号处理](#因子与信号处理)
- [Web Dashboard](#web-dashboard)
- [配置说明](#配置说明)
- [模块结构](#模块结构)
- [通知与外部依赖](#通知与外部依赖)
- [常见问题](#常见问题)

---

## 环境说明

### Python

- 目标 Python 版本：`>=3.9`
- 项目默认解释器：`./.venv/bin/python`（当前为 Python 3.11，已包含运行依赖如 akshare）
- 除非用户明确要求，不要切换到外部 Python 环境

### qlib 数据目录

默认配置在 `config/base.yaml`：

```yaml
qlib:
  provider_uri: "./qlib_data/qlib_bin"
  region: "cn"
```

如使用本机已有 qlib 数据，也可以改成绝对路径。

---

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 检查注册表

```bash
./.venv/bin/python run_train.py --list-registry
```

预期模型注册至少包含：

```text
lgbm, xgb, ridge, lasso, mlp
```

常用因子注册至少包含：

```text
technical, sector, mined, regime
```

### 3. 运行轻量测试

```bash
./.venv/bin/python -m pytest test/test_universe_filter.py test/test_trainer.py test/test_data_sources.py
```

---

## 外部数据获取

`run_fetch_data.py` 独立于 qlib 训练流水线，用于拉取 akshare 数据并缓存到 `cache/<type>/`。

```bash
# 按类型获取
./.venv/bin/python run_fetch_data.py --type financial       # A 股基本面（利润表/现金流）
./.venv/bin/python run_fetch_data.py --type northbound      # 北向资金
./.venv/bin/python run_fetch_data.py --type analyst         # 分析师评级与 EPS 预测
./.venv/bin/python run_fetch_data.py --type balance_sheet   # 资产负债表
./.venv/bin/python run_fetch_data.py --type dividend        # 分红历史
./.venv/bin/python run_fetch_data.py --type earnings_guidance  # 业绩预告
./.venv/bin/python run_fetch_data.py --type insider         # 高管增减持
./.venv/bin/python run_fetch_data.py --type institutional   # 机构持仓（基金/QFII/社保）
./.venv/bin/python run_fetch_data.py --type margin          # 融资融券
./.venv/bin/python run_fetch_data.py --type pledge          # 股权质押
./.venv/bin/python run_fetch_data.py --type repurchase      # 回购进度
./.venv/bin/python run_fetch_data.py --type shareholder     # 股东户数
./.venv/bin/python run_fetch_data.py --type valuation       # 估值（PE/PB/市值）
./.venv/bin/python run_fetch_data.py --type visit           # 机构调研
./.venv/bin/python run_fetch_data.py --type sw1_industry   # 申万一级行业
./.venv/bin/python run_fetch_data.py --type all             # 全量获取

# 限定范围
./.venv/bin/python run_fetch_data.py --type financial --universe csi300
./.venv/bin/python run_fetch_data.py --type financial --symbols SH600519,SZ000001

# 强制刷新（忽略 TTL 缓存）
./.venv/bin/python run_fetch_data.py --type analyst --force
```

各类型数据缓存 TTL：1 天（margin/pledge/insider/repurchase），3 天（analyst），7 天（financial/visit），30 天（balance_sheet/dividend/earnings_guidance/institutional/shareholder）。

---

## 数据更新

数据更新入口：

```bash
./.venv/bin/python run_update_qlib_data.py
```

该流程负责：Dolt clone/pull → SQL server → 导出 source CSV → normalize → dump 成 qlib bin。

常用参数：

```bash
./.venv/bin/python run_update_qlib_data.py --skip-dolt-pull
./.venv/bin/python run_update_qlib_data.py --reuse-dolt-server
./.venv/bin/python run_update_qlib_data.py --supplement-source akshare
./.venv/bin/python run_update_qlib_data.py --workspace-dir ./qlib_data --qlib-dir ./qlib_data/qlib_bin
```

说明：

- `data/qlib_update/` 是数据更新主逻辑目录
- `data/sources/` 中的 GapFiller 可用 akshare 或 eastmoney 补足缺失交易日
- `qlib_data/`、`backtest_results/`、`optimization_results/` 都是运行产物，默认不应提交

---

## 训练模型

### 自定义模型模式

```bash
./.venv/bin/python run_train.py --model lgbm --tag baseline
./.venv/bin/python run_train.py --model xgb --tag xgb_baseline
./.venv/bin/python run_train.py --model ridge --tag ridge_baseline
./.venv/bin/python run_train.py --model lasso --tag lasso_baseline
./.venv/bin/python run_train.py --model mlp --tag mlp_baseline
```

仅使用 Alpha158：

```bash
./.venv/bin/python run_train.py --model lgbm --no-extra-factors --tag alpha158_only
```

启用板块因子：

```bash
./.venv/bin/python run_train.py --model lgbm --with-sector --tag sector_full
```

### qlib-native 模式

```bash
./.venv/bin/python run_train.py --qlib-native
```

该模式训练完成后，会生成 MLflow Recorder。后续需要把 Recorder ID 写入 `config/base.yaml` 的 `experiment.latest_recorder_id`。

### Ensemble

在 `config/model.yaml` 中启用：

```yaml
model:
  ensemble:
    enabled: true
    seeds: [42, 123, 2024]
    bagging_fraction: 0.8
```

自定义模型会输出到 `models/*.pkl`，并附带 `_meta.json` 与 `_feature_importance.json` sidecar 文件。

---

## 回测与网格搜索

基础回测：

```bash
./.venv/bin/python run_backtest.py --model-path models/lgbm_xxx.pkl
```

参数网格搜索：

```bash
./.venv/bin/python run_backtest.py \
  --model-path models/lgbm_xxx.pkl \
  --market csi300 \
  --topk 5,15,20 \
  --n-drop 1,3 \
  --hold-thresh 5,8,10
```

多 seed 稳健性：

```bash
./.venv/bin/python run_backtest.py --model-path models/lgbm_xxx.pkl --seeds
```

输出独立 CSV：

```bash
./.venv/bin/python run_backtest.py --model-path models/lgbm_xxx.pkl --output-csv results/my_run.csv
```

Claude 参数优化：

```bash
export ANTHROPIC_API_KEY="..."
./.venv/bin/python run_backtest.py --optimize --n-iters 3
```

常见输出指标包括：`annual_return`、`sharpe`、`max_drawdown`、`calmar`、`win_rate`、`excess_annual_return`、`information_ratio`、`tracking_error`、`alpha`、`beta`、`ic`、`icir`、`rank_ic`、`rank_icir`。网格搜索默认按 `backtest.rank_metric: information_ratio` 排序；无 benchmark 指标时退回 Sharpe。

---

## Walk-forward 验证

完整时间交叉验证：

```bash
./.venv/bin/python run_walk_forward_validation.py \
  --train-universes csi300,csi800,csi1000 \
  --eval-market csi300 \
  --topk 5,15,20 \
  --n-drop 1,3 \
  --hold-thresh 5,8,10
```

并行运行：

```bash
./.venv/bin/python run_walk_forward_validation.py \
  --workers 3 \
  --grid-workers 1 \
  --train-universes csi300,csi800,csi1000
```

自定义折叠：

```bash
./.venv/bin/python run_walk_forward_validation.py --folds-config config/walk_forward_folds.yaml
```

自定义稳健得分权重：

```bash
./.venv/bin/python run_walk_forward_validation.py \
  --robust-weights '{"mean_sharpe": 1.0, "sharpe_std": -0.3, "min_sharpe": 0.5, "positive_sharpe_folds": 0.05}'
```

输出目录位于：

```text
optimization_results/walk_forward_<run_id>/
```

汇总表会包含 `sharpe_ttest_pvalue` 和 `return_ttest_pvalue`，用于衡量结果显著性。

长期结论建议整理到 `config/strategy_candidates.yaml`，不要只保留在运行产物中。

---

## Agent 策略迭代

`agent/strategy_iteration/` 提供一个轻量的研究 agent 层，吸收 RD-Agent 的 hypothesis/experiment/feedback trace 和 TradingAgents-ex 的多角色审议机制，但不直接绕过现有训练、回测、WFV 和审批链路。

核心产物：

- `docs/strategy_log/agent_runs/{run_id}/run.json`：完整 run bundle
- `plan.md`：多角色汇总计划
- `role_traces.json` / `role_traces.md`：每个 role 的 prompt、模型、上游角色、原始响应和结构化报告
- `discussion_trace.json` / `discussion_trace.md`：meeting 模式下虚拟主持人的角色调度、每轮参与角色、参与理由和收敛判断；默认 sequential 模式为空追踪。创建 run 时可限制最大轮数和每轮最多角色数。
- `commands.json` / `commands.md`：命令提案、风险标签和 command hash
- `approval_template.yaml`：受保护命令的审批模板
- `agent_tasks.json` / `agent_tasks.md`：可选 `--use-agent` 生成的本地 Codex/Claude 类 coding-agent 任务提案
- `agent_approval_template.yaml`：coding-agent 任务审批模板，按 `task_id` + `prompt_sha256` 锁定
- `feedback.json` / `feedback.md`：回测或 WFV CSV 回灌后的结果评价
- `docs/strategy_log/agent_memory.md`：跨 run 的追加式 agent memory

离线计划（默认不调用模型）：

```bash
./.venv/bin/python run_agent_strategy_iteration.py \
  --objective "比较 csi1000 baseline 与一个新的 postprocess ablation" \
  --run-id local_agent_plan \
  --no-llm \
  --propose-actions \
  --write-approval-template
```

真实 LLM 多角色计划：

```bash
./.venv/bin/python run_agent_strategy_iteration.py \
  --objective "基于当前候选提出下一轮可审批的策略迭代" \
  --run-id real_llm_agent_strategy_iteration \
  --use-llm \
  --propose-actions \
  --write-approval-template
```

回测/WFV 结果回灌：

```bash
./.venv/bin/python run_agent_strategy_iteration.py \
  --feedback-run-id real_llm_agent_strategy_iteration \
  --result-csv backtest_results/agent_runs/result.csv \
  --control-csv backtest_results/ablation/control.csv \
  --result-kind backtest \
  --rank-metric information_ratio
```

LLM 配置使用本地文件 `config/agent_strategy_iteration.yaml`，该文件被 gitignore 排除；提交样例为 `config/agent_strategy_iteration.example.yaml`。支持 quick/deep tier，例如 quick 使用轻量模型，deep 使用 reasoning 模型。不要把真实 API key 写入可提交文件。

2026-05-13 完整闭环验证：

- Run: `docs/strategy_log/agent_runs/full_agent_train_backtest_20260513/`
- 严格主线：`csi1000` 训练、`csi300` 评估、`topk=15/n_drop=3/hold_thresh=8`
- 结果：Sharpe `1.2490`，IR `0.5774`，MaxDD `-20.86%`
- Control: `backtest_results/ablation/fundamental_control_15_3_8_20260511.csv`
- Feedback decision: `reject / refuted`
- 结论：完整 agent→训练→回测→feedback 通路已跑通，但该 strict csi1000 重训候选不应推广；下一步应回到现有 baseline control 或设计更小、更正交的 ablation。

注意：`config/daily_csi1000.yaml` 是日常信号覆盖配置名，但当前文件中的 `market.name` 实际为 `csi300`，不要仅凭文件名判断训练股票池。需要 strict csi1000 训练时，应显式检查或创建 override，使 `market.name: "csi1000"`。

---

## 每日信号与调仓

### 每日信号

```bash
./.venv/bin/python run_daily.py --model-path models/lgbm_xxx.pkl --dry-run
```

使用策略覆盖配置：

```bash
./.venv/bin/python run_daily.py \
  --config config/daily_csi1000.yaml \
  --model-path models/lgbm_xxx.pkl \
  --dry-run
```

带账户规模和当前持仓：

```bash
./.venv/bin/python run_daily.py \
  --model-path models/lgbm_xxx.pkl \
  --account 500000 \
  --positions SH600000:500,SZ000001:300
```

### 调仓提醒与计划生成

```bash
# 测试格式
./.venv/bin/python run_scheduled_rebalance.py --mock --dry-run

# 实际运行（传入当前持仓，含建仓日期用于计算持股天数和 hold 保护）
./.venv/bin/python run_scheduled_rebalance.py \
  --config config/csi1000_balanced_overlay.yaml \
  --model-path models/lgbm_sector_csi1000_balanced_20260428_235851.pkl \
  --positions SH600489:900:2026-04-29,SH600900:900:2026-04-29 \
  --min-action-value 1000

# 不带建仓日期（兼容旧格式）
./.venv/bin/python run_scheduled_rebalance.py \
  --positions SH600489:900,SH600900:900
```

`--positions` 格式：`INSTRUMENT:SHARES` 或 `INSTRUMENT:SHARES:ENTRY_DATE`。传入建仓日期后，报告中每只股票会显示持股天数和个股收益，hold_thresh 保护也按逐股独立判断。

该脚本在收盘后执行：更新数据 → 重放回测 → 生成目标持仓和次交易日调仓动作 → 缓存结果 → 推送通知。

关键约束：

- `daily_rebalance.start_date` 必须早于今天至少几个交易日
- `TopkDropoutStrategy` 在回测首日不开仓，所以起点不能设成当天
- 首次跟踪策略时，应优先执行“次交易日调仓动作”中的买入项，而不是机械照搬“目标持仓摘要”

---

## 定时任务

安装 macOS launchd 任务（自动检测项目路径，无需手动修改）：

```bash
scripts/install_daily_rebalance_launchd.sh
```

默认注册三个任务：

| 任务 | 时间 | 功能 |
|---|---:|---|
| `com.quant_ex.daily_rebalance` | 20:00 | 更新数据、回测、缓存信号、推送调仓动作 |
| `com.quant_ex.daily_rebalance.open_reminder` | 09:00 | 开盘前提醒 |
| `com.quant_ex.daily_rebalance.close_reminder` | 14:00 | 收盘前提醒 |

---

## 因子与信号处理

### 因子配置

在 `config/model.yaml` 的 `model.features.factors` 中声明因子：

```yaml
model:
  features:
    factors:
      - name: technical
      - name: sector
        include_sector_momentum: true
        include_stock_vs_sector: true
        include_sector_reversal: true
        include_concept: true
      - name: mined
        path: "./cache/mined_factors.json"
      - name: regime
        windows: [20, 60]
        dd_window: 120
      - name: northbound        # 北向资金
      - name: fundamental       # 财务因子（利润表/现金流）
      - name: pledge            # 股权质押率
      - name: margin            # 融资融券（余额/增减）
      - name: insider           # 高管增减持（5/20/60d 滚动）
      - name: analyst           # 分析师评级与 EPS 增速
      - name: shareholder       # 股东户数变化
      - name: dividend          # 股息率、分红连续性
      - name: valuation         # PE/PB/市值
      - name: balance_sheet     # 杠杆率、流动比率
      - name: earnings_guidance # 业绩预告类型与惊喜度
      - name: institutional     # 机构持仓（基金/QFII/社保）
      - name: repurchase        # 回购完成率
      - name: visit             # 机构调研
      - name: csv               # CSV 自定义因子频次
```

`regime` 因子会产出：`regime_trend_{w}d`、`regime_vol_{w}d`、`regime_breadth_{w}d`、`regime_corr_{w}d`、`regime_drawdown`、`regime_label`。

上述 akshare 数据驱动因子需提前运行 `run_fetch_data.py` 填充缓存，否则因子返回空 DataFrame。

### FactorScreener

```yaml
model:
  features:
    screener:
      min_ic: 0.02
      min_icir: 0.3
      max_corr: 0.7
```

### 信号后处理

在 `config/base.yaml` 中配置：

```yaml
signal:
  postprocess:
    enabled: true
    daily_transform: "rank"
    rank_pct: true
    industry_neutralize: false
    size_neutralize: false
```

### Regime 策略切换

```yaml
strategy:
  regime_switch:
    enabled: true
    rules:
      0:
        topk: 15
        n_drop: 3
        hold_thresh: 5
      1:
        topk: 10
        n_drop: 1
        hold_thresh: 8
      2:
        topk: 12
        n_drop: 2
        hold_thresh: 5
      3:
        topk: 8
        n_drop: 1
        hold_thresh: 10
```

`run_daily.py` 和 `run_scheduled_rebalance.py` 都会尝试自动检测并应用该切换。

### 回测 benchmark 与成交价口径

```yaml
market:
  benchmark: "SH000300"

backtest:
  deal_price: "close"              # 兼容历史结果；正式候选建议额外用 open 复跑
  rank_metric: "information_ratio" # 无 IR 时自动退回 sharpe
```

`BacktestEngine` 会把 `market.benchmark` 传给 qlib，回测报告的 `bench` 列会自动进入 `compute_metrics()`，输出 IR、alpha、tracking error 等相对基准指标。

### 流动性过滤与集中度

```yaml
strategy:
  universe_filter:
    exclude_kcb: true
    exclude_st: true
    exclude_suspended: true
    min_price: 3
    min_avg_volume: 1000000
    avg_volume_window: 20
    min_avg_amount: 50000000
    avg_amount_window: 20
  portfolio:
    max_position_pct: 0.25
    concentration_hard_limit: 0.35
```

### 诊断与归因

IC 诊断：

```python
from quant_ex.backtest.signal_diagnostics import compute_ic_decay, compute_rolling_ic

decay = compute_ic_decay(pred, price_data)
monitor = compute_rolling_ic(pred, price_data, horizon=5, window=20)
```

Brinson 归因：

```python
from quant_ex.backtest.attribution import brinson_attribution, format_attribution

result = brinson_attribution(portfolio_weights, benchmark_weights, returns, sector_map)
print(format_attribution(result))
```

---

## Web Dashboard

基于 React 19 + FastAPI 的本地可视化面板，提供所有 quant_ex 功能的交互式访问，支持中英文切换。

### 启动

```bash
# 生产模式（单一进程，同时提供 API 和前端）
./.venv/bin/python web/run_web.py    # http://localhost:8000

# 开发模式（热重载）
# 终端 1：后端
./.venv/bin/python web/run_web.py

# 终端 2：前端
cd web/frontend
npm install    # 首次运行
npm run dev    # http://localhost:5173（自动代理 /api → :8000）
```

### 功能页面

| 页面 | 功能 |
|---|---|
| Dashboard | 系统状态总览、模型计数、缓存状态表、regime 状态 |
| Data Management | 数据获取（15 种类型）、缓存状态、股票查询 |
| Models | 模型训练表单、已保存模型浏览（含 meta + feature importance）、注册表 |
| Backtest | 网格搜索、Walk-forward 验证、结果浏览 |
| Signals | 信号生成、历史记录、调仓模拟、通知测试 |
| Factors | 因子库（19 个注册因子）、因子评估、因子挖掘 |
| Config | YAML 配置编辑器、策略候选、Regime 规则编辑 |
| Agent Runs | 创建/浏览 agent run、查看计划/trace/commands/feedback、生成审批模板 |
| System | 日志查看、缓存管理、运行时信息 |

### API

共 37 个 API 端点，分为 8 组路由：

- `/api/system/`：健康检查、运行时信息、日志、任务管理、SSE 流
- `/api/data/`：缓存状态、数据获取、股票查询
- `/api/models/`：模型列表/元数据/特征重要性、训练、注册表
- `/api/backtest/`：网格搜索、结果、Walk-forward、图表
- `/api/signals/`：信号生成、历史、regime、调仓、通知测试
- `/api/factors/`：因子列表、库、评估、挖掘
- `/api/config/`：YAML 读写、预设列表
- `/api/agents/`：agent run 列表、详情、创建、审批模板生成

---

## 配置说明

配置加载顺序：

```text
config/base.yaml → config/model.yaml → config/notify.yaml → --config 覆盖文件
```

常见配置职责：

- `config/base.yaml`：市场、benchmark、策略、回测成交口径、daily_rebalance、信号处理
- `config/model.yaml`：模型参数、额外因子、ensemble
- `config/notify.yaml`：通知渠道配置，建议从 `config/notify.yaml.example` 复制
- `config/agent_strategy_iteration.yaml`：本地 agent LLM 配置，gitignored；提交样例为 `config/agent_strategy_iteration.example.yaml`
- `config/strategy_candidates.yaml`：长期保留的研究结论，不会被自动加载
- `docs/strategy_log/strategy_iteration_log.csv`：策略级迭代历史（配置路径、参数、指标、结论），后续策略比较与 ablation 决策的首选入口
- `docs/strategy_log/system_iteration_log.csv`：系统级迭代历史（全系统变更、基线范围、前后最佳 Sharpe、诊断评分、收敛状态），通过 `strategy_iteration_ids` 与策略日志关联
- `config/walk_forward_folds.yaml.example`：自定义时间折模板

---

## 模块结构

```text
quant_ex/
├── config/                        # 策略与运行配置（base → model → notify → 覆盖文件，逐层合并）
│   ├── base.yaml                  #   市场、策略(topk/n_drop/hold)、回测、daily_rebalance、信号处理
│   ├── model.yaml                 #   模型参数、额外因子列表、ensemble、FactorScreener
│   ├── notify.yaml.example        #   通知渠道模板（Bark/PushPlus/钉钉/Server酱/微信）
│   └── csi1000_balanced_overlay.yaml  #   SVS overlay 策略配置（独立研究线）
│
├── data/                          # 数据层：加载、过滤、更新、外部数据获取
│   ├── loader.py                  #   DataLoader：qlib D.features 构建 dataset + price_data
│   ├── utils.py                   #   统一 code_to_qlib_instrument() + cached load_stock_names()
│   ├── sector.py                  #   SectorDataProvider：并发 akshare 行业/概念数据（7d 缓存）
│   ├── universe.py                #   UniverseFilter：流动性/ST/KCB/停牌/价格过滤
│   ├── fetchers/                  #   15 个 akshare 数据 fetcher（BaseDataFetcher 子类）
│   │   ├── financial_fetcher.py   #     利润表/现金流，TTL=7d
│   │   ├── northbound_fetcher.py  #     北向资金，TTL=1d
│   │   ├── analyst_fetcher.py     #     分析师评级/EPS，TTL=3d
│   │   ├── margin_fetcher.py      #     融资融券，TTL=1d
│   │   ├── pledge_fetcher.py      #     股权质押，TTL=1d
│   │   ├── insider_fetcher.py     #     高管增减持，TTL=1d
│   │   ├── valuation_fetcher.py   #     估值PE/PB/市值，TTL=1d
│   │   ├── balance_sheet_fetcher.py  #  资产负债表比率，TTL=30d
│   │   ├── dividend_fetcher.py    #     分红历史/股息率，TTL=30d
│   │   ├── earnings_guidance_fetcher.py  # 业绩预告/惊喜度，TTL=30d
│   │   ├── institutional_fetcher.py  #   机构持仓（基金/QFII/社保），TTL=30d
│   │   ├── repurchase_fetcher.py  #     回购计划与进度，TTL=1d
│   │   ├── shareholder_fetcher.py #     股东户数变化，TTL=30d
│   │   ├── visit_fetcher.py       #     机构调研统计，TTL=7d
│   │   └── sw1_industry_fetcher.py  #   申万一级行业成分，TTL=7d
│   ├── qlib_update/               #   Dolt → SQL → CSV → normalize → dump_bin 数据管道
│   │   └── normalize.py           #     NoopNormalize 修复 tradedate/date 列名错位
│   └── sources/                   #   GapFiller（akshare/eastmoney 补缺交易日）
│
├── features/                      # 因子层：20 个已注册因子，装饰器自动注册
│   ├── base.py                    #   BaseFactor + FactorPipeline（并行计算）+ FactorScreener
│   ├── technical_factors.py       #   Alpha158 + 扩展技术因子
│   ├── sector_factors.py          #   板块动量/相对强弱/反转/波动/概念（向量化 groupby）
│   ├── regime_features.py         #   市场状态因子：trend/vol/breadth/corr/drawdown/label
│   ├── fundamental_factor.py      #   财务因子：ROE/ROA/毛利率/营收增速/FCF 等
│   ├── northbound_factor.py       #   北向资金：持股比例/增减/集中度
│   ├── csv_factor.py              #   CSV 自定义因子（从文件加载）
│   ├── factor_mining.py           #   qlib 表达式挖掘 + MinedFactorLoader
│   ├── *_factor.py                #   其余10个数据驱动因子（pledge/margin/insider/analyst/
│   │                              #   shareholder/dividend/valuation/balance_sheet/
│   │                              #   earnings_guidance/institutional/repurchase/visit）
│   └── library/                   #   FactorMeta + FactorLibrary（目录）+ FactorCleaner
│
├── models/                        # 模型层：注册制 + 持久化 + 兼容补丁
│   ├── base.py                    #   BaseAlphaModel + ModelRegistry + load/save
│   ├── lgbm_model.py              #   LGBMAlphaModel（bootstrap bagging + ensemble）
│   ├── trainer.py                 #   ModelTrainer：自动 importlib 注册 + 特征重要性持久化
│   └── *.pkl                      #   训练产物（+ _meta.json + _feature_importance.json sidecar）
│
├── backtest/                      # 回测层：qlib 包装 + 指标 + 归因 + 诊断
│   ├── engine.py                  #   BacktestEngine → qlib backtest_daily + TopkDropoutStrategy
│   ├── metrics.py                 #   compute_metrics：绝对/超额/换手率/IR/tracking_error
│   ├── attribution.py             #   Brinson 板块归因（allocation/selection/interaction）
│   └── signal_diagnostics.py      #   IC 衰减分析 + 滚动 IC 监控
│
├── signals/                       # 信号层：生成 → 后处理 → 持仓 → 差分
│   ├── generator.py               #   SignalGenerator：预测 → 过滤 → topk → 目标持仓 → 报告
│   └── postprocess.py             #   rank/zscore + 行业中性化 + 市值中性化 + SVS过滤 + 回撤门控
│
├── strategy/                      # 策略层：regime 感知与参数切换
│   └── regime_switch.py           #   RegimeStrategySwitch：检测 regime → 调整 topk/n_drop/hold
│
├── notify/                        # 通知层：5 渠道推送
│   └── pusher.py                  #   NotificationPusher：Bark/PushPlus/钉钉/Server酱/微信
│
├── crawler/                       # 东方财富 SDK（独立于 qlib，直连无代理）
│   ├── eastmoney/                 #   API 封装
│   └── data/                      #   sector_codes.json + sector_stocks.json 缓存
│
├── web/                           # Web Dashboard：FastAPI + React
│   ├── api/                       #   后端
│   │   ├── app.py                 #     应用工厂 + CORS + 静态文件挂载 + sys.path 设置
│   │   ├── deps.py                #     共享依赖（配置加载、路径常量）
│   │   ├── routers/               #     8 个 API 路由（system/data/models/backtest/signals/factors/config/agents）
│   │   └── services/              #     TaskManager（后台任务 + SSE）、日志捕获流
│   ├── frontend/                  #   前端（Vite + TypeScript + Tailwind + react-i18next）
│   │   ├── src/pages/             #     9 个页面组件（含 Agent Runs）
│   │   ├── src/api/client.ts      #     Typed API 客户端
│   │   ├── src/hooks/useSSE.ts    #     SSE 流式推送 hook
│   │   ├── src/i18n/             #     国际化（en.json / zh.json）
│   │   └── src/components/        #     Sidebar、Layout、LanguageToggle、共享组件
│   └── run_web.py                 #   入口：uvicorn + 静态文件服务
│
├── agent/                         # AI 辅助与 agent 策略迭代
│   ├── auto_optimizer.py          #   Claude API 网格搜索参数优化
│   └── strategy_iteration/        #   多角色 agent planner、prompt、LLM client、feedback、approval gate
│
├── scripts/                       # 运维脚本
│   ├── install_daily_rebalance_launchd.sh  # 安装定时调仓（动态路径）
│   ├── run_ablation.sh            # 因子消融训练（4 变体）
│   ├── run_ablation_launcher.py   # Python 版消融启动器
│   ├── run_ablation_backtest.py   # 消融模型回测对比（自动发现最新模型）
│   └── run_overlay_csi1000_balanced_signal.sh  # 每日调仓信号（含 --positions）
│
├── command/                       # 快捷命令
│   ├── daily/                     #   日常信号脚本（csi1000_balanced_overlay 等）
│   ├── backtest/                  #   回测/网格搜索/WFV
│   ├── data/                      #   数据获取/更新
│   ├── train/                     #   模型训练
│   └── util/                      #   工具（测试/注册表/web 启动）
│
├── test/                          # pytest 测试套件（331 tests）
│
├── run_train.py                   # 模型训练入口
├── run_backtest.py                # 回测 + 网格搜索 + AI 优化入口
├── run_agent_strategy_iteration.py # 多角色 agent 策略迭代入口
├── run_walk_forward_validation.py # Walk-forward 时间交叉验证入口
├── run_daily.py                   # 每日信号生成入口
├── run_scheduled_rebalance.py     # 收盘后调仓信号入口（P&L + 持股天数 + hold 保护）
├── run_fetch_data.py              # 外部数据获取入口（15 种类型）
├── run_update_qlib_data.py        # qlib 数据管道入口
└── run_factor_mining.py           # 因子挖掘入口
```

---

## 通知与外部依赖

通知配置：

```bash
cp config/notify.yaml.example config/notify.yaml
./.venv/bin/python run_notify_test.py --channel bark
```

支持的通知渠道包括：Bark、PushPlus、DingTalk、Server 酱、微信公众号模板消息。

东方财富 SDK 位于 `crawler/eastmoney/`，独立于 qlib 主链路。直连可用，代理环境下可能出现空响应。

行业/概念数据抓取：

```bash
./.venv/bin/python crawler/scripts/fetch_sector_enums.py
./.venv/bin/python crawler/scripts/fetch_sector_stocks.py --resume
```

---

## 常见问题

**Q: qlib 数据路径找不到？**  
A: 检查 `config/base.yaml` 中的 `qlib.provider_uri`，目录下应包含 `calendars/`、`features/`、`instruments/`。

**Q: 数据更新时报 Dolt lock？**  
A: 先确认没有实际运行中的 `dolt sql-server`。如只是 stale lock，可直接重试；如已有 SQL server，则用 `--reuse-dolt-server`。

**Q: 并行回测报 semaphore 或资源竞争错误？**  
A: 降低 `--workers` / `--grid-workers`，或在 `config/model.yaml` 中下调 LightGBM 的 `num_threads`。

**Q: 为什么每日调仓没有目标持仓？**  
A: 通常是 `daily_rebalance.start_date` 设得太晚。回测首日不会开仓，起点应早于信号日几个交易日。

**Q: 为什么旧模型文件加载后报缺属性？**  
A: 旧 `pkl` 会依赖运行时兼容补丁。当前代码已通过 `__setstate__` 和默认值补齐大部分历史属性，但跨版本模型仍建议重新验证一次推理链路。

---

## License

MIT License. 本项目仅供学习和研究使用，不构成投资建议。市场有风险，投资需谨慎。
