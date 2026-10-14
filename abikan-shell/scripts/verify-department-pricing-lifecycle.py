#!/usr/bin/env python3
"""Complete the pricing lifecycle on the already-created TEST patients."""

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
PATIENT_1 = "ef0ccb3c-7298-41bc-81d9-736d6b67ab3b"
PATIENT_2 = None


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


def call(method: str, path: str, cookie: str, body: dict | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json", "Cookie": cookie}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            return error.code, json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            return error.code, raw[:400]


def amount(payload: object, *keys: str) -> float | None:
    if not isinstance(payload, dict):
        return None
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


def wait_charge(path: str, cookie: str, body: dict) -> tuple[int, object]:
    last = (0, None)
    for _ in range(8):
        last = call("POST", path, cookie, body)
        if last[0] == 200:
            return last
        if isinstance(last[1], dict) and last[1].get("code") != "account_not_found":
            return last
        time.sleep(4)
    return last


def main() -> int:
    rec = login("reception.abikan")
    lab = login("lab.abikan")
    doctor = login("doctor.abikan")
    report: dict[str, object] = {}

    rec_list = call("GET", "/pricing/reception", rec)[1]
    individual = next(row for row in rec_list["items"] if row["id"] == "individual")
    original = float(individual["price"]["amount"])
    first = original + 21
    second = first + 22
    call("PATCH", "/pricing/reception/individual", rec, {"price": first, "expectedPrice": original})

    meta = call("GET", "/registration/metadata", rec)[1]
    opd = next(row for row in meta["visitTypes"] if row.get("name") == "OPD")
    locations = meta.get("locations") or meta.get("loginLocations") or []
    location = next((row for row in locations if row.get("name") == "OPD-1"), locations[0] if locations else None)

    patients = []
    for given, family, gender, birth in (
        ("PRICE", "LIFECYCLEA", "F", "1991-02-02"),
        ("PRICE", "LIFECYCLEB", "M", "1987-03-03"),
    ):
        st, body = call(
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
        patients.append(body.get("uuid") if isinstance(body, dict) else None)
        report[f"register_{family}"] = st

    fees = []
    for index, patient in enumerate(patients):
        price = first if index == 0 else second
        if index == 1:
            call("PATCH", "/pricing/reception/individual", rec, {"price": second, "expectedPrice": first})
        visit = call(
            "POST",
            f"/registration/patient/{patient}/visit",
            rec,
            {"visitTypeUuid": opd["uuid"], "requestId": f"price-life-visit-{index}-{int(time.time())}"},
        )
        visit_uuid = visit[1].get("uuid") if isinstance(visit[1], dict) else None
        charge = wait_charge(
            f"/registration/patient/{patient}/charge",
            rec,
            {"visitUuid": visit_uuid, "cardType": "individual", "requestId": f"price-life-charge-{index}-{int(time.time())}"},
        )
        fees.append(amount(charge[1], "feeAmount"))
        report[f"charge_{index}"] = {"status": charge[0], "fee": fees[-1], "visit": visit_uuid}
        if index == 0:
            time.sleep(2)
            after = call("GET", f"/registration/patient/{patient}", rec)[1]
            report["old_fee_before_second_price"] = amount(after, "feeAmount")

    after_change = call("GET", f"/registration/patient/{patients[0]}", rec)[1]
    report["old_fee_after_second_price"] = amount(after_change, "feeAmount")
    report["new_fee"] = fees[1] if len(fees) > 1 else None
    call("PATCH", "/pricing/reception/individual", rec, {"price": original})

    tests = call("GET", "/pricing/laboratory?q=Malarial", lab)[1]["items"]
    test = next(row for row in tests if row.get("editable"))
    original_lab = float(test["price"]["amount"])
    lab_first = original_lab + 11
    call("PATCH", f"/pricing/laboratory/{test['id']}", lab, {"price": lab_first, "expectedPrice": original_lab})

    visit_uuid = report["charge_0"]["visit"]
    location_uuid = (location or {}).get("uuid") if isinstance(location, dict) else ""
    if not location_uuid:
        visit_payload = call("GET", f"/registration/patient/{patients[0]}", rec)[1]
        location_uuid = ((visit_payload or {}).get("visit") or {}).get("locationUuid") or ""
    order = call(
        "POST",
        f"/laboratory/patient/{patients[0]}/orders",
        doctor,
        {
            "visitUuid": visit_uuid,
            "locationUuid": location_uuid,
            "tests": [{"conceptUuid": test["id"]}],
            "requestId": f"price-life-lab-{int(time.time())}",
        },
    )
    report["lab_order"] = {"status": order[0], "body": order[1] if not isinstance(order[1], dict) else {
        "message": order[1].get("message"),
        "chargeError": order[1].get("chargeError"),
        "orders": [
            {"uuid": row.get("uuid"), "fee": (row.get("feeAmount") or {}).get("amount")}
            for row in (order[1].get("orders") or [])
        ],
        "chargeFee": amount((order[1].get("charge") or {}), "feeAmount") if order[1].get("charge") else None,
        "tests": [
            {"orderUuid": row.get("orderUuid") or row.get("uuid"), "fee": (row.get("feeAmount") or {}).get("amount")}
            for row in ((order[1].get("charge") or {}).get("tests") or [])
        ],
    }}
    first_lab_fee = None
    if isinstance(order[1], dict):
        charge = order[1].get("charge") or {}
        first_lab_fee = amount(charge, "feeAmount")
        if first_lab_fee is None:
            for row in charge.get("tests") or []:
                first_lab_fee = amount(row, "feeAmount")
                if first_lab_fee is not None:
                    break
    call("PATCH", f"/pricing/laboratory/{test['id']}", lab, {"price": lab_first + 30})
    after_lab = call("GET", f"/laboratory/patient/{patients[0]}", lab)[1]
    old_lab = None
    if isinstance(after_lab, dict):
        for row in after_lab.get("tests") or []:
            old_lab = amount(row, "feeAmount")
            if old_lab is not None:
                break
    report["lab_first_fee"] = first_lab_fee
    report["lab_old_fee_after_change"] = old_lab
    call("PATCH", f"/pricing/laboratory/{test['id']}", lab, {"price": original_lab})

    json.dump(report, sys.stdout, indent=2, default=str)
    print()
    reception_ok = fees[0] == first and report["old_fee_after_second_price"] == first and fees[1] == second
    lab_ok = first_lab_fee == lab_first and old_lab == lab_first
    return 0 if reception_ok and lab_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
