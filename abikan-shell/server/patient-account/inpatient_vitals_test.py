from __future__ import annotations

import unittest
from unittest.mock import patch

import inpatient
import inpatient_vitals as vitals
from server import ApiError


PATIENT = "patient-a"
OTHER = "patient-b"
ADMISSION = "admission-1"
VISIT = "visit-1"


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


def vital_obs(
    key: str,
    value: float,
    request_id: str,
    recorded_at: str = "2026-08-27T08:00:00.000+0000",
    uuid: str = "obs-1",
) -> dict[str, object]:
    concept = vitals.VITAL_CONCEPTS[key]
    return {
        "uuid": uuid,
        "obsDatetime": recorded_at,
        "value": value,
        "comment": (
            f"{vitals.VITALS_MARKER}{request_id}|nurse-user|nurse-person|"
            "Nursing%20Staff"
        ),
        "voided": False,
        "concept": {"uuid": concept["uuid"], "display": concept["label"]},
        "creator": {"uuid": "service-user", "display": "superman"},
    }


class InpatientVitalsTests(unittest.TestCase):
    def test_nurse_records_valid_vitals_with_server_identity_and_time(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []
        stored: list[dict[str, object]] = []

        def service_post(path: str, body: dict[str, object]):
            calls.append((path, body))
            key = next(
                name
                for name, concept in vitals.VITAL_CONCEPTS.items()
                if concept["uuid"] == body["concept"]
            )
            stored.append(
                vital_obs(
                    key,
                    float(body["value"]),
                    "request-1",
                    str(body["obsDatetime"]),
                    uuid=f"obs-{len(stored)+1}",
                )
            )
            return {"uuid": stored[-1]["uuid"]}

        live = admission()

        def active(_patient: str, _cookie: str):
            return admission(list(stored)) if stored else live

        with (
            patch.object(
                vitals.ward,
                "require_nursing_user",
                return_value={"uuid": "nurse-user", "privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(vitals, "_active_context", return_value=live),
            patch.object(vitals.ward, "_active_admission", side_effect=active),
            patch.object(
                vitals.ward,
                "_authenticated_nurse_identity",
                return_value={
                    "userUuid": "nurse-user",
                    "personUuid": "nurse-person",
                    "authorName": "Nursing Staff",
                },
            ),
            patch.object(
                vitals.ward,
                "now_openmrs",
                return_value="2026-08-27T07:15:00.000+0000",
            ),
            patch.object(vitals.core, "openmrs_service_post", side_effect=service_post),
        ):
            result = vitals.create_vitals(
                PATIENT,
                {
                    "temperature": 37.2,
                    "pulse": 82,
                    "respiratoryRate": 18,
                    "systolic": 120,
                    "diastolic": 80,
                    "spo2": 98,
                    "requestId": "request-1",
                },
                "JSESSIONID=nurse",
            )

        self.assertFalse(result["duplicate"])
        self.assertEqual(result["patientUuid"], PATIENT)
        self.assertEqual(result["visitUuid"], VISIT)
        self.assertEqual(result["admissionEncounterUuid"], ADMISSION)
        self.assertEqual(result["reading"]["recordedBy"], "Nursing Staff")
        self.assertEqual(result["reading"]["authorUserUuid"], "nurse-user")
        self.assertEqual(result["reading"]["recordedAt"], "2026-08-27T07:15:00.000+0000")
        self.assertEqual(len(calls), 6)
        for path, body in calls:
            self.assertEqual(path, "/openmrs/ws/rest/v1/obs")
            self.assertEqual(body["person"], PATIENT)
            self.assertEqual(body["encounter"], ADMISSION)
            self.assertEqual(body["obsDatetime"], "2026-08-27T07:15:00.000+0000")
            self.assertIn(vitals.VITALS_MARKER, str(body["comment"]))
            self.assertIn("nurse-user", str(body["comment"]))
            self.assertNotIn("creator", body)
            self.assertNotIn("uuid", body)
        values = {row["key"]: row["value"] for row in result["reading"]["observations"]}
        self.assertEqual(values["temperature"], "37.2")
        self.assertEqual(values["pulse"], "82")
        self.assertEqual(values["systolic"], "120")
        self.assertEqual(values["diastolic"], "80")

    def test_client_cannot_override_identity_time_or_patient(self) -> None:
        with patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}):
            with self.assertRaises(ApiError) as raised:
                vitals.create_vitals(
                    PATIENT,
                    {
                        "temperature": 37.2,
                        "requestId": "request-2",
                        "obsDatetime": "2001-01-01T00:00:00.000+0000",
                        "patientUuid": OTHER,
                        "authorName": "Someone else",
                    },
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "server_fields_only")

    def test_active_admission_is_required_for_write(self) -> None:
        with (
            patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}),
            patch.object(
                vitals,
                "_active_context",
                side_effect=ApiError(409, "not_admitted", "Not admitted"),
            ),
        ):
            with self.assertRaises(ApiError) as raised:
                vitals.create_vitals(
                    PATIENT,
                    {"temperature": 37.2, "requestId": "request-3"},
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "not_admitted")

    def test_multiple_readings_are_preserved(self) -> None:
        first = [
            vital_obs("temperature", 37.2, "reading-1", "2026-08-27T08:00:00.000+0000", "obs-a"),
            vital_obs("pulse", 82, "reading-1", "2026-08-27T08:00:00.000+0000", "obs-b"),
        ]
        second = first + [
            vital_obs("temperature", 37.5, "reading-2", "2026-08-27T12:00:00.000+0000", "obs-c"),
            vital_obs("pulse", 88, "reading-2", "2026-08-27T12:00:00.000+0000", "obs-d"),
        ]
        with (
            patch.object(
                vitals.ward,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(
                vitals,
                "_read_context",
                return_value=(admission(second), True),
            ),
        ):
            result = vitals.build_vitals(PATIENT, "JSESSIONID=nurse")
        self.assertEqual(len(result["readings"]), 2)
        self.assertEqual(result["readings"][0]["requestId"], "reading-2")
        self.assertEqual(result["readings"][1]["requestId"], "reading-1")
        latest = {row["key"]: row["value"] for row in result["readings"][0]["observations"]}
        earlier = {row["key"]: row["value"] for row in result["readings"][1]["observations"]}
        self.assertEqual(latest["temperature"], "37.5")
        self.assertEqual(earlier["temperature"], "37.2")

    def test_doctor_can_read_and_cannot_write(self) -> None:
        with (
            patch.object(
                vitals.ward,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.CLINICAL_PRIVILEGE]},
            ),
            patch.object(
                vitals,
                "_read_context",
                return_value=(admission([vital_obs("temperature", 37.2, "reading-1")]), True),
            ),
        ):
            result = vitals.build_vitals(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(len(result["readings"]), 1)

        with patch.object(
            vitals.ward,
            "require_nursing_user",
            side_effect=ApiError(403, "forbidden", "Doctor cannot record"),
        ):
            with self.assertRaises(ApiError) as raised:
                vitals.create_vitals(
                    PATIENT,
                    {"temperature": 37.2, "requestId": "request-4"},
                    "JSESSIONID=doctor",
                )
        self.assertEqual(raised.exception.status, 403)

    def test_unrelated_department_cannot_read(self) -> None:
        with patch.object(
            vitals.ward,
            "require_inpatient_view",
            side_effect=ApiError(403, "forbidden", "Denied"),
        ):
            with self.assertRaises(ApiError) as raised:
                vitals.build_vitals(PATIENT, "JSESSIONID=lab")
        self.assertEqual(raised.exception.status, 403)

    def test_cross_patient_body_is_rejected(self) -> None:
        with patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}):
            with self.assertRaises(ApiError) as raised:
                vitals.create_vitals(
                    PATIENT,
                    {
                        "temperature": 37.2,
                        "requestId": "request-5",
                        "patientUuid": OTHER,
                    },
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "server_fields_only")

    def test_invalid_values_are_rejected(self) -> None:
        with patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}):
            with self.assertRaises(ApiError) as raised:
                vitals.create_vitals(
                    PATIENT,
                    {"temperature": "hot", "requestId": "request-6"},
                    "JSESSIONID=nurse",
                )
            self.assertEqual(raised.exception.code, "invalid_vital")
            with self.assertRaises(ApiError) as incomplete:
                vitals.create_vitals(
                    PATIENT,
                    {"systolic": 120, "requestId": "request-7"},
                    "JSESSIONID=nurse",
                )
            self.assertEqual(incomplete.exception.code, "incomplete_blood_pressure")
            with self.assertRaises(ApiError) as empty:
                vitals.create_vitals(
                    PATIENT,
                    {"requestId": "request-8"},
                    "JSESSIONID=nurse",
                )
            self.assertEqual(empty.exception.code, "vitals_required")
            with self.assertRaises(ApiError) as out_of_range:
                vitals.create_vitals(
                    PATIENT,
                    {"temperature": 12, "requestId": "request-9"},
                    "JSESSIONID=nurse",
                )
            self.assertEqual(out_of_range.exception.code, "vital_out_of_range")

    def test_historical_read_after_discharge_and_write_rejected(self) -> None:
        historical = admission([vital_obs("temperature", 37.2, "reading-1")])
        historical["visit"]["stopDatetime"] = "2026-08-27T18:00:00.000+0000"
        with (
            patch.object(
                vitals.ward,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(
                vitals,
                "_read_context",
                return_value=(historical, False),
            ),
        ):
            result = vitals.build_vitals(PATIENT, "JSESSIONID=nurse")
        self.assertFalse(result["activeAdmission"])
        self.assertEqual(len(result["readings"]), 1)

        with (
            patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}),
            patch.object(
                vitals,
                "_active_context",
                side_effect=ApiError(409, "not_admitted", "Not admitted"),
            ),
        ):
            with self.assertRaises(ApiError) as raised:
                vitals.create_vitals(
                    PATIENT,
                    {"temperature": 37.2, "requestId": "request-10"},
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "not_admitted")

    def test_duplicate_request_returns_existing_reading(self) -> None:
        existing = admission([vital_obs("temperature", 37.2, "same-request")])
        with (
            patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}),
            patch.object(vitals, "_active_context", return_value=existing),
            patch.object(vitals.ward, "_active_admission", return_value=existing),
            patch.object(
                vitals.ward,
                "_authenticated_nurse_identity",
                return_value={
                    "userUuid": "nurse-user",
                    "personUuid": "nurse-person",
                    "authorName": "Nursing Staff",
                },
            ),
            patch.object(vitals.core, "openmrs_service_post") as openmrs,
        ):
            result = vitals.create_vitals(
                PATIENT,
                {"temperature": 38.0, "requestId": "same-request"},
                "JSESSIONID=nurse",
            )
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["reading"]["observations"][0]["value"], "37.2")
        openmrs.assert_not_called()

    def test_nurse_records_vitals_on_an_open_outpatient_visit(self) -> None:
        stored: list[dict[str, object]] = []
        live = {
            "uuid": "consult-1",
            "patient": {"uuid": PATIENT},
            "location": {"uuid": "opd-loc", "name": "OPD"},
            "visit": {
                "uuid": "opd-visit",
                "stopDatetime": None,
                "visitType": {"name": "OPD"},
                "location": {"uuid": "opd-loc", "name": "OPD"},
            },
            "obs": [],
        }

        def reload(_patient: str, encounter_uuid: str, _cookie: str):
            return {
                **live,
                "uuid": encounter_uuid,
                "obs": list(stored),
            }

        def service_post(path: str, body: dict[str, object]):
            stored.append(
                vital_obs(
                    "temperature",
                    float(body["value"]),
                    "opd-request",
                    str(body["obsDatetime"]),
                    uuid="obs-opd-1",
                )
            )
            return {"uuid": "obs-opd-1"}

        with (
            patch.object(vitals.ward, "require_nursing_user", return_value={"uuid": "nurse"}),
            patch.object(vitals, "_active_context", return_value=live),
            patch.object(vitals.ward, "_active_admission", return_value=None),
            patch.object(vitals, "_reload_write_context", side_effect=reload),
            patch.object(
                vitals.ward,
                "_authenticated_nurse_identity",
                return_value={
                    "userUuid": "nurse-user",
                    "personUuid": "nurse-person",
                    "authorName": "Nursing Staff",
                },
            ),
            patch.object(
                vitals.ward,
                "now_openmrs",
                return_value="2026-09-29T09:15:00.000+0000",
            ),
            patch.object(vitals.core, "openmrs_service_post", side_effect=service_post),
        ):
            result = vitals.create_vitals(
                PATIENT,
                {"temperature": 37.1, "requestId": "opd-request"},
                "JSESSIONID=nurse",
            )
        self.assertFalse(result["duplicate"])
        self.assertTrue(result["canRecord"])
        self.assertFalse(result["activeAdmission"])
        self.assertEqual(result["visitUuid"], "opd-visit")
        self.assertEqual(result["reading"]["observations"][0]["value"], "37.1")

    def test_vitals_read_falls_back_to_an_open_visit_without_admission(self) -> None:
        context = {
            "uuid": "consult-1",
            "patient": {"uuid": PATIENT},
            "visit": {
                "uuid": "opd-visit",
                "stopDatetime": None,
                "visitType": {"name": "OPD"},
            },
            "obs": [vital_obs("pulse", 88, "visit-read")],
        }
        with (
            patch.object(
                vitals.ward,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(
                vitals,
                "_read_context",
                side_effect=ApiError(409, "admission_history_not_found", "No admission"),
            ),
            patch.object(vitals, "_open_visit_vitals_context", return_value=context),
        ):
            result = vitals.build_vitals(PATIENT, "JSESSIONID=nurse")
        self.assertFalse(result["activeAdmission"])
        self.assertTrue(result["canRecord"])
        self.assertEqual(result["visitUuid"], "opd-visit")
        self.assertEqual(len(result["readings"]), 1)

    def test_vitals_read_without_a_visit_still_allows_recording(self) -> None:
        with (
            patch.object(
                vitals.ward,
                "require_inpatient_view",
                return_value={"privileges": [inpatient.ADT_PRIVILEGE]},
            ),
            patch.object(
                vitals,
                "_read_context",
                side_effect=ApiError(409, "admission_history_not_found", "No admission"),
            ),
            patch.object(vitals, "_open_visit_vitals_context", return_value=None),
        ):
            result = vitals.build_vitals(PATIENT, "JSESSIONID=nurse")
        self.assertFalse(result["activeAdmission"])
        self.assertTrue(result["canRecord"])
        self.assertEqual(result["readings"], [])

    def test_active_context_starts_a_visit_when_none_is_open(self) -> None:
        created = {
            "uuid": "consult-new",
            "patient": {"uuid": PATIENT},
            "visit": {"uuid": "new-visit", "stopDatetime": None},
        }
        with (
            patch.object(vitals, "_ipd_write_context", return_value=None),
            patch.object(vitals, "_open_visit_vitals_context", return_value=None),
            patch.object(vitals, "_create_open_visit_context", return_value=created) as start,
        ):
            result = vitals._active_context(PATIENT, "JSESSIONID=nurse")
        start.assert_called_once_with(PATIENT, "JSESSIONID=nurse")
        self.assertEqual(result["uuid"], "consult-new")


if __name__ == "__main__":
    unittest.main()
