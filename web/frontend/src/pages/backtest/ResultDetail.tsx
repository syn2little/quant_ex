import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "../../components/ui/Card";
import { EChartsWrapper } from "../../components/ui/EChartsWrapper";
import { Select } from "../../components/ui/Select";
import { Skeleton } from "../../components/ui/Skeleton";
import {
  fetchResultDrawdown,
  fetchResultEquityCurve,
  fetchResultMetrics,
  listBacktestResults,
  type BacktestResultFile,
} from "../../api/backtest";
import type { BacktestMetrics, DrawdownSeries, EquityCurve } from "../../api/types";

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

function metricNumber(metrics: Record<string, unknown>, key: string) {
  const value = metrics[key];
  return typeof value === "number" ? value : undefined;
}

function formatMetric(metrics: Record<string, unknown>, key: string, digits = 3) {
  const value = metricNumber(metrics, key);
  return value == null ? "-" : value.toFixed(digits);
}

export function ResultDetail() {
  const { t } = useTranslation();
  const [results, setResults] = useState<BacktestResultFile[]>([]);
  const [selected, setSelected] = useState("");
  const [metrics, setMetrics] = useState<(BacktestMetrics & Record<string, unknown>) | null>(null);
  const [equity, setEquity] = useState<EquityCurve | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownSeries | null>(null);
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
    Promise.all([
      fetchResultMetrics(selected).catch(() => ({} as BacktestMetrics & Record<string, unknown>)),
      fetchResultEquityCurve(selected).catch(() => ({ dates: [], portfolio: [], benchmark: [], excess: [] })),
      fetchResultDrawdown(selected).catch(() => ({ dates: [], drawdown: [] })),
    ])
      .then(([nextMetrics, nextEquity, nextDrawdown]) => {
        setMetrics(nextMetrics);
        setEquity(nextEquity);
        setDrawdown(nextDrawdown);
      })
      .finally(() => setLoading(false));
  }, [selected]);

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
        ["IR", formatMetric(metrics, "information_ratio", 4)],
        ["Sharpe", formatMetric(metrics, "sharpe", 3)],
        ["Max DD", metricNumber(metrics, "max_drawdown") == null ? "-" : `${(metricNumber(metrics, "max_drawdown")! * 100).toFixed(2)}%`],
        ["Calmar", formatMetric(metrics, "calmar", 3)],
        ["Rank IC", formatMetric(metrics, "rank_ic", 4)],
        ["Rank ICIR", formatMetric(metrics, "rank_icir", 3)],
        ["Win Rate", metricNumber(metrics, "win_rate") == null ? "-" : `${(metricNumber(metrics, "win_rate")! * 100).toFixed(1)}%`],
        ["Turnover", metricNumber(metrics, "turnover") == null ? "-" : `${(metricNumber(metrics, "turnover")! * 100).toFixed(1)}%`],
      ]
    : [];

  return (
    <div className="space-y-4">
      <Card title={t("console.backtest.detailTitle")}>
        <div className="max-w-xl">
          <Select
            options={results.map((result) => ({ value: result.filename, label: result.filename }))}
            value={selected}
            onChange={setSelected}
            searchable
          />
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
            {metricItems.map(([label, value]) => (
              <div key={label} className="rounded-sm border border-terminal-border bg-terminal-raised px-3 py-2">
                <p className="font-mono text-xs uppercase text-terminal-text-dim">{label}</p>
                <p className="font-mono text-sm font-semibold text-terminal-text-bright">{value}</p>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {equityOption ? (
              <EChartsWrapper option={equityOption} height={340} />
            ) : (
              <Card title={t("console.backtest.equityCurve")}>
                <p className="py-8 text-center font-mono text-xs text-terminal-text-dim">
                  {t("console.backtest.noCurveData")}
                </p>
              </Card>
            )}
            {drawdownOption ? (
              <EChartsWrapper option={drawdownOption} height={340} />
            ) : (
              <Card title={t("console.backtest.drawdown")}>
                <p className="py-8 text-center font-mono text-xs text-terminal-text-dim">
                  {t("console.backtest.noCurveData")}
                </p>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}
