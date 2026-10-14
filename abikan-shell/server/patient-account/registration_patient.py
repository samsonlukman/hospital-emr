"""Reception patient registration and visit start.

Patients, identifiers, visits, and locations stay in OpenMRS.
Hospital EMR only exposes the hospital arrival workflow. No Hospital EMR patient table.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import server as core

ApiError = core.ApiError
OPENMRS_URL = core.OPENMRS_URL

IDENTIFIER_SOURCE = 1
IDENTIFIER_PREFIX = "ABC"
RECEPTION_START_VISIT_TYPES = {
    "OPD",
    "FOLLOW UP",
    "NURSING TREATMENT",
    "EMERGENCY",
    "IPD",
    "ANC",
}
EMERGENCY_NAMES = {"emergency"}
IPD_NAMES = {"ipd"}
APPOINTMENT_LOCATION_TAG = "appointment location"
ADMISSION_LOCATION_TAG = "admission location"
# Existing Clinical session location. Not a new OpenMRS identity. Never fall back to OPD-2.
DEFAULT_OUTPATIENT_LOCATION_NAME = "OPD-1"
NURSING_TREATMENT_VISIT_TYPE_NAME = "Nursing Treatment"
LOCATION_UNAVAILABLE_MESSAGE = (
    "This visit cannot be started because no hospital location is configured for it. "
    "Ask an administrator to review the location setup."
)
LOCATION_REQUIRED_MESSAGE = "Select the ward."
IDENTIFIER_LABELS = {
    "Old Identification Number": "Previous hospital number",
}


def staff_identifier_label(name: str) -> str | None:
    if "openmrs" in name.lower():
        return None
    return IDENTIFIER_LABELS.get(name, name)


ATTRIBUTE_LABELS = {
    "phoneNumber": "Phone",
    "alternatePhoneNumber": "Other phone",
    "email": "Email",
    "familyNameLocal": "Local family name",
    "middleNameLocal": "Local middle name",
    "givenNameLocal": "Local given name",
    "cardType": "Card Type",
}
# Staff HR person attributes. They belong on staff records, not patient registration.
STAFF_ATTRIBUTE_PREFIXES = ("abikan.",)
ADDRESS_FIELDS = (
    ("address1", "Address"),
    ("address2", "Area / landmark"),
    ("cityVillage", "City / town"),
    ("stateProvince", "State"),
    ("countyDistrict", "Local government area"),
    ("postalCode", "Postal code"),
    ("country", "Country"),
)
VISIT_LABELS = {
    "OPD": "General Outpatient",
    "Follow Up": "Follow-up",
    "Nursing Treatment": "Nursing Treatment",
    "EMERGENCY": "Emergency",
    "IPD": "Admission",
    "ANC": "Antenatal Care (ANC)",
    "Special OPD": "Retrospective visit",
}
VISIT_HELPERS = {
    "OPD": "Regular outpatient consultation",
    "Follow Up": "Returning for a previous treatment or condition",
    "Nursing Treatment": "Medicine, injection, wound care, or another planned nursing treatment",
    "EMERGENCY": "Urgent care",
    "IPD": "Patient is being admitted",
    "ANC": "Antenatal clinic visit for pregnancy care",
}


def require_registrar(cookie: str) -> dict[str, Any]:
    import registration as reception

    return reception.require_registrar(cookie)


def _openmrs_error(error: HTTPError, fallback: str) -> ApiError:
    raw = ""
    try:
        raw = error.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    detail = payload.get("error") if isinstance(payload, dict) else {}
    message = ""
    if isinstance(detail, dict):
        global_errors = detail.get("globalErrors") or []
        messages = [str(item.get("message") or "") for item in global_errors if isinstance(item, dict)]
        message = detail.get("message") or " ".join(messages)
    if error.code == 401:
        return ApiError(401, "unauthenticated", "Sign in required.")
    if error.code == 403:
        # OpenMRS privilege misses are not Hospital EMR Reception RBAC.
        # require_registrar is the only source of "Reception access" copy.
        return ApiError(502, "openmrs_error", fallback)
    return ApiError(502, "openmrs_error", message or fallback)


def _openmrs_json(
    path: str,
    cookie: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    fallback: str = "The registration record could not be loaded.",
) -> Any:
    headers = {"Accept": "application/json", "Cookie": cookie}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(f"{OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=40) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        raise _openmrs_error(error, fallback) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", fallback) from error


def _results(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("results") if isinstance(payload, dict) else payload
    return [row for row in (rows or []) if isinstance(row, dict)]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display") or value.get("name") or value.get("uuid") or "").strip()
    if value is None:
        return ""
    return str(value).strip()


def _uuid(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("uuid") or "").strip()
    return str(value or "").strip()


def _staff_visit_label(name: str) -> str:
    return VISIT_LABELS.get(name, name)


def _staff_visit_helper(name: str) -> str:
    return VISIT_HELPERS.get(name, "")


def ensure_nursing_treatment_visit_type(cookie: str) -> dict[str, Any] | None:
    rows = _results(
        _openmrs_json(
            "/openmrs/ws/rest/v1/visittype?v=custom:(uuid,name,display,retired,description)",
            cookie,
            fallback="Visit types could not be loaded.",
        )
    )
    for row in rows:
        name = _text(row.get("name") or row.get("display"))
        if name.upper() == NURSING_TREATMENT_VISIT_TYPE_NAME.upper() and not row.get("retired"):
            return row
    try:
        created = _openmrs_json(
            "/openmrs/ws/rest/v1/visittype",
            cookie,
            method="POST",
            payload={
                "name": NURSING_TREATMENT_VISIT_TYPE_NAME,
                "description": "Nurse-led treatment visits without a doctor consultation.",
            },
            fallback="The nursing treatment visit type could not be created.",
        )
        return created if isinstance(created, dict) else None
    except ApiError:
        return None


def _visit_bucket(name: str) -> str:
    key = name.strip().lower()
    if key in EMERGENCY_NAMES:
        return "emergency"
    if key in IPD_NAMES:
        return "inpatient"
    return "outpatient"


def _location_tags(row: dict[str, Any]) -> set[str]:
    tags = row.get("tags") or []
    names: set[str] = set()
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                name = str(tag.get("name") or tag.get("display") or "").strip().lower()
            else:
                name = str(tag or "").strip().lower()
            if name:
                names.add(name)
    return names


def _location_allowed(row: dict[str, Any], bucket: str) -> bool:
    name = str(row.get("name") or "").strip().lower()
    tags = _location_tags(row)
    if bucket == "emergency":
        return name == "emergency"
    if bucket == "inpatient":
        return ADMISSION_LOCATION_TAG in tags and "ward" in name and "emergency" not in name
    return APPOINTMENT_LOCATION_TAG in tags and ADMISSION_LOCATION_TAG not in tags


def load_identifier_type(cookie: str) -> dict[str, str]:
    rows = _results(
        _openmrs_json(
            "/openmrs/ws/rest/v1/patientidentifiertype?v=custom:(uuid,name,required,retired)",
            cookie,
        )
    )
    live = [row for row in rows if not row.get("retired")]
    required = [row for row in live if row.get("required")]
    chosen = required[0] if required else (live[0] if live else None)
    if not chosen:
        raise ApiError(502, "identifier_missing", "No hospital number type is configured.")
    extras = []
    for row in live:
        if str(row.get("uuid")) == str(chosen.get("uuid")):
            continue
        label = staff_identifier_label(str(row.get("name") or ""))
        if not label:
            continue
        extras.append({"uuid": str(row.get("uuid")), "name": label, "required": False})
    return {
        "uuid": str(chosen.get("uuid")),
        "name": str(chosen.get("name") or "Patient Identifier"),
        "required": True,
        "otherTypes": extras,
        "sourceName": "ABC",
        "prefix": IDENTIFIER_PREFIX,
        "note": (
            "Hospital numbers are created by the existing identifier source. "
            "Hospital EMR does not generate them."
        ),
    }


def is_registration_contact_attribute(name: str) -> bool:
    key = str(name or "").strip()
    if not key:
        return False
    lowered = key.lower()
    return not lowered.startswith(STAFF_ATTRIBUTE_PREFIXES)


def load_person_attributes(cookie: str) -> list[dict[str, Any]]:
    rows = _results(
        _openmrs_json(
            "/openmrs/ws/rest/v1/personattributetype?v=custom:(uuid,name,description,format,retired,searchable)&limit=100",
            cookie,
        )
    )
    fields = []
    for row in rows:
        if row.get("retired"):
            continue
        name = str(row.get("name") or "")
        if not is_registration_contact_attribute(name):
            continue
        fields.append(
            {
                "uuid": str(row.get("uuid")),
                "name": name,
                "label": ATTRIBUTE_LABELS.get(name) or re.sub(r"([a-z])([A-Z])", r"\1 \2", name).strip().title(),
                "searchable": bool(row.get("searchable")),
                "format": str(row.get("format") or ""),
            }
        )
    return fields


def load_relationship_types(cookie: str) -> list[dict[str, str]]:
    rows = _results(
        _openmrs_json(
            "/openmrs/ws/rest/v1/relationshiptype?v=full&limit=50",
            cookie,
        )
    )
    types = []
    for row in rows:
        if row.get("retired"):
            continue
        types.append(
            {
                "uuid": str(row.get("uuid")),
                "label": str(row.get("aIsToB") or row.get("display") or "Relative"),
                "aIsToB": str(row.get("aIsToB") or ""),
                "bIsToA": str(row.get("bIsToA") or ""),
            }
        )
    return types


def load_login_locations(cookie: str) -> list[dict[str, Any]]:
    rows = _results(
        _openmrs_json(
            "/openmrs/ws/rest/v1/location?tag=Login+Location&v=custom:(uuid,name,description,retired,tags:(name))&limit=100",
            cookie,
        )
    )
    locations = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not row.get("uuid") or not name or row.get("retired"):
            continue
        locations.append(
            {
                "uuid": str(row.get("uuid")),
                "name": name,
                "description": str(row.get("description") or "").strip(),
                "tags": [
                    str(tag.get("name") or "").strip()
                    for tag in (row.get("tags") or [])
                    if isinstance(tag, dict) and tag.get("name")
                ],
            }
        )
    locations.sort(key=lambda row: row["name"])
    return locations


def load_visit_types(cookie: str) -> list[dict[str, Any]]:
    import antenatal as anc

    # Ensure the OpenMRS ANC visit type exists so Reception can offer it.
    anc.ensure_openmrs_anc_visit_type(cookie)
    ensure_nursing_treatment_visit_type(cookie)
    rows = _results(
        _openmrs_json(
            "/openmrs/ws/rest/v1/visittype?v=custom:(uuid,name,display,retired,description)",
            cookie,
        )
    )
    types = []
    for row in rows:
        name = str(row.get("name") or row.get("display") or "")
        if row.get("retired") or name.strip().upper() not in RECEPTION_START_VISIT_TYPES:
            continue
        # Keep OpenMRS display name "ANC" stable for matching; staff label is separate.
        canonical = "ANC" if name.strip().upper() == "ANC" else name
        types.append(
            {
                "uuid": str(row.get("uuid")),
                "name": canonical,
                "label": _staff_visit_label(canonical),
                "helper": _staff_visit_helper(canonical),
                "bucket": _visit_bucket(canonical),
            }
        )
    order = ["OPD", "ANC", "Follow Up", "Nursing Treatment", "EMERGENCY", "IPD"]
    types.sort(key=lambda item: (order.index(item["name"]) if item["name"] in order else 99, item["label"]))
    return types


def locations_for_visit(visit: dict[str, Any], locations: list[dict[str, Any]]) -> list[dict[str, str]]:
    bucket = visit.get("bucket") or "outpatient"
    if bucket == "outpatient":
        matched = [
            {"uuid": row["uuid"], "name": row["name"]}
            for row in locations
            if str(row.get("name") or "").strip().lower() == DEFAULT_OUTPATIENT_LOCATION_NAME.lower()
        ]
        return matched
    matched = [
        {"uuid": row["uuid"], "name": row["name"]}
        for row in locations
        if _location_allowed(row, bucket)
    ]
    matched.sort(key=lambda row: row["name"])
    return matched


def registration_desk_location(locations: list[dict[str, str]]) -> dict[str, str] | None:
    for row in locations:
        if row["name"].strip().lower() == "registration desk":
            return row
    return locations[0] if locations else None


def _visit_type_options(cookie: str) -> list[dict[str, Any]]:
    locations = load_login_locations(cookie)
    visit_types = load_visit_types(cookie)
    for visit in visit_types:
        visit["locations"] = locations_for_visit(visit, locations)
        visit["defaultLocationUuid"] = (
            visit["locations"][0]["uuid"] if len(visit["locations"]) == 1 else ""
        )
    return visit_types


def build_registration_metadata(cookie: str) -> dict[str, Any]:
    require_registrar(cookie)
    import registration as reception

    identifier = load_identifier_type(cookie)
    attributes = load_person_attributes(cookie)
    relationships = load_relationship_types(cookie)
    locations = load_login_locations(cookie)
    visit_types = _visit_type_options(cookie)
    try:
        fees = reception.card_catalog(cookie)
    except Exception:
        fees = []
    return {
        "status": "ok",
        "identifier": identifier,
        "personAttributes": attributes,
        "addressFields": [{"name": name, "label": label} for name, label in ADDRESS_FIELDS],
        "relationshipTypes": relationships,
        "visitTypes": visit_types,
        "locations": locations,
        "cards": fees,
        "queueAvailable": False,
        "duplicateCheck": "openmrs-search",
    }


def search_patient_matches(cookie: str, query: str) -> list[dict[str, str]]:
    term = query.strip()
    if len(term) < 2:
        return []
    payload = _openmrs_json(
        "/openmrs/ws/rest/v1/patient?"
        + f"q={quote(term)}&v=custom:(uuid,display,identifiers:(identifier),person:(gender,age,preferredName:(givenName,familyName)))&limit=8",
        cookie,
        fallback="Patients could not be searched.",
    )
    matches = []
    for row in _results(payload):
        person = row.get("person") if isinstance(row.get("person"), dict) else {}
        name = person.get("preferredName") if isinstance(person.get("preferredName"), dict) else {}
        display = str(row.get("display") or "")
        identifier = ""
        identifiers = row.get("identifiers") if isinstance(row.get("identifiers"), list) else []
        if identifiers and isinstance(identifiers[0], dict):
            identifier = str(identifiers[0].get("identifier") or "")
        given = str(name.get("givenName") or "")
        family = str(name.get("familyName") or "")
        matches.append(
            {
                "uuid": str(row.get("uuid") or ""),
                "display": display,
                "name": f"{given} {family}".strip() or display,
                "mrn": identifier,
                "age": "" if person.get("age") is None else str(person.get("age")),
                "sex": {"M": "Male", "F": "Female"}.get(str(person.get("gender") or ""), str(person.get("gender") or "")),
            }
        )
    return matches


def _generate_identifier(cookie: str) -> str:
    payload = _openmrs_json(
        f"/openmrs/module/idgen/generateIdentifier.form?source={IDENTIFIER_SOURCE}&comment=abikan-reception",
        cookie,
        fallback="A hospital number could not be created.",
    )
    identifiers = payload.get("identifiers") if isinstance(payload, dict) else None
    if not isinstance(identifiers, list) or not identifiers:
        raise ApiError(502, "identifier_failed", "A hospital number could not be created.")
    value = str(identifiers[0] or "").strip()
    if not value:
        raise ApiError(502, "identifier_failed", "A hospital number could not be created.")
    return value


def _birthdate_from_age(age: str) -> tuple[str, bool]:
    try:
        years = int(str(age).strip())
    except ValueError as error:
        raise ApiError(422, "invalid_age", "Enter a valid age in years.") from error
    if years < 0 or years > 130:
        raise ApiError(422, "invalid_age", "Enter a valid age in years.")
    born = datetime.now(timezone.utc).date() - timedelta(days=years * 365)
    return born.isoformat(), True


def _person_payload(
    body: dict[str, Any],
    attribute_types: list[dict[str, Any]],
    existing_attributes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    given = str(body.get("givenName") or "").strip()
    family = str(body.get("familyName") or "").strip()
    middle = str(body.get("middleName") or "").strip()
    gender = str(body.get("gender") or "").strip().upper()
    if not given or not family:
        raise ApiError(422, "name_required", "Enter the patient's first and last name.")
    if gender not in {"M", "F", "O"}:
        raise ApiError(422, "sex_required", "Select male, female, or other.")
    birthdate = str(body.get("birthdate") or "").strip()
    estimated = bool(body.get("birthdateEstimated"))
    if not birthdate:
        age = str(body.get("age") or "").strip()
        if not age:
            raise ApiError(422, "birthdate_required", "Enter a date of birth or an age.")
        birthdate, estimated = _birthdate_from_age(age)
    if bool(body.get("nhis")):
        import consultation as clinical

        given, middle, family = clinical.apply_nhis_mark(given, middle, family, True)
    name = {"givenName": given, "familyName": family, "preferred": True}
    if middle:
        name["middleName"] = middle
    person: dict[str, Any] = {
        "gender": gender,
        "birthdate": birthdate,
        "birthdateEstimated": estimated,
        "names": [name],
    }
    # Life status is Admin-only. Registration never collects Alive/Deceased.
    # New patients are Alive; edits leave the existing OpenMRS person.dead alone.
    if existing_attributes is None:
        person["dead"] = False
    address = body.get("address") if isinstance(body.get("address"), dict) else {}
    address_row = {
        key: str(address.get(key) or "").strip()
        for key, _label in ADDRESS_FIELDS
        if str(address.get(key) or "").strip()
    }
    if address_row:
        address_row["preferred"] = True
        person["addresses"] = [address_row]
    attributes_in = body.get("attributes") if isinstance(body.get("attributes"), dict) else {}
    existing_by_name = {
        str(row.get("name") or ""): str(row.get("uuid") or "")
        for row in (existing_attributes or [])
        if isinstance(row, dict) and row.get("name") and row.get("uuid")
    }
    attributes = []
    for field in attribute_types:
        value = str(attributes_in.get(field["name"]) or "").strip()
        if value:
            attr: dict[str, Any] = {"attributeType": field["uuid"], "value": value}
            existing_uuid = existing_by_name.get(field["name"]) or ""
            if existing_uuid:
                attr["uuid"] = existing_uuid
            attributes.append(attr)
    if attributes:
        person["attributes"] = attributes
    return person


def _possible_duplicates(cookie: str, body: dict[str, Any]) -> list[dict[str, str]]:
    given = str(body.get("givenName") or "").strip()
    family = str(body.get("familyName") or "").strip()
    attributes = body.get("attributes") if isinstance(body.get("attributes"), dict) else {}
    phone = str(attributes.get("phoneNumber") or body.get("phone") or "").strip()
    seen: dict[str, dict[str, str]] = {}
    for term in (f"{given} {family}".strip(), phone):
        for match in search_patient_matches(cookie, term):
            if match.get("uuid"):
                seen[match["uuid"]] = match
    return list(seen.values())


def ensure_card_type_attribute(cookie: str) -> None:
    """Make sure OpenMRS can store Individual / Family hospital card type."""
    for field in load_person_attributes(cookie):
        if field.get("name") == "cardType":
            return
    try:
        _openmrs_json(
            "/openmrs/ws/rest/v1/personattributetype",
            cookie,
            method="POST",
            payload={
                "name": "cardType",
                "description": "Hospital card type (Individual or Family)",
                "format": "java.lang.String",
                "searchable": False,
            },
            fallback="Hospital card type could not be prepared.",
        )
    except ApiError:
        # Attribute may already exist, or this session cannot create types.
        # Registration still continues; Patients list shows blank Card Type if write fails.
        return


def create_patient(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_registrar(cookie)
    import hospital_family as household

    # Hospital card type is Individual or Family only.
    # ANC is a separate enrollment/service on an existing patient — never a registration category.
    card_type = str(body.get("cardType") or "").strip().lower()
    attributes = body.get("attributes") if isinstance(body.get("attributes"), dict) else {}
    attributes = dict(attributes)
    # Ignore mistaken ANC values from older clients; do not store them as identity.
    if str(attributes.get("cardType") or "").strip().lower() in {"antenatal", "anc"}:
        attributes.pop("cardType", None)
    if card_type in {"individual", "family"}:
        attributes["cardType"] = card_type
        body = {**body, "attributes": attributes, "cardType": card_type}
        ensure_card_type_attribute(cookie)
    elif attributes:
        body = {**body, "attributes": attributes}

    plan = household.prepare_family_registration(body)
    if plan.get("conflict"):
        raise ApiError(409, "family_exists", household.FAMILY_EXISTS_MESSAGE)
    if not body.get("confirmDuplicate"):
        matches = _possible_duplicates(cookie, body)
        if matches:
            raise ApiError(
                409,
                "possible_duplicate",
                "A similar patient is already registered. Open the existing record instead of creating another.",
            )
    attribute_types = load_person_attributes(cookie)
    identifier_type = load_identifier_type(cookie)
    locations = load_login_locations(cookie)
    desk = registration_desk_location(locations)
    if not desk:
        raise ApiError(502, "location_missing", "Reception location is not configured.")
    identifier = _generate_identifier(cookie)
    person = _person_payload(body, attribute_types)
    created = _openmrs_json(
        "/openmrs/ws/rest/v1/patient",
        cookie,
        method="POST",
        payload={
            "identifiers": [
                {
                    "identifier": identifier,
                    "identifierType": identifier_type["uuid"],
                    "location": desk["uuid"],
                    "preferred": True,
                }
            ],
            "person": person,
        },
        fallback="The patient could not be registered.",
    )
    uuid = str(created.get("uuid") or "")
    if not uuid:
        raise ApiError(502, "register_failed", "The patient could not be registered.")
    extra_ids = body.get("otherIdentifiers") if isinstance(body.get("otherIdentifiers"), list) else []
    for item in extra_ids:
        if not isinstance(item, dict):
            continue
        value = str(item.get("identifier") or "").strip()
        type_uuid = str(item.get("identifierType") or "").strip()
        if not value or not type_uuid:
            continue
        _openmrs_json(
            f"/openmrs/ws/rest/v1/patient/{uuid}/identifier",
            cookie,
            method="POST",
            payload={"identifier": value, "identifierType": type_uuid, "location": desk["uuid"]},
            fallback="An extra identifier could not be saved.",
        )
    kin = body.get("nextOfKin") if isinstance(body.get("nextOfKin"), dict) else {}
    kin_given = str(kin.get("givenName") or "").strip()
    kin_family = str(kin.get("familyName") or "").strip()
    kin_type = str(kin.get("relationshipType") or "").strip()
    if kin_given and kin_family and kin_type:
        relative = _openmrs_json(
            "/openmrs/ws/rest/v1/person",
            cookie,
            method="POST",
            payload={
                "gender": str(kin.get("gender") or "F").strip().upper()[:1] or "F",
                "names": [{"givenName": kin_given, "familyName": kin_family, "preferred": True}],
            },
            fallback="Next of kin could not be saved.",
        )
        person_b = str(relative.get("uuid") or "")
        if person_b:
            _openmrs_json(
                "/openmrs/ws/rest/v1/relationship",
                cookie,
                method="POST",
                payload={"personA": uuid, "personB": person_b, "relationshipType": kin_type},
                fallback="Next of kin could not be saved.",
            )
    display = str(created.get("display") or f"{identifier} - {person['names'][0]['givenName']} {person['names'][0]['familyName']}")
    payload = {
        "status": "ok",
        "uuid": uuid,
        "identifier": identifier,
        "display": display,
        "identifierSource": "ABC",
        "family": None,
        "newCardCreated": False,
        "feeWillBeGenerated": False,
    }
    if plan.get("mode") in {"existing", "new"}:
        try:
            linked = household.apply_registration(
                uuid,
                plan,
                user,
                member_name=f"{person['names'][0]['givenName']} {person['names'][0]['familyName']}".strip(),
                member_identifier=identifier,
            )
            payload.update(linked)
        except ApiError:
            payload["familyWarning"] = (
                "The patient was registered, but could not be linked to the family. "
                "Open Families to add them to the Family Card."
            )
    try:
        import consultation as clinical

        clinical.store_patient_nhis(clinical.odoo_reader(), uuid, bool(body.get("nhis")))
        payload["nhis"] = bool(body.get("nhis"))
    except Exception as error:
        print(f"registration NHIS mark was not saved: {error}", flush=True)
        payload["nhisWarning"] = (
            "The patient was registered, but NHIS could not be saved. Open the record and tick NHIS again."
        )
    try:
        import registration as reception

        billed = reception.bill_new_card(uuid, cookie, str(attributes.get("cardType") or "individual"))
        billed_now = bool(billed and billed.get("hasCharge") and not billed.get("cardAlreadyRegistered"))
        payload["feeWillBeGenerated"] = billed_now
        payload["newCardCreated"] = billed_now
    except Exception as error:
        print(f"registration card bill was not created: {error}", flush=True)
    try:
        patient = reception.load_openmrs_patient(uuid, cookie)
        if not reception.ensure_patient_partner(reception.odoo_reader(), patient, wait=False):
            print("registration bill account was not opened", flush=True)
    except Exception as error:
        print(f"registration bill account was not opened: {error}", flush=True)
    return payload


def create_patient_response(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    require_registrar(cookie)
    import hospital_family as household

    plan = household.prepare_family_registration(body)
    if plan.get("conflict"):
        return {
            "status": "error",
            "code": "family_exists",
            "message": household.FAMILY_EXISTS_MESSAGE,
            "families": plan.get("families") or [],
            "matches": [],
        }
    if not body.get("confirmDuplicate"):
        matches = _possible_duplicates(cookie, body)
        if matches:
            return {
                "status": "error",
                "code": "possible_duplicate",
                "message": "A similar patient is already registered. Open the existing record instead of creating another.",
                "matches": matches,
            }
    created = create_patient({**body, "confirmDuplicate": True, "confirmCreateFamily": True}, cookie)
    created["matches"] = []
    return created


def clinical_name_part(value: str) -> str:
    """Registration edits the real name. The NHIS mark is added again on save."""
    import consultation as clinical

    return clinical.strip_nhis_mark(value)


def _patient_is_nhis(patient_uuid: str) -> bool:
    try:
        import consultation as clinical

        return clinical.patient_is_nhis(clinical.odoo_reader(), patient_uuid)
    except Exception:
        return False


def read_patient_profile(patient_uuid: str, cookie: str) -> dict[str, Any]:
    patient = _openmrs_json(
        f"/openmrs/ws/rest/v1/patient/{quote(patient_uuid)}?v=full",
        cookie,
        fallback="This patient could not be loaded.",
    )
    person = patient.get("person") if isinstance(patient.get("person"), dict) else {}
    name = person.get("preferredName") if isinstance(person.get("preferredName"), dict) else {}
    address = person.get("preferredAddress") if isinstance(person.get("preferredAddress"), dict) else {}
    attributes = {}
    attribute_records = []
    for row in person.get("attributes") or []:
        if not isinstance(row, dict) or row.get("voided"):
            continue
        attr_type = row.get("attributeType") if isinstance(row.get("attributeType"), dict) else {}
        key = str(attr_type.get("display") or attr_type.get("name") or "")
        if key:
            value = str(row.get("value") or "")
            attributes[key] = value
            attribute_records.append(
                {
                    "name": key,
                    "uuid": str(row.get("uuid") or ""),
                    "value": value,
                }
            )
    identifiers = []
    for row in patient.get("identifiers") or []:
        if not isinstance(row, dict) or row.get("voided"):
            continue
        ident_type = row.get("identifierType") if isinstance(row.get("identifierType"), dict) else {}
        identifiers.append(
            {
                "uuid": str(row.get("uuid") or ""),
                "identifier": str(row.get("identifier") or ""),
                "preferred": bool(row.get("preferred")),
                "type": str(ident_type.get("display") or ident_type.get("name") or ""),
            }
        )
    preferred = next((row for row in identifiers if row.get("preferred")), identifiers[0] if identifiers else {})
    created = str(patient.get("dateCreated") or person.get("dateCreated") or "")
    return {
        "status": "ok",
        "uuid": str(patient.get("uuid") or patient_uuid),
        "personUuid": str(person.get("uuid") or ""),
        "identifier": preferred.get("identifier") or "",
        "givenName": clinical_name_part(str(name.get("givenName") or "")),
        "middleName": clinical_name_part(str(name.get("middleName") or "")),
        "familyName": clinical_name_part(str(name.get("familyName") or "")),
        "gender": str(person.get("gender") or ""),
        "birthdate": str(person.get("birthdate") or "")[:10],
        "birthdateEstimated": bool(person.get("birthdateEstimated")),
        "age": person.get("age"),
        "attributes": attributes,
        "attributeRecords": attribute_records,
        "address": {key: str(address.get(key) or "") for key, _label in ADDRESS_FIELDS},
        "identifiers": identifiers,
        "registeredOn": created[:10],
        "nameUuid": str(name.get("uuid") or ""),
        "addressUuid": str(address.get("uuid") or ""),
        "nhis": _patient_is_nhis(str(patient.get("uuid") or patient_uuid)),
    }


def load_patient_profile(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_registrar(cookie)
    profile = read_patient_profile(patient_uuid, cookie)
    import hospital_family as household

    profile["family"] = household.family_for_patient(patient_uuid)
    return profile


def update_patient(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    require_registrar(cookie)
    profile = load_patient_profile(patient_uuid, cookie)
    if not profile.get("uuid"):
        raise ApiError(404, "patient_not_found", "This patient was not found.")
    attribute_types = load_person_attributes(cookie)
    existing_attributes = profile.get("attributeRecords")
    if not isinstance(existing_attributes, list):
        existing_attributes = []
    payload_body = dict(body)
    if "nhis" not in payload_body:
        payload_body["nhis"] = _patient_is_nhis(patient_uuid)
    person = _person_payload(payload_body, attribute_types, existing_attributes)
    if profile.get("nameUuid"):
        person["names"][0]["uuid"] = profile["nameUuid"]
    if profile.get("addressUuid") and person.get("addresses"):
        person["addresses"][0]["uuid"] = profile["addressUuid"]
    # Reception has Edit Patients, not Edit People. Person REST 403s after a
    # successful-looking form save and is remapped as a false access error.
    _openmrs_json(
        f"/openmrs/ws/rest/v1/patient/{quote(patient_uuid)}",
        cookie,
        method="POST",
        payload={"person": person},
        fallback="The patient details could not be saved.",
    )
    if "nhis" in body:
        import consultation as clinical

        clinical.store_patient_nhis(clinical.odoo_reader(), patient_uuid, bool(body.get("nhis")))
    return load_patient_profile(patient_uuid, cookie)


def _existing_visit_result(
    visit: dict[str, Any],
    *,
    code: str,
    message: str,
) -> dict[str, Any]:
    visit_type = str(visit.get("visitType") or "")
    return {
        "status": "existing",
        "created": False,
        "code": code,
        "message": message,
        "uuid": visit.get("uuid") or "",
        "visitType": visit_type,
        "visitTypeLabel": _staff_visit_label(visit_type),
        "location": visit.get("location") or "",
        "locationUuid": visit.get("locationUuid") or "",
        "startDatetime": visit.get("startDatetime") or "",
        "dailyVisitNumber": visit.get("dailyVisitNumber") or "",
        "open": bool(visit.get("open", True)),
    }


def _admission_visit_context(patient_uuid: str, cookie: str) -> dict[str, str] | None:
    try:
        import inpatient

        return inpatient.inpatient_order_context(patient_uuid, cookie)
    except Exception:
        return None


def _patient_occupied(patient_uuid: str, cookie: str) -> bool:
    try:
        import inpatient

        assignment = inpatient.current_assignment(patient_uuid, cookie, scan_board=True)
        if not assignment:
            return False
        assigned = str(assignment.get("patientUuid") or patient_uuid)
        return assigned == patient_uuid
    except Exception:
        return False


def build_visit_context(patient_uuid: str, cookie: str) -> dict[str, Any]:
    """Existing-patient visit state. OpenMRS only. No card fee. No Odoo."""
    require_registrar(cookie)
    import registration as reception

    patient = reception.load_openmrs_patient(patient_uuid, cookie)
    visit = reception.latest_open_visit(patient_uuid, cookie)
    occupied = _patient_occupied(patient_uuid, cookie)
    admission = _admission_visit_context(patient_uuid, cookie)
    admission_active = occupied or bool(admission and admission.get("visitUuid"))
    if admission_active and not visit and admission and admission.get("visitUuid"):
        visit = reception.load_visit(admission["visitUuid"], patient_uuid, cookie)
    if visit and str(visit.get("visitType") or "").upper() == "IPD":
        admission_active = True
    code = None
    message = None
    if admission_active:
        code = reception.ADMISSION_IN_PROGRESS_CODE
        message = reception.ADMISSION_IN_PROGRESS_MESSAGE
    elif visit:
        code = reception.VISIT_ALREADY_OPEN_CODE
        message = reception.VISIT_ALREADY_OPEN_MESSAGE
    try:
        visit_types = _visit_type_options(cookie)
    except Exception:
        visit_types = []
    return {
        "status": "ok",
        "patient": patient,
        "visit": visit,
        "visitTypes": visit_types,
        "admissionActive": admission_active,
        "canStartVisit": not visit and not admission_active,
        "code": code,
        "message": message,
    }


def start_visit(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_registrar(cookie)
    import registration as reception

    occupied = _patient_occupied(patient_uuid, cookie)
    admission = _admission_visit_context(patient_uuid, cookie)
    if occupied:
        if admission and admission.get("visitUuid"):
            visit = reception.load_visit(admission["visitUuid"], patient_uuid, cookie)
            return _existing_visit_result(
                visit,
                code=reception.ADMISSION_IN_PROGRESS_CODE,
                message=reception.ADMISSION_IN_PROGRESS_MESSAGE,
            )
        open_visit = reception.latest_open_visit(patient_uuid, cookie)
        if open_visit:
            code = (
                reception.ADMISSION_IN_PROGRESS_CODE
                if str(open_visit.get("visitType") or "").upper() == "IPD"
                else reception.VISIT_ALREADY_OPEN_CODE
            )
            message = (
                reception.ADMISSION_IN_PROGRESS_MESSAGE
                if code == reception.ADMISSION_IN_PROGRESS_CODE
                else reception.VISIT_ALREADY_OPEN_MESSAGE
            )
            return _existing_visit_result(open_visit, code=code, message=message)
        return {
            "status": "existing",
            "created": False,
            "code": reception.ADMISSION_IN_PROGRESS_CODE,
            "message": reception.ADMISSION_IN_PROGRESS_MESSAGE,
            "uuid": "",
            "visitType": "IPD",
            "visitTypeLabel": _staff_visit_label("IPD"),
            "location": "",
            "locationUuid": "",
            "startDatetime": "",
            "open": True,
        }

    existing = reception.latest_open_visit(patient_uuid, cookie)
    if existing:
        ipd = str(existing.get("visitType") or "").upper() == "IPD"
        return _existing_visit_result(
            existing,
            code=reception.ADMISSION_IN_PROGRESS_CODE if ipd else reception.VISIT_ALREADY_OPEN_CODE,
            message=(
                reception.ADMISSION_IN_PROGRESS_MESSAGE
                if ipd
                else reception.VISIT_ALREADY_OPEN_MESSAGE
            ),
        )

    location_uuid = str(body.get("locationUuid") or "").strip()
    visit_type_uuid = str(body.get("visitTypeUuid") or "").strip()
    if not visit_type_uuid:
        raise ApiError(422, "visit_type_required", "Select the kind of visit.")
    visit_types = load_visit_types(cookie)
    chosen = next((row for row in visit_types if row["uuid"] == visit_type_uuid), None)
    if not chosen:
        raise ApiError(422, "visit_type_invalid", "That visit type is not available.")
    if str(chosen.get("name") or "").strip().upper() == "ANC":
        import antenatal as anc

        if not anc.patient_is_enrolled(patient_uuid):
            raise ApiError(
                422,
                anc.ANC_NOT_ENROLLED_CODE,
                anc.ANC_NOT_ENROLLED_MESSAGE,
            )
        anc.require_anc_card_enabled(patient_uuid)
    locations = locations_for_visit(chosen, load_login_locations(cookie))
    if not locations:
        raise ApiError(422, "location_unavailable", LOCATION_UNAVAILABLE_MESSAGE)
    if chosen.get("bucket") != "inpatient":
        location_uuid = locations[0]["uuid"]
    elif not location_uuid:
        if len(locations) == 1:
            location_uuid = locations[0]["uuid"]
        else:
            raise ApiError(422, "location_required", LOCATION_REQUIRED_MESSAGE)
    allowed = {row["uuid"] for row in locations}
    if location_uuid not in allowed:
        raise ApiError(422, "location_invalid", LOCATION_REQUIRED_MESSAGE)
    import daily_visit_number as daily

    daily.ignore_client_number(body)
    request_id = str(body.get("requestId") or "").strip()
    reused = daily.begin_request(request_id)
    if reused:
        if reused.get("created") and reused.get("uuid"):
            _emit_visit_started_notification(
                patient_uuid=patient_uuid,
                visit_uuid=str(reused.get("uuid") or ""),
                daily_visit_number=str(reused.get("dailyVisitNumber") or ""),
                request_id=request_id,
                user=user,
                cookie=cookie,
                visit_type=str(chosen.get("name") or ""),
            )
        return reused
    try:
        created, visit_number = daily.create_visit_with_number(
            cookie,
            {
                "patient": patient_uuid,
                "visitType": visit_type_uuid,
                "location": location_uuid,
                "startDatetime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
            },
        )
        uuid = str(created.get("uuid") or "")
        if not uuid:
            raise ApiError(502, "visit_failed", "The visit could not be started.")
        location_name = next((row["name"] for row in locations if row["uuid"] == location_uuid), "")
        result = {
            "status": "ok",
            "created": True,
            "uuid": uuid,
            "visitType": chosen["name"],
            "visitTypeLabel": chosen["label"],
            "location": location_name,
            "locationUuid": location_uuid,
            "startDatetime": created.get("startDatetime") or "",
            "dailyVisitNumber": visit_number,
            "open": True,
        }
        daily.finish_request(request_id, result, ok=True)
        _emit_visit_started_notification(
            patient_uuid=patient_uuid,
            visit_uuid=uuid,
            daily_visit_number=str(visit_number or ""),
            request_id=request_id,
            user=user,
            cookie=cookie,
            visit_type=str(chosen.get("name") or ""),
        )
        return result
    except Exception:
        daily.finish_request(request_id, None, ok=False)
        raise


def _emit_visit_started_notification(
    *,
    patient_uuid: str,
    visit_uuid: str,
    daily_visit_number: str,
    request_id: str,
    user: dict[str, Any],
    cookie: str,
    visit_type: str = "",
) -> None:
    """Notify Clinical after a new visit is actually created. Never on validation failure."""
    try:
        import notifications as staff_notes
        from clinical_queue import name_and_mrn

        patient = _openmrs_json(
            f"/openmrs/ws/rest/v1/patient/{quote(patient_uuid)}"
            "?v=custom:(uuid,display,identifiers:(identifier,preferred))",
            cookie,
            fallback="Patient details could not be loaded.",
        )
        if not isinstance(patient, dict):
            patient = {}
        name, mrn = name_and_mrn(patient.get("display"), patient.get("identifiers"))
        sender_username = str(user.get("username") or "reception")
        sender_display = str(user.get("username") or "Reception")
        if visit_type.strip().upper() == "NURSING TREATMENT":
            staff_notes.emit_nursing_treatment_started(
                patient_uuid=patient_uuid,
                visit_uuid=visit_uuid,
                patient_name=name or "Patient",
                mrn=mrn or "—",
                sender_username=sender_username,
                sender_display=sender_display,
                request_id=request_id,
            )
        else:
            staff_notes.emit_visit_started(
                patient_uuid=patient_uuid,
                visit_uuid=visit_uuid,
                patient_name=name or "Patient",
                mrn=mrn or "—",
                sender_username=sender_username,
                sender_display=sender_display,
                daily_visit_number=daily_visit_number,
                request_id=request_id,
            )
    except Exception:
        # Visit already started; never fail the arrival workflow on a notify miss.
        return


VISIT_ALREADY_CLOSED_CODE = "visit_already_closed"
VISIT_ALREADY_CLOSED_MESSAGE = "This visit is already closed."
CANNOT_CLOSE_ADMISSION_CODE = "cannot_close_admission"
CANNOT_CLOSE_ADMISSION_MESSAGE = (
    "An admitted patient's stay is closed by discharge, not by closing an outpatient visit."
)
CLOSE_VISIT_SUCCESS_MESSAGE = "Visit closed successfully."


def _now_openmrs() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _visit_type_is_ipd(visit: dict[str, Any]) -> bool:
    return str(visit.get("visitType") or "").upper() == "IPD"


def can_close_outpatient_visit(
    visit: dict[str, Any] | None,
    *,
    admission_active: bool,
    admission_visit_uuid: str = "",
) -> tuple[bool, str | None, str | None]:
    if not visit or not visit.get("uuid"):
        return False, "visit_not_found", "This visit was not found."
    if _visit_type_is_ipd(visit) or admission_active:
        return False, CANNOT_CLOSE_ADMISSION_CODE, CANNOT_CLOSE_ADMISSION_MESSAGE
    if not visit.get("open"):
        return False, VISIT_ALREADY_CLOSED_CODE, VISIT_ALREADY_CLOSED_MESSAGE
    return True, None, None


def close_visit(patient_uuid: str, visit_uuid: str, cookie: str) -> dict[str, Any]:
    """Close a completed outpatient visit. Sets stopDatetime only. Does not rewrite encounters."""
    require_registrar(cookie)
    import registration as reception

    visit = reception.load_visit(visit_uuid, patient_uuid, cookie)
    occupied = _patient_occupied(patient_uuid, cookie)
    admission = _admission_visit_context(patient_uuid, cookie)
    admission_visit_uuid = str((admission or {}).get("visitUuid") or "")
    admission_active = occupied or bool(admission_visit_uuid)
    if _visit_type_is_ipd(visit):
        admission_active = True
    allowed, code, message = can_close_outpatient_visit(
        visit,
        admission_active=admission_active,
        admission_visit_uuid=admission_visit_uuid,
    )
    if not allowed:
        raise ApiError(409, code or "cannot_close_visit", message or "This visit cannot be closed.")

    stop = _now_openmrs()
    updated = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}",
        cookie,
        method="POST",
        payload={"stopDatetime": stop},
        fallback="The visit could not be closed.",
    )
    closed = reception.load_visit(visit_uuid, patient_uuid, cookie)
    visit_type = str(closed.get("visitType") or visit.get("visitType") or "")
    return {
        "status": "ok",
        "uuid": visit_uuid,
        "visitType": visit_type,
        "visitTypeLabel": _staff_visit_label(visit_type),
        "location": closed.get("location") or visit.get("location") or "",
        "startDatetime": closed.get("startDatetime") or visit.get("startDatetime") or "",
        "stopDatetime": (updated.get("stopDatetime") if isinstance(updated, dict) else None) or stop,
        "open": False,
        "message": CLOSE_VISIT_SUCCESS_MESSAGE,
    }
