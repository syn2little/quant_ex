# Multi-regime Markov-switching models with time-varying transition probabilities: An application to U.S. Treasury yields

```yaml
idea_id: 20260518_multi-regime-markov-switching-models-with-time-v
source_url: https://arxiv.org/abs/2605.14976v1
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
This paper studies Markov-switching (MS) models with time-varying transition probabilities (TVTP) under various specifications of the transition probability matrix. Especially, we extend the two-regime common-variance setting of the Generalized Autoregressive Score (GAS) model from (Bazzi et al., 2017) to the general $K$-regime case with regime-specific means and variances. Our study contains comprehensive Monte Carlo simulations and we developed an open-source R package, \texttt{multiregimeTVTP}, for data simulation and parameter estimation. We find that the regime means, variances, and transition probabilities are reliably recovered, whereas the TVTP driving coefficients are harder to identify. Another finding from our paper is that the GAS score coefficient appears to be statistically non-identifiable, due to a ridge in the joint likelihood surface $(σ^2,A)$. In addition, we find that one-step point forecasts are remarkably robust to TVTP misspecification, but filtered regime probabilities are not, so correct specification matters most for characterizing regime dynamics rather than short-horizon forecasting. An empirical application to U.S. Treasury zero-coupon yield changes at four maturities (1961-2024) shows that an exogenous specification driven by the lagged yield level dominates the constant and lagged-change models in fit, while the GAS specification fails to converge, with $\hat{A}$ collapsing to zero, reflecting the same identifiability issue observed in simulation.

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
- https://arxiv.org/abs/2605.14976v1
