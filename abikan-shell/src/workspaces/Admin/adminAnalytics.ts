import type {
  AdminAnalyticsOverview,
  AdminMetric,
  AdminPeriodId,
  AdminStaffAuditEvent,
} from "../../types/administration";

export const ANALYTICS_PERIODS: { id: AdminPeriodId; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "this_week", label: "This week" },
  { id: "last_week", label: "Last week" },
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
  { id: "custom", label: "Custom range" },
];

export function isUnavailable(metric: AdminMetric | undefined): boolean {
  return !metric || metric.status === "unavailable";
}

export function formatMetricCount(metric: AdminMetric | undefined): string {
  if (isUnavailable(metric)) {
    return "Unavailable";
  }
  const value = metric?.value;
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "0";
  }
  return String(value);
}

export function formatMetricMoney(metric: AdminMetric | undefined): string {
  if (isUnavailable(metric)) {
    return "Unavailable";
  }
  if (metric?.formatted) {
    return metric.formatted;
  }
  const amount = metric?.amount ?? metric?.value;
  if (typeof amount !== "number" || Number.isNaN(amount)) {
    return "₦0.00";
  }
  return `₦${amount.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function occupancyHeadline(metric: AdminMetric | undefined): string {
  if (isUnavailable(metric)) {
    return "Unavailable";
  }
  if (metric?.label) {
    return metric.label;
  }
  const occupied = metric?.occupied ?? 0;
  const total = metric?.total ?? 0;
  return `${occupied} / ${total}`;
}

export function occupancyRateLabel(metric: AdminMetric | undefined): string {
  if (isUnavailable(metric)) {
    return "Unavailable";
  }
  const rate = metric?.rate;
  if (typeof rate !== "number" || Number.isNaN(rate)) {
    return "0%";
  }
  return `${Math.round(rate * 1000) / 10}%`;
}

export function occupancyHint(metric: AdminMetric | undefined): string {
  if (isUnavailable(metric)) {
    return metric?.message || "Current occupancy could not be loaded.";
  }
  return "Current occupancy now, not occupancy during the selected date range.";
}

export function outstandingHint(metric: AdminMetric | undefined): string {
  if (isUnavailable(metric)) {
    return metric?.message || "Outstanding balance could not be loaded.";
  }
  return (
    metric?.message ||
    "Current amount still unpaid. This is not the outstanding balance as of the selected dates."
  );
}

export function periodQuery(period: AdminPeriodId, start: string, end: string): string {
  const params = new URLSearchParams({ period });
  if (period === "custom" && start && end) {
    params.set("from", start);
    params.set("to", end);
  }
  return params.toString();
}

export function customRangeValid(start: string, end: string): string {
  if (!start || !end) {
    return "Enter a start date and an end date.";
  }
  if (end < start) {
    return "The end date cannot be before the start date.";
  }
  return "";
}

export type OverviewCardId =
  | "patientsRegistered"
  | "consultations"
  | "admissions"
  | "discharges"
  | "occupancy"
  | "occupancyRate"
  | "labOrders"
  | "prescriptions"
  | "dispensed"
  | "billed"
  | "collected"
  | "outstanding";

export interface OverviewCard {
  id: OverviewCardId;
  label: string;
  value: string;
  hint: string;
  snapshot?: boolean;
}

export function overviewCards(overview: AdminAnalyticsOverview | null): OverviewCard[] {
  if (!overview) {
    return [];
  }
  return [
    {
      id: "patientsRegistered",
      label: "Patients registered",
      value: formatMetricCount(overview.patientsRegistered),
      hint: "New hospital registrations in this date range.",
    },
    {
      id: "consultations",
      label: "Consultations",
      value: formatMetricCount(overview.consultations),
      hint: "Consultation encounters in this date range.",
    },
    {
      id: "admissions",
      label: "Admissions",
      value: formatMetricCount(overview.admissions),
      hint: "Admission encounters in this date range.",
    },
    {
      id: "discharges",
      label: "Discharges",
      value: formatMetricCount(overview.discharges),
      hint: "Discharge encounters in this date range.",
    },
    {
      id: "occupancy",
      label: "Current occupancy",
      value: occupancyHeadline(overview.occupancy),
      hint: occupancyHint(overview.occupancy),
      snapshot: true,
    },
    {
      id: "occupancyRate",
      label: "Current occupancy rate",
      value: occupancyRateLabel(overview.occupancy),
      hint: occupancyHint(overview.occupancy),
      snapshot: true,
    },
    {
      id: "labOrders",
      label: "Laboratory orders",
      value: formatMetricCount(overview.labOrders),
      hint: "Laboratory tests ordered in this date range.",
    },
    {
      id: "prescriptions",
      label: "Prescriptions",
      value: formatMetricCount(overview.prescriptions),
      hint: "Medication orders in this date range.",
    },
    {
      id: "dispensed",
      label: "Dispensed",
      value: formatMetricCount(overview.dispensed),
      hint: "Prescriptions with a completed pharmacy movement in this date range.",
    },
    {
      id: "billed",
      label: "Billed",
      value: formatMetricMoney(overview.billed),
      hint: "Posted invoices dated in this range.",
    },
    {
      id: "collected",
      label: "Collected",
      value: formatMetricMoney(overview.collected),
      hint: "Posted payments received in this date range.",
    },
    {
      id: "outstanding",
      label: "Outstanding",
      value: formatMetricMoney(overview.outstanding),
      hint: outstandingHint(overview.outstanding),
      snapshot: true,
    },
  ];
}

export function auditOutcomeLabel(outcome: string): string {
  if (outcome === "success") {
    return "Completed";
  }
  if (outcome === "failure") {
    return "Failed";
  }
  if (outcome === "pending") {
    return "Interrupted";
  }
  return outcome || "Unknown";
}

export function formatAuditTime(value: string): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value || "—";
  }
  return new Intl.DateTimeFormat("en-NG", {
    timeZone: "Africa/Lagos",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(parsed));
}

export function auditChangeSummary(event: AdminStaffAuditEvent): string {
  const previous = event.previous?.departments?.join(", ") || "";
  const next = event.current?.departments?.join(", ") || "";
  if (previous || next) {
    if (previous === next) {
      return next ? `Departments: ${next}` : "";
    }
    return `${previous || "None"} → ${next || "None"}`;
  }
  if (typeof event.previous?.enabled === "boolean" || typeof event.current?.enabled === "boolean") {
    const before = event.previous?.enabled ? "Active" : "Disabled";
    const after = event.current?.enabled ? "Active" : "Disabled";
    return `${before} → ${after}`;
  }
  if (typeof event.previous?.alive === "boolean" || typeof event.current?.alive === "boolean") {
    const before = event.previous?.alive === false ? "Dead" : "Alive";
    const after = event.current?.alive === false ? "Dead" : "Alive";
    if (before === after) {
      const deathDate = event.current?.deathDate || event.previous?.deathDate || "";
      return deathDate ? `${after} (${deathDate})` : after;
    }
    const deathDate = event.current?.deathDate ? ` · death ${event.current.deathDate}` : "";
    return `${before} → ${after}${deathDate}`;
  }
  return "";
}

export function emptyOverview(periodLabel: string): AdminAnalyticsOverview {
  const zero: AdminMetric = { status: "ok", value: 0 };
  const money: AdminMetric = {
    status: "ok",
    value: 0,
    amount: 0,
    formatted: "₦0.00",
  };
  return {
    status: "ok",
    period: {
      period: "today",
      label: periodLabel,
      timezone: "Africa/Lagos",
      startDate: "2026-08-27",
      endDate: "2026-08-27",
    },
    patientsRegistered: zero,
    opdVisits: zero,
    consultations: zero,
    admissions: zero,
    discharges: zero,
    occupancy: {
      status: "ok",
      value: 0,
      occupied: 0,
      total: 0,
      rate: 0,
      asOf: "current",
      label: "0 / 0",
    },
    labOrders: zero,
    prescriptions: zero,
    dispensed: zero,
    billed: money,
    collected: money,
    outstanding: { ...money, asOf: "current" },
    revenueByDepartment: { status: "ok", departments: [], total: money },
  };
}
