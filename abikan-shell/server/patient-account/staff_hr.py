"""Hospital staff directory profiles on OpenMRS Person records.

A staff profile is an OpenMRS person. An EMR login is an optional OpenMRS user
linked to that person. Security and Attendant have profiles only.

Sensitive HR values stay on person attributes and are returned only from
Hospital Admin staff endpoints. Files live under /var/lib/abikan/staff-files.
"""

from __future__ import annotations

import base64
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import hospital_admin as admin
from admin_audit import finish_admin_event, record_admin_event, start_admin_event
from server import ApiError

STAFF_FILES_ROOT = Path(
    os.environ.get("ABIKAN_STAFF_FILES_ROOT", "/var/lib/abikan/staff-files")
)
USERNAME_PATTERN = admin.USERNAME_PATTERN
PERSON_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SAFE_STAFF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")
MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_LETTER_BYTES = 8 * 1024 * 1024
PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
LETTER_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

ATTR_CATEGORY = "abikan.staffCategory"
ATTR_EMPLOYMENT = "abikan.employmentType"
ATTR_ADDRESS = "abikan.address"
ATTR_PHONE = "abikan.phone"
ATTR_NIN = "abikan.nin"
ATTR_BANK_ACCOUNT = "abikan.bankAccount"
ATTR_BANK_NAME = "abikan.bankName"
ATTR_ACCOUNT_NAME = "abikan.accountName"
ATTR_QUALIFICATION = "abikan.qualification"
HR_ATTRIBUTE_NAMES = (
    ATTR_CATEGORY,
    ATTR_EMPLOYMENT,
    ATTR_ADDRESS,
    ATTR_PHONE,
    ATTR_NIN,
    ATTR_BANK_ACCOUNT,
    ATTR_BANK_NAME,
    ATTR_ACCOUNT_NAME,
    ATTR_QUALIFICATION,
)
SENSITIVE_HR_FIELDS = {
    "nin",
    "bankAccountNumber",
    "bankName",
    "accountName",
}

LOGIN_CATEGORIES = {
    "clinical",
    "nursing",
    "reception",
    "laboratory",
    "radiology",
    "pharmacy",
    "accountant",
    "hospital_admin",
}
NON_LOGIN_CATEGORIES = {
    "security": {"label": "Security", "roleLabel": "Security"},
    "attendant": {"label": "Attendant", "roleLabel": "Attendant"},
}
STAFF_CATEGORIES: dict[str, dict[str, Any]] = {
    **{
        row["id"]: {
            "id": row["id"],
            "label": row["label"],
            "roleLabel": row["roleLabel"],
            "emrAccess": "account",
        }
        for row in admin.DEPARTMENTS
    },
    "hospital_admin": {
        "id": "hospital_admin",
        "label": "Administration",
        "roleLabel": "Hospital Administrator",
        "emrAccess": "account",
    },
    **{
        key: {**value, "id": key, "emrAccess": "none"}
        for key, value in NON_LOGIN_CATEGORIES.items()
    },
}
DEPARTMENT_TO_CATEGORY = {row["id"]: row["id"] for row in admin.DEPARTMENTS}
CATEGORY_TO_DEPARTMENT = {
    row["id"]: row["id"] for row in admin.DEPARTMENTS if row["id"] != "hospital_admin"
}
EMPLOYMENT_TYPES = {
    "permanent": "Permanent",
    "external": "External / Sourced",
}

_ATTRIBUTE_TYPES: dict[str, str] | None = None


def staff_files_root() -> Path:
    return Path(STAFF_FILES_ROOT)


def public_staff_categories() -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "roleLabel": row["roleLabel"],
            "emrAccess": row["emrAccess"],
            "requiresEmploymentType": row["id"] == "clinical",
            "requiresLogin": row["emrAccess"] == "account",
        }
        for row in STAFF_CATEGORIES.values()
    ]


def is_non_login_category(category: str) -> bool:
    return category in NON_LOGIN_CATEGORIES


def collects_hr_profile(category: str, employment_type: str = "") -> bool:
    """NIN and related HR details for every staff type except outsourced doctors."""
    if not category:
        return False
    if category == "clinical":
        return employment_type == "permanent"
    return True


def parse_staff_category(value: Any, *, required: bool = False) -> str:
    category = str(value or "").strip().lower()
    if not category:
        if required:
            raise ApiError(422, "staff_category_required", "Choose a staff type.")
        return ""
    if category not in STAFF_CATEGORIES:
        raise ApiError(422, "invalid_staff_category", "Choose an approved staff type.")
    return category


def parse_employment_type(value: Any, *, required: bool = False) -> str:
    employment = str(value or "").strip().lower()
    if employment in {"sourced", "external_sourced", "external/sourced"}:
        employment = "external"
    if not employment:
        if required:
            raise ApiError(
                422,
                "employment_type_required",
                "Choose Permanent or External / Sourced for a Clinical Doctor.",
            )
        return ""
    if employment not in EMPLOYMENT_TYPES:
        raise ApiError(
            422,
            "invalid_employment_type",
            "Choose Permanent or External / Sourced.",
        )
    return employment


def category_from_departments(
    departments: list[str],
    account_type: str = "staff",
) -> str:
    if account_type == "hospital_administrator":
        return "hospital_admin"
    if len(departments) == 1:
        return DEPARTMENT_TO_CATEGORY.get(departments[0], departments[0])
    if "clinical" in departments:
        return "clinical"
    return departments[0] if departments else ""


def default_employment_type(category: str, requested: str) -> str:
    if category != "clinical":
        return requested
    return requested or "external"


def validate_hr_profile(body: dict[str, Any], *, require_contact: bool = False) -> dict[str, str]:
    profile = {
        "address": str(body.get("address") or "").strip(),
        "phone": str(body.get("phone") or body.get("phoneNumber") or "").strip(),
        "nin": str(body.get("nin") or "").strip(),
        "bankAccountNumber": str(
            body.get("bankAccountNumber") or body.get("bankAccount") or ""
        ).strip(),
        "bankName": str(body.get("bankName") or "").strip(),
        "accountName": str(body.get("accountName") or body.get("nameOnAccount") or "").strip(),
        "qualification": str(body.get("qualification") or "").strip(),
    }
    if require_contact and not profile["phone"]:
        raise ApiError(422, "phone_required", "Enter a phone number for this staff record.")
    if profile["nin"] and not re.fullmatch(r"[A-Za-z0-9]{8,20}", profile["nin"]):
        raise ApiError(422, "invalid_nin", "Enter a valid NIN, or leave it blank.")
    if profile["bankAccountNumber"] and not re.fullmatch(r"\d{8,12}", profile["bankAccountNumber"]):
        raise ApiError(
            422,
            "invalid_bank_account",
            "Enter an 8–12 digit account number, or leave it blank.",
        )
    if len(profile["qualification"]) > 120:
        raise ApiError(422, "invalid_qualification", "Qualification is too long.")
    return profile


def _person_dir(person_uuid: str) -> Path:
    if not SAFE_STAFF_ID_RE.fullmatch(person_uuid):
        raise ApiError(404, "staff_not_found", "That staff record was not found.")
    path = staff_files_root() / person_uuid
    path.mkdir(parents=True, exist_ok=True)
    return path


def remember_directory_person(person_uuid: str) -> None:
    marker = _person_dir(person_uuid) / ".staff"
    if not marker.exists():
        marker.write_text("abikan-staff\n", encoding="utf-8")


def list_directory_person_uuids() -> list[str]:
    root = staff_files_root()
    if not root.is_dir():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and SAFE_STAFF_ID_RE.fullmatch(path.name)
    )


def photo_path(person_uuid: str) -> Path | None:
    folder = staff_files_root() / person_uuid
    if not folder.is_dir():
        return None
    for name in ("profile.jpg", "profile.png", "profile.webp"):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def letter_path(person_uuid: str) -> Path | None:
    folder = staff_files_root() / person_uuid
    if not folder.is_dir():
        return None
    for name in ("appointment-letter.pdf", "appointment-letter.jpg", "appointment-letter.png"):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def has_profile_picture(person_uuid: str) -> bool:
    return photo_path(person_uuid) is not None


def has_appointment_letter(person_uuid: str) -> bool:
    return letter_path(person_uuid) is not None


def _decode_upload(content: str, *, allowed: dict[str, str], limit: int) -> tuple[bytes, str]:
    raw = str(content or "").strip()
    media_type = ""
    if raw.startswith("data:") and ";base64," in raw:
        header, raw = raw.split(";base64,", 1)
        media_type = header.replace("data:", "", 1).lower()
    try:
        data = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as error:
        raise ApiError(422, "invalid_file", "That file could not be read.") from error
    if not data:
        raise ApiError(422, "invalid_file", "Choose a file to upload.")
    if len(data) > limit:
        raise ApiError(422, "file_too_large", "That file is too large.")
    if data.startswith(b"%PDF"):
        guessed = "application/pdf"
    elif data.startswith(b"\x89PNG"):
        guessed = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        guessed = "image/jpeg"
    elif data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        guessed = "image/webp"
    else:
        guessed = media_type
    if guessed not in allowed:
        raise ApiError(422, "unsupported_file", "Use a JPEG, PNG, or PDF file.")
    return data, allowed[guessed]


def save_profile_picture(person_uuid: str, content: str) -> dict[str, Any]:
    data, suffix = _decode_upload(content, allowed=PHOTO_TYPES, limit=MAX_PHOTO_BYTES)
    folder = _person_dir(person_uuid)
    for stale in folder.glob("profile.*"):
        stale.unlink(missing_ok=True)
    target = folder / f"profile{suffix}"
    target.write_bytes(data)
    return {"hasProfilePicture": True, "contentType": next(k for k, v in PHOTO_TYPES.items() if v == suffix)}


def save_appointment_letter(person_uuid: str, content: str) -> dict[str, Any]:
    data, suffix = _decode_upload(content, allowed=LETTER_TYPES, limit=MAX_LETTER_BYTES)
    folder = _person_dir(person_uuid)
    for stale in folder.glob("appointment-letter.*"):
        stale.unlink(missing_ok=True)
    target = folder / f"appointment-letter{suffix}"
    target.write_bytes(data)
    return {"hasAppointmentLetter": True}


def read_profile_picture(person_uuid: str) -> tuple[bytes, str]:
    path = photo_path(person_uuid)
    if path is None:
        raise ApiError(404, "photo_not_found", "No profile picture has been uploaded.")
    suffix = path.suffix.lower()
    content_type = next((key for key, value in PHOTO_TYPES.items() if value == suffix), "image/jpeg")
    return path.read_bytes(), content_type


def read_appointment_letter(person_uuid: str) -> tuple[bytes, str, str]:
    path = letter_path(person_uuid)
    if path is None:
        raise ApiError(404, "letter_not_found", "No appointment letter has been uploaded.")
    suffix = path.suffix.lower()
    content_type = next(
        (key for key, value in LETTER_TYPES.items() if value == suffix),
        "application/pdf",
    )
    return path.read_bytes(), content_type, path.name


def attribute_type_map() -> dict[str, str]:
    global _ATTRIBUTE_TYPES
    if _ATTRIBUTE_TYPES is not None:
        return _ATTRIBUTE_TYPES
    rows = admin._results(
        admin._admin_openmrs_json(
            "/openmrs/ws/rest/v1/personattributetype?v=custom:(uuid,name,retired)&limit=200",
            fallback="Staff records could not be loaded.",
        )
    )
    found = {
        str(row.get("name")): str(row.get("uuid"))
        for row in rows
        if row.get("name") and row.get("uuid") and not row.get("retired")
    }
    created = dict(found)
    for name in HR_ATTRIBUTE_NAMES:
        if name in created:
            continue
        payload = admin._admin_openmrs_json(
            "/openmrs/ws/rest/v1/personattributetype",
            method="POST",
            payload={
                "name": name,
                "description": f"Hospital EMR staff field {name}",
                "format": "java.lang.String",
                "searchable": name in {ATTR_CATEGORY, ATTR_PHONE},
            },
            fallback="Staff records could not be prepared.",
        )
        created[name] = str((payload or {}).get("uuid") or "")
        if not created[name]:
            raise ApiError(502, "openmrs_error", "Staff records could not be prepared.")
    _ATTRIBUTE_TYPES = created
    return created


def reset_attribute_type_cache() -> None:
    global _ATTRIBUTE_TYPES
    _ATTRIBUTE_TYPES = None


def _attribute_values(person: dict[str, Any]) -> dict[str, str]:
    types = {uuid: name for name, uuid in attribute_type_map().items()}
    values: dict[str, str] = {}
    for item in person.get("attributes") or []:
        if not isinstance(item, dict) or item.get("voided"):
            continue
        attr_type = item.get("attributeType") or {}
        type_uuid = (
            str(attr_type.get("uuid") or "")
            if isinstance(attr_type, dict)
            else str(attr_type or "")
        )
        name = str(attr_type.get("display") or attr_type.get("name") or "") if isinstance(attr_type, dict) else ""
        key = types.get(type_uuid) or (name if name in HR_ATTRIBUTE_NAMES else "")
        if key:
            values[key] = str(item.get("value") or "")
    return values


def load_person(person_uuid: str) -> dict[str, Any]:
    representation = (
        "custom:(uuid,display,preferredName:(givenName,familyName,display),"
        "attributes:(uuid,value,voided,attributeType:(uuid,display,name)))"
    )
    payload = admin._admin_openmrs_json(
        f"/openmrs/ws/rest/v1/person/{quote(person_uuid)}?v={quote(representation, safe='():,')}",
        fallback="That staff record could not be loaded.",
    )
    if not isinstance(payload, dict) or not payload.get("uuid"):
        raise ApiError(404, "staff_not_found", "That staff record was not found.")
    return payload


def write_person_attributes(person_uuid: str, values: dict[str, str]) -> None:
    types = attribute_type_map()
    attributes = []
    for name, value in values.items():
        type_uuid = types.get(name)
        if not type_uuid:
            continue
        attributes.append({"attributeType": type_uuid, "value": value})
    if not attributes:
        return
    admin._admin_openmrs_json(
        f"/openmrs/ws/rest/v1/person/{quote(person_uuid)}",
        method="POST",
        payload={"attributes": attributes},
        fallback="The staff record could not be saved.",
    )


def hr_from_attributes(values: dict[str, str]) -> dict[str, str]:
    return {
        "address": values.get(ATTR_ADDRESS, ""),
        "phone": values.get(ATTR_PHONE, ""),
        "nin": values.get(ATTR_NIN, ""),
        "bankAccountNumber": values.get(ATTR_BANK_ACCOUNT, ""),
        "bankName": values.get(ATTR_BANK_NAME, ""),
        "accountName": values.get(ATTR_ACCOUNT_NAME, ""),
        "qualification": values.get(ATTR_QUALIFICATION, ""),
    }


def public_staff_fields(
    *,
    person_uuid: str,
    user: dict[str, Any] | None,
    category: str,
    employment_type: str,
    display_name: str,
    hr: dict[str, str] | None = None,
) -> dict[str, Any]:
    meta = STAFF_CATEGORIES.get(category) or {
        "id": category,
        "label": category.title(),
        "roleLabel": category.title(),
        "emrAccess": "account" if user else "none",
    }
    login = bool(user and user.get("userUuid"))
    enabled = bool(user.get("enabled")) if user else True
    payload = {
        "staffId": person_uuid,
        "personUuid": person_uuid,
        "userUuid": (user or {}).get("userUuid") or "",
        "username": (user or {}).get("username") or "",
        "displayName": display_name,
        "enabled": enabled,
        "accountType": (user or {}).get("accountType") or "staff",
        "staffCategory": category,
        "staffCategoryLabel": meta["label"],
        "employmentType": employment_type or None,
        "employmentTypeLabel": EMPLOYMENT_TYPES.get(employment_type, ""),
        "emrAccess": "account" if login else "none",
        "emrAccessLabel": "Has account" if login else "No account",
        "departments": (user or {}).get("departments") or [],
        "preferredDepartment": (user or {}).get("preferredDepartment"),
        "providerStatus": (user or {}).get("providerStatus") or "not_required",
        "providerRequired": bool((user or {}).get("providerRequired")),
        "hasProfilePicture": has_profile_picture(person_uuid),
        "hasAppointmentLetter": has_appointment_letter(person_uuid),
        "profilePictureHref": (
            f"/openmrs/abikan-api/admin/staff/{person_uuid}/photo"
            if has_profile_picture(person_uuid)
            else ""
        ),
    }
    if hr is not None:
        payload["hr"] = hr
    return payload


def decorate_login_staff(row: dict[str, Any]) -> dict[str, Any]:
    person_uuid = str(row.get("personUuid") or "")
    category = str(row.get("staffCategory") or "")
    if not category:
        if row.get("accountType") == "hospital_administrator":
            category = "hospital_admin"
        else:
            category = category_from_departments(
                [item["id"] for item in (row.get("departments") or [])],
                str(row.get("accountType") or "staff"),
            )
    employment = str(row.get("employmentType") or "")
    if category == "clinical" and not employment:
        employment = "external"
    display = str(row.get("displayName") or row.get("username") or "Staff member")
    decorated = public_staff_fields(
        person_uuid=person_uuid,
        user=row,
        category=category,
        employment_type=employment,
        display_name=display,
        hr=row.get("hr"),
    )
    decorated.update({key: row[key] for key in row if key not in decorated})
    decorated.update(
        {
            "staffCategory": category,
            "employmentType": employment or None,
            "employmentTypeLabel": EMPLOYMENT_TYPES.get(employment, ""),
            "emrAccess": "account" if row.get("userUuid") else "none",
            "emrAccessLabel": "Has account" if row.get("userUuid") else "No account",
        }
    )
    return decorated


def record_login_staff_profile(
    *,
    person_uuid: str,
    departments: list[str],
    account_type: str,
    employment_type: str = "",
    hr: dict[str, str] | None = None,
) -> None:
    if not person_uuid:
        return
    remember_directory_person(person_uuid)
    category = category_from_departments(departments, account_type)
    if not category:
        return
    values = {ATTR_CATEGORY: category}
    if category == "clinical":
        values[ATTR_EMPLOYMENT] = default_employment_type(category, employment_type)
    if hr and collects_hr_profile(category, values.get(ATTR_EMPLOYMENT, "") or employment_type):
        values[ATTR_ADDRESS] = hr.get("address", "")
        values[ATTR_PHONE] = hr.get("phone", "")
        values[ATTR_NIN] = hr.get("nin", "")
        values[ATTR_BANK_ACCOUNT] = hr.get("bankAccountNumber", "")
        values[ATTR_BANK_NAME] = hr.get("bankName", "")
        values[ATTR_ACCOUNT_NAME] = hr.get("accountName", "")
        values[ATTR_QUALIFICATION] = hr.get("qualification", "")
    try:
        write_person_attributes(person_uuid, values)
    except ApiError:
        return


def create_directory_staff(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = admin.require_hospital_admin(cookie)
    admin.reject_arbitrary_authority(body)
    category = parse_staff_category(body.get("staffCategory"), required=True)
    if not is_non_login_category(category):
        raise ApiError(422, "login_required", "This staff type needs an EMR sign-in.")
    given_name, family_name = admin._full_name(body.get("fullName"))
    hr = validate_hr_profile(body, require_contact=False)
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the form and try again.")
    if body.get("username") or body.get("initialPassword"):
        raise ApiError(
            422,
            "login_not_allowed",
            "Security and Attendant records do not receive EMR sign-in.",
        )
    event_id = start_admin_event(
        actor=actor,
        target_username=f"{given_name} {family_name}",
        action="ADMIN_CREATE_STAFF_PROFILE",
        previous_state=None,
        new_state={"staffCategory": category, "emrAccess": "none"},
        details={"fullName": f"{given_name} {family_name}"},
        request_id=request_id,
    )
    person_uuid = ""
    try:
        person = admin._admin_openmrs_json(
            "/openmrs/ws/rest/v1/person",
            method="POST",
            payload={
                "names": [{"givenName": given_name, "familyName": family_name, "preferred": True}],
                "gender": "U",
            },
            fallback="The staff record could not be created.",
        )
        person_uuid = str((person or {}).get("uuid") or "")
        if not person_uuid:
            raise ApiError(502, "person_create_failed", "The staff record could not be created.")
        remember_directory_person(person_uuid)
        write_person_attributes(
            person_uuid,
            {
                ATTR_CATEGORY: category,
                ATTR_ADDRESS: hr["address"],
                ATTR_PHONE: hr["phone"],
                ATTR_NIN: hr["nin"],
                ATTR_BANK_ACCOUNT: hr["bankAccountNumber"],
                ATTR_BANK_NAME: hr["bankName"],
                ATTR_ACCOUNT_NAME: hr["accountName"],
                ATTR_QUALIFICATION: hr["qualification"],
            },
        )
        staff = public_staff_fields(
            person_uuid=person_uuid,
            user=None,
            category=category,
            employment_type="",
            display_name=f"{given_name} {family_name}",
            hr=hr,
        )
        payload = {
            "status": "ok",
            "message": f"{STAFF_CATEGORIES[category]['label']} staff record created.",
            "staff": staff,
            "recordedBy": actor.get("username") or "",
        }
        finish_admin_event(
            event_id,
            outcome="success",
            new_state={"staffCategory": category, "emrAccess": "none", "personUuid": person_uuid},
            details={"personUuid": person_uuid},
        )
        return payload
    except Exception as error:
        admin._finish_failure(event_id, error, details={"personUuid": person_uuid})
        raise


def update_staff_profile(staff_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = admin.require_hospital_admin(cookie)
    admin.reject_arbitrary_authority(body)
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the record and try again.")
    person_uuid, user = resolve_staff(staff_id)
    person = load_person(person_uuid)
    current = _attribute_values(person)
    category = parse_staff_category(body.get("staffCategory") or current.get(ATTR_CATEGORY) or "")
    if user and category and category != (current.get(ATTR_CATEGORY) or category_from_user(user)):
        # Keep login role mapping as the source of department; category can be refined
        # only when it still matches an assigned department or stays hospital admin.
        inferred = category_from_user(user)
        if category not in {inferred, current.get(ATTR_CATEGORY, "")} and not is_non_login_category(
            inferred
        ):
            category = inferred
    if not category:
        category = category_from_user(user) if user else ""
    employment = parse_employment_type(
        body.get("employmentType"),
        required=category == "clinical" and "employmentType" in body,
    )
    if category == "clinical":
        employment = default_employment_type(category, employment or current.get(ATTR_EMPLOYMENT, ""))
    elif is_non_login_category(category):
        employment = ""
    hr = validate_hr_profile(body)
    event_id = start_admin_event(
        actor=actor,
        target_user_uuid=(user or {}).get("userUuid") or "",
        target_username=(user or {}).get("username") or person.get("display") or "",
        action="ADMIN_UPDATE_STAFF_PROFILE",
        previous_state={
            "staffCategory": current.get(ATTR_CATEGORY, ""),
            "employmentType": current.get(ATTR_EMPLOYMENT, ""),
        },
        new_state={"staffCategory": category, "employmentType": employment},
        details={"personUuid": person_uuid},
        request_id=request_id,
    )
    try:
        values = {ATTR_CATEGORY: category}
        if category == "clinical":
            values[ATTR_EMPLOYMENT] = employment
        if collects_hr_profile(category, employment):
            values.update(
                {
                    ATTR_ADDRESS: hr["address"],
                    ATTR_PHONE: hr["phone"],
                    ATTR_NIN: hr["nin"],
                    ATTR_BANK_ACCOUNT: hr["bankAccountNumber"],
                    ATTR_BANK_NAME: hr["bankName"],
                    ATTR_ACCOUNT_NAME: hr["accountName"],
                    ATTR_QUALIFICATION: hr["qualification"],
                }
            )
        write_person_attributes(person_uuid, values)
        remember_directory_person(person_uuid)
        if body.get("fullName"):
            given, family = admin._full_name(body.get("fullName"))
            admin._admin_openmrs_json(
                f"/openmrs/ws/rest/v1/person/{quote(person_uuid)}",
                method="POST",
                payload={
                    "names": [{"givenName": given, "familyName": family, "preferred": True}],
                },
                fallback="The staff name could not be saved.",
            )
        finish_admin_event(
            event_id,
            outcome="success",
            new_state={"staffCategory": category, "employmentType": employment},
            details={"personUuid": person_uuid},
        )
        return {
            "status": "ok",
            "message": "Staff record saved.",
            "staff": get_staff(person_uuid, cookie),
            "recordedBy": actor.get("username") or "",
        }
    except Exception as error:
        admin._finish_failure(event_id, error, details={"personUuid": person_uuid})
        raise


def category_from_user(user: dict[str, Any]) -> str:
    if user.get("accountType") == "hospital_administrator":
        return "hospital_admin"
    return category_from_departments([item["id"] for item in (user.get("departments") or [])])


def resolve_staff(staff_id: str) -> tuple[str, dict[str, Any] | None]:
    identifier = str(staff_id or "").strip()
    if not identifier:
        raise ApiError(404, "staff_not_found", "That staff record was not found.")
    if PERSON_UUID_RE.fullmatch(identifier):
        try:
            person = load_person(identifier)
            return str(person["uuid"]), find_login_for_person(identifier)
        except ApiError:
            pass
    user = admin._load_user(identifier)
    person = user.get("person") or {}
    person_uuid = str(person.get("uuid") or "") if isinstance(person, dict) else ""
    if not person_uuid:
        raise ApiError(409, "person_missing", "This staff account has no person record.")
    serialized = admin.serialize_staff(user, admin._provider_rows_by_person(admin._load_providers()))
    if serialized is None:
        raise ApiError(404, "staff_not_found", "That staff record was not found.")
    serialized["personUuid"] = person_uuid
    return person_uuid, serialized


def find_login_for_person(person_uuid: str) -> dict[str, Any] | None:
    providers = admin._provider_rows_by_person(admin._load_providers())
    for user in admin._load_users():
        person = user.get("person") or {}
        if isinstance(person, dict) and str(person.get("uuid") or "") == person_uuid:
            serialized = admin.serialize_staff(user, providers)
            if serialized:
                serialized["personUuid"] = person_uuid
                return serialized
    return None


def get_staff(staff_id: str, cookie: str) -> dict[str, Any]:
    admin.require_hospital_admin(cookie)
    person_uuid, user = resolve_staff(staff_id)
    person = load_person(person_uuid)
    values = _attribute_values(person)
    category = values.get(ATTR_CATEGORY) or (category_from_user(user) if user else "")
    employment = values.get(ATTR_EMPLOYMENT, "")
    if category == "clinical" and not employment:
        employment = "external"
    display = str(person.get("display") or (user or {}).get("displayName") or "Staff member")
    return public_staff_fields(
        person_uuid=person_uuid,
        user=user,
        category=category,
        employment_type=employment,
        display_name=display,
        hr=hr_from_attributes(values),
    )


def list_directory_profiles(existing_person_uuids: set[str]) -> list[dict[str, Any]]:
    rows = []
    for person_uuid in list_directory_person_uuids():
        if person_uuid in existing_person_uuids:
            continue
        try:
            person = load_person(person_uuid)
        except ApiError:
            continue
        values = _attribute_values(person)
        category = values.get(ATTR_CATEGORY, "")
        if not is_non_login_category(category):
            continue
        rows.append(
            public_staff_fields(
                person_uuid=person_uuid,
                user=None,
                category=category,
                employment_type="",
                display_name=str(person.get("display") or "Staff member"),
                hr=hr_from_attributes(values),
            )
        )
    return rows


def enrich_login_row(row: dict[str, Any], person_uuid: str) -> dict[str, Any]:
    remember_directory_person(person_uuid)
    try:
        person = load_person(person_uuid)
        values = _attribute_values(person)
    except ApiError:
        values = {}
    category = values.get(ATTR_CATEGORY) or category_from_user(row)
    employment = values.get(ATTR_EMPLOYMENT, "")
    if category == "clinical" and not employment:
        employment = "external"
        try:
            write_person_attributes(person_uuid, {ATTR_CATEGORY: category, ATTR_EMPLOYMENT: employment})
        except ApiError:
            pass
    elif category and not values.get(ATTR_CATEGORY):
        try:
            write_person_attributes(person_uuid, {ATTR_CATEGORY: category})
        except ApiError:
            pass
    row = {
        **row,
        "personUuid": person_uuid,
        "staffCategory": category,
        "employmentType": employment or None,
        "hr": hr_from_attributes(values),
    }
    return decorate_login_staff(row)


def upload_staff_file(staff_id: str, kind: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = admin.require_hospital_admin(cookie)
    person_uuid, user = resolve_staff(staff_id)
    content = str(body.get("content") or body.get("file") or "")
    request_id = str(body.get("requestId") or uuid.uuid4())
    action = "ADMIN_UPLOAD_STAFF_PHOTO" if kind == "photo" else "ADMIN_UPLOAD_APPOINTMENT_LETTER"
    event_id = start_admin_event(
        actor=actor,
        target_user_uuid=(user or {}).get("userUuid") or "",
        target_username=(user or {}).get("username") or "",
        action=action,
        previous_state={
            "hasProfilePicture": has_profile_picture(person_uuid),
            "hasAppointmentLetter": has_appointment_letter(person_uuid),
        },
        new_state={},
        details={"personUuid": person_uuid, "kind": kind},
        request_id=request_id,
    )
    try:
        if kind == "photo":
            result = save_profile_picture(person_uuid, content)
            try:
                admin._admin_openmrs_json(
                    "/openmrs/ws/rest/v1/personimage",
                    method="POST",
                    payload={"person": person_uuid, "base64EncodedImage": content.split(",")[-1]},
                    fallback="The profile picture could not be published.",
                )
            except ApiError:
                pass
            message = "Profile picture saved."
        else:
            result = save_appointment_letter(person_uuid, content)
            message = "Appointment letter saved."
        finish_admin_event(event_id, outcome="success", new_state=result, details={"personUuid": person_uuid})
        return {
            "status": "ok",
            "message": message,
            "staff": get_staff(person_uuid, cookie),
            "recordedBy": actor.get("username") or "",
        }
    except Exception as error:
        admin._finish_failure(event_id, error, details={"personUuid": person_uuid})
        raise


def session_person_uuid(session: dict[str, Any]) -> str:
    user = session.get("user") or {}
    person = user.get("person") if isinstance(user.get("person"), dict) else {}
    person_uuid = str((person or {}).get("uuid") or "").strip()
    if person_uuid:
        return person_uuid
    user_uuid = str(user.get("uuid") or "").strip()
    if not user_uuid:
        return ""
    try:
        person_uuid, _row = resolve_staff(user_uuid)
    except ApiError:
        return ""
    return person_uuid


def download_own_photo(cookie: str) -> tuple[bytes, str, str]:
    session = admin.core.require_session(cookie)
    person_uuid = session_person_uuid(session)
    if not person_uuid or not has_profile_picture(person_uuid):
        raise ApiError(404, "photo_not_found", "No profile picture has been uploaded.")
    data, content_type = read_profile_picture(person_uuid)
    path = photo_path(person_uuid)
    suffix = path.suffix if path else ".jpg"
    return data, content_type, f"profile-picture{suffix}"


def download_staff_file(staff_id: str, kind: str, cookie: str) -> tuple[bytes, str, str]:
    admin.require_hospital_admin(cookie)
    person_uuid, _user = resolve_staff(staff_id)
    if kind == "photo":
        data, content_type = read_profile_picture(person_uuid)
        return data, content_type, f"staff-photo{Path(photo_path(person_uuid).name).suffix if photo_path(person_uuid) else '.jpg'}"
    data, content_type, name = read_appointment_letter(person_uuid)
    return data, content_type, name
