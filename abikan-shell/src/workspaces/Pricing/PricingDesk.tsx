import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { openLaboratorySection } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import {
  fetchDepartmentPrices,
  fetchPriceHistory,
  formatPriceChangedAt,
  saveDepartmentPrice,
} from "../../services/departmentPricing";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  DepartmentPriceItem,
  PriceChange,
  PricingDepartment,
} from "../../types/departmentPricing";
import { catalogueHint, matchesPriceSearch, parsePriceDraft, priceDraftError } from "./pricingView";
import "./PricingDesk.css";

interface PricingDeskProps {
  department: PricingDepartment;
  title: string;
  description: string;
  searchPlaceholder?: string;
}

export function PricingDesk({
  department,
  title,
  description,
  searchPlaceholder = "Search",
}: PricingDeskProps) {
  const [items, setItems] = useState<DepartmentPriceItem[]>([]);
  const [canWrite, setCanWrite] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [history, setHistory] = useState<PriceChange[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const historyItem = useMemo(
    () => items.find((row) => row.id === historyId) || null,
    [items, historyId],
  );

  const closeHistory = () => {
    setHistoryId(null);
    setHistory([]);
    setHistoryLoading(false);
  };

  const load = (search = query) => {
    setLoading(true);
    setError("");
    fetchDepartmentPrices(department, department === "reception" ? "" : search)
      .then((payload) => {
        setItems(payload.items);
        setCanWrite(payload.canWrite);
        setMessage(payload.message || "");
        setDrafts((current) => {
          const next: Record<string, string> = {};
          for (const item of payload.items) {
            next[item.id] = current[item.id] ?? (item.price ? String(item.price.amount) : "");
          }
          return next;
        });
      })
      .catch((reason) => {
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Those prices could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department]);

  useEffect(() => {
    if (!historyId) {
      return;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeHistory();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [historyId]);

  const visible = useMemo(
    () => items.filter((row) => matchesPriceSearch(row, query)),
    [items, query],
  );

  const save = async (item: DepartmentPriceItem) => {
    const problem = priceDraftError(drafts[item.id] || "");
    if (problem) {
      setError(problem);
      return;
    }
    const amount = parsePriceDraft(drafts[item.id] || "");
    if (amount === null) {
      setError("Enter a price of zero or more.");
      return;
    }
    setSavingId(item.id);
    setError("");
    setNotice("");
    try {
      const payload = await saveDepartmentPrice(department, item.id, amount, item.price?.amount);
      setItems(payload.items);
      setCanWrite(payload.canWrite);
      setNotice(`Saved ${item.name}. Bills already created stay as they were.`);
      if (historyId === item.id) {
        const latest = await fetchPriceHistory(department, item.id);
        setHistory(latest.history);
      }
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The price could not be saved.",
      );
    } finally {
      setSavingId(null);
    }
  };

  const openHistory = async (item: DepartmentPriceItem) => {
    setHistoryId(item.id);
    setHistory([]);
    setHistoryLoading(true);
    try {
      const payload = await fetchPriceHistory(department, item.id);
      setHistory(payload.history);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div className="price-desk">
      <PageHeader title={title} description={description} />
      {message ? (
        <Alert tone="info" title="Existing bills stay the same">
          <p>{message}</p>
        </Alert>
      ) : null}
      {notice ? (
        <Alert
          tone="success"
          title={department === "laboratory" ? "Laboratory prices" : "Price saved"}
        >
          <p>{notice}</p>
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="danger" title={department === "laboratory" ? "Tests & prices" : "Pricing"}>
          <p>{error}</p>
        </Alert>
      ) : null}

      {department === "laboratory" ? (
        <Card>
          <SectionHeader
            title="Hospital tests"
            description="Choose which laboratory tests this hospital offers under Hospital Tests. This screen only sets selling prices."
            action={
              <Button variant="secondary" onClick={() => openLaboratorySection("hospital-tests")}>
                Open Hospital Tests
              </Button>
            }
          />
        </Card>
      ) : null}

      <Card>
        <SectionHeader title={title} />
        {department !== "reception" ? (
          <label className="price-desk__search">
            <span>Search</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
            />
          </label>
        ) : null}
        {loading ? (
          <LoadingState variant="board" label="Loading prices…" />
        ) : visible.length === 0 ? (
          <EmptyState title={query.trim() ? "No matching items." : "No prices to show."} />
        ) : (
          <div className="abikan-table-wrap">
            <table className="abikan-table price-desk__table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Current price</th>
                  {canWrite ? <th>New price</th> : null}
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.name}</strong>
                      <div className="price-desk__hint">{catalogueHint(item)}</div>
                    </td>
                    <td>{item.price?.formatted || "—"}</td>
                    {canWrite ? (
                      <td>
                        <input
                          className="price-desk__input"
                          inputMode="decimal"
                          value={drafts[item.id] ?? ""}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [item.id]: event.target.value,
                            }))
                          }
                          aria-label={`New price for ${item.name}`}
                        />
                      </td>
                    ) : null}
                    <td>
                      <div className="price-desk__actions">
                        {canWrite ? (
                          <Button
                            disabled={savingId === item.id}
                            onClick={() => void save(item)}
                          >
                            {savingId === item.id ? "Saving…" : "Save"}
                          </Button>
                        ) : null}
                        <Button variant="ghost" onClick={() => void openHistory(item)}>
                          History
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {historyId
        ? createPortal(
            <div
              className="price-history-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="price-history-title"
              onClick={(event) => {
                if (event.target === event.currentTarget) {
                  closeHistory();
                }
              }}
            >
              <div className="price-history-dialog__panel">
                <h2 id="price-history-title">Price history</h2>
                <p className="price-history-dialog__item">{historyItem?.name || "Selected item"}</p>
                {historyLoading ? (
                  <p className="price-history-dialog__status">Loading history…</p>
                ) : null}
                {!historyLoading && history.length === 0 ? (
                  <p className="price-history-dialog__status">No price changes recorded yet.</p>
                ) : null}
                {!historyLoading && history.length > 0 ? (
                  <div className="abikan-table-wrap price-history-dialog__table">
                    <table className="abikan-table">
                      <thead>
                        <tr>
                          <th>When</th>
                          <th>Who</th>
                          <th>From</th>
                          <th>To</th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((row) => (
                          <tr key={`${row.occurredAt}-${row.newPrice.amount}`}>
                            <td>{formatPriceChangedAt(row.occurredAt)}</td>
                            <td>{row.changedBy || row.username}</td>
                            <td>{row.oldPrice.formatted}</td>
                            <td>{row.newPrice.formatted}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                <div className="price-history-dialog__actions">
                  <Button onClick={closeHistory}>Close</Button>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
