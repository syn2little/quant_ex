# Phase 8 first formal batch iteration plan - 2026-05-19

## Scope and guardrails

This batch is research-only. It does not refresh data, rebalance, send live notifications, promote configs, run full WFV, or perform trading-like actions.

Current decision: keep `gate_m008` fixed and stop signal-threshold micro-tuning. The next useful work is portfolio-risk-cap experimentation and missing daily diagnostics.

## Evidence read

- `docs/strategy_log/phase8_regime_gate_grid_full_wfv_conclusion_2026-05-19.md`: `gate_m008` is the best grid candidate but remains not promotable.
- `docs/strategy_log/phase8_phase8_regime_gate_grid_m008_full_wfv_20260519_promotion_report_2026-05-19.md`: mean Sharpe 1.1248, min Sharpe -0.0424, 6/7 positive Sharpe, worst drawdown -29.15%; status remains `compare_next` / `not_promotable`.
- `docs/strategy_log/phase8_gate_m008_failure_attribution_v0_2026-05-19.md`: 2022 fold has annual return -1.35%, Sharpe -0.0424, IR 1.3398, alpha 26.19%, volatility 31.80%, beta 1.2281.
- `docs/strategy_log/phase8_gate_m008_2022_daily_failure_attribution_conclusion_2026-05-19.md`: daily attribution concludes `portfolio_risk_cap_over_signal_tuning`.
- `docs/strategy_log/phase8_gate_m008_2022_daily_failure_attribution_v0_2026-05-19.md`: 242 days, mean residual return +0.001070, worst drawdown -29.15%, worst daily return -6.81%, stress days 196.
- `config/csi1000_transient_repair_regime_gated_svs_m008.yaml`: fixed candidate parameters are `topk=15`, `n_drop=3`, `hold_thresh=8`, SVS keep-top settings, and drawdown gate -0.08.

## Quant strategy-risk lane

Recommended experiments with `gate_m008` fixed:

1. Stress gross exposure cap
   - Keep signal, `topk`, `n_drop`, `hold_thresh`, and SVS settings unchanged.
   - Test portfolio-level gross exposure caps such as 0.75 and 0.60 only when the portfolio or market is already in stress.
   - Primary question: can April/October 2022 drawdown improve without destroying 2024-2026 upside?

2. Volatility budget cap
   - Keep selected names unchanged and scale exposure by trailing realized volatility.
   - Target annualized volatility around 22%-24% with scale upper bound 1.0 and lower bound no lower than 0.5.
   - Primary question: can the 2022 31.80% annualized volatility be reduced while preserving positive residual returns?

3. Drawdown brake and recovery ramp
   - Cut risk after portfolio drawdown enters a predefined stress region.
   - Restore exposure gradually over 3-5 trading days after stress exits.
   - Primary question: can this reduce whipsaw around 2022-04-25/26 and 2022-10-10/28?

4. Turnover-aware cap as a secondary arm
   - Add daily risk-budget change limits only if exposure caps reduce drawdown but increase turnover/cost.
   - Do not tune signal thresholds as a substitute for portfolio risk control.

## Quant diagnostics lane

Existing 2022 attribution artifacts are present:

- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_portfolio_returns.csv`
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_risk_exposures.csv`
- `backtest_results/agent_runs/wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519_candidate_events.csv`
- `optimization_results/walk_forward_phase8_gate_m008_single_fold_2022_attr_20260519/walk_forward_all_results.csv`

Useful current fields:

- `portfolio_returns.csv`: `date`, `portfolio_return`, `benchmark_return`, `cost`, `excess_return`.
- `risk_exposures.csv`: `date`, `portfolio_return`, `benchmark_return`, `residual_return`, `drawdown`, `abs_residual_return`.
- `candidate_events.csv`: `date`, `instrument`, `decision`, `rejection_reason`, `score`, `rank`, `forward_return`.

Missing diagnostics before a risk-cap prototype:

- Daily holdings and weights, including actual holding count and concentration.
- Daily gross/net exposure or cash ratio.
- Daily turnover, trade list, buy/sell amounts, and cap-induced turnover estimate.
- Raw trigger series for risk cap rules: realized volatility, rolling volatility, risk budget utilization, cap state, pre-cap exposure, post-cap exposure.
- Industry, style, size, beta, or market exposure fields to separate beta/industry/size drawdown from idiosyncratic loss.
- Candidate event `weight` or contribution fields to map accepted losers and missed winners into portfolio risk contribution.
- Pre-cap vs post-cap daily counterfactual fields for drawdown, return, and rebound loss.

## Validation ladder

1. Read-only post-hoc simulation
   - Use existing daily returns, residual returns, and drawdown series.
   - Estimate exposure scaling effects without retraining, data refresh, or WFV.
   - Gate: max drawdown improves materially versus -29.15% and residual advantage is not erased.

2. 2022 single-fold light validation
   - Fixed `gate_m008`, fixed `topk=15`, `n_drop=3`, `hold_thresh=8`.
   - Export attribution inputs and risk-cap state fields.
   - Gate: Sharpe moves from -0.0424 toward positive, max drawdown improves, turnover/cost does not explode.

3. Recent-window damage check
   - Use fixed-model / same-model windows only as diagnostic evidence, not promotion evidence.
   - Gate: 2024-2026 annual return and Sharpe do not collapse, and drawdown is not worse than original `gate_m008`.

4. Full WFV only after explicit approval
   - Only request full WFV if the previous steps pass.
   - Promotion remains blocked until WFV promotion evidence and human review exist.

## Decision

Status: `research_candidate` for portfolio-risk-cap experiments; `gate_m008` remains `not_promotable` and `compare_next`.

Next background-ready task: implement a read-only diagnostic script or notebook that materializes daily risk-cap input fields from existing attribution exports. It should not refresh data, rebalance, send notifications, promote configs, or run full WFV.
