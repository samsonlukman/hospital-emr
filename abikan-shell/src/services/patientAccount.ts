import type {
  PatientAccountInvoicePayload,
  PatientAccountPayload,
} from "../types/patientAccount";

export class PatientAccountRequestError extends Error {
  status?: number;
  code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "PatientAccountRequestError";
    this.status = status;
    this.code = code;
  }
}

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = (await response.json().catch(() => ({}))) as PatientAccountPayload & {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to load the patient account.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchPatientAccount(patientUuid: string): Promise<PatientAccountPayload> {
  return readJson<PatientAccountPayload>(
    `/openmrs/abikan-api/patient-account/${encodeURIComponent(patientUuid)}`,
  );
}

export function fetchPatientAccountInvoice(
  patientUuid: string,
  invoiceId: string,
): Promise<PatientAccountInvoicePayload> {
  return readJson<PatientAccountInvoicePayload>(
    `/openmrs/abikan-api/patient-account/${encodeURIComponent(patientUuid)}/invoice/${encodeURIComponent(invoiceId)}`,
  );
}
