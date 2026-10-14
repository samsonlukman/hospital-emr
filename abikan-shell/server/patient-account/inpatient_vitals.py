"""Nursing vitals — OpenMRS observations on the patient's visit.

Bahmni already records vital signs as numeric CIEL observations. This module
does not create a second clinical store. Nursing lacks Add Observations, so
the constrained service identity performs the OpenMRS write after Hospital EMR
authorization. Each recording is a new set of observations; previous values
are never overwritten or voided.

Inpatient recordings stay on the admission encounter. Outpatient recordings
use the open visit (a Consultation encounter on that visit). If the patient
has no open visit, one is started so the nurse can still record vitals.
"""

from __future__ import annotations

import re
import threading
from typing import Any
from urllib.parse import quote, unquote

import inpatient as ward
import server as core
from server import ApiError

VITALS_MARKER = "ABIKAN_VITALS:v1:"
VITALS_CREATE_LOCK = threading.Lock()
ALLOWED_KEYS = {
    "temperature",
    "pulse",
    "respiratoryRate",
    "systolic",
    "diastolic",
    "spo2",
    "weight",
    "height",
}
FORBIDDEN_FIELDS = {
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
    "visitUuid",
    "providerUuid",
    "recordedBy",
}
VITAL_CONCEPTS: dict[str, dict[str, Any]] = {
    "systolic": {
        "uuid": "5085AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Systolic",
        "unit": "mmHg",
        "low_absolute": 0,
        "hi_absolute": 250,
    },
    "diastolic": {
        "uuid": "5086AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Diastolic",
        "unit": "mmHg",
        "low_absolute": 0,
        "hi_absolute": 150,
    },
    "pulse": {
        "uuid": "5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Pulse",
        "unit": "bpm",
        "low_absolute": 0,
        "hi_absolute": 230,
    },
    "temperature": {
        "uuid": "5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Temperature",
        "unit": "°C",
        "low_absolute": 25,
        "hi_absolute": 47,
    },
    "spo2": {
        "uuid": "5092AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "SpO₂",
        "unit": "%",
        "low_absolute": 0,
        "hi_absolute": 100,
    },
    "weight": {
        "uuid": "5089AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Weight",
        "unit": "kg",
        "low_absolute": 0,
        "hi_absolute": 250,
    },
    "respiratoryRate": {
        "uuid": "5242AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Respiratory Rate",
        "unit": "/min",
        "low_absolute": 0,
        "hi_absolute": 99,
    },
    "height": {
        "uuid": "5090AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "label": "Height",
        "unit": "cm",
        "low_absolute": 10,
        "hi_absolute": 272,
    },
}
CONCEPT_BY_UUID = {
    str(row["uuid"]): key for key, row in VITAL_CONCEPTS.items()
}
READING_ORDER = (
    "systolic",
    "diastolic",
    "pulse",
    "temperature",
    "respiratoryRate",
    "spo2",
    "weight",
    "height",
)


def _is_patient_ipd_admission(admission: dict[str, Any], patient_uuid: str) -> bool:
    patient = admission.get("patient") if isinstance(admission.get("patient"), dict) else {}
    visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
    visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
    return bool(
        patient.get("uuid") == patient_uuid
        and visit.get("uuid")
        and (
            visit_type.get("uuid") == ward.IPD_VISIT_TYPE
            or str(visit_type.get("name") or "").upper() == "IPD"
        )
    )


VISIT_VITALS_REP = (
    "custom:(uuid,startDatetime,stopDatetime,location:(uuid,name),"
    "visitType:(name,uuid),"
    "encounters:(uuid,encounterDatetime,encounterType:(uuid,name),"
    "obs:(uuid,concept:(uuid,display),value,obsDatetime,comment,voided,"
    "creator:(uuid,display))))"
)
ENCOUNTER_VITALS_REP = (
    "custom:(uuid,encounterDatetime,voided,patient:(uuid),location:(uuid,name),"
    "visit:(uuid,startDatetime,stopDatetime,visitType:(uuid,name),location:(uuid,name)),"
    "obs:(uuid,obsDatetime,value,comment,voided,concept:(uuid,display),"
    "creator:(uuid,display)))"
)


def _visit_is_open(visit: dict[str, Any]) -> bool:
    return bool(visit.get("uuid")) and not visit.get("stopDatetime")


def _consultation_encounter_uuid(visit: dict[str, Any]) -> str:
    for encounter in visit.get("encounters") or []:
        if not isinstance(encounter, dict) or encounter.get("voided"):
            continue
        encounter_type = (
            encounter.get("encounterType")
            if isinstance(encounter.get("encounterType"), dict)
            else {}
        )
        if (
            encounter_type.get("uuid") == ward.CONSULTATION_ENCOUNTER
            or str(encounter_type.get("name") or "") == "Consultation"
        ):
            uuid = str(encounter.get("uuid") or "").strip()
            if uuid:
                return uuid
    return ""


def _obs_from_visit(visit: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for encounter in visit.get("encounters") or []:
        if not isinstance(encounter, dict):
            continue
        for obs in encounter.get("obs") or []:
            if isinstance(obs, dict):
                rows.append(obs)
    return rows


def _session_location_uuid(cookie: str) -> str:
    session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
    location = (
        session.get("sessionLocation")
        if isinstance(session.get("sessionLocation"), dict)
        else {}
    )
    return str(location.get("uuid") or "").strip()


def _preferred_open_visit(visits: list[dict[str, Any]]) -> dict[str, Any] | None:
    open_visits = [row for row in visits if _visit_is_open(row)]
    if not open_visits:
        return None
    for visit in open_visits:
        if ward._visit_type_is_ipd(visit):
            return visit
    return max(open_visits, key=lambda row: str(row.get("startDatetime") or ""))


def _context_from_visit(patient_uuid: str, visit: dict[str, Any]) -> dict[str, Any]:
    encounter_uuid = _consultation_encounter_uuid(visit)
    location = visit.get("location") if isinstance(visit.get("location"), dict) else {}
    return {
        "uuid": encounter_uuid,
        "patient": {"uuid": patient_uuid},
        "location": location,
        "visit": visit,
        "obs": _obs_from_visit(visit),
    }


def _load_visit_for_vitals(visit_uuid: str, cookie: str) -> dict[str, Any] | None:
    try:
        visit = ward.openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}?v={VISIT_VITALS_REP}",
            cookie,
        )
    except ApiError as error:
        if error.status in {404, 409}:
            return None
        raise
    return visit if isinstance(visit, dict) and visit.get("uuid") else None


def _visit_context_by_uuid(
    patient_uuid: str,
    visit_uuid: str,
    cookie: str,
) -> dict[str, Any] | None:
    visit = _load_visit_for_vitals(visit_uuid, cookie)
    if not visit:
        return None
    return _context_from_visit(patient_uuid, visit)


def _open_visit_vitals_context(patient_uuid: str, cookie: str) -> dict[str, Any] | None:
    chosen = _preferred_open_visit(ward._open_visits(patient_uuid, cookie))
    visit_uuid = str((chosen or {}).get("uuid") or "").strip()
    if not visit_uuid:
        return None
    visit = _load_visit_for_vitals(visit_uuid, cookie) or chosen
    if not isinstance(visit, dict):
        return None
    return _context_from_visit(patient_uuid, visit)


def _create_consultation_encounter(
    patient_uuid: str,
    visit: dict[str, Any],
    cookie: str,
) -> str:
    location = visit.get("location") if isinstance(visit.get("location"), dict) else {}
    location_uuid = str(location.get("uuid") or "").strip() or _session_location_uuid(cookie)
    visit_uuid = str(visit.get("uuid") or "").strip()
    if not visit_uuid or not location_uuid:
        raise ApiError(
            409,
            "visit_location_missing",
            "This visit does not have a location, so vitals could not be saved. Ask Reception to check the visit.",
        )
    payload: dict[str, Any] = {
        "patient": patient_uuid,
        "encounterType": ward.CONSULTATION_ENCOUNTER,
        "visit": visit_uuid,
        "location": location_uuid,
        "encounterDatetime": ward.now_openmrs(),
    }
    identity = ward._authenticated_nurse_identity(cookie)
    try:
        provider_uuid = ward._provider_uuid(identity.get("userUuid") or "", cookie)
        payload["encounterProviders"] = [
            {"provider": provider_uuid, "encounterRole": ward.UNKNOWN_ENCOUNTER_ROLE}
        ]
    except ApiError:
        pass
    saved = core.openmrs_service_post("/openmrs/ws/rest/v1/encounter", payload)
    encounter_uuid = str((saved or {}).get("uuid") or "").strip()
    if not encounter_uuid:
        raise ApiError(
            502,
            "encounter_create_failed",
            "The vitals could not be saved. Please try again.",
        )
    return encounter_uuid


def _ensure_visit_encounter(
    patient_uuid: str,
    context: dict[str, Any],
    cookie: str,
) -> dict[str, Any]:
    encounter_uuid = str(context.get("uuid") or "").strip()
    if encounter_uuid:
        return context
    visit = context.get("visit") if isinstance(context.get("visit"), dict) else {}
    encounter_uuid = _create_consultation_encounter(patient_uuid, visit, cookie)
    context = {**context, "uuid": encounter_uuid}
    return context


def _ipd_write_context(patient_uuid: str, cookie: str) -> dict[str, Any] | None:
    return ward._open_ipd_admission(patient_uuid, cookie) or ward._active_admission(
        patient_uuid, cookie
    )


def _active_context(patient_uuid: str, cookie: str) -> dict[str, Any]:
    admission = _ipd_write_context(patient_uuid, cookie)
    if admission:
        patient = admission.get("patient") if isinstance(admission.get("patient"), dict) else {}
        visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
        if patient.get("uuid") != patient_uuid or not visit.get("uuid"):
            raise ApiError(
                409,
                "admission_mismatch",
                "The active admission could not be confirmed for this patient.",
            )
        if visit.get("stopDatetime"):
            raise ApiError(
                409,
                "not_admitted",
                "Vitals can be recorded during an open visit.",
            )
        return admission
    context = _open_visit_vitals_context(patient_uuid, cookie)
    if context:
        return _ensure_visit_encounter(patient_uuid, context, cookie)
    return _create_open_visit_context(patient_uuid, cookie)


def _opd_visit_type_uuid() -> str:
    payload = core.openmrs_service_get(
        "/openmrs/ws/rest/v1/visittype?v=custom:(uuid,name,display,retired)"
    )
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if not isinstance(row, dict) or row.get("retired"):
            continue
        name = str(row.get("name") or row.get("display") or "").strip().upper()
        if name == "OPD":
            uuid = str(row.get("uuid") or "").strip()
            if uuid:
                return uuid
    raise ApiError(
        502,
        "visit_type_missing",
        "Vitals could not be saved. Please try again.",
    )


def _vitals_location_uuid(cookie: str) -> str:
    session = _session_location_uuid(cookie)
    if session:
        return session
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
    raise ApiError(
        409,
        "visit_location_missing",
        "Vitals could not be saved because no hospital location is available. Try again.",
    )


def _create_open_visit_context(patient_uuid: str, cookie: str) -> dict[str, Any]:
    location_uuid = _vitals_location_uuid(cookie)
    created = core.openmrs_service_post(
        "/openmrs/ws/rest/v1/visit",
        {
            "patient": patient_uuid,
            "visitType": _opd_visit_type_uuid(),
            "location": location_uuid,
            "startDatetime": ward.now_openmrs(),
        },
    )
    visit_uuid = str((created or {}).get("uuid") or "").strip()
    if not visit_uuid:
        raise ApiError(
            502,
            "visit_failed",
            "The vitals could not be saved. Please try again.",
        )
    visit = _load_visit_for_vitals(visit_uuid, cookie)
    if not isinstance(visit, dict):
        visit = created if isinstance(created, dict) else {"uuid": visit_uuid}
    if not visit.get("location"):
        visit = {**visit, "location": {"uuid": location_uuid}}
    return _ensure_visit_encounter(
        patient_uuid,
        _context_from_visit(patient_uuid, visit),
        cookie,
    )


def _reload_write_context(
    patient_uuid: str,
    encounter_uuid: str,
    cookie: str,
) -> dict[str, Any] | None:
    admission = _ipd_write_context(patient_uuid, cookie)
    if admission and str(admission.get("uuid") or "") == encounter_uuid:
        return admission
    try:
        encounter = ward.openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/encounter/{quote(encounter_uuid)}?v={ENCOUNTER_VITALS_REP}",
            cookie,
        )
    except ApiError:
        encounter = None
    if not isinstance(encounter, dict) or not encounter.get("uuid") or encounter.get("voided"):
        return _open_visit_vitals_context(patient_uuid, cookie)
    patient = encounter.get("patient") if isinstance(encounter.get("patient"), dict) else {}
    if patient.get("uuid") != patient_uuid:
        return None
    return encounter


def _read_context(
    patient_uuid: str,
    cookie: str,
    *,
    visit_uuid: str | None = None,
    admission_encounter_uuid: str | None = None,
) -> tuple[dict[str, Any], bool]:
    active = ward._active_admission(patient_uuid, cookie)
    requested_visit = str(visit_uuid or "").strip()
    requested_admission = str(admission_encounter_uuid or "").strip()
    if active and not requested_visit and not requested_admission:
        return active, True

    admissions = [
        row
        for row in ward._admission_encounters(patient_uuid, cookie)
        if _is_patient_ipd_admission(row, patient_uuid)
    ]
    if requested_visit:
        admissions = [
            row
            for row in admissions
            if str((row.get("visit") or {}).get("uuid") or "") == requested_visit
        ]
    if requested_admission:
        admissions = [
            row for row in admissions if str(row.get("uuid") or "") == requested_admission
        ]
    if not admissions:
        raise ApiError(
            409,
            "admission_history_not_found",
            "No inpatient vitals were found for that admission.",
        )
    selected = admissions[0]
    selected_visit = selected.get("visit") if isinstance(selected.get("visit"), dict) else {}
    active_visit = active.get("visit") if active and isinstance(active.get("visit"), dict) else {}
    is_active = bool(
        active
        and str(active.get("uuid") or "") == str(selected.get("uuid") or "")
        and str(active_visit.get("uuid") or "") == str(selected_visit.get("uuid") or "")
    )
    return selected, is_active


def _format_value(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if not number.is_integer() or "." in str(value).lower() or "e" in str(value).lower():
        text = f"{number:.10f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(int(number))


def _request_marker(request_id: str, identity: dict[str, str]) -> str:
    value = request_id.strip()
    if not value or len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ApiError(422, "request_id_required", "Please try saving these vitals again.")
    user_uuid = identity.get("userUuid", "").strip()
    person_uuid = identity.get("personUuid", "").strip()
    author_name = identity.get("authorName", "").strip()[:64]
    if not user_uuid or not person_uuid or not author_name:
        raise ApiError(409, "author_unavailable", "Your staff identity could not be recorded.")
    return (
        f"{VITALS_MARKER}{value}|{user_uuid}|{person_uuid}|"
        f"{quote(author_name, safe='')}"
    )


def _metadata(comment: Any) -> dict[str, str]:
    text = str(comment or "")
    if not text.startswith(VITALS_MARKER):
        return {}
    parts = text[len(VITALS_MARKER) :].split("|", 3)
    if len(parts) != 4 or not all(parts[:3]):
        return {}
    return {
        "requestId": parts[0],
        "userUuid": parts[1],
        "personUuid": parts[2],
        "authorName": unquote(parts[3]) or "Nurse",
    }


def _parse_values(body: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for key in ALLOWED_KEYS:
        if key not in body or body[key] in (None, ""):
            continue
        raw = body[key]
        if isinstance(raw, bool) or isinstance(raw, (dict, list)):
            raise ApiError(
                422,
                "invalid_vital",
                f"Enter a number for {VITAL_CONCEPTS[key]['label']}.",
            )
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise ApiError(
                422,
                "invalid_vital",
                f"Enter a number for {VITAL_CONCEPTS[key]['label']}.",
            ) from None
        if number != number:  # NaN
            raise ApiError(
                422,
                "invalid_vital",
                f"Enter a number for {VITAL_CONCEPTS[key]['label']}.",
            )
        concept = VITAL_CONCEPTS[key]
        if number < concept["low_absolute"] or number > concept["hi_absolute"]:
            raise ApiError(
                422,
                "vital_out_of_range",
                (
                    f"{concept['label']} must be between {concept['low_absolute']} "
                    f"and {concept['hi_absolute']} {concept['unit']}."
                ),
            )
        values[key] = number
    systolic = values.get("systolic")
    diastolic = values.get("diastolic")
    if (systolic is None) != (diastolic is None):
        raise ApiError(
            422,
            "incomplete_blood_pressure",
            "Enter both systolic and diastolic pressure.",
        )
    if systolic is not None and diastolic is not None and systolic <= diastolic:
        raise ApiError(
            422,
            "invalid_blood_pressure",
            "Systolic pressure must be higher than diastolic.",
        )
    if not values:
        raise ApiError(422, "vitals_required", "Enter at least one vital sign.")
    return values


def _serialize_readings(admission: dict[str, Any]) -> list[dict[str, Any]]:
    encounter_uuid = str(admission.get("uuid") or "")
    visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
    visit_uuid = str(visit.get("uuid") or "")
    grouped: dict[str, dict[str, Any]] = {}
    for obs in admission.get("obs") or []:
        if not isinstance(obs, dict) or obs.get("voided"):
            continue
        concept = obs.get("concept") if isinstance(obs.get("concept"), dict) else {}
        key = CONCEPT_BY_UUID.get(str(concept.get("uuid") or ""))
        if not key:
            continue
        value = _format_value(obs.get("value"))
        if not value:
            continue
        metadata = _metadata(obs.get("comment"))
        recorded_at = str(obs.get("obsDatetime") or "")
        group_key = metadata.get("requestId") or f"{recorded_at}|{encounter_uuid}"
        row = grouped.setdefault(
            group_key,
            {
                "requestId": metadata.get("requestId", ""),
                "recordedAt": recorded_at,
                "recordedBy": metadata.get("authorName")
                or str((obs.get("creator") or {}).get("display") or "—"),
                "authorUserUuid": metadata.get("userUuid", ""),
                "authorPersonUuid": metadata.get("personUuid", ""),
                "encounterUuid": encounter_uuid,
                "visitUuid": visit_uuid,
                "observations": [],
            },
        )
        if recorded_at > str(row["recordedAt"] or ""):
            row["recordedAt"] = recorded_at
        if metadata.get("authorName"):
            row["recordedBy"] = metadata["authorName"]
            row["authorUserUuid"] = metadata.get("userUuid", "")
            row["authorPersonUuid"] = metadata.get("personUuid", "")
        row["observations"].append(
            {
                "uuid": str(obs.get("uuid") or ""),
                "key": key,
                "label": VITAL_CONCEPTS[key]["label"],
                "value": value,
                "unit": VITAL_CONCEPTS[key]["unit"],
                "conceptUuid": VITAL_CONCEPTS[key]["uuid"],
            }
        )
    readings = list(grouped.values())
    for reading in readings:
        reading["observations"].sort(
            key=lambda item: READING_ORDER.index(item["key"])
            if item["key"] in READING_ORDER
            else 99
        )
    readings.sort(key=lambda item: str(item.get("recordedAt") or ""), reverse=True)
    return readings


def _payload(patient_uuid: str, admission: dict[str, Any], is_active: bool) -> dict[str, Any]:
    visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
    return {
        "status": "ok",
        "patientUuid": patient_uuid,
        "visitUuid": str(visit.get("uuid") or ""),
        "admissionEncounterUuid": str(admission.get("uuid") or ""),
        "activeAdmission": is_active,
        "canRecord": _visit_is_open(visit),
        "readings": _serialize_readings(admission),
    }


def _empty_vitals(patient_uuid: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "patientUuid": patient_uuid,
        "visitUuid": "",
        "admissionEncounterUuid": "",
        "activeAdmission": False,
        "canRecord": True,
        "readings": [],
    }


def build_vitals(
    patient_uuid: str,
    cookie: str,
    *,
    visit_uuid: str | None = None,
    admission_encounter_uuid: str | None = None,
) -> dict[str, Any]:
    ward.require_inpatient_view(cookie)
    try:
        admission, is_active = _read_context(
            patient_uuid,
            cookie,
            visit_uuid=visit_uuid,
            admission_encounter_uuid=admission_encounter_uuid,
        )
        return _payload(patient_uuid, admission, is_active)
    except ApiError as error:
        if error.code not in {"admission_history_not_found", "not_admitted"}:
            raise
        context = None
        requested_visit = str(visit_uuid or "").strip()
        if requested_visit:
            context = _visit_context_by_uuid(patient_uuid, requested_visit, cookie)
        elif not str(admission_encounter_uuid or "").strip():
            context = _open_visit_vitals_context(patient_uuid, cookie)
        if context and (context.get("visit") or context.get("obs") or context.get("uuid")):
            return _payload(patient_uuid, context, False)
        if requested_visit or str(admission_encounter_uuid or "").strip():
            raise
        return _empty_vitals(patient_uuid)


def create_vitals(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
) -> dict[str, Any]:
    ward.require_nursing_user(cookie)
    if FORBIDDEN_FIELDS & set(body):
        raise ApiError(
            422,
            "server_fields_only",
            "The nurse, time, patient, and admission are set automatically.",
        )
    values = _parse_values(body)
    admission = _active_context(patient_uuid, cookie)
    identity = ward._authenticated_nurse_identity(cookie)
    request_id = str(body.get("requestId") or "").strip()
    marker = _request_marker(request_id, identity)
    admission_uuid = str(admission.get("uuid") or "")
    if not admission_uuid:
        raise ApiError(
            502,
            "encounter_create_failed",
            "The vitals could not be saved. Please try again.",
        )
    with VITALS_CREATE_LOCK:
        # Reload under the lock so a concurrent retry sees the first write.
        refreshed_admission = ward._active_admission(patient_uuid, cookie)
        if not refreshed_admission or str(refreshed_admission.get("uuid") or "") != admission_uuid:
            refreshed_admission = _reload_write_context(patient_uuid, admission_uuid, cookie)
        if not refreshed_admission or str(refreshed_admission.get("uuid") or "") != admission_uuid:
            raise ApiError(
                409,
                "no_open_visit",
                "Vitals could not be saved. Please try again.",
            )
        existing = _serialize_readings(refreshed_admission)
        prior = next((row for row in existing if row["requestId"] == request_id), None)
        if prior:
            is_active = bool(ward._active_admission(patient_uuid, cookie))
            return {
                **_payload(patient_uuid, refreshed_admission, is_active),
                "reading": prior,
                "duplicate": True,
            }
        observation_datetime = ward.now_openmrs()
        for key, number in values.items():
            concept = VITAL_CONCEPTS[key]
            core.openmrs_service_post(
                "/openmrs/ws/rest/v1/obs",
                {
                    "person": patient_uuid,
                    "concept": concept["uuid"],
                    "value": number,
                    "obsDatetime": observation_datetime,
                    "encounter": admission_uuid,
                    "comment": marker,
                },
            )
        confirmed = ward._active_admission(patient_uuid, cookie)
        if not confirmed or str(confirmed.get("uuid") or "") != admission_uuid:
            confirmed = _reload_write_context(patient_uuid, admission_uuid, cookie)
        confirmed = confirmed or refreshed_admission
        readings = _serialize_readings(confirmed)
        saved = next((row for row in readings if row["requestId"] == request_id), None)
        if not saved:
            raise ApiError(
                502,
                "vitals_not_confirmed",
                "The vitals could not be confirmed. Please try again.",
            )
        is_active = bool(ward._active_admission(patient_uuid, cookie))
        return {
            **_payload(patient_uuid, confirmed, is_active),
            "reading": saved,
            "duplicate": False,
        }
