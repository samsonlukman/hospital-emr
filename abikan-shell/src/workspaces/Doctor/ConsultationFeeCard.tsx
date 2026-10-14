import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createConsultationCharge,
  fetchConsultationCharge,
  newConsultationRequestId,
} from "../../services/consultation";
import type { ConsultationChargePayload } from "../../types/consultation";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import {
  CONSULTATION_FEE_SYMBOL,
  formatConsultationAmountNgn,
  parseConsultationAmount,
} from "./consultationFeeAmount";
import "./ConsultationFeeCard.css";

interface ConsultationFeeCardProps {
  patientUuid: string;
  patientName?: string;
  patientMrn?: string;
  visitUuid?: string;
  readOnly?: boolean;
}

export function ConsultationFeeCard({
  patientUuid,
  patientName,
  patientMrn,
  visitUuid,
  readOnly = false,
}: ConsultationFeeCardProps) {
  const [charge, setCharge] = useState<ConsultationChargePayload | null>(null);
  const [amountInput, setAmountInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [requestId, setRequestId] = useState(newConsultationRequestId);
  const [nhis, setNhis] = useState(false);

  const parsedAmount = parseConsultationAmount(amountInput);

  const load = () => {
    if (!visitUuid) {
      setCharge(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetchConsultationCharge(patientUuid, visitUuid)
      .then((payload) => {
        setCharge(payload);
        setNhis(Boolean(payload.nhis));
        setLoading(false);
      })
      .catch((reason) => {
        setCharge(null);
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to load the consultation fee.",
        );
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
    setAmountInput("");
    setConfirming(false);
    setRequestId(newConsultationRequestId());
  }, [patientUuid, visitUuid]);

  const activeVisitUuid = visitUuid;
  const paid = Boolean(charge?.hasCharge && charge.paymentStatus === "PAID");
  const unpaid = Boolean(charge?.hasCharge && charge.paymentStatus === "UNPAID");

  const openConfirm = () => {
    if (!parsedAmount.ok) {
      setError(parsedAmount.message);
      return;
    }
    setError(null);
    setConfirming(true);
  };

  const submit = async () => {
    const amount = parseConsultationAmount(amountInput);
    if (!activeVisitUuid || submitting) {
      return;
    }
    if (!amount.ok) {
      setError(amount.message);
      setConfirming(false);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = await createConsultationCharge(
        patientUuid,
        activeVisitUuid,
        requestId,
        amount.amount,
      );
      setCharge(payload);
      setNhis(Boolean(payload.nhis));
      setConfirming(false);
      setRequestId(newConsultationRequestId());
    } catch (reason) {
      if (reason instanceof PatientAccountRequestError && reason.code === "charge_in_progress") {
        load();
        setConfirming(false);
        return;
      }
      setError(
        reason instanceof Error
          ? reason.message
          : "The consultation fee could not be created.",
      );
      setConfirming(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="consult-fee">
      {loading ? <LoadingState variant="inline" label="Loading fee…" /> : null}
      {!loading && error && !charge ? (
        <p className="consult-fee__block">{error}</p>
      ) : null}
      {!loading && error && charge ? (
        <p className="consult-fee__block">{error}</p>
      ) : null}
      {!loading && charge ? (
        <>
          {nhis && !charge.hasCharge ? (
            <p className="consult-fee__block">No consultation fee. This patient is covered by NHIS.</p>
          ) : charge.canCreateCharge && !readOnly ? (
            <div className="consult-fee__compose">
              <label htmlFor="consultation-fee-amount">Consultation fee</label>
              <div className="consult-fee__input">
                <span aria-hidden="true">{CONSULTATION_FEE_SYMBOL}</span>
                <input
                  id="consultation-fee-amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={amountInput}
                  onChange={(event) => setAmountInput(event.target.value)}
                  placeholder="0"
                  aria-describedby="consultation-fee-currency"
                />
              </div>
              <p id="consultation-fee-currency" className="consult-fee__currency">
                Amount is in Nigerian naira (NGN).
              </p>
              <Button onClick={openConfirm} disabled={submitting || !parsedAmount.ok}>
                Create fee
              </Button>
            </div>
          ) : (
            <div className="consult-fee__compose">
              <span>Consultation fee</span>
              <strong>{charge.hasCharge ? charge.feeAmount.formatted : "Not billed yet"}</strong>
              {charge.hasCharge ? (
                <Badge tone={paymentStateTone(charge.paymentStatus)}>{charge.paymentStatus}</Badge>
              ) : null}
              {unpaid ? <span>Please proceed to the cashier.</span> : null}
              {paid ? <span>Payment received.</span> : null}
            </div>
          )}
          {!charge.hasCharge && readOnly && !nhis ? (
            <p className="consult-fee__block">No consultation fee recorded for this visit.</p>
          ) : !nhis && !paid && !unpaid && !charge.canCreateCharge && charge.blockReason ? (
            <p className="consult-fee__block">{charge.blockReason}</p>
          ) : null}
        </>
      ) : null}

      {confirming && charge && activeVisitUuid && parsedAmount.ok ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="consult-fee-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="consult-fee-title">Confirm consultation fee</h2>
            <p>This sends the bill to the cashier. Clinical does not collect money.</p>
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
                <dt>Consultation fee</dt>
                <dd>{formatConsultationAmountNgn(parsedAmount.amount)}</dd>
              </div>
            </dl>
            <div className="cashier-confirm__actions">
              <Button onClick={() => void submit()} disabled={submitting}>
                {submitting ? "Creating…" : "Confirm fee"}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={submitting}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
