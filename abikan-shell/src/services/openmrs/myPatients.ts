import type { MyPatientRow } from "../../types";
import { PatientAccountRequestError } from "../patientAccount";
import { mapMyPatientRow, uniqueMyPatients } from "../../workspaces/Doctor/myPatients";

interface MyPatientsResponse {
  patients?: Array<{
    patient?: string;
    mrn?: string;
    ageSex?: string;
    visitType?: string;
    lastAttended?: string;
    dailyVisitNumber?: string;
    attendedBy?: string;
    patientUuid?: string;
  }>;
  message?: string;
  code?: string;
}

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = (await response.json().catch(() => ({}))) as MyPatientsResponse;
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new PatientAccountRequestError(
      body.message || "This action requires the Doctor workspace.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Your patients could not be loaded.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export async function fetchMyPatients(): Promise<MyPatientRow[]> {
  const data = await readJson<MyPatientsResponse>("/openmrs/abikan-api/consultation/my-patients");
  return uniqueMyPatients(
    (data.patients ?? [])
      .map(mapMyPatientRow)
      .filter((row): row is MyPatientRow => row != null),
  );
}
