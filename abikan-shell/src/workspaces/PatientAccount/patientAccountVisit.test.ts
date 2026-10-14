import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  parseShellHash,
  patientAccountHref,
  readPatientAccountUuid,
  readPatientAccountVisitUuid,
} from "../../app/hashRoute.ts";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes.ts";
import type { PatientVisitSummary } from "../../types/index.ts";
import { visitNumberLabel } from "../../utils/dailyVisitNumber.ts";
import { firstOpenVisit } from "../Doctor/consultationVisit.ts";
import {
  PATIENT_ACCOUNT_SHOWS_LOCATION,
  bindPatientAccountVisit,
  patientAccountVisitLabel,
  selectedPatientAccountVisit,
} from "./patientAccountVisit.ts";

function visit(overrides: Partial<PatientVisitSummary> & { uuid: string }): PatientVisitSummary {
  return {
    start: "00:38",
    startDate: "24 Aug 2026",
    startDatetime: "2026-08-23T23:38:00.000+0000",
    stop: null,
    visitType: "OPD",
    location: "OPD-1",
    open: true,
    dailyVisitNumber: "001",
    attendedBy: "Clinical Doctor",
    ...overrides,
  };
}

const visit001 = visit({
  uuid: "visit-001",
  dailyVisitNumber: "001",
  visitType: "OPD",
  location: "OPD-1",
});
const visit002 = visit({
  uuid: "visit-002",
  dailyVisitNumber: "002",
  visitType: "OPD",
  location: "OPD-1",
  startDate: "23 Aug 2026",
});
const visit003 = visit({
  uuid: "visit-003",
  dailyVisitNumber: "003",
  visitType: "Follow Up",
  location: "OPD-1",
  startDate: "23 Aug 2026",
});

const samePatientVisits = [visit003, visit002, visit001];

describe("patient account visit labels", () => {
  it("maps OPD to General Outpatient", () => {
    assert.equal(receptionVisitTypeLabel("OPD"), "General Outpatient");
    assert.equal(patientAccountVisitLabel(visit001), "Visit #001 · General Outpatient");
  });

  it("maps Follow Up to Follow-up", () => {
    assert.equal(receptionVisitTypeLabel("Follow Up"), "Follow-up");
    assert.equal(patientAccountVisitLabel(visit003), "Visit #003 · Follow-up");
  });

  it("maps EMERGENCY to Emergency", () => {
    assert.equal(receptionVisitTypeLabel("EMERGENCY"), "Emergency");
    assert.equal(
      patientAccountVisitLabel(visit({ uuid: "e", visitType: "EMERGENCY", dailyVisitNumber: "004" })),
      "Visit #004 · Emergency",
    );
  });

  it("maps IPD to Admission", () => {
    assert.equal(receptionVisitTypeLabel("IPD"), "Admission");
    assert.equal(
      patientAccountVisitLabel(visit({ uuid: "i", visitType: "IPD", dailyVisitNumber: "005" })),
      "Visit #005 · Admission",
    );
  });

  it("uses the stored daily visit number, not list position", () => {
    assert.equal(samePatientVisits[0]?.uuid, "visit-003");
    assert.equal(visitNumberLabel(visit002.dailyVisitNumber), "Visit #002");
    assert.equal(patientAccountVisitLabel(visit002), "Visit #002 · General Outpatient");
  });

  it("keeps the stored location as OPD-1 and does not show it as the visit", () => {
    assert.equal(visit001.location, "OPD-1");
    assert.equal(PATIENT_ACCOUNT_SHOWS_LOCATION, false);
    assert.equal(patientAccountVisitLabel(visit001)?.includes("OPD-1"), false);
    assert.equal(patientAccountVisitLabel(visit001), "Visit #001 · General Outpatient");
  });

  it("does not invent a visit label when no visit is selected", () => {
    assert.equal(patientAccountVisitLabel(null), undefined);
  });
});

describe("patient account selected visit", () => {
  it("uses the selected visit number and type", () => {
    const bound = bindPatientAccountVisit({
      selectedVisitUuid: "visit-001",
      patientUuid: "patient-a",
      visits: samePatientVisits,
    });
    const selected = selectedPatientAccountVisit(bound);
    assert.equal(selected?.uuid, "visit-001");
    assert.equal(selected?.dailyVisitNumber, "001");
    assert.equal(receptionVisitTypeLabel(selected?.visitType), "General Outpatient");
    assert.equal(selected?.location, "OPD-1");
  });

  it("distinguishes multiple visits for the same patient", () => {
    const first = selectedPatientAccountVisit(
      bindPatientAccountVisit({
        selectedVisitUuid: "visit-001",
        patientUuid: "patient-a",
        visits: samePatientVisits,
      }),
    );
    const third = selectedPatientAccountVisit(
      bindPatientAccountVisit({
        selectedVisitUuid: "visit-003",
        patientUuid: "patient-a",
        visits: samePatientVisits,
      }),
    );
    assert.equal(first?.dailyVisitNumber, "001");
    assert.equal(third?.dailyVisitNumber, "003");
    assert.equal(patientAccountVisitLabel(first), "Visit #001 · General Outpatient");
    assert.equal(patientAccountVisitLabel(third), "Visit #003 · Follow-up");
  });

  it("does not fall back to the first open visit", () => {
    const bound = bindPatientAccountVisit({
      selectedVisitUuid: "visit-002",
      patientUuid: "patient-a",
      visits: samePatientVisits,
    });
    assert.equal(selectedPatientAccountVisit(bound)?.uuid, "visit-002");
    assert.notEqual(selectedPatientAccountVisit(bound)?.uuid, firstOpenVisit(samePatientVisits)?.uuid);
  });

  it("does not invent a visit when none is selected", () => {
    const bound = bindPatientAccountVisit({
      selectedVisitUuid: null,
      patientUuid: "patient-a",
      visits: samePatientVisits,
    });
    assert.equal(bound.status, "no-selection");
    assert.equal(selectedPatientAccountVisit(bound), null);
  });

  it("clears the previous patient's visit when switching patients", () => {
    const previous = patientAccountHref("patient-a", "visit-001");
    const next = patientAccountHref("patient-b");
    assert.equal(readPatientAccountUuid(previous), "patient-a");
    assert.equal(readPatientAccountVisitUuid(previous), "visit-001");
    assert.equal(readPatientAccountUuid(next), "patient-b");
    assert.equal(readPatientAccountVisitUuid(next), null);
    assert.equal(next.includes("visit-001"), false);
    const bound = bindPatientAccountVisit({
      selectedVisitUuid: readPatientAccountVisitUuid(next),
      patientUuid: "patient-b",
      visits: samePatientVisits,
    });
    assert.equal(selectedPatientAccountVisit(bound), null);
  });

  it("rejects a visit that belongs to another patient", () => {
    const bound = bindPatientAccountVisit({
      selectedVisitUuid: "visit-other",
      patientUuid: "patient-b",
      visits: [],
      extraVisit: { visit: visit({ uuid: "visit-other" }), patientUuid: "patient-a" },
    });
    assert.equal(bound.status, "mismatch");
    assert.equal(selectedPatientAccountVisit(bound), null);
  });
});

describe("patient account route", () => {
  it("keeps the selected visit on the Patient Account hash", () => {
    const href = patientAccountHref("patient-a", "visit-001");
    assert.equal(href, "#/patient-account/patient-a/visit/visit-001");
    assert.equal(parseShellHash(href).route, "patient-account");
    assert.equal(readPatientAccountUuid(href), "patient-a");
    assert.equal(readPatientAccountVisitUuid(href), "visit-001");
  });

  it("keeps a patient-only account hash when no visit is selected", () => {
    const href = patientAccountHref("patient-a");
    assert.equal(href, "#/patient-account/patient-a");
    assert.equal(readPatientAccountVisitUuid(href), null);
    assert.equal(parseShellHash(href).route, "patient-account");
  });
});
