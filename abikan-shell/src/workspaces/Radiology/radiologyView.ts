export type RadiologyView = "worklist" | "new-study" | "history";

export function radiologyViewFromNav(navItemId: string | null): RadiologyView {
  if (navItemId === "new-study" || navItemId === "history") {
    return navItemId;
  }
  if (
    navItemId === "worklist" ||
    navItemId === "radiology-dashboard" ||
    navItemId === "orders" ||
    navItemId === "requests" ||
    !navItemId
  ) {
    return "worklist";
  }
  return "worklist";
}
