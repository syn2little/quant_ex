# Promotion Report: phase8_soft_svs_narrow_wfv_20260519

- Generated: 2026-05-19T13:46:37
- Decision: promote
- Promotion status: promotable
- Evidence level: wfv
- Recommendation: WFV-grade evidence clears the configured gates; review manually before updating strategy candidates.

## Result Contract
- Source: `optimization_results/walk_forward_phase8_soft_svs_narrow_wfv_20260519/walk_forward_summary.csv`
- Kind: walk_forward_summary
- Rows: 1
- Rank metric requested: mean_sharpe
- Rank metric used: mean_sharpe
- Benchmark aware: False

## Best Row
- Result: `{'train_universe': 'csi1000', 'eval_market': 'csi300', 'topk': '15', 'n_drop': '3', 'hold_thresh': '8', 'folds': '3', 'mean_annual_return': '0.26356666666666667', 'median_annual_return': '0.2033', 'mean_sharpe': '1.2863', 'median_sharpe': '1.2871', 'min_sharpe': '1.0906', 'sharpe_std': '0.15946278562724286', 'mean_max_drawdown': '-0.10306666666666668', 'worst_max_drawdown': '-0.1401', 'positive_return_folds': '3', 'positive_sharpe_folds': '3', 'mean_rank_ic': '0.04806666666666667', 'mean_rank_icir': '0.30219999999999997', 'sharpe_ttest_pvalue': '0.007596843960864178', 'return_ttest_pvalue': '0.05517351044951422', 'robust_score': '1.5746886071863786', 'pareto_front': 'True'}`

## Gates
- PASS `contract_complete`: CSV classified and required fields are present.
- PASS `rank_metric_policy`: Rank metric used: mean_sharpe.
- PASS `wfv_required_for_promotion`: Only WFV summary evidence can produce a promote decision.
- PASS `wfv_mean_sharpe`: mean_sharpe=1.2863
- PASS `wfv_min_sharpe`: min_sharpe=1.0906
- PASS `wfv_pvalue`: sharpe_ttest_pvalue=0.007596843960864178
- PASS `wfv_drawdown`: worst_max_drawdown=-0.1401

## Warnings
- No control CSV supplied; promotion decision is conservative.
