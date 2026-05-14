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


def _ensure_spa_dist():
    dist = PROJECT_ROOT / "web" / "frontend" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")


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
