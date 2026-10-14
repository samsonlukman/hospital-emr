"""Cancel an admission that is still waiting for a bed. Occupied beds stay put."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import inpatient
from server import ApiError


PATIENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
IPD_VISIT = "22222222-2222-4222-8222-222222222222"
ADMISSION = "33333333-3333-4333-8333-333333333333"


def nurse() -> dict[str, str]:
    return {"uuid": "nurse-1", "username": "nurse.ada"}


def brief() -> dict[str, str]:
    return {"uuid": PATIENT, "name": "Ada Bello", "mrn": "ABC1", "sex": "F", "age": "30"}


def admission() -> dict[str, object]:
    return {
        "uuid": ADMISSION,
        "patient": {"uuid": PATIENT},
        "visit": {
            "uuid": IPD_VISIT,
            "stopDatetime": None,
            "visitType": {"uuid": inpatient.IPD_VISIT_TYPE, "name": "IPD"},
        },
    }


def open_ipd() -> dict[str, object]:
    return {
        "uuid": IPD_VISIT,
        "stopDatetime": None,
        "visitType": {"name": "IPD"},
    }


class CancelWaitingAdmissionTests(unittest.TestCase):
    def test_occupied_bed_is_not_canceled(self) -> None:
        with (
            patch.object(inpatient, "require_assign_user", return_value=nurse()),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value={"bedNumber": "4"}),
            patch.object(inpatient, "_end_visit") as end_visit,
            patch.object(inpatient, "_void_openmrs_record") as void,
        ):
            with self.assertRaises(ApiError) as caught:
                inpatient.cancel_waiting_admission({"patientUuid": PATIENT}, "cookie")
        self.assertEqual(caught.exception.code, "already_admitted")
        end_visit.assert_not_called()
        void.assert_not_called()

    def test_waiting_ipd_visit_is_closed_and_the_patient_leaves_the_list(self) -> None:
        state = {"open": True}
        ended: list[str] = []

        def end_visit(visit_uuid: str, cookie: str) -> None:
            self.assertEqual(cookie, "cookie")
            ended.append(visit_uuid)
            state["open"] = False

        with (
            patch.object(inpatient, "require_assign_user", return_value=nurse()),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", side_effect=lambda *_: admission() if state["open"] else None),
            patch.object(inpatient, "_open_ipd_visit", side_effect=lambda *_: open_ipd() if state["open"] else None),
            patch.object(inpatient, "_disposition_awaiting", return_value=False),
            patch.object(inpatient, "_patient_awaiting", return_value=False),
            patch.object(inpatient, "_awaiting_patients", return_value=[]),
            patch.object(inpatient, "_end_visit", side_effect=end_visit),
            patch.object(inpatient, "_void_openmrs_record") as void,
            patch.object(inpatient, "_void_open_admit_dispositions"),
            patch.object(inpatient, "_safe_patient_brief", return_value=brief()),
            patch.object(inpatient, "_end_open_non_ipd_visits") as end_opd,
        ):
            import notifications as staff_notes

            with patch.object(staff_notes, "expire_patient_event") as expire:
                result = inpatient.cancel_waiting_admission({"patientUuid": PATIENT}, "cookie")
        self.assertEqual(ended, [IPD_VISIT])
        void.assert_called_once()
        self.assertIn(ADMISSION, void.call_args.args[0])
        end_opd.assert_not_called()
        expire.assert_called_once_with(PATIENT, "admit_requested")
        self.assertFalse(result["awaiting"])
        self.assertIsNone(result["assignment"])
        self.assertIn("Reception can start a new visit", result["message"])

    def test_admit_decision_on_an_open_outpatient_visit_is_cleared_without_closing_it(self) -> None:
        flags = {"admit": True}

        def disposition(*_args: object) -> bool:
            return flags["admit"]

        def clear(*_args: object) -> None:
            flags["admit"] = False

        with (
            patch.object(inpatient, "require_assign_user", return_value=nurse()),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=None),
            patch.object(inpatient, "_open_ipd_visit", return_value=None),
            patch.object(inpatient, "_disposition_awaiting", side_effect=disposition),
            patch.object(inpatient, "_patient_awaiting", side_effect=disposition),
            patch.object(inpatient, "_awaiting_patients", return_value=[]),
            patch.object(inpatient, "_end_visit") as end_visit,
            patch.object(inpatient, "_void_open_admit_dispositions", side_effect=clear),
            patch.object(inpatient, "_safe_patient_brief", return_value=brief()),
        ):
            result = inpatient.cancel_waiting_admission({"patientUuid": PATIENT}, "cookie")
        end_visit.assert_not_called()
        self.assertFalse(result["awaiting"])
        self.assertNotIn("Reception can start a new visit", result["message"])

    def test_patient_who_is_not_waiting_is_left_alone(self) -> None:
        with (
            patch.object(inpatient, "require_assign_user", return_value=nurse()),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=None),
            patch.object(inpatient, "_open_ipd_visit", return_value=None),
            patch.object(inpatient, "_disposition_awaiting", return_value=False),
            patch.object(inpatient, "_awaiting_patients", return_value=[]),
            patch.object(inpatient, "_end_visit") as end_visit,
        ):
            with self.assertRaises(ApiError) as caught:
                inpatient.cancel_waiting_admission({"patientUuid": PATIENT}, "cookie")
        self.assertEqual(caught.exception.code, "not_waiting")
        end_visit.assert_not_called()

    def test_visit_that_stays_open_is_not_reported_as_canceled(self) -> None:
        with (
            patch.object(inpatient, "require_assign_user", return_value=nurse()),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=admission()),
            patch.object(inpatient, "_open_ipd_visit", return_value=open_ipd()),
            patch.object(inpatient, "_disposition_awaiting", return_value=False),
            patch.object(inpatient, "_end_visit"),
            patch.object(inpatient, "_void_openmrs_record") as void,
        ):
            with self.assertRaises(ApiError) as caught:
                inpatient.cancel_waiting_admission({"patientUuid": PATIENT}, "cookie")
        self.assertEqual(caught.exception.code, "cancel_incomplete")
        void.assert_not_called()

    def test_a_missed_alert_does_not_undo_the_cancel(self) -> None:
        state = {"open": True}

        def end_visit(*_args: object) -> None:
            state["open"] = False

        with (
            patch.object(inpatient, "require_assign_user", return_value=nurse()),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", side_effect=lambda *_: admission() if state["open"] else None),
            patch.object(inpatient, "_open_ipd_visit", side_effect=lambda *_: open_ipd() if state["open"] else None),
            patch.object(inpatient, "_disposition_awaiting", return_value=False),
            patch.object(inpatient, "_patient_awaiting", return_value=False),
            patch.object(inpatient, "_awaiting_patients", return_value=[]),
            patch.object(inpatient, "_end_visit", side_effect=end_visit),
            patch.object(inpatient, "_void_openmrs_record"),
            patch.object(inpatient, "_void_open_admit_dispositions"),
            patch.object(inpatient, "_safe_patient_brief", return_value=brief()),
        ):
            import notifications as staff_notes

            with patch.object(staff_notes, "expire_patient_event", side_effect=RuntimeError("alert store")):
                result = inpatient.cancel_waiting_admission({"patientUuid": PATIENT}, "cookie")
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["awaiting"])
