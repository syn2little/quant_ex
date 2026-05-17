import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Skeleton, SkeletonTable } from "../components/ui/Skeleton";
import { Tabs } from "../components/ui/Tabs";
import { del, get, post } from "../api/client";
import { useSSE } from "../hooks/useSSE";
import type { SSEEvent } from "../hooks/useSSE";
import type { AgentRunCreateRequest, AgentRunDetail, AgentRunSummary } from "../api/types";

type AgentTabKey = "plan" | "commands" | "agentTasks" | "summary" | "feedback" | "promotion" | "approval" | "raw";
type DiscussionMode = "sequential" | "meeting";
type AgentMode = "readonly" | "patch" | "danger-full-access";
type AgentCommand = {
  command_id: string;
  command: string;
  purpose?: string;
  source?: string;
  risk_tags?: string[];
  requires_approval?: boolean;
};
type ApprovalEntry = {
  command_id: string;
  approved?: boolean;
  approved_by?: string;
  reason?: string;
};
type FeedbackCandidate = {
  command_id: string;
  result_kind: string;
  result_csv: string;
  ready?: boolean;
};
type AgentCommandResult = {
  command_id: string;
  skipped?: boolean;
  returncode?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
  stdout_tail?: string;
  stderr_tail?: string;
  skip_reason?: string;
  approval_reason?: string;
};
type AgentTaskProposal = {
  task_id: string;
  title: string;
  provider?: string;
  mode?: string;
  source?: string;
  target_files?: string[];
  allowed_paths?: string[];
  requires_approval?: boolean;
};
type AgentTaskApprovalEntry = {
  task_id: string;
  approved?: boolean;
  approved_by?: string;
  reason?: string;
};
type AgentTaskResult = {
  task_id: string;
  skipped?: boolean;
  returncode?: number | null;
  result_path?: string;
  diff_path?: string;
  skip_reason?: string;
  warning?: string;
};
type CommandLogLine = {
  stream: "stdout" | "stderr";
  line: string;
};
type CommandLiveOutput = {
  command_id: string;
  command?: string;
  stage?: string;
  stdout_tail?: string;
  stderr_tail?: string;
  lines: CommandLogLine[];
};

const DETAIL_TABS: { key: AgentTabKey; labelKey: string }[] = [
  { key: "plan", labelKey: "agentRuns.plan" },
  { key: "commands", labelKey: "agentRuns.commands" },
  { key: "agentTasks", labelKey: "agentRuns.agentTasks" },
  { key: "summary", labelKey: "agentRuns.summary" },
  { key: "feedback", labelKey: "agentRuns.feedback" },
  { key: "promotion", labelKey: "agentRuns.promotionReport" },
  { key: "approval", labelKey: "agentRuns.approval" },
  { key: "raw", labelKey: "agentRuns.raw" },
];

const ARTIFACT_KEYS = [
  { key: "plan", flag: "has_plan", fields: ["plan.md", "plan_markdown", "plan", "plan_path"] },
  { key: "cmd", flag: "has_commands", fields: ["commands.md", "commands.json", "commands_markdown", "commands", "commands_path"] },
  { key: "task", flag: "has_agent_tasks", fields: ["agent_tasks.md", "agent_tasks.json", "agent_tasks", "agent_tasks_path"] },
  { key: "sum", flag: "has_execution_summary", fields: ["execution_summary.md", "execution_summary", "summary", "execution_summary_path"] },
  { key: "fb", flag: "has_feedback", fields: ["feedback.md", "feedback.json", "feedback", "feedback_path"] },
  { key: "promo", flag: "has_promotion_report", fields: ["promotion_report.md", "promotion_report.json", "promotion_report", "promotion_report_path"] },
  { key: "tpl", flag: "has_approval_template", fields: ["approval_template.yaml", "approval_template", "approval", "approval_template_path"] },
];
const MAX_LIVE_LOG_LINES = 500;
const PREVIEW_LOG_LINES = 5;

function normalizeRunList(payload: AgentRunSummary[] | { runs?: AgentRunSummary[] }) {
  return Array.isArray(payload) ? payload : payload.runs ?? [];
}

function coerceText(value: unknown) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return JSON.stringify(value, null, 2);
}

function firstText(run: AgentRunDetail | null, fields: string[]) {
  if (!run) return "";
  for (const field of fields) {
    const value = run[field];
    if (typeof value === "string" && value.trim()) return value;
  }
  if (run.artifacts && typeof run.artifacts === "object" && !Array.isArray(run.artifacts)) {
    const artifacts = run.artifacts as Record<string, unknown>;
    for (const field of fields) {
      const value = artifacts[field];
      if (typeof value === "string" && value.trim()) return value;
    }
  }
  return "";
}

function formatJson(value: unknown) {
  if (value == null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function artifactValue(run: AgentRunDetail | null, key: string) {
  if (!run?.artifacts || Array.isArray(run.artifacts) || typeof run.artifacts !== "object") return undefined;
  return (run.artifacts as Record<string, unknown>)[key];
}

function commandList(run: AgentRunDetail | null): AgentCommand[] {
  const commandsPayload = artifactValue(run, "commands.json");
  if (!commandsPayload || typeof commandsPayload !== "object" || Array.isArray(commandsPayload)) return [];
  const commands = (commandsPayload as Record<string, unknown>).commands;
  return Array.isArray(commands) ? (commands as AgentCommand[]) : [];
}

function agentTaskList(run: AgentRunDetail | null): AgentTaskProposal[] {
  const payload = artifactValue(run, "agent_tasks.json");
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  const tasks = (payload as Record<string, unknown>).tasks;
  return Array.isArray(tasks) ? (tasks as AgentTaskProposal[]) : [];
}

function agentTaskResultMap(run: AgentRunDetail | null) {
  const payload = artifactValue(run, "agent_tasks.json");
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return new Map<string, AgentTaskResult>();
  const results = (payload as Record<string, unknown>).results;
  if (!Array.isArray(results)) return new Map<string, AgentTaskResult>();
  return new Map((results as AgentTaskResult[]).map((result) => [result.task_id, result]));
}

function commandResultMap(run: AgentRunDetail | null) {
  const commandsPayload = artifactValue(run, "commands.json");
  if (!commandsPayload || typeof commandsPayload !== "object" || Array.isArray(commandsPayload)) return new Map<string, AgentCommandResult>();
  const results = (commandsPayload as Record<string, unknown>).results;
  if (!Array.isArray(results)) return new Map<string, AgentCommandResult>();
  return new Map((results as AgentCommandResult[]).map((result) => [result.command_id, result]));
}

function approvalMap(run: AgentRunDetail | null) {
  const entries = (run?.approval_entries ?? []) as ApprovalEntry[];
  return new Map(entries.map((entry) => [entry.command_id, entry]));
}

function agentTaskApprovalMap(run: AgentRunDetail | null) {
  const entries = (run?.agent_approval_entries ?? []) as AgentTaskApprovalEntry[];
  return new Map(entries.map((entry) => [entry.task_id, entry]));
}

function feedbackCandidateMap(run: AgentRunDetail | null) {
  const commandsPayload = artifactValue(run, "commands.json");
  if (!commandsPayload || typeof commandsPayload !== "object" || Array.isArray(commandsPayload)) return new Map<string, FeedbackCandidate>();
  const candidates = (commandsPayload as Record<string, unknown>).feedback_candidates;
  if (!Array.isArray(candidates)) return new Map<string, FeedbackCandidate>();
  return new Map((candidates as FeedbackCandidate[]).map((candidate) => [candidate.command_id, candidate]));
}

function collectLiveCommandOutput(events: SSEEvent[]) {
  const output = new Map<string, CommandLiveOutput>();
  for (const event of events) {
    if (event.type !== "progress") continue;
    const data = event.data;
    const commandId = typeof data.command_id === "string" ? data.command_id : "";
    if (!commandId) continue;
    const current = output.get(commandId) ?? { command_id: commandId, lines: [] };
    if (typeof data.command === "string") current.command = data.command;
    if (typeof data.stage === "string") current.stage = data.stage;
    if (typeof data.stdout_tail === "string") current.stdout_tail = data.stdout_tail;
    if (typeof data.stderr_tail === "string") current.stderr_tail = data.stderr_tail;
    if (data.stage === "command_output" && typeof data.line === "string" && data.line) {
      const stream = data.stream === "stderr" ? "stderr" : "stdout";
      current.lines = [...current.lines, { stream, line: data.line }];
      if (current.lines.length > MAX_LIVE_LOG_LINES) {
        current.lines = current.lines.slice(-MAX_LIVE_LOG_LINES);
      }
    }
    output.set(commandId, current);
  }
  return output;
}

function progressLine(data: Record<string, unknown>) {
  const parts = [typeof data.message === "string" && data.message ? data.message : String(data.stage ?? "")];
  if (typeof data.role === "string" && data.role) parts.push(`role=${data.role}`);
  if (typeof data.turn_index === "number") parts.push(`round=${data.turn_index}`);
  if (typeof data.index === "number" && typeof data.total === "number") parts.push(`${data.index}/${data.total}`);
  if (typeof data.verdict === "string" && data.verdict) parts.push(`verdict=${data.verdict}`);
  return parts.filter(Boolean).join(" | ");
}

function resultTailLines(result?: AgentCommandResult | null): CommandLogLine[] {
  if (!result) return [];
  const lines: CommandLogLine[] = [];
  if (result.stdout_tail) {
    lines.push(
      ...result.stdout_tail
        .replace(/\r\n/g, "\n")
        .split("\n")
        .filter(Boolean)
        .map((line) => ({ stream: "stdout" as const, line: `${line}\n` }))
    );
  }
  if (result.stderr_tail) {
    lines.push(
      ...result.stderr_tail
        .replace(/\r\n/g, "\n")
        .split("\n")
        .filter(Boolean)
        .map((line) => ({ stream: "stderr" as const, line: `${line}\n` }))
    );
  }
  return lines.slice(-MAX_LIVE_LOG_LINES);
}

function CommandLogPreview({
  lines,
  expanded,
  onToggle,
  labels,
}: {
  lines: CommandLogLine[];
  expanded: boolean;
  onToggle: () => void;
  labels: {
    latestOutput: string;
    showLog: string;
    hideLog: string;
    noOutputYet: string;
  };
}) {
  const visibleLines = expanded ? lines : lines.slice(-PREVIEW_LOG_LINES);
  return (
    <div className="mt-2 rounded-sm border border-terminal-border bg-black/30">
      <div className="flex items-center justify-between border-b border-terminal-border px-2 py-1">
        <span className="font-mono text-[10px] uppercase tracking-wider text-terminal-text-dim">{labels.latestOutput}</span>
        {lines.length > PREVIEW_LOG_LINES && (
          <button
            type="button"
            onClick={onToggle}
            className="font-mono text-[10px] text-terminal-cyan transition-colors hover:text-terminal-text-bright"
          >
            {expanded ? labels.hideLog : labels.showLog}
          </button>
        )}
      </div>
      <pre className={`${expanded ? "max-h-72" : "max-h-24"} overflow-auto whitespace-pre-wrap px-2 py-1.5 font-mono text-[11px] leading-5`}>
        {visibleLines.length === 0 ? (
          <span className="text-terminal-text-dim">{labels.noOutputYet}</span>
        ) : (
          visibleLines.map((item, index) => (
            <div key={index} className={item.stream === "stderr" ? "text-terminal-amber" : "text-terminal-text"}>
              <span className="select-none text-terminal-text-dim">[{item.stream}] </span>
              <span>{item.line}</span>
            </div>
          ))
        )}
      </pre>
    </div>
  );
}

function statusVariant(status?: string) {
  switch ((status ?? "").toLowerCase()) {
    case "done":
    case "completed":
    case "success":
    case "keep":
    case "promote":
    case "accepted":
      return "success" as const;
    case "running":
    case "started":
    case "pending":
    case "planned":
    case "hold":
    case "inconclusive":
      return "info" as const;
    case "failed":
    case "error":
    case "reject":
    case "refuted":
    case "rejected":
      return "error" as const;
    case "cancelled":
    case "needs_approval":
    case "waiting":
    case "artifact_only":
      return "warning" as const;
    default:
      return "neutral" as const;
  }
}

function hasArtifact(run: AgentRunSummary | AgentRunDetail | null, fields: string[]) {
  if (!run) return false;
  for (const artifact of ARTIFACT_KEYS) {
    if (fields === artifact.fields && Boolean(run[artifact.flag])) return true;
  }
  if (fields.some((field) => Boolean(run[field]))) return true;
  const artifacts = run.artifacts;
  if (Array.isArray(artifacts)) {
    return fields.some((field) => artifacts.some((item) => item.includes(field.replace("_path", ""))));
  }
  if (artifacts && typeof artifacts === "object") {
    return fields.some((field) => Boolean((artifacts as Record<string, unknown>)[field]));
  }
  return false;
}

function displayTime(run: AgentRunSummary | AgentRunDetail | null, kind: "created" | "updated") {
  if (!run) return "-";
  if (kind === "created") return run.created_at ?? run.generated_at ?? "-";
  return run.updated_at ?? run.modified_at ?? "-";
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-[10px] font-mono uppercase tracking-wider text-terminal-text-dim">
      {children}
    </p>
  );
}

function renderInline(text: string) {
  return text.split(/(`[^`]+`)/g).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded-sm border border-terminal-border bg-terminal-raised px-1 py-0.5 font-mono text-[11px] text-terminal-green"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function renderJsonLine(line: string) {
  const tokenPattern = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}\[\],]/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(line)) !== null) {
    if (match.index > lastIndex) parts.push(line.slice(lastIndex, match.index));
    const token = match[0];
    const isKey = Boolean(match[2]);
    const className = isKey
      ? "text-terminal-cyan"
      : /^"/.test(token)
        ? "text-terminal-green"
        : /^(true|false|null)$/.test(token)
          ? "text-terminal-amber"
          : /^[{}\[\],]$/.test(token)
            ? "text-terminal-text-dim"
            : "text-terminal-red";
    parts.push(
      <span key={`${match.index}-${token}`} className={className}>
        {isKey ? token.replace(/:\s*$/, "") : token}
      </span>
    );
    if (isKey) parts.push(<span key={`${match.index}-colon`} className="text-terminal-text-dim">:</span>);
    lastIndex = match.index + token.length;
  }

  if (lastIndex < line.length) parts.push(line.slice(lastIndex));
  return parts;
}

function JsonBlock({ value, empty }: { value: string; empty: string }) {
  const trimmed = value.trim();
  if (!trimmed) {
    return (
      <pre className="min-h-[360px] max-h-[620px] overflow-auto whitespace-pre-wrap rounded-sm border border-terminal-border bg-terminal-bg p-4 font-mono text-xs leading-relaxed text-terminal-text">
        {empty}
      </pre>
    );
  }

  const lines = value.replace(/\r\n/g, "\n").split("\n");
  const lineWidth = String(lines.length).length;

  return (
    <div className="min-h-[360px] max-h-[620px] overflow-auto rounded-sm border border-terminal-border bg-terminal-bg">
      <pre className="p-4 font-mono text-[11px] leading-5">
        {lines.map((line, index) => (
          <div key={index} className="grid grid-cols-[auto_minmax(0,1fr)] gap-4">
            <span className="select-none text-right text-terminal-text-dim">
              {String(index + 1).padStart(lineWidth, " ")}
            </span>
            <span className="whitespace-pre text-terminal-text">{renderJsonLine(line)}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}

function MarkdownBlock({ value, empty }: { value: string; empty: string }) {
  const trimmed = value.trim();
  if (!trimmed) {
    return (
      <pre className="min-h-[360px] max-h-[620px] overflow-auto whitespace-pre-wrap rounded-sm border border-terminal-border bg-terminal-bg p-4 font-mono text-xs leading-relaxed text-terminal-text">
        {empty}
      </pre>
    );
  }

  const lines = value.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let orderedListItems: string[] = [];
  let codeLines: string[] | null = null;
  let tableRows: string[][] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ");
    blocks.push(
      <p key={`p-${blocks.length}`} className="text-xs leading-6 text-terminal-text">
        {renderInline(text)}
      </p>
    );
    paragraph = [];
  };

  const flushList = () => {
    if (listItems.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="space-y-1 pl-5 text-xs leading-6 text-terminal-text marker:text-terminal-green">
          {listItems.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
    if (orderedListItems.length) {
      blocks.push(
        <ol key={`ol-${blocks.length}`} className="list-decimal space-y-1 pl-5 text-xs leading-6 text-terminal-text marker:text-terminal-cyan">
          {orderedListItems.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>
      );
      orderedListItems = [];
    }
  };

  const flushTable = () => {
    if (!tableRows.length) return;
    const [header, ...rows] = tableRows;
    blocks.push(
      <div key={`table-${blocks.length}`} className="overflow-auto rounded-sm border border-terminal-border">
        <table className="min-w-full border-collapse font-mono text-[11px] text-terminal-text">
          <thead className="bg-terminal-raised text-terminal-text-bright">
            <tr>
              {header.map((cell, index) => (
                <th key={index} className="border-b border-terminal-border px-2 py-1 text-left font-semibold">
                  {renderInline(cell)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-t border-terminal-border/60">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-2 py-1 align-top">
                    {renderInline(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
    tableRows = [];
  };

  const flushAll = () => {
    flushParagraph();
    flushList();
    flushTable();
  };

  lines.forEach((line) => {
    const fence = line.match(/^```/);
    if (fence) {
      if (codeLines) {
        blocks.push(
          <pre key={`code-${blocks.length}`} className="overflow-auto rounded-sm border border-terminal-border bg-terminal-raised p-3 font-mono text-[11px] leading-5 text-terminal-text">
            {codeLines.join("\n")}
          </pre>
        );
        codeLines = null;
      } else {
        flushAll();
        codeLines = [];
      }
      return;
    }

    if (codeLines) {
      codeLines.push(line);
      return;
    }

    if (!line.trim()) {
      flushAll();
      return;
    }

    const tableMatch = line.match(/^\s*\|(.+)\|\s*$/);
    if (tableMatch) {
      flushParagraph();
      flushList();
      const cells = tableMatch[1].split("|").map((cell) => cell.trim());
      if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) tableRows.push(cells);
      return;
    }
    flushTable();

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const className =
        level === 1
          ? "border-b border-terminal-border pb-2 text-base font-semibold text-terminal-text-bright"
          : level === 2
            ? "pt-3 text-sm font-semibold text-terminal-cyan"
            : "pt-2 text-xs font-semibold uppercase tracking-wider text-terminal-green";
      blocks.push(
        <h2 key={`h-${blocks.length}`} className={className}>
          {renderInline(heading[2])}
        </h2>
      );
      return;
    }

    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      flushTable();
      orderedListItems = [];
      listItems.push(bullet[1]);
      return;
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      flushTable();
      listItems = [];
      orderedListItems.push(ordered[1]);
      return;
    }

    const quote = line.match(/^>\s?(.+)$/);
    if (quote) {
      flushAll();
      blocks.push(
        <blockquote key={`quote-${blocks.length}`} className="border-l-2 border-terminal-cyan pl-3 text-xs leading-6 text-terminal-text-dim">
          {renderInline(quote[1])}
        </blockquote>
      );
      return;
    }

    paragraph.push(line.trim());
  });

  const remainingCodeLines = codeLines as string[] | null;
  if (remainingCodeLines) {
    blocks.push(
      <pre key={`code-${blocks.length}`} className="overflow-auto rounded-sm border border-terminal-border bg-terminal-raised p-3 font-mono text-[11px] leading-5 text-terminal-text">
        {remainingCodeLines.join("\n")}
      </pre>
    );
  }
  flushAll();

  return (
    <div className="min-h-[360px] max-h-[620px] overflow-auto rounded-sm border border-terminal-border bg-terminal-bg p-4">
      <div className="space-y-3">{blocks}</div>
    </div>
  );
}

function ToggleField({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 font-mono text-xs text-terminal-text-dim">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-3.5 w-3.5 accent-terminal-green"
      />
      {label}
    </label>
  );
}

export function AgentRunsPage() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [activeTab, setActiveTab] = useState<AgentTabKey>("plan");
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [objective, setObjective] = useState("");
  const [runId, setRunId] = useState("");
  const [discussionMode, setDiscussionMode] = useState<DiscussionMode>("sequential");
  const [meetingMaxRounds, setMeetingMaxRounds] = useState(6);
  const [meetingMaxRolesPerRound, setMeetingMaxRolesPerRound] = useState(1);
  const [useLlm, setUseLlm] = useState(false);
  const [useAgent, setUseAgent] = useState(false);
  const [agentMode, setAgentMode] = useState<AgentMode>("readonly");
  const [agentMaxTasks, setAgentMaxTasks] = useState(2);
  const [proposeActions, setProposeActions] = useState(true);
  const [writeApprovalTemplate, setWriteApprovalTemplate] = useState(true);
  const [appendMemory, setAppendMemory] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createTaskId, setCreateTaskId] = useState<string | null>(null);
  const [pendingCreatedRunId, setPendingCreatedRunId] = useState<string | null>(null);
  const [executionTaskId, setExecutionTaskId] = useState<string | null>(null);
  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);
  const [deleteBusyRunId, setDeleteBusyRunId] = useState<string | null>(null);
  const [selectedCommandIds, setSelectedCommandIds] = useState<Set<string>>(new Set());
  const [selectedAgentTaskIds, setSelectedAgentTaskIds] = useState<Set<string>>(new Set());
  const [expandedCommandLogs, setExpandedCommandLogs] = useState<Set<string>>(new Set());
  const [regeneratingTemplate, setRegeneratingTemplate] = useState(false);
  const createTask = useSSE(createTaskId);
  const executionTask = useSSE(executionTaskId);

  const fetchRuns = useCallback((nextSelected?: string) => {
    setLoadingRuns(true);
    setError(null);
    get<AgentRunSummary[] | { runs?: AgentRunSummary[] }>("/agents/runs")
      .then((payload) => {
        const nextRuns = normalizeRunList(payload);
        setRuns(nextRuns);
        setSelectedRunId((current) => {
          const fallback = nextRuns[0]?.run_id ?? null;
          if (nextSelected !== undefined) return nextSelected || fallback;
          if (current && nextRuns.some((run) => run.run_id === current)) return current;
          return fallback;
        });
      })
      .catch((err: Error) => {
        setRuns([]);
        setError(err.message);
      })
      .finally(() => setLoadingRuns(false));
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  useEffect(() => {
    if (!selectedRunId) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    get<AgentRunDetail>(`/agents/runs/${encodeURIComponent(selectedRunId)}`)
      .then(setDetail)
      .catch((err: Error) => {
        setDetail(null);
        setError(err.message);
      })
      .finally(() => setLoadingDetail(false));
  }, [selectedRunId]);

  useEffect(() => {
    if (!createTaskId) return;
    const errorEvent = [...createTask.events].reverse().find((event) => event.type === "error");
    if (createTask.status === "error" || errorEvent) {
      setError(createTask.error || String(errorEvent?.data.message || "Agent run creation failed"));
      setCreating(false);
      setCreateTaskId(null);
      setPendingCreatedRunId(null);
      return;
    }
    if (createTask.status !== "done") return;

    const doneEvent = [...createTask.events].reverse().find((event) => event.type === "done");
    const result = doneEvent?.data.result;
    const resultRunId =
      result && typeof result === "object" && !Array.isArray(result)
        ? ((result as Record<string, unknown>).run_id as string | undefined)
        : undefined;
    const createdId = resultRunId || pendingCreatedRunId || undefined;
    if (createdId) {
      setSelectedRunId(createdId);
      get<AgentRunDetail>(`/agents/runs/${encodeURIComponent(createdId)}`)
        .then(setDetail)
        .catch((err: Error) => setError(err.message));
    }
    fetchRuns(createdId);
    setObjective("");
    setRunId("");
    setCreating(false);
    setCreateTaskId(null);
    setPendingCreatedRunId(null);
  }, [createTask.status, createTask.error, createTask.events, createTaskId, fetchRuns, pendingCreatedRunId]);

  useEffect(() => {
    if (!executionTaskId) return;
    const errorEvent = [...executionTask.events].reverse().find((event) => event.type === "error");
    if (executionTask.status === "error" || errorEvent) {
      setError(executionTask.error || String(errorEvent?.data.message || "Agent command execution failed"));
      setExecutionTaskId(null);
      return;
    }
    if (executionTask.status !== "done") return;

    const doneEvent = [...executionTask.events].reverse().find((event) => event.type === "done");
    const result = doneEvent?.data.result;
    const resultRunId =
      result && typeof result === "object" && !Array.isArray(result)
        ? ((result as Record<string, unknown>).run_id as string | undefined)
        : undefined;
    const nextRunId = resultRunId || selectedRunId;
    if (nextRunId) {
      get<AgentRunDetail>(`/agents/runs/${encodeURIComponent(nextRunId)}`)
        .then((nextDetail) => {
          setDetail(nextDetail);
          setActiveTab("summary");
        })
        .catch((err: Error) => setError(err.message));
    }
    fetchRuns(nextRunId || undefined);
    setExecutionTaskId(null);
  }, [executionTask.status, executionTask.error, executionTask.events, executionTaskId, fetchRuns, selectedRunId]);

  const selectedSummary = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  const detailTabs = useMemo(
    () => DETAIL_TABS.map((tab) => ({ key: tab.key, label: t(tab.labelKey) })),
    [t]
  );

  const currentText = useMemo(() => {
    if (activeTab === "plan") return firstText(detail, ["plan.md", "plan_markdown", "plan"]);
    if (activeTab === "commands") return firstText(detail, ["commands.md", "commands_markdown", "commands"]);
    if (activeTab === "agentTasks") return firstText(detail, ["agent_tasks.md", "agent_tasks"]) || coerceText(artifactValue(detail, "agent_tasks.json"));
    if (activeTab === "summary") return firstText(detail, ["execution_summary.md", "execution_summary", "summary"]);
    if (activeTab === "feedback") return firstText(detail, ["feedback.md", "feedback"]) || coerceText(artifactValue(detail, "feedback.json"));
    if (activeTab === "promotion") return firstText(detail, ["promotion_report.md", "promotion_report"]) || coerceText(artifactValue(detail, "promotion_report.json"));
    if (activeTab === "approval") return firstText(detail, ["approval_template.yaml", "approval_template", "approval"]);
    return formatJson(detail?.raw ?? detail);
  }, [activeTab, detail]);

  const selectedDecision = (detail?.feedback_decision ?? selectedSummary?.feedback_decision) as string | undefined;
  const commands = useMemo(() => commandList(detail), [detail]);
  const commandResults = useMemo(() => commandResultMap(detail), [detail]);
  const agentTasks = useMemo(() => agentTaskList(detail), [detail]);
  const agentTaskResults = useMemo(() => agentTaskResultMap(detail), [detail]);
  const approvals = useMemo(() => approvalMap(detail), [detail]);
  const agentTaskApprovals = useMemo(() => agentTaskApprovalMap(detail), [detail]);
  const feedbackCandidates = useMemo(() => feedbackCandidateMap(detail), [detail]);
  const selectedCommands = useMemo(
    () => commands.filter((command) => selectedCommandIds.has(command.command_id)),
    [commands, selectedCommandIds]
  );
  const selectedCommandIdList = useMemo(
    () => selectedCommands.map((command) => command.command_id),
    [selectedCommands]
  );
  const selectedAgentTasks = useMemo(
    () => agentTasks.filter((task) => selectedAgentTaskIds.has(task.task_id)),
    [agentTasks, selectedAgentTaskIds]
  );
  const selectedAgentTaskIdList = useMemo(
    () => selectedAgentTasks.map((task) => task.task_id),
    [selectedAgentTasks]
  );
  const successfulCommandIds = useMemo(
    () =>
      new Set(
        [...commandResults.values()]
          .filter((result) => !result.skipped && result.returncode === 0)
          .map((result) => result.command_id)
      ),
    [commandResults]
  );
  const successfulAgentTaskIds = useMemo(
    () =>
      new Set(
        [...agentTaskResults.values()]
          .filter((result) => !result.skipped && result.returncode === 0)
          .map((result) => result.task_id)
      ),
    [agentTaskResults]
  );
  const selectedApprovedAgentTaskIds = useMemo(
    () =>
      selectedAgentTasks
        .filter((task) => agentTaskApprovals.get(task.task_id)?.approved && !successfulAgentTaskIds.has(task.task_id))
        .map((task) => task.task_id),
    [agentTaskApprovals, selectedAgentTasks, successfulAgentTaskIds]
  );
  const selectedSafeCommandIds = useMemo(
    () =>
      selectedCommands
        .filter((command) => !command.requires_approval && !successfulCommandIds.has(command.command_id))
        .map((command) => command.command_id),
    [selectedCommands, successfulCommandIds]
  );
  const selectedApprovedProtectedCommandIds = useMemo(
    () =>
      selectedCommands
        .filter(
          (command) =>
            command.requires_approval &&
            approvals.get(command.command_id)?.approved &&
            !successfulCommandIds.has(command.command_id)
        )
        .map((command) => command.command_id),
    [approvals, selectedCommands, successfulCommandIds]
  );
  const selectedRunnableCommandIds = useMemo(
    () =>
      selectedCommands
        .filter(
          (command) =>
            (!command.requires_approval || approvals.get(command.command_id)?.approved) &&
            !successfulCommandIds.has(command.command_id)
        )
        .map((command) => command.command_id),
    [approvals, selectedCommands, successfulCommandIds]
  );
  const selectedRunnableCommandIdSet = useMemo(() => new Set(selectedRunnableCommandIds), [selectedRunnableCommandIds]);
  const selectedProtectedRunnableCount = selectedCommands.filter(
    (command) => command.requires_approval && selectedRunnableCommandIdSet.has(command.command_id)
  ).length;
  const selectedExpensiveRunnableCount = selectedCommands.filter(
    (command) =>
      selectedRunnableCommandIdSet.has(command.command_id) &&
      (command.risk_tags ?? []).some((tag) => ["expensive", "network", "external_effect", "trading_like"].includes(tag))
  ).length;
  const selectedSafeCount = selectedSafeCommandIds.length;
  const selectedRerunnableSafeCommandIds = useMemo(
    () => selectedCommands.filter((command) => !command.requires_approval).map((command) => command.command_id),
    [selectedCommands]
  );
  const selectedRerunnableCommandIds = useMemo(
    () =>
      selectedCommands
        .filter((command) => !command.requires_approval || approvals.get(command.command_id)?.approved)
        .map((command) => command.command_id),
    [approvals, selectedCommands]
  );
  const latestExecutionProgress = useMemo(
    () => [...executionTask.events].reverse().find((event) => event.type === "progress")?.data,
    [executionTask.events]
  );
  const latestCreateProgress = useMemo(
    () => [...createTask.events].reverse().find((event) => event.type === "progress")?.data,
    [createTask.events]
  );
  const recentCreateProgress = useMemo(
    () => createTask.events.filter((event) => event.type === "progress").slice(-6),
    [createTask.events]
  );
  const liveCommandOutput = useMemo(
    () => collectLiveCommandOutput(executionTask.events),
    [executionTask.events]
  );
  const activeCommandOutput = useMemo(() => {
    const commandId =
      latestExecutionProgress && typeof latestExecutionProgress.command_id === "string"
        ? latestExecutionProgress.command_id
        : "";
    return commandId ? liveCommandOutput.get(commandId) ?? null : null;
  }, [latestExecutionProgress, liveCommandOutput]);
  const logLabels = useMemo(
    () => ({
      latestOutput: t("agentRuns.latestOutput"),
      showLog: t("agentRuns.showLog"),
      hideLog: t("agentRuns.hideLog"),
      noOutputYet: t("agentRuns.noOutputYet"),
    }),
    [t]
  );

  useEffect(() => {
    setSelectedCommandIds(new Set());
    setSelectedAgentTaskIds(new Set());
  }, [selectedRunId]);

  useEffect(() => {
    setSelectedCommandIds((current) => {
      const valid = new Set(commands.map((command) => command.command_id));
      const next = new Set([...current].filter((commandId) => valid.has(commandId)));
      return next.size === current.size ? current : next;
    });
  }, [commands]);

  useEffect(() => {
    setSelectedAgentTaskIds((current) => {
      const valid = new Set(agentTasks.map((task) => task.task_id));
      const next = new Set([...current].filter((taskId) => valid.has(taskId)));
      return next.size === current.size ? current : next;
    });
  }, [agentTasks]);

  const handleCreate = () => {
    if (!objective.trim()) return;
    const payload: AgentRunCreateRequest = {
      objective: objective.trim(),
      discussion_mode: discussionMode,
      meeting_max_rounds: discussionMode === "meeting" ? meetingMaxRounds : undefined,
      meeting_max_roles_per_round: discussionMode === "meeting" ? meetingMaxRolesPerRound : undefined,
      use_llm: useLlm,
      propose_actions: proposeActions,
      write_approval_template: writeApprovalTemplate,
      use_agent: useAgent,
      agent_provider: "codex",
      agent_mode: agentMode,
      agent_max_tasks: agentMaxTasks,
      write_agent_approval_template: true,
      append_memory: appendMemory,
    };
    if (runId.trim()) payload.run_id = runId.trim();

    setCreating(true);
    setError(null);
    post<AgentRunDetail | AgentRunSummary | { task_id: string; run_id?: string | null }>("/agents/runs", payload)
      .then((created) => {
        if (typeof created.task_id === "string") {
          setCreateTaskId(created.task_id);
          setPendingCreatedRunId((typeof created.run_id === "string" ? created.run_id : payload.run_id) || null);
          return;
        }
        const createdId = created.run_id || payload.run_id;
        setObjective("");
        setRunId("");
        if (createdId) {
          setSelectedRunId(createdId);
          setDetail(created as AgentRunDetail);
          fetchRuns(createdId);
        } else {
          fetchRuns();
        }
      })
      .catch((err: Error) => {
        setError(err.message);
        setCreating(false);
      })
      .finally(() => {
        if (!useLlm) setCreating(false);
      });
  };

  const handleRegenerateTemplate = () => {
    if (!selectedRunId) return;
    setRegeneratingTemplate(true);
    setError(null);
    post<AgentRunSummary>(`/agents/runs/${encodeURIComponent(selectedRunId)}/approval-template`)
      .then(() => {
        fetchRuns(selectedRunId);
        return get<AgentRunDetail>(`/agents/runs/${encodeURIComponent(selectedRunId)}`);
      })
      .then(setDetail)
      .catch((err: Error) => setError(err.message))
      .finally(() => setRegeneratingTemplate(false));
  };

  const refreshSelectedRun = (runId: string) =>
    get<AgentRunDetail>(`/agents/runs/${encodeURIComponent(runId)}`).then((nextDetail) => {
      setDetail(nextDetail);
      fetchRuns(runId);
    });

  const handleApprovalUpdate = (commandId: string, approved: boolean) => {
    if (!selectedRunId) return;
    setApprovalBusyId(commandId);
    setError(null);
    post(`/agents/runs/${encodeURIComponent(selectedRunId)}/approvals/${encodeURIComponent(commandId)}`, {
      approved,
      approved_by: "web",
      reason: approved ? "Approved from dashboard" : "Revoked from dashboard",
    })
      .then(() => refreshSelectedRun(selectedRunId))
      .catch((err: Error) => setError(err.message))
      .finally(() => setApprovalBusyId(null));
  };

  const handleAgentTaskApprovalUpdate = (taskId: string, approved: boolean) => {
    if (!selectedRunId) return;
    setApprovalBusyId(taskId);
    setError(null);
    post(`/agents/runs/${encodeURIComponent(selectedRunId)}/agent-task-approvals/${encodeURIComponent(taskId)}`, {
      approved,
      approved_by: "web",
      reason: approved ? "Approved from dashboard" : "Revoked from dashboard",
    })
      .then(() => refreshSelectedRun(selectedRunId))
      .catch((err: Error) => setError(err.message))
      .finally(() => setApprovalBusyId(null));
  };

  const handleSelectCommand = (commandId: string, checked: boolean) => {
    setSelectedCommandIds((current) => {
      const next = new Set(current);
      if (checked) next.add(commandId);
      else next.delete(commandId);
      return next;
    });
  };

  const handleSelectAllCommands = () => {
    setSelectedCommandIds(new Set(commands.map((command) => command.command_id)));
  };

  const handleClearCommandSelection = () => {
    setSelectedCommandIds(new Set());
  };

  const handleSelectAgentTask = (taskId: string, checked: boolean) => {
    setSelectedAgentTaskIds((current) => {
      const next = new Set(current);
      if (checked) next.add(taskId);
      else next.delete(taskId);
      return next;
    });
  };

  const handleSelectAllAgentTasks = () => {
    setSelectedAgentTaskIds(new Set(agentTasks.map((task) => task.task_id)));
  };

  const handleClearAgentTaskSelection = () => {
    setSelectedAgentTaskIds(new Set());
  };

  const toggleCommandLog = (commandId: string) => {
    setExpandedCommandLogs((current) => {
      const next = new Set(current);
      if (next.has(commandId)) next.delete(commandId);
      else next.add(commandId);
      return next;
    });
  };

  const handleExecuteSafe = (rerunSuccessful = false) => {
    const commandIds = rerunSuccessful ? selectedRerunnableSafeCommandIds : selectedSafeCommandIds;
    if (!selectedRunId || commandIds.length === 0) return;
    setError(null);
    setExpandedCommandLogs(new Set());
    post<{ task_id: string; run_id: string }>(`/agents/runs/${encodeURIComponent(selectedRunId)}/execute-safe`, {
      command_ids: commandIds,
      skip_successful: !rerunSuccessful,
    })
      .then((payload) => setExecutionTaskId(payload.task_id))
      .catch((err: Error) => setError(err.message));
  };

  const handleExecuteApproved = (includeSafe: boolean, rerunSuccessful = false) => {
    const commandIds = includeSafe
      ? rerunSuccessful
        ? selectedRerunnableCommandIds
        : selectedRunnableCommandIds
      : selectedApprovedProtectedCommandIds;
    if (!selectedRunId || commandIds.length === 0) return;
    setError(null);
    setExpandedCommandLogs(new Set());
    post<{ task_id: string; run_id: string }>(`/agents/runs/${encodeURIComponent(selectedRunId)}/execute-approved`, {
      include_safe: includeSafe,
      command_ids: commandIds,
      skip_successful: !rerunSuccessful,
    })
      .then((payload) => setExecutionTaskId(payload.task_id))
      .catch((err: Error) => setError(err.message));
  };

  const handleExecuteAgentTasks = () => {
    if (!selectedRunId || selectedApprovedAgentTaskIds.length === 0) return;
    setError(null);
    post<{ task_id: string; run_id: string }>(`/agents/runs/${encodeURIComponent(selectedRunId)}/execute-agent-tasks`, {
      task_ids: selectedApprovedAgentTaskIds,
      skip_successful: true,
    })
      .then((payload) => setExecutionTaskId(payload.task_id))
      .catch((err: Error) => setError(err.message));
  };

  const handleGenerateFeedback = (commandId: string) => {
    if (!selectedRunId) return;
    setError(null);
    post<{ task_id: string; run_id: string }>(
      `/agents/runs/${encodeURIComponent(selectedRunId)}/feedback/${encodeURIComponent(commandId)}`,
      {}
    )
      .then((payload) => setExecutionTaskId(payload.task_id))
      .catch((err: Error) => setError(err.message));
  };

  const handleDeleteRun = (targetRunId: string) => {
    if (!window.confirm(t("agentRuns.deleteConfirm", { runId: targetRunId }))) return;
    const currentIndex = runs.findIndex((run) => run.run_id === targetRunId);
    const nextSelected =
      targetRunId === selectedRunId
        ? runs[currentIndex + 1]?.run_id || runs[currentIndex - 1]?.run_id || null
        : selectedRunId;
    setDeleteBusyRunId(targetRunId);
    setError(null);
    del<{ run_id: string; deleted: boolean }>(`/agents/runs/${encodeURIComponent(targetRunId)}`)
      .then(() => {
        if (targetRunId === selectedRunId) {
          setDetail(null);
          setSelectedRunId(nextSelected);
        }
        fetchRuns(nextSelected || undefined);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setDeleteBusyRunId(null));
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-terminal-text-bright">{t("agentRuns.title")}</h1>
        <p className="mt-1 font-mono text-xs text-terminal-text-dim">{t("agentRuns.subtitle")}</p>
      </div>

      {error && (
        <div className="rounded-sm border border-terminal-red bg-terminal-red-glow px-3 py-2 font-mono text-xs text-terminal-red">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card title={t("agentRuns.createRun")} accent="green">
            <div className="space-y-3">
              <div>
                <FieldLabel>{t("agentRuns.objective")}</FieldLabel>
                <textarea
                  value={objective}
                  onChange={(event) => setObjective(event.target.value)}
                  placeholder={t("agentRuns.objectivePlaceholder")}
                  rows={4}
                  className="w-full rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-xs text-terminal-text outline-none focus:border-terminal-green"
                />
              </div>
              <div>
                <FieldLabel>{t("agentRuns.runIdOptional")}</FieldLabel>
                <input
                  value={runId}
                  onChange={(event) => setRunId(event.target.value)}
                  placeholder={t("agentRuns.runIdPlaceholder")}
                  className="w-full rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-xs text-terminal-text outline-none focus:border-terminal-green"
                />
              </div>
              <div>
                <FieldLabel>{t("agentRuns.discussionMode")}</FieldLabel>
                <div className="grid grid-cols-2 gap-2">
                  {(["sequential", "meeting"] as DiscussionMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setDiscussionMode(mode)}
                      className={`rounded-sm border px-3 py-2 text-left font-mono text-xs transition-colors ${
                        discussionMode === mode
                          ? "border-terminal-green bg-terminal-green-glow text-terminal-green"
                          : "border-terminal-border bg-terminal-bg text-terminal-text-dim hover:border-terminal-cyan hover:text-terminal-cyan"
                      }`}
                    >
                      {t(`agentRuns.mode.${mode}`)}
                    </button>
                  ))}
                </div>
              </div>
              {discussionMode === "meeting" && (
                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    <FieldLabel>{t("agentRuns.maxRounds")}</FieldLabel>
                    <input
                      type="number"
                      min={1}
                      max={12}
                      value={meetingMaxRounds}
                      onChange={(event) => setMeetingMaxRounds(Math.max(1, Math.min(12, Number(event.target.value) || 1)))}
                      className="w-full rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-xs text-terminal-text outline-none focus:border-terminal-green"
                    />
                  </label>
                  <label className="block">
                    <FieldLabel>{t("agentRuns.maxRolesPerRound")}</FieldLabel>
                    <input
                      type="number"
                      min={1}
                      max={4}
                      value={meetingMaxRolesPerRound}
                      onChange={(event) =>
                        setMeetingMaxRolesPerRound(Math.max(1, Math.min(4, Number(event.target.value) || 1)))
                      }
                      className="w-full rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-xs text-terminal-text outline-none focus:border-terminal-green"
                    />
                  </label>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <ToggleField checked={useLlm} label={t("agentRuns.useLlm")} onChange={setUseLlm} />
                <ToggleField checked={useAgent} label={t("agentRuns.useAgent")} onChange={setUseAgent} />
                <ToggleField checked={proposeActions} label={t("agentRuns.proposeActions")} onChange={setProposeActions} />
                <ToggleField checked={writeApprovalTemplate} label={t("agentRuns.approvalTemplate")} onChange={setWriteApprovalTemplate} />
                <ToggleField checked={appendMemory} label={t("agentRuns.appendMemory")} onChange={setAppendMemory} />
              </div>
              {useAgent && (
                <div className="space-y-2 rounded-sm border border-terminal-border bg-terminal-bg p-3">
                  <FieldLabel>{t("agentRuns.agentMode")}</FieldLabel>
                  <div className="grid grid-cols-3 gap-2">
                    {(["readonly", "patch", "danger-full-access"] as AgentMode[]).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setAgentMode(mode)}
                        className={`rounded-sm border px-2 py-1.5 text-left font-mono text-[11px] transition-colors ${
                          agentMode === mode
                            ? "border-terminal-green bg-terminal-green-glow text-terminal-green"
                            : "border-terminal-border text-terminal-text-dim hover:border-terminal-cyan hover:text-terminal-cyan"
                        }`}
                      >
                        {t(`agentRuns.agentModeOption.${mode}`)}
                      </button>
                    ))}
                  </div>
                  <label className="block">
                    <FieldLabel>{t("agentRuns.agentMaxTasks")}</FieldLabel>
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={agentMaxTasks}
                      onChange={(event) => setAgentMaxTasks(Math.max(1, Math.min(5, Number(event.target.value) || 1)))}
                      className="w-full rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-xs text-terminal-text outline-none focus:border-terminal-green"
                    />
                  </label>
                  {agentMode === "danger-full-access" && (
                    <p className="font-mono text-[11px] text-terminal-red">{t("agentRuns.agentDangerWarning")}</p>
                  )}
                </div>
              )}
              <button
                onClick={handleCreate}
                disabled={creating || !objective.trim()}
                className="w-full rounded-sm border border-terminal-green px-3 py-2 font-mono text-xs text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:cursor-not-allowed disabled:opacity-40"
              >
                {creating ? t("agentRuns.creating") : t("agentRuns.create")}
              </button>
              {createTaskId && (
                <div className="space-y-2 rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-[11px] text-terminal-text-dim">
                  <div className="flex items-center justify-between gap-2">
                    <span>task:{createTaskId.slice(0, 8)}</span>
                    <Badge variant={createTask.status === "error" ? "error" : createTask.status === "done" ? "success" : "info"}>
                      {createTask.status === "streaming" ? "running" : createTask.status}
                    </Badge>
                  </div>
                  {latestCreateProgress && (
                    <div className="rounded-sm border border-terminal-border/70 bg-black/20 px-2 py-1 text-terminal-text">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span>{progressLine(latestCreateProgress)}</span>
                        <Badge variant="info">{String(latestCreateProgress.stage ?? "")}</Badge>
                      </div>
                    </div>
                  )}
                  {recentCreateProgress.length > 1 && (
                    <div className="max-h-28 space-y-1 overflow-auto border-t border-terminal-border pt-2">
                      {recentCreateProgress.map((event, index) => (
                        <p key={index} className="truncate text-terminal-text-dim">
                          {progressLine(event.data)}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card
            title={t("agentRuns.runs")}
            actions={
              <button
                onClick={() => fetchRuns()}
                className="rounded-sm border border-terminal-border px-3 py-1.5 font-mono text-xs text-terminal-text-dim transition-colors hover:border-terminal-text-dim hover:text-terminal-text"
              >
                {t("common.refresh")}
              </button>
            }
          >
            {loadingRuns ? (
              <SkeletonTable rows={6} />
            ) : runs.length === 0 ? (
              <p className="font-mono text-xs text-terminal-text-dim">{t("agentRuns.noRuns")}</p>
            ) : (
              <div className="max-h-[560px] space-y-2 overflow-auto pr-1">
                {runs.map((run) => (
                  <div
                    key={run.run_id}
                    onClick={() => setSelectedRunId(run.run_id)}
                    className={`w-full cursor-pointer rounded-sm border px-3 py-2 text-left transition-colors ${
                      selectedRunId === run.run_id
                        ? "border-terminal-green bg-terminal-green-glow"
                        : "border-terminal-border bg-terminal-bg hover:border-terminal-text-dim"
                    }`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") setSelectedRunId(run.run_id);
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-xs text-terminal-green">{run.run_id}</span>
                      <div className="flex shrink-0 items-center gap-1">
                        <Badge variant={statusVariant(run.status)}>{run.status ?? "unknown"}</Badge>
                        {typeof run.feedback_decision === "string" && (
                          <Badge variant={statusVariant(run.feedback_decision)}>{run.feedback_decision}</Badge>
                        )}
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleDeleteRun(run.run_id);
                          }}
                          disabled={Boolean(executionTaskId) || Boolean(createTaskId) || deleteBusyRunId === run.run_id}
                          className="rounded-sm border border-terminal-border px-1.5 py-0.5 font-mono text-[10px] text-terminal-text-dim transition-colors hover:border-terminal-red hover:text-terminal-red disabled:cursor-not-allowed disabled:opacity-40"
                          title={t("agentRuns.deleteRun")}
                        >
                          {deleteBusyRunId === run.run_id ? t("agentRuns.deleting") : t("agentRuns.deleteRun")}
                        </button>
                      </div>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-terminal-text-dim">
                      {run.objective || t("agentRuns.noObjective")}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {ARTIFACT_KEYS.map((artifact) => (
                        <Badge
                          key={artifact.key}
                          variant={hasArtifact(run, artifact.fields) ? "success" : "neutral"}
                          className="px-1.5"
                        >
                          {artifact.key}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          <Card
            title={t("agentRuns.detail")}
            accent="cyan"
            actions={
              selectedRunId ? (
                <button
                  onClick={handleRegenerateTemplate}
                  disabled={regeneratingTemplate}
                  className="rounded-sm border border-terminal-border px-3 py-1.5 font-mono text-xs text-terminal-text-dim transition-colors hover:border-terminal-cyan hover:text-terminal-cyan disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {regeneratingTemplate ? t("agentRuns.regenerating") : t("agentRuns.regenerateApproval")}
                </button>
              ) : null
            }
          >
            {!selectedRunId ? (
              <p className="font-mono text-xs text-terminal-text-dim">{t("agentRuns.selectRun")}</p>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
                  <div className="rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                    <FieldLabel>{t("agentRuns.runId")}</FieldLabel>
                    <p className="truncate font-mono text-xs text-terminal-green">{selectedRunId}</p>
                  </div>
                  <div className="rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                    <FieldLabel>{t("common.status")}</FieldLabel>
                    <Badge variant={statusVariant(detail?.status ?? selectedSummary?.status)}>
                      {detail?.status ?? selectedSummary?.status ?? "unknown"}
                    </Badge>
                  </div>
                  <div className="rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                    <FieldLabel>{t("agentRuns.decision")}</FieldLabel>
                    {selectedDecision ? (
                      <Badge variant={statusVariant(selectedDecision)}>{selectedDecision}</Badge>
                    ) : (
                      <p className="font-mono text-xs text-terminal-text-dim">-</p>
                    )}
                  </div>
                  <div className="rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                    <FieldLabel>{t("agentRuns.created")}</FieldLabel>
                    <p className="truncate font-mono text-xs text-terminal-text">
                      {displayTime(detail ?? selectedSummary, "created")}
                    </p>
                  </div>
                  <div className="rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                    <FieldLabel>{t("agentRuns.updated")}</FieldLabel>
                    <p className="truncate font-mono text-xs text-terminal-text">
                      {displayTime(detail ?? selectedSummary, "updated")}
                    </p>
                  </div>
                </div>

                <div className="rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                  <FieldLabel>{t("agentRuns.objective")}</FieldLabel>
                  <p className="whitespace-pre-wrap font-mono text-xs text-terminal-text">
                    {detail?.objective ?? selectedSummary?.objective ?? t("agentRuns.noObjective")}
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {ARTIFACT_KEYS.map((artifact) => (
                    <Badge
                      key={artifact.key}
                      variant={hasArtifact(detail ?? selectedSummary, artifact.fields) ? "success" : "neutral"}
                    >
                      {artifact.key}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {selectedRunId && (
            <Card title={t("agentRuns.execution")} accent="amber">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2">
                  <span className="font-mono text-xs text-terminal-text-dim">
                    {t("agentRuns.selectedCommands", { count: selectedCommandIdList.length, total: commands.length })}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={handleSelectAllCommands}
                      disabled={commands.length === 0 || Boolean(executionTaskId)}
                      className="rounded-sm border border-terminal-border px-2 py-1 font-mono text-[11px] text-terminal-text-dim transition-colors hover:border-terminal-cyan hover:text-terminal-cyan disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {t("agentRuns.selectAll")}
                    </button>
                    <button
                      onClick={handleClearCommandSelection}
                      disabled={selectedCommandIdList.length === 0 || Boolean(executionTaskId)}
                      className="rounded-sm border border-terminal-border px-2 py-1 font-mono text-[11px] text-terminal-text-dim transition-colors hover:border-terminal-red hover:text-terminal-red disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {t("agentRuns.clearSelection")}
                    </button>
                  </div>
                </div>

                {selectedCommandIdList.length === 0 && (
                  <p className="font-mono text-[11px] text-terminal-text-dim">{t("agentRuns.selectCommandsToExecute")}</p>
                )}
                {selectedCommandIdList.length > 0 && (
                  <p className="font-mono text-[11px] text-terminal-text-dim">
                    {t("agentRuns.executionSelectionSummary", {
                      safe: selectedSafeCount,
                      protected: selectedProtectedRunnableCount,
                      expensive: selectedExpensiveRunnableCount,
                    })}
                  </p>
                )}
                {selectedExpensiveRunnableCount > 0 && (
                  <p className="rounded-sm border border-terminal-amber bg-terminal-amber-glow px-3 py-2 font-mono text-[11px] text-terminal-amber">
                    {t("agentRuns.expensiveExecutionWarning")}
                  </p>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handleExecuteSafe(false)}
                    disabled={Boolean(executionTaskId) || selectedSafeCount === 0}
                    className="rounded-sm border border-terminal-green px-3 py-1.5 font-mono text-xs text-terminal-green transition-colors hover:bg-terminal-green-glow disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {t("agentRuns.executeSelectedSafe")}
                  </button>
                  <button
                    onClick={() => handleExecuteApproved(false)}
                    disabled={Boolean(executionTaskId) || !detail?.has_approval_template || selectedApprovedProtectedCommandIds.length === 0}
                    className="rounded-sm border border-terminal-amber px-3 py-1.5 font-mono text-xs text-terminal-amber transition-colors hover:bg-terminal-amber-glow disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {t("agentRuns.executeSelectedApproved")}
                  </button>
                  <button
                    onClick={() => handleExecuteApproved(true)}
                    disabled={Boolean(executionTaskId) || !detail?.has_approval_template || selectedRunnableCommandIds.length === 0}
                    className="rounded-sm border border-terminal-border px-3 py-1.5 font-mono text-xs text-terminal-text-dim transition-colors hover:border-terminal-cyan hover:text-terminal-cyan disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {t("agentRuns.executeSelectedApprovedWithSafe")}
                  </button>
                  <button
                    onClick={() => {
                      if (detail?.has_approval_template) handleExecuteApproved(true, true);
                      else handleExecuteSafe(true);
                    }}
                    disabled={
                      Boolean(executionTaskId) ||
                      (detail?.has_approval_template
                        ? selectedRerunnableCommandIds.length === 0
                        : selectedRerunnableSafeCommandIds.length === 0)
                    }
                    className="rounded-sm border border-terminal-border px-3 py-1.5 font-mono text-xs text-terminal-text-dim transition-colors hover:border-terminal-red hover:text-terminal-red disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {t("agentRuns.rerunSelected")}
                  </button>
                </div>

                {executionTaskId && (
                  <div className="space-y-2 rounded-sm border border-terminal-border bg-terminal-bg px-3 py-2 font-mono text-[11px] text-terminal-text-dim">
                    <div className="flex items-center justify-between">
                      <span>task:{executionTaskId}</span>
                      <Badge variant={executionTask.status === "error" ? "error" : executionTask.status === "done" ? "success" : "info"}>
                        {executionTask.status === "streaming" ? "running" : executionTask.status}
                      </Badge>
                    </div>
                    {latestExecutionProgress && (
                      <div className="space-y-1">
                        <div className="flex items-center justify-between gap-3">
                          <span>
                            {t("agentRuns.commandProgress", {
                              index: String(latestExecutionProgress.index ?? "?"),
                              total: String(latestExecutionProgress.total ?? "?"),
                              stage: String(latestExecutionProgress.stage ?? ""),
                            })}
                          </span>
                          <Badge variant={latestExecutionProgress.returncode === 0 ? "success" : latestExecutionProgress.skipped ? "info" : "warning"}>
                            {String(latestExecutionProgress.command_id ?? "")}
                          </Badge>
                        </div>
                        <p className="overflow-x-auto whitespace-nowrap text-terminal-text">
                          {String(latestExecutionProgress.command ?? "")}
                        </p>
                        {Boolean(latestExecutionProgress.skip_reason) && (
                          <p className="text-terminal-text-dim">{String(latestExecutionProgress.skip_reason)}</p>
                        )}
                        {activeCommandOutput && (
                          <CommandLogPreview
                            lines={activeCommandOutput.lines}
                            expanded={expandedCommandLogs.has(activeCommandOutput.command_id)}
                            onToggle={() => toggleCommandLog(activeCommandOutput.command_id)}
                            labels={logLabels}
                          />
                        )}
                      </div>
                    )}
                  </div>
                )}

                {commands.length === 0 ? (
                  <p className="font-mono text-xs text-terminal-text-dim">{t("agentRuns.noCommands")}</p>
                ) : (
                  <div className="max-h-72 space-y-2 overflow-auto pr-1">
                    {commands.map((command) => {
                      const approval = approvals.get(command.command_id);
                      const feedbackCandidate = feedbackCandidates.get(command.command_id);
                      const result = commandResults.get(command.command_id);
                      const approved = Boolean(approval?.approved);
                      const selected = selectedCommandIds.has(command.command_id);
                      const succeeded = Boolean(result && !result.skipped && result.returncode === 0);
                      const failed = Boolean(result && !result.skipped && result.returncode != null && result.returncode !== 0);
                      const liveOutput = liveCommandOutput.get(command.command_id);
                      const persistedLogLines = resultTailLines(result);
                      const logLines = liveOutput?.lines.length ? liveOutput.lines : persistedLogLines;
                      return (
                        <div
                          key={command.command_id}
                          className={`rounded-sm border px-3 py-2 ${
                            selected ? "border-terminal-green bg-terminal-green-glow" : "border-terminal-border bg-terminal-bg"
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <label className="flex shrink-0 items-center gap-2 font-mono text-[11px] text-terminal-text-dim">
                                <input
                                  type="checkbox"
                                  checked={selected}
                                  disabled={Boolean(executionTaskId)}
                                  onChange={(event) => handleSelectCommand(command.command_id, event.target.checked)}
                                  className="h-3.5 w-3.5 accent-terminal-green"
                                />
                                {t("agentRuns.select")}
                              </label>
                              <span className="font-mono text-xs text-terminal-cyan">{command.command_id}</span>
                              <Badge variant={command.requires_approval ? "warning" : "success"}>
                                {command.requires_approval ? t("agentRuns.protected") : t("agentRuns.safeLocal")}
                              </Badge>
                              {approved && <Badge variant="success">{t("agentRuns.approved")}</Badge>}
                              {succeeded && <Badge variant="success">{t("agentRuns.executed")}</Badge>}
                              {failed && <Badge variant="error">{t("agentRuns.failed")}</Badge>}
                              {result?.skipped && <Badge variant="info">{t("agentRuns.skipped")}</Badge>}
                            </div>
                            {command.requires_approval && (
                              <button
                                onClick={() => handleApprovalUpdate(command.command_id, !approved)}
                                disabled={approvalBusyId === command.command_id || Boolean(executionTaskId)}
                                className="rounded-sm border border-terminal-border px-2 py-1 font-mono text-[11px] text-terminal-text-dim transition-colors hover:border-terminal-green hover:text-terminal-green disabled:cursor-not-allowed disabled:opacity-40"
                              >
                                {approved ? t("agentRuns.revokeApproval") : t("agentRuns.approve")}
                              </button>
                            )}
                            {feedbackCandidate?.ready && (
                              <button
                                onClick={() => handleGenerateFeedback(command.command_id)}
                                disabled={Boolean(executionTaskId)}
                                className="rounded-sm border border-terminal-cyan px-2 py-1 font-mono text-[11px] text-terminal-cyan transition-colors hover:bg-terminal-cyan-glow disabled:cursor-not-allowed disabled:opacity-40"
                              >
                                {t("agentRuns.generateFeedback")}
                              </button>
                            )}
                          </div>
                          <p className="mt-2 overflow-x-auto whitespace-nowrap font-mono text-[11px] text-terminal-text">
                            {command.command}
                          </p>
                          {feedbackCandidate && (
                            <p className="mt-1 overflow-x-auto whitespace-nowrap font-mono text-[11px] text-terminal-text-dim">
                              {feedbackCandidate.ready ? t("agentRuns.feedbackReady") : t("agentRuns.feedbackPending")}: {feedbackCandidate.result_csv}
                            </p>
                          )}
                          {result && (
                            <p className="mt-1 overflow-x-auto whitespace-nowrap font-mono text-[11px] text-terminal-text-dim">
                              {t("agentRuns.lastResult")}:{" "}
                              {result.skipped
                                ? result.skip_reason || t("agentRuns.skipped")
                                : result.returncode === 0
                                  ? t("agentRuns.executed")
                                  : `${t("agentRuns.failed")} (${result.returncode ?? "?"})`}
                            </p>
                          )}
                          {logLines.length > 0 && (
                            <CommandLogPreview
                              lines={logLines}
                              expanded={expandedCommandLogs.has(command.command_id)}
                              onToggle={() => toggleCommandLog(command.command_id)}
                              labels={logLabels}
                            />
                          )}
                          <p className="mt-1 text-xs text-terminal-text-dim">{command.purpose || command.source}</p>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="border-t border-terminal-border pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-xs text-terminal-text-dim">
                      {t("agentRuns.selectedAgentTasks", { count: selectedAgentTaskIdList.length, total: agentTasks.length })}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={handleSelectAllAgentTasks}
                        disabled={agentTasks.length === 0 || Boolean(executionTaskId)}
                        className="rounded-sm border border-terminal-border px-2 py-1 font-mono text-[11px] text-terminal-text-dim transition-colors hover:border-terminal-cyan hover:text-terminal-cyan disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {t("agentRuns.selectAll")}
                      </button>
                      <button
                        onClick={handleClearAgentTaskSelection}
                        disabled={selectedAgentTaskIdList.length === 0 || Boolean(executionTaskId)}
                        className="rounded-sm border border-terminal-border px-2 py-1 font-mono text-[11px] text-terminal-text-dim transition-colors hover:border-terminal-red hover:text-terminal-red disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {t("agentRuns.clearSelection")}
                      </button>
                      <button
                        onClick={handleExecuteAgentTasks}
                        disabled={Boolean(executionTaskId) || !detail?.has_agent_approval_template || selectedApprovedAgentTaskIds.length === 0}
                        className="rounded-sm border border-terminal-amber px-2 py-1 font-mono text-[11px] text-terminal-amber transition-colors hover:bg-terminal-amber-glow disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {t("agentRuns.executeSelectedAgentTasks")}
                      </button>
                    </div>
                  </div>
                  {agentTasks.length === 0 ? (
                    <p className="mt-2 font-mono text-xs text-terminal-text-dim">{t("agentRuns.noAgentTasks")}</p>
                  ) : (
                    <div className="mt-2 max-h-56 space-y-2 overflow-auto pr-1">
                      {agentTasks.map((task) => {
                        const approval = agentTaskApprovals.get(task.task_id);
                        const result = agentTaskResults.get(task.task_id);
                        const approved = Boolean(approval?.approved);
                        const selected = selectedAgentTaskIds.has(task.task_id);
                        const succeeded = Boolean(result && !result.skipped && result.returncode === 0);
                        const failed = Boolean(result && !result.skipped && result.returncode != null && result.returncode !== 0);
                        return (
                          <div
                            key={task.task_id}
                            className={`rounded-sm border px-3 py-2 ${
                              selected ? "border-terminal-green bg-terminal-green-glow" : "border-terminal-border bg-terminal-bg"
                            }`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="flex min-w-0 items-center gap-2">
                                <label className="flex shrink-0 items-center gap-2 font-mono text-[11px] text-terminal-text-dim">
                                  <input
                                    type="checkbox"
                                    checked={selected}
                                    disabled={Boolean(executionTaskId)}
                                    onChange={(event) => handleSelectAgentTask(task.task_id, event.target.checked)}
                                    className="h-3.5 w-3.5 accent-terminal-green"
                                  />
                                  {t("agentRuns.select")}
                                </label>
                                <span className="font-mono text-xs text-terminal-cyan">{task.task_id}</span>
                                <Badge variant="info">{task.mode ?? "readonly"}</Badge>
                                {approved && <Badge variant="success">{t("agentRuns.approved")}</Badge>}
                                {succeeded && <Badge variant="success">{t("agentRuns.executed")}</Badge>}
                                {failed && <Badge variant="error">{t("agentRuns.failed")}</Badge>}
                                {result?.skipped && <Badge variant="info">{t("agentRuns.skipped")}</Badge>}
                              </div>
                              <button
                                onClick={() => handleAgentTaskApprovalUpdate(task.task_id, !approved)}
                                disabled={approvalBusyId === task.task_id || Boolean(executionTaskId)}
                                className="rounded-sm border border-terminal-border px-2 py-1 font-mono text-[11px] text-terminal-text-dim transition-colors hover:border-terminal-green hover:text-terminal-green disabled:cursor-not-allowed disabled:opacity-40"
                              >
                                {approved ? t("agentRuns.revokeApproval") : t("agentRuns.approve")}
                              </button>
                            </div>
                            <p className="mt-2 font-mono text-[11px] text-terminal-text">{task.title}</p>
                            <p className="mt-1 overflow-x-auto whitespace-nowrap font-mono text-[11px] text-terminal-text-dim">
                              {task.source || task.provider || "codex"}
                            </p>
                            {result && (
                              <p className="mt-1 overflow-x-auto whitespace-nowrap font-mono text-[11px] text-terminal-text-dim">
                                {t("agentRuns.lastResult")}:{" "}
                                {result.skipped
                                  ? result.skip_reason || t("agentRuns.skipped")
                                  : result.returncode === 0
                                    ? t("agentRuns.executed")
                                    : `${t("agentRuns.failed")} (${result.returncode ?? "?"})`}
                                {result.diff_path ? ` | diff: ${result.diff_path}` : ""}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </Card>
          )}

          <Card>
            <Tabs tabs={detailTabs} activeKey={activeTab} onChange={(key) => setActiveTab(key as AgentTabKey)} />
            <div className="pt-4">
              {loadingDetail ? (
                <Skeleton className="h-[420px] w-full" />
              ) : activeTab === "raw" ? (
                <JsonBlock value={currentText} empty={t("agentRuns.emptySection")} />
              ) : (
                <MarkdownBlock value={currentText} empty={t("agentRuns.emptySection")} />
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
