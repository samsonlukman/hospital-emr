import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  addCreateTestColumn,
  addCreateTestRow,
  createTestDraftError,
  emptyCreateTestDraft,
  removeCreateTestColumn,
  removeCreateTestRow,
  serializeCreateTestDraft,
} from "./laboratoryCreateTest.ts";

describe("laboratory create test draft", () => {
  it("starts with one Name row and one result column", () => {
    const draft = emptyCreateTestDraft();
    assert.equal(draft.columns.length, 1);
    assert.equal(draft.rows.length, 1);
    assert.equal(draft.rows[0]?.values[draft.columns[0]!.key], "");
  });

  it("adds infinite columns and keeps row value maps aligned", () => {
    let draft = emptyCreateTestDraft();
    draft = addCreateTestColumn(draft);
    draft = addCreateTestColumn(draft);
    assert.equal(draft.columns.length, 3);
    for (const row of draft.rows) {
      assert.equal(Object.keys(row.values).length, 3);
    }
  });

  it("adds infinite property rows under the Name column", () => {
    let draft = emptyCreateTestDraft();
    draft = addCreateTestRow(draft);
    draft = addCreateTestRow(draft);
    assert.equal(draft.rows.length, 3);
  });

  it("will not remove the last column or last row", () => {
    const draft = emptyCreateTestDraft();
    assert.equal(removeCreateTestColumn(draft, draft.columns[0]!.key).columns.length, 1);
    assert.equal(removeCreateTestRow(draft, draft.rows[0]!.key).rows.length, 1);
  });

  it("requires test name, a named column, and a named property", () => {
    const draft = emptyCreateTestDraft();
    assert.equal(createTestDraftError(draft), "Enter a test name.");
    draft.testName = "Malaria smear+";
    assert.equal(createTestDraftError(draft), "Name at least one result column.");
    draft.columns[0]!.name = "Parasite density";
    assert.equal(createTestDraftError(draft), "Add at least one property name in the Name column.");
    draft.rows[0]!.name = "Unit";
    assert.equal(createTestDraftError(draft), "");
  });

  it("serializes columns and property rows for Hospital EMR save", () => {
    let draft = emptyCreateTestDraft();
    draft.testName = "Custom CBC";
    draft.price = "1,500";
    draft.columns[0]!.name = "WBC";
    draft = addCreateTestColumn(draft);
    draft.columns[1]!.name = "RBC";
    draft.rows[0]!.name = "Unit";
    draft.rows[0]!.values[draft.columns[0]!.key] = "10^9/L";
    draft.rows[0]!.values[draft.columns[1]!.key] = "10^12/L";
    const body = serializeCreateTestDraft(draft);
    assert.equal(body.name, "Custom CBC");
    assert.equal(body.price, 1500);
    assert.deepEqual(body.columns, ["WBC", "RBC"]);
    assert.deepEqual(body.properties, [{ name: "Unit", values: ["10^9/L", "10^12/L"] }]);
  });
});
