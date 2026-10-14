export function isAttendanceTerminalLocation(
  pathname = typeof window === "undefined" ? "" : window.location.pathname,
  hash = typeof window === "undefined" ? "" : window.location.hash,
): boolean {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/abikan/log" || path === "/log") {
    return true;
  }
  const normalized = hash.replace(/^#/, "").replace(/^\/+/, "");
  return normalized === "log";
}
