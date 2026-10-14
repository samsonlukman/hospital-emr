import {
  LOCATION_COOKIE,
  USER_COOKIE,
} from "../../config/appConfig";
import { resolveDefaultWorkplace } from "../../config/workplaces";
import { locationTagNames } from "../../config/workspaceMap";
import type { WorkspaceContext } from "../../types";
import {
  bahmniUserCookieNeedsRewrite,
  encodeBahmniUserCookie,
  usernameFromBahmniCookie,
} from "./bahmniUserCookie";
import { getCookie, OpenmrsRequestError, setCookie } from "./client";
import { changeLoginLocation, fetchLocation, fetchLocationByName } from "./location";
import { fetchSession } from "./session";
import { fetchUserByUsername, fetchUserByUuid, userFromSession } from "./user";

export class UnauthenticatedError extends Error {
  constructor() {
    super("unauthenticated");
    this.name = "UnauthenticatedError";
  }
}

export class MissingLocationError extends Error {
  constructor() {
    super("location");
    this.name = "MissingLocationError";
  }
}

function readCookieUsername(): string | null {
  return usernameFromBahmniCookie(getCookie(USER_COOKIE));
}

function syncBahmniUserCookie(username: string): void {
  const raw = getCookie(USER_COOKIE);
  if (bahmniUserCookieNeedsRewrite(raw, username)) {
    setCookie(USER_COOKIE, encodeBahmniUserCookie(username));
  }
}

function readCookieLocationUuid(): string | null {
  const raw = getCookie(LOCATION_COOKIE);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as { uuid?: string };
    return parsed.uuid ?? null;
  } catch {
    return null;
  }
}

function privilegesOf(user: { privileges?: { name?: string; retired?: boolean }[] }): string[] {
  return (user.privileges ?? [])
    .filter((privilege) => !privilege.retired && privilege.name)
    .map((privilege) => privilege.name as string);
}

function rolesOf(user: { roles?: { name?: string }[] }): string[] {
  return (user.roles ?? [])
    .map((role) => role.name)
    .filter((name): name is string => Boolean(name));
}

export async function loadWorkspaceContext(): Promise<WorkspaceContext> {
  let session;
  try {
    session = await fetchSession();
  } catch (error) {
    if (error instanceof OpenmrsRequestError && error.status === 401) {
      throw new UnauthenticatedError();
    }
    throw new Error("session");
  }

  if (!session.authenticated) {
    throw new UnauthenticatedError();
  }

  const username = session.user?.username || readCookieUsername();
  if (!username) {
    throw new Error("user");
  }

  let user = userFromSession(session);
  if (!user) {
    try {
      user = session.user?.uuid
        ? await fetchUserByUuid(session.user.uuid)
        : await fetchUserByUsername(username);
    } catch (error) {
      if (error instanceof OpenmrsRequestError && error.status === 401) {
        throw new UnauthenticatedError();
      }
      console.error("Unable to load OpenMRS user", error);
      throw new Error("user");
    }
  }

  syncBahmniUserCookie(user.username || username);

  const privileges = privilegesOf(user);
  const roles = rolesOf(user);
  const partialContext: WorkspaceContext = {
    username: user.username,
    displayName: (user.person?.display || user.username).trim(),
    userUuid: user.uuid,
    roles,
    privileges,
    userProperties: user.userProperties,
    location: { uuid: "", name: "", tags: [] },
  };

  let locationUuid = session.sessionLocation?.uuid || readCookieLocationUuid();
  if (!locationUuid) {
    const workplace = resolveDefaultWorkplace(partialContext);
    const fallback = await fetchLocationByName(workplace.sessionLocationName);
    if (!fallback) {
      throw new MissingLocationError();
    }
    await changeLoginLocation(fallback);
    locationUuid = fallback.uuid;
  }

  let location;
  try {
    location = await fetchLocation(locationUuid);
  } catch (error) {
    if (error instanceof OpenmrsRequestError && error.status === 401) {
      throw new UnauthenticatedError();
    }
    console.error("Unable to load OpenMRS location", error);
    throw new Error("location");
  }

  return {
    ...partialContext,
    location: {
      uuid: location.uuid,
      name: location.name || location.display || "Unknown location",
      tags: locationTagNames(location.tags ?? []),
    },
  };
}
