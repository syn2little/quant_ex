import type { TaskTrigger } from "./tasks";
import type { DeleteModelParams, TrainParams } from "../schemas/train";

export interface ModelInfo {
  filename: string;
  size_mb: number;
  modified: string;
  meta?: Record<string, unknown>;
  result_paths?: string[];
}

export interface RegistryInfo {
  models: { name: string }[];
  factors: { name: string }[];
}

export interface TrainPreview {
  model_type?: string;
  tag?: string | null;
  final_market?: string;
  train_window?: {
    start?: string | null;
    end?: string | null;
  };
  config_override?: string | null;
  estimated_minutes?: number;
  output_path?: string;
  estimated_outputs?: string[];
  config_source?: Record<string, unknown>;
  effective_params?: Record<string, unknown>;
  command?: string | string[];
  meta?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface DeleteModelPreview {
  filename?: string;
  files?: string[];
  count?: number;
  [key: string]: unknown;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body}`);
  }
  return response.json();
}

export async function listModels(): Promise<ModelInfo[]> {
  return request<ModelInfo[]>("/api/models");
}

export async function getModelRegistry(): Promise<RegistryInfo> {
  return request<RegistryInfo>("/api/models/registry");
}

export async function getModelMeta(filename: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/api/models/${encodeURIComponent(filename)}/meta`,
  );
}

export async function getModelImportance(filename: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/api/models/${encodeURIComponent(filename)}/importance`,
  );
}

export async function triggerTrain(
  params: TrainParams,
): Promise<TaskTrigger<TrainPreview>> {
  return request<TaskTrigger<TrainPreview>>("/api/models/train", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function triggerDelete(
  params: DeleteModelParams,
): Promise<TaskTrigger<DeleteModelPreview>> {
  const qs = new URLSearchParams({ dry_run: String(params.dry_run) });
  return request<TaskTrigger<DeleteModelPreview>>(
    `/api/models/${encodeURIComponent(params.filename)}?${qs}`,
    { method: "DELETE" },
  );
}
