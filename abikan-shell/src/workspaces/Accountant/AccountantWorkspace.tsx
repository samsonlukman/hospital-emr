import { useEffect, useMemo, useState } from "react";
import { Undo2 } from "lucide-react";
import { openAccountantPatient, returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { MoneyStack } from "../../components/MoneyStack";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import {
  accountantReceiptHref,
  deleteAccountantBill,
  fetchAccountantDashboard,
  createAccountantBill,
  fetchDeletedBills,
  fetchWaivedBills,
  fetchAccountantOutstanding,
  fetchAccountantPayment,
  fetchAccountantPayments,
  fetchAccountantRefunds,
  moneyAmount,
  newPaymentRequestId,
  refundAccountantPayment,
} from "../../services/accountant";
import type {
  AccountantAttentionRow,
  AccountantDashboard,
  AccountantPaymentRow,
  AccountantRefundRow,
  DeletedBillRow,
  WaivedBillRow,
} from "../../types/accountant";
import { searchPatients } from "../../services/openmrs/patients";
import { parsePatientDisplay } from "../../services/openmrs/clinicalPatient";
import type { PatientSearchHit, WorkspaceContext } from "../../types";
import { formatClinicalWhen, greetingForNow } from "../../utils/datetime";
import { departmentDisplay, journalDisplay, paymentStateTone } from "../PatientAccount/accountBadges";
import {
  HospitalRevenueBreakdown,
  RevenueGeneratedCard,
  RevenuePeriodFilter,
  useDepartmentRevenue,
} from "../shared/DepartmentRevenue";
import "./AccountantWorkspace.css";

const PAGE_SIZE = 25;

function hospitalNumberLabel(row: { mrn?: string; patientUuid?: string | null }): string {
  const account = row.patientUuid || "";
  if (account.startsWith("pharmacy:")) {
    return "Other buyer";
  }
  if (account.startsWith("cashier:")) {
    return "Not registered";
  }
  if (account.startsWith("laboratory:") || account.startsWith("radiology:")) {
    const token = account.slice(account.indexOf(":") + 1);
    if (!row.mrn || row.mrn === token) {
      return "Not registered";
    }
  }
  return row.mrn || "—";
}

interface AccountantWorkspaceProps {
  context: WorkspaceContext;
  section?: string | null;
}

type RefundDialog = {
  payment: AccountantPaymentRow;
  amount: string;
  reason: string;
};

function openSection(hash: string) {
  window.location.hash = hash;
}

function pageLabel(total: number, offset: number, limit: number): string {
  if (total <= 0) {
    return "No records";
  }
  const start = offset + 1;
  const end = Math.min(offset + limit, total);
  return `Showing ${start}–${end} of ${total}`;
}

function DashboardView({
  context,
  dashboard,
  loading,
  error,
}: {
  context: WorkspaceContext;
  dashboard: AccountantDashboard | null;
  loading: boolean;
  error: string | null;
}) {
  const revenue = useDepartmentRevenue();
  const today = dashboard?.today;
  const attention = dashboard?.attention ?? [];
  const recent = dashboard?.recentPayments ?? [];
  const refunds = dashboard?.recentRefunds ?? [];

  return (
    <div className="cashier">
      <PageHeader
        title="Accountant"
        description={`${greetingForNow()}, ${context.displayName}. Collect payments, review outstanding bills, and process refunds.`}
      />

      {loading ? <LoadingState variant="board" label="Loading financial overview…" /> : null}
      {!loading && error ? <ErrorState title="Unable to load the accountant desk." description={error} /> : null}

      {!loading && dashboard ? (
        <>
          <section className="cashier__kpis" aria-label="Today">
            <KpiCard
              label="Collected today"
              value={<MoneyStack amounts={today?.paymentsReceivedByCurrency} />}
              hint={
                today?.paymentCount
                  ? `${today.paymentCount} payment${today.paymentCount === 1 ? "" : "s"}`
                  : "No payments yet today"
              }
              icon="receipt"
              tone="teal"
            />
            <KpiCard
              label="Still unpaid"
              value={<MoneyStack amounts={today?.outstandingByCurrency} />}
              hint={
                today?.outstandingCount
                  ? `${today.outstandingCount} bill${today.outstandingCount === 1 ? "" : "s"} waiting`
                  : "No unpaid bills"
              }
              icon="creditCard"
              tone="collection"
            />
            <KpiCard
              label="Refunds today"
              value={<MoneyStack amounts={today?.refundsByCurrency} />}
              hint={
                today?.refundCount
                  ? `${today.refundCount} refund${today.refundCount === 1 ? "" : "s"}`
                  : "No refunds today"
              }
              icon="fileText"
              tone="collection"
            />
            <KpiCard
              label="Net today"
              value={<MoneyStack amounts={today?.netByCurrency} />}
              hint="Collections minus refunds"
              icon="naira"
              tone="teal"
            />
          </section>

          <div className="cashier__grid">
            <Card id="outstanding">
              <SectionHeader
                title="Outstanding bills"
                description="Newest bills first."
                action={
                  (dashboard.attentionTotal || 0) > attention.length ? (
                    <Button variant="ghost" onClick={() => openSection("#/accountant/outstanding")}>
                      See all →
                    </Button>
                  ) : null
                }
              />
              {attention.length === 0 ? (
                <EmptyState title="No one is waiting to pay" />
              ) : (
                <div className="abikan-table-wrap">
                  <table className="abikan-table">
                    <thead>
                      <tr>
                        <th>Patient</th>
                        <th>Bill</th>
                        <th>Outstanding</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attention.map((row) => (
                        <tr key={row.id}>
                          <td>
                            {row.patientUuid ? (
                              <button
                                type="button"
                                className="cashier__link"
                                onClick={() => openAccountantPatient(row.patientUuid!)}
                              >
                                {row.patientName}
                              </button>
                            ) : (
                              row.patientName
                            )}
                            <div className="cashier__muted">{hospitalNumberLabel(row)}</div>
                            {row.nhis ? <Badge tone="info">NHIS patient</Badge> : null}
                          </td>
                          <td>
                            {row.number}
                            <div className="cashier__muted">{departmentDisplay(row.department)}</div>
                          </td>
                          <td>{row.outstanding.formatted}</td>
                          <td>
                            <Badge tone={paymentStateTone(row.paymentStateLabel)}>
                              {row.paymentStateLabel}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card id="payments">
              <SectionHeader
                title="Recent payments"
                description="Latest receipts."
                action={
                  (dashboard.recentPaymentsTotal || 0) > recent.length ? (
                    <Button variant="ghost" onClick={() => openSection("#/accountant/payments")}>
                      See all →
                    </Button>
                  ) : null
                }
              />
              {recent.length === 0 ? (
                <EmptyState title="No recent payments" />
              ) : (
                <div className="abikan-table-wrap">
                  <table className="abikan-table">
                    <thead>
                      <tr>
                        <th>Receipt</th>
                        <th>Patient</th>
                        <th>Amount</th>
                        <th>Method</th>
                        <th>Accountant</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recent.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <a className="cashier__link" href={accountantReceiptHref(row.id)} target="_blank" rel="noreferrer">
                              {row.reference}
                            </a>
                            <div className="cashier__muted">{formatClinicalWhen(row.actedAt)}</div>
                          </td>
                          <td>{row.patientName}</td>
                          <td>{row.amount.formatted}</td>
                          <td>{journalDisplay(row.journal || row.method)}</td>
                          <td>{row.recordedBy || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card id="refunds">
              <SectionHeader
                title="Recent refunds"
                description="Credit notes across the hospital."
                action={
                  (dashboard.recentRefundsTotal || 0) > refunds.length ? (
                    <Button variant="ghost" onClick={() => openSection("#/accountant/refunds")}>
                      See all →
                    </Button>
                  ) : null
                }
              />
              {refunds.length === 0 ? (
                <EmptyState title="No recent refunds" />
              ) : (
                <div className="abikan-table-wrap">
                  <table className="abikan-table">
                    <thead>
                      <tr>
                        <th>Refund</th>
                        <th>Patient</th>
                        <th>Amount</th>
                        <th>Processed by</th>
                      </tr>
                    </thead>
                    <tbody>
                      {refunds.map((row) => (
                        <tr key={row.id}>
                          <td>
                            {row.reference}
                            <div className="cashier__muted">{formatClinicalWhen(row.actedAt)}</div>
                          </td>
                          <td>{row.patientName}</td>
                          <td>{row.amount.formatted}</td>
                          <td>{row.processedBy || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>

          <RevenuePeriodFilter revenue={revenue} />
          <section className="cashier__kpis" aria-label="Revenue">
            <RevenueGeneratedCard revenue={revenue} />
          </section>
          <HospitalRevenueBreakdown revenue={revenue} />
        </>
      ) : null}
    </div>
  );
}

function OutstandingPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<AccountantAttentionRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [epoch, setEpoch] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<AccountantAttentionRow | null>(null);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void fetchAccountantOutstanding({ q: applied, offset, limit: PAGE_SIZE })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items ?? []);
        setTotal(payload.total ?? 0);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Outstanding bills could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset, epoch]);

  const confirmDelete = async () => {
    if (!deleteTarget || deleting || deleteReason.trim().length < 3) {
      setDeleteError("Enter why this bill is being deleted.");
      return;
    }
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteAccountantBill({
        invoiceId: deleteTarget.id,
        reason: deleteReason.trim(),
        patientUuid: deleteTarget.patientUuid || undefined,
      });
      setDeleteTarget(null);
      setDeleteReason("");
      setEpoch((value) => value + 1);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "This bill could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="cashier">
      <PageHeader
        title="Outstanding"
        description="Bills still waiting for payment, newest first."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      <Card>
        <div className="cashier__filters">
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search patient, hospital number, or bill"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOffset(0);
                setApplied(q.trim());
              }
            }}
          />
          <Button
            onClick={() => {
              setOffset(0);
              setApplied(q.trim());
            }}
          >
            Search
          </Button>
        </div>
        <p className="cashier__muted">{pageLabel(total, offset, PAGE_SIZE)}</p>
        {loading ? <LoadingState variant="board" label="Loading outstanding…" /> : null}
        {error ? <Alert tone="warning" title="Outstanding"><p>{error}</p></Alert> : null}
        {!loading && !error && items.length === 0 ? <EmptyState title="No outstanding bills match." /> : null}
        {!loading && items.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Bill</th>
                  <th>Arrived</th>
                  <th>Total</th>
                  <th>Outstanding</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.patientUuid ? (
                        <button type="button" className="cashier__link" onClick={() => openAccountantPatient(row.patientUuid!)}>
                          {row.patientName}
                        </button>
                      ) : (
                        row.patientName
                      )}
                      <div className="cashier__muted">{hospitalNumberLabel(row)}</div>
                      {row.nhis ? <Badge tone="info">NHIS patient</Badge> : null}
                    </td>
                    <td>
                      {row.number}
                      {row.purpose ? <div className="cashier__muted">{row.purpose}</div> : null}
                      <div className="cashier__muted">{departmentDisplay(row.department)}</div>
                      {row.createdBy ? <div className="cashier__muted">Created by {row.createdBy}</div> : null}
                    </td>
                    <td>{formatClinicalWhen(row.arrivedAt)}</td>
                    <td>{row.total.formatted}</td>
                    <td>{row.outstanding.formatted}</td>
                    <td>
                      <Badge tone={paymentStateTone(row.paymentStateLabel)}>{row.paymentStateLabel}</Badge>
                    </td>
                    <td>
                      {row.paymentState === "not_paid" &&
                      Math.abs(row.outstanding.amount - row.total.amount) < 0.001 ? (
                        <Button
                          variant="ghost"
                          onClick={() => {
                            setDeleteTarget(row);
                            setDeleteReason("");
                            setDeleteError("");
                          }}
                        >
                          Delete
                        </Button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="cashier__pager">
          <Button variant="secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </Button>
          <Button variant="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </Button>
        </div>
      </Card>
      {deleteTarget ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-bill-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="delete-bill-title">Delete this bill</h2>
            <p>
              {deleteTarget.number} for {deleteTarget.patientName} will be removed. No payment has been taken.
              This cannot be undone here.
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
    </div>
  );
}

function PaymentsPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<AccountantPaymentRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<AccountantPaymentRow | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refundDialog, setRefundDialog] = useState<RefundDialog | null>(null);
  const [refundBusy, setRefundBusy] = useState(false);
  const [refundError, setRefundError] = useState("");
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void fetchAccountantPayments({ q: applied, offset, limit: PAGE_SIZE })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items ?? []);
        setTotal(payload.total ?? 0);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Payments could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset, epoch]);

  const openPayment = async (row: AccountantPaymentRow) => {
    setDetailLoading(true);
    setSelected(row);
    try {
      const detail = await fetchAccountantPayment(row.id);
      setSelected(detail.payment);
    } catch {
      /* keep list row */
    } finally {
      setDetailLoading(false);
    }
  };

  const confirmRefund = async () => {
    if (!refundDialog || refundBusy) return;
    setRefundBusy(true);
    setRefundError("");
    try {
      const result = await refundAccountantPayment(refundDialog.payment.id, {
        requestId: newPaymentRequestId(),
        amount: Number(refundDialog.amount),
        reason: refundDialog.reason.trim() || "Payment refund",
      });
      setNotice(result.message || "Refund completed.");
      setRefundDialog(null);
      if (result.payment) {
        setSelected(result.payment);
      }
      setEpoch((value) => value + 1);
    } catch (reason) {
      setRefundError(reason instanceof Error ? reason.message : "This payment could not be refunded.");
    } finally {
      setRefundBusy(false);
    }
  };

  return (
    <div className="cashier">
      <PageHeader
        title="Payments"
        description="Posted receipts. Refund eligible payments from here. Medicine stock returns stay in Pharmacy."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      {notice ? (
        <Alert tone="success" title="Updated">
          <p>{notice}</p>
        </Alert>
      ) : null}
      <div className={`cashier__split${selected ? " is-open" : ""}`}>
        <Card>
          <div className="cashier__filters">
            <input
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Search receipt, patient, or hospital number"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  setOffset(0);
                  setApplied(q.trim());
                }
              }}
            />
            <Button
              onClick={() => {
                setOffset(0);
                setApplied(q.trim());
              }}
            >
              Search
            </Button>
          </div>
          <p className="cashier__muted">{pageLabel(total, offset, PAGE_SIZE)}</p>
          {loading ? <LoadingState variant="board" label="Loading payments…" /> : null}
          {error ? <Alert tone="warning" title="Payments"><p>{error}</p></Alert> : null}
          {!loading && items.length > 0 ? (
            <div className="abikan-table-wrap">
              <table className="abikan-table">
                <thead>
                  <tr>
                    <th>Receipt</th>
                    <th>Patient</th>
                    <th>Amount</th>
                    <th>Accountant</th>
                    <th>Status</th>
                    <th> </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row) => (
                    <tr key={row.id} className={selected?.id === row.id ? "is-selected" : undefined}>
                      <td>
                        <button type="button" className="cashier__link" onClick={() => void openPayment(row)}>
                          {row.reference}
                        </button>
                        <div className="cashier__muted">{formatClinicalWhen(row.actedAt)}</div>
                      </td>
                      <td>{row.patientName}</td>
                      <td>{row.amount.formatted}</td>
                      <td>{row.recordedBy || "—"}</td>
                      <td>
                        <Badge tone={paymentStateTone(row.refundStatus || "PAID")}>
                          {row.refundStatus || "Paid"}
                        </Badge>
                      </td>
                      <td>
                        {row.canRefund ? (
                          <button
                            type="button"
                            className="cashier__refund"
                            title="Refund payment"
                            aria-label={`Refund ${row.reference}`}
                            onClick={() => {
                              setRefundError("");
                              setRefundDialog({
                                payment: row,
                                amount: String(row.amountRefundable ?? moneyAmount(row.amount)),
                                reason: "",
                              });
                            }}
                          >
                            <Undo2 size={16} strokeWidth={1.75} aria-hidden="true" />
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="cashier__pager">
            <Button variant="secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <Button variant="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        </Card>

        {selected ? (
          <Card className="cashier__detail">
            <SectionHeader
              title={selected.reference}
              description="Payment detail"
              action={
                <Button variant="ghost" onClick={() => setSelected(null)}>
                  Close
                </Button>
              }
            />
            {detailLoading ? <LoadingState variant="board" label="Loading payment…" /> : null}
            <dl className="cashier__facts">
              <div>
                <dt>Patient</dt>
                <dd>
                  {selected.patientUuid ? (
                    <button type="button" className="cashier__link" onClick={() => openAccountantPatient(selected.patientUuid!)}>
                      {selected.patientName}
                    </button>
                  ) : (
                    selected.patientName
                  )}
                </dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>{selected.amount.formatted}</dd>
              </div>
              {selected.discountNote ? (
                <div>
                  <dt>Discount</dt>
                  <dd>{selected.discountNote}</dd>
                </div>
              ) : null}
              <div>
                <dt>Method</dt>
                <dd>{journalDisplay(selected.journal || selected.method)}</dd>
              </div>
              <div>
                <dt>Paid</dt>
                <dd>{formatClinicalWhen(selected.actedAt)}</dd>
              </div>
              <div>
                <dt>Accountant</dt>
                <dd>{selected.recordedBy || "—"}</dd>
              </div>
              <div>
                <dt>Refund status</dt>
                <dd>{selected.refundStatus || "Paid"}</dd>
              </div>
            </dl>
            {selected.relatedInvoices?.length ? (
              <p className="cashier__muted">
                Bills: {selected.relatedInvoices.map((item) => item.number).join(", ")}
              </p>
            ) : null}
            <div className="cashier__detail-actions">
              <a className="abikan-button abikan-button--secondary" href={accountantReceiptHref(selected.id)} target="_blank" rel="noreferrer">
                Print receipt
              </a>
              {selected.canRefund ? (
                <Button
                  variant="secondary"
                  onClick={() =>
                    setRefundDialog({
                      payment: selected,
                      amount: String(selected.amountRefundable ?? moneyAmount(selected.amount)),
                      reason: "",
                    })
                  }
                >
                  Refund payment
                </Button>
              ) : null}
            </div>
          </Card>
        ) : null}
      </div>

      {refundDialog ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="acct-refund-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="acct-refund-title">Refund payment?</h2>
            <p>Receipt: {refundDialog.payment.reference}</p>
            <p>Patient: {refundDialog.payment.patientName}</p>
            <p>Original payment: {refundDialog.payment.amount.formatted}</p>
            <label>
              Refund amount
              <input
                type="number"
                min={0.01}
                max={refundDialog.payment.amountRefundable ?? moneyAmount(refundDialog.payment.amount)}
                step="any"
                value={refundDialog.amount}
                disabled={refundBusy}
                onChange={(event) => setRefundDialog({ ...refundDialog, amount: event.target.value })}
              />
            </label>
            <label>
              Reason
              <input
                value={refundDialog.reason}
                disabled={refundBusy}
                onChange={(event) => setRefundDialog({ ...refundDialog, reason: event.target.value })}
                placeholder="Why is this being refunded?"
              />
            </label>
            <p>
              This will reverse the financial amount and mark the payment as refunded. It does not return pharmacy
              stock.
            </p>
            {refundError ? <p className="pharm-dialog__error">{refundError}</p> : null}
            <div className="cashier-confirm__actions">
              <Button variant="secondary" disabled={refundBusy} onClick={() => setRefundDialog(null)}>
                Cancel
              </Button>
              <Button variant="primary" busy={refundBusy} busyLabel="Refunding…" onClick={() => void confirmRefund()}>
                Confirm refund
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RefundsPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<AccountantRefundRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void fetchAccountantRefunds({ q: applied, offset, limit: PAGE_SIZE })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items ?? []);
        setTotal(payload.total ?? 0);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Refunds could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset]);

  return (
    <div className="cashier">
      <PageHeader
        title="Refunds"
        description="Hospital credit notes, including Pharmacy and Accountant refunds."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      <Card>
        <div className="cashier__filters">
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search refund, patient, or reference"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOffset(0);
                setApplied(q.trim());
              }
            }}
          />
          <Button
            onClick={() => {
              setOffset(0);
              setApplied(q.trim());
            }}
          >
            Search
          </Button>
        </div>
        <p className="cashier__muted">{pageLabel(total, offset, PAGE_SIZE)}</p>
        {loading ? <LoadingState variant="board" label="Loading refunds…" /> : null}
        {error ? <Alert tone="warning" title="Refunds"><p>{error}</p></Alert> : null}
        {!loading && items.length === 0 ? <EmptyState title="No refunds match." /> : null}
        {!loading && items.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Refund</th>
                  <th>Patient</th>
                  <th>Amount</th>
                  <th>Source</th>
                  <th>Processed by</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.reference}
                      <div className="cashier__muted">{formatClinicalWhen(row.actedAt)}</div>
                    </td>
                    <td>
                      {row.patientName}
                      <div className="cashier__muted">{row.mrn || "—"}</div>
                    </td>
                    <td>{row.amount.formatted}</td>
                    <td>{row.source === "pharmacy" ? "Pharmacy" : "Accountant"}</td>
                    <td>{row.processedBy || "—"}</td>
                    <td>{row.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="cashier__pager">
          <Button variant="secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </Button>
          <Button variant="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </Button>
        </div>
      </Card>
    </div>
  );
}

function RevenuePage() {
  const revenue = useDepartmentRevenue();
  return (
    <div className="cashier">
      <PageHeader
        title="Revenue"
        description="Hospital revenue by department from posted bills, net of credit notes."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      <RevenuePeriodFilter revenue={revenue} />
      <section className="cashier__kpis" aria-label="Revenue">
        <RevenueGeneratedCard revenue={revenue} />
      </section>
      <HospitalRevenueBreakdown revenue={revenue} />
    </div>
  );
}

function DeletedBillsPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<DeletedBillRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void fetchDeletedBills({ q: applied, offset, limit: PAGE_SIZE })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items ?? []);
        setTotal(payload.total ?? 0);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Deleted bills could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset]);

  return (
    <div className="cashier">
      <PageHeader
        title="Deleted bills"
        description="Unpaid bills removed by an accountant, with the reason and who deleted them."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      <Card>
        <div className="cashier__filters">
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search patient, bill, or reason"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOffset(0);
                setApplied(q.trim());
              }
            }}
          />
          <Button
            onClick={() => {
              setOffset(0);
              setApplied(q.trim());
            }}
          >
            Search
          </Button>
        </div>
        <p className="cashier__muted">{pageLabel(total, offset, PAGE_SIZE)}</p>
        {loading ? <LoadingState variant="board" label="Loading deleted bills…" /> : null}
        {error ? (
          <Alert tone="warning" title="Deleted bills">
            <p>{error}</p>
          </Alert>
        ) : null}
        {!loading && !error && items.length === 0 ? <EmptyState title="No deleted bills match." /> : null}
        {!loading && items.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Patient</th>
                  <th>Bill</th>
                  <th>Amount</th>
                  <th>Deleted by</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td>{formatClinicalWhen(row.deletedAt)}</td>
                    <td>
                      {row.patientName}
                      <div className="cashier__muted">{row.hospitalNumber || "—"}</div>
                    </td>
                    <td>
                      {row.billNumber}
                      <div className="cashier__muted">{departmentDisplay(row.department)}</div>
                    </td>
                    <td>{row.amount}</td>
                    <td>{row.deletedBy}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="cashier__pager">
          <Button variant="secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </Button>
          <Button variant="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </Button>
        </div>
      </Card>
    </div>
  );
}

function WaivedBillsPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<WaivedBillRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void fetchWaivedBills({ q: applied, offset, limit: PAGE_SIZE })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items ?? []);
        setTotal(payload.total ?? 0);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Waived bills could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset]);

  return (
    <div className="cashier">
      <PageHeader
        title="Waived bills"
        description="Bills written off by an accountant, including NHIS patients. No money was collected."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      <Card>
        <div className="cashier__filters">
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search patient, bill, or accountant"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOffset(0);
                setApplied(q.trim());
              }
            }}
          />
          <Button
            variant="secondary"
            onClick={() => {
              setOffset(0);
              setApplied(q.trim());
            }}
          >
            Search
          </Button>
        </div>
        {loading ? <LoadingState variant="board" label="Loading waived bills…" /> : null}
        {error ? (
          <Alert tone="warning" title="Waived bills">
            <p>{error}</p>
          </Alert>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="No waived bills." description="Waived bills appear here with the patient, amount, and accountant." />
        ) : null}
        {!loading && items.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Patient</th>
                  <th>Bill</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Accountant</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.invoiceId}>
                    <td>{row.waivedAt ? formatClinicalWhen(row.waivedAt) : "—"}</td>
                    <td>
                      {row.patientUuid ? (
                        <button type="button" className="cashier__link" onClick={() => openAccountantPatient(row.patientUuid!)}>
                          {row.patientName}
                        </button>
                      ) : (
                        row.patientName
                      )}
                      <div className="cashier__muted">{row.hospitalNumber || "—"}</div>
                    </td>
                    <td>{row.billNumber}</td>
                    <td>{row.amount}</td>
                    <td>
                      <Badge tone={paymentStateTone(row.statusLabel)}>{row.statusLabel}</Badge>
                    </td>
                    <td>{row.waivedBy || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="cashier__pager">
          <Button variant="secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </Button>
          <Button
            variant="secondary"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </Card>
    </div>
  );
}

function CreateBillPage() {
  const [kind, setKind] = useState<"registered" | "unregistered">("registered");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [patient, setPatient] = useState<PatientSearchHit | null>(null);
  const [unregisteredName, setUnregisteredName] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{
    billNumber: string;
    amount: string;
    description: string;
    createdBy: string;
    patientName: string;
    patientUuid: string;
  } | null>(null);

  useEffect(() => {
    if (kind !== "registered" || patient || query.trim().length < 2) {
      setHits([]);
      setSearching(false);
      return;
    }
    const handle = window.setTimeout(() => {
      setSearching(true);
      void searchPatients(query)
        .then((results) => setHits(results))
        .catch(() => setHits([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, patient, kind]);

  const patientLabel = patient ? parsePatientDisplay(patient.display) : null;
  const amountValue = Number(amount);
  const amountReady = amount.trim() !== "" && Number.isFinite(amountValue) && amountValue > 0;
  const personReady = kind === "registered" ? Boolean(patient) : unregisteredName.trim().length >= 2;
  const ready = personReady && amountReady && description.trim().length >= 3;
  const billingName = kind === "registered" ? patientLabel?.name || "" : unregisteredName.trim();

  const submit = () => {
    if (!ready) return;
    setBusy(true);
    setError("");
    void createAccountantBill({
      patientUuid: kind === "registered" ? patient?.uuid : undefined,
      patientName: kind === "unregistered" ? unregisteredName.trim() : undefined,
      amount: amount.trim(),
      description: description.trim(),
      requestId: newPaymentRequestId(),
    })
      .then((result) => {
        setCreated({
          billNumber: result.billNumber,
          amount: result.amount.formatted,
          description: result.description,
          createdBy: result.createdBy,
          patientName: result.patient.name || billingName,
          patientUuid: result.patient.uuid,
        });
        setConfirming(false);
        setPatient(null);
        setQuery("");
        setUnregisteredName("");
        setAmount("");
        setDescription("");
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "The bill could not be created.");
        setConfirming(false);
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="cashier">
      <PageHeader
        title="Create bill"
        description="Add a bill for a registered patient, or for someone who is not registered. It stays unpaid until you collect it."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/accountant")}>
          ← Dashboard
        </Button>
      </PageHeader>
      {created ? (
        <Alert tone="success" title="Bill created">
          <p>
            {created.billNumber} for {created.patientName}: {created.amount}. {created.description}
          </p>
          <p>Created by {created.createdBy}.</p>
          <Button variant="secondary" onClick={() => openAccountantPatient(created.patientUuid)}>
            Collect payment
          </Button>
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="warning" title="Bill not created">
          <p>{error}</p>
        </Alert>
      ) : null}
      <Card>
        <form
          className="cashier-create"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) setConfirming(true);
          }}
        >
          <fieldset className="cashier-create__kind">
            <legend>Patient</legend>
            <label>
              <input
                type="radio"
                name="bill-patient-kind"
                checked={kind === "registered"}
                onChange={() => {
                  setKind("registered");
                  setUnregisteredName("");
                }}
              />
              Registered
            </label>
            <label>
              <input
                type="radio"
                name="bill-patient-kind"
                checked={kind === "unregistered"}
                onChange={() => {
                  setKind("unregistered");
                  setPatient(null);
                  setQuery("");
                  setHits([]);
                }}
              />
              Not registered
            </label>
          </fieldset>
          {kind === "unregistered" ? (
            <label>
              Name
              <input
                value={unregisteredName}
                onChange={(event) => setUnregisteredName(event.target.value)}
                placeholder="Full name"
                autoComplete="off"
              />
            </label>
          ) : (
            <>
              <label>
                Patient
                {patient && patientLabel ? (
                  <div className="cashier-create__chosen">
                    <strong>{patientLabel.name}</strong>
                    <span>{patientLabel.mrn}</span>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setPatient(null);
                        setQuery("");
                      }}
                    >
                      Change
                    </Button>
                  </div>
                ) : (
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Name or hospital number"
                    autoComplete="off"
                  />
                )}
              </label>
              {!patient && searching ? <p className="cashier__muted">Searching…</p> : null}
              {!patient && hits.length > 0 ? (
                <ul className="cashier-create__hits">
                  {hits.map((hit) => {
                    const parsed = parsePatientDisplay(hit.display);
                    return (
                      <li key={hit.uuid}>
                        <button
                          type="button"
                          onClick={() => {
                            setPatient(hit);
                            setHits([]);
                            setQuery("");
                          }}
                        >
                          <strong>{parsed.name}</strong>
                          <span>{parsed.mrn}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </>
          )}
          <label>
            Amount
            <input
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
            />
          </label>
          <label>
            What is this bill for?
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={200}
              rows={3}
              placeholder="Medical certificate, folder, procedure"
            />
          </label>
          <p className="cashier__muted">The bill is recorded under your name.</p>
          <Button type="submit" disabled={!ready || busy}>
            Create bill
          </Button>
        </form>
      </Card>
      {confirming && billingName ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="create-bill-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="create-bill-title">Create this bill?</h2>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>
                  {billingName}
                  <div className="cashier__muted">
                    {kind === "registered" ? patientLabel?.mrn || "—" : "Not registered"}
                  </div>
                </dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>{amount.trim()}</dd>
              </div>
              <div>
                <dt>What it is for</dt>
                <dd>{description.trim()}</dd>
              </div>
            </dl>
            <div className="cashier-confirm__actions">
              <Button busy={busy} busyLabel="Creating…" onClick={submit}>
                Create bill
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function AccountantWorkspace({ context, section = null }: AccountantWorkspaceProps) {
  const view = useMemo(() => {
    if (section === "create") return "create";
    if (section === "outstanding") return "outstanding";
    if (section === "deleted") return "deleted";
    if (section === "waived") return "waived";
    if (section === "payments") return "payments";
    if (section === "refunds") return "refunds";
    if (section === "revenue") return "revenue";
    return "dashboard";
  }, [section]);

  const [dashboard, setDashboard] = useState<AccountantDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (view !== "dashboard") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchAccountantDashboard()
      .then((value) => {
        if (!cancelled) {
          setDashboard(value);
          setError(null);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setDashboard(null);
          setError(reason instanceof Error ? reason.message : "Unable to load the accountant desk.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view]);

  if (view === "create") return <CreateBillPage />;
  if (view === "outstanding") return <OutstandingPage />;
  if (view === "deleted") return <DeletedBillsPage />;
  if (view === "waived") return <WaivedBillsPage />;
  if (view === "payments") return <PaymentsPage />;
  if (view === "refunds") return <RefundsPage />;
  if (view === "revenue") return <RevenuePage />;
  return <DashboardView context={context} dashboard={dashboard} loading={loading} error={error} />;
}
