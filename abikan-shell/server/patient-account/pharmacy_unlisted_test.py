"""Typed medicines must be visible to Pharmacy without a bill."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pharmacy as dispensary
import pharmacy_unlisted as unlisted


class PharmacyUnlistedTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-unlisted-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        unlisted.reset_for_tests(self.db)

    def tearDown(self) -> None:
        Path(self.db).unlink(missing_ok=True)

    def test_typed_name_is_not_in_pharmacy(self) -> None:
        self.assertTrue(
            unlisted.not_in_pharmacy_order(
                {"drugNonCoded": "Calamine lotion extra", "drugUuid": "", "drugName": "Calamine lotion extra"},
                catalogue_ids={"coded-1"},
            )
        )
        self.assertFalse(
            unlisted.not_in_pharmacy_order(
                {"drugNonCoded": "", "drugUuid": "coded-1", "drugName": "Paracetamol"},
                catalogue_ids={"coded-1"},
            )
        )
        self.assertFalse(
            unlisted.not_in_pharmacy_order(
                {"drugNonCoded": "", "drugUuid": "", "drugName": "Paracetamol"},
                catalogue_ids={"coded-1"},
            )
        )
        self.assertFalse(
            unlisted.not_in_pharmacy_order(
                {"drugNonCoded": "", "drugUuid": "other-drug", "drugName": "Outside list"},
                catalogue_ids={"coded-1"},
            )
        )

    def test_remember_and_list_by_encounter(self) -> None:
        unlisted.remember(
            {
                "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "patientUuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "encounterUuid": "enc-1",
                "drugName": "Calamine lotion extra",
                "ordered": "2026-09-25",
            }
        )
        rows = unlisted.list_rows(patient_uuid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", encounter_uuid="enc-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drugName"], "Calamine lotion extra")
        unlisted.forget("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(unlisted.list_rows(patient_uuid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), [])

    def test_serialize_hides_bill_and_blocks_dispense(self) -> None:
        payload = dispensary.serialize_prescription(
            clinical={
                "uuid": "order-1",
                "orderNumber": "ORD-1",
                "patientUuid": "patient-1",
                "patientName": "Test Patient",
                "mrn": "ABC200016",
                "prescriber": "Clinical Doctor",
                "ordered": "2026-09-25",
                "encounterUuid": "enc-1",
                "drugName": "Calamine lotion extra",
                "drugNonCoded": "Calamine lotion extra",
                "drugUuid": "",
                "quantity": 1,
                "quantityUnits": "Tablet",
            },
            line={"product_uom_qty": 10, "qty_delivered": 0},
            invoice={"payment_state": "not_paid", "amount_residual": 500},
            picking={"state": "assigned"},
            on_hand=40,
            sale={"id": 99, "name": "S00099"},
            catalogue_ids={"coded-1"},
        )
        self.assertTrue(payload["notInPharmacy"])
        self.assertFalse(payload["canDispense"])
        self.assertEqual(payload["dispensingStatus"], unlisted.NOT_IN_PHARMACY_STATUS)
        self.assertEqual(payload["paymentStatus"], unlisted.NOT_BILLED_STATUS)
        self.assertEqual(payload["blockReason"], unlisted.NOT_IN_PHARMACY_REASON)
        self.assertIsNone(payload["saleId"])
        self.assertEqual(payload["groupKey"], "enc-1")

    def test_group_status_ignores_unlisted_when_pharmacy_line_is_ready(self) -> None:
        status = dispensary.group_dispensing_status(
            [
                {"dispensingStatus": "READY TO DISPENSE", "notInPharmacy": False},
                {
                    "dispensingStatus": unlisted.NOT_IN_PHARMACY_STATUS,
                    "notInPharmacy": True,
                    "paymentStatus": unlisted.NOT_BILLED_STATUS,
                },
            ]
        )
        self.assertEqual(status, "READY TO DISPENSE")
        payment = dispensary._group_payment_status(
            [
                {"paymentStatus": "UNPAID", "notInPharmacy": False},
                {"paymentStatus": unlisted.NOT_BILLED_STATUS, "notInPharmacy": True},
            ],
            {"paymentStatus": "UNPAID"},
        )
        self.assertEqual(payment, "UNPAID")
