# Phase8 Systematic Iteration Evidence Audit

## Objective
- Primary: `risk_transient_factor_attribution_v0` as a low-budget diagnostic layer for Phase7 attribution.
- Cheap diagnostic: `rejected_candidate_attribution_v0` feasibility inventory only.
- Guardrail: no trading rules, no full WFV, no data refresh, no live rebalance.

## Planner Run
- Run dir: `docs/strategy_log/agent_runs/phase8_risk_transient_system_iteration`
- Result: planner generated safe validation commands, but offline role templates reverted to Phase7 generic arms rather than transient-factor-specific implementation steps.
- Interpretation: useful as budget gate confirmation, insufficient as implementation evidence.

## Artifact Inventory
### backtest_csv
- none found

### optimization_csv
- none found

### strategy_log
- `/Users/weidian/code/quant_ex/docs/strategy_log/system_iteration_log.csv`
- `/Users/weidian/code/quant_ex/docs/strategy_log/strategy_iteration_log.csv`

### position_like
- `/Users/weidian/code/quant_ex/docs/strategy_log/knowledge_scout/ideas/20260518_frwkv-adaptive-periodic-position-branch-interact_frwkv-adaptive-periodic-position-branch-.md`

### trade_like
- none found

### reject_like
- none found

### signal_like
- `/Users/weidian/code/quant_ex/web/frontend/src/schemas/signals.ts`
- `/Users/weidian/code/quant_ex/web/frontend/src/api/signals.ts`
- `/Users/weidian/code/quant_ex/web/api/routers/signals.py`
- `/Users/weidian/code/quant_ex/test/test_web_console_signals.py`
- `/Users/weidian/code/quant_ex/test/test_signal_postprocess.py`
- `/Users/weidian/code/quant_ex/scripts/run_overlay_csi1000_balanced_signal.sh`
- `/Users/weidian/code/quant_ex/backtest/signal_diagnostics.py`
- `/Users/weidian/code/quant_ex/test/test_signal_diagnostics.py`
- `/Users/weidian/code/quant_ex/test/test_backtest_signal.py`

## Schema Observations
### `docs/strategy_log/system_iteration_log.csv`
- columns: iteration_date, iteration_num, focus_areas, changes_summary, baseline_scope, best_pre_sharpe, best_post_sharpe, best_pre_strategy, best_post_strategy, diagnostic_scores, decision, convergence_reason, diagnostic_report, strategy_iteration_ids, notes
- sample_rows: 3

### `docs/strategy_log/strategy_iteration_log.csv`
- columns: iteration_date, strategy_id, parent_strategy_id, stage, decision, config_path, model_path, train_universe, eval_market, backtest_start, backtest_end, topk, n_drop, hold_thresh, daily_transform, industry_neutralize, size_neutralize, stock_vs_sector_filter, svs_window, svs_keep_top_pct, max_position_pct, concentration_hard_limit, annual_return, sharpe, max_drawdown, rank_ic, result_source, notes, next_ablation
- sample_rows: 3

## Conclusions
- Current checked-in WFV summaries in `config/strategy_candidates.yaml` are enough for Phase7 candidate-level attribution fallback.
- The repo search did not surface fold-level residual return, holdings exposure matrix, or explicit accepted/rejected candidate event logs in a ready schema.
- Therefore `risk_transient_factor_attribution_v0` should not proceed directly to PCA/ICA implementation yet; the next valid iteration is a data-contract task: define and emit local-only attribution inputs.
- `rejected_candidate_attribution_v0` is blocked on event logging: generated candidates, accepted trades, rejected candidates, rejection reason, and forward return label are not present as a durable artifact.

## Next Systematic Iteration Recommendation
- Primary next task: implement `attribution_input_contract_v0` that detects/exports three disabled-by-default local artifacts: portfolio/position returns by date, strategy residual series vs benchmark/control, and candidate decision events if available.
- Cheap diagnostic: add tests that fail clearly when required columns are missing, rather than silently falling back to candidate summary.
- Kill/stop condition: if required source data cannot be reconstructed from existing outputs without running full WFV or data refresh, stop and request approval for the narrowest data-generation command.
