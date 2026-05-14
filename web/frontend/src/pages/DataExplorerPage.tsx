import { useCallback, useEffect, useMemo, useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Database, Play, RefreshCw, Trash2 } from "lucide-react";
import { Card } from "../components/ui/Card";
import { Tabs } from "../components/ui/Tabs";
import { Table } from "../components/ui/Table";
import { Select } from "../components/ui/Select";
import { SearchInput } from "../components/ui/SearchInput";
import { DatePicker } from "../components/ui/DatePicker";
import { MultiSelect } from "../components/ui/MultiSelect";
import { EChartsWrapper } from "../components/ui/EChartsWrapper";
import { Skeleton, SkeletonTable } from "../components/ui/Skeleton";
import {
  ConfirmDialog,
  ConsolePageLayout,
  DryRunPreview,
  ExecutionForm,
} from "../components/console";
import { useDryRunPreview } from "../hooks/useDryRunPreview";
import { useTaskTracking } from "../hooks/useTaskTracking";
import {
  searchStocks,
  fetchStockQuotes,
  fetchSectors,
  fetchSectorStocks,
  fetchSectorRotation,
  fetchAltData,
} from "../api/client";
import { getCacheStatus, triggerFetch, triggerPurge } from "../api/data";
import type { CacheStatus, DataFetchPreview, DataPurgePreview } from "../api/data";
import type { StockQuote, SectorInfo, SectorRotation, AltDataResponse, TaskState } from "../api/types";
import { FetchSchema, PurgeSchema } from "../schemas/data";
import type { DataType, FetchParams, PurgeParams } from "../schemas/data";

const TASK_TYPE_FILTER = ["data_fetch", "data_purge", "data_fetch_dry_run", "data_purge_dry_run"];

const DATA_TYPE_OPTIONS: { value: DataType; labelKey: string }[] = [
  { value: "prices", labelKey: "console.data.dataTypePrices" },
  { value: "financial", labelKey: "console.data.dataTypeFinancial" },
  { value: "northbound", labelKey: "console.data.dataTypeNorthbound" },
  { value: "sectors", labelKey: "console.data.dataTypeSectors" },
];

const INSPECT_TABS = [
  { key: "quotes", label: "Stock Quotes" },
  { key: "sectors", label: "Sectors" },
  { key: "altData", label: "Alt Data" },
];

const ALT_DATA_TYPES = [
  "northbound", "margin", "pledge", "insider", "analyst",
  "shareholder", "dividend", "valuation", "balance_sheet",
  "earnings_guidance", "institutional", "repurchase", "visit",
];

const OVERLAY_OPTIONS = [
  { value: "ma5", label: "MA5" },
  { value: "ma20", label: "MA20" },
  { value: "boll", label: "BOLL" },
  { value: "vwap", label: "VWAP" },
];

function computeMA(data: number[], period: number): (number | null)[] {
  return data.map((_, i) => {
    if (i < period - 1) return null;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j];
    return sum / period;
  });
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatBytes(value: number | undefined) {
  if (!value) return "0 B";
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function actionButtonLabel(dryRun: boolean, previewLabel: string, submitLabel: string) {
  return dryRun ? previewLabel : submitLabel;
}

function DataTypeCheckboxes({ form }: { form: UseFormReturn<FetchParams> }) {
  const { t } = useTranslation();
  const selected = form.watch("data_types") ?? [];

  return (
    <fieldset>
      <legend className="mb-2 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">
        {t("console.data.dataTypes")}
      </legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {DATA_TYPE_OPTIONS.map((option) => {
          const checked = selected.includes(option.value);
          return (
            <label
              key={option.value}
              className="flex items-center gap-2 rounded-sm border border-terminal-border px-3 py-2 text-sm text-terminal-text"
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...selected, option.value]
                    : selected.filter((value) => value !== option.value);
                  form.setValue("data_types", next, { shouldValidate: true, shouldDirty: true });
                }}
              />
              {t(option.labelKey)}
            </label>
          );
        })}
      </div>
      {form.formState.errors.data_types && (
        <p className="mt-2 text-xs text-terminal-red">{String(form.formState.errors.data_types.message)}</p>
      )}
    </fieldset>
  );
}

function FetchPreview({ preview }: { preview: DataFetchPreview }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-3 text-sm sm:grid-cols-2">
      <div>
        <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.previewFiles")}</p>
        <p className="font-mono text-terminal-text-bright">{preview.estimated_files ?? 0}</p>
      </div>
      <div>
        <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.previewMinutes")}</p>
        <p className="font-mono text-terminal-text-bright">{preview.estimated_minutes ?? 0}</p>
      </div>
      <div>
        <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.previewDisk")}</p>
        <p className="font-mono text-terminal-text-bright">{preview.estimated_disk_mb ?? 0} MB</p>
      </div>
      <div>
        <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.previewSkipped")}</p>
        <p className="font-mono text-terminal-text-bright">
          {preview.skipped_cached?.length ? preview.skipped_cached.join(", ") : "-"}
        </p>
      </div>
    </div>
  );
}

function PurgePreview({ preview }: { preview: DataPurgePreview }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3 text-sm">
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.dataType")}</p>
          <p className="font-mono text-terminal-text-bright">{preview.data_type ?? "-"}</p>
        </div>
        <div>
          <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.previewFiles")}</p>
          <p className="font-mono text-terminal-text-bright">{preview.count ?? 0}</p>
        </div>
        <div>
          <p className="text-xs font-mono uppercase text-terminal-text-dim">{t("console.data.previewFreed")}</p>
          <p className="font-mono text-terminal-text-bright">{formatBytes(preview.freed_bytes)}</p>
        </div>
      </div>
      {preview.files?.length ? (
        <ul className="max-h-40 space-y-1 overflow-auto font-mono text-xs text-terminal-text-dim">
          {preview.files.slice(0, 20).map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
      ) : (
        <p className="font-mono text-xs text-terminal-text-dim">{t("console.data.noExpiredFiles")}</p>
      )}
    </div>
  );
}

function FetchActionCard({ trackTask }: { trackTask: (taskId: string) => void }) {
  const { t } = useTranslation();
  const preview = useDryRunPreview<FetchParams, DataFetchPreview>(triggerFetch);
  const [confirmParams, setConfirmParams] = useState<FetchParams | null>(null);
  const [confirming, setConfirming] = useState(false);

  const dryRun = async (params: FetchParams) => {
    const result = await preview.run({ ...params, dry_run: true });
    trackTask(result.task_id);
    return result;
  };

  const submit = async (params: FetchParams) => {
    if (params.force_refresh) {
      setConfirmParams({ ...params, dry_run: false });
      return { task_id: "awaiting-confirmation" };
    }
    const result = await triggerFetch({ ...params, dry_run: false });
    trackTask(result.task_id);
    return result;
  };

  const confirmSubmit = async () => {
    if (!confirmParams) return;
    setConfirming(true);
    try {
      const result = await triggerFetch(confirmParams);
      trackTask(result.task_id);
      setConfirmParams(null);
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Card title={t("console.data.fetchTitle")} accent="green">
      <div className="mb-4 flex items-start gap-3">
        <Database className="mt-0.5 h-5 w-5 text-terminal-green" />
        <p className="text-sm text-terminal-text-dim">{t("console.data.fetchDescription")}</p>
      </div>
      <ExecutionForm<FetchParams>
        pageKey="data"
        actionKey="data.fetch"
        schema={FetchSchema}
        defaults={{
          data_types: ["financial"],
          date_range: { start: null, end: null },
          force_refresh: false,
          dry_run: true,
        }}
        dryRunDefault={true}
        onDryRun={dryRun}
        onSubmit={submit}
        renderFields={(form) => {
          const isDryRun = form.watch("dry_run");
          return (
            <>
              <DataTypeCheckboxes form={form} />
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-xs font-mono uppercase tracking-wider text-terminal-text-dim">
                    {t("console.data.startDate")}
                  </span>
                  <DatePicker
                    value={form.watch("date_range")?.start ?? ""}
                    onChange={(value) => form.setValue("date_range.start", value || null)}
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-mono uppercase tracking-wider text-terminal-text-dim">
                    {t("console.data.endDate")}
                  </span>
                  <DatePicker
                    value={form.watch("date_range")?.end ?? ""}
                    onChange={(value) => form.setValue("date_range.end", value || null)}
                  />
                </label>
              </div>
              <div className="flex flex-wrap gap-4 text-sm text-terminal-text">
                <label className="inline-flex items-center gap-2">
                  <input type="checkbox" {...form.register("force_refresh")} />
                  {t("console.data.forceRefresh")}
                </label>
                <label className="inline-flex items-center gap-2">
                  <input type="checkbox" {...form.register("dry_run")} />
                  {t("console.common.dryRun")}
                </label>
              </div>
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green hover:bg-terminal-green-glow"
              >
                {isDryRun ? <RefreshCw className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                {actionButtonLabel(
                  isDryRun,
                  t("console.data.previewFetch"),
                  t("console.data.runFetch"),
                )}
              </button>
            </>
          );
        }}
      />
      <div className="mt-4">
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => <FetchPreview preview={value as DataFetchPreview} />}
        />
      </div>
      <ConfirmDialog
        open={!!confirmParams}
        titleKey="console.data.confirmFetchTitle"
        impactSummary={
          <span>
            {t("console.data.confirmFetchImpact")} {confirming ? t("common.loading") : ""}
          </span>
        }
        confirmLabelKey="console.data.runFetch"
        destructive
        onConfirm={confirmSubmit}
        onCancel={() => setConfirmParams(null)}
      />
    </Card>
  );
}

function PurgeActionCard({ trackTask }: { trackTask: (taskId: string) => void }) {
  const { t } = useTranslation();
  const preview = useDryRunPreview<PurgeParams, DataPurgePreview>(triggerPurge);
  const [confirmParams, setConfirmParams] = useState<PurgeParams | null>(null);
  const [confirming, setConfirming] = useState(false);

  const dryRun = async (params: PurgeParams) => {
    const result = await preview.run({ ...params, dry_run: true });
    trackTask(result.task_id);
    return result;
  };

  const submit = async (params: PurgeParams) => {
    setConfirmParams({ ...params, dry_run: false });
    return { task_id: "awaiting-confirmation" };
  };

  const confirmSubmit = async () => {
    if (!confirmParams) return;
    setConfirming(true);
    try {
      const result = await triggerPurge(confirmParams);
      trackTask(result.task_id);
      setConfirmParams(null);
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Card title={t("console.data.purgeTitle")} accent="red">
      <div className="mb-4 flex items-start gap-3">
        <Trash2 className="mt-0.5 h-5 w-5 text-terminal-red" />
        <p className="text-sm text-terminal-text-dim">{t("console.data.purgeDescription")}</p>
      </div>
      <ExecutionForm<PurgeParams>
        pageKey="data"
        actionKey="data.purge_expired"
        schema={PurgeSchema}
        defaults={{ data_type: "financial", dry_run: true }}
        dryRunDefault={true}
        destructive
        onDryRun={dryRun}
        onSubmit={submit}
        renderFields={(form) => {
          const isDryRun = form.watch("dry_run");
          return (
            <>
              <label className="block">
                <span className="mb-1 block text-xs font-mono uppercase tracking-wider text-terminal-text-dim">
                  {t("console.data.dataType")}
                </span>
                <Select
                  value={form.watch("data_type")}
                  onChange={(value) => form.setValue("data_type", value as DataType)}
                  options={DATA_TYPE_OPTIONS.map((option) => ({
                    value: option.value,
                    label: t(option.labelKey),
                  }))}
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-terminal-text">
                <input type="checkbox" {...form.register("dry_run")} />
                {t("console.common.dryRun")}
              </label>
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-sm border border-terminal-red px-3 py-1.5 text-xs font-mono text-terminal-red hover:bg-terminal-red-glow"
              >
                {isDryRun ? <RefreshCw className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
                {actionButtonLabel(
                  isDryRun,
                  t("console.data.previewPurge"),
                  t("console.data.runPurge"),
                )}
              </button>
            </>
          );
        }}
      />
      <div className="mt-4">
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => <PurgePreview preview={value as DataPurgePreview} />}
        />
      </div>
      <ConfirmDialog
        open={!!confirmParams}
        titleKey="console.data.confirmPurgeTitle"
        impactSummary={
          <span>
            {t("console.data.confirmPurgeImpact")} {confirming ? t("common.loading") : ""}
          </span>
        }
        confirmLabelKey="console.data.runPurge"
        destructive
        onConfirm={confirmSubmit}
        onCancel={() => setConfirmParams(null)}
      />
    </Card>
  );
}

function ExecuteTab() {
  const { trackTask } = useTaskTracking({ pageKey: "data", taskTypeFilter: TASK_TYPE_FILTER });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <FetchActionCard trackTask={trackTask} />
      <PurgeActionCard trackTask={trackTask} />
    </div>
  );
}

function useCacheStatus() {
  const [cache, setCache] = useState<CacheStatus[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    getCacheStatus()
      .then(setCache)
      .catch(() => setCache([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(refresh, [refresh]);

  return { cache, loading, refresh };
}

function OverviewTab() {
  const { t } = useTranslation();
  const { cache, loading } = useCacheStatus();
  const { tasks } = useTaskTracking({ pageKey: "data", taskTypeFilter: TASK_TYPE_FILTER });
  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const recentTaskCount = tasks.filter((task) => new Date(task.created_at).getTime() >= sevenDaysAgo).length;
  const totalFiles = cache.reduce((sum, item) => sum + item.file_count, 0);
  const totalSize = cache.reduce((sum, item) => sum + item.total_size_mb, 0);

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card title={t("console.data.cacheFiles")} accent="green">
        <p className="font-mono text-3xl text-terminal-text-bright">{loading ? "-" : totalFiles}</p>
      </Card>
      <Card title={t("console.data.cacheSize")} accent="cyan">
        <p className="font-mono text-3xl text-terminal-text-bright">{loading ? "-" : totalSize.toFixed(2)} MB</p>
      </Card>
      <Card title={t("console.data.recentTasks")} accent="amber">
        <p className="font-mono text-3xl text-terminal-text-bright">{recentTaskCount}</p>
      </Card>
    </div>
  );
}

function HistoryTab() {
  const { t } = useTranslation();
  const { tasks, refresh: refreshTasks } = useTaskTracking({ pageKey: "data", taskTypeFilter: TASK_TYPE_FILTER });
  const { cache, loading: cacheLoading, refresh: refreshCache } = useCacheStatus();
  const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000;
  const recentTasks = tasks.filter((task) => new Date(task.created_at).getTime() >= thirtyDaysAgo);

  const refreshAll = () => {
    refreshTasks();
    refreshCache();
  };

  return (
    <div className="space-y-4">
      <Card
        title={t("console.data.taskHistory")}
        actions={
          <button
            type="button"
            onClick={refreshAll}
            className="inline-flex items-center gap-1 rounded-sm border border-terminal-border px-2 py-1 text-xs font-mono text-terminal-text-dim hover:text-terminal-text"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t("console.data.refresh")}
          </button>
        }
      >
        <Table<TaskState & Record<string, unknown>>
          columns={[
            { key: "created_at", label: t("console.data.createdAt"), render: (row) => formatDate(row.created_at) },
            { key: "task_type", label: t("console.data.taskType"), sortable: true },
            { key: "action_key", label: t("console.data.actionKey"), sortable: true },
            { key: "status", label: t("console.data.status"), sortable: true },
            { key: "error", label: t("console.data.error"), render: (row) => row.error ?? "-" },
          ]}
          data={recentTasks as (TaskState & Record<string, unknown>)[]}
          pageSize={10}
          rowKey="task_id"
          emptyMessage={t("console.data.noTasks")}
        />
      </Card>
      <Card title={t("console.data.cacheFingerprint")}>
        {cacheLoading ? (
          <SkeletonTable rows={5} />
        ) : (
          <Table<CacheStatus & Record<string, unknown>>
            columns={[
              { key: "type", label: t("console.data.dataType"), sortable: true },
              { key: "file_count", label: t("console.data.files"), align: "right", sortable: true },
              { key: "total_size_mb", label: t("console.data.sizeMb"), align: "right", sortable: true },
              { key: "latest", label: t("console.data.latest"), render: (row) => formatDate(row.latest) },
              { key: "ttl_days", label: t("console.data.ttlDays"), align: "right" },
            ]}
            data={cache as (CacheStatus & Record<string, unknown>)[]}
            pageSize={10}
            rowKey="type"
          />
        )}
      </Card>
    </div>
  );
}

function StockQuotesTab() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{ symbol: string; name: string }[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [selectedName, setSelectedName] = useState("");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("");
  const [quotes, setQuotes] = useState<StockQuote[]>([]);
  const [overlays, setOverlays] = useState<string[]>(["ma20"]);
  const [loading, setLoading] = useState(false);

  const handleSearch = useCallback((q: string) => {
    setQuery(q);
    if (q.length >= 2) {
      searchStocks(q, 8).then(setSearchResults).catch(() => setSearchResults([]));
    } else {
      setSearchResults([]);
    }
  }, []);

  const selectStock = (symbol: string, name: string) => {
    setSelectedSymbol(symbol);
    setSelectedName(name);
    setSearchResults([]);
    setLoading(true);
    fetchStockQuotes(symbol, { start: startDate, end: endDate || undefined })
      .then((res) => setQuotes(res.data || []))
      .catch(() => setQuotes([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (selectedSymbol) {
      setLoading(true);
      fetchStockQuotes(selectedSymbol, { start: startDate, end: endDate || undefined })
        .then((res) => setQuotes(res.data || []))
        .catch(() => setQuotes([]))
        .finally(() => setLoading(false));
    }
  }, [startDate, endDate, selectedSymbol]);

  const lastQuote = quotes[quotes.length - 1];

  const chartOption = quotes.length > 0 ? {
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    legend: { data: ["Kline", "Volume", ...overlays.map((o) => o.toUpperCase())], textStyle: { color: "#71717a" } },
    grid: [
      { left: 60, right: 20, top: 40, height: "55%" },
      { left: 60, right: 20, top: "72%", height: "18%" },
    ],
    xAxis: [
      { type: "category", data: quotes.map((q) => q.date), gridIndex: 0, axisLine: { lineStyle: { color: "#27272a" } }, axisLabel: { color: "#71717a", fontSize: 10 } },
      { type: "category", data: quotes.map((q) => q.date), gridIndex: 1, axisLabel: { show: false } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, scale: true, splitLine: { lineStyle: { color: "#1e1e22" } }, axisLabel: { color: "#71717a", fontSize: 10 } },
      { type: "value", gridIndex: 1, scale: true, splitLine: { show: false }, axisLabel: { show: false } },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: Math.max(0, 100 - (200 / quotes.length) * 100) },
      { type: "slider", xAxisIndex: [0, 1], bottom: 10, height: 16, borderColor: "#27272a", fillerColor: "rgba(34,197,94,0.15)", handleStyle: { color: "#22c55e" } },
    ],
    series: [
      {
        name: "Kline",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: quotes.map((q) => [q.open, q.close, q.low, q.high]),
        itemStyle: { color: "#22c55e", color0: "#ef4444", borderColor: "#22c55e", borderColor0: "#ef4444" },
      },
      {
        name: "Volume",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: quotes.map((q) => [q.volume, q.close >= q.open ? "#22c55e" : "#ef4444"]),
        itemStyle: { color: (params: { data?: [number, string] }) => params.data?.[1] || "#22c55e" },
        encode: { y: 0 },
      },
      ...(overlays.includes("ma5") ? [{
        name: "MA5",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: computeMA(quotes.map((q) => q.close), 5),
        smooth: true,
        lineStyle: { width: 1, color: "#f59e0b" },
        symbol: "none",
      }] : []),
      ...(overlays.includes("ma20") ? [{
        name: "MA20",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: computeMA(quotes.map((q) => q.close), 20),
        smooth: true,
        lineStyle: { width: 1, color: "#06b6d4" },
        symbol: "none",
      }] : []),
    ],
  } : undefined;

  return (
    <div className="flex gap-4">
      <div className="w-72 shrink-0 space-y-4">
        <Card>
          <p className="mb-2 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("dataExplorer.search")}</p>
          <SearchInput value={query} onChange={handleSearch} placeholder="600519 / maotai" />
          {searchResults.length > 0 && (
            <div className="mt-2 max-h-48 overflow-auto rounded-sm border border-terminal-border bg-terminal-raised">
              {searchResults.map((result) => (
                <button
                  key={result.symbol}
                  onClick={() => selectStock(result.symbol, result.name)}
                  className="flex w-full justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-terminal-border"
                >
                  <span className="font-mono text-xs text-terminal-text">{result.symbol}</span>
                  <span className="text-terminal-text-dim">{result.name}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <p className="mb-2 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("dataExplorer.dateRange")}</p>
          <div className="flex gap-2">
            <DatePicker value={startDate} onChange={setStartDate} className="flex-1" />
            <DatePicker value={endDate} onChange={setEndDate} className="flex-1" />
          </div>
        </Card>
        <Card>
          <p className="mb-2 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{t("dataExplorer.overlays")}</p>
          <MultiSelect
            options={OVERLAY_OPTIONS}
            values={overlays}
            onChange={setOverlays}
            placeholder="Select overlays..."
          />
        </Card>
        {lastQuote && (
          <Card title={selectedName || selectedSymbol}>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-terminal-text-dim">Open</span><span className="font-mono text-terminal-text">{lastQuote.open?.toFixed(2)}</span></div>
              <div className="flex justify-between"><span className="text-terminal-text-dim">High</span><span className="font-mono text-terminal-green">{lastQuote.high?.toFixed(2)}</span></div>
              <div className="flex justify-between"><span className="text-terminal-text-dim">Low</span><span className="font-mono text-terminal-red">{lastQuote.low?.toFixed(2)}</span></div>
              <div className="flex justify-between"><span className="text-terminal-text-dim">Close</span><span className="font-mono text-terminal-text-bright">{lastQuote.close?.toFixed(2)}</span></div>
              <div className="flex justify-between"><span className="text-terminal-text-dim">Volume</span><span className="font-mono text-terminal-text-dim">{(lastQuote.volume / 1e4).toFixed(0)}w</span></div>
              <div className="flex justify-between">
                <span className="text-terminal-text-dim">Change</span>
                <span className={`font-mono ${lastQuote.change >= 0 ? "text-terminal-green" : "text-terminal-red"}`}>
                  {(lastQuote.change * 100).toFixed(2)}%
                </span>
              </div>
            </div>
          </Card>
        )}
      </div>

      <div className="flex-1">
        {loading && <Skeleton className="h-[520px] w-full" />}
        {!loading && chartOption && <EChartsWrapper option={chartOption} height={520} />}
        {!loading && !chartOption && selectedSymbol && <p className="text-sm text-terminal-text-dim">{t("dataExplorer.noData")}</p>}
        {!selectedSymbol && (
          <div className="flex h-96 items-center justify-center text-sm font-mono text-terminal-text-dim">
            {t("dataExplorer.searchHint")}
          </div>
        )}
      </div>
    </div>
  );
}

function SectorsTab() {
  const { t } = useTranslation();
  const [sectors, setSectors] = useState<SectorInfo[]>([]);
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [sectorStocks, setSectorStocks] = useState<{ symbol: string; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [rotation, setRotation] = useState<SectorRotation[]>([]);
  const [rotationLoading, setRotationLoading] = useState(false);

  useEffect(() => {
    fetchSectors()
      .then(setSectors)
      .catch(() => setSectors([]))
      .finally(() => setLoading(false));
  }, []);

  const loadRotation = () => {
    setRotationLoading(true);
    fetchSectorRotation("1,5,20")
      .then(setRotation)
      .catch(() => setRotation([]))
      .finally(() => setRotationLoading(false));
  };

  const handleSectorClick = (row: Record<string, unknown>) => {
    const id = row.sector_id as string;
    setSelectedSector(id);
    fetchSectorStocks(id)
      .then((res) => setSectorStocks(res.stocks || []))
      .catch(() => setSectorStocks([]));
  };

  const rotationHeatmapOption = useMemo(() => {
    if (rotation.length === 0) return null;
    const windows = Object.keys(rotation[0].returns).sort();
    const sectorNames = rotation.map((item) => item.sector_name);
    const data: [number, number, number][] = [];
    rotation.forEach((item, i) => {
      windows.forEach((window, j) => {
        data.push([j, i, item.returns[window] ?? 0]);
      });
    });
    return {
      tooltip: {
        position: "top",
        formatter: (params: { data: [number, number, number] }) => {
          const value = params.data[2];
          return `${sectorNames[params.data[1]]} / ${windows[params.data[0]]}: ${(value * 100).toFixed(2)}%`;
        },
      },
      grid: { left: 120, right: 30, top: 10, bottom: 50 },
      xAxis: {
        type: "category",
        data: windows,
        axisLabel: { color: "#71717a", fontSize: 11 },
        axisLine: { lineStyle: { color: "#27272a" } },
      },
      yAxis: {
        type: "category",
        data: sectorNames,
        axisLabel: { color: "#71717a", fontSize: 10 },
        axisLine: { lineStyle: { color: "#27272a" } },
      },
      visualMap: {
        min: -0.1,
        max: 0.1,
        inRange: { color: ["#7f1d1d", "#18181b", "#065f46"] },
        textStyle: { color: "#71717a" },
      },
      series: [
        {
          type: "heatmap",
          data,
          label: {
            show: true,
            fontSize: 9,
            color: "#c8ccd0",
            formatter: (params: { data: [number, number, number] }) => `${(params.data[2] * 100).toFixed(1)}%`,
          },
        },
      ],
    };
  }, [rotation]);

  if (loading) return <SkeletonTable rows={8} />;

  return (
    <div className="space-y-4">
      <div className="flex gap-4">
        <div className="flex-1">
          <Table
            columns={[
              { key: "sector_name", label: "Sector", sortable: true },
              { key: "stock_count", label: "Stocks", align: "right", sortable: true },
            ]}
            data={sectors as unknown as Record<string, unknown>[]}
            onRowClick={handleSectorClick}
            pageSize={20}
          />
        </div>
        {selectedSector && (
          <div className="w-72">
            <Card title={selectedSector}>
              {sectorStocks.length > 0 ? (
                <div className="max-h-96 space-y-1 overflow-auto">
                  {sectorStocks.map((stock) => (
                    <div key={stock.symbol} className="flex justify-between rounded-sm px-2 py-1 text-sm transition-colors hover:bg-terminal-raised">
                      <span className="font-mono text-xs text-terminal-text">{stock.symbol}</span>
                      <span className="text-terminal-text-dim">{stock.name}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-terminal-text-dim">{t("common.noData")}</p>
              )}
            </Card>
          </div>
        )}
      </div>
      <Card title="Sector Rotation Heatmap">
        <div className="space-y-3">
          <button
            onClick={loadRotation}
            disabled={rotationLoading}
            className="rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
          >
            {rotationLoading ? t("common.loading") : "Load Rotation"}
          </button>
          {rotationHeatmapOption && (
            <EChartsWrapper option={rotationHeatmapOption} height={Math.max(300, rotation.length * 28 + 60)} />
          )}
          {!rotationHeatmapOption && rotation.length === 0 && !rotationLoading && (
            <p className="text-sm font-mono text-terminal-text-dim">Click "Load Rotation" to fetch sector returns across time windows.</p>
          )}
        </div>
      </Card>
    </div>
  );
}

function AltDataTab() {
  const { t } = useTranslation();
  const [dataType, setDataType] = useState("northbound");
  const [symbol, setSymbol] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [data, setData] = useState<AltDataResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = () => {
    setLoading(true);
    fetchAltData(dataType, { symbol: symbol || undefined, start: startDate || undefined, end: endDate || undefined })
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="w-48">
          <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">Data Type</p>
          <Select
            options={ALT_DATA_TYPES.map((type) => ({ value: type, label: type }))}
            value={dataType}
            onChange={setDataType}
          />
        </div>
        <div className="w-48">
          <p className="mb-1 text-xs font-mono uppercase tracking-wider text-terminal-text-dim">Symbol</p>
          <SearchInput value={symbol} onChange={setSymbol} placeholder="Filter symbol..." />
        </div>
        <DatePicker value={startDate} onChange={setStartDate} />
        <DatePicker value={endDate} onChange={setEndDate} />
        <button
          onClick={fetchData}
          className="rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green transition-colors hover:bg-terminal-green-glow"
        >
          {t("common.search")}
        </button>
      </div>

      {loading && <SkeletonTable rows={6} />}
      {data && data.rows.length > 0 && (
        <Card>
          <p className="mb-2 text-xs font-mono text-terminal-text-dim">
            {data.total} rows ({data.columns.length} cols) {data.has_more ? "(showing first 100)" : ""}
          </p>
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="sticky top-0 border-b border-terminal-border bg-terminal-surface">
                  {data.columns.map((column) => (
                    <th key={column} className="px-3 py-2 text-left text-xs font-mono uppercase tracking-wider text-terminal-text-dim">{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, index) => (
                  <tr key={index} className="border-b border-terminal-border-dim transition-colors hover:bg-terminal-raised">
                    {data.columns.map((column) => (
                      <td key={column} className="px-3 py-1 text-xs font-mono text-terminal-text">{String(row[column] ?? "-")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {data && data.rows.length === 0 && <p className="text-sm text-terminal-text-dim">{t("common.noData")}</p>}
    </div>
  );
}

function InspectTab() {
  const [activeTab, setActiveTab] = useState("quotes");

  return (
    <div className="space-y-4">
      <Tabs tabs={INSPECT_TABS} activeKey={activeTab} onChange={setActiveTab} />
      {activeTab === "quotes" && <StockQuotesTab />}
      {activeTab === "sectors" && <SectorsTab />}
      {activeTab === "altData" && <AltDataTab />}
    </div>
  );
}

export function DataExplorerPage() {
  return (
    <ConsolePageLayout
      pageKey="data"
      titleKey="console.data.title"
      taskTypeFilter={TASK_TYPE_FILTER}
      initialTab="execute"
      tabs={{
        overview: <OverviewTab />,
        execute: <ExecuteTab />,
        history: <HistoryTab />,
        inspect: <InspectTab />,
      }}
    />
  );
}
