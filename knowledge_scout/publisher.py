from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .schemas import IdeaCard, ScoutBrief, ScoutItem
from .scorer import score_item, slugify


def write_raw_cache(items: Iterable[ScoutItem], *, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "latest_items.json"
    path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def publish_brief(brief: ScoutBrief, *, output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ideas_dir = output_dir / "ideas"
    briefs_dir = output_dir / "briefs"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    briefs_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for card in brief.idea_cards:
        path = ideas_dir / f"{card.idea_id}_{slugify(card.title)[:40]}.md"
        path.write_text(render_idea_card(card), encoding="utf-8")
        written.append(path)

    date = brief.generated_at[:10]
    brief_path = briefs_dir / f"{date}_weekly_scout.md"
    brief_path.write_text(render_weekly_brief(brief), encoding="utf-8")
    written.append(brief_path)

    latest = output_dir / "latest_agent_context.md"
    latest.write_text(render_agent_context(brief), encoding="utf-8")
    written.append(latest)
    return written


def render_idea_card(card: IdeaCard) -> str:
    score = card.score
    lines = [
        f"# {card.title}",
        "",
        "```yaml",
        f"idea_id: {card.idea_id}",
        f"source_url: {card.source_url}",
        f"source_type: {card.source_type}",
        f"source_name: {card.source_name}",
        f"retrieved_at: {card.retrieved_at}",
        f"access: {card.access}",
        f"asset_class_fit: {card.asset_class_fit}",
        f"horizon_fit: {card.horizon_fit}",
        f"quant_ex_fit_score: {score.quant_ex_fit_score}",
        f"novelty_score: {score.novelty_score}",
        f"evidence_score: {score.evidence_score}",
        f"implementation_cost: {score.implementation_cost}",
        f"recommended_action: {score.recommended_action}",
        f"risk_flags: {score.risk_flags}",
        "```",
        "",
        "## Claim",
        card.claim,
        "",
        "## Mechanism",
        card.mechanism,
        "",
        "## Evidence",
        card.evidence,
        "",
        "## Mapping to quant_ex",
    ]
    lines.extend(f"- {item}" for item in card.mapping_to_quant_ex)
    lines.extend(["", "## Validation Ladder"])
    lines.extend(f"- {item}" for item in card.validation_ladder)
    lines.extend(["", "## Kill Criteria"])
    lines.extend(f"- {item}" for item in card.kill_criteria)
    lines.extend(["", "## References"])
    lines.extend(f"- {item}" for item in card.references)
    lines.append("")
    return "\n".join(lines)


def render_weekly_brief(brief: ScoutBrief) -> str:
    lines = [
        f"# External Knowledge Scout Brief: {brief.generated_at[:10]}",
        "",
        f"- Generated: {brief.generated_at}",
        f"- Items considered: {brief.items_considered}",
        f"- Sources: {', '.join(brief.source_names) or 'none'}",
        "",
        "## Top Ideas",
    ]
    for idx, card in enumerate(brief.idea_cards, start=1):
        lines.extend(
            [
                f"{idx}. **{card.title}**",
                f"   - Source: {card.source_name} ({card.source_type})",
                f"   - Action: {card.score.recommended_action}",
                f"   - Fit/Evidence/Novelty: {card.score.quant_ex_fit_score}/{card.score.evidence_score}/{card.score.novelty_score}",
                f"   - Mapping: {'; '.join(card.mapping_to_quant_ex)}",
                f"   - URL: {card.source_url}",
            ]
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "- This brief proposes research hypotheses only; it is not strategy promotion evidence.",
            "- Any prototype must define a control arm, rank metric, costs/slippage, and WFV promotion gate.",
            "- Do not ingest external market/fundamental time-series data through this module.",
            "",
        ]
    )
    return "\n".join(lines)


def render_source_report(items_by_source: dict[str, List[ScoutItem]], selected_items: Iterable[ScoutItem]) -> str:
    selected_urls = {item.url.strip().lower().rstrip("/") for item in selected_items}
    lines = [
        "# Knowledge Scout Source Report",
        "",
        "This report shows what each source returned and why only some items reached the brief.",
        "",
    ]
    for source_name, raw_items in sorted(items_by_source.items()):
        selected = [item for item in raw_items if item.url.strip().lower().rstrip("/") in selected_urls]
        filtered = [item for item in raw_items if item.url.strip().lower().rstrip("/") not in selected_urls]
        lines.extend(
            [
                f"## {source_name}",
                f"- Raw items: {len(raw_items)}",
                f"- Selected items: {len(selected)}",
                "",
                "### Selected",
            ]
        )
        if selected:
            for item in selected[:10]:
                score = score_item(item)
                lines.append(f"- {item.title} ({score.recommended_action}, fit/evidence/novelty {score.quant_ex_fit_score}/{score.evidence_score}/{score.novelty_score}) <{item.url}>")
        else:
            lines.append("- None")
        lines.extend(["", "### Filtered/Not selected"])
        if filtered:
            for item in filtered[:20]:
                score = score_item(item)
                reason = ", ".join(score.risk_flags) or "lower score, duplicate, or did not match final ranking"
                lines.append(f"- {item.title} ({reason}) <{item.url}>")
        else:
            lines.append("- None")
        lines.append("")
    return "\n".join(lines)


def render_agent_context(brief: ScoutBrief) -> str:
    lines = [
        f"# Latest External Knowledge Context ({brief.generated_at[:10]})",
        "",
        "Use these as weak-to-medium research hypotheses. Phase7 attribution and local validation remain binding.",
        "",
    ]
    for card in brief.idea_cards[:5]:
        lines.extend(
            [
                f"## {card.title}",
                f"- Source: {card.source_name} ({card.source_type}) <{card.source_url}>",
                f"- Recommended action: {card.score.recommended_action}",
                f"- Fit/Evidence/Novelty: {card.score.quant_ex_fit_score}/{card.score.evidence_score}/{card.score.novelty_score}",
                f"- Mechanism: {card.mechanism}",
                f"- Local mapping: {'; '.join(card.mapping_to_quant_ex)}",
                "",
            ]
        )
    return "\n".join(lines)
