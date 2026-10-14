/**
 * Bahmni Clinical reads `bahmni.user` with $bahmniCookieStore.get:
 *   angular.fromJson(decodeURIComponent($.cookie("bahmni.user")))
 *
 * Bahmni login writes the username with angular.toJson(username), i.e.
 * JSON.stringify of a string: `"clinical.user"`.
 *
 * A plain username is not JSON and throws:
 *   SyntaxError: Unexpected token 'd', "…" is not valid JSON
 */

export function encodeBahmniUserCookie(username: string): string {
  return JSON.stringify(username);
}

export function usernameFromBahmniCookie(raw: string | null | undefined): string | null {
  if (raw == null) {
    return null;
  }
  const value = raw.trim();
  if (!value) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(value);
    if (typeof parsed === "string") {
      const username = parsed.trim();
      return username || null;
    }
    if (parsed && typeof parsed === "object" && "username" in parsed) {
      const username = String((parsed as { username?: unknown }).username ?? "").trim();
      return username || null;
    }
    return null;
  } catch {
    if (value.startsWith("{") || value.startsWith("[")) {
      return null;
    }
    return value;
  }
}

export function bahmniUserCookieNeedsRewrite(
  raw: string | null | undefined,
  username: string,
): boolean {
  return raw !== encodeBahmniUserCookie(username);
}
