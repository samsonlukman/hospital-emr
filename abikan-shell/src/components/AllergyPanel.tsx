import { useState } from "react";
import type { AllergyRecord, AllergyState } from "../types";
import {
  createAllergy,
  removeAllergy,
  updateAllergy,
} from "../services/allergies";
import { searchDrugCatalogue } from "../services/openmrs/drugOrders";
import type { DrugCatalogueHit } from "../services/openmrs/drugOrderMap";
import { PatientAccountRequestError } from "../services/patientAccount";
import {
  ALLERGEN_TYPES,
  ALLERGY_SEVERITIES,
  draftFromRecord,
  emptyAllergyDraft,
  validateAllergyDraft,
  type AllergyDraft,
} from "../utils/allergies";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { InpatientConfirmDialog } from "../workspaces/Nursing/InpatientDialogs";
import "./AllergyPanel.css";

interface Props {
  patientUuid: string;
  allergy: AllergyState;
  onChanged: (next: AllergyState) => void;
  readOnly?: boolean;
}

function requestMessage(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "The allergy could not be saved on the patient chart. Try again.";
}

export function AllergyPanel({ patientUuid, allergy, onChanged, readOnly = false }: Props) {
  const canWrite = !readOnly && Boolean(allergy.status === "recorded" ? allergy.canWrite : allergy.canWrite);
  const records = allergy.status === "recorded" ? allergy.records : [];
  const [draft, setDraft] = useState<AllergyDraft | null>(null);
  const [editingUuid, setEditingUuid] = useState("");
  const [pendingRemove, setPendingRemove] = useState<AllergyRecord | null>(null);
  const [hits, setHits] = useState<DrugCatalogueHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const openCreate = () => {
    setEditingUuid("");
    setDraft(emptyAllergyDraft());
    setHits([]);
    setError("");
  };

  const openEdit = (row: AllergyRecord) => {
    if (!row.uuid || row.uuid.startsWith("read-")) {
      return;
    }
    setEditingUuid(row.uuid);
    setDraft(draftFromRecord(row));
    setHits([]);
    setError("");
  };

  const searchMedicines = async (term: string) => {
    setDraft((current) => (current ? { ...current, allergenName: term, codedAllergenUuid: "" } : current));
    if (term.trim().length < 2) {
      setHits([]);
      return;
    }
    setSearching(true);
    try {
      setHits(await searchDrugCatalogue(term));
    } catch {
      setHits([]);
    } finally {
      setSearching(false);
    }
  };

  const save = async () => {
    if (!draft || saving) {
      return;
    }
    const invalid = validateAllergyDraft(draft);
    if (invalid) {
      setError(invalid);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const next = editingUuid
        ? await updateAllergy(patientUuid, editingUuid, draft)
        : await createAllergy(patientUuid, draft);
      onChanged(next);
      setDraft(null);
      setEditingUuid("");
    } catch (saveError) {
      setError(requestMessage(saveError));
    } finally {
      setSaving(false);
    }
  };

  const confirmRemove = async () => {
    if (!pendingRemove || saving) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      onChanged(await removeAllergy(patientUuid, pendingRemove.uuid));
      setPendingRemove(null);
    } catch (saveError) {
      setError(requestMessage(saveError));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="allergy-panel">
      <div className="allergy-panel__intro">
        <p>
          Allergies belong to the patient, not to one visit. They stay on the chart until a doctor
          or nurse updates them.
        </p>
        {canWrite ? (
          <Button variant="secondary" onClick={openCreate}>
            Record allergy
          </Button>
        ) : null}
      </div>
      {allergy.status === "unavailable" ? (
        <Alert tone="danger" title="Allergy record unavailable">
          <p>The allergy list could not be loaded. Try again from this chart.</p>
        </Alert>
      ) : records.length === 0 ? (
        <EmptyState
          title="No allergies recorded"
          description={
            canWrite
              ? "Record a known allergy here so doctors, nurses, and pharmacy can see it."
              : "No allergies have been recorded for this patient."
          }
        />
      ) : (
        <ul className="allergy-panel__list">
          {records.map((row) => (
            <li key={row.uuid}>
              <div>
                <strong>{row.allergen}</strong>
                <span>
                  {[
                    row.allergenTypeLabel,
                    row.severity,
                    row.reactions.join(", "),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {row.comment ? <em>{row.comment}</em> : null}
              </div>
              {canWrite && !row.uuid.startsWith("read-") ? (
                <div className="allergy-panel__row-actions">
                  <Button variant="ghost" onClick={() => openEdit(row)}>
                    Edit
                  </Button>
                  <Button variant="ghost" onClick={() => setPendingRemove(row)}>
                    Remove
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {draft ? (
        <InpatientConfirmDialog
          title={editingUuid ? "Update allergy" : "Record allergy"}
          confirmLabel={editingUuid ? "Save allergy" : "Save allergy"}
          busy={saving}
          error={error}
          onClose={() => {
            if (!saving) {
              setDraft(null);
              setError("");
            }
          }}
          onConfirm={() => {
            void save();
          }}
        >
          <div className="allergy-panel__form">
            <label>
              Type
              <select
                value={draft.allergenType}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    allergenType: event.target.value,
                    codedAllergenUuid: "",
                  })
                }
              >
                {ALLERGEN_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Substance
              <input
                value={draft.allergenName}
                onChange={(event) => {
                  if (draft.allergenType === "DRUG") {
                    void searchMedicines(event.target.value);
                  } else {
                    setDraft({ ...draft, allergenName: event.target.value });
                  }
                }}
                placeholder={
                  draft.allergenType === "DRUG"
                    ? "Search a medicine or type the name"
                    : "For example peanuts or latex"
                }
              />
            </label>
            {draft.allergenType === "DRUG" && hits.length > 0 ? (
              <ul className="allergy-panel__hits">
                {hits.map((hit) => (
                  <li key={hit.uuid}>
                    <button
                      type="button"
                      onClick={() => {
                        setDraft({
                          ...draft,
                          allergenName: hit.name,
                          codedAllergenUuid: hit.conceptUuid || "",
                        });
                        setHits([]);
                      }}
                    >
                      {hit.name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {searching ? <p className="allergy-panel__hint">Searching medicines…</p> : null}
            <label>
              Severity
              <select
                value={draft.severity}
                onChange={(event) => setDraft({ ...draft, severity: event.target.value })}
              >
                {ALLERGY_SEVERITIES.map((item) => (
                  <option key={item.value || "none"} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reaction
              <input
                value={draft.reaction}
                onChange={(event) => setDraft({ ...draft, reaction: event.target.value })}
                placeholder="Optional, for example rash or swelling"
              />
            </label>
            <label>
              Comment
              <textarea
                value={draft.comment}
                onChange={(event) => setDraft({ ...draft, comment: event.target.value })}
                rows={3}
              />
            </label>
          </div>
        </InpatientConfirmDialog>
      ) : null}

      {pendingRemove ? (
        <InpatientConfirmDialog
          title="Remove allergy"
          confirmLabel="Remove allergy"
          busy={saving}
          error={error}
          onClose={() => {
            if (!saving) {
              setPendingRemove(null);
              setError("");
            }
          }}
          onConfirm={() => {
            void confirmRemove();
          }}
        >
          <p>
            Remove <strong>{pendingRemove.allergen}</strong> from this patient’s allergy record?
            The change is saved on the shared clinical chart.
          </p>
        </InpatientConfirmDialog>
      ) : null}

      {error && !draft && !pendingRemove ? (
        <Alert tone="danger" title="Allergy update failed">
          {error}
        </Alert>
      ) : null}
    </div>
  );
}
