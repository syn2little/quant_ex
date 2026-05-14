import type { TaskState } from "../../api/types";

export function TaskChip({ task, onClick }: { task: TaskState; onClick?: () => void }) {
  const color =
    {
      pending: "bg-slate-200 text-slate-700",
      running: "bg-blue-200 text-blue-800",
      done: "bg-green-200 text-green-800",
      failed: "bg-red-200 text-red-800",
      cancelled: "bg-amber-200 text-amber-800",
    }[task.status] ?? "bg-slate-200 text-slate-700";

  return (
    <button
      type="button"
      data-testid={`task-chip-${task.task_id}`}
      onClick={onClick}
      className={`rounded px-2 py-0.5 text-xs ${color}`}
    >
      {task.action_key ?? task.task_type} - {task.status}
    </button>
  );
}
