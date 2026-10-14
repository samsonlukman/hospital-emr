"""External (unregistered) radiology imaging studies.

Odoo is the financial source of truth. No OpenMRS patient or order is created.
Study identity is radiology-ext:{token}:{index}. Reports and link audit live in
Hospital EMR SQLite (same DB as Family Cards / admin audit).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

import radiology as imaging
import radiology_menu
import xmlrpc.client
from admin_audit import AUDIT_DB_PATH
from server import ApiError

EXT_PREFIX = "radiology-ext:"
WALKIN_REF_PREFIX = "RAD-WALKIN:"
SOURCE_EXTERNAL_REFERRAL = "external_referral"
SOURCE_RADIOLOGY_DIRECT = "radiology_direct"
PATIENT_TYPE_EXTERNAL = "external"
PATIENT_TYPE_REGISTERED = "registered"

IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}
STORE_LOCK = threading.Lock()

execute = imaging.execute
odoo_reader = imaging.odoo_reader
many2one_id = imaging.many2one_id
many2one_name = imaging.many2one_name
as_float = imaging.as_float
require_radiology_user = imaging.require_radiology_user


def study_external_key(token: str, index: int = 0) -> str:
    return f"{EXT_PREFIX}{token}:{index}"


def is_external_study_id(value: str) -> bool:
    return str(value or "").startswith(EXT_PREFIX)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or os.environ.get("ABIKAN_ADMIN_AUDIT_DB") or AUDIT_DB_PATH)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        if not db_path.exists():
            raise
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(path: str | None = None) -> None:
    with STORE_LOCK:
        connection = _connect(path)
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS radiology_external_study (
                    study_id TEXT PRIMARY KEY,
                    sale_id INTEGER NOT NULL,
                    sale_name TEXT NOT NULL DEFAULT '',
                    token TEXT NOT NULL,
                    buyer_name TEXT NOT NULL,
                    buyer_phone TEXT NOT NULL DEFAULT '',
                    buyer_sex TEXT NOT NULL DEFAULT '',
                    buyer_dob TEXT NOT NULL DEFAULT '',
                    buyer_address TEXT NOT NULL DEFAULT '',
                    indication TEXT NOT NULL DEFAULT '',
                    request_source TEXT NOT NULL,
                    referrer TEXT NOT NULL DEFAULT '',
                    concept_uuid TEXT NOT NULL DEFAULT '',
                    investigation TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    linked_patient_uuid TEXT NOT NULL DEFAULT '',
                    linked_at TEXT NOT NULL DEFAULT '',
                    linked_by TEXT NOT NULL DEFAULT '',
                    report_text TEXT NOT NULL DEFAULT '',
                    report_by TEXT NOT NULL DEFAULT '',
                    report_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rad_ext_sale ON radiology_external_study(sale_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rad_ext_phone ON radiology_external_study(buyer_phone)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rad_ext_linked ON radiology_external_study(linked_patient_uuid)"
            )
            connection.commit()
        finally:
            connection.close()


def _upsert_study_row(row: dict[str, Any], path: str | None = None) -> None:
    ensure_schema(path)
    with STORE_LOCK:
        connection = _connect(path)
        try:
            connection.execute(
                """
                INSERT INTO radiology_external_study (
                    study_id, sale_id, sale_name, token, buyer_name, buyer_phone, buyer_sex,
                    buyer_dob, buyer_address, indication, request_source, referrer,
                    concept_uuid, investigation, created_by, created_at,
                    linked_patient_uuid, linked_at, linked_by, report_text, report_by, report_at
                ) VALUES (
                    :study_id, :sale_id, :sale_name, :token, :buyer_name, :buyer_phone, :buyer_sex,
                    :buyer_dob, :buyer_address, :indication, :request_source, :referrer,
                    :concept_uuid, :investigation, :created_by, :created_at,
                    :linked_patient_uuid, :linked_at, :linked_by, :report_text, :report_by, :report_at
                )
                ON CONFLICT(study_id) DO UPDATE SET
                    sale_id=excluded.sale_id,
                    sale_name=excluded.sale_name,
                    buyer_name=excluded.buyer_name,
                    buyer_phone=excluded.buyer_phone,
                    buyer_sex=excluded.buyer_sex,
                    buyer_dob=excluded.buyer_dob,
                    buyer_address=excluded.buyer_address,
                    indication=excluded.indication,
                    request_source=excluded.request_source,
                    referrer=excluded.referrer,
                    concept_uuid=excluded.concept_uuid,
                    investigation=excluded.investigation,
                    linked_patient_uuid=excluded.linked_patient_uuid,
                    linked_at=excluded.linked_at,
                    linked_by=excluded.linked_by,
                    report_text=excluded.report_text,
                    report_by=excluded.report_by,
                    report_at=excluded.report_at
                """,
                row,
            )
            connection.commit()
        finally:
            connection.close()


def _load_study_row(study_id: str, path: str | None = None) -> dict[str, Any] | None:
    ensure_schema(path)
    connection = _connect(path)
    try:
        row = connection.execute(
            "SELECT * FROM radiology_external_study WHERE study_id = ?",
            (study_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def _list_study_rows(path: str | None = None) -> list[dict[str, Any]]:
    ensure_schema(path)
    connection = _connect(path)
    try:
        rows = connection.execute(
            "SELECT * FROM radiology_external_study ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _ensure_walkin_partner(
    odoo: imaging.OdooReader,
    *,
    name: str,
    phone: str,
    sex: str,
    dob: str,
    address: str,
    token: str,
) -> dict[str, Any]:
    clean_name = re.sub(r"\s+", " ", name).strip()
    if len(clean_name) < 2:
        raise ApiError(422, "buyer_required", "Enter the person's full name.")
    ref = f"{WALKIN_REF_PREFIX}{token}"
    existing = odoo.search_read(
        "res.partner",
        [("ref", "=", ref)],
        ["id", "name", "ref", "uuid", "phone", "comment"],
        limit=1,
    )
    if existing:
        row = existing[0]
        if not str(row.get("uuid") or "").strip():
            link = f"radiology:{token}"
            execute(odoo, "res.partner", "write", [[int(row["id"])], {"uuid": link}])
            row["uuid"] = link
        return row
    comment_parts = []
    if sex:
        comment_parts.append(f"Sex: {sex}")
    if dob:
        comment_parts.append(f"DOB/Age: {dob}")
    if address:
        comment_parts.append(f"Address: {address}")
    values: dict[str, Any] = {
        "name": clean_name,
        "ref": ref,
        "uuid": f"radiology:{token}",
        "customer_rank": 1,
        "company_type": "person",
        "comment": " | ".join(comment_parts),
    }
    if phone.strip():
        values["phone"] = phone.strip()
    partner_id = int(execute(odoo, "res.partner", "create", [values]))
    rows = odoo.read("res.partner", [partner_id], ["id", "name", "ref", "uuid", "phone", "comment"])
    return rows[0]


def _normalize_request_source(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"external_referral", "external", "referral", "outside"}:
        return SOURCE_EXTERNAL_REFERRAL
    if text in {"radiology_direct", "direct", "desk"}:
        return SOURCE_RADIOLOGY_DIRECT
    if text in {"doctor_order", "doctor"}:
        # Outside doctor's note without hospital registration → external referral.
        return SOURCE_EXTERNAL_REFERRAL
    return SOURCE_EXTERNAL_REFERRAL


def request_source_label(source: str) -> str:
    if source == SOURCE_RADIOLOGY_DIRECT:
        return "Radiology Direct"
    if source == SOURCE_EXTERNAL_REFERRAL:
        return "External Referral"
    return imaging.request_source_label(source)


def _payment_bits(invoice: dict[str, Any] | None, has_charge: bool) -> tuple[str, str]:
    payment = imaging.invoice_payment_status(invoice, has_charge)
    if not has_charge:
        return payment, "Price pending"
    if payment == "PAID":
        return payment, "Paid"
    if payment == "PARTIALLY PAID":
        return payment, "Partially paid"
    return payment, "Unpaid"


def _serialize_study(
    *,
    meta: dict[str, Any],
    sale: dict[str, Any] | None,
    invoice: dict[str, Any] | None,
    currency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    has_charge = bool(sale)
    payment, billing = _payment_bits(invoice, has_charge)
    has_report = bool(_text(meta.get("report_text")))
    fee_formatted = None
    if has_charge and currency and invoice:
        fee_formatted = imaging.format_money(as_float(invoice.get("amount_total")), currency).get("formatted")
    elif has_charge and currency and sale:
        fee_formatted = imaging.format_money(as_float(sale.get("amount_total")), currency).get("formatted")
    linked = _text(meta.get("linked_patient_uuid"))
    return {
        "uuid": meta["study_id"],
        "studyId": meta["study_id"],
        "orderNumber": _text(meta.get("sale_name")) or _text((sale or {}).get("name")),
        "investigation": _text(meta.get("investigation")) or "Imaging examination",
        "conceptUuid": _text(meta.get("concept_uuid")),
        "category": (radiology_menu.entry_by_concept(_text(meta.get("concept_uuid"))) or {}).get("group") or "",
        "patientUuid": linked,
        "patientName": _text(meta.get("buyer_name")) or "External patient",
        "mrn": "",
        "visitUuid": "",
        "encounterUuid": "",
        "visitType": "",
        "dailyVisitNumber": "",
        "ordered": _text(meta.get("created_at")),
        "urgency": "Routine",
        "comment": _text(meta.get("indication")),
        "clinicalIndication": _text(meta.get("indication")),
        "requestSource": _text(meta.get("request_source")) or SOURCE_EXTERNAL_REFERRAL,
        "requestSourceLabel": request_source_label(_text(meta.get("request_source"))),
        # Remain External even after link — linkage is recorded separately.
        "patientType": PATIENT_TYPE_EXTERNAL,
        "patientTypeLabel": "External Patient",
        "buyerPhone": _text(meta.get("buyer_phone")),
        "buyerSex": _text(meta.get("buyer_sex")),
        "buyerDob": _text(meta.get("buyer_dob")),
        "buyerAddress": _text(meta.get("buyer_address")),
        "referrer": _text(meta.get("referrer")),
        "provider": _text(meta.get("created_by")) or "—",
        "hasReport": has_report,
        "reportStatus": "Report available" if has_report else "Report pending",
        "reportText": _text(meta.get("report_text")),
        "reportedBy": _text(meta.get("report_by")),
        "reportedAt": _text(meta.get("report_at")),
        "hasCharge": has_charge,
        "paymentStatus": payment,
        "billingStatus": billing,
        "feeFormatted": fee_formatted,
        "saleId": str(meta.get("sale_id") or ""),
        "invoiceName": _text((invoice or {}).get("name")),
        "linkedPatientUuid": linked,
        "linkedAt": _text(meta.get("linked_at")),
        "linkedBy": _text(meta.get("linked_by")),
        "isExternal": True,
    }


def list_external_studies(cookie: str) -> list[dict[str, Any]]:
    require_radiology_user(cookie)
    rows = _list_study_rows()
    if not rows:
        return []
    try:
        odoo = odoo_reader()
        currency = imaging.radiology_currency(odoo)
    except ApiError:
        odoo = None
        currency = None
    sales_by_id: dict[int, dict[str, Any]] = {}
    if odoo:
        sale_ids = [int(row["sale_id"]) for row in rows if row.get("sale_id")]
        if sale_ids:
            for sale in odoo.read(
                "sale.order",
                sale_ids,
                ["name", "state", "partner_id", "invoice_ids", "origin", "amount_total", "create_date"],
            ):
                sales_by_id[int(sale["id"])] = sale
    items = []
    for meta in rows:
        sale = sales_by_id.get(int(meta.get("sale_id") or 0))
        invoice = imaging.related_invoice(odoo, sale) if odoo and sale else None
        items.append(_serialize_study(meta=meta, sale=sale, invoice=invoice, currency=currency))
    return items


def get_external_study(study_id: str, cookie: str) -> dict[str, Any]:
    require_radiology_user(cookie)
    study_id = unquote(study_id)
    if not is_external_study_id(study_id):
        raise ApiError(404, "study_not_found", "This external imaging study was not found.")
    meta = _load_study_row(study_id)
    if not meta:
        raise ApiError(404, "study_not_found", "This external imaging study was not found.")
    odoo = odoo_reader()
    sale_id = int(meta["sale_id"])
    sales = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "origin", "amount_total", "create_date", "note"],
    )
    sale = sales[0] if sales else None
    invoice = imaging.related_invoice(odoo, sale) if sale else None
    currency = imaging.radiology_currency(odoo)
    payload = _serialize_study(meta=meta, sale=sale, invoice=invoice, currency=currency)
    payload["status"] = "ok"
    return payload


def create_external_study(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_radiology_user(cookie)
    request_id = _text(body.get("requestId")) or str(uuid.uuid4())
    token = request_id.replace(":", "")[:36]
    idem_key = f"radiology-ext-create:{token}"
    with IDEMPOTENCY_LOCK:
        state = IDEMPOTENCY.get(idem_key) or {}
        if state.get("status") == "pending":
            raise ApiError(409, "study_in_progress", "This imaging study is already being created.")
        if state.get("status") == "done" and state.get("studyId"):
            payload = get_external_study(str(state["studyId"]), cookie)
            payload["alreadyCreated"] = True
            return payload
        IDEMPOTENCY[idem_key] = {"status": "pending"}
    try:
        services = body.get("services")
        if not isinstance(services, list) or not services:
            raise ApiError(422, "service_required", "Select an imaging examination.")
        first = services[0] if isinstance(services[0], dict) else {}
        service_id = _text(first.get("serviceId"))
        concept_uuid = _text(first.get("conceptUuid"))
        entry = radiology_menu.resolve_orderable(service_id, concept_uuid)
        if not entry or not entry.get("conceptUuid"):
            raise ApiError(422, "not_orderable", "That imaging examination is not available yet.")
        concept_uuid = str(entry["conceptUuid"])
        investigation = str(entry.get("hospitalName") or entry.get("conceptName") or "Imaging examination")
        amount = imaging.parse_radiology_amount(body.get("amount"))

        odoo = odoo_reader()
        masters = imaging.ensure_radiology_masters(odoo)
        shop = imaging.ensure_radiology_ngn_pricelist(odoo, masters["shop"])
        product = imaging.find_radiology_product(odoo, concept_uuid)
        price = amount
        if price < 0:
            raise ApiError(422, "amount_invalid", "Enter a valid imaging fee in naira.")

        partner = _ensure_walkin_partner(
            odoo,
            name=_text(body.get("buyerName") or body.get("patientName")),
            phone=_text(body.get("buyerPhone") or body.get("phone")),
            sex=_text(body.get("buyerSex") or body.get("sex")),
            dob=_text(body.get("buyerDob") or body.get("dateOfBirth") or body.get("age")),
            address=_text(body.get("buyerAddress") or body.get("address")),
            token=token,
        )
        request_source = _normalize_request_source(_text(body.get("requestSource")))
        indication = _text(body.get("indication") or body.get("clinicalIndication"))
        referrer = _text(body.get("referrer") or body.get("referrerName"))
        study_id = study_external_key(token, 0)
        note = "\n".join(
            part
            for part in (
                f"Patient Type: External Patient",
                f"Request Source: {request_source_label(request_source)}",
                f"Indication: {indication}" if indication else "",
                f"Referrer: {referrer}" if referrer else "",
                f"Study: {study_id}",
            )
            if part
        )
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = imaging._radiology_pricelist_id(shop)
        currency_id = imaging._ngn_currency_id(odoo)
        sale_vals: dict[str, Any] = {
            "partner_id": int(partner["id"]),
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "pricelist_id": pricelist_id,
            "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
            "origin": f"{EXT_PREFIX}{token}",
            "care_setting": "opd",
            "note": note,
            "order_line": [
                (
                    0,
                    0,
                    {
                        "product_id": int(product["id"]),
                        "name": investigation,
                        "product_uom_qty": 1,
                        "price_unit": price,
                        "tax_id": [(6, 0, [])],
                        "external_order_id": study_id,
                        "external_id": f"walkin:{token}",
                    },
                )
            ],
        }
        if currency_id:
            sale_vals["currency_id"] = int(currency_id)
        sale_id = int(execute(odoo, "sale.order", "create", [sale_vals]))
        sale_rows = odoo.read("sale.order", [sale_id], ["name", "order_line", "state"])
        sale = sale_rows[0]
        line_ids = [int(item) for item in (sale.get("order_line") or [])]
        if line_ids:
            try:
                execute(
                    odoo,
                    "sale.order.line",
                    "write",
                    [line_ids, {"tax_id": [(6, 0, [])], "price_unit": price}],
                )
            except xmlrpc.client.Fault:
                pass
        imaging._confirm_sale(odoo, sale_id)
        confirmed = odoo.read("sale.order", [sale_id], ["name", "state", "invoice_ids", "amount_total"])
        if not confirmed or confirmed[0].get("state") not in {"sale", "done"}:
            raise ApiError(
                502,
                "odoo_charge_failed",
                "The imaging bill could not be created. Refresh and try again.",
            )
        sale = confirmed[0]
        meta = {
            "study_id": study_id,
            "sale_id": sale_id,
            "sale_name": _text(sale.get("name")),
            "token": token,
            "buyer_name": _text(partner.get("name")),
            "buyer_phone": _text(body.get("buyerPhone") or body.get("phone") or partner.get("phone")),
            "buyer_sex": _text(body.get("buyerSex") or body.get("sex")),
            "buyer_dob": _text(body.get("buyerDob") or body.get("dateOfBirth") or body.get("age")),
            "buyer_address": _text(body.get("buyerAddress") or body.get("address")),
            "indication": indication,
            "request_source": request_source,
            "referrer": referrer,
            "concept_uuid": concept_uuid,
            "investigation": investigation,
            "created_by": _text(user.get("username") or user.get("display")),
            "created_at": _now(),
            "linked_patient_uuid": "",
            "linked_at": "",
            "linked_by": "",
            "report_text": "",
            "report_by": "",
            "report_at": "",
        }
        _upsert_study_row(meta)
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY[idem_key] = {"status": "done", "studyId": study_id}
        payload = get_external_study(study_id, cookie)
        payload["alreadyCreated"] = False
        payload["message"] = "External imaging study created."
        return payload
    except Exception:
        with IDEMPOTENCY_LOCK:
            if (IDEMPOTENCY.get(idem_key) or {}).get("status") == "pending":
                IDEMPOTENCY.pop(idem_key, None)
        raise


def save_external_report(study_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_radiology_user(cookie)
    study_id = unquote(study_id)
    meta = _load_study_row(study_id)
    if not meta:
        raise ApiError(404, "study_not_found", "This external imaging study was not found.")
    text = _text(body.get("text") or body.get("report") or body.get("findings"))
    if not text:
        raise ApiError(422, "report_required", "Enter the radiology findings and impression before saving.")
    meta["report_text"] = text
    meta["report_by"] = _text(user.get("username") or user.get("display"))
    meta["report_at"] = _now()
    _upsert_study_row(meta)
    payload = get_external_study(study_id, cookie)
    payload["message"] = "Report saved."
    return payload


def link_external_study(study_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Link an external study to a registered patient. Does not duplicate the study."""
    user = require_radiology_user(cookie)
    study_id = unquote(study_id)
    meta = _load_study_row(study_id)
    if not meta:
        raise ApiError(404, "study_not_found", "This external imaging study was not found.")
    patient_uuid = _text(body.get("patientUuid"))
    if not patient_uuid:
        raise ApiError(422, "patient_required", "Select the registered patient to link.")
    confirm = bool(body.get("confirm"))
    if not confirm:
        raise ApiError(
            422,
            "confirm_required",
            "Confirm that these imaging studies belong to this registered patient.",
        )
    if _text(meta.get("linked_patient_uuid")):
        if meta["linked_patient_uuid"] == patient_uuid:
            payload = get_external_study(study_id, cookie)
            payload["alreadyLinked"] = True
            return payload
        raise ApiError(
            409,
            "already_linked",
            "This imaging study is already linked to another registered patient.",
        )

    patient = imaging.load_openmrs_patient(patient_uuid, cookie)
    odoo = odoo_reader()
    partner = imaging.find_partner(odoo, patient)
    if not partner:
        raise ApiError(
            409,
            "account_not_found",
            "This patient has no financial account yet. Try again in a moment.",
        )
    sale_id = int(meta["sale_id"])
    execute(odoo, "sale.order", "write", [[sale_id], {"partner_id": int(partner["id"])}])
    lines = odoo.search_read(
        "sale.order.line",
        [("order_id", "=", sale_id)],
        ["id", "external_order_id"],
    )
    line_ids = [int(row["id"]) for row in lines if row.get("id")]
    if line_ids:
        execute(odoo, "sale.order.line", "write", [line_ids, {"external_id": patient_uuid}])
    sales = odoo.read("sale.order", [sale_id], ["note"])
    note = _text((sales[0] if sales else {}).get("note"))
    link_line = (
        f"Linked to registered patient {patient.get('mrn') or ''} "
        f"({patient_uuid}) by {user.get('username') or ''} at {_now()}"
    ).strip()
    execute(odoo, "sale.order", "write", [[sale_id], {"note": f"{note}\n{link_line}".strip()}])
    meta["linked_patient_uuid"] = patient_uuid
    meta["linked_at"] = _now()
    meta["linked_by"] = _text(user.get("username") or user.get("display"))
    _upsert_study_row(meta)
    payload = get_external_study(study_id, cookie)
    payload["message"] = "Imaging study linked to the registered patient."
    return payload


def studies_for_registered_patient(patient_uuid: str, cookie: str) -> list[dict[str, Any]]:
    require_radiology_user(cookie)
    ensure_schema()
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT * FROM radiology_external_study WHERE linked_patient_uuid = ? ORDER BY created_at DESC",
            (patient_uuid,),
        ).fetchall()
        metas = [dict(row) for row in rows]
    finally:
        connection.close()
    if not metas:
        return []
    odoo = odoo_reader()
    currency = imaging.radiology_currency(odoo)
    sale_ids = [int(row["sale_id"]) for row in metas]
    sales = {
        int(row["id"]): row
        for row in odoo.read(
            "sale.order",
            sale_ids,
            ["name", "state", "partner_id", "invoice_ids", "amount_total"],
        )
    }
    items = []
    for meta in metas:
        sale = sales.get(int(meta["sale_id"]))
        invoice = imaging.related_invoice(odoo, sale) if sale else None
        items.append(_serialize_study(meta=meta, sale=sale, invoice=invoice, currency=currency))
    return items
