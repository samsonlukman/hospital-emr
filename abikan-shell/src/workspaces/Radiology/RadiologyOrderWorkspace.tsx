import { useEffect, useState } from "react";
import { openRadiologyPatient, returnToPreviousScreen } from "../../app/hashRoute";
import { rejectMismatchedWorklistOrder } from "./radiologyWorklist";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { fetchVisitByUuid } from "../../services/openmrs/clinicalPatient";
import { fetchRadiologyOrder } from "../../services/openmrs/radiology";
import type { PatientVisitSummary, RadiologyOrderSummary, WorkspaceContext } from "../../types";
import { RadiologyFeeCard } from "./RadiologyFeeCard";
import { RadiologyReportPanel } from "./RadiologyReportPanel";
import {
  radiologyDailyVisitNumber,
  radiologyLocationLabel,
  radiologyStaffName,
} from "./radiologyDesk";
import "./RadiologyWorkspace.css";

interface RadiologyOrderWorkspaceProps {
  orderUuid: string;
  expectedPatientUuid?: string;
  expectedVisitUuid?: string;
  context: WorkspaceContext;
}

export function RadiologyOrderWorkspace({
  orderUuid,
  expectedPatientUuid,
  expectedVisitUuid,
  context,
}: RadiologyOrderWorkspaceProps) {
  const [order, setOrder] = useState<RadiologyOrderSummary | null>(null);
  const [visit, setVisit] = useState<PatientVisitSummary | null>(null);
  const [visitMismatch, setVisitMismatch] = useState(false);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setUnavailable(false);
    setVisit(null);
    setVisitMismatch(false);
    setOrder(null);
    fetchRadiologyOrder(orderUuid)
      .then(async (value) => {
        if (cancelled) {
          return;
        }
        setOrder(value);
        if (!value) {
          return;
        }
        if (!value.visitUuid) {
          setVisitMismatch(true);
          return;
        }
        if (
          rejectMismatchedWorklistOrder({
            order: value,
            expectedPatientUuid,
            expectedVisitUuid,
          }) === "mismatch"
        ) {
          setVisitMismatch(true);
          return;
        }
        const visitResult = await fetchVisitByUuid(value.visitUuid);
        if (cancelled) {
          return;
        }
        if (!visitResult || visitResult.patientUuid !== value.patientUuid) {
          setVisit(null);
          setVisitMismatch(true);
          return;
        }
        setVisit(visitResult.visit);
      })
      .catch((error) => {
        console.error("Unable to load radiology order", error);
        if (!cancelled) {
          setOrder(null);
          setUnavailable(true);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [orderUuid, expectedPatientUuid, expectedVisitUuid]);

  const dailyVisit = radiologyDailyVisitNumber(visit?.dailyVisitNumber);
  const visitType = receptionVisitTypeLabel(visit?.visitType || order?.visitType);
  const location = radiologyLocationLabel(visit?.location);
  const orderedBy = radiologyStaffName(order?.provider);

  return (
    <div className="rad-order">
      <div className="rad-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/radiology")}>
          ← Radiology
        </Button>
      </div>

      <PageHeader
        title={order?.investigation || "Radiology order"}
        description="Set the price and write the report. Accounts collects payment."
      />

      <Card>
        {loading ? (
          <LoadingState variant="board" label="Loading order…" />
        ) : unavailable ? (
          <EmptyState
            title="Order unavailable"
            description="This order could not be loaded. Try again in a moment."
          />
        ) : !order ? (
          <EmptyState
            title="This radiology order was not found"
            description="No radiology order was found with this reference."
          />
        ) : visitMismatch ? (
          <EmptyState
            title="This order is not on the selected visit"
            description="Open the order from the patient's radiology list and try again."
          />
        ) : (
          <dl className="rad-order__facts">
            <div>
              <dt>Patient</dt>
              <dd>
                {order.patientUuid ? (
                  <button
                    type="button"
                    className="rad-link"
                    onClick={() => openRadiologyPatient(order.patientUuid)}
                  >
                    {order.patientName}
                  </button>
                ) : (
                  order.patientName
                )}
              </dd>
            </div>
            <div>
              <dt>Hospital number</dt>
              <dd>{order.mrn || "—"}</dd>
            </div>
            {dailyVisit ? (
              <div>
                <dt>Daily visit number</dt>
                <dd>{dailyVisit}</dd>
              </div>
            ) : null}
            {visitType && visitType !== "—" ? (
              <div>
                <dt>Visit type</dt>
                <dd>{visitType}</dd>
              </div>
            ) : null}
            {location ? (
              <div>
                <dt>Location</dt>
                <dd>{location}</dd>
              </div>
            ) : null}
            <div>
              <dt>Order date / time</dt>
              <dd>{order.ordered}</dd>
            </div>
            {order.orderNumber && order.orderNumber !== "—" ? (
              <div>
                <dt>Order number</dt>
                <dd>{order.orderNumber}</dd>
              </div>
            ) : null}
            {order.urgency === "STAT" ? (
              <div>
                <dt>Priority</dt>
                <dd>
                  <Badge tone="danger">STAT</Badge>
                </dd>
              </div>
            ) : null}
            {order.comment ? (
              <div>
                <dt>Clinical indication</dt>
                <dd>{order.comment}</dd>
              </div>
            ) : null}
            {orderedBy !== "—" ? (
              <div>
                <dt>Ordered by</dt>
                <dd>{orderedBy}</dd>
              </div>
            ) : null}
          </dl>
        )}
      </Card>

      {order?.patientUuid && !visitMismatch ? (
        <>
          <RadiologyFeeCard
            patientUuid={order.patientUuid}
            patientName={order.patientName}
            patientMrn={order.mrn}
            orderUuid={order.uuid}
          />
          <Card>
            <RadiologyReportPanel
              order={order}
              visitStartDatetime={visit?.startDatetime || ""}
              locationUuid={context.location.uuid}
              userUuid={context.userUuid}
            />
          </Card>
        </>
      ) : null}
    </div>
  );
}
