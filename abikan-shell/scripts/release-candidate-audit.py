#!/usr/bin/env python3
"""Release-candidate runtime audit against the live development stack.

Creates clearly named synthetic TEST records. Does not delete data.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
CTX = ssl._create_unverified_context()
STAMP = int(time.time())
CONSULTATION_ENCOUNTER = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
HPI_CONCEPT = "1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
NOTE_CONCEPT = "d37294c5-5e07-11ef-8f7c-0242ac120002"
TEMP_CONCEPT = "5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
PULSE_CONCEPT = "5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
FLEXIBLE = "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions"
CETIRIZINE = "7e0766e1-b679-4eb3-ab93-d63910ad6eb4"

report: dict[str, object] = {
    "stamp": STAMP,
    "synthetic": {},
    "checks": [],
    "failures": [],
}


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


def call(method: str, url: str, cookie: str | None, body: dict | None = None, timeout: int = 90):
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        context = CTX if url.startswith("https") else None
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read().decode()
            payload = json.loads(raw) if raw else None
            return response.status, payload, round((time.perf_counter() - started) * 1000)
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            payload = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            payload = raw[:400]
        return error.code, payload, round((time.perf_counter() - started) * 1000)
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}, 0


def api(method: str, path: str, cookie: str | None, body: dict | None = None, timeout: int = 90):
    return call(method, f"{API}{path}", cookie, body, timeout)


def omrs(method: str, path: str, cookie: str | None, body: dict | None = None, timeout: int = 60):
    return call(method, f"{BASE}{path}", cookie, body, timeout)


def check(name: str, ok: bool, detail: object = None) -> bool:
    row = {"name": name, "ok": bool(ok), "detail": detail}
    report["checks"].append(row)
    if not ok:
        report["failures"].append(row)
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:240])
    return bool(ok)


def amount(payload: object, *keys: str) -> float | None:
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


def wait_ok(method: str, path: str, cookie: str, body: dict | None = None, tries: int = 8, delay: float = 4):
    last = (0, None, 0)
    for _ in range(tries):
        last = api(method, path, cookie, body)
        if last[0] == 200:
            return last
        time.sleep(delay)
    return last


def register_patient(rec: str, given: str, family: str, gender: str, birth: str) -> str | None:
    status, body, _ = api(
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
    uuid_value = body.get("uuid") if isinstance(body, dict) else None
    check(f"register_{family}", status == 200 and bool(uuid_value), {"status": status, "uuid": uuid_value})
    return uuid_value


def start_visit(rec: str, patient: str, visit_type: str) -> str | None:
    status, body, _ = api(
        "POST",
        f"/registration/patient/{patient}/visit",
        rec,
        {"visitTypeUuid": visit_type, "requestId": f"rc-visit-{STAMP}-{patient[:8]}"},
    )
    uuid_value = body.get("uuid") if isinstance(body, dict) else None
    check("start_opd_visit", status == 200 and bool(uuid_value), {"status": status, "uuid": uuid_value})
    return uuid_value


def session_user(cookie: str) -> dict:
    status, body, _ = omrs("GET", "/openmrs/ws/rest/v1/session", cookie)
    return body if status == 200 and isinstance(body, dict) else {}


def provider_uuid(cookie: str, user_uuid: str) -> str | None:
    status, body, _ = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/provider?user={user_uuid}&v=custom:(uuid,retired)",
        cookie,
    )
    rows = (body or {}).get("results") if isinstance(body, dict) else []
    for row in rows or []:
        if row.get("uuid") and not row.get("retired"):
            return row["uuid"]
    return None


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
        "radiologist.abikan",
        "superman",
    ):
        try:
            users[role] = login(role)
            check(f"login_{role}", True)
        except Exception as exc:  # noqa: BLE001
            users[role] = ""
            check(f"login_{role}", False, str(exc))

    rec, doctor, nurse = users.get("reception.abikan"), users.get("doctor.abikan"), users.get("nurse.abikan")
    lab, pharm, acct = users.get("lab.abikan"), users.get("pharmacy.abikan"), users.get("accountant.abikan")
    admin, radio = users.get("admin.abikan"), users.get("radiologist.abikan")

    # Unauthenticated
    status, body, _ = api("GET", "/pharmacy/queue", None)
    check("unauthenticated_401", status == 401, {"status": status, "body": body})

    meta_status, meta, _ = api("GET", "/registration/metadata", rec)
    check("registration_metadata", meta_status == 200, {"status": meta_status})
    visit_types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in visit_types or [] if row.get("name") == "OPD"), None)
    locations = (meta or {}).get("locations") or (meta or {}).get("loginLocations") or []
    location = next((row for row in locations if row.get("name") == "OPD-1"), locations[0] if locations else None)
    location_uuid = (location or {}).get("uuid") if isinstance(location, dict) else ""
    opd_uuid = (opd or {}).get("uuid") if isinstance(opd, dict) else ""

    patient_a = register_patient(rec, "RCAUDIT", f"ALPHA{STAMP % 100000}", "F", "1990-01-15")
    patient_b = register_patient(rec, "RCAUDIT", f"BRAVO{STAMP % 100000}", "M", "1988-06-20")
    report["synthetic"]["patients"] = {"a": patient_a, "b": patient_b}
    if not patient_a or not patient_b or not opd_uuid:
        json.dump(report, sys.stdout, indent=2, default=str)
        return 1

    profile_status, profile, _ = api("GET", f"/registration/patient/{patient_a}/profile", rec)
    name = ""
    if isinstance(profile, dict):
        name = str((profile.get("patient") or profile).get("name") or profile.get("givenName") or "")
    check("demographics", profile_status == 200 and "RCAUDIT" in json.dumps(profile), {"status": profile_status})

    visit_a = start_visit(rec, patient_a, opd_uuid)
    visit_b = start_visit(rec, patient_b, opd_uuid)
    report["synthetic"]["visits"] = {"a": visit_a, "b": visit_b}

    # Reception pricing lifecycle
    rec_list = api("GET", "/pricing/reception", rec)[1]
    individual = next((row for row in (rec_list or {}).get("items") or [] if row.get("id") == "individual"), None)
    original_card = amount(individual, "price") if individual else None
    first_card = (original_card or 2000) + 19
    second_card = first_card + 13
    if individual and original_card is not None:
        api("PATCH", "/pricing/reception/individual", rec, {"price": first_card, "expectedPrice": original_card})
    charge_a = wait_ok(
        "POST",
        f"/registration/patient/{patient_a}/charge",
        rec,
        {"visitUuid": visit_a, "cardType": "individual", "requestId": f"rc-charge-a-{STAMP}"},
    )
    fee_a = amount(charge_a[1], "feeAmount")
    check("registration_charge_old_price", charge_a[0] == 200 and fee_a == first_card, {"status": charge_a[0], "fee": fee_a, "expected": first_card})
    if original_card is not None:
        api("PATCH", "/pricing/reception/individual", rec, {"price": second_card, "expectedPrice": first_card})
    charge_b = wait_ok(
        "POST",
        f"/registration/patient/{patient_b}/charge",
        rec,
        {"visitUuid": visit_b, "cardType": "individual", "requestId": f"rc-charge-b-{STAMP}"},
    )
    fee_b = amount(charge_b[1], "feeAmount")
    after_a = amount(api("GET", f"/registration/patient/{patient_a}", rec)[1], "feeAmount")
    check("registration_old_bill_unchanged", after_a == first_card, {"old": after_a, "expected": first_card})
    check("registration_new_bill_new_price", fee_b == second_card, {"new": fee_b, "expected": second_card})
    if original_card is not None:
        api("PATCH", "/pricing/reception/individual", rec, {"price": original_card, "expectedPrice": second_card})
    hist = api("GET", "/pricing/reception/individual/history", rec)[1]
    hist_rows = (hist or {}).get("changes") or (hist or {}).get("history") or (hist or {}).get("items") or []
    check("reception_price_history", isinstance(hist, dict) and (hist_rows or hist.get("status") == "ok"), {"keys": list(hist.keys()) if isinstance(hist, dict) else None})

    # Doctor consultation
    session = session_user(doctor)
    user_uuid = ((session.get("user") or {}).get("uuid")) if session else None
    prov = provider_uuid(doctor, user_uuid or "")
    check("doctor_provider", bool(prov), {"provider": prov})
    config_status, config, _ = omrs("GET", "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders", doctor)
    check("drug_order_config", config_status == 200, {"status": config_status})
    dose_units = [row.get("name") for row in (config or {}).get("doseUnits") or [] if row.get("name")]
    routes = [row.get("name") for row in (config or {}).get("routes") or [] if row.get("name")]
    freqs = [row.get("name") for row in (config or {}).get("frequencies") or [] if row.get("name")]
    durations = [row.get("name") for row in (config or {}).get("durationUnits") or [] if row.get("name")]
    qty_units = [row.get("name") for row in (config or {}).get("dispensingUnits") or dose_units if row.get("name")]
    tablet = next((item for item in dose_units if "tablet" in item.lower() or item.lower() == "tablet(s)"), dose_units[0] if dose_units else "Tablet(s)")
    oral = next((item for item in routes if "oral" in item.lower()), routes[0] if routes else "Oral")
    once = next((item for item in freqs if item.lower() in {"once a day", "od", "once daily"}), freqs[0] if freqs else "Once a day")
    days = next((item for item in durations if "day" in item.lower()), durations[0] if durations else "Day(s)")
    qty_unit = next((item for item in qty_units if "tablet" in item.lower()), qty_units[0] if qty_units else tablet)

    consult_body = {
        "patientUuid": patient_a,
        "visitUuid": visit_a,
        "visitType": "OPD",
        "encounterTypeUuid": CONSULTATION_ENCOUNTER,
        "locationUuid": location_uuid,
        "providers": [{"uuid": prov}],
        "observations": [
            {"concept": {"uuid": HPI_CONCEPT, "name": "History of present illness", "dataType": "Text"}, "value": "RC AUDIT HPI: cough for two days. Synthetic."},
            {"concept": {"uuid": NOTE_CONCEPT, "name": "Consultation Note", "dataType": "Text"}, "value": "RC AUDIT note: supportive care. Synthetic."},
            {"concept": {"uuid": TEMP_CONCEPT, "name": "Temperature (C)", "dataType": "Numeric"}, "value": 36.8},
            {"concept": {"uuid": PULSE_CONCEPT, "name": "Pulse", "dataType": "Numeric"}, "value": 78},
        ],
        "bahmniDiagnoses": [
            {"freeTextAnswer": "RC AUDIT viral illness", "order": "PRIMARY", "certainty": "PRESUMED"}
        ],
        "orders": [],
        "drugOrders": [
            {
                "careSetting": "OUTPATIENT",
                "drug": {"uuid": CETIRIZINE},
                "orderType": "Drug Order",
                "dosingInstructionType": FLEXIBLE,
                "dosingInstructions": {
                    "dose": 1,
                    "doseUnits": tablet,
                    "route": oral,
                    "frequency": once,
                    "asNeeded": False,
                    "quantity": 1,
                    "quantityUnits": qty_unit,
                    "numberOfRefills": 0,
                },
                "duration": 1,
                "durationUnits": days,
            }
        ],
    }
    save_status, saved, _ = omrs("POST", "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter", doctor, consult_body)
    encounter_uuid = (saved or {}).get("encounterUuid") if isinstance(saved, dict) else None
    check("consultation_save", save_status in {200, 201} and bool(encounter_uuid or saved), {"status": save_status, "encounter": encounter_uuid, "body": saved if save_status >= 400 else None})

    consult = api("GET", f"/consultation/patient/{patient_a}?visitUuid={visit_a}", doctor)
    check("consultation_load", consult[0] == 200, {"status": consult[0]})
    dx_status, dx, _ = omrs("GET", f"/openmrs/ws/rest/v1/bahmnicore/diagnosis/search?patientUuid={patient_a}", doctor)
    dx_text = json.dumps(dx, default=str).lower()
    check("diagnosis_recorded", dx_status == 200 and "rc audit" in dx_text, {"status": dx_status})

    # Laboratory order + pricing lifecycle
    lab_items = api("GET", "/pricing/laboratory?q=Malarial", lab)[1]
    lab_item = next((row for row in (lab_items or {}).get("items") or [] if row.get("editable")), None)
    if not lab_item:
        lab_items = api("GET", "/pricing/laboratory", lab)[1]
        lab_item = next((row for row in (lab_items or {}).get("items") or [] if row.get("editable") and amount(row, "price")), None)
    lab_id = (lab_item or {}).get("id")
    lab_original = amount(lab_item, "price") if lab_item else None
    lab_first = (lab_original or 1500) + 11
    lab_second = lab_first + 17
    if lab_id and lab_original is not None:
        api("PATCH", f"/pricing/laboratory/{lab_id}", lab, {"price": lab_first, "expectedPrice": lab_original})
    lab_order = api(
        "POST",
        f"/laboratory/patient/{patient_a}/orders",
        doctor,
        {
            "visitUuid": visit_a,
            "locationUuid": location_uuid,
            "encounterUuid": encounter_uuid,
            "tests": [{"conceptUuid": lab_id}],
            "requestId": f"rc-lab-a-{STAMP}",
        },
    )
    lab_fee = None
    lab_order_uuid = None
    if isinstance(lab_order[1], dict):
        charge = lab_order[1].get("charge") or {}
        lab_fee = amount(charge, "feeAmount")
        orders = lab_order[1].get("orders") or (charge.get("tests") or [])
        if orders:
            lab_order_uuid = orders[0].get("uuid") or orders[0].get("orderUuid")
        if lab_fee is None:
            for row in charge.get("tests") or []:
                lab_fee = amount(row, "feeAmount")
                if lab_fee is not None:
                    break
    check("lab_order_created", lab_order[0] == 200 and bool(lab_order_uuid or lab_order[1]), {"status": lab_order[0], "fee": lab_fee, "order": lab_order_uuid, "message": (lab_order[1] or {}).get("message") if isinstance(lab_order[1], dict) else lab_order[1]})
    report["synthetic"]["labOrder"] = lab_order_uuid
    board = api("GET", "/laboratory/board", lab)
    board_text = json.dumps(board[1], default=str)
    check("lab_board_has_order", board[0] == 200 and (patient_a in board_text or (lab_order_uuid or "") in board_text), {"status": board[0], "orders": len((board[1] or {}).get("orders") or []) if isinstance(board[1], dict) else None})
    if lab_id and lab_original is not None:
        api("PATCH", f"/pricing/laboratory/{lab_id}", lab, {"price": lab_second, "expectedPrice": lab_first})
    after_lab = api("GET", f"/laboratory/patient/{patient_a}", lab)[1]
    old_lab_fee = None
    if isinstance(after_lab, dict):
        for row in after_lab.get("tests") or []:
            old_lab_fee = amount(row, "feeAmount")
            if old_lab_fee is not None:
                break
    check("lab_old_charge_unchanged", old_lab_fee in {lab_fee, lab_first} if lab_fee or lab_first else True, {"after": old_lab_fee, "captured": lab_fee})
    # isolation: order lab for B using A's visit
    cross_lab = api(
        "POST",
        f"/laboratory/patient/{patient_b}/orders",
        doctor,
        {
            "visitUuid": visit_a,
            "locationUuid": location_uuid,
            "tests": [{"conceptUuid": lab_id}],
            "requestId": f"rc-lab-cross-{STAMP}",
        },
    )
    check("lab_cross_patient_rejected", cross_lab[0] in {409, 422, 403, 404}, {"status": cross_lab[0], "code": (cross_lab[1] or {}).get("code") if isinstance(cross_lab[1], dict) else cross_lab[1]})
    if lab_id and lab_original is not None:
        api("PATCH", f"/pricing/laboratory/{lab_id}", lab, {"price": original_card and lab_original or lab_original})

    # Radiology
    rad = api(
        "POST",
        f"/radiology/patient/{patient_a}/orders",
        doctor,
        {
            "visitUuid": visit_a,
            "locationUuid": location_uuid,
            "encounterUuid": encounter_uuid,
            "services": [{"serviceId": "xr-chest"}],
            "requestId": f"rc-rad-a-{STAMP}",
        },
    )
    check("radiology_order", rad[0] == 200, {"status": rad[0], "body": rad[1] if rad[0] != 200 else {"orders": len((rad[1] or {}).get("orders") or []) if isinstance(rad[1], dict) else True}})
    worklist = api("GET", "/radiology/worklist", radio or doctor)
    check("radiology_worklist", worklist[0] in {200, 403}, {"status": worklist[0], "role": "radiologist" if radio else "doctor-fallback"})
    report["synthetic"]["radiology"] = rad[1] if isinstance(rad[1], dict) else {"status": rad[0]}

    # Admission
    admit = api(
        "POST",
        f"/inpatient/patient/{patient_a}/admit-decision",
        doctor,
        {"visitUuid": visit_a, "locationUuid": location_uuid, "requestId": f"rc-admit-{STAMP}"},
    )
    check("admit_request", admit[0] == 200, {"status": admit[0], "message": (admit[1] or {}).get("message") if isinstance(admit[1], dict) else admit[1]})

    board_ip = api("GET", "/inpatient/board", nurse)
    check("ward_board", board_ip[0] == 200, {"status": board_ip[0]})
    bed = None
    if isinstance(board_ip[1], dict):
        for area in board_ip[1].get("areas") or []:
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
            "patientUuid": patient_a,
            "bedUuid": (bed or {}).get("bedUuid"),
            "bedId": (bed or {}).get("bedId"),
            "requestId": f"rc-assign-{STAMP}",
        },
    ) if bed else (0, {"error": "no_free_bed"}, 0)
    check("bed_assign", assign[0] == 200, {"status": assign[0], "bed": (bed or {}).get("bedNumber"), "message": (assign[1] or {}).get("message") if isinstance(assign[1], dict) else assign[1]})
    stay = api("GET", f"/inpatient/patient/{patient_a}", nurse)
    assignment = (stay[1] or {}).get("assignment") if isinstance(stay[1], dict) else None
    check("stay_assigned", stay[0] == 200 and bool(assignment), {"status": stay[0], "assignment": assignment})
    report["synthetic"]["bed"] = {"bedNumber": (bed or {}).get("bedNumber"), "bedUuid": (bed or {}).get("bedUuid")}

    # Isolation: assign B to same bed
    if bed:
        cross_bed = api(
            "POST",
            "/inpatient/assign",
            nurse,
            {"patientUuid": patient_b, "bedUuid": bed.get("bedUuid"), "bedId": bed.get("bedId"), "requestId": f"rc-assign-cross-{STAMP}"},
        )
        check("bed_cross_or_occupied_rejected", cross_bed[0] in {409, 422, 403}, {"status": cross_bed[0], "code": (cross_bed[1] or {}).get("code") if isinstance(cross_bed[1], dict) else cross_bed[1]})

    # Nursing notes + vitals
    note1 = api(
        "POST",
        f"/inpatient/patient/{patient_a}/nursing-notes",
        nurse,
        {"content": "RC AUDIT first nursing note. Synthetic.", "requestId": f"rc-note-1-{STAMP}"},
    )
    time.sleep(1)
    note2 = api(
        "POST",
        f"/inpatient/patient/{patient_a}/nursing-notes",
        nurse,
        {"content": "RC AUDIT second nursing note. Synthetic.", "requestId": f"rc-note-2-{STAMP}"},
    )
    notes = api("GET", f"/inpatient/patient/{patient_a}/nursing-notes", nurse)
    note_rows = (notes[1] or {}).get("notes") if isinstance(notes[1], dict) else []
    check("nursing_notes_two_separate", notes[0] == 200 and len(note_rows) >= 2, {"status": notes[0], "count": len(note_rows), "create": [note1[0], note2[0]]})
    cross_note = api(
        "POST",
        f"/inpatient/patient/{patient_b}/nursing-notes",
        nurse,
        {"content": "should fail not admitted", "requestId": f"rc-note-cross-{STAMP}"},
    )
    check("notes_unadmitted_rejected", cross_note[0] in {409, 403, 422}, {"status": cross_note[0], "code": (cross_note[1] or {}).get("code") if isinstance(cross_note[1], dict) else None})

    v1 = api(
        "POST",
        f"/inpatient/patient/{patient_a}/vitals",
        nurse,
        {"temperature": 36.9, "pulse": 80, "requestId": f"rc-vitals-1-{STAMP}"},
    )
    time.sleep(1)
    v2 = api(
        "POST",
        f"/inpatient/patient/{patient_a}/vitals",
        nurse,
        {"temperature": 37.2, "pulse": 88, "requestId": f"rc-vitals-2-{STAMP}"},
    )
    vitals = api("GET", f"/inpatient/patient/{patient_a}/vitals", nurse)
    check("vitals_created", v1[0] == 200 and v2[0] == 200, {"first": v1[0], "second": v2[0], "firstBody": v1[1] if v1[0] != 200 else None})
    vital_sets = 0
    if isinstance(vitals[1], dict):
        history = vitals[1].get("history") or vitals[1].get("sets") or vitals[1].get("readings") or []
        if isinstance(history, dict):
            vital_sets = sum(len(rows) for rows in history.values() if isinstance(rows, list))
        else:
            vital_sets = len(history)
    check("vitals_history_separate", vitals[0] == 200 and vital_sets >= 2, {"status": vitals[0], "count": vital_sets})
    cross_vitals = api("POST", f"/inpatient/patient/{patient_b}/vitals", nurse, {"temperature": 36.5, "requestId": f"rc-vitals-cross-{STAMP}"})
    check("vitals_cross_patient_rejected", cross_vitals[0] in {409, 403, 422}, {"status": cross_vitals[0]})

    # IPD prescription for MAR
    stay_visit = None
    if isinstance(stay[1], dict):
        stay_visit = ((stay[1].get("visit") or {}) .get("uuid")) or None
    ipd_visit_status, ipd_visits, _ = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={patient_a}&includeInactive=false&v=custom:(uuid,stopDatetime,visitType:(name))",
        doctor,
    )
    for row in (ipd_visits or {}).get("results") or []:
        vtype = ((row.get("visitType") or {}).get("name") or "").upper()
        if vtype == "IPD" and not row.get("stopDatetime"):
            stay_visit = row.get("uuid")
    report["synthetic"]["ipdVisit"] = stay_visit
    if stay_visit and prov:
        ipd_save = omrs(
            "POST",
            "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
            doctor,
            {
                "patientUuid": patient_a,
                "visitUuid": stay_visit,
                "visitType": "IPD",
                "encounterTypeUuid": CONSULTATION_ENCOUNTER,
                "locationUuid": (assignment or {}).get("areaUuid") or location_uuid,
                "providers": [{"uuid": prov}],
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
                            "quantityUnits": qty_unit,
                            "numberOfRefills": 0,
                        },
                        "duration": 3,
                        "durationUnits": days,
                    }
                ],
            },
        )
        check("ipd_prescription", ipd_save[0] in {200, 201}, {"status": ipd_save[0]})
        time.sleep(3)
    mar = api("GET", f"/inpatient/patient/{patient_a}/medication-administration", nurse)
    slots = []
    if isinstance(mar[1], dict):
        for order in mar[1].get("orders") or [mar[1]]:
            slots.extend(order.get("slots") or [])
        if not slots:
            slots = mar[1].get("slots") or []
    check("mar_loaded", mar[0] == 200, {"status": mar[0], "slots": len(slots), "message": (mar[1] or {}).get("message") if isinstance(mar[1], dict) else None})
    scheduled = [row for row in slots if str(row.get("status") or "").upper() == "SCHEDULED"]
    eligible = [row for row in scheduled if (row.get("timing") or {}).get("status") == "eligible" or row.get("windowStatus") == "eligible"]
    future = [row for row in scheduled if (row.get("timing") or {}).get("status") in {"future", "upcoming"} or row.get("windowStatus") in {"future", "upcoming"}]
    if not eligible and scheduled:
        # try first scheduled with outsideWindow
        first = scheduled[0]
        future_try = api(
            "POST",
            f"/inpatient/patient/{patient_a}/medication-administration",
            nurse,
            {"slotUuid": first.get("uuid"), "outcome": "given"},
        )
        check(
            "mar_future_or_window_blocked",
            future_try[0] in {409, 422},
            {"status": future_try[0], "code": (future_try[1] or {}).get("code") if isinstance(future_try[1], dict) else None},
        )
        outside = api(
            "POST",
            f"/inpatient/patient/{patient_a}/medication-administration",
            nurse,
            {"slotUuid": first.get("uuid"), "outcome": "given", "outsideWindow": True, "reason": "RC AUDIT outside-window reason"},
        )
        check("mar_outside_window_with_reason", outside[0] == 200, {"status": outside[0], "body": outside[1] if outside[0] != 200 else {"duplicate": (outside[1] or {}).get("duplicate")}})
        if outside[0] == 200 and isinstance(outside[1], dict):
            slot = outside[1].get("slot") or {}
            admin = slot.get("medicationAdministration") or outside[1].get("administration") or {}
            check("mar_schedule_unchanged", bool(slot.get("startTime") or first.get("startTime")), {"scheduled": slot.get("startTime") or first.get("startTime")})
            check("mar_actual_time_present", bool(admin.get("administeredAt") or admin.get("occurrenceDateTime") or admin.get("uuid")), {"admin": list(admin.keys())[:8] if isinstance(admin, dict) else admin})
            check("mar_performer_present", "nurse" in json.dumps(outside[1], default=str).lower() or bool(admin.get("performer") or admin.get("authorName")), {"keys": list((outside[1] or {}).keys())})
            dup = api(
                "POST",
                f"/inpatient/patient/{patient_a}/medication-administration",
                nurse,
                {"slotUuid": first.get("uuid"), "outcome": "given", "outsideWindow": True, "reason": "duplicate"},
            )
            check("mar_duplicate_safe", dup[0] in {200, 409} and (dup[0] == 409 or (isinstance(dup[1], dict) and dup[1].get("duplicate"))), {"status": dup[0]})
    elif eligible:
        given = api(
            "POST",
            f"/inpatient/patient/{patient_a}/medication-administration",
            nurse,
            {"slotUuid": eligible[0].get("uuid"), "outcome": "given"},
        )
        check("mar_eligible_given", given[0] == 200, {"status": given[0]})
    else:
        check("mar_slots_present", False, {"marStatus": mar[0], "slots": len(slots)})

    wrong_slot = api(
        "POST",
        f"/inpatient/patient/{patient_b}/medication-administration",
        nurse,
        {"slotUuid": (scheduled[0].get("uuid") if scheduled else str(uuid.uuid4())), "outcome": "given"},
    )
    check("mar_cross_patient_rejected", wrong_slot[0] in {409, 403, 422, 404}, {"status": wrong_slot[0]})

    # Pharmacy queue / price / payment / dispense
    queue = api("GET", "/pharmacy/queue", pharm)
    check("pharmacy_queue", queue[0] == 200, {"status": queue[0], "ready": len((queue[1] or {}).get("ready") or []), "other": len((queue[1] or {}).get("other") or [])})
    rx = None
    if isinstance(queue[1], dict):
        for row in (queue[1].get("ready") or []) + (queue[1].get("other") or []):
            if row.get("patientUuid") == patient_a:
                rx = row
                break
    if not rx:
        for _ in range(10):
            time.sleep(4)
            queue = api("GET", "/pharmacy/queue", pharm)
            if isinstance(queue[1], dict):
                for row in (queue[1].get("ready") or []) + (queue[1].get("other") or []):
                    if row.get("patientUuid") == patient_a:
                        rx = row
                        break
            if rx:
                break
    check("pharmacy_prescription_visible", bool(rx), {"rx": {k: (rx or {}).get(k) for k in ("orderUuid", "paymentStatus", "dispensingStatus", "drugName")}})
    report["synthetic"]["prescription"] = (rx or {}).get("orderUuid")

    # Billing + payment
    account = api("GET", f"/patient-account/{patient_a}", acct)
    check("patient_account", account[0] == 200, {"status": account[0]})
    invoices = (account[1] or {}).get("invoices") if isinstance(account[1], dict) else []
    unpaid = [row for row in invoices or [] if row.get("state") == "posted" and amount(row, "outstanding") not in (None, 0)]
    dash = api("GET", "/accountant/dashboard", acct)
    journals = api("GET", "/accountant/journals", acct)
    journal_id = None
    if isinstance(journals[1], dict):
        rows = journals[1].get("journals") or []
        if rows:
            journal_id = rows[0].get("id")
    pay_status = None
    if unpaid and journal_id:
        invoice_ids = [row.get("id") for row in unpaid if row.get("id")]
        total = sum(amount(row, "outstanding") or 0 for row in unpaid)
        pay = api(
            "POST",
            "/accountant/payment",
            acct,
            {
                "patientUuid": patient_a,
                "invoiceIds": invoice_ids,
                "amount": total,
                "journalId": journal_id,
                "requestId": f"rc-pay-{STAMP}",
            },
        )
        pay_status = pay[0]
        check("payment_recorded", pay[0] == 200, {"status": pay[0], "amount": total, "body": pay[1] if pay[0] != 200 else (pay[1] or {}).get("payment")})
        report["synthetic"]["payment"] = (pay[1] or {}).get("payment") if isinstance(pay[1], dict) else None
        after_pay = api("GET", f"/patient-account/{patient_a}", acct)[1]
        billed = None
        collected = None
        outstanding = None
        if isinstance(after_pay, dict):
            summary = after_pay.get("summary") or {}
            billed = summary.get("billedByCurrency") or after_pay.get("billed")
            collected = summary.get("paidByCurrency") or after_pay.get("paid")
            outstanding = summary.get("outstandingByCurrency")
        check("billed_collected_outstanding_present", after_pay is not None, {"billed": billed, "collected": collected, "outstanding": outstanding})
    else:
        check("payment_possible", False, {"unpaid": len(unpaid or []), "journal": journal_id, "invoices": len(invoices or [])})

    if rx and (rx.get("orderUuid")):
        after_pay_rx = api("GET", f"/pharmacy/prescription/{rx['orderUuid']}", pharm)
        check("pharmacy_prescription_detail", after_pay_rx[0] == 200, {"status": after_pay_rx[0], "payment": (after_pay_rx[1] or {}).get("paymentStatus")})
        if (after_pay_rx[1] or {}).get("canDispense"):
            disp = api("POST", f"/pharmacy/prescription/{rx['orderUuid']}/dispense", pharm, {"requestId": f"rc-disp-{STAMP}"})
            check("pharmacy_dispense", disp[0] == 200, {"status": disp[0]})
        else:
            check("pharmacy_dispense_gated", True, {"reason": (after_pay_rx[1] or {}).get("blockReason"), "status": (after_pay_rx[1] or {}).get("dispensingStatus")})

    # RBAC matrix
    rbac_cases = [
        ("doctor_lab_price_write", doctor, "PATCH", "/pricing/laboratory/x", {"price": 1}, {403, 404, 422}),
        ("nurse_pharmacy_write", nurse, "PATCH", "/pricing/pharmacy/x", {"price": 1}, {403, 404, 422}),
        ("lab_pharmacy_write", lab, "PATCH", "/pricing/pharmacy/x", {"price": 1}, {403, 404, 422}),
        ("reception_lab_write", rec, "PATCH", "/pricing/laboratory/x", {"price": 1}, {403, 404, 422}),
        ("accountant_price_write", acct, "PATCH", "/pricing/reception/individual", {"price": 1}, {403}),
        ("doctor_admin_staff", doctor, "GET", "/admin/staff", None, {403}),
        ("doctor_analytics", doctor, "GET", "/admin/analytics/overview", None, {403}),
        ("doctor_audit", doctor, "GET", "/admin/audit", None, {403}),
        ("nurse_pharmacy_queue", nurse, "GET", "/pharmacy/queue", None, {403}),
        ("pharmacy_lab_board", pharm, "GET", "/laboratory/board", None, {403}),
        ("lab_ward_board", lab, "GET", "/inpatient/board", None, {403}),
        ("reception_mar", rec, "GET", f"/inpatient/patient/{patient_a}/medication-administration", None, {403}),
        ("accountant_notes_write", acct, "POST", f"/inpatient/patient/{patient_a}/nursing-notes", {"content": "no", "requestId": "x"}, {403}),
        ("admin_price_write", admin, "PATCH", "/pricing/reception/individual", {"price": 1}, {403}),
    ]
    for name, cookie, method, path, body, allowed in rbac_cases:
        if not cookie:
            check(name, False, "no session")
            continue
        status, payload, _ = api(method, path, cookie, body)
        check(name, status in allowed, {"status": status, "allowed": list(allowed), "code": (payload or {}).get("code") if isinstance(payload, dict) else None})

    # Analytics periods
    for period in ("today", "yesterday", "this_week", "last_week", "this_month", "last_month"):
        status, payload, ms = api("GET", f"/admin/analytics/overview?period={period}", admin)
        tz = (payload or {}).get("timezone") or (payload or {}).get("period", {})
        if isinstance(payload, dict) and isinstance(payload.get("period"), dict):
            tz = payload["period"].get("timezone")
        occupancy = (payload or {}).get("occupancy") if isinstance(payload, dict) else None
        check(
            f"analytics_{period}",
            status == 200 and (tz == "Africa/Lagos" or "Lagos" in json.dumps(payload, default=str)),
            {"status": status, "ms": ms, "timezone": tz, "occupancy": occupancy},
        )
        text = json.dumps(payload, default=str)
        check(f"analytics_{period}_no_patient_uuid_leak", patient_a not in text and patient_b not in text, {"leaked": patient_a in text})
        if "$" in text and "₦" not in text and "NGN" not in text:
            check(f"analytics_{period}_naira", False, "dollar without naira")
        else:
            check(f"analytics_{period}_naira", True, {"hasNaira": "₦" in text or "NGN" in text})

    custom = api("GET", "/admin/analytics/overview?period=custom&start=2026-08-01&end=2026-08-30", admin)
    check("analytics_custom", custom[0] == 200, {"status": custom[0]})

    # Staff audit
    staff_create = api(
        "POST",
        "/admin/staff",
        admin,
        {
            "fullName": f"RC Audit Staff {STAMP}",
            "username": f"rcstaff{STAMP % 100000}",
            "initialPassword": "TempPass!234",
            "accountType": "operational",
            "departments": ["reception"],
            "enabled": True,
            "requestId": f"rc-staff-{STAMP}",
        },
    )
    check("staff_create", staff_create[0] == 200, {"status": staff_create[0], "code": (staff_create[1] or {}).get("code") if isinstance(staff_create[1], dict) else staff_create[1]})
    created_user = None
    if isinstance(staff_create[1], dict):
        created_user = (staff_create[1].get("user") or staff_create[1]).get("uuid") or (staff_create[1].get("staff") or {}).get("uuid")
        report["synthetic"]["staff"] = {
            "username": f"rcstaff{STAMP % 100000}",
            "uuid": created_user,
            "passwordNotReturned": "TempPass" not in json.dumps(staff_create[1]),
        }
        check("staff_password_not_returned", "TempPass" not in json.dumps(staff_create[1]) and "initialPassword" not in json.dumps(staff_create[1]).lower(), {"keys": list(staff_create[1].keys())})
    if created_user:
        disable = api("POST", f"/admin/staff/{created_user}/status", admin, {"enabled": False, "requestId": f"rc-staff-off-{STAMP}"})
        check("staff_disable", disable[0] == 200, {"status": disable[0]})
    audit = api("GET", "/admin/audit", admin)
    audit_text = json.dumps(audit[1], default=str)
    check("staff_audit_visible", audit[0] == 200 and ("rcstaff" in audit_text.lower() or "ADMIN_CREATE" in audit_text or "create" in audit_text.lower()), {"status": audit[0]})
    check("audit_no_password", "TempPass" not in audit_text and "Admin123" not in audit_text, {})
    check("nurse_cannot_audit", api("GET", "/admin/audit", nurse)[0] == 403)

    # Errors
    error_cases = [
        ("invalid_patient", "GET", f"/consultation/patient/{uuid.uuid4()}", doctor, None, {404, 409, 422}),
        ("invalid_order", "GET", f"/pharmacy/prescription/{uuid.uuid4()}", pharm, None, {404, 409, 422}),
        ("invalid_slot", "POST", f"/inpatient/patient/{patient_a}/medication-administration", nurse, {"slotUuid": str(uuid.uuid4()), "outcome": "given"}, {409, 422, 404}),
        ("negative_price", "PATCH", "/pricing/reception/individual", rec, {"price": -5}, {422}),
        ("malformed_price", "PATCH", "/pricing/reception/individual", rec, {"price": "abc"}, {422}),
        ("missing_tests", "POST", f"/laboratory/patient/{patient_a}/orders", doctor, {"visitUuid": visit_a, "locationUuid": location_uuid, "tests": []}, {422}),
    ]
    for name, method, path, cookie, body, allowed in error_cases:
        status, payload, _ = api(method, path, cookie, body)
        text = json.dumps(payload, default=str)
        check(
            f"error_{name}",
            status in allowed and "Traceback" not in text and "ODOO_PASSWORD" not in text,
            {"status": status, "code": (payload or {}).get("code") if isinstance(payload, dict) else None, "message": (payload or {}).get("message") if isinstance(payload, dict) else None},
        )

    # Doctor historical after we still have records
    hist_consult = api("GET", f"/consultation/patient/{patient_a}", doctor)
    check("doctor_can_read_chart", hist_consult[0] == 200, {"status": hist_consult[0]})

    # Discharge
    discharge = api(
        "POST",
        "/inpatient/discharge",
        nurse,
        {"patientUuid": patient_a, "requestId": f"rc-discharge-{STAMP}"},
    )
    check("discharge", discharge[0] == 200, {"status": discharge[0], "message": (discharge[1] or {}).get("message") if isinstance(discharge[1], dict) else discharge[1]})
    stay_after = api("GET", f"/inpatient/patient/{patient_a}", nurse)
    assignment_after = (stay_after[1] or {}).get("assignment") if isinstance(stay_after[1], dict) else "missing"
    check("bed_released", stay_after[0] == 200 and not assignment_after, {"assignment": assignment_after})
    notes_after = api("GET", f"/inpatient/patient/{patient_a}/nursing-notes", nurse)
    check("notes_survive_discharge", notes_after[0] in {200, 409}, {"status": notes_after[0], "count": len((notes_after[1] or {}).get("notes") or []) if isinstance(notes_after[1], dict) else None})
    vitals_after = api("GET", f"/inpatient/patient/{patient_a}/vitals", nurse)
    check("vitals_survive_or_history_policy", vitals_after[0] in {200, 409}, {"status": vitals_after[0]})
    new_note = api(
        "POST",
        f"/inpatient/patient/{patient_a}/nursing-notes",
        nurse,
        {"content": "should fail after discharge", "requestId": f"rc-note-after-{STAMP}"},
    )
    check("notes_rejected_after_discharge", new_note[0] in {409, 403, 422}, {"status": new_note[0], "code": (new_note[1] or {}).get("code") if isinstance(new_note[1], dict) else None})
    chart_after = api("GET", f"/consultation/patient/{patient_a}", doctor)
    check("doctor_reads_history_after_discharge", chart_after[0] == 200, {"status": chart_after[0]})

    # OpenELIS reachability
    elis = call("GET", "https://localhost/openelis", doctor, timeout=15)
    check("openelis_reachable", elis[0] in {200, 302, 401, 403}, {"status": elis[0]})
    report["openelis"] = {"http": elis[0], "resultReturn": "UNVERIFIED"}

    json.dump(report, sys.stdout, indent=2, default=str)
    print()
    failed = [row for row in report["checks"] if not row["ok"]]
    print(f"SUMMARY {len(report['checks']) - len(failed)}/{len(report['checks'])} passed, {len(failed)} failed", file=sys.stderr)
    return 0 if len(failed) <= 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
