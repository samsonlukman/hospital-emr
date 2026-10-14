"""Pharmacy can add a medicine to a prescription and replace one that is still open."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pharmacy as dispensary
import pharmacy_rx_edit as rx_edit
import pharmacy_rx_links as rx_links
from server import ApiError


class PharmacyRxLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-rx-link-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        rx_links.reset_for_tests(self.db)

    def tearDown(self) -> None:
        Path(self.db).unlink(missing_ok=True)

    def test_added_medicine_stays_on_the_prescription(self) -> None:
        rx_links.remember("new-order", "encounter-1")
        self.assertEqual(rx_links.group_for("new-order"), "encounter-1")
        self.assertEqual(rx_links.members("encounter-1"), ["new-order"])
        self.assertEqual(rx_links.group_for("encounter-1"), "")

    def test_replaced_medicine_resolves_to_the_latest(self) -> None:
        rx_links.replace("old-order", "new-order", "encounter-1")
        self.assertEqual(rx_links.resolve("old-order"), "new-order")
        self.assertEqual(rx_links.resolve("new-order"), "new-order")
        self.assertEqual(rx_links.members("encounter-1"), ["new-order"])
        self.assertNotIn("old-order", rx_links.members("encounter-1"))


class PharmacyRxEditTests(unittest.TestCase):
    def test_medicine_must_come_from_the_hospital_list(self) -> None:
        with self.assertRaises(ApiError) as caught:
            rx_edit.medicine_fields({"drugName": "Cough syrup", "quantity": 1})
        self.assertEqual(caught.exception.code, "medicine_required")

    def test_quantity_is_required(self) -> None:
        with self.assertRaises(ApiError) as caught:
            rx_edit.medicine_fields({"drugUuid": "drug-1", "quantity": 0})
        self.assertEqual(caught.exception.code, "quantity_required")

    def test_duration_uses_the_hospital_day_unit(self) -> None:
        fields = rx_edit.medicine_fields(
            {"drugUuid": "drug-1", "quantity": 2, "durationUnits": "Day(s)"}
        )
        self.assertEqual(fields["durationUnits"], "Days")
        self.assertEqual(rx_edit.duration_units("Weeks"), "Weeks")

    def test_change_marks_the_previous_medicine(self) -> None:
        payload = rx_edit.drug_order_payload(
            {
                "drugUuid": "drug-1",
                "conceptUuid": "concept-1",
                "drugName": "Paracetamol",
                "dose": 1,
                "doseUnits": "Tablet",
                "route": "Oral",
                "frequency": "Twice a day",
                "duration": 5,
                "durationUnits": "Day(s)",
                "quantity": 10,
                "quantityUnits": "Tablet",
                "instructions": "After food",
            },
            care_setting="Outpatient",
            previous_uuid="old-order",
        )
        self.assertEqual(payload["action"], "REVISE")
        self.assertEqual(payload["previousOrderUuid"], "old-order")
        self.assertEqual(payload["drug"]["uuid"], "drug-1")
        self.assertNotIn("encounterUuid", payload)

    def test_closed_visit_uses_the_original_prescription_time(self) -> None:
        started = datetime(2026, 10, 1, 11, 26, 45, tzinfo=timezone.utc)
        stopped = datetime(2026, 10, 1, 11, 34, 11, tzinfo=timezone.utc)
        original = datetime(2026, 10, 1, 11, 31, 28, tzinfo=timezone.utc)
        later = datetime(2026, 10, 1, 13, 40, 30, tzinfo=timezone.utc)
        chosen = rx_edit.encounter_moment(later, started, stopped, original)
        self.assertEqual(chosen, original)

    def test_dosing_names_use_the_hospital_wording(self) -> None:
        options = ["Tablet(s)", "mg", "Day(s)", "Oral"]
        self.assertEqual(rx_edit._match_dosing_name("Tablet", options), "Tablet(s)")
        self.assertEqual(rx_edit._match_dosing_name("Days", options), "Day(s)")
        self.assertEqual(rx_edit._match_dosing_name("Oral", options), "Oral")
        self.assertEqual(rx_edit._match_dosing_name("Injection", options), "Injection")

    def test_a_consumable_form_is_not_used_as_the_dose_unit(self) -> None:
        options = ["Tablet", "ml", "Unit"]
        self.assertEqual(rx_edit._known_option("Consumables", options, ("Unit", "Tablet")), "Unit")
        self.assertEqual(rx_edit._known_option("Tablet", options, ("Unit",)), "Tablet")

    def test_open_visit_uses_the_current_time(self) -> None:
        started = datetime(2026, 10, 1, 11, 26, 45, tzinfo=timezone.utc)
        now = datetime(2026, 10, 1, 11, 40, 0, tzinfo=timezone.utc)
        chosen = rx_edit.encounter_moment(now, started, None, started)
        self.assertEqual(chosen, now)


class FamilyCardBillAccountTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-rx-link-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        rx_links.reset_for_tests(self.db)

    def tearDown(self) -> None:
        Path(self.db).unlink(missing_ok=True)

    def test_an_existing_bill_account_is_reused(self) -> None:
        patient = {"uuid": "patient-family", "mrn": "ABC205200", "name": "Ada Bello"}
        partner = {"id": 7, "uuid": "patient-family", "ref": "ABC205200", "name": "Ada Bello"}
        with (
            patch("pharmacy.find_partner", return_value=partner) as found,
            patch("registration.ensure_patient_partner") as opened,
        ):
            self.assertEqual(dispensary.billing_partner(object(), patient), partner)
        found.assert_called_once()
        opened.assert_not_called()

    def test_a_family_member_without_a_bill_account_gets_one(self) -> None:
        patient = {"uuid": "patient-family", "mrn": "ABC205200", "name": "Ada Bello"}
        created = {"id": 44, "uuid": "patient-family", "ref": "ABC205200", "name": "Ada Bello"}
        with (
            patch("pharmacy.find_partner", return_value=None),
            patch("registration.ensure_patient_partner", return_value=created) as opened,
        ):
            self.assertEqual(dispensary.billing_partner(object(), patient), created)
        opened.assert_called_once()
        self.assertFalse(opened.call_args.kwargs["wait"])

    def test_adding_medicine_still_stops_when_no_account_can_be_opened(self) -> None:
        clinical = {
            "uuid": "order-1",
            "patientUuid": "patient-family",
            "encounterUuid": "enc-1",
            "stopped": False,
            "careSetting": "Outpatient",
        }
        with (
            patch.object(rx_edit.dispensary, "require_pharmacist"),
            patch.object(rx_edit.dispensary, "load_openmrs_order", return_value=clinical),
            patch.object(rx_edit.dispensary, "odoo_reader", return_value=object()),
            patch.object(
                rx_edit.dispensary,
                "find_pharmacy_products",
                return_value={"drug-1": {"id": 9, "list_price": 250, "name": "Amoxicillin"}},
            ),
            patch.object(rx_edit.core, "load_openmrs_patient", return_value={"uuid": "patient-family", "mrn": "ABC205200"}),
            patch("pharmacy.find_partner", return_value=None),
            patch("registration.ensure_patient_partner", return_value=None),
        ):
            with self.assertRaises(ApiError) as caught:
                rx_edit.add_medicine(
                    "order-1",
                    {"drugUuid": "drug-1", "drugName": "Amoxicillin", "quantity": 10, "conceptUuid": "concept-1"},
                    "cookie",
                )
        self.assertEqual(caught.exception.code, "account_not_found")

    def test_adding_medicine_opens_the_bill_account_and_charges_that_person(self) -> None:
        clinical = {
            "uuid": "order-1",
            "patientUuid": "patient-family",
            "encounterUuid": "enc-1",
            "stopped": False,
            "careSetting": "Outpatient",
        }
        saved = {**clinical, "uuid": "order-2"}
        partner = {"id": 44, "uuid": "patient-family", "ref": "ABC205200", "name": "Ada Bello"}
        product = {"id": 9, "list_price": 250, "name": "Amoxicillin"}
        odoo = MagicMock()
        odoo.read.return_value = [
            {
                "id": 80,
                "name": "S00080",
                "state": "draft",
                "partner_id": [44, "Ada Bello"],
                "invoice_ids": [],
                "origin": "enc-1",
                "shop_id": [3, "Pharmacy Counter"],
            }
        ]
        shop = {
            "id": 3,
            "warehouse_id": [1, "WH"],
            "pricelist_id": [2, "NGN"],
            "payment_default_id": [1, "Immediate"],
        }
        with (
            patch.object(rx_edit.dispensary, "require_pharmacist"),
            patch.object(rx_edit.dispensary, "load_openmrs_order", side_effect=[clinical, saved]),
            patch.object(rx_edit.dispensary, "odoo_reader", return_value=odoo),
            patch.object(rx_edit.dispensary, "find_pharmacy_products", return_value={"drug-1": product}),
            patch.object(
                rx_edit.core,
                "load_openmrs_patient",
                return_value={"uuid": "patient-family", "mrn": "ABC205200", "name": "Ada Bello"},
            ),
            patch("pharmacy.find_partner", return_value=None),
            patch("registration.ensure_patient_partner", return_value=partner) as opened,
            patch.object(rx_edit, "_save_order", return_value="order-2"),
            patch.object(rx_edit.dispensary, "sale_line_for_order", return_value=None),
            patch("pharmacy_sale.find_pharmacy_shop", return_value=shop),
            patch.object(rx_edit, "execute", return_value=80) as created,
            patch.object(rx_edit.dispensary, "ensure_pharmacy_invoice"),
            patch.object(rx_edit.dispensary, "assemble_prescription_group", return_value={"status": "ok"}),
        ):
            result = rx_edit.add_medicine(
                "order-1",
                {"drugUuid": "drug-1", "drugName": "Amoxicillin", "quantity": 10, "conceptUuid": "concept-1"},
                "cookie",
            )
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(opened.call_count, 1)
        sale = created.call_args.args[3][0]
        self.assertEqual(sale["partner_id"], 44)
        self.assertEqual(sale["order_line"][0][2]["product_id"], 9)
        self.assertEqual(sale["order_line"][0][2]["product_uom_qty"], 10)
        self.assertEqual(rx_links.group_for("order-2"), "enc-1")


def _row(order_uuid: str, group_key: str) -> dict:
    return {
        "orderUuid": order_uuid,
        "encounterUuid": "enc-1",
        "patientUuid": "patient-1",
        "groupKey": group_key,
        "notInPharmacy": False,
        "dispensingStatus": "UNPAID",
        "paymentStatus": "UNPAID",
        "stopped": False,
    }


class PrescriptionBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-rx-batch-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        rx_links.reset_for_tests(self.db)

    def tearDown(self) -> None:
        Path(self.db).unlink(missing_ok=True)

    def test_opening_a_prescription_keeps_later_orders_separate(self) -> None:
        early = dispensary.prescription_batch_key("enc-1", "2026-10-11T16:38:18.000+0000")
        later = dispensary.prescription_batch_key("enc-1", "2026-10-11T17:02:26.000+0000")
        rx_links.remember("added", early)
        rows = {
            "flu": _row("flu", early),
            "para": _row("para", later),
            "added": _row("added", early),
        }

        def load(order_uuid: str, cookie: str) -> dict:
            del cookie
            return dict(rows[order_uuid])

        with (
            patch.object(dispensary, "assemble_prescription", side_effect=load),
            patch.object(dispensary, "odoo_reader", return_value=MagicMock()),
            patch.object(dispensary, "sale_line_for_order", return_value=None),
            patch.object(dispensary, "_encounter_drug_order_uuids", return_value=["flu", "para"]),
            patch.object(dispensary, "_unlisted_siblings", return_value=[]),
            patch("consultation.patient_is_nhis", return_value=False),
        ):
            opened = dispensary.assemble_prescription_group("flu", "cookie")

        names = [row["orderUuid"] for row in opened["medicines"]]
        self.assertEqual(names, ["flu", "added"])
        self.assertNotIn("para", names)

    def test_later_order_is_not_the_same_prescription(self) -> None:
        early = dispensary.prescription_batch_key("enc-1", "2026-10-11T16:38:18.000+0000")
        same_minute = dispensary.prescription_batch_key("enc-1", "2026-10-11T16:38:59.000+0000")
        later = dispensary.prescription_batch_key("enc-1", "2026-10-11T17:02:26.000+0000")
        self.assertEqual(early, same_minute)
        self.assertNotEqual(early, later)
