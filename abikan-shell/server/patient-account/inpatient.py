"""Inpatient ward board and ADT writes.

OpenMRS/Bahmni remains the clinical engine. This module forwards the
authenticated session to installed REST APIs. Accommodation billing is
attempted after a successful bed write and must never roll back ADT.
"""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

import server as core

ADT_PRIVILEGE = "app:adt"
ASSIGN_BEDS_PRIVILEGE = "Assign Beds"
CLINICAL_PRIVILEGE = "app:clinical"
ADMIN_ROLES = {"SuperAdmin", "System Developer"}

ADMISSION_ENCOUNTER = "d3785931-5e07-11ef-8f7c-0242ac120002"
TRANSFER_ENCOUNTER = "d3873bd5-5e07-11ef-8f7c-0242ac120002"
DISCHARGE_ENCOUNTER = "d37e03e0-5e07-11ef-8f7c-0242ac120002"
CONSULTATION_ENCOUNTER = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
IPD_VISIT_TYPE = "b7494a80-fdf9-49bb-bb40-396c47b40343"
UNKNOWN_ENCOUNTER_ROLE = "a0b03050-c99b-11e0-9572-0800200c9a66"
ADMIT_CONCEPT = "d36dd2e4-5e07-11ef-8f7c-0242ac120002"
DISPOSITION_CONCEPT = "d36e97b8-5e07-11ef-8f7c-0242ac120002"
GENERAL_PATIENT_NOTE_CONCEPT = "165095AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
NURSING_NOTE_MARKER = "ABIKAN_NURSING_NOTE:v1:"
NURSING_NOTE_MAX_LENGTH = 10000

HOSPITAL_AREAS = [
    "Hawawu Maternity Ward",
    "Aisha Children Ward",
    "Emergency Room",
    "Gold Room 203",
    "Gold Room 202",
    "Gold Room 204",
    "Silver 207",
    "Bronze 208",
    "Gold Room 210",
    "Gold Room 211",
    "Platinum Room 209",
    "Diamond 214",
    "Pre Labour Room",
    "Gold Room 212",
    "Gold Room 213",
    "Silver 206",
    "ICPU",
]
HOSPITAL_AREA_SET = set(HOSPITAL_AREAS)

ApiError = core.ApiError
require_session = core.require_session

IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}
NURSING_NOTE_CREATE_LOCK = threading.Lock()


def now_openmrs() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def openmrs_call(
    method: str,
    path: str,
    cookie: str,
    body: dict[str, Any] | None = None,
    *,
    allow_empty: bool = False,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "Cookie": cookie}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{core.OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {} if allow_empty else {}
            return json.loads(raw)
    except HTTPError as error:
        raw = error.read().decode("utf-8")
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        detail = (
            (parsed.get("error") or {}).get("message")
            or parsed.get("message")
            or ""
        )
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 403:
            raise ApiError(403, "forbidden", "This action requires the ward workspace.") from error
        if error.code == 404:
            raise ApiError(404, "not_found", "That record was not found.") from error
        if error.code in {400, 409, 422}:
            raise ApiError(409, "openmrs_conflict", _staff_error(detail)) from error
        raise ApiError(502, "openmrs_error", "We couldn't complete this ward request. Please try again.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "We couldn't complete this ward request. Please try again.") from error


def _staff_error(detail: str) -> str:
    text = (detail or "").lower()
    if "occupied" in text or "already" in text and "bed" in text:
        return "This bed has just been assigned to another patient. Please choose another bed."
    if "privilege" in text or "not logged" in text:
        return "This action requires the ward workspace."
    return "We couldn't complete this ward request. Please try again."


def load_openmrs_user(cookie: str) -> dict[str, Any]:
    import accountant as cashier

    return cashier.load_openmrs_user(cookie)


def _is_admin(user: dict[str, Any]) -> bool:
    return bool(set(user.get("roles") or []) & ADMIN_ROLES)


def require_nursing_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    privileges = set(user.get("privileges") or [])
    if _is_admin(user) or ADT_PRIVILEGE in privileges:
        return user
    raise ApiError(403, "forbidden", "This action requires the ward workspace.")


def require_assign_user(cookie: str) -> dict[str, Any]:
    user = require_nursing_user(cookie)
    privileges = set(user.get("privileges") or [])
    if _is_admin(user) or ASSIGN_BEDS_PRIVILEGE in privileges or ADT_PRIVILEGE in privileges:
        return user
    raise ApiError(403, "forbidden", "This action requires the ward workspace.")


def require_clinical_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    privileges = set(user.get("privileges") or [])
    if _is_admin(user) or CLINICAL_PRIVILEGE in privileges:
        return user
    raise ApiError(403, "forbidden", "This action requires the doctor workspace.")


def require_inpatient_view(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    privileges = set(user.get("privileges") or [])
    if _is_admin(user) or ADT_PRIVILEGE in privileges or CLINICAL_PRIVILEGE in privileges:
        return user
    raise ApiError(403, "forbidden", "This action requires the ward or doctor workspace.")


def _is_clinical_user(user: dict[str, Any]) -> bool:
    return _is_admin(user) or CLINICAL_PRIVILEGE in set(user.get("privileges") or [])


def _provider_uuid(user_uuid: str, cookie: str) -> str:
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/provider?user={quote(user_uuid)}&v=custom:(uuid,retired)",
        cookie,
    )
    for row in payload.get("results") or []:
        if row.get("uuid") and not row.get("retired"):
            return str(row["uuid"])
    raise ApiError(409, "provider_missing", "This account is not set up as a clinician.")


def _patient_brief(patient_uuid: str, cookie: str) -> dict[str, str]:
    patient = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/patient/{quote(patient_uuid)}"
        "?v=custom:(uuid,display,voided,identifiers:(identifier),person:(display,gender,age,preferredName:(givenName,familyName)))",
        cookie,
    )
    if patient.get("voided"):
        raise ApiError(
            409,
            "patient_inactive",
            "This patient record is no longer active. Search again and choose a current hospital patient.",
        )
    given = ((patient.get("person") or {}).get("preferredName") or {}).get("givenName") or ""
    family = ((patient.get("person") or {}).get("preferredName") or {}).get("familyName") or ""
    display = (patient.get("display") or "").strip()
    name = f"{given} {family}".strip() or (patient.get("person") or {}).get("display") or display
    mrn = ""
    identifiers = patient.get("identifiers") or []
    if identifiers:
        mrn = str(identifiers[0].get("identifier") or "")
    if " - " in display and not mrn:
        mrn = display.split(" - ", 1)[0].strip()
    if " - " in display and name == display:
        name = display.split(" - ", 1)[-1].strip()
    gender = (patient.get("person") or {}).get("gender") or ""
    sex = "Male" if gender == "M" else "Female" if gender == "F" else (gender or "—")
    age = (patient.get("person") or {}).get("age")
    return {
        "uuid": str(patient.get("uuid") or patient_uuid),
        "name": name or "Unknown patient",
        "mrn": mrn or "—",
        "sex": sex,
        "age": str(age) if age is not None else "—",
    }


def _require_active_patient(patient_uuid: str, cookie: str) -> None:
    """Reject voided patients before ward writes."""
    needle = str(patient_uuid or "").strip()
    if not needle:
        raise ApiError(422, "invalid_body", "Choose a patient.")
    patient = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/patient/{quote(needle)}?v=custom:(uuid,voided)",
        cookie,
    )
    if not isinstance(patient, dict) or not patient.get("uuid"):
        raise ApiError(404, "not_found", "That patient was not found.")
    if patient.get("voided"):
        raise ApiError(
            409,
            "patient_inactive",
            "This patient record is no longer active. Search again and choose a current hospital patient.",
        )


def _patient_is_active(patient_uuid: str, cookie: str) -> bool:
    try:
        patient = openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/patient/{quote(patient_uuid)}?v=custom:(uuid,voided)",
            cookie,
        )
    except ApiError:
        return False
    return bool(isinstance(patient, dict) and patient.get("uuid") and not patient.get("voided"))


def _layout_patient(layout: dict[str, Any]) -> dict[str, Any] | None:
    patients = layout.get("patients") or []
    if isinstance(patients, dict):
        patients = [patients]
    if not patients:
        person = layout.get("patient")
        if isinstance(person, dict) and person.get("uuid"):
            patients = [person]
    if not patients:
        return None
    row = patients[0] if isinstance(patients[0], dict) else {}
    uuid = str(row.get("uuid") or "")
    if not uuid:
        return None
    given = str(row.get("givenName") or "")
    family = str(row.get("familyName") or "")
    name = f"{given} {family}".strip() or str(row.get("display") or "Patient assigned")
    return {
        "uuid": uuid,
        "name": name,
        "mrn": str(row.get("identifier") or row.get("display") or "").split(" - ")[0] or "—",
    }


def _map_bed(layout: dict[str, Any], area_name: str, area_uuid: str, cookie: str | None = None) -> dict[str, Any] | None:
    number = str(layout.get("bedNumber") or "").strip()
    if not number:
        return None
    occupant = _layout_patient(layout)
    status = str(layout.get("status") or "AVAILABLE").upper()
    occupied = bool(occupant) or status == "OCCUPIED"
    bed: dict[str, Any] = {
        "bedUuid": str(layout.get("bedUuid") or layout.get("uuid") or ""),
        "bedId": layout.get("bedId"),
        "bedNumber": number,
        "status": "OCCUPIED" if occupied else "AVAILABLE",
        "areaName": area_name,
        "areaUuid": area_uuid,
        "patientUuid": occupant.get("uuid") if occupant else None,
        "patientName": occupant.get("name") if occupant else None,
        "mrn": occupant.get("mrn") if occupant else None,
        "sex": None,
        "age": None,
        "admitted": None,
    }
    return bed


def _hospital_locations(cookie: str) -> list[dict[str, Any]]:
    payload = openmrs_call("GET", "/openmrs/ws/rest/v1/admissionLocation", cookie)
    rows = payload.get("results") if isinstance(payload, dict) else payload
    found: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ward = row.get("ward") if isinstance(row.get("ward"), dict) else {}
        name = str(ward.get("name") or "")
        uuid = str(ward.get("uuid") or "")
        if name in HOSPITAL_AREA_SET and uuid:
            found[name] = {"name": name, "uuid": uuid, "totalBeds": row.get("totalBeds"), "occupiedBeds": row.get("occupiedBeds")}
    ordered = []
    for name in HOSPITAL_AREAS:
        if name in found:
            ordered.append(found[name])
    return ordered


def _area_detail(area: dict[str, Any], cookie: str) -> dict[str, Any]:
    detail = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/admissionLocation/{quote(area['uuid'])}?v=full",
        cookie,
    )
    beds = []
    for layout in detail.get("bedLayouts") or []:
        if not isinstance(layout, dict):
            continue
        mapped = _map_bed(layout, area["name"], area["uuid"])
        if mapped:
            beds.append(mapped)
    occupied = sum(1 for bed in beds if bed["status"] == "OCCUPIED")
    return {
        "uuid": area["uuid"],
        "name": area["name"],
        "totalBeds": len(beds),
        "occupiedBeds": occupied,
        "availableBeds": max(0, len(beds) - occupied),
        "beds": beds,
    }


def _row_has_patient(row: dict[str, Any], patient_uuid: str) -> bool:
    patients = row.get("patients") or []
    if isinstance(patients, dict):
        patients = [patients]
    for person in patients:
        if isinstance(person, dict) and str(person.get("uuid") or "") == patient_uuid:
            return True
    return False


def current_assignment(
    patient_uuid: str,
    cookie: str,
    *,
    scan_board: bool = False,
) -> dict[str, Any] | None:
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/beds?patientUuid={quote(patient_uuid)}&v=full",
        cookie,
        allow_empty=True,
    )
    rows = payload.get("results") if isinstance(payload, dict) else payload
    if isinstance(payload, dict) and payload.get("bedId"):
        rows = [payload]
    if not isinstance(rows, list):
        rows = [payload] if payload else []
    found: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("patients") and not _row_has_patient(row, patient_uuid):
            continue
        bed_id = row.get("bedId") or row.get("id")
        number = row.get("bedNumber")
        if not number:
            continue
        location = row.get("physicalLocation") or row.get("location") or {}
        if isinstance(location, str):
            location_name = location
            location_uuid = ""
        else:
            location_name = str(location.get("name") or location.get("display") or "")
            location_uuid = str(location.get("uuid") or "")
        patients = row.get("patients") or []
        found = {
            "bedId": bed_id,
            "bedUuid": row.get("bedUuid") or row.get("uuid"),
            "bedNumber": str(number),
            "areaName": location_name,
            "areaUuid": location_uuid,
            "status": "OCCUPIED",
            "patientCount": len(patients) if isinstance(patients, list) else 0,
        }
        break
    if found and (not scan_board or (found.get("bedUuid") and found.get("areaUuid"))):
        return found
    if not scan_board or not found:
        return found
    for area in _hospital_locations(cookie):
        detail = _area_detail(area, cookie)
        for bed in detail["beds"]:
            if bed.get("patientUuid") == patient_uuid:
                return {
                    "bedId": bed.get("bedId"),
                    "bedUuid": bed.get("bedUuid"),
                    "bedNumber": bed.get("bedNumber"),
                    "areaName": bed.get("areaName"),
                    "areaUuid": bed.get("areaUuid"),
                    "status": "OCCUPIED",
                    "patientCount": 1,
                    "sex": bed.get("sex"),
                    "age": bed.get("age"),
                    "admitted": bed.get("admitted"),
                }
    return found


def _open_visits(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={quote(patient_uuid)}&includeInactive=false"
        "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),location:(name,uuid))",
        cookie,
    )
    return [row for row in (payload.get("results") or []) if isinstance(row, dict) and not row.get("stopDatetime")]


def _end_visit(visit_uuid: str, cookie: str) -> None:
    try:
        openmrs_call(
            "POST",
            f"/openmrs/ws/rest/v1/bahmnicore/visit/endVisit?visitUuid={quote(visit_uuid)}",
            cookie,
            {},
            allow_empty=True,
        )
    except ApiError:
        openmrs_call(
            "POST",
            f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}",
            cookie,
            {"stopDatetime": now_openmrs()},
        )


def _visit_type_is_ipd(visit: dict[str, Any]) -> bool:
    visit_type = visit.get("visitType")
    if isinstance(visit_type, dict):
        return (
            visit_type.get("uuid") == IPD_VISIT_TYPE
            or str(visit_type.get("name") or "").upper() == "IPD"
        )
    return str(visit_type or "").upper() == "IPD"


def _end_open_non_ipd_visits(patient_uuid: str, cookie: str) -> None:
    for visit in _open_visits(patient_uuid, cookie):
        if _visit_type_is_ipd(visit):
            continue
        visit_uuid = str(visit.get("uuid") or "").strip()
        if visit_uuid:
            _end_visit(visit_uuid, cookie)


def _admission_datetime(patient_uuid: str, cookie: str) -> str | None:
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/encounter?patient={quote(patient_uuid)}"
        f"&encounterType={ADMISSION_ENCOUNTER}&v=custom:(uuid,encounterDatetime)&limit=5",
        cookie,
    )
    rows = payload.get("results") or []
    if not rows:
        return None
    return str(rows[0].get("encounterDatetime") or "") or None


def _safe_patient_brief(patient_uuid: str, cookie: str) -> dict[str, str] | None:
    try:
        return _patient_brief(patient_uuid, cookie)
    except ApiError:
        return None


def _enrich_occupied_beds(areas: list[dict[str, Any]], cookie: str) -> None:
    occupant_ids = []
    seen: set[str] = set()
    for area in areas:
        for bed in area["beds"]:
            patient_uuid = str(bed.get("patientUuid") or "")
            if patient_uuid and patient_uuid not in seen:
                seen.add(patient_uuid)
                occupant_ids.append(patient_uuid)
    if not occupant_ids:
        return
    workers = min(8, max(len(occupant_ids) * 2, 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        brief_futures = {uuid: pool.submit(_safe_patient_brief, uuid, cookie) for uuid in occupant_ids}
        admit_futures = {uuid: pool.submit(_admission_datetime, uuid, cookie) for uuid in occupant_ids}
    brief_by_uuid = {
        uuid: future.result() for uuid, future in brief_futures.items() if future.result()
    }
    admitted_by_uuid = {uuid: future.result() for uuid, future in admit_futures.items()}
    for area in areas:
        for bed in area["beds"]:
            patient_uuid = str(bed.get("patientUuid") or "")
            brief = brief_by_uuid.get(patient_uuid)
            if brief:
                bed["patientName"] = brief["name"]
                bed["mrn"] = brief["mrn"]
                bed["sex"] = brief["sex"]
                bed["age"] = brief["age"]
            if patient_uuid:
                bed["admitted"] = admitted_by_uuid.get(patient_uuid)


def _release_voided_bed_assignments() -> int:
    """Free beds still held by voided patients (e.g. after a register refresh)."""
    try:
        import openmrs_sql as clinical_sql
    except Exception:
        return 0
    if not clinical_sql.sql_configured():
        return 0
    try:
        connection = clinical_sql._connect()
    except Exception:
        return 0
    released = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE bed_patient_assignment_map m
                JOIN patient p ON p.patient_id = m.patient_id
                SET m.date_stopped = NOW()
                WHERE m.date_stopped IS NULL
                  AND p.voided = 1
                """
            )
            released = int(cursor.rowcount or 0)
            if released:
                cursor.execute(
                    """
                    UPDATE bed b
                    SET b.status = 'AVAILABLE'
                    WHERE b.status = 'OCCUPIED'
                      AND NOT EXISTS (
                        SELECT 1 FROM bed_patient_assignment_map live
                        WHERE live.bed_id = b.bed_id AND live.date_stopped IS NULL
                      )
                    """
                )
        connection.commit()
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        return 0
    finally:
        connection.close()
    return released


def build_board(cookie: str) -> dict[str, Any]:
    require_nursing_user(cookie)
    _release_voided_bed_assignments()
    locations = _hospital_locations(cookie)
    if locations:
        with ThreadPoolExecutor(max_workers=min(6, len(locations))) as pool:
            areas = list(pool.map(lambda area: _area_detail(area, cookie), locations))
    else:
        areas = []
    _enrich_occupied_beds(areas, cookie)
    occupied = sum(area["occupiedBeds"] for area in areas)
    total = sum(area["totalBeds"] for area in areas)
    return {
        "status": "ok",
        "areas": areas,
        "totalBeds": total,
        "occupiedBeds": occupied,
        "availableBeds": max(0, total - occupied),
        "awaiting": _awaiting_patients(cookie),
        "message": None,
    }


def _obs_value_uuid(row: dict[str, Any]) -> str:
    value = row.get("value")
    if isinstance(value, dict):
        return str(value.get("uuid") or "")
    coded = row.get("valueCoded")
    if isinstance(coded, dict):
        return str(coded.get("uuid") or "")
    return ""


def _is_admit_obs(row: dict[str, Any]) -> bool:
    if _obs_value_uuid(row) == ADMIT_CONCEPT:
        return True
    value = row.get("value")
    if isinstance(value, dict) and "admit" in str(value.get("display") or "").lower():
        return True
    return isinstance(value, str) and "admit" in value.lower()


def _login_location_uuids(cookie: str) -> list[str]:
    payload = openmrs_call(
        "GET",
        "/openmrs/ws/rest/v1/location?tag=Login+Location&v=custom:(uuid,name)",
        cookie,
    )
    uuids = []
    for row in payload.get("results") or []:
        uuid = str(row.get("uuid") or "")
        if uuid:
            uuids.append(uuid)
    return uuids


def _awaiting_from_sql(location_uuid: str, cookie: str) -> list[dict[str, Any]]:
    try:
        payload = openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/bahmnicore/sql?q=emrapi.sqlSearch.patientsToAdmit"
            f"&visit_location_uuid={quote(location_uuid)}",
            cookie,
        )
    except ApiError:
        return []
    rows = payload if isinstance(payload, list) else (payload or {}).get("results") or []
    if isinstance(rows, dict):
        rows = [rows]
    awaiting = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        patient_uuid = str(row.get("uuid") or row.get("patientUuid") or "")
        if not patient_uuid:
            continue
        given = str(row.get("givenName") or row.get("given_name") or "")
        family = str(row.get("familyName") or row.get("family_name") or "")
        name = f"{given} {family}".strip() or str(row.get("name") or row.get("patientName") or "Patient")
        gender = str(row.get("gender") or "")
        sex = "Male" if gender == "M" else "Female" if gender == "F" else (gender or "—")
        awaiting.append(
            {
                "patientUuid": patient_uuid,
                "patientName": name,
                "mrn": str(row.get("identifier") or row.get("mrn") or "—"),
                "sex": sex,
                "age": str(row.get("age") or "—"),
                "requested": str(row.get("dateCreated") or row.get("datetime") or ""),
                "visitUuid": str(row.get("activeVisitUuid") or row.get("visitUuid") or ""),
            }
        )
    return awaiting


def _awaiting_from_open_ipd(cookie: str) -> list[dict[str, Any]]:
    try:
        payload = openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/visit?visitType={quote(IPD_VISIT_TYPE)}"
            "&includeInactive=false"
            "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),"
            "patient:(uuid,display,identifiers:(identifier),"
            "person:(display,gender,age,preferredName:(givenName,familyName))))",
            cookie,
        )
    except ApiError:
        return []
    awaiting = []
    for visit in payload.get("results") or []:
        if not isinstance(visit, dict) or visit.get("stopDatetime"):
            continue
        if not _visit_type_is_ipd(visit):
            continue
        patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
        patient_uuid = str(patient.get("uuid") or "")
        if not patient_uuid or current_assignment(patient_uuid, cookie):
            continue
        given = ((patient.get("person") or {}).get("preferredName") or {}).get("givenName") or ""
        family = ((patient.get("person") or {}).get("preferredName") or {}).get("familyName") or ""
        display = str(patient.get("display") or "")
        name = f"{given} {family}".strip() or (patient.get("person") or {}).get("display") or display
        if " - " in display and (not name or name == display):
            name = display.split(" - ", 1)[-1].strip()
        mrn = ""
        identifiers = patient.get("identifiers") or []
        if identifiers:
            mrn = str(identifiers[0].get("identifier") or "")
        if " - " in display and not mrn:
            mrn = display.split(" - ", 1)[0].strip()
        gender = (patient.get("person") or {}).get("gender") or ""
        sex = "Male" if gender == "M" else "Female" if gender == "F" else (gender or "—")
        age = (patient.get("person") or {}).get("age")
        awaiting.append(
            {
                "patientUuid": patient_uuid,
                "patientName": name or "Unknown patient",
                "mrn": mrn or "—",
                "sex": sex,
                "age": str(age) if age is not None else "—",
                "requested": str(visit.get("startDatetime") or ""),
                "visitUuid": str(visit.get("uuid") or ""),
            }
        )
    return awaiting


def _awaiting_patients(cookie: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    awaiting: list[dict[str, Any]] = []
    for row in _awaiting_from_open_ipd(cookie):
        patient_uuid = row["patientUuid"]
        if patient_uuid in seen:
            continue
        seen.add(patient_uuid)
        if not _patient_is_active(patient_uuid, cookie):
            continue
        awaiting.append(row)
    for location_uuid in _login_location_uuids(cookie):
        for row in _awaiting_from_sql(location_uuid, cookie):
            patient_uuid = row["patientUuid"]
            if patient_uuid in seen:
                continue
            seen.add(patient_uuid)
            if current_assignment(patient_uuid, cookie):
                continue
            if not _patient_is_active(patient_uuid, cookie):
                continue
            awaiting.append(row)
    return awaiting


def _disposition_awaiting(patient_uuid: str, cookie: str) -> bool:
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/obs?patient={quote(patient_uuid)}&concept={DISPOSITION_CONCEPT}"
        "&v=custom:(uuid,value:(uuid,display),encounter:(visit:(uuid,stopDatetime)))",
        cookie,
    )
    for row in payload.get("results") or []:
        if not _is_admit_obs(row):
            continue
        encounter = row.get("encounter") if isinstance(row.get("encounter"), dict) else {}
        visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
        if visit.get("stopDatetime"):
            continue
        return True
    return False


def _patient_awaiting(patient_uuid: str, cookie: str) -> bool:
    if current_assignment(patient_uuid, cookie):
        return False
    if _open_ipd_admission(patient_uuid, cookie):
        return True
    return _disposition_awaiting(patient_uuid, cookie)


def _admission_awaiting_bed(patient_uuid: str, cookie: str) -> bool:
    if current_assignment(patient_uuid, cookie, scan_board=True):
        return False
    return _open_ipd_admission(patient_uuid, cookie) is not None


def build_patient_stay(
    patient_uuid: str,
    cookie: str,
    *,
    catch_up_billing: bool = True,
) -> dict[str, Any]:
    require_inpatient_view(cookie)
    brief = _patient_brief(patient_uuid, cookie)
    assignment = current_assignment(patient_uuid, cookie, scan_board=True)
    open_admission = _open_ipd_admission(patient_uuid, cookie)
    admitted = _admission_datetime(patient_uuid, cookie) if assignment else None
    stay = {
        "status": "ok",
        "patient": brief,
        "assignment": None
        if not assignment
        else {
            "areaName": assignment.get("areaName"),
            "areaUuid": assignment.get("areaUuid"),
            "bedNumber": assignment.get("bedNumber"),
            "bedUuid": assignment.get("bedUuid"),
            "bedId": assignment.get("bedId"),
            "status": "OCCUPIED",
            "admitted": admitted,
        },
        "awaiting": (not assignment)
        and (bool(open_admission) or _disposition_awaiting(patient_uuid, cookie)),
    }
    active = (_active_admission(patient_uuid, cookie) if assignment else None) or (
        open_admission if not assignment else None
    )
    visit = active.get("visit") if isinstance((active or {}).get("visit"), dict) else {}
    stay["visitUuid"] = str(visit.get("uuid") or "")
    stay["visitStartDatetime"] = str(visit.get("startDatetime") or "")
    stay["admissionEncounterUuid"] = str((active or {}).get("uuid") or "")
    if catch_up_billing:
        return _attach_billing(
            stay,
            lambda billing: billing.summarize_and_catch_up(patient_uuid, cookie),
        )
    return stay


def _admission_encounters(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/encounter?patient={quote(patient_uuid)}"
        f"&encounterType={ADMISSION_ENCOUNTER}"
        "&v=custom:(uuid,encounterDatetime,voided,patient:(uuid),location:(uuid,name),"
        "visit:(uuid,startDatetime,stopDatetime,visitType:(uuid,name)),"
        "obs:(uuid,obsDatetime,value,comment,voided,concept:(uuid,display),"
        "creator:(uuid,display)),encounterProviders:(provider:(uuid)))&limit=100",
        cookie,
    )
    rows = [
        row
        for row in (payload.get("results") or [])
        if isinstance(row, dict) and not row.get("voided")
    ]
    rows.sort(key=lambda row: str(row.get("encounterDatetime") or ""), reverse=True)
    return rows


def _open_ipd_admission(patient_uuid: str, cookie: str) -> dict[str, Any] | None:
    """Open IPD visit plus Admission encounter. A bed is not required."""
    for encounter in _admission_encounters(patient_uuid, cookie):
        patient = encounter.get("patient") if isinstance(encounter.get("patient"), dict) else {}
        visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
        if patient.get("uuid") != patient_uuid:
            continue
        if visit.get("stopDatetime"):
            continue
        if not _visit_type_is_ipd(visit):
            continue
        return encounter
    return None


def _active_admission(patient_uuid: str, cookie: str) -> dict[str, Any] | None:
    if not current_assignment(patient_uuid, cookie, scan_board=True):
        return None
    return _open_ipd_admission(patient_uuid, cookie)


def inpatient_order_context(patient_uuid: str, cookie: str) -> dict[str, str] | None:
    """Open IPD visit for an occupied admission. Never invents a visit."""
    active = _active_admission(patient_uuid, cookie)
    if not active:
        return None
    patient = active.get("patient") if isinstance(active.get("patient"), dict) else {}
    if patient.get("uuid") != patient_uuid:
        return None
    visit = active.get("visit") if isinstance(active.get("visit"), dict) else {}
    visit_uuid = str(visit.get("uuid") or "").strip()
    if not visit_uuid or visit.get("stopDatetime"):
        return None
    location = active.get("location") if isinstance(active.get("location"), dict) else {}
    return {
        "visitUuid": visit_uuid,
        "visitStartDatetime": str(visit.get("startDatetime") or ""),
        "admissionEncounterUuid": str(active.get("uuid") or ""),
        "locationUuid": str(location.get("uuid") or ""),
    }


def resolve_clinical_order_visit_uuid(
    patient_uuid: str,
    requested_visit_uuid: str,
    cookie: str,
    *,
    missing_visit_message: str,
) -> str:
    """Prefer the occupied IPD visit. Outpatients still need the requested open visit."""
    context = inpatient_order_context(patient_uuid, cookie)
    if context:
        return context["visitUuid"]
    if _admission_awaiting_bed(patient_uuid, cookie):
        raise ApiError(
            409,
            "awaiting_bed",
            "This patient is waiting for a bed. Nursing must assign a bed before inpatient orders.",
        )
    requested = (requested_visit_uuid or "").strip()
    if not requested:
        raise ApiError(422, "visit_required", missing_visit_message)
    return requested


def encounter_on_resolved_visit(
    visit: dict[str, Any],
    requested_encounter_uuid: str,
) -> str:
    """Keep a client encounter only when it already belongs to this visit."""
    requested = (requested_encounter_uuid or "").strip()
    if not requested:
        return ""
    for row in visit.get("encounters") or []:
        if isinstance(row, dict) and str(row.get("uuid") or "") == requested:
            return requested
    return ""


def _note_metadata(comment: Any) -> dict[str, str]:
    text = str(comment or "")
    if not text.startswith(NURSING_NOTE_MARKER):
        return {}
    parts = text[len(NURSING_NOTE_MARKER) :].split("|", 3)
    if len(parts) != 4 or not all(parts[:3]):
        return {}
    return {
        "requestId": parts[0],
        "userUuid": parts[1],
        "personUuid": parts[2],
        "authorName": unquote(parts[3]) or "Nurse",
    }


def _serialize_nursing_notes(encounters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for encounter in encounters:
        encounter_uuid = str(encounter.get("uuid") or "")
        visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
        for obs in encounter.get("obs") or []:
            if not isinstance(obs, dict) or obs.get("voided"):
                continue
            concept = obs.get("concept") if isinstance(obs.get("concept"), dict) else {}
            metadata = _note_metadata(obs.get("comment"))
            if concept.get("uuid") != GENERAL_PATIENT_NOTE_CONCEPT or not metadata:
                continue
            notes.append(
                {
                    "uuid": str(obs.get("uuid") or ""),
                    "patientUuid": str(
                        (encounter.get("patient") or {}).get("uuid") or ""
                    ),
                    "admissionEncounterUuid": encounter_uuid,
                    "visitUuid": str(visit.get("uuid") or ""),
                    "authorUserUuid": metadata["userUuid"],
                    "authorPersonUuid": metadata["personUuid"],
                    "authorName": metadata["authorName"],
                    "recordedAt": str(obs.get("obsDatetime") or ""),
                    "content": str(obs.get("value") or ""),
                    "requestId": metadata["requestId"],
                }
            )
    notes.sort(key=lambda row: row["recordedAt"], reverse=True)
    return notes


def build_nursing_notes(patient_uuid: str, cookie: str) -> dict[str, Any]:
    user = require_inpatient_view(cookie)
    active = _active_admission(patient_uuid, cookie)
    if not _is_clinical_user(user) and not active:
        raise ApiError(
            409,
            "not_admitted",
            "Nursing notes are available from the patient's active admission.",
        )
    encounters = _admission_encounters(patient_uuid, cookie)
    if not _is_clinical_user(user):
        encounters = [active] if active else []
    return {
        "status": "ok",
        "patientUuid": patient_uuid,
        "activeAdmissionEncounterUuid": str((active or {}).get("uuid") or ""),
        "notes": _serialize_nursing_notes(encounters),
    }


def _request_marker(request_id: str, identity: dict[str, str]) -> str:
    value = request_id.strip()
    if not value or len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ApiError(422, "request_id_required", "Please try saving this nursing note again.")
    user_uuid = identity.get("userUuid", "").strip()
    person_uuid = identity.get("personUuid", "").strip()
    author_name = identity.get("authorName", "").strip()[:64]
    if not user_uuid or not person_uuid or not author_name:
        raise ApiError(409, "author_unavailable", "Your staff identity could not be recorded.")
    return (
        f"{NURSING_NOTE_MARKER}{value}|{user_uuid}|{person_uuid}|"
        f"{quote(author_name, safe='')}"
    )


def _authenticated_nurse_identity(cookie: str) -> dict[str, str]:
    session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    person = user.get("person") if isinstance(user.get("person"), dict) else {}
    return {
        "userUuid": str(user.get("uuid") or ""),
        "personUuid": str(person.get("uuid") or ""),
        "authorName": str(person.get("display") or user.get("display") or ""),
    }


def create_nursing_note(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
) -> dict[str, Any]:
    user = require_nursing_user(cookie)
    forbidden = {
        "author",
        "authorName",
        "authorUuid",
        "authorUserUuid",
        "timestamp",
        "recordedAt",
        "obsDatetime",
        "encounterUuid",
        "admissionEncounterUuid",
        "patientUuid",
    }
    if forbidden & set(body):
        raise ApiError(
            422,
            "server_fields_only",
            "The note author, time, patient, and admission are set automatically.",
        )
    content = str(body.get("note") or "").strip()
    if not content:
        raise ApiError(422, "note_required", "Enter a nursing note before saving.")
    if len(content) > NURSING_NOTE_MAX_LENGTH:
        raise ApiError(422, "note_too_long", "The nursing note is too long.")
    active = _active_admission(patient_uuid, cookie)
    if not active:
        raise ApiError(
            409,
            "not_admitted",
            "This patient does not have an active admission.",
        )
    request_id = str(body.get("requestId") or "").strip()
    marker = _request_marker(
        request_id,
        _authenticated_nurse_identity(cookie),
    )
    admission_uuid = str(active.get("uuid") or "")
    with NURSING_NOTE_CREATE_LOCK:
        # The OpenMRS observation model has no unique request-id constraint.
        # Serialize the check/write/confirm sequence so concurrent browser or
        # network retries cannot both create the same immutable clinical note.
        existing = _serialize_nursing_notes(_admission_encounters(patient_uuid, cookie))
        prior = next((row for row in existing if row["requestId"] == request_id), None)
        if prior:
            return {
                "status": "ok",
                "patientUuid": patient_uuid,
                "activeAdmissionEncounterUuid": admission_uuid,
                "note": prior,
                "duplicate": True,
            }
        location = active.get("location") if isinstance(active.get("location"), dict) else {}
        observation_datetime = now_openmrs()
        payload: dict[str, Any] = {
            "person": patient_uuid,
            "concept": GENERAL_PATIENT_NOTE_CONCEPT,
            "value": content,
            "comment": marker,
            "obsDatetime": observation_datetime,
            "encounter": admission_uuid,
        }
        location_uuid = str(location.get("uuid") or "")
        if location_uuid:
            payload["location"] = location_uuid
        core.openmrs_service_post("/openmrs/ws/rest/v1/obs", payload)
        refreshed = _serialize_nursing_notes(_admission_encounters(patient_uuid, cookie))
        saved = next(
            (
                row
                for row in refreshed
                if row["admissionEncounterUuid"] == admission_uuid
                and row["requestId"] == request_id
            ),
            None,
        )
        if not saved:
            raise ApiError(
                502,
                "note_not_confirmed",
                "The nursing note could not be confirmed. Please try again.",
            )
        return {
            "status": "ok",
            "patientUuid": patient_uuid,
            "activeAdmissionEncounterUuid": admission_uuid,
            "note": saved,
            "duplicate": False,
        }


def _find_bed(bed_uuid: str, cookie: str, bed_id: int | None = None) -> dict[str, Any]:
    for area in _hospital_locations(cookie):
        detail = _area_detail(area, cookie)
        for bed in detail["beds"]:
            if bed_id is not None and bed.get("bedId") == bed_id:
                return bed
            if bed_uuid and bed.get("bedUuid") == bed_uuid:
                return bed
    raise ApiError(404, "bed_not_found", "That bed was not found.")


def _body_bed_id(body: dict[str, Any]) -> int | None:
    raw = body.get("bedId")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _assert_bed_available(bed_id: int, cookie: str) -> None:
    resource = openmrs_call("GET", f"/openmrs/ws/rest/v1/beds/{int(bed_id)}", cookie)
    patients = resource.get("patients") or []
    if isinstance(patients, dict):
        patients = [patients]
    if patients or str(resource.get("status") or "").upper() == "OCCUPIED":
        raise ApiError(
            409,
            "bed_occupied",
            "This bed has just been assigned to another patient. Please choose another bed.",
        )


def _create_ipd_visit(patient_uuid: str, location_uuid: str, cookie: str) -> str:
    saved = openmrs_call(
        "POST",
        "/openmrs/ws/rest/v1/visit",
        cookie,
        {
            "patient": patient_uuid,
            "visitType": IPD_VISIT_TYPE,
            "location": location_uuid,
            "startDatetime": now_openmrs(),
        },
    )
    visit_uuid = saved.get("uuid") if isinstance(saved, dict) else ""
    if not visit_uuid:
        raise ApiError(502, "openmrs_error", "We couldn't complete the admission request. Please try again.")
    return str(visit_uuid)


def _create_admission_encounter_on_visit(
    *,
    patient_uuid: str,
    visit_uuid: str,
    location_uuid: str,
    provider_uuid: str,
    cookie: str,
) -> str:
    saved = openmrs_call(
        "POST",
        "/openmrs/ws/rest/v1/encounter",
        cookie,
        {
            "patient": patient_uuid,
            "encounterType": ADMISSION_ENCOUNTER,
            "visit": visit_uuid,
            "location": location_uuid,
            "encounterDatetime": now_openmrs(),
            "encounterProviders": [
                {"provider": provider_uuid, "encounterRole": UNKNOWN_ENCOUNTER_ROLE}
            ],
        },
    )
    encounter_uuid = saved.get("uuid") if isinstance(saved, dict) else ""
    if not encounter_uuid:
        raise ApiError(502, "openmrs_error", "We couldn't complete the admission request. Please try again.")
    return str(encounter_uuid)


def _open_ipd_visit(patient_uuid: str, cookie: str) -> dict[str, Any] | None:
    for visit in _open_visits(patient_uuid, cookie):
        if _visit_type_is_ipd(visit):
            return visit
    return None


def _create_adt_encounter(
    *,
    patient_uuid: str,
    encounter_type: str,
    location_uuid: str,
    provider_uuid: str,
    cookie: str,
    visit_type_uuid: str | None = None,
    visit_uuid: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "patientUuid": patient_uuid,
        "encounterTypeUuid": encounter_type,
        "locationUuid": location_uuid,
        "providers": [{"uuid": provider_uuid}],
        "observations": [],
        "encounterDateTime": now_openmrs(),
    }
    if visit_uuid:
        payload["visitUuid"] = visit_uuid
    elif visit_type_uuid:
        payload["visitTypeUuid"] = visit_type_uuid
    saved = openmrs_call("POST", "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", cookie, payload)
    encounter_uuid = saved.get("encounterUuid") or saved.get("encounter") or ""
    if isinstance(encounter_uuid, dict):
        encounter_uuid = encounter_uuid.get("uuid") or ""
    if not encounter_uuid:
        raise ApiError(502, "openmrs_error", "We couldn't complete this ward request. Please try again.")
    return str(encounter_uuid)


def _assign_bed(bed_id: int, patient_uuid: str, encounter_uuid: str, cookie: str) -> dict[str, Any]:
    payload = openmrs_call(
        "POST",
        f"/openmrs/ws/rest/v1/beds/{int(bed_id)}",
        cookie,
        {"patientUuid": patient_uuid, "encounterUuid": encounter_uuid},
    )
    return payload if isinstance(payload, dict) else {}


def _attach_billing(stay: dict[str, Any], callback: Any) -> dict[str, Any]:
    try:
        import accommodation as billing

        stay["billing"] = callback(billing)
    except Exception:
        stay["billing"] = {
            "status": "needs_attention",
            "message": "Accommodation billing needs attention.",
        }
    return stay


def _admin_as_of(body: dict[str, Any], user: dict[str, Any]) -> Any:
    raw = body.get("asOf")
    if raw in (None, ""):
        return None
    if not _is_admin(user):
        return None
    import accommodation as billing

    return billing.parse_as_of(raw)


def _admit_location_uuid(body: dict[str, Any], cookie: str) -> str:
    location_uuid = str(body.get("locationUuid") or "").strip()
    if location_uuid:
        return location_uuid
    found = _login_location_uuids(cookie)
    return found[0] if found else ""


def _validate_optional_admit_visit(patient_uuid: str, visit_uuid: str, cookie: str) -> dict[str, Any] | None:
    if not visit_uuid:
        return None
    visit = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}?v=custom:(uuid,stopDatetime,patient:(uuid),visitType:(name,uuid))",
        cookie,
    )
    if not isinstance(visit, dict) or not visit.get("uuid"):
        raise ApiError(404, "visit_not_found", "This visit was not found.")
    visit_patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    if visit_patient.get("uuid") and visit_patient.get("uuid") != patient_uuid:
        raise ApiError(409, "wrong_patient", "This visit does not belong to this patient.")
    return visit


def _admit_already_requested(patient_uuid: str, cookie: str) -> dict[str, Any]:
    stay = build_patient_stay(patient_uuid, cookie, catch_up_billing=False)
    stay["alreadyRequested"] = True
    stay["message"] = "Admission already requested. Nursing will assign a bed."
    return stay


def create_admit_decision(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_clinical_user(cookie)
    brief = _patient_brief(patient_uuid, cookie)
    optional_visit = _validate_optional_admit_visit(
        patient_uuid,
        str(body.get("visitUuid") or "").strip(),
        cookie,
    )
    if current_assignment(patient_uuid, cookie, scan_board=True):
        raise ApiError(409, "already_admitted", "This patient already has an active admission.")
    existing = _open_ipd_admission(patient_uuid, cookie)
    if existing or (optional_visit and _visit_type_is_ipd(optional_visit) and not optional_visit.get("stopDatetime")):
        return _admit_already_requested(patient_uuid, cookie)
    location_uuid = _admit_location_uuid(body, cookie)
    if not location_uuid:
        raise ApiError(
            422,
            "location_required",
            "We couldn't complete the admission request. Please try again.",
        )
    provider = _provider_uuid(str(user.get("uuid") or ""), cookie)
    visit_uuid = _create_ipd_visit(patient_uuid, location_uuid, cookie)
    encounter_uuid = _create_admission_encounter_on_visit(
        patient_uuid=patient_uuid,
        visit_uuid=visit_uuid,
        location_uuid=location_uuid,
        provider_uuid=provider,
        cookie=cookie,
    )
    _end_open_non_ipd_visits(patient_uuid, cookie)
    stay = build_patient_stay(patient_uuid, cookie, catch_up_billing=False)
    stay["message"] = "Admission requested. Nursing will assign a bed."
    stay["patient"] = brief
    if not stay.get("admissionEncounterUuid"):
        stay["admissionEncounterUuid"] = encounter_uuid
    if not stay.get("visitUuid"):
        created = _open_ipd_admission(patient_uuid, cookie)
        visit = created.get("visit") if isinstance((created or {}).get("visit"), dict) else {}
        stay["visitUuid"] = str(visit.get("uuid") or "")
        stay["visitStartDatetime"] = str(visit.get("startDatetime") or "")
        stay["admissionEncounterUuid"] = str((created or {}).get("uuid") or encounter_uuid)
    stay["awaiting"] = True
    _emit_admit_requested_notification(
        patient_uuid=patient_uuid,
        visit_uuid=str(stay.get("visitUuid") or visit_uuid or ""),
        brief=brief if isinstance(brief, dict) else {},
        user=user,
        cookie=cookie,
        request_id=str(body.get("requestId") or "").strip(),
    )
    return stay


def _emit_admit_requested_notification(
    *,
    patient_uuid: str,
    visit_uuid: str,
    brief: dict[str, Any],
    user: dict[str, Any],
    cookie: str,
    request_id: str,
) -> None:
    """Notify Nursing after a new admission request write succeeds."""
    try:
        import notifications as staff_notes
        import server as core

        username = str(user.get("username") or "").strip()
        display = username or "Doctor"
        try:
            session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
            session_user = session.get("user") if isinstance(session, dict) else {}
            if isinstance(session_user, dict):
                person = session_user.get("person") if isinstance(session_user.get("person"), dict) else {}
                display = (
                    str(person.get("display") or "").strip()
                    or str(session_user.get("display") or "").strip()
                    or display
                )
        except Exception:
            pass
        staff_notes.emit_admit_requested(
            patient_uuid=patient_uuid,
            visit_uuid=visit_uuid,
            patient_name=str(brief.get("name") or "Patient"),
            mrn=str(brief.get("mrn") or "—"),
            sender_username=username or "doctor",
            sender_display=display,
            request_id=request_id,
        )
    except Exception:
        # Admission already requested; never fail ward handoff on a notify miss.
        return


def assign_bed(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_assign_user(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    bed_uuid = str(body.get("bedUuid") or "").strip()
    request_id = str(body.get("requestId") or "").strip()
    if not patient_uuid or not bed_uuid:
        raise ApiError(422, "invalid_body", "Choose a patient and an available bed.")
    _require_active_patient(patient_uuid, cookie)
    if current_assignment(patient_uuid, cookie):
        raise ApiError(409, "already_admitted", "This patient already has an active admission.")
    bed = _find_bed(bed_uuid, cookie, _body_bed_id(body))
    if bed["status"] != "AVAILABLE" or bed.get("patientUuid"):
        raise ApiError(
            409,
            "bed_occupied",
            "This bed has just been assigned to another patient. Please choose another bed.",
        )
    if not bed.get("bedId"):
        raise ApiError(502, "openmrs_error", "We couldn't complete the bed assignment. Please try again.")
    key = request_id or f"assign:{patient_uuid}:{bed_uuid}"
    with IDEMPOTENCY_LOCK:
        prior = IDEMPOTENCY.get(key) or {}
        if prior.get("status") == "pending":
            raise ApiError(409, "in_progress", "This bed assignment is already being completed.")
        IDEMPOTENCY[key] = {"status": "pending"}
    try:
        _end_open_non_ipd_visits(patient_uuid, cookie)
        provider = _provider_uuid(str(user.get("uuid") or ""), cookie)
        _assert_bed_available(int(bed["bedId"]), cookie)
        existing_admission = _open_ipd_admission(patient_uuid, cookie)
        existing_ipd = _open_ipd_visit(patient_uuid, cookie)
        if existing_admission:
            encounter_uuid = str(existing_admission.get("uuid") or "")
            if not encounter_uuid:
                raise ApiError(502, "openmrs_error", "We couldn't complete this ward request. Please try again.")
        elif existing_ipd:
            encounter_uuid = _create_adt_encounter(
                patient_uuid=patient_uuid,
                encounter_type=ADMISSION_ENCOUNTER,
                location_uuid=str(bed["areaUuid"]),
                provider_uuid=provider,
                cookie=cookie,
                visit_uuid=str(existing_ipd.get("uuid") or ""),
            )
        else:
            encounter_uuid = _create_adt_encounter(
                patient_uuid=patient_uuid,
                encounter_type=ADMISSION_ENCOUNTER,
                location_uuid=str(bed["areaUuid"]),
                provider_uuid=provider,
                cookie=cookie,
                visit_type_uuid=IPD_VISIT_TYPE,
            )
        _assert_bed_available(int(bed["bedId"]), cookie)
        _assign_bed(int(bed["bedId"]), patient_uuid, encounter_uuid, cookie)
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[key] = {"status": "done"}
        stay = build_patient_stay(patient_uuid, cookie, catch_up_billing=False)
        stay["message"] = f"Admitted to {bed['areaName']} · {bed['bedNumber']}."
        as_of = _admin_as_of(body, user)
        return _attach_billing(
            stay,
            lambda billing: billing.after_assignment(
                patient_uuid=patient_uuid,
                area_uuid=str(bed["areaUuid"]),
                area_name=str(bed["areaName"]),
                bed_number=str(bed["bedNumber"]),
                encounter_uuid=encounter_uuid,
                cookie=cookie,
                request_id=request_id or None,
                as_of=as_of,
            ),
        )
    except Exception:
        with IDEMPOTENCY_LOCK:
            if (IDEMPOTENCY.get(key) or {}).get("status") == "pending":
                IDEMPOTENCY.pop(key, None)
        raise


def transfer_bed(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_assign_user(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    bed_uuid = str(body.get("bedUuid") or "").strip()
    if not patient_uuid or not bed_uuid:
        raise ApiError(422, "invalid_body", "Choose an available bed to transfer to.")
    current = current_assignment(patient_uuid, cookie, scan_board=True)
    if not current:
        raise ApiError(409, "not_admitted", "This patient is not assigned to a bed.")
    destination = _find_bed(bed_uuid, cookie, _body_bed_id(body))
    if destination["status"] != "AVAILABLE" or destination.get("patientUuid"):
        raise ApiError(
            409,
            "bed_occupied",
            "This bed has just been assigned to another patient. Please choose another bed.",
        )
    if str(destination.get("bedUuid")) == str(current.get("bedUuid")) or (
        destination.get("bedId") is not None and destination.get("bedId") == current.get("bedId")
    ):
        raise ApiError(409, "same_bed", "Choose a different bed for the transfer.")
    _assert_bed_available(int(destination["bedId"]), cookie)
    provider = _provider_uuid(str(user.get("uuid") or ""), cookie)
    previous_encounter = None
    try:
        import accommodation as billing

        rows = billing.list_adt_encounters(patient_uuid, cookie)
        previous_encounter = rows[0] if rows else None
    except Exception:
        previous_encounter = None
    existing_ipd = _open_ipd_visit(patient_uuid, cookie)
    encounter_uuid = _create_adt_encounter(
        patient_uuid=patient_uuid,
        encounter_type=TRANSFER_ENCOUNTER,
        location_uuid=str(destination["areaUuid"]),
        provider_uuid=provider,
        cookie=cookie,
        visit_uuid=str((existing_ipd or {}).get("uuid") or "") or None,
        visit_type_uuid=None if existing_ipd else IPD_VISIT_TYPE,
    )
    _assign_bed(int(destination["bedId"]), patient_uuid, encounter_uuid, cookie)
    stay = build_patient_stay(patient_uuid, cookie, catch_up_billing=False)
    stay["message"] = (
        f"Transferred from {current.get('areaName')} · {current.get('bedNumber')} "
        f"to {destination['areaName']} · {destination['bedNumber']}."
    )
    stay["previous"] = {
        "areaName": current.get("areaName"),
        "bedNumber": current.get("bedNumber"),
    }
    as_of = _admin_as_of(body, user)
    return _attach_billing(
        stay,
        lambda billing: billing.after_transfer(
            patient_uuid=patient_uuid,
            previous_area_uuid=str(current.get("areaUuid") or ""),
            previous_area_name=str(current.get("areaName") or ""),
            previous_bed_number=str(current.get("bedNumber") or ""),
            previous_encounter_uuid=(previous_encounter or {}).get("uuid"),
            previous_start=(previous_encounter or {}).get("datetime"),
            area_uuid=str(destination["areaUuid"]),
            area_name=str(destination["areaName"]),
            bed_number=str(destination["bedNumber"]),
            encounter_uuid=encounter_uuid,
            cookie=cookie,
            as_of=as_of,
        ),
    )


def _void_openmrs_record(path: str, cookie: str, reason: str) -> None:
    try:
        openmrs_call("POST", path, cookie, {"voided": True, "voidReason": reason})
        return
    except ApiError as error:
        if error.status == 404:
            return
    try:
        openmrs_call("DELETE", path, cookie, None, allow_empty=True)
    except ApiError as error:
        if error.status == 404:
            return
        raise


def _void_open_admit_dispositions(patient_uuid: str, cookie: str) -> None:
    """Clear an admit decision that still sits on an open visit with no bed."""
    payload = openmrs_call(
        "GET",
        f"/openmrs/ws/rest/v1/obs?patient={quote(patient_uuid)}&concept={DISPOSITION_CONCEPT}"
        "&v=custom:(uuid,voided,value:(uuid,display),encounter:(visit:(uuid,stopDatetime)))",
        cookie,
    )
    for row in payload.get("results") or []:
        if not isinstance(row, dict) or row.get("voided") or not _is_admit_obs(row):
            continue
        encounter = row.get("encounter") if isinstance(row.get("encounter"), dict) else {}
        visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
        if visit.get("stopDatetime"):
            continue
        obs_uuid = str(row.get("uuid") or "").strip()
        if not obs_uuid:
            continue
        _void_openmrs_record(
            f"/openmrs/ws/rest/v1/obs/{quote(obs_uuid)}",
            cookie,
            "Admission canceled before a bed was assigned",
        )


def cancel_waiting_admission(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Remove a patient who is waiting for a bed. Occupied beds stay on Discharge."""
    require_assign_user(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    if not patient_uuid:
        raise ApiError(422, "invalid_body", "Choose a patient waiting for a bed.")
    _require_active_patient(patient_uuid, cookie)
    if current_assignment(patient_uuid, cookie, scan_board=True):
        raise ApiError(
            409,
            "already_admitted",
            "This patient is already on a bed. Use Discharge to end the admission.",
        )
    admission = _open_ipd_admission(patient_uuid, cookie)
    open_ipd = _open_ipd_visit(patient_uuid, cookie)
    if not admission and not open_ipd and not _disposition_awaiting(patient_uuid, cookie):
        listed = any(
            str(row.get("patientUuid") or "") == patient_uuid
            for row in _awaiting_patients(cookie)
        )
        if not listed:
            raise ApiError(
                409,
                "not_waiting",
                "This patient is not waiting for a bed. Refresh the admission list.",
            )
    if current_assignment(patient_uuid, cookie, scan_board=True):
        raise ApiError(
            409,
            "already_admitted",
            "This patient is already on a bed. Use Discharge to end the admission.",
        )
    visit = admission.get("visit") if isinstance((admission or {}).get("visit"), dict) else {}
    visit_uuid = str(visit.get("uuid") or "").strip()
    if not visit_uuid and open_ipd:
        visit_uuid = str(open_ipd.get("uuid") or "").strip()
    if visit_uuid:
        _end_visit(visit_uuid, cookie)
        remaining = _open_ipd_visit(patient_uuid, cookie)
        if remaining:
            _end_visit(str(remaining.get("uuid") or visit_uuid), cookie)
        if _open_ipd_visit(patient_uuid, cookie):
            raise ApiError(
                409,
                "cancel_incomplete",
                "The admission is still open. Refresh the list and try again.",
            )
    encounter_uuid = str((admission or {}).get("uuid") or "").strip()
    if encounter_uuid:
        try:
            _void_openmrs_record(
                f"/openmrs/ws/rest/v1/encounter/{quote(encounter_uuid)}",
                cookie,
                "Admission canceled before a bed was assigned",
            )
        except ApiError:
            # The visit is already closed, so the patient is off the waiting list.
            pass
    try:
        _void_open_admit_dispositions(patient_uuid, cookie)
    except ApiError:
        if _patient_awaiting(patient_uuid, cookie) or _open_ipd_visit(patient_uuid, cookie):
            raise ApiError(
                409,
                "cancel_incomplete",
                "This admission could not be canceled. Refresh the list and try again.",
            ) from None
    if (
        _patient_awaiting(patient_uuid, cookie)
        or _open_ipd_visit(patient_uuid, cookie)
        or any(
            str(row.get("patientUuid") or "") == patient_uuid
            for row in _awaiting_patients(cookie)
        )
    ):
        raise ApiError(
            409,
            "cancel_incomplete",
            "This admission could not be canceled. Refresh the list and try again.",
        )
    try:
        import notifications as staff_notes

        staff_notes.expire_patient_event(patient_uuid, staff_notes.EVENT_ADMIT_REQUESTED)
    except Exception:
        pass
    brief = _safe_patient_brief(patient_uuid, cookie) or {
        "uuid": patient_uuid,
        "name": "Patient",
        "mrn": "—",
        "sex": "—",
        "age": "—",
    }
    message = "Admission canceled. This patient is no longer waiting for a bed."
    if visit_uuid:
        message = (
            "Admission canceled. This patient is no longer waiting for a bed. "
            "Reception can start a new visit if they are still here."
        )
    return {
        "status": "ok",
        "message": message,
        "patient": brief,
        "assignment": None,
        "awaiting": False,
        "visitUuid": "",
        "visitStartDatetime": "",
        "admissionEncounterUuid": "",
    }


def discharge_patient(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_assign_user(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    if not patient_uuid:
        raise ApiError(422, "invalid_body", "Choose a patient to discharge.")
    _require_active_patient(patient_uuid, cookie)
    current = current_assignment(patient_uuid, cookie, scan_board=True)
    if not current:
        raise ApiError(409, "not_admitted", "This patient is not assigned to a bed.")
    provider = _provider_uuid(str(user.get("uuid") or ""), cookie)
    previous_encounter = None
    try:
        import accommodation as billing

        rows = billing.list_adt_encounters(patient_uuid, cookie)
        previous_encounter = rows[0] if rows else None
    except Exception:
        previous_encounter = None
    # Bahmni discharge must target the open IPD visit. Without visitUuid, OpenMRS
    # tries to invent a visit with no type and fails ("Visit Type is required").
    open_visit = _open_ipd_visit(patient_uuid, cookie) or (
        (_open_visits(patient_uuid, cookie) or [None])[0]
    )
    visit_uuid = str((open_visit or {}).get("uuid") or "").strip()
    if not visit_uuid:
        raise ApiError(
            409,
            "visit_required",
            "This patient has a bed but no open hospital stay. Ask a supervisor to review the admission before discharge.",
        )
    openmrs_call(
        "POST",
        "/openmrs/ws/rest/v1/bahmnicore/discharge",
        cookie,
        {
            "patientUuid": patient_uuid,
            "encounterTypeUuid": DISCHARGE_ENCOUNTER,
            "locationUuid": str(current.get("areaUuid") or ""),
            "visitUuid": visit_uuid,
            "providers": [{"uuid": provider}],
            "observations": [],
            "encounterDateTime": now_openmrs(),
        },
        allow_empty=True,
    )
    # Bahmni sometimes leaves the IPD visit open after discharge; close it so the
    # patient does not linger on Awaiting.
    if _open_ipd_visit(patient_uuid, cookie) or any(
        str(row.get("uuid") or "") == visit_uuid for row in _open_visits(patient_uuid, cookie)
    ):
        _end_visit(visit_uuid, cookie)
    remaining = current_assignment(patient_uuid, cookie, scan_board=True)
    stay = {
        "status": "ok",
        "message": "Patient discharged. Bed released.",
        "patient": _patient_brief(patient_uuid, cookie),
        "previous": {
            "areaName": current.get("areaName"),
            "bedNumber": current.get("bedNumber"),
        },
        "assignment": remaining,
        "bedReleased": remaining is None,
    }
    as_of = _admin_as_of(body, user)
    return _attach_billing(
        stay,
        lambda billing: billing.after_discharge(
            patient_uuid=patient_uuid,
            area_uuid=str(current.get("areaUuid") or ""),
            area_name=str(current.get("areaName") or ""),
            bed_number=str(current.get("bedNumber") or ""),
            cookie=cookie,
            encounter_uuid=(previous_encounter or {}).get("uuid"),
            start=(previous_encounter or {}).get("datetime"),
            as_of=as_of,
        ),
    )
