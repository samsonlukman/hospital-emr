import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatClinicalWhen } from "./datetime.ts";

describe("formatClinicalWhen", () => {
  it("does not invent 1:00 for a date that has no time", () => {
    const shown = formatClinicalWhen("2026-10-12");
    assert.equal(shown.includes("1:00"), false);
    assert.match(shown, /12 Oct 2026|Oct 12, 2026/);
  });

  it("shows the Lagos clock for a real timestamp", () => {
    const shown = formatClinicalWhen("2026-10-12T16:55:55+00:00");
    assert.match(shown, /5:55/);
    assert.equal(shown.includes("1:00"), false);
  });
});
