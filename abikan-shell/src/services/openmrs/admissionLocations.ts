import type { PatientBedAssignment, WardBed, WardPatient, WardSummary } from "../../types";
import { formatClinicalWhen } from "../../utils/datetime";
import { openmrsGet } from "./client";
import { parsePatientDisplay } from "./clinicalPatient";

interface AdmissionLocationListResponse {
  results?: Array<{
    ward?: { uuid?: string; name?: string; display?: string };
    wardName?: string;
    totalBeds?: number;
    occupiedBeds?: number;
  }>;
}

interface AdmissionLocationDetail {
  ward?: { uuid?: string; name?: string; display?: string };
  wardName?: string;
  totalBeds?: number;
  occupiedBeds?: number;
  bedLayouts?: Array<{
    bedUuid?: string;
    uuid?: string;
    bedNumber?: string;
    bedId?: number | string;
    status?: string;
    patient?: {
      uuid?: string;
      givenName?: string;
      familyName?: string;
      identifier?: string;
      display?: string;
    } | null;
  }>;
}

interface VisitSearchResponse {
  results?: Array<{
    uuid: string;
    startDatetime?: string;
    visitType?: { name?: string };
    patient?: { uuid?: string; display?: string };
  }>;
}

function wardName(row: { ward?: { name?: string; display?: string }; wardName?: string }): string {
  return row.ward?.name || row.ward?.display || row.wardName || "Ward";
}

function mapBeds(detail: AdmissionLocationDetail): WardBed[] {
  return (detail.bedLayouts ?? []).map((layout) => {
    const given = layout.patient?.givenName ?? "";
    const family = layout.patient?.familyName ?? "";
    const parsed = parsePatientDisplay(layout.patient?.display);
    const patientName =
      `${given} ${family}`.trim() || parsed.name || layout.patient?.display || undefined;
    return {
      uuid: String(layout.bedUuid || layout.uuid || layout.bedId || layout.bedNumber || ""),
      bedNumber: String(layout.bedNumber || layout.bedId || "Bed"),
      status: layout.status || "UNKNOWN",
      patientUuid: layout.patient?.uuid || undefined,
      patientName: layout.patient?.uuid ? patientName : undefined,
      mrn: layout.patient?.identifier || (layout.patient?.uuid ? parsed.mrn : undefined),
    };
  });
}

function toSummary(uuid: string, detail: AdmissionLocationDetail): WardSummary {
  const totalBeds = Number(detail.totalBeds ?? 0);
  const occupiedBeds = Number(detail.occupiedBeds ?? 0);
  return {
    uuid,
    name: wardName(detail),
    totalBeds,
    occupiedBeds,
    availableBeds: Math.max(0, totalBeds - occupiedBeds),
    beds: mapBeds(detail),
  };
}

export async function fetchAdmissionWards(): Promise<WardSummary[]> {
  const list = await openmrsGet<AdmissionLocationListResponse>(
    "/openmrs/ws/rest/v1/admissionLocation",
  );
  const rows = list.results ?? [];
  const details = await Promise.all(
    rows.map(async (row) => {
      const uuid = row.ward?.uuid;
      if (!uuid) {
        return null;
      }
      try {
        const detail = await openmrsGet<AdmissionLocationDetail>(
          `/openmrs/ws/rest/v1/admissionLocation/${uuid}?v=full`,
        );
        return toSummary(uuid, detail);
      } catch (error) {
        console.error(`Unable to load ward ${uuid}`, error);
        const totalBeds = Number(row.totalBeds ?? 0);
        const occupiedBeds = Number(row.occupiedBeds ?? 0);
        return {
          uuid,
          name: wardName(row),
          totalBeds,
          occupiedBeds,
          availableBeds: Math.max(0, totalBeds - occupiedBeds),
          beds: [],
        } satisfies WardSummary;
      }
    }),
  );
  return details.filter((ward): ward is WardSummary => Boolean(ward));
}

export async function fetchOpenVisitsAtLocation(locationUuid: string): Promise<WardPatient[]> {
  const query = new URLSearchParams({
    location: locationUuid,
    includeInactive: "false",
    v: "custom:(uuid,startDatetime,visitType:(name),patient:(uuid,display))",
    limit: "50",
  });
  const data = await openmrsGet<VisitSearchResponse>(
    `/openmrs/ws/rest/v1/visit?${query.toString()}`,
  );
  return (data.results ?? [])
    .filter((visit) => visit.patient?.uuid)
    .map((visit) => {
      const parsed = parsePatientDisplay(visit.patient?.display);
      return {
        visitUuid: visit.uuid,
        patientUuid: visit.patient?.uuid || "",
        patientName: parsed.name,
        mrn: parsed.mrn,
        visitType: visit.visitType?.name || "Visit",
        started: formatClinicalWhen(visit.startDatetime),
      };
    });
}

export function findPatientBed(
  wards: WardSummary[],
  patientUuid: string,
): PatientBedAssignment | null {
  for (const ward of wards) {
    const bed = ward.beds.find((item) => item.patientUuid === patientUuid);
    if (bed) {
      return {
        wardUuid: ward.uuid,
        wardName: ward.name,
        bedUuid: bed.uuid,
        bedNumber: bed.bedNumber,
      };
    }
  }
  return null;
}

export function matchWardToLocation(
  wards: WardSummary[],
  locationName: string,
  locationUuid: string,
): WardSummary | undefined {
  const byUuid = wards.find((ward) => ward.uuid === locationUuid);
  if (byUuid) {
    return byUuid;
  }
  const expected = locationName.trim().toLowerCase();
  return wards.find((ward) => ward.name.trim().toLowerCase() === expected);
}
