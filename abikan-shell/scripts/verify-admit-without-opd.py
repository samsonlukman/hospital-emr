#!/usr/bin/env python3
"""Live UAT: doctor can admit without an open OPD visit."""

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
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
CTX = ssl._create_unverified_context()
STAMP = int(time.time())
ADMISSION = "d3785931-5e07-11ef-8f7c-0242ac120002"
CONSULT = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
OPD_TYPE = "54f43754-c6ce-4472-890e-0f28acaeaea6"
IPD_TYPE = "b7494a80-fdf9-49bb-bb40-396c47b40343"
MP_CONCEPT = "32AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CETIRIZINE = "7e0766e1-b679-4eb3-ab93-d63910ad6eb4"
FLEXIBLE = "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions"
PROTECTED = {"ABC200016", "ABC200021"}
report: dict[str, object] = {"stamp": STAMP, "checks": [], "failures": [], "patients": {}, "objects": {}}


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
    return "; ".join(f"{c.name}={c.value}" for c in jar)


def call(method: str, url: str, cookie: str, body: dict | None = None):
    headers = {"Accept": "application/json", "Cookie": cookie}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90, context=CTX if url.startswith("https") else None) as response:
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
    return call(method, f"{API}{path}", cookie, body)


def omrs(method: str, path: str, cookie: str, body: dict | None = None):
    return call(method, f"{BASE}{path}", cookie, body)


def check(name: str, ok: bool, detail: object = None) -> bool:
    row = {"name": name, "ok": bool(ok), "detail": detail}
    report["checks"].append(row)
    if not ok:
        report["failures"].append(row)
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:500])
    return bool(ok)


def visits(cookie: str, patient: str):
    status, body = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/visit?patient={patient}&includeInactive=true"
        "&v=custom:(uuid,startDatetime,stopDatetime,visitType:(name,uuid),encounters:(uuid,encounterType:(name,uuid),encounterDatetime))",
        cookie,
    )
    rows = (body or {}).get("results") if isinstance(body, dict) else []
    return status, [row for row in rows or [] if isinstance(row, dict)]


def open_of_type(rows: list[dict], name: str) -> list[dict]:
    found = []
    for row in rows:
        visit_type = ((row.get("visitType") or {}).get("name") or "").upper()
        if visit_type == name.upper() and not row.get("stopDatetime"):
            found.append(row)
    return found


def register(rec: str, family: str) -> dict:
    status, created = api(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "UATFIX",
            "familyName": family,
            "gender": "F",
            "birthdate": "1992-04-11",
            "confirmDuplicate": True,
        },
    )
    patient = (created or {}).get("uuid") if isinstance(created, dict) else None
    mrn = str((created or {}).get("identifier") or "")
    check(f"register_{family}", status == 200 and bool(patient) and mrn not in PROTECTED, {"uuid": patient, "mrn": mrn})
    return {"uuid": patient, "mrn": mrn}


def first_free_bed(nurse: str) -> dict | None:
    status, board = api("GET", "/inpatient/board", nurse)
    if not isinstance(board, dict):
        return None
    for area in board.get("areas") or []:
        for row in area.get("beds") or []:
            if row.get("status") == "AVAILABLE" and not row.get("patientUuid"):
                return row
    return None


def provider_uuid(cookie: str) -> str:
    status, session = omrs("GET", "/openmrs/ws/rest/v1/session", cookie)
    user = (session or {}).get("user") or {}
    status, providers = omrs("GET", f"/openmrs/ws/rest/v1/provider?user={user.get('uuid')}&v=custom:(uuid,retired)", cookie)
    for row in (providers or {}).get("results") or []:
        if row.get("uuid") and not row.get("retired"):
            return str(row["uuid"])
    return ""


def main() -> int:
    rec = login("reception.abikan")
    doctor = login("doctor.abikan")
    nurse = login("nurse.abikan")
    status, meta = api("GET", "/registration/metadata", rec)
    types = (meta or {}).get("visitTypes") if isinstance(meta, dict) else []
    opd = next((row for row in types or [] if str(row.get("name") or "") == "OPD"), None)
    loc = ((opd or {}).get("locations") or [{}])[0].get("uuid") if opd else ""
    check("metadata", status == 200 and bool(opd) and bool(loc), {"status": status})
    if not opd:
        return 1

    no_opd = register(rec, f"ADMITNO{STAMP % 100000}")
    with_opd = register(rec, f"ADMITOP{STAMP % 100000}")
    report["patients"] = {"noOpd": no_opd, "withOpd": with_opd}
    if not no_opd.get("uuid") or not with_opd.get("uuid"):
        return 1

    status, before = visits(doctor, no_opd["uuid"])
    check("no_opd_patient_has_no_open_opd", status == 200 and not open_of_type(before, "OPD"), {"visits": len(before)})

    rec_denied, rec_body = api(
        "POST",
        f"/inpatient/patient/{no_opd['uuid']}/admit-decision",
        rec,
        {"locationUuid": loc},
    )
    check("reception_cannot_admit", rec_denied == 403, {"status": rec_denied, "code": (rec_body or {}).get("code") if isinstance(rec_body, dict) else rec_body})

    admit1, body1 = api(
        "POST",
        f"/inpatient/patient/{no_opd['uuid']}/admit-decision",
        doctor,
        {"locationUuid": loc},
    )
    check(
        "admit_without_opd",
        admit1 == 200
        and isinstance(body1, dict)
        and body1.get("awaiting")
        and (body1.get("visitUuid") or "")
        and "Start an open visit" not in str(body1.get("message") or ""),
        {"status": admit1, "body": body1},
    )

    status, after1 = visits(doctor, no_opd["uuid"])
    ipd1 = open_of_type(after1, "IPD")
    opd1 = [row for row in after1 if ((row.get("visitType") or {}).get("name") or "").upper() == "OPD"]
    check("no_artificial_opd", status == 200 and len(opd1) == 0 and len(ipd1) == 1, {"opd": len(opd1), "ipd": [row.get("uuid") for row in ipd1]})
    admission_encounters = []
    for visit in ipd1:
        for encounter in visit.get("encounters") or []:
            enc_type = (encounter.get("encounterType") or {})
            if enc_type.get("uuid") == ADMISSION or str(enc_type.get("name") or "").lower() == "admission":
                admission_encounters.append(encounter)
    check("admission_encounter_on_ipd", bool(admission_encounters), {"encounters": admission_encounters})
    report["objects"]["noOpd"] = {
        "patientUuid": no_opd["uuid"],
        "ipdVisitUuid": (ipd1[0].get("uuid") if ipd1 else None),
        "admissionEncounterUuid": (admission_encounters[0].get("uuid") if admission_encounters else None),
        "encounterType": ((admission_encounters[0].get("encounterType") or {}).get("name") if admission_encounters else None),
        "startDatetime": (ipd1[0].get("startDatetime") if ipd1 else None),
    }

    stay1, stay_body = api("GET", f"/inpatient/patient/{no_opd['uuid']}", doctor)
    check(
        "awaiting_bed_before_assignment",
        stay1 == 200 and isinstance(stay_body, dict) and stay_body.get("awaiting") and not stay_body.get("assignment"),
        stay_body if isinstance(stay_body, dict) else {"status": stay1},
    )
    board, board_body = api("GET", "/inpatient/board", nurse)
    awaiting_ids = [row.get("patientUuid") for row in ((board_body or {}).get("awaiting") or [])] if isinstance(board_body, dict) else []
    check("nursing_sees_awaiting", board == 200 and no_opd["uuid"] in awaiting_ids, {"awaiting": awaiting_ids})

    blocked, blocked_body = api(
        "POST",
        f"/laboratory/patient/{no_opd['uuid']}/orders",
        doctor,
        {"visitUuid": (ipd1[0].get("uuid") if ipd1 else ""), "locationUuid": loc, "tests": [{"conceptUuid": MP_CONCEPT}], "requestId": f"admit-lab-early-{STAMP}"},
    )
    check("orders_blocked_while_awaiting_bed", blocked == 409 and isinstance(blocked_body, dict) and blocked_body.get("code") == "awaiting_bed", {"status": blocked, "body": blocked_body})

    start_opd, start_body = api(
        "POST",
        f"/registration/patient/{with_opd['uuid']}/visit",
        rec,
        {"visitTypeUuid": opd.get("uuid"), "locationUuid": loc},
    )
    opd_uuid = (start_body or {}).get("uuid") if isinstance(start_body, dict) else None
    check("start_opd_for_second_patient", start_opd == 200 and bool(opd_uuid), {"status": start_opd, "uuid": opd_uuid})

    consult_status, consult = omrs(
        "POST",
        "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
        doctor,
        {
            "patientUuid": with_opd["uuid"],
            "visitUuid": opd_uuid,
            "encounterTypeUuid": CONSULT,
            "encounterDateTime": time.strftime("%Y-%m-%dT%H:%M:%S.000+0000", time.gmtime()),
            "locationUuid": loc,
            "providers": [{"uuid": provider_uuid(doctor)}],
            "observations": [
                {
                    "concept": {"uuid": "d37294c5-5e07-11ef-8f7c-0242ac120002", "name": "Consultation Note", "dataType": "Text"},
                    "value": "UATFIX OPD note before admission.",
                    "voided": False,
                }
            ],
            "bahmniDiagnoses": [],
            "orders": [],
            "drugOrders": [],
        },
    )
    check("opd_consultation_documented", consult_status in {200, 201}, {"status": consult_status, "encounter": (consult or {}).get("encounterUuid")})

    admit2, body2 = api(
        "POST",
        f"/inpatient/patient/{with_opd['uuid']}/admit-decision",
        doctor,
        {"visitUuid": opd_uuid, "locationUuid": loc},
    )
    check("admit_with_existing_opd", admit2 == 200 and isinstance(body2, dict) and body2.get("awaiting"), {"status": admit2, "body": body2})
    status, after2 = visits(doctor, with_opd["uuid"])
    ipd2 = open_of_type(after2, "IPD")
    open_opd2 = open_of_type(after2, "OPD")
    ended_opd = [
        row
        for row in after2
        if ((row.get("visitType") or {}).get("name") or "").upper() == "OPD" and row.get("stopDatetime")
    ]
    check("opd_ended_one_ipd", status == 200 and len(ipd2) == 1 and not open_opd2 and bool(ended_opd), {"ipd": [row.get("uuid") for row in ipd2], "openOpd": len(open_opd2), "endedOpd": [(row.get("uuid"), row.get("stopDatetime")) for row in ended_opd]})
    note_kept = False
    for visit in ended_opd:
        if any((enc.get("encounterType") or {}).get("uuid") == CONSULT for enc in visit.get("encounters") or []):
            note_kept = True
    check("opd_documentation_kept", note_kept or consult_status in {200, 201}, {"endedOpd": [row.get("uuid") for row in ended_opd]})
    report["objects"]["withOpd"] = {
        "patientUuid": with_opd["uuid"],
        "endedOpdVisitUuid": (ended_opd[0].get("uuid") if ended_opd else opd_uuid),
        "ipdVisitUuid": (ipd2[0].get("uuid") if ipd2 else None),
    }

    bed = first_free_bed(nurse)
    assign, assign_body = (
        api(
            "POST",
            "/inpatient/assign",
            nurse,
            {
                "patientUuid": no_opd["uuid"],
                "bedUuid": (bed or {}).get("bedUuid"),
                "bedId": (bed or {}).get("bedId"),
                "requestId": f"admit-assign-{STAMP}",
            },
        )
        if bed
        else (0, {"error": "no_free_bed"})
    )
    check("assign_bed_reuses_admission", assign == 200 and isinstance(assign_body, dict) and (assign_body.get("visitUuid") == (ipd1[0].get("uuid") if ipd1 else None) or bool(assign_body.get("assignment"))), {"status": assign, "body": assign_body, "bed": (bed or {}).get("bedNumber")})
    status, after_assign = visits(doctor, no_opd["uuid"])
    ipd_after = open_of_type(after_assign, "IPD")
    check("same_ipd_after_bed", len(ipd_after) == 1 and ipd_after[0].get("uuid") == (ipd1[0].get("uuid") if ipd1 else None), {"ipd": [row.get("uuid") for row in ipd_after]})

    stay2, stay2_body = api("GET", f"/inpatient/patient/{no_opd['uuid']}", doctor)
    ipd_visit = (stay2_body or {}).get("visitUuid") if isinstance(stay2_body, dict) else ""
    check("occupied_stay", stay2 == 200 and isinstance(stay2_body, dict) and stay2_body.get("assignment") and ipd_visit, stay2_body if isinstance(stay2_body, dict) else {"status": stay2})

    names_status, cfg = omrs("GET", "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders", doctor)
    def first(key: str, *preferred: str) -> str:
        rows = (cfg or {}).get(key) or []
        names = [str(row.get("name") or "") for row in rows if row.get("name")]
        for name in preferred:
            if name in names:
                return name
        return names[0] if names else ""
    names = {
        "tablet": first("doseUnits", "Tablet", "Tablet(s)"),
        "oral": first("routes", "Oral"),
        "once": first("frequencies", "Once a day"),
        "days": first("durationUnits", "Day(s)", "Days", "Day"),
        "qty": first("dispensingUnits", "Tablet", "Tablet(s)") or first("doseUnits", "Tablet"),
    }
    rx, rx_body = omrs(
        "POST",
        "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
        doctor,
        {
            "patientUuid": no_opd["uuid"],
            "visitUuid": ipd_visit,
            "visitType": "IPD",
            "encounterTypeUuid": CONSULT,
            "locationUuid": loc,
            "providers": [{"uuid": provider_uuid(doctor)}],
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
                        "quantity": 1,
                        "quantityUnits": names["qty"],
                        "numberOfRefills": 0,
                    },
                    "duration": 1,
                    "durationUnits": names["days"],
                }
            ],
        },
    )
    check("ipd_prescription", names_status == 200 and rx in {200, 201} and (rx_body or {}).get("encounterUuid"), {"status": rx, "encounter": (rx_body or {}).get("encounterUuid")})
    sched, sched_body = api("POST", f"/inpatient/patient/{no_opd['uuid']}/medication-schedule", doctor, {})
    check(
        "mar_schedule",
        sched == 200 and bool((sched_body or {}).get("createdOrderUuids") or (sched_body or {}).get("alreadyScheduledOrderUuids")),
        sched_body,
    )
    status, after_rx = visits(doctor, no_opd["uuid"])
    check("prescription_did_not_create_opd", not open_of_type(after_rx, "OPD") and len(open_of_type(after_rx, "IPD")) == 1, {"ipd": [row.get("uuid") for row in open_of_type(after_rx, "IPD")]})

    lab, lab_body = api(
        "POST",
        f"/laboratory/patient/{no_opd['uuid']}/orders",
        doctor,
        {
            "visitUuid": "",
            "locationUuid": loc,
            "tests": [{"conceptUuid": MP_CONCEPT}],
            "requestId": f"admit-lab-{STAMP}",
        },
    )
    lab_visit = ((lab_body or {}).get("orders") or [{}])[0].get("visitUuid") if isinstance(lab_body, dict) else None
    check(
        "ipd_lab_order",
        lab == 200 and (lab_visit == ipd_visit or (isinstance(lab_body, dict) and lab_body.get("visitUuid") == ipd_visit) or bool(lab_body)),
        {"status": lab, "body": lab_body},
    )
    rad, rad_body = api(
        "POST",
        f"/radiology/patient/{no_opd['uuid']}/orders",
        doctor,
        {
            "visitUuid": "",
            "locationUuid": loc,
            "services": [{"serviceId": "xr-chest"}],
            "requestId": f"admit-rad-{STAMP}",
        },
    )
    rad_visit = (rad_body or {}).get("visitUuid") if isinstance(rad_body, dict) else None
    check("ipd_radiology_order", rad == 200 and (rad_visit == ipd_visit or bool(rad_body)), {"status": rad, "body": rad_body})
    status, after_orders = visits(doctor, no_opd["uuid"])
    check("orders_did_not_create_opd", not open_of_type(after_orders, "OPD"), {"openOpd": len(open_of_type(after_orders, "OPD"))})

    cross, cross_body = api(
        "POST",
        f"/inpatient/patient/{no_opd['uuid']}/admit-decision",
        doctor,
        {"visitUuid": (ipd2[0].get("uuid") if ipd2 else ""), "locationUuid": loc},
    )
    check(
        "cannot_use_other_patient_visit",
        cross in {409, 422} and isinstance(cross_body, dict) and cross_body.get("code") in {"wrong_patient", "already_admitted"},
        {"status": cross, "body": cross_body},
    )

    ctx, ctx_body = api("GET", f"/registration/patient/{with_opd['uuid']}/visit", rec)
    check(
        "create_visit_no_card_after_admit",
        ctx == 200
        and isinstance(ctx_body, dict)
        and "cards" not in ctx_body
        and "canCreateCharge" not in ctx_body
        and ctx_body.get("code") == "admission_in_progress",
        {"status": ctx, "keys": sorted(ctx_body.keys()) if isinstance(ctx_body, dict) else ctx, "code": (ctx_body or {}).get("code") if isinstance(ctx_body, dict) else None},
    )
    dup, dup_body = api(
        "POST",
        f"/registration/patient/{with_opd['uuid']}/visit",
        rec,
        {"visitTypeUuid": opd.get("uuid"), "locationUuid": loc},
    )
    check(
        "create_visit_blocked_for_admitted",
        dup == 409 and isinstance(dup_body, dict) and dup_body.get("code") in {"admission_in_progress", "visit_already_open"},
        {"status": dup, "body": dup_body},
    )

    returning = register(rec, f"ADMITRV{STAMP % 100000}")
    if returning.get("uuid"):
        rctx, rctx_body = api("GET", f"/registration/patient/{returning['uuid']}/visit", rec)
        check(
            "create_visit_existing_patient_no_card",
            rctx == 200
            and isinstance(rctx_body, dict)
            and "cards" not in rctx_body
            and "canCreateCharge" not in rctx_body
            and rctx_body.get("canStartVisit") is True,
            {"status": rctx, "keys": sorted(rctx_body.keys()) if isinstance(rctx_body, dict) else rctx},
        )

    path = f"/Users/apple/Hospital EMREMR/abikan-shell/scripts/verify-admit-without-opd-{STAMP}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)
    print("REPORT", path)
    print("failures", len(report["failures"]))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
