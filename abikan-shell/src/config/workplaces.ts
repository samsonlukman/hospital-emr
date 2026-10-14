import { PRIVILEGES } from "./appConfig";
import {
  canOpenAdministration,
  canOpenAccountant,
  canOpenDoctor,
  canOpenLaboratory,
  canOpenNursing,
  canOpenPharmacy,
  canOpenRadiology,
  canOpenRegistration,
  hasPrivilege,
  isFullAccessAdmin,
} from "./workspaceMap";
import { fallbackRouteForUser } from "./routingPolicy";
import { switchableWorkplaceIds } from "./workplaceSwitcher";
import type { ShellRoute } from "../app/hashRoute";
import type { WorkspaceContext } from "../types";

/**
 * Hospital EMR workplace = the department a staff member works in.
 * OpenMRS location = the hidden clinical location the session still needs.
 * Staff never pick rooms, beds, or OPD-1 / OPD-2 as a "workplace".
 */
export type WorkplaceId =
  | "administration"
  | "registration"
  | "clinical"
  | "nursing"
  | "pharmacy"
  | "laboratory"
  | "radiology"
  | "accountant";

export interface WorkplaceDefinition {
  id: WorkplaceId;
  label: string;
  /** Hash route after login. */
  route: ShellRoute;
  /**
   * OpenMRS login location used silently for visits/encounters.
   * Not shown as a workplace name.
   */
  sessionLocationName: string;
  canOpen: (context: WorkspaceContext) => boolean;
}

export const WORKPLACE_PROPERTY = "abikan.workplace";

export const WORKPLACES: WorkplaceDefinition[] = [
  {
    id: "registration",
    label: "Reception",
    route: "registration-desk",
    sessionLocationName: "Registration Desk",
    canOpen: canOpenRegistration,
  },
  {
    id: "clinical",
    label: "Clinical",
    route: "doctor",
    sessionLocationName: "OPD-1",
    canOpen: canOpenDoctor,
  },
  {
    id: "nursing",
    label: "Nursing",
    route: "nursing",
    sessionLocationName: "General Ward",
    canOpen: canOpenNursing,
  },
  {
    id: "pharmacy",
    label: "Pharmacy",
    route: "pharmacy",
    sessionLocationName: "Registration Desk",
    canOpen: canOpenPharmacy,
  },
  {
    id: "laboratory",
    label: "Laboratory",
    route: "laboratory",
    sessionLocationName: "Registration Desk",
    canOpen: canOpenLaboratory,
  },
  {
    id: "radiology",
    label: "Radiology",
    route: "radiology",
    sessionLocationName: "Registration Desk",
    canOpen: canOpenRadiology,
  },
  {
    id: "accountant",
    label: "Accountant",
    route: "accountant",
    sessionLocationName: "Registration Desk",
    canOpen: canOpenAccountant,
  },
  {
    id: "administration",
    label: "Administration",
    route: "home",
    sessionLocationName: "Registration Desk",
    canOpen: canOpenAdministration,
  },
];

const MULTI_PRIVILEGE_ORDER: WorkplaceId[] = [
  "clinical",
  "nursing",
  "registration",
  "pharmacy",
  "laboratory",
  "radiology",
  "accountant",
];

export function workplaceById(id: WorkplaceId): WorkplaceDefinition {
  const found = WORKPLACES.find((item) => item.id === id);
  if (!found) {
    throw new Error("Unknown workplace");
  }
  return found;
}

export function allowedWorkplaces(context: WorkspaceContext): WorkplaceDefinition[] {
  return WORKPLACES.filter((workplace) => workplace.canOpen(context));
}

/**
 * SuperAdmin and Hospital Administrator may switch across every department.
 * Ordinary staff only get a switcher when they have more than one approved
 * department. Unassigned departments and Administration stay hidden.
 */
export function switchableWorkplaces(context: WorkspaceContext): WorkplaceDefinition[] {
  return switchableWorkplaceIds(
    isFullAccessAdmin(context),
    allowedWorkplaces(context).map((item) => item.id),
  ).map((id) => workplaceById(id as WorkplaceId));
}

export function resolveDefaultWorkplace(context: WorkspaceContext): WorkplaceDefinition {
  if (canOpenAdministration(context)) {
    return workplaceById("administration");
  }

  const allowed = allowedWorkplaces(context);
  const namedRaw = context.userProperties?.[WORKPLACE_PROPERTY];
  const named = (namedRaw === "reception" ? "registration" : namedRaw) as WorkplaceId | undefined;
  if (named) {
    const preferred = allowed.find((item) => item.id === named);
    if (preferred) {
      return preferred;
    }
  }

  if (allowed.length === 1) {
    return allowed[0];
  }

  for (const id of MULTI_PRIVILEGE_ORDER) {
    const match = allowed.find((item) => item.id === id);
    if (match) {
      return match;
    }
  }

  return workplaceById("administration");
}

export function workplaceFromRoute(route: ShellRoute): WorkplaceId | null {
  if (
    route === "home" ||
    route === "workspace" ||
    route === "staff-accounts" ||
    route === "department-access" ||
    route === "admin-analytics" ||
    route === "admin-audit" ||
    route === "admin-export" ||
    route === "admin-log" ||
    route === "admin-patients" ||
    route === "admin-patient-record" ||
    route === "admin-hmo-bills" ||
    route === "admin-certificates" ||
    route === "accommodation-settings"
  ) {
    return "administration";
  }
  if (route === "unavailable") {
    return null;
  }
  if (
    route === "registration-desk" ||
    route === "registration-patient" ||
    route === "registration-register" ||
    route === "registration-visit" ||
    route === "registration-antenatal" ||
    route === "registration-antenatal-register" ||
    route === "registration-patients" ||
    route === "registration-patient-record" ||
    route === "registration-families" ||
    route === "registration-family"
  ) {
    return "registration";
  }
  if (route === "doctor" || route === "consultation") {
    return "clinical";
  }
  if (route === "nursing" || route === "nursing-patient") {
    return "nursing";
  }
  if (route === "pharmacy" || route === "pharmacy-patient" || route === "pharmacy-prescription") {
    return "pharmacy";
  }
  if (
    route === "laboratory" ||
    route === "laboratory-patient" ||
    route === "laboratory-order" ||
    route === "laboratory-external"
  ) {
    return "laboratory";
  }
  if (route === "radiology" || route === "radiology-patient" || route === "radiology-order" || route === "radiology-external") {
    return "radiology";
  }
  if (route === "accountant" || route === "accountant-patient") {
    return "accountant";
  }
  if (route === "patient-account" || route === "patient-account-invoice") {
    return null;
  }
  return null;
}

export function workplaceLabel(context: WorkspaceContext, route: ShellRoute): string {
  const fromRoute = workplaceFromRoute(route);
  if (fromRoute) {
    return workplaceById(fromRoute).label;
  }
  return resolveDefaultWorkplace(context).label;
}

/** Staff-facing name. Never return an OpenMRS room or OPD code. */
export function displayWorkplaceName(context: WorkspaceContext, route: ShellRoute): string {
  return workplaceLabel(context, route);
}

export function canOpenWorkplaceId(context: WorkspaceContext, id: WorkplaceId): boolean {
  return workplaceById(id).canOpen(context);
}

export function hasAnyHospital EMRWorkplace(context: WorkspaceContext): boolean {
  return allowedWorkplaces(context).length > 0 || hasPrivilege(context.privileges, PRIVILEGES.admin);
}

/**
 * Staff never land in Administration unless they are SuperAdmin or Hospital Administrator.
 * Unknown hashes stay in the user's department; they do not become Administration.
 */
export function resolveRouteForUser(route: ShellRoute, context: WorkspaceContext): ShellRoute {
  return fallbackRouteForUser(
    route,
    canOpenAdministration(context),
    resolveDefaultWorkplace(context).route,
  );
}
