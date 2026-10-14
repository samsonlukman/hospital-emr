"""Create Bahmni IPD medication schedules for Hospital EMR inpatient orders.

Installed bahmni-ipd 1.1.1 does not create MAR slots when a drug order is saved.
The IPD drug chart expects an explicit POST to:

    POST /openmrs/ws/rest/v1/ipd/schedule/type/medication

This module is the Hospital EMR-authorized wrapper around that installed API.
It does not store a second medication database.
"""

from __future__ import annotations

import base64
import json
import math
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import inpatient as ward
import medication_administration as mar
import server as core
from server import ApiError

SCHEDULE_PATH = "/openmrs/ws/rest/v1/ipd/schedule/type/medication"
DRUG_ORDERS_PATH = "/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive"
ORDER_REPRESENTATION = (
    "custom:(uuid,orderNumber,patient:(uuid),encounter:(uuid,visit:(uuid)),"
    "careSetting:(name),action,dateActivated,scheduledDate,dateStopped,"
    "autoExpireDate,voided,asNeeded,dose,quantity,frequency:(display,name),"
    "route:(display),drug:(uuid,display),drugNonCoded,concept:(display),orderer:(uuid))"
)
ALREADY_CREATED_MARKER = "slots already created for this drug order"
START_TIME_DURATION_FREQUENCY = "START_TIME_DURATION_FREQUENCY"
MEDICATION_REQUEST = "MEDICATION_REQUEST"
AS_NEEDED_NAMES = {
    "as needed",
    "as-needed",
    "prn",
    "when required",
    "when needed",
    "sos",
}


def _error_text(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "")
        return str(payload.get("message") or payload.get("code") or "")
    return str(payload or "")


def _already_created(payload: Any) -> bool:
    return ALREADY_CREATED_MARKER in _error_text(payload).lower()


def _service_post(path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    if not core.OPENMRS_ADMIN_USER or not core.OPENMRS_ADMIN_PASSWORD:
        raise ApiError(503, "clinical_write_config", "Clinical service is unavailable.")
    token = base64.b64encode(
        f"{core.OPENMRS_ADMIN_USER}:{core.OPENMRS_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        f"{core.OPENMRS_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as error:
        raw = error.read().decode("utf-8") if error.fp else ""
        try:
            parsed = json.loads(raw) if raw else {"message": str(error)}
        except json.JSONDecodeError:
            parsed = {"message": raw or str(error)}
        return error.code, parsed
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(
            502,
            "schedule_unavailable",
            "The ward medication schedule could not be created. Try again.",
        ) from error


def _existing_slots(patient_uuid: str, order_uuid: str) -> list[dict[str, Any]]:
    query = urlencode({"patientUuid": patient_uuid, "orderUuids": order_uuid})
    try:
        payload = core.openmrs_service_get(f"{SCHEDULE_PATH}?{query}")
    except ApiError:
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _order_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = list(payload)
    elif isinstance(payload, dict):
        rows = list(payload.get("visitDrugOrders") or payload.get("results") or [])
        if payload.get("uuid") and payload.get("drug"):
            rows.append(payload)
    else:
        rows = []
    found: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nested_rows = row.get("visitDrugOrders")
        if isinstance(nested_rows, list) and not row.get("uuid"):
            found.extend(_order_rows(nested_rows))
            continue
        nested = row.get("drugOrder")
        if isinstance(nested, dict):
            merged = {**nested, **{key: value for key, value in row.items() if key != "drugOrder"}}
            merged["uuid"] = nested.get("uuid") or row.get("uuid")
            found.append(merged)
        elif row.get("uuid"):
            found.append(row)
    return found


def _load_visit_orders(patient_uuid: str, visit_uuid: str) -> list[dict[str, Any]]:
    payload = core.openmrs_service_get(f"{DRUG_ORDERS_PATH}?patientUuid={quote(patient_uuid)}")
    orders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _order_rows(payload):
        nested = row.get("drugOrder") if isinstance(row.get("drugOrder"), dict) else {}
        order_uuid = str(nested.get("uuid") or row.get("uuid") or "")
        wrapper_visit = row.get("visit") if isinstance(row.get("visit"), dict) else {}
        wrapper_visit_uuid = str(wrapper_visit.get("uuid") or "")
        if wrapper_visit_uuid and wrapper_visit_uuid != visit_uuid:
            continue
        if not order_uuid or order_uuid in seen:
            continue
        seen.add(order_uuid)
        try:
            order = core.openmrs_service_get(
                f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}?v={ORDER_REPRESENTATION}"
            )
        except ApiError:
            continue
        if not isinstance(order, dict):
            continue
        encounter = order.get("encounter") if isinstance(order.get("encounter"), dict) else {}
        visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
        order_visit = str(visit.get("uuid") or wrapper_visit_uuid or "")
        if order_visit != visit_uuid:
            continue
        orders.append(order)
    _include_visit_drug_orders(patient_uuid, visit_uuid, orders, seen)
    return orders


def _include_visit_drug_orders(
    patient_uuid: str,
    visit_uuid: str,
    orders: list[dict[str, Any]],
    seen: set[str],
) -> None:
    """The active-prescription list can omit a medicine. The visit itself is the source."""
    import openmrs_sql

    try:
        rows = openmrs_sql.fetch_all(
            """
            SELECT o.uuid
            FROM orders o
            JOIN order_type ot ON ot.order_type_id = o.order_type_id
            JOIN encounter e ON e.encounter_id = o.encounter_id
            JOIN visit v ON v.visit_id = e.visit_id
            JOIN person p ON p.person_id = o.patient_id
            WHERE v.uuid = %s AND p.uuid = %s AND ot.name = 'Drug Order'
              AND o.voided = 0 AND o.date_stopped IS NULL
            """,
            (visit_uuid, patient_uuid),
        )
    except openmrs_sql.OpenmrsSqlError:
        return
    for row in rows:
        order_uuid = str(row[0] or "")
        if not order_uuid or order_uuid in seen:
            continue
        seen.add(order_uuid)
        try:
            order = core.openmrs_service_get(
                f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}?v={ORDER_REPRESENTATION}"
            )
        except ApiError:
            continue
        if isinstance(order, dict):
            orders.append(order)


def course_slot_count(order: dict[str, Any]) -> int:
    """How many ward doses a course needs. Quantity alone is only one dose."""
    frequency = order.get("frequency") if isinstance(order.get("frequency"), dict) else {}
    units = order.get("durationUnits")
    unit_name = (
        str(units.get("display") or units.get("name") or "")
        if isinstance(units, dict)
        else str(units or "")
    ).lower()
    try:
        per_day = float(frequency.get("frequencyPerDay"))
        duration = float(order.get("duration"))
    except (TypeError, ValueError):
        per_day = 0.0
        duration = 0.0
    if per_day > 0 and duration > 0:
        if "week" in unit_name:
            days = duration * 7
        elif "hour" in unit_name:
            days = duration / 24
        elif "month" in unit_name:
            days = duration * 30
        else:
            days = duration
        count = int(round(per_day * days))
        if count > 0:
            return min(count, 200)
    try:
        dose = float(order.get("dose") or 0) or 1.0
        quantity = float(order.get("quantity") or 0)
    except (TypeError, ValueError):
        return 1
    if quantity > 0 and dose > 0:
        return max(1, int(math.ceil(quantity / dose)))
    return 1


def course_interval_seconds(order: dict[str, Any]) -> int:
    frequency = order.get("frequency") if isinstance(order.get("frequency"), dict) else {}
    try:
        per_day = float(frequency.get("frequencyPerDay"))
    except (TypeError, ValueError):
        per_day = 0.0
    if per_day <= 0:
        return 24 * 60 * 60
    return max(60, int(round(86400 / per_day)))


def _course_details(order_uuid: str) -> dict[str, Any] | None:
    import openmrs_sql

    row = openmrs_sql.fetch_one(
        """
        SELECT ofr.frequency_per_day, do.duration, IFNULL(cn.name, 'Days')
        FROM orders o
        JOIN drug_order do ON do.order_id = o.order_id
        LEFT JOIN order_frequency ofr ON ofr.order_frequency_id = do.frequency
        LEFT JOIN concept_name cn ON cn.concept_id = do.duration_units
            AND cn.voided = 0 AND cn.locale = 'en' AND cn.concept_name_type = 'FULLY_SPECIFIED'
        WHERE o.uuid = %s
        LIMIT 1
        """,
        (order_uuid,),
    )
    if not row:
        return None
    return {
        "frequency": {"frequencyPerDay": row[0]},
        "duration": row[1],
        "durationUnits": str(row[2] or "Days"),
    }


def _ensure_course_slots(order: dict[str, Any]) -> None:
    """Add the rest of the course. The ward sheet otherwise keeps only the first dose."""
    import openmrs_sql

    order_uuid = str(order.get("uuid") or "")
    if not order_uuid:
        return
    try:
        details = _course_details(order_uuid)
        slots = openmrs_sql.fetch_all(
            """
            SELECT s.schedule_id, s.location_id, s.service_type_id, s.creator, s.start_date_time
            FROM ipd_slot s
            JOIN orders o ON o.order_id = s.order_id
            WHERE o.uuid = %s AND s.voided = 0
            ORDER BY s.start_date_time
            """,
            (order_uuid,),
        )
    except openmrs_sql.OpenmrsSqlError:
        return
    if not details or not slots or not isinstance(slots[0][4], datetime):
        return
    needed = course_slot_count({**order, **details})
    if len(slots) >= needed:
        return
    schedule_id, location_id, service_type_id, creator, started = slots[0]
    existing = {row[4] for row in slots if isinstance(row[4], datetime)}
    interval = timedelta(seconds=course_interval_seconds({**order, **details}))
    for index in range(needed):
        moment = started + interval * index
        if moment in existing:
            continue
        try:
            openmrs_sql.execute(
                """
                INSERT INTO ipd_slot (
                    uuid, location_id, service_type_id, schedule_id, status,
                    start_date_time, overbooked, creator, date_created, voided, order_id
                )
                SELECT %s, %s, %s, %s, 'SCHEDULED', %s, 0, %s, UTC_TIMESTAMP(), 0, o.order_id
                FROM orders o
                WHERE o.uuid = %s
                """,
                (
                    str(uuid.uuid4()),
                    location_id,
                    service_type_id,
                    schedule_id,
                    moment.strftime("%Y-%m-%d %H:%M:%S"),
                    creator or 1,
                    order_uuid,
                ),
            )
        except openmrs_sql.OpenmrsSqlError:
            return


def _frequency_name(order: dict[str, Any]) -> str:
    return mar._display(order.get("frequency")).strip()


def _reject_reason(order: dict[str, Any], patient_uuid: str, visit_uuid: str) -> dict[str, str] | None:
    patient = order.get("patient") if isinstance(order.get("patient"), dict) else {}
    if str(patient.get("uuid") or "") != patient_uuid:
        return {
            "code": "order_patient_mismatch",
            "message": "This prescription belongs to another patient.",
        }
    encounter = order.get("encounter") if isinstance(order.get("encounter"), dict) else {}
    visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
    if str(visit.get("uuid") or "") != visit_uuid:
        return {
            "code": "order_visit_mismatch",
            "message": "This prescription does not belong to the current admission.",
        }
    care_setting = order.get("careSetting") if isinstance(order.get("careSetting"), dict) else {}
    if str(care_setting.get("name") or "").lower() != "inpatient":
        return {
            "code": "outpatient_order",
            "message": "Take-home medicines are not added to the ward medication sheet.",
        }
    if order.get("asNeeded") or _frequency_name(order).lower() in AS_NEEDED_NAMES:
        return {
            "code": "as_needed_not_scheduled",
            "message": "When-needed medicines are not added to the scheduled medication sheet.",
        }
    if not mar._order_is_active(order):
        return {
            "code": "inactive_order",
            "message": "This prescription is no longer active and will not receive new scheduled doses.",
        }
    if mar._epoch_seconds(order.get("dateActivated") or order.get("scheduledDate")) is None:
        return {
            "code": "start_time_required",
            "message": "This prescription cannot be scheduled because the start time is missing.",
        }
    dose = order.get("dose")
    try:
        dose_value = float(dose)
    except (TypeError, ValueError):
        dose_value = 0.0
    if dose_value <= 0:
        return {
            "code": "dose_required",
            "message": "This prescription cannot be scheduled because the dose is missing.",
        }
    if not order.get("frequency"):
        return {
            "code": "frequency_required",
            "message": "This prescription cannot be scheduled because how often it is given is missing.",
        }
    return None


def _schedule_request(order: dict[str, Any], patient_uuid: str) -> dict[str, Any]:
    start = mar._epoch_seconds(order.get("dateActivated") or order.get("scheduledDate"))
    orderer = order.get("orderer") if isinstance(order.get("orderer"), dict) else {}
    provider_uuid = str(orderer.get("uuid") or "").strip()
    if not provider_uuid:
        raise ApiError(
            409,
            "provider_unavailable",
            "The prescribing clinician could not be confirmed for this schedule.",
        )
    return {
        "patientUuid": patient_uuid,
        "orderUuid": str(order.get("uuid") or ""),
        "providerUuid": provider_uuid,
        "comments": "",
        "slotStartTime": start,
        "medicationFrequency": START_TIME_DURATION_FREQUENCY,
        "serviceType": MEDICATION_REQUEST,
    }


def _issue(order: dict[str, Any], code: str, message: str) -> dict[str, str]:
    return {
        "orderUuid": str(order.get("uuid") or ""),
        "orderNumber": str(order.get("orderNumber") or ""),
        "medication": mar.medication_label(order),
        "code": code,
        "message": message,
    }


def _create_or_reuse(order: dict[str, Any], patient_uuid: str) -> dict[str, Any]:
    order_uuid = str(order.get("uuid") or "")
    existing = _existing_slots(patient_uuid, order_uuid)
    if existing:
        return {"state": "already", "slots": existing}
    status, body = _service_post(SCHEDULE_PATH, _schedule_request(order, patient_uuid))
    if status in {200, 201} or _already_created(body):
        slots = _existing_slots(patient_uuid, order_uuid)
        if slots:
            return {
                "state": "already" if _already_created(body) else "created",
                "slots": slots,
            }
        raise ApiError(
            502,
            "schedule_not_confirmed",
            "The prescription was saved, but the ward schedule was not created. Try again.",
        )
    if status in {401, 403}:
        raise ApiError(
            502,
            "schedule_forbidden",
            "The ward schedule could not be created. Try again.",
        )
    raise ApiError(
        502,
        "schedule_create_failed",
        "The prescription was saved, but the ward schedule could not be created. Try again.",
    )


def ensure_medication_schedules(
    patient_uuid: str,
    cookie: str,
    *,
    admission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ward.require_inpatient_view(cookie)
    stay = admission if admission is not None else ward._active_admission(patient_uuid, cookie)
    if not stay:
        raise ApiError(
            409,
            "not_admitted",
            "Inpatient medication schedules can only be created during an active admission.",
        )
    if not mar._is_patient_ipd_admission(stay, patient_uuid):
        raise ApiError(
            409,
            "not_admitted",
            "Inpatient medication schedules can only be created during an active admission.",
        )
    visit = stay.get("visit") if isinstance(stay.get("visit"), dict) else {}
    visit_uuid = str(visit.get("uuid") or "")
    created: list[str] = []
    already: list[str] = []
    issues: list[dict[str, str]] = []
    for order in _load_visit_orders(patient_uuid, visit_uuid):
        rejected = _reject_reason(order, patient_uuid, visit_uuid)
        if rejected:
            if rejected["code"] in {"inactive_order", "outpatient_order"}:
                continue
            issues.append(_issue(order, rejected["code"], rejected["message"]))
            continue
        try:
            result = _create_or_reuse(order, patient_uuid)
        except ApiError as error:
            issues.append(_issue(order, error.code, error.message))
            continue
        order_uuid = str(order.get("uuid") or "")
        _ensure_course_slots(order)
        if result["state"] == "created":
            created.append(order_uuid)
        else:
            already.append(order_uuid)
    return {
        "status": "ok" if not issues else "partial",
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "admissionEncounterUuid": str(stay.get("uuid") or ""),
        "createdOrderUuids": created,
        "alreadyScheduledOrderUuids": already,
        "issues": issues,
    }


def create_medication_schedules(patient_uuid: str, cookie: str) -> dict[str, Any]:
    result = ensure_medication_schedules(patient_uuid, cookie)
    if result["issues"] and not result["createdOrderUuids"] and not result["alreadyScheduledOrderUuids"]:
        first = result["issues"][0]
        raise ApiError(
            422 if str(first.get("code") or "").endswith("required")
            or str(first.get("code") or "")
            in {"as_needed_not_scheduled", "order_patient_mismatch", "order_visit_mismatch"}
            else 502,
            str(first.get("code") or "schedule_create_failed"),
            str(first.get("message") or "The ward schedule could not be created."),
        )
    return result
