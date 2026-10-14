import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hmo
from server import ApiError


RECEPTION = {
    "username": "reception.abikan",
    "roles": ["Abikan:Reception"],
    "privileges": ["app:registration"],
}
NURSE = {
    "username": "nurse.abikan",
    "roles": ["Abikan:Nursing"],
    "privileges": ["app:adt"],
}


class HmoRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = str(Path(self.directory.name) / "hmo.sqlite3")
        self.previous = hmo.HMO_DB_PATH
        hmo.HMO_DB_PATH = self.db

    def tearDown(self) -> None:
        hmo.HMO_DB_PATH = self.previous
        self.directory.cleanup()

    @patch.object(hmo, "_user", return_value=NURSE)
    def test_nurse_can_read_assignments(self, _user) -> None:
        self.assertEqual(hmo.list_assignments("cookie"), {"assignments": []})

    @patch.object(hmo, "_user", return_value=NURSE)
    def test_nurse_cannot_add_patient(self, _user) -> None:
        with self.assertRaises(ApiError) as error:
            hmo.assign_patient(
                {"patientUuid": "patient-1", "scheme": "NHIA", "body": "Hygeia"},
                "cookie",
            )
        self.assertEqual(error.exception.code, "forbidden")

    @patch.object(hmo.patient_directory, "load_patient_identity", return_value={"name": "Ada Patient", "mrn": "ABC001"})
    @patch.object(hmo, "_user", return_value=RECEPTION)
    def test_reception_assigns_and_replaces_patient_coverage(self, _user, identity) -> None:
        first = hmo.assign_patient(
            {"patientUuid": "patient-1", "scheme": "NHIA", "body": "Hygeia"},
            "cookie",
        )
        self.assertEqual(first["assignment"]["body"], "Hygeia")
        hmo.assign_patient(
            {"patientUuid": "patient-1", "scheme": "HMO (Private)", "body": "Reliance"},
            "cookie",
        )
        rows = hmo.list_assignments("cookie")
        self.assertEqual(len(rows["assignments"]), 1)
        self.assertEqual(rows["assignments"][0]["body"], "Reliance")

    @patch.object(hmo, "_user", return_value=RECEPTION)
    def test_rejects_body_from_wrong_scheme(self, _user) -> None:
        with self.assertRaises(ApiError) as error:
            hmo.assign_patient(
                {"patientUuid": "patient-1", "scheme": "NHIA", "body": "Reliance"},
                "cookie",
            )
        self.assertEqual(error.exception.code, "body_required")


if __name__ == "__main__":
    unittest.main()
