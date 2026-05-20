from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


@dataclass
class SourceConfig:
    name: str
    source_type: str
    url: str = ""
    enabled: bool = True
    tier: int = 1
    query: str = ""
    keywords: List[str] = field(default_factory=list)
    max_items: int = 10
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SourceConfig":
        return cls(
            name=str(payload.get("name") or ""),
            source_type=str(payload.get("source_type") or payload.get("type") or ""),
            url=str(payload.get("url") or ""),
            enabled=bool(payload.get("enabled", True)),
            tier=int(payload.get("tier", 1)),
            query=str(payload.get("query") or ""),
            keywords=list(payload.get("keywords") or []),
            max_items=int(payload.get("max_items") or 10),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScoutItem:
    title: str
    url: str
    source_name: str
    source_type: str
    retrieved_at: str
    published_at: str = ""
    summary: str = ""
    authors: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ScoutItem":
        return cls(
            title=str(payload.get("title") or ""),
            url=str(payload.get("url") or ""),
            source_name=str(payload.get("source_name") or ""),
            source_type=str(payload.get("source_type") or ""),
            retrieved_at=str(payload.get("retrieved_at") or utc_now_iso()),
            published_at=str(payload.get("published_at") or ""),
            summary=str(payload.get("summary") or ""),
            authors=list(payload.get("authors") or []),
            tags=list(payload.get("tags") or []),
            raw=dict(payload.get("raw") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdeaScore:
    quant_ex_fit_score: int
    novelty_score: int
    evidence_score: int
    implementation_cost: str
    recommended_action: str
    risk_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdeaCard:
    idea_id: str
    title: str
    source_url: str
    source_name: str
    source_type: str
    retrieved_at: str
    claim: str
    mechanism: str
    evidence: str
    mapping_to_quant_ex: List[str]
    validation_ladder: List[str]
    kill_criteria: List[str]
    score: IdeaScore
    references: List[str] = field(default_factory=list)
    access: str = "open_or_metadata"
    asset_class_fit: str = "a_share_equity"
    horizon_fit: str = "daily_or_low_frequency"

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["score"] = self.score.to_dict()
        return payload


@dataclass
class ScoutBrief:
    generated_at: str
    items_considered: int
    idea_cards: List[IdeaCard]
    source_names: List[str]

    def top_ideas(self, limit: int = 5) -> List[IdeaCard]:
        return self.idea_cards[:limit]
