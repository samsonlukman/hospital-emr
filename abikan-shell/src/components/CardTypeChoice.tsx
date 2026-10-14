import { REGISTRATION_CARDS, rememberCardType } from "../config/registrationCharges";
import { openRegistrationRegister } from "../app/hashRoute";
import type { RegistrationCardType } from "../types";
import { IconWell } from "./IconWell";
import "./CardTypeChoice.css";

function startRegistration(cardType: RegistrationCardType) {
  rememberCardType(cardType);
  openRegistrationRegister();
}

export function CardTypeChoice() {
  return (
    <div className="abikan-card-types">
      <button
        type="button"
        className="abikan-card-type abikan-card-type--registration"
        onClick={() => startRegistration("individual")}
      >
        <IconWell name="user" tone="registration" size="md" />
        <span>
          <strong>{REGISTRATION_CARDS.individual.label}</strong>
          <em>For a single patient</em>
        </span>
      </button>
      <button
        type="button"
        className="abikan-card-type abikan-card-type--appointments"
        onClick={() => startRegistration("family")}
      >
        <IconWell name="users" tone="appointments" size="md" />
        <span>
          <strong>{REGISTRATION_CARDS.family.label}</strong>
          <em>For family registration</em>
        </span>
      </button>
      <p className="abikan-card-types__note">
        The registration fee is created after the patient is registered, then paid at
        Accountant. Reception does not collect payment.
      </p>
    </div>
  );
}
