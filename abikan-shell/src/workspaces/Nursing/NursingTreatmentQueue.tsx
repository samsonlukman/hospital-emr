import { useCallback, useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import {
  callReceptionForNursingTreatment,
  fetchNursingTreatmentQueue,
  recordNursingTreatment,
} from "../../services/inpatient";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { NursingTreatmentItem } from "../../types/inpatient";
import { InpatientConfirmDialog } from "./InpatientDialogs";
import { openNursingTreatmentVisit } from "../../app/hashRoute";

type Outcome = "given" | "held" | "not-done";

function errorMessage(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "Treatments could not be loaded. Please try again.";
}

export function NursingTreatmentQueue() {
  const [items, setItems] = useState<NursingTreatmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<NursingTreatmentItem | null>(null);
  const [outcome, setOutcome] = useState<Outcome>("given");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [callingVisitUuid, setCallingVisitUuid] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchNursingTreatmentQueue();
      setItems(result.items || []);
      setError("");
    } catch (reasonValue) {
      setError(errorMessage(reasonValue));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = (item: NursingTreatmentItem) => {
    setSelected(item);
    setOutcome("given");
    setReason("");
  };

  const save = async () => {
    if (!selected || saving || (outcome !== "given" && !reason.trim())) {
      return;
    }
    setSaving(true);
    try {
      await recordNursingTreatment(selected.patientUuid, selected, outcome, reason.trim());
      setSelected(null);
      await load();
    } catch (reasonValue) {
      setError(errorMessage(reasonValue));
    } finally {
      setSaving(false);
    }
  };

  const callReception = async (item: NursingTreatmentItem) => {
    if (callingVisitUuid) {
      return;
    }
    setCallingVisitUuid(item.visitUuid);
    setError("");
    try {
      await callReceptionForNursingTreatment(item.patientUuid, item.visitUuid);
    } catch (reasonValue) {
      setError(errorMessage(reasonValue));
    } finally {
      setCallingVisitUuid("");
    }
  };

  return (
    <>
      {error ? <Alert tone="danger" title="Treatment queue unavailable">{error}</Alert> : null}
      {loading ? (
        <p className="nursing-patient__muted">Loading treatments…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="No hospital treatments are due."
          description="Take-home medicines stay with Pharmacy. Inpatient medicines appear on the patient’s medication sheet."
        />
      ) : (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Patient</th>
                <th>Medicine</th>
                <th>Instructions</th>
                <th>Route</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={`${item.visitUuid}-${item.orderUuid}`}>
                  <td>
                    <button
                      type="button"
                      className="consult__link"
                      onClick={() => openNursingTreatmentVisit(item.patientUuid, item.visitUuid)}
                    >
                      {item.patientName}
                    </button>
                  </td>
                  <td>{item.medication}</td>
                  <td>{item.instructions || "Follow the prescription."}</td>
                  <td>{item.route || "—"}</td>
                  <td>
                    {item.status === "COMPLETED"
                      ? "Completed"
                      : item.status === "WAITING"
                        ? "Waiting for prescription"
                        : "Due"}
                  </td>
                  <td>
                    <div className="nursing-treatment__actions">
                      {item.status === "DUE" ? (
                        <Button variant="primary" onClick={() => open(item)}>
                          Record treatment
                        </Button>
                      ) : null}
                      <Button
                        variant="secondary"
                        onClick={() => void callReception(item)}
                        disabled={callingVisitUuid === item.visitUuid}
                      >
                        {callingVisitUuid === item.visitUuid ? "Calling…" : "Call Reception"}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected ? (
        <InpatientConfirmDialog
          title={`Record ${selected.medication}`}
          confirmLabel="Save treatment"
          busy={saving}
          confirmDisabled={saving || (outcome !== "given" && !reason.trim())}
          onClose={() => {
            if (!saving) setSelected(null);
          }}
          onConfirm={() => void save()}
        >
          <p>
            {selected.patientName} · {selected.route || "Route not recorded"}
          </p>
          <p><strong>Instructions:</strong> {selected.instructions || "Follow the prescription."}</p>
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
              <textarea
                rows={4}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Why was the treatment not given?"
              />
            </label>
          ) : null}
        </InpatientConfirmDialog>
      ) : null}
    </>
  );
}
