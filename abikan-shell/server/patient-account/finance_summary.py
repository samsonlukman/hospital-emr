"""Shared Odoo finance totals for Accountant and Hospital Admin.

Odoo remains the financial source of truth. These helpers never total Hospital EMR
local payment copies.

Billed
    Posted customer invoices whose invoice_date falls in the selected
    Africa/Lagos business range, inclusive.

Collected
    Posted inbound customer payments whose payment date falls in the selected
    Africa/Lagos business range, inclusive.

Outstanding
    Current residual on posted customer invoices. This is a snapshot, not the
    outstanding balance as of the selected dates.
"""

from __future__ import annotations

import logging
from typing import Any

import xmlrpc.client

import admin_period as periods
import server as core

LOGGER = logging.getLogger(__name__)

NONE_MARSHAL = "cannot marshal None"


def billed_domain(start_date: str, end_date: str) -> list[Any]:
    return [
        ("move_type", "=", "out_invoice"),
        ("state", "=", "posted"),
        ("invoice_date", ">=", start_date),
        ("invoice_date", "<=", end_date),
    ]


def collected_domain(start_date: str, end_date: str) -> list[Any]:
    return [
        ("partner_type", "=", "customer"),
        ("payment_type", "=", "inbound"),
        ("state", "=", "posted"),
        ("date", ">=", start_date),
        ("date", "<=", end_date),
    ]


def outstanding_domain() -> list[Any]:
    return [
        ("move_type", "=", "out_invoice"),
        ("state", "=", "posted"),
    ]


def refund_domain(start_date: str, end_date: str) -> list[Any]:
    return [
        ("move_type", "=", "out_refund"),
        ("state", "=", "posted"),
        ("invoice_date", ">=", start_date),
        ("invoice_date", "<=", end_date),
    ]


def hospital_business_date(now: Any = None) -> str:
    return periods.hospital_today(now).isoformat()


def _sum_search_read(odoo: Any, model: str, domain: list[Any], field: str) -> float:
    rows = odoo.search_read(model, domain, [field], limit=10000)
    return sum(core.as_float(row.get(field)) for row in rows)


def odoo_sum(odoo: Any, model: str, domain: list[Any], field: str) -> float:
    """Sum an Odoo field. An empty range is 0, not a transport failure.

    Odoo XML-RPC cannot marshal None. A read_group with no matching rows
    returns amount=None and the RPC call fails. That is an empty total.
    """
    try:
        rows = odoo.models.execute_kw(
            core.ODOO_DB,
            odoo.uid,
            core.ODOO_PASSWORD,
            model,
            "read_group",
            [domain, [f"{field}:sum"], []],
            {"lazy": False},
        )
    except xmlrpc.client.Fault as error:
        fault = str(error)
        if NONE_MARSHAL not in fault:
            LOGGER.warning("odoo_sum %s.%s failed domain=%s error=%s", model, field, domain, fault)
            raise
        LOGGER.info("odoo_sum %s.%s empty aggregate for %s; summing rows", model, field, domain)
        return _sum_search_read(odoo, model, domain, field)
    if not rows:
        return 0.0
    return core.as_float(rows[0].get(field))


def collected_outbound_domain(start_date: str, end_date: str) -> list[Any]:
    return [
        ("partner_type", "=", "customer"),
        ("payment_type", "=", "outbound"),
        ("state", "=", "posted"),
        ("date", ">=", start_date),
        ("date", "<=", end_date),
    ]


def billed_total(odoo: Any, start_date: str, end_date: str) -> float:
    invoiced = odoo_sum(odoo, "account.move", billed_domain(start_date, end_date), "amount_total")
    refunded = odoo_sum(odoo, "account.move", refund_domain(start_date, end_date), "amount_total")
    return round(max(invoiced - refunded, 0.0), 2)


def collected_total(odoo: Any, start_date: str, end_date: str) -> float:
    inbound = odoo_sum(odoo, "account.payment", collected_domain(start_date, end_date), "amount")
    outbound = odoo_sum(
        odoo, "account.payment", collected_outbound_domain(start_date, end_date), "amount"
    )
    return round(max(inbound - outbound, 0.0), 2)


def outstanding_total(odoo: Any) -> float:
    return odoo_sum(odoo, "account.move", outstanding_domain(), "amount_residual")


def collected_count(odoo: Any, start_date: str, end_date: str) -> int:
    domain = collected_domain(start_date, end_date)
    try:
        return int(odoo.search_count("account.payment", domain))
    except AttributeError:
        return len(odoo.search_read("account.payment", domain, ["id"], limit=10000))


REVENUE_DEPARTMENTS = (
    "Registration",
    "Consultation",
    "Laboratory",
    "Radiology",
    "Pharmacy",
    "Accommodation",
    "Theatre",
    "Physiotherapy",
    "Dental",
)
UNIDENTIFIED_DEPARTMENT = "Department not identified"


def _invoice_category_names(odoo: Any, invoices: list[dict[str, Any]]) -> dict[int, list[str]]:
    line_ids: list[int] = []
    for invoice in invoices:
        line_ids.extend(int(line_id) for line_id in (invoice.get("invoice_line_ids") or []))
    if not line_ids:
        return {}
    lines = odoo.read("account.move.line", line_ids, ["move_id", "product_id"])
    product_ids = [
        core.many2one_id(line.get("product_id"))
        for line in lines
        if core.many2one_id(line.get("product_id"))
    ]
    products = {
        int(row["id"]): row
        for row in (odoo.read("product.product", product_ids, ["categ_id"]) if product_ids else [])
    }
    category_ids = [
        core.many2one_id(product.get("categ_id"))
        for product in products.values()
        if core.many2one_id(product.get("categ_id"))
    ]
    categories = {
        int(row["id"]): row
        for row in (
            odoo.read("product.category", category_ids, ["name", "complete_name"])
            if category_ids
            else []
        )
    }
    by_move: dict[int, list[str]] = {}
    for line in lines:
        move_id = core.many2one_id(line.get("move_id"))
        if not move_id:
            continue
        product = products.get(core.many2one_id(line.get("product_id")) or 0) or {}
        category = categories.get(core.many2one_id(product.get("categ_id")) or 0) or {}
        names = [
            str(name)
            for name in (category.get("complete_name"), category.get("name"))
            if name
        ]
        by_move.setdefault(int(move_id), []).extend(names)
    return by_move


def billed_by_department(odoo: Any, start_date: str, end_date: str) -> dict[str, float]:
    """Posted invoice totals by originating department.

    Uses the same posted-invoice domain as billed_total. Draft, cancelled, and
    reversed invoices are excluded. Attribution reuses identify_department
    (sale shop, then product category).
    """
    invoices = odoo.search_read(
        "account.move",
        billed_domain(start_date, end_date),
        ["id", "name", "invoice_origin", "amount_total", "payment_state", "invoice_line_ids"],
        limit=10000,
    )
    totals = {name: 0.0 for name in REVENUE_DEPARTMENTS}
    origins = sorted(
        {
            str(row.get("invoice_origin") or "")
            for row in invoices
            if row.get("invoice_origin")
        }
    )
    orders = (
        odoo.search_read(
            "sale.order",
            [("name", "in", origins)],
            ["name", "shop_id"],
            limit=10000,
        )
        if origins
        else []
    )
    order_by_name = {str(row.get("name") or ""): row for row in orders}
    unmatched: list[dict[str, Any]] = []
    for invoice in invoices:
        if invoice.get("payment_state") == "reversed":
            continue
        amount = core.as_float(invoice.get("amount_total"))
        origin = str(invoice.get("invoice_origin") or "")
        shop = core.many2one_name((order_by_name.get(origin) or {}).get("shop_id"))
        department = core.identify_department(shop, [])
        if department:
            totals[department] = totals.get(department, 0.0) + amount
        else:
            unmatched.append(invoice)
    if unmatched:
        categories_by_move = _invoice_category_names(odoo, unmatched)
        for invoice in unmatched:
            amount = core.as_float(invoice.get("amount_total"))
            department = core.identify_department(
                "",
                categories_by_move.get(int(invoice["id"]), []),
            )
            key = department or UNIDENTIFIED_DEPARTMENT
            totals[key] = totals.get(key, 0.0) + amount

    # Net posted credit notes so Pharmacy (and other) refunds reduce revenue.
    refunds = odoo.search_read(
        "account.move",
        refund_domain(start_date, end_date),
        ["id", "invoice_origin", "amount_total", "invoice_line_ids", "ref"],
        limit=10000,
    )
    refund_origins = sorted(
        {
            str(row.get("invoice_origin") or "")
            for row in refunds
            if row.get("invoice_origin")
        }
    )
    refund_orders = (
        odoo.search_read(
            "sale.order",
            [("name", "in", refund_origins)],
            ["name", "shop_id"],
            limit=10000,
        )
        if refund_origins
        else []
    )
    refund_order_by_name = {str(row.get("name") or ""): row for row in refund_orders}
    unmatched_refunds: list[dict[str, Any]] = []
    for credit in refunds:
        amount = core.as_float(credit.get("amount_total"))
        origin = str(credit.get("invoice_origin") or "")
        shop = core.many2one_name((refund_order_by_name.get(origin) or {}).get("shop_id"))
        department = core.identify_department(shop, [])
        if department:
            totals[department] = totals.get(department, 0.0) - amount
        else:
            unmatched_refunds.append(credit)
    if unmatched_refunds:
        categories_by_move = _invoice_category_names(odoo, unmatched_refunds)
        for credit in unmatched_refunds:
            amount = core.as_float(credit.get("amount_total"))
            department = core.identify_department(
                "",
                categories_by_move.get(int(credit["id"]), []),
            )
            key = department or UNIDENTIFIED_DEPARTMENT
            totals[key] = totals.get(key, 0.0) - amount

    return {
        name: round(amount, 2)
        for name, amount in totals.items()
        if name != UNIDENTIFIED_DEPARTMENT or amount != 0
    }
