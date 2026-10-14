"""Reception and Hospital Admin patient list.

Patients stay in OpenMRS. This module only pages the hospital register for
staff who already work registration or administration. It is not a second
patient store.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qs

import admin_period as periods
import hospital_admin as administration
import openmrs_sql as clinical_sql
import registration as reception
import server as core
from server import ApiError

PAGE_SIZES = {50, 100}
DEFAULT_PAGE_SIZE = 50
MAX_QUERY = 80
LIFE_STATUSES = {"all", "alive", "deceased"}
DIRECTORY_UNAVAILABLE = "The patient list is temporarily unavailable."
DIRECTORY_FORBIDDEN = "This list is for Reception and Hospital Administration."

SEX_LABELS = {"M": "Male", "F": "Female", "O": "Other"}
CARD_TYPE_LABELS = {
    "family": "Family Card",
    "individual": "Individual Card",
    "family card": "Family Card",
    "individual card": "Individual Card",
    # Legacy mistake: ANC was briefly stored as cardType. Hospital card stays Individual/Family;
    # ANC is a separate service shown from the antenatal record, not this column.
    "antenatal": "Individual Card",
    "anc": "Individual Card",
    "antenatal card": "Individual Card",
    "antenatal card (anc)": "Individual Card",
}

LIST_SQL = """
SELECT
  per.uuid,
  TRIM(CONCAT_WS(' ',
    NULLIF(pn.given_name, ''),
    NULLIF(pn.middle_name, ''),
    NULLIF(pn.family_name, '')
  )) AS patient_name,
  pi.identifier AS hospital_number,
  per.gender,
  per.birthdate,
  phone.value AS phone,
  card.value AS card_type,
  p.date_created,
  per.dead,
  per.death_date
FROM patient p
INNER JOIN person per ON per.person_id = p.patient_id AND per.voided = 0
LEFT JOIN person_name pn ON pn.person_name_id = (
  SELECT pn2.person_name_id
  FROM person_name pn2
  WHERE pn2.person_id = per.person_id AND pn2.voided = 0
  ORDER BY pn2.preferred DESC, pn2.person_name_id ASC
  LIMIT 1
)
LEFT JOIN patient_identifier pi ON pi.patient_identifier_id = (
  SELECT pi2.patient_identifier_id
  FROM patient_identifier pi2
  WHERE pi2.patient_id = p.patient_id AND pi2.voided = 0
  ORDER BY pi2.preferred DESC, pi2.patient_identifier_id ASC
  LIMIT 1
)
LEFT JOIN person_attribute phone ON phone.person_attribute_id = (
  SELECT pa.person_attribute_id
  FROM person_attribute pa
  JOIN person_attribute_type pat
    ON pat.person_attribute_type_id = pa.person_attribute_type_id
  WHERE pa.person_id = per.person_id
    AND pa.voided = 0
    AND pat.retired = 0
    AND pat.name IN ('phoneNumber', 'primaryContact')
  ORDER BY CASE pat.name WHEN 'phoneNumber' THEN 0 ELSE 1 END,
           pa.person_attribute_id
  LIMIT 1
)
LEFT JOIN person_attribute card ON card.person_attribute_id = (
  SELECT pa.person_attribute_id
  FROM person_attribute pa
  JOIN person_attribute_type pat
    ON pat.person_attribute_type_id = pa.person_attribute_type_id
  WHERE pa.person_id = per.person_id
    AND pa.voided = 0
    AND pat.retired = 0
    AND pat.name = 'cardType'
  ORDER BY pa.person_attribute_id
  LIMIT 1
)
WHERE p.voided = 0
"""

SEARCH_SQL = """
  AND (
    CONCAT_WS(' ', pn.given_name, pn.middle_name, pn.family_name) LIKE %s ESCAPE '\\\\'
    OR pi.identifier LIKE %s ESCAPE '\\\\'
    OR phone.value LIKE %s ESCAPE '\\\\'
  )
"""

ALIVE_SQL = " AND COALESCE(per.dead, 0) = 0"
DECEASED_SQL = " AND COALESCE(per.dead, 0) = 1"

ORDER_SQL = " ORDER BY p.date_created DESC, per.person_id DESC"
COUNT_SQL = "SELECT COUNT(*) FROM (" + LIST_SQL + "{search}{life}) listed"
PAGE_SQL = LIST_SQL + "{search}{life}" + ORDER_SQL + " LIMIT %s OFFSET %s"


def require_directory_reader(cookie: str) -> dict[str, Any]:
    core.require_session(cookie)
    import accountant as cashier

    user = cashier.load_openmrs_user(cookie)
    if reception.is_registrar(user) or administration.is_hospital_admin(user):
        return user
    raise ApiError(403, "forbidden", DIRECTORY_FORBIDDEN)


def parse_directory_query(raw_path: str) -> dict[str, Any]:
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    raw_limit = (query.get("limit") or [str(DEFAULT_PAGE_SIZE)])[0]
    raw_start = (query.get("startIndex") or ["0"])[0]
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_page", "Choose 50 or 100 patients per page.") from error
    try:
        start_index = int(raw_start)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_page", "The page could not be opened.") from error
    if limit not in PAGE_SIZES:
        raise ApiError(422, "invalid_page", "Choose 50 or 100 patients per page.")
    if start_index < 0:
        raise ApiError(422, "invalid_page", "The page could not be opened.")
    term = str((query.get("q") or [""])[0] or "").strip()
    if len(term) > MAX_QUERY:
        term = term[:MAX_QUERY]
    if len(term) < 2:
        term = ""
    life = str((query.get("lifeStatus") or query.get("status") or ["all"])[0] or "all").strip().lower()
    if life not in LIFE_STATUSES:
        raise ApiError(422, "invalid_life_status", "Choose all patients, alive patients, or deceased patients.")
    return {"q": term, "limit": limit, "startIndex": start_index, "lifeStatus": life}


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _sex_label(value: Any) -> str:
    key = _text(value).upper()
    return SEX_LABELS.get(key, key)


def _card_type_label(value: Any) -> str:
    key = _text(value).casefold()
    if not key or key in {"0", "null", "none", "no card", "nocard"}:
        return ""
    return CARD_TYPE_LABELS.get(key, "")


def _age_years(birthdate: Any, today: date) -> str:
    if not isinstance(birthdate, date):
        return ""
    born = birthdate if not isinstance(birthdate, datetime) else birthdate.date()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if years < 0:
        return ""
    return str(years)


def _registered_on(value: Any) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        local = moment.astimezone(periods.HOSPITAL_TZ).date()
    elif isinstance(value, date):
        local = value
    else:
        return ""
    return f"{local.day} {local.strftime('%b %Y')}"


def _is_dead(value: Any) -> bool:
    if isinstance(value, (datetime, date)):
        return True
    if isinstance(value, (int, float)):
        return bool(value)
    text = _text(value).lower()
    return text in {"1", "true", "yes"}


def alive_label(value: Any) -> str:
    return "No" if _is_dead(value) else "Yes"


def format_death_date(value: Any) -> str:
    iso = _iso_date(value)
    if not iso or len(iso) < 10:
        return ""
    year, month, day = iso.split("-")[:3]
    return f"{day}/{month}/{year}"


def serialize_directory_row(row: tuple[Any, ...], today: date) -> dict[str, str]:
    uuid, name, hospital_number, gender, birthdate, phone, card_type, created, dead, death_date = row
    display_name = _text(name)
    deceased = _is_dead(dead)
    return {
        "uuid": _text(uuid),
        "name": display_name or "Unnamed patient",
        "hospitalNumber": _text(hospital_number),
        "sex": _sex_label(gender),
        "age": _age_years(birthdate, today),
        "phone": _text(phone),
        "cardType": _card_type_label(card_type),
        "registeredOn": _registered_on(created),
        "alive": "No" if deceased else "Yes",
        "deathDate": _iso_date(death_date) if deceased else "",
    }


def build_directory(cookie: str, raw_path: str = "") -> dict[str, Any]:
    require_directory_reader(cookie)
    page = parse_directory_query(raw_path)
    term = page["q"]
    search_sql = SEARCH_SQL if term else ""
    like = _like(term) if term else ""
    search_params: tuple[Any, ...] = (like, like, like) if term else ()
    life_sql = ""
    if page["lifeStatus"] == "alive":
        life_sql = ALIVE_SQL
    elif page["lifeStatus"] == "deceased":
        life_sql = DECEASED_SQL
    today = periods.hospital_today()
    try:
        total = clinical_sql.fetch_int(
            COUNT_SQL.format(search=search_sql, life=life_sql),
            search_params,
        )
        rows = clinical_sql.fetch_all(
            PAGE_SQL.format(search=search_sql, life=life_sql),
            (*search_params, page["limit"], page["startIndex"]),
        )
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    patients = [serialize_directory_row(row, today) for row in rows if row and row[0]]
    marked = _nhis_patient_ids([row["uuid"] for row in patients])
    for row in patients:
        row["nhis"] = row["uuid"] in marked
    start_index = page["startIndex"]
    return {
        "status": "ok",
        "q": term,
        "lifeStatus": page["lifeStatus"],
        "limit": page["limit"],
        "startIndex": start_index,
        "total": total,
        "hasMore": start_index + len(patients) < total,
        "patients": patients,
    }


RECORD_SQL = """
SELECT
  per.uuid,
  pn.given_name,
  pn.middle_name,
  pn.family_name,
  pi.identifier,
  per.gender,
  per.birthdate,
  per.birthdate_estimated,
  phone.value,
  p.date_created,
  addr.address1,
  addr.address2,
  addr.city_village,
  addr.state_province,
  addr.county_district,
  addr.postal_code,
  addr.country,
  per.dead,
  per.death_date
FROM patient p
INNER JOIN person per ON per.person_id = p.patient_id AND per.voided = 0
LEFT JOIN person_name pn ON pn.person_name_id = (
  SELECT pn2.person_name_id
  FROM person_name pn2
  WHERE pn2.person_id = per.person_id AND pn2.voided = 0
  ORDER BY pn2.preferred DESC, pn2.person_name_id ASC
  LIMIT 1
)
LEFT JOIN patient_identifier pi ON pi.patient_identifier_id = (
  SELECT pi2.patient_identifier_id
  FROM patient_identifier pi2
  WHERE pi2.patient_id = p.patient_id AND pi2.voided = 0
  ORDER BY pi2.preferred DESC, pi2.patient_identifier_id ASC
  LIMIT 1
)
LEFT JOIN person_attribute phone ON phone.person_attribute_id = (
  SELECT pa.person_attribute_id
  FROM person_attribute pa
  JOIN person_attribute_type pat
    ON pat.person_attribute_type_id = pa.person_attribute_type_id
  WHERE pa.person_id = per.person_id
    AND pa.voided = 0
    AND pat.retired = 0
    AND pat.name IN ('phoneNumber', 'primaryContact')
  ORDER BY CASE pat.name WHEN 'phoneNumber' THEN 0 ELSE 1 END,
           pa.person_attribute_id
  LIMIT 1
)
LEFT JOIN person_address addr ON addr.person_address_id = (
  SELECT addr2.person_address_id
  FROM person_address addr2
  WHERE addr2.person_id = per.person_id AND addr2.voided = 0
  ORDER BY addr2.preferred DESC, addr2.person_address_id ASC
  LIMIT 1
)
WHERE p.voided = 0 AND per.uuid = %s
LIMIT 1
"""

IDENTIFIERS_SQL = """
SELECT pi.identifier, pi.preferred, pit.name
FROM patient_identifier pi
JOIN patient p ON p.patient_id = pi.patient_id AND p.voided = 0
JOIN person per ON per.person_id = p.patient_id
JOIN patient_identifier_type pit
  ON pit.patient_identifier_type_id = pi.identifier_type
WHERE per.uuid = %s AND pi.voided = 0
ORDER BY pi.preferred DESC, pi.patient_identifier_id ASC
"""


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(periods.HOSPITAL_TZ).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)[:10]


def serialize_patient_record(
    row: tuple[Any, ...],
    identifiers: list[tuple[Any, ...]],
    today: date,
) -> dict[str, Any]:
    (
        uuid,
        given,
        middle,
        family,
        hospital_number,
        gender,
        birthdate,
        estimated,
        phone,
        created,
        address1,
        address2,
        city,
        state,
        lga,
        postal,
        country,
        dead,
        death_date,
    ) = row
    identifier = _text(hospital_number)
    deceased = _is_dead(dead)
    return {
        "status": "ok",
        "uuid": _text(uuid),
        "identifier": identifier,
        "givenName": _text(given),
        "middleName": _text(middle),
        "familyName": _text(family),
        "gender": _text(gender),
        "birthdate": _iso_date(birthdate),
        "birthdateEstimated": bool(estimated),
        "age": int(_age_years(birthdate, today) or 0) if _age_years(birthdate, today) else None,
        "attributes": {"phoneNumber": _text(phone)} if _text(phone) else {},
        "address": {
            "address1": _text(address1),
            "address2": _text(address2),
            "cityVillage": _text(city),
            "stateProvince": _text(state),
            "countyDistrict": _text(lga),
            "postalCode": _text(postal),
            "country": _text(country),
        },
        "identifiers": [
            {
                "identifier": _text(item[0]),
                "preferred": bool(item[1]),
                "type": _text(item[2]),
            }
            for item in identifiers
            if item and _text(item[0])
        ] or (
            [{"identifier": identifier, "preferred": True, "type": "Hospital number"}]
            if identifier
            else []
        ),
        "registeredOn": _iso_date(created),
        "alive": not deceased,
        "deathDate": _iso_date(death_date) if deceased else "",
    }


def _record_row(patient_uuid: str) -> tuple[tuple[Any, ...], list[tuple[Any, ...]]]:
    uuid = (patient_uuid or "").strip()
    if not uuid:
        raise ApiError(404, "patient_not_found", "This patient was not found.")
    try:
        row = clinical_sql.fetch_one(RECORD_SQL, (uuid,))
        identifiers = clinical_sql.fetch_all(IDENTIFIERS_SQL, (uuid,))
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    if not row or not row[0]:
        raise ApiError(404, "patient_not_found", "This patient was not found.")
    return row, identifiers


def load_patient_identity(patient_uuid: str) -> dict[str, str]:
    """Name and hospital number from the register. Does not use clinical REST."""
    row, identifiers = _record_row(patient_uuid)
    record = serialize_patient_record(row, identifiers, periods.hospital_today())
    identifier = record.get("identifier") or ""
    if not identifier:
        raise ApiError(422, "mrn_missing", "This patient has no medical record number.")
    name = " ".join(
        part
        for part in (record.get("givenName"), record.get("middleName"), record.get("familyName"))
        if part
    )
    return {
        "uuid": record.get("uuid") or patient_uuid,
        "name": name or "Unknown patient",
        "mrn": identifier,
    }


def _nhis_patient_ids(patient_uuids: list[str]) -> set[str]:
    wanted = {str(item).strip() for item in patient_uuids if str(item).strip()}
    if not wanted:
        return set()
    try:
        import consultation as clinical

        marked = clinical.load_nhis_patients(clinical.odoo_reader())
    except Exception:
        return set()
    return marked & wanted


def load_patient_record(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_directory_reader(cookie)
    row, identifiers = _record_row(patient_uuid)
    record = serialize_patient_record(row, identifiers, periods.hospital_today())
    record["nhis"] = patient_uuid in _nhis_patient_ids([patient_uuid])
    return record
