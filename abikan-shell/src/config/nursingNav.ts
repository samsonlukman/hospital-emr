import type { NavGroup } from "../types";

export const NURSING_NAV: NavGroup[] = [
  {
    id: "nursing",
    label: "Nursing",
    items: [
      {
        id: "nursing-dashboard",
        label: "Dashboard",
        kind: "route",
        href: "#/nursing",
        icon: "dashboard",
      },
      {
        id: "ward-board",
        label: "Ward Board",
        kind: "route",
        href: "#/nursing/ward-board",
        icon: "bed",
      },
      {
        id: "patients",
        label: "Patients",
        kind: "route",
        href: "#/nursing/patients",
        icon: "search",
      },
      {
        id: "hmo",
        label: "HMO patients",
        kind: "route",
        href: "#/hmo",
        icon: "creditCard",
      },
      {
        id: "todays-visits",
        label: "Today's Visits",
        kind: "route",
        href: "#/nursing/visits",
        icon: "clipboardList",
      },
      {
        id: "treatments",
        label: "Treatment Queue",
        kind: "route",
        href: "#/nursing/treatments",
        icon: "clipboardPlus",
      },
      {
        id: "admissions",
        label: "Admissions",
        kind: "route",
        href: "#/nursing/admissions",
        icon: "clipboardPlus",
      },
      {
        id: "transfers",
        label: "Transfers",
        kind: "route",
        href: "#/nursing/transfers",
        icon: "activity",
      },
      {
        id: "discharges",
        label: "Discharges",
        kind: "route",
        href: "#/nursing/discharges",
        icon: "calendar",
      },
      {
        id: "pricing",
        label: "Bed Prices",
        kind: "route",
        href: "#/nursing/pricing",
        icon: "naira",
      },
    ],
  },
];
