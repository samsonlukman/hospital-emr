import { useEffect, useRef, useState } from "react";
import { searchDiagnosisConcepts, type DiagnosisSearchHit } from "../services/openmrs/clinicalEncounter";
import type { DiagnosisDraftItem, DiagnosisRecord } from "../types";
import { Badge } from "./Badge";
import "./DiagnosisPanel.css";

interface DiagnosisPanelProps {
  recorded: DiagnosisRecord[];
  recordedUnavailable?: boolean;
  draft: DiagnosisDraftItem[];
  canEdit: boolean;
  onChange: (draft: DiagnosisDraftItem[]) => void;
}

function addDiagnosis(
  draft: DiagnosisDraftItem[],
  hit: DiagnosisSearchHit,
): DiagnosisDraftItem[] {
  if (draft.some((item) => item.conceptUuid === hit.conceptUuid)) {
    return draft;
  }
  const hasPrimary = draft.some((item) => item.order === "PRIMARY");
  return [
    ...draft,
    {
      conceptUuid: hit.conceptUuid,
      conceptName: hit.conceptName,
      matchedName: hit.matchedName,
      order: hasPrimary ? "SECONDARY" : "PRIMARY",
    },
  ];
}

export function DiagnosisPanel({
  recorded,
  recordedUnavailable,
  draft,
  canEdit,
  onChange,
}: DiagnosisPanelProps) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DiagnosisSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setHits([]);
      setSearching(false);
      setSearchError("");
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchDiagnosisConcepts(term)
        .then((results) => {
          if (!cancelled) {
            setHits(results);
            setSearchError("");
            setOpen(true);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setHits([]);
            setSearchError("Diagnosis search is unavailable.");
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSearching(false);
          }
        });
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, []);

  const selectHit = (hit: DiagnosisSearchHit) => {
    onChange(addDiagnosis(draft, hit));
    setQuery("");
    setHits([]);
    setOpen(false);
  };

  const setPrimary = (conceptUuid: string) => {
    onChange(
      draft.map((item) => ({
        ...item,
        order: item.conceptUuid === conceptUuid ? "PRIMARY" : "SECONDARY",
      })),
    );
  };

  const removeDraft = (conceptUuid: string) => {
    const next = draft.filter((item) => item.conceptUuid !== conceptUuid);
    if (next.length > 0 && !next.some((item) => item.order === "PRIMARY")) {
      next[0] = { ...next[0], order: "PRIMARY" };
    }
    onChange(next);
  };

  return (
    <div className="abikan-dx">
      {recordedUnavailable ? (
        <p className="consult__muted">Recorded diagnoses unavailable</p>
      ) : recorded.length > 0 ? (
        <ul className="abikan-dx__recorded">
          {recorded.map((row) => (
            <li key={row.uuid}>
              {row.order ? (
                <Badge tone={row.order === "PRIMARY" ? "info" : "neutral"}>
                  {row.order === "PRIMARY" ? "Primary" : "Secondary"}
                </Badge>
              ) : null}
              <span>{row.display}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="consult__muted">No diagnoses recorded for this patient.</p>
      )}

      {canEdit ? (
        <div className="abikan-dx__composer" ref={boxRef}>
          <label className="abikan-dx__search-label" htmlFor="diagnosis-search">
            Diagnoses
          </label>
          <input
            id="diagnosis-search"
            type="search"
            autoComplete="off"
            placeholder="Diagnoses"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => hits.length > 0 && setOpen(true)}
          />
          {searching ? <p className="abikan-dx__status">Searching…</p> : null}
          {searchError ? <p className="abikan-dx__status is-error">{searchError}</p> : null}
          {open && query.trim().length >= 2 && !searching ? (
            <ul className="abikan-dx__hits" role="listbox">
              {hits.length === 0 ? (
                <li className="abikan-dx__empty">No matching diagnoses</li>
              ) : (
                hits.map((hit) => (
                  <li key={hit.conceptUuid}>
                    <button type="button" onClick={() => selectHit(hit)}>
                      <strong>{hit.conceptName}</strong>
                      {hit.matchedName && hit.matchedName !== hit.conceptName ? (
                        <span>Matched: {hit.matchedName}</span>
                      ) : null}
                    </button>
                  </li>
                ))
              )}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="consult__hint">Start an open OPD visit to add a diagnosis.</p>
      )}

      {draft.length > 0 ? (
        <div className="abikan-dx__draft">
          <h4>Diagnoses</h4>
          <ul>
            {draft.map((item) => (
              <li key={item.conceptUuid}>
                <div>
                  <Badge tone={item.order === "PRIMARY" ? "info" : "neutral"}>
                    {item.order === "PRIMARY" ? "Primary" : "Secondary"}
                  </Badge>
                  <strong>{item.conceptName}</strong>
                </div>
                <div className="abikan-dx__row-actions">
                  {item.order !== "PRIMARY" ? (
                    <button type="button" onClick={() => setPrimary(item.conceptUuid)}>
                      Primary
                    </button>
                  ) : null}
                  <button type="button" onClick={() => removeDraft(item.conceptUuid)}>
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
