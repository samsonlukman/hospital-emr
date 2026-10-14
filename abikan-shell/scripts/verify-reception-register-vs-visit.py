#!/usr/bin/env python3
"""Live check: Register Patient vs Create Visit are separate workflows."""

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
NO_CARD_PATIENT = os.environ.get(
    "ABIKAN_EXISTING_NO_CARD_UUID",
    "b2f5cf0b-77c0-486c-8884-f450b946e025",
)
IPD_PATIENT = os.environ.get(
    "ABIKAN_IPD_PATIENT_UUID",
    "a1fb4a69-30de-4e64-a813-0406377648f7",
)
report: dict[str, object] = {"stamp": STAMP, "checks": [], "failures": [], "patients": {}, "attendance": None}


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
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:360])
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
    check("metadata", status == 200 and bool(opd) and bool(loc), {"status": status})
    if not opd:
        return 1

    status, created = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "UATFIX",
            "familyName": f"REGVISIT{STAMP % 100000}",
            "gender": "F",
            "birthdate": "1995-06-12",
            "confirmDuplicate": True,
        },
    )
    patient = (created or {}).get("uuid") if isinstance(created, dict) else None
    mrn = str((created or {}).get("identifier") or (created or {}).get("display") or "")
    check("a_register_new_patient", status == 200 and bool(patient), {"status": status, "uuid": patient, "mrn": mrn})
    if not patient or any(marker in mrn for marker in PROTECTED):
        return 1
    report["patients"]["new"] = {"uuid": patient, "mrn": mrn}

    status, started = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-1-{STAMP}"},
    )
    first_uuid = (started or {}).get("uuid") if isinstance(started, dict) else None
    check(
        "a_first_visit",
        status == 200 and bool(first_uuid) and started.get("created") is True,
        {"status": status, "visit": first_uuid},
    )
    status, charge = api(
        "POST",
        f"/registration/patient/{patient}/charge",
        rec,
        {"visitUuid": first_uuid, "cardType": "individual", "requestId": f"regv-card-{STAMP}"},
    )
    check(
        "a_card_charge",
        status == 200 and isinstance(charge, dict) and charge.get("hasCharge") is True,
        {
            "status": status,
            "fee": (charge or {}).get("feeName"),
            "amount": ((charge or {}).get("feeAmount") or {}).get("formatted"),
            "hasCharge": (charge or {}).get("hasCharge"),
        },
    )

    status, context = api("GET", f"/registration/patient/{patient}/visit", rec)
    check(
        "visit_context_has_no_card_fields",
        status == 200
        and isinstance(context, dict)
        and "canCreateCharge" not in context
        and "cards" not in context
        and "feeName" not in context,
        {"status": status, "keys": sorted((context or {}).keys()) if isinstance(context, dict) else context},
    )

    status, again = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-2-{STAMP}"},
    )
    after_dup = visits_for(rec, patient)
    check(
        "c_existing_open_visit",
        status == 409
        and (again or {}).get("code") == "visit_already_open"
        and (again or {}).get("uuid") == first_uuid
        and len(open_visits(after_dup, patient)) == 1,
        {"status": status, "code": (again or {}).get("code"), "uuid": (again or {}).get("uuid")},
    )

    close_visit(rec, first_uuid)
    status, second = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-3-{STAMP}"},
    )
    second_uuid = (second or {}).get("uuid") if isinstance(second, dict) else None
    check(
        "d_new_visit_after_close",
        status == 200 and bool(second_uuid) and second_uuid != first_uuid,
        {"status": status, "new": second_uuid},
    )
    if second_uuid:
        close_visit(rec, second_uuid)

    status, no_card_ctx = api("GET", f"/registration/patient/{NO_CARD_PATIENT}/visit", rec)
    no_card_visit = (no_card_ctx or {}).get("visit") if isinstance(no_card_ctx, dict) else None
    if no_card_visit and no_card_visit.get("open") and no_card_visit.get("uuid"):
        close_visit(rec, no_card_visit["uuid"])
    status, no_card_started = api(
        "POST",
        f"/registration/patient/{NO_CARD_PATIENT}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-nocard-{STAMP}"},
    )
    no_card_uuid = (no_card_started or {}).get("uuid") if isinstance(no_card_started, dict) else None
    check(
        "e_existing_patient_without_card_can_start_visit",
        status in {200, 409} and bool(no_card_uuid) and "canCreateCharge" not in (no_card_started or {}),
        {"status": status, "visit": no_card_uuid, "created": (no_card_started or {}).get("created")},
    )
    report["patients"]["noCard"] = {"uuid": NO_CARD_PATIENT, "visit": no_card_uuid}

    before_ipd = visits_for(rec, IPD_PATIENT)
    status, ipd = api(
        "POST",
        f"/registration/patient/{IPD_PATIENT}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-ipd-{STAMP}"},
    )
    after_ipd = visits_for(rec, IPD_PATIENT)
    check(
        "f_inpatient_no_new_opd",
        status == 409
        and (ipd or {}).get("code") in {"admission_in_progress", "visit_already_open"}
        and len(after_ipd) == len(before_ipd),
        {
            "status": status,
            "code": (ipd or {}).get("code"),
            "visit": (ipd or {}).get("uuid"),
            "before": len(before_ipd),
            "after": len(after_ipd),
        },
    )

    status, doctor_ctx = api("GET", f"/registration/patient/{patient}/visit", doctor)
    check("rbac_doctor_cannot_read_visit_context", status == 403, {"status": status})
    status, doctor_visit = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        doctor,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-doc-{STAMP}"},
    )
    check("rbac_doctor_cannot_start_reception_visit", status == 403, {"status": status})

    attend_status, attend_started = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"regv-attend-{STAMP}"},
    )
    attend_visit = (attend_started or {}).get("uuid") if isinstance(attend_started, dict) else None
    if attend_visit:
        status, consult = api("GET", f"/consultation/patient/{patient}?visitUuid={attend_visit}", doctor)
        encounter = (consult or {}).get("encounter") if isinstance(consult, dict) else None
        check(
            "attendance_visit_is_not_consultation",
            status == 200 and (not encounter or not encounter.get("uuid")),
            {"status": status, "visit": attend_visit, "encounter": encounter},
        )
        note_status, note = omrs(
            "GET",
            "/openmrs/ws/rest/v1/encountertype?q=Consultation&v=custom:(uuid,name)",
            doctor,
        )
        types = (note or {}).get("results") if isinstance(note, dict) else []
        consult_type = next((row for row in types or [] if row.get("name") == "Consultation"), None)
        report["attendance"] = {
            "visitUuid": attend_visit,
            "consultationEncounterBeforeSave": encounter,
            "consultationEncounterType": consult_type,
            "note": "A visit is arrival only. Attendance is a Consultation encounter with encounter_provider.",
        }
        check("attendance_consultation_type_exists", note_status == 200 and bool(consult_type), consult_type)

    path = os.path.join(os.path.dirname(__file__), f"verify-reception-register-vs-visit-{STAMP}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("WROTE", path)
    print("FAILURES", len(report["failures"]))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
