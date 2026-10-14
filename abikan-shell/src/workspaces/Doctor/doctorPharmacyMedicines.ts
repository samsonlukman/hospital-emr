import type { PharmacyCatalogueItem } from "../../types/pharmacy";

export const DOCTOR_PHARMACY_MEDICINES_TITLE = "Pharmacy medicines";
export const DOCTOR_PHARMACY_MEDICINES_HELP =
  "Medicines Pharmacy currently lists. In-stock items are shown first. Open a patient chart to prescribe.";
export const DOCTOR_PHARMACY_MEDICINES_EMPTY = "No medicines are listed as available in Pharmacy.";
export const DOCTOR_PHARMACY_MEDICINES_NONE_FOUND = "No matching medicines.";

function matchesMedicine(row: PharmacyCatalogueItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.name, row.hospitalName, row.listedAs, row.brandName, row.strength, row.form].some((value) =>
    (value || "").toLowerCase().includes(needle),
  );
}

export function doctorVisiblePharmacyMedicines(items: PharmacyCatalogueItem[]): PharmacyCatalogueItem[] {
  return items
    .filter((row) => row.available)
    .slice()
    .sort((left, right) => {
      const stock = Number(right.stockOnHand > 0) - Number(left.stockOnHand > 0);
      if (stock !== 0) {
        return stock;
      }
      return left.name.localeCompare(right.name) || left.strength.localeCompare(right.strength);
    });
}

export function filterDoctorPharmacyMedicines(
  items: PharmacyCatalogueItem[],
  query: string,
): PharmacyCatalogueItem[] {
  return doctorVisiblePharmacyMedicines(items).filter((row) => matchesMedicine(row, query));
}

export function doctorMedicineStockLabel(row: PharmacyCatalogueItem): string {
  const qty = Number(row.stockOnHand);
  if (!Number.isFinite(qty) || qty <= 0) {
    return "None in stock";
  }
  const units = row.stockUnits || "";
  const qtyText = String(qty).replace(/\.0$/, "");
  return units ? `${qtyText} in stock · ${units}` : `${qtyText} in stock`;
}
