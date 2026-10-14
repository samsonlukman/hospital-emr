"""Persistent Hospital EMR staff messaging.

OpenMRS remains authoritative for sessions, users, roles, workplaces, and
patient records. This module stores only conversation/message references and
uses the existing notification store for delivery alerts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote

import hospital_admin
import notifications
import server as core

MESSAGING_DB_PATH = os.environ.get(
    "ABIKAN_MESSAGING_DB",
    "/var/lib/abikan/messaging.sqlite3",
)
LOCK = threading.Lock()

TYPE_DEPARTMENT = "department"
TYPE_DIRECT = "direct"
PARTICIPANT_WORKPLACE = "workplace"
PARTICIPANT_USER = "user"
ATTENTION_REQUESTED = "requested"
ATTENTION_ACKNOWLEDGED = "acknowledged"

WORKPLACE_LABELS = {
    str(row["id"]): str(row["label"])
    for row in hospital_admin.DEPARTMENTS
}
WORKPLACE_LABELS["administration"] = "Administration"


def _text(value: Any) -> str:
    return str(value or "").strip()


def canonical_workplace(value: Any) -> str:
    workplace = _text(value)
    if workplace == "registration":
        return "reception"
    return workplace


def _workplace_label(workplace: str) -> str:
    key = canonical_workplace(workplace)
    return WORKPLACE_LABELS.get(key, key or "Department")


def _add_participant(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    participant_type: str,
    workplace: str = "",
    username: str = "",
    added_by: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO conversation_participant
        (conversation_id, participant_type, workplace, username, added_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (conversation_id, participant_type, workplace, username, added_by, created_at),
    )


def _conversation_label(user: dict[str, Any], participants: list[Any]) -> str:
    username = user["username"]
    current = _current_workplace(user)
    other_workplaces = [
        canonical_workplace(row["workplace"])
        for row in participants
        if row["participant_type"] == PARTICIPANT_WORKPLACE
        and canonical_workplace(row["workplace"])
        and canonical_workplace(row["workplace"]) != current
    ]
    if other_workplaces:
        return _workplace_label(other_workplaces[0])
    other_users = [
        _text(row["username"])
        for row in participants
        if row["participant_type"] == PARTICIPANT_USER and _text(row["username"]) not in {"", username}
    ]
    if other_users:
        return other_users[0]
    own = [
        canonical_workplace(row["workplace"])
        for row in participants
        if row["participant_type"] == PARTICIPANT_WORKPLACE and canonical_workplace(row["workplace"])
    ]
    if own:
        return _workplace_label(own[0])
    return "Conversation"


def _public_attention(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    return {
        "id": data["id"],
        "status": data["status"],
        "requesterUsername": data.get("requester_username") or data.get("requesterUsername") or "",
        "recipientWorkplace": canonical_workplace(
            data.get("recipient_workplace") or data.get("recipientWorkplace") or ""
        ),
        "recipientUsername": data.get("recipient_username") or data.get("recipientUsername") or "",
        "createdAt": data.get("created_at") or data.get("createdAt") or "",
        "acknowledgedAt": data.get("acknowledged_at") or data.get("acknowledgedAt") or "",
        "acknowledgedByUsername": data.get("acknowledged_by_username")
        or data.get("acknowledgedByUsername")
        or "",
    }


def _now() -> float:
    return time.time()


def _iso(epoch: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch or _now()))


def _json(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, separators=(",", ":"))


def _connect(path: str | None = None) -> sqlite3.Connection:
    db = Path(path or MESSAGING_DB_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversation (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL CHECK (type IN ('department', 'direct')),
            created_by_username TEXT NOT NULL,
            patient_uuid TEXT NOT NULL DEFAULT '',
            visit_uuid TEXT NOT NULL DEFAULT '',
            encounter_uuid TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conversation_participant (
            conversation_id TEXT NOT NULL,
            participant_type TEXT NOT NULL CHECK (participant_type IN ('workplace', 'user')),
            workplace TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            added_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_read_message_id TEXT,
            last_read_at TEXT,
            PRIMARY KEY (conversation_id, participant_type, workplace, username),
            FOREIGN KEY (conversation_id) REFERENCES conversation(id)
        );
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            sender_username TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_at_epoch REAL NOT NULL,
            edited_at TEXT,
            deleted_at TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversation(id)
        );
        CREATE TABLE IF NOT EXISTS conversation_user_state (
            conversation_id TEXT NOT NULL,
            username TEXT NOT NULL,
            last_read_message_id TEXT,
            last_read_at TEXT,
            PRIMARY KEY (conversation_id, username),
            FOREIGN KEY (conversation_id) REFERENCES conversation(id)
        );
        CREATE TABLE IF NOT EXISTS attention_request (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            requester_username TEXT NOT NULL,
            recipient_workplace TEXT NOT NULL,
            recipient_username TEXT NOT NULL DEFAULT '',
            patient_uuid TEXT NOT NULL DEFAULT '',
            visit_uuid TEXT NOT NULL DEFAULT '',
            encounter_uuid TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN ('requested', 'acknowledged')),
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            acknowledged_by_username TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversation(id)
        );
        CREATE TABLE IF NOT EXISTS messaging_audit_event (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            conversation_id TEXT NOT NULL DEFAULT '',
            message_id TEXT NOT NULL DEFAULT '',
            attention_request_id TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS message_conversation_created
            ON message (conversation_id, created_at_epoch DESC);
        CREATE INDEX IF NOT EXISTS conversation_updated
            ON conversation (updated_at DESC);
        CREATE INDEX IF NOT EXISTS attention_workplace_status
            ON attention_request (recipient_workplace, status, created_at);
        CREATE TABLE IF NOT EXISTS staff_presence (
            username TEXT PRIMARY KEY,
            last_seen_at TEXT NOT NULL,
            last_seen_epoch REAL NOT NULL
        );
        """
    )
    attention_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(attention_request)").fetchall()
    }
    if "recipient_username" not in attention_columns:
        connection.execute(
            "ALTER TABLE attention_request ADD COLUMN recipient_username TEXT NOT NULL DEFAULT ''"
        )
    return connection


def _audit(
    connection: sqlite3.Connection,
    *,
    action: str,
    actor: str,
    conversation_id: str = "",
    message_id: str = "",
    attention_request_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO messaging_audit_event
        (id, action, actor_username, conversation_id, message_id,
         attention_request_id, details_json, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            action,
            actor,
            conversation_id,
            message_id,
            attention_request_id,
            _json(details),
            _iso(),
        ),
    )


def _session_user(cookie: str) -> dict[str, Any]:
    session = core.require_session(cookie)
    user = session.get("user") or {}
    session_location = session.get("sessionLocation") or {}
    username = _text(user.get("username"))
    if not username:
        raise core.ApiError(401, "unauthenticated", "Sign in required.")
    return {
        "username": username,
        "uuid": _text(user.get("uuid")),
        "display": _text(user.get("display")) or username,
        "roles": [
            _text(item.get("name"))
            for item in user.get("roles") or []
            if isinstance(item, dict) and _text(item.get("name"))
        ],
        "privileges": [
            _text(item.get("name"))
            for item in user.get("privileges") or []
            if isinstance(item, dict) and not item.get("retired") and _text(item.get("name"))
        ],
        "userProperties": user.get("userProperties") or {},
        "sessionLocationName": _text(
            session_location.get("name") or session_location.get("display")
        ),
    }


def _user_workplaces(user: dict[str, Any], *, include_superadmin: bool = True) -> set[str]:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    if include_superadmin and roles & {"SuperAdmin", "System Developer"}:
        return set(WORKPLACE_LABELS)
    result: set[str] = set()
    for row in hospital_admin.DEPARTMENTS:
        accepted = {str(row["roleName"]), *(str(item) for item in row.get("compatibilityRoles") or [])}
        if roles & accepted:
            result.add(str(row["id"]))
    if not (roles & {"SuperAdmin", "System Developer"}):
        privilege_map = {
            "registration": "app:registration",
            "clinical": "app:clinical",
            "nursing": "app:adt",
            "laboratory": "app:lab-lite",
            "radiology": "app:radiology-upload",
            "pharmacy": "bahmni:clinical:dispense",
            "accountant": "abikan:accountant",
        }
        result.update(key for key, privilege in privilege_map.items() if privilege in privileges)
        if "abikan:admin:staff" in privileges:
            result.add("administration")
    preferred = canonical_workplace(
        (user.get("userProperties") or {}).get(hospital_admin.WORKPLACE_PROPERTY)
    )
    if preferred in WORKPLACE_LABELS:
        result.add(preferred)
    return result


def _desk_workplaces(user: dict[str, Any]) -> set[str]:
    """Departments this person actually works, not every desk SuperAdmin can open."""
    return _user_workplaces(user, include_superadmin=False)


def _require_messaging_user(cookie: str) -> dict[str, Any]:
    user = _session_user(cookie)
    if not _user_workplaces(user):
        raise core.ApiError(403, "forbidden", "This account cannot use staff messages.")
    return user


def _current_workplace(user: dict[str, Any]) -> str:
    preferred = canonical_workplace(
        (user.get("userProperties") or {}).get(hospital_admin.WORKPLACE_PROPERTY)
    )
    if preferred in WORKPLACE_LABELS:
        return preferred
    if set(user.get("roles") or {}) & {"SuperAdmin", "System Developer", "Abikan:Hospital Admin"}:
        return "administration"
    location = _text(user.get("sessionLocationName")).lower()
    if "opd" in location or "consult" in location:
        return "clinical"
    if "ward" in location or "inpatient" in location:
        return "nursing"
    workplaces = _user_workplaces(user)
    return next(iter(workplaces), "")


def _staff_directory(cookie: str, representation: str) -> Any:
    path = (
        "/openmrs/ws/rest/v1/user?includeAll=true&limit=500&v="
        + quote(representation, safe="():,")
    )
    try:
        return core.openmrs_get(path, cookie)
    except core.ApiError as error:
        # Some department accounts cannot read the OpenMRS user directory.
        # Use the server-side identity account for the shared staff picker.
        if error.status != 502:
            raise
        import server

        return server.openmrs_service_get(path)


def _validate_staff_target(cookie: str, username: str) -> None:
    representation = "custom:(uuid,username,retired,person:(display),roles:(name),userProperties)"
    payload = _staff_directory(cookie, representation)
    rows = payload.get("results") if isinstance(payload, dict) else payload
    if not any(
        _text(row.get("username")).lower() == username.lower() and not row.get("retired")
        for row in rows or []
    ):
        raise core.ApiError(404, "staff_not_found", "That staff member was not found.")


def _validate_context(
    cookie: str,
    patient_uuid: str,
    visit_uuid: str,
    encounter_uuid: str,
) -> None:
    patient = _text(patient_uuid)
    visit = _text(visit_uuid)
    encounter = _text(encounter_uuid)
    if not patient and (visit or encounter):
        raise core.ApiError(422, "invalid_context", "A patient is required for this context.")
    if not patient:
        return
    core.load_openmrs_patient(patient, cookie)
    if visit:
        visit_row = core.openmrs_get(f"/openmrs/ws/rest/v1/visit/{visit}", cookie)
        visit_patient = visit_row.get("patient") or {}
        if _text(visit_patient.get("uuid")) and _text(visit_patient.get("uuid")) != patient:
            raise core.ApiError(403, "invalid_context", "This visit does not belong to the selected patient.")
    if encounter:
        encounter_row = core.openmrs_get(f"/openmrs/ws/rest/v1/encounter/{encounter}", cookie)
        encounter_patient = encounter_row.get("patient") or {}
        if _text(encounter_patient.get("uuid")) and _text(encounter_patient.get("uuid")) != patient:
            raise core.ApiError(403, "invalid_context", "This encounter does not belong to the selected patient.")


def _row_conversation(row: sqlite3.Row, unread: int = 0) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "createdByUsername": row["created_by_username"],
        "patientUuid": row["patient_uuid"] or "",
        "visitUuid": row["visit_uuid"] or "",
        "encounterUuid": row["encounter_uuid"] or "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "archivedAt": row["archived_at"] or "",
        "unreadCount": unread,
    }


def _participant_access(
    user: dict[str, Any],
    connection: sqlite3.Connection,
    conversation_id: str,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        "SELECT * FROM conversation_participant WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchall()
    workplaces = _user_workplaces(user)
    username = user["username"]
    allowed = [
        row
        for row in rows
        if (row["participant_type"] == PARTICIPANT_USER and row["username"] == username)
        or (row["participant_type"] == PARTICIPANT_WORKPLACE and row["workplace"] in workplaces)
    ]
    if not allowed:
        raise core.ApiError(403, "forbidden", "This conversation is not available for this account.")
    return allowed


def _conversation(connection: sqlite3.Connection, conversation_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM conversation WHERE id = ? AND archived_at IS NULL",
        (conversation_id,),
    ).fetchone()
    if not row:
        raise core.ApiError(404, "conversation_not_found", "That conversation was not found.")
    return row


def _unread_count(connection: sqlite3.Connection, conversation_id: str, user: dict[str, Any]) -> int:
    _participant_access(user, connection, conversation_id)
    state = connection.execute(
        """
        SELECT last_read_at FROM conversation_user_state
        WHERE conversation_id = ? AND username = ?
        """,
        (conversation_id, user["username"]),
    ).fetchone()
    if state and state["last_read_at"]:
        return int(
            connection.execute(
                """
                SELECT COUNT(*) FROM message
                WHERE conversation_id = ? AND created_at > ?
                  AND sender_username != ? AND deleted_at IS NULL
                """,
                (conversation_id, state["last_read_at"], user["username"]),
            ).fetchone()[0]
        )
    return int(
        connection.execute(
            """
            SELECT COUNT(*) FROM message
            WHERE conversation_id = ? AND sender_username != ? AND deleted_at IS NULL
            """,
            (conversation_id, user["username"]),
        ).fetchone()[0]
    )


def list_workplaces(cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    current_workplace = _current_workplace(user)
    available = sorted(
        (
            {"id": key, "label": WORKPLACE_LABELS[key]}
            for key in WORKPLACE_LABELS
            if key != current_workplace
        ),
        key=lambda item: item["label"],
    )
    return {"status": "ok", "workplaces": available}


def list_staff(cookie: str, raw_path: str = "") -> dict[str, Any]:
    current_user = _require_messaging_user(cookie)
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    needle = _text((query.get("q") or [""])[0]).lower()
    representation = (
        "custom:(uuid,username,display,retired,person:(display),"
        "roles:(name),userProperties)"
    )
    payload = _staff_directory(cookie, representation)
    rows = payload.get("results") if isinstance(payload, dict) else payload
    staff = []
    for row in rows or []:
        if row.get("retired"):
            continue
        role_names = {
            _text(item.get("name"))
            for item in row.get("roles") or []
            if isinstance(item, dict)
        }
        if role_names & {"SuperAdmin", "System Developer", "Privilege Level: Full"}:
            continue
        username = _text(row.get("username"))
        person = row.get("person") or {}
        display = _text(person.get("display")) or _text(row.get("display")) or username
        if (
            not username
            or username == current_user["username"]
            or (needle and needle not in f"{username} {display}".lower())
        ):
            continue
        staff.append({
            "username": username,
            "displayName": display,
            "online": _staff_is_online(username),
        })
    staff.sort(key=lambda item: (not item["online"], item["displayName"].lower()))
    return {"status": "ok", "staff": staff[:100]}


def heartbeat(cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    now = _now()
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO staff_presence (username, last_seen_at, last_seen_epoch)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    last_seen_epoch = excluded.last_seen_epoch
                """,
                (user["username"], _iso(now), now),
            )
            connection.commit()
        finally:
            connection.close()
    return {"status": "ok", "online": True}


def _staff_is_online(username: str) -> bool:
    with LOCK:
        connection = _connect()
        try:
            row = connection.execute(
                "SELECT last_seen_epoch FROM staff_presence WHERE username = ?",
                (_text(username),),
            ).fetchone()
        finally:
            connection.close()
    return bool(row and float(row["last_seen_epoch"]) >= _now() - 90)


def _load_messages(
    connection: sqlite3.Connection,
    conversation_id: str,
    *,
    before: str = "",
    after: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit or 50), 1), 100)
    if after:
        rows = connection.execute(
            """
            SELECT * FROM message
            WHERE conversation_id = ? AND created_at_epoch > ?
            ORDER BY created_at_epoch ASC LIMIT ?
            """,
            (conversation_id, float(after), safe_limit),
        ).fetchall()
    elif before:
        rows = connection.execute(
            """
            SELECT * FROM message
            WHERE conversation_id = ? AND created_at_epoch < ?
            ORDER BY created_at_epoch DESC LIMIT ?
            """,
            (conversation_id, float(before), safe_limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM message WHERE conversation_id = ?
            ORDER BY created_at_epoch DESC LIMIT ?
            """,
            (conversation_id, safe_limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "conversationId": row["conversation_id"],
            "senderUsername": row["sender_username"],
            "body": "[Message removed]" if row["deleted_at"] else row["body"],
            "createdAt": row["created_at"],
            "editedAt": row["edited_at"] or "",
            "deletedAt": row["deleted_at"] or "",
        }
        for row in reversed(rows)
    ]


def list_conversations(cookie: str, raw_path: str = "") -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    needle = _text((query.get("q") or [""])[0]).lower()
    with LOCK:
        connection = _connect()
        try:
            _merge_duplicate_direct(connection, _iso())
            connection.commit()
            rows = connection.execute(
                "SELECT * FROM conversation WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 200"
            ).fetchall()
            result = []
            for row in rows:
                try:
                    _participant_access(user, connection, row["id"])
                except core.ApiError:
                    continue
                participants = connection.execute(
                    "SELECT * FROM conversation_participant WHERE conversation_id = ?",
                    (row["id"],),
                ).fetchall()
                label = _conversation_label(user, participants)
                latest = connection.execute(
                    """
                    SELECT body FROM message WHERE conversation_id = ?
                    ORDER BY created_at_epoch DESC LIMIT 1
                    """,
                    (row["id"],),
                ).fetchone()
                if needle and needle not in f"{label} {latest['body'] if latest else ''}".lower():
                    continue
                result.append(
                    {
                        **_row_conversation(row, _unread_count(connection, row["id"], user)),
                        "label": label,
                        "latestMessage": latest["body"] if latest else "",
                        "hasPatientContext": bool(row["patient_uuid"]),
                        "participants": [
                            {
                                "type": p["participant_type"],
                                "workplace": p["workplace"],
                                "username": p["username"],
                            }
                            for p in participants
                        ],
                    }
                )
            return {"status": "ok", "conversations": result}
        finally:
            connection.close()


def _direct_user_key(connection: sqlite3.Connection, conversation_id: str) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT username FROM conversation_participant
        WHERE conversation_id = ? AND participant_type = 'user' AND username != ''
        ORDER BY username
        """,
        (conversation_id,),
    ).fetchall()
    return tuple(_text(row["username"]) for row in rows)


def _fold_conversation(connection: sqlite3.Connection, keeper_id: str, extra_id: str, now: str) -> None:
    connection.execute(
        "UPDATE message SET conversation_id = ? WHERE conversation_id = ?",
        (keeper_id, extra_id),
    )
    connection.execute(
        "UPDATE attention_request SET conversation_id = ? WHERE conversation_id = ?",
        (keeper_id, extra_id),
    )
    for state in connection.execute(
        "SELECT * FROM conversation_user_state WHERE conversation_id = ?",
        (extra_id,),
    ).fetchall():
        current = connection.execute(
            """
            SELECT last_read_at FROM conversation_user_state
            WHERE conversation_id = ? AND username = ?
            """,
            (keeper_id, state["username"]),
        ).fetchone()
        if not current:
            connection.execute(
                """
                INSERT INTO conversation_user_state
                (conversation_id, username, last_read_message_id, last_read_at)
                VALUES (?, ?, ?, ?)
                """,
                (keeper_id, state["username"], state["last_read_message_id"], state["last_read_at"]),
            )
        elif (state["last_read_at"] or "") > (current["last_read_at"] or ""):
            connection.execute(
                """
                UPDATE conversation_user_state
                SET last_read_message_id = ?, last_read_at = ?
                WHERE conversation_id = ? AND username = ?
                """,
                (state["last_read_message_id"], state["last_read_at"], keeper_id, state["username"]),
            )
    connection.execute("UPDATE conversation SET archived_at = ? WHERE id = ?", (now, extra_id))


def _merge_duplicate_direct(connection: sqlite3.Connection, now: str) -> None:
    rows = connection.execute(
        """
        SELECT id, patient_uuid, visit_uuid, updated_at
        FROM conversation
        WHERE type = 'direct' AND archived_at IS NULL
        """
    ).fetchall()
    groups: dict[tuple[str, str, tuple[str, ...]], list[sqlite3.Row]] = {}
    for row in rows:
        users = _direct_user_key(connection, row["id"])
        if len(users) < 2:
            continue
        groups.setdefault((row["patient_uuid"] or "", row["visit_uuid"] or "", users), []).append(row)
    for members in groups.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda item: item["updated_at"] or "", reverse=True)
        keeper_id = ordered[0]["id"]
        for extra in ordered[1:]:
            _fold_conversation(connection, keeper_id, extra["id"], now)


def _find_direct_conversation(
    connection: sqlite3.Connection,
    patient: str,
    visit: str,
    first_username: str,
    second_username: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT c.* FROM conversation c
        WHERE c.type = 'direct' AND c.archived_at IS NULL
          AND c.patient_uuid = ? AND c.visit_uuid = ?
          AND EXISTS (
            SELECT 1 FROM conversation_participant p
            WHERE p.conversation_id = c.id
              AND p.participant_type = 'user' AND p.username = ?
          )
          AND EXISTS (
            SELECT 1 FROM conversation_participant p
            WHERE p.conversation_id = c.id
              AND p.participant_type = 'user' AND p.username = ?
          )
        ORDER BY c.updated_at DESC LIMIT 1
        """,
        (patient, visit, first_username, second_username),
    ).fetchone()


def create_conversation(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    conversation_type = _text(body.get("type"))
    workplace = _text(body.get("workplace"))
    username = _text(body.get("username"))
    if conversation_type not in {TYPE_DEPARTMENT, TYPE_DIRECT}:
        raise core.ApiError(422, "invalid_body", "Choose a department or staff member.")
    if conversation_type == TYPE_DEPARTMENT:
        workplace = canonical_workplace(workplace)
        if workplace not in WORKPLACE_LABELS:
            raise core.ApiError(403, "forbidden", "Choose an available department.")
        if workplace == _current_workplace(user):
            raise core.ApiError(422, "invalid_recipient", "Choose another department.")
    elif not username or username == user["username"]:
        raise core.ApiError(422, "invalid_body", "Choose another staff member.")
    elif conversation_type == TYPE_DIRECT:
        _validate_staff_target(cookie, username)
    patient = _text(body.get("patientUuid"))
    visit = _text(body.get("visitUuid"))
    encounter = _text(body.get("encounterUuid"))
    _validate_context(cookie, patient, visit, encounter)
    now = _iso()
    conversation_id = uuid.uuid4().hex
    with LOCK:
        connection = _connect()
        try:
            origin = _current_workplace(user)
            if conversation_type == TYPE_DIRECT:
                _merge_duplicate_direct(connection, now)
                existing_direct = _find_direct_conversation(connection, patient, visit, user["username"], username)
                if existing_direct:
                    connection.commit()
                    return {"status": "ok", "conversation": _row_conversation(existing_direct), "duplicate": True}
            if conversation_type == TYPE_DEPARTMENT:
                existing = connection.execute(
                    """
                    SELECT c.* FROM conversation c
                    WHERE c.type = 'department' AND c.archived_at IS NULL
                      AND c.patient_uuid = ? AND c.visit_uuid = ?
                      AND EXISTS (
                        SELECT 1 FROM conversation_participant p
                        WHERE p.conversation_id = c.id
                          AND p.participant_type = 'workplace' AND p.workplace = ?
                      )
                      AND (
                        ? = '' OR EXISTS (
                          SELECT 1 FROM conversation_participant p
                          WHERE p.conversation_id = c.id
                            AND p.participant_type = 'workplace' AND p.workplace = ?
                        )
                      )
                    ORDER BY c.updated_at DESC LIMIT 1
                    """,
                    (patient, visit, workplace, origin, origin),
                ).fetchone()
                if existing:
                    _add_participant(
                        connection,
                        conversation_id=existing["id"],
                        participant_type=PARTICIPANT_USER,
                        username=user["username"],
                        added_by=user["username"],
                        created_at=now,
                    )
                    if origin:
                        _add_participant(
                            connection,
                            conversation_id=existing["id"],
                            participant_type=PARTICIPANT_WORKPLACE,
                            workplace=origin,
                            added_by=user["username"],
                            created_at=now,
                        )
                    _add_participant(
                        connection,
                        conversation_id=existing["id"],
                        participant_type=PARTICIPANT_WORKPLACE,
                        workplace=workplace,
                        added_by=user["username"],
                        created_at=now,
                    )
                    connection.commit()
                    return {"status": "ok", "conversation": _row_conversation(existing), "duplicate": True}
            connection.execute(
                """
                INSERT INTO conversation
                (id, type, created_by_username, patient_uuid, visit_uuid,
                 encounter_uuid, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, conversation_type, user["username"], patient, visit, encounter, now, now),
            )
            _add_participant(
                connection,
                conversation_id=conversation_id,
                participant_type=PARTICIPANT_USER,
                username=user["username"],
                added_by=user["username"],
                created_at=now,
            )
            if conversation_type == TYPE_DEPARTMENT:
                _add_participant(
                    connection,
                    conversation_id=conversation_id,
                    participant_type=PARTICIPANT_WORKPLACE,
                    workplace=workplace,
                    added_by=user["username"],
                    created_at=now,
                )
                if origin and origin != workplace:
                    _add_participant(
                        connection,
                        conversation_id=conversation_id,
                        participant_type=PARTICIPANT_WORKPLACE,
                        workplace=origin,
                        added_by=user["username"],
                        created_at=now,
                    )
            else:
                _add_participant(
                    connection,
                    conversation_id=conversation_id,
                    participant_type=PARTICIPANT_USER,
                    username=username,
                    added_by=user["username"],
                    created_at=now,
                )
            _audit(connection, action="conversation_created", actor=user["username"], conversation_id=conversation_id)
            connection.commit()
            row = connection.execute("SELECT * FROM conversation WHERE id = ?", (conversation_id,)).fetchone()
            return {"status": "ok", "conversation": _row_conversation(row), "duplicate": False}
        finally:
            connection.close()


def get_conversation(conversation_id: str, cookie: str, raw_path: str = "") -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    before = _text((query.get("before") or [""])[0])
    after = _text((query.get("after") or [""])[0])
    with LOCK:
        connection = _connect()
        try:
            row = _conversation(connection, conversation_id)
            _participant_access(user, connection, conversation_id)
            participants = connection.execute(
                "SELECT * FROM conversation_participant WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            attention = connection.execute(
                """
                SELECT * FROM attention_request
                WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            payload = {
                **_row_conversation(row, _unread_count(connection, conversation_id, user)),
                "label": _conversation_label(user, participants),
                "participants": [
                    {
                        "type": p["participant_type"],
                        "workplace": p["workplace"],
                        "username": p["username"],
                        "lastReadAt": p["last_read_at"] or "",
                    }
                    for p in participants
                ],
                "messages": _load_messages(connection, conversation_id, before=before, after=after),
                "attention": _public_attention(attention),
            }
            if row["patient_uuid"]:
                payload["patient"] = core.load_openmrs_patient(row["patient_uuid"], cookie)
            return {"status": "ok", "conversation": payload}
        finally:
            connection.close()


def send_message(conversation_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    text = _text(body.get("body"))
    if not text:
        raise core.ApiError(422, "invalid_body", "Type a message first.")
    if len(text) > 5000:
        raise core.ApiError(422, "invalid_body", "Messages must be 5,000 characters or fewer.")
    with LOCK:
        connection = _connect()
        try:
            row = _conversation(connection, conversation_id)
            _participant_access(user, connection, conversation_id)
            now_epoch = _now()
            now = _iso(now_epoch)
            message_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO message
                (id, conversation_id, sender_username, body, created_at, created_at_epoch)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, user["username"], text, now, now_epoch),
            )
            connection.execute(
                "UPDATE conversation SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            _audit(connection, action="message_sent", actor=user["username"], conversation_id=conversation_id, message_id=message_id)
            connection.commit()
        finally:
            connection.close()
    # Alerts are best-effort: durable message creation must not be rolled back by a banner failure.
    try:
        with LOCK:
            connection = _connect()
            participants = connection.execute(
                "SELECT * FROM conversation_participant WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            connection.close()
        current_workplace = _current_workplace(user)
        recipient_workplaces = [
            canonical_workplace(p["workplace"])
            for p in participants
            if p["participant_type"] == PARTICIPANT_WORKPLACE
            and canonical_workplace(p["workplace"])
            and canonical_workplace(p["workplace"]) != current_workplace
        ]
        recipient_users = (
            []
            if _text(row["type"]) == TYPE_DEPARTMENT
            else [
                p["username"]
                for p in participants
                if p["participant_type"] == PARTICIPANT_USER and p["username"] != user["username"]
            ]
        )
        for target in recipient_workplaces:
            if notifications.message_notification_allowed(
                conversation_id=conversation_id,
                recipient_scope=notifications.SCOPE_WORKPLACE,
                recipient_workplace=target,
            ):
                notifications.emit(
                    event_type="message_received",
                    title="New message",
                    message=f"{user['display']} sent you a message.",
                    sender_username=user["username"],
                    sender_display=user["display"],
                    recipient_scope=notifications.SCOPE_WORKPLACE,
                    recipient_workplace=target,
                    patient_uuid=_text(row["patient_uuid"]),
                    visit_uuid=_text(row["visit_uuid"]),
                    priority=notifications.PRIORITY_NORMAL,
                    ttl_seconds=24 * 60 * 60,
                    idempotency_key=f"message_received:{message_id}:{target}",
                    action_href=f"#/messages/{conversation_id}",
                    payload={"conversationId": conversation_id, "messageId": message_id},
                )
        for target in recipient_users:
            if notifications.message_notification_allowed(
                conversation_id=conversation_id,
                recipient_scope=notifications.SCOPE_USER,
                recipient_user=target,
            ):
                notifications.emit(
                    event_type="message_received",
                    title="New message",
                    message=f"{user['display']} sent you a message.",
                    sender_username=user["username"],
                    sender_display=user["display"],
                    recipient_scope=notifications.SCOPE_USER,
                    recipient_user=target,
                    priority=notifications.PRIORITY_NORMAL,
                    ttl_seconds=24 * 60 * 60,
                    idempotency_key=f"message_received:{message_id}:{target}",
                    action_href=f"#/messages/{conversation_id}",
                    payload={"conversationId": conversation_id, "messageId": message_id},
                )
    except Exception:
        pass
    return {"status": "ok", "message": {"id": message_id, "conversationId": conversation_id, "senderUsername": user["username"], "body": text, "createdAt": now}}


def mark_read(conversation_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    message_id = _text(body.get("messageId"))
    with LOCK:
        connection = _connect()
        try:
            _conversation(connection, conversation_id)
            participants = _participant_access(user, connection, conversation_id)
            target = message_id or _text(
                (
                    connection.execute(
                        "SELECT id FROM message WHERE conversation_id = ? ORDER BY created_at_epoch DESC LIMIT 1",
                        (conversation_id,),
                    ).fetchone()["id"]
                    if connection.execute(
                        "SELECT id FROM message WHERE conversation_id = ? ORDER BY created_at_epoch DESC LIMIT 1",
                        (conversation_id,),
                    ).fetchone()
                    else ""
                )
            )
            if not target:
                return {"status": "ok", "changed": False}
            message = connection.execute(
                "SELECT id, created_at FROM message WHERE id = ? AND conversation_id = ?",
                (target, conversation_id),
            ).fetchone()
            if not message:
                raise core.ApiError(404, "message_not_found", "That message was not found.")
            for participant in participants:
                if participant["participant_type"] == PARTICIPANT_USER and participant["username"] == user["username"]:
                    connection.execute(
                        """
                        UPDATE conversation_participant
                        SET last_read_message_id = ?, last_read_at = ?
                        WHERE conversation_id = ? AND participant_type = 'user' AND username = ?
                        """,
                        (target, message["created_at"], conversation_id, user["username"]),
                    )
            connection.execute(
                """
                INSERT INTO conversation_user_state
                (conversation_id, username, last_read_message_id, last_read_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(conversation_id, username) DO UPDATE SET
                    last_read_message_id = excluded.last_read_message_id,
                    last_read_at = excluded.last_read_at
                """,
                (conversation_id, user["username"], target, message["created_at"]),
            )
            _audit(connection, action="conversation_read", actor=user["username"], conversation_id=conversation_id, message_id=target)
            connection.commit()
            return {"status": "ok", "changed": True}
        finally:
            connection.close()


def _attention_target(
    user: dict[str, Any],
    participants: list[sqlite3.Row],
) -> tuple[str, str]:
    current = _current_workplace(user)
    other_workplaces = [
        canonical_workplace(row["workplace"])
        for row in participants
        if row["participant_type"] == PARTICIPANT_WORKPLACE
        and canonical_workplace(row["workplace"])
        and canonical_workplace(row["workplace"]) != current
    ]
    if other_workplaces:
        return PARTICIPANT_WORKPLACE, other_workplaces[0]
    other_users = [
        _text(row["username"])
        for row in participants
        if row["participant_type"] == PARTICIPANT_USER
        and _text(row["username"]) not in {"", user["username"]}
    ]
    if other_users:
        return PARTICIPANT_USER, other_users[0]
    raise core.ApiError(422, "invalid_recipient", "Choose another department or staff member.")


def _notify_attention(
    *,
    user: dict[str, Any],
    conversation_id: str,
    request_id: str,
    target_type: str,
    target_value: str,
    patient_uuid: str,
    visit_uuid: str,
) -> None:
    origin = _current_workplace(user)
    origin_label = _workplace_label(origin) if origin else user["display"]
    if target_type == PARTICIPANT_WORKPLACE:
        message = f"{origin_label} needs {_workplace_label(target_value)}."
    else:
        message = f"{user['display']} needs you."
    notifications.emit(
        event_type="department_attention_requested",
        title="Incoming call",
        message=message,
        sender_username=user["username"],
        sender_display=user["display"],
        recipient_scope=(
            notifications.SCOPE_WORKPLACE
            if target_type == PARTICIPANT_WORKPLACE
            else notifications.SCOPE_USER
        ),
        recipient_workplace=target_value if target_type == PARTICIPANT_WORKPLACE else "",
        recipient_user=target_value if target_type == PARTICIPANT_USER else "",
        patient_uuid=patient_uuid,
        visit_uuid=visit_uuid,
        mrn="",
        patient_name="",
        priority=notifications.PRIORITY_URGENT,
        speak=True,
        ttl_seconds=2 * 60 * 60,
        idempotency_key=f"attention:{request_id}:{int(_now())}",
        action_href=f"#/messages/{conversation_id}",
        payload={
            "attentionRequestId": request_id,
            "conversationId": conversation_id,
            "recipientWorkplace": target_value if target_type == PARTICIPANT_WORKPLACE else "",
            "recipientUsername": target_value if target_type == PARTICIPANT_USER else "",
        },
    )


def request_attention(conversation_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    with LOCK:
        connection = _connect()
        try:
            row = _conversation(connection, conversation_id)
            _participant_access(user, connection, conversation_id)
            participants = connection.execute(
                "SELECT * FROM conversation_participant WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            target_type, target_value = _attention_target(user, participants)
            existing = connection.execute(
                """
                SELECT * FROM attention_request
                WHERE conversation_id = ? AND status = 'requested'
                  AND requester_username = ?
                  AND recipient_workplace = ?
                  AND recipient_username = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (
                    conversation_id,
                    user["username"],
                    target_value if target_type == PARTICIPANT_WORKPLACE else "",
                    target_value if target_type == PARTICIPANT_USER else "",
                ),
            ).fetchone()
            duplicate = False
            if existing:
                request_id = existing["id"]
                now = existing["created_at"]
                duplicate = True
            else:
                request_id = uuid.uuid4().hex
                now = _iso()
                connection.execute(
                    """
                    INSERT INTO attention_request
                    (id, conversation_id, requester_username, recipient_workplace,
                     recipient_username, patient_uuid, visit_uuid, encounter_uuid, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'requested', ?)
                    """,
                    (
                        request_id,
                        conversation_id,
                        user["username"],
                        target_value if target_type == PARTICIPANT_WORKPLACE else "",
                        target_value if target_type == PARTICIPANT_USER else "",
                        _text(row["patient_uuid"]),
                        _text(row["visit_uuid"]),
                        _text(row["encounter_uuid"]),
                        now,
                    ),
                )
                _audit(
                    connection,
                    action="attention_requested",
                    actor=user["username"],
                    conversation_id=conversation_id,
                    attention_request_id=request_id,
                )
                connection.commit()
            attention = connection.execute(
                "SELECT * FROM attention_request WHERE id = ?",
                (request_id,),
            ).fetchone()
        finally:
            connection.close()
    try:
        _notify_attention(
            user=user,
            conversation_id=conversation_id,
            request_id=request_id,
            target_type=target_type,
            target_value=target_value,
            patient_uuid=_text(row["patient_uuid"]),
            visit_uuid=_text(row["visit_uuid"]),
        )
    except Exception:
        pass
    return {
        "status": "ok",
        "attention": _public_attention(attention),
        "duplicate": duplicate,
    }


def acknowledge_attention(attention_id: str, cookie: str) -> dict[str, Any]:
    user = _require_messaging_user(cookie)
    with LOCK:
        connection = _connect()
        try:
            attention = connection.execute(
                "SELECT * FROM attention_request WHERE id = ?",
                (attention_id,),
            ).fetchone()
            if not attention:
                raise core.ApiError(404, "attention_not_found", "That attention request was not found.")
            if not (
                attention["recipient_username"] == user["username"]
                or (
                    attention["recipient_workplace"]
                    and canonical_workplace(attention["recipient_workplace"]) in _desk_workplaces(user)
                )
            ):
                raise core.ApiError(403, "forbidden", "Only the requested department can acknowledge this request.")
            if attention["status"] == ATTENTION_ACKNOWLEDGED:
                try:
                    notifications.acknowledge_attention_request(attention_id, cookie)
                except Exception:
                    pass
                return {"status": "ok", "attention": _public_attention(attention), "duplicate": True}
            now = _iso()
            connection.execute(
                """
                UPDATE attention_request
                SET status = 'acknowledged', acknowledged_at = ?, acknowledged_by_username = ?
                WHERE id = ?
                """,
                (now, user["username"], attention_id),
            )
            _audit(connection, action="attention_acknowledged", actor=user["username"], conversation_id=attention["conversation_id"], attention_request_id=attention_id)
            connection.commit()
            updated = connection.execute("SELECT * FROM attention_request WHERE id = ?", (attention_id,)).fetchone()
            conversation_id = str(attention["conversation_id"] or "")
            result = _public_attention(updated) or {}
        finally:
            connection.close()
    try:
        notifications.emit(
            event_type="department_attention_acknowledged",
            title="Attention acknowledged",
            message=f"{user['display']} acknowledged your request.",
            sender_username=user["username"],
            sender_display=user["display"],
            recipient_scope=notifications.SCOPE_USER,
            recipient_user=result.get("requesterUsername") or "",
            priority=notifications.PRIORITY_HIGH,
            ttl_seconds=24 * 60 * 60,
            idempotency_key=f"attention_acknowledged:{attention_id}",
            action_href=f"#/messages/{conversation_id}",
            payload={
                "attentionRequestId": attention_id,
                "conversationId": conversation_id,
                "acknowledgedByUsername": user["username"],
            },
        )
    except Exception:
        pass
    try:
        notifications.acknowledge_attention_request(attention_id, cookie)
    except Exception:
        pass
    return {"status": "ok", "attention": result, "duplicate": False}


def reset_for_tests(path: str | None = None) -> None:
    with LOCK:
        connection = _connect(path)
        try:
            for table in ("messaging_audit_event", "attention_request", "conversation_user_state", "message", "conversation_participant", "conversation"):
                connection.execute(f"DELETE FROM {table}")
            connection.commit()
        finally:
            connection.close()
