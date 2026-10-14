"""Pharmacy inventory: receive stock and stock adjustment.

Odoo remains the inventory source of truth. Hospital EMR does not keep a local
stock table. Catalogue selling price is never overwritten here.
Supplier payment / purchase orders are not part of this phase.
"""

from __future__ import annotations

import html
import re
import xmlrpc.client
from typing import Any

import pharmacy as dispensary
import pharmacy_catalogue
import pharmacy_manage
import server as core

ApiError = core.ApiError
OdooReader = dispensary.OdooReader

INVENTORY_PRIVILEGE = "abikan:pharmacy:inventory"
PROTECTED_TEST_DRUGS = set(pharmacy_catalogue.TEST_DRUG_UUIDS)
VENDOR_LOCATION_NAME = "Partners/Vendors"
INVENTORY_LOCATION_NAME = "Virtual Locations/Inventory adjustment"

ADJUST_REASONS = [
    "Incorrect opening stock",
    "Physical stock count",
    "Damaged stock",
    "Expired stock",
    "Lost/missing stock",
    "Correction",
]


def is_inventory_manager(user: dict[str, Any]) -> bool:
    """Pharmacists who can open Pharmacy can receive and adjust shelf stock."""
    return dispensary.is_pharmacist(user)


def require_inventory_manager(cookie: str) -> dict[str, Any]:
    user = dispensary.require_pharmacist(cookie)
    if not is_inventory_manager(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires authorization to change pharmacy stock.",
        )
    return user


def _text(value: Any) -> str:
    return str(value or "").strip()


def _qty(value: Any) -> float:
    return round(dispensary.as_float(value), 4)


def _fault_text(error: BaseException) -> str:
    return str(getattr(error, "faultString", "") or error)


def _staff_odoo_error(error: BaseException, fallback: str) -> ApiError:
    detail = _fault_text(error)
    lowered = detail.lower()
    if "negative" in lowered or "insufficient" in lowered:
        return ApiError(409, "insufficient_stock", "There is not enough stock for this change.")
    if "marshal none" in lowered:
        return ApiError(502, "stock_update_failed", fallback)
    return ApiError(502, "stock_update_failed", fallback)


def stock_levels(odoo: OdooReader, product_id: int, location_id: int | None) -> dict[str, float]:
    grouped = stock_levels_by_product(odoo, [product_id] if product_id else [], location_id)
    return grouped.get(product_id, {"onHand": 0.0, "reserved": 0.0, "available": 0.0})


def stock_levels_by_product(
    odoo: OdooReader,
    product_ids: list[int],
    location_id: int | None,
) -> dict[int, dict[str, float]]:
    empty = {"onHand": 0.0, "reserved": 0.0, "available": 0.0}
    levels = {int(pid): dict(empty) for pid in product_ids if pid}
    if not levels or not location_id:
        return levels
    quants = odoo.search_read(
        "stock.quant",
        [("product_id", "in", list(levels)), ("location_id", "=", location_id)],
        ["product_id", "quantity", "reserved_quantity"],
        limit=max(len(levels) * 8, 200),
    )
    for row in quants:
        product_id = core.many2one_id(row.get("product_id"))
        if product_id not in levels:
            continue
        levels[product_id]["onHand"] += dispensary.as_float(row.get("quantity"))
        levels[product_id]["reserved"] += dispensary.as_float(row.get("reserved_quantity"))
    for product_id, item in levels.items():
        item["onHand"] = round(item["onHand"], 4)
        item["reserved"] = round(item["reserved"], 4)
        item["available"] = round(max(item["onHand"] - item["reserved"], 0.0), 4)
    return levels


def _stock_status(levels: dict[str, float]) -> str:
    if levels["onHand"] <= 0:
        return "Out of stock"
    if levels["reserved"] > 0:
        return "Reserved"
    return "In stock"


def vendor_location_id(odoo: OdooReader) -> int:
    rows = odoo.search_read(
        "stock.location",
        [("complete_name", "=", VENDOR_LOCATION_NAME), ("usage", "=", "supplier")],
        ["id"],
        limit=1,
    )
    if not rows:
        rows = odoo.search_read(
            "stock.location",
            [("usage", "=", "supplier")],
            ["id"],
            limit=1,
        )
    if not rows:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")
    return int(rows[0]["id"])


def inventory_location_id(odoo: OdooReader) -> int | None:
    rows = odoo.search_read(
        "stock.location",
        [("complete_name", "=", INVENTORY_LOCATION_NAME), ("usage", "=", "inventory")],
        ["id"],
        limit=1,
    )
    if rows:
        return int(rows[0]["id"])
    rows = odoo.search_read(
        "stock.location",
        [("usage", "=", "inventory"), ("scrap_location", "=", False)],
        ["id"],
        limit=1,
    )
    return int(rows[0]["id"]) if rows else None


def receipts_picking_type_id(odoo: OdooReader, dest_id: int) -> int:
    rows = odoo.search_read(
        "stock.picking.type",
        [("code", "=", "incoming")],
        ["id", "name", "sequence_code", "default_location_dest_id"],
    )
    preferred = []
    for row in rows:
        name = _text(row.get("name")).lower()
        if "return" in name:
            continue
        dest = core.many2one_id(row.get("default_location_dest_id"))
        if dest == dest_id or not dest:
            preferred.append(row)
    chosen = preferred[0] if preferred else (rows[0] if rows else None)
    if not chosen:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")
    return int(chosen["id"])


def _product_uom(product: dict[str, Any]) -> int:
    uom = core.many2one_id(product.get("uom_id"))
    if not uom:
        raise ApiError(502, "missing_uom", "This medicine could not be updated.")
    return uom


def _catalogue_entries(odoo: OdooReader) -> list[dict[str, Any]]:
    entries = list(pharmacy_catalogue.search_mapped_entries(""))
    entries.extend(pharmacy_manage.extra_catalogue_rows(odoo))
    return entries


def _find_entry(odoo: OdooReader, drug_uuid: str) -> dict[str, Any]:
    uuid = _text(drug_uuid)
    if not uuid:
        raise ApiError(404, "not_found", "This medicine is not in the hospital catalogue.")
    for row in _catalogue_entries(odoo):
        if str(row.get("drugUuid") or "") == uuid:
            return row
    product = dispensary.find_pharmacy_products(odoo, [uuid]).get(uuid)
    if product:
        name = str(product.get("name") or "Medicine")
        return {
            "drugUuid": uuid,
            "openmrsName": name,
            "hospitalName": name,
            "createName": name,
            "strength": "",
            "dosageFormName": core.many2one_name(product.get("uom_id")),
        }
    raise ApiError(404, "not_found", "This medicine is not in the hospital catalogue.")


def _mapped_product(odoo: OdooReader, drug_uuid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if drug_uuid in PROTECTED_TEST_DRUGS:
        raise ApiError(
            409,
            "protected_test",
            "The dedicated TEST medicine cannot be changed from this screen.",
        )
    entry = _find_entry(odoo, drug_uuid)
    product = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid)
    if not product or not product.get("id"):
        raise ApiError(409, "unmapped_product", "This medicine is not ready for stock yet.")
    return entry, product


def _serialize_item(
    entry: dict[str, Any],
    product: dict[str, Any],
    levels: dict[str, float],
    brand: str,
    *,
    can_manage: bool,
) -> dict[str, Any]:
    name = str(entry.get("openmrsName") or entry.get("createName") or entry.get("hospitalName") or "Medicine")
    form = str(entry.get("dosageFormName") or core.many2one_name(product.get("uom_id")) or "")
    selling = dispensary.as_float(product.get("list_price")) if product else None
    return {
        "id": str(entry.get("drugUuid") or ""),
        "name": name,
        "hospitalName": str(entry.get("hospitalName") or ""),
        "listedAs": dispensary._listed_as(str(entry.get("hospitalName") or ""), name),
        "brandName": brand,
        "strength": str(entry.get("strength") or ""),
        "form": form,
        "stockUnits": form,
        "onHand": levels["onHand"],
        "reserved": levels["reserved"],
        "available": levels["available"],
        "status": _stock_status(levels),
        "sellingPrice": dispensary._format_ngn(selling) if selling is not None else None,
        "canReceive": can_manage,
        "canAdjust": can_manage,
        "protectedTest": str(entry.get("drugUuid") or "") in PROTECTED_TEST_DRUGS,
    }


def list_inventory(cookie: str, query: str = "") -> dict[str, Any]:
    user = dispensary.require_pharmacist(cookie)
    can_manage = is_inventory_manager(user)
    odoo = dispensary.odoo_reader()
    entries = _catalogue_entries(odoo)
    brands = pharmacy_manage.brand_by_uuid(odoo)
    location_id = dispensary.stock_location_id(odoo)
    products = dispensary.find_pharmacy_products(
        odoo,
        [str(row.get("drugUuid") or "") for row in entries],
    )
    product_ids = [int(row["id"]) for row in products.values() if row.get("id")]
    levels_by_product = stock_levels_by_product(odoo, product_ids, location_id)
    needle = query.strip().lower()
    items: list[dict[str, Any]] = []
    for row in entries:
        drug_uuid = str(row.get("drugUuid") or "")
        product = products.get(drug_uuid) or {}
        product_id = int(product["id"]) if product.get("id") else 0
        levels = levels_by_product.get(product_id) or {"onHand": 0.0, "reserved": 0.0, "available": 0.0}
        item = _serialize_item(
            row,
            product,
            levels,
            str(row.get("brandName") or brands.get(drug_uuid) or ""),
            can_manage=can_manage and drug_uuid not in PROTECTED_TEST_DRUGS,
        )
        hay = " ".join(
            [item["name"], item["hospitalName"], item["brandName"], item["strength"], item["form"]]
        ).lower()
        if needle and needle not in hay:
            continue
        items.append(item)
    items.sort(key=lambda item: (item["name"].lower(), item["strength"].lower(), item["form"].lower(), item["id"]))
    return {
        "status": "ok",
        "canManageInventory": can_manage,
        "count": len(items),
        "items": items,
        "adjustmentReasons": list(ADJUST_REASONS),
    }


def get_inventory_item(drug_uuid: str, cookie: str) -> dict[str, Any]:
    payload = list_inventory(cookie)
    for item in payload["items"]:
        if item["id"] == drug_uuid:
            return {"status": "ok", "canManageInventory": payload["canManageInventory"], "item": item}
    raise ApiError(404, "not_found", "This medicine is not in the hospital catalogue.")


def _find_or_create_supplier(odoo: OdooReader, name: str) -> int | None:
    supplier = _text(name)
    if not supplier:
        return None
    found = odoo.search_read(
        "res.partner",
        [("name", "=", supplier)],
        ["id", "supplier_rank"],
        limit=1,
    )
    if found:
        partner_id = int(found[0]["id"])
        if dispensary.as_float(found[0].get("supplier_rank")) < 1:
            dispensary.execute(odoo, "res.partner", "write", [[partner_id], {"supplier_rank": 1}])
        return partner_id
    return int(
        dispensary.execute(
            odoo,
            "res.partner",
            "create",
            [{"name": supplier, "is_company": True, "supplier_rank": 1, "customer_rank": 0}],
        )
    )


def _picking_note(parts: dict[str, str]) -> str:
    lines = [f"{key}: {html.escape(value)}" for key, value in parts.items() if value]
    return "<br/>".join(lines)


def _set_move_done(odoo: OdooReader, picking_id: int, qty: float | None = None, price: float | None = None) -> None:
    """Mark incoming moves done. Prefer each move's own demand qty/price (multi-line safe)."""
    picking = odoo.read(
        "stock.picking",
        [picking_id],
        ["move_ids_without_package", "move_line_ids", "state"],
    )[0]
    move_ids = [int(item) for item in (picking.get("move_ids_without_package") or [])]
    if move_ids:
        moves = odoo.read(
            "stock.move",
            move_ids,
            ["id", "product_uom_qty", "price_unit", "move_line_ids"],
        )
        for move in moves:
            move_qty = _qty(move.get("product_uom_qty")) if qty is None else qty
            move_price = dispensary.as_float(move.get("price_unit")) if price is None else price
            if len(moves) == 1 and qty is not None:
                move_qty = qty
            if len(moves) == 1 and price is not None:
                move_price = price
            dispensary.execute(
                odoo,
                "stock.move",
                "write",
                [[int(move["id"])], {"quantity_done": move_qty, "price_unit": move_price}],
            )
            line_ids = [int(item) for item in (move.get("move_line_ids") or [])]
            if line_ids:
                dispensary.execute(odoo, "stock.move.line", "write", [line_ids, {"qty_done": move_qty}])
        return
    line_ids = [int(item) for item in (picking.get("move_line_ids") or [])]
    if line_ids and qty is not None:
        dispensary.execute(odoo, "stock.move.line", "write", [line_ids, {"qty_done": qty}])


def _validate_incoming(odoo: OdooReader, picking_id: int, qty: float | None = None, price: float | None = None) -> None:
    try:
        dispensary.execute(odoo, "stock.picking", "action_confirm", [[picking_id]])
    except xmlrpc.client.Fault as error:
        if "marshal none" not in _fault_text(error).lower():
            raise _staff_odoo_error(error, "The stock receipt could not be recorded.") from error
    try:
        dispensary.execute(odoo, "stock.picking", "action_assign", [[picking_id]])
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, TypeError):
        pass
    _set_move_done(odoo, picking_id, qty, price)
    fresh = odoo.read("stock.picking", [picking_id], ["state"])
    if fresh and fresh[0].get("state") == "done":
        return
    try:
        result = dispensary.execute(
            odoo,
            "stock.picking",
            "button_validate",
            [[picking_id]],
            {"context": {"validation_confirmed": True}},
        )
    except xmlrpc.client.Fault as error:
        if "marshal none" in _fault_text(error).lower():
            done = odoo.read("stock.picking", [picking_id], ["state"])
            if done and done[0].get("state") == "done":
                return
        raise _staff_odoo_error(error, "The stock receipt could not be recorded.") from error
    if isinstance(result, dict) and result.get("res_model") == "stock.picking.validate.wizard":
        move_lines = odoo.read("stock.picking", [picking_id], ["move_line_ids"])
        line_ids = [int(item) for item in ((move_lines[0].get("move_line_ids") if move_lines else []) or [])]
        wizard_id = int(
            dispensary.execute(
                odoo,
                "stock.picking.validate.wizard",
                "create",
                [{"picking_id": picking_id, "move_lines": [(6, 0, line_ids)]}],
            )
        )
        try:
            dispensary.execute(
                odoo,
                "stock.picking.validate.wizard",
                "btn_confirm",
                [[wizard_id]],
                {"context": {"validation_confirmed": True}},
            )
        except xmlrpc.client.Fault as error:
            if "marshal none" not in _fault_text(error).lower():
                raise _staff_odoo_error(error, "The stock receipt could not be recorded.") from error
        result = True
    if isinstance(result, dict) and result.get("res_model") == "stock.immediate.transfer" and result.get("res_id"):
        try:
            dispensary.execute(odoo, "stock.immediate.transfer", "process", [[int(result["res_id"])]])
        except xmlrpc.client.Fault as error:
            if "marshal none" not in _fault_text(error).lower():
                raise _staff_odoo_error(error, "The stock receipt could not be recorded.") from error
    elif isinstance(result, dict) and result.get("res_model") == "stock.backorder.confirmation" and result.get("res_id"):
        try:
            dispensary.execute(odoo, "stock.backorder.confirmation", "process", [[int(result["res_id"])]])
        except xmlrpc.client.Fault as error:
            raise _staff_odoo_error(error, "The stock receipt could not be recorded.") from error
    elif isinstance(result, dict) and result.get("res_model") and result.get("type") not in {
        None,
        "ir.actions.act_window_close",
    }:
        raise ApiError(502, "stock_update_failed", "The stock receipt could not be recorded.")
    try:
        picking = odoo.read("stock.picking", [picking_id], ["move_ids_without_package"])[0]
        move_ids = [int(item) for item in (picking.get("move_ids_without_package") or [])]
        if move_ids:
            dispensary.execute(odoo, "stock.move", "write", [move_ids, {"price_unit": price}])
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, TypeError, IndexError):
        return


def receive_stock(drug_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_inventory_manager(cookie)
    qty = _qty(body.get("quantity") or body.get("quantityReceived"))
    price = dispensary.as_float(body.get("purchasePrice") or body.get("purchasePricePerUnit"))
    supplier = _text(body.get("supplier"))
    reference = _text(body.get("reference"))
    note = _text(body.get("note") or body.get("reason"))
    if qty <= 0:
        raise ApiError(422, "invalid_quantity", "Enter how many units arrived.")
    if price < 0:
        raise ApiError(422, "invalid_price", "Enter the purchase price per unit. This is not the selling price.")
    if price == 0:
        raise ApiError(422, "invalid_price", "Enter the purchase price paid for this receipt.")
    odoo = dispensary.odoo_reader()
    entry, product = _mapped_product(odoo, drug_uuid)
    product_id = int(product["id"])
    location_id = dispensary.stock_location_id(odoo)
    if not location_id:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")
    before = stock_levels(odoo, product_id, location_id)
    selling_before = dispensary.as_float(product.get("list_price"))
    partner_id = _find_or_create_supplier(odoo, supplier)
    origin = reference or "Pharmacy receive"
    vendor_id = vendor_location_id(odoo)
    picking_id = int(
        dispensary.execute(
            odoo,
            "stock.picking",
            "create",
            [
                {
                    "picking_type_id": receipts_picking_type_id(odoo, location_id),
                    "location_id": vendor_id,
                    "location_dest_id": location_id,
                    "partner_id": partner_id or False,
                    "origin": origin,
                    "note": _picking_note(
                        {
                            "Received by": str(user.get("username") or ""),
                            "Supplier": supplier,
                            "Reference": reference,
                            "Purchase price per unit": f"{price:.2f}",
                            "Note": note,
                        }
                    ),
                    "move_ids_without_package": [
                        (
                            0,
                            0,
                            {
                                "name": str(product.get("name") or entry.get("openmrsName") or "Medicine"),
                                "product_id": product_id,
                                "product_uom_qty": qty,
                                "product_uom": _product_uom(product),
                                "location_id": vendor_id,
                                "location_dest_id": location_id,
                                "price_unit": price,
                                "procure_method": "make_to_stock",
                            },
                        )
                    ],
                }
            ],
        )
    )
    try:
        _validate_incoming(odoo, picking_id, qty, price)
    except ApiError:
        done = odoo.read("stock.picking", [picking_id], ["state"])
        if not (done and done[0].get("state") == "done"):
            raise
    after = stock_levels(odoo, product_id, location_id)
    if abs(after["onHand"] - (before["onHand"] + qty)) > 0.01:
        raise ApiError(
            502,
            "stock_update_failed",
            "The stock receipt was not recorded. Shelf quantity was left unchanged.",
        )
    fresh = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid) or product
    if abs(dispensary.as_float(fresh.get("list_price")) - selling_before) > 0.01:
        pharmacy_manage.set_price(odoo, product_id, selling_before)
        fresh = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid) or fresh
    brands = pharmacy_manage.brand_by_uuid(odoo)
    item = _serialize_item(
        entry,
        fresh,
        after,
        str(entry.get("brandName") or brands.get(drug_uuid) or ""),
        can_manage=True,
    )
    picking_name = ""
    named = odoo.read("stock.picking", [picking_id], ["name"])
    if named:
        picking_name = str(named[0].get("name") or "")
    return {
        "status": "ok",
        "item": item,
        "receipt": {
            "quantity": qty,
            "previousOnHand": before["onHand"],
            "resultingOnHand": after["onHand"],
            "purchasePricePerUnit": price,
            "purchaseCost": round(qty * price, 2),
            "supplier": supplier,
            "reference": reference or picking_name,
            "recordedBy": str(user.get("username") or ""),
        },
    }


def _annotate_adjustment_move(
    odoo: OdooReader,
    product_id: int,
    reason: str,
    reference: str,
    username: str,
    note: str,
) -> None:
    inv_loc = inventory_location_id(odoo)
    domain: list[Any] = [("product_id", "=", product_id), ("state", "=", "done")]
    if inv_loc:
        domain = [
            ("product_id", "=", product_id),
            ("state", "=", "done"),
            "|",
            ("location_id", "=", inv_loc),
            ("location_dest_id", "=", inv_loc),
        ]
    rows = dispensary.execute(
        odoo,
        "stock.move",
        "search_read",
        [domain],
        {"fields": ["id"], "limit": 1, "order": "id desc"},
    )
    if not rows:
        return
    origin = " · ".join(part for part in [reason, username, reference] if part)
    try:
        dispensary.execute(
            odoo,
            "stock.move",
            "write",
            [
                [int(rows[0]["id"])],
                {
                    "origin": origin or reason,
                    "name": f"Stock adjustment: {reason}" + (f" — {note}" if note else ""),
                },
            ],
        )
    except xmlrpc.client.Fault:
        return


def adjust_stock(drug_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_inventory_manager(cookie)
    direction = _text(body.get("direction") or body.get("adjustment")).lower()
    qty = _qty(body.get("quantity") or body.get("adjustmentQuantity"))
    reason = _text(body.get("reason"))
    reference = _text(body.get("reference"))
    note = _text(body.get("note"))
    if direction not in {"increase", "decrease"}:
        raise ApiError(422, "invalid_direction", "Choose whether to increase or decrease stock.")
    if qty <= 0:
        raise ApiError(422, "invalid_quantity", "Enter how many units to adjust.")
    if not reason:
        raise ApiError(422, "missing_reason", "Choose why the stock is being adjusted.")
    odoo = dispensary.odoo_reader()
    entry, product = _mapped_product(odoo, drug_uuid)
    product_id = int(product["id"])
    location_id = dispensary.stock_location_id(odoo)
    if not location_id:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")
    before = stock_levels(odoo, product_id, location_id)
    delta = qty if direction == "increase" else -qty
    target = round(before["onHand"] + delta, 4)
    if target < 0:
        raise ApiError(409, "insufficient_stock", "Stock cannot go below zero.")
    if target + 0.0001 < before["reserved"]:
        raise ApiError(
            409,
            "stock_reserved",
            "Some of this medicine is already reserved for a prescription. Enter a smaller decrease.",
        )
    if abs(target - before["onHand"]) < 0.0001:
        raise ApiError(422, "invalid_quantity", "Enter how many units to adjust.")
    quants = odoo.search_read(
        "stock.quant",
        [("product_id", "=", product_id), ("location_id", "=", location_id)],
        ["id"],
        limit=1,
    )
    values = {"product_id": product_id, "location_id": location_id, "inventory_quantity": target}
    try:
        if quants:
            quant_id = int(quants[0]["id"])
            dispensary.execute(odoo, "stock.quant", "write", [[quant_id], values])
        else:
            quant_id = int(dispensary.execute(odoo, "stock.quant", "create", [values]))
        try:
            dispensary.execute(odoo, "stock.quant", "action_apply_inventory", [[quant_id]])
        except xmlrpc.client.Fault as error:
            if "cannot marshal none" not in _fault_text(error).lower():
                raise
    except xmlrpc.client.Fault as error:
        after_fail = stock_levels(odoo, product_id, location_id)
        if abs(after_fail["onHand"] - before["onHand"]) < 0.01:
            raise _staff_odoo_error(error, "The stock adjustment could not be recorded.") from error
        raise
    after = stock_levels(odoo, product_id, location_id)
    if abs(after["onHand"] - target) > 0.01:
        raise ApiError(
            502,
            "stock_update_failed",
            "The stock adjustment was not recorded. Shelf quantity was left unchanged.",
        )
    _annotate_adjustment_move(
        odoo,
        product_id,
        reason,
        reference,
        str(user.get("username") or ""),
        note,
    )
    brands = pharmacy_manage.brand_by_uuid(odoo)
    item = _serialize_item(
        entry,
        product,
        after,
        str(entry.get("brandName") or brands.get(drug_uuid) or ""),
        can_manage=True,
    )
    return {
        "status": "ok",
        "item": item,
        "adjustment": {
            "direction": direction,
            "quantity": qty,
            "previousOnHand": before["onHand"],
            "resultingOnHand": after["onHand"],
            "reason": reason,
            "reference": reference,
            "note": note,
            "recordedBy": str(user.get("username") or ""),
        },
    }


def _parse_receive_lines(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("lines")
    if not isinstance(raw, list) or not raw:
        raise ApiError(422, "lines_required", "Add at least one medicine to this receipt.")
    lines: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ApiError(422, "invalid_line", f"Medicine {index + 1} is incomplete.")
        drug_uuid = _text(row.get("drugUuid") or row.get("id"))
        qty = _qty(row.get("quantity") or row.get("quantityReceived"))
        price = dispensary.as_float(row.get("purchasePrice") or row.get("purchasePricePerUnit"))
        if not drug_uuid:
            raise ApiError(422, "invalid_line", f"Choose a medicine for row {index + 1}.")
        if qty <= 0:
            raise ApiError(422, "invalid_quantity", f"Enter how many units arrived for row {index + 1}.")
        if price < 0 or price == 0:
            raise ApiError(
                422,
                "invalid_price",
                f"Enter the purchase price paid for row {index + 1}. This is not the selling price.",
            )
        lines.append({"drugUuid": drug_uuid, "quantity": qty, "purchasePrice": price, "index": index})
    return lines


def receive_stock_batch(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Receive several medicines in one stock receipt (one Odoo picking)."""
    user = require_inventory_manager(cookie)
    lines = _parse_receive_lines(body)
    supplier = _text(body.get("supplier"))
    reference = _text(body.get("reference"))
    note = _text(body.get("note") or body.get("reason"))
    odoo = dispensary.odoo_reader()
    location_id = dispensary.stock_location_id(odoo)
    if not location_id:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")
    vendor_id = vendor_location_id(odoo)
    partner_id = _find_or_create_supplier(odoo, supplier)
    origin = reference or "Pharmacy receive"
    prepared: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in lines:
        drug_uuid = row["drugUuid"]
        # Same medicine may appear twice with different purchase prices — keep separate moves.
        key = f"{drug_uuid}:{row['purchasePrice']}:{row['index']}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entry, product = _mapped_product(odoo, drug_uuid)
        product_id = int(product["id"])
        before = stock_levels(odoo, product_id, location_id)
        prepared.append(
            {
                **row,
                "entry": entry,
                "product": product,
                "productId": product_id,
                "sellingBefore": dispensary.as_float(product.get("list_price")),
                "before": before,
            }
        )
    move_commands = []
    for row in prepared:
        product = row["product"]
        entry = row["entry"]
        move_commands.append(
            (
                0,
                0,
                {
                    "name": str(product.get("name") or entry.get("openmrsName") or "Medicine"),
                    "product_id": row["productId"],
                    "product_uom_qty": row["quantity"],
                    "product_uom": _product_uom(product),
                    "location_id": vendor_id,
                    "location_dest_id": location_id,
                    "price_unit": row["purchasePrice"],
                    "procure_method": "make_to_stock",
                },
            )
        )
    picking_id = int(
        dispensary.execute(
            odoo,
            "stock.picking",
            "create",
            [
                {
                    "picking_type_id": receipts_picking_type_id(odoo, location_id),
                    "location_id": vendor_id,
                    "location_dest_id": location_id,
                    "partner_id": partner_id or False,
                    "origin": origin,
                    "note": _picking_note(
                        {
                            "Received by": str(user.get("username") or ""),
                            "Supplier": supplier,
                            "Reference": reference,
                            "Lines": str(len(prepared)),
                            "Note": note,
                        }
                    ),
                    "move_ids_without_package": move_commands,
                }
            ],
        )
    )
    try:
        _validate_incoming(odoo, picking_id)
    except ApiError:
        done = odoo.read("stock.picking", [picking_id], ["state"])
        if not (done and done[0].get("state") == "done"):
            raise
    brands = pharmacy_manage.brand_by_uuid(odoo)
    receipts: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for row in prepared:
        after = stock_levels(odoo, row["productId"], location_id)
        expected = row["before"]["onHand"] + row["quantity"]
        if abs(after["onHand"] - expected) > 0.01:
            raise ApiError(
                502,
                "stock_update_failed",
                "The stock receipt was not recorded completely. Check Inventory and try again.",
            )
        fresh = dispensary.find_pharmacy_products(odoo, [row["drugUuid"]]).get(row["drugUuid"]) or row["product"]
        if abs(dispensary.as_float(fresh.get("list_price")) - row["sellingBefore"]) > 0.01:
            pharmacy_manage.set_price(odoo, row["productId"], row["sellingBefore"])
            fresh = dispensary.find_pharmacy_products(odoo, [row["drugUuid"]]).get(row["drugUuid"]) or fresh
        item = _serialize_item(
            row["entry"],
            fresh,
            after,
            str(row["entry"].get("brandName") or brands.get(row["drugUuid"]) or ""),
            can_manage=True,
        )
        items.append(item)
        receipts.append(
            {
                "drugUuid": row["drugUuid"],
                "drugName": item.get("name") or "",
                "quantity": row["quantity"],
                "previousOnHand": row["before"]["onHand"],
                "resultingOnHand": after["onHand"],
                "purchasePricePerUnit": row["purchasePrice"],
                "purchaseCost": round(row["quantity"] * row["purchasePrice"], 2),
            }
        )
    picking_name = ""
    named = odoo.read("stock.picking", [picking_id], ["name"])
    if named:
        picking_name = str(named[0].get("name") or "")
    return {
        "status": "ok",
        "count": len(receipts),
        "items": items,
        "receipts": receipts,
        "supplier": supplier,
        "reference": reference or picking_name,
        "recordedBy": str(user.get("username") or ""),
        "message": f"{len(receipts)} medicine{'s' if len(receipts) != 1 else ''} added to inventory.",
    }


def _parse_adjust_lines(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("lines")
    if not isinstance(raw, list) or not raw:
        raise ApiError(422, "lines_required", "Add at least one medicine to this adjustment.")
    lines: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ApiError(422, "invalid_line", f"Medicine {index + 1} is incomplete.")
        drug_uuid = _text(row.get("drugUuid") or row.get("id"))
        direction = _text(row.get("direction") or row.get("adjustment")).lower()
        qty = _qty(row.get("quantity") or row.get("adjustmentQuantity"))
        reason = _text(row.get("reason"))
        if not drug_uuid:
            raise ApiError(422, "invalid_line", f"Choose a medicine for row {index + 1}.")
        if direction not in {"increase", "decrease"}:
            raise ApiError(422, "invalid_direction", f"Choose increase or decrease for row {index + 1}.")
        if qty <= 0:
            raise ApiError(422, "invalid_quantity", f"Enter how many units to adjust for row {index + 1}.")
        if not reason:
            raise ApiError(422, "missing_reason", f"Choose why stock is being adjusted for row {index + 1}.")
        lines.append(
            {
                "drugUuid": drug_uuid,
                "direction": direction,
                "quantity": qty,
                "reason": reason,
                "index": index,
            }
        )
    return lines


def adjust_stock_batch(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Validate all adjustment lines, then apply them one by one with accurate results."""
    user = require_inventory_manager(cookie)
    lines = _parse_adjust_lines(body)
    reference = _text(body.get("reference"))
    note = _text(body.get("note"))
    odoo = dispensary.odoo_reader()
    location_id = dispensary.stock_location_id(odoo)
    if not location_id:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")

    # Validate every line against current stock before writing anything.
    planned: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    for row in lines:
        entry, product = _mapped_product(odoo, row["drugUuid"])
        product_id = int(product["id"])
        if row["drugUuid"] not in running:
            levels = stock_levels(odoo, product_id, location_id)
            running[row["drugUuid"]] = levels["onHand"]
            reserved = levels["reserved"]
        else:
            reserved = stock_levels(odoo, product_id, location_id)["reserved"]
        before = running[row["drugUuid"]]
        delta = row["quantity"] if row["direction"] == "increase" else -row["quantity"]
        target = round(before + delta, 4)
        if target < 0:
            raise ApiError(
                409,
                "insufficient_stock",
                f"Stock cannot go below zero for row {row['index'] + 1}.",
            )
        if target + 0.0001 < reserved:
            raise ApiError(
                409,
                "stock_reserved",
                f"Some stock is reserved for a prescription on row {row['index'] + 1}. Enter a smaller decrease.",
            )
        planned.append(
            {
                **row,
                "entry": entry,
                "product": product,
                "productId": product_id,
                "before": before,
                "target": target,
                "reserved": reserved,
            }
        )
        running[row["drugUuid"]] = target

    saved: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for row in planned:
        try:
            result = adjust_stock(
                row["drugUuid"],
                {
                    "direction": row["direction"],
                    "quantity": row["quantity"],
                    "reason": row["reason"],
                    "reference": reference,
                    "note": note,
                },
                cookie,
            )
            saved.append(
                {
                    "drugUuid": row["drugUuid"],
                    "drugName": (result.get("item") or {}).get("name") or "",
                    "direction": row["direction"],
                    "quantity": row["quantity"],
                    "reason": row["reason"],
                    "resultingOnHand": (result.get("adjustment") or {}).get("resultingOnHand"),
                }
            )
        except ApiError as error:
            failed.append(
                {
                    "drugUuid": row["drugUuid"],
                    "drugName": str(row["entry"].get("openmrsName") or row["drugUuid"]),
                    "index": row["index"],
                    "code": error.code,
                    "message": error.message,
                }
            )
            # Stop applying further lines so stock stays predictable.
            for pending in planned[planned.index(row) + 1 :]:
                failed.append(
                    {
                        "drugUuid": pending["drugUuid"],
                        "drugName": str(pending["entry"].get("openmrsName") or pending["drugUuid"]),
                        "index": pending["index"],
                        "code": "not_applied",
                        "message": "Not applied because an earlier line failed.",
                    }
                )
            break

    if failed and not saved:
        first = failed[0]
        raise ApiError(
            409 if first.get("code") in {"insufficient_stock", "stock_reserved"} else 422,
            str(first.get("code") or "adjust_failed"),
            str(first.get("message") or "The stock adjustment could not be recorded."),
        )
    if failed and saved:
        return {
            "status": "partial",
            "count": len(saved),
            "saved": saved,
            "failed": failed,
            "message": (
                f"{len(saved)} medicine{'s' if len(saved) != 1 else ''} adjusted. "
                f"{len(failed)} could not be saved — nothing after the first problem was applied."
            ),
            "recordedBy": str(user.get("username") or ""),
        }
    return {
        "status": "ok",
        "count": len(saved),
        "saved": saved,
        "failed": [],
        "message": f"{len(saved)} medicine{'s' if len(saved) != 1 else ''} adjusted in inventory.",
        "recordedBy": str(user.get("username") or ""),
    }


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+\n", "\n", html.unescape(text)).strip()


def _note_field(note: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*(.+)", note, flags=re.I)
    return _text(match.group(1)) if match else ""


def _classify_move(
    move: dict[str, Any],
    stock_id: int,
    vendor_id: int | None,
    inv_id: int | None,
    picking_code: str,
) -> str:
    src = core.many2one_id(move.get("location_id"))
    dest = core.many2one_id(move.get("location_dest_id"))
    if picking_code == "incoming" or (dest == stock_id and src == vendor_id):
        return "Receive Stock"
    if picking_code == "outgoing" or (src == stock_id and dest and dest != stock_id and dest != inv_id):
        name = _text(move.get("reference") or move.get("origin"))
        if name.startswith("WH/OUT") or picking_code == "outgoing":
            return "Dispensing"
        if inv_id and (src == inv_id or dest == inv_id):
            return "Stock Adjustment"
        return "Dispensing"
    if inv_id and (src == inv_id or dest == inv_id):
        return "Stock Adjustment"
    return "Stock movement"


def _signed_qty(move: dict[str, Any], stock_id: int) -> float:
    dest = core.many2one_id(move.get("location_dest_id"))
    qty = _qty(move.get("quantity_done") or move.get("product_uom_qty"))
    return qty if dest == stock_id else -qty


def list_history(drug_uuid: str, cookie: str) -> dict[str, Any]:
    payload = get_inventory_item(drug_uuid, cookie)
    item = payload["item"]
    odoo = dispensary.odoo_reader()
    product = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid)
    if not product:
        return {"status": "ok", "item": item, "movements": []}
    product_id = int(product["id"])
    stock_id = dispensary.stock_location_id(odoo)
    vendor_id = None
    try:
        vendor_id = vendor_location_id(odoo)
    except ApiError:
        vendor_id = None
    inv_id = inventory_location_id(odoo)
    moves = dispensary.execute(
        odoo,
        "stock.move",
        "search_read",
        [[("product_id", "=", product_id), ("state", "=", "done")]],
        {
            "fields": [
                "id",
                "name",
                "origin",
                "reference",
                "picking_id",
                "location_id",
                "location_dest_id",
                "product_uom_qty",
                "quantity_done",
                "price_unit",
                "create_uid",
                "date",
            ],
            "order": "date asc, id asc",
            "limit": 200,
        },
    ) or []
    picking_ids = [core.many2one_id(row.get("picking_id")) for row in moves]
    picking_ids = [item_id for item_id in picking_ids if item_id]
    pickings = {
        int(row["id"]): row
        for row in (
            odoo.read(
                "stock.picking",
                picking_ids,
                ["name", "origin", "partner_id", "note", "picking_type_id", "create_uid"],
            )
            if picking_ids
            else []
        )
    }
    type_ids = [core.many2one_id(row.get("picking_type_id")) for row in pickings.values()]
    type_ids = [item_id for item_id in type_ids if item_id]
    types = {
        int(row["id"]): str(row.get("code") or "")
        for row in (odoo.read("stock.picking.type", type_ids, ["code"]) if type_ids else [])
    }
    running = 0.0
    movements: list[dict[str, Any]] = []
    for move in moves:
        signed = _signed_qty(move, stock_id or 0)
        previous = running
        running = round(running + signed, 4)
        picking = pickings.get(core.many2one_id(move.get("picking_id")) or 0) or {}
        code = types.get(core.many2one_id(picking.get("picking_type_id")) or 0, "")
        kind = _classify_move(move, stock_id or 0, vendor_id, inv_id, code)
        note = _strip_html(str(picking.get("note") or ""))
        purchase = dispensary.as_float(move.get("price_unit")) if kind == "Receive Stock" else None
        if kind == "Receive Stock" and not purchase:
            purchase = None
        supplier = core.many2one_name(picking.get("partner_id")) or _note_field(note, "Supplier")
        recorded_by = (
            _note_field(note, "Received by")
            or core.many2one_name(move.get("create_uid"))
            or core.many2one_name(picking.get("create_uid"))
        )
        reason = _text(move.get("origin")) or _note_field(note, "Note")
        if kind == "Stock Adjustment" and reason.startswith("Stock adjustment:"):
            reason = reason.split(":", 1)[-1].strip()
        if kind == "Receive Stock" and reason in {"Pharmacy receive", supplier}:
            reason = _note_field(note, "Note")
        movements.append(
            {
                "id": str(move.get("id")),
                "productName": item["name"],
                "previousQuantity": previous,
                "movementQuantity": signed,
                "resultingQuantity": running,
                "movementType": kind,
                "purchasePricePerUnit": purchase if kind == "Receive Stock" and purchase else None,
                "purchaseCost": round(abs(signed) * purchase, 2)
                if kind == "Receive Stock" and purchase
                else None,
                "supplier": supplier if kind == "Receive Stock" else "",
                "reason": reason,
                "user": recorded_by,
                "when": str(move.get("date") or ""),
                "reference": str(
                    picking.get("name") or move.get("reference") or move.get("origin") or ""
                ),
            }
        )
    movements.reverse()
    return {"status": "ok", "item": item, "movements": movements}
