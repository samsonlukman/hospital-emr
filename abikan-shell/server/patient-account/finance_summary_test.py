"""Shared Odoo finance totals — empty days are zero, not transport failures."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import xmlrpc.client

import admin_period as periods
import finance_summary as finance
import accountant as cashier


def _none_fault() -> xmlrpc.client.Fault:
    return xmlrpc.client.Fault(1, "TypeError: cannot marshal None unless allow_none is enabled")


class FinanceDefinitions(unittest.TestCase):
    def test_today_and_yesterday_and_week_and_month_use_lagos_dates(self) -> None:
        now = datetime(2026, 9, 6, 22, 10, tzinfo=timezone.utc)
        today = periods.resolve_period("today", now=now)
        yesterday = periods.resolve_period("yesterday", now=now)
        week = periods.resolve_period("this_week", now=now)
        month = periods.resolve_period("this_month", now=now)
        custom = periods.resolve_period("custom", start="2026-09-01", end="2026-09-06", now=now)
        self.assertEqual(today["startDate"], "2026-09-06")
        self.assertEqual(today["endDate"], "2026-09-06")
        self.assertEqual(yesterday["startDate"], "2026-09-05")
        self.assertEqual(week["startDate"], "2026-08-31")
        self.assertEqual(week["endDate"], "2026-09-06")
        self.assertEqual(month["startDate"], "2026-09-01")
        self.assertEqual(month["endDate"], "2026-09-30")
        self.assertEqual(custom["endDate"], "2026-09-06")
        self.assertEqual(finance.hospital_business_date(now), "2026-09-06")
        self.assertEqual(
            finance.billed_domain(today["startDate"], today["endDate"])[2],
            ("invoice_date", ">=", "2026-09-06"),
        )
        self.assertEqual(
            finance.collected_domain(today["startDate"], today["endDate"])[3],
            ("date", ">=", "2026-09-06"),
        )
        self.assertNotIn("invoice_date", str(finance.outstanding_domain()))

    def test_accountant_and_analytics_share_the_same_odoo_domains(self) -> None:
        self.assertEqual(
            finance.collected_domain("2026-09-06", "2026-09-06"),
            [
                ("partner_type", "=", "customer"),
                ("payment_type", "=", "inbound"),
                ("state", "=", "posted"),
                ("date", ">=", "2026-09-06"),
                ("date", "<=", "2026-09-06"),
            ],
        )
        from pathlib import Path

        source = Path(cashier.__file__).read_text(encoding="utf-8")
        self.assertIn("finance.collected_domain", source)
        self.assertIn("finance.hospital_business_date", source)
        analytics_source = Path(finance.__file__).with_name("admin_analytics.py").read_text(encoding="utf-8")
        self.assertIn("finance.billed_total", analytics_source)
        self.assertIn("finance.collected_total", analytics_source)
        self.assertIn("finance.outstanding_total", analytics_source)


class EmptyAggregate(unittest.TestCase):
    def test_none_marshal_from_empty_read_group_is_zero(self) -> None:
        odoo = MagicMock()
        odoo.uid = 2
        odoo.models.execute_kw.side_effect = _none_fault()
        odoo.search_read.return_value = []
        self.assertEqual(finance.billed_total(odoo, "2026-09-06", "2026-09-06"), 0.0)
        self.assertEqual(finance.collected_total(odoo, "2026-09-06", "2026-09-06"), 0.0)
        odoo.search_read.assert_called()

    def test_todays_payment_is_included_and_excluded_outside_the_range(self) -> None:
        odoo = MagicMock()
        odoo.uid = 2
        odoo.models.execute_kw.side_effect = [
            [{"amount": 1500.0}],  # inbound today
            [{"amount": 0.0}],  # outbound today
            [{"amount": 0.0}],  # inbound outside
            [{"amount": 0.0}],  # outbound outside
        ]
        self.assertEqual(finance.collected_total(odoo, "2026-09-06", "2026-09-06"), 1500.0)
        self.assertEqual(finance.collected_total(odoo, "2026-09-01", "2026-09-05"), 0.0)
        today_domain = odoo.models.execute_kw.call_args_list[0][0][5][0]
        outside_domain = odoo.models.execute_kw.call_args_list[2][0][5][0]
        self.assertEqual(today_domain, finance.collected_domain("2026-09-06", "2026-09-06"))
        self.assertEqual(outside_domain, finance.collected_domain("2026-09-01", "2026-09-05"))
        self.assertTrue(any(item == ("date", "<=", "2026-09-05") for item in outside_domain))
        outbound_today = odoo.models.execute_kw.call_args_list[1][0][5][0]
        self.assertEqual(
            outbound_today,
            finance.collected_outbound_domain("2026-09-06", "2026-09-06"),
        )

    def test_other_odoo_faults_are_not_treated_as_zero(self) -> None:
        odoo = MagicMock()
        odoo.uid = 2
        odoo.models.execute_kw.side_effect = xmlrpc.client.Fault(1, "Access Denied")
        with self.assertRaises(xmlrpc.client.Fault):
            finance.collected_total(odoo, "2026-09-06", "2026-09-06")


if __name__ == "__main__":
    unittest.main()
