"""Hospital Admin patient Alive / Deceased updates."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import hospital_admin as administration
import patient_directory as register
import patient_life_status as life
from server import ApiError


def _user(roles: list[str], privileges: list[str], username: str) -> dict:
    return {
        "uuid": f"user-{username}",
        "username": username,
        "roles": roles,
        "privileges": privileges,
    }


HOSPITAL_ADMIN = _user(
    ["Abikan:Hospital Admin"],
    ["abikan:admin:staff"],
    "hospitaladmin.abikan",
)
RECEPTION = _user(["Abikan:Reception"], ["app:registration"], "reception.abikan")
DOCTOR = _user(["Abikan:Doctor"], ["app:clinical"], "doctor.abikan")

ALIVE_RECORD = {
    "status": "ok",
    "uuid": "pat-1",
    "identifier": "ABC123",
    "givenName": "Adaeze",
    "middleName": "",
    "familyName": "Okafor",
    "alive": True,
    "deathDate": "",
}

DECEASED_RECORD = {
    **ALIVE_RECORD,
    "alive": False,
    "deathDate": "2026-09-01",
}


class LifeStatusParsing(unittest.TestCase):
    def test_parse_alive_accepts_yes_no(self) -> None:
        self.assertTrue(life.parse_alive("Yes"))
        self.assertFalse(life.parse_alive("No"))
        self.assertTrue(life.parse_alive(True))
        with self.assertRaises(ApiError) as raised:
            life.parse_alive("")
        self.assertEqual(raised.exception.code, "alive_required")

    def test_death_date_required_when_deceased_and_not_in_future(self) -> None:
        today = date(2026, 9, 7)
        self.assertEqual(life.parse_death_date("2026-09-01", today=today), date(2026, 9, 1))
        with self.assertRaises(ApiError) as raised:
            life.parse_death_date("", today=today)
        self.assertEqual(raised.exception.code, "death_date_required")
        with self.assertRaises(ApiError) as raised:
            life.parse_death_date("2026-09-08", today=today)
        self.assertEqual(raised.exception.code, "future_death_date")


class LifeStatusAccess(unittest.TestCase):
    def test_only_hospital_admin_can_change_status(self) -> None:
        with (
            patch.object(administration, "require_hospital_admin", side_effect=ApiError(403, "forbidden", life.LIFE_STATUS_FORBIDDEN)),
            self.assertRaises(ApiError) as raised,
        ):
            life.update_life_status("pat-1", {"alive": False, "deathDate": "2026-09-01", "requestId": "req-1"}, "cookie")
        self.assertEqual(raised.exception.status, 403)

        with (
            patch.object(administration.core, "require_session"),
            patch("accountant.load_openmrs_user", return_value=RECEPTION),
            self.assertRaises(ApiError) as raised,
        ):
            administration.require_hospital_admin("cookie")
        self.assertEqual(raised.exception.status, 403)

        with (
            patch.object(administration.core, "require_session"),
            patch("accountant.load_openmrs_user", return_value=DOCTOR),
            self.assertRaises(ApiError) as raised,
        ):
            administration.require_hospital_admin("cookie")
        self.assertEqual(raised.exception.status, 403)


class LifeStatusUpdate(unittest.TestCase):
    def test_marks_deceased_with_audit_and_keeps_patient_record(self) -> None:
        with (
            patch.object(administration, "require_hospital_admin", return_value=HOSPITAL_ADMIN),
            patch.object(register, "load_patient_record", side_effect=[ALIVE_RECORD, DECEASED_RECORD]),
            patch.object(life, "_write_person_life_status") as write,
            patch.object(life.admin_audit, "start_admin_event", return_value="evt-1") as start,
            patch.object(life.admin_audit, "finish_admin_event") as finish,
            patch.object(life.periods, "hospital_today", return_value=date(2026, 9, 7)),
        ):
            result = life.update_life_status(
                "pat-1",
                {"alive": False, "deathDate": "2026-09-01", "requestId": "req-deceased"},
                "cookie",
            )
        write.assert_called_once_with("pat-1", alive=False, death_day=date(2026, 9, 1))
        start.assert_called_once()
        self.assertEqual(start.call_args.kwargs["action"], "ADMIN_UPDATE_PATIENT_LIFE_STATUS")
        self.assertEqual(start.call_args.kwargs["previous_state"]["alive"], True)
        self.assertEqual(start.call_args.kwargs["new_state"]["alive"], False)
        self.assertEqual(start.call_args.kwargs["new_state"]["deathDate"], "2026-09-01")
        finish.assert_called_once()
        self.assertEqual(finish.call_args.kwargs["outcome"], "success")
        self.assertFalse(result["alive"])
        self.assertEqual(result["deathDate"], "2026-09-01")
        self.assertEqual(result["uuid"], "pat-1")

    def test_restoring_alive_clears_death_date_and_audits(self) -> None:
        restored = {**ALIVE_RECORD}
        with (
            patch.object(administration, "require_hospital_admin", return_value=HOSPITAL_ADMIN),
            patch.object(register, "load_patient_record", side_effect=[DECEASED_RECORD, restored]),
            patch.object(life, "_write_person_life_status") as write,
            patch.object(life.admin_audit, "start_admin_event", return_value="evt-2") as start,
            patch.object(life.admin_audit, "finish_admin_event") as finish,
            patch.object(life.periods, "hospital_today", return_value=date(2026, 9, 7)),
        ):
            result = life.update_life_status(
                "pat-1",
                {"alive": True, "requestId": "req-restore"},
                "cookie",
            )
        write.assert_called_once_with("pat-1", alive=True, death_day=None)
        self.assertTrue(start.call_args.kwargs["previous_state"]["alive"] is False)
        self.assertTrue(start.call_args.kwargs["new_state"]["alive"] is True)
        finish.assert_called_once()
        self.assertTrue(result["alive"])
        self.assertEqual(result["deathDate"], "")

    def test_deceased_without_death_date_is_rejected(self) -> None:
        with (
            patch.object(administration, "require_hospital_admin", return_value=HOSPITAL_ADMIN),
            patch.object(register, "load_patient_record", return_value=ALIVE_RECORD),
            patch.object(life.periods, "hospital_today", return_value=date(2026, 9, 7)),
            self.assertRaises(ApiError) as raised,
        ):
            life.update_life_status("pat-1", {"alive": False, "requestId": "req-missing"}, "cookie")
        self.assertEqual(raised.exception.code, "death_date_required")

    def test_request_id_required(self) -> None:
        with (
            patch.object(administration, "require_hospital_admin", return_value=HOSPITAL_ADMIN),
            self.assertRaises(ApiError) as raised,
        ):
            life.update_life_status("pat-1", {"alive": True}, "cookie")
        self.assertEqual(raised.exception.code, "request_id_required")


if __name__ == "__main__":
    unittest.main()
