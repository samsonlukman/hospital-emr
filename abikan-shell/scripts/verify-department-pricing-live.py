#!/usr/bin/env python3
"""Live development verification for department pricing. Uses TEST data only."""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
CTX = ssl._create_unverified_context()


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


def call(method: str, path: str, cookie: str | None = None, body: dict | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    url = path if path.startswith("http") else f"{API}{path}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60, context=CTX if url.startswith("https") else None) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            parsed: object = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            parsed = raw[:400]
        return error.code, parsed


def amount_of(item: dict) -> float:
    price = item.get("price") or {}
    return float(price.get("amount") or 0)


def main() -> int:
    report: dict[str, object] = {"security": {}, "lifecycle": {}, "created": []}
    users = [
        "reception.abikan",
        "lab.abikan",
        "pharmacy.abikan",
        "doctor.abikan",
        "nurse.abikan",
        "accountant.abikan",
    ]
    cookies: dict[str, str] = {}
    for user in users:
        cookies[user] = login(user)

    status, _ = call("GET", "/pricing/reception")
    report["security"]["unauthenticated"] = status

    rec, lab, pharm, doctor, nurse, acct = (
        cookies["reception.abikan"],
        cookies["lab.abikan"],
        cookies["pharmacy.abikan"],
        cookies["doctor.abikan"],
        cookies["nurse.abikan"],
        cookies["accountant.abikan"],
    )

    report["security"]["reception_read"] = call("GET", "/pricing/reception", rec)[0]
    report["security"]["lab_read"] = call("GET", "/pricing/laboratory", lab)[0]
    report["security"]["pharmacy_read"] = call("GET", "/pricing/pharmacy", pharm)[0]
    report["security"]["accountant_read"] = call("GET", "/pricing/laboratory", acct)[0]
    report["security"]["doctor_lab_write"] = call("PATCH", "/pricing/laboratory/x", doctor, {"price": 1})[0]
    report["security"]["nurse_pharmacy_write"] = call("PATCH", "/pricing/pharmacy/x", nurse, {"price": 1})[0]
    report["security"]["lab_pharmacy_write"] = call("PATCH", "/pricing/pharmacy/x", lab, {"price": 1})[0]
    report["security"]["pharmacy_lab_write"] = call("PATCH", "/pricing/laboratory/x", pharm, {"price": 1})[0]
    report["security"]["reception_lab_write"] = call("PATCH", "/pricing/laboratory/x", rec, {"price": 1})[0]
    report["security"]["accountant_write"] = call("PATCH", "/pricing/reception/individual", acct, {"price": 1})[0]
    report["security"]["doctor_reception_read"] = call("GET", "/pricing/reception", doctor)[0]

    rec_list = call("GET", "/pricing/reception", rec)[1]
    cards = (rec_list or {}).get("items") if isinstance(rec_list, dict) else []
    individual = next((row for row in cards if row.get("id") == "individual"), None)
    if not individual:
        raise RuntimeError("Individual card missing")
    original_card = amount_of(individual)
    first_card = original_card + 17 if original_card else 2117
    second_card = first_card + 20
    st, saved = call(
        "PATCH",
        "/pricing/reception/individual",
        rec,
        {"price": first_card, "expectedPrice": original_card},
    )
    report["reception_change"] = {"status": st, "new": first_card}
    hist = call("GET", "/pricing/reception/individual/history", rec)[1]
    report["reception_history"] = hist

    created = call(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "PRICE",
            "familyName": "TESTONE",
            "gender": "F",
            "birthdate": "1990-01-15",
            "confirmDuplicate": True,
        },
    )
    report["created_patient_1"] = created
    patient_1 = ((created[1] or {}) if isinstance(created[1], dict) else {}).get("uuid")
    meta = call("GET", "/registration/metadata", rec)[1]
    visit_types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in visit_types or [] if row.get("name") == "OPD"), None)
    visit_1 = None
    if patient_1 and opd:
        visit_resp = call(
            "POST",
            f"/registration/patient/{patient_1}/visit",
            rec,
            {"visitTypeUuid": opd["uuid"], "requestId": f"price-test-visit-1-{int(time.time())}"},
        )
        visit_1 = ((visit_resp[1] or {}) if isinstance(visit_resp[1], dict) else {}).get("uuid")
        report["created_visit_1"] = visit_resp[0]
        charge = call(
            "POST",
            f"/registration/patient/{patient_1}/charge",
            rec,
            {"visitUuid": visit_1, "cardType": "individual", "requestId": f"price-test-charge-1-{int(time.time())}"},
        )
        report["charge_1"] = charge
    call("PATCH", "/pricing/reception/individual", rec, {"price": second_card, "expectedPrice": first_card})
    after = call("GET", f"/registration/patient/{patient_1}", rec)[1] if patient_1 else {}
    old_fee = ((after or {}).get("feeAmount") or {}).get("amount") if isinstance(after, dict) else None
    report["lifecycle"]["reception_old_charge_after_change"] = old_fee

    created2 = call(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "PRICE",
            "familyName": "TESTTWO",
            "gender": "M",
            "birthdate": "1988-04-20",
            "confirmDuplicate": True,
        },
    )
    patient_2 = ((created2[1] or {}) if isinstance(created2[1], dict) else {}).get("uuid")
    report["created_patient_2"] = created2[0]
    new_fee = None
    if patient_2 and opd:
        visit_2 = call(
            "POST",
            f"/registration/patient/{patient_2}/visit",
            rec,
            {"visitTypeUuid": opd["uuid"], "requestId": f"price-test-visit-2-{int(time.time())}"},
        )
        visit_2_uuid = ((visit_2[1] or {}) if isinstance(visit_2[1], dict) else {}).get("uuid")
        charge2 = call(
            "POST",
            f"/registration/patient/{patient_2}/charge",
            rec,
            {"visitUuid": visit_2_uuid, "cardType": "individual", "requestId": f"price-test-charge-2-{int(time.time())}"},
        )
        new_fee = (((charge2[1] or {}) if isinstance(charge2[1], dict) else {}).get("feeAmount") or {}).get("amount")
        report["charge_2"] = charge2[0]
    report["lifecycle"]["reception_new_charge"] = new_fee
    call("PATCH", "/pricing/reception/individual", rec, {"price": original_card})

    lab_list = call("GET", "/pricing/laboratory?q=Malarial", lab)[1]
    tests = (lab_list or {}).get("items") if isinstance(lab_list, dict) else []
    test = next((row for row in tests or [] if row.get("editable")), None)
    if test:
        original_lab = amount_of(test)
        first_lab = original_lab + 13 if original_lab else 1513
        st, _ = call(
            "PATCH",
            f"/pricing/laboratory/{test['id']}",
            lab,
            {"price": first_lab, "expectedPrice": original_lab},
        )
        report["lab_change"] = {"status": st, "id": test["id"], "name": test.get("name"), "new": first_lab}
        hist = call("GET", f"/pricing/laboratory/{test['id']}/history", lab)[1]
        report["lab_history"] = bool((hist or {}).get("history")) if isinstance(hist, dict) else hist
        if patient_1 and visit_1:
            consult = call("GET", f"/consultation/patient/{patient_1}?visitUuid={visit_1}", doctor)[1]
            encounter = None
            location = None
            if isinstance(consult, dict):
                encounter = (consult.get("encounter") or {}).get("uuid") or consult.get("encounterUuid")
                location = (consult.get("location") or {}).get("uuid") or consult.get("locationUuid")
            order = call(
                "POST",
                f"/laboratory/patient/{patient_1}/orders",
                doctor,
                {
                    "visitUuid": visit_1,
                    "locationUuid": location or "",
                    "encounterUuid": encounter or "",
                    "tests": [{"conceptUuid": test["id"]}],
                    "requestId": f"price-test-lab-order-{int(time.time())}",
                },
            )
            report["lab_order"] = order[0]
            orders = ((order[1] or {}) if isinstance(order[1], dict) else {}).get("orders") or ((order[1] or {}) if isinstance(order[1], dict) else {}).get("created")
            order_uuid = None
            if isinstance(order[1], dict):
                created_orders = order[1].get("created") or order[1].get("orders") or []
                if created_orders:
                    order_uuid = created_orders[0].get("uuid")
                tests_after = (order[1].get("tests") or [])
                if not order_uuid and tests_after:
                    order_uuid = tests_after[-1].get("orderUuid") or tests_after[-1].get("uuid")
            charge = call(
                "POST",
                f"/laboratory/patient/{patient_1}/charge",
                doctor,
                {"orderUuid": order_uuid, "requestId": f"price-test-lab-charge-{int(time.time())}"} if order_uuid else {"requestId": f"price-test-lab-charge-{int(time.time())}"},
            )
            report["lab_charge"] = charge
            first_lab_fee = None
            if isinstance(charge[1], dict):
                rows = charge[1].get("tests") or []
                match = next((row for row in rows if row.get("orderUuid") == order_uuid or True), None)
                if match:
                    first_lab_fee = (match.get("feeAmount") or {}).get("amount")
            call(
                "PATCH",
                f"/pricing/laboratory/{test['id']}",
                lab,
                {"price": first_lab + 20, "expectedPrice": first_lab},
            )
            after_lab = call("GET", f"/laboratory/patient/{patient_1}", lab)[1]
            old_lab_fee = None
            if isinstance(after_lab, dict):
                for row in after_lab.get("tests") or []:
                    if order_uuid and row.get("orderUuid") == order_uuid:
                        old_lab_fee = (row.get("feeAmount") or {}).get("amount")
                        break
                if old_lab_fee is None and (after_lab.get("tests") or []):
                    old_lab_fee = ((after_lab["tests"][0].get("feeAmount") or {}).get("amount"))
            report["lifecycle"]["lab_first_fee"] = first_lab_fee
            report["lifecycle"]["lab_old_fee_after_change"] = old_lab_fee
        call("PATCH", f"/pricing/laboratory/{test['id']}", lab, {"price": original_lab})

    pharm_list = call("GET", "/pricing/pharmacy", pharm)[1]
    medicines = (pharm_list or {}).get("items") if isinstance(pharm_list, dict) else []
    medicine = next((row for row in medicines or [] if row.get("editable")), None)
    if medicine:
        original_rx = amount_of(medicine)
        st, _ = call(
            "PATCH",
            f"/pricing/pharmacy/{medicine['id']}",
            pharm,
            {"price": original_rx + 5 if original_rx else 105, "expectedPrice": original_rx},
        )
        report["pharmacy_change"] = {"status": st, "name": medicine.get("name")}
        hist = call("GET", f"/pricing/pharmacy/{medicine['id']}/history", pharm)[1]
        report["pharmacy_history"] = bool((hist or {}).get("history")) if isinstance(hist, dict) else hist
        call("PATCH", f"/pricing/pharmacy/{medicine['id']}", pharm, {"price": original_rx})

    json.dump(report, sys.stdout, indent=2, default=str)
    print()
    security_ok = (
        report["security"]["unauthenticated"] == 401
        and report["security"]["reception_read"] == 200
        and report["security"]["lab_read"] == 200
        and report["security"]["pharmacy_read"] == 200
        and report["security"]["accountant_read"] == 200
        and report["security"]["doctor_lab_write"] == 403
        and report["security"]["nurse_pharmacy_write"] == 403
        and report["security"]["lab_pharmacy_write"] == 403
        and report["security"]["pharmacy_lab_write"] == 403
        and report["security"]["reception_lab_write"] == 403
        and report["security"]["accountant_write"] == 403
        and report["security"]["doctor_reception_read"] == 403
    )
    reception_ok = (
        report.get("reception_change", {}).get("status") == 200
        and old_fee == first_card
        and new_fee == second_card
    )
    if not security_ok or not reception_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
