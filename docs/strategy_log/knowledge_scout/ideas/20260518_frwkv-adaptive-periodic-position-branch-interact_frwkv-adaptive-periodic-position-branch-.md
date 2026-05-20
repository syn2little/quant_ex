# FRWKV+: Adaptive Periodic-Position Branch Interaction for Frequency-Space Linear Time Series Forecasting

```yaml
idea_id: 20260518_frwkv-adaptive-periodic-position-branch-interact
source_url: https://arxiv.org/abs/2605.15690v1
source_type: arxiv
source_name: arxiv_ml_finance
retrieved_at: 2026-05-18T18:05:16Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 4
novelty_score: 4
evidence_score: 4
implementation_cost: low
recommended_action: prototype
risk_flags: []
```

## Claim
Long-term time series forecasting is essential for decision making in energy, finance, transportation, and healthcare systems. Recent lightweight forecasting models improve efficiency by operating in transformed or linearized spaces, but two challenges remain in frequency-space forecasting. The real and imaginary streams of complex spectra contain complementary information that is often weakly exchanged, and periodic-position cues can help recurring patterns only when they are reliable for the current dataset and prediction horizon. To address these challenges, we propose FRWKV+, an enhanced FRWKV forecasting model for selective periodic-position branch interaction. FRWKV+ first introduces cross-branch gates that exchange compact contexts between the real and imaginary frequency streams, allowing each stream to modulate the other. It then uses the Adaptive PhaseGate mechanism to extract periodic-position context and generate signed corrections to these gates. An adaptive trust mechanism controls the correction strength at the sample, variable, and channel levels, so periodic-position information is admitted as a reliable correction signal while preserving the efficiency of the FRWKV backbone. External benchmark tables report a separately labeled FRWKV-family selected system for manuscript-level comparison, while mechanism-level claims are based on strict matched-seed FRWKV-family ablations and representative component-level ablations. Under this matched protocol, FRWKV+ achieves the largest MSE winner coverage among the family variants and provides clear gains in selected periodic regimes. Component analysis further supports the usefulness of periodic-position context, signed correction, and adaptive trust in these regimes, while revealing boundary cases where simpler correction rules remain preferable.

## Mechanism
Modeling architecture or training objective may improve ranking signal extraction.

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
- https://arxiv.org/abs/2605.15690v1
