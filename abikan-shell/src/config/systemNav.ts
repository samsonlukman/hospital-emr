import type { NavGroup } from "../types";

export const SYSTEM_NAV: NavGroup = {
  id: "system",
  label: "System",
  items: [
    {
      id: "system-settings",
      label: "System Settings",
      kind: "route",
      href: "#/system-settings",
      icon: "settings",
    },
  ],
};
