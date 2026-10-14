#!/usr/bin/env python3
"""Read-only laboratory end-to-end verification probe. No clinical or financial writes."""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
for candidate in (Path("/app"), ROOT / "server" / "patient-account"):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
import laboratory as labmod  # noqa: E402

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "http://openmrs:8080").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
PATIENT = "f242364e-b70f-4fec-b29e-8ad4fbe147b5"
KNOWN = {
    "ORD-8": "c2421f0b-fa94-4ae8-a493-4f657ab7793d",
    "ORD-9": "a915d836-e429-4443-afc1-5401f16f037c",
    "ORD-10": "07cf32a8-c31b-4d61-906f-30a83785ce96",
}


def login(user: str) -> str:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    auth = "Basic " + base64.b64encode(f"{user}:{PWD}".encode()).decode()
    with opener.open(
        Request(f"{BASE}/openmrs/ws/rest/v1/session", headers={"Authorization": auth}),
        timeout=20,
    ) as response:
        payload = json.loads(response.read().decode())
    if not payload.get("authenticated"):
        raise RuntimeError(f"{user} not authenticated")
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in jar)


def get(url: str, cookie: str | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            parsed: object = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            parsed = raw[:400]
        return error.code, parsed


def main() -> int:
    report: dict[str, object] = {"users": {}, "security": {}}
    cookies: dict[str, str] = {}
    for user in ["doctor.abikan", "lab.abikan", "accountant.abikan", "pharmacy.abikan"]:
        try:
            cookies[user] = login(user)
            report["users"][user] = "ok"
        except Exception as error:  # noqa: BLE001
            report["users"][user] = str(error)

    lab = cookies.get("lab.abikan", "")
    doctor = cookies.get("doctor.abikan", "")
    accountant = cookies.get("accountant.abikan", "")

    if lab:
        status, board = get(f"{API}/laboratory/board", lab)
        rows = (board or {}).get("orders") if isinstance(board, dict) else []
        abc_rows = [row for row in rows or [] if row.get("patientUuid") == PATIENT]
        report["worklist"] = {
            "status": status,
            "total": len(rows or []),
            "abc200016": [
                {
                    key: row.get(key)
                    for key in (
                        "uuid",
                        "orderNumber",
                        "testName",
                        "stage",
                        "laboratoryStatus",
                        "paymentStatus",
                        "visitUuid",
                    )
                }
                for row in abc_rows
            ],
        }
        order_uuid = KNOWN["ORD-8"]
        match = next((row for row in rows or [] if row.get("uuid") == order_uuid), None)
        visit_uuid = (match or {}).get("visitUuid") or ""
        detail_status, detail = get(
            f"{API}/laboratory/order/{order_uuid}?patient={PATIENT}&visit={visit_uuid}",
            lab,
        )
        loaded = detail.get("order") if isinstance(detail, dict) else None
        report["action_open"] = {
            "orderUuid": order_uuid,
            "visitUuid": visit_uuid,
            "status": detail_status,
            "code": detail.get("code") if isinstance(detail, dict) else None,
            "testName": loaded.get("testName") if isinstance(loaded, dict) else None,
            "loadedUuid": loaded.get("uuid") if isinstance(loaded, dict) else None,
        }

    if doctor:
        status, orders = get(
            f"{BASE}/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={PATIENT}"
            "&orderTypeUuid=d3560b17-5e07-11ef-8f7c-0242ac120002",
            doctor,
        )
        rows = orders if isinstance(orders, list) else (orders or {}).get("results") if isinstance(orders, dict) else []
        report["doctor_orders"] = {
            "status": status,
            "count": len(rows or []),
            "known_matches": {
                label: next((row.get("uuid") for row in rows or [] if row.get("uuid") == uuid), None)
                for label, uuid in KNOWN.items()
            },
        }

    report["orders"] = {}
    for label, order_uuid in KNOWN.items():
        status, raw = get(
            f"{BASE}/openmrs/ws/rest/v1/order/{order_uuid}"
            "?v=custom:(uuid,orderNumber,dateActivated,voided,accessionNumber,patient:(uuid),"
            "encounter:(uuid,visit:(uuid)),concept:(uuid,display),orderType:(uuid,display))",
            lab or doctor,
        )
        if isinstance(raw, dict):
            encounter = raw.get("encounter") if isinstance(raw.get("encounter"), dict) else {}
            report["orders"][label] = {
                "status": status,
                "uuid": raw.get("uuid"),
                "orderNumber": raw.get("orderNumber"),
                "test": (raw.get("concept") or {}).get("display"),
                "encounterUuid": encounter.get("uuid"),
                "visitUuid": (encounter.get("visit") or {}).get("uuid"),
                "accessionNumber": raw.get("accessionNumber"),
            }

    report["openelis"] = {}
    for label in KNOWN:
        encounter_uuid = (report["orders"].get(label) or {}).get("encounterUuid")
        if not encounter_uuid:
            continue
        try:
            details = labmod._accession_details(str(encounter_uuid))
            report["openelis"][label] = {
                "encounterUuid": encounter_uuid,
                "testDetails": [
                    {
                        key: item.get(key)
                        for key in ("testUuid", "status", "result", "accessionNumber", "analysisUuid")
                    }
                    for item in (details or [])
                ],
            }
        except Exception as error:  # noqa: BLE001
            report["openelis"][label] = {"error": type(error).__name__, "message": str(error)[:200]}

    if doctor:
        status, payload = get(
            f"{BASE}/openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid={PATIENT}",
            doctor,
        )
        rows = payload.get("results") if isinstance(payload, dict) else []
        non_empty = [
            row
            for row in rows or []
            if str(row.get("result") or "").strip() not in ("", "null", "None", "—")
        ]
        report["results"] = {
            "status": status,
            "count": len(rows or []),
            "non_empty_count": len(non_empty),
            "non_empty": [
                {key: row.get(key) for key in ("orderUuid", "testName", "result", "resultDateTime")}
                for row in non_empty[:5]
            ],
            "all_rows": [
                {key: row.get(key) for key in ("orderUuid", "testName", "result")}
                for row in (rows or [])[:8]
            ],
        }

    if lab:
        status, charge = get(f"{API}/laboratory/patient/{PATIENT}", lab)
        if isinstance(charge, dict):
            report["billing"] = {
                "status": status,
                "tests": [
                    {
                        key: row.get(key)
                        for key in ("orderUuid", "testName", "paymentStatus", "hasCharge")
                    }
                    for row in (charge.get("tests") or [])
                ],
            }

    if accountant:
        status, account = get(f"{API}/patient-account/{PATIENT}", accountant)
        if isinstance(account, dict):
            invoices = account.get("invoices") or []
            report["billing_accountant"] = {
                "status": status,
                "laboratory_invoices": [
                    {
                        key: invoice.get(key)
                        for key in ("name", "reference", "paymentState", "department", "amount")
                    }
                    for invoice in invoices
                    if "lab" in str(invoice.get("department") or invoice.get("journal") or "").lower()
                    or "Laboratory" in str(invoice.get("department") or "")
                ],
            }

    for name, cookie in [
        ("doctor", doctor),
        ("lab", lab),
        ("accountant", accountant),
        ("pharmacy", cookies.get("pharmacy.abikan", "")),
    ]:
        if cookie:
            status, _ = get(f"{API}/laboratory/board", cookie)
            report["security"][f"{name}_laboratory_board"] = status
    if lab:
        status, _ = get(f"{API}/admin/staff", lab)
        report["security"]["lab_admin_staff"] = status

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
