# Who Profits from Prediction Markets?

```yaml
idea_id: 20260522_who-profits-from-prediction-markets
source_url: https://quantpedia.com/who-profits-from-prediction-markets/
source_type: rss
source_name: quantpedia_blog
retrieved_at: 2026-05-22T06:24:51Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 1
novelty_score: 2
evidence_score: 3
implementation_cost: low
recommended_action: watch
risk_flags: []
```

## Claim
In the high-stakes arena of prediction markets, a counterintuitive pattern emerges: retail traders who correctly pick winners more than half the time still lose money, while automated traders with coin-flip accuracy pocket nine-figure profits. Using 222 million prediction market tradeswith directly observable terminal payoffs, the paper "Who Profits from Prediction? Execution, Not Information" presents a clean answer to why it is so. The authors decompose trader returns into a directional component and an execution component, revealing that the execution component, not the directional component, determines which trader types earn positive returns. The post Who Profits from Prediction Markets? first appeared on QuantPedia .

## Mechanism
Execution-aware evaluation may change slippage/cost assumptions or rebalance rules.

## Evidence
Practitioner/blog metadata from RSS. Use as guidance, not promotion evidence.

## Mapping to quant_ex
- models/: optional model architecture or training objective prototype

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
- https://quantpedia.com/who-profits-from-prediction-markets/
