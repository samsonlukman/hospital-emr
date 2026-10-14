"""Birth and death certificate values, PDF, and Dead status."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

import certificates


BIRTH = {
    "referenceNo": "BRRN5",
    "occurredAt": "2023-07-08T11:36",
    "childName": "TAIWO Toluwanimi Marvelous",
    "gender": "Male",
    "weight": "3.8",
    "motherName": "TAIWO Hannah Amioye (335)",
    "caseId": "870",
    "fatherName": "Taiwo Babajide Adedayo",
    "address": "C51, Surulere Street, Along CAC Oke-Alafia, Ganmo Area, Ilorin, Kwara State.",
}

DEATH = {
    "referenceNo": "DRRN9",
    "occurredAt": "2025-08-28T09:00",
    "patientName": "BAMIDELE Adeleye (2651)",
    "caseId": "5651",
    "gender": "Female",
    "guardianName": "INDIVIDUAL CARD",
    "address": "Olorunsogo",
    "report": "",
}

RECORD = {
    "uuid": "patient-1",
    "identifier": "ABC201972",
    "givenName": "Damilola",
    "middleName": "",
    "familyName": "Damilola",
    "gender": "F",
    "birthdate": "2006-08-07",
    "alive": True,
    "deathDate": "",
    "address": {"address1": "Olorunsogo", "address2": "", "cityVillage": "Ilorin", "stateProvince": ""},
}


class CertificatePdfTests(unittest.TestCase):
    def test_birth_and_death_pdfs_carry_the_record_values(self) -> None:
        birth = certificates.render_pdf("birth", BIRTH)
        death = certificates.render_pdf("death", DEATH)
        self.assertTrue(birth.startswith(b"%PDF"))
        self.assertIn(b"BRRN5", birth)
        self.assertIn(b"TAIWO Toluwanimi Marvelous", birth)
        self.assertIn(b"3.8kg", birth)
        self.assertIn(b"DRRN9", death)
        self.assertIn(b"BAMIDELE Adeleye", death)
        self.assertIn(b"08/28/2025 09:00 AM", death)

    def test_birth_certificate_does_not_need_a_registered_child(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db = f"{folder}/certificates.sqlite3"
            with (
                patch.object(certificates.hospital_admin, "require_hospital_admin", return_value={"username": "admin"}),
                patch.object(certificates.patient_directory, "load_patient_record") as lookup,
            ):
                saved = certificates.save("cookie", {"kind": "birth", **BIRTH}, db_path=db)
            lookup.assert_not_called()
            self.assertTrue(saved["birth"]["certificateId"].startswith("birth-"))
            self.assertEqual(saved["birth"]["childName"], "TAIWO Toluwanimi Marvelous")
            self.assertEqual(saved["birth"]["motherName"], "TAIWO Hannah Amioye (335)")

    def test_saving_a_death_certificate_marks_the_patient_dead(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db = f"{folder}/certificates.sqlite3"
            with (
                patch.object(certificates.hospital_admin, "require_hospital_admin", return_value={"username": "admin"}),
                patch.object(certificates.patient_directory, "load_patient_record", return_value=RECORD),
                patch.object(certificates.patient_life_status, "update_life_status", return_value=RECORD) as mark,
            ):
                saved = certificates.save(
                    "cookie",
                    {"patientUuid": "patient-1", "kind": "death", **DEATH},
                    db_path=db,
                )
            self.assertEqual(saved["death"]["referenceNo"], "DRRN9")
            mark.assert_called_once()
            self.assertFalse(mark.call_args.args[1]["alive"])
            self.assertEqual(mark.call_args.args[1]["deathDate"], "2025-08-28")
