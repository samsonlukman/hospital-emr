import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { findRadiologyService, HISTORICAL_ORD_6 } from "../../config/radiologyMenu.ts";
import {
  bindRadiologyOrderVisit,
  canSubmitRadiologyOrder,
  historicalOrd6Unchanged,
  radiologyBillingStatus,
  radiologyOrderPayload,
  radiologyOrdersForSelectedVisit,
} from "./radiologyOrder.ts";

const VISIT_001 = "2857db49-c8fa-46d0-be38-2213f4cc54bc";
const VISIT_002 = "a70cbb56-88f2-43bd-afa8-463e61c220e7";
const PATIENT = "f242364e-b70f-4fec-b29e-8ad4fbe147b5";

describe("radiology selected visit", () => {
  it("requires the selected visitUuid and does not fall back to another visit", () => {
    assert.equal(bindRadiologyOrderVisit({ selectedVisitUuid: "", patientUuid: PATIENT }).status, "no-selection");
    const bound = bindRadiologyOrderVisit({ selectedVisitUuid: VISIT_001, patientUuid: PATIENT });
    assert.equal(bound.status, "selected");
    if (bound.status === "selected") {
      assert.equal(bound.visitUuid, VISIT_001);
    }
    const mismatch = bindRadiologyOrderVisit({
      selectedVisitUuid: VISIT_001,
      patientUuid: PATIENT,
      visitPatientUuid: "someone-else",
    });
    assert.equal(mismatch.status, "mismatch");
  });

  it("keeps only orders that belong to the selected visit", () => {
    const rows = [
      { uuid: "a", visitUuid: VISIT_001 },
      { uuid: "b", visitUuid: VISIT_002 },
      { uuid: "c" },
    ];
    assert.deepEqual(
      radiologyOrdersForSelectedVisit(rows, VISIT_001).map((row) => row.uuid),
      ["a"],
    );
    assert.deepEqual(radiologyOrdersForSelectedVisit(rows, null), []);
    assert.deepEqual(radiologyOrdersForSelectedVisit(rows, ""), []);
  });

  it("builds an OpenMRS Radiology order for an orderable hospital service on the selected visit", () => {
    const payload = radiologyOrderPayload({
      selectedVisitUuid: VISIT_001,
      patientUuid: PATIENT,
      serviceId: "us-obstetrics",
    });
    assert.ok(payload);
    assert.equal(payload?.visitUuid, VISIT_001);
    assert.equal(payload?.conceptUuid, "159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.equal(payload?.hospitalName, "Obstetrics (Pregnancy)");
    assert.equal("price" in (payload || {}), false);
    assert.equal(
      canSubmitRadiologyOrder({
        selectedVisitUuid: VISIT_001,
        service: findRadiologyService("us-obstetrics"),
      }),
      true,
    );
    const newlyEnabled = radiologyOrderPayload({
      selectedVisitUuid: VISIT_001,
      patientUuid: PATIENT,
      serviceId: "us-abdominopelvic",
    });
    assert.equal(newlyEnabled?.visitUuid, VISIT_001);
    assert.equal(newlyEnabled?.conceptUuid, "32f23df0-927d-4fd7-b446-d92ed6dff831");
    assert.equal(newlyEnabled?.hospitalName, "Abdominopelvic");
    assert.equal(
      radiologyOrderPayload({
        selectedVisitUuid: "",
        patientUuid: PATIENT,
        serviceId: "us-obstetrics",
      }),
      null,
    );
    assert.equal(
      radiologyOrderPayload({
        selectedVisitUuid: VISIT_001,
        patientUuid: PATIENT,
        serviceId: "unknown-service",
      }),
      null,
    );
  });

  it("requires laterality before ordering Knee Joint and keeps the selected visit", () => {
    assert.equal(
      canSubmitRadiologyOrder({
        selectedVisitUuid: VISIT_001,
        service: findRadiologyService("xr-knee"),
      }),
      false,
    );
    assert.equal(
      radiologyOrderPayload({
        selectedVisitUuid: VISIT_001,
        patientUuid: PATIENT,
        serviceId: "xr-knee",
      }),
      null,
    );
    const knee = radiologyOrderPayload({
      selectedVisitUuid: VISIT_001,
      patientUuid: PATIENT,
      serviceId: "xr-knee",
      optionId: "right",
    });
    assert.equal(knee?.visitUuid, VISIT_001);
    assert.equal(knee?.conceptUuid, "161349AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.equal(knee?.hospitalName, "Knee Joint — Right");
    assert.equal("price" in (knee || {}), false);
  });

  it("does not invent a billed visit or reuse ORD-6 as the next order", () => {
    const first = radiologyOrderPayload({
      selectedVisitUuid: VISIT_001,
      patientUuid: PATIENT,
      serviceId: "xr-chest",
    });
    const second = radiologyOrderPayload({
      selectedVisitUuid: VISIT_002,
      patientUuid: PATIENT,
      serviceId: "xr-chest",
    });
    assert.notEqual(first?.visitUuid, second?.visitUuid);
    assert.notEqual(first?.visitUuid, HISTORICAL_ORD_6.orderUuid);
    assert.equal(historicalOrd6Unchanged().orderNumber, "ORD-6");
    assert.equal(historicalOrd6Unchanged().amountUsd, 60);
  });
});

describe("protected development TEST orders", () => {
  it("keeps ORD-16/17/18/19 identities unchanged", () => {
    assert.equal(historicalOrd6Unchanged().orderNumber, "ORD-6");
    assert.equal(historicalOrd6Unchanged().orderUuid, "46e6031f-1fa9-4c48-a510-d32666cbc2ce");
    assert.equal(findRadiologyService("us-msk")?.hospitalName, "Musculoskeletal");
    assert.equal(findRadiologyService("xr-skull")?.hospitalName, "Skull X-ray");
    assert.equal(findRadiologyService("us-pelvic")?.hospitalName, "Pelvic");
    assert.equal(findRadiologyService("xr-lumbosacral")?.hospitalName, "Lumbosacral Spine");
  });
});

describe("radiology billing status", () => {
  it("distinguishes price pending, unpaid, and paid from Odoo charge data", () => {
    assert.equal(radiologyBillingStatus({}), "Price pending");
    assert.equal(radiologyBillingStatus({ hasCharge: false }), "Price pending");
    assert.equal(radiologyBillingStatus({ hasCharge: true, paymentStatus: "UNPAID" }), "Unpaid");
    assert.equal(radiologyBillingStatus({ hasCharge: true, paymentStatus: "PAID" }), "Paid");
    assert.equal(
      radiologyBillingStatus({ hasCharge: true, paymentStatus: "PARTIALLY PAID" }),
      "Partially paid",
    );
  });
});
