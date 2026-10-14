"""Payment amount rules — integer minor units, no float equality."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import accountant
import server as core
from server import ApiError


class MoneyHelpers(unittest.TestCase):
    def test_format_money_quantizes_amount_and_formatted(self) -> None:
        money = core.format_money(
            10.105,
            {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "after"},
        )
        self.assertEqual(money["amount"], 10.11)
        self.assertEqual(money["formatted"], "₦10.11")

    def test_minor_units_round_half_up(self) -> None:
        self.assertEqual(core.money_minor(1.005, 2), 101)
        self.assertEqual(core.money_minor("10.105", 2), 1011)
        self.assertEqual(core.money_minor(4999.99999999, 2), 500000)
        self.assertEqual(core.money_minor("5000.00", 2), 500000)

    def test_binary_float_sum_matches_typed_exact_due(self) -> None:
        due = 0.1 + 0.2
        self.assertEqual(core.money_minor(due, 2), core.money_minor("0.30", 2))


class ValidatePaymentAmount(unittest.TestCase):
    def test_partial_payment_succeeds(self) -> None:
        amount, outstanding = accountant.validate_payment_amount(2000, 5000, 2)
        self.assertEqual(amount, 2000.0)
        self.assertEqual(outstanding, 5000.0)

    def test_exact_payment_equal_to_due_succeeds(self) -> None:
        amount, outstanding = accountant.validate_payment_amount("5000.00", 5000, 2)
        self.assertEqual(amount, 5000.0)
        self.assertEqual(outstanding, 5000.0)

    def test_exact_payment_survives_float_noise(self) -> None:
        amount, outstanding = accountant.validate_payment_amount(5000.00, 4999.99999999, 2)
        self.assertEqual(core.money_minor(amount, 2), core.money_minor(outstanding, 2))

    def test_overpayment_fails(self) -> None:
        with self.assertRaises(ApiError) as caught:
            accountant.validate_payment_amount(5000.01, 5000, 2)
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(caught.exception.code, "amount_exceeds_outstanding")

    def test_zero_payment_fails(self) -> None:
        with self.assertRaises(ApiError) as caught:
            accountant.validate_payment_amount(0, 5000, 2)
        self.assertEqual(caught.exception.code, "invalid_amount")

    def test_negative_payment_fails(self) -> None:
        with self.assertRaises(ApiError) as caught:
            accountant.validate_payment_amount(-1, 5000, 2)
        self.assertEqual(caught.exception.code, "invalid_amount")

    def test_already_fully_paid_fails(self) -> None:
        with self.assertRaises(ApiError) as caught:
            accountant.validate_payment_amount(100, 0, 2)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.code, "invoice_already_paid")

    def test_multiple_partials_settle_exactly(self) -> None:
        due = 11111.11
        first, current = accountant.validate_payment_amount(5000, due, 2)
        remaining = core.money_major(
            core.money_minor(current, 2) - core.money_minor(first, 2),
            2,
        )
        second, current = accountant.validate_payment_amount(4000, remaining, 2)
        remaining = core.money_major(
            core.money_minor(current, 2) - core.money_minor(second, 2),
            2,
        )
        final, current = accountant.validate_payment_amount(remaining, remaining, 2)
        self.assertEqual(core.money_minor(current, 2) - core.money_minor(final, 2), 0)

    def test_one_kobo_over_is_rejected(self) -> None:
        with self.assertRaises(ApiError) as caught:
            accountant.validate_payment_amount(10.11, 10.10, 2)
        self.assertEqual(caught.exception.code, "amount_exceeds_outstanding")

    def test_one_kobo_under_is_partial(self) -> None:
        amount, outstanding = accountant.validate_payment_amount(10.09, 10.10, 2)
        self.assertEqual(amount, 10.09)
        self.assertEqual(outstanding, 10.10)

    def test_ensure_payment_mail_sender_fills_missing_addresses(self) -> None:
        odoo = MagicMock()
        odoo.uid = 7
        odoo.search_read.side_effect = [
            [{"id": 1, "email": False}],
            [],
            [{"id": 7, "email": False, "partner_id": [72, "Hospital EMR Odoo"]}],
        ]
        with patch.object(accountant, "execute") as execute:
            accountant.ensure_payment_mail_sender(odoo)
        writes = [call.args for call in execute.call_args_list]
        self.assertTrue(any(args[1] == "res.company" and args[2] == "write" for args in writes))
        self.assertTrue(
            any(args[1] == "ir.config_parameter" and args[2] == "create" for args in writes)
        )
        self.assertTrue(any(args[1] == "res.users" and args[2] == "write" for args in writes))
        self.assertTrue(any(args[1] == "res.partner" and args[2] == "write" for args in writes))


class PaymentIdempotency(unittest.TestCase):
    def setUp(self) -> None:
        accountant.IDEMPOTENCY.clear()

    def tearDown(self) -> None:
        accountant.IDEMPOTENCY.clear()

    def test_retry_returns_same_payment_without_second_write(self) -> None:
        first = {
            "payment": {"id": 44, "reference": "PAY/001"},
            "status": "ok",
            "success": True,
        }
        with (
            patch.object(
                accountant,
                "require_accountant",
                return_value={"username": "accountant.abikan"},
            ),
            patch.object(accountant, "get_payment", return_value=first) as fetch,
            patch.object(accountant, "_register_payment_once", return_value=first) as write,
        ):
            body = {"requestId": "pay-1", "amount": 5000}
            created = accountant.register_payment(body, "cookie")
            replay = accountant.register_payment(body, "cookie")
        self.assertEqual(created["payment"]["id"], 44)
        self.assertFalse(created.get("idempotentReplay"))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["payment"]["id"], 44)
        write.assert_called_once()
        fetch.assert_called()

    def test_pending_request_is_not_duplicated(self) -> None:
        accountant.IDEMPOTENCY["pay-busy"] = {
            "status": "pending",
            "username": "accountant.abikan",
        }
        with patch.object(
            accountant,
            "require_accountant",
            return_value={"username": "accountant.abikan"},
        ):
            with self.assertRaises(ApiError) as caught:
                accountant.register_payment({"requestId": "pay-busy"}, "cookie")
        self.assertEqual(caught.exception.code, "payment_in_progress")


class InvoiceResidualCompare(unittest.TestCase):
    def test_expected_residual_uses_minor_units(self) -> None:
        invoice = {
            "id": 9,
            "move_type": "out_invoice",
            "state": "posted",
            "payment_state": "not_paid",
            "amount_residual": 4999.99999999,
            "partner_id": [3, "Patient"],
            "currency_id": [1, "NGN"],
        }
        odoo = type("Odoo", (), {"read": staticmethod(lambda *args, **kwargs: [invoice])})()
        invoices, total = accountant._validate_invoices(
            odoo, 3, [9], {9: 5000.00}
        )
        self.assertEqual(len(invoices), 1)
        self.assertEqual(core.money_minor(total, 2), 500000)


if __name__ == "__main__":
    unittest.main()
