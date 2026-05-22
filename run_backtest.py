#!/usr/bin/env python3
"""
批量回测 & 参数网格搜索脚本。

用法:
    # 使用默认网格搜索
    python run_backtest.py

    # 自定义参数范围
    python run_backtest.py --topk 5,10,15,20 --n-drop 1,3,5 --hold-thresh 3,5,10

    # 使用 AI Agent 自动迭代优化（需要 ANTHROPIC_API_KEY）
    python run_backtest.py --optimize --n-iters 3

    # 指定回测区间
    python run_backtest.py --start 2024-01-01 --end 2025-12-31
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# PYTHONHASHSEED must be set before the interpreter starts to take effect.
# Skip re-exec when running as a seed-worker subprocess (grid_search multi-seed),
# because the worker already has PYTHONHASHSEED set to its target seed value.
if (os.environ.get("PYTHONHASHSEED") != "42"
        and os.environ.get("_QUANT_EX_SEED_WORKER") != "1"):
    os.environ["PYTHONHASHSEED"] = "42"
    os.execv(sys.executable, [sys.executable] + sys.argv)

sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_ex.utils.logger import setup_logger
from quant_ex.utils.config import load_config
from quant_ex.utils.qlib_utils import load_recorder_model
from quant_ex.data.loader import DataLoader
from quant_ex.data.sector import SectorDataProvider
from quant_ex.data.universe import UniverseFilter
from quant_ex.backtest.engine import BacktestEngine
from quant_ex.backtest.grid_search import GridSearchBacktest
from quant_ex.backtest.metrics import format_metrics
from quant_ex.backtest.signal_diagnostics import compute_signal_ic
from quant_ex.agent.strategy_iteration.attribution_input_export import export_attribution_inputs as write_attribution_inputs
from quant_ex.signals.postprocess import postprocess_requires_price_data, postprocess_signal
from quant_ex.strategy.regime_switch import apply_overlay_gating

logger = setup_logger("run_backtest")


def parse_ints(s: str) -> list:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def parse_strings(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()]


def _load_model(config: dict, model_path: str = None):
    """Load model from .pkl path (custom) or MLflow recorder (qlib-native)."""
    if model_path:
        from quant_ex.models.base import BaseAlphaModel
        logger.info(f"加载模型: {model_path}")
        return BaseAlphaModel.load(model_path)

    exp_cfg = config.get("experiment", {})
    rid = exp_cfg.get("latest_recorder_id", "")
    if not rid:
        logger.error(
            "未配置模型路径。请使用 --model-path 指定 .pkl 文件，\n"
            "或在 config/base.yaml 中填写 experiment.latest_recorder_id"
        )
        sys.exit(1)
    return load_recorder_model(exp_cfg.get("name", "tutorial_exp"), rid)


def main(
    config_path: str = None,
    model_path: str = None,
    topk_vals: list = None,
    n_drop_vals: list = None,
    hold_thresh_vals: list = None,
    start: str = None,
    end: str = None,
    optimize: bool = False,
    n_iters: int = 3,
    multi_seed: bool = False,
    market: str = None,
    markets: list = None,
    explore_markets: bool = False,
    grid_workers: int = -1,
    output_csv: str = None,
    benchmark: str = None,
    deal_price: str = None,
    open_cost: float = None,
    close_cost: float = None,
    min_cost: float = None,
    slippage_sensitivity: bool = False,
    slippage_multipliers: list = None,
    export_attribution_inputs: bool = False,
    export_risk_cap_diagnostics: bool = False,
    run_id: str = None,
):
    config = load_config(config_path)
    today = datetime.now().strftime("%Y-%m-%d")

    logger.info("=== 批量回测 ===")

    # ── 加载模型 ──────────────────────────────────────────────────────────────
    model = _load_model(config, model_path)

    data_loader = DataLoader(config)
    universe_filter = UniverseFilter(config.get("strategy", {}))
    post_cfg = config.get("signal", {}).get("postprocess", {})
    sector_provider = (
        SectorDataProvider(config)
        if (
            post_cfg.get("industry_neutralize", False)
            or post_cfg.get("stock_vs_sector_filter", {}).get("enabled", False)
        )
        else None
    )
    tcfg = config.get("training", {})
    market_cfg = config.get("market", {})
    base_market = market or market_cfg.get("name", "csi300")
    if explore_markets:
        eval_markets = markets or market_cfg.get("candidates") or [base_market]
    else:
        eval_markets = markets or [base_market]
    eval_markets = list(dict.fromkeys(eval_markets))

    if optimize and len(eval_markets) > 1:
        logger.warning(
            "--optimize 仅支持单个候选池，本次使用第一个: %s",
            eval_markets[0],
        )
        eval_markets = eval_markets[:1]

    # ── Regime-aware parameter switching (optional) ────────────────────────────
    try:
        from quant_ex.strategy.regime_switch import RegimeStrategySwitch

        regime_switch = RegimeStrategySwitch.from_config(config)
        if regime_switch is not None:
            regime_market = base_market
            regime_price = data_loader.load_price_data(
                instruments=regime_market,
                start_time=tcfg.get("test_start", "2024-01-01"),
                end_time=end or today,
            )
            regime_label = regime_switch.detect_regime(regime_price)
            base_params = config.get("strategy", {}).get("topk_dropout", {})
            adjusted = regime_switch.adjust(base_params, regime_label)
            config.setdefault("strategy", {}).setdefault("topk_dropout", {}).update(
                {k: adjusted[k] for k in ("topk", "n_drop", "hold_thresh") if k in adjusted}
            )
            # Gate overlay (stock_vs_sector_filter) by regime
            apply_overlay_gating(config, adjusted.get("overlay_enabled", True))
    except Exception as exc:
        logger.warning("Regime switch integration skipped: %s", exc)

    # ── 构建参数网格 ──────────────────────────────────────────────────────────
    param_grid = {
        "topk":        topk_vals        or [5, 10, 15, 20],
        "n_drop":      n_drop_vals      or [1, 3, 5],
        "hold_thresh": hold_thresh_vals or [3, 5, 10],
    }

    engine = BacktestEngine(config)
    out_dir = Path(config.get("paths", {}).get("backtest_results_dir", "./backtest_results"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 执行 ──────────────────────────────────────────────────────────────────
    if optimize:
        pred = _predict_for_market(
            model=model,
            data_loader=data_loader,
            universe_filter=universe_filter,
            config=config,
            instruments=eval_markets[0],
            sector_provider=sector_provider,
            start=start,
            end=end,
            today=today,
        )
        from quant_ex.agent.auto_optimizer import AutoOptimizer
        logger.info("启动 AI 优化 Agent …")
        optimizer = AutoOptimizer()
        records = optimizer.run_loop(
            backtest_engine=engine,
            pred=pred,
            initial_grid=param_grid,
            n_iterations=n_iters,
            save_dir=str(out_dir),
        )
        print("\n=== 优化汇总 ===")
        for r in records:
            print(f"  第{r['iteration']}轮最优: {r.get('best_params', {})}")
    else:
        result_frames = []
        for eval_market in eval_markets:
            logger.info("=== 回测候选池: %s ===", eval_market)
            pred = _predict_for_market(
                model=model,
                data_loader=data_loader,
                universe_filter=universe_filter,
                config=config,
                instruments=eval_market,
                sector_provider=sector_provider,
                start=start,
                end=end,
                today=today,
            )

            searcher = GridSearchBacktest(engine, pred, config)
            market_df = searcher.run(
                param_grid=param_grid,
                start_time=start,
                end_time=end,
                multi_seed=multi_seed,
                n_jobs=grid_workers,
                benchmark=benchmark,
                deal_price=deal_price,
                open_cost=open_cost,
                close_cost=close_cost,
                min_cost=min_cost,
            )
            diagnostics = _signal_diagnostics_for_market(
                data_loader=data_loader,
                pred=pred,
                config=config,
                instruments=eval_market,
                start=start,
                end=end,
                today=today,
            )
            market_df.insert(0, "market", eval_market)
            for key, value in diagnostics.items():
                market_df[key] = value
            result_frames.append(market_df)

        results_df = (
            pd.concat(result_frames, ignore_index=True)
            if result_frames else pd.DataFrame()
        )
        rank_metric = config.get("backtest", {}).get("rank_metric", "information_ratio")
        if rank_metric not in results_df.columns:
            rank_metric = "sharpe"
        if rank_metric in results_df.columns:
            sort_cols = [rank_metric]
            ascending = [False]
            if "sharpe_std" in results_df.columns:
                sort_cols.append("sharpe_std")
                ascending.append(True)
            results_df = results_df.sort_values(
                sort_cols,
                ascending=ascending,
            ).reset_index(drop=True)

        print("\n=== 网格搜索结果 ===")
        print(results_df.to_string())

        best = GridSearchBacktest.best_params(results_df)
        print(f"\n✅ 最优参数: {best}")

        csv_path = Path(output_csv) if output_csv else out_dir / f"grid_{today}.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        results_df.to_csv(csv_path, index=False)
        logger.info(f"结果已保存 → {csv_path}")

        # 单独展示最优参数的详细指标
        if not results_df.empty and "sharpe" in results_df.columns:
            top_row = results_df.iloc[0]
            m = {k: top_row[k] for k in
                 ["cum_return","annual_return","annual_vol","sharpe",
                  "max_drawdown","calmar","win_rate","sortino","n_days",
                  "excess_annual_return","information_ratio","tracking_error","beta","alpha"]
                 if k in top_row}
            print("\n最优参数详细指标:")
            print(format_metrics(m))

        pred_by_market = None
        if (slippage_sensitivity or export_attribution_inputs) and not results_df.empty:
            pred_by_market = {
                m: _predict_for_market(
                    model=model,
                    data_loader=data_loader,
                    universe_filter=universe_filter,
                    config=config,
                    instruments=m,
                    sector_provider=sector_provider,
                    start=start,
                    end=end,
                    today=today,
                )
                for m in eval_markets
            }

        # CAP-13: Slippage sensitivity analysis
        if slippage_sensitivity and not results_df.empty:
            best_params = GridSearchBacktest.best_params(results_df)
            _run_slippage_sensitivity(
                engine=engine,
                pred_by_market=pred_by_market,
                best_params=best_params,
                config=config,
                start=start,
                end=end,
                multipliers=slippage_multipliers or [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
            )

        if export_attribution_inputs and not results_df.empty:
            _export_best_attribution_inputs(
                engine=engine,
                pred_by_market=pred_by_market,
                data_loader=data_loader,
                best_params=GridSearchBacktest.best_params(results_df),
                config=config,
                output_dir=out_dir / "agent_runs",
                run_id=run_id or f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                start=start,
                end=end,
                today=today,
                market=eval_markets[0] if eval_markets else base_market,
                benchmark=benchmark,
                deal_price=deal_price,
                open_cost=open_cost,
                close_cost=close_cost,
                min_cost=min_cost,
                export_risk_cap_diagnostics=export_risk_cap_diagnostics,
            )


def _export_best_attribution_inputs(
    engine,
    pred_by_market: dict,
    data_loader: DataLoader,
    best_params: dict,
    config: dict,
    output_dir: Path,
    run_id: str,
    start: str = None,
    end: str = None,
    today: str = None,
    market: str = None,
    benchmark: str = None,
    deal_price: str = None,
    open_cost: float = None,
    close_cost: float = None,
    min_cost: float = None,
    export_risk_cap_diagnostics: bool = False,
) -> dict[str, Path]:
    """Run the best local backtest once more and export agent attribution contracts."""

    if not pred_by_market:
        return {}
    market = market or next(iter(pred_by_market))
    pred = pred_by_market.get(market) if market in pred_by_market else next(iter(pred_by_market.values()))
    strategy_params = {
        "topk": int(best_params.get("topk", 10)),
        "n_drop": int(best_params.get("n_drop", 3)),
        "hold_thresh": int(best_params.get("hold_thresh", 5)),
    }
    backtest_kwargs = {
        key: value
        for key, value in {
            "benchmark": benchmark,
            "deal_price": deal_price,
            "open_cost": open_cost,
            "close_cost": close_cost,
            "min_cost": min_cost,
        }.items()
        if value is not None
    }
    report, _ = engine.run(
        pred=pred,
        strategy_params=strategy_params,
        start_time=start,
        end_time=end,
        **backtest_kwargs,
    )
    tcfg = config.get("training", {})
    price_data = data_loader.load_price_data(
        instruments=market,
        start_time=start or tcfg.get("test_start", "2024-01-01"),
        end_time=end or today,
    )
    written = write_attribution_inputs(
        run_id=run_id,
        output_dir=output_dir,
        report=report,
        signal=pred,
        price_data=price_data,
        topk=strategy_params["topk"],
        export_risk_cap_diagnostics=export_risk_cap_diagnostics,
    )
    logger.info("Attribution inputs exported → %s", ", ".join(str(path) for path in written.values()))
    return written


def _run_slippage_sensitivity(
    engine,
    pred_by_market: dict,
    best_params: dict,
    config: dict,
    start: str = None,
    end: str = None,
    multipliers: list = None,
):
    """CAP-13: Run the best parameter set under varying transaction cost assumptions.

    Prints a table of Sharpe / annual_return vs cost multiplier, and reports
    the approximate break-even cost multiplier (where mean Sharpe crosses 0).

    Parameters
    ----------
    engine        : BacktestEngine instance
    pred_by_market: dict of market→pred Series
    best_params   : dict from GridSearchBacktest.best_params() e.g. {"topk":10,"n_drop":3,...}
    config        : merged config dict
    multipliers   : list of floats, each applied to base open_cost and close_cost
    """
    if multipliers is None:
        multipliers = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]

    from quant_ex.backtest.metrics import compute_metrics as _compute_metrics

    bt_cfg = config.get("backtest", {})
    base_open  = bt_cfg.get("open_cost",  0.0005)
    base_close = bt_cfg.get("close_cost", 0.0015)
    base_min = bt_cfg.get("min_cost", 5)

    strategy_params = {
        "topk":        best_params.get("topk", 10),
        "n_drop":      best_params.get("n_drop", 3),
        "hold_thresh": best_params.get("hold_thresh", 5),
    }

    rows = []
    for mult in multipliers:
        sharpe_list, ret_list = [], []
        for market, pred in pred_by_market.items():
            try:
                report, _ = engine.run(
                    pred=pred,
                    strategy_params=strategy_params,
                    start_time=start,
                    end_time=end,
                    open_cost=base_open * mult,
                    close_cost=base_close * mult,
                    min_cost=base_min * mult,
                )
                m = _compute_metrics(report)
                sharpe_list.append(m.get("sharpe", float("nan")))
                ret_list.append(m.get("annual_return", float("nan")))
            except Exception as exc:
                logger.warning("Slippage sensitivity backtest failed (mult=%.2f): %s", mult, exc)

        import numpy as np
        rows.append({
            "cost_multiplier": mult,
            "open_cost":  round(base_open  * mult, 6),
            "close_cost": round(base_close * mult, 6),
            "min_cost": round(base_min * mult, 4),
            "mean_sharpe": round(float(np.nanmean(sharpe_list)), 4) if sharpe_list else float("nan"),
            "mean_annual_return": round(float(np.nanmean(ret_list)), 4)   if ret_list   else float("nan"),
        })

    df = pd.DataFrame(rows)
    print("\n=== 滑点敏感性分析 (Slippage Sensitivity) ===")
    print(f"  基准参数: {strategy_params}")
    print(f"  基础成本: open={base_open:.4f}  close={base_close:.4f}  min={base_min:.2f}")
    print()
    print(df.to_string(index=False))

    # Break-even estimation by linear interpolation
    valid = df.dropna(subset=["mean_sharpe"])
    break_even = None
    for i in range(len(valid) - 1):
        s0 = valid.iloc[i]["mean_sharpe"]
        s1 = valid.iloc[i + 1]["mean_sharpe"]
        if s0 >= 0 >= s1 or s1 >= 0 >= s0:
            m0 = valid.iloc[i]["cost_multiplier"]
            m1 = valid.iloc[i + 1]["cost_multiplier"]
            # linear interp: mult where sharpe = 0
            be = m0 + (0 - s0) * (m1 - m0) / (s1 - s0) if s1 != s0 else m0
            break_even = round(be, 3)
            break

    if break_even is not None:
        print(f"\n  ⚠  Break-even cost multiplier ≈ {break_even}×  "
              f"(open={base_open * break_even:.5f}, close={base_close * break_even:.5f})")
    else:
        # Check if always positive or always negative
        if valid["mean_sharpe"].min() > 0:
            print("\n  ✓ Sharpe 在所有成本假设下均为正，策略对交易成本具有较强鲁棒性")
        else:
            print("\n  ✗ Sharpe 在基准成本下即为负，信号质量存疑")


def _predict_for_market(
    model,
    data_loader: DataLoader,
    universe_filter: UniverseFilter,
    config: dict,
    instruments: str,
    sector_provider: SectorDataProvider = None,
    start: str = None,
    end: str = None,
    today: str = None,
):
    """Build an evaluation dataset and prediction signal for one candidate pool."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    tcfg = config.get("training", {})
    segments = {
        "train": (tcfg.get("fit_start", "2015-01-01"), tcfg.get("fit_end", "2021-12-31")),
        "valid": (tcfg.get("valid_start", "2022-01-01"), tcfg.get("valid_end", "2023-12-31")),
        "test":  (start or tcfg.get("test_start", "2024-01-01"), end or today),
    }

    dataset = data_loader.build_dataset(segments=segments, instruments=instruments)

    price_data = None
    needs_full_price_data = (
        getattr(model, "factor_pipeline", None) is not None
        or postprocess_requires_price_data(config)
    )

    if needs_full_price_data:
        price_data = data_loader.load_price_data(
            instruments=instruments,
            start_time=tcfg.get("fit_start", "2015-01-01"),
            end_time=end or today,
        )

    if getattr(model, "factor_pipeline", None) is not None:
        logger.info(
            "模型含有 factor_pipeline，为 %s 重新计算额外因子 …",
            instruments,
        )
        model.refresh_extra_factors(price_data)

    pred = model.predict(dataset, segment="test")
    if universe_filter.requires_price_data():
        if price_data is None:
            price_data = data_loader.load_price_data(
                instruments=instruments,
                start_time=start or tcfg.get("test_start", "2024-01-01"),
                end_time=end or today,
            )
        pred = universe_filter.filter(pred, price_data=price_data)
    else:
        pred = universe_filter.filter(pred)

    sector_map = sector_provider.get_map() if sector_provider is not None else None
    return postprocess_signal(
        pred,
        config=config,
        sector_map=sector_map,
        price_data=price_data,
    )


def _signal_diagnostics_for_market(
    data_loader: DataLoader,
    pred,
    config: dict,
    instruments: str,
    start: str = None,
    end: str = None,
    today: str = None,
) -> dict:
    diag_cfg = config.get("signal", {}).get("diagnostics", {})
    if not diag_cfg.get("enabled", True):
        return {}

    tcfg = config.get("training", {})
    today = today or datetime.now().strftime("%Y-%m-%d")
    price_data = data_loader.load_price_data(
        instruments=instruments,
        start_time=start or tcfg.get("test_start", "2024-01-01"),
        end_time=end or today,
    )
    return compute_signal_ic(
        pred=pred,
        price_data=price_data,
        horizon=int(diag_cfg.get("horizon", 5)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="量化策略批量回测")
    parser.add_argument("--config",      type=str, default=None)
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="直接加载 .pkl 模型文件，例如 models/lgbm_baseline_20260308_143021.pkl",
    )
    parser.add_argument("--topk",        type=str, default=None, help="e.g. 5,10,15")
    parser.add_argument("--n-drop",      type=str, default=None)
    parser.add_argument("--hold-thresh", type=str, default=None)
    parser.add_argument("--start",       type=str, default=None)
    parser.add_argument("--end",         type=str, default=None)
    parser.add_argument("--optimize",    action="store_true", help="使用 AI Agent 迭代优化")
    parser.add_argument("--n-iters",     type=int, default=3)
    parser.add_argument(
        "--seeds",
        action="store_true",
        help="多 seed 评估：用 5 个内置 seed 跑每个参数组合并取平均，结果更稳健",
    )
    parser.add_argument("--market",      type=str, default=None,
                        help="单个回测候选池，例如 csi300 | csi500 | all")
    parser.add_argument("--markets",     type=str, default=None,
                        help="多个回测候选池，例如 csi300,csi500,csi1000,all")
    parser.add_argument("--explore-markets", action="store_true",
                        help="使用 config/base.yaml 中 market.candidates 批量探索候选池")
    parser.add_argument(
        "--grid-workers",
        type=int,
        default=-1,
        help="网格搜索并行进程数，-1 表示使用全部 CPU 核心，1 表示串行（默认: -1）",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="指定 grid search 结果输出 CSV 路径（默认: backtest_results/grid_{date}.csv）。"
             "walk-forward 模式下用此参数隔离每折结果，避免并行竞争。",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default=None,
        help="回测基准代码，例如 SH000300 或 SH000905（默认读取配置）。",
    )
    parser.add_argument(
        "--deal-price",
        type=str,
        default=None,
        choices=["open", "close"],
        help="成交价格字段（默认读取配置，通常为 close）。",
    )
    parser.add_argument(
        "--open-cost",
        type=float,
        default=None,
        help="买入交易成本，覆盖配置 backtest.open_cost。",
    )
    parser.add_argument(
        "--close-cost",
        type=float,
        default=None,
        help="卖出交易成本，覆盖配置 backtest.close_cost。",
    )
    parser.add_argument(
        "--min-cost",
        type=float,
        default=None,
        help="最低交易费用，覆盖配置 backtest.min_cost。",
    )
    parser.add_argument(
        "--slippage-sensitivity",
        action="store_true",
        help="滑点敏感性分析：用最优参数在不同交易成本倍数下测试 Sharpe 变化（CAP-13）",
    )
    parser.add_argument(
        "--slippage-multipliers",
        type=str,
        default=None,
        help="滑点倍数列表（逗号分隔），默认 0,0.25,0.5,1,1.5,2,3,5",
    )
    parser.add_argument(
        "--export-attribution-inputs",
        action="store_true",
        help="可选导出 agent attribution 输入契约文件到 backtest_results/agent_runs（默认关闭）。",
    )
    parser.add_argument(
        "--export-risk-cap-diagnostics",
        action="store_true",
        help="随 attribution inputs 额外导出 diagnostic-only risk-cap counterfactual 文件（默认关闭）。",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="导出 attribution inputs 时使用的 run id（默认自动生成 backtest_{timestamp}）。",
    )
    args = parser.parse_args()
    if args.export_risk_cap_diagnostics and not args.export_attribution_inputs:
        parser.error("--export-risk-cap-diagnostics requires --export-attribution-inputs")

    main(
        config_path=args.config,
        model_path=args.model_path,
        topk_vals=parse_ints(args.topk) if args.topk else None,
        n_drop_vals=parse_ints(args.n_drop) if args.n_drop else None,
        hold_thresh_vals=parse_ints(args.hold_thresh) if args.hold_thresh else None,
        start=args.start,
        end=args.end,
        optimize=args.optimize,
        n_iters=args.n_iters,
        multi_seed=args.seeds,
        market=args.market,
        markets=parse_strings(args.markets) if args.markets else None,
        explore_markets=args.explore_markets,
        grid_workers=args.grid_workers,
        output_csv=args.output_csv,
        benchmark=args.benchmark,
        deal_price=args.deal_price,
        open_cost=args.open_cost,
        close_cost=args.close_cost,
        min_cost=args.min_cost,
        slippage_sensitivity=args.slippage_sensitivity,
        slippage_multipliers=(
            [float(x) for x in args.slippage_multipliers.split(",")]
            if args.slippage_multipliers else None
        ),
        export_attribution_inputs=args.export_attribution_inputs,
        export_risk_cap_diagnostics=args.export_risk_cap_diagnostics,
        run_id=args.run_id,
    )
