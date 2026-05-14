import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export type ConfirmDialogProps = {
  open: boolean;
  titleKey: string;
  impactSummary: ReactNode;
  confirmLabelKey: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  titleKey,
  impactSummary,
  confirmLabelKey,
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation();

  if (!open) return null;
  return (
    <div
      data-testid="confirm-dialog"
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="w-[480px] max-w-[90vw] rounded-lg bg-white p-6 shadow-xl">
        <h3 className="mb-3 text-lg font-semibold" data-i18n={titleKey}>
          {t(titleKey)}
        </h3>
        <div className="mb-4 text-sm text-slate-700">{impactSummary}</div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded border px-3 py-1.5">
            {t("console.common.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            data-testid="confirm-dialog-confirm"
            className={`rounded px-3 py-1.5 text-white ${
              destructive ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {t(confirmLabelKey)}
          </button>
        </div>
      </div>
    </div>
  );
}
