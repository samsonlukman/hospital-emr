import type { NavGroup } from "../types";

export const PHARMACY_NAV: NavGroup[] = [
  {
    id: "pharmacy",
    label: "Pharmacy",
    items: [
      {
        id: "pharmacy-dashboard",
        label: "Dashboard",
        kind: "route",
        href: "#/pharmacy",
        icon: "dashboard",
      },
      {
        id: "prescriptions",
        label: "Prescriptions",
        kind: "route",
        href: "#/pharmacy/prescriptions",
        icon: "clipboardList",
      },
      {
        id: "new-sale",
        label: "New Sale",
        kind: "route",
        href: "#/pharmacy/new-sale",
        icon: "clipboardPlus",
      },
      {
        id: "sales-history",
        label: "Sales History",
        kind: "route",
        href: "#/pharmacy/sales-history",
        icon: "receipt",
      },
      {
        id: "catalogue",
        label: "Drug Catalogue",
        kind: "route",
        href: "#/pharmacy/catalogue",
        icon: "fileText",
      },
      {
        id: "pricing",
        label: "Drug Pricing",
        kind: "route",
        href: "#/pharmacy/pricing",
        icon: "naira",
      },
      {
        id: "inventory",
        label: "Inventory",
        kind: "route",
        href: "#/pharmacy/inventory",
        icon: "pill",
      },
    ],
  },
];
