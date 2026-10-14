"""Department revenue scope, attribution, and excluded invoice states."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from server import ApiError

import department_revenue as revenue
import finance_summary as finance
import hospital_admin as administration
import registration as reception
import consultation as clinical
import laboratory as lab
import pharmacy as dispensary
import radiology as imaging
import accountant as cashier


def _user(roles: list[str], privileges: list[str], username: str) -> dict:
    return {
        "uuid": f"user-{username}",
        "username": username,
        "roles": roles,
        "privileges": privileges,
    }


RECEPTION = _user(["Abikan:Reception"], ["app:registration"], "reception.abikan")
DOCTOR = _user(["Abikan:Doctor"], ["app:clinical"], "doctor.abikan")
LAB = _user(["Abikan:Laboratory"], ["app:lab-lite"], "lab.abikan")
PHARMACY = _user(["Abikan:Pharmacy"], ["bahmni:clinical:dispense"], "pharmacy.abikan")
RADIOLOGY = _user(["Abikan:Radiology"], ["app:radiology-upload"], "radiology.abikan")
NURSE = _user(["Abikan:Nursing"], ["app:adt"], "nurse.abikan")
ACCOUNTANT = _user(["Abikan:Accountant"], ["abikan:accountant"], "accountant.abikan")
HOSPITAL_ADMIN = _user(
    ["Abikan:Hospital Admin"],
    ["abikan:admin:staff", "abikan:admin:analytics"],
    "hospitaladmin.abikan",
)


class Attribution(unittest.TestCase):
    def test_shop_and_category_map_to_existing_departments(self) -> None:
        from server import identify_department

        self.assertEqual(identify_department("Registration Desk", []), "Registration")
        self.assertEqual(identify_department("Consultation Desk", []), "Consultation")
        self.assertEqual(identify_department("Laboratory", []), "Laboratory")
        self.assertEqual(identify_department("Radiology Desk", []), "Radiology")
        self.assertEqual(identify_department("Pharmacy Counter", []), "Pharmacy")
        self.assertEqual(identify_department("Accommodation", []), "Accommodation")
        self.assertEqual(identify_department("Main Theatre", []), "Theatre")
        self.assertEqual(identify_department("", ["Physiotherapy"]), "Physiotherapy")
        self.assertEqual(identify_department("", ["Dental"]), "Dental")
        self.assertIsNone(identify_department("", []))

    def test_posted_invoices_are_grouped_and_reversed_are_excluded(self) -> None:
        odoo = MagicMock()
        odoo.search_read.side_effect = [
            [
                {
                    "id": 1,
                    "invoice_origin": "S0001",
                    "amount_total": 2000.0,
                    "payment_state": "not_paid",
                    "invoice_line_ids": [],
                },
                {
                    "id": 2,
                    "invoice_origin": "S0002",
                    "amount_total": 4000.0,
                    "payment_state": "reversed",
                    "invoice_line_ids": [],
                },
                {
                    "id": 3,
                    "invoice_origin": "S0003",
                    "amount_total": 1500.0,
                    "payment_state": "paid",
                    "invoice_line_ids": [],
                },
            ],
            [
                {"name": "S0001", "shop_id": [11, "Laboratory"]},
                {"name": "S0003", "shop_id": [12, "Pharmacy Counter"]},
            ],
            [],  # posted credit notes / refunds
        ]
        totals = finance.billed_by_department(odoo, "2026-09-07", "2026-09-07")
        self.assertEqual(totals["Laboratory"], 2000.0)
        self.assertEqual(totals["Pharmacy"], 1500.0)
        self.assertEqual(totals["Consultation"], 0.0)
        self.assertNotIn(4000.0, totals.values())
        invoice_domain = odoo.search_read.call_args_list[0][0][1]
        self.assertEqual(invoice_domain, finance.billed_domain("2026-09-07", "2026-09-07"))
        self.assertIn(("state", "=", "posted"), invoice_domain)
        refund_domain = odoo.search_read.call_args_list[2][0][1]
        self.assertEqual(refund_domain, finance.refund_domain("2026-09-07", "2026-09-07"))

    def test_category_fallback_when_shop_is_missing(self) -> None:
        odoo = MagicMock()
        odoo.search_read.side_effect = [
            [
                {
                    "id": 9,
                    "invoice_origin": "S0099",
                    "amount_total": 800.0,
                    "payment_state": "paid",
                    "invoice_line_ids": [44],
                }
            ],
            [],
            [],  # refunds
        ]
        odoo.read.side_effect = [
            [{"id": 44, "move_id": [9, "INV"], "product_id": [7, "FBC"]}],
            [{"id": 7, "categ_id": [3, "Laboratory"]}],
            [{"id": 3, "name": "Laboratory", "complete_name": "All / Services / Laboratory"}],
        ]
        totals = finance.billed_by_department(odoo, "2026-09-01", "2026-09-07")
        self.assertEqual(totals["Laboratory"], 800.0)


class ViewerScope(unittest.TestCase):
    def test_department_staff_see_only_their_department(self) -> None:
        cases = [
            (RECEPTION, ["Registration"]),
            (DOCTOR, ["Consultation"]),
            (LAB, ["Laboratory"]),
            (PHARMACY, ["Pharmacy"]),
            (RADIOLOGY, ["Radiology"]),
            (NURSE, ["Accommodation"]),
        ]
        for user, expected in cases:
            with (
                patch.object(administration.core, "require_session"),
                patch("accountant.load_openmrs_user", return_value=user),
            ):
                _viewer, allowed = revenue.require_revenue_viewer("cookie")
            self.assertEqual(allowed, expected, user["username"])

    def test_finance_and_admin_see_hospital_scope(self) -> None:
        for user in (ACCOUNTANT, HOSPITAL_ADMIN):
            with (
                patch.object(administration.core, "require_session"),
                patch("accountant.load_openmrs_user", return_value=user),
            ):
                _viewer, allowed = revenue.require_revenue_viewer("cookie")
            self.assertIsNone(allowed, user["username"])

    def test_unrelated_staff_are_refused(self) -> None:
        security = _user(["Abikan:Security"], [], "security.abikan")
        with (
            patch.object(administration.core, "require_session"),
            patch("accountant.load_openmrs_user", return_value=security),
            self.assertRaises(ApiError) as raised,
        ):
            revenue.require_revenue_viewer("cookie")
        self.assertEqual(raised.exception.status, 403)
        self.assertNotIn("OpenMRS", raised.exception.message)

    def test_payload_hides_other_departments_from_lab(self) -> None:
        totals = {"Laboratory": 900.0, "Pharmacy": 4000.0, "Consultation": 2500.0}
        currency = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
        rows = revenue.serialize_department_rows(totals, currency, ["Laboratory"])
        self.assertEqual([row["department"] for row in rows], ["Laboratory"])
        self.assertEqual(rows[0]["amount"], 900.0)
        self.assertEqual(rows[0]["share"], 1.0)

    def test_hospital_rows_include_contribution_share(self) -> None:
        totals = {"Laboratory": 250.0, "Pharmacy": 750.0}
        currency = {"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}
        rows = revenue.serialize_department_rows(totals, currency, None)
        lab_row = next(row for row in rows if row["department"] == "Laboratory")
        pharmacy_row = next(row for row in rows if row["department"] == "Pharmacy")
        self.assertEqual(lab_row["share"], 0.25)
        self.assertEqual(pharmacy_row["share"], 0.75)
        self.assertTrue(any(row["department"] == "Consultation" and row["amount"] == 0 for row in rows))


class HelpersStayAligned(unittest.TestCase):
    def test_existing_role_helpers_are_used(self) -> None:
        self.assertTrue(reception.is_registrar(RECEPTION))
        self.assertTrue(clinical.is_clinician(DOCTOR))
        self.assertTrue(lab.is_lab_user(LAB))
        self.assertTrue(dispensary.is_pharmacist(PHARMACY))
        self.assertTrue(imaging.is_radiology_user(RADIOLOGY))
        self.assertTrue(cashier.is_accountant(ACCOUNTANT))
        self.assertTrue(administration.is_hospital_admin(HOSPITAL_ADMIN))


if __name__ == "__main__":
    unittest.main()
