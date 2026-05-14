import type { TaskState } from "./types";

export type TaskTrigger<TPreview = unknown> = {
  task_id: string;
  dry_run: boolean;
  preview: TPreview | null;
};

const BASE = "/api/system";

export async function listTasks(): Promise<TaskState[]> {
  const response = await fetch(`${BASE}/tasks`);
  if (!response.ok) throw new Error(`listTasks failed: ${response.status}`);
  return response.json();
}

export function subscribeTask(
  taskId: string,
  onMessage: (ev: MessageEvent) => void,
): EventSource {
  const source = new EventSource(`${BASE}/tasks/${taskId}/stream`);
  source.onmessage = onMessage;
  return source;
}

export async function cancelTask(taskId: string): Promise<void> {
  const response = await fetch(`${BASE}/tasks/${taskId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`cancelTask failed: ${response.status}`);
}
