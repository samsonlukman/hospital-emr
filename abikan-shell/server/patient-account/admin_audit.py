"""Durable, scoped audit history for Hospital Administration mutations."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_DB_PATH = os.environ.get(
    "ABIKAN_ADMIN_AUDIT_DB",
    "/var/lib/abikan/admin-audit.sqlite3",
)
AUDIT_LOCK = threading.Lock()
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "initialpassword",
    "password",
    "secret",
    "session",
    "token",
    "nin",
    "bankaccount",
    "bankaccountnumber",
    "bankname",
    "accountname",
    "nameonaccount",
    "base64encodedimage",
    "content",
    "file",
    "sample",
    "template",
    "templatekey",
    "fingerprint",
    "fingerprintimage",
    "capture",
    "staffcode",
    "attendancecode",
    "photo",
}


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_safe_value(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or AUDIT_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_audit_event (
            event_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            actor_uuid TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            target_user_uuid TEXT NOT NULL,
            target_username TEXT NOT NULL,
            action TEXT NOT NULL,
            previous_state_json TEXT NOT NULL,
            new_state_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('pending', 'success', 'failure')),
            error_code TEXT NOT NULL,
            request_id TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS admin_audit_event_occurred_at "
        "ON admin_audit_event (occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS admin_audit_event_target "
        "ON admin_audit_event (target_username, occurred_at DESC)"
    )
    return connection


def record_admin_event(
    *,
    actor: dict[str, Any],
    target_user_uuid: str = "",
    target_username: str = "",
    action: str,
    previous_state: Any = None,
    new_state: Any = None,
    details: Any = None,
    outcome: str,
    error_code: str = "",
    request_id: str = "",
    path: str | None = None,
) -> str:
    if outcome not in {"pending", "success", "failure"}:
        raise ValueError("outcome must be pending, success or failure")
    event_id = str(uuid.uuid4())
    row = (
        event_id,
        datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        str(actor.get("uuid") or ""),
        str(actor.get("username") or ""),
        str(target_user_uuid or ""),
        str(target_username or ""),
        str(action or ""),
        _json(previous_state),
        _json(new_state),
        _json(details),
        outcome,
        str(error_code or ""),
        str(request_id or ""),
    )
    with AUDIT_LOCK:
        connection = _connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO admin_audit_event (
                        event_id, occurred_at, actor_uuid, actor_username,
                        target_user_uuid, target_username, action,
                        previous_state_json, new_state_json, details_json,
                        outcome, error_code, request_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
        finally:
            connection.close()
    return event_id


def start_admin_event(**kwargs: Any) -> str:
    return record_admin_event(outcome="pending", **kwargs)


def finish_admin_event(
    event_id: str,
    *,
    outcome: str,
    new_state: Any = None,
    details: Any = None,
    error_code: str = "",
    path: str | None = None,
) -> None:
    if outcome not in {"success", "failure"}:
        raise ValueError("outcome must be success or failure")
    with AUDIT_LOCK:
        connection = _connect(path)
        try:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE admin_audit_event
                    SET outcome = ?, new_state_json = ?, details_json = ?, error_code = ?
                    WHERE event_id = ? AND outcome = 'pending'
                    """,
                    (
                        outcome,
                        _json(new_state),
                        _json(details),
                        str(error_code or ""),
                        event_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("pending administrative audit event was not found")
        finally:
            connection.close()


def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        **dict(row),
        "previous_state": _safe_value(json.loads(row["previous_state_json"])),
        "new_state": _safe_value(json.loads(row["new_state_json"])),
        "details": _safe_value(json.loads(row["details_json"])),
    }


def read_admin_events(*, path: str | None = None) -> list[dict[str, Any]]:
    """Support/test helper. HTTP reads go through list_admin_events."""
    with AUDIT_LOCK:
        connection = _connect(path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM admin_audit_event ORDER BY occurred_at, event_id"
            ).fetchall()
        finally:
            connection.close()
    return [_row_payload(row) for row in rows]


def list_admin_events(
    *,
    path: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = min(max(int(limit), 1), 200)
    safe_offset = max(int(offset), 0)
    with AUDIT_LOCK:
        connection = _connect(path)
        connection.row_factory = sqlite3.Row
        try:
            total = int(
                connection.execute("SELECT COUNT(*) FROM admin_audit_event").fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT * FROM admin_audit_event
                ORDER BY occurred_at DESC, event_id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
        finally:
            connection.close()
    return {
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "events": [_row_payload(row) for row in rows],
    }
