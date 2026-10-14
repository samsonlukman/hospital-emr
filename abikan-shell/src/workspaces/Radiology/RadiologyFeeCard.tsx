import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import {
  createRadiologyCharge,
  fetchRadiologyCharge,
  newRadiologyRequestId,
} from "../../services/radiologyBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { RadiologyChargePayload } from "../../types/radiologyBilling";
import {
  RADIOLOGY_FEE_SYMBOL,
  formatRadiologyAmountNgn,
  parseRadiologyAmount,
} from "./radiologyPrice";
import {
  NO_PRICE_SET,
  NO_RADIOLOGY_ORDERS_HELP,
  RADIOLOGY_PRICE_HELPER,
  RADIOLOGY_SAVE_PRICE,
  RADIOLOGY_SET_PRICE,
  radiologyPaymentLabel,
  radiologyPaymentTone,
} from "./radiologyDesk";
import "./RadiologyFeeCard.css";

interface RadiologyFeeCardProps {
  patientUuid: string;
  patientName?: string;
  patientMrn?: string;
  orderUuid?: string;
}

export function RadiologyFeeCard({
  patientUuid,
  patientName,
  patientMrn,
  orderUuid,
}: RadiologyFeeCardProps) {
  const [charge, setCharge] = useState<RadiologyChargePayload | null>(null);
  const [amountInput, setAmountInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [requestId, setRequestId] = useState(newRadiologyRequestId);
  const parsedAmount = parseRadiologyAmount(amountInput);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchRadiologyCharge(patientUuid)
      .then((payload) => {
        setCharge(payload);
        setLoading(false);
        setAmountInput("");
      })
      .catch((reason) => {
        setCharge(null);
        setError(
          reason instanceof Error ? reason.message : "Unable to load the radiology price.",
        );
        setLoading(false);
      });
  };

  useEffect(() => {
    setCharge(null);
    setAmountInput("");
    setConfirming(false);
    setError(null);
    setRequestId(newRadiologyRequestId());
    load();
  }, [patientUuid, orderUuid]);

  const examinations = charge?.examinations ?? [];
  const visible = orderUuid
    ? examinations.filter((row) => row.orderUuid === orderUuid)
    : examinations;
  const scopedPaid =
    visible.length > 0 && visible.every((row) => row.hasCharge && row.paymentStatus === "PAID");
  const needsCashier = visible.some(
    (row) =>
      row.hasCharge &&
      (row.paymentStatus === "UNPAID" || row.paymentStatus === "PARTIALLY PAID"),
  );
  const unbilled = visible.filter((row) => !row.hasCharge);
  const canCreate = Boolean(charge?.canCreateCharge && unbilled.length > 0);
  const amountDue =
    visible.find((row) => row.hasCharge && row.outstanding)?.outstanding?.formatted ||
    (needsCashier ? charge?.outstanding?.formatted : undefined);

  const openConfirm = () => {
    if (!parsedAmount.ok) {
      setError(parsedAmount.message);
      return;
    }
    setError(null);
    setConfirming(true);
  };

  const submit = async () => {
    const amount = parseRadiologyAmount(amountInput);
    if (submitting) {
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
      const payload = await createRadiologyCharge(patientUuid, requestId, orderUuid, amount.amount);
      setCharge(payload);
      setConfirming(false);
      setRequestId(newRadiologyRequestId());
    } catch (reason) {
      if (reason instanceof PatientAccountRequestError && reason.code === "charge_in_progress") {
        load();
        setConfirming(false);
        return;
      }
      setError(
        reason instanceof Error ? reason.message : "The price could not be saved.",
      );
      setConfirming(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="rad-fee">
      <SectionHeader
        title="Price"
        description="Accounts collects payment. Writing the report does not require payment."
      />
      {loading ? <LoadingState variant="inline" label="Loading price…" /> : null}
      {!loading && error && !charge ? <p className="rad-patient__muted">{error}</p> : null}
      {!loading && error && charge ? (
        <Alert tone="danger" title="Could not save the price">
          <p>{error}</p>
        </Alert>
      ) : null}
      {scopedPaid ? (
        <Alert tone="success" title="Paid">
          <p>The cashier has collected this fee. Payment does not mean the scan has been done.</p>
        </Alert>
      ) : null}
      {needsCashier ? (
        <Alert tone="warning" title="Unpaid">
          <p>The cashier still needs to collect this fee. You can still write the report.</p>
        </Alert>
      ) : null}
      {!loading && charge ? (
        <>
          {visible.length === 0 ? (
            <p className="rad-fee__block">
              {charge.blockReason || NO_RADIOLOGY_ORDERS_HELP}
            </p>
          ) : (
            <ul className="rad-fee__exams">
              {visible.map((row) => {
                const payment = radiologyPaymentLabel({
                  hasCharge: row.hasCharge,
                  paymentStatus: row.paymentStatus,
                });
                return (
                  <li key={row.orderUuid}>
                    <div>
                      {orderUuid ? null : <strong>{row.examinationName}</strong>}
                      <span>
                        {row.hasCharge ? row.feeAmount.formatted : NO_PRICE_SET}
                      </span>
                    </div>
                    <Badge tone={radiologyPaymentTone(payment)}>{payment}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
          {needsCashier && amountDue ? (
            <p className="rad-fee__block">Amount due: {amountDue}</p>
          ) : null}
          {canCreate ? (
            <div className="rad-fee__amount">
              <label htmlFor="radiology-fee-amount">Price</label>
              <div className="rad-fee__input">
                <span aria-hidden="true">{RADIOLOGY_FEE_SYMBOL}</span>
                <input
                  id="radiology-fee-amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={amountInput}
                  onChange={(event) => setAmountInput(event.target.value)}
                  placeholder="Amount"
                  aria-describedby="radiology-fee-currency"
                />
              </div>
              <p id="radiology-fee-currency" className="rad-fee__currency">
                {RADIOLOGY_PRICE_HELPER}
              </p>
              <div className="rad-fee__actions">
                <Button onClick={openConfirm} disabled={submitting || !parsedAmount.ok}>
                  {RADIOLOGY_SET_PRICE}
                </Button>
              </div>
            </div>
          ) : !scopedPaid && !needsCashier && charge.blockReason ? (
            <p className="rad-fee__block">{charge.blockReason}</p>
          ) : null}
        </>
      ) : null}

      {confirming && charge ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="rad-fee-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="rad-fee-title">Save this price?</h2>
            <p>Accounts will collect payment. Radiology does not collect money.</p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{patientName || charge.patient.name}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patientMrn || charge.patient.mrn}</dd>
              </div>
              {unbilled.map((row) => (
                <div key={row.orderUuid}>
                  <dt>{row.examinationName}</dt>
                  <dd>
                    {parsedAmount.ok ? formatRadiologyAmountNgn(parsedAmount.amount) : "Enter the amount"}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="cashier-confirm__actions">
              <Button onClick={() => void submit()} disabled={submitting}>
                {submitting ? "Saving…" : RADIOLOGY_SAVE_PRICE}
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
