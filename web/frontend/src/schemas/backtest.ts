import { z } from "zod";

const parseNumberList = (value: unknown) => {
  if (Array.isArray(value)) {
    return value.map((item) => Number(item)).filter((item) => Number.isFinite(item));
  }
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item));
  }
  return [];
};

const NumberListSchema = z.preprocess(
  parseNumberList,
  z.array(z.number()).min(1),
);

export const GridSchema = z.object({
  model_path: z.string().min(1),
  market: z.enum(["csi300", "csi500", "csi800", "csi1000"]).default("csi300"),
  benchmark: z.string().nullable().optional(),
  topk_list: NumberListSchema,
  n_drop_list: NumberListSchema,
  hold_thresh_list: NumberListSchema,
  deal_price: z.enum(["close", "open"]).default("close"),
  open_cost: z.number().default(0.0005),
  close_cost: z.number().default(0.0015),
  min_cost: z.number().default(5.0),
  slippage: z.number().default(0.0),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  output_csv: z.string().nullable().optional(),
  dry_run: z.boolean().default(true),
});

export type GridParams = z.infer<typeof GridSchema>;

export const WFVSchema = z.object({
  train_universes: z.array(z.string()).min(1),
  eval_market: z.string().min(1),
  rolling_window_days: z.number().default(252),
  step_days: z.number().default(63),
  topk_list: NumberListSchema,
  n_drop_list: NumberListSchema,
  hold_thresh_list: NumberListSchema,
  rank_metric: z.literal("information_ratio").default("information_ratio"),
  dry_run: z.boolean().default(true),
});

export type WFVParams = z.infer<typeof WFVSchema>;

export const CompareSchema = z.object({
  result_files: z.array(z.string()).min(2).max(5),
  dry_run: z.boolean().default(true),
});

export type CompareParams = z.infer<typeof CompareSchema>;
