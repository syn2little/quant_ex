import copy
import json
import logging
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from web.api.deps import PROJECT_ROOT, SIGNALS_DIR, get_config
from web.api.services.task_manager import get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_ACTION_RE = re.compile(
    r"^(?P<side>买入|加仓|减仓|卖出)\s+(?P<instrument>[A-Z]{2}\d{6})\s+(?P<name>[^:：]+).*?约(?P<amount>[\d,]+(?:\.\d+)?)元"
)
_HOLDING_RE = re.compile(
    r"^(?P<instrument>[A-Z]{2}\d{6})\s+(?P<name>[^\[:：]+)(?:\s+\[[^\]]+\])?:\s+(?P<shares>[\d,]+(?:\.\d+)?)股\s+约(?P<value>[\d,]+(?:\.\d+)?)元"
)


def _safe_path(base_dir, filename: str):
    """Prevent path traversal."""
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid filename")
    return base_dir / filename


def _resolve_project_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved


def _signal_output_path(config_path: Optional[str]) -> Path:
    from quant_ex.utils.config import load_config

    config = load_config(config_path) if config_path else get_config()
    signal_dir = _resolve_project_path(config.get("paths", {}).get("signal_dir", "./signals"))
    return signal_dir / f"signal_{date.today().isoformat()}.txt"


def _rebalance_cache_candidates(req: "RebalanceRequest") -> list[Path]:
    from quant_ex.utils.config import load_config

    config = load_config(req.config) if req.config else get_config()
    daily_cfg = config.get("daily_rebalance", {})
    cache_dir = _resolve_project_path(daily_cfg.get("cache_dir", "signals/daily_rebalance_cache"))
    trade_date = date.today().isoformat()
    return [cache_dir / f"rebalance_{trade_date}.json", cache_dir / "latest.json"]


def _fresh_existing_paths(paths: list[Path], started_at: float) -> list[str]:
    result_paths = []
    for path in paths:
        try:
            if path.exists() and path.stat().st_mtime >= started_at:
                result_paths.append(str(path))
        except OSError:
            continue
    return result_paths


def _rebalance_cache_dir() -> Path:
    config = get_config()
    daily_cfg = config.get("daily_rebalance", {})
    return _resolve_project_path(daily_cfg.get("cache_dir", "signals/daily_rebalance_cache"))


def _as_float(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _position_rows(positions: object) -> list[dict]:
    if not isinstance(positions, dict):
        return []
    rows = []
    for instrument, payload in positions.items():
        if not isinstance(payload, dict):
            continue
        value = _as_float(payload.get("value"))
        rows.append(
            {
                "instrument": str(instrument),
                "shares": _as_float(payload.get("shares")),
                "price": _as_float(payload.get("price")),
                "value": value,
                "weight": None,
                "entry_date": payload.get("entry_date"),
            }
        )
    total = sum(row["value"] or 0 for row in rows)
    if total > 0:
        for row in rows:
            row["weight"] = (row["value"] or 0) / total
    return sorted(rows, key=lambda row: row["value"] or 0, reverse=True)


def _report_holding_rows(report: object) -> list[dict]:
    if not isinstance(report, str):
        return []
    rows = []
    for line in report.splitlines():
        match = _HOLDING_RE.search(line.strip())
        if not match:
            continue
        rows.append(
            {
                "instrument": match.group("instrument"),
                "shares": _as_float(match.group("shares")),
                "price": None,
                "value": _as_float(match.group("value")),
                "weight": None,
                "entry_date": None,
            }
        )
    total = sum(row["value"] or 0 for row in rows)
    if total > 0:
        for row in rows:
            row["weight"] = (row["value"] or 0) / total
    return sorted(rows, key=lambda row: row["value"] or 0, reverse=True)


def _action_rows(data: dict) -> list[dict]:
    raw_actions = data.get("actions")
    rows = []
    if isinstance(raw_actions, list):
        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            side = str(action.get("side") or action.get("action") or "").lower()
            amount = _as_float(
                action.get("amount")
                or action.get("value")
                or action.get("trade_value")
                or action.get("action_value")
            )
            rows.append(
                {
                    "side": "sell" if "sell" in side or side in {"减仓", "卖出"} else "buy",
                    "instrument": action.get("instrument") or action.get("symbol"),
                    "name": action.get("name"),
                    "amount": abs(amount) if amount is not None else None,
                }
            )
    report = data.get("report")
    if not rows and isinstance(report, str):
        for line in report.splitlines():
            match = _ACTION_RE.search(line.strip())
            if not match:
                continue
            side_text = match.group("side")
            rows.append(
                {
                    "side": "sell" if side_text in {"减仓", "卖出"} else "buy",
                    "instrument": match.group("instrument"),
                    "name": match.group("name").strip(),
                    "amount": _as_float(match.group("amount")),
                }
            )
    return rows


def _value_from_positions(rows: list[dict]) -> Optional[float]:
    total = sum(row["value"] or 0 for row in rows)
    return total if total > 0 else None


def _strategy_identity(strategy: object) -> tuple[str, str]:
    if not isinstance(strategy, dict):
        return "unknown", "unknown strategy"

    identity = {
        key: strategy.get(key)
        for key in ("market", "topk", "n_drop", "hold_thresh", "start_date")
        if strategy.get(key) is not None
    }
    signature = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    label = (
        f"{identity.get('market', '-')}"
        f" / topk={identity.get('topk', '-')}"
        f" / n_drop={identity.get('n_drop', '-')}"
        f" / hold={identity.get('hold_thresh', '-')}"
        f" / start={identity.get('start_date', '-')}"
    )
    return signature, label


def _parse_rebalance_cache(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to parse rebalance cache %s", path, exc_info=True)
        return None
    if not isinstance(data, dict):
        return None

    target_holdings = _position_rows(data.get("target_positions") or data.get("executed_positions"))
    if not target_holdings:
        target_holdings = _report_holding_rows(data.get("report"))
    executed_holdings = _position_rows(data.get("executed_positions"))
    value_source = data.get("display_portfolio_pnl") or data.get("portfolio_pnl") or data.get("pnl_carry") or {}
    portfolio_value = _as_float(value_source.get("total_value")) if isinstance(value_source, dict) else None
    target_value = _value_from_positions(target_holdings)
    actions = _action_rows(data)
    buy_amount = sum(action["amount"] or 0 for action in actions if action["side"] == "buy")
    sell_amount = sum(action["amount"] or 0 for action in actions if action["side"] == "sell")
    stat = path.stat()
    strategy = data.get("strategy") if isinstance(data.get("strategy"), dict) else {}
    strategy_signature, strategy_label = _strategy_identity(strategy)

    return {
        "filename": path.name,
        "path": str(path),
        "size_kb": round(stat.st_size / 1024, 1),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "trade_date": data.get("trade_date"),
        "next_trade_date": data.get("next_trade_date"),
        "created_at": data.get("created_at"),
        "mock": bool(data.get("mock", False)),
        "strategy": strategy,
        "strategy_signature": strategy_signature,
        "strategy_label": strategy_label,
        "portfolio_value": portfolio_value,
        "target_value": target_value,
        "holdings_count": len(target_holdings or executed_holdings),
        "top_holdings": target_holdings[:8],
        "actions": actions,
        "action_summary": {
            "buy_count": sum(1 for action in actions if action["side"] == "buy"),
            "sell_count": sum(1 for action in actions if action["side"] == "sell"),
            "buy_amount": buy_amount,
            "sell_amount": sell_amount,
            "net_amount": buy_amount - sell_amount,
        },
        "report": data.get("report") if isinstance(data.get("report"), str) else "",
    }


@router.get("/regime")
async def get_regime():
    config = get_config()
    try:
        from quant_ex.strategy.regime_switch import RegimeStrategySwitch
        rss = RegimeStrategySwitch.from_config(config)
        if rss is None:
            return {"enabled": False, "regime": None, "label": None}
        return {"enabled": True, "regime": None, "label": "requires_price_data"}
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


class GenerateSignalRequest(BaseModel):
    model_path: str
    account: float = 1000000
    positions: Optional[str] = None
    dry_run: bool = True
    universe: Optional[str] = None
    refresh_cache: bool = False
    config: Optional[str] = None
    config_override: Optional[str] = None
    position_date: Optional[str] = None
    min_action_value: Optional[float] = None

    @field_validator("model_path", "positions", "universe", "config", "config_override", "position_date")
    @classmethod
    def strings_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("string fields must not be blank")
        return value


@router.post("/generate")
async def generate_signal(req: GenerateSignalRequest):
    tm = get_task_manager()
    if req.dry_run:
        from datetime import date

        preview = {
            "model_path": req.model_path,
            "target_date": req.position_date or date.today().isoformat(),
            "universe": req.universe,
            "account": req.account,
            "positions": req.positions,
            "writes_signal_file": False,
            "config_override": req.config_override or req.config,
        }
        task_id = await tm.start_sync_task(
            "signal_generate_dry_run",
            lambda: preview,
            page_key="signals",
            action_key="signals.generate",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _generate():
        from quant_ex.run_daily import main as daily_main

        positions = {}
        if req.positions:
            for pair in req.positions.split(","):
                sym, qty = pair.strip().split(":")
                positions[sym] = float(qty)

        signal_path = daily_main(
            config_path=req.config_override or req.config,
            model_path=req.model_path,
            account=req.account,
            current_positions=positions if positions else None,
            dry_run=False,
        )
        if signal_path is None:
            signal_path = _signal_output_path(req.config_override or req.config)
        return {"status": "completed", "result_paths": [str(signal_path)]}

    task_id = await tm.start_sync_task(
        "signal_generate",
        _generate,
        page_key="signals",
        action_key="signals.generate",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


class RebalanceRequest(BaseModel):
    mock: bool = True
    dry_run: bool = True
    confirm_send: bool = False
    config: Optional[str] = None
    positions: Optional[str] = None
    position_date: Optional[str] = None
    min_action_value: Optional[float] = None
    skip_update: bool = True
    force: bool = False
    notify_channel: Optional[str] = None

    @field_validator("config", "positions", "position_date", "notify_channel")
    @classmethod
    def strings_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("string fields must not be blank")
        return value


def _build_rebalance_cmd(req: RebalanceRequest) -> list[str]:
    cmd = [sys.executable, str(PROJECT_ROOT / "run_scheduled_rebalance.py")]
    if req.mock:
        cmd.append("--mock")
    if req.dry_run:
        cmd.append("--dry-run")
    if req.config:
        cmd.extend(["--config", req.config])
    if req.positions:
        cmd.extend(["--positions", req.positions])
    if req.position_date:
        cmd.extend(["--position-date", req.position_date])
    if req.min_action_value is not None:
        cmd.extend(["--min-action-value", str(req.min_action_value)])
    if req.skip_update:
        cmd.append("--skip-update")
    if req.force:
        cmd.append("--force")
    if req.notify_channel:
        cmd.extend(["--notify-channel", req.notify_channel])
    return cmd


def _parse_positions(positions: Optional[str]) -> dict[str, float]:
    parsed = {}
    if not positions:
        return parsed
    for pair in positions.split(","):
        if not pair.strip() or ":" not in pair:
            continue
        symbol, value = pair.strip().split(":", 1)
        try:
            parsed[symbol.strip()] = float(value)
        except ValueError:
            parsed[symbol.strip()] = 0.0
    return parsed


def _compute_position_diff(req: RebalanceRequest) -> dict:
    current = _parse_positions(req.positions)
    return {
        "buys": [],
        "sells": [],
        "net_value": 0.0,
        "current_positions": current,
        "min_action_value": req.min_action_value,
    }


def _render_notify_template(req: RebalanceRequest) -> dict:
    return {
        "title": "Rebalance preview",
        "config": req.config,
        "channel": req.notify_channel,
        "dry_run": req.dry_run,
    }


@router.post("/rebalance")
async def run_rebalance(req: RebalanceRequest):
    tm = get_task_manager()
    if not req.dry_run and not req.confirm_send:
        raise HTTPException(status_code=400, detail="Real rebalance requires confirm_send=true.")

    if req.dry_run:
        preview = {
            "config": req.config,
            "diff": _compute_position_diff(req),
            "notify_template": _render_notify_template(req),
            "notify_channel": req.notify_channel,
        }
        task_id = await tm.start_sync_task(
            "rebalance_dry_run",
            lambda: preview,
            page_key="signals",
            action_key="signals.rebalance",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _run():
        cmd = _build_rebalance_cmd(req)
        candidates = _rebalance_cache_candidates(req)
        started_at = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Rebalance failed (exit {result.returncode}): {result.stderr[-500:]}")
        return {
            "stdout": result.stdout[-2000:],
            "returncode": result.returncode,
            "result_paths": _fresh_existing_paths(candidates, started_at),
        }

    task_id = await tm.start_sync_task(
        "rebalance",
        _run,
        page_key="signals",
        action_key="signals.rebalance",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


class NotifyTestRequest(BaseModel):
    title: str = Field(default="Notification test", min_length=1)
    content: Optional[str] = None
    message: Optional[str] = None
    channel: Optional[str] = None
    dry_run: bool = True
    confirm_send: bool = False

    @field_validator("content", "message", "channel")
    @classmethod
    def strings_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("string fields must not be blank")
        return value


_NOTIFY_CHANNELS = {"bark", "pushplus", "dingtalk", "serverchan", "wechat_mp", "all"}


def _enabled_notify_channels(config: dict) -> list[str]:
    notify_cfg = config.get("notify") or {
        key: config.get(key, {})
        for key in ("bark", "pushplus", "dingtalk", "serverchan", "wechat_mp")
        if key in config
    }
    return [
        name
        for name, cfg in notify_cfg.items()
        if isinstance(cfg, dict) and cfg.get("enabled", False)
    ]


def _notify_config_for_channel(config: dict, channel: Optional[str]) -> dict:
    if not channel or channel == "all":
        return config
    if channel not in _NOTIFY_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unknown notification channel: {channel}")

    patched = copy.deepcopy(config)
    notify_cfg = patched.get("notify")
    if not notify_cfg:
        notify_cfg = {
            key: patched.get(key, {})
            for key in ("bark", "pushplus", "dingtalk", "serverchan", "wechat_mp")
            if key in patched
        }
        patched["notify"] = notify_cfg

    for name, cfg in notify_cfg.items():
        if isinstance(cfg, dict):
            cfg["enabled"] = name == channel
    return patched


@router.post("/notify-test")
async def send_notify_test(req: NotifyTestRequest):
    config = get_config()
    selected_channel = req.channel or "all"
    if selected_channel not in _NOTIFY_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unknown notification channel: {selected_channel}")

    enabled_channels = _enabled_notify_channels(_notify_config_for_channel(config, selected_channel))
    content = req.message or req.content or "Preview only"
    tm = get_task_manager()
    if req.dry_run:
        preview = {
            "channel": selected_channel,
            "channels": enabled_channels,
            "target_masked": True,
            "title": req.title,
            "content": content,
        }
        task_id = await tm.start_sync_task(
            "notify_test_dry_run",
            lambda: preview,
            page_key="signals",
            action_key="signals.notify_test",
        )
        return {
            "task_id": task_id,
            "success": True,
            "dry_run": True,
            "sent": False,
            "channels": enabled_channels,
            "preview": preview,
        }
    if not req.confirm_send:
        raise HTTPException(
            status_code=400,
            detail="Real notification requires confirm_send=true.",
        )

    try:
        def _send() -> dict:
            from quant_ex.notify.pusher import NotificationPusher

            pusher = NotificationPusher(_notify_config_for_channel(config, selected_channel))
            results = pusher.send(title=req.title, content=content)
            return {
                "success": all(results.values()) if results else False,
                "sent": True,
                "results": results,
                "result_paths": [],
            }

        task_id = await tm.start_sync_task(
            "notify_test",
            _send,
            page_key="signals",
            action_key="signals.notify_test",
        )
        return {"task_id": task_id, "dry_run": False, "preview": None, "sent": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def signal_history():
    if not SIGNALS_DIR.exists():
        return []
    results = []
    for f in sorted(SIGNALS_DIR.glob("signal_*.txt"), reverse=True):
        results.append({
            "filename": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return results


@router.get("/rebalance-history")
async def rebalance_history():
    cache_dir = _rebalance_cache_dir()
    if not cache_dir.exists():
        return []
    items = []
    for path in sorted(cache_dir.glob("rebalance_*.json"), reverse=True):
        parsed = _parse_rebalance_cache(path)
        if parsed:
            items.append(parsed)
    return items


@router.get("/history/{filename}")
async def get_signal(filename: str):
    path = _safe_path(SIGNALS_DIR, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Signal file not found")
    return {"content": path.read_text(encoding="utf-8")}
