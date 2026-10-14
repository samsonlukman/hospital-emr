"""HMO statements include every charge in the period, including charges not yet invoiced."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import hmo_bills


class HmoBillsTest(unittest.TestCase):
    def test_statement_keeps_one_hmo_and_the_chosen_period(self) -> None:
        assignments = [
            {"patient_uuid": "p1", "patient_name": "Amina Bello", "hospital_number": "ABC200001", "scheme": "NHIA", "body": "Hygeia"},
            {"patient_uuid": "p2", "patient_name": "Tunde Ade", "hospital_number": "ABC200014", "scheme": "NHIA", "body": "Hygeia"},
            {"patient_uuid": "p3", "patient_name": "Other Person", "hospital_number": "ABC200099", "scheme": "HMO (Private)", "body": "Reliance"},
        ]
        charges = [
            {"patientUuid": "p1", "date": "2026-10-02", "description": "Consultation", "department": "Clinical", "amount": 5000, "status": "Unpaid"},
            {"patientUuid": "p1", "date": "2026-09-30", "description": "Old visit", "department": "Clinical", "amount": 1000, "status": "Unpaid"},
            {"patientUuid": "p2", "date": "2026-10-11", "description": "Pharmacy", "department": "Pharmacy", "amount": 8200, "status": "Paid"},
            {"patientUuid": "p2", "date": "2026-10-12", "description": "Malaria test", "department": "Laboratory", "amount": 1500, "status": "Not invoiced"},
            {"patientUuid": "p3", "date": "2026-10-04", "description": "Consultation", "department": "Clinical", "amount": 5000, "status": "Unpaid"},
        ]
        statement = hmo_bills.assemble_statement(
            assignments, charges, body="Hygeia", scheme="NHIA", start="2026-10-01", end="2026-10-31"
        )
        self.assertEqual([row["patientName"] for row in statement["patients"]], ["Amina Bello", "Tunde Ade"])
        self.assertEqual(len(statement["patients"][0]["lines"]), 1)
        self.assertEqual(statement["total"], 14700)
        html = hmo_bills.statement_html(statement)
        self.assertIn("Amount due from the HMO", html)
        self.assertNotIn("Already paid", html)
        self.assertIn("Hygeia", html)
        self.assertIn("0000 000 0000", html)

    def test_both_coverage_types_are_listed(self) -> None:
        bodies = hmo_bills.list_bodies(
            [{"scheme": "HMO (Private)", "body": "Reliance"}]
        )
        schemes = {row["scheme"] for row in bodies}
        self.assertEqual(schemes, {"NHIA", "HMO (Private)"})
        self.assertIn("Hygeia", [row["body"] for row in bodies if row["scheme"] == "NHIA"])
        self.assertIn("Reliance", [row["body"] for row in bodies if row["scheme"] == "HMO (Private)"])

    def test_send_asks_for_a_real_recipient(self) -> None:
        with self.assertRaises(hmo_bills.core.ApiError) as caught:
            hmo_bills._recipient("not-an-email")
        self.assertEqual(caught.exception.code, "recipient_required")

    def test_mail_is_not_pretended_when_smtp_is_absent(self) -> None:
        statement = hmo_bills.assemble_statement(
            [{"patient_uuid": "p1", "patient_name": "Amina Bello", "hospital_number": "ABC1", "scheme": "NHIA", "body": "Hygeia"}],
            [],
            body="Hygeia",
            scheme="NHIA",
            start="2026-10-01",
            end="2026-10-31",
        )
        with patch.dict("os.environ", {"ABIKAN_SMTP_HOST": ""}, clear=False):
            result = hmo_bills.deliver_statement(statement, "claims@hygeia.test")
        self.assertEqual(result["sent"], "no")
        self.assertIn("not set up", result["message"])


if __name__ == "__main__":
    unittest.main()
