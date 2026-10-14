import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import laboratory_inventory as stock
from server import ApiError


class LaboratoryInventoryStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "laboratory_inventory.sqlite3"
        self.user = {"username": "lab.tech", "display": "Lab Tech"}

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_seeds_consumables_and_adjusts_stock(self) -> None:
        with (
            patch.object(stock, "_store_path", return_value=self.path),
            patch.object(stock, "require_lab_inventory_user", return_value=self.user),
        ):
            listed = stock.list_consumables("cookie")
            self.assertGreaterEqual(len(listed["items"]), 5)
            created = stock.create_consumable(
                {
                    "name": "Blood culture bottle",
                    "kind": "consumable",
                    "unit": "bottle",
                    "onHand": 10,
                    "purchasePrice": 450,
                },
                "cookie",
            )
            adjusted = stock.adjust_consumable(
                created["item"]["id"],
                {"reason": "Received stock", "onHand": 18, "purchasePrice": 500},
                "cookie",
            )
            unchanged = stock.adjust_consumable(
                created["item"]["id"],
                {"reason": "Used in laboratory", "onHand": 7},
                "cookie",
            )
        self.assertEqual(created["item"]["onHand"], 10)
        self.assertEqual(created["item"]["purchasePrice"], 450)
        self.assertEqual(adjusted["item"]["purchasePrice"], 500)
        self.assertEqual(unchanged["item"]["onHand"], 7)
        self.assertEqual(unchanged["item"]["purchasePrice"], 500)

    def test_receives_and_reserves_blood_unit(self) -> None:
        with (
            patch.object(stock, "_store_path", return_value=self.path),
            patch.object(stock, "require_lab_inventory_user", return_value=self.user),
        ):
            received = stock.receive_blood_unit(
                {
                    "component": "Whole blood",
                    "abo": "O",
                    "rh": "Positive",
                    "bagNumber": "BB-1001",
                    "expiresOn": "2099-12-31",
                    "volumeMl": 450,
                },
                "cookie",
            )
            updated = stock.update_blood_unit_status(
                received["unit"]["id"],
                {"status": "reserved", "patientName": "Ada Okafor"},
                "cookie",
            )
            listed = stock.list_blood_units("cookie")
        self.assertEqual(received["unit"]["status"], "available")
        self.assertEqual(updated["unit"]["status"], "reserved")
        self.assertEqual(updated["unit"]["patientName"], "Ada Okafor")
        self.assertEqual(listed["counts"]["reserved"], 1)

    def test_rejects_duplicate_bag_number(self) -> None:
        body = {
            "component": "Packed red cells",
            "abo": "A",
            "rh": "Negative",
            "bagNumber": "BB-DUP",
            "expiresOn": "2099-01-01",
        }
        with (
            patch.object(stock, "_store_path", return_value=self.path),
            patch.object(stock, "require_lab_inventory_user", return_value=self.user),
        ):
            stock.receive_blood_unit(body, "cookie")
            with self.assertRaises(ApiError) as raised:
                stock.receive_blood_unit(body, "cookie")
        self.assertEqual(raised.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
