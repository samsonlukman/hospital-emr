import type { ReactNode } from "react";
import { Button } from "./Button";
import "./CardTypeDialog.css";

interface ConfirmDialogProps {
  title: string;
  description: ReactNode;
  confirmLabel: string;
  busyLabel?: string;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  busyLabel,
  busy = false,
  error,
  onClose,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="abikan-confirm-title">
      <div className="abikan-dialog__panel">
        <h2 id="abikan-confirm-title">{title}</h2>
        {typeof description === "string" ? <p>{description}</p> : description}
        {error ? <p className="abikan-dialog__error">{error}</p> : null}
        <div className="abikan-dialog__actions">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" busy={busy} busyLabel={busyLabel} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
