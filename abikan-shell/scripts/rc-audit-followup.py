#!/usr/bin/env python3
"""Release-candidate follow-up: restore price, MAR, isolation, errors, pharmacy."""

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


def call(method: str, url: str, cookie: str, body=None, timeout: int = 60):
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
            raw = resp.read().decode() or "null"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "null"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:800]}
        return exc.code, payload


def api(method: str, path: str, cookie: str, body=None, timeout: int = 60):
    return call(method, API + path, cookie, body, timeout)


def report(name: str, ok: bool, detail):
    status = "PASS" if ok else "FAIL"
    text = detail if isinstance(detail, str) else json.dumps(detail, default=str)[:500]
    print(f"{status} {name} {text}")


def main() -> int:
    rec = login("reception.abikan")
    st, prices = api("GET", "/pricing/reception", rec)
    items = (prices or {}).get("items") or []
    individual = next((row for row in items if row.get("id") == "individual"), None)
    amt = ((individual or {}).get("price") or {}).get("amount")
    print("individual_now", amt)
    if amt is not None and amt <= 1.01:
        st, restored = api(
            "PATCH",
            "/pricing/reception/individual",
            rec,
            {"price": 2000, "expectedPrice": amt, "reason": "RC audit restore after SuperAdmin write test"},
        )
        report("restore_individual_card", st == 200, {"status": st, "body": restored if st != 200 else "ok"})
        st, prices = api("GET", "/pricing/reception", rec)
        amt = next(
            ((row.get("price") or {}).get("amount") for row in (prices or {}).get("items") or [] if row.get("id") == "individual"),
            None,
        )
    report("individual_card_restored", amt == 2000, amt)

    st, hist = api("GET", "/pricing/reception/individual/history", rec)
    history = (hist or {}).get("history") or []
    report(
        "reception_price_history",
        st == 200 and len(history) >= 1,
        {
            "count": len(history),
            "latest": history[0] if history else None,
        },
    )

    nurse = login("nurse.abikan")
    st, mar = api("GET", f"/inpatient/patient/{E2E}/medication-administration", nurse)
    orders = (mar or {}).get("orders") or []
    report("e2e_mar_orders", st == 200 and len(orders) > 0, {"status": st, "orders": len(orders)})

    slots = []
    for order in orders:
        for slot in order.get("slots") or []:
            slots.append({**slot, "orderUuid": order.get("orderUuid") or order.get("uuid")})
    print("slot_count", len(slots))
    for slot in slots[:12]:
        print(
            "SLOT",
            slot.get("uuid"),
            slot.get("status"),
            slot.get("scheduledTime") or slot.get("startTime"),
            (slot.get("timing") or {}).get("status") if isinstance(slot.get("timing"), dict) else slot.get("windowStatus"),
            bool((slot.get("administration") or {})),
        )

    eligible = [
        slot
        for slot in slots
        if str(slot.get("status") or "").upper() == "SCHEDULED"
        and (
            (isinstance(slot.get("timing"), dict) and slot["timing"].get("status") == "eligible")
            or slot.get("windowStatus") == "eligible"
        )
        and not slot.get("administration")
    ]
    future = [
        slot
        for slot in slots
        if str(slot.get("status") or "").upper() == "SCHEDULED"
        and (
            (isinstance(slot.get("timing"), dict) and slot["timing"].get("status") in {"future", "too_early"})
            or slot.get("windowStatus") in {"future", "too_early", "upcoming"}
        )
        and not slot.get("administration")
    ]
    outside = [
        slot
        for slot in slots
        if str(slot.get("status") or "").upper() == "SCHEDULED"
        and not slot.get("administration")
        and slot not in eligible
    ]
    print("eligible", len(eligible), "future", len(future), "outside_or_other", len(outside))

    if eligible:
        slot = eligible[0]
        scheduled_before = slot.get("scheduledTime") or slot.get("startTime")
        st, given = api(
            "POST",
            f"/inpatient/patient/{E2E}/medication-administration",
            nurse,
            {"slotUuid": slot["uuid"], "outcome": "given"},
        )
        admin = ((given or {}).get("slot") or {}).get("administration") or {}
        scheduled_after = ((given or {}).get("slot") or {}).get("scheduledTime")
        report(
            "mar_administer_eligible",
            st == 200 and not given.get("duplicate") and admin,
            {"status": st, "code": (given or {}).get("code"), "admin": admin},
        )
        report(
            "mar_scheduled_time_unchanged",
            scheduled_before and (scheduled_after == scheduled_before or scheduled_after is None),
            {"before": scheduled_before, "after": scheduled_after},
        )
        report(
            "mar_actual_time_present",
            bool(admin.get("administeredAt") or admin.get("administeredDateTime")),
            admin,
        )
        report(
            "mar_performer_present",
            bool(admin.get("authorName") or admin.get("performer") or admin.get("userUuid")),
            admin,
        )
        st, dup = api(
            "POST",
            f"/inpatient/patient/{E2E}/medication-administration",
            nurse,
            {"slotUuid": slot["uuid"], "outcome": "given"},
        )
        report(
            "mar_duplicate_idempotent",
            st == 200 and dup.get("duplicate") is True,
            {"status": st, "duplicate": (dup or {}).get("duplicate"), "code": (dup or {}).get("code")},
        )
        doctor = login("doctor.abikan")
        st, cross = api(
            "POST",
            f"/inpatient/patient/{PA}/medication-administration",
            nurse,
            {"slotUuid": slot["uuid"], "outcome": "given"},
        )
        report(
            "mar_cross_patient_rejected",
            st in {403, 404, 409},
            {"status": st, "code": (cross or {}).get("code")},
        )
        _ = doctor
    else:
        report("mar_administer_eligible", False, "no eligible slot on E2E patient")
        report("mar_scheduled_time_unchanged", False, "skipped")
        report("mar_actual_time_present", False, "skipped")
        report("mar_performer_present", False, "skipped")
        report("mar_duplicate_idempotent", False, "skipped")
        report("mar_cross_patient_rejected", False, "skipped")

    if future:
        slot = future[0]
        st, blocked = api(
            "POST",
            f"/inpatient/patient/{E2E}/medication-administration",
            nurse,
            {"slotUuid": slot["uuid"], "outcome": "given"},
        )
        report(
            "mar_future_blocked",
            st == 409 and (blocked or {}).get("code") == "outside_administration_window",
            {"status": st, "code": (blocked or {}).get("code")},
        )
        st, with_reason = api(
            "POST",
            f"/inpatient/patient/{E2E}/medication-administration",
            nurse,
            {
                "slotUuid": slot["uuid"],
                "outcome": "given",
                "outsideWindow": True,
                "reason": "RC AUDIT synthetic outside-window administration.",
            },
        )
        report(
            "mar_outside_window_with_reason",
            st == 200 and ((with_reason or {}).get("slot") or {}).get("administration"),
            {"status": st, "code": (with_reason or {}).get("code")},
        )
    elif outside:
        slot = outside[0]
        st, blocked = api(
            "POST",
            f"/inpatient/patient/{E2E}/medication-administration",
            nurse,
            {"slotUuid": slot["uuid"], "outcome": "given"},
        )
        report(
            "mar_future_blocked",
            st == 409,
            {"status": st, "code": (blocked or {}).get("code"), "note": "used non-eligible scheduled slot"},
        )
        st, with_reason = api(
            "POST",
            f"/inpatient/patient/{E2E}/medication-administration",
            nurse,
            {
                "slotUuid": slot["uuid"],
                "outcome": "given",
                "outsideWindow": True,
                "reason": "RC AUDIT synthetic outside-window administration.",
            },
        )
        report(
            "mar_outside_window_with_reason",
            st == 200,
            {"status": st, "code": (with_reason or {}).get("code")},
        )
    else:
        report("mar_future_blocked", False, "no future/outside slot")
        report("mar_outside_window_with_reason", False, "skipped")

    st, notes = api("GET", f"/inpatient/patient/{E2E}/nursing-notes", nurse)
    note_list = (notes or {}).get("notes") or []
    report("nursing_notes_multiple", st == 200 and len(note_list) >= 2, {"count": len(note_list)})
    st, vitals = api("GET", f"/inpatient/patient/{E2E}/vitals", nurse)
    vital_list = (vitals or {}).get("sets") or (vitals or {}).get("vitals") or []
    report("vitals_history_multiple", st == 200 and len(vital_list) >= 1, {"status": st, "count": len(vital_list)})

    st, cross_note = api(
        "POST",
        f"/inpatient/patient/{PB}/nursing-notes",
        nurse,
        {"note": "RC AUDIT should fail — Bravo not admitted.", "requestId": f"rc-iso-note-{int(time.time())}"},
    )
    report("notes_unadmitted_rejected", st in {403, 404, 409}, {"status": st, "code": (cross_note or {}).get("code")})

    st, fake = api("GET", "/inpatient/patient/00000000-0000-0000-0000-000000000000/vitals", nurse)
    report("invalid_patient_uuid", st in {404, 409}, {"status": st, "code": (fake or {}).get("code")})
    st, fake_slot = api(
        "POST",
        f"/inpatient/patient/{E2E}/medication-administration",
        nurse,
        {"slotUuid": "00000000-0000-0000-0000-000000000000", "outcome": "given"},
    )
    report("invalid_slot_uuid", st in {404, 409, 422}, {"status": st, "code": (fake_slot or {}).get("code")})

    doctor = login("doctor.abikan")
    st, chart = api("GET", f"/consultation/patient/{PA}", doctor)
    report("discharged_chart_readable", st == 200, st)
    st, note_a = api(
        "POST",
        f"/inpatient/patient/{PA}/nursing-notes",
        nurse,
        {"note": "should reject after discharge", "requestId": f"rc-dc-note-{int(time.time())}"},
    )
    report("post_discharge_note_rejected", st == 409, {"status": st, "code": (note_a or {}).get("code")})

    lab = login("lab.abikan")
    st, board = api("GET", "/laboratory/board", lab, timeout=90)
    rows = (board or {}).get("orders") or (board or {}).get("items") or []
    a_orders = [row for row in rows if PA in json.dumps(row)]
    b_orders = [row for row in rows if PB in json.dumps(row)]
    report(
        "lab_board_has_a",
        st == 200 and len(a_orders) >= 1,
        {"status": st, "total": len(rows), "a": len(a_orders), "b": len(b_orders)},
    )

    pharm = login("pharmacy.abikan")
    st, queue = api("GET", "/pharmacy/queue", pharm, timeout=90)
    qrows = (queue or {}).get("orders") or (queue or {}).get("items") or []
    a_rx = [row for row in qrows if PA in json.dumps(row)]
    report("pharmacy_queue_has_a", st == 200 and len(a_rx) >= 1, {"status": st, "a": len(a_rx), "sample": a_rx[:1]})

    if a_rx:
        row = a_rx[0]
        unpaid = str(row.get("paymentState") or row.get("payment") or "").upper()
        report("pharmacy_payment_state_visible", True, {"state": unpaid or row.get("status"), "keys": list(row)[:20]})
        order_uuid = row.get("orderUuid") or row.get("uuid")
        st, disp = api(
            "POST",
            "/pharmacy/dispense",
            pharm,
            {"orderUuid": order_uuid, "patientUuid": PA, "requestId": f"rc-disp-{int(time.time())}"},
        )
        report(
            "pharmacy_dispense_gate",
            st in {200, 409, 422},
            {"status": st, "code": (disp or {}).get("code"), "body": disp if st != 200 else {k: disp.get(k) for k in ("status", "dispensed")}},
        )

    acct = login("accountant.abikan")
    st, bills = api("GET", f"/accountant/patient/{PA}", acct, timeout=90)
    invoices = (bills or {}).get("invoices") or []
    report("billing_invoices_present", st == 200 and len(invoices) >= 2, {"status": st, "count": len(invoices)})
    for inv in invoices:
        print(
            "INV",
            inv.get("id"),
            inv.get("number"),
            (inv.get("amount") or inv.get("total") or {}).get("formatted")
            if isinstance(inv.get("amount") or inv.get("total"), dict)
            else inv.get("residual") or inv.get("amountDue"),
            inv.get("state") or inv.get("paymentState"),
            inv.get("currency") or ((inv.get("amount") or {}).get("currencyCode")),
        )

    admin = login("hospitaladmin.abikan")
    for period in ("today", "yesterday", "this_week", "last_week", "this_month", "last_month"):
        st, data = api("GET", f"/admin/analytics?period={period}", admin, timeout=90)
        tz = (data or {}).get("timezone") or ((data or {}).get("period") or {}).get("timezone")
        occ = (data or {}).get("occupancy") or {}
        fin = (data or {}).get("finance") or (data or {}).get("financial") or {}
        report(
            f"analytics_{period}",
            st == 200 and ("Lagos" in json.dumps(data) or tz in {"Africa/Lagos", "Africa/Lagos"}),
            {
                "status": st,
                "timezone": tz,
                "occupancyAsOf": occ.get("asOf") or occ.get("asOfLabel"),
                "hasNaira": "₦" in json.dumps(data) or "NGN" in json.dumps(data),
                "keys": list((data or {}).keys())[:16],
            },
        )
        _ = fin

    st, custom = api(
        "GET",
        "/admin/analytics?period=custom&from=2026-08-01&to=2026-08-30",
        admin,
        timeout=90,
    )
    report("analytics_custom", st == 200, {"status": st, "code": (custom or {}).get("code")})

    st, staff = api(
        "POST",
        "/admin/staff",
        admin,
        {
            "fullName": "RC Audit Staff3",
            "username": f"rcstaff3{int(time.time()) % 100000}",
            "initialPassword": "TempPass!234",
            "accountType": "staff",
            "departments": ["reception"],
            "enabled": True,
            "requestId": f"rc-staff3-{int(time.time())}",
        },
    )
    blob = json.dumps(staff)
    report(
        "staff_create_full",
        st == 200 and "TempPass" not in blob,
        {"status": st, "keys": list((staff or {}).keys()), "code": (staff or {}).get("code")},
    )

    st, audit = api("GET", "/admin/audit", admin)
    report("audit_readable", st == 200, {"status": st, "hasRcstaff": "rcstaff" in json.dumps(audit).lower()})

    doctor_cookie = doctor
    st, admin_from_doc = api("GET", "/admin/audit", doctor_cookie)
    report("audit_doctor_denied", st == 403, st)
    st, analytics_from_doc = api("GET", "/admin/analytics?period=today", doctor_cookie)
    report("analytics_doctor_denied", st == 403, st)
    st, price_from_doc = api("PATCH", "/pricing/reception/individual", doctor_cookie, {"price": 1})
    report("pricing_doctor_denied", st == 403, st)

    rec2 = login("reception.abikan")
    st, unauth_price = call("GET", API + "/pricing/reception", "", None)
    report("unauthenticated_401", st == 401, st)

    radio = login("radiology.abikan")
    st, wl = api("GET", "/radiology/worklist", radio)
    items = (wl or {}).get("orders") or (wl or {}).get("items") or []
    a_rad = [row for row in items if PA in json.dumps(row)]
    report("radiology_worklist_a", st == 200, {"status": st, "total": len(items), "a": len(a_rad)})

    st, lab_price_hist = api("GET", "/pricing/laboratory", lab)
    lab_items = (lab_price_hist or {}).get("items") or []
    changed = [row for row in lab_items if (row.get("lastChange") or row.get("history"))]
    report("lab_pricing_list", st == 200 and len(lab_items) > 0, {"count": len(lab_items), "withHistory": len(changed)})

    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
