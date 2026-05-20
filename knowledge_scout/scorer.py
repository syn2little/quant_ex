from __future__ import annotations

import re
from typing import List

from .schemas import IdeaScore, ScoutItem


HIGH_FIT_TERMS = {
    "cross-sectional": 2,
    "stock returns": 2,
    "factor": 2,
    "portfolio": 2,
    "risk model": 2,
    "drawdown": 2,
    "regime": 2,
    "time series": 1,
    "machine learning": 1,
    "transformer": 1,
    "backtest": 1,
    "alpha": 1,
}

FINANCE_TERMS = {
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

OFF_TOPIC_TERMS = {
    "protein",
    "crystallography",
    "nuclear",
    "fission",
    "fusion",
    "medical",
}

WEAK_SIGNAL_SOURCES = {"x_search", "youtube"}


def score_item(item: ScoutItem) -> IdeaScore:
    text = _text(item)
    is_finance = any(term in text for term in FINANCE_TERMS)
    is_off_topic = any(term in text for term in OFF_TOPIC_TERMS) and not is_finance
    fit = min(5, 1 + sum(weight for term, weight in HIGH_FIT_TERMS.items() if term in text))
    if is_off_topic:
        fit = 0
    elif item.source_type == "arxiv" and not is_finance:
        fit = min(fit, 1)
    evidence = _evidence_score(item)
    novelty = _novelty_score(text)
    cost = _implementation_cost(text)
    risk_flags: List[str] = []
    if is_off_topic:
        risk_flags.append("off_topic_non_finance")
    if item.source_type in WEAK_SIGNAL_SOURCES:
        risk_flags.append("weak_signal_requires_corroboration")
    if "crypto" in text and "equity" not in text and "stock" not in text:
        risk_flags.append("non_a_share_asset_class")
    action = _recommended_action(fit, evidence, cost, risk_flags)
    return IdeaScore(
        quant_ex_fit_score=fit,
        novelty_score=novelty,
        evidence_score=evidence,
        implementation_cost=cost,
        recommended_action=action,
        risk_flags=risk_flags,
    )


def _text(item: ScoutItem) -> str:
    return " ".join([item.title, item.summary, " ".join(item.tags), item.source_type]).lower()


def _evidence_score(item: ScoutItem) -> int:
    if item.source_type == "arxiv":
        return 4
    if item.source_type == "html_index" and item.raw.get("metadata_only"):
        return 2
    if item.source_type == "rss":
        return 3
    return 1


def _novelty_score(text: str) -> int:
    if any(term in text for term in ["transformer", "foundation model", "graph neural", "attention", "regime"]):
        return 4
    if any(term in text for term in ["factor", "anomaly", "portfolio", "risk"]):
        return 3
    return 2


def _implementation_cost(text: str) -> str:
    if any(term in text for term in ["tick", "order book", "intraday", "high frequency", "options"]):
        return "high"
    if any(term in text for term in ["transformer", "deep", "foundation model", "reinforcement"]):
        return "medium"
    return "low"


def _recommended_action(fit: int, evidence: int, cost: str, risk_flags: List[str]) -> str:
    if fit <= 0 or "off_topic_non_finance" in risk_flags:
        return "reject"
    if fit < 2 or "non_a_share_asset_class" in risk_flags:
        return "watch"
    if evidence >= 4 and fit >= 4 and cost != "high":
        return "prototype"
    if evidence >= 3 and fit >= 3:
        return "summarize"
    return "watch"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or "idea"
