"""Hospital laboratory catalogue management tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lab_catalogue
import laboratory_manage as manage
from server import ApiError


class ManagedCatalogueEnableTests(unittest.TestCase):
    def test_managed_overlay_becomes_orderable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "managed.json"
            with patch.object(lab_catalogue, "_managed_path", return_value=path):
                lab_catalogue.append_managed_item(
                    {
                        "sn": "M-PROBE-abcdef",
                        "conceptUuid": "concept-managed-probe",
                        "hospitalName": "Managed Probe Test",
                        "openmrsName": "Managed Probe Test",
                        "conceptClass": "Test",
                        "department": "Laboratory",
                        "type": "Test",
                        "specimen": "Blood",
                        "enabled": True,
                    }
                )
                entry = lab_catalogue.entry_by_concept("concept-managed-probe")
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertTrue(entry["orderable"])
                self.assertEqual(entry["hospitalName"], "Managed Probe Test")

    def test_disabled_concept_is_not_orderable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "managed.json"
            with patch.object(lab_catalogue, "_managed_path", return_value=path):
                lab_catalogue.save_managed_store(
                    {
                        "items": [
                            {
                                "conceptUuid": "concept-disabled",
                                "hospitalName": "Disabled Probe",
                                "openmrsName": "Disabled Probe",
                                "conceptClass": "Test",
                                "enabled": True,
                            }
                        ],
                        "disabledConceptUuids": ["concept-disabled"],
                    }
                )
                self.assertIsNone(lab_catalogue.entry_by_concept("concept-disabled"))


class HospitalTestManageTests(unittest.TestCase):
    def test_enable_adds_immediately_and_duplicate_is_already_available(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "managed.json"
            lab_user = {
                "uuid": "u-lab",
                "username": "lab.abikan",
                "roles": ["Abikan:Laboratory"],
                "privileges": ["app:lab-lite"],
            }
            concept = {
                "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "display": "Hospital EMR Master Malaria Probe",
                "retired": False,
                "conceptClass": {"display": "Test"},
                "names": [
                    {"name": "Hospital EMR Master Malaria Probe", "conceptNameType": "FULLY_SPECIFIED"},
                    {"name": "Malaria Probe", "conceptNameType": "SHORT"},
                ],
            }
            with (
                patch.object(lab_catalogue, "_managed_path", return_value=path),
                patch.object(manage, "require_hospital_test_manager", return_value=lab_user),
                patch.object(
                    manage.pricing,
                    "_actor",
                    return_value={
                        "uuid": "u-lab",
                        "username": "lab.abikan",
                        "display": "Lab Hospital EMR",
                    },
                ),
                patch.object(manage, "load_master_concept", return_value=concept),
                patch.object(manage, "_ensure_orderable_member"),
                patch.object(manage, "_ensure_fee_product_available"),
            ):
                first = manage.enable_hospital_test(
                    {"conceptUuid": concept["uuid"]},
                    "cookie",
                )
                self.assertFalse(first["alreadyEnabled"])
                self.assertIn("added", first["message"].lower())
                self.assertEqual(first["test"]["conceptUuid"], concept["uuid"])
                self.assertIsNotNone(lab_catalogue.entry_by_concept(concept["uuid"]))

                second = manage.enable_hospital_test(
                    {"conceptUuid": concept["uuid"]},
                    "cookie",
                )
                self.assertTrue(second["alreadyEnabled"])
                self.assertEqual(second["message"], "Already available")

    def test_disable_removes_from_ordering_only(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "managed.json"
            lab_user = {
                "uuid": "u-lab",
                "username": "lab.abikan",
                "roles": [],
                "privileges": ["app:lab-lite"],
            }
            concept_uuid = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
            with patch.object(lab_catalogue, "_managed_path", return_value=path):
                lab_catalogue.save_managed_store(
                    {
                        "items": [
                            {
                                "conceptUuid": concept_uuid,
                                "hospitalName": "Removable Probe",
                                "openmrsName": "Removable Probe",
                                "conceptClass": "LabSet",
                                "type": "Panel",
                                "enabled": True,
                            }
                        ],
                        "disabledConceptUuids": [],
                    }
                )
                self.assertIsNotNone(lab_catalogue.entry_by_concept(concept_uuid))
                with (
                    patch.object(manage, "require_hospital_test_manager", return_value=lab_user),
                    patch.object(manage, "_remove_orderable_member") as remove_member,
                ):
                    result = manage.disable_hospital_test(concept_uuid, "cookie")
                self.assertIn("removed", result["message"].lower())
                self.assertIsNone(lab_catalogue.entry_by_concept(concept_uuid))
                remove_member.assert_called_once()
                store = lab_catalogue.load_managed_store()
                self.assertIn(concept_uuid, store["disabledConceptUuids"])

    def test_direct_create_laboratory_test_is_forbidden(self) -> None:
        with self.assertRaises(ApiError) as caught:
            manage.create_laboratory_test({"name": "Invented Test", "price": 100}, "cookie")
        self.assertEqual(caught.exception.code, "test_create_forbidden")
        self.assertIn("master catalogue", caught.exception.message.lower())

    def test_master_search_filters_to_tests_and_panels(self) -> None:
        lab_user = {
            "uuid": "u-lab",
            "username": "lab.abikan",
            "roles": [],
            "privileges": ["app:lab-lite"],
        }
        payload = {
            "results": [
                {
                    "uuid": "test-1",
                    "display": "Malaria Parasite",
                    "retired": False,
                    "conceptClass": {"display": "Test"},
                    "names": [{"name": "Malaria Parasite"}],
                },
                {
                    "uuid": "drug-1",
                    "display": "Malaria Medicine",
                    "retired": False,
                    "conceptClass": {"display": "Drug"},
                    "names": [{"name": "Malaria Medicine"}],
                },
                {
                    "uuid": "panel-1",
                    "display": "Malaria Panel",
                    "retired": False,
                    "conceptClass": {"display": "LabSet"},
                    "names": [{"name": "Malaria Panel"}],
                },
            ]
        }
        with (
            patch.object(manage, "require_hospital_test_manager", return_value=lab_user),
            patch.object(manage, "_openmrs", return_value=payload),
            patch.object(manage, "_enabled_concept_uuids", return_value={"test-1"}),
        ):
            result = manage.search_master_tests("cookie", "malaria")
        names = [row["name"] for row in result["tests"]]
        self.assertEqual(names, ["Malaria Parasite", "Malaria Panel"])
        self.assertTrue(result["tests"][0]["alreadyEnabled"])
        self.assertEqual(result["tests"][0]["type"], "Test")
        self.assertEqual(result["tests"][1]["type"], "Panel")
        self.assertFalse(result["tests"][1]["alreadyEnabled"])


if __name__ == "__main__":
    unittest.main()
