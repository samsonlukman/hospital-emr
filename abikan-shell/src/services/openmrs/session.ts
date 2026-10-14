import type { OpenmrsSession } from "../../types";
import { LOCATION_COOKIE, USER_COOKIE } from "../../config/appConfig";
import { encodeBahmniUserCookie } from "./bahmniUserCookie";
import { clearCookie, openmrsDelete, openmrsGet, openmrsPost, setCookie } from "./client";

export function fetchSession(): Promise<OpenmrsSession> {
  return openmrsGet<OpenmrsSession>("/openmrs/ws/rest/v1/session");
}

async function readSessionResponse(response: Response): Promise<OpenmrsSession | null> {
  try {
    return (await response.json()) as OpenmrsSession;
  } catch {
    return null;
  }
}

/**
 * OpenMRS Basic auth only attaches to an existing servlet session.
 * A GET without Authorization plants JSESSIONID. Authenticating before that
 * cookie exists returns { authenticated: false } even with a valid password.
 */
export async function ensureAnonymousSession(): Promise<void> {
  const probe = await fetch("/openmrs/ws/rest/v1/session", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!probe.ok && probe.status !== 401) {
    throw new Error("signin-failed");
  }
  const current = await readSessionResponse(probe);
  if (!current?.authenticated) {
    return;
  }
  await destroySession();
  const anonymous = await fetch("/openmrs/ws/rest/v1/session", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!anonymous.ok && anonymous.status !== 401) {
    throw new Error("signin-failed");
  }
}

export async function createSession(
  username: string,
  password: string,
): Promise<OpenmrsSession> {
  await ensureAnonymousSession();
  const token = btoa(`${username}:${password}`);
  const response = await fetch("/openmrs/ws/rest/v1/session", {
    credentials: "include",
    headers: {
      Accept: "application/json",
      Authorization: `Basic ${token}`,
    },
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("invalid-credentials");
    }
    throw new Error("signin-failed");
  }
  const session = (await response.json()) as OpenmrsSession;
  if (!session.authenticated) {
    throw new Error("invalid-credentials");
  }
  setCookie(USER_COOKIE, encodeBahmniUserCookie(username));
  return session;
}

export function updateSessionLocation(locationUuid: string): Promise<OpenmrsSession> {
  return openmrsPost<OpenmrsSession>("/openmrs/ws/rest/v1/session", {
    sessionLocation: locationUuid,
  });
}

export async function destroySession(): Promise<void> {
  try {
    await openmrsDelete("/openmrs/ws/rest/v1/session");
  } finally {
    clearCookie(USER_COOKIE);
    clearCookie(LOCATION_COOKIE);
  }
}
