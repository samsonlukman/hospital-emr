import { useEffect, useRef, useState } from "react";
import { Badge } from "./Badge";
import { Button } from "./Button";
import type { DrugOrderSummary } from "../types";
import {
  fetchDrugOrderConfig,
  searchMedicinesForPrescription,
  dosingUnitForForm,
  typedMedicineName,
  validatePrescription,
  type DrugCatalogueHit,
  type DrugOrderConfig,
  type MedicationAdministrationMode,
  type PrescriptionDraftItem,
} from "../services/openmrs/drugOrders";
import "./PrescriptionPanel.css";

interface PrescriptionPanelProps {
  recorded: DrugOrderSummary[];
  recordedUnavailable?: boolean;
  loading?: boolean;
  draft: PrescriptionDraftItem[];
  canEdit: boolean;
  blockedReason?: string;
  submitting?: boolean;
  onChange: (draft: PrescriptionDraftItem[]) => void;
  onPrescribe: () => void;
  allergyWarning?: string;
  defaultAdministrationMode?: MedicationAdministrationMode;
}

function pickName(options: Array<{ name: string }>, preferred: string): string {
  return options.some((item) => item.name === preferred) ? preferred : options[0]?.name || "";
}

function medicationStatusTone(status: string): "info" | "warning" | "neutral" {
  if (status === "Ordered") {
    return "info";
  }
  if (status === "Expired") {
    return "warning";
  }
  return "neutral";
}

function nextDraftId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function PrescriptionPanel({
  recorded,
  recordedUnavailable,
  loading,
  draft,
  canEdit,
  blockedReason,
  submitting,
  onChange,
  onPrescribe,
  allergyWarning,
  defaultAdministrationMode = "HOME",
}: PrescriptionPanelProps) {
  const [config, setConfig] = useState<DrugOrderConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DrugCatalogueHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<DrugCatalogueHit | null>(null);
  const [route, setRoute] = useState("");
  const [frequency, setFrequency] = useState("");
  const [duration, setDuration] = useState("5");
  const [durationUnits, setDurationUnits] = useState("");
  const [instructions, setInstructions] = useState("");
  const [administrationMode, setAdministrationMode] =
    useState<MedicationAdministrationMode>(defaultAdministrationMode);
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setAdministrationMode(defaultAdministrationMode);
  }, [defaultAdministrationMode]);

  useEffect(() => {
    let cancelled = false;
    fetchDrugOrderConfig()
      .then((value) => {
        if (cancelled) {
          return;
        }
        setConfig(value);
        setConfigError("");
        setRoute((current) => current || pickName(value.routes, "Oral"));
        setFrequency((current) => current || pickName(value.frequencies, "Twice a day"));
        setDurationUnits((current) => current || pickName(value.durationUnits, "Days"));
      })
      .catch(() => {
        if (!cancelled) {
          setConfigError("Medication options could not be loaded. Try again.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2 || selected) {
      setHits([]);
      setSearching(false);
      setSearchError("");
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchMedicinesForPrescription(term)
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
            setSearchError("Medicine search is unavailable.");
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
  }, [query, selected]);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, []);

  const resetComposer = () => {
    setSelected(null);
    setQuery("");
    setHits([]);
    setOpen(false);
    setDuration("5");
    setInstructions("");
    setAdministrationMode(defaultAdministrationMode);
    setFormErrors([]);
  };

  const chooseDrug = (hit: DrugCatalogueHit) => {
    setSelected(hit);
    setQuery(hit.name);
    setHits([]);
    setOpen(false);
    setSearchError("");
    setFormErrors([]);
  };

  const chooseTypedName = (name: string) => {
    const typed = typedMedicineName(name);
    if (typed.length < 3) {
      setFormErrors(["Type the full medicine name."]);
      return;
    }
    setSelected({
      uuid: "",
      name: typed,
      strength: "—",
      form: "—",
      genericName: "—",
    });
    setQuery(typed);
    setHits([]);
    setOpen(false);
    setSearchError("");
    setFormErrors([]);
  };

  const addToReview = () => {
    if (!config) {
      setFormErrors(["Medication options could not be loaded. Try again."]);
      return;
    }
    const errors = validatePrescription(
      {
        drugUuid: selected?.uuid || "",
        drugName: selected?.name || query,
        dose: 1,
        doseUnits: dosingUnitForForm(selected?.form || "", config.doseUnits),
        route,
        frequency,
        duration,
        durationUnits,
        quantity: 1,
        quantityUnits: dosingUnitForForm(selected?.form || "", config.dispensingUnits.length ? config.dispensingUnits : config.doseUnits),
        instructions,
        administrationMode,
      },
      config,
    );
    if (errors.length > 0) {
      setFormErrors(errors);
      return;
    }
    onChange([
      ...draft,
      {
        id: nextDraftId(),
        drugUuid: selected?.uuid || "",
        drugName: typedMedicineName(selected?.name || query) || "Medication",
        dose: 1,
        doseUnits: dosingUnitForForm(selected?.form || "", config.doseUnits),
        route,
        frequency,
        duration: Number(duration),
        durationUnits,
        quantity: 1,
        quantityUnits: dosingUnitForForm(
          selected?.form || "",
          config.dispensingUnits.length ? config.dispensingUnits : config.doseUnits,
        ),
        instructions: instructions.trim(),
        administrationMode,
        nonCoded: !selected?.uuid,
        conceptUuid: selected?.conceptUuid || "",
      },
    ]);
    resetComposer();
    window.setTimeout(() => searchRef.current?.focus(), 0);
  };

  const removeDraft = (id: string) => {
    onChange(draft.filter((item) => item.id !== id));
  };

  return (
    <div className="abikan-rx">
      {recordedUnavailable ? (
        <p className="consult__muted">Medications unavailable</p>
      ) : loading ? (
        <p className="consult__muted">Loading medications…</p>
      ) : recorded.length > 0 ? (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Drug Name</th>
                <th>Dose</th>
                <th>Frequency</th>
                <th>Duration</th>
                <th>Instructions</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recorded.map((row) => (
                <tr key={row.uuid}>
                  <td>{row.drugName || row.display}</td>
                  <td>{row.dose || "—"}</td>
                  <td>{row.frequency || "—"}</td>
                  <td>{row.duration || "—"}</td>
                  <td>{row.instructions || "—"}</td>
                  <td>
                    {row.status ? (
                      <Badge tone={medicationStatusTone(row.status)}>{row.status}</Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="consult__muted">No medications recorded</p>
      )}

      {canEdit ? (
        <div className="abikan-rx__composer">
          <h4>Treatments</h4>
          {allergyWarning ? (
            <p className="abikan-rx__status is-error" role="status">
              This patient has recorded allergies: {allergyWarning}. Check the medicine before prescribing.
            </p>
          ) : null}
          <div className="abikan-rx__search" ref={boxRef}>
            <label htmlFor="medication-search">Drug Name</label>
            <input
              ref={searchRef}
              id="medication-search"
              type="search"
              autoComplete="off"
              placeholder="Drug Name"
              value={query}
              onChange={(event) => {
                setSelected(null);
                setQuery(event.target.value);
              }}
              onFocus={() => {
                if (hits.length > 0) {
                  setOpen(true);
                }
              }}
            />
            {searching ? <p className="abikan-rx__status">Searching…</p> : null}
            {searchError ? <p className="abikan-rx__status is-error">{searchError}</p> : null}
            {open && !selected && query.trim().length >= 2 && !searching ? (
              <ul className="abikan-rx__hits">
                {hits.length === 0 ? (
                  <li className="abikan-rx__empty">No matching medicines in Pharmacy.</li>
                ) : (
                  hits.map((hit) => (
                    <li key={hit.uuid}>
                      <button type="button" onClick={() => chooseDrug(hit)}>
                        <strong>{hit.name}</strong>
                        {hit.price ? <em>{hit.price}</em> : null}
                        <span>
                          {[
                            hit.form !== "—" ? hit.form : "",
                            hit.genericName !== "—" ? hit.genericName : "",
                            hit.stockLabel || "",
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </button>
                    </li>
                  ))
                )}
                {typedMedicineName(query).length >= 3 ? (
                  <li>
                    <button type="button" className="abikan-rx__typed" onClick={() => chooseTypedName(query)}>
                      <strong>Use “{typedMedicineName(query)}”</strong>
                      <span>If this medicine is not in Pharmacy</span>
                    </button>
                  </li>
                ) : null}
              </ul>
            ) : null}
          </div>
          {selected?.uuid && selected.price ? (
            <p className="abikan-rx__price" role="status">
              Current price: {selected.price}
            </p>
          ) : null}
          {selected && !selected.uuid ? (
            <p className="abikan-rx__status" role="status">
              This name is not in the Pharmacy list. Pharmacy will see the name you typed.
            </p>
          ) : null}

          <div className="abikan-rx__grid">
            <label>
              Route
              <select value={route} onChange={(event) => setRoute(event.target.value)}>
                {(config?.routes ?? []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Frequency
              <select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
                {(config?.frequencies ?? []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Duration
              <span className="abikan-rx__split">
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={duration}
                  onChange={(event) => setDuration(event.target.value)}
                />
                <select
                  value={durationUnits}
                  onChange={(event) => setDurationUnits(event.target.value)}
                >
                  {(config?.durationUnits ?? []).map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </span>
            </label>
            <label>
              Given
              <select
                value={administrationMode}
                onChange={(event) =>
                  setAdministrationMode(event.target.value as MedicationAdministrationMode)
                }
              >
                <option value="HOME">At home</option>
                <option value="HOSPITAL_FOLLOW_UP">Hospital follow-up</option>
                <option value="INPATIENT">Inpatient ward</option>
              </select>
            </label>
          </div>

          {formErrors.length > 0 ? (
            <ul className="abikan-rx__errors">
              {formErrors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          ) : null}
          {configError ? <p className="abikan-rx__status is-error">{configError}</p> : null}

          <div className="abikan-rx__actions">
            <label className="abikan-rx__instructions">
              Instructions
              <input
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                placeholder="Instructions"
              />
            </label>
            <Button variant="secondary" onClick={addToReview} disabled={Boolean(submitting)}>
              Add
            </Button>
          </div>
        </div>
      ) : (
        <p className="consult__hint">{blockedReason}</p>
      )}

      {draft.length > 0 ? (
        <div className="abikan-rx__review">
          <h4>Treatments</h4>
          <ul>
            {draft.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.drugName}</strong>
                  <p>
                    {item.nonCoded || !item.drugUuid ? "Not in Pharmacy list · " : ""}
                    {item.route} · {item.frequency} · {item.duration} {item.durationUnits}
                    {" · "}
                    {item.administrationMode === "INPATIENT"
                      ? "Inpatient ward"
                      : item.administrationMode === "HOSPITAL_FOLLOW_UP"
                        ? "Hospital follow-up"
                        : "At home"}
                    {item.instructions ? ` · ${item.instructions}` : ""}
                  </p>
                </div>
                <button type="button" onClick={() => removeDraft(item.id)} disabled={Boolean(submitting)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
          <Button
            variant="primary"
            disabled={!canEdit}
            busy={Boolean(submitting)}
            busyLabel="Saving prescription…"
            onClick={onPrescribe}
          >
            Prescribe
          </Button>
        </div>
      ) : null}
    </div>
  );
}
