# Phase 8 transient repair soft SVS conclusion — 2026-05-19

## Scope
- No full WFV.
- No data refresh.
- No rebalance or trading action.
- Diagnostic-only same-model local backtest.

## Experiment
- Config: `config/csi1000_transient_repair_soft_svs.yaml`
- Model: `models/lgbm_csi1000_balanced_20260429_002424.pkl`
- Run id: `phase8_transient_repair_soft_svs_20260519`
- Change: keep original stock-vs-sector `keep_top_pct: 0.4`, but apply `soft_keep_top_pct_floor: 0.5` as a narrow repair knob to reduce missed-winner pruning.

## Same-model result
- cumulative return: 94.13%
- annual return: 33.94%
- sharpe: 1.6663
- max drawdown: -11.77%
- information ratio: 1.0973
- alpha: 19.11%
- rank_ic: 0.0537
- rank_icir: 0.3420
- days: 572

## Attribution result
- Report: `docs/strategy_log/phase8_transient_repair_soft_svs_attribution_v0_2026-05-19.md`
- mean residual return: 0.000559
- hit rate: 0.533217
- worst drawdown: -0.117744
- drawdown_stress mean residual return: -0.000828
- accepted_count: 8220
- rejected_count: 67289
- missed_winner_count: 31311
- accepted_loser_count: 4010

## Comparison against prior same-model attribution baseline
- Baseline run: `phase8_same_model_attribution_20260519`
- Baseline cumulative return: 36.90%
- Baseline sharpe: 0.6306
- Baseline max drawdown: -22.00%
- Baseline IR: -0.0471
- Baseline mean residual return: -0.000026
- Baseline missed_winner_count: 69682
- Soft SVS improved same-model return, drawdown, IR, mean residual, and missed-winner count.

## Guardrail conclusion
`same_model_promising_but_not_promoted`

This is positive diagnostic evidence only. It is not promotion evidence and must not be used for live trading, notifications, or daily rebalance changes without explicit WFV validation.

## Next action
Run a narrow WFV gate for `config/csi1000_transient_repair_soft_svs.yaml` only after approval, or add a second diagnostic comparing baseline, hard SVS, and soft SVS on identical artifact windows before spending WFV budget.
