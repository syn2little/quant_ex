import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if "quant_ex" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "quant_ex",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["quant_ex"] = module
    spec.loader.exec_module(module)

from web.api.app import create_app


def test_models_page_serves():
    client = TestClient(create_app())

    r = client.get("/models")

    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_models_train_dry_run_preview_includes_final_market():
    client = TestClient(create_app())

    r = client.post(
        "/api/models/train",
        json={
            "model_type": "lgbm",
            "tag": "ci_test",
            "market": "csi1000",
            "dry_run": True,
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["preview"]["final_market"] == "csi1000"
    assert body["preview"]["config_source"]["type"] == "default"
    assert "estimated_outputs" in body["preview"]
    assert "effective_params" in body["preview"]
