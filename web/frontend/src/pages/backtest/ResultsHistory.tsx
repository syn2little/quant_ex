import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "../../components/ui/Card";
import { Table } from "../../components/ui/Table";
import { useTaskTracking } from "../../hooks/useTaskTracking";
import {
  fetchResultMetrics,
  listBacktestResults,
  type BacktestResultFile,
} from "../../api/backtest";
import type { TaskState } from "../../api/types";

type HistoryRow = Record<string, unknown> & {
  filename: string;
  market: string;
  model: string;
  information_ratio: number | null;
  sharpe: number | null;
  annual_return: number | null;
  excess_annual_return: number | null;
  max_drawdown: number | null;
  deal_price: string;
  status: string;
  task_id: string;
  modified: string;
};

const TASK_FILTER = [
  "grid_search",
  "wfv",
  "compare",
  "grid_search_dry_run",
  "wfv_dry_run",
  "compare_dry_run",
];

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function taskForFile(tasks: TaskState[], file: BacktestResultFile): TaskState | undefined {
  return tasks.find((task) =>
    task.result_paths?.some((path) => path.endsWith(file.filename)),
  );
}

export function ResultsHistory() {
  const { t } = useTranslation();
  const { tasks } = useTaskTracking({ pageKey: "backtest", taskTypeFilter: TASK_FILTER });
  const [results, setResults] = useState<BacktestResultFile[]>([]);
  const [rows, setRows] = useState<HistoryRow[]>([]);

  useEffect(() => {
    listBacktestResults()
      .then(setResults)
      .catch(() => setResults([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      results.map(async (result) => {
        const metrics: Record<string, unknown> = await fetchResultMetrics(result.filename).catch(() => ({}));
        const task = taskForFile(tasks, result);
        return {
          filename: result.filename,
          market: String(metrics.market ?? "-"),
          model: String(metrics.model ?? metrics.model_path ?? "-"),
          information_ratio: asNumber(metrics.information_ratio ?? metrics.ir),
          sharpe: asNumber(metrics.sharpe),
          annual_return: asNumber(metrics.annual_return),
          excess_annual_return: asNumber(metrics.excess_annual_return),
          max_drawdown: asNumber(metrics.max_drawdown),
          deal_price: String(metrics.deal_price ?? "-"),
          status: task?.status ?? "-",
          task_id: task?.task_id ?? "-",
          modified: result.modified,
        };
      }),
    ).then((nextRows) => {
      if (cancelled) return;
      setRows(
        nextRows.sort((a, b) => {
          const ai = a.information_ratio ?? Number.NEGATIVE_INFINITY;
          const bi = b.information_ratio ?? Number.NEGATIVE_INFINITY;
          return bi - ai;
        }),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [results, tasks]);

  const taskRows = useMemo(
    () =>
      tasks.slice(0, 8).map((task) => ({
        task_id: task.task_id,
        task_type: task.task_type,
        status: task.status,
        action_key: task.action_key ?? "-",
        created_at: task.created_at,
      })),
    [tasks],
  );

  return (
    <div className="space-y-4">
      <Card title={t("console.backtest.historyTitle")}>
        <p className="mb-3 font-mono text-xs text-terminal-text-dim">
          {t("console.backtest.historyIrNote")}
        </p>
        <Table
          data={rows}
          pageSize={12}
          rowKey="filename"
          emptyMessage={t("console.backtest.noResults")}
          columns={[
            { key: "filename", label: t("console.backtest.file"), sortable: true },
            { key: "market", label: t("console.backtest.market") },
            { key: "model", label: t("console.backtest.model") },
            {
              key: "information_ratio",
              label: "IR",
              align: "right",
              render: (row) =>
                row.information_ratio == null ? "-" : row.information_ratio.toFixed(4),
            },
            {
              key: "sharpe",
              label: "Sharpe",
              align: "right",
              render: (row) => (row.sharpe == null ? "-" : row.sharpe.toFixed(4)),
            },
            {
              key: "annual_return",
              label: t("console.backtest.annualReturn"),
              align: "right",
              render: (row) =>
                row.annual_return == null ? "-" : `${(row.annual_return * 100).toFixed(2)}%`,
            },
            {
              key: "excess_annual_return",
              label: t("console.backtest.excessAnnualReturn"),
              align: "right",
              render: (row) =>
                row.excess_annual_return == null
                  ? "-"
                  : `${(row.excess_annual_return * 100).toFixed(2)}%`,
            },
            {
              key: "max_drawdown",
              label: "Max DD",
              align: "right",
              render: (row) =>
                row.max_drawdown == null ? "-" : `${(row.max_drawdown * 100).toFixed(2)}%`,
            },
            { key: "deal_price", label: t("console.backtest.dealPrice") },
            { key: "status", label: t("console.backtest.status") },
            { key: "task_id", label: "task_id" },
          ]}
        />
      </Card>
      <Card title={t("console.backtest.recentTasks")}>
        <Table
          data={taskRows}
          pageSize={8}
          rowKey="task_id"
          emptyMessage={t("console.tasks.empty")}
          columns={[
            { key: "task_id", label: "task_id" },
            { key: "task_type", label: "type" },
            { key: "status", label: t("console.backtest.status") },
            { key: "action_key", label: "action" },
            { key: "created_at", label: "created" },
          ]}
        />
      </Card>
    </div>
  );
}
