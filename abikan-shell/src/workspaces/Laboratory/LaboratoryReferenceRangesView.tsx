import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import {
  fetchReferenceRanges,
  saveReferenceRange,
  type LaboratoryReferenceRange,
} from "../../services/laboratoryBilling";

type RangeFilter = "review" | "approved" | "all";

interface RangeEdit {
  low: string;
  high: string;
  unit: string;
  sex: string;
  sourceTitle: string;
  limitations: string;
}

function toneFor(status: string): "neutral" | "info" | "success" | "warning" {
  if (status === "approved") return "success";
  if (status === "pending_review") return "info";
  if (status === "inactive") return "neutral";
  return "warning";
}

function canApprove(row: LaboratoryReferenceRange): boolean {
  return (
    row.purpose === "reference_interval" &&
    (row.status === "draft" || row.status === "pending_review") &&
    Boolean(row.sourceTitle.trim()) &&
    Boolean(row.low.trim() || row.high.trim())
  );
}

export function LaboratoryReferenceRangesView() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<RangeFilter>("all");
  const [items, setItems] = useState<LaboratoryReferenceRange[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [editingId, setEditingId] = useState("");
  const [edit, setEdit] = useState<RangeEdit | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = () => {
    setLoading(true);
    fetchReferenceRanges()
      .then((payload) => {
        setItems(payload.items ?? []);
        setError("");
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "Reference ranges could not be loaded.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((row) => {
      if (filter === "review" && row.status !== "draft" && row.status !== "pending_review") return false;
      if (filter === "approved" && row.status !== "approved") return false;
      if (!needle) return true;
      return [row.testName, row.appliesTo, row.sourceTitle, row.unit, row.limitations]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [filter, items, query]);

  const groups = useMemo(() => {
    const map = new Map<string, LaboratoryReferenceRange[]>();
    for (const row of visible) {
      const bucket = map.get(row.testName) ?? [];
      bucket.push(row);
      map.set(row.testName, bucket);
    }
    return [...map.entries()];
  }, [visible]);

  const run = (id: string, action: "approve" | "inactivate" | "revise" | "submit") => {
    setBusyId(id);
    setNotice("");
    setError("");
    saveReferenceRange({ action, id })
      .then((payload) => {
        const label =
          action === "approve"
            ? "Approved. Result entry can use it when the patient matches."
            : action === "revise"
              ? "A draft revision was created. The approved range stays in use until the revision is approved."
              : action === "inactivate"
                ? "That range is no longer used on results."
                : "Sent for review.";
        setNotice(`${payload.range.testName}: ${label}`);
        setEditingId("");
        load();
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "The reference range could not be updated.");
      })
      .finally(() => setBusyId(""));
  };

  const startEdit = (row: LaboratoryReferenceRange) => {
    setEditingId(row.id);
    setEdit({
      low: row.low,
      high: row.high,
      unit: row.unit,
      sex: row.sex || "any",
      sourceTitle: row.sourceTitle,
      limitations: row.limitations,
    });
  };

  const saveEdit = (row: LaboratoryReferenceRange) => {
    if (!edit) return;
    setBusyId(row.id);
    setNotice("");
    setError("");
    saveReferenceRange({
      action: "save",
      id: row.id,
      low: edit.low.trim(),
      high: edit.high.trim(),
      unit: edit.unit.trim(),
      sex: edit.sex,
      sourceTitle: edit.sourceTitle.trim(),
      limitations: edit.limitations.trim(),
    })
      .then(() => {
        setNotice(
          row.status === "approved"
            ? `${row.testName} was updated. Result entry uses this range.`
            : `${row.testName} was saved as a draft. It is not used on results until it is approved.`,
        );
        setEditingId("");
        setEdit(null);
        load();
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "The reference range could not be saved.");
      })
      .finally(() => setBusyId(""));
  };

  return (
    <div className="lab-desk">
      <PageHeader
        title="Reference ranges"
        description="Result entry fills the range that matches the patient's age and sex. Change a value here when that usual range should change."
      />
      {notice ? (
        <Alert tone="success" title="Reference range">
          <p>{notice}</p>
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="warning" title="Reference range">
          <p>{error}</p>
        </Alert>
      ) : null}
      <Card>
        <div className="lab-ranges__toolbar">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search a test or source"
            aria-label="Search reference ranges"
          />
          <div className="lab-ranges__filters" role="group" aria-label="Range status">
            {(
              [
                ["review", "Needs review"],
                ["approved", "Approved"],
                ["all", "All"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={filter === value ? "is-selected" : ""}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {loading ? <LoadingState variant="board" label="Loading reference ranges…" /> : null}
        {!loading && groups.length === 0 ? (
          <EmptyState
            title="No ranges in this view."
            description="Draft ranges wait here until they are approved. A test with no source has no numeric limits."
          />
        ) : null}
        {!loading
          ? groups.map(([name, rows]) => {
              const approved = rows.filter((row) => row.status === "approved").length;
              return (
                <details key={name} className="lab-ranges__group" open={query.trim().length >= 2}>
                  <summary>
                    <span>{name}</span>
                    <span className="lab-ranges__count">
                      {rows.length} {rows.length === 1 ? "row" : "rows"}
                      {approved ? `, ${approved} approved` : ""}
                    </span>
                  </summary>
                  <div className="abikan-table-wrap">
                    <table className="abikan-table">
                      <thead>
                        <tr>
                          <th>Applies to</th>
                          <th>Range</th>
                          <th>Status</th>
                          <th>Source</th>
                          <th> </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.id}>
                            <td>{row.appliesTo}</td>
                            <td>
                              {row.rangeText ? (
                                <span>
                                  {row.rangeText}
                                  {row.unit ? ` ${row.unit}` : ""}
                                </span>
                              ) : (
                                <span className="lab-ranges__missing">No numeric range</span>
                              )}
                              {row.purpose !== "reference_interval" ? (
                                <p className="lab-ranges__note">Not used on the result sheet.</p>
                              ) : null}
                              {row.conflictNote ? <p className="lab-ranges__note">{row.conflictNote}</p> : null}
                              {editingId === row.id && edit ? (
                                <div className="lab-ranges__edit">
                                  <label>
                                    Low
                                    <input
                                      value={edit.low}
                                      onChange={(event) => setEdit({ ...edit, low: event.target.value })}
                                    />
                                  </label>
                                  <label>
                                    High
                                    <input
                                      value={edit.high}
                                      onChange={(event) => setEdit({ ...edit, high: event.target.value })}
                                    />
                                  </label>
                                  <label>
                                    Unit
                                    <input
                                      value={edit.unit}
                                      onChange={(event) => setEdit({ ...edit, unit: event.target.value })}
                                    />
                                  </label>
                                  <label>
                                    Sex
                                    <select
                                      value={edit.sex}
                                      onChange={(event) => setEdit({ ...edit, sex: event.target.value })}
                                    >
                                      <option value="any">Any</option>
                                      <option value="male">Male</option>
                                      <option value="female">Female</option>
                                    </select>
                                  </label>
                                  <label className="lab-ranges__wide">
                                    Source
                                    <input
                                      value={edit.sourceTitle}
                                      onChange={(event) => setEdit({ ...edit, sourceTitle: event.target.value })}
                                    />
                                  </label>
                                  <label className="lab-ranges__wide">
                                    Limitation
                                    <textarea
                                      value={edit.limitations}
                                      onChange={(event) => setEdit({ ...edit, limitations: event.target.value })}
                                    />
                                  </label>
                                  <Button busy={busyId === row.id} busyLabel="Saving…" onClick={() => saveEdit(row)}>
                                    {row.status === "approved" ? "Save" : "Save draft"}
                                  </Button>
                                </div>
                              ) : null}
                            </td>
                            <td>
                              <Badge tone={toneFor(row.status)}>{row.statusLabel}</Badge>
                            </td>
                            <td>
                              {row.sourceTitle ? (
                                <details>
                                  <summary>{row.sourceTitle}</summary>
                                  {row.sourcePublisher ? <p>{row.sourcePublisher}</p> : null}
                                  {row.sourceVersion ? <p>{row.sourceVersion}</p> : null}
                                  {row.method ? <p>{row.method}</p> : null}
                                  {row.sourceAccessed ? <p>Read {row.sourceAccessed}</p> : null}
                                  {row.limitations ? <p>{row.limitations}</p> : null}
                                  {row.sourceUrl ? (
                                    <p>
                                      <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                                        Source page
                                      </a>
                                    </p>
                                  ) : null}
                                </details>
                              ) : (
                                <span className="lab-ranges__missing">No source yet</span>
                              )}
                            </td>
                            <td className="lab-ranges__actions">
                              {canApprove(row) ? (
                                <Button
                                  busy={busyId === row.id}
                                  busyLabel="Approving…"
                                  onClick={() => run(row.id, "approve")}
                                >
                                  Approve
                                </Button>
                              ) : null}
                              {row.status === "draft" || row.status === "pending_review" || row.status === "approved" ? (
                                <Button variant="secondary" onClick={() => startEdit(row)} disabled={busyId === row.id}>
                                  Edit
                                </Button>
                              ) : null}
                              {row.status === "approved" ? (
                                <Button variant="ghost" onClick={() => run(row.id, "inactivate")} disabled={busyId !== ""}>
                                  Retire
                                </Button>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              );
            })
          : null}
      </Card>
    </div>
  );
}
