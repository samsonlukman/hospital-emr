#!/usr/bin/env python3
"""Doctor → Reception patient call (compat wrapper over staff notifications).

Preserves the existing call-patient / patient-calls HTTP contract while storing
events in the persistent notifications SQLite store.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from urllib.parse import parse_qs, quote

import consultation as clinical
import notifications as staff_notes
import registration as reception
import server as core
from server import ApiError

CALL_TTL_SECONDS = staff_notes.PATIENT_CALLED_TTL_SECONDS
DEDUPE_SECONDS = staff_notes.PATIENT_CALLED_DEDUPE_SECONDS

# Phase-1 test DB path (overridable). Production uses ABIKAN_NOTIFICATIONS_DB.
_TEST_DB: str | None = None


def _db_path() -> str | None:
    return _TEST_DB


def _text(value: Any) -> str:
    return str(value or "").strip()


def _doctor_display(user: dict[str, Any], cookie: str) -> str:
    username = _text(user.get("username")) or "Doctor"
    try:
        session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
    except ApiError:
        session = {}
    session_user = session.get("user") if isinstance(session, dict) else {}
    if not isinstance(session_user, dict):
        session_user = {}
    person = session_user.get("person") if isinstance(session_user.get("person"), dict) else {}
    display = _text(person.get("display")) or _text(session_user.get("display")) or username
    if display.lower().startswith("dr"):
        return display
    return f"Dr. {display}"


def _assert_visit_callable(patient_uuid: str, visit_uuid: str, cookie: str) -> dict[str, Any]:
    import clinical_queue as queue

    visit = clinical._openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}?v={queue.VISIT_REPRESENTATION}",
        cookie,
    )
    if not isinstance(visit, dict) or not visit.get("uuid"):
        raise ApiError(404, "visit_not_found", "This visit was not found.")
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    if _text(patient.get("uuid")) != patient_uuid:
        raise ApiError(409, "wrong_patient", "This visit does not belong to this patient.")
    if visit.get("stopDatetime"):
        raise ApiError(409, "visit_ended", "This visit has already ended.")
    visit_type = queue.visit_type_name(visit)
    if not queue.is_queue_visit_type(visit_type):
        raise ApiError(
            409,
            "visit_not_callable",
            "Only outpatient consultation visits can be called to Reception.",
        )
    today = queue.hospital_today()
    if not queue.started_on_hospital_day(visit.get("startDatetime"), today):
        raise ApiError(
            409,
            "visit_not_today",
            "Only today's consultation patients can be called to Reception.",
        )
    return visit


def clinical_queue_row(visit: dict[str, Any]) -> dict[str, str]:
    import clinical_queue as queue

    mapped = queue.row_from_visit(visit) or {}
    return {
        "patientName": _text(mapped.get("patient")) or "Patient",
        "mrn": _text(mapped.get("mrn")) or "—",
        "dailyVisitNumber": _text(mapped.get("dailyVisitNumber")),
    }


def _serialize_call(notification: dict[str, Any], *, duplicate: bool = False) -> dict[str, Any]:
    payload = notification.get("payload") if isinstance(notification.get("payload"), dict) else {}
    status = notification.get("status")
    call_status = "acked" if status == staff_notes.STATUS_ACKED else "pending"
    return {
        "id": notification["id"],
        "createdAt": notification["createdAt"],
        "patientUuid": notification.get("patientUuid") or "",
        "visitUuid": notification.get("visitUuid") or "",
        "patientName": notification.get("patientName") or "Patient",
        "mrn": notification.get("mrn") or "—",
        "dailyVisitNumber": _text(payload.get("dailyVisitNumber")),
        "doctorName": notification.get("senderDisplay") or "Doctor",
        "doctorUsername": notification.get("senderUsername") or "",
        "status": call_status,
        "message": notification.get("message") or "",
        "duplicate": bool(duplicate),
    }


def create_patient_call(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = clinical.require_clinician(cookie)
    patient_uuid = _text(body.get("patientUuid"))
    visit_uuid = _text(body.get("visitUuid"))
    if not patient_uuid or not visit_uuid:
        raise ApiError(422, "invalid_body", "Choose a patient from today's list.")
    request_id = _text(body.get("requestId"))

    visit = _assert_visit_callable(patient_uuid, visit_uuid, cookie)
    row = clinical_queue_row(visit)
    patient_name = _text(body.get("patientName")) or row["patientName"]
    mrn = _text(body.get("mrn")) or row["mrn"]
    daily = _text(body.get("dailyVisitNumber")) or row.get("dailyVisitNumber") or ""

    doctor_name = _doctor_display(user, cookie)
    doctor_username = _text(user.get("username"))
    message = f"{doctor_name} is calling {patient_name}"
    if daily:
        message = f"{message} (No. {daily})"

    recent = staff_notes.find_recent_patient_called(
        visit_uuid=visit_uuid,
        sender_username=doctor_username,
        within_seconds=DEDUPE_SECONDS,
        path=_db_path(),
    )
    if request_id:
        idempotency_key = f"patient_called:request:{request_id}"
        if recent and _text(recent.get("idempotencyKey")) != idempotency_key:
            return {"status": "ok", "call": _serialize_call(recent, duplicate=True), "duplicate": True}
    else:
        if recent:
            return {"status": "ok", "call": _serialize_call(recent, duplicate=True), "duplicate": True}
        idempotency_key = f"patient_called:auto:{visit_uuid}:{doctor_username}:{os.urandom(8).hex()}"

    result = staff_notes.emit(
        event_type=staff_notes.EVENT_PATIENT_CALLED,
        title="Patient Call",
        message=message,
        sender_username=doctor_username,
        sender_display=doctor_name,
        recipient_scope=staff_notes.SCOPE_WORKPLACE,
        recipient_workplace=staff_notes.WORKPLACE_REGISTRATION,
        patient_uuid=patient_uuid,
        visit_uuid=visit_uuid,
        mrn=mrn or "—",
        patient_name=patient_name,
        # Reception should be able to open the patient's record directly from the call.
        action_href=f"#/reception/record/{patient_uuid}",
        priority=staff_notes.PRIORITY_HIGH,
        speak=True,
        ttl_seconds=CALL_TTL_SECONDS,
        idempotency_key=idempotency_key,
        payload={"dailyVisitNumber": daily},
        path=_db_path(),
    )
    return {
        "status": "ok",
        "call": _serialize_call(result["notification"], duplicate=result["duplicate"]),
        "duplicate": bool(result["duplicate"]),
    }


def list_pending_calls(cookie: str, raw_path: str = "") -> dict[str, Any]:
    reception.require_registrar(cookie)
    listed = staff_notes.list_for_session(cookie, raw_path, path=_db_path())
    calls = [
        _serialize_call(item)
        for item in listed.get("notifications") or []
        if item.get("eventType") == staff_notes.EVENT_PATIENT_CALLED
        and item.get("status") in {staff_notes.STATUS_PENDING, staff_notes.STATUS_READ}
    ]
    # Compat: only pending-like (non-acked) patient calls; treat read as still pending in call shape.
    pending = [call for call in calls if call.get("status") == "pending"]
    return {
        "status": "ok",
        "serverTime": listed.get("serverTime") or "",
        "calls": pending,
        "pendingCount": len(pending),
    }


def acknowledge_call(call_id: str, cookie: str) -> dict[str, Any]:
    reception.require_registrar(cookie)
    result = staff_notes.acknowledge(call_id, cookie, path=_db_path())
    return {
        "status": "ok",
        "call": _serialize_call(result["notification"], duplicate=result["duplicate"]),
        "duplicate": bool(result["duplicate"]),
    }


def reset_for_tests() -> None:
    global _TEST_DB
    if not _TEST_DB:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-notifications-", suffix=".sqlite3", delete=False)
        handle.close()
        _TEST_DB = handle.name
        os.environ["ABIKAN_NOTIFICATIONS_DB"] = _TEST_DB
    staff_notes.reset_for_tests(path=_TEST_DB)
