import type { NavGroup, NavItem, WorkspaceContext } from "../types";
import { visibleWorkspaces } from "./clinicalWorkspaces";
import { isFullAccessAdmin } from "./workspaceMap";

export const CLINICAL_HOME_GROUP: NavGroup = {
  id: "abikan",
  label: "Hospital EMR",
  items: [
    {
      id: "clinical-home",
      label: "Home",
      kind: "route",
      href: "#/home",
      icon: "dashboard",
    },
  ],
};

export function clinicalHomeNav(context: WorkspaceContext): NavGroup[] {
  const items: NavItem[] = [];
  for (const { workspace, status } of visibleWorkspaces(context)) {
    if (status !== "ready") {
      if (isFullAccessAdmin(context)) {
        items.push({
          id: workspace.id,
          label: workspace.label,
          kind: "soon",
          icon: workspace.icon,
        });
      }
      continue;
    }
    const href =
      workspace.id === "registration-desk"
        ? "#/registration-desk"
        : workspace.id === "doctor"
          ? "#/doctor"
          : workspace.id === "nursing"
            ? "#/nursing"
            : workspace.id === "laboratory"
              ? "#/laboratory"
              : workspace.id === "radiology"
                ? "#/radiology"
                : workspace.id === "pharmacy"
                  ? "#/pharmacy"
                  : workspace.id === "accountant"
                    ? "#/accountant"
                    : workspace.id === "accommodation-settings"
                      ? "#/accommodation-settings"
                      : "";
    if (!href) {
      continue;
    }
    items.push({
      id: workspace.id,
      label: workspace.label,
      kind: "route",
      href,
      icon: workspace.icon,
    });
  }
  return [
    CLINICAL_HOME_GROUP,
    {
      id: "workspaces",
      label: "Departments",
      items,
    },
  ];
}
