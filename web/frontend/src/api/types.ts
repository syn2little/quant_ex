// --- Data ---
export interface StockQuote {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number;
}

export interface StockSearchResult {
  symbol: string;
  name: string;
  exchange: string;
}

export interface SectorInfo {
  sector_id: string;
  sector_name: string;
  stock_count: number;
}

export interface SectorStock {
  symbol: string;
  name: string;
}

export interface SectorRotation {
  sector_id: string;
  sector_name: string;
  returns: Record<string, number>;
}

export interface AltDataResponse {
  type: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  has_more: boolean;
}

// --- Factors ---
export interface FactorValueRow {
  symbol: string;
  date: string;
  [factor: string]: string | number;
}

export interface ICDecayPoint {
  horizon: number;
  ic: number;
}

export interface RollingICPoint {
  date: string;
  ic: number;
}

export interface ICDAnalysis {
  factor: string;
  ic_mean: number;
  icir: number;
  decay: ICDecayPoint[];
  rolling: RollingICPoint[];
}

export interface FactorHeatmap {
  factors: string[];
  matrix: number[][];
}

// --- Backtest ---
export interface EquityCurve {
  dates: string[];
  portfolio: number[];
  benchmark: number[];
  excess: number[];
}

export interface BacktestMetrics {
  annual_return: number;
  sharpe: number;
  max_drawdown: number;
  calmar: number;
  ic: number;
  icir: number;
  rank_ic: number;
  rank_icir: number;
  win_rate: number;
  turnover: number;
  cum_return: number;
  annual_vol: number;
  sortino: number;
}

export interface DrawdownSeries {
  dates: string[];
  drawdown: number[];
}

export interface CompareRun {
  filename: string;
  label: string;
  color: string;
  equity_curve: EquityCurve;
  drawdown: DrawdownSeries;
  metrics: BacktestMetrics;
}

export interface CompareResponse {
  runs: CompareRun[];
  dates: string[];
}

// --- Models ---
export interface ModelInfo {
  filename: string;
  size_mb: number;
  modified: string;
  meta?: Record<string, unknown>;
}

// --- Tasks ---
export interface TaskInfo {
  task_id: string;
  task_type: string;
  status: string;
  created_at: string;
  error?: string;
  result?: unknown;
}

export type TaskStatus = "pending" | "running" | "done" | "failed" | "cancelled";

export interface TaskState {
  task_id: string;
  task_type: string;
  status: TaskStatus;
  created_at: string;
  result: unknown;
  error: string | null;
  page_key: string | null;
  action_key: string | null;
  result_paths: string[];
}

// --- Agent Runs ---
export interface AgentRunSummary {
  run_id: string;
  objective?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  generated_at?: string;
  modified_at?: string;
  has_plan?: boolean;
  has_commands?: boolean;
  has_feedback?: boolean;
  has_promotion_report?: boolean;
  has_execution_summary?: boolean;
  has_approval_template?: boolean;
  commands_count?: number;
  results_count?: number;
  feedback_candidates_count?: number;
  approved_commands_count?: number;
  has_next_iteration?: boolean;
  has_agent_tasks?: boolean;
  has_agent_approval_template?: boolean;
  agent_tasks_count?: number;
  agent_task_results_count?: number;
  approved_agent_tasks_count?: number;
  approval_entries?: Record<string, unknown>[];
  agent_approval_entries?: Record<string, unknown>[];
  artifacts?: Record<string, unknown> | string[];
  [key: string]: unknown;
}

export interface AgentRunDetail extends AgentRunSummary {
  plan_markdown?: string;
  commands_markdown?: string;
  execution_summary?: string;
  feedback?: string;
  approval_template?: string;
  raw?: unknown;
}

export interface AgentRunCreateRequest {
  objective: string;
  run_id?: string;
  discussion_mode?: "sequential" | "meeting";
  meeting_max_rounds?: number;
  meeting_max_roles_per_round?: number;
  use_llm: boolean;
  propose_actions: boolean;
  write_approval_template: boolean;
  use_agent?: boolean;
  agent_provider?: string;
  agent_mode?: "readonly" | "patch" | "danger-full-access";
  agent_max_tasks?: number;
  write_agent_approval_template?: boolean;
  append_memory: boolean;
}
