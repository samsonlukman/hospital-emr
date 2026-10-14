"""Department catalogue pricing.

Writes Odoo product.product.list_price for department catalogue items.
Laboratory can also create a missing hospital fee product when a price is saved.
Does not invent invoices. Historical sale.order.line / account.move amounts stay
whatever was stored at charge time.
"""

from __future__ import annotations

import math
from typing import Any

import lab_catalogue
import laboratory as lab_billing
import pharmacy as dispensary
import pharmacy_manage
import price_history
import registration as reception
import server as core
from accountant import is_accountant, load_openmrs_user
from hospital_admin import is_hospital_admin, is_technical_superadmin
from pharmacy import is_pharmacist
from registration import is_registrar

ApiError = core.ApiError
format_money = core.format_money

DEPARTMENTS = price_history.DEPARTMENTS
NGN = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}


def parse_catalogue_price(raw: Any) -> float:
    if isinstance(raw, bool) or raw is None:
        raise ApiError(422, "invalid_price", "Enter a price of zero or more.")
    if isinstance(raw, str):
        text = raw.strip().replace(",", "").replace("₦", "").replace("NGN", "").strip()
        if not text or text.lower() in {"nan", "inf", "+inf", "-inf", "infinity"}:
            raise ApiError(422, "invalid_price", "Enter a price of zero or more.")
        raw = text
    try:
        amount = float(raw)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_price", "Enter a price of zero or more.") from error
    if not math.isfinite(amount) or amount < 0:
        raise ApiError(422, "invalid_price", "The price cannot be negative.")
    return round(amount, 2)


def _actor(cookie: str, user: dict[str, Any]) -> dict[str, Any]:
    display = str(user.get("username") or "")
    try:
        session = core.openmrs_get("/openmrs/ws/rest/v1/session", cookie)
        person = (session.get("user") or {}).get("person") if isinstance(session, dict) else {}
        if isinstance(person, dict) and person.get("display"):
            display = str(person.get("display"))
        elif isinstance(session, dict) and (session.get("user") or {}).get("display"):
            display = str((session.get("user") or {}).get("display"))
    except ApiError:
        pass
    return {
        "uuid": str(user.get("uuid") or ""),
        "username": str(user.get("username") or ""),
        "display": display,
    }


def can_write_pricing(user: dict[str, Any], department: str) -> bool:
    if department == "reception":
        return is_registrar(user)
    if department == "laboratory":
        return lab_billing.is_lab_user(user)
    if department == "pharmacy":
        return is_pharmacist(user)
    return False


def can_read_pricing(user: dict[str, Any], department: str) -> bool:
    if can_write_pricing(user, department):
        return True
    if is_accountant(user) or is_hospital_admin(user) or is_technical_superadmin(user):
        return True
    return False


def require_pricing_read(cookie: str, department: str) -> dict[str, Any]:
    core.require_session(cookie)
    if department not in DEPARTMENTS:
        raise ApiError(404, "not_found", "That pricing list was not found.")
    user = load_openmrs_user(cookie)
    if not can_read_pricing(user, department):
        raise ApiError(403, "forbidden", "This action is not available in this department.")
    return user


def require_pricing_write(cookie: str, department: str) -> dict[str, Any]:
    core.require_session(cookie)
    if department not in DEPARTMENTS:
        raise ApiError(404, "not_found", "That pricing list was not found.")
    user = load_openmrs_user(cookie)
    if not can_write_pricing(user, department):
        raise ApiError(403, "forbidden", "This department cannot change those prices.")
    return user


def _serialize_change(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    currency = dict(NGN)
    currency["code"] = str(row.get("currency") or "NGN")
    return {
        "occurredAt": row.get("occurred_at"),
        "department": row.get("department"),
        "itemId": row.get("item_id"),
        "itemLabel": row.get("item_label"),
        "oldPrice": format_money(float(row.get("old_price") or 0), currency),
        "newPrice": format_money(float(row.get("new_price") or 0), currency),
        "changedBy": row.get("actor_display") or row.get("actor_username") or "",
        "username": row.get("actor_username") or "",
        "reason": row.get("reason") or "",
    }


def _attach_history(department: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        item["lastChange"] = _serialize_change(
            price_history.latest_change(department, str(item.get("id") or ""))
        )
    return items


def list_department_prices(department: str, cookie: str, query: str = "") -> dict[str, Any]:
    user = require_pricing_read(cookie, department)
    if department == "reception":
        items = _reception_items()
    elif department == "laboratory":
        items = _laboratory_items(query)
    else:
        items = _pharmacy_items(cookie, query)
    return {
        "status": "ok",
        "department": department,
        "currency": {"code": "NGN", "symbol": "₦", "decimalPlaces": 2},
        "canWrite": can_write_pricing(user, department),
        "message": "Changing a price does not change bills already created.",
        "items": _attach_history(department, items),
    }


def list_item_history(department: str, item_id: str, cookie: str) -> dict[str, Any]:
    require_pricing_read(cookie, department)
    rows = price_history.list_price_changes(department=department, item_id=item_id, limit=20)
    return {
        "status": "ok",
        "department": department,
        "itemId": item_id,
        "history": [_serialize_change(row) for row in rows],
    }


def update_department_price(department: str, item_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_pricing_write(cookie, department)
    amount = parse_catalogue_price(body.get("price") if "price" in body else body.get("listPrice"))
    expected = body.get("expectedPrice")
    expected_amount = parse_catalogue_price(expected) if expected not in (None, "") else None
    reason = str(body.get("reason") or "").strip()
    if department == "reception":
        _update_reception(item_id, amount, expected_amount, user, cookie, reason)
    elif department == "laboratory":
        _update_laboratory(item_id, amount, expected_amount, user, cookie, reason)
    else:
        _update_pharmacy(item_id, amount, expected_amount, user, cookie, reason)
    return list_department_prices(department, cookie)


def record_pharmacy_price_change(
    *,
    drug_uuid: str,
    item_label: str,
    old_price: float,
    new_price: float,
    cookie: str,
    user: dict[str, Any] | None = None,
) -> None:
    actor = _actor(cookie, user or load_openmrs_user(cookie))
    price_history.record_price_change(
        department="pharmacy",
        item_id=drug_uuid,
        item_label=item_label,
        currency="NGN",
        old_price=old_price,
        new_price=new_price,
        actor=actor,
    )


def _reception_items() -> list[dict[str, Any]]:
    import antenatal as anc

    odoo = reception.odoo_reader()
    masters = reception.ensure_registration_masters(odoo)
    currency = reception.registration_currency(odoo)
    items = []
    for card_id, spec in reception.card_specs().items():
        product = (masters.get("products") or {}).get(card_id) or {}
        amount = core.as_float(product.get("list_price"))
        if amount <= 0:
            amount = core.as_float(spec.get("amount"))
        items.append(
            {
                "id": card_id,
                "name": spec.get("label") or product.get("name") or card_id,
                "kind": "card",
                "mapping": reception.PRODUCT_CODES.get(card_id) or "",
                "editable": bool(product.get("id")),
                "price": format_money(amount, currency),
            }
        )
    # ANC enrollment fee is a separate service price — not a hospital registration card.
    anc_masters = anc.ensure_anc_masters(odoo)
    anc_product = anc_masters.get("product") or {}
    anc_amount = core.as_float(anc_product.get("list_price")) or anc.ANC_DEFAULT_AMOUNT
    items.append(
        {
            "id": "anc",
            "name": anc.ANC_PRODUCT_NAME,
            "kind": "service-fee",
            "mapping": anc.ANC_PRODUCT_CODE,
            "editable": bool(anc_product.get("id")),
            "price": format_money(anc_amount, currency),
        }
    )
    return items


def _laboratory_items(query: str) -> list[dict[str, Any]]:
    odoo = None
    currency = dict(NGN)
    try:
        odoo = lab_billing.odoo_reader()
        currency = lab_billing.lab_currency(odoo)
    except ApiError:
        odoo = None
    rows = list(lab_catalogue.search_entries(query, include_unorderable=False))
    products = (
        lab_billing.find_lab_pricing_products(
            odoo,
            [str(row.get("conceptUuid") or "") for row in rows],
        )
        if odoo
        else {}
    )
    items = []
    for row in rows:
        concept = str(row.get("conceptUuid") or "")
        live = None
        editable = bool(odoo and concept)
        note = ""
        product = products.get(concept)
        if product:
            live = core.as_float(product.get("list_price"))
        elif odoo and concept:
            note = "No hospital fee yet. Enter a price to add it."
            if row.get("priceNgn") is not None:
                live = float(row["priceNgn"])
        serialized = lab_catalogue.serialize_entry(row, live_price=live, currency=currency)
        items.append(
            {
                "id": concept or str(row.get("sn") or ""),
                "catalogueId": row.get("sn"),
                "name": serialized.get("name"),
                "kind": "laboratory-test",
                "mapping": concept,
                "specimen": serialized.get("specimen") or "",
                "type": serialized.get("type") or "",
                "editable": editable,
                "note": note,
                "price": serialized.get("price"),
            }
        )
    return items


def _pharmacy_items(cookie: str, query: str) -> list[dict[str, Any]]:
    payload = dispensary.build_catalogue(cookie, query, enforce_pharmacist=False)
    items = []
    for row in payload.get("items") or []:
        items.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "kind": "medicine",
                "mapping": row.get("id") or "",
                "strength": row.get("strength") or "",
                "form": row.get("form") or "",
                "editable": bool(row.get("canEdit")),
                "price": row.get("price"),
            }
        )
    return items


def _guard_expected(current: float, expected: float | None) -> None:
    if expected is None:
        return
    if not math.isclose(round(current, 2), round(expected, 2), abs_tol=0.004):
        raise ApiError(
            409,
            "price_changed",
            "Someone else already saved a different price. Refresh and try again.",
        )


def _update_reception(
    item_id: str,
    amount: float,
    expected: float | None,
    user: dict[str, Any],
    cookie: str,
    reason: str,
) -> None:
    if item_id in {"anc", "antenatal"}:
        import antenatal as anc

        odoo = reception.odoo_reader()
        product = (anc.ensure_anc_masters(odoo).get("product") or {})
        if not product.get("id"):
            raise ApiError(404, "not_found", "Antenatal Care pricing was not found.")
        current = core.as_float(product.get("list_price")) or anc.ANC_DEFAULT_AMOUNT
        _guard_expected(current, expected)
        if math.isclose(current, amount, abs_tol=0.004):
            return
        anc.execute(
            odoo,
            "product.product",
            "write",
            [[int(product["id"])], {"list_price": amount, "taxes_id": [(6, 0, [])]}],
        )
        price_history.record_price_change(
            department="reception",
            item_id="anc",
            item_label=anc.ANC_PRODUCT_NAME,
            currency="NGN",
            old_price=current,
            new_price=amount,
            actor=_actor(cookie, user),
            reason=reason,
        )
        return
    if item_id not in reception.PRODUCT_CODES:
        raise ApiError(404, "not_found", "That card was not found.")
    odoo = reception.odoo_reader()
    masters = reception.ensure_registration_masters(odoo)
    product = (masters.get("products") or {}).get(item_id)
    if not product:
        raise ApiError(404, "not_found", "That card was not found.")
    current = core.as_float(product.get("list_price"))
    _guard_expected(current, expected)
    if math.isclose(current, amount, abs_tol=0.004):
        return
    reception.execute(
        odoo,
        "product.product",
        "write",
        [[int(product["id"])], {"list_price": amount, "taxes_id": [(6, 0, [])]}],
    )
    spec = reception.card_specs().get(item_id) or {}
    price_history.record_price_change(
        department="reception",
        item_id=item_id,
        item_label=str(spec.get("label") or product.get("name") or item_id),
        currency="NGN",
        old_price=current,
        new_price=amount,
        actor=_actor(cookie, user),
        reason=reason,
    )


def _update_laboratory(
    item_id: str,
    amount: float,
    expected: float | None,
    user: dict[str, Any],
    cookie: str,
    reason: str,
) -> None:
    entry = lab_catalogue.entry_by_concept(item_id)
    if not entry or not entry.get("conceptUuid"):
        raise ApiError(404, "not_found", "That laboratory test was not found in the hospital list.")
    if entry.get("conceptUuid") != item_id:
        raise ApiError(409, "identity_locked", "The test itself cannot be changed from pricing.")
    odoo = lab_billing.odoo_reader()
    import laboratory_manage as lab_manage

    label = str(entry.get("hospitalName") or entry.get("openmrsName") or item_id)
    try:
        product = lab_billing.find_lab_pricing_product(odoo, item_id)
    except ApiError as error:
        if error.code != "missing_mapping":
            raise
        product = lab_manage.ensure_lab_fee_product(
            odoo,
            item_id,
            name=label,
            list_price=0.0,
        )
    current = core.as_float(product.get("list_price"))
    # Newly created fee products start at 0; the screen may still show a catalogue
    # list price that is not an Odoo value yet, so skip the concurrency guard.
    if current > lab_catalogue.LAB_PLACEHOLDER_PRICE:
        _guard_expected(current, expected)
    if math.isclose(current, amount, abs_tol=0.004):
        return
    lab_billing.execute(
        odoo,
        "product.product",
        "write",
        [[int(product["id"])], {"list_price": amount, "taxes_id": [(6, 0, [])], "supplier_taxes_id": [(6, 0, [])]}],
    )
    price_history.record_price_change(
        department="laboratory",
        item_id=item_id,
        item_label=label,
        currency="NGN",
        old_price=current,
        new_price=amount,
        actor=_actor(cookie, user),
        reason=reason,
        details={"conceptUuid": item_id, "catalogueSn": entry.get("sn")},
    )


def _update_pharmacy(
    item_id: str,
    amount: float,
    expected: float | None,
    user: dict[str, Any],
    cookie: str,
    reason: str,
) -> None:
    if item_id in pharmacy_manage.PROTECTED_TEST_DRUGS:
        raise ApiError(409, "protected_test", "The dedicated TEST medicine cannot be changed from this screen.")
    odoo = dispensary.odoo_reader()
    product = dispensary.find_pharmacy_products(odoo, [item_id]).get(item_id)
    if not product:
        raise ApiError(404, "not_found", "That medicine was not found.")
    current = core.as_float(product.get("list_price"))
    _guard_expected(current, expected)
    if math.isclose(current, amount, abs_tol=0.004):
        return
    pharmacy_manage.set_price(odoo, int(product["id"]), amount)
    price_history.record_price_change(
        department="pharmacy",
        item_id=item_id,
        item_label=str(product.get("name") or item_id),
        currency="NGN",
        old_price=current,
        new_price=amount,
        actor=_actor(cookie, user),
        reason=reason,
    )
