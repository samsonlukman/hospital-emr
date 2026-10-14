"""Hospital Admin helpers — mocked OpenMRS, no live writes."""

from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import admin_audit
import hospital_admin as admin
from server import ApiError


AUDIT_DIRECTORY = tempfile.TemporaryDirectory()
admin_audit.AUDIT_DB_PATH = str(Path(AUDIT_DIRECTORY.name) / "admin-audit.sqlite3")


def user_row(
    username: str,
    roles: list[str],
    *,
    retired: bool = False,
    person_uuid: str = "person-1",
) -> dict:
    return {
        "uuid": f"user-{username}",
        "username": username,
        "retired": retired,
        "person": {"uuid": person_uuid, "display": username.replace(".", " ").title()},
        "roles": [{"uuid": f"role-{index}", "name": name} for index, name in enumerate(roles)],
        "userProperties": {"abikan.workplace": "clinical"},
    }


class Authorization(unittest.TestCase):
    def test_only_hospital_admin_or_technical_admin_is_allowed(self) -> None:
        self.assertTrue(admin.is_hospital_admin({"roles": ["SuperAdmin"], "privileges": []}))
        self.assertTrue(admin.is_hospital_admin({"roles": ["System Developer"], "privileges": []}))
        self.assertTrue(
            admin.is_hospital_admin(
                {"roles": ["Abikan:Hospital Admin"], "privileges": ["abikan:admin:staff"]}
            )
        )
        for role, privilege in [
            ("Abikan:Doctor", "app:clinical"),
            ("Abikan:Radiology", "app:radiology-upload"),
            ("Abikan:Accountant", "abikan:accountant"),
            ("Abikan:Reception", "app:registration"),
            ("Abikan:Nursing", "app:adt"),
        ]:
            self.assertFalse(admin.is_hospital_admin({"roles": [role], "privileges": [privilege]}))

    def test_superadmin_is_never_assignable_as_a_department(self) -> None:
        with self.assertRaises(ApiError) as caught:
            admin.validate_departments(["SuperAdmin"])
        self.assertEqual(caught.exception.code, "invalid_department")

    def test_hospital_admin_role_has_only_the_dedicated_abikan_privilege(self) -> None:
        script = Path(__file__).parents[2] / "scripts" / "provision-dev-users.py"
        spec = importlib.util.spec_from_file_location("provision_dev_users", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        role = next(item for item in module.ROLES if item["name"] == "Abikan:Hospital Admin")
        self.assertEqual(role["inherited"], [])
        self.assertEqual(
            set(role["privileges"]),
            {
                "abikan:admin:staff",
                "abikan:admin:analytics",
                "abikan:admin:audit-read",
                "Get Providers",
            },
        )
        self.assertNotIn("app:admin", role["privileges"])
        self.assertNotIn("app:adt", role["privileges"])
        self.assertNotIn("app:clinical", role["privileges"])
        self.assertNotIn("app:lab-lite", role["privileges"])
        self.assertNotIn("bahmni:clinical:dispense", role["privileges"])
        self.assertNotIn("abikan:accountant", role["privileges"])
        self.assertNotIn("Manage Providers", role["privileges"])
        self.assertNotIn("Add Users", role["privileges"])
        self.assertNotIn("Edit Users", role["privileges"])
        self.assertNotIn("Get Allergies", role["privileges"])
        self.assertNotIn("Add Allergies", role["privileges"])
        self.assertNotIn("Edit Allergies", role["privileges"])
        self.assertNotIn("Remove Allergies", role["privileges"])

    def test_admin_orchestration_uses_service_identity_not_actor_cookie(self) -> None:
        response = MagicMock()
        response.read.return_value = b'{"status":"ok"}'
        context = MagicMock()
        context.__enter__.return_value = response
        with (
            patch.object(admin, "OPENMRS_ADMIN_USER", "service.admin"),
            patch.object(admin, "OPENMRS_ADMIN_PASSWORD", "service-password"),
            patch.object(admin, "urlopen", return_value=context) as urlopen,
        ):
            result = admin._admin_openmrs_json("/openmrs/ws/rest/v1/user?limit=1")
        self.assertEqual(result, {"status": "ok"})
        request = urlopen.call_args.args[0]
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))
        self.assertIsNone(request.get_header("Cookie"))


class ApprovedRoles(unittest.TestCase):
    def test_exact_staff_facing_role_mapping(self) -> None:
        expected = {
            "clinical": "Doctor",
            "nursing": "Nurse",
            "reception": "Receptionist",
            "laboratory": "Laboratory Staff",
            "radiology": "Radiologist",
            "pharmacy": "Pharmacist",
            "accountant": "Accountant",
        }
        self.assertEqual(
            {row["id"]: row["roleLabel"] for row in admin.public_departments()},
            expected,
        )

    def test_clinical_nursing_and_radiology_require_provider(self) -> None:
        self.assertTrue(admin.provider_required(["clinical"]))
        self.assertTrue(admin.provider_required(["nursing"]))
        self.assertTrue(admin.provider_required(["radiology", "accountant"]))
        self.assertFalse(admin.provider_required(["reception", "laboratory", "pharmacy", "accountant"]))

    def test_multiple_approved_departments_are_preserved(self) -> None:
        self.assertEqual(
            admin.validate_departments(["clinical", "radiology", "clinical"]),
            ["clinical", "radiology"],
        )

    def test_clinical_radiology_and_nursing_combinations_are_allowed_by_allow_list(self) -> None:
        self.assertEqual(
            admin.validate_departments(["clinical", "radiology"]),
            ["clinical", "radiology"],
        )
        self.assertEqual(
            admin.validate_departments(["nursing", "radiology"]),
            ["nursing", "radiology"],
        )
        self.assertEqual(
            admin.validate_departments(["clinical", "nursing"]),
            ["clinical", "nursing"],
        )

    def test_system_developer_is_not_an_assignable_department(self) -> None:
        with self.assertRaises(ApiError) as caught:
            admin.validate_departments(["clinical", "System Developer"])
        self.assertEqual(caught.exception.code, "invalid_department")

    def test_pharmacy_department_includes_stock_receive_access(self) -> None:
        catalog = {
            "Abikan:Pharmacy": {"uuid": "role-pharmacy"},
            "Abikan:Pharmacy Inventory": {"uuid": "role-pharmacy-inventory"},
            "Abikan:Doctor": {"uuid": "role-doctor"},
        }
        refs = admin._approved_role_refs(["pharmacy"], catalog)
        self.assertEqual(
            {row["name"] for row in refs},
            {"Abikan:Pharmacy", "Abikan:Pharmacy Inventory"},
        )
        clinical = admin._approved_role_refs(["clinical"], catalog)
        self.assertEqual({row["name"] for row in clinical}, {"Abikan:Doctor"})


class ExistingUsers(unittest.TestCase):
    def test_existing_development_users_are_represented_without_raw_roles(self) -> None:
        providers = {
            "doctor-person": [{"uuid": "provider-doctor"}],
            "radio-person": [{"uuid": "provider-radio"}],
        }
        doctor = admin.serialize_staff(
            user_row("doctor.abikan", ["Abikan:Doctor"], person_uuid="doctor-person"),
            providers,
        )
        radiology = admin.serialize_staff(
            user_row("radiology.abikan", ["Abikan:Radiology"], person_uuid="radio-person"),
            providers,
        )
        accountant = admin.serialize_staff(
            user_row("accountant.abikan", ["Abikan:Accountant"], person_uuid="account-person"),
            providers,
        )
        self.assertEqual(doctor["departments"][0]["roleLabel"], "Doctor")
        self.assertEqual(doctor["providerStatus"], "ready")
        self.assertEqual(radiology["departments"][0]["roleLabel"], "Radiologist")
        self.assertEqual(radiology["providerStatus"], "ready")
        self.assertEqual(accountant["departments"][0]["roleLabel"], "Accountant")
        self.assertEqual(accountant["providerStatus"], "not_required")

    def test_disabled_user_remains_in_directory(self) -> None:
        row = admin.serialize_staff(
            user_row("doctor.disabled", ["Abikan:Doctor"], retired=True),
            {},
        )
        self.assertIsNotNone(row)
        self.assertFalse(row["enabled"])
        self.assertEqual(row["providerStatus"], "missing")

    def test_technical_accounts_are_not_manageable_staff(self) -> None:
        self.assertIsNone(admin.serialize_staff(user_row("admin", ["SuperAdmin"]), {}))

    def test_hospital_administrator_is_listed_without_department_roles(self) -> None:
        row = admin.serialize_staff(
            user_row("hospitaladmin.abikan", ["Abikan:Hospital Admin"]),
            {},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["accountType"], "hospital_administrator")
        self.assertEqual(row["departments"], [])
        self.assertEqual(row["providerStatus"], "not_required")

    def test_hospital_administrator_with_full_access_stays_in_the_directory(self) -> None:
        row = admin.serialize_staff(
            user_row("ismail.admin", ["Abikan:Hospital Admin", "SuperAdmin"]),
            {},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["accountType"], "hospital_administrator")
        self.assertEqual(row["departments"], [])


class ProviderProvisioning(unittest.TestCase):
    def test_existing_provider_is_reused(self) -> None:
        with (
            patch.object(
                admin,
                "_load_providers",
                return_value=[
                    {
                        "uuid": "provider-1",
                        "identifier": "doctor.abikan",
                        "retired": False,
                        "person": {"uuid": "person-1"},
                    }
                ],
            ),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            created = admin._ensure_provider("person-1", "doctor.abikan")
        self.assertFalse(created)
        request.assert_not_called()

    def test_missing_provider_is_created_once(self) -> None:
        with (
            patch.object(admin, "_load_providers", return_value=[]),
            patch.object(admin, "_admin_openmrs_json", return_value={"uuid": "provider-1"}) as request,
        ):
            created = admin._ensure_provider("person-1", "radiology.test")
        self.assertTrue(created)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs["payload"]["person"], "person-1")

    def test_provider_identifier_for_another_person_is_rejected(self) -> None:
        with patch.object(
            admin,
            "_load_providers",
            return_value=[
                {
                    "uuid": "provider-other",
                    "identifier": "doctor.test",
                    "retired": False,
                    "person": {"uuid": "person-other"},
                }
            ],
        ):
            with self.assertRaises(ApiError) as caught:
                admin._ensure_provider("person-target", "doctor.test")
        self.assertEqual(caught.exception.code, "duplicate_provider")


class PasswordPolicy(unittest.TestCase):
    def test_requires_mixed_case_and_digit(self) -> None:
        with self.assertRaises(ApiError) as caught:
            admin._initial_password("password")
        self.assertEqual(caught.exception.code, "password_case_required")
        with self.assertRaises(ApiError) as caught:
            admin._initial_password("PASSWORD1")
        self.assertEqual(caught.exception.code, "password_case_required")
        with self.assertRaises(ApiError) as caught:
            admin._initial_password("Password")
        self.assertEqual(caught.exception.code, "password_digit_required")
        with self.assertRaises(ApiError) as caught:
            admin._initial_password("Temporary123", username="Temporary123")
        self.assertEqual(caught.exception.code, "password_matches_username")
        self.assertEqual(admin._initial_password("Temporary123", username="nurse.ade"), "Temporary123")

    def test_openmrs_password_errors_are_staff_facing(self) -> None:
        body = json.dumps(
            {
                "error": {
                    "message": "[Please choose a password that contains both upper- and lower-case letters]"
                }
            }
        ).encode()
        error = HTTPError("http://openmrs/user", 500, "Server Error", hdrs=None, fp=BytesIO(body))
        mapped = admin._openmrs_error(error, "fallback")
        self.assertEqual(mapped.code, "password_rejected")
        self.assertIn("uppercase and lowercase", mapped.message)


class StaffCreation(unittest.TestCase):
    def setUp(self) -> None:
        admin.CREATE_RESULTS.clear()

    def test_duplicate_username_is_rejected_before_any_create(self) -> None:
        body = {
            "fullName": "Test Doctor",
            "username": "doctor.abikan",
            "initialPassword": "Temporary123",
            "departments": ["clinical"],
            "requestId": "request-1",
        }
        with (
            patch.object(
                admin,
                "require_hospital_admin",
                return_value={"username": "admin.abikan", "uuid": "admin-1"},
            ),
            patch.object(admin, "_find_user_by_username", return_value={"uuid": "existing"}),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.create_staff(body, "cookie")
        self.assertEqual(caught.exception.code, "duplicate_username")
        request.assert_not_called()

    def test_user_and_required_provider_are_created(self) -> None:
        body = {
            "fullName": "Test Radiologist",
            "username": "test.radiologist",
            "initialPassword": "Temporary123",
            "departments": ["radiology"],
            "requestId": "request-2",
            "enabled": True,
        }
        catalog = {"Abikan:Radiology": {"uuid": "role-radiology"}}
        responses = [
            {"uuid": "person-test"},
            {"uuid": "user-test"},
        ]
        with (
            patch.object(
                admin,
                "require_hospital_admin",
                return_value={"username": "admin.abikan", "uuid": "admin-1"},
            ),
            patch.object(admin, "_find_user_by_username", return_value=None),
            patch.object(admin, "_role_catalog", return_value=catalog),
            patch.object(admin, "_admin_openmrs_json", side_effect=responses) as request,
            patch.object(admin, "_ensure_provider", return_value=True) as provider,
        ):
            result = admin.create_staff(body, "cookie")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["staff"]["providerStatus"], "ready")
        self.assertNotIn("initialPassword", result)
        self.assertNotIn("Temporary123", str(result))
        self.assertGreaterEqual(request.call_count, 2)
        self.assertTrue(request.call_args_list[0].args[0].endswith("/person"))
        self.assertIn("/user", request.call_args_list[1].args[0])
        provider.assert_called_once_with("person-test", "test.radiologist")
        events = [
            row
            for row in admin_audit.read_admin_events()
            if row["request_id"] == "request-2"
        ]
        self.assertIn(
            ("ADMIN_CREATE_USER", "success"),
            {(row["action"], row["outcome"]) for row in events},
        )
        self.assertIn(
            ("ADMIN_PROVIDER_LINK", "success"),
            {(row["action"], row["outcome"]) for row in events},
        )
        self.assertNotIn("Temporary123", str(events))

    def test_provider_failure_disables_new_account_and_reports_failure(self) -> None:
        body = {
            "fullName": "Test Doctor",
            "username": "doctor.provider-failure",
            "initialPassword": "Temporary123",
            "departments": ["clinical"],
            "requestId": "request-provider-failure",
            "enabled": True,
        }
        catalog = {"Abikan:Doctor": {"uuid": "role-doctor"}}
        with (
            patch.object(
                admin,
                "require_hospital_admin",
                return_value={"username": "hospitaladmin.abikan", "uuid": "admin-1"},
            ),
            patch.object(admin, "_find_user_by_username", return_value=None),
            patch.object(admin, "_role_catalog", return_value=catalog),
            patch.object(
                admin,
                "_admin_openmrs_json",
                side_effect=[
                    {"uuid": "person-test"},
                    {"uuid": "user-test"},
                    {},
                ],
            ) as request,
            patch.object(
                admin,
                "_ensure_provider",
                side_effect=ApiError(502, "provider_error", "Provider failed."),
            ),
        ):
            with self.assertRaises(ApiError) as caught:
                admin.create_staff(body, "actor-cookie")
        self.assertEqual(caught.exception.code, "provider_create_failed_account_disabled")
        self.assertEqual(request.call_args_list[2].kwargs["method"], "DELETE")
        self.assertIn("reason=", request.call_args_list[2].args[0])
        events = [
            row
            for row in admin_audit.read_admin_events()
            if row["request_id"] == "request-provider-failure"
        ]
        self.assertEqual(
            {(row["action"], row["outcome"]) for row in events},
            {
                ("ADMIN_CREATE_USER", "failure"),
                ("ADMIN_PROVIDER_LINK", "failure"),
            },
        )
        self.assertNotIn("Temporary123", str(events))

    def test_request_id_replay_does_not_create_a_duplicate(self) -> None:
        admin.CREATE_RESULTS["same-request"] = {
            "username": "test.accountant",
            "payload": {"status": "ok", "message": "Staff account created."},
        }
        body = {
            "fullName": "Test Accountant",
            "username": "test.accountant",
            "initialPassword": "Temporary123",
            "departments": ["accountant"],
            "requestId": "same-request",
        }
        with patch.object(
            admin,
            "require_hospital_admin",
            return_value={"username": "admin.abikan", "uuid": "admin-1"},
        ):
            result = admin.create_staff(body, "cookie")
        self.assertEqual(result["message"], "Staff account created.")


class HospitalAdministratorAccounts(unittest.TestCase):
    def setUp(self) -> None:
        admin.CREATE_RESULTS.clear()

    def test_technical_superadmin_can_create_hospital_administrator(self) -> None:
        body = {
            "fullName": "Hospital Administrator",
            "username": "hospitaladmin.test",
            "initialPassword": "Temporary123",
            "accountType": "hospital_administrator",
            "requestId": "request-hospital-admin",
        }
        catalog = {"Abikan:Hospital Admin": {"uuid": "role-hospital-admin"}, "SuperAdmin": {"uuid": "role-superadmin"}}
        responses = [{"uuid": "person-hospital-admin"}, {"uuid": "user-hospital-admin"}]
        with (
            patch.object(
                admin,
                "require_hospital_admin",
                return_value={"username": "admin.abikan", "uuid": "admin-1", "roles": ["SuperAdmin"]},
            ),
            patch.object(admin, "_find_user_by_username", return_value=None),
            patch.object(admin, "_role_catalog", return_value=catalog),
            patch.object(admin, "_admin_openmrs_json", side_effect=responses) as request,
            patch.object(admin, "_ensure_provider") as provider,
        ):
            result = admin.create_staff(body, "cookie")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["staff"]["accountType"], "hospital_administrator")
        self.assertEqual(result["staff"]["departments"], [])
        self.assertEqual(
            request.call_args_list[1].kwargs["payload"]["roles"],
            [
                {"uuid": "role-hospital-admin", "name": "Abikan:Hospital Admin"},
                {"uuid": "role-superadmin", "name": "SuperAdmin"},
            ],
        )
        provider.assert_not_called()

    def test_hospital_administrator_only_actor_cannot_create_hospital_administrator(self) -> None:
        body = {
            "fullName": "Hospital Administrator",
            "username": "hospitaladmin.test",
            "initialPassword": "Temporary123",
            "accountType": "hospital_administrator",
            "requestId": "request-hospital-admin-denied",
        }
        with (
            patch.object(
                admin,
                "require_hospital_admin",
                return_value={
                    "username": "hospitaladmin.abikan",
                    "uuid": "hospital-admin-1",
                    "roles": ["Abikan:Hospital Admin"],
                    "privileges": ["abikan:admin:staff"],
                },
            ),
            patch.object(admin, "_find_user_by_username", return_value=None),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.create_staff(body, "cookie")
        self.assertEqual(caught.exception.code, "hospital_administrator_creation_forbidden")
        request.assert_not_called()

    def test_hospital_administrator_cannot_be_changed_by_hospital_administrator(self) -> None:
        actor = {
            "username": "hospitaladmin.abikan",
            "uuid": "hospital-admin-1",
            "roles": ["Abikan:Hospital Admin"],
            "privileges": ["abikan:admin:staff"],
        }
        target = user_row("hospitaladmin.other", ["Abikan:Hospital Admin"])
        with self.assertRaises(ApiError) as caught:
            admin._assert_manageable(target, actor)
        self.assertEqual(caught.exception.code, "hospital_administrator_account")

    def test_technical_superadmin_can_manage_hospital_administrator(self) -> None:
        actor = {"username": "admin.abikan", "uuid": "admin-1", "roles": ["SuperAdmin"]}
        target = user_row("hospitaladmin.other", ["Abikan:Hospital Admin"])
        admin._assert_manageable(target, actor)

    def test_full_access_hospital_administrator_is_still_manageable(self) -> None:
        actor = {"username": "admin.abikan", "uuid": "admin-1", "roles": ["SuperAdmin"]}
        target = user_row("ismail.admin", ["Abikan:Hospital Admin", "SuperAdmin"])
        admin._assert_manageable(target, actor)

    def test_even_technical_admin_cannot_assign_departments_to_hospital_administrator(self) -> None:
        actor = {"username": "admin.abikan", "uuid": "admin-1", "roles": ["SuperAdmin"]}
        target = user_row("hospitaladmin.other", ["Abikan:Hospital Admin"])
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_load_user", return_value=target),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.update_access(
                    target["uuid"],
                    {
                        "departments": ["clinical"],
                        "preferredDepartment": "clinical",
                        "requestId": "hospital-admin-department-denied",
                    },
                    "cookie",
                )
        self.assertEqual(caught.exception.code, "hospital_administrator_department_access")
        request.assert_not_called()


class AccessAndStatus(unittest.TestCase):
    def test_access_merge_keeps_unrelated_roles_and_multiple_departments(self) -> None:
        existing = [
            {"uuid": "role-old", "name": "Abikan:Doctor"},
            {"uuid": "role-other", "name": "Reports-App"},
        ]
        refs = [
            {"uuid": "role-clinical", "name": "Abikan:Doctor"},
            {"uuid": "role-radiology", "name": "Abikan:Radiology"},
        ]
        merged = admin._merge_department_roles(existing, ["clinical", "radiology"], refs)
        self.assertEqual(
            {row["name"] for row in merged},
            {"Reports-App", "Abikan:Doctor", "Abikan:Radiology"},
        )

    def test_access_merge_preserves_hospital_administrator_role(self) -> None:
        existing = [
            {"uuid": "role-hospital-admin", "name": "Abikan:Hospital Admin"},
            {"uuid": "role-reception", "name": "Abikan:Reception"},
        ]
        refs = [{"uuid": "role-reception", "name": "Abikan:Reception"}]
        merged = admin._merge_department_roles(existing, ["reception"], refs)
        self.assertEqual(
            {row["name"] for row in merged},
            {"Abikan:Hospital Admin", "Abikan:Reception"},
        )

    def test_admin_cannot_disable_self_or_technical_admin(self) -> None:
        actor = {"uuid": "admin-1"}
        with self.assertRaises(ApiError) as self_change:
            admin._assert_manageable({"uuid": "admin-1", "roles": []}, actor)
        self.assertEqual(self_change.exception.code, "self_change_blocked")
        with self.assertRaises(ApiError) as technical:
            admin._assert_manageable(
                {"uuid": "admin-2", "roles": [{"name": "SuperAdmin"}]},
                actor,
            )
        self.assertEqual(technical.exception.code, "technical_account")

    def test_enable_and_disable_retire_only_the_user(self) -> None:
        target = user_row("test.staff", ["Abikan:Reception"])
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        for enabled in (False, True):
            updated = user_row(
                "test.staff",
                ["Abikan:Reception"],
                retired=not enabled,
            )
            with (
                self.subTest(enabled=enabled),
                patch.object(admin, "require_hospital_admin", return_value=actor),
                patch.object(admin, "_load_user", side_effect=[target, updated]),
                patch.object(admin, "_admin_openmrs_json", return_value={}) as request,
            ):
                result = admin.update_status(
                    target["uuid"],
                    {"enabled": enabled, "requestId": f"status-{enabled}"},
                    "cookie",
                )
                self.assertEqual(result["enabled"], enabled)
                if enabled:
                    self.assertEqual(request.call_args.kwargs["method"], "POST")
                    self.assertEqual(request.call_args.kwargs["payload"], {"retired": False})
                else:
                    self.assertEqual(request.call_args.kwargs["method"], "DELETE")
                    self.assertIn("reason=", request.call_args.args[0])
                    self.assertNotIn("payload", request.call_args.kwargs)
                events = [
                    row
                    for row in admin_audit.read_admin_events()
                    if row["request_id"] == f"status-{enabled}"
                ]
                self.assertEqual(len(events), 1)
                self.assertEqual(
                    events[0]["action"],
                    "ADMIN_ENABLE_USER" if enabled else "ADMIN_DISABLE_USER",
                )
                self.assertEqual(events[0]["outcome"], "success")
                self.assertEqual(events[0]["new_state"]["enabled"], enabled)

    def test_admin_can_change_a_staff_sign_in_password(self) -> None:
        target = user_row("nurse.ade", ["Abikan:Nursing"])
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_load_user", return_value=target),
            patch.object(admin, "_admin_openmrs_json", return_value={}) as request,
        ):
            result = admin.change_password(
                target["uuid"],
                {"password": "Temporary123", "requestId": "password-1"},
                "cookie",
            )
        self.assertEqual(result["status"], "ok")
        self.assertIn("Tell the staff member", result["message"])
        self.assertEqual(request.call_args.kwargs["method"], "POST")
        self.assertEqual(request.call_args.kwargs["payload"], {"password": "Temporary123"})
        events = [row for row in admin_audit.read_admin_events() if row["request_id"] == "password-1"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "ADMIN_CHANGE_PASSWORD")
        self.assertEqual(events[0]["outcome"], "success")
        self.assertNotIn("Temporary123", str(events[0]))

    def test_password_change_rejects_weak_passwords_and_does_not_write(self) -> None:
        target = user_row("nurse.ade", ["Abikan:Nursing"])
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_load_user", return_value=target),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.change_password(
                    target["uuid"],
                    {"password": "password", "requestId": "password-weak"},
                    "cookie",
                )
        self.assertEqual(caught.exception.code, "password_case_required")
        request.assert_not_called()

    def test_password_change_cannot_target_technical_admin(self) -> None:
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(
                admin,
                "_load_user",
                return_value={"uuid": "admin-2", "username": "other.admin", "roles": [{"name": "SuperAdmin"}]},
            ),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.change_password(
                    "admin-2",
                    {"password": "Temporary123", "requestId": "password-tech"},
                    "cookie",
                )
        self.assertEqual(caught.exception.code, "technical_account")
        request.assert_not_called()

    def test_assigning_multiple_departments_uses_only_approved_roles(self) -> None:
        target = user_row("test.staff", ["Abikan:Reception"])
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        catalog = {
            "Abikan:Doctor": {"uuid": "role-doctor"},
            "Abikan:Accountant": {"uuid": "role-accountant"},
        }
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_load_user", return_value=target),
            patch.object(admin, "_role_catalog", return_value=catalog),
            patch.object(admin, "_ensure_provider", return_value=False) as provider,
            patch.object(admin, "_admin_openmrs_json", return_value={}) as request,
        ):
            result = admin.update_access(
                target["uuid"],
                {
                    "departments": ["clinical", "accountant"],
                    "preferredDepartment": "clinical",
                    "requestId": "access-multiple",
                },
                "cookie",
            )
        self.assertEqual(result["status"], "ok")
        provider.assert_called_once()
        role_names = {row["name"] for row in request.call_args.kwargs["payload"]["roles"]}
        self.assertEqual(role_names, {"Abikan:Doctor", "Abikan:Accountant"})

    def test_hospital_admin_can_assign_each_approved_department_via_orchestration(self) -> None:
        actor = {
            "username": "hospitaladmin.abikan",
            "uuid": "hospital-admin-1",
            "roles": ["Abikan:Hospital Admin"],
            "privileges": ["abikan:admin:staff"],
        }
        for index, department in enumerate(admin.DEPARTMENTS):
            department_id = str(department["id"])
            role_name = str(department["roleName"])
            target = user_row(f"staff.{department_id}", ["Abikan:Reception"])
            updated = user_row(f"staff.{department_id}", [role_name])
            updated["userProperties"] = {"abikan.workplace": department_id}
            with (
                self.subTest(department=department_id),
                patch.object(admin, "require_hospital_admin", return_value=actor),
                patch.object(admin, "_load_user", side_effect=[target, updated]),
                patch.object(
                    admin,
                    "_role_catalog",
                    return_value={role_name: {"uuid": f"role-{department_id}"}},
                ),
                patch.object(admin, "_ensure_provider", return_value=False),
                patch.object(admin, "_admin_openmrs_json", return_value={}) as request,
            ):
                result = admin.update_access(
                    target["uuid"],
                    {
                        "departments": [department_id],
                        "preferredDepartment": department_id,
                        "requestId": f"approved-{index}",
                    },
                    "actor-cookie",
                )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                {row["name"] for row in request.call_args.kwargs["payload"]["roles"]},
                {role_name},
            )

    def test_radiology_reception_accountant_remove_and_restore_preserves_other_access(self) -> None:
        all_three = [
            {"uuid": "role-radiology", "name": "Abikan:Radiology"},
            {"uuid": "role-reception", "name": "Abikan:Reception"},
            {"uuid": "role-accountant", "name": "Abikan:Accountant"},
        ]
        without_reception = admin._merge_department_roles(
            all_three,
            ["radiology", "accountant"],
            [all_three[0], all_three[2]],
        )
        self.assertEqual(
            {row["name"] for row in without_reception},
            {"Abikan:Radiology", "Abikan:Accountant"},
        )
        restored = admin._merge_department_roles(
            without_reception,
            ["radiology", "reception", "accountant"],
            all_three,
        )
        self.assertEqual(
            {row["name"] for row in restored},
            {"Abikan:Radiology", "Abikan:Reception", "Abikan:Accountant"},
        )

    def test_access_change_records_before_after_assign_and_remove_events(self) -> None:
        actor = {
            "username": "hospitaladmin.abikan",
            "uuid": "hospital-admin-1",
            "roles": ["Abikan:Hospital Admin"],
            "privileges": ["abikan:admin:staff"],
        }
        target = user_row(
            "radiology.audit",
            ["Abikan:Radiology", "Abikan:Reception", "Abikan:Accountant"],
        )
        updated = user_row("radiology.audit", ["Abikan:Radiology", "Abikan:Accountant"])
        updated["userProperties"] = {"abikan.workplace": "radiology"}
        catalog = {
            "Abikan:Radiology": {"uuid": "role-radiology"},
            "Abikan:Accountant": {"uuid": "role-accountant"},
        }
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_load_user", side_effect=[target, updated]),
            patch.object(admin, "_role_catalog", return_value=catalog),
            patch.object(admin, "_ensure_provider", return_value=False),
            patch.object(admin, "_admin_openmrs_json", return_value={}),
        ):
            admin.update_access(
                target["uuid"],
                {
                    "departments": ["radiology", "accountant"],
                    "preferredDepartment": "radiology",
                    "requestId": "access-audit-remove",
                },
                "actor-cookie",
            )
        events = [
            row
            for row in admin_audit.read_admin_events()
            if row["request_id"] == "access-audit-remove"
        ]
        self.assertIn(
            ("ADMIN_REMOVE_DEPARTMENT", "success"),
            {(row["action"], row["outcome"]) for row in events},
        )
        update = next(row for row in events if row["action"] == "ADMIN_UPDATE_DEPARTMENTS")
        self.assertIn("reception", update["previous_state"]["departments"])
        self.assertNotIn("reception", update["new_state"]["departments"])

    def test_removing_one_department_keeps_the_others(self) -> None:
        existing = [
            {"uuid": "role-radiology", "name": "Abikan:Radiology"},
            {"uuid": "role-reception", "name": "Abikan:Reception"},
            {"uuid": "role-accountant", "name": "Abikan:Accountant"},
            {"uuid": "role-other", "name": "Provider"},
        ]
        refs = [
            {"uuid": "role-radiology", "name": "Abikan:Radiology"},
            {"uuid": "role-accountant", "name": "Abikan:Accountant"},
        ]
        merged = admin._merge_department_roles(existing, ["radiology", "accountant"], refs)
        self.assertEqual(
            {row["name"] for row in merged},
            {"Provider", "Abikan:Radiology", "Abikan:Accountant"},
        )

    def test_arbitrary_privileges_and_raw_roles_are_rejected(self) -> None:
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        body = {
            "departments": ["radiology"],
            "preferredDepartment": "radiology",
            "privileges": ["Edit Users", "Delete Orders"],
            "roles": ["SuperAdmin"],
        }
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.update_access("user-1", body, "cookie")
        self.assertEqual(caught.exception.code, "arbitrary_privilege_rejected")
        request.assert_not_called()

    def test_superadmin_cannot_be_assigned_through_access_update(self) -> None:
        actor = {"username": "admin.abikan", "uuid": "admin-1"}
        with (
            patch.object(admin, "require_hospital_admin", return_value=actor),
            patch.object(admin, "_admin_openmrs_json") as request,
        ):
            with self.assertRaises(ApiError) as caught:
                admin.update_access(
                    "user-1",
                    {
                        "departments": ["SuperAdmin"],
                        "preferredDepartment": "SuperAdmin",
                    },
                    "cookie",
                )
        self.assertEqual(caught.exception.code, "invalid_department")
        request.assert_not_called()


class OpenmrsErrorMapping(unittest.TestCase):
    def _http_error(self, code: int, payload: dict) -> HTTPError:
        return HTTPError(
            "https://localhost/openmrs/ws/rest/v1/user/x",
            code,
            "Error",
            hdrs=None,
            fp=BytesIO(json.dumps(payload).encode()),
        )

    def test_missing_assignment_privilege_is_staff_facing(self) -> None:
        mapped = admin._openmrs_error(
            self._http_error(
                500,
                {"error": {"message": "You must have privilege {0} in order to assign it."}},
            ),
            "Department access could not be saved.",
        )
        self.assertEqual(mapped.status, 403)
        self.assertEqual(mapped.code, "role_assignment_unauthorized")
        self.assertIn("does not have permission to assign this role", mapped.message)
        self.assertNotIn("{0}", mapped.message)

    def test_openmrs_forbidden_does_not_claim_success(self) -> None:
        mapped = admin._openmrs_error(
            self._http_error(403, {"error": {"message": "Forbidden"}}),
            "Department access could not be saved.",
        )
        self.assertEqual(mapped.status, 403)
        self.assertEqual(mapped.code, "admin_permission_missing")

    def test_unknown_openmrs_failure_uses_safe_fallback(self) -> None:
        mapped = admin._openmrs_error(
            self._http_error(500, {"error": {"message": "Internal server error", "detail": "stack"}}),
            "Department access could not be saved.",
        )
        self.assertEqual(mapped.status, 502)
        self.assertEqual(mapped.message, "Department access could not be saved.")
        self.assertNotIn("stack", mapped.message)


if __name__ == "__main__":
    unittest.main()
