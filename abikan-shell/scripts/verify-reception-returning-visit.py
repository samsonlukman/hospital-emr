#!/usr/bin/env python3
"""Live check: returning Reception patients are not card-gated and cannot duplicate open visits."""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
CTX = ssl._create_unverified_context()
STAMP = int(time.time())
PROTECTED = {"ABC200016", "ABC200021"}
report: dict[str, object] = {"stamp": STAMP, "checks": [], "failures": [], "patients": {}}


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


def call(method: str, url: str, cookie: str | None, body: dict | None = None):
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60, context=CTX) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            payload = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            payload = raw[:400]
        return error.code, payload


def api(method: str, path: str, cookie: str, body: dict | None = None):
    return call(method, f"{BASE}/openmrs/abikan-api{path}", cookie, body)


def omrs(method: str, path: str, cookie: str, body: dict | None = None):
    return call(method, f"{BASE}{path}", cookie, body)


def check(name: str, ok: bool, detail: object = None) -> bool:
    row = {"name": name, "ok": bool(ok), "detail": detail}
    report["checks"].append(row)
    if not ok:
        report["failures"].append(row)
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:320])
    return bool(ok)


def visits_for(cookie: str, patient: str) -> list[dict]:
    status, body = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={patient}"
        "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name),patient:(uuid))&limit=50",
        cookie,
    )
    rows = (body or {}).get("results") if isinstance(body, dict) else []
    return [row for row in rows or [] if isinstance(row, dict)]


def open_visits(rows: list[dict], patient: str) -> list[dict]:
    found = []
    for row in rows:
        if row.get("stopDatetime"):
            continue
        owner = (row.get("patient") or {}).get("uuid") if isinstance(row.get("patient"), dict) else ""
        if owner == patient:
            found.append(row)
    return found


def close_visit(cookie: str, visit_uuid: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    status, body = omrs("POST", f"/openmrs/ws/rest/v1/visit/{visit_uuid}", cookie, {"stopDatetime": now})
    if status not in {200, 201}:
        raise RuntimeError(f"Unable to close visit {visit_uuid}: {status} {body}")


def main() -> int:
    rec = login("reception.abikan")
    doctor = login("doctor.abikan")
    status, meta = api("GET", "/registration/metadata", rec)
    types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in types or [] if str(row.get("name") or "") == "OPD"), None)
    loc = ((opd or {}).get("locations") or [{}])[0].get("uuid") if opd else ""
    check("metadata", status == 200 and bool(opd) and bool(loc), {"status": status, "opd": (opd or {}).get("uuid")})
    if not opd:
        return 1

    status, created = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "UATFIX",
            "familyName": f"RECVISIT{STAMP % 100000}",
            "gender": "F",
            "birthdate": "1994-04-18",
            "confirmDuplicate": True,
        },
    )
    patient = (created or {}).get("uuid") if isinstance(created, dict) else None
    mrn = str((created or {}).get("identifier") or (created or {}).get("display") or "")
    check("register_existing_patient", status == 200 and bool(patient), {"status": status, "uuid": patient, "mrn": mrn})
    if not patient or any(marker in mrn for marker in PROTECTED):
        return 1
    report["patients"]["returning"] = {"uuid": patient, "mrn": mrn}

    before = visits_for(rec, patient)
    status, charge = api("GET", f"/registration/patient/{patient}", rec)
    check(
        "existing_patient_charge_does_not_block_page",
        status == 200 and isinstance(charge, dict) and charge.get("canCreateCharge") is False,
        {"status": status, "canCreate": (charge or {}).get("canCreateCharge"), "visit": (charge or {}).get("visit")},
    )

    status, started = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {
            "visitTypeUuid": opd["uuid"],
            "locationUuid": loc,
            "requestId": f"recv-1-{STAMP}",
        },
    )
    first_uuid = (started or {}).get("uuid") if isinstance(started, dict) else None
    after_first = visits_for(rec, patient)
    check(
        "test1_start_visit_without_card_fee",
        status == 200 and bool(first_uuid) and started.get("created") is True,
        {"status": status, "visit": first_uuid, "created": (started or {}).get("created"), "openmrs": len(after_first)},
    )
    check("test1_openmrs_one_open_visit", len(open_visits(after_first, patient)) == 1, {"open": [row["uuid"] for row in open_visits(after_first, patient)]})

    status, after_charge = api("GET", f"/registration/patient/{patient}", rec)
    # New patient may still be offered a first card. Starting the visit must not require creating it.
    check(
        "test1_visit_exists_even_if_card_not_created",
        status == 200 and ((after_charge or {}).get("visit") or {}).get("uuid") == first_uuid,
        {"canCreate": (after_charge or {}).get("canCreateCharge"), "cardAlready": (after_charge or {}).get("cardAlreadyRegistered")},
    )

    status, again = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {
            "visitTypeUuid": opd["uuid"],
            "locationUuid": loc,
            "requestId": f"recv-2-{STAMP}",
        },
    )
    after_second = visits_for(rec, patient)
    check(
        "test2_duplicate_open_visit_rejected",
        status == 409
        and (again or {}).get("code") == "visit_already_open"
        and (again or {}).get("uuid") == first_uuid
        and len(open_visits(after_second, patient)) == 1,
        {
            "status": status,
            "code": (again or {}).get("code"),
            "message": (again or {}).get("message"),
            "uuid": (again or {}).get("uuid"),
            "openmrsOpen": [row["uuid"] for row in open_visits(after_second, patient)],
        },
    )
    check(
        "test2_no_second_openmrs_visit",
        len(after_second) == len(after_first),
        {"before": len(after_first), "after": len(after_second)},
    )

    close_visit(rec, first_uuid)
    closed_rows = visits_for(rec, patient)
    check("test3_visit_closed", len(open_visits(closed_rows, patient)) == 0, {"open": open_visits(closed_rows, patient)})

    status, third = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {
            "visitTypeUuid": opd["uuid"],
            "locationUuid": loc,
            "requestId": f"recv-3-{STAMP}",
        },
    )
    after_third = visits_for(rec, patient)
    third_uuid = (third or {}).get("uuid") if isinstance(third, dict) else None
    check(
        "test3_new_visit_after_close",
        status == 200 and bool(third_uuid) and third_uuid != first_uuid and (third or {}).get("created") is True,
        {"status": status, "new": third_uuid, "openmrsOpen": [row["uuid"] for row in open_visits(after_third, patient)]},
    )

    if third_uuid:
        close_visit(rec, third_uuid)

    status, doctor_charge = api("GET", f"/registration/patient/{patient}", doctor)
    check("rbac_doctor_cannot_use_reception_charge", status == 403, {"status": status})
    status, doctor_visit = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        doctor,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"recv-doc-{STAMP}"},
    )
    check("rbac_doctor_cannot_start_reception_visit", status == 403, {"status": status})

    status, board = api("GET", "/inpatient/board", login("nurse.abikan"))
    occupied = None
    if isinstance(board, dict):
        for area in board.get("areas") or []:
            for bed in area.get("beds") or []:
                uuid_value = bed.get("patientUuid")
                if uuid_value and bed.get("status") == "OCCUPIED":
                    occupied = {"uuid": uuid_value, "bed": bed.get("bedNumber"), "area": area.get("name")}
                    break
            if occupied:
                break
    check("test4_found_occupied_patient", bool(occupied), occupied)
    if occupied:
        before_ipd = visits_for(rec, occupied["uuid"])
        status, ipd = api(
            "POST",
            f"/registration/patient/{occupied['uuid']}/visit",
            rec,
            {
                "visitTypeUuid": opd["uuid"],
                "locationUuid": loc,
                "requestId": f"recv-ipd-{STAMP}",
            },
        )
        after_ipd = visits_for(rec, occupied["uuid"])
        check(
            "test4_no_unnecessary_opd",
            status == 409
            and (ipd or {}).get("code") in {"admission_in_progress", "visit_already_open"}
            and len(after_ipd) == len(before_ipd),
            {
                "status": status,
                "code": (ipd or {}).get("code"),
                "message": (ipd or {}).get("message"),
                "visit": (ipd or {}).get("uuid"),
                "before": len(before_ipd),
                "after": len(after_ipd),
                "open": [
                    {"uuid": row.get("uuid"), "type": (row.get("visitType") or {}).get("name"), "stop": row.get("stopDatetime")}
                    for row in after_ipd
                ],
            },
        )

    path = os.path.join(os.path.dirname(__file__), f"verify-reception-returning-visit-{STAMP}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("WROTE", path)
    print("FAILURES", len(report["failures"]))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
