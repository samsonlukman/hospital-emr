"""Deleting a laboratory order records the reason and who deleted it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deleted_lab_orders
import laboratory
from server import ApiError


ORDER = {
    "uuid": "order-1",
    "orderNumber": "ORD-9",
    "testName": "Malaria parasite",
    "patientUuid": "patient-1",
    "patientName": "Adaeze Okafor",
    "mrn": "ABC1",
    "accession": "",
}


class DeleteLabOrderTests(unittest.TestCase):
    def test_a_reason_is_required(self) -> None:
        with (
            patch.object(laboratory, "require_lab_user", return_value={"username": "lab"}),
            self.assertRaises(ApiError) as caught,
        ):
            laboratory.delete_lab_order("order-1", {"reason": "no"}, "cookie")
        self.assertEqual(caught.exception.code, "reason_required")

    def test_a_processed_order_cannot_be_deleted(self) -> None:
        processed = {**ORDER, "accession": "A-1"}
        with (
            patch.object(laboratory, "require_lab_user", return_value={"username": "lab"}),
            patch.object(laboratory, "load_lab_order", return_value=processed),
            self.assertRaises(ApiError) as caught,
        ):
            laboratory.delete_lab_order("order-1", {"reason": "Entered on the wrong patient"}, "cookie")
        self.assertEqual(caught.exception.code, "order_in_progress")

    def test_a_paid_bill_blocks_deletion(self) -> None:
        class PaidOdoo:
            def search_read(self, model, domain, fields, limit=0):
                del model, domain, fields, limit
                return [{"id": 1}]

            def read(self, model, ids, fields):
                del model, ids, fields
                return [
                    {
                        "id": 9,
                        "move_type": "out_invoice",
                        "state": "posted",
                        "payment_state": "paid",
                        "amount_residual": 0,
                        "amount_total": 1500,
                    }
                ]

        with (
            patch.object(laboratory, "require_lab_user", return_value={"username": "lab"}),
            patch.object(laboratory, "load_lab_order", return_value=ORDER),
            patch.object(laboratory, "_result_order_uuids", return_value=set()),
            patch.object(laboratory, "odoo_reader", return_value=PaidOdoo()),
            patch.object(
                laboratory,
                "find_existing_sale",
                return_value=({}, {"id": 3, "state": "sale", "invoice_ids": [9]}),
            ),
            self.assertRaises(ApiError) as caught,
        ):
            laboratory.delete_lab_order("order-1", {"reason": "Entered on the wrong patient"}, "cookie")
        self.assertEqual(caught.exception.code, "bill_has_payment")

    def test_an_unbilled_order_is_removed_and_recorded(self) -> None:
        voided: list[str] = []
        with tempfile.TemporaryDirectory() as folder:
            deleted_lab_orders.DB_PATH = str(Path(folder) / "deleted.sqlite3")
            with (
                patch.object(laboratory, "require_lab_user", return_value={"username": "lab"}),
                patch.object(laboratory, "load_lab_order", return_value=ORDER),
                patch.object(laboratory, "_result_order_uuids", return_value=set()),
                patch.object(laboratory, "odoo_reader", return_value=object()),
                patch.object(laboratory, "find_existing_sale", return_value=None),
                patch.object(laboratory, "_void_lab_order", side_effect=lambda order_uuid, cookie: voided.append(order_uuid)),
            ):
                result = laboratory.delete_lab_order(
                    "order-1",
                    {"reason": "Entered on the wrong patient", "patientUuid": "patient-1"},
                    "cookie",
                )
                listed = deleted_lab_orders.list_deletions()
        self.assertEqual(voided, ["order-1"])
        self.assertEqual(result["deleted"]["deletedBy"], "lab")
        self.assertEqual(result["deleted"]["reason"], "Entered on the wrong patient")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["testName"], "Malaria parasite")
        self.assertEqual(listed["items"][0]["hospitalNumber"], "ABC1")


if __name__ == "__main__":
    unittest.main()
