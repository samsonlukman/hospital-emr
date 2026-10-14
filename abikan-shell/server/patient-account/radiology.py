"""Radiology orders and order-specific fees.

Doctor orders use the existing Consultation encounter write. The Radiologist
sets the NGN amount for that order. Payment stays on the Accountant path.
Idempotency key is radiology:{orderUuid}. The isolated ORD-6 TEST product is
never used as a universal price.
"""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import radiology_menu
import xmlrpc.client

import inpatient as ward
import server as core

RADIOLOGY_PRIVILEGE = "app:radiology-upload"
CLINICAL_PRIVILEGE = "app:clinical"
RADIOLOGY_ROLES = {"SuperAdmin", "System Developer"}
SHOP_NAME = "Radiology Desk"
CATEGORY_NAME = "Radiology"
PRICELIST_NAME = "Radiology Desk"
EXTERNAL_PREFIX = "radiology:"
RADIOLOGY_ORDER_TYPE_UUID = "d3561dc0-5e07-11ef-8f7c-0242ac120002"
RADIOLOGY_ORDER_TYPE_NAME = "Radiology Order"
CONSULTATION_ENCOUNTER_TYPE = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
RADIOLOGY_ENCOUNTER_TYPE = "d3a89c59-5e07-11ef-8f7c-0242ac120002"
RADIOLOGY_NOTES_CONCEPT_UUID = "ae6e5490-ade9-486e-8268-9e4efd45b07e"
DIRECT_SOURCE_MARKER = "[Radiology Direct]"
SOURCE_DOCTOR_ORDER = "doctor_order"
SOURCE_RADIOLOGY_DIRECT = "radiology_direct"
WORKLIST_PAGE_SIZE = 50
# Runaway guard only. Not a clinical date window.
WORKLIST_PAGE_CAP = 2000
WORKLIST_VISIT_REPRESENTATION = (
    "custom:(uuid,startDatetime,"
    "visitType:(name),"
    "patient:(uuid,display,identifiers:(identifier,preferred)),"
    "attributes:(value,display,attributeType:(uuid,name)),"
    "encounters:(uuid,encounterType:(uuid,name),"
    "obs:(uuid,voided,value,concept:(uuid),order:(uuid)),"
    "orders:(uuid,voided,orderNumber,dateActivated,dateCreated,urgency,commentToFulfiller,"
    "orderType:(uuid,display),concept:(uuid,display),orderer:(display))))"
)
HISTORY_DEFAULT_LIMIT = 25
HISTORY_MAX_LIMIT = 100
PLACEHOLDER_PRICE = 1.01
MAX_RADIOLOGY_AMOUNT = 10_000_000
NGN_CURRENCY = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}

# Isolated TEST product. Do not modify it. Do not use it for new charges.
TEST_CONCEPT_UUID = "165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
TEST_PRODUCT_NAME = "Chest x-ray, single view — TEST"
TEST_LIST_PRICE = 60.0

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


def is_radiology_user(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & RADIOLOGY_ROLES) or RADIOLOGY_PRIVILEGE in privileges


def is_clinical_user(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & RADIOLOGY_ROLES) or CLINICAL_PRIVILEGE in privileges


def require_radiology_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_radiology_user(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires the Radiology workspace.",
        )
    return user


def request_source_of(
    *,
    encounter_type_uuid: str = "",
    comment: str = "",
) -> str:
    text = str(comment or "")
    if str(encounter_type_uuid or "") == RADIOLOGY_ENCOUNTER_TYPE:
        return SOURCE_RADIOLOGY_DIRECT
    if text.startswith(DIRECT_SOURCE_MARKER) or text.startswith("Radiology Direct"):
        return SOURCE_RADIOLOGY_DIRECT
    return SOURCE_DOCTOR_ORDER


def request_source_label(source: str) -> str:
    if source == SOURCE_RADIOLOGY_DIRECT:
        return "Radiology Direct"
    if source == "external_referral":
        return "External Referral"
    return "Doctor Order"


def clinical_indication_text(comment: str) -> str:
    text = str(comment or "").strip()
    for prefix in (DIRECT_SOURCE_MARKER, "Radiology Direct:", "Radiology Direct"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip(" :-")
    return text


def direct_study_comment(indication: str) -> str:
    note = " ".join(str(indication or "").split()).strip()
    if note:
        return f"{DIRECT_SOURCE_MARKER} {note}"
    return DIRECT_SOURCE_MARKER


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


def require_clinical_or_radiology_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_radiology_user(user) and not is_clinical_user(user):
        raise ApiError(
            403,
            "forbidden",
            "This action is not available in this department.",
        )
    return user


def now_openmrs() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def parse_radiology_amount(value: Any) -> float:
    if value is None:
        raise ApiError(422, "amount_required", "Enter the imaging fee in naira.")
    if isinstance(value, bool):
        raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
        amount = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ApiError(422, "amount_required", "Enter the imaging fee in naira.")
        if re.search(r"[$€£]|USD|EUR|GBP", text, flags=re.I):
            raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
        text = re.sub(r"^(NGN|₦)\s*", "", text, flags=re.I)
        if re.search(r"[^\d,.\s]", text):
            raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
        compact = text.replace(",", "").replace(" ", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", compact):
            raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
        amount = float(compact)
    else:
        raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
    if amount <= 0:
        raise ApiError(422, "amount_invalid", "Imaging fee must be greater than zero.")
    if amount > MAX_RADIOLOGY_AMOUNT:
        raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")
    return round(amount, 2)


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
    currency_id = int(rows[0]["id"])
    if not rows[0].get("active"):
        execute(odoo, "res.currency", "write", [[currency_id], {"active": True}])
    return currency_id


def radiology_currency(odoo: OdooReader, currency_id: int | None = None) -> dict[str, Any]:
    if currency_id:
        loaded = load_currency(odoo, currency_id)
        if (loaded.get("code") or "").upper() == "NGN":
            return {**loaded, "code": "NGN", "symbol": "₦", "position": "before"}
        return loaded
    ngn_id = _ngn_currency_id(odoo)
    if ngn_id:
        loaded = load_currency(odoo, ngn_id)
        return {**loaded, "code": "NGN", "symbol": "₦", "position": "before"}
    return dict(NGN_CURRENCY)


def _openmrs_json(path: str, cookie: str, timeout: int = 20) -> dict[str, Any] | list[Any] | None:
    request = Request(
        f"{core.OPENMRS_URL}{path}",
        headers={"Accept": "application/json", "Cookie": cookie},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 404:
            return None
        raise ApiError(502, "openmrs_error", "The radiology record could not be loaded.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The radiology record could not be loaded.") from error


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
        detail = ""
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = ""
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 403 or "privileges" in detail.lower() or "privilege" in detail.lower():
            raise ApiError(
                403,
                "forbidden",
                "This Radiology account cannot create imaging studies yet. Ask Hospital Administration to allow ordering for Radiology.",
            ) from error
        raise ApiError(502, "openmrs_error", "The imaging order could not be saved.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The imaging order could not be saved.") from error


def _provider_uuid(user_uuid: str, cookie: str) -> str:
    payload = _openmrs_json(
        f"/openmrs/ws/rest/v1/provider?user={quote(user_uuid)}&v=custom:(uuid,retired)",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if isinstance(row, dict) and row.get("uuid") and not row.get("retired"):
            return str(row["uuid"])
    raise ApiError(409, "provider_missing", "This account is not set up as a clinician.")


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


def _map_bahmni_order_row(row: dict[str, Any], patient_uuid: str) -> dict[str, Any] | None:
    """Map bahmnicore/orders. Radiology staff can read this without Get Orders."""
    order_uuid = str(row.get("uuid") or row.get("orderUuid") or "").strip()
    concept = row.get("concept") if isinstance(row.get("concept"), dict) else {}
    concept_uuid = str(concept.get("uuid") or "").strip()
    if not order_uuid or not concept_uuid:
        return None
    order_date = row.get("orderDate") or row.get("dateActivated") or row.get("dateCreated") or ""
    if isinstance(order_date, (int, float)):
        ordered = datetime.fromtimestamp(float(order_date) / 1000.0, tz=timezone.utc).isoformat()
    else:
        ordered = str(order_date or "")
    return {
        "uuid": order_uuid,
        "orderNumber": row.get("orderNumber") or "",
        "testName": radiology_menu.hospital_name(
            concept_uuid,
            concept.get("name") or concept.get("shortName") or "Imaging examination",
        ),
        "conceptUuid": concept_uuid,
        "patientUuid": patient_uuid,
        "visitUuid": "",
        "encounterUuid": "",
        "urgency": "STAT" if row.get("urgency") == "STAT" else (row.get("urgency") or "Routine"),
        "accession": row.get("accessionNumber") or "",
        "ordered": ordered,
        "provider": _named(row.get("provider")) or "—",
    }


def _visit_order_bindings(patient_uuid: str, cookie: str) -> dict[str, tuple[str, str]]:
    """orderUuid → (visitUuid, encounterUuid) using Get Visits. Does not require Get Orders."""
    payload = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit?patient={quote(patient_uuid)}"
        "&v=custom:(uuid,encounters:(uuid,orders:(uuid)))&limit=50",
        cookie,
    )
    visits = payload.get("results") if isinstance(payload, dict) else payload
    bindings: dict[str, tuple[str, str]] = {}
    if not isinstance(visits, list):
        return bindings
    for visit in visits:
        if not isinstance(visit, dict) or not visit.get("uuid"):
            continue
        visit_uuid = str(visit["uuid"])
        for encounter in visit.get("encounters") or []:
            if not isinstance(encounter, dict):
                continue
            encounter_uuid = str(encounter.get("uuid") or "")
            for order in encounter.get("orders") or []:
                if not isinstance(order, dict) or not order.get("uuid"):
                    continue
                bindings[str(order["uuid"])] = (visit_uuid, encounter_uuid)
    return bindings


def load_radiology_order(order_uuid: str, patient_uuid: str | None, cookie: str) -> dict[str, Any]:
    order = _openmrs_json(
        f"/openmrs/ws/rest/v1/order/{order_uuid}"
        "?v=custom:(uuid,orderNumber,dateActivated,dateCreated,urgency,commentToFulfiller,"
        "accessionNumber,voided,action,patient:(uuid,display),encounter:(uuid,encounterType:(uuid,display),visit:(uuid)),"
        "concept:(uuid,display),orderType:(uuid,display),orderer:(display))",
        cookie,
    )
    if not isinstance(order, dict) or not order.get("uuid") or order.get("voided"):
        raise ApiError(404, "order_not_found", "This imaging request was not found.")
    order_type = order.get("orderType") if isinstance(order.get("orderType"), dict) else {}
    type_uuid = order_type.get("uuid") or ""
    type_name = order_type.get("display") or order_type.get("name") or ""
    if type_uuid != RADIOLOGY_ORDER_TYPE_UUID and type_name != RADIOLOGY_ORDER_TYPE_NAME:
        raise ApiError(422, "not_radiology_order", "That record is not a radiology order.")
    patient = order.get("patient") if isinstance(order.get("patient"), dict) else {}
    found_patient = patient.get("uuid") or ""
    if patient_uuid and found_patient != patient_uuid:
        raise ApiError(409, "wrong_patient", "This imaging request does not belong to this patient.")
    encounter = order.get("encounter") if isinstance(order.get("encounter"), dict) else {}
    encounter_type = encounter.get("encounterType") if isinstance(encounter.get("encounterType"), dict) else {}
    visit = encounter.get("visit") if isinstance(encounter.get("visit"), dict) else {}
    concept = order.get("concept") if isinstance(order.get("concept"), dict) else {}
    concept_uuid = concept.get("uuid") or ""
    if not concept_uuid:
        raise ApiError(
            409,
            "missing_test",
            "This imaging request has no procedure identifier, so a fee cannot be created.",
        )
    comment = str(order.get("commentToFulfiller") or "")
    encounter_type_uuid = str(encounter_type.get("uuid") or "")
    source = request_source_of(encounter_type_uuid=encounter_type_uuid, comment=comment)
    return {
        "uuid": order.get("uuid"),
        "orderNumber": order.get("orderNumber") or "",
        "testName": radiology_menu.hospital_name(concept_uuid, concept.get("display") or "Imaging examination"),
        "conceptUuid": concept_uuid,
        "patientUuid": found_patient,
        "visitUuid": visit.get("uuid") or "",
        "encounterUuid": encounter.get("uuid") or "",
        "encounterTypeUuid": encounter_type_uuid,
        "urgency": "STAT" if order.get("urgency") == "STAT" else (order.get("urgency") or "Routine"),
        "accession": order.get("accessionNumber") or "",
        "ordered": order.get("dateActivated") or order.get("dateCreated") or "",
        "provider": _named(order.get("orderer")) or "—",
        "comment": comment,
        "clinicalIndication": clinical_indication_text(comment),
        "requestSource": source,
        "requestSourceLabel": request_source_label(source),
    }


def list_radiology_orders(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    payload = _openmrs_json(
        f"/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={patient_uuid}"
        f"&orderTypeUuid={RADIOLOGY_ORDER_TYPE_UUID}",
        cookie,
    )
    rows = payload if isinstance(payload, list) else (payload.get("results") if isinstance(payload, dict) else [])
    if not isinstance(rows, list):
        return []
    orders: list[dict[str, Any]] = []
    seen: set[str] = set()
    bindings: dict[str, tuple[str, str]] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_uuid = str(row.get("uuid") or row.get("orderUuid") or "").strip()
        if not order_uuid or order_uuid in seen:
            continue
        seen.add(order_uuid)
        try:
            orders.append(load_radiology_order(order_uuid, patient_uuid, cookie))
            continue
        except ApiError:
            mapped = _map_bahmni_order_row(row, patient_uuid)
            if not mapped:
                continue
        if bindings is None:
            try:
                bindings = _visit_order_bindings(patient_uuid, cookie)
            except ApiError:
                bindings = {}
        visit_uuid, encounter_uuid = bindings.get(order_uuid, ("", ""))
        mapped["visitUuid"] = visit_uuid
        mapped["encounterUuid"] = encounter_uuid
        orders.append(mapped)
    return orders


def ensure_radiology_masters(odoo: OdooReader) -> dict[str, Any]:
    """Idempotent TEST shop/category/product. Does not change catalogue radiology products."""
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


def find_radiology_product(odoo: OdooReader, concept_uuid: str) -> dict[str, Any]:
    """Catalogue product for the concept. Never use the isolated TEST $60 product."""
    found = odoo.search_read(
        "product.product",
        [("uuid", "=", concept_uuid), ("type", "=", "service")],
        ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "uuid", "default_code", "categ_id"],
        limit=2,
    )
    for product in found:
        name = str(product.get("name") or "")
        if TEST_PRODUCT_NAME in name:
            continue
        return product
    raise ApiError(
        409,
        "missing_mapping",
        "This imaging examination is not available to bill yet.",
    )


def ensure_radiology_ngn_pricelist(odoo: OdooReader, shop: dict[str, Any]) -> dict[str, Any]:
    ngn_id = _ngn_currency_id(odoo)
    if not ngn_id:
        raise ApiError(
            409,
            "missing_currency",
            "Naira is not available for this imaging fee.",
        )
    pricelists = odoo.search_read(
        "product.pricelist",
        [("name", "=", PRICELIST_NAME)],
        ["id", "name", "currency_id"],
        limit=1,
    )
    if pricelists:
        pricelist_id = int(pricelists[0]["id"])
        if many2one_id(pricelists[0].get("currency_id")) != ngn_id:
            execute(odoo, "product.pricelist", "write", [[pricelist_id], {"currency_id": ngn_id}])
    else:
        pricelist_id = int(
            execute(
                odoo,
                "product.pricelist",
                "create",
                [{"name": PRICELIST_NAME, "currency_id": ngn_id}],
            )
        )
    if many2one_id(shop.get("pricelist_id")) != pricelist_id:
        execute(odoo, "sale.shop", "write", [[int(shop["id"])], {"pricelist_id": pricelist_id}])
        shop = odoo.read(
            "sale.shop",
            [int(shop["id"])],
            ["name", "warehouse_id", "pricelist_id", "payment_default_id"],
        )[0]
    shop["pricelist_id"] = [pricelist_id, PRICELIST_NAME]
    return shop


def _radiology_pricelist_id(shop: dict[str, Any]) -> int:
    raw = shop.get("pricelist_id")
    pricelist_id = many2one_id(raw)
    if pricelist_id is None and isinstance(raw, int):
        pricelist_id = raw
    if not pricelist_id:
        raise ApiError(
            409,
            "missing_pricelist",
            "The imaging desk is not ready to set a fee.",
        )
    return int(pricelist_id)


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


def invoice_payment_status(invoice: dict[str, Any] | None, has_charge: bool) -> str:
    if not has_charge:
        return "UNPAID"
    if invoice_paid(invoice):
        return "PAID"
    if invoice and invoice.get("payment_state") == "partial":
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
    status = invoice_payment_status(invoice, has_charge)
    amount = 0.0
    if invoice:
        amount = as_float(invoice.get("amount_total"))
    elif sale:
        amount = as_float(sale.get("amount_total"))
    if status == "PAID":
        billing = "Paid"
    elif status == "PARTIALLY PAID":
        billing = "Partially paid"
    elif has_charge:
        billing = "Unpaid"
    else:
        billing = "Price pending"
    return {
        "orderUuid": order["uuid"],
        "orderNumber": order.get("orderNumber") or "",
        "examinationName": order.get("testName") or "Imaging examination",
        "visitUuid": order.get("visitUuid") or "",
        "encounterUuid": order.get("encounterUuid") or "",
        "feeName": order.get("testName") or (product or {}).get("name"),
        "feeAmount": format_money(amount, currency) if has_charge else format_money(0.0, currency),
        "paymentStatus": status if has_charge else "UNPAID",
        "billingStatus": billing,
        "hasCharge": has_charge,
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
    if existing:
        product_id = many2one_id(existing[0].get("product_id"))
        if product_id:
            rows = odoo.read("product.product", [product_id], ["name", "list_price"])
            product = rows[0] if rows else None
        if product is None:
            product = {"name": order.get("testName"), "list_price": as_float(existing[0].get("price_unit"))}
    else:
        try:
            product = find_radiology_product(odoo, order["conceptUuid"])
        except ApiError:
            product = None
    currency_id = many2one_id((invoice or sale or {}).get("currency_id"))
    display_currency = radiology_currency(odoo, currency_id if existing else None)
    row = serialize_order_charge(order, product, sale, invoice, display_currency)
    if existing:
        row["hasCharge"] = True
        row["paymentStatus"] = invoice_payment_status(invoice, True)
        if invoice:
            row["outstanding"] = format_money(as_float(invoice.get("amount_residual")), display_currency)
            row["tax"] = format_money(as_float(invoice.get("amount_tax")), display_currency)
    return row


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
    ensure_radiology_masters(reader)
    currency = radiology_currency(reader)
    partner = find_partner(reader, patient)
    orders = list_radiology_orders(patient_uuid, cookie)
    items = [_order_financials(reader, order, currency) for order in orders]
    billed = [item for item in items if item.get("hasCharge")]
    unbilled = [item for item in items if not item.get("hasCharge")]
    mappable = 0
    mapping_error = None
    for order in orders:
        if find_existing_sale(reader, order["uuid"]):
            continue
        try:
            find_radiology_product(reader, order["conceptUuid"])
            mappable += 1
        except ApiError as error:
            if mapping_error is None:
                mapping_error = error.message
    paid_all = bool(billed) and all(item.get("paymentStatus") == "PAID" for item in billed)
    partial_any = any(item.get("paymentStatus") == "PARTIALLY PAID" for item in billed)
    unpaid_any = any(item.get("paymentStatus") == "UNPAID" and item.get("hasCharge") for item in items)
    if paid_all and not unbilled:
        payment_status = "PAID"
    elif partial_any:
        payment_status = "PARTIALLY PAID"
    elif billed or unbilled:
        payment_status = "UNPAID" if (unpaid_any or unbilled) else "PAID"
    else:
        payment_status = "UNPAID"
    can_create = bool(partner) and mappable > 0
    reason = None
    if not partner:
        reason = "This patient has no financial account yet. Try again in a moment."
        can_create = False
    elif not orders:
        reason = "No imaging requests on this chart yet."
    elif unbilled and mappable == 0:
        reason = mapping_error or "Enter the imaging fee for this request."
    elif unbilled:
        reason = None
    elif unpaid_any or partial_any:
        reason = "Please proceed to the cashier for payment."
    total = sum(as_float(item["feeAmount"]["amount"]) for item in items) if items else 0.0
    outstanding = 0.0
    for item in billed:
        if item.get("paymentStatus") != "PAID":
            outstanding += as_float((item.get("outstanding") or item.get("feeAmount") or {}).get("amount"))
    return {
        "status": "ok",
        "patient": patient,
        "examinations": items,
        "feeAmount": format_money(total, currency),
        "paymentStatus": payment_status,
        "hasCharge": bool(billed),
        "canCreateCharge": can_create,
        "blockReason": reason,
        "partnerFound": bool(partner),
        "outstanding": format_money(outstanding, currency),
        "message": None,
    }


def build_radiology(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_clinical_or_radiology_user(cookie)
    return _charge_payload(cookie, patient_uuid)


def _preferred_mrn(identifiers: Any) -> str:
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
    return next(
        (
            str(item.get("identifier") or "").strip()
            for item in rows
            if isinstance(item, dict) and item.get("identifier")
        ),
        "",
    )


def _name_and_mrn(display: Any, identifiers: Any) -> tuple[str, str]:
    raw = str(display or "").strip()
    mrn = _preferred_mrn(identifiers)
    if " - " in raw:
        left, right = raw.split(" - ", 1)
        if left.strip().upper().startswith("ABC") or (mrn and left.strip() == mrn):
            return right.strip() or "Unknown patient", left.strip() or mrn
        if mrn and right.strip() == mrn:
            return left.strip() or "Unknown patient", mrn
        return right.strip() or "Unknown patient", left.strip() or mrn
    return raw or "Unknown patient", mrn


def _load_worklist_visits(cookie: str) -> list[dict[str, Any]]:
    """All visits, newest or oldest. Pagination only — no 30-day cutoff."""
    rows: list[dict[str, Any]] = []
    start_index = 0
    while start_index < WORKLIST_PAGE_CAP:
        payload = _openmrs_json(
            f"/openmrs/ws/rest/v1/visit?includeInactive=true"
            f"&limit={WORKLIST_PAGE_SIZE}"
            f"&startIndex={start_index}"
            f"&v={WORKLIST_VISIT_REPRESENTATION}",
            cookie,
            timeout=40,
        )
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list) or not results:
            break
        for item in results:
            if isinstance(item, dict) and item.get("uuid"):
                rows.append(item)
        if len(results) < WORKLIST_PAGE_SIZE:
            break
        start_index += len(results)
    return rows


def _is_radiology_order_type(order: dict[str, Any]) -> bool:
    order_type = order.get("orderType") if isinstance(order.get("orderType"), dict) else {}
    type_uuid = order_type.get("uuid") or ""
    type_name = order_type.get("display") or order_type.get("name") or ""
    return type_uuid == RADIOLOGY_ORDER_TYPE_UUID or type_name == RADIOLOGY_ORDER_TYPE_NAME


def _note_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display") or value.get("value") or "").strip()
    return str(value or "").strip()


def _worklist_notes(visits: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for visit in visits:
        visit_uuid = str(visit.get("uuid") or "")
        patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
        patient_uuid = str(patient.get("uuid") or "")
        if not visit_uuid or not patient_uuid:
            continue
        for encounter in visit.get("encounters") or []:
            if not isinstance(encounter, dict):
                continue
            for obs in encounter.get("obs") or []:
                if not isinstance(obs, dict) or obs.get("voided"):
                    continue
                concept = obs.get("concept") if isinstance(obs.get("concept"), dict) else {}
                if (concept.get("uuid") or "") != RADIOLOGY_NOTES_CONCEPT_UUID:
                    continue
                if not _note_value(obs.get("value")):
                    continue
                order = obs.get("order") if isinstance(obs.get("order"), dict) else {}
                order_uuid = str(order.get("uuid") or "")
                if order_uuid:
                    found.add((patient_uuid, visit_uuid, order_uuid))
    return found


def _worklist_orders_from_visits(visits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import daily_visit_number as daily

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for visit in visits:
        visit_uuid = str(visit.get("uuid") or "")
        visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
        patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
        patient_uuid = str(patient.get("uuid") or "")
        if not visit_uuid or not patient_uuid:
            continue
        name, mrn = _name_and_mrn(patient.get("display"), patient.get("identifiers"))
        daily_no = daily.daily_visit_number_from_visit(visit)
        for encounter in visit.get("encounters") or []:
            if not isinstance(encounter, dict):
                continue
            encounter_uuid = str(encounter.get("uuid") or "")
            encounter_type = encounter.get("encounterType") if isinstance(encounter.get("encounterType"), dict) else {}
            encounter_type_uuid = str(encounter_type.get("uuid") or "")
            for order in encounter.get("orders") or []:
                if not isinstance(order, dict) or order.get("voided") or not order.get("uuid"):
                    continue
                if not _is_radiology_order_type(order):
                    continue
                order_uuid = str(order["uuid"])
                if order_uuid in seen:
                    continue
                seen.add(order_uuid)
                concept = order.get("concept") if isinstance(order.get("concept"), dict) else {}
                concept_uuid = str(concept.get("uuid") or "")
                comment = str(order.get("commentToFulfiller") or "")
                source = request_source_of(encounter_type_uuid=encounter_type_uuid, comment=comment)
                rows.append(
                    {
                        "uuid": order_uuid,
                        "orderNumber": order.get("orderNumber") or "",
                        "testName": radiology_menu.hospital_name(
                            concept_uuid,
                            concept.get("display") or "Imaging examination",
                        ),
                        "conceptUuid": concept_uuid,
                        "patientUuid": patient_uuid,
                        "patientName": name,
                        "mrn": mrn,
                        "visitUuid": visit_uuid,
                        "encounterUuid": encounter_uuid,
                        "encounterTypeUuid": encounter_type_uuid,
                        "visitType": visit_type.get("name") or "",
                        "dailyVisitNumber": daily_no,
                        "urgency": "STAT" if order.get("urgency") == "STAT" else (order.get("urgency") or "Routine"),
                        "comment": comment,
                        "clinicalIndication": clinical_indication_text(comment),
                        "requestSource": source,
                        "requestSourceLabel": request_source_label(source),
                        "ordered": order.get("dateActivated") or order.get("dateCreated") or visit.get("startDatetime") or "",
                        "provider": _named(order.get("orderer")) or "—",
                    }
                )
    return rows


def _supplement_worklist_from_patients(
    visits: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    cookie: str,
) -> list[dict[str, Any]]:
    import daily_visit_number as daily

    known = {row["uuid"] for row in existing}
    visit_by_patient: dict[str, list[dict[str, Any]]] = {}
    for visit in visits:
        patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
        patient_uuid = str(patient.get("uuid") or "")
        if patient_uuid:
            visit_by_patient.setdefault(patient_uuid, []).append(visit)
    extra: list[dict[str, Any]] = []
    for patient_uuid, patient_visits in visit_by_patient.items():
        try:
            listed = list_radiology_orders(patient_uuid, cookie)
        except ApiError:
            continue
        visit_lookup = {str(visit.get("uuid") or ""): visit for visit in patient_visits}
        sample = patient_visits[0]
        patient = sample.get("patient") if isinstance(sample.get("patient"), dict) else {}
        name, mrn = _name_and_mrn(patient.get("display"), patient.get("identifiers"))
        for order in listed:
            if order["uuid"] in known or not order.get("visitUuid"):
                continue
            visit = visit_lookup.get(order["visitUuid"])
            if not visit:
                continue
            known.add(order["uuid"])
            extra.append(
                {
                    **order,
                    "patientName": name,
                    "mrn": mrn,
                    "visitType": order.get("visitType")
                    or ((visit.get("visitType") or {}).get("name") if isinstance(visit.get("visitType"), dict) else ""),
                    "dailyVisitNumber": daily.daily_visit_number_from_visit(visit),
                }
            )
    return extra


def _serialize_worklist_row(
    order: dict[str, Any],
    notes: set[tuple[str, str, str]],
    financial: dict[str, Any] | None,
) -> dict[str, Any] | None:
    identity = (
        str(order.get("patientUuid") or ""),
        str(order.get("visitUuid") or ""),
        str(order.get("uuid") or ""),
    )
    if not all(identity):
        return None
    has_report = identity in notes
    entry = radiology_menu.entry_by_concept(order.get("conceptUuid") or "")
    has_charge = bool(financial and financial.get("hasCharge"))
    source = str(order.get("requestSource") or "") or request_source_of(
        encounter_type_uuid=str(order.get("encounterTypeUuid") or ""),
        comment=str(order.get("comment") or ""),
    )
    return {
        "uuid": identity[2],
        "orderNumber": order.get("orderNumber") or "",
        "investigation": order.get("testName") or "Imaging examination",
        "conceptUuid": order.get("conceptUuid") or "",
        "category": (entry or {}).get("group") or "",
        "patientUuid": identity[0],
        "patientName": order.get("patientName") or "Unknown patient",
        "mrn": order.get("mrn") or "",
        "visitUuid": identity[1],
        "encounterUuid": order.get("encounterUuid") or "",
        "encounterTypeUuid": order.get("encounterTypeUuid") or "",
        "visitType": order.get("visitType") or "",
        "dailyVisitNumber": order.get("dailyVisitNumber") or "",
        "ordered": order.get("ordered") or "",
        "urgency": order.get("urgency") or "Routine",
        "comment": order.get("comment") or "",
        "clinicalIndication": order.get("clinicalIndication") or clinical_indication_text(str(order.get("comment") or "")),
        "requestSource": source,
        "requestSourceLabel": order.get("requestSourceLabel") or request_source_label(source),
        "provider": order.get("provider") or "—",
        "hasReport": has_report,
        "reportStatus": "Report available" if has_report else "Report pending",
        "hasCharge": has_charge,
        "paymentStatus": (financial or {}).get("paymentStatus") or "UNPAID",
        "billingStatus": (financial or {}).get("billingStatus") or "Price pending",
        "feeFormatted": ((financial or {}).get("feeAmount") or {}).get("formatted") if has_charge else None,
    }


def build_worklist(cookie: str) -> dict[str, Any]:
    require_radiology_user(cookie)
    visits = _load_worklist_visits(cookie)
    orders = _worklist_orders_from_visits(visits)
    if not orders:
        orders = _supplement_worklist_from_patients(visits, orders, cookie)
    else:
        for extra in _supplement_worklist_from_patients(visits, orders, cookie):
            orders.append(extra)
    notes = _worklist_notes(visits)
    reader: OdooReader | None = None
    try:
        reader = odoo_reader()
    except ApiError:
        reader = None
    rows: list[dict[str, Any]] = []
    for order in orders:
        financial = None
        if reader:
            try:
                financial = _order_financials(reader, order, radiology_currency(reader))
            except ApiError:
                financial = None
        mapped = _serialize_worklist_row(order, notes, financial)
        if mapped:
            mapped["patientType"] = "registered"
            mapped["patientTypeLabel"] = "Registered Patient"
            mapped["isExternal"] = False
            rows.append(mapped)
    try:
        import radiology_external as external

        for item in external.list_external_studies(cookie):
            rows.append(item)
    except ApiError:
        pass
    rows.sort(key=lambda row: (row.get("ordered") or "", row.get("orderNumber") or ""), reverse=True)
    pending = [row for row in rows if not row["hasReport"]]
    reported = [row for row in rows if row["hasReport"]]
    return {
        "status": "ok",
        "pending": pending,
        "reported": reported,
        "orders": rows,
    }


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_charge_failed",
            "The radiology fee could not be created. Refresh and try again.",
        ) from error


def create_radiology_charge(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_radiology_user(cookie)
    request_id = str(body.get("requestId") or "").strip()
    selected = str(body.get("orderUuid") or "").strip()
    amount = parse_radiology_amount(body.get("amount"))
    orders = list_radiology_orders(patient_uuid, cookie)
    if selected:
        orders = [row for row in orders if row["uuid"] == selected]
        if not orders:
            raise ApiError(404, "order_not_found", "This imaging request was not found.")
    if not orders:
        raise ApiError(422, "order_required", "An imaging request is required before creating a fee.")
    odoo = odoo_reader()
    ensure_radiology_masters(odoo)
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
                    "This radiology fee is already being created.",
                )
            if state.get("status") == "done" and not to_bill:
                payload = _charge_payload(cookie, patient_uuid, user=user, odoo=odoo)
                payload["alreadyCreated"] = True
                return payload
        for key in keys:
            IDEMPOTENCY[key] = {"status": "pending"}
    try:
        patient = load_openmrs_patient(patient_uuid, cookie)
        partner = find_partner(odoo, patient)
        if not partner:
            raise ApiError(
                409,
                "account_not_found",
                "This patient has no financial account yet. Try again in a moment.",
            )
        # Re-check inside the lock window.
        still: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for order in to_bill:
            if find_existing_sale(odoo, order["uuid"]):
                continue
            try:
                product = find_radiology_product(odoo, order["conceptUuid"])
            except ApiError as error:
                if error.code in {"missing_mapping", "missing_price"} and selected:
                    raise
                if error.code in {"missing_mapping", "missing_price"}:
                    continue
                raise
            still.append((order, product))
        if not still:
            raise ApiError(
                409,
                "missing_mapping",
                "This imaging examination is not available to bill yet.",
            )
        masters = ensure_radiology_masters(odoo)
        shop = ensure_radiology_ngn_pricelist(odoo, masters["shop"])
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = _radiology_pricelist_id(shop)
        currency_id = _ngn_currency_id(odoo)
        origin = still[0][0].get("visitUuid") or still[0][0]["uuid"]
        order_lines = []
        for order, product in still:
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": int(product["id"]),
                        "name": order.get("testName") or product.get("name"),
                        "product_uom_qty": 1,
                        "price_unit": amount,
                        "tax_id": [(6, 0, [])],
                        "external_order_id": charge_key(order["uuid"]),
                        "external_id": order["uuid"],
                    },
                )
            )
        sale_vals: dict[str, Any] = {
            "partner_id": int(partner["id"]),
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "pricelist_id": pricelist_id,
            "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
            "origin": origin,
            "care_setting": "opd",
            "order_line": order_lines,
        }
        if currency_id:
            sale_vals["currency_id"] = int(currency_id)
        sale_id = int(
            execute(
                odoo,
                "sale.order",
                "create",
                [sale_vals],
            )
        )
        sale_rows = odoo.read("sale.order", [sale_id], ["order_line"])
        line_ids = [int(item) for item in ((sale_rows[0].get("order_line") if sale_rows else None) or [])]
        if line_ids:
            execute(
                odoo,
                "sale.order.line",
                "write",
                [line_ids, {"tax_id": [(6, 0, [])], "price_unit": amount}],
            )
        _confirm_sale(odoo, sale_id)
        confirmed = odoo.read("sale.order", [sale_id], ["state", "invoice_ids"])
        if not confirmed or confirmed[0].get("state") not in {"sale", "done"}:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The radiology fee could not be created. Refresh and try again.",
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


def create_radiology_orders(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_clinical_user(cookie)
    visit_uuid = ward.resolve_clinical_order_visit_uuid(
        patient_uuid,
        str(body.get("visitUuid") or ""),
        cookie,
        missing_visit_message="Start an open visit before ordering imaging.",
    )
    location_uuid = str(body.get("locationUuid") or "").strip()
    encounter_uuid = str(body.get("encounterUuid") or "").strip()
    requested = body.get("services")
    if not location_uuid:
        raise ApiError(422, "location_required", "A consulting location is required.")
    if not isinstance(requested, list) or not requested:
        raise ApiError(422, "service_required", "Select an imaging examination.")
    if len(requested) > 10:
        raise ApiError(422, "too_many_services", "Select fewer imaging examinations at a time.")
    if any(isinstance(item, dict) and item.get("amount") not in (None, "") for item in requested):
        raise ApiError(422, "doctor_cannot_price", "The doctor does not set the imaging fee.")

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
        raise ApiError(409, "visit_closed", "This visit is closed. Start a new visit before ordering imaging.")

    encounter_uuid = ward.encounter_on_resolved_visit(visit, encounter_uuid)
    existing = _open_consultation_on_visit(visit)
    if existing and not encounter_uuid:
        encounter_uuid = existing["uuid"]

    before = {row["uuid"] for row in list_radiology_orders(patient_uuid, cookie)}
    orders_payload: list[dict[str, Any]] = []
    seen_concepts: set[str] = set()
    for item in requested:
        if not isinstance(item, dict):
            continue
        service_id = str(item.get("serviceId") or "").strip()
        concept_uuid = str(item.get("conceptUuid") or "").strip()
        service = radiology_menu.entry_by_id(service_id)
        if service and service.get("options") and not concept_uuid:
            prompt = str(service.get("optionPrompt") or "details").lower()
            raise ApiError(
                422,
                "option_required",
                f"Choose the {prompt} for this examination.",
            )
        entry = radiology_menu.resolve_orderable(service_id, concept_uuid)
        if not entry or not entry.get("conceptUuid"):
            raise ApiError(
                422,
                "not_orderable",
                "That imaging examination is not available to order yet.",
            )
        concept_uuid = str(entry["conceptUuid"])
        if concept_uuid in seen_concepts:
            continue
        seen_concepts.add(concept_uuid)
        orders_payload.append(
            {
                "concept": {
                    "uuid": concept_uuid,
                    "name": entry.get("conceptName") or entry.get("hospitalName"),
                },
                "commentToFulfiller": str(item.get("comment") or "").strip(),
            }
        )
    if not orders_payload:
        raise ApiError(422, "service_required", "Select an imaging examination.")

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
    after = list_radiology_orders(patient_uuid, cookie)
    created = [row for row in after if row["uuid"] not in before and row.get("visitUuid") == visit_uuid]
    if not created:
        created = [row for row in after if row["uuid"] not in before]
    return {
        "status": "ok",
        "encounterUuid": saved_encounter,
        "visitUuid": visit_uuid,
        "orders": created,
        "message": "Radiology order created.",
        "requestSource": SOURCE_DOCTOR_ORDER,
        "requestSourceLabel": request_source_label(SOURCE_DOCTOR_ORDER),
    }


def _build_orders_payload(requested: list[Any], *, default_comment: str = "") -> list[dict[str, Any]]:
    orders_payload: list[dict[str, Any]] = []
    seen_concepts: set[str] = set()
    for item in requested:
        if not isinstance(item, dict):
            continue
        service_id = str(item.get("serviceId") or "").strip()
        concept_uuid = str(item.get("conceptUuid") or "").strip()
        service = radiology_menu.entry_by_id(service_id)
        if service and service.get("options") and not concept_uuid:
            prompt = str(service.get("optionPrompt") or "details").lower()
            raise ApiError(
                422,
                "option_required",
                f"Choose the {prompt} for this examination.",
            )
        entry = radiology_menu.resolve_orderable(service_id, concept_uuid)
        if not entry or not entry.get("conceptUuid"):
            raise ApiError(
                422,
                "not_orderable",
                "That imaging examination is not available to order yet.",
            )
        concept_uuid = str(entry["conceptUuid"])
        if concept_uuid in seen_concepts:
            continue
        seen_concepts.add(concept_uuid)
        comment = str(item.get("comment") or "").strip() or default_comment
        orders_payload.append(
            {
                "concept": {
                    "uuid": concept_uuid,
                    "name": entry.get("conceptName") or entry.get("hospitalName"),
                },
                "commentToFulfiller": comment,
            }
        )
    if not orders_payload:
        raise ApiError(422, "service_required", "Select an imaging examination.")
    return orders_payload


def create_direct_radiology_study(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Radiology desk-initiated study. Real Radiology Order — not a forged doctor order."""
    user = require_radiology_user(cookie)
    visit_uuid = str(body.get("visitUuid") or "").strip()
    location_uuid = str(body.get("locationUuid") or "").strip()
    requested = body.get("services")
    indication = str(body.get("indication") or body.get("clinicalIndication") or "").strip()
    if not visit_uuid:
        raise ApiError(
            422,
            "visit_required",
            "Start an open visit for this patient before creating an imaging study.",
        )
    if not location_uuid:
        raise ApiError(422, "location_required", "A hospital location is required.")
    if not isinstance(requested, list) or not requested:
        raise ApiError(422, "service_required", "Select an imaging examination.")
    if len(requested) > 10:
        raise ApiError(422, "too_many_services", "Select fewer imaging examinations at a time.")
    amount = parse_radiology_amount(body.get("amount"))
    request_id = str(body.get("requestId") or "").strip()

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
        raise ApiError(
            409,
            "visit_closed",
            "This visit is closed. Start a new visit before creating an imaging study.",
        )

    marker_comment = direct_study_comment(indication)
    orders_payload = _build_orders_payload(requested, default_comment=marker_comment)
    for row in orders_payload:
        existing_comment = str(row.get("commentToFulfiller") or "").strip()
        if not existing_comment.startswith(DIRECT_SOURCE_MARKER):
            row["commentToFulfiller"] = (
                f"{DIRECT_SOURCE_MARKER} {existing_comment}".strip()
                if existing_comment
                else marker_comment
            )

    before = {row["uuid"] for row in list_radiology_orders(patient_uuid, cookie)}
    try:
        provider = _provider_uuid(str(user.get("uuid") or ""), cookie)
    except ApiError as error:
        if error.code == "provider_missing":
            raise ApiError(
                409,
                "provider_missing",
                "This Radiology account is not set up to create imaging studies yet.",
            ) from error
        raise
    visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
    payload: dict[str, Any] = {
        "patientUuid": patient_uuid,
        "visitUuid": visit_uuid,
        "visitType": visit_type.get("name") or "OPD",
        "encounterTypeUuid": RADIOLOGY_ENCOUNTER_TYPE,
        "encounterDateTime": now_openmrs(),
        "locationUuid": location_uuid,
        "providers": [{"uuid": provider}],
        "observations": [],
        "bahmniDiagnoses": [],
        "orders": orders_payload,
        "drugOrders": [],
    }
    saved = _openmrs_post("/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", cookie, payload)
    saved_encounter = str(saved.get("encounterUuid") or "")
    after = list_radiology_orders(patient_uuid, cookie)
    created = [row for row in after if row["uuid"] not in before and row.get("visitUuid") == visit_uuid]
    if not created:
        created = [row for row in after if row["uuid"] not in before]
    for row in created:
        row["requestSource"] = SOURCE_RADIOLOGY_DIRECT
        row["requestSourceLabel"] = request_source_label(SOURCE_RADIOLOGY_DIRECT)
    charge_payload: dict[str, Any] | None = None
    if created:
        charge_payload = create_radiology_charge(
            patient_uuid,
            {
                "requestId": request_id or f"direct-charge:{created[0]['uuid']}",
                "orderUuid": created[0]["uuid"],
                "amount": amount,
            },
            cookie,
        )
    return {
        "status": "ok",
        "encounterUuid": saved_encounter,
        "visitUuid": visit_uuid,
        "orders": created,
        "requestSource": SOURCE_RADIOLOGY_DIRECT,
        "requestSourceLabel": request_source_label(SOURCE_RADIOLOGY_DIRECT),
        "charge": charge_payload,
        "message": "Imaging study created by Radiology.",
    }


def build_radiology_history(cookie: str, raw_path: str = "") -> dict[str, Any]:
    """Paginated imaging history for the Radiology desk. Reuses worklist rows."""
    from urllib.parse import parse_qs

    require_radiology_user(cookie)
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
    if source_filter in {"direct", "radiology", "radiology_direct", "Radiology Direct"}:
        source_filter = SOURCE_RADIOLOGY_DIRECT
    elif source_filter in {"doctor", "doctor_order", "Doctor Order"}:
        source_filter = SOURCE_DOCTOR_ORDER
    elif source_filter in {
        "external_referral",
        "external",
        "referral",
        "External Referral",
    }:
        source_filter = "external_referral"
    else:
        source_filter = (
            source_filter
            if source_filter in {SOURCE_DOCTOR_ORDER, SOURCE_RADIOLOGY_DIRECT, "external_referral"}
            else ""
        )
    patient_type_filter = (first("patientType") or first("type")).lower()
    if patient_type_filter in {"external", "external_patient"}:
        patient_type_filter = "external"
    elif patient_type_filter in {"registered", "registered_patient"}:
        patient_type_filter = "registered"
    else:
        patient_type_filter = ""
    report_filter = first("report") or first("status")
    category = first("category") or first("modality")
    date_from = first("from") or first("start")
    date_to = first("to") or first("end")

    payload = build_worklist(cookie)
    rows = list(payload.get("orders") or [])

    def ordered_day(value: str) -> str:
        text = str(value or "")
        return text[:10] if len(text) >= 10 else text

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if source_filter and row.get("requestSource") != source_filter:
            continue
        if patient_type_filter:
            row_type = "external" if row.get("isExternal") or row.get("patientType") == "external" else "registered"
            if row_type != patient_type_filter:
                continue
        if report_filter in {"pending", "report_pending"} and row.get("hasReport"):
            continue
        if report_filter in {"reported", "available", "report_available"} and not row.get("hasReport"):
            continue
        if category and str(row.get("category") or "") != category:
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
                    str(row.get("investigation") or ""),
                    str(row.get("orderNumber") or ""),
                    str(row.get("requestSourceLabel") or ""),
                    str(row.get("buyerPhone") or ""),
                    str(row.get("studyId") or ""),
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
