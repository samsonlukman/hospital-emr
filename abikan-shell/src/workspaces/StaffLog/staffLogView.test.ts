import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isAttendanceTerminalLocation } from "./staffLogView.ts";

describe("Staff log terminal location", () => {
  it("opens the dedicated /abikan/log terminal", () => {
    assert.equal(isAttendanceTerminalLocation("/abikan/log", ""), true);
    assert.equal(isAttendanceTerminalLocation("/abikan/log/", "#/home"), true);
    assert.equal(isAttendanceTerminalLocation("/log", ""), true);
    assert.equal(isAttendanceTerminalLocation("/abikan/", "#/log"), true);
  });

  it("does not treat Admin Log as the public terminal", () => {
    assert.equal(isAttendanceTerminalLocation("/abikan/", "#/admin/log"), false);
    assert.equal(isAttendanceTerminalLocation("/abikan/", "#/home"), false);
    assert.equal(isAttendanceTerminalLocation("/abikan/staff-accounts", ""), false);
  });
});
