import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { clockOrDash, formatLogClock, formatLogClockShort, shiftIsoDate } from "./adminStaffLogView.ts";

const NAV = readFileSync(fileURLToPath(new URL("../../config/adminNav.ts", import.meta.url)), "utf8");
const ROUTER = readFileSync(fileURLToPath(new URL("../../app/WorkspaceRouter.tsx", import.meta.url)), "utf8");
const HASH = readFileSync(fileURLToPath(new URL("../../app/hashRoute.ts", import.meta.url)), "utf8");
const APP = readFileSync(fileURLToPath(new URL("../../App.tsx", import.meta.url)), "utf8");
const TERMINAL = readFileSync(
  fileURLToPath(new URL("../StaffLog/StaffLogTerminal.tsx", import.meta.url)),
  "utf8",
);

describe("Admin staff log", () => {
  it("formats hospital clock times without using integration words", () => {
    assert.equal(formatLogClock("08:04:32"), "8:04:32 AM");
    assert.equal(formatLogClock("12:04:18"), "12:04:18 PM");
    assert.equal(formatLogClockShort("17:12:00"), "5:12 PM");
    assert.equal(clockOrDash(""), "—");
    assert.equal(clockOrDash("08:02:00"), "8:02 AM");
  });

  it("moves one calendar day at a time", () => {
    assert.equal(shiftIsoDate("2026-09-18", -1), "2026-09-17");
    assert.equal(shiftIsoDate("2026-09-18", 1), "2026-09-19");
  });

  it("keeps Log in Administration and the public terminal off the dashboard", () => {
    assert.match(NAV, /label: "Log"/);
    assert.match(NAV, /#\/admin\/log/);
    assert.match(HASH, /admin-log/);
    assert.match(ROUTER, /AdminStaffLogWorkspace/);
    assert.match(APP, /StaffLogTerminal/);
    assert.match(APP, /isAttendanceTerminalLocation/);
    assert.doesNotMatch(NAV, /Attendance/);
    assert.doesNotMatch(NAV, /OpenMRS/);
    assert.doesNotMatch(NAV, /UUID/);
  });

  it("looks up the staff code before showing sign in or sign out", () => {
    assert.match(TERMINAL, /Staff Code/);
    assert.match(TERMINAL, /Continue/);
    assert.match(TERMINAL, /lookupStaffAttendance/);
    assert.match(TERMINAL, /Look at the camera/);
    assert.match(TERMINAL, /getUserMedia/);
    assert.match(TERMINAL, /Sign in/);
    assert.match(TERMINAL, /Sign out/);
    assert.doesNotMatch(TERMINAL, /Fingerprint/);
    assert.doesNotMatch(TERMINAL, /WebAuthn/);
    assert.doesNotMatch(TERMINAL, /biometric/i);
  });
});
