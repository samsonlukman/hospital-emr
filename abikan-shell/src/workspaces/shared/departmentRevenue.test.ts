import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { customRangeValid, periodQuery } from "../Admin/adminAnalytics.ts";
import {
  DEPARTMENT_REVENUE_PERIODS,
  revenueHint,
  revenueShareLabel,
} from "./departmentRevenueView.ts";

describe("Department revenue presentation", () => {
  it("offers today, this week, this month, and a custom range", () => {
    assert.deepEqual(
      DEPARTMENT_REVENUE_PERIODS.map((item) => item.id),
      ["today", "this_week", "this_month", "custom"],
    );
    assert.equal(periodQuery("today", "", ""), "period=today");
    assert.equal(periodQuery("this_week", "", ""), "period=this_week");
    assert.equal(periodQuery("this_month", "", ""), "period=this_month");
    assert.equal(
      periodQuery("custom", "2026-09-01", "2026-09-07"),
      "period=custom&from=2026-09-01&to=2026-09-07",
    );
    assert.equal(customRangeValid("2026-09-07", "2026-09-01"), "The end date cannot be before the start date.");
  });

  it("shows ₦0.00 language for an empty department period", () => {
    assert.equal(revenueHint("Today", "Laboratory"), "Laboratory posted invoices for Today.");
    assert.equal(revenueShareLabel(0.25), "25%");
    assert.equal(revenueShareLabel(0), "0%");
    assert.equal(revenueShareLabel(undefined), "0%");
  });
});
