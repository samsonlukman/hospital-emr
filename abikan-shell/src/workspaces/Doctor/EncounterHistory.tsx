import { useEffect, useState } from "react";
import {
  encounterDetailIsEmpty,
  fetchEncounterDetail,
  type EncounterDetail,
} from "../../services/openmrs/clinicalDocumentation";
import type { EncounterSummary } from "../../types";

function DetailBlock({ label, value }: { label: string; value: string }) {
  if (!value) {
    return null;
  }
  return (
    <div>
      <h5>{label}</h5>
      <p>{value}</p>
    </div>
  );
}

function DetailList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <h5>{label}</h5>
      <ul>
        {items.map((item, index) => (
          <li key={`${label}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function EncounterHistory({
  patientUuid,
  encounters,
  unavailable,
  showAll,
}: {
  patientUuid: string;
  encounters: EncounterSummary[];
  unavailable: boolean;
  showAll: boolean;
}) {
  const [selectedUuid, setSelectedUuid] = useState("");
  const [detail, setDetail] = useState<EncounterDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const visible = showAll ? encounters : encounters.slice(0, 4);

  useEffect(() => {
    setSelectedUuid("");
    setDetail(null);
    setError("");
  }, [patientUuid]);

  useEffect(() => {
    if (!selectedUuid) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setError("");
    fetchEncounterDetail(selectedUuid, patientUuid)
      .then((payload) => {
        if (!cancelled) {
          setDetail(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("This encounter could not be opened. Try again.");
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
  }, [patientUuid, selectedUuid]);

  const openEncounter = (row: EncounterSummary) => {
    setError("");
    if (selectedUuid === row.uuid) {
      setSelectedUuid("");
      setDetail(null);
      return;
    }
    setSelectedUuid(row.uuid);
  };

  return (
    <div className="consult__history-side">
      <h4>Encounters</h4>
      {unavailable ? (
        <p className="consult__muted">Encounters unavailable</p>
      ) : encounters.length > 0 ? (
        <ul className="consult__encounters">
          {visible.map((row) => {
            const selected = row.uuid === selectedUuid;
            return (
              <li key={row.uuid}>
                <button
                  type="button"
                  className={selected ? "is-selected" : undefined}
                  aria-expanded={selected}
                  onClick={() => openEncounter(row)}
                >
                  {row.date}
                  {row.time ? ` · ${row.time}` : ""} · {row.type}
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="consult__muted">No previous encounters recorded</p>
      )}
      {selectedUuid ? (
        <div className="consult__encounter-detail">
          {loading ? <p className="consult__muted">Opening encounter…</p> : null}
          {error ? <p className="consult__muted">{error}</p> : null}
          {detail && !loading ? (
            <>
              {detail.clinician ? (
                <p className="consult__muted">Seen by {detail.clinician}</p>
              ) : null}
              {encounterDetailIsEmpty(detail) ? (
                <p className="consult__muted">No notes, diagnosis, or orders were recorded.</p>
              ) : (
                <>
                  <DetailBlock label="Chief Complaint" value={detail.complaint} />
                  <DetailBlock label="History of Present Illness" value={detail.history} />
                  <DetailBlock label="Consultation Note" value={detail.notes} />
                  <DetailList label="Vitals" items={detail.vitals} />
                  <DetailList label="Diagnoses" items={detail.diagnoses} />
                  <DetailList label="Orders" items={detail.orders} />
                </>
              )}
            </>
          ) : null}
        </div>
      ) : encounters.length > 0 ? (
        <p className="consult__hint">Open an encounter.</p>
      ) : null}
    </div>
  );
}
