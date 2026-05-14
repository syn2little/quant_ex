import type { TaskTrigger } from "./tasks";
import type {
  GenerateParams,
  NotifyTestParams,
  RebalanceParams,
} from "../schemas/signals";

export type SignalFile = {
  filename: string;
  size_kb: number;
  modified: string;
};

export type SignalContent = {
  content: string;
};

export type RegimeInfo = {
  enabled: boolean;
  regime: number | null;
  label: string | null;
  error?: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const r = await fetch(`/api/signals${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json();
}

export async function triggerGenerate(
  params: GenerateParams,
): Promise<TaskTrigger<Record<string, unknown>>> {
  return request("/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function triggerRebalance(
  params: RebalanceParams,
): Promise<TaskTrigger<Record<string, unknown>>> {
  return request("/rebalance", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function triggerNotifyTest(
  params: NotifyTestParams,
): Promise<TaskTrigger<Record<string, unknown>>> {
  return request("/notify-test", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function fetchSignalHistory(): Promise<SignalFile[]> {
  return request("/history");
}

export async function fetchSignalContent(filename: string): Promise<SignalContent> {
  return request(`/history/${encodeURIComponent(filename)}`);
}

export async function fetchRegime(): Promise<RegimeInfo> {
  return request("/regime");
}

