/** Staff-facing visit wording only. OpenMRS visit type names stay unchanged. */

export const RECEPTION_START_VISIT_TYPES = [
  "OPD",
  "ANC",
  "Follow Up",
  "Nursing Treatment",
  "EMERGENCY",
  "IPD",
] as const;

export type ReceptionStartVisitType = (typeof RECEPTION_START_VISIT_TYPES)[number];

export const RECEPTION_VISIT_TYPE_COPY: Record<string, { label: string; helper: string }> = {
  OPD: {
    label: "General Outpatient",
    helper: "Regular outpatient consultation",
  },
  "Follow Up": {
    label: "Follow-up",
    helper: "Returning for a previous treatment or condition",
  },
  "Nursing Treatment": {
    label: "Nursing Treatment",
    helper: "Medicine, injection, wound care, or another planned nursing treatment",
  },
  EMERGENCY: {
    label: "Emergency",
    helper: "Urgent care",
  },
  IPD: {
    label: "Admission",
    helper: "Patient is being admitted",
  },
  ANC: {
    label: "Antenatal Care (ANC)",
    helper: "Antenatal clinic visit for pregnancy care",
  },
};

export function isReceptionStartVisitType(name: string | undefined): boolean {
  const key = (name || "").trim();
  return (RECEPTION_START_VISIT_TYPES as readonly string[]).includes(key);
}

/** Create Visit / first hospital visit — ANC belongs on Antenatal Care, not here. */
export function isGeneralReceptionVisitType(name: string | undefined): boolean {
  const key = (name || "").trim();
  return key.toUpperCase() !== "ANC" && isReceptionStartVisitType(key);
}

export function receptionVisitTypeLabel(name: string | undefined): string {
  const key = (name || "").trim();
  if (key === "Special OPD") {
    return "Retrospective visit";
  }
  return RECEPTION_VISIT_TYPE_COPY[key]?.label || key;
}

/** Existing OpenMRS outpatient location already used by Clinical. Not a new identity. */
export const DEFAULT_OUTPATIENT_LOCATION_NAME = "OPD-1";

export function receptionAsksForLocation(visitName: string | undefined): boolean {
  return (visitName || "").trim() === "IPD";
}

export function receptionLocationChoiceMode(
  visitName: string | undefined,
  count: number,
): "none" | "auto" | "choose" {
  if (count <= 0) {
    return "none";
  }
  if (!receptionAsksForLocation(visitName)) {
    return "auto";
  }
  if (count === 1) {
    return "auto";
  }
  return "choose";
}
