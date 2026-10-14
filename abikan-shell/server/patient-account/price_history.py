"""Immutable catalogue price-change history.

Stores commercial price changes only. Does not store clinical identity,
invoices, or payments. Uses the existing Hospital EMR SQLite file so hospital
backups already cover it.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from admin_audit import AUDIT_DB_PATH, AUDIT_LOCK

CATALOGUE_DEPARTMENTS = ("reception", "laboratory", "pharmacy")
DEPARTMENTS = CATALOGUE_DEPARTMENTS
HISTORY_DEPARTMENTS = CATALOGUE_DEPARTMENTS + ("accommodation",)


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or os.environ.get("ABIKAN_ADMIN_AUDIT_DB") or AUDIT_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS price_change_event (
            event_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            department TEXT NOT NULL,
            item_id TEXT NOT NULL,
            item_label TEXT NOT NULL,
            currency TEXT NOT NULL,
            old_price REAL NOT NULL,
            new_price REAL NOT NULL,
            actor_uuid TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            actor_display TEXT NOT NULL,
            reason TEXT NOT NULL,
            details_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS price_change_event_item "
        "ON price_change_event (department, item_id, occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS price_change_event_occurred "
        "ON price_change_event (occurred_at DESC)"
    )
    return connection


def record_price_change(
    *,
    department: str,
    item_id: str,
    item_label: str,
    currency: str,
    old_price: float,
    new_price: float,
    actor: dict[str, Any],
    reason: str = "",
    details: Any = None,
    path: str | None = None,
) -> str | None:
    if department not in HISTORY_DEPARTMENTS:
        raise ValueError("unknown pricing department")
    if math.isclose(float(old_price), float(new_price), abs_tol=0.004):
        return None
    event_id = str(uuid.uuid4())
    row = (
        event_id,
        datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        department,
        str(item_id),
        str(item_label or item_id),
        str(currency or "NGN"),
        float(old_price),
        float(new_price),
        str(actor.get("uuid") or ""),
        str(actor.get("username") or ""),
        str(actor.get("display") or actor.get("username") or ""),
        str(reason or ""),
        json.dumps(details or {}, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
    )
    with AUDIT_LOCK:
        connection = _connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO price_change_event (
                        event_id, occurred_at, department, item_id, item_label,
                        currency, old_price, new_price, actor_uuid, actor_username,
                        actor_display, reason, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
        finally:
            connection.close()
    return event_id


def list_price_changes(
    *,
    department: str | None = None,
    item_id: str | None = None,
    limit: int = 20,
    path: str | None = None,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 100)
    clauses = ["1=1"]
    args: list[Any] = []
    if department:
        clauses.append("department = ?")
        args.append(department)
    if item_id:
        clauses.append("item_id = ?")
        args.append(item_id)
    args.append(safe_limit)
    with AUDIT_LOCK:
        connection = _connect(path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                f"""
                SELECT * FROM price_change_event
                WHERE {' AND '.join(clauses)}
                ORDER BY occurred_at DESC, event_id DESC
                LIMIT ?
                """,
                args,
            ).fetchall()
        finally:
            connection.close()
    return [_row(row) for row in rows]


def latest_change(
    department: str,
    item_id: str,
    *,
    path: str | None = None,
) -> dict[str, Any] | None:
    rows = list_price_changes(department=department, item_id=item_id, limit=1, path=path)
    return rows[0] if rows else None


def _row(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    try:
        payload["details"] = json.loads(row["details_json"] or "{}")
    except json.JSONDecodeError:
        payload["details"] = {}
    return payload
