import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { TableSkeleton } from "../../components/TableSkeleton";
import {
  adjustLaboratoryConsumable,
  createLaboratoryConsumable,
  fetchLaboratoryConsumables,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { LaboratoryConsumableItem } from "../../types/laboratoryCatalogue";

function purchaseLabel(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "Not entered";
  }
  return `₦${value.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function stockTone(status: string): "success" | "warning" | "danger" {
  if (status === "In stock") {
    return "success";
  }
  if (status === "Low stock") {
    return "warning";
  }
  return "danger";
}

export function LaboratoryInventoryView() {
  const [items, setItems] = useState<LaboratoryConsumableItem[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [reasons, setReasons] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("consumable");
  const [unit, setUnit] = useState("piece");
  const [opening, setOpening] = useState("0");
  const [reorder, setReorder] = useState("0");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [adjustId, setAdjustId] = useState("");
  const [adjustQty, setAdjustQty] = useState("");
  const [adjustPrice, setAdjustPrice] = useState("");
  const [adjustReason, setAdjustReason] = useState("Received stock");
  const [adjustNote, setAdjustNote] = useState("");

  const load = (search = query) => {
    setLoading(true);
    fetchLaboratoryConsumables(search)
      .then((payload) => {
        setItems(payload.items || []);
        setKinds(payload.kinds || []);
        setReasons(payload.adjustReasons || []);
        if (payload.adjustReasons?.length && !payload.adjustReasons.includes(adjustReason)) {
          setAdjustReason(payload.adjustReasons[0] || "Received stock");
        }
        setError("");
      })
      .catch((reason) => {
        setItems([]);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Laboratory inventory could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onAdd = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = await createLaboratoryConsumable({
        name,
        kind,
        unit,
        onHand: Number(opening || 0),
        reorderLevel: Number(reorder || 0),
        purchasePrice: purchasePrice.trim() === "" ? null : Number(purchasePrice),
      });
      setNotice(payload.message || "Consumable added.");
      setName("");
      setOpening("0");
      setReorder("0");
      setPurchasePrice("");
      load(query);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The consumable could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };

  const onAdjust = async () => {
    if (!adjustId) {
      setError("Choose a consumable to update.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = await adjustLaboratoryConsumable(adjustId, {
        reason: adjustReason,
        note: adjustNote,
        onHand: Number(adjustQty),
        purchasePrice: adjustPrice.trim() === "" ? null : Number(adjustPrice),
      });
      setNotice(payload.message || "Stock updated.");
      setAdjustQty("");
      setAdjustNote("");
      load(query);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "Stock could not be updated.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lab-desk lab-inventory">
      <PageHeader
        title="Laboratory Inventory"
        description="Consumables, reagents, tubes, and kits for laboratory work. Blood units are managed under Blood Bank."
      />

      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="success" title={notice} /> : null}

      <div className="lab-inventory__grid">
        <Card>
          <SectionHeader title="Add consumable" description="Create a new item for the laboratory store." />
          <div className="lab-inventory__form">
            <label className="lab-desk__search">
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} disabled={busy} />
            </label>
            <label className="lab-desk__search">
              Type
              <select value={kind} onChange={(event) => setKind(event.target.value)} disabled={busy}>
                {(kinds.length ? kinds : ["consumable"]).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              Unit
              <input value={unit} onChange={(event) => setUnit(event.target.value)} disabled={busy} />
            </label>
            <label className="lab-desk__search">
              Opening stock
              <input
                value={opening}
                onChange={(event) => setOpening(event.target.value)}
                inputMode="decimal"
                disabled={busy}
              />
            </label>
            <label className="lab-desk__search">
              Low-stock level
              <input
                value={reorder}
                onChange={(event) => setReorder(event.target.value)}
                inputMode="decimal"
                disabled={busy}
              />
            </label>
            <label className="lab-desk__search">
              Purchase price
              <input
                value={purchasePrice}
                onChange={(event) => setPurchasePrice(event.target.value)}
                inputMode="decimal"
                placeholder="Price paid per unit"
                disabled={busy}
              />
            </label>
            <Button disabled={busy || !name.trim()} onClick={() => void onAdd()}>
              {busy ? "Saving…" : "Add to inventory"}
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeader title="Update stock" description="Receive stock or set the quantity on the shelf." />
          <div className="lab-inventory__form">
            <label className="lab-desk__search">
              Consumable
              <select
                value={adjustId}
                onChange={(event) => {
                  const nextId = event.target.value;
                  setAdjustId(nextId);
                  const chosen = items.find((item) => item.id === nextId);
                  setAdjustPrice(chosen?.purchasePrice == null ? "" : String(chosen.purchasePrice));
                }}
                disabled={busy || items.length === 0}
              >
                <option value="">Choose item</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({item.onHand} {item.unit})
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              New quantity on hand
              <input
                value={adjustQty}
                onChange={(event) => setAdjustQty(event.target.value)}
                inputMode="decimal"
                disabled={busy}
              />
            </label>
            <label className="lab-desk__search">
              Purchase price
              <input
                value={adjustPrice}
                onChange={(event) => setAdjustPrice(event.target.value)}
                inputMode="decimal"
                placeholder="Price paid per unit"
                disabled={busy}
              />
            </label>
            <label className="lab-desk__search">
              Reason
              <select
                value={adjustReason}
                onChange={(event) => setAdjustReason(event.target.value)}
                disabled={busy}
              >
                {(reasons.length ? reasons : ["Received stock"]).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              Note
              <input value={adjustNote} onChange={(event) => setAdjustNote(event.target.value)} disabled={busy} />
            </label>
            <Button disabled={busy || !adjustId || adjustQty === ""} onClick={() => void onAdjust()}>
              {busy ? "Saving…" : "Save stock change"}
            </Button>
          </div>
        </Card>
      </div>

      <Card>
        <SectionHeader title="Store on hand" />
        <label className="lab-desk__search">
          Search inventory
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                load(query);
              }
            }}
            placeholder="Name or type"
          />
        </label>
        <div className="lab-inventory__search-actions">
          <Button variant="secondary" disabled={loading} onClick={() => load(query)}>
            Search
          </Button>
        </div>
        {loading ? (
          <TableSkeleton label="Loading inventory…" headers={["Item", "Type", "On hand", "Purchase price", "Status"]} />
        ) : null}
        {!loading && items.length === 0 ? (
          <EmptyState
            title="No consumables yet"
            description="Add tubes, kits, and reagents above so laboratory stock is visible to staff."
          />
        ) : null}
        {!loading && items.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Type</th>
                  <th>On hand</th>
                  <th>Purchase price</th>
                  <th>Low-stock level</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.name}</strong>
                    </td>
                    <td>{item.kindLabel}</td>
                    <td>
                      {item.onHand} {item.unit}
                    </td>
                    <td>{purchaseLabel(item.purchasePrice)}</td>
                    <td>
                      {item.reorderLevel} {item.unit}
                    </td>
                    <td>
                      <Badge tone={stockTone(item.status)}>{item.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
