from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from .filters import filter_items
from .llm import LLMError, call_openai_compatible_chat
from .publisher import publish_brief, render_source_report, render_weekly_brief, write_raw_cache
from .sources import build_adapter
from .storage import load_config, load_sources
from .synthesis import build_synthesis_prompt, render_rule_based_synthesis
from .synthesizer import build_brief


def collect_items(config_path: Path, *, tier: int = 1, limit: int = 20, timeout: int = 20):
    config = load_config(config_path)
    filters = config.get("filters", {}) or {}
    items = []
    items_by_source = {}
    errors = []
    for source in load_sources(config, tier=tier):
        try:
            fetched = build_adapter(source, timeout=timeout).fetch()
            source_items = fetched[: source.max_items]
            items.extend(source_items)
            items_by_source[source.name] = source_items
        except Exception as exc:
            errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
            items_by_source[source.name] = []
    filtered = filter_items(
        items,
        include_keywords=filters.get("include_keywords", []),
        exclude_keywords=filters.get("exclude_keywords", []),
    )
    return config, filtered[:limit], items_by_source, errors


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect external quant research ideas into guidance docs.")
    parser.add_argument("--config", default="config/knowledge_scout.yaml")
    parser.add_argument("--tier", type=int, default=1, help="Maximum source tier to run")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="Print brief without writing docs")
    parser.add_argument("--publish", action="store_true", help="Write markdown docs and raw metadata cache")
    parser.add_argument("--source-report", action="store_true", help="Include a per-source report explaining selected and filtered items")
    parser.add_argument("--synthesis", action="store_true", help="Generate a Chinese research synthesis memo")
    parser.add_argument("--use-llm", action="store_true", help="Use Hermes Agent LLM config for synthesis; fallback to rule-based memo on failure")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    config, items, items_by_source, errors = collect_items(
        config_path,
        tier=args.tier,
        limit=args.limit,
        timeout=args.timeout,
    )
    brief = build_brief(items, limit=args.limit)
    source_report = render_source_report(items_by_source, items)
    synthesis = ""
    if args.synthesis:
        if args.use_llm:
            try:
                synthesis = call_openai_compatible_chat(build_synthesis_prompt(brief, source_report))
            except LLMError as exc:
                errors.append(f"llm_synthesis: {exc}")
                synthesis = render_rule_based_synthesis(brief)
        else:
            synthesis = render_rule_based_synthesis(brief)

    if args.dry_run or not args.publish:
        print(render_weekly_brief(brief))
        if args.source_report:
            print("\n" + source_report)
        if synthesis:
            print("\n" + synthesis)
        if errors:
            print("\n## Source Errors", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
        return 0 if brief.idea_cards else 2

    raw_cache_dir = Path(config.get("raw_cache_dir", "cache/knowledge_scout"))
    output_dir = Path(config.get("output_dir", "docs/strategy_log/knowledge_scout"))
    write_raw_cache([item for source_items in items_by_source.values() for item in source_items], cache_dir=raw_cache_dir)
    written = publish_brief(brief, output_dir=output_dir)
    if args.source_report:
        reports_dir = output_dir / "source_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{brief.generated_at[:10]}_source_report.md"
        report_path.write_text(source_report, encoding="utf-8")
        written.append(report_path)
    if synthesis:
        synthesis_dir = output_dir / "synthesis"
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        synthesis_path = synthesis_dir / f"{brief.generated_at[:10]}_research_synthesis.md"
        synthesis_path.write_text(synthesis, encoding="utf-8")
        written.append(synthesis_path)
    for path in written:
        print(path)
    if errors:
        print("\n## Source Errors", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    return 0 if brief.idea_cards else 2


if __name__ == "__main__":
    raise SystemExit(main())
