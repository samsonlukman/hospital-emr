import type { NavGroup } from "../types";

export const ACCOUNTANT_NAV: NavGroup[] = [
  {
    id: "accountant-overview",
    label: "Overview",
    items: [
      {
        id: "accountant-cashier",
        label: "Dashboard",
        kind: "route",
        href: "#/accountant",
        icon: "dashboard",
      },
    ],
  },
  {
    id: "accountant-billing",
    label: "Billing",
    items: [
      {
        id: "accountant-create",
        label: "Create bill",
        kind: "route",
        href: "#/accountant/create-bill",
        icon: "fileText",
      },
      {
        id: "accountant-outstanding",
        label: "Outstanding",
        kind: "route",
        href: "#/accountant/outstanding",
        icon: "creditCard",
      },
      {
        id: "accountant-deleted",
        label: "Deleted bills",
        kind: "route",
        href: "#/accountant/deleted",
        icon: "fileText",
      },
      {
        id: "accountant-waived",
        label: "Waived bills",
        kind: "route",
        href: "#/accountant/waived",
        icon: "fileText",
      },
      {
        id: "search",
        label: "Patient Accounts",
        kind: "action",
        action: "search",
        icon: "search",
      },
      {
        id: "hmo",
        label: "HMO patients",
        kind: "route",
        href: "#/hmo",
        icon: "creditCard",
      },
    ],
  },
  {
    id: "accountant-money",
    label: "Money",
    items: [
      {
        id: "accountant-payments",
        label: "Payments",
        kind: "route",
        href: "#/accountant/payments",
        icon: "receipt",
      },
      {
        id: "accountant-refunds",
        label: "Refunds",
        kind: "route",
        href: "#/accountant/refunds",
        icon: "fileText",
      },
    ],
  },
  {
    id: "accountant-reports",
    label: "Reports",
    items: [
      {
        id: "accountant-revenue",
        label: "Revenue",
        kind: "route",
        href: "#/accountant/revenue",
        icon: "chart",
      },
    ],
  },
];
