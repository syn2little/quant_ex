# Dynamic Elliptical Graph Factor Models via Riemannian Optimization with Geodesic Temporal Regularization

```yaml
idea_id: 20260519_dynamic-elliptical-graph-factor-models-via-riema
source_url: https://arxiv.org/abs/2605.18316v1
source_type: arxiv
source_name: arxiv_ml_finance
retrieved_at: 2026-05-19T15:53:22Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 5
novelty_score: 4
evidence_score: 4
implementation_cost: low
recommended_action: prototype
risk_flags: []
```

## Claim
Inferring time-varying graph structures from high-dimensional nodal observations is a fundamental problem arising in neuroscience, finance, climatology, and beyond. Two intrinsic challenges govern this problem: maintaining the \emph{temporal coherence} of the latent graph across successive observation windows, and respecting the \emph{intrinsic Riemannian geometry} of the symmetric positive definite manifold on which precision matrices naturally reside, a curved space whose geodesic structure departs fundamentally from that of the ambient Euclidean space. In this paper we propose dynamic estimation on the Grassmann manifold with a factor model (\textsc{Degfm}), a novel algorithm that jointly addresses both challenges. We model the time-varying precision matrix sequence as a low-rank-plus-diagonal structure governed by a latent elliptical graph factor model, which drastically reduces the effective parameter count and enables reliable estimation in the challenging small-sample regime. Temporal coherence is enforced through a Riemannian geodesic penalty defined on the Grassmann manifold, ensuring that the estimated graph trajectory is smooth with respect to the intrinsic geometry rather than the ambient Euclidean space. To solve the resulting non-convex optimization problem over Grassmann-manifold-valued sequences subject to the LRaD constraint, we derive an efficient Riemannian gradient descent algorithm that respects the manifold structure at every iterate and rigorously establish its convergence to a stationary point. Extensive experiments on both synthetic benchmarks and real-world datasets demonstrate that \textsc{Degfm} consistently outperforms state-of-the-art baselines across all evaluation metrics, confirming the practical effectiveness of the proposed framework.

## Mechanism
Potential factor/anomaly mechanism that may translate into feature engineering or candidate filters.

## Evidence
Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally.

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
- https://arxiv.org/abs/2605.18316v1
