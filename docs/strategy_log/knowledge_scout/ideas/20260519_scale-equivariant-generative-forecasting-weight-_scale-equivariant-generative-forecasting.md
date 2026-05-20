# Scale-Equivariant Generative Forecasting: Weight-Tied Dilated Convolutions, Wavelet Scattering Inputs, and Spectral-Consistency Training for Self-Similar Time Series

```yaml
idea_id: 20260519_scale-equivariant-generative-forecasting-weight-
source_url: https://arxiv.org/abs/2605.17582v1
source_type: arxiv
source_name: arxiv_ml_finance
retrieved_at: 2026-05-19T15:53:22Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 5
novelty_score: 4
evidence_score: 4
implementation_cost: medium
recommended_action: prototype
risk_flags: []
```

## Claim
Many natural and engineered time series -- equity returns, climate anomalies, turbulent velocities, neural recordings, packet-level network traffic -- are approximately self-similar: their horizon-$T$ distribution is tied to the horizon-$1$ distribution by one scaling exponent $H$. Standard deep generative sequence models (transformers, dilated TCNs, the WaveNet family) ignore this. Their receptive fields are wide, but kernel parameters live independently at every dilation level, yielding a multi-scale architecture, not a scale-equivariant one. We make three contributions. First, we give a precise definition of discrete scale equivariance for 1D causal networks and prove that dyadic dilation commutes (up to boundary effects) with any dilated-convolution stack whose kernel weights are shared across levels. Tying the kernel shrinks the convolutional parameter budget by an $L$-fold factor (where $L$ is depth) and hard-wires self-similarity in as an inductive bias. Second, we wrap this Scale-Equivariant WaveNet (SE-WaveNet) backbone in three components that carry the same prior: a one-level Daubechies-4 wavelet input, a Hurst-FiLM block exposing the local scaling exponent, and a spectral-consistency training term targeting the $|f|^{-(2H+1)}$ power-law spectrum. The head is a conditional normalising flow, chosen to preserve equivariance. Third, on 30 years of S&P 500 daily log-returns, SE-WaveNet samples reproduce the empirical scaling-collapse diagnostic on the Allan-Variance top-25 universe (median $\mathcal{C}^\star = 0.020$), while a vanilla WaveNet at matched capacity does not ($\geq 0.06$). NLL, KS-calibration, and tail energy distance tie or beat the baseline, with $L\times$ fewer convolutional parameters.

## Mechanism
Potential factor/anomaly mechanism that may translate into feature engineering or candidate filters.

## Evidence
Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally.

## Mapping to quant_ex
- features/ or features/library/: candidate feature or factor diagnostic
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
- https://arxiv.org/abs/2605.17582v1
