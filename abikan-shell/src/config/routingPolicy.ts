import type { ShellRoute } from "../app/hashRoute";

export function fallbackRouteForUser(
  route: ShellRoute,
  isAdmin: boolean,
  departmentRoute: ShellRoute,
): ShellRoute {
  if (route === "unavailable") {
    return isAdmin ? "unavailable" : departmentRoute;
  }
  if (route === "workspace") {
    return departmentRoute;
  }
  if (route === "home" && !isAdmin) {
    return departmentRoute;
  }
  return route;
}
