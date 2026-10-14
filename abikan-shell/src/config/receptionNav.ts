import type { NavGroup } from "../types";

export const RECEPTION_NAV: NavGroup[] = [
  {
    id: "reception",
    label: "Reception",
    items: [
      { id: "home", label: "Dashboard", kind: "route", href: "#/reception", icon: "dashboard" },
      { id: "register", label: "Register Patient", kind: "route", href: "#/reception/register", icon: "userPlus" },
      { id: "create-visit", label: "Create Visit", kind: "route", href: "#/reception/visit", icon: "clipboardPlus" },
      { id: "antenatal", label: "Antenatal Care", kind: "route", href: "#/reception/antenatal", icon: "clipboardList" },
      { id: "patients", label: "Patients", kind: "route", href: "#/reception/patients", icon: "users" },
      { id: "hmo", label: "HMO patients", kind: "route", href: "#/hmo", icon: "creditCard" },
      { id: "families", label: "Families", kind: "route", href: "#/reception/families", icon: "users" },
      { id: "todays-visits", label: "Today's Visits", kind: "route", href: "#/reception/visits", icon: "clipboardList" },
      { id: "pricing", label: "Pricing", kind: "route", href: "#/reception/pricing", icon: "naira" },
      { id: "patient-accounts", label: "Patient Accounts", kind: "action", action: "search", icon: "creditCard" },
    ],
  },
];
