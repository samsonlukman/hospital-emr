"""Bills for patients on an HMO list, and the statement sent to that HMO.

Cashier only sees an invoiced balance. Care that has not been invoiced still
belongs on the HMO statement.
"""

from __future__ import annotations

import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any

import hmo
import hospital_admin
import server as core

HOSPITAL_NAME = "Hospital EMR"
HOSPITAL_PHONE = "0803 555 0142"
HOSPITAL_EMAIL = "accounts@abikanhospital.test"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hospital_contact() -> dict[str, str]:
    return {"name": HOSPITAL_NAME, "phone": HOSPITAL_PHONE, "email": HOSPITAL_EMAIL}


def _day(value: str, label: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as error:
        raise core.ApiError(422, "period_required", f"Choose a valid {label}.") from error
    return text


def period(start: str, end: str) -> tuple[str, str]:
    first = _day(start, "start date")
    last = _day(end, "end date")
    if first > last:
        raise core.ApiError(422, "period_required", "The start date must be on or before the end date.")
    return first, last


def _in_period(value: Any, start: str, end: str) -> bool:
    day = str(value or "")[:10]
    return bool(day) and start <= day <= end


def _naira(amount: float) -> str:
    return f"₦{amount:,.2f}"


def _status_label(payment_state: str) -> str:
    label = core.payment_state_label(payment_state)
    if label == "PAID":
        return "Paid"
    if label == "PARTIALLY PAID":
        return "Part paid"
    if label == "REVERSED":
        return "Reversed"
    return "Unpaid"


def assemble_statement(
    assignments: list[dict[str, Any]],
    charges: list[dict[str, Any]],
    *,
    body: str,
    scheme: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Group one HMO's patients and the charges that fall in the period."""
    selected = [
        row
        for row in assignments
        if str(row.get("body") or "") == body and (not scheme or str(row.get("scheme") or "") == scheme)
    ]
    by_patient: dict[str, list[dict[str, Any]]] = {}
    for charge in charges:
        if not _in_period(charge.get("date"), start, end):
            continue
        by_patient.setdefault(str(charge.get("patientUuid") or ""), []).append(charge)
    patients = []
    total = paid = 0.0
    for row in selected:
        uuid = str(row.get("patient_uuid") or row.get("patientUuid") or "")
        lines = sorted(by_patient.get(uuid, []), key=lambda item: str(item.get("date") or ""))
        patient_total = 0.0
        prepared = []
        for line in lines:
            amount = float(line.get("amount") or 0)
            patient_total += amount
            prepared.append(
                {
                    "date": str(line.get("date") or "")[:10],
                    "description": str(line.get("description") or "Charge"),
                    "department": str(line.get("department") or ""),
                    "amount": amount,
                    "amountLabel": str(line.get("amountLabel") or _naira(amount)),
                }
            )
        total += patient_total
        patients.append(
            {
                "patientUuid": uuid,
                "patientName": str(row.get("patient_name") or row.get("patientName") or ""),
                "hospitalNumber": str(row.get("hospital_number") or row.get("hospitalNumber") or ""),
                "scheme": str(row.get("scheme") or scheme),
                "lines": prepared,
                "totalLabel": _naira(patient_total),
            }
        )
    return {
        "hospital": hospital_contact(),
        "body": body,
        "scheme": scheme,
        "start": start,
        "end": end,
        "patients": patients,
        "patientCount": len(patients),
        "total": total,
        "totalLabel": _naira(total),
    }


def list_bodies(assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Both coverage types, with every body under that type."""
    counts: dict[tuple[str, str], int] = {}
    for row in assignments:
        key = (str(row.get("scheme") or ""), str(row.get("body") or ""))
        counts[key] = counts.get(key, 0) + 1
    bodies: list[dict[str, Any]] = []
    for scheme, names in hmo.SCHEMES.items():
        for name in names:
            bodies.append({"scheme": scheme, "body": name, "patients": counts.get((scheme, name), 0)})
    return bodies


def _assignments(cookie: str) -> list[dict[str, Any]]:
    hospital_admin.require_hospital_admin(cookie)
    with hmo._db() as connection:
        rows = connection.execute(
            """
            SELECT patient_uuid, patient_name, hospital_number, scheme, body
            FROM hmo_assignments
            ORDER BY patient_name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _partners_for(odoo: core.OdooReader, assignments: list[dict[str, Any]]) -> dict[str, int]:
    uuids = [str(row["patient_uuid"]) for row in assignments if row.get("patient_uuid")]
    numbers = [str(row["hospital_number"]) for row in assignments if row.get("hospital_number")]
    found: list[dict[str, Any]] = []
    if uuids:
        found.extend(odoo.search_read("res.partner", [("uuid", "in", uuids)], ["id", "uuid", "ref"], limit=500))
    if numbers:
        found.extend(odoo.search_read("res.partner", [("ref", "in", numbers)], ["id", "uuid", "ref"], limit=500))
    by_uuid = {str(row.get("uuid") or ""): int(row["id"]) for row in found if row.get("uuid")}
    by_ref = {str(row.get("ref") or ""): int(row["id"]) for row in found if row.get("ref")}
    mapped: dict[str, int] = {}
    for row in assignments:
        uuid = str(row.get("patient_uuid") or "")
        partner_id = by_uuid.get(uuid) or by_ref.get(str(row.get("hospital_number") or ""))
        if partner_id:
            mapped[uuid] = partner_id
    return mapped


def _charges(odoo: core.OdooReader, partner_by_patient: dict[str, int]) -> list[dict[str, Any]]:
    if not partner_by_patient:
        return []
    patient_by_partner = {partner_id: uuid for uuid, partner_id in partner_by_patient.items()}
    partner_ids = list(patient_by_partner)
    invoices = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("partner_id", "in", partner_ids),
        ],
        ["name", "invoice_date", "invoice_origin", "amount_total", "payment_state", "partner_id", "currency_id", "invoice_line_ids"],
        limit=500,
    )
    currencies = core.money_maps(
        odoo,
        {cid for row in invoices if (cid := core.many2one_id(row.get("currency_id")))},
    )
    default = core.load_currency(odoo, None)
    line_ids = [int(item) for row in invoices for item in (row.get("invoice_line_ids") or [])]
    lines = odoo.read("account.move.line", line_ids, ["move_id", "name", "price_subtotal", "quantity"]) if line_ids else []
    lines_by_move: dict[int, list[dict[str, Any]]] = {}
    for line in lines:
        if float(line.get("quantity") or 0) == 0 and float(line.get("price_subtotal") or 0) == 0:
            continue
        move_id = core.many2one_id(line.get("move_id"))
        if move_id:
            lines_by_move.setdefault(int(move_id), []).append(line)
    origins = [row.get("invoice_origin") for row in invoices if row.get("invoice_origin")]
    orders = (
        odoo.search_read("sale.order", [("name", "in", origins)], ["name", "shop_id"], limit=500) if origins else []
    )
    shop_by_origin = {row.get("name"): core.many2one_name(row.get("shop_id")) for row in orders}
    charges: list[dict[str, Any]] = []
    invoiced_origins = {str(row.get("invoice_origin") or "") for row in invoices if row.get("invoice_origin")}
    for invoice in invoices:
        partner_id = core.many2one_id(invoice.get("partner_id"))
        patient_uuid = patient_by_partner.get(int(partner_id or 0), "")
        currency = currencies.get(core.many2one_id(invoice.get("currency_id")) or 0, default)
        department = core.identify_department(shop_by_origin.get(invoice.get("invoice_origin") or "") or "", []) or ""
        status = _status_label(str(invoice.get("payment_state") or ""))
        detail = lines_by_move.get(int(invoice["id"])) or []
        if not detail:
            amount = core.as_float(invoice.get("amount_total"))
            charges.append(
                {
                    "patientUuid": patient_uuid,
                    "date": invoice.get("invoice_date") or "",
                    "description": invoice.get("name") or "Bill",
                    "department": department,
                    "amount": amount,
                    "amountLabel": core.format_money(amount, currency).get("formatted") or _naira(amount),
                    "status": status,
                }
            )
            continue
        for line in detail:
            amount = core.as_float(line.get("price_subtotal"))
            charges.append(
                {
                    "patientUuid": patient_uuid,
                    "date": invoice.get("invoice_date") or "",
                    "description": str(line.get("name") or "Charge").split("\n", 1)[0],
                    "department": department,
                    "amount": amount,
                    "amountLabel": core.format_money(amount, currency).get("formatted") or _naira(amount),
                    "status": status,
                }
            )
    sales = odoo.search_read(
        "sale.order",
        [("partner_id", "in", partner_ids), ("state", "!=", "cancel")],
        ["name", "date_order", "amount_total", "partner_id", "shop_id", "invoice_ids", "currency_id", "order_line"],
        limit=500,
    )
    pending = [row for row in sales if not row.get("invoice_ids") and str(row.get("name") or "") not in invoiced_origins]
    order_lines: dict[int, list[dict[str, Any]]] = {}
    pending_line_ids = [int(item) for row in pending for item in (row.get("order_line") or [])]
    if pending_line_ids:
        for line in odoo.read("sale.order.line", pending_line_ids, ["order_id", "name", "price_subtotal"]):
            order_id = core.many2one_id(line.get("order_id"))
            if order_id:
                order_lines.setdefault(int(order_id), []).append(line)
    for sale in pending:
        partner_id = core.many2one_id(sale.get("partner_id"))
        patient_uuid = patient_by_partner.get(int(partner_id or 0), "")
        currency = currencies.get(core.many2one_id(sale.get("currency_id")) or 0, default)
        department = core.identify_department(core.many2one_name(sale.get("shop_id")), []) or ""
        detail = order_lines.get(int(sale["id"])) or []
        if not detail:
            amount = core.as_float(sale.get("amount_total"))
            charges.append(
                {
                    "patientUuid": patient_uuid,
                    "date": sale.get("date_order") or "",
                    "description": sale.get("name") or "Charge",
                    "department": department,
                    "amount": amount,
                    "amountLabel": core.format_money(amount, currency).get("formatted") or _naira(amount),
                    "status": "Not invoiced",
                }
            )
            continue
        for line in detail:
            amount = core.as_float(line.get("price_subtotal"))
            charges.append(
                {
                    "patientUuid": patient_uuid,
                    "date": sale.get("date_order") or "",
                    "description": str(line.get("name") or "Charge").split("\n", 1)[0],
                    "department": department,
                    "amount": amount,
                    "amountLabel": core.format_money(amount, currency).get("formatted") or _naira(amount),
                    "status": "Not invoiced",
                }
            )
    return charges


def bills(cookie: str, body: str = "", scheme: str = "", start: str = "", end: str = "") -> dict[str, Any]:
    assignments = _assignments(cookie)
    payload: dict[str, Any] = {"status": "ok", "hospital": hospital_contact(), "bodies": list_bodies(assignments)}
    if not body:
        return payload
    first, last = period(start, end)
    selected = [
        row
        for row in assignments
        if str(row.get("body") or "") == body and (not scheme or str(row.get("scheme") or "") == scheme)
    ]
    try:
        odoo = core.OdooReader()
        charges = _charges(odoo, _partners_for(odoo, selected))
    except core.ApiError:
        raise
    except Exception as error:
        raise core.ApiError(502, "hmo_bills_unavailable", "HMO bills could not be loaded. Try again.") from error
    payload["statement"] = assemble_statement(selected, charges, body=body, scheme=scheme, start=first, end=last)
    return payload


def statement_html(statement: dict[str, Any]) -> str:
    hospital = statement.get("hospital") or hospital_contact()
    rows = []
    for patient in statement.get("patients") or []:
        lines = patient.get("lines") or []
        if not lines:
            line_html = "<tr><td colspan='4'>No bills in this period.</td></tr>"
        else:
            line_html = "".join(
                "<tr>"
                f"<td>{_escape(line.get('date'))}</td>"
                f"<td>{_escape(line.get('description'))}</td>"
                f"<td>{_escape(line.get('department'))}</td>"
                f"<td class='num'>{_escape(line.get('amountLabel'))}</td>"
                "</tr>"
                for line in lines
            )
        rows.append(
            "<section class='patient'>"
            f"<h2>{_escape(patient.get('patientName'))}</h2>"
            f"<p class='meta'>{_escape(patient.get('hospitalNumber'))}</p>"
            "<table><thead><tr><th>Date</th><th>Description</th><th>Department</th><th>Amount</th></tr></thead>"
            f"<tbody>{line_html}</tbody></table>"
            f"<p class='patient-total'>Patient total {_escape(patient.get('totalLabel'))}</p>"
            "</section>"
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>HMO statement</title>
<style>
body {{ margin: 0; background: #f4f6f8; color: #1a2332; font: 14px/1.45 Georgia, "Times New Roman", serif; }}
.sheet {{ max-width: 760px; margin: 24px auto; background: #fff; border: 1px solid #e2e7ee; }}
.bar {{ height: 8px; background: #0d7377; }}
.head {{ padding: 28px 36px 18px; border-bottom: 1px solid #e2e7ee; }}
.head p {{ margin: 0; letter-spacing: 0.14em; text-transform: uppercase; font: 11px/1.4 "Helvetica Neue", Helvetica, Arial, sans-serif; color: #5b6675; }}
.head h1 {{ margin: 8px 0 0; font-size: 22px; font-weight: 500; color: #121e33; }}
.contact {{ margin-top: 10px; font: 13px/1.4 "Helvetica Neue", Helvetica, Arial, sans-serif; color: #5b6675; }}
.intro {{ padding: 22px 36px 0; }}
.intro h2 {{ margin: 0; font-size: 20px; font-weight: 500; }}
.intro p {{ margin: 6px 0 0; color: #5b6675; font: 13px/1.4 "Helvetica Neue", Helvetica, Arial, sans-serif; }}
.patient {{ padding: 8px 36px 0; }}
.patient h2 {{ margin: 18px 0 0; font-size: 16px; }}
.meta {{ margin: 2px 0 8px; color: #5b6675; font: 12px "Helvetica Neue", Helvetica, Arial, sans-serif; }}
table {{ width: 100%; border-collapse: collapse; font: 13px/1.4 "Helvetica Neue", Helvetica, Arial, sans-serif; }}
th {{ text-align: left; color: #5b6675; font-weight: 600; font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; border-bottom: 1px solid #121e33; padding: 6px 8px 6px 0; }}
td {{ border-bottom: 1px solid #e2e7ee; padding: 8px 8px 8px 0; vertical-align: top; }}
.num, th:nth-child(4), td:nth-child(4) {{ text-align: right; }}
.patient-total {{ margin: 8px 0 0; text-align: right; font: 13px "Helvetica Neue", Helvetica, Arial, sans-serif; }}
.totals {{ margin: 22px 36px 32px; padding-top: 12px; border-top: 2px solid #0d7377; }}
.totals div {{ display: flex; justify-content: space-between; font: 14px "Helvetica Neue", Helvetica, Arial, sans-serif; padding: 3px 0; }}
.totals .due {{ font-weight: 650; color: #121e33; }}
</style></head>
<body><article class="sheet"><div class="bar"></div>
<header class="head"><p>HMO statement</p><h1>{_escape(hospital.get("name"))}</h1>
<p class="contact">{_escape(hospital.get("phone"))} · {_escape(hospital.get("email"))}</p></header>
<div class="intro"><h2>{_escape(statement.get("body"))}</h2>
<p>{_escape(statement.get("scheme"))} · {_escape(statement.get("start"))} to {_escape(statement.get("end"))}</p></div>
{''.join(rows)}
<footer class="totals">
<div class="due"><span>Amount due from the HMO</span><span>{_escape(statement.get("totalLabel"))}</span></div>
</footer></article></body></html>"""


def _escape(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _recipient(value: str) -> str:
    email = str(value or "").strip()
    if not _EMAIL.match(email):
        raise core.ApiError(422, "recipient_required", "Enter the email address that should receive this statement.")
    return email


def deliver_statement(statement: dict[str, Any], recipient: str) -> dict[str, str]:
    host = os.environ.get("ABIKAN_SMTP_HOST", "").strip()
    subject = f"{statement.get('body')} statement, {statement.get('start')} to {statement.get('end')}"
    if not host:
        return {
            "sent": "no",
            "message": "The statement is ready. Mail is not set up yet, so it was not sent.",
        }
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ.get("ABIKAN_SMTP_FROM", HOSPITAL_EMAIL)
    message["To"] = recipient
    message.set_content(
        f"{statement.get('body')} statement from {HOSPITAL_NAME} for {statement.get('start')} to {statement.get('end')}."
    )
    message.add_alternative(statement_html(statement), subtype="html")
    port = int(os.environ.get("ABIKAN_SMTP_PORT", "587") or "587")
    user = os.environ.get("ABIKAN_SMTP_USER", "")
    password = os.environ.get("ABIKAN_SMTP_PASSWORD", "")
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise core.ApiError(502, "mail_failed", "The statement could not be sent. Check the mail settings and try again.") from error
    return {"sent": "yes", "message": f"The statement was sent to {recipient}."}


def send_statement(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    recipient = _recipient(str(body.get("recipient") or ""))
    loaded = bills(
        cookie,
        str(body.get("body") or ""),
        str(body.get("scheme") or ""),
        str(body.get("start") or ""),
        str(body.get("end") or ""),
    )
    statement = loaded.get("statement")
    if not statement:
        raise core.ApiError(422, "body_required", "Choose the HMO this statement is for.")
    result = deliver_statement(statement, recipient)
    return {"status": "ok", "statement": statement, **result}
