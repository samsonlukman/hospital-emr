"""Admin-only patient Alive / Deceased status.

Patients stay in OpenMRS. This module only lets Hospital Administration change
person.dead and person.death_date. It does not create a second patient store
or change visits, results, or bills.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import admin_audit
import admin_period as periods
import hospital_admin as administration
import openmrs_sql as clinical_sql
import patient_directory as register
from server import ApiError

LIFE_STATUS_FORBIDDEN = "This action requires Hospital Administration."
LIFE_STATUS_UNAVAILABLE = "The patient status could not be updated."
CAUSE_NAMES = ("Unknown", "Death - Unknown", "Not recorded")
CAUSE_SQL = """
SELECT c.uuid
FROM concept c
JOIN concept_name cn ON cn.concept_id = c.concept_id AND cn.voided = 0
WHERE c.retired = 0
  AND cn.name IN ('Unknown', 'Death - Unknown', 'Not recorded')
ORDER BY CASE cn.name WHEN 'Unknown' THEN 0 WHEN 'Not recorded' THEN 1 ELSE 2 END
LIMIT 1
"""
_CAUSE_CACHE: dict[str, str] = {}


def parse_alive(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "1"}:
        return True
    if text in {"no", "false", "0"}:
        return False
    raise ApiError(422, "alive_required", "Choose whether the patient is alive.")


def parse_death_date(value: Any, *, today: date) -> date:
    text = str(value or "").strip()
    if not text:
        raise ApiError(422, "death_date_required", "Enter the date of death.")
    try:
        day = periods.parse_iso_date(text, field="deathDate")
    except ApiError as error:
        raise ApiError(422, "invalid_death_date", "Enter a valid date of death.") from error
    if day > today:
        raise ApiError(422, "future_death_date", "Date of death cannot be in the future.")
    return day


def current_life_status(record: dict[str, Any]) -> dict[str, Any]:
    alive = bool(record.get("alive", True))
    death_date = str(record.get("deathDate") or "") if not alive else ""
    return {
        "alive": alive,
        "status": "Alive" if alive else "Dead",
        "deathDate": death_date,
        "patientName": " ".join(
            part
            for part in (record.get("givenName"), record.get("middleName"), record.get("familyName"))
            if part
        ).strip(),
        "hospitalNumber": str(record.get("identifier") or ""),
    }


def _unknown_cause_uuid() -> str:
    cached = _CAUSE_CACHE.get("uuid")
    if cached:
        return cached
    try:
        row = clinical_sql.fetch_one(CAUSE_SQL)
    except clinical_sql.OpenmrsSqlError:
        row = None
    uuid = str((row or [""])[0] or "").strip()
    if uuid:
        _CAUSE_CACHE["uuid"] = uuid
    return uuid


def _openmrs_death_datetime(day: date) -> str:
    local = datetime(day.year, day.month, day.day, tzinfo=periods.HOSPITAL_TZ)
    return local.isoformat(timespec="milliseconds")


def _write_person_life_status(person_uuid: str, *, alive: bool, death_day: date | None) -> None:
    path = f"/openmrs/ws/rest/v1/person/{quote(person_uuid)}"
    payload: dict[str, Any] = {"dead": not alive}
    if alive:
        payload["deathDate"] = ""
        payload["causeOfDeath"] = ""
        payload["causeOfDeathNonCoded"] = ""
    else:
        if death_day is None:
            raise ApiError(422, "death_date_required", "Enter the date of death.")
        payload["deathDate"] = _openmrs_death_datetime(death_day)
        cause = _unknown_cause_uuid()
        if cause:
            payload["causeOfDeath"] = cause
        else:
            payload["causeOfDeathNonCoded"] = "Not recorded"
    administration._admin_openmrs_json(
        path,
        method="POST",
        payload=payload,
        fallback=LIFE_STATUS_UNAVAILABLE,
    )


def update_life_status(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = administration.require_hospital_admin(cookie)
    request_id = str((body or {}).get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh the form and try again.")
    alive = parse_alive((body or {}).get("alive"))
    today = periods.hospital_today()
    death_day = None if alive else parse_death_date((body or {}).get("deathDate"), today=today)
    record = register.load_patient_record(patient_uuid, cookie)
    previous = current_life_status(record)
    next_state = {
        "alive": alive,
        "status": "Alive" if alive else "Dead",
        "deathDate": death_day.isoformat() if death_day else "",
        "patientName": previous["patientName"],
        "hospitalNumber": previous["hospitalNumber"],
    }
    if previous["alive"] == next_state["alive"] and previous["deathDate"] == next_state["deathDate"]:
        return record
    event_id = admin_audit.start_admin_event(
        actor=actor,
        target_user_uuid=record.get("uuid") or patient_uuid,
        target_username=previous["hospitalNumber"] or previous["patientName"] or patient_uuid,
        action="ADMIN_UPDATE_PATIENT_LIFE_STATUS",
        previous_state=previous,
        new_state=next_state,
        details={
            "patientName": previous["patientName"],
            "hospitalNumber": previous["hospitalNumber"],
            "changedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        },
        request_id=request_id,
    )
    try:
        _write_person_life_status(patient_uuid, alive=alive, death_day=death_day)
        updated = register.load_patient_record(patient_uuid, cookie)
        admin_audit.finish_admin_event(
            event_id,
            outcome="success",
            new_state=current_life_status(updated),
            details={
                "patientName": previous["patientName"],
                "hospitalNumber": previous["hospitalNumber"],
                "changedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            },
        )
        return updated
    except ApiError as error:
        admin_audit.finish_admin_event(
            event_id,
            outcome="failure",
            new_state=next_state,
            details={"error": error.message},
            error_code=error.code,
        )
        raise
    except Exception:
        admin_audit.finish_admin_event(
            event_id,
            outcome="failure",
            new_state=next_state,
            error_code="life_status_failed",
        )
        raise ApiError(502, "life_status_failed", LIFE_STATUS_UNAVAILABLE) from None
