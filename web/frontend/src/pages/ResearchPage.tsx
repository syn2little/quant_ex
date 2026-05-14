import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Activity, GitCompare, Library, Pickaxe, TrendingUp } from "lucide-react";
import { Card } from "../components/ui/Card";
import { Tabs } from "../components/ui/Tabs";
import { Badge } from "../components/ui/Badge";
import { Table } from "../components/ui/Table";
import { Select } from "../components/ui/Select";
import { MultiSelect } from "../components/ui/MultiSelect";
import { DatePicker } from "../components/ui/DatePicker";
import { NumberInput } from "../components/ui/NumberInput";
import { TaskStatus } from "../components/ui/TaskStatus";
import { EChartsWrapper } from "../components/ui/EChartsWrapper";
import { Skeleton, SkeletonTable } from "../components/ui/Skeleton";
import { get, post, fetchICAnalysis, fetchFactorHeatmap } from "../api/client";
import type { ICDAnalysis, FactorHeatmap } from "../api/types";

const RESEARCH_TABS = [
  { key: "library", label: "Library" },
  { key: "icAnalysis", label: "Evaluation Flow" },
  { key: "heatmap", label: "Correlation" },
  { key: "mining", label: "Mining" },
];

interface FactorLibEntry {
  name: string;
  class_name: string;
  enabled: boolean;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex min-h-56 items-center justify-center rounded-sm border border-dashed border-terminal-border-dim bg-terminal-raised/40 px-6 text-center">
      <div>
        <p className="font-mono text-sm uppercase tracking-wider text-terminal-text">{title}</p>
        <p className="mt-2 max-w-xl text-sm text-terminal-text-dim">{detail}</p>
      </div>
    </div>
  );
}

function ResearchHeader() {
  const { t } = useTranslation();
  return (
    <Card accent="cyan">
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <p className="font-mono text-xs uppercase tracking-wider text-terminal-cyan">{t("research.factorDecisionLab")}</p>
          <h1 className="mt-2 text-lg font-semibold text-terminal-text-bright">{t("research.title")}</h1>
          <p className="mt-2 text-sm text-terminal-text-dim">{t("research.purpose")}</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {[
            { icon: Library, label: t("research.flowLibrary"), text: t("research.flowLibraryText") },
            { icon: Activity, label: t("research.flowValidate"), text: t("research.flowValidateText") },
            { icon: TrendingUp, label: t("research.flowPromote"), text: t("research.flowPromoteText") },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="rounded-sm border border-terminal-border-dim bg-terminal-raised p-3">
                <Icon className="mb-2 h-4 w-4 text-terminal-green" />
                <p className="font-mono text-xs uppercase tracking-wider text-terminal-text">{item.label}</p>
                <p className="mt-1 text-xs text-terminal-text-dim">{item.text}</p>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function metricTone(value: number | undefined, good: number) {
  if (value == null) return "text-terminal-text-dim";
  if (Math.abs(value) >= good) return "text-terminal-green";
  if (Math.abs(value) >= good / 2) return "text-terminal-amber";
  return "text-terminal-text-dim";
}

function LibraryTab() {
  const { t } = useTranslation();
  const [factors, setFactors] = useState<FactorLibEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    get<FactorLibEntry[]>("/factors/library")
      .then(setFactors)
      .catch(() => setFactors([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <SkeletonTable rows={8} />;

  const enabledCount = factors.filter((factor) => factor.enabled).length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Card title={t("research.registeredFactors")} accent="green">
          <p className="font-mono text-3xl text-terminal-text-bright">{factors.length}</p>
        </Card>
        <Card title={t("research.enabledFactors")} accent="cyan">
          <p className="font-mono text-3xl text-terminal-text-bright">{enabledCount}</p>
        </Card>
        <Card title={t("research.libraryUse")}>
          <p className="text-sm text-terminal-text-dim">{t("research.libraryUseText")}</p>
        </Card>
      </div>
      <Card title={t("research.factorLibrary")}>
        <Table
          columns={[
            { key: "name", label: t("research.name"), sortable: true },
            { key: "class_name", label: t("research.className"), sortable: true },
            {
              key: "enabled",
              label: t("research.status"),
              render: (row) => (
                <Badge variant={row.enabled ? "success" : "neutral"}>
                  {row.enabled ? t("research.enabled") : t("research.disabled")}
                </Badge>
              ),
            },
          ]}
          data={factors as unknown as Record<string, unknown>[]}
          pageSize={20}
          emptyMessage={t("research.noFactors")}
        />
      </Card>
    </div>
  );
}

function ICAnalysisTab() {
  const { t } = useTranslation();
  const [factorList, setFactorList] = useState<{ value: string; label: string }[]>([]);
  const [selectedFactor, setSelectedFactor] = useState("");
  const [horizon, setHorizon] = useState(5);
  const [window, setWindow] = useState(20);
  const [result, setResult] = useState<ICDAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    get<{ name: string }[]>("/factors")
      .then((factors) => setFactorList(factors.map((f) => ({ value: f.name, label: f.name }))))
      .catch(() => setFactorList([]));
  }, []);

  const analyze = () => {
    if (!selectedFactor) return;
    setLoading(true);
    fetchICAnalysis({ factor: selectedFactor, horizon, window })
      .then(setResult)
      .catch(() => setResult(null))
      .finally(() => setLoading(false));
  };

  const rollingMean = useMemo(() => {
    if (!result?.rolling.length) return undefined;
    return result.rolling.reduce((sum, row) => sum + row.ic, 0) / result.rolling.length;
  }, [result]);

  const decayChartOption = result && result.decay.length > 0 ? {
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 20, top: 30, bottom: 40 },
    xAxis: { type: "category", data: result.decay.map((d) => `${d.horizon}d`), axisLine: { lineStyle: { color: "#27272a" } }, axisLabel: { color: "#71717a" } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#1e1e22" } }, axisLabel: { color: "#71717a" } },
    series: [{
      type: "line",
      data: result.decay.map((d) => d.ic),
      smooth: true,
      lineStyle: { color: "#22c55e", width: 2 },
      areaStyle: { color: "rgba(34,197,94,0.1)" },
      itemStyle: { color: "#22c55e" },
    }],
    title: { text: t("research.icDecay"), textStyle: { color: "#71717a", fontSize: 13 } },
  } : undefined;

  const rollingChartOption = result && result.rolling.length > 0 ? {
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 20, top: 30, bottom: 50 },
    xAxis: { type: "category", data: result.rolling.map((r) => r.date), axisLine: { lineStyle: { color: "#27272a" } }, axisLabel: { color: "#71717a", fontSize: 10, rotate: 30 } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#1e1e22" } }, axisLabel: { color: "#71717a" } },
    dataZoom: [{ type: "inside" }, { type: "slider", bottom: 10, height: 16 }],
    series: [{
      type: "line",
      data: result.rolling.map((r) => r.ic),
      lineStyle: { color: "#22c55e", width: 1.5 },
      symbol: "none",
    }],
    title: { text: t("research.rollingIC"), textStyle: { color: "#71717a", fontSize: 13 } },
  } : undefined;

  return (
    <div className="space-y-4">
      <Card title={t("research.evaluationFlow")} accent="green">
        <div className="grid gap-3 md:grid-cols-4">
          {[
            t("research.stepChoose"),
            t("research.stepMeasure"),
            t("research.stepStability"),
            t("research.stepDecision"),
          ].map((step, index) => (
            <div key={step} className="rounded-sm border border-terminal-border-dim bg-terminal-raised p-3">
              <p className="font-mono text-xs text-terminal-green">0{index + 1}</p>
              <p className="mt-1 text-sm text-terminal-text">{step}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title={t("research.runEvaluation")}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-56">
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.selectFactor")}</p>
            <Select options={factorList} value={selectedFactor} onChange={setSelectedFactor} searchable />
          </div>
          <div>
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.horizon")}</p>
            <NumberInput value={horizon} onChange={(v) => setHorizon(v ?? 5)} min={1} max={60} />
          </div>
          <div>
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.window")}</p>
            <NumberInput value={window} onChange={(v) => setWindow(v ?? 20)} min={5} max={120} />
          </div>
          <button
            onClick={analyze}
            disabled={!selectedFactor}
            className="rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
          >
            {t("research.analyze")}
          </button>
        </div>
      </Card>

      {loading && <Skeleton className="h-[320px] w-full" />}

      {!loading && !result && (
        <EmptyState title={t("research.noEvaluation")} detail={t("research.noEvaluationDetail")} />
      )}

      {result && (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Card title={t("research.meanIC")} accent="green">
              <p className={`font-mono text-2xl font-bold ${metricTone(result.ic_mean, 0.03)}`}>{result.ic_mean}</p>
            </Card>
            <Card title={t("research.rankIC")} accent="cyan">
              <p className="font-mono text-2xl font-bold text-terminal-text-dim">-</p>
            </Card>
            <Card title={t("research.icir")} accent="cyan">
              <p className={`font-mono text-2xl font-bold ${metricTone(result.icir, 0.4)}`}>{result.icir}</p>
            </Card>
            <Card title={t("research.coverage")} accent="amber">
              <p className="font-mono text-2xl font-bold text-terminal-text-dim">-</p>
              <p className="mt-1 text-xs text-terminal-text-dim">{t("research.coveragePending")}</p>
            </Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t("research.icDecay")}>
              {decayChartOption ? <EChartsWrapper option={decayChartOption} height={280} /> : (
                <EmptyState title={t("research.noDecay")} detail={t("research.noDecayDetail")} />
              )}
            </Card>
            <Card title={t("research.rollingIC")}>
              {rollingChartOption ? <EChartsWrapper option={rollingChartOption} height={280} /> : (
                <EmptyState title={t("research.noRolling")} detail={t("research.noRollingDetail")} />
              )}
              {rollingMean != null && (
                <p className="mt-2 text-xs text-terminal-text-dim">{t("research.rollingMean")}: {rollingMean.toFixed(4)}</p>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function HeatmapTab() {
  const { t } = useTranslation();
  const [factorList, setFactorList] = useState<{ value: string; label: string }[]>([]);
  const [selectedFactors, setSelectedFactors] = useState<string[]>([]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [result, setResult] = useState<FactorHeatmap | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    get<{ name: string }[]>("/factors")
      .then((factors) => setFactorList(factors.map((f) => ({ value: f.name, label: f.name }))))
      .catch(() => setFactorList([]));
  }, []);

  const generate = () => {
    if (selectedFactors.length < 2) return;
    setLoading(true);
    fetchFactorHeatmap({ factors: selectedFactors.join(","), start: startDate || undefined, end: endDate || undefined })
      .then(setResult)
      .catch(() => setResult(null))
      .finally(() => setLoading(false));
  };

  const heatmapOption = result && result.factors.length > 0 ? {
    tooltip: { position: "top" },
    grid: { left: 80, right: 30, top: 10, bottom: 50 },
    xAxis: { type: "category", data: result.factors, axisLabel: { color: "#71717a", fontSize: 10, rotate: 30 }, axisLine: { lineStyle: { color: "#27272a" } } },
    yAxis: { type: "category", data: result.factors, axisLabel: { color: "#71717a", fontSize: 10 }, axisLine: { lineStyle: { color: "#27272a" } } },
    visualMap: {
      min: -1, max: 1,
      inRange: { color: ["#7f1d1d", "#18181b", "#065f46"] },
      textStyle: { color: "#71717a" },
    },
    series: [{
      type: "heatmap",
      data: result.matrix.flatMap((row, i) => row.map((val, j) => [j, i, val])),
      label: { show: true, fontSize: 9, color: "#c8ccd0", formatter: (p: { data: [number, number, number] }) => p.data[2].toFixed(2) },
    }],
  } : undefined;

  return (
    <div className="space-y-4">
      <Card title={t("research.correlationPurpose")} accent="cyan">
        <div className="flex items-start gap-3">
          <GitCompare className="mt-0.5 h-5 w-5 text-terminal-cyan" />
          <p className="text-sm text-terminal-text-dim">{t("research.correlationPurposeText")}</p>
        </div>
      </Card>
      <Card title={t("research.generateHeatmap")}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-80">
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.factorsSelect")}</p>
            <MultiSelect options={factorList} values={selectedFactors} onChange={setSelectedFactors} placeholder={t("research.selectFactors")} />
          </div>
          <DatePicker value={startDate} onChange={setStartDate} />
          <DatePicker value={endDate} onChange={setEndDate} />
          <button
            onClick={generate}
            disabled={selectedFactors.length < 2}
            className="rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
          >
            {t("research.generate")}
          </button>
        </div>
      </Card>
      {loading && <Skeleton className="h-[400px] w-full" />}
      {!loading && heatmapOption && (
        <Card title={t("research.factorCorrelation")}>
          <EChartsWrapper option={heatmapOption} height={400} />
        </Card>
      )}
      {!loading && !heatmapOption && (
        <EmptyState title={t("research.noHeatmap")} detail={t("research.noHeatmapDetail")} />
      )}
    </div>
  );
}

function MiningTab() {
  const { t } = useTranslation();
  const [minIC, setMinIC] = useState(0.03);
  const [minICIR, setMinICIR] = useState(0.4);
  const [topN, setTopN] = useState(30);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const startMining = () => {
    setSubmitting(true);
    post<{ task_id: string }>("/factors/mine", { min_ic: minIC, min_icir: minICIR, top_n: topN })
      .then((res) => setTaskId(res.task_id))
      .catch(() => {})
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="space-y-4">
      <Card title={t("research.miningWorkflow")} accent="amber">
        <div className="grid gap-3 md:grid-cols-3">
          {[
            { label: t("research.mineStepScreen"), text: t("research.mineStepScreenText") },
            { label: t("research.mineStepValidate"), text: t("research.mineStepValidateText") },
            { label: t("research.mineStepPromote"), text: t("research.mineStepPromoteText") },
          ].map((step) => (
            <div key={step.label} className="rounded-sm border border-terminal-border-dim bg-terminal-raised p-3">
              <Pickaxe className="mb-2 h-4 w-4 text-terminal-amber" />
              <p className="font-mono text-xs uppercase tracking-wider text-terminal-text">{step.label}</p>
              <p className="mt-1 text-xs text-terminal-text-dim">{step.text}</p>
            </div>
          ))}
        </div>
      </Card>
      <Card title={t("research.candidateThresholds")}>
        <div className="grid max-w-2xl gap-4 sm:grid-cols-3">
          <div>
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.minIC")}</p>
            <NumberInput value={minIC} onChange={(v) => setMinIC(v ?? 0.03)} step={0.01} min={0} />
          </div>
          <div>
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.minICIR")}</p>
            <NumberInput value={minICIR} onChange={(v) => setMinICIR(v ?? 0.4)} step={0.1} min={0} />
          </div>
          <div>
            <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("research.topN")}</p>
            <NumberInput value={topN} onChange={(v) => setTopN(v ?? 30)} min={1} max={100} />
          </div>
        </div>
        <button
          onClick={startMining}
          disabled={submitting}
          className="mt-4 rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
        >
          {submitting ? t("common.starting") : t("research.startMining")}
        </button>
        {!taskId && (
          <p className="mt-3 text-sm text-terminal-text-dim">{t("research.noMiningTask")}</p>
        )}
        <TaskStatus taskId={taskId} />
      </Card>
    </div>
  );
}

export function ResearchPage() {
  const [activeTab, setActiveTab] = useState("library");

  return (
    <div className="space-y-5">
      <ResearchHeader />
      <div className="flex justify-end">
        <Tabs tabs={RESEARCH_TABS} activeKey={activeTab} onChange={setActiveTab} />
      </div>

      {activeTab === "library" && <LibraryTab />}
      {activeTab === "icAnalysis" && <ICAnalysisTab />}
      {activeTab === "heatmap" && <HeatmapTab />}
      {activeTab === "mining" && <MiningTab />}
    </div>
  );
}
