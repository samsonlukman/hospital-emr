import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DEFAULT_OUTPATIENT_LOCATION_NAME,
  RECEPTION_START_VISIT_TYPES,
  RECEPTION_VISIT_TYPE_COPY,
  isGeneralReceptionVisitType,
  isReceptionStartVisitType,
  receptionAsksForLocation,
  receptionLocationChoiceMode,
  receptionVisitTypeLabel,
} from "./receptionVisitTypes.ts";

describe("reception visit type labels", () => {
  it("maps OpenMRS visit types to Reception wording without renaming them", () => {
    assert.equal(receptionVisitTypeLabel("OPD"), "General Outpatient");
    assert.equal(receptionVisitTypeLabel("Follow Up"), "Follow-up");
    assert.equal(receptionVisitTypeLabel("EMERGENCY"), "Emergency");
    assert.equal(receptionVisitTypeLabel("IPD"), "Admission");
    assert.equal(receptionVisitTypeLabel("ANC"), "Antenatal Care (ANC)");
  });

  it("does not present Special OPD as a specialist clinic", () => {
    assert.equal(isReceptionStartVisitType("Special OPD"), false);
    assert.equal(receptionVisitTypeLabel("Special OPD"), "Retrospective visit");
    assert.equal(RECEPTION_VISIT_TYPE_COPY["Special OPD"], undefined);
  });

  it("includes nursing treatment alongside normal Reception start-visit types", () => {
    assert.deepEqual([...RECEPTION_START_VISIT_TYPES], [
      "OPD",
      "ANC",
      "Follow Up",
      "Nursing Treatment",
      "EMERGENCY",
      "IPD",
    ]);
    assert.deepEqual(Object.keys(RECEPTION_VISIT_TYPE_COPY), [
      "OPD",
      "Follow Up",
      "Nursing Treatment",
      "EMERGENCY",
      "IPD",
      "ANC",
    ]);
    assert.equal(RECEPTION_VISIT_TYPE_COPY.OPD.helper, "Regular outpatient consultation");
    assert.equal(RECEPTION_VISIT_TYPE_COPY["Follow Up"].helper, "Returning for a previous treatment or condition");
    assert.equal(RECEPTION_VISIT_TYPE_COPY.EMERGENCY.helper, "Urgent care");
    assert.equal(RECEPTION_VISIT_TYPE_COPY.IPD.helper, "Patient is being admitted");
    assert.equal(RECEPTION_VISIT_TYPE_COPY.ANC.helper, "Antenatal clinic visit for pregnancy care");
    for (const name of RECEPTION_START_VISIT_TYPES) {
      assert.equal(isReceptionStartVisitType(name), true);
    }
    assert.equal(isReceptionStartVisitType("Medical Officer"), false);
    assert.equal(isReceptionStartVisitType("Consultant"), false);
    assert.equal(isGeneralReceptionVisitType("OPD"), true);
    assert.equal(isGeneralReceptionVisitType("Follow Up"), true);
    assert.equal(isGeneralReceptionVisitType("EMERGENCY"), true);
    assert.equal(isGeneralReceptionVisitType("IPD"), true);
    assert.equal(isGeneralReceptionVisitType("ANC"), false);
  });

  it("hides outpatient, emergency, and ANC location choice and only asks for a ward on admission", () => {
    assert.equal(DEFAULT_OUTPATIENT_LOCATION_NAME, "OPD-1");
    assert.equal(receptionAsksForLocation("OPD"), false);
    assert.equal(receptionAsksForLocation("Follow Up"), false);
    assert.equal(receptionAsksForLocation("EMERGENCY"), false);
    assert.equal(receptionAsksForLocation("ANC"), false);
    assert.equal(receptionAsksForLocation("IPD"), true);
    assert.equal(receptionLocationChoiceMode("OPD", 2), "auto");
    assert.equal(receptionLocationChoiceMode("Follow Up", 2), "auto");
    assert.equal(receptionLocationChoiceMode("EMERGENCY", 1), "auto");
    assert.equal(receptionLocationChoiceMode("ANC", 2), "auto");
    assert.equal(receptionLocationChoiceMode("OPD", 0), "none");
    assert.equal(receptionLocationChoiceMode("IPD", 0), "none");
    assert.equal(receptionLocationChoiceMode("IPD", 1), "auto");
    assert.equal(receptionLocationChoiceMode("IPD", 4), "choose");
  });
});
