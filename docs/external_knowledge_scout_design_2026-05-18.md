# External Knowledge Scout Design Plan

> **For Hermes:** This is a confirmation-first design plan. Do not implement until the user confirms source scope, cadence, and output policy.

**Goal:** Add a research-only external knowledge module that collects strong strategy, model, and quant research ideas, converts them into evidence-bound guidance documents, and feeds the agent strategy iteration process without ingesting market/fundamental time-series data.

**Architecture:** A small `knowledge_scout/` package will separate source discovery, document extraction, triage/scoring, synthesis, and publishing. It will store raw metadata and derived markdown locally, then expose compact guidance summaries to `agent/strategy_iteration/context.py` as research hints, not executable strategy conclusions.

**Tech Stack:** Python stdlib first (`urllib`, `feedparser` optional if accepted), YAML config, markdown outputs, pytest fixtures with mocked HTTP, optional Hermes tools/skills for ad-hoc enrichment.

---

## 1. Non-Goals and Guardrails

This module is not a market data crawler.

It must not collect:

- price bars, tick data, order books, holdings, fundamentals, analyst estimates, or company events for direct modeling;
- proprietary/paywalled full text unless the source explicitly allows it;
- credentials or API keys in repository files;
- auto-promoted strategies without backtest/WFV validation.

It may collect:

- paper metadata, abstracts, citations, links, and open-access text snippets;
- RSS/blog article metadata and summaries;
- public strategy descriptions, model architecture ideas, validation methods, failure modes, and implementation hypotheses;
- links to code repos or runnable examples, stored as references rather than blindly imported code.

Every output must include:

- source URL and retrieval timestamp;
- source type and license/access notes when known;
- applicability score to `quant_ex`;
- evidence strength and confidence;
- explicit validation ladder before any idea becomes a strategy candidate.

---

## 2. Proposed Source Pool

### Tier 1: Stable, high-signal sources for automated collection

| Source | Why useful | Access method | Initial filters |
|---|---|---|---|
| arXiv `q-fin.PM`, `q-fin.ST`, `q-fin.TR`, `cs.LG`, `stat.ML` | Fresh academic research on portfolio management, statistical finance, time-series ML | arXiv Atom API | `cross-sectional returns`, `portfolio optimization`, `factor model`, `time series transformer`, `market regime`, `risk model` |
| Quantpedia Blog | Practitioner summaries of published strategy research | RSS feed | strategy, factor, portfolio construction, robustness, regime |
| Alpha Architect | Factor investing, anomalies, portfolio construction | RSS feed | factor, anomaly, replication, ETF/portfolio construction |
| Quantocracy | Aggregator for quant blog posts | RSS feed | AQR, factor, backtest, machine learning, portfolio |
| Robot Wealth | Practical quant research and implementation | RSS feed | stat arb, features, robustness, portfolio, execution |
| Papers With Backtest | Executable paper/strategy discovery | HTML/API if available, metadata only | paper title, strategy category, code availability |

Connectivity smoke results on 2026-05-18:

- `https://quantpedia.com/blog/feed/` returned HTTP 200 RSS.
- `https://alphaarchitect.com/feed/` returned HTTP 200 RSS.
- `https://quantocracy.com/feed/` returned HTTP 200 XML.
- `https://robotwealth.com/feed/` returned HTTP 200 RSS.
- `https://paperswithbacktest.com/` returned HTTP 200 HTML.
- arXiv Atom API returned HTTP 200.
- Semantic Scholar returned HTTP 429 in an unauthenticated smoke test, so it should be optional/rate-limited only.

### Tier 2: Optional enrichment sources

| Source | Use | Risk/limit |
|---|---|---|
| Semantic Scholar | citation counts, influential citations, related papers | unauthenticated 429 risk; must cache and rate-limit |
| Hugging Face Daily Papers | ML model trend discovery | broad AI noise; needs finance/time-series filter |
| YouTube transcripts | lectures/interviews on strategies/models | transcript availability varies; summarize only with citations |
| X/Twitter search | breaking ideas, practitioner discussions | noisy; use only as weak signal, never as evidence alone |
| GitHub repo search | implementations of papers/models | license/security review required before code reuse |

---

## 3. Output Products

### 3.1 Weekly Scout Brief

Path pattern:

```text
docs/strategy_log/knowledge_scout/briefs/YYYY-MM-DD_weekly_scout.md
```

Contents:

- top 5 external ideas;
- why each matters to A-share low-frequency stock selection;
- candidate mapping to current system components (`features/`, `models/`, `strategy/`, `backtest/`, `agent/strategy_iteration/`);
- validation ladder;
- kill criteria;
- do-not-repeat notes.

### 3.2 Idea Cards

Path pattern:

```text
docs/strategy_log/knowledge_scout/ideas/YYYY-MM-DD_slug.md
```

Each card uses this schema:

```yaml
idea_id: YYYYMMDD_source_slug
source_url: https://...
source_type: paper|blog|repo|video|social
retrieved_at: ISO8601
access: open|metadata_only|paywalled_summary|unknown
asset_class_fit: a_share_equity|global_equity|multi_asset|crypto|commodity|other
horizon_fit: intraday|daily|weekly|monthly|unknown
quant_ex_fit_score: 0-5
novelty_score: 0-5
evidence_score: 0-5
implementation_cost: low|medium|high
risk_flags: []
recommended_action: reject|watch|summarize|prototype|backtest
```

Markdown sections:

- Claim
- Mechanism
- Evidence
- Mapping to `quant_ex`
- Minimal prototype path
- Validation ladder
- Kill criteria
- References

### 3.3 Agent Context Summary

Path:

```text
docs/strategy_log/knowledge_scout/latest_agent_context.md
```

This is a compact rolling summary consumed by the agent planner. It should contain only top actionable ideas and explicit constraints, not long raw notes.

---

## 4. Package Layout

Proposed files:

```text
knowledge_scout/
  __init__.py
  schemas.py              # SourceConfig, ScoutItem, IdeaCard, ScoutBrief
  sources.py              # arXiv/RSS/HTML source adapters
  filters.py              # keyword, asset-class, horizon, duplicate filters
  scorer.py               # fit/evidence/novelty/cost scoring
  synthesizer.py          # item -> idea card -> weekly brief
  storage.py              # local json/md persistence
  publisher.py            # markdown writers
  cli.py                  # run scout/refresh/publish
config/knowledge_scout.yaml
run_knowledge_scout.py
test/test_knowledge_scout.py
docs/strategy_log/knowledge_scout/README.md
```

The module should be independent from existing `crawler/`, because `crawler/` currently implies financial data extraction. Keeping a separate `knowledge_scout/` namespace reduces the risk of mixing research ideas with market/fundamental data.

---

## 5. Data Flow

```text
config/knowledge_scout.yaml
  -> Source adapters fetch metadata/articles
  -> Filters remove duplicates, off-topic, inaccessible items
  -> Scorer ranks fit/evidence/novelty/cost
  -> Synthesizer writes idea cards + weekly brief
  -> latest_agent_context.md feeds agent strategy iteration
  -> human approves any prototype/backtest task
```

No fetched idea should directly change:

- `config/strategy_candidates.yaml`
- model configs
- daily rebalance configs
- launchd jobs
- live signals

Promotion requires the existing strategy validation chain: prototype -> small backtest -> WFV -> attribution -> promotion report -> human approval.

---

## 6. Integration with Existing Agent Iteration

After implementation, update `agent/strategy_iteration/context.py` to optionally include:

```python
artifact_summaries["external_knowledge_scout"] = {
    "latest_context_path": "docs/strategy_log/knowledge_scout/latest_agent_context.md",
    "top_ideas": [...],
    "guardrails": [...],
}
```

Planner rule:

- external knowledge can propose hypotheses;
- Phase7 attribution still decides budget focus;
- strategy performance claims require local validation;
- weak sources such as X/social can only create `watch` items unless corroborated.

---

## 7. Initial Scoring Rubric

| Dimension | 0 | 3 | 5 |
|---|---|---|---|
| `quant_ex_fit_score` | unrelated asset/horizon | related but requires major infra | daily equity selection or portfolio/risk method fits current stack |
| `evidence_score` | opinion only | paper/blog with partial evidence | peer-reviewed or reproducible backtest/code with robust validation |
| `novelty_score` | already tried/rejected | adjacent variation | new mechanism not covered by current candidates |
| `implementation_cost` | high infra/data burden | moderate feature/model changes | small prototype in existing `features/`/`models/`/`backtest/` |

Recommended action:

- `reject`: low fit or high risk;
- `watch`: interesting but weak evidence or poor local fit;
- `summarize`: useful guidance but not testable yet;
- `prototype`: cheap implementation path exists;
- `backtest`: already maps cleanly to current framework and has strong evidence.

---

## 8. Implementation Plan After Confirmation

### Task 1: Add config and schemas

Files:

- Create `config/knowledge_scout.yaml`
- Create `knowledge_scout/schemas.py`
- Create `test/test_knowledge_scout.py`

Verification:

```bash
./.venv/bin/python -m pytest test/test_knowledge_scout.py -q
```

Expected: schema serialization/deserialization tests pass.

### Task 2: Implement source adapters with mocked tests

Files:

- Create `knowledge_scout/sources.py`
- Extend `test/test_knowledge_scout.py`

Adapters:

- `ArxivSource`
- `RSSSource`
- `StaticHtmlSource` for Papers With Backtest metadata only

Tests must mock network responses. No live network required in CI.

### Task 3: Implement filters and scorer

Files:

- Create `knowledge_scout/filters.py`
- Create `knowledge_scout/scorer.py`

Verification:

- duplicate URL/title removal;
- exclusion of market/fundamental data items;
- scoring favors daily equity strategy/model/portfolio construction ideas.

### Task 4: Implement markdown publisher

Files:

- Create `knowledge_scout/synthesizer.py`
- Create `knowledge_scout/publisher.py`
- Create `docs/strategy_log/knowledge_scout/README.md`

Verification:

- generated markdown includes source URLs, scores, validation ladder, kill criteria;
- generated docs are deterministic in tests.

### Task 5: Add CLI dry-run

Files:

- Create `knowledge_scout/cli.py`
- Create `run_knowledge_scout.py`

Commands:

```bash
./.venv/bin/python run_knowledge_scout.py --config config/knowledge_scout.yaml --dry-run --limit 20
./.venv/bin/python run_knowledge_scout.py --config config/knowledge_scout.yaml --publish --limit 20
```

Dry-run prints selected items without writing idea cards. Publish writes docs only.

### Task 6: Integrate with agent context

Files:

- Modify `agent/strategy_iteration/context.py`
- Extend `test/test_agent_strategy_iteration.py` or add `test/test_knowledge_scout_agent_context.py`

Verification:

```bash
./.venv/bin/python -m pytest test/test_knowledge_scout.py test/test_agent_strategy_iteration.py -q
```

Expected: existing agent tests stay green, new context includes latest scout summary when file exists.

---

## 9. Open Decisions for User Confirmation

Please confirm these before implementation:

1. Cadence: should the scout be manual only, weekly cron, or agent-triggered before each strategy iteration?
2. Source scope: start with Tier 1 only, or include X/YouTube/GitHub from day one?
3. Output language: English source notes, Chinese guidance summaries, or bilingual?
4. Storage policy: keep only markdown summaries, or also store raw fetched metadata JSON under ignored cache?
5. Integration strictness: should external ideas only appear in docs, or should `run_agent_strategy_iteration.py` include them automatically in context?
6. Risk tolerance: allow optional dependencies like `feedparser`, or keep stdlib-only for v1?

---

## 10. Confirmed Defaults

Confirmed by user on 2026-05-18:

- cadence: manual first;
- source architecture: design for broad compatibility from day one, including Tier 1 plus optional X/YouTube/GitHub/Semantic Scholar style sources;
- execution scope: v1 must actually run and validate Tier 1 first; optional sources should be represented by adapter interfaces/config stubs, not enabled until separately verified;
- language: Chinese guidance summary with original English titles/links;
- storage: markdown docs tracked, raw JSON ignored under `cache/knowledge_scout/`;
- integration: agent context reads `latest_agent_context.md` if present, but does not auto-promote ideas;
- dependencies: stdlib-only first; add `feedparser` only if RSS parsing becomes brittle.

Implementation implication: `sources.py` should use a source adapter registry and a generic `SourceAdapter` protocol so later X/YouTube/GitHub plugins can be added without changing downstream filter/scorer/publisher logic. Initial smoke tests and real CLI verification should remain Tier 1 only.
