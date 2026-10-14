"""Record of bills an accountant deleted, including why and who."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = os.environ.get("ABIKAN_DELETED_BILLS_DB", "/var/lib/abikan/deleted-bills.sqlite3")
LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL UNIQUE,
            bill_number TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            hospital_number TEXT NOT NULL,
            patient_uuid TEXT NOT NULL,
            department TEXT NOT NULL,
            amount TEXT NOT NULL,
            reason TEXT NOT NULL,
            deleted_by TEXT NOT NULL,
            deleted_at TEXT NOT NULL
        )
        """
    )
    return connection


def record_deletion(row: dict[str, Any]) -> dict[str, Any]:
    deleted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO deleted_bills (
                    invoice_id, bill_number, patient_name, hospital_number, patient_uuid,
                    department, amount, reason, deleted_by, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["invoiceId"]),
                    str(row.get("billNumber") or ""),
                    str(row.get("patientName") or ""),
                    str(row.get("hospitalNumber") or ""),
                    str(row.get("patientUuid") or ""),
                    str(row.get("department") or ""),
                    str(row.get("amount") or ""),
                    str(row.get("reason") or ""),
                    str(row.get("deletedBy") or ""),
                    deleted_at,
                ),
            )
            connection.commit()
            saved_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        finally:
            connection.close()
    return {**row, "id": saved_id, "deletedAt": deleted_at}


def list_deletions(query: str = "", offset: int = 0, limit: int = 25) -> dict[str, Any]:
    needle = f"%{query.strip().lower()}%"
    with LOCK:
        connection = _connect()
        try:
            if query.strip():
                where = """
                    WHERE lower(bill_number) LIKE ?
                       OR lower(patient_name) LIKE ?
                       OR lower(hospital_number) LIKE ?
                       OR lower(reason) LIKE ?
                       OR lower(deleted_by) LIKE ?
                """
                params: tuple[Any, ...] = (needle, needle, needle, needle, needle)
            else:
                where = ""
                params = ()
            total = int(
                connection.execute(f"SELECT COUNT(*) FROM deleted_bills {where}", params).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT id, invoice_id, bill_number, patient_name, hospital_number, patient_uuid,
                       department, amount, reason, deleted_by, deleted_at
                FROM deleted_bills
                {where}
                ORDER BY deleted_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        finally:
            connection.close()
    return {
        "status": "ok",
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": int(row["id"]),
                "invoiceId": int(row["invoice_id"]),
                "billNumber": row["bill_number"],
                "patientName": row["patient_name"],
                "hospitalNumber": row["hospital_number"],
                "patientUuid": row["patient_uuid"] or None,
                "department": row["department"],
                "amount": row["amount"],
                "reason": row["reason"],
                "deletedBy": row["deleted_by"],
                "deletedAt": row["deleted_at"],
            }
            for row in rows
        ],
    }
