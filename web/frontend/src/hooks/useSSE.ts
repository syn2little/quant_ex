import { useState, useEffect, useRef, useCallback } from "react";

export interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}

export function useSSE(taskId: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [status, setStatus] = useState<"idle" | "streaming" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStatus("done");
  }, []);

  useEffect(() => {
    if (!taskId) return;

    setEvents([]);
    setStatus("streaming");
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;

    fetch(`/api/system/tasks/${taskId}/stream`, { signal: controller.signal })
      .then((res) => {
        const reader = res.body?.getReader();
        if (!reader) throw new Error("No readable stream");
        const decoder = new TextDecoder();
        let buffer = "";

        function read(): Promise<void> {
          return reader!.read().then(({ done, value }) => {
            if (done) {
              setStatus("done");
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const event: SSEEvent = JSON.parse(line.slice(6));
                  setEvents((prev) => [...prev, event]);
                  if (event.type === "error") {
                    setError(event.data.message as string);
                    setStatus("error");
                  }
                  if (event.type === "done") {
                    setStatus("done");
                  }
                } catch {
                  // skip malformed lines
                }
              }
            }
            return read();
          });
        }
        return read();
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError(err.message);
          setStatus("error");
        }
      });

    return () => controller.abort();
  }, [taskId]);

  return { events, status, error, stop };
}
