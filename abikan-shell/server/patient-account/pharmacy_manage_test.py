"""Pharmacy catalogue create: explicit generic selection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pharmacy_manage as catalogue
from server import ApiError


class ParseAddMedicine(unittest.TestCase):
    def test_requires_concept_uuid_and_keeps_product_name_separate(self) -> None:
        parsed = catalogue._parse_add(
            {
                "name": "Panadol 500mg Tablet",
                "conceptUuid": "concept-1",
                "genericName": "Paracetamol",
                "strength": "500mg",
                "form": "Tablet",
                "manufacturer": "GSK",
                "price": 100,
            }
        )
        self.assertEqual(parsed["name"], "Panadol 500mg Tablet")
        self.assertEqual(parsed["productName"], "Panadol 500mg Tablet")
        self.assertEqual(parsed["conceptUuid"], "concept-1")
        self.assertEqual(parsed["generic"], "Paracetamol")
        self.assertEqual(parsed["manufacturer"], "GSK")

    def test_refuses_product_name_as_generic_lookup(self) -> None:
        with self.assertRaises(ApiError) as raised:
            catalogue._parse_add(
                {
                    "name": "add",
                    "strength": "10mg",
                    "form": "Tablet",
                    "price": 100,
                }
            )
        self.assertEqual(raised.exception.code, "concept_required")


class SearchGenerics(unittest.TestCase):
    def test_returns_matching_drug_concepts_for_selection(self) -> None:
        payload = {
            "results": [
                {
                    "uuid": "c1",
                    "display": "Cyproheptadine",
                    "retired": False,
                    "conceptClass": {"display": "Drug"},
                },
                {
                    "uuid": "c2",
                    "display": "Adderall",
                    "retired": False,
                    "conceptClass": {"display": "Drug"},
                },
                {
                    "uuid": "c3",
                    "display": "Blood add-on",
                    "retired": False,
                    "conceptClass": {"display": "Test"},
                },
            ]
        }
        with (
            patch.object(catalogue.dispensary, "require_pharmacist", return_value={"username": "pharmacy.abikan"}),
            patch.object(catalogue, "_openmrs", return_value=payload),
        ):
            result = catalogue.search_generics("cookie", "add")
        names = [row["name"] for row in result["generics"]]
        self.assertEqual(names, ["Adderall", "Cyproheptadine"])
        self.assertNotIn("Blood add-on", names)

    def test_create_medicine_uses_selected_concept_not_product_name(self) -> None:
        body = {
            "name": "add",
            "conceptUuid": "concept-para",
            "strength": "500mg",
            "form": "Tablet",
            "price": 100,
            "available": True,
        }
        with (
            patch.object(catalogue.dispensary, "require_pharmacist", return_value={"username": "pharmacy.abikan"}),
            patch.object(
                catalogue,
                "load_generic",
                return_value={"uuid": "concept-para", "name": "Paracetamol"},
            ) as load,
            patch.object(catalogue, "resolve_form", return_value="form-1"),
            patch.object(catalogue, "find_existing_drug", return_value=None),
            patch.object(catalogue, "_openmrs", return_value={"uuid": "drug-1"}) as openmrs,
            patch.object(catalogue.dispensary, "odoo_reader", return_value=object()),
            patch.object(catalogue, "wait_for_product", return_value={"id": 9, "list_price": 0}),
            patch.object(catalogue, "set_price"),
            patch.object(catalogue, "set_active"),
            patch.object(catalogue, "upsert_managed") as managed,
            patch("department_pricing.record_pharmacy_price_change"),
        ):
            result = catalogue.create_medicine(body, "cookie")
        load.assert_called_once_with("cookie", "concept-para")
        created = openmrs.call_args_list[0]
        payload = created.kwargs.get("payload")
        if payload is None and len(created.args) >= 4:
            payload = created.args[3]
        self.assertEqual(payload["name"], "add")
        self.assertEqual(payload["concept"], "concept-para")
        self.assertEqual(managed.call_args.args[1]["hospitalName"], "Paracetamol")
        self.assertEqual(managed.call_args.args[1]["conceptUuid"], "concept-para")
        self.assertEqual(result["genericName"], "Paracetamol")


class CreateMedicinesBatch(unittest.TestCase):
    def test_requires_lines(self) -> None:
        with patch.object(catalogue.dispensary, "require_pharmacist", return_value={"username": "pharmacy.abikan"}):
            with self.assertRaises(ApiError) as raised:
                catalogue.create_medicines_batch({}, "cookie")
        self.assertEqual(raised.exception.code, "lines_required")

    def test_validates_all_rows_before_creating(self) -> None:
        with patch.object(catalogue.dispensary, "require_pharmacist", return_value={"username": "pharmacy.abikan"}):
            with patch.object(catalogue, "create_medicine") as create:
                with self.assertRaises(ApiError) as raised:
                    catalogue.create_medicines_batch(
                        {
                            "lines": [
                                {
                                    "name": "Panadol 500mg Tablet",
                                    "conceptUuid": "concept-1",
                                    "genericName": "Paracetamol",
                                    "strength": "500mg",
                                    "form": "Tablet",
                                    "price": 100,
                                },
                                {
                                    "name": "Bad",
                                    "strength": "10mg",
                                    "form": "Tablet",
                                    "price": 50,
                                },
                            ]
                        },
                        "cookie",
                    )
        self.assertEqual(raised.exception.code, "concept_required")
        self.assertIn("Medicine 2", raised.exception.message)
        create.assert_not_called()

    def test_creates_valid_rows(self) -> None:
        with (
            patch.object(catalogue.dispensary, "require_pharmacist", return_value={"username": "pharmacy.abikan"}),
            patch.object(
                catalogue,
                "create_medicine",
                side_effect=[
                    {"status": "ok", "id": "d1", "name": "A"},
                    {"status": "ok", "id": "d2", "name": "B"},
                ],
            ),
        ):
            result = catalogue.create_medicines_batch(
                {
                    "lines": [
                        {
                            "name": "Alpha 10mg Tablet",
                            "conceptUuid": "c1",
                            "genericName": "Alpha",
                            "strength": "10mg",
                            "form": "Tablet",
                            "price": 100,
                        },
                        {
                            "name": "Beta 20mg Capsule",
                            "conceptUuid": "c2",
                            "genericName": "Beta",
                            "strength": "20mg",
                            "form": "Capsule",
                            "price": 200,
                        },
                    ]
                },
                "cookie",
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["saved"][0]["id"], "d1")
        self.assertEqual(result["saved"][1]["id"], "d2")


if __name__ == "__main__":
    unittest.main()
