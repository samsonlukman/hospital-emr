import { useEffect, useMemo, useState } from "react";
import { returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import {
  createStaffAccount,
  fetchStaffDirectory,
  newAdminRequestId,
  saveStaffAccess,
  setStaffEnabled,
  setStaffPassword,
  staffPhotoHref,
  updateStaffProfile,
  uploadAppointmentLetter,
  uploadStaffPhoto,
} from "../../services/administration";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  AdminDepartmentId,
  StaffAccount,
  StaffCategoryId,
  StaffDirectoryPayload,
} from "../../types/administration";
import {
  emrAccessLabel,
  employmentTypeLabel,
  filterStaff,
  staffDepartmentLabel,
  staffKey,
  staffRoleLabel,
  validateStaffDraft,
  type StaffCategoryFilter,
  type StaffEmploymentFilter,
  type StaffStatusFilter,
} from "./adminView";
import {
  AddStaffDialog,
  type AddStaffDraft,
  StaffDetailDialog,
} from "./AdminDialogs";
import "./AdminWorkspace.css";

function emptyDraft(): AddStaffDraft {
  return {
    fullName: "",
    username: "",
    initialPassword: "",
    accountType: "staff",
    staffCategory: "",
    employmentType: "",
    departments: [],
    enabled: true,
    address: "",
    phone: "",
    nin: "",
    bankAccountNumber: "",
    bankName: "",
    accountName: "",
    qualification: "",
    photoFile: null,
    letterFile: null,
  };
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

export function StaffAccountsWorkspace() {
  const [payload, setPayload] = useState<StaffDirectoryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState<StaffCategoryFilter>("all");
  const [status, setStatus] = useState<StaffStatusFilter>("all");
  const [employment, setEmployment] = useState<StaffEmploymentFilter>("all");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<AddStaffDraft>(emptyDraft);
  const [selectedKey, setSelectedKey] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [busy, setBusy] = useState(false);
  const [photoStamp, setPhotoStamp] = useState<Record<string, number>>({});

  const load = async (options?: { quiet?: boolean }) => {
    const quiet = options?.quiet === true;
    if (!quiet) {
      setLoading(true);
    }
    setError("");
    try {
      setPayload(await fetchStaffDirectory());
    } catch (reason) {
      if (!quiet) {
        setPayload(null);
      }
      setError(errorMessage(reason, "Staff records could not be loaded."));
    } finally {
      if (!quiet) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const visible = useMemo(
    () => filterStaff(payload?.staff ?? [], query, department, status, employment),
    [department, employment, payload?.staff, query, status],
  );
  const applyStaff = (staff: StaffAccount) => {
    setPayload((current) =>
      current
        ? {
            ...current,
            staff: current.staff.some((row) => staffKey(row) === staffKey(staff))
              ? current.staff.map((row) => (staffKey(row) === staffKey(staff) ? { ...row, ...staff } : row))
              : [...current.staff, staff],
          }
        : current,
    );
  };

  const photoHref = (staff: StaffAccount) => {
    const href = staffPhotoHref(staff);
    const stamp = photoStamp[staffKey(staff)];
    return stamp ? `${href}${href.includes("?") ? "&" : "?"}v=${stamp}` : href;
  };

  const selectedRaw = payload?.staff.find((staff) => staffKey(staff) === selectedKey) ?? null;
  const selected = selectedRaw
    ? { ...selectedRaw, profilePictureHref: photoHref(selectedRaw) }
    : null;

  const handleCreate = async () => {
    const problem = validateStaffDraft(draft);
    if (problem) {
      setDialogError(problem);
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const { photoFile, letterFile, ...account } = draft;
      const result = await createStaffAccount({
        ...account,
        requestId: newAdminRequestId(),
      });
      const staffId = result.staff?.personUuid || result.staff?.staffId || result.staff?.userUuid || "";
      const failed: string[] = [];
      if (staffId && photoFile) {
        try {
          await uploadStaffPhoto(staffId, photoFile);
        } catch {
          failed.push("profile picture");
        }
      }
      if (staffId && letterFile) {
        try {
          await uploadAppointmentLetter(staffId, letterFile);
        } catch {
          failed.push("appointment letter");
        }
      }
      setDraft(emptyDraft());
      setAdding(false);
      await load();
      if (failed.length) {
        if (staffId) {
          setSelectedKey(staffId);
        }
        setDialogError(
          `The staff record was created, but the ${failed.join(" and ")} could not be saved. Upload ${failed.length === 1 ? "it" : "them"} on this record.`,
        );
        setNotice(result.message);
        return;
      }
      setNotice(result.message);
    } catch (reason) {
      setDialogError(errorMessage(reason, "The staff record could not be created."));
    } finally {
      setBusy(false);
    }
  };

  const handleSaveAccess = async (
    departments: AdminDepartmentId[],
    preferredDepartment: AdminDepartmentId,
  ) => {
    if (!selected?.userUuid) {
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
      await load();
      setSelectedKey("");
    } catch (reason) {
      setDialogError(errorMessage(reason, "Department access could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const handleSetEnabled = async (enabled: boolean) => {
    if (!selected?.userUuid) {
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const result = await setStaffEnabled(selected.userUuid, enabled);
      setNotice(result.message);
      await load();
      setSelectedKey("");
    } catch (reason) {
      setDialogError(errorMessage(reason, "The account status could not be changed."));
    } finally {
      setBusy(false);
    }
  };

  const handleChangePassword = async (password: string) => {
    if (!selected?.userUuid) {
      throw new Error("That staff member does not have a sign-in account.");
    }
    const result = await setStaffPassword(selected.userUuid, password);
    setNotice(result.message);
  };

  const handleSaveProfile = async (body: Record<string, unknown>) => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const result = await updateStaffProfile(staffKey(selected), body);
      setNotice(result.message);
      await load();
    } catch (reason) {
      setDialogError(errorMessage(reason, "The staff record could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const handleUploadPhoto = async (file: File) => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const result = await uploadStaffPhoto(staffKey(selected), file);
      setNotice(result.message);
      if (result.staff) {
        applyStaff(result.staff);
      }
      setPhotoStamp((current) => ({ ...current, [staffKey(selected)]: Date.now() }));
      await load({ quiet: true });
    } catch (reason) {
      setDialogError(errorMessage(reason, "The profile picture could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const handleUploadLetter = async (file: File) => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      const result = await uploadAppointmentLetter(staffKey(selected), file);
      setNotice(result.message);
      if (result.staff) {
        applyStaff(result.staff);
      }
      await load({ quiet: true });
    } catch (reason) {
      setDialogError(errorMessage(reason, "The appointment letter could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const categoryOptions = payload?.staffCategories?.length
    ? payload.staffCategories
    : (payload?.departments ?? []).map((item) => ({
        id: item.id as StaffCategoryId,
        label: item.label,
        roleLabel: item.roleLabel,
        emrAccess: "account" as const,
        requiresEmploymentType: item.id === "clinical",
        requiresLogin: true,
      }));

  return (
    <div className="admin-workspace">
      <div className="admin-workspace__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/home")}>
          ← Administration
        </Button>
      </div>
      <PageHeader
        title="Staff directory"
        description="Hospital staff records, employment type, and EMR sign-in where it is needed."
      >
        <Button onClick={() => setAdding(true)}>Add staff</Button>
      </PageHeader>

      {notice ? <Alert tone="success" title={notice} /> : null}
      {error ? <Alert tone="danger" title="Staff records could not be loaded">{error}</Alert> : null}

      <div className="admin-workspace__filters" aria-label="Filter staff">
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
          Staff type
          <select
            value={department}
            onChange={(event) => setDepartment(event.target.value as StaffCategoryFilter)}
          >
            <option value="all">All staff types</option>
            {categoryOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Employment
          <select
            value={employment}
            onChange={(event) => setEmployment(event.target.value as StaffEmploymentFilter)}
          >
            <option value="all">All employment types</option>
            <option value="permanent">Permanent</option>
            <option value="external">External / Sourced</option>
            <option value="na">Not applicable</option>
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

      {loading ? <LoadingState variant="board" label="Loading staff…" /> : null}
      {!loading && !error && visible.length === 0 ? (
        <EmptyState title="No staff records match these filters." />
      ) : null}
      {!loading && visible.length > 0 ? (
        <div className="abikan-table-wrap admin-workspace__table">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Department / Role</th>
                <th>Employment type</th>
                <th>EMR access</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((staff) => (
                <tr key={staffKey(staff)}>
                  <td>
                    <span className="admin-workspace__person">
                      {staff.hasProfilePicture ? (
                        <img src={photoHref(staff)} alt="" className="admin-workspace__avatar" />
                      ) : (
                        <span className="admin-workspace__avatar admin-workspace__avatar--empty" aria-hidden="true" />
                      )}
                      <span>
                        <strong>{staff.displayName}</strong>
                        <small className="admin-workspace__hint">
                          {staff.username || "No EMR username"}
                        </small>
                      </span>
                    </span>
                  </td>
                  <td>
                    {staffDepartmentLabel(staff)}
                    <small className="admin-workspace__hint">{staffRoleLabel(staff)}</small>
                  </td>
                  <td>{employmentTypeLabel(staff)}</td>
                  <td>
                    <Badge tone={staff.emrAccess === "none" || !staff.userUuid ? "neutral" : "success"}>
                      {emrAccessLabel(staff)}
                    </Badge>
                  </td>
                  <td>
                    <Badge tone={staff.enabled ? "success" : "neutral"}>
                      {staff.userUuid ? (staff.enabled ? "Active" : "Disabled") : "On record"}
                    </Badge>
                  </td>
                  <td>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setSelectedKey(staffKey(staff));
                        setDialogError("");
                      }}
                    >
                      Manage
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {adding && payload ? (
        <AddStaffDialog
          departments={payload.departments}
          categories={categoryOptions}
          draft={draft}
          busy={busy}
          error={dialogError}
          canCreateHospitalAdministrator={
            payload.capabilities?.canCreateHospitalAdministrator === true
          }
          onChange={setDraft}
          onCancel={() => {
            setDraft(emptyDraft());
            setDialogError("");
            setAdding(false);
          }}
          onSubmit={() => void handleCreate()}
        />
      ) : null}
      {selected && payload ? (
        <StaffDetailDialog
          staff={selected}
          departments={payload.departments}
          busy={busy}
          error={dialogError}
          onClose={() => {
            setSelectedKey("");
            setDialogError("");
          }}
          onSaveAccess={(departments, preferredDepartment) =>
            void handleSaveAccess(departments, preferredDepartment)
          }
          onSetEnabled={(enabled) => void handleSetEnabled(enabled)}
          onChangePassword={handleChangePassword}
          onSaveProfile={(body) => void handleSaveProfile(body)}
          onUploadPhoto={(file) => void handleUploadPhoto(file)}
          onUploadLetter={(file) => void handleUploadLetter(file)}
          onAttendanceCodeNotice={(message) => {
            if (message) {
              setNotice(message);
            }
          }}
        />
      ) : null}
    </div>
  );
}
