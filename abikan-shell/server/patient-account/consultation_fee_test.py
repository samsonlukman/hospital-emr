"""NHIS is a patient flag. It does not discount pharmacy bills."""

from __future__ import annotations

import unittest

import consultation


class NhisNameTests(unittest.TestCase):
    def test_nhis_is_added_to_the_surname_and_can_be_removed(self) -> None:
        given, middle, family = consultation.apply_nhis_mark("Rofiat", "", "Musiliu", True)
        self.assertEqual((given, middle, family), ("Rofiat", "", "Musiliu NHIS"))
        given, middle, family = consultation.apply_nhis_mark(given, middle, family, False)
        self.assertEqual((given, middle, family), ("Rofiat", "", "Musiliu"))
        self.assertEqual(consultation.strip_nhis_mark("Ade NHIS"), "Ade")


class ConfigOdoo:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.uid = 1
        self.models = self

    def search_read(self, model, domain, fields, limit=0):
        del model, fields, limit
        key = domain[0][2]
        return [row for row in self.rows if row.get("key") == key]

    def execute_kw(self, db, uid, password, model, method, args, kwargs=None):
        del db, uid, password, model, kwargs
        if method == "create":
            row = {"id": len(self.rows) + 1, **args[0]}
            self.rows.append(row)
            return row["id"]
        if method == "write":
            ids, values = args
            for row in self.rows:
                if row["id"] in ids:
                    row.update(values)
            return True
        raise AssertionError(method)


class NhisPatientFlagTest(unittest.TestCase):
    def test_flag_is_stored_without_a_financial_account(self) -> None:
        odoo = ConfigOdoo()
        self.assertTrue(consultation.store_patient_nhis(odoo, "patient-1", True))
        self.assertTrue(consultation.patient_is_nhis(odoo, "patient-1"))
        consultation.store_patient_nhis(odoo, "patient-1", False)
        self.assertFalse(consultation.patient_is_nhis(odoo, "patient-1"))

    def test_pharmacy_prices_are_not_reduced(self) -> None:
        self.assertEqual(consultation.NHIS_PHARMACY_DISCOUNT, 0)
        consultation.apply_nhis_pharmacy_discount(ConfigOdoo(), {"id": 1, "state": "draft"})


if __name__ == "__main__":
    unittest.main()
