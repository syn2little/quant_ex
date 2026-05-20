# Promotion Report: phase8_regime_gate_grid_m005_full_wfv_20260519

- Generated: 2026-05-19T15:09:49
- Decision: compare_next
- Promotion status: not_promotable
- Evidence level: wfv
- Recommendation: WFV evidence is mixed; keep as compare_next and inspect blocked gates before spending more budget.

## Result Contract
- Source: `optimization_results/walk_forward_phase8_regime_gate_grid_m005_full_wfv_20260519/walk_forward_summary.csv`
- Kind: walk_forward_summary
- Rows: 1
- Rank metric requested: mean_sharpe
- Rank metric used: mean_sharpe
- Benchmark aware: False

## Best Row
- Result: `{'train_universe': 'csi1000', 'eval_market': 'csi300', 'topk': '15', 'n_drop': '3', 'hold_thresh': '8', 'folds': '7', 'mean_annual_return': '0.21717142857142857', 'median_annual_return': '0.2646', 'mean_sharpe': '0.8847857142857143', 'median_sharpe': '1.3507', 'min_sharpe': '-0.4998', 'sharpe_std': '0.8394412706906751', 'mean_max_drawdown': '-0.19745714285714286', 'worst_max_drawdown': '-0.3293', 'positive_return_folds': '5', 'positive_sharpe_folds': '5', 'mean_rank_ic': '0.04871428571428571', 'mean_rank_icir': '0.36422857142857146', 'sharpe_ttest_pvalue': '0.041668238996072526', 'return_ttest_pvalue': '0.052525874631201494', 'robust_score': '0.6151050789403767', 'pareto_front': 'True'}`

## Gates
- PASS `contract_complete`: CSV classified and required fields are present.
- PASS `rank_metric_policy`: Rank metric used: mean_sharpe.
- PASS `wfv_required_for_promotion`: Only WFV summary evidence can produce a promote decision.
- BLOCK `wfv_mean_sharpe`: mean_sharpe=0.8848
- BLOCK `wfv_min_sharpe`: min_sharpe=-0.4998
- PASS `wfv_pvalue`: sharpe_ttest_pvalue=0.041668238996072526
- PASS `wfv_drawdown`: worst_max_drawdown=-0.3293

## Warnings
- No control CSV supplied; promotion decision is conservative.
