import type { AllergyRecord, AllergyState } from "../types";

export const ALLERGEN_TYPES = [
  { value: "DRUG", label: "Medicine" },
  { value: "FOOD", label: "Food" },
  { value: "ENVIRONMENT", label: "Environment" },
  { value: "OTHER", label: "Other" },
] as const;

export const ALLERGY_SEVERITIES = [
  { value: "", label: "Not recorded" },
  { value: "MILD", label: "Mild" },
  { value: "MODERATE", label: "Moderate" },
  { value: "SEVERE", label: "Severe" },
] as const;

export interface AllergyDraft {
  allergenType: string;
  allergenName: string;
  codedAllergenUuid: string;
  severity: string;
  reaction: string;
  comment: string;
}

export function emptyAllergyDraft(): AllergyDraft {
  return {
    allergenType: "DRUG",
    allergenName: "",
    codedAllergenUuid: "",
    severity: "",
    reaction: "",
    comment: "",
  };
}

export function draftFromRecord(row: AllergyRecord): AllergyDraft {
  const severity = ALLERGY_SEVERITIES.find(
    (item) => item.label.toLowerCase() === row.severity.toLowerCase(),
  );
  return {
    allergenType: row.allergenType || "OTHER",
    allergenName: row.allergen,
    codedAllergenUuid: "",
    severity: severity?.value || "",
    reaction: row.reactions[0] || "",
    comment: row.comment,
  };
}

export function validateAllergyDraft(draft: AllergyDraft): string {
  if (!ALLERGEN_TYPES.some((item) => item.value === draft.allergenType)) {
    return "Choose whether this is a medicine, food, environment, or other allergy.";
  }
  if (!draft.allergenName.trim()) {
    return "Enter the substance the patient reacts to.";
  }
  return "";
}

export function allergyStateFromPayload(payload: {
  canWrite?: boolean;
  allergies?: AllergyRecord[];
}): AllergyState {
  const records = (payload.allergies || []).filter((row) => row.uuid && row.allergen);
  const canWrite = Boolean(payload.canWrite);
  if (records.length === 0) {
    return { status: "none-recorded", canWrite };
  }
  return {
    status: "recorded",
    items: records.map((row) => row.display || row.allergen),
    records,
    canWrite,
  };
}

export function allergyNames(allergy: AllergyState): string {
  if (allergy.status !== "recorded") {
    return "";
  }
  return allergy.items.join(", ");
}
