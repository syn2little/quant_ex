# External Knowledge Scout Synthesis: 2026-05-19

## 本期结论
本报告是规则生成的保底深度解析草稿。它只提供研究假设，不构成策略晋升证据，也不允许直接生成实盘信号。

## 最值得投入的方向
### 1. Dynamic Elliptical Graph Factor Models via Riemannian Optimization with Geodesic Temporal Regularization
- 推荐动作：prototype
- 适配评分：5/5，证据评分：4/5，新颖度：4/5
- 核心机制：Potential factor/anomaly mechanism that may translate into feature engineering or candidate filters.
- quant_ex 映射：features/ or features/library/: candidate feature or factor diagnostic; backtest/ and strategy/: portfolio construction, regime, or risk overlay diagnostic
- 最小验证实验：先做离线诊断或小窗口 backtest，对照当前 baseline/control arm；只有通过 Phase7 attribution 和 experiment budget gate 才进入 WFV。
- 放弃条件：无法定义 rank metric/control arm、需要新增外部行情或基本面数据、或初筛恶化 drawdown/positive-fold 约束。

### 2. Deep Reinforcement Learning Framework for Diversified Portfolio Management Across Global Equity Markets
- 推荐动作：prototype
- 适配评分：5/5，证据评分：4/5，新颖度：4/5
- 核心机制：Risk-aware portfolio construction or drawdown control may improve stability before return repair.
- quant_ex 映射：models/: optional model architecture or training objective prototype; backtest/ and strategy/: portfolio construction, regime, or risk overlay diagnostic
- 最小验证实验：先做离线诊断或小窗口 backtest，对照当前 baseline/control arm；只有通过 Phase7 attribution 和 experiment budget gate 才进入 WFV。
- 放弃条件：无法定义 rank metric/control arm、需要新增外部行情或基本面数据、或初筛恶化 drawdown/positive-fold 约束。

### 3. Scale-Equivariant Generative Forecasting: Weight-Tied Dilated Convolutions, Wavelet Scattering Inputs, and Spectral-Consistency Training for Self-Similar Time Series
- 推荐动作：prototype
- 适配评分：5/5，证据评分：4/5，新颖度：4/5
- 核心机制：Potential factor/anomaly mechanism that may translate into feature engineering or candidate filters.
- quant_ex 映射：features/ or features/library/: candidate feature or factor diagnostic; models/: optional model architecture or training objective prototype
- 最小验证实验：先做离线诊断或小窗口 backtest，对照当前 baseline/control arm；只有通过 Phase7 attribution 和 experiment budget gate 才进入 WFV。
- 放弃条件：无法定义 rank metric/control arm、需要新增外部行情或基本面数据、或初筛恶化 drawdown/positive-fold 约束。

## 不建议做的方向
- 需要高频盘口、tick、未授权基本面或外部实时行情的数据型 idea。
- 只有模型复杂度、没有可比较 control arm 的深度模型 idea。
- 与 A 股低频选股/组合风控无关的泛机器学习论文。

## 下一轮 agent strategy iteration 建议
优先选择 1 个 low/medium cost prototype，加 1 个 cheap diagnostic；不要同时展开多个高成本模型方向。
