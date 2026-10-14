"""Staff attendance / work-log service.

OpenMRS remains the staff identity source. Staff enter a unique attendance code
on the shared terminal. This module records one sign-in/sign-out session per
hospital local day and never trusts a browser timestamp.
"""

from __future__ import annotations

import hmac
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import admin_audit
import attendance_store as store
import hospital_admin as administration
import staff_hr as directory
from server import ApiError

DEFAULT_TIMEZONE = "Africa/Lagos"
DEFAULT_TERMINAL_NAME = "Staff Log Terminal"
AUTH_STAFF_CODE = "staff_code"
STATUS_NOT_SIGNED_IN = "NOT_SIGNED_IN"
STATUS_SIGNED_IN = store.STATUS_SIGNED_IN
STATUS_SIGNED_OUT = store.STATUS_SIGNED_OUT
STATUS_LABELS = {
    STATUS_NOT_SIGNED_IN: "Not signed in",
    STATUS_SIGNED_IN: "Signed in",
    STATUS_SIGNED_OUT: "Signed out",
}
CODE_ACTION_LABELS = {
    "ADMIN_ATTENDANCE_CODE_SET": "Set staff attendance code",
    "ADMIN_ATTENDANCE_CODE_REPLACE": "Replaced staff attendance code",
}
CODE_PATTERN = re.compile(r"^[A-Z0-9]{4,8}$")
UNKNOWN_CODE_MESSAGE = "That staff code is not recognized."
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def hospital_timezone_name() -> str:
    name = str(os.environ.get("ABIKAN_HOSPITAL_TIMEZONE") or DEFAULT_TIMEZONE).strip()
    return name or DEFAULT_TIMEZONE


def hospital_zone() -> ZoneInfo:
    try:
        return ZoneInfo(hospital_timezone_name())
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def deployment_environment() -> str:
    return str(os.environ.get("ABIKAN_ENVIRONMENT") or "").strip().lower()


def server_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def local_parts(moment: datetime | None = None) -> tuple[datetime, str, str, str]:
    utc = as_utc(moment or server_now())
    local = utc.astimezone(hospital_zone())
    return (
        utc,
        local.date().isoformat(),
        local.strftime("%H:%M:%S"),
        format_display_date(local.date()),
    )


def format_display_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def greeting_for(moment: datetime | None = None) -> str:
    local = as_utc(moment or server_now()).astimezone(hospital_zone())
    hour = local.hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def terminal_name(body: dict[str, Any] | None = None, headers: Any = None) -> str:
    requested = ""
    if isinstance(body, dict):
        requested = str(body.get("terminalName") or body.get("terminal") or "").strip()
    if not requested and headers is not None:
        requested = str(headers.get("X-Hospital EMR-Terminal-Name") or "").strip()
    configured = str(os.environ.get("ABIKAN_ATTENDANCE_TERMINAL_NAME") or "").strip()
    value = requested or configured or DEFAULT_TERMINAL_NAME
    return value[:80]


def terminal_id(body: dict[str, Any] | None = None, headers: Any = None) -> str:
    requested = ""
    if isinstance(body, dict):
        requested = str(body.get("terminalId") or "").strip()
    if not requested and headers is not None:
        requested = str(headers.get("X-Hospital EMR-Terminal-Id") or "").strip()
    return (requested or "staff-log")[:80]


def _header_secret(headers: Any) -> str:
    if headers is None:
        return ""
    return str(headers.get("X-Hospital EMR-Terminal-Key") or "").strip()


def _configured_terminal_secret() -> str:
    return str(os.environ.get("ABIKAN_ATTENDANCE_TERMINAL_SECRET") or "").strip()


def _secrets_match(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    if len(provided.encode("utf-8")) != len(expected.encode("utf-8")):
        return False
    return hmac.compare_digest(provided, expected)


def authorize_terminal(headers: Any, cookie: str) -> dict[str, Any]:
    secret = _configured_terminal_secret()
    provided = _header_secret(headers)
    env = deployment_environment()
    if secret and _secrets_match(provided, secret):
        return {"actor": "terminal", "username": "terminal"}
    if env in {"development", "test"} and (
        not secret or provided == "development-terminal" or not provided
    ):
        return {"actor": "terminal", "username": "terminal"}
    if cookie:
        try:
            user = administration.require_hospital_admin(cookie)
            return {
                "actor": "admin",
                "username": str(user.get("username") or "admin"),
                "user": user,
            }
        except ApiError:
            pass
    if env == "production" and not secret:
        raise ApiError(503, "terminal_unconfigured", "Staff log is not configured.")
    raise ApiError(401, "unauthenticated", "This terminal is not authorized.")


def workplace_snapshot(staff: dict[str, Any]) -> tuple[str, str]:
    preferred = staff.get("preferredDepartment") or {}
    if isinstance(preferred, dict) and preferred.get("label"):
        return str(preferred.get("id") or ""), str(preferred.get("label") or "")
    departments = staff.get("departments") or []
    if departments and isinstance(departments[0], dict) and departments[0].get("label"):
        return str(departments[0].get("id") or ""), str(departments[0].get("label") or "")
    category = str(staff.get("staffCategory") or "")
    label = str(staff.get("staffCategoryLabel") or "")
    if category == "hospital_admin" or staff.get("accountType") == "hospital_administrator":
        return "administration", "Administration"
    if label:
        return category, label
    return "", "Workplace not set"


def staff_snapshot(staff_id: str) -> dict[str, Any]:
    person_uuid, user = directory.resolve_staff(staff_id)
    person = directory.load_person(person_uuid)
    values = directory._attribute_values(person)
    category = values.get(directory.ATTR_CATEGORY) or (
        directory.category_from_user(user) if user else ""
    )
    employment = values.get(directory.ATTR_EMPLOYMENT, "")
    if category == "clinical" and not employment:
        employment = "external"
    display = str(person.get("display") or (user or {}).get("displayName") or "Staff member")
    staff = directory.public_staff_fields(
        person_uuid=person_uuid,
        user=user,
        category=category,
        employment_type=employment,
        display_name=display,
    )
    workplace_id, workplace_label = workplace_snapshot(staff)
    staff["workplaceId"] = workplace_id
    staff["workplaceLabel"] = workplace_label
    return staff


def public_staff_card(staff: dict[str, Any]) -> dict[str, Any]:
    return {
        "personUuid": staff.get("personUuid") or "",
        "userUuid": staff.get("userUuid") or "",
        "username": staff.get("username") or "",
        "displayName": staff.get("displayName") or "Staff member",
        "workplaceId": staff.get("workplaceId") or "",
        "workplaceLabel": staff.get("workplaceLabel") or "Workplace not set",
    }


def terminal_config() -> dict[str, Any]:
    utc, local_date, local_time, display_date = local_parts()
    payload = {
        "status": "ok",
        "title": "Staff Log",
        "prompt": "Enter your staff code.",
        "timezone": hospital_timezone_name(),
        "localDate": local_date,
        "localTime": local_time,
        "displayDate": display_date,
        "greeting": greeting_for(utc),
        "terminalName": terminal_name(),
    }
    if deployment_environment() in {"development", "test"} and not _configured_terminal_secret():
        payload["developmentTerminalKey"] = "development-terminal"
    return payload


def normalize_staff_code(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def parse_staff_code(value: Any) -> str:
    code = normalize_staff_code(value)
    if not CODE_PATTERN.fullmatch(code):
        raise ApiError(422, "invalid_staff_code", "Enter a valid staff code.")
    return code


def _requested_code(body: dict[str, Any]) -> str:
    return parse_staff_code(body.get("code") or body.get("staffCode") or "")


def public_session(
    row: dict[str, Any] | None,
    *,
    include_photo_link: bool = False,
) -> dict[str, Any] | None:
    if not row:
        return None
    status = str(row.get("status") or STATUS_NOT_SIGNED_IN)
    payload = {
        "id": row["id"],
        "personUuid": row["personUuid"],
        "userUuid": row.get("userUuid") or "",
        "username": row.get("username") or "",
        "displayName": row.get("displayName") or "Staff member",
        "workplaceId": row.get("workplaceId") or "",
        "workplaceLabel": row.get("workplaceLabel") or "Workplace not set",
        "localDate": row.get("localDate") or "",
        "status": status,
        "statusLabel": STATUS_LABELS.get(status, status),
        "signInAt": row.get("signInAt") or "",
        "signInLocalTime": row.get("signInLocalTime") or "",
        "signOutAt": row.get("signOutAt") or "",
        "signOutLocalTime": row.get("signOutLocalTime") or "",
        "authenticationMethod": row.get("authenticationMethod") or AUTH_STAFF_CODE,
        "terminalName": row.get("terminalName") or "",
        "createdAt": row.get("createdAt") or "",
        "createdBy": row.get("createdBy") or "",
        "hasPhoto": bool(row.get("hasPhoto") or row.get("signInPhoto")),
    }
    if include_photo_link and payload["hasPhoto"]:
        payload["photoHref"] = f"/openmrs/abikan-api/admin/log/{row['id']}/photo"
    return payload


def _action_payload(
    *,
    message: str,
    staff: dict[str, Any],
    session: dict[str, Any],
    already_recorded: bool,
    display_date: str,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "message": message,
        "alreadyRecorded": already_recorded,
        "attendanceStatus": session.get("status") or STATUS_NOT_SIGNED_IN,
        "staff": public_staff_card(staff),
        "session": public_session(session),
        "displayDate": display_date,
        "timezone": hospital_timezone_name(),
    }


def _unknown_code() -> None:
    raise ApiError(401, "code_unknown", UNKNOWN_CODE_MESSAGE)


def _purge_old_photos() -> None:
    store.purge_expired_photos(local_parts()[1])


def _required_sign_in_photo(body: dict[str, Any]) -> tuple[bytes, str]:
    raw = body.get("photo") or ""
    if not str(raw).strip():
        raise ApiError(422, "photo_required", "Take a photo to sign in.")
    try:
        return store.decode_sign_in_photo(raw)
    except ValueError as error:
        if str(error) == "photo too large":
            raise ApiError(422, "photo_too_large", "That photo is too large. Try again.") from error
        raise ApiError(422, "photo_required", "Take a photo to sign in.") from error


def _resolve_staff_from_code(
    body: dict[str, Any],
    throttle_key: str,
    now: datetime,
) -> dict[str, Any]:
    store.check_throttle(throttle_key, now)
    code = _requested_code(body)
    matched = store.lookup_code(code)
    if not matched:
        store.record_failure(throttle_key, now)
        _unknown_code()
    try:
        staff = staff_snapshot(matched["personUuid"])
    except ApiError:
        store.record_failure(throttle_key, now)
        _unknown_code()
    store.clear_failures(throttle_key)
    return staff


def lookup_status(
    body: dict[str, Any],
    headers: Any,
    cookie: str,
    throttle_key: str = "",
) -> dict[str, Any]:
    authorize_terminal(headers, cookie)
    _purge_old_photos()
    utc, local_date, _, display_date = local_parts()
    staff = _resolve_staff_from_code(body, throttle_key or "terminal", utc)
    existing = store.get_session_for_person_date(staff["personUuid"], local_date)
    if not existing:
        status = STATUS_NOT_SIGNED_IN
        action = "SIGN_IN"
        message = "Sign in to start today."
    elif existing["status"] == STATUS_SIGNED_OUT:
        status = STATUS_SIGNED_OUT
        action = ""
        message = "Attendance completed for today"
    else:
        status = STATUS_SIGNED_IN
        action = "SIGN_OUT"
        message = "You are signed in."
    return {
        "status": "ok",
        "attendanceStatus": status,
        "statusLabel": STATUS_LABELS[status],
        "availableAction": action,
        "message": message,
        "staff": public_staff_card(staff),
        "session": public_session(existing),
        "displayDate": display_date,
        "timezone": hospital_timezone_name(),
    }


def sign_in(
    body: dict[str, Any],
    headers: Any,
    cookie: str,
    throttle_key: str = "",
) -> dict[str, Any]:
    actor = authorize_terminal(headers, cookie)
    _purge_old_photos()
    utc, local_date, local_time, display_date = local_parts()
    staff = _resolve_staff_from_code(body, throttle_key or "terminal", utc)
    existing = store.get_session_for_person_date(staff["personUuid"], local_date)
    if existing:
        if existing["status"] == STATUS_SIGNED_OUT:
            return _action_payload(
                message="Attendance completed for today",
                staff=staff,
                session=existing,
                already_recorded=True,
                display_date=display_date,
            )
        return _action_payload(
            message="Already signed in today",
            staff=staff,
            session=existing,
            already_recorded=True,
            display_date=display_date,
        )
    photo_bytes, suffix = _required_sign_in_photo(body)
    workplace_id, workplace_label = workplace_snapshot(staff)
    session_id = store.new_id()
    photo_name = store.save_sign_in_photo(
        session_id=session_id,
        local_date=local_date,
        data=photo_bytes,
        suffix=suffix,
    )
    try:
        created = store.insert_session(
            {
                "id": session_id,
                "person_uuid": staff["personUuid"],
                "user_uuid": staff.get("userUuid") or "",
                "username": staff.get("username") or "",
                "display_name": staff.get("displayName") or "Staff member",
                "workplace_id": workplace_id,
                "workplace_label": workplace_label,
                "local_date": local_date,
                "status": STATUS_SIGNED_IN,
                "sign_in_at": store.utc_stamp(utc),
                "sign_in_local_time": local_time,
                "authentication_method": AUTH_STAFF_CODE,
                "terminal_id": terminal_id(body, headers),
                "terminal_name": terminal_name(body, headers),
                "created_by": actor.get("username") or "terminal",
                "sign_in_photo": photo_name,
            }
        )
    except sqlite3.IntegrityError:
        try:
            (store.photos_root() / photo_name).unlink(missing_ok=True)
        except OSError:
            pass
        created = store.get_session_for_person_date(staff["personUuid"], local_date)
        if not created:
            raise
        if created["status"] == STATUS_SIGNED_OUT:
            return _action_payload(
                message="Attendance completed for today",
                staff=staff,
                session=created,
                already_recorded=True,
                display_date=display_date,
            )
        return _action_payload(
            message="Already signed in today",
            staff=staff,
            session=created,
            already_recorded=True,
            display_date=display_date,
        )
    return _action_payload(
        message="Signed in successfully",
        staff=staff,
        session=created,
        already_recorded=False,
        display_date=display_date,
    )


def sign_out(
    body: dict[str, Any],
    headers: Any,
    cookie: str,
    throttle_key: str = "",
) -> dict[str, Any]:
    actor = authorize_terminal(headers, cookie)
    utc, local_date, local_time, display_date = local_parts()
    staff = _resolve_staff_from_code(body, throttle_key or "terminal", utc)
    existing = store.get_session_for_person_date(staff["personUuid"], local_date)
    if not existing:
        raise ApiError(409, "sign_in_required", "Sign in first today.")
    if existing["status"] == STATUS_SIGNED_OUT:
        return _action_payload(
            message="Attendance completed for today",
            staff=staff,
            session=existing,
            already_recorded=True,
            display_date=display_date,
        )
    completed = store.complete_session(
        existing["id"],
        sign_out_at=store.utc_stamp(utc),
        sign_out_local_time=local_time,
        signed_out_by=actor.get("username") or "terminal",
    ) or existing
    return _action_payload(
        message="Attendance completed for today",
        staff=staff,
        session=completed,
        already_recorded=False,
        display_date=display_date,
    )


def _query_map(raw_path: str) -> dict[str, str]:
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    return {key: (values[0] if values else "") for key, values in query.items()}


def _requested_date(query: dict[str, str]) -> str:
    value = str(query.get("date") or "").strip()
    if not value:
        return local_parts()[1]
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ApiError(422, "invalid_date", "Choose a valid date.") from error
    return value


def _requested_status(query: dict[str, str]) -> str:
    value = str(query.get("status") or "").strip().upper().replace(" ", "_")
    if not value:
        return ""
    if value not in {STATUS_SIGNED_IN, STATUS_SIGNED_OUT}:
        raise ApiError(422, "invalid_status", "Choose a valid attendance status.")
    return value


def list_sessions(cookie: str, raw_path: str) -> dict[str, Any]:
    administration.require_hospital_admin(cookie)
    _purge_old_photos()
    query = _query_map(raw_path)
    local_date = _requested_date(query)
    try:
        limit = int(query.get("limit") or 200)
        offset = int(query.get("offset") or 0)
    except ValueError as error:
        raise ApiError(422, "invalid_page", "Choose a valid page.") from error
    rows, total = store.search_sessions(
        local_date=local_date,
        query=str(query.get("q") or query.get("search") or query.get("staff") or ""),
        workplace_id=str(query.get("department") or query.get("workplace") or "").strip(),
        status=_requested_status(query),
        person_uuid=str(query.get("personUuid") or "").strip(),
        limit=limit,
        offset=offset,
    )
    utc, today, _, display_date = local_parts()
    selected = datetime.strptime(local_date, "%Y-%m-%d").date()
    previous = (selected - timedelta(days=1)).isoformat()
    nxt = (selected + timedelta(days=1)).isoformat()
    return {
        "status": "ok",
        "date": local_date,
        "displayDate": format_display_date(selected),
        "today": today,
        "previousDate": previous,
        "nextDate": nxt,
        "timezone": hospital_timezone_name(),
        "total": total,
        "limit": max(1, min(limit, 500)),
        "offset": max(0, offset),
        "sessions": [public_session(row, include_photo_link=True) for row in rows],
        "departments": [
            {"id": row["id"], "label": row["label"]} for row in administration.DEPARTMENTS
        ]
        + [{"id": "administration", "label": "Administration"}],
        "statuses": [
            {"id": STATUS_SIGNED_IN, "label": STATUS_LABELS[STATUS_SIGNED_IN]},
            {"id": STATUS_SIGNED_OUT, "label": STATUS_LABELS[STATUS_SIGNED_OUT]},
        ],
        "serverTime": store.utc_stamp(utc),
        "displayDateLong": display_date,
    }


def list_events(cookie: str, raw_path: str) -> dict[str, Any]:
    return list_sessions(cookie, raw_path)


def session_photo(session_id: str, cookie: str) -> tuple[bytes, str, str]:
    administration.require_hospital_admin(cookie)
    _purge_old_photos()
    today = local_parts()[1]
    row = store.get_session(session_id)
    relative = str((row or {}).get("signInPhoto") or "")
    if not row or not relative or row.get("localDate") != today:
        raise ApiError(404, "photo_not_found", "This sign-in photo is no longer kept.")
    try:
        data, content_type = store.read_sign_in_photo(relative)
    except FileNotFoundError as error:
        raise ApiError(404, "photo_not_found", "This sign-in photo is no longer kept.") from error
    return data, content_type, "sign-in.jpg"


def daily_summaries(cookie: str, raw_path: str) -> dict[str, Any]:
    payload = list_sessions(cookie, raw_path)
    return {
        "status": "ok",
        "date": payload["date"],
        "displayDate": payload["displayDate"],
        "timezone": payload["timezone"],
        "sessions": payload["sessions"],
        "summaries": payload["sessions"],
        "total": payload["total"],
    }


def _code_public(person_uuid: str) -> dict[str, Any]:
    assigned = store.get_code_for_person(person_uuid)
    audit = store.list_code_audit(person_uuid)
    return {
        "hasCode": bool(assigned),
        "code": assigned["code"] if assigned else "",
        "createdAt": assigned["createdAt"] if assigned else "",
        "createdBy": assigned["createdBy"] if assigned else "",
        "replacedAt": assigned["replacedAt"] if assigned else "",
        "replacedBy": assigned["replacedBy"] if assigned else "",
        "audit": [
            {
                "id": row["id"],
                "occurredAt": row["occurredAt"],
                "action": row["action"],
                "actionLabel": CODE_ACTION_LABELS.get(row["action"], row["action"]),
                "actorUsername": row["actorUsername"],
            }
            for row in audit
        ],
    }


def staff_attendance_code(staff_id: str, cookie: str) -> dict[str, Any]:
    administration.require_hospital_admin(cookie)
    staff = staff_snapshot(staff_id)
    return {
        "status": "ok",
        "staff": public_staff_card(staff),
        "attendanceCode": _code_public(staff["personUuid"]),
    }


def _record_admin_code(
    *,
    actor: dict[str, Any],
    staff: dict[str, Any],
    action: str,
    had_code: bool,
    request_id: str,
) -> None:
    store.insert_code_audit(
        {
            "action": action,
            "person_uuid": staff["personUuid"],
            "actor_uuid": str(actor.get("uuid") or ""),
            "actor_username": str(actor.get("username") or ""),
            "details": {"hasCode": True},
        }
    )
    admin_audit.record_admin_event(
        actor=actor,
        target_user_uuid=str(staff.get("userUuid") or ""),
        target_username=str(staff.get("username") or staff.get("displayName") or ""),
        action=action,
        previous_state={"hasCode": had_code},
        new_state={"hasCode": True},
        details={"personUuid": staff["personUuid"]},
        outcome="success",
        request_id=request_id,
    )


def set_staff_attendance_code(staff_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = administration.require_hospital_admin(cookie)
    administration.reject_arbitrary_authority(body)
    staff = staff_snapshot(staff_id)
    existing = store.get_code_for_person(staff["personUuid"])
    replace = bool(body.get("replace"))
    requested = normalize_staff_code(body.get("code") or body.get("staffCode") or "")
    if requested:
        code = parse_staff_code(requested)
    else:
        try:
            code = store.generate_unique_code()
        except RuntimeError as error:
            raise ApiError(503, "code_unavailable", "A staff code could not be created. Try again.") from error
    if existing and existing["code"] == code:
        return {
            "status": "ok",
            "message": "Staff code is unchanged.",
            "staff": public_staff_card(staff),
            "attendanceCode": _code_public(staff["personUuid"]),
        }
    if existing and not replace:
        raise ApiError(409, "code_exists", "This staff member already has a staff code. Replace it instead.")
    try:
        store.upsert_code(
            person_uuid=staff["personUuid"],
            code_normalized=code,
            actor_username=str(actor.get("username") or ""),
            replace=True,
        )
    except sqlite3.IntegrityError as error:
        raise ApiError(409, "code_in_use", "That staff code is already in use.") from error
    action = "ADMIN_ATTENDANCE_CODE_REPLACE" if existing else "ADMIN_ATTENDANCE_CODE_SET"
    _record_admin_code(
        actor=actor,
        staff=staff,
        action=action,
        had_code=bool(existing),
        request_id=str(body.get("requestId") or ""),
    )
    return {
        "status": "ok",
        "message": "Staff code replaced." if existing else "Staff code created.",
        "staff": public_staff_card(staff),
        "attendanceCode": _code_public(staff["personUuid"]),
    }
