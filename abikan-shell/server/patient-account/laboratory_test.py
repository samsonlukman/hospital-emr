"""Laboratory P0 correctness guards — mocked only, no clinical writes."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import hospital_admin
import lab_catalogue
import laboratory
from server import ApiError


def order(
    uuid: str,
    *,
    concept: str = "concept-mp",
    encounter: str = "encounter-1",
) -> dict[str, str]:
    return {
        "uuid": uuid,
        "conceptUuid": concept,
        "encounterUuid": encounter,
    }


class OpenElisWorklistStatusTests(unittest.TestCase):
    def test_finalized_openelis_result_is_completed(self) -> None:
        row = order("order-1")
        state = laboratory._laboratory_state(
            row,
            [row],
            [{"testUuid": "concept-mp", "status": "Results final", "result": "Negative"}],
            {"order-1"},
        )
        self.assertEqual(state["stage"], "completed")
        self.assertEqual(state["laboratoryStatus"], "Results final")
        self.assertTrue(state["hasResult"])
        self.assertEqual(state["resultMapping"], "unique")

    def test_missing_openelis_details_still_show_as_pending(self) -> None:
        row = order("order-1")
        state = laboratory._laboratory_state(row, [row], None, set())
        self.assertEqual(state["stage"], "pending")
        self.assertEqual(state["laboratoryStatus"], "Awaiting laboratory receipt")
        self.assertFalse(state["hasResult"])

    def test_openelis_status_is_authoritative(self) -> None:
        row = {
            **order("order-1"),
            # OpenMRS currently contains the encounter UUID in this field. It
            # must not influence laboratory stage.
            "accession": "encounter-1",
        }
        state = laboratory._laboratory_state(
            row,
            [row],
            [{"testUuid": "concept-mp", "status": "Testing Started"}],
            {"order-1"},
        )
        self.assertEqual(state["stage"], "processing")
        self.assertEqual(state["laboratoryStatus"], "Testing Started")
        self.assertFalse(state["hasResult"])

    def test_unknown_openelis_status_is_not_invented(self) -> None:
        row = order("order-1")
        state = laboratory._laboratory_state(
            row,
            [row],
            [{"testUuid": "concept-mp", "status": "Site-specific state"}],
            set(),
        )
        self.assertEqual(state["stage"], "unknown")
        self.assertEqual(state["laboratoryStatus"], "Site-specific state")


class DuplicateOrderSafetyTests(unittest.TestCase):
    def test_future_duplicate_on_same_consultation_is_rejected(self) -> None:
        with self.assertRaises(ApiError) as caught:
            laboratory._guard_duplicate_test_order(
                "concept-mp",
                "encounter-1",
                [order("existing-order")],
                set(),
            )
        self.assertEqual(caught.exception.code, "duplicate_lab_test")

    def test_same_test_on_a_different_consultation_is_not_collapsed(self) -> None:
        laboratory._guard_duplicate_test_order(
            "concept-mp",
            "encounter-2",
            [order("existing-order", encounter="encounter-1")],
            set(),
        )

    def test_duplicate_orders_remain_separate_and_mapping_is_ambiguous(self) -> None:
        first = order("order-1")
        second = order("order-2")
        details = [
            {"testUuid": "concept-mp", "status": "Results final", "result": "Negative"}
        ]
        first_state = laboratory._laboratory_state(
            first, [first, second], details, {"order-1"}
        )
        second_state = laboratory._laboratory_state(
            second, [first, second], details, set()
        )
        self.assertNotEqual(first["uuid"], second["uuid"])
        for state in (first_state, second_state):
            self.assertEqual(state["stage"], "completed")
            self.assertEqual(state["resultMapping"], "ambiguous")
            self.assertFalse(state["hasResult"])
            self.assertIn("duplicate", state["statusMessage"].lower())

    def test_unique_concept_mapping_continues_to_work(self) -> None:
        first = order("order-1", concept="concept-mp")
        second = order("order-2", concept="concept-urine")
        details = [
            {"testUuid": "concept-mp", "status": "Results final", "result": "Negative"},
            {"testUuid": "concept-urine", "status": "Not started", "result": None},
        ]
        first_state = laboratory._laboratory_state(
            first, [first, second], details, {"order-1"}
        )
        second_state = laboratory._laboratory_state(
            second, [first, second], details, set()
        )
        self.assertEqual(first_state["resultMapping"], "unique")
        self.assertTrue(first_state["hasResult"])
        self.assertEqual(second_state["resultMapping"], "unique")
        self.assertEqual(second_state["stage"], "pending")


class CatalogueSafetyTests(unittest.TestCase):
    def test_unsafe_same_name_drug_concepts_are_not_orderable(self) -> None:
        affected = {
            "42": "Inorganic Phosphate",
            "56": "Testosterone",
            "57": "Progesterone",
            "58": "Estradiol",
        }
        entries = {row["sn"]: row for row in lab_catalogue.catalogue_entries()}
        runtime = lab_catalogue.load_runtime()
        for sn, name in affected.items():
            with self.subTest(name=name):
                self.assertEqual(entries[sn]["action"], "skip")
                self.assertFalse(entries[sn]["orderable"])
                self.assertFalse(entries[sn]["conceptUuid"])
                self.assertNotIn(sn, runtime)
                self.assertIn("Unavailable", entries[sn]["note"])

    def test_safe_existing_test_mapping_remains_orderable(self) -> None:
        complete_blood_count = next(
            row for row in lab_catalogue.catalogue_entries() if row["sn"] == "1"
        )
        self.assertTrue(complete_blood_count["orderable"])
        self.assertIn(complete_blood_count["conceptClass"], {"Test", "LabSet"})


class LaboratoryRoleSafetyTests(unittest.TestCase):
    @staticmethod
    def _roles() -> list[dict]:
        script = Path(__file__).parents[2] / "scripts" / "provision-dev-users.py"
        spec = importlib.util.spec_from_file_location("provision_dev_users_lab", script)
        assert spec
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        return module.ROLES

    def test_laboratory_role_does_not_inherit_user_management(self) -> None:
        role = next(
            item for item in self._roles() if item["name"] == "Abikan:Laboratory"
        )
        self.assertEqual(role["inherited"], ["Lab"])
        self.assertNotIn("Edit Users", role["privileges"])
        self.assertNotIn("Get Users", role["privileges"])
        self.assertIn("Get Encounters", role["privileges"])
        self.assertIn("Get Visits", role["privileges"])
        self.assertIn("View Patients", role["privileges"])

    def test_unrelated_department_role_definitions_are_unchanged(self) -> None:
        roles = {item["name"]: item for item in self._roles()}
        self.assertEqual(roles["Abikan:Doctor"]["inherited"], ["Clinical-App", "Provider"])
        self.assertEqual(roles["Abikan:Nursing"]["inherited"], ["InPatient-App"])
        self.assertEqual(roles["Abikan:Radiology"]["inherited"], ["Radiology-App"])
        self.assertEqual(
            roles["Abikan:Pharmacy"]["inherited"], ["Bahmni-App-User-Login"]
        )

    def test_laboratory_identity_is_denied_by_admin_backend(self) -> None:
        self.assertFalse(
            hospital_admin.is_hospital_admin(
                {
                    "roles": ["Abikan:Laboratory"],
                    "privileges": [
                        "app:lab-lite",
                        "Get Orders",
                        "Get Patients",
                        "Get Encounters",
                    ],
                }
            )
        )


class BuildLabOrderTests(unittest.TestCase):
    @staticmethod
    def _order(uuid: str, *, patient: str = "patient-1", visit: str = "visit-1") -> dict[str, str]:
        return {
            "uuid": uuid,
            "orderNumber": "ORD-9" if uuid == "order-9" else "ORD-10",
            "testName": "Malarial smear",
            "conceptUuid": "concept-mp",
            "patientUuid": patient,
            "visitUuid": visit,
            "encounterUuid": "encounter-1",
            "patientName": "Test Patient",
            "mrn": "ABC200016",
            "ordered": "2026-08-19",
            "urgency": "Routine",
            "accession": "",
            "provider": "Doctor Hospital EMR",
            "comment": "",
        }

    def test_valid_lab_order_returns_exact_identity(self) -> None:
        loaded = self._order("order-9")
        with (
            patch.object(laboratory, "require_lab_user"),
            patch.object(laboratory, "load_lab_order", return_value=loaded) as load,
        ):
            payload = laboratory.build_lab_order("order-9", "patient-1", "visit-1", "cookie")
        load.assert_called_once_with("order-9", "patient-1", "cookie")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["order"]["uuid"], "order-9")
        self.assertEqual(payload["order"]["patientUuid"], "patient-1")
        self.assertEqual(payload["order"]["visitUuid"], "visit-1")

    def test_invalid_order_uuid_is_not_found(self) -> None:
        with (
            patch.object(laboratory, "require_lab_user"),
            patch.object(
                laboratory,
                "load_lab_order",
                side_effect=ApiError(404, "order_not_found", "This laboratory order was not found."),
            ),
        ):
            with self.assertRaises(ApiError) as caught:
                laboratory.build_lab_order("missing-order", "patient-1", "visit-1", "cookie")
            self.assertEqual(caught.exception.code, "order_not_found")

    def test_wrong_patient_is_rejected(self) -> None:
        with (
            patch.object(laboratory, "require_lab_user"),
            patch.object(
                laboratory,
                "load_lab_order",
                side_effect=ApiError(
                    409,
                    "wrong_patient",
                    "This laboratory order does not belong to this patient.",
                ),
            ),
        ):
            with self.assertRaises(ApiError) as caught:
                laboratory.build_lab_order("order-9", "other-patient", "visit-1", "cookie")
            self.assertEqual(caught.exception.code, "wrong_patient")

    def test_wrong_visit_is_rejected(self) -> None:
        loaded = self._order("order-9")
        with (
            patch.object(laboratory, "require_lab_user"),
            patch.object(laboratory, "load_lab_order", return_value=loaded),
        ):
            with self.assertRaises(ApiError) as caught:
                laboratory.build_lab_order("order-9", "patient-1", "visit-2", "cookie")
            self.assertEqual(caught.exception.code, "wrong_visit")

    def test_duplicate_same_test_orders_remain_distinct(self) -> None:
        first = self._order("order-9")
        second = self._order("order-10")
        with patch.object(laboratory, "require_lab_user"):
            with patch.object(laboratory, "load_lab_order", return_value=first):
                payload_first = laboratory.build_lab_order("order-9", "patient-1", "visit-1", "cookie")
            with patch.object(laboratory, "load_lab_order", return_value=second):
                payload_second = laboratory.build_lab_order("order-10", "patient-1", "visit-1", "cookie")
        self.assertNotEqual(payload_first["order"]["uuid"], payload_second["order"]["uuid"])
        self.assertEqual(payload_first["order"]["orderNumber"], "ORD-9")
        self.assertEqual(payload_second["order"]["orderNumber"], "ORD-10")

    def test_non_lab_user_is_rejected(self) -> None:
        with patch.object(
            laboratory,
            "require_lab_user",
            side_effect=ApiError(403, "forbidden", "This action requires the Laboratory workspace."),
        ):
            with self.assertRaises(ApiError) as caught:
                laboratory.build_lab_order("order-9", "patient-1", "visit-1", "cookie")
            self.assertEqual(caught.exception.code, "forbidden")

    def test_response_never_exposes_openelis_credentials(self) -> None:
        loaded = self._order("order-9")
        with (
            patch.object(laboratory, "require_lab_user"),
            patch.object(laboratory, "load_lab_order", return_value=loaded),
        ):
            payload = laboratory.build_lab_order("order-9", "patient-1", "visit-1", "cookie")
        encoded = str(payload).lower()
        self.assertNotIn("openelis", encoded)
        self.assertNotIn("password", encoded)
        self.assertNotIn("loginname", encoded)


if __name__ == "__main__":
    unittest.main()
