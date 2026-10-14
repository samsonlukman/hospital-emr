"""Today's Patients for Clinical.

Read-only OpenMRS visit list for the hospital day in Africa/Lagos.
Appointments are not used. No queue table. No writes.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import consultation as clinical

ApiError = clinical.ApiError

HOSPITAL_TZ = ZoneInfo("Africa/Lagos")
# Live GET /visittype names on this installation. IPD and EMERGENCY stay out
# of the ordinary outpatient doctor list.
QUEUE_VISIT_TYPES = frozenset({"opd", "special opd", "follow up", "anc"})
VISIT_PAGE_SIZE = 100
VISIT_PAGE_CAP = 500
VISIT_REPRESENTATION = (
    "custom:(uuid,startDatetime,stopDatetime,"
    "visitType:(name,display),"
    "patient:(uuid,display,identifiers:(identifier,preferred)),"
    "attributes:(value,display,attributeType:(uuid,name)))"
)


def hospital_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(HOSPITAL_TZ).date()


def parse_openmrs_dt(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", text):
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_queue_visit_type(name: str) -> bool:
    return (name or "").strip().lower() in QUEUE_VISIT_TYPES


def started_on_hospital_day(start_raw: str | None, day: date) -> bool:
    parsed = parse_openmrs_dt(start_raw)
    if parsed is None:
        return False
    return parsed.astimezone(HOSPITAL_TZ).date() == day


def preferred_mrn(identifiers: Any) -> str:
    rows = identifiers if isinstance(identifiers, list) else []
    preferred = next(
        (
            str(item.get("identifier") or "").strip()
            for item in rows
            if isinstance(item, dict) and item.get("preferred") and item.get("identifier")
        ),
        "",
    )
    if preferred:
        return preferred
    any_id = next(
        (
            str(item.get("identifier") or "").strip()
            for item in rows
            if isinstance(item, dict) and item.get("identifier")
        ),
        "",
    )
    return any_id


def name_and_mrn(display: str | None, identifiers: Any) -> tuple[str, str]:
    mrn = preferred_mrn(identifiers)
    raw = (display or "Unknown patient").strip()
    if mrn and raw.endswith(mrn):
        name = re.sub(r"[\s\-–—()]+$", "", raw[: -len(mrn)]).strip()
        return name or raw, mrn
    paren = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if paren:
        return paren.group(1).strip(), mrn or paren.group(2).strip()
    dashed = re.match(r"^(\S+)\s+-\s+(.+)$", raw)
    if dashed:
        maybe_mrn, maybe_name = dashed.group(1).strip(), dashed.group(2).strip()
        return maybe_name, mrn or maybe_mrn
    return raw, mrn


def visit_type_name(visit: dict[str, Any]) -> str:
    visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
    return str(visit_type.get("name") or visit_type.get("display") or "").strip()


def format_lagos_clock(start_raw: str | None) -> str:
    parsed = parse_openmrs_dt(start_raw)
    if parsed is None:
        return "—"
    return parsed.astimezone(HOSPITAL_TZ).strftime("%H:%M")


def load_recent_visits(cookie: str, from_start: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start_index = 0
    while start_index < VISIT_PAGE_CAP:
        path = (
            f"/openmrs/ws/rest/v1/visit?fromStartDate={from_start}"
            f"&includeInactive=true"
            f"&limit={VISIT_PAGE_SIZE}"
            f"&startIndex={start_index}"
            f"&v={VISIT_REPRESENTATION}"
        )
        payload = clinical._openmrs_json(path, cookie)
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list) or not results:
            break
        for item in results:
            if isinstance(item, dict) and item.get("uuid"):
                rows.append(item)
        if len(results) < VISIT_PAGE_SIZE:
            break
        start_index += len(results)
    return rows


def row_from_visit(visit: dict[str, Any], *, any_visit_type: bool = False) -> dict[str, Any] | None:
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    patient_uuid = str(patient.get("uuid") or "").strip()
    if not patient_uuid:
        return None
    visit_type = visit_type_name(visit)
    if not any_visit_type and not is_queue_visit_type(visit_type):
        return None
    name, mrn = name_and_mrn(patient.get("display"), patient.get("identifiers"))
    stop = visit.get("stopDatetime")
    import daily_visit_number as daily

    return {
        "patient": name,
        "mrn": mrn or "—",
        "visitType": visit_type or "Visit",
        "visitStart": visit.get("startDatetime") or "",
        "time": format_lagos_clock(visit.get("startDatetime")),
        "status": "Ended" if stop else "Open",
        "dailyVisitNumber": daily.daily_visit_number_from_visit(visit),
        "patientUuid": patient_uuid,
        "visitUuid": str(visit.get("uuid") or ""),
    }


def build_todays_patients(cookie: str) -> dict[str, list[dict[str, Any]]]:
    clinical.require_clinician(cookie)
    today = hospital_today()
    from_start = (today - timedelta(days=1)).isoformat()
    try:
        visits = load_recent_visits(cookie, from_start)
    except ApiError as error:
        if error.status == 502:
            raise ApiError(
                502,
                "openmrs_error",
                "Today's patients could not be loaded. You can still search for a patient.",
            ) from error
        raise
    rows: list[dict[str, Any]] = []
    for visit in visits:
        if not started_on_hospital_day(visit.get("startDatetime"), today):
            continue
        row = row_from_visit(visit)
        if row:
            rows.append(row)
    rows.sort(key=lambda item: str(item.get("visitStart") or ""), reverse=True)
    return {"patients": rows}


def build_nursing_todays_patients(cookie: str) -> dict[str, list[dict[str, Any]]]:
    import inpatient as ward

    ward.require_nursing_user(cookie)
    today = hospital_today()
    from_start = (today - timedelta(days=1)).isoformat()
    try:
        visits = load_recent_visits(cookie, from_start)
    except ApiError as error:
        if error.status == 502:
            raise ApiError(
                502,
                "openmrs_error",
                "Today's visits could not be loaded. You can still search for a patient.",
            ) from error
        raise
    rows: list[dict[str, Any]] = []
    for visit in visits:
        if not started_on_hospital_day(visit.get("startDatetime"), today):
            continue
        row = row_from_visit(visit, any_visit_type=True)
        if row:
            rows.append(row)
    import daily_visit_number as daily

    rows.sort(key=lambda item: daily.sort_key(item.get("dailyVisitNumber")))
    return {"patients": rows}
