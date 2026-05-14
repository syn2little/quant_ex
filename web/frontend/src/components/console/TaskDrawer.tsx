import { useEffect } from "react";
import { cancelTask } from "../../api/tasks";
import { useTaskTracking } from "../../hooks/useTaskTracking";
import { TaskChip } from "./TaskChip";

export type TaskDrawerProps = {
  pageKey: string;
  taskTypeFilter: string[];
  open: boolean;
  onClose: () => void;
};

export function TaskDrawer({ pageKey, taskTypeFilter, open, onClose }: TaskDrawerProps) {
  const { tasks, refresh } = useTaskTracking({ pageKey, taskTypeFilter });

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  if (!open) return null;
  return (
    <aside
      data-testid="task-drawer"
      className="fixed right-0 top-0 z-40 h-full w-[420px] max-w-[92vw] overflow-y-auto border-l bg-white shadow-xl"
    >
      <div className="flex items-center justify-between border-b p-4">
        <h3 className="font-semibold">Tasks - {pageKey}</h3>
        <button type="button" onClick={onClose} aria-label="Close task drawer">
          x
        </button>
      </div>
      <ul className="divide-y">
        {tasks.length === 0 && <li className="p-4 text-sm text-slate-500">No tasks yet.</li>}
        {tasks.map((task) => (
          <li key={task.task_id} className="p-3">
            <div className="flex items-center justify-between gap-3">
              <TaskChip task={task} />
              {task.status === "running" && (
                <button
                  type="button"
                  onClick={() => cancelTask(task.task_id).then(refresh)}
                  className="text-xs text-red-600"
                >
                  cancel
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
    </aside>
  );
}
