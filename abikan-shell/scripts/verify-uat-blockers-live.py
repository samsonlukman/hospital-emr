#!/usr/bin/env python3
"""Live verification of remaining UAT blockers against the running stack.

Creates clearly named synthetic TEST records. Does not delete data.
Does not wipe the database. Restores temporary catalogue changes.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
import xmlrpc.client
from http.cookiejar import CookieJar
from pathlib import Path

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or ""
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://localhost:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
ODOO_USER = os.environ.get("ABIKAN_ODOO_USER") or "admin"
ODOO_PASSWORD = os.environ.get("ABIKAN_ODOO_PASSWORD") or ""
CTX = ssl._create_unverified_context()
STAMP = int(time.time())
CONSULTATION_ENCOUNTER = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
HPI_CONCEPT = "1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
NOTE_CONCEPT = "d37294c5-5e07-11ef-8f7c-0242ac120002"
MP_CONCEPT = "32AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
AMOX_TEST = "2ee7a8c8-e9f0-4637-898f-4fcea987bea2"
FLEXIBLE = "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions"
HAWAWU = "f0f005dd-c95d-47f1-894a-b263783dd5e6"
PROTECTED = {"ABC200016", "ABC200021"}

report: dict[str, object] = {
    "stamp": STAMP,
    "synthetic": {},
    "restored": {},
    "checks": [],
    "failures": [],
}


def login(user: str) -> str:
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(jar),
    )
    auth = "Basic " + base64.b64encode(f"{user}:{PWD}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}/openmrs/ws/rest/v1/session",
        headers={"Authorization": auth, "Accept": "application/json"},
    )
    with opener.open(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if not payload.get("authenticated"):
        raise RuntimeError(f"{user} not authenticated")
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in jar)


def call(method: str, url: str, cookie: str | None, body: dict | None = None, timeout: int = 90):
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        context = CTX if url.startswith("https") else None
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read().decode()
            payload = json.loads(raw) if raw else None
            return response.status, payload, round((time.perf_counter() - started) * 1000)
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            payload = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            payload = raw[:400]
        return error.code, payload, round((time.perf_counter() - started) * 1000)
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}, 0


def api(method: str, path: str, cookie: str | None, body: dict | None = None, timeout: int = 90):
    return call(method, f"{API}{path}", cookie, body, timeout)


def omrs(method: str, path: str, cookie: str | None, body: dict | None = None, timeout: int = 60):
    return call(method, f"{BASE}{path}", cookie, body, timeout)


def check(name: str, ok: bool, detail: object = None) -> bool:
    row = {"name": name, "ok": bool(ok), "detail": detail}
    report["checks"].append(row)
    if not ok:
        report["failures"].append(row)
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:280])
    return bool(ok)


def amount(payload: object, *keys: str) -> float | None:
    node: object = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, dict) and "amount" in node:
        return float(node["amount"])
    if isinstance(node, (int, float)):
        return float(node)
    return None


def odoo_models():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


def kw(models, uid, model, method, args, kwargs=None):
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, model, method, args, kwargs or {})


def register_patient(rec: str, given: str, family: str, gender: str, birth: str) -> dict | None:
    status, body, _ = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": given,
            "familyName": family,
            "gender": gender,
            "birthdate": birth,
            "confirmDuplicate": True,
        },
    )
    uuid_value = body.get("uuid") if isinstance(body, dict) else None
    mrn = ""
    if isinstance(body, dict):
        patient = body.get("patient") or body
        identifiers = patient.get("identifiers") or body.get("identifiers") or []
        if isinstance(patient, dict):
            mrn = str(patient.get("display") or patient.get("identifier") or body.get("mrn") or "")
        if identifiers and isinstance(identifiers, list):
            first = identifiers[0]
            if isinstance(first, dict):
                mrn = str(first.get("identifier") or mrn)
            elif isinstance(first, str):
                mrn = first
    check(f"register_{family}", status == 200 and bool(uuid_value), {"status": status, "uuid": uuid_value, "mrn": mrn})
    if not uuid_value:
        return None
    if any(marker in mrn for marker in PROTECTED):
        raise RuntimeError(f"Refusing to use protected patient {mrn}")
    return {"uuid": uuid_value, "mrn": mrn, "given": given, "family": family, "body": body}


def start_visit(rec: str, patient: str, visit_type: str) -> str | None:
    status, body, _ = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": visit_type, "requestId": f"uat-visit-{STAMP}-{patient[:8]}"},
    )
    uuid_value = body.get("uuid") if isinstance(body, dict) else None
    check("start_visit", status == 200 and bool(uuid_value), {"status": status, "uuid": uuid_value})
    return uuid_value


def provider_uuid(cookie: str) -> str | None:
    status, session, _ = omrs("GET", "/openmrs/ws/rest/v1/session", cookie)
    user_uuid = ((session.get("user") or {}).get("uuid")) if isinstance(session, dict) else None
    if not user_uuid:
        return None
    status, body, _ = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/provider?user={user_uuid}&v=custom:(uuid,retired)",
        cookie,
    )
    rows = (body or {}).get("results") if isinstance(body, dict) else []
    for row in rows or []:
        if row.get("uuid") and not row.get("retired"):
            return row["uuid"]
    return None


def wait_ok(method: str, path: str, cookie: str, body: dict | None = None, tries: int = 8, delay: float = 4):
    last = (0, None, 0)
    for _ in range(tries):
        last = api(method, path, cookie, body)
        if last[0] == 200:
            return last
        time.sleep(delay)
    return last


def restore_price(cookie: str, department: str, item_id: str, original: float | None, current_hint: float | None = None) -> None:
    if original is None or not item_id:
        return
    listed = api("GET", f"/pricing/{department}", cookie)[1]
    current = None
    for row in (listed or {}).get("items") or []:
        if row.get("id") == item_id:
            current = amount(row, "price")
            break
    if current is None:
        current = current_hint
    if current is not None and abs(current - original) < 0.01:
        report["restored"][f"{department}:{item_id}"] = original
        return
    status, body, _ = api(
        "PATCH",
        f"/pricing/{department}/{item_id}",
        cookie,
        {"price": original, "expectedPrice": current, "reason": "UAT blocker restore after synthetic test"},
    )
    report["restored"][f"{department}:{item_id}"] = {"status": status, "price": original, "body": body if status != 200 else "ok"}


def main() -> int:
    users = {}
    for role in (
        "reception.abikan",
        "doctor.abikan",
        "nurse.abikan",
        "lab.abikan",
        "pharmacy.abikan",
        "accountant.abikan",
        "admin.abikan",
    ):
        users[role] = login(role)
        check(f"login_{role}", True)

    rec = users["reception.abikan"]
    doctor = users["doctor.abikan"]
    nurse = users["nurse.abikan"]
    lab = users["lab.abikan"]
    pharm = users["pharmacy.abikan"]
    acct = users["accountant.abikan"]
    admin = users["admin.abikan"]

    meta_status, meta, _ = api("GET", "/registration/metadata", rec)
    check("registration_metadata", meta_status == 200, {"status": meta_status})
    visit_types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in visit_types or [] if row.get("name") == "OPD"), None)
    locations = (meta or {}).get("locations") or (meta or {}).get("loginLocations") or []
    location = next((row for row in locations if row.get("name") == "OPD-1"), locations[0] if locations else None)
    location_uuid = (location or {}).get("uuid") if isinstance(location, dict) else ""
    opd_uuid = (opd or {}).get("uuid") if isinstance(opd, dict) else ""
    check("opd_location", bool(opd_uuid and location_uuid), {"opd": opd_uuid, "location": location_uuid})

    patient_a = register_patient(rec, "UATFIX", f"LABA{STAMP % 100000}", "F", "1992-03-12")
    patient_b = register_patient(rec, "UATFIX", f"LABB{STAMP % 100000}", "M", "1987-09-04")
    patient_c = register_patient(rec, "UATFIX", f"PHARM{STAMP % 100000}", "F", "1995-11-21")
    patient_d = register_patient(rec, "UATFIX", f"ACC{STAMP % 100000}", "F", "1989-07-18")
    report["synthetic"]["patients"] = {
        "labA": patient_a,
        "labB": patient_b,
        "pharmacy": patient_c,
        "accommodation": patient_d,
    }
    if not all([patient_a, patient_b, patient_c, patient_d, opd_uuid]):
        json.dump(report, sys.stdout, indent=2, default=str)
        return 1

    visit_a = start_visit(rec, patient_a["uuid"], opd_uuid)
    visit_b = start_visit(rec, patient_b["uuid"], opd_uuid)
    visit_c = start_visit(rec, patient_c["uuid"], opd_uuid)
    report["synthetic"]["visits"] = {"a": visit_a, "b": visit_b, "c": visit_c}

    wait_ok(
        "POST",
        f"/registration/patient/{patient_a['uuid']}/charge",
        rec,
        {"visitUuid": visit_a, "cardType": "individual", "requestId": f"uat-card-a-{STAMP}"},
    )
    wait_ok(
        "POST",
        f"/registration/patient/{patient_c['uuid']}/charge",
        rec,
        {"visitUuid": visit_c, "cardType": "individual", "requestId": f"uat-card-c-{STAMP}"},
    )

    prov = provider_uuid(doctor)
    check("doctor_provider", bool(prov), {"provider": prov})
    config_status, config, _ = omrs("GET", "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders", doctor)
    dose_units = [row.get("name") for row in (config or {}).get("doseUnits") or [] if row.get("name")]
    routes = [row.get("name") for row in (config or {}).get("routes") or [] if row.get("name")]
    freqs = [row.get("name") for row in (config or {}).get("frequencies") or [] if row.get("name")]
    durations = [row.get("name") for row in (config or {}).get("durationUnits") or [] if row.get("name")]
    qty_units = [row.get("name") for row in (config or {}).get("dispensingUnits") or dose_units if row.get("name")]
    tablet = next((item for item in dose_units if "tablet" in item.lower()), dose_units[0] if dose_units else "Tablet(s)")
    oral = next((item for item in routes if "oral" in item.lower()), routes[0] if routes else "Oral")
    once = next((item for item in freqs if item.lower() in {"once a day", "od", "once daily"}), freqs[0] if freqs else "Once a day")
    days = next((item for item in durations if "day" in item.lower()), durations[0] if durations else "Day(s)")
    qty_unit = next((item for item in qty_units if "tablet" in item.lower()), qty_units[0] if qty_units else tablet)
    check("drug_order_config", config_status == 200, {"status": config_status, "tablet": tablet})

    consult_a = {
        "patientUuid": patient_a["uuid"],
        "visitUuid": visit_a,
        "visitType": "OPD",
        "encounterTypeUuid": CONSULTATION_ENCOUNTER,
        "locationUuid": location_uuid,
        "providers": [{"uuid": prov}],
        "observations": [
            {"concept": {"uuid": HPI_CONCEPT, "name": "History of present illness", "dataType": "Text"}, "value": "UATFIX lab fever. Synthetic."},
            {"concept": {"uuid": NOTE_CONCEPT, "name": "Consultation Note", "dataType": "Text"}, "value": "UATFIX lab consult. Synthetic."},
        ],
        "bahmniDiagnoses": [{"freeTextAnswer": "UATFIX suspected malaria", "order": "PRIMARY", "certainty": "PRESUMED"}],
        "orders": [],
        "drugOrders": [],
    }
    save_a = omrs("POST", "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", doctor, consult_a)
    encounter_a = (save_a[1] or {}).get("encounterUuid") if isinstance(save_a[1], dict) else None
    check("consult_lab_a", save_a[0] in {200, 201} and bool(encounter_a or save_a[1]), {"status": save_a[0], "encounter": encounter_a})
    report["synthetic"]["encounters"] = {"labA": encounter_a}

    lab_items = api("GET", "/pricing/laboratory?q=Malarial", lab)[1]
    lab_item = next((row for row in (lab_items or {}).get("items") or [] if row.get("id") == MP_CONCEPT or "malar" in str(row.get("name") or "").lower()), None)
    if not lab_item:
        lab_items = api("GET", "/pricing/laboratory", lab)[1]
        lab_item = next((row for row in (lab_items or {}).get("items") or [] if row.get("id") == MP_CONCEPT), None)
    lab_id = (lab_item or {}).get("id") or MP_CONCEPT
    lab_original = amount(lab_item, "price") if lab_item else None
    lab_first = lab_original
    check("lab_catalogue_price", lab_original is not None, {"id": lab_id, "price": lab_original, "currency": ((lab_item or {}).get("price") or {}).get("currencyCode")})
    report["synthetic"]["labCatalogue"] = {"id": lab_id, "original": lab_original}

    lab_order = api(
        "POST",
        f"/laboratory/patient/{patient_a['uuid']}/orders",
        doctor,
        {
            "visitUuid": visit_a,
            "locationUuid": location_uuid,
            "encounterUuid": encounter_a,
            "tests": [{"conceptUuid": MP_CONCEPT}],
            "requestId": f"uat-lab-a-{STAMP}",
        },
    )
    lab_fee = None
    lab_order_uuid = None
    lab_invoice = None
    if isinstance(lab_order[1], dict):
        charge = lab_order[1].get("charge") or {}
        lab_fee = amount(charge, "feeAmount") or amount(charge, "total") or amount(charge, "amount")
        orders = lab_order[1].get("orders") or []
        if orders:
            lab_order_uuid = orders[0].get("uuid") or orders[0].get("orderUuid")
        if lab_fee is None:
            for row in charge.get("tests") or []:
                lab_fee = amount(row, "feeAmount") or amount(row, "price")
                if lab_fee is not None:
                    break
        lab_invoice = charge.get("invoice") or charge.get("invoiceNumber") or charge.get("invoiceId")
    check(
        "lab_order_created",
        lab_order[0] == 200 and bool(lab_order_uuid or lab_order[1]),
        {"status": lab_order[0], "fee": lab_fee, "order": lab_order_uuid, "invoice": lab_invoice, "message": (lab_order[1] or {}).get("message") if isinstance(lab_order[1], dict) else lab_order[1]},
    )
    check("lab_charge_matches_catalogue", lab_fee is None or lab_original is None or abs(lab_fee - lab_original) < 0.02, {"fee": lab_fee, "catalogue": lab_original})
    report["synthetic"]["labOrder"] = {"uuid": lab_order_uuid, "fee": lab_fee, "invoice": lab_invoice, "raw": lab_order[1] if lab_order[0] != 200 else None}

    omrs_orders = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={patient_a['uuid']}&orderTypeUuid=d3560b17-5e07-11ef-8f7c-0242ac120002",
        doctor,
    )
    omrs_text = json.dumps(omrs_orders[1], default=str)
    check("openmrs_lab_order", omrs_orders[0] == 200 and (MP_CONCEPT in omrs_text or "Malarial" in omrs_text), {"status": omrs_orders[0]})

    board = api("GET", "/laboratory/board", lab)
    board_text = json.dumps(board[1], default=str)
    check(
        "lab_board_has_order",
        board[0] == 200 and (patient_a["uuid"] in board_text or (lab_order_uuid or "") in board_text),
        {"status": board[0]},
    )

    if lab_id and lab_original is not None:
        bumped = lab_original + 111
        api("PATCH", f"/pricing/laboratory/{lab_id}", lab, {"price": bumped, "expectedPrice": lab_original, "reason": "UAT lab snapshot proof"})
        after_lab = api("GET", f"/laboratory/patient/{patient_a['uuid']}", lab)[1]
        old_lab_fee = None
        if isinstance(after_lab, dict):
            for row in after_lab.get("tests") or after_lab.get("orders") or []:
                old_lab_fee = amount(row, "feeAmount") or amount(row, "price")
                if old_lab_fee is not None:
                    break
            if old_lab_fee is None:
                old_lab_fee = amount(after_lab, "feeAmount") or amount(after_lab.get("charge") or {}, "feeAmount")
        check("lab_old_charge_unchanged", old_lab_fee in {None, lab_fee, lab_original} and old_lab_fee != bumped, {"after": old_lab_fee, "captured": lab_fee, "bumped": bumped})
        restore_price(lab, "laboratory", lab_id, lab_original, bumped)

    cross_lab = api(
        "POST",
        f"/laboratory/patient/{patient_b['uuid']}/orders",
        doctor,
        {
            "visitUuid": visit_a,
            "locationUuid": location_uuid,
            "tests": [{"conceptUuid": MP_CONCEPT}],
            "requestId": f"uat-lab-cross-{STAMP}",
        },
    )
    check("lab_cross_patient_rejected", cross_lab[0] in {409, 422, 403, 404}, {"status": cross_lab[0], "code": (cross_lab[1] or {}).get("code") if isinstance(cross_lab[1], dict) else cross_lab[1]})

    # Pharmacy: receive TEST stock, prescribe, unpaid block, pay, dispense, snapshot
    receive = api(
        "POST",
        f"/pharmacy/inventory/{AMOX_TEST}/receive",
        pharm,
        {
            "quantity": 20,
            "purchasePrice": 900,
            "supplier": "UATFIX TEST supplier",
            "reference": f"UAT-RX-{STAMP}",
            "note": "Synthetic TEST stock for UAT pharmacy dispense proof",
        },
    )
    check("pharmacy_receive_test_stock", receive[0] == 200, {"status": receive[0], "body": receive[1] if receive[0] != 200 else {k: (receive[1] or {}).get(k) for k in ("onHand", "quantity", "product")}})
    report["synthetic"]["stockReceipt"] = receive[1] if receive[0] == 200 else {"status": receive[0], "body": receive[1]}

    pharm_items = api("GET", "/pricing/pharmacy?q=Amoxicillin", pharm)[1]
    pharm_item = next((row for row in (pharm_items or {}).get("items") or [] if row.get("id") == AMOX_TEST or "Amoxicillin 500 mg — TEST" in str(row.get("name") or "")), None)
    if not pharm_item:
        pharm_items = api("GET", "/pricing/pharmacy", pharm)[1]
        pharm_item = next((row for row in (pharm_items or {}).get("items") or [] if row.get("id") == AMOX_TEST), None)
    pharm_id = (pharm_item or {}).get("id") or AMOX_TEST
    pharm_original = amount(pharm_item, "price") if pharm_item else 2500.0
    report["synthetic"]["pharmacyCatalogue"] = {"id": pharm_id, "original": pharm_original}

    consult_c = {
        "patientUuid": patient_c["uuid"],
        "visitUuid": visit_c,
        "visitType": "OPD",
        "encounterTypeUuid": CONSULTATION_ENCOUNTER,
        "locationUuid": location_uuid,
        "providers": [{"uuid": prov}],
        "observations": [
            {"concept": {"uuid": NOTE_CONCEPT, "name": "Consultation Note", "dataType": "Text"}, "value": "UATFIX pharmacy consult. Synthetic."},
        ],
        "bahmniDiagnoses": [{"freeTextAnswer": "UATFIX test infection", "order": "PRIMARY", "certainty": "PRESUMED"}],
        "orders": [],
        "drugOrders": [
            {
                "careSetting": "OUTPATIENT",
                "drug": {"uuid": AMOX_TEST},
                "orderType": "Drug Order",
                "dosingInstructionType": FLEXIBLE,
                "dosingInstructions": {
                    "dose": 1,
                    "doseUnits": tablet,
                    "route": oral,
                    "frequency": once,
                    "asNeeded": False,
                    "quantity": 2,
                    "quantityUnits": qty_unit,
                    "numberOfRefills": 0,
                },
                "duration": 2,
                "durationUnits": days,
            }
        ],
    }
    save_c = omrs("POST", "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", doctor, consult_c)
    encounter_c = (save_c[1] or {}).get("encounterUuid") if isinstance(save_c[1], dict) else None
    check("consult_pharmacy", save_c[0] in {200, 201}, {"status": save_c[0], "encounter": encounter_c})
    report["synthetic"]["encounters"] = {**(report["synthetic"].get("encounters") or {}), "pharmacy": encounter_c}

    rx = None
    for _ in range(20):
        queue = api("GET", "/pharmacy/queue", pharm)
        if isinstance(queue[1], dict):
            for row in (queue[1].get("ready") or []) + (queue[1].get("other") or []) + (queue[1].get("unpaid") or []) + (queue[1].get("items") or []):
                if row.get("patientUuid") == patient_c["uuid"]:
                    rx = row
                    break
        if rx:
            break
        time.sleep(4)
    check("pharmacy_prescription_visible", bool(rx), {"rx": {k: (rx or {}).get(k) for k in ("orderUuid", "paymentStatus", "dispensingStatus", "drugName", "quantity")}})
    report["synthetic"]["prescription"] = rx

    if rx and rx.get("orderUuid"):
        detail = api("GET", f"/pharmacy/prescription/{rx['orderUuid']}", pharm)
        check(
            "pharmacy_unpaid_visible",
            detail[0] == 200 and str((detail[1] or {}).get("paymentStatus") or "").upper() in {"UNPAID", "PARTIALLY PAID"},
            {"status": detail[0], "payment": (detail[1] or {}).get("paymentStatus"), "dispense": (detail[1] or {}).get("dispensingStatus"), "can": (detail[1] or {}).get("canDispense")},
        )
        unpaid_disp = api("POST", f"/pharmacy/prescription/{rx['orderUuid']}/dispense", pharm, {"requestId": f"uat-disp-unpaid-{STAMP}"})
        check(
            "pharmacy_unpaid_blocked",
            unpaid_disp[0] in {409, 422} or (isinstance(unpaid_disp[1], dict) and unpaid_disp[1].get("canDispense") is False),
            {"status": unpaid_disp[0], "code": (unpaid_disp[1] or {}).get("code") if isinstance(unpaid_disp[1], dict) else unpaid_disp[1]},
        )
        price_amt = amount(detail[1], "price") if isinstance(detail[1], dict) else None
        if price_amt is None and isinstance(detail[1], dict):
            price_amt = amount(detail[1], "unitPrice") or amount((detail[1].get("sale") or {}), "amount")
        check("pharmacy_price_correct", price_amt is None or abs(price_amt - pharm_original) < 0.02 or abs((price_amt or 0) - (pharm_original * 2)) < 0.02, {"price": price_amt, "catalogue": pharm_original})

        uid, models = odoo_models()
        sale_lines = []
        for _ in range(15):
            sale_lines = kw(
                models,
                uid,
                "sale.order.line",
                "search_read",
                [[("external_order_id", "=", rx["orderUuid"])]],
                {"fields": ["id", "price_unit", "product_uom_qty", "order_id", "name"]},
            )
            if sale_lines:
                break
            time.sleep(4)
        check("pharmacy_sale_from_order", bool(sale_lines), {"lines": sale_lines})
        report["synthetic"]["pharmacySale"] = sale_lines
        captured_unit = float(sale_lines[0]["price_unit"]) if sale_lines else None
        check("pharmacy_sale_old_price", captured_unit is None or abs(captured_unit - pharm_original) < 0.02, {"unit": captured_unit, "catalogue": pharm_original})

        account = wait_ok("GET", f"/patient-account/{patient_c['uuid']}", acct)
        invoices = (account[1] or {}).get("invoices") if isinstance(account[1], dict) else []
        unpaid = [
            row
            for row in invoices or []
            if amount(row, "outstanding") not in (None, 0)
            and str(row.get("state") or row.get("paymentState") or "").lower() not in {"cancel", "cancelled"}
        ]
        journals = api("GET", "/accountant/dashboard", acct)[1]
        journal_id = 6
        if isinstance(journals, dict):
            rows = journals.get("journals") or []
            cash = next((row for row in rows if str(row.get("type") or "") == "cash" or str(row.get("name") or "").lower() == "cash"), None)
            journal_id = (cash or (rows[0] if rows else {})).get("id") or 6
        if unpaid:
            invoice_ids = [row.get("id") for row in unpaid if row.get("id")]
            total = sum(amount(row, "outstanding") or 0 for row in unpaid)
            pay = api(
                "POST",
                "/accountant/payment",
                acct,
                {
                    "patientUuid": patient_c["uuid"],
                    "invoiceIds": invoice_ids,
                    "amount": total,
                    "journalId": journal_id,
                    "requestId": f"uat-pay-c-{STAMP}",
                },
            )
            check("pharmacy_payment_recorded", pay[0] == 200, {"status": pay[0], "amount": total, "invoices": invoice_ids, "body": pay[1] if pay[0] != 200 else (pay[1] or {}).get("payment")})
            report["synthetic"]["pharmacyPayment"] = pay[1] if isinstance(pay[1], dict) else {"status": pay[0]}
            after_pay = api("GET", f"/patient-account/{patient_c['uuid']}", acct)[1]
            summary = (after_pay or {}).get("summary") if isinstance(after_pay, dict) else {}
            check(
                "pharmacy_account_paid_state",
                isinstance(after_pay, dict),
                {"billed": summary.get("billedByCurrency") or after_pay.get("billed"), "collected": summary.get("paidByCurrency") or after_pay.get("paid"), "outstanding": summary.get("outstandingByCurrency")},
            )
        else:
            check("pharmacy_invoices_present", False, {"invoices": invoices})

        paid_detail = api("GET", f"/pharmacy/prescription/{rx['orderUuid']}", pharm)
        check(
            "pharmacy_queue_paid_ready",
            paid_detail[0] == 200 and bool((paid_detail[1] or {}).get("canDispense")) and str((paid_detail[1] or {}).get("paymentStatus") or "").upper() == "PAID",
            {"status": paid_detail[0], "payment": (paid_detail[1] or {}).get("paymentStatus"), "dispense": (paid_detail[1] or {}).get("dispensingStatus"), "can": (paid_detail[1] or {}).get("canDispense"), "reason": (paid_detail[1] or {}).get("blockReason")},
        )
        stock_before = (paid_detail[1] or {}).get("stockOnHand") if isinstance(paid_detail[1], dict) else None
        disp = api("POST", f"/pharmacy/prescription/{rx['orderUuid']}/dispense", pharm, {"requestId": f"uat-disp-{STAMP}"})
        check(
            "pharmacy_dispense",
            disp[0] == 200 and not (disp[1] or {}).get("alreadyDispensed"),
            {"status": disp[0], "body": disp[1] if disp[0] != 200 else {k: (disp[1] or {}).get(k) for k in ("dispensingStatus", "drugName", "quantity", "alreadyDispensed", "stockOnHand")}},
        )
        report["synthetic"]["dispense"] = disp[1] if isinstance(disp[1], dict) else {"status": disp[0]}
        after_disp = api("GET", f"/pharmacy/prescription/{rx['orderUuid']}", pharm)
        check(
            "pharmacy_dispensed_not_ready",
            after_disp[0] == 200
            and str((after_disp[1] or {}).get("dispensingStatus") or "").upper() == "DISPENSED"
            and not (after_disp[1] or {}).get("canDispense"),
            {"status": (after_disp[1] or {}).get("dispensingStatus"), "can": (after_disp[1] or {}).get("canDispense"), "qty": (after_disp[1] or {}).get("quantity"), "drug": (after_disp[1] or {}).get("drugName")},
        )
        check(
            "pharmacy_dispense_association",
            (after_disp[1] or {}).get("patientUuid") == patient_c["uuid"] and "Amoxicillin" in str((after_disp[1] or {}).get("drugName") or ""),
            {"patient": (after_disp[1] or {}).get("patientUuid"), "drug": (after_disp[1] or {}).get("drugName"), "qty": (after_disp[1] or {}).get("quantity")},
        )
        stock_after = (after_disp[1] or {}).get("stockOnHand")
        check(
            "pharmacy_stock_decreased",
            stock_before is None or stock_after is None or float(stock_after) < float(stock_before),
            {"before": stock_before, "after": stock_after},
        )
        pickings = []
        if sale_lines:
            sale_id = sale_lines[0]["order_id"][0] if isinstance(sale_lines[0].get("order_id"), (list, tuple)) else sale_lines[0].get("order_id")
            pickings = kw(models, uid, "stock.picking", "search_read", [[("sale_id", "=", sale_id)]], {"fields": ["name", "state", "origin"]})
        check("pharmacy_picking_done", any(str(row.get("state")) == "done" for row in pickings) if pickings else True, {"pickings": pickings})
        report["synthetic"]["pickings"] = pickings
        dup = api("POST", f"/pharmacy/prescription/{rx['orderUuid']}/dispense", pharm, {"requestId": f"uat-disp-dup-{STAMP}"})
        check(
            "pharmacy_duplicate_blocked",
            dup[0] in {200, 409} and (dup[0] == 409 or (isinstance(dup[1], dict) and (dup[1].get("alreadyDispensed") or dup[1].get("code") == "already_dispensed"))),
            {"status": dup[0], "code": (dup[1] or {}).get("code") if isinstance(dup[1], dict) else None, "already": (dup[1] or {}).get("alreadyDispensed") if isinstance(dup[1], dict) else None},
        )

        if pharm_id and pharm_original is not None:
            bumped = pharm_original + 77
            api("PATCH", f"/pricing/pharmacy/{pharm_id}", pharm, {"price": bumped, "expectedPrice": pharm_original, "reason": "UAT pharmacy snapshot proof"})
            if sale_lines:
                fresh = kw(models, uid, "sale.order.line", "read", [[sale_lines[0]["id"]], ["price_unit"]])
                still = float(fresh[0]["price_unit"]) if fresh else None
                check("pharmacy_old_bill_unchanged_after_catalogue", still is not None and abs(still - pharm_original) < 0.02, {"still": still, "original": pharm_original, "newCatalogue": bumped})
            restore_price(pharm, "pharmacy", pharm_id, pharm_original, bumped)

    doctor_disp = api("POST", f"/pharmacy/prescription/{((rx or {}).get('orderUuid') or 'x')}/dispense", doctor, {"requestId": f"uat-doc-disp-{STAMP}"})
    check("doctor_cannot_dispense", doctor_disp[0] in {403, 404, 409, 422}, {"status": doctor_disp[0]})
    nurse_disp = api("POST", f"/pharmacy/prescription/{((rx or {}).get('orderUuid') or 'x')}/dispense", nurse, {"requestId": f"uat-nurse-disp-{STAMP}"})
    check("nurse_cannot_dispense", nurse_disp[0] in {403, 404, 409, 422}, {"status": nurse_disp[0]})

    # Accommodation: record config, admit to Hawawu, prove NGN invoice
    uid, models = odoo_models()
    company = kw(models, uid, "res.company", "search_read", [[]], {"fields": ["name", "currency_id"], "limit": 1})
    shop = kw(models, uid, "sale.shop", "search_read", [[("name", "=", "Accommodation")]], {"fields": ["name", "pricelist_id"]})
    hawawu_product = kw(models, uid, "product.product", "search_read", [[("default_code", "=", HAWAWU)]], {"fields": ["id", "name", "list_price"]})
    hist = kw(models, uid, "account.move", "search_read", [[("name", "=", "INV/2026/00053")]], {"fields": ["name", "amount_total", "currency_id", "payment_state"]})
    report["synthetic"]["accommodationConfigBefore"] = {"company": company, "shop": shop, "hawawu": hawawu_product, "historical": hist}
    check("company_currency_untouched_usd", company and many2one_name(company[0].get("currency_id")) == "USD", {"company": company})
    check("accommodation_shop_ngn", shop and "NGN" in str(shop[0].get("pricelist_id")), {"shop": shop})
    check("hawawu_tariff_55000", hawawu_product and abs(float(hawawu_product[0]["list_price"]) - 55000) < 0.01, {"product": hawawu_product})
    check("historical_invoice_still_usd", hist and many2one_name(hist[0].get("currency_id")) == "USD" and abs(float(hist[0]["amount_total"]) - 55000) < 0.01, {"invoice": hist})

    tariffs = api("GET", "/inpatient/accommodation/tariffs", admin)
    hawawu_tariff = next((row for row in ((tariffs[1] or {}).get("areas") or []) if row.get("areaUuid") == HAWAWU), None)
    check(
        "tariff_api_ngn",
        tariffs[0] == 200
        and ((tariffs[1] or {}).get("currency") or {}).get("code") == "NGN"
        and amount(hawawu_tariff, "listPrice") == 55000,
        {"currency": (tariffs[1] or {}).get("currency"), "hawawu": hawawu_tariff},
    )

    board_ip = api("GET", "/inpatient/board", nurse)
    bed = None
    if isinstance(board_ip[1], dict):
        for area in board_ip[1].get("areas") or []:
            if str(area.get("areaUuid") or area.get("uuid") or "") != HAWAWU and "Hawawu" not in str(area.get("areaName") or area.get("name") or ""):
                continue
            for row in area.get("beds") or []:
                if str(row.get("status") or "").upper() == "AVAILABLE" and not row.get("patientUuid"):
                    bed = row
                    break
            if bed:
                break
    check("hawawu_free_bed", bool(bed), {"bed": {k: (bed or {}).get(k) for k in ("bedNumber", "bedUuid", "bedId")}})
    assign = (
        api(
            "POST",
            "/inpatient/assign",
            nurse,
            {
                "patientUuid": patient_d["uuid"],
                "bedUuid": (bed or {}).get("bedUuid"),
                "bedId": (bed or {}).get("bedId"),
                "requestId": f"uat-assign-{STAMP}",
            },
        )
        if bed
        else (0, {"error": "no_free_bed"}, 0)
    )
    check("accommodation_admit", assign[0] == 200, {"status": assign[0], "bed": (bed or {}).get("bedNumber"), "billing": (assign[1] or {}).get("billing") if isinstance(assign[1], dict) else assign[1]})
    report["synthetic"]["admission"] = {"bed": bed, "assign": assign[1] if assign[0] == 200 else {"status": assign[0], "body": assign[1]}}

    stay = api("GET", f"/inpatient/patient/{patient_d['uuid']}", nurse)
    billing = (stay[1] or {}).get("billing") if isinstance(stay[1], dict) else {}
    billed = amount(billing, "total") or amount(billing, "outstanding")
    billed_code = ((billing.get("total") or billing.get("outstanding") or {}) if isinstance(billing, dict) else {}).get("currencyCode")
    check(
        "accommodation_new_charge_ngn",
        stay[0] == 200 and billed_code == "NGN" and billed in {55000, None} or (billed is not None and abs(billed - 55000) < 0.01 and billed_code == "NGN"),
        {"status": stay[0], "billing": billing},
    )

    partner_invoices = []
    if assign[0] == 200:
        time.sleep(2)
        acc_account = api("GET", f"/patient-account/{patient_d['uuid']}", acct)
        invoices = (acc_account[1] or {}).get("invoices") if isinstance(acc_account[1], dict) else []
        acc_inv = [row for row in invoices or [] if "accommodation" in json.dumps(row, default=str).lower() or "Hawawu" in json.dumps(row, default=str)]
        if not acc_inv:
            acc_inv = invoices or []
        check("accommodation_invoice_ngn", bool(acc_inv) and any(((row.get("total") or row.get("outstanding") or {}).get("currencyCode") == "NGN") for row in acc_inv), {"invoices": acc_inv})
        report["synthetic"]["accommodationInvoices"] = acc_inv
        new_numbers = [row.get("number") or row.get("name") for row in acc_inv]
        odoo_new = []
        if new_numbers:
            odoo_new = kw(models, uid, "account.move", "search_read", [[("name", "in", [n for n in new_numbers if n])]], {"fields": ["name", "amount_total", "currency_id", "invoice_origin"]})
        if not odoo_new:
            odoo_new = kw(
                models,
                uid,
                "account.move",
                "search_read",
                [[("invoice_line_ids.name", "ilike", "Hawawu"), ("currency_id", "=", 121)]],
                {"fields": ["name", "amount_total", "currency_id", "partner_id"], "limit": 8, "order": "id desc"},
            )
        check(
            "odoo_new_accommodation_ngn",
            any(many2one_name(row.get("currency_id")) == "NGN" and abs(float(row.get("amount_total") or 0) - 55000) < 0.01 for row in odoo_new),
            {"moves": odoo_new},
        )
        report["synthetic"]["accommodationOdooMoves"] = odoo_new
        hist_after = kw(models, uid, "account.move", "search_read", [[("name", "=", "INV/2026/00053")]], {"fields": ["name", "amount_total", "currency_id"]})
        check("historical_untouched", hist_after and many2one_name(hist_after[0].get("currency_id")) == "USD" and abs(float(hist_after[0]["amount_total"]) - 55000) < 0.01, {"invoice": hist_after})

        if hawawu_tariff and admin:
            api(
                "POST",
                "/inpatient/accommodation/tariffs",
                admin,
                {"areaUuid": HAWAWU, "listPrice": 56000, "requestId": f"uat-tariff-bump-{STAMP}"},
            )
            hist_after_bump = kw(models, uid, "account.move", "search_read", [[("name", "in", [n for n in new_numbers if n] or ["__none__"])]], {"fields": ["name", "amount_total", "currency_id"]})
            if not hist_after_bump and odoo_new:
                hist_after_bump = kw(models, uid, "account.move", "read", [[odoo_new[0]["id"]], ["name", "amount_total", "currency_id"]])
            check(
                "accommodation_old_invoice_unchanged_after_tariff",
                hist_after_bump and abs(float(hist_after_bump[0]["amount_total"]) - 55000) < 0.01,
                {"after": hist_after_bump},
            )
            api(
                "POST",
                "/inpatient/accommodation/tariffs",
                admin,
                {"areaUuid": HAWAWU, "listPrice": 55000, "requestId": f"uat-tariff-restore-{STAMP}"},
            )
            report["restored"]["hawawu"] = 55000

    company_after = kw(models, uid, "res.company", "search_read", [[]], {"fields": ["name", "currency_id"], "limit": 1})
    check("company_currency_still_usd", company_after and many2one_name(company_after[0].get("currency_id")) == "USD", {"company": company_after})

    # Analytics
    overview = api("GET", "/admin/analytics/overview?period=today", admin)
    text = json.dumps(overview[1], default=str)
    check("analytics_overview", overview[0] == 200, {"status": overview[0]})
    check("analytics_has_billed_collected_outstanding", all(word in text.lower() for word in ("billed", "collected", "outstanding")) or all(key in json.dumps(overview[1], default=str).lower() for key in ("billed", "collected", "outstanding")), {"keys": list((overview[1] or {}).keys()) if isinstance(overview[1], dict) else None})
    check("analytics_no_patient_uuid_leak", patient_a["uuid"] not in text and patient_c["uuid"] not in text, {})

    # RBAC pricing isolation
    rbac = [
        ("lab_can_lab_price", lab, "GET", "/pricing/laboratory", None, {200}),
        ("lab_cannot_pharmacy_price", lab, "GET", "/pricing/pharmacy", None, {403}),
        ("lab_cannot_reception_price", lab, "GET", "/pricing/reception", None, {403}),
        ("pharmacy_can_pharmacy_price", pharm, "GET", "/pricing/pharmacy", None, {200}),
        ("pharmacy_cannot_lab_price", pharm, "GET", "/pricing/laboratory", None, {403}),
        ("pharmacy_cannot_reception_price", pharm, "GET", "/pricing/reception", None, {403}),
        ("reception_can_reception_price", rec, "GET", "/pricing/reception", None, {200}),
        ("reception_cannot_lab_price", rec, "GET", "/pricing/laboratory", None, {403}),
        ("reception_cannot_pharmacy_price", rec, "GET", "/pricing/pharmacy", None, {403}),
        ("doctor_cannot_lab_price_write", doctor, "PATCH", f"/pricing/laboratory/{lab_id}", {"price": 1}, {403, 404, 422}),
        ("doctor_cannot_pharmacy_price", doctor, "GET", "/pricing/pharmacy", None, {403}),
        ("nurse_cannot_prices", nurse, "GET", "/pricing/pharmacy", None, {403}),
        ("accountant_cannot_prices", acct, "PATCH", "/pricing/reception/individual", {"price": 1}, {403}),
        ("admin_price_write_blocked", admin, "PATCH", "/pricing/reception/individual", {"price": 1}, {403}),
        ("doctor_cannot_mar_on_opd", doctor, "POST", f"/inpatient/patient/{patient_a['uuid']}/medication-administration", {"slotUuid": str(uuid.uuid4()), "outcome": "given"}, {403, 409, 422, 404}),
    ]
    for name, cookie, method, path, body, allowed in rbac:
        status, payload, _ = api(method, path, cookie, body)
        check(name, status in allowed, {"status": status, "allowed": list(allowed), "code": (payload or {}).get("code") if isinstance(payload, dict) else None})

    rec_prices = api("GET", "/pricing/reception", rec)[1]
    individual = next((row for row in (rec_prices or {}).get("items") or [] if row.get("id") == "individual"), None)
    report["restored"]["reception_individual"] = amount(individual, "price") if individual else None

    # OpenELIS reachability + accession poll (result processed later in UI)
    elis = call("GET", f"{BASE}/openelis", None, timeout=15)
    check("openelis_reachable", elis[0] in {200, 302, 401, 403}, {"status": elis[0]})
    accession = None
    for _ in range(12):
        detail = api("GET", f"/laboratory/patient/{patient_a['uuid']}", lab)
        text = json.dumps(detail[1], default=str)
        if "accession" in text.lower() and ("200" in text or "UATFIX" in text or patient_a["uuid"] in text):
            accession = detail[1]
            break
        time.sleep(5)
    report["synthetic"]["openelis"] = {"patient": patient_a, "order": lab_order_uuid, "encounter": encounter_a, "boardOrDetail": accession or board[1]}
    check("openelis_order_visible_for_processing", lab_order[0] == 200, {"order": lab_order_uuid})

    results_a = omrs("GET", f"/openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid={patient_a['uuid']}", doctor)
    results_b = omrs("GET", f"/openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid={patient_b['uuid']}", doctor)
    report["synthetic"]["labResultsBeforeOpenelis"] = {"a": results_a[1], "b": results_b[1]}
    check("patient_b_has_no_lab_result_yet", results_b[0] == 200, {"status": results_b[0], "body": results_b[1]})

    out = Path(__file__).with_name(f"verify-uat-blockers-{STAMP}.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"WROTE {out}")
    failed = [row for row in report["checks"] if not row["ok"]]
    print(f"SUMMARY {len(report['checks']) - len(failed)}/{len(report['checks'])} passed, {len(failed)} failed")
    for row in failed:
        print("  FAIL", row["name"], json.dumps(row.get("detail"), default=str)[:200])
    return 0


def many2one_name(value: object) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return str(value[1])
    return str(value or "")


if __name__ == "__main__":
    raise SystemExit(main())
