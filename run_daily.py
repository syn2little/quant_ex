#!/usr/bin/env python3
"""
每日信号生成脚本 — 收盘后运行，推送次日持仓建议。

用法:
    python run_daily.py                        # 使用默认配置
    python run_daily.py --config my.yaml       # 自定义配置文件
    python run_daily.py --dry-run              # 不推送通知，只打印
    python run_daily.py --account 500000       # 指定账户资金
    python run_daily.py --positions SH600000:500,SZ000001:300   # 当前持仓
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime
from pathlib import Path

# 确保包路径正确
sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_ex.utils.logger import setup_logger
from quant_ex.utils.config import load_config
from quant_ex.utils.qlib_utils import load_recorder_model
from quant_ex.data.loader import DataLoader
from quant_ex.data.universe import UniverseFilter
from quant_ex.data.sector import SectorDataProvider
from quant_ex.signals.generator import SignalGenerator
from quant_ex.signals.postprocess import postprocess_requires_price_data
from quant_ex.notify.pusher import NotificationPusher

logger = setup_logger("run_daily")


def _check_concentration(data: dict, config: dict) -> None:
    """Log warnings when any single position exceeds the concentration limit."""
    positions = data.get("target_positions", {})
    if not positions:
        return
    account = data.get("account_value", 1)
    port_cfg = config.get("strategy", {}).get("portfolio", {})
    max_pct = port_cfg.get("max_position_pct", 0.25)
    hard_limit = port_cfg.get("concentration_hard_limit", None)

    weights = {
        inst: info["target_value"] / account
        for inst, info in positions.items()
        if account > 0
    }
    total_invested = sum(weights.values())
    n = len(weights)

    for inst, w in sorted(weights.items(), key=lambda x: -x[1]):
        if w > max_pct:
            logger.warning(
                "集中度警告: %s 权重 %.1f%% 超过上限 %.1f%%", inst, w * 100, max_pct * 100
            )
        if hard_limit and w > hard_limit:
            logger.error(
                "集中度超限 [HARD LIMIT]: %s 权重 %.1f%% 超过硬上限 %.1f%%",
                inst, w * 100, hard_limit * 100,
            )

    if n > 0:
        herfindahl = sum(w ** 2 for w in weights.values())
        effective_n = 1.0 / herfindahl if herfindahl > 0 else n
        logger.info(
            "集中度报告: %d 持仓, 有效分散数=%.1f, 总投入=%.1f%%",
            n, effective_n, total_invested * 100,
        )
        if effective_n < n * 0.5:
            logger.warning(
                "集中度警告: 有效分散数 %.1f 低于持仓数 %d 的 50%%，组合过度集中",
                effective_n, n,
            )


def parse_positions(s: str) -> dict:
    """Parse 'SH600000:500,SZ000001:300' → {'SH600000': 500, ...}"""
    if not s:
        return {}
    result = {}
    for pair in s.split(","):
        inst, shares = pair.strip().split(":")
        result[inst.strip()] = float(shares.strip())
    return result


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
    logger.info(f"加载模型: {exp_cfg.get('name')} / {rid}")
    return load_recorder_model(exp_cfg.get("name", "tutorial_exp"), rid)


def main(
    config_path: str = None,
    model_path: str = None,
    dry_run: bool = False,
    account: float = None,
    current_positions: dict = None,
):
    config = load_config(config_path)
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"=== 每日选股信号 {today} ===")

    # ── 初始化组件 ────────────────────────────────────────────────────────────
    data_loader = DataLoader(config)
    universe_filter = UniverseFilter(config.get("strategy", {}))
    sector_provider = SectorDataProvider(config)
    pusher = NotificationPusher(config)

    # ── 刷新外部数据缓存 ────────────────────────────────────────────────────────
    try:
        from quant_ex.data.fetchers import (
            NorthboundFetcher, FinancialFetcher, PledgeFetcher,
            MarginTradeFetcher, InsiderTradeFetcher, AnalystForecastFetcher,
            ShareholderCountFetcher, DividendFetcher, ValuationFetcher,
            BalanceSheetFetcher, EarningsGuidanceFetcher, InstitutionalHoldFetcher,
            RepurchaseFetcher, InstitutionalVisitFetcher,
        )
        feat_cfg = config.get("model", {}).get("features", {})
        factor_names = [f.get("name") for f in feat_cfg.get("factors", []) if f.get("name")]

        _FETCHER_MAP = {
            "northbound": (NorthboundFetcher, "./cache/northbound", 1),
            "fundamental": (FinancialFetcher, "./cache/financial", 7),
            "pledge": (PledgeFetcher, "./cache/pledge", 1),
            "margin": (MarginTradeFetcher, "./cache/margin", 1),
            "insider": (InsiderTradeFetcher, "./cache/insider", 1),
            "analyst": (AnalystForecastFetcher, "./cache/analyst", 3),
            "shareholder": (ShareholderCountFetcher, "./cache/shareholder", 30),
            "dividend": (DividendFetcher, "./cache/dividend", 30),
            "valuation": (ValuationFetcher, "./cache/valuation", 1),
            "balance_sheet": (BalanceSheetFetcher, "./cache/balance_sheet", 30),
            "earnings_guidance": (EarningsGuidanceFetcher, "./cache/earnings_guidance", 30),
            "institutional": (InstitutionalHoldFetcher, "./cache/institutional", 30),
            "repurchase": (RepurchaseFetcher, "./cache/repurchase", 1),
            "visit": (InstitutionalVisitFetcher, "./cache/visit", 7),
        }

        for fname in factor_names:
            if fname in _FETCHER_MAP:
                cls, cache_dir, ttl = _FETCHER_MAP[fname]
                try:
                    cls(cache_dir=cache_dir, cache_ttl_days=ttl).refresh_cache([])
                    logger.info(f"{fname} 缓存已刷新")
                except Exception as e:
                    logger.warning(f"{fname} 缓存刷新失败: {e}")
    except Exception as exc:
        logger.warning(f"外部数据缓存刷新跳过: {exc}")

    # ── 加载模型 ──────────────────────────────────────────────────────────────
    model = _load_model(config, model_path)

    # ── 构建数据集 ────────────────────────────────────────────────────────────
    tcfg = config.get("training", {})
    dataset = data_loader.build_dataset(
        segments={
            "train": (tcfg.get("fit_start", "2015-01-01"), tcfg.get("fit_end", "2021-12-31")),
            "valid": (tcfg.get("valid_start", "2022-01-01"), tcfg.get("valid_end", "2023-12-31")),
            "test":  (tcfg.get("test_start", "2024-01-01"), today),
        },
        instruments=config.get("market", {}).get("name", "csi300"),
    )

    # ── 生成信号 ──────────────────────────────────────────────────────────────
    acct = account or config.get("backtest", {}).get("account", 1_000_000)

    # Pre-load price data once so SignalGenerator.generate() can reuse it
    # instead of loading again internally (avoids 2-3× redundant qlib queries)
    instruments = config.get("market", {}).get("name", "csi300")
    if universe_filter.requires_price_data() or postprocess_requires_price_data(config):
        tcfg2 = config.get("training", {})
        price_start = tcfg2.get("test_start", "2024-01-01")
        price_data = data_loader.load_price_data(
            instruments=instruments,
            start_time=price_start,
            end_time=today,
        )
        logger.info(f"Pre-loaded price_data: {len(price_data)} rows")
    else:
        price_data = None

    # ── Regime-aware parameter switching (optional) ────────────────────────────
    try:
        from quant_ex.strategy.regime_switch import RegimeStrategySwitch, apply_overlay_gating

        regime_switch = RegimeStrategySwitch.from_config(config)
        if regime_switch is not None and price_data is not None:
            regime_label = regime_switch.detect_regime(price_data)
            base_params = config.get("strategy", {}).get("topk_dropout", {})
            adjusted = regime_switch.adjust(base_params, regime_label)
            config.setdefault("strategy", {}).setdefault("topk_dropout", {}).update(
                {k: adjusted[k] for k in ("topk", "n_drop", "hold_thresh") if k in adjusted}
            )
            # Gate overlay (stock_vs_sector_filter) by regime
            apply_overlay_gating(config, adjusted.get("overlay_enabled", True))
    except Exception as exc:
        logger.warning("Regime switch integration skipped: %s", exc)

    sig_gen = SignalGenerator(config, data_loader, universe_filter, sector_provider)
    data = sig_gen.generate(
        model=model,
        dataset=dataset,
        current_positions=current_positions or {},
        account_value=acct,
        trade_date=today,
        price_data=price_data,
    )

    report = sig_gen.format_report(data)

    # ── 集中度风险检查 ────────────────────────────────────────────────────────
    _check_concentration(data, config)

    print(report)

    # ── 保存到文件 ────────────────────────────────────────────────────────────
    sig_dir = Path(config.get("paths", {}).get("signal_dir", "./signals"))
    sig_dir.mkdir(parents=True, exist_ok=True)
    out = sig_dir / f"signal_{today}.txt"
    out.write_text(report, encoding="utf-8")
    logger.info(f"信号已保存 → {out}")

    # ── 推送通知 ──────────────────────────────────────────────────────────────
    if not dry_run:
        results = pusher.send(f"量化选股信号 {today}", report)
        for ch, ok in results.items():
            logger.info(f"  {'✅' if ok else '❌'} {ch}")
    else:
        logger.info("dry-run 模式，跳过通知推送")

    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="每日量化选股信号生成")
    parser.add_argument("--config",      type=str, default=None)
    parser.add_argument("--model-path",  type=str, default=None,
                        help="直接加载 .pkl 模型文件，例如 models/lgbm_sector_full_20260308_143021.pkl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--account", type=float, default=None)
    parser.add_argument(
        "--positions",
        type=str,
        default="",
        help="当前持仓，格式: 'SH600000:500,SZ000001:300'",
    )
    args = parser.parse_args()
    main(
        config_path=args.config,
        model_path=args.model_path,
        dry_run=args.dry_run,
        account=args.account,
        current_positions=parse_positions(args.positions),
    )
