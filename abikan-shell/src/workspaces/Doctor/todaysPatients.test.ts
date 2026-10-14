import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CLINICAL_TODAY_EXCLUDED_VISIT_TYPE_NAMES,
  CLINICAL_TODAY_VISIT_TYPE_NAMES,
} from "../../config/clinicalConcepts.ts";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes.ts";
import { isClinicalTodayVisitType, latestPatientsFirst, mapTodaysPatientRow } from "./todaysPatients.ts";
import type { DoctorQueueRow } from "../../types/index.ts";

describe("isClinicalTodayVisitType", () => {
  it("includes OPD, Special OPD, Follow Up, and ANC from this installation", () => {
    for (const name of CLINICAL_TODAY_VISIT_TYPE_NAMES) {
      assert.equal(isClinicalTodayVisitType(name), true);
    }
    assert.equal(isClinicalTodayVisitType("ANC"), true);
  });

  it("excludes IPD and EMERGENCY from the ordinary doctor list", () => {
    for (const name of CLINICAL_TODAY_EXCLUDED_VISIT_TYPE_NAMES) {
      assert.equal(isClinicalTodayVisitType(name), false);
    }
  });

  it("does not treat an unknown visit type as today's clinical work", () => {
    assert.equal(isClinicalTodayVisitType(""), false);
    assert.equal(isClinicalTodayVisitType("Unknown"), false);
  });
});

describe("mapTodaysPatientRow", () => {
  it("maps visit payload fields without exposing a waiting count", () => {
    const row = mapTodaysPatientRow({
      patient: "Adaeze Okafor",
      mrn: "ABC200003",
      visitType: "OPD",
      time: "08:40",
      status: "Open",
      dailyVisitNumber: "001",
      patientUuid: "patient-1",
      visitUuid: "visit-1",
    });
    assert.deepEqual(row, {
      id: "visit-1",
      patientUuid: "patient-1",
      visitUuid: "visit-1",
      patientName: "Adaeze Okafor",
      mrn: "ABC200003",
      visitType: "OPD",
      time: "08:40",
      status: "Open",
      dailyVisitNumber: "001",
      visitStart: "",
    });
  });

  it("lists the latest visit first", () => {
    const row = (visitStart: string, number: string): DoctorQueueRow => ({
      id: number,
      patientUuid: number,
      visitUuid: number,
      patientName: number,
      mrn: number,
      visitType: "OPD",
      time: "08:00",
      status: "Open",
      dailyVisitNumber: number,
      visitStart,
    });
    const ordered = latestPatientsFirst([
      row("2026-10-08T08:00:00.000+0000", "001"),
      row("2026-10-08T14:10:00.000+0000", "004"),
      row("2026-10-08T11:00:00.000+0000", "003"),
    ]);
    assert.deepEqual(
      ordered.map((item) => item.dailyVisitNumber),
      ["004", "003", "001"],
    );
  });

  it("keeps the stored OpenMRS visit type and only maps the doctor-facing label", () => {
    const opd = mapTodaysPatientRow({
      patient: "Adaeze Okafor",
      mrn: "ABC200003",
      visitType: "OPD",
      patientUuid: "patient-1",
      visitUuid: "visit-opd",
    });
    const followUp = mapTodaysPatientRow({
      patient: "Aisha Ibrahim",
      mrn: "ABC200018",
      visitType: "Follow Up",
      patientUuid: "patient-2",
      visitUuid: "visit-fu",
    });
    const retrospective = mapTodaysPatientRow({
      patient: "Test User Testing",
      mrn: "ABC200018",
      visitType: "Special OPD",
      patientUuid: "patient-3",
      visitUuid: "visit-special",
    });
    assert.equal(opd?.visitType, "OPD");
    assert.equal(followUp?.visitType, "Follow Up");
    assert.equal(retrospective?.visitType, "Special OPD");
    assert.equal(receptionVisitTypeLabel(opd?.visitType), "General Outpatient");
    assert.equal(receptionVisitTypeLabel(followUp?.visitType), "Follow-up");
    assert.equal(receptionVisitTypeLabel(retrospective?.visitType), "Retrospective visit");
    assert.equal(receptionVisitTypeLabel("EMERGENCY"), "Emergency");
    assert.equal(receptionVisitTypeLabel("IPD"), "Admission");
    assert.equal(receptionVisitTypeLabel("ANC"), "Antenatal Care (ANC)");
  });

  it("keeps a stored hospital-wide number even when Clinical skips a visit type", () => {
    const row = mapTodaysPatientRow({
      patient: "Aisha Ibrahim",
      mrn: "ABC200018",
      visitType: "Follow Up",
      dailyVisitNumber: "003",
      patientUuid: "patient-3",
      visitUuid: "visit-3",
    });
    assert.equal(row?.dailyVisitNumber, "003");
  });

  it("drops rows that cannot open a patient record", () => {
    assert.equal(
      mapTodaysPatientRow({
        patient: "Unknown",
        visitUuid: "visit-1",
      }),
      null,
    );
  });
});
