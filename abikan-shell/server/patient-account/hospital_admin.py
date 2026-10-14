"""Hospital Admin staff accounts and approved department access.

OpenMRS remains the identity, role, and provider source of truth. This module
exposes only the seven approved Hospital EMR departments. It never accepts raw roles
or privileges from the browser.

Writes use the acting Admin's OpenMRS session so existing audit metadata keeps
the real actor. Initial passwords pass directly to OpenMRS during user creation;
they are never stored, logged, returned, or cached by Hospital EMR.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import server as core
import admin_audit
from admin_audit import finish_admin_event, record_admin_event, start_admin_event

ApiError = core.ApiError
OPENMRS_URL = core.OPENMRS_URL
OPENMRS_ADMIN_USER = os.environ.get("ABIKAN_OPENMRS_ADMIN_USER", "")
OPENMRS_ADMIN_PASSWORD = os.environ.get("ABIKAN_OPENMRS_ADMIN_PASSWORD", "")
ADMIN_ROLES = {"SuperAdmin", "System Developer"}
HOSPITAL_ADMIN_PRIVILEGE = "abikan:admin:staff"
ANALYTICS_PRIVILEGE = "abikan:admin:analytics"
AUDIT_READ_PRIVILEGE = "abikan:admin:audit-read"
HOSPITAL_ADMIN_ROLE_NAME = "Abikan:Hospital Admin"
SUPERADMIN_ROLE_NAME = "SuperAdmin"
STAFF_AUDIT_ACTION_LABELS = {
    "ADMIN_CREATE_USER": "Created staff account",
    "ADMIN_CREATE_HOSPITAL_ADMIN": "Created hospital administrator",
    "ADMIN_DISABLE_USER": "Disabled staff account",
    "ADMIN_ENABLE_USER": "Enabled staff account",
    "ADMIN_CHANGE_PASSWORD": "Changed sign-in password",
    "ADMIN_UPDATE_DEPARTMENTS": "Updated department access",
    "ADMIN_ASSIGN_DEPARTMENT": "Assigned department access",
    "ADMIN_REMOVE_DEPARTMENT": "Removed department access",
    "ADMIN_PROVIDER_LINK": "Linked clinical profile",
    "ADMIN_CREATE_STAFF_PROFILE": "Created staff profile",
    "ADMIN_UPDATE_STAFF_PROFILE": "Updated staff profile",
    "ADMIN_UPLOAD_STAFF_PHOTO": "Updated profile picture",
    "ADMIN_UPLOAD_APPOINTMENT_LETTER": "Updated appointment letter",
    "ADMIN_EXPORT_DATA": "Generated a data export",
    "ADMIN_EXPORT_DELETE": "Deleted an export file",
    "ADMIN_UPDATE_PATIENT_LIFE_STATUS": "Updated patient life status",
    "ADMIN_ATTENDANCE_CODE_SET": "Set staff attendance code",
    "ADMIN_ATTENDANCE_CODE_REPLACE": "Replaced staff attendance code",
    "ADMIN_BIOMETRIC_ENROLL": "Registered fingerprint",
    "ADMIN_BIOMETRIC_REPLACE": "Replaced fingerprint",
    "ADMIN_BIOMETRIC_DISABLE": "Disabled fingerprint",
}
WORKPLACE_PROPERTY = "abikan.workplace"
TECHNICAL_ROLES = {"SuperAdmin", "System Developer", "Privilege Level: Full"}
TECHNICAL_SUPERADMIN_ROLES = {"SuperAdmin", "System Developer"}
ANCILLARY_ROLE_BY_DEPARTMENT = {"pharmacy": "Abikan:Pharmacy Inventory"}

DEPARTMENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "clinical",
        "label": "Clinical",
        "roleName": "Abikan:Doctor",
        "roleLabel": "Doctor",
        "providerRequired": True,
    },
    {
        "id": "nursing",
        "label": "Nursing",
        "roleName": "Abikan:Nursing",
        "roleLabel": "Nurse",
        "providerRequired": True,
    },
    {
        "id": "reception",
        "label": "Reception",
        "roleName": "Abikan:Reception",
        "compatibilityRoles": ["Abikan:Registration"],
        "roleLabel": "Receptionist",
        "providerRequired": False,
    },
    {
        "id": "laboratory",
        "label": "Laboratory",
        "roleName": "Abikan:Laboratory",
        "roleLabel": "Laboratory Staff",
        "providerRequired": False,
    },
    {
        "id": "radiology",
        "label": "Radiology",
        "roleName": "Abikan:Radiology",
        "roleLabel": "Radiologist",
        "providerRequired": True,
    },
    {
        "id": "pharmacy",
        "label": "Pharmacy",
        "roleName": "Abikan:Pharmacy",
        "roleLabel": "Pharmacist",
        "providerRequired": False,
    },
    {
        "id": "accountant",
        "label": "Accountant",
        "roleName": "Abikan:Accountant",
        "roleLabel": "Accountant",
        "providerRequired": False,
    },
)
DEPARTMENT_BY_ID = {row["id"]: row for row in DEPARTMENTS}
PRIMARY_ROLE_NAMES = {str(row["roleName"]) for row in DEPARTMENTS}
COMPATIBILITY_ROLE_NAMES = {
    str(role)
    for row in DEPARTMENTS
    for role in (row.get("compatibilityRoles") or [])
}
ANCILLARY_ROLE_NAMES = set(ANCILLARY_ROLE_BY_DEPARTMENT.values())
DEPARTMENT_ROLE_NAMES = PRIMARY_ROLE_NAMES | COMPATIBILITY_ROLE_NAMES | ANCILLARY_ROLE_NAMES
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
CREATE_LOCK = threading.Lock()
CREATE_RESULTS: dict[str, dict[str, Any]] = {}
ARBITRARY_AUTHORITY_KEYS = {"privileges", "privilege", "roles", "role"}


ASSIGNMENT_PERMISSION_MESSAGE = (
    "Department access could not be updated. "
    "The administrator account does not have permission to assign this role."
)


def _openmrs_error_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("error") if isinstance(payload.get("error"), dict) else payload
    parts: list[str] = []
    if isinstance(detail, dict):
        for key in ("message", "code", "detail"):
            value = detail.get(key)
            if value:
                parts.append(str(value))
        global_errors = detail.get("globalErrors") or payload.get("globalErrors") or []
        if isinstance(global_errors, list):
            parts.extend(str(item) for item in global_errors if item)
    return " ".join(parts)


def _is_role_assignment_denied(message: str) -> bool:
    lowered = message.lower()
    return (
        "in order to assign" in lowered
        or "privilege required" in lowered
        or "must have privilege" in lowered
        or "does not have privilege" in lowered
    )


def _openmrs_error(error: HTTPError, fallback: str) -> ApiError:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    message = _openmrs_error_text(payload)
    if error.code == 401:
        return ApiError(401, "unauthenticated", "Sign in required.")
    if _is_role_assignment_denied(message):
        return ApiError(403, "role_assignment_unauthorized", ASSIGNMENT_PERMISSION_MESSAGE)
    password_problem = _password_policy_message(message)
    if password_problem:
        return ApiError(422, "password_rejected", password_problem)
    if error.code == 403:
        return ApiError(
            403,
            "admin_permission_missing",
            "This administrator is not allowed to manage staff accounts.",
        )
    if error.code == 404:
        return ApiError(409, "invalid_role", "Department access could not be updated. That role is not available.")
    if message and "already" in message.lower() and "user" in message.lower():
        return ApiError(409, "duplicate_username", "That username is already in use.")
    return ApiError(502, "openmrs_error", fallback)


def _password_policy_message(message: str) -> str:
    lowered = message.lower()
    if not lowered:
        return ""
    if "upper" in lowered and "lower" in lowered:
        return (
            "The sign-in password must include both uppercase and lowercase letters, "
            "plus at least one number."
        )
    if "digit" in lowered or "number" in lowered:
        return "The sign-in password must include at least one number."
    if "username" in lowered and "password" in lowered:
        return "The sign-in password cannot match the username."
    if "password" in lowered and (
        "invalid" in lowered or "choose" in lowered or "require" in lowered or "contain" in lowered
    ):
        return (
            "The sign-in password does not meet the hospital sign-in rules. "
            "Use at least 8 characters with uppercase, lowercase, and a number."
        )
    return ""


def _admin_openmrs_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    fallback: str = "Staff accounts could not be loaded.",
) -> Any:
    if not OPENMRS_ADMIN_USER or not OPENMRS_ADMIN_PASSWORD:
        raise ApiError(503, "admin_service_config", "Staff administration is unavailable.")
    token = base64.b64encode(
        f"{OPENMRS_ADMIN_USER}:{OPENMRS_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {token}",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(f"{OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=40) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        raise _openmrs_error(error, fallback) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", fallback) from error


def _results(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("results") if isinstance(payload, dict) else payload
    return [row for row in (rows or []) if isinstance(row, dict)]


def is_hospital_admin(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & ADMIN_ROLES) or HOSPITAL_ADMIN_PRIVILEGE in privileges


def is_technical_superadmin(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    return bool(roles & TECHNICAL_SUPERADMIN_ROLES)


def is_hospital_administrator_account(role_names: list[str]) -> bool:
    return HOSPITAL_ADMIN_ROLE_NAME in role_names


def require_hospital_admin(cookie: str) -> dict[str, Any]:
    core.require_session(cookie)
    import accountant as cashier

    user = cashier.load_openmrs_user(cookie)
    if is_hospital_admin(user):
        return user
    raise ApiError(403, "forbidden", "This action requires Hospital Administration.")


def require_admin_audit_read(cookie: str) -> dict[str, Any]:
    user = require_hospital_admin(cookie)
    if is_technical_superadmin(user):
        return user
    privileges = set(user.get("privileges") or [])
    if AUDIT_READ_PRIVILEGE not in privileges:
        raise ApiError(403, "forbidden", "This action requires Hospital Administration.")
    return user


def _audit_state_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    departments = value.get("departments")
    enabled = value.get("enabled")
    summary: dict[str, Any] = {}
    if isinstance(departments, list):
        summary["departments"] = [str(item) for item in departments]
    if isinstance(enabled, bool):
        summary["enabled"] = enabled
    account_type = value.get("accountType") or value.get("account_type")
    if account_type:
        summary["accountType"] = str(account_type)
    if "alive" in value:
        summary["alive"] = bool(value.get("alive"))
    if value.get("deathDate"):
        summary["deathDate"] = str(value.get("deathDate"))
    return summary


def build_staff_audit(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_admin_audit_read(cookie)
    params = query or {}
    try:
        limit = int((params.get("limit") or ["100"])[0] or 100)
        offset = int((params.get("offset") or ["0"])[0] or 0)
    except ValueError as error:
        raise ApiError(422, "invalid_query", "Enter a valid page size.") from error
    payload = admin_audit.list_admin_events(limit=limit, offset=offset)
    events = []
    for row in payload["events"]:
        action = str(row.get("action") or "")
        events.append(
            {
                "eventId": row.get("event_id"),
                "occurredAt": row.get("occurred_at"),
                "actorUsername": row.get("actor_username") or "",
                "targetUsername": row.get("target_username") or "",
                "action": action,
                "actionLabel": STAFF_AUDIT_ACTION_LABELS.get(action, "Staff administration change"),
                "outcome": row.get("outcome") or "",
                "errorCode": row.get("error_code") or "",
                "requestId": row.get("request_id") or "",
                "previous": _audit_state_summary(row.get("previous_state")),
                "current": _audit_state_summary(row.get("new_state")),
            }
        )
    return {
        "status": "ok",
        "total": payload["total"],
        "limit": payload["limit"],
        "offset": payload["offset"],
        "events": events,
    }


def validate_departments(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ApiError(422, "invalid_department", "Choose an approved department.")
    departments: list[str] = []
    for item in value:
        department_id = str(item or "").strip().lower()
        if department_id not in DEPARTMENT_BY_ID:
            raise ApiError(422, "invalid_department", "Choose an approved department.")
        if department_id not in departments:
            departments.append(department_id)
    if not departments and not allow_empty:
        raise ApiError(422, "department_required", "Choose at least one department.")
    return departments


def reject_arbitrary_authority(body: dict[str, Any]) -> None:
    keys = {str(key).strip().lower() for key in body}
    if keys & ARBITRARY_AUTHORITY_KEYS:
        raise ApiError(
            422,
            "arbitrary_privilege_rejected",
            "Department access uses approved departments only.",
        )


def provider_required(departments: list[str]) -> bool:
    return any(bool(DEPARTMENT_BY_ID[item]["providerRequired"]) for item in departments)


def _role_names(user: dict[str, Any]) -> list[str]:
    return [
        str(role.get("name") or "").strip()
        for role in (user.get("roles") or [])
        if isinstance(role, dict) and role.get("name")
    ]


def _departments_for_roles(role_names: list[str]) -> list[dict[str, Any]]:
    names = set(role_names)
    rows = []
    for department in DEPARTMENTS:
        accepted = {department["roleName"], *(department.get("compatibilityRoles") or [])}
        if names & accepted or ANCILLARY_ROLE_BY_DEPARTMENT.get(department["id"]) in names:
            rows.append(department)
    return rows


def _provider_rows_by_person(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_person: dict[str, list[dict[str, Any]]] = {}
    for provider in rows:
        if provider.get("retired"):
            continue
        person = provider.get("person") or {}
        person_uuid = str(person.get("uuid") or "") if isinstance(person, dict) else ""
        if person_uuid:
            by_person.setdefault(person_uuid, []).append(provider)
    return by_person


def serialize_staff(
    user: dict[str, Any],
    providers_by_person: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    role_names = _role_names(user)
    hospital_administrator = is_hospital_administrator_account(role_names)
    if set(role_names) & TECHNICAL_ROLES and not hospital_administrator:
        return None
    departments = _departments_for_roles(role_names)
    if not departments and not hospital_administrator:
        return None
    if hospital_administrator and not departments:
        person = user.get("person") or {}
        return {
            "userUuid": str(user.get("uuid") or ""),
            "username": str(user.get("username") or ""),
            "displayName": str(
                person.get("display") or user.get("display") or user.get("username") or "Staff member"
            ),
            "enabled": not bool(user.get("retired")),
            "accountType": "hospital_administrator",
            "personUuid": str(person.get("uuid") or "") if isinstance(person, dict) else "",
            "departments": [],
            "preferredDepartment": {"id": "administration", "label": "Administration"},
            "providerStatus": "not_required",
            "providerRequired": False,
        }
    person = user.get("person") or {}
    person_uuid = str(person.get("uuid") or "") if isinstance(person, dict) else ""
    providers = providers_by_person.get(person_uuid, [])
    needs_provider = any(bool(row["providerRequired"]) for row in departments)
    provider_status = "ready" if needs_provider and providers else "missing" if needs_provider else "not_required"
    properties = user.get("userProperties") or {}
    preferred_id = str(properties.get(WORKPLACE_PROPERTY) or "")
    preferred = DEPARTMENT_BY_ID.get("reception" if preferred_id == "registration" else preferred_id)
    return {
        "userUuid": str(user.get("uuid") or ""),
        "username": str(user.get("username") or ""),
        "displayName": str(person.get("display") or user.get("display") or user.get("username") or "Staff member"),
        "enabled": not bool(user.get("retired")),
        "accountType": "staff",
        "personUuid": person_uuid,
        "departments": [
            {
                "id": row["id"],
                "label": row["label"],
                "roleLabel": row["roleLabel"],
            }
            for row in departments
        ],
        "preferredDepartment": (
            {"id": preferred["id"], "label": preferred["label"]} if preferred else None
        ),
        "providerStatus": provider_status,
        "providerRequired": needs_provider,
    }


def _load_users() -> list[dict[str, Any]]:
    representation = (
        "custom:(uuid,username,display,retired,"
        "person:(uuid,display),roles:(uuid,name),userProperties)"
    )
    payload = _admin_openmrs_json(
        f"/openmrs/ws/rest/v1/user?includeAll=true&limit=500&v={quote(representation, safe='():,')}",
    )
    return _results(payload)


def _load_providers() -> list[dict[str, Any]]:
    representation = "custom:(uuid,identifier,retired,person:(uuid,display))"
    payload = _admin_openmrs_json(
        f"/openmrs/ws/rest/v1/provider?includeAll=true&limit=500&v={quote(representation, safe='():,')}",
    )
    return _results(payload)


def list_staff(cookie: str) -> dict[str, Any]:
    actor = require_hospital_admin(cookie)
    providers = _provider_rows_by_person(_load_providers())
    import staff_hr

    staff = []
    seen_people: set[str] = set()
    for user in _load_users():
        serialized = serialize_staff(user, providers)
        if serialized is None:
            continue
        person_uuid = str(serialized.get("personUuid") or "")
        if person_uuid:
            try:
                serialized = staff_hr.enrich_login_row(serialized, person_uuid)
            except Exception:
                serialized = staff_hr.decorate_login_staff({**serialized, "personUuid": person_uuid})
            seen_people.add(person_uuid)
        else:
            serialized = staff_hr.decorate_login_staff(serialized)
        staff.append(serialized)
    try:
        staff.extend(staff_hr.list_directory_profiles(seen_people))
    except Exception:
        pass
    staff.sort(key=lambda row: (row["displayName"].lower(), str(row.get("username") or "").lower()))
    return {
        "status": "ok",
        "staff": staff,
        "departments": public_departments(),
        "staffCategories": staff_hr.public_staff_categories(),
        "capabilities": {
            "canCreateHospitalAdministrator": is_technical_superadmin(actor),
        },
    }


def public_departments() -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "roleLabel": row["roleLabel"],
            "providerRequired": row["providerRequired"],
        }
        for row in DEPARTMENTS
    ]


def list_access(cookie: str) -> dict[str, Any]:
    payload = list_staff(cookie)
    rows = [
        {
            "userUuid": staff["userUuid"],
            "displayName": staff["displayName"],
            "username": staff["username"],
            "enabled": staff["enabled"],
            "department": department,
        }
        for staff in payload["staff"]
        for department in staff["departments"]
    ]
    rows.sort(key=lambda row: (row["department"]["label"], row["displayName"].lower()))
    return {
        "status": "ok",
        "access": rows,
        "departments": payload["departments"],
    }


def _role_catalog() -> dict[str, dict[str, Any]]:
    representation = "custom:(uuid,name,retired)"
    rows = _results(
        _admin_openmrs_json(
            f"/openmrs/ws/rest/v1/role?limit=500&v={quote(representation, safe='():,')}",
            fallback="Approved staff roles could not be loaded.",
        )
    )
    return {
        str(row.get("name")): row
        for row in rows
        if row.get("name") and not row.get("retired")
    }


def _approved_role_refs(departments: list[str], catalog: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    refs = []
    for department_id in departments:
        role_name = str(DEPARTMENT_BY_ID[department_id]["roleName"])
        role = catalog.get(role_name)
        if not role or not role.get("uuid"):
            raise ApiError(
                409,
                "approved_role_missing",
                f"The approved {DEPARTMENT_BY_ID[department_id]['label']} role is not configured.",
            )
        refs.append({"uuid": str(role["uuid"]), "name": role_name})
        extra_name = ANCILLARY_ROLE_BY_DEPARTMENT.get(department_id)
        if extra_name:
            extra = catalog.get(extra_name)
            if extra and extra.get("uuid"):
                refs.append({"uuid": str(extra["uuid"]), "name": extra_name})
    return refs


def _hospital_administrator_role_refs(catalog: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for name, missing in (
        (HOSPITAL_ADMIN_ROLE_NAME, "The Hospital Administrator role is not configured."),
        (SUPERADMIN_ROLE_NAME, "Full administrator access is not configured."),
    ):
        role = catalog.get(name)
        if not role or not role.get("uuid"):
            raise ApiError(409, "approved_role_missing", missing)
        refs.append({"uuid": str(role["uuid"]), "name": name})
    return refs


def _find_user_by_username(username: str) -> dict[str, Any] | None:
    representation = (
        "custom:(uuid,username,retired,person:(uuid,display),"
        "roles:(uuid,name),userProperties)"
    )
    payload = _admin_openmrs_json(
        f"/openmrs/ws/rest/v1/user?includeAll=true&username={quote(username)}"
        f"&v={quote(representation, safe='():,')}",
    )
    return next(
        (row for row in _results(payload) if str(row.get("username") or "").lower() == username.lower()),
        None,
    )


def _load_user(user_uuid: str) -> dict[str, Any]:
    representation = (
        "custom:(uuid,username,retired,person:(uuid,display),"
        "roles:(uuid,name),userProperties)"
    )
    payload = _admin_openmrs_json(
        f"/openmrs/ws/rest/v1/user/{quote(user_uuid)}?v={quote(representation, safe='():,')}",
        fallback="That staff account could not be loaded.",
    )
    if not isinstance(payload, dict) or not payload.get("uuid"):
        raise ApiError(404, "staff_not_found", "That staff account was not found.")
    return payload


def _assert_manageable(user: dict[str, Any], actor: dict[str, Any]) -> None:
    if str(user.get("uuid") or "") == str(actor.get("uuid") or ""):
        raise ApiError(409, "self_change_blocked", "You cannot change your own Admin account here.")
    role_names = _role_names(user)
    hospital_administrator = is_hospital_administrator_account(role_names)
    if set(role_names) & TECHNICAL_ROLES and not hospital_administrator:
        raise ApiError(403, "technical_account", "Technical administrator accounts cannot be changed here.")
    if hospital_administrator and not is_technical_superadmin(actor):
        raise ApiError(
            403,
            "hospital_administrator_account",
            "Hospital Administrator accounts can only be changed by another full administrator.",
        )


def _ensure_provider(person_uuid: str, username: str) -> bool:
    providers = _load_providers()
    for provider in providers:
        if provider.get("retired"):
            continue
        person = provider.get("person") or {}
        provider_person_uuid = (
            str(person.get("uuid") or "") if isinstance(person, dict) else ""
        )
        if provider_person_uuid == person_uuid:
            return False
        if str(provider.get("identifier") or "").lower() == username.lower():
            raise ApiError(
                409,
                "duplicate_provider",
                "A clinical profile already uses this username. Contact technical support.",
            )
    _admin_openmrs_json(
        "/openmrs/ws/rest/v1/provider",
        method="POST",
        payload={"person": person_uuid, "identifier": username},
        fallback="The staff account was created, but the clinical profile could not be completed.",
    )
    return True


def _full_name(value: Any) -> tuple[str, str]:
    parts = [part for part in str(value or "").strip().split() if part]
    if len(parts) < 2:
        raise ApiError(422, "invalid_name", "Enter the staff member's full name.")
    return parts[0], " ".join(parts[1:])


def _username(value: Any) -> str:
    username = str(value or "").strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ApiError(
            422,
            "invalid_username",
            "Use 3–50 lowercase letters, numbers, dots, dashes, or underscores.",
        )
    return username


def _initial_password(value: Any, *, username: str = "") -> str:
    password = str(value or "")
    if len(password) < 8:
        raise ApiError(
            422,
            "password_too_short",
            "The sign-in password must be at least 8 characters.",
        )
    if not any(char.isupper() for char in password) or not any(char.islower() for char in password):
        raise ApiError(
            422,
            "password_case_required",
            "The sign-in password must include both uppercase and lowercase letters.",
        )
    if not any(char.isdigit() for char in password):
        raise ApiError(
            422,
            "password_digit_required",
            "The sign-in password must include at least one number.",
        )
    if not any(not char.isdigit() for char in password):
        raise ApiError(
            422,
            "password_letter_required",
            "The sign-in password must include letters as well as a number.",
        )
    if username and password.lower() == username.lower():
        raise ApiError(
            422,
            "password_matches_username",
            "The sign-in password cannot match the username.",
        )
    return password


def _account_type(value: Any) -> str:
    account_type = str(value or "staff").strip().lower()
    if account_type not in {"staff", "hospital_administrator"}:
        raise ApiError(
            422,
            "invalid_account_type",
            "Choose Staff or Hospital Administrator.",
        )
    return account_type


def _audit_user_state(
    user: dict[str, Any],
    *,
    provider_linked: bool | None = None,
) -> dict[str, Any]:
    role_names = _role_names(user)
    state: dict[str, Any] = {
        "enabled": not bool(user.get("retired")),
        "roles": sorted(role_names),
        "departments": sorted(row["id"] for row in _departments_for_roles(role_names)),
        "preferredDepartment": str((user.get("userProperties") or {}).get(WORKPLACE_PROPERTY) or ""),
    }
    if provider_linked is not None:
        state["providerLinked"] = provider_linked
    return state


def _finish_failure(event_id: str, error: Exception, *, details: dict[str, Any] | None = None) -> None:
    code = error.code if isinstance(error, ApiError) else "server_error"
    finish_admin_event(
        event_id,
        outcome="failure",
        details=details or {},
        error_code=str(code),
    )


def create_staff(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = require_hospital_admin(cookie)
    reject_arbitrary_authority(body)
    import staff_hr

    requested_category = staff_hr.parse_staff_category(body.get("staffCategory"))
    if requested_category and staff_hr.is_non_login_category(requested_category):
        return staff_hr.create_directory_staff(body, cookie)

    given_name, family_name = _full_name(body.get("fullName"))
    username = _username(body.get("username"))
    password = _initial_password(body.get("initialPassword"), username=username)
    account_type = _account_type(body.get("accountType"))
    enabled = body.get("enabled") is not False
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the form and try again.")

    with CREATE_LOCK:
        cached = CREATE_RESULTS.get(request_id)
        if cached:
            if cached.get("username") != username:
                raise ApiError(409, "request_conflict", "Refresh the form and try again.")
            return dict(cached["payload"])

    if requested_category and requested_category in staff_hr.CATEGORY_TO_DEPARTMENT:
        if not body.get("departments"):
            body = {**body, "departments": [requested_category]}
    if requested_category == "clinical":
        staff_hr.parse_employment_type(body.get("employmentType"), required=True)

    desired_departments = (
        [] if account_type == "hospital_administrator" else validate_departments(body.get("departments"))
    )
    if staff_hr.category_from_departments(desired_departments, account_type) == "clinical":
        employment_type = staff_hr.parse_employment_type(
            body.get("employmentType"),
            required=bool(body.get("employmentType") is not None or requested_category == "clinical"),
        )
    else:
        employment_type = ""
    staff_category = staff_hr.category_from_departments(desired_departments, account_type)
    permanent_hr = (
        staff_hr.validate_hr_profile(body)
        if staff_hr.collects_hr_profile(staff_category or requested_category, employment_type)
        else None
    )
    action = (
        "ADMIN_CREATE_HOSPITAL_ADMIN"
        if account_type == "hospital_administrator"
        else "ADMIN_CREATE_USER"
    )
    event_id = start_admin_event(
        actor=actor,
        target_username=username,
        action=action,
        previous_state=None,
        new_state={
            "enabled": enabled,
            "accountType": account_type,
            "departments": desired_departments,
        },
        details={"fullName": f"{given_name} {family_name}"},
        request_id=request_id,
    )
    event_finished = False
    created_user_state: dict[str, Any] | None = None
    user_uuid = ""
    person_uuid = ""
    provider_status = "not_required"
    try:
        if _find_user_by_username(username):
            raise ApiError(409, "duplicate_username", "That username is already in use.")

        if account_type == "hospital_administrator" and not is_technical_superadmin(actor):
            raise ApiError(
                403,
                "hospital_administrator_creation_forbidden",
                "Only technical support can create Hospital Administrator accounts.",
            )

        catalog = _role_catalog()
        if account_type == "hospital_administrator":
            departments: list[str] = []
            role_refs = _hospital_administrator_role_refs(catalog)
            workplace = "administration"
        else:
            departments = desired_departments
            role_refs = _approved_role_refs(departments, catalog)
            workplace = departments[0]
        person = _admin_openmrs_json(
            "/openmrs/ws/rest/v1/person",
            method="POST",
            payload={
                "names": [{"givenName": given_name, "familyName": family_name, "preferred": True}],
                "gender": "U",
            },
            fallback="The staff account could not be created.",
        )
        person_uuid = str((person or {}).get("uuid") or "")
        if not person_uuid:
            raise ApiError(502, "person_create_failed", "The staff account could not be created.")
        try:
            created = _admin_openmrs_json(
                "/openmrs/ws/rest/v1/user",
                method="POST",
                payload={
                    "username": username,
                    "password": password,
                    "person": person_uuid,
                    "roles": role_refs,
                    "userProperties": {WORKPLACE_PROPERTY: workplace},
                    "retired": not enabled,
                },
                fallback=(
                    "The staff identity was started, but the account could not be completed. "
                    "Contact technical support before retrying."
                ),
            )
        finally:
            password = ""  # Do not retain plaintext longer than the OpenMRS request.
        user_uuid = str((created or {}).get("uuid") or "")
        if not user_uuid:
            raise ApiError(
                502,
                "user_create_failed",
                "The staff identity was started, but the account could not be completed.",
            )
        created_user_state = {
            "enabled": enabled,
            "roles": sorted(row["name"] for row in role_refs),
            "departments": sorted(departments),
            "preferredDepartment": workplace,
            "providerLinked": False,
        }

        if provider_required(departments):
            provider_event_id = start_admin_event(
                actor=actor,
                target_user_uuid=user_uuid,
                target_username=username,
                action="ADMIN_PROVIDER_LINK",
                previous_state={"providerLinked": False},
                new_state={"providerLinked": True},
                details={"personUuid": person_uuid},
                request_id=request_id,
            )
            try:
                provider_created = _ensure_provider(person_uuid, username)
                provider_status = "ready"
                created_user_state["providerLinked"] = True
                finish_admin_event(
                    provider_event_id,
                    outcome="success",
                    new_state={"providerLinked": True},
                    details={"created": provider_created, "personUuid": person_uuid},
                )
            except Exception as provider_error:
                _finish_failure(
                    provider_event_id,
                    provider_error,
                    details={"personUuid": person_uuid},
                )
                try:
                    reason = quote("Disabled after incomplete clinical profile creation")
                    _admin_openmrs_json(
                        f"/openmrs/ws/rest/v1/user/{quote(user_uuid)}?reason={reason}",
                        method="DELETE",
                        fallback="The incomplete staff account could not be disabled.",
                    )
                except ApiError as compensation_error:
                    created_user_state["enabled"] = enabled
                    finish_admin_event(
                        event_id,
                        outcome="failure",
                        new_state=created_user_state,
                        details={
                            "personUuid": person_uuid,
                            "providerFailure": getattr(provider_error, "code", "server_error"),
                            "compensationFailure": compensation_error.code,
                        },
                        error_code="provider_create_failed_compensation_failed",
                    )
                    event_finished = True
                    raise ApiError(
                        503,
                        "provider_create_failed_compensation_failed",
                        "The account was created, but its clinical profile and safe disable could not be completed. "
                        "Contact technical support immediately.",
                    ) from compensation_error
                created_user_state["enabled"] = False
                finish_admin_event(
                    event_id,
                    outcome="failure",
                    new_state=created_user_state,
                    details={
                        "personUuid": person_uuid,
                        "providerFailure": getattr(provider_error, "code", "server_error"),
                        "compensatedByDisablingUser": True,
                    },
                    error_code="provider_create_failed_account_disabled",
                )
                event_finished = True
                raise ApiError(
                    502,
                    "provider_create_failed_account_disabled",
                    "The account was created but disabled because its clinical profile could not be completed. "
                    "Contact technical support before enabling it.",
                ) from provider_error

        if account_type == "hospital_administrator":
            staff_payload = {
                "userUuid": user_uuid,
                "username": username,
                "displayName": f"{given_name} {family_name}",
                "enabled": enabled,
                "accountType": "hospital_administrator",
                "departments": [],
                "preferredDepartment": {"id": "administration", "label": "Administration"},
                "providerStatus": "not_required",
                "providerRequired": False,
            }
            success_message = "Hospital Administrator account created."
        else:
            staff_payload = {
                "userUuid": user_uuid,
                "username": username,
                "displayName": f"{given_name} {family_name}",
                "enabled": enabled,
                "accountType": "staff",
                "departments": [
                    {
                        "id": DEPARTMENT_BY_ID[item]["id"],
                        "label": DEPARTMENT_BY_ID[item]["label"],
                        "roleLabel": DEPARTMENT_BY_ID[item]["roleLabel"],
                    }
                    for item in departments
                ],
                "preferredDepartment": {
                    "id": departments[0],
                    "label": DEPARTMENT_BY_ID[departments[0]]["label"],
                },
                "providerStatus": provider_status,
                "providerRequired": provider_required(departments),
            }
            success_message = "Staff account created."
        staff_payload["personUuid"] = person_uuid
        try:
            record_employment = staff_hr.default_employment_type(
                staff_hr.category_from_departments(departments, account_type),
                employment_type,
            )
            staff_hr.record_login_staff_profile(
                person_uuid=person_uuid,
                departments=departments,
                account_type=account_type,
                employment_type=record_employment,
                hr=permanent_hr,
            )
            staff_payload = staff_hr.decorate_login_staff(
                {
                    **staff_payload,
                    "staffCategory": staff_hr.category_from_departments(departments, account_type),
                    "employmentType": record_employment or None,
                    "hr": permanent_hr,
                }
            )
        except Exception:
            pass
        payload = {
            "status": "ok",
            "message": success_message,
            "staff": staff_payload,
            "recordedBy": actor.get("username") or "",
        }
        finish_admin_event(
            event_id,
            outcome="success",
            new_state=created_user_state,
            details={"personUuid": person_uuid},
        )
        event_finished = True
        with CREATE_LOCK:
            CREATE_RESULTS[request_id] = {"username": username, "payload": payload}
        return payload
    except Exception as error:
        if not event_finished:
            _finish_failure(
                event_id,
                error,
                details={"personUuid": person_uuid, "userUuid": user_uuid},
            )
        raise


def _merge_department_roles(
    existing_roles: list[dict[str, Any]],
    departments: list[str],
    approved_refs: list[dict[str, str]],
) -> list[dict[str, str]]:
    keep_pharmacy_inventory = "pharmacy" in departments
    preserved = []
    for role in existing_roles:
        name = str(role.get("name") or "")
        if name == HOSPITAL_ADMIN_ROLE_NAME:
            if role.get("uuid") and name:
                preserved.append({"uuid": str(role["uuid"]), "name": name})
            continue
        if name in PRIMARY_ROLE_NAMES or name in COMPATIBILITY_ROLE_NAMES:
            continue
        if name in ANCILLARY_ROLE_NAMES and not keep_pharmacy_inventory:
            continue
        if role.get("uuid") and name:
            preserved.append({"uuid": str(role["uuid"]), "name": name})
    seen = {row["name"] for row in preserved}
    return preserved + [row for row in approved_refs if row["name"] not in seen]


def update_access(user_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = require_hospital_admin(cookie)
    reject_arbitrary_authority(body)
    departments = validate_departments(body.get("departments"))
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the account and try again.")
    preferred = str(body.get("preferredDepartment") or departments[0]).strip().lower()
    if preferred not in departments:
        raise ApiError(422, "invalid_preferred_department", "Choose one assigned department as the default.")
    user = _load_user(user_uuid)
    _assert_manageable(user, actor)
    if is_hospital_administrator_account(_role_names(user)):
        record_admin_event(
            actor=actor,
            target_user_uuid=user_uuid,
            target_username=str(user.get("username") or ""),
            action="ADMIN_UPDATE_DEPARTMENTS",
            previous_state=_audit_user_state(user),
            new_state=_audit_user_state(user),
            details={"requestedDepartments": departments},
            outcome="failure",
            error_code="hospital_administrator_department_access",
            request_id=request_id,
        )
        raise ApiError(
            403,
            "hospital_administrator_department_access",
            "Hospital Administrator accounts do not receive department access.",
        )
    before_state = _audit_user_state(user)
    previous_departments = set(before_state["departments"])
    desired_departments = set(departments)
    added = sorted(desired_departments - previous_departments)
    removed = sorted(previous_departments - desired_departments)
    event_id = start_admin_event(
        actor=actor,
        target_user_uuid=user_uuid,
        target_username=str(user.get("username") or ""),
        action="ADMIN_UPDATE_DEPARTMENTS",
        previous_state=before_state,
        new_state={
            **before_state,
            "departments": sorted(desired_departments),
            "preferredDepartment": preferred,
        },
        details={"added": added, "removed": removed},
        request_id=request_id,
    )
    person = user.get("person") or {}
    person_uuid = str(person.get("uuid") or "") if isinstance(person, dict) else ""
    provider_created = False
    try:
        catalog = _role_catalog()
        approved_refs = _approved_role_refs(departments, catalog)
        if provider_required(departments):
            if not person_uuid:
                raise ApiError(409, "person_missing", "This staff account has no person record.")
            provider_event_id = start_admin_event(
                actor=actor,
                target_user_uuid=user_uuid,
                target_username=str(user.get("username") or ""),
                action="ADMIN_PROVIDER_LINK",
                previous_state={"providerLinked": False},
                new_state={"providerLinked": True},
                details={"personUuid": person_uuid},
                request_id=request_id,
            )
            try:
                provider_created = _ensure_provider(
                    person_uuid,
                    str(user.get("username") or ""),
                )
                finish_admin_event(
                    provider_event_id,
                    outcome="success",
                    new_state={"providerLinked": True},
                    details={"created": provider_created, "personUuid": person_uuid},
                )
            except Exception as provider_error:
                _finish_failure(
                    provider_event_id,
                    provider_error,
                    details={"personUuid": person_uuid},
                )
                raise

        roles = _merge_department_roles(user.get("roles") or [], departments, approved_refs)
        properties = {**(user.get("userProperties") or {}), WORKPLACE_PROPERTY: preferred}
        _admin_openmrs_json(
            f"/openmrs/ws/rest/v1/user/{quote(user_uuid)}",
            method="POST",
            payload={"roles": roles, "userProperties": properties},
            fallback="Department access could not be saved.",
        )
        updated = _load_user(user_uuid)
        after_state = _audit_user_state(updated)
        finish_admin_event(
            event_id,
            outcome="success",
            new_state=after_state,
            details={"added": added, "removed": removed, "providerCreated": provider_created},
        )
        for department_id in added:
            record_admin_event(
                actor=actor,
                target_user_uuid=user_uuid,
                target_username=str(user.get("username") or ""),
                action="ADMIN_ASSIGN_DEPARTMENT",
                previous_state=before_state,
                new_state=after_state,
                details={"department": department_id},
                outcome="success",
                request_id=request_id,
            )
        for department_id in removed:
            record_admin_event(
                actor=actor,
                target_user_uuid=user_uuid,
                target_username=str(user.get("username") or ""),
                action="ADMIN_REMOVE_DEPARTMENT",
                previous_state=before_state,
                new_state=after_state,
                details={"department": department_id},
                outcome="success",
                request_id=request_id,
            )
        return {
            "status": "ok",
            "message": "Department access saved.",
            "recordedBy": actor.get("username") or "",
        }
    except Exception as error:
        _finish_failure(
            event_id,
            error,
            details={"added": added, "removed": removed, "providerCreated": provider_created},
        )
        raise


def update_status(user_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = require_hospital_admin(cookie)
    if not isinstance(body.get("enabled"), bool):
        raise ApiError(422, "invalid_status", "Choose whether this account is active or disabled.")
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the account and try again.")
    user = _load_user(user_uuid)
    _assert_manageable(user, actor)
    enabled = bool(body["enabled"])
    before_state = _audit_user_state(user)
    action = "ADMIN_ENABLE_USER" if enabled else "ADMIN_DISABLE_USER"
    event_id = start_admin_event(
        actor=actor,
        target_user_uuid=user_uuid,
        target_username=str(user.get("username") or ""),
        action=action,
        previous_state=before_state,
        new_state={**before_state, "enabled": enabled},
        details={},
        request_id=request_id,
    )
    try:
        if enabled:
            _admin_openmrs_json(
                f"/openmrs/ws/rest/v1/user/{quote(user_uuid)}",
                method="POST",
                payload={"retired": False},
                fallback="The account status could not be changed.",
            )
        else:
            reason = quote("Disabled through Hospital EMR Hospital Administration")
            _admin_openmrs_json(
                f"/openmrs/ws/rest/v1/user/{quote(user_uuid)}?reason={reason}",
                method="DELETE",
                fallback="The account status could not be changed.",
            )
        updated = _load_user(user_uuid)
        after_state = _audit_user_state(updated)
        finish_admin_event(event_id, outcome="success", new_state=after_state, details={})
        return {
            "status": "ok",
            "message": "Account enabled." if enabled else "Account disabled.",
            "enabled": enabled,
            "recordedBy": actor.get("username") or "",
        }
    except Exception as error:
        _finish_failure(event_id, error)
        raise


def _password_salt() -> str:
    return hashlib.sha512(os.urandom(64)).hexdigest()


def _password_hash(password: str, salt: str) -> str:
    return hashlib.sha512(f"{password}{salt}".encode("utf-8")).hexdigest()


def _replace_sign_in_password(user_uuid: str, password: str) -> None:
    """OpenMRS accepts a password on a new account, then ignores it on later updates."""
    import openmrs_sql

    salt = _password_salt()
    hashed = _password_hash(password, salt)
    connection = openmrs_sql._connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET password = %s, salt = %s, date_changed = UTC_TIMESTAMP(), changed_by = user_id
                WHERE uuid = %s AND retired = 0
                """,
                (hashed, salt, user_uuid),
            )
            updated = cursor.rowcount
            cursor.execute(
                """
                DELETE user_property
                FROM user_property
                INNER JOIN users ON users.user_id = user_property.user_id
                WHERE users.uuid = %s
                  AND user_property.property IN ('loginAttempts', 'lockoutTimestamp')
                """,
                (user_uuid,),
            )
        connection.commit()
    except Exception as error:
        raise ApiError(502, "password_not_changed", "The sign-in password could not be changed.") from error
    finally:
        connection.close()
    if updated != 1:
        raise ApiError(502, "password_not_changed", "The sign-in password could not be changed.")


def change_password(user_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = require_hospital_admin(cookie)
    reject_arbitrary_authority(body)
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the account and try again.")
    user = _load_user(user_uuid)
    _assert_manageable(user, actor)
    username = str(user.get("username") or "")
    password = _initial_password(body.get("password"), username=username)
    before_state = _audit_user_state(user)
    event_id = start_admin_event(
        actor=actor,
        target_user_uuid=user_uuid,
        target_username=username,
        action="ADMIN_CHANGE_PASSWORD",
        previous_state=before_state,
        new_state=before_state,
        details={},
        request_id=request_id,
    )
    try:
        _replace_sign_in_password(user_uuid, password)
        password = ""
        finish_admin_event(event_id, outcome="success", new_state=before_state, details={})
        return {
            "status": "ok",
            "message": "Sign-in password updated. Tell the staff member the new password in person.",
            "recordedBy": actor.get("username") or "",
        }
    except Exception as error:
        password = ""
        _finish_failure(event_id, error)
        raise
