"""An accountant can create a bill and the name of who created it is kept."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import accountant
import cashier_records
from server import ApiError


class RecordingOdoo:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def read(self, model, ids, fields):
        del ids
        if model == "sale.order" and "order_line" in fields and "invoice_ids" not in fields:
            return [{"id": 9, "order_line": [3]}]
        if model == "sale.order":
            return [{"id": 9, "name": "S00999", "state": "sale", "invoice_ids": [88], "amount_total": 2500}]
        if model == "account.move":
            return [
                {
                    "id": 88,
                    "name": "INV/2026/00088",
                    "state": "posted",
                    "move_type": "out_invoice",
                    "currency_id": [1, "NGN"],
                    "amount_total": 2500,
                }
            ]
        if model == "res.currency":
            return [{"id": 1, "name": "NGN", "symbol": "₦", "decimal_places": 2, "position": "before"}]
        return []

    def search_read(self, model, domain, fields, limit=0):
        del model, domain, fields, limit
        return []


class CreateCashierBillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        cashier_records.DB_PATH = str(Path(self.folder.name) / "cashier.sqlite3")
        accountant._CREATED_BILLS.clear()

    def tearDown(self) -> None:
        self.folder.cleanup()

    def test_the_patient_amount_and_reason_are_required(self) -> None:
        user = patch.object(accountant, "require_accountant", return_value={"username": "cashier"})
        with user, self.assertRaises(ApiError) as missing_patient:
            accountant.create_cashier_bill({"amount": "2500", "description": "Medical certificate"}, "cookie")
        self.assertEqual(missing_patient.exception.code, "patient_required")
        with user, self.assertRaises(ApiError) as missing_reason:
            accountant.create_cashier_bill(
                {"patientUuid": "patient-1", "amount": "2500", "description": "no"},
                "cookie",
            )
        self.assertEqual(missing_reason.exception.code, "description_required")
        with user, self.assertRaises(ApiError) as missing_amount:
            accountant.create_cashier_bill(
                {"patientUuid": "patient-1", "amount": "0", "description": "Medical certificate"},
                "cookie",
            )
        self.assertEqual(missing_amount.exception.code, "amount_required")

    def test_the_bill_uses_the_typed_reason_and_the_accountant(self) -> None:
        odoo = RecordingOdoo()
        created: list[tuple] = []

        def execute(reader, model, method, args, kwargs=None):
            del reader, kwargs
            created.append((model, method, args))
            if model == "sale.order" and method == "create":
                return 9
            return None

        with (
            patch.object(accountant, "require_accountant", return_value={"username": "cashier.ade"}),
            patch.object(accountant, "load_openmrs_patient", return_value={"uuid": "patient-1", "name": "Adaeze Okafor", "mrn": "ABC1"}),
            patch.object(accountant, "odoo_reader", return_value=odoo),
            patch.object(accountant, "find_partner", return_value={"id": 7, "name": "Adaeze Okafor", "ref": "ABC1"}),
            patch.object(
                accountant,
                "ensure_cashier_masters",
                return_value={
                    "product": {"id": 4, "name": "Cashier bill"},
                    "shop": {"id": 2, "warehouse_id": [1, "WH"], "pricelist_id": [1, "NGN"], "payment_default_id": [1, "Immediate"]},
                },
            ),
            patch.object(accountant, "execute", side_effect=execute),
            patch.object(accountant, "execute_allowing_empty", side_effect=execute),
        ):
            result = accountant.create_cashier_bill(
                {
                    "patientUuid": "patient-1",
                    "amount": "2,500",
                    "description": "Medical certificate",
                    "requestId": "once",
                },
                "cookie",
            )
            again = accountant.create_cashier_bill(
                {
                    "patientUuid": "patient-1",
                    "amount": "2500",
                    "description": "Medical certificate",
                    "requestId": "once",
                },
                "cookie",
            )
        self.assertEqual(result["createdBy"], "cashier.ade")
        self.assertEqual(result["billNumber"], "INV/2026/00088")
        self.assertEqual(result["description"], "Medical certificate")
        sale = next(args for model, method, args in created if model == "sale.order" and method == "create")
        line = sale[0]["order_line"][0][2]
        self.assertEqual(line["name"], "Medical certificate")
        self.assertEqual(line["price_unit"], 2500)
        self.assertEqual(cashier_records.creators_for([88])[88]["createdBy"], "cashier.ade")
        self.assertEqual(again["invoiceId"], 88)
        self.assertEqual(sum(1 for model, method, _args in created if model == "sale.order" and method == "create"), 1)

    def test_someone_who_is_not_registered_can_be_billed(self) -> None:
        odoo = RecordingOdoo()
        created: list[tuple] = []

        def execute(reader, model, method, args, kwargs=None):
            del reader, kwargs
            created.append((model, method, args))
            if model == "res.partner" and method == "create":
                return 7
            if model == "sale.order" and method == "create":
                return 9
            return None

        def read(model, ids, fields):
            if model == "res.partner":
                values = created[0][2][0]
                return [{"id": 7, "name": values["name"], "ref": values["ref"], "uuid": values["uuid"]}]
            return RecordingOdoo.read(odoo, model, ids, fields)

        odoo.read = read
        with (
            patch.object(accountant, "require_accountant", return_value={"username": "cashier.ade"}),
            patch.object(accountant, "load_openmrs_patient", side_effect=AssertionError("registered lookup")),
            patch.object(accountant, "odoo_reader", return_value=odoo),
            patch.object(
                accountant,
                "ensure_cashier_masters",
                return_value={
                    "product": {"id": 4, "name": "Cashier bill"},
                    "shop": {"id": 2, "warehouse_id": [1, "WH"], "pricelist_id": [1, "NGN"], "payment_default_id": [1, "Immediate"]},
                },
            ),
            patch.object(accountant, "execute", side_effect=execute),
            patch.object(accountant, "execute_allowing_empty", side_effect=execute),
        ):
            result = accountant.create_cashier_bill(
                {
                    "patientName": "Kunle Bello",
                    "amount": 1500,
                    "description": "Medical certificate",
                },
                "cookie",
            )
        partner = next(args[0] for model, method, args in created if model == "res.partner" and method == "create")
        self.assertEqual(partner["name"], "Kunle Bello")
        self.assertTrue(str(partner["ref"]).startswith("CASHIER-WALKIN:"))
        self.assertTrue(str(partner["uuid"]).startswith("cashier:"))
        self.assertEqual(result["patient"]["name"], "Kunle Bello")
        self.assertTrue(str(result["patient"]["uuid"]).startswith("cashier:"))
        self.assertEqual(result["createdBy"], "cashier.ade")


class UnregisteredBuyerBills(unittest.TestCase):
    def test_pharmacy_other_buyer_and_doctorless_orders_can_be_opened(self) -> None:
        import server as core

        self.assertEqual(
            core.walkin_account_uuid({"ref": "PHARM-WALKIN:sale-1", "uuid": ""}),
            "pharmacy:sale-1",
        )
        self.assertEqual(
            core.walkin_account_uuid({"ref": "LAB-WALKIN:EXTLAB000001", "uuid": ""}),
            "laboratory:EXTLAB000001",
        )
        self.assertEqual(
            core.walkin_account_uuid({"ref": "RAD-WALKIN:study-9", "uuid": ""}),
            "radiology:study-9",
        )
        self.assertEqual(core.walkin_ref_for_account("pharmacy:sale-1"), "PHARM-WALKIN:sale-1")
        self.assertEqual(
            core.walkin_account_uuid({"ref": "ABC200229", "uuid": "patient-1"}),
            "patient-1",
        )


if __name__ == "__main__":
    unittest.main()
