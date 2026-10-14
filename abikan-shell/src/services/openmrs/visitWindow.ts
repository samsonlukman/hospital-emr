import { HOSPITAL_TIMEZONE, parseOpenmrsDateTime } from "../../utils/datetime.ts";

export const VISIT_NOT_STARTED_MESSAGE =
  "Visit has not started yet. Please wait until the visit starts before saving.";

export { HOSPITAL_TIMEZONE };

/**
 * OpenMRS rejects an encounter whose datetime is before visit.startDatetime.
 * Compare the visit start instant with "now". Both are absolute instants;
 * Africa/Lagos is the hospital zone used to interpret wall-clock test cases.
 * Missing or unreadable start times do not block save (preserve existing path).
 */
export function visitHasStarted(
  visitStartDatetime: string | number | Date | undefined | null,
  now: Date | number = Date.now(),
): boolean {
  const start = parseOpenmrsDateTime(visitStartDatetime);
  if (!start) {
    return true;
  }
  const nowMs = typeof now === "number" ? now : now.getTime();
  if (Number.isNaN(nowMs)) {
    return true;
  }
  return nowMs >= start.getTime();
}

export function consultationSaveBlockedByVisitWindow(
  visitStartDatetime: string | number | Date | undefined | null,
  now: Date | number = Date.now(),
): boolean {
  return !visitHasStarted(visitStartDatetime, now);
}
