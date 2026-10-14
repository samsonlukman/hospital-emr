/** Pure department-switcher rules. Kept free of OpenMRS/session imports so tests can run in Node. */

export const ADMIN_SWITCHER_IDS = [
  "administration",
  "registration",
  "clinical",
  "nursing",
  "pharmacy",
  "laboratory",
  "radiology",
  "accountant",
] as const;

export function switchableWorkplaceIds(
  isAdmin: boolean,
  allowedIds: readonly string[],
): string[] {
  if (isAdmin) {
    return [...ADMIN_SWITCHER_IDS];
  }
  const assigned = allowedIds.filter((id) => id !== "administration");
  return assigned.length > 1 ? assigned : [];
}
