import { useCallback, useEffect, useState } from "react";
import { openLaboratoryExternalPatient, returnToPreviousScreen } from "../../app/hashRoute";
import { BAHMNI_ROUTES, bahmniUrl } from "../../config/appConfig";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { LabOrderTable, LabResultTable } from "../../components/LabTables";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionIndex } from "../../components/SectionIndex";
import { LaboratoryFeeCard } from "./LaboratoryFeeCard";
import {
  fetchPatientIdentity,
  fetchPatientVisits,
} from "../../services/openmrs/clinicalPatient";
import { fetchLaboratoryChart, fetchLinkedExternalLaboratoryOrders } from "../../services/laboratoryBilling";
import type {
  LabOrderSummary,
  LabResultSummary,
  PatientIdentity,
  PatientVisitSummary,
  WorkspaceContext,
} from "../../types";
import type { LaboratoryBoardOrder } from "../../types/laboratoryCatalogue";
import { formatClinicalWhen } from "../../utils/datetime";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import { laboratoryRequestSourceLabel } from "./laboratoryView";
import "./LaboratoryWorkspace.css";

interface LaboratoryPatientWorkspaceProps {
  patientUuid: string;
  context: WorkspaceContext;
}

const FLOW = [
  { id: "orders", label: "Orders" },
  { id: "samples", label: "Samples" },
  { id: "results", label: "Results" },
  { id: "previous", label: "Previous results" },
] as const;

export function LaboratoryPatientWorkspace({
  patientUuid,
}: LaboratoryPatientWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [orders, setOrders] = useState<LabOrderSummary[]>([]);
  const [results, setResults] = useState<LabResultSummary[]>([]);
  const [linkedExternal, setLinkedExternal] = useState<LaboratoryBoardOrder[]>([]);
  const [chartError, setChartError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchLaboratoryChart(patientUuid),
      fetchLinkedExternalLaboratoryOrders(patientUuid).catch(() => ({
        status: "ok" as const,
        items: [] as LaboratoryBoardOrder[],
      })),
    ]).then(([identity, visitResult, chartResult, linkedResult]) => {
      if (cancelled) {
        return;
      }
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      }
      if (visitResult.status === "fulfilled") {
        setVisits(visitResult.value);
      }
      if (chartResult.status === "fulfilled") {
        setChartError("");
        setOrders(
          (chartResult.value.orders || []).map((row) => ({
            uuid: row.uuid,
            orderNumber: row.orderNumber || "—",
            testName: row.testName || "Laboratory order",
            patientUuid: row.patientUuid || patientUuid,
            visitUuid: row.visitUuid || "",
            patientName: "",
            mrn: "",
            ordered: formatClinicalWhen(row.ordered),
            urgency: row.urgency === "STAT" ? "STAT" : row.urgency || "Routine",
            comment: row.comment || "",
            provider: row.provider || "—",
            accession: row.accession || "—",
          })),
        );
        setResults(
          (chartResult.value.results || []).map((row) => ({
            orderUuid: String(row.orderUuid || ""),
            accessionUuid: String(row.accessionUuid || ""),
            testName: String(row.testName || "Laboratory result"),
            panelName: String(row.panelName || ""),
            result: String(row.result || "—"),
            unit: String(row.testUnitOfMeasurement || row.unit || ""),
            minNormal: row.minNormal === null || row.minNormal === undefined || row.minNormal === "" ? "—" : String(row.minNormal),
            maxNormal: row.maxNormal === null || row.maxNormal === undefined || row.maxNormal === "" ? "—" : String(row.maxNormal),
            abnormal: typeof row.abnormal === "boolean" ? row.abnormal : null,
            notes: String(row.notes || ""),
            provider: String(row.provider || "—"),
            resultAt: formatClinicalWhen(typeof row.resultDateTime === "string" || typeof row.resultDateTime === "number" ? row.resultDateTime : ""),
            accessionAt: formatClinicalWhen(
              typeof row.accessionDateTime === "string" || typeof row.accessionDateTime === "number"
                ? row.accessionDateTime
                : "",
            ),
            mappingStatus: "unique",
            mappingMessage: "",
          })),
        );
      } else {
        setOrders([]);
        setResults([]);
        setChartError(
          chartResult.reason instanceof Error
            ? chartResult.reason.message
            : "This patient's laboratory record could not be loaded.",
        );
      }
      if (linkedResult.status === "fulfilled") {
        setLinkedExternal(linkedResult.value.items || []);
      } else {
        setLinkedExternal([]);
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  useEffect(() => {
    const cancel = load();
    return cancel;
  }, [load]);

  const latestVisit = orders.find((order) => order.visitUuid)?.visitUuid || "";
  const currentOrderIds = new Set(
    orders.filter((order) => !latestVisit || order.visitUuid === latestVisit).map((order) => order.uuid),
  );
  const currentResults = results.filter((row) => !row.orderUuid || currentOrderIds.has(row.orderUuid));
  const previousResults = results.filter((row) => row.orderUuid && !currentOrderIds.has(row.orderUuid));

  const openVisit = visits.find((visit) => visit.open);
  const visitLabel = openVisit
    ? `${openVisit.visitType} · ${openVisit.startDate}`
    : visits[0]
      ? `${visits[0].visitType} · ${visits[0].startDate}`
      : undefined;

  return (
    <div className="lab-patient">
      <div className="lab-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/laboratory")}>
          ← Laboratory
        </Button>
        <div className="abikan-account-nav">
          <PatientAccountLink patientUuid={patientUuid} />
          <a href={bahmniUrl(BAHMNI_ROUTES.patientDashboard(patientUuid))}>
            Open full chart
          </a>
        </div>
      </div>

      {patient ? (
        <PatientIdentityHeader
          compact
          patient={patient}
          visitLabel={[visitLabel, "Laboratory"].filter(Boolean).join(" · ")}
        />
      ) : (
        <p className="lab-patient__muted">Loading patient…</p>
      )}

      <div className="abikan-sheet">
      <div className="abikan-sheet__main">
      <LaboratoryFeeCard
        patientUuid={patientUuid}
        patientName={patient?.name}
        patientMrn={patient?.mrn}
      />

      <ClinicalSection
        id="orders"
        title="Laboratory orders"
        description="Tests ordered for this patient."
      >
        {chartError ? (
          <EmptyState title="Orders unavailable" description={chartError} />
        ) : (
          <LabOrderTable
            rows={orders}
            loading={loading}
            showPatient={false}
            openPatientUuid={patientUuid}
            emptyTitle="No laboratory orders"
            emptyDescription="This patient has no laboratory orders yet."
          />
        )}
      </ClinicalSection>

      {linkedExternal.length > 0 ? (
        <ClinicalSection
          id="linked-external"
          title="Linked external laboratory"
          description="Laboratory work done before hospital registration. These orders stay marked as External Patient."
        >
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Test</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Payment</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {linkedExternal.map((row) => (
                  <tr key={row.uuid}>
                    <td>{formatClinicalWhen(row.ordered)}</td>
                    <td>{row.testName}</td>
                    <td>
                      {row.requestSourceLabel ||
                        laboratoryRequestSourceLabel(row.requestSource, row.comment)}
                    </td>
                    <td>{row.laboratoryStatus}</td>
                    <td>
                      <Badge tone={paymentStateTone(row.paymentStatus)}>{row.paymentStatus}</Badge>
                    </td>
                    <td>
                      {row.externalId ? (
                        <button
                          type="button"
                          className="lab-desk__link"
                          onClick={() => openLaboratoryExternalPatient(row.externalId || "")}
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
        </ClinicalSection>
      ) : null}

      <ClinicalSection
        id="samples"
        title="Sample information"
        description="Each test and the sample collected for it."
      >
        {chartError ? (
          <EmptyState title="Samples unavailable" description={chartError} />
        ) : loading ? (
          <p className="lab-patient__muted">Loading samples…</p>
        ) : orders.length === 0 ? (
          <EmptyState title="No samples" description="Samples appear here after a test is ordered." />
        ) : (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Sample</th>
                  <th>Ordered</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.uuid}>
                    <td>{order.testName}</td>
                    <td>{order.accession && order.accession !== "—" ? order.accession : "Waiting for sample"}</td>
                    <td>{order.ordered}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ClinicalSection>

      <ClinicalSection
        id="results"
        title="Results"
        description="Released results. A positive or negative test shows that answer."
      >
        {chartError ? (
          <EmptyState title="Results unavailable" description={chartError} />
        ) : (
          <LabResultTable
            rows={currentResults}
            loading={loading}
            emptyTitle="No laboratory results"
            emptyDescription="No laboratory results on this chart yet."
          />
        )}
      </ClinicalSection>

      <ClinicalSection
        id="previous"
        title="Previous results"
        description="Earlier results for this patient."
      >
        {chartError ? (
          <EmptyState title="Previous results unavailable" description={chartError} />
        ) : (
          <LabResultTable
            rows={previousResults}
            loading={loading}
            emptyTitle="No previous laboratory results"
            emptyDescription="Earlier results will appear here when they exist."
          />
        )}
      </ClinicalSection>
      </div>
      <SectionIndex
        label="Laboratory sections"
        items={
          linkedExternal.length > 0
            ? [{ id: "orders", label: "Orders" }, { id: "linked-external", label: "External" }, ...FLOW.slice(1)]
            : FLOW
        }
      />
      </div>
    </div>
  );
}
