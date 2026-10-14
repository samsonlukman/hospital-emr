import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { fetchDrugOrderConfig, searchMedicinesForPrescription } from "../../services/openmrs/drugOrders";
import type { DrugCatalogueHit, DrugOrderConfig } from "../../services/openmrs/drugOrderMap";
import type { PharmacyPrescriptionEdit } from "../../services/pharmacy";
import type { PharmacyPrescription } from "../../types/pharmacy";

const FALLBACK_FREQUENCIES = [
  "Once a day",
  "Twice a day",
  "Three times a day",
  "Four times a day",
  "At night",
  "Immediately",
];

interface PharmacyPrescriptionEditorProps {
  mode: "add" | "change";
  row?: PharmacyPrescription | null;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (body: PharmacyPrescriptionEdit) => void;
}

function splitDuration(value: string): { duration: string; units: string } {
  const match = (value || "").trim().match(/^(\d+(?:\.\d+)?)\s+(.+)$/);
  if (!match) {
    return { duration: "5", units: "Days" };
  }
  return { duration: match[1].replace(/\.0$/, ""), units: hospitalDurationUnit(match[2]) };
}

function hospitalDurationUnit(value: string): string {
  const text = value.trim().toLowerCase();
  if (text === "day" || text === "days" || text === "day(s)") {
    return "Days";
  }
  if (text === "week" || text === "weeks" || text === "week(s)") {
    return "Weeks";
  }
  if (text === "month" || text === "months" || text === "month(s)") {
    return "Months";
  }
  return value.trim() || "Days";
}

function namesOf(options: Array<{ name?: string }> | undefined, fallback: string[]): string[] {
  const names = (options || []).map((item) => (item.name || "").trim()).filter(Boolean);
  return names.length ? names : fallback;
}

function withCurrent(options: string[], current: string): string[] {
  if (current && !options.includes(current)) {
    return [current, ...options];
  }
  return options;
}

export function PharmacyPrescriptionEditor({
  mode,
  row,
  busy,
  error,
  onClose,
  onSave,
}: PharmacyPrescriptionEditorProps) {
  const parsed = splitDuration(row?.duration || "");
  const [query, setQuery] = useState(mode === "change" ? row?.drugName || "" : "");
  const [hits, setHits] = useState<DrugCatalogueHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<DrugCatalogueHit | null>(
    mode === "change" && row?.drugUuid
      ? {
          uuid: row.drugUuid,
          name: row.drugName,
          strength: row.strength || "",
          form: row.doseUnits || "",
          genericName: "",
        }
      : null,
  );
  const [dose, setDose] = useState(row?.dose || "1");
  const [doseUnits, setDoseUnits] = useState(row?.doseUnits || "Tablet");
  const [route, setRoute] = useState(row?.route || "Oral");
  const [frequency, setFrequency] = useState(row?.frequency || "Twice a day");
  const [duration, setDuration] = useState(parsed.duration);
  const [durationUnits, setDurationUnits] = useState(parsed.units || "Days");
  const [quantity, setQuantity] = useState(mode === "change" && row?.quantity ? String(row.quantity) : "");
  const [quantityUnits, setQuantityUnits] = useState(row?.quantityUnits || row?.doseUnits || "Tablet");
  const [instructions, setInstructions] = useState(row?.instructions || "");
  const [config, setConfig] = useState<DrugOrderConfig | null>(null);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchDrugOrderConfig()
      .then((value) => {
        if (!cancelled) {
          setConfig(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setConfig(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2 || (selected && selected.name === term)) {
      setHits([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchMedicinesForPrescription(term)
        .then((results) => {
          if (!cancelled) {
            setHits(results);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setHits([]);
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

  const doseUnitOptions = withCurrent(namesOf(config?.doseUnits, ["Tablet", "Capsule", "ml", "mg"]), doseUnits);
  const routeOptions = withCurrent(namesOf(config?.routes, ["Oral"]), route);
  const frequencyOptions = withCurrent(namesOf(config?.frequencies, FALLBACK_FREQUENCIES), frequency);
  const durationUnitOptions = withCurrent(namesOf(config?.durationUnits, ["Days", "Weeks", "Months"]), durationUnits);
  const quantityUnitOptions = withCurrent(
    namesOf(config?.dispensingUnits, doseUnitOptions),
    quantityUnits,
  );

  const choose = (hit: DrugCatalogueHit) => {
    setSelected(hit);
    setQuery(hit.name);
    setHits([]);
    const form = hit.form && hit.form !== "—" ? hit.form : "";
    const unitNames = namesOf(config?.doseUnits, ["Tablet", "Capsule", "ml", "mg", "Unit"]);
    const matched = unitNames.find((name) => name.toLowerCase() === form.toLowerCase());
    const unit = matched || form || unitNames.find((name) => name.toLowerCase() === "unit") || "Unit";
    setDoseUnits(unit);
    setQuantityUnits(unit);
    setFormError("");
  };

  const submit = () => {
    if (!selected?.uuid) {
      setFormError("Choose a medicine from the hospital list.");
      return;
    }
    const qty = Number(quantity);
    if (!Number.isFinite(qty) || qty <= 0) {
      setFormError("Enter the quantity.");
      return;
    }
    const days = Number(duration);
    setFormError("");
    onSave({
      drugUuid: selected.uuid,
      drugName: selected.name,
      conceptUuid: selected.conceptUuid,
      dose: Number(dose) > 0 ? Number(dose) : 1,
      doseUnits,
      route,
      frequency,
      duration: Number.isFinite(days) && days > 0 ? days : 5,
      durationUnits,
      quantity: qty,
      quantityUnits,
      instructions: instructions.trim(),
    });
  };

  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="rx-edit-title">
      <div className="abikan-dialog__panel abikan-dialog__panel--rx">
        <h2 id="rx-edit-title">{mode === "add" ? "Add a medicine" : "Change medicine"}</h2>
        <p>
          {mode === "add"
            ? "This is added to the doctor’s prescription and to the pharmacy bill."
            : "The previous medicine is replaced. A handed-over or paid medicine cannot be changed."}
        </p>
        <div className="pharm-catalogue-form pharm-rx-editor">
          <label>
            Medicine
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setSelected(null);
              }}
              placeholder="Search the hospital list"
              autoFocus
            />
          </label>
          {searching ? <p className="pharm-patient__muted">Searching…</p> : null}
          {hits.length ? (
            <ul className="pharm-rx-editor__hits">
              {hits.map((hit) => (
                <li key={hit.uuid}>
                  <button type="button" onClick={() => choose(hit)}>
                    <strong>{hit.name}</strong>
                    <span>
                      {[hit.strength, hit.form, hit.price, hit.stockLabel].filter((part) => part && part !== "—").join(" · ")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <label>
            Dose
            <span className="pharm-rx-editor__pair">
              <input inputMode="decimal" value={dose} onChange={(event) => setDose(event.target.value)} />
              <select value={doseUnits} onChange={(event) => setDoseUnits(event.target.value)}>
                {doseUnitOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label>
            Route
            <select value={route} onChange={(event) => setRoute(event.target.value)}>
              {routeOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            How often
            <select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
              {frequencyOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            For
            <span className="pharm-rx-editor__pair">
              <input inputMode="decimal" value={duration} onChange={(event) => setDuration(event.target.value)} />
              <select value={durationUnits} onChange={(event) => setDurationUnits(event.target.value)}>
                {durationUnitOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label>
            Quantity
            <span className="pharm-rx-editor__pair">
              <input
                inputMode="decimal"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                placeholder="Required"
              />
              <select value={quantityUnits} onChange={(event) => setQuantityUnits(event.target.value)}>
                {quantityUnitOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label>
            Instructions
            <textarea
              rows={2}
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder="Optional"
            />
          </label>
        </div>
        {formError || error ? <p className="pharm-dialog__error">{formError || error}</p> : null}
        <div className="cashier-confirm__actions">
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button busy={busy} busyLabel="Saving…" onClick={submit}>
            {mode === "add" ? "Add medicine" : "Save change"}
          </Button>
        </div>
      </div>
    </div>
  );
}
