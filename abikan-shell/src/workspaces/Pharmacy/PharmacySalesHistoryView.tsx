import { useEffect, useMemo, useState } from "react";
import { Trash2, Undo2 } from "lucide-react";
import { openPharmacyPatient } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import {
  cancelPharmacySalePrescription,
  fetchPharmacySalesHistory,
  fetchPharmacySalesHistoryItem,
  newRefundRequestId,
  refundPharmacySale,
} from "../../services/pharmacy";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  PharmacySalesHistoryDetail,
  PharmacySalesHistoryItem,
  PharmacySalesHistoryLine,
  PharmacySalesHistoryQuery,
} from "../../types/pharmacy";
import { formatClinicalWhen } from "../../utils/datetime";
import { formatNaira } from "../../utils/naira";
import { pharmacyStatusTone } from "../PatientAccount/accountBadges";
import { pharmacyStaffError } from "./pharmacyView";

const PAGE_SIZE = 25;

type RefundDialog =
  | { kind: "full"; sale: PharmacySalesHistoryItem | PharmacySalesHistoryDetail }
  | {
      kind: "line";
      sale: PharmacySalesHistoryDetail;
      line: PharmacySalesHistoryLine;
      quantity: string;
    };

function buyerTypeLabel(value: string): string {
  return value === "registered" ? "Registered Patient" : "Other Buyer";
}

function transactionTypeLabel(value: string): string {
  return value === "prescription" ? "Prescription" : "Direct sale";
}

function careSettingLabel(value: string): string {
  if (value === "inpatient") {
    return "Inpatient";
  }
  if (value === "outpatient") {
    return "Outpatient";
  }
  return "—";
}

function paymentDisplay(value: string): string {
  if (value === "PARTIALLY PAID") {
    return "Partial";
  }
  if (value === "PAID") {
    return "Paid";
  }
  if (value === "UNPAID") {
    return "Unpaid";
  }
  return value || "—";
}

function statusLabel(row: PharmacySalesHistoryItem): string {
  if (row.refundStatus) {
    return row.refundStatus;
  }
  if (row.refunded) {
    return "Refunded";
  }
  return row.dispensingStatus || "—";
}

function remainingRefundAmount(
  sale: PharmacySalesHistoryItem | PharmacySalesHistoryDetail,
): number {
  if ("lines" in sale && Array.isArray(sale.lines) && sale.lines.length > 0) {
    return sale.lines.reduce((sum, line) => {
      const qty = Number(line.quantityRefundable ?? 0);
      const unit = Number(line.refundAmountPerUnit ?? line.unitPrice ?? 0);
      return sum + qty * unit;
    }, 0);
  }
  return Number(sale.amountTotal) || 0;
}

function itemsLabel(count: number): string {
  if (count === 1) {
    return "1 medicine";
  }
  return `${count} medicines`;
}

function emptyFilters(): PharmacySalesHistoryQuery {
  return {
    period: "this_month",
    from: "",
    to: "",
    q: "",
    paymentStatus: "",
    dispensingStatus: "",
    buyerType: "",
    transactionType: "",
    careSetting: "",
    pharmacist: "",
    transactionId: "",
    patientId: "",
  };
}

export function PharmacySalesHistoryView() {
  const [filters, setFilters] = useState<PharmacySalesHistoryQuery>(emptyFilters);
  const [applied, setApplied] = useState<PharmacySalesHistoryQuery>(emptyFilters);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<PharmacySalesHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [periodLabel, setPeriodLabel] = useState("This month");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PharmacySalesHistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [refundDialog, setRefundDialog] = useState<RefundDialog | null>(null);
  const [refundBusy, setRefundBusy] = useState(false);
  const [refundError, setRefundError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<PharmacySalesHistoryItem | PharmacySalesHistoryDetail | null>(
    null,
  );
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [notice, setNotice] = useState("");
  const [listEpoch, setListEpoch] = useState(0);

  const query = useMemo(
    () => ({
      ...applied,
      period: applied.from && applied.to ? "custom" : applied.period || "this_month",
      offset,
      limit: PAGE_SIZE,
    }),
    [applied, offset],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void fetchPharmacySalesHistory(query)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setItems(payload.items ?? []);
        setTotal(Number(payload.total) || 0);
        setPeriodLabel(payload.period?.label || "Selected period");
      })
      .catch((reason) => {
        if (cancelled) {
          return;
        }
        setItems([]);
        setTotal(0);
        setError(pharmacyStaffError(reason, "Sales history could not be loaded."));
        if (reason instanceof PatientAccountRequestError && reason.status === 401) {
          setError("Sign in again to review sales history.");
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
  }, [query, listEpoch]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError("");
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError("");
    void fetchPharmacySalesHistoryItem(selectedId)
      .then((payload) => {
        if (!cancelled) {
          setDetail(payload);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(pharmacyStaffError(reason, "This sale could not be opened."));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, listEpoch]);

  const openSaleDetail = (saleId: string) => {
    setNotice("");
    setSelectedId(saleId);
  };

  const closeSaleDetail = () => {
    setSelectedId(null);
    setDetail(null);
    setDetailError("");
  };

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  const applyFilters = () => {
    setOffset(0);
    setApplied({ ...filters });
  };

  const clearFilters = () => {
    const next = emptyFilters();
    setFilters(next);
    setApplied(next);
    setOffset(0);
  };

  const openFullRefund = (sale: PharmacySalesHistoryItem | PharmacySalesHistoryDetail) => {
    setRefundError("");
    setRefundDialog({ kind: "full", sale });
  };

  const openLineRefund = (sale: PharmacySalesHistoryDetail, line: PharmacySalesHistoryLine) => {
    setRefundError("");
    setRefundDialog({
      kind: "line",
      sale,
      line,
      quantity: String(line.quantityRefundable ?? line.quantity ?? ""),
    });
  };

  const confirmRefund = async () => {
    if (!refundDialog || refundBusy) {
      return;
    }
    setRefundBusy(true);
    setRefundError("");
    try {
      const requestId = newRefundRequestId();
      const result =
        refundDialog.kind === "full"
          ? await refundPharmacySale(refundDialog.sale.saleId, { requestId, mode: "full" })
          : await refundPharmacySale(refundDialog.sale.saleId, {
              requestId,
              mode: "line",
              lineId: refundDialog.line.lineId,
              quantity: Number(refundDialog.quantity),
            });
      setNotice(result.message || "Refund completed. Stock restored.");
      setRefundDialog(null);
      setSelectedId(refundDialog.sale.saleId);
      if (result.sale) {
        setDetail(result.sale);
      }
      setListEpoch((value) => value + 1);
    } catch (reason) {
      setRefundError(pharmacyStaffError(reason, "This sale could not be refunded."));
    } finally {
      setRefundBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || deleteBusy) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError("");
    try {
      const result = await cancelPharmacySalePrescription(deleteTarget.saleId);
      setNotice(result.message || "Prescription deleted.");
      setDeleteTarget(null);
      closeSaleDetail();
      setListEpoch((value) => value + 1);
    } catch (reason) {
      setDeleteError(pharmacyStaffError(reason, "This prescription could not be deleted."));
    } finally {
      setDeleteBusy(false);
    }
  };

  const lineRefundAmount =
    refundDialog?.kind === "line"
      ? Number(refundDialog.quantity || 0) * Number(refundDialog.line.refundAmountPerUnit || 0)
      : 0;

  if (selectedId) {
    return (
      <div className="pharm-history">
        <Card className="pharm-history__detail" id="sale-detail">
          <SectionHeader
            title={detail?.saleName ? `Sale ${detail.saleName}` : "Sale details"}
            description="Review every medicine on this receipt. Delete unpaid prescriptions or refund dispensed sales."
            action={
              <Button variant="ghost" onClick={closeSaleDetail}>
                Back to sales
              </Button>
            }
          />
          {notice ? (
            <Alert tone="success" title="Updated">
              <p>{notice}</p>
            </Alert>
          ) : null}
          {detailLoading ? <LoadingState variant="board" label="Loading sale…" /> : null}
          {detailError ? (
            <Alert tone="warning" title="Sale details">
              <p>{detailError}</p>
            </Alert>
          ) : null}
          {detail && !detailLoading ? (
            <div className="pharm-history__detail-body">
              <p className="pharm-history__detail-meta">
                {formatClinicalWhen(detail.dateOrder)}
                {detail.buyerName ? (
                  <>
                    {" · "}
                    {detail.patientUuid ? (
                      <button
                        type="button"
                        className="pharm-history__link"
                        onClick={() => openPharmacyPatient(detail.patientUuid)}
                      >
                        {detail.buyerName}
                      </button>
                    ) : (
                      detail.buyerName
                    )}
                  </>
                ) : null}
                {detail.mrn ? ` (${detail.mrn})` : ""}
                {` · ${transactionTypeLabel(String(detail.transactionType))}`}
                {careSettingLabel(detail.careSetting) !== "—"
                  ? ` · ${careSettingLabel(detail.careSetting)}`
                  : ""}
              </p>

              <div className="pharm-history__detail-badges">
                <Badge tone={pharmacyStatusTone(detail.paymentStatus)}>
                  {paymentDisplay(String(detail.paymentStatus))}
                </Badge>
                <Badge tone={pharmacyStatusTone(statusLabel(detail))}>{statusLabel(detail)}</Badge>
              </div>

              <table className="pharm-history__table">
                <thead>
                  <tr>
                    <th>Medicine</th>
                    <th>Qty</th>
                    <th>Unit price</th>
                    <th>Total</th>
                    <th>Refunded</th>
                    <th className="pharm-history__actions-col"> </th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.lines || []).map((line) => (
                    <tr key={line.lineId || `${line.drugName}-${line.quantity}`}>
                      <td>{line.drugName}</td>
                      <td>{line.quantity}</td>
                      <td>{formatNaira(line.unitPrice)}</td>
                      <td>{formatNaira(line.lineTotal)}</td>
                      <td>
                        {line.quantityRefunded && line.quantityRefunded > 0
                          ? `${line.quantityRefunded} / ${line.quantity}`
                          : "—"}
                      </td>
                      <td className="pharm-history__actions-col">
                        {line.canRefund ? (
                          <button
                            type="button"
                            className="pharm-history__refund"
                            title="Refund medicine"
                            aria-label={`Refund ${line.drugName}`}
                            onClick={() => openLineRefund(detail, line)}
                          >
                            <Undo2 size={16} strokeWidth={1.75} aria-hidden="true" />
                          </button>
                        ) : (line.quantityRefundable ?? 0) <= 0 && (line.quantityRefunded ?? 0) > 0 ? (
                          <span className="pharm-history__refunded" title="Refunded">
                            ✓
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="pharm-history__detail-total">
                <span>Total</span>
                <strong>{formatNaira(detail.amountTotal)}</strong>
              </div>

              <p className="pharm-history__detail-staff">
                Processed by {detail.processedBy || detail.createdBy || "—"}
                {detail.invoiceName ? ` · ${detail.invoiceName}` : ""}
              </p>

              <div className="pharm-history__detail-actions">
                {detail.canDeletePrescription ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setDeleteError("");
                      setDeleteTarget(detail);
                    }}
                  >
                    Delete prescription
                  </Button>
                ) : null}
                {detail.canRefund ? (
                  <Button variant="secondary" onClick={() => openFullRefund(detail)}>
                    Refund entire sale
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
        </Card>

        {refundDialog ? (
          <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="refund-sale-title">
            <div className="abikan-dialog__panel cashier-confirm">
              <h2 id="refund-sale-title">
                {refundDialog.kind === "full" ? "Refund entire sale?" : "Refund medicine?"}
              </h2>
              {refundDialog.kind === "full" ? (
                <>
                  <p>Receipt: {refundDialog.sale.saleName || refundDialog.sale.saleId}</p>
                  <p>
                    This will return all eligible medicines to inventory and reverse the corresponding
                    financial amount.
                  </p>
                  <p>
                    <strong>
                      Refund amount: {formatNaira(remainingRefundAmount(refundDialog.sale))}
                    </strong>
                  </p>
                </>
              ) : (
                <>
                  <p>
                    <strong>{refundDialog.line.drugName}</strong>
                  </p>
                  <dl>
                    <div>
                      <dt>Original quantity</dt>
                      <dd>{refundDialog.line.quantity}</dd>
                    </div>
                    <div>
                      <dt>Already refunded</dt>
                      <dd>{refundDialog.line.quantityRefunded || 0}</dd>
                    </div>
                    <div>
                      <dt>Refund quantity</dt>
                      <dd>
                        <input
                          type="number"
                          min={0.0001}
                          max={refundDialog.line.quantityRefundable || refundDialog.line.quantity}
                          step="any"
                          value={refundDialog.quantity}
                          onChange={(event) =>
                            setRefundDialog({
                              ...refundDialog,
                              quantity: event.target.value,
                            })
                          }
                          disabled={refundBusy}
                        />
                      </dd>
                    </div>
                  </dl>
                  <p>
                    Refund amount: {formatNaira(Number.isFinite(lineRefundAmount) ? lineRefundAmount : 0)}
                  </p>
                  <p>
                    This will restore {refundDialog.quantity || "0"} unit(s) to inventory and reverse the
                    corresponding financial amount.
                  </p>
                </>
              )}
              {refundError ? <p className="pharm-dialog__error">{refundError}</p> : null}
              <div className="cashier-confirm__actions">
                <Button
                  variant="secondary"
                  disabled={refundBusy}
                  onClick={() => {
                    setRefundDialog(null);
                    setRefundError("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  busy={refundBusy}
                  busyLabel="Refunding…"
                  onClick={() => void confirmRefund()}
                >
                  {refundDialog.kind === "full" ? "Refund entire sale" : "Confirm refund"}
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        {deleteTarget ? (
          <div
            className="abikan-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-rx-sale-title"
          >
            <div className="abikan-dialog__panel cashier-confirm">
              <h2 id="delete-rx-sale-title">Delete prescription?</h2>
              <p>This prescription has not been paid for or dispensed.</p>
              <p>
                Receipt: {deleteTarget.saleName || deleteTarget.saleId}
                {deleteTarget.buyerName ? ` · ${deleteTarget.buyerName}` : ""}
              </p>
              {deleteError ? <p className="pharm-dialog__error">{deleteError}</p> : null}
              <div className="cashier-confirm__actions">
                <Button
                  variant="secondary"
                  disabled={deleteBusy}
                  onClick={() => {
                    setDeleteTarget(null);
                    setDeleteError("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  busy={deleteBusy}
                  busyLabel="Deleting…"
                  onClick={() => void confirmDelete()}
                >
                  Delete prescription
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="pharm-history">
      <Card id="sales-history">
        <SectionHeader
          title="Sales History"
          description="Each receipt is one sale. Open a receipt to review medicines, delete unpaid prescriptions, or refund."
        />

        <div className="pharm-history__filters">
          <label>
            <span>Search</span>
            <input
              value={filters.q || ""}
              onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
              placeholder="Transaction, patient, or hospital number"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  applyFilters();
                }
              }}
            />
          </label>
          <label>
            <span>Period</span>
            <select
              value={filters.period || "this_month"}
              onChange={(event) => setFilters((current) => ({ ...current, period: event.target.value }))}
            >
              <option value="today">Today</option>
              <option value="this_week">This week</option>
              <option value="this_month">This month</option>
              <option value="custom">Custom dates</option>
            </select>
          </label>
          <label>
            <span>Payment</span>
            <select
              value={filters.paymentStatus || ""}
              onChange={(event) =>
                setFilters((current) => ({ ...current, paymentStatus: event.target.value }))
              }
            >
              <option value="">Any</option>
              <option value="UNPAID">Unpaid</option>
              <option value="PARTIALLY PAID">Partial</option>
              <option value="PAID">Paid</option>
            </select>
          </label>
          <label>
            <span>Sale type</span>
            <select
              value={filters.transactionType || ""}
              onChange={(event) =>
                setFilters((current) => ({ ...current, transactionType: event.target.value }))
              }
            >
              <option value="">Any</option>
              <option value="direct_sale">Direct sale</option>
              <option value="prescription">Prescription</option>
            </select>
          </label>
          <div className="pharm-history__filter-actions">
            <Button variant="secondary" onClick={clearFilters}>
              Clear
            </Button>
            <Button onClick={applyFilters}>Apply</Button>
          </div>
        </div>

        {error ? (
          <Alert tone="warning" title="Sales History">
            <p>{error}</p>
          </Alert>
        ) : null}

        {notice ? (
          <Alert tone="success" title="Updated">
            <p>{notice}</p>
          </Alert>
        ) : null}

        <p className="pharm-history__period">
          Showing {periodLabel}
          {total > 0 ? ` · ${pageStart}–${pageEnd} of ${total}` : ""}
        </p>

        {loading ? (
          <LoadingState variant="board" label="Loading sales history…" />
        ) : items.length === 0 ? (
          <EmptyState title="No pharmacy sales in this period." />
        ) : (
          <div className="pharm-history__table-wrap">
            <table className="pharm-history__table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Receipt</th>
                  <th>Patient</th>
                  <th>Items</th>
                  <th>Amount</th>
                  <th>Payment</th>
                  <th>Status</th>
                  <th className="pharm-history__actions-col"> </th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.saleId} className={selectedId === row.saleId ? "is-selected" : undefined}>
                    <td>{formatClinicalWhen(row.dateOrder)}</td>
                    <td>
                      <button
                        type="button"
                        className="pharm-history__link"
                        onClick={() => openSaleDetail(row.saleId)}
                      >
                        {row.saleName || row.saleId}
                      </button>
                    </td>
                    <td>
                      <div className="pharm-history__buyer">
                        {row.patientUuid ? (
                          <button
                            type="button"
                            className="pharm-history__link"
                            onClick={() => openPharmacyPatient(row.patientUuid)}
                          >
                            {row.buyerName || "Patient"}
                          </button>
                        ) : (
                          <strong>{row.buyerName || "—"}</strong>
                        )}
                        <span>
                          {row.mrn ? `${row.mrn} · ` : ""}
                          {buyerTypeLabel(row.buyerType)}
                        </span>
                      </div>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="pharm-history__link"
                        onClick={() => openSaleDetail(row.saleId)}
                      >
                        {itemsLabel(row.lineCount)}
                      </button>
                    </td>
                    <td>{formatNaira(row.amountTotal)}</td>
                    <td>
                      <Badge tone={pharmacyStatusTone(row.paymentStatus)}>
                        {paymentDisplay(String(row.paymentStatus))}
                      </Badge>
                    </td>
                    <td>
                      <Badge tone={pharmacyStatusTone(statusLabel(row))}>{statusLabel(row)}</Badge>
                    </td>
                    <td className="pharm-history__actions-col">
                      {row.canDeletePrescription ? (
                        <button
                          type="button"
                          className="pharm-history__delete"
                          title="Delete prescription"
                          aria-label={`Delete prescription ${row.saleName || ""}`}
                          onClick={() => {
                            setDeleteError("");
                            setDeleteTarget(row);
                          }}
                        >
                          <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />
                        </button>
                      ) : null}
                      {row.canRefund ? (
                        <button
                          type="button"
                          className="pharm-history__refund"
                          title="Refund sale"
                          aria-label={`Refund ${row.saleName || "sale"}`}
                          onClick={() => openFullRefund(row)}
                        >
                          <Undo2 size={16} strokeWidth={1.75} aria-hidden="true" />
                        </button>
                      ) : null}
                      {row.refunded ? (
                        <span className="pharm-history__refunded" title="Refunded">
                          ✓
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && total > PAGE_SIZE ? (
          <div className="pharm-history__pager">
            <Button variant="secondary" disabled={!canPrev} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <Button variant="secondary" disabled={!canNext} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        ) : null}
      </Card>

      {refundDialog ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="refund-sale-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="refund-sale-title">
              {refundDialog.kind === "full" ? "Refund entire sale?" : "Refund medicine?"}
            </h2>
            {refundDialog.kind === "full" ? (
              <>
                <p>Receipt: {refundDialog.sale.saleName || refundDialog.sale.saleId}</p>
                <p>
                  This will return all eligible medicines to inventory and reverse the corresponding
                  financial amount.
                </p>
                <p>
                  <strong>
                    Refund amount: {formatNaira(remainingRefundAmount(refundDialog.sale))}
                  </strong>
                </p>
              </>
            ) : (
              <>
                <p>
                  <strong>{refundDialog.line.drugName}</strong>
                </p>
                <dl>
                  <div>
                    <dt>Original quantity</dt>
                    <dd>{refundDialog.line.quantity}</dd>
                  </div>
                  <div>
                    <dt>Already refunded</dt>
                    <dd>{refundDialog.line.quantityRefunded || 0}</dd>
                  </div>
                  <div>
                    <dt>Refund quantity</dt>
                    <dd>
                      <input
                        type="number"
                        min={0.0001}
                        max={refundDialog.line.quantityRefundable || refundDialog.line.quantity}
                        step="any"
                        value={refundDialog.quantity}
                        onChange={(event) =>
                          setRefundDialog({
                            ...refundDialog,
                            quantity: event.target.value,
                          })
                        }
                        disabled={refundBusy}
                      />
                    </dd>
                  </div>
                </dl>
                <p>
                  Refund amount: {formatNaira(Number.isFinite(lineRefundAmount) ? lineRefundAmount : 0)}
                </p>
                <p>
                  This will restore {refundDialog.quantity || "0"} unit(s) to inventory and reverse the
                  corresponding financial amount.
                </p>
              </>
            )}
            {refundError ? <p className="pharm-dialog__error">{refundError}</p> : null}
            <div className="cashier-confirm__actions">
              <Button
                variant="secondary"
                disabled={refundBusy}
                onClick={() => {
                  setRefundDialog(null);
                  setRefundError("");
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                busy={refundBusy}
                busyLabel="Refunding…"
                onClick={() => void confirmRefund()}
              >
                {refundDialog.kind === "full" ? "Refund entire sale" : "Confirm refund"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteTarget ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-rx-sale-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="delete-rx-sale-title">Delete prescription?</h2>
            <p>This prescription has not been paid for or dispensed.</p>
            <p>
              Receipt: {deleteTarget.saleName || deleteTarget.saleId}
              {deleteTarget.buyerName ? ` · ${deleteTarget.buyerName}` : ""}
            </p>
            {deleteError ? <p className="pharm-dialog__error">{deleteError}</p> : null}
            <div className="cashier-confirm__actions">
              <Button
                variant="secondary"
                disabled={deleteBusy}
                onClick={() => {
                  setDeleteTarget(null);
                  setDeleteError("");
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                busy={deleteBusy}
                busyLabel="Deleting…"
                onClick={() => void confirmDelete()}
              >
                Delete prescription
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
