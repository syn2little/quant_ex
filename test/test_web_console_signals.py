from pathlib import Path
import sys
import types

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "quant_ex" not in sys.modules:
    package = types.ModuleType("quant_ex")
    package.__path__ = [str(PROJECT_ROOT)]
    sys.modules["quant_ex"] = package

from web.api.app import create_app
import web.api.routers.signals as signals_router


def _ensure_spa_dist():
    dist = PROJECT_ROOT / "web" / "frontend" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    index = dist / "index.html"
    if not index.exists():
        index.write_text('<div id="root"></div>', encoding="utf-8")


def test_signals_page_serves():
    _ensure_spa_dist()
    client = TestClient(create_app())
    r = client.get("/signals")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_signals_rebalance_real_send_requires_confirm():
    client = TestClient(create_app())
    r = client.post(
        "/api/signals/rebalance",
        json={
            "config": "config/daily_csi1000.yaml",
            "dry_run": False,
            "confirm_send": False,
            "skip_update": True,
        },
    )
    assert r.status_code == 400


def test_signals_notify_test_real_send_requires_confirm():
    client = TestClient(create_app())
    r = client.post(
        "/api/signals/notify-test",
        json={
            "channel": "bark",
            "message": "Should not send",
            "dry_run": False,
            "confirm_send": False,
        },
    )
    assert r.status_code == 400


def test_signals_rebalance_dry_run_envelope():
    client = TestClient(create_app())
    r = client.post(
        "/api/signals/rebalance",
        json={
            "config": "config/daily_csi1000.yaml",
            "dry_run": True,
            "skip_update": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert "diff" in body["preview"]
    assert "notify_template" in body["preview"]


def test_signals_rebalance_history_parses_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "daily_rebalance_cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "rebalance_2026-05-14.json"
    cache_file.write_text(
        """
        {
          "trade_date": "2026-05-14",
          "next_trade_date": "2026-05-15",
          "created_at": "2026-05-14T18:37:31",
          "mock": true,
          "strategy": {"market": "csi1000", "topk": 15},
          "display_portfolio_pnl": {"total_value": 120000},
          "target_positions": {
            "SH600000": {"shares": 1000, "price": 10, "value": 10000},
            "SZ000001": {"shares": 2000, "price": 20, "value": 40000}
          },
          "actions": [
            {"side": "buy", "instrument": "SH600000", "amount": 10000},
            {"side": "sell", "instrument": "SZ000002", "amount": 5000}
          ],
          "report": "cache report"
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        signals_router,
        "get_config",
        lambda: {"daily_rebalance": {"cache_dir": str(cache_dir)}},
    )

    client = TestClient(create_app())
    r = client.get("/api/signals/rebalance-history")

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    item = body[0]
    assert item["filename"] == cache_file.name
    assert item["trade_date"] == "2026-05-14"
    assert item["portfolio_value"] == 120000
    assert item["target_value"] == 50000
    assert item["holdings_count"] == 2
    assert item["top_holdings"][0]["instrument"] == "SZ000001"
    assert item["top_holdings"][0]["weight"] == 0.8
    assert item["action_summary"]["buy_count"] == 1
    assert item["action_summary"]["sell_amount"] == 5000


def test_signals_rebalance_history_report_action_fallback(monkeypatch, tmp_path):
    cache_dir = tmp_path / "daily_rebalance_cache"
    cache_dir.mkdir()
    (cache_dir / "rebalance_2026-05-15.json").write_text(
        """
        {
          "trade_date": "2026-05-15",
          "mock": false,
          "report": "次交易日调仓动作:\\n减仓 SH600216 浙江医药: -300股 @ 12.40 约3,720元\\n买入 SH603197 保隆科技: +1000股 @ 29.30 约29,300元\\n\\n目标持仓摘要:\\nSH600216 浙江医药 [原料药]: 500股 约6,200元\\nSH603197 保隆科技 [其他汽车零部件]: 1000股 约29,300元"
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        signals_router,
        "get_config",
        lambda: {"daily_rebalance": {"cache_dir": str(cache_dir)}},
    )

    client = TestClient(create_app())
    r = client.get("/api/signals/rebalance-history")

    assert r.status_code == 200
    item = r.json()[0]
    assert item["action_summary"]["buy_count"] == 1
    assert item["action_summary"]["sell_count"] == 1
    assert item["action_summary"]["buy_amount"] == 29300
    assert item["action_summary"]["sell_amount"] == 3720
    assert item["target_value"] == 35500
    assert item["top_holdings"][0]["instrument"] == "SH603197"
