"""Patient allergies via the installed OpenMRS allergy REST.

OpenMRS remains the clinical store. Hospital EMR only forwards the authenticated
session, checks hospital roles, and validates the payload. Nothing is stored
in a Hospital EMR table.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import inpatient as ward
from server import ApiError

LOGGER = logging.getLogger(__name__)

PATIENT_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
PHARMACY_PRIVILEGE = "bahmni:clinical:dispense"
ALLERGEN_TYPES = {
    "DRUG": "Medicine",
    "FOOD": "Food",
    "ENVIRONMENT": "Environment",
    "OTHER": "Other",
}
SEVERITY_NAMES = {
    "MILD": "Mild",
    "MODERATE": "Moderate",
    "SEVERE": "Severe",
}
ALLERGEN_MAX = 200
COMMENT_MAX = 1000
REACTION_MAX = 200

# CIEL concepts shipped with Bahmni / OpenMRS reference dictionaries.
SEVERITY_CONCEPTS = {
    "MILD": "1498AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "MODERATE": "1499AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "SEVERE": "1500AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
}
# OpenMRS Allergy.allergen.codedAllergen is NOT NULL. Free-text names must use
# CIEL Other Non-Coded plus nonCodedAllergen. Verified on this deployment.
OTHER_NON_CODED_CONCEPT = "5622AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _require_patient_uuid(value: str) -> str:
    patient_uuid = str(value or "").strip()
    if not PATIENT_UUID_RE.match(patient_uuid):
        raise ApiError(422, "invalid_patient", "Choose a patient before recording an allergy.")
    return patient_uuid


def _require_allergy_uuid(value: str) -> str:
    allergy_uuid = str(value or "").strip()
    if not PATIENT_UUID_RE.match(allergy_uuid):
        raise ApiError(422, "invalid_allergy", "That allergy record could not be found.")
    return allergy_uuid


def _can_write_allergies(user: dict[str, Any]) -> bool:
    privileges = set(user.get("privileges") or [])
    return bool(
        ward._is_admin(user)
        or ward.ADT_PRIVILEGE in privileges
        or ward.CLINICAL_PRIVILEGE in privileges
    )


def _can_read_allergies(user: dict[str, Any]) -> bool:
    privileges = set(user.get("privileges") or [])
    return _can_write_allergies(user) or PHARMACY_PRIVILEGE in privileges


def require_allergy_reader(cookie: str) -> dict[str, Any]:
    ward.require_session(cookie)
    user = ward.load_openmrs_user(cookie)
    if not _can_read_allergies(user):
        raise ApiError(403, "forbidden", "This allergy record is not available for your department.")
    return user


def require_allergy_writer(cookie: str) -> dict[str, Any]:
    ward.require_session(cookie)
    user = ward.load_openmrs_user(cookie)
    if not _can_write_allergies(user):
        raise ApiError(403, "forbidden", "Recording allergies requires the doctor or ward workspace.")
    return user


def _named(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("display") or value.get("name") or "").strip()
    return ""


def _allergen_name(row: dict[str, Any]) -> str:
    allergen = row.get("allergen") if isinstance(row.get("allergen"), dict) else {}
    non_coded = str(allergen.get("nonCodedAllergen") or "").strip()
    if non_coded:
        return non_coded
    return (
        _named(allergen.get("codedAllergen"))
        or _named(row.get("display"))
        or _named(row)
    )


def _allergen_type(row: dict[str, Any]) -> str:
    allergen = row.get("allergen") if isinstance(row.get("allergen"), dict) else {}
    raw = str(allergen.get("allergenType") or "").strip().upper()
    return raw if raw in ALLERGEN_TYPES else ""


def _reactions(row: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for item in row.get("reactions") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("reactionNonCoded") or "").strip() or _named(item.get("reaction"))
        if label and label not in items:
            items.append(label)
    return items


def serialize_allergy(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    uuid = str(row.get("uuid") or "").strip()
    name = _allergen_name(row)
    if not uuid or not name:
        return None
    allergen_type = _allergen_type(row)
    severity = _named(row.get("severity"))
    reactions = _reactions(row)
    comment = str(row.get("comment") or "").strip()
    extras = [part for part in [severity, ", ".join(reactions)] if part]
    display = name if not extras else f"{name} ({' — '.join(extras)})"
    return {
        "uuid": uuid,
        "allergen": name,
        "allergenType": allergen_type,
        "allergenTypeLabel": ALLERGEN_TYPES.get(allergen_type, ""),
        "severity": severity,
        "reactions": reactions,
        "comment": comment,
        "display": display,
    }


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("results")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if payload.get("uuid"):
            return [payload]
    return []


def _openmrs_allergies_path(patient_uuid: str, allergy_uuid: str | None = None) -> str:
    path = f"/openmrs/ws/rest/v1/patient/{quote(patient_uuid)}/allergy"
    if allergy_uuid:
        path = f"{path}/{quote(allergy_uuid)}"
    return path


def _staff_allergy_error(detail: str) -> str:
    text = (detail or "").lower()
    if "privilege" in text or "not logged" in text:
        return "This action requires the doctor or ward workspace."
    if "codedallergen" in text or "allergen.coded" in text:
        return "Enter the substance the patient reacts to."
    if "allergyreaction.reaction" in text or "reaction" in text and "not-null" in text:
        return "The reaction could not be saved. Leave it blank or use a simpler description."
    if "allergen" in text:
        return "Enter the substance the patient reacts to."
    if "duplicate" in text or "already" in text:
        return "That allergy is already on this patient's record."
    return "The allergy could not be saved on the patient chart. Try again."


def _clip_log(value: Any, limit: int = 800) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("\n", " ")
    return text[:limit]


def _openmrs_allergy_call(
    method: str,
    path: str,
    cookie: str,
    body: dict[str, Any] | None = None,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "Cookie": cookie}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{ward.core.OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            LOGGER.info(
                "openmrs allergy %s %s http=%s payload=%s body=%s",
                method,
                path,
                getattr(response, "status", 200),
                _clip_log(body or {}),
                _clip_log(raw or ""),
            )
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        raw = error.read().decode("utf-8")
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        detail = (
            ((parsed.get("error") or {}).get("message") if isinstance(parsed.get("error"), dict) else "")
            or parsed.get("message")
            or raw
        )
        LOGGER.warning(
            "openmrs allergy %s %s http=%s payload=%s body=%s",
            method,
            path,
            error.code,
            _clip_log(body or {}),
            _clip_log(raw or detail),
        )
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 403:
            raise ApiError(
                403,
                "forbidden",
                "This action requires the doctor or ward workspace.",
            ) from error
        if error.code == 404:
            raise ApiError(404, "not_found", "That allergy record could not be found.") from error
        if error.code in {400, 409, 422}:
            raise ApiError(409, "openmrs_conflict", _staff_allergy_error(str(detail))) from error
        raise ApiError(502, "openmrs_error", _staff_allergy_error(str(detail))) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        LOGGER.warning("openmrs allergy %s %s transport_error payload=%s", method, path, _clip_log(body or {}))
        raise ApiError(
            502,
            "openmrs_error",
            "The allergy could not be saved on the patient chart. Try again.",
        ) from error


def list_openmrs_allergies(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    payload = _openmrs_allergy_call("GET", _openmrs_allergies_path(patient_uuid), cookie)
    serialized = [item for item in (serialize_allergy(row) for row in _rows_from_payload(payload)) if item]
    return serialized


def list_allergies(patient_uuid: str, cookie: str) -> dict[str, Any]:
    user = require_allergy_reader(cookie)
    patient = _require_patient_uuid(patient_uuid)
    _ensure_patient(patient, cookie)
    allergies = list_openmrs_allergies(patient, cookie)
    return {
        "status": "ok",
        "patientUuid": patient,
        "canWrite": _can_write_allergies(user),
        "allergies": allergies,
    }


def _clean_text(value: Any, limit: int, field: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise ApiError(422, "invalid_allergy", f"The {field} is too long.")
    return text


def _validated_write(body: dict[str, Any]) -> dict[str, Any]:
    allergen_type = str(body.get("allergenType") or "").strip().upper()
    if allergen_type not in ALLERGEN_TYPES:
        raise ApiError(422, "invalid_allergen_type", "Choose whether this is a medicine, food, environment, or other allergy.")
    allergen = _clean_text(body.get("allergenName") or body.get("allergen"), ALLERGEN_MAX, "allergy name")
    if not allergen:
        raise ApiError(422, "allergen_required", "Enter the substance the patient reacts to.")
    coded = str(body.get("codedAllergenUuid") or "").strip()
    if coded and not PATIENT_UUID_RE.match(coded):
        raise ApiError(422, "invalid_allergen", "Choose a recognised medicine or enter the name.")
    severity_key = str(body.get("severity") or "").strip().upper()
    if severity_key and severity_key not in SEVERITY_NAMES:
        raise ApiError(422, "invalid_severity", "Choose mild, moderate, severe, or leave severity blank.")
    reaction = _clean_text(body.get("reaction"), REACTION_MAX, "reaction")
    comment = _clean_text(body.get("comment"), COMMENT_MAX, "comment")
    return {
        "allergenType": allergen_type,
        "allergen": allergen,
        "codedAllergenUuid": coded,
        "severity": severity_key,
        "reaction": reaction,
        "comment": comment,
    }


def _ensure_patient(patient_uuid: str, cookie: str) -> None:
    ward._patient_brief(patient_uuid, cookie)


def _resolve_reaction_concept(cookie: str, name: str) -> str:
    wanted = name.strip()
    if not wanted:
        return ""
    try:
        payload = ward.openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/concept?q={quote(wanted)}"
            "&v=custom:(uuid,display,retired)&limit=20",
            cookie,
        )
    except ApiError:
        return ""
    rows = payload.get("results") if isinstance(payload, dict) else []
    target = wanted.casefold()
    for row in rows or []:
        if not isinstance(row, dict) or row.get("retired") or not row.get("uuid"):
            continue
        if str(row.get("display") or "").strip().casefold() == target:
            return str(row["uuid"])
    return ""


def _openmrs_write_body(fields: dict[str, Any], cookie: str) -> dict[str, Any]:
    if fields["codedAllergenUuid"]:
        allergen: dict[str, Any] = {
            "allergenType": fields["allergenType"],
            "codedAllergen": {"uuid": fields["codedAllergenUuid"]},
        }
    else:
        allergen = {
            "allergenType": fields["allergenType"],
            "codedAllergen": {"uuid": OTHER_NON_CODED_CONCEPT},
            "nonCodedAllergen": fields["allergen"],
        }
    payload: dict[str, Any] = {"allergen": allergen}
    if fields["severity"]:
        payload["severity"] = {"uuid": SEVERITY_CONCEPTS[fields["severity"]]}
    if fields["comment"]:
        payload["comment"] = fields["comment"]
    if fields["reaction"]:
        reaction_uuid = _resolve_reaction_concept(cookie, fields["reaction"])
        if reaction_uuid:
            payload["reactions"] = [{"reaction": {"uuid": reaction_uuid}}]
        else:
            payload["reactions"] = [
                {
                    "reaction": {"uuid": OTHER_NON_CODED_CONCEPT},
                    "reactionNonCoded": fields["reaction"],
                }
            ]
    return payload


def _existing_for_patient(patient_uuid: str, allergy_uuid: str, cookie: str) -> dict[str, Any]:
    allergies = list_openmrs_allergies(patient_uuid, cookie)
    match = next((row for row in allergies if row["uuid"] == allergy_uuid), None)
    if match is None:
        raise ApiError(404, "not_found", "That allergy is not on this patient's record.")
    return match


def _write_attempts(fields: dict[str, Any], cookie: str) -> list[dict[str, Any]]:
    primary = _openmrs_write_body(fields, cookie)
    attempts = [primary]
    if not fields["codedAllergenUuid"] and primary["allergen"].get("allergenType") != "OTHER":
        fallback = dict(primary)
        fallback["allergen"] = {
            "allergenType": "OTHER",
            "codedAllergen": {"uuid": OTHER_NON_CODED_CONCEPT},
            "nonCodedAllergen": fields["allergen"],
        }
        attempts.append(fallback)
    if fields["severity"]:
        for item in list(attempts):
            stripped = dict(item)
            stripped.pop("severity", None)
            attempts.append(stripped)
    return attempts


def _save_openmrs_allergy(method: str, path: str, cookie: str, fields: dict[str, Any]) -> None:
    last_error: ApiError | None = None
    for payload in _write_attempts(fields, cookie):
        try:
            _openmrs_allergy_call(method, path, cookie, payload)
            return
        except ApiError as error:
            last_error = error
            if error.code not in {"openmrs_conflict", "openmrs_error"}:
                raise
    if last_error:
        raise last_error


def create_allergy(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    require_allergy_writer(cookie)
    patient = _require_patient_uuid(patient_uuid)
    fields = _validated_write(body)
    _ensure_patient(patient, cookie)
    _save_openmrs_allergy("POST", _openmrs_allergies_path(patient), cookie, fields)
    return list_allergies(patient, cookie)


def update_allergy(patient_uuid: str, allergy_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    require_allergy_writer(cookie)
    patient = _require_patient_uuid(patient_uuid)
    allergy = _require_allergy_uuid(allergy_uuid)
    _ensure_patient(patient, cookie)
    _existing_for_patient(patient, allergy, cookie)
    fields = _validated_write(body)
    _save_openmrs_allergy("POST", _openmrs_allergies_path(patient, allergy), cookie, fields)
    return list_allergies(patient, cookie)


def void_allergy(patient_uuid: str, allergy_uuid: str, cookie: str) -> dict[str, Any]:
    require_allergy_writer(cookie)
    patient = _require_patient_uuid(patient_uuid)
    allergy = _require_allergy_uuid(allergy_uuid)
    _ensure_patient(patient, cookie)
    _existing_for_patient(patient, allergy, cookie)
    _openmrs_allergy_call("DELETE", _openmrs_allergies_path(patient, allergy), cookie)
    return list_allergies(patient, cookie)
