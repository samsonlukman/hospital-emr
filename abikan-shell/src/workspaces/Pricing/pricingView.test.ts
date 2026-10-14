import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { DepartmentPriceItem } from "../../types/departmentPricing.ts";
import { catalogueHint, matchesPriceSearch, parsePriceDraft, priceDraftError } from "./pricingView.ts";

function item(overrides: Partial<DepartmentPriceItem> = {}): DepartmentPriceItem {
  return {
    id: "individual",
    name: "Individual Card",
    kind: "card",
    mapping: "registration-individual",
    editable: true,
    price: {
      amount: 2000,
      formatted: "₦2,000.00",
      currencyCode: "NGN",
      currencySymbol: "₦",
      decimalPlaces: 2,
    },
    ...overrides,
  };
}

describe("department pricing helpers", () => {
  it("searches hospital names without requiring a UUID", () => {
    assert.equal(matchesPriceSearch(item(), "individual"), true);
    assert.equal(matchesPriceSearch(item({ name: "Malarial smear" }), "malaria"), true);
    assert.equal(matchesPriceSearch(item(), "pharmacy"), false);
  });

  it("rejects invalid price drafts and accepts naira amounts", () => {
    assert.equal(priceDraftError(""), "Enter a price of zero or more.");
    assert.equal(priceDraftError("-10"), "Enter a price of zero or more.");
    assert.equal(priceDraftError("abc"), "Enter a price of zero or more.");
    assert.equal(priceDraftError("1500"), "");
    assert.equal(parsePriceDraft("₦1,500"), 1500);
    assert.equal(parsePriceDraft("0"), 0);
  });

  it("keeps catalogue hints clinical, without integration mapping codes", () => {
    assert.equal(catalogueHint(item()), "");
    assert.equal(
      catalogueHint(item({ specimen: "Blood", type: "Panel", strength: "", form: "" })),
      "Blood · Panel",
    );
    assert.doesNotMatch(catalogueHint(item()), /registration-individual/);
  });
});
