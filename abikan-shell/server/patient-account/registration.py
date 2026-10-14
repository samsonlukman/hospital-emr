"""Registration fee charges.

Creates an Odoo sale order for a service product, then confirms it so the
installed automated invoicing posts a customer invoice. Payment stays on the
Accountant path. OpenMRS Dispensed and Pharmacy stock are never touched.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import xmlrpc.client

import server as core

REGISTRATION_PRIVILEGE = "app:registration"
REGISTRATION_ROLES = {
    "SuperAdmin",
    "System Developer",
    "Abikan:Reception",
    "Abikan:Registration",
}
SHOP_NAME = "Registration Desk"
CATEGORY_NAME = "Registration"
PRICELIST_NAME = "Hospital Registration"
PRODUCT_CODES = {
    "individual": "registration-individual",
    "family": "registration-family",
}
FEES_PATH = os.path.join(os.path.dirname(__file__), "data", "registration_fees.json")
NGN_CURRENCY = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
EXTERNAL_PREFIX = "registration:"
VISIT_ALREADY_OPEN_CODE = "visit_already_open"
VISIT_ALREADY_OPEN_MESSAGE = "Patient already has an open visit. Continue with the existing visit."
ADMISSION_IN_PROGRESS_CODE = "admission_in_progress"
ADMISSION_IN_PROGRESS_MESSAGE = (
    "This patient is already admitted. Continue with the existing admission visit."
)
CARD_ALREADY_REGISTERED_CODE = "card_already_registered"
CARD_ALREADY_REGISTERED_MESSAGE = (
    "This patient's card is already registered. Continue with the visit."
)
FAMILY_CARD_ISSUED_CODE = "family_card_issued"
FAMILY_CARD_ISSUED_MESSAGE = (
    "This family already has a Family Card. No new card fee is created."
)
CARD_FEE_UNAVAILABLE_MESSAGE = (
    "Registration card prices are unavailable. You can still start the visit."
)

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


def load_fee_config() -> dict[str, Any]:
    with open(FEES_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def card_specs() -> dict[str, dict[str, Any]]:
    cards = load_fee_config().get("cards") or {}
    return {str(key): dict(value) for key, value in cards.items() if isinstance(value, dict)}


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


def registration_currency(odoo: OdooReader, currency_id: int | None = None) -> dict[str, Any]:
    ngn_id = currency_id or _ngn_currency_id(odoo)
    if ngn_id:
        loaded = load_currency(odoo, ngn_id)
        return {**loaded, "code": "NGN", "symbol": "₦", "position": "before"}
    return dict(NGN_CURRENCY)


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


def is_registrar(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & REGISTRATION_ROLES) or REGISTRATION_PRIVILEGE in privileges


def require_registrar(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_registrar(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires Reception access.",
        )
    return user


def list_new_registrations(cookie: str, raw_path: str) -> dict[str, Any]:
    """Patients whose hospital record was created in the selected date range."""
    require_registrar(cookie)
    from datetime import datetime, timezone
    from urllib.parse import parse_qs
    from zoneinfo import ZoneInfo

    import admin_period
    import openmrs_sql

    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    window = admin_period.resolve_period(
        (query.get("period") or ["today"])[0],
        start=(query.get("from") or [""])[0],
        end=(query.get("to") or [""])[0],
    )
    count_rows = openmrs_sql.fetch_all(
        """
        SELECT COUNT(*)
        FROM patient p
        INNER JOIN person per ON per.person_id = p.patient_id AND per.voided = 0
        WHERE p.voided = 0
          AND p.date_created >= %s
          AND p.date_created < %s
        """,
        (window["utcStartNaive"], window["utcEndNaive"]),
    )
    total = int(count_rows[0][0]) if count_rows else 0
    rows = openmrs_sql.fetch_all(
        """
        SELECT per.uuid,
               TRIM(CONCAT_WS(' ', NULLIF(pn.given_name, ''), NULLIF(pn.family_name, ''))),
               pi.identifier,
               p.date_created
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
        WHERE p.voided = 0
          AND p.date_created >= %s
          AND p.date_created < %s
        ORDER BY p.date_created DESC
        LIMIT 300
        """,
        (window["utcStartNaive"], window["utcEndNaive"]),
    )
    lagos = ZoneInfo("Africa/Lagos")
    items: list[dict[str, str]] = []
    for patient_uuid, name, hospital_number, created in rows:
        time_label = "—"
        date_label = ""
        if isinstance(created, datetime):
            aware = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            local = aware.astimezone(lagos)
            time_label = local.strftime("%I:%M %p").lstrip("0").lower()
            date_label = local.date().isoformat()
        items.append(
            {
                "uuid": str(patient_uuid or ""),
                "patientName": " ".join(str(name or "").split()) or "Unknown patient",
                "mrn": str(hospital_number or "").strip() or "—",
                "time": time_label,
                "date": date_label,
            }
        )
    return {
        "status": "ok",
        "period": window["label"],
        "singleDay": window["startDate"] == window["endDate"],
        "total": total,
        "items": items,
    }


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
        raise ApiError(502, "openmrs_error", "The registration record could not be loaded.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The registration record could not be loaded.") from error


def charge_key(visit_uuid: str) -> str:
    return f"{EXTERNAL_PREFIX}{visit_uuid}"


def load_visit(visit_uuid: str, patient_uuid: str, cookie: str) -> dict[str, Any]:
    visit = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit/{visit_uuid}"
        "?v=custom:(uuid,startDatetime,stopDatetime,visitType:(name),location:(name),patient:(uuid,display))",
        cookie,
    )
    if not isinstance(visit, dict) or not visit.get("uuid"):
        raise ApiError(404, "visit_not_found", "This visit was not found.")
    patient = visit.get("patient") if isinstance(visit.get("patient"), dict) else {}
    if (patient.get("uuid") or "") != patient_uuid:
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


def latest_open_visit(patient_uuid: str, cookie: str) -> dict[str, Any] | None:
    """Open visit for this patient only. Open = stopDatetime empty. No extra time window."""
    payload = _openmrs_json(
        f"/openmrs/ws/rest/v1/visit?patient={patient_uuid}"
        "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name),location:(name),patient:(uuid))"
        "&limit=20",
        cookie,
    )
    results = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        return None
    open_rows: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict) or row.get("stopDatetime"):
            continue
        patient = row.get("patient") if isinstance(row.get("patient"), dict) else {}
        if (patient.get("uuid") or "") != patient_uuid:
            continue
        if not row.get("uuid"):
            continue
        open_rows.append(row)
    if not open_rows:
        return None
    open_rows.sort(key=lambda row: str(row.get("startDatetime") or ""), reverse=True)
    return load_visit(str(open_rows[0].get("uuid")), patient_uuid, cookie)


def _ensure_product(
    odoo: OdooReader,
    *,
    category_id: int,
    code: str,
    name: str,
    amount: float,
) -> dict[str, Any]:
    fields = ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "default_code"]
    found = odoo.search_read("product.product", [("default_code", "=", code)], fields, limit=1)
    values = {
        "name": name,
        "taxes_id": [(6, 0, [])],
        "supplier_taxes_id": [(6, 0, [])],
        "invoice_policy": "order",
    }
    if found:
        product_id = int(found[0]["id"])
        # Keep the live hospital price. JSON is only a first-create seed.
        execute(odoo, "product.product", "write", [[product_id], values])
        return odoo.read("product.product", [product_id], fields)[0]
    product_id = int(
        execute(
            odoo,
            "product.product",
            "create",
            [
                {
                    "name": name,
                    "type": "service",
                    "categ_id": category_id,
                    "list_price": amount,
                    "default_code": code,
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
    return odoo.read("product.product", [product_id], fields)[0]


def ensure_registration_masters(odoo: OdooReader) -> dict[str, Any]:
    """Approved Individual/Family card products on the Registration Desk NGN pricelist."""
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
    products: dict[str, dict[str, Any]] = {}
    for card_id, spec in card_specs().items():
        if card_id not in PRODUCT_CODES:
            continue
        products[card_id] = _ensure_product(
            odoo,
            category_id=category_id,
            code=PRODUCT_CODES[card_id],
            name=str(spec.get("productName") or spec.get("label") or card_id),
            amount=as_float(spec.get("amount")),
        )
    ngn_id = _ngn_currency_id(odoo)
    pricelists = odoo.search_read(
        "product.pricelist",
        [("name", "=", PRICELIST_NAME)],
        ["id", "name", "currency_id"],
        limit=1,
    )
    if pricelists:
        pricelist_id = int(pricelists[0]["id"])
        if ngn_id and many2one_id(pricelists[0].get("currency_id")) != ngn_id:
            execute(odoo, "product.pricelist", "write", [[pricelist_id], {"currency_id": ngn_id}])
    else:
        pricelist_id = int(
            execute(
                odoo,
                "product.pricelist",
                "create",
                [{"name": PRICELIST_NAME, "currency_id": ngn_id or 1}],
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
        "products": products,
        "product": products.get("individual") or next(iter(products.values())),
        "shop": shop,
        "category_id": category_id,
        "pricelist_id": pricelist_id,
    }


def card_catalog(cookie: str | None = None) -> list[dict[str, Any]]:
    del cookie
    specs = card_specs()
    try:
        odoo = odoo_reader()
        masters = ensure_registration_masters(odoo)
        currency = registration_currency(odoo)
        cards = []
        for card_id, spec in specs.items():
            product = masters["products"].get(card_id) or {}
            amount = as_float(product.get("list_price")) or as_float(spec.get("amount"))
            cards.append(
                {
                    "id": card_id,
                    "label": spec.get("label") or product.get("name") or card_id,
                    "amount": format_money(amount, currency),
                }
            )
        return cards
    except ApiError:
        currency = dict(NGN_CURRENCY)
        return [
            {
                "id": card_id,
                "label": spec.get("label") or card_id,
                "amount": format_money(as_float(spec.get("amount")), currency),
            }
            for card_id, spec in specs.items()
        ]


def product_for_card(masters: dict[str, Any], card_type: str | None) -> tuple[str, dict[str, Any]]:
    products = masters.get("products") or {}
    chosen = str(card_type or "individual").strip().lower()
    if chosen not in products:
        chosen = "individual" if "individual" in products else next(iter(products))
    return chosen, products[chosen]


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


def _sale_fields() -> list[str]:
    return [
        "name",
        "state",
        "partner_id",
        "invoice_ids",
        "shop_id",
        "origin",
        "amount_total",
        "amount_tax",
        "currency_id",
        "warehouse_id",
        "pricelist_id",
    ]


def _line_fields() -> list[str]:
    return [
        "order_id",
        "product_id",
        "product_uom_qty",
        "price_unit",
        "external_order_id",
        "external_id",
    ]


def find_existing_sale(odoo: OdooReader, visit_uuid: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    key = charge_key(visit_uuid)
    lines = odoo.search_read(
        "sale.order.line",
        [("external_order_id", "=", key)],
        _line_fields(),
        limit=5,
    )
    if not lines:
        return None
    sale_id = many2one_id(lines[0].get("order_id"))
    if not sale_id:
        return None
    sales = odoo.read("sale.order", [sale_id], _sale_fields())
    if not sales:
        return None
    return lines[0], sales[0]


def sale_line_is_family_card(odoo: OdooReader, line: dict[str, Any] | None) -> bool:
    if not line:
        return False
    product_id = many2one_id(line.get("product_id"))
    if not product_id:
        return False
    try:
        rows = odoo.read("product.product", [product_id], ["default_code"])
    except Exception:
        return False
    return bool(rows) and str(rows[0].get("default_code") or "") == PRODUCT_CODES["family"]


def find_patient_registration_sale(
    odoo: OdooReader,
    partner_id: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Any prior Individual/Family card sale for this patient. Not another patient's."""
    if partner_id <= 0:
        return None
    sales = odoo.search_read(
        "sale.order",
        [("partner_id", "=", partner_id)],
        _sale_fields(),
        limit=80,
    )
    if not sales:
        return None
    sales = sorted(sales, key=lambda row: int(row.get("id") or 0), reverse=True)
    sale_ids = [int(row["id"]) for row in sales]
    lines = odoo.search_read(
        "sale.order.line",
        [("order_id", "in", sale_ids), ("external_order_id", "=like", f"{EXTERNAL_PREFIX}%")],
        _line_fields(),
        limit=20,
    )
    lines = sorted(lines, key=lambda row: int(row.get("id") or 0), reverse=True)
    if not lines:
        return None
    sale_id = many2one_id(lines[0].get("order_id"))
    sale = next((row for row in sales if int(row["id"]) == sale_id), None)
    if not sale:
        return None
    sale_partner = many2one_id(sale.get("partner_id"))
    if sale_partner != partner_id:
        return None
    return lines[0], sale


def serialize_charge(
    *,
    patient: dict[str, str],
    visit: dict[str, Any] | None,
    product: dict[str, Any] | None,
    sale: dict[str, Any] | None,
    invoice: dict[str, Any] | None,
    currency: dict[str, Any],
    can_create: bool,
    block_reason: str | None,
    card_type: str | None = None,
    cards: list[dict[str, Any]] | None = None,
    card_already_registered: bool = False,
    admission_active: bool = False,
    family: dict[str, Any] | None = None,
    family_card_issued: bool = False,
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
    if not amount and product:
        amount = as_float(product.get("list_price"))
    return {
        "status": "ok",
        "patient": patient,
        "visit": visit,
        "cardType": card_type or "individual",
        "cards": cards or [],
        "feeName": (product or {}).get("name") or "Registration card",
        "feeAmount": format_money(amount, currency) if amount else format_money(as_float((product or {}).get("list_price")), currency),
        "paymentStatus": "PAID" if status == "PAID" else "UNPAID",
        "hasCharge": bool(sale or invoice),
        "canCreateCharge": can_create,
        "cardAlreadyRegistered": card_already_registered,
        "familyCardIssued": family_card_issued,
        "family": family,
        "admissionActive": admission_active,
        "blockReason": block_reason,
        "message": None,
    }


def _charge_payload(
    cookie: str,
    patient_uuid: str,
    visit: dict[str, Any] | None,
    *,
    user: dict[str, Any] | None = None,
    card_type: str | None = None,
) -> dict[str, Any]:
    del user
    import hospital_family as household

    family_decision = household.charge_decision(patient_uuid)
    family = family_decision.get("family")
    family_card_issued = bool(family_decision.get("familyCardIssued"))
    can_charge_family = bool(family_decision.get("canChargeFamilyFee"))
    if can_charge_family:
        card_type = "family"
    patient = load_openmrs_patient(patient_uuid, cookie)
    odoo = odoo_reader()
    masters = ensure_registration_masters(odoo)
    chosen, product = product_for_card(masters, card_type)
    currency = registration_currency(odoo)
    partner = find_partner(odoo, patient)
    sale = None
    sale_line = None
    invoice = None
    card_already_registered = False
    visit_sale = find_existing_sale(odoo, visit["uuid"]) if visit else None
    partner_id = int(partner["id"]) if partner and partner.get("id") else 0
    patient_sale = find_patient_registration_sale(odoo, partner_id) if partner_id else None
    if visit_sale:
        sale_line, sale = visit_sale
        invoice = related_invoice(odoo, sale)
    elif family_card_issued:
        card_already_registered = True
        if (
            patient_sale
            and (family or {}).get("isFeePatient")
            and sale_line_is_family_card(odoo, patient_sale[0])
        ):
            sale_line, sale = patient_sale
            invoice = related_invoice(odoo, sale)
    elif patient_sale and can_charge_family:
        if sale_line_is_family_card(odoo, patient_sale[0]):
            sale_line, sale = patient_sale
            invoice = related_invoice(odoo, sale)
            card_already_registered = True
    elif patient_sale:
        sale_line, sale = patient_sale
        invoice = related_invoice(odoo, sale)
        paid = invoice and invoice.get("payment_state") in {"paid", "in_payment"} and as_float(invoice.get("amount_residual")) <= 0.009
        card_already_registered = bool(paid)
    if sale_line and sale_line_is_family_card(odoo, sale_line):
        chosen, product = product_for_card(masters, "family")
    can_create = False
    reason = None
    # The patient who was billed still has that invoice. Later family members do not.
    owns_family_bill = bool(sale and family_card_issued and (family or {}).get("isFeePatient"))
    if family_card_issued and not owns_family_bill:
        reason = FAMILY_CARD_ISSUED_MESSAGE
        can_create = False
        card_already_registered = True
    elif card_already_registered:
        reason = CARD_ALREADY_REGISTERED_MESSAGE
        can_create = False
    elif not partner:
        reason = "This patient has no financial account yet. Try again in a moment."
    elif invoice and invoice.get("payment_state") in {"paid", "in_payment"} and as_float(invoice.get("amount_residual")) <= 0.009:
        reason = None
        can_create = False
    elif sale or invoice:
        reason = "Please proceed to the cashier for payment."
        can_create = False
    else:
        can_create = True
    cards = card_catalog(cookie)
    if family_decision.get("inFamily"):
        cards = [card for card in cards if card.get("id") == "family"] or cards
    payload = serialize_charge(
        patient=patient,
        visit=visit,
        product=product,
        sale=sale,
        invoice=invoice,
        currency=currency,
        can_create=can_create,
        block_reason=reason,
        card_type=chosen,
        cards=cards,
        card_already_registered=card_already_registered,
        admission_active=_admission_active(patient_uuid, cookie),
        family=family,
        family_card_issued=family_card_issued and not owns_family_bill,
    )
    if not partner:
        payload["partnerFound"] = False
    else:
        payload["partnerFound"] = True
    if invoice:
        payload["tax"] = format_money(as_float(invoice.get("amount_tax")), currency)
        payload["outstanding"] = format_money(as_float(invoice.get("amount_residual")), currency)
    return payload


def _admission_active(patient_uuid: str, cookie: str) -> bool:
    try:
        import inpatient

        return bool(inpatient.current_assignment(patient_uuid, cookie, scan_board=True))
    except Exception:
        return False


def _charge_unavailable_payload(
    cookie: str,
    patient_uuid: str,
    visit: dict[str, Any] | None,
) -> dict[str, Any]:
    import hospital_family as household

    patient = load_openmrs_patient(patient_uuid, cookie)
    decision = household.charge_decision(patient_uuid)
    return serialize_charge(
        patient=patient,
        visit=visit,
        product=None,
        sale=None,
        invoice=None,
        currency=dict(NGN_CURRENCY),
        can_create=False,
        block_reason=CARD_FEE_UNAVAILABLE_MESSAGE,
        cards=card_catalog(None),
        admission_active=_admission_active(patient_uuid, cookie),
        family=decision.get("family"),
        family_card_issued=bool(decision.get("familyCardIssued")),
    )


def ensure_patient_partner(odoo: OdooReader, patient: dict[str, str], *, wait: bool = False) -> dict[str, Any] | None:
    """The card bill needs the patient's account. Create it if registration has not synced it yet."""
    found = find_partner(odoo, patient)
    if found:
        return found
    if wait:
        import time

        for _ in range(6):
            time.sleep(0.5)
            found = find_partner(odoo, patient)
            if found:
                return found
    name = str(patient.get("name") or patient.get("mrn") or "Patient").strip() or "Patient"
    values: dict[str, Any] = {
        "name": name,
        "customer_rank": 1,
        "company_type": "person",
    }
    ref = str(patient.get("mrn") or "").strip()
    if ref:
        values["ref"] = ref
    patient_uuid = str(patient.get("uuid") or "").strip()
    if patient_uuid:
        values["uuid"] = patient_uuid
    try:
        partner_id = int(execute(odoo, "res.partner", "create", [values]))
    except Exception:
        found = find_partner(odoo, patient)
        if found:
            return found
        values.pop("uuid", None)
        try:
            partner_id = int(execute(odoo, "res.partner", "create", [values]))
        except Exception as error:
            print(f"registration account was not created: {error}", flush=True)
            return find_partner(odoo, patient)
    rows = odoo.read("res.partner", [partner_id], ["id", "name", "ref", "uuid"])
    return rows[0] if rows else {"id": partner_id, "name": name, "ref": ref, "uuid": patient_uuid}


def _billing_records(odoo: OdooReader) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        rows = execute(
            odoo,
            "res.partner",
            "search_read",
            [[]],
            {
                "fields": ["id", "uuid", "ref", "active"],
                "limit": 1000,
                "offset": offset,
                "context": {"active_test": False},
            },
        ) or []
        records.extend(rows)
        if len(rows) < 1000:
            return records
        offset += len(rows)


def open_missing_patient_accounts() -> dict[str, int]:
    """Open a bill account for every registered patient who does not have one."""
    import openmrs_sql

    patients = openmrs_sql.fetch_all(
        """
        SELECT p.uuid,
               COALESCE(pi.identifier, ''),
               COALESCE(pn.given_name, ''),
               COALESCE(pn.family_name, '')
        FROM patient pa
        JOIN person p ON p.person_id = pa.patient_id
        LEFT JOIN patient_identifier pi
          ON pi.patient_id = pa.patient_id AND pi.voided = 0 AND pi.preferred = 1
        LEFT JOIN person_name pn
          ON pn.person_id = p.person_id AND pn.voided = 0 AND pn.preferred = 1
        WHERE pa.voided = 0 AND p.voided = 0
        """
    )
    odoo = odoo_reader()
    active_uuids: set[str] = set()
    active_refs: set[str] = set()
    inactive_by_uuid: dict[str, int] = {}
    inactive_by_ref: dict[str, int] = {}
    for row in _billing_records(odoo):
        partner_id = int(row["id"])
        patient_uuid = str(row.get("uuid") or "").strip()
        ref = str(row.get("ref") or "").strip()
        if row.get("active"):
            if patient_uuid:
                active_uuids.add(patient_uuid)
            if ref:
                active_refs.add(ref)
            continue
        if patient_uuid and patient_uuid not in inactive_by_uuid:
            inactive_by_uuid[patient_uuid] = partner_id
        if ref and ref not in inactive_by_ref:
            inactive_by_ref[ref] = partner_id
    opened = 0
    failed = 0
    missing = 0
    for patient_uuid, identifier, given, family in patients:
        chart_number = str(identifier or "").strip()
        if patient_uuid in active_uuids or (chart_number and chart_number in active_refs):
            continue
        missing += 1
        inactive_id = inactive_by_uuid.get(patient_uuid) or (
            inactive_by_ref.get(chart_number) if chart_number else None
        )
        if inactive_id:
            try:
                execute(odoo, "res.partner", "write", [[inactive_id], {"active": True}])
            except Exception as error:
                failed += 1
                print(f"bill account was not reopened: {error}", flush=True)
                continue
            opened += 1
            active_uuids.add(patient_uuid)
            if chart_number:
                active_refs.add(chart_number)
            continue
        name = f"{given or ''} {family or ''}".strip() or chart_number or "Patient"
        partner = ensure_patient_partner(
            odoo,
            {"uuid": patient_uuid, "mrn": chart_number, "name": name},
            wait=False,
        )
        if not partner or not partner.get("id"):
            failed += 1
            continue
        opened += 1
        active_uuids.add(patient_uuid)
        if chart_number:
            active_refs.add(chart_number)
    print(
        f"bill accounts checked {len(patients)}, opened {opened}, still missing {failed}",
        flush=True,
    )
    return {
        "registered": len(patients),
        "missing": missing,
        "opened": opened,
        "failed": failed,
    }


_ACCOUNT_SYNC_STARTED = False
_ACCOUNT_SYNC_LOCK = threading.Lock()


def start_bill_account_sync() -> None:
    """Keep opening bill accounts for patients registered outside this screen."""
    global _ACCOUNT_SYNC_STARTED
    with _ACCOUNT_SYNC_LOCK:
        if _ACCOUNT_SYNC_STARTED:
            return
        _ACCOUNT_SYNC_STARTED = True
    threading.Thread(target=_bill_account_sync_loop, name="bill-accounts", daemon=True).start()


def _bill_account_sync_loop() -> None:
    import time

    while True:
        try:
            open_missing_patient_accounts()
        except Exception as error:
            print(f"bill accounts were not checked: {error}", flush=True)
        time.sleep(180)


def bill_new_card(patient_uuid: str, cookie: str, card_type: str = "individual") -> dict[str, Any] | None:
    """Bill a new hospital card as soon as the patient is registered. No visit is required."""
    patient = load_openmrs_patient(patient_uuid, cookie)
    odoo = odoo_reader()
    if not ensure_patient_partner(odoo, patient, wait=True):
        print("registration card bill was not created: account_not_found", flush=True)
        return None
    return create_registration_charge(
        patient_uuid,
        {"cardType": card_type or "individual"},
        cookie,
    )


def _ensure_new_card_bill(
    patient_uuid: str,
    visit: dict[str, Any] | None,
    cookie: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create the new-card bill when the patient is registered. A visit is not required."""
    if not payload.get("canCreateCharge"):
        return payload
    visit_uuid = str((visit or {}).get("uuid") or "").strip()
    body: dict[str, Any] = {"cardType": payload.get("cardType") or "individual"}
    if visit_uuid:
        body["visitUuid"] = visit_uuid
    try:
        billed = create_registration_charge(
            patient_uuid,
            body,
            cookie,
        )
    except ApiError as error:
        print(
            f"registration card bill was not created: {error.code} {error.message}",
            flush=True,
        )
        return payload
    except Exception as error:
        print(f"registration card bill was not created: {error}", flush=True)
        return payload
    if isinstance(billed, dict) and (
        billed.get("hasCharge") or billed.get("cardAlreadyRegistered") or billed.get("familyCardIssued")
    ):
        return billed
    return payload


def build_registration(patient_uuid: str, cookie: str, visit_uuid: str | None = None) -> dict[str, Any]:
    require_registrar(cookie)
    if visit_uuid:
        visit = load_visit(visit_uuid, patient_uuid, cookie)
    else:
        visit = latest_open_visit(patient_uuid, cookie)
    try:
        payload = _charge_payload(cookie, patient_uuid, visit)
    except ApiError as error:
        if error.status in {502, 503} or error.code in {"odoo_error", "odoo_charge_failed"}:
            return _charge_unavailable_payload(cookie, patient_uuid, visit)
        raise
    if payload.get("partnerFound") is False and not payload.get("hasCharge"):
        try:
            patient = load_openmrs_patient(patient_uuid, cookie)
            if ensure_patient_partner(odoo_reader(), patient, wait=False):
                payload = _charge_payload(cookie, patient_uuid, visit)
        except Exception as error:
            print(f"registration account was not ready: {error}", flush=True)
    return _ensure_new_card_bill(patient_uuid, visit, cookie, payload)


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_charge_failed",
            "The registration fee could not be created. Refresh and try again.",
        ) from error


def create_registration_charge(patient_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_registrar(cookie)
    visit_uuid = str(body.get("visitUuid") or "").strip()
    card_type = str(body.get("cardType") or "individual").strip().lower()
    request_id = str(body.get("requestId") or "").strip()
    charge_ref = visit_uuid or patient_uuid
    visit_key = charge_key(charge_ref)
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
                    "This registration fee is already being created.",
                )
            if state.get("status") == "done":
                visit = load_visit(visit_uuid, patient_uuid, cookie) if visit_uuid else None
                payload = _charge_payload(cookie, patient_uuid, visit, user=user, card_type=card_type)
                payload["alreadyCreated"] = True
                return payload
        for key in keys:
            IDEMPOTENCY[key] = {"status": "pending"}
    try:
        visit = load_visit(visit_uuid, patient_uuid, cookie) if visit_uuid else None
        patient = load_openmrs_patient(patient_uuid, cookie)
        odoo = odoo_reader()
        partner = find_partner(odoo, patient)
        if not partner:
            raise ApiError(
                409,
                "account_not_found",
                "This patient has no financial account yet. Try again in a moment.",
            )
        import hospital_family as household

        family_decision = household.charge_decision(patient_uuid)
        if family_decision.get("familyCardIssued"):
            payload = _charge_payload(cookie, patient_uuid, visit, user=user, card_type="family")
            payload["alreadyCreated"] = True
            payload["canCreateCharge"] = False
            payload["cardAlreadyRegistered"] = True
            payload["familyCardIssued"] = True
            payload["code"] = FAMILY_CARD_ISSUED_CODE
            payload["message"] = FAMILY_CARD_ISSUED_MESSAGE
            payload["blockReason"] = FAMILY_CARD_ISSUED_MESSAGE
            with IDEMPOTENCY_LOCK:
                for key in keys:
                    IDEMPOTENCY[key] = {"status": "done"}
            return payload
        if family_decision.get("canChargeFamilyFee"):
            card_type = "family"
        existing = find_existing_sale(odoo, charge_ref)
        if existing:
            line, sale = existing
            if sale.get("state") == "draft":
                _confirm_sale(odoo, int(sale["id"]))
            payload = _charge_payload(cookie, patient_uuid, visit, user=user, card_type=card_type)
            payload["alreadyCreated"] = True
            with IDEMPOTENCY_LOCK:
                for key in keys:
                    IDEMPOTENCY[key] = {"status": "done"}
            return payload
        prior = find_patient_registration_sale(odoo, int(partner["id"]))
        if prior and not (
            family_decision.get("canChargeFamilyFee") and not sale_line_is_family_card(odoo, prior[0])
        ):
            payload = _charge_payload(cookie, patient_uuid, visit, user=user, card_type=card_type)
            payload["alreadyCreated"] = True
            payload["canCreateCharge"] = False
            payload["cardAlreadyRegistered"] = True
            payload["code"] = CARD_ALREADY_REGISTERED_CODE
            payload["message"] = CARD_ALREADY_REGISTERED_MESSAGE
            payload["blockReason"] = CARD_ALREADY_REGISTERED_MESSAGE
            with IDEMPOTENCY_LOCK:
                for key in keys:
                    IDEMPOTENCY[key] = {"status": "done"}
            return payload
        masters = ensure_registration_masters(odoo)
        card_type, product = product_for_card(masters, card_type)
        shop = masters["shop"]
        product_id = int(product["id"])
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = many2one_id(shop.get("pricelist_id")) or masters.get("pricelist_id") or 1
        price = as_float(product.get("list_price"))
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
                        "origin": charge_ref,
                        "care_setting": "opd",
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": product_id,
                                    "name": product.get("name") or "Registration card",
                                    "product_uom_qty": 1,
                                    "price_unit": price,
                                    "tax_id": [(6, 0, [])],
                                    "external_order_id": visit_key,
                                    "external_id": charge_ref,
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
            execute(odoo, "sale.order.line", "write", [line_ids, {"tax_id": [(6, 0, [])]}])
        _confirm_sale(odoo, sale_id)
        confirmed = odoo.read("sale.order", [sale_id], ["state", "invoice_ids"])
        if not confirmed or confirmed[0].get("state") not in {"sale", "done"}:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The registration fee could not be created. Refresh and try again.",
            )
        with IDEMPOTENCY_LOCK:
            for key in keys:
                IDEMPOTENCY[key] = {"status": "done"}
        if family_decision.get("canChargeFamilyFee") and family_decision.get("family"):
            household.mark_fee_billed(
                family_decision["family"]["familyId"],
                user,
                patient_uuid=patient_uuid,
            )
        payload = _charge_payload(cookie, patient_uuid, visit, user=user, card_type=card_type)
        payload["alreadyCreated"] = False
        payload["recordedBy"] = user.get("username") or ""
        payload["feeGenerated"] = bool(family_decision.get("canChargeFamilyFee"))
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
