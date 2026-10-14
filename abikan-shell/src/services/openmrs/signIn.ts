import { resolveDefaultWorkplace } from "../../config/workplaces";
import { setShellRoute } from "../../app/hashRoute";
import { OpenmrsRequestError } from "./client";
import { changeLoginLocation, fetchLocationByName } from "./location";
import { createSession } from "./session";
import { fetchUserByUuid, userFromSession } from "./user";
import type { OpenmrsSession, OpenmrsUser, WorkspaceContext } from "../../types";

export class InvalidCredentialsError extends Error {
  constructor() {
    super("invalid-credentials");
    this.name = "InvalidCredentialsError";
  }
}

export class NetworkError extends Error {
  constructor() {
    super("network");
    this.name = "NetworkError";
  }
}

export class SessionInitError extends Error {
  constructor() {
    super("session-init");
    this.name = "SessionInitError";
  }
}

function privilegesOf(user: {
  privileges?: { name?: string; retired?: boolean }[];
}): string[] {
  return (user.privileges ?? [])
    .filter((privilege) => !privilege.retired && privilege.name)
    .map((privilege) => privilege.name as string);
}

function rolesOf(user: { roles?: { name?: string }[] }): string[] {
  return (user.roles ?? [])
    .map((role) => role.name)
    .filter((name): name is string => Boolean(name));
}

async function loadUserRecord(session: OpenmrsSession): Promise<OpenmrsUser> {
  const fromSession = userFromSession(session);
  if (fromSession) {
    return fromSession;
  }
  const uuid = session.user?.uuid;
  if (!uuid) {
    throw new SessionInitError();
  }
  try {
    return await fetchUserByUuid(uuid);
  } catch (error) {
    if (error instanceof OpenmrsRequestError && error.status === 401) {
      throw new SessionInitError();
    }
    throw error instanceof SessionInitError ? error : new SessionInitError();
  }
}

/**
 * Authenticate, load the current user, assign the hidden session location,
 * then point the hash at the department home. Does not report init failures
 * as a bad password.
 */
export async function signInToHospital EMR(username: string, password: string): Promise<void> {
  let session: OpenmrsSession;
  try {
    session = await createSession(username, password);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new NetworkError();
    }
    if (error instanceof Error && error.message === "invalid-credentials") {
      throw new InvalidCredentialsError();
    }
    if (error instanceof OpenmrsRequestError && error.status === 401) {
      throw new InvalidCredentialsError();
    }
    throw new NetworkError();
  }

  if (!session.authenticated) {
    throw new InvalidCredentialsError();
  }

  let user: OpenmrsUser;
  try {
    user = await loadUserRecord(session);
  } catch (error) {
    if (error instanceof InvalidCredentialsError || error instanceof NetworkError) {
      throw error;
    }
    throw new SessionInitError();
  }

  const context: WorkspaceContext = {
    username: user.username,
    displayName: (user.person?.display || user.username).trim(),
    userUuid: user.uuid,
    roles: rolesOf(user),
    privileges: privilegesOf(user),
    userProperties: user.userProperties,
    location: { uuid: "", name: "", tags: [] },
  };
  const workplace = resolveDefaultWorkplace(context);

  try {
    const location = await fetchLocationByName(workplace.sessionLocationName);
    if (location) {
      await changeLoginLocation(location);
    }
  } catch (error) {
    if (error instanceof TypeError) {
      throw new NetworkError();
    }
    throw new SessionInitError();
  }

  setShellRoute(workplace.route);
}
