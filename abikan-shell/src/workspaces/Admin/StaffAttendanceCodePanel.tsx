import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { fetchStaffAttendanceCode, setStaffAttendanceCode } from "../../services/attendance";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { StaffAccount } from "../../types/administration";
import type { StaffAttendanceCodePayload } from "../../types/attendance";
import { staffKey } from "./adminView";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

export function StaffAttendanceCodePanel({
  staff,
  onNotice,
}: {
  staff: StaffAccount;
  onNotice?: (message: string) => void;
}) {
  const staffId = staffKey(staff);
  const [payload, setPayload] = useState<StaffAttendanceCodePayload | null>(null);
  const [customCode, setCustomCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setPayload(await fetchStaffAttendanceCode(staffId));
    } catch (reason) {
      setError(errorMessage(reason, "Staff code details could not be loaded."));
    }
  };

  useEffect(() => {
    setError("");
    setCustomCode("");
    void load();
  }, [staffId]);

  const save = async (replace: boolean) => {
    setBusy(true);
    setError("");
    try {
      const result = await setStaffAttendanceCode(staffId, {
        code: customCode.trim() || undefined,
        replace,
      });
      setPayload(result);
      setCustomCode("");
      onNotice?.(result.message || "Staff code saved.");
    } catch (reason) {
      setError(errorMessage(reason, "The staff code could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const hasCode = Boolean(payload?.attendanceCode.hasCode);

  return (
    <section className="admin-attendance-code">
      <h3>Staff code</h3>
      <p className="admin-dialog__note">
        This code is what the staff member enters on Staff Log. It is not a second staff record.
      </p>
      <dl className="admin-dialog__facts">
        <div>
          <dt>Staff</dt>
          <dd>{staff.displayName}</dd>
        </div>
        <div>
          <dt>Workplace</dt>
          <dd>
            {staff.preferredDepartment?.label ||
              staff.staffCategoryLabel ||
              staff.departments[0]?.label ||
              "Workplace not set"}
          </dd>
        </div>
        <div>
          <dt>Current code</dt>
          <dd className="admin-attendance-code__value">
            {payload?.attendanceCode.code || "Not set"}
          </dd>
        </div>
      </dl>
      <label>
        Custom code (optional)
        <input
          value={customCode}
          onChange={(event) => setCustomCode(event.target.value.toUpperCase())}
          disabled={busy}
          autoComplete="off"
          maxLength={8}
          placeholder="Leave blank to create one"
        />
      </label>
      {error ? <p className="admin-dialog__error">{error}</p> : null}
      <div className="admin-dialog__actions">
        <Button onClick={() => void save(hasCode)} disabled={busy}>
          {busy ? "Saving…" : hasCode ? "Replace code" : "Create staff code"}
        </Button>
      </div>
      {payload?.attendanceCode.audit.length ? (
        <div className="admin-attendance-code__audit">
          <h4>Code history</h4>
          <ul>
            {payload.attendanceCode.audit.map((item) => (
              <li key={item.id}>
                <strong>{item.actionLabel}</strong>
                <span>{item.actorUsername}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
