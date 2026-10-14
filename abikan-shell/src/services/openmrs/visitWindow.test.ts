import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { HOSPITAL_TIMEZONE, parseOpenmrsDateTime } from "../../utils/datetime.ts";
import {
  consultationSaveBlockedByVisitWindow,
  VISIT_NOT_STARTED_MESSAGE,
  visitHasStarted,
} from "./visitWindow.ts";

/** Ibrahim's seeded OPD visit: 08:40 Africa/Lagos. */
const IBRAHIM_START_OPENMRS = "2026-08-19T07:40:00.000+0000";
const IBRAHIM_START_LAGOS = "2026-08-19T08:40:00+01:00";

function lagosNow(isoLocal: string): number {
  const ms = Date.parse(`${isoLocal}+01:00`);
  assert.ok(!Number.isNaN(ms), `invalid Lagos test time ${isoLocal}`);
  return ms;
}

function lagosClock(value: string | number | Date): string {
  const date = parseOpenmrsDateTime(value);
  assert.ok(date);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: HOSPITAL_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

describe("parseOpenmrsDateTime", () => {
  it("reads the OpenMRS +0000 offset used on this installation", () => {
    const parsed = parseOpenmrsDateTime(IBRAHIM_START_OPENMRS);
    assert.ok(parsed);
    assert.equal(parsed.getTime(), Date.parse(IBRAHIM_START_LAGOS));
  });

  it("treats Africa/Lagos 08:40 as the same instant as 07:40 UTC", () => {
    assert.equal(lagosClock(IBRAHIM_START_OPENMRS), "08:40");
    assert.equal(lagosClock("2026-08-19T07:40:00.000+00:00"), "08:40");
    assert.equal(lagosClock(IBRAHIM_START_LAGOS), "08:40");
  });

  it("keeps Africa/Lagos at UTC+1 in January (no daylight saving)", () => {
    const januaryUtc = parseOpenmrsDateTime("2026-01-15T07:40:00.000+0000");
    assert.ok(januaryUtc);
    assert.equal(lagosClock(januaryUtc), "08:40");
    assert.equal(januaryUtc.getTime(), Date.parse("2026-01-15T08:40:00+01:00"));
  });
});

describe("visitHasStarted", () => {
  it("blocks save when now is before visit start (Ibrahim ~03:00 Lagos)", () => {
    const now = lagosNow("2026-08-19T03:00:00");
    assert.equal(visitHasStarted(IBRAHIM_START_OPENMRS, now), false);
    assert.equal(consultationSaveBlockedByVisitWindow(IBRAHIM_START_OPENMRS, now), true);
  });

  it("blocks save one second before the Africa/Lagos visit start", () => {
    const now = lagosNow("2026-08-19T08:39:59");
    assert.equal(visitHasStarted(IBRAHIM_START_OPENMRS, now), false);
  });

  it("allows save at the Africa/Lagos visit start", () => {
    const now = lagosNow("2026-08-19T08:40:00");
    assert.equal(visitHasStarted(IBRAHIM_START_OPENMRS, now), true);
    assert.equal(consultationSaveBlockedByVisitWindow(IBRAHIM_START_OPENMRS, now), false);
  });

  it("allows save after the visit has started", () => {
    const now = lagosNow("2026-08-19T09:15:00");
    assert.equal(visitHasStarted(IBRAHIM_START_OPENMRS, now), true);
  });

  it("does not treat payment state as an input — only visit start vs now", () => {
    const unpaidStarted = "2026-08-17T02:09:08.000+0000";
    const paidNotStarted = IBRAHIM_START_OPENMRS;
    const threeAmLagos = lagosNow("2026-08-19T03:00:00");
    assert.equal(visitHasStarted(unpaidStarted, threeAmLagos), true);
    assert.equal(visitHasStarted(paidNotStarted, threeAmLagos), false);
  });

  it("does not invent or clamp a timestamp — it only answers yes or no", () => {
    const now = lagosNow("2026-08-19T03:00:00");
    assert.equal(visitHasStarted(IBRAHIM_START_OPENMRS, now), false);
    assert.equal(parseOpenmrsDateTime(IBRAHIM_START_OPENMRS)?.toISOString(), "2026-08-19T07:40:00.000Z");
  });
});

describe("VISIT_NOT_STARTED_MESSAGE", () => {
  it("is the hospital-facing sentence, with no system jargon", () => {
    assert.equal(
      VISIT_NOT_STARTED_MESSAGE,
      "Visit has not started yet. Please wait until the visit starts before saving.",
    );
  });
});
