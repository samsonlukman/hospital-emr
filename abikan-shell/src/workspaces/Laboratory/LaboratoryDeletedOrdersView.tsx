import { useEffect, useState } from "react";
import { returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { fetchDeletedLabOrders } from "../../services/laboratoryBilling";
import type { DeletedLabOrderRow } from "../../types/laboratoryCatalogue";
import { formatClinicalWhen } from "../../utils/datetime";

const PAGE_SIZE = 25;

export function LaboratoryDeletedOrdersView() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<DeletedLabOrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDeletedLabOrders({ q: applied, offset, limit: PAGE_SIZE })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items ?? []);
        setTotal(payload.total ?? 0);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Deleted orders could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset]);

  return (
    <div className="lab-desk">
      <PageHeader
        title="Deleted orders"
        description="Laboratory orders removed by the laboratory, with the reason and who deleted them."
      >
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/laboratory")}>
          ← Laboratory
        </Button>
      </PageHeader>
      <Card>
        <div className="lab-desk__search">
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search patient, test, or reason"
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
        {loading ? <LoadingState variant="board" label="Loading deleted orders…" /> : null}
        {error ? (
          <Alert tone="warning" title="Deleted orders">
            <p>{error}</p>
          </Alert>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="No deleted laboratory orders." description="Deleted orders appear here with the reason." />
        ) : null}
        {!loading && items.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Patient</th>
                  <th>Test</th>
                  <th>Order</th>
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
                      <div className="lab-desk__muted">{row.hospitalNumber || "—"}</div>
                    </td>
                    <td>{row.testName}</td>
                    <td>{row.orderNumber || "—"}</td>
                    <td>{row.deletedBy}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="lab-desk__row-actions">
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
