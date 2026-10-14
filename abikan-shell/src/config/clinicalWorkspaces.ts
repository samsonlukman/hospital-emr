import { PRIVILEGES, REGISTRATION_DESK_NAME } from "./appConfig";
import { canOpenAccommodationSettings, canOpenAccountant, hasPrivilege, isFullAccessAdmin } from "./workspaceMap";
import type { AppIconName, WorkspaceContext } from "../types";
import type { IconWellTone } from "../components/IconWell";

export type WorkspaceCardStatus = "ready" | "soon" | "needs-location";

export interface ClinicalWorkspace {
  id: string;
  label: string;
  description: string;
  icon: AppIconName;
  tone: IconWellTone;
  privilege?: string;
  matchLocation: (locationName: string) => boolean;
  locationHint?: string;
  implemented?: boolean;
  /** Open from any login location when the user has the privilege. */
  locationIndependent?: boolean;
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function isName(locationName: string, expected: string): boolean {
  return normalize(locationName) === normalize(expected);
}

export const CLINICAL_WORKSPACES: ClinicalWorkspace[] = [
  {
    id: "registration-desk",
    label: "Reception",
    description: "Register a new patient, or create a visit for someone already registered.",
    icon: "userPlus",
    tone: "registration",
    privilege: PRIVILEGES.registration,
    matchLocation: (name) => isName(name, REGISTRATION_DESK_NAME),
    implemented: true,
    locationIndependent: true,
  },
  {
    id: "appointments",
    label: "Appointments",
    description: "A dedicated appointment workspace will be added here.",
    icon: "calendar",
    tone: "appointments",
    privilege: PRIVILEGES.appointments,
    matchLocation: () => false,
  },
  {
    id: "emergency",
    label: "Emergency",
    description: "Emergency assessment and treatment will open from this workspace.",
    icon: "activity",
    tone: "visits",
    privilege: PRIVILEGES.emergency,
    matchLocation: (name) => isName(name, "Emergency"),
  },
  {
    id: "doctor",
    label: "Doctor / Consultant",
    description: "Today's queue, consultation, vitals and clinical review.",
    icon: "stethoscope",
    tone: "registration",
    privilege: PRIVILEGES.clinical,
    matchLocation: (name) => normalize(name).startsWith("opd"),
    implemented: true,
    locationIndependent: true,
  },
  {
    id: "nursing",
    label: "Nursing / Ward",
    description: "Ward board, beds, vitals, medication chart and nursing care.",
    icon: "bed",
    tone: "teal",
    privilege: PRIVILEGES.adt,
    matchLocation: (name) =>
      isName(name, "Emergency") ||
      isName(name, "General Ward") ||
      isName(name, "Pediatric Ward"),
    implemented: true,
    locationIndependent: true,
  },
  {
    id: "laboratory",
    label: "Laboratory",
    description: "Orders, samples, processing and results.",
    icon: "flask",
    tone: "collection",
    privilege: PRIVILEGES.labLite,
    matchLocation: () => false,
    locationIndependent: true,
    implemented: true,
  },
  {
    id: "radiology",
    label: "Radiology",
    description: "Imaging requests, studies and reports.",
    icon: "image",
    tone: "visits",
    privilege: PRIVILEGES.radiology,
    matchLocation: () => false,
    locationIndependent: true,
    implemented: true,
  },
  {
    id: "pharmacy",
    label: "Pharmacy",
    description: "Prescriptions and dispensing.",
    icon: "pill",
    tone: "teal",
    privilege: PRIVILEGES.pharmacy,
    matchLocation: () => false,
    locationIndependent: true,
    implemented: true,
  },
  {
    id: "accountant",
    label: "Accountant / Cashier",
    description: "Collect payment for unpaid bills.",
    icon: "creditCard",
    tone: "collection",
    privilege: PRIVILEGES.accountant,
    matchLocation: () => false,
    locationIndependent: true,
    implemented: true,
  },
  {
    id: "documents",
    label: "Patient Documents",
    description: "Document upload will open from this workspace.",
    icon: "folder",
    tone: "neutral",
    privilege: PRIVILEGES.documents,
    matchLocation: () => false,
  },
  {
    id: "reports",
    label: "Reports",
    description: "Hospital reports will open from this workspace.",
    icon: "fileText",
    tone: "collection",
    privilege: PRIVILEGES.reports,
    matchLocation: () => false,
  },
  {
    id: "accommodation-settings",
    label: "Accommodation prices",
    description: "Set the daily price for each ward and room.",
    icon: "settings",
    tone: "neutral",
    locationIndependent: true,
    implemented: true,
    matchLocation: () => false,
  },
  {
    id: "administration",
    label: "Administration",
    description: "Hospital administration will open from this workspace.",
    icon: "settings",
    tone: "neutral",
    privilege: PRIVILEGES.adminStaff,
    matchLocation: () => false,
  },
];

export interface VisibleWorkspace {
  workspace: ClinicalWorkspace;
  status: WorkspaceCardStatus;
  current: boolean;
}

export function visibleWorkspaces(context: WorkspaceContext): VisibleWorkspace[] {
  return CLINICAL_WORKSPACES.flatMap((workspace) => {
    const privileged =
      workspace.id === "accountant"
        ? canOpenAccountant(context)
        : workspace.id === "accommodation-settings"
          ? canOpenAccommodationSettings(context)
        : workspace.privilege
          ? hasPrivilege(context.privileges, workspace.privilege) || isFullAccessAdmin(context)
          : isFullAccessAdmin(context);
    if (!privileged) {
      return [];
    }
    if (!workspace.implemented && !isFullAccessAdmin(context)) {
      return [];
    }
    const status: WorkspaceCardStatus = workspace.implemented ? "ready" : "soon";
    return [{ workspace, status, current: false }];
  });
}

export function currentUnimplementedWorkspace(
  context: WorkspaceContext,
): ClinicalWorkspace | undefined {
  return CLINICAL_WORKSPACES.find(
    (workspace) => !workspace.implemented && workspace.matchLocation(context.location.name),
  );
}
