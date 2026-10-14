import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RegistrationChargePayload, RegistrationStartedVisit } from "../../types/registration";
import {
  ADMISSION_IN_PROGRESS_CODE,
  ADMISSION_IN_PROGRESS_MESSAGE,
  CLOSE_VISIT_CONFIRM_COPY,
  CLOSE_VISIT_LABEL,
  CLOSING_VISIT_LABEL,
  CONTINUE_EXISTING_VISIT_LABEL,
  CREATE_VISIT_NO_CARD_COPY,
  VISIT_ALREADY_OPEN_CODE,
  VISIT_ALREADY_OPEN_MESSAGE,
  VISIT_CLOSED_SUCCESS_MESSAGE,
  canCloseOutpatientVisit,
  createVisitShowsCardFee,
  existingVisitNotice,
  isExistingVisitCode,
  outpatientVisitStatus,
  patientOwnsVisit,
  readStartVisitResult,
  shouldOfferCardFee,
  shouldOfferStartVisit,
  shouldShowCardFeeCard,
} from "./receptionVisit.ts";

function charge(
  overrides: Partial<RegistrationChargePayload> = {},
): RegistrationChargePayload {
  return {
    status: "ok",
    patient: { uuid: "patient-a", name: "Ada", mrn: "ABC1" },
    visit: null,
    feeName: "Individual Card",
    feeAmount: { amount: 2000, formatted: "₦2,000.00", currency: "NGN" },
    paymentStatus: "UNPAID",
    hasCharge: false,
    canCreateCharge: false,
    blockReason: null,
    ...overrides,
  };
}

function started(
  overrides: Partial<RegistrationStartedVisit> = {},
): RegistrationStartedVisit {
  return {
    status: "ok",
    created: true,
    uuid: "visit-a",
    visitType: "OPD",
    visitTypeLabel: "General Outpatient",
    location: "OPD-1",
    locationUuid: "opd-1",
    startDatetime: "2026-09-02T09:00:00.000+0000",
    open: true,
    ...overrides,
  };
}

describe("reception visit selection", () => {
  it("lets an existing patient with no open visit start a visit", () => {
    assert.equal(shouldOfferStartVisit({ openVisit: null, admissionActive: false }), true);
  });

  it("does not offer a second visit when this patient already has an open visit", () => {
    assert.equal(
      shouldOfferStartVisit({ openVisit: { uuid: "visit-a" }, admissionActive: false }),
      false,
    );
    assert.equal(
      existingVisitNotice({ openVisit: { uuid: "visit-a" }, admissionActive: false }),
      VISIT_ALREADY_OPEN_MESSAGE,
    );
  });

  it("does not offer an OPD visit for an admitted occupied patient", () => {
    assert.equal(shouldOfferStartVisit({ openVisit: null, admissionActive: true }), false);
    assert.equal(
      existingVisitNotice({ openVisit: null, admissionActive: true }),
      ADMISSION_IN_PROGRESS_MESSAGE,
    );
  });

  it("never treats another patient's visit as this patient's open visit", () => {
    assert.equal(patientOwnsVisit("patient-a", "patient-b"), false);
    assert.equal(patientOwnsVisit("patient-a", "patient-a"), true);
    assert.equal(patientOwnsVisit("patient-a", ""), false);
  });
});

describe("reception card fee", () => {
  it("still offers Individual/Family card fee for a new registration", () => {
    assert.equal(
      shouldOfferCardFee(charge({ canCreateCharge: true, cardAlreadyRegistered: false })),
      true,
    );
    assert.equal(
      shouldShowCardFeeCard(charge({ canCreateCharge: true, cardAlreadyRegistered: false })),
      true,
    );
  });

  it("never shows a card fee on Create Visit, even if a card invoice is missing", () => {
    assert.equal(createVisitShowsCardFee(), false);
    assert.equal(CREATE_VISIT_NO_CARD_COPY.includes("No hospital card fee"), true);
    assert.equal(CONTINUE_EXISTING_VISIT_LABEL, "Continue with existing visit");
    const neverBilled = charge({
      canCreateCharge: true,
      cardAlreadyRegistered: false,
      hasCharge: false,
    });
    assert.equal(createVisitShowsCardFee(), false);
    assert.notEqual(neverBilled.canCreateCharge, createVisitShowsCardFee());
  });

  it("does not require a Family Card fee when the family already has a card", () => {
    const familyMember = charge({
      canCreateCharge: false,
      cardAlreadyRegistered: true,
      familyCardIssued: true,
      hasCharge: false,
    });
    assert.equal(shouldOfferCardFee(familyMember), false);
    assert.equal(shouldShowCardFeeCard(familyMember), false);
  });

  it("does not require a card-creation fee for a returning patient", () => {
    const returning = charge({
      canCreateCharge: false,
      cardAlreadyRegistered: true,
      hasCharge: true,
      visit: {
        uuid: "visit-a",
        startDatetime: "2026-09-02T09:00:00.000+0000",
        open: true,
        visitType: "OPD",
        location: "OPD-1",
      },
    });
    assert.equal(shouldOfferCardFee(returning), false);
    assert.equal(shouldShowCardFeeCard(returning), false);
  });

  it("keeps an unpaid new-card bill visible so Reception can send the patient to Accountant", () => {
    const billed = charge({
      canCreateCharge: false,
      cardAlreadyRegistered: false,
      hasCharge: true,
    });
    assert.equal(shouldOfferCardFee(billed), false);
    assert.equal(shouldShowCardFeeCard(billed), true);
  });
});

describe("close outpatient visit", () => {
  it("lets Reception close an open OPD visit that belongs to this patient", () => {
    assert.equal(
      canCloseOutpatientVisit({
        visit: { uuid: "visit-a", visitType: "OPD", open: true },
        admissionActive: false,
        patientUuid: "patient-a",
        visitPatientUuid: "patient-a",
      }),
      true,
    );
    assert.equal(CLOSE_VISIT_LABEL, "Close Visit");
    assert.equal(CLOSING_VISIT_LABEL, "Closing visit...");
    assert.match(CLOSE_VISIT_CONFIRM_COPY, /Clinical records already recorded/);
    assert.equal(VISIT_CLOSED_SUCCESS_MESSAGE, "Visit closed successfully.");
  });

  it("does not offer Close Visit for IPD, a closed visit, or another patient", () => {
    assert.equal(
      canCloseOutpatientVisit({
        visit: { uuid: "ipd-a", visitType: "IPD", open: true },
        admissionActive: false,
      }),
      false,
    );
    assert.equal(
      canCloseOutpatientVisit({
        visit: { uuid: "visit-a", visitType: "OPD", open: true },
        admissionActive: true,
      }),
      false,
    );
    assert.equal(
      canCloseOutpatientVisit({
        visit: { uuid: "visit-a", visitType: "OPD", open: false },
        admissionActive: false,
      }),
      false,
    );
    assert.equal(
      canCloseOutpatientVisit({
        visit: { uuid: "visit-a", visitType: "OPD", open: true },
        admissionActive: false,
        patientUuid: "patient-a",
        visitPatientUuid: "patient-b",
      }),
      false,
    );
  });

  it("distinguishes awaiting consultation, attended, and closed from the visit record", () => {
    assert.deepEqual(outpatientVisitStatus({ open: true, attendedBy: "" }), {
      kind: "awaiting",
      badge: "Active — Awaiting consultation",
      label: "Active — Awaiting consultation",
    });
    assert.deepEqual(outpatientVisitStatus({ open: true, attendedBy: "Clinical Doctor" }), {
      kind: "attended",
      badge: "Active — Attended",
      label: "Active — Attended by Dr. Clinical Doctor",
    });
    assert.deepEqual(outpatientVisitStatus({ open: false, stop: "10:00", attendedBy: "Clinical Doctor" }), {
      kind: "closed",
      badge: "Closed",
      label: "Closed",
    });
  });

  it("lets a later visit start after the previous OPD visit is closed", () => {
    assert.equal(shouldOfferStartVisit({ openVisit: null, admissionActive: false }), true);
    assert.equal(
      shouldOfferStartVisit({ openVisit: { uuid: "still-open" }, admissionActive: false }),
      false,
    );
  });
});

describe("start visit response", () => {
  it("treats a structured open-visit reject as continue, not a generic error", () => {
    assert.equal(isExistingVisitCode(VISIT_ALREADY_OPEN_CODE), true);
    const result = readStartVisitResult(
      started({
        status: "existing",
        created: false,
        code: VISIT_ALREADY_OPEN_CODE,
        message: VISIT_ALREADY_OPEN_MESSAGE,
      }),
    );
    assert.equal(result.kind, "existing");
    assert.equal(result.message, VISIT_ALREADY_OPEN_MESSAGE);
    assert.equal(result.visit.uuid, "visit-a");
  });

  it("keeps future-dated open visits as existing open visits", () => {
    const result = readStartVisitResult(
      started({
        status: "existing",
        created: false,
        code: VISIT_ALREADY_OPEN_CODE,
        startDatetime: "2026-09-03T08:00:00.000+0000",
        message: VISIT_ALREADY_OPEN_MESSAGE,
      }),
    );
    assert.equal(result.kind, "existing");
    assert.equal(result.visit.startDatetime, "2026-09-03T08:00:00.000+0000");
  });

  it("returns the admission visit instead of creating an OPD visit", () => {
    const result = readStartVisitResult(
      started({
        status: "existing",
        created: false,
        code: ADMISSION_IN_PROGRESS_CODE,
        visitType: "IPD",
        visitTypeLabel: "Admission",
        uuid: "ipd-visit",
        message: ADMISSION_IN_PROGRESS_MESSAGE,
      }),
    );
    assert.equal(result.kind, "existing");
    assert.equal(result.visit.uuid, "ipd-visit");
    assert.equal(result.message, ADMISSION_IN_PROGRESS_MESSAGE);
  });

  it("still reports a newly created visit for a returning patient with no open visit", () => {
    const result = readStartVisitResult(started());
    assert.equal(result.kind, "created");
    assert.equal(result.message, "Visit successfully created.");
  });
});
