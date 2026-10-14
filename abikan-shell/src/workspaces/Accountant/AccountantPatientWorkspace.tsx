import { useEffect, useMemo, useState } from "react";
import { openPatientAccount, returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { MoneyStack } from "../../components/MoneyStack";
import { SectionIndex } from "../../components/SectionIndex";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import {
  accountantReceiptHref,
  deleteAccountantBill,
  fetchAccountantDashboard,
  newPaymentRequestId,
  registerAccountantPayment,
  waiveAccountantBills,
} from "../../services/accountant";
import { fetchPatientIdentity } from "../../services/openmrs/clinicalPatient";
import { fetchPatientAccount } from "../../services/patientAccount";
import type { AccountantJournal, AccountantPaymentResult } from "../../types/accountant";
import { formatClinicalWhen } from "../../utils/datetime";
import type { PatientIdentity, WorkspaceContext } from "../../types";
import type { PatientAccountInvoice, PatientAccountPayload } from "../../types/patientAccount";
import { departmentDisplay, journalDisplay, paymentStateTone } from "../PatientAccount/accountBadges";
import {
  MIXED_CURRENCY_MESSAGE,
  accountSummaryAmounts,
  checkPaymentAmount,
  checkDiscountPercentage,
  formatMoneyAmount,
  invoiceCurrencyCode,
  isPayableInvoice,
  isReversedInvoice,
  selectedOutstandingTotal,
  selectionIsSameCurrency,
} from "./accountantHonesty";
import "./AccountantWorkspace.css";

interface AccountantPatientWorkspaceProps {
  patientUuid: string;
  context: WorkspaceContext;
}

function eligibleInvoices(account: PatientAccountPayload | null): PatientAccountInvoice[] {
  return (account?.invoices ?? []).filter(isPayableInvoice);
}

function unregisteredAccountLabel(patientUuid: string): string {
  if (patientUuid.startsWith("pharmacy:")) {
    return "Other buyer";
  }
  if (
    patientUuid.startsWith("cashier:") ||
    patientUuid.startsWith("laboratory:") ||
    patientUuid.startsWith("radiology:")
  ) {
    return "Not registered";
  }
  return "";
}

export function AccountantPatientWorkspace({
  patientUuid,
}: AccountantPatientWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [account, setAccount] = useState<PatientAccountPayload | null>(null);
  const [journals, setJournals] = useState<AccountantJournal[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [amountInput, setAmountInput] = useState("");
  const [discountInput, setDiscountInput] = useState("");
  const [journalId, setJournalId] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [waiveConfirming, setWaiveConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [waiving, setWaiving] = useState(false);
  const [waivedNote, setWaivedNote] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<PatientAccountInvoice | null>(null);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AccountantPaymentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestId, setRequestId] = useState(newPaymentRequestId);

  const applyAccount = (next: PatientAccountPayload) => {
    setAccount(next);
    setDiscountInput("");
    const payable = eligibleInvoices(next);
    if (payable.length === 1) {
      const invoice = payable[0];
      setSelected([invoice.id]);
      setAmountInput(invoice.outstanding.amount.toFixed(invoice.outstanding.decimalPlaces));
    } else {
      setSelected([]);
      setAmountInput("");
    }
  };

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientAccount(patientUuid),
      fetchAccountantDashboard(),
    ]).then(([identity, accountResult, dashboard]) => {
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      }
      if (accountResult.status === "fulfilled") {
        applyAccount(accountResult.value);
      } else {
        setAccount(null);
        setError(
          accountResult.reason instanceof Error
            ? accountResult.reason.message
            : "Unable to load this patient's bills.",
        );
      }
      if (dashboard.status === "fulfilled") {
        const nextJournals = dashboard.value.journals ?? [];
        setJournals(nextJournals);
        setJournalId((current) => current ?? nextJournals[0]?.id ?? null);
      }
      setLoading(false);
    });
  };

  useEffect(() => {
    load();
    setResult(null);
    setWaivedNote("");
    setRequestId(newPaymentRequestId());
  }, [patientUuid]);

  const payable = useMemo(() => eligibleInvoices(account), [account]);
  const closed = useMemo(
    () =>
      (account?.invoices ?? []).filter(
        (invoice) => invoice.state !== "cancel" && !payable.some((row) => row.id === invoice.id),
      ),
    [account, payable],
  );
  const settled = closed.filter((invoice) => !isReversedInvoice(invoice));
  const waived = settled.filter((invoice) => invoice.paymentStateLabel.toUpperCase().includes("WAIVED"));
  const paidClosed = settled.filter((invoice) => !invoice.paymentStateLabel.toUpperCase().includes("WAIVED"));
  const reversed = closed.filter(isReversedInvoice);
  const selectedInvoices = payable.filter((invoice) => selected.includes(invoice.id));
  const sameCurrency = selectionIsSameCurrency(selectedInvoices);
  const selectedDue = selectedOutstandingTotal(selectedInvoices);
  const currency = sameCurrency ? selectedInvoices[0]?.outstanding : undefined;
  const places = currency?.decimalPlaces ?? 2;
  const discountCheck = checkDiscountPercentage(discountInput, selectedDue, places);
  const discountedDue =
    discountCheck.ok ? Math.max(0, selectedDue - discountCheck.amount) : selectedDue;
  const paymentCheck = checkPaymentAmount(amountInput, discountedDue, places);
  const parsedAmount = paymentCheck.ok ? paymentCheck.amount : Number(amountInput);
  const amountReady =
    sameCurrency &&
    selectedInvoices.length > 0 &&
    discountCheck.ok &&
    paymentCheck.ok &&
    journalId != null;

  const waiveSelected = async () => {
    if (!sameCurrency || selectedInvoices.length === 0 || waiving) {
      return;
    }
    setWaiving(true);
    setError(null);
    try {
      const payload = await waiveAccountantBills({
        patientUuid,
        invoiceIds: selectedInvoices.map((invoice) => invoice.id),
        expectedResiduals: Object.fromEntries(
          selectedInvoices.map((invoice) => [String(invoice.id), invoice.outstanding.amount]),
        ),
      });
      setWaiveConfirming(false);
      setResult(null);
      setWaivedNote("The selected bill was waived. No payment was collected.");
      if (payload.account) {
        applyAccount(payload.account);
      } else {
        load();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The bill could not be waived.");
      setWaiveConfirming(false);
    } finally {
      setWaiving(false);
    }
  };

  const toggle = (invoiceId: number) => {
    setSelected((current) => {
      const next = current.includes(invoiceId)
        ? current.filter((id) => id !== invoiceId)
        : [...current, invoiceId];
      const nextInvoices = payable.filter((invoice) => next.includes(invoice.id));
      if (!selectionIsSameCurrency(nextInvoices) || nextInvoices.length === 0) {
        setDiscountInput("");
        setAmountInput("");
        return next;
      }
      const due = selectedOutstandingTotal(nextInvoices);
      const nextPlaces = nextInvoices[0]?.outstanding.decimalPlaces ?? 2;
      setDiscountInput("");
      setAmountInput(due > 0 ? due.toFixed(nextPlaces) : "");
      return next;
    });
  };

  const submit = async () => {
    if (!amountReady || journalId == null || submitting || !sameCurrency) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = await registerAccountantPayment({
        requestId,
        patientUuid,
        invoiceIds: selectedInvoices.map((invoice) => invoice.id),
        discountPercentage: discountCheck.ok ? discountCheck.percentage : 0,
        amount: paymentCheck.ok ? paymentCheck.amount : parsedAmount,
        journalId,
        expectedResiduals: Object.fromEntries(
          selectedInvoices.map((invoice) => [String(invoice.id), invoice.outstanding.amount]),
        ),
      });
      setResult(payload);
      setConfirming(false);
      setRequestId(newPaymentRequestId());
      if (payload.account) {
        applyAccount(payload.account);
      } else {
        load();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Payment was not recorded.");
      setConfirming(false);
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || deleting || deleteReason.trim().length < 3) {
      setDeleteError("Enter why this bill is being deleted.");
      return;
    }
    setDeleting(true);
    setDeleteError("");
    try {
      const payload = await deleteAccountantBill({
        invoiceId: deleteTarget.id,
        reason: deleteReason.trim(),
        patientUuid,
      });
      setDeleteTarget(null);
      setDeleteReason("");
      setSelected((current) => current.filter((id) => id !== deleteTarget.id));
      if (payload.account) {
        applyAccount(payload.account);
      } else {
        load();
      }
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "This bill could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  const journal = journals.find((item) => item.id === journalId);

  return (
    <div className="cashier">
      <div className="cashier__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Accountant
        </Button>
        {unregisteredAccountLabel(patientUuid) ? null : (
          <Button variant="ghost" onClick={() => openPatientAccount(patientUuid)}>
            Patient Account
          </Button>
        )}
      </div>

      {patient ? (
        <PatientIdentityHeader compact patient={patient} />
      ) : account?.patient ? (
        <p className="cashier__patient-fallback">
          {account.patient.name}
          {unregisteredAccountLabel(account.patient.uuid)
            ? ` · ${unregisteredAccountLabel(account.patient.uuid)}`
            : account.patient.mrn
              ? ` · ${account.patient.mrn}`
              : ""}
        </p>
      ) : loading ? (
        <p className="cashier__muted">Loading patient…</p>
      ) : null}
      {account?.patient.nhis ? <Badge tone="info">NHIS patient</Badge> : null}

      {loading ? <LoadingState variant="board" label="Loading bills…" /> : null}
      {!loading && error && !account ? (
        <EmptyState title="Unable to load bills" description={error} />
      ) : null}
      {!loading && account?.status === "account_not_found" ? (
        <EmptyState
          title="No bills for this patient"
          description="This patient does not have a billing account yet."
        />
      ) : null}

      {waivedNote ? (
        <Alert tone="success" title="Bill waived">
          <p>{waivedNote}</p>
        </Alert>
      ) : null}

      {result?.success && result.payment ? (
        <Alert tone="success" title="Payment recorded">
          <p>
            {result.patient?.name} · {result.patient?.mrn}
          </p>
          <p>
            {result.payment.reference} · {result.payment.amount.formatted} ·{" "}
            {journalDisplay(result.payment.journal)} · {formatClinicalWhen(result.payment.actedAt)}
          </p>
          {result.payment.discountNote ? <p>{result.payment.discountNote}</p> : null}
          <p>Accountant: {result.payment.recordedBy || result.recordedBy || "—"}</p>
          <p>
            Bills:{" "}
            {result.payment.relatedInvoices.map((item) => item.number).join(", ") || "See receipt"}
          </p>
          <p>
            <a href={accountantReceiptHref(result.payment.id)} target="_blank" rel="noreferrer">
              Print receipt
            </a>
          </p>
        </Alert>
      ) : null}

      {!loading && error && account ? (
        <Alert tone="danger" title="Payment was not recorded">
          {error}
        </Alert>
      ) : null}

      {!loading && account?.summary ? (
        <section className="cashier__kpis" aria-label="Amount due">
          <KpiCard
            label="Amount due"
            value={<MoneyStack amounts={accountSummaryAmounts(account.summary, "outstanding")} />}
            hint={
              payable.length
                ? `${payable.length} unpaid bill${payable.length === 1 ? "" : "s"}`
                : "Nothing waiting to be paid"
            }
            icon="creditCard"
            tone="collection"
          />
          <KpiCard
            label="Already paid"
            value={<MoneyStack amounts={accountSummaryAmounts(account.summary, "paid")} />}
            hint="On posted bills"
            icon="receipt"
            tone="teal"
          />
        </section>
      ) : null}

      {!loading && account && account.status !== "account_not_found" ? (
        <div className="abikan-sheet">
        <div className="abikan-sheet__main">
          <ClinicalSection
            id="unpaid"
            title="Unpaid bills"
            description="Select the bill you are collecting. You cannot change prices here."
          >
            {payable.length === 0 ? (
              <EmptyState
                title="Nothing to collect"
                description="This patient has no unpaid bills."
              />
            ) : (
              <InvoiceTable
                rows={payable}
                selected={selected}
                onToggle={toggle}
                selectable
                onDelete={(invoice) => {
                  setDeleteTarget(invoice);
                  setDeleteReason("");
                  setDeleteError("");
                }}
              />
            )}
          </ClinicalSection>

          {waived.length > 0 ? (
            <ClinicalSection id="waived" title="Waived bills">
              <InvoiceTable rows={waived} selected={[]} onToggle={() => undefined} />
            </ClinicalSection>
          ) : null}

          {paidClosed.length > 0 ? (
            <ClinicalSection id="closed" title="Paid bills">
              <InvoiceTable rows={paidClosed} selected={[]} onToggle={() => undefined} />
            </ClinicalSection>
          ) : null}

          {reversed.length > 0 ? (
            <ClinicalSection id="reversed" title="Reversed bills">
              <InvoiceTable rows={reversed} selected={[]} onToggle={() => undefined} />
            </ClinicalSection>
          ) : null}

          <ClinicalSection
            id="collect"
            title="Payment"
            description="Partial payment is allowed. You cannot take more than the amount due."
          >
            {payable.length === 0 ? (
              <EmptyState title="No unpaid bills." />
            ) : (
              <form
                className="cashier-pay"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (amountReady) {
                    setConfirming(true);
                  }
                }}
              >
                {!sameCurrency && selectedInvoices.length > 1 ? (
                  <Alert tone="warning" title="Cannot collect these together">
                    {MIXED_CURRENCY_MESSAGE}
                  </Alert>
                ) : null}
                <p>
                  Selected: {selectedInvoices.length || 0} bill
                  {selectedInvoices.length === 1 ? "" : "s"} · Due{" "}
                  {sameCurrency && currency ? formatMoneyAmount(selectedDue, currency) : "—"}
                  {sameCurrency && currency && discountCheck.ok && discountCheck.amount > 0
                    ? ` · After ${discountCheck.percentage}% discount ${formatMoneyAmount(discountedDue, currency)}`
                    : ""}
                  {sameCurrency && currency && paymentCheck.ok
                    ? ` · Remaining ${formatMoneyAmount(paymentCheck.remaining, currency)}`
                    : ""}
                </p>
                {sameCurrency && selectedInvoices.length > 0 && !discountCheck.ok ? (
                  <Alert tone="warning" title="Check the discount">
                    {discountCheck.message}
                  </Alert>
                ) : null}
                {sameCurrency && selectedInvoices.length > 0 && amountInput && !paymentCheck.ok ? (
                  <Alert tone="warning" title="Check the amount">
                    {paymentCheck.message}
                  </Alert>
                ) : null}
                <label>
                  Discount (%)
                  <input
                    type="number"
                    min="0"
                    max="99.99"
                    step="0.01"
                    value={discountInput}
                    onChange={(event) => {
                      const next = event.target.value;
                      setDiscountInput(next);
                      const nextCheck = checkDiscountPercentage(next, selectedDue, places);
                      if (nextCheck.ok && currency) {
                        setAmountInput(
                          Math.max(0, selectedDue - nextCheck.amount).toFixed(places),
                        );
                      }
                    }}
                    disabled={selectedInvoices.length === 0}
                  />
                </label>
                <label>
                  Payment amount
                  <input
                    type="number"
                    min="0"
                    step={places === 0 ? "1" : `0.${"1".padStart(places, "0")}`}
                    value={amountInput}
                    onChange={(event) => setAmountInput(event.target.value)}
                    disabled={selectedInvoices.length === 0}
                  />
                </label>
                <label>
                  Payment method
                  <select
                    value={journalId ?? ""}
                    onChange={(event) => setJournalId(Number(event.target.value))}
                  >
                    {journals.map((item) => (
                      <option key={item.id} value={item.id}>
                        {journalDisplay(item.name, item.code)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="cashier-confirm__actions">
                  <Button type="submit" disabled={!amountReady || submitting || waiving}>
                    Review payment
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!sameCurrency || selectedInvoices.length === 0 || submitting || waiving}
                    onClick={() => setWaiveConfirming(true)}
                  >
                    Waive bill
                  </Button>
                </div>
              </form>
            )}
          </ClinicalSection>
        </div>
        <SectionIndex
          label="Payment sections"
          items={[
            { id: "unpaid", label: "Unpaid bills" },
            ...(waived.length > 0 ? [{ id: "waived", label: "Waived bills" }] : []),
            ...(paidClosed.length > 0 ? [{ id: "closed", label: "Paid bills" }] : []),
            ...(reversed.length > 0 ? [{ id: "reversed", label: "Reversed bills" }] : []),
            { id: "collect", label: "Payment" },
          ]}
        />
        </div>
      ) : null}

      {deleteTarget ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-patient-bill-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="delete-patient-bill-title">Delete this bill</h2>
            <p>
              {deleteTarget.number} · {deleteTarget.outstanding.formatted}. No payment has been taken. This cannot
              be undone here.
            </p>
            <label>
              Why is this bill being deleted?
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
                Delete bill
              </Button>
              <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {waiveConfirming ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="waive-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="waive-title">Waive this bill</h2>
            <p>No money will be collected. The whole amount due on the selected bills will be written off.</p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{patient?.name || account?.patient.name}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patient?.mrn || account?.patient.mrn}</dd>
              </div>
              <div>
                <dt>Bills</dt>
                <dd>
                  {selectedInvoices
                    .map((invoice) => `${departmentDisplay(invoice.department)} — ${invoice.number}`)
                    .join(", ")}
                </dd>
              </div>
              <div>
                <dt>Amount written off</dt>
                <dd>{sameCurrency && currency ? formatMoneyAmount(selectedDue, currency) : "—"}</dd>
              </div>
            </dl>
            <div className="cashier-confirm__actions">
              <Button onClick={() => void waiveSelected()} busy={waiving} busyLabel="Waiving bill…">
                Waive bill
              </Button>
              <Button variant="ghost" onClick={() => setWaiveConfirming(false)} disabled={waiving}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {confirming ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="pay-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="pay-title">Confirm payment</h2>
            <p>Check the patient and amount before you continue. This payment cannot be undone here.</p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{patient?.name || account?.patient.name}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patient?.mrn || account?.patient.mrn}</dd>
              </div>
              <div>
                <dt>Bills</dt>
                <dd>
                  {selectedInvoices
                    .map((invoice) => `${departmentDisplay(invoice.department)} — ${invoice.number}`)
                    .join(", ")}
                </dd>
              </div>
              <div>
                <dt>Amount due</dt>
                <dd>{sameCurrency && currency ? formatMoneyAmount(selectedDue, currency) : "—"}</dd>
              </div>
              <div>
                <dt>Discount</dt>
                <dd>
                  {sameCurrency && currency && discountCheck.ok
                    ? formatMoneyAmount(discountCheck.amount, currency)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Payment amount</dt>
                <dd>
                  {sameCurrency && currency && Number.isFinite(parsedAmount)
                    ? formatMoneyAmount(parsedAmount, currency)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Payment method</dt>
                <dd>{journal ? journalDisplay(journal.name, journal.code) : "—"}</dd>
              </div>
            </dl>
            <div className="cashier-confirm__actions">
              <Button onClick={() => void submit()} busy={submitting} busyLabel="Recording payment…">
                Confirm payment
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={submitting}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function InvoiceTable({
  rows,
  selected,
  onToggle,
  selectable = false,
  onDelete,
}: {
  rows: PatientAccountInvoice[];
  selected: number[];
  onToggle: (invoiceId: number) => void;
  selectable?: boolean;
  onDelete?: (invoice: PatientAccountInvoice) => void;
}) {
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            {selectable ? <th>Pay</th> : null}
            <th>Bill</th>
            <th>Department</th>
            <th>Description</th>
            <th>Currency</th>
            <th>Total</th>
            <th>Paid</th>
            <th>Amount due</th>
            <th>Status</th>
            {onDelete ? <th>Action</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((invoice) => (
            <tr key={invoice.id}>
              {selectable ? (
                <td>
                  <input
                    type="checkbox"
                    checked={selected.includes(invoice.id)}
                    onChange={() => onToggle(invoice.id)}
                    aria-label={`Select ${invoice.number}`}
                  />
                </td>
              ) : null}
              <td>{invoice.number}</td>
              <td>{departmentDisplay(invoice.department)}</td>
              <td>
                {invoice.lines.length > 0 ? (
                  <ul className="cashier__bill-lines">
                    {invoice.lines.map((line, index) => (
                      <li key={`${invoice.id}-${index}`}>
                        {line.description || invoice.description}
                        {line.quantity ? ` × ${line.quantity}` : ""}
                        {line.total?.formatted ? ` · ${line.total.formatted}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  invoice.description
                )}
                {invoice.createdBy ? <div className="cashier__muted">Created by {invoice.createdBy}</div> : null}
              </td>
              <td>{invoiceCurrencyCode(invoice) || "—"}</td>
              <td>{invoice.total.formatted}</td>
              <td>{invoice.paid.formatted}</td>
              <td>{invoice.outstanding.formatted}</td>
              <td>
                <Badge tone={paymentStateTone(invoice.paymentStateLabel)}>
                  {invoice.paymentStateLabel}
                </Badge>
                {invoice.waivedBy ? <div className="cashier__muted">{invoice.waivedBy}</div> : null}
              </td>
              {onDelete ? (
                <td>
                  {invoice.paymentState === "not_paid" && invoice.paid.amount <= 0 ? (
                    <Button variant="ghost" onClick={() => onDelete(invoice)}>
                      Delete
                    </Button>
                  ) : (
                    "—"
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
