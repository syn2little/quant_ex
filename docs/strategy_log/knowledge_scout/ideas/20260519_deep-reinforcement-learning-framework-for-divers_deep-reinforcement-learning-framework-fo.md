# Deep Reinforcement Learning Framework for Diversified Portfolio Management Across Global Equity Markets

```yaml
idea_id: 20260519_deep-reinforcement-learning-framework-for-divers
source_url: https://arxiv.org/abs/2605.17307v1
source_type: arxiv
source_name: arxiv_qfin_pm
retrieved_at: 2026-05-19T15:53:16Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 5
novelty_score: 4
evidence_score: 4
implementation_cost: medium
recommended_action: prototype
risk_flags: []
```

## Claim
This study develops and evaluates a deep reinforcement learning framework for dynamic portfolio allocation across global equity markets. The Soft Actor-Critic algorithm is used to learn continuous portfolio weights within a Markov Decision Process, incorporating transaction costs, turnover penalties, and diversification constraints into the reward function. Five model configurations are compared, varying in reward formulation, policy structure (flat versus hierarchical Dirichlet), portfolio constraints, and temporal encoder (LSTM versus Transformer), and evaluated via walk-forward optimization across sixteen out-of-sample folds spanning 2003-2026 on the Nasdaq-100, Nikkei 225, and Euro Stoxx 50. Results show that RL strategies achieve competitive risk-adjusted performance primarily in the Euro Stoxx 50, where statistically significant abnormal returns are observed, but the central hypothesis is only partially confirmed: no strategy achieves statistically significant excess returns relative to Buy and Hold under HAC-robust inference across all markets. Regime analysis reveals that RL adds the most value during periods of elevated uncertainty, while ensemble aggregation across markets improves risk-adjusted performance and confirms the benefits of geographic diversification.

## Mechanism
Risk-aware portfolio construction or drawdown control may improve stability before return repair.

## Evidence
Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally.

## Mapping to quant_ex
- models/: optional model architecture or training objective prototype
- backtest/ and strategy/: portfolio construction, regime, or risk overlay diagnostic

## Validation Ladder
- Summarize mechanism and compare against existing rejected/promising research threads.
- Map the idea to one minimal feature/model/backtest change with a fixed control arm.
- Run a cheap same-model or small-window diagnostic only if implementation cost is low/medium.
- Promote to WFV only if the diagnostic improves IR/Sharpe without worsening drawdown controls.
- Require promotion report and human approval before touching strategy_candidates or rebalance configs.

## Kill Criteria
- Do not ingest external market/fundamental time-series data; reject ideas that require it outside approved data sources.
- Reject if it cannot define a comparable control arm and rank metric.
- Kill if early diagnostic breaks current drawdown/positive-fold constraints.

## References
- https://arxiv.org/abs/2605.17307v1
