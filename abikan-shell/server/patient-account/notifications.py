"""Hospital staff notifications — persistent SQLite store.

Phase 1 foundation. Domain writers call emit(); desks poll list_for_session().
Does not store clinical notes, diagnoses, meds, or lab results.
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
from urllib.parse import parse_qs

import registration as reception
import server as core
from server import ApiError

NOTIFICATIONS_DB_PATH = os.environ.get(
    "ABIKAN_NOTIFICATIONS_DB",
    "/var/lib/abikan/notifications.sqlite3",
)

LOCK = threading.Lock()

PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_URGENT = "urgent"
PRIORITIES = {PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_URGENT}

STATUS_PENDING = "pending"
STATUS_READ = "read"
STATUS_ACKED = "acked"
STATUS_EXPIRED = "expired"
ACTIVE_STATUSES = {STATUS_PENDING, STATUS_READ}

SCOPE_ROLE = "role"
SCOPE_WORKPLACE = "workplace"
SCOPE_USER = "user"

EVENT_PATIENT_CALLED = "patient_called"
EVENT_VISIT_STARTED = "visit_started"
EVENT_ADMIT_REQUESTED = "admit_requested"
EVENT_PRESCRIPTION_CREATED = "prescription_created"
EVENT_NURSING_TREATMENT = "nursing_treatment"
EVENT_MEDICATION_DUE = "medication_due"
EVENT_MESSAGE_RECEIVED = "message_received"
EVENT_DEPARTMENT_ATTENTION_REQUESTED = "department_attention_requested"
WORKPLACE_REGISTRATION = "registration"
WORKPLACE_CLINICAL = "clinical"
WORKPLACE_NURSING = "nursing"
WORKPLACE_PHARMACY = "pharmacy"
WORKPLACE_LABORATORY = "laboratory"
WORKPLACE_RADIOLOGY = "radiology"
WORKPLACE_ACCOUNTANT = "accountant"
WORKPLACE_ADMINISTRATION = "administration"

PATIENT_CALLED_TTL_SECONDS = 15 * 60
PATIENT_CALLED_DEDUPE_SECONDS = 20
VISIT_STARTED_TTL_SECONDS = 4 * 60 * 60
ADMIT_REQUESTED_TTL_SECONDS = 2 * 60 * 60
PRESCRIPTION_CREATED_TTL_SECONDS = 4 * 60 * 60
NURSING_TREATMENT_TTL_SECONDS = 4 * 60 * 60


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> float:
    return time.time()


def _iso(epoch: float | None = None) -> str:
    moment = epoch if epoch is not None else _now()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(moment))


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True, separators=(",", ":"))


def _json_loads(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or NOTIFICATIONS_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS staff_notification (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            priority TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            sender_username TEXT NOT NULL,
            sender_display TEXT NOT NULL,
            recipient_scope TEXT NOT NULL,
            recipient_role TEXT NOT NULL,
            recipient_workplace TEXT NOT NULL,
            recipient_user TEXT NOT NULL,
            patient_uuid TEXT NOT NULL,
            visit_uuid TEXT NOT NULL,
            mrn TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            action_href TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'read', 'acked', 'expired')),
            created_at TEXT NOT NULL,
            created_at_epoch REAL NOT NULL,
            read_at TEXT,
            acked_at TEXT,
            acked_by TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL,
            expires_at_epoch REAL NOT NULL,
            speak INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS staff_notification_active "
        "ON staff_notification (status, expires_at_epoch, recipient_workplace, event_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS staff_notification_created "
        "ON staff_notification (created_at_epoch DESC)"
    )
    return connection


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "eventType": row["event_type"],
        "idempotencyKey": row["idempotency_key"],
        "priority": row["priority"],
        "title": row["title"],
        "message": row["message"],
        "senderUsername": row["sender_username"],
        "senderDisplay": row["sender_display"],
        "recipientScope": row["recipient_scope"],
        "recipientRole": row["recipient_role"],
        "recipientWorkplace": row["recipient_workplace"],
        "recipientUser": row["recipient_user"],
        "patientUuid": row["patient_uuid"],
        "visitUuid": row["visit_uuid"],
        "mrn": row["mrn"],
        "patientName": row["patient_name"],
        "actionHref": row["action_href"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "createdAtEpoch": float(row["created_at_epoch"]),
        "readAt": row["read_at"] or "",
        "ackedAt": row["acked_at"] or "",
        "ackedBy": row["acked_by"] or "",
        "expiresAt": row["expires_at"],
        "expiresAtEpoch": float(row["expires_at_epoch"]),
        "speak": bool(row["speak"]),
        "payload": _json_loads(row["payload_json"]),
    }


def purge_expired(path: str | None = None, now: float | None = None) -> int:
    moment = now if now is not None else _now()
    with LOCK:
        connection = _connect(path)
        try:
            cursor = connection.execute(
                """
                UPDATE staff_notification
                SET status = ?
                WHERE status IN (?, ?)
                  AND expires_at_epoch < ?
                """,
                (STATUS_EXPIRED, STATUS_PENDING, STATUS_READ, moment),
            )
            connection.commit()
            return int(cursor.rowcount or 0)
        finally:
            connection.close()


def _get_by_idempotency(connection: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM staff_notification WHERE idempotency_key = ? LIMIT 1",
        (key,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def _get_by_id(connection: sqlite3.Connection, notification_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM staff_notification WHERE id = ? LIMIT 1",
        (notification_id,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def emit(
    *,
    event_type: str,
    title: str,
    message: str,
    sender_username: str,
    sender_display: str,
    recipient_scope: str,
    recipient_role: str = "",
    recipient_workplace: str = "",
    recipient_user: str = "",
    patient_uuid: str = "",
    visit_uuid: str = "",
    mrn: str = "",
    patient_name: str = "",
    action_href: str = "",
    priority: str = PRIORITY_NORMAL,
    speak: bool = False,
    ttl_seconds: int = 24 * 60 * 60,
    idempotency_key: str = "",
    payload: dict[str, Any] | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Create a notification. Returns {notification, duplicate}."""
    event = _text(event_type)
    if not event:
        raise ApiError(422, "invalid_body", "Notification event type is required.")
    if priority not in PRIORITIES:
        raise ApiError(422, "invalid_body", "Notification priority is invalid.")
    if recipient_scope not in {SCOPE_ROLE, SCOPE_WORKPLACE, SCOPE_USER}:
        raise ApiError(422, "invalid_body", "Notification recipient is invalid.")

    now = _now()
    expires = now + max(60, int(ttl_seconds))
    key = _text(idempotency_key) or f"{event}:{uuid.uuid4().hex}"
    notification_id = uuid.uuid4().hex
    safe_payload = payload if isinstance(payload, dict) else {}

    with LOCK:
        connection = _connect(path)
        try:
            # Expire old rows opportunistically.
            connection.execute(
                """
                UPDATE staff_notification
                SET status = ?
                WHERE status IN (?, ?)
                  AND expires_at_epoch < ?
                """,
                (STATUS_EXPIRED, STATUS_PENDING, STATUS_READ, now),
            )
            existing = _get_by_idempotency(connection, key)
            if existing:
                connection.commit()
                return {"notification": existing, "duplicate": True}

            connection.execute(
                """
                INSERT INTO staff_notification (
                    id, event_type, idempotency_key, priority, title, message,
                    sender_username, sender_display, recipient_scope, recipient_role,
                    recipient_workplace, recipient_user, patient_uuid, visit_uuid,
                    mrn, patient_name, action_href, status, created_at, created_at_epoch,
                    read_at, acked_at, acked_by, expires_at, expires_at_epoch, speak,
                    payload_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    NULL, NULL, '', ?, ?, ?,
                    ?
                )
                """,
                (
                    notification_id,
                    event,
                    key,
                    priority,
                    _text(title) or "Notification",
                    _text(message) or "New notification",
                    _text(sender_username),
                    _text(sender_display) or _text(sender_username) or "Staff",
                    recipient_scope,
                    _text(recipient_role),
                    _text(recipient_workplace),
                    _text(recipient_user),
                    _text(patient_uuid),
                    _text(visit_uuid),
                    _text(mrn),
                    _text(patient_name),
                    _text(action_href),
                    STATUS_PENDING,
                    _iso(now),
                    now,
                    _iso(expires),
                    expires,
                    1 if speak else 0,
                    _json_dumps(safe_payload),
                ),
            )
            connection.commit()
            created = _get_by_id(connection, notification_id)
            assert created is not None
            return {"notification": created, "duplicate": False}
        except sqlite3.IntegrityError:
            # Race on unique idempotency_key.
            existing = _get_by_idempotency(connection, key)
            connection.rollback()
            if existing:
                return {"notification": existing, "duplicate": True}
            raise ApiError(409, "duplicate_notification", "That notification already exists.")
        finally:
            connection.close()


def message_notification_allowed(
    *,
    conversation_id: str,
    recipient_scope: str,
    recipient_workplace: str = "",
    recipient_user: str = "",
    now: float | None = None,
    path: str | None = None,
) -> bool:
    """Limit message alerts to the first alert of a day or a three-hour window."""
    moment = now if now is not None else _now()
    utc_day_start = moment - (moment % 86400)
    cutoff = max(utc_day_start, moment - (3 * 60 * 60))
    with LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                """
                SELECT payload_json FROM staff_notification
                WHERE event_type = ?
                  AND recipient_scope = ?
                  AND recipient_workplace = ?
                  AND recipient_user = ?
                  AND created_at_epoch >= ?
                LIMIT 20
                """,
                (
                    EVENT_MESSAGE_RECEIVED,
                    _text(recipient_scope),
                    _text(recipient_workplace),
                    _text(recipient_user),
                    cutoff,
                ),
            ).fetchall()
        finally:
            connection.close()
    return not any(
        _json_loads(row["payload_json"]).get("conversationId") == _text(conversation_id)
        for row in rows
    )


DESK_ROLES = {
    "reception": {"Abikan:Reception", "Abikan:Registration"},
    "registration": {"Abikan:Reception", "Abikan:Registration"},
    "clinical": {"Abikan:Doctor"},
    "nursing": {"Abikan:Nursing"},
    "pharmacy": {"Abikan:Pharmacy"},
    "laboratory": {"Abikan:Laboratory"},
    "radiology": {"Abikan:Radiology"},
    "accountant": {"Abikan:Accountant"},
    "administration": {"Abikan:Hospital Admin"},
}
DESK_PRIVILEGES = {
    "reception": {"app:registration"},
    "registration": {"app:registration"},
    "clinical": {"app:clinical"},
    "nursing": {"app:adt"},
    "pharmacy": {"bahmni:clinical:dispense"},
    "laboratory": {"app:lab-lite"},
    "radiology": {"app:radiology-upload"},
    "accountant": {"abikan:accountant"},
    "administration": {"abikan:admin:staff"},
}


def _session_sees_nursing_alerts(user: dict[str, Any]) -> bool:
    import inpatient as ward

    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(
        ward._is_admin(user)
        or ward.ADT_PRIVILEGE in privileges
        or "Abikan:Nursing" in roles
    )


def _user_works_desk(user: dict[str, Any], workplace: str) -> bool:
    desk = "reception" if workplace == WORKPLACE_REGISTRATION else workplace
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    if roles & {"SuperAdmin", "System Developer"}:
        return bool(roles & DESK_ROLES.get(desk, set()))
    return bool(roles & DESK_ROLES.get(desk, set()) or privileges & DESK_PRIVILEGES.get(desk, set()))


def _user_may_receive(user: dict[str, Any], row: dict[str, Any]) -> bool:
    if (
        row.get("eventType") == EVENT_DEPARTMENT_ATTENTION_REQUESTED
        and _text(user.get("username")) == _text(row.get("senderUsername"))
    ):
        # A user may have access to every workplace, but never receives their
        # own attention request as a department alert.
        return False
    scope = row.get("recipientScope")
    event = _text(row.get("eventType"))
    if event in {
        EVENT_MESSAGE_RECEIVED,
        EVENT_DEPARTMENT_ATTENTION_REQUESTED,
        "department_attention_acknowledged",
    }:
        if scope == SCOPE_USER:
            return _text(user.get("username")) == _text(row.get("recipientUser"))
        if scope == SCOPE_WORKPLACE:
            return _user_works_desk(user, _text(row.get("recipientWorkplace")))
        return False
    if scope == SCOPE_USER:
        return _text(user.get("username")) == _text(row.get("recipientUser"))
    if scope == SCOPE_WORKPLACE:
        workplace = _text(row.get("recipientWorkplace"))
        if workplace in {WORKPLACE_REGISTRATION, "reception"}:
            return reception.is_registrar(user)
        if workplace == WORKPLACE_CLINICAL:
            import consultation as clinical

            return clinical.is_clinician(user)
        if workplace == WORKPLACE_NURSING:
            import inpatient as ward

            roles = set(user.get("roles") or [])
            privileges = set(user.get("privileges") or [])
            return (
                ward._is_admin(user)
                or ward.ADT_PRIVILEGE in privileges
                or "Abikan:Nursing" in roles
            )
        if workplace == WORKPLACE_PHARMACY:
            import pharmacy as dispensary

            return dispensary.is_pharmacist(user)
        role_map = {
            WORKPLACE_LABORATORY: ({"Abikan:Laboratory"}, {"app:lab-lite"}),
            WORKPLACE_RADIOLOGY: ({"Abikan:Radiology"}, {"app:radiology-upload"}),
            WORKPLACE_ACCOUNTANT: ({"Abikan:Accountant"}, {"abikan:accountant"}),
            WORKPLACE_ADMINISTRATION: (
                {"Abikan:Hospital Admin", "SuperAdmin", "System Developer"},
                {"abikan:admin:staff", "app:admin"},
            ),
        }
        accepted_roles, accepted_privileges = role_map.get(workplace, (set(), set()))
        return bool(
            set(user.get("roles") or []) & accepted_roles
            or set(user.get("privileges") or []) & accepted_privileges
        )
    if scope == SCOPE_ROLE:
        role = _text(row.get("recipientRole"))
        roles = {str(item) for item in (user.get("roles") or [])}
        return bool(role) and role in roles
    return False


def emit_visit_started(
    *,
    patient_uuid: str,
    visit_uuid: str,
    patient_name: str,
    mrn: str,
    sender_username: str,
    sender_display: str = "",
    daily_visit_number: str = "",
    request_id: str = "",
    path: str | None = None,
) -> dict[str, Any]:
    patient = _text(patient_name) or "Patient"
    visit = _text(visit_uuid)
    key = (
        f"visit_started:request:{_text(request_id)}"
        if _text(request_id)
        else f"visit_started:visit:{visit}"
    )
    message = f"{patient} is ready for consultation."
    href = f"#/doctor/patient/{_text(patient_uuid)}/visit/{visit}" if visit else f"#/doctor/patient/{_text(patient_uuid)}"
    return emit(
        event_type=EVENT_VISIT_STARTED,
        title="Patient ready",
        message=message,
        sender_username=_text(sender_username) or "reception",
        sender_display=_text(sender_display) or "Reception",
        recipient_scope=SCOPE_WORKPLACE,
        recipient_workplace=WORKPLACE_CLINICAL,
        patient_uuid=_text(patient_uuid),
        visit_uuid=visit,
        mrn=_text(mrn) or "—",
        patient_name=patient,
        action_href=href,
        priority=PRIORITY_HIGH,
        speak=False,
        ttl_seconds=VISIT_STARTED_TTL_SECONDS,
        idempotency_key=key,
        payload={"dailyVisitNumber": _text(daily_visit_number)},
        path=path,
    )


def emit_admit_requested(
    *,
    patient_uuid: str,
    visit_uuid: str,
    patient_name: str,
    mrn: str,
    sender_username: str,
    sender_display: str,
    request_id: str = "",
    path: str | None = None,
) -> dict[str, Any]:
    patient = _text(patient_name) or "Patient"
    doctor = _text(sender_display) or "Doctor"
    if not doctor.lower().startswith("dr"):
        doctor = f"Dr. {doctor}"
    visit = _text(visit_uuid)
    key = (
        f"admit_requested:request:{_text(request_id)}"
        if _text(request_id)
        else f"admit_requested:visit:{visit or _text(patient_uuid)}"
    )
    message = f"{doctor} has requested admission for {patient}."
    href = f"#/nursing/patient/{_text(patient_uuid)}" if _text(patient_uuid) else "#/nursing"
    return emit(
        event_type=EVENT_ADMIT_REQUESTED,
        title="Admission requested",
        message=message,
        sender_username=_text(sender_username),
        sender_display=doctor,
        recipient_scope=SCOPE_WORKPLACE,
        recipient_workplace=WORKPLACE_NURSING,
        patient_uuid=_text(patient_uuid),
        visit_uuid=visit,
        mrn=_text(mrn) or "—",
        patient_name=patient,
        action_href=href,
        priority=PRIORITY_URGENT,
        speak=True,
        ttl_seconds=ADMIT_REQUESTED_TTL_SECONDS,
        idempotency_key=key,
        payload={},
        path=path,
    )


def emit_nursing_treatment_started(
    *,
    patient_uuid: str,
    visit_uuid: str,
    patient_name: str,
    mrn: str,
    sender_username: str,
    sender_display: str = "Reception",
    request_id: str = "",
    path: str | None = None,
) -> dict[str, Any]:
    patient = _text(patient_name) or "Patient"
    visit = _text(visit_uuid)
    key = (
        f"nursing_treatment:request:{_text(request_id)}"
        if _text(request_id)
        else f"nursing_treatment:visit:{visit}"
    )
    return emit(
        event_type=EVENT_NURSING_TREATMENT,
        title="Nursing treatment ready",
        message=f"{patient} is ready for nursing treatment.",
        sender_username=_text(sender_username) or "reception",
        sender_display=_text(sender_display) or "Reception",
        recipient_scope=SCOPE_WORKPLACE,
        recipient_workplace=WORKPLACE_NURSING,
        patient_uuid=_text(patient_uuid),
        visit_uuid=visit,
        mrn=_text(mrn) or "—",
        patient_name=patient,
        action_href=(
            f"#/nursing/patient/{_text(patient_uuid)}/treatment/{visit}"
            if _text(patient_uuid) and visit
            else "#/nursing/treatments"
        ),
        priority=PRIORITY_HIGH,
        speak=True,
        ttl_seconds=NURSING_TREATMENT_TTL_SECONDS,
        idempotency_key=key,
        payload={},
        path=path,
    )


def emit_nursing_call_to_reception(
    *,
    patient_uuid: str,
    visit_uuid: str,
    patient_name: str,
    mrn: str,
    sender_username: str,
    sender_display: str,
    path: str | None = None,
) -> dict[str, Any]:
    patient = _text(patient_name) or "Patient"
    visit = _text(visit_uuid)
    key = f"nursing_call_reception:visit:{visit}:patient:{_text(patient_uuid)}"
    return emit(
        event_type=EVENT_NURSING_TREATMENT,
        title="Nurse needs Reception",
        message=f"Nursing is calling Reception for {patient}.",
        sender_username=_text(sender_username) or "nurse",
        sender_display=_text(sender_display) or "Nursing",
        recipient_scope=SCOPE_WORKPLACE,
        recipient_workplace=WORKPLACE_REGISTRATION,
        patient_uuid=_text(patient_uuid),
        visit_uuid=visit,
        mrn=_text(mrn) or "—",
        patient_name=patient,
        action_href=f"#/reception/record/{_text(patient_uuid)}",
        priority=PRIORITY_HIGH,
        speak=True,
        ttl_seconds=NURSING_TREATMENT_TTL_SECONDS,
        idempotency_key=key,
        payload={},
        path=path,
    )


def emit_prescription_created(
    *,
    patient_uuid: str,
    order_uuid: str,
    patient_name: str,
    mrn: str,
    sender_username: str,
    sender_display: str,
    drug_name: str = "",
    medicine_count: int = 1,
    drug_names: list[str] | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    patient = _text(patient_name) or "Patient"
    doctor = _text(sender_display) or "Doctor"
    if not doctor.lower().startswith("dr"):
        doctor = f"Dr. {doctor}"
    order = _text(order_uuid)
    count = max(1, int(medicine_count or 1))
    names = [name for name in (drug_names or []) if _text(name)]
    if count > 1:
        key = f"prescription_created:patient:{_text(patient_uuid)}:batch:{order}:{count}"
        message = f"New prescription for {patient}"
        detail = f"{doctor} · {count} medicines"
    else:
        key = f"prescription_created:order:{order}"
        message = f"New prescription for {patient}"
        detail = doctor
        if _text(drug_name):
            detail = f"{doctor} · {_text(drug_name)}"
    href = (
        f"#/pharmacy/prescription/{order}"
        if order
        else (f"#/pharmacy/patient/{_text(patient_uuid)}" if _text(patient_uuid) else "#/pharmacy")
    )
    return emit(
        event_type=EVENT_PRESCRIPTION_CREATED,
        title="New prescription",
        message=message,
        sender_username=_text(sender_username),
        sender_display=doctor,
        recipient_scope=SCOPE_WORKPLACE,
        recipient_workplace=WORKPLACE_PHARMACY,
        patient_uuid=_text(patient_uuid),
        visit_uuid="",
        mrn=_text(mrn) or "—",
        patient_name=patient,
        action_href=href,
        priority=PRIORITY_HIGH,
        speak=True,
        ttl_seconds=PRESCRIPTION_CREATED_TTL_SECONDS,
        idempotency_key=key,
        payload={
            "orderUuid": order,
            "drugName": _text(drug_name),
            "drugNames": names,
            "medicineCount": count,
            "detail": detail,
        },
        path=path,
    )


def expire_event_except(event_type: str, keep_keys: set[str], *, path: str | None = None) -> int:
    """Retire alerts for this event that are no longer in the current set."""
    event = _text(event_type)
    if not event:
        return 0
    with LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                """
                SELECT id, idempotency_key FROM staff_notification
                WHERE event_type = ? AND status IN (?, ?)
                """,
                (event, STATUS_PENDING, STATUS_READ),
            ).fetchall()
            drop = [row["id"] for row in rows if row["idempotency_key"] not in keep_keys]
            if not drop:
                return 0
            placeholders = ", ".join("?" for _ in drop)
            cursor = connection.execute(
                f"UPDATE staff_notification SET status = ? WHERE id IN ({placeholders})",
                (STATUS_EXPIRED, *drop),
            )
            connection.commit()
            return int(cursor.rowcount or 0)
        finally:
            connection.close()


def expire_idempotency_keys(keys: list[str], *, path: str | None = None) -> int:
    """Drop alerts whose dose has been given or is no longer due."""
    wanted = [key for key in (_text(item) for item in keys) if key]
    if not wanted:
        return 0
    placeholders = ", ".join("?" for _ in wanted)
    with LOCK:
        connection = _connect(path)
        try:
            cursor = connection.execute(
                f"""
                UPDATE staff_notification
                SET status = ?
                WHERE status IN (?, ?)
                  AND idempotency_key IN ({placeholders})
                """,
                (STATUS_EXPIRED, STATUS_PENDING, STATUS_READ, *wanted),
            )
            connection.commit()
            return int(cursor.rowcount or 0)
        finally:
            connection.close()


def list_for_session(
    cookie: str,
    raw_path: str = "",
    *,
    path: str | None = None,
) -> dict[str, Any]:
    core.require_session(cookie)
    user = reception.load_openmrs_user(cookie)
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    since_raw = _text((query.get("since") or [""])[0])
    since_epoch = 0.0
    if since_raw:
        try:
            since_epoch = float(since_raw)
        except ValueError:
            since_epoch = 0.0

    now = _now()
    purge_expired(path=path, now=now)
    if path is None and _session_sees_nursing_alerts(user):
        try:
            import medication_administration as mar

            mar.publish_due_dose_notifications()
        except Exception:
            pass

    with LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                """
                SELECT * FROM staff_notification
                WHERE status IN (?, ?)
                  AND expires_at_epoch >= ?
                  AND created_at_epoch >= ?
                ORDER BY created_at_epoch DESC
                LIMIT 200
                """,
                (STATUS_PENDING, STATUS_READ, now, since_epoch),
            ).fetchall()
        finally:
            connection.close()

    notifications = []
    for row in rows:
        item = _row_to_dict(row)
        if _user_may_receive(user, item):
            notifications.append(item)

    pending_count = sum(1 for item in notifications if item.get("status") == STATUS_PENDING)
    return {
        "status": "ok",
        "serverTime": str(now),
        "notifications": notifications,
        "pendingCount": pending_count,
        "activeCount": len(notifications),
    }


def _require_recipient_access(cookie: str, notification: dict[str, Any]) -> dict[str, Any]:
    core.require_session(cookie)
    user = reception.load_openmrs_user(cookie)
    if not _user_may_receive(user, notification):
        raise ApiError(403, "forbidden", "This notification is not available for this account.")
    return user


def mark_read(notification_id: str, cookie: str, *, path: str | None = None) -> dict[str, Any]:
    note_id = _text(notification_id)
    if not note_id:
        raise ApiError(422, "invalid_body", "Choose a notification.")
    purge_expired(path=path)
    with LOCK:
        connection = _connect(path)
        try:
            existing = _get_by_id(connection, note_id)
            if not existing or existing["status"] == STATUS_EXPIRED:
                raise ApiError(404, "notification_not_found", "That notification was not found or has expired.")
            if existing["expiresAtEpoch"] < _now():
                connection.execute(
                    "UPDATE staff_notification SET status = ? WHERE id = ?",
                    (STATUS_EXPIRED, note_id),
                )
                connection.commit()
                raise ApiError(404, "notification_not_found", "That notification was not found or has expired.")
            _require_recipient_access(cookie, existing)
            if existing["status"] == STATUS_ACKED:
                return {"status": "ok", "notification": existing, "duplicate": True}
            if existing["status"] == STATUS_READ:
                return {"status": "ok", "notification": existing, "duplicate": True}
            now_iso = _iso()
            connection.execute(
                "UPDATE staff_notification SET status = ?, read_at = ? WHERE id = ?",
                (STATUS_READ, now_iso, note_id),
            )
            connection.commit()
            updated = _get_by_id(connection, note_id)
            assert updated is not None
            return {"status": "ok", "notification": updated, "duplicate": False}
        finally:
            connection.close()


def acknowledge(notification_id: str, cookie: str, *, path: str | None = None) -> dict[str, Any]:
    note_id = _text(notification_id)
    if not note_id:
        raise ApiError(422, "invalid_body", "Choose a notification.")
    purge_expired(path=path)
    with LOCK:
        connection = _connect(path)
        try:
            existing = _get_by_id(connection, note_id)
            if not existing or existing["status"] == STATUS_EXPIRED:
                raise ApiError(404, "notification_not_found", "That notification was not found or has expired.")
            if existing["expiresAtEpoch"] < _now():
                connection.execute(
                    "UPDATE staff_notification SET status = ? WHERE id = ?",
                    (STATUS_EXPIRED, note_id),
                )
                connection.commit()
                raise ApiError(404, "notification_not_found", "That notification was not found or has expired.")
            user = _require_recipient_access(cookie, existing)
            if existing["status"] == STATUS_ACKED:
                return {"status": "ok", "notification": existing, "duplicate": True}
            now_iso = _iso()
            connection.execute(
                """
                UPDATE staff_notification
                SET status = ?, acked_at = ?, acked_by = ?,
                    read_at = COALESCE(read_at, ?)
                WHERE id = ?
                """,
                (STATUS_ACKED, now_iso, _text(user.get("username")), now_iso, note_id),
            )
            connection.commit()
            updated = _get_by_id(connection, note_id)
            assert updated is not None
            return {"status": "ok", "notification": updated, "duplicate": False}
        finally:
            connection.close()


def acknowledge_attention_request(
    attention_request_id: str,
    cookie: str,
    *,
    path: str | None = None,
) -> int:
    """Acknowledge the delivery alert linked to a messaging attention request."""
    target = _text(attention_request_id)
    if not target:
        return 0
    with LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                """
                SELECT id, payload_json FROM staff_notification
                WHERE event_type = ? AND status IN (?, ?)
                """,
                (EVENT_DEPARTMENT_ATTENTION_REQUESTED, STATUS_PENDING, STATUS_READ),
            ).fetchall()
        finally:
            connection.close()
    matched = 0
    for row in rows:
        if _json_loads(row["payload_json"]).get("attentionRequestId") == target:
            acknowledge(row["id"], cookie, path=path)
            matched += 1
    return matched


def find_recent_patient_called(
    *,
    visit_uuid: str,
    sender_username: str,
    within_seconds: float = PATIENT_CALLED_DEDUPE_SECONDS,
    path: str | None = None,
) -> dict[str, Any] | None:
    now = _now()
    with LOCK:
        connection = _connect(path)
        try:
            row = connection.execute(
                """
                SELECT * FROM staff_notification
                WHERE event_type = ?
                  AND visit_uuid = ?
                  AND sender_username = ?
                  AND status IN (?, ?)
                  AND created_at_epoch >= ?
                ORDER BY created_at_epoch DESC
                LIMIT 1
                """,
                (
                    EVENT_PATIENT_CALLED,
                    visit_uuid,
                    sender_username,
                    STATUS_PENDING,
                    STATUS_READ,
                    now - within_seconds,
                ),
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            connection.close()


def expire_patient_event(
    patient_uuid: str,
    event_type: str,
    *,
    path: str | None = None,
) -> int:
    """Drop a staff alert after the ward action it describes is no longer pending."""
    patient = _text(patient_uuid)
    event = _text(event_type)
    if not patient or not event:
        return 0
    with LOCK:
        connection = _connect(path)
        try:
            cursor = connection.execute(
                """
                UPDATE staff_notification
                SET status = ?
                WHERE patient_uuid = ?
                  AND event_type = ?
                  AND status IN (?, ?)
                """,
                (STATUS_EXPIRED, patient, event, STATUS_PENDING, STATUS_READ),
            )
            connection.commit()
            return int(cursor.rowcount or 0)
        finally:
            connection.close()


def reset_for_tests(path: str | None = None) -> None:
    with LOCK:
        connection = _connect(path)
        try:
            connection.execute("DELETE FROM staff_notification")
            connection.commit()
        finally:
            connection.close()
