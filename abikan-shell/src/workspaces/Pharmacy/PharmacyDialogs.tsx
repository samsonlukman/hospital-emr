import { useEffect, useRef, useState } from "react";
import type {
  PharmacyCatalogueDraft,
  PharmacyGenericOption,
  PharmacyInventoryHistoryRow,
  PharmacyInventoryItem,
  PharmacyPrescription,
} from "../../types/pharmacy";
import { Button } from "../../components/Button";
import { createPharmacyGeneric, quantityLabel, searchPharmacyGenerics } from "../../services/pharmacy";
import { formatStockQty, pharmacyStaffError, dosageFormChoices, isUnlistedDosageForm } from "./pharmacyView";

interface DispenseConfirmDialogProps {
  order: PharmacyPrescription;
  busy?: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DispenseConfirmDialog({
  order,
  busy,
  error,
  onCancel,
  onConfirm,
}: DispenseConfirmDialogProps) {
  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="dispense-title">
      <div className="abikan-dialog__panel cashier-confirm">
        <h2 id="dispense-title">Dispense medication?</h2>
        <p>This will mark the prescription as dispensed and update pharmacy stock.</p>
        <dl>
          <div>
            <dt>Patient</dt>
            <dd>{order.patientName}</dd>
          </div>
          <div>
            <dt>Hospital number</dt>
            <dd>{order.mrn || "Not recorded"}</dd>
          </div>
          <div>
            <dt>Medication</dt>
            <dd>{order.drugName}</dd>
          </div>
          <div>
            <dt>Quantity</dt>
            <dd>{quantityLabel(order)}</dd>
          </div>
        </dl>
        {error ? <p className="pharm-dialog__error">{error}</p> : null}
        <div className="cashier-confirm__actions">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={onConfirm} busy={busy} busyLabel="Dispensing…">
            Confirm Dispense
          </Button>
        </div>
      </div>
    </div>
  );
}

interface GenericSelectorProps {
  draft: PharmacyCatalogueDraft;
  disabled?: boolean;
  onChange: (draft: PharmacyCatalogueDraft) => void;
  onError: (message: string) => void;
}

function GenericSelector({ draft, disabled, onChange, onError }: GenericSelectorProps) {
  const [query, setQuery] = useState(draft.genericName || "");
  const [hits, setHits] = useState<PharmacyGenericOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    if (draft.conceptUuid && draft.genericName) {
      setQuery(draft.genericName);
    }
  }, [draft.conceptUuid, draft.genericName]);

  useEffect(() => {
    const term = query.trim();
    if (draft.conceptUuid && term.toLowerCase() === draft.genericName.trim().toLowerCase()) {
      setHits([]);
      setOpen(false);
      return;
    }
    if (term.length < 2) {
      setHits([]);
      setSearching(false);
      return;
    }
    const current = ++requestId.current;
    setSearching(true);
    const timer = window.setTimeout(() => {
      void searchPharmacyGenerics(term)
        .then((payload) => {
          if (current !== requestId.current) {
            return;
          }
          setHits(payload.generics || []);
          setOpen(true);
        })
        .catch(() => {
          if (current !== requestId.current) {
            return;
          }
          setHits([]);
          onError("Generics could not be searched. Try again.");
        })
        .finally(() => {
          if (current === requestId.current) {
            setSearching(false);
          }
        });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [draft.conceptUuid, draft.genericName, onError, query]);

  const selectGeneric = (row: PharmacyGenericOption) => {
    onChange({
      ...draft,
      conceptUuid: row.uuid,
      genericName: row.name,
    });
    setQuery(row.name);
    setHits([]);
    setOpen(false);
    onError("");
  };

  const clearGeneric = () => {
    onChange({ ...draft, conceptUuid: "", genericName: "" });
    setQuery("");
    setHits([]);
    setOpen(false);
  };

  const createGeneric = async () => {
    const name = query.trim();
    if (name.length < 2 || creating) {
      return;
    }
    setCreating(true);
    onError("");
    try {
      const created = await createPharmacyGeneric(name);
      selectGeneric({ uuid: created.uuid, name: created.name });
    } catch (reason) {
      onError(pharmacyStaffError(reason, "The generic could not be saved."));
    } finally {
      setCreating(false);
    }
  };

  const exactHit = hits.some((row) => row.name.toLowerCase() === query.trim().toLowerCase());
  const showCreate =
    open && query.trim().length >= 2 && !searching && !exactHit && !draft.conceptUuid;

  return (
    <div className="pharm-generic-selector">
      <label>
        Generic
        <input
          value={query}
          disabled={disabled}
          onChange={(event) => {
            const value = event.target.value;
            setQuery(value);
            if (draft.conceptUuid) {
              onChange({ ...draft, conceptUuid: "", genericName: "" });
            }
          }}
          onFocus={() => {
            if (hits.length) {
              setOpen(true);
            }
          }}
          placeholder="Search and select generic…"
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={open}
        />
      </label>
      {draft.conceptUuid ? (
        <div className="pharm-generic-selector__selected">
          <span>Selected: {draft.genericName}</span>
          <button type="button" onClick={clearGeneric} disabled={disabled}>
            Change
          </button>
        </div>
      ) : null}
      {searching ? <p className="pharm-generic-selector__hint">Searching generics…</p> : null}
      {open && !draft.conceptUuid && hits.length > 0 ? (
        <ul className="pharm-generic-selector__results" role="listbox">
          {hits.map((row) => (
            <li key={row.uuid}>
              <button type="button" onClick={() => selectGeneric(row)} disabled={disabled}>
                {row.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {open && !draft.conceptUuid && !searching && query.trim().length >= 2 && hits.length === 0 ? (
        <p className="pharm-generic-selector__hint">No generic matches that search.</p>
      ) : null}
      {showCreate ? (
        <div className="pharm-generic-selector__create">
          <Button type="button" variant="secondary" onClick={() => void createGeneric()} disabled={disabled || creating}>
            {creating ? "Creating generic…" : `Create generic “${query.trim()}”`}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function DosageFormFields({
  form,
  customForm = "",
  forms,
  disabled,
  invalid,
  ariaLabel,
  onChange,
}: {
  form: string;
  customForm?: string;
  forms: string[];
  disabled?: boolean;
  invalid?: boolean;
  ariaLabel: string;
  onChange: (next: { form: string; customForm: string }) => void;
}) {
  const choices = dosageFormChoices(forms, form);
  const selected = choices.includes(form) ? form : choices[0] || form;
  const unlisted = isUnlistedDosageForm(selected);
  return (
    <div className="pharm-catalogue-form-pick">
      <select
        value={selected}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-invalid={invalid}
        onChange={(event) => {
          const next = event.target.value;
          onChange({
            form: next,
            customForm: isUnlistedDosageForm(next) ? customForm : "",
          });
        }}
      >
        {choices.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      {unlisted ? (
        <input
          value={customForm}
          disabled={disabled}
          placeholder="e.g. Sachet"
          autoComplete="off"
          aria-label="Write the dosage form"
          aria-invalid={invalid}
          onChange={(event) => onChange({ form: selected, customForm: event.target.value })}
        />
      ) : null}
    </div>
  );
}

interface CatalogueFormDialogProps {
  mode: "add" | "edit";
  draft: PharmacyCatalogueDraft;
  forms: string[];
  stockLabel?: string;
  busy?: boolean;
  error?: string;
  onChange: (draft: PharmacyCatalogueDraft) => void;
  onCancel: () => void;
  onSave: () => void;
  onError: (message: string) => void;
}

export function CatalogueFormDialog({
  mode,
  draft,
  forms,
  stockLabel,
  busy,
  error,
  onChange,
  onCancel,
  onSave,
  onError,
}: CatalogueFormDialogProps) {
  const title = mode === "add" ? "Create Medicine" : "Edit medicine";
  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="catalogue-form-title">
      <div className="abikan-dialog__panel cashier-confirm">
        <h2 id="catalogue-form-title">{title}</h2>
        <p>
          {mode === "add"
            ? "Choose the product name and the generic separately. Stock on the shelf cannot be changed here."
            : "Stock on the shelf cannot be changed here."}
        </p>
        <form
          className="pharm-catalogue-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSave();
          }}
        >
          <label>
            Medicine / product name
            <input
              value={draft.name}
              onChange={(event) => onChange({ ...draft, name: event.target.value })}
              placeholder="As written on the pack or hospital list"
              autoComplete="off"
            />
          </label>
          {mode === "add" ? (
            <GenericSelector draft={draft} disabled={busy} onChange={onChange} onError={onError} />
          ) : draft.genericName ? (
            <p className="pharm-catalogue-form__stock">Generic: {draft.genericName}</p>
          ) : null}
          <label>
            Brand name (optional)
            <input
              value={draft.brandName}
              onChange={(event) => onChange({ ...draft, brandName: event.target.value })}
              placeholder="Leave blank if none"
              autoComplete="off"
            />
          </label>
          <label>
            Strength
            <input
              value={draft.strength}
              onChange={(event) => onChange({ ...draft, strength: event.target.value })}
              placeholder="As written on the pack"
              autoComplete="off"
            />
          </label>
          <label>
            Dosage form
            <DosageFormFields
              form={draft.form}
              customForm={draft.customForm}
              forms={forms}
              disabled={busy}
              ariaLabel="Dosage form"
              onChange={(next) => onChange({ ...draft, ...next })}
            />
          </label>
          {mode === "add" ? (
            <label>
              Manufacturer
              <input
                value={draft.manufacturer}
                onChange={(event) => onChange({ ...draft, manufacturer: event.target.value })}
                placeholder="Optional"
                autoComplete="off"
              />
            </label>
          ) : null}
          <label>
            Selling price (₦)
            <input
              value={draft.price}
              onChange={(event) => onChange({ ...draft, price: event.target.value })}
              inputMode="decimal"
            />
          </label>
          {stockLabel ? (
            <p className="pharm-catalogue-form__stock">
              Stock: {stockLabel}. Receiving and adjusting stock will be a separate step.
            </p>
          ) : (
            <p className="pharm-catalogue-form__stock">
              New medicines start with none in stock. Receiving stock will be a separate step.
            </p>
          )}
          <label className="pharm-catalogue-form__check">
            <input
              type="checkbox"
              checked={draft.available}
              onChange={(event) => onChange({ ...draft, available: event.target.checked })}
            />
            Available
          </label>
          {error ? <p className="pharm-dialog__error">{error}</p> : null}
          <div className="cashier-confirm__actions">
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : mode === "add" ? "Create Medicine" : "Save medicine"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface InventoryHistoryDialogProps {
  item: PharmacyInventoryItem;
  movements: PharmacyInventoryHistoryRow[];
  loading?: boolean;
  error?: string;
  onClose: () => void;
}

export function InventoryHistoryDialog({
  item,
  movements,
  loading,
  error,
  onClose,
}: InventoryHistoryDialogProps) {
  return (
    <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="inventory-history-title">
      <div className="abikan-dialog__panel cashier-confirm pharm-history-panel">
        <h2 id="inventory-history-title">Stock history</h2>
        <p>
          {item.name}
          {item.strength || item.form ? ` · ${[item.strength, item.form].filter(Boolean).join(" · ")}` : ""}
        </p>
        {loading ? <p className="pharm-catalogue-form__stock">Loading history…</p> : null}
        {error ? <p className="pharm-dialog__error">{error}</p> : null}
        {!loading && !error && movements.length === 0 ? (
          <p className="pharm-catalogue-form__stock">No stock movements recorded yet.</p>
        ) : null}
        {!loading && movements.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Type</th>
                  <th>Change</th>
                  <th>Result</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((row) => (
                  <tr key={row.id}>
                    <td>{row.when.replace("T", " ").slice(0, 16)}</td>
                    <td>{row.movementType}</td>
                    <td>
                      {row.movementQuantity > 0 ? "+" : ""}
                      {formatStockQty(row.movementQuantity)}
                    </td>
                    <td>{formatStockQty(row.resultingQuantity)}</td>
                    <td>
                      {[
                        row.purchasePricePerUnit
                          ? `Purchase ₦${row.purchasePricePerUnit.toLocaleString("en-NG")}/unit`
                          : "",
                        row.purchaseCost != null ? `Cost ₦${row.purchaseCost.toLocaleString("en-NG")}` : "",
                        row.supplier,
                        row.reason,
                        row.user,
                        row.reference,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="cashier-confirm__actions">
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}
