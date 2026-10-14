import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { fetchAdminStaffAudit } from "../../services/administration";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { AdminStaffAuditPayload } from "../../types/administration";
import { auditChangeSummary, auditOutcomeLabel, formatAuditTime } from "./adminAnalytics";
import "./AdminWorkspace.css";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

function outcomeTone(outcome: string): "success" | "danger" | "warning" | "neutral" {
  if (outcome === "success") {
    return "success";
  }
  if (outcome === "failure") {
    return "danger";
  }
  if (outcome === "pending") {
    return "warning";
  }
  return "neutral";
}

export function AdminAuditWorkspace() {
  const [payload, setPayload] = useState<AdminStaffAuditPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void fetchAdminStaffAudit()
      .then((result) => {
        if (!cancelled) {
          setPayload(result);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setPayload(null);
          setError(errorMessage(reason, "Staff activity could not be loaded."));
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
  }, []);

  const events = payload?.events ?? [];

  return (
    <div className="admin-workspace admin-audit">
      <PageHeader
        title="Staff activity"
        description="Changes to staff accounts and department access. Clinical patient activity is not shown here."
      />

      {error ? <Alert tone="danger" title={error} /> : null}
      {loading ? (
        <LoadingState variant="board" label="Loading staff activity…" />
      ) : null}
      {!loading && !error && events.length === 0 ? (
        <EmptyState
          title="No staff activity yet"
          description="Account and access changes will appear here after they are saved."
        />
      ) : null}

      {events.length ? (
        <div className="admin-workspace__table admin-audit__table">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Administrator</th>
                <th>Action</th>
                <th>Staff member</th>
                <th>Result</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.eventId}>
                  <td>
                    <div>{formatAuditTime(event.occurredAt)}</div>
                    {event.requestId ? (
                      <span className="admin-audit__meta">Ref {event.requestId}</span>
                    ) : null}
                  </td>
                  <td>{event.actorUsername}</td>
                  <td>{event.actionLabel}</td>
                  <td>{event.targetUsername || "—"}</td>
                  <td>
                    <Badge tone={outcomeTone(event.outcome)}>{auditOutcomeLabel(event.outcome)}</Badge>
                  </td>
                  <td>{auditChangeSummary(event) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}