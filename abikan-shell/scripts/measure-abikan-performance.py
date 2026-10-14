#!/usr/bin/env python3
"""Time representative Hospital EMR API and OpenMRS requests on this installation."""

from __future__ import annotations

import argparse
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
    started = time.perf_counter()
    auth = "Basic " + base64.b64encode(f"{user}:{PWD}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}/openmrs/ws/rest/v1/session",
        headers={"Authorization": auth, "Accept": "application/json"},
    )
    with opener.open(req, timeout=60) as response:
        payload = json.loads(response.read().decode())
    elapsed = time.perf_counter() - started
    if not payload.get("authenticated"):
        raise RuntimeError(f"{user} not authenticated")
    cookie = "; ".join(f"{item.name}={item.value}" for item in jar)
    return cookie, elapsed


def timed(method: str, url: str, cookie: str, timeout: int = 120) -> dict:
    headers = {"Accept": "application/json", "Cookie": cookie}
    request = urllib.request.Request(url, headers=headers, method=method)
    started = time.perf_counter()
    status = 0
    size = 0
    error = None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=CTX if url.startswith("https") else None) as response:
            raw = response.read()
            status = response.status
            size = len(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        size = len(raw)
        error = raw[:180].decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    return {
        "ms": round((time.perf_counter() - started) * 1000),
        "status": status,
        "bytes": size,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--patient", default="")
    args = parser.parse_args()
    users = {
        "reception": "reception.abikan",
        "doctor": "doctor.abikan",
        "nurse": "nurse.abikan",
        "lab": "lab.abikan",
        "pharmacy": "pharmacy.abikan",
        "admin": "admin.abikan",
        "accountant": "accountant.abikan",
    }
    cookies: dict[str, str] = {}
    rows: list[dict] = []
    for key, user in users.items():
        try:
            cookie, elapsed = login(user)
            cookies[key] = cookie
            rows.append({"workflow": f"login:{key}", "ms": round(elapsed * 1000), "status": 200, "bytes": 0})
        except Exception as exc:  # noqa: BLE001
            rows.append({"workflow": f"login:{key}", "ms": None, "status": 0, "error": str(exc)})

    patient = args.patient
    if not patient and "doctor" in cookies:
        result = timed(
            "GET",
            f"{BASE}/openmrs/ws/rest/v1/patient?q=TEST&limit=1&v=custom:(uuid,display)",
            cookies["doctor"],
        )
        rows.append({"workflow": "patient_search_openmrs", **result})
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"{BASE}/openmrs/ws/rest/v1/patient?q=TEST&limit=1&v=custom:(uuid,display)",
                    headers={"Accept": "application/json", "Cookie": cookies["doctor"]},
                ),
                timeout=30,
                context=CTX,
            ) as response:
                payload = json.loads(response.read().decode())
            found = (payload.get("results") or [None])[0]
            if found:
                patient = found.get("uuid") or ""
        except Exception:
            pass

    checks = [
        ("home_session", "doctor", f"{BASE}/openmrs/ws/rest/v1/session"),
        ("patient_search", "reception", f"{BASE}/openmrs/ws/rest/v1/patient?q=PRICE&limit=10&v=custom:(uuid,display)"),
        ("registration_metadata", "reception", f"{API}/registration/metadata"),
        ("doctor_todays_patients", "doctor", f"{API}/consultation/todays-patients"),
        ("doctor_my_patients", "doctor", f"{API}/consultation/my-patients"),
        ("laboratory_board", "lab", f"{API}/laboratory/board"),
        ("pharmacy_queue", "pharmacy", f"{API}/pharmacy/queue"),
        ("pharmacy_catalogue", "pharmacy", f"{API}/pharmacy/catalogue"),
        ("inpatient_board", "nurse", f"{API}/inpatient/board"),
        ("admin_analytics", "admin", f"{API}/admin/analytics/overview"),
        ("admin_audit", "admin", f"{API}/admin/audit"),
        ("accountant_dashboard", "accountant", f"{API}/accountant/dashboard"),
        ("pricing_laboratory", "lab", f"{API}/pricing/laboratory"),
        ("pricing_pharmacy", "pharmacy", f"{API}/pricing/pharmacy"),
    ]
    if patient:
        checks.extend(
            [
                ("patient_chart_identity", "doctor", f"{BASE}/openmrs/ws/rest/v1/patient/{patient}?v=custom:(uuid,display,person:(gender,age))"),
                ("consultation", "doctor", f"{API}/consultation/patient/{patient}"),
                ("inpatient_stay", "nurse", f"{API}/inpatient/patient/{patient}"),
                ("inpatient_vitals", "nurse", f"{API}/inpatient/patient/{patient}/vitals"),
                ("inpatient_notes", "nurse", f"{API}/inpatient/patient/{patient}/nursing-notes"),
                ("inpatient_mar", "nurse", f"{API}/inpatient/patient/{patient}/medication-administration"),
                ("laboratory_patient", "lab", f"{API}/laboratory/patient/{patient}"),
                ("patient_account", "accountant", f"{API}/patient-account/{patient}"),
            ]
        )

    for name, role, url in checks:
        cookie = cookies.get(role)
        if not cookie:
            rows.append({"workflow": name, "ms": None, "status": 0, "error": f"no {role} session"})
            continue
        result = timed("GET", url, cookie)
        rows.append({"workflow": name, **result})

    report = {"label": args.label, "patient": patient, "rows": rows}
    json.dump(report, sys.stdout, indent=2)
    print()
    ranked = sorted([row for row in rows if isinstance(row.get("ms"), int)], key=lambda row: row["ms"], reverse=True)
    print("SLOWEST", file=sys.stderr)
    for row in ranked[:12]:
        print(f"  {row['ms']:>7} ms  {row['workflow']}  {row.get('status')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
