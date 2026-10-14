"""Pharmacy sale refunds — full sale and item/partial quantity.

Stock returns use stock.return.picking. Financial reversals use Odoo invoice
cancel (full unpaid) or posted out_refund credit notes (paid / partial).

Per-line refunded quantities are recorded on sale.order.note as:
  ABIKAN_LINE_REFUND:{lineId}:{qty}
A full-sale marker ABIKAN_PHARMACY_REFUND is written when nothing remains.
"""

from __future__ import annotations

import re
import threading
import xmlrpc.client
from typing import Any

import pharmacy as dispensary
import pharmacy_history as history
import pharmacy_sale as counter
from server import ApiError

execute = dispensary.execute
odoo_reader = dispensary.odoo_reader
many2one_id = dispensary.many2one_id
as_float = dispensary.as_float
require_pharmacist = dispensary.require_pharmacist

REFUND_MARKER = "ABIKAN_PHARMACY_REFUND"
LINE_REFUND_PREFIX = "ABIKAN_LINE_REFUND:"
LINE_REFUND_RE = re.compile(r"ABIKAN_LINE_REFUND:(\d+):([0-9]+(?:\.[0-9]+)?)")

IDEMPOTENCY: dict[str, dict[str, Any]] = {}
IDEMPOTENCY_LOCK = threading.Lock()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _staff_currency_id(odoo: dispensary.OdooReader, currency_id: int | None) -> int | None:
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


def _sale_note(sale: dict[str, Any]) -> str:
    return _text(sale.get("note") or sale.get("client_order_ref") or "")


def line_refunded_quantities(note: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for match in LINE_REFUND_RE.finditer(note or ""):
        line_id = match.group(1)
        qty = as_float(match.group(2))
        totals[line_id] = round(totals.get(line_id, 0.0) + qty, 4)
    return totals


def _already_fully_refunded(sale: dict[str, Any], invoice: dict[str, Any] | None) -> bool:
    note = _sale_note(sale)
    if REFUND_MARKER in note and LINE_REFUND_PREFIX not in note:
        return True
    payment = _text((invoice or {}).get("payment_state")).lower()
    return payment == "reversed"


def _outgoing_done_picking(odoo: dispensary.OdooReader, sale_id: int) -> dict[str, Any] | None:
    rows = execute(
        odoo,
        "stock.picking",
        "search_read",
        [[("sale_id", "=", sale_id), ("state", "=", "done")]],
        {
            "fields": ["id", "name", "state", "picking_type_id", "location_id", "location_dest_id"],
            "limit": 20,
            "order": "id desc",
        },
    )
    if not rows:
        return None
    type_ids = [many2one_id(row.get("picking_type_id")) for row in rows if many2one_id(row.get("picking_type_id"))]
    types = {
        int(row["id"]): _text(row.get("code"))
        for row in (odoo.read("stock.picking.type", type_ids, ["code"]) if type_ids else [])
    }
    for row in rows:
        code = types.get(many2one_id(row.get("picking_type_id")) or 0, "")
        if code == "outgoing" or _text(row.get("name")).startswith("WH/OUT"):
            return row
    return rows[0]


def _moves_for_picking(odoo: dispensary.OdooReader, picking_id: int) -> list[dict[str, Any]]:
    return (
        execute(
            odoo,
            "stock.move",
            "search_read",
            [[("picking_id", "=", picking_id), ("state", "=", "done")]],
            {
                "fields": ["id", "product_id", "product_uom_qty", "product_qty", "product_uom"],
                "limit": 200,
            },
        )
        or []
    )


def _return_stock_lines(
    odoo: dispensary.OdooReader,
    picking: dict[str, Any],
    return_lines: list[dict[str, Any]],
    username: str,
    marker: str,
) -> int:
    """return_lines: [{product_id, quantity, move_id?, uom_id?}]"""
    picking_id = int(picking["id"])
    if not return_lines:
        raise ApiError(422, "nothing_to_return", "There is nothing left to return to stock.")
    lines = []
    for item in return_lines:
        product_id = int(item["product_id"])
        qty = as_float(item.get("quantity"))
        if product_id <= 0 or qty <= 0:
            continue
        line: dict[str, Any] = {
            "product_id": product_id,
            "quantity": qty,
        }
        if item.get("move_id"):
            line["move_id"] = int(item["move_id"])
        if item.get("uom_id"):
            line["uom_id"] = int(item["uom_id"])
        lines.append((0, 0, line))
    if not lines:
        raise ApiError(422, "nothing_to_return", "There is nothing left to return to stock.")
    values: dict[str, Any] = {"picking_id": picking_id, "product_return_moves": lines}
    location_id = many2one_id(picking.get("location_id"))
    if location_id:
        values["location_id"] = location_id
    try:
        wizard_id = int(
            execute(
                odoo,
                "stock.return.picking",
                "create",
                [values],
                {
                    "context": {
                        "active_id": picking_id,
                        "active_ids": [picking_id],
                        "active_model": "stock.picking",
                    }
                },
            )
        )
        action = execute(odoo, "stock.return.picking", "create_returns", [[wizard_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "refund_stock_failed",
            "Stock could not be restored for this refund. No financial change was applied.",
        ) from error
    return_id = None
    if isinstance(action, dict):
        return_id = action.get("res_id")
        if not return_id:
            domain = action.get("domain") if isinstance(action.get("domain"), list) else []
            for clause in domain:
                if isinstance(clause, (list, tuple)) and len(clause) >= 3 and clause[0] == "id":
                    ids = clause[2] if isinstance(clause[2], (list, tuple)) else []
                    if ids:
                        return_id = ids[0]
                        break
    if not return_id:
        raise ApiError(
            502,
            "refund_stock_failed",
            "Stock could not be restored for this refund. No financial change was applied.",
        )
    return_id = int(return_id)
    try:
        execute(
            odoo,
            "stock.picking",
            "write",
            [
                [return_id],
                {
                    "origin": (
                        f"Return of {picking.get('name') or picking_id} · {username} · {marker}"
                    )
                },
            ],
        )
    except Exception:
        pass
    dispensary._complete_picking(odoo, return_id)
    done = odoo.read("stock.picking", [return_id], ["state"])
    if not done or done[0].get("state") != "done":
        raise ApiError(
            502,
            "refund_stock_failed",
            "Stock could not be restored for this refund. No financial change was applied.",
        )
    return return_id


def _post_credit_note(odoo: dispensary.OdooReader, move_id: int) -> None:
    rows = odoo.read("account.move", [move_id], ["state"])
    if rows and _text(rows[0].get("state")).lower() == "posted":
        return
    try:
        execute(odoo, "account.move", "action_post", [[move_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "refund_finance_failed",
            "Stock was restored, but the financial refund could not be posted. Contact hospital admin before retrying.",
        ) from error


def _load_invoice(odoo: dispensary.OdooReader, sale: dict[str, Any]) -> dict[str, Any] | None:
    invoice = dispensary.related_invoice(odoo, sale)
    if not invoice:
        return None
    invoice_id = int(invoice["id"])
    fresh = odoo.read(
        "account.move",
        [invoice_id],
        [
            "name",
            "state",
            "payment_state",
            "amount_residual",
            "amount_total",
            "move_type",
            "partner_id",
            "journal_id",
            "company_id",
            "currency_id",
            "invoice_origin",
        ],
    )
    return fresh[0] if fresh else invoice


def _reverse_full_invoice(
    odoo: dispensary.OdooReader,
    invoice: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    invoice_id = int(invoice["id"])
    payment = _text(invoice.get("payment_state")).lower()
    if payment == "reversed":
        return {"method": "already_reversed", "creditNoteId": None}

    residual = as_float(invoice.get("amount_residual"))
    total = as_float(invoice.get("amount_total"))
    unpaid = residual + 0.01 >= total and payment in {"", "not_paid"}
    method = "cancel" if unpaid else "refund"

    journal_id = many2one_id(invoice.get("journal_id"))
    company_id = many2one_id(invoice.get("company_id"))
    values: dict[str, Any] = {
        "move_ids": [(6, 0, [invoice_id])],
        "refund_method": method,
        "reason": reason,
        "date_mode": "entry",
    }
    if journal_id:
        values["journal_id"] = journal_id
    if company_id:
        values["company_id"] = company_id
    try:
        wizard_id = int(execute(odoo, "account.move.reversal", "create", [values]))
        execute(odoo, "account.move.reversal", "reverse_moves", [[wizard_id]])
        wizards = odoo.read("account.move.reversal", [wizard_id], ["new_move_ids"])
        new_ids = (wizards[0].get("new_move_ids") if wizards else []) or []
        credit_id = int(new_ids[0]) if new_ids else None
        if credit_id and method == "refund":
            _post_credit_note(odoo, credit_id)
        return {"method": method, "creditNoteId": credit_id}
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "refund_finance_failed",
            "Stock was restored, but the financial refund could not be completed. Contact hospital admin before retrying.",
        ) from error


def _create_partial_credit_note(
    odoo: dispensary.OdooReader,
    *,
    invoice: dict[str, Any],
    sale_name: str,
    lines: list[dict[str, Any]],
    reason: str,
) -> int:
    """lines: [{product_id, name, quantity, price_unit}]"""
    partner_id = many2one_id(invoice.get("partner_id"))
    journal_id = many2one_id(invoice.get("journal_id"))
    company_id = many2one_id(invoice.get("company_id"))
    if not partner_id:
        raise ApiError(502, "refund_finance_failed", "The bill partner could not be found for this refund.")
    invoice_lines = []
    for item in lines:
        qty = as_float(item.get("quantity"))
        price = as_float(item.get("price_unit"))
        if qty <= 0:
            continue
        invoice_lines.append(
            (
                0,
                0,
                {
                    "product_id": int(item["product_id"]),
                    "name": _text(item.get("name")) or "Pharmacy refund",
                    "quantity": qty,
                    "price_unit": price,
                },
            )
        )
    if not invoice_lines:
        raise ApiError(422, "nothing_to_refund", "There is no remaining amount to refund.")
    currency_id = many2one_id(invoice.get("currency_id"))
    values: dict[str, Any] = {
        "move_type": "out_refund",
        "partner_id": partner_id,
        "invoice_origin": sale_name or _text(invoice.get("invoice_origin")),
        "ref": reason[:200],
        "invoice_line_ids": invoice_lines,
    }
    if journal_id:
        values["journal_id"] = journal_id
    if company_id:
        values["company_id"] = company_id
    resolved = _staff_currency_id(odoo, currency_id)
    if resolved:
        values["currency_id"] = resolved
    try:
        credit_id = int(execute(odoo, "account.move", "create", [values]))
        _post_credit_note(odoo, credit_id)
        return credit_id
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "refund_finance_failed",
            "Stock was restored, but the financial refund could not be completed. Contact hospital admin before retrying.",
        ) from error


def _append_sale_note(odoo: dispensary.OdooReader, sale_id: int, extra: str) -> None:
    rows = odoo.read("sale.order", [sale_id], ["note"])
    note = _text((rows[0] if rows else {}).get("note"))
    next_note = f"{note}\n{extra}".strip() if note else extra
    try:
        execute(odoo, "sale.order", "write", [[sale_id], {"note": next_note}])
    except xmlrpc.client.Fault:
        pass


def _mark_line_refunds(
    odoo: dispensary.OdooReader,
    sale_id: int,
    line_qtys: dict[str, float],
    username: str,
    *,
    fully: bool,
) -> None:
    extras = [f"{LINE_REFUND_PREFIX}{line_id}:{qty:g}" for line_id, qty in line_qtys.items() if qty > 0]
    if fully:
        extras.append(f"{REFUND_MARKER}:{sale_id}:{username}")
    if extras:
        _append_sale_note(odoo, sale_id, "\n".join(extras))


def _sale_lines(odoo: dispensary.OdooReader, sale_id: int) -> list[dict[str, Any]]:
    return (
        execute(
            odoo,
            "sale.order.line",
            "search_read",
            [[("order_id", "=", sale_id)]],
            {
                "fields": [
                    "id",
                    "name",
                    "product_id",
                    "product_uom_qty",
                    "qty_delivered",
                    "price_unit",
                    "discount",
                    "external_order_id",
                ],
                "limit": 200,
            },
        )
        or []
    )


def _build_refundable(
    lines: list[dict[str, Any]],
    already: dict[str, float],
) -> list[dict[str, Any]]:
    rows = []
    for line in lines:
        line_id = str(line.get("id") or "")
        qty = as_float(line.get("product_uom_qty"))
        delivered = as_float(line.get("qty_delivered"))
        basis = delivered if delivered > 0 else qty
        refunded = already.get(line_id, 0.0)
        remaining = round(max(basis - refunded, 0.0), 4)
        unit = as_float(line.get("price_unit"))
        discount = as_float(line.get("discount"))
        unit_net = unit * (1.0 - (discount / 100.0))
        rows.append(
            {
                "line": line,
                "lineId": line_id,
                "productId": many2one_id(line.get("product_id")) or 0,
                "name": dispensary.many2one_name(line.get("product_id")) or _text(line.get("name")) or "Medication",
                "quantity": qty,
                "delivered": delivered,
                "alreadyRefunded": refunded,
                "refundable": remaining,
                "unitPrice": unit,
                "unitNet": unit_net,
            }
        )
    return rows


def refund_sale(sale_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Refund a full sale or a single line (optional partial quantity)."""
    user = require_pharmacist(cookie)
    username = _text(user.get("username")) or "pharmacy"
    sale_key = _text(sale_id)
    if not sale_key.isdigit():
        raise ApiError(422, "invalid_sale", "Choose a sale to refund.")
    sale_id_int = int(sale_key)

    line_id = _text(body.get("lineId") or body.get("saleLineId"))
    quantity_raw = body.get("quantity")
    mode = _text(body.get("mode") or ("line" if line_id else "full")).lower()
    if mode not in {"full", "line"}:
        raise ApiError(422, "invalid_mode", "Choose a full sale refund or a medicine refund.")

    request_id = _text(body.get("requestId"))
    if not request_id:
        request_id = f"refund:{sale_id_int}:{line_id or 'full'}:{quantity_raw or 'all'}"
    idem_key = f"pharmacy-refund:{request_id}"
    req_key = idem_key

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
        sales = odoo.read(
            "sale.order",
            [sale_id_int],
            [
                "name",
                "state",
                "partner_id",
                "invoice_ids",
                "origin",
                "shop_id",
                "amount_total",
                "note",
                "client_order_ref",
            ],
        )
        if not sales:
            raise ApiError(404, "sale_not_found", "That sale was not found.")
        sale = sales[0]
        if not dispensary.is_pharmacy_sale(sale) and not _text(sale.get("origin")).startswith(
            counter.SALE_PREFIX
        ):
            raise ApiError(404, "sale_not_found", "That pharmacy sale was not found.")

        invoice = _load_invoice(odoo, sale)
        note = _sale_note(sale)
        already = line_refunded_quantities(note)
        lines = _sale_lines(odoo, sale_id_int)
        refundable_rows = _build_refundable(lines, already)

        if _already_fully_refunded(sale, invoice) or all(row["refundable"] <= 0 for row in refundable_rows):
            detail = history.get_sales_history_item(sale_id_int, cookie)
            result = {
                "status": "ok",
                "duplicate": True,
                "refunded": True,
                "refundStatus": "Refunded",
                "saleId": str(sale_id_int),
                "message": "This sale was already refunded.",
                "sale": detail,
            }
            with IDEMPOTENCY_LOCK:
                IDEMPOTENCY[idem_key] = {"status": "done", "payload": result}
            return result

        picking = _outgoing_done_picking(odoo, sale_id_int)
        delivered_any = any(row["delivered"] > 0 or row["quantity"] > 0 for row in refundable_rows)
        if not picking and not delivered_any:
            raise ApiError(409, "sale_not_dispensed", "Only dispensed sales can be refunded.")

        selected: list[dict[str, Any]] = []
        if mode == "line":
            if not line_id:
                raise ApiError(422, "missing_line", "Choose which medicine to refund.")
            target = next((row for row in refundable_rows if row["lineId"] == line_id), None)
            if not target:
                raise ApiError(404, "line_not_found", "That medicine was not found on this sale.")
            if target["refundable"] <= 0:
                raise ApiError(409, "line_already_refunded", "This medicine has already been fully refunded.")
            if quantity_raw in (None, ""):
                qty = target["refundable"]
            else:
                qty = as_float(quantity_raw)
            if qty <= 0:
                raise ApiError(422, "invalid_quantity", "Enter how many units to refund.")
            if qty > target["refundable"] + 0.0001:
                raise ApiError(
                    422,
                    "quantity_too_high",
                    f"Only {target['refundable']:g} unit(s) can still be refunded for this medicine.",
                )
            selected = [{**target, "refundQty": round(qty, 4)}]
        else:
            selected = [
                {**row, "refundQty": row["refundable"]}
                for row in refundable_rows
                if row["refundable"] > 0
            ]
            if not selected:
                raise ApiError(409, "nothing_to_refund", "There is nothing left to refund on this sale.")

        # Prefer clean full invoice reverse when refunding everything and no prior line refunds.
        prior_partial = bool(already)
        refunding_all_remaining = mode == "full" and all(
            abs(row["refundQty"] - row["refundable"]) < 0.0001 for row in selected
        )
        use_full_invoice_reverse = (
            mode == "full"
            and not prior_partial
            and refunding_all_remaining
            and invoice
            and _text(invoice.get("state")).lower() == "posted"
        )

        return_picking_id = None
        if picking:
            moves = _moves_for_picking(odoo, int(picking["id"]))
            move_by_product: dict[int, dict[str, Any]] = {}
            for move in moves:
                product_id = many2one_id(move.get("product_id")) or 0
                if product_id and product_id not in move_by_product:
                    move_by_product[product_id] = move
            return_specs = []
            for row in selected:
                move = move_by_product.get(row["productId"])
                spec: dict[str, Any] = {
                    "product_id": row["productId"],
                    "quantity": row["refundQty"],
                }
                if move:
                    spec["move_id"] = int(move["id"])
                    uom_id = many2one_id(move.get("product_uom"))
                    if uom_id:
                        spec["uom_id"] = uom_id
                return_specs.append(spec)
            if return_specs:
                return_picking_id = _return_stock_lines(
                    odoo,
                    picking,
                    return_specs,
                    username,
                    REFUND_MARKER if use_full_invoice_reverse else f"{LINE_REFUND_PREFIX}partial",
                )

        refund_amount = round(sum(row["refundQty"] * row["unitNet"] for row in selected), 2)
        finance: dict[str, Any] = {"method": "none", "creditNoteId": None}

        if use_full_invoice_reverse and invoice:
            finance = _reverse_full_invoice(
                odoo,
                invoice,
                reason=f"Pharmacy refund of {sale.get('name') or sale_id_int}",
            )
        elif invoice and _text(invoice.get("state")).lower() == "posted":
            finance = {
                "method": "partial_credit",
                "creditNoteId": _create_partial_credit_note(
                    odoo,
                    invoice=invoice,
                    sale_name=_text(sale.get("name")),
                    lines=[
                        {
                            "product_id": row["productId"],
                            "name": row["name"],
                            "quantity": row["refundQty"],
                            "price_unit": row["unitNet"],
                        }
                        for row in selected
                    ],
                    reason=(
                        f"Pharmacy refund of {sale.get('name') or sale_id_int}"
                        + (f" · line {line_id}" if mode == "line" else "")
                    ),
                ),
            }
        elif invoice and _text(invoice.get("state")).lower() == "draft" and mode == "full" and not prior_partial:
            try:
                execute(odoo, "account.move", "button_cancel", [[int(invoice["id"])]])
                finance = {"method": "cancel_draft", "creditNoteId": None}
            except Exception:
                pass

        line_qtys = {row["lineId"]: row["refundQty"] for row in selected}
        # Recompute remaining after this refund.
        next_already = dict(already)
        for line_id_key, qty in line_qtys.items():
            next_already[line_id_key] = round(next_already.get(line_id_key, 0.0) + qty, 4)
        fully = True
        for row in refundable_rows:
            basis = row["delivered"] if row["delivered"] > 0 else row["quantity"]
            remaining = round(max(basis - next_already.get(row["lineId"], 0.0), 0.0), 4)
            if remaining > 0:
                fully = False
                break
        _mark_line_refunds(odoo, sale_id_int, line_qtys, username, fully=fully or use_full_invoice_reverse)

        detail = history.get_sales_history_item(sale_id_int, cookie)
        status_label = "Refunded" if fully or use_full_invoice_reverse else "Partially Refunded"
        if mode == "line":
            message = (
                f"Refunded {selected[0]['refundQty']:g} × {selected[0]['name']}. "
                f"Stock restored · {status_label}."
            )
        else:
            message = f"Sale {_text(sale.get('name')) or sale_id_int} refunded. Stock restored."

        result = {
            "status": "ok",
            "duplicate": False,
            "refunded": fully or use_full_invoice_reverse,
            "refundStatus": status_label,
            "saleId": str(sale_id_int),
            "saleName": _text(sale.get("name")),
            "refundAmount": refund_amount,
            "returnPickingId": return_picking_id,
            "financeMethod": finance.get("method"),
            "creditNoteId": finance.get("creditNoteId"),
            "mode": mode,
            "lines": [
                {
                    "lineId": row["lineId"],
                    "drugName": row["name"],
                    "quantity": row["refundQty"],
                    "amount": round(row["refundQty"] * row["unitNet"], 2),
                }
                for row in selected
            ],
            "message": message,
            "sale": detail,
        }
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[idem_key] = {"status": "done", "payload": result}
            IDEMPOTENCY[req_key] = {"status": "done", "payload": result}
        return result
    except Exception:
        with IDEMPOTENCY_LOCK:
            state = IDEMPOTENCY.get(idem_key) or {}
            if state.get("status") == "pending":
                IDEMPOTENCY.pop(idem_key, None)
        raise


def reset_for_tests() -> None:
    with IDEMPOTENCY_LOCK:
        IDEMPOTENCY.clear()


# Backwards-compatible alias used by older tests.
def _already_refunded(sale: dict[str, Any], invoice: dict[str, Any] | None) -> bool:
    return _already_fully_refunded(sale, invoice)
