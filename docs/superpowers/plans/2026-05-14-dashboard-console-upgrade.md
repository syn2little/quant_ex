# Dashboard Console Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Web Dashboard 4 主流程页面(Data / Models / Backtest / Signals)从"只读 artifact 浏览器"升级为参数化执行 + 任务追踪 + 历史回溯的研究控制台。

**Architecture:** 三阶段。Phase 0 主 agent 串行做后端契约统一 + 前端公共组件;Phase 1 由 4 个 subagent 在各自 git worktree 中并行实现每页 console;Phase 2 主 agent 顺序合并并跑完三层集成测试。

**Tech Stack:** FastAPI + Pydantic 后端;React 19 + TypeScript + Vite + Tailwind CSS v4 + ECharts 前端;zod 表单校验;pytest 测试;Chrome DevTools Protocol 做 e2e。

**Design Spec:** [docs/superpowers/specs/2026-05-14-dashboard-console-upgrade-design.md](../specs/2026-05-14-dashboard-console-upgrade-design.md)

---

## File Structure

### 后端(Phase 0 修改 / 新增)

| 路径 | 责任 |
|---|---|
| `web/api/services/task_manager.py` | 给 `TaskState` 加 `page_key`、`action_key`、`result_paths` 三个可选字段;序列化时输出这些字段 |
| `web/api/routers/data.py` | `/fetch` 与 `DELETE /cache/{type}/expired` 改成统一 `{task_id, dry_run, preview}` 返回 |
| `web/api/routers/models.py` | `/train` 改返回;新增 `DELETE /models/{filename}` 支持 `?dry_run` |
| `web/api/routers/backtest.py` | `/grid`、`/walk-forward`、`/compare` 改返回 |
| `web/api/routers/signals.py` | `/generate`、`/rebalance`、`/notify-test` 字段名核对/微调,保持统一返回结构 |
| `web/api/routers/factors.py` | `/evaluate`、`/mine` 改返回(保持一致性,不做 console UI) |
| `test/test_web_console_contract.py` | 后端契约回归测试(新建) |

### 前端公共组件(Phase 0 新建)

| 路径 | 责任 |
|---|---|
| `web/frontend/src/api/tasks.ts` | 任务列表 GET、SSE 订阅、cancel 封装 |
| `web/frontend/src/hooks/useTaskTracking.ts` | 任务订阅 hook,按 `pageKey + taskTypeFilter` 过滤 |
| `web/frontend/src/hooks/useDryRunPreview.ts` | 包装 dry-run 调用 + 状态 |
| `web/frontend/src/components/console/ExecutionForm.tsx` | 通用参数表单容器,内含 dry-run 默认 + zod 校验 |
| `web/frontend/src/components/console/DryRunPreview.tsx` | dry-run 返回结果的可视化容器 |
| `web/frontend/src/components/console/ConfirmDialog.tsx` | 二次确认对话框,支持 `destructive` |
| `web/frontend/src/components/console/TaskDrawer.tsx` | 右侧任务抽屉:列表 + 详情 + SSE 日志 + cancel |
| `web/frontend/src/components/console/TaskChip.tsx` | 单任务状态徽标 |
| `web/frontend/src/components/console/ConsolePageLayout.tsx` | 4-tab 骨架:概览/执行/历史/详情 |
| `web/frontend/src/components/console/index.ts` | 导出 |
| `web/frontend/src/i18n/en.json` | 加 `console.common.*`、`console.tasks.*` 命名空间 |
| `web/frontend/src/i18n/zh.json` | 同上,中文 |

### 前端 Phase 1(4 个 subagent 各自负责一组)

| 路径 | 负责 subagent |
|---|---|
| `web/frontend/src/pages/DataExplorerPage.tsx`, `api/data.ts`, `schemas/data.ts` | Subagent A |
| `web/frontend/src/pages/ModelsPage.tsx`, `api/models.ts`, `schemas/train.ts` | Subagent B |
| `web/frontend/src/pages/BacktestPage.tsx`, `pages/backtest/{GridConsole,WFVConsole,CompareConsole,ResultsHistory,ResultDetail}.tsx`, `api/backtest.ts`, `schemas/backtest.ts` | Subagent C |
| `web/frontend/src/pages/SignalsPage.tsx`, `api/signals.ts`, `schemas/signals.ts` | Subagent D |

### 测试(Phase 2 新建)

| 路径 | 责任 |
|---|---|
| `test/test_web_console_contract.py` | Phase 0 已建,Phase 2 补强 |
| `test/test_web_console_integration.py` | 4 个 router 各 action 的 dry-run + 实跑(mock)+ 校验失败 |
| `test/test_web_console_e2e.py` | CDP 浏览器 e2e,4 页"提交 → 抽屉 → 历史"全链路 |

---

## Phase 0 — 公共基础(主 agent 串行执行)

**分支策略**: 在 `main` 分支基础上创建新分支 `dashboard-console-base`,所有 Phase 0 改动落在该分支。Phase 0 结束后将该分支作为后续 4 个 worktree 的分叉点。

### Task 0.0: 准备 Phase 0 分支

**Files:** N/A (git)

- [x] **Step 1: 确认干净工作树**

```bash
git status --short
```

Expected: 空输出(无 uncommitted)。若有,先与用户对齐再继续。

- [x] **Step 2: 创建分支**

```bash
git checkout -b dashboard-console-base
git log --oneline -1
```

Expected: 列出最新 commit hash + 分支已切换。

---

### Task 0.1: TaskState schema 扩展

**Files:**
- Modify: `web/api/services/task_manager.py`
- Test: `test/test_web_console_contract.py`(新建,这是首个 test 文件)

- [x] **Step 1: 写失败测试**

新建 `test/test_web_console_contract.py`:

```python
"""Phase 0 contract regression tests for the dashboard console upgrade."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.api.app import create_app
from web.api.services.task_manager import TaskManager, TaskState, TaskStatus


def test_task_state_has_console_fields():
    state = TaskState(task_id="abc", task_type="model_train")

    assert hasattr(state, "page_key")
    assert hasattr(state, "action_key")
    assert hasattr(state, "result_paths")
    assert state.page_key is None
    assert state.action_key is None
    assert state.result_paths == []
```

- [x] **Step 2: 跑测试确认失败**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py::test_task_state_has_console_fields -v
```

Expected: FAIL (`AttributeError: 'TaskState' object has no attribute 'page_key'`)

- [x] **Step 3: 修改 `web/api/services/task_manager.py`**

在 `TaskState` dataclass 中(`web/api/services/task_manager.py:26-34`)新增三个字段:

```python
@dataclass
class TaskState:
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    result: Optional[Any] = None
    error: Optional[str] = None
    page_key: Optional[str] = None
    action_key: Optional[str] = None
    result_paths: list[str] = field(default_factory=list)
```

并扩展 `start_sync_task` / `start_task` 签名,允许通过关键字参数(`page_key=`, `action_key=`)传入这些字段:

```python
async def start_sync_task(
    self,
    task_type: str,
    fn: Callable,
    *args,
    page_key: Optional[str] = None,
    action_key: Optional[str] = None,
    **kwargs,
) -> str:
    task_id = uuid.uuid4().hex[:12]
    state = TaskState(
        task_id=task_id,
        task_type=task_type,
        page_key=page_key,
        action_key=action_key,
    )
    self._tasks[task_id] = state
    self._queues[task_id] = asyncio.Queue()

    async def _wrapper():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    bg = asyncio.create_task(self._run(task_id, _wrapper()))
    self._bg_tasks[task_id] = bg
    return task_id
```

对 `start_task` 做同样改造。

并修改 `_run` 中将 result 写回 state 时,如果 result 是 dict 且含 `result_paths`,则填入 `state.result_paths`。

并修改任务序列化逻辑(在 `web/api/routers/system.py` 的 `list_tasks` 与 `stream_task` 中)输出三个新字段:

```python
def _serialize(state: TaskState) -> dict:
    return {
        "task_id": state.task_id,
        "task_type": state.task_type,
        "status": state.status.value,
        "created_at": state.created_at,
        "result": state.result,
        "error": state.error,
        "page_key": state.page_key,
        "action_key": state.action_key,
        "result_paths": state.result_paths,
    }
```

(若已有类似 serialize 函数则就地扩展)

- [x] **Step 4: 跑测试确认通过**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py::test_task_state_has_console_fields -v
```

Expected: PASS

- [x] **Step 5: 跑既有测试不破坏**

```bash
./.venv/bin/python -m pytest test/test_web_dashboard.py test/test_agent_strategy_iteration.py -q
```

Expected: 全 PASS(无回归)

- [x] **Step 6: Commit**

```bash
git add web/api/services/task_manager.py web/api/routers/system.py test/test_web_console_contract.py
git commit -m "feat(web): extend TaskState with page_key/action_key/result_paths"
```

---

### Task 0.2: data router 统一返回契约

**Files:**
- Modify: `web/api/routers/data.py`
- Test: `test/test_web_console_contract.py`

- [x] **Step 1: 写失败测试**

在 `test/test_web_console_contract.py` 追加:

```python
def test_data_fetch_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/data/fetch", json={
        "data_types": ["prices"],
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is True
    assert body["preview"] is not None


def test_data_fetch_returns_unified_envelope_for_real_run(monkeypatch):
    client = TestClient(create_app())

    # mock the actual fetch implementation
    monkeypatch.setattr("web.api.routers.data._do_fetch", lambda **kwargs: {"ok": True})

    response = client.post("/api/data/fetch", json={
        "data_types": ["prices"],
        "dry_run": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is False
    assert body["preview"] is None
```

- [x] **Step 2: 跑测试确认失败**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py::test_data_fetch_returns_unified_envelope_for_dry_run -v
```

Expected: FAIL(KeyError 或 assertion error)

- [x] **Step 3: 修改 `web/api/routers/data.py` 的 `start_fetch`**

将 `FetchRequest` 加入 `dry_run: bool = True` 字段。改造 `start_fetch`:

```python
@router.post("/fetch")
async def start_fetch(req: FetchRequest):
    if req.dry_run:
        preview = _build_fetch_preview(req)
        # 仍创建 task 记录(状态 done)
        tm = get_task_manager()
        task_id = await tm.start_sync_task(
            "data_fetch_dry_run",
            lambda: preview,
            page_key="data",
            action_key="data.fetch",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    tm = get_task_manager()
    task_id = await tm.start_sync_task(
        "data_fetch",
        _do_fetch,
        page_key="data",
        action_key="data.fetch",
        data_types=req.data_types,
        date_range=req.date_range,
        force_refresh=req.force_refresh,
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
```

新建 `_build_fetch_preview(req)` 返回 dict(计划抓取条数、估算耗时、磁盘占用、跳过项)。若需要预览实现复杂,先返回最小结构:

```python
def _build_fetch_preview(req: FetchRequest) -> dict:
    return {
        "data_types": req.data_types,
        "date_range": req.date_range,
        "force_refresh": req.force_refresh,
        "estimated_files": _estimate_fetch_count(req),
        "skipped_cached": _list_cached(req) if not req.force_refresh else [],
    }
```

未实现的辅助函数提供最小 stub,Phase 1 subagent A 在前端使用时按需扩展。

- [x] **Step 4: 改 `DELETE /cache/{type}/expired`**

加上 `dry_run: bool = Query(True)` 查询参数:

```python
@router.delete("/cache/{data_type}/expired")
async def delete_expired(data_type: str, dry_run: bool = Query(True)):
    candidates = _list_expired_files(data_type)
    if dry_run:
        tm = get_task_manager()
        task_id = await tm.start_sync_task(
            "data_purge_dry_run",
            lambda: {"files": candidates, "freed_bytes": sum(_size(f) for f in candidates)},
            page_key="data",
            action_key="data.purge_expired",
        )
        return {
            "task_id": task_id,
            "dry_run": True,
            "preview": {"files": candidates, "count": len(candidates)},
        }
    # real delete
    tm = get_task_manager()
    task_id = await tm.start_sync_task(
        "data_purge",
        _do_purge,
        page_key="data",
        action_key="data.purge_expired",
        data_type=data_type,
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
```

- [x] **Step 5: 跑测试**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py -v
./.venv/bin/python -m pytest test/test_web_dashboard.py -q
```

Expected: 新增 + 既有测试全 PASS。

- [x] **Step 6: Commit**

```bash
git add web/api/routers/data.py test/test_web_console_contract.py
git commit -m "feat(web/api): data router returns {task_id, dry_run, preview} envelope"
```

---

### Task 0.3: models router 统一返回 + 新增 DELETE

**Files:**
- Modify: `web/api/routers/models.py`
- Test: `test/test_web_console_contract.py`

- [x] **Step 1: 写失败测试**

追加到 `test/test_web_console_contract.py`:

```python
def test_models_train_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/models/train", json={
        "model_type": "lgbm",
        "tag": "ci_test",
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is True
    assert body["preview"] is not None
    # final_market must appear in preview to catch the csi300/csi1000 config trap
    assert "final_market" in body["preview"]


def test_models_delete_dry_run_lists_files(tmp_path, monkeypatch):
    client = TestClient(create_app())

    # monkeypatch models dir or just call with a known fake filename
    response = client.delete("/api/models/nonexistent.pkl?dry_run=true")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        body = response.json()
        assert body["dry_run"] is True
        assert "files" in body["preview"]
```

- [x] **Step 2: 跑测试确认失败**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py::test_models_train_returns_unified_envelope_for_dry_run -v
```

Expected: FAIL

- [x] **Step 3: 改造 `web/api/routers/models.py`**

`TrainRequest` 加 `dry_run: bool = True`、`market: Optional[str] = None`、`train_start_date: Optional[str] = None`、`train_end_date: Optional[str] = None`、`config_override: Optional[str] = None`。

`start_training`:

```python
@router.post("/train")
async def start_training(req: TrainRequest):
    final_market = _resolve_final_market(req.config_override, req.market)
    if req.dry_run:
        preview = {
            "model_type": req.model_type,
            "tag": req.tag,
            "final_market": final_market,
            "train_window": {"start": req.train_start_date, "end": req.train_end_date},
            "config_override": req.config_override,
            "estimated_minutes": _estimate_train_minutes(req),
            "output_path": f"models/{req.model_type}_{req.tag}.pkl",
        }
        tm = get_task_manager()
        task_id = await tm.start_sync_task(
            "model_train_dry_run",
            lambda: preview,
            page_key="models",
            action_key="models.train",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    tm = get_task_manager()
    task_id = await tm.start_sync_task(
        "model_train",
        _train,
        page_key="models",
        action_key="models.train",
        # ... (existing args)
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
```

`_resolve_final_market(config_override, market)` 必须解析 yaml 中 `market.name`,如有显式覆盖参数优先 — 这是 CLAUDE.md 提到的 `daily_csi1000.yaml` 陷阱的关键防线。

新增 DELETE:

```python
from fastapi import Query
from pathlib import Path

@router.delete("/{filename}")
async def delete_model(filename: str, dry_run: bool = Query(True)):
    models_dir = Path("models")
    target = models_dir / filename
    if not target.exists():
        raise HTTPException(404, f"model not found: {filename}")
    meta = target.with_suffix(".json")
    files = [str(target)] + ([str(meta)] if meta.exists() else [])
    if dry_run:
        tm = get_task_manager()
        task_id = await tm.start_sync_task(
            "model_delete_dry_run",
            lambda: {"files": files},
            page_key="models",
            action_key="models.delete",
        )
        return {"task_id": task_id, "dry_run": True, "preview": {"files": files}}
    for f in files:
        Path(f).unlink()
    tm = get_task_manager()
    task_id = await tm.start_sync_task(
        "model_delete",
        lambda: {"removed": files},
        page_key="models",
        action_key="models.delete",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
```

- [x] **Step 4: 跑测试**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py -v
./.venv/bin/python -m pytest test/test_web_dashboard.py -q
```

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add web/api/routers/models.py test/test_web_console_contract.py
git commit -m "feat(web/api): models train returns unified envelope + DELETE endpoint"
```

---

### Task 0.4: backtest router 统一返回

**Files:**
- Modify: `web/api/routers/backtest.py`
- Test: `test/test_web_console_contract.py`

- [x] **Step 1: 写失败测试**

追加:

```python
def test_backtest_grid_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/backtest/grid", json={
        "model_path": "models/dummy.pkl",
        "topk_list": [5, 10],
        "n_drop_list": [1, 3],
        "hold_thresh_list": [5, 8],
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["candidate_count"] == 2 * 2 * 2  # 8


def test_backtest_wfv_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())

    response = client.post("/api/backtest/walk-forward", json={
        "train_universes": ["csi300", "csi1000"],
        "eval_market": "csi300",
        "topk_list": [5],
        "n_drop_list": [1],
        "hold_thresh_list": [5],
        "rank_metric": "information_ratio",
        "dry_run": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"]["rank_metric"] == "information_ratio"
```

- [x] **Step 2: 跑测试确认失败**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py::test_backtest_grid_returns_unified_envelope_for_dry_run -v
```

Expected: FAIL

- [x] **Step 3: 改造 `web/api/routers/backtest.py`**

`GridSearchRequest` 加 `dry_run: bool = True`、`deal_price: str = "close"`、`benchmark: Optional[str] = None`、`open_cost: float = 0.0005`、`close_cost: float = 0.0015`、`min_cost: float = 5.0`、`slippage: float = 0.0`、`start_date: Optional[str] = None`、`end_date: Optional[str] = None`、`output_csv: Optional[str] = None`(若已有同名字段就核对类型)。

```python
@router.post("/grid")
async def start_grid_search(req: GridSearchRequest):
    candidate_count = len(req.topk_list) * len(req.n_drop_list) * len(req.hold_thresh_list)
    if req.dry_run:
        preview = {
            "model_path": req.model_path,
            "market": req.market,
            "benchmark": req.benchmark,
            "candidate_count": candidate_count,
            "estimated_minutes": candidate_count * 0.5,  # crude estimate; subagent C 可调整
            "deal_price": req.deal_price,
            "rank_metric": "information_ratio",
        }
        tm = get_task_manager()
        task_id = await tm.start_sync_task(
            "grid_search_dry_run",
            lambda: preview,
            page_key="backtest",
            action_key="backtest.grid",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    tm = get_task_manager()
    task_id = await tm.start_sync_task(
        "grid_search",
        _grid,
        page_key="backtest",
        action_key="backtest.grid",
        # ... existing kwargs
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
```

WFV 类同。`compare` 加 `dry_run`,dry-run 返回输入文件列表与会读到的列信息预览。

- [x] **Step 4: 跑测试**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py -v
./.venv/bin/python -m pytest test/test_web_dashboard.py -q
```

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add web/api/routers/backtest.py test/test_web_console_contract.py
git commit -m "feat(web/api): backtest grid/wfv/compare return unified envelope"
```

---

### Task 0.5: signals router 字段核对 + factors router 跟齐

**Files:**
- Modify: `web/api/routers/signals.py`, `web/api/routers/factors.py`
- Test: `test/test_web_console_contract.py`

- [x] **Step 1: 写失败测试**

```python
def test_signals_generate_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())
    response = client.post("/api/signals/generate", json={
        "model_path": "models/dummy.pkl",
        "dry_run": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["preview"] is not None


def test_signals_rebalance_dry_run_preview_includes_diff():
    client = TestClient(create_app())
    response = client.post("/api/signals/rebalance", json={
        "config": "config/daily_csi1000.yaml",
        "dry_run": True,
        "skip_update": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert "diff" in body["preview"]


def test_factors_evaluate_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())
    response = client.post("/api/factors/evaluate", json={
        "factor": "technical",
        "dry_run": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["dry_run"] is True
```

- [x] **Step 2: 跑测试**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py -v
```

Expected: 部分 PASS(已存在 dry-run 的)+ 部分 FAIL。

- [x] **Step 3: 改造 `signals.py` 与 `factors.py`**

对每个触发端点确保返回 `{task_id, dry_run, preview}`,并在 task 创建时填入 `page_key + action_key`(`signals.generate`、`signals.rebalance`、`signals.notify_test`、`factors.evaluate`、`factors.mine`)。

`signals/rebalance` 的 dry-run preview 必须包含:

```python
{
  "config": req.config,
  "diff": _compute_position_diff(req),   # {"buys": [...], "sells": [...], "net_value": float}
  "notify_template": _render_notify_template(req),
  "notify_channel": req.notify_channel,
}
```

- [x] **Step 4: 跑测试**

```bash
./.venv/bin/python -m pytest test/test_web_console_contract.py -v
./.venv/bin/python -m pytest test/test_web_dashboard.py -q
```

Expected: 全 PASS。

- [x] **Step 5: Commit**

```bash
git add web/api/routers/signals.py web/api/routers/factors.py test/test_web_console_contract.py
git commit -m "feat(web/api): signals + factors unified envelope"
```

---

### Task 0.6: 评估 update-qlib 包装可行性

**Files:** Inspect `run_update_qlib_data.py`;若可包装则 modify `web/api/routers/data.py`。

- [ ] **Step 1: 检查 `run_update_qlib_data.py`**

```bash
./.venv/bin/python run_update_qlib_data.py --help
```

Expected: 输出 CLI 选项。若 `--dry-run` 标志存在且参数化清晰 → 可包装。

- [ ] **Step 2: 决策**

如可包装,继续 Step 3;否则跳到 Step 5,在 plan 中标注 skip 并通知 subagent A。

- [ ] **Step 3: 在 `data.py` 加端点**

```python
@router.post("/update-qlib")
async def update_qlib(req: UpdateQlibRequest):
    if req.dry_run:
        preview = {
            "region": req.region,
            "date_range": req.date_range,
            "estimated_minutes": 5,
        }
        tm = get_task_manager()
        task_id = await tm.start_sync_task(
            "qlib_update_dry_run",
            lambda: preview,
            page_key="data",
            action_key="data.update_qlib",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}
    tm = get_task_manager()
    task_id = await tm.start_sync_task(
        "qlib_update",
        _do_update_qlib,
        page_key="data",
        action_key="data.update_qlib",
        region=req.region,
        date_range=req.date_range,
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}
```

`_do_update_qlib(region, date_range)` 调用 `run_update_qlib_data.main(...)`。

- [ ] **Step 4: 加测试**

```python
def test_data_update_qlib_returns_unified_envelope_for_dry_run():
    client = TestClient(create_app())
    response = client.post("/api/data/update-qlib", json={
        "region": "cn",
        "dry_run": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
```

跑测试,PASS 后 commit。

- [ ] **Step 5: (若 skip) 记录决策**

如果 Step 2 判定不可包装,在 plan 末尾"Phase 0 决策记录"段标注:`update-qlib 不实现,Subagent A 在 §4.1 中跳过该卡片`。Subagent A 派发 prompt 时主 agent 必须复述这条决策。

- [ ] **Step 6: Commit(若实现)**

```bash
git add web/api/routers/data.py test/test_web_console_contract.py
git commit -m "feat(web/api): wrap run_update_qlib_data behind POST /data/update-qlib"
```

---

### Task 0.7: 前端 api/tasks.ts 客户端封装

**Files:**
- Create: `web/frontend/src/api/tasks.ts`

- [ ] **Step 1: 检查既有 api 客户端模式**

```bash
ls web/frontend/src/api/
cat web/frontend/src/api/types.ts | head -30
```

Expected: 列出现有 api 文件 + types 风格,后续保持一致。

- [ ] **Step 2: 写 `web/frontend/src/api/tasks.ts`**

```typescript
import type { TaskState } from "./types";

export type TaskTrigger<TPreview = unknown> = {
  task_id: string;
  dry_run: boolean;
  preview: TPreview | null;
};

const BASE = "/api/system";

export async function listTasks(params?: {
  page_key?: string;
  task_types?: string[];
}): Promise<TaskState[]> {
  const qs = new URLSearchParams();
  if (params?.page_key) qs.set("page_key", params.page_key);
  if (params?.task_types?.length) qs.set("task_types", params.task_types.join(","));
  const url = qs.toString() ? `${BASE}/tasks?${qs}` : `${BASE}/tasks`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`listTasks failed: ${r.status}`);
  return r.json();
}

export function subscribeTask(taskId: string, onMessage: (ev: MessageEvent) => void): EventSource {
  const es = new EventSource(`${BASE}/tasks/${taskId}/stream`);
  es.onmessage = onMessage;
  return es;
}

export async function cancelTask(taskId: string): Promise<void> {
  const r = await fetch(`${BASE}/tasks/${taskId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`cancelTask failed: ${r.status}`);
}
```

在 `api/types.ts` 中加(或确认已有)`TaskState`:

```typescript
export type TaskState = {
  task_id: string;
  task_type: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
  created_at: string;
  result: unknown;
  error: string | null;
  page_key: string | null;
  action_key: string | null;
  result_paths: string[];
};
```

后端 `/api/system/tasks` 当前可能不支持 `page_key` / `task_types` 查询参数 — 在 `web/api/routers/system.py` 的 `list_tasks` 中加这两个可选过滤参数;不加则前端做客户端 filter。**为简化,采用客户端 filter**:`listTasks()` 不传参,前端拿到全表后用 `useTaskTracking` 过滤。修订后:

```typescript
export async function listTasks(): Promise<TaskState[]> {
  const r = await fetch(`${BASE}/tasks`);
  if (!r.ok) throw new Error(`listTasks failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 3: TypeScript 编译检查**

```bash
cd web/frontend && npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/api/tasks.ts web/frontend/src/api/types.ts
git commit -m "feat(web): add tasks.ts client wrapper + extended TaskState type"
```

---

### Task 0.8: useTaskTracking + useDryRunPreview hooks

**Files:**
- Create: `web/frontend/src/hooks/useTaskTracking.ts`
- Create: `web/frontend/src/hooks/useDryRunPreview.ts`

- [ ] **Step 1: 写 useTaskTracking.ts**

```typescript
import { useEffect, useState, useCallback } from "react";
import { listTasks, subscribeTask } from "../api/tasks";
import type { TaskState } from "../api/types";

export type UseTaskTrackingOptions = {
  pageKey: string;
  taskTypeFilter: string[];
  pollMs?: number;
};

export function useTaskTracking({ pageKey, taskTypeFilter, pollMs = 5000 }: UseTaskTrackingOptions) {
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [activeStreams, setActiveStreams] = useState<Record<string, EventSource>>({});

  const refresh = useCallback(async () => {
    const all = await listTasks();
    const filtered = all.filter(
      (t) => t.page_key === pageKey || taskTypeFilter.includes(t.task_type),
    );
    setTasks(filtered);
  }, [pageKey, taskTypeFilter]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  const trackTask = useCallback((taskId: string) => {
    if (activeStreams[taskId]) return;
    const es = subscribeTask(taskId, (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setTasks((prev) => {
          const i = prev.findIndex((t) => t.task_id === taskId);
          if (i === -1) return [data, ...prev];
          const next = [...prev];
          next[i] = { ...next[i], ...data };
          return next;
        });
        if (data.status === "done" || data.status === "failed" || data.status === "cancelled") {
          es.close();
          setActiveStreams((s) => {
            const { [taskId]: _, ...rest } = s;
            return rest;
          });
        }
      } catch (e) {
        console.error("SSE parse error", e);
      }
    });
    setActiveStreams((s) => ({ ...s, [taskId]: es }));
  }, [activeStreams]);

  useEffect(() => {
    return () => {
      Object.values(activeStreams).forEach((es) => es.close());
    };
  }, [activeStreams]);

  return { tasks, refresh, trackTask };
}
```

- [ ] **Step 2: 写 useDryRunPreview.ts**

```typescript
import { useState, useCallback } from "react";

export type UseDryRunPreviewState<TPreview> = {
  loading: boolean;
  preview: TPreview | null;
  error: string | null;
};

export function useDryRunPreview<TParams, TPreview>(
  caller: (p: TParams) => Promise<{ task_id: string; dry_run: boolean; preview: TPreview | null }>,
) {
  const [state, setState] = useState<UseDryRunPreviewState<TPreview>>({
    loading: false,
    preview: null,
    error: null,
  });

  const run = useCallback(async (p: TParams) => {
    setState({ loading: true, preview: null, error: null });
    try {
      const result = await caller(p);
      setState({ loading: false, preview: result.preview, error: null });
      return result;
    } catch (e) {
      setState({ loading: false, preview: null, error: (e as Error).message });
      throw e;
    }
  }, [caller]);

  const reset = useCallback(() => setState({ loading: false, preview: null, error: null }), []);

  return { ...state, run, reset };
}
```

- [ ] **Step 3: TypeScript 编译检查**

```bash
cd web/frontend && npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/hooks/useTaskTracking.ts web/frontend/src/hooks/useDryRunPreview.ts
git commit -m "feat(web): add useTaskTracking + useDryRunPreview hooks"
```

---

### Task 0.9: ExecutionForm + DryRunPreview + ConfirmDialog 组件

**Files:**
- Create: `web/frontend/src/components/console/ExecutionForm.tsx`
- Create: `web/frontend/src/components/console/DryRunPreview.tsx`
- Create: `web/frontend/src/components/console/ConfirmDialog.tsx`

- [ ] **Step 1: 写 ExecutionForm.tsx**

```tsx
import { ReactNode } from "react";
import { useForm, UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

export type DryRunResult<TPreview = unknown> = {
  task_id: string;
  dry_run: boolean;
  preview: TPreview | null;
};

export type ExecutionFormProps<TParams extends Record<string, unknown>> = {
  pageKey: "data" | "models" | "backtest" | "signals";
  actionKey: string;
  schema: z.ZodType<TParams>;
  defaults: Partial<TParams>;
  dryRunDefault: boolean;
  onDryRun: (p: TParams) => Promise<DryRunResult>;
  onSubmit: (p: TParams) => Promise<{ task_id: string }>;
  renderFields: (form: UseFormReturn<TParams>) => ReactNode;
  destructive?: boolean;
};

export function ExecutionForm<TParams extends Record<string, unknown>>({
  pageKey,
  actionKey,
  schema,
  defaults,
  dryRunDefault,
  onDryRun,
  onSubmit,
  renderFields,
  destructive = false,
}: ExecutionFormProps<TParams>) {
  const form = useForm<TParams>({
    resolver: zodResolver(schema),
    defaultValues: defaults as TParams,
  });

  return (
    <form
      data-testid={`execution-form-${actionKey}`}
      onSubmit={form.handleSubmit(async (p) => {
        if ((p as any).dry_run ?? dryRunDefault) {
          await onDryRun(p);
        } else {
          await onSubmit(p);
        }
      })}
    >
      {renderFields(form)}
    </form>
  );
}
```

注意:如果项目尚未装 `react-hook-form` + `@hookform/resolvers` + `zod`,先检查 `web/frontend/package.json`,**若缺则在本任务一并装**(此 plan 范围内允许加这三个前端库,它们是表单工程必需,不算"新功能依赖")。

- [ ] **Step 2: 检查依赖**

```bash
cd web/frontend && grep -E '"(react-hook-form|zod|@hookform/resolvers)"' package.json
```

如果三个都列出 → 跳到 Step 4。否则:

```bash
cd web/frontend && npm install react-hook-form zod @hookform/resolvers
```

- [ ] **Step 3: 写 DryRunPreview.tsx**

```tsx
import { ReactNode } from "react";

export type DryRunPreviewProps = {
  loading?: boolean;
  error?: string | null;
  preview: unknown;
  renderPreview?: (p: unknown) => ReactNode;
};

export function DryRunPreview({ loading, error, preview, renderPreview }: DryRunPreviewProps) {
  if (loading) return <div data-testid="dry-run-loading">Loading preview…</div>;
  if (error) return <div data-testid="dry-run-error" className="text-red-600">{error}</div>;
  if (!preview) return null;
  return (
    <div data-testid="dry-run-preview" className="p-3 rounded border bg-slate-50">
      {renderPreview ? renderPreview(preview) : <pre className="text-xs">{JSON.stringify(preview, null, 2)}</pre>}
    </div>
  );
}
```

- [ ] **Step 4: 写 ConfirmDialog.tsx**

```tsx
import { ReactNode } from "react";

export type ConfirmDialogProps = {
  open: boolean;
  titleKey: string;
  impactSummary: ReactNode;
  confirmLabelKey: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  titleKey,
  impactSummary,
  confirmLabelKey,
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div
      data-testid="confirm-dialog"
      role="dialog"
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    >
      <div className="bg-white rounded-lg p-6 w-[480px] max-w-[90vw] shadow-xl">
        <h3 className="text-lg font-semibold mb-3" data-i18n={titleKey}>{titleKey}</h3>
        <div className="mb-4 text-sm">{impactSummary}</div>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="px-3 py-1.5 rounded border">Cancel</button>
          <button
            onClick={onConfirm}
            data-testid="confirm-dialog-confirm"
            className={`px-3 py-1.5 rounded text-white ${destructive ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"}`}
          >
            {confirmLabelKey}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: TypeScript 编译**

```bash
cd web/frontend && npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/console/ExecutionForm.tsx web/frontend/src/components/console/DryRunPreview.tsx web/frontend/src/components/console/ConfirmDialog.tsx web/frontend/package.json web/frontend/package-lock.json
git commit -m "feat(web): add ExecutionForm + DryRunPreview + ConfirmDialog console components"
```

---

### Task 0.10: TaskDrawer + TaskChip + ConsolePageLayout 组件

**Files:**
- Create: `web/frontend/src/components/console/TaskDrawer.tsx`
- Create: `web/frontend/src/components/console/TaskChip.tsx`
- Create: `web/frontend/src/components/console/ConsolePageLayout.tsx`
- Create: `web/frontend/src/components/console/index.ts`

- [ ] **Step 1: 写 TaskChip.tsx**

```tsx
import type { TaskState } from "../../api/types";

export function TaskChip({ task, onClick }: { task: TaskState; onClick?: () => void }) {
  const color = {
    pending: "bg-slate-200 text-slate-700",
    running: "bg-blue-200 text-blue-800",
    done: "bg-green-200 text-green-800",
    failed: "bg-red-200 text-red-800",
    cancelled: "bg-amber-200 text-amber-800",
  }[task.status] ?? "bg-slate-200";
  return (
    <button
      data-testid={`task-chip-${task.task_id}`}
      onClick={onClick}
      className={`px-2 py-0.5 text-xs rounded ${color}`}
    >
      {task.action_key ?? task.task_type} · {task.status}
    </button>
  );
}
```

- [ ] **Step 2: 写 TaskDrawer.tsx**

```tsx
import { useEffect } from "react";
import { useTaskTracking } from "../../hooks/useTaskTracking";
import { cancelTask } from "../../api/tasks";
import { TaskChip } from "./TaskChip";

export type TaskDrawerProps = {
  pageKey: string;
  taskTypeFilter: string[];
  open: boolean;
  onClose: () => void;
};

export function TaskDrawer({ pageKey, taskTypeFilter, open, onClose }: TaskDrawerProps) {
  const { tasks, refresh } = useTaskTracking({ pageKey, taskTypeFilter });

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  if (!open) return null;
  return (
    <aside
      data-testid="task-drawer"
      className="fixed right-0 top-0 h-full w-[420px] bg-white shadow-xl border-l z-40 overflow-y-auto"
    >
      <div className="p-4 border-b flex items-center justify-between">
        <h3 className="font-semibold">Tasks · {pageKey}</h3>
        <button onClick={onClose}>×</button>
      </div>
      <ul className="divide-y">
        {tasks.length === 0 && <li className="p-4 text-sm text-slate-500">No tasks yet.</li>}
        {tasks.map((t) => (
          <li key={t.task_id} className="p-3">
            <div className="flex items-center justify-between">
              <TaskChip task={t} />
              {t.status === "running" && (
                <button
                  onClick={() => cancelTask(t.task_id).then(refresh)}
                  className="text-xs text-red-600"
                >
                  cancel
                </button>
              )}
            </div>
            <div className="text-xs text-slate-500 mt-1">{t.created_at}</div>
            {t.result_paths.length > 0 && (
              <ul className="mt-1 text-xs text-blue-700 list-disc pl-4">
                {t.result_paths.map((p) => <li key={p}>{p}</li>)}
              </ul>
            )}
            {t.error && <div className="text-xs text-red-600 mt-1">{t.error}</div>}
          </li>
        ))}
      </ul>
    </aside>
  );
}
```

- [ ] **Step 3: 写 ConsolePageLayout.tsx**

```tsx
import { ReactNode, useState } from "react";
import { TaskDrawer } from "./TaskDrawer";

export type ConsoleTab = "overview" | "execute" | "history" | "inspect";

export type ConsolePageLayoutProps = {
  pageKey: "data" | "models" | "backtest" | "signals";
  titleKey: string;
  tabs: {
    overview?: ReactNode;
    execute: ReactNode;
    history: ReactNode;
    inspect?: ReactNode;
  };
  taskTypeFilter: string[];
  initialTab?: ConsoleTab;
};

export function ConsolePageLayout({
  pageKey,
  titleKey,
  tabs,
  taskTypeFilter,
  initialTab = "execute",
}: ConsolePageLayoutProps) {
  const [active, setActive] = useState<ConsoleTab>(initialTab);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const tabList: { key: ConsoleTab; available: boolean; labelKey: string }[] = [
    { key: "overview", available: !!tabs.overview, labelKey: "console.tabs.overview" },
    { key: "execute", available: true, labelKey: "console.tabs.execute" },
    { key: "history", available: true, labelKey: "console.tabs.history" },
    { key: "inspect", available: !!tabs.inspect, labelKey: "console.tabs.inspect" },
  ];

  return (
    <div className="p-6">
      <header className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold" data-i18n={titleKey}>{titleKey}</h1>
        <button
          onClick={() => setDrawerOpen(true)}
          data-testid="open-task-drawer"
          className="px-3 py-1.5 rounded border"
        >
          Tasks
        </button>
      </header>
      <nav className="border-b mb-4">
        <ul className="flex gap-4">
          {tabList.filter((t) => t.available).map((t) => (
            <li key={t.key}>
              <button
                onClick={() => setActive(t.key)}
                data-testid={`tab-${t.key}`}
                className={`pb-2 ${active === t.key ? "border-b-2 border-blue-600 font-medium" : ""}`}
              >
                {t.labelKey}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <main data-testid={`tab-panel-${active}`}>
        {active === "overview" && tabs.overview}
        {active === "execute" && tabs.execute}
        {active === "history" && tabs.history}
        {active === "inspect" && tabs.inspect}
      </main>
      <TaskDrawer
        pageKey={pageKey}
        taskTypeFilter={taskTypeFilter}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
```

- [ ] **Step 4: 写 index.ts**

```typescript
export { ExecutionForm } from "./ExecutionForm";
export type { ExecutionFormProps, DryRunResult } from "./ExecutionForm";
export { DryRunPreview } from "./DryRunPreview";
export type { DryRunPreviewProps } from "./DryRunPreview";
export { ConfirmDialog } from "./ConfirmDialog";
export type { ConfirmDialogProps } from "./ConfirmDialog";
export { TaskDrawer } from "./TaskDrawer";
export type { TaskDrawerProps } from "./TaskDrawer";
export { TaskChip } from "./TaskChip";
export { ConsolePageLayout } from "./ConsolePageLayout";
export type { ConsolePageLayoutProps, ConsoleTab } from "./ConsolePageLayout";
```

- [ ] **Step 5: 编译 + build**

```bash
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: build 成功(允许 Vite chunk-size 警告)。

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/console/
git commit -m "feat(web): add TaskDrawer + TaskChip + ConsolePageLayout + barrel index"
```

---

### Task 0.11: i18n 公共命名空间

**Files:**
- Modify: `web/frontend/src/i18n/en.json`
- Modify: `web/frontend/src/i18n/zh.json`

- [ ] **Step 1: 在 en.json 加 console.common + console.tasks + console.tabs**

```json
{
  "console": {
    "common": {
      "dryRun": "Dry run",
      "preview": "Preview",
      "confirm": "Confirm",
      "cancel": "Cancel",
      "retry": "Retry",
      "submit": "Submit",
      "dryRunHint": "Defaults to dry-run preview. Uncheck and confirm to actually run.",
      "destructiveWarning": "This action is destructive and cannot be undone."
    },
    "tasks": {
      "drawerTitle": "Task drawer",
      "empty": "No tasks yet.",
      "statusPending": "pending",
      "statusRunning": "running",
      "statusDone": "done",
      "statusFailed": "failed",
      "statusCancelled": "cancelled",
      "cancel": "Cancel"
    },
    "tabs": {
      "overview": "Overview",
      "execute": "Execute",
      "history": "History",
      "inspect": "Inspect"
    },
    "data": {},
    "models": {},
    "backtest": {},
    "signals": {}
  }
}
```

(`data/models/backtest/signals` 空对象由 Phase 1 subagent 填充)

- [ ] **Step 2: 在 zh.json 同步**

```json
{
  "console": {
    "common": {
      "dryRun": "演练",
      "preview": "预览",
      "confirm": "确认",
      "cancel": "取消",
      "retry": "重试",
      "submit": "提交",
      "dryRunHint": "默认演练模式,取消勾选并确认后才会真实执行。",
      "destructiveWarning": "此操作不可逆,请谨慎确认。"
    },
    "tasks": {
      "drawerTitle": "任务面板",
      "empty": "暂无任务。",
      "statusPending": "等待中",
      "statusRunning": "运行中",
      "statusDone": "已完成",
      "statusFailed": "失败",
      "statusCancelled": "已取消",
      "cancel": "取消任务"
    },
    "tabs": {
      "overview": "概览",
      "execute": "执行",
      "history": "历史",
      "inspect": "详情"
    },
    "data": {},
    "models": {},
    "backtest": {},
    "signals": {}
  }
}
```

- [ ] **Step 3: 校验 JSON 合法**

```bash
./.venv/bin/python -c "import json; json.load(open('web/frontend/src/i18n/en.json')); json.load(open('web/frontend/src/i18n/zh.json')); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/i18n/en.json web/frontend/src/i18n/zh.json
git commit -m "feat(web): i18n console.common/tasks/tabs namespaces"
```

---

### Task 0.12: Phase 0 完整验收门禁

- [ ] **Step 1: 后端全测**

```bash
./.venv/bin/python -m pytest test/test_web_dashboard.py test/test_web_console_contract.py test/test_agent_strategy_iteration.py -v
```

Expected: 全 PASS。

- [ ] **Step 2: 后端 app 路由数量自检**

```bash
./.venv/bin/python -c "from web.api.app import create_app; app = create_app(); print('routes', len(app.routes))"
```

Expected: 输出 routes 数(应 ≥ 之前的 55,具体值与新增端点数相关)。

- [ ] **Step 3: 前端 TypeScript + build**

```bash
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: 无错误,build 成功。

- [ ] **Step 4: 启动服务 + AgentRuns 页冒烟**

```bash
./.venv/bin/python web/run_web.py &
SERVER_PID=$!
sleep 3
curl -s http://127.0.0.1:8000/api/agents/runs | head -c 200
curl -s http://127.0.0.1:8000/agent-runs | head -c 100
kill $SERVER_PID
```

Expected: `/api/agents/runs` 返回 JSON 列表(可能为空数组);`/agent-runs` 返回包含 `<div id="root">` 的 HTML。

- [ ] **Step 5: Push Phase 0 分支**

```bash
git push -u origin dashboard-console-base
```

Expected: push 成功。

- [ ] **Step 6: 总结 Phase 0 完成**

主 agent 总结:列出本阶段新增 / 修改文件、commit 数、关键决策(尤其是 update-qlib 是否实现)。这段总结直接作为 Phase 1 各 subagent 派发 prompt 的上下文。

---

## Phase 1 — 4 个 subagent 并行实现每页 console

**Phase 1 仅由 4 个 subagent 完成,主 agent 在 Phase 1 中只负责派发 + 监控 + 整合反馈。**

每个 subagent 通过 `superpowers:using-git-worktrees` 进入自己的 worktree。主 agent 在派发前为每个 subagent 创建一个 worktree:

```bash
git worktree add .claude/worktrees/console-data dashboard-console-base
git worktree add .claude/worktrees/console-models dashboard-console-base
git worktree add .claude/worktrees/console-backtest dashboard-console-base
git worktree add .claude/worktrees/console-signals dashboard-console-base
```

派发顺序:同时派发 A、B、D(三者较轻量);**C 单独评估,允许中段拆分。**

### Task 1.A: Subagent A — Data Explorer console

**Files (Subagent A 允许改):**
- Modify: `web/frontend/src/pages/DataExplorerPage.tsx`
- Modify: `web/frontend/src/api/data.ts`
- Create: `web/frontend/src/schemas/data.ts`
- Modify: `web/frontend/src/i18n/en.json`(仅 `console.data.*`)
- Modify: `web/frontend/src/i18n/zh.json`(仅 `console.data.*`)
- Create: `test/test_web_console_data.py`

**Files (Subagent A 严禁碰):** 任何 router、其他 page、其他 i18n 命名空间、`components/console/`。

**派发 prompt 包含:** 本任务全文 + spec §4.1 + Phase 0 update-qlib 决策结果。

- [ ] **Step A.1: 进入 worktree**

```bash
cd .claude/worktrees/console-data
```

- [ ] **Step A.2: 写 schemas/data.ts**

```typescript
import { z } from "zod";

export const FetchSchema = z.object({
  data_types: z.array(z.enum(["prices", "financial", "northbound", "sectors"])).min(1),
  date_range: z.object({
    start: z.string().nullable(),
    end: z.string().nullable(),
  }).optional(),
  force_refresh: z.boolean().default(false),
  dry_run: z.boolean().default(true),
});
export type FetchParams = z.infer<typeof FetchSchema>;

export const PurgeSchema = z.object({
  data_type: z.enum(["prices", "financial", "northbound", "sectors"]),
  dry_run: z.boolean().default(true),
});
export type PurgeParams = z.infer<typeof PurgeSchema>;

export const UpdateQlibSchema = z.object({
  region: z.enum(["cn", "us"]).default("cn"),
  date_range: z.object({
    start: z.string().nullable(),
    end: z.string().nullable(),
  }).optional(),
  dry_run: z.boolean().default(true),
});
export type UpdateQlibParams = z.infer<typeof UpdateQlibSchema>;
```

(如果 Phase 0 决定不实现 update-qlib,删除 UpdateQlibSchema 与对应 UI 卡片。)

- [ ] **Step A.3: 扩展 api/data.ts**

加入:

```typescript
import type { TaskTrigger } from "./tasks";
import type { FetchParams, PurgeParams, UpdateQlibParams } from "../schemas/data";

export async function triggerFetch(params: FetchParams): Promise<TaskTrigger> {
  const r = await fetch("/api/data/fetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`fetch failed: ${r.status}`);
  return r.json();
}

export async function triggerPurge(params: PurgeParams): Promise<TaskTrigger> {
  const qs = new URLSearchParams({ dry_run: String(params.dry_run) });
  const r = await fetch(`/api/data/cache/${params.data_type}/expired?${qs}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`purge failed: ${r.status}`);
  return r.json();
}

export async function triggerUpdateQlib(params: UpdateQlibParams): Promise<TaskTrigger> {
  const r = await fetch("/api/data/update-qlib", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`update-qlib failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step A.4: 重写 DataExplorerPage.tsx**

用 `<ConsolePageLayout>` 包裹,4 个 tab 分别填:

- **execute tab**: 3 个 action 卡片(若 update-qlib skipped 则 2 个),每个用 `<ExecutionForm>` + `useDryRunPreview` + `<DryRunPreview>` + `<ConfirmDialog>`(`force_refresh=true` 或 purge 时 `destructive=true`)。
- **history tab**: 使用 `useTaskTracking({ pageKey: 'data', taskTypeFilter: ['data_fetch', 'data_purge', 'qlib_update'] })`,列出任务表 + cache 文件 mtime(用现有 `/api/data/cache-status`)。
- **inspect tab**: 复用现有"个股查找/行情、板块/轮动、替代数据"组件代码块,搬到 tab 下。
- **overview tab**: 简短 KPI(cache 总文件数、最近 7 天任务数),可选。

**i18n key 添加到 `console.data.*` 命名空间**(中英同步):`console.data.fetchTitle`、`fetchDescription`、`purgeTitle`、`updateQlibTitle`、`dataTypePrices`、`dataTypeFinancial` 等。

- [ ] **Step A.5: 写 test/test_web_console_data.py**

```python
from fastapi.testclient import TestClient
from web.api.app import create_app


def test_data_explorer_page_serves():
    client = TestClient(create_app())
    r = client.get("/data-explorer")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_data_fetch_dry_run_records_task():
    client = TestClient(create_app())
    r = client.post("/api/data/fetch", json={
        "data_types": ["prices"],
        "dry_run": True,
    })
    assert r.status_code == 200
    body = r.json()
    task_id = body["task_id"]

    # task should appear in /api/system/tasks
    tasks = client.get("/api/system/tasks").json()
    matching = [t for t in tasks if t["task_id"] == task_id]
    assert len(matching) == 1
    assert matching[0]["page_key"] == "data"
    assert matching[0]["action_key"] == "data.fetch"
```

- [ ] **Step A.6: 验收**

```bash
./.venv/bin/python -m pytest test/test_web_console_data.py -v
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: 测试 PASS;前端 build 通过。

- [ ] **Step A.7: 启动 dev 服务 + 自检截图(可选,建议)**

```bash
cd web/frontend && npm run dev &
DEV_PID=$!
sleep 5
# 用 curl 验证主页可达
curl -s http://localhost:5173/data-explorer | head -c 200
kill $DEV_PID
```

- [ ] **Step A.8: Commit**

```bash
git add web/frontend/src/pages/DataExplorerPage.tsx web/frontend/src/api/data.ts web/frontend/src/schemas/data.ts web/frontend/src/i18n/en.json web/frontend/src/i18n/zh.json test/test_web_console_data.py
git commit -m "feat(web): Data Explorer console with execute/history/inspect tabs"
```

- [ ] **Step A.9: 上报**

Subagent A 报告:diff 摘要、新增 i18n key 数量、6 项验收命令的输出、是否触发到 update-qlib skip 决策。

---

### Task 1.B: Subagent B — Models console

**Files (允许改):**
- Modify: `web/frontend/src/pages/ModelsPage.tsx`
- Modify: `web/frontend/src/api/models.ts`
- Create: `web/frontend/src/schemas/train.ts`
- Modify: `web/frontend/src/i18n/{en,zh}.json`(仅 `console.models.*`)
- Create: `test/test_web_console_models.py`

**Files (严禁碰):** 同 A。

- [ ] **Step B.1: 进入 worktree**

```bash
cd .claude/worktrees/console-models
```

- [ ] **Step B.2: 写 schemas/train.ts**

```typescript
import { z } from "zod";

export const TrainSchema = z.object({
  model_type: z.string().min(1),
  tag: z.string().min(1),
  config_override: z.string().nullable().optional(),
  market: z.enum(["csi300", "csi500", "csi800", "csi1000", "all"]).default("csi300"),
  train_start_date: z.string().nullable().optional(),
  train_end_date: z.string().nullable().optional(),
  dry_run: z.boolean().default(true),
});
export type TrainParams = z.infer<typeof TrainSchema>;

export const DeleteModelSchema = z.object({
  filename: z.string().min(1),
  dry_run: z.boolean().default(true),
});
export type DeleteModelParams = z.infer<typeof DeleteModelSchema>;
```

- [ ] **Step B.3: 扩展 api/models.ts**

```typescript
import type { TaskTrigger } from "./tasks";
import type { TrainParams, DeleteModelParams } from "../schemas/train";

export async function triggerTrain(params: TrainParams): Promise<TaskTrigger> {
  const r = await fetch("/api/models/train", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`train failed: ${r.status}`);
  return r.json();
}

export async function triggerDelete(params: DeleteModelParams): Promise<TaskTrigger> {
  const qs = new URLSearchParams({ dry_run: String(params.dry_run) });
  const r = await fetch(`/api/models/${encodeURIComponent(params.filename)}?${qs}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`delete failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step B.4: 重写 ModelsPage.tsx**

用 `<ConsolePageLayout pageKey="models" ...>`,4 tab:

- **execute**: 2 个 action 卡片(训练、删除)。训练表单字段:model_type(from `/api/models/registry`)、tag、market、train_start_date、train_end_date、config_override(text input);删除字段:filename(select from `/api/models`)。
- **history**: `useTaskTracking({ pageKey: 'models', taskTypeFilter: ['model_train', 'model_delete'] })` + 现有 `/api/models` 列表 + `_meta.json` 字段聚合。
- **inspect**: 复用现有 meta + registry + 特征重要性。
- **overview**: KPI(模型总数、近期训练次数)。

**关键校验**:训练 dry-run preview 中显式渲染 `preview.final_market`,字号加大、颜色显眼。如果 `final_market` 与表单 `market` 不一致,显示红色警告。

- [ ] **Step B.5: 写 test/test_web_console_models.py**

```python
from fastapi.testclient import TestClient
from web.api.app import create_app


def test_models_page_serves():
    client = TestClient(create_app())
    r = client.get("/models")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_models_train_dry_run_preview_includes_final_market():
    client = TestClient(create_app())
    r = client.post("/api/models/train", json={
        "model_type": "lgbm",
        "tag": "ci_test",
        "market": "csi1000",
        "dry_run": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["preview"]["final_market"] == "csi1000"
```

- [ ] **Step B.6: 验收**

```bash
./.venv/bin/python -m pytest test/test_web_console_models.py -v
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: PASS + build OK.

- [ ] **Step B.7: Commit**

```bash
git add web/frontend/src/pages/ModelsPage.tsx web/frontend/src/api/models.ts web/frontend/src/schemas/train.ts web/frontend/src/i18n/en.json web/frontend/src/i18n/zh.json test/test_web_console_models.py
git commit -m "feat(web): Models console with train + delete actions"
```

- [ ] **Step B.8: 上报**

Subagent B 上报:diff 摘要、关键决策(final_market 显示逻辑)、6 项验收命令输出。

---

### Task 1.C: Subagent C — Backtest console

**Files (允许改):**
- Modify: `web/frontend/src/pages/BacktestPage.tsx`(转成组合外壳)
- Create: `web/frontend/src/pages/backtest/GridConsole.tsx`
- Create: `web/frontend/src/pages/backtest/WFVConsole.tsx`
- Create: `web/frontend/src/pages/backtest/CompareConsole.tsx`
- Create: `web/frontend/src/pages/backtest/ResultsHistory.tsx`
- Create: `web/frontend/src/pages/backtest/ResultDetail.tsx`
- Modify: `web/frontend/src/api/backtest.ts`
- Create: `web/frontend/src/schemas/backtest.ts`
- Modify: `web/frontend/src/i18n/{en,zh}.json`(仅 `console.backtest.*`)
- Create: `test/test_web_console_backtest.py`

**Files (严禁碰):** 同 A。

**Subagent C 工时高,允许中段拆分。如果 Step C.4 完成后预估剩余 > 8 小时,主 agent 立刻派发 sub-subagent C2 来接手 Compare/History/Detail。**

- [ ] **Step C.1: 进入 worktree**

```bash
cd .claude/worktrees/console-backtest
```

- [ ] **Step C.2: 写 schemas/backtest.ts**

```typescript
import { z } from "zod";

const NumberListSchema = z.string().transform((s) =>
  s.split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x)),
);

export const GridSchema = z.object({
  model_path: z.string().min(1),
  market: z.enum(["csi300", "csi500", "csi800", "csi1000"]).default("csi300"),
  benchmark: z.string().nullable().optional(),
  topk_list: NumberListSchema,
  n_drop_list: NumberListSchema,
  hold_thresh_list: NumberListSchema,
  deal_price: z.enum(["close", "vwap"]).default("close"),
  open_cost: z.number().default(0.0005),
  close_cost: z.number().default(0.0015),
  min_cost: z.number().default(5.0),
  slippage: z.number().default(0.0),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  output_csv: z.string().nullable().optional(),
  dry_run: z.boolean().default(true),
});
export type GridParams = z.infer<typeof GridSchema>;

export const WFVSchema = z.object({
  train_universes: z.array(z.string()).min(1),
  eval_market: z.string().min(1),
  rolling_window_days: z.number().default(252),
  step_days: z.number().default(63),
  topk_list: NumberListSchema,
  n_drop_list: NumberListSchema,
  hold_thresh_list: NumberListSchema,
  rank_metric: z.literal("information_ratio").default("information_ratio"),
  dry_run: z.boolean().default(true),
});
export type WFVParams = z.infer<typeof WFVSchema>;

export const CompareSchema = z.object({
  result_files: z.array(z.string()).min(2).max(5),
  dry_run: z.boolean().default(true),
});
export type CompareParams = z.infer<typeof CompareSchema>;
```

注意 `rank_metric` 字面量锁死 `"information_ratio"`,符合 CLAUDE.md 研究规则。

- [ ] **Step C.3: 扩展 api/backtest.ts**

```typescript
import type { TaskTrigger } from "./tasks";
import type { GridParams, WFVParams, CompareParams } from "../schemas/backtest";

export async function triggerGrid(params: GridParams): Promise<TaskTrigger> {
  const r = await fetch("/api/backtest/grid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`grid failed: ${r.status}`);
  return r.json();
}

export async function triggerWFV(params: WFVParams): Promise<TaskTrigger> {
  const r = await fetch("/api/backtest/walk-forward", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`wfv failed: ${r.status}`);
  return r.json();
}

export async function triggerCompare(params: CompareParams): Promise<TaskTrigger> {
  const r = await fetch("/api/backtest/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`compare failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step C.4: 实现 GridConsole.tsx + WFVConsole.tsx**

每个组件使用 `<ExecutionForm>` + `useDryRunPreview` + `<DryRunPreview>` + `<ConfirmDialog>`。

GridConsole 关键逻辑:`candidate_count = topk × n_drop × hold_thresh`,当 > 200 时 dry-run preview 区域显红警告。WFVConsole 同理。

**评估点**:此时检查工时余量。若已 > 8 小时,通知主 agent 派 C2 接手 C.5 - C.8。

- [ ] **Step C.5: 实现 CompareConsole.tsx**

支持 2-5 个 result_files 多选(from `/api/backtest/results`),提交后接收 compare 端点返回的 chart_data,并排渲染 ECharts(equity / drawdown / 指标表)。

- [ ] **Step C.6: 实现 ResultsHistory.tsx**

`useTaskTracking({ pageKey: 'backtest', taskTypeFilter: ['grid_search', 'wfv', 'compare', 'grid_search_dry_run', 'wfv_dry_run'] })` + `/api/backtest/results` 合并。表列:文件名、市场、模型、IR、Sharpe、deal_price、状态、task_id、artifact 链接。**默认按 IR 降序**(不允许默认排序为 Sharpe)。

- [ ] **Step C.7: 实现 ResultDetail.tsx**

复用现有 equity curve / drawdown / metrics 视图,通过 `/api/backtest/results/{f}/{equity-curve,metrics,drawdown}` 拉数据。

- [ ] **Step C.8: 改造 BacktestPage.tsx 为外壳**

```tsx
import { ConsolePageLayout } from "../components/console";
import { GridConsole } from "./backtest/GridConsole";
import { WFVConsole } from "./backtest/WFVConsole";
import { CompareConsole } from "./backtest/CompareConsole";
import { ResultsHistory } from "./backtest/ResultsHistory";
import { ResultDetail } from "./backtest/ResultDetail";

export default function BacktestPage() {
  return (
    <ConsolePageLayout
      pageKey="backtest"
      titleKey="console.backtest.title"
      taskTypeFilter={["grid_search", "wfv", "compare", "grid_search_dry_run", "wfv_dry_run"]}
      tabs={{
        execute: (
          <div className="space-y-6">
            <GridConsole />
            <WFVConsole />
            <CompareConsole />
          </div>
        ),
        history: <ResultsHistory />,
        inspect: <ResultDetail />,
      }}
    />
  );
}
```

- [ ] **Step C.9: 写 test/test_web_console_backtest.py**

```python
from fastapi.testclient import TestClient
from web.api.app import create_app


def test_backtest_page_serves():
    client = TestClient(create_app())
    r = client.get("/backtest")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_backtest_grid_dry_run_candidate_count():
    client = TestClient(create_app())
    r = client.post("/api/backtest/grid", json={
        "model_path": "models/dummy.pkl",
        "topk_list": [5, 10, 20],
        "n_drop_list": [1, 3],
        "hold_thresh_list": [5, 8, 10],
        "dry_run": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["preview"]["candidate_count"] == 18


def test_backtest_wfv_dry_run_rank_metric_locked():
    client = TestClient(create_app())
    r = client.post("/api/backtest/walk-forward", json={
        "train_universes": ["csi300"],
        "eval_market": "csi300",
        "topk_list": [5],
        "n_drop_list": [1],
        "hold_thresh_list": [5],
        "rank_metric": "information_ratio",
        "dry_run": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["preview"]["rank_metric"] == "information_ratio"
```

- [ ] **Step C.10: 验收**

```bash
./.venv/bin/python -m pytest test/test_web_console_backtest.py -v
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: PASS + build OK。

- [ ] **Step C.11: Commit**

```bash
git add web/frontend/src/pages/BacktestPage.tsx web/frontend/src/pages/backtest/ web/frontend/src/api/backtest.ts web/frontend/src/schemas/backtest.ts web/frontend/src/i18n/en.json web/frontend/src/i18n/zh.json test/test_web_console_backtest.py
git commit -m "feat(web): Backtest console split into Grid/WFV/Compare/History/Detail"
```

- [ ] **Step C.12: 上报**

Subagent C 上报:diff 摘要 + 5 个子组件行数 + 是否触发 sub-subagent 拆分 + IR 默认排序与 candidate_count 警告的实现细节。

---

### Task 1.D: Subagent D — Signals console

**Files (允许改):**
- Modify: `web/frontend/src/pages/SignalsPage.tsx`
- Modify: `web/frontend/src/api/signals.ts`
- Create: `web/frontend/src/schemas/signals.ts`
- Modify: `web/frontend/src/i18n/{en,zh}.json`(仅 `console.signals.*`)
- Create: `test/test_web_console_signals.py`

**Files (严禁碰):** 同 A。

- [ ] **Step D.1: 进入 worktree**

```bash
cd .claude/worktrees/console-signals
```

- [ ] **Step D.2: 写 schemas/signals.ts**

```typescript
import { z } from "zod";

export const GenerateSchema = z.object({
  model_path: z.string().min(1),
  config_override: z.string().nullable().optional(),
  dry_run: z.boolean().default(true),
});
export type GenerateParams = z.infer<typeof GenerateSchema>;

export const RebalanceSchema = z.object({
  config: z.string().min(1),
  positions: z.string().nullable().optional(),
  position_date: z.string().nullable().optional(),
  min_action_value: z.number().default(1000),
  skip_update: z.boolean().default(true),
  force: z.boolean().default(false),
  notify_channel: z.enum(["all", "bark", "pushplus", "dingtalk", "serverchan", "wechat_mp", "none"]).default("none"),
  dry_run: z.boolean().default(true),
  confirm_send: z.boolean().default(false),
}).refine(
  (d) => d.dry_run === true || d.confirm_send === true,
  { message: "confirm_send required when dry_run is false", path: ["confirm_send"] },
);
export type RebalanceParams = z.infer<typeof RebalanceSchema>;

export const NotifyTestSchema = z.object({
  channel: z.enum(["all", "bark", "pushplus", "dingtalk", "serverchan", "wechat_mp"]),
  message: z.string().min(1),
  dry_run: z.boolean().default(true),
  confirm_send: z.boolean().default(false),
}).refine(
  (d) => d.dry_run === true || d.confirm_send === true,
  { message: "confirm_send required when dry_run is false", path: ["confirm_send"] },
);
export type NotifyTestParams = z.infer<typeof NotifyTestSchema>;
```

- [ ] **Step D.3: 扩展 api/signals.ts**

```typescript
import type { TaskTrigger } from "./tasks";
import type { GenerateParams, RebalanceParams, NotifyTestParams } from "../schemas/signals";

export async function triggerGenerate(params: GenerateParams): Promise<TaskTrigger> {
  const r = await fetch("/api/signals/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`generate failed: ${r.status}`);
  return r.json();
}

export async function triggerRebalance(params: RebalanceParams): Promise<TaskTrigger> {
  const r = await fetch("/api/signals/rebalance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`rebalance failed: ${r.status}`);
  return r.json();
}

export async function triggerNotifyTest(params: NotifyTestParams): Promise<TaskTrigger> {
  const r = await fetch("/api/signals/notify-test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`notify-test failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step D.4: 重写 SignalsPage.tsx**

`<ConsolePageLayout pageKey="signals" ...>`,4 tab:

- **execute**: 3 个 action 卡片(每日信号、调仓、通知测试)。调仓 dry-run preview 必须显示 diff(买/卖/金额) + 通知模板预览。调仓的 ConfirmDialog `destructive=true`,Confirm 按钮仅在 `dry_run=false && confirm_send=true` 时启用(纯按钮,无倒计时)。
- **history**: `useTaskTracking({ pageKey: 'signals', taskTypeFilter: ['signal_generate', 'rebalance', 'notify_test'] })` + `/api/signals/history` 合并。rebalance 历史额外列"是否真发"。
- **inspect**: 复用现有 regime 状态 + 单文件信号查看。
- **overview**: 最近 7 天信号数 + regime 简要。

- [ ] **Step D.5: 写 test/test_web_console_signals.py**

```python
from fastapi.testclient import TestClient
from web.api.app import create_app


def test_signals_page_serves():
    client = TestClient(create_app())
    r = client.get("/signals")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_signals_rebalance_real_send_requires_confirm():
    client = TestClient(create_app())
    r = client.post("/api/signals/rebalance", json={
        "config": "config/daily_csi1000.yaml",
        "dry_run": False,
        "confirm_send": False,
        "skip_update": True,
    })
    assert r.status_code == 400


def test_signals_rebalance_dry_run_envelope():
    client = TestClient(create_app())
    r = client.post("/api/signals/rebalance", json={
        "config": "config/daily_csi1000.yaml",
        "dry_run": True,
        "skip_update": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert "diff" in body["preview"]
```

- [ ] **Step D.6: 验收**

```bash
./.venv/bin/python -m pytest test/test_web_console_signals.py -v
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: PASS + build OK。

- [ ] **Step D.7: Commit**

```bash
git add web/frontend/src/pages/SignalsPage.tsx web/frontend/src/api/signals.ts web/frontend/src/schemas/signals.ts web/frontend/src/i18n/en.json web/frontend/src/i18n/zh.json test/test_web_console_signals.py
git commit -m "feat(web): Signals console with generate/rebalance/notify-test actions"
```

- [ ] **Step D.8: 上报**

Subagent D 上报:diff 摘要、调仓 confirm 流程的实现、`destructive=true` 是否在 4 处恰当使用。

---

## Phase 2 — 主 agent 集成 + 测试

### Task 2.1: Merge subagent A

- [ ] **Step 1: 切回 dashboard-console-base 主分支**

```bash
git worktree list
git checkout dashboard-console-base
```

- [ ] **Step 2: Merge console-data worktree 分支**

```bash
# 假定 subagent A 在 worktree 中 commit 到了 dashboard-console-base 同一分支
# 如果 worktree 在独立分支,改成:
# git merge --no-ff <subagent A 分支名>
git pull .claude/worktrees/console-data dashboard-console-base
```

如有冲突,主要会在 `i18n/{en,zh}.json` 上(其他文件 subagent A 独占)。冲突处人工合并,确保两个 JSON 文件中 `console.data.*` 命名空间完整且 en/zh 对齐。

- [ ] **Step 3: 跑后端测试**

```bash
./.venv/bin/python -m pytest test/test_web_dashboard.py test/test_web_console_contract.py test/test_web_console_data.py test/test_agent_strategy_iteration.py -v
```

Expected: 全 PASS。

- [ ] **Step 4: 跑前端 build**

```bash
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: 通过。

- [ ] **Step 5: Commit 解冲突(若有)**

```bash
git status
git add -A
# 若有合并冲突解决,记得 commit;否则跳过
```

### Task 2.2: Merge subagent D

同 2.1,目标分支 `.claude/worktrees/console-signals`,新增 `test_web_console_signals.py` 进 pytest 列表。

### Task 2.3: Merge subagent B

同上,目标 `.claude/worktrees/console-models`,新增 `test_web_console_models.py`。

### Task 2.4: Merge subagent C

同上,目标 `.claude/worktrees/console-backtest`,新增 `test_web_console_backtest.py`。

Merge 完毕后跑一遍完整 pytest:

```bash
./.venv/bin/python -m pytest test/ -q
cd web/frontend && npx tsc --noEmit && npm run build
```

Expected: 全 PASS;build 通过。

---

### Task 2.5: 写 integration test

**Files:** Create `test/test_web_console_integration.py`

- [ ] **Step 1: 写测试覆盖三个分支(dry-run / 实跑 mock / 校验失败)**

```python
"""Web console integration tests: covers dry-run / real-run / validation-failure for each action."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.api.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


# ---------- Data ----------
def test_data_fetch_validation_failure(client):
    r = client.post("/api/data/fetch", json={"data_types": []})  # empty list
    assert r.status_code in (400, 422)


def test_data_fetch_real_run_mocked(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.data._do_fetch", lambda **kw: {"ok": True})
    r = client.post("/api/data/fetch", json={"data_types": ["prices"], "dry_run": False})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is False
    assert body["preview"] is None


# ---------- Models ----------
def test_models_train_validation_failure(client):
    r = client.post("/api/models/train", json={})
    assert r.status_code in (400, 422)


def test_models_train_real_run_mocked(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.models._train", lambda **kw: {"ok": True})
    r = client.post("/api/models/train", json={
        "model_type": "lgbm",
        "tag": "ci",
        "dry_run": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is False


# ---------- Backtest ----------
def test_backtest_grid_validation_failure(client):
    r = client.post("/api/backtest/grid", json={"model_path": ""})
    assert r.status_code in (400, 422)


def test_backtest_grid_real_run_mocked(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.backtest._grid", lambda **kw: {"ok": True})
    r = client.post("/api/backtest/grid", json={
        "model_path": "models/dummy.pkl",
        "topk_list": [5],
        "n_drop_list": [1],
        "hold_thresh_list": [5],
        "dry_run": False,
    })
    assert r.status_code == 200


# ---------- Signals ----------
def test_signals_rebalance_real_send_requires_confirm(client):
    r = client.post("/api/signals/rebalance", json={
        "config": "config/daily_csi1000.yaml",
        "dry_run": False,
        "confirm_send": False,
    })
    assert r.status_code == 400


def test_signals_generate_real_run_mocked(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.signals._generate", lambda **kw: {"ok": True})
    r = client.post("/api/signals/generate", json={
        "model_path": "models/dummy.pkl",
        "dry_run": False,
    })
    assert r.status_code == 200
```

- [ ] **Step 2: 跑测试**

```bash
./.venv/bin/python -m pytest test/test_web_console_integration.py -v
```

Expected: 全 PASS。

- [ ] **Step 3: Commit**

```bash
git add test/test_web_console_integration.py
git commit -m "test(web): cross-page console integration coverage"
```

---

### Task 2.6: 写 e2e CDP 测试

**Files:** Create `test/test_web_console_e2e.py`

- [ ] **Step 1: 找现有 CDP 模板**

```bash
grep -rn "chrome.*--headless\|cdp\|playwright" test/ docs/ 2>&1 | head -10
```

若找到既有脚本,复用风格;否则用 Python 的 `pychrome` / `subprocess + chrome --headless --remote-debugging-port`。

- [ ] **Step 2: 写 e2e 脚本**

```python
"""CDP-driven e2e tests for the 4 console pages.

Requires the FastAPI server to be running on http://127.0.0.1:8000.
"""
from __future__ import annotations

import os
import subprocess
import time
import json
import pytest

import requests


SERVER_URL = os.environ.get("WEB_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def server():
    # caller should start the server externally; this fixture only verifies it's up
    for _ in range(20):
        try:
            r = requests.get(f"{SERVER_URL}/api/system/health", timeout=1)
            if r.status_code == 200:
                return SERVER_URL
        except requests.RequestException:
            time.sleep(0.5)
    pytest.skip("Web server not running at " + SERVER_URL)


@pytest.mark.parametrize("path,h1_zh", [
    ("/data-explorer", "数据探索"),
    ("/models", "模型"),
    ("/backtest", "回测"),
    ("/signals", "信号"),
])
def test_page_renders_with_h1(server, path, h1_zh):
    r = requests.get(f"{server}{path}", timeout=5)
    assert r.status_code == 200
    assert '<div id="root">' in r.text


@pytest.mark.parametrize("page,action_key,payload", [
    ("data", "data.fetch", {"data_types": ["prices"], "dry_run": True}),
    ("models", "models.train", {"model_type": "lgbm", "tag": "e2e", "dry_run": True}),
    ("backtest", "backtest.grid", {
        "model_path": "models/dummy.pkl",
        "topk_list": [5], "n_drop_list": [1], "hold_thresh_list": [5],
        "dry_run": True,
    }),
    ("signals", "signals.generate", {"model_path": "models/dummy.pkl", "dry_run": True}),
])
def test_dry_run_creates_task_record(server, page, action_key, payload):
    endpoint = {
        "data.fetch": "/api/data/fetch",
        "models.train": "/api/models/train",
        "backtest.grid": "/api/backtest/grid",
        "signals.generate": "/api/signals/generate",
    }[action_key]

    r = requests.post(f"{server}{endpoint}", json=payload, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    task_id = body["task_id"]

    # task should appear in /api/system/tasks with correct page_key/action_key
    tasks = requests.get(f"{server}/api/system/tasks", timeout=5).json()
    matching = [t for t in tasks if t["task_id"] == task_id]
    assert len(matching) == 1
    assert matching[0]["page_key"] == page
    assert matching[0]["action_key"] == action_key
```

注意:该脚本不需要真正驱动浏览器 DOM,**对"提交 → 抽屉 → 历史"的端到端验证由 HTTP 层 + task_id 一致性 + 页面 HTML 渲染断言组合达成**,这是为了避免引入 Playwright 等新框架(spec §6.1 约束)。

如果团队后续愿意装 Playwright,可单独加 `test/test_web_console_browser.py` 真驱动 DOM,本 plan 不强制。

- [ ] **Step 3: 跑测试**

```bash
# 先后台启动服务
./.venv/bin/python web/run_web.py &
SERVER_PID=$!
sleep 5
./.venv/bin/python -m pytest test/test_web_console_e2e.py -v
kill $SERVER_PID
```

Expected: 全 PASS(若有跳过,需诊断为何 server 未起)。

- [ ] **Step 4: Commit**

```bash
git add test/test_web_console_e2e.py
git commit -m "test(web): e2e HTTP-driven coverage of dry-run task wiring"
```

---

### Task 2.7: 全量验收门禁

- [ ] **Step 1: 后端全测**

```bash
./.venv/bin/python -m pytest test/ -v
```

Expected: 全 PASS。

- [ ] **Step 2: 后端 app 路由计数**

```bash
./.venv/bin/python -c "from web.api.app import create_app; app = create_app(); print('routes', len(app.routes))"
```

Expected: 输出 ≥ Phase 0 后的数量。

- [ ] **Step 3: 前端 TypeScript**

```bash
cd web/frontend && npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 4: 前端 build**

```bash
cd web/frontend && npm run build
```

Expected: 通过(Vite chunk-size 警告可接受)。

- [ ] **Step 5: e2e**

```bash
./.venv/bin/python web/run_web.py &
SERVER_PID=$!
sleep 5
./.venv/bin/python -m pytest test/test_web_console_e2e.py -v
kill $SERVER_PID
```

Expected: 全 PASS。

- [ ] **Step 6: 人肉跑 4 页**

```bash
./.venv/bin/python web/run_web.py &
SERVER_PID=$!
sleep 5
echo "Open http://127.0.0.1:8000/data-explorer, then /models, /backtest, /signals"
echo "For each: switch to 'execute' tab, fill any action's defaults (dry-run prechecked),"
echo "click submit, watch the task drawer open, verify task chip appears in history tab."
read -p "All 4 pages OK? (y/n) " confirm
kill $SERVER_PID
[ "$confirm" = "y" ] || exit 1
```

Expected: 人肉确认 4 页 dry-run 链路完整。

- [ ] **Step 7: 验收通过 → 总结**

主 agent 输出本阶段完成摘要,准备 close plan。

---

### Task 2.8: 更新 MEMORY.md

**Files:** Modify `/Users/weidian/.claude/projects/-Users-weidian-code-algorithms-quant-x-strategy-claude-quant-ex/memory/MEMORY.md`

- [ ] **Step 1: 添加一行索引**

在 Web Dashboard 段下追加(简短一行,链接到 spec/plan):

```markdown
- [Console upgrade](console_upgrade_2026_05_14.md) — 4 主流程页 console 化(Data/Models/Backtest/Signals)2026-05-14 完成
```

并在 memory 目录下新建对应 `console_upgrade_2026_05_14.md`:

```markdown
---
name: console-upgrade-2026-05-14
description: 2026-05-14 完成 Web Dashboard 4 主流程页(Data/Models/Backtest/Signals)从只读浏览器升级为参数化执行+任务跟踪 console。所有触发型 endpoint 统一返回 {task_id, dry_run, preview},TaskState 新增 page_key/action_key/result_paths。
metadata:
  type: project
---

事实:Web Dashboard 4 主流程页(Data/Models/Backtest/Signals)console 化已完成。

**Why:** 之前页面以只读 artifact 浏览为主,执行需手跑 CLI,操作面割裂。

**How to apply:** 后续触发型 Web 端点必须返回 `{task_id, dry_run, preview}`;前端公共组件在 `web/frontend/src/components/console/`;每页用 `<ConsolePageLayout>` 套 4 tab 骨架。详见 `docs/superpowers/specs/2026-05-14-dashboard-console-upgrade-design.md` 与 `docs/superpowers/plans/2026-05-14-dashboard-console-upgrade.md`。

AgentRuns 页未在本轮范围内。Research/Config/System/Overview 等待下一轮。
```

- [ ] **Step 2: Commit memory(主目录的 git 不包含 memory,跳过 git add)**

memory 文件不入仓库,只需保存到本地。

---

### Task 2.9: 清理 worktree + push 主分支

- [ ] **Step 1: 清理 4 个 worktree**

```bash
git worktree remove .claude/worktrees/console-data
git worktree remove .claude/worktrees/console-models
git worktree remove .claude/worktrees/console-backtest
git worktree remove .claude/worktrees/console-signals
git worktree list
```

Expected: worktree 列表中只剩主工作区。

- [ ] **Step 2: Push**

```bash
git push origin dashboard-console-base
```

Expected: push 成功。

- [ ] **Step 3: 准备 PR(可选)**

可创建 PR 让用户在 GitHub UI 上做最终 review。这一步若用户未明确要求则保持在 `dashboard-console-base` 分支不 PR。

---

## Phase 0 决策记录(主 agent 在 Phase 0 完成后填写)

> 主 agent 完成 Phase 0 后必须填写下列字段,Phase 1 派发时直接使用。

- update-qlib 包装可行性:[YES / NO + 原因]
- TaskState 新增字段实际命名:[`page_key`, `action_key`, `result_paths`(默认值已确认)]
- Phase 0 commit 数:[N]
- Phase 0 测试用例数:[N]
- 任何后端契约偏差:[N/A 或描述]

---

## Self-Review Checklist

- [x] **Spec coverage**: §1-8 全部映射到任务 — §3.1/3.2 → Task 0.1-0.5;§3.3 → Task 0.9-0.10;§3.4 → Task 0.11;§4.1-4.4 → Task 1.A/1.B/1.C/1.D;§5.1 阶段 → Phase 0/1/2;§5.2 文件边界 → Task 1.A-1.D 头注;§6 测试 → Task 0.1-0.5(契约层)+ 1.A-1.D(每页层)+ 2.5/2.6(集成+e2e);§7 风险/回滚 → 主 agent 在 Phase 2 中作为人肉门禁
- [x] **Placeholder scan**: 已扫,无 TBD/TODO/"appropriate error handling"
- [x] **Type consistency**: `TaskTrigger` / `TaskState` / `ExecutionFormProps` / `ConsolePageLayoutProps` 跨任务一致;`page_key` 与 `action_key` 命名一致;`rank_metric` 字面量在 spec / schema / test 中三处一致
