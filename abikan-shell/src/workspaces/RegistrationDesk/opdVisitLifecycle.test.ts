import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { CONSULTATION_ENCOUNTER_TYPE } from "../../config/clinicalConcepts.ts";
import {
  attendingDoctorFromVisitEncounters,
  MISSING_ATTENDING_DOCTOR,
} from "../../services/openmrs/visitAttendingProvider.ts";
import { createVisitShowsCardFee } from "./receptionVisit.ts";
import {
  shouldOfferStartVisit,
  patientOwnsVisit,
  VISIT_ALREADY_OPEN_MESSAGE,
} from "./receptionVisit.ts";

const here = dirname(fileURLToPath(import.meta.url));

function source(relative: string): string {
  return readFileSync(join(here, relative), "utf8");
}

describe("OPD visit lifecycle — current behavior", () => {
  it("starts an OPD visit as open because stopDatetime is empty", () => {
    assert.equal(shouldOfferStartVisit({ openVisit: null, admissionActive: false }), true);
    assert.equal(
      shouldOfferStartVisit({ openVisit: { uuid: "opd-open" }, admissionActive: false }),
      false,
    );
  });

  it("blocks a second visit while this patient's OPD visit is still open", () => {
    assert.equal(
      shouldOfferStartVisit({ openVisit: { uuid: "visit-a" }, admissionActive: false }),
      false,
    );
    assert.equal(VISIT_ALREADY_OPEN_MESSAGE.includes("Continue with the existing visit"), true);
  });

  it("lets a later visit start after the previous OPD visit is closed", () => {
    assert.equal(shouldOfferStartVisit({ openVisit: null, admissionActive: false }), true);
  });

  it("identifies the attending doctor from the Consultation encounter provider", () => {
    const name = attendingDoctorFromVisitEncounters([
      {
        uuid: "consult-1",
        encounterDatetime: "2026-09-03T10:00:00.000+0000",
        encounterType: { uuid: CONSULTATION_ENCOUNTER_TYPE, name: "Consultation" },
        encounterProviders: [
          {
            provider: {
              display: "doctor.abikan - Clinical Doctor",
              person: { display: "Clinical Doctor" },
            },
          },
        ],
      },
    ]);
    assert.equal(name, "Clinical Doctor");
    assert.equal(attendingDoctorFromVisitEncounters([]), MISSING_ATTENDING_DOCTOR);
  });

  it("does not treat an IPD admission as an OPD visit that can be started", () => {
    assert.equal(shouldOfferStartVisit({ openVisit: null, admissionActive: true }), false);
  });

  it("keeps future-dated open visits as blocking, not expired", () => {
    assert.equal(
      shouldOfferStartVisit({ openVisit: { uuid: "future-opd" }, admissionActive: false }),
      false,
    );
  });

  it("does not load card pricing on Create Visit", () => {
    const createVisit = source("CreateVisitWorkspace.tsx");
    assert.equal(createVisitShowsCardFee(), false);
    assert.equal(createVisit.includes("fetchRegistrationCharge"), false);
    assert.equal(createVisit.includes("Individual Card"), false);
    assert.equal(createVisit.includes("Family Card"), false);
  });

  it("never uses another patient's visit as this patient's open visit", () => {
    assert.equal(patientOwnsVisit("patient-a", "patient-b"), false);
    assert.equal(patientOwnsVisit("patient-a", "patient-a"), true);
  });

  it("lets Reception close a completed OPD visit, but not the doctor chart", () => {
    const createVisit = source("CreateVisitWorkspace.tsx");
    const register = source("RegistrationPatientWorkspace.tsx");
    const consult = source("../Doctor/ConsultationWorkspace.tsx");
    const encounter = source("../../services/openmrs/clinicalEncounter.ts");
    assert.equal(createVisit.includes("closeRegistrationVisit"), true);
    assert.equal(createVisit.includes("CLOSE_VISIT_LABEL"), true);
    assert.equal(createVisit.includes("endVisit"), false);
    assert.equal(register.includes("closeRegistrationVisit"), false);
    assert.equal(consult.includes("closeRegistrationVisit"), false);
    assert.equal(consult.includes("endVisit"), false);
    assert.equal(consult.includes("stopDatetime"), false);
    assert.equal(encounter.includes("stopDatetime"), false);
    assert.equal(encounter.includes('"/openmrs/ws/rest/v1/visit"'), true);
  });

  it("does not invent a 24-hour OPD expiry in the Reception visit helpers", () => {
    const helpers = source("receptionVisit.ts");
    assert.equal(/24.?hour|expir|auto.?clos/i.test(helpers), false);
  });
});
