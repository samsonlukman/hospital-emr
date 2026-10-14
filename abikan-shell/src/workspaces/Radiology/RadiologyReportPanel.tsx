import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { OpenmrsRequestError } from "../../services/openmrs/client";
import { fetchRadiologyNotesForVisit, saveRadiologyReport } from "../../services/openmrs/radiology";
import type { RadiologyNoteSummary, RadiologyOrderSummary } from "../../types";
import {
  NO_RADIOLOGY_REPORT,
  RADIOLOGY_REPORT_PLACEHOLDER,
  canWriteRadiologyReport,
  radiologyNoteForOrder,
  radiologyReportActionLabel,
  radiologyReportStatusLabel,
  staffMessageForRadiologyReportError,
} from "./radiologyReport";
import { radiologyStaffName } from "./radiologyDesk";
import "./RadiologyReportPanel.css";

interface RadiologyReportPanelProps {
  order: RadiologyOrderSummary;
  visitStartDatetime?: string;
  locationUuid: string;
  userUuid: string;
}

export function RadiologyReportPanel({
  order,
  visitStartDatetime = "",
  locationUuid,
  userUuid,
}: RadiologyReportPanelProps) {
  const [notes, setNotes] = useState<RadiologyNoteSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visitUuid = order.visitUuid || "";
  const encounterUuid = order.encounterUuid || "";
  const note = radiologyNoteForOrder(notes, {
    patientUuid: order.patientUuid,
    visitUuid,
    orderUuid: order.uuid,
  });
  const writeGate = canWriteRadiologyReport({
    patientUuid: order.patientUuid,
    visitUuid,
    encounterUuid,
    orderUuid: order.uuid,
    orderPatientUuid: order.patientUuid,
    orderVisitUuid: order.visitUuid,
    orderEncounterUuid: order.encounterUuid,
  });

  useEffect(() => {
    setEditing(false);
    setDraft("");
    setError(null);
    setNotes([]);
    if (!order.patientUuid || !visitUuid) {
      setLoading(false);
      setUnavailable(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setUnavailable(false);
    fetchRadiologyNotesForVisit(order.patientUuid, visitUuid)
      .then((visitNotes) => {
        if (!cancelled) {
          setNotes(visitNotes);
        }
      })
      .catch((reason) => {
        console.error("Unable to load radiology report", reason);
        if (!cancelled) {
          setNotes([]);
          setUnavailable(true);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [order.uuid, order.patientUuid, visitUuid]);

  const openEditor = () => {
    setError(null);
    setDraft(note?.value || "");
    setEditing(true);
  };

  const save = async () => {
    if (saving) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveRadiologyReport({
        patientUuid: order.patientUuid,
        visitUuid,
        visitType: order.visitType,
        visitStartDatetime,
        encounterUuid,
        encounterDatetime: order.encounterDatetime,
        orderUuid: order.uuid,
        locationUuid,
        userUuid,
        text: draft,
      });
      setNotes((current) => {
        const others = current.filter(
          (row) => row.uuid !== saved.uuid && row.orderUuid !== order.uuid,
        );
        return [...others, saved];
      });
      setEditing(false);
    } catch (reason) {
      setError(staffMessageForRadiologyReportError(reason));
      if (reason instanceof OpenmrsRequestError && reason.status === 401) {
        setUnavailable(true);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rad-report" aria-labelledby="rad-report-heading">
      <h3 id="rad-report-heading">Radiology Report</h3>
      <p className="rad-report__muted">
        This report is for this examination only. It is not the doctor's clinical notes.
      </p>

      {loading ? (
        <p className="rad-report__muted">Loading report…</p>
      ) : unavailable ? (
        <p className="rad-report__muted">The report could not be loaded. Try again in a moment.</p>
      ) : !writeGate.ok ? (
        <p className="rad-report__muted">{writeGate.message}</p>
      ) : editing ? (
        <form
          className="rad-report__form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <label>
            <span>Report</span>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={RADIOLOGY_REPORT_PLACEHOLDER}
              rows={12}
              disabled={saving}
            />
          </label>
          {error ? <Alert tone="danger" title={error} /> : null}
          <div className="rad-report__actions">
            <Button type="button" variant="ghost" disabled={saving} onClick={() => {
              setDraft("");
              setEditing(false);
            }}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save Report"}
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="rad-report__status">{radiologyReportStatusLabel(note)}</p>
          {note ? (
            <>
              <p className="rad-report__text">{note.value}</p>
              {radiologyStaffName(note.reportedBy) !== "—" ? (
                <p className="rad-report__meta">Reported by: {radiologyStaffName(note.reportedBy)}</p>
              ) : null}
              {note.observedAt && note.observedAt !== "—" ? (
                <p className="rad-report__meta">Reported: {note.observedAt}</p>
              ) : null}
            </>
          ) : (
            <p className="rad-report__empty">{NO_RADIOLOGY_REPORT}</p>
          )}
          {error ? <Alert tone="danger" title={error} /> : null}
          <div className="rad-report__actions">
            <Button onClick={openEditor}>{radiologyReportActionLabel(note)}</Button>
          </div>
        </>
      )}
    </section>
  );
}
