from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

import medication_administration as mar
from server import ApiError

PATIENT = "patient-1"
VISIT = "visit-1"
ADMISSION = "admission-1"
ORDER = "order-1"
SLOT = "slot-1"


def admission() -> dict:
    return {
        "uuid": ADMISSION,
        "encounterDatetime": "2026-08-26T13:29:00.000+0000",
        "patient": {"uuid": PATIENT},
        "visit": {
            "uuid": VISIT,
            "visitType": {"uuid": mar.ward.IPD_VISIT_TYPE, "name": "IPD"},
        },
    }


def slot(
    *,
    uuid: str = SLOT,
    order_uuid: str = ORDER,
    patient_uuid: str = PATIENT,
    status: str = "SCHEDULED",
    administration: dict | None = None,
    start_time: int = 1787806800,
) -> dict:
    return {
        "uuid": uuid,
        "serviceType": "MedicationRequest",
        "status": status,
        "startTime": start_time,
        "order": {
            "uuid": order_uuid,
            "orderNumber": "ORD-28",
            "patient": {"uuid": patient_uuid},
            "action": "NEW",
            "careSetting": {"name": "Inpatient"},
            "encounter": {"uuid": "order-encounter"},
            "drug": {"uuid": "drug-1", "display": "Paracetamol 500 mg — TEST"},
            "dose": 1.0,
            "doseUnits": {"display": "Tablet"},
            "route": {"display": "Oral"},
            "frequency": {"display": "Twice a day"},
            "asNeeded": False,
            "instructions": None,
        },
        "medicationAdministration": administration,
        "notes": "ABIKAN MAR DEVELOPMENT FIXTURE",
    }


def schedules(*items: dict) -> list[dict]:
    return [{"uuid": "schedule-1", "slots": list(items)}]


def saved_administration(outcome: str = "given") -> dict:
    underlying = mar.OUTCOME_TO_BAHMNI_STATUS[outcome]
    return {
        "uuid": "administration-1",
        "patientUuid": PATIENT,
        "encounterUuid": ADMISSION,
        "orderUuid": ORDER,
        "status": underlying,
        "administeredDateTime": 1787807100000,
        "notes": [
            {
                "text": (
                    f'{mar.MAR_NOTE_MARKER}{{"outcome":"{outcome}",'
                    f'"reason":"","userUuid":"nurse-user","personUuid":"nurse-person",'
                    f'"authorName":"Aisha Bello"}}'
                )
            }
        ],
    }


class MedicationAdministrationTests(unittest.TestCase):
    def test_openmrs_offset_without_colon_parses_to_epoch_seconds(self) -> None:
        self.assertEqual(
            mar._epoch_seconds("2026-08-30T10:05:00.000+0000"),
            1788084300,
        )
    def _create(
        self,
        body: dict,
        *,
        scheduled: list[dict] | None = None,
        now_seconds: int = 1787807100,
    ) -> tuple[dict, list[dict]]:
        writes: list[dict] = []

        def openmrs(path: str, payload):
            self.assertEqual(
                path,
                "/openmrs/ws/rest/v1/ipd/scheduledMedicationAdministrations",
            )
            request = payload[0]
            writes.append(request)
            return [
                {
                    **request,
                    "uuid": "administration-created",
                }
            ]

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    mar.ward,
                    "require_nursing_user",
                    return_value={"uuid": "nurse-user"},
                )
            )
            stack.enter_context(
                patch.object(mar.ward, "_active_admission", return_value=admission())
            )
            stack.enter_context(patch.object(mar, "_now_seconds", return_value=now_seconds))
            stack.enter_context(
                patch.object(
                    mar,
                    "_load_schedules",
                    return_value=scheduled if scheduled is not None else schedules(slot()),
                )
            )
            stack.enter_context(patch.object(mar, "_validate_order", return_value={}))
            stack.enter_context(
                patch.object(mar.ward, "_provider_uuid", return_value="nurse-provider")
            )
            stack.enter_context(
                patch.object(
                    mar.ward,
                    "_authenticated_nurse_identity",
                    return_value={
                        "userUuid": "nurse-user",
                        "personUuid": "nurse-person",
                        "authorName": "Aisha Bello",
                    },
                )
            )
            stack.enter_context(
                patch.object(mar.core, "openmrs_service_post", side_effect=openmrs)
            )
            result = mar.create_scheduled_administration(
                PATIENT,
                body,
                "JSESSIONID=nurse",
            )
        return result, writes

    def test_read_returns_only_valid_admission_bound_scheduled_slots(self) -> None:
        valid = slot()
        other_patient = slot(uuid="slot-2", order_uuid="order-2", patient_uuid="patient-2")
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=admission()),
            patch.object(mar, "_sync_active_schedules", return_value=[]),
            patch.object(
                mar,
                "_load_schedules",
                return_value=schedules(valid, other_patient),
            ),
            patch.object(mar, "_now_seconds", return_value=1787806800),
            patch.object(mar, "_validate_order", return_value={}) as validate,
        ):
            result = mar.build_mar(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(len(result["orders"]), 1)
        self.assertEqual(result["orders"][0]["orderUuid"], ORDER)
        self.assertEqual(result["orders"][0]["slots"][0]["uuid"], SLOT)
        self.assertEqual(
            result["orders"][0]["slots"][0]["scheduledTime"],
            1787806800000,
        )
        self.assertTrue(result["activeAdmission"])
        self.assertTrue(
            result["orders"][0]["slots"][0]["timing"]["canAdministerNormally"]
        )
        validate.assert_called_once_with(
            ORDER,
            PATIENT,
            VISIT,
            require_active=False,
        )

    def test_invalid_outpatient_order_is_not_exposed(self) -> None:
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=admission()),
            patch.object(mar, "_sync_active_schedules", return_value=[]),
            patch.object(mar, "_load_schedules", return_value=schedules(slot())),
            patch.object(
                mar,
                "_validate_order",
                side_effect=ApiError(409, "outpatient_order", "Outpatient"),
            ),
        ):
            result = mar.build_mar(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(result["orders"], [])

    def test_inactive_order_keeps_finalized_history_but_not_stale_scheduled_slots(self) -> None:
        completed = slot(status="COMPLETED", administration=saved_administration())
        stale = slot(uuid="slot-stale")
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=admission()),
            patch.object(mar, "_sync_active_schedules", return_value=[]),
            patch.object(
                mar,
                "_load_schedules",
                return_value=schedules(completed, stale),
            ),
            patch.object(
                mar,
                "_validate_order",
                return_value={"autoExpireDate": "2020-01-01T00:00:00+00:00"},
            ),
        ):
            result = mar.build_mar(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(
            [item["uuid"] for item in result["orders"][0]["slots"]],
            [SLOT],
        )

    def test_given_uses_exact_slot_and_server_owned_clinical_values(self) -> None:
        result, writes = self._create(
            {"slotUuid": SLOT, "outcome": "given", "reason": ""}
        )
        self.assertFalse(result["duplicate"])
        self.assertEqual(len(writes), 1)
        payload = writes[0]
        self.assertEqual(payload["patientUuid"], PATIENT)
        self.assertEqual(payload["encounterUuid"], ADMISSION)
        self.assertEqual(payload["orderUuid"], ORDER)
        self.assertEqual(payload["slotUuid"], SLOT)
        self.assertEqual(payload["drugUuid"], "drug-1")
        self.assertEqual(payload["dose"], 1.0)
        self.assertEqual(payload["doseUnits"], "Tablet")
        self.assertEqual(payload["route"], "Oral")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["providers"][0]["providerUuid"], "nurse-provider")
        self.assertEqual(payload["providers"][0]["function"], "Performer")
        self.assertIsInstance(payload["administeredDateTime"], int)
        self.assertLess(payload["administeredDateTime"], 10_000_000_000)
        self.assertEqual(payload["administeredDateTime"], 1787807100)
        self.assertEqual(result["slot"]["status"], "COMPLETED")
        self.assertEqual(result["slot"]["administration"]["nurseName"], "Aisha Bello")
        self.assertNotEqual(
            result["slot"]["administration"]["scheduledTime"],
            result["slot"]["administration"]["actualTime"],
        )

    def test_supported_outcomes_map_to_installed_statuses_and_preserve_reason(self) -> None:
        for outcome, expected in (
            ("given", "completed"),
            ("not-done", "not-done"),
            ("refused", "not-done"),
            ("held", "stopped"),
        ):
            reason = "" if outcome == "given" else f"Reason for {outcome}"
            result, writes = self._create(
                {"slotUuid": SLOT, "outcome": outcome, "reason": reason}
            )
            self.assertEqual(writes[0]["status"], expected)
            self.assertEqual(result["slot"]["administration"]["outcome"], outcome)
            self.assertEqual(result["slot"]["administration"]["reason"], reason)

    def test_non_given_requires_reason(self) -> None:
        with self.assertRaises(ApiError) as raised:
            self._create({"slotUuid": SLOT, "outcome": "refused", "reason": ""})
        self.assertEqual(raised.exception.code, "reason_required")

    def test_browser_cannot_supply_patient_order_dose_route_performer_or_times(self) -> None:
        with patch.object(
            mar.ward,
            "require_nursing_user",
            return_value={"uuid": "nurse-user"},
        ):
            with self.assertRaises(ApiError) as raised:
                mar.create_scheduled_administration(
                    PATIENT,
                    {
                        "slotUuid": SLOT,
                        "outcome": "given",
                        "reason": "",
                        "orderUuid": "another-order",
                        "providerUuid": "another-provider",
                        "dose": 1000,
                        "route": "IV",
                        "actualTime": 1,
                    },
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "server_fields_only")

    def test_future_slot_requires_explicit_outside_window_action(self) -> None:
        with self.assertRaises(ApiError) as raised:
            self._create(
                {"slotUuid": SLOT, "outcome": "given", "reason": ""},
                now_seconds=1787806800 - 31 * 60,
            )
        self.assertEqual(raised.exception.code, "outside_administration_window")

    def test_installed_early_and_late_window_allows_normal_administration(self) -> None:
        for now_seconds in (
            1787806800 - mar.EARLY_ADMINISTRATION_MINUTES * 60,
            1787806800 + mar.LATE_ADMINISTRATION_MINUTES * 60,
        ):
            result, writes = self._create(
                {"slotUuid": SLOT, "outcome": "given", "reason": ""},
                now_seconds=now_seconds,
            )
            self.assertFalse(result["duplicate"])
            self.assertEqual(len(writes), 1)

    def test_outside_window_requires_reason_and_preserves_server_time(self) -> None:
        now_seconds = 1787806800 - 24 * 60 * 60
        with self.assertRaises(ApiError) as raised:
            self._create(
                {
                    "slotUuid": SLOT,
                    "outcome": "given",
                    "reason": "",
                    "outsideWindow": True,
                },
                now_seconds=now_seconds,
            )
        self.assertEqual(raised.exception.code, "outside_window_reason_required")

        result, writes = self._create(
            {
                "slotUuid": SLOT,
                "outcome": "given",
                "reason": "Dose timing changed by the prescriber",
                "outsideWindow": True,
            },
            now_seconds=now_seconds,
        )
        self.assertEqual(writes[0]["administeredDateTime"], now_seconds)
        self.assertEqual(result["slot"]["scheduledTime"], 1787806800000)
        self.assertTrue(result["slot"]["administration"]["outsideWindow"])

    def test_normal_action_rejects_unneeded_outside_window_override(self) -> None:
        with self.assertRaises(ApiError) as raised:
            self._create(
                {
                    "slotUuid": SLOT,
                    "outcome": "given",
                    "reason": "Not applicable",
                    "outsideWindow": True,
                }
            )
        self.assertEqual(raised.exception.code, "outside_window_not_required")

    def test_normal_action_cannot_supply_an_actual_administration_time(self) -> None:
        with self.assertRaises(ApiError) as raised:
            self._create(
                {
                    "slotUuid": SLOT,
                    "outcome": "given",
                    "reason": "",
                    "actualAdministrationTime": 1787806900,
                }
            )
        self.assertEqual(raised.exception.code, "server_fields_only")

    def test_wrong_patient_admission_order_or_slot_is_rejected(self) -> None:
        with self.assertRaises(ApiError) as raised:
            self._create(
                {"slotUuid": "missing", "outcome": "given", "reason": ""}
            )
        self.assertEqual(raised.exception.code, "slot_mismatch")

        with self.assertRaises(ApiError) as raised:
            self._create(
                {"slotUuid": SLOT, "outcome": "given", "reason": ""},
                scheduled=schedules(slot(patient_uuid="another-patient")),
            )
        self.assertEqual(raised.exception.code, "slot_patient_mismatch")

    def test_slot_is_authoritative_duplicate_key(self) -> None:
        prior = saved_administration()
        result, writes = self._create(
            {"slotUuid": SLOT, "outcome": "given", "reason": ""},
            scheduled=schedules(
                slot(status="COMPLETED", administration=prior)
            ),
        )
        self.assertTrue(result["duplicate"])
        self.assertEqual(writes, [])
        self.assertEqual(result["slot"]["administration"]["uuid"], "administration-1")

    def test_finalized_slot_without_administration_cannot_be_rewritten(self) -> None:
        with self.assertRaises(ApiError) as raised:
            self._create(
                {"slotUuid": SLOT, "outcome": "given", "reason": ""},
                scheduled=schedules(slot(status="MISSED")),
            )
        self.assertEqual(raised.exception.code, "slot_finalized")

    def test_unauthorized_department_is_rejected(self) -> None:
        denial = ApiError(403, "forbidden", "Denied")
        with patch.object(mar.ward, "require_inpatient_view", side_effect=denial):
            with self.assertRaises(ApiError) as raised:
                mar.build_mar(PATIENT, "JSESSIONID=lab")
        self.assertEqual(raised.exception.status, 403)

    def test_discharged_admission_history_remains_readable(self) -> None:
        completed = slot(status="COMPLETED", administration=saved_administration())
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=None),
            patch.object(
                mar.ward,
                "_admission_encounters",
                return_value=[admission()],
            ),
            patch.object(mar, "_load_schedules", return_value=schedules(completed)),
            patch.object(mar, "_validate_order", return_value={}),
        ):
            result = mar.build_mar(PATIENT, "JSESSIONID=nurse")
        self.assertFalse(result["activeAdmission"])
        administration = result["orders"][0]["slots"][0]["administration"]
        self.assertEqual(administration["outcome"], "given")
        self.assertEqual(administration["nurseName"], "Aisha Bello")
        self.assertEqual(result["visitUuid"], VISIT)
        self.assertEqual(result["admissionEncounterUuid"], ADMISSION)

    def test_doctor_can_read_historical_mar_for_selected_admission(self) -> None:
        completed = slot(status="COMPLETED", administration=saved_administration())
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user", "privileges": [mar.ward.CLINICAL_PRIVILEGE]},
            ),
            patch.object(mar.ward, "_active_admission", return_value=None),
            patch.object(
                mar.ward,
                "_admission_encounters",
                return_value=[admission()],
            ),
            patch.object(mar, "_load_schedules", return_value=schedules(completed)),
            patch.object(mar, "_validate_order", return_value={}),
        ):
            result = mar.build_mar(
                PATIENT,
                "JSESSIONID=doctor",
                visit_uuid=VISIT,
                admission_encounter_uuid=ADMISSION,
            )
        self.assertFalse(result["activeAdmission"])
        self.assertEqual(result["orders"][0]["slots"][0]["administration"]["outcome"], "given")

    def test_historical_read_rejects_a_visit_that_is_not_this_admission(self) -> None:
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=None),
            patch.object(
                mar.ward,
                "_admission_encounters",
                return_value=[admission()],
            ),
        ):
            with self.assertRaises(ApiError) as raised:
                mar.build_mar(
                    PATIENT,
                    "JSESSIONID=doctor",
                    visit_uuid="another-visit",
                )
        self.assertEqual(raised.exception.code, "admission_history_not_found")

    def test_discharged_admission_cannot_receive_new_administration(self) -> None:
        with (
            patch.object(
                mar.ward,
                "require_nursing_user",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=None),
        ):
            with self.assertRaises(ApiError) as raised:
                mar.create_scheduled_administration(
                    PATIENT,
                    {"slotUuid": SLOT, "outcome": "given", "reason": ""},
                    "JSESSIONID=nurse",
                )
        self.assertEqual(raised.exception.code, "not_admitted")

    def test_doctor_cannot_administer_historical_or_active_dose(self) -> None:
        denial = ApiError(403, "forbidden", "Denied")
        with patch.object(mar.ward, "require_nursing_user", side_effect=denial):
            with self.assertRaises(ApiError) as raised:
                mar.create_scheduled_administration(
                    PATIENT,
                    {"slotUuid": SLOT, "outcome": "given", "reason": ""},
                    "JSESSIONID=doctor",
                )
        self.assertEqual(raised.exception.status, 403)

    def test_active_read_creates_missing_schedules_before_loading_slots(self) -> None:
        synced: list[str] = []

        def sync(patient_uuid: str, cookie: str, admission: dict) -> list:
            synced.append(patient_uuid)
            self.assertEqual(cookie, "JSESSIONID=nurse")
            self.assertEqual(admission["uuid"], ADMISSION)
            return []

        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=admission()),
            patch.object(mar, "_sync_active_schedules", side_effect=sync),
            patch.object(mar, "_load_schedules", return_value=schedules(slot())),
            patch.object(mar, "_validate_order", return_value={}),
        ):
            result = mar.build_mar(PATIENT, "JSESSIONID=nurse")
        self.assertEqual(synced, [PATIENT])
        self.assertEqual(result["scheduleIssues"], [])
        self.assertEqual(result["orders"][0]["orderUuid"], ORDER)

    def test_historical_read_does_not_create_schedules(self) -> None:
        with (
            patch.object(
                mar.ward,
                "require_inpatient_view",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(mar.ward, "_active_admission", return_value=None),
            patch.object(
                mar.ward,
                "_admission_encounters",
                return_value=[admission()],
            ),
            patch.object(
                mar,
                "_sync_active_schedules",
                side_effect=AssertionError("historical read must not create schedules"),
            ),
            patch.object(
                mar,
                "_load_schedules",
                return_value=schedules(slot(status="COMPLETED", administration=saved_administration())),
            ),
            patch.object(mar, "_validate_order", return_value={}),
        ):
            result = mar.build_mar(PATIENT, "JSESSIONID=nurse")
        self.assertFalse(result["activeAdmission"])
        self.assertEqual(result["scheduleIssues"], [])

    def test_typed_medicine_uses_the_name_the_doctor_wrote(self) -> None:
        self.assertEqual(
            mar.medication_label(
                {
                    "drugNonCoded": "Calamine lotion extra",
                    "drug": {},
                    "concept": {"display": "DrugOther"},
                }
            ),
            "Calamine lotion extra",
        )
        self.assertEqual(
            mar.medication_label({"drug": {"display": "Paracetamol 500 mg — TEST"}}),
            "Paracetamol 500 mg — TEST",
        )


if __name__ == "__main__":
    unittest.main()
