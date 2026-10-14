import type {
  AdminDepartmentId,
  AdminMutationPayload,
  CreateStaffRequest,
  DepartmentAccessPayload,
  StaffAccount,
  StaffDirectoryPayload,
} from "../types/administration";
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
      body.message || "The staff account could not be saved.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

function jsonPost<T>(path: string, body: object): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchStaffDirectory(): Promise<StaffDirectoryPayload> {
  return requestJson<StaffDirectoryPayload>("/openmrs/abikan-api/admin/staff");
}

export function fetchDepartmentAccess(): Promise<DepartmentAccessPayload> {
  return requestJson<DepartmentAccessPayload>("/openmrs/abikan-api/admin/access");
}

export function fetchAdminAnalyticsOverview(
  query: string,
): Promise<import("../types/administration").AdminAnalyticsOverview> {
  const suffix = query ? `?${query}` : "";
  return requestJson(`/openmrs/abikan-api/admin/analytics/overview${suffix}`);
}

export function fetchAdminStaffAudit(
  offset = 0,
): Promise<import("../types/administration").AdminStaffAuditPayload> {
  return requestJson(
    `/openmrs/abikan-api/admin/audit?limit=100&offset=${encodeURIComponent(String(offset))}`,
  );
}

export function createStaffAccount(request: CreateStaffRequest): Promise<AdminMutationPayload> {
  return jsonPost<AdminMutationPayload>("/openmrs/abikan-api/admin/staff", request);
}

export function saveStaffAccess(
  userUuid: string,
  departments: AdminDepartmentId[],
  preferredDepartment: AdminDepartmentId,
): Promise<AdminMutationPayload> {
  return jsonPost<AdminMutationPayload>(
    `/openmrs/abikan-api/admin/staff/${encodeURIComponent(userUuid)}/access`,
    { departments, preferredDepartment, requestId: newAdminRequestId() },
  );
}

export function setStaffEnabled(
  userUuid: string,
  enabled: boolean,
): Promise<AdminMutationPayload> {
  return jsonPost<AdminMutationPayload>(
    `/openmrs/abikan-api/admin/staff/${encodeURIComponent(userUuid)}/status`,
    { enabled, requestId: newAdminRequestId() },
  );
}

export function setStaffPassword(
  userUuid: string,
  password: string,
): Promise<AdminMutationPayload> {
  return jsonPost<AdminMutationPayload>(
    `/openmrs/abikan-api/admin/staff/${encodeURIComponent(userUuid)}/password`,
    { password, requestId: newAdminRequestId() },
  );
}

export function updateStaffProfile(
  staffId: string,
  body: Record<string, unknown>,
): Promise<AdminMutationPayload> {
  return jsonPost<AdminMutationPayload>(
    `/openmrs/abikan-api/admin/staff/${encodeURIComponent(staffId)}/profile`,
    { ...body, requestId: newAdminRequestId() },
  );
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("That file could not be read."));
    reader.readAsDataURL(file);
  });
}

export async function uploadStaffPhoto(staffId: string, file: File): Promise<AdminMutationPayload> {
  const content = await fileToDataUrl(file);
  return jsonPost<AdminMutationPayload>(
    `/openmrs/abikan-api/admin/staff/${encodeURIComponent(staffId)}/photo`,
    { content, requestId: newAdminRequestId() },
  );
}

export async function uploadAppointmentLetter(
  staffId: string,
  file: File,
): Promise<AdminMutationPayload> {
  const content = await fileToDataUrl(file);
  return jsonPost<AdminMutationPayload>(
    `/openmrs/abikan-api/admin/staff/${encodeURIComponent(staffId)}/appointment-letter`,
    { content, requestId: newAdminRequestId() },
  );
}

export function staffPhotoHref(staff: Pick<StaffAccount, "personUuid" | "staffId" | "userUuid" | "profilePictureHref">): string {
  if (staff.profilePictureHref) {
    return staff.profilePictureHref;
  }
  const id = staff.personUuid || staff.staffId || staff.userUuid;
  return `/openmrs/abikan-api/admin/staff/${encodeURIComponent(id)}/photo`;
}

export function appointmentLetterHref(staffId: string): string {
  return `/openmrs/abikan-api/admin/staff/${encodeURIComponent(staffId)}/appointment-letter`;
}

export function newAdminRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `admin-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
