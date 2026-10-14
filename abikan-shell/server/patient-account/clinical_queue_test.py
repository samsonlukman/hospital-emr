"""Today's visit lists for Clinical and Nursing."""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import clinical_queue as queue
from server import ApiError


def visit_row(visit_type: str, *, stop: str | None = None) -> dict:
    return {
        "uuid": f"visit-{visit_type.lower().replace(' ', '-')}",
        "startDatetime": "2026-09-29T08:10:00.000+0000",
        "stopDatetime": stop,
        "visitType": {"name": visit_type},
        "patient": {
            "uuid": f"patient-{visit_type.lower().replace(' ', '-')}",
            "display": f"{visit_type} Patient - ABC200010",
            "identifiers": [{"identifier": "ABC200010", "preferred": True}],
        },
        "attributes": [],
    }


class ClinicalQueueTests(unittest.TestCase):
    def test_doctor_list_keeps_outpatient_types_only(self) -> None:
        self.assertTrue(queue.is_queue_visit_type("OPD"))
        self.assertFalse(queue.is_queue_visit_type("IPD"))
        opd = queue.row_from_visit(visit_row("OPD"))
        ipd = queue.row_from_visit(visit_row("IPD"))
        nursing = queue.row_from_visit(visit_row("IPD"), any_visit_type=True)
        self.assertEqual(opd["visitType"], "OPD")
        self.assertIsNone(ipd)
        self.assertEqual(nursing["visitType"], "IPD")

    def test_nursing_todays_patients_includes_every_visit_started_today(self) -> None:
        today = datetime(2026, 9, 29, 12, 0, tzinfo=ZoneInfo("Africa/Lagos"))
        with (
            patch.object(queue, "hospital_today", return_value=today.date()),
            patch("inpatient.require_nursing_user", return_value={"uuid": "nurse"}),
            patch.object(
                queue,
                "load_recent_visits",
                return_value=[visit_row("OPD"), visit_row("IPD"), visit_row("ANC")],
            ),
        ):
            result = queue.build_nursing_todays_patients("JSESSIONID=nurse")
        types = {row["visitType"] for row in result["patients"]}
        self.assertEqual(types, {"OPD", "IPD", "ANC"})

    def test_nursing_todays_patients_requires_the_ward(self) -> None:
        with patch(
            "inpatient.require_nursing_user",
            side_effect=ApiError(403, "forbidden", "Ward only"),
        ):
            with self.assertRaises(ApiError) as raised:
                queue.build_nursing_todays_patients("JSESSIONID=doctor")
        self.assertEqual(raised.exception.status, 403)
