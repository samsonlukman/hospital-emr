"""Admitted patients order on the existing IPD visit. Outpatient visit rules stay."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import laboratory
import radiology
from server import ApiError


PATIENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
IPD_VISIT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
OPD_VISIT = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
CONSULT = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
OTHER_ENCOUNTER = "ffffffff-ffff-4fff-8fff-ffffffffffff"


def ipd_visit(*, patient: str = PATIENT_A, closed: bool = False) -> dict[str, object]:
    return {
        "uuid": IPD_VISIT,
        "startDatetime": "2026-08-26T13:00:00.000+0000",
        "stopDatetime": "2026-08-27T10:00:00.000+0000" if closed else None,
        "visitType": {"name": "IPD", "uuid": "ipd-type"},
        "patient": {"uuid": patient},
        "encounters": [
            {
                "uuid": CONSULT,
                "encounterDatetime": "2026-08-26T14:00:00.000+0000",
                "encounterType": {"name": "Consultation", "uuid": laboratory.CONSULTATION_ENCOUNTER_TYPE},
            }
        ],
    }


def opd_visit(*, patient: str = PATIENT_A) -> dict[str, object]:
    return {
        "uuid": OPD_VISIT,
        "startDatetime": "2026-08-26T08:00:00.000+0000",
        "stopDatetime": None,
        "visitType": {"name": "OPD", "uuid": "opd-type"},
        "patient": {"uuid": patient},
        "encounters": [
            {
                "uuid": "consult-opd",
                "encounterDatetime": "2026-08-26T08:10:00.000+0000",
                "encounterType": {"name": "Consultation", "uuid": laboratory.CONSULTATION_ENCOUNTER_TYPE},
            }
        ],
    }


class InpatientLaboratoryOrderTests(unittest.TestCase):
    def _create(self, body: dict[str, object], *, visit: dict[str, object], existing=None, created=None):
        posts: list[tuple[str, dict[str, object]]] = []
        listed = {"n": 0}
        existing = existing or []
        created = created or [
            {
                "uuid": "lab-1",
                "conceptUuid": "concept-mp",
                "encounterUuid": CONSULT,
                "visitUuid": visit["uuid"],
            }
        ]

        def list_orders(patient_uuid: str, cookie: str):
            listed["n"] += 1
            return existing if listed["n"] == 1 else existing + created

        def post(path: str, cookie: str, payload: dict[str, object]):
            posts.append((path, payload))
            return {"encounterUuid": CONSULT}

        with (
            patch.object(laboratory, "require_clinical_user", return_value={"uuid": "doc-user"}),
            patch.object(
                laboratory.ward,
                "inpatient_order_context",
                return_value={"visitUuid": IPD_VISIT} if visit["uuid"] == IPD_VISIT else None,
            ),
            patch.object(laboratory, "_openmrs_json", return_value=visit),
            patch.object(laboratory, "list_lab_orders", side_effect=list_orders),
            patch.object(
                laboratory.lab_catalogue,
                "entry_by_concept",
                return_value={
                    "orderable": True,
                    "hospitalName": "Malaria parasite",
                    "openmrsName": "Malaria parasite",
                    "outsourced": False,
                    "notStat": False,
                },
            ),
            patch.object(laboratory, "_provider_uuid", return_value="provider-1"),
            patch.object(laboratory, "_openmrs_post", side_effect=post),
            patch.object(
                laboratory,
                "create_laboratory_charge",
                return_value={"status": "ok", "message": "Laboratory fee created."},
            ) as charge,
        ):
            result = laboratory.create_lab_orders(PATIENT_A, body, "JSESSIONID=doc")
        return result, posts, charge

    def test_admitted_patient_orders_lab_on_existing_ipd_encounter_without_a_new_visit(self) -> None:
        result, posts, charge = self._create(
            {
                "visitUuid": "",
                "locationUuid": "ward",
                "encounterUuid": "",
                "tests": [{"conceptUuid": "concept-mp"}],
                "requestId": "lab-req-1",
            },
            visit=ipd_visit(),
        )
        path, payload = posts[0]
        self.assertEqual(path, "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter")
        self.assertEqual(payload["visitUuid"], IPD_VISIT)
        self.assertEqual(payload["visitType"], "IPD")
        self.assertEqual(payload["encounterUuid"], CONSULT)
        self.assertEqual(payload["patientUuid"], PATIENT_A)
        self.assertEqual(result["orders"][0]["visitUuid"], IPD_VISIT)
        self.assertEqual(result["orders"][0]["encounterUuid"], CONSULT)
        charge.assert_called_once()
        self.assertEqual(result["charge"]["status"], "ok")

    def test_closed_opd_visit_is_replaced_by_the_active_ipd_visit(self) -> None:
        _, posts, _ = self._create(
            {
                "visitUuid": OPD_VISIT,
                "locationUuid": "opd-1",
                "encounterUuid": "consult-opd",
                "tests": [{"conceptUuid": "concept-mp"}],
            },
            visit=ipd_visit(),
        )
        self.assertEqual(posts[0][1]["visitUuid"], IPD_VISIT)
        self.assertEqual(posts[0][1]["encounterUuid"], CONSULT)
        self.assertNotEqual(posts[0][1]["encounterUuid"], "consult-opd")

    def test_another_patient_encounter_cannot_be_used(self) -> None:
        _, posts, _ = self._create(
            {
                "visitUuid": IPD_VISIT,
                "locationUuid": "ward",
                "encounterUuid": OTHER_ENCOUNTER,
                "tests": [{"conceptUuid": "concept-mp"}],
            },
            visit=ipd_visit(),
        )
        self.assertEqual(posts[0][1]["encounterUuid"], CONSULT)
        self.assertNotEqual(posts[0][1]["encounterUuid"], OTHER_ENCOUNTER)

    def test_repeated_same_test_on_the_same_encounter_is_rejected(self) -> None:
        with self.assertRaises(ApiError) as caught:
            self._create(
                {
                    "visitUuid": IPD_VISIT,
                    "locationUuid": "ward",
                    "encounterUuid": CONSULT,
                    "tests": [{"conceptUuid": "concept-mp"}],
                },
                visit=ipd_visit(),
                existing=[
                    {
                        "uuid": "lab-existing",
                        "conceptUuid": "concept-mp",
                        "encounterUuid": CONSULT,
                        "visitUuid": IPD_VISIT,
                    }
                ],
            )
        self.assertEqual(caught.exception.code, "duplicate_lab_test")

    def test_non_doctor_is_rejected(self) -> None:
        with (
            patch.object(
                laboratory,
                "require_clinical_user",
                side_effect=ApiError(403, "forbidden", "This action requires the Clinical workspace."),
            ),
            self.assertRaises(ApiError) as caught,
        ):
            laboratory.create_lab_orders(
                PATIENT_A,
                {"visitUuid": IPD_VISIT, "locationUuid": "ward", "tests": [{"conceptUuid": "concept-mp"}]},
                "JSESSIONID=nurse",
            )
        self.assertEqual(caught.exception.status, 403)

    def test_outpatient_still_requires_an_open_visit(self) -> None:
        with (
            patch.object(laboratory, "require_clinical_user", return_value={"uuid": "doc-user"}),
            patch.object(laboratory.ward, "inpatient_order_context", return_value=None),
            patch.object(laboratory.ward, "_admission_awaiting_bed", return_value=False),
            self.assertRaises(ApiError) as caught,
        ):
            laboratory.create_lab_orders(
                PATIENT_A,
                {"visitUuid": "", "locationUuid": "opd-1", "tests": [{"conceptUuid": "concept-mp"}]},
                "JSESSIONID=doc",
            )
        self.assertEqual(caught.exception.code, "visit_required")

    def test_outpatient_open_visit_still_orders_on_that_visit(self) -> None:
        posts: list[dict[str, object]] = []

        def list_orders(patient_uuid: str, cookie: str):
            if not posts:
                return []
            return [
                {
                    "uuid": "lab-opd",
                    "conceptUuid": "concept-mp",
                    "encounterUuid": "consult-opd",
                    "visitUuid": OPD_VISIT,
                }
            ]

        with (
            patch.object(laboratory, "require_clinical_user", return_value={"uuid": "doc-user"}),
            patch.object(laboratory.ward, "inpatient_order_context", return_value=None),
            patch.object(laboratory.ward, "_admission_awaiting_bed", return_value=False),
            patch.object(laboratory, "_openmrs_json", return_value=opd_visit()),
            patch.object(laboratory, "list_lab_orders", side_effect=list_orders),
            patch.object(
                laboratory.lab_catalogue,
                "entry_by_concept",
                return_value={
                    "orderable": True,
                    "hospitalName": "Malaria parasite",
                    "openmrsName": "Malaria parasite",
                    "outsourced": False,
                    "notStat": False,
                },
            ),
            patch.object(laboratory, "_provider_uuid", return_value="provider-1"),
            patch.object(
                laboratory,
                "_openmrs_post",
                side_effect=lambda path, cookie, payload: posts.append(payload) or {"encounterUuid": "consult-opd"},
            ),
            patch.object(laboratory, "create_laboratory_charge", return_value={"status": "ok"}),
        ):
            result = laboratory.create_lab_orders(
                PATIENT_A,
                {
                    "visitUuid": OPD_VISIT,
                    "locationUuid": "opd-1",
                    "tests": [{"conceptUuid": "concept-mp"}],
                },
                "JSESSIONID=doc",
            )
        self.assertEqual(posts[0]["visitUuid"], OPD_VISIT)
        self.assertEqual(posts[0]["visitType"], "OPD")
        self.assertEqual(result["orders"][0]["visitUuid"], OPD_VISIT)

    def test_wrong_patient_visit_is_rejected(self) -> None:
        with (
            patch.object(laboratory, "require_clinical_user", return_value={"uuid": "doc-user"}),
            patch.object(laboratory.ward, "inpatient_order_context", return_value=None),
            patch.object(laboratory.ward, "_admission_awaiting_bed", return_value=False),
            patch.object(laboratory, "_openmrs_json", return_value=opd_visit(patient=PATIENT_B)),
            self.assertRaises(ApiError) as caught,
        ):
            laboratory.create_lab_orders(
                PATIENT_A,
                {
                    "visitUuid": OPD_VISIT,
                    "locationUuid": "opd-1",
                    "tests": [{"conceptUuid": "concept-mp"}],
                },
                "JSESSIONID=doc",
            )
        self.assertEqual(caught.exception.code, "wrong_patient")


class InpatientRadiologyOrderTests(unittest.TestCase):
    def test_admitted_patient_orders_imaging_on_existing_ipd_encounter(self) -> None:
        posts: list[tuple[str, dict[str, object]]] = []
        listed = {"n": 0}
        created = {
            "uuid": "rad-1",
            "conceptUuid": "rad-concept",
            "encounterUuid": CONSULT,
            "visitUuid": IPD_VISIT,
        }

        def list_orders(patient_uuid: str, cookie: str):
            listed["n"] += 1
            return [] if listed["n"] == 1 else [created]

        with (
            patch.object(radiology, "require_clinical_user", return_value={"uuid": "doc-user"}),
            patch.object(radiology.ward, "inpatient_order_context", return_value={"visitUuid": IPD_VISIT}),
            patch.object(radiology, "_openmrs_json", return_value=ipd_visit()),
            patch.object(radiology, "list_radiology_orders", side_effect=list_orders),
            patch.object(radiology.radiology_menu, "entry_by_id", return_value={"id": "cxr"}),
            patch.object(
                radiology.radiology_menu,
                "resolve_orderable",
                return_value={
                    "conceptUuid": "rad-concept",
                    "conceptName": "Chest X-ray",
                    "hospitalName": "Chest X-ray",
                },
            ),
            patch.object(radiology, "_provider_uuid", return_value="provider-1"),
            patch.object(
                radiology,
                "_openmrs_post",
                side_effect=lambda path, cookie, payload: posts.append((path, payload))
                or {"encounterUuid": CONSULT},
            ),
        ):
            result = radiology.create_radiology_orders(
                PATIENT_A,
                {
                    "visitUuid": "",
                    "locationUuid": "ward",
                    "services": [{"serviceId": "cxr", "conceptUuid": "rad-concept"}],
                },
                "JSESSIONID=doc",
            )
        self.assertEqual(posts[0][0], "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter")
        self.assertEqual(posts[0][1]["visitUuid"], IPD_VISIT)
        self.assertEqual(posts[0][1]["visitType"], "IPD")
        self.assertEqual(posts[0][1]["encounterUuid"], CONSULT)
        self.assertEqual(result["visitUuid"], IPD_VISIT)
        self.assertEqual(result["orders"][0]["uuid"], "rad-1")

    def test_outpatient_imaging_still_requires_an_open_visit(self) -> None:
        with (
            patch.object(radiology, "require_clinical_user", return_value={"uuid": "doc-user"}),
            patch.object(radiology.ward, "inpatient_order_context", return_value=None),
            patch.object(radiology.ward, "_admission_awaiting_bed", return_value=False),
            self.assertRaises(ApiError) as caught,
        ):
            radiology.create_radiology_orders(
                PATIENT_A,
                {"visitUuid": "", "locationUuid": "opd-1", "services": [{"serviceId": "cxr"}]},
                "JSESSIONID=doc",
            )
        self.assertEqual(caught.exception.code, "visit_required")
