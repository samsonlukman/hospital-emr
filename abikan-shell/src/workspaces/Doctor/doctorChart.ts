/** Index order matches the visual order on the consultation page. */
export const CONSULTATION_FLOW = [
  { id: "allergies", label: "Allergies" },
  { id: "anc", label: "ANC Card" },
  { id: "vitals", label: "Vitals" },
  { id: "document", label: "History and Examinations" },
  { id: "visits", label: "Visits" },
  { id: "diagnose", label: "Diagnoses" },
  { id: "laboratory", label: "Lab Investigations" },
  { id: "radiology", label: "Radiology Orders" },
  { id: "prescribe", label: "Treatments" },
  { id: "disposition", label: "Disposition" },
] as const;

export const CLINICAL_BACK_LABEL = "← Clinical";
export const CLINICAL_LOAD_FAIL_BACK_LABEL = "Back to Clinical";

export const PREVIOUS_VISITS_DESCRIPTION =
  "All visits on this chart. Choose one to open it.";

export const LAB_ORDERS_EMPTY_DESCRIPTION =
  "No laboratory orders recorded for this patient.";
