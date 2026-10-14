"""Pharmacy Sales History — read-only view over existing Pharmacy Counter sales.

Odoo sale.order / invoices / pickings remain the source of truth. No separate
pharmacy ledger is created.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

import xmlrpc.client

import admin_period as periods
import pharmacy as dispensary
import pharmacy_sale as counter
from server import ApiError

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
MAX_POST_FILTER_SCAN = 2000
BATCH_SIZE = 50

SALE_FIELDS = [
    "name",
    "date_order",
    "partner_id",
    "invoice_ids",
    "origin",
    "shop_id",
    "amount_total",
    "create_uid",
    "create_date",
    "write_date",
    "care_setting",
    "state",
    "note",
    "client_order_ref",
]

LINE_FIELDS = [
    "id",
    "order_id",
    "name",
    "product_id",
    "product_uom_qty",
    "qty_delivered",
    "price_unit",
    "discount",
    "external_order_id",
    "external_id",
]

execute = dispensary.execute
odoo_reader = dispensary.odoo_reader
many2one_id = dispensary.many2one_id
many2one_name = dispensary.many2one_name
as_float = dispensary.as_float
require_pharmacist = dispensary.require_pharmacist


def _query_first(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key) or []
    return str(values[0] if values else default).strip()


def _parse_int(value: str, *, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(parsed, minimum)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def _normalize_payment_filter(value: str) -> str:
    text = value.strip().upper().replace("-", " ").replace("_", " ")
    aliases = {
        "PAID": "PAID",
        "UNPAID": "UNPAID",
        "PARTIAL": "PARTIALLY PAID",
        "PARTIALLY PAID": "PARTIALLY PAID",
        "PARTIALLY": "PARTIALLY PAID",
    }
    return aliases.get(text, "")


def _normalize_dispensing_filter(value: str) -> str:
    text = value.strip().upper().replace("-", " ").replace("_", " ")
    aliases = {
        "DISPENSED": "DISPENSED",
        "READY": "READY TO DISPENSE",
        "READY TO DISPENSE": "READY TO DISPENSE",
        "PENDING": "PENDING",
        "PARTIAL": "PARTIALLY DISPENSED",
        "PARTIALLY DISPENSED": "PARTIALLY DISPENSED",
        "PARTIALLY": "PARTIALLY DISPENSED",
        "STOPPED": "STOPPED",
        "UNPAID": "UNPAID",
        "PAID": "PAID",
    }
    return aliases.get(text, "")


def _normalize_buyer_type(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"registered", "registered_patient", "patient"}:
        return "registered"
    if text in {"other", "other_buyer", "walkin", "walk_in"}:
        return "other"
    return ""


def _normalize_transaction_type(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"direct", "direct_sale", "sale"}:
        return "direct_sale"
    if text in {"prescription", "rx", "clinical"}:
        return "prescription"
    return ""


def _normalize_care_setting(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"inpatient", "ipd", "in_patient"}:
        return "inpatient"
    if text in {"outpatient", "opd", "out_patient"}:
        return "outpatient"
    return ""


def _window_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    period = _query_first(query, "period")
    start = _query_first(query, "from") or _query_first(query, "start")
    end = _query_first(query, "to") or _query_first(query, "end")
    if start and end and not period:
        period = "custom"
    if not period and not start and not end:
        period = "this_month"
    return periods.resolve_period(period or "this_month", start=start, end=end)


def _odoo_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _care_setting_label(sale: dict[str, Any]) -> str:
    raw = sale.get("care_setting")
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        text = str(raw[1] or "").strip().lower()
    else:
        text = str(raw or "").strip().lower()
    if text in {"ipd", "inpatient", "in-patient"}:
        return "inpatient"
    if text in {"opd", "outpatient", "out-patient"}:
        return "outpatient"
    return text or ""


def _transaction_type(sale: dict[str, Any], lines: list[dict[str, Any]]) -> str:
    origin = str(sale.get("origin") or "")
    if origin.startswith(counter.SALE_PREFIX):
        return "direct_sale"
    for line in lines:
        external = str(line.get("external_order_id") or "")
        if counter.is_direct_sale_key(external):
            return "direct_sale"
    for line in lines:
        external = str(line.get("external_order_id") or "")
        if dispensary.is_pharmacy_external_id(external):
            return "prescription"
    if origin and not origin.startswith(counter.SALE_PREFIX):
        return "prescription"
    return "direct_sale"


def _buyer_type(partner: dict[str, Any]) -> tuple[str, str]:
    ref = str(partner.get("ref") or "")
    patient_uuid = str(partner.get("uuid") or "")
    if ref.startswith(counter.WALKIN_REF_PREFIX):
        return "other", ""
    if patient_uuid:
        return "registered", patient_uuid
    return "other", ""


def _prescription_refs(lines: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for line in lines:
        external = str(line.get("external_order_id") or "")
        if not dispensary.is_pharmacy_external_id(external):
            continue
        if external in seen:
            continue
        seen.add(external)
        refs.append(external)
    return refs


def _money_from_invoice(invoice: dict[str, Any] | None, sale_total: float) -> tuple[float, float, float]:
    if invoice:
        total = as_float(invoice.get("amount_total"))
        if total <= 0:
            total = sale_total
        residual = as_float(invoice.get("amount_residual"))
    else:
        total = sale_total
        residual = sale_total
    paid = max(total - residual, 0.0)
    return round(total, 2), round(paid, 2), round(residual, 2)


def _uid_name(value: Any) -> str:
    return many2one_name(value) if value else ""


def _history_domain(
    shop_id: int,
    window: dict[str, Any],
    *,
    q: str,
    transaction_type: str,
    buyer_type: str,
    pharmacist: str,
    sale_name: str,
    patient_id: str,
) -> list[Any]:
    domain: list[Any] = [
        ("shop_id", "=", shop_id),
        ("state", "in", ["sale", "done"]),
        ("date_order", ">=", _odoo_datetime(window["utcStartNaive"])),
        ("date_order", "<", _odoo_datetime(window["utcEndNaive"])),
    ]
    if sale_name:
        domain.append(("name", "ilike", sale_name))
    if patient_id:
        domain.append(("partner_id.ref", "ilike", patient_id))
    if transaction_type == "direct_sale":
        domain.append(("origin", "like", f"{counter.SALE_PREFIX}%"))
    elif transaction_type == "prescription":
        domain.append("!")
        domain.append(("origin", "like", f"{counter.SALE_PREFIX}%"))
    if buyer_type == "other":
        domain.append("|")
        domain.append(("partner_id.ref", "like", f"{counter.WALKIN_REF_PREFIX}%"))
        domain.append(("partner_id.uuid", "=", False))
    elif buyer_type == "registered":
        domain.append(("partner_id.uuid", "!=", False))
        domain.append("!")
        domain.append(("partner_id.ref", "like", f"{counter.WALKIN_REF_PREFIX}%"))
    if pharmacist:
        domain.append(("create_uid.name", "ilike", pharmacist))
    if q:
        domain.extend(
            [
                "|",
                "|",
                "|",
                ("name", "ilike", q),
                ("partner_id.name", "ilike", q),
                ("partner_id.ref", "ilike", q),
                ("origin", "ilike", q),
            ]
        )
    return domain


def _load_lines(odoo: dispensary.OdooReader, sale_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not sale_ids:
        return {}
    rows = execute(
        odoo,
        "sale.order.line",
        "search_read",
        [[("order_id", "in", sale_ids)]],
        {"fields": LINE_FIELDS, "limit": max(len(sale_ids) * 40, 200)},
    )
    grouped: dict[int, list[dict[str, Any]]] = {sale_id: [] for sale_id in sale_ids}
    for row in rows or []:
        sale_id = many2one_id(row.get("order_id"))
        if sale_id in grouped:
            grouped[sale_id].append(row)
    return grouped


def _load_partners(odoo: dispensary.OdooReader, sales: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    partner_ids = []
    seen: set[int] = set()
    for sale in sales:
        partner_id = many2one_id(sale.get("partner_id"))
        if partner_id and partner_id not in seen:
            seen.add(partner_id)
            partner_ids.append(partner_id)
    if not partner_ids:
        return {}
    rows = odoo.read("res.partner", partner_ids, ["id", "name", "ref", "uuid"])
    return {int(row["id"]): row for row in rows}


def _load_pickings_audit(
    odoo: dispensary.OdooReader, sale_ids: list[int]
) -> dict[int, dict[str, Any] | None]:
    if not sale_ids:
        return {}
    rows = execute(
        odoo,
        "stock.picking",
        "search_read",
        [[("sale_id", "in", sale_ids)]],
        {
            "fields": ["name", "state", "sale_id", "picking_type_id", "origin", "create_uid", "date_done"],
            "limit": max(len(sale_ids) * 4, 50),
        },
    )
    type_ids = [many2one_id(row.get("picking_type_id")) for row in (rows or [])]
    type_ids = [item for item in type_ids if item]
    types = {
        int(row["id"]): row.get("code") or ""
        for row in (odoo.read("stock.picking.type", type_ids, ["code"]) if type_ids else [])
    }
    grouped: dict[int, list[dict[str, Any]]] = {sale_id: [] for sale_id in sale_ids}
    for row in rows or []:
        sale_id = many2one_id(row.get("sale_id"))
        code = types.get(many2one_id(row.get("picking_type_id")) or 0, "")
        if sale_id in grouped and (code == "outgoing" or str(row.get("name") or "").startswith("WH/OUT")):
            grouped[sale_id].append(row)
    chosen: dict[int, dict[str, Any] | None] = {}
    for sale_id, items in grouped.items():
        if not items:
            chosen[sale_id] = None
            continue
        done = [row for row in items if row.get("state") == "done"]
        open_rows = [row for row in items if row.get("state") != "done"]
        chosen[sale_id] = (done[0] if done else None) or (open_rows[0] if open_rows else items[0])
    return chosen


def _line_refund_map(note: str) -> dict[str, float]:
    import pharmacy_refund as refunds

    return refunds.line_refunded_quantities(note)


def _refund_status_for(
    *,
    note: str,
    invoice: dict[str, Any] | None,
    lines: list[dict[str, Any]],
) -> tuple[str, bool, bool]:
    """Returns (refundStatus, refundedFully, hasRemainingRefundable)."""
    import pharmacy_refund as refunds

    payment = str((invoice or {}).get("payment_state") or "").lower()
    already = _line_refund_map(note)
    remaining = 0.0
    for line in lines:
        line_id = str(line.get("id") or "")
        basis = as_float(line.get("qty_delivered")) or as_float(line.get("product_uom_qty"))
        remaining += max(basis - already.get(line_id, 0.0), 0.0)

    if payment == "reversed" or (refunds.REFUND_MARKER in note and remaining <= 0.0001):
        return "Refunded", True, False
    if remaining <= 0.0001 and (already or refunds.REFUND_MARKER in note):
        return "Refunded", True, False
    if already or (refunds.REFUND_MARKER in note and remaining > 0):
        return "Partially Refunded", False, remaining > 0.0001
    return "", False, remaining > 0.0001


def _serialize_row(
    *,
    sale: dict[str, Any],
    lines: list[dict[str, Any]],
    invoice: dict[str, Any] | None,
    picking: dict[str, Any] | None,
    partner: dict[str, Any],
) -> dict[str, Any]:
    buyer_type, patient_uuid = _buyer_type(partner)
    payment = counter._payment_label(invoice)
    dispensing = counter._dispensing_label(lines, picking)
    sale_total = as_float(sale.get("amount_total"))
    amount_total, amount_paid, amount_residual = _money_from_invoice(invoice, sale_total)
    quantity_total = sum(as_float(line.get("product_uom_qty")) for line in lines)
    prescription_refs = _prescription_refs(lines)
    care = _care_setting_label(sale)
    dispensed_by = ""
    dispensed_at = ""
    if picking and str(picking.get("state") or "") == "done":
        dispensed_by = _uid_name(picking.get("create_uid"))
        dispensed_at = str(picking.get("date_done") or "")
    note = str(sale.get("note") or sale.get("client_order_ref") or "")
    refund_status, refunded_fully, has_remaining = _refund_status_for(
        note=note, invoice=invoice, lines=lines
    )
    dispensed = (
        (picking is not None and str(picking.get("state") or "") == "done")
        or sum(as_float(line.get("qty_delivered")) for line in lines) > 0
        or dispensing == "DISPENSED"
    )
    can_refund = not refunded_fully and dispensed and has_remaining
    transaction_type = _transaction_type(sale, lines)
    can_delete_prescription = (
        transaction_type == "prescription"
        and bool(prescription_refs)
        and payment in {"UNPAID", "PAID"}
        and not dispensed
        and dispensing not in {"DISPENSED", "STOPPED"}
        and not refunded_fully
    )
    display_status = refund_status or dispensing
    return {
        "saleId": str(sale.get("id") or ""),
        "saleName": str(sale.get("name") or ""),
        "dateOrder": str(sale.get("date_order") or ""),
        "transactionType": transaction_type,
        "buyerType": buyer_type,
        "buyerName": str(partner.get("name") or many2one_name(sale.get("partner_id")) or ""),
        "mrn": str(partner.get("ref") or "") if buyer_type == "registered" else "",
        "patientUuid": patient_uuid,
        "paymentStatus": payment,
        "dispensingStatus": display_status if refund_status else dispensing,
        "refundStatus": refund_status or ("Refunded" if refunded_fully else ""),
        "refunded": refunded_fully,
        "partiallyRefunded": refund_status == "Partially Refunded",
        "canRefund": can_refund,
        "canDeletePrescription": can_delete_prescription,
        "amountTotal": amount_total,
        "amountPaid": amount_paid,
        "amountResidual": amount_residual,
        "invoiceName": str((invoice or {}).get("name") or ""),
        "lineCount": len(lines),
        "quantityTotal": round(quantity_total, 4),
        "prescriptionRefs": prescription_refs,
        "careSetting": care,
        "admissionReference": "",
        "createdBy": _uid_name(sale.get("create_uid")),
        "dispensedBy": dispensed_by,
        "dispensedAt": dispensed_at,
        "processedBy": dispensed_by or _uid_name(sale.get("create_uid")),
    }


def _hydrate_sales(odoo: dispensary.OdooReader, sales: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sales:
        return []
    sale_ids = [int(sale["id"]) for sale in sales]
    lines_by_sale = _load_lines(odoo, sale_ids)
    invoices = dispensary._queue_invoices(odoo, sales)
    pickings = _load_pickings_audit(odoo, sale_ids)
    partners = _load_partners(odoo, sales)
    rows = []
    for sale in sales:
        sale_id = int(sale["id"])
        partner_id = many2one_id(sale.get("partner_id")) or 0
        partner = partners.get(partner_id) or {
            "name": many2one_name(sale.get("partner_id")),
            "ref": "",
            "uuid": "",
        }
        rows.append(
            _serialize_row(
                sale=sale,
                lines=lines_by_sale.get(sale_id, []),
                invoice=invoices.get(sale_id),
                picking=pickings.get(sale_id),
                partner=partner,
            )
        )
    return rows


def _matches_post_filters(
    row: dict[str, Any],
    *,
    payment_status: str,
    dispensing_status: str,
    care_setting: str,
) -> bool:
    if payment_status and row.get("paymentStatus") != payment_status:
        return False
    if dispensing_status and row.get("dispensingStatus") != dispensing_status:
        return False
    if care_setting and row.get("careSetting") != care_setting:
        return False
    return True


def _search_sales(
    odoo: dispensary.OdooReader,
    domain: list[Any],
    *,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    kwargs = {
        "fields": SALE_FIELDS,
        "offset": offset,
        "limit": limit,
        "order": "date_order desc, id desc",
    }
    try:
        return execute(odoo, "sale.order", "search_read", [domain], kwargs) or []
    except xmlrpc.client.Fault:
        safe_fields = [field for field in SALE_FIELDS if field != "care_setting"]
        kwargs["fields"] = safe_fields
        return execute(odoo, "sale.order", "search_read", [domain], kwargs) or []


def _count_sales(odoo: dispensary.OdooReader, domain: list[Any]) -> int:
    return int(execute(odoo, "sale.order", "search_count", [domain]) or 0)


def list_sales_history(cookie: str, raw_path: str = "") -> dict[str, Any]:
    require_pharmacist(cookie)
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "", keep_blank_values=True)
    window = _window_from_query(query)
    limit = _parse_int(_query_first(query, "limit"), default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
    offset = _parse_int(_query_first(query, "offset"), default=0, minimum=0)
    q = _query_first(query, "q")
    payment_status = _normalize_payment_filter(_query_first(query, "paymentStatus"))
    dispensing_status = _normalize_dispensing_filter(_query_first(query, "dispensingStatus"))
    buyer_type = _normalize_buyer_type(_query_first(query, "buyerType"))
    transaction_type = _normalize_transaction_type(_query_first(query, "transactionType"))
    care_setting = _normalize_care_setting(
        _query_first(query, "careSetting") or _query_first(query, "visitType")
    )
    pharmacist = _query_first(query, "pharmacist")
    sale_name = _query_first(query, "transactionId") or _query_first(query, "saleName")
    patient_id = _query_first(query, "patientId") or _query_first(query, "mrn")

    odoo = odoo_reader()
    shop = counter.find_pharmacy_shop(odoo)
    domain = _history_domain(
        int(shop["id"]),
        window,
        q=q,
        transaction_type=transaction_type,
        buyer_type=buyer_type,
        pharmacist=pharmacist,
        sale_name=sale_name,
        patient_id=patient_id,
    )
    needs_post = bool(payment_status or dispensing_status or care_setting)

    if not needs_post:
        total = _count_sales(odoo, domain)
        sales = _search_sales(odoo, domain, offset=offset, limit=limit)
        items = _hydrate_sales(odoo, sales)
        return {
            "status": "ok",
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "period": {
                "period": window["period"],
                "label": window["label"],
                "timezone": window["timezone"],
                "startDate": window["startDate"],
                "endDate": window["endDate"],
            },
        }

    matched: list[dict[str, Any]] = []
    total_matched = 0
    scan_offset = 0
    truncated = False
    while scan_offset < MAX_POST_FILTER_SCAN:
        batch = _search_sales(odoo, domain, offset=scan_offset, limit=BATCH_SIZE)
        if not batch:
            break
        for row in _hydrate_sales(odoo, batch):
            if not _matches_post_filters(
                row,
                payment_status=payment_status,
                dispensing_status=dispensing_status,
                care_setting=care_setting,
            ):
                continue
            if total_matched >= offset and len(matched) < limit:
                matched.append(row)
            total_matched += 1
        scan_offset += len(batch)
        if len(batch) < BATCH_SIZE:
            break
    else:
        truncated = True

    return {
        "status": "ok",
        "items": matched,
        "total": total_matched,
        "offset": offset,
        "limit": limit,
        "truncated": truncated,
        "period": {
            "period": window["period"],
            "label": window["label"],
            "timezone": window["timezone"],
            "startDate": window["startDate"],
            "endDate": window["endDate"],
        },
    }


def get_sales_history_item(sale_id: int, cookie: str) -> dict[str, Any]:
    require_pharmacist(cookie)
    odoo = odoo_reader()
    try:
        sales = odoo.read("sale.order", [sale_id], SALE_FIELDS)
    except Exception:
        sales = execute(
            odoo,
            "sale.order",
            "read",
            [[sale_id], [field for field in SALE_FIELDS if field != "care_setting"]],
        )
    if not sales:
        raise ApiError(404, "sale_not_found", "This pharmacy sale was not found.")
    sale = sales[0]
    if not dispensary.is_pharmacy_sale(sale):
        raise ApiError(404, "sale_not_found", "This pharmacy sale was not found.")

    lines = _load_lines(odoo, [sale_id]).get(sale_id, [])
    invoice = dispensary.related_invoice(odoo, sale)
    if invoice and "amount_total" not in invoice:
        fresh = odoo.read(
            "account.move",
            [int(invoice["id"])],
            ["name", "state", "payment_state", "amount_residual", "amount_total", "move_type", "partner_id"],
        )
        invoice = fresh[0] if fresh else invoice
    pickings = _load_pickings_audit(odoo, [sale_id])
    picking = pickings.get(sale_id)
    partners = _load_partners(odoo, [sale])
    partner_id = many2one_id(sale.get("partner_id")) or 0
    partner = partners.get(partner_id) or {"name": "", "ref": "", "uuid": ""}
    summary = _serialize_row(
        sale=sale,
        lines=lines,
        invoice=invoice,
        picking=picking,
        partner=partner,
    )
    items = []
    already = _line_refund_map(str(sale.get("note") or sale.get("client_order_ref") or ""))
    for line in lines:
        qty = as_float(line.get("product_uom_qty"))
        unit = as_float(line.get("price_unit"))
        discount = as_float(line.get("discount"))
        line_total = qty * unit * (1.0 - (discount / 100.0))
        delivered = as_float(line.get("qty_delivered"))
        basis = delivered if delivered > 0 else qty
        line_id = str(line.get("id") or "")
        refunded_qty = already.get(line_id, 0.0)
        refundable = round(max(basis - refunded_qty, 0.0), 4)
        unit_net = unit * (1.0 - (discount / 100.0))
        items.append(
            {
                "lineId": line_id,
                "externalOrderId": str(line.get("external_order_id") or ""),
                "drugName": many2one_name(line.get("product_id")) or str(line.get("name") or "Medication"),
                "quantity": qty,
                "unitPrice": unit,
                "discount": discount,
                "lineTotal": round(line_total, 2),
                "delivered": delivered,
                "quantityRefunded": refunded_qty,
                "quantityRefundable": refundable,
                "canRefund": bool(summary.get("canRefund")) and refundable > 0,
                "refundAmountPerUnit": round(unit_net, 2),
            }
        )
    return {
        "status": "ok",
        **summary,
        "createDate": str(sale.get("create_date") or ""),
        "writeDate": str(sale.get("write_date") or ""),
        "lines": items,
    }
