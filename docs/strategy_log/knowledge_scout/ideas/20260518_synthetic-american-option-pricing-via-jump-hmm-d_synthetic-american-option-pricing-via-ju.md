# Synthetic American Option Pricing via Jump-HMM-Driven Heston Implied Volatility

```yaml
idea_id: 20260518_synthetic-american-option-pricing-via-jump-hmm-d
source_url: https://arxiv.org/abs/2605.13998v1
source_type: arxiv
source_name: arxiv_ml_finance
retrieved_at: 2026-05-18T18:05:16Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 3
novelty_score: 4
evidence_score: 4
implementation_cost: high
recommended_action: summarize
risk_flags: []
```

## Claim
Generating realistic synthetic option prices requires implied volatility as an input, yet implied volatility is itself derived from observed option prices, creating a circular dependency that limits synthetic data for machine-learning and risk-analysis applications. We break this circularity with a pipeline in which implied volatility emerges as an output of a structural model of equity returns. A Jump Hidden Markov Model produces multi-asset price paths with realistic stylized facts and cross-asset tail dependence; a modified Heston variance process, whose mean-reversion target depends on regime state, days to expiration, moneyness, and a market-mood indicator, converts those paths into implied-volatility paths; and a recombining binomial lattice prices American options from the resulting surface. Initializing variance at its mean-reversion target for each strike-expiration pair lets smile, skew, and term structure emerge without external calibration. We calibrate the shape function through a hierarchy spanning a parametric baseline, a globally shared neural surrogate, and a sector-specific neural surrogate fit to a multi-ticker, multi-sector option ladder. A temporal holdout on a multi-day capture isolated scheduled corporate events as the dominant source of test-time generalization error, and calendar-derived earnings-distance and same-sector peer-coupling features recovered the anticipatory portion of that signal. We then apply the framework as a synthetic-data generator on real near-the-money put and call contracts, forward-simulating price paths, and recovering path-conditional implied volatility, finite-difference American Greeks, and terminal short-premium profit and loss from one coherent simulation, and confirm cross-ticker robustness by re-running on a second underlying from a different sector and volatility regime. The framework is released as an open-source Julia package.

## Mechanism
Risk-aware portfolio construction or drawdown control may improve stability before return repair.

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
- https://arxiv.org/abs/2605.13998v1
