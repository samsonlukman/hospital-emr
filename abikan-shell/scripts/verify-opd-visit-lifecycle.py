#!/usr/bin/env python3
"""Live audit: OPD visit lifecycle. Does not add 24-hour expiry."""

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
CONSULT = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
HPI = "1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
NOTE = "d37294c5-5e07-11ef-8f7c-0242ac120002"
IPD_PATIENT = "a1fb4a69-30de-4e64-a813-0406377648f7"
PROTECTED = {"ABC200016", "ABC200021"}
report: dict[str, object] = {"stamp": STAMP, "checks": [], "failures": [], "visit": None, "attendance": None, "scheduler": None}


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
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:400])
    return bool(ok)


def main() -> int:
    rec, _ = login("reception.abikan")
    doctor, session = login("doctor.abikan")
    status, meta = api("GET", "/registration/metadata", rec)
    types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in types or [] if str(row.get("name") or "") == "OPD"), None)
    loc = ((opd or {}).get("locations") or [{}])[0].get("uuid") if opd else ""
    check("metadata", status == 200 and bool(opd) and bool(loc), {"status": status})
    if not opd:
        return 1

    status, tasks = omrs("GET", "/openmrs/ws/rest/v1/taskdefinition?v=custom:(uuid,name,taskClass)&limit=100", rec)
    task_rows = (tasks or {}).get("results") if isinstance(tasks, dict) else []
    report["scheduler"] = [{"name": row.get("name"), "class": row.get("taskClass")} for row in task_rows or []]
    stale = [
        row
        for row in task_rows or []
        if "visit" in str(row.get("name") or "").lower() or "visit" in str(row.get("taskClass") or "").lower()
    ]
    check("no_openmrs_visit_expiry_task", status in {200, 403} and not stale, {"status": status, "visitTasks": stale, "count": len(task_rows or [])})

    status, created = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "UATFIX",
            "familyName": f"OPDLIFE{STAMP % 100000}",
            "gender": "M",
            "birthdate": "1990-02-14",
            "confirmDuplicate": True,
        },
    )
    patient = (created or {}).get("uuid") if isinstance(created, dict) else None
    mrn = str((created or {}).get("identifier") or "")
    check("register_synthetic", status == 200 and bool(patient) and mrn not in PROTECTED, {"uuid": patient, "mrn": mrn})
    if not patient:
        return 1

    status, context = api("GET", f"/registration/patient/{patient}/visit", rec)
    check(
        "create_visit_context_has_no_card",
        status == 200 and "cards" not in (context or {}) and "canCreateCharge" not in (context or {}),
        {"keys": sorted((context or {}).keys()) if isinstance(context, dict) else context},
    )

    status, started = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"life-1-{STAMP}"},
    )
    visit_uuid = (started or {}).get("uuid") if isinstance(started, dict) else None
    check("start_opd", status == 200 and bool(visit_uuid) and started.get("created") is True, {"status": status, "visit": visit_uuid})
    status, visit = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit/{visit_uuid}?v=custom:(uuid,visitType:(name),startDatetime,stopDatetime,patient:(uuid))",
        rec,
    )
    check(
        "openmrs_visit_open",
        status == 200
        and (visit or {}).get("stopDatetime") in (None, "")
        and ((visit or {}).get("visitType") or {}).get("name") == "OPD"
        and ((visit or {}).get("patient") or {}).get("uuid") == patient,
        visit,
    )
    report["visit"] = visit

    status, again = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"life-2-{STAMP}"},
    )
    check(
        "duplicate_blocked",
        status == 409 and (again or {}).get("uuid") == visit_uuid,
        {"status": status, "code": (again or {}).get("code")},
    )

    user = ((session.get("user") or {}).get("uuid"))
    status, providers = omrs("GET", f"/openmrs/ws/rest/v1/provider?user={user}&v=custom:(uuid,display,retired,person:(display))", doctor)
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
                {"concept": {"uuid": HPI, "name": "History of present illness", "dataType": "Text"}, "value": "UATFIX OPD lifecycle. Synthetic."},
                {"concept": {"uuid": NOTE, "name": "Consultation Note", "dataType": "Text"}, "value": "Attended. Visit must stay open."},
            ],
            "bahmniDiagnoses": [],
            "orders": [],
            "drugOrders": [],
        },
    )
    encounter_uuid = (save[1] or {}).get("encounterUuid") if isinstance(save[1], dict) else None
    check("doctor_attended", save[0] in {200, 201} and bool(encounter_uuid), {"status": save[0], "encounter": encounter_uuid})
    status, encounter = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/encounter/{encounter_uuid}?v=custom:(uuid,encounterDatetime,encounterType:(uuid,name),visit:(uuid),patient:(uuid),encounterProviders:(provider:(uuid,display,person:(display))))",
        doctor,
    )
    report["attendance"] = encounter
    check(
        "consultation_on_same_visit",
        status == 200
        and ((encounter or {}).get("encounterType") or {}).get("name") == "Consultation"
        and ((encounter or {}).get("visit") or {}).get("uuid") == visit_uuid
        and ((encounter or {}).get("patient") or {}).get("uuid") == patient,
        encounter,
    )
    status, still = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit/{visit_uuid}?v=custom:(uuid,stopDatetime,visitType:(name))",
        rec,
    )
    check(
        "consultation_does_not_close_visit",
        status == 200 and (still or {}).get("stopDatetime") in (None, ""),
        still,
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    status, closed = omrs("POST", f"/openmrs/ws/rest/v1/visit/{visit_uuid}", rec, {"stopDatetime": now})
    check(
        "manual_rest_close_sets_stop",
        status in {200, 201} and bool((closed or {}).get("stopDatetime")),
        {"status": status, "stop": (closed or {}).get("stopDatetime")},
    )

    status, next_visit = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"life-3-{STAMP}"},
    )
    next_uuid = (next_visit or {}).get("uuid") if isinstance(next_visit, dict) else None
    check(
        "subsequent_create_visit_after_close",
        status == 200 and bool(next_uuid) and next_uuid != visit_uuid and next_visit.get("created") is True,
        {"status": status, "new": next_uuid},
    )
    if next_uuid:
        omrs("POST", f"/openmrs/ws/rest/v1/visit/{next_uuid}", rec, {"stopDatetime": now})

    before = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={IPD_PATIENT}&v=custom:(uuid,stopDatetime,visitType:(name))&limit=20",
        rec,
    )
    ipd_before = [
        row
        for row in ((before[1] or {}).get("results") or [])
        if ((row.get("visitType") or {}).get("name") or "").upper() == "IPD" and not row.get("stopDatetime")
    ]
    status, ipd = api(
        "POST",
        f"/registration/patient/{IPD_PATIENT}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "locationUuid": loc, "requestId": f"life-ipd-{STAMP}"},
    )
    after = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={IPD_PATIENT}&v=custom:(uuid,stopDatetime,visitType:(name))&limit=20",
        rec,
    )
    ipd_after = [
        row
        for row in ((after[1] or {}).get("results") or [])
        if ((row.get("visitType") or {}).get("name") or "").upper() == "IPD" and not row.get("stopDatetime")
    ]
    check(
        "ipd_unaffected",
        status == 409
        and (ipd or {}).get("code") in {"admission_in_progress", "visit_already_open"}
        and [row.get("uuid") for row in ipd_before] == [row.get("uuid") for row in ipd_after],
        {"status": status, "code": (ipd or {}).get("code"), "ipd": [row.get("uuid") for row in ipd_after]},
    )

    path = os.path.join(os.path.dirname(__file__), f"verify-opd-visit-lifecycle-{STAMP}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("WROTE", path)
    print("FAILURES", len(report["failures"]))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
