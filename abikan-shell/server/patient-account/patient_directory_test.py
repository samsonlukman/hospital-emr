"""Patient directory paging, staff copy, and Reception/Admin access."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import hospital_admin as administration
import openmrs_sql
import patient_directory as directory
import registration as reception
from server import ApiError


def _user(roles: list[str], privileges: list[str], username: str) -> dict:
    return {
        "uuid": f"user-{username}",
        "username": username,
        "roles": roles,
        "privileges": privileges,
    }


RECEPTION = _user(["Abikan:Reception"], ["app:registration"], "reception.abikan")
HOSPITAL_ADMIN = _user(
    ["Abikan:Hospital Admin"],
    ["abikan:admin:staff"],
    "hospitaladmin.abikan",
)
DOCTOR = _user(["Abikan:Doctor"], ["app:clinical"], "doctor.abikan")


class DirectoryQuery(unittest.TestCase):
    def test_defaults_to_fifty_and_ignores_one_letter_search(self) -> None:
        page = directory.parse_directory_query("/patients")
        self.assertEqual(page["limit"], 50)
        self.assertEqual(page["startIndex"], 0)
        self.assertEqual(page["q"], "")
        self.assertEqual(page["lifeStatus"], "all")
        page = directory.parse_directory_query("/patients?q=A&limit=100&startIndex=100")
        self.assertEqual(page["q"], "")
        self.assertEqual(page["limit"], 100)
        self.assertEqual(page["startIndex"], 100)

    def test_rejects_page_sizes_other_than_50_or_100(self) -> None:
        with self.assertRaises(ApiError) as raised:
            directory.parse_directory_query("/patients?limit=25")
        self.assertEqual(raised.exception.status, 422)
        self.assertIn("50 or 100", raised.exception.message)

    def test_accepts_alive_and_deceased_filters(self) -> None:
        page = directory.parse_directory_query("/patients?lifeStatus=deceased")
        self.assertEqual(page["lifeStatus"], "deceased")
        with self.assertRaises(ApiError) as raised:
            directory.parse_directory_query("/patients?lifeStatus=unknown")
        self.assertEqual(raised.exception.code, "invalid_life_status")


class DirectoryRows(unittest.TestCase):
    def test_uses_hospital_columns_and_lagos_registration_date(self) -> None:
        created = datetime(2026, 9, 6, 23, 30, tzinfo=timezone.utc)
        row = directory.serialize_directory_row(
            (
                "pat-1",
                "Adaeze Okafor",
                "ABC123",
                "F",
                date(1990, 1, 15),
                "08012345678",
                "family",
                created,
                0,
                None,
            ),
            date(2026, 9, 7),
        )
        self.assertEqual(row["name"], "Adaeze Okafor")
        self.assertEqual(row["hospitalNumber"], "ABC123")
        self.assertEqual(row["sex"], "Female")
        self.assertEqual(row["age"], "36")
        self.assertEqual(row["phone"], "08012345678")
        self.assertEqual(row["cardType"], "Family Card")
        self.assertEqual(row["registeredOn"], "7 Sep 2026")
        self.assertEqual(row["alive"], "Yes")
        self.assertEqual(row["deathDate"], "")
        self.assertNotIn("OpenMRS", row["name"])

    def test_keeps_blank_optional_fields_empty(self) -> None:
        row = directory.serialize_directory_row(
            ("pat-2", None, None, "M", None, None, None, None, 0, None),
            date(2026, 9, 7),
        )
        self.assertEqual(row["name"], "Unnamed patient")
        self.assertEqual(row["hospitalNumber"], "")
        self.assertEqual(row["sex"], "Male")
        self.assertEqual(row["age"], "")
        self.assertEqual(row["phone"], "")
        self.assertEqual(row["cardType"], "")
        self.assertEqual(row["registeredOn"], "")
        self.assertEqual(row["alive"], "Yes")

    def test_shows_deceased_patients_as_alive_no(self) -> None:
        row = directory.serialize_directory_row(
            (
                "pat-3",
                "Late Patient",
                "ABC999",
                "M",
                date(1960, 5, 1),
                "",
                "individual",
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                1,
                date(2026, 8, 15),
            ),
            date(2026, 9, 7),
        )
        self.assertEqual(row["alive"], "No")
        self.assertEqual(row["cardType"], "Individual Card")
        self.assertEqual(row["deathDate"], "2026-08-15")
        self.assertEqual(directory.format_death_date(row["deathDate"]), "15/08/2026")

    def test_legacy_antenatal_card_type_shows_as_individual_not_anc_identity(self) -> None:
        row = directory.serialize_directory_row(
            (
                "pat-anc",
                "Fatima Musa",
                "ABC555",
                "F",
                date(1995, 3, 10),
                "08099998888",
                "antenatal",
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                0,
                None,
            ),
            date(2026, 9, 10),
        )
        # Mistaken historical cardType=antenatal must not redefine the patient as ANC-only.
        self.assertEqual(row["cardType"], "Individual Card")
        self.assertEqual(directory._card_type_label("anc"), "Individual Card")
        self.assertEqual(directory._card_type_label("Antenatal Card (ANC)"), "Individual Card")


class DirectoryAccess(unittest.TestCase):
    def test_reception_and_hospital_admin_can_read(self) -> None:
        with (
            patch.object(directory.core, "require_session"),
            patch("accountant.load_openmrs_user", return_value=RECEPTION),
        ):
            self.assertEqual(directory.require_directory_reader("cookie")["username"], "reception.abikan")
        with (
            patch.object(directory.core, "require_session"),
            patch("accountant.load_openmrs_user", return_value=HOSPITAL_ADMIN),
        ):
            self.assertEqual(
                directory.require_directory_reader("cookie")["username"],
                "hospitaladmin.abikan",
            )

    def test_clinical_staff_cannot_read(self) -> None:
        with (
            patch.object(directory.core, "require_session"),
            patch("accountant.load_openmrs_user", return_value=DOCTOR),
            self.assertRaises(ApiError) as raised,
        ):
            directory.require_directory_reader("cookie")
        self.assertEqual(raised.exception.status, 403)
        self.assertIn("Reception", raised.exception.message)
        self.assertNotIn("OpenMRS", raised.exception.message)

    def test_list_pages_from_hospital_records(self) -> None:
        created = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
        with (
            patch.object(directory, "require_directory_reader", return_value=RECEPTION),
            patch.object(openmrs_sql, "fetch_int", return_value=2),
            patch.object(
                openmrs_sql,
                "fetch_all",
                return_value=[
                    ("pat-1", "Adaeze Okafor", "ABC123", "F", date(1990, 1, 15), "0801", "Individual", created, 0, None),
                ],
            ),
        ):
            payload = directory.build_directory("cookie", "/patients?limit=50&startIndex=0")
        self.assertEqual(payload["total"], 2)
        self.assertTrue(payload["hasMore"])
        self.assertEqual(payload["patients"][0]["hospitalNumber"], "ABC123")
        self.assertEqual(payload["patients"][0]["alive"], "Yes")
        self.assertEqual(len(payload["patients"]), 1)


class DirectoryRecord(unittest.TestCase):
    def test_record_uses_hospital_details_not_bills(self) -> None:
        row = (
            "pat-1",
            "Adaeze",
            "",
            "Okafor",
            "ABC123",
            "F",
            date(1990, 1, 15),
            0,
            "08012345678",
            datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
            "12 Hospital Road",
            "",
            "Ilorin",
            "Kwara",
            "",
            "",
            "Nigeria",
            0,
            None,
        )
        with (
            patch.object(directory, "require_directory_reader", return_value=HOSPITAL_ADMIN) as gate,
            patch.object(openmrs_sql, "fetch_one", return_value=row),
            patch.object(openmrs_sql, "fetch_all", return_value=[("ABC123", 1, "Patient Identifier")]),
        ):
            payload = directory.load_patient_record("pat-1", "cookie")
        gate.assert_called_once_with("cookie")
        self.assertEqual(payload["givenName"], "Adaeze")
        self.assertEqual(payload["familyName"], "Okafor")
        self.assertEqual(payload["birthdate"], "1990-01-15")
        self.assertEqual(payload["attributes"]["phoneNumber"], "08012345678")
        self.assertEqual(payload["address"]["cityVillage"], "Ilorin")
        self.assertTrue(payload["alive"])
        self.assertEqual(payload["deathDate"], "")
        self.assertNotIn("invoice", payload)
        self.assertNotIn("OpenMRS", str(payload))

    def test_identity_uses_register_when_clinical_rest_is_blocked(self) -> None:
        row = (
            "pat-1",
            "Adaeze",
            "",
            "Okafor",
            "ABC123",
            "F",
            date(1990, 1, 15),
            0,
            "08012345678",
            datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
            "12 Hospital Road",
            "",
            "Ilorin",
            "Kwara",
            "",
            "",
            "Nigeria",
            0,
            None,
        )
        with (
            patch.object(openmrs_sql, "fetch_one", return_value=row),
            patch.object(openmrs_sql, "fetch_all", return_value=[("ABC123", 1, "Patient Identifier")]),
            patch.object(
                directory.core,
                "openmrs_get",
                side_effect=ApiError(502, "openmrs_error", "Clinical service is unavailable."),
            ),
        ):
            identity = directory.load_patient_identity("pat-1")
            fallback = directory.core.load_openmrs_patient("pat-1", "cookie")
        self.assertEqual(identity["name"], "Adaeze Okafor")
        self.assertEqual(identity["mrn"], "ABC123")
        self.assertEqual(fallback["name"], "Adaeze Okafor")
        self.assertEqual(fallback["mrn"], "ABC123")


class RoleHelpersStayAligned(unittest.TestCase):
    def test_role_helpers_match_existing_gates(self) -> None:
        self.assertTrue(reception.is_registrar(RECEPTION))
        self.assertTrue(administration.is_hospital_admin(HOSPITAL_ADMIN))
        self.assertFalse(reception.is_registrar(DOCTOR))
        self.assertFalse(administration.is_hospital_admin(DOCTOR))


if __name__ == "__main__":
    unittest.main()
