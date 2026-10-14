import { CONSULTATION_ENCOUNTER_TYPE } from "../../config/clinicalConcepts.ts";

export const MISSING_ATTENDING_DOCTOR = "—";

export interface VisitEncounterProviderSource {
  uuid?: string;
  encounterDatetime?: string;
  encounterType?: { uuid?: string; name?: string };
  encounterProviders?: Array<{
    encounterRole?: { display?: string };
    provider?: {
      uuid?: string;
      display?: string;
      person?: { display?: string };
    };
  }>;
}

function isConsultationEncounter(row: VisitEncounterProviderSource): boolean {
  return (
    row.encounterType?.uuid === CONSULTATION_ENCOUNTER_TYPE ||
    row.encounterType?.name === "Consultation"
  );
}

/** Staff-facing name only. Never use a login id such as doctor.abikan. */
export function attendingDoctorName(
  provider:
    | {
        display?: string;
        person?: { display?: string };
      }
    | undefined,
): string | null {
  const person = (provider?.person?.display || "").trim();
  if (person) {
    return person;
  }
  const display = (provider?.display || "").trim();
  if (!display || /\bnull\b/i.test(display)) {
    return null;
  }
  const separator = display.indexOf(" - ");
  if (separator >= 0) {
    const name = display.slice(separator + 3).trim();
    return name && !/\bnull\b/i.test(name) ? name : null;
  }
  return display;
}

/**
 * Provider on the latest Consultation encounter for this visit.
 * Does not use the logged-in doctor, another visit, or a laboratory encounter.
 */
export function attendingDoctorFromVisitEncounters(
  encounters: VisitEncounterProviderSource[] | undefined,
): string {
  const consultations = (encounters ?? [])
    .filter((row) => Boolean(row.uuid) && isConsultationEncounter(row))
    .sort((left, right) =>
      (right.encounterDatetime || "").localeCompare(left.encounterDatetime || ""),
    );
  const latest = consultations[0];
  if (!latest) {
    return MISSING_ATTENDING_DOCTOR;
  }
  for (const row of latest.encounterProviders ?? []) {
    const name = attendingDoctorName(row.provider);
    if (name) {
      return name;
    }
  }
  return MISSING_ATTENDING_DOCTOR;
}

export function attendedByLabel(value: string | undefined): string {
  const name = (value || "").trim();
  return name && name !== MISSING_ATTENDING_DOCTOR ? name : MISSING_ATTENDING_DOCTOR;
}
