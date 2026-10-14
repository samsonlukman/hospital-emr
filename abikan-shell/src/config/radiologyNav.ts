import type { NavGroup } from "../types";

export const RADIOLOGY_NAV: NavGroup[] = [
  {
    id: "radiology",
    label: "Radiology",
    items: [
      {
        id: "radiology-dashboard",
        label: "Radiology",
        kind: "route",
        href: "#/radiology",
        icon: "dashboard",
      },
      {
        id: "worklist",
        label: "Worklist",
        kind: "route",
        href: "#/radiology/worklist",
        icon: "clipboardList",
      },
      {
        id: "new-study",
        label: "New Imaging Study",
        kind: "route",
        href: "#/radiology/new-study",
        icon: "clipboardPlus",
      },
      {
        id: "history",
        label: "Imaging History",
        kind: "route",
        href: "#/radiology/history",
        icon: "receipt",
      },
    ],
  },
];
