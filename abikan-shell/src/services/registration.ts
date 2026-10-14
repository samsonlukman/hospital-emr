import type { HospitalFamily } from "../types/hospitalFamily";
import type { RegistrationCardType } from "../types/registration";
import type {
  RegistrationChargePayload,
  RegistrationCreateResult,
  RegistrationMatch,
  RegistrationMetadata,
  RegistrationPatientDraft,
  RegistrationPatientProfile,
  RegistrationClosedVisit,
  RegistrationStartedVisit,
  RegistrationVisitContext,
} from "../types/registration";
import { isExistingVisitCode } from "../workspaces/RegistrationDesk/receptionVisit";
import { PatientAccountRequestError } from "./patientAccount";

export class RegistrationRequestError extends PatientAccountRequestError {
  matches: RegistrationMatch[];
  families: HospitalFamily[];

  constructor(
    message: string,
    status?: number,
    code?: string,
    matches: RegistrationMatch[] = [],
    families: HospitalFamily[] = [],
  ) {
    super(message, status, code);
    this.name = "RegistrationRequestError";
    this.matches = matches;
    this.families = families;
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
    matches?: RegistrationMatch[];
    families?: HospitalFamily[];
  };
  if (response.status === 401) {
    throw new RegistrationRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new RegistrationRequestError(
      body.message || "This action requires Reception access.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new RegistrationRequestError(
      body.message || "Unable to complete the registration request.",
      response.status,
      body.code,
      body.matches || [],
      body.families || [],
    );
  }
  return body as T;
}

export function fetchRegistrationMetadata(): Promise<RegistrationMetadata> {
  return readJson("/openmrs/abikan-api/registration/metadata");
}

export function fetchRegistrationProfile(patientUuid: string): Promise<RegistrationPatientProfile> {
  return readJson(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}/profile`,
  );
}

export function createRegistrationPatient(
  draft: RegistrationPatientDraft,
  options: { confirmDuplicate?: boolean; confirmCreateFamily?: boolean } = {},
): Promise<RegistrationCreateResult> {
  return readJson("/openmrs/abikan-api/registration/patients", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      ...draft,
      confirmDuplicate: Boolean(options.confirmDuplicate),
      confirmCreateFamily: Boolean(options.confirmCreateFamily),
    }),
  });
}

export function updateRegistrationPatient(
  patientUuid: string,
  draft: RegistrationPatientDraft,
): Promise<RegistrationPatientProfile> {
  return readJson(`/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(draft),
  });
}

export async function startRegistrationVisit(
  patientUuid: string,
  visitTypeUuid: string,
  locationUuid: string,
  requestId: string,
  visitTypeName?: string,
): Promise<RegistrationStartedVisit> {
  const response = await fetch(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}/visit`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ visitTypeUuid, locationUuid, requestId, visitTypeName }),
    },
  );
  const body = (await response.json().catch(() => ({}))) as RegistrationStartedVisit & {
    message?: string;
    code?: string;
    matches?: RegistrationMatch[];
  };
  if (response.status === 401) {
    throw new RegistrationRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new RegistrationRequestError(
      body.message || "This action requires Reception access.",
      403,
      "forbidden",
    );
  }
  if (response.ok || isExistingVisitCode(body.code) || body.status === "existing") {
    return body as RegistrationStartedVisit;
  }
  throw new RegistrationRequestError(
    body.message || "Unable to complete the registration request.",
    response.status,
    body.code,
    body.matches || [],
  );
}

export async function closeRegistrationVisit(
  patientUuid: string,
  visitUuid: string,
): Promise<RegistrationClosedVisit> {
  const response = await fetch(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}/visit/${encodeURIComponent(visitUuid)}/close`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: "{}",
    },
  );
  const body = (await response.json().catch(() => ({}))) as RegistrationClosedVisit & {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new RegistrationRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new RegistrationRequestError(
      body.message || "This action requires Reception access.",
      403,
      "forbidden",
    );
  }
  if (response.ok) {
    return body as RegistrationClosedVisit;
  }
  throw new RegistrationRequestError(
    body.message || "The visit could not be closed.",
    response.status,
    body.code,
  );
}

export function fetchRegistrationVisitContext(
  patientUuid: string,
): Promise<RegistrationVisitContext> {
  return readJson(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}/visit`,
  );
}

export function fetchRegistrationCharge(patientUuid: string): Promise<RegistrationChargePayload> {
  return readJson<RegistrationChargePayload>(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}`,
  );
}

export function createRegistrationCharge(
  patientUuid: string,
  visitUuid: string,
  requestId: string,
  cardType: RegistrationCardType = "individual",
): Promise<RegistrationChargePayload> {
  return readJson<RegistrationChargePayload>(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}/charge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ visitUuid, requestId, cardType }),
    },
  );
}

export function newRegistrationRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `reg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function emptyRegistrationDraft(): RegistrationPatientDraft {
  return {
    givenName: "",
    middleName: "",
    familyName: "",
    gender: "",
    birthdate: "",
    birthdateEstimated: false,
    age: "",
    attributes: {},
    address: {},
    otherIdentifiers: [],
    nextOfKin: {
      givenName: "",
      familyName: "",
      relationshipType: "",
      gender: "F",
    },
    familyMode: "none",
    familyId: "",
    householdName: "",
    familyRelationship: "Family member",
    nhis: false,
  };
}
