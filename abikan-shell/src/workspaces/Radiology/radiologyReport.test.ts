import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { OpenmrsRequestError } from "../../services/openmrs/client.ts";
import type { RadiologyNoteSummary } from "../../types";
import {
  NO_RADIOLOGY_REPORT,
  RADIOLOGY_NOTES_CONCEPT_UUID,
  RADIOLOGY_REPORT_PLACEHOLDER,
  canWriteRadiologyReport,
  existingRadiologyNoteUuid,
  preparedRadiologyReportText,
  radiologyExaminationReportView,
  radiologyNoteForListedOrder,
  radiologyNoteForOrder,
  radiologyNotesForVisit,
  radiologyReportActionLabel,
  radiologyReportAvailability,
  radiologyReportEncounterPayload,
  radiologyReportObservation,
  radiologyReportOpenLabel,
  radiologyReportStatusLabel,
  staffMessageForRadiologyReportError,
} from "./radiologyReport.ts";

const PATIENT_A = "26b50a91-0e06-4153-b872-530a9c67a4c8";
const PATIENT_B = "f242364e-b70f-4fec-b29e-8ad4fbe147b5";
const VISIT_16 = "0b99c191-5e6d-4784-8ecf-cb747cfccef3";
const VISIT_OTHER = "43518247-9125-478b-bbca-6a5473f0fb9b";
const VISIT_14 = "2857db49-c8fa-46d0-be38-2213f4cc54bc";
const ORD_16 = "a6e20ad8-7b64-49fc-9c87-8cb8a57d227d";
const ORD_14 = "c09b9e2f-cdcb-4db3-899e-16e3e6031dc6";
const NOTE_16 = "16742ff2-0e53-410e-a532-177ab4b716f6";
const ENC_16 = "5f8a2f36-6772-425e-9933-bf03b9219162";

function note(overrides: Partial<RadiologyNoteSummary> = {}): RadiologyNoteSummary {
  return {
    uuid: NOTE_16,
    value: "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY",
    observedAt: "24 Aug 2026 · 21:49",
    obsDatetime: "2026-08-24T20:49:41.000+0000",
    encounterUuid: ENC_16,
    orderUuid: ORD_16,
    visitUuid: VISIT_16,
    patientUuid: PATIENT_A,
    reportedBy: "Radiology Staff",
    ...overrides,
  };
}

describe("Radiology Desk report states", () => {
  it("treats a missing note as no report recorded", () => {
    assert.equal(radiologyReportAvailability(null), "pending");
    assert.equal(radiologyReportActionLabel(null), "Write Report");
    assert.equal(radiologyReportOpenLabel(null), "Write Report");
    assert.equal(radiologyReportStatusLabel(null), "Report pending");
    assert.equal(NO_RADIOLOGY_REPORT, "No report recorded for this examination.");
  });

  it("opens Edit Report when the order already has a note", () => {
    const existing = note();
    assert.equal(radiologyReportAvailability(existing), "available");
    assert.equal(radiologyReportActionLabel(existing), "Edit Report");
    assert.equal(radiologyReportOpenLabel(existing), "View Report");
    assert.equal(radiologyReportStatusLabel(existing), "Report available");
    assert.equal(existing.reportedBy, "Radiology Staff");
    assert.ok(existing.observedAt);
  });

  it("creates a Radiology Notes observation without a uuid", () => {
    const observation = radiologyReportObservation({
      value: "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY",
      orderUuid: ORD_16,
    });
    assert.equal(observation.uuid, undefined);
    assert.equal(observation.concept.uuid, RADIOLOGY_NOTES_CONCEPT_UUID);
    assert.equal(observation.concept.name, "Radiology Notes");
    assert.equal(observation.concept.dataType, "Text");
    assert.equal(observation.orderUuid, ORD_16);
    assert.equal(observation.voided, false);
  });

  it("updates the existing observation uuid instead of creating another", () => {
    const existing = note();
    const observation = radiologyReportObservation({
      observationUuid: existingRadiologyNoteUuid(existing),
      value: "Updated TEST report",
      orderUuid: ORD_16,
    });
    assert.equal(observation.uuid, NOTE_16);
    assert.equal(observation.orderUuid, ORD_16);
    assert.equal(observation.concept.uuid, RADIOLOGY_NOTES_CONCEPT_UUID);
  });

  it("does not save the placeholder or blank text", () => {
    assert.equal(preparedRadiologyReportText("").ok, false);
    assert.equal(preparedRadiologyReportText("   ").ok, false);
    assert.equal(preparedRadiologyReportText(RADIOLOGY_REPORT_PLACEHOLDER).ok, false);
    const saved = preparedRadiologyReportText("  Fracture of the distal radius.  ");
    assert.equal(saved.ok, true);
    if (saved.ok) {
      assert.equal(saved.text, "Fracture of the distal radius.");
    }
  });

  it("maps save failures to staff-facing messages", () => {
    assert.equal(
      staffMessageForRadiologyReportError(new OpenmrsRequestError("unauthenticated", 401)),
      "Sign in required.",
    );
    assert.equal(
      staffMessageForRadiologyReportError(new OpenmrsRequestError("forbidden", 403)),
      "You do not have permission to save this report.",
    );
    assert.equal(
      staffMessageForRadiologyReportError(new OpenmrsRequestError("missing", 404)),
      "This imaging request was not found.",
    );
    assert.equal(
      staffMessageForRadiologyReportError(new OpenmrsRequestError("This account is not set up as a clinician.")),
      "This account is not set up as a clinician.",
    );
    assert.equal(
      staffMessageForRadiologyReportError(new Error("ECONNRESET")),
      "The report could not be saved. Try again.",
    );
    assert.equal(
      staffMessageForRadiologyReportError(new Error("Failed to fetch")),
      "The report could not be saved. Try again.",
    );
    assert.equal(
      staffMessageForRadiologyReportError(new OpenmrsRequestError("unauthenticated", 401)),
      "Sign in required.",
    );
  });
});

describe("visit and order safety", () => {
  const rows = [
    note(),
    note({
      uuid: "other-note",
      orderUuid: ORD_14,
      visitUuid: VISIT_14,
      patientUuid: PATIENT_B,
      value: "Should never appear for ORD-16",
    }),
  ];

  it("shows the ORD-16 report on its selected visit", () => {
    const found = radiologyNoteForOrder(rows, {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      orderUuid: ORD_16,
    });
    assert.equal(found?.uuid, NOTE_16);
    assert.equal(found?.value, "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY");
    assert.equal(found?.encounterUuid, ENC_16);
  });

  it("does not show the report on another visit for the same patient", () => {
    assert.equal(
      radiologyNoteForOrder(rows, {
        patientUuid: PATIENT_A,
        visitUuid: VISIT_OTHER,
        orderUuid: ORD_16,
      }),
      null,
    );
    assert.deepEqual(
      radiologyNotesForVisit(rows, { patientUuid: PATIENT_A, visitUuid: VISIT_OTHER }),
      [],
    );
  });

  it("does not show the report on another patient's visit", () => {
    assert.equal(
      radiologyNoteForOrder(rows, {
        patientUuid: PATIENT_B,
        visitUuid: VISIT_14,
        orderUuid: ORD_16,
      }),
      null,
    );
    assert.equal(
      radiologyNoteForOrder(rows, {
        patientUuid: PATIENT_B,
        visitUuid: VISIT_16,
        orderUuid: ORD_16,
      }),
      null,
    );
  });

  it("does not attach the report to the wrong order", () => {
    assert.equal(
      radiologyNoteForOrder(rows, {
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
        orderUuid: ORD_14,
      }),
      null,
    );
  });

  it("keeps the same report after a refresh-style read of the same visit and order", () => {
    const first = radiologyNoteForOrder(rows, {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      orderUuid: ORD_16,
    });
    const refreshed = radiologyNoteForOrder(rows, {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      orderUuid: ORD_16,
    });
    assert.equal(first?.uuid, refreshed?.uuid);
    assert.equal(refreshed?.uuid, NOTE_16);
  });

  it("clears a stale report when the selected patient changes", () => {
    const previous = radiologyNoteForOrder(rows, {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      orderUuid: ORD_16,
    });
    assert.ok(previous);
    const switched = radiologyNotesForVisit(rows, {
      patientUuid: PATIENT_B,
      visitUuid: VISIT_16,
    });
    assert.deepEqual(switched, []);
    assert.equal(
      radiologyNoteForOrder(previous ? [previous] : [], {
        patientUuid: PATIENT_B,
        visitUuid: VISIT_16,
        orderUuid: ORD_16,
      }),
      null,
    );
  });

  it("refuses to write when visit or encounter is missing or mismatched", () => {
    assert.equal(
      canWriteRadiologyReport({
        patientUuid: PATIENT_A,
        visitUuid: "",
        encounterUuid: ENC_16,
        orderUuid: ORD_16,
      }).ok,
      false,
    );
    assert.equal(
      canWriteRadiologyReport({
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
        encounterUuid: "",
        orderUuid: ORD_16,
      }).ok,
      false,
    );
    assert.equal(
      canWriteRadiologyReport({
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
        encounterUuid: ENC_16,
        orderUuid: ORD_16,
        orderVisitUuid: VISIT_OTHER,
      }).ok,
      false,
    );
    assert.equal(
      canWriteRadiologyReport({
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
        encounterUuid: ENC_16,
        orderUuid: ORD_16,
        orderPatientUuid: PATIENT_B,
      }).ok,
      false,
    );
    assert.equal(
      canWriteRadiologyReport({
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
        encounterUuid: ENC_16,
        orderUuid: ORD_16,
        orderVisitUuid: VISIT_16,
        orderEncounterUuid: ENC_16,
        orderPatientUuid: PATIENT_A,
      }).ok,
      true,
    );
  });

  it("prefers the latest note when two notes exist for the same order, still one current report", () => {
    const older = note({
      uuid: "older",
      obsDatetime: "2026-08-24T20:00:00.000+0000",
      value: "Older",
    });
    const newer = note({
      uuid: "newer",
      obsDatetime: "2026-08-24T21:00:00.000+0000",
      value: "Newer",
    });
    const current = radiologyNoteForOrder([older, newer], {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      orderUuid: ORD_16,
    });
    assert.equal(current?.uuid, "newer");
    assert.equal(existingRadiologyNoteUuid(current), "newer");
  });

  it("does not treat a note without an order as the current order report", () => {
    const unbound = note({ orderUuid: "", uuid: "unbound" });
    assert.equal(
      radiologyNoteForOrder([unbound], {
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
        orderUuid: ORD_16,
      }),
      null,
    );
  });
});

describe("Doctor Workspace radiology reports", () => {
  const orders = [
    {
      uuid: ORD_16,
      investigation: "Musculoskeletal",
      billingStatus: "Price pending" as const,
    },
    {
      uuid: ORD_14,
      investigation: "Chest X-ray",
      billingStatus: "Paid" as const,
    },
  ];

  it("shows the report for the correct order on the selected visit", () => {
    const view = radiologyExaminationReportView(orders[0], [note()], {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
    });
    assert.equal(view.examination, "Musculoskeletal");
    assert.equal(view.report, "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY");
    assert.equal(view.reportedBy, "Radiology Staff");
    assert.equal(view.reportedAt, "24 Aug 2026 · 21:49");
    assert.equal(view.empty, null);
  });

  it("does not show a login id as the report author", () => {
    const view = radiologyExaminationReportView(
      orders[0],
      [note({ reportedBy: "radiology.abikan" })],
      {
        patientUuid: PATIENT_A,
        visitUuid: VISIT_16,
      },
    );
    assert.equal(view.reportedBy, "");
  });

  it("shows the empty state when no report exists for that examination", () => {
    const view = radiologyExaminationReportView(orders[0], [], {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
    });
    assert.equal(view.report, null);
    assert.equal(view.empty, "No report recorded for this examination.");
  });

  it("does not leak a report from another visit", () => {
    const view = radiologyExaminationReportView(orders[0], [note()], {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_OTHER,
    });
    assert.equal(view.report, null);
    assert.equal(view.empty, NO_RADIOLOGY_REPORT);
  });

  it("does not leak a report from another patient", () => {
    const view = radiologyExaminationReportView(orders[0], [note()], {
      patientUuid: PATIENT_B,
      visitUuid: VISIT_16,
    });
    assert.equal(view.report, null);
  });

  it("does not attach ORD-16's report to ORD-14", () => {
    const view = radiologyExaminationReportView(orders[1], [note()], {
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
    });
    assert.equal(view.report, null);
    assert.equal(view.examination, "Chest X-ray");
  });
});

describe("Radiology Notes storage payload", () => {
  it("reuses the existing Consultation and binds Radiology Notes to the order", () => {
    const created = radiologyReportEncounterPayload({
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      visitType: "OPD",
      encounterUuid: ENC_16,
      encounterDateTime: "2026-08-24T20:49:41.000+0000",
      locationUuid: "location-opd",
      providerUuid: "01a06b87-5fb5-43ef-a0c5-0d3a4fe1472b",
      observation: radiologyReportObservation({
        value: "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY",
        orderUuid: ORD_16,
      }),
    });
    assert.equal(created.encounterUuid, ENC_16);
    assert.ok(created.encounterUuid);
    assert.equal(created.visitUuid, VISIT_16);
    assert.equal(created.encounterTypeUuid, "d34fe3ab-5e07-11ef-8f7c-0242ac120002");
    assert.equal(created.orders.length, 0);
    assert.equal(created.observations.length, 1);
    assert.equal(created.observations[0]?.uuid, undefined);
    assert.equal(created.observations[0]?.concept.uuid, RADIOLOGY_NOTES_CONCEPT_UUID);
    assert.equal(created.observations[0]?.concept.name, "Radiology Notes");
    assert.equal(created.observations[0]?.orderUuid, ORD_16);
    assert.equal(created.providers[0]?.uuid, "01a06b87-5fb5-43ef-a0c5-0d3a4fe1472b");
  });

  it("updates the existing observation uuid instead of posting a second observation", () => {
    const updated = radiologyReportEncounterPayload({
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
      visitType: "OPD",
      encounterUuid: ENC_16,
      encounterDateTime: "2026-08-24T20:49:41.000+0000",
      locationUuid: "location-opd",
      providerUuid: "01a06b87-5fb5-43ef-a0c5-0d3a4fe1472b",
      observation: radiologyReportObservation({
        observationUuid: NOTE_16,
        value: "Updated TEST report",
        orderUuid: ORD_16,
      }),
    });
    assert.equal(updated.observations[0]?.uuid, NOTE_16);
    assert.equal(updated.encounterUuid, ENC_16);
    assert.equal(updated.orders.length, 0);
  });

  it("keeps listed-order lookup on the same patient and order", () => {
    const rows = [
      note(),
      note({
        uuid: "other-note",
        orderUuid: ORD_14,
        visitUuid: VISIT_14,
        patientUuid: PATIENT_B,
        value: "Should never appear for ORD-16",
      }),
    ];
    const found = radiologyNoteForListedOrder(rows, {
      uuid: ORD_16,
      patientUuid: PATIENT_A,
      visitUuid: VISIT_16,
    });
    assert.equal(found?.uuid, NOTE_16);
    assert.equal(
      radiologyNoteForListedOrder(rows, {
        uuid: ORD_16,
        patientUuid: PATIENT_B,
        visitUuid: VISIT_16,
      }),
      null,
    );
  });
});

