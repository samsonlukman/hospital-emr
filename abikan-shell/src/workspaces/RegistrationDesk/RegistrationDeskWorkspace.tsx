import { useEffect, useState } from "react";
import { openAntenatalRegistration, openCreateVisit, openReceptionFamilies, openRegistrationPatient, openRegistrationRegister, readHashNavItemId, setShellRoute } from "../../app/hashRoute";
import { PricingDesk } from "../Pricing/PricingDesk";
import { Badge, statusTone } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { TableSkeleton } from "../../components/TableSkeleton";
import { KpiCard } from "../../components/KpiCard";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { QuickAction } from "../../components/QuickAction";
import { SectionHeader } from "../../components/SectionHeader";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes";
import { formatDailyVisitNumber } from "../../utils/dailyVisitNumber";
import { fetchNewRegistrations } from "../../services/openmrs/patients";
import { fetchTodaysVisits } from "../../services/openmrs/visits";
import type { ReceptionRegistration, ReceptionVisit } from "../../types";
import { periodQuery } from "../Admin/adminAnalytics";
import {
  RevenueGeneratedCard,
  RevenuePeriodFilter,
  useDepartmentRevenue,
} from "../shared/DepartmentRevenue";
import "./RegistrationDeskWorkspace.css";

function focusPatientSearch() {
  document.getElementById("global-patient-search")?.focus();
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function registeredWhen(row: ReceptionRegistration, singleDay: boolean): string {
  if (singleDay || !row.date) {
    return row.time;
  }
  const [, month, day] = row.date.split("-");
  const monthName = MONTHS[Number(month) - 1];
  if (!monthName || !day) {
    return row.time;
  }
  return `${Number(day)} ${monthName} · ${row.time}`;
}

export function RegistrationDeskWorkspace() {
  const [visits, setVisits] = useState<ReceptionVisit[]>([]);
  const [registrations, setRegistrations] = useState<ReceptionRegistration[]>([]);
  const [registrationTotal, setRegistrationTotal] = useState(0);
  const [registrationSingleDay, setRegistrationSingleDay] = useState(true);
  const [registrationsLoading, setRegistrationsLoading] = useState(true);
  const [registrationsError, setRegistrationsError] = useState("");
  const [showNewPatients, setShowNewPatients] = useState(false);
  const [loading, setLoading] = useState(true);
  const [visitsError, setVisitsError] = useState<string | null>(null);
  const [nav, setNav] = useState(() => readHashNavItemId());
  const revenue = useDepartmentRevenue();
  const rangeKey =
    revenue.period === "custom"
      ? revenue.payload?.period.period === "custom"
        ? `${revenue.payload.period.startDate}|${revenue.payload.period.endDate}`
        : ""
      : revenue.period;

  useEffect(() => {
    let cancelled = false;
    fetchTodaysVisits()
      .then((rows) => {
        if (cancelled) {
          return;
        }
        setVisits(rows);
        setVisitsError(null);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setVisits([]);
        setVisitsError("Unable to load today's patients.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!rangeKey) {
      setRegistrations([]);
      setRegistrationTotal(0);
      setRegistrationsLoading(false);
      return;
    }
    let cancelled = false;
    setRegistrationsLoading(true);
    const query =
      revenue.period === "custom" && revenue.payload?.period.period === "custom"
        ? periodQuery("custom", revenue.payload.period.startDate, revenue.payload.period.endDate)
        : periodQuery(revenue.period, "", "");
    fetchNewRegistrations(query)
      .then((result) => {
        if (cancelled) {
          return;
        }
        setRegistrations(result.items);
        setRegistrationTotal(result.total);
        setRegistrationSingleDay(result.singleDay);
        setRegistrationsError("");
      })
      .catch((reason: unknown) => {
        if (cancelled) {
          return;
        }
        setRegistrations([]);
        setRegistrationTotal(0);
        setRegistrationsError(reason instanceof Error ? reason.message : "New patients could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) {
          setRegistrationsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [rangeKey, revenue.period, revenue.payload]);

  useEffect(() => {
    const onHash = () => {
      const current = readHashNavItemId();
      setNav(current);
      if (current === "create-visit") {
        openCreateVisit();
        return;
      }
      if (current === "patient-accounts") {
        focusPatientSearch();
      }
    };
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const activeVisits = visits.filter((visit) => visit.status.startsWith("Active"));
  const newPatientCount = registrationsLoading ? "…" : registrationTotal;

  const openNewPatients = () => {
    setShowNewPatients(true);
    window.setTimeout(() => scrollTo("new-patients"), 0);
  };

  if (nav === "pricing") {
    return (
      <PricingDesk
        department="reception"
        title="Card Pricing"
        description="Hospital card prices used for new registrations. Changing a price does not change bills already created."
      />
    );
  }

  return (
    <div className="reg-desk">
      <RevenuePeriodFilter revenue={revenue} caption={null} />
      {!loading ? (
        <section className="reg-desk__kpis" aria-label="Reception summary">
          <KpiCard
            label="Today's patients"
            value={visits.length}
            hint={visits.length === 0 ? "None yet" : "Visits today"}
            tone="visits"
            icon="users"
            actionLabel="Open"
            onAction={() => scrollTo("visits")}
          />
          <KpiCard
            label="Open visits"
            value={activeVisits.length}
            hint={activeVisits.length === 0 ? "None open" : "Still here"}
            tone="appointments"
            icon="clipboardList"
            actionLabel="Open"
            onAction={() => scrollTo("visits")}
          />
          <KpiCard
            label="New patients"
            value={newPatientCount}
            hint={revenue.periodLabel}
            tone="registration"
            icon="userPlus"
            actionLabel="See list"
            onClick={openNewPatients}
          />
          <KpiCard
            label="Accounts"
            value="View"
            hint="Balances"
            tone="collection"
            icon="creditCard"
            actionLabel="Find"
            onAction={focusPatientSearch}
          />
          <RevenueGeneratedCard revenue={revenue} />
        </section>
      ) : null}

      <Card>
        <SectionHeader title="Quick actions" />
        <div className="reg-desk__actions">
          <QuickAction
            label="Register patient"
            icon="userPlus"
            tone="registration"
            onClick={() => openRegistrationRegister()}
          />
          <QuickAction
            label="Create visit"
            icon="clipboardPlus"
            tone="appointments"
            onClick={() => openCreateVisit()}
          />
          <QuickAction
            label="Antenatal"
            icon="activity"
            tone="teal"
            onClick={() => openAntenatalRegistration()}
          />
          <QuickAction
            label="Families"
            icon="users"
            tone="visits"
            onClick={() => openReceptionFamilies()}
          />
          <QuickAction
            label="Today's visits"
            icon="clipboardList"
            tone="visits"
            onClick={() => scrollTo("visits")}
          />
          <QuickAction
            label="Patients"
            icon="folder"
            tone="appointments"
            onClick={() => setShellRoute("registration-patients")}
          />
          <QuickAction
            label="Accounts"
            icon="creditCard"
            tone="collection"
            onClick={focusPatientSearch}
          />
        </div>
      </Card>

      {showNewPatients ? (
        <section id="new-patients">
          <Card>
            <SectionHeader
              title="New patients"
              description={
                registrationTotal > registrations.length
                  ? `${revenue.periodLabel} · latest ${registrations.length}`
                  : revenue.periodLabel
              }
            />
            {registrationsLoading ? (
              <TableSkeleton
                label="Loading new patients…"
                headers={["Patient", "Hospital number", "Registered"]}
              />
            ) : registrationsError ? (
              <ErrorState title="New patients could not be loaded." description={registrationsError} />
            ) : registrations.length === 0 ? (
              <EmptyState
                title="No new patients."
                description={`Nobody was registered for ${revenue.periodLabel.toLowerCase()}.`}
              />
            ) : (
              <div className="abikan-table-wrap">
                <table className="abikan-table">
                  <thead>
                    <tr>
                      <th>Patient</th>
                      <th>Hospital number</th>
                      <th>Registered</th>
                    </tr>
                  </thead>
                  <tbody>
                    {registrations.map((row) => (
                      <tr key={row.uuid}>
                        <td>
                          <button
                            type="button"
                            className="reg-link"
                            onClick={() => openRegistrationPatient(row.uuid)}
                          >
                            {row.patientName}
                          </button>
                        </td>
                        <td>{row.mrn}</td>
                        <td className="reg-desk__when">{registeredWhen(row, registrationSingleDay)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </section>
      ) : null}

      <section id="visits">
        <Card>
          <SectionHeader
            title="Today's patients"
          />
          {loading ? (
            <TableSkeleton
              label="Loading today's patients…"
              headers={["No.", "Patient", "Hospital number", "Visit", "Time", "Status", "Action"]}
            />
          ) : visitsError ? (
            <ErrorState title="Unable to load today's patients." description={visitsError} />
          ) : visits.length === 0 ? (
            <EmptyState
              title="No visits today."
              description="A visit started today will appear here."
            />
          ) : (
            <div className="abikan-table-wrap">
              <table className="abikan-table">
                <thead>
                  <tr>
                    <th>No.</th>
                    <th>Patient</th>
                    <th>Hospital number</th>
                    <th>Visit</th>
                    <th>Time</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {visits.map((visit) => (
                    <tr key={visit.uuid}>
                      <td>{formatDailyVisitNumber(visit.dailyVisitNumber)}</td>
                      <td>
                        {visit.patientUuid ? (
                          <button
                            type="button"
                            className="reg-link"
                            onClick={() => openCreateVisit(visit.patientUuid)}
                          >
                            {visit.patientName}
                          </button>
                        ) : (
                          visit.patientName
                        )}
                      </td>
                      <td>{visit.mrn || "No hospital number"}</td>
                      <td>{receptionVisitTypeLabel(visit.visitType)}</td>
                      <td>{visit.time}</td>
                      <td>
                        <Badge tone={statusTone(visit.status)}>{visit.status}</Badge>
                      </td>
                      <td>
                        {visit.patientUuid ? (
                          <span className="reg-desk__row-actions">
                            <Button
                              variant="secondary"
                              onClick={() => openCreateVisit(visit.patientUuid)}
                            >
                              Open
                            </Button>
                            <PatientAccountLink patientUuid={visit.patientUuid} label="Account" />
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
