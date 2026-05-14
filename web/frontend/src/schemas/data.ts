import { z } from "zod";

export const DataTypeSchema = z.enum(["prices", "financial", "northbound", "sectors"]);
export type DataType = z.infer<typeof DataTypeSchema>;

export const FetchSchema = z.object({
  data_types: z.array(DataTypeSchema).min(1),
  date_range: z.object({
    start: z.string().nullable(),
    end: z.string().nullable(),
  }).optional(),
  force_refresh: z.boolean().default(false),
  dry_run: z.boolean().default(true),
});
export type FetchParams = z.infer<typeof FetchSchema>;

export const PurgeSchema = z.object({
  data_type: DataTypeSchema,
  dry_run: z.boolean().default(true),
});
export type PurgeParams = z.infer<typeof PurgeSchema>;
