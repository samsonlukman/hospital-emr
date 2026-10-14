"""Staff directory profiles — OpenMRS person plus optional login."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import admin_audit
import hospital_admin as admin
import staff_hr
from server import ApiError

AUDIT_DIRECTORY = tempfile.TemporaryDirectory()
FILES_DIRECTORY = tempfile.TemporaryDirectory()
admin_audit.AUDIT_DB_PATH = str(Path(AUDIT_DIRECTORY.name) / "admin-audit.sqlite3")
staff_hr.STAFF_FILES_ROOT = Path(FILES_DIRECTORY.name)


def _jpeg() -> str:
    import base64

    return base64.b64encode(
        bytes(
            [
                0xFF,
                0xD8,
                0xFF,
                0xE0,
                0x00,
                0x10,
                0x4A,
                0x46,
                0x49,
                0x46,
                0x00,
                0x01,
                0x01,
                0x00,
                0x00,
                0x01,
                0x00,
                0x01,
                0x00,
                0x00,
                0xFF,
                0xD9,
            ]
        )
    ).decode("ascii")


class StaffHrRules(unittest.TestCase):
    def setUp(self) -> None:
        staff_hr.reset_attribute_type_cache()
        admin.CREATE_RESULTS.clear()

    def test_security_and_attendant_never_receive_login(self) -> None:
        self.assertTrue(staff_hr.is_non_login_category("security"))
        self.assertTrue(staff_hr.is_non_login_category("attendant"))
        self.assertFalse(staff_hr.is_non_login_category("clinical"))
        for category in staff_hr.NON_LOGIN_CATEGORIES:
            self.assertEqual(staff_hr.STAFF_CATEGORIES[category]["emrAccess"], "none")

    def test_clinical_employment_type_is_required_when_creating_from_category(self) -> None:
        body = {
            "fullName": "Test Doctor",
            "username": "test.doctor",
            "initialPassword": "Temporary123",
            "staffCategory": "clinical",
            "departments": ["clinical"],
            "requestId": "clinical-missing-type",
        }
        with patch.object(
            admin,
            "require_hospital_admin",
            return_value={"username": "hospitaladmin.abikan", "uuid": "admin-1"},
        ):
            with self.assertRaises(ApiError) as caught:
                admin.create_staff(body, "cookie")
        self.assertEqual(caught.exception.code, "employment_type_required")

    def test_legacy_clinical_create_defaults_to_external(self) -> None:
        self.assertEqual(staff_hr.default_employment_type("clinical", ""), "external")
        self.assertEqual(staff_hr.default_employment_type("nursing", ""), "")

    def test_sensitive_hr_is_not_required_for_external_clinicians(self) -> None:
        profile = staff_hr.validate_hr_profile({})
        self.assertEqual(profile["nin"], "")
        self.assertEqual(profile["bankAccountNumber"], "")

    def test_hr_is_collected_for_every_staff_type_except_outsourced_doctors(self) -> None:
        self.assertFalse(staff_hr.collects_hr_profile(""))
        self.assertFalse(staff_hr.collects_hr_profile("clinical", "external"))
        self.assertFalse(staff_hr.collects_hr_profile("clinical", ""))
        self.assertTrue(staff_hr.collects_hr_profile("clinical", "permanent"))
        self.assertTrue(staff_hr.collects_hr_profile("hospital_admin"))
        self.assertTrue(staff_hr.collects_hr_profile("nursing"))
        self.assertTrue(staff_hr.collects_hr_profile("security"))

    def test_login_profiles_store_hr_except_for_outsourced_doctors(self) -> None:
        hr = {
            "address": "Staff quarters",
            "phone": "08000000000",
            "nin": "12345678901",
            "bankAccountNumber": "0123456789",
            "bankName": "Access Bank",
            "accountName": "Ada Nurse",
            "qualification": "RN/RM",
        }
        with patch.object(staff_hr, "write_person_attributes") as write:
            staff_hr.record_login_staff_profile(
                person_uuid="person-admin-1",
                departments=[],
                account_type="hospital_administrator",
                hr=hr,
            )
            staff_hr.record_login_staff_profile(
                person_uuid="person-nurse-1",
                departments=["nursing"],
                account_type="staff",
                hr=hr,
            )
            staff_hr.record_login_staff_profile(
                person_uuid="person-external-1",
                departments=["clinical"],
                account_type="staff",
                employment_type="external",
                hr=hr,
            )
        saved = {
            call.args[0]: call.args[1]
            for call in write.call_args_list
        }
        self.assertEqual(saved["person-admin-1"][staff_hr.ATTR_NIN], "12345678901")
        self.assertEqual(saved["person-nurse-1"][staff_hr.ATTR_NIN], "12345678901")
        self.assertNotIn(staff_hr.ATTR_NIN, saved["person-external-1"])

    def test_invalid_nin_and_bank_are_rejected(self) -> None:
        with self.assertRaises(ApiError) as caught:
            staff_hr.validate_hr_profile({"nin": "12"})
        self.assertEqual(caught.exception.code, "invalid_nin")
        with self.assertRaises(ApiError) as caught:
            staff_hr.validate_hr_profile({"bankAccountNumber": "abc"})
        self.assertEqual(caught.exception.code, "invalid_bank_account")


class DirectoryStaffCreate(unittest.TestCase):
    def setUp(self) -> None:
        staff_hr.reset_attribute_type_cache()
        admin.CREATE_RESULTS.clear()

    def test_security_is_created_without_a_user(self) -> None:
        body = {
            "fullName": "Gate Security",
            "staffCategory": "security",
            "phone": "08000000000",
            "address": "Hospital gate",
            "qualification": "SSCE",
            "requestId": "security-1",
        }
        types = {name: f"type-{name}" for name in staff_hr.HR_ATTRIBUTE_NAMES}
        with (
            patch.object(
                admin,
                "require_hospital_admin",
                return_value={"username": "hospitaladmin.abikan", "uuid": "admin-1"},
            ),
            patch.object(staff_hr, "attribute_type_map", return_value=types),
            patch.object(
                admin,
                "_admin_openmrs_json",
                side_effect=[{"uuid": "person-security-1"}, {}],
            ) as request,
        ):
            result = admin.create_staff(body, "cookie")
        self.assertEqual(result["staff"]["emrAccess"], "none")
        self.assertEqual(result["staff"]["staffCategory"], "security")
        self.assertEqual(result["staff"]["username"], "")
        self.assertFalse(result["staff"]["userUuid"])
        paths = [call.args[0] for call in request.call_args_list]
        self.assertTrue(any(path.endswith("/person") for path in paths))
        self.assertFalse(any("/user" in path and not path.endswith("person") for path in paths))

    def test_security_rejects_username_and_password(self) -> None:
        with patch.object(
            admin,
            "require_hospital_admin",
            return_value={"username": "hospitaladmin.abikan", "uuid": "admin-1"},
        ):
            with self.assertRaises(ApiError) as caught:
                admin.create_staff(
                    {
                        "fullName": "Gate Security",
                        "staffCategory": "security",
                        "username": "security.gate",
                        "initialPassword": "Temporary123",
                        "requestId": "security-login",
                    },
                    "cookie",
                )
        self.assertEqual(caught.exception.code, "login_not_allowed")


class StaffFiles(unittest.TestCase):
    def test_profile_picture_type_and_size(self) -> None:
        staff_hr.save_profile_picture("person-photo-1", _jpeg())
        self.assertTrue(staff_hr.has_profile_picture("person-photo-1"))
        data, content_type = staff_hr.read_profile_picture("person-photo-1")
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8\xff"))
        with self.assertRaises(ApiError) as caught:
            staff_hr.save_profile_picture("person-photo-1", "not-a-file")
        self.assertEqual(caught.exception.code, "invalid_file")

    def test_signed_in_staff_can_read_their_own_photo(self) -> None:
        staff_hr.save_profile_picture("person-own-1", _jpeg())
        session = {
            "authenticated": True,
            "user": {"uuid": "user-1", "username": "accountant.abikan", "person": {"uuid": "person-own-1"}},
        }
        with patch.object(admin.core, "require_session", return_value=session):
            data, content_type, name = staff_hr.download_own_photo("cookie")
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8\xff"))
        self.assertTrue(name.startswith("profile-picture"))

    def test_signed_in_staff_without_a_photo_get_a_clear_empty_result(self) -> None:
        session = {
            "authenticated": True,
            "user": {"uuid": "user-2", "username": "accountant.abikan", "person": {"uuid": "person-none"}},
        }
        with patch.object(admin.core, "require_session", return_value=session):
            with self.assertRaises(ApiError) as caught:
                staff_hr.download_own_photo("cookie")
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(caught.exception.code, "photo_not_found")

    def test_appointment_letter_is_not_public_path(self) -> None:
        pdf = base64_pdf()
        staff_hr.save_appointment_letter("person-letter-1", pdf)
        data, content_type, name = staff_hr.read_appointment_letter("person-letter-1")
        self.assertEqual(content_type, "application/pdf")
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertTrue(name.startswith("appointment-letter"))


def base64_pdf() -> str:
    import base64

    return base64.b64encode(b"%PDF-1.4\n1 0 obj<<>>endobj\n").decode("ascii")


class SensitiveRedaction(unittest.TestCase):
    def test_audit_redacts_nin_and_bank_details(self) -> None:
        event_id = admin_audit.record_admin_event(
            actor={"uuid": "admin-1", "username": "hospitaladmin.abikan"},
            target_username="doctor.test",
            action="ADMIN_UPDATE_STAFF_PROFILE",
            previous_state={},
            new_state={"nin": "12345678901", "bankAccountNumber": "0123456789"},
            details={"content": "FILE"},
            outcome="success",
        )
        row = next(item for item in admin_audit.read_admin_events() if item["event_id"] == event_id)
        self.assertEqual(row["new_state"]["nin"], "[REDACTED]")
        self.assertEqual(row["new_state"]["bankAccountNumber"], "[REDACTED]")
        self.assertEqual(row["details"]["content"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
