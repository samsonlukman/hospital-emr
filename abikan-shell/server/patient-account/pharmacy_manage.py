"""Hospital pharmacy catalogue add/edit.

OpenMRS Drug is created first. Atomfeed creates the Odoo product.
Prices are then written in Odoo. Catalogue add/edit does not overwrite shelf quantity.
Staff never enter technical ids.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pharmacy as dispensary
import pharmacy_catalogue
import server as core
import xmlrpc.client

ApiError = core.ApiError
OdooReader = dispensary.OdooReader
DICTIONARY_USER = os.environ.get("ABIKAN_OPENMRS_ADMIN_USER", "")
DICTIONARY_PASSWORD = os.environ.get("ABIKAN_OPENMRS_ADMIN_PASSWORD", "")

MANAGED_PARAM = "abikan.pharmacy.hospital_catalogue"
STAFF_FORMS = [
    "Tablet",
    "Injection",
    "Oral solution",
    "Powder for injection",
    "Oral capsule",
    "Capsule",
    "Drops",
    "Syrup",
    "Cream",
    "Ointment",
    "Suppository",
    "Gel",
    "Sublingual tablet",
    "Consumables",
]
UNLISTED_FORM = "Not listed"
MAX_FORM_LEN = 40
PROTECTED_TEST_DRUGS = set(pharmacy_catalogue.TEST_DRUG_UUIDS)


def _openmrs(
    method: str,
    path: str,
    cookie: str,
    payload: dict[str, Any] | None = None,
    *,
    dictionary: bool = False,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if dictionary:
        token = base64.b64encode(f"{DICTIONARY_USER}:{DICTIONARY_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    else:
        headers["Cookie"] = cookie
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{core.OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 403:
            if dictionary:
                raise ApiError(502, "dictionary_forbidden", "The medicine could not be saved.") from error
            raise ApiError(403, "forbidden", "This action requires the Pharmacy workspace.") from error
        if error.code == 400:
            raise ApiError(422, "invalid_medicine", "This medicine could not be saved. Check the name, strength, and form.") from error
        raise ApiError(502, "openmrs_error", "The medicine list could not be updated.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The medicine list could not be updated.") from error


def _text(value: Any) -> str:
    return str(value or "").strip()


def _compact(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def list_forms() -> dict[str, Any]:
    return {"status": "ok", "forms": list(STAFF_FORMS)}


DRUG_CLASS_UUID = "8d490dfc-c2cc-11de-8d13-0010c6dffd0f"
MISC_CLASS_UUID = "8d492774-c2cc-11de-8d13-0010c6dffd0f"
NA_DATATYPE_UUID = "8d4a4c94-c2cc-11de-8d13-0010c6dffd0f"


def _is_drug_class(row: dict[str, Any]) -> bool:
    if row.get("retired"):
        return False
    concept_class = row.get("conceptClass")
    if not isinstance(concept_class, dict):
        return False
    return str(concept_class.get("display") or "").strip().lower() == "drug"


def _concept_hit(row: dict[str, Any]) -> dict[str, str]:
    return {
        "uuid": _text(row.get("uuid")),
        "name": _text(row.get("display")),
    }


def search_generics(cookie: str, raw_query: str) -> dict[str, Any]:
    """Return Drug-class concepts matching the staff search.

    OpenMRS concept search is token/substring based, so short words like "add"
    can match many names. Staff must pick one UUID; Hospital EMR never invents the
    generic from the medicine/product name.
    """
    dispensary.require_pharmacist(cookie)
    term = _text(raw_query)
    if len(term) < 2:
        return {"status": "ok", "q": term, "generics": []}
    quoted = quote(term)
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept?q={quoted}&v=custom:(uuid,display,conceptClass:(display),retired)&limit=30",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    hits = [_concept_hit(row) for row in rows or [] if isinstance(row, dict) and _is_drug_class(row)]
    hits = [row for row in hits if row["uuid"] and row["name"]]
    # Prefer closer matches first: exact, then starts-with, then others.
    needle = term.lower()
    exact: list[dict[str, str]] = []
    prefix: list[dict[str, str]] = []
    other: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in hits:
        if row["uuid"] in seen:
            continue
        seen.add(row["uuid"])
        name = row["name"].lower()
        if name == needle:
            exact.append(row)
        elif name.startswith(needle):
            prefix.append(row)
        else:
            other.append(row)
    ordered = exact + prefix + other
    return {"status": "ok", "q": term, "generics": ordered[:20]}


def load_generic(cookie: str, concept_uuid: str) -> dict[str, str]:
    uuid = _text(concept_uuid)
    if not uuid:
        raise ApiError(422, "concept_required", "Search and select a generic.")
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept/{quote(uuid)}?v=custom:(uuid,display,conceptClass:(display),retired)",
        cookie,
    )
    if not isinstance(payload, dict) or not payload.get("uuid"):
        raise ApiError(422, "invalid_concept", "That generic is not in the hospital dictionary.")
    if payload.get("retired") or not _is_drug_class(payload):
        raise ApiError(422, "invalid_concept", "Choose a medicine generic from the dictionary.")
    return _concept_hit(payload)


def create_generic(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Create a Drug-class concept for Pharmacy/Admin when none exists."""
    dispensary.require_pharmacist(cookie)
    name = _text(body.get("name") or body.get("genericName"))
    if len(name) < 2:
        raise ApiError(422, "invalid_generic", "Enter the generic name.")
    existing = search_generics(cookie, name).get("generics") or []
    exact = [row for row in existing if row["name"].lower() == name.lower()]
    if len(exact) == 1:
        return {"status": "ok", "created": False, **exact[0]}
    if len(exact) > 1:
        raise ApiError(
            409,
            "ambiguous_generic",
            "More than one matching generic was found. Select the exact generic from the list.",
        )
    created = _openmrs(
        "POST",
        "/openmrs/ws/rest/v1/concept",
        cookie,
        {
            "names": [
                {
                    "name": name,
                    "locale": "en",
                    "conceptNameType": "FULLY_SPECIFIED",
                    "localePreferred": True,
                }
            ],
            "datatype": NA_DATATYPE_UUID,
            "conceptClass": DRUG_CLASS_UUID,
        },
        dictionary=True,
    )
    uuid = _text((created or {}).get("uuid"))
    display = _text((created or {}).get("display")) or name
    if not uuid:
        raise ApiError(502, "openmrs_error", "The generic could not be saved.")
    return {"status": "ok", "created": True, "uuid": uuid, "name": display}


def resolve_concept(cookie: str, generic: str) -> str:
    """Legacy free-text resolve. Prefer conceptUuid from the Generic selector."""
    needle = generic.strip()
    quoted = quote(needle)
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept?q={quoted}&v=custom:(uuid,display,conceptClass:(display),retired)&limit=20",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    drugs = [row for row in rows or [] if isinstance(row, dict) and _is_drug_class(row)]
    exact = [row for row in drugs if _text(row.get("display")).lower() == needle.lower()]
    if len(exact) == 1:
        return str(exact[0]["uuid"])
    if len(exact) > 1:
        raise ApiError(
            409,
            "ambiguous_generic",
            "More than one matching generic was found. Select the exact generic from the list.",
        )
    if not drugs:
        raise ApiError(
            409,
            "missing_generic",
            "This generic is not in the hospital dictionary yet. Search again or create the generic first.",
        )
    raise ApiError(
        409,
        "ambiguous_generic",
        "Several generics matched that search. Select the exact generic from the list.",
    )


def load_managed(odoo: OdooReader) -> list[dict[str, Any]]:
    try:
        rows = odoo.search_read("ir.config_parameter", [("key", "=", MANAGED_PARAM)], ["value"], limit=1)
    except Exception:
        # Hospital Odoo service accounts may lack Settings; catalogue still works from CSV map.
        return []
    if not rows:
        return []
    try:
        parsed = json.loads(str(rows[0].get("value") or "[]"))
    except json.JSONDecodeError:
        return []
    return [row for row in parsed if isinstance(row, dict) and row.get("drugUuid")]


def save_managed(odoo: OdooReader, rows: list[dict[str, Any]]) -> None:
    payload = json.dumps(rows)
    try:
        found = odoo.search_read("ir.config_parameter", [("key", "=", MANAGED_PARAM)], ["id"], limit=1)
    except Exception as exc:
        raise ApiError(
            503,
            "odoo_settings_required",
            "Pharmacy catalogue updates need billing settings access. Ask Hospital Admin to fix service access.",
        ) from exc
    if found:
        dispensary.execute(odoo, "ir.config_parameter", "write", [[int(found[0]["id"])], {"value": payload}])
        return
    dispensary.execute(odoo, "ir.config_parameter", "create", [{"key": MANAGED_PARAM, "value": payload}])


def upsert_managed(odoo: OdooReader, entry: dict[str, Any]) -> None:
    rows = load_managed(odoo)
    uuid = str(entry.get("drugUuid") or "")
    kept = [row for row in rows if str(row.get("drugUuid") or "") != uuid]
    kept.append(entry)
    save_managed(odoo, kept)


def drug_display_name(generic: str, strength: str, form: str) -> str:
    parts = [generic]
    if strength and _compact(strength) not in _compact(generic):
        parts.append(strength)
    if form and _compact(form) not in _compact(" ".join(parts)):
        parts.append(form)
    return " ".join(parts)


def resolve_form(cookie: str, form_name: str) -> str:
    wanted = _validate_form_name(form_name)
    quoted = quote(wanted)
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept?q={quoted}&v=custom:(uuid,display,conceptClass:(display),retired)&limit=20",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    exact = [
        row
        for row in rows or []
        if isinstance(row, dict) and not row.get("retired") and _text(row.get("display")).lower() == wanted.lower()
    ]
    if exact:
        misc = [
            row
            for row in exact
            if str((row.get("conceptClass") or {}).get("display") or "").lower() == "misc"
        ]
        return str((misc or exact)[0]["uuid"])
    return _create_form_concept(cookie, wanted)


def _validate_form_name(form_name: str) -> str:
    wanted = " ".join(_text(form_name).split())
    if not wanted or wanted.lower() == UNLISTED_FORM.lower():
        raise ApiError(422, "invalid_form", "Choose a dosage form, or write the form if it is not listed.")
    if len(wanted) < 2:
        raise ApiError(422, "invalid_form", "Write the dosage form.")
    if len(wanted) > MAX_FORM_LEN:
        raise ApiError(422, "invalid_form", "The dosage form is too long.")
    if not any(ch.isalpha() for ch in wanted):
        raise ApiError(422, "invalid_form", "Write the dosage form.")
    return wanted


def _create_form_concept(cookie: str, name: str) -> str:
    created = _openmrs(
        "POST",
        "/openmrs/ws/rest/v1/concept",
        cookie,
        {
            "names": [
                {
                    "name": name,
                    "locale": "en",
                    "conceptNameType": "FULLY_SPECIFIED",
                    "localePreferred": True,
                }
            ],
            "datatype": NA_DATATYPE_UUID,
            "conceptClass": MISC_CLASS_UUID,
        },
        dictionary=True,
    )
    uuid = _text((created or {}).get("uuid"))
    if not uuid:
        raise ApiError(409, "missing_form", "That dosage form could not be saved. Try again.")
    return uuid


def find_existing_drug(cookie: str, name: str, strength: str, form: str) -> dict[str, Any] | None:
    quoted = quote(name)
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/drug?q={quoted}&v=custom:(uuid,display,name,strength,retired,dosageForm:(display))&limit=20",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    want_name = _compact(name)
    want_strength = _compact(strength)
    want_form = _compact(form)
    for row in rows or []:
        if row.get("retired"):
            continue
        display = _text(row.get("display") or row.get("name"))
        form_name = ""
        dosage = row.get("dosageForm")
        if isinstance(dosage, dict):
            form_name = _text(dosage.get("display"))
        if _compact(display) == want_name and _compact(_text(row.get("strength"))) == want_strength:
            return row
        if (
            want_strength
            and want_strength in _compact(display)
            and want_form
            and want_form in _compact(display + " " + form_name)
        ):
            if want_name in _compact(display) or _compact(display) in want_name:
                return row
    return None


def wait_for_product(odoo: OdooReader, drug_uuid: str, timeout: int = 90) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid)
        if found:
            return found
        time.sleep(3)
    raise ApiError(
        504,
        "sync_timeout",
        "The medicine was saved but is not ready at the counter yet. Wait a moment and refresh.",
    )


def _form_category_id(odoo: OdooReader, form: str) -> int:
    wanted = [form.strip()]
    if form.strip() and not form.strip().lower().startswith("oral "):
        wanted.append(f"Oral {form.strip()}")
    for name in wanted:
        if not name:
            continue
        rows = odoo.search_read("product.category", [("name", "=", name)], ["id"], limit=1)
        if rows:
            return int(rows[0]["id"])
    rows = odoo.search_read("product.category", [("name", "=", "Drugs")], ["id"], limit=1)
    if rows:
        return int(rows[0]["id"])
    raise ApiError(502, "missing_category", "The medicine could not be added at the counter.")


def create_counter_product(odoo: OdooReader, drug_uuid: str, name: str, form: str) -> dict[str, Any]:
    category_id = _form_category_id(odoo, form)
    product_id = int(
        dispensary.execute(
            odoo,
            "product.product",
            "create",
            [
                {
                    "name": name,
                    "uuid": drug_uuid,
                    "type": "product",
                    "categ_id": category_id,
                    "list_price": 0.0,
                    "uom_id": 1,
                    "uom_po_id": 1,
                    "sale_ok": True,
                    "purchase_ok": True,
                    "invoice_policy": "order",
                    "taxes_id": [(6, 0, [])],
                    "supplier_taxes_id": [(6, 0, [])],
                }
            ],
        )
    )
    dispensary.execute(
        odoo,
        "product.product",
        "write",
        [[product_id], {"uuid": drug_uuid, "active": True, "sale_ok": True, "taxes_id": [(6, 0, [])]}],
    )
    found = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid)
    if found:
        return found
    raise ApiError(502, "counter_create_failed", "The medicine could not be added at the counter.")


def ensure_counter_product(odoo: OdooReader, drug_uuid: str, name: str, form: str) -> dict[str, Any]:
    found = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid)
    if found:
        product_id = int(found["id"])
        if not found.get("active", True):
            set_active(odoo, product_id, True)
            found = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid) or found
        return found
    return create_counter_product(odoo, drug_uuid, name, form)


def reserved_quantity(odoo: OdooReader, product_id: int, location_id: int | None) -> float:
    if not product_id or not location_id:
        return 0.0
    quants = odoo.search_read(
        "stock.quant",
        [("product_id", "=", product_id), ("location_id", "=", location_id)],
        ["reserved_quantity"],
    )
    return round(sum(dispensary.as_float(row.get("reserved_quantity")) for row in quants), 4)


def set_price(odoo: OdooReader, product_id: int, amount: float) -> None:
    dispensary.execute(
        odoo,
        "product.product",
        "write",
        [[product_id], {"list_price": amount, "taxes_id": [(6, 0, [])], "supplier_taxes_id": [(6, 0, [])]}],
    )


def set_active(odoo: OdooReader, product_id: int, available: bool) -> None:
    dispensary.execute(odoo, "product.product", "write", [[product_id], {"active": available, "sale_ok": available}])


def apply_stock(odoo: OdooReader, product_id: int, qty: float) -> None:
    location_id = dispensary.stock_location_id(odoo)
    if not location_id:
        raise ApiError(502, "missing_stock_location", "Pharmacy stock could not be updated.")
    reserved = reserved_quantity(odoo, product_id, location_id)
    if qty + 0.0001 < reserved:
        raise ApiError(
            409,
            "stock_reserved",
            "Some of this medicine is already reserved for a prescription. Enter a higher quantity.",
        )
    current = dispensary.on_hand_quantity(odoo, product_id, location_id)
    if abs(current - qty) < 0.0001:
        return
    quants = odoo.search_read(
        "stock.quant",
        [("product_id", "=", product_id), ("location_id", "=", location_id)],
        ["id"],
        limit=1,
    )
    values = {"product_id": product_id, "location_id": location_id, "inventory_quantity": qty}
    if quants:
        quant_id = int(quants[0]["id"])
        dispensary.execute(odoo, "stock.quant", "write", [[quant_id], values])
    else:
        quant_id = int(dispensary.execute(odoo, "stock.quant", "create", [values]))
    try:
        dispensary.execute(odoo, "stock.quant", "action_apply_inventory", [[quant_id]])
    except xmlrpc.client.Fault as error:
        if "cannot marshal None" not in str(error):
            raise
    after = dispensary.on_hand_quantity(odoo, product_id, location_id)
    if abs(after - qty) > 0.01:
        raise ApiError(502, "stock_update_failed", "The shelf quantity could not be updated.")


def _parse_add(body: dict[str, Any]) -> dict[str, Any]:
    product_name = _text(body.get("name") or body.get("productName") or body.get("medicineName"))
    brand = _text(body.get("brandName"))
    manufacturer = _text(body.get("manufacturer"))
    strength = _text(body.get("strength"))
    form = _text(body.get("form"))
    concept_uuid = _text(body.get("conceptUuid") or body.get("genericUuid"))
    generic_label = _text(body.get("genericName") or body.get("generic"))
    if len(product_name) < 3:
        raise ApiError(422, "invalid_name", "Enter the medicine or product name.")
    if not concept_uuid:
        # Legacy clients sent the product name as the generic. Refuse that path.
        raise ApiError(
            422,
            "concept_required",
            "Search and select a generic. The medicine name is not used to choose the generic.",
        )
    if not strength:
        raise ApiError(422, "invalid_strength", "Enter the strength as written on the pack.")
    if not form:
        raise ApiError(422, "invalid_form", "Choose a dosage form.")
    try:
        price = float(body.get("price") if body.get("price") not in (None, "") else pharmacy_catalogue.DEVELOPMENT_PRICE_NGN)
    except (TypeError, ValueError) as error:
        raise ApiError(422, "invalid_price", "Enter a selling price.") from error
    if price < 0:
        raise ApiError(422, "invalid_price", "Price cannot be negative.")
    available = body.get("available")
    if available is None:
        available = True
    return {
        "productName": product_name,
        "generic": generic_label,
        "conceptUuid": concept_uuid,
        "brand": brand,
        "manufacturer": manufacturer,
        "strength": strength,
        "form": form,
        "price": price,
        "available": bool(available),
        "name": product_name,
    }


def create_medicine(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    dispensary.require_pharmacist(cookie)
    parsed = _parse_add(body)
    concept = load_generic(cookie, parsed["conceptUuid"])
    concept_uuid = concept["uuid"]
    generic_name = concept["name"]
    form_uuid = resolve_form(cookie, parsed["form"])
    existing = find_existing_drug(cookie, parsed["name"], parsed["strength"], parsed["form"])
    if existing:
        drug_uuid = str(existing.get("uuid") or "")
        if drug_uuid in PROTECTED_TEST_DRUGS:
            raise ApiError(409, "protected_test", "That TEST medicine cannot be changed from this screen.")
    else:
        created = _openmrs(
            "POST",
            "/openmrs/ws/rest/v1/drug",
            cookie,
            {
                "name": parsed["name"],
                "concept": concept_uuid,
                "combination": False,
                "dosageForm": form_uuid,
                "strength": parsed["strength"],
            },
            dictionary=True,
        )
        drug_uuid = str((created or {}).get("uuid") or "")
        if not drug_uuid:
            raise ApiError(502, "openmrs_error", "The medicine could not be saved.")
    odoo = dispensary.odoo_reader()
    product = ensure_counter_product(odoo, drug_uuid, parsed["name"], parsed["form"])
    product_id = int(product["id"])
    previous_price = dispensary.as_float(product.get("list_price"))
    set_price(odoo, product_id, parsed["price"])
    import department_pricing as pricing

    pricing.record_pharmacy_price_change(
        drug_uuid=drug_uuid,
        item_label=parsed["name"],
        old_price=previous_price,
        new_price=parsed["price"],
        cookie=cookie,
    )
    set_active(odoo, product_id, parsed["available"])
    upsert_managed(
        odoo,
        {
            "drugUuid": drug_uuid,
            "name": parsed["name"],
            "brandName": parsed["brand"],
            "manufacturer": parsed["manufacturer"],
            "strength": parsed["strength"],
            "form": parsed["form"],
            "hospitalName": generic_name,
            "conceptUuid": concept_uuid,
        },
    )
    if not parsed["available"]:
        _openmrs(
            "POST",
            f"/openmrs/ws/rest/v1/drug/{drug_uuid}",
            cookie,
            {"retired": True},
            dictionary=True,
        )
    return {
        "status": "ok",
        "id": drug_uuid,
        "name": parsed["name"],
        "genericName": generic_name,
        "conceptUuid": concept_uuid,
    }


def create_medicines_batch(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Create several catalogue medicines in one staff action.

    Validates every row first so incomplete drafts never start creating.
    Then creates sequentially. If a later row fails, earlier rows stay saved
    and the response reports partial results honestly.
    """
    dispensary.require_pharmacist(cookie)
    raw = body.get("lines")
    if not isinstance(raw, list) or not raw:
        raise ApiError(422, "lines_required", "Add at least one medicine.")
    prepared: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ApiError(422, "invalid_line", f"Medicine {index + 1} is incomplete.")
        try:
            prepared.append({**_parse_add(row), "index": index})
        except ApiError as error:
            message = str(getattr(error, "message", "") or error)
            raise ApiError(
                getattr(error, "status", 422),
                getattr(error, "code", "invalid_line"),
                f"Medicine {index + 1}: {message}",
            ) from error

    saved: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for row in prepared:
        payload = {
            "name": row["productName"],
            "brandName": row["brand"],
            "manufacturer": row["manufacturer"],
            "strength": row["strength"],
            "form": row["form"],
            "price": row["price"],
            "available": row["available"],
            "conceptUuid": row["conceptUuid"],
            "genericName": row["generic"],
        }
        try:
            created = create_medicine(payload, cookie)
            saved.append(
                {
                    "index": row["index"],
                    "id": created.get("id"),
                    "name": created.get("name") or row["productName"],
                }
            )
        except ApiError as error:
            failed.append(
                {
                    "index": row["index"],
                    "name": row["productName"],
                    "message": str(getattr(error, "message", "") or error),
                }
            )
            break
        except Exception as error:  # noqa: BLE001 - surface unexpected create failures to staff
            failed.append(
                {
                    "index": row["index"],
                    "name": row["productName"],
                    "message": "This medicine could not be saved. Try again.",
                }
            )
            _ = error
            break

    if failed and not saved:
        raise ApiError(502, "catalogue_create_failed", failed[0]["message"])
    if failed:
        return {
            "status": "partial",
            "count": len(saved),
            "saved": saved,
            "failed": failed,
            "message": (
                f"{len(saved)} medicine{'s' if len(saved) != 1 else ''} added. "
                f"Stopped at medicine {failed[0]['index'] + 1}: {failed[0]['message']}"
            ),
        }
    return {
        "status": "ok",
        "count": len(saved),
        "saved": saved,
        "failed": [],
        "message": f"{len(saved)} medicine{'s' if len(saved) != 1 else ''} added to the catalogue.",
    }


def update_medicine(item_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    dispensary.require_pharmacist(cookie)
    drug_uuid = _text(item_id)
    if not drug_uuid:
        raise ApiError(404, "not_found", "That medicine was not found.")
    if drug_uuid in PROTECTED_TEST_DRUGS:
        raise ApiError(409, "protected_test", "The dedicated TEST medicine cannot be changed from this screen.")
    odoo = dispensary.odoo_reader()
    product = dispensary.find_pharmacy_products(odoo, [drug_uuid]).get(drug_uuid)
    if not product:
        raise ApiError(404, "not_found", "That medicine was not found.")
    product_id = int(product["id"])
    if "price" in body and body.get("price") not in (None, ""):
        try:
            price = float(body.get("price"))
        except (TypeError, ValueError) as error:
            raise ApiError(422, "invalid_price", "Enter a selling price.") from error
        if price < 0:
            raise ApiError(422, "invalid_price", "Price cannot be negative.")
        previous_price = dispensary.as_float(product.get("list_price"))
        set_price(odoo, product_id, price)
        import department_pricing as pricing

        pricing.record_pharmacy_price_change(
            drug_uuid=drug_uuid,
            item_label=str(product.get("name") or drug_uuid),
            old_price=previous_price,
            new_price=price,
            cookie=cookie,
        )
    if "available" in body:
        available = bool(body.get("available"))
        set_active(odoo, product_id, available)
        _openmrs(
            "POST",
            f"/openmrs/ws/rest/v1/drug/{drug_uuid}",
            cookie,
            {"retired": not available},
            dictionary=True,
        )
    managed = {
        "drugUuid": drug_uuid,
        "name": _text(product.get("name")) or drug_uuid,
        "brandName": _text(body.get("brandName")),
        "manufacturer": _text(body.get("manufacturer")),
        "strength": _text(body.get("strength")),
        "form": _text(body.get("form")),
        "hospitalName": _text(body.get("name") or body.get("genericName") or product.get("name")),
    }
    if managed["strength"] or managed["form"] or managed["brandName"] or managed["manufacturer"] or body.get("name"):
        current = next((row for row in load_managed(odoo) if row.get("drugUuid") == drug_uuid), {})
        if not managed["strength"]:
            managed["strength"] = _text(current.get("strength"))
        if not managed["form"]:
            managed["form"] = _text(current.get("form"))
        if "brandName" not in body:
            managed["brandName"] = _text(current.get("brandName"))
        if "manufacturer" not in body:
            managed["manufacturer"] = _text(current.get("manufacturer"))
        if not managed["hospitalName"]:
            managed["hospitalName"] = _text(current.get("hospitalName") or current.get("name"))
        if current.get("conceptUuid"):
            managed["conceptUuid"] = _text(current.get("conceptUuid"))
        upsert_managed(odoo, managed)
    return {"status": "ok", "id": drug_uuid}


def extra_catalogue_rows(odoo: OdooReader) -> list[dict[str, Any]]:
    extras: list[dict[str, Any]] = []
    mapped_uuids = {str(row.get("drugUuid") or "") for row in pharmacy_catalogue.mapped_entries()}
    for row in load_managed(odoo):
        uuid = str(row.get("drugUuid") or "")
        if not uuid or uuid in mapped_uuids:
            continue
        extras.append(
            {
                "sn": uuid,
                "hospitalName": row.get("hospitalName") or row.get("name") or "",
                "action": "create",
                "drugUuid": uuid,
                "openmrsName": row.get("name") or "",
                "strength": row.get("strength") or "",
                "dosageFormName": row.get("form") or "",
                "brandName": row.get("brandName") or "",
                "developmentPriceNgn": pharmacy_catalogue.DEVELOPMENT_PRICE_NGN,
            }
        )
    return extras


def brand_by_uuid(odoo: OdooReader) -> dict[str, str]:
    return {
        str(row.get("drugUuid") or ""): str(row.get("brandName") or "")
        for row in load_managed(odoo)
        if row.get("drugUuid")
    }
