"""E2E coverage for dashboard console task wiring.

The test expects the built FastAPI dashboard to be running. Start it with:

    ./.venv/bin/python -m uvicorn web.api.app:app --host 127.0.0.1 --port 8000

The browser test uses Chrome DevTools Protocol directly so the repo does not
need a Playwright dependency.
"""
from __future__ import annotations

import os
import json
import shutil
import socket
import subprocess
import tempfile
import time
from itertools import count
from pathlib import Path
from urllib.parse import quote

import pytest
import requests

try:
    import websocket
except Exception:  # pragma: no cover - environment-dependent skip path
    websocket = None


SERVER_URL = os.environ.get("WEB_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def server_url() -> str:
    for _ in range(30):
        try:
            response = requests.get(f"{SERVER_URL}/api/system/health", timeout=1)
            if response.status_code == 200:
                return SERVER_URL
        except requests.RequestException:
            time.sleep(0.5)
    pytest.skip(f"Web server not running at {SERVER_URL}")


@pytest.fixture(scope="module")
def e2e_model_file():
    models_dir = PROJECT_ROOT / "models"
    models_dir.mkdir(exist_ok=True)
    model_file = models_dir / "e2e_dummy.pkl"
    model_file.write_bytes(b"e2e")
    try:
        yield model_file
    finally:
        model_file.unlink(missing_ok=True)


def _find_chrome() -> str | None:
    candidates = [
        os.environ.get("CHROME_BIN"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    return next((path for path in candidates if path and Path(path).exists()), None)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class CDPPage:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self._ids = count(1)

    def close(self) -> None:
        self.ws.close()

    def command(self, method: str, params: dict | None = None) -> dict:
        message_id = next(self._ids)
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = self.ws.recv()
            data = json.loads(message)
            if data.get("id") == message_id:
                if "error" in data:
                    raise AssertionError(data["error"])
                return data.get("result", {})

    def evaluate(self, expression: str):
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        value = result.get("result", {})
        if "exceptionDetails" in result:
            raise AssertionError(result["exceptionDetails"])
        return value.get("value")

    def navigate(self, url: str) -> None:
        self.command("Page.navigate", {"url": url})
        assert self.evaluate(
            """
            (async () => {
              const deadline = Date.now() + 8000;
              while (Date.now() < deadline) {
                if (document.querySelector("#root")) return true;
                await new Promise((resolve) => setTimeout(resolve, 100));
              }
              return false;
            })()
            """
        )


@pytest.fixture(scope="module")
def cdp_page(server_url: str):
    if websocket is None:
        pytest.skip("websocket-client is not installed")
    chrome = _find_chrome()
    if chrome is None:
        pytest.skip("Chrome/Chromium not found for CDP e2e")

    port = _free_port()
    user_data_dir = tempfile.mkdtemp(prefix="quant-ex-cdp-")
    proc = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        debug_base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try:
                if requests.get(f"{debug_base}/json/version", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            pytest.skip("Chrome CDP endpoint did not start")

        target = requests.put(f"{debug_base}/json/new?{quote(server_url, safe=':/')}", timeout=3).json()
        page = CDPPage(target["webSocketDebuggerUrl"])
        page.command("Runtime.enable")
        page.command("Page.enable")
        page.evaluate("localStorage.setItem('lang', 'en')")
        yield page
        page.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(user_data_dir, ignore_errors=True)


@pytest.mark.parametrize("path", ["/data-explorer", "/models", "/backtest", "/signals"])
def test_console_spa_routes_render(server_url: str, path: str):
    response = requests.get(f"{server_url}{path}", timeout=5)

    assert response.status_code == 200
    assert '<div id="root">' in response.text


@pytest.mark.parametrize(
    ("page_key", "action_key", "endpoint", "payload"),
    [
        ("data", "data.fetch", "/api/data/fetch", {"data_types": ["prices"], "dry_run": True}),
        (
            "models",
            "models.train",
            "/api/models/train",
            {"model_type": "lgbm", "tag": "e2e", "dry_run": True},
        ),
        (
            "backtest",
            "backtest.grid",
            "/api/backtest/grid",
            {
                "model_path": "models/dummy.pkl",
                "topk_list": [5],
                "n_drop_list": [1],
                "hold_thresh_list": [5],
                "dry_run": True,
            },
        ),
        (
            "signals",
            "signals.generate",
            "/api/signals/generate",
            {"model_path": "models/dummy.pkl", "dry_run": True},
        ),
    ],
)
def test_dry_run_submit_creates_history_task(
    server_url: str,
    page_key: str,
    action_key: str,
    endpoint: str,
    payload: dict,
):
    response = requests.post(f"{server_url}{endpoint}", json=payload, timeout=10)

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"] is not None
    task_id = body["task_id"]

    tasks_response = requests.get(f"{server_url}/api/system/tasks", timeout=5)
    assert tasks_response.status_code == 200
    matching = [task for task in tasks_response.json() if task["task_id"] == task_id]
    assert len(matching) == 1
    assert matching[0]["page_key"] == page_key
    assert matching[0]["action_key"] == action_key


@pytest.mark.parametrize(
    ("path", "submit_script"),
    [
        (
            "/data-explorer",
            "document.querySelector('[data-testid=\"execution-form-data.fetch\"]').requestSubmit()",
        ),
        (
            "/models",
            "document.querySelector('[data-testid=\"models-train-submit\"]').click()",
        ),
        (
            "/backtest",
            "backtest-grid-submit",
        ),
        (
            "/signals",
            "signals-generate-submit",
        ),
    ],
)
def test_browser_submit_opens_drawer_and_history_tab(
    server_url: str,
    cdp_page: CDPPage,
    e2e_model_file: Path,
    path: str,
    submit_script: str,
):
    cdp_page.navigate(f"{server_url}{path}")

    assert cdp_page.evaluate(
        """
        (async () => {
          const deadline = Date.now() + 8000;
          while (Date.now() < deadline) {
            const panel = document.querySelector('[data-testid="tab-panel-execute"]');
            if (panel && !document.body.innerText.includes('console.')) return true;
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
          return false;
        })()
        """
    )

    if submit_script == "backtest-grid-submit":
        cdp_page.evaluate(
            """
            (() => {
              const form = document.querySelector('[data-testid="execution-form-backtest.grid"]');
              const input = form.querySelector('input');
              input.focus();
              input.select();
              return true;
            })()
            """
        )
        cdp_page.command("Input.insertText", {"text": "models/e2e_dummy.pkl"})
        assert cdp_page.evaluate(
            """
            (async () => {
              const deadline = Date.now() + 3000;
              while (Date.now() < deadline) {
                const form = document.querySelector('[data-testid="execution-form-backtest.grid"]');
                const inputReady = form.querySelector('input').value === 'models/e2e_dummy.pkl';
                const buttonReady = !form.querySelector('button[type="submit"]').disabled;
                if (inputReady && buttonReady) return true;
                await new Promise((resolve) => setTimeout(resolve, 50));
              }
              return false;
            })()
            """
        )
        cdp_page.evaluate(
            "document.querySelector('[data-testid=\"execution-form-backtest.grid\"] button[type=\"submit\"]').click()"
        )
    elif submit_script == "signals-generate-submit":
        assert cdp_page.evaluate(
            """
            (async () => {
              const deadline = Date.now() + 5000;
              while (Date.now() < deadline) {
                const button = document.querySelector('[data-testid="signals-generate-submit"]');
                if (button && !button.disabled) return true;
                await new Promise((resolve) => setTimeout(resolve, 100));
              }
              return false;
            })()
            """
        )
        cdp_page.evaluate("document.querySelector('[data-testid=\"signals-generate-submit\"]').click()")
    else:
        cdp_page.evaluate(submit_script)

    drawer_state = cdp_page.evaluate(
        """
        (async () => {
          const deadline = Date.now() + 8000;
          while (Date.now() < deadline) {
            const drawer = document.querySelector('[data-testid="task-drawer"]');
            const detail = document.querySelector('[data-testid="task-drawer-detail"]');
            const chip = document.querySelector('[data-testid^="task-chip-"]');
            if (drawer && detail && chip) return { ok: true };
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
          return {
            ok: false,
            hasDrawer: Boolean(document.querySelector('[data-testid="task-drawer"]')),
            hasDetail: Boolean(document.querySelector('[data-testid="task-drawer-detail"]')),
            hasChip: Boolean(document.querySelector('[data-testid^="task-chip-"]')),
            text: document.body.innerText.slice(0, 1000),
          };
        })()
        """
    )
    assert drawer_state["ok"], drawer_state

    cdp_page.evaluate("document.querySelector('[data-testid=\"tab-history\"]').click()")
    assert cdp_page.evaluate(
        """
        (async () => {
          const deadline = Date.now() + 5000;
          while (Date.now() < deadline) {
            if (document.querySelector('[data-testid="tab-panel-history"]')) return true;
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
          return false;
        })()
        """
    )
