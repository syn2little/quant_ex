import { useMemo, useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { useTranslation } from "react-i18next";
import {
  ConfirmDialog,
  DryRunPreview,
  ExecutionForm,
} from "../../components/console";
import { Card } from "../../components/ui/Card";
import { NumberInput } from "../../components/ui/NumberInput";
import { Select } from "../../components/ui/Select";
import { TaskStatus } from "../../components/ui/TaskStatus";
import { useDryRunPreview } from "../../hooks/useDryRunPreview";
import { WFVSchema, type WFVParams } from "../../schemas/backtest";
import { triggerWFV, type BacktestPreview } from "../../api/backtest";

const MARKET_OPTIONS = [
  { value: "csi300", label: "CSI 300" },
  { value: "csi500", label: "CSI 500" },
  { value: "csi800", label: "CSI 800" },
  { value: "csi1000", label: "CSI 1000" },
];

const DEFAULT_WFV: WFVParams = {
  train_universes: ["csi300"],
  eval_market: "csi300",
  rolling_window_days: 252,
  step_days: 63,
  topk_list: [5, 15, 20],
  n_drop_list: [1, 3],
  hold_thresh_list: [5, 8, 10],
  rank_metric: "information_ratio",
  dry_run: true,
};

function parseNumberList(value: string): number[] {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function parseStringList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

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
      className="w-full rounded-sm border border-terminal-border bg-terminal-surface px-3 py-2 font-mono text-xs text-terminal-text placeholder:text-terminal-text-dim transition-colors hover:border-terminal-text-dim focus:border-terminal-green focus:outline-none"
    />
  );
}

function PreviewBody({ preview }: { preview: unknown }) {
  const typed = preview as BacktestPreview;
  const candidateCount = Number(typed.candidate_count ?? 0);
  const isLarge = candidateCount > 200;
  return (
    <div className="space-y-2 font-mono text-xs text-slate-700">
      <div className={isLarge ? "font-semibold text-red-700" : "font-semibold"}>
        candidate_count: {candidateCount}
      </div>
      <div>window_count: {String(typed.window_count ?? "-")}</div>
      <div>total_runs: {String(typed.total_runs ?? "-")}</div>
      <div>estimated_minutes: {String(typed.estimated_minutes ?? "-")}</div>
      <div>rank_metric: information_ratio</div>
      {isLarge && (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-red-700">
          Candidate count exceeds 200. Review the WFV grid before launch.
        </div>
      )}
    </div>
  );
}

function WFVFields({
  form,
  universesText,
  setUniversesText,
  topkText,
  setTopkText,
  nDropText,
  setNDropText,
  holdText,
  setHoldText,
}: {
  form: UseFormReturn<WFVParams>;
  universesText: string;
  setUniversesText: (value: string) => void;
  topkText: string;
  setTopkText: (value: string) => void;
  nDropText: string;
  setNDropText: (value: string) => void;
  holdText: string;
  setHoldText: (value: string) => void;
}) {
  const { t } = useTranslation();
  const values = form.watch();
  const candidateCount =
    values.topk_list.length * values.n_drop_list.length * values.hold_thresh_list.length;
  const windowCount = Math.max(1, Math.floor(values.rolling_window_days / Math.max(1, values.step_days)));

  const setList = (
    key: "topk_list" | "n_drop_list" | "hold_thresh_list",
    value: string,
    setter: (value: string) => void,
  ) => {
    setter(value);
    form.setValue(key, parseNumberList(value), { shouldDirty: true, shouldValidate: true });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <FieldLabel>{t("console.backtest.trainUniverses")}</FieldLabel>
          <TextInput
            value={universesText}
            onChange={(value) => {
              setUniversesText(value);
              form.setValue("train_universes", parseStringList(value), {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
            placeholder="csi300,csi800"
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.evalMarket")}</FieldLabel>
          <Select
            options={MARKET_OPTIONS}
            value={values.eval_market}
            onChange={(value) =>
              form.setValue("eval_market", value, {
                shouldDirty: true,
                shouldValidate: true,
              })
            }
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <FieldLabel>{t("console.backtest.topkList")}</FieldLabel>
          <TextInput
            value={topkText}
            onChange={(value) => setList("topk_list", value, setTopkText)}
            placeholder="5,15,20"
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.nDropList")}</FieldLabel>
          <TextInput
            value={nDropText}
            onChange={(value) => setList("n_drop_list", value, setNDropText)}
            placeholder="1,3"
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.holdThreshList")}</FieldLabel>
          <TextInput
            value={holdText}
            onChange={(value) => setList("hold_thresh_list", value, setHoldText)}
            placeholder="5,8,10"
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <FieldLabel>{t("console.backtest.rollingWindowDays")}</FieldLabel>
          <NumberInput
            value={values.rolling_window_days}
            onChange={(value) => form.setValue("rolling_window_days", value ?? 252)}
            min={1}
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.stepDays")}</FieldLabel>
          <NumberInput
            value={values.step_days}
            onChange={(value) => form.setValue("step_days", value ?? 63)}
            min={1}
          />
        </div>
      </div>
      <div className="rounded-sm border border-terminal-border px-3 py-2 font-mono text-xs text-terminal-text">
        {t("console.backtest.rankMetricLocked")}: information_ratio
      </div>
      <div
        className={`rounded-sm border px-3 py-2 font-mono text-xs ${
          candidateCount > 200
            ? "border-terminal-red text-terminal-red"
            : "border-terminal-border text-terminal-text"
        }`}
      >
        {t("console.backtest.candidateCount")}: {candidateCount} |{" "}
        {t("console.backtest.windowCount")}: {windowCount}
        {candidateCount > 200 ? ` - ${t("console.backtest.largeCandidateWarning")}` : ""}
      </div>
      <label className="flex items-center gap-2 font-mono text-xs text-terminal-text">
        <input type="checkbox" className="accent-terminal-green" {...form.register("dry_run")} />
        {t("console.common.dryRun")}
      </label>
      <button
        type="submit"
        className="rounded-sm border border-terminal-green px-3 py-1.5 font-mono text-xs text-terminal-green transition-colors hover:bg-terminal-green-glow"
      >
        {values.dry_run ? t("console.backtest.previewWfv") : t("console.backtest.runWfv")}
      </button>
    </div>
  );
}

export function WFVConsole() {
  const { t } = useTranslation();
  const preview = useDryRunPreview<WFVParams, BacktestPreview>((params) =>
    triggerWFV({ ...params, rank_metric: "information_ratio", dry_run: true }),
  );
  const [taskId, setTaskId] = useState<string | null>(null);
  const [confirmParams, setConfirmParams] = useState<WFVParams | null>(null);
  const [universesText, setUniversesText] = useState("csi300");
  const [topkText, setTopkText] = useState("5,15,20");
  const [nDropText, setNDropText] = useState("1,3");
  const [holdText, setHoldText] = useState("5,8,10");

  const impact = useMemo(() => {
    if (!confirmParams) return null;
    const count =
      confirmParams.topk_list.length *
      confirmParams.n_drop_list.length *
      confirmParams.hold_thresh_list.length;
    const windows = Math.max(
      1,
      Math.floor(confirmParams.rolling_window_days / Math.max(1, confirmParams.step_days)),
    );
    return (
      <div className="space-y-1">
        <div>candidate_count: {count}</div>
        <div>window_count: {windows}</div>
        <div>rank_metric: information_ratio</div>
      </div>
    );
  }, [confirmParams]);

  return (
    <Card title={t("console.backtest.wfvTitle")}>
      <ExecutionForm<WFVParams>
        pageKey="backtest"
        actionKey="backtest.walk_forward"
        schema={WFVSchema}
        defaults={DEFAULT_WFV}
        dryRunDefault
        onDryRun={preview.run}
        onSubmit={async (params) => {
          setConfirmParams({ ...params, rank_metric: "information_ratio", dry_run: false });
          return { task_id: "pending-confirmation" };
        }}
        renderFields={(form) => (
          <WFVFields
            form={form}
            universesText={universesText}
            setUniversesText={setUniversesText}
            topkText={topkText}
            setTopkText={setTopkText}
            nDropText={nDropText}
            setNDropText={setNDropText}
            holdText={holdText}
            setHoldText={setHoldText}
          />
        )}
      />
      <div className="mt-4">
        <DryRunPreview
          loading={preview.loading}
          error={preview.error}
          preview={preview.preview}
          renderPreview={(value) => <PreviewBody preview={value} />}
        />
      </div>
      <TaskStatus taskId={taskId} />
      <ConfirmDialog
        open={!!confirmParams}
        titleKey="console.backtest.confirmWfv"
        impactSummary={impact}
        confirmLabelKey="console.backtest.runWfv"
        onCancel={() => setConfirmParams(null)}
        onConfirm={async () => {
          if (!confirmParams) return;
          const result = await triggerWFV({
            ...confirmParams,
            rank_metric: "information_ratio",
            dry_run: false,
          });
          setTaskId(result.task_id);
          setConfirmParams(null);
        }}
      />
    </Card>
  );
}
