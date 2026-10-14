/** Existing OpenMRS privilege and Hospital EMR roles for the Reception desk. */
export const RECEPTION_PRIVILEGE = "app:registration";

export const RECEPTION_ROLES = ["Abikan:Reception", "Abikan:Registration"] as const;

export function hasReceptionAccess(roles: string[], privileges: string[]): boolean {
  if (privileges.includes(RECEPTION_PRIVILEGE)) {
    return true;
  }
  return roles.some((role) => (RECEPTION_ROLES as readonly string[]).includes(role));
}
