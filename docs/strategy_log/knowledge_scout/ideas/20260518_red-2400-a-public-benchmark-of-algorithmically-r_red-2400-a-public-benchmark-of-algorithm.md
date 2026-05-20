# RED-2400: A Public Benchmark of Algorithmically-Rejected Trading Events with Outcome Labels

```yaml
idea_id: 20260518_red-2400-a-public-benchmark-of-algorithmically-r
source_url: https://arxiv.org/abs/2605.12151v1
source_type: arxiv
source_name: arxiv_qfin_pm
retrieved_at: 2026-05-18T18:16:44Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 3
novelty_score: 4
evidence_score: 4
implementation_cost: low
recommended_action: summarize
risk_flags: []
```

## Claim
RED-2400 is a public benchmark of algorithmically-rejected trading events from a live Solana decentralized-exchange filter stack. I logged the data continuously between 2026-04-10 and 2026-05-02. The benchmark contains 6,659 rejection events linked to 169,122 post-rejection price and liquidity observations and 1,836 graveyard-tracker snapshots. Outcome labels follow the five-tier classification of Kamat (2026c): saved (windowed), saved (early-death), missed, flat, and unclassifiable. Thresholds use the trough-to-reference and peak-to-reference price ratios within a 24-hour window. Most filter-design datasets cover the accept side only. That gap leaves reject-side outcomes unmeasured and biases filter validation. RED-2400 lets researchers replicate filter-precision claims directly. RED-2400 is the first window in a planned dataset series; subsequent windows will extend the time horizon and enable regime-stratified analysis.

## Mechanism
External research mechanism requires manual interpretation before local validation.

## Evidence
Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally.

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
- https://arxiv.org/abs/2605.12151v1
