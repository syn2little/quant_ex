**1. 本期结论**

本期 Knowledge Scout 的有效信息集中在三个可落地主题：风险模型的短暂统计因子、离散潜变量的截面排序建模、以及“被拒绝交易事件”的归因与学习。它们对 quant_ex 的价值不在于直接产生新 alpha，而在于改善 Phase7 attribution 中对收益来源、风险暴露、失败样本和模型状态漂移的解释能力。

优先级判断如下：

- 第一优先级：Transient Statistical Factors。最适合 quant_ex 现阶段，因为它可以作为风险模型增强层，直接服务于 attribution、组合风险解释和实验晋级 gate。
- 第二优先级：Vector-Quantized Discrete Latent Factors。适合作为模型诊断与特征压缩实验，不建议一开始做完整深度架构，应先验证离散状态是否提升截面排序稳定性。
- 第三优先级：Rejected Trading Events / Abstention Attribution。论文数据集本身不应引入，但“被策略过滤掉的候选交易”这一思想很适合 quant_ex，用于分析 missed winners、avoided losers 和过滤器边际贡献。
- 暂不建议投入：Treasury Markov-switching 和 Kyle lambda noise order-flow。前者资产域和数据结构错位，后者更偏微观结构理论，当前不具备最小闭环收益。
- 所有方向都必须经过 experiment budget gate：只允许小预算、强对照、可解释、可 kill 的验证；不得因为论文新颖而扩大搜索空间。

---

**2. 最值得投入的 3 个方向**

1. 风险模型中加入短暂统计因子
   对应论文：Enhancing a Risk Model by Adding Transient Statistical Factors
   研究定位：风险归因增强，不是 alpha 发现。

2. 离散潜变量辅助截面排序
   对应论文：Vector-Quantized Discrete Latent Factors Meet Financial Priors
   研究定位：模型状态压缩、截面排序稳定性诊断，不应直接替代现有排序模型。

3. 被拒绝交易事件的结果归因
   对应论文：RED-2400: A Public Benchmark of Algorithmically-Rejected Trading Events with Outcome Labels
   研究定位：策略过滤器、风控 gate、信号冲突规则的边际贡献评估。

---

**3. 每个方向的机制解释、适配性、最小验证实验、风险和放弃条件**

**方向一：风险模型中加入短暂统计因子**

机制解释：

传统风险模型通常假设一组较稳定的风险维度，例如市场、行业、风格、规模、流动性、波动等。但策略真实亏损常常来自短周期、非稳定、难以命名的共同冲击：例如近期反转拥挤、因子拥挤解除、局部流动性恶化、异常相关性上升、某类持仓短期同步失效。

“Transient Statistical Factors”的核心价值是：不要求因子长期稳定存在，而是承认某些风险因子只在短窗口内有效。它们更像是风险残差中的临时主成分，用于解释近期组合波动和异常回撤，而不是用于长期预测。

对 quant_ex 的适配性：

- 高适配 Phase7 attribution：可以把 unexplained PnL、residual drawdown、unexpected correlation spike 拆解到短暂统计风险暴露上。
- 对现有策略侵入性低：不需要改动 alpha 逻辑，只在风险诊断和实验晋级前增加解释层。
- 与 experiment budget gate 匹配：可以作为低成本 diagnostic experiment，不需要扩大交易规则搜索。
- 特别适合判断“某次改进是否真的提高 alpha，还是只是偶然降低了某个短期风险暴露”。

最小验证实验：

实验名称建议：`risk_transient_factor_attribution_v0`

实验设计：

- 数据范围：仅使用 quant_ex 已有的历史价格、收益、持仓、预测分数、行业/风格暴露或已有风险特征；不新增外部数据。
- 构造对象：对现有风险模型解释后的 residual return 或策略持仓收益残差，在滚动窗口内做 PCA / ICA / sparse PCA 之一。
- 因子数量：固定小规模，例如 3、5、8 三档，不做大范围搜索。
- 对照组：现有 Phase7 attribution 风险模型，不包含 transient factors。
- 处理组：现有风险模型 + transient statistical factors。
- 评估指标：
  - residual PnL variance explained 是否提升；
  - drawdown period 的解释率是否提升；
  - out-of-sample attribution stability 是否提升；
  - 加入 transient factors 后，原有 alpha attribution 是否被大幅重写；
  - 因子换手率和暴露漂移是否可控。
- 不用于直接交易：第一阶段只做归因增强，不产生调仓规则。

与 Phase7 attribution 的关系：

- 应作为 Phase7 的“风险解释补丁层”，用于回答：当前策略收益/亏损中有多少来自可解释 alpha，有多少来自短暂共同风险？
- 如果某个新策略在普通 attribution 下看似提升，但加入 transient factors 后提升主要来自少数临时风险暴露，则不应通过晋级。
- 如果 transient factors 显著解释回撤，但其暴露不可预测、不可控，则只用于风险标签，不转为策略规则。

与 experiment budget gate 的关系：

- 预算等级：低预算 diagnostic。
- 晋级要求：必须优先证明 attribution 解释质量提升，而不是回测收益提升。
- 禁止行为：不得围绕 transient factor 做大量参数寻优，例如窗口长度、因子数、正则化强度、再平衡频率的笛卡尔搜索。

主要风险：

- 把噪声主成分误认为风险因子，导致 attribution 过拟合。
- transient factor 对历史回撤解释很好，但未来不可复现。
- 因子符号和经济含义不稳定，解释性弱。
- 加入后“解释率”提升，但对策略筛选没有帮助。

放弃条件 / kill criteria：

- OOS residual variance explained 提升低于 5%，或只在单一历史区间有效。
- 加入 transient factors 后，Phase7 attribution 结论频繁翻转，但无法形成稳定解释。
- transient factor 暴露与已有风险因子高度共线，增量解释不足。
- drawdown attribution 没有改善，或者改善来自明显 lookback overfit。
- 需要超过 3 组核心参数组合才勉强有效，直接 kill。

---

**方向二：离散潜变量辅助截面排序**

机制解释：

Vector Quantization 的思想是把连续、高维、噪声很大的市场状态或股票特征压缩成有限数量的离散“原型状态”。对截面排序而言，它的潜在价值不一定是提高模型复杂度，而是让模型学到“某类股票在某类状态下更容易排序有效”。

相比普通连续 embedding，离散 latent factor 有两个优点：

- 它可以减少模型在噪声连续空间中乱拟合；
- 它天然适合 attribution，因为每个样本可以被归入某个 latent bucket，方便观察哪些状态贡献收益、哪些状态制造失败。

对 quant_ex 的适配性：

- 适合用于现有截面模型的诊断层，而不是一开始替换 production ranker。
- 可以帮助 Phase7 attribution 从“因子贡献”扩展到“状态贡献”：某个策略在 latent state A 有效，在 state B 失效。
- 对 experiment budget gate 的价值是限制模型复杂度：先做离散分桶带来的稳定性检验，再决定是否值得做更复杂模型。
- 如果 quant_ex 已有模型输出、特征矩阵和横截面标签，这个方向可以不引入外部数据。

最小验证实验：

实验名称建议：`vq_latent_rank_diagnostic_v0`

实验设计：

- 输入：quant_ex 现有特征库、已有截面预测目标、已有训练/验证切分。
- 第一阶段不训练完整深度 VQ 模型，先做轻量近似：
  - 对标准化特征或现有模型中间表征做 k-means / mini-batch k-means；
  - 得到离散 latent bucket；
  - 每个股票-日期样本分配一个 bucket。
- 对照组：
  - baseline ranker；
  - baseline ranker + 原始连续特征；
  - baseline ranker + 简单行业/风格分组诊断。
- 处理组：
  - baseline ranker + latent bucket interaction；
  - 或仅做 bucket-level attribution，不进入模型训练。
- 评估指标：
  - rank IC / NDCG / top-bottom spread 的 OOS 稳定性；
  - 各 bucket 内 IC 是否存在稳定差异；
  - bucket 的时间稳定性和样本覆盖率；
  - 是否减少极端失败日期的集中损失；
  - 是否提升 Phase7 中“模型在哪里有效/失效”的解释能力。
- 参数限制：
  - bucket 数只测试 8、16、32；
  - 固定一个 rolling 或 expanding 训练方案；
  - 不允许同时搜索复杂网络结构。

与 Phase7 attribution 的关系：

- 可以把策略收益拆成 latent bucket contribution：哪些离散状态贡献了收益，哪些状态造成亏损。
- 可用于识别“平均有效、局部失效”的策略：总体 IC 尚可，但某些 latent bucket 持续负贡献。
- 如果某个新 agent 生成的策略只在小样本 latent bucket 中有效，应在 Phase7 降权或拒绝晋级。

与 experiment budget gate 的关系：

- 预算等级：中低预算 model diagnostic。
- gate 重点不是收益最大化，而是状态分层后的稳定性。
- 只有当离散 bucket 在多个 WFV fold 中显示一致的排序差异，才允许进入下一轮更复杂 VQ 模型。
- 若只是用更复杂架构换来微弱 in-sample 提升，不应晋级。

主要风险：

- 离散 latent bucket 可能只是行业、市值、波动等已有风险维度的重命名。
- bucket 数选择容易过拟合。
- 小 bucket 样本不足，导致 attribution 偶然性强。
- 深度 VQ 架构会显著增加实验自由度，破坏 budget gate。

放弃条件 / kill criteria：

- bucket-level OOS IC 差异不稳定，跨 WFV fold 排名相关低。
- latent bucket 与已有行业/风格/波动分组重合度过高，增量解释不足。
- 只有极少数 bucket 有效果，且样本覆盖低于可用阈值。
- baseline ranker 加入 bucket 后没有提升稳定性，反而提高换手或尾部亏损。
- 若轻量 k-means 诊断无效，不进入深度 VQ 原型。

---

**方向三：被拒绝交易事件的结果归因**

机制解释：

RED-2400 的启发不在于使用其外部数据集，而在于建立一种事件级评估框架：策略每天会生成很多候选交易，其中一部分被过滤器、风控规则、冲突检测、成本模型或组合约束拒绝。传统回测只看最终成交组合，容易忽略“被拒绝样本”的真实结果。

如果被拒绝交易后来表现很好，说明过滤器可能过严，错过 alpha；如果被拒绝交易后来表现很差，说明过滤器提供了有效保护。更重要的是，它能把“没做的交易”纳入 attribution，避免只分析已执行样本。

对 quant_ex 的适配性：

- 高度适合 agent strategy iteration，因为 agent 常常会新增过滤条件、阈值、风险 gate。
- 可以直接服务 Phase7 attribution：不仅归因 executed trades，也归因 rejected candidates。
- 不需要外部数据，只需要保存 quant_ex 内部候选池、拒绝原因、最终标签和后验收益。
- 有助于防止策略迭代变成“不断加过滤器改善历史曲线”。

最小验证实验：

实验名称建议：`rejected_candidate_attribution_v0`

实验设计：

- 对每次策略运行保存三类事件：
  - generated candidates：模型或规则原始候选；
  - accepted trades：最终进入组合；
  - rejected candidates：被过滤、成本、约束、冲突规则排除。
- 为每个 rejected candidate 标记拒绝原因：
  - risk_limit；
  - cost_slippage；
  - liquidity_proxy；
  - factor_conflict；
  - portfolio_constraint；
  - score_threshold；
  - duplicate_or_capacity。
- 使用 quant_ex 已有 forward return / rank label 计算事后结果，不增加外部数据。
- 对照组：
  - 当前策略最终成交样本 attribution；
  - 无 rejection attribution。
- 处理组：
  - 增加 rejected event attribution；
  - 计算每类拒绝原因的 avoided loss、missed gain、net rejection value。
- 评估指标：
  - rejected candidates 的平均后验表现；
  - 各拒绝原因的边际贡献；
  - missed winners 占比；
  - avoided losers 占比；
  - 被拒绝样本与成交样本的特征分布差异；
  - 新增过滤规则是否只是减少交易数量而非提高质量。

与 Phase7 attribution 的关系：

- Phase7 应增加一张“执行路径归因表”：候选生成 → 过滤 → 组合约束 → 成交 → 结果。
- 对 agent 生成的新规则，不只看最终回测，还要看它拒绝了什么。
- 如果某个过滤器提升收益但主要通过减少样本、错过大量高分候选实现，应视为不稳定改善。
- 如果过滤器稳定剔除负期望候选，且 missed gain 可控，才允许进入下一轮。

与 experiment budget gate 的关系：

- 预算等级：低预算 instrumentation / attribution。
- 这是 gate 的基础设施，不是新策略。
- 每个未来策略实验都应自动产出 rejected-event attribution，否则不允许扩大预算。
- 防止 agent 通过堆叠过滤器制造虚假的历史改进。

主要风险：

- 需要 quant_ex 回测链路保留候选级日志，工程上可能需要轻微改造。
- 拒绝原因可能重叠，需要定义优先级或多标签。
- 如果候选池本身质量很差，rejection attribution 的解释价值有限。
- 事后标签容易被误读为“本该交易”，必须避免直接转化为实盘调仓规则。

放弃条件 / kill criteria：

- 候选日志无法稳定复现，或同一实验重复运行 rejected set 不一致。
- 拒绝原因覆盖率低，大量样本落入 unknown。
- rejected-event attribution 与最终表现没有解释关系，不能区分有效过滤和无效过滤。
- 新过滤器的收益提升主要来自交易数量下降，且 missed winners 显著上升。
- 若三轮策略实验中该框架没有改变任何 gate 决策，可暂停深化，只保留基础日志。

---

**4. 不建议做的方向**

不建议优先投入 Multi-regime Markov-switching Treasury yield：

- 该论文资产对象是美国国债收益率，和 quant_ex 当前 A 股/截面策略假设不完全匹配。
- Markov regime 本身容易成为宏观状态拟合器，但 quant_ex 当前限制是不引入外部市场/基本面时间序列。
- 若用内部价格特征硬做 regime，容易与已有波动、趋势、流动性状态重复。
- 可以保留为方法观察，不建议进入 prototype。
- 若未来要做，也应作为 existing return distribution regime diagnostic，而不是宏观预测模块。

不建议投入 Kyle lambda under noise-perturbed order-flow：

- 理论价值较高，但需要订单流、盘口或微观结构层面的观测。
- 如果 quant_ex 当前没有稳定内部 order-flow 特征，引入会违反“不新增外部数据采集需求”的约束。
- 用日频或普通成交量代理 Kyle lambda，容易得到伪精确指标。
- 当前不适合作为 strategy iteration 方向，最多作为未来流动性/冲击成本模型的 watch item。

不建议直接复现完整深度 VQ 架构：

- 复杂度高，实验自由度大，不符合 budget gate 的初始阶段。
- 深度模型可能通过架构、训练轮数、损失权重引入大量隐性搜索。
- 应先用轻量离散分桶证明状态分层有增量价值，再考虑复杂模型。

不建议把 transient factors 直接用作交易信号：

- 它们的定位应是风险解释和暴露诊断。
- 短暂统计因子通常缺乏稳定经济含义。
- 直接交易 transient factor 很容易变成回撤期拟合。

---

**5. 下一轮 agent strategy iteration 建议**

建议下一轮不要让 agent 直接生成新交易规则，而是围绕 attribution 和 gate 增强做三组小实验：

1. 先做 `risk_transient_factor_attribution_v0`
   目标是提升 Phase7 对 residual PnL 和 drawdown 的解释能力。若 attribution 解释率无增量，立即停止，不进入交易规则层。

2. 并行做 `rejected_candidate_attribution_v0`
   目标是让所有未来 agent 策略实验都能回答“被过滤掉的候选后来怎样”。这是防止过度过滤和样本选择偏差的核心基础设施。

3. 小预算做 `vq_latent_rank_diagnostic_v0`
   只做轻量 bucket 诊断，不做完整深度模型。若 latent bucket 无法稳定解释 ranker 的有效/失效区域，不继续扩展。

下一轮 gate 规则建议：

- 每个实验必须有 baseline、处理组、WFV fold、成本/滑点假设和 Phase7 attribution 输出。
- 每个实验最多允许 3 个核心参数设置，超过即视为搜索空间膨胀。
- 晋级条件必须包含 attribution 改善，而不只是回测收益改善。
- 若收益提升无法被 attribution 解释，或者解释依赖单一窗口/单一状态，默认不晋级。
- 若实验未改变任何策略选择、风险解释或 gate 决策，应 kill 或降级为观察项。

最终建议：本期最值得做的是“风险归因增强 + 拒绝事件归因”这两个基础能力；VQ 离散潜变量作为辅助诊断小步验证。不要把本期论文解读为新 alpha 来源，而应把它们转化为 quant_ex Phase7 更严格的实验筛选机制。