import type { CertificatesPayload } from "../types/certificates";
import { PatientAccountRequestError } from "./patientAccount";

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const payload = (await response.json().catch(() => ({}))) as T & { message?: string; code?: string };
  if (!response.ok) {
    throw new PatientAccountRequestError(
      payload.message || "The certificate could not be saved.",
      response.status,
      payload.code || "certificate_error",
    );
  }
  return payload;
}

export function fetchCertificates(patientUuid: string): Promise<CertificatesPayload> {
  return readJson(`/openmrs/abikan-api/certificates/patient/${encodeURIComponent(patientUuid)}`);
}

export function saveCertificate(body: Record<string, string>): Promise<CertificatesPayload> {
  return readJson("/openmrs/abikan-api/certificates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function downloadCertificate(patientUuid: string, kind: "birth" | "death", filename: string): Promise<void> {
  const response = await fetch(
    `/openmrs/abikan-api/certificates/patient/${encodeURIComponent(patientUuid)}/${kind}/pdf`,
    { credentials: "include" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { message?: string; code?: string };
    throw new PatientAccountRequestError(
      body.message || "The certificate could not be downloaded.",
      response.status,
      body.code,
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
