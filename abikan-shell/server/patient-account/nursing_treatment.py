"""Nurse-led outpatient treatment queue.

Treatment visits are separate from inpatient medication schedules. A treatment
visit may be used for an injection or other medicine given at the hospital
without requiring a bed or a doctor consultation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import inpatient as ward
import notifications as staff_notes
import server as core
from server import ApiError

TREATMENT_VISIT_NAME = "Nursing Treatment"
DRUG_ORDERS_PATH = "/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive"
ORDER_PATH = "/openmrs/ws/rest/v1/order"
ADMINISTRATION_PATH = "/openmrs/ws/rest/v1/ipd/scheduledMedicationAdministrations"
TREATMENT_MARKER = "ABIKAN_TREATMENT:"
TREATMENT_ADMIN_MARKER = "ABIKAN_TREATMENT_ADMIN:v1:"
TREATMENT_REASON_MAX_LENGTH = 80
TREATMENT_NOTE_MAX_LENGTH = 10000
ORDER_REPRESENTATION = (
    "custom:(uuid,orderNumber,patient:(uuid),encounter:(uuid,visit:(uuid)),"
    "careSetting:(name),action,dateActivated,dateStopped,autoExpireDate,voided,"
    "asNeeded,dose,quantity,duration,durationUnits,frequency:(display,name),"
    "route:(display),drug:(uuid,display,dosageForm:(display)),drugNonCoded,concept:(display),orderer:(uuid))"
)


def _display(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display") or value.get("name") or value.get("uuid") or "")
    return str(value or "")


def _active(order: dict[str, Any]) -> bool:
    if order.get("voided") or order.get("dateStopped"):
        return False
    if str(order.get("action") or "").upper() == "DISCONTINUE":
        return False
    expiry = order.get("autoExpireDate")
    if not expiry:
        return True
    try:
        value = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        return value.timestamp() * 1000 >= datetime.now(timezone.utc).timestamp() * 1000
    except ValueError:
        return True


def _administration_data(order: dict[str, Any]) -> tuple[str, str]:
    dosing = order.get("dosingInstructions")
    dosing = dosing if isinstance(dosing, dict) else {}
    raw = dosing.get("administrationInstructions") or order.get("instructions") or ""
    if not isinstance(raw, str):
        return "", ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw, ""
    if not isinstance(parsed, dict):
        return raw, ""
    return (
        str(parsed.get("instructions") or ""),
        str(parsed.get("administrationMode") or "").upper(),
    )


def _order_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("visitDrugOrders") or payload.get("results") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _load_orders(patient_uuid: str) -> list[dict[str, Any]]:
    payload = core.openmrs_service_get(
        f"{DRUG_ORDERS_PATH}?patientUuid={quote(patient_uuid)}"
    )
    orders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _order_rows(payload):
        nested = row.get("drugOrder") if isinstance(row.get("drugOrder"), dict) else {}
        uuid = str(nested.get("uuid") or row.get("uuid") or "")
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        try:
            order = core.openmrs_service_get(
                f"{ORDER_PATH}/{quote(uuid)}?v={ORDER_REPRESENTATION}"
            )
        except ApiError:
            continue
        try:
            extension = core.openmrs_service_get(
                f"/openmrs/ws/rest/v1/bahmnicore/drugOrders/{quote(uuid)}"
            )
        except ApiError:
            extension = {}
        nested = extension.get("drugOrder") if isinstance(extension, dict) else {}
        if isinstance(extension, dict):
            order = {
                **(nested if isinstance(nested, dict) else {}),
                **order,
                **extension,
                "dosingInstructions": (
                    extension.get("dosingInstructions")
                    or (nested.get("dosingInstructions") if isinstance(nested, dict) else {})
                    or order.get("dosingInstructions")
                ),
            }
        if isinstance(order, dict) and _active(order):
            orders.append(order)
    import medication_administration as mar

    mar.apply_dosage_forms(orders)
    return orders


def _load_treatment_visits() -> list[dict[str, Any]]:
    payload = core.openmrs_service_get(
        "/openmrs/ws/rest/v1/visit?includeInactive=false&limit=1000"
        "&v=custom:(uuid,patient:(uuid,display,identifiers:(identifier,preferred)),"
        "visitType:(name,display),location:(name),startDatetime,stopDatetime)"
    )
    rows = payload.get("results") if isinstance(payload, dict) else payload
    return [
        row
        for row in (rows or [])
        if isinstance(row, dict)
        and _display(row.get("visitType")).strip().lower() == TREATMENT_VISIT_NAME.lower()
        and not row.get("stopDatetime")
    ]


def _load_visit_detail(visit_uuid: str, patient_uuid: str) -> dict[str, Any]:
    detail = core.openmrs_service_get(
        f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}"
        "?v=custom:(uuid,patient:(uuid),location:(uuid),encounters:(uuid))"
    )
    if not isinstance(detail, dict):
        raise ApiError(404, "treatment_visit_not_found", "This treatment visit was not found.")
    patient = detail.get("patient") if isinstance(detail.get("patient"), dict) else {}
    if str(patient.get("uuid") or "") != patient_uuid:
        raise ApiError(409, "wrong_patient", "This treatment visit belongs to another patient.")
    encounters = []
    for row in detail.get("encounters") or []:
        encounter_uuid = str(row.get("uuid") or "") if isinstance(row, dict) else ""
        if not encounter_uuid:
            continue
        try:
            encounter = core.openmrs_service_get(
                f"/openmrs/ws/rest/v1/encounter/{quote(encounter_uuid)}"
                "?v=custom:(uuid,patient:(uuid),visit:(uuid),encounterDatetime,"
                "obs:(uuid,concept:(uuid),value,comment,obsDatetime,creator:(display),voided))"
            )
        except ApiError:
            continue
        if isinstance(encounter, dict):
            encounters.append(encounter)
    detail["encounters"] = encounters
    return detail


def _treatment_notes(patient_uuid: str, visit_uuid: str) -> list[dict[str, Any]]:
    try:
        detail = _load_visit_detail(visit_uuid, patient_uuid)
    except ApiError:
        return []
    return [
        {
            "uuid": row["uuid"],
            "patientUuid": row["patientUuid"],
            "visitUuid": row["visitUuid"],
            "authorName": row["authorName"],
            "recordedAt": row["recordedAt"],
            "content": row["content"],
            "requestId": row["requestId"],
        }
        for row in ward._serialize_nursing_notes(detail.get("encounters") or [])
    ]


def _administration_key(visit_uuid: str, order_uuid: str) -> str:
    return f"{TREATMENT_MARKER}{visit_uuid}:{order_uuid}"


def _treatment_admin_comment(
    order_uuid: str,
    outcome: str,
    reason: str,
    identity: dict[str, str],
) -> str:
    fields = (
        order_uuid,
        outcome,
        reason,
        str(identity.get("userUuid") or ""),
        str(identity.get("personUuid") or ""),
        str(identity.get("authorName") or ""),
    )
    return TREATMENT_ADMIN_MARKER + "|".join(quote(value, safe="") for value in fields)


def _create_visit_observation(
    *,
    patient_uuid: str,
    encounter_uuid: str,
    location_uuid: str,
    value: str,
    comment: str,
    observed_at: str,
) -> dict[str, Any]:
    result = core.openmrs_service_post(
        "/openmrs/ws/rest/v1/obs",
        {
            "person": patient_uuid,
            "concept": ward.GENERAL_PATIENT_NOTE_CONCEPT,
            "encounter": encounter_uuid,
            "location": location_uuid,
            "obsDatetime": observed_at,
            "value": value,
            "comment": comment,
        },
    )
    return result if isinstance(result, dict) else {}


def _existing_administrations(patient_uuid: str, visit_uuid: str) -> set[str]:
    """Return treatment actions already recorded on this outpatient visit."""
    try:
        detail = _load_visit_detail(visit_uuid, patient_uuid)
    except ApiError:
        return set()
    completed: set[str] = set()
    for encounter in detail.get("encounters") or []:
        if not isinstance(encounter, dict):
            continue
        for obs in encounter.get("obs") or []:
            if not isinstance(obs, dict) or obs.get("voided"):
                continue
            comment = str(obs.get("comment") or "")
            if not comment.startswith(TREATMENT_ADMIN_MARKER):
                continue
            fields = comment[len(TREATMENT_ADMIN_MARKER) :].split("|", 5)
            if len(fields) < 1:
                continue
            order_uuid = str(fields[0] or "")
            if order_uuid:
                completed.add(_administration_key(visit_uuid, order_uuid))
    return completed


def _existing_inpatient_administrations(patient_uuid: str) -> set[str]:
    """Legacy helper retained for reading old inpatient administration data."""
    try:
        payload = core.openmrs_service_get(
            f"{ADMINISTRATION_PATH}?patientUuid={quote(patient_uuid)}"
        )
    except ApiError:
        return set()
    rows = payload if isinstance(payload, list) else payload.get("results", [])
    keys: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for note in row.get("notes") or []:
            if isinstance(note, dict):
                text = str(note.get("text") or "")
                if text.startswith(TREATMENT_MARKER):
                    keys.add(text.split("|", 1)[0])
    return keys


def _order_summary(order: dict[str, Any]) -> dict[str, Any]:
    import medication_administration as mar

    dosing = order.get("dosingInstructions") if isinstance(order.get("dosingInstructions"), dict) else {}
    instructions, mode = _administration_data(order)
    dose = order.get("dose") if order.get("dose") not in (None, "") else dosing.get("dose")
    units = _display(order.get("doseUnits")) or _display(dosing.get("doseUnits"))
    return {
        "medication": mar.medication_label(order),
        "instructions": instructions,
        "dose": "" if dose in (None, "") else dose,
        "doseUnits": mar._displayed_unit(units, mar._order_form(order)),
        "route": _display(order.get("route")) or _display(dosing.get("route")),
        "frequency": _display(order.get("frequency")) or _display(dosing.get("frequency")),
        "duration": order.get("duration") if order.get("duration") not in (None, "") else dosing.get("duration"),
        "durationUnits": _display(order.get("durationUnits")) or _display(dosing.get("durationUnits")),
        "administrationMode": mode,
    }


def _serialize_visit(
    visit: dict[str, Any],
    order: dict[str, Any],
    completed: bool,
    medications: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    summary = _order_summary(order)
    return {
        "visitUuid": str(visit.get("uuid") or ""),
        "patientUuid": str(patient.get("uuid") or ""),
        "patientName": _display(patient),
        "treatmentVisitStarted": str(visit.get("startDatetime") or ""),
        "orderUuid": str(order.get("uuid") or ""),
        "orderNumber": str(order.get("orderNumber") or ""),
        "medication": summary["medication"],
        "instructions": summary["instructions"],
        "dose": summary["dose"],
        "doseUnits": summary["doseUnits"],
        "route": summary["route"],
        "frequency": summary["frequency"],
        "duration": summary["duration"],
        "durationUnits": summary["durationUnits"],
        "status": "COMPLETED" if completed else "DUE",
        "medications": medications,
        "notes": notes,
    }


def _serialize_waiting_visit(
    visit: dict[str, Any],
    medications: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    return {
        "visitUuid": str(visit.get("uuid") or ""),
        "patientUuid": str(patient.get("uuid") or ""),
        "patientName": _display(patient),
        "treatmentVisitStarted": str(visit.get("startDatetime") or ""),
        "orderUuid": "",
        "orderNumber": "",
        "medication": "No hospital treatment selected",
        "instructions": "Check the patient record or contact the doctor before treatment.",
        "dose": "",
        "doseUnits": "",
        "route": "",
        "frequency": "",
        "duration": None,
        "durationUnits": "",
        "status": "WAITING",
        "medications": medications,
        "notes": notes,
    }


def build_treatment_queue(cookie: str) -> dict[str, Any]:
    ward.require_nursing_user(cookie)
    items: list[dict[str, Any]] = []
    for visit in _load_treatment_visits():
        patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
        patient_uuid = str(patient.get("uuid") or "")
        visit_uuid = str(visit.get("uuid") or "")
        if not patient_uuid or not visit_uuid:
            continue
        completed = _existing_administrations(patient_uuid, visit_uuid)
        all_orders = _load_orders(patient_uuid)
        medications = [_order_summary(order) for order in all_orders]
        notes = _treatment_notes(patient_uuid, visit_uuid)
        matched = False
        for order in all_orders:
            _, mode = _administration_data(order)
            if mode != "HOSPITAL_FOLLOW_UP":
                continue
            matched = True
            order_uuid = str(order.get("uuid") or "")
            key = _administration_key(visit_uuid, order_uuid)
            items.append(_serialize_visit(visit, order, key in completed, medications, notes))
        if not matched:
            items.append(_serialize_waiting_visit(visit, medications, notes))
    items.sort(key=lambda item: (item["status"] != "DUE", item["patientName"].lower()))
    return {"status": "ok", "items": items}


def build_treatment_notes(patient_uuid: str, visit_uuid: str, cookie: str) -> dict[str, Any]:
    ward.require_inpatient_view(cookie)
    return {
        "status": "ok",
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "notes": _treatment_notes(patient_uuid, visit_uuid),
    }


def create_treatment_note(
    patient_uuid: str,
    visit_uuid: str,
    body: dict[str, Any],
    cookie: str,
) -> dict[str, Any]:
    user = ward.require_nursing_user(cookie)
    forbidden = {
        "author",
        "authorName",
        "authorUuid",
        "timestamp",
        "recordedAt",
        "obsDatetime",
        "encounterUuid",
        "patientUuid",
        "visitUuid",
    }
    if forbidden & set(body):
        raise ApiError(422, "server_fields_only", "The note author, time, patient, and visit are set automatically.")
    content = str(body.get("note") or "").strip()
    if not content:
        raise ApiError(422, "note_required", "Enter a treatment note before saving.")
    if len(content) > TREATMENT_NOTE_MAX_LENGTH:
        raise ApiError(422, "note_too_long", "The treatment note is too long.")
    visit = next(
        (row for row in _load_treatment_visits() if str(row.get("uuid") or "") == visit_uuid),
        None,
    )
    if not visit:
        raise ApiError(409, "treatment_visit_closed", "This treatment visit is no longer open.")
    detail = _load_visit_detail(visit_uuid, patient_uuid)
    request_id = str(body.get("requestId") or "").strip()
    identity = ward._authenticated_nurse_identity(cookie)
    marker = ward._request_marker(request_id, identity)
    existing = _treatment_notes(patient_uuid, visit_uuid)
    prior = next((row for row in existing if row["requestId"] == request_id), None)
    if prior:
        return {
            "status": "ok",
            "patientUuid": patient_uuid,
            "visitUuid": visit_uuid,
            "note": prior,
            "duplicate": True,
        }
    location = detail.get("location") if isinstance(detail.get("location"), dict) else {}
    observation_datetime = ward.now_openmrs()
    visit_encounters = [
        row for row in (detail.get("encounters") or [])
        if isinstance(row, dict) and str(row.get("uuid") or "")
    ]
    encounter_uuid = str(visit_encounters[0].get("uuid") or "") if visit_encounters else ""
    if not encounter_uuid:
        raise ApiError(409, "treatment_encounter_unavailable", "This treatment visit has no clinical record yet.")
    _create_visit_observation(
        patient_uuid=patient_uuid,
        encounter_uuid=encounter_uuid,
        location_uuid=str(location.get("uuid") or ""),
        value=content,
        comment=marker,
        observed_at=observation_datetime,
    )
    refreshed = _treatment_notes(patient_uuid, visit_uuid)
    saved = next((row for row in refreshed if row["requestId"] == request_id), None)
    if not saved:
        raise ApiError(502, "note_not_confirmed", "The treatment note could not be confirmed. Please try again.")
    return {
        "status": "ok",
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "note": saved,
        "duplicate": False,
    }


def call_reception(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = ward.require_nursing_user(cookie)
    if set(body) - {"visitUuid"}:
        raise ApiError(422, "server_fields_only", "Only the treatment visit can be called.")
    visit_uuid = str(body.get("visitUuid") or "").strip()
    visit = next(
        (row for row in _load_treatment_visits() if str(row.get("uuid") or "") == visit_uuid),
        None,
    )
    if not visit:
        raise ApiError(409, "treatment_visit_closed", "This nursing treatment visit is no longer open.")
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    try:
        from clinical_queue import name_and_mrn

        patient_name, mrn = name_and_mrn(patient.get("display"), patient.get("identifiers"))
    except Exception:
        patient_name, mrn = _display(patient), "—"
    identity = ward._authenticated_nurse_identity(cookie)
    result = staff_notes.emit_nursing_call_to_reception(
        patient_uuid=patient_uuid,
        visit_uuid=visit_uuid,
        patient_name=patient_name or "Patient",
        mrn=mrn or "—",
        sender_username=str(identity.get("userUuid") or user.get("username") or "nurse"),
        sender_display=str(identity.get("authorName") or "Nursing"),
    )
    return {"status": "ok", "duplicate": bool(result.get("duplicate"))}


def record_treatment(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = ward.require_nursing_user(cookie)
    allowed = {"visitUuid", "orderUuid", "outcome", "reason"}
    if set(body) - allowed:
        raise ApiError(422, "server_fields_only", "Only the treatment result and reason can be recorded.")
    visit_uuid = str(body.get("visitUuid") or "").strip()
    order_uuid = str(body.get("orderUuid") or "").strip()
    outcome = str(body.get("outcome") or "").strip().lower()
    reason = str(body.get("reason") or "").strip()
    if not visit_uuid or not order_uuid:
        raise ApiError(422, "treatment_required", "Choose a treatment.")
    if outcome not in {"given", "held", "not-done"}:
        raise ApiError(422, "outcome_required", "Choose what happened with this treatment.")
    if outcome != "given" and not reason:
        raise ApiError(422, "reason_required", "Record why this treatment was not given.")
    if len(reason) > TREATMENT_REASON_MAX_LENGTH:
        raise ApiError(422, "reason_too_long", "Keep the treatment reason under 80 characters.")
    visit = next(
        (row for row in _load_treatment_visits() if str(row.get("uuid") or "") == visit_uuid),
        None,
    )
    if not visit:
        raise ApiError(409, "treatment_visit_closed", "This nursing treatment visit is no longer open.")
    order = next((row for row in _load_orders(patient_uuid) if str(row.get("uuid") or "") == order_uuid), None)
    if not order:
        raise ApiError(409, "order_unavailable", "This medicine is no longer available for treatment.")
    instructions, mode = _administration_data(order)
    if mode != "HOSPITAL_FOLLOW_UP":
        raise ApiError(409, "wrong_treatment_mode", "This medicine is not scheduled for hospital treatment.")
    key = _administration_key(visit_uuid, order_uuid)
    if key in _existing_administrations(patient_uuid, visit_uuid):
        return {"status": "ok", "duplicate": True, "key": key}
    identity = ward._authenticated_nurse_identity(cookie)
    provider_uuid = ward._provider_uuid(str(user.get("uuid") or ""), cookie)
    if not provider_uuid or not identity.get("authorName"):
        raise ApiError(409, "performer_unavailable", "Your staff identity could not be recorded.")
    drug = order.get("drug") if isinstance(order.get("drug"), dict) else {}
    detail = _load_visit_detail(visit_uuid, patient_uuid)
    encounters = [
        row for row in (detail.get("encounters") or [])
        if isinstance(row, dict) and str(row.get("uuid") or "")
    ]
    encounter_uuid = str(encounters[0].get("uuid") or "") if encounters else ""
    if not encounter_uuid:
        raise ApiError(409, "treatment_encounter_unavailable", "This treatment visit has no clinical record yet.")
    observation_datetime = ward.now_openmrs()
    _create_visit_observation(
        patient_uuid=patient_uuid,
        encounter_uuid=encounter_uuid,
        location_uuid=str((detail.get("location") or {}).get("uuid") or ""),
        value=outcome,
        comment=_treatment_admin_comment(order_uuid, outcome, reason, identity),
        observed_at=observation_datetime,
    )
    if key not in _existing_administrations(patient_uuid, visit_uuid):
        raise ApiError(502, "treatment_not_confirmed", "The treatment could not be recorded. Please try again.")
    return {"status": "ok", "duplicate": False, "key": key}
