import { VITAL_CONCEPTS, type VitalConceptKey } from "../config/clinicalConcepts.ts";
import type { VitalDraftValues } from "../services/openmrs/clinicalEncounter.ts";
import type { InpatientVitalsPayload } from "../types/inpatient.ts";
import type { VitalReading } from "../types/index.ts";
import { formatClinicalWhen } from "./datetime.ts";

export function canRecordInpatientVitals(
  allowed: boolean,
  ready = true,
): boolean {
  return allowed && ready;
}

export function vitalsRequestBody(
  values: VitalDraftValues,
  requestId: string,
): Record<string, number | string> {
  const body: Record<string, number | string> = { requestId };
  (Object.keys(VITAL_CONCEPTS) as VitalConceptKey[]).forEach((key) => {
    const value = values[key];
    if (value != null && Number.isFinite(value)) {
      body[key] = value;
    }
  });
  return body;
}

export function historyFromVitalsPayload(
  payload: InpatientVitalsPayload | null,
): Record<string, VitalReading[]> {
  const history: Record<string, VitalReading[]> = {};
  for (const reading of payload?.readings ?? []) {
    for (const observation of reading.observations) {
      const rows = history[observation.key] ?? [];
      rows.push({
        key: observation.key,
        label: observation.label,
        value: observation.value,
        unit: observation.unit,
        recordedAt: formatClinicalWhen(reading.recordedAt),
        recordedBy: reading.recordedBy,
        recordedAtIso: reading.recordedAt,
      });
      history[observation.key] = rows;
    }
  }
  return history;
}
