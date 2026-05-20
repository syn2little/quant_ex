from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from .schemas import ScoutItem


DATA_EXCLUSION_HINTS = {
    "tick data",
    "order book dataset",
    "level 2 dataset",
    "fundamental database",
    "earnings estimate feed",
    "price api",
    "real-time quote api",
}

FINANCE_REQUIRED_SOURCE_TYPES = {"arxiv"}

FINANCE_HINTS = {
    "finance",
    "financial",
    "market",
    "trading",
    "portfolio",
    "asset",
    "equity",
    "stock",
    "returns",
    "alpha",
    "factor",
    "risk",
    "drawdown",
    "volatility",
    "option",
    "execution",
    "order-flow",
    "q-fin",
}

OFF_TOPIC_HINTS = {
    "protein",
    "protein structure",
    "crystallography",
    "nuclear",
    "nuclear fission",
    "nuclear fusion",
    "medical image",
}


def filter_items(
    items: Iterable[ScoutItem],
    *,
    include_keywords: Sequence[str] = (),
    exclude_keywords: Sequence[str] = (),
) -> List[ScoutItem]:
    seen = set()
    kept: List[ScoutItem] = []
    exclude = {k.lower() for k in list(exclude_keywords) + list(DATA_EXCLUSION_HINTS) + list(OFF_TOPIC_HINTS)}
    include = [k.lower() for k in include_keywords]
    for item in items:
        key = _dedupe_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        haystack = _haystack(item)
        if any(term in haystack for term in exclude):
            continue
        if item.source_type in FINANCE_REQUIRED_SOURCE_TYPES and not any(term in haystack for term in FINANCE_HINTS):
            continue
        if include and not any(term in haystack for term in include):
            continue
        kept.append(item)
    return kept


def _dedupe_key(item: ScoutItem) -> str:
    if item.url:
        return item.url.strip().lower().rstrip("/")
    return re.sub(r"\W+", "-", item.title.lower()).strip("-")


def _haystack(item: ScoutItem) -> str:
    return " ".join([item.title, item.summary, " ".join(item.tags)]).lower()
