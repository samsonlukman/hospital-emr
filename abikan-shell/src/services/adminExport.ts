import type {
  AdminExportCatalog,
  AdminExportHistoryPayload,
  AdminExportMutationPayload,
  AdminExportRequest,
} from "../types/adminExport";
import { PatientAccountRequestError } from "./patientAccount";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = (await response.json().catch(() => ({}))) as {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new PatientAccountRequestError(
      body.message || "This action requires Hospital Administration.",
      403,
      body.code || "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "The export could not be completed.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchAdminExportCatalog(): Promise<AdminExportCatalog> {
  return requestJson("/openmrs/abikan-api/admin/export");
}

export function fetchAdminExportHistory(query = ""): Promise<AdminExportHistoryPayload> {
  const suffix = query ? `?${query}` : "";
  return requestJson(`/openmrs/abikan-api/admin/export/history${suffix}`);
}

export function generateAdminExport(request: AdminExportRequest): Promise<AdminExportMutationPayload> {
  return requestJson("/openmrs/abikan-api/admin/export", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(request),
  });
}

export function deleteAdminExport(exportId: string): Promise<AdminExportMutationPayload> {
  return requestJson(`/openmrs/abikan-api/admin/export/${encodeURIComponent(exportId)}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({}),
  });
}

export async function downloadAdminExport(exportId: string, filename: string): Promise<void> {
  const response = await fetch(
    `/openmrs/abikan-api/admin/export/${encodeURIComponent(exportId)}/file`,
    { credentials: "include" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { message?: string; code?: string };
    throw new PatientAccountRequestError(
      body.message || "This export file is no longer available.",
      response.status,
      body.code,
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "abikan-export";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
