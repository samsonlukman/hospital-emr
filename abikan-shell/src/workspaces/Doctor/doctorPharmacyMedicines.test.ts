import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PharmacyCatalogueItem } from "../../types/pharmacy.ts";
import {
  doctorVisiblePharmacyMedicines,
  filterDoctorPharmacyMedicines,
} from "./doctorPharmacyMedicines.ts";

function item(overrides: Partial<PharmacyCatalogueItem>): PharmacyCatalogueItem {
  return {
    id: "drug-1",
    name: "Paracetamol 500 mg",
    hospitalName: "Paracetamol",
    listedAs: "",
    brandName: "",
    strength: "500 mg",
    form: "Tablet",
    stockOnHand: 12,
    stockUnits: "Tablet",
    price: {
      amount: 200,
      formatted: "₦200",
      currencyCode: "NGN",
      currencySymbol: "₦",
    },
    developmentPrice: false,
    developmentPriceNote: "",
    available: true,
    status: "Available",
    ...overrides,
  };
}

describe("doctor pharmacy medicines", () => {
  it("shows available medicines and puts in-stock items first", () => {
    const rows = doctorVisiblePharmacyMedicines([
      item({ id: "out", name: "Zinc", available: true, stockOnHand: 0 }),
      item({ id: "hidden", name: "Hidden", available: false, stockOnHand: 40 }),
      item({ id: "in", name: "Amoxicillin", available: true, stockOnHand: 8 }),
    ]);
    assert.deepEqual(
      rows.map((row) => row.id),
      ["in", "out"],
    );
  });

  it("filters by medicine name without showing unavailable items", () => {
    const visible = filterDoctorPharmacyMedicines(
      [
        item({ id: "para", name: "Paracetamol 500 mg" }),
        item({ id: "amox", name: "Amoxicillin 250 mg", available: false }),
      ],
      "para",
    );
    assert.equal(visible.length, 1);
    assert.equal(visible[0].id, "para");
  });
});
