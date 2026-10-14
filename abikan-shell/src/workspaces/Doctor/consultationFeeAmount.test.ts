import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatConsultationAmountNgn,
  parseConsultationAmount,
} from "./consultationFeeAmount.ts";

describe("parseConsultationAmount", () => {
  it("accepts a whole naira amount", () => {
    const result = parseConsultationAmount("5000");
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.equal(result.amount, 5000);
    }
  });

  it("accepts thousands separators and a leading naira label", () => {
    const result = parseConsultationAmount("₦ 5,000");
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.equal(result.amount, 5000);
    }
  });

  it("rejects empty, zero, negative, text, and foreign currency", () => {
    assert.equal(parseConsultationAmount("").ok, false);
    assert.equal(parseConsultationAmount("   ").ok, false);
    assert.equal(parseConsultationAmount("0").ok, false);
    assert.equal(parseConsultationAmount(-10).ok, false);
    assert.equal(parseConsultationAmount("abc").ok, false);
    assert.equal(parseConsultationAmount("5,000naira").ok, false);
    assert.equal(parseConsultationAmount("$75").ok, false);
    assert.equal(parseConsultationAmount("USD 75").ok, false);
    assert.equal(parseConsultationAmount("75.00.1").ok, false);
    assert.equal(parseConsultationAmount(Number.NaN).ok, false);
  });

  it("does not treat a currency symbol as part of the number", () => {
    const dollars = parseConsultationAmount("$5000");
    assert.equal(dollars.ok, false);
    const naira = parseConsultationAmount("₦5000");
    assert.equal(naira.ok, true);
    if (naira.ok) {
      assert.equal(naira.amount, 5000);
    }
  });
});

describe("formatConsultationAmountNgn", () => {
  it("formats the amount in naira", () => {
    assert.equal(formatConsultationAmountNgn(5000), "₦5,000");
  });
});
