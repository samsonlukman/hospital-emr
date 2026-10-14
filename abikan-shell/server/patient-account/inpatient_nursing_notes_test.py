from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from unittest.mock import patch

import inpatient
from server import ApiError


PATIENT = "f242364e-b70f-4fec-b29e-8ad4fbe147b5"
ADMISSION = "aaf674d5-128d-4697-8a13-71c2590340e4"
VISIT = "fabd9192-e8f5-4389-9c91-030ca2e73da7"


def admission(obs: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "uuid": ADMISSION,
        "encounterDatetime": "2026-08-26T13:29:00.000+0000",
        "patient": {"uuid": PATIENT},
        "location": {"uuid": "ward-location", "name": "Ward"},
        "visit": {
            "uuid": VISIT,
            "stopDatetime": None,
            "visitType": {"uuid": inpatient.IPD_VISIT_TYPE, "name": "IPD"},
        },
        "obs": obs or [],
    }


def note_obs(request_id: str = "request-1") -> dict[str, object]:
    return {
        "uuid": "saved-note",
        "obsDatetime": "2026-08-26T19:30:45.000+0000",
        "value": "Patient resting comfortably.",
        "comment": (
            f"{inpatient.NURSING_NOTE_MARKER}{request_id}|nurse-user|nurse-person|"
            "Nurse%20Hospital EMR"
        ),
        "voided": False,
        "concept": {"uuid": inpatient.GENERAL_PATIENT_NOTE_CONCEPT},
        "creator": {"uuid": "nurse-user", "display": "nurse.abikan"},
    }


class NursingNoteTests(unittest.TestCase):
    def test_create_binds_note_to_active_admission_and_server_identity(self) -> None:
        calls: list[tuple[str, str, dict[str, object]]] = []

        def service_post(path: str, body: dict[str, object]):
            calls.append(("POST", path, body))
            return {}

        with (
            patch.object(
                inpatient,
                "require_nursing_user",
                return_value={"uuid": "nurse-user", "privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(inpatient, "_active_admission", return_value=admission()),
            patch.object(
                inpatient,
                "_authenticated_nurse_identity",
                return_value={
                    "userUuid": "nurse-user",
                    "personUuid": "nurse-person",
                    "authorName": "Nurse Hospital EMR",
                },
            ),
            patch.object(inpatient, "_provider_uuid", return_value="nurse-provider"),
            patch.object(inpatient.core, "openmrs_service_post", side_effect=service_post),
            patch.object(
                inpatient,
                "_admission_encounters",
                side_effect=[
                    [admission()],
                    [admission([note_obs()])],
                ],
            ),
        ):
            result = inpatient.create_nursing_note(
                PATIENT,
                {"note": "Patient resting comfortably.", "requestId": "request-1"},
                "JSESSIONID=nurse",
            )

        self.assertFalse(result["duplicate"])
        self.assertEqual(result["note"]["authorName"], "Nurse Hospital EMR")
        self.assertEqual(result["note"]["recordedAt"], "2026-08-26T19:30:45.000+0000")
        self.assertEqual(len(calls), 1)
        body = calls[0][2]
        self.assertEqual(body["patientUuid"], PATIENT)
        self.assertEqual(body["visitUuid"], VISIT)
        self.assertEqual(body["encounterUuid"], ADMISSION)
        observation = body["observations"][0]
        self.assertEqual(observation["value"], "Patient resting comfortably.")
        self.assertNotIn("uuid", observation)
        self.assertNotIn("creator", observation)
        self.assertRegex(observation["obsDatetime"], r"^\d{4}-\d{2}-\d{2}T")

    def test_client_cannot_override_author_time_patient_or_admission(self) -> None:
        with patch.object(
            inpatient,
            "require_nursing_user",
            return_value={"uuid": "nurse-user"},
        ):
            with self.assertRaises(ApiError) as raised:
                inpatient.create_nursing_note(
                    PATIENT,
                    {
                        "note": "Unsafe",
                        "requestId": "request-2",
                        "authorName": "Someone else",
                        "recordedAt": "2001-01-01",
                        "patientUuid": "other",
                        "encounterUuid": "other",
                    },
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "server_fields_only")

    def test_duplicate_request_returns_persisted_note_without_writing(self) -> None:
        existing = admission([note_obs("same-request")])
        with (
            patch.object(
                inpatient,
                "require_nursing_user",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(inpatient, "_active_admission", return_value=existing),
            patch.object(
                inpatient,
                "_authenticated_nurse_identity",
                return_value={
                    "userUuid": "nurse-user",
                    "personUuid": "nurse-person",
                    "authorName": "Nurse Hospital EMR",
                },
            ),
            patch.object(inpatient, "_admission_encounters", return_value=[existing]),
            patch.object(inpatient.core, "openmrs_service_post") as openmrs,
        ):
            result = inpatient.create_nursing_note(
                PATIENT,
                {"note": "Patient resting comfortably.", "requestId": "same-request"},
                "JSESSIONID=nurse",
            )
        self.assertTrue(result["duplicate"])
        openmrs.assert_not_called()

    def test_concurrent_duplicate_requests_create_one_note(self) -> None:
        persisted: list[dict[str, object]] = []
        writes = 0
        start = Barrier(2)

        def encounters(*_args: object) -> list[dict[str, object]]:
            return [admission(list(persisted))]

        def service_post(_path: str, _body: dict[str, object]) -> dict[str, object]:
            nonlocal writes
            writes += 1
            sleep(0.05)
            persisted.append(note_obs("concurrent-request"))
            return {}

        def create(_: int) -> dict[str, object]:
            start.wait()
            return inpatient.create_nursing_note(
                PATIENT,
                {
                    "note": "Patient resting comfortably.",
                    "requestId": "concurrent-request",
                },
                "JSESSIONID=nurse",
            )

        with (
            patch.object(
                inpatient,
                "require_nursing_user",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(inpatient, "_active_admission", return_value=admission()),
            patch.object(
                inpatient,
                "_authenticated_nurse_identity",
                return_value={
                    "userUuid": "nurse-user",
                    "personUuid": "nurse-person",
                    "authorName": "Nurse Hospital EMR",
                },
            ),
            patch.object(inpatient, "_provider_uuid", return_value="nurse-provider"),
            patch.object(inpatient, "_admission_encounters", side_effect=encounters),
            patch.object(inpatient.core, "openmrs_service_post", side_effect=service_post),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(create, range(2)))

        self.assertEqual(writes, 1)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(sorted(result["duplicate"] for result in results), [False, True])

    def test_create_rejects_missing_or_mismatched_active_admission(self) -> None:
        with (
            patch.object(inpatient, "require_nursing_user", return_value={"uuid": "nurse-user"}),
            patch.object(inpatient, "_active_admission", return_value=None),
        ):
            with self.assertRaises(ApiError) as raised:
                inpatient.create_nursing_note(
                    PATIENT,
                    {"note": "Patient resting.", "requestId": "request-3"},
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "not_admitted")

    def test_doctor_can_read_historical_notes_without_active_admission(self) -> None:
        with (
            patch.object(
                inpatient,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.CLINICAL_PRIVILEGE]},
            ),
            patch.object(inpatient, "_active_admission", return_value=None),
            patch.object(
                inpatient,
                "_admission_encounters",
                return_value=[admission([note_obs()])],
            ),
        ):
            result = inpatient.build_nursing_notes(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(result["activeAdmissionEncounterUuid"], "")
        self.assertEqual(len(result["notes"]), 1)
        self.assertEqual(result["notes"][0]["admissionEncounterUuid"], ADMISSION)

    def test_nurse_read_requires_active_admission(self) -> None:
        with (
            patch.object(
                inpatient,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(inpatient, "_active_admission", return_value=None),
        ):
            with self.assertRaises(ApiError) as raised:
                inpatient.build_nursing_notes(PATIENT, "JSESSIONID=nurse")
        self.assertEqual(raised.exception.code, "not_admitted")

    def test_nurse_read_is_limited_to_the_active_admission(self) -> None:
        current = admission([note_obs("current")])
        historical = admission([note_obs("historical")])
        historical["uuid"] = "older-admission"
        with (
            patch.object(
                inpatient,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(inpatient, "_active_admission", return_value=current),
            patch.object(
                inpatient,
                "_admission_encounters",
                return_value=[current, historical],
            ),
        ):
            result = inpatient.build_nursing_notes(PATIENT, "JSESSIONID=nurse")
        self.assertEqual(
            [row["requestId"] for row in result["notes"]],
            ["current"],
        )

    def test_unrelated_department_cannot_read(self) -> None:
        denial = ApiError(403, "forbidden", "Denied")
        with patch.object(inpatient, "require_inpatient_view", side_effect=denial):
            with self.assertRaises(ApiError) as raised:
                inpatient.build_nursing_notes(PATIENT, "JSESSIONID=other")
        self.assertEqual(raised.exception.status, 403)

    def test_only_marked_unvoided_observations_are_returned_newest_first(self) -> None:
        older = note_obs("older")
        older["uuid"] = "older-note"
        older["obsDatetime"] = "2026-08-26T18:00:00.000+0000"
        unrelated = {**note_obs("other"), "concept": {"uuid": "another-concept"}}
        voided = {**note_obs("voided"), "voided": True}
        notes = inpatient._serialize_nursing_notes(
            [admission([older, unrelated, voided, note_obs("newer")])]
        )
        self.assertEqual([row["requestId"] for row in notes], ["newer", "older"])


if __name__ == "__main__":
    unittest.main()
