import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog, DryRunPreview } from "../../components/console";
import { Card } from "../../components/ui/Card";
import { EChartsWrapper } from "../../components/ui/EChartsWrapper";
import { Table } from "../../components/ui/Table";
import { TaskStatus } from "../../components/ui/TaskStatus";
import {
  fetchCompareRuns,
  listBacktestResults,
  triggerCompare,
  type BacktestPreview,
  type BacktestResultFile,
} from "../../api/backtest";
import type { BacktestMetrics, CompareRun } from "../../api/types";
import { useDryRunPreview } from "../../hooks/useDryRunPreview";
import type { CompareParams } from "../../schemas/backtest";

const CHART_DATA_ZOOM = [
  { type: "inside" as const },
  {
    type: "slider" as const,
    bottom: 10,
    height: 16,
    borderColor: "#27272a",
    fillerColor: "rgba(34,197,94,0.15)",
    handleStyle: { color: "#22c55e" },
  },
];

function metricValue(metrics: BacktestMetrics | Record<string, unknown>, key: string) {
  const value = (metrics as Record<string, unknown>)[key];
  return typeof value === "number" ? value : undefined;
}

function formatNumber(value: number | undefined, digits = 3) {
  return value == null ? "-" : value.toFixed(digits);
}

export function CompareConsole() {
  const { t } = useTranslation();
  const [results, setResults] = useState<BacktestResultFile[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [runs, setRuns] = useState<CompareRun[]>([]);
  const [loadingCharts, setLoadingCharts] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const preview = useDryRunPreview<CompareParams, BacktestPreview>(triggerCompare);

  useEffect(() => {
    listBacktestResults()
      .then(setResults)
      .catch(() => setResults([]));
  }, []);

  const toggle = (filename: string) => {
    setSelected((current) => {
      if (current.includes(filename)) {
        return current.filter((item) => item !== filename);
      }
      if (current.length >= 5) return current;
      return [...current, filename];
    });
  };

  const loadCharts = async () => {
    if (selected.length < 2) return;
    setLoadingCharts(true);
    try {
      setRuns(await fetchCompareRuns(selected));
    } catch {
      setRuns([]);
    } finally {
      setLoadingCharts(false);
    }
  };

  const submit = async () => {
    if (selected.length < 2) return;
    const params = { result_files: selected, dry_run: dryRun };
    if (dryRun) {
      await preview.run(params);
      await loadCharts();
      return;
    }
    setConfirmOpen(true);
  };

  const equityOption = useMemo(() => {
    const runWithDates = runs.find((run) => run.equity_curve?.dates?.length);
    if (!runWithDates) return null;
    return {
      tooltip: { trigger: "axis" },
      legend: { data: runs.map((run) => run.label), textStyle: { color: "#c8ccd0", fontSize: 11 } },
      grid: { left: 60, right: 20, top: 40, bottom: 60 },
      xAxis: {
        type: "category",
        data: runWithDates.equity_curve.dates,
        axisLabel: { color: "#71717a", fontSize: 10, rotate: 30 },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#1e1e22" } } },
      dataZoom: CHART_DATA_ZOOM,
      series: runs.map((run) => ({
        name: run.label,
        type: "line",
        data: run.equity_curve.portfolio,
        lineStyle: { color: run.color, width: 2 },
        symbol: "none",
      })),
      title: { text: t("console.backtest.equityComparison"), textStyle: { color: "#c8ccd0", fontSize: 13 } },
    };
  }, [runs, t]);

  const drawdownOption = useMemo(() => {
    const runWithDates = runs.find((run) => run.drawdown?.dates?.length);
    if (!runWithDates) return null;
    return {
      tooltip: { trigger: "axis" },
      legend: { data: runs.map((run) => run.label), textStyle: { color: "#c8ccd0", fontSize: 11 } },
      grid: { left: 60, right: 20, top: 40, bottom: 60 },
      xAxis: {
        type: "category",
        data: runWithDates.drawdown.dates,
        axisLabel: { color: "#71717a", fontSize: 10, rotate: 30 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#1e1e22" } },
        axisLabel: { formatter: (value: number) => `${(value * 100).toFixed(1)}%` },
      },
      dataZoom: CHART_DATA_ZOOM,
      series: runs.map((run) => ({
        name: run.label,
        type: "line",
        data: run.drawdown.drawdown,
        lineStyle: { color: run.color, width: 1.5 },
        areaStyle: { color: run.color, opacity: 0.08 },
        symbol: "none",
      })),
      title: { text: t("console.backtest.drawdownComparison"), textStyle: { color: "#c8ccd0", fontSize: 13 } },
    };
  }, [runs, t]);

  return (
    <Card title={t("console.backtest.compareTitle")}>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {results.length === 0 && (
            <span className="font-mono text-xs text-terminal-text-dim">
              {t("console.backtest.noResults")}
            </span>
          )}
          {results.map((result) => {
            const active = selected.includes(result.filename);
            return (
              <button
                key={result.filename}
                type="button"
                onClick={() => toggle(result.filename)}
                className={`rounded-sm border px-3 py-1.5 text-left font-mono text-xs transition-colors ${
                  active
                    ? "border-terminal-green bg-terminal-green-glow text-terminal-green"
                    : "border-terminal-border text-terminal-text-dim hover:border-terminal-text-dim"
                }`}
              >
                {result.filename}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-terminal-text">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(event) => setDryRun(event.target.checked)}
              className="accent-terminal-green"
            />
            {t("console.common.dryRun")}
          </label>
          <span>
            {selected.length} / 5 {t("console.backtest.selected")}
          </span>
          <button
            type="button"
            onClick={submit}
            disabled={selected.length < 2 || selected.length > 5}
            className="rounded-sm border border-terminal-green px-3 py-1.5 text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
          >
            {dryRun ? t("console.backtest.previewCompare") : t("console.backtest.runCompare")}
          </button>
          <button
            type="button"
            onClick={loadCharts}
            disabled={selected.length < 2 || loadingCharts}
            className="rounded-sm border border-terminal-border px-3 py-1.5 text-terminal-text transition-colors hover:border-terminal-text-dim disabled:opacity-30"
          >
            {loadingCharts ? t("common.loading") : t("console.backtest.renderCompare")}
          </button>
        </div>
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => (
            <pre className="overflow-auto text-xs leading-5">
              {JSON.stringify(value, null, 2)}
            </pre>
          )}
        />
        {runs.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {equityOption && <EChartsWrapper option={equityOption} height={340} />}
              {drawdownOption && <EChartsWrapper option={drawdownOption} height={340} />}
            </div>
            <Table
              data={runs as unknown as Record<string, unknown>[]}
              pageSize={5}
              columns={[
                {
                  key: "label",
                  label: t("console.backtest.file"),
                  render: (row) => {
                    const run = row as unknown as CompareRun;
                    return (
                      <span className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: run.color }}
                        />
                        {run.label}
                      </span>
                    );
                  },
                },
                {
                  key: "information_ratio",
                  label: "IR",
                  render: (row) =>
                    formatNumber(metricValue((row as unknown as CompareRun).metrics, "information_ratio")),
                },
                {
                  key: "sharpe",
                  label: "Sharpe",
                  render: (row) => formatNumber(metricValue((row as unknown as CompareRun).metrics, "sharpe")),
                },
                {
                  key: "max_drawdown",
                  label: "Max DD",
                  render: (row) => {
                    const value = metricValue((row as unknown as CompareRun).metrics, "max_drawdown");
                    return value == null ? "-" : `${(value * 100).toFixed(2)}%`;
                  },
                },
              ]}
            />
          </>
        )}
        <TaskStatus taskId={taskId} />
      </div>
      <ConfirmDialog
        open={confirmOpen}
        titleKey="console.backtest.confirmCompare"
        impactSummary={<div>{selected.join(", ")}</div>}
        confirmLabelKey="console.backtest.runCompare"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          const result = await triggerCompare({ result_files: selected, dry_run: false });
          setTaskId(result.task_id);
          setConfirmOpen(false);
        }}
      />
    </Card>
  );
}
