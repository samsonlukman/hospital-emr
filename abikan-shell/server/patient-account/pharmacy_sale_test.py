"""Direct pharmacy sale helpers."""

from __future__ import annotations

import unittest

import pharmacy_sale as counter


class PharmacySaleKeys(unittest.TestCase):
    def test_direct_sale_keys_are_namespaced(self) -> None:
        self.assertTrue(counter.is_direct_sale_key("pharmacy-sale:abc:0"))
        self.assertFalse(counter.is_direct_sale_key("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
        self.assertEqual(counter.sale_external_key("token1", 2), "pharmacy-sale:token1:2")

    def test_payment_and_dispensing_labels_stay_separate(self) -> None:
        self.assertEqual(counter._payment_label(None), "UNPAID")
        self.assertEqual(
            counter._payment_label(
                {"payment_state": "not_paid", "amount_residual": 500, "amount_total": 500}
            ),
            "UNPAID",
        )
        self.assertEqual(
            counter._payment_label(
                {"payment_state": "paid", "amount_residual": 0, "amount_total": 500}
            ),
            "PAID",
        )
        self.assertEqual(
            counter._dispensing_label(
                [{"product_uom_qty": 10, "qty_delivered": 0}],
                {"state": "assigned"},
            ),
            "READY TO DISPENSE",
        )
        self.assertEqual(
            counter._dispensing_label(
                [{"product_uom_qty": 10, "qty_delivered": 10}],
                {"state": "done"},
            ),
            "DISPENSED",
        )


if __name__ == "__main__":
    unittest.main()
