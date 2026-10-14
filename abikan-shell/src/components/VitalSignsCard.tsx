import { useEffect, useMemo, useState } from "react";
import { VITAL_CONCEPTS, type VitalConceptKey } from "../config/clinicalConcepts";
import type { VitalDraftValues } from "../services/openmrs/clinicalEncounter";
import type { VitalReading } from "../types";
import {
  draftBmi,
  parseVitalInput,
  validateVitalDraft,
  validateVitalField,
} from "../utils/vitalValidation";
import { Button } from "./Button";
import { SectionHeader } from "./SectionHeader";
import "./VitalSignsCard.css";

interface VitalSignsCardProps {
  history: Record<string, VitalReading[]>;
  bmi: VitalReading | null;
  loading?: boolean;
  canRecord?: boolean;
  recordBlockedReason?: string;
  draft?: VitalDraftValues | null;
  onDraftChange?: (values: VitalDraftValues | null) => void;
  onRecord?: (values: VitalDraftValues) => void;
  recordActionLabel?: string;
  saving?: boolean;
  resetToken?: number;
}

interface VitalDisplay {
  key: string;
  label: string;
  value: string;
  unit: string;
  recordedAt: string;
  recordedBy: string;
  recordedAtIso: string;
}

const LATEST_ORDER = [
  "bloodPressure",
  "pulse",
  "temperature",
  "respiratoryRate",
  "spo2",
  "weight",
  "height",
  "bmi",
] as const;

const FORM_FIELDS: Array<{ key: VitalConceptKey; wide?: boolean }> = [
  { key: "temperature" },
  { key: "pulse" },
  { key: "respiratoryRate" },
  { key: "spo2" },
  { key: "systolic" },
  { key: "diastolic" },
  { key: "weight" },
  { key: "height" },
];

const EMPTY_RAW: Record<VitalConceptKey, string> = {
  systolic: "",
  diastolic: "",
  pulse: "",
  temperature: "",
  spo2: "",
  weight: "",
  respiratoryRate: "",
  height: "",
};

function latestOf(history: Record<string, VitalReading[]>, key: string): VitalReading | undefined {
  return history[key]?.[0];
}

function bloodPressureDisplay(history: Record<string, VitalReading[]>): VitalDisplay | null {
  const systolic = latestOf(history, "systolic");
  const diastolic = latestOf(history, "diastolic");
  if (!systolic && !diastolic) {
    return null;
  }
  const source = systolic ?? diastolic;
  return {
    key: "bloodPressure",
    label: "Blood Pressure",
    value: `${systolic?.value ?? "—"} / ${diastolic?.value ?? "—"}`,
    unit: "mmHg",
    recordedAt: source?.recordedAt ?? "—",
    recordedBy: source?.recordedBy ?? "—",
    recordedAtIso: source?.recordedAtIso ?? "",
  };
}

function toDisplay(reading: VitalReading): VitalDisplay {
  return {
    key: reading.key,
    label: reading.label,
    value: reading.value,
    unit: reading.unit,
    recordedAt: reading.recordedAt,
    recordedBy: reading.recordedBy,
    recordedAtIso: reading.recordedAtIso,
  };
}

function historyRows(history: Record<string, VitalReading[]>, bmi: VitalReading | null): VitalDisplay[] {
  const rows: VitalDisplay[] = [];
  const systolicRows = history.systolic ?? [];
  const diastolicByIso = new Map((history.diastolic ?? []).map((row) => [row.recordedAtIso, row]));
  const usedDiastolic = new Set<string>();

  systolicRows.forEach((systolic) => {
    const diastolic = diastolicByIso.get(systolic.recordedAtIso);
    if (diastolic) {
      usedDiastolic.add(diastolic.recordedAtIso);
    }
    rows.push({
      key: `bp-${systolic.recordedAtIso}-${systolic.value}`,
      label: "Blood Pressure",
      value: `${systolic.value} / ${diastolic?.value ?? "—"}`,
      unit: "mmHg",
      recordedAt: systolic.recordedAt,
      recordedBy: systolic.recordedBy,
      recordedAtIso: systolic.recordedAtIso,
    });
  });

  (history.diastolic ?? []).forEach((diastolic) => {
    if (usedDiastolic.has(diastolic.recordedAtIso)) {
      return;
    }
    rows.push({
      key: `dia-${diastolic.recordedAtIso}`,
      label: "Diastolic",
      value: diastolic.value,
      unit: diastolic.unit,
      recordedAt: diastolic.recordedAt,
      recordedBy: diastolic.recordedBy,
      recordedAtIso: diastolic.recordedAtIso,
    });
  });

  Object.entries(history).forEach(([key, readings]) => {
    if (key === "systolic" || key === "diastolic") {
      return;
    }
    readings.forEach((reading, index) => {
      rows.push({
        ...toDisplay(reading),
        key: `${reading.key}-${reading.recordedAtIso}-${index}`,
      });
    });
  });

  if (bmi) {
    rows.push({ ...toDisplay(bmi), key: "bmi-calculated" });
  }

  return rows.sort((left, right) => right.recordedAtIso.localeCompare(left.recordedAtIso));
}

function valuesFromRaw(raw: Record<VitalConceptKey, string>): VitalDraftValues {
  const values: VitalDraftValues = {};
  (Object.keys(VITAL_CONCEPTS) as VitalConceptKey[]).forEach((key) => {
    const parsed = parseVitalInput(raw[key]);
    if (parsed !== undefined && !Number.isNaN(parsed)) {
      values[key] = parsed;
    }
  });
  return values;
}

export function VitalSignsCard({
  history,
  bmi,
  loading,
  canRecord = false,
  recordBlockedReason,
  draft,
  onDraftChange,
  onRecord,
  recordActionLabel,
  saving = false,
  resetToken = 0,
}: VitalSignsCardProps) {
  const [view, setView] = useState<"latest" | "history">("latest");
  const [formOpen, setFormOpen] = useState(false);
  const [raw, setRaw] = useState<Record<VitalConceptKey, string>>(EMPTY_RAW);

  useEffect(() => {
    setRaw(EMPTY_RAW);
    setFormOpen(false);
  }, [resetToken]);

  const latestItems = useMemo(() => {
    const items: VitalDisplay[] = [];
    const pressure = bloodPressureDisplay(history);
    if (pressure) {
      items.push(pressure);
    }
    ["pulse", "temperature", "respiratoryRate", "spo2", "weight", "height"].forEach((key) => {
      const reading = latestOf(history, key);
      if (reading) {
        items.push(toDisplay(reading));
      }
    });
    if (bmi) {
      items.push(toDisplay(bmi));
    }
    return items.sort(
      (left, right) =>
        LATEST_ORDER.indexOf(left.key as (typeof LATEST_ORDER)[number]) -
        LATEST_ORDER.indexOf(right.key as (typeof LATEST_ORDER)[number]),
    );
  }, [history, bmi]);

  const previous = useMemo(() => historyRows(history, bmi), [history, bmi]);
  const draftValues = valuesFromRaw(raw);
  const issues = validateVitalDraft(draftValues, raw);
  const previewBmi = draftBmi(draftValues);
  const draftCount = draft ? Object.values(draft).filter((value) => value != null).length : 0;

  const applyDraft = () => {
    if (issues.blocking.length > 0 || saving) {
      return;
    }
    if (onRecord) {
      onRecord(draftValues);
      return;
    }
    onDraftChange?.(draftValues);
    setFormOpen(false);
  };

  const clearDraft = () => {
    setRaw(EMPTY_RAW);
    onDraftChange?.(null);
    setFormOpen(false);
  };

  return (
    <section className="abikan-vital" aria-label="Vital signs">
      <SectionHeader
        title="Vitals"
        action={
          <div className="abikan-vital__actions">
            <div className="abikan-vital__toggle" role="tablist" aria-label="Vital view">
              <button
                type="button"
                role="tab"
                aria-selected={view === "latest"}
                className={view === "latest" ? "is-active" : ""}
                onClick={() => setView("latest")}
              >
                Latest
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === "history"}
                className={view === "history" ? "is-active" : ""}
                onClick={() => setView("history")}
                disabled={previous.length === 0}
              >
                History
              </button>
            </div>
            {canRecord ? (
              <button
                type="button"
                className="abikan-vital__record is-live"
                onClick={() => setFormOpen((open) => !open)}
              >
                {formOpen ? "Close form" : draft && !onRecord ? "Edit draft vitals" : "Record vitals"}
              </button>
            ) : (
              <span className="abikan-vital__blocked">{recordBlockedReason}</span>
            )}
          </div>
        }
      />
      {formOpen && canRecord ? (
        <div className="abikan-vital__form">
          <div className="abikan-vital__form-grid">
            {FORM_FIELDS.map(({ key }) => {
              const concept = VITAL_CONCEPTS[key];
              const issue = validateVitalField(key, raw[key]);
              return (
                <label key={key} className="abikan-vital__field">
                  <span>
                    {concept.label}
                    <em>{concept.unit}</em>
                  </span>
                  <input
                    inputMode="decimal"
                    value={raw[key]}
                    onChange={(event) =>
                      setRaw((current) => ({ ...current, [key]: event.target.value }))
                    }
                    disabled={saving}
                    aria-invalid={issue?.level === "block"}
                  />
                  {issue ? (
                    <small className={issue.level === "block" ? "is-block" : "is-warn"}>
                      {issue.message}
                    </small>
                  ) : null}
                </label>
              );
            })}
          </div>
          {previewBmi ? (
            <p className="abikan-vital__bmi-preview">
              BMI {previewBmi} (calculated, not saved as an observation)
            </p>
          ) : null}
          {issues.warnings.length > 0 ? (
            <p className="abikan-vital__form-warn">
              Unusual values can still be saved: {issues.warnings.join(" · ")}
            </p>
          ) : null}
          {issues.blocking.length > 0 ? (
            <p className="abikan-vital__form-block">{issues.blocking.join(" · ")}</p>
          ) : null}
          <div className="abikan-vital__form-actions">
            <Button
              variant="primary"
              disabled={issues.blocking.length > 0}
              busy={saving}
              busyLabel="Saving…"
              onClick={applyDraft}
            >
              {recordActionLabel || (onRecord ? "Record vitals" : "Add to consultation")}
            </Button>
            <Button variant="secondary" onClick={clearDraft} disabled={saving}>
              Clear
            </Button>
          </div>
        </div>
      ) : null}
      {draft && !formOpen && !onRecord ? (
        <p className="abikan-vital__draft">
          {draftCount} vital{draftCount === 1 ? "" : "s"} ready to save with this consultation.
          BMI is calculated after height and weight are recorded, and is not written separately.
        </p>
      ) : null}
      {loading ? (
        <p className="abikan-vital__empty">Loading vitals…</p>
      ) : latestItems.length === 0 ? (
        <p className="abikan-vital__empty">No vitals recorded.</p>
      ) : view === "latest" ? (
        <div className="abikan-vital__grid">
          {latestItems.map((item) => (
            <div key={item.key} className="abikan-vital__item">
              <p className="abikan-vital__label">{item.label}</p>
              <p className="abikan-vital__value">
                {item.value}
                {item.unit ? <span>{item.unit}</span> : null}
              </p>
              <p className="abikan-vital__when">{item.recordedAt}</p>
              <p className="abikan-vital__who">{item.recordedBy}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Observation</th>
                <th>Value</th>
                <th>Recorded</th>
                <th>Recorded by</th>
              </tr>
            </thead>
            <tbody>
              {previous.map((row) => (
                <tr key={row.key}>
                  <td>{row.label}</td>
                  <td>
                    {row.value}
                    {row.unit ? ` ${row.unit}` : ""}
                  </td>
                  <td>{row.recordedAt}</td>
                  <td>{row.recordedBy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
