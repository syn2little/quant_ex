import { useMemo, useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { useTranslation } from "react-i18next";
import {
  ConfirmDialog,
  DryRunPreview,
  ExecutionForm,
} from "../../components/console";
import { Card } from "../../components/ui/Card";
import { DatePicker } from "../../components/ui/DatePicker";
import { NumberInput } from "../../components/ui/NumberInput";
import { Select } from "../../components/ui/Select";
import { TaskStatus } from "../../components/ui/TaskStatus";
import { useDryRunPreview } from "../../hooks/useDryRunPreview";
import { GridSchema, type GridParams } from "../../schemas/backtest";
import { triggerGrid, type BacktestPreview } from "../../api/backtest";

const MARKET_OPTIONS = [
  { value: "csi300", label: "CSI 300" },
  { value: "csi500", label: "CSI 500" },
  { value: "csi800", label: "CSI 800" },
  { value: "csi1000", label: "CSI 1000" },
];

const DEAL_PRICE_OPTIONS = [
  { value: "close", label: "close" },
  { value: "open", label: "open" },
];

const DEFAULT_GRID: GridParams = {
  model_path: "",
  market: "csi300",
  benchmark: "",
  topk_list: [5, 10, 15, 20],
  n_drop_list: [1, 3, 5],
  hold_thresh_list: [3, 5, 10],
  deal_price: "close",
  open_cost: 0.0005,
  close_cost: 0.0015,
  min_cost: 5,
  slippage: 0,
  start_date: "",
  end_date: "",
  output_csv: "",
  dry_run: true,
};

function parseNumberList(value: string): number[] {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
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
  const isLarge = candidateCount > 200 || typed.warning === "candidate_count_gt_200";

  return (
    <div className="space-y-2 font-mono text-xs text-slate-700">
      <div className={isLarge ? "font-semibold text-red-700" : "font-semibold"}>
        candidate_count: {candidateCount}
      </div>
      <div>estimated_minutes: {String(typed.estimated_minutes ?? "-")}</div>
      <div>rank_metric: information_ratio</div>
      {isLarge && (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-red-700">
          Candidate count exceeds 200. Dry-run review is required before launch.
        </div>
      )}
    </div>
  );
}

function GridFields({
  form,
  topkText,
  setTopkText,
  nDropText,
  setNDropText,
  holdText,
  setHoldText,
}: {
  form: UseFormReturn<GridParams>;
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
      <div>
        <FieldLabel>{t("console.backtest.modelPath")}</FieldLabel>
        <TextInput
          value={values.model_path}
          onChange={(value) =>
            form.setValue("model_path", value, { shouldDirty: true, shouldValidate: true })
          }
          placeholder="models/lgbm_latest.pkl"
        />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <FieldLabel>{t("console.backtest.market")}</FieldLabel>
          <Select
            options={MARKET_OPTIONS}
            value={values.market}
            onChange={(value) =>
              form.setValue("market", value as GridParams["market"], {
                shouldDirty: true,
                shouldValidate: true,
              })
            }
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.benchmark")}</FieldLabel>
          <TextInput
            value={values.benchmark ?? ""}
            onChange={(value) => form.setValue("benchmark", value || null)}
            placeholder="CSI300"
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.dealPrice")}</FieldLabel>
          <Select
            options={DEAL_PRICE_OPTIONS}
            value={values.deal_price}
            onChange={(value) =>
              form.setValue("deal_price", value as GridParams["deal_price"], {
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
            placeholder="5,10,15,20"
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.nDropList")}</FieldLabel>
          <TextInput
            value={nDropText}
            onChange={(value) => setList("n_drop_list", value, setNDropText)}
            placeholder="1,3,5"
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.holdThreshList")}</FieldLabel>
          <TextInput
            value={holdText}
            onChange={(value) => setList("hold_thresh_list", value, setHoldText)}
            placeholder="3,5,10"
          />
        </div>
      </div>
      <div
        className={`rounded-sm border px-3 py-2 font-mono text-xs ${
          candidateCount > 200
            ? "border-terminal-red text-terminal-red"
            : "border-terminal-border text-terminal-text"
        }`}
      >
        {t("console.backtest.candidateCount")}: {candidateCount}
        {candidateCount > 200 ? ` - ${t("console.backtest.largeCandidateWarning")}` : ""}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div>
          <FieldLabel>{t("console.backtest.openCost")}</FieldLabel>
          <NumberInput
            value={values.open_cost}
            onChange={(value) => form.setValue("open_cost", value ?? 0.0005)}
            step={0.0001}
            min={0}
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.closeCost")}</FieldLabel>
          <NumberInput
            value={values.close_cost}
            onChange={(value) => form.setValue("close_cost", value ?? 0.0015)}
            step={0.0001}
            min={0}
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.minCost")}</FieldLabel>
          <NumberInput
            value={values.min_cost}
            onChange={(value) => form.setValue("min_cost", value ?? 5)}
            step={1}
            min={0}
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.slippage")}</FieldLabel>
          <NumberInput
            value={values.slippage}
            onChange={(value) => form.setValue("slippage", value ?? 0)}
            step={0.0001}
            min={0}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <FieldLabel>{t("console.backtest.startDate")}</FieldLabel>
          <DatePicker
            value={values.start_date ?? ""}
            onChange={(value) => form.setValue("start_date", value || null)}
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.endDate")}</FieldLabel>
          <DatePicker
            value={values.end_date ?? ""}
            onChange={(value) => form.setValue("end_date", value || null)}
          />
        </div>
        <div>
          <FieldLabel>{t("console.backtest.outputCsv")}</FieldLabel>
          <TextInput
            value={values.output_csv ?? ""}
            onChange={(value) => form.setValue("output_csv", value || null)}
            placeholder="backtest_results/my_run.csv"
          />
        </div>
      </div>
      <label className="flex items-center gap-2 font-mono text-xs text-terminal-text">
        <input type="checkbox" className="accent-terminal-green" {...form.register("dry_run")} />
        {t("console.common.dryRun")}
      </label>
      <button
        type="submit"
        className="rounded-sm border border-terminal-green px-3 py-1.5 font-mono text-xs text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:opacity-30"
        disabled={!values.model_path}
      >
        {values.dry_run ? t("console.backtest.previewGrid") : t("console.backtest.runGrid")}
      </button>
    </div>
  );
}

export function GridConsole() {
  const { t } = useTranslation();
  const preview = useDryRunPreview<GridParams, BacktestPreview>((params) =>
    triggerGrid({ ...params, dry_run: true }),
  );
  const [taskId, setTaskId] = useState<string | null>(null);
  const [confirmParams, setConfirmParams] = useState<GridParams | null>(null);
  const [topkText, setTopkText] = useState("5,10,15,20");
  const [nDropText, setNDropText] = useState("1,3,5");
  const [holdText, setHoldText] = useState("3,5,10");

  const impact = useMemo(() => {
    if (!confirmParams) return null;
    const count =
      confirmParams.topk_list.length *
      confirmParams.n_drop_list.length *
      confirmParams.hold_thresh_list.length;
    return (
      <div className="space-y-1">
        <div>candidate_count: {count}</div>
        <div>rank_metric: information_ratio</div>
      </div>
    );
  }, [confirmParams]);

  return (
    <Card title={t("console.backtest.gridTitle")}>
      <ExecutionForm<GridParams>
        pageKey="backtest"
        actionKey="backtest.grid"
        schema={GridSchema}
        defaults={DEFAULT_GRID}
        dryRunDefault
        onDryRun={preview.run}
        onSubmit={async (params) => {
          setConfirmParams({ ...params, dry_run: false });
          return null;
        }}
        renderFields={(form) => (
          <GridFields
            form={form}
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
        titleKey="console.backtest.confirmGrid"
        impactSummary={impact}
        confirmLabelKey="console.backtest.runGrid"
        onCancel={() => setConfirmParams(null)}
        onConfirm={async () => {
          if (!confirmParams) return;
          const result = await triggerGrid({ ...confirmParams, dry_run: false });
          setTaskId(result.task_id);
          setConfirmParams(null);
        }}
      />
    </Card>
  );
}
