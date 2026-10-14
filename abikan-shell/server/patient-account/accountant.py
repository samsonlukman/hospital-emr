"""Accountant / Cashier payment operations.

Odoo remains the ledger. Payments go through account.payment.register.
This module does not insert account.payment or reconciliation rows directly.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from decimal import Decimal, InvalidOperation
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import xmlrpc.client

import finance_summary as finance
import server as core

ACCOUNTANT_PRIVILEGE = "abikan:accountant"
ACCOUNTANT_ROLES = {"SuperAdmin", "System Developer"}

ApiError = core.ApiError
OdooReader = core.OdooReader
ODOO_DB = core.ODOO_DB
ODOO_PASSWORD = core.ODOO_PASSWORD
ODOO_URL = core.ODOO_URL
ODOO_USER = core.ODOO_USER
as_float = core.as_float
money_major = core.money_major
money_minor = core.money_minor
build_account = core.build_account
find_partner = core.find_partner
aggregate_by_currency = core.aggregate_by_currency
format_money = core.format_money
load_currency = core.load_currency
staff_currency = core.staff_currency
MIXED_CURRENCY_MESSAGE = core.MIXED_CURRENCY_MESSAGE
load_openmrs_patient = core.load_openmrs_patient
many2one_id = core.many2one_id
many2one_name = core.many2one_name
money_maps = core.money_maps
openmrs_get = core.openmrs_get
payment_state_label = core.payment_state_label
require_session = core.require_session

# Existing Odoo payment receipt. Staff see a Hospital EMR receipt; the xml id is
# the installed report. Hospital EMR does not invent receipt numbers.
PAYMENT_RECEIPT = "bahmni_auto_payment_reconciliation.report_payment_invoice"
STANDARD_RECEIPT = "account.report_payment_receipt"
DISCOUNT_ACCOUNT_ID = os.environ.get("ABIKAN_ODOO_DISCOUNT_ACCOUNT_ID", "").strip()
ELIGIBLE_STATES = {"not_paid", "partial"}
IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}


def load_openmrs_user(cookie: str) -> dict[str, Any]:
    session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
    if not session.get("authenticated"):
        raise ApiError(401, "unauthenticated", "Sign in required.")
    session_user = session.get("user") or {}
    username = session_user.get("username") or ""
    if not username:
        raise ApiError(401, "unauthenticated", "Sign in required.")
    # The signed-in session is the runtime authority. User-search representations
    # can lag behind a just-assigned department role, which would deny a workspace
    # the staff member can already open.
    roles = [
        role.get("name")
        for role in (session_user.get("roles") or [])
        if isinstance(role, dict) and role.get("name")
    ]
    privileges = [
        item.get("name")
        for item in (session_user.get("privileges") or [])
        if isinstance(item, dict) and item.get("name") and not item.get("retired")
    ]
    return {
        "username": username,
        "uuid": session_user.get("uuid") or "",
        "roles": roles,
        "privileges": privileges,
    }


def is_accountant(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & ACCOUNTANT_ROLES) or ACCOUNTANT_PRIVILEGE in privileges


def require_accountant(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_accountant(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires the Accountant / Cashier workspace.",
        )
    return user


def odoo_reader() -> OdooReader:
    try:
        return OdooReader()
    except ApiError:
        raise
    except xmlrpc.client.Fault as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error
    except (ConnectionError, TimeoutError, OSError) as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error


def execute(odoo: OdooReader, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None) -> Any:
    return odoo.models.execute_kw(
        ODOO_DB,
        odoo.uid,
        ODOO_PASSWORD,
        model,
        method,
        args,
        kwargs or {},
    )


def execute_allowing_empty(odoo: OdooReader, model: str, method: str, args: list[Any]) -> Any:
    """Some bill actions succeed and then return nothing the finance link can send back."""
    try:
        return execute(odoo, model, method, args)
    except xmlrpc.client.Fault as error:
        if "cannot marshal None" in str(error):
            return None
        raise


DEFAULT_MAIL_FROM = "noreply@abikan.local"
DEFAULT_MAIL_DOMAIN = "abikan.local"


def ensure_payment_mail_sender(odoo: OdooReader) -> None:
    """Full settlements can post a paid-invoice notice; Odoo needs a sender address.

    Partial payments often skip that notice, which is why underpayment can succeed
    while paying the exact balance fails when email is unset.
    """
    companies = odoo.search_read("res.company", [], ["email"], limit=1)
    if companies and not (companies[0].get("email") or "").strip():
        execute(odoo, "res.company", "write", [[int(companies[0]["id"])], {"email": DEFAULT_MAIL_FROM}])

    domain_rows = odoo.search_read(
        "ir.config_parameter",
        [("key", "=", "mail.catchall.domain")],
        ["value"],
        limit=1,
    )
    if not domain_rows:
        execute(
            odoo,
            "ir.config_parameter",
            "create",
            [{"key": "mail.catchall.domain", "value": DEFAULT_MAIL_DOMAIN}],
        )
    elif not (domain_rows[0].get("value") or "").strip():
        execute(
            odoo,
            "ir.config_parameter",
            "write",
            [[int(domain_rows[0]["id"])], {"value": DEFAULT_MAIL_DOMAIN}],
        )

    users = odoo.search_read("res.users", [("id", "=", int(odoo.uid))], ["email", "partner_id"], limit=1)
    if users and not (users[0].get("email") or "").strip():
        execute(odoo, "res.users", "write", [[int(users[0]["id"])], {"email": DEFAULT_MAIL_FROM}])
        partner = many2one_id(users[0].get("partner_id"))
        if partner:
            execute(odoo, "res.partner", "write", [[partner], {"email": DEFAULT_MAIL_FROM}])


def authorized_journals(odoo: OdooReader) -> list[dict[str, Any]]:
    rows = odoo.search_read(
        "account.journal",
        [("type", "in", ["cash", "bank"])],
        ["name", "code", "type"],
    )
    return [
        {
            "id": int(row["id"]),
            "name": row.get("name") or "",
            "code": row.get("code") or "",
            "type": row.get("type") or "",
        }
        for row in rows
    ]


def serialize_payment(
    odoo: OdooReader,
    payment: dict[str, Any],
    currency: dict[str, Any],
    collected: dict[str, str] | None = None,
) -> dict[str, Any]:
    invoices = odoo.read(
        "account.move",
        [int(item) for item in (payment.get("reconciled_invoice_ids") or [])],
        ["name"],
    )
    partner_name = many2one_name(payment.get("partner_id"))
    partner_id = many2one_id(payment.get("partner_id"))
    partner = {}
    if partner_id:
        found = odoo.read("res.partner", [partner_id], ["name", "ref", "uuid"])
        partner = found[0] if found else {}
    import accountant_refund as refunds

    refund_meta = refunds.payment_refund_summary(odoo, payment)
    return {
        "id": int(payment["id"]),
        "reference": payment.get("name") or "",
        "date": payment.get("date") or "",
        "amount": format_money(as_float(payment.get("amount")), currency),
        "journal": many2one_name(payment.get("journal_id")),
        "journalId": many2one_id(payment.get("journal_id")),
        "method": many2one_name(payment.get("payment_method_id")),
        "state": payment.get("state") or "",
        "patientName": partner.get("name") or partner_name,
        "mrn": partner.get("ref") or "",
        "patientUuid": core.walkin_account_uuid(partner) or None,
        "relatedInvoices": [
            {"id": int(row["id"]), "number": row.get("name") or ""}
            for row in invoices
        ],
        "createUid": many2one_name(payment.get("create_uid")),
        "createDate": payment.get("create_date") or "",
        "actedAt": staff_instant(
            (collected or {}).get("collectedAt") or payment.get("create_date")
        ),
        "amountRefunded": refund_meta["amountRefunded"],
        "amountRefundable": refund_meta["amountRefundable"],
        "refundStatus": refund_meta["refundStatus"],
        "canRefund": refund_meta["canRefund"],
        "recordedBy": staff_display_name(
            str((collected or {}).get("collectedBy") or "")
            or _collector_name(int(payment["id"]))
        ),
        "discountNote": (
            str(payment.get("ref") or "").strip()
            if str(payment.get("ref") or "").strip().startswith("Discount given:")
            else None
        ),
    }


PAYMENT_FIELDS = [
    "name",
    "amount",
    "date",
    "journal_id",
    "currency_id",
    "reconciled_invoice_ids",
    "payment_method_id",
    "state",
    "partner_id",
    "create_uid",
    "create_date",
    "ref",
]


def staff_instant(value: Any) -> str:
    """Clock time for staff. A date with no time stays a date, so it is not shown as 1:00."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    normalized = text.replace(" ", "T")
    try:
        if normalized.endswith("Z"):
            moment = datetime.fromisoformat(normalized[:-1] + "+00:00")
        elif len(normalized) > 19 and normalized[-6] in "+-":
            moment = datetime.fromisoformat(normalized)
        else:
            moment = datetime.fromisoformat(normalized[:19]).replace(tzinfo=timezone.utc)
    except ValueError:
        return text
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo("Africa/Lagos")).isoformat(timespec="seconds")


_STAFF_NAMES: dict[str, str] = {}


def staff_display_name(username: str) -> str:
    """First and last name of a staff member. The sign-in name is kept when the chart name is missing."""
    key = " ".join(str(username or "").split())
    if not key or key in {"Pharmacy", "—"}:
        return key
    cached = _STAFF_NAMES.get(key.casefold())
    if cached is not None:
        return cached
    name = key
    try:
        from urllib.parse import quote

        found = core.openmrs_service_get(
            "/openmrs/ws/rest/v1/user?q="
            f"{quote(key)}&v=custom:(username,person:(display,preferredName:(givenName,familyName)))&limit=5"
        )
        results = found.get("results") if isinstance(found, dict) else []
        for user in results or []:
            if str(user.get("username") or "").casefold() != key.casefold():
                continue
            person = user.get("person") if isinstance(user.get("person"), dict) else {}
            preferred = person.get("preferredName") if isinstance(person.get("preferredName"), dict) else {}
            given = str(preferred.get("givenName") or "").strip()
            family = str(preferred.get("familyName") or "").strip()
            name = " ".join(part for part in (given, family) if part) or str(person.get("display") or key)
            break
    except Exception:
        name = key
    _STAFF_NAMES[key.casefold()] = name
    return name


def _collector_name(payment_id: int) -> str:
    import cashier_records as ledger

    return ledger.collectors_for([payment_id]).get(int(payment_id), "")


def _serialize_payments(odoo: OdooReader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        rows,
        key=lambda row: (row.get("create_date") or row.get("date") or "", int(row["id"])),
        reverse=True,
    )
    currencies = money_maps(
        odoo,
        {cid for row in rows if (cid := many2one_id(row.get("currency_id")))},
    )
    default = load_currency(odoo, None)
    import cashier_records as ledger

    collected = ledger.collection_facts([int(row["id"]) for row in rows if row.get("id")])
    return [
        serialize_payment(
            odoo,
            row,
            currencies.get(many2one_id(row.get("currency_id")) or 0, default),
            collected.get(int(row["id"])),
        )
        for row in rows
    ]


def list_recent_payments(odoo: OdooReader, limit: int = 20) -> list[dict[str, Any]]:
    rows = odoo.search_read(
        "account.payment",
        [
            ("partner_type", "=", "customer"),
            ("payment_type", "=", "inbound"),
            ("state", "=", "posted"),
        ],
        PAYMENT_FIELDS,
        limit=limit,
    )
    return _serialize_payments(odoo, rows)


def list_payments_for_range(odoo: OdooReader, start_date: str, end_date: str) -> list[dict[str, Any]]:
    rows = odoo.search_read(
        "account.payment",
        finance.collected_domain(start_date, end_date),
        PAYMENT_FIELDS,
        limit=10000,
    )
    return _serialize_payments(odoo, rows)


def _chart_uuids_for_walkins(odoo: OdooReader, partners: dict[int, dict[str, Any]]) -> dict[int, str]:
    """External bills are stored without a chart link. Match the hospital number to the chart."""
    tokens: dict[str, list[int]] = {}
    for partner_id, partner in partners.items():
        if partner.get("uuid"):
            continue
        number = core.chart_number_from_ref(str(partner.get("ref") or ""))
        raw = str(partner.get("ref") or "").strip()
        if not number or number == raw:
            continue
        tokens.setdefault(number, []).append(partner_id)
    if not tokens:
        return {}
    linked = odoo.search_read(
        "res.partner",
        [("ref", "in", list(tokens))],
        ["ref", "uuid"],
        limit=len(tokens),
    )
    resolved: dict[int, str] = {}
    for row in linked:
        patient_uuid = str(row.get("uuid") or "").strip()
        number = str(row.get("ref") or "").strip()
        if not patient_uuid or number not in tokens:
            continue
        for partner_id in tokens[number]:
            resolved[partner_id] = patient_uuid
    return resolved


def _post_confirmed_draft_invoices(odoo: OdooReader) -> None:
    """A confirmed order can be left as a draft bill. Post it so it can be collected."""
    drafts = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "draft"),
            ("amount_residual", ">", 0),
        ],
        ["id", "invoice_origin"],
        limit=40,
    )
    origins = [str(row.get("invoice_origin") or "") for row in drafts if row.get("invoice_origin")]
    if not origins:
        return
    confirmed = {
        str(row.get("name") or "")
        for row in odoo.search_read(
            "sale.order",
            [("name", "in", origins), ("state", "in", ["sale", "done"])],
            ["name"],
            limit=len(origins),
        )
    }
    for draft in drafts:
        if str(draft.get("invoice_origin") or "") not in confirmed:
            continue
        try:
            execute(odoo, "account.move", "action_post", [[int(draft["id"])]])
        except xmlrpc.client.Fault:
            continue


def outstanding_invoices(odoo: OdooReader) -> list[dict[str, Any]]:
    _post_confirmed_draft_invoices(odoo)
    invoices = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("amount_residual", ">", 0),
            ("payment_state", "in", list(ELIGIBLE_STATES)),
        ],
        [
            "name",
            "payment_state",
            "amount_total",
            "amount_residual",
            "currency_id",
            "partner_id",
            "invoice_origin",
            "invoice_date",
            "create_date",
        ],
    )
    if not invoices:
        return []
    origins = [row.get("invoice_origin") for row in invoices if row.get("invoice_origin")]
    orders = (
        odoo.search_read(
            "sale.order",
            [("name", "in", origins)],
            ["name", "shop_id"],
        )
        if origins
        else []
    )
    shop_by_origin = {row.get("name"): many2one_name(row.get("shop_id")) for row in orders}
    partner_ids = {
        pid for row in invoices if (pid := many2one_id(row.get("partner_id")))
    }
    partners = {
        int(row["id"]): row
        for row in odoo.read("res.partner", list(partner_ids), ["name", "ref", "uuid"])
    }
    chart_uuids = _chart_uuids_for_walkins(odoo, partners)
    import consultation as clinical

    nhis_patients = clinical.load_nhis_patients(odoo)
    currencies = money_maps(
        odoo,
        {cid for row in invoices if (cid := many2one_id(row.get("currency_id")))},
    )
    default = load_currency(odoo, None)
    rows = []
    for invoice in invoices:
        partner = partners.get(many2one_id(invoice.get("partner_id")) or 0) or {}
        shop = shop_by_origin.get(invoice.get("invoice_origin") or "")
        department = core.identify_department(shop or "", []) or "Department not identified"
        currency = currencies.get(many2one_id(invoice.get("currency_id")) or 0, default)
        partner_ref = str(partner.get("ref") or "")
        partner_uuid = core.walkin_account_uuid(partner)
        rows.append(
            {
                "id": int(invoice["id"]),
                "number": invoice.get("name") or "",
                "date": invoice.get("invoice_date") or "",
                "department": department,
                "paymentState": invoice.get("payment_state") or "not_paid",
                "paymentStateLabel": payment_state_label(invoice.get("payment_state")),
                "total": format_money(as_float(invoice.get("amount_total")), currency),
                "outstanding": format_money(as_float(invoice.get("amount_residual")), currency),
                "patientName": partner.get("name") or many2one_name(invoice.get("partner_id")),
                "mrn": core.chart_number_from_ref(partner_ref),
                "patientUuid": partner_uuid or chart_uuids.get(int(partner.get("id") or 0)) or None,
                "nhis": str(partner.get("uuid") or "") in nhis_patients,
                "createDate": invoice.get("create_date") or "",
                "arrivedAt": staff_instant(invoice.get("create_date")),
            }
        )
    import cashier_records as ledger

    created = ledger.creators_for([int(row["id"]) for row in rows])
    for row in rows:
        saved = created.get(int(row["id"]))
        if not saved:
            continue
        row["createdBy"] = staff_display_name(str(saved.get("createdBy") or ""))
        row["purpose"] = saved.get("description") or ""
    return sort_outstanding_bills(rows)


def sort_outstanding_bills(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest bills first. Cashier work is time order, not highest amount."""
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("createDate") or row.get("date") or ""),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )


def build_dashboard(cookie: str) -> dict[str, Any]:
    require_accountant(cookie)
    odoo = odoo_reader()
    currency = load_currency(odoo, None)
    today = finance.hospital_business_date()
    attention_all = outstanding_invoices(odoo)
    recent_all = list_recent_payments(odoo, limit=25)
    today_payments = list_payments_for_range(odoo, today, today)
    refund_rows = list_refunds(odoo, limit=25, start_date=None, end_date=None)
    today_refunds = [
        row for row in list_refunds(odoo, limit=200, start_date=today, end_date=today)
    ]
    collected = aggregate_by_currency([row["amount"] for row in today_payments])
    refunded_today = aggregate_by_currency([row["amount"] for row in today_refunds])
    collected_amount = sum(as_float(item.get("amount")) for item in collected)
    refunded_amount = sum(as_float(item.get("amount")) for item in refunded_today)
    net_by_currency = [format_money(round(collected_amount - refunded_amount, 2), currency)]
    return {
        "status": "ok",
        "readOnly": False,
        "currency": currency,
        "journals": authorized_journals(odoo),
        "today": {
            "date": today,
            "paymentsReceivedByCurrency": collected,
            "paymentCount": len(today_payments),
            "outstandingByCurrency": aggregate_by_currency(
                [row["outstanding"] for row in attention_all]
            ),
            "outstandingCount": len(attention_all),
            "refundsByCurrency": refunded_today,
            "refundCount": len(today_refunds),
            "netByCurrency": net_by_currency,
        },
        "attention": attention_all[:5],
        "attentionTotal": len(attention_all),
        "recentPayments": recent_all[:5],
        "recentPaymentsTotal": len(recent_all),
        "recentRefunds": refund_rows[:5],
        "recentRefundsTotal": len(refund_rows),
    }


def _query_int(params: dict[str, list[str]], key: str, default: int) -> int:
    raw = (params.get(key) or [str(default)])[0]
    try:
        return max(int(raw), 0)
    except ValueError as error:
        raise ApiError(422, "invalid_query", "Enter a valid page size.") from error


def list_outstanding_page(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_accountant(cookie)
    params = query or {}
    limit = min(_query_int(params, "limit", 25) or 25, 100)
    offset = _query_int(params, "offset", 0)
    q = str((params.get("q") or [""])[0] or "").strip().lower()
    odoo = odoo_reader()
    rows = outstanding_invoices(odoo)
    if q:
        rows = [
            row
            for row in rows
            if q in str(row.get("patientName") or "").lower()
            or q in str(row.get("mrn") or "").lower()
            or q in str(row.get("number") or "").lower()
        ]
    total = len(rows)
    return {
        "status": "ok",
        "items": rows[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def list_payments_page(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_accountant(cookie)
    params = query or {}
    limit = min(_query_int(params, "limit", 25) or 25, 100)
    offset = _query_int(params, "offset", 0)
    q = str((params.get("q") or [""])[0] or "").strip().lower()
    start = str((params.get("from") or params.get("start") or [""])[0] or "").strip()
    end = str((params.get("to") or params.get("end") or [""])[0] or "").strip()
    odoo = odoo_reader()
    domain: list[Any] = [
        ("partner_type", "=", "customer"),
        ("payment_type", "=", "inbound"),
        ("state", "=", "posted"),
    ]
    if start:
        domain.append(("date", ">=", start))
    if end:
        domain.append(("date", "<=", end))
    if q:
        domain = [
            "&",
            *domain,
            "|",
            "|",
            ("name", "ilike", q),
            ("partner_id.name", "ilike", q),
            ("partner_id.ref", "ilike", q),
        ]
    total = int(execute(odoo, "account.payment", "search_count", [domain]) or 0)
    rows = (
        execute(
            odoo,
            "account.payment",
            "search_read",
            [domain],
            {"fields": PAYMENT_FIELDS, "limit": limit, "offset": offset, "order": "create_date desc, id desc"},
        )
        or []
    )
    return {
        "status": "ok",
        "items": _serialize_payments(odoo, rows),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def list_refunds(
    odoo: OdooReader,
    *,
    limit: int = 25,
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
    q: str = "",
) -> list[dict[str, Any]]:
    domain: list[Any] = [("move_type", "=", "out_refund"), ("state", "=", "posted")]
    if start_date:
        domain.append(("invoice_date", ">=", start_date))
    if end_date:
        domain.append(("invoice_date", "<=", end_date))
    if q:
        domain = [
            "&",
            *domain,
            "|",
            "|",
            ("name", "ilike", q),
            ("ref", "ilike", q),
            ("partner_id.name", "ilike", q),
        ]
    rows = (
        execute(
            odoo,
            "account.move",
            "search_read",
            [domain],
            {
                "fields": [
                    "name",
                    "invoice_date",
                    "amount_total",
                    "payment_state",
                    "invoice_origin",
                    "partner_id",
                    "ref",
                    "narration",
                    "create_uid",
                    "create_date",
                    "currency_id",
                ],
                "limit": limit,
                "offset": offset,
                "order": "invoice_date desc, id desc",
            },
        )
        or []
    )
    return _serialize_refunds(odoo, rows)


def _serialize_refunds(odoo: OdooReader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import accountant_refund as refunds

    partner_ids = {pid for row in rows if (pid := many2one_id(row.get("partner_id")))}
    partners = {
        int(row["id"]): row
        for row in (odoo.read("res.partner", list(partner_ids), ["name", "ref", "uuid"]) if partner_ids else [])
    }
    currencies = money_maps(
        odoo,
        {cid for row in rows if (cid := many2one_id(row.get("currency_id")))},
    )
    default = load_currency(odoo, None)
    items = []
    for row in rows:
        partner = partners.get(many2one_id(row.get("partner_id")) or 0) or {}
        currency = currencies.get(many2one_id(row.get("currency_id")) or 0, default)
        ref = str(row.get("ref") or "")
        narration = str(row.get("narration") or "")
        processed_by = ""
        payment_id = None
        for match in refunds.REFUND_RE.finditer(ref):
            payment_id = int(match.group(1))
            # marker ends with :username when written by accountant_refund
            tail = ref.split(f"{refunds.REFUND_PREFIX}{match.group(1)}:{match.group(2)}:")
            if len(tail) > 1 and tail[1]:
                processed_by = tail[1].split()[0]
        if not processed_by and "Pharmacy refund" in ref:
            processed_by = "Pharmacy"
        if not processed_by:
            processed_by = many2one_name(row.get("create_uid")) or "—"
        items.append(
            {
                "id": int(row["id"]),
                "reference": row.get("name") or "",
                "date": row.get("invoice_date") or "",
                "amount": format_money(as_float(row.get("amount_total")), currency),
                "paymentState": row.get("payment_state") or "",
                "paymentStateLabel": payment_state_label(row.get("payment_state")),
                "origin": row.get("invoice_origin") or "",
                "reason": narration or ref or "",
                "ref": ref,
                "patientName": partner.get("name") or many2one_name(row.get("partner_id")),
                "mrn": partner.get("ref") or "",
                "patientUuid": partner.get("uuid") or None,
                "processedBy": processed_by if processed_by == "Pharmacy" else staff_display_name(processed_by),
                "createUid": many2one_name(row.get("create_uid")),
                "createDate": row.get("create_date") or "",
                "actedAt": staff_instant(row.get("create_date")),
                "sourcePaymentId": payment_id,
                "source": "pharmacy" if "Pharmacy refund" in ref or "Pharmacy cancelled" in ref else "accountant",
            }
        )
    return items


def list_refunds_page(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_accountant(cookie)
    params = query or {}
    limit = min(_query_int(params, "limit", 25) or 25, 100)
    offset = _query_int(params, "offset", 0)
    q = str((params.get("q") or [""])[0] or "").strip()
    start = str((params.get("from") or params.get("start") or [""])[0] or "").strip() or None
    end = str((params.get("to") or params.get("end") or [""])[0] or "").strip() or None
    odoo = odoo_reader()
    domain: list[Any] = [("move_type", "=", "out_refund"), ("state", "=", "posted")]
    if start:
        domain.append(("invoice_date", ">=", start))
    if end:
        domain.append(("invoice_date", "<=", end))
    if q:
        domain = [
            "&",
            *domain,
            "|",
            "|",
            ("name", "ilike", q),
            ("ref", "ilike", q),
            ("partner_id.name", "ilike", q),
        ]
    total = int(execute(odoo, "account.move", "search_count", [domain]) or 0)
    items = list_refunds(odoo, limit=limit, offset=offset, start_date=start, end_date=end, q=q)
    return {
        "status": "ok",
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def get_payment(payment_id: int, cookie: str) -> dict[str, Any]:
    require_accountant(cookie)
    odoo = odoo_reader()
    rows = odoo.read(
        "account.payment",
        [payment_id],
        [
            "name",
            "amount",
            "date",
            "journal_id",
            "currency_id",
            "reconciled_invoice_ids",
            "payment_method_id",
            "state",
            "partner_id",
            "create_uid",
            "create_date",
            "ref",
        ],
    )
    if not rows:
        raise ApiError(404, "payment_not_found", "Payment not found.")
    payment = rows[0]
    if payment.get("state") != "posted":
        raise ApiError(404, "payment_not_found", "Payment not found.")
    currency = staff_currency(odoo, many2one_id(payment.get("currency_id")))
    return {
        "status": "ok",
        "payment": serialize_payment(odoo, payment, currency),
        "receiptAvailable": True,
    }


def list_payments(cookie: str) -> dict[str, Any]:
    require_accountant(cookie)
    odoo = odoo_reader()
    return {"status": "ok", "payments": list_recent_payments(odoo)}


def _validate_invoices(
    odoo: OdooReader,
    partner_id: int,
    invoice_ids: list[int],
    expected: dict[int, float] | None,
) -> tuple[list[dict[str, Any]], float]:
    if not invoice_ids:
        raise ApiError(422, "invoices_required", "Select at least one bill.")
    invoices = odoo.read(
        "account.move",
        invoice_ids,
        [
            "name",
            "move_type",
            "state",
            "payment_state",
            "amount_residual",
            "amount_total",
            "partner_id",
            "currency_id",
        ],
    )
    if len(invoices) != len(set(invoice_ids)):
        raise ApiError(404, "invoice_not_found", "One or more bills were not found.")
    total = 0.0
    for invoice in invoices:
        if invoice.get("move_type") != "out_invoice":
            raise ApiError(422, "not_customer_invoice", "This bill cannot be paid here.")
        if invoice.get("state") != "posted":
            raise ApiError(422, "invoice_not_posted", "This bill is not ready for payment.")
        if many2one_id(invoice.get("partner_id")) != partner_id:
            raise ApiError(409, "invoice_wrong_patient", "A bill does not belong to this patient.")
        if invoice.get("payment_state") == "paid" or as_float(invoice.get("amount_residual")) <= 0:
            raise ApiError(409, "invoice_already_paid", f"{invoice.get('name')} is already paid.")
        if invoice.get("payment_state") not in ELIGIBLE_STATES:
            raise ApiError(
                409,
                "invoice_not_eligible",
                f"{invoice.get('name')} is not eligible for payment.",
            )
        residual = as_float(invoice.get("amount_residual"))
        if expected is not None and int(invoice["id"]) in expected:
            if money_minor(residual, 2) != money_minor(expected[int(invoice["id"])], 2):
                raise ApiError(
                    409,
                    "invoice_changed",
                    f"{invoice.get('name')} changed since the page was loaded. Refresh and try again.",
                )
        total += residual
    currency_ids = {many2one_id(invoice.get("currency_id")) for invoice in invoices}
    if len(currency_ids) > 1:
        raise ApiError(422, "mixed_currency", MIXED_CURRENCY_MESSAGE)
    return invoices, total


def validate_payment_amount(amount: Any, outstanding: Any, places: int = 2) -> tuple[float, float]:
    """Compare tendered amount to due using integer minor units.

    Exact due is accepted. Only a greater minor-unit amount is an overpayment.
    """
    amount_minor = money_minor(amount, places)
    outstanding_minor = money_minor(outstanding, places)
    if outstanding_minor <= 0:
        raise ApiError(409, "invoice_already_paid", "This bill is already fully paid.")
    if amount_minor <= 0:
        raise ApiError(422, "invalid_amount", "Payment amount must be greater than zero.")
    if amount_minor > outstanding_minor:
        raise ApiError(
            422,
            "amount_exceeds_outstanding",
            "Payment amount cannot exceed the selected outstanding balance.",
        )
    return money_major(amount_minor, places), money_major(outstanding_minor, places)


def validate_discount_percentage(
    percentage: Any,
    amount: Any,
    outstanding: Any,
    places: int = 2,
) -> tuple[float, float]:
    """Ensure a percentage discount produces the final amount being collected."""
    try:
        percentage_value = float(percentage or 0)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_discount", "Enter a valid discount percentage.") from error
    if percentage_value < 0 or percentage_value >= 100:
        raise ApiError(422, "invalid_discount", "Discount percentage must be below 100%.")
    amount_minor = money_minor(amount, places)
    if percentage_value == 0:
        return 0.0, money_major(amount_minor, places)
    return percentage_value, money_major(amount_minor, places)


def choose_discount_account(rows: list[dict[str, Any]]) -> int | None:
    """Pick the expense account used when a bill is reduced."""
    named = [row for row in rows if row.get("id")]

    def label(row: dict[str, Any]) -> str:
        return str(row.get("name") or "").lower()

    losses = [
        row
        for row in named
        if row.get("account_type") == "expense" and "loss" in label(row)
    ]
    expenses = [row for row in named if row.get("account_type") == "expense"]
    chosen = losses or expenses or (named if len(named) == 1 else [])
    if not chosen:
        return None
    return int(chosen[0]["id"])


def discount_account_id(odoo: OdooReader) -> int:
    if DISCOUNT_ACCOUNT_ID:
        try:
            return int(DISCOUNT_ACCOUNT_ID)
        except ValueError as error:
            raise ApiError(503, "discount_not_configured", "The discount could not be applied.") from error
    rows = odoo.search_read(
        "account.account",
        [("name", "ilike", "discount")],
        ["id", "name", "account_type"],
        limit=20,
    )
    account_id = choose_discount_account(rows)
    if not account_id:
        raise ApiError(503, "discount_not_configured", "The discount could not be applied.")
    return account_id


def apply_invoice_discounts(
    odoo: OdooReader,
    invoices: list[dict[str, Any]],
    percentage: float,
    currency: dict[str, Any],
) -> float:
    """Write off the approved discount on each invoice, then return adjusted due."""
    if percentage <= 0:
        return sum(as_float(invoice.get("amount_residual")) for invoice in invoices)
    places = int(currency.get("decimalPlaces") or 2)
    discount_account = discount_account_id(odoo)
    journals = odoo.search_read("account.journal", [("type", "=", "general")], ["id"], limit=1)
    if not journals:
        raise ApiError(503, "discount_not_configured", "A general journal is required for discounts.")
    journal_id = int(journals[0]["id"])
    adjusted_total = 0.0
    for invoice in invoices:
        residual_minor = money_minor(invoice.get("amount_residual"), places)
        discount_minor = round(residual_minor * percentage / 100)
        adjusted_total += money_major(residual_minor - discount_minor, places)
        if discount_minor <= 0:
            continue
        invoice_lines = odoo.search_read(
            "account.move.line",
            [
                ("move_id", "=", int(invoice["id"])),
                ("reconciled", "=", False),
                ("amount_residual", ">", 0),
            ],
            ["id", "account_id", "amount_residual", "partner_id", "company_id"],
        )
        account_ids = {
            account_id
            for line in invoice_lines
            if (account_id := many2one_id(line.get("account_id")))
        }
        account_types = {
            int(row["id"]): row.get("account_type")
            for row in (odoo.read("account.account", list(account_ids), ["account_type"]) if account_ids else [])
        }
        receivable = next(
            (
                line
                for line in invoice_lines
                if account_types.get(many2one_id(line.get("account_id"))) == "asset_receivable"
            ),
            None,
        )
        if not receivable:
            raise ApiError(409, "discount_failed", f"{invoice.get('name')} has no open balance to discount.")
        amount = money_major(discount_minor, places)
        move_id = execute(
            odoo,
            "account.move",
            "create",
            [{
                "move_type": "entry",
                "date": finance.hospital_business_date(),
                "journal_id": journal_id,
                "ref": f"Patient bill discount {invoice.get('name')}",
                "line_ids": [
                    (0, 0, {
                        "name": "Patient bill discount",
                        "account_id": discount_account,
                        "debit": amount,
                        "credit": 0,
                    }),
                    (0, 0, {
                        "name": "Patient bill discount",
                        "account_id": many2one_id(receivable.get("account_id")),
                        "partner_id": many2one_id(receivable.get("partner_id")),
                        "debit": 0,
                        "credit": amount,
                    }),
                ],
            }],
        )
        execute(odoo, "account.move", "action_post", [[int(move_id)]])
        new_lines = odoo.search_read(
            "account.move.line",
            [("move_id", "=", int(move_id)), ("account_id", "=", many2one_id(receivable.get("account_id")))],
            ["id"],
        )
        if not new_lines:
            raise ApiError(502, "discount_failed", "The discount could not be applied.")
        new_line_id = int(new_lines[0]["id"])
        reconcile_invoice_line(int(invoice["id"]), new_line_id)
        verified = odoo.read(
            "account.move.line",
            [int(receivable["id"]), new_line_id],
            ["reconciled", "amount_residual"],
        )
        expected_residual = money_major(residual_minor - discount_minor, places)
        if (
            len(verified) != 2
            or not verified[1].get("reconciled")
            or money_minor(verified[0].get("amount_residual"), places)
            != money_minor(expected_residual, places)
        ):
            raise ApiError(502, "discount_failed", "The discount could not be applied.")
    return adjusted_total


def reconcile_invoice_line(invoice_id: int, line_id: int) -> None:
    """Use Odoo's web RPC because XML-RPC cannot marshal reconcile recordsets."""
    if not ODOO_USER or not ODOO_PASSWORD:
        raise ApiError(503, "discount_failed", "The discount could not be applied.")
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))

    def call(path: str, params: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{ODOO_URL}{path}",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=20) as response:
            return json.loads(response.read())

    auth = call(
        "/web/session/authenticate",
        {"db": ODOO_DB, "login": ODOO_USER, "password": ODOO_PASSWORD},
    )
    if auth.get("error") or not (auth.get("result") or {}).get("uid"):
        raise ApiError(503, "discount_failed", "The discount could not be applied.")
    result = call(
        "/web/dataset/call_kw/account.move/js_assign_outstanding_line",
        {
            "model": "account.move",
            "method": "js_assign_outstanding_line",
            "args": [[invoice_id], line_id],
            "kwargs": {},
        },
    )
    if result.get("error"):
        message = ((result["error"].get("data") or {}).get("message") or "").strip()
        # The reconciliation may already have committed before Odoo tries to
        # serialize its recordset response. The caller verifies both lines.
        return


def register_payment(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_accountant(cookie)
    request_id = str(body.get("requestId") or "").strip()
    if not request_id:
        raise ApiError(422, "request_id_required", "A payment request identifier is required.")
    with IDEMPOTENCY_LOCK:
        existing = IDEMPOTENCY.get(request_id)
        if existing and existing.get("status") == "done":
            return get_payment(int(existing["paymentId"]), cookie) | {
                "idempotentReplay": True,
                "requestId": request_id,
            }
        if existing and existing.get("status") == "pending":
            raise ApiError(409, "payment_in_progress", "This payment request is already being processed.")
        IDEMPOTENCY[request_id] = {"status": "pending", "username": user.get("username")}

    try:
        result = _register_payment_once(body, cookie, request_id, user)
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[request_id] = {
                "status": "done",
                "paymentId": result["payment"]["id"],
                "username": user.get("username"),
            }
        return result
    except Exception:
        with IDEMPOTENCY_LOCK:
            current = IDEMPOTENCY.get(request_id) or {}
            if current.get("status") == "pending":
                IDEMPOTENCY.pop(request_id, None)
        raise


def _register_payment_once(
    body: dict[str, Any],
    cookie: str,
    request_id: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    patient_uuid = str(body.get("patientUuid") or "").strip()
    raw_ids = body.get("invoiceIds") or []
    try:
        invoice_ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_invoices", "Those bills cannot be paid.") from error
    amount = as_float(body.get("amount"))
    discount_percentage = as_float(body.get("discountPercentage") or 0)
    try:
        journal_id = int(body.get("journalId"))
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_journal", "Select a payment method.") from error
    expected_raw = body.get("expectedResiduals") or {}
    expected: dict[int, float] | None = None
    if expected_raw:
        try:
            expected = {int(key): as_float(value) for key, value in expected_raw.items()}
        except (TypeError, ValueError) as error:
            raise ApiError(422, "invalid_residuals", "The amount due has changed. Refresh and try again.") from error

    patient = load_openmrs_patient(patient_uuid, cookie)
    odoo = odoo_reader()
    partner = find_partner(odoo, patient)
    if not partner:
        raise ApiError(404, "account_not_found", "No bills for this patient.")
    journals = {row["id"]: row for row in authorized_journals(odoo)}
    if journal_id not in journals:
        raise ApiError(422, "invalid_journal", "That payment method is not authorized.")
    invoices, outstanding = _validate_invoices(odoo, int(partner["id"]), invoice_ids, expected)
    currency = load_currency(odoo, many2one_id(invoices[0].get("currency_id")))
    places = int(currency.get("decimalPlaces") or 2)
    discount_percentage, amount = validate_discount_percentage(
        discount_percentage,
        amount,
        outstanding,
        places,
    )
    adjusted_outstanding = money_major(
        money_minor(outstanding, places)
        - round(money_minor(outstanding, places) * discount_percentage / 100),
        places,
    )
    amount, outstanding = validate_payment_amount(amount, adjusted_outstanding, places)
    ensure_payment_mail_sender(odoo)
    if discount_percentage > 0:
        apply_invoice_discounts(odoo, invoices, discount_percentage, currency)

    ctx = {
        "active_model": "account.move",
        "active_ids": invoice_ids,
        "active_id": invoice_ids[0],
    }
    try:
        wizard_id = execute(
            odoo,
            "account.payment.register",
            "create",
            [
                {
                    "journal_id": journal_id,
                    "amount": amount,
                    "payment_date": finance.hospital_business_date(),
                    "group_payment": True,
                    "communication": (
                        f"Discount given: {discount_percentage:g}%"
                        if discount_percentage > 0
                        else request_id
                    ),
                }
            ],
            {"context": ctx},
        )
        action = execute(
            odoo,
            "account.payment.register",
            "action_create_payments",
            [[wizard_id]],
            {"context": ctx},
        )
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_payment_failed",
            "The payment could not be recorded. Check the amount and try again.",
        ) from error

    payment_id = _payment_id_from_action(action)
    if not payment_id:
        raise ApiError(
            502,
            "odoo_payment_failed",
            "The payment could not be recorded. Check the amount and try again.",
        )
    payload = get_payment(payment_id, cookie)
    import cashier_records as ledger

    collector = str(user.get("username") or "").strip()
    ledger.record_collector(payment_id, collector)
    payload["payment"]["recordedBy"] = collector
    if discount_percentage > 0:
        payload["payment"]["discountNote"] = (
            f"Discount given: {discount_percentage:g}%"
        )
    account = build_account(patient_uuid, cookie)
    return {
        "status": "ok",
        "success": True,
        "requestId": request_id,
        "recordedBy": user.get("username"),
        "patient": patient,
        "journal": journals[journal_id],
        "payment": payload["payment"],
        "account": account,
        "receiptAvailable": True,
        "idempotentReplay": False,
    }


def delete_unpaid_bill(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Remove one unpaid bill and keep who deleted it and why."""
    user = require_accountant(cookie)
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 3:
        raise ApiError(422, "reason_required", "Enter why this bill is being deleted.")
    if len(reason) > 500:
        raise ApiError(422, "reason_too_long", "Keep the reason shorter than 500 characters.")
    try:
        invoice_id = int(body.get("invoiceId"))
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_invoice", "Choose a bill to delete.") from error
    patient_uuid = str(body.get("patientUuid") or "").strip()

    odoo = odoo_reader()
    invoices = odoo.read(
        "account.move",
        [invoice_id],
        [
            "name",
            "move_type",
            "state",
            "payment_state",
            "amount_residual",
            "amount_total",
            "partner_id",
            "currency_id",
            "invoice_origin",
            "invoice_date",
        ],
    )
    if not invoices:
        raise ApiError(404, "invoice_not_found", "That bill was not found.")
    invoice = invoices[0]
    if invoice.get("move_type") != "out_invoice":
        raise ApiError(422, "not_customer_invoice", "This bill cannot be deleted here.")
    if invoice.get("state") == "cancel":
        raise ApiError(409, "already_deleted", "This bill was already deleted.")
    if invoice.get("state") not in {"posted", "draft"}:
        raise ApiError(422, "invoice_not_posted", "This bill is not ready to delete.")
    if invoice.get("payment_state") != "not_paid" or money_minor(invoice.get("amount_residual"), 2) != money_minor(
        invoice.get("amount_total"), 2
    ):
        raise ApiError(
            409,
            "bill_has_payment",
            "Only a bill with no payment can be deleted.",
        )
    if money_minor(invoice.get("amount_residual"), 2) <= 0:
        raise ApiError(409, "invoice_already_paid", "This bill is already fully paid.")

    partner_id = many2one_id(invoice.get("partner_id")) or 0
    partners = odoo.read("res.partner", [partner_id], ["name", "ref", "uuid"]) if partner_id else []
    partner = partners[0] if partners else {}
    if patient_uuid and str(partner.get("uuid") or "") != patient_uuid:
        raise ApiError(409, "invoice_wrong_patient", "This bill does not belong to this patient.")

    username = str(user.get("username") or "").strip() or "Accountant"
    try:
        if invoice.get("state") == "posted":
            execute_allowing_empty(odoo, "account.move", "button_draft", [[invoice_id]])
        execute(
            odoo,
            "account.move",
            "write",
            [[invoice_id], {"narration": f"Deleted by {username}. Reason: {reason}"}],
        )
        execute_allowing_empty(odoo, "account.move", "button_cancel", [[invoice_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            409,
            "bill_not_deleted",
            "This bill could not be deleted. Refresh and try again.",
        ) from error
    checked = odoo.read("account.move", [invoice_id], ["state"])
    if not checked or checked[0].get("state") != "cancel":
        raise ApiError(502, "bill_not_deleted", "This bill could not be deleted. Refresh and try again.")
    _cancel_unbilled_sale(odoo, str(invoice.get("invoice_origin") or ""))

    currency = load_currency(odoo, many2one_id(invoice.get("currency_id")))
    shop = ""
    origin = str(invoice.get("invoice_origin") or "")
    if origin:
        orders = odoo.search_read("sale.order", [("name", "=", origin)], ["shop_id"], limit=1)
        if orders:
            shop = many2one_name(orders[0].get("shop_id"))
    department = core.identify_department(shop or "", []) or ""
    import deleted_bills as deletions

    saved = deletions.record_deletion(
        {
            "invoiceId": invoice_id,
            "billNumber": invoice.get("name") or "",
            "patientName": partner.get("name") or many2one_name(invoice.get("partner_id")) or "Unknown patient",
            "hospitalNumber": core.chart_number_from_ref(str(partner.get("ref") or "")),
            "patientUuid": partner.get("uuid") or "",
            "department": department,
            "amount": format_money(as_float(invoice.get("amount_total")), currency)["formatted"],
            "reason": reason,
            "deletedBy": username,
        }
    )
    payload: dict[str, Any] = {
        "status": "ok",
        "success": True,
        "deleted": saved,
        "message": "The unpaid bill was deleted.",
    }
    if patient_uuid:
        payload["account"] = build_account(patient_uuid, cookie)
    return payload


def _cancel_unbilled_sale(odoo: OdooReader, origin: str) -> None:
    """Drop the source order when nothing has been dispensed, so the bill is not created again."""
    if not origin:
        return
    orders = odoo.search_read(
        "sale.order",
        [("name", "=", origin)],
        ["id", "state", "picking_ids"],
        limit=1,
    )
    if not orders or orders[0].get("state") in {"cancel", "draft"}:
        return
    picking_ids = [int(item) for item in (orders[0].get("picking_ids") or [])]
    if picking_ids:
        pickings = odoo.read("stock.picking", picking_ids, ["state"])
        if any(row.get("state") == "done" for row in pickings):
            return
    try:
        wizard_id = execute(odoo, "sale.order.cancel", "create", [{"order_id": int(orders[0]["id"])}])
        execute(odoo, "sale.order.cancel", "action_cancel", [[int(wizard_id)]])
    except Exception:
        return


def _record_waivers(
    odoo: OdooReader,
    invoices: list[dict[str, Any]],
    patient: dict[str, str],
    username: str,
    currency: dict[str, Any],
) -> None:
    import cashier_records as ledger

    partner_ids = {pid for row in invoices if (pid := many2one_id(row.get("partner_id")))}
    partners = {
        int(row["id"]): row
        for row in (odoo.read("res.partner", list(partner_ids), ["name", "ref"]) if partner_ids else [])
    }
    for invoice in invoices:
        partner = partners.get(many2one_id(invoice.get("partner_id")) or 0) or {}
        amount_value = as_float(invoice.get("amount_residual"))
        ledger.record_waiver(
            {
                "invoiceId": int(invoice["id"]),
                "billNumber": invoice.get("name") or "",
                "patientName": partner.get("name") or patient.get("name") or "Unknown patient",
                "hospitalNumber": core.chart_number_from_ref(str(partner.get("ref") or patient.get("mrn") or "")),
                "patientUuid": patient.get("uuid") or "",
                "amount": format_money(amount_value, currency)["formatted"],
                "amountValue": amount_value,
                "waivedBy": username,
            }
        )


def mark_waived_invoices(odoo: OdooReader, rows: list[dict[str, Any]], nhis: bool) -> None:
    """A fully written-off bill is Waived, and Waived | NHIS when the patient is covered."""
    if not rows:
        return
    import cashier_records as ledger

    stored = ledger.waivers_for([int(row["id"]) for row in rows])
    journal_amounts = _full_discount_amounts(
        odoo,
        [str(row.get("number") or "") for row in rows if int(row["id"]) not in stored],
    )
    for row in rows:
        invoice_id = int(row["id"])
        total = as_float((row.get("total") or {}).get("amount"))
        residual = as_float((row.get("outstanding") or {}).get("amount"))
        saved = stored.get(invoice_id)
        if saved:
            waived = float(saved.get("amountValue") or 0)
            who = str(saved.get("waivedBy") or "")
        else:
            waived = journal_amounts.get(str(row.get("number") or ""), 0.0)
            who = ""
            if waived + 0.02 < total or residual > 0.02 or waived <= 0.009:
                continue
        row["paymentStateLabel"] = "Waived | NHIS" if nhis else "Waived"
        row["waivedBy"] = who
        sample = row.get("paid") or row.get("total") or {}
        row["paid"] = format_money(
            max(total - waived, 0),
            {
                "code": sample.get("currencyCode") or "NGN",
                "symbol": sample.get("currencySymbol") or "₦",
                "decimalPlaces": sample.get("decimalPlaces") or 2,
                "position": "before",
            },
        )


def _full_discount_amounts(odoo: OdooReader, bill_numbers: list[str]) -> dict[str, float]:
    numbers = [number for number in bill_numbers if number]
    if not numbers:
        return {}
    moves = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "entry"),
            ("state", "=", "posted"),
            ("ref", "in", [f"Patient bill discount {number}" for number in numbers]),
        ],
        ["ref", "amount_total"],
        limit=max(len(numbers), 1),
    )
    totals: dict[str, float] = {}
    prefix = "Patient bill discount "
    for move in moves:
        ref = str(move.get("ref") or "")
        if not ref.startswith(prefix):
            continue
        name = ref[len(prefix) :].strip()
        totals[name] = totals.get(name, 0.0) + as_float(move.get("amount_total"))
    return totals


def list_waived_bills(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_accountant(cookie)
    params = query or {}
    limit = min(_query_int(params, "limit", 25) or 25, 100)
    offset = _query_int(params, "offset", 0)
    q = str((params.get("q") or [""])[0] or "").strip().lower()
    import cashier_records as ledger
    import consultation as clinical

    odoo = odoo_reader()
    stored = ledger.list_stored_waivers()
    known = {int(row["invoiceId"]) for row in stored}
    rows = [*stored, *_discover_full_waivers(odoo, known)]
    nhis = clinical.load_nhis_patients(odoo)
    prepared = []
    for row in rows:
        patient_uuid = str(row.get("patientUuid") or "")
        prepared.append(
            {
                **row,
                "statusLabel": "Waived | NHIS" if patient_uuid in nhis else "Waived",
            }
        )
    for row in prepared:
        row["waivedBy"] = staff_display_name(str(row.get("waivedBy") or ""))
        row["waivedAt"] = staff_instant(row.get("waivedAt")) or str(row.get("waivedAt") or "")
    if q:
        prepared = [
            row
            for row in prepared
            if q in str(row.get("patientName") or "").lower()
            or q in str(row.get("hospitalNumber") or "").lower()
            or q in str(row.get("billNumber") or "").lower()
            or q in str(row.get("waivedBy") or "").lower()
        ]
    prepared.sort(key=lambda row: (str(row.get("waivedAt") or ""), int(row.get("invoiceId") or 0)), reverse=True)
    total = len(prepared)
    return {
        "status": "ok",
        "items": prepared[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _discover_full_waivers(odoo: OdooReader, known_invoice_ids: set[int]) -> list[dict[str, Any]]:
    """Bills written off before the waiver list existed. The accountant name was not kept."""
    moves = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "entry"),
            ("state", "=", "posted"),
            ("ref", "ilike", "Patient bill discount INV%"),
        ],
        ["ref", "amount_total", "date"],
        limit=500,
    )
    prefix = "Patient bill discount "
    by_name: dict[str, dict[str, Any]] = {}
    for move in moves:
        ref = str(move.get("ref") or "")
        if not ref.startswith(prefix):
            continue
        name = ref[len(prefix) :].strip()
        bucket = by_name.setdefault(name, {"amount": 0.0, "date": ""})
        bucket["amount"] += as_float(move.get("amount_total"))
        bucket["date"] = max(str(bucket["date"]), str(move.get("date") or ""))
    if not by_name:
        return []
    invoices = odoo.search_read(
        "account.move",
        [("move_type", "=", "out_invoice"), ("name", "in", list(by_name))],
        ["name", "amount_total", "amount_residual", "partner_id", "currency_id", "invoice_date"],
        limit=len(by_name),
    )
    partner_ids = {pid for row in invoices if (pid := many2one_id(row.get("partner_id")))}
    partners = {
        int(row["id"]): row
        for row in (odoo.read("res.partner", list(partner_ids), ["name", "ref", "uuid"]) if partner_ids else [])
    }
    found = []
    for invoice in invoices:
        invoice_id = int(invoice["id"])
        if invoice_id in known_invoice_ids:
            continue
        written_off = by_name.get(str(invoice.get("name") or ""), {}).get("amount", 0)
        total = as_float(invoice.get("amount_total"))
        residual = as_float(invoice.get("amount_residual"))
        if written_off + 0.02 < total or residual > 0.02 or written_off <= 0.009:
            continue
        partner = partners.get(many2one_id(invoice.get("partner_id")) or 0) or {}
        currency = load_currency(odoo, many2one_id(invoice.get("currency_id")))
        found.append(
            {
                "invoiceId": invoice_id,
                "billNumber": invoice.get("name") or "",
                "patientName": partner.get("name") or many2one_name(invoice.get("partner_id")) or "Unknown patient",
                "hospitalNumber": core.chart_number_from_ref(str(partner.get("ref") or "")),
                "patientUuid": partner.get("uuid") or None,
                "amount": format_money(written_off, currency)["formatted"],
                "amountValue": written_off,
                "waivedBy": "",
                "waivedAt": by_name[str(invoice.get("name") or "")].get("date")
                or invoice.get("invoice_date")
                or "",
            }
        )
    return found


def list_deleted_bills(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_accountant(cookie)
    params = query or {}
    limit = min(_query_int(params, "limit", 25) or 25, 100)
    offset = _query_int(params, "offset", 0)
    q = str((params.get("q") or [""])[0] or "").strip()
    import deleted_bills as deletions

    payload = deletions.list_deletions(q, offset, limit)
    for item in payload.get("items") or []:
        item["deletedBy"] = staff_display_name(str(item.get("deletedBy") or ""))
        item["deletedAt"] = staff_instant(item.get("deletedAt")) or str(item.get("deletedAt") or "")
    return payload


CASHIER_SHOP = "Cashier"
CASHIER_CATEGORY = "Cashier"
CASHIER_PRODUCT = "Cashier bill"
_CREATED_BILLS: dict[str, dict[str, Any]] = {}
_CREATED_LOCK = threading.Lock()


def _bill_amount(raw: Any) -> float:
    text = str(raw if raw is not None else "").replace(",", "").replace("₦", "").strip()
    if not text:
        raise ApiError(422, "amount_required", "Enter the amount.")
    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise ApiError(422, "amount_required", "Enter the amount in naira.") from error
    if value <= 0:
        raise ApiError(422, "amount_required", "Enter an amount greater than zero.")
    if value > Decimal("100000000"):
        raise ApiError(422, "amount_required", "That amount is too large. Check it and try again.")
    return float(value.quantize(Decimal("0.01")))


def _ngn_currency_id(odoo: OdooReader) -> int | None:
    rows = odoo.search_read("res.currency", [("name", "=", "NGN")], ["id"], limit=1)
    return int(rows[0]["id"]) if rows else None


def ensure_cashier_masters(odoo: OdooReader) -> dict[str, Any]:
    """A service the cashier can price per bill. The typed reason is the line the staff see."""
    services = odoo.search_read(
        "product.category",
        [("complete_name", "=", "All / Services")],
        ["id"],
        limit=1,
    )
    parent_id = int(services[0]["id"]) if services else None
    categories = odoo.search_read(
        "product.category",
        [("name", "=", CASHIER_CATEGORY), ("parent_id", "=", parent_id)] if parent_id else [("name", "=", CASHIER_CATEGORY)],
        ["id"],
        limit=1,
    )
    if categories:
        category_id = int(categories[0]["id"])
    else:
        category_id = int(
            execute(odoo, "product.category", "create", [{"name": CASHIER_CATEGORY, "parent_id": parent_id}])
        )
    products = odoo.search_read(
        "product.product",
        [("name", "=", CASHIER_PRODUCT), ("categ_id", "=", category_id)],
        ["id", "name", "taxes_id"],
        limit=1,
    )
    if products:
        product = products[0]
        product_id = int(product["id"])
        if product.get("taxes_id"):
            execute(odoo, "product.product", "write", [[product_id], {"taxes_id": [(6, 0, [])]}])
    else:
        product_id = int(
            execute(
                odoo,
                "product.product",
                "create",
                [
                    {
                        "name": CASHIER_PRODUCT,
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
        product = {"id": product_id, "name": CASHIER_PRODUCT}
    ngn_id = _ngn_currency_id(odoo)
    if not ngn_id:
        raise ApiError(503, "odoo_config", "Naira is not available for billing.")
    pricelists = odoo.search_read("product.pricelist", [("name", "=", CASHIER_SHOP)], ["id"], limit=1)
    if pricelists:
        pricelist_id = int(pricelists[0]["id"])
    else:
        pricelist_id = int(
            execute(odoo, "product.pricelist", "create", [{"name": CASHIER_SHOP, "currency_id": ngn_id}])
        )
    shops = odoo.search_read(
        "sale.shop",
        [("name", "=", CASHIER_SHOP)],
        ["id", "name", "warehouse_id", "pricelist_id", "payment_default_id"],
        limit=1,
    )
    if shops:
        shop = shops[0]
    else:
        registration = odoo.search_read(
            "sale.shop",
            [("name", "=", "Registration Desk")],
            ["warehouse_id", "payment_default_id", "company_id"],
            limit=1,
        )
        source = registration[0] if registration else {}
        shop_id = int(
            execute(
                odoo,
                "sale.shop",
                "create",
                [
                    {
                        "name": CASHIER_SHOP,
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
    return {"product": product, "shop": shop}


def _posted_cashier_invoice(odoo: OdooReader, sale: dict[str, Any]) -> dict[str, Any] | None:
    invoice_ids = [int(item) for item in (sale.get("invoice_ids") or []) if item]
    invoices = (
        odoo.read(
            "account.move",
            invoice_ids,
            ["name", "state", "move_type", "currency_id", "amount_total"],
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
    origin = str(sale.get("name") or "")
    if not origin:
        return None
    found = odoo.search_read(
        "account.move",
        [("move_type", "=", "out_invoice"), ("invoice_origin", "=", origin), ("state", "=", "posted")],
        ["name", "state", "move_type", "currency_id", "amount_total"],
        limit=1,
    )
    return found[0] if found else None


def annotate_created_bills(rows: list[dict[str, Any]]) -> None:
    """Show the reason the accountant typed, and who created the bill."""
    if not rows:
        return
    import cashier_records as ledger

    found = ledger.creators_for([int(row["id"]) for row in rows if row.get("id")])
    for row in rows:
        saved = found.get(int(row["id"]))
        if not saved:
            continue
        row["createdBy"] = staff_display_name(str(saved.get("createdBy") or ""))
        description = saved.get("description") or ""
        if not description:
            continue
        row["description"] = description
        lines = row.get("lines") or []
        if len(lines) == 1:
            lines[0]["description"] = description


def _cashier_walkin_partner(odoo: OdooReader, name: str, token: str) -> dict[str, Any]:
    """A billing name for someone who is not on the hospital register."""
    ref = f"CASHIER-WALKIN:{token}"
    link = f"cashier:{token}"
    existing = odoo.search_read(
        "res.partner",
        [("ref", "=", ref)],
        ["id", "name", "ref", "uuid"],
        limit=1,
    )
    if existing:
        return existing[0]
    values = {
        "name": name,
        "ref": ref,
        "uuid": link,
        "customer_rank": 1,
        "company_type": "person",
    }
    partner_id = int(execute(odoo, "res.partner", "create", [values]))
    rows = odoo.read("res.partner", [partner_id], ["id", "name", "ref", "uuid"])
    return rows[0] if rows else {"id": partner_id, "name": name, "ref": ref, "uuid": link}


def create_cashier_bill(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Create one unpaid bill for a patient. The signed-in accountant is recorded."""
    user = require_accountant(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    patient_name = " ".join(str(body.get("patientName") or "").split())
    description = " ".join(str(body.get("description") or "").split())
    request_id = str(body.get("requestId") or "").strip()
    if not patient_uuid and len(patient_name) < 2:
        raise ApiError(422, "patient_required", "Choose a patient, or enter the name of someone who is not registered.")
    if len(description) < 3:
        raise ApiError(422, "description_required", "Say what this bill is for.")
    if len(description) > 200:
        raise ApiError(422, "description_required", "Shorten what this bill is for.")
    amount = _bill_amount(body.get("amount"))
    if request_id:
        with _CREATED_LOCK:
            prior = _CREATED_BILLS.get(request_id)
        if prior:
            return prior
    odoo = odoo_reader()
    if patient_uuid:
        patient = load_openmrs_patient(patient_uuid, cookie)
        partner = find_partner(odoo, patient)
        if not partner:
            import registration as cards

            partner = cards.ensure_patient_partner(odoo, patient)
        if not partner:
            raise ApiError(
                409,
                "account_not_found",
                "This patient has no account yet. Try again in a moment.",
            )
    else:
        token = uuid.uuid4().hex
        partner = _cashier_walkin_partner(odoo, patient_name, token)
        patient = {
            "uuid": str(partner.get("uuid") or f"cashier:{token}"),
            "name": str(partner.get("name") or patient_name),
            "mrn": "",
        }
        patient_uuid = patient["uuid"]
    masters = ensure_cashier_masters(odoo)
    product = masters["product"]
    shop = masters["shop"]
    charge_ref = f"CASHIER-{uuid.uuid4()}"
    try:
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
                        "pricelist_id": many2one_id(shop.get("pricelist_id")) or 1,
                        "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                        "origin": charge_ref,
                        "care_setting": "opd",
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": int(product["id"]),
                                    "name": description,
                                    "product_uom_qty": 1,
                                    "price_unit": amount,
                                    "tax_id": [(6, 0, [])],
                                    "external_order_id": charge_ref,
                                    "external_id": patient_uuid,
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
                [line_ids, {"tax_id": [(6, 0, [])], "price_unit": amount, "name": description}],
            )
        execute_allowing_empty(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "bill_not_created",
            "The bill could not be created. Check the amount and try again.",
        ) from error
    sales = odoo.read("sale.order", [sale_id], ["name", "state", "invoice_ids", "amount_total"])
    if not sales or sales[0].get("state") not in {"sale", "done"}:
        raise ApiError(502, "bill_not_created", "The bill could not be created. Check the amount and try again.")
    invoice = _posted_cashier_invoice(odoo, sales[0])
    if not invoice:
        raise ApiError(502, "bill_not_created", "The bill could not be created. Check the amount and try again.")
    username = str(user.get("username") or "").strip() or "Accountant"
    currency = load_currency(odoo, many2one_id(invoice.get("currency_id")))
    money = format_money(amount, currency)
    import cashier_records as ledger

    ledger.record_created_bill(
        {
            "invoiceId": int(invoice["id"]),
            "billNumber": invoice.get("name") or "",
            "patientName": partner.get("name") or patient.get("name") or "Unknown patient",
            "hospitalNumber": core.chart_number_from_ref(str(partner.get("ref") or patient.get("mrn") or "")),
            "patientUuid": patient.get("uuid") or patient_uuid,
            "description": description,
            "amount": money["formatted"],
            "amountValue": amount,
            "createdBy": username,
        }
    )
    payload = {
        "status": "ok",
        "success": True,
        "invoiceId": int(invoice["id"]),
        "billNumber": invoice.get("name") or "",
        "amount": money,
        "description": description,
        "createdBy": username,
        "patient": {
            "uuid": patient.get("uuid") or patient_uuid,
            "name": patient.get("name") or partner.get("name") or "",
        },
    }
    if request_id:
        with _CREATED_LOCK:
            _CREATED_BILLS[request_id] = payload
            if len(_CREATED_BILLS) > 200:
                _CREATED_BILLS.pop(next(iter(_CREATED_BILLS)))
    return payload


def waive_bills(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Write off the whole selected bill. No money is collected."""
    user = require_accountant(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    raw_ids = body.get("invoiceIds") or []
    try:
        invoice_ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_invoices", "Those bills cannot be waived.") from error
    if not invoice_ids:
        raise ApiError(422, "invalid_invoices", "Select a bill to waive.")
    expected_raw = body.get("expectedResiduals") or {}
    expected: dict[int, float] | None = None
    if expected_raw:
        try:
            expected = {int(key): as_float(value) for key, value in expected_raw.items()}
        except (TypeError, ValueError) as error:
            raise ApiError(422, "invalid_residuals", "The amount due has changed. Refresh and try again.") from error

    patient = load_openmrs_patient(patient_uuid, cookie)
    odoo = odoo_reader()
    partner = find_partner(odoo, patient)
    if not partner:
        raise ApiError(404, "account_not_found", "No bills for this patient.")
    invoices, outstanding = _validate_invoices(odoo, int(partner["id"]), invoice_ids, expected)
    if outstanding <= 0:
        raise ApiError(409, "invoice_already_paid", "This bill is already fully paid.")
    currency = load_currency(odoo, many2one_id(invoices[0].get("currency_id")))
    apply_invoice_discounts(odoo, invoices, 100.0, currency)
    username = str(user.get("username") or "").strip() or "Accountant"
    _record_waivers(odoo, invoices, patient, username, currency)
    account = build_account(patient_uuid, cookie)
    return {
        "status": "ok",
        "success": True,
        "patient": {"uuid": patient.get("uuid"), "name": patient.get("name")},
        "account": account,
    }


def _payment_id_from_action(action: Any) -> int | None:
    if isinstance(action, dict):
        if action.get("res_id"):
            return int(action["res_id"])
        res_ids = action.get("res_ids") or []
        if res_ids:
            return int(res_ids[0])
        domain = action.get("domain")
        if isinstance(domain, list):
            for clause in domain:
                if isinstance(clause, (list, tuple)) and clause and clause[0] == "id":
                    value = clause[-1]
                    if isinstance(value, list) and value:
                        return int(value[0])
                    if isinstance(value, int):
                        return int(value)
    if isinstance(action, int):
        return action
    return None


def _receipt_money(amount: Any, currency: dict[str, Any]) -> str:
    formatted = str(format_money(as_float(amount), currency).get("formatted") or "")
    return formatted.replace("₦", "NGN ")


def _sale_code(value: str) -> bool:
    text = str(value or "").strip()
    return len(text) > 1 and text[0] in "Ss" and text[1:].isdigit()


def _receipt_clock(value: Any) -> str:
    instant = staff_instant(value)
    if len(instant) >= 16 and instant[4] == "-" and instant[7] == "-" and "T" in instant[:19]:
        year, month, day = instant[:10].split("-")
        return f"{day}/{month}/{year} {instant[11:16]}"
    if len(instant) == 10 and instant[4] == "-" and instant[7] == "-":
        year, month, day = instant.split("-")
        return f"{day}/{month}/{year}"
    return instant


def _receipt_department(invoice: dict[str, Any]) -> str:
    department = str(invoice.get("department") or "").strip()
    if department:
        return department
    origin = str(invoice.get("invoice_origin") or invoice.get("ref") or "").strip()
    if origin and not _sale_code(origin):
        return origin
    return "Bill"


def _receipt_lines(invoice: dict[str, Any]) -> list[dict[str, Any]]:
    raw = invoice.get("lines")
    if not isinstance(raw, list):
        return []
    lines: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").split("\n", 1)[0].strip()
        if not name or _sale_code(name):
            continue
        lines.append(item)
    return lines


def _describe_receipt_invoices(odoo: OdooReader, invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Department and the charges on each bill. A sale code is not a description."""
    origins = [str(row.get("invoice_origin") or "") for row in invoices if row.get("invoice_origin")]
    shop_by_origin: dict[str, str] = {}
    if origins:
        try:
            orders = odoo.search_read(
                "sale.order",
                [("name", "in", origins)],
                ["name", "shop_id"],
                limit=max(len(origins), 1),
            )
            shop_by_origin = {str(row.get("name") or ""): many2one_name(row.get("shop_id")) for row in orders}
        except Exception:
            shop_by_origin = {}
    line_ids = [int(item) for row in invoices for item in (row.get("invoice_line_ids") or []) if item]
    lines_by_move: dict[int, list[dict[str, Any]]] = {}
    raw_lines: list[dict[str, Any]] = []
    if line_ids:
        try:
            raw_lines = odoo.read(
                "account.move.line",
                line_ids,
                ["move_id", "name", "quantity", "price_subtotal", "price_total", "product_id", "display_type"],
            )
        except Exception:
            try:
                raw_lines = odoo.read(
                    "account.move.line",
                    line_ids,
                    ["move_id", "name", "quantity", "price_subtotal", "product_id"],
                )
            except Exception:
                raw_lines = []
    for line in raw_lines:
        display = str(line.get("display_type") or "")
        if display in {"line_section", "line_note", "payment_term"}:
            continue
        if not line.get("product_id") and as_float(line.get("quantity")) == 0:
            continue
        name = str(line.get("name") or "").split("\n", 1)[0].strip()
        if not name:
            continue
        amount = line.get("price_total")
        if amount in (None, False, ""):
            amount = line.get("price_subtotal")
        move_id = many2one_id(line.get("move_id"))
        if not move_id:
            continue
        lines_by_move.setdefault(int(move_id), []).append(
            {"name": name, "amount": amount, "quantity": line.get("quantity")}
        )
    described: list[dict[str, Any]] = []
    for invoice in invoices:
        shop = shop_by_origin.get(str(invoice.get("invoice_origin") or "")) or ""
        department = core.identify_department(shop, []) or shop or ""
        move_id = int(invoice["id"]) if invoice.get("id") else 0
        lines = lines_by_move.get(move_id) or []
        described.append({**invoice, "department": department, "lines": lines})
    return described


def _plain_receipt(value: Any) -> str:
    text = str(value or "").replace("₦", "NGN ").replace("—", "-").replace("–", "-")
    return text.encode("latin-1", "ignore").decode("latin-1")


def _compose_receipt(
    *,
    page_h: int,
    patient: str,
    mrn: str,
    receipt: str,
    collected: str,
    method: str,
    collector: str,
    invoices: list[dict[str, Any]],
    currency: dict[str, Any],
    total: str,
) -> tuple[list[str], float]:
    from lab_result_report import BODY_INK, _write_lines, _wrap_text

    title = "Payment receipt"
    title_x = round((612 - len(title) * 6.6) / 2, 1)
    commands = [
        "q",
        f"612 0 0 122 0 {page_h - 122} cm",
        "/Im1 Do",
        "Q",
        "0.051 0.451 0.467 rg",
        f"0 {page_h - 122} 612 24 re f",
        "BT",
        "/F2 13 Tf",
        "1 1 1 rg",
        f"1 0 0 1 {title_x:.1f} {page_h - 115} Tm",
        f"({_plain_receipt(title)}) Tj",
        "ET",
    ]
    identity = [
        f"Patient: {_plain_receipt(patient)}",
        f"Hospital number: {_plain_receipt(mrn) or '-'}",
        f"Receipt: {_plain_receipt(receipt) or '-'}",
        f"Collected: {_plain_receipt(collected) or '-'}",
        f"Method: {_plain_receipt(method) or '-'}",
    ]
    if collector:
        identity.append(f"Collected by: {_plain_receipt(collector)}")
    y = _write_lines(
        commands,
        x=36,
        y=page_h - 150,
        lines=identity,
        font="/F1 9 Tf",
        ink=BODY_INK,
        leading=14,
    )
    y -= 18
    if not invoices:
        y = _write_lines(
            commands,
            x=36,
            y=y,
            lines=["No separate bill was linked to this receipt."],
            font="/F1 10 Tf",
            ink=BODY_INK,
            leading=14,
        )
        y -= 12
    for invoice in invoices:
        department = _plain_receipt(_receipt_department(invoice)) or "Bill"
        title_lines = _wrap_text(department, 70)
        bar_h = 16 + 13 * max(len(title_lines) - 1, 0)
        commands.extend(
            [
                "0.051 0.451 0.467 rg",
                f"28 {y - 4:.1f} 556 {bar_h:.1f} re f",
            ]
        )
        y = _write_lines(
            commands,
            x=36,
            y=y,
            lines=title_lines,
            font="/F2 11 Tf",
            ink="1 1 1 rg",
            leading=13,
        )
        y -= 8
        lines = _receipt_lines(invoice)
        if not lines:
            lines = [{"name": "Bill", "amount": invoice.get("amount_total"), "quantity": 1}]
        for line in lines:
            name = _plain_receipt(str(line.get("name") or "Charge").split("\n", 1)[0])
            quantity = as_float(line.get("quantity"))
            if quantity and abs(quantity - 1) > 0.001:
                shown = str(int(quantity)) if abs(quantity - round(quantity)) < 0.001 else f"{quantity:g}"
                name = f"{shown} x {name}"
            y = _write_lines(
                commands,
                x=36,
                y=y,
                lines=_wrap_text(name, 80),
                font="/F2 10 Tf",
                ink="0.07 0.18 0.22 rg",
                leading=13,
            )
            y -= 2
            y = _write_lines(
                commands,
                x=36,
                y=y,
                lines=[_receipt_money(line.get("amount"), currency)],
                font="/F1 10 Tf",
                ink=BODY_INK,
                leading=14,
            )
            y -= 8
        number = _plain_receipt(str(invoice.get("name") or ""))
        if number:
            y = _write_lines(
                commands,
                x=36,
                y=y,
                lines=[f"Bill {number}"],
                font="/F1 9 Tf",
                ink="0.28 0.34 0.4 rg",
                leading=12,
            )
            y -= 6
        y -= 6
        commands.extend(
            [
                "0.75 0.8 0.84 RG",
                "0.8 w",
                f"28 {y:.1f} m 584 {y:.1f} l S",
            ]
        )
        y -= 16
    y -= 6
    y = _write_lines(
        commands,
        x=36,
        y=y,
        lines=[f"Total collected: {total}"],
        font="/F2 12 Tf",
        ink="0.07 0.18 0.22 rg",
        leading=16,
    )
    y -= 8
    y = _write_lines(
        commands,
        x=36,
        y=y,
        lines=["Hospital EMR"],
        font="/F1 8 Tf",
        ink="0.2 0.25 0.3 rg",
        leading=12,
    )
    return commands, y


def _payment_receipt_pdf(
    payment: dict[str, Any],
    invoices: list[dict[str, Any]],
    currency: dict[str, Any],
    partner: dict[str, Any],
    collected: dict[str, str],
) -> bytes:
    from pathlib import Path

    from certificates import _assemble, _image_object

    header_path = Path(__file__).resolve().parent / "assets" / "certificate-header-birth.jpg"
    header_jpeg = header_path.read_bytes() if header_path.is_file() else b""
    if not header_jpeg.startswith(b"\xff\xd8"):
        raise ApiError(500, "receipt_unavailable", "The receipt could not be prepared.")
    patient = str(partner.get("name") or many2one_name(payment.get("partner_id")) or "Patient")
    when = _receipt_clock(collected.get("collectedAt") or payment.get("create_date") or payment.get("date") or "")
    page_h = 792
    commands: list[str] = []
    y = 0.0
    while page_h < 12000:
        commands, y = _compose_receipt(
            page_h=page_h,
            patient=patient,
            mrn=str(partner.get("ref") or ""),
            receipt=str(payment.get("name") or ""),
            collected=when,
            method=str(many2one_name(payment.get("journal_id")) or ""),
            collector=str(collected.get("collectedBy") or ""),
            invoices=invoices,
            currency=currency,
            total=_receipt_money(payment.get("amount"), currency),
        )
        if y >= 46:
            break
        page_h += int(46 - y) + 80
    stream = "\n".join(commands).encode("latin-1", "replace")
    content = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    image = _image_object(header_jpeg)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 612 {page_h}] >>".encode("ascii"),
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 "
            + str(page_h).encode("ascii")
            + b"] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> /XObject << /Im1 7 0 R >> >> /Contents 4 0 R >>"
        ),
        content,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        image,
    ]
    return _assemble(objects)


def render_receipt_pdf(payment_id: int, cookie: str) -> tuple[bytes, str]:
    require_accountant(cookie)
    odoo = odoo_reader()
    rows = odoo.read(
        "account.payment",
        [payment_id],
        ["name", "state", "amount", "date", "partner_id", "journal_id", "currency_id", "reconciled_invoice_ids", "create_date"],
    )
    if not rows or rows[0].get("state") != "posted":
        raise ApiError(404, "payment_not_found", "Payment not found.")
    payment = rows[0]
    reference = payment.get("name") or f"payment-{payment_id}"
    currency = load_currency(odoo, many2one_id(payment.get("currency_id")))
    invoice_ids = [int(item) for item in (payment.get("reconciled_invoice_ids") or []) if item]
    invoices: list[dict[str, Any]] = []
    if invoice_ids:
        try:
            invoices = odoo.read(
                "account.move",
                invoice_ids,
                ["name", "amount_total", "invoice_origin", "ref", "invoice_line_ids"],
            )
        except Exception:
            invoices = odoo.read("account.move", invoice_ids, ["name", "amount_total"])
        invoices = _describe_receipt_invoices(odoo, invoices)
    partner_id = many2one_id(payment.get("partner_id"))
    partner = {}
    if partner_id:
        found = odoo.read("res.partner", [partner_id], ["name", "ref"])
        partner = found[0] if found else {}
    collected = {}
    try:
        import cashier_records

        collected = cashier_records.collection_facts([payment_id]).get(payment_id) or {}
    except Exception:
        collected = {}
    pdf = _payment_receipt_pdf(payment, invoices, currency, partner, collected)
    return pdf, str(reference)


def _fetch_odoo_report(report_name: str, payment_id: int) -> bytes | None:
    if not ODOO_USER or not ODOO_PASSWORD:
        return None
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    auth = Request(
        f"{ODOO_URL}/web/session/authenticate",
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "params": {"db": ODOO_DB, "login": ODOO_USER, "password": ODOO_PASSWORD},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener.open(auth, timeout=20)
        response = opener.open(
            f"{ODOO_URL}/report/pdf/{report_name}/{payment_id}",
            timeout=40,
        )
        data = response.read()
        if data.startswith(b"%PDF"):
            return data
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    return None


def new_request_id() -> str:
    return str(uuid.uuid4())
