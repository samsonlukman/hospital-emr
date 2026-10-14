import { useEffect, useState } from "react";
import { openLaboratoryPatient, readLaboratoryOrderExpectedIdentity, returnToPreviousScreen } from "../../app/hashRoute";
import { Badge } from "../../components/Badge";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import { deleteLaboratoryOrder } from "../../services/laboratoryBilling";
import { fetchLabOrder } from "../../services/openmrs/laboratory";
import { rejectMismatchedLaboratoryOrder } from "./laboratoryWorklist";
import { LaboratoryFeeCard } from "./LaboratoryFeeCard";
import { LaboratoryWorkflowPanel } from "./LaboratoryWorkflowPanel";
import type { LabOrderSummary, WorkspaceContext } from "../../types";
import "./LaboratoryWorkspace.css";

interface LaboratoryOrderWorkspaceProps {
  orderUuid: string;
  expectedPatientUuid?: string;
  expectedVisitUuid?: string;
  context: WorkspaceContext;
}

export function LaboratoryOrderWorkspace({
  orderUuid,
  expectedPatientUuid,
  expectedVisitUuid,
  context,
}: LaboratoryOrderWorkspaceProps) {
  const [order, setOrder] = useState<LabOrderSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [identityMismatch, setIdentityMismatch] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setUnavailable(false);
    setIdentityMismatch(false);
    setOrder(null);
    const identity = readLaboratoryOrderExpectedIdentity();
    fetchLabOrder(orderUuid, identity?.patientUuid, identity?.visitUuid)
      .then((value) => {
        if (cancelled) {
          return;
        }
        if (
          value &&
          rejectMismatchedLaboratoryOrder({
            order: value,
            expectedPatientUuid,
            expectedVisitUuid,
          }) === "mismatch"
        ) {
          setIdentityMismatch(true);
          setOrder(null);
          return;
        }
        setOrder(value);
      })
      .catch((error) => {
        console.error("Unable to load laboratory order", error);
        if (!cancelled) {
          setOrder(null);
          if (error instanceof PatientAccountRequestError && error.status === 409) {
            setIdentityMismatch(true);
            return;
          }
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

  const confirmDelete = async () => {
    if (!order || deleting || deleteReason.trim().length < 3) {
      setDeleteError("Enter why this laboratory order is being deleted.");
      return;
    }
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteLaboratoryOrder({
        orderUuid: order.uuid,
        reason: deleteReason.trim(),
        patientUuid: order.patientUuid,
      });
      returnToPreviousScreen("#/laboratory");
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "This laboratory order could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="lab-order">
      <div className="lab-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/laboratory")}>
          ← Laboratory
        </Button>
        {order?.patientUuid ? <PatientAccountLink patientUuid={order.patientUuid} /> : null}
      </div>

      <PageHeader
        title="Laboratory order"
        description={`Signed in as ${context.displayName}. Sample collection and result entry are done in the laboratory processing system.`}
      />

      <Card>
        {loading ? (
          <LoadingState variant="board" label="Loading order…" />
        ) : identityMismatch ? (
          <EmptyState
            title="Order unavailable"
            description="This order does not match the selected patient or visit. Return to the worklist and open it again."
          />
        ) : unavailable ? (
          <EmptyState
            title="Order unavailable"
            description="This order could not be loaded. Try again in a moment."
          />
        ) : !order ? (
          <EmptyState
            title="This laboratory order was not found"
            description="No laboratory order was found with this reference."
          />
        ) : (
          <>
            <SectionHeader
              title={order.testName}
              description="Sample and result status are not attached yet."
            />
            <dl className="lab-order__facts">
              <div>
                <dt>Patient</dt>
                <dd>
                  {order.patientUuid ? (
                    <button
                      type="button"
                      className="lab-desk__link"
                      onClick={() => openLaboratoryPatient(order.patientUuid)}
                    >
                      {order.patientName}
                    </button>
                  ) : (
                    order.patientName
                  )}
                </dd>
              </div>
              <div>
                <dt>MRN</dt>
                <dd>{order.mrn}</dd>
              </div>
              <div>
                <dt>Age</dt>
                <dd>{order.age || "—"}</dd>
              </div>
              <div>
                <dt>Doctor / provider</dt>
                <dd>{order.provider}</dd>
              </div>
              <div>
                <dt>Order date / time</dt>
                <dd>{order.ordered}</dd>
              </div>
              <div>
                <dt>Investigation</dt>
                <dd>{order.testName}</dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>
                  <Badge tone={order.urgency === "STAT" ? "danger" : "neutral"}>
                    {order.urgency}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt>Clinical indication</dt>
                <dd>{order.comment || "Not recorded on this order"}</dd>
              </div>
              <div>
                <dt>Sample</dt>
                <dd>{order.accession}</dd>
              </div>
              <div>
                <dt>Order number</dt>
                <dd>{order.orderNumber}</dd>
              </div>
            </dl>
            {!order.accession ? (
              <Button
                variant="ghost"
                onClick={() => {
                  setDeleteOpen(true);
                  setDeleteReason("");
                  setDeleteError("");
                }}
              >
                Delete order
              </Button>
            ) : null}
          </>
        )}
      </Card>

      {order ? (
        <LaboratoryWorkflowPanel
          orderUuid={order.uuid}
          patientUuid={order.patientUuid}
          visitUuid={order.visitUuid}
        />
      ) : null}

      {deleteOpen && order ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="lab-order-delete-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="lab-order-delete-title">Delete this laboratory order</h2>
            <p>
              {order.testName} · {order.patientName}. This removes the order from the laboratory list.
            </p>
            <label>
              Why is this order being deleted?
              <textarea
                value={deleteReason}
                rows={3}
                disabled={deleting}
                onChange={(event) => setDeleteReason(event.target.value)}
              />
            </label>
            {deleteError ? <p className="pharm-dialog__error">{deleteError}</p> : null}
            <div className="cashier-confirm__actions">
              <Button onClick={() => void confirmDelete()} busy={deleting} busyLabel="Deleting…">
                Delete order
              </Button>
              <Button variant="ghost" onClick={() => setDeleteOpen(false)} disabled={deleting}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {order?.patientUuid ? (
        <LaboratoryFeeCard
          patientUuid={order.patientUuid}
          patientName={order.patientName}
          patientMrn={order.mrn}
          orderUuid={order.uuid}
        />
      ) : null}
    </div>
  );
}
