"""Prescriptions that Pharmacy must see but must not dispense or bill.

Doctors may type a medicine name that is not in the hospital Pharmacy list.
Those orders stay on the chart and on the inpatient sheet. They must not create
a patient bill. Pharmacy still sees them, marked as not for dispensing.

Persisted on the Hospital EMR volume so the Pharmacy list can find typed-only
prescriptions that never receive a sellable line.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

NOT_IN_PHARMACY_STATUS = "NOT IN PHARMACY"
NOT_BILLED_STATUS = "NOT BILLED"
NOT_IN_PHARMACY_REASON = "Not in Pharmacy — do not dispense."

DB_PATH = os.environ.get(
    "ABIKAN_PHARMACY_UNLISTED_DB",
    os.environ.get("ABIKAN_NOTIFICATIONS_DB", "/var/lib/abikan/notifications.sqlite3"),
)
LOCK = threading.Lock()

CREATE_STATEMENT = """
    CREATE TABLE IF NOT EXISTS pharmacy_unlisted_order (
        order_uuid TEXT PRIMARY KEY,
        patient_uuid TEXT NOT NULL,
        encounter_uuid TEXT NOT NULL DEFAULT '',
        drug_name TEXT NOT NULL DEFAULT '',
        ordered_at TEXT NOT NULL DEFAULT '',
        stopped INTEGER NOT NULL DEFAULT 0
    )
"""


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(CREATE_STATEMENT)
    return connection


def reset_for_tests(path: str) -> None:
    global DB_PATH
    DB_PATH = path
    with LOCK:
        connection = _connect(path)
        try:
            connection.execute("DROP TABLE IF EXISTS pharmacy_unlisted_order")
            connection.execute(CREATE_STATEMENT)
            connection.commit()
        finally:
            connection.close()


def _text(value: Any) -> str:
    return str(value or "").strip()


def hospital_catalogue_drug_uuids(odoo: Any | None = None) -> set[str]:
    import pharmacy_catalogue

    ids = {
        _text(row.get("drugUuid"))
        for row in pharmacy_catalogue.search_mapped_entries("")
        if _text(row.get("drugUuid"))
    }
    ids.update(pharmacy_catalogue.TEST_DRUG_UUIDS)
    if odoo is None:
        return ids
    try:
        import pharmacy_manage

        for row in pharmacy_manage.extra_catalogue_rows(odoo):
            uuid = _text(row.get("drugUuid"))
            if uuid:
                ids.add(uuid)
    except Exception:
        pass
    return ids


def not_in_pharmacy_order(
    clinical: dict[str, Any],
    catalogue_ids: set[str] | None = None,
) -> bool:
    """Only typed medicine names skip Pharmacy stock, price, and the bill.

    Coded hospital medicines stay on the Pharmacy queue even when the
    catalogue lookup is incomplete. An empty or partial catalogue list must
    never mark every coded prescription as not for dispensing.
    """
    del catalogue_ids
    return bool(_text(clinical.get("drugNonCoded")))


def remember(clinical: dict[str, Any]) -> None:
    order_uuid = _text(clinical.get("uuid"))
    patient_uuid = _text(clinical.get("patientUuid"))
    if not order_uuid or not patient_uuid:
        return
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO pharmacy_unlisted_order (
                    order_uuid, patient_uuid, encounter_uuid, drug_name, ordered_at, stopped
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_uuid) DO UPDATE SET
                    patient_uuid=excluded.patient_uuid,
                    encounter_uuid=excluded.encounter_uuid,
                    drug_name=excluded.drug_name,
                    ordered_at=excluded.ordered_at,
                    stopped=excluded.stopped
                """,
                (
                    order_uuid,
                    patient_uuid,
                    _text(clinical.get("encounterUuid")),
                    _text(clinical.get("drugName")),
                    _text(clinical.get("ordered")),
                    1 if clinical.get("stopped") else 0,
                ),
            )
            connection.commit()
        finally:
            connection.close()


def forget(order_uuid: str) -> None:
    uuid = _text(order_uuid)
    if not uuid:
        return
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                "DELETE FROM pharmacy_unlisted_order WHERE order_uuid = ?",
                (uuid,),
            )
            connection.commit()
        finally:
            connection.close()


def list_rows(
    *,
    patient_uuid: str | None = None,
    encounter_uuid: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["stopped = 0"]
    values: list[str] = []
    if _text(patient_uuid):
        clauses.append("patient_uuid = ?")
        values.append(_text(patient_uuid))
    if _text(encounter_uuid):
        clauses.append("encounter_uuid = ?")
        values.append(_text(encounter_uuid))
    sql = (
        "SELECT order_uuid, patient_uuid, encounter_uuid, drug_name, ordered_at "
        "FROM pharmacy_unlisted_order WHERE "
        + " AND ".join(clauses)
        + " ORDER BY ordered_at DESC"
    )
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(sql, values).fetchall()
        finally:
            connection.close()
    return [
        {
            "orderUuid": str(row["order_uuid"]),
            "patientUuid": str(row["patient_uuid"]),
            "encounterUuid": str(row["encounter_uuid"] or ""),
            "drugName": str(row["drug_name"] or ""),
            "ordered": str(row["ordered_at"] or ""),
        }
        for row in rows
    ]
