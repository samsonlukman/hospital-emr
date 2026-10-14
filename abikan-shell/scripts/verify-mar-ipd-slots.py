#!/usr/bin/env python3
"""Live verification: new IPD prescription creates Bahmni MAR slots."""

from __future__ import annotations

import base64
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "patient-account"))

BASE = "https://localhost"
API = "http://127.0.0.1:8787"
PWD = "Admin123"
CTX = ssl._create_unverified_context()
STAMP = int(time.time())
CONSULTATION_ENCOUNTER = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
CETIRIZINE = "7e0766e1-b679-4eb3-ab93-d63910ad6eb4"
FLEXIBLE = "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions"
E2E = "f242364e-b70f-4fec-b29e-8ad4fbe147b5"

report: dict = {"synthetic": {}, "checks": []}


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
    with opener.open(req, timeout=30) as resp:
        json.loads(resp.read().decode())
    return "; ".join(f"{c.name}={c.value}" for c in jar)


def call(method: str, url: str, cookie: str | None, body=None, timeout: int = 90):
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=CTX if url.startswith("https") else None
        ) as resp:
            elapsed = round((time.perf_counter() - started) * 1000)
            return resp.status, json.loads(resp.read().decode() or "null"), elapsed
    except urllib.error.HTTPError as exc:
        elapsed = round((time.perf_counter() - started) * 1000)
        raw = exc.read().decode() or "null"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:800]}
        return exc.code, payload, elapsed


def api(method, path, cookie, body=None, timeout=90):
    return call(method, API + path, cookie, body, timeout)


def omrs(method, path, cookie, body=None, timeout=60):
    return call(method, BASE + path, cookie, body, timeout)


def check(name: str, ok: bool, detail=None) -> None:
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:500])


def provider_uuid(cookie: str) -> str:
    status, session, _ = omrs("GET", "/openmrs/ws/rest/v1/session", cookie)
    user = ((session or {}).get("user") or {}).get("uuid") if status == 200 else ""
    status, body, _ = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/provider?user={user}&v=custom:(uuid,retired)",
        cookie,
    )
    for row in (body or {}).get("results") or []:
        if row.get("uuid") and not row.get("retired"):
            return str(row["uuid"])
    return ""


def register(rec: str, given: str, family: str) -> str:
    status, body, _ = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": given,
            "familyName": family,
            "gender": "F",
            "birthdate": "1992-03-12",
            "confirmDuplicate": True,
        },
    )
    uuid_value = body.get("uuid") if isinstance(body, dict) else None
    check(f"register_{family}", status == 200 and bool(uuid_value), {"status": status, "uuid": uuid_value})
    return str(uuid_value or "")


def start_opd(rec: str, patient: str, visit_type: str) -> str:
    status, body, _ = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": visit_type, "requestId": f"marfix-visit-{STAMP}-{patient[:8]}"},
    )
    uuid_value = body.get("uuid") if isinstance(body, dict) else None
    check("start_opd", status == 200 and bool(uuid_value), {"status": status, "uuid": uuid_value})
    return str(uuid_value or "")


def admit_and_assign(doctor: str, nurse: str, patient: str, visit: str, location: str) -> dict:
    admit = api(
        "POST",
        f"/inpatient/patient/{patient}/admit-decision",
        doctor,
        {"visitUuid": visit, "locationUuid": location, "requestId": f"marfix-admit-{STAMP}-{patient[:8]}"},
    )
    check("admit", admit[0] == 200, {"status": admit[0], "message": (admit[1] or {}).get("message")})
    board = api("GET", "/inpatient/board", nurse)
    bed = None
    if isinstance(board[1], dict):
        for area in board[1].get("areas") or []:
            for row in area.get("beds") or []:
                if row.get("status") == "AVAILABLE" and not row.get("patientUuid"):
                    bed = row
                    break
            if bed:
                break
    assign = (
        api(
            "POST",
            "/inpatient/assign",
            nurse,
            {
                "patientUuid": patient,
                "bedUuid": (bed or {}).get("bedUuid"),
                "bedId": (bed or {}).get("bedId"),
                "requestId": f"marfix-assign-{STAMP}-{patient[:8]}",
            },
        )
        if bed
        else (0, {"error": "no_free_bed"}, 0)
    )
    check("assign_bed", assign[0] == 200, {"status": assign[0], "bed": (bed or {}).get("bedNumber")})
    return bed or {}


def active_ipd_visit(cookie: str, patient: str) -> str:
    status, body, _ = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={patient}&includeInactive=false&v=custom:(uuid,stopDatetime,visitType:(name))",
        cookie,
    )
    for row in (body or {}).get("results") or []:
        visit_type = (row.get("visitType") or {}).get("name")
        if not row.get("stopDatetime") and str(visit_type or "").upper() == "IPD":
            return str(row.get("uuid") or "")
    return ""


def config_names(doctor: str) -> dict[str, str]:
    status, cfg, _ = omrs("GET", "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders", doctor)
    check("drug_order_config", status == 200, {"status": status})
    def first(key: str, *preferred: str) -> str:
        rows = (cfg or {}).get(key) or []
        names = [str(row.get("name") or "") for row in rows if row.get("name")]
        for name in preferred:
            if name in names:
                return name
        return names[0] if names else ""
    return {
        "tablet": first("doseUnits", "Tablet", "Tablet(s)"),
        "oral": first("routes", "Oral"),
        "once": first("frequencies", "Once a day"),
        "days": first("durationUnits", "Day(s)", "Days", "Day"),
        "qty": first("dispensingUnits", "Tablet", "Tablet(s)") or first("doseUnits", "Tablet"),
    }


def prescribe(doctor: str, patient: str, visit: str, location: str, provider: str, names: dict, quantity: int, duration: int):
    started = time.perf_counter()
    status, body, elapsed = omrs(
        "POST",
        "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
        doctor,
        {
            "patientUuid": patient,
            "visitUuid": visit,
            "visitType": "IPD",
            "encounterTypeUuid": CONSULTATION_ENCOUNTER,
            "locationUuid": location,
            "providers": [{"uuid": provider}],
            "observations": [],
            "bahmniDiagnoses": [],
            "orders": [],
            "drugOrders": [
                {
                    "careSetting": "INPATIENT",
                    "drug": {"uuid": CETIRIZINE},
                    "orderType": "Drug Order",
                    "dosingInstructionType": FLEXIBLE,
                    "dosingInstructions": {
                        "dose": 1,
                        "doseUnits": names["tablet"],
                        "route": names["oral"],
                        "frequency": names["once"],
                        "asNeeded": False,
                        "quantity": quantity,
                        "quantityUnits": names["qty"],
                        "numberOfRefills": 0,
                    },
                    "duration": duration,
                    "durationUnits": names["days"],
                }
            ],
        },
    )
    return status, body, elapsed, round((time.perf_counter() - started) * 1000)


def latest_ipd_order(cookie: str, patient: str) -> dict:
    status, body, _ = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive?patientUuid={patient}",
        cookie,
    )
    rows = []
    if isinstance(body, dict):
        rows = body.get("visitDrugOrders") or body.get("results") or []
    elif isinstance(body, list):
        rows = body
    orders = []
    for row in rows:
        nested = row.get("drugOrder") if isinstance(row, dict) else None
        item = {**(nested or {}), **row} if isinstance(row, dict) else {}
        if item.get("uuid"):
            orders.append(item)
    return orders[0] if orders else {}


def slots_from(mar_body) -> list[dict]:
    slots = []
    for order in (mar_body or {}).get("orders") or []:
        for slot in order.get("slots") or []:
            slots.append({**slot, "orderUuid": order.get("orderUuid"), "medication": order.get("medication")})
    return slots


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

    rec, doctor, nurse = users["reception.abikan"], users["doctor.abikan"], users["nurse.abikan"]
    meta_status, meta, _ = api("GET", "/registration/metadata", rec)
    visit_types = (meta or {}).get("visitTypes") or []
    opd = next((row for row in visit_types if row.get("name") == "OPD"), None)
    locations = (meta or {}).get("locations") or (meta or {}).get("loginLocations") or []
    location = next((row for row in locations if row.get("name") == "OPD-1"), locations[0] if locations else {})
    location_uuid = (location or {}).get("uuid") or ""
    opd_uuid = (opd or {}).get("uuid") or ""
    check("metadata", bool(opd_uuid and location_uuid), {"status": meta_status})

    names = config_names(doctor)
    provider = provider_uuid(doctor)
    check("doctor_provider", bool(provider), {"provider": provider, "names": names})

    patient_a = register(rec, "MARFIX", f"ALPHA{STAMP % 100000}")
    patient_b = register(rec, "MARFIX", f"BRAVO{STAMP % 100000}")
    report["synthetic"]["patients"] = {"a": patient_a, "b": patient_b}
    visit_a = start_opd(rec, patient_a, opd_uuid)
    visit_b = start_opd(rec, patient_b, opd_uuid)
    bed_a = admit_and_assign(doctor, nurse, patient_a, visit_a, location_uuid)
    bed_b = admit_and_assign(doctor, nurse, patient_b, visit_b, location_uuid)
    ipd_a = active_ipd_visit(doctor, patient_a)
    ipd_b = active_ipd_visit(doctor, patient_b)
    check("ipd_visits", bool(ipd_a and ipd_b), {"a": ipd_a, "b": ipd_b})
    report["synthetic"]["visits"] = {"a": ipd_a, "b": ipd_b, "beds": {"a": bed_a, "b": bed_b}}

    order_status, order_body, order_ms, _ = prescribe(doctor, patient_a, ipd_a, location_uuid, provider, names, 3, 3)
    check("ipd_order_a", order_status == 200, {"status": order_status, "ms": order_ms})
    schedule_started = time.perf_counter()
    sched_status, sched, sched_ms = api("POST", f"/inpatient/patient/{patient_a}/medication-schedule", doctor, {})
    slot_ms = round((time.perf_counter() - schedule_started) * 1000)
    check(
        "schedule_a",
        sched_status == 200 and bool((sched or {}).get("createdOrderUuids") or (sched or {}).get("alreadyScheduledOrderUuids")),
        {"status": sched_status, "body": sched, "ms": sched_ms},
    )
    retry_status, retry, _ = api("POST", f"/inpatient/patient/{patient_a}/medication-schedule", doctor, {})
    check(
        "schedule_retry_no_duplicate",
        retry_status == 200
        and not (retry or {}).get("createdOrderUuids")
        and (retry or {}).get("alreadyScheduledOrderUuids"),
        {"status": retry_status, "body": retry},
    )

    mar_status, mar_a, _ = api("GET", f"/inpatient/patient/{patient_a}/medication-administration", nurse)
    slots_a = slots_from(mar_a)
    check("mar_slots_a", mar_status == 200 and len(slots_a) == 3, {"status": mar_status, "slots": len(slots_a), "orders": (mar_a or {}).get("orders")})
    report["performance"] = {
        "orderCreationMs": order_ms,
        "scheduleCreationMs": sched_ms,
        "slotAvailabilityMs": slot_ms,
        "asynchronous": False,
    }
    report["workflow"] = {
        "order": latest_ipd_order(doctor, patient_a),
        "schedule": sched,
        "mar": mar_a,
    }

    if slots_a:
        first, second = slots_a[0], slots_a[1] if len(slots_a) > 1 else None
        eligible = api(
            "POST",
            f"/inpatient/patient/{patient_a}/medication-administration",
            nurse,
            {"slotUuid": first["uuid"], "outcome": "given", "reason": ""},
        )
        check("eligible_200", eligible[0] == 200, {"status": eligible[0], "slot": eligible[1]})
        given = ((eligible[1] or {}).get("slot") or {})
        admin = given.get("administration") or {}
        check(
            "server_actual_time",
            bool(admin.get("actualTime")) and admin.get("scheduledTime") == first.get("scheduledTime"),
            {"scheduled": first.get("scheduledTime"), "actual": admin.get("actualTime")},
        )
        if second:
            future = api(
                "POST",
                f"/inpatient/patient/{patient_a}/medication-administration",
                nurse,
                {"slotUuid": second["uuid"], "outcome": "given", "reason": ""},
            )
            check(
                "future_409",
                future[0] == 409 and (future[1] or {}).get("code") == "outside_administration_window",
                {"status": future[0], "code": (future[1] or {}).get("code")},
            )
            no_reason = api(
                "POST",
                f"/inpatient/patient/{patient_a}/medication-administration",
                nurse,
                {"slotUuid": second["uuid"], "outcome": "given", "reason": "", "outsideWindow": True},
            )
            check(
                "outside_window_reason_required",
                no_reason[0] == 422 and (no_reason[1] or {}).get("code") == "outside_window_reason_required",
                {"status": no_reason[0], "code": (no_reason[1] or {}).get("code")},
            )
            client_time = api(
                "POST",
                f"/inpatient/patient/{patient_a}/medication-administration",
                nurse,
                {"slotUuid": second["uuid"], "outcome": "given", "reason": "x", "administeredDateTime": 1},
            )
            check(
                "server_fields_only",
                client_time[0] == 422 and (client_time[1] or {}).get("code") == "server_fields_only",
                {"status": client_time[0], "code": (client_time[1] or {}).get("code")},
            )
            not_required = api(
                "POST",
                f"/inpatient/patient/{patient_a}/medication-administration",
                nurse,
                {"slotUuid": first["uuid"], "outcome": "given", "reason": "late", "outsideWindow": True},
            )
            check(
                "outside_window_not_required_or_duplicate",
                not_required[0] in {200, 422}
                and (
                    (not_required[1] or {}).get("duplicate") is True
                    or (not_required[1] or {}).get("code") == "outside_window_not_required"
                    or (not_required[1] or {}).get("code") == "slot_finalized"
                ),
                {"status": not_required[0], "code": (not_required[1] or {}).get("code"), "dup": (not_required[1] or {}).get("duplicate")},
            )

    prescribe(doctor, patient_b, ipd_b, location_uuid, provider, names, 1, 1)
    api("POST", f"/inpatient/patient/{patient_b}/medication-schedule", doctor, {})
    mar_b_status, mar_b, _ = api("GET", f"/inpatient/patient/{patient_b}/medication-administration", nurse)
    slots_b = slots_from(mar_b)
    check("mar_slots_b", mar_b_status == 200 and len(slots_b) >= 1, {"status": mar_b_status, "slots": len(slots_b)})
    if slots_b:
        cross = api(
            "POST",
            f"/inpatient/patient/{patient_a}/medication-administration",
            nurse,
            {"slotUuid": slots_b[0]["uuid"], "outcome": "given", "reason": ""},
        )
        check(
            "patient_isolation",
            cross[0] == 409 and (cross[1] or {}).get("code") in {"slot_mismatch", "slot_patient_mismatch"},
            {"status": cross[0], "code": (cross[1] or {}).get("code")},
        )
        rbac = {}
        for role, cookie in (
            ("doctor", users["doctor.abikan"]),
            ("lab", users["lab.abikan"]),
            ("pharmacy", users["pharmacy.abikan"]),
            ("accountant", users["accountant.abikan"]),
            ("admin", users["admin.abikan"]),
        ):
            status, body, _ = api(
                "POST",
                f"/inpatient/patient/{patient_b}/medication-administration",
                cookie,
                {"slotUuid": slots_b[0]["uuid"], "outcome": "given", "reason": ""},
            )
            rbac[role] = {"status": status, "code": (body or {}).get("code")}
            check(f"rbac_{role}_cannot_administer", status == 403, rbac[role])
        unauth = api(
            "POST",
            f"/inpatient/patient/{patient_b}/medication-administration",
            None,
            {"slotUuid": slots_b[0]["uuid"], "outcome": "given", "reason": ""},
        )
        check("rbac_unauthenticated", unauth[0] == 401, {"status": unauth[0]})
        report["rbac"] = rbac
        nurse_read = api("GET", f"/inpatient/patient/{patient_b}/medication-administration", nurse)
        doctor_read = api("GET", f"/inpatient/patient/{patient_b}/medication-administration", doctor)
        check("nurse_can_read", nurse_read[0] == 200, {"status": nurse_read[0]})
        check("doctor_can_read", doctor_read[0] == 200, {"status": doctor_read[0]})

    discharged = api("POST", "/inpatient/discharge", nurse, {"patientUuid": patient_b, "requestId": f"marfix-dc-{STAMP}"})
    check("discharge_b", discharged[0] == 200, {"status": discharged[0]})
    after_dc = api("POST", f"/inpatient/patient/{patient_b}/medication-schedule", doctor, {})
    check("no_schedule_after_discharge", after_dc[0] == 409 and (after_dc[1] or {}).get("code") == "not_admitted", {"status": after_dc[0], "code": (after_dc[1] or {}).get("code")})
    hist = api("GET", f"/inpatient/patient/{patient_b}/medication-administration?visitUuid={ipd_b}", nurse)
    check("historical_mar_readable", hist[0] == 200, {"status": hist[0], "orders": len((hist[1] or {}).get("orders") or [])})
    write_dc = api(
        "POST",
        f"/inpatient/patient/{patient_b}/medication-administration",
        nurse,
        {"slotUuid": (slots_b[0]["uuid"] if slots_b else "missing"), "outcome": "given", "reason": ""},
    )
    check("no_administer_after_discharge", write_dc[0] == 409, {"status": write_dc[0], "code": (write_dc[1] or {}).get("code")})

    e2e = api("GET", f"/inpatient/patient/{E2E}/medication-administration", nurse)
    check("e2e_historical_mar", e2e[0] == 200 and len((e2e[1] or {}).get("orders") or []) >= 1, {"status": e2e[0], "orders": len((e2e[1] or {}).get("orders") or [])})
    notes = api(
        "POST",
        f"/inpatient/patient/{patient_a}/nursing-notes",
        nurse,
        {"note": "MARFIX synthetic nursing note.", "requestId": f"marfix-note-{STAMP}"},
    )
    check("nursing_notes", notes[0] == 200, {"status": notes[0]})
    vitals = api(
        "POST",
        f"/inpatient/patient/{patient_a}/vitals",
        nurse,
        {
            "requestId": f"marfix-vitals-{STAMP}",
            "temperature": 36.8,
            "pulse": 80,
            "systolic": 110,
            "diastolic": 70,
            "respiratoryRate": 16,
            "spo2": 98,
        },
    )
    check("vitals", vitals[0] in {200, 422}, {"status": vitals[0], "code": (vitals[1] or {}).get("code")})

    failed = [row for row in report["checks"] if not row["ok"]]
    report["failed"] = failed
    report["passed"] = len(report["checks"]) - len(failed)
    print(json.dumps({"passed": report["passed"], "failed": len(failed), "performance": report.get("performance")}, indent=2))
    out = ROOT / "scripts" / f"verify-mar-ipd-slots-{STAMP}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print("wrote", out)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
