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

