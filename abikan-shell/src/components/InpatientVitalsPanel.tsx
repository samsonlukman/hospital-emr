import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert } from "./Alert";
import { calculateBmi } from "../services/openmrs/clinicalPatient";
import { VitalSignsCard } from "./VitalSignsCard";
import {
  fetchVitals,
  newVitalsRequestId,
  recordVitals,
} from "../services/inpatient";
import { PatientAccountRequestError } from "../services/patientAccount";
import type { InpatientVitalsPayload } from "../types/inpatient";
import type { VitalDraftValues } from "../services/openmrs/clinicalEncounter";
import { VITAL_CONCEPTS, type VitalConceptKey } from "../config/clinicalConcepts";
import { HOSPITAL_TIMEZONE, parseOpenmrsDateTime } from "../utils/datetime";
import {
  canRecordInpatientVitals,
  historyFromVitalsPayload,
} from "../utils/inpatientVitals";
import { InpatientConfirmDialog } from "../workspaces/Nursing/InpatientDialogs";
import "./VitalSignsCard.css";

interface Props {
  patientUuid: string;
  canRecord: boolean;
  visitUuid?: string;
  hideWhenNotAdmitted?: boolean;
}

function requestError(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "Vitals could not be loaded. Try again.";
}

function formatWhen(value: string): string {
  const date = parseOpenmrsDateTime(value);
  return date
    ? date.toLocaleString("en-NG", {
        timeZone: HOSPITAL_TIMEZONE,
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Time is recorded automatically";
}

function summaryLines(values: VitalDraftValues): string[] {
  const lines: string[] = [];
  if (values.systolic != null || values.diastolic != null) {
    lines.push(
      `Blood pressure ${values.systolic ?? "—"} / ${values.diastolic ?? "—"} mmHg`,
    );
  }
  (["temperature", "pulse", "respiratoryRate", "spo2", "weight", "height"] as VitalConceptKey[]).forEach(
    (key) => {
      const value = values[key];
      if (value == null) {
        return;
      }
      const concept = VITAL_CONCEPTS[key];
      lines.push(`${concept.label} ${value} ${concept.unit}`.trim());
    },
  );
  return lines;
}

export function InpatientVitalsPanel({
  patientUuid,
  canRecord,
  visitUuid,
  hideWhenNotAdmitted = false,
}: Props) {
  const [payload, setPayload] = useState<InpatientVitalsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAdmitted, setNotAdmitted] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [pending, setPending] = useState<VitalDraftValues | null>(null);
  const [requestId, setRequestId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [resetToken, setResetToken] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPayload(await fetchVitals(patientUuid, visitUuid));
      setNotAdmitted(false);
      setLoadError("");
    } catch (error) {
      setPayload(null);
      setNotAdmitted(
        error instanceof PatientAccountRequestError &&
          (error.code === "not_admitted" ||
            error.code === "admission_history_not_found" ||
            error.code === "no_open_visit"),
      );
      setLoadError(requestError(error));
    } finally {
      setLoading(false);
    }
  }, [patientUuid, visitUuid]);

  useEffect(() => {
    void load();
  }, [load]);

  const history = useMemo(() => historyFromVitalsPayload(payload), [payload]);
  const bmi = useMemo(() => calculateBmi(history), [history]);
  const allowRecord = canRecordInpatientVitals(canRecord, Boolean(payload) && !loading);

  if (hideWhenNotAdmitted && !loading && !payload?.activeAdmission) {
    return null;
  }

  const save = async () => {
    if (!pending || saving) {
      return;
    }
    setSaving(true);
    setSaveError("");
    try {
      const result = await recordVitals(patientUuid, pending, requestId);
      setPayload(result);
      setPending(null);
      setResetToken((value) => value + 1);
    } catch (error) {
      setSaveError(requestError(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div id="inpatient-vitals">
      {loadError && !notAdmitted ? (
        <Alert tone="danger" title="Vitals unavailable">
          <p>{loadError}</p>
        </Alert>
      ) : null}
      <VitalSignsCard
        history={history}
        bmi={bmi}
        loading={loading}
        canRecord={allowRecord}
        recordBlockedReason={
          canRecord
            ? "Vitals could not be loaded. Try again."
            : "Doctors review vitals. Nursing records them."
        }
        onRecord={
          allowRecord
            ? (values) => {
                setPending(values);
                setSaveError("");
                setRequestId(newVitalsRequestId());
              }
            : undefined
        }
        recordActionLabel="Review and record"
        saving={saving}
        resetToken={resetToken}
      />
      {pending ? (
        <InpatientConfirmDialog
          title="Record vitals"
          confirmLabel="Save vitals"
          busy={saving}
          error={saveError}
          onClose={() => {
            if (!saving) {
              setPending(null);
              setSaveError("");
            }
          }}
          onConfirm={() => {
            void save();
          }}
        >
          <p className="abikan-vital__note">
            Time is recorded automatically. These observations are added to the
            chart and do not replace earlier readings.
          </p>
          <dl className="abikan-vital__confirm">
            {summaryLines(pending).map((line) => (
              <div key={line}>
                <dt>Observation</dt>
                <dd>{line}</dd>
              </div>
            ))}
            {payload?.readings[0]?.recordedAt ? (
              <div>
                <dt>Previous reading</dt>
                <dd>{formatWhen(payload.readings[0].recordedAt)}</dd>
              </div>
            ) : null}
          </dl>
        </InpatientConfirmDialog>
      ) : null}
    </div>
  );
}
