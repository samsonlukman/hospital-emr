"""Accountant payment refunds — financial reversal without pharmacy stock.

Creates a posted customer credit note (out_refund) and a posted outbound
customer payment for the cash return. Markers record the authenticated
processor. Pharmacy stock is never restored here — use Pharmacy Sales History
for medicine returns.
"""

from __future__ import annotations

import re
import threading
import xmlrpc.client
from typing import Any

import accountant as cashier
import finance_summary as finance
from server import ApiError

execute = cashier.execute
odoo_reader = cashier.odoo_reader
require_accountant = cashier.require_accountant
as_float = cashier.as_float
many2one_id = cashier.many2one_id
many2one_name = cashier.many2one_name
format_money = cashier.format_money
load_currency = cashier.load_currency

REFUND_PREFIX = "ABIKAN_PAYMENT_REFUND:"
REFUND_RE = re.compile(r"ABIKAN_PAYMENT_REFUND:(\d+):([0-9]+(?:\.[0-9]+)?)")

IDEMPOTENCY: dict[str, dict[str, Any]] = {}
IDEMPOTENCY_LOCK = threading.Lock()


def reset_for_tests() -> None:
    with IDEMPOTENCY_LOCK:
        IDEMPOTENCY.clear()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _staff_currency_id(odoo: cashier.OdooReader, currency_id: int | None) -> int | None:
    """Prefer NGN for hospital money. Never create new refunds in company USD."""
    if currency_id:
        rows = odoo.read("res.currency", [int(currency_id)], ["name"]) or []
        if rows and _text(rows[0].get("name")) == "NGN":
            return int(currency_id)
    ngn = (
        execute(
            odoo,
            "res.currency",
            "search",
            [[("name", "=", "NGN")]],
            {"limit": 1},
        )
        or []
    )
    if ngn:
        return int(ngn[0])
    return currency_id


def refunded_amounts_by_payment(note_or_ref: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for match in REFUND_RE.finditer(note_or_ref or ""):
        payment_id = match.group(1)
        totals[payment_id] = round(totals.get(payment_id, 0.0) + as_float(match.group(2)), 2)
    return totals


def _sum_refunded_for_payment(odoo: cashier.OdooReader, payment_id: int) -> float:
    marker = f"{REFUND_PREFIX}{payment_id}:"
    moves = (
        execute(
            odoo,
            "account.move",
            "search_read",
            [[("move_type", "=", "out_refund"), ("state", "=", "posted"), ("ref", "ilike", marker)]],
            {"fields": ["ref", "amount_total"], "limit": 200},
        )
        or []
    )
    payments = (
        execute(
            odoo,
            "account.payment",
            "search_read",
            [
                [
                    ("payment_type", "=", "outbound"),
                    ("partner_type", "=", "customer"),
                    ("state", "=", "posted"),
                    ("ref", "ilike", marker),
                ]
            ],
            {"fields": ["ref", "amount"], "limit": 200},
        )
        or []
    )
    total = 0.0
    for row in moves:
        parsed = refunded_amounts_by_payment(_text(row.get("ref")))
        total = max(total, parsed.get(str(payment_id), as_float(row.get("amount_total"))))
    cash = 0.0
    for row in payments:
        parsed = refunded_amounts_by_payment(_text(row.get("ref")))
        cash += parsed.get(str(payment_id), as_float(row.get("amount")))
    # Prefer cash returned when present; otherwise credit-note total.
    return round(cash if cash > 0 else total, 2)


def payment_refund_summary(odoo: cashier.OdooReader, payment: dict[str, Any]) -> dict[str, Any]:
    payment_id = int(payment["id"])
    original = as_float(payment.get("amount"))
    refunded = _sum_refunded_for_payment(odoo, payment_id)
    refundable = round(max(original - refunded, 0.0), 2)
    if refundable <= 0.0001:
        status = "Refunded"
    elif refunded > 0:
        status = "Partially Refunded"
    else:
        status = "Paid"
    return {
        "amountRefunded": refunded,
        "amountRefundable": refundable,
        "refundStatus": status,
        "canRefund": refundable > 0.0001 and _text(payment.get("state")).lower() == "posted",
    }


def _outbound_method_line(odoo: cashier.OdooReader, journal_id: int) -> int | None:
    rows = (
        execute(
            odoo,
            "account.payment.method.line",
            "search_read",
            [[("journal_id", "=", journal_id), ("payment_type", "=", "outbound")]],
            {"fields": ["id"], "limit": 1},
        )
        or []
    )
    return int(rows[0]["id"]) if rows else None


def _create_credit_note(
    odoo: cashier.OdooReader,
    *,
    partner_id: int,
    amount: float,
    journal_id: int | None,
    company_id: int | None,
    currency_id: int | None,
    reason: str,
    marker: str,
) -> int:
    values: dict[str, Any] = {
        "move_type": "out_refund",
        "partner_id": partner_id,
        "ref": marker[:200],
        "narration": reason[:500],
        "invoice_line_ids": [
            (
                0,
                0,
                {
                    "name": reason[:200] or "Payment refund",
                    "quantity": 1,
                    "price_unit": amount,
                },
            )
        ],
    }
    if journal_id:
        values["journal_id"] = journal_id
    if company_id:
        values["company_id"] = company_id
    # Always stamp hospital NGN so refunds never inherit company USD.
    resolved = _staff_currency_id(odoo, currency_id)
    if resolved:
        values["currency_id"] = resolved
    try:
        credit_id = int(execute(odoo, "account.move", "create", [values]))
        execute(odoo, "account.move", "action_post", [[credit_id]])
        return credit_id
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "refund_finance_failed",
            "The financial refund could not be completed. No cash return was recorded.",
        ) from error


def _create_outbound_payment(
    odoo: cashier.OdooReader,
    *,
    partner_id: int,
    amount: float,
    journal_id: int,
    currency_id: int | None,
    marker: str,
    payment_date: str,
) -> int:
    method_line = _outbound_method_line(odoo, journal_id)
    values: dict[str, Any] = {
        "payment_type": "outbound",
        "partner_type": "customer",
        "partner_id": partner_id,
        "amount": amount,
        "journal_id": journal_id,
        "date": payment_date,
        "ref": marker[:200],
    }
    if method_line:
        values["payment_method_line_id"] = method_line
    resolved = _staff_currency_id(odoo, currency_id)
    if resolved:
        values["currency_id"] = resolved
    try:
        payment_id = int(execute(odoo, "account.payment", "create", [values]))
        execute(odoo, "account.payment", "action_post", [[payment_id]])
        return payment_id
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "refund_cash_failed",
            "The credit note was created, but the cash return could not be posted. Contact hospital admin before retrying.",
        ) from error


def refund_payment(payment_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_accountant(cookie)
    username = _text(user.get("username")) or "accountant"
    if not str(payment_id).isdigit():
        raise ApiError(422, "invalid_payment", "Choose a payment to refund.")
    payment_id_int = int(payment_id)

    request_id = _text(body.get("requestId"))
    if not request_id:
        raise ApiError(422, "request_id_required", "Refresh and try the refund again.")
    reason = _text(body.get("reason")) or "Payment refund"
    if len(reason) > 200:
        raise ApiError(422, "reason_too_long", "Keep the refund reason under 200 characters.")

    idem_key = f"accountant-refund:{request_id}"
    with IDEMPOTENCY_LOCK:
        existing = IDEMPOTENCY.get(idem_key) or {}
        if existing.get("status") == "pending":
            raise ApiError(409, "refund_in_progress", "This refund is already being processed.")
        if existing.get("status") == "done":
            payload = dict(existing.get("payload") or {})
            payload["duplicate"] = True
            return payload
        IDEMPOTENCY[idem_key] = {"status": "pending"}

    try:
        odoo = odoo_reader()
        rows = odoo.read(
            "account.payment",
            [payment_id_int],
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
                "partner_type",
                "payment_type",
                "company_id",
                "create_uid",
                "create_date",
                "ref",
            ],
        )
        if not rows:
            raise ApiError(404, "payment_not_found", "That payment was not found.")
        payment = rows[0]
        if _text(payment.get("payment_type")).lower() != "inbound":
            raise ApiError(409, "not_refundable", "Only collected customer payments can be refunded.")
        if _text(payment.get("partner_type")).lower() != "customer":
            raise ApiError(409, "not_refundable", "Only customer payments can be refunded.")
        if _text(payment.get("state")).lower() != "posted":
            raise ApiError(409, "not_refundable", "Only posted payments can be refunded.")

        summary = payment_refund_summary(odoo, payment)
        if not summary["canRefund"]:
            detail = cashier.get_payment(payment_id_int, cookie)
            result = {
                "status": "ok",
                "duplicate": True,
                "refunded": True,
                "refundStatus": "Refunded",
                "message": "This payment was already refunded.",
                "payment": detail.get("payment"),
            }
            with IDEMPOTENCY_LOCK:
                IDEMPOTENCY[idem_key] = {"status": "done", "payload": result}
            return result

        amount_raw = body.get("amount")
        if amount_raw in (None, ""):
            amount = float(summary["amountRefundable"])
        else:
            amount = round(as_float(amount_raw), 2)
        if amount <= 0:
            raise ApiError(422, "invalid_amount", "Enter how much to refund.")
        if amount > float(summary["amountRefundable"]) + 0.001:
            raise ApiError(
                422,
                "amount_too_high",
                f"Only {summary['amountRefundable']:g} can still be refunded on this payment.",
            )

        partner_id = many2one_id(payment.get("partner_id"))
        journal_id = many2one_id(payment.get("journal_id"))
        if not partner_id or not journal_id:
            raise ApiError(502, "refund_finance_failed", "This payment is missing account details.")

        currency_id = many2one_id(payment.get("currency_id"))
        company_id = many2one_id(payment.get("company_id"))
        invoice_journal_id = None
        invoice_ids = [int(item) for item in (payment.get("reconciled_invoice_ids") or [])]
        if invoice_ids:
            inv = odoo.read("account.move", [invoice_ids[0]], ["journal_id"])
            if inv:
                invoice_journal_id = many2one_id(inv[0].get("journal_id"))
        marker = f"{REFUND_PREFIX}{payment_id_int}:{amount:g}:{username}"
        credit_id = _create_credit_note(
            odoo,
            partner_id=partner_id,
            amount=amount,
            journal_id=invoice_journal_id,
            company_id=company_id,
            currency_id=currency_id,
            reason=f"{reason} · {payment.get('name') or payment_id_int}",
            marker=marker,
        )
        outbound_id = _create_outbound_payment(
            odoo,
            partner_id=partner_id,
            amount=amount,
            journal_id=journal_id,
            currency_id=currency_id,
            marker=marker,
            payment_date=finance.hospital_business_date(),
        )

        updated = payment_refund_summary(odoo, payment)
        detail = cashier.get_payment(payment_id_int, cookie)
        currency = cashier.staff_currency(odoo, currency_id)
        result = {
            "status": "ok",
            "duplicate": False,
            "refunded": updated["amountRefundable"] <= 0.0001,
            "refundStatus": updated["refundStatus"],
            "refundAmount": format_money(amount, currency),
            "creditNoteId": credit_id,
            "outboundPaymentId": outbound_id,
            "processedBy": username,
            "reason": reason,
            "message": (
                f"Refunded {format_money(amount, currency)['formatted']} from "
                f"{payment.get('name') or payment_id_int}."
            ),
            "payment": detail.get("payment"),
        }
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[idem_key] = {"status": "done", "payload": result}
        return result
    except Exception:
        with IDEMPOTENCY_LOCK:
            state = IDEMPOTENCY.get(idem_key) or {}
            if state.get("status") == "pending":
                IDEMPOTENCY.pop(idem_key, None)
        raise
