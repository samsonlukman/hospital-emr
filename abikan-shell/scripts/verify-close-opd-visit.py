#!/usr/bin/env python3
"""Live UAT: Reception Close Visit for a completed OPD visit. IPD stays open."""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
CTX = ssl._create_unverified_context()
STAMP = int(time.time())
CONSULT = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
HPI = "1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
NOTE = "d37294c5-5e07-11ef-8f7c-0242ac120002"
IPD_PATIENT = "a1fb4a69-30de-4e64-a813-0406377648f7"
PROTECTED = {"ABC200016", "ABC200021"}
report: dict[str, object] = {"stamp": STAMP, "checks": [], "failures": []}


def login(user: str) -> tuple[str, dict]:
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
    cookie = "; ".join(f"{c.name}={c.value}" for c in jar)
    return cookie, payload


def call(method: str, url: str, cookie: str, body: dict | None = None):
    headers = {"Accept": "application/json", "Cookie": cookie}
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
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:500])
    return bool(ok)


def main() -> int:
    rec, _ = login("reception.abikan")
    doctor, session = login("doctor.abikan")
    nurse, _ = login("nurse.abikan")
    status, meta = api("GET", "/registration/metadata", rec)
    types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in types or [] if str(row.get("name") or "") == "OPD"), None)
    loc = ((opd or {}).get("locations") or [{}])[0].get("uuid") if opd else ""
    check("metadata", status == 200 and bool(opd) and bool(loc), {"status": status})
    if not opd:
        return 1

    status, gp = omrs(
        "GET",
        "/openmrs/ws/rest/v1/systemsetting?q=emrapi.visitExpireHours&v=custom:(property,value)",
        rec,
    )
    settings = (gp or {}).get("results") if isinstance(gp, dict) else []
    expire = next((row for row in settings or [] if row.get("property") == "emrapi.visitExpireHours"), None)
    expire_value = str((expire or {}).get("value") or "0")
    check(
        "no_24_hour_expiry_setting",
        expire_value in {"", "0", "0.0", "null"} or expire is None,
        {"status": status, "value": expire_value},
    )

    status, created = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "UATFIX",
            "familyName": f"CLOSEOPD{STAMP % 100000}",
            "gender": "F",
            "birthdate": "1992-04-08",
            "confirmDuplicate": True,
        },
    )
    patient = (created or {}).get("uuid") if isinstance(created, dict) else None
    mrn = str((created or {}).get("identifier") or "")
    check("register_synthetic", status == 200 and bool(patient) and mrn not in PROTECTED, {"uuid": patient, "mrn": mrn})
    if not patient:
        return 1

    status, started = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"close-1-{STAMP}"},
    )
    visit_uuid = (started or {}).get("uuid") if isinstance(started, dict) else None
    check("start_opd", status == 200 and bool(visit_uuid) and started.get("created") is True, started)
    report["visit"] = visit_uuid
    report["patient"] = patient
    report["mrn"] = mrn

    user = ((session.get("user") or {}).get("uuid"))
    status, providers = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/provider?user={user}&v=custom:(uuid,display,retired,person:(display))",
        doctor,
    )
    provider = next((row for row in (providers or {}).get("results") or [] if row.get("uuid") and not row.get("retired")), None)
    save = omrs(
        "POST",
        "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
        doctor,
        {
            "patientUuid": patient,
            "visitUuid": visit_uuid,
            "visitType": "OPD",
            "encounterTypeUuid": CONSULT,
            "locationUuid": loc,
            "providers": [{"uuid": (provider or {}).get("uuid")}],
            "observations": [
                {
                    "concept": {"uuid": HPI, "name": "History of present illness", "dataType": "Text"},
                    "value": "UATFIX Close Visit. Synthetic.",
                },
                {
                    "concept": {"uuid": NOTE, "name": "Consultation Note", "dataType": "Text"},
                    "value": "Attended. Close Visit must keep this consultation.",
                },
            ],
            "bahmniDiagnoses": [],
            "orders": [],
            "drugOrders": [],
        },
    )
    encounter_uuid = (save[1] or {}).get("encounterUuid") if isinstance(save[1], dict) else None
    check("doctor_attended", save[0] in {200, 201} and bool(encounter_uuid), {"status": save[0], "encounter": encounter_uuid})

    doctor_close = api("POST", f"/registration/patient/{patient}/visit/{visit_uuid}/close", doctor, {})
    check(
        "doctor_cannot_close",
        doctor_close[0] == 403,
        {"status": doctor_close[0], "code": (doctor_close[1] or {}).get("code") if isinstance(doctor_close[1], dict) else doctor_close[1]},
    )
    nurse_close = api("POST", f"/registration/patient/{patient}/visit/{visit_uuid}/close", nurse, {})
    check(
        "nurse_cannot_close",
        nurse_close[0] == 403,
        {"status": nurse_close[0], "code": (nurse_close[1] or {}).get("code") if isinstance(nurse_close[1], dict) else nurse_close[1]},
    )

    status, closed = api("POST", f"/registration/patient/{patient}/visit/{visit_uuid}/close", rec, {})
    check(
        "reception_closes_opd",
        status == 200
        and (closed or {}).get("uuid") == visit_uuid
        and (closed or {}).get("open") is False
        and bool((closed or {}).get("stopDatetime"))
        and (closed or {}).get("message") == "Visit closed successfully.",
        closed,
    )

    status, visit = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit/{visit_uuid}?v=custom:(uuid,stopDatetime,visitType:(name),encounters:(uuid,encounterType:(name)))",
        rec,
    )
    encounter_ids = [row.get("uuid") for row in ((visit or {}).get("encounters") or [])]
    check(
        "stop_datetime_set_and_consultation_kept",
        status == 200
        and bool((visit or {}).get("stopDatetime"))
        and encounter_uuid in encounter_ids,
        {"stop": (visit or {}).get("stopDatetime"), "encounters": encounter_ids},
    )

    again = api("POST", f"/registration/patient/{patient}/visit/{visit_uuid}/close", rec, {})
    check(
        "already_closed_rejected",
        again[0] == 409 and (again[1] or {}).get("code") == "visit_already_closed",
        again[1],
    )

    status, next_visit = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"close-2-{STAMP}"},
        )
    next_uuid = (next_visit or {}).get("uuid") if isinstance(next_visit, dict) else None
    check(
        "subsequent_create_visit_no_card",
        status == 200 and bool(next_uuid) and next_uuid != visit_uuid and next_visit.get("created") is True,
        {"status": status, "new": next_uuid, "keys": sorted((next_visit or {}).keys()) if isinstance(next_visit, dict) else next_visit},
    )
    if next_uuid:
        api("POST", f"/registration/patient/{patient}/visit/{next_uuid}/close", rec, {})

    status, still = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/encounter/{encounter_uuid}?v=custom:(uuid,visit:(uuid),obs:(uuid,display))",
        rec,
    )
    check(
        "clinical_records_unchanged",
        status == 200
        and ((still or {}).get("visit") or {}).get("uuid") == visit_uuid
        and len((still or {}).get("obs") or []) >= 1,
        still,
    )

    before = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={IPD_PATIENT}&v=custom:(uuid,stopDatetime,visitType:(name))&limit=20",
        rec,
    )
    ipd_open = [
        row
        for row in ((before[1] or {}).get("results") or [])
        if ((row.get("visitType") or {}).get("name") or "").upper() == "IPD" and not row.get("stopDatetime")
    ]
    ipd_uuid = (ipd_open[0] or {}).get("uuid") if ipd_open else None
    if ipd_uuid:
        ipd_close = api("POST", f"/registration/patient/{IPD_PATIENT}/visit/{ipd_uuid}/close", rec, {})
        after = omrs(
            "GET",
            f"/openmrs/ws/rest/v1/visit/{ipd_uuid}?v=custom:(uuid,stopDatetime,visitType:(name))",
            rec,
        )
        check(
            "ipd_cannot_be_closed",
            ipd_close[0] == 409
            and (ipd_close[1] or {}).get("code") == "cannot_close_admission"
            and not (after[1] or {}).get("stopDatetime"),
            {"status": ipd_close[0], "body": ipd_close[1], "after": after[1]},
        )
    else:
        check("ipd_cannot_be_closed", False, {"detail": "No open IPD visit found for synthetic admitted patient"})

    wrong = api("POST", f"/registration/patient/{patient}/visit/{ipd_uuid or visit_uuid}/close", rec, {})
    if ipd_uuid:
        check(
            "patient_isolation_or_ipd_guard",
            wrong[0] == 409,
            wrong[1],
        )

    path = os.path.join(os.path.dirname(__file__), f"verify-close-opd-visit-{STAMP}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("WROTE", path)
    print("FAILURES", len(report["failures"]))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
