"""Who waived a bill, and which accountant collected a payment."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = os.environ.get("ABIKAN_CASHIER_DB", "/var/lib/abikan/cashier.sqlite3")
LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS waived_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL UNIQUE,
            bill_number TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            hospital_number TEXT NOT NULL,
            patient_uuid TEXT NOT NULL,
            amount TEXT NOT NULL,
            amount_value REAL NOT NULL,
            waived_by TEXT NOT NULL,
            waived_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS collected_payments (
            payment_id INTEGER PRIMARY KEY,
            collected_by TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS created_bills (
            invoice_id INTEGER PRIMARY KEY,
            bill_number TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            hospital_number TEXT NOT NULL,
            patient_uuid TEXT NOT NULL,
            description TEXT NOT NULL,
            amount TEXT NOT NULL,
            amount_value REAL NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record_waiver(row: dict[str, Any]) -> dict[str, Any]:
    waived_at = _now()
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO waived_bills (
                    invoice_id, bill_number, patient_name, hospital_number, patient_uuid,
                    amount, amount_value, waived_by, waived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(invoice_id) DO UPDATE SET
                    waived_by=excluded.waived_by,
                    amount=excluded.amount,
                    amount_value=excluded.amount_value
                """,
                (
                    int(row["invoiceId"]),
                    str(row.get("billNumber") or ""),
                    str(row.get("patientName") or ""),
                    str(row.get("hospitalNumber") or ""),
                    str(row.get("patientUuid") or ""),
                    str(row.get("amount") or ""),
                    float(row.get("amountValue") or 0),
                    str(row.get("waivedBy") or ""),
                    waived_at,
                ),
            )
            connection.commit()
        finally:
            connection.close()
    return {**row, "waivedAt": waived_at}


def waivers_for(invoice_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not invoice_ids:
        return {}
    placeholders = ",".join("?" for _ in invoice_ids)
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                f"""
                SELECT invoice_id, bill_number, patient_name, hospital_number, patient_uuid,
                       amount, amount_value, waived_by, waived_at
                FROM waived_bills
                WHERE invoice_id IN ({placeholders})
                """,
                tuple(int(item) for item in invoice_ids),
            ).fetchall()
        finally:
            connection.close()
    return {
        int(row["invoice_id"]): {
            "invoiceId": int(row["invoice_id"]),
            "billNumber": row["bill_number"],
            "patientName": row["patient_name"],
            "hospitalNumber": row["hospital_number"],
            "patientUuid": row["patient_uuid"],
            "amount": row["amount"],
            "amountValue": float(row["amount_value"] or 0),
            "waivedBy": row["waived_by"],
            "waivedAt": row["waived_at"],
        }
        for row in rows
    }


def list_stored_waivers() -> list[dict[str, Any]]:
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                """
                SELECT invoice_id, bill_number, patient_name, hospital_number, patient_uuid,
                       amount, amount_value, waived_by, waived_at
                FROM waived_bills
                ORDER BY waived_at DESC, id DESC
                """
            ).fetchall()
        finally:
            connection.close()
    return [
        {
            "invoiceId": int(row["invoice_id"]),
            "billNumber": row["bill_number"],
            "patientName": row["patient_name"],
            "hospitalNumber": row["hospital_number"],
            "patientUuid": row["patient_uuid"] or None,
            "amount": row["amount"],
            "amountValue": float(row["amount_value"] or 0),
            "waivedBy": row["waived_by"],
            "waivedAt": row["waived_at"],
        }
        for row in rows
    ]


def record_collector(payment_id: int, username: str) -> None:
    name = str(username or "").strip()
    if not payment_id or not name:
        return
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO collected_payments (payment_id, collected_by, collected_at)
                VALUES (?, ?, ?)
                ON CONFLICT(payment_id) DO UPDATE SET collected_by=excluded.collected_by
                """,
                (int(payment_id), name, _now()),
            )
            connection.commit()
        finally:
            connection.close()


def collection_facts(payment_ids: list[int]) -> dict[int, dict[str, str]]:
    if not payment_ids:
        return {}
    placeholders = ",".join("?" for _ in payment_ids)
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                f"""
                SELECT payment_id, collected_by, collected_at
                FROM collected_payments
                WHERE payment_id IN ({placeholders})
                """,
                tuple(int(item) for item in payment_ids),
            ).fetchall()
        finally:
            connection.close()
    return {
        int(row["payment_id"]): {
            "collectedBy": str(row["collected_by"] or ""),
            "collectedAt": str(row["collected_at"] or ""),
        }
        for row in rows
    }


def collectors_for(payment_ids: list[int]) -> dict[int, str]:
    return {
        payment_id: facts["collectedBy"]
        for payment_id, facts in collection_facts(payment_ids).items()
    }


def record_created_bill(row: dict[str, Any]) -> None:
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO created_bills (
                    invoice_id, bill_number, patient_name, hospital_number, patient_uuid,
                    description, amount, amount_value, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(invoice_id) DO UPDATE SET
                    description=excluded.description,
                    created_by=excluded.created_by
                """,
                (
                    int(row["invoiceId"]),
                    str(row.get("billNumber") or ""),
                    str(row.get("patientName") or ""),
                    str(row.get("hospitalNumber") or ""),
                    str(row.get("patientUuid") or ""),
                    str(row.get("description") or ""),
                    str(row.get("amount") or ""),
                    float(row.get("amountValue") or 0),
                    str(row.get("createdBy") or ""),
                    _now(),
                ),
            )
            connection.commit()
        finally:
            connection.close()


def creators_for(invoice_ids: list[int]) -> dict[int, dict[str, str]]:
    if not invoice_ids:
        return {}
    placeholders = ",".join("?" for _ in invoice_ids)
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                f"""
                SELECT invoice_id, description, created_by
                FROM created_bills
                WHERE invoice_id IN ({placeholders})
                """,
                tuple(int(item) for item in invoice_ids),
            ).fetchall()
        finally:
            connection.close()
    return {
        int(row["invoice_id"]): {
            "description": str(row["description"] or ""),
            "createdBy": str(row["created_by"] or ""),
        }
        for row in rows
    }
