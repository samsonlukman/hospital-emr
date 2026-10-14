import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { ClinicalSection } from "./ClinicalSection";
import { EmptyState } from "./EmptyState";
import {
  createNursingNote,
  fetchNursingNotes,
  newNursingNoteRequestId,
} from "../services/inpatient";
import { PatientAccountRequestError } from "../services/patientAccount";
import type { NursingNotesPayload } from "../types/inpatient";
import { HOSPITAL_TIMEZONE, parseOpenmrsDateTime } from "../utils/datetime";
import { InpatientConfirmDialog } from "../workspaces/Nursing/InpatientDialogs";
import {
  canCreateNursingNote,
  canSubmitNursingNote,
  notesForAdmission,
} from "../utils/nursingNotes";
import "./NursingNotesPanel.css";

interface NursingNotesPanelProps {
  patientUuid: string;
  canCreate: boolean;
  hideWhenEmptyAndNotAdmitted?: boolean;
}

function noteDate(value: string): string {
  const date = parseOpenmrsDateTime(value);
  return date
    ? date.toLocaleDateString("en-NG", {
        timeZone: HOSPITAL_TIMEZONE,
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Date unavailable";
}

function noteTime(value: string): string {
  const date = parseOpenmrsDateTime(value);
  return date
    ? date.toLocaleTimeString("en-NG", {
        timeZone: HOSPITAL_TIMEZONE,
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Time unavailable";
}

function requestMessage(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "Nursing notes could not be loaded. Try again.";
}

export function NursingNotesPanel({
  patientUuid,
  canCreate,
  hideWhenEmptyAndNotAdmitted = false,
}: NursingNotesPanelProps) {
  const [payload, setPayload] = useState<NursingNotesPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [note, setNote] = useState("");
  const [requestId, setRequestId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPayload(await fetchNursingNotes(patientUuid));
      setLoadError("");
    } catch (error) {
      setPayload(null);
      setLoadError(requestMessage(error));
    } finally {
      setLoading(false);
    }
  }, [patientUuid]);

  useEffect(() => {
    void load();
  }, [load]);

  const notes = useMemo(() => {
    const rows = payload?.notes ?? [];
    if (!canCreate || !payload?.activeAdmissionEncounterUuid) {
      return rows;
    }
    return notesForAdmission(rows, payload.activeAdmissionEncounterUuid);
  }, [canCreate, payload]);

  if (
    hideWhenEmptyAndNotAdmitted &&
    !loading &&
    !loadError &&
    !payload?.activeAdmissionEncounterUuid &&
    notes.length === 0
  ) {
    return null;
  }

  const openDialog = () => {
    setNote("");
    setSaveError("");
    setRequestId(newNursingNoteRequestId());
    setDialogOpen(true);
  };

  const save = async () => {
    if (!canSubmitNursingNote(note, saving)) {
      return;
    }
    setSaving(true);
    setSaveError("");
    try {
      await createNursingNote(patientUuid, note, requestId);
      setDialogOpen(false);
      setNote("");
      await load();
    } catch (error) {
      setSaveError(requestMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <ClinicalSection
        id="notes"
        title="Inpatient Nursing Notes"
        description={
          canCreate
            ? "Observations recorded by nurses during this admission."
            : "Nursing observations recorded during inpatient care."
        }
        action={
          canCreateNursingNote(canCreate, payload?.activeAdmissionEncounterUuid ?? "") ? (
            <Button variant="primary" onClick={openDialog}>
              + Nursing Note
            </Button>
          ) : undefined
        }
      >
        {loadError ? (
          <Alert tone="danger" title="Nursing notes unavailable">
            {loadError}
          </Alert>
        ) : loading ? (
          <p className="nursing-notes__muted">Loading nursing notes…</p>
        ) : notes.length === 0 ? (
          <EmptyState
            title="No nursing notes recorded for this admission."
            description={
              canCreate && !payload?.activeAdmissionEncounterUuid
                ? "A nursing note can be added after the patient is admitted."
                : undefined
            }
          />
        ) : (
          <ol className="nursing-notes__list">
            {notes.map((row) => (
              <li key={row.uuid} className="nursing-notes__item">
                <div className="nursing-notes__when">
                  <time dateTime={row.recordedAt}>
                    {noteDate(row.recordedAt)} · {noteTime(row.recordedAt)}
                  </time>
                  <span>Nurse: {row.authorName}</span>
                </div>
                <p>{row.content}</p>
              </li>
            ))}
          </ol>
        )}
      </ClinicalSection>

      {dialogOpen ? (
        <InpatientConfirmDialog
          title="Add Nursing Note"
          confirmLabel="Save Nursing Note"
          busy={saving}
          confirmDisabled={!canSubmitNursingNote(note, saving)}
          error={saveError}
          onClose={() => {
            if (!saving) {
              setDialogOpen(false);
            }
          }}
          onConfirm={() => void save()}
        >
          <label className="nursing-notes__field">
            <span>Note</span>
            <textarea
              autoFocus
              rows={8}
              maxLength={10000}
              value={note}
              disabled={saving}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Record the patient observation, care provided, and response."
            />
          </label>
          <p className="nursing-notes__help">
            Your name and the current date and time are recorded automatically.
          </p>
        </InpatientConfirmDialog>
      ) : null}
    </>
  );
}
