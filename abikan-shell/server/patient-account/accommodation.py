"""Accommodation daily charges.

OpenMRS/Bahmni remains the occupancy source of truth. Odoo remains the
financial ledger. Hospital EMR creates departmental Accommodation invoices after
an actual bed assignment. Clinical ADT must never fail because of billing.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import xmlrpc.client

import server as core

ADMIN_ROLES = {"SuperAdmin", "System Developer"}
ADT_PRIVILEGE = "app:adt"
SHOP_NAME = "Accommodation"
CATEGORY_NAME = "Accommodation"
PRICELIST_NAME = "Hospital Accommodation"
NGN_CURRENCY = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
EXTERNAL_PREFIX = "accommodation:"
HOSPITAL_TZ = ZoneInfo("Africa/Lagos")
CHECKOUT_HOUR = 12
TARIFF_MISSING = (
    "Accommodation price is not configured for this bed/ward. "
    "Please contact Hospital Admin to configure the accommodation tariff."
)
BILLING_ATTENTION = "Accommodation billing needs attention."
CHEAPER_TRANSFER = (
    "The patient moved to a lower-priced room on the same day. "
    "The original daily charge was kept. Accounting must decide whether a credit is needed."
)

# One service product per hospital area. default_code = OpenMRS location uuid.
# Prices start at 0 (unconfigured). Charging refuses 0. Do not invent a 28th bed.
AREAS: list[dict[str, Any]] = [
    {
        "name": "Hawawu Maternity Ward",
        "uuid": "f0f005dd-c95d-47f1-894a-b263783dd5e6",
        "beds": 4,
        "priceKind": "bed",
    },
    {
        "name": "Aisha Children Ward",
        "uuid": "652ff562-62e2-4a0c-8564-f17df728d731",
        "beds": 3,
        "priceKind": "bed",
    },
    {
        "name": "Emergency Room",
        "uuid": "0a6ba74e-6ef3-4906-8e84-236303fa2679",
        "beds": 2,
        "priceKind": "bed",
    },
    {
        "name": "Gold Room 203",
        "uuid": "5f5fe128-3575-48e8-a496-3e057b4fdfda",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Gold Room 202",
        "uuid": "ea1f2988-b000-4b76-b717-eb22611e85eb",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Gold Room 204",
        "uuid": "cf44c30d-8d9f-49e8-a0c1-ce57619f1e57",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Silver 207",
        "uuid": "4decab9e-62ef-48b1-8503-c79210abfeab",
        "beds": 2,
        "priceKind": "bed",
    },
    {
        "name": "Bronze 208",
        "uuid": "bac29e77-fc4f-4fdd-8d5c-4690ca670b19",
        "beds": 3,
        "priceKind": "bed",
    },
    {
        "name": "Gold Room 210",
        "uuid": "03f4a978-bbcf-4d6a-ba81-9f6791a37e2d",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Gold Room 211",
        "uuid": "1c8b96c6-e8b7-4303-b74a-284ec62c6a88",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Platinum Room 209",
        "uuid": "41d5b1a3-8fdb-4820-bb00-9df4cf44383d",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Diamond 214",
        "uuid": "dc70601e-22d0-49dc-ae85-cec2d698c2d1",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Pre Labour Room",
        "uuid": "7291117d-ae8d-481f-8c09-95d973e83f78",
        "beds": 2,
        "priceKind": "bed",
    },
    {
        "name": "Gold Room 212",
        "uuid": "76e48736-2a67-4b1e-b3e4-b9712d545770",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Gold Room 213",
        "uuid": "fae357f1-c85f-4bd1-a996-bed4decad692",
        "beds": 1,
        "priceKind": "room",
    },
    {
        "name": "Silver 206",
        "uuid": "9971567f-8dbb-4cab-89f2-9269204758f1",
        "beds": 2,
        "priceKind": "bed",
    },
    {
        "name": "ICPU",
        "uuid": "bde025ba-d264-434c-90cf-9a61bd78c589",
        "beds": 1,
        "priceKind": "room",
    },
]
AREA_BY_UUID = {row["uuid"]: row for row in AREAS}

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


def accommodation_currency(odoo: OdooReader, currency_id: int | None = None) -> dict[str, Any]:
    ngn_id = _ngn_currency_id(odoo)
    chosen = currency_id or ngn_id
    if chosen:
        loaded = load_currency(odoo, chosen)
        if ngn_id and chosen == ngn_id:
            return {**loaded, "code": "NGN", "symbol": "₦", "position": "before"}
        return loaded
    return dict(NGN_CURRENCY)


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


def _is_admin(user: dict[str, Any]) -> bool:
    return bool(set(user.get("roles") or []) & ADMIN_ROLES)


def _can_manage_tariffs(user: dict[str, Any]) -> bool:
    from hospital_admin import is_hospital_admin

    return is_hospital_admin(user)


def require_admin_user(cookie: str) -> dict[str, Any]:
    """Hospital Admin or SuperAdmin may read and write accommodation tariffs."""
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not _can_manage_tariffs(user):
        raise ApiError(403, "forbidden", "This action requires hospital administration.")
    return user


def require_tariff_reader(cookie: str) -> dict[str, Any]:
    """Ward staff and administrators may view bed and room prices."""
    return require_ward_or_admin(cookie)


def require_ward_or_admin(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    privileges = set(user.get("privileges") or [])
    if _is_admin(user) or ADT_PRIVILEGE in privileges:
        return user
    raise ApiError(403, "forbidden", "This action requires the ward workspace.")


def parse_openmrs_dt(value: str | None) -> datetime:
    text = (value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    text = text.replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", text):
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_as_of(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return parse_openmrs_dt(str(value))


def now_or(as_of: datetime | None) -> datetime:
    return as_of or datetime.now(timezone.utc)


def to_lagos(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(HOSPITAL_TZ)


def day1_date(start: datetime) -> Any:
    return to_lagos(start).date()


def first_extra_checkout(start: datetime) -> datetime:
    day = day1_date(start) + timedelta(days=1)
    return datetime.combine(day, time(CHECKOUT_HOUR, 0), tzinfo=HOSPITAL_TZ)


def still_on_first_day(start: datetime, moment: datetime) -> bool:
    return to_lagos(moment) < first_extra_checkout(start)


def extra_checkout_moments(start: datetime, end: datetime) -> list[datetime]:
    moments: list[datetime] = []
    cursor = first_extra_checkout(start)
    end_lagos = to_lagos(end)
    while cursor <= end_lagos:
        moments.append(cursor)
        cursor += timedelta(days=1)
    return moments


def staff_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%d %b").lstrip("0")
    return str(value)


def product_name_for(area_name: str) -> str:
    return f"Accommodation — {area_name}"


def charge_key(assignment_key: str, billing_date: Any, *, upgrade: bool = False) -> str:
    key = f"{EXTERNAL_PREFIX}{assignment_key}:{billing_date.isoformat()}"
    if upgrade:
        key = f"{key}:upgrade"
    return key


def line_label(area_name: str, bed_number: str, billing_date: Any, *, upgrade: bool = False) -> str:
    when = staff_date(billing_date)
    if upgrade:
        return f"{area_name} · same-day upgrade · {when}"
    bed = (bed_number or "").strip()
    if bed:
        return f"{area_name} · {bed} · {when}"
    return f"{area_name} · {when}"


def area_for_uuid(area_uuid: str) -> dict[str, Any] | None:
    return AREA_BY_UUID.get(str(area_uuid or "").strip())


def ensure_accommodation_masters(odoo: OdooReader) -> dict[str, Any]:
    """Create the Accommodation shop, category, and service products per hospital area.

    Existing list prices are never overwritten. Tax 15% is not changed
    globally; only these products are given empty sales taxes.
    """
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
    products: list[dict[str, Any]] = []
    for area in AREAS:
        name = product_name_for(area["name"])
        found = odoo.search_read(
            "product.product",
            [("default_code", "=", area["uuid"])],
            ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "default_code", "categ_id"],
            limit=1,
        )
        if not found:
            found = odoo.search_read(
                "product.product",
                [("name", "=", name), ("categ_id", "=", category_id)],
                ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "default_code", "categ_id"],
                limit=1,
            )
        if found:
            product = found[0]
            product_id = int(product["id"])
            writes: dict[str, Any] = {}
            if product.get("taxes_id"):
                writes["taxes_id"] = [(6, 0, [])]
            if (product.get("default_code") or "") != area["uuid"]:
                writes["default_code"] = area["uuid"]
            if many2one_id(product.get("categ_id")) != category_id:
                writes["categ_id"] = category_id
            if writes:
                execute(odoo, "product.product", "write", [[product_id], writes])
                product = odoo.read(
                    "product.product",
                    [product_id],
                    ["name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "default_code", "categ_id"],
                )[0]
            products.append(product)
            continue
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
                        "list_price": 0.0,
                        "uom_id": 1,
                        "uom_po_id": 1,
                        "sale_ok": True,
                        "purchase_ok": False,
                        "invoice_policy": "order",
                        "default_code": area["uuid"],
                        "taxes_id": [(6, 0, [])],
                        "supplier_taxes_id": [(6, 0, [])],
                    }
                ],
            )
        )
        execute(odoo, "product.product", "write", [[product_id], {"taxes_id": [(6, 0, [])]}])
        products.append(
            odoo.read(
                "product.product",
                [product_id],
                ["name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "default_code", "categ_id"],
            )[0]
        )
    ngn_id = _ngn_currency_id(odoo)
    pricelists = odoo.search_read(
        "product.pricelist",
        [("name", "ilike", PRICELIST_NAME)],
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
        "shop": shop,
        "category_id": category_id,
        "products": products,
        "pricelist_id": pricelist_id,
    }


def find_accommodation_product(odoo: OdooReader, area_uuid: str) -> dict[str, Any]:
    area = area_for_uuid(area_uuid)
    if not area:
        raise ApiError(409, "unknown_area", TARIFF_MISSING)
    found = odoo.search_read(
        "product.product",
        [("default_code", "=", area["uuid"]), ("type", "=", "service")],
        ["id", "name", "list_price", "type", "uom_id", "taxes_id", "invoice_policy", "default_code", "categ_id"],
        limit=1,
    )
    if not found:
        raise ApiError(409, "tariff_missing", TARIFF_MISSING)
    return found[0]


def approved_tariff(product: dict[str, Any]) -> float:
    price = as_float(product.get("list_price"))
    if price <= 0:
        raise ApiError(409, "tariff_missing", TARIFF_MISSING)
    return price


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


def find_existing_sale(odoo: OdooReader, key: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    lines = odoo.search_read(
        "sale.order.line",
        [("external_order_id", "=", key)],
        ["order_id", "product_id", "product_uom_qty", "price_unit", "external_order_id", "external_id", "name"],
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


def accommodation_lines_for_partner(odoo: OdooReader, partner_id: int) -> list[dict[str, Any]]:
    shops = odoo.search_read("sale.shop", [("name", "=", SHOP_NAME)], ["id"], limit=1)
    domain: list[Any] = [("partner_id", "=", partner_id)]
    if shops:
        domain.append(("shop_id", "=", int(shops[0]["id"])))
    sales = odoo.search_read("sale.order", domain, ["id"], limit=200)
    sale_ids = [int(row["id"]) for row in sales]
    if not sale_ids:
        return []
    return odoo.search_read(
        "sale.order.line",
        [("order_id", "in", sale_ids), ("external_order_id", "=like", f"{EXTERNAL_PREFIX}%")],
        ["order_id", "product_id", "product_uom_qty", "price_unit", "external_order_id", "external_id", "name"],
        limit=500,
    )


def billed_amount_for_date(
    odoo: OdooReader,
    partner_id: int,
    billing_date: Any,
    assignment_keys: list[str] | None = None,
) -> float:
    date_s = billing_date.isoformat()
    allowed = set(assignment_keys) if assignment_keys is not None else None
    total = 0.0
    for line in accommodation_lines_for_partner(odoo, partner_id):
        key = str(line.get("external_order_id") or "")
        parts = key.split(":")
        if len(parts) < 3 or parts[0] != "accommodation" or parts[2] != date_s:
            continue
        if allowed is not None and parts[1] not in allowed:
            continue
        qty = as_float(line.get("product_uom_qty")) or 1.0
        total += as_float(line.get("price_unit")) * qty
    return total


def stay_assignment_keys(patient_uuid: str, cookie: str, extra: str | None = None) -> list[str]:
    keys = [str(row["uuid"]) for row in list_adt_encounters(patient_uuid, cookie)]
    if extra and extra not in keys:
        keys.append(extra)
    return keys


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(502, "odoo_charge_failed", BILLING_ATTENTION) from error


def create_posted_charge(
    odoo: OdooReader,
    *,
    partner: dict[str, Any],
    product: dict[str, Any],
    price: float,
    key: str,
    external_id: str,
    name: str,
    origin: str,
    request_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    existing = find_existing_sale(odoo, key)
    if existing:
        return existing[0], existing[1], True
    if price <= 0:
        raise ApiError(409, "tariff_missing", TARIFF_MISSING)
    keys = [key]
    if request_id:
        keys.append(request_id)
    with IDEMPOTENCY_LOCK:
        for item in keys:
            state = IDEMPOTENCY.get(item) or {}
            if state.get("status") == "pending":
                raise ApiError(409, "charge_in_progress", "This accommodation charge is already being created.")
            if state.get("status") == "done":
                again = find_existing_sale(odoo, key)
                if again:
                    return again[0], again[1], True
        for item in keys:
            IDEMPOTENCY[item] = {"status": "pending"}
    try:
        again = find_existing_sale(odoo, key)
        if again:
            with IDEMPOTENCY_LOCK:
                for item in keys:
                    IDEMPOTENCY[item] = {"status": "done"}
            return again[0], again[1], True
        masters = ensure_accommodation_masters(odoo)
        shop = masters["shop"]
        pricelist_id = many2one_id(shop.get("pricelist_id")) or masters.get("pricelist_id") or 1
        currency_id = _ngn_currency_id(odoo) or many2one_id(
            (odoo.read("product.pricelist", [pricelist_id], ["currency_id"]) or [{}])[0].get(
                "currency_id"
            )
        )
        sale_id = int(
            execute(
                odoo,
                "sale.order",
                "create",
                [
                    {
                        "partner_id": int(partner["id"]),
                        "shop_id": int(shop["id"]),
                        "warehouse_id": many2one_id(shop.get("warehouse_id")) or 1,
                        "pricelist_id": pricelist_id,
                        "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                        **({"currency_id": int(currency_id)} if currency_id else {}),
                        "origin": origin,
                        "care_setting": "opd",
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": int(product["id"]),
                                    "name": name,
                                    "product_uom_qty": 1,
                                    "price_unit": price,
                                    "tax_id": [(6, 0, [])],
                                    "external_order_id": key,
                                    "external_id": external_id,
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
                [line_ids, {"tax_id": [(6, 0, [])], "price_unit": price, "name": name}],
            )
        _confirm_sale(odoo, sale_id)
        confirmed = odoo.read("sale.order", [sale_id], ["state", "invoice_ids", "name", "amount_total", "currency_id"])
        if not confirmed or confirmed[0].get("state") not in {"sale", "done"}:
            raise ApiError(502, "odoo_charge_failed", BILLING_ATTENTION)
        created = find_existing_sale(odoo, key)
        if not created:
            raise ApiError(502, "odoo_charge_failed", BILLING_ATTENTION)
        with IDEMPOTENCY_LOCK:
            for item in keys:
                IDEMPOTENCY[item] = {"status": "done"}
        return created[0], created[1], False
    except ApiError:
        with IDEMPOTENCY_LOCK:
            for item in keys:
                if (IDEMPOTENCY.get(item) or {}).get("status") == "pending":
                    IDEMPOTENCY.pop(item, None)
        raise
    except Exception:
        with IDEMPOTENCY_LOCK:
            for item in keys:
                if (IDEMPOTENCY.get(item) or {}).get("status") == "pending":
                    IDEMPOTENCY.pop(item, None)
        raise


def notice(
    *,
    status: str,
    message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"status": status, "message": message}
    if extra:
        payload.update(extra)
    return payload


def billing_from_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, ApiError):
        if error.code == "tariff_missing":
            return notice(status="tariff_missing", message=error.message)
        if error.code == "account_not_found":
            return notice(status="needs_attention", message=error.message)
        return notice(status="needs_attention", message=error.message or BILLING_ATTENTION)
    return notice(status="needs_attention", message=BILLING_ATTENTION)


def list_adt_encounters(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    """Encounters in the current stay: latest ADMISSION plus later transfers."""
    rows = [
        row
        for row in _list_stay_encounters(patient_uuid, cookie)
        if row.get("kind") in {"admission", "transfer"}
    ]
    latest_admission = next((row for row in rows if row.get("kind") == "admission"), None)
    if not latest_admission:
        return rows
    return [row for row in rows if row["datetime"] >= latest_admission["datetime"]]


def _list_stay_encounters(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    import inpatient as ward

    kinds = (
        (ward.ADMISSION_ENCOUNTER, "admission"),
        (ward.TRANSFER_ENCOUNTER, "transfer"),
        (ward.DISCHARGE_ENCOUNTER, "discharge"),
    )
    rows: list[dict[str, Any]] = []
    for encounter_type, kind in kinds:
        payload = ward.openmrs_call(
            "GET",
            f"/openmrs/ws/rest/v1/encounter?patient={quote(patient_uuid)}"
            f"&encounterType={encounter_type}&v=custom:(uuid,encounterDatetime)&limit=50",
            cookie,
        )
        for row in payload.get("results") or []:
            if not isinstance(row, dict) or not row.get("uuid"):
                continue
            rows.append(
                {
                    "uuid": str(row["uuid"]),
                    "datetime": parse_openmrs_dt(str(row.get("encounterDatetime") or "")),
                    "raw": str(row.get("encounterDatetime") or ""),
                    "kind": kind,
                }
            )
    rows.sort(key=lambda row: row["datetime"], reverse=True)
    return rows


def current_segment(
    patient_uuid: str,
    cookie: str,
    *,
    encounter_uuid: str | None = None,
    start: datetime | None = None,
) -> dict[str, Any] | None:
    if encounter_uuid and start:
        return {"encounterUuid": encounter_uuid, "start": start}
    rows = list_adt_encounters(patient_uuid, cookie)
    if encounter_uuid:
        match = next((row for row in rows if row["uuid"] == encounter_uuid), None)
        if match:
            return {"encounterUuid": match["uuid"], "start": start or match["datetime"]}
    if not rows:
        return None
    latest = rows[0]
    return {"encounterUuid": latest["uuid"], "start": start or latest["datetime"]}


def _partner_or_notice(odoo: OdooReader, patient_uuid: str, cookie: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    patient = load_openmrs_patient(patient_uuid, cookie)
    partner = find_partner(odoo, patient)
    if not partner:
        return None, notice(
            status="needs_attention",
            message="This patient has no financial account yet. Accommodation can be billed when the account is ready.",
        )
    return partner, None


def _charge_day(
    odoo: OdooReader,
    *,
    partner: dict[str, Any],
    area_uuid: str,
    area_name: str,
    bed_number: str,
    assignment_key: str,
    billing_date: Any,
    origin: str,
    request_id: str | None = None,
    upgrade: bool = False,
    price: float | None = None,
) -> dict[str, Any]:
    product = find_accommodation_product(odoo, area_uuid)
    tariff = approved_tariff(product) if price is None else price
    key = charge_key(assignment_key, billing_date, upgrade=upgrade)
    line, sale, reused = create_posted_charge(
        odoo,
        partner=partner,
        product=product,
        price=tariff,
        key=key,
        external_id=assignment_key,
        name=line_label(area_name, bed_number, billing_date, upgrade=upgrade),
        origin=origin,
        request_id=request_id,
    )
    return {
        "key": key,
        "reused": reused,
        "saleName": sale.get("name"),
        "amount": as_float(line.get("price_unit")),
        "upgrade": upgrade,
    }


def catch_up_extras(
    odoo: OdooReader,
    *,
    partner: dict[str, Any],
    area_uuid: str,
    area_name: str,
    bed_number: str,
    assignment_key: str,
    start: datetime,
    end: datetime,
    stay_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    product = find_accommodation_product(odoo, area_uuid)
    tariff = approved_tariff(product)
    partner_id = int(partner["id"])
    keys = stay_keys or [assignment_key]
    for moment in extra_checkout_moments(start, end):
        billing_date = moment.date()
        key = charge_key(assignment_key, billing_date)
        if find_existing_sale(odoo, key):
            continue
        if billed_amount_for_date(odoo, partner_id, billing_date, keys) > 0:
            continue
        created.append(
            _charge_day(
                odoo,
                partner=partner,
                area_uuid=area_uuid,
                area_name=area_name,
                bed_number=bed_number,
                assignment_key=assignment_key,
                billing_date=billing_date,
                origin=assignment_key,
                price=tariff,
            )
        )
    return created


def ensure_day_one(
    odoo: OdooReader,
    *,
    partner: dict[str, Any],
    area_uuid: str,
    area_name: str,
    bed_number: str,
    assignment_key: str,
    start: datetime,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    billing_date = day1_date(start)
    if find_existing_sale(odoo, charge_key(assignment_key, billing_date)):
        return None
    return _charge_day(
        odoo,
        partner=partner,
        area_uuid=area_uuid,
        area_name=area_name,
        bed_number=bed_number,
        assignment_key=assignment_key,
        billing_date=billing_date,
        origin=assignment_key,
        request_id=request_id,
    )


def summarize_billing(patient_uuid: str, cookie: str, odoo: OdooReader | None = None) -> dict[str, Any]:
    try:
        reader = odoo or odoo_reader()
        ensure_accommodation_masters(reader)
        patient = load_openmrs_patient(patient_uuid, cookie)
        partner = find_partner(reader, patient)
        currency = accommodation_currency(reader)
        if not partner:
            return notice(
                status="needs_attention",
                message="This patient has no financial account yet.",
                extra={"paymentLabel": None},
            )
        sales = []
        shops = reader.search_read("sale.shop", [("name", "=", SHOP_NAME)], ["id"], limit=1)
        domain: list[Any] = [("partner_id", "=", int(partner["id"]))]
        if shops:
            domain.append(("shop_id", "=", int(shops[0]["id"])))
        sales = reader.search_read(
            "sale.order",
            domain,
            ["name", "state", "invoice_ids", "amount_total", "currency_id"],
            limit=200,
        )
        invoices = []
        for sale in sales:
            invoice = related_invoice(reader, sale)
            if invoice:
                invoices.append(invoice)
        if not invoices:
            return notice(status="ok", message=None, extra={"paymentLabel": None, "chargeCount": 0})
        currency_ids = {
            many2one_id(row.get("currency_id"))
            for row in invoices
            if many2one_id(row.get("currency_id"))
        }
        if len(currency_ids) == 1:
            currency = accommodation_currency(reader, next(iter(currency_ids)))
        residual = sum(as_float(row.get("amount_residual")) for row in invoices)
        total = sum(as_float(row.get("amount_total")) for row in invoices)
        paid = max(0.0, total - residual)
        states = {str(row.get("payment_state") or "") for row in invoices}
        if residual <= 0.009 and states <= {"paid", "in_payment"}:
            label = "PAID"
        elif paid > 0.009 and residual > 0.009:
            label = "PARTIALLY PAID"
        else:
            label = "OUTSTANDING"
        return notice(
            status="ok",
            message=None,
            extra={
                "paymentLabel": label,
                "chargeCount": len(invoices),
                "outstanding": format_money(residual, currency),
                "paid": format_money(paid, currency),
                "total": format_money(total, currency),
            },
        )
    except ApiError as error:
        return billing_from_error(error)
    except Exception:
        return notice(status="needs_attention", message=BILLING_ATTENTION)


def after_assignment(
    *,
    patient_uuid: str,
    area_uuid: str,
    area_name: str,
    bed_number: str,
    encounter_uuid: str,
    cookie: str,
    start: datetime | None = None,
    request_id: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    try:
        odoo = odoo_reader()
        ensure_accommodation_masters(odoo)
        partner, missing = _partner_or_notice(odoo, patient_uuid, cookie)
        if missing or not partner:
            return missing or notice(status="needs_attention", message=BILLING_ATTENTION)
        moment = now_or(as_of)
        started = start or moment
        assignment_key = encounter_uuid
        created = ensure_day_one(
            odoo,
            partner=partner,
            area_uuid=area_uuid,
            area_name=area_name,
            bed_number=bed_number,
            assignment_key=assignment_key,
            start=started,
            request_id=request_id,
        )
        extras = catch_up_extras(
            odoo,
            partner=partner,
            area_uuid=area_uuid,
            area_name=area_name,
            bed_number=bed_number,
            assignment_key=assignment_key,
            start=started,
            end=moment,
        )
        summary = summarize_billing(patient_uuid, cookie, odoo)
        if created or extras:
            summary["created"] = bool(created) or bool(extras)
        return summary
    except Exception as error:
        return billing_from_error(error)


def after_transfer(
    *,
    patient_uuid: str,
    previous_area_uuid: str,
    previous_area_name: str,
    previous_bed_number: str,
    previous_encounter_uuid: str | None,
    previous_start: datetime | None,
    area_uuid: str,
    area_name: str,
    bed_number: str,
    encounter_uuid: str,
    cookie: str,
    request_id: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    try:
        odoo = odoo_reader()
        ensure_accommodation_masters(odoo)
        partner, missing = _partner_or_notice(odoo, patient_uuid, cookie)
        if missing or not partner:
            return missing or notice(status="needs_attention", message=BILLING_ATTENTION)
        moment = now_or(as_of)
        old_start = previous_start
        old_key = previous_encounter_uuid
        if not old_key or not old_start:
            rows = list_adt_encounters(patient_uuid, cookie)
            older = [row for row in rows if row["uuid"] != encounter_uuid]
            if older:
                old_key = old_key or older[0]["uuid"]
                old_start = old_start or older[0]["datetime"]
        if old_key and old_start:
            try:
                catch_up_extras(
                    odoo,
                    partner=partner,
                    area_uuid=previous_area_uuid,
                    area_name=previous_area_name,
                    bed_number=previous_bed_number,
                    assignment_key=old_key,
                    start=old_start,
                    end=moment,
                    stay_keys=stay_assignment_keys(patient_uuid, cookie, extra=old_key),
                )
            except ApiError as error:
                if error.code != "tariff_missing":
                    raise
        new_product = find_accommodation_product(odoo, area_uuid)
        new_tariff = approved_tariff(new_product)
        partner_id = int(partner["id"])
        stay_keys = stay_assignment_keys(patient_uuid, cookie, extra=encounter_uuid)
        if old_key and old_key not in stay_keys:
            stay_keys.append(old_key)
        if old_start and still_on_first_day(old_start, moment):
            billing_date = day1_date(old_start)
            billed = billed_amount_for_date(odoo, partner_id, billing_date, stay_keys)
            if billed <= 0:
                ensure_day_one(
                    odoo,
                    partner=partner,
                    area_uuid=area_uuid,
                    area_name=area_name,
                    bed_number=bed_number,
                    assignment_key=encounter_uuid,
                    start=moment,
                    request_id=request_id,
                )
            elif new_tariff > billed + 0.009:
                _charge_day(
                    odoo,
                    partner=partner,
                    area_uuid=area_uuid,
                    area_name=area_name,
                    bed_number=bed_number,
                    assignment_key=encounter_uuid,
                    billing_date=billing_date,
                    origin=encounter_uuid,
                    request_id=request_id,
                    upgrade=True,
                    price=round(new_tariff - billed, 2),
                )
            elif new_tariff + 0.009 < billed:
                summary = summarize_billing(patient_uuid, cookie, odoo)
                summary["status"] = "policy_required"
                summary["message"] = CHEAPER_TRANSFER
                return summary
        else:
            billing_date = day1_date(moment)
            billed = billed_amount_for_date(odoo, partner_id, billing_date, stay_keys)
            if billed <= 0:
                ensure_day_one(
                    odoo,
                    partner=partner,
                    area_uuid=area_uuid,
                    area_name=area_name,
                    bed_number=bed_number,
                    assignment_key=encounter_uuid,
                    start=moment,
                    request_id=request_id,
                )
        catch_up_extras(
            odoo,
            partner=partner,
            area_uuid=area_uuid,
            area_name=area_name,
            bed_number=bed_number,
            assignment_key=encounter_uuid,
            start=moment,
            end=moment,
            stay_keys=stay_keys,
        )
        return summarize_billing(patient_uuid, cookie, odoo)
    except Exception as error:
        return billing_from_error(error)


def after_discharge(
    *,
    patient_uuid: str,
    area_uuid: str,
    area_name: str,
    bed_number: str,
    cookie: str,
    encounter_uuid: str | None = None,
    start: datetime | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    try:
        odoo = odoo_reader()
        ensure_accommodation_masters(odoo)
        partner, missing = _partner_or_notice(odoo, patient_uuid, cookie)
        if missing or not partner:
            return missing or notice(status="needs_attention", message=BILLING_ATTENTION)
        moment = now_or(as_of)
        segment = current_segment(patient_uuid, cookie, encounter_uuid=encounter_uuid, start=start)
        if not segment:
            return summarize_billing(patient_uuid, cookie, odoo)
        assignment_key = str(segment["encounterUuid"])
        started = segment["start"]
        try:
            ensure_day_one(
                odoo,
                partner=partner,
                area_uuid=area_uuid,
                area_name=area_name,
                bed_number=bed_number,
                assignment_key=assignment_key,
                start=started,
            )
            catch_up_extras(
                odoo,
                partner=partner,
                area_uuid=area_uuid,
                area_name=area_name,
                bed_number=bed_number,
                assignment_key=assignment_key,
                start=started,
                end=moment,
            )
        except ApiError as error:
            if error.code == "tariff_missing":
                summary = summarize_billing(patient_uuid, cookie, odoo)
                summary["status"] = "tariff_missing"
                summary["message"] = TARIFF_MISSING
                return summary
            raise
        return summarize_billing(patient_uuid, cookie, odoo)
    except Exception as error:
        return billing_from_error(error)


def summarize_and_catch_up(patient_uuid: str, cookie: str, as_of: datetime | None = None) -> dict[str, Any]:
    try:
        import inpatient as ward

        assignment = ward.current_assignment(patient_uuid, cookie, scan_board=True)
        if not assignment:
            return summarize_billing(patient_uuid, cookie)
        segment = current_segment(patient_uuid, cookie)
        if not segment:
            return summarize_billing(patient_uuid, cookie)
        return after_assignment(
            patient_uuid=patient_uuid,
            area_uuid=str(assignment.get("areaUuid") or ""),
            area_name=str(assignment.get("areaName") or ""),
            bed_number=str(assignment.get("bedNumber") or ""),
            encounter_uuid=str(segment["encounterUuid"]),
            cookie=cookie,
            start=segment["start"],
            as_of=as_of,
        )
    except Exception as error:
        return billing_from_error(error)


def attach_billing(stay: dict[str, Any], billing: dict[str, Any] | None) -> dict[str, Any]:
    stay["billing"] = billing
    return stay


def safe_billing(callback: Any) -> dict[str, Any]:
    try:
        return callback()
    except Exception as error:
        return billing_from_error(error)


def list_tariffs(cookie: str) -> dict[str, Any]:
    user = require_tariff_reader(cookie)
    odoo = odoo_reader()
    masters = ensure_accommodation_masters(odoo)
    currency = accommodation_currency(odoo)
    items = []
    products = {str(row.get("default_code") or ""): row for row in masters["products"]}
    for area in AREAS:
        product = products.get(area["uuid"])
        if product is None:
            try:
                product = find_accommodation_product(odoo, area["uuid"])
            except ApiError:
                product = {}
        price = as_float((product or {}).get("list_price"))
        items.append(
            {
                "areaUuid": area["uuid"],
                "areaName": area["name"],
                "beds": area["beds"],
                "priceKind": area["priceKind"],
                "priceKindLabel": (
                    "Price per occupied bed" if area["priceKind"] == "bed" else "Price per room"
                ),
                "listPrice": format_money(price, currency),
                "configured": price > 0,
            }
        )
    return {
        "status": "ok",
        "currency": {
            "code": currency.get("code"),
            "symbol": currency.get("symbol"),
            "decimalPlaces": currency.get("decimalPlaces"),
        },
        "areas": items,
        "canEdit": _can_manage_tariffs(user),
        "message": "Patient hospital services are tax-exempt. These prices have no patient tax.",
    }


def save_tariff(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_admin_user(cookie)
    area_uuid = str(body.get("areaUuid") or "").strip()
    request_id = str(body.get("requestId") or "").strip()
    if area_uuid not in AREA_BY_UUID:
        raise ApiError(422, "unknown_area", "Choose a hospital ward or room.")
    try:
        price = float(body.get("listPrice"))
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_price", "Enter a daily price.") from error
    if price < 0:
        raise ApiError(422, "invalid_price", "The daily price cannot be negative.")
    if request_id:
        with IDEMPOTENCY_LOCK:
            prior = IDEMPOTENCY.get(request_id) or {}
            if prior.get("status") == "done" and prior.get("areaUuid") == area_uuid:
                return list_tariffs(cookie)
            IDEMPOTENCY[request_id] = {"status": "pending", "areaUuid": area_uuid}
    try:
        odoo = odoo_reader()
        ensure_accommodation_masters(odoo)
        product = find_accommodation_product(odoo, area_uuid)
        old_price = as_float(product.get("list_price"))
        execute(
            odoo,
            "product.product",
            "write",
            [[int(product["id"])], {"list_price": price, "taxes_id": [(6, 0, [])]}],
        )
        import price_history

        area = AREA_BY_UUID[area_uuid]
        price_history.record_price_change(
            department="accommodation",
            item_id=area_uuid,
            item_label=str(area.get("name") or area_uuid),
            currency="NGN",
            old_price=old_price,
            new_price=price,
            actor={
                "uuid": str(user.get("uuid") or ""),
                "username": str(user.get("username") or ""),
                "display": str(user.get("display") or user.get("username") or ""),
            },
            reason="Accommodation daily price",
        )
        if request_id:
            with IDEMPOTENCY_LOCK:
                IDEMPOTENCY[request_id] = {"status": "done", "areaUuid": area_uuid}
        payload = list_tariffs(cookie)
        payload["savedAreaUuid"] = area_uuid
        return payload
    except Exception:
        if request_id:
            with IDEMPOTENCY_LOCK:
                if (IDEMPOTENCY.get(request_id) or {}).get("status") == "pending":
                    IDEMPOTENCY.pop(request_id, None)
        raise


def catch_up_request(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_ward_or_admin(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    as_of = parse_as_of(body.get("asOf"))
    if as_of and not _is_admin(user):
        raise ApiError(403, "forbidden", "This action requires an administrator.")
    if patient_uuid:
        billing = summarize_and_catch_up(patient_uuid, cookie, as_of=as_of)
        return {"status": "ok", "patientUuid": patient_uuid, "billing": billing}
    import inpatient as ward

    board = ward.build_board(cookie)
    results = []
    for area in board.get("areas") or []:
        for bed in area.get("beds") or []:
            occupant = str(bed.get("patientUuid") or "")
            if not occupant:
                continue
            results.append(
                {
                    "patientUuid": occupant,
                    "areaName": bed.get("areaName"),
                    "bedNumber": bed.get("bedNumber"),
                    "billing": summarize_and_catch_up(occupant, cookie, as_of=as_of),
                }
            )
    return {"status": "ok", "patients": results}


def retry_charge(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    require_ward_or_admin(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    if not patient_uuid:
        raise ApiError(422, "invalid_body", "Choose a patient.")
    as_of = parse_as_of(body.get("asOf"))
    user = load_openmrs_user(cookie)
    if as_of and not _is_admin(user):
        raise ApiError(403, "forbidden", "This action requires an administrator.")
    billing = summarize_and_catch_up(patient_uuid, cookie, as_of=as_of)
    return {"status": "ok", "patientUuid": patient_uuid, "billing": billing}
