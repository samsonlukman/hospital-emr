import type { DoctorQueueRow } from "../../types";
import { PatientAccountRequestError } from "../patientAccount";
import { mapTodaysPatientRow } from "../../workspaces/Doctor/todaysPatients";

interface TodaysPatientsResponse {
  patients?: Array<{
    patient?: string;
    mrn?: string;
    visitType?: string;
    visitStart?: string;
    time?: string;
    status?: string;
    dailyVisitNumber?: string;
    patientUuid?: string;
    visitUuid?: string;
  }>;
  message?: string;
  code?: string;
}

async function readJson<T>(path: string, forbiddenMessage: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = (await response.json().catch(() => ({}))) as TodaysPatientsResponse;
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new PatientAccountRequestError(
      body.message || forbiddenMessage,
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Today's patients could not be loaded. You can still search for a patient.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

function mapRows(data: TodaysPatientsResponse): DoctorQueueRow[] {
  return (data.patients ?? [])
    .map(mapTodaysPatientRow)
    .filter((row): row is DoctorQueueRow => row != null);
}

export async function fetchDoctorQueue(): Promise<DoctorQueueRow[]> {
  const data = await readJson<TodaysPatientsResponse>(
    "/openmrs/abikan-api/consultation/todays-patients",
    "This action requires the Doctor workspace.",
  );
  return mapRows(data);
}

export async function fetchNursingTodaysPatients(): Promise<DoctorQueueRow[]> {
  const data = await readJson<TodaysPatientsResponse>(
    "/openmrs/abikan-api/nursing/todays-patients",
    "This action requires the ward workspace.",
  );
  return mapRows(data);
}
