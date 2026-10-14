"""Department revenue from posted Odoo invoices.

Odoo remains the financial source of truth. Department staff only receive
totals for their own originating department. Finance and Hospital Admin
receive the hospital total and a departmental breakdown.
"""

from __future__ import annotations

import logging
from typing import Any

import accountant as cashier
import admin_analytics as analytics
import accommodation as ward_billing
import consultation as clinical
import finance_summary as finance
import hospital_admin as administration
import laboratory as lab
import pharmacy as dispensary
import radiology as imaging
import registration as reception
from server import ApiError, format_money

LOGGER = logging.getLogger(__name__)

REVENUE_FORBIDDEN = "This revenue view is not available for this account."
ADT_PRIVILEGE = ward_billing.ADT_PRIVILEGE


def require_revenue_viewer(cookie: str) -> tuple[dict[str, Any], list[str] | None]:
    administration.core.require_session(cookie)
    user = cashier.load_openmrs_user(cookie)
    if (
        administration.is_technical_superadmin(user)
        or administration.is_hospital_admin(user)
        or cashier.is_accountant(user)
    ):
        return user, None
    departments: list[str] = []
    if reception.is_registrar(user):
        departments.append("Registration")
    if clinical.is_clinician(user):
        departments.append("Consultation")
    if lab.is_lab_user(user):
        departments.append("Laboratory")
    if imaging.is_radiology_user(user):
        departments.append("Radiology")
    if dispensary.is_pharmacist(user):
        departments.append("Pharmacy")
    privileges = set(user.get("privileges") or [])
    if ADT_PRIVILEGE in privileges:
        departments.append("Accommodation")
    seen: list[str] = []
    for name in departments:
        if name not in seen:
            seen.append(name)
    if not seen:
        raise ApiError(403, "forbidden", REVENUE_FORBIDDEN)
    return user, seen


def _money(amount: float, currency: dict[str, Any]) -> dict[str, Any]:
    money = format_money(amount, currency)
    return {
        "status": "ok",
        "value": money["amount"],
        "amount": money["amount"],
        "formatted": money["formatted"],
        "currencyCode": money["currencyCode"],
        "currencySymbol": money["currencySymbol"],
    }


def serialize_department_rows(
    totals: dict[str, float],
    currency: dict[str, Any],
    allowed: list[str] | None,
) -> list[dict[str, Any]]:
    names = list(finance.REVENUE_DEPARTMENTS)
    if finance.UNIDENTIFIED_DEPARTMENT in totals and (
        allowed is None or finance.UNIDENTIFIED_DEPARTMENT in allowed
    ):
        names = [*names, finance.UNIDENTIFIED_DEPARTMENT]
    if allowed is not None:
        names = [name for name in names if name in allowed]
    visible = {name: float(totals.get(name) or 0.0) for name in names}
    hospital_total = sum(visible.values()) if allowed is not None else sum(
        float(totals.get(name) or 0.0) for name in names
    )
    rows: list[dict[str, Any]] = []
    for name in names:
        amount = visible[name]
        share = (amount / hospital_total) if hospital_total else 0.0
        row = _money(amount, currency)
        row["department"] = name
        row["share"] = round(share, 4)
        rows.append(row)
    return rows


def build_department_revenue(cookie: str, raw_path: str) -> dict[str, Any]:
    _user, allowed = require_revenue_viewer(cookie)
    window = analytics._window_from_query(analytics.parse_request_query(raw_path))
    try:
        odoo = cashier.odoo_reader()
        currency = analytics._hospital_currency(odoo)
        totals = finance.billed_by_department(odoo, window["startDate"], window["endDate"])
    except ApiError as error:
        LOGGER.warning("department revenue source unavailable: %s", error)
        missing = {
            "status": "unavailable",
            "value": None,
            "amount": None,
            "formatted": None,
            "message": "Finance totals are temporarily unavailable.",
        }
        return {
            "status": "ok",
            "period": analytics._period_payload(window),
            "scope": "hospital" if allowed is None else "department",
            "departmentsAllowed": allowed or [],
            "revenue": dict(missing),
            "departments": [],
        }
    except Exception as error:
        LOGGER.warning("department revenue unavailable: %s", error)
        missing = {
            "status": "unavailable",
            "value": None,
            "amount": None,
            "formatted": None,
            "message": "Finance totals are temporarily unavailable.",
        }
        return {
            "status": "ok",
            "period": analytics._period_payload(window),
            "scope": "hospital" if allowed is None else "department",
            "departmentsAllowed": allowed or [],
            "revenue": dict(missing),
            "departments": [],
        }

    rows = serialize_department_rows(totals, currency, allowed)
    hospital_amount = sum(float(row.get("amount") or 0.0) for row in rows)
    return {
        "status": "ok",
        "period": analytics._period_payload(window),
        "scope": "hospital" if allowed is None else "department",
        "departmentsAllowed": allowed or [row["department"] for row in rows],
        "revenue": _money(hospital_amount, currency),
        "departments": rows,
    }
