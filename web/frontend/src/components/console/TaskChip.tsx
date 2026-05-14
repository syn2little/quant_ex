import type { TaskState } from "../../api/types";

export function TaskChip({ task, onClick }: { task: TaskState; onClick?: () => void }) {
  const color =
    {
      pending: "bg-terminal-raised text-terminal-text",
      running: "bg-terminal-cyan-glow text-terminal-cyan",
      done: "bg-terminal-green-glow text-terminal-green",
      failed: "bg-terminal-red-glow text-terminal-red",
      cancelled: "bg-terminal-amber-glow text-terminal-amber",
    }[task.status] ?? "bg-terminal-raised text-terminal-text";

  return (
    <button
      type="button"
      data-testid={`task-chip-${task.task_id}`}
      onClick={onClick}
      className={`border border-transparent px-2 py-0.5 text-xs ${color}`}
    >
      {task.action_key ?? task.task_type} - {task.status}
    </button>
  );
}
