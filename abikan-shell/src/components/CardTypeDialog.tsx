import { REGISTRATION_CARDS, rememberCardType } from "../config/registrationCharges";
import { openRegistrationRegister } from "../app/hashRoute";
import type { RegistrationCardType } from "../types";
import { Button } from "./Button";
import { IconWell } from "./IconWell";
import "./CardTypeDialog.css";

interface CardTypeDialogProps {
  open: boolean;
  onClose: () => void;
}

function startRegistration(cardType: RegistrationCardType) {
  rememberCardType(cardType);
  openRegistrationRegister();
}

export function CardTypeDialog({ open, onClose }: CardTypeDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="card-type-title">
      <div className="abikan-dialog__panel">
        <h2 id="card-type-title">Register Patient</h2>
        <p>Register the patient first. The registration fee is paid at Accountant, not at Reception.</p>
        <div className="abikan-dialog__choices">
          <button
            type="button"
            onClick={() => {
              startRegistration("individual");
              onClose();
            }}
          >
            <IconWell name="user" tone="registration" size="sm" />
            <strong>{REGISTRATION_CARDS.individual.label}</strong>
            <span>One patient</span>
          </button>
          <button
            type="button"
            onClick={() => {
              startRegistration("family");
              onClose();
            }}
          >
            <IconWell name="users" tone="appointments" size="sm" />
            <strong>{REGISTRATION_CARDS.family.label}</strong>
            <span>Family file</span>
          </button>
        </div>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
