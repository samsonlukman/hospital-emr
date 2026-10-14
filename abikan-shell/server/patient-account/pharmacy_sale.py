"""Direct pharmacy counter sales (no clinical prescription required).

Odoo remains the financial and stock source of truth. OpenMRS patients are
only linked when the buyer is a registered patient. Walk-in buyers use an
Odoo partner only — no fake patient record is created.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

import xmlrpc.client

import pharmacy as dispensary
import server as core
from server import ApiError

SALE_PREFIX = "pharmacy-sale:"
WALKIN_REF_PREFIX = "PHARM-WALKIN:"
SHOP_NAME = "Pharmacy Counter"

IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}

execute = dispensary.execute
odoo_reader = dispensary.odoo_reader
many2one_id = dispensary.many2one_id
many2one_name = dispensary.many2one_name
as_float = dispensary.as_float
find_partner = dispensary.find_partner
require_pharmacist = dispensary.require_pharmacist


def sale_external_key(token: str, line_index: int) -> str:
    return f"{SALE_PREFIX}{token}:{line_index}"


def is_direct_sale_key(value: str) -> bool:
    return str(value or "").startswith(SALE_PREFIX)


def find_pharmacy_shop(odoo: dispensary.OdooReader) -> dict[str, Any]:
    rows = odoo.search_read(
        "sale.shop",
        [("name", "=", SHOP_NAME)],
        ["id", "name", "warehouse_id", "pricelist_id", "payment_default_id"],
        limit=1,
    )
    if not rows:
        rows = odoo.search_read(
            "sale.shop",
            [("name", "ilike", "Pharmacy")],
            ["id", "name", "warehouse_id", "pricelist_id", "payment_default_id"],
            limit=1,
        )
    if not rows:
        raise ApiError(502, "shop_missing", "The pharmacy counter is not configured yet.")
    return rows[0]


def _payment_label(invoice: dict[str, Any] | None) -> str:
    if not invoice:
        return "UNPAID"
    payment_state = invoice.get("payment_state")
    residual = as_float(invoice.get("amount_residual"))
    fully_paid = payment_state in {"paid", "in_payment"} and residual <= 0.009
    if fully_paid:
        return "PAID"
    if residual > 0.009 and (
        str(payment_state or "") == "partial"
        or as_float(invoice.get("amount_total")) > residual + 0.009
    ):
        return "PARTIALLY PAID"
    return "UNPAID"


def _dispensing_label(
    lines: list[dict[str, Any]],
    picking: dict[str, Any] | None,
) -> str:
    if not lines:
        return "UNPAID"
    all_done = True
    any_delivered = False
    for line in lines:
        requested = as_float(line.get("product_uom_qty"))
        delivered = as_float(line.get("qty_delivered"))
        if delivered + 0.0001 >= requested and requested > 0:
            any_delivered = True
        else:
            all_done = False
    picking_state = str((picking or {}).get("state") or "")
    if all_done or picking_state == "done":
        return "DISPENSED"
    if any_delivered:
        return "PARTIALLY DISPENSED"
    if picking and picking_state not in {"cancel", "cancelled"}:
        return "READY TO DISPENSE"
    return "PENDING"


def _load_openmrs_patient(patient_uuid: str, cookie: str) -> dict[str, str]:
    return core.load_openmrs_patient(patient_uuid, cookie)


def _ensure_walkin_partner(
    odoo: dispensary.OdooReader,
    *,
    name: str,
    phone: str,
    token: str,
) -> dict[str, Any]:
    clean_name = " ".join(name.split()).strip()
    if len(clean_name) < 2:
        raise ApiError(422, "buyer_required", "Enter the buyer's name.")
    ref = f"{WALKIN_REF_PREFIX}{token}"
    existing = odoo.search_read(
        "res.partner",
        [("ref", "=", ref)],
        ["id", "name", "ref", "uuid", "phone"],
        limit=1,
    )
    if existing:
        row = existing[0]
        if not str(row.get("uuid") or "").strip():
            link = f"pharmacy:{token}"
            execute(odoo, "res.partner", "write", [[int(row["id"])], {"uuid": link}])
            row["uuid"] = link
        return row
    values: dict[str, Any] = {
        "name": clean_name,
        "ref": ref,
        "uuid": f"pharmacy:{token}",
        "customer_rank": 1,
        "company_type": "person",
    }
    if phone.strip():
        values["phone"] = phone.strip()
    partner_id = int(execute(odoo, "res.partner", "create", [values]))
    rows = odoo.read("res.partner", [partner_id], ["id", "name", "ref", "uuid", "phone"])
    return rows[0]


def _resolve_product(
    odoo: dispensary.OdooReader,
    drug_uuid: str,
) -> dict[str, Any]:
    key = (drug_uuid or "").strip()
    if not key:
        raise ApiError(422, "medicine_required", "Choose a medicine for each line.")
    found = dispensary.find_pharmacy_products(odoo, [key])
    product = found.get(key)
    if not product or not product.get("id"):
        raise ApiError(
            409,
            "missing_mapping",
            "That medicine is not available in the pharmacy catalogue yet.",
        )
    if as_float(product.get("list_price")) <= 0:
        raise ApiError(
            409,
            "missing_price",
            "Set a selling price for this medicine before selling it.",
        )
    return product


def _parse_lines(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("lines")
    if not isinstance(raw, list) or not raw:
        raise ApiError(422, "lines_required", "Add at least one medicine to the sale.")
    lines: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        drug_uuid = str(item.get("drugUuid") or item.get("id") or "").strip()
        quantity = as_float(item.get("quantity"))
        if quantity <= 0:
            raise ApiError(422, "invalid_quantity", "Enter a quantity greater than zero.")
        lines.append(
            {
                "index": index,
                "drugUuid": drug_uuid,
                "quantity": quantity,
                "dose": str(item.get("dose") or "").strip(),
                "doseUnits": str(item.get("doseUnits") or "").strip(),
                "frequency": str(item.get("frequency") or "").strip(),
                "duration": str(item.get("duration") or "").strip(),
                "route": str(item.get("route") or "").strip(),
                "instructions": str(item.get("instructions") or "").strip(),
            }
        )
    if not lines:
        raise ApiError(422, "lines_required", "Add at least one medicine to the sale.")
    return lines


def _serialize_sale(
    *,
    sale: dict[str, Any],
    lines: list[dict[str, Any]],
    invoice: dict[str, Any] | None,
    picking: dict[str, Any] | None,
    partner: dict[str, Any],
    stock: dict[int, float],
    buyer_type: str,
    patient_uuid: str,
    recorded_by: str = "",
) -> dict[str, Any]:
    payment = _payment_label(invoice)
    dispensing = _dispensing_label(lines, picking)
    picking_state = str((picking or {}).get("state") or "")
    can_dispense = dispensing == "READY TO DISPENSE" and bool(picking) and picking_state not in {
        "cancel",
        "cancelled",
        "done",
    }
    reason = None
    if dispensing == "DISPENSED":
        reason = "This sale has already been dispensed."
        can_dispense = False
    elif not picking or picking_state in {"cancel", "cancelled"}:
        reason = "This sale is not ready to dispense yet."
        can_dispense = False
    else:
        for line in lines:
            product_id = many2one_id(line.get("product_id")) or 0
            requested = as_float(line.get("product_uom_qty"))
            if stock.get(product_id, 0.0) + 0.0001 < requested:
                reason = "Not enough stock to dispense this medication."
                can_dispense = False
                break
    items = []
    for line in lines:
        product_id = many2one_id(line.get("product_id")) or 0
        items.append(
            {
                "lineId": str(line.get("id") or ""),
                "externalOrderId": str(line.get("external_order_id") or ""),
                "drugName": many2one_name(line.get("product_id")) or str(line.get("name") or "Medication"),
                "quantity": as_float(line.get("product_uom_qty")),
                "unitPrice": as_float(line.get("price_unit")),
                "delivered": as_float(line.get("qty_delivered")),
                "stockOnHand": stock.get(product_id, 0.0),
                "instructions": str(line.get("name") or ""),
            }
        )
    total = sum(as_float(item.get("unitPrice")) * as_float(item.get("quantity")) for item in items)
    return {
        "status": "ok",
        "saleId": str(sale.get("id") or ""),
        "saleName": str(sale.get("name") or ""),
        "saleToken": str(sale.get("origin") or "").removeprefix(SALE_PREFIX) if str(sale.get("origin") or "").startswith(SALE_PREFIX) else "",
        "buyerType": buyer_type,
        "patientUuid": patient_uuid,
        "buyerName": str(partner.get("name") or ""),
        "mrn": str(partner.get("ref") or "") if buyer_type == "registered" else "",
        "paymentStatus": payment,
        "dispensingStatus": dispensing,
        "canDispense": can_dispense,
        "blockReason": reason,
        "amountTotal": round(total, 2),
        "invoiceName": str((invoice or {}).get("name") or ""),
        "lines": items,
        "recordedBy": recorded_by,
        "transactionType": "direct_sale",
    }


def assemble_sale(sale_id: int, cookie: str) -> dict[str, Any]:
    require_pharmacist(cookie)
    odoo = odoo_reader()
    sales = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id", "amount_total"],
    )
    if not sales:
        raise ApiError(404, "sale_not_found", "This pharmacy sale was not found.")
    sale = sales[0]
    if not dispensary.is_pharmacy_sale(sale) and not str(sale.get("origin") or "").startswith(SALE_PREFIX):
        raise ApiError(404, "sale_not_found", "This pharmacy sale was not found.")
    lines = odoo.search_read(
        "sale.order.line",
        [("order_id", "=", sale_id)],
        [
            "id",
            "name",
            "product_id",
            "product_uom_qty",
            "qty_delivered",
            "price_unit",
            "external_order_id",
            "external_id",
        ],
    )
    invoice = dispensary.related_invoice(odoo, sale)
    pickings = dispensary.outgoing_pickings(odoo, sale_id)
    picking = dispensary.choose_picking(pickings)
    partner_id = many2one_id(sale.get("partner_id")) or 0
    partners = odoo.read("res.partner", [partner_id], ["id", "name", "ref", "uuid"]) if partner_id else []
    partner = partners[0] if partners else {"name": "", "ref": "", "uuid": ""}
    location_id = dispensary.stock_location_id(odoo, sale)
    stock = dispensary.on_hand_quantities(
        odoo,
        [many2one_id(line.get("product_id")) or 0 for line in lines],
        location_id,
    )
    patient_uuid = str(partner.get("uuid") or "")
    buyer_type = "registered" if patient_uuid else "other"
    ref = str(partner.get("ref") or "")
    if ref.startswith(WALKIN_REF_PREFIX):
        buyer_type = "other"
        patient_uuid = ""
    return _serialize_sale(
        sale=sale,
        lines=lines,
        invoice=invoice,
        picking=picking,
        partner=partner,
        stock=stock,
        buyer_type=buyer_type,
        patient_uuid=patient_uuid,
    )


def list_sales(cookie: str) -> dict[str, Any]:
    require_pharmacist(cookie)
    odoo = odoo_reader()
    lines = execute(
        odoo,
        "sale.order.line",
        "search_read",
        [[("external_order_id", "like", f"{SALE_PREFIX}%")]],
        {
            "fields": ["order_id", "external_order_id"],
            "limit": 200,
            "order": "id desc",
        },
    )
    sale_ids: list[int] = []
    seen: set[int] = set()
    for line in lines or []:
        sale_id = many2one_id(line.get("order_id"))
        if sale_id and sale_id not in seen:
            seen.add(sale_id)
            sale_ids.append(sale_id)
    sales = []
    for sale_id in sale_ids[:50]:
        try:
            sales.append(assemble_sale(sale_id, cookie))
        except ApiError:
            continue
    ready = [row for row in sales if row.get("dispensingStatus") == "READY TO DISPENSE"]
    other = [row for row in sales if row.get("dispensingStatus") != "READY TO DISPENSE"]
    return {"status": "ok", "ready": ready, "other": other, "sales": sales}


def create_direct_sale(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_pharmacist(cookie)
    request_id = str(body.get("requestId") or "").strip() or str(uuid.uuid4())
    buyer_type = str(body.get("buyerType") or "").strip().lower()
    if buyer_type in {"registered", "patient", "registered_patient"}:
        buyer_type = "registered"
    elif buyer_type in {"other", "walkin", "other_buyer", "unregistered"}:
        buyer_type = "other"
    else:
        raise ApiError(422, "buyer_type_required", "Choose Registered Patient or Other Buyer.")
    lines_in = _parse_lines(body)
    dispense_now = bool(body.get("dispense", True))
    idem_key = f"pharmacy-sale-create:{request_id}"
    with IDEMPOTENCY_LOCK:
        state = IDEMPOTENCY.get(idem_key) or {}
        if state.get("status") == "pending":
            raise ApiError(409, "sale_in_progress", "This pharmacy sale is already being created.")
        if state.get("status") == "done" and state.get("saleId"):
            payload = assemble_sale(int(state["saleId"]), cookie)
            payload["alreadyCreated"] = True
            return payload
        IDEMPOTENCY[idem_key] = {"status": "pending"}
    try:
        odoo = odoo_reader()
        shop = find_pharmacy_shop(odoo)
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = many2one_id(shop.get("pricelist_id")) or 1
        token = request_id.replace(":", "")[:36]
        patient_uuid = ""
        if buyer_type == "registered":
            patient_uuid = str(body.get("patientUuid") or "").strip()
            if not patient_uuid:
                raise ApiError(422, "patient_required", "Select a registered patient.")
            patient = _load_openmrs_patient(patient_uuid, cookie)
            partner = dispensary.billing_partner(odoo, patient)
            if not partner:
                raise ApiError(
                    409,
                    "account_not_found",
                    "This patient has no financial account yet. Try again in a moment.",
                )
        else:
            partner = _ensure_walkin_partner(
                odoo,
                name=str(body.get("buyerName") or ""),
                phone=str(body.get("buyerPhone") or ""),
                token=token,
            )
        order_lines = []
        location_id = dispensary.stock_location_id(odoo)
        for item in lines_in:
            product = _resolve_product(odoo, item["drugUuid"])
            product_id = int(product["id"])
            on_hand = dispensary.on_hand_quantity(odoo, product_id, location_id)
            if on_hand + 0.0001 < item["quantity"]:
                raise ApiError(
                    409,
                    "insufficient_stock",
                    f"Not enough stock for {product.get('name') or 'this medicine'}.",
                )
            label_parts = [str(product.get("name") or "Medication")]
            for part in (
                item["dose"],
                item["doseUnits"],
                item["frequency"],
                item["duration"],
                item["route"],
                item["instructions"],
            ):
                if part:
                    label_parts.append(part)
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product_id,
                        "name": " · ".join(label_parts),
                        "product_uom_qty": item["quantity"],
                        "price_unit": as_float(product.get("list_price")),
                        "discount": 0,
                        "tax_id": [(6, 0, [])],
                        "external_order_id": sale_external_key(token, item["index"]),
                        "external_id": patient_uuid or f"walkin:{token}",
                    },
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
                        "shop_id": shop_id,
                        "warehouse_id": warehouse_id,
                        "pricelist_id": pricelist_id,
                        "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                        "origin": f"{SALE_PREFIX}{token}",
                        "care_setting": "opd",
                        "order_line": order_lines,
                    }
                ],
            )
        )
        sale_rows = odoo.read(
            "sale.order",
            [sale_id],
            ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id", "order_line"],
        )
        sale = sale_rows[0]
        line_ids = [int(item) for item in (sale.get("order_line") or [])]
        if line_ids:
            try:
                execute(odoo, "sale.order.line", "write", [line_ids, {"tax_id": [(6, 0, [])]}])
            except xmlrpc.client.Fault:
                pass
        invoice = dispensary.ensure_pharmacy_invoice(odoo, sale)
        if not invoice:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The pharmacy bill could not be created. Refresh and try again.",
            )
        dispense_error = ""
        if dispense_now:
            try:
                _dispense_sale_id(odoo, sale_id)
            except ApiError as error:
                # Charge already exists — return the sale so staff can retry dispense.
                dispense_error = error.message
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[idem_key] = {"status": "done", "saleId": sale_id}
        payload = assemble_sale(sale_id, cookie)
        payload["alreadyCreated"] = False
        payload["recordedBy"] = user.get("username") or ""
        if dispense_error:
            payload["success"] = False
            payload["message"] = (
                "The sale was charged, but dispensing did not finish. "
                f"{dispense_error}"
            )
            payload["code"] = "dispense_failed"
        return payload
    except Exception:
        with IDEMPOTENCY_LOCK:
            if (IDEMPOTENCY.get(idem_key) or {}).get("status") == "pending":
                IDEMPOTENCY.pop(idem_key, None)
        raise


def _dispense_sale_id(odoo: dispensary.OdooReader, sale_id: int) -> None:
    sales = odoo.read("sale.order", [sale_id], ["state", "partner_id", "name"])
    if not sales or sales[0].get("state") not in {"sale", "done"}:
        raise ApiError(409, "not_ready", "This sale is not ready to dispense yet.")
    pickings = dispensary.outgoing_pickings(odoo, sale_id)
    picking = dispensary.choose_picking(pickings)
    if not picking:
        raise ApiError(409, "not_ready", "This sale is not ready to dispense yet.")
    if picking.get("state") == "done":
        raise ApiError(409, "already_dispensed", "This sale has already been dispensed.")
    lines = odoo.search_read(
        "sale.order.line",
        [("order_id", "=", sale_id)],
        ["product_id", "product_uom_qty", "qty_delivered"],
    )
    location_id = dispensary.stock_location_id(odoo, sales[0])
    for line in lines:
        product_id = many2one_id(line.get("product_id")) or 0
        requested = as_float(line.get("product_uom_qty"))
        delivered = as_float(line.get("qty_delivered"))
        if delivered + 0.0001 >= requested:
            continue
        on_hand = dispensary.on_hand_quantity(odoo, product_id, location_id)
        if on_hand + 0.0001 < (requested - delivered):
            raise ApiError(409, "insufficient_stock", "Not enough stock to dispense this medication.")
    dispensary._complete_picking(odoo, int(picking["id"]))


def dispense_direct_sale(sale_id: str, cookie: str, request_id: str | None = None) -> dict[str, Any]:
    user = require_pharmacist(cookie)
    try:
        numeric_id = int(str(sale_id).strip())
    except ValueError as error:
        raise ApiError(404, "sale_not_found", "This pharmacy sale was not found.") from error
    idem_key = f"pharmacy-sale-dispense:{numeric_id}:{request_id or ''}"
    with IDEMPOTENCY_LOCK:
        state = IDEMPOTENCY.get(idem_key) or {}
        if state.get("status") == "pending":
            raise ApiError(409, "dispense_in_progress", "This sale is already being dispensed.")
        if state.get("status") == "done":
            payload = assemble_sale(numeric_id, cookie)
            payload["alreadyDispensed"] = True
            return payload
        IDEMPOTENCY[idem_key] = {"status": "pending"}
    try:
        odoo = odoo_reader()
        _dispense_sale_id(odoo, numeric_id)
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[idem_key] = {"status": "done"}
        payload = assemble_sale(numeric_id, cookie)
        payload["alreadyDispensed"] = False
        payload["success"] = True
        payload["recordedBy"] = user.get("username") or ""
        return payload
    except ApiError as error:
        with IDEMPOTENCY_LOCK:
            if (IDEMPOTENCY.get(idem_key) or {}).get("status") == "pending":
                IDEMPOTENCY.pop(idem_key, None)
        if error.code == "already_dispensed":
            payload = assemble_sale(numeric_id, cookie)
            payload["alreadyDispensed"] = True
            return payload
        raise
    except Exception:
        with IDEMPOTENCY_LOCK:
            if (IDEMPOTENCY.get(idem_key) or {}).get("status") == "pending":
                IDEMPOTENCY.pop(idem_key, None)
        raise
