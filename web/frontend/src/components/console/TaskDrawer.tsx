import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { cancelTask, subscribeTask } from "../../api/tasks";
import { useTaskTracking } from "../../hooks/useTaskTracking";
import type { TaskState } from "../../api/types";
import { TaskChip } from "./TaskChip";

export type TaskDrawerProps = {
  pageKey: string;
  taskTypeFilter: string[];
  open: boolean;
  onClose: () => void;
};

export function TaskDrawer({ pageKey, taskTypeFilter, open, onClose }: TaskDrawerProps) {
  const { t } = useTranslation();
  const { tasks, refresh } = useTaskTracking({ pageKey, taskTypeFilter });
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<Record<string, string[]>>({});

  const selectedTask = useMemo<TaskState | null>(
    () => tasks.find((task) => task.task_id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open || !selectedTask) return undefined;
    const terminal = new Set(["done", "failed", "cancelled"]);
    if (terminal.has(selectedTask.status)) return undefined;

    const source = subscribeTask(selectedTask.task_id, (event) => {
      setEvents((prev) => ({
        ...prev,
        [selectedTask.task_id]: [...(prev[selectedTask.task_id] ?? []), event.data],
      }));
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === "done" || payload?.type === "error") {
          refresh();
          source.close();
        }
      } catch {
        // Keep the raw event in the log even if it is not JSON.
      }
    });

    return () => source.close();
  }, [open, refresh, selectedTask]);

  if (!open) return null;
  return (
    <aside
      data-testid="task-drawer"
      className="fixed right-0 top-0 z-40 h-full w-[420px] max-w-[92vw] overflow-y-auto border-l bg-white shadow-xl"
    >
      <div className="flex items-center justify-between border-b p-4">
        <h3 className="font-semibold">{t("console.tasks.drawerTitle")} - {pageKey}</h3>
        <button type="button" onClick={onClose} aria-label={t("console.tasks.close")}>
          x
        </button>
      </div>
      <div className="grid gap-0 md:grid-cols-[1fr_1.1fr]">
        <ul className="max-h-[calc(100vh-65px)] divide-y overflow-y-auto border-r">
          {tasks.length === 0 && <li className="p-4 text-sm text-slate-500">{t("console.tasks.empty")}</li>}
          {tasks.map((task) => (
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
              <div className="mt-1 text-xs text-slate-500">{task.created_at}</div>
              {task.result_paths.length > 0 && (
                <ul className="mt-1 list-disc pl-4 text-xs text-blue-700">
                  {task.result_paths.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
              )}
              {task.error && <div className="mt-1 text-xs text-red-600">{task.error}</div>}
            </li>
          ))}
        </ul>
        <section className="space-y-4 p-4" data-testid="task-drawer-detail">
          {selectedTask ? (
            <>
              <div>
                <h4 className="mb-2 font-semibold">{t("console.tasks.details")}</h4>
                <dl className="grid grid-cols-[90px_1fr] gap-2 text-xs">
                  <dt className="text-slate-500">{t("console.tasks.taskId")}</dt>
                  <dd className="font-mono">{selectedTask.task_id}</dd>
                  <dt className="text-slate-500">{t("console.tasks.action")}</dt>
                  <dd>{selectedTask.action_key ?? selectedTask.task_type}</dd>
                  <dt className="text-slate-500">{t("console.tasks.status")}</dt>
                  <dd>{selectedTask.status}</dd>
                  <dt className="text-slate-500">{t("console.tasks.createdAt")}</dt>
                  <dd>{selectedTask.created_at}</dd>
                </dl>
              </div>
              <div>
                <h4 className="mb-2 font-semibold">{t("console.tasks.result")}</h4>
                <pre className="max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs">
                  {JSON.stringify(selectedTask.result ?? selectedTask.error ?? {}, null, 2)}
                </pre>
              </div>
              <div>
                <h4 className="mb-2 font-semibold">{t("console.tasks.events")}</h4>
                {(events[selectedTask.task_id] ?? []).length === 0 ? (
                  <p className="text-xs text-slate-500">{t("console.tasks.noEvents")}</p>
                ) : (
                  <pre className="max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs">
                    {(events[selectedTask.task_id] ?? []).join("\n")}
                  </pre>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">{t("console.tasks.empty")}</p>
          )}
        </section>
      </div>
    </aside>
  );
}
