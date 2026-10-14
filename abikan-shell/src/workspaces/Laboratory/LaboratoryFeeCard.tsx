import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import {
  createLaboratoryCharge,
  fetchLaboratoryCharge,
  newLaboratoryRequestId,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { LaboratoryChargePayload } from "../../types/laboratoryBilling";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import { laboratoryChargesForOrder } from "./laboratoryView";
import "./LaboratoryFeeCard.css";

interface LaboratoryFeeCardProps {
  patientUuid: string;
  patientName?: string;
  patientMrn?: string;
  orderUuid?: string;
}

export function LaboratoryFeeCard({
  patientUuid,
  patientName,
  patientMrn,
  orderUuid,
}: LaboratoryFeeCardProps) {
  const [charge, setCharge] = useState<LaboratoryChargePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [requestId, setRequestId] = useState(newLaboratoryRequestId);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchLaboratoryCharge(patientUuid)
      .then((payload) => {
        setCharge(payload);
        setLoading(false);
      })
      .catch((reason) => {
        setCharge(null);
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to load the laboratory fee.",
        );
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
    setConfirmingId(null);
    setRequestId(newLaboratoryRequestId());
  }, [patientUuid, orderUuid]);

  const tests = charge?.tests ?? [];
  const visible = laboratoryChargesForOrder(tests, orderUuid);
  const shownTotal = visible.reduce((sum, row) => sum + (row.feeAmount?.amount || 0), 0);
  const shownTotalLabel =
    visible.length > 0 && visible.length === tests.length
      ? charge?.feeAmount.formatted
      : `₦${shownTotal.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const scopedPaid =
    visible.length > 0 && visible.every((row) => row.hasCharge && row.paymentStatus === "PAID");
  const unpaid = visible.some(
    (row) =>
      row.hasCharge &&
      (row.paymentStatus === "UNPAID" || row.paymentStatus === "PARTIALLY PAID"),
  );
  const confirming = visible.find((row) => row.orderUuid === confirmingId) ?? null;

  const submit = async (selectedOrderUuid: string) => {
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = await createLaboratoryCharge(patientUuid, requestId, selectedOrderUuid);
      setCharge(payload);
      setConfirmingId(null);
      setRequestId(newLaboratoryRequestId());
    } catch (reason) {
      if (reason instanceof PatientAccountRequestError && reason.code === "charge_in_progress") {
        load();
        setConfirmingId(null);
        return;
      }
      setError(
        reason instanceof Error
          ? reason.message
          : "The bill could not be submitted.",
      );
      setConfirmingId(null);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="lab-fee">
      {loading ? <LoadingState variant="inline" label="Loading fee…" /> : null}
      {!loading && error ? <p className="lab-fee__block">{error}</p> : null}
      {unpaid ? (
        <p className="lab-fee__block">Please proceed to the cashier. Laboratory does not collect money.</p>
      ) : null}
      {!loading && charge ? (
        <>
          {visible.length === 0 ? (
            <p className="lab-fee__block">
              {charge.blockReason || "No laboratory orders on this chart yet."}
            </p>
          ) : (
            <ul className="lab-fee__tests">
              {visible.map((row) => (
                <li key={row.orderUuid}>
                  <div>
                    <strong>{row.testName}</strong>
                    <span>{row.feeAmount.formatted}</span>
                  </div>
                  {row.hasCharge ? (
                    <Badge tone={paymentStateTone(row.paymentStatus)}>{row.paymentStatus}</Badge>
                  ) : (
                    <Button
                      onClick={() => setConfirmingId(row.orderUuid)}
                      disabled={submitting}
                    >
                      Submit bill
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {visible.length > 1 ? (
            <dl className="lab-fee__facts">
              <div>
                <dt>Total</dt>
                <dd>{shownTotalLabel}</dd>
              </div>
              <div>
                <dt>Payment</dt>
                <dd>
                  <Badge tone={paymentStateTone(charge.paymentStatus)}>{charge.paymentStatus}</Badge>
                </dd>
              </div>
            </dl>
          ) : null}
          {!scopedPaid && !unpaid && charge.blockReason && visible.every((row) => row.hasCharge) ? (
            <p className="lab-fee__block">{charge.blockReason}</p>
          ) : null}
        </>
      ) : null}

      {confirming && charge ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="lab-fee-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="lab-fee-title">Submit this bill</h2>
            <p>This sends the bill to the cashier. Laboratory does not collect money.</p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{patientName || charge.patient.name}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patientMrn || charge.patient.mrn}</dd>
              </div>
              <div>
                <dt>{confirming.testName}</dt>
                <dd>{confirming.feeAmount.formatted}</dd>
              </div>
            </dl>
            <div className="cashier-confirm__actions">
              <Button onClick={() => void submit(confirming.orderUuid)} disabled={submitting}>
                {submitting ? "Submitting…" : "Submit bill"}
              </Button>
              <Button variant="ghost" onClick={() => setConfirmingId(null)} disabled={submitting}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
