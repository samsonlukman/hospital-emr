"""Department pricing validation, authorization, and history."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import department_pricing
import price_history
import server as core


class ParseCataloguePriceTests(unittest.TestCase):
    def test_accepts_naira_and_zero(self) -> None:
        self.assertEqual(department_pricing.parse_catalogue_price("₦1,500"), 1500.0)
        self.assertEqual(department_pricing.parse_catalogue_price(0), 0.0)
        self.assertEqual(department_pricing.parse_catalogue_price("10.259"), 10.26)

    def test_rejects_invalid_values(self) -> None:
        for raw in (None, True, "", "abc", "-1", "nan", "inf"):
            with self.subTest(raw=raw):
                with self.assertRaises(core.ApiError) as caught:
                    department_pricing.parse_catalogue_price(raw)
                self.assertEqual(caught.exception.code, "invalid_price")


class PriceHistoryTests(unittest.TestCase):
    def test_records_change_and_skips_duplicate_same_amount(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "audit.sqlite3")
            actor = {"uuid": "u1", "username": "lab.abikan", "display": "Laboratory Staff"}
            first = price_history.record_price_change(
                department="laboratory",
                item_id="concept-1",
                item_label="Malarial smear",
                currency="NGN",
                old_price=1500,
                new_price=2000,
                actor=actor,
                path=path,
            )
            same = price_history.record_price_change(
                department="laboratory",
                item_id="concept-1",
                item_label="Malarial smear",
                currency="NGN",
                old_price=2000,
                new_price=2000,
                actor=actor,
                path=path,
            )
            second = price_history.record_price_change(
                department="laboratory",
                item_id="concept-1",
                item_label="Malarial smear",
                currency="NGN",
                old_price=2000,
                new_price=2500,
                actor=actor,
                path=path,
            )
            rows = price_history.list_price_changes(
                department="laboratory", item_id="concept-1", path=path
            )
            self.assertTrue(first)
            self.assertIsNone(same)
            self.assertTrue(second)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["new_price"], 2500)
            self.assertEqual(rows[0]["actor_username"], "lab.abikan")
            self.assertTrue(rows[0]["occurred_at"])


class PricingAuthorizationTests(unittest.TestCase):
    def test_department_write_matrix(self) -> None:
        reception = {"roles": ["Abikan:Reception"], "privileges": ["app:registration"]}
        lab = {"roles": ["Abikan:Laboratory"], "privileges": ["app:lab-lite"]}
        pharmacy = {"roles": ["Abikan:Pharmacy"], "privileges": ["bahmni:clinical:dispense"]}
        doctor = {"roles": ["Abikan:Doctor"], "privileges": ["app:clinical"]}
        nurse = {"roles": ["Abikan:Nursing"], "privileges": []}
        accountant = {"roles": ["Abikan:Accountant"], "privileges": ["abikan:accountant"]}
        admin = {"roles": ["Abikan:Hospital Admin"], "privileges": ["abikan:admin:staff"]}

        self.assertTrue(department_pricing.can_write_pricing(reception, "reception"))
        self.assertFalse(department_pricing.can_write_pricing(reception, "laboratory"))
        self.assertTrue(department_pricing.can_write_pricing(lab, "laboratory"))
        self.assertFalse(department_pricing.can_write_pricing(lab, "pharmacy"))
        self.assertTrue(department_pricing.can_write_pricing(pharmacy, "pharmacy"))
        self.assertFalse(department_pricing.can_write_pricing(pharmacy, "laboratory"))
        self.assertFalse(department_pricing.can_write_pricing(doctor, "reception"))
        self.assertFalse(department_pricing.can_write_pricing(doctor, "laboratory"))
        self.assertFalse(department_pricing.can_write_pricing(nurse, "pharmacy"))
        self.assertFalse(department_pricing.can_write_pricing(accountant, "reception"))
        self.assertTrue(department_pricing.can_read_pricing(accountant, "laboratory"))
        self.assertTrue(department_pricing.can_read_pricing(admin, "pharmacy"))
        self.assertFalse(department_pricing.can_write_pricing(admin, "pharmacy"))

    def test_unauthenticated_write_is_denied(self) -> None:
        with patch.object(core, "require_session", side_effect=core.ApiError(401, "unauthenticated", "Sign in required.")):
            with self.assertRaises(core.ApiError) as caught:
                department_pricing.require_pricing_write("", "laboratory")
            self.assertEqual(caught.exception.status, 401)


class RegistrationEnsureDoesNotOverwriteTests(unittest.TestCase):
    def test_existing_product_keeps_live_price(self) -> None:
        import registration as reception

        class FakeOdoo:
            def search_read(self, *_args, **_kwargs):
                return [
                    {
                        "id": 9,
                        "name": "Individual Card",
                        "list_price": 1111,
                        "type": "service",
                        "uom_id": 1,
                        "taxes_id": [],
                        "invoice_policy": "order",
                        "default_code": "registration-individual",
                    }
                ]

            def read(self, *_args, **_kwargs):
                return [
                    {
                        "id": 9,
                        "name": "Individual Card",
                        "list_price": 1111,
                        "default_code": "registration-individual",
                    }
                ]

        written: list[object] = []

        def execute(_odoo, model, method, args, kwargs=None):
            written.append((model, method, args))
            return True

        with patch.object(reception, "execute", side_effect=execute):
            product = reception._ensure_product(
                FakeOdoo(),
                category_id=1,
                code="registration-individual",
                name="Individual Card",
                amount=2000,
            )
        self.assertEqual(product["list_price"], 1111)
        write_payload = written[0][2][1]
        self.assertNotIn("list_price", write_payload)


class LaboratoryConfigureDoesNotOverwriteTests(unittest.TestCase):
    def test_existing_staff_price_is_preserved(self) -> None:
        import lab_catalogue

        values = lab_catalogue.lab_product_write_values(
            name="Full Blood Count",
            category_id=3,
            catalogue_price=4500,
            existing_list_price=2750,
        )
        self.assertNotIn("list_price", values)
        self.assertEqual(values["name"], "Full Blood Count")
        self.assertEqual(values["categ_id"], 3)

    def test_placeholder_and_missing_products_receive_catalogue_price(self) -> None:
        import lab_catalogue

        created = lab_catalogue.lab_product_write_values(
            name="Malarial smear",
            category_id=3,
            catalogue_price=1500,
            existing_list_price=None,
        )
        placeholder = lab_catalogue.lab_product_write_values(
            name="Malarial smear",
            category_id=3,
            catalogue_price=1500,
            existing_list_price=1.0,
        )
        self.assertEqual(created["list_price"], 1500)
        self.assertEqual(placeholder["list_price"], 1500)

    def test_explicit_reset_overwrites_staff_price(self) -> None:
        import lab_catalogue

        values = lab_catalogue.lab_product_write_values(
            name="Full Blood Count",
            category_id=3,
            catalogue_price=4500,
            existing_list_price=2750,
            reset_prices=True,
        )
        self.assertEqual(values["list_price"], 4500)
        self.assertTrue(lab_catalogue.should_write_lab_list_price(2750, reset_prices=True))
        self.assertFalse(lab_catalogue.should_write_lab_list_price(2750))


class PharmacyQueueFilterTests(unittest.TestCase):
    def test_keeps_drug_order_uuids_only(self) -> None:
        import pharmacy as dispensary

        self.assertTrue(dispensary.is_pharmacy_external_id("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
        self.assertFalse(dispensary.is_pharmacy_external_id("lab:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
        self.assertFalse(dispensary.is_pharmacy_external_id("registration:visit-1"))
        self.assertFalse(dispensary.is_pharmacy_external_id("consultation:visit-1"))
        self.assertFalse(dispensary.is_pharmacy_external_id("pharmacy-sale:token-1"))
        self.assertFalse(dispensary.is_pharmacy_external_id(""))


if __name__ == "__main__":
    unittest.main()
