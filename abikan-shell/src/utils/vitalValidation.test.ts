import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { VITAL_CONCEPTS } from "../config/clinicalConcepts.ts";
import type { VitalDraftValues } from "../services/openmrs/clinicalEncounter.ts";
import {
  parseVitalInput,
  validateVitalDraft,
  validateVitalField,
} from "./vitalValidation.ts";

const emptyRaw = {
  systolic: "",
  diastolic: "",
  pulse: "",
  temperature: "",
  spo2: "",
  weight: "",
  respiratoryRate: "",
  height: "",
};

describe("vital validation", () => {
  it("rejects non-numeric input using installed absolute ranges", () => {
    assert.equal(parseVitalInput(""), undefined);
    assert.equal(Number.isNaN(parseVitalInput("hot")), true);
    assert.deepEqual(validateVitalField("temperature", "hot"), {
      level: "block",
      message: "Enter a number",
    });
    assert.equal(validateVitalField("temperature", "12")?.level, "block");
    assert.equal(validateVitalField("temperature", "37.2"), null);
    assert.equal(VITAL_CONCEPTS.temperature.unit, "°C");
  });

  it("rejects incomplete blood pressure and empty recordings", () => {
    const incomplete = validateVitalDraft({ systolic: 120 }, { ...emptyRaw, systolic: "120" });
    assert.equal(
      incomplete.blocking.includes("Enter both systolic and diastolic pressure"),
      true,
    );
    const empty = validateVitalDraft({}, emptyRaw);
    assert.equal(empty.blocking.includes("Enter at least one vital sign"), true);
  });

  it("warns on unusual values without diagnosing", () => {
    const values: VitalDraftValues = { temperature: 38.5, pulse: 82 };
    const issues = validateVitalDraft(values, {
      ...emptyRaw,
      temperature: "38.5",
      pulse: "82",
    });
    assert.equal(issues.blocking.length, 0);
    assert.equal(issues.warnings.some((row) => row.includes("Temperature")), true);
    assert.equal(issues.warnings.some((row) => /septic|hypertensive/i.test(row)), false);
  });
});
