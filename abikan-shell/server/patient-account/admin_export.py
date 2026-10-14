"""Hospital Admin data exports over existing OpenMRS and Odoo sources.

OpenMRS remains the clinical source of truth. Odoo remains the financial
source of truth. This module does not create a second store. Only Hospital
Administration may generate, download, or delete exports.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qs

import accountant as cashier
import admin_analytics as analytics
import admin_audit
import admin_export_formats as formats
import admin_export_store as store
import admin_period as periods
import finance_summary as finance
import hospital_admin as administration
import inpatient_vitals as vitals
import openmrs_sql as clinical_sql
import patient_directory as register
import server as core
from server import ApiError

LOGGER = logging.getLogger(__name__)

EXPORT_FORBIDDEN = "This action requires Hospital Administration."
EXPIRED_MESSAGE = "This export file is no longer available."
MAX_ROWS = 10000
FINANCIAL_DEPARTMENTS = list(finance.REVENUE_DEPARTMENTS)
STAFF_DEPARTMENTS = [row["id"] for row in administration.DEPARTMENTS]
INVOICE_STATUSES = ("posted", "unpaid", "partial", "paid", "reversed")
STAFF_STATUSES = ("all", "active", "disabled")
VISIT_STATUSES = ("all", "open", "closed")
PATIENT_STATUSES = ("all", "alive", "deceased")
PAYMENT_STATE_FILTERS = {
    "unpaid": {"not_paid"},
    "partial": {"partial", "in_payment"},
    "paid": {"paid"},
    "reversed": {"reversed"},
}

DATASETS: dict[str, dict[str, Any]] = {
    "patients": {
        "label": "Patients",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": PATIENT_STATUSES,
        "preferred": ("csv", "xlsx"),
    },
    "visits": {
        "label": "Visits",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": True,
        "statuses": VISIT_STATUSES,
        "preferred": ("csv", "xlsx"),
    },
    "encounters": {
        "label": "Encounters",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": True,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "clinical_records": {
        "label": "Clinical records",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": True,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "laboratory": {
        "label": "Laboratory",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "pharmacy": {
        "label": "Pharmacy",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "radiology": {
        "label": "Radiology",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "admissions": {
        "label": "Admissions",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "discharges": {
        "label": "Discharges",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "nursing_vitals": {
        "label": "Nursing vitals",
        "kind": "clinical",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "invoices": {
        "label": "Invoices",
        "kind": "financial",
        "usesDateRange": True,
        "usesDepartment": True,
        "statuses": INVOICE_STATUSES,
        "preferred": ("csv", "xlsx"),
    },
    "payments": {
        "label": "Payments",
        "kind": "financial",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "outstanding": {
        "label": "Outstanding balances",
        "kind": "financial",
        "usesDateRange": False,
        "usesDepartment": True,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "refunds": {
        "label": "Refunds",
        "kind": "financial",
        "usesDateRange": True,
        "usesDepartment": True,
        "statuses": (),
        "preferred": ("csv", "xlsx"),
    },
    "revenue": {
        "label": "Revenue by department",
        "kind": "financial",
        "usesDateRange": True,
        "usesDepartment": True,
        "statuses": (),
        "preferred": ("csv", "xlsx", "pdf"),
    },
    "accommodation": {
        "label": "Accommodation bills",
        "kind": "financial",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": INVOICE_STATUSES,
        "preferred": ("csv", "xlsx"),
    },
    "accommodation_prices": {
        "label": "Accommodation prices",
        "kind": "financial",
        "usesDateRange": False,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx", "pdf"),
    },
    "staff": {
        "label": "Staff",
        "kind": "staff",
        "usesDateRange": False,
        "usesDepartment": True,
        "statuses": STAFF_STATUSES,
        "preferred": ("csv", "xlsx"),
    },
    "analytics": {
        "label": "Hospital overview",
        "kind": "analytics",
        "usesDateRange": True,
        "usesDepartment": False,
        "statuses": (),
        "preferred": ("csv", "xlsx", "pdf"),
    },
}

DEPARTMENT_ENCOUNTER_TYPES = {
    "Consultation": ("Consultation",),
    "Registration": (),
    "Laboratory": (),
    "Pharmacy": (),
    "Radiology": (),
    "Accommodation": ("ADMISSION", "DISCHARGE"),
}


def require_admin_export(cookie: str) -> dict[str, Any]:
    return administration.require_hospital_admin(cookie)


def catalog(cookie: str) -> dict[str, Any]:
    require_admin_export(cookie)
    store.expire_due_files()
    return {
        "status": "ok",
        "datasets": [
            {
                "id": key,
                "label": spec["label"],
                "kind": spec["kind"],
                "usesDateRange": bool(spec["usesDateRange"]),
                "usesDepartment": bool(spec["usesDepartment"]),
                "departments": _dataset_departments(spec),
                "statuses": [
                    {"id": item, "label": _status_label(item)}
                    for item in spec["statuses"]
                ],
                "preferredFormats": list(spec["preferred"]),
            }
            for key, spec in DATASETS.items()
        ],
        "formats": [
            {"id": item, "label": formats.format_label(item)} for item in formats.FORMATS
        ],
        "periods": [
            {"id": "today", "label": "Today"},
            {"id": "yesterday", "label": "Yesterday"},
            {"id": "this_week", "label": "This week"},
            {"id": "last_week", "label": "Last week"},
            {"id": "this_month", "label": "This month"},
            {"id": "last_month", "label": "Last month"},
            {"id": "custom", "label": "Custom range"},
        ],
        "fileHours": store.EXPORT_TTL_HOURS,
    }


def generate_export(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    actor = require_admin_export(cookie)
    store.expire_due_files()
    request = _parse_request(body)
    spec = DATASETS[request["dataset"]]
    audit_id = admin_audit.start_admin_event(
        actor=actor,
        action="ADMIN_EXPORT_DATA",
        details=_audit_details(request, spec),
        request_id=str(body.get("requestId") or ""),
    )
    export_id = ""
    try:
        columns, rows = _load_rows(request, cookie)
        data = formats.render_export(
            fmt=request["format"],
            title=spec["label"],
            columns=columns,
            rows=rows,
            meta=_file_meta(request, spec),
        )
        filename = _filename(spec["label"], request["format"], request["period_label"])
        export_id = uuid.uuid4().hex
        file_size = store.write_file(export_id, data)
        store.insert_export(
            actor=_actor_row(actor),
            dataset=request["dataset"],
            dataset_label=spec["label"],
            fmt=request["format"],
            department=request["department"],
            department_label=request["department_label"],
            status_filter=request["status"],
            period=request["period"],
            period_label=request["period_label"],
            start_date=request["start_date"],
            end_date=request["end_date"],
            record_count=len(rows),
            file_size=file_size,
            filename=filename,
            content_type=formats.CONTENT_TYPES[request["format"]],
            outcome="success",
            file_status="available",
            expires_at=store.default_expiry(),
            audit_event_id=audit_id,
            export_id=export_id,
        )
        admin_audit.finish_admin_event(
            audit_id,
            outcome="success",
            details={**_audit_details(request, spec), "recordCount": len(rows), "fileSize": file_size},
        )
        LOGGER.info(
            "admin export created dataset=%s format=%s records=%s",
            request["dataset"],
            request["format"],
            len(rows),
        )
        return {
            "status": "ok",
            "export": serialize_export(store.get_export(export_id) or {"export_id": export_id}),
        }
    except ApiError as error:
        _record_failure(actor, request, spec, audit_id, error.code)
        raise
    except Exception as error:
        LOGGER.warning(
            "admin export failed dataset=%s format=%s error=%s",
            request["dataset"],
            request["format"],
            type(error).__name__,
        )
        _record_failure(actor, request, spec, audit_id, "export_failed")
        raise ApiError(500, "export_failed", "The export could not be generated.") from error


def list_history(cookie: str, raw_path: str = "") -> dict[str, Any]:
    require_admin_export(cookie)
    store.expire_due_files()
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    listed = store.list_exports(
        query=str((query.get("q") or [""])[0] or ""),
        dataset=str((query.get("dataset") or [""])[0] or ""),
        outcome=str((query.get("status") or query.get("outcome") or [""])[0] or ""),
        limit=int((query.get("limit") or ["100"])[0] or 100),
        offset=int((query.get("offset") or ["0"])[0] or 0),
    )
    return {
        "status": "ok",
        "total": listed["total"],
        "limit": listed["limit"],
        "offset": listed["offset"],
        "exports": [serialize_export(row) for row in listed["exports"]],
    }


def get_history_item(export_id: str, cookie: str) -> dict[str, Any]:
    require_admin_export(cookie)
    store.expire_due_files()
    row = store.get_export(export_id)
    if not row:
        raise ApiError(404, "not_found", "That export was not found.")
    return {"status": "ok", "export": serialize_export(row)}


def download_export(export_id: str, cookie: str) -> tuple[bytes, str, str]:
    require_admin_export(cookie)
    store.expire_due_files()
    row = store.get_export(export_id)
    if not row:
        raise ApiError(404, "not_found", "That export was not found.")
    if row["outcome"] != "success" or row["file_status"] != "available":
        raise ApiError(410, "export_expired", EXPIRED_MESSAGE)
    try:
        data = store.read_file(export_id)
    except FileNotFoundError as error:
        store.update_file_status(export_id, "missing")
        raise ApiError(410, "export_expired", EXPIRED_MESSAGE) from error
    return data, str(row["content_type"]), str(row["filename"])


def delete_export(export_id: str, cookie: str) -> dict[str, Any]:
    actor = require_admin_export(cookie)
    store.expire_due_files()
    row = store.get_export(export_id)
    if not row:
        raise ApiError(404, "not_found", "That export was not found.")
    store.remove_file(export_id)
    store.update_file_status(export_id, "deleted")
    admin_audit.record_admin_event(
        actor=actor,
        action="ADMIN_EXPORT_DELETE",
        details={"dataset": row.get("dataset"), "format": row.get("format")},
        outcome="success",
    )
    updated = store.get_export(export_id) or row
    return {"status": "ok", "export": serialize_export(updated)}


def serialize_export(row: dict[str, Any]) -> dict[str, Any]:
    file_status = str(row.get("file_status") or "none")
    outcome = str(row.get("outcome") or "failed")
    available = outcome == "success" and file_status == "available"
    return {
        "exportId": row.get("export_id") or "",
        "createdAt": row.get("created_at") or "",
        "adminUsername": row.get("actor_username") or "",
        "adminDisplayName": row.get("actor_display") or row.get("actor_username") or "",
        "dataset": row.get("dataset") or "",
        "datasetLabel": row.get("dataset_label") or "",
        "format": row.get("format") or "",
        "formatLabel": formats.format_label(str(row.get("format") or "csv"))
        if str(row.get("format") or "") in formats.FORMATS
        else str(row.get("format") or ""),
        "department": row.get("department") or "",
        "departmentLabel": row.get("department_label") or "All departments",
        "statusFilter": row.get("status_filter") or "",
        "statusLabel": _status_label(str(row.get("status_filter") or "")),
        "period": row.get("period") or "",
        "periodLabel": row.get("period_label") or "",
        "startDate": row.get("start_date") or "",
        "endDate": row.get("end_date") or "",
        "recordCount": int(row.get("record_count") or 0),
        "fileSize": int(row.get("file_size") or 0),
        "filename": row.get("filename") or "",
        "outcome": outcome,
        "outcomeLabel": "Success" if outcome == "success" else "Failed",
        "fileStatus": file_status,
        "fileStatusLabel": _file_status_label(file_status),
        "expiresAt": row.get("expires_at") or "",
        "canDownload": available,
        "canDelete": file_status == "available",
        "expired": file_status in {"expired", "missing"},
    }


def _parse_request(body: dict[str, Any]) -> dict[str, Any]:
    dataset = str(body.get("dataset") or "").strip()
    if dataset not in DATASETS:
        raise ApiError(422, "invalid_dataset", "Choose a dataset to export.")
    try:
        fmt = formats.validate_format(str(body.get("format") or "csv"))
    except ValueError as error:
        raise ApiError(422, "invalid_format", "Choose CSV, Excel, PDF, or JSON.") from error
    spec = DATASETS[dataset]
    period = str(body.get("period") or "today").strip().lower()
    start = str(body.get("start") or body.get("from") or "").strip()
    end = str(body.get("end") or body.get("to") or "").strip()
    if spec["usesDateRange"]:
        window = periods.resolve_period(period, start=start, end=end)
        period_label = str(window["label"])
        start_date = str(window["startDate"])
        end_date = str(window["endDate"])
    else:
        window = None
        period_label = "Current"
        start_date = ""
        end_date = ""
        period = "current"
    department = str(body.get("department") or "").strip()
    department_label = _department_label(department)
    status = str(body.get("status") or "").strip().lower()
    allowed_statuses = spec["statuses"]
    if allowed_statuses:
        if not status:
            status = allowed_statuses[0]
        if status not in allowed_statuses:
            raise ApiError(422, "invalid_status", "Choose a valid status for this export.")
    else:
        status = ""
    return {
        "dataset": dataset,
        "format": fmt,
        "period": period if spec["usesDateRange"] else "current",
        "period_label": period_label,
        "start_date": start_date,
        "end_date": end_date,
        "window": window,
        "department": department,
        "department_label": department_label,
        "status": status,
    }


def _load_rows(request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    loader = LOADERS[request["dataset"]]
    columns, rows = loader(request, cookie)
    return columns, rows[:MAX_ROWS]


def _load_patients(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    window = request["window"]
    extra = ""
    if request["status"] == "alive":
        extra = " AND (per.dead = 0 OR per.dead IS NULL)"
    elif request["status"] == "deceased":
        extra = " AND per.dead = 1"
    sql = (
        register.LIST_SQL
        + extra
        + " AND p.date_created >= %s AND p.date_created < %s"
        + register.ORDER_SQL
        + " LIMIT %s"
    )
    today = periods.hospital_today()
    try:
        raw = clinical_sql.fetch_all(sql, (window["utcStartNaive"], window["utcEndNaive"], MAX_ROWS))
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    columns = ["Name", "Hospital number", "Sex", "Age", "Phone", "Alive", "Date of death", "Registered on"]
    rows = []
    for item in raw:
        patient = register.serialize_directory_row(item, today)
        rows.append(
            {
                "Name": patient["name"],
                "Hospital number": patient["hospitalNumber"],
                "Sex": patient["sex"],
                "Age": patient["age"],
                "Phone": patient["phone"],
                "Alive": patient["alive"],
                "Date of death": register.format_death_date(patient.get("deathDate") or ""),
                "Registered on": patient["registeredOn"],
            }
        )
    return columns, rows


def _load_visits(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    window = request["window"]
    department = request["department"]
    if department and department not in {"", "Registration", "reception"}:
        return _visit_columns(), []
    extra = ""
    params: list[Any] = [*analytics.OPD_VISIT_TYPES, window["utcStartNaive"], window["utcEndNaive"]]
    if request["status"] == "open":
        extra = " AND v.date_stopped IS NULL"
    elif request["status"] == "closed":
        extra = " AND v.date_stopped IS NOT NULL"
    sql = f"""
        SELECT
          TRIM(CONCAT_WS(' ', NULLIF(pn.given_name, ''), NULLIF(pn.middle_name, ''), NULLIF(pn.family_name, ''))),
          pi.identifier,
          vt.name,
          v.date_started,
          v.date_stopped
        FROM visit v
        JOIN visit_type vt ON vt.visit_type_id = v.visit_type_id
        JOIN person per ON per.person_id = v.patient_id AND per.voided = 0
        LEFT JOIN person_name pn ON pn.person_name_id = (
          SELECT pn2.person_name_id FROM person_name pn2
          WHERE pn2.person_id = per.person_id AND pn2.voided = 0
          ORDER BY pn2.preferred DESC, pn2.person_name_id ASC LIMIT 1
        )
        LEFT JOIN patient_identifier pi ON pi.patient_identifier_id = (
          SELECT pi2.patient_identifier_id FROM patient_identifier pi2
          WHERE pi2.patient_id = v.patient_id AND pi2.voided = 0
          ORDER BY pi2.preferred DESC, pi2.patient_identifier_id ASC LIMIT 1
        )
        WHERE v.voided = 0
          AND vt.retired = 0
          AND vt.name IN ({",".join(["%s"] * len(analytics.OPD_VISIT_TYPES))})
          AND v.date_started >= %s
          AND v.date_started < %s
          {extra}
        ORDER BY v.date_started DESC
        LIMIT %s
    """
    params.append(MAX_ROWS)
    try:
        raw = clinical_sql.fetch_all(sql, tuple(params))
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    rows = [
        {
            "Patient": _text(item[0]) or "Unnamed patient",
            "Hospital number": _text(item[1]),
            "Visit type": _text(item[2]),
            "Started": _local_when(item[3]),
            "Ended": _local_when(item[4]) or "Open",
        }
        for item in raw
    ]
    return _visit_columns(), rows


def _visit_columns() -> list[str]:
    return ["Patient", "Hospital number", "Visit type", "Started", "Ended"]


def _load_encounters(
    request: dict[str, Any],
    _cookie: str,
    *,
    types: tuple[str, ...] | None = None,
    title_prefix: str | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    window = request["window"]
    encounter_types = list(types or ())
    department = request["department"]
    if not encounter_types:
        encounter_types = list(DEPARTMENT_ENCOUNTER_TYPES.get(department, ()))
        if department == "Consultation":
            encounter_types = ["Consultation"]
        elif department in {"Laboratory", "Pharmacy", "Radiology", "Registration"}:
            encounter_types = []
        elif not department:
            encounter_types = []
    extra = ""
    params: list[Any] = [window["utcStartNaive"], window["utcEndNaive"]]
    if encounter_types:
        extra = " AND et.name IN (" + ",".join(["%s"] * len(encounter_types)) + ")"
        params.extend(encounter_types)
    elif department and department not in {"", "All departments"}:
        return ["Patient", "Hospital number", "Encounter", "When"], []
    sql = f"""
        SELECT
          TRIM(CONCAT_WS(' ', NULLIF(pn.given_name, ''), NULLIF(pn.middle_name, ''), NULLIF(pn.family_name, ''))),
          pi.identifier,
          et.name,
          e.encounter_datetime
        FROM encounter e
        JOIN encounter_type et ON et.encounter_type_id = e.encounter_type
        JOIN person per ON per.person_id = e.patient_id AND per.voided = 0
        LEFT JOIN person_name pn ON pn.person_name_id = (
          SELECT pn2.person_name_id FROM person_name pn2
          WHERE pn2.person_id = per.person_id AND pn2.voided = 0
          ORDER BY pn2.preferred DESC, pn2.person_name_id ASC LIMIT 1
        )
        LEFT JOIN patient_identifier pi ON pi.patient_identifier_id = (
          SELECT pi2.patient_identifier_id FROM patient_identifier pi2
          WHERE pi2.patient_id = e.patient_id AND pi2.voided = 0
          ORDER BY pi2.preferred DESC, pi2.patient_identifier_id ASC LIMIT 1
        )
        WHERE e.voided = 0
          AND et.retired = 0
          AND e.encounter_datetime >= %s
          AND e.encounter_datetime < %s
          {extra}
        ORDER BY e.encounter_datetime DESC
        LIMIT %s
    """
    params.append(MAX_ROWS)
    try:
        raw = clinical_sql.fetch_all(sql, tuple(params))
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    kind = title_prefix or "Encounter"
    rows = [
        {
            "Patient": _text(item[0]) or "Unnamed patient",
            "Hospital number": _text(item[1]),
            kind: _text(item[2]),
            "When": _local_when(item[3]),
        }
        for item in raw
    ]
    return ["Patient", "Hospital number", kind, "When"], rows


def _load_clinical_records(request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    selected = request["department"]
    if selected and selected not in {"", "Consultation", "clinical"}:
        return ["Patient", "Hospital number", "Encounter", "When"], []
    return _load_encounters(request, cookie, types=("Consultation",), title_prefix="Encounter")


def _load_orders(request: dict[str, Any], order_type: str) -> tuple[list[str], list[dict[str, Any]]]:
    window = request["window"]
    sql = """
        SELECT
          TRIM(CONCAT_WS(' ', NULLIF(pn.given_name, ''), NULLIF(pn.middle_name, ''), NULLIF(pn.family_name, ''))),
          pi.identifier,
          ot.name,
          COALESCE(cn.name, ''),
          COALESCE(o.date_activated, o.date_created),
          COALESCE(o.fulfiller_status, '')
        FROM orders o
        JOIN order_type ot ON ot.order_type_id = o.order_type_id
        JOIN person per ON per.person_id = o.patient_id AND per.voided = 0
        LEFT JOIN concept_name cn ON cn.concept_id = o.concept_id
          AND cn.voided = 0 AND cn.locale = 'en' AND cn.concept_name_type = 'FULLY_SPECIFIED'
        LEFT JOIN person_name pn ON pn.person_name_id = (
          SELECT pn2.person_name_id FROM person_name pn2
          WHERE pn2.person_id = per.person_id AND pn2.voided = 0
          ORDER BY pn2.preferred DESC, pn2.person_name_id ASC LIMIT 1
        )
        LEFT JOIN patient_identifier pi ON pi.patient_identifier_id = (
          SELECT pi2.patient_identifier_id FROM patient_identifier pi2
          WHERE pi2.patient_id = o.patient_id AND pi2.voided = 0
          ORDER BY pi2.preferred DESC, pi2.patient_identifier_id ASC LIMIT 1
        )
        WHERE o.voided = 0
          AND ot.retired = 0
          AND ot.name = %s
          AND o.order_action <> 'DISCONTINUE'
          AND COALESCE(o.date_activated, o.date_created) >= %s
          AND COALESCE(o.date_activated, o.date_created) < %s
        ORDER BY COALESCE(o.date_activated, o.date_created) DESC
        LIMIT %s
    """
    try:
        raw = clinical_sql.fetch_all(
            sql,
            (order_type, window["utcStartNaive"], window["utcEndNaive"], MAX_ROWS),
        )
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    rows = [
        {
            "Patient": _text(item[0]) or "Unnamed patient",
            "Hospital number": _text(item[1]),
            "Order": _text(item[2]),
            "Item": _text(item[3]),
            "When": _local_when(item[4]),
            "Status": _text(item[5]) or "Ordered",
        }
        for item in raw
    ]
    return ["Patient", "Hospital number", "Order", "Item", "When", "Status"], rows


def _load_laboratory(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    return _load_orders(request, "Lab Order")


def _load_pharmacy(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    return _load_orders(request, "Drug Order")


def _load_radiology(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    return _load_orders(request, "Radiology Order")


def _load_admissions(request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    return _load_encounters(request, cookie, types=("ADMISSION",), title_prefix="Admission")


def _load_discharges(request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    return _load_encounters(request, cookie, types=("DISCHARGE",), title_prefix="Discharge")


def _load_vitals(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    window = request["window"]
    concept_uuids = tuple(item["uuid"] for item in vitals.VITAL_CONCEPTS.values())
    labels = {item["uuid"]: item["label"] for item in vitals.VITAL_CONCEPTS.values()}
    units = {item["uuid"]: item.get("unit") or "" for item in vitals.VITAL_CONCEPTS.values()}
    sql = f"""
        SELECT
          TRIM(CONCAT_WS(' ', NULLIF(pn.given_name, ''), NULLIF(pn.middle_name, ''), NULLIF(pn.family_name, ''))),
          pi.identifier,
          c.uuid,
          obs.value_numeric,
          obs.obs_datetime
        FROM obs
        JOIN concept c ON c.concept_id = obs.concept_id
        JOIN person per ON per.person_id = obs.person_id AND per.voided = 0
        LEFT JOIN person_name pn ON pn.person_name_id = (
          SELECT pn2.person_name_id FROM person_name pn2
          WHERE pn2.person_id = per.person_id AND pn2.voided = 0
          ORDER BY pn2.preferred DESC, pn2.person_name_id ASC LIMIT 1
        )
        LEFT JOIN patient_identifier pi ON pi.patient_identifier_id = (
          SELECT pi2.patient_identifier_id FROM patient_identifier pi2
          WHERE pi2.patient_id = obs.person_id AND pi2.voided = 0
          ORDER BY pi2.preferred DESC, pi2.patient_identifier_id ASC LIMIT 1
        )
        WHERE obs.voided = 0
          AND c.uuid IN ({",".join(["%s"] * len(concept_uuids))})
          AND obs.obs_datetime >= %s
          AND obs.obs_datetime < %s
        ORDER BY obs.obs_datetime DESC
        LIMIT %s
    """
    try:
        raw = clinical_sql.fetch_all(
            sql,
            (*concept_uuids, window["utcStartNaive"], window["utcEndNaive"], MAX_ROWS),
        )
    except clinical_sql.OpenmrsSqlError as error:
        raise clinical_sql.unavailable_error() from error
    rows = [
        {
            "Patient": _text(item[0]) or "Unnamed patient",
            "Hospital number": _text(item[1]),
            "Vital": labels.get(_text(item[2]), _text(item[2])),
            "Value": "" if item[3] is None else str(item[3]),
            "Unit": units.get(_text(item[2]), ""),
            "When": _local_when(item[4]),
        }
        for item in raw
    ]
    return ["Patient", "Hospital number", "Vital", "Value", "Unit", "When"], rows


def _load_invoices(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    odoo = cashier.odoo_reader()
    window = request["window"]
    invoices = _posted_invoices(
        odoo,
        window["startDate"],
        window["endDate"],
        status=request["status"],
        department=request["department"],
    )
    return _invoice_columns(), invoices


def _load_accommodation_bills(request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    copy = {**request, "department": "Accommodation"}
    return _load_invoices(copy, cookie)


def _load_payments(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    odoo = cashier.odoo_reader()
    window = request["window"]
    payments = cashier.list_payments_for_range(odoo, window["startDate"], window["endDate"])
    columns = ["Date", "Reference", "Patient", "Hospital number", "Amount", "Method", "Received by"]
    rows = [
        {
            "Date": item.get("date") or "",
            "Reference": item.get("reference") or "",
            "Patient": item.get("patientName") or "",
            "Hospital number": item.get("mrn") or "",
            "Amount": _money_text(item.get("amount")),
            "Method": item.get("method") or item.get("journal") or "",
            "Received by": item.get("createUid") or "",
        }
        for item in payments
    ]
    return columns, rows


def _load_outstanding(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    odoo = cashier.odoo_reader()
    invoices = cashier.outstanding_invoices(odoo)
    department = request["department"]
    if department in FINANCIAL_DEPARTMENTS:
        invoices = [row for row in invoices if row.get("department") == department]
    columns = ["Invoice", "Patient", "Hospital number", "Department", "Status", "Billed", "Still unpaid"]
    rows = [
        {
            "Invoice": item.get("number") or "",
            "Patient": item.get("patientName") or "",
            "Hospital number": item.get("mrn") or "",
            "Department": item.get("department") or "",
            "Status": item.get("paymentStateLabel") or "",
            "Billed": _money_text(item.get("total")),
            "Still unpaid": _money_text(item.get("outstanding")),
        }
        for item in invoices
    ]
    return columns, rows


def _load_refunds(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    odoo = cashier.odoo_reader()
    window = request["window"]
    rows = odoo.search_read(
        "account.move",
        finance.refund_domain(window["startDate"], window["endDate"]),
        ["id", "name", "invoice_date", "amount_total", "payment_state", "invoice_origin", "partner_id"],
        limit=MAX_ROWS,
    )
    attributed = _attribute_moves(odoo, rows)
    department = request["department"]
    columns = ["Refund", "Date", "Patient", "Hospital number", "Department", "Amount", "Status"]
    export_rows = []
    for item in attributed:
        if department in FINANCIAL_DEPARTMENTS and item["department"] != department:
            continue
        export_rows.append(
            {
                "Refund": item["number"],
                "Date": item["date"],
                "Patient": item["patient"],
                "Hospital number": item["hospitalNumber"],
                "Department": item["department"],
                "Amount": item["amount"],
                "Status": item["status"],
            }
        )
    return columns, export_rows


def _load_revenue(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    odoo = cashier.odoo_reader()
    window = request["window"]
    currency = analytics._hospital_currency(odoo)
    totals = finance.billed_by_department(odoo, window["startDate"], window["endDate"])
    department = request["department"]
    names = [department] if department in FINANCIAL_DEPARTMENTS else list(finance.REVENUE_DEPARTMENTS)
    hospital = sum(float(totals.get(name) or 0.0) for name in finance.REVENUE_DEPARTMENTS)
    rows = []
    for name in names:
        amount = float(totals.get(name) or 0.0)
        share = (amount / hospital) if hospital else 0.0
        money = core.format_money(amount, currency)
        rows.append(
            {
                "Department": name,
                "Revenue generated": money["formatted"],
                "Share": f"{share:.1%}".replace(".0%", "%") if share else "0%",
            }
        )
    if not department:
        hospital_money = core.format_money(hospital, currency)
        rows.append(
            {
                "Department": "Hospital total",
                "Revenue generated": hospital_money["formatted"],
                "Share": "100%" if hospital else "0%",
            }
        )
    return ["Department", "Revenue generated", "Share"], rows


def _load_accommodation_prices(_request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    import accommodation as lodging

    payload = lodging.list_tariffs(cookie)
    columns = ["Ward or room", "Price type", "Daily price", "Set"]
    rows = [
        {
            "Ward or room": item.get("areaName") or "",
            "Price type": item.get("priceKindLabel") or "",
            "Daily price": _money_text(item.get("listPrice")),
            "Set": "Yes" if item.get("configured") else "No",
        }
        for item in payload.get("areas") or []
    ]
    return columns, rows


def _load_staff(request: dict[str, Any], cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    payload = administration.list_staff(cookie)
    department = request["department"]
    status = request["status"]
    columns = ["Name", "Username", "Departments", "Category", "Sign-in", "Status"]
    rows = []
    for item in payload.get("staff") or []:
        departments = [
            str(row.get("label") or "")
            for row in (item.get("departments") or [])
            if row.get("label")
        ]
        dept_ids = [str(row.get("id") or "") for row in (item.get("departments") or [])]
        if department in STAFF_DEPARTMENTS and department not in dept_ids:
            continue
        if department in FINANCIAL_DEPARTMENTS:
            mapped = _staff_department_from_revenue(department)
            if mapped and mapped not in dept_ids:
                continue
        enabled = bool(item.get("enabled", True))
        if status == "active" and not enabled:
            continue
        if status == "disabled" and enabled:
            continue
        rows.append(
            {
                "Name": item.get("displayName") or "",
                "Username": item.get("username") or "",
                "Departments": ", ".join(departments) or "Administration",
                "Category": item.get("staffCategoryLabel") or item.get("accountType") or "",
                "Sign-in": "Yes" if item.get("username") else "No",
                "Status": "Active" if enabled else "Disabled",
            }
        )
    return columns, rows


def _load_analytics(request: dict[str, Any], _cookie: str) -> tuple[list[str], list[dict[str, Any]]]:
    window = request["window"]
    occupancy = analytics._current_occupancy()
    money = analytics._finance_totals(window)
    metrics = [
        ("Patients registered", analytics._count_registrations(window)),
        ("Outpatient visits", analytics._count_opd_visits(window)),
        ("Consultations", analytics._count_encounters("Consultation", window)),
        ("Admissions", analytics._count_encounters("ADMISSION", window)),
        ("Discharges", analytics._count_encounters("DISCHARGE", window)),
        ("Laboratory orders", analytics._count_orders("Lab Order", window)),
        ("Prescriptions", analytics._count_orders("Drug Order", window)),
        ("Dispensed", analytics._dispensing(window)),
        ("Billed", money["billed"]),
        ("Collected", money["collected"]),
        ("Outstanding", money["outstanding"]),
        ("Beds in use now", occupancy),
    ]
    columns = ["Measure", "Value", "Note"]
    rows = []
    for label, metric in metrics:
        rows.append(
            {
                "Measure": label,
                "Value": _metric_text(metric),
                "Note": str(metric.get("message") or ("Current snapshot" if metric.get("asOf") == "current" else "")),
            }
        )
    return columns, rows


LOADERS = {
    "patients": _load_patients,
    "visits": _load_visits,
    "encounters": _load_encounters,
    "clinical_records": _load_clinical_records,
    "laboratory": _load_laboratory,
    "pharmacy": _load_pharmacy,
    "radiology": _load_radiology,
    "admissions": _load_admissions,
    "discharges": _load_discharges,
    "nursing_vitals": _load_vitals,
    "invoices": _load_invoices,
    "payments": _load_payments,
    "outstanding": _load_outstanding,
    "refunds": _load_refunds,
    "revenue": _load_revenue,
    "accommodation": _load_accommodation_bills,
    "accommodation_prices": _load_accommodation_prices,
    "staff": _load_staff,
    "analytics": _load_analytics,
}


def _posted_invoices(
    odoo: Any,
    start_date: str,
    end_date: str,
    *,
    status: str,
    department: str,
) -> list[dict[str, Any]]:
    invoices = odoo.search_read(
        "account.move",
        finance.billed_domain(start_date, end_date),
        [
            "id",
            "name",
            "invoice_date",
            "invoice_origin",
            "amount_total",
            "amount_residual",
            "payment_state",
            "invoice_line_ids",
            "partner_id",
        ],
        limit=MAX_ROWS,
    )
    attributed = _attribute_moves(odoo, invoices)
    selected = []
    for item in attributed:
        payment_state = item["paymentState"]
        if status == "reversed" and payment_state != "reversed":
            continue
        if status in PAYMENT_STATE_FILTERS and payment_state not in PAYMENT_STATE_FILTERS[status]:
            continue
        if status in {"posted", ""} and payment_state == "reversed":
            continue
        if department in FINANCIAL_DEPARTMENTS and item["department"] != department:
            continue
        selected.append(
            {
                "Invoice": item["number"],
                "Date": item["date"],
                "Patient": item["patient"],
                "Hospital number": item["hospitalNumber"],
                "Department": item["department"],
                "Status": item["status"],
                "Billed": item["amount"],
                "Still unpaid": item["residual"],
            }
        )
    return selected


def _invoice_columns() -> list[str]:
    return [
        "Invoice",
        "Date",
        "Patient",
        "Hospital number",
        "Department",
        "Status",
        "Billed",
        "Still unpaid",
    ]


def _attribute_moves(odoo: Any, invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    origins = sorted({str(row.get("invoice_origin") or "") for row in invoices if row.get("invoice_origin")})
    orders = (
        odoo.search_read("sale.order", [("name", "in", origins)], ["name", "shop_id"], limit=MAX_ROWS)
        if origins
        else []
    )
    order_by_name = {str(row.get("name") or ""): row for row in orders}
    unmatched = []
    departments: dict[int, str] = {}
    for invoice in invoices:
        origin = str(invoice.get("invoice_origin") or "")
        shop = core.many2one_name((order_by_name.get(origin) or {}).get("shop_id"))
        department = core.identify_department(shop, [])
        if department:
            departments[int(invoice["id"])] = department
        else:
            unmatched.append(invoice)
    if unmatched:
        categories_by_move = finance._invoice_category_names(odoo, unmatched)
        for invoice in unmatched:
            department = core.identify_department("", categories_by_move.get(int(invoice["id"]), []))
            departments[int(invoice["id"])] = department or finance.UNIDENTIFIED_DEPARTMENT
    partner_ids = {core.many2one_id(row.get("partner_id")) for row in invoices if core.many2one_id(row.get("partner_id"))}
    partners = {
        int(row["id"]): row
        for row in (odoo.read("res.partner", list(partner_ids), ["name", "ref"]) if partner_ids else [])
    }
    currency = analytics._hospital_currency(odoo)
    rows = []
    for invoice in invoices:
        partner = partners.get(core.many2one_id(invoice.get("partner_id")) or 0) or {}
        amount = core.format_money(core.as_float(invoice.get("amount_total")), currency)
        residual = core.format_money(core.as_float(invoice.get("amount_residual")), currency)
        payment_state = str(invoice.get("payment_state") or "not_paid")
        rows.append(
            {
                "number": invoice.get("name") or "",
                "date": invoice.get("invoice_date") or "",
                "patient": partner.get("name") or core.many2one_name(invoice.get("partner_id")),
                "hospitalNumber": partner.get("ref") or "",
                "department": departments.get(int(invoice["id"]), finance.UNIDENTIFIED_DEPARTMENT),
                "status": core.payment_state_label(payment_state),
                "paymentState": payment_state,
                "amount": amount["formatted"],
                "residual": residual["formatted"],
            }
        )
    return rows


def _record_failure(
    actor: dict[str, Any],
    request: dict[str, Any],
    spec: dict[str, Any],
    audit_id: str,
    error_code: str,
) -> None:
    try:
        store.insert_export(
            actor=_actor_row(actor),
            dataset=request["dataset"],
            dataset_label=spec["label"],
            fmt=request["format"],
            department=request["department"],
            department_label=request["department_label"],
            status_filter=request["status"],
            period=request["period"],
            period_label=request["period_label"],
            start_date=request["start_date"],
            end_date=request["end_date"],
            record_count=0,
            file_size=0,
            filename="",
            content_type="",
            outcome="failed",
            error_code=error_code,
            file_status="none",
            expires_at="",
            audit_event_id=audit_id,
        )
    except Exception:
        LOGGER.warning("admin export history could not record a failed attempt")
    try:
        admin_audit.finish_admin_event(
            audit_id,
            outcome="failure",
            details=_audit_details(request, spec),
            error_code=error_code,
        )
    except Exception:
        LOGGER.warning("admin export audit could not record a failed attempt")


def _audit_details(request: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": request["dataset"],
        "format": request["format"],
        "department": request["department_label"],
        "period": request["period_label"],
        "status": request["status"],
        "label": spec["label"],
    }


def _actor_row(actor: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": actor.get("uuid") or "",
        "username": actor.get("username") or "",
        "displayName": actor.get("display") or actor.get("username") or "Administrator",
    }


def _filename(label: str, fmt: str, period_label: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", f"Hospital EMR-{label}-{period_label}").strip("-")
    return f"{stem}.{formats.EXTENSIONS[fmt]}"


def _file_meta(request: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "periodLabel": request["period_label"],
        "departmentLabel": request["department_label"],
        "statusLabel": _status_label(request["status"]),
        "dataset": spec["label"],
    }


def _dataset_departments(spec: dict[str, Any]) -> list[dict[str, str]]:
    if not spec.get("usesDepartment"):
        return []
    options = [{"id": "", "label": "All departments"}]
    if spec.get("kind") == "staff":
        options.extend({"id": row["id"], "label": str(row["label"])} for row in administration.DEPARTMENTS)
        return options
    options.extend({"id": name, "label": name} for name in FINANCIAL_DEPARTMENTS)
    return options


def _department_label(department: str) -> str:
    if not department:
        return "All departments"
    for row in administration.DEPARTMENTS:
        if row["id"] == department:
            return str(row["label"])
    return department


def _staff_department_from_revenue(name: str) -> str:
    mapping = {
        "Consultation": "clinical",
        "Registration": "reception",
        "Laboratory": "laboratory",
        "Radiology": "radiology",
        "Pharmacy": "pharmacy",
        "Accommodation": "nursing",
    }
    return mapping.get(name, "")


def _status_label(status: str) -> str:
    return {
        "": "All",
        "all": "All",
        "posted": "Posted",
        "unpaid": "Unpaid",
        "partial": "Partially paid",
        "paid": "Paid",
        "reversed": "Reversed",
        "active": "Active",
        "disabled": "Disabled",
        "open": "Open",
        "closed": "Closed",
        "alive": "Alive",
        "deceased": "Dead",
        "current": "Current",
    }.get(status, status.replace("_", " ").title() if status else "All")


def _file_status_label(status: str) -> str:
    return {
        "available": "Available",
        "expired": "Expired",
        "deleted": "Deleted",
        "missing": "No longer available",
        "none": "No file",
    }.get(status, status)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _local_when(value: Any) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        local = moment.astimezone(periods.HOSPITAL_TZ)
        return local.strftime("%d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return _text(value)


def _money_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("formatted") or value.get("amount") or "")
    return _text(value)


def _metric_text(metric: dict[str, Any]) -> str:
    if metric.get("status") == "unavailable":
        return "Unavailable"
    if metric.get("formatted"):
        return str(metric["formatted"])
    if metric.get("label"):
        return str(metric["label"])
    value = metric.get("value")
    if value is None:
        return "0"
    return str(value)
