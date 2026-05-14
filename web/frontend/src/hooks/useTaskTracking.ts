import { useCallback, useEffect, useRef, useState } from "react";
import { listTasks, subscribeTask } from "../api/tasks";
import type { TaskState } from "../api/types";

export type UseTaskTrackingOptions = {
  pageKey: string;
  taskTypeFilter: string[];
  pollMs?: number;
};

const TERMINAL_STATUSES = new Set(["done", "failed", "cancelled"]);

export function useTaskTracking({
  pageKey,
  taskTypeFilter,
  pollMs = 5000,
}: UseTaskTrackingOptions) {
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const streamsRef = useRef<Record<string, EventSource>>({});

  const refresh = useCallback(async () => {
    const all = await listTasks();
    const filtered = all.filter(
      (task) => task.page_key === pageKey || taskTypeFilter.includes(task.task_type),
    );
    setTasks(filtered);
  }, [pageKey, taskTypeFilter]);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, pollMs);
    return () => window.clearInterval(id);
  }, [refresh, pollMs]);

  const trackTask = useCallback(
    (taskId: string) => {
      window.dispatchEvent(new CustomEvent("console:task-created", { detail: { taskId } }));
      if (streamsRef.current[taskId]) return;
      const source = subscribeTask(taskId, (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (payload?.task_id) {
            setTasks((prev) => {
              const index = prev.findIndex((task) => task.task_id === taskId);
              if (index === -1) return [payload, ...prev];
              const next = [...prev];
              next[index] = { ...next[index], ...payload };
              return next;
            });
          } else {
            refresh();
          }
          const status = payload?.status;
          if (status && TERMINAL_STATUSES.has(status)) {
            source.close();
            delete streamsRef.current[taskId];
          }
          if (payload?.type === "done" || payload?.type === "error") {
            refresh();
            source.close();
            delete streamsRef.current[taskId];
          }
        } catch (error) {
          console.error("SSE parse error", error);
        }
      });
      streamsRef.current[taskId] = source;
    },
    [refresh],
  );

  useEffect(() => {
    return () => {
      Object.values(streamsRef.current).forEach((source) => source.close());
      streamsRef.current = {};
    };
  }, []);

  return { tasks, refresh, trackTask };
}
