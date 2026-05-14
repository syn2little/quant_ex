import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import type { DefaultValues, FieldValues, UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

export type DryRunResult<TPreview = unknown> = {
  task_id: string;
  dry_run: boolean;
  preview: TPreview | null;
};

export type ExecutionFormProps<TParams extends FieldValues> = {
  pageKey: "data" | "models" | "backtest" | "signals";
  actionKey: string;
  schema: z.ZodType<TParams>;
  defaults: Partial<TParams>;
  dryRunDefault: boolean;
  onDryRun: (params: TParams) => Promise<DryRunResult>;
  onSubmit: (params: TParams) => Promise<{ task_id: string }>;
  renderFields: (form: UseFormReturn<TParams>) => ReactNode;
  destructive?: boolean;
};

export function ExecutionForm<TParams extends FieldValues>({
  actionKey,
  schema,
  defaults,
  dryRunDefault,
  onDryRun,
  onSubmit,
  renderFields,
}: ExecutionFormProps<TParams>) {
  const form = useForm<TParams>({
    resolver: zodResolver(schema),
    defaultValues: defaults as DefaultValues<TParams>,
  });

  return (
    <form
      data-testid={`execution-form-${actionKey}`}
      className="space-y-4"
      onSubmit={form.handleSubmit(async (params) => {
        const dryRun = (params as Record<string, unknown>).dry_run;
        if ((typeof dryRun === "boolean" ? dryRun : undefined) ?? dryRunDefault) {
          await onDryRun(params);
          return;
        }
        await onSubmit(params);
      })}
    >
      {renderFields(form)}
    </form>
  );
}
