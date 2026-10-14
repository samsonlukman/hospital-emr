import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import type { AdminAnalyticsOverview, AdminMetric, AdminStaffAuditEvent } from "../../types/administration.ts";
import {
  auditChangeSummary,
  auditOutcomeLabel,
  customRangeValid,
  emptyOverview,
  formatMetricCount,
  formatMetricMoney,
  occupancyHeadline,
  occupancyHint,
  occupancyRateLabel,
  outstandingHint,
  overviewCards,
  periodQuery,
} from "./adminAnalytics.ts";

const CSS = readFileSync(fileURLToPath(new URL("./AdminWorkspace.css", import.meta.url)), "utf8");
const ANALYTICS_SOURCE = readFileSync(
  fileURLToPath(new URL("./AdminAnalyticsWorkspace.tsx", import.meta.url)),
  "utf8",
);
const AUDIT_SOURCE = readFileSync(
  fileURLToPath(new URL("./AdminAuditWorkspace.tsx", import.meta.url)),
  "utf8",
);

function metric(overrides: Partial<AdminMetric> = {}): AdminMetric {
  return { status: "ok", value: 0, ...overrides };
}

function overviewFrom(empty: AdminAnalyticsOverview, patch: Partial<AdminAnalyticsOverview>): AdminAnalyticsOverview {
  return { ...empty, ...patch };
}

describe("Admin analytics cards", () => {
  it("renders zero values instead of blank, null, or NaN", () => {
    const cards = overviewCards(emptyOverview("Today"));
    for (const card of cards) {
      assert.notEqual(card.value, "undefined");
      assert.notEqual(card.value, "null");
      assert.notEqual(card.value, "NaN");
      assert.notEqual(card.value, "");
    }
    assert.equal(formatMetricCount(metric({ value: 0 })), "0");
    assert.equal(formatMetricMoney(metric({ value: 0, amount: 0, formatted: "₦0.00" })), "₦0.00");
    assert.equal(occupancyHeadline(metric({ occupied: 0, total: 0, label: "0 / 0" })), "0 / 0");
  });

  it("shows ₦0.00 for an empty day and Unavailable only when finance failed", () => {
    const empty = overviewCards(
      overviewFrom(emptyOverview("Today"), {
        billed: { status: "ok", value: 0, amount: 0, formatted: "₦0.00" },
        collected: { status: "ok", value: 0, amount: 0, formatted: "₦0.00" },
        outstanding: { status: "ok", value: 0, amount: 0, formatted: "₦0.00", asOf: "current" },
      }),
    );
    assert.equal(empty.find((card) => card.id === "billed")?.value, "₦0.00");
    assert.equal(empty.find((card) => card.id === "collected")?.value, "₦0.00");
    assert.equal(empty.find((card) => card.id === "outstanding")?.value, "₦0.00");
    const failed = overviewCards(
      overviewFrom(emptyOverview("Today"), {
        billed: { status: "unavailable", value: null, message: "Finance totals are temporarily unavailable." },
        collected: { status: "unavailable", value: null, message: "Finance totals are temporarily unavailable." },
        outstanding: { status: "unavailable", value: null, asOf: "current", message: "Finance totals are temporarily unavailable." },
      }),
    );
    assert.equal(failed.find((card) => card.id === "billed")?.value, "Unavailable");
    assert.equal(failed.find((card) => card.id === "collected")?.value, "Unavailable");
    assert.notEqual(failed.find((card) => card.id === "billed")?.value, "₦0.00");
  });

  it("distinguishes unavailable metrics from zero", () => {
    const unavailable = metric({ status: "unavailable", value: null, message: "Hospital records are temporarily unavailable." });
    assert.equal(formatMetricCount(unavailable), "Unavailable");
    assert.equal(formatMetricMoney(unavailable), "Unavailable");
    assert.equal(occupancyHeadline(unavailable), "Unavailable");
    assert.equal(occupancyRateLabel(unavailable), "Unavailable");
    assert.notEqual(formatMetricCount(unavailable), "0");
  });

  it("keeps occupancy as a current snapshot, not a historical period total", () => {
    const occupancy = metric({
      occupied: 12,
      total: 27,
      rate: 12 / 27,
      asOf: "current",
      label: "12 / 27",
    });
    const cards = overviewCards(
      overviewFrom(emptyOverview("This month"), { occupancy }),
    );
    const bedCard = cards.find((card) => card.id === "occupancy");
    const rateCard = cards.find((card) => card.id === "occupancyRate");
    assert.equal(bedCard?.value, "12 / 27");
    assert.equal(bedCard?.snapshot, true);
    assert.match(bedCard?.hint || "", /now/i);
    assert.equal(occupancyRateLabel(occupancy), "44.4%");
    assert.equal(rateCard?.snapshot, true);
    assert.doesNotMatch(bedCard?.label || "", /August occupancy/i);
  });

  it("labels billed, collected, and outstanding without calling billed revenue", () => {
    const cards = overviewCards(emptyOverview("Today"));
    const billed = cards.find((card) => card.id === "billed");
    const collected = cards.find((card) => card.id === "collected");
    const outstanding = cards.find((card) => card.id === "outstanding");
    assert.equal(billed?.label, "Billed");
    assert.doesNotMatch(billed?.hint || "", /revenue/i);
    assert.equal(collected?.label, "Collected");
    assert.match(outstanding?.hint || "", /not the outstanding balance as of the selected/i);
    assert.equal(outstanding?.snapshot, true);
    assert.match(outstandingHint(metric({ asOf: "current" })), /not the outstanding balance as of the selected/i);
  });

  it("builds date-filter query strings for presets and custom ranges", () => {
    assert.equal(periodQuery("today", "", ""), "period=today");
    assert.equal(periodQuery("this_week", "", ""), "period=this_week");
    assert.equal(periodQuery("custom", "2026-08-01", "2026-08-07"), "period=custom&from=2026-08-01&to=2026-08-07");
    assert.equal(customRangeValid("", "2026-08-07"), "Enter a start date and an end date.");
    assert.equal(customRangeValid("2026-08-10", "2026-08-01"), "The end date cannot be before the start date.");
    assert.equal(customRangeValid("2026-08-01", "2026-08-07"), "");
  });

  it("stacks analytics cards on a 390px-wide layout", () => {
    assert.match(CSS, /@media \(max-width: 480px\)/);
    assert.match(CSS, /grid-template-columns: 1fr/);
    assert.match(CSS, /admin-analytics__grid/);
    assert.match(ANALYTICS_SOURCE, /admin-analytics__grid/);
    assert.match(ANALYTICS_SOURCE, /Hospital overview/);
    assert.match(ANALYTICS_SOURCE, /Reception/);
    assert.match(ANALYTICS_SOURCE, /Inpatient/);
    assert.match(ANALYTICS_SOURCE, /Revenue by department/);
    assert.doesNotMatch(ANALYTICS_SOURCE, /OpenMRS|Bahmni|Odoo|UUID|OpenELIS/);
  });
});

describe("Staff administration audit view", () => {
  it("summarizes department and status changes without secrets", () => {
    const event: AdminStaffAuditEvent = {
      eventId: "evt-1",
      occurredAt: "2026-08-27T01:18:55.738+00:00",
      actorUsername: "hospitaladmin.abikan",
      targetUsername: "doctor.test",
      action: "ADMIN_UPDATE_DEPARTMENTS",
      actionLabel: "Updated department access",
      outcome: "success",
      errorCode: "",
      requestId: "req-1",
      previous: { departments: ["clinical"] },
      current: { departments: ["clinical", "nursing"] },
    };
    assert.equal(auditOutcomeLabel("success"), "Completed");
    assert.equal(auditChangeSummary(event), "clinical → clinical, nursing");
    assert.match(AUDIT_SOURCE, /Staff activity/);
    assert.doesNotMatch(AUDIT_SOURCE, /password|OpenELIS|JSESSIONID/i);
    assert.match(CSS, /admin-audit__table/);
    assert.match(CSS, /overflow-x: auto/);
  });

  it("summarizes patient Alive to Dead changes", () => {
    const event: AdminStaffAuditEvent = {
      eventId: "evt-life",
      occurredAt: "2026-09-07T12:00:00.000+00:00",
      actorUsername: "hospitaladmin.abikan",
      targetUsername: "ABC123",
      action: "ADMIN_UPDATE_PATIENT_LIFE_STATUS",
      actionLabel: "Updated patient life status",
      outcome: "success",
      errorCode: "",
      requestId: "req-life",
      previous: { alive: true },
      current: { alive: false, deathDate: "2026-09-01" },
    };
    assert.equal(auditChangeSummary(event), "Alive → Dead · death 2026-09-01");
  });
});
