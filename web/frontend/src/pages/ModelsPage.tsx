import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Play, RefreshCw, Search, SlidersHorizontal, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { DatePicker } from "../components/ui/DatePicker";
import { EChartsWrapper } from "../components/ui/EChartsWrapper";
import { Select } from "../components/ui/Select";
import { Skeleton, SkeletonTable } from "../components/ui/Skeleton";
import { Table } from "../components/ui/Table";
import { ConsolePageLayout } from "../components/console/ConsolePageLayout";
import { useTaskTracking } from "../hooks/useTaskTracking";
import {
  getModelImportance,
  getModelMeta,
  getModelRegistry,
  listModels,
  triggerDelete,
  triggerTrain,
} from "../api/models";
import type {
  DeleteModelPreview,
  ModelInfo,
  RegistryInfo,
  TrainPreview,
} from "../api/models";
import type { TaskState } from "../api/types";
import { DeleteModelSchema, TrainSchema } from "../schemas/train";
import type { DeleteModelParams, TrainParams } from "../schemas/train";

const MARKET_OPTIONS = [
  { value: "csi300", label: "CSI 300" },
  { value: "csi500", label: "CSI 500" },
  { value: "csi800", label: "CSI 800" },
  { value: "csi1000", label: "CSI 1000" },
  { value: "all", label: "All" },
];

const TASK_FILTERS = ["model_train", "model_train_dry_run", "model_delete", "model_delete_dry_run"];

function valueText(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function modelRows(models: ModelInfo[]): Record<string, unknown>[] {
  return models.map((model) => ({
    filename: model.filename,
    size_mb: model.size_mb,
    modified: model.modified,
    model_type: model.meta?.model_type ?? model.meta?.model ?? model.meta?.name,
    tag: model.meta?.tag,
    market: model.meta?.final_market ?? model.meta?.market ?? model.meta?.universe,
    result_paths: model.result_paths?.join(", ") ?? "",
  }));
}

function taskRows(tasks: TaskState[]): Record<string, unknown>[] {
  return tasks.map((task) => ({
    task_id: task.task_id,
    task_type: task.task_type,
    action_key: task.action_key,
    status: task.status,
    created_at: task.created_at,
    result_paths: task.result_paths.join(", "),
  }));
}

function PreviewJson({ value }: { value: unknown }) {
  return (
    <pre className="max-h-56 overflow-auto rounded-sm border border-terminal-border bg-terminal-bg p-3 text-[11px] text-terminal-text-dim">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-[10px] font-mono uppercase tracking-wider text-terminal-text-dim">
      {children}
    </p>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className="w-full rounded-sm border border-terminal-border bg-terminal-surface px-3 py-2 font-mono text-xs text-terminal-text transition-colors placeholder:text-terminal-text-dim hover:border-terminal-text-dim focus:border-terminal-green focus:outline-none"
    />
  );
}

function TextArea({
  value,
  onChange,
  placeholder,
  rows = 4,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      rows={rows}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className="w-full resize-y rounded-sm border border-terminal-border bg-terminal-surface px-3 py-2 font-mono text-xs text-terminal-text transition-colors placeholder:text-terminal-text-dim hover:border-terminal-text-dim focus:border-terminal-green focus:outline-none"
    />
  );
}

function Toggle({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 font-mono text-xs text-terminal-text">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-terminal-green"
      />
      {children}
    </label>
  );
}

function parseCsvList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseSeeds(value: string): number[] | null {
  const items = parseCsvList(value);
  if (items.length === 0) return null;
  const seeds = items.map((item) => Number(item));
  if (seeds.some((seed) => !Number.isInteger(seed))) {
    throw new Error("ensemble_seeds must be comma-separated integers");
  }
  return seeds;
}

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error("bagging_fraction must be numeric");
  return parsed;
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  if (!value.trim()) return null;
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("LightGBM params must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function previewItems(preview: TrainPreview): { label: string; value: unknown }[] {
  return [
    { label: "final_market", value: preview.final_market },
    { label: "train_window", value: preview.train_window },
    { label: "config_source", value: preview.config_source ?? preview.config_override },
    { label: "estimated_outputs", value: preview.estimated_outputs ?? preview.output_path },
    { label: "effective_params", value: preview.effective_params },
  ];
}

function importanceEntries(importance: Record<string, unknown>): [string, number][] {
  const raw = Array.isArray(importance.importance) ? importance.importance : null;
  if (raw) {
    return raw
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const record = item as Record<string, unknown>;
        const feature = record.feature ?? record.name;
        const value = record.importance ?? record.gain ?? record.value;
        if (typeof feature !== "string" || typeof value !== "number") return null;
        return [feature, value] as [string, number];
      })
      .filter((item): item is [string, number] => item !== null);
  }
  return Object.entries(importance)
    .filter(([, value]) => typeof value === "number")
    .map(([key, value]) => [key, Number(value)]);
}

function TrainActionCard({
  registry,
  onTriggered,
}: {
  registry: RegistryInfo | null;
  onTriggered: () => void;
}) {
  const { t } = useTranslation();
  const { trackTask } = useTaskTracking({ pageKey: "models", taskTypeFilter: TASK_FILTERS });
  const [modelType, setModelType] = useState("lgbm");
  const [tag, setTag] = useState("web");
  const [market, setMarket] = useState("csi300");
  const [trainStartDate, setTrainStartDate] = useState("");
  const [trainEndDate, setTrainEndDate] = useState("");
  const [configOverride, setConfigOverride] = useState("");
  const [trainingMode, setTrainingMode] = useState("custom");
  const [factorNames, setFactorNames] = useState("");
  const [withSector, setWithSector] = useState(false);
  const [noExtraFactors, setNoExtraFactors] = useState(false);
  const [skipFactorPipeline, setSkipFactorPipeline] = useState(false);
  const [ensembleSeeds, setEnsembleSeeds] = useState("");
  const [baggingFraction, setBaggingFraction] = useState("");
  const [lgbmParams, setLgbmParams] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [preview, setPreview] = useState<TrainPreview | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const first = registry?.models[0]?.name;
    if (first) setModelType(first);
  }, [registry]);

  const modelOptions = registry?.models.map((model) => ({
    value: model.name,
    label: model.name,
  })) ?? [{ value: modelType, label: modelType }];
  const factorOptionsText = registry?.factors.slice(0, 10).map((factor) => factor.name).join(", ");

  const finalMarket = preview?.final_market ? String(preview.final_market) : "";
  const marketMismatch = Boolean(finalMarket && finalMarket !== market);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const params: TrainParams = TrainSchema.parse({
        model_type: modelType,
        tag,
        market,
        train_start_date: trainStartDate || null,
        train_end_date: trainEndDate || null,
        config_override: configOverride.trim() || null,
        factors: parseCsvList(factorNames),
        qlib_native: trainingMode === "qlib_native",
        with_sector: withSector,
        no_extra_factors: noExtraFactors,
        skip_factor_pipeline: skipFactorPipeline,
        ensemble_seeds: parseSeeds(ensembleSeeds),
        bagging_fraction: parseOptionalNumber(baggingFraction),
        lgbm_params: parseJsonObject(lgbmParams),
        dry_run: dryRun,
      });
      const result = await triggerTrain(params);
      setTaskId(result.task_id);
      trackTask(result.task_id);
      setPreview(result.preview);
      onTriggered();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card
      title={t("console.models.train.title")}
      accent="green"
      actions={
        <Badge variant={dryRun ? "warning" : "success"}>
          {dryRun ? t("console.models.dryRun") : t("console.models.liveRun")}
        </Badge>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>{t("console.models.train.modelType")}</FieldLabel>
            <Select options={modelOptions} value={modelType} onChange={setModelType} searchable />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.tag")}</FieldLabel>
            <TextInput value={tag} onChange={setTag} placeholder="web" />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.market")}</FieldLabel>
            <Select options={MARKET_OPTIONS} value={market} onChange={setMarket} />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.configOverride")}</FieldLabel>
            <TextInput
              value={configOverride}
              onChange={setConfigOverride}
              placeholder="config/daily_csi1000.yaml"
            />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.trainingMode")}</FieldLabel>
            <Select
              options={[
                { value: "custom", label: t("console.models.train.customMode") },
                { value: "qlib_native", label: t("console.models.train.qlibNativeMode") },
              ]}
              value={trainingMode}
              onChange={setTrainingMode}
            />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.startDate")}</FieldLabel>
            <DatePicker value={trainStartDate} onChange={setTrainStartDate} />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.endDate")}</FieldLabel>
            <DatePicker value={trainEndDate} onChange={setTrainEndDate} />
          </div>
        </div>

        <div className="grid gap-4 rounded-sm border border-terminal-border bg-terminal-raised p-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {t("console.models.train.researchConfig")}
            </div>
            <FieldLabel>{t("console.models.train.factorNames")}</FieldLabel>
            <TextInput
              value={factorNames}
              onChange={setFactorNames}
              placeholder={factorOptionsText || "northbound, sector"}
            />
          </div>
          <Toggle checked={withSector} onChange={setWithSector}>
            {t("console.models.train.withSector")}
          </Toggle>
          <Toggle checked={noExtraFactors} onChange={setNoExtraFactors}>
            {t("console.models.train.noExtraFactors")}
          </Toggle>
          <Toggle checked={skipFactorPipeline} onChange={setSkipFactorPipeline}>
            {t("console.models.train.skipFactorPipeline")}
          </Toggle>
          <div>
            <FieldLabel>{t("console.models.train.ensembleSeeds")}</FieldLabel>
            <TextInput value={ensembleSeeds} onChange={setEnsembleSeeds} placeholder="42, 123, 2024" />
          </div>
          <div>
            <FieldLabel>{t("console.models.train.baggingFraction")}</FieldLabel>
            <TextInput value={baggingFraction} onChange={setBaggingFraction} placeholder="0.8" />
          </div>
          <div className="md:col-span-2">
            <FieldLabel>{t("console.models.train.lgbmParams")}</FieldLabel>
            <TextArea
              value={lgbmParams}
              onChange={setLgbmParams}
              rows={5}
              placeholder={'{"learning_rate": 0.03, "num_leaves": 64, "n_estimators": 1200}'}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Toggle checked={dryRun} onChange={setDryRun}>
            {t("console.models.dryRun")}
          </Toggle>
          <button
            type="button"
            data-testid="models-train-submit"
            onClick={submit}
            disabled={submitting || !modelType || !tag}
            className="inline-flex items-center gap-2 rounded-sm border border-terminal-green px-3 py-1.5 font-mono text-xs text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play className="h-3.5 w-3.5" />
            {dryRun ? t("console.models.train.previewButton") : t("console.models.train.runButton")}
          </button>
        </div>

        {taskId && (
          <p className="font-mono text-xs text-terminal-text-dim">
            {t("console.models.taskId")}: {taskId}
          </p>
        )}
        {error && <p className="font-mono text-xs text-terminal-red">{error}</p>}

        {preview && (
          <div className="space-y-3 rounded-sm border border-terminal-border bg-terminal-raised p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">
                  {t("console.models.train.finalMarket")}
                </p>
                <p
                  className={`font-mono text-2xl font-semibold ${
                    marketMismatch ? "text-terminal-red" : "text-terminal-green"
                  }`}
                  data-testid="train-preview-final-market"
                >
                  {finalMarket || "-"}
                </p>
              </div>
              <div className="text-right font-mono text-xs text-terminal-text-dim">
                <p>{t("console.models.train.outputPath")}: {valueText(preview.output_path)}</p>
                <p>{t("console.models.train.estimatedMinutes")}: {valueText(preview.estimated_minutes)}</p>
              </div>
            </div>
            {marketMismatch && (
              <div className="flex gap-2 rounded-sm border border-terminal-red bg-terminal-red-glow p-3 font-mono text-xs text-terminal-red">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  {t("console.models.train.marketMismatch", {
                    selected: market,
                    final: finalMarket,
                  })}
                </span>
              </div>
            )}
            <div className="grid gap-2 md:grid-cols-2">
              {previewItems(preview).map((item) => (
                <div key={item.label} className="rounded-sm border border-terminal-border bg-terminal-surface px-3 py-2">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">
                    {item.label}
                  </p>
                  <p className="break-words font-mono text-xs text-terminal-text-bright">
                    {valueText(item.value)}
                  </p>
                </div>
              ))}
            </div>
            <PreviewJson value={preview} />
          </div>
        )}
      </div>
    </Card>
  );
}

function DeleteActionCard({
  models,
  onTriggered,
}: {
  models: ModelInfo[];
  onTriggered: () => void;
}) {
  const { t } = useTranslation();
  const { trackTask } = useTaskTracking({ pageKey: "models", taskTypeFilter: TASK_FILTERS });
  const [filename, setFilename] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [preview, setPreview] = useState<DeleteModelPreview | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!filename && models[0]?.filename) setFilename(models[0].filename);
  }, [filename, models]);

  const modelOptions = models.map((model) => ({
    value: model.filename,
    label: `${model.filename} (${model.size_mb} MB)`,
  }));

  const submit = async () => {
    if (!dryRun && !window.confirm(t("console.models.delete.confirm"))) return;
    setSubmitting(true);
    setError(null);
    try {
      const params: DeleteModelParams = DeleteModelSchema.parse({ filename, dry_run: dryRun });
      const result = await triggerDelete(params);
      setTaskId(result.task_id);
      trackTask(result.task_id);
      setPreview(result.preview);
      onTriggered();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card
      title={t("console.models.delete.title")}
      accent="red"
      actions={<Badge variant="error">{t("console.models.delete.destructive")}</Badge>}
    >
      <div className="space-y-4">
        <div>
          <FieldLabel>{t("console.models.delete.filename")}</FieldLabel>
          <Select
            options={modelOptions}
            value={filename}
            onChange={setFilename}
            searchable
            placeholder={t("console.models.delete.noModels")}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Toggle checked={dryRun} onChange={setDryRun}>
            {t("console.models.dryRun")}
          </Toggle>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || !filename}
            className="inline-flex items-center gap-2 rounded-sm border border-terminal-red px-3 py-1.5 font-mono text-xs text-terminal-red transition-colors hover:bg-terminal-red-glow disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {dryRun ? t("console.models.delete.previewButton") : t("console.models.delete.runButton")}
          </button>
        </div>

        {taskId && (
          <p className="font-mono text-xs text-terminal-text-dim">
            {t("console.models.taskId")}: {taskId}
          </p>
        )}
        {error && <p className="font-mono text-xs text-terminal-red">{error}</p>}

        {preview && (
          <div className="space-y-3 rounded-sm border border-terminal-border bg-terminal-raised p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-xs text-terminal-text">
                {t("console.models.delete.filesCount", { count: preview.count ?? preview.files?.length ?? 0 })}
              </p>
              <Badge variant="warning">{preview.filename ?? filename}</Badge>
            </div>
            <ul className="space-y-1 font-mono text-xs text-terminal-text-dim">
              {(preview.files ?? []).map((file) => (
                <li key={file}>{file}</li>
              ))}
            </ul>
            <PreviewJson value={preview} />
          </div>
        )}
      </div>
    </Card>
  );
}

function OverviewTab({ models, tasks }: { models: ModelInfo[]; tasks: TaskState[] }) {
  const { t } = useTranslation();
  const recentTrainCount = tasks.filter((task) => task.action_key === "models.train").length;
  const latestModel = [...models].sort((a, b) => b.modified.localeCompare(a.modified))[0];

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card title={t("console.models.overview.totalModels")} accent="cyan">
        <p className="font-mono text-3xl font-semibold text-terminal-text-bright">{models.length}</p>
      </Card>
      <Card title={t("console.models.overview.recentTraining")} accent="green">
        <p className="font-mono text-3xl font-semibold text-terminal-green">{recentTrainCount}</p>
      </Card>
      <Card title={t("console.models.overview.latestModel")} accent="amber">
        <p className="truncate font-mono text-sm text-terminal-text-bright">
          {latestModel?.filename ?? "-"}
        </p>
        <p className="mt-1 font-mono text-xs text-terminal-text-dim">
          {latestModel?.modified ? new Date(latestModel.modified).toLocaleString() : "-"}
        </p>
      </Card>
    </div>
  );
}

function ExecuteTab({
  registry,
  models,
  onRefresh,
}: {
  registry: RegistryInfo | null;
  models: ModelInfo[];
  onRefresh: () => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <TrainActionCard registry={registry} onTriggered={onRefresh} />
      <DeleteActionCard models={models} onTriggered={onRefresh} />
    </div>
  );
}

function HistoryTab({
  models,
  tasks,
  loading,
  onRefresh,
}: {
  models: ModelInfo[];
  tasks: TaskState[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <Card
        title={t("console.models.history.tasks")}
        actions={
          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex items-center gap-1 rounded-sm border border-terminal-border px-2 py-1 font-mono text-[10px] text-terminal-text-dim hover:border-terminal-text-dim"
          >
            <RefreshCw className="h-3 w-3" />
            {t("console.models.refresh")}
          </button>
        }
      >
        <Table
          columns={[
            { key: "created_at", label: t("console.models.history.created"), sortable: true },
            { key: "task_type", label: t("console.models.history.type"), sortable: true },
            { key: "action_key", label: t("console.models.history.action"), sortable: true },
            {
              key: "status",
              label: t("console.models.history.status"),
              sortable: true,
              render: (row) => <Badge>{String(row.status ?? "-")}</Badge>,
            },
            { key: "result_paths", label: t("console.models.history.outputs") },
          ]}
          data={taskRows(tasks)}
          pageSize={10}
          emptyMessage={t("console.models.history.noTasks")}
        />
      </Card>

      <Card title={t("console.models.history.models")}>
        {loading ? (
          <SkeletonTable rows={5} />
        ) : (
          <Table
            columns={[
              { key: "filename", label: t("console.models.filename"), sortable: true },
              { key: "model_type", label: t("console.models.modelType"), sortable: true },
              { key: "tag", label: t("console.models.tag"), sortable: true },
              { key: "market", label: t("console.models.market"), sortable: true },
              { key: "result_paths", label: t("console.models.history.outputs") },
              { key: "size_mb", label: t("console.models.sizeMb"), sortable: true, align: "right" },
              {
                key: "modified",
                label: t("console.models.modified"),
                sortable: true,
                render: (row) => (
                  <span className="text-terminal-text-dim">
                    {row.modified ? new Date(String(row.modified)).toLocaleString() : "-"}
                  </span>
                ),
              },
            ]}
            data={modelRows(models)}
            pageSize={12}
            emptyMessage={t("console.models.noModels")}
          />
        )}
      </Card>
    </div>
  );
}

function InspectTab({
  models,
  registry,
  loading,
}: {
  models: ModelInfo[];
  registry: RegistryInfo | null;
  loading: boolean;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState("");
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [importance, setImportance] = useState<Record<string, unknown> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (!selected && models[0]?.filename) setSelected(models[0].filename);
  }, [models, selected]);

  useEffect(() => {
    if (!selected) {
      setMeta(null);
      setImportance(null);
      return;
    }
    setDetailLoading(true);
    Promise.allSettled([getModelMeta(selected), getModelImportance(selected)])
      .then(([metaResult, importanceResult]) => {
        setMeta(metaResult.status === "fulfilled" ? metaResult.value : null);
        setImportance(importanceResult.status === "fulfilled" ? importanceResult.value : null);
      })
      .finally(() => setDetailLoading(false));
  }, [selected]);

  const modelOptions = models.map((model) => ({
    value: model.filename,
    label: `${model.filename} (${model.size_mb} MB)`,
  }));
  const selectedInfo = models.find((model) => model.filename === selected);
  const lineageItems = [
    ["model", meta?.model ?? meta?.model_type ?? selectedInfo?.meta?.model],
    ["tag", meta?.tag ?? selectedInfo?.meta?.tag],
    ["safe_tag", meta?.safe_tag],
    ["ts", meta?.ts ?? selectedInfo?.modified],
    ["recorder_id", meta?.recorder_id],
    ["result_paths", selectedInfo?.result_paths],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  const importanceChartOption = useMemo(() => {
    if (!importance) return null;
    const entries = importanceEntries(importance)
      .sort(([, a], [, b]) => Number(b) - Number(a))
      .slice(0, 20);
    if (entries.length === 0) return null;
    return {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 140, right: 20, top: 10, bottom: 30 },
      xAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#1e1e22" } },
        axisLabel: { color: "#71717a" },
      },
      yAxis: {
        type: "category",
        data: entries.map(([feature]) => feature).reverse(),
        axisLine: { lineStyle: { color: "#27272a" } },
        axisLabel: { color: "#71717a", fontSize: 10 },
      },
      series: [
        {
          type: "bar",
          data: entries.map(([, value]) => Number(value)).reverse(),
          itemStyle: { color: "#22c55e" },
          barWidth: 14,
        },
      ],
    };
  }, [importance]);

  return (
    <div className="space-y-6">
      <Card title={t("console.models.inspect.select")} actions={<Search className="h-4 w-4 text-terminal-text-dim" />}>
        {loading ? (
          <Skeleton className="h-9 w-full" />
        ) : (
          <Select
            options={modelOptions}
            value={selected}
            onChange={setSelected}
            searchable
            placeholder={t("console.models.noModels")}
          />
        )}
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
        <div className="space-y-6">
          <Card title={t("console.models.inspect.meta")}>
            {detailLoading ? (
              <SkeletonTable rows={4} />
            ) : meta && Object.keys(meta).length > 0 ? (
              <div className="grid gap-2 md:grid-cols-2">
                {Object.entries(meta).map(([key, value]) => (
                  <div key={key} className="rounded-sm border border-terminal-border bg-terminal-raised px-3 py-2">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">{key}</p>
                    <p className="break-words font-mono text-xs text-terminal-text-bright">{valueText(value)}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="font-mono text-xs text-terminal-text-dim">{t("console.models.inspect.noMeta")}</p>
            )}
          </Card>

          <Card title={t("console.models.inspect.lineage")}>
            {lineageItems.length > 0 ? (
              <div className="grid gap-2 md:grid-cols-2">
                {lineageItems.map(([key, value]) => (
                  <div key={String(key)} className="rounded-sm border border-terminal-border bg-terminal-raised px-3 py-2">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">{String(key)}</p>
                    <p className="break-words font-mono text-xs text-terminal-text-bright">{valueText(value)}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="font-mono text-xs text-terminal-text-dim">{t("console.models.inspect.noLineage")}</p>
            )}
          </Card>
        </div>

        <Card title={t("console.models.inspect.registry")}>
          {registry ? (
            <div className="space-y-4">
              <div>
                <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">
                  {t("console.models.inspect.registeredModels", { count: registry.models.length })}
                </p>
                <div className="flex flex-wrap gap-2">
                  {registry.models.map((model) => (
                    <Badge key={model.name} variant="success">{model.name}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">
                  {t("console.models.inspect.registeredFactors", { count: registry.factors.length })}
                </p>
                <div className="flex max-h-40 flex-wrap gap-2 overflow-auto">
                  {registry.factors.map((factor) => (
                    <Badge key={factor.name} variant="info">{factor.name}</Badge>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="font-mono text-xs text-terminal-text-dim">{t("console.models.inspect.noRegistry")}</p>
          )}
        </Card>
      </div>

      <Card title={t("console.models.inspect.importance")}>
        {detailLoading ? (
          <Skeleton className="h-[420px] w-full" />
        ) : importanceChartOption ? (
          <EChartsWrapper option={importanceChartOption} height={420} />
        ) : (
          <p className="font-mono text-xs text-terminal-text-dim">{t("console.models.inspect.noImportance")}</p>
        )}
      </Card>
    </div>
  );
}

export function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [registry, setRegistry] = useState<RegistryInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const { tasks, refresh: refreshTasks } = useTaskTracking({
    pageKey: "models",
    taskTypeFilter: TASK_FILTERS,
  });

  const refresh = () => {
    setLoading(true);
    Promise.allSettled([listModels(), getModelRegistry()])
      .then(([modelsResult, registryResult]) => {
        setModels(modelsResult.status === "fulfilled" ? modelsResult.value : []);
        setRegistry(registryResult.status === "fulfilled" ? registryResult.value : null);
      })
      .finally(() => setLoading(false));
    refreshTasks();
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <ConsolePageLayout
      pageKey="models"
      titleKey="console.models.title"
      taskTypeFilter={TASK_FILTERS}
      tabs={{
        overview: <OverviewTab models={models} tasks={tasks} />,
        execute: <ExecuteTab registry={registry} models={models} onRefresh={refresh} />,
        history: (
          <HistoryTab
            models={models}
            tasks={tasks}
            loading={loading}
            onRefresh={refresh}
          />
        ),
        inspect: <InspectTab models={models} registry={registry} loading={loading} />,
      }}
    />
  );
}
