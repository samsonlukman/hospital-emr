import type { DrugOrderSummary } from "../../types";

const OPENMRS_ORDER_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** True only for real OpenMRS order ids (not drug-name fallbacks). */
export function isOpenmrsOrderUuid(value: string): boolean {
  return OPENMRS_ORDER_UUID.test(String(value || "").trim());
}

/** Pick newly persisted, UUID-shaped drug orders that are not already known. */
export function newDrugOrderUuidsFromList(
  latest: DrugOrderSummary[],
  priorUuids: ReadonlySet<string>,
): string[] {
  return latest
    .filter(
      (row) =>
        isOpenmrsOrderUuid(row.uuid) &&
        !priorUuids.has(row.uuid) &&
        row.status !== "Stopped",
    )
    .map((row) => row.uuid);
}
