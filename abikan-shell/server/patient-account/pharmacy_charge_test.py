from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pharmacy as dispensary
from server import ApiError


class PharmacyChargeTests(unittest.TestCase):
    def test_pharmacy_sale_is_identified_by_shop(self) -> None:
        self.assertTrue(dispensary.is_pharmacy_sale({"shop_id": [1, "Pharmacy Counter"]}))
        self.assertFalse(dispensary.is_pharmacy_sale({"shop_id": [6, "Accommodation"]}))
        self.assertFalse(dispensary.is_pharmacy_sale({"shop_id": [2, "Hospital Laboratory"]}))

    def test_ensure_invoice_confirms_draft_without_rewriting_price(self) -> None:
        odoo = MagicMock()
        odoo.read.side_effect = [
            [{"id": 66, "name": "S00066", "state": "sale", "invoice_ids": [99], "partner_id": [43, "P"], "origin": "API FEED SYNC", "shop_id": [1, "Pharmacy Counter"]}],
            [{"id": 99, "name": "INV/1", "state": "posted", "payment_state": "not_paid", "amount_residual": 5750, "move_type": "out_invoice", "partner_id": [43, "P"]}],
        ]
        writes: list[tuple] = []

        def execute(_odoo, model, method, args, kwargs=None):
            writes.append((model, method, args))
            return True

        with patch.object(dispensary, "execute", side_effect=execute):
            invoice = dispensary.ensure_pharmacy_invoice(
                odoo,
                {"id": 66, "state": "draft", "invoice_ids": [], "name": "S00066", "shop_id": [1, "Pharmacy Counter"]},
            )
        self.assertEqual(writes[0][0], "sale.order")
        self.assertEqual(writes[0][1], "action_confirm")
        self.assertEqual(invoice["id"], 99)
        self.assertFalse(any(row[1] == "write" for row in writes))

    def test_already_confirmed_sale_is_not_confirmed_again(self) -> None:
        odoo = MagicMock()
        odoo.read.return_value = [
            {"id": 99, "name": "INV/1", "state": "posted", "payment_state": "paid", "amount_residual": 0, "move_type": "out_invoice", "partner_id": [43, "P"]}
        ]
        with patch.object(dispensary, "execute") as execute:
            invoice = dispensary.ensure_pharmacy_invoice(
                odoo,
                {"id": 51, "state": "sale", "invoice_ids": [99], "name": "S00051", "shop_id": [1, "Pharmacy Counter"]},
            )
        execute.assert_not_called()
        self.assertEqual(invoice["payment_state"], "paid")

    def test_partner_catch_up_only_confirms_pharmacy_drafts(self) -> None:
        odoo = MagicMock()
        confirmed: list[int] = []

        def fake_ensure(_odoo, sale):
            confirmed.append(int(sale["id"]))
            return {"id": 1}

        orders = [
            {"id": 66, "state": "draft", "shop_id": [1, "Pharmacy Counter"]},
            {"id": 67, "state": "draft", "shop_id": [6, "Accommodation"]},
            {"id": 51, "state": "sale", "shop_id": [1, "Pharmacy Counter"]},
        ]
        with patch.object(dispensary, "ensure_pharmacy_invoice", side_effect=fake_ensure):
            changed = dispensary.ensure_partner_pharmacy_invoices(odoo, orders)
        self.assertTrue(changed)
        self.assertEqual(confirmed, [66])


class PharmacyInventoryFallbackTests(unittest.TestCase):
    def test_receive_finds_odoo_mapped_test_drug(self) -> None:
        import pharmacy_inventory as stockroom

        odoo = MagicMock()
        with (
            patch.object(stockroom, "_catalogue_entries", return_value=[]),
            patch.object(
                stockroom.dispensary,
                "find_pharmacy_products",
                return_value={"2ee7a8c8-e9f0-4637-898f-4fcea987bea2": {"id": 2386, "name": "Amoxicillin 500 mg — TEST", "uom_id": [1, "Units"]}},
            ),
        ):
            entry = stockroom._find_entry(odoo, "2ee7a8c8-e9f0-4637-898f-4fcea987bea2")
        self.assertEqual(entry["drugUuid"], "2ee7a8c8-e9f0-4637-898f-4fcea987bea2")
        self.assertIn("Amoxicillin", entry["openmrsName"])

    def test_unknown_drug_still_not_found(self) -> None:
        import pharmacy_inventory as stockroom

        odoo = MagicMock()
        with (
            patch.object(stockroom, "_catalogue_entries", return_value=[]),
            patch.object(stockroom.dispensary, "find_pharmacy_products", return_value={}),
        ):
            with self.assertRaises(ApiError) as error:
                stockroom._find_entry(odoo, "missing-uuid")
        self.assertEqual(error.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
