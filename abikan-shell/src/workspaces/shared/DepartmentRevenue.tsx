import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { KpiCard } from "../../components/KpiCard";
import { fetchDepartmentRevenue } from "../../services/departmentRevenue";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { AdminPeriodId } from "../../types/administration";
import type { DepartmentRevenuePayload } from "../../types/departmentRevenue";
import { customRangeValid, formatMetricMoney, periodQuery } from "../Admin/adminAnalytics";
import {
  DEPARTMENT_REVENUE_PERIODS,
  revenueHint,
  revenueShareLabel,
} from "./departmentRevenueView";
import "./DepartmentRevenue.css";

function errorMessage(reason: unknown): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : "Revenue generated could not be loaded.";
}

export function useDepartmentRevenue() {
  const [period, setPeriod] = useState<AdminPeriodId>("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [payload, setPayload] = useState<DepartmentRevenuePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const customProblem = period === "custom" ? customRangeValid(customStart, customEnd) : "";

  const load = async () => {
    if (period === "custom" && customProblem) {
      setError(customProblem);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setPayload(await fetchDepartmentRevenue(periodQuery(period, customStart, customEnd)));
    } catch (reason) {
      setPayload(null);
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (period === "custom") {
      return;
    }
    void load();
  }, [period]);

  const periodLabel =
    payload?.period.label || DEPARTMENT_REVENUE_PERIODS.find((item) => item.id === period)?.label || "Today";

  return {
    period,
    setPeriod,
    customStart,
    setCustomStart,
    customEnd,
    setCustomEnd,
    customProblem,
    payload,
    loading,
    error,
    periodLabel,
    load,
    value: formatMetricMoney(payload?.revenue),
    departmentName: payload?.departments.length === 1 ? payload.departments[0].department : undefined,
  };
}

export type DepartmentRevenueState = ReturnType<typeof useDepartmentRevenue>;

export function RevenuePeriodFilter({
  revenue,
  caption,
}: {
  revenue: DepartmentRevenueState;
  caption?: string | null;
}) {
  return (
    <form
      className="dept-revenue__filters"
      aria-label="Revenue date range"
      onSubmit={(event) => {
        event.preventDefault();
        void revenue.load();
      }}
    >
      <label>
        Date range
        <select
          value={revenue.period}
          onChange={(event) => revenue.setPeriod(event.target.value as AdminPeriodId)}
        >
          {DEPARTMENT_REVENUE_PERIODS.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {revenue.period === "custom" ? (
        <>
          <label>
            From
            <input
              type="date"
              value={revenue.customStart}
              onChange={(event) => revenue.setCustomStart(event.target.value)}
            />
          </label>
          <label>
            To
            <input
              type="date"
              value={revenue.customEnd}
              onChange={(event) => revenue.setCustomEnd(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={Boolean(revenue.customProblem)}>
            Apply dates
          </Button>
        </>
      ) : null}
      {caption === null ? null : (
        <p className="dept-revenue__range">
          {caption ?? `Showing ${revenue.periodLabel} in Ilorin time. Posted invoices only.`}
        </p>
      )}
    </form>
  );
}

export function RevenueGeneratedCard({ revenue }: { revenue: DepartmentRevenueState }) {
  const value = revenue.loading ? "…" : revenue.error ? "Unavailable" : revenue.value;
  return (
    <KpiCard
      label="Revenue Generated"
      value={value}
      hint={
        revenue.error
          ? revenue.error
          : revenueHint(revenue.periodLabel, revenue.departmentName)
      }
      icon="naira"
      tone="collection"
    />
  );
}

export function HospitalRevenueBreakdown({ revenue }: { revenue: DepartmentRevenueState }) {
  if (revenue.payload?.scope !== "hospital") {
    return null;
  }
  const rows = revenue.payload.departments;
  return (
    <section className="dept-revenue__breakdown" aria-label="Revenue by department">
      <h2>Revenue by department</h2>
      <p>Each department’s share of posted invoices for {revenue.periodLabel}.</p>
      {revenue.error ? <Alert tone="danger" title={revenue.error} /> : null}
      {!revenue.loading && !revenue.error && rows.length === 0 ? (
        <p className="dept-revenue__empty">No posted invoices in this date range.</p>
      ) : null}
      {!revenue.loading && rows.length > 0 ? (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Department</th>
                <th>Revenue Generated</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.department}>
                  <td>{row.department}</td>
                  <td>{formatMetricMoney(row)}</td>
                  <td>{revenueShareLabel(row.share)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
