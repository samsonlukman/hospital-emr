"""External (unregistered) laboratory patients and orders.

OpenELIS only receives patients and orders through the OpenMRS atomfeed, so
external customers get a thin OpenMRS laboratory identity (EXTLAB######) —
not Reception registration and not a registration card fee.

SQLite (same AUDIT_DB_PATH as radiology_external) stores External Lab ID
EXT-LAB-######, demographics, openmrs_uuid mapping, and link audit.
Odoo remains the financial source of truth with lab:{orderUuid} charge keys.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import laboratory as lab
import server as core
from admin_audit import AUDIT_DB_PATH
from server import ApiError

EXT_DISPLAY_PREFIX = "EXT-LAB-"
EXT_OPENMRS_PREFIX = "EXTLAB"
WALKIN_REF_PREFIX = "LAB-WALKIN:"
SOURCE_EXTERNAL_REFERRAL = "external_referral"
SOURCE_LABORATORY_DIRECT = "laboratory_direct"
PATIENT_TYPE_EXTERNAL = "external"
PATIENT_TYPE_REGISTERED = "registered"

STORE_LOCK = threading.Lock()

require_lab_user = lab.require_lab_user
_openmrs_json = lab._openmrs_json
_openmrs_post = lab._openmrs_post


def _service_get(path: str) -> dict[str, Any] | list[Any]:
    return core.openmrs_service_get(path)


def _service_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return core.openmrs_service_post(path, payload)
    except ApiError as error:
        if error.code in {"clinical_write_error", "clinical_write_config"}:
            raise ApiError(
                error.status,
                "external_patient_failed",
                "The laboratory customer or visit could not be created. Try again, or ask an administrator for help.",
            ) from error
        raise


def display_external_id(sequence: int) -> str:
    return f"{EXT_DISPLAY_PREFIX}{int(sequence):06d}"


def openmrs_identifier_for(sequence: int) -> str:
    return f"{EXT_OPENMRS_PREFIX}{int(sequence):06d}"


def is_external_openmrs_identifier(value: str) -> bool:
    text = str(value or "").strip().upper()
    return text.startswith(EXT_OPENMRS_PREFIX)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_openmrs() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or os.environ.get("ABIKAN_ADMIN_AUDIT_DB") or AUDIT_DB_PATH)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        if not db_path.exists():
            raise
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(path: str | None = None) -> None:
    with STORE_LOCK:
        connection = _connect(path)
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS laboratory_external_patient (
                    external_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL,
                    openmrs_uuid TEXT NOT NULL UNIQUE,
                    openmrs_identifier TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL DEFAULT '',
                    sex TEXT NOT NULL DEFAULT '',
                    dob TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    linked_patient_uuid TEXT NOT NULL DEFAULT '',
                    linked_at TEXT NOT NULL DEFAULT '',
                    linked_by TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lab_ext_phone ON laboratory_external_patient(phone)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lab_ext_openmrs ON laboratory_external_patient(openmrs_uuid)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lab_ext_linked ON laboratory_external_patient(linked_patient_uuid)"
            )
            connection.commit()
        finally:
            connection.close()


def _next_sequence(path: str | None = None) -> int:
    ensure_schema(path)
    local_max = 0
    connection = _connect(path)
    try:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS max_seq FROM laboratory_external_patient"
        ).fetchone()
        local_max = int((row["max_seq"] if row else 0) or 0)
    finally:
        connection.close()
    remote_max = 0
    try:
        payload = _service_get(
            f"/openmrs/ws/rest/v1/patient?q={EXT_OPENMRS_PREFIX}&v=custom:(identifiers:(identifier))&limit=50"
        )
        rows = payload.get("results") if isinstance(payload, dict) else payload
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            for ident in row.get("identifiers") or []:
                if not isinstance(ident, dict):
                    continue
                text = str(ident.get("identifier") or "").strip().upper()
                if text.startswith(EXT_OPENMRS_PREFIX) and text[len(EXT_OPENMRS_PREFIX) :].isdigit():
                    remote_max = max(remote_max, int(text[len(EXT_OPENMRS_PREFIX) :]))
    except ApiError:
        pass
    return max(local_max, remote_max) + 1


def _upsert_patient_row(row: dict[str, Any], path: str | None = None) -> None:
    ensure_schema(path)
    with STORE_LOCK:
        connection = _connect(path)
        try:
            connection.execute(
                """
                INSERT INTO laboratory_external_patient (
                    external_id, sequence, openmrs_uuid, openmrs_identifier, full_name,
                    phone, sex, dob, address, created_by, created_at,
                    linked_patient_uuid, linked_at, linked_by
                ) VALUES (
                    :external_id, :sequence, :openmrs_uuid, :openmrs_identifier, :full_name,
                    :phone, :sex, :dob, :address, :created_by, :created_at,
                    :linked_patient_uuid, :linked_at, :linked_by
                )
                ON CONFLICT(external_id) DO UPDATE SET
                    openmrs_uuid=excluded.openmrs_uuid,
                    openmrs_identifier=excluded.openmrs_identifier,
                    full_name=excluded.full_name,
                    phone=excluded.phone,
                    sex=excluded.sex,
                    dob=excluded.dob,
                    address=excluded.address,
                    linked_patient_uuid=excluded.linked_patient_uuid,
                    linked_at=excluded.linked_at,
                    linked_by=excluded.linked_by
                """,
                row,
            )
            connection.commit()
        finally:
            connection.close()


def _load_patient_row(external_id: str, path: str | None = None) -> dict[str, Any] | None:
    ensure_schema(path)
    connection = _connect(path)
    try:
        row = connection.execute(
            "SELECT * FROM laboratory_external_patient WHERE external_id = ?",
            (external_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def _load_by_openmrs_uuid(openmrs_uuid: str, path: str | None = None) -> dict[str, Any] | None:
    ensure_schema(path)
    connection = _connect(path)
    try:
        row = connection.execute(
            "SELECT * FROM laboratory_external_patient WHERE openmrs_uuid = ?",
            (openmrs_uuid,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def _list_patient_rows(path: str | None = None) -> list[dict[str, Any]]:
    ensure_schema(path)
    connection = _connect(path)
    try:
        rows = connection.execute(
            "SELECT * FROM laboratory_external_patient ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _normalize_request_source(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"laboratory_direct", "lab_direct", "direct", "desk"}:
        return SOURCE_LABORATORY_DIRECT
    if text in {"external_referral", "external", "referral", "outside"}:
        return SOURCE_EXTERNAL_REFERRAL
    if text in {"doctor_order", "doctor"}:
        return SOURCE_EXTERNAL_REFERRAL
    return SOURCE_EXTERNAL_REFERRAL


def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = re.sub(r"\s+", " ", full_name).strip().split(" ")
    if len(parts) < 2:
        raise ApiError(422, "name_required", "Enter the person's full name.")
    given = " ".join(parts[:-1]).strip()
    family = parts[-1].strip()
    if len(given) < 1 or len(family) < 1:
        raise ApiError(422, "name_required", "Enter the person's full name.")
    return given, family


def _normalize_sex(value: str) -> str:
    text = value.strip().upper()
    if text in {"M", "MALE"}:
        return "M"
    if text in {"F", "FEMALE"}:
        return "F"
    if text in {"O", "OTHER"}:
        return "O"
    raise ApiError(422, "sex_required", "Select male, female, or other.")


def _birthdate_from_body(body: dict[str, Any]) -> tuple[str, bool]:
    raw = _text(
        body.get("buyerDob")
        or body.get("dateOfBirth")
        or body.get("birthdate")
        or body.get("age")
        or body.get("buyerAge")
    )
    if not raw:
        raise ApiError(422, "birthdate_required", "Enter a date of birth or an age.")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw, bool(body.get("birthdateEstimated"))
    age_match = re.fullmatch(r"(\d{1,3})\s*(y|yr|yrs|year|years)?", raw, re.I)
    if age_match:
        years = int(age_match.group(1))
        if years < 0 or years > 130:
            raise ApiError(422, "invalid_age", "Enter a valid age in years.")
        born = datetime.now(timezone.utc).date() - timedelta(days=years * 365)
        return born.isoformat(), True
    raise ApiError(
        422,
        "birthdate_invalid",
        "Enter date of birth as YYYY-MM-DD or an age in years.",
    )


def _serialize_patient(meta: dict[str, Any]) -> dict[str, Any]:
    linked = _text(meta.get("linked_patient_uuid"))
    return {
        "status": "ok",
        "externalId": _text(meta.get("external_id")),
        "openmrsUuid": _text(meta.get("openmrs_uuid")),
        "openmrsIdentifier": _text(meta.get("openmrs_identifier")),
        "patientUuid": _text(meta.get("openmrs_uuid")),
        "fullName": _text(meta.get("full_name")),
        "patientName": _text(meta.get("full_name")),
        "phone": _text(meta.get("phone")),
        "sex": _text(meta.get("sex")),
        "dob": _text(meta.get("dob")),
        "address": _text(meta.get("address")),
        "patientType": PATIENT_TYPE_EXTERNAL,
        "patientTypeLabel": "External Patient",
        "createdBy": _text(meta.get("created_by")),
        "createdAt": _text(meta.get("created_at")),
        "linkedPatientUuid": linked,
        "linkedAt": _text(meta.get("linked_at")),
        "linkedBy": _text(meta.get("linked_by")),
        "isExternal": True,
    }


def search_external_patients(cookie: str, query: str = "") -> dict[str, Any]:
    require_lab_user(cookie)
    q = _text(query).lower()
    rows = _list_patient_rows()
    items = []
    for meta in rows:
        payload = _serialize_patient(meta)
        if q:
            haystack = " ".join(
                [
                    payload["externalId"],
                    payload["openmrsIdentifier"],
                    payload["fullName"],
                    payload["phone"],
                    payload["linkedPatientUuid"],
                ]
            ).lower()
            if q not in haystack:
                continue
        items.append(payload)
    return {"status": "ok", "items": items}


def get_external_patient(external_id: str, cookie: str) -> dict[str, Any]:
    require_lab_user(cookie)
    external_id = unquote(external_id)
    meta = _load_patient_row(external_id)
    if not meta:
        raise ApiError(404, "external_patient_not_found", "This external patient was not found.")
    return _serialize_patient(meta)


def external_for_openmrs_uuid(openmrs_uuid: str, path: str | None = None) -> dict[str, Any] | None:
    if not _text(openmrs_uuid):
        return None
    meta = _load_by_openmrs_uuid(openmrs_uuid, path)
    return _serialize_patient(meta) if meta else None


def linked_external_for_registered(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_lab_user(cookie)
    ensure_schema()
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT * FROM laboratory_external_patient WHERE linked_patient_uuid = ? ORDER BY created_at DESC",
            (patient_uuid,),
        ).fetchall()
        metas = [dict(row) for row in rows]
    finally:
        connection.close()
    return {"status": "ok", "items": [_serialize_patient(meta) for meta in metas]}


def _identifier_type_uuid(cookie: str) -> str:
    import registration_patient as arrival

    try:
        identifier_type = arrival.load_identifier_type(cookie)
        return str(identifier_type["uuid"])
    except ApiError:
        payload = _service_get(
            "/openmrs/ws/rest/v1/patientidentifiertype?v=custom:(uuid,name,required,retired)"
        )
        rows = payload.get("results") if isinstance(payload, dict) else payload
        for row in rows or []:
            if isinstance(row, dict) and not row.get("retired") and row.get("uuid"):
                if row.get("required"):
                    return str(row["uuid"])
        for row in rows or []:
            if isinstance(row, dict) and not row.get("retired") and row.get("uuid"):
                return str(row["uuid"])
        raise ApiError(502, "identifier_missing", "No hospital number type is configured.")


def _registration_location_uuid(cookie: str) -> str:
    import registration_patient as arrival

    try:
        locations = arrival.load_login_locations(cookie)
        desk = arrival.registration_desk_location(locations)
        if desk and desk.get("uuid"):
            return str(desk["uuid"])
        for row in locations:
            if str(row.get("name") or "").strip().upper() == "OPD-1":
                return str(row["uuid"])
        if locations:
            return str(locations[0]["uuid"])
    except ApiError:
        pass
    payload = _service_get("/openmrs/ws/rest/v1/location?tag=Login+Location&v=custom:(uuid,name,display)")
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if isinstance(row, dict) and row.get("uuid"):
            name = str(row.get("name") or row.get("display") or "").strip().upper()
            if name in {"REGISTRATION DESK", "OPD-1"}:
                return str(row["uuid"])
    for row in rows or []:
        if isinstance(row, dict) and row.get("uuid"):
            return str(row["uuid"])
    raise ApiError(
        502,
        "location_missing",
        "No hospital location is configured for laboratory registration.",
    )


def _create_thin_openmrs_patient(
    *,
    cookie: str,
    identifier: str,
    given: str,
    family: str,
    sex: str,
    birthdate: str,
    birthdate_estimated: bool,
    phone: str,
    address: str,
) -> dict[str, Any]:
    location_uuid = _registration_location_uuid(cookie)
    identifier_type = _identifier_type_uuid(cookie)
    person: dict[str, Any] = {
        "gender": sex,
        "birthdate": birthdate,
        "birthdateEstimated": birthdate_estimated,
        "names": [{"givenName": given, "familyName": family, "preferred": True}],
        "dead": False,
    }
    if address:
        person["addresses"] = [{"address1": address, "preferred": True}]
    try:
        created = _service_post(
            "/openmrs/ws/rest/v1/patient",
            {
                "identifiers": [
                    {
                        "identifier": identifier,
                        "identifierType": identifier_type,
                        "location": location_uuid,
                        "preferred": True,
                    }
                ],
                "person": person,
            },
        )
    except ApiError as error:
        raise ApiError(
            502,
            "external_patient_failed",
            "The external patient could not be created. Try again in a moment.",
        ) from error
    uuid = _text(created.get("uuid"))
    if not uuid:
        raise ApiError(
            502,
            "external_patient_failed",
            "The external patient could not be created.",
        )
    if phone:
        try:
            import registration_patient as arrival

            person_row = created.get("person") if isinstance(created.get("person"), dict) else {}
            person_uuid = _text(person_row.get("uuid")) or uuid
            attributes = arrival.load_person_attributes(cookie)
            phone_type = next(
                (
                    row
                    for row in attributes
                    if str(row.get("name") or "") in {"phoneNumber", "phone"}
                ),
                None,
            )
            if phone_type and phone_type.get("uuid"):
                _service_post(
                    f"/openmrs/ws/rest/v1/person/{quote(person_uuid)}/attribute",
                    {"attributeType": phone_type["uuid"], "value": phone},
                )
        except ApiError:
            pass
    return {"uuid": uuid, "identifier": identifier, "display": _text(created.get("display"))}


def create_or_find_external_patient(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_lab_user(cookie)
    external_id = _text(body.get("externalId"))
    if external_id:
        meta = _load_patient_row(external_id)
        if meta:
            payload = _serialize_patient(meta)
            payload["alreadyCreated"] = True
            return payload
        raise ApiError(404, "external_patient_not_found", "This external patient was not found.")

    openmrs_uuid = _text(body.get("openmrsUuid") or body.get("patientUuid"))
    if openmrs_uuid:
        meta = _load_by_openmrs_uuid(openmrs_uuid)
        if meta:
            payload = _serialize_patient(meta)
            payload["alreadyCreated"] = True
            return payload

    full_name = _text(body.get("buyerName") or body.get("patientName") or body.get("fullName"))
    phone = _text(body.get("buyerPhone") or body.get("phone"))
    if phone:
        for meta in _list_patient_rows():
            if _text(meta.get("phone")) == phone and _text(meta.get("full_name")).lower() == full_name.lower():
                payload = _serialize_patient(meta)
                payload["alreadyCreated"] = True
                return payload

    given, family = _split_full_name(full_name)
    sex = _normalize_sex(_text(body.get("buyerSex") or body.get("sex") or body.get("gender")))
    birthdate, estimated = _birthdate_from_body(body)
    address = _text(body.get("buyerAddress") or body.get("address"))

    sequence = _next_sequence()
    display_id = display_external_id(sequence)
    openmrs_id = openmrs_identifier_for(sequence)
    created = _create_thin_openmrs_patient(
        cookie=cookie,
        identifier=openmrs_id,
        given=given,
        family=family,
        sex=sex,
        birthdate=birthdate,
        birthdate_estimated=estimated,
        phone=phone,
        address=address,
    )
    meta = {
        "external_id": display_id,
        "sequence": sequence,
        "openmrs_uuid": created["uuid"],
        "openmrs_identifier": openmrs_id,
        "full_name": f"{given} {family}".strip(),
        "phone": phone,
        "sex": sex,
        "dob": birthdate,
        "address": address,
        "created_by": _text(user.get("username") or user.get("display")),
        "created_at": _now(),
        "linked_patient_uuid": "",
        "linked_at": "",
        "linked_by": "",
    }
    _upsert_patient_row(meta)
    payload = _serialize_patient(meta)
    payload["alreadyCreated"] = False
    payload["message"] = "External patient created."
    return payload


def _opd_visit_type_uuid(cookie: str) -> str:
    try:
        payload = _openmrs_json(
            "/openmrs/ws/rest/v1/visittype?v=custom:(uuid,name,display,retired)",
            cookie,
        )
    except ApiError:
        payload = _service_get("/openmrs/ws/rest/v1/visittype?v=custom:(uuid,name,display,retired)")
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if not isinstance(row, dict) or row.get("retired"):
            continue
        name = _text(row.get("name") or row.get("display")).upper()
        if name == "OPD":
            return _text(row.get("uuid"))
    raise ApiError(502, "visit_type_missing", "Outpatient visit type is not configured.")


def _default_opd_location_uuid(cookie: str) -> str:
    return _registration_location_uuid(cookie)


def _ensure_open_opd_visit(patient_uuid: str, cookie: str, location_uuid: str = "") -> dict[str, str]:
    try:
        payload = _openmrs_json(
            f"/openmrs/ws/rest/v1/visit?patient={quote(patient_uuid)}&includeInactive=false"
            "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),location:(uuid,name))",
            cookie,
        )
    except ApiError:
        payload = _service_get(
            f"/openmrs/ws/rest/v1/visit?patient={quote(patient_uuid)}&includeInactive=false"
            "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),location:(uuid,name))"
        )
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if not isinstance(row, dict) or row.get("stopDatetime") or not row.get("uuid"):
            continue
        visit_type = row.get("visitType") if isinstance(row.get("visitType"), dict) else {}
        return {
            "uuid": str(row["uuid"]),
            "visitType": _text(visit_type.get("name")) or "OPD",
            "locationUuid": _text(
                (row.get("location") or {}).get("uuid")
                if isinstance(row.get("location"), dict)
                else ""
            ),
        }

    loc = location_uuid or _default_opd_location_uuid(cookie)
    visit_type_uuid = _opd_visit_type_uuid(cookie)
    created = _service_post(
        "/openmrs/ws/rest/v1/visit",
        {
            "patient": patient_uuid,
            "visitType": visit_type_uuid,
            "location": loc,
            "startDatetime": _now_openmrs(),
        },
    )
    uuid = _text(created.get("uuid"))
    if not uuid:
        raise ApiError(
            502,
            "visit_failed",
            "The laboratory visit could not be started. Try again in a moment.",
        )
    return {"uuid": uuid, "visitType": "OPD", "locationUuid": loc}


def create_external_lab_order(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Create thin external patient (if needed), open OPD visit, place Lab Direct order."""
    require_lab_user(cookie)
    patient = create_or_find_external_patient(body, cookie)
    patient_uuid = _text(patient.get("openmrsUuid") or patient.get("patientUuid"))
    if not patient_uuid:
        raise ApiError(502, "external_patient_failed", "The external patient could not be created.")

    location_uuid = _text(body.get("locationUuid")) or _default_opd_location_uuid(cookie)
    visit = _ensure_open_opd_visit(patient_uuid, cookie, location_uuid)
    request_source = _normalize_request_source(_text(body.get("requestSource")))
    referrer = _text(body.get("referrer") or body.get("referrerName"))
    indication = _text(body.get("indication") or body.get("clinicalIndication") or body.get("comment"))
    comment_parts = []
    if indication:
        comment_parts.append(indication)
    if referrer:
        comment_parts.append(f"Referrer: {referrer}")
    comment = " ".join(comment_parts).strip()

    order_body = {
        "visitUuid": visit["uuid"],
        "locationUuid": location_uuid or visit.get("locationUuid") or "",
        "tests": body.get("tests") if isinstance(body.get("tests"), list) else [],
        "requestSource": request_source,
        "comment": comment,
        "requestId": _text(body.get("requestId")),
        "skipCharge": bool(body.get("skipCharge")),
        "walkinPartnerToken": _text(body.get("walkinPartnerToken"))
        or _text(patient.get("externalId")).replace("-", "").replace(":", ""),
        "buyerName": _text(body.get("buyerName") or body.get("patientName") or patient.get("fullName")),
        "buyerPhone": _text(body.get("buyerPhone") or body.get("phone") or patient.get("phone")),
    }
    result = lab.create_lab_direct_orders(patient_uuid, order_body, cookie)
    result["externalPatient"] = patient
    result["externalId"] = patient.get("externalId")
    result["patientType"] = PATIENT_TYPE_EXTERNAL
    result["patientTypeLabel"] = "External Patient"
    result["message"] = "External laboratory order created. Submit the bill when you are ready."
    return result


def link_external_patient(external_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Link an external laboratory patient to a registered patient. Confirm required; no name merge."""
    user = require_lab_user(cookie)
    external_id = unquote(external_id)
    meta = _load_patient_row(external_id)
    if not meta:
        raise ApiError(404, "external_patient_not_found", "This external patient was not found.")
    patient_uuid = _text(body.get("patientUuid"))
    if not patient_uuid:
        raise ApiError(422, "patient_required", "Select the registered patient to link.")
    if not bool(body.get("confirm")):
        raise ApiError(
            422,
            "confirm_required",
            "Confirm that these laboratory records belong to this registered patient.",
        )
    if _text(meta.get("linked_patient_uuid")):
        if meta["linked_patient_uuid"] == patient_uuid:
            payload = _serialize_patient(meta)
            payload["alreadyLinked"] = True
            return payload
        raise ApiError(
            409,
            "already_linked",
            "This external patient is already linked to another registered patient.",
        )
    if patient_uuid == _text(meta.get("openmrs_uuid")):
        raise ApiError(
            422,
            "invalid_link",
            "Choose a registered hospital patient, not the external laboratory record.",
        )

    lab.load_openmrs_patient(patient_uuid, cookie)
    meta["linked_patient_uuid"] = patient_uuid
    meta["linked_at"] = _now()
    meta["linked_by"] = _text(user.get("username") or user.get("display"))
    _upsert_patient_row(meta)
    payload = _serialize_patient(meta)
    payload["message"] = "External patient linked to the registered patient."
    return payload
