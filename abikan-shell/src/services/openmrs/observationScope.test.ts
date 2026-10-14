import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { consultationHref, readConsultationPatientUuid, readConsultationVisitUuid } from "../../app/hashRoute.ts";
import { documentationForSelectedVisit } from "./clinicalDocumentation.ts";
import { consultationActionVisitUuid, bindConsultationVisit } from "../../workspaces/Doctor/consultationVisit.ts";
import type { PatientVisitSummary } from "../../types/index.ts";

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
    attendedBy: "",
    ...overrides,
  };
}

describe("clinical observation scope", () => {
  it("keeps complaint, HPI, and notes on the selected visit, not the latest patient obs", () => {
    const selected = "visit-001-today";
    const draft = documentationForSelectedVisit(
      { uuid: "older-visit", patient: { uuid: "patient-a" }, encounters: [] },
      selected,
      "patient-a",
    );
    assert.equal(draft.hpi, "");
    assert.equal(draft.consultationNote, "");
    assert.equal(draft.complaints.length, 0);
  });

  it("keeps Known Diagnoses, medications, orders, and vitals as patient-level chart data", () => {
    // These reads stay patient-scoped on purpose. New writes still use the selected visit.
    const bound = bindConsultationVisit({
      selectedVisitUuid: "visit-001-today",
      patientUuid: "patient-a",
      visits: [
        visit({ uuid: "visit-003", dailyVisitNumber: "003" }),
        visit({ uuid: "visit-001-today", dailyVisitNumber: "001" }),
      ],
    });
    assert.equal(consultationActionVisitUuid(bound), "visit-001-today");
  });

  it("keeps the consultation fee and save actions keyed by the selected visit", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: "2857db49-c8fa-46d0-be38-2213f4cc54bc",
      patientUuid: "f242364e-b70f-4fec-b29e-8ad4fbe147b5",
      visits: [visit({ uuid: "2857db49-c8fa-46d0-be38-2213f4cc54bc" })],
    });
    assert.equal(
      `consultation:${consultationActionVisitUuid(bound)}`,
      "consultation:2857db49-c8fa-46d0-be38-2213f4cc54bc",
    );
  });

  it("clears the previous patient's visit when header search switches patients", () => {
    const previous = consultationHref("patient-a", "visit-a-001");
    const next = consultationHref("patient-b");
    assert.equal(readConsultationPatientUuid(previous), "patient-a");
    assert.equal(readConsultationVisitUuid(previous), "visit-a-001");
    assert.equal(readConsultationPatientUuid(next), "patient-b");
    assert.equal(readConsultationVisitUuid(next), null);
  });

  it("preserves the selected visit after a refresh-style hash read", () => {
    const href = consultationHref("patient-a", "visit-001-today");
    assert.equal(readConsultationVisitUuid(href), "visit-001-today");
    assert.equal(readConsultationPatientUuid(href), "patient-a");
  });
});
