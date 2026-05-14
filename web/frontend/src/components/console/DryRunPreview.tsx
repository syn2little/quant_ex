import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export type DryRunPreviewProps = {
  loading?: boolean;
  error?: string | null;
  preview: unknown;
  renderPreview?: (preview: unknown) => ReactNode;
};

export function DryRunPreview({
  loading,
  error,
  preview,
  renderPreview,
}: DryRunPreviewProps) {
  const { t } = useTranslation();

  if (loading) return <div data-testid="dry-run-loading">{t("common.loading")}</div>;
  if (error) {
    return (
      <div data-testid="dry-run-error" className="rounded border border-red-200 bg-red-50 p-3 text-red-700">
        {error}
      </div>
    );
  }
  if (!preview) return null;
  return (
    <div data-testid="dry-run-preview" className="rounded border border-slate-200 bg-slate-50 p-3">
      {renderPreview ? (
        renderPreview(preview)
      ) : (
        <pre className="overflow-auto text-xs leading-5">{JSON.stringify(preview, null, 2)}</pre>
      )}
    </div>
  );
}
