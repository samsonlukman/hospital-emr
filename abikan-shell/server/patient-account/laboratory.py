"""Laboratory fee charges.

Creates an Odoo sale order for mapped laboratory service products, then
confirms it so automated invoicing posts a customer invoice. Payment stays
on the Accountant path. OpenMRS Dispensed, Pharmacy stock, Registration,
Consultation, and OpenELIS results are never written here.

Idempotency key is lab:{orderUuid}. Product mapping prefers an isolated
TEST product (default_code = OpenMRS concept uuid), then product.uuid =
concept uuid. Placeholder catalogue prices of 1.00 are refused.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import lab_catalogue

import xmlrpc.client

import inpatient as ward
import server as core

LAB_PRIVILEGE = "app:lab-lite"
CLINICAL_PRIVILEGE = "app:clinical"
LAB_ROLES = {"SuperAdmin", "System Developer"}
SHOP_NAME = "Laboratory"
CATEGORY_NAME = "Laboratory"
EXTERNAL_PREFIX = "lab:"
WALKIN_REF_PREFIX = "LAB-WALKIN:"
LAB_ORDER_TYPE_UUID = "d3560b17-5e07-11ef-8f7c-0242ac120002"
LAB_ORDER_TYPE_NAME = "Lab Order"
UNLISTED_LAB_CONCEPT_UUID = "1d528c77-05f2-453f-a735-51c290a01f07"
UNLISTED_LAB_MARKER = "Unlisted laboratory test: "
CONSULTATION_ENCOUNTER_TYPE = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
DIRECT_SOURCE_MARKER = "[Lab Direct]"
EXTERNAL_REFERRAL_MARKER = "[External Referral]"
SOURCE_DOCTOR_ORDER = "doctor_order"
SOURCE_LABORATORY_DIRECT = "laboratory_direct"
SOURCE_EXTERNAL_REFERRAL = "external_referral"
HISTORY_DEFAULT_LIMIT = 25
HISTORY_MAX_LIMIT = 100
PLACEHOLDER_PRICE = 1.01
NGN_CURRENCY = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
OPENELIS_URL = os.environ.get("ABIKAN_OPENELIS_URL", "http://openelis:8052/openelis").rstrip("/")
OPENELIS_USER = os.environ.get("ABIKAN_OPENELIS_USER", "")
OPENELIS_PASSWORD = os.environ.get("ABIKAN_OPENELIS_PASSWORD", "")

LOGGER = logging.getLogger(__name__)

# Exact OpenELIS terms observed in this deployment or defined in status_of_sample.
# The UI may group them, but laboratoryStatus always preserves the source term.
OPENELIS_PENDING_STATUSES = {
    "not started",
    "not tested",
    "sampleentered",
    "test entered",
}
OPENELIS_PROCESSING_STATUSES = {
    "testing started",
    "testing finished",
    "technical acceptance",
    "technical acceptance ro",
}
OPENELIS_COMPLETED_STATUSES = {
    "finalized",
    "finalized ro",
    "marked as done",
    "results final",
}


def patient_age_label(birth: Any, today: Any = None) -> str:
    """Age in plain language, from the patient's date of birth."""
    if birth is None or birth == "":
        return ""
    if isinstance(birth, datetime):
        born = birth.date()
    elif hasattr(birth, "year") and hasattr(birth, "month") and hasattr(birth, "day"):
        born = birth
    else:
        try:
            born = datetime.strptime(str(birth)[:10], "%Y-%m-%d").date()
        except ValueError:
            return ""
    current = today or datetime.now().date()
    if hasattr(current, "date"):
        current = current.date()
    if born > current:
        return ""
    years = current.year - born.year - ((current.month, current.day) < (born.month, born.day))
    if years >= 2:
        return f"{years} years"
    months = (current.year - born.year) * 12 + current.month - born.month
    if current.day < born.day:
        months -= 1
    if months >= 1:
        return "1 month" if months == 1 else f"{months} months"
    days = (current - born).days
    if days <= 1:
        return "1 day"
    return f"{days} days"


def _patient_facts(patient_uuid: str) -> dict[str, str]:
    if not patient_uuid:
        return {}
    import openmrs_sql

    try:
        rows = openmrs_sql.fetch_all(
            """
            SELECT pn.given_name, pn.family_name, per.gender, per.birthdate
            FROM person per
            LEFT JOIN person_name pn
              ON pn.person_id = per.person_id AND pn.voided = 0 AND pn.preferred = 1
            WHERE per.uuid = %s
            LIMIT 1
            """,
            (patient_uuid,),
        )
    except Exception:
        return {}
    if not rows:
        return {}
    given, family, gender, birth = rows[0]
    birth_text = birth.strftime("%d/%m/%Y") if hasattr(birth, "strftime") else ""
    return {
        "givenName": str(given or "").strip(),
        "familyName": str(family or "").strip(),
        "gender": str(gender or "").strip(),
        "birthDate": birth_text,
        "age": patient_age_label(birth),
    }

# Isolated TEST product. Does not modify catalogue product 1820.
TEST_CONCEPT_UUID = "32AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
TEST_PRODUCT_NAME = "Malarial smear — TEST"
TEST_LIST_PRICE = 40.0

ApiError = core.ApiError
OdooReader = core.OdooReader
ODOO_DB = core.ODOO_DB
ODOO_PASSWORD = core.ODOO_PASSWORD
as_float = core.as_float
find_partner = core.find_partner
format_money = core.format_money
load_currency = core.load_currency
load_openmrs_patient = core.load_openmrs_patient
many2one_id = core.many2one_id
many2one_name = core.many2one_name
require_session = core.require_session

IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}
WORKFLOW_IDEMPOTENCY: dict[str, dict[str, Any]] = {}
WORKFLOW_ACCESSIONS_PATH = os.environ.get(
    "ABIKAN_LAB_WORKFLOW_DB",
    "/var/lib/abikan/laboratory-workflow.json",
)
WORKFLOW_VALIDATIONS_PATH = f"{WORKFLOW_ACCESSIONS_PATH}.validated"
WORKFLOW_VALIDATORS_PATH = f"{WORKFLOW_ACCESSIONS_PATH}.validators"
WORKFLOW_RESULTS_PATH = f"{WORKFLOW_ACCESSIONS_PATH}.results"


def _load_workflow_accessions() -> dict[str, str]:
    try:
        with open(WORKFLOW_ACCESSIONS_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return {str(key): str(accession) for key, accession in value.items() if str(accession).strip()}
    except (OSError, ValueError, AttributeError):
        return {}


WORKFLOW_ACCESSIONS: dict[str, str] = _load_workflow_accessions()
WORKFLOW_VALIDATIONS: dict[str, bool] = {}
try:
    with open(WORKFLOW_VALIDATIONS_PATH, encoding="utf-8") as handle:
        WORKFLOW_VALIDATIONS = {
            str(key): bool(value) for key, value in json.load(handle).items()
        }
except (OSError, ValueError, AttributeError):
    WORKFLOW_VALIDATIONS = {}
try:
    with open(WORKFLOW_VALIDATORS_PATH, encoding="utf-8") as handle:
        WORKFLOW_VALIDATORS: dict[str, str] = {
            str(key): str(value).strip()
            for key, value in json.load(handle).items()
            if str(value or "").strip()
        }
except (OSError, ValueError, AttributeError):
    WORKFLOW_VALIDATORS = {}
try:
    with open(WORKFLOW_RESULTS_PATH, encoding="utf-8") as handle:
        WORKFLOW_RESULTS: dict[str, list[dict[str, Any]]] = json.load(handle)
except (OSError, ValueError, AttributeError):
    WORKFLOW_RESULTS = {}


def _remember_workflow_accession(order_uuid: str, accession: str) -> None:
    with IDEMPOTENCY_LOCK:
        WORKFLOW_ACCESSIONS[order_uuid] = accession
        try:
            os.makedirs(os.path.dirname(WORKFLOW_ACCESSIONS_PATH), exist_ok=True)
            temporary_path = f"{WORKFLOW_ACCESSIONS_PATH}.tmp"
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(WORKFLOW_ACCESSIONS, handle)
            os.replace(temporary_path, WORKFLOW_ACCESSIONS_PATH)
        except OSError:
            LOGGER.warning("Could not persist laboratory accession order=%s", order_uuid)


def _remember_workflow_validation(order_uuid: str, validator: str = "") -> None:
    with IDEMPOTENCY_LOCK:
        WORKFLOW_VALIDATIONS[order_uuid] = True
        name = " ".join(str(validator or "").split())
        if name:
            WORKFLOW_VALIDATORS[order_uuid] = name
            for item in WORKFLOW_RESULTS.get(order_uuid) or []:
                if isinstance(item, dict):
                    item["validatedBy"] = name
        try:
            os.makedirs(os.path.dirname(WORKFLOW_VALIDATIONS_PATH), exist_ok=True)
            temporary_path = f"{WORKFLOW_VALIDATIONS_PATH}.tmp"
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(WORKFLOW_VALIDATIONS, handle)
            os.replace(temporary_path, WORKFLOW_VALIDATIONS_PATH)
            if name:
                name_path = f"{WORKFLOW_VALIDATORS_PATH}.tmp"
                with open(name_path, "w", encoding="utf-8") as handle:
                    json.dump(WORKFLOW_VALIDATORS, handle)
                os.replace(name_path, WORKFLOW_VALIDATORS_PATH)
                results_path = f"{WORKFLOW_RESULTS_PATH}.tmp"
                with open(results_path, "w", encoding="utf-8") as handle:
                    json.dump(WORKFLOW_RESULTS, handle)
                os.replace(results_path, WORKFLOW_RESULTS_PATH)
        except OSError:
            LOGGER.warning("Could not persist laboratory validation order=%s", order_uuid)


def _format_person_name(person: Any) -> str:
    if not isinstance(person, dict):
        return ""
    preferred = person.get("preferredName") if isinstance(person.get("preferredName"), dict) else {}
    given = str(preferred.get("givenName") or "").strip()
    family = str(preferred.get("familyName") or "").strip()
    full = " ".join(part for part in (given, family) if part)
    if full:
        return full
    return " ".join(str(person.get("display") or "").split())


def signed_in_staff_name(cookie: str) -> str:
    """First and last name of the person signed in now."""
    try:
        session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
    except Exception:
        return ""
    user = session.get("user") if isinstance(session, dict) and isinstance(session.get("user"), dict) else {}
    user_uuid = str(user.get("uuid") or "").strip()
    person = user.get("person") if isinstance(user.get("person"), dict) else {}
    person_uuid = str(person.get("uuid") or "").strip()
    if user_uuid:
        try:
            record = core.openmrs_service_get(
                f"/openmrs/ws/rest/v1/user/{quote(user_uuid)}"
                "?v=custom:(person:(uuid,display,preferredName:(givenName,familyName)))"
            )
            found = record.get("person") if isinstance(record, dict) else {}
            name = _format_person_name(found)
            if name:
                return name
            if isinstance(found, dict) and found.get("uuid"):
                person_uuid = str(found.get("uuid") or "").strip()
        except Exception:
            pass
    if person_uuid:
        try:
            detail = core.openmrs_service_get(
                f"/openmrs/ws/rest/v1/person/{quote(person_uuid)}"
                "?v=custom:(display,preferredName:(givenName,familyName))"
            )
            name = _format_person_name(detail)
            if name:
                return name
        except Exception:
            pass
    return _format_person_name(person)


def validator_name_for_order(order: dict[str, Any], cookie: str) -> str:
    """Name of the laboratory staff member who accepted and released the result."""
    candidates = list(_orders_on_same_request(order, cookie))
    focal_uuid = str(order.get("uuid") or "")
    if focal_uuid and all(str(row.get("uuid") or "") != focal_uuid for row in candidates):
        candidates.append(order)
    for member in candidates:
        order_uuid = str(member.get("uuid") or "")
        stored = WORKFLOW_VALIDATORS.get(order_uuid, "")
        if stored:
            return stored
        for item in WORKFLOW_RESULTS.get(order_uuid) or []:
            if not isinstance(item, dict):
                continue
            name = " ".join(str(item.get("validatedBy") or "").split())
            if name:
                return name
    return ""


REQUEST_MARKER = re.compile(r"\[Request ([0-9A-Za-z-]{8,40})\]")


def new_request_marker() -> str:
    return f"[Request {uuid.uuid4().hex[:12]}]"


def append_request_marker(comment: str, marker: str) -> str:
    text = str(comment or "").strip()
    if REQUEST_MARKER.search(text):
        return text
    return f"{text} {marker}".strip()


def visible_comment(comment: str) -> str:
    return REQUEST_MARKER.sub("", str(comment or "")).strip()


def order_request_key(order: dict[str, Any]) -> str:
    """Tests sent together stay one order. A later order stays on its own."""
    match = REQUEST_MARKER.search(str(order.get("comment") or ""))
    if match:
        return f"request:{match.group(1)}"
    encounter = str(order.get("encounterUuid") or "").strip()
    stamp = str(order.get("ordered") or "").strip()[:16]
    if encounter and len(stamp) >= 16:
        return f"{encounter}:{stamp}"
    if encounter:
        return encounter
    return f"order:{order.get('uuid') or ''}"


def _orders_on_same_request(order: dict[str, Any], cookie: str) -> list[dict[str, Any]]:
    encounter = str(order.get("encounterUuid") or "").strip()
    patient = str(order.get("patientUuid") or "").strip()
    if not encounter or not patient:
        return [order]
    try:
        siblings = list_lab_orders(patient, cookie)
    except Exception:
        return [order]
    key = order_request_key(order)
    matched = [row for row in siblings if order_request_key(row) == key]
    return matched or [order]


def _store_request_results(order: dict[str, Any], cookie: str, results: list[dict[str, Any]]) -> None:
    """Keep each entered result on the test it belongs to, including tests saved together."""
    filled = [
        item
        for item in results
        if isinstance(item, dict)
        and str(item.get("resultLabel") or item.get("resultValue") or item.get("qualifiedResultValue") or "").strip()
    ]
    if not filled:
        return
    for member in _orders_on_same_request(order, cookie):
        name = str(member.get("testName") or "").strip().casefold()
        matched = [
            item
            for item in filled
            if name
            and name
            in {
                str(item.get("testName") or "").strip().casefold(),
                str(item.get("orderedAs") or "").strip().casefold(),
            }
        ]
        if matched:
            _merge_workflow_results(str(member.get("uuid") or ""), matched)


def _saved_results_for_request(order: dict[str, Any], cookie: str) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for member in _orders_on_same_request(order, cookie):
        for item in WORKFLOW_RESULTS.get(str(member.get("uuid") or "")) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("testName") or "").strip().casefold()
            if not name or name in seen:
                continue
            seen.add(name)
            saved.append(item)
    return saved


def _remember_released_request(
    order: dict[str, Any],
    cookie: str,
    released_names: set[str] | None = None,
    validator: str = "",
) -> None:
    """Release the tests that have a result. A test left blank stays on the request."""
    names = {name.casefold() for name in (released_names or set()) if str(name or "").strip()}
    if not names:
        _remember_workflow_validation(str(order.get("uuid") or ""), validator)
        return
    siblings = _orders_on_same_request(order, cookie)
    matched = False
    for row in siblings:
        labels = {str(row.get("testName") or "").strip().casefold()}
        labels.update(name.casefold() for name in _ordered_test_names(row) if name)
        if labels & names:
            _remember_workflow_validation(str(row.get("uuid") or ""), validator)
            matched = True
    if not matched:
        _remember_workflow_validation(str(order.get("uuid") or ""), validator)


def _request_validation_status(order: dict[str, Any], order_uuid: str, cookie: str) -> str:
    """The request is released only after every test on it has been accepted."""
    siblings = [row for row in _orders_on_same_request(order, cookie) if row.get("uuid")]
    if len(siblings) > 1:
        if all(WORKFLOW_VALIDATIONS.get(str(row.get("uuid") or "")) for row in siblings):
            return "validated"
        return "pending"
    return "validated" if WORKFLOW_VALIDATIONS.get(order_uuid) else "pending"


def _released_board_stage(order_uuid: str, state: dict[str, Any]) -> dict[str, Any]:
    """Released results stay on Completed results. Payment does not hold them back."""
    if not order_uuid or not WORKFLOW_VALIDATIONS.get(order_uuid):
        return state
    if state.get("stage") == "completed":
        return state
    return {
        **state,
        "stage": "completed",
        "laboratoryStatus": "Results ready",
        "hasResult": True,
    }


def _merge_workflow_results(order_uuid: str, results: list[dict[str, Any]]) -> None:
    """Keep results already saved, and add only the tests entered this time."""
    merged: dict[str, dict[str, Any]] = {}
    for item in WORKFLOW_RESULTS.get(order_uuid) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("testName") or "").strip().casefold()
        if name:
            merged[name] = item
    for item in results:
        if not isinstance(item, dict):
            continue
        value = str(
            item.get("resultLabel")
            or item.get("qualifiedResultValue")
            or item.get("resultValue")
            or ""
        ).strip()
        name = str(item.get("testName") or "").strip()
        if not value or not name:
            continue
        previous = merged.get(name.casefold())
        if previous and previous.get("validatedBy") and not item.get("validatedBy"):
            item = {**item, "validatedBy": previous["validatedBy"]}
        merged[name.casefold()] = item
    _remember_workflow_results(order_uuid, list(merged.values()))


def _remember_workflow_results(order_uuid: str, results: list[dict[str, Any]]) -> None:
    with IDEMPOTENCY_LOCK:
        WORKFLOW_RESULTS[order_uuid] = results
        try:
            os.makedirs(os.path.dirname(WORKFLOW_RESULTS_PATH), exist_ok=True)
            temporary_path = f"{WORKFLOW_RESULTS_PATH}.tmp"
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(WORKFLOW_RESULTS, handle)
            os.replace(temporary_path, WORKFLOW_RESULTS_PATH)
        except OSError:
            LOGGER.warning("Could not persist laboratory results order=%s", order_uuid)


def execute(
    odoo: OdooReader,
    model: str,
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    return odoo.models.execute_kw(
        ODOO_DB,
        odoo.uid,
        ODOO_PASSWORD,
        model,
        method,
        args,
        kwargs or {},
    )


def execute_allowing_empty(
    odoo: OdooReader,
    model: str,
    method: str,
    args: list[Any],
) -> Any:
    """Some bill actions succeed and then return nothing the finance link can send back."""
    try:
        return execute(odoo, model, method, args)
    except xmlrpc.client.Fault as error:
        if "cannot marshal None" in str(error):
            return None
        raise


def odoo_reader() -> OdooReader:
    try:
        return core.OdooReader()
    except ApiError:
        raise
    except xmlrpc.client.Fault as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error
    except (ConnectionError, TimeoutError, OSError) as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error


def load_openmrs_user(cookie: str) -> dict[str, Any]:
    import accountant as cashier

    return cashier.load_openmrs_user(cookie)


def is_lab_user(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & LAB_ROLES) or LAB_PRIVILEGE in privileges


def is_clinical_user(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & LAB_ROLES) or CLINICAL_PRIVILEGE in privileges


def require_lab_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_lab_user(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires the Laboratory workspace.",
        )
    return user


def require_clinical_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_clinical_user(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires the Clinical workspace.",
        )
    return user


def require_clinical_or_lab_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_lab_user(user) and not is_clinical_user(user):
        raise ApiError(
            403,
            "forbidden",
            "This action is not available in this department.",
        )
    return user


def request_source_of(comment: str = "") -> str:
    text = str(comment or "").strip()
    if text.startswith(EXTERNAL_REFERRAL_MARKER) or text.startswith("External Referral"):
        return SOURCE_EXTERNAL_REFERRAL
    if text.startswith(DIRECT_SOURCE_MARKER) or text.startswith("Lab Direct") or text.startswith(
        "Laboratory Direct"
    ):
        return SOURCE_LABORATORY_DIRECT
    return SOURCE_DOCTOR_ORDER


def request_source_label(source: str) -> str:
    if source == SOURCE_LABORATORY_DIRECT:
        return "Laboratory Direct"
    if source == SOURCE_EXTERNAL_REFERRAL:
        return "External Referral"
    return "Doctor Order"


def _strip_source_markers(comment: str) -> str:
    text = str(comment or "").strip()
    for prefix in (
        EXTERNAL_REFERRAL_MARKER,
        DIRECT_SOURCE_MARKER,
        "External Referral:",
        "External Referral",
        "Laboratory Direct:",
        "Laboratory Direct",
        "Lab Direct:",
        "Lab Direct",
    ):
        if text.startswith(prefix):
            return text[len(prefix) :].strip(" :-")
    return text


def direct_order_comment(note: str, *, source: str = SOURCE_LABORATORY_DIRECT) -> str:
    cleaned = " ".join(str(note or "").split()).strip()
    marker = (
        EXTERNAL_REFERRAL_MARKER
        if source == SOURCE_EXTERNAL_REFERRAL
        else DIRECT_SOURCE_MARKER
    )
    if cleaned:
        return f"{marker} {cleaned}"
    return marker


def _patient_type_bits(
    *,
    mrn: str,
    patient_uuid: str,
    external_uuids: set[str] | None = None,
) -> tuple[str, str, bool]:
    import laboratory_external as external

    if external.is_external_openmrs_identifier(mrn) or (
        patient_uuid and external_uuids is not None and patient_uuid in external_uuids
    ):
        return "external", "External Patient", True
    if patient_uuid and external_uuids is None:
        try:
            if external.external_for_openmrs_uuid(patient_uuid):
                return "external", "External Patient", True
        except Exception:
            pass
    return "registered", "Registered Patient", False


def now_openmrs() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _direct_encounter_time(visit: dict[str, Any], existing: dict[str, str] | None) -> str:
    """Keep a laboratory addition inside the doctor's visit, even after the visit has ended."""
    original = str((existing or {}).get("encounterDatetime") or "").strip()
    if original:
        return original
    started = str(visit.get("startDatetime") or "").strip()
    if visit.get("stopDatetime") and started:
        return started
    return now_openmrs()


def _ngn_currency_id(odoo: OdooReader) -> int | None:
    try:
        rows = execute(
            odoo,
            "res.currency",
            "search_read",
            [[("name", "=", "NGN")]],
            {"fields": ["id", "active"], "limit": 1, "context": {"active_test": False}},
        )
    except xmlrpc.client.Fault:
        rows = odoo.search_read("res.currency", [("name", "=", "NGN")], ["id", "active"], limit=1)
    if not rows:
        return None
    return int(rows[0]["id"])


def lab_currency(odoo: OdooReader) -> dict[str, Any]:
    currency_id = _ngn_currency_id(odoo)
    if currency_id:
        loaded = load_currency(odoo, currency_id)
        return {
            **loaded,
            "code": "NGN",
            "symbol": "₦",
            "position": "before",
        }
    return dict(NGN_CURRENCY)


def _provider_uuid(user_uuid: str, cookie: str) -> str:
    rows: list[Any] = []
    try:
        payload = _openmrs_json(
            f"/openmrs/ws/rest/v1/provider?user={quote(user_uuid)}&v=custom:(uuid,retired)",
            cookie,
        )
        raw = payload.get("results") if isinstance(payload, dict) else payload
        rows = list(raw or [])
    except ApiError:
        rows = []
    for row in rows:
        if isinstance(row, dict) and row.get("uuid") and not row.get("retired"):
            return str(row["uuid"])
    # Lab accounts are often not providers; resolve via identity service.
    try:
        service = core.openmrs_service_get(
            f"/openmrs/ws/rest/v1/provider?user={quote(user_uuid)}&v=custom:(uuid,retired,display)"
        )
        service_rows = service.get("results") if isinstance(service, dict) else service
        for row in service_rows or []:
            if isinstance(row, dict) and row.get("uuid") and not row.get("retired"):
                return str(row["uuid"])
        fallback = core.openmrs_service_get(
            "/openmrs/ws/rest/v1/provider?v=custom:(uuid,display,retired)&limit=50"
        )
        fallback_rows = fallback.get("results") if isinstance(fallback, dict) else fallback
        for preferred in ("lab.abikan", "LABSYSTEM", "LABMANAGER", "UNKNOWN"):
            for row in fallback_rows or []:
                if not isinstance(row, dict) or row.get("retired") or not row.get("uuid"):
                    continue
                if preferred.lower() in str(row.get("display") or "").lower():
                    return str(row["uuid"])
    except ApiError:
        pass
    raise ApiError(409, "provider_missing", "This account is not set up as a clinician.")


def _clinical_write_post(path: str, cookie: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Prefer the signed-in cookie; fall back to the identity service for lab writes."""
    try:
        return _openmrs_post(path, cookie, payload)
    except ApiError as error:
        if error.status not in {403, 502}:
            raise
        try:
            return core.openmrs_service_post(path, payload)
        except ApiError as service_error:
            raise ApiError(
                502,
                "openmrs_error",
                "The laboratory order could not be saved. Try again in a moment.",
            ) from service_error


def _openmrs_json_readable(path: str, cookie: str) -> dict[str, Any] | list[Any] | None:
    """Read a laboratory record. If this account cannot, use the identity service."""
    try:
        return _openmrs_json(path, cookie)
    except ApiError as error:
        if error.code != "openmrs_error":
            raise
        try:
            return core.openmrs_service_get(path)
        except ApiError:
            raise error


def _openmrs_json(path: str, cookie: str) -> dict[str, Any] | list[Any] | None:
    request = Request(
        f"{core.OPENMRS_URL}{path}",
        headers={"Accept": "application/json", "Cookie": cookie},
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 404:
            return None
        raise ApiError(502, "openmrs_error", "The laboratory record could not be loaded.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The laboratory record could not be loaded.") from error


def _openmrs_post(path: str, cookie: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        f"{core.OPENMRS_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=40) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        raise ApiError(502, "openmrs_error", "The laboratory order could not be saved.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The laboratory order could not be saved.") from error


def _openelis_json(path: str) -> dict[str, Any]:
    """Read supported OpenELIS JSON with a server-side integration session."""
    if not OPENELIS_USER or not OPENELIS_PASSWORD:
        raise ApiError(
            503,
            "openelis_configuration",
            "Laboratory processing status is temporarily unavailable.",
        )
    request = Request(
        f"{OPENELIS_URL}{path}",
        data=urlencode(
            {
                "loginName": OPENELIS_USER,
                "password": OPENELIS_PASSWORD,
            }
        ).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                raise ValueError("OpenELIS returned a non-object response")
            return payload
    except HTTPError as error:
        raise ApiError(
            502,
            "openelis_error",
            "Laboratory processing status is temporarily unavailable.",
        ) from error
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
        raise ApiError(
            502,
            "openelis_error",
            "Laboratory processing status is temporarily unavailable.",
        ) from error


def charge_key(order_uuid: str) -> str:
    return f"{EXTERNAL_PREFIX}{order_uuid}"


def _named(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display") or value.get("name") or "")
    if value is None:
        return ""
    return str(value)


def _uuid_of(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("uuid") or "")
    return ""


def load_lab_order(order_uuid: str, patient_uuid: str | None, cookie: str) -> dict[str, Any]:
    order = _openmrs_json_readable(
        f"/openmrs/ws/rest/v1/order/{order_uuid}"
        "?v=custom:(uuid,orderNumber,dateActivated,dateCreated,urgency,commentToFulfiller,"
        "accessionNumber,voided,action,patient:(uuid,display),encounter:(uuid,visit:(uuid)),"
        "concept:(uuid,display),orderType:(uuid,display),orderer:(display))",
        cookie,
    )
    if not isinstance(order, dict) or not order.get("uuid") or order.get("voided"):
        raise ApiError(404, "order_not_found", "This laboratory order was not found.")
    order_type = order.get("orderType") if isinstance(order.get("orderType"), dict) else {}
    type_uuid = order_type.get("uuid") or ""
    type_name = order_type.get("display") or order_type.get("name") or ""
    if type_uuid != LAB_ORDER_TYPE_UUID and type_name != LAB_ORDER_TYPE_NAME:
        raise ApiError(422, "not_lab_order", "That record is not a laboratory order.")
    patient = order.get("patient") if isinstance(order.get("patient"), dict) else {}
    found_patient = patient.get("uuid") or ""
    if patient_uuid and found_patient != patient_uuid:
        raise ApiError(409, "wrong_patient", "This laboratory order does not belong to this patient.")
    encounter = order.get("encounter") if isinstance(order.get("encounter"), dict) else {}
    visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
    concept = order.get("concept") if isinstance(order.get("concept"), dict) else {}
    concept_uuid = concept.get("uuid") or ""
    if not concept_uuid:
        raise ApiError(
            409,
            "missing_test",
            "This laboratory order has no test identifier, so a fee cannot be created.",
        )
    comment = order.get("commentToFulfiller") or ""
    test_name = concept.get("display") or "Laboratory test"
    if str(comment).startswith(UNLISTED_LAB_MARKER):
        test_name = str(comment)[len(UNLISTED_LAB_MARKER) :].strip() or test_name
    return {
        "uuid": order.get("uuid"),
        "orderNumber": order.get("orderNumber") or "",
        "testName": test_name,
        "conceptUuid": concept_uuid,
        "patientUuid": found_patient,
        "visitUuid": visit.get("uuid") or "",
        "encounterUuid": encounter.get("uuid") or "",
        "urgency": "STAT" if order.get("urgency") == "STAT" else (order.get("urgency") or "Routine"),
        "accession": order.get("accessionNumber") or "",
        "ordered": order.get("dateActivated") or order.get("dateCreated") or "",
        "provider": _named(order.get("orderer")) or "—",
        "comment": comment,
        "patientName": (patient.get("display") or "").split(" - ", 1)[-1].strip() or "Unknown patient",
        "mrn": (patient.get("display") or "").split(" - ", 1)[0].strip() if " - " in (patient.get("display") or "") else "",
        **_patient_facts(str(found_patient or "")),
    }


def list_lab_orders(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    payload = _openmrs_json_readable(
        f"/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={patient_uuid}"
        f"&orderTypeUuid={LAB_ORDER_TYPE_UUID}",
        cookie,
    )
    rows = payload if isinstance(payload, list) else (payload.get("results") if isinstance(payload, dict) else [])
    if not isinstance(rows, list):
        return []
    seen: set[str] = set()
    uuids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_uuid = str(row.get("uuid") or row.get("orderUuid") or "").strip()
        if not order_uuid or order_uuid in seen:
            continue
        seen.add(order_uuid)
        uuids.append(order_uuid)
    if not uuids:
        return []

    def _one(order_uuid: str) -> dict[str, Any] | None:
        try:
            return load_lab_order(order_uuid, patient_uuid, cookie)
        except ApiError:
            return None

    with ThreadPoolExecutor(max_workers=min(8, len(uuids))) as pool:
        return [row for row in pool.map(_one, uuids) if row]


def ensure_lab_masters(odoo: OdooReader) -> dict[str, Any]:
    """Idempotent TEST shop/category/product. Does not change catalogue lab products."""
    services = odoo.search_read(
        "product.category",
        [("complete_name", "=", "All / Services")],
        ["id"],
        limit=1,
    )
    parent_id = int(services[0]["id"]) if services else None
    categories = odoo.search_read(
        "product.category",
        [("name", "=", CATEGORY_NAME), ("parent_id", "=", parent_id)] if parent_id else [("name", "=", CATEGORY_NAME)],
        ["id", "complete_name"],
        limit=1,
    )
    if categories:
        category_id = int(categories[0]["id"])
    else:
        category_id = int(
            execute(
                odoo,
                "product.category",
                "create",
                [{"name": CATEGORY_NAME, "parent_id": parent_id}],
            )
        )
    products = odoo.search_read(
        "product.product",
        [("name", "=", TEST_PRODUCT_NAME), ("categ_id", "=", category_id)],
        ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "uuid", "default_code"],
        limit=1,
    )
    if products:
        product = products[0]
        product_id = int(product["id"])
        writes: dict[str, Any] = {}
        if product.get("taxes_id"):
            writes["taxes_id"] = [(6, 0, [])]
        if (product.get("default_code") or "") != TEST_CONCEPT_UUID:
            writes["default_code"] = TEST_CONCEPT_UUID
        if writes:
            execute(odoo, "product.product", "write", [[product_id], writes])
            product["taxes_id"] = []
            product["default_code"] = TEST_CONCEPT_UUID
    else:
        product_id = int(
            execute(
                odoo,
                "product.product",
                "create",
                [
                    {
                        "name": TEST_PRODUCT_NAME,
                        "type": "service",
                        "categ_id": category_id,
                        "list_price": TEST_LIST_PRICE,
                        "uom_id": 1,
                        "uom_po_id": 1,
                        "sale_ok": True,
                        "purchase_ok": False,
                        "invoice_policy": "order",
                        "default_code": TEST_CONCEPT_UUID,
                        "taxes_id": [(6, 0, [])],
                        "supplier_taxes_id": [(6, 0, [])],
                    }
                ],
            )
        )
        execute(odoo, "product.product", "write", [[product_id], {"taxes_id": [(6, 0, [])]}])
        found = odoo.read(
            "product.product",
            [product_id],
            ["name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "uuid", "default_code"],
        )
        product = found[0]
    shops = odoo.search_read(
        "sale.shop",
        [("name", "=", SHOP_NAME)],
        ["id", "name", "warehouse_id", "pricelist_id", "payment_default_id"],
        limit=1,
    )
    if shops:
        shop = shops[0]
    else:
        source_rows = odoo.search_read(
            "sale.shop",
            [("name", "=", "Consultation Desk")],
            ["warehouse_id", "pricelist_id", "payment_default_id", "company_id"],
            limit=1,
        )
        source = source_rows[0] if source_rows else {}
        shop_id = int(
            execute(
                odoo,
                "sale.shop",
                "create",
                [
                    {
                        "name": SHOP_NAME,
                        "warehouse_id": many2one_id(source.get("warehouse_id")) or 1,
                        "pricelist_id": many2one_id(source.get("pricelist_id")) or 1,
                        "payment_default_id": many2one_id(source.get("payment_default_id")) or 1,
                        "company_id": many2one_id(source.get("company_id")) or 1,
                    }
                ],
            )
        )
        shop = odoo.read(
            "sale.shop",
            [shop_id],
            ["name", "warehouse_id", "pricelist_id", "payment_default_id"],
        )[0]
    return {"testProduct": product, "shop": shop, "category_id": category_id}


def _is_test_product(product: dict[str, Any]) -> bool:
    name = str(product.get("name") or "")
    return " — TEST" in name


def find_lab_pricing_products(odoo: OdooReader, concept_uuids: list[str]) -> dict[str, dict[str, Any]]:
    """Hospital service products for catalogue pricing. Does not create tests."""
    needles = [str(item).strip() for item in concept_uuids if str(item or "").strip()]
    if not needles:
        return {}
    fields = ["id", "name", "list_price", "type", "uuid", "default_code"]
    found = execute(
        odoo,
        "product.product",
        "search_read",
        [[("uuid", "in", needles), ("type", "=", "service")]],
        {"fields": fields, "limit": max(len(needles) * 3, 20)},
    )
    mapped: dict[str, dict[str, Any]] = {}
    for row in found or []:
        if _is_test_product(row):
            continue
        key = str(row.get("uuid") or "")
        if key and key not in mapped:
            mapped[key] = row
    return mapped


def find_lab_pricing_product(odoo: OdooReader, concept_uuid: str) -> dict[str, Any]:
    """Hospital service product for catalogue pricing. Does not create tests or OpenELIS rows."""
    needle = (concept_uuid or "").strip()
    if not needle:
        raise ApiError(404, "not_found", "That laboratory test was not found in the hospital list.")
    mapped = find_lab_pricing_products(odoo, [needle])
    if needle in mapped:
        return mapped[needle]
    raise ApiError(
        409,
        "missing_mapping",
        "This test does not have a hospital fee yet.",
    )


def find_lab_product(odoo: OdooReader, concept_uuid: str) -> dict[str, Any]:
    """Hospital product (uuid = concept, real price) wins over isolated TEST products."""
    fields = ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "uuid", "default_code", "categ_id"]
    found = odoo.search_read(
        "product.product",
        [("uuid", "=", concept_uuid), ("type", "=", "service")],
        fields,
        limit=5,
    )
    hospital = [
        row
        for row in found
        if not _is_test_product(row) and as_float(row.get("list_price")) > PLACEHOLDER_PRICE
    ]
    if hospital:
        return hospital[0]
    test_rows = odoo.search_read(
        "product.product",
        [("default_code", "=", concept_uuid), ("name", "ilike", " — TEST")],
        fields,
        limit=1,
    )
    if test_rows and as_float(test_rows[0].get("list_price")) > PLACEHOLDER_PRICE:
        return test_rows[0]
    if not found and not test_rows:
        raise ApiError(
            409,
            "missing_mapping",
            "This test does not have an approved laboratory fee yet.",
        )
    raise ApiError(
        409,
        "missing_price",
        "This test does not have an approved laboratory fee yet.",
    )


def related_invoice(odoo: OdooReader, sale: dict[str, Any]) -> dict[str, Any] | None:
    invoice_ids = [int(item) for item in (sale.get("invoice_ids") or [])]
    invoices = (
        odoo.read(
            "account.move",
            invoice_ids,
            ["name", "state", "payment_state", "amount_residual", "amount_total", "amount_tax", "move_type", "currency_id"],
        )
        if invoice_ids
        else []
    )
    posted = [
        row
        for row in invoices
        if row.get("move_type") == "out_invoice" and row.get("state") == "posted"
    ]
    if posted:
        return posted[0]
    origin = sale.get("name") or ""
    if not origin:
        return None
    found = odoo.search_read(
        "account.move",
        [("move_type", "=", "out_invoice"), ("invoice_origin", "=", origin), ("state", "=", "posted")],
        ["name", "state", "payment_state", "amount_residual", "amount_total", "amount_tax", "move_type", "currency_id"],
        limit=1,
    )
    return found[0] if found else None


def find_existing_sale(odoo: OdooReader, order_uuid: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    key = charge_key(order_uuid)
    lines = odoo.search_read(
        "sale.order.line",
        [("external_order_id", "=", key)],
        ["order_id", "product_id", "product_uom_qty", "price_unit", "external_order_id", "external_id"],
        limit=5,
    )
    if not lines:
        return None
    sale_id = many2one_id(lines[0].get("order_id"))
    if not sale_id:
        return None
    sales = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "shop_id", "origin", "amount_total", "amount_tax", "currency_id"],
    )
    if not sales:
        return None
    return lines[0], sales[0]


def invoice_paid(invoice: dict[str, Any] | None) -> bool:
    if not invoice:
        return False
    residual = as_float(invoice.get("amount_residual"))
    return invoice.get("payment_state") in {"paid", "in_payment"} and residual <= 0.009


def invoice_payment_label(invoice: dict[str, Any] | None) -> str:
    if not invoice:
        return "UNPAID"
    if invoice_paid(invoice):
        return "PAID"
    if invoice.get("payment_state") == "partial":
        return "PARTIALLY PAID"
    residual = as_float(invoice.get("amount_residual"))
    total = as_float(invoice.get("amount_total"))
    if residual > 0.009 and total > 0 and residual < total - 0.009:
        return "PARTIALLY PAID"
    return "UNPAID"


def serialize_order_charge(
    order: dict[str, Any],
    product: dict[str, Any] | None,
    sale: dict[str, Any] | None,
    invoice: dict[str, Any] | None,
    currency: dict[str, Any],
) -> dict[str, Any]:
    has_charge = bool(sale or invoice)
    status = invoice_payment_label(invoice) if has_charge else "UNPAID"
    amount = as_float((product or {}).get("list_price"))
    if not amount and invoice:
        amount = as_float(invoice.get("amount_total"))
    return {
        "orderUuid": order["uuid"],
        "orderNumber": order.get("orderNumber") or "",
        "testName": order.get("testName") or "Laboratory test",
        "visitUuid": order.get("visitUuid") or "",
        "encounterUuid": order.get("encounterUuid") or "",
        "feeName": (product or {}).get("name") or order.get("testName"),
        "feeAmount": format_money(amount, currency),
        "paymentStatus": status if has_charge else "UNPAID",
        "hasCharge": has_charge,
        "requestKey": order_request_key(order),
    }


def _order_financials(
    odoo: OdooReader,
    order: dict[str, Any],
    currency: dict[str, Any],
) -> dict[str, Any]:
    existing = find_existing_sale(odoo, order["uuid"])
    sale = existing[1] if existing else None
    invoice = related_invoice(odoo, sale) if sale else None
    product = None
    try:
        product = find_lab_product(odoo, order["conceptUuid"])
    except ApiError:
        if existing:
            product_id = many2one_id(existing[0].get("product_id"))
            if product_id:
                rows = odoo.read("product.product", [product_id], ["name", "list_price"])
                product = rows[0] if rows else None
        elif not existing:
            product = None
    if existing:
        line = existing[0]
        line_price = as_float(line.get("price_unit"))
        if product is None:
            product = {"name": order.get("testName"), "list_price": line_price}
        else:
            product = {**product, "list_price": line_price or as_float(product.get("list_price"))}
    row = serialize_order_charge(order, product, sale, invoice, currency)
    if existing:
        row["hasCharge"] = True
        row["paymentStatus"] = invoice_payment_label(invoice)
        if invoice:
            row["outstanding"] = format_money(as_float(invoice.get("amount_residual")), currency)
            row["tax"] = format_money(as_float(invoice.get("amount_tax")), currency)
    return row


def _order_financials_many(
    odoo: OdooReader,
    orders: list[dict[str, Any]],
    currency: dict[str, Any],
) -> list[dict[str, Any]]:
    if not orders:
        return []
    keys = [charge_key(str(order["uuid"])) for order in orders]
    lines = execute(
        odoo,
        "sale.order.line",
        "search_read",
        [[("external_order_id", "in", keys)]],
        {
            "fields": ["order_id", "product_id", "product_uom_qty", "price_unit", "external_order_id", "external_id"],
            "limit": max(len(keys) * 2, 20),
        },
    )
    line_by_key = {str(row.get("external_order_id") or ""): row for row in lines or []}
    sale_ids = []
    seen_sales: set[int] = set()
    for line in line_by_key.values():
        sale_id = many2one_id(line.get("order_id"))
        if sale_id and sale_id not in seen_sales:
            seen_sales.add(sale_id)
            sale_ids.append(sale_id)
    sales = {
        int(row["id"]): row
        for row in (
            odoo.read(
                "sale.order",
                sale_ids,
                ["name", "state", "partner_id", "invoice_ids", "shop_id", "origin", "amount_total", "amount_tax", "currency_id"],
            )
            if sale_ids
            else []
        )
    }
    invoice_ids: list[int] = []
    for sale in sales.values():
        invoice_ids.extend(int(item) for item in (sale.get("invoice_ids") or []) if item)
    invoices = {
        int(row["id"]): row
        for row in (
            odoo.read(
                "account.move",
                invoice_ids,
                ["name", "state", "payment_state", "amount_residual", "amount_total", "amount_tax", "move_type", "currency_id"],
            )
            if invoice_ids
            else []
        )
    }
    concepts = [str(order.get("conceptUuid") or "") for order in orders if order.get("conceptUuid")]
    product_fields = ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "uuid", "default_code", "categ_id"]
    hospital_rows = execute(
        odoo,
        "product.product",
        "search_read",
        [[("uuid", "in", concepts), ("type", "=", "service")]] if concepts else [[("id", "=", 0)]],
        {"fields": product_fields, "limit": max(len(concepts) * 3, 20)},
    ) if concepts else []
    hospital_by_uuid: dict[str, dict[str, Any]] = {}
    for row in hospital_rows or []:
        if _is_test_product(row):
            continue
        key = str(row.get("uuid") or "")
        if key and as_float(row.get("list_price")) > PLACEHOLDER_PRICE and key not in hospital_by_uuid:
            hospital_by_uuid[key] = row
    missing = [item for item in concepts if item not in hospital_by_uuid]
    test_by_code: dict[str, dict[str, Any]] = {}
    if missing:
        test_rows = execute(
            odoo,
            "product.product",
            "search_read",
            [[("default_code", "in", missing), ("name", "ilike", " — TEST")]],
            {"fields": product_fields, "limit": max(len(missing), 20)},
        )
        for row in test_rows or []:
            key = str(row.get("default_code") or "")
            if key and as_float(row.get("list_price")) > PLACEHOLDER_PRICE and key not in test_by_code:
                test_by_code[key] = row
    results = []
    for order in orders:
        key = charge_key(str(order["uuid"]))
        line = line_by_key.get(key)
        sale = sales.get(many2one_id((line or {}).get("order_id")) or 0) if line else None
        invoice = None
        if sale:
            posted = [
                invoices[int(item)]
                for item in (sale.get("invoice_ids") or [])
                if int(item) in invoices
                and invoices[int(item)].get("move_type") == "out_invoice"
                and invoices[int(item)].get("state") == "posted"
            ]
            invoice = posted[0] if posted else None
        concept = str(order.get("conceptUuid") or "")
        product = hospital_by_uuid.get(concept) or test_by_code.get(concept)
        if line:
            line_price = as_float(line.get("price_unit"))
            if product is None:
                product = {"name": order.get("testName"), "list_price": line_price}
            else:
                product = {**product, "list_price": line_price or as_float(product.get("list_price"))}
        row = serialize_order_charge(order, product, sale, invoice, currency)
        if line:
            row["hasCharge"] = True
            row["paymentStatus"] = invoice_payment_label(invoice)
            if invoice:
                row["outstanding"] = format_money(as_float(invoice.get("amount_residual")), currency)
                row["tax"] = format_money(as_float(invoice.get("amount_tax")), currency)
        results.append(row)
    return results


def _charge_payload(
    cookie: str,
    patient_uuid: str,
    *,
    user: dict[str, Any] | None = None,
    odoo: OdooReader | None = None,
) -> dict[str, Any]:
    del user
    patient = load_openmrs_patient(patient_uuid, cookie)
    reader = odoo or odoo_reader()
    ensure_lab_masters(reader)
    currency = lab_currency(reader)
    partner = find_partner(reader, patient)
    orders = list_lab_orders(patient_uuid, cookie)
    items = _order_financials_many(reader, orders, currency)
    billed = [item for item in items if item.get("hasCharge")]
    unbilled = [item for item in items if not item.get("hasCharge")]
    mappable = 0
    mapping_error = None
    charged = {str(item.get("orderUuid") or "") for item in items if item.get("hasCharge")}
    for order in orders:
        if order["uuid"] in charged:
            continue
        try:
            find_lab_product(reader, order["conceptUuid"])
            mappable += 1
        except ApiError as error:
            if mapping_error is None:
                mapping_error = error.message
    billed_statuses = {str(item.get("paymentStatus") or "") for item in billed}
    unpaid_any = any(item.get("paymentStatus") == "UNPAID" and item.get("hasCharge") for item in items)
    if billed and not unbilled and billed_statuses == {"PAID"}:
        payment_status = "PAID"
    elif "PARTIALLY PAID" in billed_statuses or (
        "PAID" in billed_statuses and (unbilled or unpaid_any)
    ):
        payment_status = "PARTIALLY PAID"
    else:
        payment_status = "UNPAID"
    can_create = bool(partner) and mappable > 0
    reason = None
    if not partner:
        reason = "This patient has no financial account yet. Try again in a moment."
        can_create = False
    elif not orders:
        reason = "No laboratory orders on this chart yet."
    elif unbilled and mappable == 0:
        reason = mapping_error or "This test does not have an approved laboratory fee yet."
    elif unbilled:
        reason = None
    elif unpaid_any:
        reason = "Please proceed to the cashier for payment."
    total = sum(as_float(item["feeAmount"]["amount"]) for item in items) if items else 0.0
    outstanding = 0.0
    for item in billed:
        if item.get("paymentStatus") != "PAID":
            outstanding += as_float((item.get("outstanding") or item.get("feeAmount") or {}).get("amount"))
    return {
        "status": "ok",
        "patient": patient,
        "tests": items,
        "feeAmount": format_money(total, currency),
        "paymentStatus": payment_status,
        "hasCharge": bool(billed),
        "canCreateCharge": can_create,
        "blockReason": reason,
        "partnerFound": bool(partner),
        "outstanding": format_money(outstanding, currency),
        "message": None,
    }


def build_patient_chart(patient_uuid: str, cookie: str) -> dict[str, Any]:
    """Orders, samples, and released results for the laboratory patient page."""
    require_lab_user(cookie)
    orders = list_lab_orders(patient_uuid, cookie)
    released = build_released_lab_results(patient_uuid, cookie).get("results") or []
    chart_orders = []
    for order in orders:
        accession = WORKFLOW_ACCESSIONS.get(str(order.get("uuid") or "")) or str(order.get("accession") or "")
        chart_orders.append(
            {
                "uuid": order.get("uuid") or "",
                "orderNumber": order.get("orderNumber") or "",
                "testName": order.get("testName") or "Laboratory test",
                "patientUuid": order.get("patientUuid") or patient_uuid,
                "visitUuid": order.get("visitUuid") or "",
                "ordered": order.get("ordered") or "",
                "urgency": order.get("urgency") or "Routine",
                "comment": order.get("comment") or "",
                "provider": order.get("provider") or "—",
                "accession": accession,
                "encounterUuid": order.get("encounterUuid") or "",
            }
        )
    return {"status": "ok", "orders": chart_orders, "results": released}


def build_laboratory(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_clinical_or_lab_user(cookie)
    return _charge_payload(cookie, patient_uuid)


def _prefer_typed(typed: Any, external: Any) -> str:
    """Keep the words the laboratory typed, including notes and line breaks."""
    saved = str(typed or "")
    other = str(external or "")
    if saved.strip():
        return saved
    return other


def _chart_result_text(saved: dict[str, Any], field: dict[str, Any]) -> str:
    """Use Positive or Negative on the chart, not the code stored behind that answer."""
    value = str(
        saved.get("resultLabel")
        or saved.get("qualifiedResultValue")
        or saved.get("resultValue")
        or ""
    ).strip()
    coded = str(saved.get("resultValue") or field.get("resultValue") or value).strip()
    for option in list(saved.get("options") or []) + list(field.get("resultOptions") or []):
        if not isinstance(option, dict):
            continue
        if str(option.get("value") or "").strip() != coded:
            continue
        label = str(option.get("label") or "").strip()
        if label:
            return label
    return value


def _chart_result_is_choice(saved: dict[str, Any], field: dict[str, Any], value: str) -> bool:
    kind = str(saved.get("resultType") or field.get("resultType") or "").strip().upper()
    if kind in {"D", "A", "R"}:
        return True
    options = list(saved.get("options") or []) + list(field.get("resultOptions") or [])
    return any(isinstance(option, dict) and str(option.get("label") or "").strip() == value for option in options)


def _saved_rows_from_fields(fields: list[dict[str, Any]], order_name: str) -> list[dict[str, Any]]:
    """A released test can live on the sample before it is copied onto the chart."""
    if not fields:
        return []
    import openelis_sql

    names = openelis_sql.test_names_by_id([str(field.get("testId") or "") for field in fields])
    rows: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        value = str(field.get("resultValue") or field.get("qualifiedResultValue") or "").strip()
        if not value or value == "0":
            continue
        test_id = str(field.get("testId") or "")
        rows.append(
            {
                "testId": test_id,
                "testName": names.get(test_id) or order_name,
                "resultValue": value,
                "resultType": str(field.get("resultType") or ""),
                "options": field.get("resultOptions") if isinstance(field.get("resultOptions"), list) else [],
            }
        )
    return rows


def build_released_lab_results(patient_uuid: str, cookie: str) -> dict[str, Any]:
    """Expose validated workflow results to the clinical chart."""
    require_clinical_or_lab_user(cookie)
    orders_payload = _openmrs_json_readable(
        f"/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={quote(patient_uuid)}"
        f"&orderTypeUuid={quote(LAB_ORDER_TYPE_UUID)}",
        cookie,
    )
    raw_orders = orders_payload if isinstance(orders_payload, list) else (
        orders_payload.get("results") if isinstance(orders_payload, dict) else []
    )
    released: list[dict[str, Any]] = []
    for raw_order in raw_orders or []:
        if not isinstance(raw_order, dict):
            continue
        order_uuid = str(raw_order.get("uuid") or raw_order.get("orderUuid") or "").strip()
        if not order_uuid or not WORKFLOW_VALIDATIONS.get(order_uuid):
            continue
        order_name = str(
            raw_order.get("conceptName")
            or raw_order.get("testName")
            or _named(raw_order.get("concept"))
            or "Laboratory result"
        )
        saved_rows = [row for row in (WORKFLOW_RESULTS.get(order_uuid) or []) if isinstance(row, dict)]
        external_fields: list[dict[str, Any]] = []
        accession = WORKFLOW_ACCESSIONS.get(order_uuid) or str(raw_order.get("accessionNumber") or "")
        if accession:
            try:
                from openelis_adapter import OpenElisAdapter

                external_fields = OpenElisAdapter().result_fields(accession)
            except ApiError:
                external_fields = []
        if not any(
            str(row.get("resultLabel") or row.get("resultValue") or row.get("qualifiedResultValue") or "").strip()
            for row in saved_rows
        ):
            saved_rows = _saved_rows_from_fields(external_fields, order_name)
        fields_by_id = {
            str(field.get("testId") or ""): field
            for field in external_fields
            if isinstance(field, dict) and str(field.get("testId") or "")
        }
        for index, saved in enumerate(saved_rows):
            if not isinstance(saved, dict):
                continue
            field = fields_by_id.get(str(saved.get("testId") or ""))
            if field is None and index < len(external_fields):
                field = external_fields[index]
            value = _chart_result_text(saved, field if isinstance(field, dict) else {})
            if not value:
                continue
            choice = _chart_result_is_choice(saved, field if isinstance(field, dict) else {}, value)
            released.append(
                {
                    "orderUuid": order_uuid,
                    "accessionUuid": accession,
                    "testName": str(saved.get("testName") or order_name),
                    "panelName": "",
                    "result": value,
                    "testUnitOfMeasurement": "" if choice else str(saved.get("unit") or ""),
                    "minNormal": None if choice else saved.get("referenceLow"),
                    "maxNormal": None if choice else saved.get("referenceHigh"),
                    "abnormal": None if choice else bool(saved.get("flag")),
                    "notes": str(saved.get("note") or ""),
                    "provider": str(raw_order.get("provider") or "Laboratory"),
                    "resultDateTime": saved.get("resultDateTime") or datetime.now(timezone.utc).isoformat(),
                    "accessionDateTime": raw_order.get("dateActivated") or raw_order.get("dateCreated"),
                }
            )
    return {"results": released}


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_charge_failed",
            "The laboratory fee could not be created. Refresh and try again.",
        ) from error


def _ensure_lab_walkin_partner(
    odoo: OdooReader,
    *,
    name: str,
    phone: str,
    token: str,
) -> dict[str, Any]:
    clean_name = " ".join(str(name or "").split()).strip()
    if len(clean_name) < 2:
        raise ApiError(422, "buyer_required", "Enter the person's full name.")
    ref = f"{WALKIN_REF_PREFIX}{token}"
    existing = odoo.search_read(
        "res.partner",
        [("ref", "=", ref)],
        ["id", "name", "ref", "uuid", "phone"],
        limit=1,
    )
    if existing:
        row = existing[0]
        if not str(row.get("uuid") or "").strip():
            link = f"laboratory:{token}"
            execute(odoo, "res.partner", "write", [[int(row["id"])], {"uuid": link}])
            row["uuid"] = link
        return row
    values: dict[str, Any] = {
        "name": clean_name,
        "ref": ref,
        "uuid": f"laboratory:{token}",
        "customer_rank": 1,
        "company_type": "person",
    }
    if phone.strip():
        values["phone"] = phone.strip()
    partner_id = int(execute(odoo, "res.partner", "create", [values]))
    rows = odoo.read("res.partner", [partner_id], ["id", "name", "ref", "uuid", "phone"])
    return rows[0]


def _partner_for_laboratory_bill(
    odoo: OdooReader,
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
) -> dict[str, Any]:
    """The billing record for this laboratory order, including an external patient."""
    walkin_token = str(body.get("walkinPartnerToken") or "").strip()
    if walkin_token:
        partner = _ensure_lab_walkin_partner(
            odoo,
            name=str(body.get("buyerName") or body.get("patientName") or "").strip(),
            phone=str(body.get("buyerPhone") or body.get("phone") or "").strip(),
            token=walkin_token,
        )
        return _remember_chart_on_partner(odoo, partner, patient_uuid)
    patient = load_openmrs_patient(patient_uuid, cookie)
    partner = find_partner(odoo, patient)
    if partner:
        return partner
    chart_number = core.chart_number_from_ref(str(patient.get("mrn") or "")).upper()
    if chart_number.startswith("EXTLAB"):
        partner = _ensure_lab_walkin_partner(
            odoo,
            name=str(patient.get("name") or "").strip(),
            phone="",
            token=chart_number,
        )
        return _remember_chart_on_partner(odoo, partner, patient_uuid)
    raise ApiError(
        409,
        "account_not_found",
        "This patient has no financial account yet. Try again in a moment.",
    )


def _remember_chart_on_partner(
    odoo: OdooReader,
    partner: dict[str, Any],
    patient_uuid: str,
) -> dict[str, Any]:
    stored = str(partner.get("uuid") or "").strip()
    chart = str(patient_uuid or "").strip()
    synthetic = stored.startswith(("cashier:", "pharmacy:", "laboratory:", "radiology:"))
    if (stored and not synthetic) or not chart or chart == stored:
        return partner
    existing = odoo.search_read("res.partner", [("uuid", "=", patient_uuid)], ["id"], limit=1)
    if existing:
        return partner
    execute(odoo, "res.partner", "write", [[int(partner["id"])], {"uuid": patient_uuid}])
    partner["uuid"] = patient_uuid
    return partner


def create_laboratory_charge(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_clinical_or_lab_user(cookie)
    request_id = str(body.get("requestId") or "").strip()
    selected = str(body.get("orderUuid") or "").strip()
    selected_many = body.get("orderUuids")
    wanted: set[str] = set()
    if selected:
        wanted.add(selected)
    if isinstance(selected_many, list):
        wanted.update(str(item).strip() for item in selected_many if str(item).strip())
    orders = list_lab_orders(patient_uuid, cookie)
    if wanted:
        orders = [row for row in orders if row["uuid"] in wanted]
        if not orders:
            raise ApiError(404, "order_not_found", "This laboratory order was not found.")
    if not orders:
        raise ApiError(422, "order_required", "A laboratory order is required before creating a fee.")
    odoo = odoo_reader()
    ensure_lab_masters(odoo)
    to_bill: list[dict[str, Any]] = []
    already: list[str] = []
    for order in orders:
        if find_existing_sale(odoo, order["uuid"]):
            already.append(order["uuid"])
        else:
            to_bill.append(order)
    keys = [charge_key(order["uuid"]) for order in to_bill]
    if request_id:
        keys.append(request_id)
    if not to_bill:
        payload = _charge_payload(cookie, patient_uuid, user=user, odoo=odoo)
        payload["alreadyCreated"] = True
        return payload
    with IDEMPOTENCY_LOCK:
        for key in keys:
            state = IDEMPOTENCY.get(key) or {}
            if state.get("status") == "pending":
                raise ApiError(
                    409,
                    "charge_in_progress",
                    "This laboratory fee is already being created.",
                )
            if state.get("status") == "done" and not to_bill:
                payload = _charge_payload(cookie, patient_uuid, user=user, odoo=odoo)
                payload["alreadyCreated"] = True
                return payload
        for key in keys:
            IDEMPOTENCY[key] = {"status": "pending"}
    try:
        partner = _partner_for_laboratory_bill(odoo, patient_uuid, body, cookie)
        # Re-check inside the lock window.
        still: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for order in to_bill:
            if find_existing_sale(odoo, order["uuid"]):
                continue
            try:
                product = find_lab_product(odoo, order["conceptUuid"])
            except ApiError as error:
                if error.code in {"missing_mapping", "missing_price"} and wanted:
                    raise
                if error.code in {"missing_mapping", "missing_price"}:
                    continue
                raise
            still.append((order, product))
        if not still:
            raise ApiError(
                409,
                "missing_mapping",
                "This test does not have an approved laboratory fee yet.",
            )
        masters = ensure_lab_masters(odoo)
        shop = masters["shop"]
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = many2one_id(shop.get("pricelist_id")) or 1
        currency_id = _ngn_currency_id(odoo) or many2one_id(
            (odoo.read("product.pricelist", [pricelist_id], ["currency_id"]) or [{}])[0].get("currency_id")
        )
        origin = still[0][0].get("visitUuid") or still[0][0]["uuid"]
        accession = ""
        for order, _product in still:
            accession = _resolve_accession(order, body)
            if accession:
                _record_order_accession(order, accession, cookie)
                break
        accession_field = _sale_accession_field(odoo) if accession else ""
        line_accession_field = _sale_accession_field(odoo, "sale.order.line") if accession else ""
        order_lines = []
        for order, product in still:
            line = {
                "product_id": int(product["id"]),
                "name": product.get("name") or order.get("testName"),
                "product_uom_qty": 1,
                "price_unit": as_float(product.get("list_price")),
                "tax_id": [(6, 0, [])],
                "external_order_id": charge_key(order["uuid"]),
                "external_id": order["uuid"],
            }
            if line_accession_field:
                line[line_accession_field] = accession
            order_lines.append((0, 0, line))
        sale_id = int(
            execute(
                odoo,
                "sale.order",
                "create",
                [
                    {
                        "partner_id": int(partner["id"]),
                        "shop_id": shop_id,
                        "warehouse_id": warehouse_id,
                        "pricelist_id": pricelist_id,
                        "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                        "origin": origin,
                        "care_setting": "opd",
                        "order_line": order_lines,
                        **({accession_field: accession} if accession_field and accession else {}),
                        **({"currency_id": int(currency_id)} if currency_id else {}),
                    }
                ],
            )
        )
        sale_rows = odoo.read("sale.order", [sale_id], ["order_line"])
        line_ids = [int(item) for item in ((sale_rows[0].get("order_line") if sale_rows else None) or [])]
        if line_ids:
            execute(odoo, "sale.order.line", "write", [line_ids, {"tax_id": [(6, 0, [])]}])
        _confirm_sale(odoo, sale_id)
        confirmed = odoo.read("sale.order", [sale_id], ["state", "invoice_ids"])
        if not confirmed or confirmed[0].get("state") not in {"sale", "done"}:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The laboratory fee could not be created. Refresh and try again.",
            )
        with IDEMPOTENCY_LOCK:
            for key in keys:
                IDEMPOTENCY[key] = {"status": "done"}
        payload = _charge_payload(cookie, patient_uuid, user=user, odoo=odoo)
        payload["alreadyCreated"] = False
        payload["recordedBy"] = user.get("username") or ""
        return payload
    except ApiError:
        with IDEMPOTENCY_LOCK:
            for key in keys:
                current = IDEMPOTENCY.get(key) or {}
                if current.get("status") == "pending":
                    IDEMPOTENCY.pop(key, None)
        raise
    except Exception:
        with IDEMPOTENCY_LOCK:
            for key in keys:
                current = IDEMPOTENCY.get(key) or {}
                if current.get("status") == "pending":
                    IDEMPOTENCY.pop(key, None)
        raise


def delete_lab_order(order_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Remove a laboratory order that has not been processed, and keep who deleted it and why."""
    user = require_lab_user(cookie)
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 3:
        raise ApiError(422, "reason_required", "Enter why this laboratory order is being deleted.")
    if len(reason) > 500:
        raise ApiError(422, "reason_too_long", "Keep the reason shorter than 500 characters.")
    order_uuid = str(order_uuid or "").strip()
    if not order_uuid:
        raise ApiError(422, "missing_order", "Choose a laboratory order to delete.")
    patient_uuid = str(body.get("patientUuid") or "").strip() or None
    order = load_lab_order(order_uuid, patient_uuid, cookie)
    if WORKFLOW_VALIDATIONS.get(order_uuid):
        raise ApiError(
            409,
            "order_in_progress",
            "This result has been released and cannot be removed.",
        )
    if WORKFLOW_RESULTS.get(order_uuid):
        raise ApiError(
            409,
            "order_in_progress",
            "This test has already been processed and cannot be deleted.",
        )
    found_patient = str(order.get("patientUuid") or "")
    if found_patient:
        try:
            if order_uuid in _result_order_uuids(found_patient, cookie):
                raise ApiError(
                    409,
                    "order_in_progress",
                    "This test has already been processed and cannot be deleted.",
                )
        except ApiError as error:
            if error.code == "order_in_progress":
                raise

    odoo = odoo_reader()
    username = str(user.get("username") or "").strip() or "Laboratory"
    _release_unpaid_lab_bill(odoo, order_uuid, username, reason)
    _void_lab_order(order_uuid, cookie)

    import deleted_lab_orders as deletions

    saved = deletions.record_deletion(
        {
            "orderUuid": order_uuid,
            "orderNumber": order.get("orderNumber") or "",
            "testName": order.get("testName") or "Laboratory test",
            "patientName": order.get("patientName") or "Unknown patient",
            "hospitalNumber": core.chart_number_from_ref(str(order.get("mrn") or "")),
            "patientUuid": found_patient,
            "reason": reason,
            "deletedBy": username,
        }
    )
    return {
        "status": "ok",
        "success": True,
        "deleted": saved,
        "message": "The laboratory order was deleted.",
    }


def list_deleted_lab_orders(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_lab_user(cookie)
    params = query or {}
    try:
        limit = min(max(int((params.get("limit") or ["25"])[0]), 1), 100)
    except ValueError:
        limit = 25
    try:
        offset = max(int((params.get("offset") or ["0"])[0]), 0)
    except ValueError:
        offset = 0
    q = str((params.get("q") or [""])[0] or "").strip()
    import deleted_lab_orders as deletions

    return deletions.list_deletions(q, offset, limit)


def _release_unpaid_lab_bill(odoo: OdooReader, order_uuid: str, username: str, reason: str) -> None:
    found = find_existing_sale(odoo, order_uuid)
    if not found:
        return
    _line, sale = found
    if str(sale.get("state") or "") == "cancel":
        return
    sale_id = int(sale["id"])
    lines = odoo.search_read(
        "sale.order.line",
        [("order_id", "=", sale_id)],
        ["id"],
        limit=5,
    )
    if len(lines) > 1:
        raise ApiError(
            409,
            "bill_shared",
            "This test is on a bill with other tests. Ask the cashier before deleting it.",
        )
    invoice_ids = [int(item) for item in (sale.get("invoice_ids") or [])]
    invoices = odoo.read(
        "account.move",
        invoice_ids,
        ["name", "state", "payment_state", "amount_residual", "amount_total", "move_type"],
    ) if invoice_ids else []
    for invoice in invoices:
        if invoice.get("move_type") != "out_invoice" or invoice.get("state") == "cancel":
            continue
        if invoice_payment_label(invoice) != "UNPAID":
            raise ApiError(
                409,
                "bill_has_payment",
                "This test has a payment. Ask the cashier before deleting it.",
            )
        invoice_id = int(invoice["id"])
        try:
            if invoice.get("state") == "posted":
                execute_allowing_empty(odoo, "account.move", "button_draft", [[invoice_id]])
            execute(
                odoo,
                "account.move",
                "write",
                [[invoice_id], {"narration": f"Deleted with laboratory order by {username}. Reason: {reason}"}],
            )
            execute_allowing_empty(odoo, "account.move", "button_cancel", [[invoice_id]])
        except xmlrpc.client.Fault as error:
            raise ApiError(
                409,
                "order_not_deleted",
                "This laboratory order could not be deleted. Refresh and try again.",
            ) from error
    if str(sale.get("state") or "") not in {"cancel", "draft"}:
        try:
            wizard_id = execute(odoo, "sale.order.cancel", "create", [{"order_id": sale_id}])
            execute(odoo, "sale.order.cancel", "action_cancel", [[int(wizard_id)]])
        except Exception:
            return


def _void_lab_order(order_uuid: str, cookie: str) -> None:
    path = f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}"
    status = _delete_openmrs(path, cookie)
    if status in {None, 404}:
        return
    if _delete_openmrs_service(path):
        return
    raise ApiError(
        502,
        "order_not_deleted",
        "This laboratory order could not be deleted. Refresh and try again.",
    )


def _delete_openmrs(path: str, cookie: str) -> int | None:
    request = Request(
        f"{core.OPENMRS_URL}{path}",
        headers={"Accept": "application/json", "Cookie": cookie},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=30) as response:
            response.read()
        return None
    except HTTPError as error:
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        return int(error.code)
    except (URLError, TimeoutError) as error:
        raise ApiError(
            502,
            "order_not_deleted",
            "This laboratory order could not be deleted. Refresh and try again.",
        ) from error


def _delete_openmrs_service(path: str) -> bool:
    if not core.OPENMRS_ADMIN_USER or not core.OPENMRS_ADMIN_PASSWORD:
        return False
    token = base64.b64encode(
        f"{core.OPENMRS_ADMIN_USER}:{core.OPENMRS_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        f"{core.OPENMRS_URL}{path}",
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=30) as response:
            response.read()
        return True
    except HTTPError as error:
        return error.code == 404
    except (URLError, TimeoutError):
        return False


def build_catalogue(cookie: str, query: str = "") -> dict[str, Any]:
    require_clinical_or_lab_user(cookie)
    currency = dict(NGN_CURRENCY)
    reader: OdooReader | None = None
    try:
        reader = odoo_reader()
        currency = lab_currency(reader)
    except ApiError:
        reader = None
    items = []
    for row in lab_catalogue.search_entries(query, include_unorderable=False):
        live = None
        if reader and row.get("conceptUuid"):
            try:
                product = find_lab_product(reader, row["conceptUuid"])
                live = as_float(product.get("list_price"))
            except ApiError:
                live = None
        items.append(lab_catalogue.serialize_entry(row, live_price=live, currency=currency))
    return {
        "status": "ok",
        "currency": {
            "code": currency.get("code") or "NGN",
            "symbol": currency.get("symbol") or "₦",
        },
        "tests": items,
    }


def _result_order_uuids(patient_uuid: str, cookie: str) -> set[str]:
    payload = _openmrs_json(
        f"/openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid={quote(patient_uuid)}",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    found: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict) and row.get("orderUuid") and row.get("result"):
            found.add(str(row["orderUuid"]))
    return found


def _openelis_status_stage(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in OPENELIS_COMPLETED_STATUSES:
        return "completed"
    if normalized in OPENELIS_PROCESSING_STATUSES:
        return "processing"
    if normalized in OPENELIS_PENDING_STATUSES:
        return "pending"
    return "unknown"


def _accession_details(encounter_uuid: str) -> list[dict[str, Any]]:
    if not encounter_uuid:
        return []
    payload = _openelis_json(f"/ws/rest/accession/{quote(encounter_uuid)}")
    if str(payload.get("accessionUuid") or "") != encounter_uuid:
        raise ApiError(
            502,
            "openelis_identity_mismatch",
            "Laboratory processing status could not be matched safely.",
        )
    rows = payload.get("testDetails")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _detail_concept_uuid(detail: dict[str, Any]) -> str:
    return str(detail.get("testUuid") or detail.get("panelUuid") or "").strip()


def _laboratory_state(
    order: dict[str, Any],
    encounter_orders: list[dict[str, Any]],
    details: list[dict[str, Any]] | None,
    result_uuids: set[str],
) -> dict[str, Any]:
    """Map one independent OpenMRS order to authoritative OpenELIS state."""
    concept_uuid = str(order.get("conceptUuid") or "")
    same_orders = [
        row for row in encounter_orders if str(row.get("conceptUuid") or "") == concept_uuid
    ]
    matches = [
        row for row in (details or []) if _detail_concept_uuid(row) == concept_uuid
    ]
    if len(same_orders) > 1 or len(matches) > 1:
        order_uuids = sorted(str(row.get("uuid") or "") for row in same_orders)
        if str(order.get("uuid") or "") == order_uuids[0]:
            LOGGER.warning(
                "Ambiguous laboratory result mapping encounter=%s concept=%s orders=%s details=%s",
                order.get("encounterUuid") or "",
                concept_uuid,
                order_uuids,
                len(matches),
            )
        statuses = sorted(
            {
                str(row.get("status") or "").strip()
                for row in matches
                if str(row.get("status") or "").strip()
            }
        )
        completed = any(_openelis_status_stage(status) == "completed" for status in statuses)
        return {
            "stage": "completed" if completed else "unknown",
            "laboratoryStatus": " / ".join(statuses) if statuses else "Order match needs review",
            "resultMapping": "ambiguous",
            "statusMessage": (
                "OpenELIS has a finalized result, but duplicate same-test orders "
                "prevent a safe order match."
                if completed
                else "Duplicate same-test orders prevent a safe laboratory status match."
            ),
            # The OpenMRS worker's first-wins result must not be represented as a
            # safely correlated per-order result.
            "hasResult": False,
        }
    if len(matches) == 1:
        status = str(matches[0].get("status") or "").strip()
        return {
            "stage": _openelis_status_stage(status),
            "laboratoryStatus": status or "Status unavailable",
            "resultMapping": "unique",
            "statusMessage": "",
            "hasResult": (
                order["uuid"] in result_uuids
                and _openelis_status_stage(status) == "completed"
            ),
        }
    # OpenELIS often lags atomfeed by seconds/minutes. Treat "not loaded yet"
    # as pending so new Lab Direct / external orders appear on Pending Orders.
    return {
        "stage": "pending",
        "laboratoryStatus": (
            "Awaiting laboratory receipt"
            if details is None
            else "Not received by laboratory"
        ),
        "resultMapping": "none",
        "statusMessage": (
            "This order is waiting to be received for sample processing."
            if details is None
            else "No matching laboratory analysis was found."
        ),
        "hasResult": False,
    }


BOARD_VISIT_WINDOW_DAYS = 14
BOARD_VISIT_PAGE_SIZE = 50
BOARD_VISIT_PAGE_CAP = 400
BOARD_VISIT_REPRESENTATION = (
    "custom:(uuid,startDatetime,"
    "encounters:(orders:(uuid,voided,dateActivated,dateCreated,"
    "orderType:(uuid,display))))"
)


def lab_order_uuids_from_visits(visits: list[dict[str, Any]]) -> list[str]:
    """Lab order UUIDs on these visits, newest first."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for visit in visits:
        if not isinstance(visit, dict):
            continue
        started = str(visit.get("startDatetime") or "")
        for encounter in visit.get("encounters") or []:
            if not isinstance(encounter, dict):
                continue
            for order in encounter.get("orders") or []:
                if not isinstance(order, dict) or order.get("voided") or not order.get("uuid"):
                    continue
                order_type = order.get("orderType") if isinstance(order.get("orderType"), dict) else {}
                type_uuid = str(order_type.get("uuid") or "")
                type_name = str(order_type.get("display") or order_type.get("name") or "")
                if type_uuid != LAB_ORDER_TYPE_UUID and type_name != LAB_ORDER_TYPE_NAME:
                    continue
                uuid = str(order["uuid"]).strip()
                if not uuid or uuid in seen:
                    continue
                seen.add(uuid)
                when = str(order.get("dateActivated") or order.get("dateCreated") or started)
                found.append((when, uuid))
    found.sort(reverse=True)
    return [uuid for _when, uuid in found]


def _board_uuids_from_visits(cookie: str) -> list[str]:
    """Recent doctor orders have no bill yet, so the visit list is how they are found."""
    from_start = (datetime.now(timezone.utc).date() - timedelta(days=BOARD_VISIT_WINDOW_DAYS)).isoformat()
    visits: list[dict[str, Any]] = []
    start_index = 0
    try:
        while start_index < BOARD_VISIT_PAGE_CAP:
            payload = _openmrs_json(
                "/openmrs/ws/rest/v1/visit"
                f"?fromStartDate={quote(from_start)}"
                "&includeInactive=true"
                f"&limit={BOARD_VISIT_PAGE_SIZE}"
                f"&startIndex={start_index}"
                f"&v={quote(BOARD_VISIT_REPRESENTATION, safe='(),:')}",
                cookie,
            )
            rows = payload.get("results") if isinstance(payload, dict) else payload
            if not isinstance(rows, list) or not rows:
                break
            visits.extend(row for row in rows if isinstance(row, dict))
            if len(rows) < BOARD_VISIT_PAGE_SIZE:
                break
            start_index += len(rows)
    except ApiError:
        return []
    return lab_order_uuids_from_visits(visits)


def _board_uuids_from_openmrs(cookie: str, limit: int = 80) -> list[str]:
    try:
        payload = _openmrs_json(
            f"/openmrs/ws/rest/v1/order?orderType={LAB_ORDER_TYPE_UUID}&limit={limit}"
            "&v=custom:(uuid,voided,dateActivated,orderType:(uuid,display))",
            cookie,
        )
    except ApiError:
        return []
    rows = payload.get("results") if isinstance(payload, dict) else payload
    uuids: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict) or row.get("voided"):
            continue
        order_type = row.get("orderType") if isinstance(row.get("orderType"), dict) else {}
        type_uuid = order_type.get("uuid") or ""
        type_name = order_type.get("display") or ""
        if type_uuid and type_uuid != LAB_ORDER_TYPE_UUID and type_name != LAB_ORDER_TYPE_NAME:
            continue
        uuid = str(row.get("uuid") or "").strip()
        if uuid and uuid not in seen:
            seen.add(uuid)
            uuids.append(uuid)
    return uuids


def _board_uuids_from_odoo(odoo: OdooReader) -> list[str]:
    try:
        lines = execute(
            odoo,
            "sale.order.line",
            "search_read",
            [[("external_order_id", "like", f"{EXTERNAL_PREFIX}%")]],
            {"fields": ["external_order_id"], "limit": 80, "order": "id desc"},
        )
    except xmlrpc.client.Fault:
        lines = odoo.search_read(
            "sale.order.line",
            [("external_order_id", "like", f"{EXTERNAL_PREFIX}%")],
            ["external_order_id"],
            limit=80,
        )
    uuids: list[str] = []
    seen: set[str] = set()
    for line in lines or []:
        key = str(line.get("external_order_id") or "")
        if not key.startswith(EXTERNAL_PREFIX):
            continue
        uuid = key[len(EXTERNAL_PREFIX) :]
        if uuid and uuid not in seen:
            seen.add(uuid)
            uuids.append(uuid)
    return uuids


def _board_uuids_from_external(cookie: str, limit_patients: int = 40) -> list[str]:
    """Seed recent external Lab Direct patients so they are not lost to the top-80 cut."""
    try:
        import laboratory_external as external

        external.ensure_schema()
        rows = external._list_patient_rows()[:limit_patients]
    except Exception:
        return []
    uuids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        patient_uuid = str(row.get("openmrs_uuid") or "").strip()
        if not patient_uuid:
            continue
        try:
            for order in list_lab_orders(patient_uuid, cookie):
                order_uuid = str(order.get("uuid") or "").strip()
                if order_uuid and order_uuid not in seen:
                    seen.add(order_uuid)
                    uuids.append(order_uuid)
        except ApiError:
            continue
    return uuids


def _load_board_orders(uuids: list[str], cookie: str, limit: int = 80) -> list[dict[str, Any]]:
    """Expand seeded order UUIDs to all lab orders for the same patients."""
    orders: list[dict[str, Any]] = []
    seen_orders: set[str] = set()
    seen_patients: set[str] = set()
    queue = list(uuids)
    extra: list[dict[str, Any]] = []

    def _one(order_uuid: str) -> dict[str, Any] | None:
        try:
            return load_lab_order(order_uuid, None, cookie)
        except ApiError:
            return None

    while queue and len(orders) < limit:
        batch: list[str] = []
        while queue and len(batch) < min(8, limit - len(orders)):
            uuid = queue.pop(0)
            if uuid not in seen_orders:
                seen_orders.add(uuid)
                batch.append(uuid)
        if not batch:
            break
        with ThreadPoolExecutor(max_workers=min(8, len(batch))) as pool:
            loaded = list(pool.map(_one, batch))
        for order in loaded:
            if not order:
                continue
            orders.append(order)
            patient_uuid = str(order.get("patientUuid") or "")
            if patient_uuid and patient_uuid not in seen_patients:
                seen_patients.add(patient_uuid)
                try:
                    siblings = list_lab_orders(patient_uuid, cookie)
                except ApiError:
                    siblings = []
                for sibling in siblings:
                    sibling_uuid = str(sibling.get("uuid") or "")
                    if not sibling_uuid or sibling_uuid in seen_orders:
                        continue
                    seen_orders.add(sibling_uuid)
                    extra.append(sibling)
            if len(orders) >= limit:
                break
    for sibling in extra:
        if len(orders) >= limit:
            break
        orders.append(sibling)
    return orders


def build_lab_order(
    order_uuid: str,
    patient_uuid: str | None,
    visit_uuid: str | None,
    cookie: str,
) -> dict[str, Any]:
    """Load one laboratory order for the Laboratory workspace detail page."""
    require_lab_user(cookie)
    order = load_lab_order(order_uuid, patient_uuid or None, cookie)
    found_visit = str(order.get("visitUuid") or "")
    if visit_uuid and found_visit and found_visit != visit_uuid:
        raise ApiError(
            409,
            "wrong_visit",
            "This laboratory order does not belong to this visit.",
        )
    accession = WORKFLOW_ACCESSIONS.get(order_uuid) or str(order.get("accession") or "")
    return {
        "status": "ok",
        "order": {
            "uuid": order["uuid"],
            "orderNumber": order.get("orderNumber") or "—",
            "testName": ", ".join(_tests_on_same_request(order, cookie)) or order.get("testName") or "Laboratory order",
            "patientUuid": order.get("patientUuid") or "",
            "visitUuid": found_visit,
            "encounterUuid": order.get("encounterUuid") or "",
            "patientName": order.get("patientName") or "Unknown patient",
            "mrn": order.get("mrn") or "",
            "age": order.get("age") or "",
            "ordered": order.get("ordered") or "",
            "urgency": order.get("urgency") or "Routine",
            "comment": order.get("comment") or "",
            "provider": order.get("provider") or "—",
            "accession": accession,
        },
    }


def _bill_lines(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One bill line per test, so a combined order can be billed test by test."""
    lines = []
    for member in members:
        lines.append(
            {
                "orderUuid": str(member.get("uuid") or ""),
                "testName": str(member.get("testName") or "Laboratory test"),
                "hasCharge": bool(member.get("hasCharge")),
                "paymentStatus": str(member.get("paymentStatus") or "UNPAID"),
            }
        )
    return lines


def orders_waiting_for_bill(odoo: OdooReader, order_uuids: list[str]) -> list[str]:
    """Order ids that do not yet have a laboratory bill."""
    waiting = []
    for order_uuid in order_uuids:
        uuid = str(order_uuid or "").strip()
        if uuid and not find_existing_sale(odoo, uuid):
            waiting.append(uuid)
    return waiting


def _group_board_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Show tests requested together as one laboratory order."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    order_keys: list[str] = []
    for order in orders:
        key = str(order.get("requestKey") or "") or order_request_key(order)
        if key not in buckets:
            order_keys.append(key)
            buckets[key] = []
        buckets[key].append(order)
    grouped: list[dict[str, Any]] = []
    for key in order_keys:
        members = buckets[key]
        if len(members) == 1:
            only = dict(members[0])
            only["orderUuids"] = [str(only.get("uuid") or "")]
            only["testNames"] = [str(only.get("testName") or "Laboratory test")]
            only["charges"] = _bill_lines([only])
            grouped.append(only)
            continue
        members.sort(key=lambda row: str(row.get("ordered") or ""))
        released_members = [
            member
            for member in members
            if WORKFLOW_VALIDATIONS.get(str(member.get("uuid") or ""))
        ]
        chunks = [members]
        if released_members and len(released_members) < len(members):
            chunks = [
                released_members,
                [member for member in members if member not in released_members],
            ]
        for chunk in chunks:
            names: list[str] = []
            uuids: list[str] = []
            for member in chunk:
                name = str(member.get("testName") or "").strip() or "Laboratory test"
                if name not in names:
                    names.append(name)
                uuid = str(member.get("uuid") or "")
                if uuid:
                    uuids.append(uuid)
            stages = [str(member.get("stage") or "") for member in chunk]
            released = any(WORKFLOW_VALIDATIONS.get(str(member.get("uuid") or "")) for member in chunk)
            if stages and all(stage == "completed" for stage in stages) or released:
                stage = "completed"
                status = "Results ready"
            elif any(stage in {"processing", "completed"} for stage in stages):
                stage = "processing"
                status = "In progress"
            else:
                stage = "pending"
                status = str(chunk[0].get("laboratoryStatus") or "Waiting")
            lead = dict(chunk[-1])
            lead["uuid"] = uuids[0] if uuids else lead.get("uuid")
            lead["orderUuids"] = uuids
            lead["testNames"] = names
            lead["testName"] = ", ".join(names)
            lead["ordered"] = str(chunk[-1].get("ordered") or lead.get("ordered") or "")
            lead["stage"] = stage
            lead["laboratoryStatus"] = status
            lead["charges"] = _bill_lines(chunk)
            lead["hasCharge"] = all(bool(member.get("hasCharge")) for member in chunk)
            lead["hasResult"] = any(bool(member.get("hasResult")) for member in chunk)
            lead["outsourced"] = any(bool(member.get("outsourced")) for member in chunk)
            lead["accession"] = next((str(member.get("accession") or "") for member in chunk if member.get("accession")), "")
            if not lead["hasCharge"]:
                lead["paymentStatus"] = "UNPAID"
            elif all(str(member.get("paymentStatus") or "") == "PAID" for member in chunk):
                lead["paymentStatus"] = "PAID"
            grouped.append(lead)
    return grouped


def _ordered_test_names(order: dict[str, Any]) -> list[str]:
    """Tests that belong to this order, including the members of a panel."""
    import lab_catalogue

    concept = str(order.get("conceptUuid") or "").strip()
    entries = lab_catalogue.catalogue_entries()
    entry = next((row for row in entries if str(row.get("conceptUuid") or "") == concept), None)
    names: list[str] = []
    if entry:
        by_sn = {str(row.get("sn") or ""): row for row in entries}
        for sn in entry.get("memberSns") or []:
            member = by_sn.get(str(sn))
            if not member:
                continue
            name = str(
                member.get("openmrsName") or member.get("createName") or member.get("hospitalName") or ""
            ).strip()
            if name and name not in names:
                names.append(name)
    if not names:
        fallback = str(order.get("testName") or "").strip()
        if fallback:
            names.append(fallback)
    return names


def _tests_on_same_request(order: dict[str, Any], cookie: str) -> list[str]:
    """Every test the doctor sent on this consultation, not only the one row that was opened."""
    names = list(_ordered_test_names(order))
    siblings = _orders_on_same_request(order, cookie)
    if siblings == [order] and not order.get("patientUuid"):
        return names
    siblings.sort(key=lambda row: str(row.get("ordered") or ""))
    combined: list[str] = []
    for row in siblings or [order]:
        for name in _ordered_test_names(row):
            if name and name not in combined:
                combined.append(name)
    return combined or names


def _resolve_accession(order: dict[str, Any], body: dict[str, Any] | None = None) -> str:
    """Use the accession already on the sample, not only the one remembered for this row."""
    payload = body or {}
    order_uuid = str(order.get("uuid") or "")
    for candidate in (
        payload.get("accession"),
        WORKFLOW_ACCESSIONS.get(order_uuid),
        order.get("accession"),
    ):
        text = str(candidate or "").strip()
        if text and text != "—":
            return text
    encounter = str(order.get("encounterUuid") or "")
    if not encounter:
        return ""
    try:
        from openelis_adapter import OpenElisAdapter

        found = _accession_for_visit(OpenElisAdapter(), encounter)
    except Exception:
        found = ""
    if found and order_uuid:
        _remember_workflow_accession(order_uuid, found)
    return found


def _attach_missing_tests(accession: str, results: list[Any]) -> None:
    if not accession:
        return
    test_ids = [
        str(item.get("testId") or "").strip()
        for item in results
        if isinstance(item, dict) and str(item.get("testId") or "").strip()
    ]
    if not test_ids:
        return
    import openelis_sql

    try:
        openelis_sql.ensure_analyses(accession, test_ids)
    except Exception:
        LOGGER.warning("Could not attach tests to accession %s", accession)


def _record_order_accession(order: dict[str, Any], accession: str, cookie: str) -> None:
    """The bill reads the accession from the order. Collection stores it on the sample."""
    number = str(accession or "").strip()
    order_uuid = str(order.get("uuid") or "").strip()
    if not number or not order_uuid or str(order.get("accession") or "").strip() == number:
        return
    try:
        _openmrs_post(
            f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}",
            cookie,
            {"accessionNumber": number},
        )
    except ApiError:
        try:
            import server

            server.openmrs_service_post(
                f"/openmrs/ws/rest/v1/order/{quote(order_uuid)}",
                {"accessionNumber": number},
            )
        except Exception:
            LOGGER.warning("Could not store accession on order %s", order_uuid)


def _sale_accession_field(odoo: OdooReader, model: str = "sale.order") -> str:
    try:
        fields = execute(odoo, model, "fields_get", [], {"attributes": ["string"]})
    except Exception:
        return ""
    if not isinstance(fields, dict):
        return ""
    for name in ("accession_number", "accession", "x_accession_number", "lab_number", "lab_no"):
        if name in fields:
            return name
    for name in fields:
        if "accession" in str(name).lower():
            return str(name)
    return ""


def _accession_for_visit(adapter: Any, encounter_uuid: str) -> str:
    """Use the sample already on this visit, and give it an accession if it does not have one."""
    if not encounter_uuid:
        return ""
    import openelis_sql

    samples = openelis_sql.samples_for_encounter(encounter_uuid)
    first = ""
    for sample in samples:
        number = str(sample.get("accession") or "")
        if not number:
            try:
                number = adapter.next_accession()
                openelis_sql.assign_accession(str(sample.get("id") or ""), number)
            except Exception:
                number = ""
        if number and not first:
            first = number
    return first


def _expand_panel_results(
    tests: list[dict[str, Any]],
    panels: dict[str, dict[str, str]],
    result_fields: list[dict[str, Any]],
    adapter: Any,
    sample_type_id: str,
) -> list[dict[str, Any]]:
    """A panel such as complete blood count is several results, not one empty row."""
    if not panels or not result_fields:
        return tests
    catalogue = adapter.tests_for_sample_type(sample_type_id)
    names_by_id = {str(value): name for name, value in catalogue.items()}
    expanded: list[dict[str, Any]] = []
    for test in tests:
        panel = panels.get(str(test.get("name") or ""))
        if not panel:
            expanded.append(test)
            continue
        member_ids = {
            item.strip() for item in str(panel.get("members") or "").split(",") if item.strip()
        }
        members = [
            row for row in result_fields if str(row.get("testId") or "") in member_ids
        ]
        if not members:
            expanded.append(test)
            continue
        for field in members:
            test_id = str(field.get("testId") or "")
            expanded.append(
                {
                    **test,
                    "testId": test_id,
                    "analysisId": str(field.get("analysisId") or ""),
                    "resultId": str(field.get("resultId") or ""),
                    "resultType": str(field.get("resultType") or test.get("resultType") or "D"),
                    "name": names_by_id.get(test_id) or str(test.get("name") or "Test"),
                    "resultValue": str(field.get("resultValue") or field.get("qualifiedResultValue") or ""),
                    "qualifiedResultValue": str(field.get("qualifiedResultValue") or ""),
                    "note": str(field.get("note") or test.get("note") or ""),
                    "referenceLow": "",
                    "referenceHigh": "",
                    "savedReferenceLow": "",
                    "savedReferenceHigh": "",
                    "options": field.get("resultOptions") if isinstance(field.get("resultOptions"), list) else [],
                }
            )
    return expanded


def _option_tokens(test: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    options = test.get("options") if isinstance(test.get("options"), list) else []
    for option in options:
        if isinstance(option, dict):
            tokens.add(str(option.get("value") or "").strip())
            tokens.add(str(option.get("label") or "").strip())
        else:
            tokens.add(str(option).strip())
    tokens.discard("")
    return tokens


def _clear_borrowed_results(tests: list[dict[str, Any]]) -> None:
    """Drop an answer that belongs to a different test on the same request."""
    owners: dict[str, set[str]] = {}
    for test in tests:
        name = str(test.get("name") or "").strip()
        for token in _option_tokens(test):
            owners.setdefault(token, set()).add(name)
    for test in tests:
        name = str(test.get("name") or "").strip()
        own = _option_tokens(test)
        for field in ("resultValue", "qualifiedResultValue"):
            value = str(test.get(field) or "").strip()
            if not value:
                continue
            if own and value not in own:
                test[field] = ""
                continue
            holders = owners.get(value) or set()
            if holders and name not in holders:
                test[field] = ""


def _apply_catalogue_parameters(
    tests: list[dict[str, Any]],
    result_fields: list[dict[str, Any]],
    saved_results: list[Any],
) -> list[dict[str, Any]]:
    """Replace a panel with its parameters, and attach the unit stored on each test."""
    import openelis_sql

    found = openelis_sql.parameters_for_names([str(test.get("name") or "") for test in tests])
    if not found:
        return tests
    fields_by_id = {
        str(row.get("testId") or ""): row
        for row in result_fields
        if isinstance(row, dict) and str(row.get("testId") or "")
    }
    saved_by_name: dict[str, dict[str, Any]] = {}
    for item in saved_results:
        if isinstance(item, dict) and str(item.get("testName") or "").strip():
            saved_by_name[str(item.get("testName") or "").casefold()] = item
    expanded: list[dict[str, Any]] = []
    for test in tests:
        key = str(test.get("name") or "").casefold()
        params = found.get(key) or []
        single = len(params) == 1 and str(params[0].get("name") or "").casefold() == key
        if not params or single:
            saved = saved_by_name.get(key) or {}
            unit = str(saved.get("unit") or "").strip() or (str(params[0].get("unit") or "") if params else "")
            row = {**test, "unit": unit or str(test.get("unit") or "")}
            if str(saved.get("note") or "").strip():
                row["note"] = str(saved.get("note") or "")
            if params:
                if not str(row.get("testId") or "").strip():
                    row["testId"] = str(params[0].get("testId") or "")
                if params[0].get("resultType"):
                    row["resultType"] = str(params[0].get("resultType") or "")
                if isinstance(params[0].get("options"), list) and params[0].get("options"):
                    row["options"] = params[0]["options"]
            if _choice_result(row):
                row["unit"] = ""
                row["referenceLow"] = ""
                row["referenceHigh"] = ""
            expanded.append(row)
            continue
        for param in params:
            field = fields_by_id.get(str(param.get("testId") or "")) or {}
            saved = saved_by_name.get(str(param.get("name") or "").casefold()) or {}
            unit = str(saved.get("unit") or "").strip() or str(param.get("unit") or "")
            parent_note = str(test.get("note") or "")
            expanded.append(
                {
                    **test,
                    "testId": str(param.get("testId") or ""),
                    "analysisId": str(field.get("analysisId") or ""),
                    "resultId": str(field.get("resultId") or ""),
                    "resultType": str(field.get("resultType") or param.get("resultType") or ""),
                    "name": str(param.get("name") or test.get("name") or "Test"),
                    "orderedAs": str(test.get("orderedAs") or test.get("name") or ""),
                    "unit": unit,
                    "status": str(field.get("status") or ""),
                    "resultValue": _prefer_typed(
                        saved.get("resultLabel") or saved.get("resultValue"),
                        field.get("resultValue") or field.get("qualifiedResultValue"),
                    ),
                    "qualifiedResultValue": str(
                        field.get("qualifiedResultValue") or saved.get("qualifiedResultValue") or ""
                    ),
                    "note": _prefer_typed(saved.get("note") or parent_note, field.get("note")),
                    "referenceLow": "",
                    "referenceHigh": "",
                    "savedReferenceLow": str(saved.get("referenceLow") or ""),
                    "savedReferenceHigh": str(saved.get("referenceHigh") or ""),
                    "flag": str(field.get("flag") or saved.get("flag") or ""),
                    "options": (
                        field.get("resultOptions")
                        if isinstance(field.get("resultOptions"), list) and field.get("resultOptions")
                        else param.get("options")
                        if isinstance(param.get("options"), list)
                        else []
                    ),
                }
            )
            if _choice_result(expanded[-1]):
                expanded[-1]["unit"] = ""
                expanded[-1]["referenceLow"] = ""
                expanded[-1]["referenceHigh"] = ""
    return expanded


def build_lab_workflow(
    order_uuid: str,
    patient_uuid: str | None,
    visit_uuid: str | None,
    cookie: str,
) -> dict[str, Any]:
    """Return the Hospital EMR-facing collection, result, and validation workflow."""
    require_lab_user(cookie)
    order = load_lab_order(order_uuid, patient_uuid or None, cookie)
    found_visit = str(order.get("visitUuid") or "")
    if visit_uuid and found_visit and found_visit != visit_uuid:
        raise ApiError(409, "wrong_visit", "This laboratory order does not belong to this visit.")
    details: list[dict[str, Any]] = []
    if order.get("encounterUuid"):
        try:
            details = _accession_details(str(order.get("encounterUuid") or ""))
        except ApiError:
            # A new order has no accession yet. OpenELIS reports that as an error.
            # Collection still has to start from the ordered test.
            details = []
    accession = WORKFLOW_ACCESSIONS.get(order_uuid) or str(order.get("accession") or "")
    from openelis_adapter import OpenElisAdapter

    adapter = OpenElisAdapter()
    ordered_names = _tests_on_same_request(order, cookie)
    wanted = {name.casefold() for name in ordered_names}
    matched_details = [
        detail
        for detail in details
        if str(detail.get("testName") or detail.get("name") or "").casefold() in wanted
    ]
    sample_type_id, sample_test_ids, sample_panels = adapter.match_ordered_tests(ordered_names)
    if not accession:
        accession = _accession_for_visit(adapter, str(order.get("encounterUuid") or ""))
    result_fields = adapter.result_fields(accession) if accession else []
    fields_by_test = {
        str(row.get("testId") or ""): row
        for row in result_fields
        if isinstance(row, dict) and str(row.get("testId") or "")
    }
    saved_results = _saved_results_for_request(order, cookie)
    orders_by_name = {
        str(row.get("testName") or "").strip().casefold(): str(row.get("uuid") or "")
        for row in _orders_on_same_request(order, cookie)
        if str(row.get("testName") or "").strip()
    }
    saved_by_name = {
        str(item.get("testName") or "").strip().casefold(): item
        for item in saved_results
        if isinstance(item, dict) and str(item.get("testName") or "").strip()
    }
    tests: list[dict[str, Any]] = []
    for test_name in ordered_names:
        detail = next(
            (
                row
                for row in matched_details
                if str(row.get("testName") or row.get("name") or "").casefold() == test_name.casefold()
            ),
            {},
        )
        panel = sample_panels.get(test_name) or {}
        test_id = str(sample_test_ids.get(test_name) or panel.get("id") or "")
        form_fields = {} if panel or not test_id else fields_by_test.get(test_id) or {}
        if not isinstance(form_fields, dict):
            form_fields = {}
        saved_result = saved_by_name.get(test_name.casefold()) or {}
        if not isinstance(saved_result, dict):
            saved_result = {}
        tests.append(
            {
                "testId": str(form_fields.get("testId") or sample_test_ids.get(test_name) or panel.get("id") or ""),
                "analysisId": str(form_fields.get("analysisId") or ""),
                "resultId": str(form_fields.get("resultId") or ""),
                "resultType": str(form_fields.get("resultType") or detail.get("resultType") or "D"),
                "name": test_name,
                "orderedAs": test_name,
                "status": str(detail.get("status") or ""),
                "orderUuid": orders_by_name.get(test_name.casefold()) or order_uuid,
                "resultValue": _prefer_typed(
                    saved_result.get("resultLabel") or saved_result.get("resultValue"),
                    detail.get("result")
                    or form_fields.get("resultValue")
                    or form_fields.get("qualifiedResultValue"),
                ),
                "qualifiedResultValue": str(
                    form_fields.get("qualifiedResultValue") or saved_result.get("qualifiedResultValue") or ""
                ),
                "note": _prefer_typed(
                    saved_result.get("note"),
                    detail.get("notes") or form_fields.get("note"),
                ),
                "referenceLow": "",
                "referenceHigh": "",
                "savedReferenceLow": str(saved_result.get("referenceLow") or ""),
                "savedReferenceHigh": str(saved_result.get("referenceHigh") or ""),
                "flag": str(form_fields.get("flag") or detail.get("flag") or saved_result.get("flag") or ""),
                "options": (
                    form_fields.get("resultOptions")
                    if isinstance(form_fields.get("resultOptions"), list)
                    else detail.get("resultOptions")
                    if isinstance(detail.get("resultOptions"), list)
                    else []
                ),
                "unit": str(saved_result.get("unit") or ""),
                "sampleTypeId": sample_type_id,
            }
        )
    tests = _expand_panel_results(tests, sample_panels, result_fields, adapter, sample_type_id)
    tests = _apply_catalogue_parameters(tests, result_fields, saved_results)
    _clear_borrowed_results(tests)
    _apply_stored_ranges(tests, order)
    return {
        "status": "ok",
        "order": {
            "uuid": order["uuid"],
            "patientUuid": order.get("patientUuid") or "",
            "patientName": order.get("patientName") or "Unknown patient",
            "mrn": order.get("mrn") or "",
            "age": order.get("age") or "",
            "testName": ", ".join(ordered_names) or order.get("testName") or "Laboratory test",
            "accession": accession,
            "encounterUuid": order.get("encounterUuid") or "",
        },
        "sample": {
            "status": "collected" if accession else "waiting",
            "accession": accession,
            "sampleTypeId": sample_type_id,
            "sampleSourceId": "",
        },
        "tests": tests,
        "validation": {
            "status": _request_validation_status(order, order_uuid, cookie),
            "validatedBy": validator_name_for_order(order, cookie),
        },
    }


def _workflow_once(
    action: str,
    order_uuid: str,
    body: dict[str, Any],
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    request_id = str(body.get("requestId") or "").strip()
    key = f"{action}:{order_uuid}:{request_id}" if request_id else ""
    if not key:
        return operation()
    with IDEMPOTENCY_LOCK:
        previous = WORKFLOW_IDEMPOTENCY.get(key)
        if previous and previous.get("status") == "done":
            return dict(previous["payload"])
        if previous and previous.get("status") == "pending":
            raise ApiError(409, "laboratory_action_in_progress", "This laboratory step is already being saved.")
        WORKFLOW_IDEMPOTENCY[key] = {"status": "pending"}
    try:
        payload = operation()
        with IDEMPOTENCY_LOCK:
            WORKFLOW_IDEMPOTENCY[key] = {"status": "done", "payload": payload}
        return payload
    except Exception:
        with IDEMPOTENCY_LOCK:
            WORKFLOW_IDEMPOTENCY.pop(key, None)
        raise


def collect_lab_sample(
    order_uuid: str,
    body: dict[str, Any],
    patient_uuid: str | None,
    cookie: str,
) -> dict[str, Any]:
    require_lab_user(cookie)
    def operation() -> dict[str, Any]:
        order = load_lab_order(order_uuid, patient_uuid or None, cookie)
        from openelis_adapter import OpenElisAdapter

        adapter = OpenElisAdapter()
        encounter_uuid = str(order.get("encounterUuid") or "")
        existing = _accession_for_visit(adapter, encounter_uuid)
        requested = [str(item) for item in (body.get("testIds") or []) if str(item).strip()]
        if existing:
            _attach_missing_tests(existing, [{"testId": item} for item in requested])
            _remember_workflow_accession(order_uuid, existing)
            _record_order_accession(order, existing, cookie)
            workflow = build_lab_workflow(order_uuid, patient_uuid, "", cookie)
            workflow["sample"] = {**workflow.get("sample", {}), "status": "collected", "accession": existing}
            workflow["message"] = "Sample collected."
            return workflow
        panel_ids = adapter.known_panel_ids()
        result = adapter.collect_sample(
            patient_identifier=str(order.get("mrn") or ""),
            sample_type_id=str(body.get("sampleTypeId") or ""),
            test_ids=[item for item in requested if item not in panel_ids],
            panel_ids=[item for item in requested if item in panel_ids],
            sample_source_id=str(body.get("sampleSourceId") or ""),
            received_date=str(body.get("receivedDate") or datetime.now(timezone.utc).strftime("%d/%m/%Y")),
            accession=str(order.get("accession") or body.get("accession") or ""),
            first_name=str(order.get("givenName") or ""),
            last_name=str(order.get("familyName") or order.get("patientName") or ""),
            gender=str(order.get("gender") or ""),
            birth_date=str(order.get("birthDate") or ""),
        )
        if result.get("accession") and encounter_uuid:
            import openelis_sql

            try:
                openelis_sql.attach_accession_to_encounter(str(result["accession"]), encounter_uuid)
            except Exception:
                pass
        if result.get("accession"):
            _remember_workflow_accession(order_uuid, str(result["accession"]))
        workflow = build_lab_workflow(order_uuid, patient_uuid, "", cookie)
        workflow["sample"] = {**workflow.get("sample", {}), "status": "collected", "accession": result.get("accession") or ""}
        workflow["message"] = "Sample collected."
        workflow["adapter"] = result
        return workflow

    return _workflow_once("collect", order_uuid, body, operation)


def _choice_result(test: dict[str, Any]) -> bool:
    """Positive/negative and written results are not numbers."""
    options = test.get("options")
    if isinstance(options, list) and options:
        return True
    return str(test.get("resultType") or "").strip().upper() in {"D", "A", "R"}


def _apply_stored_ranges(tests: list[dict[str, Any]], order: dict[str, Any] | None = None) -> None:
    """Suggest an approved range. A limit already saved with this result is left as it was."""
    import lab_reference_ranges as ranges

    facts = order or {}
    ranges.apply_to_tests(
        tests,
        sex=str(facts.get("gender") or ""),
        birth=facts.get("birthDate") or "",
        on_date=facts.get("ordered") or "",
        specimen=str(facts.get("specimen") or ""),
    )


def list_reference_ranges(cookie: str, query: str = "", status: str = "") -> dict[str, Any]:
    require_lab_user(cookie)
    import lab_reference_ranges as ranges

    items = ranges.list_ranges(query, status)
    return {
        "status": "ok",
        "items": items,
        "proposed": sum(1 for item in items if item.get("status") == "draft"),
        "pendingReview": sum(1 for item in items if item.get("status") == "pending_review"),
        "approved": sum(1 for item in items if item.get("status") == "approved"),
    }


def save_reference_range(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_lab_user(cookie)
    import lab_reference_ranges as ranges

    try:
        saved = ranges.apply_action(body, str(user.get("username") or ""))
    except ValueError as error:
        raise ApiError(422, "reference_range", str(error)) from error
    return {"status": "ok", "range": saved}


def save_lab_results(
    order_uuid: str,
    body: dict[str, Any],
    patient_uuid: str | None,
    cookie: str,
) -> dict[str, Any]:
    require_lab_user(cookie)
    def operation() -> dict[str, Any]:
        order = load_lab_order(order_uuid, patient_uuid or None, cookie)
        from openelis_adapter import OpenElisAdapter

        results = body.get("results") if isinstance(body.get("results"), list) else []
        import lab_reference_ranges as ranges

        for item in results:
            if isinstance(item, dict) and not _choice_result(item):
                ranges.apply_result_flag(item)
        accession = _resolve_accession(order, body)
        if not accession:
            raise ApiError(
                422,
                "accession_required",
                "Collect the sample before saving the result.",
            )
        _attach_missing_tests(accession, results)
        _record_order_accession(order, accession, cookie)
        result = OpenElisAdapter().save_results(
            accession=accession,
            results=results,
        )
        _store_request_results(order, cookie, results)
        workflow = build_lab_workflow(order_uuid, patient_uuid, "", cookie)
        workflow["message"] = "Results saved."
        workflow["adapter"] = result
        return workflow

    return _workflow_once("results", order_uuid, body, operation)


def validate_lab_results(
    order_uuid: str,
    body: dict[str, Any],
    patient_uuid: str | None,
    cookie: str,
) -> dict[str, Any]:
    require_lab_user(cookie)
    validator = signed_in_staff_name(cookie)

    def operation() -> dict[str, Any]:
        order = load_lab_order(order_uuid, patient_uuid or None, cookie)
        from openelis_adapter import OpenElisAdapter

        accession = _resolve_accession(order, body)
        if not accession:
            raise ApiError(
                422,
                "accession_required",
                "Collect the sample before validating the result.",
            )
        _record_order_accession(order, accession, cookie)
        submitted = body.get("results") if isinstance(body.get("results"), list) else []
        filled = [
            item
            for item in submitted
            if isinstance(item, dict)
            and str(item.get("resultLabel") or item.get("resultValue") or item.get("qualifiedResultValue") or "").strip()
        ]
        result = OpenElisAdapter().validate_results(
            accession=accession,
            test_section=str(body.get("testSection") or "All Sections"),
            test_name=str(body.get("testName") or order.get("testName") or ""),
            results=filled,
            decision=str(body.get("decision") or "accept"),
        )
        accepted = str(body.get("decision") or "accept") != "reject"
        if accepted and filled:
            _store_request_results(order, cookie, filled)
        workflow = build_lab_workflow(order_uuid, patient_uuid, "", cookie)
        if accepted:
            released_names = {
                str(item.get("testName") or item.get("orderedAs") or "").strip()
                for item in filled
            }
            released_names.update(
                str(item.get("orderedAs") or "").strip() for item in filled if isinstance(item, dict)
            )
            _remember_released_request(order, cookie, released_names, validator)
        workflow["validation"] = {
            "status": "validated" if accepted else "pending",
            "validatedBy": validator if accepted else validator_name_for_order(order, cookie),
        }
        workflow["message"] = "Results accepted and released." if accepted else "Results rejected. Correct them and submit again."
        workflow["adapter"] = result
        return workflow

    return _workflow_once("validate", order_uuid, body, operation)


def top_ordered_tests(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Ten laboratory tests ordered most often in the selected dates."""
    require_lab_user(cookie)
    import admin_analytics
    import openmrs_sql as clinical_sql

    window = admin_analytics._window_from_query(query or {})
    period = admin_analytics._period_payload(window)
    bounds = (LAB_ORDER_TYPE_NAME, window["utcStartNaive"], window["utcEndNaive"])
    dated = """
          AND ot.retired = 0
          AND ot.name = %s
          AND o.order_action <> 'DISCONTINUE'
          AND COALESCE(o.date_activated, o.date_created) >= %s
          AND COALESCE(o.date_activated, o.date_created) < %s
    """
    try:
        total = clinical_sql.fetch_int(
            f"""
            SELECT COUNT(*)
            FROM orders o
            JOIN order_type ot ON ot.order_type_id = o.order_type_id
            WHERE o.voided = 0
            {dated}
            """,
            bounds,
        )
        rows = clinical_sql.fetch_all(
            f"""
            SELECT cn.name, COUNT(*)
            FROM orders o
            JOIN order_type ot ON ot.order_type_id = o.order_type_id
            JOIN concept_name cn ON cn.concept_id = o.concept_id
              AND cn.voided = 0
              AND cn.locale = 'en'
              AND cn.concept_name_type = 'FULLY_SPECIFIED'
            WHERE o.voided = 0
            {dated}
            GROUP BY cn.name
            ORDER BY COUNT(*) DESC, cn.name
            LIMIT 10
            """,
            bounds,
        )
    except clinical_sql.OpenmrsSqlError:
        return {
            "status": "unavailable",
            "period": period,
            "total": None,
            "tests": [],
            "message": "Test totals could not be loaded. Try again in a moment.",
        }
    tests = [{"name": str(name or "Laboratory test"), "count": int(count or 0)} for name, count in rows]
    return {"status": "ok", "period": period, "total": total, "tests": tests}


def build_board(cookie: str) -> dict[str, Any]:
    require_lab_user(cookie)
    reader: OdooReader | None = None
    currency = dict(NGN_CURRENCY)
    try:
        reader = odoo_reader()
        currency = lab_currency(reader)
    except ApiError:
        reader = None
    uuids: list[str] = []
    seen_uuids: set[str] = set()

    def _add_uuids(items: list[str]) -> None:
        for uuid in items:
            if uuid and uuid not in seen_uuids:
                seen_uuids.add(uuid)
                uuids.append(uuid)

    # Unbilled doctor orders first. The order list itself cannot be searched
    # hospital-wide, and a bill is only created when the laboratory submits it.
    _add_uuids(_board_uuids_from_visits(cookie))
    _add_uuids(_board_uuids_from_openmrs(cookie))
    if reader:
        _add_uuids(_board_uuids_from_odoo(reader))
    _add_uuids(_board_uuids_from_external(cookie))
    loaded_orders = _load_board_orders(uuids, cookie)
    financials = (
        _order_financials_many(reader, loaded_orders, currency) if reader and loaded_orders else [{} for _ in loaded_orders]
    )
    orders: list[dict[str, Any]] = []
    result_cache: dict[str, set[str]] = {}
    accession_cache: dict[str, list[dict[str, Any]] | None] = {}
    encounter_orders: dict[str, list[dict[str, Any]]] = {}
    for order in loaded_orders:
        encounter_orders.setdefault(str(order.get("encounterUuid") or ""), []).append(order)
    patient_ids = []
    encounter_ids = []
    seen_patients: set[str] = set()
    seen_encounters: set[str] = set()
    for order in loaded_orders:
        patient_uuid = str(order.get("patientUuid") or "")
        encounter_uuid = str(order.get("encounterUuid") or "")
        if patient_uuid and patient_uuid not in seen_patients:
            seen_patients.add(patient_uuid)
            patient_ids.append(patient_uuid)
        if encounter_uuid and encounter_uuid not in seen_encounters:
            seen_encounters.add(encounter_uuid)
            encounter_ids.append(encounter_uuid)

    external_uuids: set[str] = set()
    try:
        import laboratory_external as external

        external.ensure_schema()
        for row in external._list_patient_rows():
            uuid = str(row.get("openmrs_uuid") or "").strip()
            if uuid:
                external_uuids.add(uuid)
    except Exception:
        external_uuids = set()

    def _results(patient_uuid: str) -> set[str]:
        try:
            return _result_order_uuids(patient_uuid, cookie)
        except ApiError:
            return set()

    def _accessions(encounter_uuid: str) -> list[dict[str, Any]] | None:
        try:
            return _accession_details(encounter_uuid)
        except ApiError:
            return None

    workers = min(8, max(len(patient_ids) + len(encounter_ids), 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        result_futures = {uuid: pool.submit(_results, uuid) for uuid in patient_ids}
        accession_futures = {uuid: pool.submit(_accessions, uuid) for uuid in encounter_ids}
    result_cache = {uuid: future.result() for uuid, future in result_futures.items()}
    accession_cache = {uuid: future.result() for uuid, future in accession_futures.items()}
    for order, financial in zip(loaded_orders, financials):
        patient_uuid = order.get("patientUuid") or ""
        encounter_uuid = str(order.get("encounterUuid") or "")
        is_unlisted = str(order.get("comment") or "").startswith(UNLISTED_LAB_MARKER)
        state = _laboratory_state(
            order,
            encounter_orders.get(encounter_uuid) or [order],
            accession_cache.get(encounter_uuid),
            result_cache.get(patient_uuid) or set(),
        )
        if is_unlisted:
            state = {
                **state,
                "stage": "pending",
                "laboratoryStatus": "Unlisted test requested",
                "statusMessage": "Review this requested test and add it to the laboratory catalogue before processing.",
                "resultMapping": "unique",
            }
        workflow_accession = WORKFLOW_ACCESSIONS.get(str(order.get("uuid") or ""))
        if workflow_accession and state.get("stage") == "pending":
            state = {
                **state,
                "stage": "processing",
                "laboratoryStatus": "Sample collected",
                "statusMessage": "Sample collected and ready for result entry.",
            }
        if not isinstance(financial, dict):
            financial = {}
        catalogue = lab_catalogue.entry_by_concept(order.get("conceptUuid") or "")
        comment = order.get("comment") or ""
        source = request_source_of(comment)
        patient_type, patient_type_label, is_external = _patient_type_bits(
            mrn=str(order.get("mrn") or ""),
            patient_uuid=patient_uuid,
            external_uuids=external_uuids,
        )
        orders.append(
            {
                "uuid": order["uuid"],
                "orderNumber": order.get("orderNumber") or "",
                "testName": order.get("testName") or "Laboratory test",
                "patientUuid": patient_uuid,
                "visitUuid": order.get("visitUuid") or "",
                "patientName": order.get("patientName") or "Unknown patient",
                "mrn": order.get("mrn") or "",
                "age": order.get("age") or "",
                "ordered": order.get("ordered") or "",
                "urgency": order.get("urgency") or "Routine",
                "accession": workflow_accession or order.get("accession") or "",
                "provider": order.get("provider") or "—",
                "comment": visible_comment(comment),
                "requestKey": order_request_key({**order, "comment": comment}),
                "requestSource": source,
                "requestSourceLabel": request_source_label(source),
                "patientType": patient_type,
                "patientTypeLabel": patient_type_label,
                "isExternal": is_external,
                "outsourced": bool(catalogue and catalogue.get("outsourced")),
                "encounterUuid": order.get("encounterUuid") or "",
                "conceptUuid": order.get("conceptUuid") or "",
                **_released_board_stage(str(order.get("uuid") or ""), state),
                "paymentStatus": financial.get("paymentStatus") or "UNPAID",
                "hasCharge": bool(financial.get("hasCharge")),
                "feeAmount": financial.get("feeAmount"),
            }
        )
    orders = _group_board_orders(orders)
    pending = [row for row in orders if row["stage"] == "pending"]
    processing = [row for row in orders if row["stage"] == "processing"]
    completed = [row for row in orders if row["stage"] == "completed"]
    unknown = [row for row in orders if row["stage"] == "unknown"]
    return {
        "status": "ok",
        "orders": orders,
        "pending": pending,
        "processing": processing,
        "completed": completed,
        "unknown": unknown,
        "openelisUrl": "/openelis",
        "processingNote": "Sample collection and result entry are done in the laboratory processing system.",
    }


def _open_consultation_on_visit(visit: dict[str, Any]) -> dict[str, str] | None:
    encounters = visit.get("encounters") or []
    matches = []
    for row in encounters:
        if not isinstance(row, dict):
            continue
        encounter_type = row.get("encounterType") if isinstance(row.get("encounterType"), dict) else {}
        if encounter_type.get("uuid") == CONSULTATION_ENCOUNTER_TYPE or encounter_type.get("name") == "Consultation":
            matches.append(row)
    matches.sort(key=lambda row: str(row.get("encounterDatetime") or ""), reverse=True)
    if not matches or not matches[0].get("uuid"):
        return None
    return {
        "uuid": str(matches[0]["uuid"]),
        "encounterDatetime": str(matches[0].get("encounterDatetime") or ""),
    }


def _guard_duplicate_test_order(
    concept_uuid: str,
    encounter_uuid: str,
    existing_orders: list[dict[str, Any]],
    requested_concepts: set[str],
) -> None:
    if concept_uuid in requested_concepts:
        raise ApiError(
            409,
            "duplicate_lab_test",
            "The same laboratory test cannot be ordered twice on one consultation.",
        )
    if encounter_uuid and any(
        str(row.get("encounterUuid") or "") == encounter_uuid
        and str(row.get("conceptUuid") or "") == concept_uuid
        for row in existing_orders
    ):
        raise ApiError(
            409,
            "duplicate_lab_test",
            "This test is already ordered on this consultation. "
            "Open the existing order instead of creating a duplicate.",
        )


def create_lab_orders(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_clinical_user(cookie)
    visit_uuid = ward.resolve_clinical_order_visit_uuid(
        patient_uuid,
        str(body.get("visitUuid") or ""),
        cookie,
        missing_visit_message="Start an open visit before ordering laboratory tests.",
    )
    location_uuid = str(body.get("locationUuid") or "").strip()
    encounter_uuid = str(body.get("encounterUuid") or "").strip()
    requested = body.get("tests")
    if not location_uuid:
        raise ApiError(422, "location_required", "A consulting location is required.")
    if not isinstance(requested, list) or not requested:
        raise ApiError(422, "tests_required", "Select at least one laboratory test.")
    if len(requested) > 20:
        raise ApiError(422, "too_many_tests", "Select fewer laboratory tests at a time.")

    visit = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}"
        "?v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),patient:(uuid),"
        "encounters:(uuid,encounterDatetime,encounterType:(uuid,name)))",
        cookie,
    )
    if not isinstance(visit, dict) or not visit.get("uuid"):
        raise ApiError(404, "visit_not_found", "This visit was not found.")
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    if patient.get("uuid") and patient.get("uuid") != patient_uuid:
        raise ApiError(409, "wrong_patient", "This visit does not belong to this patient.")
    if visit.get("stopDatetime"):
        if ward.inpatient_order_context(patient_uuid, cookie):
            raise ApiError(
                409,
                "visit_closed",
                "This admission is no longer open. Check the ward record before ordering.",
            )
        raise ApiError(409, "visit_closed", "This visit is closed. Start a new visit before ordering tests.")

    encounter_uuid = ward.encounter_on_resolved_visit(visit, encounter_uuid)
    existing = _open_consultation_on_visit(visit)
    if existing and not encounter_uuid:
        encounter_uuid = existing["uuid"]

    existing_orders = list_lab_orders(patient_uuid, cookie)
    before = {row["uuid"] for row in existing_orders}
    request_marker = new_request_marker()
    orders_payload: list[dict[str, Any]] = []
    unlisted_names: set[str] = set()
    seen_concepts: set[str] = set()
    for item in requested:
        if not isinstance(item, dict):
            continue
        concept_uuid = str(item.get("conceptUuid") or "").strip()
        unlisted = bool(item.get("unlisted"))
        name = str(item.get("name") or "").strip()
        if unlisted:
            if len(name) < 2:
                raise ApiError(422, "test_name_required", "Enter the unlisted laboratory test name.")
            if name.casefold() in unlisted_names:
                continue
            concept_uuid = UNLISTED_LAB_CONCEPT_UUID
            unlisted_names.add(name.casefold())
        if not concept_uuid:
            continue
        if not unlisted:
            _guard_duplicate_test_order(
                concept_uuid,
                encounter_uuid,
                existing_orders,
                seen_concepts,
            )
            catalogue = lab_catalogue.entry_by_concept(concept_uuid)
            if not catalogue or not catalogue.get("orderable"):
                raise ApiError(
                    422,
                    "not_orderable",
                    "One of the selected tests is not available to order.",
                )
            seen_concepts.add(concept_uuid)
        else:
            catalogue = None
        comment = str(item.get("comment") or "").strip()
        if unlisted:
            comment = f"{UNLISTED_LAB_MARKER}{name}"
        elif catalogue and catalogue.get("outsourced"):
            note = "Outsourced — send to the external laboratory."
            comment = f"{comment} {note}".strip() if comment else note
        name = (
            name
            if unlisted
            else catalogue.get("hospitalName") or catalogue.get("openmrsName") or name or "Laboratory test"
        )
        row: dict[str, Any] = {
            "concept": {"uuid": concept_uuid, "name": name},
            "commentToFulfiller": append_request_marker(comment, request_marker),
        }
        if not unlisted and str(item.get("urgency") or "").upper() == "STAT" and not catalogue.get("notStat"):
            row["urgency"] = "STAT"
        orders_payload.append(row)
    if not orders_payload:
        raise ApiError(422, "tests_required", "Select at least one laboratory test.")

    provider = _provider_uuid(str(user.get("uuid") or ""), cookie)
    visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
    payload: dict[str, Any] = {
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "visitType": visit_type.get("name") or "OPD",
        "encounterTypeUuid": CONSULTATION_ENCOUNTER_TYPE,
        "encounterDateTime": (existing or {}).get("encounterDatetime") or now_openmrs(),
        "locationUuid": location_uuid,
        "providers": [{"uuid": provider}],
        "observations": [],
        "bahmniDiagnoses": [],
        "orders": orders_payload,
        "drugOrders": [],
    }
    if encounter_uuid:
        payload["encounterUuid"] = encounter_uuid
    saved = _openmrs_post("/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", cookie, payload)
    saved_encounter = str(saved.get("encounterUuid") or encounter_uuid or "")
    after = list_lab_orders(patient_uuid, cookie)
    created = [row for row in after if row["uuid"] not in before]
    return {
        "status": "ok",
        "encounterUuid": saved_encounter,
        "orders": created,
        "message": (
            "Laboratory order saved. The unlisted test was sent to the laboratory for review."
            if unlisted_names
            else "Laboratory order saved. The laboratory submits the bill."
        ),
        "charge": None,
        "chargeError": None,
    }


def _normalize_direct_request_source(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"external_referral", "external", "referral", "outside"}:
        return SOURCE_EXTERNAL_REFERRAL
    if text in {"laboratory_direct", "lab_direct", "direct", "desk", ""}:
        return SOURCE_LABORATORY_DIRECT
    if text in {"doctor_order", "doctor"}:
        return SOURCE_LABORATORY_DIRECT
    return SOURCE_LABORATORY_DIRECT


def create_lab_direct_orders(patient_uuid: str, body: dict[str, Any], cookie: str, user: dict[str, Any] | None = None) -> dict[str, Any]:
    """Laboratory desk-initiated orders. Real Lab Order — not a forged doctor order."""
    actor = user or require_lab_user(cookie)
    visit_uuid = str(body.get("visitUuid") or "").strip()
    location_uuid = str(body.get("locationUuid") or "").strip()
    encounter_uuid = str(body.get("encounterUuid") or "").strip()
    requested = body.get("tests")
    request_source = _normalize_direct_request_source(str(body.get("requestSource") or ""))
    note = str(body.get("comment") or body.get("indication") or body.get("clinicalIndication") or "").strip()
    if not visit_uuid:
        raise ApiError(
            422,
            "visit_required",
            "Start an open visit for this patient before ordering laboratory tests.",
        )
    if not location_uuid:
        raise ApiError(422, "location_required", "A hospital location is required.")
    if not isinstance(requested, list) or not requested:
        raise ApiError(422, "tests_required", "Select at least one laboratory test.")
    if len(requested) > 20:
        raise ApiError(422, "too_many_tests", "Select fewer laboratory tests at a time.")

    visit = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{quote(visit_uuid)}"
        "?v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),patient:(uuid),"
        "encounters:(uuid,encounterDatetime,encounterType:(uuid,name)))",
        cookie,
    )
    if not isinstance(visit, dict) or not visit.get("uuid"):
        raise ApiError(404, "visit_not_found", "This visit was not found.")
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    if patient.get("uuid") and patient.get("uuid") != patient_uuid:
        raise ApiError(409, "wrong_patient", "This visit does not belong to this patient.")
    encounter_uuid = ward.encounter_on_resolved_visit(visit, encounter_uuid)
    existing = _open_consultation_on_visit(visit)
    if existing and not encounter_uuid:
        encounter_uuid = existing["uuid"]

    marker_comment = direct_order_comment(note, source=request_source)
    existing_orders = list_lab_orders(patient_uuid, cookie)
    before = {row["uuid"] for row in existing_orders}
    request_marker = new_request_marker()
    orders_payload: list[dict[str, Any]] = []
    seen_concepts: set[str] = set()
    for item in requested:
        if not isinstance(item, dict):
            continue
        concept_uuid = str(item.get("conceptUuid") or "").strip()
        if not concept_uuid:
            continue
        _guard_duplicate_test_order(
            concept_uuid,
            encounter_uuid,
            existing_orders,
            seen_concepts,
        )
        catalogue = lab_catalogue.entry_by_concept(concept_uuid)
        if not catalogue or not catalogue.get("orderable"):
            raise ApiError(
                422,
                "not_orderable",
                "One of the selected tests is not available to order.",
            )
        seen_concepts.add(concept_uuid)
        item_comment = str(item.get("comment") or "").strip()
        if catalogue.get("outsourced"):
            outsourced_note = "Outsourced — send to the external laboratory."
            item_comment = f"{item_comment} {outsourced_note}".strip() if item_comment else outsourced_note
        if item_comment and not item_comment.startswith(DIRECT_SOURCE_MARKER) and not item_comment.startswith(
            EXTERNAL_REFERRAL_MARKER
        ):
            comment = direct_order_comment(item_comment, source=request_source)
        elif item_comment:
            comment = item_comment
        else:
            comment = marker_comment
        name = catalogue.get("hospitalName") or catalogue.get("openmrsName") or str(item.get("name") or "Laboratory test")
        row: dict[str, Any] = {
            "concept": {"uuid": concept_uuid, "name": name},
            "commentToFulfiller": append_request_marker(comment, request_marker),
        }
        if str(item.get("urgency") or "").upper() == "STAT" and not catalogue.get("notStat"):
            row["urgency"] = "STAT"
        orders_payload.append(row)
    if not orders_payload:
        raise ApiError(422, "tests_required", "Select at least one laboratory test.")

    try:
        provider = _provider_uuid(str(actor.get("uuid") or ""), cookie)
    except ApiError as error:
        if error.code == "provider_missing":
            raise ApiError(
                409,
                "provider_missing",
                "This Laboratory account is not set up to create laboratory orders yet.",
            ) from error
        raise
    visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
    payload: dict[str, Any] = {
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "visitType": visit_type.get("name") or "OPD",
        "encounterTypeUuid": CONSULTATION_ENCOUNTER_TYPE,
        "encounterDateTime": _direct_encounter_time(visit, existing),
        "locationUuid": location_uuid,
        "providers": [{"uuid": provider}],
        "observations": [],
        "bahmniDiagnoses": [],
        "orders": orders_payload,
        "drugOrders": [],
    }
    if encounter_uuid:
        payload["encounterUuid"] = encounter_uuid
    saved = _clinical_write_post("/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", cookie, payload)
    saved_encounter = str(saved.get("encounterUuid") or encounter_uuid or "")
    after = list_lab_orders(patient_uuid, cookie)
    created = [row for row in after if row["uuid"] not in before]
    for row in created:
        row["requestSource"] = request_source
        row["requestSourceLabel"] = request_source_label(request_source)

    return {
        "status": "ok",
        "encounterUuid": saved_encounter,
        "visitUuid": visit_uuid,
        "orders": created,
        "requestSource": request_source,
        "requestSourceLabel": request_source_label(request_source),
        "message": "Laboratory order created. Submit the bill when you are ready.",
        "charge": None,
        "chargeError": None,
    }


def build_laboratory_history(cookie: str, raw_path: str = "") -> dict[str, Any]:
    """Paginated laboratory history for the Laboratory desk. Reuses board rows."""
    from urllib.parse import parse_qs

    require_lab_user(cookie)
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "", keep_blank_values=True)

    def first(key: str, default: str = "") -> str:
        values = query.get(key) or []
        return str(values[0] if values else default).strip()

    try:
        limit = min(max(int(first("limit", str(HISTORY_DEFAULT_LIMIT))), 1), HISTORY_MAX_LIMIT)
    except ValueError:
        limit = HISTORY_DEFAULT_LIMIT
    try:
        offset = max(int(first("offset", "0")), 0)
    except ValueError:
        offset = 0
    q = first("q").lower()
    source_filter = first("requestSource") or first("source")
    if source_filter in {"direct", "lab", "laboratory", "laboratory_direct", "Laboratory Direct", "Lab Direct"}:
        source_filter = SOURCE_LABORATORY_DIRECT
    elif source_filter in {"doctor", "doctor_order", "Doctor Order"}:
        source_filter = SOURCE_DOCTOR_ORDER
    elif source_filter in {
        "external_referral",
        "external",
        "referral",
        "External Referral",
    }:
        source_filter = SOURCE_EXTERNAL_REFERRAL
    else:
        source_filter = (
            source_filter
            if source_filter
            in {SOURCE_DOCTOR_ORDER, SOURCE_LABORATORY_DIRECT, SOURCE_EXTERNAL_REFERRAL}
            else ""
        )
    patient_type_filter = (first("patientType") or first("type")).lower()
    if patient_type_filter in {"external", "external_patient"}:
        patient_type_filter = "external"
    elif patient_type_filter in {"registered", "registered_patient"}:
        patient_type_filter = "registered"
    else:
        patient_type_filter = ""
    stage_filter = (first("stage") or first("status")).lower()
    date_from = first("from") or first("start")
    date_to = first("to") or first("end")

    payload = build_board(cookie)
    rows = list(payload.get("orders") or [])

    def ordered_day(value: str) -> str:
        text = str(value or "")
        return text[:10] if len(text) >= 10 else text

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if source_filter and row.get("requestSource") != source_filter:
            continue
        if patient_type_filter:
            row_type = (
                "external"
                if row.get("isExternal") or row.get("patientType") == "external"
                else "registered"
            )
            if row_type != patient_type_filter:
                continue
        if stage_filter and str(row.get("stage") or "").lower() != stage_filter:
            continue
        day = ordered_day(str(row.get("ordered") or ""))
        if date_from and day and day < date_from:
            continue
        if date_to and day and day > date_to:
            continue
        if q:
            haystack = " ".join(
                [
                    str(row.get("patientName") or ""),
                    str(row.get("mrn") or ""),
                    str(row.get("testName") or ""),
                    str(row.get("orderNumber") or ""),
                    str(row.get("requestSourceLabel") or ""),
                    str(row.get("uuid") or ""),
                    str(row.get("patientTypeLabel") or ""),
                ]
            ).lower()
            if q not in haystack:
                continue
        filtered.append(row)

    total = len(filtered)
    page = filtered[offset : offset + limit]
    return {
        "status": "ok",
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
    }
