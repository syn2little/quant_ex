import json
from datetime import datetime, date as date_mod, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from web.api.deps import CACHE_DIR, get_config
from web.api.services.task_manager import get_task_manager
from web.api.routers.system import stream_task

router = APIRouter()


class FetchRequest(BaseModel):
    type: Optional[str] = None
    data_types: Optional[list[str]] = None
    date_range: Optional[dict[str, Optional[str]]] = None
    scope: str = "all"
    symbols: Optional[list[str]] = None
    universe: Optional[str] = None
    ttl: Optional[int] = None
    force: bool = False
    force_refresh: bool = False
    dry_run: bool = True


class CacheStatus(BaseModel):
    type: str
    file_count: int
    total_size_mb: float
    latest: Optional[str]
    ttl_days: int


def _get_fetcher_registry():
    from quant_ex.run_fetch_data import _FETCHER_REGISTRY
    return _FETCHER_REGISTRY


def _resolve_fetch_types(req: FetchRequest) -> list[str]:
    if req.data_types:
        return req.data_types
    if req.type == "all":
        return list(_get_fetcher_registry().keys())
    if req.type:
        return [req.type]
    return ["financial"]


def _build_fetch_preview(req: FetchRequest) -> dict:
    data_types = _resolve_fetch_types(req)
    registry = _get_fetcher_registry()
    skipped_cached = []
    if not (req.force_refresh or req.force):
        for data_type in data_types:
            cache_dir = registry.get(data_type, (None, f"./cache/{data_type}", None))[1]
            cache_path = Path(cache_dir)
            if cache_path.exists() and any(cache_path.glob("*.csv")):
                skipped_cached.append(data_type)
    return {
        "data_types": data_types,
        "date_range": req.date_range,
        "force_refresh": req.force_refresh or req.force,
        "estimated_files": len(data_types),
        "estimated_minutes": max(1, len(data_types) * 2),
        "estimated_disk_mb": len(data_types) * 5,
        "skipped_cached": skipped_cached,
    }


def _do_fetch(**kwargs) -> dict:
    from quant_ex.run_fetch_data import fetch_generic, _FETCHER_REGISTRY

    data_types = kwargs["data_types"]
    ttl_override = kwargs.get("ttl")
    force_refresh = kwargs.get("force_refresh", False)

    results = {}
    for data_type in data_types:
        if data_type not in _FETCHER_REGISTRY:
            results[data_type] = "skipped: unknown type"
            continue
        _cls_name, cache_dir, ttl = _FETCHER_REGISTRY[data_type]
        ttl = 0 if force_refresh else (ttl_override or ttl)
        try:
            fetch_generic(data_type, symbols=kwargs.get("symbols") or [], cache_dir=cache_dir, ttl_days=ttl)
            results[data_type] = "done"
        except Exception as exc:
            results[data_type] = f"error: {exc}"
    return results


def _list_expired_files(data_type: str) -> tuple[list[Path], int]:
    registry = _get_fetcher_registry()
    if data_type not in registry:
        raise HTTPException(status_code=400, detail=f"Unknown type: {data_type}")
    _, cache_dir, ttl = registry[data_type]
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return [], ttl
    expired = []
    for path in cache_path.glob("*.csv"):
        mtime = date_mod.fromtimestamp(path.stat().st_mtime)
        if (date_mod.today() - mtime).days > ttl:
            expired.append(path)
    return expired, ttl


def _normalize_sector_symbol(code: str) -> str:
    raw = str(code).strip().upper()
    if not raw:
        return raw
    if raw.startswith(("SH", "SZ", "BJ")):
        return raw
    if raw.startswith(("6", "9")):
        return f"SH{raw}"
    if raw.startswith(("8", "4")):
        return f"BJ{raw}"
    return f"SZ{raw}"


def _load_sector_groups() -> dict[str, dict]:
    """Load sectors from the checked-in sector map, with crawler cache fallback."""
    sector_map_path = CACHE_DIR / "sector_map.json"
    if sector_map_path.exists():
        with open(sector_map_path, encoding="utf-8") as f:
            sector_map = json.load(f)
        groups: dict[str, dict] = {}
        for symbol, sector_name in sector_map.items():
            sector_id = str(sector_name)
            group = groups.setdefault(
                sector_id,
                {"sector_id": sector_id, "sector_name": sector_id, "stocks": []},
            )
            group["stocks"].append(_normalize_sector_symbol(symbol))
        for group in groups.values():
            group["stocks"] = sorted(set(group["stocks"]))
        return groups

    crawler_path = Path(__file__).resolve().parents[3] / "crawler" / "data" / "sector_stocks.json"
    if not crawler_path.exists():
        return {}

    with open(crawler_path, encoding="utf-8") as f:
        crawler_data = json.load(f)

    groups = {}
    for category_data in crawler_data.values():
        if not isinstance(category_data, dict):
            continue
        for sector_id, payload in category_data.items():
            if not isinstance(payload, dict):
                continue
            stocks = [
                _normalize_sector_symbol(item.get("code", ""))
                for item in payload.get("stocks", [])
                if item.get("code")
            ]
            groups[sector_id] = {
                "sector_id": sector_id,
                "sector_name": payload.get("name") or sector_id,
                "stocks": sorted(set(stocks)),
            }
    return groups


@router.get("/cache-status")
async def cache_status():
    registry = _get_fetcher_registry()
    results = []
    for name, (cls_name, cache_dir, ttl) in registry.items():
        d = Path(cache_dir)
        if not d.exists():
            results.append(CacheStatus(type=name, file_count=0, total_size_mb=0.0, latest=None, ttl_days=ttl))
            continue
        files = list(d.glob("*.csv"))
        total_size = sum(f.stat().st_size for f in files)
        latest = max((f.stat().st_mtime for f in files), default=0)
        results.append(CacheStatus(
            type=name,
            file_count=len(files),
            total_size_mb=round(total_size / 1024 / 1024, 2),
            latest=datetime.fromtimestamp(latest).isoformat() if latest else None,
            ttl_days=ttl,
        ))
    return results


@router.post("/fetch")
async def start_fetch(req: FetchRequest):
    tm = get_task_manager()
    data_types = _resolve_fetch_types(req)
    if req.dry_run:
        preview = _build_fetch_preview(req)
        task_id = await tm.start_sync_task(
            "data_fetch_dry_run",
            lambda: preview,
            page_key="data",
            action_key="data.fetch",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    task_id = await tm.start_sync_task(
        "data_fetch",
        _do_fetch,
        page_key="data",
        action_key="data.fetch",
        data_types=data_types,
        date_range=req.date_range,
        force_refresh=req.force_refresh or req.force,
        symbols=req.symbols or [],
        universe=req.universe,
        ttl=req.ttl,
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.get("/fetch/{task_id}/stream")
async def stream_fetch(task_id: str):
    return await stream_task(task_id)


@router.delete("/cache/{data_type}/expired")
async def delete_expired(data_type: str, dry_run: bool = Query(True)):
    tm = get_task_manager()
    expired, ttl = _list_expired_files(data_type)
    files = [str(path) for path in expired]
    freed_bytes = sum(path.stat().st_size for path in expired)

    if dry_run:
        preview = {
            "data_type": data_type,
            "ttl_days": ttl,
            "files": files,
            "count": len(files),
            "freed_bytes": freed_bytes,
        }
        task_id = await tm.start_sync_task(
            "data_purge_dry_run",
            lambda: preview,
            page_key="data",
            action_key="data.purge_expired",
        )
        return {"task_id": task_id, "dry_run": True, "preview": preview}

    def _do_purge() -> dict:
        deleted = 0
        for path in expired:
            if path.exists():
                path.unlink()
                deleted += 1
        return {"deleted": deleted, "result_paths": []}

    task_id = await tm.start_sync_task(
        "data_purge",
        _do_purge,
        page_key="data",
        action_key="data.purge_expired",
    )
    return {"task_id": task_id, "dry_run": False, "preview": None}


@router.get("/stock-lookup/{symbol}")
async def stock_lookup(symbol: str):
    from quant_ex.data.utils import load_stock_names
    names = load_stock_names()
    matched = {k: v for k, v in names.items() if symbol.upper() in k or symbol.lower() in v.lower()}
    if not matched:
        return {"symbol": symbol, "matches": []}

    registry = _get_fetcher_registry()
    result = []
    for sym, name in matched.items():
        cache_files = []
        for dtype, (_, cache_dir, _) in registry.items():
            d = Path(cache_dir)
            if d.exists():
                bare = sym[2:]
                for f in d.glob(f"*{bare}*"):
                    cache_files.append({
                        "type": dtype,
                        "file": f.name,
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
        result.append({"symbol": sym, "name": name, "cache_files": cache_files})
    return {"symbol": symbol, "matches": result}


@router.get("/stock/search")
async def stock_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    from web.api.services.data_service import search_stocks
    return search_stocks(q, limit)


@router.get("/stock/{symbol}/quotes")
async def stock_quotes(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    fields: Optional[str] = None,
):
    from web.api.services.data_service import get_stock_quotes
    field_list = fields.split(",") if fields else None
    return get_stock_quotes(symbol, start or "2020-01-01", end, field_list)


@router.get("/sectors")
async def list_sectors():
    groups = _load_sector_groups()
    return sorted(
        [
            {
                "sector_id": group["sector_id"],
                "sector_name": group["sector_name"],
                "stock_count": len(group["stocks"]),
            }
            for group in groups.values()
        ],
        key=lambda item: (-item["stock_count"], item["sector_name"]),
    )


@router.get("/sectors/rotation")
async def sector_rotation(windows: str = Query("1,5,20")):
    from web.api.services.data_service import _qlib_loader, _cached

    window_list = [int(w) for w in windows.split(",") if w.strip().isdigit()]

    def _compute():
        sector_data = _load_sector_groups()

        if not sector_data:
            return []

        loader = _qlib_loader()
        if loader is None:
            return []

        today = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=max(window_list) + 30)).strftime("%Y-%m-%d")

        results = []
        for sector_id, group in sector_data.items():
            stocks = group["stocks"]
            if not stocks:
                continue
            qlib_instruments = stocks[:50]

            try:
                price_data = loader.load(
                    instruments=qlib_instruments,
                    start_time=start,
                    end_time=today,
                    fields=["$close"],
                )
                if price_data is None or price_data.empty:
                    continue

                close = price_data["$close"].unstack(level=0) if hasattr(price_data["$close"], "unstack") else None
                if close is None or close.empty:
                    continue

                sector_mean = close.mean(axis=1)
                returns = {}
                for w in window_list:
                    if len(sector_mean) > w:
                        ret = (sector_mean.iloc[-1] / sector_mean.iloc[-w - 1] - 1) if len(sector_mean) > w + 1 else 0.0
                        returns[f"{w}d"] = round(float(ret), 4)

                results.append({
                    "sector_id": sector_id,
                    "sector_name": group["sector_name"],
                    "returns": returns,
                })
            except Exception:
                continue

        return results

    cache_key = f"sector_rotation_{windows}"
    return _cached(cache_key, ttl=14400.0, factory=_compute)


@router.get("/sectors/{sector_id}/stocks")
async def sector_stocks(sector_id: str):
    groups = _load_sector_groups()
    group = groups.get(sector_id)
    if group is None:
        return {"sector_id": sector_id, "sector_name": sector_id, "stocks": []}
    from quant_ex.data.utils import load_stock_names
    names = load_stock_names()
    return {
        "sector_id": sector_id,
        "sector_name": group["sector_name"],
        "stocks": [{"symbol": s, "name": names.get(s, s)} for s in group["stocks"]],
    }


@router.get("/alt-data/{data_type}")
async def alt_data(
    data_type: str,
    symbol: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    cache_dir = CACHE_DIR / data_type
    if not cache_dir.exists():
        return {"type": data_type, "columns": [], "rows": [], "total": 0, "has_more": False}

    import pandas as pd
    csv_files = sorted(cache_dir.glob("*.csv"))
    if not csv_files:
        return {"type": data_type, "columns": [], "rows": [], "total": 0, "has_more": False}

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f)
            if symbol and "symbol" in df.columns:
                df = df[df["symbol"].str.contains(symbol, case=False, na=False)]
            dfs.append(df)
        except Exception:
            continue

    if not dfs:
        return {"type": data_type, "columns": [], "rows": [], "total": 0, "has_more": False}

    combined = pd.concat(dfs, ignore_index=True)

    if start and "date" in combined.columns:
        combined = combined[combined["date"] >= start]
    if end and "date" in combined.columns:
        combined = combined[combined["date"] <= end]

    total = len(combined)
    has_more = total > limit
    combined = combined.head(limit)

    columns = combined.columns.tolist()
    rows = combined.to_dict(orient="records")
    for row in rows:
        for k, v in row.items():
            if pd.isna(v):
                row[k] = None

    return {"type": data_type, "columns": columns, "rows": rows, "total": total, "has_more": has_more}
