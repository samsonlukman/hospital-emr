import type {
  AllergyState,
  ConditionSummary,
  EncounterSummary,
  PatientIdentity,
  PatientVisitSummary,
  VitalReading,
} from "../../types";
import { VITAL_CONCEPTS } from "../../config/clinicalConcepts";
import { dailyVisitNumberFromAttributes } from "../../utils/dailyVisitNumber";
import { formatClock, formatClinicalWhen, formatDate } from "../../utils/datetime";
import { attendingDoctorFromVisitEncounters } from "./visitAttendingProvider.ts";
import { openmrsGet } from "./client";
import { fetchDrugOrders } from "./drugOrders";
import { fetchAllergyRecord } from "../allergies";

export { fetchDrugOrders };

interface PatientResponse {
  uuid: string;
  display?: string;
  identifiers?: Array<{ identifier?: string }>;
  person?: {
    display?: string;
    gender?: string;
    age?: number;
    birthdate?: string;
    preferredName?: { givenName?: string; familyName?: string };
  };
}

function sexLabel(gender?: string): string {
  if (gender === "M") {
    return "Male";
  }
  if (gender === "F") {
    return "Female";
  }
  return gender || "—";
}

export function parsePatientDisplay(display?: string): { mrn: string; name: string } {
  const value = (display || "").trim();
  const parts = value.split(" - ");
  if (parts.length >= 2) {
    return { mrn: parts[0].trim(), name: parts.slice(1).join(" - ").trim() };
  }
  return { mrn: "—", name: value || "Unknown patient" };
}

export async function fetchPatientIdentity(uuid: string): Promise<PatientIdentity> {
  const patient = await openmrsGet<PatientResponse>(
    `/openmrs/ws/rest/v1/patient/${uuid}?v=custom:(uuid,display,identifiers:(identifier),person:(display,gender,age,birthdate,preferredName:(givenName,familyName)))`,
  );
  const given = patient.person?.preferredName?.givenName ?? "";
  const family = patient.person?.preferredName?.familyName ?? "";
  const name =
    `${given} ${family}`.trim() ||
    patient.person?.display ||
    parsePatientDisplay(patient.display).name;
  return {
    uuid: patient.uuid,
    name,
    mrn: patient.identifiers?.[0]?.identifier || parsePatientDisplay(patient.display).mrn,
    age: patient.person?.age != null ? String(patient.person.age) : "—",
    sex: sexLabel(patient.person?.gender),
    birthdate: formatDate(patient.person?.birthdate),
  };
}

const VISIT_REPRESENTATION =
  "custom:(uuid,startDatetime,stopDatetime,visitType:(name),location:(name),patient:(uuid),attributes:(value,display,attributeType:(name)),encounters:(uuid,encounterDatetime,encounterType:(uuid,name),encounterProviders:(provider:(uuid,display,person:(display)))))";

interface VisitRecord {
  uuid: string;
  startDatetime?: string;
  stopDatetime?: string;
  visitType?: { name?: string };
  location?: { name?: string };
  patient?: { uuid?: string };
  attributes?: Array<{
    value?: string;
    display?: string;
    attributeType?: { uuid?: string; name?: string };
  }>;
  encounters?: Array<{
    uuid?: string;
    encounterDatetime?: string;
    encounterType?: { uuid?: string; name?: string };
    encounterProviders?: Array<{
      provider?: {
        uuid?: string;
        display?: string;
        person?: { display?: string };
      };
    }>;
  }>;
}

interface VisitListResponse {
  results: VisitRecord[];
}

function mapVisitSummary(visit: VisitRecord): PatientVisitSummary {
  return {
    uuid: visit.uuid,
    start: formatClock(visit.startDatetime),
    startDate: formatDate(visit.startDatetime),
    startDatetime: visit.startDatetime || "",
    stop: visit.stopDatetime ? formatClock(visit.stopDatetime) : null,
    visitType: visit.visitType?.name || "—",
    location: visit.location?.name || "—",
    open: !visit.stopDatetime,
    dailyVisitNumber: dailyVisitNumberFromAttributes(visit.attributes),
    attendedBy: attendingDoctorFromVisitEncounters(visit.encounters),
  };
}

export async function fetchPatientVisits(patientUuid: string): Promise<PatientVisitSummary[]> {
  const query = new URLSearchParams({
    patient: patientUuid,
    v: VISIT_REPRESENTATION,
    limit: "20",
  });
  const data = await openmrsGet<VisitListResponse>(
    `/openmrs/ws/rest/v1/visit?${query.toString()}`,
  );
  return (data.results ?? []).map(mapVisitSummary);
}

export async function fetchVisitByUuid(
  visitUuid: string,
): Promise<{ visit: PatientVisitSummary; patientUuid: string } | null> {
  try {
    const visit = await openmrsGet<VisitRecord>(
      `/openmrs/ws/rest/v1/visit/${encodeURIComponent(visitUuid)}?v=${VISIT_REPRESENTATION}`,
    );
    if (!visit?.uuid) {
      return null;
    }
    return {
      visit: mapVisitSummary(visit),
      patientUuid: visit.patient?.uuid || "",
    };
  } catch {
    return null;
  }
}

interface ObsListResponse {
  results: Array<{
    uuid: string;
    value?: string | number;
    obsDatetime?: string;
    concept?: { display?: string };
    creator?: { display?: string };
  }>;
}

function toReading(
  concept: (typeof VITAL_CONCEPTS)[keyof typeof VITAL_CONCEPTS],
  obs: ObsListResponse["results"][number],
): VitalReading | null {
  if (obs.value === undefined || obs.value === null || obs.value === "") {
    return null;
  }
  return {
    key: concept.key,
    label: concept.label,
    value: String(obs.value),
    unit: concept.unit,
    recordedAt: formatClinicalWhen(obs.obsDatetime),
    recordedBy: obs.creator?.display || "—",
    recordedAtIso: obs.obsDatetime || "",
  };
}

export async function fetchVitalHistory(
  patientUuid: string,
): Promise<Record<string, VitalReading[]>> {
  const entries = await Promise.all(
    Object.values(VITAL_CONCEPTS).map(async (concept) => {
      const query = new URLSearchParams({
        patient: patientUuid,
        concept: concept.uuid,
        v: "custom:(uuid,value,obsDatetime,concept:(display),creator:(display))",
        limit: "8",
      });
      try {
        const data = await openmrsGet<ObsListResponse>(
          `/openmrs/ws/rest/v1/obs?${query.toString()}`,
        );
        const rows = (data.results ?? [])
          .map((obs) => toReading(concept, obs))
          .filter((row): row is VitalReading => row !== null)
          .sort((left, right) => right.recordedAtIso.localeCompare(left.recordedAtIso));
        return [concept.key, rows] as const;
      } catch (error) {
        console.error(`Unable to load ${concept.label}`, error);
        return [concept.key, []] as const;
      }
    }),
  );
  return Object.fromEntries(entries);
}

export function latestVitalsFromHistory(
  history: Record<string, VitalReading[]>,
): VitalReading[] {
  return Object.values(history)
    .map((rows) => rows[0])
    .filter((row): row is VitalReading => Boolean(row));
}

export function calculateBmi(history: Record<string, VitalReading[]>): VitalReading | null {
  const weight = Number(history.weight?.[0]?.value);
  const heightCm = Number(history.height?.[0]?.value);
  if (!Number.isFinite(weight) || !Number.isFinite(heightCm) || heightCm <= 0) {
    return null;
  }
  const metres = heightCm / 100;
  const bmi = weight / (metres * metres);
  return {
    key: "bmi",
    label: "BMI",
    value: bmi.toFixed(1),
    unit: "",
    recordedAt: history.weight[0].recordedAt,
    recordedBy: "Calculated from recorded weight and height",
    recordedAtIso: history.weight[0].recordedAtIso,
  };
}

export async function fetchLatestVitals(patientUuid: string): Promise<VitalReading[]> {
  const history = await fetchVitalHistory(patientUuid);
  return latestVitalsFromHistory(history);
}

export async function fetchConditions(patientUuid: string): Promise<ConditionSummary[]> {
  const data = await openmrsGet<
    | Array<{ uuid?: string; display?: string; conditionNonCoded?: string }>
    | { results?: Array<{ uuid?: string; display?: string; conditionNonCoded?: string }> }
  >(`/openmrs/ws/rest/v1/condition?patientUuid=${encodeURIComponent(patientUuid)}`);
  const rows = Array.isArray(data) ? data : data.results ?? [];
  return rows.map((row) => ({
    uuid: row.uuid || row.display || "condition",
    display: row.display || row.conditionNonCoded || "Condition",
  }));
}

export async function fetchPatientEncounters(
  patientUuid: string,
): Promise<EncounterSummary[]> {
  const query = new URLSearchParams({
    patient: patientUuid,
    v: "custom:(uuid,encounterDatetime,encounterType:(name))",
    limit: "40",
  });
  const data = await openmrsGet<{
    results: Array<{
      uuid: string;
      encounterDatetime?: string;
      encounterType?: { name?: string };
    }>;
  }>(`/openmrs/ws/rest/v1/encounter?${query.toString()}`);
  return (data.results ?? []).map((row) => ({
    uuid: row.uuid,
    date: formatDate(row.encounterDatetime),
    time: formatClock(row.encounterDatetime),
    type: row.encounterType?.name || "Encounter",
  }));
}

export async function fetchAllergyState(patientUuid: string): Promise<AllergyState> {
  try {
    return await fetchAllergyRecord(patientUuid);
  } catch {
    return fetchOpenmrsAllergyFallback(patientUuid);
  }
}

async function fetchOpenmrsAllergyFallback(patientUuid: string): Promise<AllergyState> {
  try {
    const response = await fetch(
      `/openmrs/ws/rest/v1/patient/${patientUuid}/allergy`,
      { credentials: "include", headers: { Accept: "application/json" } },
    );
    if (response.status === 204) {
      return { status: "none-recorded" };
    }
    if (!response.ok) {
      return { status: "unavailable" };
    }
    const data = (await response.json()) as
      | Array<{ display?: string; allergen?: { display?: string } }>
      | { results?: Array<{ display?: string; allergen?: { display?: string } }> };
    const rows = Array.isArray(data) ? data : data.results ?? [];
    const items = rows
      .map((row) => row.display || row.allergen?.display || "")
      .filter(Boolean);
    if (items.length === 0) {
      return { status: "none-recorded" };
    }
    return {
      status: "recorded",
      items,
      records: items.map((item, index) => ({
        uuid: `read-${index}`,
        allergen: item,
        allergenType: "",
        allergenTypeLabel: "",
        severity: "",
        reactions: [],
        comment: "",
        display: item,
      })),
      canWrite: false,
    };
  } catch {
    return { status: "unavailable" };
  }
}
