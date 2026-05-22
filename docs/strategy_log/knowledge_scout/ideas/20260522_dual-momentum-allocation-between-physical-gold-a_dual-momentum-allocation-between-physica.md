# Dual Momentum Allocation Between Physical Gold and Bitcoin (Digital Gold)

```yaml
idea_id: 20260522_dual-momentum-allocation-between-physical-gold-a
source_url: https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/
source_type: rss
source_name: quantpedia_blog
retrieved_at: 2026-05-22T06:24:51Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 3
novelty_score: 3
evidence_score: 3
implementation_cost: low
recommended_action: watch
risk_flags: ['non_a_share_asset_class']
```

## Claim
From the trading desk to the portfolio committee, investors face a familiar question: how should alternative stores of value fit into a diversified portfolio? This research explores that question through a systematic dual-momentum framework comparing Bitcoin and physical gold in a rules-based tactical allocation model. Rather than debating ideology, we focus on practical portfolio construction and risk-adjusted returns. The goal is to examine whether “digital gold” can complement its physical counterpart within a disciplined investment process, and whether the distinct behavior of these assets can be used to build a more effective systematic strategy. The post Dual Momentum Allocation Between Physical Gold and Bitcoin (Digital Gold) first appeared on QuantPedia .

## Mechanism
Risk-aware portfolio construction or drawdown control may improve stability before return repair.

## Evidence
Practitioner/blog metadata from RSS. Use as guidance, not promotion evidence.

## Mapping to quant_ex
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
- https://quantpedia.com/dual-momentum-allocation-between-physical-gold-and-bitcoin-digital-gold/
