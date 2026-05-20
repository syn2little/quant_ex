# Phase 8 gate_m008 failure attribution v0 — 2026-05-19

## Scope
- Read-only diagnostic from existing WFV fold artifacts.
- No new backtest, no data refresh, no parameter search, no rebalance.
- Candidate: `gate_m008`, `drawdown_threshold: -0.08`.
- Limitation: WFV artifacts contain fold-level metrics only; daily portfolio returns, positions, trades, and candidate events were not exported for each WFV fold.

## Aggregate read
- mean Sharpe: 1.1248
- min Sharpe: -0.0424
- worst max drawdown: -29.15%
- positive Sharpe folds: 6/7
- Sharpe p-value: 0.0079

## Failure localization
- Weakest fold: 2022 with Sharpe -0.0424, annual return -1.35%, max drawdown -29.15%.
- 2022: Sharpe -0.0424, annual return -1.35%, annual vol 31.80%, max drawdown -29.15%, IR 1.3398, alpha 26.19%.
- 2023: Sharpe 0.6985, annual return 15.58%, annual vol 22.31%, max drawdown -18.50%, IR 1.7147, alpha 28.59%.

## Benchmark-relative diagnosis
- Problem years average annual return: 7.11%; average alpha: 27.39%; average IR: 1.5272.
- Non-problem years average annual return: 32.71%; average alpha: 18.76%; average IR: 1.0540.
- 2022 is not a pure stock-selection failure: annual return is slightly negative, but alpha and IR are strongly positive.
- The blocker is absolute-risk survival: high beta/tracking volatility and deep drawdown keep Sharpe slightly below zero despite positive excess performance.
- 2023 is repaired directionally versus soft_no_gate, becoming positive annual return and positive Sharpe, so the residual blocker is concentrated in 2022.

## Drawdown diagnosis
- Daily WFV returns were not persisted, so this report intentionally avoids synthetic daily-path reconstruction.
- The persisted 2022 fold max drawdown is -29.15%, with annual vol 31.80% and beta 1.2281.
- Tracking error is 20.12%, about 0.6327x annual vol, so active risk is material but not the only risk source.
- This supports a portfolio-risk interpretation: the fold does not need more alpha threshold fitting; it needs a drawdown/volatility budget if this line continues.

## What not to do
- Do not continue threshold fitting around -0.08 just to flip 2022 Sharpe from -0.0424 to positive.
- Do not promote `gate_m008` from these results.
- Do not change daily rebalance/default configs.

## Recommended next design
`portfolio_risk_cap_over_signal_tuning`

Keep `gate_m008` as the fixed signal candidate, and if continuing, test a portfolio-layer cap rather than another signal threshold:
- volatility or drawdown regime risk budget,
- lower gross exposure or per-position cap during gated regimes,
- optional turnover cap to reduce whipsaw during high-volatility periods.

Before any such run, modify WFV export plumbing to persist fold-level attribution inputs so future failure attribution can use real daily returns/candidate events instead of fold-level approximations.
