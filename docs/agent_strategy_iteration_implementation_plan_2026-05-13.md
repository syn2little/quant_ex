# Agent Strategy Iteration Implementation Plan

Date: 2026-05-13

## Goal

Integrate the agent strategy iteration design into `quant_ex` in controlled phases, starting with an offline and auditable planning layer that does not bypass the existing validation stack.

## Phase 1

Objective:
- Establish the research-planning substrate.

Deliverables:
- role and plan schemas
- prompt catalog in-repo
- local context pack builder
- append-only agent memory log
- optional OpenAI-compatible client, disabled by default
- `run_agent_strategy_iteration.py`
- per-run bundle under `docs/strategy_log/agent_runs/`
- focused tests

Exit criteria:
- offline CLI run writes `run.json`, `plan.md`, `context.json`, and `prompts.json`
- no network access required in default mode
- no secrets written to disk

## Phase 2

Objective:
- Make prompts and role execution stronger without coupling to expensive runs.

Deliverables:
- richer context pack slices for result CSVs and config diffs
- role-specific JSON schema validation
- better bull/bear/risk carry-over between roles
- prompt regression fixtures

Exit criteria:
- stable prompt outputs across repeated offline runs
- structured LLM mode degrades cleanly when env vars are absent

## Phase 3

Objective:
- Add evaluation feedback and memory reflection.

Deliverables:
- parse same-model backtest CSVs and WFV summaries into feedback objects
- append delayed reflections to agent memory
- seed the next run from prior validated outcomes

Exit criteria:
- a completed planning run can be updated with validated outcomes
- memory remains separate from durable strategy logs

## Phase 4

Objective:
- Add semi-automated execution adapters behind approval gates.

Deliverables:
- command generation and optional execution wrappers
- dry-run-only support by default
- approval tagging for WFV, qlib updates, data fetches, and notifications

Exit criteria:
- cheap validations can be executed safely from the agent layer
- expensive actions require explicit user intent

## Phase 5

Objective:
- Integrate with the dashboard and long-term research workflow.

Deliverables:
- API endpoints to create and browse agent runs
- Web Dashboard surfaces for prompts, context, decisions, and memory
- links from agent runs to strategy/system iteration logs

Exit criteria:
- planning runs are visible and traceable from the existing research UI

## Phase 6

Objective:
- Add an optional meeting-style discussion mode without removing the legacy sequential role runner.

Deliverables:
- `discussion_mode=sequential|meeting` in CLI, Web API, and Agent Runs create UI
- virtual chair decisions that select the next useful role or end the meeting
- configurable `meeting_max_rounds` and `meeting_max_roles_per_round` limits at run creation time
- `discussion_trace.json` / `discussion_trace.md` artifacts per run
- default offline fallback agenda for reproducible tests and no-LLM smoke runs

Exit criteria:
- `sequential` remains the default compatible behavior
- `meeting` records why each role participated, which roles were called in each round, and when the chair considered the discussion complete
- LLM mode lets the chair choose role participation dynamically, while no-LLM mode stays deterministic

## Phase 7

Objective:
- Add a reserved local coding-agent execution layer on top of LLM discussion and approval gates.

Deliverables:
- `--use-agent` CLI option that writes `agent_tasks.json` / `agent_tasks.md`
- `agent_approval_template.yaml` with task prompt hashes and explicit approvals
- Codex CLI provider support through `codex exec`
- `readonly`, `patch`, and reserved `danger-full-access` modes
- isolated git worktree execution for `patch` mode
- Web Agent Runs create options to generate Codex task proposals

Exit criteria:
- agent tasks are proposal-only unless an approval file matches task id and prompt hash
- `danger-full-access` is available only as an explicitly selected high-risk mode and carries a warning
- generated artifacts are browsable from Agent Runs, while execution remains approval-gated

## Current Execution Choice

Phase 1 through Phase 7 have been implemented. The current agent layer can build offline plans, parse feedback CSVs, produce gated command proposals with `commands.json` / `commands.md`, write `approval_template.yaml`, execute only explicitly approved commands whose `command_id` and `command_sha256` match the current plan, summarize execution in `execution_summary.md`, detect backtest/WFV CSV candidates for Phase 3 feedback handoff, expose run artifacts in the Web Dashboard, optionally run in `meeting` mode where a virtual chair chooses which roles should participate, and generate local Codex task proposals through `--use-agent`. `--execute-safe` remains limited to local low-risk checks; training, backtest, WFV, data fetch/update, notifications, trading-like commands, and coding-agent tasks require explicit approval before execution.

## Full-Cycle Validation

Run `full_agent_train_backtest_20260513` validated the complete path from real LLM role discussion to training, backtest, and feedback:

- Run bundle: `docs/strategy_log/agent_runs/full_agent_train_backtest_20260513/`
- Role traces: 12 roles, all real LLM calls, with quick/deep model tiers recorded in `role_traces.json` / `role_traces.md`
- Strict training config: `docs/strategy_log/agent_runs/full_agent_train_backtest_20260513/train_csi1000_eval_csi300.yaml`
- Strict model: `models/lgbm_agent_full_iter_csi1000_20260513_20260513_210545.pkl`
- Result CSV: `backtest_results/agent_runs/full_agent_train_backtest_20260513_csi1000_model_csi300_eval.csv`
- Feedback: `docs/strategy_log/agent_runs/full_agent_train_backtest_20260513/feedback.md`

Strict csi1000-trained result on csi300 evaluation:

- Sharpe: `1.2490`
- Information ratio: `0.5774`
- Annual return: `27.45%`
- Max drawdown: `-20.86%`
- Rank IC: `0.0521`

Compared with `backtest_results/ablation/fundamental_control_15_3_8_20260511.csv`, the strict candidate underperformed on Sharpe and IR. The feedback decision is `reject` with `refuted` hypothesis evaluation. This run proves the agent workflow is operational, but it is not a promoted strategy candidate and should not be escalated to WFV without a new hypothesis.

Operational note: an earlier diagnostic command in the same run used `config/daily_csi1000.yaml`, whose current `market.name` resolves to `csi300`. That diagnostic result is recorded as superseded in `full_cycle_summary.md`; strict csi1000 research should use an explicit override and verify the model `_meta.json`.

## LLM Tier Configuration

Agent role model assignment is configured in `config/agent_strategy_iteration.yaml`.

- Each role uses `model_tier`, currently `quick` or `deep`.
- Tier definitions live under `llm.tiers`.
- The local real config can directly store `api_key` and `base_url`; this file is gitignored. The committed example keeps `api_key` empty.
- `api_key_env` / `base_url_env` are still accepted as optional fallback fields for environment-driven setups.
- Tier-specific environment variables such as `QUANT_EX_AGENT_DEEP_MODEL` and `QUANT_EX_AGENT_QUICK_MODEL` can override the model names without changing the YAML.

Current default mapping:

```yaml
llm:
  api_key: ""
  base_url: "https://your-openai-compatible-endpoint.example"
  tiers:
    quick:
      model: "gpt-5.4-mini"
      reasoning_effort: "low"
      temperature: 0.1
      max_tokens: 1200
    deep:
      model: "gpt-5.5"
      reasoning_effort: "high"
      temperature: 0.2
      max_tokens: 2400
```
