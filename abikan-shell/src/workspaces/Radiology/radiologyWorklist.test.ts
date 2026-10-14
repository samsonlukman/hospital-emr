import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { RADIOLOGY_MENU } from "../../config/radiologyMenu.ts";
import { RADIOGRAPHY_GROUP, ULTRASOUND_GROUP } from "../../config/radiologyMenu.ts";
import type { RadiologyWorklistRow } from "../../types/radiologyBilling.ts";
import {
  allHospitalServicesCanAppearOnWorklist,
  canOpenWorklistRow,
  doctorCannotPriceFromWorklist,
  filterWorklistRows,
  isPendingRadiologyWork,
  matchesWorklistSearch,
  radiologistPricesFromWorklist,
  rejectMismatchedWorklistOrder,
  replaceWorklistRows,
  sortWorklistNewestFirst,
  worklistFixturesUnchanged,
  worklistHasNoCrossPatientLeak,
  worklistHasNoDuplicateOrders,
  worklistIncludesOrderRegardlessOfVisitAge,
  worklistRowIdentity,
  worklistRowsForPatient,
  worklistRowsForVisit,
  WORKLIST_TEST_ORDERS,
  WORKLIST_USES_VISIT_DATE_WINDOW,
} from "./radiologyWorklist.ts";
import { RADIOLOGY_WORKLIST_EMPTY, RADIOLOGY_WORKLIST_HELP } from "./radiologyDesk.ts";

const ABC16 = "f242364e-b70f-4fec-b29e-8ad4fbe147b5";
const ABC18 = "26b50a91-0e06-4153-b872-530a9c67a4c8";
const VISIT_001 = "2857db49-c8fa-46d0-be38-2213f4cc54bc";
const VISIT_002 = "a70cbb56-88f2-43bd-afa8-463e61c220e7";

function row(overrides: Partial<RadiologyWorklistRow> = {}): RadiologyWorklistRow {
  return {
    uuid: WORKLIST_TEST_ORDERS.ord17.orderUuid,
    orderNumber: "ORD-17",
    investigation: "Skull X-ray",
    conceptUuid: "386AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    category: RADIOGRAPHY_GROUP,
    patientUuid: ABC18,
    patientName: "Test Testing",
    mrn: "ABC200018",
    visitUuid: WORKLIST_TEST_ORDERS.ord17.visitUuid,
    encounterUuid: "encounter-17",
    visitType: "OPD",
    dailyVisitNumber: "",
    ordered: "2026-08-24T22:46:00.000+0000",
    urgency: "Routine",
    comment: "",
    provider: "Clinical Doctor",
    hasReport: false,
    reportStatus: "Report pending",
    hasCharge: false,
    paymentStatus: "UNPAID",
    billingStatus: "Price pending",
    ...overrides,
  };
}

const fixtures: RadiologyWorklistRow[] = [
  row(),
  row({
    uuid: WORKLIST_TEST_ORDERS.ord16.orderUuid,
    orderNumber: "ORD-16",
    investigation: "Musculoskeletal",
    category: ULTRASOUND_GROUP,
    visitUuid: WORKLIST_TEST_ORDERS.ord16.visitUuid,
    ordered: "2026-08-24T20:49:00.000+0000",
    hasReport: true,
    reportStatus: "Report available",
  }),
  row({
    uuid: WORKLIST_TEST_ORDERS.ord18.orderUuid,
    orderNumber: "ORD-18",
    investigation: "Pelvic",
    category: ULTRASOUND_GROUP,
    visitUuid: WORKLIST_TEST_ORDERS.ord18.visitUuid,
    ordered: "2026-08-24T22:46:30.000+0000",
    hasCharge: true,
    paymentStatus: "UNPAID",
    billingStatus: "Unpaid",
    feeFormatted: "₦11,111.00",
  }),
  row({
    uuid: WORKLIST_TEST_ORDERS.ord19.orderUuid,
    orderNumber: "ORD-19",
    investigation: "Lumbosacral Spine",
    patientUuid: ABC16,
    patientName: "ABIKAN E2E TEST PATIENT",
    mrn: "ABC200016",
    visitUuid: VISIT_001,
    ordered: "2026-08-24T22:46:40.000+0000",
    hasReport: true,
    reportStatus: "Report available",
    hasCharge: true,
    paymentStatus: "UNPAID",
    billingStatus: "Unpaid",
    feeFormatted: "₦12,222.00",
  }),
  row({
    uuid: "ord-15",
    orderNumber: "ORD-15",
    investigation: "Pelvic",
    category: ULTRASOUND_GROUP,
    patientUuid: ABC16,
    patientName: "ABIKAN E2E TEST PATIENT",
    mrn: "ABC200016",
    visitUuid: VISIT_002,
    ordered: "2026-08-24T02:24:00.000+0000",
    hasCharge: true,
    paymentStatus: "UNPAID",
    billingStatus: "Unpaid",
    feeFormatted: "₦2,500.00",
  }),
];

describe("radiology worklist", () => {
  it("loads pending work from missing Radiology Notes, not an invented status", () => {
    assert.equal(isPendingRadiologyWork(row()), true);
    assert.equal(isPendingRadiologyWork(row({ hasReport: true })), false);
    assert.equal(RADIOLOGY_WORKLIST_EMPTY, "No pending Radiology examinations.");
    assert.match(RADIOLOGY_WORKLIST_HELP, /do not yet have a Radiology Report/);
  });

  it("keeps exact patient, visit, and order identity and rejects substitution", () => {
    const identity = worklistRowIdentity(row());
    assert.deepEqual(identity, {
      orderUuid: WORKLIST_TEST_ORDERS.ord17.orderUuid,
      patientUuid: ABC18,
      visitUuid: WORKLIST_TEST_ORDERS.ord17.visitUuid,
    });
    assert.equal(canOpenWorklistRow(row({ visitUuid: "" })), false);
    assert.equal(
      canOpenWorklistRow(
        row({
          uuid: "radiology-ext:token:0",
          patientUuid: "",
          visitUuid: "",
          isExternal: true,
        }),
      ),
      true,
    );
    assert.equal(
      rejectMismatchedWorklistOrder({
        order: row(),
        expectedPatientUuid: ABC16,
        expectedVisitUuid: VISIT_001,
      }),
      "mismatch",
    );
    assert.equal(
      rejectMismatchedWorklistOrder({
        order: row(),
        expectedPatientUuid: ABC18,
        expectedVisitUuid: WORKLIST_TEST_ORDERS.ord17.visitUuid,
      }),
      "ok",
    );
  });

  it("keeps ORD-16 and ORD-17 independent on the same visit", () => {
    const sameVisit = worklistRowsForVisit(fixtures, WORKLIST_TEST_ORDERS.ord16.visitUuid);
    assert.deepEqual(
      sameVisit.map((item) => item.orderNumber).sort(),
      ["ORD-16", "ORD-17"],
    );
    const skull = sameVisit.find((item) => item.orderNumber === "ORD-17");
    const msk = sameVisit.find((item) => item.orderNumber === "ORD-16");
    assert.equal(skull?.investigation, "Skull X-ray");
    assert.equal(skull?.hasReport, false);
    assert.equal(msk?.investigation, "Musculoskeletal");
    assert.equal(msk?.hasReport, true);
    assert.notEqual(skull?.uuid, msk?.uuid);
  });

  it("keeps Visit #001 and Visit #002 distinct on the same patient", () => {
    const visit001 = worklistRowsForVisit(fixtures, VISIT_001);
    const visit002 = worklistRowsForVisit(fixtures, VISIT_002);
    assert.equal(visit001.every((item) => item.investigation === "Lumbosacral Spine"), true);
    assert.equal(visit002.every((item) => item.investigation === "Pelvic"), true);
    assert.equal(
      visit001.some((item) => item.visitUuid === VISIT_002),
      false,
    );
  });

  it("clears the other patient's orders when switching patients", () => {
    const previous = worklistRowsForPatient(fixtures, ABC18);
    assert.equal(
      previous.some((item) => item.uuid === WORKLIST_TEST_ORDERS.ord16.orderUuid),
      true,
    );
    const next = replaceWorklistRows(previous, worklistRowsForPatient(fixtures, ABC16));
    assert.equal(
      worklistHasNoCrossPatientLeak(next, ABC16, WORKLIST_TEST_ORDERS.ord16.orderUuid),
      true,
    );
    assert.equal(
      next.some((item) => item.uuid === WORKLIST_TEST_ORDERS.ord19.orderUuid),
      true,
    );
    const back = replaceWorklistRows(next, worklistRowsForPatient(fixtures, ABC18));
    assert.equal(
      back.some((item) => item.uuid === WORKLIST_TEST_ORDERS.ord16.orderUuid),
      true,
    );
    assert.equal(
      worklistHasNoCrossPatientLeak(back, ABC18, WORKLIST_TEST_ORDERS.ord19.orderUuid),
      true,
    );
  });

  it("filters pending, reported, examination, and search without leaking visits", () => {
    assert.deepEqual(
      filterWorklistRows(fixtures, { view: "pending" }).map((item) => item.orderNumber),
      ["ORD-18", "ORD-17", "ORD-15"],
    );
    assert.equal(
      filterWorklistRows(fixtures, { view: "reported" }).every((item) => item.hasReport),
      true,
    );
    assert.equal(
      filterWorklistRows(fixtures, { category: ULTRASOUND_GROUP, view: "all" }).every(
        (item) => item.category === ULTRASOUND_GROUP,
      ),
      true,
    );
    assert.equal(matchesWorklistSearch(row(), "ABC200018"), true);
    assert.equal(matchesWorklistSearch(row(), "Skull"), true);
    assert.equal(matchesWorklistSearch(row(), "ABC200016"), false);
    const newest = sortWorklistNewestFirst(fixtures);
    assert.equal(newest[0]?.orderNumber, "ORD-19");
  });

  it("lets all 42 hospital services appear and keeps pricing responsibility", () => {
    assert.equal(RADIOLOGY_MENU.length, 42);
    assert.equal(allHospitalServicesCanAppearOnWorklist(), true);
    assert.equal(doctorCannotPriceFromWorklist(), true);
    assert.equal(radiologistPricesFromWorklist(), true);
  });

  it("keeps old and recent pending orders and does not use a 30-day visit window", () => {
    const oldPending = row({
      uuid: WORKLIST_TEST_ORDERS.ord17.orderUuid,
      orderNumber: "ORD-17",
      ordered: "2026-06-01T08:00:00.000+0000",
      hasReport: false,
      reportStatus: "Report pending",
    });
    const recentPending = row({
      uuid: "recent-pending",
      orderNumber: "ORD-25",
      ordered: "2026-08-24T23:42:03.000+0000",
      hasReport: false,
      reportStatus: "Report pending",
    });
    const reported = row({
      uuid: WORKLIST_TEST_ORDERS.ord16.orderUuid,
      orderNumber: "ORD-16",
      ordered: "2026-08-24T20:49:17.000+0000",
      hasReport: true,
      reportStatus: "Report available",
    });
    const listed = filterWorklistRows([oldPending, recentPending, reported], { view: "all" });
    assert.equal(WORKLIST_USES_VISIT_DATE_WINDOW, false);
    assert.equal(worklistIncludesOrderRegardlessOfVisitAge(), true);
    assert.equal(listed.some((item) => item.orderNumber === "ORD-17" && !item.hasReport), true);
    assert.equal(listed.some((item) => item.orderNumber === "ORD-25" && !item.hasReport), true);
    assert.equal(listed.some((item) => item.orderNumber === "ORD-16" && item.hasReport), true);
    assert.equal(worklistHasNoDuplicateOrders(listed), true);
    assert.deepEqual(worklistRowIdentity(oldPending), {
      orderUuid: WORKLIST_TEST_ORDERS.ord17.orderUuid,
      patientUuid: ABC18,
      visitUuid: WORKLIST_TEST_ORDERS.ord17.visitUuid,
    });
  });

  it("leaves existing TEST orders and invoices unchanged", () => {
    const fixturesProtected = worklistFixturesUnchanged();
    assert.deepEqual(fixturesProtected.orders, [
      "ORD-6",
      "ORD-14",
      "ORD-15",
      "ORD-16",
      "ORD-17",
      "ORD-18",
      "ORD-19",
      "ORD-20",
      "ORD-21",
    ]);
    assert.equal(fixturesProtected.invoices.includes("INV/2026/00035"), true);
    assert.equal(fixturesProtected.ord6.orderNumber, "ORD-6");
    assert.equal(fixturesProtected.ord6.amountUsd, 60);
  });
});
