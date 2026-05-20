from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from .schemas import IdeaCard, ScoutBrief, ScoutItem, utc_now_iso
from .scorer import score_item, slugify


def build_idea_card(item: ScoutItem) -> IdeaCard:
    score = score_item(item)
    idea_id = datetime.now(timezone.utc).strftime("%Y%m%d") + "_" + slugify(item.title)[:48]
    mechanism = _infer_mechanism(item)
    mapping = _mapping_to_quant_ex(item)
    return IdeaCard(
        idea_id=idea_id,
        title=item.title,
        source_url=item.url,
        source_name=item.source_name,
        source_type=item.source_type,
        retrieved_at=item.retrieved_at,
        claim=item.summary or f"External item proposes a quant research direction: {item.title}.",
        mechanism=mechanism,
        evidence=_evidence_text(item),
        mapping_to_quant_ex=mapping,
        validation_ladder=[
            "Summarize mechanism and compare against existing rejected/promising research threads.",
            "Map the idea to one minimal feature/model/backtest change with a fixed control arm.",
            "Run a cheap same-model or small-window diagnostic only if implementation cost is low/medium.",
            "Promote to WFV only if the diagnostic improves IR/Sharpe without worsening drawdown controls.",
            "Require promotion report and human approval before touching strategy_candidates or rebalance configs.",
        ],
        kill_criteria=[
            "Do not ingest external market/fundamental time-series data; reject ideas that require it outside approved data sources.",
            "Reject if it cannot define a comparable control arm and rank metric.",
            "Kill if early diagnostic breaks current drawdown/positive-fold constraints.",
        ],
        score=score,
        references=[item.url],
    )


def build_brief(items: Iterable[ScoutItem], *, limit: int = 10) -> ScoutBrief:
    item_list = list(items)
    cards = [build_idea_card(item) for item in item_list]
    cards.sort(
        key=lambda card: (
            card.score.quant_ex_fit_score,
            card.score.evidence_score,
            card.score.novelty_score,
            -_cost_rank(card.score.implementation_cost),
        ),
        reverse=True,
    )
    cards = cards[:limit]
    return ScoutBrief(
        generated_at=utc_now_iso(),
        items_considered=len(item_list),
        idea_cards=cards,
        source_names=sorted({card.source_name for card in cards}),
    )


def _cost_rank(cost: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(cost, 2)


def _infer_mechanism(item: ScoutItem) -> str:
    text = " ".join([item.title, item.summary]).lower()
    if "drawdown" in text or "risk" in text:
        return "Risk-aware portfolio construction or drawdown control may improve stability before return repair."
    if "factor" in text or "anomaly" in text:
        return "Potential factor/anomaly mechanism that may translate into feature engineering or candidate filters."
    if "transformer" in text or "time series" in text or "machine learning" in text:
        return "Modeling architecture or training objective may improve ranking signal extraction."
    if "execution" in text:
        return "Execution-aware evaluation may change slippage/cost assumptions or rebalance rules."
    return "External research mechanism requires manual interpretation before local validation."


def _mapping_to_quant_ex(item: ScoutItem) -> List[str]:
    text = " ".join([item.title, item.summary]).lower()
    mapping: List[str] = []
    if any(term in text for term in ["factor", "anomaly", "attention"]):
        mapping.append("features/ or features/library/: candidate feature or factor diagnostic")
    if any(term in text for term in ["machine learning", "transformer", "time series", "prediction"]):
        mapping.append("models/: optional model architecture or training objective prototype")
    if any(term in text for term in ["portfolio", "risk", "drawdown", "regime"]):
        mapping.append("backtest/ and strategy/: portfolio construction, regime, or risk overlay diagnostic")
    if not mapping:
        mapping.append("agent/strategy_iteration/: research hypothesis only until mapped to a local experiment")
    return mapping


def _evidence_text(item: ScoutItem) -> str:
    if item.source_type == "arxiv":
        return "Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally."
    if item.source_type == "rss":
        return "Practitioner/blog metadata from RSS. Use as guidance, not promotion evidence."
    if item.raw.get("metadata_only"):
        return "Metadata-only HTML source. Manual review required before prototype."
    return "External metadata source. Evidence strength requires manual review."
