"""Nurse discharge must send the open visit id to OpenMRS."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import inpatient
from server import ApiError


PATIENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VISIT = "22222222-2222-4222-8222-222222222222"
BED = {
    "bedUuid": "bed-1",
    "bedId": 2,
    "bedNumber": "Bed 02",
    "areaName": "Hawawu Maternity Ward",
    "areaUuid": "ward-1",
    "status": "OCCUPIED",
}


class DischargeVisitUuidTests(unittest.TestCase):
    def test_discharge_includes_open_ipd_visit_uuid(self) -> None:
        posts: list[tuple[str, dict]] = []

        def capture(method: str, path: str, cookie: str, body=None, **kwargs):
            if method == "POST":
                posts.append((path, body or {}))
            return {}

        with (
            patch.object(inpatient, "require_assign_user", return_value={"uuid": "nurse-1"}),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", side_effect=[BED, None]),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_open_ipd_visit", side_effect=[{"uuid": VISIT}, {"uuid": VISIT}]),
            patch.object(inpatient, "_open_visits", return_value=[{"uuid": VISIT}]),
            patch.object(inpatient, "_end_visit") as end_visit,
            patch.object(inpatient, "_patient_brief", return_value={"uuid": PATIENT, "name": "Olusegun", "mrn": "ABC1"}),
            patch.object(inpatient, "openmrs_call", side_effect=capture),
            patch.object(inpatient, "_attach_billing", side_effect=lambda stay, _cb: stay),
            patch.object(inpatient, "_admin_as_of", return_value=None),
        ):
            result = inpatient.discharge_patient({"patientUuid": PATIENT}, "cookie")

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["bedReleased"])
        self.assertEqual(len(posts), 1)
        self.assertIn("/bahmnicore/discharge", posts[0][0])
        self.assertEqual(posts[0][1].get("visitUuid"), VISIT)
        self.assertEqual(posts[0][1].get("patientUuid"), PATIENT)
        end_visit.assert_called_once_with(VISIT, "cookie")

    def test_discharge_fails_clearly_without_open_visit(self) -> None:
        with (
            patch.object(inpatient, "require_assign_user", return_value={"uuid": "nurse-1"}),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=BED),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_open_ipd_visit", return_value=None),
            patch.object(inpatient, "_open_visits", return_value=[]),
        ):
            with self.assertRaises(ApiError) as caught:
                inpatient.discharge_patient({"patientUuid": PATIENT}, "cookie")
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.code, "visit_required")


if __name__ == "__main__":
    unittest.main()
