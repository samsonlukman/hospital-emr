import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { Plus, Save, Trash2 } from "lucide-react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { SectionHeader } from "../../components/SectionHeader";
import {
  adjustPharmacyStockBatch,
  receivePharmacyStockBatch,
} from "../../services/pharmacy";
import type {
  PharmacyAdjustLineDraft,
  PharmacyInventoryItem,
  PharmacyReceiveLineDraft,
} from "../../types/pharmacy";
import {
  ADJUST_REASONS,
  adjustLineErrors,
  emptyAdjustLine,
  emptyReceiveLine,
  formatStockQty,
  matchesInventorySearch,
  pharmacyStaffError,
  receiveLineErrors,
  resultingOnHand,
} from "./pharmacyView";

export type StockEntryMode = "receive" | "adjust";

function medicineMeta(
  line: Pick<PharmacyReceiveLineDraft, "strength" | "form" | "onHand" | "sellingPriceLabel">,
): string {
  const bits = [line.strength, line.form].filter(Boolean);
  if (!bits.length) {
    return `On hand ${formatStockQty(line.onHand)}`;
  }
  return `${bits.join(" · ")} · On hand ${formatStockQty(line.onHand)}`;
}

function lineQuantity(lines: Array<{ drugUuid: string; quantity: string }>): number {
  return lines.reduce((sum, line) => {
    if (!line.drugUuid) {
      return sum;
    }
    const qty = Number(line.quantity);
    return Number.isFinite(qty) && qty > 0 ? sum + qty : sum;
  }, 0);
}

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
    <button
      type="button"
      className="pharm-stock-table__remove"
      disabled={disabled}
      aria-label={label}
      onClick={onClick}
    >
      <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}

export function PharmacyStockEntryView({
  mode,
  inventory,
  seed,
  reasons = ADJUST_REASONS,
  onCancel,
  onCompleted,
}: {
  mode: StockEntryMode;
  inventory: PharmacyInventoryItem[];
  seed?: PharmacyInventoryItem | null;
  reasons?: string[];
  onCancel: () => void;
  onCompleted: (message: string) => void;
}) {
  const [supplier, setSupplier] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [receiveLines, setReceiveLines] = useState<PharmacyReceiveLineDraft[]>(() => [
    emptyReceiveLine(seed),
  ]);
  const [adjustLines, setAdjustLines] = useState<PharmacyAdjustLineDraft[]>(() => [
    emptyAdjustLine(seed),
  ]);
  const [activeSearchKey, setActiveSearchKey] = useState<string | null>(
    seed?.id ? null : (mode === "receive" ? receiveLines[0]?.key : adjustLines[0]?.key) || null,
  );
  const [medicineQuery, setMedicineQuery] = useState("");
  const [hitIndex, setHitIndex] = useState(0);
  const [hitMenuStyle, setHitMenuStyle] = useState<CSSProperties | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const searchRef = useRef<HTMLInputElement | null>(null);
  const hitsMenuRef = useRef<HTMLUListElement | null>(null);
  const qtyFocusKey = useRef<string | null>(null);
  const qtyRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const selectable = useMemo(
    () =>
      inventory.filter((row) => (mode === "receive" ? row.canReceive : row.canAdjust) && !row.protectedTest),
    [inventory, mode],
  );

  const medicineHits = useMemo(() => {
    if (!medicineQuery.trim()) {
      return [];
    }
    return selectable.filter((row) => matchesInventorySearch(row, medicineQuery)).slice(0, 8);
  }, [selectable, medicineQuery]);

  useEffect(() => {
    if (activeSearchKey && searchRef.current) {
      searchRef.current.focus();
    }
  }, [activeSearchKey]);

  useEffect(() => {
    setHitIndex(0);
  }, [medicineQuery, activeSearchKey]);

  useEffect(() => {
    if (!activeSearchKey) {
      setHitMenuStyle(null);
      return;
    }

    const placeMenu = () => {
      const input = searchRef.current;
      if (!input) {
        setHitMenuStyle(null);
        return;
      }
      const rect = input.getBoundingClientRect();
      const width = Math.max(rect.width, 280);
      const maxHeight = 256;
      const gap = 4;
      const spaceBelow = window.innerHeight - rect.bottom - gap - 12;
      const spaceAbove = rect.top - gap - 12;
      const openUp = spaceBelow < 160 && spaceAbove > spaceBelow;
      const top = openUp
        ? Math.max(12, rect.top - gap - Math.min(maxHeight, spaceAbove))
        : rect.bottom + gap;
      const left = Math.min(rect.left, Math.max(12, window.innerWidth - width - 12));
      setHitMenuStyle({
        position: "fixed",
        top,
        left,
        width,
        maxHeight: openUp ? Math.min(maxHeight, spaceAbove) : Math.min(maxHeight, Math.max(spaceBelow, 120)),
        zIndex: 10000,
      });
    };

    const closeSearch = () => {
      setActiveSearchKey(null);
      setMedicineQuery("");
      setHitMenuStyle(null);
    };

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) {
        return;
      }
      if (searchRef.current?.contains(target)) {
        return;
      }
      if (hitsMenuRef.current?.contains(target)) {
        return;
      }
      closeSearch();
    };

    const onKeyDown = (event: Event) => {
      if ((event as globalThis.KeyboardEvent).key === "Escape") {
        closeSearch();
      }
    };

    placeMenu();
    window.addEventListener("resize", placeMenu);
    window.addEventListener("scroll", placeMenu, true);
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.removeEventListener("resize", placeMenu);
      window.removeEventListener("scroll", placeMenu, true);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [activeSearchKey, medicineQuery, receiveLines.length, adjustLines.length]);

  useEffect(() => {
    const key = qtyFocusKey.current;
    if (!key) {
      return;
    }
    const node = qtyRefs.current[key];
    if (node) {
      node.focus();
      node.select();
    }
    qtyFocusKey.current = null;
  }, [receiveLines, adjustLines]);

  const receiveCount = receiveLines.filter((line) => line.drugUuid).length;
  const adjustCount = adjustLines.filter((line) => line.drugUuid).length;
  const lineCount = mode === "receive" ? receiveCount : adjustCount;
  const totalQty =
    mode === "receive" ? lineQuantity(receiveLines) : lineQuantity(adjustLines);

  const receiveCost = receiveLines.reduce((sum, line) => {
    const qty = Number(line.quantity);
    const price = Number(line.purchasePrice);
    if (!line.drugUuid || !Number.isFinite(qty) || !Number.isFinite(price) || qty <= 0 || price <= 0) {
      return sum;
    }
    return sum + qty * price;
  }, 0);

  const chooseMedicine = (key: string, item: PharmacyInventoryItem) => {
    if (mode === "receive") {
      setReceiveLines((current) =>
        current.map((line) =>
          line.key === key
            ? {
                ...line,
                drugUuid: item.id,
                drugName: item.name,
                strength: item.strength || "",
                form: item.form || "",
                onHand: item.onHand,
                sellingPriceLabel: item.sellingPrice?.formatted || "",
                fieldErrors: { ...line.fieldErrors, drug: undefined },
              }
            : line,
        ),
      );
    } else {
      setAdjustLines((current) =>
        current.map((line) =>
          line.key === key
            ? {
                ...line,
                drugUuid: item.id,
                drugName: item.name,
                strength: item.strength || "",
                form: item.form || "",
                onHand: item.onHand,
                reserved: item.reserved,
                fieldErrors: { ...line.fieldErrors, drug: undefined },
              }
            : line,
        ),
      );
    }
    setMedicineQuery("");
    setActiveSearchKey(null);
    setHitMenuStyle(null);
    qtyFocusKey.current = key;
  };

  const clearMedicine = (key: string) => {
    if (mode === "receive") {
      setReceiveLines((current) =>
        current.map((row) =>
          row.key === key
            ? {
                ...row,
                drugUuid: "",
                drugName: "",
                strength: "",
                form: "",
                sellingPriceLabel: "",
              }
            : row,
        ),
      );
    } else {
      setAdjustLines((current) =>
        current.map((row) =>
          row.key === key
            ? {
                ...row,
                drugUuid: "",
                drugName: "",
                strength: "",
                form: "",
              }
            : row,
        ),
      );
    }
    setActiveSearchKey(key);
    setMedicineQuery("");
  };

  const addReceiveLine = () => {
    const next = emptyReceiveLine();
    setReceiveLines((current) => [...current, next]);
    setActiveSearchKey(next.key);
    setMedicineQuery("");
  };

  const addAdjustLine = () => {
    const next = emptyAdjustLine();
    setAdjustLines((current) => [...current, next]);
    setActiveSearchKey(next.key);
    setMedicineQuery("");
  };

  const onSearchKeyDown = (key: string, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setActiveSearchKey(null);
      setMedicineQuery("");
      setHitMenuStyle(null);
      return;
    }
    if (!medicineHits.length) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHitIndex((current) => (current + 1) % medicineHits.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHitIndex((current) => (current - 1 + medicineHits.length) % medicineHits.length);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const hit = medicineHits[hitIndex] || medicineHits[0];
      if (hit) {
        chooseMedicine(key, hit);
      }
    }
  };

  const submitReceive = async () => {
    setError("");
    let invalid = false;
    const validated = receiveLines.map((line) => {
      const fieldErrors = receiveLineErrors(line);
      if (Object.keys(fieldErrors).length) {
        invalid = true;
      }
      return { ...line, fieldErrors };
    });
    setReceiveLines(validated);
    if (invalid) {
      setError("Fix the highlighted rows before saving.");
      return;
    }
    const prepared = validated
      .filter((line) => line.drugUuid)
      .map((line) => ({
        drugUuid: line.drugUuid,
        quantity: Number(line.quantity),
        purchasePrice: Number(line.purchasePrice),
      }));
    if (prepared.length === 0) {
      setError("Add at least one medicine.");
      return;
    }
    setBusy(true);
    try {
      const result = await receivePharmacyStockBatch({
        supplier: supplier.trim(),
        reference: reference.trim(),
        note: note.trim(),
        lines: prepared,
      });
      onCompleted(result.message || `${result.count} medicines added to inventory.`);
    } catch (reason) {
      setError(pharmacyStaffError(reason, "The stock receipt could not be recorded."));
    } finally {
      setBusy(false);
    }
  };

  const submitAdjust = async () => {
    setError("");
    let invalid = false;
    const validated = adjustLines.map((line) => {
      const fieldErrors = adjustLineErrors(line);
      if (Object.keys(fieldErrors).length) {
        invalid = true;
      }
      return { ...line, fieldErrors };
    });
    setAdjustLines(validated);
    if (invalid) {
      setError("Fix the highlighted rows before saving.");
      return;
    }
    const prepared = validated
      .filter((line) => line.drugUuid)
      .map((line) => ({
        drugUuid: line.drugUuid,
        direction: line.direction,
        quantity: Number(line.quantity),
        reason: line.reason.trim(),
      }));
    if (prepared.length === 0) {
      setError("Add at least one medicine.");
      return;
    }
    setBusy(true);
    try {
      const result = await adjustPharmacyStockBatch({
        reference: reference.trim(),
        note: note.trim(),
        lines: prepared,
      });
      if (result.status === "partial") {
        setError(result.message || "Some medicines could not be adjusted.");
        return;
      }
      onCompleted(result.message || `${result.count} medicines adjusted in inventory.`);
    } catch (reason) {
      setError(pharmacyStaffError(reason, "The stock adjustment could not be recorded."));
    } finally {
      setBusy(false);
    }
  };

  const title = mode === "receive" ? "Receive Stock" : "Adjust Stock";
  const description =
    mode === "receive"
      ? "Record multiple medicines that have arrived. Add all medicines in this delivery, then save once."
      : "Record stock count corrections for one or more medicines, then save once.";

  const renderMedicineCell = (
    key: string,
    selected: {
      drugUuid: string;
      drugName: string;
      strength: string;
      form: string;
      onHand: number;
      sellingPriceLabel?: string;
    },
    fieldError?: string,
  ) => {
    const searching = activeSearchKey === key && !selected.drugUuid;
    return (
      <div className="pharm-stock-table__medicine">
        {selected.drugUuid ? (
          <div className="pharm-stock-table__selected">
            <div className="pharm-stock-table__selected-copy">
              <strong>{selected.drugName}</strong>
              <span className="pharm-stock-table__meta">
                {medicineMeta({
                  strength: selected.strength,
                  form: selected.form,
                  onHand: selected.onHand,
                  sellingPriceLabel: selected.sellingPriceLabel || "",
                })}
              </span>
            </div>
            <button
              type="button"
              className="pharm-stock-table__change"
              disabled={busy}
              onClick={() => clearMedicine(key)}
            >
              Change
            </button>
          </div>
        ) : (
          <div className="pharm-stock-table__search">
            <input
              ref={searching ? searchRef : undefined}
              value={searching ? medicineQuery : ""}
              onChange={(event) => {
                setActiveSearchKey(key);
                setMedicineQuery(event.target.value);
              }}
              onFocus={() => setActiveSearchKey(key)}
              onKeyDown={(event) => onSearchKeyDown(key, event)}
              placeholder="Type to find a medicine"
              autoComplete="off"
              disabled={busy}
              aria-invalid={Boolean(fieldError)}
              aria-label="Medicine"
            />
            {searching && medicineHits.length > 0 && activeSearchKey && hitMenuStyle
              ? createPortal(
                  <ul
                    ref={hitsMenuRef}
                    className="pharm-stock-table__hits pharm-stock-table__hits--portal"
                    role="listbox"
                    style={hitMenuStyle}
                  >
                    {medicineHits.map((item, index) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={index === hitIndex}
                          className={index === hitIndex ? "is-active" : undefined}
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => chooseMedicine(activeSearchKey, item)}
                        >
                          <strong>{item.name}</strong>
                          <span>
                            {[item.strength, item.form, item.brandName].filter(Boolean).join(" · ") || "—"}
                            {` · On hand ${formatStockQty(item.onHand)}`}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>,
                  document.body,
                )
              : null}
            {searching && medicineQuery.trim() && medicineHits.length === 0 ? (
              <p className="pharm-stock-table__empty-hits">No matching medicines.</p>
            ) : null}
          </div>
        )}
        {fieldError ? <span className="pharm-stock-entry__field-error">{fieldError}</span> : null}
      </div>
    );
  };

  return (
    <Card id="stock-entry" className="pharm-stock-entry">
      <SectionHeader title={title} description={description} />

      {error ? (
        <Alert tone="danger" title={mode === "receive" ? "Could not receive stock" : "Could not adjust stock"}>
          <p>{error}</p>
        </Alert>
      ) : null}

      <section
        className={`pharm-stock-entry__receipt${mode === "receive" ? " pharm-stock-entry__receipt--receive" : ""}`}
        aria-label="Receipt information"
      >
        <div
          className={`pharm-stock-entry__shared${mode === "receive" ? " pharm-stock-entry__shared--receive" : ""}`}
        >
          {mode === "receive" ? (
            <label>
              Supplier (optional)
              <input
                value={supplier}
                onChange={(event) => setSupplier(event.target.value)}
                placeholder="Select supplier"
                autoComplete="off"
                disabled={busy}
              />
            </label>
          ) : null}
          <label>
            {mode === "receive" ? "Invoice / reference (optional)" : "Reference (optional)"}
            <input
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder={mode === "receive" ? "e.g. INV-001" : undefined}
              autoComplete="off"
              disabled={busy}
            />
          </label>
          <label className="pharm-stock-entry__note">
            Note (optional)
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={
                mode === "receive" ? "Add a note to this stock receipt…" : "Add a note to this adjustment…"
              }
              autoComplete="off"
              disabled={busy}
            />
          </label>
        </div>
      </section>

      <section className="pharm-stock-entry__medicines" aria-label="Medicines">
        <div className="pharm-stock-entry__medicines-head">
          <div>
            <h3 className="pharm-stock-entry__medicines-title">Medicines</h3>
            <p className="pharm-stock-entry__medicines-copy">
              {mode === "receive"
                ? "Add one or more medicines to this receipt. You can add as many as you need."
                : "Add one or more stock corrections. Same medicine can appear twice if reasons differ."}
            </p>
          </div>
          <button
            type="button"
            className="pharm-stock-entry__add-btn"
            disabled={busy}
            onClick={() => (mode === "receive" ? addReceiveLine() : addAdjustLine())}
          >
            <Plus size={16} strokeWidth={2.25} aria-hidden="true" />
            Add another medicine
          </button>
        </div>

        {mode === "receive" ? (
          <div className="pharm-stock-table-wrap">
            <table className="pharm-stock-table">
              <thead>
                <tr>
                  <th className="pharm-stock-table__num">#</th>
                  <th className="pharm-stock-table__med">Medicine</th>
                  <th className="pharm-stock-table__qty">Quantity</th>
                  <th className="pharm-stock-table__price">Purchase Cost (₦)</th>
                  <th className="pharm-stock-table__price">Selling Price (₦)</th>
                  <th className="pharm-stock-table__action">Action</th>
                </tr>
              </thead>
              <tbody>
                {receiveLines.map((line, index) => {
                  const invalid = Object.keys(line.fieldErrors).length > 0;
                  const isActive =
                    activeSearchKey === line.key || (!line.drugUuid && index === receiveLines.length - 1);
                  return (
                    <tr
                      key={line.key}
                      className={
                        [invalid ? "is-invalid" : "", isActive && !invalid ? "is-active" : ""]
                          .filter(Boolean)
                          .join(" ") || undefined
                      }
                    >
                      <td className="pharm-stock-table__num">
                        <span className="pharm-stock-table__index">{index + 1}</span>
                      </td>
                      <td className="pharm-stock-table__med">
                        {renderMedicineCell(line.key, line, line.fieldErrors.drug)}
                      </td>
                      <td className="pharm-stock-table__qty">
                        <input
                          ref={(node) => {
                            qtyRefs.current[line.key] = node;
                          }}
                          value={line.quantity}
                          onChange={(event) =>
                            setReceiveLines((current) =>
                              current.map((row) =>
                                row.key === line.key
                                  ? {
                                      ...row,
                                      quantity: event.target.value,
                                      fieldErrors: { ...row.fieldErrors, quantity: undefined },
                                    }
                                  : row,
                              ),
                            )
                          }
                          inputMode="decimal"
                          autoComplete="off"
                          disabled={busy}
                          aria-label={`Quantity for medicine ${index + 1}`}
                          aria-invalid={Boolean(line.fieldErrors.quantity)}
                        />
                        {line.fieldErrors.quantity ? (
                          <span className="pharm-stock-entry__field-error">{line.fieldErrors.quantity}</span>
                        ) : null}
                      </td>
                      <td className="pharm-stock-table__price">
                        <input
                          value={line.purchasePrice}
                          onChange={(event) =>
                            setReceiveLines((current) =>
                              current.map((row) =>
                                row.key === line.key
                                  ? {
                                      ...row,
                                      purchasePrice: event.target.value,
                                      fieldErrors: { ...row.fieldErrors, purchasePrice: undefined },
                                    }
                                  : row,
                              ),
                            )
                          }
                          inputMode="decimal"
                          autoComplete="off"
                          disabled={busy}
                          placeholder="0.00"
                          aria-label={`Purchase cost for medicine ${index + 1}`}
                          aria-invalid={Boolean(line.fieldErrors.purchasePrice)}
                        />
                        {line.fieldErrors.purchasePrice ? (
                          <span className="pharm-stock-entry__field-error">{line.fieldErrors.purchasePrice}</span>
                        ) : null}
                      </td>
                      <td className="pharm-stock-table__price">
                        <input
                          className="pharm-stock-table__readonly-input"
                          value={line.sellingPriceLabel || ""}
                          placeholder="—"
                          readOnly
                          tabIndex={-1}
                          aria-label={`Selling price for medicine ${index + 1} (from catalogue)`}
                        />
                      </td>
                      <td className="pharm-stock-table__action">
                        <RemoveRowButton
                          disabled={busy || receiveLines.length <= 1}
                          label={`Remove medicine ${index + 1}`}
                          onClick={() =>
                            setReceiveLines((current) => current.filter((row) => row.key !== line.key))
                          }
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="pharm-stock-table-wrap">
            <table className="pharm-stock-table pharm-stock-table--adjust">
              <thead>
                <tr>
                  <th className="pharm-stock-table__num">#</th>
                  <th className="pharm-stock-table__med">Medicine</th>
                  <th>Increase / Decrease</th>
                  <th className="pharm-stock-table__qty">Quantity</th>
                  <th>Reason</th>
                  <th>Resulting</th>
                  <th className="pharm-stock-table__action">Action</th>
                </tr>
              </thead>
              <tbody>
                {adjustLines.map((line, index) => {
                  const qty = Number(line.quantity);
                  const resulting =
                    Number.isFinite(qty) && qty > 0
                      ? resultingOnHand(line.onHand, line.direction, qty)
                      : line.onHand;
                  const invalid = Object.keys(line.fieldErrors).length > 0;
                  const isActive =
                    activeSearchKey === line.key || (!line.drugUuid && index === adjustLines.length - 1);
                  return (
                    <tr
                      key={line.key}
                      className={
                        [invalid ? "is-invalid" : "", isActive && !invalid ? "is-active" : ""]
                          .filter(Boolean)
                          .join(" ") || undefined
                      }
                    >
                      <td className="pharm-stock-table__num">
                        <span className="pharm-stock-table__index">{index + 1}</span>
                      </td>
                      <td className="pharm-stock-table__med">
                        {renderMedicineCell(line.key, line, line.fieldErrors.drug)}
                      </td>
                      <td>
                        <select
                          value={line.direction}
                          onChange={(event) =>
                            setAdjustLines((current) =>
                              current.map((row) =>
                                row.key === line.key
                                  ? {
                                      ...row,
                                      direction:
                                        event.target.value === "decrease" ? "decrease" : "increase",
                                      fieldErrors: {
                                        ...row.fieldErrors,
                                        direction: undefined,
                                        quantity: undefined,
                                      },
                                    }
                                  : row,
                              ),
                            )
                          }
                          disabled={busy}
                          aria-label={`Direction for medicine ${index + 1}`}
                        >
                          <option value="increase">Increase</option>
                          <option value="decrease">Decrease</option>
                        </select>
                      </td>
                      <td className="pharm-stock-table__qty">
                        <input
                          ref={(node) => {
                            qtyRefs.current[line.key] = node;
                          }}
                          value={line.quantity}
                          onChange={(event) =>
                            setAdjustLines((current) =>
                              current.map((row) =>
                                row.key === line.key
                                  ? {
                                      ...row,
                                      quantity: event.target.value,
                                      fieldErrors: { ...row.fieldErrors, quantity: undefined },
                                    }
                                  : row,
                              ),
                            )
                          }
                          inputMode="decimal"
                          autoComplete="off"
                          disabled={busy}
                          aria-label={`Quantity for medicine ${index + 1}`}
                          aria-invalid={Boolean(line.fieldErrors.quantity)}
                        />
                        {line.fieldErrors.quantity ? (
                          <span className="pharm-stock-entry__field-error">{line.fieldErrors.quantity}</span>
                        ) : null}
                      </td>
                      <td>
                        <select
                          value={line.reason}
                          onChange={(event) =>
                            setAdjustLines((current) =>
                              current.map((row) =>
                                row.key === line.key
                                  ? {
                                      ...row,
                                      reason: event.target.value,
                                      fieldErrors: { ...row.fieldErrors, reason: undefined },
                                    }
                                  : row,
                              ),
                            )
                          }
                          disabled={busy}
                          aria-label={`Reason for medicine ${index + 1}`}
                          aria-invalid={Boolean(line.fieldErrors.reason)}
                        >
                          <option value="">Choose a reason</option>
                          {reasons.map((reason) => (
                            <option key={reason} value={reason}>
                              {reason}
                            </option>
                          ))}
                        </select>
                        {line.fieldErrors.reason ? (
                          <span className="pharm-stock-entry__field-error">{line.fieldErrors.reason}</span>
                        ) : null}
                      </td>
                      <td className="pharm-stock-table__readonly">{formatStockQty(resulting)}</td>
                      <td className="pharm-stock-table__action">
                        <RemoveRowButton
                          disabled={busy || adjustLines.length <= 1}
                          label={`Remove medicine ${index + 1}`}
                          onClick={() =>
                            setAdjustLines((current) => current.filter((row) => row.key !== line.key))
                          }
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="pharm-stock-entry__footer">
        <div className="pharm-stock-entry__summary">
          <p>
            <strong>{`${lineCount} medicine${lineCount === 1 ? "" : "s"}`}</strong>
            <span className="pharm-stock-entry__summary-sep" aria-hidden="true">
              |
            </span>
            {totalQty > 0 ? `Total quantity: ${formatStockQty(totalQty)}` : "Total quantity: —"}
            {mode === "receive" && receiveCost > 0
              ? ` · Purchase total ₦${receiveCost.toLocaleString("en-NG")}`
              : ""}
          </p>
        </div>
        <div className="pharm-stock-entry__actions">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            className="pharm-stock-entry__save"
            busy={busy}
            busyLabel="Saving…"
            disabled={lineCount === 0}
            onClick={() => void (mode === "receive" ? submitReceive() : submitAdjust())}
          >
            <Save size={16} strokeWidth={2} aria-hidden="true" />
            {mode === "receive"
              ? lineCount > 1
                ? `Save ${lineCount} Medicines`
                : "Save Stock"
              : lineCount > 1
                ? `Save ${lineCount} Adjustments`
                : "Save Adjustment"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
