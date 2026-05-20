# Promotion Report: phase8_regime_gate_grid_m012_full_wfv_20260519

- Generated: 2026-05-19T15:09:50
- Decision: compare_next
- Promotion status: not_promotable
- Evidence level: wfv
- Recommendation: WFV evidence is mixed; keep as compare_next and inspect blocked gates before spending more budget.

## Result Contract
- Source: `optimization_results/walk_forward_phase8_regime_gate_grid_m012_full_wfv_20260519/walk_forward_summary.csv`
- Kind: walk_forward_summary
- Rows: 1
- Rank metric requested: mean_sharpe
- Rank metric used: mean_sharpe
- Benchmark aware: False

## Best Row
- Result: `{'train_universe': 'csi1000', 'eval_market': 'csi300', 'topk': '15', 'n_drop': '3', 'hold_thresh': '8', 'folds': '7', 'mean_annual_return': '0.20544285714285718', 'median_annual_return': '0.2235', 'mean_sharpe': '0.8462857142857144', 'median_sharpe': '1.1241', 'min_sharpe': '-0.537', 'sharpe_std': '0.8105305465796928', 'mean_max_drawdown': '-0.1812', 'worst_max_drawdown': '-0.3346', 'positive_return_folds': '5', 'positive_sharpe_folds': '5', 'mean_rank_ic': '0.04848571428571429', 'mean_rank_icir': '0.3470142857142857', 'sharpe_ttest_pvalue': '0.043050793480142284', 'return_ttest_pvalue': '0.049906413823839396', 'robust_score': '0.5836204409958681', 'pareto_front': 'True'}`

## Gates
- PASS `contract_complete`: CSV classified and required fields are present.
- PASS `rank_metric_policy`: Rank metric used: mean_sharpe.
- PASS `wfv_required_for_promotion`: Only WFV summary evidence can produce a promote decision.
- BLOCK `wfv_mean_sharpe`: mean_sharpe=0.8463
- BLOCK `wfv_min_sharpe`: min_sharpe=-0.537
- PASS `wfv_pvalue`: sharpe_ttest_pvalue=0.043050793480142284
- PASS `wfv_drawdown`: worst_max_drawdown=-0.3346

## Warnings
- No control CSV supplied; promotion decision is conservative.
