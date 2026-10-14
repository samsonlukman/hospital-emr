#!/usr/bin/env python3
"""Continue live MAR verification after the visit-representation fix."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import time
from pathlib import Path

_HELPER = Path(__file__).resolve().parent / "verify-mar-ipd-slots.py"
_SPEC = importlib.util.spec_from_file_location("verify_mar_ipd_slots", _HELPER)
base = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(base)

base.STAMP = int(time.time())
PA = "8c14a0dd-d509-4a0d-afcd-251b76fc1b5e"
IPD_A = "52364c0a-807e-4d63-b52c-193c3141aa86"
report = base.report
check = base.check


def main() -> int:
    users = {role: base.login(role) for role in (
        "reception.abikan", "doctor.abikan", "nurse.abikan", "lab.abikan",
        "pharmacy.abikan", "accountant.abikan", "admin.abikan",
    )}
    rec, doctor, nurse = users["reception.abikan"], users["doctor.abikan"], users["nurse.abikan"]
    names = base.config_names(doctor)
    provider = base.provider_uuid(doctor)
    meta_status, meta, _ = base.api("GET", "/registration/metadata", rec)
    visit_types = (meta or {}).get("visitTypes") or []
    opd = next((row for row in visit_types if row.get("name") == "OPD"), {})
    locations = (meta or {}).get("locations") or (meta or {}).get("loginLocations") or []
    location = next((row for row in locations if row.get("name") == "OPD-1"), locations[0] if locations else {})
    location_uuid = (location or {}).get("uuid") or ""

    started = time.perf_counter()
    st, sched, sched_ms = base.api("POST", f"/inpatient/patient/{PA}/medication-schedule", doctor, {})
    slot_ms = round((time.perf_counter() - started) * 1000)
    check(
        "schedule_existing_a",
        st == 200 and bool((sched or {}).get("createdOrderUuids") or (sched or {}).get("alreadyScheduledOrderUuids")),
        {"status": st, "body": sched, "ms": sched_ms},
    )
    retry = base.api("POST", f"/inpatient/patient/{PA}/medication-schedule", doctor, {})
    check(
        "retry_idempotent",
        retry[0] == 200 and not (retry[1] or {}).get("createdOrderUuids") and (retry[1] or {}).get("alreadyScheduledOrderUuids"),
        {"status": retry[0], "body": retry[1]},
    )

    mar_a = base.api("GET", f"/inpatient/patient/{PA}/medication-administration", nurse)
    slots_a = base.slots_from(mar_a[1])
    check("mar_slots_a", mar_a[0] == 200 and len(slots_a) >= 1, {"status": mar_a[0], "count": len(slots_a), "orders": (mar_a[1] or {}).get("orders")})
    order = base.latest_ipd_order(doctor, PA)
    check("openmrs_order", bool(order.get("uuid")), {"order": order.get("orderNumber"), "uuid": order.get("uuid")})
    report["workflow"] = {"order": order, "schedule": sched, "slots": slots_a}
    report["performance"] = {"scheduleCreationMs": sched_ms, "slotAvailabilityMs": slot_ms, "asynchronous": False}

    if slots_a:
        first = slots_a[0]
        given = next((s for s in slots_a if s.get("status") == "SCHEDULED" and (s.get("timing") or {}).get("canAdministerNormally")), first)
        admin = base.api(
            "POST",
            f"/inpatient/patient/{PA}/medication-administration",
            nurse,
            {"slotUuid": given["uuid"], "outcome": "given", "reason": ""},
        )
        check("eligible_or_duplicate", admin[0] == 200, {"status": admin[0], "code": (admin[1] or {}).get("code"), "dup": (admin[1] or {}).get("duplicate")})
        saved = ((admin[1] or {}).get("slot") or {})
        saved_admin = saved.get("administration") or {}
        check(
            "scheduled_time_unchanged",
            saved.get("scheduledTime") == given.get("scheduledTime") and bool(saved_admin.get("actualTime")),
            {"scheduled": given.get("scheduledTime"), "savedScheduled": saved.get("scheduledTime"), "actual": saved_admin.get("actualTime")},
        )
        future = next((s for s in slots_a if s.get("uuid") != given.get("uuid") and s.get("status") == "SCHEDULED"), None)
        if future:
            early = base.api(
                "POST",
                f"/inpatient/patient/{PA}/medication-administration",
                nurse,
                {"slotUuid": future["uuid"], "outcome": "given", "reason": ""},
            )
            check(
                "future_409",
                early[0] == 409 and (early[1] or {}).get("code") == "outside_administration_window",
                {"status": early[0], "code": (early[1] or {}).get("code")},
            )
            need_reason = base.api(
                "POST",
                f"/inpatient/patient/{PA}/medication-administration",
                nurse,
                {"slotUuid": future["uuid"], "outcome": "given", "reason": "", "outsideWindow": True},
            )
            check(
                "reason_required",
                need_reason[0] == 422 and (need_reason[1] or {}).get("code") == "outside_window_reason_required",
                {"status": need_reason[0], "code": (need_reason[1] or {}).get("code")},
            )
            client_time = base.api(
                "POST",
                f"/inpatient/patient/{PA}/medication-administration",
                nurse,
                {"slotUuid": future["uuid"], "outcome": "given", "reason": "x", "administeredDateTime": 1},
            )
            check(
                "server_fields_only",
                client_time[0] == 422 and (client_time[1] or {}).get("code") == "server_fields_only",
                {"status": client_time[0], "code": (client_time[1] or {}).get("code")},
            )

    patient_c = base.register(rec, "MARFIX", f"CHARLIE{base.STAMP % 100000}")
    visit_c = base.start_opd(rec, patient_c, opd.get("uuid") or "")
    bed_c = base.admit_and_assign(doctor, nurse, patient_c, visit_c, location_uuid)
    ipd_c = base.active_ipd_visit(doctor, patient_c)
    check("charlie_ipd", bool(ipd_c), {"visit": ipd_c, "bed": bed_c})
    order_st, _, order_ms, _ = base.prescribe(doctor, patient_c, ipd_c, location_uuid, provider, names, 1, 1)
    check("charlie_order", order_st == 200, {"status": order_st, "ms": order_ms})
    created_started = time.perf_counter()
    st, created, created_ms = base.api("POST", f"/inpatient/patient/{patient_c}/medication-schedule", doctor, {})
    created_slot_ms = round((time.perf_counter() - created_started) * 1000)
    check(
        "charlie_new_order_creates_schedule",
        st == 200 and bool((created or {}).get("createdOrderUuids") or (created or {}).get("alreadyScheduledOrderUuids")),
        {"status": st, "body": created, "ms": created_ms},
    )
    mar_c = base.api("GET", f"/inpatient/patient/{patient_c}/medication-administration", nurse)
    slots_c = base.slots_from(mar_c[1])
    check("charlie_mar_slot", mar_c[0] == 200 and len(slots_c) == 1, {"status": mar_c[0], "slots": slots_c})
    report["synthetic"]["charlie"] = {"patient": patient_c, "visit": ipd_c, "schedule": created, "slots": slots_c}
    report["performance"]["newOrderToSlotMs"] = created_slot_ms
    report["performance"]["newOrderCreationMs"] = order_ms

    if slots_a and slots_c:
        cross = base.api(
            "POST",
            f"/inpatient/patient/{PA}/medication-administration",
            nurse,
            {"slotUuid": slots_c[0]["uuid"], "outcome": "given", "reason": ""},
        )
        check(
            "patient_isolation",
            cross[0] == 409 and (cross[1] or {}).get("code") in {"slot_mismatch", "slot_patient_mismatch"},
            {"status": cross[0], "code": (cross[1] or {}).get("code")},
        )
        for role, cookie in (
            ("doctor", users["doctor.abikan"]),
            ("lab", users["lab.abikan"]),
            ("pharmacy", users["pharmacy.abikan"]),
            ("accountant", users["accountant.abikan"]),
            ("admin", users["admin.abikan"]),
        ):
            status, body, _ = base.api(
                "POST",
                f"/inpatient/patient/{patient_c}/medication-administration",
                cookie,
                {"slotUuid": slots_c[0]["uuid"], "outcome": "given", "reason": ""},
            )
            check(f"rbac_{role}", status == 403, {"status": status, "code": (body or {}).get("code")})
        unauth = base.api(
            "POST",
            f"/inpatient/patient/{patient_c}/medication-administration",
            None,
            {"slotUuid": slots_c[0]["uuid"], "outcome": "given", "reason": ""},
        )
        check("rbac_unauthenticated", unauth[0] == 401, {"status": unauth[0]})
        check("nurse_read", base.api("GET", f"/inpatient/patient/{patient_c}/medication-administration", nurse)[0] == 200)
        check("doctor_read", base.api("GET", f"/inpatient/patient/{patient_c}/medication-administration", doctor)[0] == 200)

    subprocess.run(["docker", "restart", "bahmni-standard-abikan-api-1"], check=True, capture_output=True)
    time.sleep(4)
    after_restart = base.api("POST", f"/inpatient/patient/{PA}/medication-schedule", doctor, {})
    mar_after = base.api("GET", f"/inpatient/patient/{PA}/medication-administration", nurse)
    slots_after = base.slots_from(mar_after[1])
    check(
        "restart_no_duplicate",
        after_restart[0] == 200
        and not (after_restart[1] or {}).get("createdOrderUuids")
        and len(slots_after) == len(slots_a),
        {"status": after_restart[0], "body": after_restart[1], "before": len(slots_a), "after": len(slots_after)},
    )

    discharged = base.api("POST", "/inpatient/discharge", nurse, {"patientUuid": patient_c, "requestId": f"marfix-dc-c-{base.STAMP}"})
    check("discharge_c", discharged[0] == 200, {"status": discharged[0]})
    no_new = base.api("POST", f"/inpatient/patient/{patient_c}/medication-schedule", doctor, {})
    check("no_schedule_after_discharge", no_new[0] == 409 and (no_new[1] or {}).get("code") == "not_admitted", {"status": no_new[0], "code": (no_new[1] or {}).get("code")})
    hist = base.api("GET", f"/inpatient/patient/{patient_c}/medication-administration?visitUuid={ipd_c}", nurse)
    check("historical_read", hist[0] == 200, {"status": hist[0], "orders": len((hist[1] or {}).get("orders") or [])})

    e2e = base.api("GET", f"/inpatient/patient/{base.E2E}/medication-administration", nurse)
    check("e2e_mar", e2e[0] == 200 and len((e2e[1] or {}).get("orders") or []) >= 1, {"orders": len((e2e[1] or {}).get("orders") or [])})
    notes = base.api("GET", f"/inpatient/patient/{PA}/nursing-notes", nurse)
    check("notes_still_readable", notes[0] == 200, {"status": notes[0], "count": len((notes[1] or {}).get("notes") or [])})
    vitals = base.api("GET", f"/inpatient/patient/{PA}/vitals", nurse)
    check("vitals_still_readable", vitals[0] == 200, {"status": vitals[0], "count": len((vitals[1] or {}).get("readings") or [])})

    failed = [row for row in report["checks"] if not row["ok"]]
    print(json.dumps({"passed": len(report["checks"]) - len(failed), "failed": failed, "performance": report.get("performance"), "workflow": report.get("workflow"), "charlie": report.get("synthetic")}, indent=2, default=str))
    out = Path(__file__).resolve().parent / f"verify-mar-ipd-slots-followup-{base.STAMP}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print("wrote", out)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
