import { z } from "zod";

const NotifyChannelSchema = z.enum([
  "all",
  "bark",
  "pushplus",
  "dingtalk",
  "serverchan",
  "wechat_mp",
  "none",
]);

export const GenerateSchema = z.object({
  model_path: z.string().min(1),
  config_override: z.string().nullable().optional(),
  dry_run: z.boolean().default(true),
});
export type GenerateParams = z.infer<typeof GenerateSchema>;

export const RebalanceSchema = z
  .object({
    config: z.string().min(1),
    positions: z.string().nullable().optional(),
    position_date: z.string().nullable().optional(),
    min_action_value: z.number().default(1000),
    skip_update: z.boolean().default(true),
    force: z.boolean().default(false),
    notify_channel: NotifyChannelSchema.default("none"),
    dry_run: z.boolean().default(true),
    confirm_send: z.boolean().default(false),
  })
  .refine((d) => d.dry_run === true || d.confirm_send === true, {
    message: "confirm_send required when dry_run is false",
    path: ["confirm_send"],
  });
export type RebalanceParams = z.infer<typeof RebalanceSchema>;

export const NotifyTestSchema = z
  .object({
    channel: z.enum(["all", "bark", "pushplus", "dingtalk", "serverchan", "wechat_mp"]),
    message: z.string().min(1),
    dry_run: z.boolean().default(true),
    confirm_send: z.boolean().default(false),
  })
  .refine((d) => d.dry_run === true || d.confirm_send === true, {
    message: "confirm_send required when dry_run is false",
    path: ["confirm_send"],
  });
export type NotifyTestParams = z.infer<typeof NotifyTestSchema>;

export const RebalanceHoldingSchema = z.object({
  instrument: z.string(),
  shares: z.number().nullable(),
  price: z.number().nullable(),
  value: z.number().nullable(),
  weight: z.number().nullable(),
  entry_date: z.string().nullable().optional(),
});
export type RebalanceHolding = z.infer<typeof RebalanceHoldingSchema>;

export const RebalanceActionSchema = z.object({
  side: z.enum(["buy", "sell"]),
  instrument: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  amount: z.number().nullable(),
});
export type RebalanceAction = z.infer<typeof RebalanceActionSchema>;

export const RebalanceCacheSchema = z.object({
  filename: z.string(),
  path: z.string(),
  size_kb: z.number(),
  modified: z.string(),
  trade_date: z.string().nullable().optional(),
  next_trade_date: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  mock: z.boolean(),
  strategy: z.record(z.string(), z.unknown()),
  portfolio_value: z.number().nullable(),
  target_value: z.number().nullable(),
  holdings_count: z.number(),
  top_holdings: z.array(RebalanceHoldingSchema),
  actions: z.array(RebalanceActionSchema),
  action_summary: z.object({
    buy_count: z.number(),
    sell_count: z.number(),
    buy_amount: z.number(),
    sell_amount: z.number(),
    net_amount: z.number(),
  }),
  report: z.string(),
});
export type RebalanceCache = z.infer<typeof RebalanceCacheSchema>;

export const RebalanceCacheListSchema = z.array(RebalanceCacheSchema);
