import type { AllergyState, DiagnosisRecord, DrugOrderSummary } from "../types";
import "./ClinicalAlertBar.css";

interface ClinicalAlertBarProps {
  allergy: AllergyState;
  diagnoses: DiagnosisRecord[];
  diagnosesUnavailable?: boolean;
  medications: DrugOrderSummary[];
  medicationsUnavailable?: boolean;
}

function allergyCopy(allergy: AllergyState): { text: string; tone: "warn" | "muted" } {
  if (allergy.status === "recorded") {
    const labels = allergy.records?.length
      ? allergy.records.map((row) => row.display || row.allergen)
      : allergy.items;
    return { text: labels.join(", "), tone: "warn" };
  }
  if (allergy.status === "unavailable") {
    return { text: "Allergy record unavailable", tone: "muted" };
  }
  return { text: "Not recorded", tone: "muted" };
}

export function ClinicalAlertBar({
  allergy,
  diagnoses,
  diagnosesUnavailable,
  medications,
  medicationsUnavailable,
}: ClinicalAlertBarProps) {
  const allergyLine = allergyCopy(allergy);
  const diagnosisText = diagnosesUnavailable
    ? "Diagnoses unavailable"
    : diagnoses.length > 0
      ? diagnoses.map((row) => row.display).join(", ")
      : "None recorded";
  const currentMedications = medications.filter(
    (row) => !row.status || row.status === "Ordered",
  );
  const medicationText = medicationsUnavailable
    ? "Medications unavailable"
    : currentMedications.length > 0
      ? currentMedications.map((row) => row.drugName || row.display).join(", ")
      : "No current medications recorded";

  return (
    <section className="abikan-alerts" aria-label="Important clinical information">
      <div className={`abikan-alerts__item ${allergy.status === "recorded" ? "is-recorded" : ""}`}>
        <p className="abikan-alerts__label">Allergies</p>
        <p className={`abikan-alerts__value abikan-alerts__value--${allergyLine.tone}`}>
          {allergyLine.text}
        </p>
      </div>
      <div className={`abikan-alerts__item ${diagnoses.length > 0 ? "is-recorded" : ""}`}>
        <p className="abikan-alerts__label">Known diagnoses</p>
        <p className="abikan-alerts__value">{diagnosisText}</p>
      </div>
      <div className={`abikan-alerts__item ${currentMedications.length > 0 ? "is-recorded" : ""}`}>
        <p className="abikan-alerts__label">Current medications</p>
        <p className="abikan-alerts__value">{medicationText}</p>
      </div>
    </section>
  );
}
