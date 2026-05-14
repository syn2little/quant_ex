import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("quant_ex")
package.__path__ = [str(REPO_ROOT)]
sys.modules.setdefault("quant_ex", package)

from web.api import app as app_module


def test_backtest_page_serves(tmp_path, monkeypatch):
    fake_app_file = tmp_path / "web" / "api" / "app.py"
    fake_app_file.parent.mkdir(parents=True)
    fake_app_file.write_text("", encoding="utf-8")
    dist_dir = tmp_path / "web" / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    monkeypatch.setattr(app_module, "Path", lambda _value: fake_app_file)

    client = TestClient(app_module.create_app())
    response = client.get("/backtest")

    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_backtest_grid_dry_run_candidate_count():
    client = TestClient(app_module.create_app())
    response = client.post(
        "/api/backtest/grid",
        json={
            "model_path": "models/dummy.pkl",
            "topk_list": [5, 10, 20],
            "n_drop_list": [1, 3],
            "hold_thresh_list": [5, 8, 10],
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview"]["candidate_count"] == 18
    assert body["preview"]["rank_metric"] == "information_ratio"


def test_backtest_wfv_dry_run_rank_metric_locked():
    client = TestClient(app_module.create_app())
    response = client.post(
        "/api/backtest/walk-forward",
        json={
            "train_universes": ["csi300"],
            "eval_market": "csi300",
            "topk_list": [5],
            "n_drop_list": [1],
            "hold_thresh_list": [5],
            "rank_metric": "information_ratio",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview"]["rank_metric"] == "information_ratio"
