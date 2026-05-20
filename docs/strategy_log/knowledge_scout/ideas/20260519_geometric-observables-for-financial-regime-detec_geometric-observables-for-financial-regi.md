# Geometric Observables for Financial Regime Detection

```yaml
idea_id: 20260519_geometric-observables-for-financial-regime-detec
source_url: https://arxiv.org/abs/2605.17117v1
source_type: arxiv
source_name: arxiv_qfin_pm
retrieved_at: 2026-05-19T15:53:16Z
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
We extract four geometric observables -- Berry Phase Rate, Spectral Entropy, Reduced State Purity, and Hamiltonian Sensitivity -- from a learned spectral embedding of equity-index returns and evaluate them as regime-shift detectors against 46 classical and machine-learning baselines on 17 historical crises spanning 2000-2024. Under walk-forward nested hyperparameter selection on nine labelled windows, the Berry Phase Rate achieves an unbiased out-of-sample median Cohen's $d = 0.72$ (95% percentile-bootstrap CI $[0.34, 1.18]$, 10,000 resamples) and produces approximately 67% fewer false alarms per year than a label-supervised Random Forest (1.2 vs. 3.6 per year). Reduced State Purity attains the highest in-sample separability of any method ($d = 0.83$), tied closely by the Absorption Ratio ($d = 0.80$); geometric and classical channels are largely uncorrelated (mean $|ρ| \approx 0.22$), suggesting they capture distinct risk signals. Score construction is unsupervised; hyperparameter selection is the only supervised step.

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
- https://arxiv.org/abs/2605.17117v1
