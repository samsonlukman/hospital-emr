"""Hospital laboratory catalogue.

Source of display metadata is the hospital CSV. Concept binding is the map JSON.
Prices shown to staff come from Odoo when mapped; otherwise the hospital CSV price.
React does not hardcode the test list.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
CSV_PATH = DATA_DIR / "laboratory_catalogue.csv"
MAP_PATH = DATA_DIR / "laboratory_catalogue_map.json"
RUNTIME_PATH = DATA_DIR / "laboratory_catalogue_runtime.json"


def _managed_path() -> Path:
    override = os.environ.get("ABIKAN_LAB_CATALOGUE_MANAGED")
    if override:
        return Path(override)
    try:
        from admin_audit import AUDIT_DB_PATH

        return Path(AUDIT_DB_PATH).resolve().parent / "laboratory_catalogue_managed.json"
    except Exception:
        return DATA_DIR / "laboratory_catalogue_managed.json"


MANAGED_PATH = _managed_path()

ALL_TESTS_AND_PANELS_UUID = "d3e6fb5f-5e07-11ef-8f7c-0242ac120002"


def parse_price(raw: str | None) -> tuple[float | None, bool]:
    """Return (amount, per_unit_or_each). None amount means not a single price."""
    text = (raw or "").strip().replace(",", "")
    each = "each" in text.lower() or "per unit" in text.lower()
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None, each
    return float(match.group(1)), each


def parse_availability(raw: str | None) -> dict[str, Any]:
    text = (raw or "").strip()
    lowered = text.lower()
    outsourced = "outsource" in lowered
    unavailable = lowered in {"no", "unavailable", "not available"}
    return {
        "raw": text,
        "orderable": not unavailable,
        "outsourced": outsourced,
        "notStat": "not stat" in lowered,
    }


def load_map() -> dict[str, Any]:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def load_runtime() -> dict[str, str]:
    if not RUNTIME_PATH.exists():
        return {}
    data = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in (data.get("conceptBySn") or {}).items()}


def load_managed_items() -> list[dict[str, Any]]:
    return list(load_managed_store().get("items") or [])


def save_managed_items(items: list[dict[str, Any]]) -> None:
    store = load_managed_store()
    store["items"] = items
    save_managed_store(store)


def append_managed_item(item: dict[str, Any]) -> dict[str, Any]:
    items = load_managed_items()
    concept = str(item.get("conceptUuid") or "").strip()
    if concept:
        for existing in items:
            if str(existing.get("conceptUuid") or "") == concept:
                existing.update(item)
                save_managed_items(items)
                return existing
    items.append(item)
    save_managed_items(items)
    return item


def load_managed_store() -> dict[str, Any]:
    path = _managed_path()
    if not path.exists():
        return {"items": [], "disabledConceptUuids": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"items": [row for row in (data or []) if isinstance(row, dict)], "disabledConceptUuids": []}
    items = [row for row in (data.get("items") or []) if isinstance(row, dict)]
    disabled = [
        str(value).strip()
        for value in (data.get("disabledConceptUuids") or [])
        if str(value or "").strip()
    ]
    return {"items": items, "disabledConceptUuids": disabled}


def save_managed_store(store: dict[str, Any]) -> None:
    path = _managed_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "items": [row for row in (store.get("items") or []) if isinstance(row, dict)],
        "disabledConceptUuids": sorted(
            {
                str(value).strip()
                for value in (store.get("disabledConceptUuids") or [])
                if str(value or "").strip()
            }
        ),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_disabled_concept_uuids() -> set[str]:
    return set(load_managed_store().get("disabledConceptUuids") or [])


def _managed_as_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    concept_uuid = str(item.get("conceptUuid") or "").strip()
    if not concept_uuid:
        return None
    if item.get("enabled") is False:
        return None
    klass = str(item.get("conceptClass") or "Test").strip() or "Test"
    hospital_name = str(item.get("hospitalName") or item.get("openmrsName") or "").strip()
    openmrs_name = str(item.get("openmrsName") or hospital_name).strip()
    if not hospital_name:
        return None
    type_label = str(item.get("type") or "").strip()
    if not type_label:
        type_label = "Panel" if klass.lower() == "labset" else "Test"
    sn = str(item.get("sn") or f"M-{concept_uuid[:8]}").strip()
    return {
        "sn": sn,
        "sourceSn": str(item.get("sourceSn") or ""),
        "action": "reuse",
        "note": str(item.get("note") or ""),
        "conceptUuid": concept_uuid,
        "openmrsName": openmrs_name,
        "createName": "",
        "conceptClass": klass,
        "memberSns": [],
        "department": str(item.get("department") or "Laboratory").strip() or "Laboratory",
        "hospitalName": hospital_name,
        "type": type_label,
        "priceRaw": "",
        "priceNgn": item.get("priceNgn"),
        "priceEach": False,
        "specimen": str(item.get("specimen") or "").strip(),
        "tat": str(item.get("tat") or "").strip(),
        "raw": "Yes",
        "orderable": True,
        "outsourced": bool(item.get("outsourced")),
        "notStat": bool(item.get("notStat")),
        "managed": True,
    }


def load_csv_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sn = str(row.get("S/N") or "").strip()
            if sn:
                rows[sn] = row
    return rows


def _csv_fields(row: dict[str, str] | None) -> dict[str, Any]:
    row = row or {}
    price_raw = row.get("Price (₦)") or row.get("Price (NGN)") or ""
    amount, each = parse_price(price_raw)
    availability = parse_availability(row.get("Available?"))
    return {
        "department": (row.get("Department") or "").strip(),
        "hospitalName": (row.get("Laboratory Test") or "").strip(),
        "type": (row.get("Type") or "").strip(),
        "priceRaw": price_raw.strip(),
        "priceNgn": amount,
        "priceEach": each,
        "specimen": (row.get("Specimen") or "").strip(),
        "tat": (row.get("TAT") or "").strip(),
        **availability,
    }


def catalogue_entries() -> list[dict[str, Any]]:
    mapping = load_map()
    csv_rows = load_csv_rows()
    runtime = load_runtime()
    store = load_managed_store()
    disabled = {str(value).strip() for value in (store.get("disabledConceptUuids") or []) if str(value or "").strip()}
    entries: list[dict[str, Any]] = []
    by_concept: dict[str, dict[str, Any]] = {}
    for item in mapping.get("items") or []:
        sn = str(item.get("sn") or "")
        source_sn = str(item.get("sourceSn") or sn.split("a")[0].split("b")[0].split("c")[0] if sn else "")
        if item.get("sourceSn"):
            source_sn = str(item["sourceSn"])
        else:
            source_sn = re.sub(r"[a-z]+$", "", sn)
        csv_row = csv_rows.get(source_sn) or csv_rows.get(sn)
        fields = _csv_fields(csv_row)
        if item.get("hospitalName"):
            fields["hospitalName"] = item["hospitalName"]
        if item.get("priceNgn") is not None:
            fields["priceNgn"] = float(item["priceNgn"])
            fields["priceEach"] = False
        concept_uuid = str(item.get("conceptUuid") or runtime.get(sn) or "").strip()
        action = item.get("action") or "skip"
        orderable = action != "skip" and fields["orderable"] and bool(concept_uuid or action == "create")
        if action == "skip":
            orderable = False
        if concept_uuid and concept_uuid in disabled:
            orderable = False
        entry = {
            "sn": sn,
            "sourceSn": source_sn,
            "action": action,
            "note": item.get("note") or "",
            "conceptUuid": concept_uuid,
            "openmrsName": item.get("openmrsName") or item.get("createName") or fields["hospitalName"],
            "createName": item.get("createName") or "",
            "conceptClass": item.get("conceptClass") or "Test",
            "memberSns": item.get("memberSns") or [],
            **fields,
            "orderable": bool(orderable and concept_uuid),
            "managed": False,
        }
        entries.append(entry)
        if concept_uuid:
            by_concept[concept_uuid] = entry

    # Staff-managed hospital enablement: select existing master concepts into the
    # hospital ordering subset. Does not invent new laboratory definitions.
    for item in store.get("items") or []:
        managed = _managed_as_entry(item)
        if not managed:
            continue
        concept_uuid = managed["conceptUuid"]
        if concept_uuid in disabled:
            continue
        existing = by_concept.get(concept_uuid)
        if existing and existing.get("orderable"):
            continue
        if existing:
            existing.update(
                {
                    "action": "reuse",
                    "orderable": True,
                    "hospitalName": managed["hospitalName"] or existing.get("hospitalName"),
                    "openmrsName": managed["openmrsName"] or existing.get("openmrsName"),
                    "conceptClass": managed["conceptClass"] or existing.get("conceptClass"),
                    "type": managed["type"] or existing.get("type"),
                    "specimen": managed["specimen"] or existing.get("specimen"),
                    "department": managed["department"] or existing.get("department"),
                    "managed": True,
                    "note": managed.get("note") or existing.get("note") or "",
                }
            )
            continue
        entries.append(managed)
        by_concept[concept_uuid] = managed
    return entries


def orderable_entries() -> list[dict[str, Any]]:
    return [row for row in catalogue_entries() if row.get("orderable")]


def entry_by_concept(concept_uuid: str) -> dict[str, Any] | None:
    needle = (concept_uuid or "").strip()
    if not needle:
        return None
    for row in catalogue_entries():
        if row.get("conceptUuid") == needle and row.get("orderable"):
            return row
    return None


def search_entries(query: str, *, include_unorderable: bool = False) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    rows = catalogue_entries() if include_unorderable else orderable_entries()
    if not needle:
        return rows
    found: list[dict[str, Any]] = []
    for row in rows:
        hay = " ".join(
            [
                row.get("hospitalName") or "",
                row.get("openmrsName") or "",
                row.get("department") or "",
                row.get("type") or "",
                row.get("specimen") or "",
                row.get("conceptUuid") or "",
            ]
        ).lower()
        if needle in hay:
            found.append(row)
    return found


# Catalogue seed may fill a missing/placeholder selling price. Staff-managed
# prices (Department Pricing) are never overwritten unless reset is explicit.
LAB_PLACEHOLDER_PRICE = 1.01


def should_write_lab_list_price(
    existing_list_price: float | None,
    *,
    reset_prices: bool = False,
) -> bool:
    if reset_prices or existing_list_price is None:
        return True
    try:
        return float(existing_list_price) <= LAB_PLACEHOLDER_PRICE
    except (TypeError, ValueError):
        return True


def lab_product_write_values(
    *,
    name: str,
    category_id: int,
    catalogue_price: float,
    existing_list_price: float | None = None,
    reset_prices: bool = False,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": name,
        "type": "service",
        "categ_id": category_id,
        "sale_ok": True,
        "purchase_ok": False,
        "invoice_policy": "order",
        "taxes_id": [(6, 0, [])],
        "supplier_taxes_id": [(6, 0, [])],
    }
    if should_write_lab_list_price(existing_list_price, reset_prices=reset_prices):
        values["list_price"] = float(catalogue_price)
    return values


def serialize_entry(row: dict[str, Any], *, live_price: float | None = None, currency: dict[str, Any] | None = None) -> dict[str, Any]:
    amount = live_price if live_price is not None else row.get("priceNgn")
    formatted = None
    if amount is not None:
        symbol = (currency or {}).get("symbol") or "₦"
        code = (currency or {}).get("code") or "NGN"
        formatted = {
            "amount": amount,
            "formatted": f"{symbol}{amount:,.0f}",
            "currencyCode": code,
            "currencySymbol": symbol,
        }
    return {
        "id": row["sn"],
        "sourceSn": row.get("sourceSn"),
        "name": row["hospitalName"] or row["openmrsName"],
        "openmrsName": row.get("openmrsName"),
        "department": row.get("department"),
        "type": row.get("type"),
        "specimen": row.get("specimen"),
        "tat": row.get("tat"),
        "outsourced": bool(row.get("outsourced")),
        "notStat": bool(row.get("notStat")),
        "orderable": bool(row.get("orderable")),
        "conceptUuid": row.get("conceptUuid") or None,
        "conceptClass": row.get("conceptClass"),
        "price": formatted,
        "availability": row.get("raw") or "",
        "note": row.get("note") or "",
    }
