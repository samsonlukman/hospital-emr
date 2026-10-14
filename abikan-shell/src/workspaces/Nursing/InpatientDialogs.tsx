import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { pendingActionLabel } from "../../utils/dataLoadState";
import type { InpatientArea, InpatientAwaiting, InpatientBed } from "../../types/inpatient";
import { availableBeds, displayBedNumber, locationLabel } from "./nursingBoard";

interface ConfirmDialogProps {
  title: string;
  confirmLabel: string;
  busy?: boolean;
  confirmDisabled?: boolean;
  error?: string;
  onClose: () => void;
  onConfirm: () => void;
  children: ReactNode;
}

export function InpatientConfirmDialog({
  title,
  confirmLabel,
  busy,
  confirmDisabled,
  error,
  onClose,
  onConfirm,
  children,
}: ConfirmDialogProps) {
  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="ward-dialog-title">
      <div className="abikan-dialog__panel cashier-confirm">
        <h2 id="ward-dialog-title">{title}</h2>
        {children}
        {error ? <p className="nursing-dialog__error">{error}</p> : null}
        <div className="cashier-confirm__actions">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={onConfirm}
            busy={busy}
            busyLabel={pendingActionLabel(confirmLabel)}
            disabled={confirmDisabled}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface WardBedPickerProps {
  areas: InpatientArea[];
  value: string;
  onChange: (bedUuid: string) => void;
  excludeBedUuid?: string;
  lockedBedUuid?: string;
  emptyLabel?: string;
}

export function WardBedPicker({
  areas,
  value,
  onChange,
  excludeBedUuid,
  lockedBedUuid,
  emptyLabel,
}: WardBedPickerProps) {
  const options = useMemo(
    () => availableBeds(areas, excludeBedUuid),
    [areas, excludeBedUuid],
  );
  const locked = options.find((row) => row.bed.bedUuid === lockedBedUuid) ?? null;
  const selectableAreas = useMemo(() => {
    const seen = new Map<string, InpatientArea>();
    for (const row of options) {
      seen.set(row.area.uuid, row.area);
    }
    return Array.from(seen.values());
  }, [options]);

  const [wardUuid, setWardUuid] = useState("");

  useEffect(() => {
    if (locked) {
      setWardUuid(locked.area.uuid);
      return;
    }
    if (value) {
      const match = options.find((row) => row.bed.bedUuid === value);
      if (match) {
        setWardUuid(match.area.uuid);
      }
      return;
    }
    setWardUuid((current) => {
      if (current && selectableAreas.some((area) => area.uuid === current)) {
        return current;
      }
      return selectableAreas.length === 1 ? selectableAreas[0].uuid : "";
    });
  }, [locked, options, selectableAreas, value]);

  if (options.length === 0) {
    return <p>{emptyLabel || "There are currently no available beds."}</p>;
  }

  const selectedArea =
    selectableAreas.find((area) => area.uuid === wardUuid) ?? (locked ? locked.area : undefined);
  const beds = selectedArea
    ? selectedArea.beds.filter(
        (bed) => bed.status === "AVAILABLE" && bed.bedUuid !== excludeBedUuid,
      )
    : [];

  return (
    <div className="nursing-bed-picker">
      <label className="nursing-dialog__field">
        <span>Ward</span>
        <select
          value={selectedArea?.uuid ?? ""}
          disabled={Boolean(locked)}
          onChange={(event) => {
            setWardUuid(event.target.value);
            onChange("");
          }}
        >
          <option value="">Choose a ward</option>
          {selectableAreas.map((area) => (
            <option key={area.uuid} value={area.uuid}>
              {area.name}
            </option>
          ))}
        </select>
      </label>
      {selectedArea ? (
        <dl>
          <div>
            <dt>Room</dt>
            <dd>{selectedArea.name}</dd>
          </div>
        </dl>
      ) : null}
      {selectedArea ? (
        <fieldset className="nursing-bed-picker__beds">
          <legend>Available beds</legend>
          {beds.length === 0 ? (
            <p>There are currently no available beds in this ward.</p>
          ) : (
            beds.map((bed) => (
              <label key={bed.bedUuid} className="nursing-bed-picker__option">
                <input
                  type="radio"
                  name="available-bed"
                  checked={value === bed.bedUuid}
                  onChange={() => onChange(bed.bedUuid)}
                />
                <span>{displayBedNumber(bed.bedNumber)}</span>
              </label>
            ))
          )}
        </fieldset>
      ) : null}
    </div>
  );
}

export function AvailableBedSelect(props: WardBedPickerProps) {
  return <WardBedPicker {...props} />;
}

interface AwaitingPatientSelectProps {
  patients: InpatientAwaiting[];
  value: string;
  onChange: (patientUuid: string) => void;
  emptyLabel?: string;
}

export function AwaitingPatientSelect({
  patients,
  value,
  onChange,
  emptyLabel,
}: AwaitingPatientSelectProps) {
  if (patients.length === 0) {
    return (
      <p>
        {emptyLabel ||
          "No patients are waiting for a bed. Search for the patient, open their chart, then assign a bed there."}
      </p>
    );
  }
  return (
    <label className="nursing-dialog__field">
      <span>Patient</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose a patient</option>
        {patients.map((row) => (
          <option key={row.patientUuid} value={row.patientUuid}>
            {row.patientName} · {row.mrn}
          </option>
        ))}
      </select>
    </label>
  );
}

interface OccupiedPatientSelectProps {
  patients: Array<{ areaName: string; bed: InpatientBed }>;
  value: string;
  onChange: (patientUuid: string) => void;
  emptyLabel?: string;
}

export function OccupiedPatientSelect({
  patients,
  value,
  onChange,
  emptyLabel,
}: OccupiedPatientSelectProps) {
  if (patients.length === 0) {
    return <p>{emptyLabel || "There are no patients on a bed right now."}</p>;
  }
  return (
    <label className="nursing-dialog__field">
      <span>Patient</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose a patient</option>
        {patients.map(({ areaName, bed }) =>
          bed.patientUuid ? (
            <option key={bed.patientUuid} value={bed.patientUuid}>
              {bed.patientName} · {bed.mrn} · {locationLabel(areaName, bed.bedNumber)}
            </option>
          ) : null,
        )}
      </select>
    </label>
  );
}

export function bedLabel(bed: Pick<InpatientBed, "areaName" | "bedNumber">): string {
  return locationLabel(bed.areaName, bed.bedNumber);
}
