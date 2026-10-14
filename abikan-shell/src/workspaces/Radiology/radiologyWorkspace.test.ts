import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { RADIOLOGY_NAV } from "../../config/radiologyNav.ts";
import { radiologyBillingStatus } from "./radiologyOrder.ts";
import { RADIOLOGY_REPORT_PLACEHOLDER } from "./radiologyReport.ts";
import {
  NO_PRICE_SET,
  RADIOLOGY_HOME_HELP,
  RADIOLOGY_SAVE_PRICE,
  RADIOLOGY_SET_PRICE,
  radiologyDailyVisitNumber,
  radiologyLocationLabel,
  radiologyOrderIdentity,
  radiologyPaymentLabel,
  radiologyPaymentTone,
  radiologyShowsUnimplementedImagesUi,
  radiologyStaffFacingCopyHasImagesPlaceholder,
  radiologyStaffName,
  radiologyVisitLabel,
} from "./radiologyDesk.ts";
import {
  radiologyReportActionLabel,
  radiologyReportOpenLabel,
  radiologyReportStatusLabel,
} from "./radiologyReport.ts";
import { WORKLIST_TEST_ORDERS, worklistFixturesUnchanged } from "./radiologyWorklist.ts";

describe("Radiologist workspace UX", () => {
  it("keeps price actions precise and does not collect payment", () => {
    assert.equal(RADIOLOGY_SET_PRICE, "Set Price");
    assert.equal(RADIOLOGY_SAVE_PRICE, "Save Price");
    assert.match(RADIOLOGY_HOME_HELP, /do not collect payment/i);
    assert.equal(NO_PRICE_SET, "No price set.");
  });

  it("maps Odoo payment data to Price pending, Unpaid, or Paid", () => {
    assert.equal(radiologyPaymentLabel({}), "Price pending");
    assert.equal(radiologyPaymentLabel({ hasCharge: true, paymentStatus: "UNPAID" }), "Unpaid");
    assert.equal(
      radiologyPaymentLabel({ hasCharge: true, paymentStatus: "PARTIALLY PAID" }),
      "Partially paid",
    );
    assert.equal(radiologyPaymentLabel({ hasCharge: true, paymentStatus: "PAID" }), "Paid");
    assert.equal(radiologyBillingStatus({ hasCharge: true, paymentStatus: "UNKNOWN" }), "Unpaid");
  });

  it("labels visit number and type without using OPD-1 as the visit", () => {
    assert.equal(
      radiologyVisitLabel({ dailyVisitNumber: "001", visitType: "OPD" }),
      "Visit #001 · General Outpatient",
    );
    assert.equal(radiologyDailyVisitNumber("001"), "001");
    assert.equal(radiologyDailyVisitNumber(""), undefined);
    assert.equal(radiologyLocationLabel("OPD-1"), undefined);
    assert.equal(radiologyLocationLabel("Emergency"), "Emergency");
    assert.equal(radiologyPaymentTone("Paid"), "success");
    assert.equal(radiologyPaymentTone("Unpaid"), "warning");
    assert.equal(radiologyPaymentTone("Price pending"), "info");
  });

  it("hides login ids from ordered-by / reported-by", () => {
    assert.equal(radiologyStaffName("radiology.abikan"), "—");
    assert.equal(radiologyStaffName("doctor.abikan - Clinical Doctor"), "Clinical Doctor");
  });

  it("requires patient, visit, and order together and does not substitute another order", () => {
    assert.deepEqual(
      radiologyOrderIdentity({
        uuid: "a6e20ad8-7b64-49fc-9c87-8cb8a57d227d",
        patientUuid: "26b50a91-0e06-4153-b872-530a9c67a4c8",
        visitUuid: "0b99c191-5e6d-4784-8ecf-cb747cfccef3",
      }),
      {
        orderUuid: "a6e20ad8-7b64-49fc-9c87-8cb8a57d227d",
        patientUuid: "26b50a91-0e06-4153-b872-530a9c67a4c8",
        visitUuid: "0b99c191-5e6d-4784-8ecf-cb747cfccef3",
      },
    );
    assert.equal(
      radiologyOrderIdentity({
        uuid: "a6e20ad8-7b64-49fc-9c87-8cb8a57d227d",
        patientUuid: "26b50a91-0e06-4153-b872-530a9c67a4c8",
        visitUuid: "",
      }),
      null,
    );
  });

  it("keeps the report editor as empty free text", () => {
    assert.equal(RADIOLOGY_REPORT_PLACEHOLDER, "Enter the radiology findings and impression.");
  });

  it("removes unfinished Images UI and keeps reports, price, and payment", () => {
    assert.equal(radiologyShowsUnimplementedImagesUi(), false);
    assert.equal(radiologyStaffFacingCopyHasImagesPlaceholder(), false);
    assert.equal(
      RADIOLOGY_NAV.flatMap((group) => group.items).some((item) => /image/i.test(item.label)),
      false,
    );
    assert.equal(radiologyReportActionLabel(null), "Write Report");
    assert.equal(
      radiologyReportActionLabel({
        uuid: "note",
        value: "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY",
        observedAt: "",
        obsDatetime: "",
        encounterUuid: "",
        orderUuid: WORKLIST_TEST_ORDERS.ord16.orderUuid,
        patientUuid: WORKLIST_TEST_ORDERS.ord16.patientUuid,
        visitUuid: WORKLIST_TEST_ORDERS.ord16.visitUuid,
        reportedBy: "Radiology Staff",
      }),
      "Edit Report",
    );
    assert.equal(
      radiologyReportOpenLabel({
        uuid: "note",
        value: "TEST RADIOLOGY REPORT — DEVELOPMENT ONLY",
        observedAt: "",
        obsDatetime: "",
        encounterUuid: "",
        orderUuid: WORKLIST_TEST_ORDERS.ord19.orderUuid,
        patientUuid: WORKLIST_TEST_ORDERS.ord19.patientUuid,
        visitUuid: WORKLIST_TEST_ORDERS.ord19.visitUuid,
        reportedBy: "Radiology Staff",
      }),
      "View Report",
    );
    assert.equal(radiologyReportStatusLabel(null), "Report pending");
    assert.equal(radiologyPaymentLabel({}), "Price pending");
    const fixtures = worklistFixturesUnchanged();
    assert.equal(fixtures.ord6.orderNumber, "ORD-6");
    assert.equal(WORKLIST_TEST_ORDERS.ord16.hasReport, true);
    assert.equal(WORKLIST_TEST_ORDERS.ord19.hasReport, true);
  });

  it("makes the worklist the live radiology starting point", () => {
    const labels = RADIOLOGY_NAV[0]?.items.map((item) => item.label) ?? [];
    assert.deepEqual(labels, ["Radiology", "Worklist", "New Imaging Study", "Imaging History"]);
    const worklist = RADIOLOGY_NAV[0]?.items.find((item) => item.label === "Worklist");
    assert.equal(worklist?.kind, "route");
    assert.equal(worklist && "href" in worklist ? worklist.href : "", "#/radiology/worklist");
    assert.equal(
      RADIOLOGY_NAV[0]?.items.some((item) => item.kind === "soon"),
      false,
    );
  });
});
