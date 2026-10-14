import type { NavGroup } from "../types";

export const DOCTOR_NAV: NavGroup[] = [
  {
    id: "clinical",
    label: "Clinical",
    items: [
      { id: "doctor-queue", label: "Dashboard", kind: "route", href: "#/doctor", icon: "dashboard" },
      { id: "queue", label: "Today's Patients", kind: "route", href: "#/doctor/queue", icon: "clipboardList" },
      { id: "my-patients", label: "My Patients", kind: "route", href: "#/doctor/my-patients", icon: "users" },
      {
        id: "pharmacy-medicines",
        label: "Pharmacy medicines",
        kind: "route",
        href: "#/doctor/pharmacy-medicines",
        icon: "pill",
      },
      { id: "search", label: "Patients", kind: "action", action: "search", icon: "search" },
    ],
  },
];
