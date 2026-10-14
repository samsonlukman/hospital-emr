import type { LoginLocationOption, OpenmrsLocation } from "../../types";
import { LOCATION_COOKIE } from "../../config/appConfig";
import { openmrsGet, setCookie } from "./client";
import { updateSessionLocation } from "./session";

interface LocationSearchResponse {
  results: OpenmrsLocation[];
}

export function fetchLocation(uuid: string): Promise<OpenmrsLocation> {
  return openmrsGet<OpenmrsLocation>(
    `/openmrs/ws/rest/v1/location/${encodeURIComponent(uuid)}?v=full`,
  );
}

export async function fetchLoginLocations(): Promise<LoginLocationOption[]> {
  const query = new URLSearchParams({
    tag: "Login Location",
    v: "default",
  });
  const data = await openmrsGet<LocationSearchResponse>(
    `/openmrs/ws/rest/v1/location?${query.toString()}`,
  );
  return (data.results ?? []).map((location) => ({
    uuid: location.uuid,
    name: location.display || location.name,
  }));
}

export async function fetchLocationByName(name: string): Promise<LoginLocationOption | null> {
  const expected = name.trim().toLowerCase();
  const query = new URLSearchParams({
    q: name,
    v: "default",
    limit: "20",
  });
  try {
    const data = await openmrsGet<LocationSearchResponse>(
      `/openmrs/ws/rest/v1/location?${query.toString()}`,
    );
    const match = (data.results ?? []).find(
      (location) => (location.display || location.name || "").trim().toLowerCase() === expected,
    );
    if (match) {
      return { uuid: match.uuid, name: match.display || match.name };
    }
  } catch {
    // Fall through to the tagged login-location list.
  }
  const locations = await fetchLoginLocations();
  return locations.find((location) => location.name.trim().toLowerCase() === expected) ?? null;
}

export async function changeLoginLocation(location: LoginLocationOption): Promise<void> {
  await updateSessionLocation(location.uuid);
  setCookie(
    LOCATION_COOKIE,
    JSON.stringify({ name: location.name, uuid: location.uuid }),
  );
}
