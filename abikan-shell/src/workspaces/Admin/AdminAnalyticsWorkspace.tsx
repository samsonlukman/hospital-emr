import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { PageHeader } from "../../components/PageHeader";
import { fetchAdminAnalyticsOverview } from "../../services/administration";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { AdminAnalyticsOverview, AdminPeriodId } from "../../types/administration";
import { revenueShareLabel } from "../shared/departmentRevenueView";
import {
  ANALYTICS_PERIODS,
  customRangeValid,
  formatMetricCount,
  formatMetricMoney,
  occupancyHeadline,
  occupancyHint,
  occupancyRateLabel,
  overviewCards,
  periodQuery,
} from "./adminAnalytics";
import "./AdminWorkspace.css";

const CARD_ICONS = {
  patientsRegistered: "userPlus",
  consultations: "stethoscope",
  admissions: "clipboardPlus",
  discharges: "calendar",
  occupancy: "bed",
  occupancyRate: "chart",
  labOrders: "flask",
  prescriptions: "pill",
  dispensed: "receipt",
  billed: "fileText",
  collected: "creditCard",
  outstanding: "naira",
} as const;

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

export function AdminAnalyticsWorkspace() {
  const [period, setPeriod] = useState<AdminPeriodId>("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [overview, setOverview] = useState<AdminAnalyticsOverview | null>(null);
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
      setOverview(
        await fetchAdminAnalyticsOverview(periodQuery(period, customStart, customEnd)),
      );
    } catch (reason) {
      setOverview(null);
      setError(errorMessage(reason, "Hospital overview could not be loaded."));
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

  const cards = useMemo(() => overviewCards(overview), [overview]);
  const rangeLabel = overview?.period.label || ANALYTICS_PERIODS.find((item) => item.id === period)?.label;

  return (
    <div className="admin-workspace admin-analytics">
      <PageHeader
        title="Hospital overview"
        description="Hospital-wide counts for the selected dates. Occupancy and outstanding are current snapshots."
      />

      <form
        className="admin-analytics__filters"
        onSubmit={(event) => {
          event.preventDefault();
          void load();
        }}
      >
        <label>
          Date range
          <select
            value={period}
            onChange={(event) => setPeriod(event.target.value as AdminPeriodId)}
          >
            {ANALYTICS_PERIODS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {period === "custom" ? (
          <>
            <label>
              From
              <input
                type="date"
                value={customStart}
                onChange={(event) => setCustomStart(event.target.value)}
              />
            </label>
            <label>
              To
              <input
                type="date"
                value={customEnd}
                onChange={(event) => setCustomEnd(event.target.value)}
              />
            </label>
            <Button type="submit" disabled={Boolean(customProblem)}>
              Apply dates
            </Button>
          </>
        ) : null}
      </form>

      <p className="admin-analytics__range">
        Showing {rangeLabel} in Ilorin time. Occupancy is how many beds are in use now.
      </p>

      {error ? <Alert tone="danger" title={error} /> : null}

      {loading ? (
        <LoadingState variant="board" label="Loading hospital overview…" />
      ) : null}

      {!loading && overview ? (
        <>
          <section className="admin-analytics__grid" aria-label="Hospital overview">
            {cards.map((card) => (
              <KpiCard
                key={card.id}
                label={card.label}
                value={card.value}
                hint={card.hint}
                icon={CARD_ICONS[card.id]}
                tone={card.snapshot ? "neutral" : "visits"}
              />
            ))}
          </section>

          <section className="admin-analytics__section">
            <h2>Reception</h2>
            <div className="admin-analytics__grid admin-analytics__grid--two">
              <KpiCard
                label="Patients registered"
                value={formatMetricCount(overview.patientsRegistered)}
                hint="New registrations in this date range."
                icon="userPlus"
                tone="registration"
              />
              <KpiCard
                label="Outpatient visits"
                value={formatMetricCount(overview.opdVisits)}
                hint="Outpatient visits only. Inpatient stays are not included."
                icon="clipboardList"
                tone="appointments"
              />
            </div>
          </section>

          <section className="admin-analytics__section" aria-label="Revenue by department">
            <h2>Revenue by department</h2>
            <p className="admin-analytics__range">
              Each department’s share of posted invoices for {rangeLabel}.
            </p>
            {overview.revenueByDepartment?.status === "unavailable" ? (
              <Alert
                tone="danger"
                title={overview.revenueByDepartment.message || "Department revenue could not be loaded."}
              />
            ) : null}
            {overview.revenueByDepartment?.status !== "unavailable" &&
            (overview.revenueByDepartment?.departments.length || 0) === 0 ? (
              <p className="admin-analytics__range">No posted invoices in this date range.</p>
            ) : null}
            {(overview.revenueByDepartment?.departments.length || 0) > 0 ? (
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
                    {overview.revenueByDepartment?.departments.map((row) => (
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

          <section className="admin-analytics__section">
            <h2>Inpatient</h2>
            <div className="admin-analytics__grid admin-analytics__grid--two">
              <KpiCard
                label="Admissions"
                value={formatMetricCount(overview.admissions)}
                hint="Admission encounters in this date range."
                icon="clipboardPlus"
                tone="visits"
              />
              <KpiCard
                label="Discharges"
                value={formatMetricCount(overview.discharges)}
                hint="Discharge encounters in this date range."
                icon="calendar"
                tone="visits"
              />
              <KpiCard
                label="Current occupancy"
                value={occupancyHeadline(overview.occupancy)}
                hint={occupancyHint(overview.occupancy)}
                icon="bed"
                tone="neutral"
              />
              <KpiCard
                label="Current occupancy rate"
                value={occupancyRateLabel(overview.occupancy)}
                hint={occupancyHint(overview.occupancy)}
                icon="chart"
                tone="neutral"
              />
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}