from __future__ import annotations

import unittest
from unittest.mock import patch

import medication_schedule as schedules
from server import ApiError

PATIENT = "patient-1"
VISIT = "visit-1"
ADMISSION = "admission-1"
ORDER = "order-1"
PROVIDER = "provider-1"
SLOT = "slot-1"


def admission() -> dict:
    return {
        "uuid": ADMISSION,
        "encounterDatetime": "2026-08-30T10:00:00.000+0000",
        "patient": {"uuid": PATIENT},
        "visit": {
            "uuid": VISIT,
            "visitType": {"name": "IPD"},
        },
    }


def ipd_order(**overrides) -> dict:
    order = {
        "uuid": ORDER,
        "orderNumber": "ORD-41",
        "action": "NEW",
        "voided": False,
        "dateStopped": None,
        "autoExpireDate": None,
        "dateActivated": "2026-08-30T10:05:00.000+0000",
        "asNeeded": False,
        "dose": 1.0,
        "quantity": 3.0,
        "patient": {"uuid": PATIENT},
        "encounter": {"uuid": "enc-1", "visit": {"uuid": VISIT}},
        "careSetting": {"name": "Inpatient"},
        "frequency": {"display": "Once a day"},
        "route": {"display": "Oral"},
        "drug": {"uuid": "drug-1", "display": "Cetirizine 10 mg"},
        "orderer": {"uuid": PROVIDER},
    }
    order.update(overrides)
    return order


class MedicationScheduleTests(unittest.TestCase):
    def test_new_inpatient_order_posts_installed_schedule_api(self) -> None:
        posts: list[tuple[str, dict]] = []

        def post(path: str, payload: dict):
            posts.append((path, payload))
            return 200, {"id": 7}

        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=admission()),
            patch.object(schedules, "_load_visit_orders", return_value=[ipd_order()]),
            patch.object(schedules, "_existing_slots", side_effect=[[], [{"uuid": SLOT}]]),
            patch.object(schedules, "_service_post", side_effect=post),
        ):
            result = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["createdOrderUuids"], [ORDER])
        self.assertEqual(len(posts), 1)
        path, payload = posts[0]
        self.assertEqual(path, schedules.SCHEDULE_PATH)
        self.assertEqual(payload["patientUuid"], PATIENT)
        self.assertEqual(payload["orderUuid"], ORDER)
        self.assertEqual(payload["providerUuid"], PROVIDER)
        self.assertEqual(
            payload["slotStartTime"],
            schedules.mar._epoch_seconds("2026-08-30T10:05:00.000+0000"),
        )
        self.assertEqual(payload["medicationFrequency"], "START_TIME_DURATION_FREQUENCY")
        self.assertEqual(payload["serviceType"], "MEDICATION_REQUEST")

    def test_retry_and_already_created_are_idempotent(self) -> None:
        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "nurse-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=admission()),
            patch.object(schedules, "_load_visit_orders", return_value=[ipd_order()]),
            patch.object(
                schedules,
                "_existing_slots",
                return_value=[{"uuid": SLOT, "startTime": 1788084300}],
            ),
            patch.object(schedules, "_service_post") as post,
        ):
            first = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=nurse")
            second = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=nurse")
        post.assert_not_called()
        self.assertEqual(first["alreadyScheduledOrderUuids"], [ORDER])
        self.assertEqual(second["alreadyScheduledOrderUuids"], [ORDER])
        self.assertEqual(first["createdOrderUuids"], [])

    def test_bahmni_already_created_error_is_treated_as_success(self) -> None:
        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=admission()),
            patch.object(schedules, "_load_visit_orders", return_value=[ipd_order()]),
            patch.object(
                schedules,
                "_existing_slots",
                side_effect=[[], [{"uuid": SLOT}]],
            ),
            patch.object(
                schedules,
                "_service_post",
                return_value=(
                    400,
                    {"error": {"message": "Slots already created for this drug order"}},
                ),
            ),
        ):
            result = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(result["alreadyScheduledOrderUuids"], [ORDER])
        self.assertEqual(result["issues"], [])

    def test_failed_schedule_does_not_look_ready(self) -> None:
        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=admission()),
            patch.object(schedules, "_load_visit_orders", return_value=[ipd_order()]),
            patch.object(schedules, "_existing_slots", return_value=[]),
            patch.object(schedules, "_service_post", return_value=(500, {"error": {"message": "down"}})),
        ):
            result = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["createdOrderUuids"], [])
        self.assertEqual(result["issues"][0]["code"], "schedule_create_failed")
        with self.assertRaises(ApiError) as raised:
            with (
                patch.object(
                    schedules.ward,
                    "require_inpatient_view",
                    return_value={"uuid": "doctor-user"},
                ),
                patch.object(schedules.ward, "_active_admission", return_value=admission()),
                patch.object(schedules, "_load_visit_orders", return_value=[ipd_order()]),
                patch.object(schedules, "_existing_slots", return_value=[]),
                patch.object(
                    schedules,
                    "_service_post",
                    return_value=(500, {"error": {"message": "down"}}),
                ),
            ):
                schedules.create_medication_schedules(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(raised.exception.status, 502)
        self.assertEqual(raised.exception.code, "schedule_create_failed")

    def test_as_needed_and_missing_dose_are_rejected(self) -> None:
        prn = ipd_order(asNeeded=True, uuid="prn-1")
        no_dose = ipd_order(dose=0, uuid="nodose-1")
        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=admission()),
            patch.object(schedules, "_load_visit_orders", return_value=[prn, no_dose]),
            patch.object(schedules, "_service_post") as post,
        ):
            result = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=doctor")
        post.assert_not_called()
        codes = {item["code"] for item in result["issues"]}
        self.assertEqual(codes, {"as_needed_not_scheduled", "dose_required"})

    def test_discharged_patient_cannot_receive_new_schedules(self) -> None:
        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=None),
        ):
            with self.assertRaises(ApiError) as raised:
                schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=doctor")
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(raised.exception.code, "not_admitted")

    def test_other_patient_order_is_not_scheduled(self) -> None:
        foreign = ipd_order(patient={"uuid": "patient-2"})
        with (
            patch.object(
                schedules.ward,
                "require_inpatient_view",
                return_value={"uuid": "doctor-user"},
            ),
            patch.object(schedules.ward, "_active_admission", return_value=admission()),
            patch.object(schedules, "_load_visit_orders", return_value=[foreign]),
            patch.object(schedules, "_service_post") as post,
        ):
            result = schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=doctor")
        post.assert_not_called()
        self.assertEqual(result["issues"][0]["code"], "order_patient_mismatch")

    def test_slot_start_uses_order_activation_not_an_eligible_window(self) -> None:
        request = schedules._schedule_request(ipd_order(), PATIENT)
        self.assertEqual(request["slotStartTime"], 1788084300)

    def test_loads_visit_orders_when_full_order_omits_visit(self) -> None:
        payload = {
            "visitDrugOrders": [
                {
                    "uuid": "wrapper-1",
                    "visit": {"uuid": VISIT},
                    "drugOrder": {"uuid": ORDER, "orderNumber": "ORD-41"},
                }
            ]
        }
        order_without_visit = ipd_order()
        order_without_visit["encounter"] = {"uuid": "enc-1"}

        def service_get(path: str):
            if "prescribedAndActive" in path:
                return payload
            if ORDER in path:
                return order_without_visit
            raise AssertionError(path)

        with patch.object(schedules.core, "openmrs_service_get", side_effect=service_get):
            rows = schedules._load_visit_orders(PATIENT, VISIT)
        self.assertEqual([row["uuid"] for row in rows], [ORDER])

    def test_unauthorized_role_cannot_create_schedule(self) -> None:
        denial = ApiError(403, "forbidden", "Denied")
        with patch.object(schedules.ward, "require_inpatient_view", side_effect=denial):
            with self.assertRaises(ApiError) as raised:
                schedules.ensure_medication_schedules(PATIENT, "JSESSIONID=lab")
        self.assertEqual(raised.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
