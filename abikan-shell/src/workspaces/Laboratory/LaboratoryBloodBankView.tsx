import { useEffect, useMemo, useState } from "react";
import {
  openLaboratoryOrder,
  openLaboratoryPatient,
  openLaboratorySection,
  openLaboratoryWorklistOrder,
} from "../../app/hashRoute";
import { BAHMNI_ROUTES, bahmniUrl } from "../../config/appConfig";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { KpiCard } from "../../components/KpiCard";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { QuickAction } from "../../components/QuickAction";
import { SectionHeader } from "../../components/SectionHeader";
import { TableSkeleton } from "../../components/TableSkeleton";
import {
  fetchLaboratoryBoard,
  fetchLaboratoryCatalogue,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  LaboratoryBoardOrder,
  LaboratoryCatalogueTest,
} from "../../types/laboratoryCatalogue";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import {
  bloodBankKindLabel,
  filterBloodBankCatalogue,
  filterBloodBankOrders,
} from "./laboratoryBloodBank";
import { BloodBankUnitsPanel } from "./BloodBankUnitsPanel";

type BloodBankTab = "requests" | "units" | "services";

function openOrder(row: LaboratoryBoardOrder) {
  if (row.patientUuid && row.visitUuid) {
    openLaboratoryWorklistOrder({
      orderUuid: row.uuid,
      patientUuid: row.patientUuid,
      visitUuid: row.visitUuid,
    });
    return;
  }
  openLaboratoryOrder(row.uuid, row.patientUuid, row.visitUuid);
}

function RequestTable({
  rows,
  emptyTitle,
  emptyDescription,
}: {
  rows: LaboratoryBoardOrder[];
  emptyTitle: string;
  emptyDescription: string;
}) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Request</th>
            <th>Kind</th>
            <th>Payment</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.uuid}>
              <td>
                {row.patientUuid ? (
                  <button
                    type="button"
                    className="lab-desk__link"
                    onClick={() => openLaboratoryPatient(row.patientUuid)}
                  >
                    {row.patientName}
                  </button>
                ) : (
                  row.patientName
                )}
                <div className="lab-blood-bank__subtle">{row.mrn || "—"}</div>
              </td>
              <td>
                <strong>{row.testName}</strong>
                <div className="lab-blood-bank__subtle">{row.ordered || "—"}</div>
              </td>
              <td>{bloodBankKindLabel(row.testName)}</td>
              <td>
                <Badge tone={paymentStateTone(row.paymentStatus)}>{row.paymentStatus}</Badge>
              </td>
              <td>
                <span title={row.statusMessage || undefined}>{row.laboratoryStatus}</span>
              </td>
              <td>
                <button type="button" className="lab-desk__link" onClick={() => openOrder(row)}>
                  Open
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LaboratoryBloodBankView() {
  const [tab, setTab] = useState<BloodBankTab>("requests");
  const [orders, setOrders] = useState<LaboratoryBoardOrder[]>([]);
  const [services, setServices] = useState<LaboratoryCatalogueTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const processingUrl = bahmniUrl(BAHMNI_ROUTES.openElis);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchLaboratoryBoard(), fetchLaboratoryCatalogue("")])
      .then(([board, catalogue]) => {
        if (cancelled) {
          return;
        }
        setOrders(filterBloodBankOrders(board.orders || []));
        setServices(filterBloodBankCatalogue(catalogue.tests || []));
        setError("");
      })
      .catch((reason) => {
        if (cancelled) {
          return;
        }
        setOrders([]);
        setServices([]);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Blood bank requests could not be loaded.",
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
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return orders;
    }
    return orders.filter((row) =>
      [row.patientName, row.mrn, row.testName, row.orderNumber, row.provider]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [orders, query]);

  const pending = filtered.filter((row) => row.stage === "pending");
  const processing = filtered.filter((row) => row.stage === "processing");
  const completed = filtered.filter((row) => row.stage === "completed");
  const readyServices = services.filter((row) => row.orderable && row.conceptUuid);

  return (
    <div className="lab-desk lab-blood-bank">
      <PageHeader
        title="Blood Bank"
        description="Grouping, cross-match, donor screening, blood product requests, and blood unit stock. Sample work and result entry stay in laboratory processing."
      />

      {error ? <Alert tone="danger" title={error} /> : null}

      <section className="lab-blood-bank__hero" aria-label="Blood bank overview">
        <div className="lab-blood-bank__hero-copy">
          <p className="lab-blood-bank__kicker">Hospital blood bank</p>
          <h2>Requests, units, and laboratory processing</h2>
          <p>
            Track blood bank orders from the laboratory catalogue, keep bag stock on the Blood units
            tab, and open laboratory processing for sample collection, grouping, cross-match, and
            result entry.
          </p>
          <div className="lab-blood-bank__hero-actions">
            <Button onClick={() => openLaboratorySection("new-order")}>New blood bank request</Button>
            <a className="abikan-button abikan-button--secondary" href={processingUrl}>
              Open laboratory processing
            </a>
          </div>
        </div>
        <div className="lab-blood-bank__hero-panel" aria-hidden="true">
          <div className="lab-blood-bank__orb" />
          <p>Grouping · Cross-match · Donor screen · Pints</p>
        </div>
      </section>

      <div className="lab-desk__actions lab-blood-bank__actions">
        <QuickAction
          label="New request"
          icon="clipboardPlus"
          tone="collection"
          onClick={() => openLaboratorySection("new-order")}
        />
        <QuickAction
          label="Process in lab"
          icon="activity"
          tone="visits"
          onClick={() => {
            window.location.href = processingUrl;
          }}
        />
        <QuickAction
          label="Blood units"
          icon="flask"
          tone="appointments"
          onClick={() => setTab("units")}
        />
        <QuickAction
          label="Blood services"
          icon="clipboardList"
          tone="visits"
          onClick={() => setTab("services")}
        />
        <QuickAction
          label="Search patient"
          icon="users"
          tone="registration"
          onClick={() => openLaboratorySection("patients")}
        />
      </div>

      <section className="lab-desk__kpis" aria-label="Blood bank today">
        <KpiCard
          label="Waiting"
          value={loading ? "—" : pending.length}
          hint="Need sample or start"
          tone="appointments"
          icon="clipboardList"
        />
        <KpiCard
          label="In progress"
          value={loading ? "—" : processing.length}
          hint="In laboratory processing"
          tone="visits"
          icon="activity"
        />
        <KpiCard
          label="Ready"
          value={loading ? "—" : completed.length}
          hint="Results available"
          tone="teal"
          icon="fileText"
        />
        <KpiCard
          label="Services"
          value={loading ? "—" : readyServices.length}
          hint="Orderable blood bank items"
          tone="collection"
          icon="flask"
        />
      </section>

      <div className="lab-blood-bank__tabs" role="tablist" aria-label="Blood bank views">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "requests"}
          className={tab === "requests" ? "is-active" : undefined}
          onClick={() => setTab("requests")}
        >
          Requests
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "units"}
          className={tab === "units" ? "is-active" : undefined}
          onClick={() => setTab("units")}
        >
          Blood units
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "services"}
          className={tab === "services" ? "is-active" : undefined}
          onClick={() => setTab("services")}
        >
          Services & prices
        </button>
      </div>

      {tab === "units" ? <BloodBankUnitsPanel /> : null}

      {tab === "requests" ? (
        <Card>
          <SectionHeader
            title="Blood bank requests"
            description="Blood grouping, cross-match, donor screening, and blood product requests from doctors or Laboratory."
          />
          <label className="lab-desk__search">
            Search requests
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Patient, hospital number, or request"
            />
          </label>
          {loading ? (
            <TableSkeleton
              label="Loading blood bank requests…"
              headers={["Patient", "Request", "Kind", "Payment", "Status", "Action"]}
            />
          ) : (
            <div className="lab-blood-bank__stacks">
              <section>
                <h3>Waiting</h3>
                <RequestTable
                  rows={pending}
                  emptyTitle="Nothing waiting"
                  emptyDescription="No blood bank requests are waiting for sample collection or start."
                />
              </section>
              <section>
                <h3>In progress</h3>
                <RequestTable
                  rows={processing}
                  emptyTitle="Nothing in progress"
                  emptyDescription="No blood bank work is in laboratory processing right now."
                />
              </section>
              <section>
                <h3>Ready</h3>
                <RequestTable
                  rows={completed}
                  emptyTitle="No ready results"
                  emptyDescription="No completed blood bank results in the current board."
                />
              </section>
            </div>
          )}
        </Card>
      ) : null}

      {tab === "services" ? (
        <Card>
          <SectionHeader
            title="Blood bank services"
            description="Hospital blood bank items from the laboratory catalogue. Use New Lab Order to request one for a patient."
          />
          {loading ? <LoadingState variant="board" label="Loading blood bank services…" /> : null}
          {!loading && services.length === 0 ? (
            <EmptyState
              title="No blood bank services yet"
              description="Ask Hospital Admin to enable Blood Grouping, Cross Match, donor screening, or blood product services under Hospital Tests."
            />
          ) : null}
          {!loading && services.length > 0 ? (
            <div className="lab-blood-bank__service-grid">
              {services.map((service) => (
                <article key={service.id || service.conceptUuid || service.name} className="lab-blood-bank__service">
                  <div className="lab-blood-bank__service-top">
                    <Badge tone="info">{bloodBankKindLabel(service.name)}</Badge>
                    <Badge tone={service.orderable ? "success" : "warning"}>
                      {service.orderable ? "Orderable" : "Not ready"}
                    </Badge>
                  </div>
                  <h3>{service.name}</h3>
                  <p>
                    {[service.specimen, service.tat, service.type].filter(Boolean).join(" · ") ||
                      "Blood bank service"}
                  </p>
                  <div className="lab-blood-bank__service-price">
                    {service.price?.formatted || "Price not set"}
                  </div>
                  <Button
                    variant="secondary"
                    disabled={!service.orderable || !service.conceptUuid}
                    onClick={() => openLaboratorySection("new-order")}
                  >
                    Request for patient
                  </Button>
                </article>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}
