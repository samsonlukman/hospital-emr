import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { Plus, Save, Trash2 } from "lucide-react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { SectionHeader } from "../../components/SectionHeader";
import {
  createPharmacyCatalogueBatch,
  createPharmacyGeneric,
  searchPharmacyGenerics,
} from "../../services/pharmacy";
import type { PharmacyCatalogueLineDraft, PharmacyGenericOption } from "../../types/pharmacy";
import { DosageFormFields } from "./PharmacyDialogs";
import {
  catalogueLineErrors,
  emptyCatalogueLine,
  pharmacyStaffError,
} from "./pharmacyView";

function RemoveRowButton({
  disabled,
  label,
  onClick,
}: {
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className="pharm-stock-table__remove" disabled={disabled} aria-label={label} onClick={onClick}>
      <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}

function GenericCell({
  line,
  disabled,
  onChange,
  onError,
}: {
  line: PharmacyCatalogueLineDraft;
  disabled?: boolean;
  onChange: (next: PharmacyCatalogueLineDraft) => void;
  onError: (message: string) => void;
}) {
  const [query, setQuery] = useState(line.genericName || "");
  const [hits, setHits] = useState<PharmacyGenericOption[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [creating, setCreating] = useState(false);
  const [hitIndex, setHitIndex] = useState(0);
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (line.conceptUuid && line.genericName) {
      setQuery(line.genericName);
    }
  }, [line.conceptUuid, line.genericName]);

  useEffect(() => {
    const term = query.trim();
    if (line.conceptUuid && term.toLowerCase() === line.genericName.trim().toLowerCase()) {
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
          setHitIndex(0);
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
  }, [line.conceptUuid, line.genericName, onError, query]);

  useEffect(() => {
    if (!open || line.conceptUuid) {
      setMenuStyle(null);
      return;
    }
    const place = () => {
      const input = inputRef.current;
      if (!input) {
        setMenuStyle(null);
        return;
      }
      const rect = input.getBoundingClientRect();
      const width = Math.max(rect.width, 240);
      const gap = 4;
      const maxHeight = 220;
      const spaceBelow = window.innerHeight - rect.bottom - gap - 12;
      const openUp = spaceBelow < 140;
      setMenuStyle({
        position: "fixed",
        top: openUp ? Math.max(12, rect.top - gap - Math.min(maxHeight, rect.top - 12)) : rect.bottom + gap,
        left: Math.min(rect.left, Math.max(12, window.innerWidth - width - 12)),
        width,
        maxHeight,
        zIndex: 10000,
      });
    };

    const closeMenu = () => {
      setOpen(false);
      setHits([]);
      setMenuStyle(null);
    };

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) {
        return;
      }
      if (inputRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      closeMenu();
    };

    const onKeyDown = (event: Event) => {
      if ((event as globalThis.KeyboardEvent).key === "Escape") {
        closeMenu();
      }
    };

    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [hits.length, line.conceptUuid, open, query]);

  const selectGeneric = (row: PharmacyGenericOption) => {
    onChange({
      ...line,
      conceptUuid: row.uuid,
      genericName: row.name,
      fieldErrors: { ...line.fieldErrors, generic: undefined },
    });
    setQuery(row.name);
    setHits([]);
    setOpen(false);
    setMenuStyle(null);
    onError("");
  };

  const clearGeneric = () => {
    onChange({ ...line, conceptUuid: "", genericName: "", fieldErrors: { ...line.fieldErrors, generic: undefined } });
    setQuery("");
    setHits([]);
    setOpen(false);
    setMenuStyle(null);
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
  const showCreate = open && query.trim().length >= 2 && !searching && !exactHit && !line.conceptUuid;

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setHits([]);
      setMenuStyle(null);
      return;
    }
    if (!open || line.conceptUuid) {
      return;
    }
    if (event.key === "ArrowDown" && hits.length) {
      event.preventDefault();
      setHitIndex((current) => (current + 1) % hits.length);
      return;
    }
    if (event.key === "ArrowUp" && hits.length) {
      event.preventDefault();
      setHitIndex((current) => (current - 1 + hits.length) % hits.length);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (hits[hitIndex]) {
        selectGeneric(hits[hitIndex]);
      } else if (showCreate) {
        void createGeneric();
      }
    }
  };

  return (
    <div className="pharm-catalogue-add__generic">
      {line.conceptUuid ? (
        <div className="pharm-stock-table__selected">
          <div className="pharm-stock-table__selected-copy">
            <strong>{line.genericName}</strong>
          </div>
          <button type="button" className="pharm-stock-table__change" disabled={disabled} onClick={clearGeneric}>
            Change
          </button>
        </div>
      ) : (
        <input
          ref={inputRef}
          value={query}
          disabled={disabled}
          onChange={(event) => {
            const value = event.target.value;
            setQuery(value);
            if (line.conceptUuid) {
              onChange({ ...line, conceptUuid: "", genericName: "" });
            }
          }}
          onFocus={() => {
            if (hits.length || query.trim().length >= 2) {
              setOpen(true);
            }
          }}
          onKeyDown={onKeyDown}
          placeholder="Search generic…"
          autoComplete="off"
          aria-label="Generic"
          aria-invalid={Boolean(line.fieldErrors.generic)}
        />
      )}
      {line.fieldErrors.generic ? (
        <span className="pharm-stock-entry__field-error">{line.fieldErrors.generic}</span>
      ) : null}
      {open && !line.conceptUuid && menuStyle
        ? createPortal(
            <div ref={menuRef} className="pharm-catalogue-add__generic-menu" style={menuStyle}>
              {searching ? <p className="pharm-catalogue-add__hint">Searching generics…</p> : null}
              {!searching && hits.length > 0 ? (
                <ul className="pharm-stock-table__hits pharm-stock-table__hits--portal" role="listbox">
                  {hits.map((row, index) => (
                    <li key={row.uuid}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={index === hitIndex}
                        className={index === hitIndex ? "is-active" : undefined}
                        disabled={disabled}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectGeneric(row)}
                      >
                        <strong>{row.name}</strong>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {!searching && query.trim().length >= 2 && hits.length === 0 ? (
                <p className="pharm-catalogue-add__hint">No generic matches that search.</p>
              ) : null}
              {showCreate ? (
                <button
                  type="button"
                  className="pharm-catalogue-add__create-generic"
                  disabled={disabled || creating}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => void createGeneric()}
                >
                  {creating ? "Creating generic…" : `Create generic “${query.trim()}”`}
                </button>
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

export function PharmacyCatalogueAddView({
  forms,
  onCancel,
  onCompleted,
}: {
  forms: string[];
  onCancel: () => void;
  onCompleted: (message: string) => void;
}) {
  const defaultForm = forms[0] || "Tablet";
  const [lines, setLines] = useState<PharmacyCatalogueLineDraft[]>(() => [emptyCatalogueLine(defaultForm)]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const nameFocusKey = useRef<string | null>(null);
  const nameRefs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    const key = nameFocusKey.current;
    if (!key) {
      return;
    }
    const node = nameRefs.current[key];
    if (node) {
      node.focus();
    }
    nameFocusKey.current = null;
  }, [lines]);

  const readyCount = lines.filter((line) => line.name.trim() || line.conceptUuid || line.strength.trim()).length;
  const saveCount = lines.filter((line) => Object.keys(catalogueLineErrors(line)).length === 0).length;

  const updateLine = (key: string, patch: Partial<PharmacyCatalogueLineDraft>) => {
    setLines((current) =>
      current.map((line) => (line.key === key ? { ...line, ...patch, fieldErrors: { ...line.fieldErrors, ...patch.fieldErrors } } : line)),
    );
  };

  const addLine = () => {
    const next = emptyCatalogueLine(defaultForm);
    setLines((current) => [...current, next]);
    nameFocusKey.current = next.key;
  };

  const submit = async () => {
    setError("");
    let invalid = false;
    const validated = lines.map((line) => {
      const fieldErrors = catalogueLineErrors(line);
      if (Object.keys(fieldErrors).length) {
        invalid = true;
      }
      return { ...line, fieldErrors };
    });
    setLines(validated);
    if (invalid) {
      setError("Fix the highlighted rows before saving.");
      return;
    }
    if (validated.length === 0) {
      setError("Add at least one medicine.");
      return;
    }
    setBusy(true);
    try {
      const result = await createPharmacyCatalogueBatch(validated);
      if (result.status === "partial") {
        setError(result.message || "Some medicines could not be saved.");
        return;
      }
      onCompleted(result.message || `${result.count} medicines added to the catalogue.`);
    } catch (reason) {
      setError(pharmacyStaffError(reason, "The medicines could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="catalogue-add" className="pharm-catalogue-add">
      <div className="pharm-catalogue-add__top">
        <div>
          <button type="button" className="pharm-catalogue-add__back" onClick={onCancel} disabled={busy}>
            ← Back to Drug Catalogue
          </button>
          <SectionHeader
            title="Add Multiple Medicines"
            description="Add one or more medicines to the catalogue. Stock levels cannot be changed here."
          />
        </div>
        <div className="pharm-catalogue-add__banner" role="note">
          New medicines start with none in stock. Receiving stock will be a separate step.
        </div>
      </div>

      {error ? (
        <Alert tone="danger" title="Could not save medicines">
          <p>{error}</p>
        </Alert>
      ) : null}

      <section className="pharm-stock-entry__medicines" aria-label="Medicines">
        <div className="pharm-stock-entry__medicines-head">
          <div>
            <h3 className="pharm-stock-entry__medicines-title">Medicines</h3>
            <p className="pharm-stock-entry__medicines-copy">
              Fill in the details for each medicine. You can add as many as you need.
            </p>
          </div>
          <button type="button" className="pharm-stock-entry__add-btn" disabled={busy} onClick={addLine}>
            <Plus size={16} strokeWidth={2.25} aria-hidden="true" />
            Add another medicine
          </button>
        </div>

        <div className="pharm-stock-table-wrap">
          <table className="pharm-stock-table pharm-catalogue-add__table">
            <thead>
              <tr>
                <th className="pharm-stock-table__num">#</th>
                <th>Medicine / product name *</th>
                <th>Generic *</th>
                <th>Brand name</th>
                <th>Strength *</th>
                <th>Dosage form *</th>
                <th>Manufacturer</th>
                <th>Selling price (₦) *</th>
                <th>Available</th>
                <th className="pharm-stock-table__action">Action</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => {
                const invalid = Object.keys(line.fieldErrors).length > 0;
                return (
                  <tr key={line.key} className={invalid ? "is-invalid" : undefined}>
                    <td className="pharm-stock-table__num">
                      <span className="pharm-stock-table__index">{index + 1}</span>
                    </td>
                    <td>
                      <input
                        ref={(node) => {
                          nameRefs.current[line.key] = node;
                        }}
                        value={line.name}
                        disabled={busy}
                        placeholder="Type medicine name…"
                        autoComplete="off"
                        aria-label={`Medicine name ${index + 1}`}
                        aria-invalid={Boolean(line.fieldErrors.name)}
                        onChange={(event) =>
                          updateLine(line.key, {
                            name: event.target.value,
                            fieldErrors: { ...line.fieldErrors, name: undefined },
                          })
                        }
                      />
                      {line.fieldErrors.name ? (
                        <span className="pharm-stock-entry__field-error">{line.fieldErrors.name}</span>
                      ) : null}
                    </td>
                    <td>
                      <GenericCell
                        line={line}
                        disabled={busy}
                        onError={setError}
                        onChange={(next) => setLines((current) => current.map((row) => (row.key === line.key ? next : row)))}
                      />
                    </td>
                    <td>
                      <input
                        value={line.brandName}
                        disabled={busy}
                        placeholder="Optional"
                        autoComplete="off"
                        aria-label={`Brand name ${index + 1}`}
                        onChange={(event) => updateLine(line.key, { brandName: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={line.strength}
                        disabled={busy}
                        placeholder="e.g. 500mg"
                        autoComplete="off"
                        aria-label={`Strength ${index + 1}`}
                        aria-invalid={Boolean(line.fieldErrors.strength)}
                        onChange={(event) =>
                          updateLine(line.key, {
                            strength: event.target.value,
                            fieldErrors: { ...line.fieldErrors, strength: undefined },
                          })
                        }
                      />
                      {line.fieldErrors.strength ? (
                        <span className="pharm-stock-entry__field-error">{line.fieldErrors.strength}</span>
                      ) : null}
                    </td>
                    <td>
                      <DosageFormFields
                        form={line.form}
                        customForm={line.customForm}
                        forms={forms}
                        disabled={busy}
                        invalid={Boolean(line.fieldErrors.form)}
                        ariaLabel={`Dosage form ${index + 1}`}
                        onChange={(next) =>
                          updateLine(line.key, {
                            ...next,
                            fieldErrors: { ...line.fieldErrors, form: undefined },
                          })
                        }
                      />
                      {line.fieldErrors.form ? (
                        <span className="pharm-stock-entry__field-error">{line.fieldErrors.form}</span>
                      ) : null}
                    </td>
                    <td>
                      <input
                        value={line.manufacturer}
                        disabled={busy}
                        placeholder="Optional"
                        autoComplete="off"
                        aria-label={`Manufacturer ${index + 1}`}
                        onChange={(event) => updateLine(line.key, { manufacturer: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={line.price}
                        disabled={busy}
                        inputMode="decimal"
                        placeholder="0.00"
                        autoComplete="off"
                        aria-label={`Selling price ${index + 1}`}
                        aria-invalid={Boolean(line.fieldErrors.price)}
                        onChange={(event) =>
                          updateLine(line.key, {
                            price: event.target.value,
                            fieldErrors: { ...line.fieldErrors, price: undefined },
                          })
                        }
                      />
                      {line.fieldErrors.price ? (
                        <span className="pharm-stock-entry__field-error">{line.fieldErrors.price}</span>
                      ) : null}
                    </td>
                    <td className="pharm-catalogue-add__available">
                      <input
                        type="checkbox"
                        checked={line.available}
                        disabled={busy}
                        aria-label={`Available ${index + 1}`}
                        onChange={(event) => updateLine(line.key, { available: event.target.checked })}
                      />
                    </td>
                    <td className="pharm-stock-table__action">
                      <RemoveRowButton
                        disabled={busy || lines.length <= 1}
                        label={`Remove medicine ${index + 1}`}
                        onClick={() => setLines((current) => current.filter((row) => row.key !== line.key))}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <button type="button" className="pharm-stock-entry__add-btn" disabled={busy} onClick={addLine}>
          <Plus size={16} strokeWidth={2.25} aria-hidden="true" />
          Add another medicine
        </button>
      </section>

      <div className="pharm-stock-entry__footer">
        <div className="pharm-catalogue-add__summary-pill">
          {readyCount} medicine{readyCount === 1 ? "" : "s"} will be added to the catalogue
        </div>
        <div className="pharm-stock-entry__actions">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            className="pharm-stock-entry__save"
            busy={busy}
            busyLabel="Saving…"
            disabled={lines.length === 0}
            onClick={() => void submit()}
          >
            <Save size={16} strokeWidth={2} aria-hidden="true" />
            {saveCount > 1 ? `Save ${saveCount} Medicines` : "Save Medicines"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
