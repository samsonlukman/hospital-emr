import type { LaboratoryBoardOrder, LaboratoryCatalogueTest } from "../../types/laboratoryCatalogue";

export type LaboratoryView =
  | "dashboard"
  | "orders"
  | "pending"
  | "processing"
  | "completed"
  | "patients"
  | "pricing"
  | "reference-ranges"
  | "hospital-tests"
  | "create-test"
  | "blood-bank"
  | "inventory"
  | "new-order"
  | "history"
  | "deleted";

export const LABORATORY_DIRECT_LABEL = "Laboratory Direct";
export const DOCTOR_ORDER_LABEL = "Doctor Order";
export const EXTERNAL_REFERRAL_LABEL = "External Referral";
export const EXTERNAL_PATIENT_LABEL = "External Patient";
export const REGISTERED_PATIENT_LABEL = "Registered Patient";

/** Tests ordered together stay on one bill. Opening one of them still shows the others. */
export function laboratoryChargesForOrder<T extends { orderUuid: string; requestKey?: string }>(
  tests: T[],
  orderUuid?: string,
): T[] {
  if (!orderUuid) {
    return tests;
  }
  const anchor = tests.find((row) => row.orderUuid === orderUuid);
  if (!anchor?.requestKey) {
    return tests.filter((row) => row.orderUuid === orderUuid);
  }
  const same = tests.filter((row) => row.requestKey === anchor.requestKey);
  return same.length > 0 ? same : [anchor];
}

/** Show a result only when it is one of this test's own answers. */
export function enteredLaboratoryResult(
  value: string,
  options: Array<string | { value: string; label?: string }>,
): string {
  const text = value.trim();
  if (!text || options.length === 0) {
    return text;
  }
  const known = options.some((option) => {
    if (typeof option === "string") {
      return option === text;
    }
    return option.value === text || (option.label || "") === text;
  });
  return known ? text : "";
}

/** A positive/negative or written result is not a number with a unit and range. */
export function resultIsNumeric(test: { resultType?: string; options?: unknown[] }): boolean {
  if ((test.options || []).length > 0) {
    return false;
  }
  const kind = (test.resultType || "").trim().toUpperCase();
  return kind !== "D" && kind !== "A" && kind !== "R";
}

export function laboratoryViewFromNav(navItemId: string | null): LaboratoryView {
  if (
    navItemId === "new-order" ||
    navItemId === "history" ||
    navItemId === "deleted" ||
    navItemId === "deleted-orders" ||
    navItemId === "hospital-tests" ||
    navItemId === "create-test" ||
    navItemId === "blood-bank" ||
    navItemId === "inventory"
  ) {
    return navItemId === "deleted-orders" ? "deleted" : navItemId;
  }
  if (
    navItemId === "pending" ||
    navItemId === "processing" ||
    navItemId === "completed" ||
    navItemId === "patients" ||
    navItemId === "orders" ||
    navItemId === "pricing" ||
    navItemId === "reference-ranges"
  ) {
    return navItemId;
  }
  return "dashboard";
}

export function laboratoryRequestSourceLabel(
  source: string | undefined,
  comment?: string,
): string {
  if (source === "laboratory_direct") {
    return LABORATORY_DIRECT_LABEL;
  }
  if (source === "external_referral") {
    return EXTERNAL_REFERRAL_LABEL;
  }
  if (source === "doctor_order") {
    return DOCTOR_ORDER_LABEL;
  }
  const text = (comment || "").trim();
  if (text.startsWith("[Lab Direct]") || text.startsWith("[Laboratory Direct]")) {
    return LABORATORY_DIRECT_LABEL;
  }
  if (text.startsWith("[External Referral]")) {
    return EXTERNAL_REFERRAL_LABEL;
  }
  return DOCTOR_ORDER_LABEL;
}

export function laboratoryPatientTypeLabel(
  type: string | undefined,
  isExternal?: boolean,
): string {
  if (isExternal || type === "external") {
    return EXTERNAL_PATIENT_LABEL;
  }
  return REGISTERED_PATIENT_LABEL;
}

export function matchesLabSearch(row: LaboratoryBoardOrder, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.patientName, row.mrn, row.testName, row.orderNumber, row.provider]
    .join(" ")
    .toLowerCase()
    .includes(needle);
}

export function formatLabPrice(
  amount: number | null | undefined,
  symbol = "₦",
  code = "NGN",
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) {
    return "—";
  }
  const formatted = `${symbol}${Math.round(amount).toLocaleString("en-NG")}`;
  return code && code !== "NGN" ? `${formatted} ${code}` : formatted;
}

export function isLabPanel(test: Pick<LaboratoryCatalogueTest, "type" | "conceptClass">): boolean {
  const type = (test.type || "").toLowerCase();
  const klass = (test.conceptClass || "").toLowerCase();
  return type.includes("panel") || type.includes("profile") || klass === "labset";
}

export function canSelectLabTest(test: LaboratoryCatalogueTest): boolean {
  return Boolean(test.orderable && test.conceptUuid);
}

export function labCatalogueHitDetails(test: LaboratoryCatalogueTest): string {
  const bits = [
    isLabPanel(test) ? "Panel" : test.type || "",
    test.specimen || "",
    test.department || "",
    test.price?.formatted || "",
    test.outsourced ? "Outsourced" : "",
  ].filter(Boolean);
  const clinical =
    test.openmrsName && test.openmrsName.trim().toLowerCase() !== test.name.trim().toLowerCase()
      ? test.openmrsName
      : "";
  return [clinical, ...bits].filter(Boolean).join(" · ");
}

export function labStaffSeesPayment(status: string): boolean {
  return status === "UNPAID" || status === "PAID" || status === "PARTIALLY PAID";
}

export function doctorCannotCollectPayment(): boolean {
  return true;
}
