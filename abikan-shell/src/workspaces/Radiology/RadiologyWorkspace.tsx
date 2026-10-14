import { useEffect, useMemo, useState } from "react";
import {
  openRadiologyExternalStudy,
  openRadiologyPatient,
  openRadiologySection,
  openRadiologyWorklistOrder,
  readHashNavItemId,
} from "../../app/hashRoute";
import { RADIOGRAPHY_GROUP, ULTRASOUND_GROUP } from "../../config/radiologyMenu";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { PageHeader } from "../../components/PageHeader";
import { QuickAction } from "../../components/QuickAction";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import { fetchRadiologyWorklist } from "../../services/radiologyBilling";
import type { RadiologyWorklistRow } from "../../types/radiologyBilling";
import type { WorkspaceContext } from "../../types";
import { formatClinicalWhen, greetingForNow } from "../../utils/datetime";
import {
  RADIOLOGY_HOME_HELP,
  RADIOLOGY_REPORTED_EMPTY,
  RADIOLOGY_WORKLIST_EMPTY,
  RADIOLOGY_WORKLIST_HELP,
  RADIOLOGY_WORKLIST_SEARCH_PLACEHOLDER,
  radiologyPaymentTone,
  radiologyPatientTypeLabel,
  radiologyRequestSourceLabel,
  radiologyVisitLabel,
} from "./radiologyDesk";
import {
  RevenueGeneratedCard,
  RevenuePeriodFilter,
  useDepartmentRevenue,
} from "../shared/DepartmentRevenue";
import {
  canOpenWorklistRow,
  filterWorklistRows,
  replaceWorklistRows,
  type RadiologyWorklistCategory,
  type RadiologyWorklistView,
} from "./radiologyWorklist";
import { RadiologyHistoryView } from "./RadiologyHistoryView";
import { RadiologyNewStudyView } from "./RadiologyNewStudyView";
import { radiologyViewFromNav } from "./radiologyView";
import "./RadiologyWorkspace.css";

interface RadiologyWorkspaceProps {
  context: WorkspaceContext;
}

function WorklistTable({
  rows,
  emptyTitle,
}: {
  rows: RadiologyWorklistRow[];
  emptyTitle: string;
}) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} />;
  }
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Type</th>
            <th>Hospital number</th>
            <th>Visit</th>
            <th>Examination</th>
            <th>Source</th>
            <th>Ordered</th>
            <th>Price</th>
            <th>Payment</th>
            <th>Report</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.uuid}>
              <td>
                {row.patientUuid && !row.isExternal ? (
                  <button
                    type="button"
                    className="rad-link"
                    onClick={() => openRadiologyPatient(row.patientUuid)}
                  >
                    {row.patientName}
                  </button>
                ) : (
                  <>
                    {row.patientName}
                    {row.buyerPhone ? (
                      <div className="rad-history__muted">{row.buyerPhone}</div>
                    ) : null}
                  </>
                )}
              </td>
              <td>{radiologyPatientTypeLabel(row.patientType, row.isExternal)}</td>
              <td>{row.mrn || "—"}</td>
              <td>{row.isExternal ? "—" : radiologyVisitLabel(row)}</td>
              <td>
                {row.investigation}
                {row.urgency === "STAT" ? (
                  <div>
                    <Badge tone="danger">STAT</Badge>
                  </div>
                ) : null}
              </td>
              <td>
                {row.requestSourceLabel ||
                  radiologyRequestSourceLabel(row.requestSource, row.comment)}
              </td>
              <td>{formatClinicalWhen(row.ordered)}</td>
              <td>{row.feeFormatted || "—"}</td>
              <td>
                <Badge tone={radiologyPaymentTone(row.billingStatus)}>{row.billingStatus}</Badge>
              </td>
              <td>{row.reportStatus}</td>
              <td>
                {canOpenWorklistRow(row) ? (
                  <button
                    type="button"
                    className="rad-link"
                    onClick={() => {
                      if (row.isExternal) {
                        openRadiologyExternalStudy(row.studyId || row.uuid);
                        return;
                      }
                      openRadiologyWorklistOrder({
                        orderUuid: row.uuid,
                        patientUuid: row.patientUuid,
                        visitUuid: row.visitUuid,
                      });
                    }}
                  >
                    Open
                  </button>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RadiologyWorkspace({ context }: RadiologyWorkspaceProps) {
  const [view, setView] = useState(() => radiologyViewFromNav(readHashNavItemId()));
  const [orders, setOrders] = useState<RadiologyWorklistRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<RadiologyWorklistCategory>("");
  const [reportView, setReportView] = useState<RadiologyWorklistView>("pending");
  const revenue = useDepartmentRevenue();

  useEffect(() => {
    const onHash = () => setView(radiologyViewFromNav(readHashNavItemId()));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (view !== "worklist") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchRadiologyWorklist()
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setOrders(replaceWorklistRows(null, payload.orders || []));
        setError("");
      })
      .catch((reason) => {
        if (cancelled) {
          return;
        }
        setOrders([]);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Radiology examinations could not be loaded. Search a patient to review that person's orders.",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [view]);

  const filtered = useMemo(
    () => filterWorklistRows(orders, { query, category, view: "all" }),
    [orders, query, category],
  );
  const pending = filtered.filter((row) => !row.hasReport);
  const reported = filtered.filter((row) => row.hasReport);
  const visiblePending = reportView === "reported" ? [] : pending;
  const visibleReported = reportView === "pending" ? [] : reported;

  const pageTitle =
    view === "new-study"
      ? "New Imaging Study"
      : view === "history"
        ? "Imaging History"
        : "Radiology Worklist";
  const pageDescription =
    view === "new-study"
      ? "Create an imaging study started by Radiology. No doctor order is required."
      : view === "history"
        ? "Review previous imaging studies. Payment and report status stay separate from request source."
        : `${greetingForNow()}, ${context.displayName}. ${RADIOLOGY_HOME_HELP}`;

  return (
    <div className="rad-desk">
      <PageHeader title={pageTitle} description={pageDescription} />

      {view === "new-study" ? <RadiologyNewStudyView context={context} /> : null}
      {view === "history" ? <RadiologyHistoryView /> : null}

      {view === "worklist" ? (
        <>
      <RevenuePeriodFilter revenue={revenue} />
      <section className="rad-desk__kpis" aria-label="Today's overview">
        <KpiCard
          label="Examinations"
          value={loading ? "…" : filtered.length}
          hint="Current radiology worklist"
          tone="visits"
          icon="clipboardList"
        />
        <KpiCard
          label="Pending"
          value={loading ? "…" : pending.length}
          hint="Waiting for a report"
          tone="appointments"
          icon="clipboardPlus"
        />
        <KpiCard
          label="Reported"
          value={loading ? "…" : reported.length}
          hint="Reports already entered"
          tone="teal"
          icon="receipt"
        />
        <RevenueGeneratedCard revenue={revenue} />
      </section>

      <Card>
        <SectionHeader title="Quick actions" />
        <div className="rad-desk__actions">
          <QuickAction
            label="New Imaging Study"
            icon="clipboardPlus"
            tone="visits"
            onClick={() => openRadiologySection("new-study")}
          />
          <QuickAction
            label="Imaging History"
            icon="receipt"
            tone="teal"
            onClick={() => openRadiologySection("history")}
          />
        </div>
      </Card>

      {error ? (
        <Alert tone="danger" title="Examinations could not be loaded">
          <p>{error}</p>
        </Alert>
      ) : null}

      <Card id="worklist">
        <SectionHeader title="Pending examinations" description={RADIOLOGY_WORKLIST_HELP} />
        <div className="rad-worklist__filters">
          <label className="rad-worklist__search">
            <span>Search</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={RADIOLOGY_WORKLIST_SEARCH_PLACEHOLDER}
            />
          </label>
          <label className="rad-worklist__search">
            <span>Examination</span>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value as RadiologyWorklistCategory)}
            >
              <option value="">All examinations</option>
              <option value={ULTRASOUND_GROUP}>Ultrasound Scan</option>
              <option value={RADIOGRAPHY_GROUP}>Radiography / Fluoroscopy</option>
            </select>
          </label>
          <label className="rad-worklist__search">
            <span>Report</span>
            <select
              value={reportView}
              onChange={(event) => setReportView(event.target.value as RadiologyWorklistView)}
            >
              <option value="pending">Pending</option>
              <option value="reported">Reported</option>
              <option value="all">Pending and reported</option>
            </select>
          </label>
        </div>
        {loading ? (
          <LoadingState variant="board" label="Loading radiology examinations…" />
        ) : (
          <WorklistTable rows={visiblePending} emptyTitle={RADIOLOGY_WORKLIST_EMPTY} />
        )}
      </Card>

      {reportView !== "pending" ? (
        <Card id="reported">
          <SectionHeader
            title="Reported"
            description="These examinations already have a Radiology Report."
          />
          {loading ? (
            <LoadingState variant="board" label="Loading reported examinations…" />
          ) : (
            <WorklistTable rows={visibleReported} emptyTitle={RADIOLOGY_REPORTED_EMPTY} />
          )}
        </Card>
      ) : null}
        </>
      ) : null}
    </div>
  );
}
