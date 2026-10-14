import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { fetchAttendanceLog } from "../../services/attendance";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { AttendanceLogPayload, AttendanceSession } from "../../types/attendance";
import { clockOrDash, statusTone } from "./adminStaffLogView";
import "./AdminWorkspace.css";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

function buildQuery(date: string, search: string, department: string, status: string): string {
  const params = new URLSearchParams({ date });
  if (search.trim()) {
    params.set("q", search.trim());
  }
  if (department) {
    params.set("department", department);
  }
  if (status) {
    params.set("status", status);
  }
  return params.toString();
}

export function AdminStaffLogWorkspace() {
  const [date, setDate] = useState("");
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [log, setLog] = useState<AttendanceLogPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const query = useMemo(
    () => (date ? buildQuery(date, search, department, status) : ""),
    [date, department, search, status],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void fetchAttendanceLog(query)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setLog(payload);
        if (!date) {
          setDate(payload.date);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setLog(null);
          setError(errorMessage(reason, "Staff log could not be loaded."));
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
  }, [date, query]);

  const go = (next: string) => {
    setDate(next);
  };

  const sessions: AttendanceSession[] = log?.sessions ?? [];

  return (
    <div className="admin-workspace admin-staff-log">
      <PageHeader
        title="Staff Log"
        description="Who signed in and signed out. Sign-in photos are kept for today only."
      />

      <div className="admin-staff-log__day">
        <h2>{log?.displayDate || "Today"}</h2>
        <div className="admin-staff-log__nav">
          <Button variant="secondary" onClick={() => log && go(log.previousDate)} disabled={!log}>
            ‹
          </Button>
          <Button variant="secondary" onClick={() => log && go(log.today)} disabled={!log || log.date === log.today}>
            Today
          </Button>
          <Button variant="secondary" onClick={() => log && go(log.nextDate)} disabled={!log}>
            ›
          </Button>
          <label>
            Date
            <input type="date" value={date} onChange={(event) => go(event.target.value)} />
          </label>
        </div>
      </div>

      <div className="admin-workspace__filters admin-staff-log__filters" aria-label="Filter staff log">
        <label>
          Staff
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name or username"
          />
        </label>
        <label>
          Workplace
          <select value={department} onChange={(event) => setDepartment(event.target.value)}>
            <option value="">All workplaces</option>
            {(log?.departments ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All statuses</option>
            {(log?.statuses ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? <Alert tone="danger" title={error} /> : null}
      {loading ? <LoadingState variant="board" label="Loading staff log…" /> : null}

      {!loading && !error && sessions.length === 0 ? (
        <EmptyState
          title="No staff log for this day"
          description="Sign-in and sign-out records will appear here after staff use Staff Log."
        />
      ) : null}

      {!loading && sessions.length > 0 ? (
        <div className="admin-staff-log__table">
          <table>
            <thead>
              <tr>
                <th>Photo</th>
                <th>Staff</th>
                <th>Workplace</th>
                <th>Sign In</th>
                <th>Sign Out</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.hasPhoto && row.photoHref ? (
                      <img src={row.photoHref} alt="" className="admin-staff-log__face" />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <strong>{row.displayName}</strong>
                  </td>
                  <td>{row.workplaceLabel}</td>
                  <td>{clockOrDash(row.signInLocalTime)}</td>
                  <td>{clockOrDash(row.signOutLocalTime)}</td>
                  <td>
                    <Badge tone={statusTone(row.status)}>{row.statusLabel}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
