import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import {
  callReceptionForNursingTreatment,
  createNursingTreatmentNote,
  fetchNursingTreatmentQueue,
  newInpatientRequestId,
  recordNursingTreatment,
} from "../../services/inpatient";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { NursingTreatmentItem } from "../../types/inpatient";
import { returnToPreviousScreen } from "../../app/hashRoute";
import { InpatientConfirmDialog } from "./InpatientDialogs";
import "./NursingTreatmentVisitWorkspace.css";

interface Props {
  visitUuid: string;
}

type Outcome = "given" | "held" | "not-done";

function message(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "The treatment visit could not be loaded.";
}

export function NursingTreatmentVisitWorkspace({ visitUuid }: Props) {
  const [item, setItem] = useState<NursingTreatmentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState<Outcome>("given");
  const [reason, setReason] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [calling, setCalling] = useState(false);
  const [note, setNote] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);

  useEffect(() => {
    fetchNursingTreatmentQueue()
      .then((result) => {
        setItem(result.items.find((row) => row.visitUuid === visitUuid) || null);
        setError("");
      })
      .catch((reasonValue) => setError(message(reasonValue)))
      .finally(() => setLoading(false));
  }, [visitUuid]);

  const record = async () => {
    if (!item || !item.orderUuid || saving || (outcome !== "given" && !reason.trim())) return;
    setSaving(true);
    try {
      await recordNursingTreatment(item.patientUuid, item, outcome, reason.trim());
      setItem((current) => (current ? { ...current, status: "COMPLETED" } : current));
      setDialogOpen(false);
    } catch (reasonValue) {
      setError(message(reasonValue));
    } finally {
      setSaving(false);
    }
  };

  const callReception = async () => {
    if (!item || calling) return;
    setCalling(true);
    try {
      await callReceptionForNursingTreatment(item.patientUuid, item.visitUuid);
    } catch (reasonValue) {
      setError(message(reasonValue));
    } finally {
      setCalling(false);
    }
  };

  const saveNote = async () => {
    if (!item || !note.trim() || noteSaving) return;
    setNoteSaving(true);
    try {
      const result = await createNursingTreatmentNote(
        item.patientUuid,
        item.visitUuid,
        note.trim(),
        newInpatientRequestId(),
      );
      setItem((current) =>
        current ? { ...current, notes: [result.note, ...current.notes] } : current,
      );
      setNote("");
      setError("");
    } catch (reasonValue) {
      setError(message(reasonValue));
    } finally {
      setNoteSaving(false);
    }
  };

  return (
    <div className="nursing-desk nursing-treatment-visit">
      <button className="nursing-treatment-visit__back" type="button" onClick={() => returnToPreviousScreen("#/nursing/treatments")}>
        ← Treatment Queue
      </button>
      {error ? <Alert tone="danger" title="Treatment visit unavailable">{error}</Alert> : null}
      {loading ? (
        <p className="nursing-treatment-visit__loading">Loading treatment visit…</p>
      ) : !item ? (
        <EmptyState
          title="Treatment visit not found"
          description="It may have been closed or is no longer available."
        />
      ) : (
        <div className="nursing-treatment-visit__content">
          <header className="nursing-treatment-visit__hero">
            <div>
              <p className="nursing-treatment-visit__eyebrow">NURSING TREATMENT VISIT</p>
              <h1>{item.patientName}</h1>
              <p>Review the patient’s medicines, give the planned treatment, and document what you did.</p>
            </div>
            <span className={`nursing-treatment-visit__status is-${item.status.toLowerCase()}`}>
              {item.status === "WAITING" ? "Waiting for prescription" : item.status === "COMPLETED" ? "Completed" : "Treatment due"}
            </span>
          </header>

          <section className="nursing-treatment-visit__panel">
            <div className="nursing-treatment-visit__panel-heading">
              <div>
                <h2>Medicines on this patient’s record</h2>
                <p>These are the active prescriptions available for this visit.</p>
              </div>
            </div>
            {item.medications.length > 0 ? (
              <div className="nursing-treatment-visit__medicines">
                {item.medications.map((medicine, index) => (
                  <article className="nursing-treatment-visit__medicine" key={`${medicine.medication}-${index}`}>
                    <div className="nursing-treatment-visit__medicine-title">
                      <h3>{medicine.medication}</h3>
                      {medicine.administrationMode === "HOSPITAL_FOLLOW_UP" ? <span>Hospital treatment</span> : null}
                    </div>
                    <p>{medicine.instructions || "No written instructions."}</p>
                    <dl>
                      <div><dt>Dose</dt><dd>{[medicine.dose, medicine.doseUnits].filter((part) => part !== undefined && part !== null && String(part) !== "").join(" ") || "Not recorded"}</dd></div>
                      <div><dt>Route</dt><dd>{medicine.route || "Not recorded"}</dd></div>
                      <div><dt>Frequency</dt><dd>{medicine.frequency || "Not recorded"}</dd></div>
                      <div><dt>Duration</dt><dd>{medicine.duration ? `${medicine.duration} ${medicine.durationUnits}` : "Not recorded"}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <p className="nursing-treatment-visit__muted">No active prescriptions were found on the patient record.</p>
            )}
          </section>

          <section className="nursing-treatment-visit__panel">
            <div className="nursing-treatment-visit__panel-heading">
              <div>
                <h2>Nursing notes</h2>
                <p>Record care you provided and the patient’s response.</p>
              </div>
            </div>
            {item.notes.length > 0 ? (
              <ol className="nursing-treatment-visit__notes">
                {item.notes.map((row) => (
                  <li key={row.uuid}>
                    <div><strong>{row.authorName}</strong><time>{row.recordedAt}</time></div>
                    <p>{row.content}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="nursing-treatment-visit__muted">No nursing notes recorded for this treatment visit.</p>
            )}
            <label className="nursing-treatment-visit__note-field">
              <span>What did you do for the patient?</span>
              <textarea
                rows={4}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Record the treatment given, patient response, and any follow-up needed."
              />
            </label>
            <Button variant="secondary" onClick={() => void saveNote()} disabled={noteSaving || !note.trim()}>
              {noteSaving ? "Saving note…" : "Save nursing note"}
            </Button>
          </section>
          <div className="nursing-treatment-visit__actions">
            {item.status === "DUE" ? (
              <Button variant="primary" onClick={() => setDialogOpen(true)}>
                Record treatment
              </Button>
            ) : null}
            <Button variant="secondary" onClick={() => void callReception()} disabled={calling}>
              {calling ? "Calling…" : "Call Reception"}
            </Button>
          </div>
        </div>
      )}
      {dialogOpen && item ? (
        <InpatientConfirmDialog
          title={`Record ${item.medication}`}
          confirmLabel="Save treatment"
          busy={saving}
          confirmDisabled={saving || (outcome !== "given" && !reason.trim())}
          onClose={() => {
            if (!saving) setDialogOpen(false);
          }}
          onConfirm={() => void record()}
        >
          <label>
            <span>Result</span>
            <select value={outcome} onChange={(event) => setOutcome(event.target.value as Outcome)}>
              <option value="given">Given</option>
              <option value="held">Held</option>
              <option value="not-done">Not given</option>
            </select>
          </label>
          {outcome !== "given" ? (
            <label>
              <span>Reason</span>
              <textarea rows={4} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
          ) : null}
        </InpatientConfirmDialog>
      ) : null}
    </div>
  );
}
