# Knowledge Scout

This directory stores research-only external knowledge outputs for `quant_ex`.

The scout collects strategy, model, and quant research ideas from public sources and turns them into guidance docs. It must not be used to ingest market/fundamental data or to promote strategies without local validation.

## Outputs

- `briefs/`: weekly or manual scout summaries.
- `ideas/`: one markdown card per selected idea.
- `latest_agent_context.md`: compact context for agent strategy iteration.

## Guardrails

- External ideas are hypotheses, not alpha evidence.
- Local validation still requires control arms, costs/slippage, rank metric, WFV, attribution, and human approval.
- Raw fetched metadata belongs in ignored `cache/knowledge_scout/`.
