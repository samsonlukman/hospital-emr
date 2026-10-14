import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isOpenmrsOrderUuid,
  newDrugOrderUuidsFromList,
} from "./prescriptionAnnounce.ts";
import type { DrugOrderSummary } from "../../types";

function row(uuid: string, status: DrugOrderSummary["status"] = "Ordered"): DrugOrderSummary {
  return {
    uuid,
    display: uuid,
    drugName: uuid,
    dose: "1",
    route: "Oral",
    frequency: "Twice a day",
    duration: "5 Days",
    status,
  };
}

describe("prescription announce helpers", () => {
  it("accepts real OpenMRS order ids and rejects drug-name fallbacks", () => {
    assert.equal(isOpenmrsOrderUuid("654f9258-f4a2-48c8-b31c-34679778259b"), true);
    assert.equal(isOpenmrsOrderUuid("Paracetamol 500 mg"), false);
    assert.equal(isOpenmrsOrderUuid(""), false);
  });

  it("keeps only new UUID-shaped orders for pharmacy announce", () => {
    const prior = new Set(["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]);
    const created = newDrugOrderUuidsFromList(
      [
        row("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        row("Paracetamol 500 mg"),
        row("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        row("cccccccc-cccc-cccc-cccc-cccccccccccc", "Stopped"),
      ],
      prior,
    );
    assert.deepEqual(created, ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"]);
  });
});
