import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "../../components/ui/Card";
import { EChartsWrapper } from "../../components/ui/EChartsWrapper";
import { Select } from "../../components/ui/Select";
import { Skeleton } from "../../components/ui/Skeleton";
import { Table, type TableColumn } from "../../components/ui/Table";
import {
  fetchResultDrawdown,
  fetchResultEquityCurve,
  fetchResultMetrics,
  fetchResultTable,
  listBacktestResults,
  type BacktestResultTable,
  type BacktestResultFile,
} from "../../api/backtest";
import type {
  BacktestMetrics,
  DrawdownSeries,
  EquityCurve,
} from "../../api/types";

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

const SUMMARY_COLUMN_ORDER = [
  "topk",
  "n_drop",
  "hold_thresh",
  "market",
  "benchmark",
  "deal_price",
  "information_ratio",
  "sharpe",
  "max_drawdown",
  "annual_return",
  "excess_annual_return",
  "rank_ic",
  "rank_icir",
  "turnover",
];

function metricNumber(metrics: Record<string, unknown>, key: string) {
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function formatMetric(metrics: Record<string, unknown>, key: string, digits = 3) {
  const value = metricNumber(metrics, key);
  return value == null ? "-" : value.toFixed(digits);
}

function formatPercent(metrics: Record<string, unknown>, key: string, digits = 2) {
  const value = metricNumber(metrics, key);
  return value == null ? "-" : `${(value * 100).toFixed(digits)}%`;
}

function formatCell(value: unknown) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value ?? "-");
}

function tableColumns(table: BacktestResultTable): TableColumn<Record<string, unknown>>[] {
  const ordered = [
    ...SUMMARY_COLUMN_ORDER.filter((column) => table.columns.includes(column)),
    ...table.columns.filter((column) => !SUMMARY_COLUMN_ORDER.includes(column)).slice(0, 8),
  ];
  return ordered.map((column) => ({
    key: column,
    label: column,
    sortable: true,
    align:
      column.includes("ratio") ||
      column.includes("sharpe") ||
      column.includes("drawdown") ||
      column.includes("return") ||
      column.includes("ic") ||
      column.includes("turnover")
        ? "right"
        : "left",
    render: (row) => formatCell(row[column]),
  }));
}

function EmptyCurveState({ hasRows }: { hasRows: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-[340px] flex-col items-center justify-center rounded-sm border border-dashed border-terminal-border bg-terminal-surface px-6 text-center">
      <p className="font-mono text-sm font-semibold text-terminal-text">
        {hasRows ? t("console.backtest.summaryOnlyTitle") : t("console.backtest.noCurveData")}
      </p>
      {hasRows && (
        <p className="mt-2 max-w-xl font-mono text-xs leading-5 text-terminal-text-dim">
          {t("console.backtest.summaryOnlyDescription")}
        </p>
      )}
    </div>
  );
}

export function ResultDetail() {
  const { t } = useTranslation();
  const [results, setResults] = useState<BacktestResultFile[]>([]);
  const [selected, setSelected] = useState("");
  const [metrics, setMetrics] = useState<(BacktestMetrics & Record<string, unknown>) | null>(null);
  const [equity, setEquity] = useState<EquityCurve | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownSeries | null>(null);
  const [table, setTable] = useState<BacktestResultTable | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listBacktestResults()
      .then((items) => {
        setResults(items);
        if (items.length > 0) setSelected(items[0].filename);
      })
      .catch(() => setResults([]));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    setMetrics(null);
    setEquity(null);
    setDrawdown(null);
    setTable(null);
    Promise.all([
      fetchResultMetrics(selected).catch(() => ({} as BacktestMetrics & Record<string, unknown>)),
      fetchResultEquityCurve(selected).catch(() => ({ dates: [], portfolio: [], benchmark: [], excess: [] })),
      fetchResultDrawdown(selected).catch(() => ({ dates: [], drawdown: [] })),
      fetchResultTable(selected).catch(() => ({ columns: [], rows: [] })),
    ])
      .then(([nextMetrics, nextEquity, nextDrawdown, nextTable]) => {
        setMetrics(nextMetrics);
        setEquity(nextEquity);
        setDrawdown(nextDrawdown);
        setTable(nextTable);
      })
      .finally(() => setLoading(false));
  }, [selected]);

  const selectedMeta = results.find((result) => result.filename === selected);
  const hasCurve = Boolean(equity?.dates?.length);
  const hasSummaryRows = Boolean(table?.rows?.length);

  const equityOption = useMemo(() => {
    if (!equity?.dates?.length) return null;
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["Portfolio", "Benchmark", "Excess"], textStyle: { color: "#c8ccd0", fontSize: 11 } },
      grid: { left: 60, right: 20, top: 40, bottom: 60 },
      xAxis: { type: "category", data: equity.dates, axisLabel: { color: "#71717a", fontSize: 10, rotate: 30 } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#1e1e22" } } },
      dataZoom: CHART_DATA_ZOOM,
      series: [
        { name: "Portfolio", type: "line", data: equity.portfolio, lineStyle: { color: "#22c55e", width: 2 }, symbol: "none" },
        { name: "Benchmark", type: "line", data: equity.benchmark, lineStyle: { color: "#71717a", width: 1.5 }, symbol: "none" },
        { name: "Excess", type: "line", data: equity.excess, lineStyle: { color: "#38bdf8", width: 1.5, type: "dashed" }, symbol: "none" },
      ],
      title: { text: t("console.backtest.equityCurve"), textStyle: { color: "#c8ccd0", fontSize: 13 } },
    };
  }, [equity, t]);

  const drawdownOption = useMemo(() => {
    if (!drawdown?.dates?.length) return null;
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 60, right: 20, top: 30, bottom: 60 },
      xAxis: { type: "category", data: drawdown.dates, axisLabel: { color: "#71717a", fontSize: 10, rotate: 30 } },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#1e1e22" } },
        axisLabel: { formatter: (value: number) => `${(value * 100).toFixed(1)}%` },
      },
      dataZoom: CHART_DATA_ZOOM,
      series: [
        {
          name: "Drawdown",
          type: "line",
          data: drawdown.drawdown,
          lineStyle: { color: "#ef4444", width: 1.5 },
          areaStyle: { color: "rgba(239,68,68,0.1)" },
          symbol: "none",
        },
      ],
      title: { text: t("console.backtest.drawdown"), textStyle: { color: "#c8ccd0", fontSize: 13 } },
    };
  }, [drawdown, t]);

  const metricItems = metrics
    ? [
        ["IR", formatMetric(metrics, "information_ratio", 4), "text-terminal-green"],
        ["Sharpe", formatMetric(metrics, "sharpe", 3), "text-terminal-text-bright"],
        ["Annual", formatPercent(metrics, "annual_return"), "text-terminal-text-bright"],
        ["Excess Ann.", formatPercent(metrics, "excess_annual_return"), "text-terminal-cyan"],
        ["Max DD", formatPercent(metrics, "max_drawdown"), "text-terminal-red"],
        ["Calmar", formatMetric(metrics, "calmar", 3), "text-terminal-text-bright"],
        ["Rank IC", formatMetric(metrics, "rank_ic", 4), "text-terminal-text-bright"],
        ["Turnover", formatPercent(metrics, "turnover", 1), "text-terminal-text-bright"],
      ]
    : [];

  const summaryColumns = table ? tableColumns(table) : [];

  return (
    <div className="space-y-4">
      <Card title={t("console.backtest.detailTitle")}>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
          <Select
            options={results.map((result) => ({ value: result.filename, label: result.filename }))}
            value={selected}
            onChange={setSelected}
            searchable
          />
          {selectedMeta && (
            <div className="grid grid-cols-2 gap-3 font-mono text-xs text-terminal-text-dim md:grid-cols-3">
              <span>{selectedMeta.size_kb} KB</span>
              <span>{new Date(selectedMeta.modified).toLocaleString()}</span>
              <span>{hasCurve ? t("console.backtest.curveReady") : t("console.backtest.summaryOnly")}</span>
            </div>
          )}
        </div>
      </Card>
      {loading && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      )}
      {!loading && selected && metrics && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            {metricItems.map(([label, value, colorClass]) => (
              <div key={label} className="rounded-sm border border-terminal-border bg-terminal-raised px-3 py-2">
                <p className="font-mono text-xs uppercase text-terminal-text-dim">{label}</p>
                <p className={`font-mono text-sm font-semibold ${colorClass}`}>{value}</p>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {equityOption ? (
              <EChartsWrapper option={equityOption} height={340} />
            ) : (
              <EmptyCurveState hasRows={hasSummaryRows} />
            )}
            {drawdownOption ? (
              <EChartsWrapper option={drawdownOption} height={340} />
            ) : (
              <EmptyCurveState hasRows={hasSummaryRows} />
            )}
          </div>
          {table && table.rows.length > 0 && (
            <Card title={hasCurve ? t("console.backtest.resultRows") : t("console.backtest.parameterMetricTable")}>
              <Table
                data={table.rows}
                pageSize={12}
                columns={summaryColumns}
                emptyMessage={t("console.backtest.noResults")}
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
