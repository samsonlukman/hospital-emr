import { useEffect, useMemo, useRef, useState } from "react";
import { CHIEF_COMPLAINT_DURATION_UNITS, OTHER_GENERIC_COMPLAINT_UUID } from "../config/clinicalConcepts";
import { optionalSectionsVisibleInWorkspace } from "../config/optionalClinicalSections";
import {
  chiefComplaintIsEmpty,
  emptyChiefComplaint,
  fetchChiefComplaintAnswers,
  formatChiefComplaintSummary,
  NO_CHIEF_COMPLAINT_FOR_VISIT,
  NO_CLINICAL_NOTES_FOR_VISIT,
  NO_HISTORY_FOR_VISIT,
  type ChiefComplaintDraft,
  type CodedAnswer,
  type DocumentationDraft,
} from "../services/openmrs/clinicalDocumentation";
import { OptionalClinicalSection } from "./OptionalClinicalSection";
import "./DocumentationPanel.css";

interface DocumentationPanelProps {
  draft: DocumentationDraft;
  recorded: DocumentationDraft;
  canEdit: boolean;
  blockedReason?: string;
  onChange: (draft: DocumentationDraft) => void;
}

export function DocumentationPanel({
  draft,
  recorded,
  canEdit,
  blockedReason,
  onChange,
}: DocumentationPanelProps) {
  const [answers, setAnswers] = useState<CodedAnswer[]>([]);
  const [answersError, setAnswersError] = useState("");
  const [queries, setQueries] = useState<Record<string, string>>({});
  const [openKey, setOpenKey] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const complaints = draft.complaints.length > 0 ? draft.complaints : [emptyChiefComplaint()];

  useEffect(() => {
    let cancelled = false;
    fetchChiefComplaintAnswers()
      .then((rows) => {
        if (!cancelled) {
          setAnswers(rows);
          setAnswersError("");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAnswers([]);
          setAnswersError("The chief complaint list could not be loaded. Type the complaint.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) {
        setOpenKey(null);
      }
    };
    window.addEventListener("mousedown", onPointer);
    return () => window.removeEventListener("mousedown", onPointer);
  }, []);

  useEffect(() => {
    if (answers.length === 0) {
      return;
    }
    let changed = false;
    const next = draft.complaints.map((row) => {
      if (!row.codedComplaintUuid || row.codedComplaintName) {
        return row;
      }
      const match = answers.find((answer) => answer.uuid === row.codedComplaintUuid);
      if (!match) {
        return row;
      }
      changed = true;
      return { ...row, codedComplaintName: match.name };
    });
    if (changed) {
      onChange({ ...draft, complaints: next });
    }
  }, [answers, draft, onChange]);

  const setField = (patch: Partial<DocumentationDraft>) => {
    onChange({ ...draft, ...patch });
  };

  const writeComplaints = (next: ChiefComplaintDraft[]) => {
    setField({ complaints: next });
  };

  const updateComplaint = (index: number, patch: Partial<ChiefComplaintDraft>) => {
    writeComplaints(complaints.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  };

  const chooseAnswer = (index: number, row: ChiefComplaintDraft, answer: CodedAnswer) => {
    updateComplaint(index, {
      codedComplaintUuid: answer.uuid,
      codedComplaintName: answer.name,
      complaintText: answer.uuid === OTHER_GENERIC_COMPLAINT_UUID ? row.complaintText : "",
    });
    setQueries((current) => {
      const next = { ...current };
      delete next[row.key];
      return next;
    });
    setOpenKey(null);
  };

  const useTypedComplaint = (index: number, row: ChiefComplaintDraft, text: string) => {
    updateComplaint(index, {
      codedComplaintUuid: "",
      codedComplaintName: "",
      complaintText: text.trim(),
    });
    setQueries((current) => {
      const next = { ...current };
      delete next[row.key];
      return next;
    });
    setOpenKey(null);
  };

  const recordedComplaint = formatChiefComplaintSummary(recorded);
  const visibleOptionalSections = optionalSectionsVisibleInWorkspace();

  return (
    <div className="abikan-docs">
      {!canEdit ? (
        <p className="abikan-docs__blocked">{blockedReason}</p>
      ) : null}

      <div className="abikan-docs__block">
        <h4>Chief Complaint</h4>
        {recordedComplaint ? (
          <p className="abikan-docs__recorded">On this visit: {recordedComplaint}</p>
        ) : (
          <p className="abikan-docs__muted">{NO_CHIEF_COMPLAINT_FOR_VISIT}</p>
        )}
        <div ref={boxRef}>
          {complaints.map((row, index) => (
            <ChiefComplaintRow
              key={row.key}
              row={row}
              answers={answers}
              answersError={answersError}
              canEdit={canEdit}
              query={queries[row.key]}
              open={openKey === row.key}
              canRemove={complaints.length > 1 || !chiefComplaintIsEmpty(row)}
              onQuery={(value) => {
                setQueries((current) => ({ ...current, [row.key]: value }));
                setOpenKey(row.key);
              }}
              onOpen={() => setOpenKey(row.key)}
              onChoose={(answer) => chooseAnswer(index, row, answer)}
              onUseTyped={(text) => useTypedComplaint(index, row, text)}
              onDuration={(durationValue) => updateComplaint(index, { durationValue })}
              onUnit={(durationUnitUuid) => updateComplaint(index, { durationUnitUuid })}
              onRemove={() => {
                const next = complaints.filter((_, rowIndex) => rowIndex !== index);
                writeComplaints(next);
                setOpenKey(null);
              }}
              onBlurQuery={() => {
                window.setTimeout(() => {
                  setQueries((current) => {
                    if (!(row.key in current)) {
                      return current;
                    }
                    const next = { ...current };
                    delete next[row.key];
                    return next;
                  });
                  setOpenKey((current) => (current === row.key ? null : current));
                }, 200);
              }}
            />
          ))}
        </div>
        {canEdit ? (
          <button
            type="button"
            className="abikan-docs__add"
            onClick={() => writeComplaints([...complaints, emptyChiefComplaint(`complaint-${Date.now()}`)])}
          >
            Add chief complaint
          </button>
        ) : null}
      </div>

      <div className="abikan-docs__block">
        <h4>History of Present Illness</h4>
        {recorded.hpi ? (
          <p className="abikan-docs__recorded">On this visit: {recorded.hpi}</p>
        ) : (
          <p className="abikan-docs__muted">{NO_HISTORY_FOR_VISIT}</p>
        )}
        <label>
          <span>History of Present Illness</span>
          <textarea
            disabled={!canEdit}
            rows={4}
            value={draft.hpi}
            onChange={(event) => setField({ hpi: event.target.value })}
          />
        </label>
      </div>

      {visibleOptionalSections.length > 0 ? (
        <div className="abikan-docs__optional-list">
          {visibleOptionalSections.map((section) => (
            <OptionalClinicalSection key={section.id} section={section} />
          ))}
        </div>
      ) : null}

      <div className="abikan-docs__block">
        <h4>Consultation Note</h4>
        {recorded.consultationNote ? (
          <p className="abikan-docs__recorded">On this visit: {recorded.consultationNote}</p>
        ) : (
          <p className="abikan-docs__muted">{NO_CLINICAL_NOTES_FOR_VISIT}</p>
        )}
        <label>
          <span>Consultation Note</span>
          <textarea
            disabled={!canEdit}
            rows={4}
            value={draft.consultationNote}
            onChange={(event) => setField({ consultationNote: event.target.value })}
          />
        </label>
      </div>
    </div>
  );
}

function complaintLabel(row: ChiefComplaintDraft): string {
  if (row.complaintText && (!row.codedComplaintUuid || row.codedComplaintUuid === OTHER_GENERIC_COMPLAINT_UUID)) {
    return row.complaintText;
  }
  return row.codedComplaintName || row.complaintText;
}

function ChiefComplaintRow({
  row,
  answers,
  answersError,
  canEdit,
  query,
  open,
  canRemove,
  onQuery,
  onOpen,
  onChoose,
  onUseTyped,
  onDuration,
  onUnit,
  onRemove,
  onBlurQuery,
}: {
  row: ChiefComplaintDraft;
  answers: CodedAnswer[];
  answersError: string;
  canEdit: boolean;
  query: string | undefined;
  open: boolean;
  canRemove: boolean;
  onQuery: (value: string) => void;
  onOpen: () => void;
  onChoose: (answer: CodedAnswer) => void;
  onUseTyped: (text: string) => void;
  onDuration: (value: string) => void;
  onUnit: (value: string) => void;
  onRemove: () => void;
  onBlurQuery: () => void;
}) {
  const typed = (query ?? "").trim();
  const showingSearch = query !== undefined;
  const filtered = useMemo(() => {
    const term = typed.toLowerCase();
    const rows = term ? answers.filter((answer) => answer.name.toLowerCase().includes(term)) : answers;
    return rows.slice(0, 12);
  }, [answers, typed]);
  const exact = typed
    ? answers.some((answer) => answer.name.toLowerCase() === typed.toLowerCase())
    : false;

  return (
    <div className="abikan-docs__complaint-row">
      <div className="abikan-docs__complaint">
        <label>
          <span>Chief Complaint</span>
          <input
            disabled={!canEdit}
            value={showingSearch ? query : complaintLabel(row)}
            placeholder="Search chief complaint"
            aria-label="Chief Complaint"
            onChange={(event) => onQuery(event.target.value)}
            onFocus={() => {
              onOpen();
              if (!showingSearch) {
                onQuery("");
              }
            }}
            onBlur={onBlurQuery}
          />
        </label>
        {open && canEdit ? (
          <ul className="abikan-docs__hits">
            {filtered.map((answer) => (
              <li key={answer.uuid}>
                <button type="button" onClick={() => onChoose(answer)}>
                  {answer.name}
                </button>
              </li>
            ))}
            {typed && !exact ? (
              <li>
                <button type="button" onClick={() => onUseTyped(typed)}>
                  {typed}
                </button>
              </li>
            ) : null}
            {filtered.length === 0 && !typed ? (
              <li className="abikan-docs__empty">{answersError || "No chief complaint found."}</li>
            ) : null}
          </ul>
        ) : null}
      </div>
      <label>
        <span>Duration</span>
        <input
          disabled={!canEdit}
          inputMode="numeric"
          value={row.durationValue}
          aria-label={`Duration for ${complaintLabel(row) || "chief complaint"}`}
          onChange={(event) => onDuration(event.target.value)}
        />
      </label>
      <label>
        <span>Unit</span>
        <select
          disabled={!canEdit}
          value={row.durationUnitUuid}
          aria-label={`Duration unit for ${complaintLabel(row) || "chief complaint"}`}
          onChange={(event) => onUnit(event.target.value)}
        >
          <option value="">Unit</option>
          {CHIEF_COMPLAINT_DURATION_UNITS.map((unit) => (
            <option key={unit.uuid} value={unit.uuid}>
              {unit.name}
            </option>
          ))}
        </select>
      </label>
      {canRemove && canEdit ? (
        <button type="button" className="abikan-docs__remove" onClick={onRemove} aria-label="Remove chief complaint">
          Remove
        </button>
      ) : (
        <span />
      )}
    </div>
  );
}
