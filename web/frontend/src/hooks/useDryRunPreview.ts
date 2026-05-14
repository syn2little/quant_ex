import { useCallback, useState } from "react";

export type UseDryRunPreviewState<TPreview> = {
  loading: boolean;
  preview: TPreview | null;
  error: string | null;
};

export function useDryRunPreview<TParams, TPreview>(
  caller: (params: TParams) => Promise<{
    task_id: string;
    dry_run: boolean;
    preview: TPreview | null;
  }>,
) {
  const [state, setState] = useState<UseDryRunPreviewState<TPreview>>({
    loading: false,
    preview: null,
    error: null,
  });

  const run = useCallback(
    async (params: TParams) => {
      setState({ loading: true, preview: null, error: null });
      try {
        const result = await caller(params);
        setState({ loading: false, preview: result.preview, error: null });
        return result;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setState({ loading: false, preview: null, error: message });
        throw error;
      }
    },
    [caller],
  );

  const reset = useCallback(() => {
    setState({ loading: false, preview: null, error: null });
  }, []);

  return { ...state, run, reset };
}
