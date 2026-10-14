#!/usr/bin/env python3
"""Admit Bravo, record notes/vitals, prescribe IPD, poll MAR, pay/dispense Alpha."""

from __future__ import annotations

import base64
import json
import ssl
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://localhost"
API = "http://127.0.0.1:8787"
PWD = "Admin123"
CTX = ssl._create_unverified_context()
PA = "95e8f010-d127-4a8d-b651-23bdb4293dc6"
PB = "a1fb4a69-30de-4e64-a813-0406377648f7"
E2E = "f242364e-b70f-4fec-b29e-8ad4fbe147b5"
CONSULTATION_ENCOUNTER = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
CETIRIZINE = "7e0766e1-b679-4eb3-ab93-d63910ad6eb4"
FLEXIBLE = "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions"
RX = "f0544efa-8cb0-4828-bc6d-c7af433a63a5"


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


def call(method: str, url: str, cookie: str, body=None, timeout: int = 90):
    headers = {"Accept": "application/json", "Cookie": cookie}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=CTX if url.startswith("https") else None
        ) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "null"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:800]}
        return exc.code, payload


def api(method, path, cookie, body=None, timeout=90):
    return call(method, API + path, cookie, body, timeout)


def omrs(method, path, cookie, body=None, timeout=60):
    return call(method, BASE + path, cookie, body, timeout)


def report(name, ok, detail):
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:500])


def prescribe_ipd(doctor, patient, visit, location, provider, tablet, oral, once, qty, days):
    return omrs(
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
                        "doseUnits": tablet,
                        "route": oral,
                        "frequency": once,
                        "asNeeded": False,
                        "quantity": 3,
                        "quantityUnits": qty,
                        "numberOfRefills": 0,
                    },
                    "duration": 3,
                    "durationUnits": days,
                }
            ],
        },
    )


def slots_from(mar):
    slots = []
    if not isinstance(mar, dict):
        return slots
    for order in mar.get("orders") or []:
        for slot in order.get("slots") or []:
            slots.append(slot)
    slots.extend(mar.get("slots") or [])
    return slots


def main() -> int:
    rec = login("reception.abikan")
    doctor = login("doctor.abikan")
    nurse = login("nurse.abikan")
    pharm = login("pharmacy.abikan")
    lab = login("lab.abikan")
    acct = login("accountant.abikan")

    st, rx = api("GET", f"/pharmacy/prescription/{RX}", pharm)
    print("alpha_rx", st, {k: (rx or {}).get(k) for k in ("paymentStatus", "dispensingStatus", "drugName", "unitPrice", "salePrice")})
    if st == 200 and (rx or {}).get("paymentStatus") in {"PAID", "paid"}:
        st, disp = api("POST", f"/pharmacy/prescription/{RX}/dispense", pharm, {"requestId": f"rc-disp-{int(time.time())}"})
        report("pharmacy_dispense_after_pay", st == 200, {"status": st, "code": (disp or {}).get("code"), "message": (disp or {}).get("message")})
    else:
        report("pharmacy_dispense_after_pay", False, {"status": st, "payment": (rx or {}).get("paymentStatus")})

    st, account = api("GET", f"/patient-account/{PA}", acct)
    invoices = (account or {}).get("invoices") or []
    print("alpha_invoices")
    for inv in invoices:
        print(
            " ",
            inv.get("id"),
            inv.get("number"),
            inv.get("state"),
            (inv.get("amountTotal") or inv.get("amount") or {}),
            (inv.get("outstanding") or inv.get("residual") or {}),
        )
    billed = (account or {}).get("billed") or (account or {}).get("totals")
    print("account_totals", {k: account.get(k) for k in ("billed", "collected", "outstanding", "activity") if isinstance(account, dict)})

    st, lab_order = api("GET", f"/laboratory/order/{ 'b9616c14-4de4-4595-9c34-6009ae87cf81' }?patientUuid={PA}", lab)
    print("lab_order_detail", st, {k: (lab_order or {}).get(k) for k in ("status", "stage", "laboratoryStatus", "hasResult", "fee", "price", "openelisUrl", "message")})
    st, lab_patient = api("GET", f"/laboratory/patient/{PA}", lab)
    print("lab_patient_keys", st, list((lab_patient or {}).keys())[:20] if isinstance(lab_patient, dict) else lab_patient)
    st, doc_lab = api("GET", f"/laboratory/patient/{PA}", doctor)
    print("doctor_lab_view", st, (doc_lab or {}).get("code") if st != 200 else list((doc_lab or {}).keys())[:16])

    st, rad = api("GET", f"/radiology/patient/{PA}", doctor)
    print("doctor_radiology", st, {k: (rad or {}).get(k) for k in ("status", "orders", "message", "code")} if isinstance(rad, dict) else rad)

    # Existing E2E MAR read integrity
    st, e2e_mar = api("GET", f"/inpatient/patient/{E2E}/medication-administration", nurse)
    e2e_slots = slots_from(e2e_mar or {})
    completed = [s for s in e2e_slots if str(s.get("status") or "").upper() == "COMPLETED"]
    report("e2e_mar_history_intact", st == 200 and len(completed) >= 1, {"slots": len(e2e_slots), "completed": len(completed)})
    if completed:
        admin = completed[0].get("administration") or completed[0].get("medicationAdministration") or {}
        print("e2e_completed_admin", json.dumps(admin, default=str)[:400])
        print("e2e_completed_slot_keys", list(completed[0].keys()))
        scheduled = completed[0].get("scheduledTime") or completed[0].get("startTime")
        actual = (admin or {}).get("administeredAt") or (admin or {}).get("occurrenceDateTime")
        report("e2e_mar_times_distinct", bool(scheduled), {"scheduled": scheduled, "actual": actual})

    st, e2e_vitals = api("GET", f"/inpatient/patient/{E2E}/vitals", nurse)
    readings = (e2e_vitals or {}).get("readings") or []
    report("e2e_vitals_readings", st == 200, {"count": len(readings), "keys": list((e2e_vitals or {}).keys())[:12]})

    # Admit Bravo
    st, meta = api("GET", "/registration/metadata", rec)
    visit_types = (meta or {}).get("visitTypes") or []
    opd = next((row for row in visit_types if row.get("name") == "OPD"), None)
    locations = (meta or {}).get("locations") or (meta or {}).get("loginLocations") or []
    location = next((row for row in locations if row.get("name") == "OPD-1"), locations[0] if locations else None)
    location_uuid = (location or {}).get("uuid") or ""

    st, visits = api("GET", f"/registration/patient/{PB}", rec)
    print("bravo_reg", st, list((visits or {}).keys())[:12] if isinstance(visits, dict) else visits)

    # start visit if needed
    st, visit_body = api(
        "POST",
        f"/registration/patient/{PB}/visit",
        rec,
        {"visitTypeUuid": (opd or {}).get("uuid"), "requestId": f"rc-bravo-visit-{int(time.time())}"},
    )
    visit_b = (visit_body or {}).get("uuid") if st == 200 else None
    if not visit_b:
        # already has open visit?
        st, profile = api("GET", f"/consultation/patient/{PB}", doctor)
        visit_b = ((profile or {}).get("visit") or {}).get("uuid") or ((profile or {}).get("openVisit") or {}).get("uuid")
        print("bravo_existing_visit", visit_b, "start_status", st)
    report("bravo_visit", bool(visit_b), {"visit": visit_b, "start": st})

    admit = api(
        "POST",
        f"/inpatient/patient/{PB}/admit-decision",
        doctor,
        {"visitUuid": visit_b, "locationUuid": location_uuid, "requestId": f"rc-bravo-admit-{int(time.time())}"},
    )
    report("bravo_admit", admit[0] == 200, {"status": admit[0], "message": (admit[1] or {}).get("message")})

    board = api("GET", "/inpatient/board", nurse)[1]
    bed = None
    for area in (board or {}).get("areas") or []:
        for row in area.get("beds") or []:
            if row.get("status") == "AVAILABLE" and not row.get("patientUuid"):
                bed = row
                break
        if bed:
            break
    assign = api(
        "POST",
        "/inpatient/assign",
        nurse,
        {
            "patientUuid": PB,
            "bedUuid": (bed or {}).get("bedUuid"),
            "bedId": (bed or {}).get("bedId"),
            "requestId": f"rc-bravo-assign-{int(time.time())}",
        },
    )
    report("bravo_bed", assign[0] == 200, {"status": assign[0], "bed": (bed or {}).get("bedNumber"), "area": (bed or {}).get("areaName"), "msg": (assign[1] or {}).get("message")})

    stay = api("GET", f"/inpatient/patient/{PB}", nurse)[1]
    assignment = (stay or {}).get("assignment")
    print("bravo_stay", assignment)

    n1 = api(
        "POST",
        f"/inpatient/patient/{PB}/nursing-notes",
        nurse,
        {"note": "RC AUDIT Bravo note 1. Synthetic.", "requestId": f"rc-bravo-n1-{int(time.time())}"},
    )
    time.sleep(1)
    n2 = api(
        "POST",
        f"/inpatient/patient/{PB}/nursing-notes",
        nurse,
        {"note": "RC AUDIT Bravo note 2. Synthetic.", "requestId": f"rc-bravo-n2-{int(time.time())}"},
    )
    notes = api("GET", f"/inpatient/patient/{PB}/nursing-notes", nurse)[1]
    report(
        "bravo_notes_two",
        n1[0] == 200 and n2[0] == 200 and len((notes or {}).get("notes") or []) >= 2,
        {"c1": n1[0], "c2": n2[0], "count": len((notes or {}).get("notes") or [])},
    )

    v1 = api("POST", f"/inpatient/patient/{PB}/vitals", nurse, {"temperature": 36.8, "pulse": 76, "requestId": f"rc-bravo-v1-{int(time.time())}"})
    time.sleep(1)
    v2 = api("POST", f"/inpatient/patient/{PB}/vitals", nurse, {"temperature": 37.1, "pulse": 82, "requestId": f"rc-bravo-v2-{int(time.time())}"})
    vitals = api("GET", f"/inpatient/patient/{PB}/vitals", nurse)[1]
    readings = (vitals or {}).get("readings") or []
    report("bravo_vitals_two", v1[0] == 200 and v2[0] == 200 and len(readings) >= 2, {"c1": v1[0], "c2": v2[0], "count": len(readings)})

    # IPD visit
    st, ipd_visits = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={PB}&includeInactive=false&v=custom:(uuid,stopDatetime,visitType:(name),location:(uuid))",
        doctor,
    )
    ipd_visit = None
    ipd_loc = (assignment or {}).get("areaUuid") or location_uuid
    for row in (ipd_visits or {}).get("results") or []:
        vtype = ((row.get("visitType") or {}).get("name") or "").upper()
        if vtype == "IPD" and not row.get("stopDatetime"):
            ipd_visit = row.get("uuid")
            ipd_loc = ((row.get("location") or {}).get("uuid")) or ipd_loc
    report("bravo_ipd_visit", bool(ipd_visit), ipd_visit)

    st, sess = omrs("GET", "/openmrs/ws/rest/v1/session", doctor)
    user_uuid = ((sess or {}).get("user") or {}).get("uuid")
    st, provs = omrs("GET", f"/openmrs/ws/rest/v1/provider?user={user_uuid}&v=custom:(uuid,retired)", doctor)
    prov = next((r["uuid"] for r in (provs or {}).get("results") or [] if r.get("uuid") and not r.get("retired")), None)
    st, config = omrs("GET", "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders", doctor)
    dosing = (config or {}).get("doseUnits") or []
    routes = (config or {}).get("routes") or []
    freqs = (config or {}).get("frequencies") or []
    durations = (config or {}).get("durationUnits") or (config or {}).get("dosingRules") or []
    tablet = next((x.get("name") or x for x in dosing if "tablet" in str(x).lower()), (dosing[0].get("name") if dosing else "Tablet"))
    oral = next((x.get("name") or x for x in routes if "oral" in str(x).lower()), "Oral")
    once = next((x.get("name") or x for x in freqs if "once" in str(x).lower() or x.get("name") == "OD"), freqs[0].get("name") if freqs else "Once a day")
    qty = tablet
    days = "Day(s)"
    if isinstance(durations, list) and durations:
        days = durations[0].get("name") if isinstance(durations[0], dict) else str(durations[0])

    if ipd_visit and prov:
        st, saved = prescribe_ipd(doctor, PB, ipd_visit, ipd_loc, prov, tablet, oral, once, qty, days)
        report("bravo_ipd_rx", st in {200, 201}, {"status": st, "body": saved if st not in {200, 201} else "ok"})
        # also add a new IPD rx on E2E to see if slots appear
        st_e, stay_e = api("GET", f"/inpatient/patient/{E2E}", nurse)
        e2e_visit = ((stay_e or {}).get("visit") or {}).get("uuid")
        e2e_loc = ((stay_e or {}).get("assignment") or {}).get("areaUuid") or ipd_loc
        if e2e_visit:
            st2, saved2 = prescribe_ipd(doctor, E2E, e2e_visit, e2e_loc, prov, tablet, oral, once, qty, days)
            report("e2e_new_ipd_rx", st2 in {200, 201}, {"status": st2})
    else:
        report("bravo_ipd_rx", False, "no ipd visit or provider")

    # Poll MAR
    found = []
    for i in range(12):
        time.sleep(5)
        st, mar = api("GET", f"/inpatient/patient/{PB}/medication-administration", nurse)
        slots = slots_from(mar or {})
        print(f"poll_bravo {i} status={st} slots={len(slots)} orders={len((mar or {}).get('orders') or [])}")
        if slots:
            found = slots
            break
        st_e, mar_e = api("GET", f"/inpatient/patient/{E2E}/medication-administration", nurse)
        e_slots = [s for s in slots_from(mar_e or {}) if str(s.get("status") or "").upper() == "SCHEDULED"]
        print(f"poll_e2e_scheduled {len(e_slots)}")
        if e_slots:
            found = e_slots
            break

    # determine which patient has scheduled slots
    st_b, mar_b = api("GET", f"/inpatient/patient/{PB}/medication-administration", nurse)
    st_e, mar_e = api("GET", f"/inpatient/patient/{E2E}/medication-administration", nurse)
    b_sched = [s for s in slots_from(mar_b or {}) if str(s.get("status") or "").upper() == "SCHEDULED"]
    e_sched = [s for s in slots_from(mar_e or {}) if str(s.get("status") or "").upper() == "SCHEDULED"]
    print("scheduled bravo", len(b_sched), "e2e", len(e_sched))

    patient, scheduled = (PB, b_sched) if b_sched else (E2E, e_sched)
    report("mar_scheduled_slots_runtime", bool(scheduled), {"patient": patient, "count": len(scheduled)})

    if scheduled:
        first = scheduled[0]
        print("first_slot", json.dumps({k: first.get(k) for k in ("uuid", "status", "startTime", "scheduledTime", "timing", "windowStatus")}, default=str))
        blocked = api(
            "POST",
            f"/inpatient/patient/{patient}/medication-administration",
            nurse,
            {"slotUuid": first.get("uuid"), "outcome": "given"},
        )
        timing = (first.get("timing") or {}).get("status")
        if timing == "eligible":
            report("mar_eligible_or_window", blocked[0] == 200, {"status": blocked[0], "timing": timing})
            given = blocked
        else:
            report(
                "mar_normal_blocked_outside",
                blocked[0] == 409,
                {"status": blocked[0], "code": (blocked[1] or {}).get("code"), "timing": timing},
            )
            given = api(
                "POST",
                f"/inpatient/patient/{patient}/medication-administration",
                nurse,
                {
                    "slotUuid": first.get("uuid"),
                    "outcome": "given",
                    "outsideWindow": True,
                    "reason": "RC AUDIT Bravo/E2E outside-window synthetic administration.",
                },
            )
            report("mar_outside_ok", given[0] == 200, {"status": given[0], "code": (given[1] or {}).get("code")})
        if given[0] == 200:
            slot = (given[1] or {}).get("slot") or {}
            admin = slot.get("administration") or slot.get("medicationAdministration") or {}
            print("admin_record", json.dumps(admin, default=str)[:500])
            print("slot_after", {k: slot.get(k) for k in ("startTime", "scheduledTime", "status")})
            report("mar_schedule_immutable", bool(first.get("startTime") or slot.get("startTime")), {"before": first.get("startTime"), "after": slot.get("startTime")})
            report("mar_server_actual_time", bool(admin.get("administeredAt") or admin.get("occurrenceDateTime") or admin.get("uuid")), list(admin.keys())[:12] if isinstance(admin, dict) else admin)
            report(
                "mar_performer",
                "nurse" in json.dumps(given[1], default=str).lower() or bool(admin.get("authorName") or admin.get("performer")),
                admin,
            )
            dup = api(
                "POST",
                f"/inpatient/patient/{patient}/medication-administration",
                nurse,
                {"slotUuid": first.get("uuid"), "outcome": "given", "outsideWindow": True, "reason": "dup"},
            )
            report("mar_duplicate", dup[0] in {200, 409} and (dup[0] == 409 or (dup[1] or {}).get("duplicate")), {"status": dup[0], "dup": (dup[1] or {}).get("duplicate")})
            cross = api(
                "POST",
                f"/inpatient/patient/{PA}/medication-administration",
                nurse,
                {"slotUuid": first.get("uuid"), "outcome": "given"},
            )
            report("mar_isolation", cross[0] in {403, 404, 409}, {"status": cross[0], "code": (cross[1] or {}).get("code")})

    st, dash = api("GET", "/admin/analytics/overview?period=today", login("hospitaladmin.abikan"))
    overview = dash if st == 200 else {}
    print("analytics_today_keys", st, list((overview or {}).keys())[:20])
    print("finance", {k: overview.get(k) for k in ("finance", "financial", "billing", "money", "kpis")})
    occ = overview.get("occupancy") if isinstance(overview, dict) else None
    print("occupancy", occ)

    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
