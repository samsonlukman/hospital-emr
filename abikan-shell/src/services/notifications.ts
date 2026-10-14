/** Staff notification API — hospital-wide foundation (patient_called, visit_started, admit_requested). */

export type NotificationPriority = "low" | "normal" | "high" | "urgent";
export type NotificationStatus = "pending" | "read" | "acked" | "expired";

export interface StaffNotification {
  id: string;
  eventType: string;
  idempotencyKey: string;
  priority: NotificationPriority;
  title: string;
  message: string;
  senderUsername: string;
  senderDisplay: string;
  recipientScope: string;
  recipientRole: string;
  recipientWorkplace: string;
  recipientUser: string;
  patientUuid: string;
  visitUuid: string;
  mrn: string;
  patientName: string;
  actionHref: string;
  status: NotificationStatus;
  createdAt: string;
  createdAtEpoch: number;
  readAt: string;
  ackedAt: string;
  ackedBy: string;
  expiresAt: string;
  expiresAtEpoch: number;
  speak: boolean;
  payload: Record<string, unknown>;
}

export interface NotificationListResult {
  status: "ok";
  serverTime: string;
  notifications: StaffNotification[];
  pendingCount: number;
  activeCount: number;
}

export interface NotificationMutationResult {
  status: "ok";
  notification: StaffNotification;
  duplicate: boolean;
}

export class NotificationRequestError extends Error {
  status?: number;
  code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "NotificationRequestError";
    this.status = status;
    this.code = code;
  }
}

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
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
    throw new NotificationRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (!response.ok) {
    throw new NotificationRequestError(
      body.message || "The notification could not be completed.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchStaffNotifications(since?: string): Promise<NotificationListResult> {
  const params = new URLSearchParams();
  if (since) {
    params.set("since", since);
  }
  const query = params.toString();
  return readJson<NotificationListResult>(
    `/openmrs/abikan-api/notifications${query ? `?${query}` : ""}`,
  );
}

export function acknowledgeNotification(id: string): Promise<NotificationMutationResult> {
  return readJson<NotificationMutationResult>(
    `/openmrs/abikan-api/notifications/${encodeURIComponent(id)}/ack`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
}

export function markNotificationRead(id: string): Promise<NotificationMutationResult> {
  return readJson<NotificationMutationResult>(
    `/openmrs/abikan-api/notifications/${encodeURIComponent(id)}/read`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
}

/** Compat: doctor still creates calls via the patient-call endpoint. */
export function createPatientCall(input: {
  patientUuid: string;
  visitUuid: string;
  patientName: string;
  mrn: string;
  dailyVisitNumber?: string;
  requestId: string;
}): Promise<{ status: "ok"; call: Record<string, unknown>; duplicate: boolean }> {
  return readJson("/openmrs/abikan-api/consultation/call-patient", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function newNotificationRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `note-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function dailyVisitNumberFromNotification(note: StaffNotification): string {
  const raw = note.payload?.dailyVisitNumber;
  return typeof raw === "string" ? raw : "";
}
