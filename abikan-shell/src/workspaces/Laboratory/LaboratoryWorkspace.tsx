import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  openLaboratoryPatient,
  openLaboratoryOrder,
  openLaboratorySection,
  openLaboratoryWorklistOrder,
  readHashNavItemId,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { TableSkeleton } from "../../components/TableSkeleton";
import { KpiCard } from "../../components/KpiCard";
import { PageHeader } from "../../components/PageHeader";
import { QuickAction } from "../../components/QuickAction";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createLaboratoryCharge,
  deleteLaboratoryOrder,
  fetchLaboratoryBoard,
  fetchLaboratoryResultPdf,
  fetchLaboratoryTestFrequency,
  newLaboratoryRequestId,
} from "../../services/laboratoryBilling";
import type {
  LaboratoryBoardOrder,
  LaboratoryBoardPayload,
  LaboratoryTestFrequency,
} from "../../types/laboratoryCatalogue";
import type { WorkspaceContext } from "../../types";
import { greetingForNow } from "../../utils/datetime";
import { periodQuery } from "../Admin/adminAnalytics";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import "./LaboratoryFeeCard.css";
import { PricingDesk } from "../Pricing/PricingDesk";
import {
  RevenueGeneratedCard,
  RevenuePeriodFilter,
  useDepartmentRevenue,
} from "../shared/DepartmentRevenue";
import { LaboratoryDeletedOrdersView } from "./LaboratoryDeletedOrdersView";
import { LaboratoryHistoryView } from "./LaboratoryHistoryView";
import { LaboratoryHospitalTestsView } from "./LaboratoryHospitalTestsView";
import { LaboratoryCreateTestView } from "./LaboratoryCreateTestView";
import { LaboratoryReferenceRangesView } from "./LaboratoryReferenceRangesView";
import { LaboratoryBloodBankView } from "./LaboratoryBloodBankView";
import { LaboratoryInventoryView } from "./LaboratoryInventoryView";
import { LaboratoryNewOrderView } from "./LaboratoryNewOrderView";
import {
  laboratoryViewFromNav,
  matchesLabSearch,
  type LaboratoryView,
} from "./laboratoryView";
import "./LaboratoryWorkspace.css";

interface LaboratoryWorkspaceProps {
  context: WorkspaceContext;
}

function focusPatientSearch() {
  document.getElementById("global-patient-search")?.focus();
}

function openBoardOrder(row: LaboratoryBoardOrder) {
  if (row.patientUuid && row.visitUuid) {
    openLaboratoryWorklistOrder({
      orderUuid: row.uuid,
      patientUuid: row.patientUuid,
      visitUuid: row.visitUuid,
    });
    return;
  }
  openLaboratoryOrder(row.uuid, row.patientUuid, row.visitUuid);
}

function billLines(row: LaboratoryBoardOrder) {
  if (row.charges && row.charges.length > 0) {
    return row.charges;
  }
  return [
    {
      orderUuid: row.uuid,
      testName: row.testName,
      hasCharge: row.hasCharge,
      paymentStatus: row.paymentStatus,
    },
  ];
}

function LabRowActions({
  row,
  billingId,
  onSubmitBill,
  onDelete,
  onResult,
}: {
  row: LaboratoryBoardOrder;
  billingId: string;
  onSubmitBill: (row: LaboratoryBoardOrder) => void;
  onDelete: (row: LaboratoryBoardOrder) => void;
  onResult?: (row: LaboratoryBoardOrder, action: "print" | "download") => void;
}) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const rootRef = useRef<HTMLDivElement>(null);
  const lines = billLines(row);
  const canBill = lines.some((line) => !line.hasCharge) && Boolean(row.patientUuid);
  const canDelete = row.stage === "pending" && !row.accession;
  const submitting = billingId === row.uuid;

  useEffect(() => {
    if (!open) {
      return;
    }
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    const rect = rootRef.current?.getBoundingClientRect();
    if (rect) {
      const openUp = window.innerHeight - rect.bottom < 260;
      setMenuStyle({
        position: "fixed",
        top: openUp ? undefined : rect.bottom + 4,
        bottom: openUp ? window.innerHeight - rect.top + 4 : undefined,
        left: Math.max(8, rect.right - 180),
        width: 180,
      });
    }
    setOpen(true);
  };

  return (
    <div className="lab-desk__menu" ref={rootRef}>
      <button
        type="button"
        className="lab-desk__menu-button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={toggle}
      >
        Actions
      </button>
      {open ? (
        <div className="lab-desk__menu-list" role="menu" style={menuStyle}>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              openBoardOrder(row);
            }}
          >
            Open
          </button>
          {canBill ? (
            <button
              type="button"
              role="menuitem"
              disabled={submitting}
              onClick={() => {
                setOpen(false);
                onSubmitBill(row);
              }}
            >
              {submitting ? "Submitting…" : "Submit bill"}
            </button>
          ) : null}
          {canDelete ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onDelete(row);
              }}
            >
              Delete
            </button>
          ) : null}
          {onResult ? (
            <>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onResult(row, "print");
                }}
              >
                Print result
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onResult(row, "download");
                }}
              >
                Download PDF
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function BoardTable({
  rows,
  emptyTitle,
  emptyDescription,
  billingId,
  onSubmitBill,
  onDelete,
  onResult,
}: {
  rows: LaboratoryBoardOrder[];
  emptyTitle: string;
  emptyDescription: string;
  billingId: string;
  onSubmitBill: (row: LaboratoryBoardOrder) => void;
  onDelete: (row: LaboratoryBoardOrder) => void;
  onResult?: (row: LaboratoryBoardOrder, action: "print" | "download") => void;
}) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Age</th>
            <th>MRN</th>
            <th>Test</th>
            <th>Payment</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.uuid}>
              <td>
                {row.patientUuid ? (
                  <button
                    type="button"
                    className="lab-desk__link"
                    onClick={() => openLaboratoryPatient(row.patientUuid)}
                  >
                    {row.patientName}
                  </button>
                ) : (
                  row.patientName
                )}
              </td>
              <td>{row.age || "—"}</td>
              <td>{row.mrn || "—"}</td>
              <td>
                {billLines(row).map((line) => (
                  <div key={line.orderUuid} className="lab-desk__test-line">
                    <span>{line.testName}</span>
                    {billLines(row).length > 1 ? (
                      <button
                        type="button"
                        className="lab-workflow__remove"
                        aria-label={`Remove ${line.testName}`}
                        title={`Remove ${line.testName}`}
                        onClick={() =>
                          onDelete({
                            ...row,
                            uuid: line.orderUuid,
                            testName: line.testName,
                            orderUuids: [line.orderUuid],
                            testNames: [line.testName],
                          })
                        }
                      >
                        <span aria-hidden="true">×</span>
                      </button>
                    ) : null}
                  </div>
                ))}
                {row.outsourced ? <span className="lab-desk__panel">Outsourced</span> : null}
              </td>
              <td>
                {billLines(row).every((line) => line.hasCharge) ? (
                  <Badge tone={paymentStateTone(row.paymentStatus)}>{row.paymentStatus}</Badge>
                ) : billLines(row).some((line) => line.hasCharge) ? (
                  <span className="lab-desk__muted">
                    {billLines(row).filter((line) => line.hasCharge).length} of {billLines(row).length} billed
                  </span>
                ) : (
                  <span className="lab-desk__muted">Not billed</span>
                )}
              </td>
              <td>
                <span title={row.statusMessage || undefined}>
                  {row.laboratoryStatus}
                  {row.resultMapping === "ambiguous" ? " — order match needs review" : ""}
                </span>
              </td>
              <td>
                <LabRowActions
                  row={row}
                  billingId={billingId}
                  onSubmitBill={onSubmitBill}
                  onDelete={onDelete}
                  onResult={onResult}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TestFrequencyCard({ query }: { query: string }) {
  const [payload, setPayload] = useState<LaboratoryTestFrequency | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!query) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchLaboratoryTestFrequency(query)
      .then((next) => {
        if (cancelled) {
          return;
        }
        setPayload(next);
        setError(next.status === "unavailable" ? next.message || "Test totals could not be loaded." : "");
      })
      .catch((reason) => {
        if (cancelled) {
          return;
        }
        setPayload(null);
        setError(reason instanceof Error ? reason.message : "Test totals could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const tests = payload?.tests ?? [];
  const busiest = tests[0]?.count ?? 0;
  const periodLabel = payload?.period?.label;

  return (
    <Card>
      <SectionHeader
        title="Most ordered tests"
        description={periodLabel ? `Top 10 for ${periodLabel}.` : "Top 10 tests ordered in the selected dates."}
      />
      {loading && tests.length === 0 ? <p className="lab-frequency__total">Loading test totals…</p> : null}
      {error ? (
        <Alert tone="danger" title="Test totals could not be loaded">
          <p>{error}</p>
        </Alert>
      ) : null}
      {!loading && !error && tests.length === 0 ? (
        <EmptyState title="No tests were ordered in these dates." />
      ) : null}
      {tests.length > 0 ? (
        <>
          {payload?.total != null ? (
            <p className="lab-frequency__total">
              {payload.total} {payload.total === 1 ? "test ordered" : "tests ordered"}
            </p>
          ) : null}
          <ol className="lab-frequency">
            {tests.map((test) => (
              <li key={test.name}>
                <span className="lab-frequency__name">{test.name}</span>
                <span className="lab-frequency__track">
                  <span
                    style={{
                      width: `${busiest > 0 ? Math.max(6, Math.round((test.count / busiest) * 100)) : 0}%`,
                    }}
                  />
                </span>
                <span className="lab-frequency__count">{test.count}</span>
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </Card>
  );
}

export function LaboratoryWorkspace({ context }: LaboratoryWorkspaceProps) {
  const [view, setView] = useState<LaboratoryView>(() => laboratoryViewFromNav(readHashNavItemId()));
  const [board, setBoard] = useState<LaboratoryBoardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [billTarget, setBillTarget] = useState<LaboratoryBoardOrder | null>(null);
  const [billingId, setBillingId] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<LaboratoryBoardOrder | null>(null);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [actionError, setActionError] = useState("");
  const revenue = useDepartmentRevenue();

  useEffect(() => {
    const sync = () => setView(laboratoryViewFromNav(readHashNavItemId()));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (
      view === "pricing" ||
      view === "reference-ranges" ||
      view === "new-order" ||
      view === "history" ||
      view === "deleted" ||
      view === "hospital-tests" ||
      view === "create-test" ||
      view === "blood-bank" ||
      view === "inventory"
    ) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchLaboratoryBoard()
      .then((payload) => {
        if (!cancelled) {
          setBoard(payload);
          setError("");
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setBoard(null);
          setError(
            reason instanceof PatientAccountRequestError
              ? reason.message
              : "Laboratory orders could not be loaded. You can still search for a patient.",
          );
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
  }, [view]);

  const filtered = useMemo(() => {
    const rows = board?.orders ?? [];
    return rows.filter((row) => matchesLabSearch(row, query));
  }, [board, query]);

  const byNewest = (rows: LaboratoryBoardOrder[]) =>
    [...rows].sort((left, right) => (right.ordered || "").localeCompare(left.ordered || ""));
  const pending = byNewest(filtered.filter((row) => row.stage === "pending"));
  const processing = byNewest(filtered.filter((row) => row.stage === "processing"));
  const completed = byNewest(filtered.filter((row) => row.stage === "completed"));

  if (view === "reference-ranges") {
    return <LaboratoryReferenceRangesView />;
  }

  if (view === "pricing") {
    return (
      <PricingDesk
        department="laboratory"
        title="Tests & Prices"
        description="Set selling prices for hospital laboratory tests already enabled for ordering. Add or remove which tests the hospital offers under Hospital Tests."
        searchPlaceholder="Test name"
      />
    );
  }

  if (view === "hospital-tests") {
    return <LaboratoryHospitalTestsView />;
  }

  if (view === "create-test") {
    return <LaboratoryCreateTestView />;
  }

  if (view === "blood-bank") {
    return <LaboratoryBloodBankView />;
  }

  if (view === "inventory") {
    return <LaboratoryInventoryView />;
  }

  if (view === "deleted") {
    return <LaboratoryDeletedOrdersView />;
  }

  const submitBill = async (orderUuid: string) => {
    if (!billTarget?.patientUuid || billingId) {
      return;
    }
    setBillingId(orderUuid);
    setActionError("");
    try {
      await createLaboratoryCharge(billTarget.patientUuid, newLaboratoryRequestId(), orderUuid);
      const payload = await fetchLaboratoryBoard();
      setBoard(payload);
      const refreshed = [...payload.pending, ...payload.processing, ...payload.completed, ...payload.orders].find(
        (row) => row.uuid === billTarget.uuid || row.orderUuids?.includes(orderUuid),
      );
      if (refreshed && billLines(refreshed).some((line) => !line.hasCharge)) {
        setBillTarget(refreshed);
      } else {
        setBillTarget(null);
      }
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "The bill could not be submitted.");
    } finally {
      setBillingId("");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || deleting || deleteReason.trim().length < 3) {
      setDeleteError("Enter why this laboratory order is being deleted.");
      return;
    }
    setDeleting(true);
    setDeleteError("");
    try {
      const orderIds = deleteTarget.orderUuids?.filter(Boolean) || [deleteTarget.uuid];
      for (const orderUuid of orderIds) {
        await deleteLaboratoryOrder({
          orderUuid,
          reason: deleteReason.trim(),
          patientUuid: deleteTarget.patientUuid,
        });
      }
      setDeleteTarget(null);
      setDeleteReason("");
      const payload = await fetchLaboratoryBoard();
      setBoard(payload);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "This laboratory order could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  const boardActions = {
    billingId,
    onSubmitBill: (row: LaboratoryBoardOrder) => {
      setActionError("");
      setBillTarget(row);
    },
    onDelete: (row: LaboratoryBoardOrder) => {
      setDeleteTarget(row);
      setDeleteReason("");
      setDeleteError("");
    },
  };

  const pageTitle =
    view === "new-order"
      ? "New Lab Order"
      : view === "history"
        ? "Lab History"
        : "Laboratory";
  const pageDescription =
    view === "new-order"
      ? "Create a laboratory order started by Laboratory. No doctor order is required."
      : view === "history"
        ? "Review previous laboratory orders for registered and external patients."
        : `${greetingForNow()}, ${context.displayName}. Review pending tests, collect samples, and release results here.`;

  return (
    <div className="lab-desk">
      <PageHeader title={pageTitle} description={pageDescription} />

      {view === "new-order" ? <LaboratoryNewOrderView context={context} /> : null}
      {view === "history" ? <LaboratoryHistoryView /> : null}

      {view !== "new-order" && view !== "history" ? (
        <>
      {error ? (
        <Alert tone="danger" title="Orders could not be loaded">
          <p>{error}</p>
        </Alert>
      ) : null}

      {view === "patients" ? (
        <Card id="patients">
          <SectionHeader
            title="Search patient"
            description="Find a patient to review their laboratory orders and results."
          />
          <Button variant="secondary" onClick={focusPatientSearch}>
            Search patient
          </Button>
        </Card>
      ) : null}

      {view === "dashboard" || view === "orders" ? (
        <>
          {view === "dashboard" ? (
            <>
              <RevenuePeriodFilter revenue={revenue} />
              <section className="lab-desk__kpis" aria-label="Today's overview">
                <KpiCard
                  label="Orders"
                  value={loading ? "…" : board?.orders.length ?? 0}
                  hint="Recent laboratory orders"
                  tone="visits"
                  icon="flask"
                />
                <KpiCard
                  label="Completed"
                  value={loading ? "…" : completed.length}
                  hint="Results already finalized"
                  tone="teal"
                  icon="clipboardPlus"
                />
                <KpiCard
                  label="Pending"
                  value={loading ? "…" : pending.length}
                  hint="Waiting for sample or processing"
                  tone="appointments"
                  icon="clipboardList"
                />
                <RevenueGeneratedCard revenue={revenue} />
              </section>

              <TestFrequencyCard
                query={
                  revenue.payload
                    ? periodQuery(
                        revenue.payload.period.period,
                        revenue.payload.period.startDate,
                        revenue.payload.period.endDate,
                      )
                    : ""
                }
              />

              <Card>
                <SectionHeader title="Quick actions" />
                <div className="lab-desk__actions">
                  <QuickAction
                    label="New Lab Order"
                    icon="clipboardPlus"
                    tone="visits"
                    onClick={() => openLaboratorySection("new-order")}
                  />
                  <QuickAction
                    label="Lab History"
                    icon="receipt"
                    tone="teal"
                    onClick={() => openLaboratorySection("history")}
                  />
                </div>
              </Card>
            </>
          ) : null}
          <Card id="orders">
            <SectionHeader
              title="Laboratory orders"
              description="Recent tests across the laboratory. Payment is collected at Accounts."
            />
            <label className="lab-desk__search">
              <span>Search</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Patient, hospital number, or test"
              />
            </label>
            {loading ? (
              <TableSkeleton
                label="Loading laboratory orders…"
                headers={["Patient", "MRN", "Test", "Payment", "Status", "Action"]}
              />
            ) : (
              <BoardTable
                rows={filtered}
                emptyTitle="No laboratory orders"
                emptyDescription="No recent laboratory orders were found. Search a patient to review that person's tests."
                {...boardActions}
              />
            )}
          </Card>
          <Card>
            <SectionHeader
              title="Process tests in Hospital EMR"
              description="Open an order to collect its sample, enter the result, and validate it."
            />
            <p className="lab-desk__note">The laboratory record is updated automatically after each step.</p>
          </Card>
        </>
      ) : null}

      {view === "pending" ? (
        <Card id="pending">
          <SectionHeader
            title="Pending orders"
            description="Tests waiting for sample collection or processing. Payment status is shown; money is collected at Accounts."
          />
          {loading ? (
            <TableSkeleton
              label="Loading pending orders…"
              headers={["Patient", "MRN", "Test", "Payment", "Status", "Action"]}
            />
          ) : (
            <BoardTable
              rows={pending}
              emptyTitle="No pending laboratory orders"
              emptyDescription="There are no pending laboratory orders right now."
              {...boardActions}
            />
          )}
        </Card>
      ) : null}

      {view === "processing" ? (
        <Card id="processing">
          <SectionHeader
            title="Processing / in progress"
              description="Tests whose processing state is reported by the laboratory system."
          />
          {loading ? (
            <TableSkeleton
              label="Loading in-progress tests…"
              headers={["Patient", "MRN", "Test", "Payment", "Status", "Action"]}
            />
          ) : (
            <BoardTable
              rows={processing}
              emptyTitle="No tests in progress"
              emptyDescription="No laboratory tests are marked in progress yet."
              {...boardActions}
            />
          )}
        </Card>
      ) : null}

      {view === "completed" ? (
        <Card id="completed">
          <SectionHeader
            title="Completed results"
              description="Tests reported as finalized by the laboratory system. Open a patient to read safely matched values."
          />
          {loading ? (
            <TableSkeleton
              label="Loading completed results…"
              headers={["Patient", "MRN", "Test", "Payment", "Status", "Action"]}
            />
          ) : (
            <BoardTable
              rows={completed}
              emptyTitle="No completed laboratory results"
              emptyDescription="Results appear here after the laboratory releases them to the chart."
              {...boardActions}
              onResult={(row, action) => {
                setActionError("");
                void fetchLaboratoryResultPdf(row.uuid, row.patientUuid, action).catch((reason) => {
                  setActionError(reason instanceof Error ? reason.message : "The result could not be prepared.");
                });
              }}
            />
          )}
        </Card>
      ) : null}
        </>
      ) : null}

      {actionError ? (
        <Alert tone="danger" title="That could not be completed">
          <p>{actionError}</p>
        </Alert>
      ) : null}

      {billTarget ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="lab-submit-bill-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="lab-submit-bill-title">Submit this bill</h2>
            <p>This sends the bill to the cashier. Laboratory does not collect money. Each test is billed on its own.</p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{billTarget.patientName}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{billTarget.mrn || "—"}</dd>
              </div>
            </dl>
            <ul className="lab-fee__tests">
              {billLines(billTarget).map((line) => (
                <li key={line.orderUuid}>
                  <div>
                    <strong>{line.testName}</strong>
                  </div>
                  {line.hasCharge ? (
                    <Badge tone={paymentStateTone(line.paymentStatus)}>{line.paymentStatus}</Badge>
                  ) : (
                    <Button
                      onClick={() => void submitBill(line.orderUuid)}
                      busy={billingId === line.orderUuid}
                      busyLabel="Submitting…"
                      disabled={Boolean(billingId)}
                    >
                      Submit bill
                    </Button>
                  )}
                </li>
              ))}
            </ul>
            <div className="cashier-confirm__actions">
              <Button variant="ghost" onClick={() => setBillTarget(null)} disabled={Boolean(billingId)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteTarget ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="lab-delete-order-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="lab-delete-order-title">Delete this laboratory order</h2>
            <p>
              {deleteTarget.testName} · {deleteTarget.patientName}. This removes that test from the laboratory list.
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
