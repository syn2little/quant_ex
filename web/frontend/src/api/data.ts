import type { TaskTrigger } from "./tasks";
import type { FetchParams, PurgeParams } from "../schemas/data";

export type CacheStatus = {
  type: string;
  file_count: number;
  total_size_mb: number;
  latest: string | null;
  ttl_days: number;
};

export type DataFetchPreview = {
  data_types?: string[];
  date_range?: { start?: string | null; end?: string | null } | null;
  force_refresh?: boolean;
  estimated_files?: number;
  estimated_minutes?: number;
  estimated_disk_mb?: number;
  skipped_cached?: string[];
};

export type DataPurgePreview = {
  data_type?: string;
  ttl_days?: number;
  files?: string[];
  count?: number;
  freed_bytes?: number;
};

export async function triggerFetch(params: FetchParams): Promise<TaskTrigger<DataFetchPreview>> {
  const response = await fetch("/api/data/fetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`fetch failed: ${response.status}`);
  return response.json();
}

export async function triggerPurge(params: PurgeParams): Promise<TaskTrigger<DataPurgePreview>> {
  const query = new URLSearchParams({ dry_run: String(params.dry_run) });
  const response = await fetch(`/api/data/cache/${params.data_type}/expired?${query}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(`purge failed: ${response.status}`);
  return response.json();
}

export async function getCacheStatus(): Promise<CacheStatus[]> {
  const response = await fetch("/api/data/cache-status");
  if (!response.ok) throw new Error(`cache-status failed: ${response.status}`);
  return response.json();
}
