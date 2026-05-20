# Promotion Report: phase8_regime_gate_grid_m008_full_wfv_20260519

- Generated: 2026-05-19T15:09:49
- Decision: compare_next
- Promotion status: not_promotable
- Evidence level: wfv
- Recommendation: WFV evidence is mixed; keep as compare_next and inspect blocked gates before spending more budget.

## Result Contract
- Source: `optimization_results/walk_forward_phase8_regime_gate_grid_m008_full_wfv_20260519/walk_forward_summary.csv`
- Kind: walk_forward_summary
- Rows: 1
- Rank metric requested: mean_sharpe
- Rank metric used: mean_sharpe
- Benchmark aware: False

## Best Row
- Result: `{'train_universe': 'csi1000', 'eval_market': 'csi300', 'topk': '15', 'n_drop': '3', 'hold_thresh': '8', 'folds': '7', 'mean_annual_return': '0.254', 'median_annual_return': '0.2951', 'mean_sharpe': '1.124842857142857', 'median_sharpe': '1.0473', 'min_sharpe': '-0.0424', 'sharpe_std': '0.7055138711953007', 'mean_max_drawdown': '-0.18111428571428573', 'worst_max_drawdown': '-0.2915', 'positive_return_folds': '6', 'positive_sharpe_folds': '6', 'mean_rank_ic': '0.04881428571428571', 'mean_rank_icir': '0.35471428571428565', 'sharpe_ttest_pvalue': '0.007934672706913668', 'return_ttest_pvalue': '0.004543987282988597', 'robust_score': '1.0636059215452067', 'pareto_front': 'True'}`

## Gates
- PASS `contract_complete`: CSV classified and required fields are present.
- PASS `rank_metric_policy`: Rank metric used: mean_sharpe.
- PASS `wfv_required_for_promotion`: Only WFV summary evidence can produce a promote decision.
- PASS `wfv_mean_sharpe`: mean_sharpe=1.1248
- BLOCK `wfv_min_sharpe`: min_sharpe=-0.0424
- PASS `wfv_pvalue`: sharpe_ttest_pvalue=0.007934672706913668
- PASS `wfv_drawdown`: worst_max_drawdown=-0.2915

## Warnings
- No control CSV supplied; promotion decision is conservative.
