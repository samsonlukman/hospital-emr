"""Hospital pharmacy catalogue mapping.

Source names come from the hospital medicines list. Binding is the map JSON.
Selling prices for development are temporary Odoo list prices, not hospital
approved prices. React does not hardcode the medicine list.
Spreadsheet quantities are recorded for reference only and must not be imported.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
CSV_PATH = DATA_DIR / "pharmacy_catalogue.csv"
MAP_PATH = DATA_DIR / "pharmacy_catalogue_map.json"
RUNTIME_PATH = DATA_DIR / "pharmacy_catalogue_runtime.json"

DEVELOPMENT_PRICE_NGN = 100.0
PRICE_LABEL = ""
TEST_DRUG_UUIDS = {
    "1c88be47-1ea9-4908-a57f-dc5ebd47caec",  # Paracetamol 500 mg — TEST
}


def load_map() -> dict[str, Any]:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def load_runtime() -> dict[str, str]:
    if not RUNTIME_PATH.exists():
        return {}
    data = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in (data.get("drugBySn") or {}).items()}


def load_csv_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sn = str(row.get("S/N") or "").strip()
            if sn:
                rows[sn] = row
    return rows


def catalogue_entries() -> list[dict[str, Any]]:
    mapping = load_map()
    csv_rows = load_csv_rows()
    runtime = load_runtime()
    entries: list[dict[str, Any]] = []
    for item in mapping.get("items") or []:
        sn = str(item.get("sn") or "")
        csv_row = csv_rows.get(sn) or {}
        action = item.get("action") or "skip"
        drug_uuid = item.get("drugUuid") or runtime.get(sn) or ""
        entries.append(
            {
                "sn": sn,
                "hospitalName": item.get("hospitalName") or csv_row.get("Medicine Name") or "",
                "hospitalCategory": item.get("hospitalCategory") or csv_row.get("Medicine Category") or "",
                "hospitalQtyRaw": csv_row.get("Available Qty") or "",
                "action": action,
                "note": item.get("note") or "",
                "skipReason": item.get("skipReason") or "",
                "drugUuid": drug_uuid,
                "openmrsName": item.get("openmrsName") or item.get("createName") or "",
                "createName": item.get("createName") or "",
                "conceptUuid": item.get("conceptUuid") or "",
                "strength": item.get("strength") or "",
                "dosageFormUuid": item.get("dosageFormUuid") or "",
                "dosageFormName": item.get("dosageFormName") or "",
                "developmentPriceNgn": DEVELOPMENT_PRICE_NGN if action in {"reuse", "create"} else None,
                "priceLabel": PRICE_LABEL if action in {"reuse", "create"} else "",
                "importStock": False,
            }
        )
    return entries


def mapped_entries() -> list[dict[str, Any]]:
    return [row for row in catalogue_entries() if row["action"] in {"reuse", "create"}]


def search_mapped_entries(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    rows = mapped_entries()
    if not needle:
        return rows
    found: list[dict[str, Any]] = []
    for row in rows:
        hay = " ".join(
            [
                str(row.get("hospitalName") or ""),
                str(row.get("openmrsName") or ""),
                str(row.get("createName") or ""),
                str(row.get("strength") or ""),
                str(row.get("dosageFormName") or ""),
            ]
        ).lower()
        if needle in hay:
            found.append(row)
    return found


def skipped_entries() -> list[dict[str, Any]]:
    return [row for row in catalogue_entries() if row["action"] == "skip"]


def summary() -> dict[str, int]:
    rows = catalogue_entries()
    return {
        "hospitalItems": len(rows),
        "mapped": sum(1 for row in rows if row["action"] in {"reuse", "create"}),
        "reused": sum(1 for row in rows if row["action"] == "reuse"),
        "created": sum(1 for row in rows if row["action"] == "create"),
        "unresolved": sum(1 for row in rows if row["action"] == "skip"),
    }
