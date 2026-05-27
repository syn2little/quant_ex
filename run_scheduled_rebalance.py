#!/usr/bin/env python3
"""After-close qlib update, backtest replay and Bark rebalance notification."""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT.parent))

from quant_ex.backtest.engine import BacktestEngine
from quant_ex.data.loader import DataLoader
from quant_ex.data.sector import SectorDataProvider
from quant_ex.data.universe import UniverseFilter
from quant_ex.data.utils import load_stock_names
from quant_ex.notify.pusher import NotificationPusher
from quant_ex.signals.postprocess import postprocess_requires_price_data, postprocess_signal
from quant_ex.strategy.regime_switch import apply_overlay_gating
from quant_ex.utils.config import load_config
from quant_ex.utils.logger import setup_logger
from quant_ex.utils.qlib_utils import load_recorder_model

logger = setup_logger("run_scheduled_rebalance")

SIGNAL_DATE_START_ALIASES = {"signal_date", "trade_date", "today"}
PREVIOUS_DATE_START_ALIASES = {"previous_trade_date", "previous_trading_day", "yesterday"}


@dataclass
class RebalanceAction:
    action: str
    instrument: str
    shares: float
    price: float
    value: float


def _resolve_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=str, default=None, help="Optional YAML config override.")
    parser.add_argument("--model-path", type=str, default=None, help="Override daily_rebalance.model_path.")
    parser.add_argument("--start-date", type=str, default=None, help="Fixed replay start date, e.g. 2024-01-01.")
    parser.add_argument("--today", type=str, default=None, help="Override current date for testing.")
    parser.add_argument("--market", type=str, default=None, help="Default: daily_rebalance.market or csi1000.")
    parser.add_argument("--topk", type=int, default=None)
    parser.add_argument("--n-drop", type=int, default=None)
    parser.add_argument("--hold-thresh", type=int, default=None)
    parser.add_argument("--account", type=float, default=None)
    parser.add_argument("--mock", action="store_true", help="Skip data update/backtest and send a mock signal.")
    parser.add_argument("--remind", action="store_true", help="Send cached previous signal for today's execution.")
    parser.add_argument(
        "--reminder-label",
        choices=["open", "close"],
        default="open",
        help="Label used in reminder title/content.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending notification.")
    parser.add_argument("--force", action="store_true", help="Run even if today is not in the trading calendar.")
    parser.add_argument("--skip-update", action="store_true", help="Skip run_update_qlib_data.py in real mode.")
    parser.add_argument(
        "--no-reminder-rebuild",
        action="store_true",
        help="Do not rebuild a missing/stale cache during reminder mode.",
    )
    parser.add_argument("--create-update-tarball", action="store_true", help="Let update script create qlib_bin.tar.gz.")
    parser.add_argument("--notify-skip", action="store_true", help="Notify when skipped on a non-trading day.")
    parser.add_argument(
        "--notify-channel",
        choices=["bark", "all"],
        default=None,
        help="Default: daily_rebalance.notify_channel or bark.",
    )
    parser.add_argument(
        "--positions",
        type=str,
        default=None,
        help="实际持仓覆盖，格式: SH600489:900 或 SH600489:900:2026-04-29（含建仓日期）。用于从真实持仓计算调仓差分和收益。",
    )
    parser.add_argument(
        "--replay-from-initial-positions",
        action="store_true",
        help="将 --positions 视为起始持仓，从 --position-date/建仓日期/回测起点逐日按策略信号回放到今天，"
             "再用回放后的持仓计算今日调仓差分。假设每次信号均按次交易日收盘价执行。",
    )
    parser.add_argument(
        "--position-date",
        type=str,
        default=None,
        help="--positions 持仓的建仓日期，用于计算 hold_thresh 保护期。"
             "默认为上一个交易日。格式: 2026-04-29。",
    )
    parser.add_argument(
        "--min-action-value",
        type=float,
        default=None,
        help="忽略金额低于此阈值（元）的调仓动作，过滤价格微变导致的噪音手数调整。建议设 500~1000。",
    )
    parser.add_argument(
        "--no-cache-roll-forward",
        action="store_true",
        help="不要用上一条已缓存且执行日为今天的目标持仓覆盖 --positions。"
             "仅在昨日信号未执行或你已手动传入最新真实持仓时使用。",
    )
    return parser.parse_args()


def _daily_cfg(config: dict, args: argparse.Namespace) -> Dict[str, Any]:
    cfg = copy.deepcopy(config.get("daily_rebalance", {}))
    cfg["market"] = args.market or cfg.get("market", "csi1000")
    cfg["topk"] = args.topk if args.topk is not None else int(cfg.get("topk", 15))
    cfg["n_drop"] = args.n_drop if args.n_drop is not None else int(cfg.get("n_drop", 3))
    cfg["hold_thresh"] = (
        args.hold_thresh if args.hold_thresh is not None else int(cfg.get("hold_thresh", 5))
    )
    start_date = args.start_date or cfg.get("start_date") or config.get("backtest", {}).get("start_time")
    cfg["start_date"] = start_date
    cfg["_start_date_raw"] = start_date
    cfg["account"] = args.account if args.account is not None else float(cfg.get("account", 1_000_000))
    cfg["model_path"] = args.model_path if args.model_path is not None else cfg.get("model_path", "")
    cfg["notify_channel"] = args.notify_channel or cfg.get("notify_channel", "bark")
    cfg["notify_on_skip"] = bool(args.notify_skip or cfg.get("notify_on_skip", False))
    cfg["create_update_tarball"] = bool(args.create_update_tarball or cfg.get("create_update_tarball", False))
    cfg["min_action_value"] = (
        args.min_action_value if args.min_action_value is not None
        else float(cfg.get("min_action_value", 0))
    )
    cfg["position_date"] = args.position_date if args.position_date is not None else cfg.get("position_date")
    cfg["positions"] = args.positions if args.positions is not None else cfg.get("positions")
    cfg["replay_from_initial_positions"] = bool(
        args.replay_from_initial_positions or cfg.get("replay_from_initial_positions", False)
    )
    cfg["execution_mode"] = str(cfg.get("execution_mode", "auto_signal")).strip().lower()
    cfg["cache_dir"] = cfg.get("cache_dir") or "signals/daily_rebalance_cache"
    cfg["reminder_rebuild_on_miss"] = bool(
        cfg.get("reminder_rebuild_on_miss", True) and not args.no_reminder_rebuild
    )
    cfg["cache_roll_forward_positions"] = bool(
        cfg.get("cache_roll_forward_positions", True) and not args.no_cache_roll_forward
    )
    if not cfg["start_date"]:
        raise ValueError("daily_rebalance.start_date is required.")
    return cfg


def _resolve_start_date(
    value: str,
    trade_date: pd.Timestamp,
    calendar: List[pd.Timestamp],
) -> Tuple[str, bool]:
    token = str(value).strip().lower()
    if token in SIGNAL_DATE_START_ALIASES:
        return trade_date.strftime("%Y-%m-%d"), True
    if token in PREVIOUS_DATE_START_ALIASES:
        return _previous_trading_day(trade_date, calendar)
    return str(value), True


def _resolve_cfg_start_date(
    cfg: Dict[str, Any],
    trade_date: pd.Timestamp,
    calendar: List[pd.Timestamp],
) -> Dict[str, Any]:
    resolved = copy.deepcopy(cfg)
    raw_start = resolved.get("_start_date_raw") or resolved.get("start_date")
    start_date, exact = _resolve_start_date(str(raw_start), trade_date, calendar)
    if not exact:
        logger.warning("未在交易日历中找到动态回测起点，暂按工作日推断: %s", start_date)
    resolved["start_date"] = start_date
    return resolved


def _apply_strategy_config(config: dict, cfg: Dict[str, Any]) -> dict:
    config = copy.deepcopy(config)
    config.setdefault("market", {})["name"] = cfg["market"]
    config.setdefault("strategy", {}).setdefault("topk_dropout", {})
    config["strategy"]["topk_dropout"].update(
        {
            "topk": int(cfg["topk"]),
            "n_drop": int(cfg["n_drop"]),
            "hold_thresh": int(cfg["hold_thresh"]),
        }
    )
    config.setdefault("backtest", {})["account"] = float(cfg["account"])
    config["backtest"]["start_time"] = cfg["start_date"]
    return config


def _calendar_files(config: dict) -> Tuple[Path, Path]:
    provider_uri = _resolve_path(config.get("qlib", {}).get("provider_uri", "./qlib_data/qlib_bin"))
    calendar_dir = provider_uri / "calendars"
    return calendar_dir / "day.txt", calendar_dir / "day_future.txt"


def _read_calendar(path: Path) -> List[pd.Timestamp]:
    if not path.exists():
        return []
    values = pd.read_csv(path, header=None).iloc[:, 0]
    dates = pd.to_datetime(values, errors="coerce").dropna().dt.normalize()
    return sorted(pd.Timestamp(day).normalize() for day in dates.unique())


def _trading_calendar(config: dict) -> Tuple[List[pd.Timestamp], List[pd.Timestamp]]:
    day_file, future_file = _calendar_files(config)
    actual = _read_calendar(day_file)
    future = _read_calendar(future_file)
    return actual, future or actual


def _next_trading_day(target: pd.Timestamp, calendar: List[pd.Timestamp]) -> Tuple[str, bool]:
    for day in calendar:
        if day > target:
            return day.strftime("%Y-%m-%d"), True
    next_bday = target + pd.offsets.BDay(1)
    return pd.Timestamp(next_bday).strftime("%Y-%m-%d"), False


def _previous_trading_day(target: pd.Timestamp, calendar: List[pd.Timestamp]) -> Tuple[str, bool]:
    for day in reversed(calendar):
        if day < target:
            return day.strftime("%Y-%m-%d"), True
    previous_bday = target - pd.offsets.BDay(1)
    return pd.Timestamp(previous_bday).strftime("%Y-%m-%d"), False


def _run_update(config_path: Optional[str], create_tarball: bool) -> None:
    cmd = [sys.executable, str(PROJECT_ROOT / "run_update_qlib_data.py")]
    if config_path:
        cmd.extend(["--config", config_path])
    if not create_tarball:
        cmd.append("--no-tarball")
    logger.info("更新 qlib 数据: %s", " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def _load_model(config: dict, model_path: str = ""):
    if model_path:
        from quant_ex.models.base import BaseAlphaModel

        logger.info("加载模型: %s", model_path)
        return BaseAlphaModel.load(model_path)

    exp_cfg = config.get("experiment", {})
    recorder_id = exp_cfg.get("latest_recorder_id", "")
    if not recorder_id:
        raise RuntimeError(
            "未配置模型。请设置 daily_rebalance.model_path，或填写 experiment.latest_recorder_id。"
        )
    logger.info("加载 qlib recorder 模型: %s / %s", exp_cfg.get("name"), recorder_id)
    return load_recorder_model(exp_cfg.get("name", "tutorial_exp"), recorder_id)


def _predict_for_replay(
    model,
    data_loader: DataLoader,
    universe_filter: UniverseFilter,
    config: dict,
    instruments: str,
    start: str,
    end: str,
):
    tcfg = config.get("training", {})
    segments = {
        "train": (tcfg.get("fit_start", "2015-01-01"), tcfg.get("fit_end", "2021-12-31")),
        "valid": (tcfg.get("valid_start", "2022-01-01"), tcfg.get("valid_end", "2023-12-31")),
        "test": (start, end),
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
            end_time=end,
        )

    if getattr(model, "factor_pipeline", None) is not None:
        logger.info("模型含有 factor_pipeline，为 %s 重新计算额外因子", instruments)
        model.refresh_extra_factors(price_data)

    pred = model.predict(dataset, segment="test")
    if universe_filter.requires_price_data():
        if price_data is None:
            price_data = data_loader.load_price_data(instruments=instruments, start_time=start, end_time=end)
        pred = universe_filter.filter(pred, price_data=price_data)
    else:
        pred = universe_filter.filter(pred)

    post_cfg = config.get("signal", {}).get("postprocess", {})
    sector_provider = (
        SectorDataProvider(config)
        if (
            post_cfg.get("industry_neutralize", False)
            or post_cfg.get("stock_vs_sector_filter", {}).get("enabled", False)
        )
        else None
    )
    sector_map = sector_provider.get_map() if sector_provider is not None else None
    return postprocess_signal(
        pred,
        config=config,
        sector_map=sector_map,
        price_data=price_data,
    )


def _position_payload(position_obj: Any) -> Dict[str, Any]:
    if hasattr(position_obj, "position"):
        return position_obj.position
    if isinstance(position_obj, dict) and "position" in position_obj:
        return position_obj["position"]
    if isinstance(position_obj, dict):
        return position_obj
    return {}


def _snapshot(position_obj: Any, lot_size: int = 100) -> Dict[str, Dict[str, float]]:
    payload = _position_payload(position_obj)
    result: Dict[str, Dict[str, float]] = {}
    for inst, info in payload.items():
        if not isinstance(info, dict) or "amount" not in info:
            continue
        shares = int(float(info.get("amount", 0)) / lot_size) * lot_size
        if shares <= 0:
            continue
        price = float(info.get("price", 0) or 0)
        result[inst] = {"shares": float(shares), "price": price, "value": shares * price}
    return result


def _source_csv_path(instrument: str) -> Path:
    return PROJECT_ROOT / "qlib_data" / "qlib_source" / f"{instrument}.csv"


def _load_actual_close(instrument: str, trade_date: str) -> Optional[float]:
    path = _source_csv_path(instrument)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=["tradedate", "close"])
    except Exception:
        return None
    dates = pd.to_datetime(df["tradedate"], errors="coerce")
    target = pd.Timestamp(trade_date).normalize()
    matched = df.loc[dates == target, "close"]
    if matched.empty:
        matched = df.loc[dates <= target, "close"].tail(1)
    if matched.empty:
        return None
    price = pd.to_numeric(matched, errors="coerce").dropna()
    if price.empty:
        return None
    value = float(price.iloc[-1])
    return value if value > 0 else None


def _load_prev_close(instrument: str, trade_date: str, trading_calendar: List[pd.Timestamp]) -> Optional[float]:
    """Load the closing price on the trading day before *trade_date*."""
    ts = pd.Timestamp(trade_date).normalize()
    prev_day = None
    for d in trading_calendar:
        if d < ts:
            prev_day = d
        else:
            break
    if prev_day is None:
        return None
    return _load_actual_close(instrument, prev_day.strftime("%Y-%m-%d"))


def _calendar_until(
    trade_date: str,
    trading_calendar: Optional[List[pd.Timestamp]] = None,
) -> List[pd.Timestamp]:
    if trading_calendar:
        return trading_calendar
    end = pd.Timestamp(trade_date).normalize()
    return [pd.Timestamp(day).normalize() for day in pd.bdate_range(end=end, periods=2600)]


def _compute_portfolio_pnl(
    positions: Dict[str, Dict[str, Any]],
    trade_date: str,
    trading_calendar: List[pd.Timestamp],
    default_entry_date: Optional[str] = None,
    pnl_carry: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Compute cumulative & daily P&L for actual positions.

    When entry_date is provided, cumulative P&L is calculated from that
    closing price. Otherwise default_entry_date is used when available, and
    finally previous-day price is used as a compatibility fallback.

    Returns dict with: total_value, cum_pnl, cum_return, daily_pnl, daily_return,
    and per_stock list with instrument/shares/entry_date/cost_price/prev_price/cur_price/
    cum_pnl/cum_return/daily_pnl/daily_return/days_held.
    """
    per_stock: List[Dict[str, Any]] = []
    total_value = 0.0
    total_cost_value = 0.0
    total_prev_value = 0.0
    for inst, info in positions.items():
        shares = float(info.get("shares", 0))
        if shares <= 0:
            continue
        cur_price = float(info.get("price", 0))
        if cur_price <= 0:
            continue
        prev_price = _load_prev_close(inst, trade_date, trading_calendar)
        if prev_price is None or prev_price <= 0:
            prev_price = cur_price
        # Determine cost basis: entry_date close if available, else prev close
        entry_str = info.get("entry_date") or default_entry_date
        cost_price = prev_price
        explicit_cost_price = float(info.get("cost_price", 0) or 0)
        if explicit_cost_price > 0:
            cost_price = explicit_cost_price
        days_held = None
        if entry_str:
            entry_ts = pd.Timestamp(entry_str).normalize()
            trade_ts = pd.Timestamp(trade_date).normalize()
            days_held = sum(1 for d in trading_calendar if entry_ts <= d < trade_ts)
            entry_price = _load_actual_close(inst, entry_str)
            if explicit_cost_price <= 0 and entry_price is not None and entry_price > 0:
                cost_price = entry_price

        cur_value = shares * cur_price
        cost_value = shares * cost_price
        prev_value = shares * prev_price
        total_value += cur_value
        total_cost_value += cost_value
        total_prev_value += prev_value
        cum_pnl = cur_value - cost_value
        cum_ret = cum_pnl / cost_value if cost_value > 0 else 0.0
        daily_pnl = cur_value - prev_value
        daily_ret = daily_pnl / prev_value if prev_value > 0 else 0.0
        per_stock.append({
            "instrument": inst,
            "shares": shares,
            "entry_date": entry_str,
            "cost_price": cost_price,
            "prev_price": prev_price,
            "cur_price": cur_price,
            "cum_pnl": cum_pnl,
            "cum_return": cum_ret,
            "daily_pnl": daily_pnl,
            "daily_return": daily_ret,
            "days_held": days_held,
        })
    position_cum_pnl = total_value - total_cost_value
    carry_pnl = float((pnl_carry or {}).get("cum_pnl", 0) or 0)
    cum_pnl = position_cum_pnl + carry_pnl
    cum_return = cum_pnl / total_cost_value if total_cost_value > 0 else 0.0
    daily_pnl = total_value - total_prev_value
    daily_return = daily_pnl / total_prev_value if total_prev_value > 0 else 0.0
    return {
        "total_value": total_value,
        "cum_pnl": cum_pnl,
        "cum_return": cum_return,
        "position_cum_pnl": position_cum_pnl,
        "pnl_carry": carry_pnl,
        "daily_pnl": daily_pnl,
        "daily_return": daily_return,
        "per_stock": per_stock,
    }


def _convert_snapshot_to_actual_prices(
    snapshot: Dict[str, Dict[str, float]],
    trade_date: str,
    lot_size: int = 100,
    account_value: float = 0,
    max_position_pct: float = 0.0,
) -> Dict[str, Dict[str, float]]:
    """Convert qlib position snapshot to actual-price-based shares.

    When *account_value* > 0, allocates equal-weight across all instruments
    in *snapshot* using actual (unadjusted) closing prices — this avoids the
    systematic under-allocation caused by dividing qlib's adjusted-price
    market value by the higher unadjusted price.

    When *account_value* is 0 (legacy path), falls back to the old behaviour
    of converting qlib's ``value`` field with actual prices.
    """
    converted: Dict[str, Dict[str, float]] = {}

    if account_value > 0 and snapshot:
        n = len(snapshot)
        weight = min(1.0 / n, max_position_pct) if max_position_pct > 0 else 1.0 / n
        for inst in snapshot:
            actual_price = _load_actual_close(inst, trade_date)
            if actual_price is None or actual_price <= 0:
                continue
            shares = int(account_value * weight / actual_price / lot_size) * lot_size
            if shares <= 0:
                continue
            converted[inst] = {
                "shares": float(shares),
                "price": actual_price,
                "value": shares * actual_price,
            }
        return converted

    # Legacy path: convert qlib adjusted-price value to actual-price shares
    for inst, info in snapshot.items():
        target_value = float(info.get("value", 0) or 0)
        actual_price = _load_actual_close(inst, trade_date)
        if actual_price is None or target_value <= 0:
            converted[inst] = dict(info)
            continue
        shares = int(target_value / actual_price / lot_size) * lot_size
        if shares <= 0:
            continue
        converted[inst] = {
            "shares": float(shares),
            "price": actual_price,
            "value": shares * actual_price,
            "raw_target_value": target_value,
        }
    return converted


def _parse_positions_arg(positions_str: str, trade_date: str) -> Dict[str, Dict[str, Any]]:
    """Parse --positions 'SH600489:900,SH600489:900:2026-04-29' into a snapshot dict.

    Format: INSTRUMENT:SHARES or INSTRUMENT:SHARES:ENTRY_DATE
    Entry date is used for per-stock holding day tracking and hold protection.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for item in positions_str.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(f"--positions 格式错误: {item!r}，期望 INSTRUMENT:SHARES 或 INSTRUMENT:SHARES:ENTRY_DATE")
        inst = parts[0].strip().upper()
        try:
            shares = float(parts[1].strip())
        except ValueError:
            raise ValueError(f"--positions 股数解析失败: {item!r}")
        entry_date = parts[2].strip() if len(parts) == 3 else None
        price = _load_actual_close(inst, trade_date) or 0.0
        result[inst] = {"shares": shares, "price": price, "value": shares * price}
        if entry_date:
            result[inst]["entry_date"] = entry_date
    return result


def _positions_start_date(
    positions_str: str,
    cfg: Dict[str, Any],
    position_date: Optional[str] = None,
) -> str:
    """Infer the date for an initial --positions snapshot."""
    if position_date:
        return pd.Timestamp(position_date).normalize().strftime("%Y-%m-%d")

    entry_dates: List[pd.Timestamp] = []
    for item in positions_str.split(","):
        parts = [part.strip() for part in item.strip().split(":")]
        if len(parts) == 3 and parts[2]:
            entry_dates.append(pd.Timestamp(parts[2]).normalize())
    if entry_dates:
        return min(entry_dates).strftime("%Y-%m-%d")

    return pd.Timestamp(cfg["start_date"]).normalize().strftime("%Y-%m-%d")


def _clone_position_snapshot(snapshot: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Return a JSON/cache-friendly position snapshot with normalized numbers."""
    result: Dict[str, Dict[str, Any]] = {}
    for inst, info in snapshot.items():
        if not isinstance(info, dict):
            continue
        shares = float(info.get("shares", 0) or 0)
        if shares <= 0:
            continue
        price = float(info.get("price", 0) or 0)
        value = float(info.get("value", shares * price) or shares * price)
        item: Dict[str, Any] = {"shares": shares, "price": price, "value": value}
        for key in ("entry_date", "cost_price", "raw_target_value"):
            if info.get(key) is not None:
                item[key] = info[key]
        result[inst] = item
    return result


def _refresh_position_prices(
    positions: Dict[str, Dict[str, Any]],
    trade_date: str,
) -> Dict[str, Dict[str, Any]]:
    """Update a snapshot to the latest actual close while keeping share counts."""
    refreshed = _clone_position_snapshot(positions)
    for inst, info in refreshed.items():
        price = _load_actual_close(inst, trade_date)
        if price is not None and price > 0:
            info["price"] = price
        info["value"] = float(info.get("shares", 0) or 0) * float(info.get("price", 0) or 0)
    return refreshed


def _reset_execution_day_costs(
    positions: Dict[str, Dict[str, Any]],
    execution_date: str,
) -> Dict[str, Dict[str, Any]]:
    """Use execution-day close as cost for positions opened at that close."""
    result = _clone_position_snapshot(positions)
    execution_ts = pd.Timestamp(execution_date).normalize()
    for info in result.values():
        entry_date = info.get("entry_date")
        if entry_date and pd.Timestamp(entry_date).normalize() == execution_ts:
            info["cost_price"] = float(info.get("price", 0) or 0)
            info["value"] = float(info.get("shares", 0) or 0) * float(info.get("price", 0) or 0)
    return result


def _annotate_executed_target(
    target: Dict[str, Dict[str, Any]],
    previous: Optional[Dict[str, Dict[str, Any]]],
    execution_date: str,
) -> Dict[str, Dict[str, Any]]:
    """Attach entry dates to a target snapshot after the rebalance is executed."""
    annotated = _clone_position_snapshot(target)
    previous = previous or {}
    for inst, info in annotated.items():
        prev_info = previous.get(inst, {})
        prev_shares = float(prev_info.get("shares", 0) or 0)
        if prev_shares > 0 and prev_info.get("entry_date"):
            info["entry_date"] = prev_info["entry_date"]
            if prev_info.get("cost_price") is not None:
                info["cost_price"] = prev_info["cost_price"]
        else:
            info["entry_date"] = execution_date
            info.setdefault("cost_price", info.get("price", 0))
    return annotated


def _parse_target_positions_from_report(report: str, execution_date: str) -> Dict[str, Dict[str, Any]]:
    """Recover target positions from legacy caches that only stored report text."""
    in_target_section = False
    result: Dict[str, Dict[str, Any]] = {}
    pattern = re.compile(
        r"^(?P<inst>(?:SH|SZ|BJ)\d{6})\b.*?:\s*"
        r"(?P<shares>[\d,]+(?:\.\d+)?)股"
        r"(?:\s+约(?P<value>[\d,]+(?:\.\d+)?)元)?"
    )
    for raw_line in str(report or "").splitlines():
        line = raw_line.strip()
        if line == "目标持仓摘要:":
            in_target_section = True
            continue
        if not in_target_section:
            continue
        if not line or line.startswith("模型选股目标"):
            break
        matched = pattern.match(line)
        if not matched:
            continue
        inst = matched.group("inst")
        shares = float(matched.group("shares").replace(",", ""))
        value = float(matched.group("value").replace(",", "")) if matched.group("value") else 0.0
        price = value / shares if shares > 0 and value > 0 else 0.0
        result[inst] = {
            "shares": shares,
            "price": price,
            "value": value,
            "cost_price": price,
            "entry_date": execution_date,
        }
    return result


def _parse_portfolio_pnl_from_report(report: str) -> Optional[Dict[str, float]]:
    """Recover portfolio-level P&L from legacy report text."""
    pattern = re.compile(
        r"累计收益\s*(?P<cum>[+-]?[\d,]+(?:\.\d+)?)元\s*"
        r"\((?P<ret>[+-]?[\d.]+)%\).*?"
        r"总市值\s*(?P<value>[\d,]+(?:\.\d+)?)元"
    )
    matched = pattern.search(str(report or "").replace("\n", " "))
    if not matched:
        return None
    cum_pnl = float(matched.group("cum").replace(",", ""))
    cum_return = float(matched.group("ret")) / 100.0
    total_value = float(matched.group("value").replace(",", ""))
    return {
        "cum_pnl": cum_pnl,
        "cum_return": cum_return,
        "total_value": total_value,
    }


def _actions_from_cache(payload: Dict[str, Any]) -> List[RebalanceAction]:
    actions: List[RebalanceAction] = []
    for item in payload.get("actions") or []:
        if not isinstance(item, dict):
            continue
        try:
            action = str(item.get("action", ""))
            inst = str(item.get("instrument", ""))
            shares = float(item.get("shares", 0) or 0)
            price = float(item.get("price", 0) or 0)
            value = float(item.get("value", shares * price) or shares * price)
        except (TypeError, ValueError):
            continue
        if action and inst and shares > 0:
            actions.append(RebalanceAction(action, inst, shares, price, value))
    return actions


def _base_pnl_carry_from_payload(payload: Dict[str, Any]) -> Dict[str, float]:
    portfolio_pnl = payload.get("portfolio_pnl")
    if isinstance(portfolio_pnl, dict):
        carry = {
            "cum_pnl": float(portfolio_pnl.get("pnl_carry", 0) or 0),
            "cum_return": 0.0,
            "total_value": float(portfolio_pnl.get("total_value", 0) or 0),
        }
    else:
        raw = payload.get("pnl_carry")
        if isinstance(raw, dict):
            carry = {
                "cum_pnl": float(raw.get("cum_pnl", 0) or 0),
                "cum_return": float(raw.get("cum_return", 0) or 0),
                "total_value": float(raw.get("total_value", 0) or 0),
            }
        else:
            carry = _parse_portfolio_pnl_from_report(str(payload.get("report", ""))) or {
                "cum_pnl": 0.0,
                "cum_return": 0.0,
                "total_value": 0.0,
            }
    carry["source_trade_date"] = str(payload.get("trade_date") or "")
    return carry


def _load_executed_state_from_cache(
    cfg: Dict[str, Any],
    trade_date: str,
    trading_calendar: Optional[List[pd.Timestamp]] = None,
) -> Optional[Dict[str, Any]]:
    """Load executed positions plus carried portfolio P&L from cache."""
    loaded = _load_executed_positions_from_cache(
        cfg, trade_date, return_state=True, trading_calendar=trading_calendar
    )
    return loaded if isinstance(loaded, dict) and "positions" in loaded else None


def _cache_strategy_matches(payload: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    strategy = payload.get("strategy") or {}
    market = strategy.get("market")
    return not market or market == cfg.get("market")


def _load_executed_positions_from_cache(
    cfg: Dict[str, Any],
    trade_date: str,
    return_state: bool = False,
    trading_calendar: Optional[List[pd.Timestamp]] = None,
) -> Any:
    """Load the latest cached target whose execution date is *trade_date*.

    This treats yesterday's signal as executed at today's close. The next
    after-close run diffs against the post-trade portfolio, while execution-day
    P&L is still measured on the pre-close holdings.
    """
    if not cfg.get("cache_roll_forward_positions", True):
        return None

    cache_dir = _cache_dir(cfg)
    if not cache_dir.exists():
        return None

    candidates: List[Tuple[pd.Timestamp, str, Path, Dict[str, Any]]] = []
    trade_ts = pd.Timestamp(trade_date).normalize()
    for path in cache_dir.glob("rebalance_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        next_trade_date = payload.get("next_trade_date")
        if not next_trade_date:
            continue
        if pd.Timestamp(next_trade_date).normalize() != trade_ts:
            continue
        if not _cache_strategy_matches(payload, cfg):
            continue
        signal_date = pd.Timestamp(payload.get("trade_date") or "1900-01-01")
        candidates.append((signal_date, str(payload.get("created_at", "")), path, payload))

    if not candidates:
        return None

    _, _, path, payload = sorted(candidates, key=lambda item: (item[0], item[1]))[-1]
    raw_positions = payload.get("executed_positions") or payload.get("target_positions")
    if isinstance(raw_positions, dict) and raw_positions:
        positions = _clone_position_snapshot(raw_positions)
    else:
        positions = _parse_target_positions_from_report(
            str(payload.get("report", "")),
            execution_date=str(payload.get("next_trade_date") or trade_date),
        )
    if not positions:
        return None

    execution_date = str(payload.get("next_trade_date") or trade_date)
    for info in positions.values():
        info.setdefault("entry_date", execution_date)
    positions = _refresh_position_prices(positions, trade_date)
    positions = _reset_execution_day_costs(positions, execution_date)

    pre_positions = None
    raw_pre_positions = payload.get("previous_positions")
    if isinstance(raw_pre_positions, dict) and raw_pre_positions:
        pre_positions = _refresh_position_prices(_clone_position_snapshot(raw_pre_positions), trade_date)

    base_pnl_carry = _base_pnl_carry_from_payload(payload)
    display_portfolio_pnl = None
    calendar = _calendar_until(trade_date, trading_calendar)
    if pre_positions:
        display_portfolio_pnl = _compute_portfolio_pnl(
            pre_positions,
            trade_date,
            calendar,
            pnl_carry=base_pnl_carry,
        )
        pnl_carry = _pnl_carry_after_actions(display_portfolio_pnl, _actions_from_cache(payload))
    else:
        display_portfolio_pnl = _compute_portfolio_pnl(
            positions,
            trade_date,
            calendar,
            pnl_carry=base_pnl_carry,
        )
        if float(display_portfolio_pnl.get("position_cum_pnl", 0) or 0) == 0:
            display_portfolio_pnl["cum_return"] = float(base_pnl_carry.get("cum_return", 0) or 0)
        pnl_carry = dict(base_pnl_carry)
    pnl_carry["source_trade_date"] = str(payload.get("trade_date") or "")
    logger.info(
        "使用上一条缓存信号作为已执行持仓: %s -> %s (%s, 共 %d 只)。",
        payload.get("trade_date"),
        payload.get("next_trade_date"),
        path.name,
        len(positions),
    )
    if return_state:
        return {
            "positions": positions,
            "pnl_carry": pnl_carry,
            "display_portfolio_pnl": display_portfolio_pnl,
            "source_cache": str(path),
        }
    return positions


def _replay_positions_from_initial(
    config: dict,
    cfg: Dict[str, Any],
    initial_positions: Dict[str, Dict[str, Any]],
    initial_date: str,
    trade_date: str,
    trading_calendar: List[pd.Timestamp],
) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, float]]]:
    """Roll an initial real-position snapshot forward by applying daily signals.

    This is a convenience path for manual workflows: it assumes every generated
    rebalance signal is executed at the next trading day's close. It should not
    be used when actual fills materially diverged from the generated signals.
    """
    if not trading_calendar:
        return _clone_position_snapshot(initial_positions), None

    start_ts = pd.Timestamp(initial_date).normalize()
    trade_ts = pd.Timestamp(trade_date).normalize()
    signal_days = [day for day in trading_calendar if start_ts <= day < trade_ts]
    if not signal_days:
        return _refresh_position_prices(initial_positions, trade_date), None
    if str(cfg.get("execution_mode", "auto_signal")).strip().lower() == "manual":
        return _refresh_position_prices(initial_positions, trade_date), None

    last_signal_date = signal_days[-1].strftime("%Y-%m-%d")
    model = _load_model(config, cfg.get("model_path", ""))
    data_loader = DataLoader(config)
    universe_filter = UniverseFilter(config.get("strategy", {}))
    pred = _predict_for_replay(
        model=model,
        data_loader=data_loader,
        universe_filter=universe_filter,
        config=config,
        instruments=cfg["market"],
        start=cfg["start_date"],
        end=last_signal_date,
    )
    engine = BacktestEngine(config)
    _report, qlib_positions = engine.run(
        pred=pred,
        strategy_params={
            "topk": cfg["topk"],
            "n_drop": cfg["n_drop"],
            "hold_thresh": 0,
        },
        start_time=cfg["start_date"],
        end_time=last_signal_date,
        account=cfg["account"],
        universe_filter=None,
    )
    position_items = _sorted_position_items(qlib_positions)
    if not position_items:
        raise RuntimeError("初始持仓回放失败：回测没有返回 position 数据。")

    positions = _clone_position_snapshot(initial_positions)
    pnl_carry: Optional[Dict[str, float]] = None
    latest_obj = None
    position_idx = 0
    acct = float(cfg.get("account", 0))
    port_cfg = config.get("strategy", {}).get("portfolio", {})
    max_pct = float(port_cfg.get("max_position_pct", 0))
    min_val = float(cfg.get("min_action_value", 0))
    replayed = 0
    for signal_day in signal_days:
        next_trade_date, exact_next = _next_trading_day(signal_day, trading_calendar)
        next_ts = pd.Timestamp(next_trade_date).normalize()
        if not exact_next or next_ts > trade_ts:
            continue
        signal_date = signal_day.strftime("%Y-%m-%d")
        while position_idx < len(position_items) and position_items[position_idx][0] <= signal_day:
            latest_obj = position_items[position_idx][1]
            position_idx += 1
        if latest_obj is None:
            continue

        positions = _refresh_position_prices(positions, signal_date)
        target = _convert_snapshot_to_actual_prices(
            _snapshot(latest_obj),
            signal_date,
            account_value=acct,
            max_position_pct=max_pct,
        )
        actions = _diff_positions(positions, target)
        raw_position_date = cfg.get("position_date")
        if raw_position_date:
            position_date_ts = pd.Timestamp(raw_position_date).normalize()
        else:
            prev_str, _ = _previous_trading_day(signal_day, trading_calendar)
            position_date_ts = pd.Timestamp(prev_str).normalize()
        actions, target = _apply_hold_protection(
            actions=actions,
            target=target,
            actual_positions=positions,
            position_date=position_date_ts,
            trade_date=signal_day,
            hold_thresh=int(cfg.get("hold_thresh", 5)),
            trading_calendar=trading_calendar,
            topk=int(cfg.get("topk", 5)),
        )
        if min_val > 0:
            actions = [action for action in actions if action.value >= min_val]

        portfolio_pnl = _compute_portfolio_pnl(
            positions,
            signal_date,
            trading_calendar,
            default_entry_date=position_date_ts.strftime("%Y-%m-%d"),
            pnl_carry=pnl_carry,
        )
        pnl_carry = _pnl_carry_after_actions(portfolio_pnl, actions)
        logger.info(
            "初始持仓回放: %s 信号 -> %s 执行（%d 笔动作）。",
            signal_date,
            next_trade_date,
            len(actions),
        )
        positions = _annotate_executed_target(
            _positions_after_actions(positions, target, actions),
            positions,
            next_trade_date,
        )
        replayed += 1

    positions = _refresh_position_prices(positions, trade_date)
    logger.info(
        "初始持仓已从 %s 回放到 %s（应用 %d 次历史信号，当前 %d 只）。",
        initial_date,
        trade_date,
        replayed,
        len(positions),
    )
    return positions, pnl_carry


def _sorted_position_items(positions: dict) -> List[Tuple[pd.Timestamp, Any]]:
    items = [(pd.to_datetime(date), value) for date, value in positions.items()]
    return sorted(items, key=lambda item: item[0])


def _diff_positions(
    previous: Dict[str, Dict[str, float]],
    target: Dict[str, Dict[str, float]],
) -> List[RebalanceAction]:
    actions: List[RebalanceAction] = []
    instruments = sorted(set(previous) | set(target))
    for inst in instruments:
        old_shares = previous.get(inst, {}).get("shares", 0)
        new_shares = target.get(inst, {}).get("shares", 0)
        diff = new_shares - old_shares
        if abs(diff) < 1:
            continue
        info = target.get(inst) or previous.get(inst) or {}
        price = float(info.get("price", 0) or 0)
        action = "buy" if diff > 0 else ("reduce" if inst in target else "sell")
        actions.append(
            RebalanceAction(
                action=action,
                instrument=inst,
                shares=abs(diff),
                price=price,
                value=abs(diff) * price,
            )
        )
    return actions


def _positions_after_actions(
    previous: Dict[str, Dict[str, Any]],
    target: Dict[str, Dict[str, Any]],
    actions: Iterable[RebalanceAction],
) -> Dict[str, Dict[str, Any]]:
    """Return the portfolio implied by the actions the report asks to execute."""
    action_instruments = {action.instrument for action in actions}
    result = _clone_position_snapshot(previous)

    for inst, info in target.items():
        old_shares = float(previous.get(inst, {}).get("shares", 0) or 0)
        new_shares = float(info.get("shares", 0) or 0)
        if abs(new_shares - old_shares) < 1 or inst in action_instruments:
            result[inst] = dict(info)
        elif inst not in previous:
            result.pop(inst, None)

    for inst in set(previous) - set(target):
        if inst in action_instruments:
            result.pop(inst, None)

    return _clone_position_snapshot(result)


def _pnl_carry_after_actions(
    portfolio_pnl: Optional[Dict[str, Any]],
    actions: Iterable[RebalanceAction],
) -> Dict[str, float]:
    """Carry realized P&L for positions reduced or sold by the pending actions."""
    if not portfolio_pnl:
        return {"cum_pnl": 0.0, "cum_return": 0.0, "total_value": 0.0}

    carry = float(portfolio_pnl.get("pnl_carry", 0) or 0)
    action_by_inst = {action.instrument: action for action in actions if action.action in {"sell", "reduce"}}
    per_stock = {
        item.get("instrument"): item
        for item in portfolio_pnl.get("per_stock", [])
        if isinstance(item, dict) and item.get("instrument")
    }
    for inst, action in action_by_inst.items():
        item = per_stock.get(inst)
        if not item:
            continue
        shares = float(item.get("shares", 0) or 0)
        if shares <= 0:
            continue
        realized_ratio = min(1.0, float(action.shares) / shares)
        carry += float(item.get("cum_pnl", 0) or 0) * realized_ratio

    total_value = float(portfolio_pnl.get("total_value", 0) or 0)
    cum_return = carry / total_value if total_value > 0 else 0.0
    return {"cum_pnl": carry, "cum_return": cum_return, "total_value": total_value}


def _count_trading_days_held(
    position_date: pd.Timestamp,
    trade_date: pd.Timestamp,
    trading_calendar: List[pd.Timestamp],
) -> int:
    """Count trading days strictly between position_date and trade_date (exclusive of trade_date)."""
    return sum(1 for d in trading_calendar if position_date <= d < trade_date)


def _apply_hold_protection(
    actions: List[RebalanceAction],
    target: Dict[str, Dict[str, float]],
    actual_positions: Dict[str, Dict[str, Any]],
    position_date: pd.Timestamp,
    trade_date: pd.Timestamp,
    hold_thresh: int,
    trading_calendar: List[pd.Timestamp],
    topk: int = 5,
) -> Tuple[List[RebalanceAction], Dict[str, Dict[str, float]]]:
    """过滤掉还在 hold_thresh 保护期内的卖出/减仓动作，并重建 target。

    当 actual_positions 包含 per-stock entry_date 时，逐股判断保护期：
    每只股票根据各自的 entry_date 独立计算持有天数，仅保护未过保护期的个股。
    否则使用全局 position_date 统一判断。

    受保护的持仓占用 topk 名额；剩余名额才允许买入新标的，
    避免总仓位超过 topk 上限。
    """
    trade_ts = pd.Timestamp(trade_date).normalize()

    # Determine per-stock protection: use entry_date if available, else global position_date
    protected: set = set()
    per_stock_days: Dict[str, int] = {}
    for inst, info in actual_positions.items():
        entry_str = info.get("entry_date")
        if entry_str:
            entry_ts = pd.Timestamp(entry_str).normalize()
            days = _count_trading_days_held(entry_ts, trade_ts, trading_calendar)
        else:
            days = _count_trading_days_held(position_date, trade_ts, trading_calendar)
        per_stock_days[inst] = days
        if days < hold_thresh:
            protected.add(inst)

    if not protected:
        return actions, target  # 所有持仓已过保护期

    remaining_slots = max(0, topk - len(protected))

    # 新 target：先放所有受保护的持仓（保留实际手数）
    new_target: Dict[str, Dict[str, float]] = {}
    for inst in sorted(protected):
        new_target[inst] = dict(actual_positions[inst])

    # 再从策略选出的 target 里补充空余名额（按原 target 顺序）
    for inst, info in target.items():
        if inst in protected:
            continue  # 已收录
        if remaining_slots <= 0:
            break
        new_target[inst] = info
        remaining_slots -= 1

    # 用实际持仓重新计算 diff
    new_actions = _diff_positions(actual_positions, new_target)

    if protected:
        details = ", ".join(f"{inst}({per_stock_days[inst]}日)" for inst in sorted(protected))
        logger.info(
            "hold 保护: %s (< hold_thresh=%d)，保留受保护持仓，新买入名额=%d。",
            details, hold_thresh, max(0, topk - len(protected)),
        )
    return new_actions, new_target


def _run_real_rebalance(
    config: dict,
    cfg: Dict[str, Any],
    trade_date: str,
    next_trade_date: str,
    actual_positions: Optional[Dict[str, Dict[str, float]]] = None,
    trading_calendar: Optional[List[pd.Timestamp]] = None,
    pnl_carry: Optional[Dict[str, float]] = None,
    display_portfolio_pnl: Optional[Dict[str, Any]] = None,
    return_details: bool = False,
) -> Any:
    model = _load_model(config, cfg.get("model_path", ""))
    data_loader = DataLoader(config)
    universe_filter = UniverseFilter(config.get("strategy", {}))
    pred = _predict_for_replay(
        model=model,
        data_loader=data_loader,
        universe_filter=universe_filter,
        config=config,
        instruments=cfg["market"],
        start=cfg["start_date"],
        end=trade_date,
    )
    engine = BacktestEngine(config)
    # When real holdings are provided, qlib's internal hold_thresh is based on
    # the replayed paper portfolio rather than the user's actual entry dates.
    # Disable it here and apply real-position hold protection below.
    replay_hold_thresh = 0 if actual_positions is not None else cfg["hold_thresh"]
    if actual_positions is not None and int(cfg.get("hold_thresh", 0)) > 0:
        logger.info(
            "检测到 --positions，回放阶段禁用 qlib 内部 hold_thresh，改用真实持仓建仓日做保护。"
        )
    report, positions = engine.run(
        pred=pred,
        strategy_params={
            "topk": cfg["topk"],
            "n_drop": cfg["n_drop"],
            "hold_thresh": replay_hold_thresh,
        },
        start_time=cfg["start_date"],
        end_time=trade_date,
        account=cfg["account"],
        universe_filter=None,
    )
    position_items = _sorted_position_items(positions)
    if not position_items:
        raise RuntimeError("回测没有返回 position 数据。")
    latest_dt, latest_obj = position_items[-1]
    acct = float(cfg.get("account", 0))
    port_cfg = config.get("strategy", {}).get("portfolio", {})
    max_pct = float(port_cfg.get("max_position_pct", 0))
    target = _convert_snapshot_to_actual_prices(
        _snapshot(latest_obj), trade_date,
        account_value=acct, max_position_pct=max_pct,
    )
    # 若用户传入了 --positions，用真实持仓做差分；否则回退到回测模拟的前一日持仓。
    if actual_positions is not None:
        logger.info("使用 --positions 实际持仓作为调仓差分基准（共 %d 只）。", len(actual_positions))
        previous = actual_positions
    else:
        prev_obj = position_items[-2][1] if len(position_items) > 1 else {}
        previous = _convert_snapshot_to_actual_prices(
            _snapshot(prev_obj), trade_date,
            account_value=acct, max_position_pct=max_pct,
        )
    actions = _diff_positions(previous, target)
    # Save pre-hold-protection target for display
    model_target = dict(target) if actual_positions is not None else None
    portfolio_position_date = None
    # hold_thresh 保护：若传入了 --positions 和 --position-date，过滤保护期内的卖出动作。
    if actual_positions is not None and trading_calendar:
        raw_position_date = cfg.get("position_date")
        if raw_position_date:
            position_date_ts = pd.Timestamp(raw_position_date).normalize()
        else:
            # 默认：--positions 是在 trade_date 的前一个交易日建立的
            prev_str, _ = _previous_trading_day(pd.Timestamp(trade_date), trading_calendar)
            position_date_ts = pd.Timestamp(prev_str).normalize()
        portfolio_position_date = position_date_ts.strftime("%Y-%m-%d")
        actions, target = _apply_hold_protection(
            actions=actions,
            target=target,
            actual_positions=actual_positions,
            position_date=position_date_ts,
            trade_date=pd.Timestamp(trade_date).normalize(),
            hold_thresh=int(cfg.get("hold_thresh", 5)),
            trading_calendar=trading_calendar,
            topk=int(cfg.get("topk", 5)),
        )
    # 过滤噪音小额调仓（如价格微变导致手数 ±100 股）。
    min_val = float(cfg.get("min_action_value", 0))
    if min_val > 0:
        filtered = [a for a in actions if a.value >= min_val]
        ignored = [a for a in actions if a.value < min_val]
        if ignored:
            logger.info(
                "已过滤 %d 笔小额调仓（< %.0f元）: %s",
                len(ignored),
                min_val,
                ", ".join(f"{a.instrument} {a.shares:.0f}股 {a.value:.0f}元" for a in ignored),
            )
        actions = filtered
    target_for_cache = _annotate_executed_target(target, previous, next_trade_date)
    executed_for_cache = _annotate_executed_target(
        _positions_after_actions(previous, target, actions),
        previous,
        next_trade_date,
    )
    metrics = _last_metrics(report)
    name_map = load_stock_names()
    sector_map = _load_sector_map(config)
    # Compute real portfolio P&L from actual positions when available.
    # When a cached signal is rolled forward with close execution semantics,
    # display_portfolio_pnl represents the pre-close holdings' P&L through
    # today's close; actual_positions is already the post-close portfolio used
    # as the next signal's diff baseline.
    portfolio_pnl = None
    state_portfolio_pnl = None
    if actual_positions is not None and trading_calendar:
        state_portfolio_pnl = _compute_portfolio_pnl(
            actual_positions,
            trade_date,
            trading_calendar,
            default_entry_date=portfolio_position_date,
            pnl_carry=pnl_carry,
        )
        portfolio_pnl = display_portfolio_pnl or state_portfolio_pnl
    carry_for_cache = {
        "cum_pnl": float((state_portfolio_pnl or {}).get("pnl_carry", 0) or 0),
        "cum_return": 0.0,
        "total_value": float((state_portfolio_pnl or {}).get("total_value", 0) or 0),
    }
    base_report = _format_report(
        trade_date=trade_date,
        next_trade_date=next_trade_date,
        latest_position_date=latest_dt.strftime("%Y-%m-%d"),
        cfg=cfg,
        target=target,
        actions=actions,
        metrics=metrics,
        mock=False,
        name_map=name_map,
        sector_map=sector_map,
        portfolio_pnl=portfolio_pnl,
        model_target=model_target,
    )
    # Overlay drawdown monitoring
    drawdown = _compute_cumulative_drawdown(report)
    overlay_warning = _check_overlay_monitor(config, drawdown)
    if overlay_warning:
        base_report = base_report.rstrip() + "\n\n" + overlay_warning
    if return_details:
        return base_report, {
            "previous_positions": _clone_position_snapshot(previous),
            "target_positions": target_for_cache,
            "executed_positions": executed_for_cache,
            "pnl_carry": carry_for_cache,
            "portfolio_pnl": state_portfolio_pnl,
            "display_portfolio_pnl": portfolio_pnl,
            "actions": [
                {
                    "action": action.action,
                    "instrument": action.instrument,
                    "shares": action.shares,
                    "price": action.price,
                    "value": action.value,
                }
                for action in actions
            ],
        }
    return base_report


def _last_metrics(report: pd.DataFrame) -> Dict[str, float]:
    if report is None or report.empty:
        return {}
    cols = [c for c in ("return", "cost", "bench") if c in report.columns]
    if not cols:
        return {}
    row = report.iloc[-1]
    return {col: float(row[col]) for col in cols if pd.notna(row[col])}


def _compute_cumulative_drawdown(report: pd.DataFrame) -> float:
    """Return the current cumulative drawdown from the backtest report."""
    if report is None or report.empty or "return" not in report.columns:
        return 0.0
    daily_ret = pd.to_numeric(report["return"], errors="coerce").fillna(0)
    cum = (1 + daily_ret).cumprod()
    running_max = cum.cummax()
    dd = (cum - running_max) / running_max
    return float(dd.iloc[-1]) if not dd.empty else 0.0


def _check_overlay_monitor(config: dict, drawdown: float) -> Optional[str]:
    """Check overlay drawdown against threshold; return warning string or None."""
    mon = config.get("overlay_monitor", {})
    if not mon.get("enabled", False):
        return None
    threshold = float(mon.get("drawdown_threshold", -0.15))
    if drawdown > threshold:
        return None
    baseline_cfg = mon.get("baseline_config", "config/daily_csi1000.yaml")
    baseline_topk = mon.get("baseline_topk", 15)
    baseline_n_drop = mon.get("baseline_n_drop", 3)
    baseline_hold = mon.get("baseline_hold_thresh", 5)
    return (
        f"⚠️ OVERLAY DRAWDOWN WARNING\n"
        f"当前累计回撤: {drawdown:.1%}，已超过阈值 {threshold:.0%}\n"
        f"建议切换至保守基线策略: {baseline_cfg}\n"
        f"基线参数: topk={baseline_topk} / n_drop={baseline_n_drop} / hold={baseline_hold}\n"
        f"(WFV证据: SVS是杠杆而非alpha，弱市放大损失)"
    )


def _mock_report(cfg: Dict[str, Any], trade_date: str, next_trade_date: str) -> str:
    previous = {
        "SH600216": {"shares": 800, "price": 12.40, "value": 9_920},
        "SZ002050": {"shares": 1200, "price": 8.80, "value": 10_560},
        "SZ300014": {"shares": 600, "price": 18.50, "value": 11_100},
        "SH603197": {"shares": 0, "price": 29.30, "value": 0},
    }
    target = {
        "SH600216": {"shares": 500, "price": 12.40, "value": 6_200},
        "SZ002050": {"shares": 1500, "price": 8.80, "value": 13_200},
        "SZ300014": {"shares": 600, "price": 18.50, "value": 11_100},
        "SH603197": {"shares": 1000, "price": 29.30, "value": 29_300},
    }
    actions = _diff_positions(previous, target)
    name_map = load_stock_names()
    sector_map = _load_sector_map({})
    return _format_report(
        trade_date=trade_date,
        next_trade_date=next_trade_date,
        latest_position_date=trade_date,
        cfg=cfg,
        target=target,
        actions=actions,
        metrics={"return": 0.0031, "cost": 0.0004},
        mock=True,
        name_map=name_map,
        sector_map=sector_map,
    )


def _cache_dir(cfg: Dict[str, Any]) -> Path:
    return _resolve_path(cfg.get("cache_dir", "signals/daily_rebalance_cache"))


def _cache_paths(cfg: Dict[str, Any], trade_date: str) -> Tuple[Path, Path]:
    cache_dir = _cache_dir(cfg)
    return cache_dir / f"rebalance_{trade_date}.json", cache_dir / "latest.json"


def _save_signal_cache(
    cfg: Dict[str, Any],
    trade_date: str,
    next_trade_date: str,
    report: str,
    mock: bool,
    details: Optional[Dict[str, Any]] = None,
) -> Path:
    cache_path, latest_path = _cache_paths(cfg, trade_date)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trade_date": trade_date,
        "next_trade_date": next_trade_date,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mock": mock,
        "strategy": {
            "market": cfg["market"],
            "topk": cfg["topk"],
            "n_drop": cfg["n_drop"],
            "hold_thresh": cfg["hold_thresh"],
            "start_date": cfg["start_date"],
        },
        "report": report,
    }
    if details:
        payload.update(details)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    cache_path.write_text(text + "\n", encoding="utf-8")
    latest_path.write_text(text + "\n", encoding="utf-8")
    logger.info("调仓信号缓存已保存: %s", cache_path)
    return cache_path


def _load_latest_signal_cache(cfg: Dict[str, Any]) -> Dict[str, Any]:
    latest_path = _cache_dir(cfg) / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(f"找不到调仓信号缓存: {latest_path}")
    return json.loads(latest_path.read_text(encoding="utf-8"))


def _cache_matches_today(payload: Dict[str, Any], today: pd.Timestamp) -> bool:
    next_trade_date = payload.get("next_trade_date")
    if not next_trade_date:
        return False
    return pd.Timestamp(next_trade_date).normalize() == today


def _reminder_title(label: str, next_trade_date: str) -> str:
    prefix = "开盘前" if label == "open" else "收盘前"
    return f"{prefix}调仓提醒 {next_trade_date}"


def _format_cached_reminder(payload: Dict[str, Any], label: str) -> str:
    prefix = "开盘前提醒" if label == "open" else "收盘前提醒"
    return "\n".join(
        [
            f"{prefix}: 请按昨日缓存信号执行/检查调仓",
            f"信号日: {payload.get('trade_date')}  执行日: {payload.get('next_trade_date')}",
            "",
            str(payload.get("report", "")).strip(),
        ]
    ).strip()


def _send_cached_reminder(
    config: dict,
    cfg: Dict[str, Any],
    config_path: Optional[str],
    today: pd.Timestamp,
    label: str,
    dry_run: bool,
    force: bool,
    skip_update: bool,
    mock: bool,
) -> None:
    today_str = today.strftime("%Y-%m-%d")
    payload = _load_reminder_payload(
        config=config,
        cfg=cfg,
        config_path=config_path,
        today=today,
        force=force,
        skip_update=skip_update,
        mock=mock,
    )

    if payload is None:
        return

    _, trading_calendar = _trading_calendar(config)
    if trading_calendar and today not in trading_calendar and not force:
        logger.info("%s 不是交易日，跳过提醒。", today_str)
        return

    report = _format_cached_reminder(payload, label)
    print(report)
    if dry_run:
        logger.info("dry-run 模式，跳过通知推送")
        return

    pusher = NotificationPusher(_notify_config(config, cfg["notify_channel"]))
    results = pusher.send(_reminder_title(label, today_str), report)
    for name, ok in results.items():
        logger.info("%s %s", "ok" if ok else "failed", name)
    if results and not all(results.values()):
        raise RuntimeError(f"提醒推送失败: {results}")


def _load_reminder_payload(
    config: dict,
    cfg: Dict[str, Any],
    config_path: Optional[str],
    today: pd.Timestamp,
    force: bool,
    skip_update: bool,
    mock: bool,
) -> Optional[Dict[str, Any]]:
    try:
        payload = _load_latest_signal_cache(cfg)
    except FileNotFoundError as exc:
        logger.warning("%s", exc)
    else:
        if _cache_matches_today(payload, today) or force:
            return payload
        logger.warning(
            "缓存执行日为 %s，今天是 %s，将尝试重新生成。",
            payload.get("next_trade_date"),
            today.strftime("%Y-%m-%d"),
        )

    if not cfg.get("reminder_rebuild_on_miss", True):
        logger.info("reminder_rebuild_on_miss=false，跳过缓存补救。")
        return None

    return _rebuild_signal_for_reminder(
        config=config,
        cfg=cfg,
        config_path=config_path,
        today=today,
        force=force,
        skip_update=skip_update,
        mock=mock,
    )


def _rebuild_signal_for_reminder(
    config: dict,
    cfg: Dict[str, Any],
    config_path: Optional[str],
    today: pd.Timestamp,
    force: bool,
    skip_update: bool,
    mock: bool,
) -> Optional[Dict[str, Any]]:
    today_str = today.strftime("%Y-%m-%d")
    if not skip_update and not mock:
        _run_update(config_path, create_tarball=cfg["create_update_tarball"])

    actual_calendar, trading_calendar = _trading_calendar(config)
    if trading_calendar and today not in trading_calendar and not force:
        logger.info("%s 不是交易日，跳过提醒补救。", today_str)
        return None

    signal_date, exact_previous = _previous_trading_day(today, trading_calendar)
    if not exact_previous:
        logger.warning("未在交易日历中找到上一交易日，暂按上一个工作日推断: %s", signal_date)

    if not mock:
        latest_actual = max(actual_calendar) if actual_calendar else None
        if latest_actual is None:
            raise RuntimeError("无法读取 qlib 实际交易日历 calendars/day.txt。")
        signal_ts = pd.Timestamp(signal_date).normalize()
        if latest_actual < signal_ts and not force:
            raise RuntimeError(
                f"qlib 数据尚未更新到 {signal_date}，当前最新数据日为 {latest_actual:%Y-%m-%d}。"
            )

    logger.info("提醒补救: 重新生成 %s -> %s 的调仓信号。", signal_date, today_str)
    signal_ts = pd.Timestamp(signal_date).normalize()
    run_cfg = _resolve_cfg_start_date(cfg, signal_ts, trading_calendar)
    run_config = _apply_strategy_config(config, run_cfg)

    details = None
    if mock:
        report = _mock_report(run_cfg, signal_date, today_str)
    else:
        actual_positions = None
        pnl_carry = None
        positions_arg = run_cfg.get("positions")
        if run_cfg.get("replay_from_initial_positions"):
            if not positions_arg:
                raise ValueError("replay_from_initial_positions 需要提供 positions 起始持仓。")
            initial_date = _positions_start_date(positions_arg, run_cfg, run_cfg.get("position_date"))
            initial_positions = _parse_positions_arg(positions_arg, initial_date)
            logger.info(
                "提醒补救使用起始持仓回放: %s（起始日 %s）。",
                list(initial_positions.keys()),
                initial_date,
            )
            actual_positions, pnl_carry = _replay_positions_from_initial(
                run_config,
                run_cfg,
                initial_positions,
                initial_date,
                signal_date,
                list(trading_calendar),
            )
        elif positions_arg:
            actual_positions = _parse_positions_arg(positions_arg, signal_date)
            logger.info("提醒补救使用 positions 实际持仓: %s", list(actual_positions.keys()))

        if not run_cfg.get("replay_from_initial_positions") and run_cfg.get("cache_roll_forward_positions", True):
            cached_state = _load_executed_state_from_cache(run_cfg, signal_date, list(trading_calendar))
            if cached_state is not None:
                if actual_positions is not None:
                    logger.info("提醒补救中上一条已执行缓存覆盖 positions。")
                actual_positions = cached_state["positions"]
                pnl_carry = cached_state.get("pnl_carry")
                display_portfolio_pnl = cached_state.get("display_portfolio_pnl")
            else:
                display_portfolio_pnl = None
        else:
            display_portfolio_pnl = None

        report, details = _run_real_rebalance(
            run_config,
            run_cfg,
            signal_date,
            today_str,
            actual_positions,
            list(trading_calendar),
            pnl_carry=pnl_carry,
            display_portfolio_pnl=display_portfolio_pnl,
            return_details=True,
        )

    _save_signal_cache(run_cfg, signal_date, today_str, report, mock=mock, details=details)
    return _load_latest_signal_cache(run_cfg)


def _load_sector_map(config: dict) -> Dict[str, str]:
    try:
        provider = SectorDataProvider(config)
        return provider.get_map() or {}
    except Exception:
        return {}


def _format_report(
    trade_date: str,
    next_trade_date: str,
    latest_position_date: str,
    cfg: Dict[str, Any],
    target: Dict[str, Dict[str, float]],
    actions: Iterable[RebalanceAction],
    metrics: Dict[str, float],
    mock: bool,
    name_map: Optional[Dict[str, str]] = None,
    sector_map: Optional[Dict[str, str]] = None,
    portfolio_pnl: Optional[Dict[str, Any]] = None,
    model_target: Optional[Dict[str, Dict[str, float]]] = None,
) -> str:
    title = "量化调仓信号"
    if mock:
        title += " MOCK"
    lines = [
        title,
        f"信号日: {trade_date}  执行日: {next_trade_date}",
        f"策略: {cfg['market']} / topk={cfg['topk']} / n_drop={cfg['n_drop']} / hold={cfg['hold_thresh']}",
        f"固定回测起点: {cfg['start_date']}  position日: {latest_position_date}",
        "价格/股数口径: 未复权收盘价，按目标市值折算为100股整数手",
    ]
    # Show real portfolio P&L when available (from --positions), otherwise fall back to backtest metrics
    if portfolio_pnl is not None:
        cum_pnl = portfolio_pnl["cum_pnl"]
        cum_ret = portfolio_pnl["cum_return"]
        daily_pnl = portfolio_pnl["daily_pnl"]
        daily_ret = portfolio_pnl["daily_return"]
        sign_cum = "+" if cum_pnl >= 0 else ""
        sign_day = "+" if daily_pnl >= 0 else ""
        lines.append(
            f"累计收益 {sign_cum}{cum_pnl:,.0f}元 ({sign_cum}{cum_ret:.2%})  "
            f"当日 {sign_day}{daily_pnl:,.0f}元 ({sign_day}{daily_ret:.2%})  "
            f"总市值 {portfolio_pnl['total_value']:,.0f}元"
        )
    elif metrics:
        daily_ret = metrics.get("return")
        cost = metrics.get("cost")
        parts = []
        if daily_ret is not None:
            parts.append(f"当日收益 {daily_ret:.2%}")
        if cost is not None:
            parts.append(f"交易成本 {cost:.2%}")
        if parts:
            lines.append(" | ".join(parts))

    actions = list(actions)
    lines.append("")
    lines.append("次交易日调仓动作:")
    if not actions:
        lines.append("无调仓动作，持仓保持不变。")
    else:
        label = {"buy": "买入", "reduce": "减仓", "sell": "卖出"}
        for item in actions:
            sign = "+" if item.action == "buy" else "-"
            price = f" @ {item.price:.2f}" if item.price > 0 else ""
            value = f" 约{item.value:,.0f}元" if item.value > 0 else ""
            name = name_map.get(item.instrument, "") if name_map else ""
            name_str = f" {name}" if name else ""
            lines.append(
                f"{label[item.action]} {item.instrument}{name_str}: {sign}{item.shares:.0f}股{price}{value}"
            )

    # Build per-stock P&L lookup for display in target positions
    stock_pnl_map: Dict[str, Dict[str, Any]] = {}
    if portfolio_pnl is not None:
        for s in portfolio_pnl.get("per_stock", []):
            stock_pnl_map[s["instrument"]] = s

    lines.append("")
    lines.append("目标持仓摘要:")
    if not target:
        lines.append("无目标持仓。")
    else:
        for inst, info in sorted(target.items()):
            name = name_map.get(inst, "") if name_map else ""
            sector = sector_map.get(inst, "") if sector_map else ""
            name_str = f" {name}" if name else ""
            sec_str = f" [{sector}]" if sector else ""
            parts = f"{inst}{name_str}{sec_str}: {info['shares']:.0f}股 约{info['value']:,.0f}元"
            # Append per-stock P&L and holding days when available
            sp = stock_pnl_map.get(inst)
            if sp:
                cum_sign = "+" if sp["cum_pnl"] >= 0 else ""
                pnl_str = f" | 累计{cum_sign}{sp['cum_pnl']:,.0f}元({cum_sign}{sp['cum_return']:.2%})"
                hold_str = f" 持{sp['days_held']}日" if sp["days_held"] is not None else ""
                parts += f"{pnl_str}{hold_str}"
            lines.append(parts)

    # Show model's original target (before hold protection) when symbols or shares differ.
    target_changed = False
    if model_target is not None:
        target_changed = set(model_target) != set(target) or any(
            abs(
                float(model_target.get(inst, {}).get("shares", 0))
                - float(target.get(inst, {}).get("shares", 0))
            ) >= 1
            for inst in set(model_target) & set(target)
        )
    if model_target is not None and target_changed:
        lines.append("")
        lines.append("模型选股目标（hold 保护前的回测选股）:")
        for inst, info in sorted(model_target.items()):
            name = name_map.get(inst, "") if name_map else ""
            sector = sector_map.get(inst, "") if sector_map else ""
            name_str = f" {name}" if name else ""
            sec_str = f" [{sector}]" if sector else ""
            protected_mark = " (受保护)" if inst in target else " (未持有)"
            lines.append(
                f"{inst}{name_str}{sec_str}: {info['shares']:.0f}股 约{info['value']:,.0f}元{protected_mark}"
            )
    return "\n".join(lines)


def _notify_config(config: dict, channel: str) -> dict:
    if channel == "all":
        return config

    patched = copy.deepcopy(config)
    notify_cfg = patched.get("notify")
    if not notify_cfg:
        notify_cfg = {
            key: patched.get(key, {})
            for key in ("bark", "pushplus", "dingtalk", "serverchan", "wechat_mp")
            if key in patched
        }
        patched["notify"] = notify_cfg
    for name in ("pushplus", "dingtalk", "serverchan", "wechat_mp"):
        if isinstance(notify_cfg.get(name), dict):
            notify_cfg[name]["enabled"] = False
    if isinstance(notify_cfg.get("bark"), dict):
        notify_cfg["bark"]["enabled"] = True
    return patched


def _send_report(config: dict, report: str, trade_date: str, dry_run: bool, channel: str) -> None:
    print(report)
    if dry_run:
        logger.info("dry-run 模式，跳过通知推送")
        return
    pusher = NotificationPusher(_notify_config(config, channel))
    results = pusher.send(f"量化调仓信号 {trade_date}", report)
    for name, ok in results.items():
        logger.info("%s %s", "ok" if ok else "failed", name)
    if results and not all(results.values()):
        raise RuntimeError(f"通知推送失败: {results}")


def main() -> None:
    args = _parse_args()
    raw_config = load_config(args.config)
    base_cfg = _daily_cfg(raw_config, args)

    trade_date = pd.Timestamp(args.today or datetime.now().strftime("%Y-%m-%d")).normalize()
    trade_date_str = trade_date.strftime("%Y-%m-%d")
    _, initial_trading_calendar = _trading_calendar(raw_config)
    cfg = _resolve_cfg_start_date(base_cfg, trade_date, initial_trading_calendar)
    config = _apply_strategy_config(raw_config, cfg)

    # ── Regime-aware parameter switching (optional) ────────────────────────────
    try:
        from quant_ex.strategy.regime_switch import RegimeStrategySwitch

        regime_switch = RegimeStrategySwitch.from_config(config)
        if regime_switch is not None:
            # Need price_data to detect regime; reuse data_loader
            dl = DataLoader(config)
            instruments = cfg.get("market", config.get("market", {}).get("name", "csi300"))
            price_data = dl.load_price_data(
                instruments=instruments,
                start_time=cfg["start_date"],
                end_time=trade_date_str,
            )
            regime_label = regime_switch.detect_regime(price_data)
            cfg = regime_switch.adjust_cfg(cfg, regime_label)
            config = _apply_strategy_config(raw_config, cfg)
            # Gate overlay (stock_vs_sector_filter) by regime
            apply_overlay_gating(config, cfg.get("overlay_enabled", True))
    except Exception as exc:
        logger.warning("Regime switch integration skipped: %s", exc)

    # ── 刷新外部数据缓存 ─────────────────────────────────────────────────────────
    try:
        from quant_ex.data.fetchers import NorthboundFetcher, FinancialFetcher
        feat_cfg = config.get("model", {}).get("features", {})
        factor_names = [f.get("name") for f in feat_cfg.get("factors", []) if f.get("name")]

        if "northbound" in factor_names:
            NorthboundFetcher(cache_dir="./cache/northbound", cache_ttl_days=1).refresh_cache([])
            logger.info("北向资金缓存已刷新")

        if "fundamental" in factor_names:
            fund_cfg = next((f for f in feat_cfg.get("factors", []) if f.get("name") == "fundamental"), {})
            metrics = fund_cfg.get("metrics", ["valuation"])
            if any(m not in ("pe_ttm", "pb", "ps_ttm", "dyr", "valuation") for m in metrics):
                FinancialFetcher(cache_dir="./cache/financial", cache_ttl_days=7).refresh_cache([])
                logger.info("财务数据缓存已刷新")
    except Exception as exc:
        logger.warning(f"外部数据缓存刷新跳过: {exc}")

    logger.info("=== 收盘后调仓任务 %s ===", trade_date_str)

    if args.remind:
        _send_cached_reminder(
            config=config,
            cfg=cfg,
            config_path=args.config,
            today=trade_date,
            label=args.reminder_label,
            dry_run=args.dry_run,
            force=args.force,
            skip_update=args.skip_update,
            mock=args.mock,
        )
        return

    if args.mock:
        _, calendar = _trading_calendar(config)
        next_trade_date, _ = _next_trading_day(trade_date, calendar)
        report = _mock_report(cfg, trade_date_str, next_trade_date)
        _save_signal_cache(cfg, trade_date_str, next_trade_date, report, mock=True)
        _send_report(config, report, trade_date_str, args.dry_run, cfg["notify_channel"])
        return

    if not args.skip_update:
        # 若 trade_date 已在 qlib 实际数据日历中，无需重新拉取。
        _pre_actual, _ = _trading_calendar(config)
        _latest_pre = max(_pre_actual) if _pre_actual else None
        if _latest_pre is not None and _latest_pre >= trade_date:
            logger.info("qlib 数据已包含 %s，跳过数据更新。", trade_date_str)
        else:
            _run_update(args.config, create_tarball=cfg["create_update_tarball"])

    actual_calendar, trading_calendar = _trading_calendar(config)
    if trade_date not in trading_calendar and not args.force:
        msg = f"{trade_date_str} 不是交易日，跳过调仓任务。"
        logger.info(msg)
        if cfg["notify_on_skip"]:
            _send_report(config, msg, trade_date_str, args.dry_run, cfg["notify_channel"])
        return

    latest_actual = max(actual_calendar) if actual_calendar else None
    if latest_actual is None:
        raise RuntimeError("无法读取 qlib 实际交易日历 calendars/day.txt。")
    # 信号生成基于前一交易日收盘数据，因此只需 qlib 数据涵盖前一交易日即可。
    prev_trade_date_str, _ = _previous_trading_day(trade_date, list(trading_calendar))
    prev_trade_date = pd.Timestamp(prev_trade_date_str)
    if latest_actual < prev_trade_date and not args.force:
        raise RuntimeError(
            f"qlib 数据尚未更新到前一交易日 {prev_trade_date_str}，当前最新数据日为 {latest_actual:%Y-%m-%d}。"
        )

    next_trade_date, exact_next = _next_trading_day(trade_date, trading_calendar)
    if not exact_next:
        logger.warning("未在交易日历中找到下一交易日，暂按下一个工作日推断: %s", next_trade_date)

    actual_positions: Optional[Dict[str, Dict[str, float]]] = None
    pnl_carry: Optional[Dict[str, float]] = None
    display_portfolio_pnl = None
    if args.replay_from_initial_positions:
        if not args.positions:
            raise ValueError("--replay-from-initial-positions 需要同时提供 --positions 起始持仓。")
        initial_date = _positions_start_date(args.positions, cfg, cfg.get("position_date"))
        initial_positions = _parse_positions_arg(args.positions, initial_date)
        logger.info(
            "已解析 --positions 起始持仓: %s（起始日 %s）。",
            list(initial_positions.keys()),
            initial_date,
        )
        actual_positions, pnl_carry = _replay_positions_from_initial(
            config,
            cfg,
            initial_positions,
            initial_date,
            trade_date_str,
            list(trading_calendar),
        )
    elif args.positions:
        actual_positions = _parse_positions_arg(args.positions, trade_date_str)
        logger.info("已解析 --positions 实际持仓: %s", list(actual_positions.keys()))

    if not args.replay_from_initial_positions:
        cached_state = _load_executed_state_from_cache(cfg, trade_date_str, list(trading_calendar))
        if cached_state is not None:
            if actual_positions is not None:
                logger.info("上一条已执行缓存覆盖 --positions；如昨日信号未执行，请加 --no-cache-roll-forward。")
            actual_positions = cached_state["positions"]
            pnl_carry = cached_state.get("pnl_carry")
            display_portfolio_pnl = cached_state.get("display_portfolio_pnl")
            if pnl_carry and float(pnl_carry.get("cum_pnl", 0) or 0) != 0:
                logger.info("延续历史累计收益: %.0f 元。", float(pnl_carry.get("cum_pnl", 0) or 0))

    report, details = _run_real_rebalance(
        config,
        cfg,
        trade_date_str,
        next_trade_date,
        actual_positions,
        list(trading_calendar),
        pnl_carry=pnl_carry,
        display_portfolio_pnl=display_portfolio_pnl,
        return_details=True,
    )
    _save_signal_cache(cfg, trade_date_str, next_trade_date, report, mock=False, details=details)
    _send_report(config, report, trade_date_str, args.dry_run, cfg["notify_channel"])


if __name__ == "__main__":
    main()
