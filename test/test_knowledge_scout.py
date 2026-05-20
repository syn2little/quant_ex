from pathlib import Path

from agent.strategy_iteration.context import build_project_context
from knowledge_scout.filters import filter_items
from knowledge_scout.publisher import render_agent_context, render_idea_card, render_source_report, render_weekly_brief
from knowledge_scout.schemas import ScoutItem, SourceConfig
from knowledge_scout.scorer import score_item
from knowledge_scout.sources import ArxivSource, RSSSource, build_adapter
from knowledge_scout.storage import load_optional_source_stubs, load_sources
from knowledge_scout.synthesis import build_synthesis_prompt, render_rule_based_synthesis
from knowledge_scout.synthesizer import build_brief, build_idea_card


def item(title: str, summary: str = "", url: str = "https://example.com/a") -> ScoutItem:
    return ScoutItem(
        title=title,
        url=url,
        source_name="unit",
        source_type="rss",
        retrieved_at="2026-05-18T00:00:00Z",
        summary=summary,
    )


def test_source_config_supports_optional_stubs():
    config = {
        "sources": [{"name": "arxiv", "source_type": "arxiv", "query": "cat:q-fin.PM"}],
        "optional_sources": [{"name": "x", "source_type": "x_search", "enabled": False}],
    }

    sources = load_sources(config)
    optional = load_optional_source_stubs(config)

    assert sources[0].source_type == "arxiv"
    assert optional[0].source_type == "x_search"
    assert build_adapter(optional[0]).fetch() == []


def test_filter_removes_duplicates_and_market_data_items():
    items = [
        item("Cross-sectional stock returns factor", url="https://example.com/a"),
        item("Cross-sectional stock returns factor", url="https://example.com/a/"),
        item("New order book dataset for tick data", url="https://example.com/b"),
    ]

    kept = filter_items(items, include_keywords=["factor"], exclude_keywords=[])

    assert [x.url for x in kept] == ["https://example.com/a"]


def test_filter_rejects_off_topic_ml_papers_even_if_they_match_generic_terms():
    items = [
        item(
            "CrystalBoltz: End-to-End Protein Structure Determination via Experiment-Guided Diffusion",
            "machine learning model for X-Ray Crystallography",
            url="https://example.com/protein",
        ),
        item(
            "Vector-Quantized Discrete Latent Factors Meet Financial Priors",
            "dynamic cross-sectional stock ranking prediction for portfolio construction",
            url="https://example.com/finance",
        ),
    ]

    kept = filter_items(items, include_keywords=["machine learning", "factor", "portfolio"], exclude_keywords=[])

    assert [x.url for x in kept] == ["https://example.com/finance"]


def test_score_item_prefers_local_fit_research():
    scored = score_item(item("Machine learning factor for cross-sectional stock returns", "portfolio risk model backtest"))

    assert scored.quant_ex_fit_score >= 4
    assert scored.recommended_action in {"prototype", "summarize"}


def test_build_idea_card_contains_validation_guardrails():
    card = build_idea_card(item("Drawdown-aware portfolio factor", "risk model and factor backtest"))
    rendered = render_idea_card(card)

    assert "Validation Ladder" in rendered
    assert "Do not ingest external market/fundamental" in rendered
    assert card.mapping_to_quant_ex


def test_build_brief_and_agent_context_are_deterministic_enough():
    brief = build_brief([
        item("Risk model for portfolio drawdown", "factor backtest", "https://example.com/1"),
        item("Transformer for finance time series", "machine learning stock prediction", "https://example.com/2"),
    ])

    assert brief.idea_cards
    assert "External Knowledge Scout Brief" in render_weekly_brief(brief)
    assert "Latest External Knowledge Context" in render_agent_context(brief)


def test_source_report_explains_rss_items_and_filtering():
    raw_items = [
        item("Risk model for portfolio drawdown", "factor backtest", "https://example.com/1"),
        item("New order book dataset for tick data", "market data API", "https://example.com/2"),
    ]
    kept_items = filter_items(raw_items, include_keywords=["factor", "risk"], exclude_keywords=[])

    report = render_source_report({"robot_wealth": raw_items}, kept_items)

    assert "# Knowledge Scout Source Report" in report
    assert "robot_wealth" in report
    assert "Raw items: 2" in report
    assert "Selected items: 1" in report
    assert "Filtered/Not selected" in report


def test_rule_based_synthesis_and_prompt_are_guidance_oriented():
    brief = build_brief([
        item("Risk model for portfolio drawdown", "factor backtest", "https://example.com/1"),
        item("Vector quantized latent factors", "cross-sectional stock ranking portfolio", "https://example.com/2"),
    ])

    prompt = build_synthesis_prompt(brief, render_source_report({"unit": []}, []))
    synthesis = render_rule_based_synthesis(brief)

    assert "中文" in prompt
    assert "不要输出实盘信号" in prompt
    assert "# External Knowledge Scout Synthesis" in synthesis
    assert "最小验证实验" in synthesis
    assert "Phase7" in synthesis


def test_arxiv_source_parses_atom(monkeypatch):
    xml = '''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2601.00001v1</id><title>Portfolio Risk Model</title><summary>Cross-sectional factor model.</summary><published>2026-01-01T00:00:00Z</published><author><name>A Quant</name></author><category term="q-fin.PM" /></entry></feed>'''
    source = ArxivSource(SourceConfig(name="arxiv", source_type="arxiv", query="cat:q-fin.PM"))
    monkeypatch.setattr(source, "_request_text", lambda url: xml)

    items = source.fetch()

    assert items[0].title == "Portfolio Risk Model"
    assert items[0].url == "https://arxiv.org/abs/2601.00001v1"
    assert items[0].tags == ["q-fin.PM"]


def test_rss_source_parses_items(monkeypatch):
    xml = '''<rss><channel><item><title>Factor Portfolio</title><link>https://example.com/factor</link><description><![CDATA[<p>Backtest and risk model.</p>]]></description><pubDate>Mon, 18 May 2026 00:00:00 GMT</pubDate><category>factor</category></item></channel></rss>'''
    source = RSSSource(SourceConfig(name="rss", source_type="rss", url="https://example.com/feed"))
    monkeypatch.setattr(source, "_request_text", lambda url: xml)

    items = source.fetch()

    assert items[0].title == "Factor Portfolio"
    assert items[0].published_at == "2026-05-18"
    assert "Backtest" in items[0].summary


def test_build_project_context_reads_latest_knowledge_scout(tmp_path: Path):
    latest = tmp_path / "docs" / "strategy_log" / "knowledge_scout" / "latest_agent_context.md"
    latest.parent.mkdir(parents=True)
    latest.write_text(
        "# Latest External Knowledge Context (2026-05-18)\n\n## Risk Model Idea\n- Recommended action: prototype\n",
        encoding="utf-8",
    )

    context = build_project_context("external scout context", root=tmp_path)

    scout = context.artifact_summaries["external_knowledge_scout"]
    assert scout["path"] == "docs/strategy_log/knowledge_scout/latest_agent_context.md"
    assert scout["top_ideas"] == ["Risk Model Idea"]
    assert "hypothesis input only" in scout["guardrails"][0]
