# The Privacy Subsidy: Kyle's $λ$ under Noise-Perturbed Order-Flow Observation

```yaml
idea_id: 20260518_the-privacy-subsidy-kyle-s-under-noise-perturbed
source_url: https://arxiv.org/abs/2605.15746v1
source_type: arxiv
source_name: arxiv_qfin_pm
retrieved_at: 2026-05-18T18:16:44Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 3
novelty_score: 3
evidence_score: 4
implementation_cost: low
recommended_action: watch
risk_flags: ['non_a_share_asset_class']
```

## Claim
Privacy-preserving cryptocurrency exchanges (shielded AMMs, batched swap auctions, sealed-bid order-flow auctions) alter what the pricing mechanism observes about order flow. We derive the unique linear Kyle equilibrium when a committed Bayesian market maker observes order flow perturbed by independent Gaussian privacy noise. The price-impact coefficient and informed-trader strategy both rescale by a single factor in the privacy parameter, and their product is invariant. A welfare decomposition then identifies a closed-form per-period transfer from the protocol's LP pool to traders -- the "privacy subsidy", the break-even fee any privacy-aggregated exchange must charge. The result is the single-period closed-form privacy-noise analog of Loss-Versus-Rebalancing (Milionis et al. 2022). The primary application is shielded AMMs with explicit additive-noise injection (e.g., differential privacy); related designs (batched swaps, sealed-bid auctions, oracle-pegged crossings) require separate frameworks that we leave to future work.

## Mechanism
Potential factor/anomaly mechanism that may translate into feature engineering or candidate filters.

## Evidence
Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally.

## Mapping to quant_ex
- features/ or features/library/: candidate feature or factor diagnostic

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
- https://arxiv.org/abs/2605.15746v1
