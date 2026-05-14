import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ConfirmDialog,
  ConsolePageLayout,
  DryRunPreview,
  ExecutionForm,
  TaskChip,
} from "../components/console";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { NumberInput } from "../components/ui/NumberInput";
import { DatePicker } from "../components/ui/DatePicker";
import { Skeleton } from "../components/ui/Skeleton";
import { EChartsWrapper } from "../components/ui/EChartsWrapper";
import { get } from "../api/client";
import {
  fetchRebalanceHistory,
  fetchRegime,
  fetchSignalContent,
  fetchSignalHistory,
  triggerGenerate,
  triggerNotifyTest,
  triggerRebalance,
} from "../api/signals";
import type { RegimeInfo, SignalFile } from "../api/signals";
import type { TaskState } from "../api/types";
import {
  GenerateSchema,
  NotifyTestSchema,
  RebalanceSchema,
} from "../schemas/signals";
import type {
  GenerateParams,
  NotifyTestParams,
  RebalanceCache,
  RebalanceParams,
} from "../schemas/signals";
import { useTaskTracking } from "../hooks/useTaskTracking";
import { useDryRunPreview } from "../hooks/useDryRunPreview";

type ModelInfo = {
  filename: string;
  size_mb: number;
  modified: string;
  meta: Record<string, unknown>;
};

const TASK_TYPES = ["signal_generate", "rebalance", "notify_test"];
const NOTIFY_CHANNELS = [
  { value: "all", label: "All" },
  { value: "bark", label: "Bark" },
  { value: "pushplus", label: "PushPlus" },
  { value: "dingtalk", label: "DingTalk" },
  { value: "serverchan", label: "ServerChan" },
  { value: "wechat_mp", label: "WeChat MP" },
];
const REBALANCE_CHANNELS = [...NOTIFY_CHANNELS, { value: "none", label: "None" }];

function FieldLabel({ children }: { children: string }) {
  return (
    <p className="mb-1 text-xs font-mono uppercase text-terminal-text-dim">
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
      className="w-full rounded-sm border border-terminal-border bg-terminal-surface px-3 py-2 text-xs font-mono text-terminal-text placeholder:text-terminal-text-dim transition-colors hover:border-terminal-text-dim focus:border-terminal-green focus:outline-none"
    />
  );
}

function TextArea({
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(event) => onChange(event.target.value)}
      rows={rows}
      placeholder={placeholder}
      className="w-full rounded-sm border border-terminal-border bg-terminal-surface px-3 py-2 text-xs font-mono text-terminal-text placeholder:text-terminal-text-dim transition-colors hover:border-terminal-text-dim focus:border-terminal-green focus:outline-none"
    />
  );
}

function Toggle({
  checked,
  onChange,
  label,
  danger,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  danger?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2 text-xs font-mono ${
        danger ? "text-terminal-red" : "text-terminal-text"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className={danger ? "accent-terminal-red" : "accent-terminal-green"}
      />
      {label}
    </label>
  );
}

function AutoSelectFirst({
  value,
  first,
  onSelect,
}: {
  value: string;
  first?: string;
  onSelect: (value: string) => void;
}) {
  useEffect(() => {
    if (!value && first) onSelect(first);
  }, [first, onSelect, value]);

  return null;
}

function PreviewDetails({ preview }: { preview: Record<string, unknown> }) {
  const diff = preview.diff as Record<string, unknown> | undefined;
  const notifyTemplate = preview.notify_template as Record<string, unknown> | undefined;

  if (diff || notifyTemplate) {
    return (
      <div className="space-y-3 text-xs">
        {diff && (
          <div className="grid grid-cols-3 gap-2">
            <Metric label="Buys" value={arraySize(diff.buys)} />
            <Metric label="Sells" value={arraySize(diff.sells)} />
            <Metric label="Net value" value={formatValue(diff.net_value)} />
          </div>
        )}
        {notifyTemplate && (
          <pre className="max-h-52 overflow-auto rounded-sm bg-white p-2 text-xs">
            {JSON.stringify(notifyTemplate, null, 2)}
          </pre>
        )}
      </div>
    );
  }

  return (
    <pre className="max-h-64 overflow-auto text-xs leading-5">
      {JSON.stringify(preview, null, 2)}
    </pre>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-sm border border-slate-200 bg-white px-3 py-2">
      <p className="text-[10px] uppercase text-slate-500">{label}</p>
      <p className="font-mono text-sm text-slate-900">{value}</p>
    </div>
  );
}

function arraySize(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

function formatValue(value: unknown) {
  return typeof value === "number" ? value.toFixed(2) : String(value ?? "-");
}

function formatMoney(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function cacheDate(cache: RebalanceCache) {
  return cache.trade_date || cache.created_at || cache.modified;
}

function matchesResultPath(task: TaskState, cache: RebalanceCache) {
  return task.result_paths?.some((path) => path === cache.path || path.endsWith(`/${cache.filename}`));
}

function useModels() {
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    get<ModelInfo[]>("/models")
      .then(setModels)
      .catch(() => setModels([]));
  }, []);

  return models;
}

function ExecuteTab() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <GenerateAction />
      <RebalanceAction />
      <NotifyTestAction />
    </div>
  );
}

function GenerateAction() {
  const { t } = useTranslation();
  const models = useModels();
  const [configOverride, setConfigOverride] = useState("");
  const preview = useDryRunPreview<GenerateParams, Record<string, unknown>>(triggerGenerate);
  const [error, setError] = useState<string | null>(null);
  const { trackTask } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  const modelOptions = models.map((model) => ({
    value: model.filename,
    label: `${model.filename} (${model.size_mb} MB)`,
  }));

  const buildParams = (params: GenerateParams, dryRun: boolean): GenerateParams =>
    GenerateSchema.parse({
      ...params,
      config_override: configOverride.trim() || null,
      dry_run: dryRun,
    });

  const dryRun = async (params: GenerateParams) => {
    setError(null);
    try {
      const response = await preview.run(buildParams(params, true));
      trackTask(response.task_id);
      return response;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  };

  const submit = async (params: GenerateParams) => {
    setError(null);
    try {
      const response = await triggerGenerate(buildParams(params, false));
      trackTask(response.task_id);
      return response;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  };

  return (
    <Card title={t("console.signals.generate.title")} accent="green">
      <div className="space-y-4">
        <ExecutionForm<GenerateParams>
          pageKey="signals"
          actionKey="signals.generate"
          schema={GenerateSchema}
          defaults={{
            model_path: models[0]?.filename ?? "",
            config_override: null,
            dry_run: true,
          }}
          dryRunDefault
          onDryRun={dryRun}
          onSubmit={submit}
          renderFields={(form) => {
            const isDryRun = form.watch("dry_run");
            const selected = form.watch("model_path");
            return (
              <>
                <AutoSelectFirst
                  value={selected}
                  first={models[0]?.filename}
                  onSelect={(value) => form.setValue("model_path", value, { shouldValidate: true })}
                />
                <div>
                  <FieldLabel>{t("console.signals.fields.modelPath")}</FieldLabel>
                  <Select
                    options={modelOptions}
                    value={form.watch("model_path")}
                    onChange={(value) => form.setValue("model_path", value, { shouldValidate: true })}
                    searchable
                  />
                </div>
                <div>
                  <FieldLabel>{t("console.signals.fields.configOverride")}</FieldLabel>
                  <TextInput
                    value={configOverride}
                    onChange={setConfigOverride}
                    placeholder="config/daily_csi1000.yaml"
                  />
                </div>
                <Toggle
                  checked={isDryRun}
                  onChange={(checked) => form.setValue("dry_run", checked)}
                  label={t("console.signals.fields.dryRun")}
                />
                <button
                  type="submit"
                  data-testid="signals-generate-submit"
                  disabled={!form.watch("model_path")}
                  className="rounded-sm border border-terminal-green px-3 py-1.5 text-xs font-mono text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
                >
                  {isDryRun ? t("console.signals.actions.preview") : t("console.signals.actions.submit")}
                </button>
              </>
            );
          }}
        />
        {error && <p className="text-xs font-mono text-terminal-red">{error}</p>}
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => <PreviewDetails preview={value as Record<string, unknown>} />}
        />
      </div>
    </Card>
  );
}

function RebalanceAction() {
  const { t } = useTranslation();
  const [pendingRealParams, setPendingRealParams] = useState<RebalanceParams | null>(null);
  const preview = useDryRunPreview<RebalanceParams, Record<string, unknown>>(triggerRebalance);
  const [error, setError] = useState<string | null>(null);
  const { trackTask } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  const buildParams = (params: RebalanceParams, dryRun: boolean): RebalanceParams =>
    RebalanceSchema.parse({
      ...params,
      positions: params.positions?.trim() || null,
      position_date: params.position_date || null,
      min_action_value: params.min_action_value ?? 1000,
      dry_run: dryRun,
      confirm_send: dryRun ? false : params.confirm_send,
    });

  const dryRun = async (params: RebalanceParams) => {
    setError(null);
    try {
      const response = await preview.run(buildParams(params, true));
      trackTask(response.task_id);
      return response;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  };

  const submit = async (params: RebalanceParams) => {
    setError(null);
    try {
      const realParams = buildParams(params, false);
      const dryRunResponse = await preview.run({ ...realParams, dry_run: true, confirm_send: false });
      trackTask(dryRunResponse.task_id);
      setPendingRealParams(realParams);
      return null;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  };

  const confirmRebalance = async () => {
    const payload = pendingRealParams;
    if (!payload) return;
    setPendingRealParams(null);
    try {
      const response = await triggerRebalance(payload);
      trackTask(response.task_id);
      window.dispatchEvent(new CustomEvent("console:task-created", { detail: { taskId: response.task_id } }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Card title={t("console.signals.rebalance.title")} accent="amber">
      <div className="space-y-4">
        <ExecutionForm<RebalanceParams>
          pageKey="signals"
          actionKey="signals.rebalance"
          schema={RebalanceSchema}
          defaults={{
            config: "config/daily_csi1000.yaml",
            positions: null,
            position_date: null,
            min_action_value: 1000,
            skip_update: true,
            force: false,
            notify_channel: "none",
            dry_run: true,
            confirm_send: false,
          }}
          dryRunDefault
          onDryRun={dryRun}
          onSubmit={submit}
          destructive
          renderFields={(form) => {
            const isDryRun = form.watch("dry_run");
            const confirmSend = form.watch("confirm_send");
            return (
              <>
                <div>
                  <FieldLabel>{t("console.signals.fields.config")}</FieldLabel>
                  <TextInput
                    value={form.watch("config")}
                    onChange={(value) => form.setValue("config", value, { shouldValidate: true })}
                  />
                </div>
                <div>
                  <FieldLabel>{t("console.signals.fields.positions")}</FieldLabel>
                  <TextArea
                    value={form.watch("positions") ?? ""}
                    onChange={(value) => form.setValue("positions", value || null)}
                    placeholder="SH600000:500,SZ000001:300"
                    rows={2}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <FieldLabel>{t("console.signals.fields.positionDate")}</FieldLabel>
                    <DatePicker
                      value={form.watch("position_date") ?? ""}
                      onChange={(value) => form.setValue("position_date", value || null)}
                    />
                  </div>
                  <div>
                    <FieldLabel>{t("console.signals.fields.minActionValue")}</FieldLabel>
                    <NumberInput
                      value={form.watch("min_action_value")}
                      onChange={(value) => form.setValue("min_action_value", value ?? 1000)}
                      min={0}
                      step={500}
                    />
                  </div>
                </div>
                <div>
                  <FieldLabel>{t("console.signals.fields.notifyChannel")}</FieldLabel>
                  <Select
                    options={REBALANCE_CHANNELS}
                    value={form.watch("notify_channel")}
                    onChange={(value) => form.setValue("notify_channel", value as RebalanceParams["notify_channel"])}
                  />
                </div>
                <div className="flex flex-wrap gap-4">
                  <Toggle
                    checked={isDryRun}
                    onChange={(checked) => {
                      form.setValue("dry_run", checked);
                      if (checked) form.setValue("confirm_send", false);
                    }}
                    label={t("console.signals.fields.dryRun")}
                  />
                  <Toggle
                    checked={form.watch("skip_update")}
                    onChange={(checked) => form.setValue("skip_update", checked)}
                    label={t("console.signals.fields.skipUpdate")}
                  />
                  <Toggle
                    checked={form.watch("force")}
                    onChange={(checked) => form.setValue("force", checked)}
                    label={t("console.signals.fields.force")}
                  />
                  {!isDryRun && (
                    <Toggle
                      checked={confirmSend}
                      onChange={(checked) => form.setValue("confirm_send", checked, { shouldValidate: true })}
                      label={t("console.signals.fields.confirmSend")}
                      danger
                    />
                  )}
                </div>
                <button
                  type="submit"
                  data-testid="signals-rebalance-submit"
                  disabled={!form.watch("config") || (!isDryRun && !confirmSend)}
                  className={`rounded-sm border px-3 py-1.5 text-xs font-mono transition-colors disabled:opacity-30 ${
                    !isDryRun
                      ? "border-terminal-red text-terminal-red hover:bg-terminal-red-glow"
                      : "border-terminal-green text-terminal-green hover:bg-terminal-green-glow"
                  }`}
                >
                  {isDryRun ? t("console.signals.actions.preview") : t("console.signals.actions.rebalanceReal")}
                </button>
              </>
            );
          }}
        />
        {error && <p className="text-xs font-mono text-terminal-red">{error}</p>}
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => <PreviewDetails preview={value as Record<string, unknown>} />}
        />
      </div>
      <ConfirmDialog
        open={!!pendingRealParams}
        titleKey="console.signals.confirm.rebalanceTitle"
        impactSummary={<p>{t("console.signals.confirm.rebalanceImpact")}</p>}
        confirmLabelKey="console.signals.confirm.confirmRealSend"
        destructive
        onCancel={() => setPendingRealParams(null)}
        onConfirm={confirmRebalance}
      />
    </Card>
  );
}

function NotifyTestAction() {
  const { t } = useTranslation();
  const [pendingRealParams, setPendingRealParams] = useState<NotifyTestParams | null>(null);
  const preview = useDryRunPreview<NotifyTestParams, Record<string, unknown>>(triggerNotifyTest);
  const [error, setError] = useState<string | null>(null);
  const { trackTask } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  const buildParams = (params: NotifyTestParams, dryRun: boolean): NotifyTestParams =>
    NotifyTestSchema.parse({
      ...params,
      dry_run: dryRun,
      confirm_send: dryRun ? false : params.confirm_send,
    });

  const dryRun = async (params: NotifyTestParams) => {
    setError(null);
    try {
      const response = await preview.run(buildParams(params, true));
      trackTask(response.task_id);
      return response;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  };

  const submit = async (params: NotifyTestParams) => {
    setError(null);
    try {
      const realParams = buildParams(params, false);
      const dryRunResponse = await preview.run({ ...realParams, dry_run: true, confirm_send: false });
      trackTask(dryRunResponse.task_id);
      setPendingRealParams(realParams);
      return null;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  };

  const confirmNotify = async () => {
    const payload = pendingRealParams;
    if (!payload) return;
    setPendingRealParams(null);
    try {
      const response = await triggerNotifyTest(payload);
      trackTask(response.task_id);
      window.dispatchEvent(new CustomEvent("console:task-created", { detail: { taskId: response.task_id } }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Card title={t("console.signals.notify.title")} accent="red">
      <div className="space-y-4">
        <ExecutionForm<NotifyTestParams>
          pageKey="signals"
          actionKey="signals.notify_test"
          schema={NotifyTestSchema}
          defaults={{
            channel: "bark",
            message: "Dashboard notification test",
            dry_run: true,
            confirm_send: false,
          }}
          dryRunDefault
          onDryRun={dryRun}
          onSubmit={submit}
          destructive
          renderFields={(form) => {
            const isDryRun = form.watch("dry_run");
            const confirmSend = form.watch("confirm_send");
            return (
              <>
                <div>
                  <FieldLabel>{t("console.signals.fields.notifyChannel")}</FieldLabel>
                  <Select
                    options={NOTIFY_CHANNELS}
                    value={form.watch("channel")}
                    onChange={(value) => form.setValue("channel", value as NotifyTestParams["channel"])}
                  />
                </div>
                <div>
                  <FieldLabel>{t("console.signals.fields.message")}</FieldLabel>
                  <TextArea
                    value={form.watch("message")}
                    onChange={(value) => form.setValue("message", value, { shouldValidate: true })}
                    rows={4}
                  />
                </div>
                <div className="flex flex-wrap gap-4">
                  <Toggle
                    checked={isDryRun}
                    onChange={(checked) => {
                      form.setValue("dry_run", checked);
                      if (checked) form.setValue("confirm_send", false);
                    }}
                    label={t("console.signals.fields.dryRun")}
                  />
                  {!isDryRun && (
                    <Toggle
                      checked={confirmSend}
                      onChange={(checked) => form.setValue("confirm_send", checked, { shouldValidate: true })}
                      label={t("console.signals.fields.confirmSend")}
                      danger
                    />
                  )}
                </div>
                <button
                  type="submit"
                  data-testid="signals-notify-submit"
                  disabled={!form.watch("message").trim() || (!isDryRun && !confirmSend)}
                  className={`rounded-sm border px-3 py-1.5 text-xs font-mono transition-colors disabled:opacity-30 ${
                    !isDryRun
                      ? "border-terminal-red text-terminal-red hover:bg-terminal-red-glow"
                      : "border-terminal-green text-terminal-green hover:bg-terminal-green-glow"
                  }`}
                >
                  {isDryRun ? t("console.signals.actions.preview") : t("console.signals.actions.notifyReal")}
                </button>
              </>
            );
          }}
        />
        {error && <p className="text-xs font-mono text-terminal-red">{error}</p>}
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => <PreviewDetails preview={value as Record<string, unknown>} />}
        />
      </div>
      <ConfirmDialog
        open={!!pendingRealParams}
        titleKey="console.signals.confirm.notifyTitle"
        impactSummary={<p>{t("console.signals.confirm.notifyImpact")}</p>}
        confirmLabelKey="console.signals.confirm.confirmRealSend"
        destructive
        onCancel={() => setPendingRealParams(null)}
        onConfirm={confirmNotify}
      />
    </Card>
  );
}

function HistoryTab() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<SignalFile[]>([]);
  const [caches, setCaches] = useState<RebalanceCache[]>([]);
  const [loadingCaches, setLoadingCaches] = useState(true);
  const { tasks, refresh } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  useEffect(() => {
    fetchSignalHistory()
      .then(setFiles)
      .catch(() => setFiles([]));
    fetchRebalanceHistory()
      .then(setCaches)
      .catch(() => setCaches([]))
      .finally(() => setLoadingCaches(false));
  }, []);

  return (
    <div className="space-y-4">
      <Card
        title={t("console.signals.history.tasks")}
        actions={
          <button type="button" onClick={refresh} className="text-xs text-terminal-green">
            {t("console.signals.actions.refresh")}
          </button>
        }
      >
        <div className="overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-terminal-text-dim">
              <tr>
                <th className="px-2 py-2">{t("console.signals.history.task")}</th>
                <th className="px-2 py-2">{t("console.signals.history.created")}</th>
                <th className="px-2 py-2">{t("console.signals.history.realSend")}</th>
                <th className="px-2 py-2">{t("console.signals.history.results")}</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.task_id} className="border-t border-terminal-border-dim">
                  <td className="px-2 py-2"><TaskChip task={task} /></td>
                  <td className="px-2 py-2 font-mono text-terminal-text-dim">{task.created_at}</td>
                  <td className="px-2 py-2">{realSendLabel(task)}</td>
                  <td className="px-2 py-2 font-mono text-terminal-text-dim">
                    {task.result_paths?.join(", ") || "-"}
                  </td>
                </tr>
              ))}
              {tasks.length === 0 && (
                <tr>
                  <td className="px-2 py-4 text-terminal-text-dim" colSpan={4}>
                    {t("console.signals.history.noTasks")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
      <RebalanceCacheHistory caches={caches} tasks={tasks} loading={loadingCaches} />
      <SignalFileList files={files} />
    </div>
  );
}

function realSendLabel(task: TaskState) {
  if (task.task_type === "rebalance") return "yes";
  if (task.task_type === "rebalance_dry_run") return "no";
  return "-";
}

function SignalFileList({ files }: { files: SignalFile[] }) {
  const { t } = useTranslation();
  return (
    <Card title={t("console.signals.history.files")}>
      {files.length === 0 ? (
        <p className="text-xs font-mono text-terminal-text-dim">
          {t("console.signals.history.noFiles")}
        </p>
      ) : (
        <div className="space-y-2">
          {files.map((file) => (
            <div
              key={file.filename}
              className="flex items-center justify-between rounded-sm border border-terminal-border-dim px-3 py-2 text-xs"
            >
              <span className="font-mono text-terminal-green">{file.filename}</span>
              <span className="text-terminal-text-dim">
                {file.size_kb} KB - {new Date(file.modified).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function RebalanceCacheHistory({
  caches,
  tasks,
  loading,
}: {
  caches: RebalanceCache[];
  tasks: TaskState[];
  loading: boolean;
}) {
  const { t } = useTranslation();
  const strategyOptions = useMemo(() => {
    const groups = new Map<string, { signature: string; label: string; count: number; latest: string }>();
    caches.forEach((cache) => {
      const existing = groups.get(cache.strategy_signature);
      const date = cacheDate(cache);
      if (existing) {
        existing.count += 1;
        if (date > existing.latest) existing.latest = date;
      } else {
        groups.set(cache.strategy_signature, {
          signature: cache.strategy_signature,
          label: cache.strategy_label,
          count: 1,
          latest: date,
        });
      }
    });
    return Array.from(groups.values()).sort((a, b) => b.latest.localeCompare(a.latest));
  }, [caches]);
  const [selectedSignature, setSelectedSignature] = useState("");

  useEffect(() => {
    if (strategyOptions.length === 0) {
      setSelectedSignature("");
      return;
    }
    if (!strategyOptions.some((option) => option.signature === selectedSignature)) {
      setSelectedSignature(strategyOptions[0].signature);
    }
  }, [selectedSignature, strategyOptions]);

  const selectedCaches = useMemo(
    () => caches.filter((cache) => cache.strategy_signature === selectedSignature),
    [caches, selectedSignature],
  );
  const latest = selectedCaches[0];
  const selectedOption = strategyOptions.find((option) => option.signature === selectedSignature);

  return (
    <Card title={t("console.signals.history.rebalanceCaches")} accent="amber">
      {loading ? (
        <Skeleton className="h-56 w-full" />
      ) : caches.length === 0 ? (
        <p className="text-xs font-mono text-terminal-text-dim">
          {t("console.signals.history.noRebalanceCaches")}
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_220px]">
            <div>
              <FieldLabel>{t("console.signals.history.strategySelector")}</FieldLabel>
              <Select
                options={strategyOptions.map((option) => ({
                  value: option.signature,
                  label: `${option.label} (${option.count})`,
                }))}
                value={selectedSignature}
                onChange={setSelectedSignature}
              />
            </div>
            <div className="rounded-sm border border-terminal-border-dim px-3 py-2 text-xs">
              <p className="font-mono uppercase text-terminal-text-dim">{t("console.signals.history.trackedRuns")}</p>
              <p className="mt-1 font-mono text-lg text-terminal-text-bright">{selectedOption?.count ?? 0}</p>
            </div>
          </div>
          <p className="text-xs text-terminal-text-dim">
            {t("console.signals.history.strategySelectorHint")}
          </p>
          <RebalanceCharts caches={selectedCaches} />
          {latest && <TopHoldingsPanel cache={latest} />}
          <div className="overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-terminal-text-dim">
                <tr>
                  <th className="px-2 py-2">{t("console.signals.history.tradeDate")}</th>
                  <th className="px-2 py-2">{t("console.signals.history.strategy")}</th>
                  <th className="px-2 py-2">{t("console.signals.history.portfolioValue")}</th>
                  <th className="px-2 py-2">{t("console.signals.history.targetValue")}</th>
                  <th className="px-2 py-2">{t("console.signals.history.holdings")}</th>
                  <th className="px-2 py-2">{t("console.signals.history.actions")}</th>
                  <th className="px-2 py-2">{t("console.signals.history.linkedTask")}</th>
                </tr>
              </thead>
              <tbody>
                {selectedCaches.map((cache) => {
                  const linkedTask = tasks.find((task) => matchesResultPath(task, cache));
                  return (
                    <tr key={cache.filename} className="border-t border-terminal-border-dim">
                      <td className="px-2 py-2 font-mono text-terminal-green">
                        {cache.trade_date ?? cache.filename}
                        {cache.mock && <span className="ml-2 text-terminal-text-dim">MOCK</span>}
                      </td>
                      <td className="px-2 py-2 font-mono text-terminal-text-dim">
                        {String(cache.strategy.market ?? "-")} / topk={String(cache.strategy.topk ?? "-")}
                      </td>
                      <td className="px-2 py-2 font-mono">{formatMoney(cache.portfolio_value)}</td>
                      <td className="px-2 py-2 font-mono">{formatMoney(cache.target_value)}</td>
                      <td className="px-2 py-2 font-mono">{cache.holdings_count}</td>
                      <td className="px-2 py-2 font-mono text-terminal-text-dim">
                        B {cache.action_summary.buy_count} / {formatMoney(cache.action_summary.buy_amount)}
                        <span className="mx-1">|</span>
                        S {cache.action_summary.sell_count} / {formatMoney(cache.action_summary.sell_amount)}
                      </td>
                      <td className="px-2 py-2">
                        {linkedTask ? <TaskChip task={linkedTask} /> : <span className="text-terminal-text-dim">-</span>}
                      </td>
                    </tr>
                  );
                })}
                {selectedCaches.length === 0 && (
                  <tr>
                    <td className="px-2 py-4 text-terminal-text-dim" colSpan={7}>
                      {t("console.signals.history.noMatchingStrategy")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

function RebalanceCharts({ caches }: { caches: RebalanceCache[] }) {
  const { t } = useTranslation();
  const chronological = useMemo(
    () => [...caches].sort((a, b) => cacheDate(a).localeCompare(cacheDate(b))),
    [caches],
  );
  const dates = chronological.map((cache) => cache.trade_date ?? cache.filename.replace("rebalance_", "").replace(".json", ""));

  const valueOption = useMemo<Record<string, unknown>>(
    () => ({
      backgroundColor: "transparent",
      color: ["#4ade80", "#38bdf8"],
      tooltip: { trigger: "axis" },
      legend: { textStyle: { color: "#94a3b8" } },
      grid: { left: 48, right: 16, top: 32, bottom: 28 },
      xAxis: { type: "category", data: dates, axisLabel: { color: "#94a3b8" } },
      yAxis: { type: "value", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#1f2937" } } },
      series: [
        {
          name: t("console.signals.history.portfolioValue"),
          type: "line",
          smooth: true,
          data: chronological.map((cache) => cache.portfolio_value),
        },
        {
          name: t("console.signals.history.targetValue"),
          type: "line",
          smooth: true,
          data: chronological.map((cache) => cache.target_value),
        },
      ],
    }),
    [chronological, dates, t],
  );

  const activityOption = useMemo<Record<string, unknown>>(
    () => ({
      backgroundColor: "transparent",
      color: ["#f59e0b", "#ef4444", "#a78bfa"],
      tooltip: { trigger: "axis" },
      legend: { textStyle: { color: "#94a3b8" } },
      grid: { left: 48, right: 16, top: 32, bottom: 28 },
      xAxis: { type: "category", data: dates, axisLabel: { color: "#94a3b8" } },
      yAxis: { type: "value", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#1f2937" } } },
      series: [
        {
          name: t("console.signals.history.holdings"),
          type: "line",
          smooth: true,
          data: chronological.map((cache) => cache.holdings_count),
        },
        {
          name: t("console.signals.history.buyAmount"),
          type: "bar",
          data: chronological.map((cache) => cache.action_summary.buy_amount),
        },
        {
          name: t("console.signals.history.sellAmount"),
          type: "bar",
          data: chronological.map((cache) => cache.action_summary.sell_amount),
        },
      ],
    }),
    [chronological, dates, t],
  );

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div className="rounded-sm border border-terminal-border-dim p-3">
        <EChartsWrapper option={valueOption} height={280} />
      </div>
      <div className="rounded-sm border border-terminal-border-dim p-3">
        <EChartsWrapper option={activityOption} height={280} />
      </div>
    </div>
  );
}

function TopHoldingsPanel({ cache }: { cache: RebalanceCache }) {
  const { t } = useTranslation();
  if (cache.top_holdings.length === 0) {
    return (
      <p className="text-xs font-mono text-terminal-text-dim">
        {t("console.signals.history.noHoldings")}
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <div className="rounded-sm border border-terminal-border-dim p-3">
        <p className="mb-3 text-xs font-mono uppercase text-terminal-text-dim">
          {t("console.signals.history.topHoldings")} ({cache.trade_date ?? cache.filename})
        </p>
        <div className="space-y-2">
          {cache.top_holdings.map((holding) => (
            <div key={holding.instrument} className="grid grid-cols-[110px_1fr_70px] items-center gap-2 text-xs">
              <span className="font-mono text-terminal-green">{holding.instrument}</span>
              <div className="h-2 overflow-hidden rounded-sm bg-terminal-border-dim">
                <div
                  className="h-full bg-terminal-green"
                  style={{ width: `${Math.max(2, (holding.weight ?? 0) * 100)}%` }}
                />
              </div>
              <span className="text-right font-mono text-terminal-text-dim">{formatPercent(holding.weight)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-sm border border-terminal-border-dim p-3">
        <p className="mb-3 text-xs font-mono uppercase text-terminal-text-dim">
          {t("console.signals.history.actionSummary")}
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Metric label={t("console.signals.history.buyAmount")} value={formatMoney(cache.action_summary.buy_amount)} />
          <Metric label={t("console.signals.history.sellAmount")} value={formatMoney(cache.action_summary.sell_amount)} />
          <Metric label={t("console.signals.history.buyCount")} value={cache.action_summary.buy_count} />
          <Metric label={t("console.signals.history.sellCount")} value={cache.action_summary.sell_count} />
        </div>
      </div>
    </div>
  );
}

function InspectTab() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <RegimeCard />
      <SignalFileInspector />
    </div>
  );
}

function RegimeCard() {
  const { t } = useTranslation();
  const [regime, setRegime] = useState<RegimeInfo | null>(null);

  useEffect(() => {
    fetchRegime()
      .then(setRegime)
      .catch((err) => setRegime({ enabled: false, regime: null, label: null, error: String(err) }));
  }, []);

  return (
    <Card title={t("console.signals.inspect.regime")}>
      {regime ? (
        <div className="space-y-2 text-xs font-mono">
          <p className={regime.enabled ? "text-terminal-green" : "text-terminal-text-dim"}>
            {regime.enabled ? t("console.signals.inspect.enabled") : t("console.signals.inspect.disabled")}
          </p>
          <p className="text-terminal-text">{regime.label ?? `Regime ${regime.regime ?? "-"}`}</p>
          {regime.error && <p className="text-terminal-red">{regime.error}</p>}
        </div>
      ) : (
        <Skeleton className="h-6 w-48" />
      )}
    </Card>
  );
}

function SignalFileInspector() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<SignalFile[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchSignalHistory()
      .then((items) => {
        setFiles(items);
        if (items.length > 0) setSelected(items[0].filename);
      })
      .catch(() => setFiles([]));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    fetchSignalContent(selected)
      .then((res) => setContent(res.content))
      .catch(() => setContent(""))
      .finally(() => setLoading(false));
  }, [selected]);

  return (
    <Card title={t("console.signals.inspect.file")}>
      <div className="space-y-3">
        <Select
          options={files.map((file) => ({ value: file.filename, label: file.filename }))}
          value={selected}
          onChange={setSelected}
        />
        {loading && <Skeleton className="h-32 w-full" />}
        {!loading && content && (
          <pre className="max-h-[460px] overflow-auto whitespace-pre-wrap rounded-sm border border-terminal-border bg-terminal-surface p-4 text-xs font-mono text-terminal-text">
            {content}
          </pre>
        )}
        {!loading && !content && (
          <p className="text-xs font-mono text-terminal-text-dim">
            {t("console.signals.inspect.noFile")}
          </p>
        )}
      </div>
    </Card>
  );
}

function OverviewTab() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<SignalFile[]>([]);
  const [caches, setCaches] = useState<RebalanceCache[]>([]);

  useEffect(() => {
    fetchSignalHistory()
      .then(setFiles)
      .catch(() => setFiles([]));
    fetchRebalanceHistory()
      .then(setCaches)
      .catch(() => setCaches([]));
  }, []);

  const recentCount = useMemo(() => {
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return files.filter((file) => new Date(file.modified).getTime() >= cutoff).length;
  }, [files]);

  const latestCache = caches[0];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
      <Card title={t("console.signals.overview.recentSignals")} accent="green">
        <p className="font-mono text-3xl text-terminal-text-bright">{recentCount}</p>
      </Card>
      <Card title={t("console.signals.overview.totalFiles")}>
        <p className="font-mono text-3xl text-terminal-text-bright">{files.length}</p>
      </Card>
      <Card title={t("console.signals.overview.rebalanceCaches")} accent="amber">
        <p className="font-mono text-3xl text-terminal-text-bright">{caches.length}</p>
      </Card>
      <Card title={t("console.signals.overview.latestTargetValue")}>
        <p className="font-mono text-3xl text-terminal-text-bright">
          {formatMoney(latestCache?.target_value ?? latestCache?.portfolio_value)}
        </p>
      </Card>
      <RegimeCard />
    </div>
  );
}

export function SignalsPage() {
  return (
    <ConsolePageLayout
      pageKey="signals"
      titleKey="console.signals.title"
      taskTypeFilter={TASK_TYPES}
      tabs={{
        overview: <OverviewTab />,
        execute: <ExecuteTab />,
        history: <HistoryTab />,
        inspect: <InspectTab />,
      }}
    />
  );
}
