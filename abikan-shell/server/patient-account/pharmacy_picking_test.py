"""Pharmacy picking wizard helpers."""

from __future__ import annotations

import unittest

import pharmacy as dispensary


class PickIdsFromWizardContext(unittest.TestCase):
    def test_reads_button_validate_picking_ids(self) -> None:
        self.assertEqual(
            dispensary._pick_ids_from_wizard_context(
                {"button_validate_picking_ids": [19]},
                1,
            ),
            [19],
        )

    def test_reads_default_pick_ids_commands(self) -> None:
        self.assertEqual(
            dispensary._pick_ids_from_wizard_context(
                {"default_pick_ids": [[4, 19]]},
                1,
            ),
            [19],
        )
        self.assertEqual(
            dispensary._pick_ids_from_wizard_context(
                {"default_pick_ids": [[6, 0, [19, 20]]]},
                1,
            ),
            [19, 20],
        )

    def test_falls_back_to_current_picking(self) -> None:
        self.assertEqual(dispensary._pick_ids_from_wizard_context({}, 42), [42])


class DispenseAvailabilityTests(unittest.TestCase):
    def _clinical(self) -> dict:
        return {
            "uuid": "order-1",
            "encounterUuid": "enc-1",
            "ordered": "2026-10-12T10:00:00.000+0000",
            "quantity": 1,
            "drugName": "Paracetamol",
        }

    def test_billed_medicine_without_a_picking_can_be_dispensed(self) -> None:
        payload = dispensary.serialize_prescription(
            clinical=self._clinical(),
            line={"product_uom_qty": 1, "qty_delivered": 0},
            invoice={"payment_state": "not_paid", "amount_residual": 1500, "amount_total": 1500},
            picking=None,
            on_hand=0,
            sale={"id": 9, "state": "sale"},
        )
        self.assertTrue(payload["canDispense"])
        self.assertEqual(payload["dispensingStatus"], "READY TO DISPENSE")

    def test_shelf_medicine_without_stock_stays_blocked(self) -> None:
        payload = dispensary.serialize_prescription(
            clinical=self._clinical(),
            line={"product_uom_qty": 10, "qty_delivered": 0},
            invoice={"payment_state": "paid", "amount_residual": 0, "amount_total": 500},
            picking={"id": 4, "state": "confirmed"},
            on_hand=0,
            sale={"id": 9, "state": "sale"},
        )
        self.assertFalse(payload["canDispense"])

    def test_cancelled_picking_does_not_hide_a_live_one(self) -> None:
        chosen = dispensary.choose_picking(
            [
                {"id": 1, "state": "cancel"},
                {"id": 2, "state": "confirmed"},
            ]
        )
        self.assertEqual(chosen["id"], 2)


if __name__ == "__main__":
    unittest.main()
