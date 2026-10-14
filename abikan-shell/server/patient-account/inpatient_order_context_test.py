"""Active admission is the inpatient order visit. No visit is invented."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import inpatient
from server import ApiError


PATIENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
IPD_VISIT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
OPD_VISIT = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ADMISSION = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
OTHER_ENCOUNTER = "ffffffff-ffff-4fff-8fff-ffffffffffff"


def admission(
    *,
    patient: str = PATIENT_A,
    visit: str = IPD_VISIT,
    stopped: str | None = None,
) -> dict[str, object]:
    return {
        "uuid": ADMISSION,
        "encounterDatetime": "2026-08-26T13:29:00.000+0000",
        "patient": {"uuid": patient},
        "location": {"uuid": "ward-location", "name": "Ward"},
        "visit": {
            "uuid": visit,
            "startDatetime": "2026-08-26T13:00:00.000+0000",
            "stopDatetime": stopped,
            "visitType": {"uuid": inpatient.IPD_VISIT_TYPE, "name": "IPD"},
        },
    }


class InpatientOrderContextTests(unittest.TestCase):
    def test_occupied_admission_exposes_existing_ipd_visit_on_stay(self) -> None:
        stay_patient = {
            "uuid": PATIENT_A,
            "name": "Fatima",
            "mrn": "ABC1",
            "sex": "F",
            "age": "30",
        }
        with (
            patch.object(inpatient, "require_inpatient_view", return_value={"uuid": "doc"}),
            patch.object(inpatient, "_patient_brief", return_value=stay_patient),
            patch.object(
                inpatient,
                "current_assignment",
                return_value={"areaName": "Ward", "bedNumber": "02", "bedUuid": "bed-1"},
            ),
            patch.object(inpatient, "_admission_datetime", return_value="2026-08-26T13:29:00.000+0000"),
            patch.object(inpatient, "_open_ipd_admission", return_value=admission()),
            patch.object(inpatient, "_active_admission", return_value=admission()),
        ):
            stay = inpatient.build_patient_stay(PATIENT_A, "JSESSIONID=doc", catch_up_billing=False)

        self.assertEqual(stay["visitUuid"], IPD_VISIT)
        self.assertEqual(stay["admissionEncounterUuid"], ADMISSION)
        self.assertEqual(stay["visitStartDatetime"], "2026-08-26T13:00:00.000+0000")
        self.assertEqual(stay["patient"]["uuid"], PATIENT_A)

    def test_resolve_uses_active_ipd_visit_instead_of_creating_or_requesting_one(self) -> None:
        with patch.object(inpatient, "inpatient_order_context", return_value={"visitUuid": IPD_VISIT}):
            resolved = inpatient.resolve_clinical_order_visit_uuid(
                PATIENT_A,
                "",
                "JSESSIONID=doc",
                missing_visit_message="Start an open visit before ordering laboratory tests.",
            )
            closed_opd = inpatient.resolve_clinical_order_visit_uuid(
                PATIENT_A,
                OPD_VISIT,
                "JSESSIONID=doc",
                missing_visit_message="Start an open visit before ordering laboratory tests.",
            )
        self.assertEqual(resolved, IPD_VISIT)
        self.assertEqual(closed_opd, IPD_VISIT)
        self.assertNotEqual(resolved, OPD_VISIT)

    def test_outpatient_still_requires_the_requested_open_visit(self) -> None:
        with (
            patch.object(inpatient, "inpatient_order_context", return_value=None),
            patch.object(inpatient, "_admission_awaiting_bed", return_value=False),
        ):
            with self.assertRaises(ApiError) as missing:
                inpatient.resolve_clinical_order_visit_uuid(
                    PATIENT_A,
                    "",
                    "JSESSIONID=doc",
                    missing_visit_message="Start an open visit before ordering laboratory tests.",
                )
            resolved = inpatient.resolve_clinical_order_visit_uuid(
                PATIENT_A,
                OPD_VISIT,
                "JSESSIONID=doc",
                missing_visit_message="Start an open visit before ordering laboratory tests.",
            )
        self.assertEqual(missing.exception.code, "visit_required")
        self.assertEqual(resolved, OPD_VISIT)

    def test_awaiting_bed_blocks_orders_without_inventing_an_opd_visit(self) -> None:
        with (
            patch.object(inpatient, "inpatient_order_context", return_value=None),
            patch.object(inpatient, "_admission_awaiting_bed", return_value=True),
            self.assertRaises(ApiError) as caught,
        ):
            inpatient.resolve_clinical_order_visit_uuid(
                PATIENT_A,
                IPD_VISIT,
                "JSESSIONID=doc",
                missing_visit_message="Start an open visit before ordering laboratory tests.",
            )
        self.assertEqual(caught.exception.code, "awaiting_bed")
        self.assertEqual(caught.exception.status, 409)

    def test_patient_b_encounter_is_not_kept_on_patient_a_visit(self) -> None:
        visit = {
            "uuid": IPD_VISIT,
            "patient": {"uuid": PATIENT_A},
            "encounters": [{"uuid": ADMISSION}, {"uuid": "consult-a"}],
        }
        self.assertEqual(
            inpatient.encounter_on_resolved_visit(visit, "consult-a"),
            "consult-a",
        )
        self.assertEqual(inpatient.encounter_on_resolved_visit(visit, OTHER_ENCOUNTER), "")
        self.assertEqual(inpatient.encounter_on_resolved_visit(visit, ""), "")

    def test_order_context_rejects_another_patient_admission(self) -> None:
        with patch.object(inpatient, "_active_admission", return_value=admission(patient=PATIENT_B)):
            self.assertIsNone(inpatient.inpatient_order_context(PATIENT_A, "JSESSIONID=doc"))
