import json
import unittest
from unittest.mock import patch

import nursing_treatment as treatment


PATIENT = "patient-1"
VISIT = "visit-1"
ORDER = "order-1"


def order(mode: str = "HOSPITAL_FOLLOW_UP") -> dict:
    return {
        "uuid": ORDER,
        "orderNumber": "ORD-1",
        "drug": {"uuid": "drug-1", "display": "Ceftriaxone"},
        "route": {"display": "Injection"},
        "frequency": {"display": "Once a day"},
        "duration": 3,
        "durationUnits": "Days",
        "dosingInstructions": {
            "administrationInstructions": json.dumps(
                {"instructions": "Give slowly and observe for 30 minutes.", "administrationMode": mode}
            )
        },
    }


def visit() -> dict:
    return {
        "uuid": VISIT,
        "patient": {"uuid": PATIENT, "display": "Ada Patient"},
        "visitType": {"name": "Nursing Treatment"},
        "startDatetime": "2026-09-12T08:00:00.000+0000",
    }


class NursingTreatmentTests(unittest.TestCase):
    @patch.object(treatment, "_existing_administrations", return_value=set())
    @patch.object(treatment, "_treatment_notes", return_value=[])
    @patch.object(treatment, "_load_orders", return_value=[order(), order("HOME")])
    @patch.object(treatment, "_load_treatment_visits", return_value=[visit()])
    @patch.object(treatment.ward, "require_nursing_user", return_value={"uuid": "nurse-user"})
    def test_queue_only_contains_hospital_follow_up_orders(
        self, _require, _visits, _orders, _notes, _existing
    ):
        result = treatment.build_treatment_queue("cookie")

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["medication"], "Ceftriaxone")
        self.assertEqual(result["items"][0]["status"], "DUE")

    @patch.object(treatment.core, "openmrs_service_post", return_value={"encounterUuid": "encounter-1"})
    @patch.object(treatment.ward, "_provider_uuid", return_value="provider-1")
    @patch.object(
        treatment.ward,
        "_authenticated_nurse_identity",
        return_value={
            "userUuid": "nurse-user",
            "personUuid": "person-1",
            "authorName": "Nurse Ada",
        },
    )
    @patch.object(
        treatment,
        "_existing_administrations",
        side_effect=[set(), {treatment._administration_key(VISIT, ORDER)}],
    )
    @patch.object(
        treatment,
        "_load_visit_detail",
        return_value={
            "location": {"uuid": "location-1"},
            "encounters": [{"uuid": "encounter-1", "encounterDatetime": "2026-09-12T08:00:00.000+0000"}],
        },
    )
    @patch.object(treatment, "_load_orders", return_value=[order()])
    @patch.object(treatment, "_load_treatment_visits", return_value=[visit()])
    @patch.object(treatment.ward, "require_nursing_user", return_value={"uuid": "nurse-user"})
    def test_records_existing_order_against_treatment_visit(
        self, _require, _visits, _orders, _load_detail, _existing, _identity, _provider, post
    ):
        result = treatment.record_treatment(
            PATIENT,
            {"visitUuid": VISIT, "orderUuid": ORDER, "outcome": "given", "reason": ""},
            "cookie",
        )

        self.assertEqual(result["status"], "ok")
        payload = post.call_args.args[1]
        self.assertEqual(payload["encounter"], "encounter-1")
        self.assertEqual(payload["person"], PATIENT)
        self.assertIn(treatment.TREATMENT_ADMIN_MARKER, payload["comment"])


if __name__ == "__main__":
    unittest.main()
