"""Unit tests for multi-item pharmacy stock receive/adjust parsing."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pharmacy_inventory as stockroom
from server import ApiError


class ReceiveBatchParseTests(unittest.TestCase):
    def test_requires_lines(self) -> None:
        with self.assertRaises(ApiError) as caught:
            stockroom._parse_receive_lines({})
        self.assertEqual(caught.exception.code, "lines_required")

    def test_rejects_zero_quantity(self) -> None:
        with self.assertRaises(ApiError) as caught:
            stockroom._parse_receive_lines(
                {"lines": [{"drugUuid": "drug-1", "quantity": 0, "purchasePrice": 10}]}
            )
        self.assertEqual(caught.exception.code, "invalid_quantity")

    def test_parses_valid_lines(self) -> None:
        lines = stockroom._parse_receive_lines(
            {
                "lines": [
                    {"drugUuid": "drug-1", "quantity": 2, "purchasePrice": 15},
                    {"drugUuid": "drug-2", "quantity": "3.5", "purchasePrice": "20"},
                ]
            }
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["drugUuid"], "drug-1")
        self.assertEqual(lines[1]["quantity"], 3.5)


class AdjustBatchParseTests(unittest.TestCase):
    def test_requires_reason(self) -> None:
        with self.assertRaises(ApiError) as caught:
            stockroom._parse_adjust_lines(
                {"lines": [{"drugUuid": "drug-1", "direction": "increase", "quantity": 1}]}
            )
        self.assertEqual(caught.exception.code, "missing_reason")

    def test_parses_valid_lines(self) -> None:
        lines = stockroom._parse_adjust_lines(
            {
                "lines": [
                    {
                        "drugUuid": "drug-1",
                        "direction": "decrease",
                        "quantity": 2,
                        "reason": "Damaged stock",
                    }
                ]
            }
        )
        self.assertEqual(lines[0]["direction"], "decrease")
        self.assertEqual(lines[0]["reason"], "Damaged stock")


class AdjustBatchValidateThenApplyTests(unittest.TestCase):
    def test_stops_after_first_apply_failure(self) -> None:
        planned_body = {
            "reference": "COUNT-1",
            "note": "",
            "lines": [
                {
                    "drugUuid": "drug-1",
                    "direction": "increase",
                    "quantity": 1,
                    "reason": "Physical stock count",
                },
                {
                    "drugUuid": "drug-2",
                    "direction": "increase",
                    "quantity": 1,
                    "reason": "Physical stock count",
                },
            ],
        }

        def fake_mapped(_odoo, drug_uuid: str):
            return (
                {"openmrsName": drug_uuid, "brandName": ""},
                {"id": 1 if drug_uuid == "drug-1" else 2, "list_price": 10},
            )

        calls: list[str] = []

        def fake_adjust(drug_uuid: str, body: dict, cookie: str):
            calls.append(drug_uuid)
            if drug_uuid == "drug-2":
                raise ApiError(409, "insufficient_stock", "Stock cannot go below zero.")
            return {
                "status": "ok",
                "item": {"name": "Paracetamol"},
                "adjustment": {"resultingOnHand": 5},
            }

        with (
            patch.object(stockroom, "require_inventory_manager", return_value={"username": "pharm"}),
            patch.object(stockroom.dispensary, "odoo_reader", return_value=object()),
            patch.object(stockroom.dispensary, "stock_location_id", return_value=9),
            patch.object(stockroom, "_mapped_product", side_effect=fake_mapped),
            patch.object(
                stockroom,
                "stock_levels",
                return_value={"onHand": 4, "reserved": 0, "available": 4},
            ),
            patch.object(stockroom, "adjust_stock", side_effect=fake_adjust),
        ):
            result = stockroom.adjust_stock_batch(planned_body, "cookie")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["saved"]), 1)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(calls, ["drug-1", "drug-2"])


if __name__ == "__main__":
    unittest.main()
