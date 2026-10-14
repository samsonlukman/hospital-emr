#!/usr/bin/env python3
"""Hospital EMR financial API.

Patient Account reads are read-only.
Accountant payment writes go through Odoo account.payment.register only.
Odoo credentials stay server-side.
"""

from __future__ import annotations

import base64
import json
import os
import traceback
import xmlrpc.client
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote
from urllib.request import Request, urlopen

from deployment_config import validate_deployment_config

LISTEN_HOST = os.environ.get("ABIKAN_API_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("ABIKAN_API_PORT", "8787"))
OPENMRS_URL = os.environ.get("ABIKAN_OPENMRS_URL", "http://openmrs:8080").rstrip("/")
OPENMRS_ADMIN_USER = os.environ.get("ABIKAN_OPENMRS_ADMIN_USER", "")
OPENMRS_ADMIN_PASSWORD = os.environ.get("ABIKAN_OPENMRS_ADMIN_PASSWORD", "")
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://odoo:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
ODOO_USER = os.environ.get("ABIKAN_ODOO_USER", "")
ODOO_PASSWORD = os.environ.get("ABIKAN_ODOO_PASSWORD", "")

PAYMENT_STATE_LABELS = {
    "not_paid": "UNPAID",
    "partial": "PARTIALLY PAID",
    "in_payment": "PAYMENT PROCESSING / IN PAYMENT",
    "paid": "PAID",
    "reversed": "REVERSED",
}

MIXED_CURRENCY_MESSAGE = "Select invoices in the same currency."


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def many2one_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    return None


def many2one_name(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return str(value[1] or "")
    return ""


def as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def money_decimal(value: Any, places: int = 2) -> Decimal:
    """Quantize a monetary value with half-up rounding. Never use binary float equality."""
    quant = Decimal("1").scaleb(-int(places))
    if value is None or value == "":
        raw = Decimal("0")
    elif isinstance(value, Decimal):
        raw = value
    else:
        try:
            raw = Decimal(str(value).strip() or "0")
        except (InvalidOperation, ValueError, TypeError):
            raw = Decimal("0")
    return raw.quantize(quant, rounding=ROUND_HALF_UP)


def money_minor(value: Any, places: int = 2) -> int:
    return int(money_decimal(value, places) * (Decimal(10) ** int(places)))


def money_major(minor: int, places: int = 2) -> float:
    return float(Decimal(int(minor)) / (Decimal(10) ** int(places)))


def format_money(amount: float, currency: dict[str, Any]) -> dict[str, Any]:
    places = int(currency.get("decimalPlaces") or 2)
    amount = float(money_decimal(amount, places))
    symbol = str(currency.get("symbol") or "")
    code = str(currency.get("code") or "")
    position = str(currency.get("position") or "before")
    # Hospital EMR hospitals display Naira with ₦ before the amount.
    if code == "NGN" or symbol in {"₦", "NGN"}:
        code = "NGN"
        symbol = "₦"
        position = "before"
    number = f"{amount:,.{places}f}"
    if symbol and position == "after":
        formatted = f"{number} {symbol}"
    elif symbol:
        formatted = f"{symbol}{number}"
    else:
        formatted = f"{number} {code}".strip()
    return {
        "amount": amount,
        "formatted": formatted,
        "currencyCode": code,
        "currencySymbol": symbol,
        "decimalPlaces": places,
    }


def abikan_currency(row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize hospital money for staff screens. Always NGN with ₦ before amount."""
    source = row or {}
    places = int(source.get("decimal_places") or source.get("decimalPlaces") or 2)
    return {
        "code": "NGN",
        "symbol": "₦",
        "decimalPlaces": places,
        "position": "before",
    }


def currency_sort_key(code: str) -> tuple[int, str]:
    preferred = {"NGN": 0, "USD": 1}
    return (preferred.get(code, 99), code)


def aggregate_by_currency(amounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sum amounts that share a currency. Never convert or mix currencies."""
    buckets: dict[str, dict[str, Any]] = {}
    for money in amounts:
        if not money:
            continue
        code = str(money.get("currencyCode") or money.get("code") or "")
        symbol = str(money.get("currencySymbol") or money.get("symbol") or "")
        if code == "NGN" or symbol in {"₦", "NGN"}:
            code, symbol = "NGN", "₦"
        key = code or symbol
        if not key:
            continue
        if key not in buckets:
            buckets[key] = {
                "amount": 0.0,
                "currency": {
                    "code": code,
                    "symbol": symbol,
                    "decimalPlaces": int(money.get("decimalPlaces") or 2),
                    "position": "before" if code == "NGN" or symbol == "₦" else (
                        "after"
                        if symbol and str(money.get("formatted") or "").endswith(symbol)
                        else "before"
                    ),
                },
            }
        buckets[key]["amount"] += as_float(money.get("amount"))
    return [
        format_money(buckets[key]["amount"], buckets[key]["currency"])
        for key in sorted(buckets, key=currency_sort_key)
    ]


def identify_department(shop_name: str, category_names: list[str]) -> str | None:
    shop = (shop_name or "").lower()
    categories = " ".join(category_names).lower()
    if "cashier" in shop or "cashier" in categories:
        return "Cashier"
    if "registration" in shop or "registration" in categories:
        return "Registration"
    if "consultation" in shop or "consultation" in categories:
        return "Consultation"
    if "laboratory" in shop or "laboratory" in categories:
        return "Laboratory"
    if " / lab" in f" {categories}" or "/ lab /" in categories:
        return "Laboratory"
    if "radiology" in shop or "radiology" in categories:
        return "Radiology"
    if "pharmacy" in shop:
        return "Pharmacy"
    if "drug" in categories:
        return "Pharmacy"
    if "accommodation" in shop or "accommodation" in categories:
        return "Accommodation"
    if "theatre" in shop or "theater" in shop or "theatre" in categories or "theater" in categories:
        return "Theatre"
    if "physio" in shop or "physiotherapy" in shop or "physio" in categories:
        return "Physiotherapy"
    if "dental" in shop or "dental" in categories:
        return "Dental"
    return None


def department_label(name: str | None) -> str:
    return name or "Department not identified"


def payment_state_label(state: str | None) -> str:
    if not state:
        return "UNPAID"
    return PAYMENT_STATE_LABELS.get(state, state.replace("_", " ").upper())


def pharmacy_dispensing_status(payment_state: str | None, picking_states: list[str]) -> str:
    paid = payment_state in {"paid", "in_payment"}
    if not paid:
        if payment_state == "partial":
            return "UNPAID"
        return "UNPAID"
    if any(state == "done" for state in picking_states):
        return "DISPENSED"
    if picking_states:
        return "READY TO DISPENSE"
    return "PAID"


class OdooReader:
    def __init__(self) -> None:
        if not ODOO_USER or not ODOO_PASSWORD:
            raise ApiError(503, "odoo_config", "Financial service is not configured.")
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
        self.uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        if not self.uid:
            raise ApiError(503, "odoo_auth", "Financial service is unavailable.")
        self.models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self.models.execute_kw(
            ODOO_DB,
            self.uid,
            ODOO_PASSWORD,
            model,
            "search_read",
            [domain],
            {"fields": fields, "limit": limit},
        )

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        return self.models.execute_kw(
            ODOO_DB,
            self.uid,
            ODOO_PASSWORD,
            model,
            "read",
            [ids],
            {"fields": fields},
        )


def openmrs_get(path: str, cookie: str) -> dict[str, Any]:
    request = Request(
        f"{OPENMRS_URL}{path}",
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
            raise ApiError(404, "patient_not_found", "Patient not found.") from error
        raise ApiError(502, "openmrs_error", "Clinical service is unavailable.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "Clinical service is unavailable.") from error


def openmrs_service_get(path: str) -> dict[str, Any]:
    if not OPENMRS_ADMIN_USER or not OPENMRS_ADMIN_PASSWORD:
        raise ApiError(503, "identity_service_config", "Identity service is unavailable.")
    token = base64.b64encode(
        f"{OPENMRS_ADMIN_USER}:{OPENMRS_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        f"{OPENMRS_URL}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {token}",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(503, "identity_service_error", "Identity service is unavailable.") from error


def openmrs_service_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not OPENMRS_ADMIN_USER or not OPENMRS_ADMIN_PASSWORD:
        raise ApiError(503, "clinical_write_config", "Clinical service is unavailable.")
    token = base64.b64encode(
        f"{OPENMRS_ADMIN_USER}:{OPENMRS_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        f"{OPENMRS_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        raise ApiError(502, "clinical_write_error", "The clinical record could not be saved.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "clinical_write_error", "The clinical record could not be saved.") from error


def invalidate_openmrs_session(cookie: str) -> None:
    if not cookie:
        return
    request = Request(
        f"{OPENMRS_URL}/openmrs/ws/rest/v1/session",
        headers={"Accept": "application/json", "Cookie": cookie},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=20):
            return
    except (HTTPError, URLError, TimeoutError):
        return


def require_session(cookie: str) -> dict[str, Any]:
    session = openmrs_get("/openmrs/ws/rest/v1/session", cookie)
    if not session.get("authenticated"):
        raise ApiError(401, "unauthenticated", "Sign in required.")
    session_user = session.get("user") or {}
    user_uuid = str(session_user.get("uuid") or "")
    if not user_uuid:
        invalidate_openmrs_session(cookie)
        raise ApiError(401, "unauthenticated", "Sign in required.")
    state = openmrs_service_get(
        f"/openmrs/ws/rest/v1/user/{user_uuid}?v=custom:(uuid,retired)"
    )
    if state.get("retired") is True:
        invalidate_openmrs_session(cookie)
        raise ApiError(
            401,
            "account_disabled",
            "This account has been disabled. Sign in with an active account.",
        )
    return session


PATIENT_ACCOUNT_PRIVILEGES = {
    "app:registration",
    "app:clinical",
    "app:adt",
    "app:lab-lite",
    "app:radiology-upload",
    "bahmni:clinical:dispense",
    "abikan:accountant",
    "abikan:admin:staff",
    "app:admin",
}
ADMIN_ROLES = {"SuperAdmin", "System Developer"}


def require_patient_account_view(cookie: str) -> None:
    require_session(cookie)
    import accountant as cashier

    user = cashier.load_openmrs_user(cookie)
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    if roles & ADMIN_ROLES or privileges & PATIENT_ACCOUNT_PRIVILEGES:
        return
    raise ApiError(403, "forbidden", "This account cannot open Patient Account.")


def load_openmrs_patient(patient_uuid: str, cookie: str) -> dict[str, str]:
    """A registered chart, or a bill for someone who is not registered."""
    walkin_ref = walkin_ref_for_account(patient_uuid)
    if walkin_ref:
        odoo = OdooReader()
        rows = odoo.search_read(
            "res.partner",
            ["|", ("uuid", "=", patient_uuid), ("ref", "=", walkin_ref)],
            ["name", "ref", "uuid"],
            limit=1,
        )
        if not rows:
            raise ApiError(404, "patient_not_found", "This patient could not be found.")
        return {
            "uuid": patient_uuid,
            "name": str(rows[0].get("name") or "Unknown patient"),
            "mrn": "",
        }
    try:
        patient = openmrs_get(
            f"/openmrs/ws/rest/v1/patient/{patient_uuid}"
            "?v=custom:(uuid,display,identifiers:(identifier,preferred,identifierType:(name)))",
            cookie,
        )
    except ApiError as error:
        if error.status == 401:
            raise
        import patient_directory as register

        return register.load_patient_identity(patient_uuid)
    identifiers = patient.get("identifiers") or []
    preferred = next((item for item in identifiers if item.get("preferred")), None)
    mrn = (
        (preferred or {}).get("identifier")
        or (identifiers[0].get("identifier") if identifiers else None)
        or ""
    )
    display = (patient.get("display") or "").strip()
    name = display
    if " - " in display:
        left, right = display.split(" - ", 1)
        if not mrn:
            mrn = left.strip()
        name = right.strip()
    if not mrn:
        raise ApiError(422, "mrn_missing", "This patient has no medical record number.")
    return {
        "uuid": patient.get("uuid") or patient_uuid,
        "name": name or "Unknown patient",
        "mrn": mrn,
    }


def load_currency(odoo: OdooReader, currency_id: int | None) -> dict[str, Any]:
    """Load a currency for staff screens.

    Hospital EMR hospitals use Naira. Prefer NGN when no currency is specified (the
    Odoo company may still be set to USD), and always show ₦ before the amount.
    """
    row: dict[str, Any] = {}
    if not currency_id:
        ngn_rows = odoo.search_read(
            "res.currency",
            [("name", "=", "NGN")],
            ["name", "symbol", "decimal_places", "position"],
            limit=1,
        )
        if ngn_rows:
            return abikan_currency(ngn_rows[0])
        companies = odoo.search_read("res.company", [], ["currency_id"], limit=1)
        currency_id = many2one_id(companies[0].get("currency_id")) if companies else None
    if not currency_id:
        rows = odoo.search_read(
            "res.currency",
            [],
            ["name", "symbol", "decimal_places", "position"],
            limit=1,
        )
        row = rows[0] if rows else {}
    else:
        rows = odoo.read(
            "res.currency",
            [currency_id],
            ["name", "symbol", "decimal_places", "position"],
        )
        row = rows[0] if rows else {}
    code = str(row.get("name") or "")
    if code == "NGN":
        return abikan_currency(row)
    return {
        "code": code,
        "symbol": str(row.get("symbol") or ""),
        "decimalPlaces": int(row.get("decimal_places") or 2),
        "position": str(row.get("position") or "before"),
    }


WALKIN_REF_PREFIXES = ("LAB-WALKIN:", "RAD-WALKIN:", "PHARM-WALKIN:")
WALKIN_ACCOUNT_LINKS = {
    "CASHIER-WALKIN:": "cashier:",
    "PHARM-WALKIN:": "pharmacy:",
    "LAB-WALKIN:": "laboratory:",
    "RAD-WALKIN:": "radiology:",
}


def walkin_account_uuid(partner: dict[str, Any]) -> str:
    """A bill for someone who is not on the register can still be opened."""
    stored = str(partner.get("uuid") or "").strip()
    if stored:
        return stored
    ref = str(partner.get("ref") or "").strip()
    for prefix, link in WALKIN_ACCOUNT_LINKS.items():
        if ref.startswith(prefix):
            token = ref[len(prefix) :].strip()
            if token:
                return f"{link}{token}"
    return ""


def walkin_ref_for_account(account_uuid: str) -> str:
    text = str(account_uuid or "").strip()
    for prefix, link in WALKIN_ACCOUNT_LINKS.items():
        if text.startswith(link):
            token = text[len(link) :].strip()
            return f"{prefix}{token}" if token else ""
    return ""


def chart_number_from_ref(ref: str) -> str:
    """Hospital number shown to staff. Walk-in billing refs keep an internal prefix."""
    text = str(ref or "").strip()
    if text.startswith("CASHIER-WALKIN:"):
        return ""
    for prefix in WALKIN_REF_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def walkin_refs_for_chart_number(chart_number: str) -> list[str]:
    number = str(chart_number or "").strip()
    if not number:
        return []
    return [f"{prefix}{number}" for prefix in WALKIN_REF_PREFIXES]


def find_partner(odoo: OdooReader, patient: dict[str, str]) -> dict[str, Any] | None:
    """The billing record for this patient, including an external walk-in bill."""
    fields = ["id", "name", "ref", "uuid"]
    seen: set[int] = set()
    candidates: list[dict[str, Any]] = []

    def add(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            partner_id = int(row["id"])
            if partner_id in seen:
                continue
            seen.add(partner_id)
            candidates.append(row)

    patient_uuid = str(patient.get("uuid") or "").strip()
    if patient_uuid:
        add(
            odoo.search_read(
                "res.partner",
                [("uuid", "=", patient_uuid)],
                fields,
                limit=2,
            )
        )
        walkin_ref = walkin_ref_for_account(patient_uuid)
        if walkin_ref:
            add(
                odoo.search_read(
                    "res.partner",
                    [("ref", "=", walkin_ref)],
                    fields,
                    limit=2,
                )
            )
    chart_number = chart_number_from_ref(str(patient.get("mrn") or ""))
    refs = [chart_number, *walkin_refs_for_chart_number(chart_number)] if chart_number else []
    if refs:
        add(
            odoo.search_read(
                "res.partner",
                [("ref", "in", refs)],
                fields,
                limit=8,
            )
        )
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    billed = _partner_holding_bills(odoo, candidates)
    if billed:
        return billed
    matched = [row for row in candidates if str(row.get("uuid") or "") == patient_uuid]
    return matched[0] if matched else candidates[0]


def _partner_holding_bills(odoo: OdooReader, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """When a chart and a walk-in record both exist, use the one that has the bills."""
    ids = [int(row["id"]) for row in candidates]
    invoices = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "out_invoice"),
            ("state", "!=", "cancel"),
            ("partner_id", "in", ids),
        ],
        ["partner_id"],
        limit=80,
    )
    counts: dict[int, int] = {}
    for invoice in invoices:
        partner_id = many2one_id(invoice.get("partner_id"))
        if partner_id:
            counts[int(partner_id)] = counts.get(int(partner_id), 0) + 1
    ranked = sorted(candidates, key=lambda row: counts.get(int(row["id"]), 0), reverse=True)
    if counts.get(int(ranked[0]["id"]), 0) <= 0:
        return None
    return ranked[0]


def staff_currency(odoo: OdooReader, currency_id: int | None) -> dict[str, Any]:
    """Currency for staff money display. Hospital amounts never show as $."""
    loaded = load_currency(odoo, currency_id)
    if loaded.get("code") in {"USD", ""}:
        return load_currency(odoo, None)
    return loaded


def money_maps(odoo: OdooReader, currency_ids: set[int]) -> dict[int, dict[str, Any]]:
    hospital = load_currency(odoo, None)
    result: dict[int, dict[str, Any]] = {}
    for currency_id in currency_ids:
        if not currency_id:
            continue
        loaded = load_currency(odoo, int(currency_id))
        # Hospital EMR is a Naira hospital. Company-default USD on older bills/refunds
        # should not surface as $ in staff screens.
        if loaded.get("code") in {"USD", ""}:
            result[int(currency_id)] = hospital
        else:
            result[int(currency_id)] = loaded
    return result


def posted_invoice_for_order(
    invoice_lookup: dict[int, dict[str, Any]],
    invoices: list[dict[str, Any]],
    order: dict[str, Any],
) -> dict[str, Any] | None:
    """The bill still shown for this sale. A cancelled bill is left out."""
    for invoice_id in order.get("invoice_ids") or []:
        found = invoice_lookup.get(int(invoice_id))
        if found:
            return found
    origin = order.get("name")
    for invoice in invoices:
        if invoice.get("invoice_origin") != origin:
            continue
        found = invoice_lookup.get(int(invoice["id"]))
        if found:
            return found
    return None


def build_account(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_patient_account_view(cookie)
    patient = load_openmrs_patient(patient_uuid, cookie)
    try:
        odoo = OdooReader()
    except xmlrpc.client.Fault as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error
    except (ConnectionError, TimeoutError, OSError) as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error

    import consultation as clinical

    patient = {**patient, "nhis": clinical.patient_is_nhis(odoo, patient_uuid)}
    partner = find_partner(odoo, patient)
    if not partner:
        return {
            "status": "account_not_found",
            "readOnly": True,
            "patient": patient,
            "partnerFound": False,
            "message": "Financial account not found.",
        }

    partner_id = int(partner["id"])
    orders_preview = odoo.search_read(
        "sale.order",
        [("partner_id", "=", partner_id), ("state", "=", "draft")],
        ["id", "name", "state", "shop_id"],
    )
    try:
        import pharmacy as dispensary

        if dispensary.ensure_partner_pharmacy_invoices(odoo, orders_preview):
            pass
    except (ApiError, xmlrpc.client.Fault):
        pass
    invoices = odoo.search_read(
        "account.move",
        [("move_type", "=", "out_invoice"), ("partner_id", "=", partner_id)],
        [
            "name",
            "state",
            "payment_state",
            "amount_untaxed",
            "amount_tax",
            "amount_total",
            "amount_residual",
            "invoice_date",
            "invoice_origin",
            "currency_id",
            "invoice_line_ids",
        ],
    )
    orders = odoo.search_read(
        "sale.order",
        [("partner_id", "=", partner_id)],
        [
            "name",
            "state",
            "origin",
            "amount_total",
            "amount_untaxed",
            "amount_tax",
            "currency_id",
            "invoice_ids",
            "picking_ids",
            "shop_id",
            "order_line",
        ],
    )
    payments = odoo.search_read(
        "account.payment",
        [
            ("partner_id", "=", partner_id),
            ("partner_type", "=", "customer"),
            ("payment_type", "=", "inbound"),
        ],
        [
            "name",
            "amount",
            "date",
            "journal_id",
            "currency_id",
            "reconciled_invoice_ids",
            "payment_method_id",
            "state",
        ],
    )

    line_ids = [line_id for row in invoices for line_id in (row.get("invoice_line_ids") or [])]
    sale_line_ids = [line_id for row in orders for line_id in (row.get("order_line") or [])]
    picking_ids = [pick_id for row in orders for pick_id in (row.get("picking_ids") or [])]

    invoice_lines = odoo.read(
        "account.move.line",
        line_ids,
        [
            "name",
            "quantity",
            "price_unit",
            "discount",
            "price_subtotal",
            "price_total",
            "tax_ids",
            "product_id",
            "sale_line_ids",
            "move_id",
            "currency_id",
        ],
    )
    sale_lines = odoo.read(
        "sale.order.line",
        sale_line_ids,
        [
            "name",
            "product_id",
            "product_uom_qty",
            "price_unit",
            "order_id",
            "external_order_id",
            "external_id",
            "invoice_lines",
        ],
    )
    pickings = odoo.read(
        "stock.picking",
        picking_ids,
        ["name", "sale_id", "state", "origin"],
    )

    product_ids = {
        pid
        for row in invoice_lines + sale_lines
        if (pid := many2one_id(row.get("product_id")))
    }
    products = {
        int(row["id"]): row
        for row in odoo.read("product.product", list(product_ids), ["name", "categ_id"])
    }
    category_ids = {
        pid
        for row in products.values()
        if (pid := many2one_id(row.get("categ_id")))
    }
    categories = {
        int(row["id"]): row
        for row in odoo.read(
            "product.category",
            list(category_ids),
            ["name", "complete_name"],
        )
    }
    tax_ids = {
        tax_id
        for row in invoice_lines
        for tax_id in (row.get("tax_ids") or [])
    }
    taxes = {
        int(row["id"]): row
        for row in odoo.read("account.tax", list(tax_ids), ["name", "amount"])
    }

    currency_ids = {
        cid
        for row in invoices + orders + payments
        if (cid := many2one_id(row.get("currency_id")))
    }
    currencies = money_maps(odoo, currency_ids)
    default_currency = next(iter(currencies.values()), load_currency(odoo, None))

    sale_line_by_id = {int(row["id"]): row for row in sale_lines}
    order_by_id = {int(row["id"]): row for row in orders}
    pickings_by_sale: dict[int, list[dict[str, Any]]] = {}
    for picking in pickings:
        sale_id = many2one_id(picking.get("sale_id"))
        if sale_id:
            pickings_by_sale.setdefault(sale_id, []).append(picking)

    lines_by_invoice: dict[int, list[dict[str, Any]]] = {}
    for line in invoice_lines:
        move_id = many2one_id(line.get("move_id"))
        if move_id:
            lines_by_invoice.setdefault(move_id, []).append(line)

    def product_categories(product_id: int | None) -> list[str]:
        product = products.get(product_id or 0) or {}
        category = categories.get(many2one_id(product.get("categ_id")) or 0) or {}
        return [
            name
            for name in (category.get("complete_name"), category.get("name"))
            if name
        ]

    def order_department(order: dict[str, Any]) -> str | None:
        category_names: list[str] = []
        for line_id in order.get("order_line") or []:
            line = sale_line_by_id.get(int(line_id)) or {}
            category_names.extend(product_categories(many2one_id(line.get("product_id"))))
        return identify_department(many2one_name(order.get("shop_id")), category_names)

    def invoice_orders(invoice: dict[str, Any]) -> list[dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        for line in lines_by_invoice.get(int(invoice["id"]), []):
            for sale_line_id in line.get("sale_line_ids") or []:
                sale_line = sale_line_by_id.get(int(sale_line_id))
                if not sale_line:
                    continue
                order_id = many2one_id(sale_line.get("order_id"))
                if order_id and order_id in order_by_id:
                    found[order_id] = order_by_id[order_id]
        origin = invoice.get("invoice_origin") or ""
        for order in orders:
            if order.get("name") == origin or int(invoice["id"]) in (order.get("invoice_ids") or []):
                found[int(order["id"])] = order
        return list(found.values())

    def invoice_department(invoice: dict[str, Any]) -> str | None:
        names: list[str | None] = [order_department(order) for order in invoice_orders(invoice)]
        category_names: list[str] = []
        for line in lines_by_invoice.get(int(invoice["id"]), []):
            category_names.extend(product_categories(many2one_id(line.get("product_id"))))
        names.append(identify_department("", category_names))
        for name in names:
            if name:
                return name
        return None

    def invoice_description(invoice: dict[str, Any]) -> str:
        for line in lines_by_invoice.get(int(invoice["id"]), []):
            line_name = str(line.get("name") or "").strip()
            product_name = many2one_name(line.get("product_id"))
            if line_name:
                return line_name
            if product_name:
                return str(product_name)
        return invoice.get("invoice_origin") or invoice.get("name") or "Invoice"

    def serialize_invoice(invoice: dict[str, Any]) -> dict[str, Any]:
        currency = currencies.get(many2one_id(invoice.get("currency_id")) or 0, default_currency)
        total = as_float(invoice.get("amount_total"))
        residual = as_float(invoice.get("amount_residual"))
        payment_state = invoice.get("payment_state") or "not_paid"
        paid = 0.0 if payment_state == "reversed" else max(total - residual, 0.0)
        related_orders = invoice_orders(invoice)
        picking_states = [
            str(picking.get("state") or "")
            for order in related_orders
            for picking in pickings_by_sale.get(int(order["id"]), [])
        ]
        department = invoice_department(invoice)
        lines = []
        for line in lines_by_invoice.get(int(invoice["id"]), []):
            line_currency = currencies.get(
                many2one_id(line.get("currency_id")) or 0,
                currency,
            )
            tax_names = [
                taxes[int(tax_id)]["name"]
                for tax_id in (line.get("tax_ids") or [])
                if int(tax_id) in taxes and taxes[int(tax_id)].get("name")
            ]
            discount_percent = as_float(line.get("discount"))
            lines.append(
                {
                    "description": (line.get("name") or many2one_name(line.get("product_id")) or ""),
                    "quantity": as_float(line.get("quantity")),
                    "unitPrice": format_money(as_float(line.get("price_unit")), line_currency),
                    "discountPercent": discount_percent,
                    "subtotal": format_money(as_float(line.get("price_subtotal")), line_currency),
                    "total": format_money(as_float(line.get("price_total")), line_currency),
                    "taxNames": tax_names,
                }
            )
        payload = {
            "id": int(invoice["id"]),
            "number": invoice.get("name") or "",
            "date": invoice.get("invoice_date") or "",
            "department": department_label(department),
            "departmentIdentified": bool(department),
            "state": invoice.get("state") or "",
            "paymentState": payment_state,
            "paymentStateLabel": payment_state_label(payment_state),
            "origin": invoice.get("invoice_origin") or "",
            "description": invoice_description(invoice),
            "untaxed": format_money(as_float(invoice.get("amount_untaxed")), currency),
            "tax": format_money(as_float(invoice.get("amount_tax")), currency),
            "hasTax": as_float(invoice.get("amount_tax")) != 0,
            "total": format_money(total, currency),
            "paid": format_money(paid, currency),
            "outstanding": format_money(residual, currency),
            "lines": lines,
            "pharmacyStatus": None,
        }
        if department == "Pharmacy":
            payload["pharmacyStatus"] = pharmacy_dispensing_status(payment_state, picking_states)
        return payload

    serialized_invoices = []
    for invoice in invoices:
        if invoice.get("state") == "cancel":
            continue
        try:
            serialized_invoices.append(serialize_invoice(invoice))
        except Exception:
            traceback.print_exc()
    import accountant as cashier

    cashier.mark_waived_invoices(odoo, serialized_invoices, bool(patient.get("nhis")))
    cashier.annotate_created_bills(serialized_invoices)
    invoice_lookup = {row["id"]: row for row in serialized_invoices}

    activity: list[dict[str, Any]] = []
    for invoice in serialized_invoices:
        activity.append(
            {
                "kind": "invoice",
                "department": invoice["department"],
                "departmentIdentified": invoice["departmentIdentified"],
                "description": invoice["description"],
                "invoiceNumber": invoice["number"],
                "invoiceId": invoice["id"],
                "statusLabel": invoice["paymentStateLabel"],
                "amount": invoice["total"],
                "outstanding": invoice["outstanding"],
                "pharmacyStatus": invoice["pharmacyStatus"],
            }
        )

    invoiced_order_ids: set[int] = set()
    for order in orders:
        for invoice_id in order.get("invoice_ids") or []:
            invoiced_order_ids.add(int(order["id"]))
        origin_match = any(
            invoice.get("invoice_origin") == order.get("name") for invoice in invoices
        )
        if origin_match:
            invoiced_order_ids.add(int(order["id"]))

    for order in orders:
        if int(order["id"]) in invoiced_order_ids:
            continue
        currency = currencies.get(many2one_id(order.get("currency_id")) or 0, default_currency)
        department = order_department(order)
        first_line = next(
            (
                sale_line_by_id[int(line_id)]
                for line_id in (order.get("order_line") or [])
                if int(line_id) in sale_line_by_id
            ),
            None,
        )
        description = ""
        if first_line:
            description = many2one_name(first_line.get("product_id")) or first_line.get("name") or ""
        activity.append(
            {
                "kind": "unbilled_order",
                "department": department_label(department),
                "departmentIdentified": bool(department),
                "description": description or order.get("name") or "Sale order",
                "invoiceNumber": None,
                "invoiceId": None,
                "statusLabel": "UNBILLED",
                "amount": format_money(as_float(order.get("amount_total")), currency),
                "outstanding": format_money(as_float(order.get("amount_total")), currency),
                "pharmacyStatus": "UNPAID" if department == "Pharmacy" else None,
                "orderName": order.get("name") or "",
            }
        )

    pharmacy_rows: list[dict[str, Any]] = []
    for order in orders:
        department = order_department(order)
        if department != "Pharmacy":
            continue
        try:
            related_invoice = posted_invoice_for_order(invoice_lookup, invoices, order)
            picking_rows = pickings_by_sale.get(int(order["id"]), [])
            payment_state = related_invoice["paymentState"] if related_invoice else None
            first_line = next(
                (
                    sale_line_by_id[int(line_id)]
                    for line_id in (order.get("order_line") or [])
                    if int(line_id) in sale_line_by_id
                ),
                None,
            )
            description = ""
            if first_line:
                description = many2one_name(first_line.get("product_id")) or ""
            pharmacy_rows.append(
                {
                    "orderName": order.get("name") or "",
                    "description": description or order.get("name") or "",
                    "invoiceNumber": related_invoice["number"] if related_invoice else None,
                    "invoiceId": related_invoice["id"] if related_invoice else None,
                    "paymentStateLabel": related_invoice["paymentStateLabel"] if related_invoice else "UNPAID",
                    "dispensingStatus": pharmacy_dispensing_status(
                        payment_state,
                        [str(row.get("state") or "") for row in picking_rows],
                    ),
                    "pickingName": picking_rows[0]["name"] if picking_rows else None,
                    "pickingState": picking_rows[0]["state"] if picking_rows else None,
                }
            )
        except Exception:
            traceback.print_exc()

    serialized_payments = []
    allocation_confirmed = True
    import cashier_records as ledger

    collectors = ledger.collectors_for([int(payment["id"]) for payment in payments if payment.get("id")])
    for payment in payments:
        currency = currencies.get(many2one_id(payment.get("currency_id")) or 0, default_currency)
        related_ids = payment.get("reconciled_invoice_ids") or []
        related = [
            {
                "id": invoice_id,
                "number": invoice_lookup.get(int(invoice_id), {}).get("number")
                or next(
                    (
                        invoice.get("name")
                        for invoice in invoices
                        if int(invoice["id"]) == int(invoice_id)
                    ),
                    None,
                ),
            }
            for invoice_id in related_ids
        ]
        serialized_payments.append(
            {
                "id": int(payment["id"]),
                "reference": payment.get("name") or "",
                "date": payment.get("date") or "",
                "amount": format_money(as_float(payment.get("amount")), currency),
                "journal": many2one_name(payment.get("journal_id")),
                "method": many2one_name(payment.get("payment_method_id")),
                "state": payment.get("state") or "",
                "relatedInvoices": related,
                "allocationConfirmed": bool(related_ids),
                "recordedBy": collectors.get(int(payment["id"]), ""),
            }
        )
        if payment.get("state") == "posted" and not related_ids:
            allocation_confirmed = False

    posted = [row for row in serialized_invoices if row["state"] == "posted"]
    posted_active = [row for row in posted if row.get("paymentState") != "reversed"]
    outstanding_by_currency = aggregate_by_currency(
        [
            row["outstanding"]
            for row in posted
            if as_float(row["outstanding"]["amount"]) > 0.009
        ]
    )
    billed_by_currency = aggregate_by_currency([row["total"] for row in posted_active])
    paid_by_currency = aggregate_by_currency([row["paid"] for row in posted_active])

    departments = sorted(
        {
            row["department"]
            for row in activity
            if row.get("departmentIdentified")
        }
    )
    has_activity = bool(activity)
    return {
        "status": "ok" if has_activity else "no_activity",
        "readOnly": True,
        "patient": patient,
        "partnerFound": True,
        "message": None if has_activity else "No financial activity recorded.",
        "currency": default_currency,
        "summary": {
            "outstandingByCurrency": outstanding_by_currency,
            "paidByCurrency": paid_by_currency,
            "billedByCurrency": billed_by_currency,
        },
        "departments": departments,
        "activity": activity,
        "invoices": serialized_invoices,
        "payments": serialized_payments,
        "pharmacy": pharmacy_rows,
        "limitations": {
            "paymentAllocation": "confirmed" if allocation_confirmed else "unavailable",
            "partialPaymentExample": any(
                invoice.get("paymentState") == "partial" for invoice in serialized_invoices
            ),
        },
    }


def build_invoice(patient_uuid: str, invoice_id: int, cookie: str) -> dict[str, Any]:
    account = build_account(patient_uuid, cookie)
    if account.get("status") == "account_not_found":
        return account
    invoice = next(
        (row for row in account.get("invoices") or [] if int(row["id"]) == invoice_id),
        None,
    )
    if not invoice:
        raise ApiError(404, "invoice_not_found", "Bill not found for this patient.")
    return {
        "status": "ok",
        "readOnly": True,
        "patient": account["patient"],
        "invoice": invoice,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "Hospital EMRPatientAccount/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cookie(self) -> str:
        return self.headers.get("Cookie") or ""

    def _terminal_throttle_key(self) -> str:
        forwarded = str(self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
        if self.client_address:
            return str(self.client_address[0])
        return "unknown"

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(self.path.split("?", 1)[0])
        for prefix in ("/openmrs/abikan-api", "/abikan/api"):
            if path.startswith(prefix):
                path = path[len(prefix) :] or "/"
                break
        try:
            parts = [part for part in path.split("/") if part]
            if path in {"/", "/health"}:
                self._send(200, {"status": "ok", "readOnly": False})
                return
            if parts == ["attendance", "terminal"]:
                import attendance as staff_log

                self._send(200, staff_log.terminal_config())
                return
            require_session(self._cookie())
            if parts == ["session", "photo"]:
                import staff_hr as directory

                data, content_type, filename = directory.download_own_photo(self._cookie())
                self._send_file(data, content_type, filename)
                return
            if (
                len(parts) == 2
                and parts[0] == "patient-account"
            ):
                self._send(200, build_account(parts[1], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "patient-account"
                and parts[2] == "invoice"
            ):
                self._send(200, build_invoice(parts[1], int(parts[3]), self._cookie()))
                return
            import accountant as cashier
            if parts == ["accountant", "dashboard"]:
                self._send(200, cashier.build_dashboard(self._cookie()))
                return
            if parts == ["accountant", "journals"]:
                cashier.require_accountant(self._cookie())
                odoo = cashier.odoo_reader()
                self._send(200, {"status": "ok", "journals": cashier.authorized_journals(odoo)})
                return
            if parts == ["accountant", "outstanding"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, cashier.list_outstanding_page(self._cookie(), query))
                return
            if parts == ["accountant", "payments"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, cashier.list_payments_page(self._cookie(), query))
                return
            if parts == ["accountant", "refunds"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, cashier.list_refunds_page(self._cookie(), query))
                return
            if parts == ["accountant", "deleted-bills"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, cashier.list_deleted_bills(self._cookie(), query))
                return
            if parts == ["accountant", "waived-bills"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, cashier.list_waived_bills(self._cookie(), query))
                return
            if (
                len(parts) == 3
                and parts[0] == "accountant"
                and parts[1] == "payment"
            ):
                self._send(200, cashier.get_payment(int(parts[2]), self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "accountant"
                and parts[1] == "payment"
                and parts[3] == "receipt"
            ):
                pdf, reference = cashier.render_receipt_pdf(int(parts[2]), self._cookie())
                self._send_pdf(pdf, reference)
                return
            import pharmacy as dispensary
            if parts == ["pharmacy", "catalogue", "forms"]:
                import pharmacy_manage as catalogue_manage
                dispensary.require_pharmacist(self._cookie())
                self._send(200, catalogue_manage.list_forms())
                return
            if parts == ["pharmacy", "catalogue", "generics"]:
                import pharmacy_manage as catalogue_manage

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, catalogue_manage.search_generics(self._cookie(), q))
                return
            if parts == ["pharmacy", "catalogue"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                dispensary.require_catalogue_reader(self._cookie())
                self._send(200, dispensary.build_catalogue(self._cookie(), q, enforce_pharmacist=False))
                return
            import pharmacy_inventory as stockroom
            if parts == ["pharmacy", "inventory"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, stockroom.list_inventory(self._cookie(), q))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "inventory"
                and parts[3] == "history"
            ):
                self._send(200, stockroom.list_history(parts[2], self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "pharmacy" and parts[1] == "inventory":
                self._send(200, stockroom.get_inventory_item(parts[2], self._cookie()))
                return
            if parts == ["pharmacy", "queue"]:
                self._send(200, dispensary.build_queue(self._cookie()))
                return
            if parts == ["pharmacy", "sales-history"]:
                import pharmacy_history as history

                self._send(200, history.list_sales_history(self._cookie(), self.path))
                return
            if len(parts) == 3 and parts[0] == "pharmacy" and parts[1] == "sales-history":
                import pharmacy_history as history

                try:
                    sale_id = int(parts[2])
                except ValueError:
                    self._send(
                        404,
                        {
                            "status": "error",
                            "code": "sale_not_found",
                            "message": "This pharmacy sale was not found.",
                        },
                    )
                    return
                self._send(200, history.get_sales_history_item(sale_id, self._cookie()))
                return
            if parts == ["pharmacy", "sales"]:
                import pharmacy_sale as counter

                self._send(200, counter.list_sales(self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "pharmacy" and parts[1] == "sales":
                import pharmacy_sale as counter

                try:
                    sale_id = int(parts[2])
                except ValueError:
                    self._send(404, {"status": "error", "code": "sale_not_found", "message": "This pharmacy sale was not found."})
                    return
                self._send(200, counter.assemble_sale(sale_id, self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "pharmacy" and parts[1] == "patient":
                self._send(200, dispensary.build_queue(self._cookie(), parts[2]))
                return
            if len(parts) == 3 and parts[0] == "pharmacy" and parts[1] == "prescription":
                self._send(200, dispensary.build_prescription(parts[2], self._cookie()))
                return
            import registration as reception
            if parts == ["patients"]:
                import patient_directory as register

                self._send(200, register.build_directory(self._cookie(), self.path))
                return
            if parts == ["hmo", "metadata"]:
                import hmo

                self._send(200, hmo.metadata(self._cookie()))
                return
            if parts == ["hmo", "patients"]:
                import hmo

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, hmo.list_assignments(self._cookie(), (query.get("q") or [""])[0]))
                return
            if len(parts) == 3 and parts[0] == "certificates" and parts[1] == "patient":
                import certificates

                self._send(200, certificates.load(self._cookie(), parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["certificates", "patient"] and parts[4] == "pdf":
                import certificates

                pdf, filename = certificates.pdf_bytes(self._cookie(), parts[2], parts[3])
                self._send_file(pdf, "application/pdf", filename)
                return
            if parts == ["hmo", "bills"]:
                import hmo_bills

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(
                    200,
                    hmo_bills.bills(
                        self._cookie(),
                        (query.get("body") or [""])[0],
                        (query.get("scheme") or [""])[0],
                        (query.get("from") or [""])[0],
                        (query.get("to") or [""])[0],
                    ),
                )
                return
            if len(parts) == 2 and parts[0] == "patients":
                import patient_directory as register

                self._send(200, register.load_patient_record(parts[1], self._cookie()))
                return
            if parts == ["registration", "metadata"]:
                import registration_patient as arrival
                self._send(200, arrival.build_registration_metadata(self._cookie()))
                return
            if parts == ["registration", "families"]:
                import hospital_family as household

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, household.list_families_response(self._cookie(), (query.get("q") or [""])[0]))
                return
            if len(parts) == 3 and parts[0] == "registration" and parts[1] == "families":
                import hospital_family as household

                self._send(200, household.get_family_response(parts[2], self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "registration" and parts[1] == "patient" and parts[3] == "family":
                import hospital_family as household

                self._send(200, household.get_patient_family_response(parts[2], self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "registration" and parts[1] == "patient" and parts[3] == "profile":
                import registration_patient as arrival
                self._send(200, arrival.load_patient_profile(parts[2], self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "registration" and parts[1] == "patient" and parts[3] == "visit":
                import registration_patient as arrival
                self._send(200, arrival.build_visit_context(parts[2], self._cookie()))
                return
            if parts == ["antenatal", "cards"]:
                import antenatal as anc

                self._send(200, anc.list_anc_cards(self._cookie(), self.path))
                return
            if len(parts) == 3 and parts[0] == "antenatal" and parts[1] == "patient":
                import antenatal as anc

                self._send(200, anc.get_patient_anc_summary(parts[2], self._cookie()))
                return
            if (
                len(parts) == 5
                and parts[0] == "antenatal"
                and parts[1] == "patient"
                and parts[3] == "pregnancy"
            ):
                import antenatal as anc

                self._send(200, anc.get_pregnancy(parts[2], parts[4], self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "antenatal" and parts[1] == "patient" and parts[3] == "charge":
                import antenatal as anc

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                pregnancy_id = (query.get("pregnancyId") or [""])[0].strip()
                self._send(200, anc.get_anc_registration_charge(parts[2], pregnancy_id, self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "registration" and parts[1] == "patient":
                self._send(200, reception.build_registration(parts[2], self._cookie()))
                return
            import consultation as clinical
            if parts == ["consultation", "todays-patients"]:
                import clinical_queue as todays
                self._send(200, todays.build_todays_patients(self._cookie()))
                return
            if parts == ["consultation", "my-patients"]:
                import clinical_my_patients as mine
                self._send(200, mine.build_my_patients(self._cookie()))
                return
            if parts == ["reception", "registrations"]:
                self._send(200, reception.list_new_registrations(self._cookie(), self.path))
                return
            if parts == ["reception", "patient-calls"]:
                import patient_call as paging

                self._send(200, paging.list_pending_calls(self._cookie(), self.path))
                return
            if parts == ["notifications"]:
                import notifications as staff_notes

                self._send(200, staff_notes.list_for_session(self._cookie(), self.path))
                return
            import messaging
            if parts == ["messages", "workplaces"]:
                self._send(200, messaging.list_workplaces(self._cookie()))
                return
            if parts == ["messages", "staff"]:
                self._send(200, messaging.list_staff(self._cookie(), self.path))
                return
            if parts == ["messages", "conversations"]:
                self._send(200, messaging.list_conversations(self._cookie(), self.path))
                return
            if len(parts) == 3 and parts[0] == "messages" and parts[1] == "conversations":
                self._send(200, messaging.get_conversation(parts[2], self._cookie(), self.path))
                return
            if len(parts) == 3 and parts[0] == "consultation" and parts[1] == "patient":
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                visit_uuid = (query.get("visitUuid") or [""])[0].strip() or None
                self._send(200, clinical.build_consultation(parts[2], self._cookie(), visit_uuid))
                return
            if len(parts) == 3 and parts[0] == "patient" and parts[2] == "allergies":
                import allergies as hypersensitivity

                self._send(200, hypersensitivity.list_allergies(parts[1], self._cookie()))
                return
            import department_pricing as pricing
            if len(parts) == 2 and parts[0] == "pricing":
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, pricing.list_department_prices(parts[1], self._cookie(), q))
                return
            if len(parts) == 4 and parts[0] == "pricing" and parts[3] == "history":
                self._send(200, pricing.list_item_history(parts[1], parts[2], self._cookie()))
                return
            import laboratory as lab_billing
            if parts == ["laboratory", "catalogue"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, lab_billing.build_catalogue(self._cookie(), q))
                return
            if parts == ["laboratory", "reference-ranges"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(
                    200,
                    lab_billing.list_reference_ranges(
                        self._cookie(),
                        (query.get("q") or [""])[0],
                        (query.get("status") or [""])[0],
                    ),
                )
                return
            if parts == ["laboratory", "hospital-tests"]:
                import laboratory_manage as lab_manage

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, lab_manage.list_hospital_tests(self._cookie(), q))
                return
            if parts == ["laboratory", "master-tests"]:
                import laboratory_manage as lab_manage

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, lab_manage.search_master_tests(self._cookie(), q))
                return
            if parts == ["laboratory", "custom-tests"]:
                import laboratory_custom as lab_custom

                self._send(200, lab_custom.list_custom_tests(self._cookie()))
                return
            if parts == ["laboratory", "inventory"]:
                import laboratory_inventory as lab_stock

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, lab_stock.list_consumables(self._cookie(), q))
                return
            if parts == ["laboratory", "blood-units"]:
                import laboratory_inventory as lab_stock

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                status = (query.get("status") or [""])[0]
                self._send(200, lab_stock.list_blood_units(self._cookie(), q, status))
                return
            if parts == ["laboratory", "board"]:
                self._send(200, lab_billing.build_board(self._cookie()))
                return
            if parts == ["laboratory", "test-frequency"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, lab_billing.top_ordered_tests(self._cookie(), query))
                return
            if parts == ["laboratory", "history"]:
                self._send(200, lab_billing.build_laboratory_history(self._cookie(), self.path))
                return
            if parts == ["laboratory", "deleted-orders"]:
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                self._send(200, lab_billing.list_deleted_lab_orders(self._cookie(), query))
                return
            if parts == ["laboratory", "external-patients"]:
                import laboratory_external as lab_external

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                q = (query.get("q") or [""])[0]
                self._send(200, lab_external.search_external_patients(self._cookie(), q))
                return
            if (
                len(parts) == 3
                and parts[0] == "laboratory"
                and parts[1] == "external-patient"
            ):
                import laboratory_external as lab_external

                self._send(200, lab_external.get_external_patient(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "patient"
                and parts[3] == "linked-external"
            ):
                import laboratory_external as lab_external

                self._send(200, lab_external.linked_external_for_registered(parts[2], self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "laboratory" and parts[1] == "order":
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                patient_uuid = (query.get("patient") or query.get("patientUuid") or [""])[0].strip() or None
                visit_uuid = (query.get("visit") or query.get("visitUuid") or [""])[0].strip() or None
                self._send(200, lab_billing.build_lab_order(parts[2], patient_uuid, visit_uuid, self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "laboratory" and parts[1] == "order" and parts[3] == "result.pdf":
                import lab_result_report

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                patient_uuid = (query.get("patient") or query.get("patientUuid") or [""])[0].strip() or None
                visit_uuid = (query.get("visit") or query.get("visitUuid") or [""])[0].strip() or None
                pdf, filename = lab_result_report.result_pdf(parts[2], patient_uuid, visit_uuid, self._cookie())
                self._send_file(pdf, "application/pdf", filename)
                return
            if len(parts) == 4 and parts[0] == "laboratory" and parts[1] == "order" and parts[3] == "workflow":
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                patient_uuid = (query.get("patient") or query.get("patientUuid") or [""])[0].strip() or None
                visit_uuid = (query.get("visit") or query.get("visitUuid") or [""])[0].strip() or None
                self._send(
                    200,
                    lab_billing.build_lab_workflow(parts[2], patient_uuid, visit_uuid, self._cookie()),
                )
                return
            if len(parts) == 3 and parts[0] == "laboratory" and parts[1] == "patient":
                self._send(200, lab_billing.build_laboratory(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "patient"
                and parts[3] == "chart"
            ):
                self._send(200, lab_billing.build_patient_chart(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "patient"
                and parts[3] == "released-results"
            ):
                self._send(200, lab_billing.build_released_lab_results(parts[2], self._cookie()))
                return
            import radiology as imaging
            if parts == ["radiology", "worklist"]:
                self._send(200, imaging.build_worklist(self._cookie()))
                return
            if parts == ["radiology", "history"]:
                self._send(200, imaging.build_radiology_history(self._cookie(), self.path))
                return
            if (
                len(parts) == 3
                and parts[0] == "radiology"
                and parts[1] == "external-study"
            ):
                import radiology_external as external

                self._send(200, external.get_external_study(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "radiology"
                and parts[1] == "patient"
                and parts[3] == "linked-external"
            ):
                import radiology_external as external

                self._send(
                    200,
                    {
                        "status": "ok",
                        "items": external.studies_for_registered_patient(parts[2], self._cookie()),
                    },
                )
                return
            if len(parts) == 3 and parts[0] == "radiology" and parts[1] == "patient":
                self._send(200, imaging.build_radiology(parts[2], self._cookie()))
                return
            import inpatient as ward
            if (
                len(parts) == 6
                and parts[0] == "nursing"
                and parts[1] == "patient"
                and parts[3] == "treatment"
                and parts[5] == "notes"
            ):
                import nursing_treatment as treatments

                self._send(
                    200,
                    treatments.build_treatment_notes(
                        parts[2],
                        parts[4],
                        self._cookie(),
                    ),
                )
                return
            if parts == ["nursing", "treatments"]:
                import nursing_treatment as treatments

                self._send(200, treatments.build_treatment_queue(self._cookie()))
                return
            if parts == ["nursing", "todays-patients"]:
                import clinical_queue as todays

                self._send(200, todays.build_nursing_todays_patients(self._cookie()))
                return
            if parts == ["inpatient", "board"]:
                self._send(200, ward.build_board(self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "nursing-notes"
            ):
                self._send(200, ward.build_nursing_notes(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "medication-administration"
            ):
                import medication_administration as mar

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                visit_uuid = (query.get("visitUuid") or [""])[0].strip() or None
                admission_uuid = (
                    query.get("admissionEncounterUuid") or [""]
                )[0].strip() or None
                self._send(
                    200,
                    mar.build_mar(
                        parts[2],
                        self._cookie(),
                        visit_uuid=visit_uuid,
                        admission_encounter_uuid=admission_uuid,
                    ),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "vitals"
            ):
                import inpatient_vitals as vitals

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                visit_uuid = (query.get("visitUuid") or [""])[0].strip() or None
                admission_uuid = (
                    query.get("admissionEncounterUuid") or [""]
                )[0].strip() or None
                self._send(
                    200,
                    vitals.build_vitals(
                        parts[2],
                        self._cookie(),
                        visit_uuid=visit_uuid,
                        admission_encounter_uuid=admission_uuid,
                    ),
                )
                return
            if len(parts) == 3 and parts[0] == "inpatient" and parts[1] == "patient":
                self._send(200, ward.build_patient_stay(parts[2], self._cookie()))
                return
            import accommodation as lodging
            if parts == ["inpatient", "accommodation", "tariffs"]:
                self._send(200, lodging.list_tariffs(self._cookie()))
                return
            import hospital_admin as administration
            if parts == ["admin", "staff"]:
                self._send(200, administration.list_staff(self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "admin" and parts[1] == "staff":
                import staff_hr as directory

                self._send(200, directory.get_staff(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] in {"photo", "appointment-letter"}
            ):
                import staff_hr as directory

                data, content_type, filename = directory.download_staff_file(
                    parts[2],
                    "photo" if parts[3] == "photo" else "letter",
                    self._cookie(),
                )
                self._send_file(data, content_type, filename)
                return
            if parts == ["admin", "access"]:
                self._send(200, administration.list_access(self._cookie()))
                return
            import admin_analytics as analytics
            if parts == ["department", "revenue"]:
                import department_revenue as departmental

                self._send(200, departmental.build_department_revenue(self._cookie(), self.path))
                return
            if parts == ["admin", "analytics", "overview"]:
                self._send(
                    200,
                    analytics.build_overview(
                        self._cookie(), analytics.parse_request_query(self.path)
                    ),
                )
                return
            if parts == ["admin", "analytics", "reception"]:
                self._send(
                    200,
                    analytics.build_reception(
                        self._cookie(), analytics.parse_request_query(self.path)
                    ),
                )
                return
            if parts == ["admin", "analytics", "inpatient"]:
                self._send(
                    200,
                    analytics.build_inpatient(
                        self._cookie(), analytics.parse_request_query(self.path)
                    ),
                )
                return
            if parts == ["admin", "audit"]:
                query = analytics.parse_request_query(self.path)
                self._send(200, administration.build_staff_audit(self._cookie(), query))
                return
            import attendance as staff_log
            if parts == ["admin", "log"]:
                self._send(200, staff_log.list_sessions(self._cookie(), self.path))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "log"
                and parts[3] == "photo"
            ):
                data, content_type, filename = staff_log.session_photo(parts[2], self._cookie())
                self._send_file(data, content_type, filename)
                return
            if parts == ["admin", "log", "summary"]:
                self._send(200, staff_log.daily_summaries(self._cookie(), self.path))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] == "attendance-code"
            ):
                self._send(200, staff_log.staff_attendance_code(parts[2], self._cookie()))
                return
            import admin_export as exports
            if parts == ["admin", "export"]:
                self._send(200, exports.catalog(self._cookie()))
                return
            if parts == ["admin", "export", "history"]:
                self._send(200, exports.list_history(self._cookie(), self.path))
                return
            if len(parts) == 3 and parts[0] == "admin" and parts[1] == "export":
                self._send(200, exports.get_history_item(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "export"
                and parts[3] == "file"
            ):
                data, content_type, filename = exports.download_export(parts[2], self._cookie())
                self._send_file(data, content_type, filename)
                return
            raise ApiError(404, "not_found", "Not found.")
        except ApiError as error:
            self._send(error.status, {"status": "error", "code": error.code, "message": error.message})
        except ValueError:
            self._send(404, {"status": "error", "code": "not_found", "message": "Not found."})
        except Exception:
            traceback.print_exc()
            self._send(
                500,
                {
                    "status": "error",
                    "code": "server_error",
                    "message": "Unable to load the financial workspace.",
                },
            )

    def _send_pdf(self, pdf: bytes, reference: str) -> None:
        filename = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reference)
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'inline; filename="Hospital EMR-receipt-{filename}.pdf"')
        self.send_header("Content-Length", str(len(pdf)))
        self.end_headers()
        self.wfile.write(pdf)

    def _send_file(self, data: bytes, content_type: str, filename: str) -> None:
        safe = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in filename) or "staff-file"
        inline = content_type.startswith("image/")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        disposition = "inline" if inline else "attachment"
        self.send_header("Content-Disposition", f'{disposition}; filename="{safe}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(self.path.split("?", 1)[0])
        for prefix in ("/openmrs/abikan-api", "/abikan/api"):
            if path.startswith(prefix):
                path = path[len(prefix) :] or "/"
                break
        parts = [part for part in path.split("/") if part]
        try:
            if parts in (
                ["attendance", "status"],
                ["attendance", "sign-in"],
                ["attendance", "sign-out"],
            ):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    raise ApiError(422, "invalid_body", "This request is invalid.")
                import attendance as staff_log

                throttle_key = self._terminal_throttle_key()
                if parts == ["attendance", "status"]:
                    self._send(200, staff_log.lookup_status(body, self.headers, self._cookie(), throttle_key))
                    return
                if parts == ["attendance", "sign-in"]:
                    self._send(200, staff_log.sign_in(body, self.headers, self._cookie(), throttle_key))
                    return
                self._send(200, staff_log.sign_out(body, self.headers, self._cookie(), throttle_key))
                return
            require_session(self._cookie())
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ApiError(422, "invalid_body", "This request is invalid.")
            if parts == ["hmo", "patients"]:
                import hmo

                self._send(200, hmo.assign_patient(body, self._cookie()))
                return
            if parts == ["certificates"]:
                import certificates

                self._send(200, certificates.save(self._cookie(), body))
                return
            if parts == ["hmo", "bills", "send"]:
                import hmo_bills

                self._send(200, hmo_bills.send_statement(body, self._cookie()))
                return
            if parts == ["accountant", "payment"]:
                import accountant as cashier
                self._send(200, cashier.register_payment(body, self._cookie()))
                return
            if parts == ["accountant", "waive"]:
                import accountant as cashier
                self._send(200, cashier.waive_bills(body, self._cookie()))
                return
            if parts == ["accountant", "delete-bill"]:
                import accountant as cashier
                self._send(200, cashier.delete_unpaid_bill(body, self._cookie()))
                return
            if parts == ["accountant", "create-bill"]:
                import accountant as cashier
                self._send(200, cashier.create_cashier_bill(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "accountant"
                and parts[1] == "payment"
                and parts[3] == "refund"
            ):
                import accountant_refund as refunds

                self._send(200, refunds.refund_payment(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 3
                and parts[0] == "pricing"
            ):
                import department_pricing as pricing
                self._send(200, pricing.update_department_price(parts[1], parts[2], body, self._cookie()))
                return
            if parts == ["pharmacy", "catalogue"]:
                import pharmacy_manage as catalogue_manage
                self._send(200, catalogue_manage.create_medicine(body, self._cookie()))
                return
            if parts == ["pharmacy", "catalogue", "batch"]:
                import pharmacy_manage as catalogue_manage

                self._send(200, catalogue_manage.create_medicines_batch(body, self._cookie()))
                return
            if parts == ["laboratory", "catalogue"]:
                import laboratory_manage as lab_manage

                self._send(200, lab_manage.create_laboratory_test(body, self._cookie()))
                return
            if parts == ["laboratory", "reference-ranges"]:
                import laboratory as lab_ranges

                self._send(200, lab_ranges.save_reference_range(body, self._cookie()))
                return
            if parts == ["laboratory", "hospital-tests"]:
                import laboratory_manage as lab_manage

                self._send(200, lab_manage.enable_hospital_test(body, self._cookie()))
                return
            if parts == ["laboratory", "custom-tests"]:
                import laboratory_custom as lab_custom

                self._send(200, lab_custom.create_custom_test(body, self._cookie()))
                return
            if parts == ["laboratory", "inventory"]:
                import laboratory_inventory as lab_stock

                self._send(200, lab_stock.create_consumable(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "inventory"
                and parts[3] == "adjust"
            ):
                import laboratory_inventory as lab_stock

                self._send(200, lab_stock.adjust_consumable(parts[2], body, self._cookie()))
                return
            if parts == ["laboratory", "blood-units"]:
                import laboratory_inventory as lab_stock

                self._send(200, lab_stock.receive_blood_unit(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "blood-units"
                and parts[3] == "status"
            ):
                import laboratory_inventory as lab_stock

                self._send(200, lab_stock.update_blood_unit_status(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "hospital-tests"
                and parts[3] == "disable"
            ):
                import laboratory_manage as lab_manage

                self._send(200, lab_manage.disable_hospital_test(parts[2], self._cookie()))
                return
            if parts == ["pharmacy", "catalogue", "generics"]:
                import pharmacy_manage as catalogue_manage

                self._send(200, catalogue_manage.create_generic(body, self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "pharmacy" and parts[1] == "catalogue":
                import pharmacy_manage as catalogue_manage
                self._send(200, catalogue_manage.update_medicine(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "inventory"
                and parts[3] == "receive"
            ):
                import pharmacy_inventory as stockroom
                self._send(200, stockroom.receive_stock(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "inventory"
                and parts[3] == "adjust"
            ):
                import pharmacy_inventory as stockroom
                self._send(200, stockroom.adjust_stock(parts[2], body, self._cookie()))
                return
            if parts == ["pharmacy", "inventory", "receive"]:
                import pharmacy_inventory as stockroom

                self._send(200, stockroom.receive_stock_batch(body, self._cookie()))
                return
            if parts == ["pharmacy", "inventory", "adjust"]:
                import pharmacy_inventory as stockroom

                self._send(200, stockroom.adjust_stock_batch(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "prescription"
                and parts[3] == "charge"
            ):
                import pharmacy as dispensary
                request_id = str(body.get("requestId") or "").strip() or None
                self._send(200, dispensary.create_pharmacy_charge(parts[2], self._cookie(), request_id))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "prescription"
                and parts[3] == "dispense"
            ):
                import pharmacy as dispensary
                request_id = str(body.get("requestId") or "").strip() or None
                self._send(200, dispensary.dispense_prescription(parts[2], self._cookie(), request_id))
                return
            if parts == ["pharmacy", "prescriptions", "dispense"]:
                import pharmacy as dispensary

                request_id = str(body.get("requestId") or "").strip() or None
                order_uuids = body.get("orderUuids") or body.get("orders") or []
                if isinstance(order_uuids, str):
                    order_uuids = [order_uuids]
                self._send(
                    200,
                    dispensary.dispense_prescriptions(
                        list(order_uuids) if isinstance(order_uuids, list) else [],
                        self._cookie(),
                        request_id,
                    ),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "prescription"
                and parts[3] == "cancel"
            ):
                import pharmacy_prescription_ops as rx_ops

                self._send(200, rx_ops.cancel_prescription(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "prescription"
                and parts[3] == "bill"
            ):
                import pharmacy as dispensary

                self._send(200, dispensary.bill_prescription(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "prescription"
                and parts[3] == "medicines"
            ):
                import pharmacy_rx_edit as rx_edit

                self._send(200, rx_edit.add_medicine(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "prescription"
                and parts[3] == "revise"
            ):
                import pharmacy_rx_edit as rx_edit

                self._send(200, rx_edit.change_medicine(parts[2], body, self._cookie()))
                return
            if parts == ["pharmacy", "prescriptions", "cancel"]:
                import pharmacy_prescription_ops as rx_ops

                self._send(200, rx_ops.cancel_prescriptions(body, self._cookie()))
                return
            if parts == ["pharmacy", "prescriptions", "announce"]:
                import pharmacy_prescription_ops as rx_ops

                self._send(200, rx_ops.announce_prescriptions(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "sales-history"
                and parts[3] == "refund"
            ):
                import pharmacy_refund as refunds

                self._send(200, refunds.refund_sale(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "sales-history"
                and parts[3] == "cancel-prescription"
            ):
                import pharmacy_prescription_ops as rx_ops

                self._send(200, rx_ops.cancel_sale_prescription(parts[2], self._cookie()))
                return
            if parts == ["pharmacy", "sales"]:
                import pharmacy_sale as counter

                self._send(200, counter.create_direct_sale(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "pharmacy"
                and parts[1] == "sales"
                and parts[3] == "dispense"
            ):
                import pharmacy_sale as counter

                request_id = str(body.get("requestId") or "").strip() or None
                self._send(200, counter.dispense_direct_sale(parts[2], self._cookie(), request_id))
                return
            if parts == ["registration", "patients"]:
                import registration_patient as arrival
                payload = arrival.create_patient_response(body, self._cookie())
                status = 409 if payload.get("code") in {"possible_duplicate", "family_exists"} else 200
                self._send(status, payload)
                return
            if parts == ["registration", "families"]:
                import hospital_family as household

                created = household.create_family_for_existing_patient(body, self._cookie())
                status = 409 if created.get("code") == "family_exists" else 200
                self._send(status, created)
                return
            if (
                len(parts) == 4
                and parts[0] == "registration"
                and parts[1] == "families"
                and parts[3] == "members"
            ):
                import hospital_family as household

                self._send(200, household.add_or_transfer_member(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 3
                and parts[0] == "registration"
                and parts[1] == "patient"
            ):
                import registration_patient as arrival
                self._send(200, arrival.update_patient(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 6
                and parts[0] == "registration"
                and parts[1] == "patient"
                and parts[3] == "visit"
                and parts[5] == "close"
            ):
                import registration_patient as arrival
                self._send(200, arrival.close_visit(parts[2], parts[4], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "registration"
                and parts[1] == "patient"
                and parts[3] == "visit"
            ):
                import registration_patient as arrival
                started = arrival.start_visit(parts[2], body, self._cookie())
                status = (
                    409
                    if started.get("code")
                    in {"visit_already_open", "admission_in_progress"}
                    else 200
                )
                self._send(status, started)
                return
            if (
                len(parts) == 4
                and parts[0] == "registration"
                and parts[1] == "patient"
                and parts[3] == "charge"
            ):
                import registration as reception
                self._send(200, reception.create_registration_charge(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "antenatal"
                and parts[1] == "patient"
                and parts[3] == "pregnancy"
            ):
                import antenatal as anc

                self._send(200, anc.start_pregnancy(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "antenatal"
                and parts[1] == "patient"
                and parts[3] == "enroll"
            ):
                import antenatal as anc

                self._send(200, anc.enroll_patient(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 5
                and parts[0] == "antenatal"
                and parts[1] == "patient"
                and parts[3] == "pregnancy"
            ):
                import antenatal as anc

                self._send(200, anc.update_pregnancy_card(parts[2], parts[4], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "antenatal"
                and parts[1] == "patient"
                and parts[3] == "visits"
            ):
                import antenatal as anc

                self._send(200, anc.record_anc_visit(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "antenatal"
                and parts[1] == "patient"
                and parts[3] == "charge"
            ):
                import antenatal as anc

                self._send(200, anc.create_anc_registration_charge(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "consultation"
                and parts[1] == "patient"
                and parts[3] == "nhis"
            ):
                import consultation as clinical

                self._send(200, clinical.set_patient_nhis(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "consultation"
                and parts[1] == "patient"
                and parts[3] == "charge"
            ):
                import consultation as clinical
                self._send(200, clinical.create_consultation_charge(parts[2], body, self._cookie()))
                return
            if parts == ["consultation", "call-patient"]:
                import patient_call as paging

                self._send(200, paging.create_patient_call(body, self._cookie()))
                return
            import messaging
            if parts == ["messages", "presence"]:
                self._send(200, messaging.heartbeat(self._cookie()))
                return
            if parts == ["messages", "conversations"]:
                self._send(200, messaging.create_conversation(body, self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "messages" and parts[1] == "conversations":
                conversation_id = parts[2]
                if parts[3] == "messages":
                    self._send(200, messaging.send_message(conversation_id, body, self._cookie()))
                    return
                if parts[3] == "read":
                    self._send(200, messaging.mark_read(conversation_id, body, self._cookie()))
                    return
                if parts[3] == "attention":
                    self._send(200, messaging.request_attention(conversation_id, body, self._cookie()))
                    return
            if len(parts) == 4 and parts[0] == "messages" and parts[1] == "attention" and parts[3] == "acknowledge":
                self._send(200, messaging.acknowledge_attention(parts[2], self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "reception"
                and parts[1] == "patient-calls"
                and parts[3] == "ack"
            ):
                import patient_call as paging

                self._send(200, paging.acknowledge_call(parts[2], self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "notifications" and parts[2] == "ack":
                import notifications as staff_notes

                self._send(200, staff_notes.acknowledge(parts[1], self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "notifications" and parts[2] == "read":
                import notifications as staff_notes

                self._send(200, staff_notes.mark_read(parts[1], self._cookie()))
                return
            if len(parts) == 3 and parts[0] == "patient" and parts[2] == "allergies":
                import allergies as hypersensitivity

                self._send(200, hypersensitivity.create_allergy(parts[1], body, self._cookie()))
                return
            if (
                len(parts) == 5
                and parts[0] == "patient"
                and parts[2] == "allergies"
                and parts[4] == "void"
            ):
                import allergies as hypersensitivity

                self._send(200, hypersensitivity.void_allergy(parts[1], parts[3], self._cookie()))
                return
            if len(parts) == 4 and parts[0] == "patient" and parts[2] == "allergies":
                import allergies as hypersensitivity

                self._send(200, hypersensitivity.update_allergy(parts[1], parts[3], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "order"
                and parts[3] == "delete"
            ):
                import laboratory as lab_billing

                self._send(200, lab_billing.delete_lab_order(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "patient"
                and parts[3] == "charge"
            ):
                import laboratory as lab_billing
                self._send(200, lab_billing.create_laboratory_charge(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "patient"
                and parts[3] == "orders"
            ):
                import laboratory as lab_billing
                self._send(200, lab_billing.create_lab_orders(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "patient"
                and parts[3] == "direct-orders"
            ):
                import laboratory as lab_billing

                self._send(200, lab_billing.create_lab_direct_orders(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 5
                and parts[0] == "laboratory"
                and parts[1] == "order"
                and parts[3] == "workflow"
            ):
                import laboratory as lab_billing

                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                patient_uuid = (query.get("patient") or query.get("patientUuid") or [""])[0].strip() or None
                action = parts[4]
                if action == "collect":
                    result = lab_billing.collect_lab_sample(parts[2], body, patient_uuid, self._cookie())
                elif action == "results":
                    result = lab_billing.save_lab_results(parts[2], body, patient_uuid, self._cookie())
                elif action == "validate":
                    result = lab_billing.validate_lab_results(parts[2], body, patient_uuid, self._cookie())
                else:
                    raise ApiError(404, "not_found", "Laboratory workflow action not found.")
                self._send(200, result)
                return
            if parts == ["laboratory", "external-patient"]:
                import laboratory_external as lab_external

                self._send(200, lab_external.create_or_find_external_patient(body, self._cookie()))
                return
            if parts == ["laboratory", "external-order"]:
                import laboratory_external as lab_external

                self._send(200, lab_external.create_external_lab_order(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "laboratory"
                and parts[1] == "external-patient"
                and parts[3] == "link"
            ):
                import laboratory_external as lab_external

                self._send(200, lab_external.link_external_patient(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "radiology"
                and parts[1] == "patient"
                and parts[3] == "charge"
            ):
                import radiology as imaging
                self._send(200, imaging.create_radiology_charge(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "radiology"
                and parts[1] == "patient"
                and parts[3] == "orders"
            ):
                import radiology as imaging
                self._send(200, imaging.create_radiology_orders(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "radiology"
                and parts[1] == "patient"
                and parts[3] == "direct-study"
            ):
                import radiology as imaging
                self._send(200, imaging.create_direct_radiology_study(parts[2], body, self._cookie()))
                return
            if parts == ["radiology", "external-study"]:
                import radiology_external as external

                self._send(200, external.create_external_study(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "radiology"
                and parts[1] == "external-study"
                and parts[3] == "report"
            ):
                import radiology_external as external

                self._send(200, external.save_external_report(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "radiology"
                and parts[1] == "external-study"
                and parts[3] == "link"
            ):
                import radiology_external as external

                self._send(200, external.link_external_study(parts[2], body, self._cookie()))
                return
            import inpatient as ward
            if (
                len(parts) == 6
                and parts[0] == "nursing"
                and parts[1] == "patient"
                and parts[3] == "treatment"
                and parts[5] == "notes"
            ):
                if self.command != "POST":
                    self._send(
                        405,
                        {"status": "error", "code": "method_not_allowed", "message": "Treatment notes use POST."},
                    )
                    return
                import nursing_treatment as treatments

                self._send(
                    200,
                    treatments.create_treatment_note(
                        parts[2],
                        parts[4],
                        body,
                        self._cookie(),
                    ),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "nursing"
                and parts[1] == "patient"
                and parts[3] in {"treatment", "treatment-call"}
            ):
                if self.command != "POST":
                    self._send(
                        405,
                        {
                            "status": "error",
                            "code": "method_not_allowed",
                            "message": "Use the treatment action to record a nursing treatment.",
                        },
                    )
                    return
                import nursing_treatment as treatments

                self._send(
                    200,
                    (
                        treatments.record_treatment(parts[2], body, self._cookie())
                        if parts[3] == "treatment"
                        else treatments.call_reception(parts[2], body, self._cookie())
                    ),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "admit-decision"
            ):
                self._send(200, ward.create_admit_decision(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "nursing-notes"
            ):
                if self.command != "POST":
                    self._send(
                        405,
                        {
                            "status": "error",
                            "code": "immutable_record",
                            "message": "Nursing notes cannot be changed or deleted.",
                        },
                    )
                    return
                self._send(200, ward.create_nursing_note(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "medication-administration"
            ):
                if self.command != "POST":
                    self._send(
                        405,
                        {
                            "status": "error",
                            "code": "immutable_record",
                            "message": "Medication administrations cannot be changed or deleted.",
                        },
                    )
                    return
                import medication_administration as mar

                self._send(
                    200,
                    mar.create_scheduled_administration(
                        parts[2],
                        body,
                        self._cookie(),
                    ),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "medication-schedule"
            ):
                if self.command != "POST":
                    self._send(
                        405,
                        {
                            "status": "error",
                            "code": "method_not_allowed",
                            "message": "Use the prescribe action to create the ward schedule.",
                        },
                    )
                    return
                import medication_schedule as schedules

                self._send(
                    200,
                    schedules.create_medication_schedules(parts[2], self._cookie()),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "inpatient"
                and parts[1] == "patient"
                and parts[3] == "vitals"
            ):
                if self.command != "POST":
                    self._send(
                        405,
                        {
                            "status": "error",
                            "code": "immutable_record",
                            "message": "Recorded vitals cannot be changed or deleted.",
                        },
                    )
                    return
                import inpatient_vitals as vitals

                self._send(200, vitals.create_vitals(parts[2], body, self._cookie()))
                return
            if parts == ["inpatient", "assign"]:
                self._send(200, ward.assign_bed(body, self._cookie()))
                return
            if parts == ["inpatient", "transfer"]:
                self._send(200, ward.transfer_bed(body, self._cookie()))
                return
            if parts == ["inpatient", "discharge"]:
                self._send(200, ward.discharge_patient(body, self._cookie()))
                return
            if parts == ["inpatient", "cancel-admission"]:
                self._send(200, ward.cancel_waiting_admission(body, self._cookie()))
                return
            import accommodation as lodging
            if parts == ["inpatient", "accommodation", "tariffs"]:
                self._send(200, lodging.save_tariff(body, self._cookie()))
                return
            if parts == ["inpatient", "accommodation", "catch-up"]:
                self._send(200, lodging.catch_up_request(body, self._cookie()))
                return
            if parts == ["inpatient", "accommodation", "charge"]:
                self._send(200, lodging.retry_charge(body, self._cookie()))
                return
            if parts == ["admin", "staff"]:
                import hospital_admin as administration
                self._send(200, administration.create_staff(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] == "profile"
            ):
                import staff_hr as directory

                self._send(200, directory.update_staff_profile(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] in {"photo", "appointment-letter"}
            ):
                import staff_hr as directory

                self._send(
                    200,
                    directory.upload_staff_file(
                        parts[2],
                        "photo" if parts[3] == "photo" else "letter",
                        body,
                        self._cookie(),
                    ),
                )
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] == "access"
            ):
                import hospital_admin as administration
                self._send(200, administration.update_access(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] == "status"
            ):
                import hospital_admin as administration
                self._send(200, administration.update_status(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] == "password"
            ):
                import hospital_admin as administration
                self._send(200, administration.change_password(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "staff"
                and parts[3] == "attendance-code"
            ):
                import attendance as staff_log

                self._send(200, staff_log.set_staff_attendance_code(parts[2], body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "patients"
                and parts[3] == "life-status"
            ):
                import patient_life_status as life

                self._send(200, life.update_life_status(parts[2], body, self._cookie()))
                return
            if parts == ["admin", "export"]:
                import admin_export as exports

                self._send(200, exports.generate_export(body, self._cookie()))
                return
            if (
                len(parts) == 4
                and parts[0] == "admin"
                and parts[1] == "export"
                and parts[3] == "delete"
            ):
                import admin_export as exports

                self._send(200, exports.delete_export(parts[2], self._cookie()))
                return
            self._send(405, {"status": "error", "code": "read_only", "message": "This path is read-only."})
        except ApiError as error:
            self._send(error.status, {"status": "error", "code": error.code, "message": error.message})
        except json.JSONDecodeError:
            self._send(422, {"status": "error", "code": "invalid_body", "message": "This request is invalid."})
        except Exception:
            traceback.print_exc()
            self._send(
                500,
                {
                    "status": "error",
                    "code": "server_error",
                    "message": "Unable to complete the request.",
                },
            )

    def do_PUT(self) -> None:  # noqa: N802
        self.do_POST()

    def do_PATCH(self) -> None:  # noqa: N802
        self.do_POST()

    def do_DELETE(self) -> None:  # noqa: N802
        self.do_POST()


def main() -> None:
    validate_deployment_config()
    import registration as reception

    reception.start_bill_account_sync()
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"Hospital EMR patient-account API listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
