"""Prescription announce/cancel + pharmacy refund unit coverage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import notifications as notes
import pharmacy_prescription_ops as rx_ops
import pharmacy_refund as refunds
import pharmacy_unlisted as unlisted
from server import ApiError

COOKIE = "JSESSIONID=doc"
ORDER = "cccccccc-cccc-cccc-cccc-cccccccccccc"
PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DOCTOR = {
    "uuid": "doc-1",
    "username": "dr.amina",
    "privileges": ["app:clinical"],
    "roles": ["Abikan:Doctor"],
}
PHARMACY = {
    "uuid": "pharm-1",
    "username": "pharmacy",
    "privileges": ["bahmni:clinical:dispense"],
    "roles": ["Abikan:Pharmacy"],
}
RECEPTION = {
    "uuid": "rec-1",
    "username": "reception",
    "privileges": ["app:registration"],
    "roles": ["Abikan:Reception"],
}


class PrescriptionCreatedNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-rx-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        notes.reset_for_tests(path=self.db)

    def tearDown(self) -> None:
        notes.reset_for_tests(path=self.db)
        Path(self.db).unlink(missing_ok=True)

    def test_emit_targets_pharmacy(self) -> None:
        created = notes.emit_prescription_created(
            patient_uuid=PATIENT,
            order_uuid=ORDER,
            patient_name="Ahmed Bello",
            mrn="ABC200100",
            sender_username="dr.amina",
            sender_display="Amina Bello",
            drug_name="Paracetamol 500mg",
            path=self.db,
        )
        note = created["notification"]
        self.assertEqual(note["eventType"], notes.EVENT_PRESCRIPTION_CREATED)
        self.assertEqual(note["recipientWorkplace"], notes.WORKPLACE_PHARMACY)
        self.assertEqual(note["priority"], notes.PRIORITY_HIGH)
        self.assertTrue(note["speak"])
        self.assertEqual(note["actionHref"], f"#/pharmacy/prescription/{ORDER}")
        self.assertIn("New prescription for Ahmed Bello", note["message"])

        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=PHARMACY),
            patch("pharmacy.is_pharmacist", return_value=True),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)

    def test_reception_does_not_receive(self) -> None:
        notes.emit_prescription_created(
            patient_uuid=PATIENT,
            order_uuid=ORDER,
            patient_name="Ahmed Bello",
            mrn="ABC200100",
            sender_username="dr.amina",
            sender_display="Amina Bello",
            path=self.db,
        )
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 0)

    def test_duplicate_order_uuid_dedupes(self) -> None:
        first = notes.emit_prescription_created(
            patient_uuid=PATIENT,
            order_uuid=ORDER,
            patient_name="Ahmed",
            mrn="1",
            sender_username="dr.amina",
            sender_display="Amina",
            path=self.db,
        )
        second = notes.emit_prescription_created(
            patient_uuid=PATIENT,
            order_uuid=ORDER,
            patient_name="Ahmed",
            mrn="1",
            sender_username="dr.amina",
            sender_display="Amina",
            path=self.db,
        )
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["notification"]["id"], second["notification"]["id"])


class AnnouncePrescriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-unlisted-", suffix=".sqlite3", delete=False)
        handle.close()
        self.unlisted_db = handle.name
        unlisted.reset_for_tests(self.unlisted_db)

    def tearDown(self) -> None:
        Path(self.unlisted_db).unlink(missing_ok=True)

    def test_announce_after_valid_order(self) -> None:
        with (
            patch("consultation.require_clinician", return_value=DOCTOR),
            patch.object(
                rx_ops.dispensary,
                "load_openmrs_order",
                return_value={
                    "uuid": ORDER,
                    "stopped": False,
                    "patientUuid": PATIENT,
                    "patientName": "Ahmed Bello",
                    "mrn": "ABC1",
                    "drugName": "Paracetamol",
                },
            ),
            patch.object(rx_ops.staff_notes, "emit_prescription_created") as emit,
            patch.object(rx_ops, "_doctor_display", return_value="Amina Bello"),
        ):
            emit.return_value = {"notification": {"id": "n1"}, "duplicate": False}
            result = rx_ops.announce_prescriptions({"orderUuids": [ORDER]}, COOKIE)
        self.assertEqual(result["count"], 1)
        emit.assert_called_once()

    def test_announce_typed_medicine_is_remembered_and_not_billed(self) -> None:
        with (
            patch("consultation.require_clinician", return_value=DOCTOR),
            patch.object(
                rx_ops.dispensary,
                "load_openmrs_order",
                return_value={
                    "uuid": ORDER,
                    "stopped": False,
                    "patientUuid": PATIENT,
                    "patientName": "Ahmed Bello",
                    "mrn": "ABC1",
                    "drugName": "Calamine lotion extra",
                    "drugNonCoded": "Calamine lotion extra",
                    "drugUuid": "",
                    "encounterUuid": "enc-1",
                    "ordered": "2026-09-25",
                },
            ),
            patch.object(rx_ops, "_cancel_odoo_sale_for_order"),
            patch.object(rx_ops.staff_notes, "emit_prescription_created") as emit,
            patch.object(rx_ops, "_doctor_display", return_value="Amina Bello"),
        ):
            emit.return_value = {"notification": {"id": "n1"}, "duplicate": False}
            result = rx_ops.announce_prescriptions({"orderUuids": [ORDER]}, COOKIE)
        self.assertEqual(result["count"], 1)
        rows = unlisted.list_rows(patient_uuid=PATIENT)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drugName"], "Calamine lotion extra")

    def test_announce_discovers_orders_when_client_uuid_missing(self) -> None:
        with (
            patch("consultation.require_clinician", return_value=DOCTOR),
            patch.object(
                rx_ops,
                "_discover_new_order_uuids",
                return_value=[ORDER],
            ) as discover,
            patch.object(
                rx_ops.dispensary,
                "load_openmrs_order",
                return_value={
                    "uuid": ORDER,
                    "stopped": False,
                    "patientUuid": PATIENT,
                    "patientName": "Ahmed Bello",
                    "mrn": "ABC1",
                    "drugName": "Paracetamol",
                },
            ),
            patch.object(rx_ops.staff_notes, "emit_prescription_created") as emit,
            patch.object(rx_ops, "_doctor_display", return_value="Amina Bello"),
        ):
            emit.return_value = {"notification": {"id": "n1"}, "duplicate": False}
            result = rx_ops.announce_prescriptions(
                {
                    "orderUuids": [],
                    "patientUuid": PATIENT,
                    "priorOrderUuids": [],
                    "expectedCount": 1,
                },
                COOKIE,
            )
        self.assertEqual(result["count"], 1)
        discover.assert_called_once()
        emit.assert_called_once()

    def test_announce_skips_stopped(self) -> None:
        with (
            patch("consultation.require_clinician", return_value=DOCTOR),
            patch.object(
                rx_ops.dispensary,
                "load_openmrs_order",
                return_value={"uuid": ORDER, "stopped": True, "patientUuid": PATIENT},
            ),
            patch.object(rx_ops.staff_notes, "emit_prescription_created") as emit,
        ):
            result = rx_ops.announce_prescriptions({"orderUuids": [ORDER]}, COOKIE)
        self.assertEqual(result["count"], 0)
        emit.assert_not_called()

    def test_multi_line_cancel_unlinks_only_target_line(self) -> None:
        line = {
            "id": 11,
            "product_id": [7, "Amox"],
            "product_uom_qty": 5,
            "qty_delivered": 0,
            "external_order_id": ORDER,
        }
        sale = {"id": 39, "name": "S00039", "state": "draft", "invoice_ids": []}
        siblings = [
            line,
            {
                "id": 12,
                "product_id": [8, "Para"],
                "product_uom_qty": 10,
                "qty_delivered": 0,
                "external_order_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            },
        ]

        class FakeOdoo:
            def read(self, *_args, **_kwargs):
                return [
                    {
                        "id": 39,
                        "name": "S00039",
                        "state": "draft",
                        "partner_id": [1, "P"],
                        "invoice_ids": [],
                        "origin": "",
                        "shop_id": False,
                    }
                ]

        def execute(_odoo, model, method, args=None, kwargs=None):
            if model == "stock.picking" and method == "search_read":
                return []
            return True

        with (
            patch.object(rx_ops.dispensary, "sale_line_for_order", return_value=(line, sale)),
            patch.object(
                rx_ops.dispensary,
                "sale_prescription_lines",
                side_effect=[siblings, [siblings[1]]],
            ),
            patch.object(rx_ops.dispensary, "related_invoice", return_value=None),
            patch.object(rx_ops.dispensary, "ensure_pharmacy_invoice", return_value=None),
            patch.object(rx_ops, "execute", side_effect=execute) as execute_mock,
        ):
            rx_ops._cancel_odoo_sale_for_order(FakeOdoo(), ORDER)
        unlink_calls = [
            call
            for call in execute_mock.call_args_list
            if len(call.args) >= 3 and call.args[1:3] == ("sale.order.line", "unlink")
        ]
        cancel_sale = [
            call
            for call in execute_mock.call_args_list
            if len(call.args) >= 3 and call.args[1:3] == ("sale.order", "action_cancel")
        ]
        self.assertEqual(len(unlink_calls), 1)
        self.assertEqual(cancel_sale, [])


class CancelPrescriptionTests(unittest.TestCase):
    def test_dispensed_cannot_be_deleted(self) -> None:
        with (
            patch.object(rx_ops.dispensary, "require_pharmacist", return_value=PHARMACY),
            patch.object(
                rx_ops.dispensary,
                "load_openmrs_order",
                return_value={"uuid": ORDER, "stopped": False, "patientUuid": PATIENT},
            ),
            patch.object(
                rx_ops.dispensary,
                "assemble_prescription",
                return_value={
                    "dispensingStatus": "DISPENSED",
                    "paymentStatus": "PAID",
                    "quantityDelivered": 10,
                },
            ),
            patch.object(rx_ops, "_openmrs_delete") as delete,
            self.assertRaises(ApiError) as caught,
        ):
            rx_ops.cancel_prescription(ORDER, COOKIE)
        self.assertEqual(caught.exception.code, "prescription_dispensed")
        delete.assert_not_called()

    def test_unpaid_undispensed_can_be_deleted(self) -> None:
        with (
            patch.object(rx_ops.dispensary, "require_pharmacist", return_value=PHARMACY),
            patch.object(
                rx_ops.dispensary,
                "load_openmrs_order",
                return_value={
                    "uuid": ORDER,
                    "stopped": False,
                    "patientUuid": PATIENT,
                    "drugName": "Paracetamol",
                },
            ),
            patch.object(
                rx_ops.dispensary,
                "assemble_prescription",
                return_value={
                    "dispensingStatus": "UNPAID",
                    "paymentStatus": "UNPAID",
                    "quantityDelivered": 0,
                },
            ),
            patch.object(rx_ops, "odoo_reader"),
            patch.object(rx_ops, "_cancel_odoo_sale_for_order"),
            patch.object(rx_ops, "_openmrs_delete") as delete,
        ):
            result = rx_ops.cancel_prescription(ORDER, COOKIE)
        self.assertFalse(result["alreadyCancelled"])
        delete.assert_called_once()


class RefundGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        refunds.reset_for_tests()

    def tearDown(self) -> None:
        refunds.reset_for_tests()

    def test_already_refunded_marker(self) -> None:
        sale = {"note": f"{refunds.REFUND_MARKER}:1:pharmacy"}
        self.assertTrue(refunds._already_refunded(sale, {"payment_state": "paid"}))

    def test_reversed_invoice_counts_as_refunded(self) -> None:
        self.assertTrue(refunds._already_refunded({"note": ""}, {"payment_state": "reversed"}))

    def test_line_refund_quantities_parse(self) -> None:
        note = "ABIKAN_LINE_REFUND:12:3\nABIKAN_LINE_REFUND:12:2\nABIKAN_LINE_REFUND:99:1.5"
        totals = refunds.line_refunded_quantities(note)
        self.assertEqual(totals["12"], 5.0)
        self.assertEqual(totals["99"], 1.5)

    def test_unauthorized_cannot_refund(self) -> None:
        with (
            patch.object(
                refunds,
                "require_pharmacist",
                side_effect=ApiError(403, "forbidden", "Pharmacy required."),
            ),
            self.assertRaises(ApiError) as caught,
        ):
            refunds.refund_sale("1", {"requestId": "r1"}, COOKIE)
        self.assertEqual(caught.exception.status, 403)

    def test_line_quantity_too_high_rejected(self) -> None:
        sale = {
            "id": 7,
            "name": "PH-7",
            "state": "sale",
            "partner_id": [1, "P"],
            "invoice_ids": [9],
            "origin": "pharmacy-sale:tok",
            "shop_id": False,
            "amount_total": 2000,
            "note": "ABIKAN_LINE_REFUND:1:3",
        }
        lines = [
            {
                "id": 1,
                "product_id": [11, "Paracetamol"],
                "product_uom_qty": 10,
                "qty_delivered": 10,
                "price_unit": 200,
                "discount": 0,
                "name": "Paracetamol",
            }
        ]
        invoice = {"id": 9, "state": "posted", "payment_state": "paid", "move_type": "out_invoice"}

        class FakeOdoo:
            def read(self, model, ids, fields):  # noqa: ANN001, ARG002
                return [sale]

        with (
            patch.object(refunds, "require_pharmacist", return_value=PHARMACY),
            patch.object(refunds, "odoo_reader", return_value=FakeOdoo()),
            patch.object(refunds, "_load_invoice", return_value=invoice),
            patch.object(refunds, "_sale_lines", return_value=lines),
            patch.object(refunds, "_outgoing_done_picking", return_value={"id": 55, "name": "WH/OUT/1"}),
            patch.object(refunds.dispensary, "is_pharmacy_sale", return_value=True),
            self.assertRaises(ApiError) as caught,
        ):
            refunds.refund_sale(
                "7",
                {"mode": "line", "lineId": "1", "quantity": 8, "requestId": "qty-high"},
                COOKIE,
            )
        self.assertEqual(caught.exception.code, "quantity_too_high")

    def test_idempotent_done_returns_duplicate(self) -> None:
        refunds.IDEMPOTENCY["pharmacy-refund:same"] = {
            "status": "done",
            "payload": {"status": "ok", "saleId": "7", "refunded": True},
        }
        with patch.object(refunds, "require_pharmacist", return_value=PHARMACY):
            result = refunds.refund_sale("7", {"requestId": "same"}, COOKIE)
        self.assertTrue(result.get("duplicate"))
        self.assertEqual(result["saleId"], "7")


class CancelSalePrescriptionTests(unittest.TestCase):
    def test_blocks_when_not_deletable(self) -> None:
        with (
            patch.object(rx_ops.dispensary, "require_pharmacist", return_value=PHARMACY),
            patch.object(
                __import__("pharmacy_history"),
                "get_sales_history_item",
                return_value={"canDeletePrescription": False, "prescriptionRefs": ["x"]},
            ),
            self.assertRaises(ApiError) as caught,
        ):
            rx_ops.cancel_sale_prescription("12", COOKIE)
        self.assertEqual(caught.exception.code, "prescription_not_deletable")

    def test_deletes_linked_orders(self) -> None:
        with (
            patch.object(rx_ops.dispensary, "require_pharmacist", return_value=PHARMACY),
            patch(
                "pharmacy_history.get_sales_history_item",
                return_value={
                    "canDeletePrescription": True,
                    "prescriptionRefs": [ORDER],
                    "saleId": "12",
                },
            ),
            patch.object(rx_ops, "cancel_prescription", return_value={"status": "ok", "orderUuid": ORDER}) as cancel,
        ):
            result = rx_ops.cancel_sale_prescription("12", COOKIE)
        self.assertEqual(result["status"], "ok")
        cancel.assert_called_once_with(ORDER, COOKIE)


if __name__ == "__main__":
    unittest.main()
