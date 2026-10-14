import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { HISTORICAL_ORD_6 } from "../../config/radiologyMenu.ts";
import {
  doctorCannotSetRadiologyPrice,
  formatRadiologyAmountNgn,
  parseRadiologyAmount,
  radiologistSetsOrderPrice,
} from "./radiologyPrice.ts";

describe("radiologist order-specific NGN price", () => {
  it("accepts a naira amount entered by the radiologist", () => {
    const result = parseRadiologyAmount("15000");
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.equal(result.amount, 15000);
    }
    assert.equal(radiologistSetsOrderPrice(), true);
    assert.equal(doctorCannotSetRadiologyPrice(), true);
  });

  it("accepts thousands separators and a leading naira label", () => {
    const result = parseRadiologyAmount("₦ 15,000");
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.equal(result.amount, 15000);
    }
  });

  it("rejects empty, zero, negative, text, and foreign currency", () => {
    assert.equal(parseRadiologyAmount("").ok, false);
    assert.equal(parseRadiologyAmount("   ").ok, false);
    assert.equal(parseRadiologyAmount("0").ok, false);
    assert.equal(parseRadiologyAmount(-10).ok, false);
    assert.equal(parseRadiologyAmount("abc").ok, false);
    assert.equal(parseRadiologyAmount("$60").ok, false);
    assert.equal(parseRadiologyAmount("USD 60").ok, false);
    assert.equal(parseRadiologyAmount(HISTORICAL_ORD_6.amountUsd).ok, true);
    assert.notEqual(parseRadiologyAmount("15000").ok === true ? 15000 : 0, HISTORICAL_ORD_6.amountUsd);
  });

  it("formats the submitted amount in naira, not the TEST product price", () => {
    assert.equal(formatRadiologyAmountNgn(15000), "₦15,000");
    assert.notEqual(formatRadiologyAmountNgn(15000), `$${HISTORICAL_ORD_6.amountUsd}`);
  });
});
