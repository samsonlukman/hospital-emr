"""My Patients for Clinical.

Patients this logged-in doctor actually attended as Consultation
encounter_provider. No assignment table. No hospital-wide directory.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import clinical_queue as todays
import consultation as clinical
import daily_visit_number as daily

ApiError = clinical.ApiError

CONSULTATION_ENCOUNTER_TYPE = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
VISIT_PAGE_SIZE = 50
VISIT_PAGE_CAP = 2000
VISIT_REPRESENTATION = (
    "custom:(uuid,startDatetime,stopDatetime,"
    "visitType:(name,display),"
    "patient:(uuid,display,identifiers:(identifier,preferred),person:(gender,age,birthdate)),"
    "attributes:(value,display,attributeType:(uuid,name)),"
    "encounters:(uuid,encounterDatetime,encounterType:(uuid,name),"
    "encounterProviders:(provider:(uuid,display,person:(display)))))"
)


def _provider_uuid(user_uuid: str, cookie: str) -> str:
    payload = clinical._openmrs_json(
        f"/openmrs/ws/rest/v1/provider?user={quote(user_uuid)}&v=custom:(uuid,retired)",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if isinstance(row, dict) and row.get("uuid") and not row.get("retired"):
            return str(row["uuid"])
    raise ApiError(409, "provider_missing", "This account is not set up as a clinician.")


def _is_consultation(encounter: dict[str, Any]) -> bool:
    encounter_type = encounter.get("encounterType") if isinstance(encounter.get("encounterType"), dict) else {}
    return (
        encounter_type.get("uuid") == CONSULTATION_ENCOUNTER_TYPE
        or encounter_type.get("name") == "Consultation"
    )


def _provider_name(provider: dict[str, Any] | None) -> str:
    if not isinstance(provider, dict):
        return ""
    person = provider.get("person") if isinstance(provider.get("person"), dict) else {}
    person_name = str(person.get("display") or "").strip()
    if person_name and "null" not in person_name.lower():
        return person_name
    display = str(provider.get("display") or "").strip()
    if " - " in display:
        display = display.split(" - ", 1)[1].strip()
    if display and "null" not in display.lower() and "." not in display:
        return display
    if display and " - " not in str(provider.get("display") or ""):
        return display
    return display


def _consultation_attended_by(
    encounter: dict[str, Any],
    provider_uuid: str,
) -> str | None:
    for row in encounter.get("encounterProviders") or []:
        if not isinstance(row, dict):
            continue
        provider = row.get("provider") if isinstance(row.get("provider"), dict) else {}
        if str(provider.get("uuid") or "") != provider_uuid:
            continue
        return _provider_name(provider) or "—"
    return None


def _age_sex(person: dict[str, Any]) -> str:
    age = person.get("age")
    sex = str(person.get("gender") or "").strip().upper()
    age_text = str(age).strip() if age is not None and str(age).strip() != "" else ""
    if age_text and sex:
        return f"{age_text} / {sex}"
    return age_text or sex


def _load_visits(cookie: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start_index = 0
    while start_index < VISIT_PAGE_CAP:
        payload = clinical._openmrs_json(
            f"/openmrs/ws/rest/v1/visit?includeInactive=true"
            f"&limit={VISIT_PAGE_SIZE}"
            f"&startIndex={start_index}"
            f"&v={VISIT_REPRESENTATION}",
            cookie,
        )
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


def build_my_patients(cookie: str) -> dict[str, list[dict[str, Any]]]:
    user = clinical.require_clinician(cookie)
    provider_uuid = _provider_uuid(str(user.get("uuid") or ""), cookie)
    try:
        visits = _load_visits(cookie)
    except ApiError as error:
        if error.status == 502:
            raise ApiError(
                502,
                "openmrs_error",
                "Your patients could not be loaded.",
            ) from error
        raise

    latest: dict[str, dict[str, Any]] = {}
    for visit in visits:
        patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
        patient_uuid = str(patient.get("uuid") or "").strip()
        if not patient_uuid:
            continue
        person = patient.get("person") if isinstance(patient.get("person"), dict) else {}
        name, mrn = todays.name_and_mrn(patient.get("display"), patient.get("identifiers"))
        visit_type = todays.visit_type_name(visit)
        daily_no = daily.daily_visit_number_from_visit(visit)
        for encounter in visit.get("encounters") or []:
            if not isinstance(encounter, dict) or not _is_consultation(encounter):
                continue
            attended_by = _consultation_attended_by(encounter, provider_uuid)
            if not attended_by:
                continue
            attended = str(encounter.get("encounterDatetime") or visit.get("startDatetime") or "")
            current = latest.get(patient_uuid)
            if current and (current.get("lastAttended") or "") >= attended:
                continue
            latest[patient_uuid] = {
                "patient": name,
                "mrn": mrn or "—",
                "ageSex": _age_sex(person),
                "visitType": visit_type,
                "visitStart": visit.get("startDatetime") or "",
                "lastAttended": attended,
                "dailyVisitNumber": daily_no,
                "attendedBy": attended_by,
                "patientUuid": patient_uuid,
            }

    rows = list(latest.values())
    rows.sort(key=lambda item: item.get("lastAttended") or "", reverse=True)
    return {"patients": rows}
