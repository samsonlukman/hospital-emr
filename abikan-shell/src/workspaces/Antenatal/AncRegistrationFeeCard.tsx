import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createAncCharge,
  fetchAncCharge,
  newAncRequestId,
} from "../../services/antenatal";
import type { AncChargePayload } from "../../types/antenatal";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import {
  ANC_FEE_SYMBOL,
  defaultAncFeeInput,
  formatAncFeeAmount,
  parseAncFeeAmount,
} from "./antenatalView";
import "../Doctor/ConsultationFeeCard.css";

interface AncRegistrationFeeCardProps {
  patientUuid: string;
  pregnancyId: string | null | undefined;
  patientName?: string;
  patientMrn?: string;
  amountDraft?: string;
  onAmountDraftChange?: (value: string) => void;
  defaultAmount?: number;
  /** When false, hide the card entirely. */
  visible?: boolean;
  onChargeChange?: (charge: AncChargePayload | null) => void;
}

export function AncRegistrationFeeCard({
  patientUuid,
  pregnancyId,
  patientName,
  patientMrn,
  amountDraft,
  onAmountDraftChange,
  defaultAmount,
  visible = true,
  onChargeChange,
}: AncRegistrationFeeCardProps) {
  const [charge, setCharge] = useState<AncChargePayload | null>(null);
  const [internalAmount, setInternalAmount] = useState(() => defaultAncFeeInput(defaultAmount));
  const [loading, setLoading] = useState(Boolean(pregnancyId));
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [requestId, setRequestId] = useState(newAncRequestId);

  const amountInput = amountDraft !== undefined ? amountDraft : internalAmount;
  const setAmountInput = onAmountDraftChange || setInternalAmount;
  const parsedAmount = parseAncFeeAmount(amountInput);

  const applyCharge = (payload: AncChargePayload | null) => {
    setCharge(payload);
    onChargeChange?.(payload);
  };

  const load = () => {
    if (!pregnancyId) {
      applyCharge(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetchAncCharge(patientUuid, pregnancyId)
      .then((payload) => {
        applyCharge(payload);
        if (amountDraft === undefined) {
          setInternalAmount(defaultAncFeeInput(payload.defaultAmount ?? defaultAmount));
        }
        setLoading(false);
      })
      .catch((reason) => {
        applyCharge(null);
        setError(
          reason instanceof Error ? reason.message : "Unable to load the antenatal registration fee.",
        );
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
    setConfirming(false);
    setRequestId(newAncRequestId());
  }, [patientUuid, pregnancyId]);

  useEffect(() => {
    if (amountDraft === undefined && defaultAmount != null && !pregnancyId) {
      setInternalAmount(defaultAncFeeInput(defaultAmount));
    }
  }, [defaultAmount, amountDraft, pregnancyId]);

  if (!visible) {
    return null;
  }

  const cardExpired = Boolean(charge?.cardExpired);
  const cardEnabled = charge?.cardEnabled !== false && !cardExpired;
  const alreadyRegistered = Boolean(
    !cardExpired && (charge?.alreadyRegistered || charge?.hasCharge || charge?.alreadyCreated),
  );
  const paid = Boolean(charge?.hasCharge && charge.paymentStatus === "PAID");
  const unpaid = Boolean(charge?.hasCharge && charge.paymentStatus === "UNPAID");
  const canCreate = Boolean(pregnancyId && charge?.canCreate && (!alreadyRegistered || cardExpired));
  const showAmountField = Boolean(pregnancyId) && (canCreate || !charge);
  const renewing = cardExpired;

  const openConfirm = () => {
    if (!parsedAmount.ok) {
      setError(parsedAmount.message);
      return;
    }
    setError(null);
    setConfirming(true);
  };

  const submit = async () => {
    const amount = parseAncFeeAmount(amountInput);
    if (!pregnancyId || submitting) {
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
      const payload = await createAncCharge(patientUuid, pregnancyId, requestId, amount.amount);
      applyCharge(payload);
      setConfirming(false);
      setRequestId(newAncRequestId());
    } catch (reason) {
      if (reason instanceof PatientAccountRequestError && reason.code === "charge_in_progress") {
        load();
        setConfirming(false);
        return;
      }
      setError(
        reason instanceof Error
          ? reason.message
          : "The antenatal registration fee could not be created.",
      );
      setConfirming(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="consult-fee">
      <SectionHeader
        title={renewing ? "Enable antenatal card" : "Antenatal registration fee"}
        description={
          renewing
            ? "The card is disabled one year after it was created. Enable the card to create a new fee. Payment is collected at Accountant."
            : "Fee for this antenatal card. The card stays enabled for one year from the date it was created. Payment is collected at Accountant."
        }
      />
      {loading ? <LoadingState variant="inline" label="Loading fee…" /> : null}
      {!loading && error && !charge ? <p className="consult__muted">{error}</p> : null}
      {!loading && error && charge ? (
        <Alert tone="danger" title="Could not create the fee">
          <p>{error}</p>
        </Alert>
      ) : null}
      {cardExpired && !paid ? (
        <Alert tone="warning" title="Card disabled">
          <p>
            Pay the antenatal fee to enable this card for another year
            {charge?.expiresAtLabel ? ` (expired ${charge.expiresAtLabel})` : ""}.
          </p>
        </Alert>
      ) : null}
      {paid && cardEnabled ? (
        <Alert tone="success" title="Payment received">
          <p>The antenatal card fee has been paid. The card is enabled.</p>
        </Alert>
      ) : null}
      {paid && cardExpired ? (
        <Alert tone="success" title="Payment received">
          <p>Payment received. Refresh if the card is still marked disabled.</p>
        </Alert>
      ) : null}
      {unpaid ? (
        <Alert tone="warning" title="Payment required">
          <p>Please proceed to the cashier to enable the antenatal card.</p>
        </Alert>
      ) : null}
      {!loading && alreadyRegistered && !paid && !unpaid && !cardExpired ? (
        <Alert tone="success" title="Antenatal fee registered">
          <p>
            This card already has its antenatal fee for the current year
            {charge?.expiresAtLabel ? ` (enabled until ${charge.expiresAtLabel})` : ""}.
          </p>
        </Alert>
      ) : null}

      {!loading ? (
        <>
          {!pregnancyId ? (
            <p className="consult-fee__block">
              Create the antenatal card first, then set this fee.
            </p>
          ) : null}

          {pregnancyId && showAmountField && canCreate ? (
            <div className="abikan-field consult-fee__amount">
              <label htmlFor="anc-fee-amount">
                {renewing ? "Enable-card fee" : "Antenatal registration fee"}
              </label>
              <div className="consult-fee__input">
                <span aria-hidden="true">{ANC_FEE_SYMBOL}</span>
                <input
                  id="anc-fee-amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={amountInput}
                  onChange={(event) => setAmountInput(event.target.value)}
                  placeholder="2000"
                  aria-describedby="anc-fee-currency"
                />
              </div>
              <p id="anc-fee-currency" className="consult-fee__currency">
                Amount is in Nigerian naira (NGN). Default is ₦2,000.
              </p>
            </div>
          ) : null}

          {pregnancyId && (alreadyRegistered || unpaid || (charge?.hasCharge && renewing)) && charge ? (
            <dl className="consult-fee__facts">
              <div>
                <dt>{renewing ? "Enable-card fee" : "Antenatal registration fee"}</dt>
                <dd>{charge.feeAmount.formatted}</dd>
              </div>
              <div>
                <dt>Payment</dt>
                <dd>
                  {charge.hasCharge && charge.paymentStatus ? (
                    <Badge tone={paymentStateTone(charge.paymentStatus)}>{charge.paymentStatus}</Badge>
                  ) : (
                    "Registered"
                  )}
                </dd>
              </div>
              {charge.expiresAtLabel ? (
                <div>
                  <dt>{charge.cardEnabled ? "Enabled until" : "Expired"}</dt>
                  <dd>{charge.expiresAtLabel}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}

          {canCreate ? (
            <div className="consult-fee__actions">
              <Button onClick={openConfirm} disabled={submitting || !parsedAmount.ok}>
                {renewing ? "Enable card" : "Create antenatal fee"}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}

      {confirming && pregnancyId && parsedAmount.ok ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="anc-fee-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="anc-fee-title">
              {renewing ? "Enable antenatal card" : "Confirm antenatal registration fee"}
            </h2>
            <p>
              {renewing
                ? "This sends a new antenatal fee to Accountant. The card enables after payment."
                : "This sends the bill to Accountant. Reception does not collect payment."}
            </p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{patientName || "—"}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patientMrn || "—"}</dd>
              </div>
              <div>
                <dt>{renewing ? "Enable-card fee" : "Antenatal registration fee"}</dt>
                <dd>{formatAncFeeAmount(parsedAmount.amount)}</dd>
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

/** @deprecated Use AncRegistrationFeeCard — ANC fee is one-time per pregnancy, not per visit. */
export { AncRegistrationFeeCard as AncVisitFeeCard };
