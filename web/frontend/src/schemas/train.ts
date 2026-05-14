import { z } from "zod";

export const TrainSchema = z.object({
  model_type: z.string().min(1),
  tag: z.string().min(1),
  config_override: z.string().nullable().optional(),
  market: z.enum(["csi300", "csi500", "csi800", "csi1000", "all"]).default("csi300"),
  train_start_date: z.string().nullable().optional(),
  train_end_date: z.string().nullable().optional(),
  factors: z.array(z.string().min(1)).default([]),
  qlib_native: z.boolean().default(false),
  with_sector: z.boolean().default(false),
  no_extra_factors: z.boolean().default(false),
  skip_factor_pipeline: z.boolean().default(false),
  bagging_fraction: z.number().gt(0).lte(1).nullable().optional(),
  ensemble_seeds: z.array(z.number().int()).nullable().optional(),
  lgbm_params: z.record(z.string(), z.unknown()).nullable().optional(),
  dry_run: z.boolean().default(true),
});
export type TrainParams = z.infer<typeof TrainSchema>;

export const DeleteModelSchema = z.object({
  filename: z.string().min(1),
  dry_run: z.boolean().default(true),
});
export type DeleteModelParams = z.infer<typeof DeleteModelSchema>;
