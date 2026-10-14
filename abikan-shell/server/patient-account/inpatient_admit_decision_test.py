"""Doctor admission does not require an OPD visit. IPD stays OpenMRS-owned."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import inpatient
import registration as reception
import registration_patient as arrival
from server import ApiError


PATIENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OPD_VISIT = "11111111-1111-4111-8111-111111111111"
IPD_VISIT = "22222222-2222-4222-8222-222222222222"
ADMISSION = "33333333-3333-4333-8333-333333333333"
LOCATION = "opd-1-uuid"
BED = "bed-01-uuid"


def doctor() -> dict[str, object]:
    return {"uuid": "doc-user", "privileges": ["app:clinical"], "roles": ["Abikan:Doctor"]}


def stay_patient() -> dict[str, str]:
    return {
        "uuid": PATIENT_A,
        "name": "Fatima",
        "mrn": "ABC1",
        "sex": "F",
        "age": "30",
    }


def ipd_admission(*, patient: str = PATIENT_A) -> dict[str, object]:
    return {
        "uuid": ADMISSION,
        "encounterDatetime": "2026-09-03T01:00:00.000+0000",
        "patient": {"uuid": patient},
        "location": {"uuid": LOCATION, "name": "OPD-1"},
        "visit": {
            "uuid": IPD_VISIT,
            "startDatetime": "2026-09-03T01:00:00.000+0000",
            "stopDatetime": None,
            "visitType": {"uuid": inpatient.IPD_VISIT_TYPE, "name": "IPD"},
        },
    }


def created_stay(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "status": "ok",
        "patient": stay_patient(),
        "assignment": None,
        "awaiting": True,
        "visitUuid": IPD_VISIT,
        "visitStartDatetime": "2026-09-03T01:00:00.000+0000",
        "admissionEncounterUuid": ADMISSION,
    }
    row.update(overrides)
    return row


class AdmitWithoutOpdVisitTests(unittest.TestCase):
    def test_doctor_admits_without_an_open_opd_visit(self) -> None:
        ended: list[str] = []
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor()),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient()),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=None),
            patch.object(inpatient, "_admit_location_uuid", return_value=LOCATION),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_create_ipd_visit", return_value=IPD_VISIT) as create_visit,
            patch.object(
                inpatient,
                "_create_admission_encounter_on_visit",
                return_value=ADMISSION,
            ) as create_admission,
            patch.object(inpatient, "_create_adt_encounter") as bahmni_adt,
            patch.object(inpatient, "_end_open_non_ipd_visits", side_effect=lambda patient, cookie: ended.append(patient)),
            patch.object(inpatient, "build_patient_stay", return_value=created_stay()),
        ):
            result = inpatient.create_admit_decision(PATIENT_A, {"locationUuid": LOCATION}, "JSESSIONID=doc")

        self.assertEqual(result["visitUuid"], IPD_VISIT)
        self.assertEqual(result["admissionEncounterUuid"], ADMISSION)
        self.assertEqual(result["awaiting"], True)
        self.assertIsNone(result["assignment"])
        create_visit.assert_called_once_with(PATIENT_A, LOCATION, "JSESSIONID=doc")
        self.assertEqual(create_admission.call_args.kwargs["visit_uuid"], IPD_VISIT)
        self.assertEqual(create_admission.call_args.kwargs["patient_uuid"], PATIENT_A)
        bahmni_adt.assert_not_called()
        self.assertEqual(ended, [PATIENT_A])
        self.assertEqual(result["patient"]["uuid"], PATIENT_A)

    def test_does_not_create_an_artificial_opd_visit(self) -> None:
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor()),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient()),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=None),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_create_ipd_visit", return_value=IPD_VISIT) as create_visit,
            patch.object(inpatient, "_create_admission_encounter_on_visit", return_value=ADMISSION),
            patch.object(inpatient, "_create_adt_encounter") as bahmni_adt,
            patch.object(inpatient, "_end_open_non_ipd_visits"),
            patch.object(inpatient, "build_patient_stay", return_value=created_stay()),
        ):
            inpatient.create_admit_decision(PATIENT_A, {"locationUuid": LOCATION}, "JSESSIONID=doc")

        create_visit.assert_called_once()
        bahmni_adt.assert_not_called()
        self.assertEqual(create_visit.call_args.args[0], PATIENT_A)
        source = Path(inpatient.__file__).read_text(encoding="utf-8")
        self.assertIn('visitType": IPD_VISIT_TYPE', source)
        self.assertNotIn("54f43754-c6ce-4472-890e-0f28acaeaea6", source.split("def create_admit_decision", 1)[1])

    def test_open_opd_visit_is_ended_and_one_ipd_is_created(self) -> None:
        ended: list[str] = []
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor()),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient()),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=None),
            patch.object(
                inpatient,
                "_validate_optional_admit_visit",
                return_value={
                    "uuid": OPD_VISIT,
                    "stopDatetime": None,
                    "patient": {"uuid": PATIENT_A},
                    "visitType": {"name": "OPD"},
                },
            ),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_create_ipd_visit", return_value=IPD_VISIT),
            patch.object(inpatient, "_create_admission_encounter_on_visit", return_value=ADMISSION),
            patch.object(
                inpatient,
                "_end_open_non_ipd_visits",
                side_effect=lambda patient, cookie: ended.append(patient),
            ),
            patch.object(inpatient, "build_patient_stay", return_value=created_stay()),
        ):
            result = inpatient.create_admit_decision(
                PATIENT_A,
                {"visitUuid": OPD_VISIT, "locationUuid": LOCATION},
                "JSESSIONID=doc",
            )

        self.assertEqual(ended, [PATIENT_A])
        self.assertEqual(result["visitUuid"], IPD_VISIT)
        self.assertNotEqual(result["visitUuid"], OPD_VISIT)

    def test_does_not_use_another_patients_visit(self) -> None:
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor()),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient()),
            patch.object(
                inpatient,
                "openmrs_call",
                return_value={"uuid": OPD_VISIT, "patient": {"uuid": PATIENT_B}, "visitType": {"name": "OPD"}},
            ),
            patch.object(inpatient, "_create_ipd_visit") as create,
            self.assertRaises(ApiError) as caught,
        ):
            inpatient.create_admit_decision(
                PATIENT_A,
                {"visitUuid": OPD_VISIT, "locationUuid": LOCATION},
                "JSESSIONID=doc",
            )
        self.assertEqual(caught.exception.code, "wrong_patient")
        create.assert_not_called()

    def test_reception_cannot_admit(self) -> None:
        with (
            patch.object(
                inpatient,
                "require_clinical_user",
                side_effect=ApiError(403, "forbidden", "This action requires the doctor workspace."),
            ),
            patch.object(inpatient, "_create_ipd_visit") as create,
            self.assertRaises(ApiError) as caught,
        ):
            inpatient.create_admit_decision(PATIENT_A, {"locationUuid": LOCATION}, "JSESSIONID=rec")
        self.assertEqual(caught.exception.status, 403)
        create.assert_not_called()

    def test_already_admitted_patient_is_rejected(self) -> None:
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor()),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient()),
            patch.object(inpatient, "current_assignment", return_value={"bedNumber": "02"}),
            patch.object(inpatient, "_create_ipd_visit") as create,
            self.assertRaises(ApiError) as caught,
        ):
            inpatient.create_admit_decision(PATIENT_A, {"locationUuid": LOCATION}, "JSESSIONID=doc")
        self.assertEqual(caught.exception.code, "already_admitted")
        create.assert_not_called()


class AwaitingBedAndAssignTests(unittest.TestCase):
    def test_stay_exposes_ipd_admission_before_a_bed_is_assigned(self) -> None:
        with (
            patch.object(inpatient, "require_inpatient_view", return_value=doctor()),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient()),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=ipd_admission()),
            patch.object(inpatient, "_disposition_awaiting", return_value=False),
        ):
            stay = inpatient.build_patient_stay(PATIENT_A, "JSESSIONID=doc", catch_up_billing=False)

        self.assertEqual(stay["awaiting"], True)
        self.assertIsNone(stay["assignment"])
        self.assertEqual(stay["visitUuid"], IPD_VISIT)
        self.assertEqual(stay["admissionEncounterUuid"], ADMISSION)
        self.assertEqual(stay["patient"]["uuid"], PATIENT_A)

    def test_assign_bed_reuses_existing_admission_and_does_not_create_another_ipd(self) -> None:
        with (
            patch.object(inpatient, "require_assign_user", return_value={"uuid": "nurse", "roles": []}),
            patch.object(inpatient, "_require_active_patient"),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(
                inpatient,
                "_find_bed",
                return_value={
                    "bedUuid": BED,
                    "bedId": 12,
                    "bedNumber": "12",
                    "areaUuid": "ward-1",
                    "areaName": "Male Ward",
                    "status": "AVAILABLE",
                },
            ),
            patch.object(inpatient, "_end_open_non_ipd_visits"),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_assert_bed_available"),
            patch.object(inpatient, "_open_ipd_admission", return_value=ipd_admission()),
            patch.object(inpatient, "_open_ipd_visit", return_value={"uuid": IPD_VISIT, "visitType": {"name": "IPD"}}),
            patch.object(inpatient, "_create_adt_encounter") as create,
            patch.object(inpatient, "_assign_bed") as assign,
            patch.object(
                inpatient,
                "build_patient_stay",
                return_value=created_stay(
                    awaiting=False,
                    assignment={"areaName": "Male Ward", "bedNumber": "12", "status": "OCCUPIED"},
                ),
            ),
            patch.object(inpatient, "_attach_billing", side_effect=lambda stay, callback: stay),
        ):
            result = inpatient.assign_bed(
                {"patientUuid": PATIENT_A, "bedUuid": BED, "requestId": "assign-1"},
                "JSESSIONID=nurse",
            )

        create.assert_not_called()
        assign.assert_called_once()
        self.assertEqual(assign.call_args.args[0], 12)
        self.assertEqual(assign.call_args.args[1], PATIENT_A)
        self.assertEqual(assign.call_args.args[2], ADMISSION)
        self.assertEqual(result["visitUuid"], IPD_VISIT)

    def test_end_open_non_ipd_visits_never_closes_ipd(self) -> None:
        ended: list[str] = []
        with (
            patch.object(
                inpatient,
                "_open_visits",
                return_value=[
                    {"uuid": OPD_VISIT, "visitType": {"name": "OPD"}},
                    {"uuid": IPD_VISIT, "visitType": {"uuid": inpatient.IPD_VISIT_TYPE, "name": "IPD"}},
                ],
            ),
            patch.object(inpatient, "_end_visit", side_effect=lambda visit_uuid, cookie: ended.append(visit_uuid)),
        ):
            inpatient._end_open_non_ipd_visits(PATIENT_A, "JSESSIONID=doc")
        self.assertEqual(ended, [OPD_VISIT])
        self.assertNotIn(IPD_VISIT, ended)


class ReceptionRegressionAfterAdmitTests(unittest.TestCase):
    def test_create_visit_context_still_has_no_card_fields(self) -> None:
        source = Path(arrival.__file__).read_text(encoding="utf-8")
        self.assertIn("No card fee. No Odoo.", source)
        self.assertNotIn("canCreateCharge", source.split("def build_visit_context", 1)[1].split("def start_visit", 1)[0])

    def test_open_ipd_from_admit_blocks_duplicate_create_visit(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(
                reception,
                "latest_open_visit",
                return_value={
                    "uuid": IPD_VISIT,
                    "visitType": "IPD",
                    "open": True,
                    "startDatetime": "2026-09-03T01:00:00.000+0000",
                },
            ),
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": "opd-type"}, "JSESSIONID=rec")
        self.assertEqual(result["created"], False)
        self.assertEqual(result["code"], reception.ADMISSION_IN_PROGRESS_CODE)
        self.assertEqual(result["uuid"], IPD_VISIT)


if __name__ == "__main__":
    unittest.main()
