import type { PatientSearchHit, ReceptionRegistration } from "../../types";
import { formatClock, todayDateString } from "../../utils/datetime";
import { openmrsGet } from "./client";

interface PatientSearchResponse {
  results: Array<{ uuid: string; display?: string }>;
}

export async function searchPatients(query: string): Promise<PatientSearchHit[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    return [];
  }
  const params = new URLSearchParams({
    q: trimmed,
    v: "custom:(uuid,display)",
    limit: "8",
  });
  const data = await openmrsGet<PatientSearchResponse>(
    `/openmrs/ws/rest/v1/patient?${params.toString()}`,
  );
  return (data.results ?? []).map((patient) => ({
    uuid: patient.uuid,
    display: patient.display || patient.uuid,
  }));
}

interface FhirBundle {
  entry?: Array<{
    resource: {
      id: string;
      name?: Array<{ given?: string[]; family?: string }>;
      identifier?: Array<{ value?: string }>;
      meta?: { lastUpdated?: string };
    };
  }>;
}

export async function fetchRecentRegistrations(): Promise<ReceptionRegistration[]> {
  const query = new URLSearchParams({
    _sort: "-_lastUpdated",
    _count: "15",
  });
  const bundle = await openmrsGet<FhirBundle>(
    `/openmrs/ws/fhir2/R4/Patient?${query.toString()}`,
  );
  return (bundle.entry ?? []).map((entry) => {
    const resource = entry.resource;
    const name = resource.name?.[0];
    const given = (name?.given ?? []).join(" ").trim();
    const family = name?.family ?? "";
    const updated = resource.meta?.lastUpdated;
    return {
      uuid: resource.id,
      time: formatClock(updated),
      date: updated ? updated.slice(0, 10) : "",
      patientName: `${given} ${family}`.trim() || "Unknown patient",
      mrn: resource.identifier?.[0]?.value || "—",
    };
  });
}

export async function fetchNewRegistrations(query: string): Promise<{
  items: ReceptionRegistration[];
  total: number;
  singleDay: boolean;
}> {
  const suffix = query ? `?${query}` : "";
  const response = await fetch(`/openmrs/abikan-api/reception/registrations${suffix}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = (await response.json().catch(() => ({}))) as {
    message?: string;
    items?: ReceptionRegistration[];
    total?: number;
    singleDay?: boolean;
  };
  if (!response.ok) {
    throw new Error(body.message || "New patients could not be loaded.");
  }
  const items = body.items ?? [];
  return {
    items,
    total: Number.isFinite(body.total) ? Number(body.total) : items.length,
    singleDay: Boolean(body.singleDay),
  };
}

export function registrationsToday(
  registrations: ReceptionRegistration[],
): ReceptionRegistration[] {
  const today = todayDateString();
  return registrations.filter((row) => row.date === today);
}
