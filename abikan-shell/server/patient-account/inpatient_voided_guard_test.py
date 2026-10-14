"""Guards against voided patients on the ward board."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import inpatient
from server import ApiError


class VoidedPatientGuardTests(unittest.TestCase):
    def test_require_active_patient_rejects_voided(self) -> None:
        with patch.object(
            inpatient,
            "openmrs_call",
            return_value={"uuid": "patient-voided", "voided": True},
        ):
            with self.assertRaises(ApiError) as caught:
                inpatient._require_active_patient("patient-voided", "cookie")
        self.assertEqual(caught.exception.code, "patient_inactive")

    def test_awaiting_skips_voided_patients(self) -> None:
        rows = [
            {
                "patientUuid": "active-1",
                "patientName": "Active One",
                "mrn": "ABC204001",
                "sex": "Female",
                "age": "30",
                "requested": "2026-09-08",
                "visitUuid": "visit-1",
            },
            {
                "patientUuid": "voided-1",
                "patientName": "Old One",
                "mrn": "ABC200001",
                "sex": "Male",
                "age": "40",
                "requested": "2026-09-01",
                "visitUuid": "visit-2",
            },
        ]
        with (
            patch.object(inpatient, "_awaiting_from_open_ipd", return_value=rows),
            patch.object(inpatient, "_login_location_uuids", return_value=[]),
            patch.object(
                inpatient,
                "_patient_is_active",
                side_effect=lambda uuid, cookie: uuid == "active-1",
            ),
        ):
            awaiting = inpatient._awaiting_patients("cookie")
        self.assertEqual([row["patientUuid"] for row in awaiting], ["active-1"])


if __name__ == "__main__":
    unittest.main()
