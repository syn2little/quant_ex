# quant_ex Web Frontend

React 19 + Vite + TypeScript + Tailwind CSS frontend for the local quant_ex dashboard.

## Pages

- Dashboard: system overview and runtime status
- Data Management: cache status, external data fetches, stock lookup
- Models: model training, model list, meta and feature importance
- Backtest: grid search, walk-forward validation, result browsing
- Signals: daily signal generation, rebalance simulation, notification tests
- Factors: factor registry, evaluation, factor mining
- Config: YAML config editor and strategy candidates
- Agent Runs: create/browse strategy-iteration agent runs, choose sequential or meeting discussion mode, cap meeting rounds and roles per round, generate optional Codex task proposals, inspect plans/traces/commands/agent tasks/feedback, regenerate approval templates
- System: logs, tasks, runtime information

## API Pattern

Use `src/api/client.ts` for `get` / `post` / `put` / `del`. Long-running backend jobs should return a task id and stream status through `src/hooks/useSSE.ts`.

The Agent Runs page talks to `/api/agents`:

- `GET /api/agents/runs`
- `GET /api/agents/runs/{run_id}`
- `POST /api/agents/runs`
- `POST /api/agents/runs/{run_id}/approval-template`
- `POST /api/agents/runs/{run_id}/execute-safe`
- `POST /api/agents/runs/{run_id}/execute-approved`
- `POST /api/agents/runs/{run_id}/feedback/{command_id}`

The dashboard can execute selected safe-local commands and selected approved commands. Training, backtest, WFV, data fetch/update, notifications, and trading-like actions remain approval-gated through command hashes and approval entries.

## Development

```bash
npm install
npm run dev
```

The Vite dev server proxies `/api` to the FastAPI backend on `:8000`.

Build:

```bash
npm run build
```

Production build output goes to `web/frontend/dist/` and is served by `web/run_web.py`.
