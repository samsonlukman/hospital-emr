"""Hospital Admin analytics facades over OpenMRS SQL and Odoo ORM.

Hospital Admin does not receive department workspace privileges. Occupancy is
a current snapshot and is never treated as a historical period total.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

import accountant as cashier
import admin_period as periods
import finance_summary as finance
import hospital_admin as administration
import openmrs_sql as clinical_sql
from server import ApiError, format_money, many2one_id

LOGGER = logging.getLogger(__name__)

ANALYTICS_PRIVILEGE = "abikan:admin:analytics"
OPD_VISIT_TYPES = ("OPD", "Special OPD", "Follow Up")
PRESCRIPTION_PREFIXES = (
    "registration:",
    "consultation:",
    "lab:",
    "radiology:",
)


def require_admin_analytics(cookie: str) -> dict[str, Any]:
    user = administration.require_hospital_admin(cookie)
    if administration.is_technical_superadmin(user):
        return user
    privileges = set(user.get("privileges") or [])
    if ANALYTICS_PRIVILEGE not in privileges:
        raise ApiError(403, "forbidden", "This action requires Hospital Administration.")
    return user


def _int_metric(value: int) -> dict[str, Any]:
    return {"status": "ok", "value": int(value)}


def _unavailable(message: str) -> dict[str, Any]:
    return {"status": "unavailable", "value": None, "message": message}


def _records_unavailable() -> dict[str, Any]:
    return _unavailable("Hospital records are temporarily unavailable.")


def _finance_unavailable() -> dict[str, Any]:
    return _unavailable("Finance totals are temporarily unavailable.")


def _count_registrations(window: dict[str, Any]) -> dict[str, Any]:
    try:
        value = clinical_sql.fetch_int(
            """
            SELECT COUNT(*)
            FROM patient
            WHERE voided = 0
              AND date_created >= %s
              AND date_created < %s
            """,
            (window["utcStartNaive"], window["utcEndNaive"]),
        )
    except clinical_sql.OpenmrsSqlError:
        return _records_unavailable()
    return _int_metric(value)


def _count_opd_visits(window: dict[str, Any]) -> dict[str, Any]:
    try:
        value = clinical_sql.fetch_int(
            """
            SELECT COUNT(*)
            FROM visit v
            JOIN visit_type vt ON vt.visit_type_id = v.visit_type_id
            WHERE v.voided = 0
              AND vt.retired = 0
              AND vt.name IN ({placeholders})
              AND v.date_started >= %s
              AND v.date_started < %s
            """.format(placeholders=",".join(["%s"] * len(OPD_VISIT_TYPES))),
            (*OPD_VISIT_TYPES, window["utcStartNaive"], window["utcEndNaive"]),
        )
    except clinical_sql.OpenmrsSqlError:
        return _records_unavailable()
    return _int_metric(value)


def _count_encounters(encounter_type: str, window: dict[str, Any]) -> dict[str, Any]:
    try:
        value = clinical_sql.fetch_int(
            """
            SELECT COUNT(*)
            FROM encounter e
            JOIN encounter_type et ON et.encounter_type_id = e.encounter_type
            WHERE e.voided = 0
              AND et.retired = 0
              AND et.name = %s
              AND e.encounter_datetime >= %s
              AND e.encounter_datetime < %s
            """,
            (encounter_type, window["utcStartNaive"], window["utcEndNaive"]),
        )
    except clinical_sql.OpenmrsSqlError:
        return _records_unavailable()
    return _int_metric(value)


def _count_orders(order_type: str, window: dict[str, Any]) -> dict[str, Any]:
    try:
        value = clinical_sql.fetch_int(
            """
            SELECT COUNT(*)
            FROM orders o
            JOIN order_type ot ON ot.order_type_id = o.order_type_id
            WHERE o.voided = 0
              AND ot.retired = 0
              AND ot.name = %s
              AND o.order_action <> 'DISCONTINUE'
              AND COALESCE(o.date_activated, o.date_created) >= %s
              AND COALESCE(o.date_activated, o.date_created) < %s
            """,
            (order_type, window["utcStartNaive"], window["utcEndNaive"]),
        )
    except clinical_sql.OpenmrsSqlError:
        return _records_unavailable()
    return _int_metric(value)


def _current_occupancy() -> dict[str, Any]:
    try:
        total = clinical_sql.fetch_int(
            "SELECT COUNT(*) FROM bed WHERE voided = 0"
        )
        occupied = clinical_sql.fetch_int(
            """
            SELECT COUNT(*)
            FROM bed_patient_assignment_map
            WHERE voided = 0
              AND date_stopped IS NULL
            """
        )
    except clinical_sql.OpenmrsSqlError:
        return {
            **_records_unavailable(),
            "occupied": None,
            "total": None,
            "rate": None,
            "asOf": "current",
        }
    rate = (occupied / total) if total else 0.0
    return {
        "status": "ok",
        "value": occupied,
        "occupied": occupied,
        "total": total,
        "available": max(0, total - occupied),
        "rate": round(rate, 4),
        "asOf": "current",
        "label": f"{occupied} / {total}",
    }


def _is_prescription_key(value: str) -> bool:
    key = value.strip()
    if not key or "-" not in key:
        return False
    lowered = key.lower()
    return not any(lowered.startswith(prefix) for prefix in PRESCRIPTION_PREFIXES)


def _money_metric(amount: float, currency: dict[str, Any]) -> dict[str, Any]:
    money = format_money(amount, currency)
    return {
        "status": "ok",
        "value": money["amount"],
        "amount": money["amount"],
        "formatted": money["formatted"],
        "currencyCode": money["currencyCode"],
        "currencySymbol": money["currencySymbol"],
    }


def _hospital_currency(odoo: Any) -> dict[str, Any]:
    rows = odoo.search_read(
        "res.currency",
        [("name", "=", "NGN")],
        ["name", "symbol", "decimal_places", "position"],
        limit=1,
    )
    row = rows[0] if rows else {}
    return {
        "code": "NGN",
        "symbol": "₦",
        "decimalPlaces": int(row.get("decimal_places") or 2),
        "position": "before",
    }


def _finance_metric(loader, currency: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    try:
        metric = _money_metric(loader(), currency)
    except Exception as error:
        LOGGER.warning("finance metric unavailable: %s", error)
        metric = _finance_unavailable()
    if as_of:
        metric["asOf"] = as_of
        if metric.get("status") == "ok":
            metric["message"] = (
                "Current amount still unpaid. This is not the outstanding balance as of "
                "the selected date range."
            )
    return metric


def _department_revenue_rows(
    odoo: Any,
    currency: dict[str, Any],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    import department_revenue as departmental

    try:
        totals = finance.billed_by_department(odoo, start_date, end_date)
        rows = departmental.serialize_department_rows(totals, currency, None)
    except Exception as error:
        LOGGER.warning("department revenue unavailable: %s", error)
        return {
            "status": "unavailable",
            "message": "Finance totals are temporarily unavailable.",
            "departments": [],
        }
    hospital = sum(float(row.get("amount") or 0.0) for row in rows)
    return {
        "status": "ok",
        "departments": rows,
        "total": _money_metric(hospital, currency),
    }


def _finance_totals(window: dict[str, Any]) -> dict[str, Any]:
    try:
        odoo = cashier.odoo_reader()
        currency = _hospital_currency(odoo)
    except ApiError as error:
        LOGGER.warning("finance source unavailable: %s", error)
        missing = _finance_unavailable()
        return {
            "billed": dict(missing),
            "collected": dict(missing),
            "outstanding": {**missing, "asOf": "current"},
            "byDepartment": {"status": "unavailable", "message": missing["message"], "departments": []},
        }

    start_date = window["startDate"]
    end_date = window["endDate"]
    by_department = _department_revenue_rows(odoo, currency, start_date, end_date)
    return {
        "billed": _finance_metric(
            lambda: finance.billed_total(odoo, start_date, end_date),
            currency,
        ),
        "collected": _finance_metric(
            lambda: finance.collected_total(odoo, start_date, end_date),
            currency,
        ),
        "outstanding": _finance_metric(
            lambda: finance.outstanding_total(odoo),
            currency,
            as_of="current",
        ),
        "byDepartment": by_department,
    }


def _dispensing(window: dict[str, Any]) -> dict[str, Any]:
    try:
        odoo = cashier.odoo_reader()
    except ApiError:
        return {
            **_finance_unavailable(),
            "movements": None,
            "message": "Pharmacy dispensing totals are temporarily unavailable.",
        }
    start = window["utcStartNaive"].strftime("%Y-%m-%d %H:%M:%S")
    end = window["utcEndNaive"].strftime("%Y-%m-%d %H:%M:%S")
    try:
        lines = odoo.search_read(
            "sale.order.line",
            [("external_order_id", "!=", False)],
            ["external_order_id", "order_id"],
            limit=5000,
        )
    except Exception:
        return {
            **_unavailable("Pharmacy dispensing totals are temporarily unavailable."),
            "movements": None,
        }
    sale_ids: set[int] = set()
    for line in lines:
        if not _is_prescription_key(str(line.get("external_order_id") or "")):
            continue
        sale_id = many2one_id(line.get("order_id"))
        if sale_id:
            sale_ids.add(sale_id)
    if not sale_ids:
        metric = _int_metric(0)
        metric["movements"] = 0
        return metric
    try:
        pickings = odoo.search_read(
            "stock.picking",
            [
                ("sale_id", "in", list(sale_ids)),
                ("state", "=", "done"),
                ("date_done", ">=", start),
                ("date_done", "<", end),
            ],
            ["sale_id", "picking_type_id", "name", "date_done"],
            limit=5000,
        )
        type_ids = [
            many2one_id(row.get("picking_type_id"))
            for row in pickings
            if many2one_id(row.get("picking_type_id"))
        ]
        types = {
            int(row["id"]): row.get("code") or ""
            for row in (
                odoo.read("stock.picking.type", type_ids, ["code"]) if type_ids else []
            )
        }
    except Exception:
        return {
            **_unavailable("Pharmacy dispensing totals are temporarily unavailable."),
            "movements": None,
        }
    outgoing = []
    for row in pickings:
        code = types.get(many2one_id(row.get("picking_type_id")) or 0, "")
        name = str(row.get("name") or "")
        if code == "outgoing" or name.startswith("WH/OUT"):
            outgoing.append(row)
    prescriptions = {
        many2one_id(row.get("sale_id"))
        for row in outgoing
        if many2one_id(row.get("sale_id"))
    }
    metric = _int_metric(len(prescriptions))
    metric["movements"] = len(outgoing)
    return metric


def _window_from_query(query: dict[str, list[str]], now: Any = None) -> dict[str, Any]:
    period = (query.get("period") or ["today"])[0]
    start = (query.get("from") or query.get("start") or [""])[0]
    end = (query.get("to") or query.get("end") or [""])[0]
    return periods.resolve_period(period, start=start, end=end, now=now)


def _period_payload(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": window["period"],
        "label": window["label"],
        "timezone": window["timezone"],
        "startDate": window["startDate"],
        "endDate": window["endDate"],
        "weekStartsOn": window["weekStartsOn"],
    }


def build_reception(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_admin_analytics(cookie)
    window = _window_from_query(query or {})
    return {
        "status": "ok",
        "period": _period_payload(window),
        "patientsRegistered": _count_registrations(window),
        "opdVisits": _count_opd_visits(window),
    }


def build_inpatient(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_admin_analytics(cookie)
    window = _window_from_query(query or {})
    occupancy = _current_occupancy()
    return {
        "status": "ok",
        "period": _period_payload(window),
        "admissions": _count_encounters("ADMISSION", window),
        "discharges": _count_encounters("DISCHARGE", window),
        "occupancy": occupancy,
    }


def build_overview(cookie: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    require_admin_analytics(cookie)
    window = _window_from_query(query or {})
    occupancy = _current_occupancy()
    finance = _finance_totals(window)
    return {
        "status": "ok",
        "period": _period_payload(window),
        "patientsRegistered": _count_registrations(window),
        "opdVisits": _count_opd_visits(window),
        "consultations": _count_encounters("Consultation", window),
        "admissions": _count_encounters("ADMISSION", window),
        "discharges": _count_encounters("DISCHARGE", window),
        "occupancy": occupancy,
        "labOrders": _count_orders("Lab Order", window),
        "prescriptions": _count_orders("Drug Order", window),
        "dispensed": _dispensing(window),
        "billed": finance["billed"],
        "collected": finance["collected"],
        "outstanding": finance["outstanding"],
        "revenueByDepartment": finance.get("byDepartment")
        or {"status": "unavailable", "departments": []},
    }


def parse_request_query(raw_path: str) -> dict[str, list[str]]:
    query = raw_path.split("?", 1)
    if len(query) == 1:
        return {}
    return parse_qs(query[1], keep_blank_values=True)
