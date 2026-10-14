import { useCallback, useEffect, useState } from "react";
import { openRadiologyExternalStudy, returnToPreviousScreen } from "../../app/hashRoute";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionIndex } from "../../components/SectionIndex";
import { RadiologyOrderTable } from "../../components/RadiologyTables";
import {
  fetchPatientIdentity,
  fetchPatientVisits,
} from "../../services/openmrs/clinicalPatient";
import {
  fetchRadiologyNotes,
  fetchRadiologyOrders,
  fetchRadiologyOrdersForVisit,
} from "../../services/openmrs/radiology";
import {
  fetchLinkedExternalRadiologyStudies,
  fetchRadiologyCharge,
} from "../../services/radiologyBilling";
import type {
  PatientIdentity,
  PatientVisitSummary,
  RadiologyNoteSummary,
  RadiologyOrderSummary,
  WorkspaceContext,
} from "../../types";
import type { RadiologyWorklistRow } from "../../types/radiologyBilling";
import { formatClinicalWhen } from "../../utils/datetime";
import { radiologyBillingStatus } from "./radiologyOrder";
import {
  NO_RADIOLOGY_ORDERS,
  NO_RADIOLOGY_ORDERS_HELP,
  radiologyPaymentTone,
  radiologyRequestSourceLabel,
} from "./radiologyDesk";
import "./RadiologyWorkspace.css";

interface RadiologyPatientWorkspaceProps {
  patientUuid: string;
  context: WorkspaceContext;
}

export function RadiologyPatientWorkspace({
  patientUuid,
}: RadiologyPatientWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [orders, setOrders] = useState<RadiologyOrderSummary[]>([]);
  const [notes, setNotes] = useState<RadiologyNoteSummary[]>([]);
  const [linkedExternal, setLinkedExternal] = useState<RadiologyWorklistRow[]>([]);
  const [ordersUnavailable, setOrdersUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setPatient(null);
    setOrders([]);
    setNotes([]);
    setLinkedExternal([]);
    setOrdersUnavailable(false);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchRadiologyOrders(patientUuid),
      fetchRadiologyNotes(patientUuid),
      fetchRadiologyCharge(patientUuid).catch(() => null),
      fetchLinkedExternalRadiologyStudies(patientUuid).catch(() => ({
        status: "ok" as const,
        items: [] as RadiologyWorklistRow[],
      })),
    ]).then(
      async ([identity, visitResult, orderResult, noteResult, chargeResult, linkedResult]) => {
        if (cancelled) {
          return;
        }
        if (identity.status === "fulfilled") {
          setPatient(identity.value);
        }
        const listedVisits: PatientVisitSummary[] =
          visitResult.status === "fulfilled" ? visitResult.value : [];
        const taggedNotes = noteResult.status === "fulfilled" ? noteResult.value : [];
        const charges = chargeResult.status === "fulfilled" ? chargeResult.value : null;
        const exams = charges?.examinations ?? [];
        if (linkedResult.status === "fulfilled") {
          setLinkedExternal(linkedResult.value.items || []);
        }
        const visitOrders = (
          await Promise.all(
            listedVisits.map((visit) =>
              fetchRadiologyOrdersForVisit(patientUuid, visit.uuid).catch(() => []),
            ),
          )
        ).flat();
        const byUuid = new Map(visitOrders.map((row) => [row.uuid, row]));
        if (orderResult.status === "fulfilled") {
          setOrders(
            orderResult.value.map((row) => {
              const extra = byUuid.get(row.uuid);
              const visit = listedVisits.find(
                (item) => item.uuid === (extra?.visitUuid || row.visitUuid),
              );
              const exam = exams.find((item) => item.orderUuid === row.uuid);
              return {
                ...row,
                ...(extra ?? {}),
                dailyVisitNumber: extra?.dailyVisitNumber || visit?.dailyVisitNumber,
                visitType: extra?.visitType || visit?.visitType || row.visitType,
                billingStatus: exam
                  ? radiologyBillingStatus({
                      hasCharge: exam.hasCharge,
                      paymentStatus: exam.paymentStatus,
                    })
                  : "Price pending",
                feeFormatted: exam?.hasCharge ? exam.feeAmount.formatted : undefined,
              };
            }),
          );
          setOrdersUnavailable(false);
        } else {
          setOrders([]);
          setOrdersUnavailable(true);
        }
        if (noteResult.status === "fulfilled") {
          setNotes(taggedNotes);
        } else {
          setNotes([]);
        }
        if (!cancelled) {
          setLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  useEffect(() => {
    const cancel = load();
    return cancel;
  }, [load]);

  return (
    <div className="rad-patient">
      <div className="rad-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/radiology")}>
          ← Radiology
        </Button>
      </div>

      {patient ? (
        <PatientIdentityHeader compact patient={patient} />
      ) : (
        <p className="rad-patient__muted">Loading patient…</p>
      )}

      <div className="abikan-sheet">
      <div className="abikan-sheet__main">
      <ClinicalSection
        id="orders"
        title="Imaging History"
        description="Doctor orders and Radiology Direct studies for this patient. Open a study to set the price or write the report."
      >
        {ordersUnavailable ? (
          <EmptyState
            title="Orders unavailable"
            description="Orders could not be loaded. Try again in a moment."
          />
        ) : (
          <RadiologyOrderTable
            rows={orders}
            notes={notes}
            patientUuid={patientUuid}
            loading={loading}
            showPatient={false}
            emptyTitle={NO_RADIOLOGY_ORDERS}
            emptyDescription={NO_RADIOLOGY_ORDERS_HELP}
          />
        )}
      </ClinicalSection>

      {linkedExternal.length > 0 ? (
        <ClinicalSection
          id="linked-external"
          title="Linked external imaging"
          description="Imaging done before hospital registration. These studies stay marked as External Patient."
        >
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Study</th>
                  <th>Source</th>
                  <th>Report</th>
                  <th>Payment</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {linkedExternal.map((row) => (
                  <tr key={row.uuid}>
                    <td>{formatClinicalWhen(row.ordered)}</td>
                    <td>{row.investigation}</td>
                    <td>
                      {row.requestSourceLabel ||
                        radiologyRequestSourceLabel(row.requestSource, row.comment)}
                    </td>
                    <td>{row.reportStatus}</td>
                    <td>
                      <Badge tone={radiologyPaymentTone(row.billingStatus)}>
                        {row.billingStatus}
                      </Badge>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="rad-link"
                        onClick={() => openRadiologyExternalStudy(row.studyId || row.uuid)}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ClinicalSection>
      ) : null}
      </div>
      <SectionIndex
        label="Radiology sections"
        items={
          linkedExternal.length > 0
            ? [
                { id: "orders", label: "Imaging" },
                { id: "linked-external", label: "External imaging" },
              ]
            : [{ id: "orders", label: "Imaging" }]
        }
      />
      </div>
    </div>
  );
}
