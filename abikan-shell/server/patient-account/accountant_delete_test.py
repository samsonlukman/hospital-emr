"""Deleting an unpaid bill records the reason and the accountant."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import xmlrpc.client

import accountant
import deleted_bills
from server import ApiError, posted_invoice_for_order


class FakeOdoo:
    def __init__(self, invoice: dict) -> None:
        self.invoice = invoice
        self.cancelled = False

    def read(self, model, ids, fields):
        del ids
        if model == "res.partner":
            return [{"id": 7, "name": "Adaeze Okafor", "ref": "ABC1", "uuid": "patient-1"}]
        if model == "account.move" and self.cancelled and fields == ["state"]:
            return [{"id": self.invoice["id"], "state": "cancel"}]
        if model == "account.move":
            return [self.invoice]
        return []

    def search_read(self, model, domain, fields, limit=0):
        del domain, fields, limit, model
        return []


def unpaid_invoice() -> dict:
    return {
        "id": 44,
        "name": "INV/2026/00044",
        "move_type": "out_invoice",
        "state": "posted",
        "payment_state": "not_paid",
        "amount_residual": 3000,
        "amount_total": 3000,
        "partner_id": [7, "Adaeze Okafor"],
        "currency_id": [1, "NGN"],
        "invoice_origin": "",
        "invoice_date": "2026-10-02",
    }


class DeleteUnpaidBillTests(unittest.TestCase):
    def test_a_reason_is_required(self) -> None:
        with (
            patch.object(accountant, "require_accountant", return_value={"username": "cashier"}),
            self.assertRaises(ApiError) as caught,
        ):
            accountant.delete_unpaid_bill({"invoiceId": 44, "reason": "no"}, "cookie")
        self.assertEqual(caught.exception.code, "reason_required")

    def test_a_partly_paid_bill_cannot_be_deleted(self) -> None:
        invoice = unpaid_invoice()
        invoice["payment_state"] = "partial"
        invoice["amount_residual"] = 1000
        with (
            patch.object(accountant, "require_accountant", return_value={"username": "cashier"}),
            patch.object(accountant, "odoo_reader", return_value=FakeOdoo(invoice)),
            self.assertRaises(ApiError) as caught,
        ):
            accountant.delete_unpaid_bill(
                {"invoiceId": 44, "reason": "Entered on the wrong patient", "patientUuid": "patient-1"},
                "cookie",
            )
        self.assertEqual(caught.exception.code, "bill_has_payment")

    def test_an_unpaid_bill_is_removed_and_recorded(self) -> None:
        odoo = FakeOdoo(unpaid_invoice())
        calls: list[str] = []

        def execute(reader, model, method, args, kwargs=None):
            del reader, model, args, kwargs
            calls.append(method)
            if method == "button_cancel":
                odoo.cancelled = True
            return 1

        with tempfile.TemporaryDirectory() as folder:
            deleted_bills.DB_PATH = str(Path(folder) / "deleted.sqlite3")
            with (
                patch.object(accountant, "require_accountant", return_value={"username": "cashier"}),
                patch.object(accountant, "odoo_reader", return_value=odoo),
                patch.object(accountant, "execute", side_effect=execute),
                patch.object(accountant, "load_currency", return_value={"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}),
                patch.object(accountant, "build_account", return_value={"status": "ok"}),
            ):
                result = accountant.delete_unpaid_bill(
                    {"invoiceId": 44, "reason": "Entered on the wrong patient", "patientUuid": "patient-1"},
                    "cookie",
                )
                listed = deleted_bills.list_deletions()
        self.assertEqual(result["deleted"]["deletedBy"], "cashier")
        self.assertEqual(result["deleted"]["reason"], "Entered on the wrong patient")
        self.assertEqual(calls, ["button_draft", "write", "button_cancel"])
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["billNumber"], "INV/2026/00044")
        self.assertEqual(listed["items"][0]["hospitalNumber"], "ABC1")

    def test_an_empty_finance_reply_still_deletes_the_bill(self) -> None:
        odoo = FakeOdoo(unpaid_invoice())

        def execute(reader, model, method, args, kwargs=None):
            del reader, model, args, kwargs
            if method == "button_draft":
                raise xmlrpc.client.Fault(1, "TypeError: cannot marshal None unless allow_none is enabled")
            if method == "button_cancel":
                odoo.cancelled = True
                raise xmlrpc.client.Fault(1, "TypeError: cannot marshal None unless allow_none is enabled")
            return True

        with tempfile.TemporaryDirectory() as folder:
            deleted_bills.DB_PATH = str(Path(folder) / "deleted.sqlite3")
            with (
                patch.object(accountant, "require_accountant", return_value={"username": "cashier"}),
                patch.object(accountant, "odoo_reader", return_value=odoo),
                patch.object(accountant, "execute", side_effect=execute),
                patch.object(accountant, "load_currency", return_value={"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}),
            ):
                result = accountant.delete_unpaid_bill(
                    {"invoiceId": 44, "reason": "Entered on the wrong patient"},
                    "cookie",
                )
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted"]["deletedBy"], "cashier")

    def test_a_bill_left_as_draft_can_still_be_deleted(self) -> None:
        invoice = unpaid_invoice()
        invoice["state"] = "draft"
        odoo = FakeOdoo(invoice)
        calls: list[str] = []

        def execute(reader, model, method, args, kwargs=None):
            del reader, model, args, kwargs
            calls.append(method)
            if method == "button_cancel":
                odoo.cancelled = True
            return True

        with tempfile.TemporaryDirectory() as folder:
            deleted_bills.DB_PATH = str(Path(folder) / "deleted.sqlite3")
            with (
                patch.object(accountant, "require_accountant", return_value={"username": "cashier"}),
                patch.object(accountant, "odoo_reader", return_value=odoo),
                patch.object(accountant, "execute", side_effect=execute),
                patch.object(accountant, "load_currency", return_value={"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}),
            ):
                accountant.delete_unpaid_bill(
                    {"invoiceId": 44, "reason": "Entered on the wrong patient"},
                    "cookie",
                )
        self.assertEqual(calls, ["write", "button_cancel"])


class ExternalBillLookupTests(unittest.TestCase):
    def test_the_walk_in_record_with_the_bill_is_used(self) -> None:
        chart = {"id": 4210, "name": "adebayo kehinde", "ref": "EXTLAB000002", "uuid": "patient-ext"}
        walkin = {
            "id": 4209,
            "name": "adebayo kehinde",
            "ref": "LAB-WALKIN:EXTLAB000002",
            "uuid": False,
        }

        class Lookup:
            def search_read(self, model, domain, fields, limit=0):
                del fields, limit
                if model == "res.partner" and domain == [("uuid", "=", "patient-ext")]:
                    return [chart]
                if model == "res.partner" and domain[0][0] == "ref":
                    return [chart, walkin]
                if model == "account.move":
                    return [{"partner_id": [4209, "adebayo kehinde"]}]
                return []

        import server as core

        partner = core.find_partner(Lookup(), {"uuid": "patient-ext", "mrn": "EXTLAB000002", "name": "adebayo kehinde"})
        self.assertEqual(partner["id"], 4209)

    def test_outstanding_links_an_external_bill_to_the_chart(self) -> None:
        class Lookup:
            def search_read(self, model, domain, fields, limit=0):
                del model, domain, fields, limit
                return [{"ref": "EXTLAB000002", "uuid": "patient-ext"}]

        linked = accountant._chart_uuids_for_walkins(
            Lookup(),
            {4209: {"id": 4209, "ref": "LAB-WALKIN:EXTLAB000002", "uuid": False}},
        )
        self.assertEqual(linked[4209], "patient-ext")


class CancelledBillLookupTest(unittest.TestCase):
    def test_cancelled_bill_does_not_block_the_sale(self) -> None:
        invoices = [
            {"id": 672, "state": "cancel", "invoice_origin": "S00999"},
            {"id": 700, "state": "posted", "invoice_origin": "S00999"},
        ]
        lookup = {700: {"id": 700, "number": "INV/700"}}
        found = posted_invoice_for_order(lookup, invoices, {"name": "S00999", "invoice_ids": [672]})
        self.assertEqual(found["id"], 700)

    def test_only_a_cancelled_bill_leaves_the_sale_without_one(self) -> None:
        invoices = [{"id": 672, "state": "cancel", "invoice_origin": "S00999"}]
        found = posted_invoice_for_order({}, invoices, {"name": "S00999", "invoice_ids": [672]})
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
