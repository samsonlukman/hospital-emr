import type { NavGroup } from "../types";

export const ADMIN_NAV: NavGroup[] = [
  {
    id: "administration",
    label: "Administration",
    items: [
      {
        id: "admin-dashboard",
        label: "Dashboard",
        kind: "route",
        href: "#/home",
        icon: "dashboard",
      },
      {
        id: "admin-analytics",
        label: "Analytics",
        kind: "route",
        href: "#/admin/analytics",
        icon: "chart",
      },
      {
        id: "admin-audit",
        label: "Audit log",
        kind: "route",
        href: "#/admin/audit",
        icon: "clipboardList",
      },
      {
        id: "admin-export",
        label: "Data export",
        kind: "route",
        href: "#/admin/export",
        icon: "fileText",
      },
      {
        id: "admin-log",
        label: "Log",
        kind: "route",
        href: "#/admin/log",
        icon: "clipboardList",
      },
      {
        id: "admin-patients",
        label: "Patients",
        kind: "route",
        href: "#/admin/patients",
        icon: "users",
      },
      {
        id: "hmo",
        label: "HMO patients",
        kind: "route",
        href: "#/hmo",
        icon: "creditCard",
      },
      {
        id: "admin-hmo-bills",
        label: "HMO bills",
        kind: "route",
        href: "#/admin/hmo-bills",
        icon: "fileText",
      },
      {
        id: "admin-certificates",
        label: "Birth/Death Certificate",
        kind: "route",
        href: "#/admin/certificates",
        icon: "fileText",
      },
      {
        id: "users",
        label: "Staff directory",
        kind: "route",
        href: "#/staff-accounts",
        icon: "user",
      },
      {
        id: "access",
        label: "Department access",
        kind: "route",
        href: "#/department-access",
        icon: "users",
      },
      {
        id: "accommodation-settings",
        label: "Accommodation Prices",
        kind: "route",
        href: "#/accommodation-settings",
        icon: "settings",
      },
    ],
  },
];
