import type { LaboratoryBoardOrder, LaboratoryCatalogueTest } from "../../types/laboratoryCatalogue";

const BLOOD_BANK_NAME_PATTERNS = [
  /blood\s*group/i,
  /cross[\s-]*match/i,
  /blood\s*pint/i,
  /prospective\s*donor/i,
  /donor\s*(viral|screen|marker)/i,
];

export function isBloodBankCatalogueItem(row: {
  name?: string;
  department?: string;
  openmrsName?: string;
}): boolean {
  if ((row.department || "").trim().toLowerCase() === "blood bank") {
    return true;
  }
  const blob = `${row.name || ""} ${row.openmrsName || ""}`;
  return BLOOD_BANK_NAME_PATTERNS.some((pattern) => pattern.test(blob));
}

export function isBloodBankOrder(row: Pick<LaboratoryBoardOrder, "testName">): boolean {
  return isBloodBankCatalogueItem({ name: row.testName });
}

export function filterBloodBankOrders(orders: LaboratoryBoardOrder[]): LaboratoryBoardOrder[] {
  return orders.filter(isBloodBankOrder);
}

export function filterBloodBankCatalogue(tests: LaboratoryCatalogueTest[]): LaboratoryCatalogueTest[] {
  return tests.filter(isBloodBankCatalogueItem);
}

export function bloodBankKindLabel(name: string): string {
  const text = name || "";
  if (/pint/i.test(text)) {
    return "Blood product";
  }
  if (/donor/i.test(text)) {
    return "Donor screen";
  }
  if (/cross[\s-]*match/i.test(text)) {
    return "Cross-match";
  }
  if (/group/i.test(text)) {
    return "Blood group";
  }
  return "Blood bank";
}
