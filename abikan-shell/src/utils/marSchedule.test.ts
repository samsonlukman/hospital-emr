import assert from "node:assert/strict";
import test from "node:test";
import { careSettingForVisitType } from "../services/openmrs/drugOrderMap.ts";

test("IPD prescriptions use the inpatient care setting that MAR schedules from", () => {
  assert.equal(careSettingForVisitType("IPD"), "INPATIENT");
  assert.equal(careSettingForVisitType("OPD"), "OUTPATIENT");
});
