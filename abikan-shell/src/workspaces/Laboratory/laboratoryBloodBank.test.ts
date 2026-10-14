import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  bloodBankKindLabel,
  filterBloodBankCatalogue,
  filterBloodBankOrders,
  isBloodBankCatalogueItem,
  isBloodBankOrder,
} from "./laboratoryBloodBank.ts";

describe("laboratory blood bank filters", () => {
  it("keeps blood bank services and grouping/cross-match, not every blood specimen test", () => {
    assert.equal(isBloodBankCatalogueItem({ department: "Blood Bank", name: "Positive Blood Pint" }), true);
    assert.equal(isBloodBankCatalogueItem({ name: "Blood Grouping" }), true);
    assert.equal(isBloodBankCatalogueItem({ name: "Grouping & Cross Match – per unit" }), true);
    assert.equal(
      isBloodBankCatalogueItem({
        name: "Prospective Donor Viral Marker Screening, Grouping & Crossmatch",
      }),
      true,
    );
    assert.equal(isBloodBankCatalogueItem({ name: "Full Blood Count (FBC)" }), false);
    assert.equal(isBloodBankCatalogueItem({ name: "Blood Culture" }), false);
    assert.equal(isBloodBankCatalogueItem({ name: "Fasting blood glucose" }), false);
  });

  it("filters board orders and catalogue rows", () => {
    const orders = filterBloodBankOrders([
      { testName: "Blood Grouping" },
      { testName: "Complete blood count" },
      { testName: "Blood cross-matching" },
    ] as never);
    assert.deepEqual(
      orders.map((row) => row.testName),
      ["Blood Grouping", "Blood cross-matching"],
    );
    assert.equal(isBloodBankOrder({ testName: "Negative Blood Pint" }), true);

    const catalogue = filterBloodBankCatalogue([
      { name: "Blood Grouping", department: "Haematology" },
      { name: "ESR", department: "Haematology" },
      { name: "Positive Blood Pint", department: "Blood Bank" },
    ] as never);
    assert.equal(catalogue.length, 2);
  });

  it("labels blood bank kinds in hospital language", () => {
    assert.equal(bloodBankKindLabel("Blood Grouping"), "Blood group");
    assert.equal(bloodBankKindLabel("Grouping & Cross Match – per unit"), "Cross-match");
    assert.equal(bloodBankKindLabel("Positive Blood Pint"), "Blood product");
    assert.equal(bloodBankKindLabel("Prospective Donor Viral Marker Screening"), "Donor screen");
  });
});
