import type { OpenmrsSession, OpenmrsUser } from "../../types";
import { openmrsGet } from "./client";

interface UserSearchResponse {
  results: OpenmrsUser[];
}

const USER_REPRESENTATION =
  "custom:(username,uuid,person:(display),roles:(name),privileges:(name,retired),userProperties)";

export function userFromSession(session: OpenmrsSession): OpenmrsUser | null {
  const sessionUser = session.user;
  if (!sessionUser?.uuid || !sessionUser.username) {
    return null;
  }
  if (!sessionUser.roles?.length && !sessionUser.privileges?.length) {
    return null;
  }
  return {
    uuid: sessionUser.uuid,
    username: sessionUser.username,
    roles: sessionUser.roles ?? [],
    privileges: sessionUser.privileges ?? [],
    userProperties: sessionUser.userProperties,
    person: sessionUser.person,
  };
}

export async function fetchUserByUuid(uuid: string): Promise<OpenmrsUser> {
  return openmrsGet<OpenmrsUser>(
    `/openmrs/ws/rest/v1/user/${encodeURIComponent(uuid)}?v=${encodeURIComponent(USER_REPRESENTATION)}`,
  );
}

export async function fetchUserByUsername(
  username: string,
): Promise<OpenmrsUser> {
  const query = new URLSearchParams({
    username,
    v: USER_REPRESENTATION,
  });
  const data = await openmrsGet<UserSearchResponse>(
    `/openmrs/ws/rest/v1/user?${query.toString()}`,
  );
  const user = data.results?.[0];
  if (!user?.uuid || !user.username) {
    throw new Error("User record was not found");
  }
  return user;
}
