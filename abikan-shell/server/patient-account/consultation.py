"""Consultation fee charges.

Creates an Odoo sale order for a service product, then confirms it so the
installed automated invoicing posts a customer invoice. Payment stays on the
Accountant path. OpenMRS Dispensed, Pharmacy stock, and Registration billing
are never touched.

Idempotency key is consultation:{visitUuid}. The Consultation encounter is
created later, on clinical save, so the visit is the stable chargeable event.
"""

from __future__ import annotations

import json
import math
import re
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import xmlrpc.client

import server as core

CLINICAL_PRIVILEGE = "app:clinical"
CLINICAL_ROLES = {"SuperAdmin", "System Developer"}
SHOP_NAME = "Consultation Desk"
CATEGORY_NAME = "Consultation"
PRODUCT_NAME = "Consultation Fee"
LEGACY_TEST_PRODUCT_NAME = "Consultation Fee — TEST"
PRICELIST_NAME = "Hospital Consultation"
NGN_CURRENCY = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
MAX_CONSULTATION_AMOUNT = 10_000_000.0
EXTERNAL_PREFIX = "consultation:"
CONSULTATION_ENCOUNTER_TYPE = "Consultation"
NHIS_PARAM = "abikan.patients.nhis"
NHIS_NAME_MARK = "NHIS"
NHIS_PHARMACY_DISCOUNT = 0.0
NHIS_FEE_REASON = "NHIS patients are not charged a consultation fee."

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
payment_state_label = core.payment_state_label
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


def parse_consultation_amount(value: Any) -> float:
    if value is None:
        raise ApiError(422, "amount_required", "Enter the consultation fee in naira.")
    if isinstance(value, bool):
        raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
        amount = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ApiError(422, "amount_required", "Enter the consultation fee in naira.")
        if re.search(r"[$€£]|USD|EUR|GBP", text, flags=re.I):
            raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
        text = re.sub(r"^(NGN|₦)\s*", "", text, flags=re.I)
        if re.search(r"[^\d,.\s]", text):
            raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
        compact = text.replace(",", "").replace(" ", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", compact):
            raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
        amount = float(compact)
    else:
        raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
    if amount <= 0:
        raise ApiError(422, "amount_invalid", "Consultation fee must be greater than zero.")
    if amount > MAX_CONSULTATION_AMOUNT:
        raise ApiError(422, "amount_invalid", "Enter a valid consultation fee in naira.")
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
    if rows[0].get("active") is False:
        execute(odoo, "res.currency", "write", [[currency_id], {"active": True}])
    return currency_id


def consultation_currency(odoo: OdooReader, currency_id: int | None = None) -> dict[str, Any]:
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


def load_openmrs_user(cookie: str) -> dict[str, Any]:
    import accountant as cashier

    return cashier.load_openmrs_user(cookie)


def is_clinician(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & CLINICAL_ROLES) or CLINICAL_PRIVILEGE in privileges


def require_clinician(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_clinician(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires the Doctor workspace.",
        )
    return user


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
        raise ApiError(502, "openmrs_error", "The consultation record could not be loaded.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The consultation record could not be loaded.") from error


def charge_key(visit_uuid: str) -> str:
    return f"{EXTERNAL_PREFIX}{visit_uuid}"


def _visit_row(visit: dict[str, Any], patient_uuid: str) -> dict[str, Any]:
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    if patient.get("uuid") and patient.get("uuid") != patient_uuid:
        raise ApiError(409, "wrong_patient", "This visit does not belong to this patient.")
    visit_type = visit.get("visitType") if isinstance(visit.get("visitType"), dict) else {}
    location = visit.get("location") if isinstance(visit.get("location"), dict) else {}
    return {
        "uuid": visit.get("uuid"),
        "startDatetime": visit.get("startDatetime") or "",
        "open": not visit.get("stopDatetime"),
        "visitType": visit_type.get("name") or "",
        "location": location.get("name") or "",
    }


def load_visit(visit_uuid: str, patient_uuid: str, cookie: str) -> dict[str, Any]:
    visit = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{visit_uuid}"
        "?v=custom:(uuid,startDatetime,stopDatetime,visitType:(name),location:(name),patient:(uuid,display))",
        cookie,
    )
    if not isinstance(visit, dict) or not visit.get("uuid"):
        raise ApiError(404, "visit_not_found", "This visit was not found.")
    return _visit_row(visit, patient_uuid)


def list_visits(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    payload = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit?patient={patient_uuid}"
        "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name),location:(name),patient:(uuid))"
        "&limit=20",
        cookie,
    )
    results = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict) or not item.get("uuid"):
            continue
        try:
            rows.append(_visit_row(item, patient_uuid))
        except ApiError:
            continue
    return rows


def latest_consultation_encounter(visit_uuid: str, cookie: str) -> dict[str, str] | None:
    visit = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{visit_uuid}"
        "?v=custom:(encounters:(uuid,encounterDatetime,encounterType:(name)))",
        cookie,
    )
    if not isinstance(visit, dict):
        return None
    encounters = visit.get("encounters") if isinstance(visit.get("encounters"), list) else []
    matches: list[dict[str, Any]] = []
    for row in encounters:
        if not isinstance(row, dict):
            continue
        encounter_type = row.get("encounterType") if isinstance(row.get("encounterType"), dict) else {}
        if (encounter_type.get("name") or "") != CONSULTATION_ENCOUNTER_TYPE:
            continue
        if not row.get("uuid"):
            continue
        matches.append(row)
    if not matches:
        return None
    matches.sort(key=lambda row: str(row.get("encounterDatetime") or ""), reverse=True)
    chosen = matches[0]
    return {"uuid": str(chosen.get("uuid"))}


def ensure_consultation_masters(odoo: OdooReader) -> dict[str, Any]:
    """Hospital consultation product on an NGN pricelist. Does not rename or rewrite the TEST product."""
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
        [("name", "=", PRODUCT_NAME), ("categ_id", "=", category_id)],
        ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy"],
        limit=1,
    )
    if products:
        product = products[0]
        if (product.get("name") or "") == LEGACY_TEST_PRODUCT_NAME:
            product = {}
    else:
        product = {}
    if product:
        product_id = int(product["id"])
        if product.get("taxes_id"):
            execute(odoo, "product.product", "write", [[product_id], {"taxes_id": [(6, 0, [])]}])
            product["taxes_id"] = []
    else:
        product_id = int(
            execute(
                odoo,
                "product.product",
                "create",
                [
                    {
                        "name": PRODUCT_NAME,
                        "type": "service",
                        "categ_id": category_id,
                        "list_price": 0.0,
                        "uom_id": 1,
                        "uom_po_id": 1,
                        "sale_ok": True,
                        "purchase_ok": False,
                        "invoice_policy": "order",
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
            ["name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy"],
        )
        product = found[0]
    ngn_id = _ngn_currency_id(odoo)
    if not ngn_id:
        raise ApiError(
            503,
            "odoo_config",
            "Naira is not available for consultation billing.",
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
    shops = odoo.search_read(
        "sale.shop",
        [("name", "=", SHOP_NAME)],
        ["id", "name", "warehouse_id", "pricelist_id", "payment_default_id"],
        limit=1,
    )
    if shops:
        shop = shops[0]
        if many2one_id(shop.get("pricelist_id")) != pricelist_id:
            execute(odoo, "sale.shop", "write", [[int(shop["id"])], {"pricelist_id": pricelist_id}])
            shop = odoo.read(
                "sale.shop",
                [int(shop["id"])],
                ["name", "warehouse_id", "pricelist_id", "payment_default_id"],
            )[0]
    else:
        registration = odoo.search_read(
            "sale.shop",
            [("name", "=", "Registration Desk")],
            ["warehouse_id", "pricelist_id", "payment_default_id", "company_id"],
            limit=1,
        )
        source = registration[0] if registration else {}
        if not source:
            pharmacy = odoo.search_read(
                "sale.shop",
                [("name", "=", "Pharmacy Counter")],
                ["warehouse_id", "pricelist_id", "payment_default_id", "company_id"],
                limit=1,
            )
            source = pharmacy[0] if pharmacy else {}
        shop_id = int(
            execute(
                odoo,
                "sale.shop",
                "create",
                [
                    {
                        "name": SHOP_NAME,
                        "warehouse_id": many2one_id(source.get("warehouse_id")) or 1,
                        "pricelist_id": pricelist_id,
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
    return {
        "product": product,
        "shop": shop,
        "category_id": category_id,
        "pricelist_id": pricelist_id,
    }


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


def find_existing_sale(odoo: OdooReader, visit_uuid: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    key = charge_key(visit_uuid)
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
        ["name", "state", "partner_id", "invoice_ids", "shop_id", "origin", "amount_total", "amount_tax", "currency_id", "warehouse_id", "pricelist_id"],
    )
    if not sales:
        return None
    return lines[0], sales[0]


def resolve_visit(
    odoo: OdooReader,
    patient_uuid: str,
    cookie: str,
    visit_uuid: str | None = None,
) -> dict[str, Any] | None:
    if visit_uuid:
        return load_visit(visit_uuid, patient_uuid, cookie)
    # Do not substitute another open or billed visit when none was selected.
    return None


def serialize_charge(
    *,
    patient: dict[str, str],
    visit: dict[str, Any] | None,
    encounter: dict[str, str] | None,
    product: dict[str, Any] | None,
    sale: dict[str, Any] | None,
    invoice: dict[str, Any] | None,
    currency: dict[str, Any],
    can_create: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    payment_state = (invoice or {}).get("payment_state")
    residual = as_float((invoice or {}).get("amount_residual"))
    fully_paid = payment_state in {"paid", "in_payment"} and residual <= 0.009
    if invoice:
        status = "PAID" if fully_paid else "UNPAID"
    elif sale:
        status = "UNPAID"
    else:
        status = "NONE"
    amount_source = invoice or sale or {}
    amount = as_float(amount_source.get("amount_total"))
    has_charge = bool(sale or invoice)
    return {
        "status": "ok",
        "patient": patient,
        "visit": visit,
        "encounter": encounter,
        "feeName": (product or {}).get("name") or PRODUCT_NAME,
        "feeAmount": format_money(amount, currency) if has_charge else format_money(0.0, currency),
        "paymentStatus": "PAID" if status == "PAID" else "UNPAID",
        "hasCharge": has_charge,
        "canCreateCharge": can_create,
        "blockReason": block_reason,
        "nhis": False,
        "pharmacyDiscountPercent": 0,
        "message": None,
    }


def _charge_payload(
    cookie: str,
    patient_uuid: str,
    visit: dict[str, Any] | None,
    *,
    user: dict[str, Any] | None = None,
    odoo: OdooReader | None = None,
) -> dict[str, Any]:
    del user
    patient = load_openmrs_patient(patient_uuid, cookie)
    reader = odoo or odoo_reader()
    masters = ensure_consultation_masters(reader)
    product = masters["product"]
    partner = find_partner(reader, patient)
    sale = None
    invoice = None
    encounter = None
    if visit:
        existing = find_existing_sale(reader, visit["uuid"])
        if existing:
            line, sale = existing
            invoice = related_invoice(reader, sale)
            line_name = many2one_name(line.get("product_id"))
            if line_name:
                product = {**product, "name": line_name}
        encounter = latest_consultation_encounter(visit["uuid"], cookie)
    currency_id = many2one_id((invoice or sale or {}).get("currency_id"))
    currency = consultation_currency(reader, currency_id if invoice or sale else None)
    can_create = False
    reason = None
    if not partner:
        reason = "This patient has no financial account yet. Try again in a moment."
    elif not visit:
        reason = "Start a visit before creating a consultation fee."
    elif invoice and invoice.get("payment_state") in {"paid", "in_payment"} and as_float(invoice.get("amount_residual")) <= 0.009:
        reason = None
        can_create = False
    elif sale or invoice:
        reason = "Please proceed to the cashier for payment."
        can_create = False
    else:
        can_create = True
    nhis = patient_is_nhis(reader, str(patient.get("uuid") or ""))
    if nhis and can_create:
        can_create = False
        reason = NHIS_FEE_REASON
    payload = serialize_charge(
        patient=patient,
        visit=visit,
        encounter=encounter,
        product=product,
        sale=sale,
        invoice=invoice,
        currency=currency,
        can_create=can_create,
        block_reason=reason,
    )
    payload["partnerFound"] = bool(partner)
    payload["nhis"] = nhis
    payload["pharmacyDiscountPercent"] = 0
    if invoice:
        payload["tax"] = format_money(as_float(invoice.get("amount_tax")), currency)
        payload["outstanding"] = format_money(as_float(invoice.get("amount_residual")), currency)
    return payload


def load_nhis_patients(odoo: OdooReader) -> set[str]:
    found = odoo.search_read(
        "ir.config_parameter",
        [("key", "=", NHIS_PARAM)],
        ["value"],
        limit=1,
    )
    if not found:
        return set()
    try:
        parsed = json.loads(str(found[0].get("value") or "[]"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item).strip() for item in parsed if str(item).strip()}


def save_nhis_patients(odoo: OdooReader, patients: set[str]) -> None:
    payload = json.dumps(sorted(patients))
    found = odoo.search_read(
        "ir.config_parameter",
        [("key", "=", NHIS_PARAM)],
        ["id"],
        limit=1,
    )
    if found:
        execute(odoo, "ir.config_parameter", "write", [[int(found[0]["id"])], {"value": payload}])
        return
    execute(odoo, "ir.config_parameter", "create", [{"key": NHIS_PARAM, "value": payload}])


def patient_is_nhis(odoo: OdooReader, patient_uuid: str) -> bool:
    uuid = str(patient_uuid or "").strip()
    return bool(uuid) and uuid in load_nhis_patients(odoo)


def partner_is_nhis(odoo: OdooReader, partner_id: int) -> bool:
    if not partner_id:
        return False
    rows = odoo.read("res.partner", [int(partner_id)], ["uuid"])
    uuid = str((rows[0].get("uuid") if rows else "") or "").strip()
    return patient_is_nhis(odoo, uuid)


def apply_nhis_pharmacy_discount(odoo: OdooReader, sale: dict[str, Any]) -> None:
    """NHIS no longer changes pharmacy prices. Kept so older callers stay safe."""
    del odoo, sale


def strip_nhis_mark(value: str) -> str:
    text = " ".join(str(value or "").split())
    if text.upper().endswith(f" {NHIS_NAME_MARK}"):
        return text[: -(len(NHIS_NAME_MARK) + 1)].strip()
    return text


def apply_nhis_mark(given: str, middle: str, family: str, nhis: bool) -> tuple[str, str, str]:
    """Keep NHIS on the surname so every department sees it in the patient name."""
    given_name = strip_nhis_mark(given)
    middle_name = strip_nhis_mark(middle)
    family_name = strip_nhis_mark(family)
    if nhis:
        family_name = f"{family_name} {NHIS_NAME_MARK}".strip()
    return given_name, middle_name, family_name


def sync_chart_name_nhis(patient_uuid: str, nhis: bool) -> None:
    """Write or remove the NHIS mark on the chart name."""
    from urllib.parse import quote

    from server import openmrs_service_get, openmrs_service_post

    uuid = str(patient_uuid or "").strip()
    if not uuid:
        return
    try:
        patient = openmrs_service_get(
            f"/openmrs/ws/rest/v1/patient/{quote(uuid)}"
            "?v=custom:(uuid,person:(preferredName:(uuid,givenName,middleName,familyName)))"
        )
    except ApiError:
        return
    person = patient.get("person") if isinstance(patient.get("person"), dict) else {}
    name = person.get("preferredName") if isinstance(person.get("preferredName"), dict) else {}
    given, middle, family = apply_nhis_mark(
        str(name.get("givenName") or ""),
        str(name.get("middleName") or ""),
        str(name.get("familyName") or ""),
        nhis,
    )
    payload: dict[str, Any] = {
        "givenName": given,
        "familyName": family or NHIS_NAME_MARK,
        "preferred": True,
    }
    if middle:
        payload["middleName"] = middle
    if name.get("uuid"):
        payload["uuid"] = name["uuid"]
    try:
        openmrs_service_post(
            f"/openmrs/ws/rest/v1/patient/{quote(uuid)}",
            {"person": {"names": [payload]}},
        )
    except ApiError:
        return


def store_patient_nhis(odoo: OdooReader, patient_uuid: str, nhis: bool) -> bool:
    uuid = str(patient_uuid or "").strip()
    if not uuid:
        raise ApiError(422, "patient_required", "Choose a patient first.")
    patients = load_nhis_patients(odoo)
    if nhis:
        patients.add(uuid)
    else:
        patients.discard(uuid)
    save_nhis_patients(odoo, patients)
    return nhis


def set_patient_nhis(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    import patient_directory as directory

    directory.require_directory_reader(cookie)
    load_openmrs_patient(patient_uuid, cookie)
    nhis = store_patient_nhis(odoo_reader(), patient_uuid, bool(body.get("nhis")))
    sync_chart_name_nhis(patient_uuid, nhis)
    return {"status": "ok", "uuid": patient_uuid, "nhis": nhis}


def build_consultation(patient_uuid: str, cookie: str, visit_uuid: str | None = None) -> dict[str, Any]:
    require_clinician(cookie)
    odoo = odoo_reader()
    visit = resolve_visit(odoo, patient_uuid, cookie, visit_uuid)
    return _charge_payload(cookie, patient_uuid, visit, odoo=odoo)


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_charge_failed",
            "The consultation fee could not be created. Refresh and try again.",
        ) from error


def create_consultation_charge(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_clinician(cookie)
    visit_uuid = str(body.get("visitUuid") or "").strip()
    if not visit_uuid:
        raise ApiError(422, "visit_required", "Start a visit before creating a consultation fee.")
    request_id = str(body.get("requestId") or "").strip()
    visit_key = charge_key(visit_uuid)
    keys = [visit_key]
    if request_id:
        keys.append(request_id)
    with IDEMPOTENCY_LOCK:
        for key in keys:
            state = IDEMPOTENCY.get(key) or {}
            if state.get("status") == "pending":
                raise ApiError(
                    409,
                    "charge_in_progress",
                    "This consultation fee is already being created.",
                )
            if state.get("status") == "done":
                visit = load_visit(visit_uuid, patient_uuid, cookie)
                payload = _charge_payload(cookie, patient_uuid, visit, user=user)
                payload["alreadyCreated"] = True
                return payload
        for key in keys:
            IDEMPOTENCY[key] = {"status": "pending"}
    try:
        visit = load_visit(visit_uuid, patient_uuid, cookie)
        patient = load_openmrs_patient(patient_uuid, cookie)
        odoo = odoo_reader()
        partner = find_partner(odoo, patient)
        if not partner:
            raise ApiError(
                409,
                "account_not_found",
                "This patient has no financial account yet. Try again in a moment.",
            )
        if patient_is_nhis(odoo, patient_uuid):
            payload = _charge_payload(cookie, patient_uuid, visit, user=user, odoo=odoo)
            with IDEMPOTENCY_LOCK:
                for key in keys:
                    IDEMPOTENCY.pop(key, None)
            return payload
        existing = find_existing_sale(odoo, visit_uuid)
        if existing:
            _line, sale = existing
            if sale.get("state") == "draft":
                _confirm_sale(odoo, int(sale["id"]))
            payload = _charge_payload(cookie, patient_uuid, visit, user=user, odoo=odoo)
            payload["alreadyCreated"] = True
            with IDEMPOTENCY_LOCK:
                for key in keys:
                    IDEMPOTENCY[key] = {"status": "done"}
            return payload
        amount = parse_consultation_amount(body.get("amount"))
        masters = ensure_consultation_masters(odoo)
        product = masters["product"]
        shop = masters["shop"]
        product_id = int(product["id"])
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = many2one_id(shop.get("pricelist_id")) or masters.get("pricelist_id") or 1
        price = amount
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
                        "origin": visit_uuid,
                        "care_setting": "opd",
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": product_id,
                                    "name": product.get("name") or PRODUCT_NAME,
                                    "product_uom_qty": 1,
                                    "price_unit": price,
                                    "tax_id": [(6, 0, [])],
                                    "external_order_id": visit_key,
                                    "external_id": visit_uuid,
                                },
                            )
                        ],
                    }
                ],
            )
        )
        sale_rows = odoo.read("sale.order", [sale_id], ["order_line"])
        line_ids = [int(item) for item in ((sale_rows[0].get("order_line") if sale_rows else None) or [])]
        if line_ids:
            execute(
                odoo,
                "sale.order.line",
                "write",
                [line_ids, {"tax_id": [(6, 0, [])], "price_unit": price}],
            )
        _confirm_sale(odoo, sale_id)
        confirmed = odoo.read("sale.order", [sale_id], ["state", "invoice_ids"])
        if not confirmed or confirmed[0].get("state") not in {"sale", "done"}:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The consultation fee could not be created. Refresh and try again.",
            )
        with IDEMPOTENCY_LOCK:
            for key in keys:
                IDEMPOTENCY[key] = {"status": "done"}
        payload = _charge_payload(cookie, patient_uuid, visit, user=user, odoo=odoo)
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
