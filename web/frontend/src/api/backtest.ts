import type { TaskTrigger } from "./tasks";
import type {
  BacktestMetrics,
  CompareRun,
  DrawdownSeries,
  EquityCurve,
  ModelInfo,
} from "./types";
import type { CompareParams, GridParams, WFVParams } from "../schemas/backtest";

export type BacktestResultFile = {
  filename: string;
  size_kb: number;
  modified: string;
};

export type BacktestPreview = {
  candidate_count?: number;
  window_count?: number;
  total_runs?: number;
  estimated_minutes?: number;
  rank_metric?: "information_ratio";
  warning?: string | null;
  [key: string]: unknown;
};

export type BacktestResultTable = {
  columns: string[];
  rows: Record<string, unknown>[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${path} failed: ${response.status} ${body}`);
  }
  return response.json();
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

function nullIfBlank(value: string | null | undefined): string | null | undefined {
  if (typeof value !== "string") return value;
  return value.trim() ? value : null;
}

export function listModels(): Promise<ModelInfo[]> {
  return request<ModelInfo[]>("/api/models");
}

export function listBacktestResults(): Promise<BacktestResultFile[]> {
  return request<BacktestResultFile[]>("/api/backtest/results");
}

export function fetchResultMetrics(filename: string): Promise<BacktestMetrics & Record<string, unknown>> {
  return request<BacktestMetrics & Record<string, unknown>>(
    `/api/backtest/results/${encodeURIComponent(filename)}/metrics`,
  );
}

export function fetchResultTable(filename: string): Promise<BacktestResultTable> {
  return request<BacktestResultTable>(`/api/backtest/results/${encodeURIComponent(filename)}`);
}

export function fetchResultEquityCurve(filename: string): Promise<EquityCurve> {
  return request<EquityCurve>(
    `/api/backtest/results/${encodeURIComponent(filename)}/equity-curve`,
  );
}

export function fetchResultDrawdown(filename: string): Promise<DrawdownSeries> {
  return request<DrawdownSeries>(
    `/api/backtest/results/${encodeURIComponent(filename)}/drawdown`,
  );
}

export async function fetchCompareRuns(filenames: string[]): Promise<CompareRun[]> {
  const colors = ["#22c55e", "#38bdf8", "#f59e0b", "#ef4444", "#a78bfa"];
  const runs = await Promise.all(
    filenames.map(async (filename, index) => {
      const [equity_curve, drawdown, metrics] = await Promise.all([
        fetchResultEquityCurve(filename).catch(() => ({ dates: [], portfolio: [], benchmark: [], excess: [] })),
        fetchResultDrawdown(filename).catch(() => ({ dates: [], drawdown: [] })),
        fetchResultMetrics(filename).catch(() => ({} as BacktestMetrics)),
      ]);
      return {
        filename,
        label: filename.replace(/\.csv$/i, ""),
        color: colors[index % colors.length],
        equity_curve,
        drawdown,
        metrics,
      };
    }),
  );
  return runs;
}

export function triggerGrid(params: GridParams): Promise<TaskTrigger<BacktestPreview>> {
  return post<TaskTrigger<BacktestPreview>>("/api/backtest/grid", {
    ...params,
    benchmark: nullIfBlank(params.benchmark),
    start_date: nullIfBlank(params.start_date),
    end_date: nullIfBlank(params.end_date),
    output_csv: nullIfBlank(params.output_csv),
  });
}

export function triggerWFV(params: WFVParams): Promise<TaskTrigger<BacktestPreview>> {
  return post<TaskTrigger<BacktestPreview>>("/api/backtest/walk-forward", {
    ...params,
    rank_metric: "information_ratio",
  });
}

export function triggerCompare(params: CompareParams): Promise<TaskTrigger<BacktestPreview>> {
  return post<TaskTrigger<BacktestPreview>>("/api/backtest/compare", params);
}
