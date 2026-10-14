"""Durable export history and private temporary files.

Stores metadata only. The exported rows themselves are written to a private
directory and removed after they expire. Patient and financial contents are
never stored in the audit database.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from admin_audit import AUDIT_DB_PATH, AUDIT_LOCK

EXPORT_LOCK = threading.Lock()
EXPORT_FILES_ROOT = os.environ.get("ABIKAN_EXPORT_FILES_ROOT", "/var/lib/abikan/exports")
EXPORT_TTL_HOURS = int(os.environ.get("ABIKAN_EXPORT_TTL_HOURS", "24"))
FILE_STATUSES = {"available", "expired", "deleted", "missing", "none"}
OUTCOMES = {"success", "failed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or os.environ.get("ABIKAN_ADMIN_AUDIT_DB") or AUDIT_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_export_event (
            export_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            actor_uuid TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            actor_display TEXT NOT NULL,
            dataset TEXT NOT NULL,
            dataset_label TEXT NOT NULL,
            format TEXT NOT NULL,
            department TEXT NOT NULL,
            department_label TEXT NOT NULL,
            status_filter TEXT NOT NULL,
            period TEXT NOT NULL,
            period_label TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            file_size INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failed')),
            error_code TEXT NOT NULL,
            file_status TEXT NOT NULL CHECK (
                file_status IN ('available', 'expired', 'deleted', 'missing', 'none')
            ),
            expires_at TEXT NOT NULL,
            audit_event_id TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS admin_export_event_created "
        "ON admin_export_event (created_at DESC)"
    )
    return connection


def files_root(root: str | None = None) -> Path:
    path = Path(root or os.environ.get("ABIKAN_EXPORT_FILES_ROOT") or EXPORT_FILES_ROOT)
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path(export_id: str, *, root: str | None = None) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "" for ch in export_id)
    if not safe or safe != export_id:
        raise ValueError("invalid_export_id")
    return files_root(root) / safe


def write_file(export_id: str, data: bytes, *, root: str | None = None) -> int:
    path = file_path(export_id, root=root)
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return path.stat().st_size


def read_file(export_id: str, *, root: str | None = None) -> bytes:
    path = file_path(export_id, root=root)
    if not path.is_file():
        raise FileNotFoundError(export_id)
    return path.read_bytes()


def remove_file(export_id: str, *, root: str | None = None) -> None:
    path = file_path(export_id, root=root)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def insert_export(
    *,
    actor: dict[str, Any],
    dataset: str,
    dataset_label: str,
    fmt: str,
    department: str,
    department_label: str,
    status_filter: str,
    period: str,
    period_label: str,
    start_date: str,
    end_date: str,
    record_count: int,
    file_size: int,
    filename: str,
    content_type: str,
    outcome: str,
    error_code: str = "",
    file_status: str,
    expires_at: str,
    audit_event_id: str = "",
    path: str | None = None,
    export_id: str | None = None,
) -> str:
    if outcome not in OUTCOMES:
        raise ValueError("outcome must be success or failed")
    if file_status not in FILE_STATUSES:
        raise ValueError("invalid file status")
    chosen_id = export_id or str(uuid.uuid4())
    row = (
        chosen_id,
        _iso(_now()),
        str(actor.get("uuid") or ""),
        str(actor.get("username") or ""),
        str(actor.get("displayName") or actor.get("username") or "Administrator"),
        dataset,
        dataset_label,
        fmt,
        department,
        department_label,
        status_filter,
        period,
        period_label,
        start_date,
        end_date,
        int(record_count),
        int(file_size),
        filename,
        content_type,
        outcome,
        error_code,
        file_status,
        expires_at,
        audit_event_id,
    )
    with AUDIT_LOCK:
        connection = _connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO admin_export_event (
                        export_id, created_at, actor_uuid, actor_username, actor_display,
                        dataset, dataset_label, format, department, department_label,
                        status_filter, period, period_label, start_date, end_date,
                        record_count, file_size, filename, content_type, outcome,
                        error_code, file_status, expires_at, audit_event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
        finally:
            connection.close()
    return chosen_id


def update_file_status(
    export_id: str,
    file_status: str,
    *,
    path: str | None = None,
) -> None:
    if file_status not in FILE_STATUSES:
        raise ValueError("invalid file status")
    with AUDIT_LOCK:
        connection = _connect(path)
        try:
            with connection:
                connection.execute(
                    "UPDATE admin_export_event SET file_status = ? WHERE export_id = ?",
                    (file_status, export_id),
                )
        finally:
            connection.close()


def get_export(export_id: str, *, path: str | None = None) -> dict[str, Any] | None:
    with AUDIT_LOCK:
        connection = _connect(path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT * FROM admin_export_event WHERE export_id = ?",
                (export_id,),
            ).fetchone()
        finally:
            connection.close()
    return dict(row) if row else None


def list_exports(
    *,
    path: str | None = None,
    query: str = "",
    dataset: str = "",
    outcome: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = min(max(int(limit), 1), 200)
    safe_offset = max(int(offset), 0)
    clauses = ["1=1"]
    params: list[Any] = []
    term = query.strip()
    if term:
        like = f"%{term}%"
        clauses.append(
            "(dataset_label LIKE ? OR actor_username LIKE ? OR actor_display LIKE ? OR format LIKE ?)"
        )
        params.extend([like, like, like, like])
    if dataset:
        clauses.append("dataset = ?")
        params.append(dataset)
    if outcome in OUTCOMES:
        clauses.append("outcome = ?")
        params.append(outcome)
    where = " AND ".join(clauses)
    with AUDIT_LOCK:
        connection = _connect(path)
        connection.row_factory = sqlite3.Row
        try:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM admin_export_event WHERE {where}",
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT * FROM admin_export_event
                WHERE {where}
                ORDER BY created_at DESC, export_id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, safe_limit, safe_offset],
            ).fetchall()
        finally:
            connection.close()
    return {
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "exports": [dict(row) for row in rows],
    }


def expire_due_files(*, path: str | None = None, root: str | None = None, now: datetime | None = None) -> int:
    moment = now or _now()
    with AUDIT_LOCK:
        connection = _connect(path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT export_id, expires_at FROM admin_export_event WHERE file_status = 'available'"
            ).fetchall()
        finally:
            connection.close()
    removed = 0
    for row in rows:
        expires = _parse_iso(str(row["expires_at"] or ""))
        if expires is None or expires > moment:
            continue
        remove_file(str(row["export_id"]), root=root)
        update_file_status(str(row["export_id"]), "expired", path=path)
        removed += 1
    return removed


def default_expiry(*, now: datetime | None = None, hours: int | None = None) -> str:
    ttl = hours if hours is not None else EXPORT_TTL_HOURS
    return _iso((now or _now()) + timedelta(hours=max(1, int(ttl))))
