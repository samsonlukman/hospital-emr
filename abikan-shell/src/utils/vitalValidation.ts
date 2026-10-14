import { VITAL_CONCEPTS, type VitalConceptKey } from "../config/clinicalConcepts.ts";
import type { VitalDraftValues } from "../services/openmrs/clinicalEncounter.ts";

export type FieldIssue = { level: "block" | "warn"; message: string };

export function parseVitalInput(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (!trimmed) {
    return undefined;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

export function validateVitalField(
  key: VitalConceptKey,
  raw: string,
): FieldIssue | null {
  const parsed = parseVitalInput(raw);
  if (parsed === undefined) {
    return null;
  }
  if (Number.isNaN(parsed)) {
    return { level: "block", message: "Enter a number" };
  }
  const concept = VITAL_CONCEPTS[key];
  if (parsed < concept.lowAbsolute || parsed > concept.hiAbsolute) {
    return {
      level: "block",
      message: `Must be between ${concept.lowAbsolute} and ${concept.hiAbsolute} ${concept.unit}`,
    };
  }
  if (concept.lowNormal != null && parsed < concept.lowNormal) {
    return { level: "warn", message: `Below usual range (${concept.lowNormal}–${concept.hiNormal ?? "—"})` };
  }
  if (concept.hiNormal != null && parsed > concept.hiNormal) {
    return { level: "warn", message: `Above usual range (${concept.lowNormal ?? "—"}–${concept.hiNormal})` };
  }
  return null;
}

export function validateVitalDraft(
  values: VitalDraftValues,
  raw: Record<VitalConceptKey, string>,
): { blocking: string[]; warnings: string[] } {
  const blocking: string[] = [];
  const warnings: string[] = [];
  (Object.keys(VITAL_CONCEPTS) as VitalConceptKey[]).forEach((key) => {
    const issue = validateVitalField(key, raw[key]);
    if (!issue) {
      return;
    }
    const label = VITAL_CONCEPTS[key].label;
    if (issue.level === "block") {
      blocking.push(`${label}: ${issue.message}`);
    } else {
      warnings.push(`${label}: ${issue.message}`);
    }
  });
  if (
    values.systolic != null &&
    values.diastolic != null &&
    values.systolic <= values.diastolic
  ) {
    blocking.push("Systolic pressure must be higher than diastolic");
  }
  if (Boolean(raw.systolic.trim()) !== Boolean(raw.diastolic.trim())) {
    blocking.push("Enter both systolic and diastolic pressure");
  }
  if (Object.values(values).every((value) => value === undefined)) {
    blocking.push("Enter at least one vital sign");
  }
  return { blocking, warnings };
}

export function draftBmi(values: VitalDraftValues): string | null {
  if (values.weight == null || values.height == null || values.height <= 0) {
    return null;
  }
  const metres = values.height / 100;
  return (values.weight / (metres * metres)).toFixed(1);
}
