import { PRIVILEGES, REGISTRATION_DESK_NAME } from "./appConfig";
import { hasHospitalAdminAccess } from "./adminAccess";
import { hasReceptionAccess } from "./receptionAccess";
import { HOSPITAL_INPATIENT_AREA_SET } from "./inpatientAreas";
import type { WorkspaceContext, WorkspaceDefinition, WorkspaceId } from "../types";

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

export function locationTagNames(tags: { name?: string; display?: string }[]): string[] {
  return tags
    .map((tag) => tag.name || tag.display || "")
    .filter(Boolean);
}

export function hasPrivilege(privileges: string[], privilege: string): boolean {
  return privileges.includes(privilege);
}

/**
 * SuperAdmin, System Developer, and Hospital Administrator may open every
 * implemented department. Ordinary users are privilege-gated, not room-gated.
 */
export function isFullAccessAdmin(context: WorkspaceContext): boolean {
  return context.roles.some(
    (role) =>
      role === "SuperAdmin" ||
      role === "System Developer" ||
      role === "Abikan:Hospital Admin",
  );
}

/** Hospital Administration without technical cross-department access. */
export function canOpenAdministration(context: WorkspaceContext): boolean {
  return hasHospitalAdminAccess(context.roles, context.privileges);
}

export function isRegistrationDesk(location: WorkspaceContext["location"]): boolean {
  return normalize(location.name) === normalize(REGISTRATION_DESK_NAME);
}

export function isOpdLocation(location: WorkspaceContext["location"]): boolean {
  return normalize(location.name).startsWith("opd");
}

export function isClinicalLocation(location: WorkspaceContext["location"]): boolean {
  const name = normalize(location.name);
  return (
    name.startsWith("opd") ||
    name === "emergency" ||
    name === "general ward" ||
    name === "pediatric ward"
  );
}

export function canOpenDoctor(context: WorkspaceContext): boolean {
  return isFullAccessAdmin(context) || hasPrivilege(context.privileges, PRIVILEGES.clinical);
}

export function isNursingLocation(location: WorkspaceContext["location"]): boolean {
  const name = normalize(location.name);
  return (
    HOSPITAL_INPATIENT_AREA_SET.has(name) ||
    name === "emergency" ||
    name === "general ward" ||
    name === "pediatric ward"
  );
}

export function canOpenNursing(context: WorkspaceContext): boolean {
  return isFullAccessAdmin(context) || hasPrivilege(context.privileges, PRIVILEGES.adt);
}

export function canOpenRegistration(context: WorkspaceContext): boolean {
  return isFullAccessAdmin(context) || hasReceptionAccess(context.roles, context.privileges);
}

/**
 * Laboratory is privilege-gated (app:lab-lite). SuperAdmin / System Developer
 * may also open it. There is no Laboratory login location on this OpenMRS,
 * so access is not location-locked.
 */
export function canOpenLaboratory(context: WorkspaceContext): boolean {
  return isFullAccessAdmin(context) || hasPrivilege(context.privileges, PRIVILEGES.labLite);
}

/**
 * Radiology is privilege-gated (app:radiology-upload). There is no
 * Radiology login location on this OpenMRS, so access is not location-locked.
 */
export function canOpenRadiology(context: WorkspaceContext): boolean {
  return isFullAccessAdmin(context) || hasPrivilege(context.privileges, PRIVILEGES.radiology);
}

/**
 * Pharmacy is privilege-gated (bahmni:clinical:dispense). There is no
 * Pharmacy login location on this OpenMRS, so access is not location-locked.
 */
export function canOpenPharmacy(context: WorkspaceContext): boolean {
  return isFullAccessAdmin(context) || hasPrivilege(context.privileges, PRIVILEGES.pharmacy);
}

/**
 * Patient Account is a read-only financial view. Any user who can already
 * open a patient workspace may open it. Access is not location-locked.
 */
export function canOpenPatientAccount(context: WorkspaceContext): boolean {
  return (
    isFullAccessAdmin(context) ||
    canOpenAccountant(context) ||
    hasPrivilege(context.privileges, PRIVILEGES.registration) ||
    hasPrivilege(context.privileges, PRIVILEGES.clinical) ||
    hasPrivilege(context.privileges, PRIVILEGES.adt) ||
    hasPrivilege(context.privileges, PRIVILEGES.labLite) ||
    hasPrivilege(context.privileges, PRIVILEGES.radiology) ||
    hasPrivilege(context.privileges, PRIVILEGES.pharmacy) ||
    hasPrivilege(context.privileges, PRIVILEGES.admin) ||
    canOpenAdministration(context)
  );
}

/**
 * Accountant / Cashier. OpenMRS is not modified: the hospital must assign
 * privilege `abikan:accountant` when a dedicated cashier account exists.
 * SuperAdmin / System Developer may open the workspace for this phase.
 * Clinical and pharmacy privileges do not grant payment rights.
 */
export function canOpenAccountant(context: WorkspaceContext): boolean {
  return (
    isFullAccessAdmin(context) ||
    hasPrivilege(context.privileges, PRIVILEGES.accountant)
  );
}

export function canOpenHmo(context: WorkspaceContext): boolean {
  return (
    isFullAccessAdmin(context) ||
    canOpenAdministration(context) ||
    canOpenRegistration(context) ||
    canOpenNursing(context) ||
    canOpenAccountant(context)
  );
}

export function hasAnyHospital EMRWorkplace(context: WorkspaceContext): boolean {
  return (
    isFullAccessAdmin(context) ||
    canOpenAdministration(context) ||
    canOpenRegistration(context) ||
    canOpenDoctor(context) ||
    canOpenNursing(context) ||
    canOpenLaboratory(context) ||
    canOpenRadiology(context) ||
    canOpenPharmacy(context) ||
    canOpenAccountant(context)
  );
}

/** Daily room prices. Hospital Admin and SuperAdmin / System Developer. */
export function canOpenAccommodationSettings(context: WorkspaceContext): boolean {
  return canOpenAdministration(context);
}

/**
 * Landing workspace from privileges, not from the OpenMRS room list.
 */
export const workspaceMap: WorkspaceDefinition[] = [
  {
    id: "registration-desk",
    label: "Reception",
    match: (context) => canOpenRegistration(context) && !isFullAccessAdmin(context),
  },
  {
    id: "doctor",
    label: "Doctor / Consultant",
    match: (context) => canOpenDoctor(context) && !isFullAccessAdmin(context),
  },
  {
    id: "nursing",
    label: "Nursing / Ward",
    match: (context) => canOpenNursing(context) && !isFullAccessAdmin(context),
  },
];

export function resolveWorkspaceId(context: WorkspaceContext): WorkspaceId {
  if (canOpenRegistration(context) && !isFullAccessAdmin(context) && !canOpenDoctor(context) && !canOpenNursing(context)) {
    return "registration-desk";
  }
  if (canOpenDoctor(context) && !isFullAccessAdmin(context) && !canOpenRegistration(context) && !canOpenNursing(context)) {
    return "doctor";
  }
  if (canOpenNursing(context) && !isFullAccessAdmin(context) && !canOpenDoctor(context) && !canOpenRegistration(context)) {
    return "nursing";
  }
  return "coming-soon";
}
