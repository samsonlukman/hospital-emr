"""Family Card grouping: one card per household, one fee at creation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hospital_family as household
from server import ApiError


RECEPTION = {
    "uuid": "rec-1",
    "username": "reception.abikan",
    "display": "Reception Desk",
    "roles": ["Abikan:Reception"],
    "privileges": ["app:registration"],
}
DOCTOR = {
    "uuid": "doc-1",
    "username": "doctor.abikan",
    "display": "Dr Ada",
    "roles": ["Abikan:Doctor"],
    "privileges": ["app:clinical"],
}
ADMIN = {
    "uuid": "admin-1",
    "username": "hospitaladmin.abikan",
    "display": "Hospital Administrator",
    "roles": ["Abikan:Hospital Admin"],
    "privileges": ["abikan:admin:staff"],
}


class FamilyStore(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = str(Path(self.directory.name) / "admin-audit.sqlite3")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _create_lukman(self) -> dict:
        return household.create_family(
            "Lukman Family",
            "mr-lukman",
            "Self",
            RECEPTION,
            member_name="Mr Lukman",
            member_identifier="ABC100001",
            path=self.db,
        )

    def test_new_family_creates_card_once_and_lists_first_member(self) -> None:
        family = self._create_lukman()
        self.assertEqual(family["cardNumber"], "FAM-001")
        self.assertEqual(family["familyName"], "Lukman Family")
        self.assertEqual(family["memberCount"], 1)
        self.assertEqual(family["feeStatus"], "pending")
        self.assertEqual(family["feePatientUuid"], "mr-lukman")
        self.assertTrue(family["isFeePatient"])

    def test_card_numbers_increment(self) -> None:
        self._create_lukman()
        second = household.create_family(
            "Ibrahim Family",
            "john-ibrahim",
            "Self",
            RECEPTION,
            member_name="John Ibrahim",
            path=self.db,
        )
        self.assertEqual(second["cardNumber"], "FAM-002")

    def test_second_member_does_not_create_card_or_pending_fee(self) -> None:
        family = self._create_lukman()
        linked = household.link_member(
            family["familyId"],
            "ade-lukman",
            "Child",
            RECEPTION,
            member_name="Ade Lukman",
            member_identifier="ABC100002",
            path=self.db,
        )
        self.assertEqual(linked["cardNumber"], "FAM-001")
        self.assertEqual(linked["memberCount"], 2)
        self.assertEqual(linked["feeStatus"], "pending")
        self.assertFalse(linked["isFeePatient"])
        first = household.charge_decision("mr-lukman", path=self.db)
        second = household.charge_decision("ade-lukman", path=self.db)
        self.assertTrue(first["canChargeFamilyFee"])
        self.assertFalse(first["familyCardIssued"])
        self.assertFalse(second["canChargeFamilyFee"])
        self.assertTrue(second["familyCardIssued"])
        self.assertEqual(second["blockReason"], household.FAMILY_CARD_ISSUED_MESSAGE)

    def test_individual_patient_is_unchanged_by_family_rules(self) -> None:
        decision = household.charge_decision("solo-patient", path=self.db)
        self.assertFalse(decision["inFamily"])
        self.assertFalse(decision["canChargeFamilyFee"])
        self.assertFalse(decision["familyCardIssued"])

    def test_family_fee_is_marked_billed_only_once(self) -> None:
        family = self._create_lukman()
        household.link_member(
            family["familyId"],
            "aisha-lukman",
            "Child",
            RECEPTION,
            member_name="Aisha Lukman",
            path=self.db,
        )
        household.mark_fee_billed(family["familyId"], RECEPTION, patient_uuid="mr-lukman", path=self.db)
        first = household.charge_decision("mr-lukman", path=self.db)
        second = household.charge_decision("aisha-lukman", path=self.db)
        self.assertTrue(first["familyCardIssued"])
        self.assertFalse(first["canChargeFamilyFee"])
        self.assertTrue(second["familyCardIssued"])
        self.assertFalse(second["canChargeFamilyFee"])

    def test_search_finds_family_by_name_card_and_member(self) -> None:
        self._create_lukman()
        by_name = household.search_families("Lukman", path=self.db)
        by_card = household.search_families("FAM-001", path=self.db)
        by_member = household.search_families("Ade", path=self.db)
        household.link_member(
            by_name[0]["familyId"],
            "ade-lukman",
            "Child",
            RECEPTION,
            member_name="Ade Lukman",
            path=self.db,
        )
        by_member = household.search_families("Ade Lukman", path=self.db)
        self.assertEqual(by_name[0]["cardNumber"], "FAM-001")
        self.assertEqual(by_card[0]["familyName"], "Lukman Family")
        self.assertEqual(by_member[0]["cardNumber"], "FAM-001")

    def test_similar_family_name_is_flagged_before_create(self) -> None:
        self._create_lukman()
        plan = household.prepare_family_registration(
            {"familyMode": "new", "householdName": "lukman family"},
            path=self.db,
        )
        self.assertTrue(plan["conflict"])
        self.assertEqual(plan["families"][0]["cardNumber"], "FAM-001")
        confirmed = household.prepare_family_registration(
            {"familyMode": "new", "householdName": "Lukman Family", "confirmCreateFamily": True},
            path=self.db,
        )
        self.assertFalse(confirmed["conflict"])

    def test_existing_family_registration_does_not_request_a_new_card(self) -> None:
        family = self._create_lukman()
        plan = household.prepare_family_registration(
            {"familyMode": "existing", "familyId": family["familyId"], "familyRelationship": "Child"},
            path=self.db,
        )
        result = household.apply_registration(
            "yusuf-lukman",
            plan,
            RECEPTION,
            member_name="Yusuf Lukman",
            path=self.db,
        )
        self.assertFalse(result["newCardCreated"])
        self.assertFalse(result["feeWillBeGenerated"])
        self.assertEqual(result["family"]["cardNumber"], "FAM-001")

    def test_new_family_registration_requests_card_fee_for_first_member_only(self) -> None:
        plan = household.prepare_family_registration(
            {"familyMode": "new", "householdName": "Ibrahim Family", "familyRelationship": "Self"},
            path=self.db,
        )
        result = household.apply_registration(
            "john-ibrahim",
            plan,
            RECEPTION,
            member_name="John Ibrahim",
            path=self.db,
        )
        self.assertTrue(result["newCardCreated"])
        self.assertTrue(result["feeWillBeGenerated"])
        self.assertEqual(result["family"]["cardNumber"], "FAM-001")

    def test_transfer_requires_confirmation_and_does_not_bill(self) -> None:
        lukman = self._create_lukman()
        ibrahim = household.create_family(
            "Ibrahim Family",
            "john-ibrahim",
            "Self",
            RECEPTION,
            member_name="John Ibrahim",
            path=self.db,
        )
        with self.assertRaises(ApiError) as error:
            household.link_member(
                ibrahim["familyId"],
                "mr-lukman",
                "Other",
                RECEPTION,
                path=self.db,
            )
        self.assertEqual(error.exception.code, "family_transfer_required")
        moved = household.link_member(
            ibrahim["familyId"],
            "mr-lukman",
            "Other",
            RECEPTION,
            confirm_transfer=True,
            path=self.db,
        )
        self.assertTrue(moved["transferred"])
        self.assertEqual(household.family_for_patient("mr-lukman", path=self.db)["cardNumber"], "FAM-002")
        self.assertFalse(household.charge_decision("mr-lukman", path=self.db)["canChargeFamilyFee"])

    def test_patient_cannot_belong_to_two_families_without_transfer(self) -> None:
        self._create_lukman()
        with self.assertRaises(ApiError) as error:
            household.create_family(
                "Another Family",
                "mr-lukman",
                "Self",
                RECEPTION,
                path=self.db,
            )
        self.assertEqual(error.exception.code, "family_membership_exists")

    def test_doctor_cannot_manage_families(self) -> None:
        with patch("hospital_family.core.require_session"), patch(
            "registration.load_openmrs_user",
            return_value=DOCTOR,
        ), patch(
            "hospital_admin.is_hospital_admin",
            return_value=False,
        ):
            with self.assertRaises(ApiError) as error:
                household.require_family_manager("cookie")
        self.assertEqual(error.exception.status, 403)

    def test_reception_and_admin_can_manage_families(self) -> None:
        with patch("hospital_family.core.require_session"), patch(
            "registration.load_openmrs_user",
            return_value=RECEPTION,
        ), patch(
            "registration.is_registrar",
            return_value=True,
        ):
            self.assertEqual(household.require_family_manager("cookie")["username"], "reception.abikan")
        with patch("hospital_family.core.require_session"), patch(
            "registration.load_openmrs_user",
            return_value=ADMIN,
        ), patch(
            "registration.is_registrar",
            return_value=False,
        ), patch(
            "hospital_admin.is_hospital_admin",
            return_value=True,
        ):
            self.assertEqual(household.require_family_manager("cookie")["username"], "hospitaladmin.abikan")


if __name__ == "__main__":
    unittest.main()
