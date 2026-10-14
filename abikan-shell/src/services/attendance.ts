import type {
  AttendanceActionPayload,
  AttendanceLogPayload,
  AttendanceLookupPayload,
  AttendanceTerminalConfig,
  StaffAttendanceCodePayload,
} from "../types/attendance";
import { PatientAccountRequestError } from "./patientAccount";
import { newAdminRequestId } from "./administration";

const API = "/openmrs/abikan-api";

let developmentTerminalKey = "";

function terminalHeaders(): HeadersInit {
  const key =
    developmentTerminalKey ||
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_ATTENDANCE_TERMINAL_KEY) ||
    "";
  return key ? { "X-Hospital EMR-Terminal-Key": String(key) } : {};
}

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
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Staff log could not be completed.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export async function fetchAttendanceTerminalConfig(): Promise<AttendanceTerminalConfig> {
  const payload = await requestJson<AttendanceTerminalConfig>(`${API}/attendance/terminal`);
  if (payload.developmentTerminalKey) {
    developmentTerminalKey = payload.developmentTerminalKey;
  }
  return payload;
}

export function lookupStaffAttendance(code: string): Promise<AttendanceLookupPayload> {
  return requestJson<AttendanceLookupPayload>(`${API}/attendance/status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...terminalHeaders(),
    },
    body: JSON.stringify({ code }),
  });
}

export function signInWithStaffCode(code: string, photo: string): Promise<AttendanceActionPayload> {
  return requestJson<AttendanceActionPayload>(`${API}/attendance/sign-in`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...terminalHeaders(),
    },
    body: JSON.stringify({ code, photo }),
  });
}

export function signOutWithStaffCode(code: string): Promise<AttendanceActionPayload> {
  return requestJson<AttendanceActionPayload>(`${API}/attendance/sign-out`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...terminalHeaders(),
    },
    body: JSON.stringify({ code }),
  });
}

export function fetchAttendanceLog(query: string): Promise<AttendanceLogPayload> {
  const suffix = query ? `?${query}` : "";
  return requestJson<AttendanceLogPayload>(`${API}/admin/log${suffix}`);
}

export function fetchStaffAttendanceCode(staffId: string): Promise<StaffAttendanceCodePayload> {
  return requestJson<StaffAttendanceCodePayload>(
    `${API}/admin/staff/${encodeURIComponent(staffId)}/attendance-code`,
  );
}

export function setStaffAttendanceCode(
  staffId: string,
  body: { code?: string; replace?: boolean } = {},
): Promise<StaffAttendanceCodePayload> {
  return requestJson<StaffAttendanceCodePayload>(
    `${API}/admin/staff/${encodeURIComponent(staffId)}/attendance-code`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        ...body,
        requestId: newAdminRequestId(),
      }),
    },
  );
}
