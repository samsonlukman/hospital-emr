import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { openLaboratoryWorklistOrder, readLaboratoryOrderExpectedIdentity } from "../../app/hashRoute.ts";
import { rejectMismatchedLaboratoryOrder } from "./laboratoryWorklist.ts";

const PATIENT = "f242364e-b70f-4fec-b29e-8ad4fbe147b5";
const VISIT = "6478a94e-1657-4abe-9271-7cf92b821576";
const ORDER = "c2421f0b-fa94-4ae8-a493-4f657ab7793d";

describe("laboratory worklist order identity", () => {
  it("preserves the exact orderUuid, patientUuid, and visitUuid", () => {
    const order = {
      uuid: "order-9",
      patientUuid: PATIENT,
      visitUuid: VISIT,
    };
    assert.equal(
      rejectMismatchedLaboratoryOrder({
        order,
        expectedPatientUuid: PATIENT,
        expectedVisitUuid: VISIT,
      }),
      "ok",
    );
  });

  it("rejects a mismatched patientUuid", () => {
    assert.equal(
      rejectMismatchedLaboratoryOrder({
        order: { uuid: "order-9", patientUuid: PATIENT, visitUuid: VISIT },
        expectedPatientUuid: "someone-else",
        expectedVisitUuid: VISIT,
      }),
      "mismatch",
    );
  });

  it("rejects a mismatched visitUuid", () => {
    assert.equal(
      rejectMismatchedLaboratoryOrder({
        order: { uuid: "order-9", patientUuid: PATIENT, visitUuid: VISIT },
        expectedPatientUuid: PATIENT,
        expectedVisitUuid: "other-visit",
      }),
      "mismatch",
    );
  });

  it("keeps duplicate same-test orders distinct by orderUuid", () => {
    const first = {
      uuid: "order-9",
      patientUuid: PATIENT,
      visitUuid: VISIT,
    };
    const second = {
      uuid: "order-10",
      patientUuid: PATIENT,
      visitUuid: VISIT,
    };
    assert.notEqual(first.uuid, second.uuid);
    assert.equal(
      rejectMismatchedLaboratoryOrder({
        order: first,
        expectedPatientUuid: PATIENT,
        expectedVisitUuid: VISIT,
      }),
      "ok",
    );
    assert.equal(
      rejectMismatchedLaboratoryOrder({
        order: second,
        expectedPatientUuid: PATIENT,
        expectedVisitUuid: VISIT,
      }),
      "ok",
    );
  });

  it("Action Open carries orderUuid, patientUuid, and visitUuid in the hash", () => {
    let hash = "";
    const prior = globalThis.window;
    globalThis.window = {
      location: {
        get hash() {
          return hash;
        },
        set hash(value: string) {
          hash = value;
        },
      },
    } as Window & typeof globalThis;
    try {
      openLaboratoryWorklistOrder({
        orderUuid: ORDER,
        patientUuid: PATIENT,
        visitUuid: VISIT,
      });
      assert.match(hash, new RegExp(`#/laboratory/order/${ORDER}\\?`));
      assert.match(hash, /patient=f242364e-b70f-4fec-b29e-8ad4fbe147b5/);
      assert.match(hash, /visit=6478a94e-1657-4abe-9271-7cf92b821576/);
      assert.deepEqual(readLaboratoryOrderExpectedIdentity(), {
        patientUuid: PATIENT,
        visitUuid: VISIT,
      });
    } finally {
      globalThis.window = prior;
    }
  });
});
