"""Safe Hospital EMR facade over the installed Bahmni IPD medication administration model."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import inpatient as ward
import server as core
from server import ApiError

MAR_NOTE_MARKER = "ABIKAN_MAR:v1:"
MAX_REASON_LENGTH = 1000
# Installed IPD dashboard configuration (abikan-config/openmrs/apps/ipdDashboard/app.json):
# nursingTasks.timeInMinutesFromNowToShowTaskAsRelevant = 30
# drugChart.timeInMinutesFromNowToShowPastTaskAsLate = 60
# drugChart.timeInMinutesFromStartTimeToShowAdministeredTaskAsLate = 60
# drugChartSlider.timeInMinutesToDisableSlotPostScheduledTime = 60
EARLY_ADMINISTRATION_MINUTES = 30
LATE_ADMINISTRATION_MINUTES = 60
OUTCOME_TO_BAHMNI_STATUS = {
    "given": "completed",
    "not-done": "not-done",
    "refused": "not-done",
    "held": "stopped",
}
FINAL_SLOT_STATUSES = {"COMPLETED", "NOT_DONE", "STOPPED"}


def _now_seconds() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _lagos_clock(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    local = parsed.astimezone(timezone(timedelta(hours=1)))
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{local.day} {local.strftime('%b')}, {hour}:{local.minute:02d} {suffix}"


def _display(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display") or value.get("name") or "")
    return str(value or "")


def medication_label(order: dict[str, Any]) -> str:
    named = str(order.get("drugNonCoded") or "").strip()
    if named:
        return named
    drug = order.get("drug") if isinstance(order.get("drug"), dict) else {}
    label = _display(drug) or _display(order.get("concept")) or "Medication"
    if label.strip().lower() in {"drugother", "drug other"}:
        return named or label
    return label


def _epoch_seconds(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    text = re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _epoch_millis(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        number = int(value)
        return number * 1000 if number < 10_000_000_000 else number
    seconds = _epoch_seconds(value)
    return seconds * 1000 if seconds is not None else None


def _active_context(patient_uuid: str, cookie: str) -> dict[str, Any]:
    admission = ward._active_admission(patient_uuid, cookie)
    if not admission:
        raise ApiError(
            409,
            "not_admitted",
            "Medication administration is available during an active admission.",
        )
    patient = admission.get("patient") if isinstance(admission.get("patient"), dict) else {}
    visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
    if patient.get("uuid") != patient_uuid or not visit.get("uuid"):
        raise ApiError(
            409,
            "admission_mismatch",
            "The active admission could not be confirmed for this patient.",
        )
    return admission


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
            "No inpatient medication history was found for that admission.",
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


def _slot_timing(scheduled_time: Any, now_seconds: int | None = None) -> dict[str, Any]:
    scheduled = _epoch_seconds(scheduled_time)
    if scheduled is None:
        return {
            "status": "unknown",
            "canAdministerNormally": False,
            "minutesFromScheduled": None,
        }
    now = _now_seconds() if now_seconds is None else now_seconds
    earliest = scheduled - EARLY_ADMINISTRATION_MINUTES * 60
    latest = scheduled + LATE_ADMINISTRATION_MINUTES * 60
    if now < earliest:
        status = "early"
    elif now > latest:
        status = "late"
    else:
        status = "eligible"
    return {
        "status": status,
        "canAdministerNormally": status == "eligible",
        "minutesFromScheduled": int((now - scheduled) / 60),
    }


def _load_schedules(
    patient_uuid: str,
    visit_uuid: str,
    admission_datetime: Any,
) -> list[dict[str, Any]]:
    start = _epoch_seconds(admission_datetime)
    if start is None:
        raise ApiError(
            409,
            "admission_time_unavailable",
            "The admission start time could not be confirmed.",
        )
    end = max(
        _now_seconds() + 90 * 86400,
        start + 90 * 86400,
    )
    query = urlencode(
        {
            "patientUuid": patient_uuid,
            "startTime": start,
            "endTime": end,
            "visitUuid": visit_uuid,
            "view": "drugChart",
        }
    )
    payload = core.openmrs_service_get(
        f"/openmrs/ws/rest/v1/ipd/schedule/type/medication?{query}"
    )
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _slots(schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for schedule in schedules:
        schedule_uuid = str(schedule.get("uuid") or "")
        for item in schedule.get("slots") or []:
            if isinstance(item, dict):
                rows.append({**item, "_scheduleUuid": schedule_uuid})
    return rows


def _slot_start(slot: dict[str, Any]) -> Any:
    for key in ("startTime", "startDateTime", "scheduledTime"):
        if _epoch_seconds(slot.get(key)) is not None:
            return slot.get(key)
    return None


def _looks_like_tablet(value: str) -> bool:
    text = value.strip().casefold().replace(".", "")
    return text in {"tablet", "tablets", "tablet(s)", "tab", "tabs"}


def _generic_dose_unit(value: str) -> bool:
    text = value.strip().casefold().replace(".", "").replace("(s)", "")
    return _looks_like_tablet(text) or text in {"unit", "units"}


def _displayed_unit(saved: str, form: str) -> str:
    chosen = form.strip()
    current = saved.strip()
    if not chosen:
        return current
    if _looks_like_tablet(chosen):
        return current or chosen
    if not current or _generic_dose_unit(current):
        return chosen
    return current


def dosage_forms_for(drug_uuids: list[str]) -> dict[str, str]:
    """Medicine form from the drug record. Injection stays injection."""
    unique: list[str] = []
    seen: set[str] = set()
    for item in drug_uuids:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    if not unique:
        return {}
    try:
        import openmrs_sql

        if not openmrs_sql.sql_configured():
            return {}
        marks = ", ".join(["%s"] * len(unique))
        rows = openmrs_sql.fetch_all(
            f"""
            SELECT d.uuid, IFNULL(cn.name, '')
            FROM drug d
            LEFT JOIN concept_name cn
              ON cn.concept_id = d.dosage_form AND cn.voided = 0
             AND cn.locale = 'en' AND cn.concept_name_type = 'FULLY_SPECIFIED'
            WHERE d.uuid IN ({marks})
            """,
            tuple(unique),
        )
    except Exception:
        return {}
    return {str(row[0]): str(row[1] or "").strip() for row in rows if row and row[0]}


def apply_dosage_forms(orders: list[dict[str, Any]]) -> None:
    pending: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for order in orders:
        if not isinstance(order, dict) or _order_form(order):
            continue
        drug = order.get("drug") if isinstance(order.get("drug"), dict) else {}
        uuid = str(drug.get("uuid") or order.get("drugUuid") or "").strip()
        if uuid:
            pending.append((order, drug, uuid))
    forms = dosage_forms_for([uuid for _, _, uuid in pending])
    for order, drug, uuid in pending:
        form = forms.get(uuid) or ""
        if not form:
            continue
        if drug:
            drug["form"] = form
        else:
            order["drug"] = {"uuid": uuid, "form": form}


def _order_form(order: dict[str, Any]) -> str:
    drug = order.get("drug") if isinstance(order.get("drug"), dict) else {}
    return _display(drug.get("form")) or _display(drug.get("dosageForm")) or _display(order.get("form"))


def _enrich_order(order: dict[str, Any]) -> dict[str, Any]:
    dosing = order.get("dosingInstructions") if isinstance(order.get("dosingInstructions"), dict) else {}
    if order.get("dose") not in (None, "") and (order.get("frequency") or dosing.get("frequency")):
        return order
    order_uuid = str(order.get("uuid") or "")
    if not order_uuid:
        return order
    try:
        full = core.openmrs_service_get(f"/openmrs/ws/rest/v1/bahmnicore/drugOrders/{quote(order_uuid)}")
    except ApiError:
        return order
    if not isinstance(full, dict):
        return order
    nested = full.get("drugOrder") if isinstance(full.get("drugOrder"), dict) else {}
    return {**order, **nested, **full}


def _slot_order(slot: dict[str, Any]) -> dict[str, Any]:
    order = slot.get("order")
    return order if isinstance(order, dict) else {}


def _order_is_active(order: dict[str, Any]) -> bool:
    if order.get("voided") or order.get("dateStopped"):
        return False
    if str(order.get("action") or "").upper() == "DISCONTINUE":
        return False
    expiry = _epoch_millis(order.get("autoExpireDate"))
    return expiry is None or expiry >= _now_seconds() * 1000


def _validate_order(
    order_uuid: str,
    patient_uuid: str,
    visit_uuid: str,
    *,
    require_active: bool = True,
) -> dict[str, Any]:
    representation = (
        "custom:(uuid,patient:(uuid),encounter:(uuid,visit:(uuid)),"
        "careSetting:(name),action,dateActivated,dateStopped,autoExpireDate,voided)"
    )
    order = core.openmrs_service_get(
        f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}?v={representation}"
    )
    patient = order.get("patient") if isinstance(order.get("patient"), dict) else {}
    encounter = order.get("encounter") if isinstance(order.get("encounter"), dict) else {}
    visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
    if patient.get("uuid") != patient_uuid:
        raise ApiError(409, "order_patient_mismatch", "This medication order is for another patient.")
    if visit.get("uuid") != visit_uuid:
        raise ApiError(
            409,
            "order_visit_mismatch",
            "This medication order does not belong to this admission.",
        )
    care_setting = order.get("careSetting") if isinstance(order.get("careSetting"), dict) else {}
    if str(care_setting.get("name") or "").lower() != "inpatient":
        raise ApiError(
            409,
            "outpatient_order",
            "Take-home medicines are not given from the ward medication sheet.",
        )
    if require_active and not _order_is_active(order):
        raise ApiError(409, "inactive_order", "This medication order is no longer active.")
    return order


def _note_metadata(administration: dict[str, Any]) -> dict[str, Any]:
    for note in administration.get("notes") or []:
        if not isinstance(note, dict):
            continue
        text = str(note.get("text") or "")
        if not text.startswith(MAR_NOTE_MARKER):
            continue
        try:
            payload = json.loads(text[len(MAR_NOTE_MARKER) :])
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _provider_name(administration: dict[str, Any]) -> str:
    for performer in administration.get("providers") or []:
        if not isinstance(performer, dict):
            continue
        actor = performer.get("actor") or performer.get("provider")
        value = _display(actor)
        if value:
            return value.split(" - ", 1)[-1].strip()
    return "Nurse"


def _serialize_administration(
    administration: dict[str, Any],
    scheduled_time: Any,
) -> dict[str, Any]:
    metadata = _note_metadata(administration)
    underlying = str(administration.get("status") or "").lower()
    outcome = str(metadata.get("outcome") or "")
    if outcome not in OUTCOME_TO_BAHMNI_STATUS:
        outcome = {
            "completed": "given",
            "not-done": "not-done",
            "stopped": "held",
        }.get(underlying, "not-done")
    return {
        "uuid": str(administration.get("uuid") or ""),
        "status": underlying,
        "outcome": outcome,
        "reason": str(metadata.get("reason") or ""),
        "outsideWindow": bool(metadata.get("outsideWindow")),
        "lateDocumentation": bool(metadata.get("lateDocumentation")),
        "scheduledTime": _epoch_millis(scheduled_time),
        "actualTime": _epoch_millis(administration.get("administeredDateTime")),
        "documentedTime": _epoch_millis(metadata.get("documentedAt")),
        "nurseUserUuid": str(metadata.get("userUuid") or ""),
        "nursePersonUuid": str(metadata.get("personUuid") or ""),
        "nurseName": str(metadata.get("authorName") or _provider_name(administration)),
    }


def _serialize_slot(slot: dict[str, Any]) -> dict[str, Any]:
    administration = slot.get("medicationAdministration")
    return {
        "uuid": str(slot.get("uuid") or ""),
        "scheduleUuid": str(slot.get("_scheduleUuid") or ""),
        "status": str(slot.get("status") or "").upper(),
        "scheduledTime": _epoch_millis(_slot_start(slot)),
        "timing": _slot_timing(_slot_start(slot)),
        "administration": (
            _serialize_administration(administration, _slot_start(slot))
            if isinstance(administration, dict) and administration.get("uuid")
            else None
        ),
    }


def _order_medication_name(order: dict[str, Any]) -> str:
    label = medication_label(order)
    if label.strip().lower() not in {"drugother", "drug other", "medication"}:
        return label
    order_uuid = str(order.get("uuid") or "")
    if not order_uuid:
        return label
    try:
        full = core.openmrs_service_get(
            f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}?v=custom:(uuid,drugNonCoded,drug:(display),concept:(display))"
        )
    except ApiError:
        return label
    if not isinstance(full, dict):
        return label
    return medication_label({**order, **full}) or label


def _serialize_orders(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for slot in slots:
        order_uuid = str(_slot_order(slot).get("uuid") or "")
        if order_uuid:
            grouped.setdefault(order_uuid, []).append(slot)
    prepared: list[tuple[str, list[dict[str, Any]], dict[str, Any]]] = []
    for order_uuid, order_slots in grouped.items():
        prepared.append((order_uuid, order_slots, _enrich_order(_slot_order(order_slots[0]))))
    apply_dosage_forms([order for _, _, order in prepared])
    result: list[dict[str, Any]] = []
    for order_uuid, order_slots, order in prepared:
        drug = order.get("drug") if isinstance(order.get("drug"), dict) else {}
        dosing = (
            order.get("dosingInstructions")
            if isinstance(order.get("dosingInstructions"), dict)
            else {}
        )
        instructions = dosing.get("administrationInstructions") or order.get("instructions") or ""
        if isinstance(instructions, str):
            try:
                parsed = json.loads(instructions)
                if isinstance(parsed, dict) and isinstance(parsed.get("instructions"), str):
                    instructions = parsed["instructions"]
            except (TypeError, ValueError):
                pass
        form = _order_form(order)
        dose_units = _displayed_unit(
            _display(order.get("doseUnits")) or _display(dosing.get("doseUnits")),
            form,
        )
        dose = order.get("dose")
        if dose in (None, "") :
            dose = dosing.get("dose")
        result.append(
            {
                "orderUuid": order_uuid,
                "orderNumber": str(order.get("orderNumber") or ""),
                "medication": _order_medication_name(order),
                "drugUuid": str(drug.get("uuid") or ""),
                "dose": dose,
                "doseUnits": dose_units,
                "route": _display(order.get("route")) or _display(dosing.get("route")),
                "frequency": _display(order.get("frequency")) or _display(dosing.get("frequency")),
                "asNeeded": bool(order.get("asNeeded") or dosing.get("asNeeded")),
                "instructions": str(instructions or ""),
                "slots": sorted(
                    (_serialize_slot(item) for item in order_slots),
                    key=lambda item: int(item.get("scheduledTime") or 0),
                ),
            }
        )
    return sorted(result, key=lambda item: item["medication"].lower())


def _sync_active_schedules(
    patient_uuid: str,
    cookie: str,
    admission: dict[str, Any],
) -> list[dict[str, str]]:
    import medication_schedule as schedules

    try:
        result = schedules.ensure_medication_schedules(
            patient_uuid,
            cookie,
            admission=admission,
        )
    except ApiError as error:
        return [{"orderUuid": "", "code": error.code, "message": error.message}]
    return list(result.get("issues") or [])


def build_mar(
    patient_uuid: str,
    cookie: str,
    *,
    visit_uuid: str | None = None,
    admission_encounter_uuid: str | None = None,
) -> dict[str, Any]:
    ward.require_inpatient_view(cookie)
    admission, is_active = _read_context(
        patient_uuid,
        cookie,
        visit_uuid=visit_uuid,
        admission_encounter_uuid=admission_encounter_uuid,
    )
    visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
    visit_uuid = str(visit.get("uuid") or "")
    schedule_issues = (
        _sync_active_schedules(patient_uuid, cookie, admission) if is_active else []
    )
    schedules = _load_schedules(patient_uuid, visit_uuid, admission.get("encounterDatetime"))
    slots = _slots(schedules)
    valid_slots: list[dict[str, Any]] = []
    validated_orders: set[str] = set()
    invalid_orders: set[str] = set()
    inactive_orders: set[str] = set()
    for slot in slots:
        order = _slot_order(slot)
        order_uuid = str(order.get("uuid") or "")
        patient = order.get("patient") if isinstance(order.get("patient"), dict) else {}
        if not order_uuid or order_uuid in invalid_orders or patient.get("uuid") != patient_uuid:
            continue
        if order_uuid not in validated_orders:
            try:
                order_details = _validate_order(
                    order_uuid,
                    patient_uuid,
                    visit_uuid,
                    require_active=False,
                )
            except ApiError as error:
                if error.status != 409:
                    raise
                invalid_orders.add(order_uuid)
                continue
            if not _order_is_active(order_details):
                inactive_orders.add(order_uuid)
            validated_orders.add(order_uuid)
        if (
            order_uuid in inactive_orders
            and not (
                isinstance(slot.get("medicationAdministration"), dict)
                and slot["medicationAdministration"].get("uuid")
            )
            and str(slot.get("status") or "").upper() == "SCHEDULED"
        ):
            continue
        valid_slots.append(slot)
    return {
        "status": "ok",
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "admissionEncounterUuid": str(admission.get("uuid") or ""),
        "activeAdmission": is_active,
        "administrationWindow": {
            "earlyMinutes": EARLY_ADMINISTRATION_MINUTES,
            "lateMinutes": LATE_ADMINISTRATION_MINUTES,
        },
        "orders": _serialize_orders(valid_slots),
        "scheduleIssues": schedule_issues,
    }


def create_scheduled_administration(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
) -> dict[str, Any]:
    user = ward.require_nursing_user(cookie)
    allowed = {"slotUuid", "outcome", "reason", "outsideWindow"}
    if set(body) - allowed:
        raise ApiError(
            422,
            "server_fields_only",
            "Patient, medication, dose, route, nurse, and times are recorded automatically.",
        )
    slot_uuid = str(body.get("slotUuid") or "").strip()
    outcome = str(body.get("outcome") or "").strip().lower()
    reason = str(body.get("reason") or "").strip()
    outside_window = body.get("outsideWindow") is True
    if "outsideWindow" in body and not isinstance(body.get("outsideWindow"), bool):
        raise ApiError(422, "invalid_outside_window", "Please reopen this medication dose and try again.")
    if not slot_uuid:
        raise ApiError(422, "slot_required", "Choose a scheduled dose.")
    if outcome not in OUTCOME_TO_BAHMNI_STATUS:
        raise ApiError(422, "outcome_required", "Choose what happened with this dose.")
    if outcome != "given" and not reason:
        raise ApiError(422, "reason_required", "Record why this dose was not given.")
    if len(reason) > MAX_REASON_LENGTH:
        raise ApiError(422, "reason_too_long", "The reason is too long.")

    admission = _active_context(patient_uuid, cookie)
    visit = admission.get("visit") if isinstance(admission.get("visit"), dict) else {}
    visit_uuid = str(visit.get("uuid") or "")
    schedules = _load_schedules(patient_uuid, visit_uuid, admission.get("encounterDatetime"))
    matching = [item for item in _slots(schedules) if str(item.get("uuid") or "") == slot_uuid]
    if len(matching) != 1:
        raise ApiError(
            409,
            "slot_mismatch",
            "This scheduled dose does not belong to the active admission.",
        )
    slot = matching[0]
    order = _slot_order(slot)
    order_uuid = str(order.get("uuid") or "")
    patient = order.get("patient") if isinstance(order.get("patient"), dict) else {}
    if patient.get("uuid") != patient_uuid:
        raise ApiError(409, "slot_patient_mismatch", "This scheduled dose is for another patient.")
    _validate_order(order_uuid, patient_uuid, visit_uuid)

    existing = slot.get("medicationAdministration")
    if isinstance(existing, dict) and existing.get("uuid"):
        return {
            "status": "ok",
            "duplicate": True,
            "slot": _serialize_slot(slot),
        }
    if str(slot.get("status") or "").upper() != "SCHEDULED":
        raise ApiError(409, "slot_finalized", "This scheduled dose is already finalized.")

    now_seconds = _now_seconds()
    timing = _slot_timing(_slot_start(slot), now_seconds)
    if timing["status"] == "unknown":
        raise ApiError(
            409,
            "slot_time_unavailable",
            "The scheduled time could not be confirmed. Do not administer this dose.",
        )
    if timing["status"] != "eligible":
        if not outside_window:
            raise ApiError(
                409,
                "outside_administration_window",
                "This dose is outside the normal administration window. Use the outside-window action and record the clinical reason.",
            )
        if not reason:
            raise ApiError(
                422,
                "outside_window_reason_required",
                "Record the clinical reason for administering outside the scheduled window.",
            )
        timing_for_record = timing
    elif outside_window:
        raise ApiError(
            422,
            "outside_window_not_required",
            "This dose is within the normal administration window. Use the normal Administer action.",
        )
    else:
        timing_for_record = timing

    provider_uuid = ward._provider_uuid(str(user.get("uuid") or ""), cookie)
    identity = ward._authenticated_nurse_identity(cookie)
    if not provider_uuid or not all(
        str(identity.get(key) or "").strip()
        for key in ("userUuid", "personUuid", "authorName")
    ):
        raise ApiError(409, "performer_unavailable", "Your staff identity could not be recorded.")
    drug = order.get("drug") if isinstance(order.get("drug"), dict) else {}
    metadata = {
        "outcome": outcome,
        "reason": reason,
        "outsideWindow": outside_window,
        "minutesFromScheduled": timing_for_record["minutesFromScheduled"],
        "userUuid": identity["userUuid"],
        "personUuid": identity["personUuid"],
        "authorName": identity["authorName"],
    }
    payload = {
        "patientUuid": patient_uuid,
        "encounterUuid": str(admission.get("uuid") or ""),
        "orderUuid": order_uuid,
        "slotUuid": slot_uuid,
        "providers": [{"providerUuid": provider_uuid, "function": "Performer"}],
        "notes": [
            {
                "authorUuid": provider_uuid,
                "recordedTime": now_seconds,
                "text": f"{MAR_NOTE_MARKER}{json.dumps(metadata, separators=(',', ':'))}",
            }
        ],
        "status": OUTCOME_TO_BAHMNI_STATUS[outcome],
        "statusReason": None,
        "drugUuid": str(drug.get("uuid") or ""),
        "dosingInstructions": str(order.get("instructions") or ""),
        "dose": order.get("dose"),
        "doseUnits": _display(order.get("doseUnits")),
        "route": _display(order.get("route")),
        "site": None,
        "administeredDateTime": now_seconds,
    }
    result = core.openmrs_service_post(
        "/openmrs/ws/rest/v1/ipd/scheduledMedicationAdministrations",
        [payload],
    )
    response = result[0] if isinstance(result, list) and result else result
    if not isinstance(response, dict) or not response.get("uuid"):
        raise ApiError(
            502,
            "administration_not_confirmed",
            "The medication administration could not be confirmed. Please try again.",
        )
    dismiss_due_dose_notification(slot_uuid)
    saved_slot = {
        **slot,
        "status": {
            "completed": "COMPLETED",
            "not-done": "NOT_DONE",
            "stopped": "STOPPED",
        }[OUTCOME_TO_BAHMNI_STATUS[outcome]],
        "medicationAdministration": response,
    }
    return {"status": "ok", "duplicate": False, "slot": _serialize_slot(saved_slot)}


_DUE_SCAN_LOCK = threading.Lock()
_DUE_SCAN_AT = 0.0
DUE_DOSE_SQL = """
    SELECT s.uuid, per.uuid, IFNULL(v.uuid, ''),
           TRIM(CONCAT(IFNULL(pn.given_name, ''), ' ', IFNULL(pn.family_name, ''))),
           IFNULL(pi.identifier, ''),
           COALESCE(NULLIF(d.name, ''), NULLIF(cn.name, ''), 'Medication'),
       IFNULL(do2.dose, ''),
       IFNULL((
         SELECT cn2.name FROM concept_name cn2
         WHERE cn2.concept_id = do2.dose_units AND cn2.voided = 0
           AND cn2.locale = 'en' AND cn2.concept_name_type = 'FULLY_SPECIFIED'
         LIMIT 1
       ), ''),
       IFNULL((
         SELECT cn3.name FROM order_frequency ofr
         JOIN concept_name cn3 ON cn3.concept_id = ofr.concept_id AND cn3.voided = 0
           AND cn3.locale = 'en' AND cn3.concept_name_type = 'FULLY_SPECIFIED'
         WHERE ofr.order_frequency_id = do2.frequency
         LIMIT 1
       ), ''),
       IFNULL(DATE_FORMAT(s.start_date_time, '%Y-%m-%d %H:%i:%s'), ''),
       IFNULL((
         SELECT cn4.name FROM concept_name cn4
         WHERE cn4.concept_id = d.dosage_form AND cn4.voided = 0
           AND cn4.locale = 'en' AND cn4.concept_name_type = 'FULLY_SPECIFIED'
         LIMIT 1
       ), '')
    FROM ipd_slot s
    JOIN orders o ON o.order_id = s.order_id AND o.voided = 0 AND o.date_stopped IS NULL
    JOIN care_setting cs ON cs.care_setting_id = o.care_setting AND cs.name = 'Inpatient'
    JOIN person per ON per.person_id = o.patient_id AND per.voided = 0
    JOIN person_name pn ON pn.person_id = per.person_id AND pn.voided = 0 AND pn.preferred = 1
    LEFT JOIN patient_identifier pi
        ON pi.patient_id = per.person_id AND pi.voided = 0 AND pi.preferred = 1
    JOIN encounter e ON e.encounter_id = o.encounter_id AND e.voided = 0
    JOIN visit v ON v.visit_id = e.visit_id AND v.voided = 0 AND v.date_stopped IS NULL
    LEFT JOIN drug_order do2 ON do2.order_id = o.order_id
    LEFT JOIN drug d ON d.drug_id = do2.drug_inventory_id
    LEFT JOIN concept_name cn ON cn.concept_id = o.concept_id
        AND cn.voided = 0 AND cn.locale = 'en' AND cn.concept_name_type = 'FULLY_SPECIFIED'
    WHERE s.voided = 0
      AND s.status = 'SCHEDULED'
      AND s.start_date_time <= NOW()
      AND s.start_date_time > DATE_SUB(NOW(), INTERVAL 24 HOUR)
"""


def dismiss_due_dose_notification(slot_uuid: str) -> None:
    slot = str(slot_uuid or "").strip()
    if not slot:
        return
    try:
        import notifications as staff_notes

        staff_notes.expire_idempotency_keys([f"medication_due:{slot}"])
    except Exception:
        return


def publish_due_dose_notifications(*, path: str | None = None) -> int:
    """Tell nursing when a ward dose has reached its time. Take-home medicines are excluded."""
    global _DUE_SCAN_AT
    now = time.time()
    with _DUE_SCAN_LOCK:
        if path is None and now - _DUE_SCAN_AT < 15:
            return 0
        if path is None:
            _DUE_SCAN_AT = now
    import notifications as staff_notes
    import openmrs_sql

    try:
        rows = openmrs_sql.fetch_all(DUE_DOSE_SQL)
    except openmrs_sql.OpenmrsSqlError:
        return 0
    created = 0
    keep: set[str] = set()
    for row in rows:
        slot_uuid = str(row[0] or "").strip()
        patient_uuid = str(row[1] or "").strip()
        if not slot_uuid or not patient_uuid:
            continue
        visit_uuid = str(row[2] or "").strip()
        patient_name = str(row[3] or "").strip() or "a patient"
        mrn = str(row[4] or "").strip()
        medicine = str(row[5] or "").strip() or "A medicine"
        dose = str(row[6] or "").strip()
        if dose.endswith(".0"):
            dose = dose[:-2]
        units = _displayed_unit(
            str(row[7] or "").strip(),
            str(row[10] or "").strip() if len(row) > 10 else "",
        )
        frequency = str(row[8] or "").strip()
        due_at = _lagos_clock(str(row[9] or ""))
        detail = medicine
        amount = " ".join(part for part in (dose, units) if part)
        if amount:
            detail = f"{detail}, {amount}"
        if frequency:
            detail = f"{detail}, {frequency}"
        when = f" at {due_at}" if due_at else ""
        key = f"medication_due:{slot_uuid}"
        keep.add(key)
        result = staff_notes.emit(
            event_type=staff_notes.EVENT_MEDICATION_DUE,
            title="Dose due",
            message=f"{detail} is due{when} for {patient_name}.",
            sender_username="ward",
            sender_display="Ward",
            recipient_scope=staff_notes.SCOPE_WORKPLACE,
            recipient_workplace=staff_notes.WORKPLACE_NURSING,
            patient_uuid=patient_uuid,
            visit_uuid=visit_uuid,
            mrn=mrn,
            patient_name=patient_name,
            action_href=f"#/nursing/patient/{patient_uuid}",
            priority=staff_notes.PRIORITY_HIGH,
            speak=True,
            ttl_seconds=24 * 60 * 60,
            idempotency_key=key,
            payload={"slotUuid": slot_uuid, "medicine": medicine},
            path=path,
        )
        if not result.get("duplicate"):
            created += 1
    staff_notes.expire_event_except(staff_notes.EVENT_MEDICATION_DUE, keep, path=path)
    return created
