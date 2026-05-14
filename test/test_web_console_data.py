import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if "quant_ex" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "quant_ex",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        sys.modules["quant_ex"] = module
        spec.loader.exec_module(module)

from web.api.app import create_app


def test_data_explorer_page_serves():
    client = TestClient(create_app())
    response = client.get("/data-explorer")

    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_data_fetch_dry_run_records_task():
    client = TestClient(create_app())
    response = client.post(
        "/api/data/fetch",
        json={
            "data_types": ["prices"],
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    task_id = body["task_id"]

    tasks = client.get("/api/system/tasks").json()
    matching = [task for task in tasks if task["task_id"] == task_id]
    assert len(matching) == 1
    assert matching[0]["page_key"] == "data"
    assert matching[0]["action_key"] == "data.fetch"


def test_data_purge_dry_run_records_task():
    client = TestClient(create_app())
    response = client.delete("/api/data/cache/financial/expired?dry_run=true")

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["data_type"] == "financial"

    tasks = client.get("/api/system/tasks").json()
    matching = [task for task in tasks if task["task_id"] == body["task_id"]]
    assert len(matching) == 1
    assert matching[0]["page_key"] == "data"
    assert matching[0]["action_key"] == "data.purge_expired"
