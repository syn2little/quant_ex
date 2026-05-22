# The Attention Factor: The Link That Connects Crypto and Public Equity Markets

```yaml
idea_id: 20260522_the-attention-factor-the-link-that-connects-cryp
source_url: https://quantpedia.com/the-attention-factor-the-link-that-connects-crypto-and-public-equity-markets/
source_type: rss
source_name: quantpedia_blog
retrieved_at: 2026-05-22T06:24:51Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 5
novelty_score: 4
evidence_score: 3
implementation_cost: high
recommended_action: summarize
risk_flags: []
```

## Claim
In an era of increasingly fragmented market microstructure, the emergence of cross-asset connectedness between Crypto and public equity markets presents a critical challenge for modern portfolio construction. This blog post examines the recent working paper by Harin de Silva, "The Attention Factor: The Speculative Risk You May Already Own," which identifies a previously underappreciated transmission channel: a speculative cohort of marginal investors whose sentiment shifts propagate correlated price movements across BTC, zero-day-to-expiration (0DTE) options, commission-free brokerages, and social-sentiment-driven equities. The author introduces the Attention factor—a capital-backed measure of collective conviction—as a systematic risk driver that persists after controlling for traditional macro factors, fundamentally reshaping how we model Equity Risk in multi-asset portfolios. For quantitative practitioners, this work underscores the need to augment conventional Risk Models with sentiment-aware factors to capture residual connectedness that standard factor frameworks may overlook. The post The Attention Factor: The Link That Connects Crypto and Public Equity Markets first appeared on QuantPedia .

## Mechanism
Risk-aware portfolio construction or drawdown control may improve stability before return repair.

## Evidence
Practitioner/blog metadata from RSS. Use as guidance, not promotion evidence.

## Mapping to quant_ex
- features/ or features/library/: candidate feature or factor diagnostic
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
- https://quantpedia.com/the-attention-factor-the-link-that-connects-crypto-and-public-equity-markets/
