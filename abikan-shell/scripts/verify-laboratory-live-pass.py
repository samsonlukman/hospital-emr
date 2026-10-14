#!/usr/bin/env python3
"""Live laboratory post-implementation checks: security, catalogue samples, in-house order."""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from script_config import required_environment

ROOT = Path(__file__).resolve().parents[1]
sys_paths = [str(ROOT / "server" / "patient-account")]
if Path("/app/lab_catalogue.py").exists():
    sys_paths.insert(0, "/app")
import sys

for path in sys_paths:
    if path not in sys.path:
        sys.path.insert(0, path)

import lab_catalogue  # noqa: E402

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "http://openmrs:8080").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
ADMIN_USER = required_environment("ABIKAN_ADMIN_USER")
PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
TEST_PATIENT = "f242364e-b70f-4fec-b29e-8ad4fbe147b5"
MP_CONCEPT = "32AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CTX = ssl._create_unverified_context()


def basic(user: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{PASSWORD}".encode()).decode()


def login(user: str) -> str:
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPCookieProcessor(jar),
    )
    req = urllib.request.Request(f"{BASE}/openmrs/ws/rest/v1/session", headers={"Authorization": basic(user)})
    with opener.open(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode())
    if not payload.get("authenticated"):
        raise RuntimeError(f"{user} not authenticated")
    cookies = []
    for cookie in jar:
        cookies.append(f"{cookie.name}={cookie.value}")
    return "; ".join(cookies)


def call(path: str, cookie: str | None = None, method="GET", body=None, timeout=25, origin: str | None = None):
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    root = origin or (API if path.startswith("/openmrs/abikan-api") else BASE)
    req = urllib.request.Request(f"{root}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            parsed = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            parsed = raw[:300]
        return error.code, parsed
    except (urllib.error.URLError, TimeoutError) as error:
        return 0, str(error)


def admin_get(path: str):
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": basic(ADMIN_USER), "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    report: dict = {"users": {}, "security": {}, "clinical": {}, "order": {}}

    for user in [
        "doctor.abikan",
        "lab.abikan",
        "accountant.abikan",
        "pharmacy.abikan",
        "nurse.abikan",
        "reception.abikan",
        "admin.abikan",
    ]:
        try:
            cookie = login(user)
            status, session = call("/openmrs/ws/rest/v1/session", cookie)
            report["users"][user] = {
                "ok": True,
                "authenticated": bool(isinstance(session, dict) and session.get("authenticated")),
                "privileges": sorted(
                    [
                        p.get("name") if isinstance(p, dict) else str(p)
                        for p in ((session or {}).get("user") or {}).get("privileges") or []
                    ]
                )[:20],
            }
        except Exception as error:  # noqa: BLE001
            report["users"][user] = {"ok": False, "error": str(error)}

    report["security"]["unauth_catalogue"] = call("/openmrs/abikan-api/laboratory/catalogue")[0]
    report["security"]["unauth_board"] = call("/openmrs/abikan-api/laboratory/board")[0]
    report["security"]["unauth_payment"] = call("/openmrs/abikan-api/accountant/payment", method="POST", body={})[0]

    doctor = login("doctor.abikan") if report["users"].get("doctor.abikan", {}).get("ok") else ""
    lab = login("lab.abikan") if report["users"].get("lab.abikan", {}).get("ok") else ""
    accountant = login("accountant.abikan") if report["users"].get("accountant.abikan", {}).get("ok") else ""
    pharmacy = login("pharmacy.abikan") if report["users"].get("pharmacy.abikan", {}).get("ok") else ""
    nurse = login("nurse.abikan") if report["users"].get("nurse.abikan", {}).get("ok") else ""
    reception = login("reception.abikan") if report["users"].get("reception.abikan", {}).get("ok") else ""
    admin = login("admin.abikan") if report["users"].get("admin.abikan", {}).get("ok") else ""

    def code(user_cookie, path, method="GET", body=None):
        return call(path, user_cookie, method=method, body=body)[0]

    report["security"]["doctor_catalogue"] = code(doctor, "/openmrs/abikan-api/laboratory/catalogue")
    report["security"]["doctor_board"] = code(doctor, "/openmrs/abikan-api/laboratory/board")
    report["security"]["doctor_payment"] = code(
        doctor, "/openmrs/abikan-api/accountant/payment", "POST", {"invoiceId": 1, "amount": 1}
    )
    report["security"]["lab_board"] = code(lab, "/openmrs/abikan-api/laboratory/board")
    report["security"]["lab_catalogue"] = code(lab, "/openmrs/abikan-api/laboratory/catalogue")
    report["security"]["lab_payment"] = code(
        lab, "/openmrs/abikan-api/accountant/payment", "POST", {"invoiceId": 1, "amount": 1}
    )
    report["security"]["lab_create_order"] = code(
        lab,
        f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}/orders",
        "POST",
        {"visitUuid": "x", "locationUuid": "x", "tests": [{"conceptUuid": MP_CONCEPT}]},
    )
    report["security"]["accountant_catalogue"] = code(accountant, "/openmrs/abikan-api/laboratory/catalogue")
    report["security"]["accountant_create_order"] = code(
        accountant,
        f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}/orders",
        "POST",
        {"visitUuid": "x", "locationUuid": "x", "tests": [{"conceptUuid": MP_CONCEPT}]},
    )
    report["security"]["accountant_account"] = code(
        accountant, f"/openmrs/abikan-api/patient-account/{TEST_PATIENT}"
    )
    report["security"]["pharmacy_board"] = code(pharmacy, "/openmrs/abikan-api/laboratory/board")
    report["security"]["pharmacy_create_order"] = code(
        pharmacy,
        f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}/orders",
        "POST",
        {"visitUuid": "x", "locationUuid": "x", "tests": [{"conceptUuid": MP_CONCEPT}]},
    )
    report["security"]["nurse_board"] = code(nurse, "/openmrs/abikan-api/laboratory/board")
    report["security"]["nurse_create_order"] = code(
        nurse,
        f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}/orders",
        "POST",
        {"visitUuid": "x", "locationUuid": "x", "tests": [{"conceptUuid": MP_CONCEPT}]},
    )
    report["security"]["nurse_payment"] = code(
        nurse, "/openmrs/abikan-api/accountant/payment", "POST", {"invoiceId": 1, "amount": 1}
    )
    report["security"]["reception_board"] = code(reception, "/openmrs/abikan-api/laboratory/board")
    report["security"]["reception_create_order"] = code(
        reception,
        f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}/orders",
        "POST",
        {"visitUuid": "x", "locationUuid": "x", "tests": [{"conceptUuid": MP_CONCEPT}]},
    )
    report["security"]["admin_board"] = code(admin, "/openmrs/abikan-api/laboratory/board")

    cat_status, catalogue = call("/openmrs/abikan-api/laboratory/catalogue?q=FBC", doctor)
    tests = (catalogue or {}).get("tests") if isinstance(catalogue, dict) else []
    report["clinical"]["catalogue_status"] = cat_status
    report["clinical"]["fbc_search"] = [
        {
            "name": t.get("name"),
            "price": (t.get("price") or {}).get("formatted"),
            "code": (t.get("price") or {}).get("currencyCode"),
            "outsourced": t.get("outsourced"),
            "conceptUuid": t.get("conceptUuid"),
        }
        for t in tests[:8]
    ]
    mp_status, mp_cat = call("/openmrs/abikan-api/laboratory/catalogue?q=Microscopy", doctor)
    report["clinical"]["microscopy_search"] = [
        {
            "name": t.get("name"),
            "price": (t.get("price") or {}).get("formatted"),
            "code": (t.get("price") or {}).get("currencyCode"),
            "outsourced": t.get("outsourced"),
            "conceptUuid": t.get("conceptUuid"),
        }
        for t in ((mp_cat or {}).get("tests") if isinstance(mp_cat, dict) else [])[:8]
    ]
    tox_status, tox_cat = call("/openmrs/abikan-api/laboratory/catalogue?q=Toxicology", doctor)
    report["clinical"]["tox_search"] = [
        {
            "name": t.get("name"),
            "price": (t.get("price") or {}).get("formatted"),
            "outsourced": t.get("outsourced"),
        }
        for t in ((tox_cat or {}).get("tests") if isinstance(tox_cat, dict) else [])[:5]
    ]

    visits = admin_get(
        f"/openmrs/ws/rest/v1/visit?patient={TEST_PATIENT}&v=custom:(uuid,startDatetime,stopDatetime,location:(uuid,display),encounters:(uuid,encounterType:(name)))&limit=10"
    )
    open_visits = [
        v
        for v in (visits.get("results") or [])
        if not v.get("stopDatetime")
    ]
    report["clinical"]["open_visits"] = [
        {
            "uuid": v.get("uuid"),
            "location": (v.get("location") or {}).get("uuid"),
            "encounters": [
                {"uuid": e.get("uuid"), "type": (e.get("encounterType") or {}).get("name")}
                for e in (v.get("encounters") or [])
            ],
        }
        for v in open_visits
    ]

    visit = open_visits[0] if open_visits else None
    if visit and doctor:
        consult = next(
            (
                e
                for e in (visit.get("encounters") or [])
                if (e.get("encounterType") or {}).get("name") == "Consultation"
            ),
            None,
        )
        create_body = {
            "visitUuid": visit["uuid"],
            "locationUuid": (visit.get("location") or {}).get("uuid"),
            "encounterUuid": (consult or {}).get("uuid") or "",
            "requestId": f"lab-verify-mp-{int(time.time())}",
            "tests": [{"conceptUuid": MP_CONCEPT, "name": "Microscopy MP"}],
        }
        status, created = call(
            f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}/orders",
            doctor,
            method="POST",
            body=create_body,
        )
        report["order"]["create_status"] = status
        report["order"]["create"] = created
        report["order"]["visitUuid"] = visit["uuid"]
        report["order"]["encounterUuid"] = (consult or {}).get("uuid")

    fee_status, fee = call(f"/openmrs/abikan-api/laboratory/patient/{TEST_PATIENT}", lab)
    report["clinical"]["lab_fee_status"] = fee_status
    if isinstance(fee, dict):
        report["clinical"]["lab_fee"] = {
            "paymentStatus": fee.get("paymentStatus"),
            "canCreateCharge": fee.get("canCreateCharge"),
            "tests": [
                {
                    "name": t.get("testName"),
                    "orderNumber": t.get("orderNumber"),
                    "amount": (t.get("feeAmount") or {}).get("formatted"),
                    "paymentStatus": t.get("paymentStatus"),
                    "outsourced": t.get("outsourced"),
                }
                for t in (fee.get("tests") or [])[-6:]
            ],
        }

    board_status, board = call("/openmrs/abikan-api/laboratory/board", lab)
    report["clinical"]["lab_board_status"] = board_status
    if isinstance(board, dict):
        report["clinical"]["lab_board_counts"] = {
            k: len(board.get(k) or [])
            for k in ("pending", "processing", "completed", "orders")
            if k in board or True
        }
        report["clinical"]["lab_board_keys"] = sorted(board.keys())
        rows = board.get("orders") or board.get("pending") or []
        report["clinical"]["lab_board_sample"] = [
            {
                "orderNumber": r.get("orderNumber"),
                "testName": r.get("testName"),
                "paymentStatus": r.get("paymentStatus"),
                "outsourced": r.get("outsourced"),
                "stage": r.get("stage"),
            }
            for r in rows[:8]
        ]

    acct_status, account = call(f"/openmrs/abikan-api/patient-account/{TEST_PATIENT}", accountant)
    report["clinical"]["accountant_status"] = acct_status
    if isinstance(account, dict):
        invoices = account.get("invoices") or []
        report["clinical"]["accountant_invoices"] = [
            {
                "name": i.get("name") or i.get("reference"),
                "amount": i.get("amount") or i.get("total"),
                "state": i.get("paymentState") or i.get("paymentStateLabel") or i.get("state"),
                "department": i.get("department") or i.get("journal"),
            }
            for i in invoices[-6:]
        ]

    # Drug vs Test class collisions
    collisions = []
    runtime = lab_catalogue.load_runtime()
    for sn, name in [("42", "Inorganic Phosphate"), ("56", "Testosterone"), ("57", "Progesterone"), ("58", "Estradiol")]:
        uuid = runtime.get(sn)
        concept = admin_get(
            f"/openmrs/ws/rest/v1/concept/{uuid}?v=custom:(uuid,display,conceptClass:(display),datatype:(display))"
        )
        search = admin_get(
            f"/openmrs/ws/rest/v1/concept?q={urllib.request.quote(name)}&v=custom:(uuid,display,conceptClass:(display),datatype:(display))&limit=15"
        )
        collisions.append(
            {
                "sn": sn,
                "bound": concept,
                "search": [
                    {
                        "uuid": r.get("uuid"),
                        "display": r.get("display"),
                        "class": (r.get("conceptClass") or {}).get("display"),
                    }
                    for r in (search.get("results") or [])
                ],
            }
        )
    report["collisions"] = collisions

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
