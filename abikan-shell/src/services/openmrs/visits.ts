import type { ReceptionVisit } from "../../types";
import { compareDailyVisitNumber, dailyVisitNumberFromAttributes } from "../../utils/dailyVisitNumber";
import { formatClock, todayDateString } from "../../utils/datetime";
import { outpatientVisitStatus } from "../../workspaces/RegistrationDesk/receptionVisit";
import { attendingDoctorFromVisitEncounters } from "./visitAttendingProvider";
import { openmrsGet } from "./client";

interface VisitSearchResponse {
  results: Array<{
    uuid: string;
    startDatetime?: string;
    stopDatetime?: string;
    visitType?: { display?: string; name?: string };
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
    patient?: {
      uuid?: string;
      display?: string;
      identifiers?: Array<{ identifier?: string; preferred?: boolean }>;
    };
  }>;
}

function preferredMrn(identifiers?: Array<{ identifier?: string; preferred?: boolean }>): string {
  const preferred = identifiers?.find((item) => item.preferred && item.identifier);
  const any = identifiers?.find((item) => item.identifier);
  return preferred?.identifier || any?.identifier || "";
}

function nameAndMrn(
  display: string | undefined,
  identifiers?: Array<{ identifier?: string; preferred?: boolean }>,
): { name: string; mrn: string } {
  const mrn = preferredMrn(identifiers);
  const raw = (display || "Unknown patient").trim();
  if (mrn && raw.endsWith(mrn)) {
    return {
      name: raw.slice(0, -mrn.length).replace(/[\s\-–—()]+$/g, "").trim() || raw,
      mrn,
    };
  }
  const paren = raw.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
  if (paren) {
    return { name: paren[1].trim(), mrn: mrn || paren[2].trim() };
  }
  return { name: raw, mrn: mrn || "" };
}

async function loadVisits(includeInactive: boolean): Promise<ReceptionVisit[]> {
  const query = new URLSearchParams({
    fromStartDate: todayDateString(),
    includeInactive: includeInactive ? "true" : "false",
    v: "custom:(uuid,startDatetime,stopDatetime,visitType:(display,name),patient:(uuid,display,identifiers:(identifier,preferred)),attributes:(value,display,attributeType:(name)),encounters:(uuid,encounterDatetime,encounterType:(uuid,name),encounterProviders:(provider:(display,person:(display)))))",
    limit: "100",
  });
  const data = await openmrsGet<VisitSearchResponse>(
    `/openmrs/ws/rest/v1/visit?${query.toString()}`,
  );
  return (data.results ?? []).map((visit) => {
    const identity = nameAndMrn(visit.patient?.display, visit.patient?.identifiers);
    const attendedBy = attendingDoctorFromVisitEncounters(visit.encounters);
    const status = outpatientVisitStatus({
      open: !visit.stopDatetime,
      stop: visit.stopDatetime || null,
      attendedBy,
    });
    return {
      uuid: visit.uuid,
      time: formatClock(visit.startDatetime),
      startDatetime: visit.startDatetime || "",
      patientName: identity.name,
      patientUuid: visit.patient?.uuid || "",
      mrn: identity.mrn,
      visitType: visit.visitType?.display || visit.visitType?.name || "Visit",
      status: status.badge,
      attendedBy,
      dailyVisitNumber: dailyVisitNumberFromAttributes(visit.attributes),
    };
  });
}

export async function fetchTodaysVisits(): Promise<ReceptionVisit[]> {
  try {
    return sortTodaysVisits(await loadVisits(true));
  } catch {
    return sortTodaysVisits(await loadVisits(false));
  }
}

function sortTodaysVisits(rows: ReceptionVisit[]): ReceptionVisit[] {
  return [...rows].sort((left, right) =>
    compareDailyVisitNumber(left.dailyVisitNumber, right.dailyVisitNumber),
  );
}
