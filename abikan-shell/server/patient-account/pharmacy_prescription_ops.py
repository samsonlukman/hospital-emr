"""Pharmacy prescription announce + safe cancel.

Prescriptions are written by Bahmni (bahmniencounter), not Hospital EMR. Announce
validates the OpenMRS order exists after a successful clinical save, then emits
into the shared staff notification store.

Cancel voids a medicine that has not been handed over. An unpaid bill is
removed. A paid bill is credited so accounts can return that payment.
Dispensed medicines cannot be destroyed.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import notifications as staff_notes
import pharmacy as dispensary
import server as core
from server import ApiError, OPENMRS_URL

execute = dispensary.execute
odoo_reader = dispensary.odoo_reader
many2one_id = dispensary.many2one_id
as_float = dispensary.as_float


def _text(value: Any) -> str:
    return str(value or "").strip()


_ORDER_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_order_uuid(value: Any) -> bool:
    return bool(_ORDER_UUID_RE.match(_text(value)))


def _parse_uuid_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        uuid = _text(item)
        if not uuid or uuid in seen or not _is_order_uuid(uuid):
            continue
        seen.add(uuid)
        out.append(uuid)
    return out


def _list_patient_drug_order_uuids(patient_uuid: str, cookie: str) -> list[str]:
    """Read Bahmni prescribed/active drug orders for a patient (UUID-shaped only).

    Newest first so discovery can take only the expected number of new orders.
    """
    patient = _text(patient_uuid)
    if not patient:
        return []
    path = (
        "/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive"
        f"?patientUuid={patient}"
    )
    payload = dispensary._openmrs_json(path, cookie)
    rows: list[Any] = []
    if isinstance(payload, dict):
        visit_rows = payload.get("visitDrugOrders")
        if isinstance(visit_rows, list):
            rows = visit_rows
        elif isinstance(payload.get("results"), list):
            rows = payload["results"]
    elif isinstance(payload, list):
        rows = payload
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        nested = row.get("drugOrder") if isinstance(row.get("drugOrder"), dict) else {}
        uuid = _text(row.get("uuid")) or _text(nested.get("uuid"))
        if not uuid or uuid in seen or not _is_order_uuid(uuid):
            continue
        stopped = bool(row.get("dateStopped") or nested.get("dateStopped"))
        action = _text(row.get("action") or nested.get("action")).upper()
        if stopped or action == "DISCONTINUE":
            continue
        activated = row.get("dateActivated")
        if activated is None:
            activated = nested.get("dateActivated")
        activated_epoch = 0.0
        if isinstance(activated, (int, float)):
            activated_epoch = float(activated)
            if activated_epoch > 1e12:
                activated_epoch /= 1000.0
        elif isinstance(activated, str) and activated.strip():
            text_value = activated.strip()
            try:
                activated_epoch = float(text_value)
                if activated_epoch > 1e12:
                    activated_epoch /= 1000.0
            except ValueError:
                try:
                    from datetime import datetime

                    activated_epoch = datetime.fromisoformat(text_value.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    activated_epoch = 0.0
        seen.add(uuid)
        ranked.append((activated_epoch, uuid))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [uuid for _epoch, uuid in ranked]


def _discover_new_order_uuids(
    patient_uuid: str,
    prior_uuids: set[str],
    expected_count: int,
    cookie: str,
    *,
    delays_seconds: tuple[float, ...] = (0.0, 0.35, 0.8, 1.6, 2.8),
) -> list[str]:
    """Retry Bahmni reads until newly saved orders are visible."""
    expected = max(1, int(expected_count or 1))
    found: list[str] = []
    for delay in delays_seconds:
        if delay > 0:
            time.sleep(delay)
        current = _list_patient_drug_order_uuids(patient_uuid, cookie)
        found = [uuid for uuid in current if uuid not in prior_uuids]
        if len(found) >= expected:
            return found[:expected]
    return found[:expected] if expected_count else found


def _openmrs_delete(path: str, cookie: str) -> None:
    request = Request(
        f"{OPENMRS_URL}{path}",
        headers={"Accept": "application/json", "Cookie": cookie},
        method="DELETE",
    )
    status = _delete_request(request)
    if status in {None, 404}:
        return
    if status == 401:
        raise ApiError(401, "unauthenticated", "Sign in required.")
    if _delete_with_service(path):
        return
    raise ApiError(
        502,
        "prescription_cancel_failed",
        "This prescription could not be removed. Refresh and try again.",
    )


def _delete_request(request: Request) -> int | None:
    try:
        with urlopen(request, timeout=30) as response:
            response.read()
        return None
    except HTTPError as error:
        return int(error.code)
    except (URLError, TimeoutError) as error:
        raise ApiError(
            502,
            "prescription_cancel_failed",
            "This prescription could not be removed. Refresh and try again.",
        ) from error


def _delete_with_service(path: str) -> bool:
    if not core.OPENMRS_ADMIN_USER or not core.OPENMRS_ADMIN_PASSWORD:
        return False
    import base64

    token = base64.b64encode(
        f"{core.OPENMRS_ADMIN_USER}:{core.OPENMRS_ADMIN_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        f"{OPENMRS_URL}{path}",
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
        method="DELETE",
    )
    try:
        return _delete_request(request) in {None, 404}
    except ApiError:
        return False


def _doctor_display(user: dict[str, Any], cookie: str) -> str:
    username = _text(user.get("username")) or "Doctor"
    display = username
    try:
        session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
        session_user = session.get("user") if isinstance(session, dict) else {}
        if isinstance(session_user, dict):
            person = session_user.get("person") if isinstance(session_user.get("person"), dict) else {}
            display = (
                _text(person.get("display"))
                or _text(session_user.get("display"))
                or display
            )
    except Exception:
        pass
    return display


def announce_prescriptions(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Clinician announces newly persisted OpenMRS drug orders to Pharmacy."""
    import consultation as clinical

    user = clinical.require_clinician(cookie)
    order_uuids = _parse_uuid_list(body.get("orderUuids") or body.get("orders") or [])
    prior_uuids = set(_parse_uuid_list(body.get("priorOrderUuids") or []))
    patient_uuid = _text(body.get("patientUuid"))
    try:
        expected_count = int(body.get("expectedCount") or 0)
    except (TypeError, ValueError):
        expected_count = 0

    # Clinical save can return before Bahmni read APIs show the new order UUID.
    # If the client could not resolve enough UUIDs, discover them here with retry.
    if patient_uuid and (not order_uuids or (expected_count > 0 and len(order_uuids) < expected_count)):
        discovered = _discover_new_order_uuids(
            patient_uuid,
            prior_uuids | set(order_uuids),
            expected_count or max(1, len(order_uuids) + 1),
            cookie,
        )
        merged: list[str] = []
        seen: set[str] = set()
        for uuid in [*order_uuids, *discovered]:
            if uuid in seen:
                continue
            seen.add(uuid)
            merged.append(uuid)
        order_uuids = merged

    if not order_uuids:
        if patient_uuid:
            return {
                "status": "ok",
                "count": 0,
                "notifications": [],
                "message": "No new prescriptions to announce.",
            }
        raise ApiError(422, "missing_orders", "Provide at least one prescription.")

    sender_username = _text(user.get("username")) or "doctor"
    sender_display = _doctor_display(user, cookie)
    loaded: list[dict[str, Any]] = []
    for order_uuid in order_uuids:
        try:
            clinical_order = dispensary.load_openmrs_order(order_uuid, cookie)
        except ApiError:
            continue
        if clinical_order.get("stopped"):
            continue
        clinical_order["uuid"] = order_uuid
        loaded.append(clinical_order)
        import pharmacy_unlisted as unlisted

        if unlisted.not_in_pharmacy_order(clinical_order):
            unlisted.remember(clinical_order)
            try:
                _cancel_odoo_sale_for_order(odoo_reader(), order_uuid)
            except ApiError:
                pass
        else:
            unlisted.forget(order_uuid)
    try:
        dispensary.ensure_nhis_prescription_sales(cookie, loaded)
    except Exception:
        pass

    # One Pharmacy alert per patient for this announce batch (not per medicine).
    by_patient: dict[str, list[dict[str, Any]]] = {}
    for clinical_order in loaded:
        key = _text(clinical_order.get("patientUuid")) or f"order:{clinical_order.get('uuid')}"
        by_patient.setdefault(key, []).append(clinical_order)

    results: list[dict[str, Any]] = []
    for rows in by_patient.values():
        first = rows[0]
        order_uuid = _text(first.get("uuid"))
        drugs = [_text(row.get("drugName")) for row in rows if _text(row.get("drugName"))]
        emitted = staff_notes.emit_prescription_created(
            patient_uuid=_text(first.get("patientUuid")),
            order_uuid=order_uuid,
            patient_name=_text(first.get("patientName")) or "Patient",
            mrn=_text(first.get("mrn")) or "—",
            sender_username=sender_username,
            sender_display=sender_display,
            drug_name=drugs[0] if drugs else "",
            medicine_count=len(rows),
            drug_names=drugs,
        )
        note = emitted["notification"]
        results.append(
            {
                "orderUuid": order_uuid,
                "orderUuids": [_text(row.get("uuid")) for row in rows],
                "notificationId": note.get("id"),
                "duplicate": bool(emitted.get("duplicate")),
            }
        )
    return {
        "status": "ok",
        "count": len(results),
        "notifications": results,
        "message": (
            f"{len(results)} prescription{'s' if len(results) != 1 else ''} sent to Pharmacy."
            if results
            else "No new prescriptions to announce."
        ),
    }


def _cancel_odoo_sale_for_order(odoo: dispensary.OdooReader, order_uuid: str) -> None:
    """Cancel the Odoo obligation for one drug order.

    Multi-medicine sales: remove only this sale line (and reopen/reconfirm the
    remaining unpaid bill). Single-line sales: cancel the whole sale.
    """
    matched = dispensary.sale_line_for_order(odoo, order_uuid)
    if not matched:
        return
    line, sale = matched
    sale_id = int(sale["id"])
    line_id = int(line["id"])
    if as_float(line.get("qty_delivered")) > 0.0001:
        raise ApiError(
            409,
            "prescription_dispensed",
            "This prescription has already been processed and cannot be deleted.",
        )

    siblings = dispensary.sale_prescription_lines(odoo, sale_id)
    sibling_count = len(siblings) if siblings else 1
    state = _text(sale.get("state")).lower()
    if state in {"cancel", "cancelled"}:
        return

    invoice = dispensary.related_invoice(odoo, sale)
    payment = _text((invoice or {}).get("payment_state")).lower()
    invoice_state = _text((invoice or {}).get("state")).lower()
    residual = as_float((invoice or {}).get("amount_residual"))
    total = as_float((invoice or {}).get("amount_total"))
    if invoice and invoice_state == "posted" and payment not in {"", "not_paid", "reversed"}:
        partly = payment == "partial" or (0.009 < residual < total - 0.009)
        if partly:
            raise ApiError(
                409,
                "prescription_billed",
                "This medicine has been partly paid. Ask accounts to adjust the bill before deleting it.",
            )
        _credit_paid_undispensed_line(odoo, line, sale)
        return

    if sibling_count <= 1:
        if invoice and invoice_state == "posted" and payment in {"", "not_paid"}:
            _reverse_unpaid_invoice(odoo, int(invoice["id"]))
        pickings = execute(
            odoo,
            "stock.picking",
            "search_read",
            [[("sale_id", "=", sale_id)]],
            {"fields": ["id", "state"], "limit": 20},
        )
        for picking in pickings or []:
            if _text(picking.get("state")) == "done":
                raise ApiError(
                    409,
                    "prescription_dispensed",
                    "This prescription has already been processed and cannot be deleted.",
                )
            if _text(picking.get("state")) not in {"cancel", "cancelled", "done"}:
                try:
                    execute(odoo, "stock.picking", "action_cancel", [[int(picking["id"])]])
                except Exception:
                    pass
        try:
            execute(odoo, "sale.order", "action_cancel", [[sale_id]])
        except Exception as error:
            raise ApiError(
                502,
                "prescription_cancel_failed",
                "The pharmacy bill linked to this prescription could not be cancelled.",
            ) from error
        return

    # --- Multi-line sale: cancel only this medicine's line ---
    if invoice and invoice_state == "posted" and payment in {"", "not_paid"}:
        _reverse_unpaid_invoice(odoo, int(invoice["id"]))

    product_id = many2one_id(line.get("product_id"))
    pickings = execute(
        odoo,
        "stock.picking",
        "search_read",
        [[("sale_id", "=", sale_id), ("state", "not in", ["done", "cancel"])]],
        {"fields": ["id", "state", "move_ids_without_package"], "limit": 20},
    )
    for picking in pickings or []:
        move_ids = [int(item) for item in (picking.get("move_ids_without_package") or [])]
        if not move_ids or not product_id:
            continue
        moves = odoo.read("stock.move", move_ids, ["id", "product_id", "state"])
        for move in moves:
            if many2one_id(move.get("product_id")) != product_id:
                continue
            if _text(move.get("state")) in {"done", "cancel"}:
                continue
            try:
                execute(odoo, "stock.move", "action_cancel", [[int(move["id"])]])
            except Exception:
                try:
                    execute(
                        odoo,
                        "stock.move",
                        "write",
                        [[int(move["id"])], {"product_uom_qty": 0, "quantity_done": 0}],
                    )
                except Exception:
                    pass

    try:
        execute(odoo, "sale.order.line", "unlink", [[line_id]])
    except Exception as error:
        # Confirmed sales sometimes need the order unlocked / drafted first.
        try:
            execute(odoo, "sale.order", "action_cancel", [[sale_id]])
            execute(odoo, "sale.order", "action_draft", [[sale_id]])
            execute(odoo, "sale.order.line", "unlink", [[line_id]])
            remaining = dispensary.sale_prescription_lines(odoo, sale_id)
            if remaining:
                execute(odoo, "sale.order", "action_confirm", [[sale_id]])
                refreshed = odoo.read(
                    "sale.order",
                    [sale_id],
                    ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
                )
                if refreshed:
                    dispensary.ensure_pharmacy_invoice(odoo, refreshed[0])
            return
        except Exception as nested:
            raise ApiError(
                502,
                "prescription_cancel_failed",
                "This medicine could not be removed from the pharmacy bill.",
            ) from nested

    remaining = dispensary.sale_prescription_lines(odoo, sale_id)
    if not remaining:
        try:
            execute(odoo, "sale.order", "action_cancel", [[sale_id]])
        except Exception:
            pass
        return

    # Rebuild unpaid invoice for remaining medicines when the sale is confirmed.
    refreshed = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
    )
    if refreshed and _text(refreshed[0].get("state")).lower() in {"sale", "done"}:
        _repost_remaining_bill(odoo, sale_id)
    # A draft still waiting for Pharmacy to choose quantities is not a bill yet.


def _credit_paid_undispensed_line(
    odoo: dispensary.OdooReader,
    line: dict[str, Any],
    sale: dict[str, Any],
) -> None:
    """Credit a paid medicine that was never handed over, then drop it from the queue."""
    import pharmacy_refund as refunds

    line_id = int(line["id"])
    fresh_rows = odoo.read(
        "sale.order.line",
        [line_id],
        ["id", "name", "product_id", "product_uom_qty", "price_unit", "discount", "qty_delivered"],
    )
    row = fresh_rows[0] if fresh_rows else line
    product_id = many2one_id(row.get("product_id"))
    qty = as_float(row.get("product_uom_qty")) or 1
    price = as_float(row.get("price_unit"))
    discount = as_float(row.get("discount"))
    net = round(price * (1 - (discount / 100.0)), 2)
    invoice = refunds._load_invoice(odoo, sale)
    already = refunds.line_refunded_quantities(refunds._sale_note(sale))
    if invoice and net > 0 and product_id and already.get(str(line_id), 0) <= 0:
        refunds._create_partial_credit_note(
            odoo,
            invoice=invoice,
            sale_name=_text(sale.get("name")),
            lines=[
                {
                    "product_id": product_id,
                    "name": _text(row.get("name")) or "Medicine removed",
                    "quantity": qty,
                    "price_unit": net,
                }
            ],
            reason="Pharmacy removed a medicine that had been paid and not handed over",
        )
        refunds._mark_line_refunds(
            odoo,
            int(sale["id"]),
            {str(line_id): qty},
            "pharmacy",
            fully=False,
        )
    _cancel_open_moves_for_product(odoo, int(sale["id"]), product_id)
    try:
        execute(odoo, "sale.order.line", "write", [[line_id], {"external_order_id": False}])
    except Exception:
        execute(
            odoo,
            "sale.order.line",
            "write",
            [[line_id], {"external_order_id": f"pharmacy-sale:deleted:{line_id}"}],
        )


def _cancel_open_moves_for_product(
    odoo: dispensary.OdooReader,
    sale_id: int,
    product_id: int | None,
) -> None:
    pickings = execute(
        odoo,
        "stock.picking",
        "search_read",
        [[("sale_id", "=", sale_id), ("state", "not in", ["done", "cancel"])]],
        {"fields": ["id", "state", "move_ids_without_package"], "limit": 20},
    )
    for picking in pickings or []:
        move_ids = [int(item) for item in (picking.get("move_ids_without_package") or [])]
        if not move_ids or not product_id:
            continue
        moves = odoo.read("stock.move", move_ids, ["id", "product_id", "state"])
        for move in moves:
            if many2one_id(move.get("product_id")) != product_id:
                continue
            if _text(move.get("state")) in {"done", "cancel"}:
                continue
            try:
                execute(odoo, "stock.move", "action_cancel", [[int(move["id"])]])
            except Exception:
                try:
                    execute(
                        odoo,
                        "stock.move",
                        "write",
                        [[int(move["id"])], {"product_uom_qty": 0, "quantity_done": 0}],
                    )
                except Exception:
                    pass


def _execute_quietly(odoo: dispensary.OdooReader, model: str, method: str, args: list[Any]) -> None:
    """Bill actions often succeed and then return nothing the link can send back."""
    try:
        execute(odoo, model, method, args)
    except Exception as error:
        if "cannot marshal None" not in str(error):
            raise


def _reverse_unpaid_invoice(odoo: dispensary.OdooReader, invoice_id: int) -> None:
    rows = odoo.read(
        "account.move",
        [invoice_id],
        ["id", "state", "payment_state", "amount_residual", "amount_total"],
    )
    if not rows:
        return
    invoice = rows[0]
    state = _text(invoice.get("state")).lower()
    if state == "cancel":
        return
    if _text(invoice.get("payment_state")).lower() == "reversed":
        return
    if state == "posted":
        residual = as_float(invoice.get("amount_residual"))
        total = as_float(invoice.get("amount_total"))
        if residual + 0.0001 < total:
            raise ApiError(
                409,
                "prescription_billed",
                "This prescription has already been billed and cannot be deleted.",
            )
    try:
        if state == "posted":
            _execute_quietly(odoo, "account.move", "button_draft", [[invoice_id]])
        _execute_quietly(odoo, "account.move", "button_cancel", [[invoice_id]])
    except Exception as error:
        raise ApiError(
            409,
            "prescription_cancel_failed",
            "This bill could not be deleted. Refresh and try again.",
        ) from error
    checked = odoo.read("account.move", [invoice_id], ["state"])
    if not checked or _text(checked[0].get("state")).lower() != "cancel":
        raise ApiError(
            502,
            "prescription_cancel_failed",
            "This bill could not be deleted. Refresh and try again.",
        )


def _repost_remaining_bill(odoo: dispensary.OdooReader, sale_id: int) -> None:
    """After one medicine is removed, bill whatever is still on the prescription."""
    rows = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
    )
    if not rows:
        return
    sale = rows[0]
    if _text(sale.get("state")).lower() not in {"sale", "done"}:
        return
    if dispensary.related_invoice(odoo, sale):
        return
    try:
        _execute_quietly(odoo, "sale.order", "_create_invoices", [[sale_id]])
    except Exception:
        return
    drafts = odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "out_invoice"),
            ("invoice_origin", "=", _text(sale.get("name"))),
            ("state", "=", "draft"),
        ],
        ["id"],
        limit=1,
    )
    if not drafts:
        return
    try:
        _execute_quietly(odoo, "account.move", "action_post", [[int(drafts[0]["id"])]])
    except Exception:
        return


def cancel_prescription(order_uuid: str, cookie: str) -> dict[str, Any]:
    """Void an eligible undispense OpenMRS drug order and cancel draft Odoo sale."""
    user = dispensary.require_pharmacist(cookie)
    order_uuid = _text(order_uuid)
    if not order_uuid:
        raise ApiError(422, "missing_order", "Choose a prescription to delete.")

    clinical = dispensary.load_openmrs_order(order_uuid, cookie)
    if clinical.get("stopped"):
        return {
            "status": "ok",
            "alreadyCancelled": True,
            "orderUuid": order_uuid,
            "message": "This prescription was already cancelled.",
        }

    # Prefer assembled pharmacy view when an Odoo line exists.
    try:
        assembled = dispensary.assemble_prescription(order_uuid, cookie)
    except ApiError as error:
        if error.status == 404:
            assembled = None
        else:
            raise

    payment = ""
    if assembled:
        dispensing = _text(assembled.get("dispensingStatus")).upper()
        payment = _text(assembled.get("paymentStatus")).upper()
        delivered = as_float(assembled.get("delivered")) or as_float(assembled.get("quantityDelivered"))
        if dispensing == "DISPENSED" or delivered > 0:
            raise ApiError(
                409,
                "prescription_dispensed",
                "This prescription has already been processed and cannot be deleted.",
            )
        if payment == "PARTIALLY PAID":
            raise ApiError(
                409,
                "prescription_billed",
                "This medicine has been partly paid. Ask accounts to adjust the bill before deleting it.",
            )

    odoo = odoo_reader()
    _openmrs_delete(f"/openmrs/ws/rest/v1/order/{order_uuid}", cookie)
    try:
        _cancel_odoo_sale_for_order(odoo, order_uuid)
    except ApiError:
        # The medicine is already off the prescription. A leftover charge can be cleared next.
        pass
    import pharmacy_unlisted as unlisted

    unlisted.forget(order_uuid)

    return {
        "status": "ok",
        "alreadyCancelled": False,
        "orderUuid": order_uuid,
        "cancelledBy": _text(user.get("username")),
        "message": (
            "Prescription deleted. Accounts can return the payment for this medicine."
            if payment == "PAID"
            else "Prescription deleted."
        ),
        "patientUuid": _text(clinical.get("patientUuid")),
        "drugName": _text(clinical.get("drugName")),
    }


def cancel_prescriptions(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Delete one or more unpaid/undispensed medicines."""
    dispensary.require_pharmacist(cookie)
    raw = body.get("orderUuids") or body.get("orders") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ApiError(422, "invalid_body", "Choose medicines to delete.")
    order_uuids = []
    seen: set[str] = set()
    for item in raw:
        uuid = _text(item)
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        order_uuids.append(uuid)
    if not order_uuids:
        raise ApiError(422, "missing_orders", "Choose at least one medicine to delete.")

    deleted: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    patient_uuid = ""
    for order_uuid in order_uuids:
        try:
            result = cancel_prescription(order_uuid, cookie)
            deleted.append(result)
            patient_uuid = patient_uuid or _text(result.get("patientUuid"))
        except ApiError as error:
            errors.append(
                {
                    "orderUuid": order_uuid,
                    "code": str(error.code or "cancel_failed"),
                    "message": str(error.message or "This medicine could not be deleted."),
                }
            )
    if not deleted and errors:
        first = errors[0]
        raise ApiError(409, first["code"], first["message"])
    return {
        "status": "ok",
        "count": len(deleted),
        "deleted": deleted,
        "errors": errors,
        "patientUuid": patient_uuid,
        "message": (
            f"Deleted {len(deleted)} medicine{'s' if len(deleted) != 1 else ''}."
            + (f" {len(errors)} could not be deleted." if errors else "")
        ),
    }


def cancel_sale_prescription(sale_id: str, cookie: str) -> dict[str, Any]:
    """Delete unpaid + undispensed prescription sales from Sales History."""
    import pharmacy_history as history

    user = dispensary.require_pharmacist(cookie)
    if not _text(sale_id).isdigit():
        raise ApiError(422, "invalid_sale", "Choose a sale to delete.")
    sale_id_int = int(sale_id)
    detail = history.get_sales_history_item(sale_id_int, cookie)
    if not detail.get("canDeletePrescription"):
        raise ApiError(
            409,
            "prescription_not_deletable",
            "Only unpaid prescriptions that have not been dispensed can be deleted.",
        )
    refs = [str(item) for item in (detail.get("prescriptionRefs") or []) if str(item).strip()]
    if not refs:
        raise ApiError(
            409,
            "prescription_not_deletable",
            "This sale is not linked to a deletable prescription.",
        )
    results = []
    for order_uuid in refs:
        results.append(cancel_prescription(order_uuid, cookie))
    return {
        "status": "ok",
        "saleId": str(sale_id_int),
        "cancelledBy": _text(user.get("username")),
        "orders": results,
        "message": "Prescription deleted.",
    }
