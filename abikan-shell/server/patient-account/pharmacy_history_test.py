"""Pharmacy sales history helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import pharmacy_history as history


class PharmacyHistoryFilters(unittest.TestCase):
    def test_normalizes_status_aliases(self) -> None:
        self.assertEqual(history._normalize_payment_filter("partial"), "PARTIALLY PAID")
        self.assertEqual(history._normalize_payment_filter("PAID"), "PAID")
        self.assertEqual(history._normalize_dispensing_filter("ready"), "READY TO DISPENSE")
        self.assertEqual(history._normalize_dispensing_filter("dispensed"), "DISPENSED")
        self.assertEqual(history._normalize_buyer_type("other-buyer"), "other")
        self.assertEqual(history._normalize_transaction_type("rx"), "prescription")
        self.assertEqual(history._normalize_care_setting("ipd"), "inpatient")

    def test_classifies_direct_and_prescription(self) -> None:
        self.assertEqual(
            history._transaction_type({"origin": "pharmacy-sale:abc"}, []),
            "direct_sale",
        )
        self.assertEqual(
            history._transaction_type(
                {"origin": ""},
                [{"external_order_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}],
            ),
            "prescription",
        )

    def test_buyer_type_walkin_and_registered(self) -> None:
        self.assertEqual(
            history._buyer_type({"ref": "PHARM-WALKIN:tok", "uuid": "should-ignore", "name": "Walk"}),
            ("other", ""),
        )
        self.assertEqual(
            history._buyer_type({"ref": "ABC200001", "uuid": "patient-1", "name": "Ada"}),
            ("registered", "patient-1"),
        )

    def test_money_keeps_outstanding_separate_from_dispense(self) -> None:
        total, paid, residual = history._money_from_invoice(
            {"amount_total": 12500, "amount_residual": 12500},
            12500,
        )
        self.assertEqual((total, paid, residual), (12500.0, 0.0, 12500.0))
        total, paid, residual = history._money_from_invoice(
            {"amount_total": 4800, "amount_residual": 0},
            4800,
        )
        self.assertEqual((total, paid, residual), (4800.0, 4800.0, 0.0))

    def test_serialize_row_shows_payment_and_dispensing_separately(self) -> None:
        row = history._serialize_row(
            sale={
                "id": 245,
                "name": "PH-000245",
                "date_order": "2026-09-08 10:00:00",
                "origin": "pharmacy-sale:tok",
                "amount_total": 12500,
                "create_uid": [3, "pharmacist.abikan"],
                "care_setting": "opd",
                "partner_id": [9, "Ade Lukman"],
            },
            lines=[
                {
                    "id": 1,
                    "product_id": [11, "Paracetamol"],
                    "product_uom_qty": 10,
                    "qty_delivered": 10,
                    "price_unit": 500,
                    "external_order_id": "pharmacy-sale:tok:0",
                    "name": "Paracetamol",
                },
                {
                    "id": 2,
                    "product_id": [12, "ORS"],
                    "product_uom_qty": 5,
                    "qty_delivered": 5,
                    "price_unit": 1500,
                    "external_order_id": "pharmacy-sale:tok:1",
                    "name": "ORS",
                },
            ],
            invoice={
                "name": "INV/245",
                "payment_state": "not_paid",
                "amount_total": 12500,
                "amount_residual": 12500,
            },
            picking={"state": "done", "create_uid": [3, "pharmacist.abikan"], "date_done": "2026-09-08 11:00:00"},
            partner={"name": "Ade Lukman", "ref": "ABC200100", "uuid": "patient-ade"},
        )
        self.assertEqual(row["paymentStatus"], "UNPAID")
        self.assertEqual(row["dispensingStatus"], "DISPENSED")
        self.assertEqual(row["buyerType"], "registered")
        self.assertEqual(row["lineCount"], 2)
        self.assertEqual(row["amountResidual"], 12500.0)
        self.assertFalse(row["canDeletePrescription"])
        self.assertTrue(row["canRefund"])

    def test_multi_item_sale_is_one_row(self) -> None:
        row = history._serialize_row(
            sale={
                "id": 1045,
                "name": "PH-001045",
                "date_order": "2026-09-09 14:32:00",
                "origin": "pharmacy-sale:multi",
                "amount_total": 5400,
                "create_uid": [3, "pharmacist.abikan"],
                "partner_id": [9, "Patient X"],
            },
            lines=[
                {"id": 10, "product_uom_qty": 10, "qty_delivered": 10, "price_unit": 200, "external_order_id": "pharmacy-sale:multi:0"},
                {"id": 11, "product_uom_qty": 5, "qty_delivered": 5, "price_unit": 500, "external_order_id": "pharmacy-sale:multi:1"},
                {"id": 12, "product_uom_qty": 3, "qty_delivered": 3, "price_unit": 300, "external_order_id": "pharmacy-sale:multi:2"},
            ],
            invoice={"name": "INV/1045", "payment_state": "paid", "amount_total": 5400, "amount_residual": 0},
            picking={"state": "done", "create_uid": [3, "pharmacist.abikan"], "date_done": "2026-09-09 14:40:00"},
            partner={"name": "Patient X", "ref": "ABC200200", "uuid": "px"},
        )
        self.assertEqual(row["lineCount"], 3)
        self.assertEqual(row["quantityTotal"], 18.0)
        self.assertEqual(row["saleName"], "PH-001045")
        self.assertFalse(row["partiallyRefunded"])

    def test_unpaid_undispensed_prescription_can_be_deleted(self) -> None:
        row = history._serialize_row(
            sale={
                "id": 88,
                "name": "S00088",
                "date_order": "2026-09-09 09:00:00",
                "origin": "",
                "amount_total": 2000,
                "create_uid": [2, "doctor"],
                "partner_id": [9, "Ada"],
            },
            lines=[
                {
                    "id": 1,
                    "product_uom_qty": 10,
                    "qty_delivered": 0,
                    "price_unit": 200,
                    "external_order_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                }
            ],
            invoice={"payment_state": "not_paid", "amount_total": 2000, "amount_residual": 2000},
            picking=None,
            partner={"name": "Ada", "ref": "ABC1", "uuid": "p1"},
        )
        self.assertTrue(row["canDeletePrescription"])
        self.assertFalse(row["canRefund"])
        self.assertEqual(row["transactionType"], "prescription")

    def test_paid_prescription_cannot_be_deleted(self) -> None:
        row = history._serialize_row(
            sale={
                "id": 89,
                "name": "S00089",
                "origin": "",
                "amount_total": 2000,
                "partner_id": [9, "Ada"],
            },
            lines=[
                {
                    "id": 1,
                    "product_uom_qty": 10,
                    "qty_delivered": 0,
                    "external_order_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                }
            ],
            invoice={"payment_state": "paid", "amount_total": 2000, "amount_residual": 0},
            picking=None,
            partner={"name": "Ada", "ref": "ABC1", "uuid": "p1"},
        )
        self.assertFalse(row["canDeletePrescription"])

    def test_partial_line_refund_status(self) -> None:
        row = history._serialize_row(
            sale={
                "id": 90,
                "name": "PH-90",
                "origin": "pharmacy-sale:x",
                "amount_total": 4000,
                "note": "ABIKAN_LINE_REFUND:1:3",
                "partner_id": [9, "Ada"],
            },
            lines=[
                {"id": 1, "product_uom_qty": 10, "qty_delivered": 10, "price_unit": 200},
                {"id": 2, "product_uom_qty": 5, "qty_delivered": 5, "price_unit": 400},
            ],
            invoice={"payment_state": "paid", "amount_total": 4000, "amount_residual": 0},
            picking={"state": "done"},
            partner={"name": "Ada", "ref": "ABC1", "uuid": "p1"},
        )
        self.assertEqual(row["refundStatus"], "Partially Refunded")
        self.assertTrue(row["partiallyRefunded"])
        self.assertTrue(row["canRefund"])
        self.assertFalse(row["refunded"])

    def test_window_defaults_to_this_month_when_blank(self) -> None:
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        with patch("pharmacy_history.periods.resolve_period") as resolve:
            resolve.return_value = {
                "period": "this_month",
                "label": "This month",
                "timezone": "Africa/Lagos",
                "startDate": "2026-09-01",
                "endDate": "2026-09-30",
                "utcStartNaive": now.replace(tzinfo=None),
                "utcEndNaive": now.replace(tzinfo=None),
            }
            window = history._window_from_query({})
            resolve.assert_called_once()
            self.assertEqual(window["period"], "this_month")


if __name__ == "__main__":
    unittest.main()
