"""Waived bills show as waived, and the accountant who collected is kept."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import accountant
import cashier_records


def money(amount: float) -> dict:
    return {
        "amount": amount,
        "formatted": f"₦{amount:,.2f}",
        "currencyCode": "NGN",
        "currencySymbol": "₦",
        "decimalPlaces": 2,
    }


class FakeOdoo:
    def __init__(self, moves: list[dict] | None = None) -> None:
        self.moves = moves or []

    def search_read(self, model, domain, fields, limit=0):
        del model, domain, fields, limit
        return self.moves


class WaivedBillLabelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        cashier_records.DB_PATH = str(Path(self.folder.name) / "cashier.sqlite3")

    def tearDown(self) -> None:
        self.folder.cleanup()

    def test_a_recorded_waiver_names_the_accountant_and_nhis(self) -> None:
        cashier_records.record_waiver(
            {
                "invoiceId": 41,
                "billNumber": "INV/2026/00041",
                "patientName": "AYINDE Silifat",
                "hospitalNumber": "ABC205101",
                "patientUuid": "patient-1",
                "amount": "₦10,500.00",
                "amountValue": 10500,
                "waivedBy": "cashier",
            }
        )
        row = {
            "id": 41,
            "number": "INV/2026/00041",
            "total": money(10500),
            "outstanding": money(0),
            "paid": money(10500),
            "paymentStateLabel": "PAID",
        }
        accountant.mark_waived_invoices(FakeOdoo(), [row], True)
        self.assertEqual(row["paymentStateLabel"], "Waived | NHIS")
        self.assertEqual(row["waivedBy"], "cashier")
        self.assertEqual(row["paid"]["amount"], 0)

    def test_a_full_write_off_without_a_name_is_still_waived(self) -> None:
        row = {
            "id": 41,
            "number": "INV/2026/00041",
            "total": money(10500),
            "outstanding": money(0),
            "paid": money(10500),
            "paymentStateLabel": "PAID",
        }
        odoo = FakeOdoo(
            [
                {
                    "ref": "Patient bill discount INV/2026/00041",
                    "amount_total": 10500,
                }
            ]
        )
        accountant.mark_waived_invoices(odoo, [row], False)
        self.assertEqual(row["paymentStateLabel"], "Waived")
        self.assertEqual(row["waivedBy"], "")
        self.assertEqual(row["paid"]["amount"], 0)

    def test_a_partial_discount_stays_paid(self) -> None:
        row = {
            "id": 42,
            "number": "INV/2026/00042",
            "total": money(1000),
            "outstanding": money(0),
            "paid": money(900),
            "paymentStateLabel": "PAID",
        }
        odoo = FakeOdoo(
            [
                {
                    "ref": "Patient bill discount INV/2026/00042",
                    "amount_total": 100,
                }
            ]
        )
        accountant.mark_waived_invoices(odoo, [row], False)
        self.assertEqual(row["paymentStateLabel"], "PAID")

    def test_a_collected_payment_keeps_the_accountant(self) -> None:
        cashier_records.record_collector(15, "cashier")
        self.assertEqual(cashier_records.collectors_for([15, 16]), {15: "cashier"})


if __name__ == "__main__":
    unittest.main()
