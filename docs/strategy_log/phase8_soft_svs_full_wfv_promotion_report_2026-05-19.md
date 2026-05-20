# Promotion Report: phase8_soft_svs_full_wfv_20260519

- Generated: 2026-05-19T14:13:08
- Decision: compare_next
- Promotion status: not_promotable
- Evidence level: wfv
- Recommendation: WFV evidence is mixed; keep as compare_next and inspect blocked gates before spending more budget.

## Result Contract
- Source: `optimization_results/walk_forward_phase8_soft_svs_full_wfv_20260519/walk_forward_summary.csv`
- Kind: walk_forward_summary
- Rows: 1
- Rank metric requested: mean_sharpe
- Rank metric used: mean_sharpe
- Benchmark aware: False

## Best Row
- Result: `{'train_universe': 'csi1000', 'eval_market': 'csi300', 'topk': '15', 'n_drop': '3', 'hold_thresh': '8', 'folds': '7', 'mean_annual_return': '0.146', 'median_annual_return': '0.1947', 'mean_sharpe': '0.6066142857142857', 'median_sharpe': '1.0906', 'min_sharpe': '-0.8828', 'sharpe_std': '0.8727170404278017', 'mean_max_drawdown': '-0.16194285714285714', 'worst_max_drawdown': '-0.2254', 'positive_return_folds': '5', 'positive_sharpe_folds': '5', 'mean_rank_ic': '0.04707142857142858', 'mean_rank_icir': '0.3308142857142857', 'sharpe_ttest_pvalue': '0.1395362290220241', 'return_ttest_pvalue': '0.11252802571327462', 'robust_score': '0.24369576550038477', 'pareto_front': 'True'}`

## Gates
- PASS `contract_complete`: CSV classified and required fields are present.
- PASS `rank_metric_policy`: Rank metric used: mean_sharpe.
- PASS `wfv_required_for_promotion`: Only WFV summary evidence can produce a promote decision.
- BLOCK `wfv_mean_sharpe`: mean_sharpe=0.6066
- BLOCK `wfv_min_sharpe`: min_sharpe=-0.8828
- PASS `wfv_pvalue`: sharpe_ttest_pvalue=0.1395362290220241
- PASS `wfv_drawdown`: worst_max_drawdown=-0.2254

## Warnings
- No control CSV supplied; promotion decision is conservative.
