import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, X } from "lucide-react";
import { cancelTask, subscribeTask } from "../../api/tasks";
import { useTaskTracking } from "../../hooks/useTaskTracking";
import type { TaskState, TaskStatus } from "../../api/types";
import type { PageKey } from "./ConsolePageLayout";
import { TaskChip } from "./TaskChip";

export type TaskDrawerProps = {
  pageKey: PageKey;
  taskTypeFilter: string[];
  open: boolean;
  onClose: () => void;
};

const ACTIVE_STATUSES = new Set<TaskStatus>(["pending", "running"]);
const TERMINAL_STATUSES = new Set<TaskStatus>(["done", "failed", "cancelled"]);

export function TaskDrawer({ pageKey, taskTypeFilter, open, onClose }: TaskDrawerProps) {
  const { t } = useTranslation();
  const { tasks, refresh, trackTask } = useTaskTracking({ pageKey, taskTypeFilter });
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<Record<string, string[]>>({});
  const [statusFilter, setStatusFilter] = useState<"all" | TaskStatus>("all");
  const [actionFilter, setActionFilter] = useState("all");
  const [showFailureDetails, setShowFailureDetails] = useState(false);

  const clearTaskEvents = useCallback((taskId: string) => {
    setEvents((prev) => {
      if (!prev[taskId]) return prev;
      const next = { ...prev };
      delete next[taskId];
      return next;
    });
  }, []);

  const actions = useMemo(
    () => Array.from(new Set(tasks.map((task) => task.action_key ?? task.task_type))).sort(),
    [tasks],
  );

  const filteredTasks = useMemo(
    () =>
      tasks.filter((task) => {
        const action = task.action_key ?? task.task_type;
        return (
          (statusFilter === "all" || task.status === statusFilter) &&
          (actionFilter === "all" || action === actionFilter)
        );
      }),
    [actionFilter, statusFilter, tasks],
  );

  const selectedTask = useMemo<TaskState | null>(
    () => filteredTasks.find((task) => task.task_id === selectedTaskId) ?? filteredTasks[0] ?? null,
    [filteredTasks, selectedTaskId],
  );

  const selectedEvents = useMemo(() => {
    if (!selectedTask) return [];
    const liveEvents = events[selectedTask.task_id] ?? [];
    const snapshot = [
      `${t("console.tasks.snapshotStatus")}: ${selectedTask.status}`,
      `${t("console.tasks.snapshotCreated")}: ${selectedTask.created_at}`,
      selectedTask.result_paths.length > 0
        ? `${t("console.tasks.snapshotOutputs")}: ${selectedTask.result_paths.join(", ")}`
        : "",
      selectedTask.error ? `${t("console.tasks.snapshotError")}: ${selectedTask.error}` : "",
    ].filter(Boolean);
    return liveEvents.length > 0 ? liveEvents : snapshot;
  }, [events, selectedTask, t]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    tasks.filter((task) => ACTIVE_STATUSES.has(task.status)).forEach((task) => {
      trackTask(task.task_id);
    });
  }, [open, tasks, trackTask]);

  useEffect(() => {
    tasks.filter((task) => TERMINAL_STATUSES.has(task.status)).forEach((task) => {
      clearTaskEvents(task.task_id);
    });
  }, [clearTaskEvents, tasks]);

  useEffect(() => {
    setShowFailureDetails(false);
  }, [selectedTaskId]);

  useEffect(() => {
    if (!open || !selectedTask) return undefined;
    if (TERMINAL_STATUSES.has(selectedTask.status)) return undefined;

    const source = subscribeTask(selectedTask.task_id, (event) => {
      setEvents((prev) => ({
        ...prev,
        [selectedTask.task_id]: [...(prev[selectedTask.task_id] ?? []), event.data],
      }));
      try {
        const payload = JSON.parse(event.data);
        const status = payload?.status as TaskStatus | undefined;
        if (status && TERMINAL_STATUSES.has(status)) {
          clearTaskEvents(selectedTask.task_id);
          source.close();
        }
        if (payload?.type === "done" || payload?.type === "error") {
          clearTaskEvents(selectedTask.task_id);
          refresh();
          source.close();
        }
      } catch {
        // Keep the raw event in the log even if it is not JSON.
      }
    });

    return () => source.close();
  }, [clearTaskEvents, open, refresh, selectedTask]);

  function copyText(text: string) {
    if (!text) return;
    void navigator.clipboard?.writeText(text);
  }

  if (!open) return null;
  return (
    <aside
      data-testid="task-drawer"
      className="fixed right-0 top-0 z-40 h-full w-[460px] max-w-[92vw] overflow-y-auto border-l border-terminal-border bg-terminal-surface shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-terminal-border p-4">
        <h3 className="font-semibold">{t("console.tasks.drawerTitle")} - {pageKey}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("console.tasks.close")}
          title={t("console.tasks.close")}
          className="grid h-8 w-8 place-items-center border border-terminal-border text-terminal-text-dim hover:bg-terminal-raised"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="grid gap-0 md:grid-cols-[1fr_1.1fr]">
        <div className="max-h-[calc(100vh-65px)] overflow-y-auto border-r">
          <div className="grid gap-2 border-b border-terminal-border p-3 text-xs">
            <label className="grid gap-1">
              <span className="text-terminal-text-dim">{t("console.tasks.statusFilter")}</span>
              <select
                className="border px-2 py-1"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as "all" | TaskStatus)}
              >
                <option value="all">{t("console.tasks.allStatuses")}</option>
                {(["pending", "running", "done", "failed", "cancelled"] as TaskStatus[]).map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1">
              <span className="text-terminal-text-dim">{t("console.tasks.actionFilter")}</span>
              <select
                className="border px-2 py-1"
                value={actionFilter}
                onChange={(event) => setActionFilter(event.target.value)}
              >
                <option value="all">{t("console.tasks.allActions")}</option>
                {actions.map((action) => (
                  <option key={action} value={action}>{action}</option>
                ))}
              </select>
            </label>
          </div>
          <ul className="divide-y">
            {filteredTasks.length === 0 && <li className="p-4 text-sm text-terminal-text-dim">{t("console.tasks.empty")}</li>}
            {filteredTasks.map((task) => (
              <li key={task.task_id} className="p-3">
                <div className="flex items-center justify-between gap-3">
                  <TaskChip task={task} onClick={() => setSelectedTaskId(task.task_id)} />
                  {task.status === "running" && (
                    <button
                      type="button"
                      onClick={() => cancelTask(task.task_id).then(refresh)}
                      className="text-xs text-red-600"
                    >
                      {t("console.tasks.cancel")}
                    </button>
                  )}
                </div>
                <div className="mt-1 text-xs text-terminal-text-dim">{task.created_at}</div>
                {task.result_paths.length > 0 && (
                  <ul className="mt-1 list-disc pl-4 text-xs text-terminal-cyan">
                    {task.result_paths.map((path) => (
                      <li key={path} className="break-all">{path}</li>
                    ))}
                  </ul>
                )}
                {task.error && <div className="mt-1 text-xs text-red-600">{task.error}</div>}
              </li>
            ))}
          </ul>
        </div>
        <section className="space-y-4 p-4" data-testid="task-drawer-detail">
          {selectedTask ? (
            <>
              <div>
                <h4 className="mb-2 font-semibold">{t("console.tasks.details")}</h4>
                <dl className="grid grid-cols-[90px_1fr] gap-2 text-xs">
                  <dt className="text-terminal-text-dim">{t("console.tasks.taskId")}</dt>
                  <dd className="flex items-center gap-2 font-mono">
                    <span className="break-all">{selectedTask.task_id}</span>
                    <button
                      type="button"
                      onClick={() => copyText(selectedTask.task_id)}
                      aria-label={t("console.tasks.copyTaskId")}
                      title={t("console.tasks.copyTaskId")}
                      className="grid h-6 w-6 shrink-0 place-items-center border border-terminal-border text-terminal-text-dim hover:bg-terminal-raised"
                    >
                      <Copy className="h-3 w-3" />
                    </button>
                  </dd>
                  <dt className="text-terminal-text-dim">{t("console.tasks.action")}</dt>
                  <dd>{selectedTask.action_key ?? selectedTask.task_type}</dd>
                  <dt className="text-terminal-text-dim">{t("console.tasks.status")}</dt>
                  <dd>{selectedTask.status}</dd>
                  <dt className="text-terminal-text-dim">{t("console.tasks.createdAt")}</dt>
                  <dd>{selectedTask.created_at}</dd>
                  {selectedTask.result_paths.length > 0 && (
                    <>
                      <dt className="text-terminal-text-dim">{t("console.tasks.outputs")}</dt>
                      <dd className="space-y-1">
                        {selectedTask.result_paths.map((path) => (
                          <div key={path} className="flex items-start gap-2">
                            <span className="break-all font-mono">{path}</span>
                            <button
                              type="button"
                              onClick={() => copyText(path)}
                              aria-label={t("console.tasks.copyPath")}
                              title={t("console.tasks.copyPath")}
                              className="grid h-6 w-6 shrink-0 place-items-center border border-terminal-border text-terminal-text-dim hover:bg-terminal-raised"
                            >
                              <Copy className="h-3 w-3" />
                            </button>
                          </div>
                        ))}
                      </dd>
                    </>
                  )}
                </dl>
              </div>
              {selectedTask.error && (
                <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                  <button
                    type="button"
                    onClick={() => setShowFailureDetails((value) => !value)}
                    className="font-semibold"
                  >
                    {t("console.tasks.failureDetails")}
                  </button>
                  {showFailureDetails && (
                    <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words">
                      {selectedTask.error}
                    </pre>
                  )}
                </div>
              )}
              <div>
                <h4 className="mb-2 font-semibold">{t("console.tasks.result")}</h4>
                <pre className="max-h-48 overflow-auto bg-terminal-raised p-2 text-xs">
                  {JSON.stringify(selectedTask.result ?? selectedTask.error ?? {}, null, 2)}
                </pre>
              </div>
              <div>
                <h4 className="mb-2 font-semibold">{t("console.tasks.events")}</h4>
                {selectedEvents.length === 0 ? (
                  <p className="text-xs text-terminal-text-dim">{t("console.tasks.noEvents")}</p>
                ) : (
                  <pre className="max-h-48 overflow-auto bg-terminal-raised p-2 text-xs">
                    {selectedEvents.join("\n")}
                  </pre>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-terminal-text-dim">{t("console.tasks.empty")}</p>
          )}
        </section>
      </div>
    </aside>
  );
}
