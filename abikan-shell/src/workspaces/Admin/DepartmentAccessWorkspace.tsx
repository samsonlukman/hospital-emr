import { useEffect, useMemo, useState } from "react";
import { returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import {
  fetchDepartmentAccess,
  fetchStaffDirectory,
  saveStaffAccess,
  setStaffEnabled,
  setStaffPassword,
} from "../../services/administration";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  AdminDepartmentId,
  DepartmentAccessPayload,
  StaffDirectoryPayload,
} from "../../types/administration";
import { filterAccess, selectedAccessStaff, type StaffStatusFilter } from "./adminView";
import { StaffDetailDialog } from "./AdminDialogs";
import "./AdminWorkspace.css";

function messageOf(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

export function DepartmentAccessWorkspace() {
  const [access, setAccess] = useState<DepartmentAccessPayload | null>(null);
  const [directory, setDirectory] = useState<StaffDirectoryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState<"all" | AdminDepartmentId>("all");
  const [status, setStatus] = useState<StaffStatusFilter>("all");
  const [selectedUuid, setSelectedUuid] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [accessPayload, staffPayload] = await Promise.all([
        fetchDepartmentAccess(),
        fetchStaffDirectory(),
      ]);
      setAccess(accessPayload);
      setDirectory(staffPayload);
    } catch (reason) {
      setAccess(null);
      setDirectory(null);
      setError(messageOf(reason, "Department access could not be loaded."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const visible = useMemo(
    () => filterAccess(access?.access ?? [], query, department, status),
    [access?.access, department, query, status],
  );
  const selected = selectedAccessStaff(directory?.staff ?? [], selectedUuid);

  const saveAccess = async (
    departments: AdminDepartmentId[],
    preferredDepartment: AdminDepartmentId,
  ) => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const result = await saveStaffAccess(
        selected.userUuid,
        departments,
        preferredDepartment,
      );
      setNotice(result.message);
      setSelectedUuid("");
      await load();
    } catch (reason) {
      setDialogError(messageOf(reason, "Department access could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const setEnabled = async (enabled: boolean) => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const result = await setStaffEnabled(selected.userUuid, enabled);
      setNotice(result.message);
      setSelectedUuid("");
      await load();
    } catch (reason) {
      setDialogError(messageOf(reason, "The account status could not be changed."));
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async (password: string) => {
    if (!selected?.userUuid) {
      throw new Error("That staff member does not have a sign-in account.");
    }
    const result = await setStaffPassword(selected.userUuid, password);
    setNotice(result.message);
  };

  return (
    <div className="admin-workspace">
      <div className="admin-workspace__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/home")}>
          ← Administration
        </Button>
      </div>
      <PageHeader
        title="Department access"
        description="Review and assign approved hospital department roles."
      />

      <Alert title="Approved access only">
        Departments and roles are controlled hospital options. Technical permissions cannot be
        assigned here.
      </Alert>
      {notice ? <Alert tone="success" title={notice} /> : null}
      {error ? <Alert tone="danger" title="Department access could not be loaded">{error}</Alert> : null}

      <div className="admin-workspace__filters" aria-label="Filter department access">
        <label className="admin-workspace__search">
          <span>Find staff</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name or username"
          />
        </label>
        <label>
          Department
          <select
            value={department}
            onChange={(event) =>
              setDepartment(event.target.value as "all" | AdminDepartmentId)
            }
          >
            <option value="all">All departments</option>
            {(access?.departments ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as StaffStatusFilter)}
          >
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </select>
        </label>
      </div>

      {loading ? <LoadingState variant="board" label="Loading department access…" /> : null}
      {!loading && !error && visible.length === 0 ? (
        <EmptyState title="No department access matches these filters." />
      ) : null}
      {!loading && visible.length > 0 ? (
        <div className="abikan-table-wrap admin-workspace__table">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Staff</th>
                <th>Department</th>
                <th>Role</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={`${row.userUuid}:${row.department.id}`}>
                  <td>
                    <strong>{row.displayName}</strong>
                    <small className="admin-workspace__hint">{row.username}</small>
                  </td>
                  <td>{row.department.label}</td>
                  <td>{row.department.roleLabel}</td>
                  <td>
                    <Badge tone={row.enabled ? "success" : "neutral"}>
                      {row.enabled ? "Active" : "Disabled"}
                    </Badge>
                  </td>
                  <td>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setSelectedUuid(row.userUuid);
                        setDialogError("");
                      }}
                    >
                      Edit access
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {selected && directory ? (
        <StaffDetailDialog
          staff={selected}
          departments={directory.departments}
          busy={busy}
          error={dialogError}
          onClose={() => {
            setSelectedUuid("");
            setDialogError("");
          }}
          onSaveAccess={(departments, preferredDepartment) =>
            void saveAccess(departments, preferredDepartment)
          }
          onSetEnabled={(enabled) => void setEnabled(enabled)}
          onChangePassword={changePassword}
        />
      ) : null}
    </div>
  );
}
