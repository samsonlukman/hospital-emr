import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { RADIOLOGY_NAV } from "../../config/radiologyNav.ts";
import {
  RADIOLOGY_CANCELLATION_CLASS,
  RADIOLOGY_CANCELLATION_DELETES_REPORTS,
  RADIOLOGY_CANCELLATION_UPDATES_ODOO,
  RADIOLOGY_MAY_DISCONTINUE_ORDERS,
  RADIOLOGY_MAY_VOID_ORDERS,
  RADIOLOGY_ORDER_WRITE_PRIVILEGE_REQUIRED,
  RADIOLOGY_SHOULD_RECEIVE_ORDER_WRITE_PRIVILEGE,
  RADIOLOGY_SHOWS_CANCEL_BUTTON,
  RADIOLOGY_SHOWS_DELETE_BUTTON,
  radiologyCanDeleteOrdersFromUi,
  radiologyCancellationIsSafeToExpose,
  radiologyProtectedCancellationTargets,
} from "./radiologyCancellation.ts";

describe("radiology order cancellation", () => {
  it("does not show Delete or Cancel on Radiology screens", () => {
    assert.equal(RADIOLOGY_SHOWS_DELETE_BUTTON, false);
    assert.equal(RADIOLOGY_SHOWS_CANCEL_BUTTON, false);
    assert.equal(radiologyCanDeleteOrdersFromUi(), false);
    const labels = RADIOLOGY_NAV.flatMap((group) => group.items).map((item) => item.label);
    assert.equal(labels.some((label) => /delete|cancel/i.test(label)), false);
  });

  it("classifies cancellation as a privileged OpenMRS/Bahmni workflow, not Radiology", () => {
    assert.equal(RADIOLOGY_CANCELLATION_CLASS, "C");
    assert.equal(RADIOLOGY_MAY_VOID_ORDERS, false);
    assert.equal(RADIOLOGY_MAY_DISCONTINUE_ORDERS, false);
    assert.equal(RADIOLOGY_ORDER_WRITE_PRIVILEGE_REQUIRED, "Edit Orders");
    assert.equal(RADIOLOGY_SHOULD_RECEIVE_ORDER_WRITE_PRIVILEGE, false);
    assert.equal(radiologyCancellationIsSafeToExpose(), false);
  });

  it("does not assume Odoo refunds or report deletion", () => {
    assert.equal(RADIOLOGY_CANCELLATION_UPDATES_ODOO, false);
    assert.equal(RADIOLOGY_CANCELLATION_DELETES_REPORTS, false);
  });

  it("does not target protected TEST orders or invoices", () => {
    const protectedTargets = radiologyProtectedCancellationTargets();
    assert.deepEqual(protectedTargets.orders, [
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
    assert.deepEqual(protectedTargets.invoices, [
      "INV/2026/00006",
      "INV/2026/00031",
      "INV/2026/00032",
      "INV/2026/00033",
      "INV/2026/00034",
      "INV/2026/00035",
    ]);
  });
});
