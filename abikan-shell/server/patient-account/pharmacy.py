"""Pharmacy counter dispensing.

Odoo picking validation is the stock write. OpenMRS Dispensed is never written.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import xmlrpc.client

import server as core

PHARMACY_PRIVILEGE = "bahmni:clinical:dispense"
CLINICAL_PRIVILEGE = "app:clinical"
PHARMACY_ROLES = {"SuperAdmin", "System Developer"}
CLINICAL_ROLES = {"Doctor", "Clinician", "Nurse", "Abikan:Clinical", "Abikan:Nursing"}
STOCK_LOCATION_NAME = "WH/Stock"
CONSULTATION_NOTE_CONCEPT = "d37294c5-5e07-11ef-8f7c-0242ac120002"

ApiError = core.ApiError
OdooReader = core.OdooReader
ODOO_DB = core.ODOO_DB
ODOO_PASSWORD = core.ODOO_PASSWORD
as_float = core.as_float
find_partner = core.find_partner


def billing_partner(odoo: OdooReader, patient: dict[str, str]) -> dict[str, Any] | None:
    """The person's bill account. A Family Card does not create one by itself."""
    found = find_partner(odoo, patient)
    if found:
        return found
    import registration as reception

    return reception.ensure_patient_partner(odoo, patient, wait=False)
many2one_id = core.many2one_id
many2one_name = core.many2one_name
require_session = core.require_session

IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}


def execute(
    odoo: OdooReader,
    model: str,
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    return odoo.models.execute_kw(
        ODOO_DB,
        odoo.uid,
        ODOO_PASSWORD,
        model,
        method,
        args,
        kwargs or {},
    )


def odoo_reader() -> OdooReader:
    return core.OdooReader()


def load_openmrs_user(cookie: str) -> dict[str, Any]:
    import accountant as cashier

    return cashier.load_openmrs_user(cookie)


def is_pharmacist(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return bool(roles & PHARMACY_ROLES) or PHARMACY_PRIVILEGE in privileges


def require_pharmacist(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if not is_pharmacist(user):
        raise ApiError(
            403,
            "forbidden",
            "This action requires the Pharmacy workspace.",
        )
    return user


def require_catalogue_reader(cookie: str) -> dict[str, Any]:
    """Allow Pharmacy and clinical staff to read medicine prices."""
    require_session(cookie)
    user = load_openmrs_user(cookie)
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    if is_pharmacist(user) or CLINICAL_PRIVILEGE in privileges or roles & CLINICAL_ROLES:
        return user
    raise ApiError(403, "forbidden", "This action requires a clinical or Pharmacy workspace.")


NGN_CURRENCY = {"code": "NGN", "symbol": "₦"}


def _openmrs_json(path: str, cookie: str) -> dict[str, Any] | list[Any] | None:
    request = Request(
        f"{core.OPENMRS_URL}{path}",
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
            return None
        raise ApiError(502, "openmrs_error", "The prescription could not be loaded.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", "The prescription could not be loaded.") from error


def _text(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def _display(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display") or value.get("name") or "")
    return _text(value)


def _instructions(raw: Any) -> str:
    text = _text(raw)
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("instructions"):
            return str(parsed["instructions"])
    except (TypeError, ValueError):
        pass
    return text


def _doctor_notes(encounter_uuid: str, cookie: str) -> list[dict[str, str]]:
    if not encounter_uuid:
        return []
    try:
        payload = _openmrs_json(
            f"/openmrs/ws/rest/v1/encounter/{encounter_uuid}"
            "?v=custom:(obs:(uuid,concept:(uuid),value,obsDatetime,creator:(display),voided))",
            cookie,
        )
    except ApiError:
        return []
    if not isinstance(payload, dict):
        return []
    notes: list[dict[str, str]] = []
    for obs in payload.get("obs") or []:
        if not isinstance(obs, dict) or obs.get("voided"):
            continue
        concept = obs.get("concept") if isinstance(obs.get("concept"), dict) else {}
        if str(concept.get("uuid") or "") != CONSULTATION_NOTE_CONCEPT:
            continue
        content = _text(obs.get("value")).strip()
        if not content:
            continue
        creator = obs.get("creator") if isinstance(obs.get("creator"), dict) else {}
        notes.append(
            {
                "content": content,
                "recordedAt": _text(obs.get("obsDatetime")),
                "authorName": _text(creator.get("display")) or "Doctor",
            }
        )
    notes.sort(key=lambda row: row["recordedAt"], reverse=True)
    return notes


def _looks_like_tablet(value: str) -> bool:
    text = value.strip().casefold().replace(".", "")
    return text in {"tablet", "tablets", "tablet(s)", "tab", "tabs"}


def _generic_dose_unit(value: str) -> bool:
    text = value.strip().casefold().replace(".", "").replace("(s)", "")
    return _looks_like_tablet(text) or text in {"unit", "units"}


def displayed_dosage_unit(saved: str, form: str) -> str:
    """Show the medicine form when the saved unit is only tablet or unit."""
    chosen = form.strip()
    current = saved.strip()
    if not chosen:
        return current
    if _looks_like_tablet(chosen):
        return current or chosen
    if not current or _generic_dose_unit(current):
        return chosen
    return current


def _drug_dosage_form(drug_uuid: str, cookie: str) -> str:
    if not drug_uuid:
        return ""
    try:
        import medication_administration as mar

        found = mar.dosage_forms_for([drug_uuid]).get(drug_uuid, "")
        if found:
            return found
    except Exception:
        found = ""
    try:
        row = _openmrs_json(
            f"/openmrs/ws/rest/v1/drug/{quote(drug_uuid)}?v=custom:(dosageForm:(display))",
            cookie,
        )
    except ApiError:
        return ""
    if not isinstance(row, dict):
        return ""
    return _display(row.get("dosageForm"))


def load_openmrs_order(order_uuid: str, cookie: str) -> dict[str, Any]:
    rich = (
        f"/openmrs/ws/rest/v1/order/{order_uuid}?v=custom:(uuid,orderNumber,action,voided,dateStopped,"
        "dateActivated,autoExpireDate,patient:(uuid,display),orderer:(display),"
        "encounter:(uuid),"
        "careSetting:(display),drug:(uuid,display,name,strength),drugNonCoded,dose,doseUnits:(display),"
        "frequency:(display),route:(display),quantity,quantityUnits:(display),duration,"
        "durationUnits:(display),dosingInstructions)"
    )
    simple = (
        f"/openmrs/ws/rest/v1/order/{order_uuid}?v=custom:(uuid,orderNumber,action,dateStopped,"
        "dateActivated,autoExpireDate,patient:(uuid,display),orderer:(display),careSetting:(display))"
    )
    try:
        core_order = _openmrs_json(rich, cookie)
    except ApiError as error:
        if error.status == 401:
            raise
        core_order = _openmrs_json(simple, cookie)
    if not isinstance(core_order, dict) or not core_order.get("uuid"):
        raise ApiError(404, "prescription_not_found", "This prescription was not found.")
    try:
        drug = _openmrs_json(f"/openmrs/ws/rest/v1/bahmnicore/drugOrders/{order_uuid}", cookie)
    except ApiError as error:
        if error.status == 401:
            raise
        drug = None
    drug = drug if isinstance(drug, dict) else {}
    nested = drug.get("drugOrder") if isinstance(drug.get("drugOrder"), dict) else {}
    merged = {**(nested or {}), **drug}
    dosing = merged.get("dosingInstructions") if isinstance(merged.get("dosingInstructions"), dict) else {}
    patient = core_order.get("patient") if isinstance(core_order.get("patient"), dict) else {}
    display = (patient.get("display") or "").strip()
    name = display
    mrn = ""
    if " - " in display:
        left, right = display.split(" - ", 1)
        mrn = left.strip()
        name = right.strip()
    stopped = bool(
        core_order.get("voided")
        or core_order.get("dateStopped")
        or core_order.get("action") == "DISCONTINUE"
    )
    duration = ""
    if merged.get("duration") not in (None, ""):
        duration = f"{merged.get('duration')} {_display(merged.get('durationUnits'))}".strip()
    elif core_order.get("duration") not in (None, ""):
        duration = f"{core_order.get('duration')} {_display(core_order.get('durationUnits'))}".strip()
    drug_ref = merged.get("drug") if isinstance(merged.get("drug"), dict) else {}
    if not drug_ref:
        drug_ref = core_order.get("drug") if isinstance(core_order.get("drug"), dict) else {}
    orderer = core_order.get("orderer") if isinstance(core_order.get("orderer"), dict) else {}
    encounter = core_order.get("encounter") if isinstance(core_order.get("encounter"), dict) else {}
    care = core_order.get("careSetting") if isinstance(core_order.get("careSetting"), dict) else {}
    drug_non_coded = _text(merged.get("drugNonCoded")) or _text(core_order.get("drugNonCoded"))
    listed_name = _text(drug_ref.get("name")) or _text(drug_ref.get("display"))
    if listed_name.lower() in {"drugother", "drug other"}:
        listed_name = ""
    dosage_form = _drug_dosage_form(_text(drug_ref.get("uuid")), cookie)
    return {
        "uuid": core_order.get("uuid") or order_uuid,
        "orderNumber": core_order.get("orderNumber") or merged.get("orderNumber") or "",
        "action": core_order.get("action") or "",
        "stopped": stopped,
        "patientUuid": patient.get("uuid") or "",
        "patientName": name or "Unknown patient",
        "mrn": mrn,
        "prescriber": orderer.get("display") or merged.get("creatorName") or "",
        "doctorNotes": _doctor_notes(str(encounter.get("uuid") or ""), cookie),
        "ordered": core_order.get("dateActivated") or "",
        "encounterUuid": encounter.get("uuid") or "",
        "careSetting": care.get("display") or merged.get("careSetting") or "",
        "drugUuid": _text(drug_ref.get("uuid")),
        "drugNonCoded": drug_non_coded,
        "drugName": listed_name
        or drug_non_coded
        or _display(core_order.get("drug"))
        or "Medication",
        "strength": drug_ref.get("strength") or "",
        "dose": _text(dosing.get("dose")) or _text(core_order.get("dose")),
        "doseUnits": displayed_dosage_unit(
            _display(dosing.get("doseUnits")) or _display(core_order.get("doseUnits")),
            dosage_form,
        ),
        "route": _display(dosing.get("route")) or _display(core_order.get("route")),
        "frequency": _display(dosing.get("frequency")) or _display(core_order.get("frequency")),
        "duration": duration,
        "quantity": as_float(dosing.get("quantity")) or as_float(core_order.get("quantity")),
        "quantityUnits": displayed_dosage_unit(
            _display(dosing.get("quantityUnits")) or _display(core_order.get("quantityUnits")),
            dosage_form,
        ),
        "instructions": _instructions(dosing.get("administrationInstructions"))
        or _text(merged.get("instructions")),
    }


def stock_location_id(odoo: OdooReader, _sale: dict[str, Any] | None = None) -> int | None:
    rows = odoo.search_read(
        "stock.location",
        [("complete_name", "=", STOCK_LOCATION_NAME), ("usage", "=", "internal")],
        ["id"],
        limit=1,
    )
    if rows:
        return int(rows[0]["id"])
    rows = odoo.search_read(
        "stock.location",
        [("name", "=", "Stock"), ("usage", "=", "internal")],
        ["id"],
        limit=1,
    )
    return int(rows[0]["id"]) if rows else None


def on_hand_quantity(odoo: OdooReader, product_id: int, location_id: int | None) -> float:
    if not product_id or not location_id:
        return 0.0
    return on_hand_quantities(odoo, [product_id], location_id).get(int(product_id), 0.0)


def on_hand_quantities(
    odoo: OdooReader,
    product_ids: list[int],
    location_id: int | None,
) -> dict[int, float]:
    wanted = {int(item) for item in product_ids if item}
    if not wanted or not location_id:
        return {item: 0.0 for item in wanted}
    quants = odoo.search_read(
        "stock.quant",
        [("product_id", "in", list(wanted)), ("location_id", "=", location_id)],
        ["product_id", "quantity"],
        limit=max(len(wanted) * 8, 200),
    )
    totals = {item: 0.0 for item in wanted}
    for row in quants:
        product_id = many2one_id(row.get("product_id"))
        if product_id in totals:
            totals[product_id] += as_float(row.get("quantity"))
    return {key: round(value, 4) for key, value in totals.items()}


NON_PHARMACY_PREFIXES = (
    "registration:",
    "consultation:",
    "lab:",
    "radiology:",
    "accommodation:",
    "pharmacy-sale:",
)


def is_pharmacy_external_id(value: str) -> bool:
    text = str(value or "").strip()
    if not text or "-" not in text:
        return False
    return not text.startswith(NON_PHARMACY_PREFIXES)


def _pharmacy_currency() -> dict[str, str]:
    return dict(NGN_CURRENCY)


def _format_ngn(amount: float | None, currency: dict[str, str] | None = None) -> dict[str, Any] | None:
    if amount is None:
        return None
    symbol = (currency or NGN_CURRENCY).get("symbol") or "₦"
    code = (currency or NGN_CURRENCY).get("code") or "NGN"
    return {
        "amount": amount,
        "formatted": f"{symbol}{amount:,.0f}",
        "currencyCode": code,
        "currencySymbol": symbol,
    }


def _listed_as(hospital_name: str, product_name: str) -> str:
    def compact(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    hospital = compact(hospital_name)
    product = compact(product_name)
    if not hospital or hospital == product or hospital in product or product in hospital:
        return ""
    return hospital_name.strip()


def find_pharmacy_products(odoo: OdooReader, drug_uuids: list[str]) -> dict[str, dict[str, Any]]:
    uuids = [item for item in drug_uuids if item]
    if not uuids:
        return {}
    rows = execute(
        odoo,
        "product.product",
        "search_read",
        [[("uuid", "in", uuids)]],
        {
            "fields": ["id", "name", "list_price", "uuid", "active", "uom_id"],
            "limit": max(len(uuids), 1),
            "context": {"active_test": False},
        },
    )
    found: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        key = str(row.get("uuid") or "")
        if key and key not in found:
            found[key] = row
    return found


def build_catalogue(cookie: str, query: str = "", *, enforce_pharmacist: bool = True) -> dict[str, Any]:
    if enforce_pharmacist:
        require_pharmacist(cookie)
    import pharmacy_catalogue
    import pharmacy_manage

    currency = _pharmacy_currency()
    odoo = odoo_reader()
    entries = list(pharmacy_catalogue.search_mapped_entries(""))
    entries.extend(pharmacy_manage.extra_catalogue_rows(odoo))
    brands = pharmacy_manage.brand_by_uuid(odoo)
    location_id = stock_location_id(odoo)
    products = find_pharmacy_products(
        odoo,
        [str(row.get("drugUuid") or "") for row in entries],
    )
    stock_by_product = on_hand_quantities(
        odoo,
        [int(row["id"]) for row in products.values() if row.get("id")],
        location_id,
    )
    needle = query.strip().lower()
    items: list[dict[str, Any]] = []
    for row in entries:
        drug_uuid = str(row.get("drugUuid") or "")
        product = products.get(drug_uuid) or {}
        product_id = int(product["id"]) if product.get("id") else 0
        on_hand = stock_by_product.get(product_id, 0.0) if product_id else 0.0
        live_price = as_float(product.get("list_price")) if product else None
        if live_price is None:
            live_price = float(row.get("developmentPriceNgn") or pharmacy_catalogue.DEVELOPMENT_PRICE_NGN)
        name = str(row.get("openmrsName") or row.get("createName") or row.get("hospitalName") or "Medicine")
        form = str(row.get("dosageFormName") or many2one_name(product.get("uom_id")) or "")
        available = bool(product.get("active", True)) if product else False
        brand = str(row.get("brandName") or brands.get(drug_uuid) or "")
        hay = " ".join([name, str(row.get("hospitalName") or ""), brand, str(row.get("strength") or ""), form]).lower()
        if needle and needle not in hay:
            continue
        items.append(
            {
                "id": drug_uuid or str(row.get("sn") or ""),
                "name": name,
                "hospitalName": str(row.get("hospitalName") or ""),
                "listedAs": _listed_as(str(row.get("hospitalName") or ""), name),
                "brandName": brand,
                "strength": str(row.get("strength") or ""),
                "form": form,
                "stockOnHand": on_hand,
                "stockUnits": form,
                "price": _format_ngn(live_price, currency),
                "developmentPrice": False,
                "developmentPriceNote": "",
                "available": available,
                "status": "Available" if available else "Not available",
                "canEdit": bool(drug_uuid) and drug_uuid not in pharmacy_catalogue.TEST_DRUG_UUIDS,
            }
        )
    items.sort(key=lambda item: (item["name"].lower(), item["strength"].lower(), item["form"].lower(), item["id"]))
    return {
        "status": "ok",
        "currency": currency,
        "developmentPrice": False,
        "developmentPriceNote": "",
        "canManage": True,
        "count": len(items),
        "items": items,
    }


def is_pharmacy_sale(sale: dict[str, Any]) -> bool:
    shop = many2one_name(sale.get("shop_id")).lower()
    return "pharmacy" in shop


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_charge_failed",
            "The pharmacy bill could not be created. Refresh and try again.",
        ) from error


def _drug_order_uuid(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 36 and text.count("-") == 4:
        return text
    return ""


def sale_awaits_pharmacy_quantity(odoo: OdooReader, sale: dict[str, Any]) -> bool:
    """A draft linked to a doctor's medicine waits until Pharmacy chooses the quantity."""
    if str(sale.get("state") or "") != "draft":
        return False
    lines = odoo.search_read(
        "sale.order.line",
        [("order_id", "=", int(sale["id"]))],
        ["external_order_id"],
        limit=80,
    )
    if not isinstance(lines, list):
        return False
    return any(_drug_order_uuid(line.get("external_order_id")) for line in lines if isinstance(line, dict))


def ensure_pharmacy_invoice(odoo: OdooReader, sale: dict[str, Any]) -> dict[str, Any] | None:
    """Confirm a pharmacy sale so the cashier has a posted invoice.

    Does not rewrite line prices or quantities. Pharmacy sets the quantity first.
    """
    sale_id = int(sale["id"])
    if sale.get("state") == "draft":
        _confirm_sale(odoo, sale_id)
        fresh = odoo.read(
            "sale.order",
            [sale_id],
            ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
        )
        if not fresh or fresh[0].get("state") not in {"sale", "done"}:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The pharmacy bill could not be created. Refresh and try again.",
            )
        sale = fresh[0]
    return related_invoice(odoo, sale)


def ensure_partner_pharmacy_invoices(odoo: OdooReader, orders: list[dict[str, Any]]) -> bool:
    """Post draft Pharmacy sales for this patient only. Other shops are left alone."""
    changed = False
    for order in orders:
        if order.get("state") != "draft" or not is_pharmacy_sale(order):
            continue
        if sale_awaits_pharmacy_quantity(odoo, order):
            continue
        try:
            ensure_pharmacy_invoice(odoo, order)
            changed = True
        except ApiError:
            continue
    return changed


def require_pharmacy_charge_user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    user = load_openmrs_user(cookie)
    if is_pharmacist(user):
        return user
    import accountant as cashier

    if cashier.is_accountant(user):
        return user
    raise ApiError(403, "forbidden", "This action requires Pharmacy or Payments.")


def create_pharmacy_charge(order_uuid: str, cookie: str, request_id: str | None = None) -> dict[str, Any]:
    user = require_pharmacy_charge_user(cookie)
    request_key = (request_id or "").strip()
    charge_key = f"pharmacy-charge:{order_uuid}"
    keys = [charge_key, request_key]
    with IDEMPOTENCY_LOCK:
        for key in keys:
            if not key:
                continue
            state = IDEMPOTENCY.get(key) or {}
            if state.get("status") == "pending":
                raise ApiError(409, "charge_in_progress", "This pharmacy bill is already being created.")
            if state.get("status") == "done":
                payload = assemble_prescription(order_uuid, cookie)
                payload["alreadyCreated"] = True
                return payload
        for key in keys:
            if key:
                IDEMPOTENCY[key] = {"status": "pending"}
    try:
        import pharmacy_unlisted as unlisted

        clinical = load_openmrs_order(order_uuid, cookie)
        if unlisted.not_in_pharmacy_order(clinical):
            unlisted.remember(clinical)
            try:
                import pharmacy_prescription_ops as rx_ops

                rx_ops._cancel_odoo_sale_for_order(odoo_reader(), order_uuid)
            except ApiError:
                pass
            raise ApiError(409, "not_in_pharmacy", unlisted.NOT_IN_PHARMACY_REASON)
        odoo = odoo_reader()
        matched = sale_line_for_order(odoo, order_uuid)
        if not matched:
            raise ApiError(
                409,
                "not_ready",
                "This prescription is not ready to bill yet. Try again in a moment.",
            )
        _line, sale = matched
        invoice = ensure_pharmacy_invoice(odoo, sale)
        if not invoice:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The pharmacy bill could not be created. Refresh and try again.",
            )
        with IDEMPOTENCY_LOCK:
            for key in keys:
                if key:
                    IDEMPOTENCY[key] = {"status": "done"}
        payload = assemble_prescription(order_uuid, cookie)
        payload["alreadyCreated"] = False
        payload["recordedBy"] = user.get("username") or ""
        return payload
    except Exception:
        with IDEMPOTENCY_LOCK:
            for key in keys:
                if key and (IDEMPOTENCY.get(key) or {}).get("status") == "pending":
                    IDEMPOTENCY.pop(key, None)
        raise


def _quantities_from_body(body: dict[str, Any]) -> dict[str, float]:
    rows = body.get("lines") if isinstance(body, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ApiError(422, "invalid_body", "Enter a quantity for each medicine.")
    wanted: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_id = str(row.get("orderUuid") or "").strip()
        if order_id:
            wanted[order_id] = as_float(row.get("quantity"))
    if not wanted:
        raise ApiError(422, "invalid_body", "Enter a quantity for each medicine.")
    return wanted


def _medicine_needs_quantity(row: dict[str, Any]) -> bool:
    if row.get("notInPharmacy"):
        return False
    if str(row.get("dispensingStatus") or "").upper() in {"DISPENSED", "STOPPED"}:
        return False
    return str(row.get("paymentStatus") or "").upper() == "NOT BILLED"


def _sale_line_command(row: dict[str, Any], quantity: float, patient_uuid: str, product: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": int(product["id"]),
        "name": _prescription_line_name(row, str(product.get("name") or row.get("drugName") or "")),
        "product_uom_qty": quantity,
        "price_unit": as_float(product.get("list_price")),
        "discount": 0,
        "tax_id": [(6, 0, [])],
        "external_order_id": str(row.get("orderUuid") or ""),
        "external_id": patient_uuid,
    }


def _ensure_unbilled_lines(
    odoo: OdooReader,
    cookie: str,
    orphans: list[dict[str, Any]],
    wanted: dict[str, float],
    drafts: dict[int, dict[str, Any]],
) -> None:
    import pharmacy_sale

    patient_uuid = str(orphans[0].get("patientUuid") or "")
    if not patient_uuid:
        raise ApiError(409, "account_not_found", "This patient has no bill account yet.")
    patient = core.load_openmrs_patient(patient_uuid, cookie)
    partner = billing_partner(odoo, patient)
    if not partner:
        raise ApiError(409, "account_not_found", "This patient has no bill account yet.")
    products = find_pharmacy_products(odoo, [str(row.get("drugUuid") or "") for row in orphans])
    commands = []
    for row in orphans:
        name = str(row.get("drugName") or "This medicine")
        product = products.get(str(row.get("drugUuid") or ""))
        if not product or not product.get("id"):
            raise ApiError(409, "medicine_required", f"{name} is not in the pharmacy list.")
        if as_float(product.get("list_price")) <= 0:
            raise ApiError(409, "missing_price", f"{name} has no selling price yet.")
        commands.append(
            (0, 0, _sale_line_command(row, wanted[str(row.get("orderUuid") or "")], patient_uuid, product))
        )
    draft_id = next(
        (sale_id for sale_id, sale in drafts.items() if str(sale.get("state") or "") == "draft"),
        None,
    )
    if draft_id:
        execute(odoo, "sale.order", "write", [[draft_id], {"order_line": commands}])
        return
    shop = pharmacy_sale.find_pharmacy_shop(odoo)
    origin = str(orphans[0].get("encounterUuid") or orphans[0].get("orderUuid") or patient_uuid)
    sale_id = int(
        execute(
            odoo,
            "sale.order",
            "create",
            [
                {
                    "partner_id": int(partner["id"]),
                    "shop_id": int(shop["id"]),
                    "warehouse_id": many2one_id(shop.get("warehouse_id")) or 1,
                    "pricelist_id": many2one_id(shop.get("pricelist_id")) or 1,
                    "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                    "origin": origin,
                    "care_setting": _sale_care_setting(orphans[0]),
                    "order_line": commands,
                }
            ],
        )
    )
    rows = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
    )
    if not rows:
        raise ApiError(502, "odoo_charge_failed", "The pharmacy bill could not be created. Refresh and try again.")
    drafts[sale_id] = rows[0]


def bill_prescription(order_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Create the prescription bill from the quantities Pharmacy entered."""
    require_pharmacist(cookie)
    wanted = _quantities_from_body(body)
    group = assemble_prescription_group(order_uuid, cookie)
    medicines = group.get("medicines") or [group]
    pending = [row for row in medicines if isinstance(row, dict) and _medicine_needs_quantity(row)]
    if not pending:
        raise ApiError(409, "already_billed", "This prescription is already billed.")
    missing = [
        str(row.get("drugName") or "a medicine")
        for row in pending
        if (wanted.get(str(row.get("orderUuid") or "")) or 0) <= 0
    ]
    if missing:
        raise ApiError(422, "invalid_quantity", "Enter the quantity for " + ", ".join(missing) + ".")
    odoo = odoo_reader()
    drafts: dict[int, dict[str, Any]] = {}
    orphans: list[dict[str, Any]] = []
    for row in pending:
        order_id = str(row.get("orderUuid") or "")
        quantity = wanted[order_id]
        matched = sale_line_for_order(odoo, order_id)
        if not matched or str(matched[1].get("state") or "") in {"cancel", "cancelled"}:
            orphans.append(row)
            continue
        line, sale = matched
        state = str(sale.get("state") or "")
        if state == "draft" and as_float(line.get("price_unit")) <= 0:
            raise ApiError(
                409,
                "missing_price",
                f"{row.get('drugName') or 'This medicine'} has no selling price yet.",
            )
        if state == "draft":
            if abs(as_float(line.get("product_uom_qty")) - quantity) > 0.001:
                execute(odoo, "sale.order.line", "write", [[int(line["id"])], {"product_uom_qty": quantity}])
            drafts[int(sale["id"])] = sale
            continue
        if abs(as_float(line.get("product_uom_qty")) - quantity) > 0.001:
            raise ApiError(409, "already_billed", "This prescription is already billed.")
        drafts[int(sale["id"])] = sale
    if orphans:
        _ensure_unbilled_lines(odoo, cookie, orphans, wanted, drafts)
    if not drafts:
        raise ApiError(502, "odoo_charge_failed", "The pharmacy bill could not be created. Refresh and try again.")
    for sale in list(drafts.values()):
        fresh_rows = odoo.read(
            "sale.order",
            [int(sale["id"])],
            ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
        )
        invoice = ensure_pharmacy_invoice(odoo, fresh_rows[0] if fresh_rows else sale)
        if not invoice:
            raise ApiError(502, "odoo_charge_failed", "The pharmacy bill could not be created. Refresh and try again.")
    return build_prescription(order_uuid, cookie)


def related_invoice(odoo: OdooReader, sale: dict[str, Any]) -> dict[str, Any] | None:
    invoice_ids = [int(item) for item in (sale.get("invoice_ids") or [])]
    invoices = (
        odoo.read(
            "account.move",
            invoice_ids,
            ["name", "state", "payment_state", "amount_residual", "move_type", "partner_id"],
        )
        if invoice_ids
        else []
    )
    posted = [
        row
        for row in invoices
        if row.get("move_type") == "out_invoice" and row.get("state") == "posted"
    ]
    if posted:
        return posted[0]
    origin = sale.get("name") or ""
    if not origin:
        return None
    found = odoo.search_read(
        "account.move",
        [("move_type", "=", "out_invoice"), ("invoice_origin", "=", origin), ("state", "=", "posted")],
        ["name", "state", "payment_state", "amount_residual", "move_type", "partner_id"],
        limit=1,
    )
    return found[0] if found else None


def outgoing_pickings(odoo: OdooReader, sale_id: int) -> list[dict[str, Any]]:
    rows = odoo.search_read(
        "stock.picking",
        [("sale_id", "=", sale_id)],
        ["name", "state", "sale_id", "picking_type_id", "origin"],
    )
    outgoing = []
    type_ids = [many2one_id(row.get("picking_type_id")) for row in rows]
    type_ids = [item for item in type_ids if item]
    types = {
        int(row["id"]): row.get("code") or ""
        for row in (odoo.read("stock.picking.type", type_ids, ["code"]) if type_ids else [])
    }
    for row in rows:
        code = types.get(many2one_id(row.get("picking_type_id")) or 0, "")
        if code == "outgoing" or str(row.get("name") or "").startswith("WH/OUT"):
            outgoing.append(row)
    return outgoing


def choose_picking(pickings: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pickings:
        return None
    live = [row for row in pickings if str(row.get("state") or "") not in {"done", "cancel", "cancelled"}]
    if live:
        return live[0]
    done = [row for row in pickings if str(row.get("state") or "") == "done"]
    return done[0] if done else None


def sale_line_for_order(odoo: OdooReader, order_uuid: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    lines = odoo.search_read(
        "sale.order.line",
        [("external_order_id", "=", order_uuid)],
        [
            "order_id",
            "product_id",
            "product_uom_qty",
            "qty_delivered",
            "price_unit",
            "external_order_id",
            "name",
        ],
    )
    if not lines:
        return None
    order_ids = [many2one_id(row.get("order_id")) for row in lines if many2one_id(row.get("order_id"))]
    sale_fields = ["name", "state", "partner_id", "invoice_ids", "origin"]
    try:
        sale_rows = odoo.read("sale.order", order_ids, [*sale_fields, "shop_id"])
    except xmlrpc.client.Fault:
        sale_rows = odoo.read("sale.order", order_ids, sale_fields)
    sales = {int(row["id"]): row for row in sale_rows}
    ranked = []
    for line in lines:
        sale = sales.get(many2one_id(line.get("order_id")) or 0)
        if not sale:
            continue
        rank = 0 if sale.get("state") in {"sale", "done"} else 1
        ranked.append((rank, int(line["id"]), line, sale))
    if not ranked:
        return None
    ranked.sort()
    return ranked[0][2], ranked[0][3]


def _prescription_line_name(clinical: dict[str, Any], product_name: str) -> str:
    parts = [product_name or str(clinical.get("drugName") or "Medication")]
    for key in ("dose", "doseUnits", "frequency", "duration", "route", "instructions"):
        value = str(clinical.get(key) or "").strip()
        if value:
            parts.append(value)
    return " · ".join(parts)


def _sale_care_setting(clinical: dict[str, Any]) -> str:
    text = str(clinical.get("careSetting") or "").lower()
    if "inpatient" in text or text == "ipd":
        return "ipd"
    return "opd"


def ensure_nhis_prescription_sales(cookie: str, clinical_orders: list[dict[str, Any]]) -> None:
    """Pharmacy creates the bill after choosing a quantity. Do not bill from the doctor's order."""
    del cookie, clinical_orders


def bill_nhis_patient_prescriptions(patient_uuid: str, cookie: str) -> None:
    """NHIS does not change pharmacy prices. Do not bill from here."""
    del patient_uuid, cookie


def _create_nhis_pharmacy_bills(
    odoo: OdooReader,
    cookie: str,
    patient_uuid: str,
    orders: list[dict[str, Any]],
    shop: dict[str, Any],
) -> None:
    patient = core.load_openmrs_patient(patient_uuid, cookie)
    partner = find_partner(odoo, patient)
    if not partner:
        return
    grouped: dict[str, list[dict[str, Any]]] = {}
    for order in orders:
        key = str(order.get("encounterUuid") or order.get("uuid") or "")
        grouped.setdefault(key, []).append(order)
    shop_id = int(shop["id"])
    warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
    pricelist_id = many2one_id(shop.get("pricelist_id")) or 1
    products = find_pharmacy_products(
        odoo,
        [str(order.get("drugUuid") or "") for order in orders],
    )
    for encounter_uuid, encounter_orders in grouped.items():
        order_lines = []
        for order in encounter_orders:
            order_uuid = str(order.get("uuid") or "")
            if sale_line_for_order(odoo, order_uuid):
                continue
            product = products.get(str(order.get("drugUuid") or ""))
            if not product or not product.get("id"):
                continue
            price = as_float(product.get("list_price"))
            if price <= 0:
                continue
            quantity = as_float(order.get("quantity"))
            if quantity <= 0:
                quantity = 1
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": int(product["id"]),
                        "name": _prescription_line_name(order, str(product.get("name") or "")),
                        "product_uom_qty": quantity,
                        "price_unit": price,
                        "discount": 0,
                        "tax_id": [(6, 0, [])],
                        "external_order_id": order_uuid,
                        "external_id": patient_uuid,
                    },
                )
            )
        if not order_lines:
            continue
        care = _sale_care_setting(encounter_orders[0])
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
                        "origin": encounter_uuid or patient_uuid,
                        "care_setting": care,
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
        if not sale_rows:
            continue
        sale = sale_rows[0]
        line_ids = [int(item) for item in (sale.get("order_line") or [])]
        if line_ids:
            execute(
                odoo,
                "sale.order.line",
                "write",
                [line_ids, {"tax_id": [(6, 0, [])], "discount": 0}],
            )
        ensure_pharmacy_invoice(odoo, sale)


def _prescription_row_for_clinical(odoo: OdooReader, clinical: dict[str, Any]) -> dict[str, Any]:
    matched = sale_line_for_order(odoo, str(clinical.get("uuid") or ""))
    if not matched:
        return serialize_prescription(
            clinical=clinical,
            line=None,
            invoice=None,
            picking=None,
            on_hand=0.0,
            sale=None,
        )
    line, sale = matched
    invoice = related_invoice(odoo, sale)
    pickings = outgoing_pickings(odoo, int(sale["id"]))
    product_id = many2one_id(line.get("product_id")) or 0
    return serialize_prescription(
        clinical=clinical,
        line=line,
        invoice=invoice,
        picking=choose_picking(pickings),
        on_hand=on_hand_quantity(odoo, product_id, stock_location_id(odoo, sale)),
        sale=sale,
    )


def serialize_prescription(
    *,
    clinical: dict[str, Any],
    line: dict[str, Any] | None,
    invoice: dict[str, Any] | None,
    picking: dict[str, Any] | None,
    on_hand: float,
    sale: dict[str, Any] | None = None,
    catalogue_ids: set[str] | None = None,
) -> dict[str, Any]:
    import pharmacy_unlisted as unlisted

    requested = as_float((line or {}).get("product_uom_qty")) or as_float(clinical.get("quantity"))
    delivered = as_float((line or {}).get("qty_delivered"))
    payment_state = (invoice or {}).get("payment_state")
    residual = as_float((invoice or {}).get("amount_residual"))
    picking_state = str((picking or {}).get("state") or "")
    live_picking = bool(picking) and picking_state not in {"cancel", "cancelled", "done"}
    billed = bool(invoice) or str((sale or {}).get("state") or "") in {"sale", "done"}
    not_in_pharmacy = unlisted.not_in_pharmacy_order(clinical, catalogue_ids)
    # Payment and dispensing are separate. Unpaid medicine may still be dispensed
    # (for example inpatient charges settled later at discharge).
    fully_paid = payment_state in {"paid", "in_payment"} and residual <= 0.009
    # Dispensed is per sale line (qty_delivered), never inferred from a shared
    # multi-medicine picking being done.
    if not_in_pharmacy:
        dispensing = "STOPPED" if clinical.get("stopped") else unlisted.NOT_IN_PHARMACY_STATUS
        pay_label = unlisted.NOT_BILLED_STATUS
        reason = None if clinical.get("stopped") else unlisted.NOT_IN_PHARMACY_REASON
        can_dispense = False
        stock_after = 0.0
    elif delivered + 0.0001 >= requested and requested > 0:
        dispensing = "DISPENSED"
    elif delivered > 0.0001:
        dispensing = "PARTIALLY DISPENSED"
    elif clinical.get("stopped"):
        dispensing = "STOPPED"
    elif live_picking or (billed and requested > delivered):
        dispensing = "READY TO DISPENSE"
    elif picking and picking_state == "done" and delivered + 0.0001 < requested:
        # Picking closed without this line — treat as not ready / unpaid path.
        dispensing = "PAID" if fully_paid else "UNPAID"
    elif fully_paid:
        dispensing = "PAID"
    else:
        dispensing = "UNPAID"
    if not not_in_pharmacy:
        if fully_paid:
            pay_label = "PAID"
        elif invoice and residual > 0.009 and (
            str(payment_state or "") == "partial"
            or as_float(invoice.get("amount_total")) > residual + 0.009
        ):
            pay_label = "PARTIALLY PAID"
        elif not invoice:
            pay_label = "NOT BILLED"
        else:
            pay_label = "UNPAID"
        units = clinical.get("quantityUnits") or clinical.get("doseUnits") or ""
        reason = None
        if clinical.get("stopped") and dispensing != "DISPENSED":
            reason = "This prescription has been stopped."
        elif dispensing == "DISPENSED":
            reason = "This medication has already been dispensed."
        elif not billed:
            reason = "Enter a quantity and create the bill first."
        elif live_picking and on_hand + 0.0001 < max(requested - delivered, 0):
            reason = "Not enough stock to dispense this medication."
        elif not live_picking and not billed:
            reason = "This prescription is not ready to dispense yet."
        remaining = max(requested - delivered, 0)
        can_dispense = (
            dispensing in {"READY TO DISPENSE", "PARTIALLY DISPENSED"}
            and reason is None
            and remaining > 0
        )
        stock_after = on_hand
        if can_dispense:
            stock_after = max(on_hand - requested, 0)
    units = clinical.get("quantityUnits") or clinical.get("doseUnits") or ""
    import pharmacy_rx_links as rx_links

    linked = rx_links.group_for(str(clinical.get("uuid") or ""))
    batch = prescription_batch_key(str(clinical.get("encounterUuid") or ""), str(clinical.get("ordered") or ""))
    if "|" in linked:
        group_key = linked
    elif batch:
        group_key = batch
    else:
        group_key = (
            linked
            or (str(int(sale["id"])) if sale and sale.get("id") else "")
            or str(clinical.get("uuid") or "")
        )
    return {
        "status": "ok",
        "orderUuid": clinical.get("uuid") or "",
        "orderNumber": clinical.get("orderNumber") or "",
        "patientUuid": clinical.get("patientUuid") or "",
        "patientName": clinical.get("patientName") or "",
        "mrn": clinical.get("mrn") or "",
        "prescriber": clinical.get("prescriber") or "—",
        "ordered": clinical.get("ordered") or "",
        "encounterUuid": clinical.get("encounterUuid") or "",
        "groupKey": group_key,
        "doctorNotes": clinical.get("doctorNotes") or [],
        "drugUuid": clinical.get("drugUuid") or "",
        "drugName": clinical.get("drugName") or many2one_name((line or {}).get("product_id")) or "Medication",
        "strength": clinical.get("strength") or "",
        "dose": clinical.get("dose") or "",
        "doseUnits": clinical.get("doseUnits") or "",
        "route": clinical.get("route") or "",
        "frequency": clinical.get("frequency") or "",
        "duration": clinical.get("duration") or "",
        "instructions": clinical.get("instructions") or "",
        "quantity": requested,
        "quantityUnits": units,
        "paymentStatus": pay_label,
        "dispensingStatus": dispensing,
        "canDispense": can_dispense,
        "blockReason": reason,
        "notInPharmacy": not_in_pharmacy,
        "stockOnHand": 0 if not_in_pharmacy else on_hand,
        "stockAfter": round(stock_after, 4),
        "delivered": 0 if not_in_pharmacy else delivered,
        "saleId": None if not_in_pharmacy else (str(int(sale["id"])) if sale and sale.get("id") else None),
        "saleName": None if not_in_pharmacy else (str((sale or {}).get("name") or "") or None),
    }


def assemble_prescription(order_uuid: str, cookie: str) -> dict[str, Any]:
    import pharmacy_unlisted as unlisted

    clinical = load_openmrs_order(order_uuid, cookie)
    odoo = odoo_reader()
    if unlisted.not_in_pharmacy_order(clinical):
        unlisted.remember(clinical)
        matched = sale_line_for_order(odoo, order_uuid)
        if matched:
            try:
                import pharmacy_prescription_ops as rx_ops

                rx_ops._cancel_odoo_sale_for_order(odoo, order_uuid)
            except ApiError:
                pass
        payload = serialize_prescription(
            clinical=clinical,
            line=None,
            invoice=None,
            picking=None,
            on_hand=0.0,
            sale=None,
        )
        return payload
    unlisted.forget(order_uuid)
    matched = sale_line_for_order(odoo, order_uuid)
    line = matched[0] if matched else None
    sale = matched[1] if matched else None
    invoice = None
    if sale and invoice is None:
        invoice = related_invoice(odoo, sale)
    pickings = outgoing_pickings(odoo, int(sale["id"])) if sale else []
    picking = choose_picking(pickings)
    product_id = many2one_id((line or {}).get("product_id"))
    location_id = stock_location_id(odoo, sale)
    on_hand = on_hand_quantity(odoo, product_id or 0, location_id)
    payload = serialize_prescription(
        clinical=clinical,
        line=line,
        invoice=invoice,
        picking=picking,
        on_hand=on_hand,
        sale=sale,
    )
    if sale and invoice:
        partner_id = many2one_id(sale.get("partner_id"))
        try:
            partner = odoo.read("res.partner", [partner_id], ["uuid", "ref"]) if partner_id else []
        except xmlrpc.client.Fault:
            partner = []
        partner_row = partner[0] if partner else {}
        partner_uuid = partner_row.get("uuid") or ""
        if partner_uuid and clinical.get("patientUuid") and partner_uuid != clinical.get("patientUuid"):
            if (partner_row.get("ref") or "") != (clinical.get("mrn") or ""):
                payload["canDispense"] = False
                payload["blockReason"] = "This prescription does not match the patient record."
    return payload


def build_prescription(order_uuid: str, cookie: str) -> dict[str, Any]:
    require_pharmacist(cookie)
    return assemble_prescription_group(order_uuid, cookie)


def sale_prescription_lines(odoo: OdooReader, sale_id: int) -> list[dict[str, Any]]:
    """Sale lines keyed to OpenMRS drug orders on one pharmacy sale."""
    return odoo.search_read(
        "sale.order.line",
        [("order_id", "=", sale_id), ("external_order_id", "!=", False)],
        [
            "id",
            "order_id",
            "product_id",
            "product_uom_qty",
            "qty_delivered",
            "price_unit",
            "external_order_id",
            "name",
        ],
    )


def prescription_batch_key(encounter_uuid: str, ordered: str) -> str:
    """Medicines sent together share a minute. A later order stays its own prescription."""
    encounter = str(encounter_uuid or "").strip()
    stamp = str(ordered or "").strip().replace(" ", "T")
    minute = stamp[:16]
    if encounter and len(minute) >= 16:
        return f"{encounter}|{minute}"
    return encounter


def group_dispensing_status(medicines: list[dict[str, Any]]) -> str:
    statuses = [str(row.get("dispensingStatus") or "").upper() for row in medicines]
    if not statuses:
        return "UNPAID"
    ignored = {"STOPPED", "NOT IN PHARMACY"}
    active = [status for status in statuses if status not in ignored]
    if not active:
        if all(status == "STOPPED" for status in statuses):
            return "STOPPED"
        if any(status == "NOT IN PHARMACY" for status in statuses):
            return "NOT IN PHARMACY"
        return "STOPPED"
    dispensed = sum(1 for status in active if status == "DISPENSED")
    handed = sum(1 for status in active if status in {"DISPENSED", "PARTIALLY DISPENSED"})
    if dispensed == len(active):
        return "DISPENSED"
    if handed > 0:
        return "PARTIALLY DISPENSED"
    if any(status == "READY TO DISPENSE" for status in active):
        return "READY TO DISPENSE"
    if any(status == "PAID" for status in active):
        return "PAID"
    return "UNPAID"


def _group_payment_status(medicines: list[dict[str, Any]], focal: dict[str, Any]) -> str:
    billed = [
        str(row.get("paymentStatus") or "").upper()
        for row in medicines
        if not row.get("notInPharmacy")
    ]
    if not billed:
        return "NOT BILLED"
    payment_statuses = set(billed)
    if "PARTIALLY PAID" in payment_statuses or (
        "PAID" in payment_statuses and "UNPAID" in payment_statuses
    ):
        return "PARTIALLY PAID"
    if payment_statuses == {"PAID"}:
        return "PAID"
    return str(focal.get("paymentStatus") or billed[0] or "UNPAID")


def _encounter_drug_order_uuids(encounter_uuid: str) -> list[str]:
    """Every active drug order written on this consultation."""
    encounter = str(encounter_uuid or "").strip()
    if not encounter:
        return []
    try:
        import openmrs_sql

        rows = openmrs_sql.fetch_all(
            """
            SELECT o.uuid
            FROM orders o
            JOIN encounter e ON e.encounter_id = o.encounter_id
            JOIN order_type ot ON ot.order_type_id = o.order_type_id
            WHERE e.uuid = %s
              AND ot.name = %s
              AND o.voided = 0
              AND o.date_stopped IS NULL
            ORDER BY o.order_id
            """,
            (encounter, "Drug Order"),
        )
    except Exception:
        return []
    return [str(row[0]) for row in rows if row and row[0]]


def _unlisted_siblings(
    cookie: str,
    *,
    patient_uuid: str,
    encounter_uuid: str,
    known_uuids: set[str],
) -> list[dict[str, Any]]:
    import pharmacy_unlisted as unlisted

    extras: list[dict[str, Any]] = []
    for row in unlisted.list_rows(patient_uuid=patient_uuid, encounter_uuid=encounter_uuid or None):
        order_uuid = str(row.get("orderUuid") or "")
        if not order_uuid or order_uuid in known_uuids:
            continue
        try:
            clinical = load_openmrs_order(order_uuid, cookie)
        except ApiError:
            continue
        if not unlisted.not_in_pharmacy_order(clinical):
            unlisted.forget(order_uuid)
            continue
        extras.append(
            serialize_prescription(
                clinical=clinical,
                line=None,
                invoice=None,
                picking=None,
                on_hand=0.0,
                sale=None,
            )
        )
        known_uuids.add(order_uuid)
    return extras


def assemble_prescription_group(order_uuid: str, cookie: str) -> dict[str, Any]:
    """Load one medicine and its sibling lines on the same consultation."""
    import pharmacy_rx_links as rx_links

    order_uuid = rx_links.resolve(order_uuid) or order_uuid
    focal = assemble_prescription(order_uuid, cookie)
    odoo = odoo_reader()
    matched = None if focal.get("notInPharmacy") else sale_line_for_order(odoo, order_uuid)
    medicines = [focal]
    sale_id = None
    sale_name = None
    if matched:
        line, sale = matched
        sale_id = int(sale["id"])
        sale_name = str(sale.get("name") or "")
        siblings = sale_prescription_lines(odoo, sale_id)
        payloads: list[dict[str, Any]] = []
        for sibling in siblings:
            sibling_uuid = str(sibling.get("external_order_id") or "").strip()
            if not sibling_uuid:
                continue
            if sibling_uuid == order_uuid:
                payloads.append(focal)
                continue
            try:
                sibling_payload = assemble_prescription(sibling_uuid, cookie)
            except ApiError:
                continue
            if sibling_payload.get("stopped") or sibling_payload.get("dispensingStatus") == "STOPPED":
                continue
            payloads.append(sibling_payload)
        if payloads:
            medicines = payloads
            medicines.sort(key=lambda row: 0 if row.get("orderUuid") == order_uuid else 1)

    known = {str(row.get("orderUuid") or "") for row in medicines}
    encounter = str(focal.get("encounterUuid") or "")
    focal_batch = str(focal.get("groupKey") or "")
    for sibling_uuid in _encounter_drug_order_uuids(encounter):
        if not sibling_uuid or sibling_uuid in known:
            continue
        try:
            sibling = assemble_prescription(sibling_uuid, cookie)
        except ApiError:
            continue
        if focal_batch and str(sibling.get("groupKey") or "") != focal_batch:
            continue
        if sibling.get("stopped") or sibling.get("dispensingStatus") == "STOPPED":
            continue
        medicines.append(sibling)
        known.add(sibling_uuid)

    for sibling_uuid in rx_links.members(focal_batch):
        if not sibling_uuid or sibling_uuid in known:
            continue
        try:
            sibling = assemble_prescription(sibling_uuid, cookie)
        except ApiError:
            continue
        if sibling.get("stopped") or sibling.get("dispensingStatus") == "STOPPED":
            continue
        medicines.append(sibling)
        known.add(sibling_uuid)

    known = {str(row.get("orderUuid") or "") for row in medicines}
    medicines.extend(
        _unlisted_siblings(
            cookie,
            patient_uuid=str(focal.get("patientUuid") or ""),
            encounter_uuid=str(focal.get("encounterUuid") or ""),
            known_uuids=known,
        )
    )
    if focal.get("notInPharmacy") and not any(row.get("orderUuid") == order_uuid for row in medicines):
        medicines.insert(0, focal)

    group_status = group_dispensing_status(medicines)
    group_payment = _group_payment_status(medicines, focal)
    import consultation as clinical
    billed_sale_id = sale_id
    billed_sale_name = sale_name
    if not billed_sale_id:
        for row in medicines:
            if row.get("saleId") and not row.get("notInPharmacy"):
                billed_sale_id = int(row["saleId"]) if str(row.get("saleId") or "").isdigit() else None
                billed_sale_name = row.get("saleName")
                break

    return {
        **focal,
        "saleId": str(billed_sale_id) if billed_sale_id else None,
        "saleName": billed_sale_name or None,
        "medicines": medicines,
        "medicineCount": len(medicines),
        "groupDispensingStatus": group_status,
        "groupPaymentStatus": group_payment,
        "dispensingStatus": group_status
        if group_status in {"DISPENSED", "PARTIALLY DISPENSED", "READY TO DISPENSE", "NOT IN PHARMACY"}
        else focal.get("dispensingStatus"),
        "nhis": clinical.patient_is_nhis(odoo, str(focal.get("patientUuid") or "")),
    }


def _prepare_partial_dispense(odoo: OdooReader, picking_id: int, product_ids: set[int]) -> None:
    """Deliver only selected products; leave sibling moves for a backorder."""
    picking = odoo.read(
        "stock.picking",
        [picking_id],
        ["move_ids_without_package", "move_line_ids", "state"],
    )
    if not picking:
        return
    move_ids = [int(item) for item in (picking[0].get("move_ids_without_package") or [])]
    if not move_ids:
        return
    moves = odoo.read(
        "stock.move",
        move_ids,
        ["id", "product_id", "product_uom_qty", "quantity_done", "move_line_ids", "state"],
    )
    for move in moves:
        if str(move.get("state") or "") in {"done", "cancel"}:
            continue
        product_id = many2one_id(move.get("product_id"))
        demand = as_float(move.get("product_uom_qty"))
        qty = demand if product_id in product_ids else 0.0
        try:
            execute(odoo, "stock.move", "write", [[int(move["id"])], {"quantity_done": qty}])
        except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, TypeError):
            pass
        line_ids = [int(item) for item in (move.get("move_line_ids") or [])]
        if line_ids:
            try:
                execute(odoo, "stock.move.line", "write", [line_ids, {"qty_done": qty}])
            except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, TypeError):
                pass


def dispense_prescriptions(
    order_uuids: list[str],
    cookie: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Dispense one or more medicines. Sibling lines on a shared sale stay pending."""
    user = require_pharmacist(cookie)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in order_uuids:
        uuid = str(item or "").strip()
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        cleaned.append(uuid)
    if not cleaned:
        raise ApiError(422, "missing_orders", "Choose at least one medicine to dispense.")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for order_uuid in cleaned:
        try:
            payload = dispense_prescription(order_uuid, cookie, request_id=f"{request_id or 'batch'}:{order_uuid}")
            results.append(payload)
        except ApiError as error:
            errors.append(
                {
                    "orderUuid": order_uuid,
                    "code": str(error.code or "dispense_failed"),
                    "message": str(error.message or "Could not dispense this medicine."),
                }
            )
    if not results and errors:
        first = errors[0]
        raise ApiError(409, first["code"], first["message"])

    group = assemble_prescription_group(cleaned[0], cookie)
    group["success"] = True
    group["dispensed"] = results
    group["dispenseErrors"] = errors
    group["recordedBy"] = user.get("username") or ""
    if errors and results:
        group["message"] = (
            f"Dispensed {len(results)} medicine{'s' if len(results) != 1 else ''}. "
            f"{len(errors)} could not be dispensed."
        )
    elif results:
        group["message"] = (
            f"Dispensed {len(results)} medicine{'s' if len(results) != 1 else ''}."
        )
    return group


def _safe_openmrs_order(order_uuid: str, cookie: str) -> dict[str, Any] | None:
    try:
        return load_openmrs_order(order_uuid, cookie)
    except ApiError:
        return None


def _drug_order_row(row: dict[str, Any]) -> str:
    """Return the order id when this row is an active drug order."""
    if not isinstance(row, dict) or not row.get("uuid") or row.get("dateStopped"):
        return ""
    if str(row.get("action") or "").upper() == "DISCONTINUE":
        return ""
    order_type = row.get("orderType")
    if isinstance(order_type, dict):
        name = str(order_type.get("display") or order_type.get("name") or "")
    else:
        name = str(order_type or "")
    if name.strip().lower() not in {"drug order", "drugorder"}:
        return ""
    return str(row.get("uuid") or "")


def _patient_order_uuids(patient_uuid: str, cookie: str) -> list[str]:
    """Return the patient's drug orders, including ones that have no bill yet."""
    try:
        payload = _openmrs_json(
            f"/openmrs/ws/rest/v1/order?patient={quote(patient_uuid)}&limit=200"
            "&v=custom:(uuid,orderType:(display),action,dateStopped)",
            cookie,
        )
    except ApiError:
        return []
    results = payload.get("results") if isinstance(payload, dict) else []
    return [order_uuid for row in results or [] if (order_uuid := _drug_order_row(row))]


def _recent_drug_order_uuids() -> list[str]:
    """Active drug orders for the counter list, including ones with no bill yet."""
    try:
        import openmrs_sql

        rows = openmrs_sql.fetch_all(
            """
            SELECT o.uuid
            FROM orders o
            JOIN order_type ot ON ot.order_type_id = o.order_type_id
            WHERE ot.name = %s
              AND o.voided = 0
              AND o.date_stopped IS NULL
            ORDER BY o.order_id DESC
            LIMIT 200
            """,
            ("Drug Order",),
        )
    except Exception:
        return []
    return [str(row[0]) for row in rows if row and row[0]]


def _queue_sales(odoo: OdooReader, lines: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    sale_ids = []
    seen: set[int] = set()
    for line in lines:
        sale_id = many2one_id(line.get("order_id"))
        if sale_id and sale_id not in seen:
            seen.add(sale_id)
            sale_ids.append(sale_id)
    sale_fields = ["name", "state", "partner_id", "invoice_ids", "origin"]
    try:
        sale_rows = odoo.read("sale.order", sale_ids, [*sale_fields, "shop_id"])
    except xmlrpc.client.Fault:
        sale_rows = odoo.read("sale.order", sale_ids, sale_fields)
    return {int(row["id"]): row for row in sale_rows}


def _queue_invoices(odoo: OdooReader, sales: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    invoice_ids: list[int] = []
    origins: list[str] = []
    for sale in sales:
        invoice_ids.extend(int(item) for item in (sale.get("invoice_ids") or []) if item)
        if sale.get("name"):
            origins.append(str(sale["name"]))
    invoices: list[dict[str, Any]] = []
    if invoice_ids:
        invoices.extend(
            odoo.read(
                "account.move",
                invoice_ids,
                ["name", "state", "payment_state", "amount_residual", "amount_total", "move_type", "partner_id", "invoice_origin"],
            )
        )
    missing_origins = [
        origin
        for origin in origins
        if not any(str(row.get("invoice_origin") or "") == origin for row in invoices)
    ]
    if missing_origins:
        invoices.extend(
            odoo.search_read(
                "account.move",
                [("move_type", "=", "out_invoice"), ("state", "=", "posted"), ("invoice_origin", "in", missing_origins)],
                ["name", "state", "payment_state", "amount_residual", "amount_total", "move_type", "partner_id", "invoice_origin"],
                limit=max(len(missing_origins), 1),
            )
        )
    by_id = {int(row["id"]): row for row in invoices if row.get("id")}
    by_origin = {
        str(row.get("invoice_origin") or ""): row
        for row in invoices
        if row.get("move_type") == "out_invoice" and row.get("state") == "posted" and row.get("invoice_origin")
    }
    chosen: dict[int, dict[str, Any]] = {}
    for sale in sales:
        sale_id = int(sale["id"])
        posted = [
            by_id[int(item)]
            for item in (sale.get("invoice_ids") or [])
            if int(item) in by_id
            and by_id[int(item)].get("move_type") == "out_invoice"
            and by_id[int(item)].get("state") == "posted"
        ]
        chosen[sale_id] = posted[0] if posted else by_origin.get(str(sale.get("name") or ""))
    return chosen


def _queue_pickings(odoo: OdooReader, sale_ids: list[int]) -> dict[int, dict[str, Any] | None]:
    if not sale_ids:
        return {}
    rows = odoo.search_read(
        "stock.picking",
        [("sale_id", "in", sale_ids)],
        ["name", "state", "sale_id", "picking_type_id", "origin"],
        limit=max(len(sale_ids) * 4, 50),
    )
    type_ids = [many2one_id(row.get("picking_type_id")) for row in rows]
    type_ids = [item for item in type_ids if item]
    types = {
        int(row["id"]): row.get("code") or ""
        for row in (odoo.read("stock.picking.type", type_ids, ["code"]) if type_ids else [])
    }
    grouped: dict[int, list[dict[str, Any]]] = {sale_id: [] for sale_id in sale_ids}
    for row in rows:
        sale_id = many2one_id(row.get("sale_id"))
        code = types.get(many2one_id(row.get("picking_type_id")) or 0, "")
        if sale_id in grouped and (code == "outgoing" or str(row.get("name") or "").startswith("WH/OUT")):
            grouped[sale_id].append(row)
    return {sale_id: choose_picking(items) for sale_id, items in grouped.items()}


def build_queue(cookie: str, patient_uuid: str | None = None) -> dict[str, Any]:
    require_pharmacist(cookie)
    odoo = odoo_reader()
    domain: list[Any] = [("external_order_id", "!=", False)]
    for prefix in NON_PHARMACY_PREFIXES:
        domain.append(("external_order_id", "not like", f"{prefix}%"))
    try:
        lines = execute(
            odoo,
            "sale.order.line",
            "search_read",
            [domain],
            {
                "fields": [
                    "external_order_id",
                    "order_id",
                    "product_id",
                    "product_uom_qty",
                    "qty_delivered",
                    "price_unit",
                    "name",
                ],
                "limit": 200,
                "order": "id desc",
            },
        )
    except xmlrpc.client.Fault:
        lines = odoo.search_read(
            "sale.order.line",
            [("external_order_id", "!=", False)],
            ["external_order_id", "order_id", "product_id", "product_uom_qty", "qty_delivered", "price_unit", "name"],
            limit=200,
        )
    unique_lines: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines or []:
        order_uuid = str(line.get("external_order_id") or "").strip()
        if not is_pharmacy_external_id(order_uuid) or order_uuid in seen:
            continue
        seen.add(order_uuid)
        unique_lines.append(line)
    sales = _queue_sales(odoo, unique_lines)
    invoices = _queue_invoices(odoo, list(sales.values()))
    pickings = _queue_pickings(odoo, list(sales))
    location_id = stock_location_id(odoo)
    product_ids = [many2one_id(line.get("product_id")) or 0 for line in unique_lines]
    stock = on_hand_quantities(odoo, product_ids, location_id)
    partner_ids = [many2one_id(sale.get("partner_id")) or 0 for sale in sales.values()]
    partners = {
        int(row["id"]): row
        for row in odoo.read("res.partner", [item for item in partner_ids if item], ["uuid", "ref"])
    }
    order_uuids = [str(line.get("external_order_id") or "") for line in unique_lines]
    workers = min(8, max(len(order_uuids), 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        clinicals = list(pool.map(lambda uuid: _safe_openmrs_order(uuid, cookie), order_uuids))
    import pharmacy_unlisted as unlisted

    rows = []
    seen_orders: set[str] = set()
    for line, clinical in zip(unique_lines, clinicals):
        if not clinical:
            continue
        if patient_uuid and clinical.get("patientUuid") != patient_uuid:
            continue
        order_id = str(clinical.get("uuid") or line.get("external_order_id") or "")
        if unlisted.not_in_pharmacy_order(clinical):
            unlisted.remember(clinical)
            try:
                import pharmacy_prescription_ops as rx_ops

                rx_ops._cancel_odoo_sale_for_order(odoo, order_id)
            except ApiError:
                pass
            payload = serialize_prescription(
                clinical=clinical,
                line=None,
                invoice=None,
                picking=None,
                on_hand=0.0,
                sale=None,
            )
            rows.append(payload)
            seen_orders.add(order_id)
            continue
        sale = sales.get(many2one_id(line.get("order_id")) or 0)
        invoice = invoices.get(int(sale["id"])) if sale else None
        picking = pickings.get(int(sale["id"])) if sale else None
        product_id = many2one_id(line.get("product_id")) or 0
        payload = serialize_prescription(
            clinical=clinical,
            line=line,
            invoice=invoice,
            picking=picking,
            on_hand=stock.get(product_id, 0.0),
            sale=sale,
        )
        if sale and invoice:
            partner = partners.get(many2one_id(sale.get("partner_id")) or 0) or {}
            partner_uuid = partner.get("uuid") or ""
            if partner_uuid and clinical.get("patientUuid") and partner_uuid != clinical.get("patientUuid"):
                if (partner.get("ref") or "") != (clinical.get("mrn") or ""):
                    payload["canDispense"] = False
                    payload["blockReason"] = "This prescription does not match the patient record."
        rows.append(payload)
        seen_orders.add(order_id)
    missing_order_uuids = [
        order_uuid
        for order_uuid in (
            _patient_order_uuids(patient_uuid, cookie)
            if patient_uuid
            else _recent_drug_order_uuids()
        )
        if order_uuid not in seen_orders
    ]
    if missing_order_uuids:
        with ThreadPoolExecutor(max_workers=min(8, len(missing_order_uuids))) as pool:
            patient_clinicals = list(
                pool.map(lambda uuid: _safe_openmrs_order(uuid, cookie), missing_order_uuids)
            )
        try:
            ensure_nhis_prescription_sales(
                cookie,
                [clinical for clinical in patient_clinicals if clinical and not clinical.get("stopped")],
            )
        except Exception:
            pass
        for clinical in patient_clinicals:
            if not clinical or clinical.get("stopped"):
                continue
            order_id = str(clinical.get("uuid") or "")
            if not order_id or order_id in seen_orders:
                continue
            if unlisted.not_in_pharmacy_order(clinical):
                unlisted.remember(clinical)
                rows.append(
                    serialize_prescription(
                        clinical=clinical,
                        line=None,
                        invoice=None,
                        picking=None,
                        on_hand=0.0,
                        sale=None,
                    )
                )
                seen_orders.add(order_id)
                continue
            rows.append(_prescription_row_for_clinical(odoo, clinical))
            seen_orders.add(order_id)
    extra_rows = unlisted.list_rows(patient_uuid=patient_uuid)
    extra_uuids = [
        str(row.get("orderUuid") or "")
        for row in extra_rows
        if str(row.get("orderUuid") or "") and str(row.get("orderUuid") or "") not in seen_orders
    ]
    if extra_uuids:
        extra_workers = min(8, max(len(extra_uuids), 1))
        with ThreadPoolExecutor(max_workers=extra_workers) as pool:
            extra_clinicals = list(pool.map(lambda uuid: _safe_openmrs_order(uuid, cookie), extra_uuids))
        for clinical in extra_clinicals:
            if not clinical:
                continue
            if patient_uuid and clinical.get("patientUuid") != patient_uuid:
                continue
            if clinical.get("stopped"):
                unlisted.forget(str(clinical.get("uuid") or ""))
                continue
            if not unlisted.not_in_pharmacy_order(clinical):
                unlisted.forget(str(clinical.get("uuid") or ""))
                continue
            rows.append(
                serialize_prescription(
                    clinical=clinical,
                    line=None,
                    invoice=None,
                    picking=None,
                    on_hand=0.0,
                    sale=None,
                )
            )
    ready = [row for row in rows if row.get("dispensingStatus") == "READY TO DISPENSE"]
    other = [row for row in rows if row.get("dispensingStatus") != "READY TO DISPENSE"]
    ready.sort(key=lambda row: str(row.get("ordered") or ""), reverse=True)
    other.sort(key=lambda row: str(row.get("ordered") or ""), reverse=True)
    import consultation as clinical

    marked = clinical.load_nhis_patients(odoo)
    for row in [*ready, *other]:
        row["nhis"] = str(row.get("patientUuid") or "") in marked
    return {
        "status": "ok",
        "ready": ready,
        "other": other,
        "nhis": bool(patient_uuid and patient_uuid in marked),
    }


def _deliver_billed_line(odoo: OdooReader, order_uuid: str) -> None:
    """Hand over a billed medicine that has no open shelf movement."""
    matched = sale_line_for_order(odoo, order_uuid)
    if not matched:
        raise ApiError(409, "not_ready", "This prescription is not ready to dispense yet.")
    line, sale = matched
    line_id = int(line["id"])
    requested = as_float(line.get("product_uom_qty"))
    delivered = as_float(line.get("qty_delivered"))
    remaining = max(requested - delivered, 0)
    if remaining <= 0.0001:
        raise ApiError(409, "already_dispensed", "This medication has already been dispensed.")
    product_id = many2one_id(line.get("product_id"))
    kind = ""
    if product_id:
        rows = odoo.read("product.product", [product_id], ["type"])
        kind = str((rows[0].get("type") if rows else "") or "")
    pickings = outgoing_pickings(odoo, int(sale["id"]))
    already_moved = any(str(row.get("state") or "") == "done" for row in pickings)
    if kind == "product" and not already_moved:
        location_id = stock_location_id(odoo, sale)
        on_hand = on_hand_quantity(odoo, product_id or 0, location_id)
        if on_hand + 0.0001 < remaining:
            raise ApiError(
                409,
                "insufficient_stock",
                "Not enough stock to dispense this medication.",
            )
        import pharmacy_manage

        pharmacy_manage.apply_stock(odoo, int(product_id), round(on_hand - remaining, 4))
    execute(odoo, "sale.order.line", "write", [[line_id], {"qty_delivered": requested}])


def _validate_for_dispense(order_uuid: str, cookie: str) -> tuple[OdooReader, dict[str, Any]]:
    import pharmacy_unlisted as unlisted

    clinical = load_openmrs_order(order_uuid, cookie)
    if clinical.get("stopped"):
        raise ApiError(409, "prescription_stopped", "This prescription has been stopped.")
    if unlisted.not_in_pharmacy_order(clinical):
        raise ApiError(
            409,
            "not_in_pharmacy",
            unlisted.NOT_IN_PHARMACY_REASON,
        )
    odoo = odoo_reader()
    matched = sale_line_for_order(odoo, order_uuid)
    if not matched:
        raise ApiError(
            409,
            "not_ready",
            "This prescription is not ready to dispense yet.",
        )
    line, sale = matched
    if sale.get("state") not in {"sale", "done"}:
        raise ApiError(
            409,
            "not_ready",
            "This prescription is not ready to dispense yet. Confirm the pharmacy bill first.",
        )
    partner = find_partner(
        odoo,
        {"uuid": clinical.get("patientUuid") or "", "mrn": clinical.get("mrn") or "", "name": ""},
    )
    sale_partner = many2one_id(sale.get("partner_id"))
    if partner and sale_partner and int(partner["id"]) != sale_partner:
        raise ApiError(409, "wrong_patient", "This prescription does not belong to this patient.")
    # Payment is intentionally not checked. Dispense and payment are separate events.
    pickings = outgoing_pickings(odoo, int(sale["id"]))
    picking = choose_picking(pickings)
    requested = as_float(line.get("product_uom_qty"))
    delivered = as_float(line.get("qty_delivered"))
    remaining = max(requested - delivered, 0)
    if delivered + 0.0001 >= requested and requested > 0:
        raise ApiError(409, "already_dispensed", "This medication has already been dispensed.")
    live = bool(picking) and str(picking.get("state") or "") not in {"done", "cancel", "cancelled"}
    if not live:
        if str(sale.get("state") or "") not in {"sale", "done"}:
            raise ApiError(
                409,
                "not_ready",
                "This prescription is not ready to dispense yet. Confirm the pharmacy bill first.",
            )
        return odoo, {"id": 0, "state": "line", "sale_id": int(sale["id"])}
    if many2one_id(picking.get("sale_id")) != int(sale["id"]):
        raise ApiError(409, "wrong_picking", "This prescription is not ready to dispense yet.")
    product_id = many2one_id(line.get("product_id"))
    location_id = stock_location_id(odoo, sale)
    on_hand = on_hand_quantity(odoo, product_id or 0, location_id)
    if on_hand + 0.0001 < remaining:
        raise ApiError(
            409,
            "insufficient_stock",
            "Not enough stock to dispense this medication.",
        )
    return odoo, picking


def _pick_ids_from_wizard_context(context: dict[str, Any], fallback_picking_id: int) -> list[int]:
    """Extract picking ids from Odoo validate / backorder wizard context."""
    raw = (
        context.get("button_validate_picking_ids")
        or context.get("default_pick_ids")
        or [fallback_picking_id]
    )
    ids: list[int] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, int):
                ids.append(item)
            elif isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] in {4, 6}:
                # [(4, id)] or [(6, 0, [ids])]
                if item[0] == 4:
                    ids.append(int(item[1]))
                elif item[0] == 6 and len(item) >= 3 and isinstance(item[2], (list, tuple)):
                    ids.extend(int(value) for value in item[2])
            elif isinstance(item, (list, tuple)) and item:
                try:
                    ids.append(int(item[-1]))
                except (TypeError, ValueError):
                    continue
    return ids or [fallback_picking_id]


def _complete_picking(odoo: OdooReader, picking_id: int) -> None:
    try:
        execute(odoo, "stock.picking", "action_set_quantities_to_reservation", [[picking_id]])
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, TypeError):
        pass
    try:
        execute(odoo, "stock.picking", "action_assign", [[picking_id]])
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, TypeError):
        pass
    try:
        result = execute(
            odoo,
            "stock.picking",
            "button_validate",
            [[picking_id]],
            {"context": {"validation_confirmed": True, "skip_sms": True}},
        )
    except xmlrpc.client.Fault as error:
        done = odoo.read("stock.picking", [picking_id], ["state"])
        if done and done[0].get("state") == "done":
            return
        raise ApiError(
            502,
            "odoo_dispense_failed",
            "The medication could not be dispensed. Refresh and try again.",
        ) from error
    # button_validate may return True/False/None, or a wizard action dict.
    # Never use `result in {True, False, None}` — dicts are unhashable.
    if result is True or result is False or result is None:
        return
    if not isinstance(result, dict):
        return
    if result.get("type") == "ir.actions.act_window_close":
        return
    model = result.get("res_model") or ""
    res_id = result.get("res_id")
    try:
        if model == "stock.picking.validate.wizard":
            move_lines = odoo.read("stock.picking", [picking_id], ["move_line_ids"])
            line_ids = [
                int(item)
                for item in ((move_lines[0].get("move_line_ids") if move_lines else []) or [])
            ]
            wizard_id = int(
                execute(
                    odoo,
                    "stock.picking.validate.wizard",
                    "create",
                    [{"picking_id": picking_id, "move_lines": [(6, 0, line_ids)]}],
                )
            )
            execute(
                odoo,
                "stock.picking.validate.wizard",
                "btn_confirm",
                [[wizard_id]],
                {"context": {"validation_confirmed": True}},
            )
            return
        if model == "stock.immediate.transfer" and res_id:
            execute(odoo, "stock.immediate.transfer", "process", [[int(res_id)]])
            return
        if model == "stock.immediate.transfer":
            context = dict(result.get("context") or {})
            pick_ids = context.get("default_pick_ids") or context.get("button_validate_picking_ids") or [
                picking_id
            ]
            if isinstance(pick_ids, (list, tuple)) and pick_ids and isinstance(pick_ids[0], (list, tuple)):
                # [(6, 0, [ids])] style — unwrap
                pick_ids = pick_ids[0][2] if len(pick_ids[0]) >= 3 else [picking_id]
            wizard_id = int(
                execute(
                    odoo,
                    "stock.immediate.transfer",
                    "create",
                    [{"pick_ids": [(6, 0, [int(item) for item in pick_ids])]}],
                    {"context": context},
                )
            )
            execute(odoo, "stock.immediate.transfer", "process", [[wizard_id]])
            return
        if model == "stock.backorder.confirmation":
            # Multi-line deliveries often need a backorder when one drug has stock
            # and another does not. Complete what is done; leave the rest open.
            context = dict(result.get("context") or {})
            pick_ids = _pick_ids_from_wizard_context(context, picking_id)
            wizard_id = int(res_id) if res_id else int(
                execute(
                    odoo,
                    "stock.backorder.confirmation",
                    "create",
                    [{"pick_ids": [(6, 0, pick_ids)]}],
                    {"context": context},
                )
            )
            execute(
                odoo,
                "stock.backorder.confirmation",
                "process",
                [[wizard_id]],
                {"context": {**context, "button_validate_picking_ids": pick_ids}},
            )
            done = odoo.read("stock.picking", [picking_id], ["state"])
            if done and done[0].get("state") == "done":
                return
            raise ApiError(
                502,
                "odoo_dispense_failed",
                "The medication could not be dispensed. Refresh and try again.",
            )
    except xmlrpc.client.Fault as error:
        done = odoo.read("stock.picking", [picking_id], ["state"])
        if done and done[0].get("state") == "done":
            return
        raise ApiError(
            502,
            "odoo_dispense_failed",
            "The medication could not be dispensed. Refresh and try again.",
        ) from error
    if model:
        done = odoo.read("stock.picking", [picking_id], ["state"])
        if done and done[0].get("state") == "done":
            return
        raise ApiError(
            502,
            "odoo_dispense_failed",
            "The medication could not be dispensed. Refresh and try again.",
        )


def _mark_keys(keys: list[str], status: str) -> None:
    with IDEMPOTENCY_LOCK:
        for key in keys:
            if key:
                IDEMPOTENCY[key] = {"status": status}


def _clear_pending(keys: list[str]) -> None:
    with IDEMPOTENCY_LOCK:
        for key in keys:
            current = IDEMPOTENCY.get(key) or {}
            if current.get("status") == "pending":
                IDEMPOTENCY.pop(key, None)


def dispense_prescription(order_uuid: str, cookie: str, request_id: str | None = None) -> dict[str, Any]:
    user = require_pharmacist(cookie)
    request_key = (request_id or "").strip()
    order_key = f"order:{order_uuid}"
    keys = [order_key, request_key]
    with IDEMPOTENCY_LOCK:
        order_state = IDEMPOTENCY.get(order_key) or {}
        request_state = IDEMPOTENCY.get(request_key) if request_key else None
        if order_state.get("status") == "pending" or (request_state or {}).get("status") == "pending":
            raise ApiError(
                409,
                "dispense_in_progress",
                "This prescription is already being dispensed.",
            )
        if (request_state or {}).get("status") == "done":
            payload = assemble_prescription(order_uuid, cookie)
            payload["success"] = True
            payload["alreadyDispensed"] = True
            payload["recordedBy"] = user.get("username") or ""
            return payload
        if order_state.get("status") == "done":
            raise ApiError(409, "already_dispensed", "This medication has already been dispensed.")
        IDEMPOTENCY[order_key] = {"status": "pending"}
        if request_key:
            IDEMPOTENCY[request_key] = {"status": "pending"}
    try:
        odoo, picking = _validate_for_dispense(order_uuid, cookie)
        if int(picking.get("id") or 0) == 0:
            _deliver_billed_line(odoo, order_uuid)
        else:
            picking_id = int(picking["id"])
            fresh = odoo.read("stock.picking", [picking_id], ["state", "sale_id"])
            if not fresh:
                raise ApiError(409, "not_ready", "This prescription is not ready to dispense yet.")
            if fresh[0].get("state") == "done":
                raise ApiError(409, "already_dispensed", "This medication has already been dispensed.")
            matched = sale_line_for_order(odoo, order_uuid)
            product_ids: set[int] = set()
            if matched:
                product_id = many2one_id(matched[0].get("product_id"))
                if product_id:
                    product_ids.add(product_id)
                sale_id = int(matched[1]["id"])
                siblings = sale_prescription_lines(odoo, sale_id)
                # On multi-medicine sales, deliver only this product and backorder the rest.
                if len(siblings) > 1 and product_ids:
                    _prepare_partial_dispense(odoo, picking_id, product_ids)
            _complete_picking(odoo, picking_id)
        payload = assemble_prescription(order_uuid, cookie)
        if payload.get("dispensingStatus") != "DISPENSED":
            # Confirm line delivery even when a backorder remains for siblings.
            line_check = sale_line_for_order(odoo, order_uuid)
            if not line_check:
                raise ApiError(
                    502,
                    "odoo_dispense_failed",
                    "The medication could not be dispensed. Refresh and try again.",
                )
            requested = as_float(line_check[0].get("product_uom_qty"))
            delivered = as_float(line_check[0].get("qty_delivered"))
            if delivered + 0.0001 < requested or requested <= 0:
                raise ApiError(
                    502,
                    "odoo_dispense_failed",
                    "The medication could not be dispensed. Refresh and try again.",
                )
            payload = assemble_prescription(order_uuid, cookie)
        _mark_keys(keys, "done")
        payload["success"] = True
        payload["alreadyDispensed"] = False
        payload["recordedBy"] = user.get("username") or ""
        return payload
    except ApiError as error:
        if error.code == "already_dispensed":
            _mark_keys(keys, "done")
        else:
            _clear_pending(keys)
        raise
    except Exception:
        _clear_pending(keys)
        raise
