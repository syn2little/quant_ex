import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ConfirmDialog,
  ConsolePageLayout,
  DryRunPreview,
  TaskChip,
} from "../components/console";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { NumberInput } from "../components/ui/NumberInput";
import { DatePicker } from "../components/ui/DatePicker";
import { Skeleton } from "../components/ui/Skeleton";
import { get } from "../api/client";
import {
  fetchRegime,
  fetchSignalContent,
  fetchSignalHistory,
  triggerGenerate,
  triggerNotifyTest,
  triggerRebalance,
} from "../api/signals";
import type { RegimeInfo, SignalFile } from "../api/signals";
import type { TaskTrigger } from "../api/tasks";
import type { TaskState } from "../api/types";
import {
  GenerateSchema,
  NotifyTestSchema,
  RebalanceSchema,
} from "../schemas/signals";
import type {
  GenerateParams,
  NotifyTestParams,
  RebalanceParams,
} from "../schemas/signals";
import { useTaskTracking } from "../hooks/useTaskTracking";

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

function ActionButton({
  children,
  disabled,
  onClick,
  danger,
  testId,
}: {
  children: string;
  disabled?: boolean;
  onClick: () => void;
  danger?: boolean;
  testId?: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-sm border px-3 py-1.5 text-xs font-mono transition-colors disabled:opacity-30 ${
        danger
          ? "border-terminal-red text-terminal-red hover:bg-terminal-red-glow"
          : "border-terminal-green text-terminal-green hover:bg-terminal-green-glow"
      }`}
    >
      {children}
    </button>
  );
}

function PreviewBlock({ result }: { result: TaskTrigger<Record<string, unknown>> | null }) {
  return (
    <DryRunPreview
      preview={result?.preview ?? null}
      renderPreview={(preview) => <PreviewDetails preview={preview as Record<string, unknown>} />}
    />
  );
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
  const [modelPath, setModelPath] = useState("");
  const [configOverride, setConfigOverride] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [result, setResult] = useState<TaskTrigger<Record<string, unknown>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { trackTask } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  useEffect(() => {
    if (!modelPath && models.length > 0) setModelPath(models[0].filename);
  }, [modelPath, models]);

  const modelOptions = models.map((model) => ({
    value: model.filename,
    label: `${model.filename} (${model.size_mb} MB)`,
  }));

  const submit = async () => {
    setError(null);
    const params: GenerateParams = GenerateSchema.parse({
      model_path: modelPath,
      config_override: configOverride.trim() || null,
      dry_run: dryRun,
    });
    const response = await triggerGenerate(params);
    setResult(response);
    trackTask(response.task_id);
  };

  return (
    <Card title={t("console.signals.generate.title")} accent="green">
      <div className="space-y-4">
        <div>
          <FieldLabel>{t("console.signals.fields.modelPath")}</FieldLabel>
          <Select options={modelOptions} value={modelPath} onChange={setModelPath} searchable />
        </div>
        <div>
          <FieldLabel>{t("console.signals.fields.configOverride")}</FieldLabel>
          <TextInput
            value={configOverride}
            onChange={setConfigOverride}
            placeholder="config/daily_csi1000.yaml"
          />
        </div>
        <Toggle checked={dryRun} onChange={setDryRun} label={t("console.signals.fields.dryRun")} />
        <ActionButton
          onClick={() => submit().catch((err) => setError(String(err)))}
          disabled={!modelPath}
          testId="signals-generate-submit"
        >
          {dryRun ? t("console.signals.actions.preview") : t("console.signals.actions.submit")}
        </ActionButton>
        {error && <p className="text-xs font-mono text-terminal-red">{error}</p>}
        <PreviewBlock result={result} />
      </div>
    </Card>
  );
}

function RebalanceAction() {
  const { t } = useTranslation();
  const [config, setConfig] = useState("config/daily_csi1000.yaml");
  const [positions, setPositions] = useState("");
  const [positionDate, setPositionDate] = useState("");
  const [minActionValue, setMinActionValue] = useState<number | undefined>(1000);
  const [skipUpdate, setSkipUpdate] = useState(true);
  const [force, setForce] = useState(false);
  const [notifyChannel, setNotifyChannel] = useState("none");
  const [dryRun, setDryRun] = useState(true);
  const [confirmSend, setConfirmSend] = useState(false);
  const [pendingRealParams, setPendingRealParams] = useState<RebalanceParams | null>(null);
  const [result, setResult] = useState<TaskTrigger<Record<string, unknown>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { trackTask } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  const params = (): RebalanceParams =>
    RebalanceSchema.parse({
      config,
      positions: positions.trim() || null,
      position_date: positionDate || null,
      min_action_value: minActionValue ?? 1000,
      skip_update: skipUpdate,
      force,
      notify_channel: notifyChannel,
      dry_run: dryRun,
      confirm_send: dryRun ? false : confirmSend,
    });

  const submit = async (payload: RebalanceParams) => {
    const response = await triggerRebalance(payload);
    setResult(response);
    trackTask(response.task_id);
  };

  const handleClick = () => {
    setError(null);
    try {
      const payload = params();
      if (!payload.dry_run) {
        setPendingRealParams(payload);
        return;
      }
      submit(payload).catch((err) => setError(String(err)));
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <Card title={t("console.signals.rebalance.title")} accent="amber">
      <div className="space-y-4">
        <div>
          <FieldLabel>{t("console.signals.fields.config")}</FieldLabel>
          <TextInput value={config} onChange={setConfig} />
        </div>
        <div>
          <FieldLabel>{t("console.signals.fields.positions")}</FieldLabel>
          <TextArea
            value={positions}
            onChange={setPositions}
            placeholder="SH600000:500,SZ000001:300"
            rows={2}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <FieldLabel>{t("console.signals.fields.positionDate")}</FieldLabel>
            <DatePicker value={positionDate} onChange={setPositionDate} />
          </div>
          <div>
            <FieldLabel>{t("console.signals.fields.minActionValue")}</FieldLabel>
            <NumberInput
              value={minActionValue}
              onChange={setMinActionValue}
              min={0}
              step={500}
            />
          </div>
        </div>
        <div>
          <FieldLabel>{t("console.signals.fields.notifyChannel")}</FieldLabel>
          <Select options={REBALANCE_CHANNELS} value={notifyChannel} onChange={setNotifyChannel} />
        </div>
        <div className="flex flex-wrap gap-4">
          <Toggle
            checked={dryRun}
            onChange={(checked) => {
              setDryRun(checked);
              if (checked) setConfirmSend(false);
            }}
            label={t("console.signals.fields.dryRun")}
          />
          <Toggle checked={skipUpdate} onChange={setSkipUpdate} label={t("console.signals.fields.skipUpdate")} />
          <Toggle checked={force} onChange={setForce} label={t("console.signals.fields.force")} />
          {!dryRun && (
            <Toggle
              checked={confirmSend}
              onChange={setConfirmSend}
              label={t("console.signals.fields.confirmSend")}
              danger
            />
          )}
        </div>
        <ActionButton
          onClick={handleClick}
          disabled={!config || (!dryRun && !confirmSend)}
          danger={!dryRun}
          testId="signals-rebalance-submit"
        >
          {dryRun ? t("console.signals.actions.preview") : t("console.signals.actions.rebalanceReal")}
        </ActionButton>
        {error && <p className="text-xs font-mono text-terminal-red">{error}</p>}
        <PreviewBlock result={result} />
      </div>
      <ConfirmDialog
        open={!!pendingRealParams}
        titleKey={t("console.signals.confirm.rebalanceTitle")}
        impactSummary={<p>{t("console.signals.confirm.rebalanceImpact")}</p>}
        confirmLabelKey={t("console.signals.confirm.confirmRealSend")}
        destructive
        onCancel={() => setPendingRealParams(null)}
        onConfirm={() => {
          const payload = pendingRealParams;
          setPendingRealParams(null);
          if (payload) submit(payload).catch((err) => setError(String(err)));
        }}
      />
    </Card>
  );
}

function NotifyTestAction() {
  const { t } = useTranslation();
  const [channel, setChannel] = useState("bark");
  const [message, setMessage] = useState("Dashboard notification test");
  const [dryRun, setDryRun] = useState(true);
  const [confirmSend, setConfirmSend] = useState(false);
  const [pendingRealParams, setPendingRealParams] = useState<NotifyTestParams | null>(null);
  const [result, setResult] = useState<TaskTrigger<Record<string, unknown>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { trackTask } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  const params = (): NotifyTestParams =>
    NotifyTestSchema.parse({
      channel,
      message,
      dry_run: dryRun,
      confirm_send: dryRun ? false : confirmSend,
    });

  const submit = async (payload: NotifyTestParams) => {
    const response = await triggerNotifyTest(payload);
    setResult(response);
    trackTask(response.task_id);
  };

  const handleClick = () => {
    setError(null);
    try {
      const payload = params();
      if (!payload.dry_run) {
        setPendingRealParams(payload);
        return;
      }
      submit(payload).catch((err) => setError(String(err)));
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <Card title={t("console.signals.notify.title")} accent="red">
      <div className="space-y-4">
        <div>
          <FieldLabel>{t("console.signals.fields.notifyChannel")}</FieldLabel>
          <Select options={NOTIFY_CHANNELS} value={channel} onChange={setChannel} />
        </div>
        <div>
          <FieldLabel>{t("console.signals.fields.message")}</FieldLabel>
          <TextArea value={message} onChange={setMessage} rows={4} />
        </div>
        <div className="flex flex-wrap gap-4">
          <Toggle
            checked={dryRun}
            onChange={(checked) => {
              setDryRun(checked);
              if (checked) setConfirmSend(false);
            }}
            label={t("console.signals.fields.dryRun")}
          />
          {!dryRun && (
            <Toggle
              checked={confirmSend}
              onChange={setConfirmSend}
              label={t("console.signals.fields.confirmSend")}
              danger
            />
          )}
        </div>
        <ActionButton
          onClick={handleClick}
          disabled={!message.trim() || (!dryRun && !confirmSend)}
          danger={!dryRun}
          testId="signals-notify-submit"
        >
          {dryRun ? t("console.signals.actions.preview") : t("console.signals.actions.notifyReal")}
        </ActionButton>
        {error && <p className="text-xs font-mono text-terminal-red">{error}</p>}
        <PreviewBlock result={result} />
      </div>
      <ConfirmDialog
        open={!!pendingRealParams}
        titleKey={t("console.signals.confirm.notifyTitle")}
        impactSummary={<p>{t("console.signals.confirm.notifyImpact")}</p>}
        confirmLabelKey={t("console.signals.confirm.confirmRealSend")}
        destructive
        onCancel={() => setPendingRealParams(null)}
        onConfirm={() => {
          const payload = pendingRealParams;
          setPendingRealParams(null);
          if (payload) submit(payload).catch((err) => setError(String(err)));
        }}
      />
    </Card>
  );
}

function HistoryTab() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<SignalFile[]>([]);
  const { tasks, refresh } = useTaskTracking({ pageKey: "signals", taskTypeFilter: TASK_TYPES });

  useEffect(() => {
    fetchSignalHistory()
      .then(setFiles)
      .catch(() => setFiles([]));
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

  useEffect(() => {
    fetchSignalHistory()
      .then(setFiles)
      .catch(() => setFiles([]));
  }, []);

  const recentCount = useMemo(() => {
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return files.filter((file) => new Date(file.modified).getTime() >= cutoff).length;
  }, [files]);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <Card title={t("console.signals.overview.recentSignals")} accent="green">
        <p className="font-mono text-3xl text-terminal-text-bright">{recentCount}</p>
      </Card>
      <Card title={t("console.signals.overview.totalFiles")}>
        <p className="font-mono text-3xl text-terminal-text-bright">{files.length}</p>
      </Card>
      <RegimeCard />
    </div>
  );
}

export function SignalsPage() {
  const { t } = useTranslation();

  return (
    <ConsolePageLayout
      pageKey="signals"
      titleKey={t("console.signals.title")}
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
