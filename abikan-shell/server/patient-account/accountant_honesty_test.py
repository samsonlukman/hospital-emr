"""Accountant honesty helpers — no Odoo writes."""

from __future__ import annotations

import unittest

import server as core


class AggregateByCurrency(unittest.TestCase):
    def test_does_not_sum_naira_and_dollars(self) -> None:
        naira = core.format_money(20000, {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "after"})
        dollars = core.format_money(100, {"code": "USD", "symbol": "$", "decimalPlaces": 2, "position": "before"})
        totals = core.aggregate_by_currency([naira, dollars])
        self.assertEqual(len(totals), 2)
        self.assertEqual(totals[0]["currencyCode"], "NGN")
        self.assertEqual(totals[0]["amount"], 20000)
        self.assertEqual(totals[1]["currencyCode"], "USD")
        self.assertEqual(totals[1]["amount"], 100)
        self.assertFalse(any("20,100" in row["formatted"] for row in totals))

    def test_sums_only_the_same_currency(self) -> None:
        first = core.format_money(10, {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "after"})
        second = core.format_money(20, {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "after"})
        totals = core.aggregate_by_currency([first, second])
        self.assertEqual(len(totals), 1)
        self.assertEqual(totals[0]["amount"], 30)
        self.assertEqual(totals[0]["currencyCode"], "NGN")


class PaymentState(unittest.TestCase):
    def test_reversed_is_not_paid(self) -> None:
        self.assertEqual(core.payment_state_label("reversed"), "REVERSED")
        self.assertEqual(core.payment_state_label("paid"), "PAID")
        self.assertEqual(core.payment_state_label("not_paid"), "UNPAID")
        self.assertEqual(core.payment_state_label("partial"), "PARTIALLY PAID")
        self.assertNotEqual(core.payment_state_label("reversed"), "PAID")


class StaffClock(unittest.TestCase):
    def test_odoo_utc_clock_becomes_lagos_time(self) -> None:
        import accountant as cashier

        self.assertEqual(
            cashier.staff_instant("2026-10-12 16:55:55"),
            "2026-10-12T17:55:55+01:00",
        )

    def test_a_date_without_a_time_is_not_turned_into_one_am(self) -> None:
        import accountant as cashier

        self.assertEqual(cashier.staff_instant("2026-10-12"), "2026-10-12")


class OutstandingBillOrder(unittest.TestCase):
    def test_sorts_by_time_not_highest_amount(self) -> None:
        import accountant as cashier

        older_large = {
            "id": 1,
            "date": "2026-09-10",
            "createDate": "2026-09-10 08:00:00",
            "outstanding": {"amount": 50000},
        }
        newer_small = {
            "id": 2,
            "date": "2026-09-12",
            "createDate": "2026-09-12 09:15:00",
            "outstanding": {"amount": 2000},
        }
        ordered = cashier.sort_outstanding_bills([older_large, newer_small])
        self.assertEqual([row["id"] for row in ordered], [2, 1])


class PaymentReceiptPdf(unittest.TestCase):
    def test_lists_every_bill_and_the_collected_total(self) -> None:
        import accountant as cashier

        currency = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
        pdf = cashier._payment_receipt_pdf(
            {
                "name": "PAY/001",
                "amount": 3500,
                "date": "2026-10-14",
                "journal_id": [1, "Cash"],
            },
            [
                {"name": "INV/100", "amount_total": 1500, "invoice_origin": "Consultation"},
                {"name": "INV/101", "amount_total": 2000, "invoice_origin": "Laboratory"},
            ],
            currency,
            {"name": "Maryam Popoola", "ref": "ABC205138"},
            {},
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"INV/100", pdf)
        self.assertIn(b"INV/101", pdf)
        self.assertIn(b"Consultation", pdf)
        self.assertIn(b"Laboratory", pdf)
        self.assertIn(b"Total collected", pdf)
        self.assertIn(b"NGN 3,500.00", pdf)
        self.assertIn(b"Payment receipt", pdf)
        self.assertIn(b"/Contents 4 0 R", pdf)
        self.assertNotIn(b"/XObject << /Im1 7 0 R >> /Contents", pdf)

    def test_shows_the_department_and_what_was_paid_for(self) -> None:
        import accountant as cashier

        currency = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
        pdf = cashier._payment_receipt_pdf(
            {
                "name": "PBNK1/2026/00135",
                "amount": 8000,
                "date": "2026-10-14",
                "journal_id": [1, "Bank"],
            },
            [
                {
                    "name": "INV/2026/00282",
                    "amount_total": 8000,
                    "invoice_origin": "S00411",
                    "department": "Accommodation",
                    "lines": [{"name": "Bronze 208 · Bed 01 · 8 Oct", "amount": 8000, "quantity": 1}],
                }
            ],
            currency,
            {"name": "Taiwo Hassan", "ref": "ABC204835"},
            {"collectedAt": "2026-10-14T14:36:27+01:00"},
        )
        self.assertIn(b"Accommodation", pdf)
        self.assertIn(b"Bronze 208", pdf)
        self.assertIn(b"Bed 01", pdf)
        self.assertIn(b"14/10/2026 14:36", pdf)
        self.assertNotIn(b"S00411", pdf)
        self.assertNotIn("2026-10-14T".encode("latin-1"), pdf)


if __name__ == "__main__":
    unittest.main()
