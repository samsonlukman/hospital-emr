import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  consultationHref,
  parseShellHash,
  readConsultationPatientUuid,
  readConsultationVisitUuid,
} from "../../app/hashRoute.ts";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes.ts";
import type { PatientVisitSummary } from "../../types/index.ts";
import { visitNumberLabel } from "../../utils/dailyVisitNumber.ts";
import type { InpatientStay } from "../../types/inpatient.ts";
import {
  ADMIT_NURSING_ASSIGNS_BED,
  INPATIENT_ORDER_BLOCKED_AWAITING,
  INPATIENT_ORDER_BLOCKED_NO_CONTEXT,
  INPATIENT_ORDER_USES_ADMISSION,
  OUTPATIENT_VISIT_REQUIRED_LAB,
  OUTPATIENT_VISIT_REQUIRED_PRESCRIBE,
  activeConsultationVisit,
  bindConsultationVisit,
  canRequestAdmission,
  clinicalOrderVisit,
  clinicalOrderVisitType,
  consultationActionVisitUuid,
  consultationVisitHeaderLabel,
  doctorVisitLocationLabel,
  firstOpenVisit,
  isInternalOutpatientLocation,
  orderBlockedReason,
  resolveClinicalOrderContext,
  shouldOfferStartOpdVisit,
} from "./consultationVisit.ts";

function visit(overrides: Partial<PatientVisitSummary> & { uuid: string }): PatientVisitSummary {
  return {
    start: "04:16",
    startDate: "23 Aug 2026",
    startDatetime: "2026-08-23T03:16:00.000+0000",
    stop: null,
    visitType: "OPD",
    location: "OPD-1",
    open: true,
    dailyVisitNumber: "001",
    attendedBy: "",
    ...overrides,
  };
}

const visit001 = visit({
  uuid: "visit-001",
  dailyVisitNumber: "001",
  visitType: "OPD",
});
const visit002 = visit({
  uuid: "visit-002",
  dailyVisitNumber: "002",
  visitType: "OPD",
});
const visit003 = visit({
  uuid: "visit-003",
  dailyVisitNumber: "003",
  visitType: "Follow Up",
});

const samePatientVisits = [visit003, visit002, visit001];

describe("consultation route", () => {
  it("contains the selected visit in the Clinical hash", () => {
    const href = consultationHref("patient-fatima", "visit-001");
    assert.equal(href, "#/doctor/patient/patient-fatima/visit/visit-001");
    assert.equal(parseShellHash(href).route, "consultation");
    assert.equal(readConsultationPatientUuid(href), "patient-fatima");
    assert.equal(readConsultationVisitUuid(href), "visit-001");
  });

  it("keeps a patient-only hash when header search opens a patient", () => {
    const href = consultationHref("patient-musa");
    assert.equal(href, "#/doctor/patient/patient-musa");
    assert.equal(readConsultationVisitUuid(href), null);
  });

  it("replaces the previous patient's visit when header search switches patients", () => {
    const previous = consultationHref("patient-a", "visit-a-001");
    const next = consultationHref("patient-b");
    assert.equal(readConsultationPatientUuid(previous), "patient-a");
    assert.equal(readConsultationVisitUuid(previous), "visit-a-001");
    assert.equal(readConsultationPatientUuid(next), "patient-b");
    assert.equal(readConsultationVisitUuid(next), null);
    assert.equal(next.includes("visit-a-001"), false);
  });

  it("preserves the selected visit after a refresh-style hash read", () => {
    const href = consultationHref("patient-fatima", "visit-001");
    assert.equal(readConsultationVisitUuid(href), "visit-001");
    assert.notEqual(readConsultationVisitUuid(href), firstOpenVisit(samePatientVisits)?.uuid);
  });
});

describe("bindConsultationVisit", () => {
  it("loads the selected visit, not the first open visit", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: "visit-001",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    assert.equal(firstOpenVisit(samePatientVisits)?.uuid, "visit-003");
    assert.equal(bound.status, "selected");
    if (bound.status === "selected") {
      assert.equal(bound.visit.uuid, "visit-001");
      assert.equal(bound.visit.dailyVisitNumber, "001");
    }
  });

  it("distinguishes multiple visits for the same patient", () => {
    const first = bindConsultationVisit({
      selectedVisitUuid: "visit-001",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    const second = bindConsultationVisit({
      selectedVisitUuid: "visit-002",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    const third = bindConsultationVisit({
      selectedVisitUuid: "visit-003",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    assert.equal(consultationActionVisitUuid(first), "visit-001");
    assert.equal(consultationActionVisitUuid(second), "visit-002");
    assert.equal(consultationActionVisitUuid(third), "visit-003");
  });

  it("does not fall back to the first open visit when the selected visit is missing", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: "visit-gone",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
      extraVisit: null,
    });
    assert.equal(bound.status, "missing");
    assert.equal(activeConsultationVisit(bound), null);
    assert.equal(consultationActionVisitUuid(bound), undefined);
  });

  it("rejects a visit that belongs to another patient", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: "visit-other",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
      extraVisit: {
        visit: visit({ uuid: "visit-other", dailyVisitNumber: "009" }),
        patientUuid: "patient-musa",
      },
    });
    assert.equal(bound.status, "mismatch");
    assert.equal(consultationActionVisitUuid(bound), undefined);
  });

  it("does not invent a visit when header search opens a patient without one", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: null,
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    assert.equal(bound.status, "no-selection");
    assert.equal(consultationActionVisitUuid(bound), undefined);
    assert.notEqual(firstOpenVisit(samePatientVisits), undefined);
  });

  it("uses the selected visit for consultation and fee actions", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: "visit-001",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    const actionVisit = consultationActionVisitUuid(bound);
    assert.equal(actionVisit, "visit-001");
    assert.notEqual(actionVisit, firstOpenVisit(samePatientVisits)?.uuid);
    assert.equal(`consultation:${actionVisit}`, "consultation:visit-001");
  });

  it("keeps the stored visit type and uuid while doctors see the Reception label", () => {
    const bound = bindConsultationVisit({
      selectedVisitUuid: "visit-001",
      patientUuid: "patient-fatima",
      visits: samePatientVisits,
    });
    assert.equal(bound.status, "selected");
    if (bound.status !== "selected") {
      return;
    }
    assert.equal(bound.visit.uuid, "visit-001");
    assert.equal(bound.visit.visitType, "OPD");
    assert.equal(bound.visit.dailyVisitNumber, "001");
    assert.equal(visitNumberLabel(bound.visit.dailyVisitNumber), "Visit #001");
    assert.equal(receptionVisitTypeLabel(bound.visit.visitType), "General Outpatient");
    assert.equal(receptionVisitTypeLabel(visit003.visitType), "Follow-up");
    assert.equal(consultationVisitHeaderLabel(bound.visit), "Visit #001 · General Outpatient");
    assert.equal(consultationVisitHeaderLabel(visit003), "Visit #003 · Follow-up");
    assert.equal(bound.visit.location, "OPD-1");
    assert.equal(consultationVisitHeaderLabel(bound.visit)?.includes("OPD-1"), false);
    assert.equal(consultationVisitHeaderLabel(bound.visit)?.includes(" · OPD"), false);
  });
});

describe("consultation visit header labels", () => {
  it("maps OPD to General Outpatient and does not show OPD-1 as the visit type", () => {
    assert.equal(receptionVisitTypeLabel("OPD"), "General Outpatient");
    assert.equal(consultationVisitHeaderLabel(visit001), "Visit #001 · General Outpatient");
    assert.equal(isInternalOutpatientLocation(visit001.location), true);
    assert.equal(doctorVisitLocationLabel(visit001.location), undefined);
  });

  it("maps Follow Up to Follow-up", () => {
    assert.equal(receptionVisitTypeLabel("Follow Up"), "Follow-up");
    assert.equal(consultationVisitHeaderLabel(visit003), "Visit #003 · Follow-up");
  });

  it("maps EMERGENCY to Emergency and IPD to Admission", () => {
    assert.equal(receptionVisitTypeLabel("EMERGENCY"), "Emergency");
    assert.equal(receptionVisitTypeLabel("IPD"), "Admission");
    assert.equal(
      consultationVisitHeaderLabel(visit({ uuid: "e", visitType: "EMERGENCY", dailyVisitNumber: "004" })),
      "Visit #004 · Emergency",
    );
    assert.equal(
      consultationVisitHeaderLabel(visit({ uuid: "i", visitType: "IPD", dailyVisitNumber: "005" })),
      "Visit #005 · Admission",
    );
  });

  it("keeps a ward or Emergency location visible while hiding OPD-1", () => {
    assert.equal(doctorVisitLocationLabel("Emergency"), "Emergency");
    assert.equal(doctorVisitLocationLabel("Male Ward"), "Male Ward");
    assert.equal(doctorVisitLocationLabel("OPD-1"), undefined);
  });

  it("preserves the selected visit when the same patient has several open visits", () => {
    const first = activeConsultationVisit(
      bindConsultationVisit({
        selectedVisitUuid: "visit-001",
        patientUuid: "patient-fatima",
        visits: samePatientVisits,
      }),
    );
    const second = activeConsultationVisit(
      bindConsultationVisit({
        selectedVisitUuid: "visit-002",
        patientUuid: "patient-fatima",
        visits: samePatientVisits,
      }),
    );
    assert.equal(consultationVisitHeaderLabel(first), "Visit #001 · General Outpatient");
    assert.equal(consultationVisitHeaderLabel(second), "Visit #002 · General Outpatient");
    assert.notEqual(first?.uuid, firstOpenVisit(samePatientVisits)?.uuid);
    assert.equal(second?.uuid, "visit-002");
  });
});

const ipdVisit = visit({
  uuid: "visit-ipd",
  visitType: "IPD",
  location: "Male Ward",
  dailyVisitNumber: "010",
});

const closedOpd = visit({
  uuid: "visit-closed",
  visitType: "OPD",
  open: false,
  stop: "23 Aug 2026",
});

function occupiedStay(overrides: Partial<InpatientStay> = {}): InpatientStay {
  return {
    status: "ok",
    patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" },
    assignment: {
      areaName: "Male Ward",
      bedNumber: "02",
      status: "OCCUPIED",
    },
    visitUuid: "visit-ipd",
    visitStartDatetime: "2026-08-23T03:16:00.000+0000",
    admissionEncounterUuid: "admission-1",
    ...overrides,
  };
}

describe("inpatient clinical order context", () => {
  it("lets an admitted patient prescribe without selecting or starting a visit", () => {
    const context = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: null,
      stay: occupiedStay(),
      visits: [ipdVisit, closedOpd],
    });
    assert.equal(context.status, "ready");
    if (context.status !== "ready") {
      return;
    }
    assert.equal(context.source, "active-admission");
    assert.equal(context.visit.uuid, "visit-ipd");
    assert.equal(context.visit.visitType, "IPD");
    assert.equal(shouldOfferStartOpdVisit({
      orderContext: context,
      stay: occupiedStay(),
      patientUuid: "patient-fatima",
    }), false);
    assert.equal(orderBlockedReason(context, "prescribe"), "");
    assert.equal(INPATIENT_ORDER_USES_ADMISSION.includes("current admission"), true);
    assert.equal(clinicalOrderVisitType(context.visit.visitType), "IPD");
    assert.notEqual(clinicalOrderVisitType(context.visit.visitType), "OPD");
  });

  it("uses the existing IPD visit when a closed OPD visit is selected", () => {
    const context = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: closedOpd,
      stay: occupiedStay(),
      visits: [ipdVisit, closedOpd],
    });
    assert.equal(clinicalOrderVisit(context)?.uuid, "visit-ipd");
    assert.notEqual(clinicalOrderVisit(context)?.uuid, closedOpd.uuid);
  });

  it("does not attach inpatient orders to an open OPD visit when the patient is admitted", () => {
    const context = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: visit001,
      stay: occupiedStay(),
      visits: [visit001, ipdVisit],
    });
    assert.equal(clinicalOrderVisit(context)?.uuid, "visit-ipd");
    assert.notEqual(clinicalOrderVisit(context)?.uuid, visit001.uuid);
  });

  it("does not invent a visit or use another patient's admission", () => {
    const otherStay = occupiedStay({
      patient: { uuid: "patient-musa", name: "Musa", mrn: "ABC2", sex: "M", age: "40" },
      visitUuid: "visit-musa-ipd",
    });
    const context = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: null,
      stay: otherStay,
      visits: samePatientVisits,
    });
    assert.equal(context.status, "blocked");
    if (context.status !== "blocked") {
      return;
    }
    assert.equal(context.code, "outpatient-visit-required");
    assert.notEqual(clinicalOrderVisit(context)?.uuid, "visit-musa-ipd");
    assert.equal(shouldOfferStartOpdVisit({
      orderContext: context,
      stay: otherStay,
      patientUuid: "patient-fatima",
    }), true);
  });

  it("keeps the outpatient open-visit requirement when the patient is not admitted", () => {
    const noSelection = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: null,
      stay: { status: "ok", patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" }, assignment: null },
      visits: samePatientVisits,
    });
    assert.equal(noSelection.status, "blocked");
    assert.equal(orderBlockedReason(noSelection, "prescribe"), OUTPATIENT_VISIT_REQUIRED_PRESCRIBE);
    assert.equal(orderBlockedReason(noSelection, "laboratory"), OUTPATIENT_VISIT_REQUIRED_LAB);
    assert.notEqual(firstOpenVisit(samePatientVisits), undefined);

    const selectedOpen = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: visit001,
      stay: { status: "ok", patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" }, assignment: null },
      visits: samePatientVisits,
    });
    assert.equal(selectedOpen.status, "ready");
    if (selectedOpen.status === "ready") {
      assert.equal(selectedOpen.source, "selected-open");
      assert.equal(selectedOpen.visit.uuid, "visit-001");
      assert.equal(clinicalOrderVisitType(selectedOpen.visit.visitType), "OPD");
    }
  });

  it("explains a missing bed or missing admission visit instead of asking to start a visit", () => {
    const awaiting = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: null,
      stay: {
        status: "ok",
        patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" },
        assignment: null,
        awaiting: true,
      },
      visits: samePatientVisits,
    });
    assert.equal(awaiting.status, "blocked");
    if (awaiting.status === "blocked") {
      assert.equal(awaiting.code, "awaiting-bed");
      assert.equal(awaiting.reason, INPATIENT_ORDER_BLOCKED_AWAITING);
    }
    assert.equal(shouldOfferStartOpdVisit({
      orderContext: awaiting,
      stay: { status: "ok", patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" }, assignment: null, awaiting: true },
      patientUuid: "patient-fatima",
    }), false);

    const noVisit = resolveClinicalOrderContext({
      patientUuid: "patient-fatima",
      selectedVisit: null,
      stay: occupiedStay({ visitUuid: "" }),
      visits: samePatientVisits,
    });
    assert.equal(noVisit.status, "blocked");
    if (noVisit.status === "blocked") {
      assert.equal(noVisit.code, "no-inpatient-context");
      assert.equal(noVisit.reason, INPATIENT_ORDER_BLOCKED_NO_CONTEXT);
    }
  });
});

describe("doctor admission without an OPD visit", () => {
  it("lets the doctor admit when no visit is selected or open", () => {
    assert.equal(
      canRequestAdmission(
        {
          status: "ok",
          patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" },
          assignment: null,
        },
        "patient-fatima",
      ),
      true,
    );
    assert.equal(canRequestAdmission(null, "patient-fatima"), true);
    assert.equal(ADMIT_NURSING_ASSIGNS_BED.includes("Nursing will choose the ward"), true);
    assert.equal(ADMIT_NURSING_ASSIGNS_BED.includes("Start an open visit"), false);
  });

  it("does not treat another patient's admission as a reason to block this patient", () => {
    assert.equal(
      canRequestAdmission(
        occupiedStay({
          patient: { uuid: "patient-musa", name: "Musa", mrn: "ABC2", sex: "M", age: "40" },
        }),
        "patient-fatima",
      ),
      true,
    );
  });

  it("blocks a second admit after the decision or bed assignment", () => {
    assert.equal(
      canRequestAdmission(
        {
          status: "ok",
          patient: { uuid: "patient-fatima", name: "Fatima", mrn: "ABC1", sex: "F", age: "30" },
          assignment: null,
          awaiting: true,
          visitUuid: "visit-ipd",
        },
        "patient-fatima",
      ),
      false,
    );
    assert.equal(canRequestAdmission(occupiedStay(), "patient-fatima"), false);
  });
});
