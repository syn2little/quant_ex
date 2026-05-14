import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import type { DefaultValues, FieldValues, Resolver, UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

export type DryRunResult<TPreview = unknown> = {
  task_id: string;
  dry_run: boolean;
  preview: TPreview | null;
};

export type ExecutionFormSubmitResult = { task_id: string } | null;

export type ExecutionFormProps<TParams extends FieldValues> = {
  pageKey: "data" | "models" | "backtest" | "signals";
  actionKey: string;
  schema: z.ZodType<TParams>;
  defaults: Partial<TParams>;
  dryRunDefault: boolean;
  onDryRun: (params: TParams) => Promise<DryRunResult>;
  onSubmit: (params: TParams) => Promise<ExecutionFormSubmitResult>;
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
    resolver: zodResolver(schema as never) as Resolver<TParams>,
    defaultValues: defaults as DefaultValues<TParams>,
  });

  const emitTaskCreated = (result: ExecutionFormSubmitResult) => {
    if (result === null) return;
    window.dispatchEvent(new CustomEvent("console:task-created", { detail: { taskId: result.task_id } }));
  };

  return (
    <form
      data-testid={`execution-form-${actionKey}`}
      className="space-y-4"
      onSubmit={form.handleSubmit(async (params) => {
        const dryRun = (params as Record<string, unknown>).dry_run;
        if ((typeof dryRun === "boolean" ? dryRun : undefined) ?? dryRunDefault) {
          const result = await onDryRun(params);
          emitTaskCreated(result);
          return;
        }
        const result = await onSubmit(params);
        emitTaskCreated(result);
      })}
    >
      {renderFields(form)}
    </form>
  );
}
