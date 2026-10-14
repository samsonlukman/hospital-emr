"""Laboratory consumables and Blood Bank unit inventory.

Bahmni/OpenELIS do not provide laboratory or blood-bag stock. Odoo pharmacy
stock is medicines-only. Hospital EMR keeps a hospital inventory ledger here so
Laboratory can manage consumables and Blood Bank can track blood units with
ABO/Rh, bag number, expiry, and status.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import laboratory as lab_billing
from hospital_admin import is_hospital_admin, is_technical_superadmin
from server import ApiError

STORE_LOCK = threading.Lock()

CONSUMABLE_KINDS = ("reagent", "kit", "tube", "consumable", "other")
BLOOD_COMPONENTS = (
    "Whole blood",
    "Packed red cells",
    "Fresh frozen plasma",
    "Platelets",
    "Cryoprecipitate",
    "Other",
)
ABO_GROUPS = ("A", "B", "AB", "O")
RH_TYPES = ("Positive", "Negative")
UNIT_STATUSES = ("available", "reserved", "issued", "expired", "discarded")

ADJUST_REASONS = (
    "Received stock",
    "Physical count",
    "Used in laboratory",
    "Damaged",
    "Expired",
    "Lost/missing",
    "Correction",
)

DEFAULT_CONSUMABLES = (
    ("EDTA tube", "tube", "tube", 0),
    ("Plain tube", "tube", "tube", 0),
    ("Fluoride tube", "tube", "tube", 0),
    ("Specimen container", "consumable", "piece", 0),
    ("Gloves (pair)", "consumable", "pair", 0),
    ("Alcohol swab", "consumable", "piece", 0),
    ("Lancet", "consumable", "piece", 0),
    ("Pipette tip", "consumable", "piece", 0),
    ("Rapid test kit", "kit", "kit", 0),
    ("Blood grouping reagents", "reagent", "set", 0),
    ("Cross-match reagents", "reagent", "set", 0),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_path() -> Path:
    override = os.environ.get("ABIKAN_LAB_INVENTORY_DB")
    if override:
        return Path(override)
    audit = os.environ.get("ABIKAN_ADMIN_AUDIT_DB")
    if audit:
        return Path(audit).resolve().parent / "laboratory_inventory.sqlite3"
    return Path(__file__).resolve().parent / "data" / "laboratory_inventory.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS lab_consumable (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          kind TEXT NOT NULL,
          unit TEXT NOT NULL,
          on_hand REAL NOT NULL DEFAULT 0,
          reorder_level REAL NOT NULL DEFAULT 0,
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lab_consumable_move (
          id TEXT PRIMARY KEY,
          consumable_id TEXT NOT NULL,
          delta REAL NOT NULL,
          resulting_on_hand REAL NOT NULL,
          reason TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',
          actor TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          FOREIGN KEY(consumable_id) REFERENCES lab_consumable(id)
        );
        CREATE TABLE IF NOT EXISTS blood_unit (
          id TEXT PRIMARY KEY,
          component TEXT NOT NULL,
          abo TEXT NOT NULL,
          rh TEXT NOT NULL,
          bag_number TEXT NOT NULL UNIQUE,
          volume_ml REAL,
          collected_on TEXT NOT NULL DEFAULT '',
          expires_on TEXT NOT NULL,
          status TEXT NOT NULL,
          patient_uuid TEXT NOT NULL DEFAULT '',
          patient_name TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT '',
          discard_reason TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          created_by TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS blood_unit_status_idx ON blood_unit(status);
        CREATE INDEX IF NOT EXISTS blood_unit_expires_idx ON blood_unit(expires_on);
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(lab_consumable)")}
    if "purchase_price" not in columns:
        connection.execute("ALTER TABLE lab_consumable ADD COLUMN purchase_price REAL")
    count = connection.execute("SELECT COUNT(*) AS n FROM lab_consumable").fetchone()["n"]
    if int(count or 0) == 0:
        now = _now()
        connection.executemany(
            """
            INSERT INTO lab_consumable
              (id, name, kind, unit, on_hand, reorder_level, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, '', ?, ?)
            """,
            [
                (str(uuid.uuid4()), name, kind, unit, float(reorder), now, now)
                for name, kind, unit, reorder in DEFAULT_CONSUMABLES
            ],
        )
    connection.commit()


def require_lab_inventory_user(cookie: str) -> dict[str, Any]:
    lab_billing.require_session(cookie)
    user = lab_billing.load_openmrs_user(cookie)
    if (
        lab_billing.is_lab_user(user)
        or is_hospital_admin(user)
        or is_technical_superadmin(user)
    ):
        return user
    raise ApiError(403, "forbidden", "Only Laboratory staff can manage laboratory inventory.")


def _actor_name(user: dict[str, Any]) -> str:
    return _text(user.get("username") or user.get("display") or "laboratory")


def _parse_qty(value: Any, *, allow_zero: bool = False) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_body", "Enter a quantity of zero or more.") from error
    if amount < 0 or (not allow_zero and amount == 0):
        raise ApiError(422, "invalid_body", "Enter a quantity greater than zero.")
    return round(amount, 4)


def _parse_purchase_price(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_body", "Enter the purchase price as a number.") from error
    if amount < 0:
        raise ApiError(422, "invalid_body", "Enter a purchase price of zero or more.")
    return amount


def _parse_optional_qty(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _parse_qty(value, allow_zero=True)


def _parse_date(value: Any, *, required: bool, label: str) -> str:
    text = _text(value)
    if not text:
        if required:
            raise ApiError(422, "invalid_body", f"Enter the {label}.")
        return ""
    try:
        date.fromisoformat(text[:10])
    except ValueError as error:
        raise ApiError(422, "invalid_body", f"Enter a valid {label} (YYYY-MM-DD).") from error
    return text[:10]


def _expire_due_units(connection: sqlite3.Connection) -> int:
    today = date.today().isoformat()
    cursor = connection.execute(
        """
        UPDATE blood_unit
        SET status = 'expired', updated_at = ?
        WHERE status IN ('available', 'reserved')
          AND expires_on <> ''
          AND expires_on < ?
        """,
        (_now(), today),
    )
    return int(cursor.rowcount or 0)


def _serialize_consumable(row: sqlite3.Row) -> dict[str, Any]:
    on_hand = float(row["on_hand"] or 0)
    reorder = float(row["reorder_level"] or 0)
    if on_hand <= 0:
        status = "Out of stock"
    elif reorder > 0 and on_hand <= reorder:
        status = "Low stock"
    else:
        status = "In stock"
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "kindLabel": row["kind"].replace("_", " ").title(),
        "unit": row["unit"],
        "onHand": on_hand,
        "reorderLevel": reorder,
        "purchasePrice": None if row["purchase_price"] is None else float(row["purchase_price"]),
        "status": status,
        "notes": row["notes"] or "",
        "updatedAt": row["updated_at"],
    }


def _serialize_unit(row: sqlite3.Row) -> dict[str, Any]:
    status = row["status"]
    return {
        "id": row["id"],
        "component": row["component"],
        "abo": row["abo"],
        "rh": row["rh"],
        "bloodGroupLabel": f"{row['abo']} {row['rh']}",
        "bagNumber": row["bag_number"],
        "volumeMl": row["volume_ml"],
        "collectedOn": row["collected_on"] or "",
        "expiresOn": row["expires_on"],
        "status": status,
        "statusLabel": str(status).replace("_", " ").title(),
        "patientUuid": row["patient_uuid"] or "",
        "patientName": row["patient_name"] or "",
        "source": row["source"] or "",
        "discardReason": row["discard_reason"] or "",
        "notes": row["notes"] or "",
        "createdBy": row["created_by"] or "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_consumables(cookie: str, query: str = "") -> dict[str, Any]:
    require_lab_inventory_user(cookie)
    needle = _text(query).lower()
    with STORE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            rows = connection.execute(
                "SELECT * FROM lab_consumable ORDER BY name COLLATE NOCASE"
            ).fetchall()
        finally:
            connection.close()
    items = [_serialize_consumable(row) for row in rows]
    if needle:
        items = [
            item
            for item in items
            if needle in item["name"].lower()
            or needle in item["kind"].lower()
            or needle in item["status"].lower()
        ]
    return {
        "items": items,
        "kinds": list(CONSUMABLE_KINDS),
        "adjustReasons": list(ADJUST_REASONS),
        "message": "Laboratory consumables are kept in Hospital EMR for this hospital.",
    }


def create_consumable(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_lab_inventory_user(cookie)
    name = _text(body.get("name"))
    kind = _text(body.get("kind")).lower() or "consumable"
    unit = _text(body.get("unit")) or "piece"
    if not name:
        raise ApiError(422, "invalid_body", "Enter a consumable name.")
    if kind not in CONSUMABLE_KINDS:
        raise ApiError(422, "invalid_body", "Choose a valid consumable type.")
    reorder = _parse_qty(body.get("reorderLevel") or 0, allow_zero=True)
    opening = _parse_qty(body.get("onHand") or 0, allow_zero=True)
    purchase_price = _parse_purchase_price(body.get("purchasePrice"))
    notes = _text(body.get("notes"))
    now = _now()
    item_id = str(uuid.uuid4())
    with STORE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            existing = connection.execute(
                "SELECT id FROM lab_consumable WHERE lower(name) = lower(?)",
                (name,),
            ).fetchone()
            if existing:
                raise ApiError(409, "duplicate_item", "A consumable with this name already exists.")
            connection.execute(
                """
                INSERT INTO lab_consumable
                  (id, name, kind, unit, on_hand, reorder_level, purchase_price, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, name, kind, unit, opening, reorder, purchase_price, notes, now, now),
            )
            if opening:
                connection.execute(
                    """
                    INSERT INTO lab_consumable_move
                      (id, consumable_id, delta, resulting_on_hand, reason, note, actor, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        item_id,
                        opening,
                        opening,
                        "Received stock",
                        "Opening stock",
                        _actor_name(user),
                        now,
                    ),
                )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lab_consumable WHERE id = ?",
                (item_id,),
            ).fetchone()
        finally:
            connection.close()
    return {"item": _serialize_consumable(row), "message": "Consumable added to laboratory inventory."}


def adjust_consumable(item_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_lab_inventory_user(cookie)
    needle = _text(item_id)
    reason = _text(body.get("reason"))
    note = _text(body.get("note"))
    if reason not in ADJUST_REASONS:
        raise ApiError(422, "invalid_body", "Choose a stock adjustment reason.")
    set_to = body.get("onHand")
    delta_raw = body.get("delta")
    with STORE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM lab_consumable WHERE id = ?",
                (needle,),
            ).fetchone()
            if not row:
                raise ApiError(404, "not_found", "That consumable was not found.")
            current = float(row["on_hand"] or 0)
            if set_to is not None and set_to != "":
                target = _parse_qty(set_to, allow_zero=True)
                delta = round(target - current, 4)
            else:
                delta = _parse_qty(delta_raw)
                if _text(body.get("direction")).lower() == "remove":
                    delta = -abs(delta)
                elif reason in {"Used in laboratory", "Damaged", "Expired", "Lost/missing"}:
                    delta = -abs(delta)
            resulting = round(current + delta, 4)
            if resulting < 0:
                raise ApiError(409, "insufficient_stock", "There is not enough stock for this change.")
            now = _now()
            purchase_price = _parse_purchase_price(body.get("purchasePrice"))
            if purchase_price is None:
                connection.execute(
                    "UPDATE lab_consumable SET on_hand = ?, updated_at = ? WHERE id = ?",
                    (resulting, now, needle),
                )
            else:
                connection.execute(
                    """
                    UPDATE lab_consumable
                    SET on_hand = ?, purchase_price = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (resulting, purchase_price, now, needle),
                )
            connection.execute(
                """
                INSERT INTO lab_consumable_move
                  (id, consumable_id, delta, resulting_on_hand, reason, note, actor, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    needle,
                    delta,
                    resulting,
                    reason,
                    note,
                    _actor_name(user),
                    now,
                ),
            )
            connection.commit()
            updated = connection.execute(
                "SELECT * FROM lab_consumable WHERE id = ?",
                (needle,),
            ).fetchone()
        finally:
            connection.close()
    return {"item": _serialize_consumable(updated), "message": "Stock updated."}


def list_blood_units(cookie: str, query: str = "", status: str = "") -> dict[str, Any]:
    require_lab_inventory_user(cookie)
    needle = _text(query).lower()
    status_filter = _text(status).lower()
    with STORE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            _expire_due_units(connection)
            connection.commit()
            rows = connection.execute(
                "SELECT * FROM blood_unit ORDER BY expires_on ASC, bag_number ASC"
            ).fetchall()
        finally:
            connection.close()
    units = [_serialize_unit(row) for row in rows]
    if status_filter and status_filter != "all":
        units = [unit for unit in units if unit["status"] == status_filter]
    if needle:
        units = [
            unit
            for unit in units
            if needle in unit["bagNumber"].lower()
            or needle in unit["component"].lower()
            or needle in unit["bloodGroupLabel"].lower()
            or needle in unit["patientName"].lower()
            or needle in unit["statusLabel"].lower()
        ]
    available = sum(1 for unit in units if unit["status"] == "available")
    reserved = sum(1 for unit in units if unit["status"] == "reserved")
    expiring = sum(
        1
        for unit in units
        if unit["status"] == "available"
        and unit["expiresOn"]
        and unit["expiresOn"] <= date.today().isoformat()
    )
    return {
        "units": units,
        "components": list(BLOOD_COMPONENTS),
        "aboGroups": list(ABO_GROUPS),
        "rhTypes": list(RH_TYPES),
        "statuses": list(UNIT_STATUSES),
        "counts": {
            "available": available,
            "reserved": reserved,
            "total": len(units),
            "expiringOrExpired": expiring,
        },
        "message": "Blood Bank unit stock is kept in Hospital EMR for this hospital.",
    }


def receive_blood_unit(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_lab_inventory_user(cookie)
    component = _text(body.get("component")) or "Whole blood"
    abo = _text(body.get("abo")).upper()
    rh = _text(body.get("rh")).title()
    bag_number = _text(body.get("bagNumber"))
    if component not in BLOOD_COMPONENTS:
        raise ApiError(422, "invalid_body", "Choose a blood component.")
    if abo not in ABO_GROUPS:
        raise ApiError(422, "invalid_body", "Choose the ABO group.")
    if rh not in RH_TYPES:
        raise ApiError(422, "invalid_body", "Choose Rh Positive or Rh Negative.")
    if not bag_number:
        raise ApiError(422, "invalid_body", "Enter the bag or unit number.")
    expires_on = _parse_date(body.get("expiresOn"), required=True, label="expiry date")
    collected_on = _parse_date(body.get("collectedOn"), required=False, label="collection date")
    volume = _parse_optional_qty(body.get("volumeMl"))
    source = _text(body.get("source"))
    notes = _text(body.get("notes"))
    now = _now()
    unit_id = str(uuid.uuid4())
    status = "available"
    if expires_on < date.today().isoformat():
        status = "expired"
    with STORE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            duplicate = connection.execute(
                "SELECT id FROM blood_unit WHERE lower(bag_number) = lower(?)",
                (bag_number,),
            ).fetchone()
            if duplicate:
                raise ApiError(
                    409,
                    "duplicate_bag",
                    "A blood unit with this bag number is already in the bank.",
                )
            connection.execute(
                """
                INSERT INTO blood_unit (
                  id, component, abo, rh, bag_number, volume_ml, collected_on, expires_on,
                  status, patient_uuid, patient_name, source, discard_reason, notes,
                  created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, '', ?, ?, ?, ?)
                """,
                (
                    unit_id,
                    component,
                    abo,
                    rh,
                    bag_number,
                    volume,
                    collected_on,
                    expires_on,
                    status,
                    source,
                    notes,
                    _actor_name(user),
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM blood_unit WHERE id = ?", (unit_id,)).fetchone()
        finally:
            connection.close()
    return {"unit": _serialize_unit(row), "message": "Blood unit added to the bank."}


def update_blood_unit_status(unit_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    require_lab_inventory_user(cookie)
    needle = _text(unit_id)
    status = _text(body.get("status")).lower()
    if status not in UNIT_STATUSES:
        raise ApiError(422, "invalid_body", "Choose a valid blood unit status.")
    patient_uuid = _text(body.get("patientUuid"))
    patient_name = _text(body.get("patientName"))
    discard_reason = _text(body.get("discardReason"))
    notes = _text(body.get("notes"))
    if status in {"reserved", "issued"} and not (patient_uuid or patient_name):
        raise ApiError(422, "invalid_body", "Name the patient when reserving or issuing a unit.")
    if status == "discarded" and not discard_reason:
        raise ApiError(422, "invalid_body", "Enter why the unit was discarded.")
    with STORE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            _expire_due_units(connection)
            row = connection.execute("SELECT * FROM blood_unit WHERE id = ?", (needle,)).fetchone()
            if not row:
                raise ApiError(404, "not_found", "That blood unit was not found.")
            current = row["status"]
            if current in {"issued", "discarded"} and status != current:
                raise ApiError(
                    409,
                    "unit_closed",
                    "Issued or discarded units cannot be changed. Receive a new unit if needed.",
                )
            if current == "expired" and status == "available":
                raise ApiError(409, "unit_expired", "Expired units cannot be made available again.")
            now = _now()
            connection.execute(
                """
                UPDATE blood_unit
                SET status = ?, patient_uuid = ?, patient_name = ?, discard_reason = ?,
                    notes = CASE WHEN ? <> '' THEN ? ELSE notes END, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    patient_uuid if status in {"reserved", "issued"} else "",
                    patient_name if status in {"reserved", "issued"} else "",
                    discard_reason if status == "discarded" else "",
                    notes,
                    notes,
                    now,
                    needle,
                ),
            )
            connection.commit()
            updated = connection.execute("SELECT * FROM blood_unit WHERE id = ?", (needle,)).fetchone()
        finally:
            connection.close()
    return {"unit": _serialize_unit(updated), "message": "Blood unit updated."}
