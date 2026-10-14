"""Accountant payment refund helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import accountant_refund as refunds
from server import ApiError

COOKIE = "JSESSIONID=acct"
ACCOUNTANT = {
    "uuid": "a1",
    "username": "cashier.abikan",
    "privileges": ["abikan:accountant"],
    "roles": ["Abikan:Accountant"],
}


class RefundMarkers(unittest.TestCase):
    def test_parses_refund_amounts(self) -> None:
        totals = refunds.refunded_amounts_by_payment(
            "ABIKAN_PAYMENT_REFUND:12:100\nABIKAN_PAYMENT_REFUND:12:50.5\nABIKAN_PAYMENT_REFUND:9:10"
        )
        self.assertEqual(totals["12"], 150.5)
        self.assertEqual(totals["9"], 10.0)

    def test_unauthorized_cannot_refund(self) -> None:
        refunds.reset_for_tests()
        with (
            patch.object(
                refunds,
                "require_accountant",
                side_effect=ApiError(403, "forbidden", "Accountant required."),
            ),
            self.assertRaises(ApiError) as caught,
        ):
            refunds.refund_payment("1", {"requestId": "r1", "amount": 10}, COOKIE)
        self.assertEqual(caught.exception.status, 403)

    def test_rejects_amount_above_refundable(self) -> None:
        refunds.reset_for_tests()
        payment = {
            "id": 7,
            "name": "PCSH1/1",
            "amount": 100,
            "date": "2026-09-09",
            "journal_id": [6, "Cash"],
            "currency_id": [1, "NGN"],
            "reconciled_invoice_ids": [11],
            "state": "posted",
            "partner_id": [2, "Ada"],
            "partner_type": "customer",
            "payment_type": "inbound",
            "company_id": [1, "Hospital"],
            "create_uid": [2, "Admin"],
            "create_date": "2026-09-09",
            "ref": "",
        }

        class FakeOdoo:
            def read(self, model, ids, fields):  # noqa: ANN001, ARG002
                if model == "account.payment":
                    return [payment]
                if model == "account.move":
                    return [{"journal_id": [1, "Sales"]}]
                return []

        with (
            patch.object(refunds, "require_accountant", return_value=ACCOUNTANT),
            patch.object(refunds, "odoo_reader", return_value=FakeOdoo()),
            patch.object(refunds, "_sum_refunded_for_payment", return_value=40.0),
            self.assertRaises(ApiError) as caught,
        ):
            refunds.refund_payment(
                "7",
                {"requestId": "too-high", "amount": 70},
                COOKIE,
            )
        self.assertEqual(caught.exception.code, "amount_too_high")

    def test_idempotent_replay(self) -> None:
        refunds.reset_for_tests()
        refunds.IDEMPOTENCY["accountant-refund:same"] = {
            "status": "done",
            "payload": {"status": "ok", "duplicate": False, "message": "done"},
        }
        with patch.object(refunds, "require_accountant", return_value=ACCOUNTANT):
            result = refunds.refund_payment("7", {"requestId": "same"}, COOKIE)
        self.assertTrue(result.get("duplicate"))


if __name__ == "__main__":
    unittest.main()
