"""Hospital Admin analytics and staff-audit read facades — mocked sources."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import admin_analytics as analytics
import admin_audit
import admin_period as periods
import hospital_admin as admin
import openmrs_sql
from server import ApiError


def _user(roles: list[str], privileges: list[str], username: str = "hospitaladmin.abikan") -> dict:
    return {
        "uuid": f"user-{username}",
        "username": username,
        "roles": roles,
        "privileges": privileges,
    }


HOSPITAL_ADMIN = _user(
    ["Abikan:Hospital Admin"],
    ["abikan:admin:staff", "abikan:admin:analytics", "abikan:admin:audit-read"],
)
DOCTOR = _user(["Abikan:Doctor"], ["app:clinical"], "doctor.abikan")
NURSE = _user(["Abikan:Nursing"], ["app:adt"], "nurse.abikan")
LAB = _user(["Abikan:Laboratory"], ["app:lab-lite"], "lab.abikan")
PHARMACY = _user(["Abikan:Pharmacy"], ["bahmni:clinical:dispense"], "pharmacy.abikan")
ACCOUNTANT = _user(["Abikan:Accountant"], ["abikan:accountant"], "accountant.abikan")


class PeriodWindows(unittest.TestCase):
    def test_lagos_today_starts_at_previous_utc_evening(self) -> None:
        now = datetime(2026, 8, 27, 5, 30, tzinfo=timezone.utc)
        window = periods.resolve_period("today", now=now)
        self.assertEqual(window["startDate"], "2026-08-27")
        self.assertEqual(window["endDate"], "2026-08-27")
        self.assertEqual(window["timezone"], "Africa/Lagos")
        self.assertEqual(
            window["utcStartNaive"],
            datetime(2026, 8, 26, 23, 0, 0),
        )
        self.assertEqual(
            window["utcEndNaive"],
            datetime(2026, 8, 27, 23, 0, 0),
        )

    def test_utc_just_before_lagos_midnight_belongs_to_previous_lagos_day(self) -> None:
        before = datetime(2026, 8, 26, 22, 59, tzinfo=timezone.utc)
        after = datetime(2026, 8, 26, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(periods.hospital_today(before).isoformat(), "2026-08-26")
        self.assertEqual(periods.hospital_today(after).isoformat(), "2026-08-27")
        yesterday = periods.resolve_period("yesterday", now=after)
        self.assertEqual(yesterday["startDate"], "2026-08-26")
        self.assertEqual(yesterday["utcStartNaive"], datetime(2026, 8, 25, 23, 0, 0))
        self.assertEqual(yesterday["utcEndNaive"], datetime(2026, 8, 26, 23, 0, 0))

    def test_this_week_starts_monday_in_lagos(self) -> None:
        thursday = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        window = periods.resolve_period("this_week", now=thursday)
        self.assertEqual(window["startDate"], "2026-08-24")
        self.assertEqual(window["endDate"], "2026-08-30")
        self.assertEqual(window["weekStartsOn"], "Monday")

    def test_custom_range_is_inclusive_and_converted_to_utc(self) -> None:
        window = periods.resolve_period(
            "custom",
            start="2026-08-01",
            end="2026-08-02",
            now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(window["startDate"], "2026-08-01")
        self.assertEqual(window["endDate"], "2026-08-02")
        self.assertEqual(window["utcStartNaive"], datetime(2026, 7, 31, 23, 0, 0))
        self.assertEqual(window["utcEndNaive"], datetime(2026, 8, 2, 23, 0, 0))

    def test_rejects_inverted_custom_range(self) -> None:
        with self.assertRaises(ApiError) as caught:
            periods.resolve_period("custom", start="2026-08-10", end="2026-08-01")
        self.assertEqual(caught.exception.code, "invalid_period")


class Authorization(unittest.TestCase):
    def test_department_users_are_denied_analytics_and_audit(self) -> None:
        for user in (DOCTOR, NURSE, LAB, PHARMACY, ACCOUNTANT):
            with patch.object(admin, "require_hospital_admin", side_effect=ApiError(403, "forbidden", "no")):
                with self.assertRaises(ApiError) as caught:
                    analytics.require_admin_analytics("cookie")
                self.assertEqual(caught.exception.status, 403)
            with patch.object(admin, "require_hospital_admin", return_value=user):
                with self.assertRaises(ApiError) as caught:
                    analytics.require_admin_analytics("cookie")
                self.assertEqual(caught.exception.status, 403)
                with self.assertRaises(ApiError) as audit_denied:
                    admin.require_admin_audit_read("cookie")
                self.assertEqual(audit_denied.exception.status, 403)

    def test_hospital_admin_with_dedicated_privileges_is_allowed(self) -> None:
        with patch.object(admin, "require_hospital_admin", return_value=HOSPITAL_ADMIN):
            self.assertEqual(analytics.require_admin_analytics("cookie")["username"], "hospitaladmin.abikan")
            self.assertEqual(admin.require_admin_audit_read("cookie")["username"], "hospitaladmin.abikan")

    def test_hospital_admin_without_analytics_privilege_is_denied(self) -> None:
        staff_only = _user(["Abikan:Hospital Admin"], ["abikan:admin:staff"])
        with patch.object(admin, "require_hospital_admin", return_value=staff_only):
            with self.assertRaises(ApiError) as caught:
                analytics.require_admin_analytics("cookie")
            self.assertEqual(caught.exception.status, 403)

    def test_unauthenticated_is_denied(self) -> None:
        with patch.object(
            admin,
            "require_hospital_admin",
            side_effect=ApiError(401, "unauthenticated", "Sign in required."),
        ):
            with self.assertRaises(ApiError) as caught:
                analytics.require_admin_analytics("cookie")
            self.assertEqual(caught.exception.status, 401)


class Aggregations(unittest.TestCase):
    def test_registrations_consultations_admissions_discharges_and_orders(self) -> None:
        counts = {
            "patient": 3,
            "visit": 5,
            "Consultation": 4,
            "ADMISSION": 2,
            "DISCHARGE": 1,
            "Lab Order": 6,
            "Drug Order": 7,
        }

        def fetch_int(sql: str, params: tuple = ()) -> int:
            if "FROM patient" in sql:
                return counts["patient"]
            if "FROM visit" in sql:
                self.assertIn("OPD", params)
                self.assertNotIn("IPD", params)
                self.assertNotIn("EMERGENCY", params)
                return counts["visit"]
            if "encounter_type" in sql:
                return counts[str(params[0])]
            if "Lab Order" in params:
                return counts["Lab Order"]
            if "Drug Order" in params:
                return counts["Drug Order"]
            raise AssertionError(sql)

        occupancy = {
            "status": "ok",
            "value": 1,
            "occupied": 1,
            "total": 27,
            "available": 26,
            "rate": 0.037,
            "asOf": "current",
            "label": "1 / 27",
        }
        finance = {
            "billed": {"status": "ok", "value": 1000, "amount": 1000, "formatted": "1,000.00 ₦"},
            "collected": {"status": "ok", "value": 400, "amount": 400, "formatted": "400.00 ₦"},
            "outstanding": {
                "status": "ok",
                "value": 600,
                "amount": 600,
                "formatted": "600.00 ₦",
                "asOf": "current",
                "message": "current residual",
            },
        }
        dispensed = {"status": "ok", "value": 2, "movements": 2}
        with (
            patch.object(analytics, "require_admin_analytics", return_value=HOSPITAL_ADMIN),
            patch.object(openmrs_sql, "fetch_int", side_effect=fetch_int),
            patch.object(analytics, "_current_occupancy", return_value=occupancy),
            patch.object(analytics, "_finance_totals", return_value=finance),
            patch.object(analytics, "_dispensing", return_value=dispensed),
        ):
            overview = analytics.build_overview(
                "cookie",
                {"period": ["today"]},
            )
        self.assertEqual(overview["patientsRegistered"]["value"], 3)
        self.assertEqual(overview["opdVisits"]["value"], 5)
        self.assertEqual(overview["consultations"]["value"], 4)
        self.assertEqual(overview["admissions"]["value"], 2)
        self.assertEqual(overview["discharges"]["value"], 1)
        self.assertEqual(overview["labOrders"]["value"], 6)
        self.assertEqual(overview["prescriptions"]["value"], 7)
        self.assertEqual(overview["occupancy"]["asOf"], "current")
        self.assertEqual(overview["occupancy"]["occupied"], 1)
        self.assertEqual(overview["occupancy"]["total"], 27)
        self.assertEqual(overview["billed"]["value"], 1000)
        self.assertEqual(overview["collected"]["value"], 400)
        self.assertEqual(overview["outstanding"]["asOf"], "current")
        self.assertEqual(overview["dispensed"]["value"], 2)

    def test_sql_failure_is_unavailable_not_zero(self) -> None:
        with (
            patch.object(analytics, "require_admin_analytics", return_value=HOSPITAL_ADMIN),
            patch.object(
                openmrs_sql,
                "fetch_int",
                side_effect=openmrs_sql.OpenmrsSqlError("connect_failed"),
            ),
            patch.object(
                analytics,
                "_finance_totals",
                return_value={
                    "billed": {"status": "unavailable", "value": None, "message": "Finance totals are temporarily unavailable."},
                    "collected": {"status": "unavailable", "value": None, "message": "Finance totals are temporarily unavailable."},
                    "outstanding": {
                        "status": "unavailable",
                        "value": None,
                        "asOf": "current",
                        "message": "Finance totals are temporarily unavailable.",
                    },
                },
            ),
            patch.object(
                analytics,
                "_dispensing",
                return_value={"status": "unavailable", "value": None, "movements": None},
            ),
        ):
            overview = analytics.build_overview("cookie", {"period": ["today"]})
        self.assertEqual(overview["patientsRegistered"]["status"], "unavailable")
        self.assertIsNone(overview["patientsRegistered"]["value"])
        self.assertEqual(overview["consultations"]["status"], "unavailable")
        self.assertEqual(overview["occupancy"]["status"], "unavailable")
        self.assertEqual(overview["labOrders"]["status"], "unavailable")

    def test_order_counts_use_order_action_not_action_column(self) -> None:
        captured: list[str] = []

        def fetch_int(sql: str, params: tuple = ()) -> int:
            captured.append(sql)
            return 4

        window = periods.resolve_period(
            "today", now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        )
        with patch.object(openmrs_sql, "fetch_int", side_effect=fetch_int):
            metric = analytics._count_orders("Lab Order", window)
        self.assertEqual(metric["value"], 4)
        sql = captured[0]
        self.assertIn("o.order_action <> 'DISCONTINUE'", sql)
        self.assertNotIn("o.action", sql)

    def test_current_occupancy_queries_live_assignment_map(self) -> None:
        def fetch_int(sql: str, params: tuple = ()) -> int:
            if "FROM bed WHERE voided = 0" in sql:
                return 27
            if "date_stopped IS NULL" in sql:
                return 1
            raise AssertionError(sql)

        with patch.object(openmrs_sql, "fetch_int", side_effect=fetch_int):
            occupancy = analytics._current_occupancy()
        self.assertEqual(occupancy["occupied"], 1)
        self.assertEqual(occupancy["total"], 27)
        self.assertEqual(occupancy["asOf"], "current")
        self.assertAlmostEqual(occupancy["rate"], 1 / 27, places=4)

    def test_collected_uses_payment_sum_not_invoice_payment_state(self) -> None:
        odoo = MagicMock()
        odoo.uid = 2
        odoo.search_read.return_value = [
            {"name": "NGN", "symbol": "$", "decimal_places": 2, "position": "before"}
        ]
        with (
            patch.object(analytics.cashier, "odoo_reader", return_value=odoo),
            patch.object(analytics.finance, "billed_total", return_value=271874) as billed,
            patch.object(analytics.finance, "collected_total", return_value=45000) as collected,
            patch.object(analytics.finance, "outstanding_total", return_value=65398),
            patch.object(analytics.finance, "billed_by_department", return_value={"Laboratory": 271874}),
        ):
            window = periods.resolve_period(
                "today", now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
            )
            finance = analytics._finance_totals(window)
        self.assertEqual(finance["billed"]["amount"], 271874)
        self.assertEqual(finance["collected"]["amount"], 45000)
        self.assertEqual(finance["outstanding"]["amount"], 65398)
        self.assertEqual(finance["outstanding"]["asOf"], "current")
        self.assertTrue(finance["billed"]["formatted"].startswith("₦"))
        self.assertEqual(finance["billed"]["currencyCode"], "NGN")
        self.assertNotIn("$", finance["billed"]["formatted"])
        billed.assert_called_once_with(odoo, "2026-08-27", "2026-08-27")
        collected.assert_called_once_with(odoo, "2026-08-27", "2026-08-27")
        self.assertIn(("payment_type", "=", "inbound"), analytics.finance.collected_domain("2026-08-27", "2026-08-27"))
        self.assertNotIn(("payment_state", "=", "paid"), analytics.finance.collected_domain("2026-08-27", "2026-08-27"))

    def test_empty_today_is_zero_not_unavailable(self) -> None:
        odoo = MagicMock()
        odoo.uid = 2
        odoo.search_read.return_value = [
            {"name": "NGN", "symbol": "₦", "decimal_places": 2, "position": "before"}
        ]
        with (
            patch.object(analytics.cashier, "odoo_reader", return_value=odoo),
            patch.object(analytics.finance, "billed_total", return_value=0.0),
            patch.object(analytics.finance, "collected_total", return_value=0.0),
            patch.object(analytics.finance, "outstanding_total", return_value=0.0),
            patch.object(analytics.finance, "billed_by_department", return_value={}),
        ):
            window = periods.resolve_period(
                "today", now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
            )
            finance = analytics._finance_totals(window)
        self.assertEqual(finance["billed"]["status"], "ok")
        self.assertEqual(finance["billed"]["amount"], 0)
        self.assertEqual(finance["collected"]["amount"], 0)
        self.assertEqual(finance["outstanding"]["amount"], 0)
        self.assertTrue(finance["billed"]["formatted"].startswith("₦0.00") or finance["billed"]["formatted"].endswith("0.00"))

    def test_odoo_failure_is_unavailable_not_zero(self) -> None:
        with patch.object(
            analytics.cashier,
            "odoo_reader",
            side_effect=ApiError(503, "odoo_error", "Financial service is unavailable."),
        ):
            window = periods.resolve_period(
                "today", now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
            )
            finance = analytics._finance_totals(window)
        self.assertEqual(finance["billed"]["status"], "unavailable")
        self.assertIsNone(finance["billed"]["value"])
        self.assertEqual(finance["collected"]["status"], "unavailable")
        self.assertEqual(finance["outstanding"]["status"], "unavailable")

    def test_one_metric_failure_does_not_hide_the_others(self) -> None:
        odoo = MagicMock()
        odoo.uid = 2
        odoo.search_read.return_value = [
            {"name": "NGN", "symbol": "₦", "decimal_places": 2, "position": "before"}
        ]
        with (
            patch.object(analytics.cashier, "odoo_reader", return_value=odoo),
            patch.object(analytics.finance, "billed_total", side_effect=RuntimeError("billed broken")),
            patch.object(analytics.finance, "collected_total", return_value=5400.0),
            patch.object(analytics.finance, "outstanding_total", return_value=100.0),
            patch.object(analytics.finance, "billed_by_department", return_value={"Laboratory": 5400.0}),
        ):
            window = periods.resolve_period(
                "today", now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
            )
            finance = analytics._finance_totals(window)
        self.assertEqual(finance["billed"]["status"], "unavailable")
        self.assertEqual(finance["collected"]["status"], "ok")
        self.assertEqual(finance["collected"]["amount"], 5400)
        self.assertEqual(finance["outstanding"]["status"], "ok")


class StaffAuditRead(unittest.TestCase):
    def test_audit_read_returns_redacted_staff_events(self) -> None:
        payload = {
            "total": 1,
            "limit": 100,
            "offset": 0,
            "events": [
                {
                    "event_id": "evt-1",
                    "occurred_at": "2026-08-27T01:18:55.738+00:00",
                    "actor_username": "hospitaladmin.abikan",
                    "target_username": "doctor.test",
                    "action": "ADMIN_DISABLE_USER",
                    "outcome": "success",
                    "error_code": "",
                    "request_id": "req-1",
                    "previous_state": {"enabled": True, "password": "secret"},
                    "new_state": {"enabled": False},
                    "details": {"cookie": "JSESSIONID=abc"},
                }
            ],
        }
        with (
            patch.object(admin, "require_admin_audit_read", return_value=HOSPITAL_ADMIN),
            patch.object(admin_audit, "list_admin_events", return_value=payload),
        ):
            result = admin.build_staff_audit("cookie", {})
        event = result["events"][0]
        self.assertEqual(event["actionLabel"], "Disabled staff account")
        self.assertEqual(event["actorUsername"], "hospitaladmin.abikan")
        self.assertEqual(event["targetUsername"], "doctor.test")
        self.assertEqual(event["requestId"], "req-1")
        self.assertEqual(event["previous"]["enabled"], True)
        self.assertNotIn("password", event["previous"])
        self.assertNotIn("cookie", json.dumps(event))

    def test_list_admin_events_redacts_secrets_on_read(self) -> None:
        import tempfile
        from pathlib import Path

        directory = tempfile.TemporaryDirectory()
        path = str(Path(directory.name) / "admin-audit.sqlite3")
        event_id = admin_audit.record_admin_event(
            actor={"uuid": "a1", "username": "hospitaladmin.abikan"},
            target_user_uuid="u1",
            target_username="nurse.test",
            action="ADMIN_CREATE_USER",
            previous_state={},
            new_state={"password": "not-a-real-password", "enabled": True},
            details={"token": "abc", "departments": ["nursing"]},
            outcome="success",
            request_id="req-secret",
            path=path,
        )
        listed = admin_audit.list_admin_events(path=path, limit=10)
        directory.cleanup()
        row = listed["events"][0]
        self.assertEqual(row["event_id"], event_id)
        self.assertEqual(row["new_state"]["password"], "[REDACTED]")
        self.assertEqual(row["details"]["token"], "[REDACTED]")
        self.assertEqual(row["details"]["departments"], ["nursing"])


class Routes(unittest.TestCase):
    def test_server_registers_admin_analytics_and_audit_routes(self) -> None:
        from pathlib import Path
        import server as server_module

        text = Path(server_module.__file__).read_text(encoding="utf-8")
        self.assertIn('parts == ["admin", "analytics", "overview"]', text)
        self.assertIn('parts == ["admin", "analytics", "reception"]', text)
        self.assertIn('parts == ["admin", "analytics", "inpatient"]', text)
        self.assertIn('parts == ["admin", "audit"]', text)
        self.assertIn("build_overview", text)
        self.assertIn("build_staff_audit", text)
