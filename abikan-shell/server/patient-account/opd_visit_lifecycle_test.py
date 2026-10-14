"""Document current OPD visit lifecycle. No 24-hour expiry is implemented."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import registration as reception
import registration_patient as arrival
from server import ApiError

PATIENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OPD_VISIT = "11111111-1111-4111-8111-111111111111"
IPD_VISIT = "22222222-2222-4222-8222-222222222222"
CLOSED_VISIT = "33333333-3333-4333-8333-333333333333"
FUTURE_VISIT = "44444444-4444-4444-8444-444444444444"
VISIT_TYPE = "opd-type-uuid"
LOCATION = "opd-1-uuid"


def open_visit(uuid: str = OPD_VISIT, patient: str = PATIENT_A, **overrides: object) -> dict[str, object]:
    row = {
        "uuid": uuid,
        "startDatetime": "2026-09-02T08:00:00.000+0000",
        "open": True,
        "visitType": "OPD",
        "location": "OPD-1",
        "patient": {"uuid": patient},
    }
    row.update(overrides)
    return row


class OpdLifecycleCurrentBehaviorTests(unittest.TestCase):
    def test_started_opd_visit_is_open_because_stop_datetime_is_empty(self) -> None:
        created = {"uuid": "new-opd", "startDatetime": "2026-09-03T09:00:00.000+0000"}
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(
                arrival,
                "load_visit_types",
                return_value=[
                    {"uuid": VISIT_TYPE, "name": "OPD", "label": "General Outpatient", "bucket": "outpatient"}
                ],
            ),
            patch.object(arrival, "load_login_locations", return_value=[{"uuid": LOCATION, "name": "OPD-1"}]),
            patch.object(arrival, "locations_for_visit", return_value=[{"uuid": LOCATION, "name": "OPD-1"}]),
            patch("daily_visit_number.ignore_client_number"),
            patch("daily_visit_number.begin_request", return_value=None),
            patch("daily_visit_number.create_visit_with_number", return_value=(created, "021")),
            patch("daily_visit_number.finish_request"),
        ):
            result = arrival.start_visit(
                PATIENT_A,
                {"visitTypeUuid": VISIT_TYPE, "locationUuid": LOCATION, "requestId": "life-1"},
                "JSESSIONID=rec",
            )
        self.assertTrue(result["created"])
        self.assertTrue(result["open"])
        self.assertNotIn("stopDatetime", result)

    def test_open_opd_visit_blocks_a_duplicate_for_this_patient_only(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=open_visit()),
            patch("daily_visit_number.create_visit_with_number") as create,
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": VISIT_TYPE}, "JSESSIONID=rec")
        create.assert_not_called()
        self.assertFalse(result["created"])
        self.assertEqual(result["code"], reception.VISIT_ALREADY_OPEN_CODE)
        self.assertEqual(result["uuid"], OPD_VISIT)

    def test_closed_opd_visit_is_not_open(self) -> None:
        payload = {
            "results": [
                {
                    "uuid": CLOSED_VISIT,
                    "startDatetime": "2026-09-01T08:00:00.000+0000",
                    "stopDatetime": "2026-09-01T12:00:00.000+0000",
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_A},
                }
            ]
        }
        with patch.object(reception, "_openmrs_json", return_value=payload):
            self.assertIsNone(reception.latest_open_visit(PATIENT_A, "JSESSIONID=rec"))

    def test_future_dated_open_opd_is_still_open_not_expired(self) -> None:
        payload = {
            "results": [
                {
                    "uuid": FUTURE_VISIT,
                    "startDatetime": "2026-09-04T08:00:00.000+0000",
                    "stopDatetime": None,
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_A},
                }
            ]
        }
        with (
            patch.object(reception, "_openmrs_json", return_value=payload),
            patch.object(
                reception,
                "load_visit",
                return_value=open_visit(FUTURE_VISIT, startDatetime="2026-09-04T08:00:00.000+0000"),
            ),
        ):
            found = reception.latest_open_visit(PATIENT_A, "JSESSIONID=rec")
        self.assertEqual(found["uuid"], FUTURE_VISIT)

    def test_open_means_empty_stop_datetime_with_no_clock_window(self) -> None:
        source = Path(reception.__file__).read_text(encoding="utf-8")
        self.assertIn("Open = stopDatetime empty. No extra time window.", source)
        self.assertNotRegex(source, r"24.?hour|timedelta\(hours=24\)|auto.?close")

    def test_ipd_open_visit_is_not_closed_by_opd_start(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=open_visit(IPD_VISIT, visitType="IPD")),
            patch("daily_visit_number.create_visit_with_number") as create,
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": VISIT_TYPE}, "JSESSIONID=rec")
        create.assert_not_called()
        self.assertEqual(result["uuid"], IPD_VISIT)
        self.assertEqual(result["code"], reception.ADMISSION_IN_PROGRESS_CODE)
        self.assertFalse(result["created"])

    def test_create_visit_context_does_not_load_card_pricing(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(reception, "load_openmrs_patient", return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"}),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(arrival, "_visit_type_options", return_value=[]),
            patch.object(reception, "card_catalog") as cards,
            patch.object(reception, "odoo_reader") as odoo,
        ):
            payload = arrival.build_visit_context(PATIENT_A, "JSESSIONID=rec")
        cards.assert_not_called()
        odoo.assert_not_called()
        self.assertNotIn("cards", payload)
        self.assertNotIn("canCreateCharge", payload)

    def test_load_visit_rejects_another_patients_visit(self) -> None:
        with patch.object(
            reception,
            "_openmrs_json",
            return_value={
                "uuid": OPD_VISIT,
                "startDatetime": "2026-09-02T08:00:00.000+0000",
                "stopDatetime": None,
                "visitType": {"name": "OPD"},
                "location": {"name": "OPD-1"},
                "patient": {"uuid": PATIENT_A},
            },
        ):
            with self.assertRaises(ApiError) as caught:
                reception.load_visit(OPD_VISIT, PATIENT_B, "JSESSIONID=rec")
        self.assertEqual(caught.exception.code, "wrong_patient")

    def test_consultation_module_does_not_end_visits(self) -> None:
        source = Path(__file__).with_name("consultation.py").read_text(encoding="utf-8")
        self.assertNotIn("endVisit", source)
        self.assertNotIn("end_visit", source)

    def test_inpatient_end_visit_is_admit_conversion_not_opd_expiry(self) -> None:
        source = Path(__file__).with_name("inpatient.py").read_text(encoding="utf-8")
        self.assertIn("bahmnicore/visit/endVisit", source)
        self.assertIn("def _end_open_non_ipd_visits", source)
        self.assertIn("def _visit_type_is_ipd", source)
        self.assertNotRegex(source, r"24.?hour|timedelta\(hours=24\)")


if __name__ == "__main__":
    unittest.main()
