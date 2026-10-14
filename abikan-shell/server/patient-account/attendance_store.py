"""SQLite persistence for staff attendance sessions and staff codes.

Lives on the Hospital EMR persistent volume next to administration audit files.
OpenMRS remains the staff identity source. This store only maps a staff code to
an existing person and records one attendance session per hospital local day.

Older biometric tables, if present, are left untouched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ATTENDANCE_DB_PATH = os.environ.get(
    "ABIKAN_ATTENDANCE_DB",
    "/var/lib/abikan/attendance.sqlite3",
)
LOCK = threading.Lock()
STATUS_SIGNED_IN = "SIGNED_IN"
STATUS_SIGNED_OUT = "SIGNED_OUT"
SESSION_STATUSES = (STATUS_SIGNED_IN, STATUS_SIGNED_OUT)
THROTTLE_WINDOW_SECONDS = 10 * 60
THROTTLE_BLOCK_SECONDS = 5 * 60
THROTTLE_MAX_FAILURES = 8
PHOTO_REL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}/[A-Za-z0-9._-]+\.(jpg|jpeg|png|webp)$")
DATE_FOLDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SIGN_IN_PHOTO_BYTES = 350 * 1024
PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS attendance_session (
        id TEXT PRIMARY KEY,
        person_uuid TEXT NOT NULL,
        user_uuid TEXT NOT NULL,
        username TEXT NOT NULL,
        display_name TEXT NOT NULL,
        workplace_id TEXT NOT NULL,
        workplace_label TEXT NOT NULL,
        local_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('SIGNED_IN', 'SIGNED_OUT')),
        sign_in_at TEXT NOT NULL,
        sign_in_local_time TEXT NOT NULL,
        sign_out_at TEXT NOT NULL DEFAULT '',
        sign_out_local_time TEXT NOT NULL DEFAULT '',
        authentication_method TEXT NOT NULL,
        terminal_id TEXT NOT NULL,
        terminal_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        signed_out_by TEXT NOT NULL DEFAULT '',
        sign_in_photo TEXT NOT NULL DEFAULT '',
        UNIQUE (person_uuid, local_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS staff_attendance_code (
        id TEXT PRIMARY KEY,
        person_uuid TEXT NOT NULL UNIQUE,
        code_normalized TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        replaced_at TEXT NOT NULL DEFAULT '',
        replaced_by TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attendance_code_audit (
        id TEXT PRIMARY KEY,
        occurred_at TEXT NOT NULL,
        action TEXT NOT NULL,
        person_uuid TEXT NOT NULL,
        actor_uuid TEXT NOT NULL,
        actor_username TEXT NOT NULL,
        details_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attendance_attempt (
        throttle_key TEXT PRIMARY KEY,
        failed_count INTEGER NOT NULL,
        window_start TEXT NOT NULL,
        blocked_until TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS attendance_session_day ON attendance_session (local_date, sign_in_at)",
    "CREATE INDEX IF NOT EXISTS attendance_session_workplace_day ON attendance_session (workplace_id, local_date, sign_in_at)",
    "CREATE INDEX IF NOT EXISTS attendance_session_status_day ON attendance_session (status, local_date)",
    "CREATE INDEX IF NOT EXISTS attendance_code_audit_person ON attendance_code_audit (person_uuid, occurred_at DESC)",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(moment: datetime | None = None) -> str:
    value = moment or utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True, separators=(",", ":"))


def _load_json(raw: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(raw or "")
    except json.JSONDecodeError:
        return fallback
    return parsed


def connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or ATTENDANCE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    for statement in CREATE_STATEMENTS:
        connection.execute(statement)
    _ensure_columns(connection)
    return connection


def _ensure_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(attendance_session)").fetchall()
    }
    if "sign_in_photo" not in columns:
        connection.execute(
            "ALTER TABLE attendance_session ADD COLUMN sign_in_photo TEXT NOT NULL DEFAULT ''"
        )


def photos_root(path: str | None = None) -> Path:
    configured = str(os.environ.get("ABIKAN_ATTENDANCE_PHOTOS") or "").strip()
    if configured:
        root = Path(configured)
    else:
        root = Path(path or ATTENDANCE_DB_PATH).parent / "attendance-photos"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_id() -> str:
    return str(uuid.uuid4())


def hash_throttle_key(raw: str) -> str:
    return hashlib.sha256(f"attendance-throttle:{raw or 'unknown'}".encode("utf-8")).hexdigest()


def insert_session(row: dict[str, Any], *, path: str | None = None) -> dict[str, Any]:
    payload = {
        "id": row.get("id") or new_id(),
        "person_uuid": row["person_uuid"],
        "user_uuid": row.get("user_uuid") or "",
        "username": row.get("username") or "",
        "display_name": row["display_name"],
        "workplace_id": row.get("workplace_id") or "",
        "workplace_label": row.get("workplace_label") or "",
        "local_date": row["local_date"],
        "status": row.get("status") or STATUS_SIGNED_IN,
        "sign_in_at": row["sign_in_at"],
        "sign_in_local_time": row["sign_in_local_time"],
        "sign_out_at": row.get("sign_out_at") or "",
        "sign_out_local_time": row.get("sign_out_local_time") or "",
        "authentication_method": row.get("authentication_method") or "staff_code",
        "terminal_id": row.get("terminal_id") or "",
        "terminal_name": row.get("terminal_name") or "",
        "created_at": row.get("created_at") or utc_stamp(),
        "created_by": row.get("created_by") or "system",
        "signed_out_by": row.get("signed_out_by") or "",
        "sign_in_photo": row.get("sign_in_photo") or "",
    }
    with LOCK:
        connection = connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO attendance_session (
                        id, person_uuid, user_uuid, username, display_name,
                        workplace_id, workplace_label, local_date, status,
                        sign_in_at, sign_in_local_time, sign_out_at, sign_out_local_time,
                        authentication_method, terminal_id, terminal_name,
                        created_at, created_by, signed_out_by, sign_in_photo
                    ) VALUES (
                        :id, :person_uuid, :user_uuid, :username, :display_name,
                        :workplace_id, :workplace_label, :local_date, :status,
                        :sign_in_at, :sign_in_local_time, :sign_out_at, :sign_out_local_time,
                        :authentication_method, :terminal_id, :terminal_name,
                        :created_at, :created_by, :signed_out_by, :sign_in_photo
                    )
                    """,
                    payload,
                )
        finally:
            connection.close()
    return get_session(payload["id"], path=path) or payload


def get_session(session_id: str, *, path: str | None = None) -> dict[str, Any] | None:
    with LOCK:
        connection = connect(path)
        try:
            row = connection.execute(
                "SELECT * FROM attendance_session WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
    return serialize_session(row)


def get_session_for_person_date(
    person_uuid: str,
    local_date: str,
    *,
    path: str | None = None,
) -> dict[str, Any] | None:
    with LOCK:
        connection = connect(path)
        try:
            row = connection.execute(
                """
                SELECT * FROM attendance_session
                WHERE person_uuid = ? AND local_date = ?
                """,
                (person_uuid, local_date),
            ).fetchone()
        finally:
            connection.close()
    return serialize_session(row)


def complete_session(
    session_id: str,
    *,
    sign_out_at: str,
    sign_out_local_time: str,
    signed_out_by: str,
    path: str | None = None,
) -> dict[str, Any] | None:
    with LOCK:
        connection = connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE attendance_session
                    SET status = ?, sign_out_at = ?, sign_out_local_time = ?, signed_out_by = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        STATUS_SIGNED_OUT,
                        sign_out_at,
                        sign_out_local_time,
                        signed_out_by,
                        session_id,
                        STATUS_SIGNED_IN,
                    ),
                )
        finally:
            connection.close()
    return get_session(session_id, path=path)


def search_sessions(
    *,
    local_date: str,
    query: str = "",
    workplace_id: str = "",
    status: str = "",
    person_uuid: str = "",
    limit: int = 200,
    offset: int = 0,
    path: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["local_date = ?"]
    values: list[Any] = [local_date]
    needle = str(query or "").strip().lower()
    if needle:
        clauses.append(
            "("
            "lower(display_name) LIKE ? OR lower(username) LIKE ? "
            "OR lower(workplace_label) LIKE ?"
            ")"
        )
        like = f"%{needle}%"
        values.extend([like, like, like])
    if workplace_id:
        clauses.append("workplace_id = ?")
        values.append(workplace_id)
    if status:
        clauses.append("status = ?")
        values.append(status)
    if person_uuid:
        clauses.append("person_uuid = ?")
        values.append(person_uuid)
    where = " AND ".join(clauses)
    bound_limit = max(1, min(int(limit), 500))
    bound_offset = max(0, int(offset))
    with LOCK:
        connection = connect(path)
        try:
            total = connection.execute(
                f"SELECT COUNT(*) FROM attendance_session WHERE {where}",
                values,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM attendance_session
                WHERE {where}
                ORDER BY display_name COLLATE NOCASE, sign_in_at ASC
                LIMIT ? OFFSET ?
                """,
                [*values, bound_limit, bound_offset],
            ).fetchall()
        finally:
            connection.close()
    return [serialize_session(row) for row in rows if serialize_session(row)], int(total)


def serialize_session(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    return {
        "id": data["id"],
        "personUuid": data["person_uuid"],
        "userUuid": data["user_uuid"],
        "username": data["username"],
        "displayName": data["display_name"],
        "workplaceId": data["workplace_id"],
        "workplaceLabel": data["workplace_label"],
        "localDate": data["local_date"],
        "status": data["status"],
        "signInAt": data["sign_in_at"],
        "signInLocalTime": data["sign_in_local_time"],
        "signOutAt": data.get("sign_out_at") or "",
        "signOutLocalTime": data.get("sign_out_local_time") or "",
        "authenticationMethod": data["authentication_method"],
        "terminalId": data["terminal_id"],
        "terminalName": data["terminal_name"],
        "createdAt": data["created_at"],
        "createdBy": data["created_by"],
        "signedOutBy": data.get("signed_out_by") or "",
        "signInPhoto": data.get("sign_in_photo") or "",
        "hasPhoto": bool(data.get("sign_in_photo")),
    }


def decode_sign_in_photo(raw: Any) -> tuple[bytes, str]:
    value = str(raw or "").strip()
    media_type = ""
    if value.startswith("data:") and ";base64," in value:
        header, value = value.split(";base64,", 1)
        media_type = header.replace("data:", "", 1).lower()
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("invalid photo") from error
    if not data:
        raise ValueError("empty photo")
    if len(data) > MAX_SIGN_IN_PHOTO_BYTES:
        raise ValueError("photo too large")
    if data.startswith(b"\xff\xd8\xff"):
        guessed = "image/jpeg"
    elif data.startswith(b"\x89PNG"):
        guessed = "image/png"
    elif data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        guessed = "image/webp"
    else:
        guessed = media_type.split(";")[0].strip()
    suffix = PHOTO_TYPES.get(guessed)
    if not suffix:
        raise ValueError("unsupported photo")
    return data, suffix


def save_sign_in_photo(
    *,
    session_id: str,
    local_date: str,
    data: bytes,
    suffix: str,
    path: str | None = None,
) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "", session_id) or new_id()
    relative = f"{local_date}/{safe_id}{suffix}"
    if not PHOTO_REL_RE.fullmatch(relative):
        raise ValueError("invalid photo path")
    folder = photos_root(path) / local_date
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{safe_id}{suffix}"
    target.write_bytes(data)
    return relative


def read_sign_in_photo(relative: str, *, path: str | None = None) -> tuple[bytes, str]:
    if not PHOTO_REL_RE.fullmatch(str(relative or "")):
        raise FileNotFoundError(relative)
    target = photos_root(path) / relative
    if not target.is_file():
        raise FileNotFoundError(relative)
    suffix = target.suffix.lower()
    content_type = next((key for key, value in PHOTO_TYPES.items() if value == suffix), "image/jpeg")
    return target.read_bytes(), content_type


def purge_expired_photos(today: str, *, path: str | None = None) -> int:
    deleted = 0
    root = photos_root(path)
    if root.is_dir():
        for folder in list(root.iterdir()):
            if not folder.is_dir() or not DATE_FOLDER_RE.fullmatch(folder.name):
                continue
            if folder.name >= today:
                continue
            for item in list(folder.iterdir()):
                if item.is_file():
                    item.unlink(missing_ok=True)
                    deleted += 1
            try:
                folder.rmdir()
            except OSError:
                pass
    with LOCK:
        connection = connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE attendance_session
                    SET sign_in_photo = ''
                    WHERE local_date < ? AND sign_in_photo != ''
                    """,
                    (today,),
                )
        finally:
            connection.close()
    return deleted


def lookup_code(code_normalized: str, *, path: str | None = None) -> dict[str, Any] | None:
    with LOCK:
        connection = connect(path)
        try:
            row = connection.execute(
                "SELECT * FROM staff_attendance_code WHERE code_normalized = ?",
                (code_normalized,),
            ).fetchone()
        finally:
            connection.close()
    return serialize_code(row)


def get_code_for_person(person_uuid: str, *, path: str | None = None) -> dict[str, Any] | None:
    with LOCK:
        connection = connect(path)
        try:
            row = connection.execute(
                "SELECT * FROM staff_attendance_code WHERE person_uuid = ?",
                (person_uuid,),
            ).fetchone()
        finally:
            connection.close()
    return serialize_code(row)


def generate_unique_code(*, path: str | None = None) -> str:
    for _ in range(40):
        candidate = f"{secrets.randbelow(1_000_000):06d}"
        if lookup_code(candidate, path=path) is None:
            return candidate
    raise RuntimeError("A unique staff code could not be created.")


def upsert_code(
    *,
    person_uuid: str,
    code_normalized: str,
    actor_username: str,
    replace: bool,
    path: str | None = None,
) -> dict[str, Any]:
    existing = get_code_for_person(person_uuid, path=path)
    clash = lookup_code(code_normalized, path=path)
    if clash and clash["personUuid"] != person_uuid:
        raise sqlite3.IntegrityError("staff code already assigned")
    stamp = utc_stamp()
    with LOCK:
        connection = connect(path)
        try:
            with connection:
                if existing:
                    if not replace and existing["code"] != code_normalized:
                        raise sqlite3.IntegrityError("staff already has a code")
                    connection.execute(
                        """
                        UPDATE staff_attendance_code
                        SET code_normalized = ?, replaced_at = ?, replaced_by = ?
                        WHERE person_uuid = ?
                        """,
                        (code_normalized, stamp, actor_username, person_uuid),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO staff_attendance_code (
                            id, person_uuid, code_normalized, created_at, created_by
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (new_id(), person_uuid, code_normalized, stamp, actor_username),
                    )
        finally:
            connection.close()
    return get_code_for_person(person_uuid, path=path) or {
        "personUuid": person_uuid,
        "code": code_normalized,
    }


def serialize_code(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    return {
        "id": data["id"],
        "personUuid": data["person_uuid"],
        "code": data["code_normalized"],
        "createdAt": data["created_at"],
        "createdBy": data["created_by"],
        "replacedAt": data.get("replaced_at") or "",
        "replacedBy": data.get("replaced_by") or "",
    }


def insert_code_audit(row: dict[str, Any], *, path: str | None = None) -> None:
    with LOCK:
        connection = connect(path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO attendance_code_audit (
                        id, occurred_at, action, person_uuid, actor_uuid,
                        actor_username, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("id") or new_id(),
                        row.get("occurred_at") or utc_stamp(),
                        row["action"],
                        row["person_uuid"],
                        row.get("actor_uuid") or "",
                        row.get("actor_username") or "",
                        _json(row.get("details") or {}),
                    ),
                )
        finally:
            connection.close()


def list_code_audit(person_uuid: str, *, path: str | None = None) -> list[dict[str, Any]]:
    with LOCK:
        connection = connect(path)
        try:
            rows = connection.execute(
                """
                SELECT * FROM attendance_code_audit
                WHERE person_uuid = ?
                ORDER BY occurred_at DESC
                """,
                (person_uuid,),
            ).fetchall()
        finally:
            connection.close()
    result = []
    for row in rows:
        data = dict(row)
        result.append(
            {
                "id": data["id"],
                "occurredAt": data["occurred_at"],
                "action": data["action"],
                "personUuid": data["person_uuid"],
                "actorUsername": data["actor_username"],
                "details": _load_json(data.get("details_json"), {}),
            }
        )
    return result


def _parse_stamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_throttle(throttle_key: str, now: datetime, *, path: str | None = None) -> None:
    key = hash_throttle_key(throttle_key)
    with LOCK:
        connection = connect(path)
        try:
            row = connection.execute(
                "SELECT * FROM attendance_attempt WHERE throttle_key = ?",
                (key,),
            ).fetchone()
        finally:
            connection.close()
    if row is None:
        return
    blocked_until = _parse_stamp(str(row["blocked_until"] or ""))
    if blocked_until is not None and blocked_until > now:
        from server import ApiError

        raise ApiError(
            429,
            "too_many_attempts",
            "Too many attempts. Wait a moment and try again.",
        )
    window_start = _parse_stamp(str(row["window_start"] or ""))
    if window_start is not None and (now - window_start).total_seconds() > THROTTLE_WINDOW_SECONDS:
        clear_failures(throttle_key, path=path)


def record_failure(throttle_key: str, now: datetime, *, path: str | None = None) -> None:
    key = hash_throttle_key(throttle_key)
    stamp = utc_stamp(now)
    with LOCK:
        connection = connect(path)
        try:
            row = connection.execute(
                "SELECT * FROM attendance_attempt WHERE throttle_key = ?",
                (key,),
            ).fetchone()
            window_start = stamp
            failed_count = 1
            if row is not None:
                previous_start = _parse_stamp(str(row["window_start"] or ""))
                if (
                    previous_start is not None
                    and (now - previous_start).total_seconds() <= THROTTLE_WINDOW_SECONDS
                ):
                    window_start = str(row["window_start"])
                    failed_count = int(row["failed_count"] or 0) + 1
            blocked_until = (
                utc_stamp(now + timedelta(seconds=THROTTLE_BLOCK_SECONDS))
                if failed_count >= THROTTLE_MAX_FAILURES
                else ""
            )
            with connection:
                connection.execute(
                    """
                    INSERT INTO attendance_attempt (
                        throttle_key, failed_count, window_start, blocked_until
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(throttle_key) DO UPDATE SET
                        failed_count = excluded.failed_count,
                        window_start = excluded.window_start,
                        blocked_until = excluded.blocked_until
                    """,
                    (
                        key,
                        failed_count,
                        window_start if isinstance(window_start, str) else stamp,
                        blocked_until,
                    ),
                )
        finally:
            connection.close()


def clear_failures(throttle_key: str, *, path: str | None = None) -> None:
    key = hash_throttle_key(throttle_key)
    with LOCK:
        connection = connect(path)
        try:
            with connection:
                connection.execute(
                    "DELETE FROM attendance_attempt WHERE throttle_key = ?",
                    (key,),
                )
        finally:
            connection.close()
