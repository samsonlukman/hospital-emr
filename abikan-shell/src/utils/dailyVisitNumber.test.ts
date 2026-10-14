import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  compareDailyVisitNumber,
  dailyVisitNumberFromAttributes,
  formatDailyVisitNumber,
  parseDailyVisitNumber,
  visitNumberLabel,
} from "./dailyVisitNumber.ts";

describe("daily visit number", () => {
  it("formats the stored sequence without using hospital numbers", () => {
    assert.equal(formatDailyVisitNumber(1), "001");
    assert.equal(formatDailyVisitNumber("12"), "012");
    assert.equal(parseDailyVisitNumber("ABC200016"), null);
    assert.equal(formatDailyVisitNumber("ABC200016"), "—");
  });

  it("resets display independently per hospital day values", () => {
    const dayOne = ["001", "002", "003"].map(formatDailyVisitNumber);
    const dayTwo = [1, 2].map(formatDailyVisitNumber);
    assert.deepEqual(dayOne, ["001", "002", "003"]);
    assert.deepEqual(dayTwo, ["001", "002"]);
  });

  it("keeps historical visits empty instead of inventing a rank", () => {
    assert.equal(formatDailyVisitNumber(""), "—");
    assert.equal(visitNumberLabel(undefined), "—");
    assert.equal(visitNumberLabel("001"), "Visit #001");
  });

  it("reads the stored visit attribute and ignores visit status", () => {
    assert.equal(
      dailyVisitNumberFromAttributes([
        { attributeType: { name: "Visit Status" }, value: "OPD" },
        { attributeType: { name: "Daily Visit Number" }, value: "003" },
      ]),
      "003",
    );
    assert.equal(dailyVisitNumberFromAttributes([]), "—");
  });

  it("sorts by the stored number and does not renumber Clinical gaps", () => {
    const rows = ["001", "—", "005", "003"];
    const ordered = [...rows].sort(compareDailyVisitNumber);
    assert.deepEqual(ordered, ["001", "003", "005", "—"]);
  });

  it("does not accept a client-supplied overwrite as a stored number", () => {
    assert.equal(parseDailyVisitNumber("999"), 999);
    assert.equal(formatDailyVisitNumber(null), "—");
  });
});
