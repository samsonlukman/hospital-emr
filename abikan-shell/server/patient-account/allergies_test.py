from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import allergies
import inpatient
from server import ApiError


PATIENT = "8c14a0dd-d509-4a0d-afcd-251b76fc1b5e"
ALLERGY = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
COOKIE = "JSESSIONID=clinical"

NURSE = {"uuid": "nurse-1", "privileges": [inpatient.ADT_PRIVILEGE], "roles": ["Abikan:Nursing"]}
DOCTOR = {"uuid": "doc-1", "privileges": [inpatient.CLINICAL_PRIVILEGE], "roles": ["Abikan:Doctor"]}
PHARMACY = {"uuid": "pharm-1", "privileges": ["app:pharmacy"], "roles": ["Abikan:Pharmacy"]}
ACCOUNTANT = {"uuid": "acc-1", "privileges": ["app:cashier"], "roles": ["Abikan:Accountant"]}


def openmrs_row() -> dict[str, object]:
    return {
        "uuid": ALLERGY,
        "display": "Penicillin",
        "allergen": {
            "allergenType": "DRUG",
            "codedAllergen": {"uuid": "concept-1", "display": "Penicillin"},
        },
        "severity": {"uuid": allergies.SEVERITY_CONCEPTS["SEVERE"], "display": "Severe"},
        "comment": "Noted at admission",
        "reactions": [{"reaction": {"display": "Rash"}}],
    }


class AllergySerializerTests(unittest.TestCase):
    def test_reads_allergen_reaction_and_severity(self) -> None:
        row = allergies.serialize_allergy(openmrs_row())
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["allergen"], "Penicillin")
        self.assertEqual(row["severity"], "Severe")
        self.assertEqual(row["reactions"], ["Rash"])
        self.assertEqual(row["display"], "Penicillin (Severe — Rash)")

    def test_prefers_free_text_over_other_non_coded_label(self) -> None:
        row = allergies.serialize_allergy(
            {
                "uuid": ALLERGY,
                "display": "UATFIX Hospital EMR Mango",
                "allergen": {
                    "allergenType": "FOOD",
                    "codedAllergen": {
                        "uuid": allergies.OTHER_NON_CODED_CONCEPT,
                        "display": "Other",
                    },
                    "nonCodedAllergen": "UATFIX Hospital EMR Mango",
                },
                "reactions": [
                    {
                        "reaction": {"uuid": allergies.OTHER_NON_CODED_CONCEPT, "display": "Other"},
                        "reactionNonCoded": "itchy eyes",
                    }
                ],
            }
        )
        assert row is not None
        self.assertEqual(row["allergen"], "UATFIX Hospital EMR Mango")
        self.assertEqual(row["reactions"], ["itchy eyes"])
        self.assertNotEqual(row["allergen"], "Other")

    def test_reads_non_coded_allergen(self) -> None:
        row = allergies.serialize_allergy(
            {
                "uuid": ALLERGY,
                "allergen": {"allergenType": "FOOD", "nonCodedAllergen": "Peanuts"},
            }
        )
        assert row is not None
        self.assertEqual(row["allergen"], "Peanuts")
        self.assertEqual(row["allergenType"], "FOOD")


class AllergyAccessTests(unittest.TestCase):
    def test_nurse_and_doctor_may_write_pharmacy_and_accountant_may_not(self) -> None:
        self.assertTrue(allergies._can_write_allergies(NURSE))
        self.assertTrue(allergies._can_write_allergies(DOCTOR))
        self.assertFalse(allergies._can_write_allergies(PHARMACY))
        self.assertFalse(allergies._can_write_allergies(ACCOUNTANT))

    def test_pharmacist_cannot_create_an_allergy(self) -> None:
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=PHARMACY),
        ):
            with self.assertRaises(ApiError) as raised:
                allergies.create_allergy(PATIENT, {"allergenType": "OTHER", "allergenName": "Dust"}, COOKIE)
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(raised.exception.code, "forbidden")

    def test_accountant_cannot_void_an_allergy(self) -> None:
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=ACCOUNTANT),
        ):
            with self.assertRaises(ApiError) as raised:
                allergies.void_allergy(PATIENT, ALLERGY, COOKIE)
        self.assertEqual(raised.exception.status, 403)


class AllergyPayloadTests(unittest.TestCase):
    def test_free_text_requires_other_non_coded_concept(self) -> None:
        fields = allergies._validated_write(
            {"allergenType": "FOOD", "allergenName": "Peanuts", "reaction": "itchy eyes"}
        )
        with patch.object(allergies, "_resolve_reaction_concept", return_value=""):
            payload = allergies._openmrs_write_body(fields, COOKIE)
            attempts = allergies._write_attempts(fields, COOKIE)
        self.assertEqual(payload["allergen"]["allergenType"], "FOOD")
        self.assertEqual(payload["allergen"]["codedAllergen"]["uuid"], allergies.OTHER_NON_CODED_CONCEPT)
        self.assertEqual(payload["allergen"]["nonCodedAllergen"], "Peanuts")
        self.assertEqual(
            payload["reactions"],
            [
                {
                    "reaction": {"uuid": allergies.OTHER_NON_CODED_CONCEPT},
                    "reactionNonCoded": "itchy eyes",
                }
            ],
        )
        for attempt in attempts:
            self.assertIn("uuid", attempt["allergen"]["codedAllergen"])

    def test_coded_medicine_does_not_send_non_coded_allergen(self) -> None:
        fields = allergies._validated_write(
            {
                "allergenType": "DRUG",
                "allergenName": "Penicillin",
                "codedAllergenUuid": "11111111-1111-1111-1111-111111111111",
            }
        )
        payload = allergies._openmrs_write_body(fields, COOKIE)
        self.assertEqual(payload["allergen"]["codedAllergen"]["uuid"], "11111111-1111-1111-1111-111111111111")
        self.assertNotIn("nonCodedAllergen", payload["allergen"])

    def test_known_reaction_uses_the_matching_concept(self) -> None:
        fields = allergies._validated_write(
            {"allergenType": "OTHER", "allergenName": "Dust", "reaction": "Rash"}
        )
        with patch.object(
            allergies,
            "_resolve_reaction_concept",
            return_value="512AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        ):
            payload = allergies._openmrs_write_body(fields, COOKIE)
        self.assertEqual(
            payload["reactions"],
            [{"reaction": {"uuid": "512AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}}],
        )

    def test_missing_coded_allergen_error_is_not_a_generic_cannot_create(self) -> None:
        message = allergies._staff_allergy_error(
            "not-null property references a null or transient value : org.openmrs.Allergy.allergen.codedAllergen"
        )
        self.assertNotEqual(message.lower(), "cannot create allergy")
        self.assertIn("substance", message.lower())

    def test_html_500_returns_a_staff_message(self) -> None:
        message = allergies._staff_allergy_error("<html><h1>Internal Server Error</h1></html>")
        self.assertEqual(message, "The allergy could not be saved on the patient chart. Try again.")
        self.assertNotIn("Cannot create allergy", message)


class AllergyWriteTests(unittest.TestCase):
    def test_create_posts_to_openmrs_patient_allergy_and_does_not_store_locally(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_call(method: str, path: str, cookie: str, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return {"results": [openmrs_row()]}
            return {"uuid": ALLERGY}

        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=NURSE),
            patch.object(allergies.ward, "_patient_brief", return_value={"uuid": PATIENT}),
            patch.object(allergies, "_openmrs_allergy_call", side_effect=fake_call),
            patch.object(allergies, "_resolve_reaction_concept", return_value="512AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"),
        ):
            payload = allergies.create_allergy(
                PATIENT,
                {
                    "allergenType": "DRUG",
                    "allergenName": "Penicillin",
                    "codedAllergenUuid": "11111111-1111-1111-1111-111111111111",
                    "severity": "SEVERE",
                    "reaction": "Rash",
                    "comment": "Noted at admission",
                },
                COOKIE,
            )
        post = next(row for row in calls if row[0] == "POST")
        self.assertEqual(post[1], f"/openmrs/ws/rest/v1/patient/{PATIENT}/allergy")
        self.assertEqual(post[2]["allergen"]["allergenType"], "DRUG")
        self.assertEqual(post[2]["allergen"]["codedAllergen"]["uuid"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(payload["allergies"][0]["uuid"], ALLERGY)
        self.assertTrue(payload["canWrite"])

    def test_create_retries_when_openmrs_rejects_the_first_payload(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_call(method: str, path: str, cookie: str, body=None):
            if method == "GET":
                return {"results": [openmrs_row()]}
            calls.append(body or {})
            if len(calls) == 1:
                raise ApiError(
                    502,
                    "openmrs_error",
                    "not-null property references a null or transient value : org.openmrs.Allergy.allergen.codedAllergen",
                )
            return {"uuid": ALLERGY}

        fields = {
            "allergenType": "FOOD",
            "allergenName": "Peanuts",
            "severity": "MILD",
        }
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=DOCTOR),
            patch.object(allergies.ward, "_patient_brief", return_value={"uuid": PATIENT}),
            patch.object(allergies, "_openmrs_allergy_call", side_effect=fake_call),
        ):
            allergies.create_allergy(PATIENT, fields, COOKIE)
        self.assertGreaterEqual(len(calls), 2)
        for body in calls:
            self.assertIn("codedAllergen", body["allergen"])

    def test_update_posts_to_the_same_patient_allergy_with_coded_allergen(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_call(method: str, path: str, cookie: str, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return {"results": [openmrs_row()]}
            return {"uuid": ALLERGY}

        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=DOCTOR),
            patch.object(allergies.ward, "_patient_brief", return_value={"uuid": PATIENT}),
            patch.object(allergies, "_openmrs_allergy_call", side_effect=fake_call),
        ):
            allergies.update_allergy(
                PATIENT,
                ALLERGY,
                {"allergenType": "OTHER", "allergenName": "Dust", "comment": "updated"},
                COOKIE,
            )
        post = next(row for row in calls if row[0] == "POST")
        self.assertEqual(post[1], f"/openmrs/ws/rest/v1/patient/{PATIENT}/allergy/{ALLERGY}")
        self.assertEqual(post[2]["allergen"]["codedAllergen"]["uuid"], allergies.OTHER_NON_CODED_CONCEPT)
        self.assertEqual(post[2]["allergen"]["nonCodedAllergen"], "Dust")

    def test_update_refuses_another_patient_allergy(self) -> None:
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=DOCTOR),
            patch.object(allergies.ward, "_patient_brief", return_value={"uuid": PATIENT}),
            patch.object(allergies, "list_openmrs_allergies", return_value=[]),
        ):
            with self.assertRaises(ApiError) as raised:
                allergies.update_allergy(
                    PATIENT,
                    ALLERGY,
                    {"allergenType": "OTHER", "allergenName": "Dust"},
                    COOKIE,
                )
        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(raised.exception.code, "not_found")

    def test_void_deletes_only_the_matching_patient_allergy(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_call(method: str, path: str, cookie: str, body=None, allow_empty=False):
            calls.append((method, path))
            if method == "GET":
                return {"results": [openmrs_row()]}
            return {}

        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=DOCTOR),
            patch.object(allergies.ward, "_patient_brief", return_value={"uuid": PATIENT}),
            patch.object(allergies, "_openmrs_allergy_call", side_effect=fake_call),
        ):
            allergies.void_allergy(PATIENT, ALLERGY, COOKIE)
        self.assertIn(
            ("DELETE", f"/openmrs/ws/rest/v1/patient/{PATIENT}/allergy/{ALLERGY}"),
            calls,
        )

    def test_rejects_invalid_patient_and_empty_allergen(self) -> None:
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=NURSE),
        ):
            with self.assertRaises(ApiError) as raised:
                allergies.create_allergy("not-a-uuid", {"allergenType": "OTHER", "allergenName": "Dust"}, COOKIE)
            self.assertEqual(raised.exception.code, "invalid_patient")
            with self.assertRaises(ApiError) as raised:
                allergies.create_allergy(PATIENT, {"allergenType": "OTHER", "allergenName": "  "}, COOKIE)
            self.assertEqual(raised.exception.code, "allergen_required")

    def test_list_marks_writer_capability_from_role(self) -> None:
        pharmacy_reader = {**PHARMACY, "privileges": ["bahmni:clinical:dispense"]}
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=pharmacy_reader),
            patch.object(allergies.ward, "_patient_brief", return_value={"uuid": PATIENT}),
            patch.object(allergies, "list_openmrs_allergies", return_value=[]),
        ):
            payload = allergies.list_allergies(PATIENT, COOKIE)
        self.assertFalse(payload["canWrite"])
        self.assertEqual(payload["allergies"], [])

    def test_accountant_cannot_read_allergies(self) -> None:
        with (
            patch.object(allergies.ward, "require_session"),
            patch.object(allergies.ward, "load_openmrs_user", return_value=ACCOUNTANT),
        ):
            with self.assertRaises(ApiError) as raised:
                allergies.list_allergies(PATIENT, COOKIE)
        self.assertEqual(raised.exception.status, 403)


class AllergyHttpMappingTests(unittest.TestCase):
    def test_openmrs_html_500_returns_a_useful_staff_message(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        error = HTTPError(
            "http://openmrs/allergy",
            500,
            "Error",
            hdrs=None,
            fp=BytesIO(b"<html><h1>Internal Server Error</h1></html>"),
        )
        with patch.object(allergies, "urlopen", side_effect=error):
            with self.assertRaises(ApiError) as raised:
                allergies._openmrs_allergy_call(
                    "POST",
                    f"/openmrs/ws/rest/v1/patient/{PATIENT}/allergy",
                    COOKIE,
                    {"allergen": {"allergenType": "OTHER", "nonCodedAllergen": "Dust"}},
                )
        self.assertEqual(raised.exception.status, 502)
        self.assertEqual(raised.exception.code, "openmrs_error")
        self.assertNotEqual(raised.exception.message.lower(), "cannot create allergy")
        self.assertIn("patient chart", raised.exception.message.lower())


class AllergyRolePrivilegeContractTests(unittest.TestCase):
    @staticmethod
    def _roles() -> tuple[list[dict], list[str]]:
        script = Path(__file__).parents[2] / "scripts" / "provision-dev-users.py"
        spec = importlib.util.spec_from_file_location("provision_dev_users_allergies", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ROLES, module.ALLERGY_WRITE_PRIVILEGES

    def test_doctor_and_nursing_reuse_existing_openmrs_allergy_privileges(self) -> None:
        roles, allergy_write = self._roles()
        catalog = {item["name"]: item for item in roles}
        expected = ["Get Allergies", "Add Allergies", "Edit Allergies", "Remove Allergies"]
        self.assertEqual(list(allergy_write), expected)
        self.assertEqual(catalog["Abikan:Doctor"]["privileges"], expected)
        self.assertEqual(catalog["Abikan:Nursing"]["privileges"], expected)
        self.assertEqual(catalog["Abikan:Doctor"]["inherited"], ["Clinical-App", "Provider"])
        self.assertEqual(catalog["Abikan:Nursing"]["inherited"], ["InPatient-App"])

    def test_other_departments_do_not_receive_allergy_write_privileges(self) -> None:
        roles, allergy_write = self._roles()
        writers = {"Abikan:Doctor", "Abikan:Nursing"}
        for spec in roles:
            if spec["name"] in writers:
                continue
            overlap = set(spec["privileges"]) & set(allergy_write)
            self.assertFalse(overlap, f"{spec['name']} must not receive {sorted(overlap)}")


if __name__ == "__main__":
    unittest.main()
