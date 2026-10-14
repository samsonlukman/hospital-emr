import { useEffect, useId, useState, type ReactNode } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import type {
  AdminAccountType,
  AdminDepartment,
  AdminDepartmentId,
  StaffAccount,
  StaffCategory,
  StaffCategoryId,
  StaffEmploymentType,
  StaffHrProfile,
} from "../../types/administration";
import { appointmentLetterHref, staffPhotoHref } from "../../services/administration";
import {
  emrAccessLabel,
  employmentTypeLabel,
  isNonLoginCategory,
  providerStatusLabel,
  showsHrFields,
  showsLoginFields,
  signInPasswordProblem,
  staffKey,
  staffRoleLabel,
} from "./adminView";
import { StaffAttendanceCodePanel } from "./StaffAttendanceCodePanel";

export interface AddStaffDraft {
  fullName: string;
  username: string;
  initialPassword: string;
  accountType: AdminAccountType;
  staffCategory: StaffCategoryId | "";
  employmentType: StaffEmploymentType | "";
  departments: AdminDepartmentId[];
  enabled: boolean;
  address: string;
  phone: string;
  nin: string;
  bankAccountNumber: string;
  bankName: string;
  accountName: string;
  qualification: string;
  photoFile: File | null;
  letterFile: File | null;
}

interface AddStaffDialogProps {
  departments: AdminDepartment[];
  categories: StaffCategory[];
  draft: AddStaffDraft;
  busy: boolean;
  error: string;
  canCreateHospitalAdministrator: boolean;
  onChange: (draft: AddStaffDraft) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

function DepartmentChoices({
  departments,
  selected,
  disabled,
  onChange,
}: {
  departments: AdminDepartment[];
  selected: AdminDepartmentId[];
  disabled?: boolean;
  onChange: (next: AdminDepartmentId[]) => void;
}) {
  return (
    <fieldset className="admin-dialog__departments" disabled={disabled}>
      <legend>Department access</legend>
      {departments.map((department) => (
        <label key={department.id}>
          <input
            type="checkbox"
            checked={selected.includes(department.id)}
            onChange={(event) => {
              onChange(
                event.target.checked
                  ? [...selected, department.id]
                  : selected.filter((item) => item !== department.id),
              );
            }}
          />
          <span>
            <strong>{department.label}</strong>
            <small>{department.roleLabel}</small>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

function FilePick({
  label,
  accept,
  busy,
  hasFile,
  emptyHint,
  savedHint,
  pendingHint,
  extra,
  onPick,
}: {
  label: string;
  accept: string;
  busy: boolean;
  hasFile: boolean;
  emptyHint: string;
  savedHint: string;
  pendingHint?: string;
  extra?: ReactNode;
  onPick: (file: File) => void;
}) {
  const inputId = useId();
  const [pickedName, setPickedName] = useState("");

  useEffect(() => {
    if (hasFile) {
      setPickedName("");
    }
  }, [hasFile]);

  const status = pickedName ? pickedName : hasFile ? "On this record" : "No file yet";

  return (
    <div className="admin-dialog__file">
      <span className="admin-dialog__file-label" id={`${inputId}-label`}>
        {label}
      </span>
      <span className="admin-dialog__file-row">
        <input
          id={inputId}
          className="admin-dialog__file-input"
          type="file"
          accept={accept}
          disabled={busy}
          aria-labelledby={`${inputId}-label`}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              setPickedName(file.name);
              onPick(file);
            }
            event.target.value = "";
          }}
        />
        <label htmlFor={inputId} className="admin-dialog__file-button">
          {busy ? "Saving…" : hasFile || pickedName ? "Replace file" : "Choose file"}
        </label>
        <strong className="admin-dialog__file-status">{status}</strong>
      </span>
      <small>
        {hasFile
          ? savedHint
          : pickedName
            ? pendingHint || "Saving this file to the staff record."
            : emptyHint}
      </small>
      {extra}
    </div>
  );
}

function HrFields({
  value,
  busy,
  onChange,
}: {
  value: StaffHrProfile;
  busy: boolean;
  onChange: (next: StaffHrProfile) => void;
}) {
  const set = (key: keyof StaffHrProfile, next: string) => onChange({ ...value, [key]: next });
  return (
    <div className="admin-dialog__hr">
      <label>
        Phone number
        <input value={value.phone} onChange={(event) => set("phone", event.target.value)} disabled={busy} />
      </label>
      <label>
        Address
        <input value={value.address} onChange={(event) => set("address", event.target.value)} disabled={busy} />
      </label>
      <label>
        Qualification
        <input
          value={value.qualification}
          onChange={(event) => set("qualification", event.target.value)}
          placeholder="MBBS, RN/RM, B.Pharm"
          disabled={busy}
        />
      </label>
      <label>
        NIN
        <input value={value.nin} onChange={(event) => set("nin", event.target.value)} disabled={busy} autoComplete="off" />
      </label>
      <label>
        Bank name
        <input value={value.bankName} onChange={(event) => set("bankName", event.target.value)} disabled={busy} />
      </label>
      <label>
        Account number
        <input
          value={value.bankAccountNumber}
          onChange={(event) => set("bankAccountNumber", event.target.value)}
          disabled={busy}
          autoComplete="off"
        />
      </label>
      <label>
        Name on account
        <input value={value.accountName} onChange={(event) => set("accountName", event.target.value)} disabled={busy} />
      </label>
    </div>
  );
}

export function AddStaffDialog({
  departments,
  categories,
  draft,
  busy,
  error,
  canCreateHospitalAdministrator,
  onChange,
  onCancel,
  onSubmit,
}: AddStaffDialogProps) {
  const isHospitalAdministrator = draft.accountType === "hospital_administrator";
  const category = draft.staffCategory;
  const showLogin = !isHospitalAdministrator && showsLoginFields(category, draft.accountType);
  const showHr = showsHrFields(category, draft.employmentType);
  const showEmployment = !isHospitalAdministrator && category === "clinical";
  const showDepartments = showLogin && category !== "clinical";

  return (
    <div className="admin-dialog" role="dialog" aria-modal="true" aria-labelledby="add-staff-title">
      <div className="admin-dialog__panel">
        <h2 id="add-staff-title">Add staff</h2>
        <p>Add a hospital staff record. Sign-in is only created when this role uses the EMR. After saving, set a staff code on the record so they can use Staff Log.</p>
        <form
          className="admin-dialog__form"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          {canCreateHospitalAdministrator ? (
            <fieldset className="admin-dialog__account-type" disabled={busy}>
              <legend>Record type</legend>
              <label>
                <input
                  type="radio"
                  name="accountType"
                  checked={draft.accountType === "staff"}
                  onChange={() => onChange({ ...draft, accountType: "staff" })}
                />
                <span className="admin-dialog__account-type-copy">
                  <span className="admin-dialog__account-type-title">Staff</span>
                  <span className="admin-dialog__account-type-description">
                    Hospital directory record, with EMR access only when the role needs it
                  </span>
                </span>
              </label>
              <label>
                <input
                  type="radio"
                  name="accountType"
                  checked={isHospitalAdministrator}
                  onChange={() =>
                    onChange({
                      ...draft,
                      accountType: "hospital_administrator",
                      departments: [],
                      staffCategory: "hospital_admin",
                      employmentType: "",
                    })
                  }
                />
                <span className="admin-dialog__account-type-copy">
                  <span className="admin-dialog__account-type-title">Hospital Administrator</span>
                  <span className="admin-dialog__account-type-description">
                    Full hospital access: every department, plus staff records
                  </span>
                </span>
              </label>
            </fieldset>
          ) : null}

          <label>
            Full name
            <input
              value={draft.fullName}
              onChange={(event) => onChange({ ...draft, fullName: event.target.value })}
              autoComplete="name"
              placeholder="First name and surname"
              disabled={busy}
            />
          </label>

          {!isHospitalAdministrator ? (
            <label>
              Staff type
              <select
                value={category}
                onChange={(event) => {
                  const next = event.target.value as StaffCategoryId;
                  const loginDepartment = departments.some((item) => item.id === next);
                  onChange({
                    ...draft,
                    staffCategory: next,
                    employmentType: next === "clinical" ? draft.employmentType : "",
                    photoFile: next === "clinical" && draft.employmentType === "external" ? null : draft.photoFile,
                    letterFile: next === "clinical" && draft.employmentType === "external" ? null : draft.letterFile,
                    departments: loginDepartment ? [next as AdminDepartmentId] : [],
                    username: isNonLoginCategory(next) ? "" : draft.username,
                    initialPassword: isNonLoginCategory(next) ? "" : draft.initialPassword,
                  });
                }}
                disabled={busy}
              >
                <option value="">Choose staff type</option>
                {(categories.length
                  ? categories.filter((item) => item.id !== "hospital_admin")
                  : departments.map((item) => ({
                      id: item.id,
                      label: item.label,
                      roleLabel: item.roleLabel,
                    }))
                ).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {showEmployment ? (
            <fieldset className="admin-dialog__account-type" disabled={busy}>
              <legend>Employment type</legend>
              <label>
                <input
                  type="radio"
                  name="employmentType"
                  checked={draft.employmentType === "permanent"}
                  onChange={() => onChange({ ...draft, employmentType: "permanent" })}
                />
                <span className="admin-dialog__account-type-copy">
                  <span className="admin-dialog__account-type-title">Permanent</span>
                  <span className="admin-dialog__account-type-description">
                    Hospital employee with a full staff record
                  </span>
                </span>
              </label>
              <label>
                <input
                  type="radio"
                  name="employmentType"
                  checked={draft.employmentType === "external"}
                  onChange={() => onChange({ ...draft, employmentType: "external", photoFile: null, letterFile: null })}
                />
                <span className="admin-dialog__account-type-copy">
                  <span className="admin-dialog__account-type-title">External / Sourced</span>
                  <span className="admin-dialog__account-type-description">
                    Visiting clinician with EMR sign-in only
                  </span>
                </span>
              </label>
            </fieldset>
          ) : null}

          {isNonLoginCategory(category) ? (
            <p className="admin-dialog__note">EMR access: No account. This person will not be able to sign in.</p>
          ) : null}

          {showHr ? (
            <>
              <HrFields
                value={{
                  address: draft.address,
                  phone: draft.phone,
                  nin: draft.nin,
                  bankAccountNumber: draft.bankAccountNumber,
                  bankName: draft.bankName,
                  accountName: draft.accountName,
                  qualification: draft.qualification,
                }}
                busy={busy}
                onChange={(hr) => onChange({ ...draft, ...hr })}
              />
              <div className="admin-dialog__uploads">
                <FilePick
                  label="Profile picture"
                  accept="image/jpeg,image/png,image/webp"
                  busy={busy}
                  hasFile={false}
                  emptyHint="JPEG, PNG, or WebP. This picture shows when the staff member signs in."
                  savedHint=""
                  pendingHint="This picture will be saved with the staff record."
                  onPick={(file) => onChange({ ...draft, photoFile: file })}
                />
                <FilePick
                  label="Letter of appointment"
                  accept="application/pdf,image/jpeg,image/png"
                  busy={busy}
                  hasFile={false}
                  emptyHint="PDF, JPEG, or PNG. Only Hospital Admin can open this file."
                  savedHint=""
                  pendingHint="This letter will be saved with the staff record."
                  onPick={(file) => onChange({ ...draft, letterFile: file })}
                />
              </div>
            </>
          ) : null}

          {(showLogin || isHospitalAdministrator) ? (
            <>
              <label>
                Username
                <input
                  value={draft.username}
                  onChange={(event) =>
                    onChange({ ...draft, username: event.target.value.toLowerCase() })
                  }
                  autoCapitalize="none"
                  autoComplete="off"
                  placeholder="firstname.surname"
                  disabled={busy}
                />
              </label>
              <label>
                Initial sign-in password
                <input
                  type="password"
                  value={draft.initialPassword}
                  onChange={(event) => onChange({ ...draft, initialPassword: event.target.value })}
                  autoComplete="new-password"
                  disabled={busy}
                />
                <small>
                  At least 8 characters, with uppercase, lowercase, and a number. It is used only to
                  create the sign-in and is not kept on the staff record.
                </small>
              </label>
            </>
          ) : null}

          {showDepartments ? (
            <DepartmentChoices
              departments={departments}
              selected={draft.departments}
              disabled={busy}
              onChange={(selected) => onChange({ ...draft, departments: selected })}
            />
          ) : null}
          {isHospitalAdministrator ? (
            <p className="admin-dialog__note">
              Hospital Administrators can open every department and manage staff, the same as the
              main administrator account.
            </p>
          ) : null}
          {showLogin || isHospitalAdministrator ? (
            <label className="admin-dialog__check">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) => onChange({ ...draft, enabled: event.target.checked })}
                disabled={busy}
              />
              Account can sign in immediately
            </label>
          ) : null}
          {error ? <p className="admin-dialog__error">{error}</p> : null}
          <div className="admin-dialog__actions">
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : isNonLoginCategory(category) ? "Save staff record" : "Create account"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface StaffDetailDialogProps {
  staff: StaffAccount;
  departments: AdminDepartment[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onSaveAccess: (
    departments: AdminDepartmentId[],
    preferredDepartment: AdminDepartmentId,
  ) => void;
  onSetEnabled: (enabled: boolean) => void;
  onChangePassword?: (password: string) => Promise<void> | void;
  onSaveProfile?: (body: Record<string, unknown>) => void;
  onUploadPhoto?: (file: File) => void;
  onUploadLetter?: (file: File) => void;
  onAttendanceCodeNotice?: (message: string) => void;
}

export function StaffDetailDialog({
  staff,
  departments,
  busy,
  error,
  onClose,
  onSaveAccess,
  onSetEnabled,
  onChangePassword,
  onSaveProfile,
  onUploadPhoto,
  onUploadLetter,
  onAttendanceCodeNotice,
}: StaffDetailDialogProps) {
  const [selected, setSelected] = useState<AdminDepartmentId[]>(
    staff.departments.map((item) => item.id),
  );
  const [preferred, setPreferred] = useState<AdminDepartmentId | undefined>(
    staff.preferredDepartment?.id ?? staff.departments[0]?.id,
  );
  const [confirmDisable, setConfirmDisable] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordNotice, setPasswordNotice] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [fullName, setFullName] = useState(staff.displayName);
  const [employmentType, setEmploymentType] = useState(staff.employmentType || "");
  const [hr, setHr] = useState<StaffHrProfile>({
    address: staff.hr?.address || "",
    phone: staff.hr?.phone || "",
    nin: staff.hr?.nin || "",
    bankAccountNumber: staff.hr?.bankAccountNumber || "",
    bankName: staff.hr?.bankName || "",
    accountName: staff.hr?.accountName || "",
    qualification: staff.hr?.qualification || "",
  });
  const isHospitalAdministrator = staff.accountType === "hospital_administrator";
  const category = staff.staffCategory || (isHospitalAdministrator ? "hospital_admin" : staff.departments[0]?.id);
  const hasLogin = Boolean(staff.userUuid) && staff.emrAccess !== "none";
  const showHr = showsHrFields(category, employmentType || staff.employmentType || "");

  useEffect(() => {
    const next = staff.departments.map((item) => item.id);
    setSelected(next);
    setPreferred(staff.preferredDepartment?.id ?? next[0]);
    setConfirmDisable(false);
    setNewPassword("");
    setConfirmPassword("");
    setPasswordError("");
    setPasswordNotice("");
    setPasswordBusy(false);
    setFullName(staff.displayName);
    setEmploymentType(staff.employmentType || "");
    setHr({
      address: staff.hr?.address || "",
      phone: staff.hr?.phone || "",
      nin: staff.hr?.nin || "",
      bankAccountNumber: staff.hr?.bankAccountNumber || "",
      bankName: staff.hr?.bankName || "",
      accountName: staff.hr?.accountName || "",
      qualification: staff.hr?.qualification || "",
    });
  }, [staff]);

  useEffect(() => {
    if (preferred && !selected.includes(preferred) && selected[0]) {
      setPreferred(selected[0]);
    }
  }, [preferred, selected]);

  return (
    <div className="admin-dialog" role="dialog" aria-modal="true" aria-labelledby="staff-detail-title">
      <div className="admin-dialog__panel">
        <div className="admin-dialog__heading">
          <div className="admin-dialog__identity">
            {staff.hasProfilePicture ? (
              <img
                className="admin-dialog__photo"
                src={staffPhotoHref(staff)}
                alt="Staff profile picture"
              />
            ) : (
              <span className="admin-dialog__photo admin-dialog__photo--empty" aria-hidden="true" />
            )}
            <div>
              <h2 id="staff-detail-title">{staff.displayName}</h2>
              <p>{staff.username || "No EMR account"}</p>
            </div>
          </div>
          <Badge tone={staff.enabled ? "success" : "neutral"}>
            {hasLogin ? (staff.enabled ? "Active" : "Disabled") : "Directory only"}
          </Badge>
        </div>
        {onUploadPhoto ? (
          <FilePick
            label="Profile picture"
            accept="image/jpeg,image/png,image/webp"
            busy={busy}
            hasFile={Boolean(staff.hasProfilePicture)}
            emptyHint="JPEG, PNG, or WebP. This picture shows when the staff member signs in."
            savedHint="This picture is saved and shows when they sign in."
            onPick={onUploadPhoto}
          />
        ) : null}
        {showHr && onUploadLetter ? (
          <FilePick
            label="Letter of appointment"
            accept="application/pdf,image/jpeg,image/png"
            busy={busy}
            hasFile={Boolean(staff.hasAppointmentLetter)}
            emptyHint={
              staff.hasAppointmentLetter
                ? "PDF, JPEG, or PNG. Only Hospital Admin can open this file."
                : "No letter is on this record yet. PDF, JPEG, or PNG. Only Hospital Admin can open this file."
            }
            savedHint="A letter is saved. Only Hospital Admin can open it. "
            extra={
              staff.hasAppointmentLetter ? (
                <a href={appointmentLetterHref(staffKey(staff))} target="_blank" rel="noreferrer">
                  View current letter
                </a>
              ) : null
            }
            onPick={onUploadLetter}
          />
        ) : null}
        <dl className="admin-dialog__facts">
          <div>
            <dt>Staff type</dt>
            <dd>{staffRoleLabel(staff)}</dd>
          </div>
          <div>
            <dt>Employment type</dt>
            <dd>{employmentTypeLabel(staff)}</dd>
          </div>
          <div>
            <dt>EMR access</dt>
            <dd>{emrAccessLabel(staff)}</dd>
          </div>
          <div>
            <dt>Clinical profile</dt>
            <dd>{providerStatusLabel(staff)}</dd>
          </div>
        </dl>

        {onSaveProfile ? (
        <label>
          Full name
          <input value={fullName} onChange={(event) => setFullName(event.target.value)} disabled={busy} />
        </label>
        ) : null}

        {onSaveProfile && category === "clinical" ? (
          <fieldset className="admin-dialog__account-type" disabled={busy}>
            <legend>Employment type</legend>
            <label>
              <input
                type="radio"
                checked={employmentType === "permanent"}
                onChange={() => setEmploymentType("permanent")}
              />
              <span className="admin-dialog__account-type-copy">
                <span className="admin-dialog__account-type-title">Permanent</span>
              </span>
            </label>
            <label>
              <input
                type="radio"
                checked={employmentType === "external"}
                onChange={() => setEmploymentType("external")}
              />
              <span className="admin-dialog__account-type-copy">
                <span className="admin-dialog__account-type-title">External / Sourced</span>
              </span>
            </label>
          </fieldset>
        ) : null}

        {showHr && onSaveProfile ? <HrFields value={hr} busy={busy} onChange={setHr} /> : null}

        <StaffAttendanceCodePanel staff={staff} onNotice={onAttendanceCodeNotice} />

        {isHospitalAdministrator ? (
          <p className="admin-dialog__note">
            This account can open every department. Department boxes are not needed.
          </p>
        ) : hasLogin ? (
          <>
            <DepartmentChoices
              departments={departments}
              selected={selected}
              disabled={busy}
              onChange={setSelected}
            />
            <label>
              Default department
              <select
                value={preferred ?? ""}
                onChange={(event) => setPreferred(event.target.value as AdminDepartmentId)}
                disabled={busy || !selected.length}
              >
                {departments
                  .filter((department) => selected.includes(department.id))
                  .map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.label}
                    </option>
                  ))}
              </select>
            </label>
          </>
        ) : (
          <p className="admin-dialog__note">EMR access: No account. This person cannot sign in.</p>
        )}

        {hasLogin && onChangePassword ? (
          <fieldset className="admin-dialog__password" disabled={busy || passwordBusy}>
            <legend>Sign-in password</legend>
            <p className="admin-dialog__note">
              Set a new password for this staff member. Tell them the password in person. It is not
              saved on the staff record.
            </p>
            <label>
              New password
              <input
                type="password"
                value={newPassword}
                onChange={(event) => {
                  setNewPassword(event.target.value);
                  setPasswordError("");
                  setPasswordNotice("");
                }}
                autoComplete="new-password"
                disabled={busy || passwordBusy}
              />
            </label>
            <label>
              Confirm new password
              <input
                type="password"
                value={confirmPassword}
                onChange={(event) => {
                  setConfirmPassword(event.target.value);
                  setPasswordError("");
                  setPasswordNotice("");
                }}
                autoComplete="new-password"
                disabled={busy || passwordBusy}
              />
              <small>At least 8 characters, with uppercase, lowercase, and a number.</small>
            </label>
            {passwordError ? <p className="admin-dialog__error">{passwordError}</p> : null}
            {passwordNotice ? <p className="admin-dialog__note">{passwordNotice}</p> : null}
            <div className="admin-dialog__actions">
              <Button
                variant="secondary"
                disabled={busy || passwordBusy || !newPassword}
                onClick={() => {
                  const problem =
                    newPassword !== confirmPassword
                      ? "The two passwords do not match."
                      : signInPasswordProblem(newPassword, staff.username || "");
                  if (problem) {
                    setPasswordError(problem);
                    return;
                  }
                  setPasswordBusy(true);
                  setPasswordError("");
                  Promise.resolve(onChangePassword(newPassword))
                    .then(() => {
                      setNewPassword("");
                      setConfirmPassword("");
                      setPasswordNotice(
                        "Sign-in password updated. Tell the staff member the new password in person.",
                      );
                    })
                    .catch((reason: unknown) => {
                      setPasswordError(
                        reason instanceof Error ? reason.message : "The sign-in password could not be changed.",
                      );
                    })
                    .finally(() => {
                      setPasswordBusy(false);
                    });
                }}
              >
                {passwordBusy ? "Saving…" : "Save password"}
              </Button>
            </div>
          </fieldset>
        ) : null}

        {confirmDisable ? (
          <div className="admin-dialog__confirm">
            <strong>Disable this sign-in?</strong>
            <p>Disabled staff cannot sign in. The staff record and history stay in place.</p>
            <div className="admin-dialog__actions">
              <Button variant="secondary" onClick={() => setConfirmDisable(false)} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={() => onSetEnabled(false)} disabled={busy}>
                {busy ? "Disabling…" : "Disable account"}
              </Button>
            </div>
          </div>
        ) : null}

        {error ? <p className="admin-dialog__error">{error}</p> : null}
        <div className="admin-dialog__actions admin-dialog__actions--split">
          <div>
            {hasLogin && staff.enabled ? (
              <Button variant="ghost" onClick={() => setConfirmDisable(true)} disabled={busy}>
                Disable account
              </Button>
            ) : null}
            {hasLogin && !staff.enabled ? (
              <Button variant="secondary" onClick={() => onSetEnabled(true)} disabled={busy}>
                {busy ? "Enabling…" : "Enable account"}
              </Button>
            ) : null}
          </div>
          <div className="admin-dialog__actions">
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Close
            </Button>
            {onSaveProfile ? (
            <Button
              variant="secondary"
              onClick={() =>
                onSaveProfile({
                  fullName,
                  staffCategory: category,
                  employmentType: category === "clinical" ? employmentType : "",
                  ...hr,
                })
              }
              disabled={busy}
            >
              {busy ? "Saving…" : "Save record"}
            </Button>
            ) : null}
            {hasLogin && !isHospitalAdministrator ? (
              <Button
                onClick={() => preferred && onSaveAccess(selected, preferred)}
                disabled={busy || !selected.length || !preferred}
              >
                {busy ? "Saving…" : "Save access"}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
