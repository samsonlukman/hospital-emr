"""Antenatal Care pregnancy episodes, visits, permissions, and fees."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import antenatal as anc
from server import ApiError


def _user(username: str = "reception", roles: list[str] | None = None) -> dict:
    return {
        "uuid": "user-1",
        "username": username,
        "display": username,
        "roles": roles or ["Abikan:Reception"],
        "privileges": ["app:registration"],
    }


class AncAmount(unittest.TestCase):
    def test_default_amount_is_2000(self) -> None:
        self.assertEqual(anc.parse_anc_amount(None), 2000.0)
        self.assertEqual(anc.parse_anc_amount(""), 2000.0)

    def test_reception_can_set_amount(self) -> None:
        self.assertEqual(anc.parse_anc_amount(2500), 2500.0)
        self.assertEqual(anc.parse_anc_amount("3,000"), 3000.0)
        self.assertEqual(anc.parse_anc_amount("₦1500"), 1500.0)

    def test_rejects_invalid_amount(self) -> None:
        with self.assertRaises(ApiError) as raised:
            anc.parse_anc_amount(0)
        self.assertEqual(raised.exception.code, "amount_invalid")
        with self.assertRaises(ApiError):
            anc.parse_anc_amount("$20")


class AncPregnancyLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "anc.sqlite3")
        anc.reset_for_tests()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_pregnancy_and_persist_card(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy(
                "patient-a",
                {"gravida": 2, "para": 1, "lmp": "2026-01-01", "bloodGroup": "O+"},
                "cookie",
                path=self.db,
            )
        self.assertTrue(created["created"])
        pregnancy_id = created["pregnancy"]["pregnancyId"]
        self.assertEqual(created["pregnancy"]["card"]["gravida"], 2)

        with patch.object(anc, "require_anc_reader", return_value=_user()):
            summary = anc.get_patient_anc_summary("patient-a", "cookie", path=self.db)
        self.assertTrue(summary["hasAnc"])
        self.assertEqual(summary["activePregnancy"]["pregnancyId"], pregnancy_id)

        with patch.object(anc, "require_anc_writer", return_value=_user("nurse", ["Abikan:Nursing"])):
            updated = anc.update_pregnancy_card(
                "patient-a",
                pregnancy_id,
                {"edd": "2026-10-08", "heightCm": 165},
                "cookie",
                path=self.db,
            )
        self.assertEqual(updated["pregnancy"]["card"]["edd"], "2026-10-08")
        self.assertEqual(updated["pregnancy"]["card"]["heightCm"], 165)
        self.assertEqual(updated["pregnancy"]["card"]["gravida"], 2)

    def test_multiple_visits_under_one_pregnancy(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            started = anc.start_pregnancy("patient-b", {}, "cookie", path=self.db)
            pregnancy_id = started["pregnancy"]["pregnancyId"]
            first = anc.record_anc_visit(
                "patient-b",
                {
                    "pregnancyId": pregnancy_id,
                    "openmrsVisitUuid": "visit-1",
                    "weightKg": 62,
                    "systolic": 110,
                    "diastolic": 70,
                    "fundalHeightCm": 24,
                    "fetalHeartRate": 140,
                },
                "cookie",
                path=self.db,
            )
            second = anc.record_anc_visit(
                "patient-b",
                {
                    "pregnancyId": pregnancy_id,
                    "openmrsVisitUuid": "visit-2",
                    "weightKg": 64,
                    "gestationalAgeWeeks": 28,
                },
                "cookie",
                path=self.db,
            )
        self.assertTrue(first["created"])
        self.assertTrue(second["created"])
        self.assertEqual(len(second["pregnancy"]["visits"]), 2)
        self.assertEqual(second["pregnancy"]["visits"][0]["weightKg"], 62)
        self.assertEqual(second["pregnancy"]["visits"][1]["weightKg"], 64)

    def test_same_openmrs_visit_updates_instead_of_duplicating(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            anc.start_pregnancy("patient-c", {}, "cookie", path=self.db)
            first = anc.record_anc_visit(
                "patient-c",
                {"openmrsVisitUuid": "same-visit", "weightKg": 60},
                "cookie",
                path=self.db,
            )
            second = anc.record_anc_visit(
                "patient-c",
                {"openmrsVisitUuid": "same-visit", "weightKg": 61, "keyFindings": "Well"},
                "cookie",
                path=self.db,
            )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(len(second["pregnancy"]["visits"]), 1)
        self.assertEqual(second["visit"]["weightKg"], 61)
        self.assertEqual(second["visit"]["keyFindings"], "Well")

    def test_start_new_does_not_create_a_second_card(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            first = anc.start_pregnancy("patient-d", {"gravida": 1}, "cookie", path=self.db)
            blocked = anc.start_pregnancy("patient-d", {"gravida": 2}, "cookie", path=self.db)
            self.assertFalse(blocked["created"])
            self.assertEqual(blocked["code"], "pregnancy_already_active")
            second = anc.start_pregnancy(
                "patient-d",
                {"gravida": 2, "startNew": True},
                "cookie",
                path=self.db,
            )
        self.assertFalse(second["created"])
        self.assertEqual(second["pregnancy"]["pregnancyId"], first["pregnancy"]["pregnancyId"])
        with patch.object(anc, "require_anc_reader", return_value=_user()):
            summary = anc.get_patient_anc_summary("patient-d", "cookie", path=self.db)
        self.assertEqual(len(summary["pregnancies"]), 1)
        self.assertEqual(summary["activePregnancy"]["pregnancyId"], first["pregnancy"]["pregnancyId"])

    def test_non_anc_patient_has_no_misleading_summary(self) -> None:
        with patch.object(anc, "require_anc_reader", return_value=_user()):
            summary = anc.get_patient_anc_summary("never-anc", "cookie", path=self.db)
        self.assertFalse(summary["hasAnc"])
        self.assertIsNone(summary["activePregnancy"])
        self.assertEqual(summary["pregnancies"], [])

    def test_enroll_reuses_active_pregnancy(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            with patch.object(anc, "require_anc_reader", return_value=_user()):
                with patch.object(anc, "get_anc_registration_charge", side_effect=ApiError(503, "odoo_error", "skip")):
                    first = anc.enroll_patient("patient-e", {}, "cookie", path=self.db)
                    second = anc.enroll_patient("patient-e", {}, "cookie", path=self.db)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(
            first["pregnancy"]["pregnancyId"],
            second["pregnancy"]["pregnancyId"],
        )
        self.assertTrue(anc.patient_is_enrolled("patient-e", path=self.db))

    def test_registration_fee_is_one_time_per_pregnancy(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            with patch.object(anc, "require_anc_reader", return_value=_user()):
                with patch.object(anc, "get_anc_registration_charge", side_effect=ApiError(503, "odoo_error", "skip")):
                    enrolled = anc.enroll_patient("patient-f", {}, "cookie", path=self.db)
        pregnancy_id = enrolled["pregnancy"]["pregnancyId"]
        self.assertEqual(anc.charge_key(pregnancy_id), f"anc-registration:{pregnancy_id}")
        self.assertTrue(anc.charge_key(pregnancy_id).startswith("anc-registration:"))
        self.assertNotIn("visit", anc.charge_key(pregnancy_id))


class AncPermissions(unittest.TestCase):
    def test_reader_rejects_unrelated_roles(self) -> None:
        with patch.object(anc.reception, "require_registrar", side_effect=ApiError(403, "forbidden", "no")):
            with patch.object(
                anc,
                "_signed_in_staff",
                return_value={"roles": ["Pharmacist"], "privileges": []},
            ):
                with self.assertRaises(ApiError) as raised:
                    anc.require_anc_reader("cookie")
                self.assertEqual(raised.exception.status, 403)

    def test_writer_allows_clinical_privilege(self) -> None:
        with patch.object(anc.reception, "require_registrar", side_effect=ApiError(403, "forbidden", "no")):
            with patch.object(
                anc,
                "_signed_in_staff",
                return_value={"roles": [], "privileges": ["app:clinical"], "username": "doc"},
            ):
                user = anc.require_anc_writer("cookie")
                self.assertEqual(user["username"], "doc")

    def test_doctor_can_read_and_update_the_antenatal_card(self) -> None:
        doctor = {"roles": ["Abikan:Doctor"], "privileges": ["app:clinical"], "username": "dr.amina"}
        with patch.object(anc.reception, "require_registrar", side_effect=ApiError(403, "forbidden", "no")):
            with patch.object(anc, "_signed_in_staff", return_value=doctor):
                self.assertEqual(anc.require_anc_reader("cookie")["username"], "dr.amina")
                self.assertEqual(anc.require_anc_writer("cookie")["username"], "dr.amina")


class AncCardList(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "anc.sqlite3")
        anc.reset_for_tests()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_records_creation_time_and_lists_permanently(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy("patient-list-a", {"gravida": 1}, "cookie", path=self.db)
        pregnancy = created["pregnancy"]
        self.assertTrue(pregnancy["createdAt"])

        with (
            patch.object(anc, "require_anc_reader", return_value=_user()),
            patch.object(
                anc,
                "load_openmrs_patient",
                return_value={"uuid": "patient-list-a", "name": "Mary Test", "mrn": "ABK-1"},
            ),
        ):
            payload = anc.list_anc_cards("cookie", "/antenatal/cards?limit=50&startIndex=0", path=self.db)
        self.assertEqual(payload["total"], 1)
        self.assertNotIn("retentionDays", payload)
        row = payload["patients"][0]
        self.assertEqual(row["patientUuid"], "patient-list-a")
        self.assertEqual(row["name"], "Mary Test")
        self.assertEqual(row["hospitalNumber"], "ABK-1")
        self.assertEqual(row["enrolledAt"], pregnancy["createdAt"])
        self.assertTrue(row["enrolledAtLabel"])
        self.assertTrue(row["cardEnabled"])
        self.assertFalse(row["cardExpired"])
        self.assertNotIn("listUntil", row)
        self.assertNotIn("onList", row)

    def test_keeps_older_cards_on_the_list(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy("patient-old", {"gravida": 1}, "cookie", path=self.db)
        pregnancy_id = created["pregnancy"]["pregnancyId"]
        old_stamp = "2024-01-01T10:00:00+00:00"
        connection = anc._connect(self.db)
        try:
            connection.execute(
                """
                UPDATE anc_pregnancy
                SET created_at = ?,
                    fee_period_started_at = ?,
                    fee_expires_at = '2025-01-01T10:00:00+00:00'
                WHERE pregnancy_id = ?
                """,
                (old_stamp, old_stamp, pregnancy_id),
            )
            connection.commit()
        finally:
            connection.close()

        with (
            patch.object(anc, "require_anc_reader", return_value=_user()),
            patch.object(
                anc,
                "load_openmrs_patient",
                return_value={"uuid": "patient-old", "name": "Old Patient", "mrn": "ABK-9"},
            ),
        ):
            payload = anc.list_anc_cards("cookie", "/antenatal/cards?limit=50&startIndex=0", path=self.db)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["patients"][0]["patientUuid"], "patient-old")
        self.assertEqual(payload["patients"][0]["enrolledAt"], old_stamp)
        self.assertFalse(payload["patients"][0]["cardEnabled"])
        self.assertTrue(payload["patients"][0]["cardExpired"])

        with patch.object(anc, "require_anc_reader", return_value=_user()):
            summary = anc.get_patient_anc_summary("patient-old", "cookie", path=self.db)
        self.assertTrue(summary["hasAnc"])
        self.assertFalse(summary["cardEnabled"])
        self.assertTrue(summary["cardExpired"])

    def test_rejects_invalid_page_size(self) -> None:
        with self.assertRaises(ApiError) as raised:
            anc.parse_anc_list_query("/antenatal/cards?limit=25")
        self.assertEqual(raised.exception.code, "invalid_page_size")


class AncCardValidity(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "anc.sqlite3")
        anc.reset_for_tests()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_new_card_enabled_for_one_year(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy("patient-valid", {}, "cookie", path=self.db)
        pregnancy = created["pregnancy"]
        self.assertTrue(pregnancy["cardEnabled"])
        self.assertFalse(pregnancy["cardExpired"])
        self.assertTrue(pregnancy["expiresAt"])
        self.assertTrue(anc.patient_anc_card_enabled("patient-valid", path=self.db))

    def test_expires_after_one_year_and_blocks_visits(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy("patient-expired", {}, "cookie", path=self.db)
        pregnancy_id = created["pregnancy"]["pregnancyId"]
        connection = anc._connect(self.db)
        try:
            connection.execute(
                """
                UPDATE anc_pregnancy
                SET fee_period_started_at = '2024-01-01T10:00:00+00:00',
                    fee_expires_at = '2025-01-01T10:00:00+00:00'
                WHERE pregnancy_id = ?
                """,
                (pregnancy_id,),
            )
            connection.commit()
        finally:
            connection.close()

        self.assertFalse(anc.patient_anc_card_enabled("patient-expired", path=self.db))
        with self.assertRaises(ApiError) as raised:
            anc.require_anc_card_enabled("patient-expired", path=self.db)
        self.assertEqual(raised.exception.code, anc.ANC_CARD_DISABLED_CODE)

        with patch.object(anc, "require_anc_writer", return_value=_user()):
            with self.assertRaises(ApiError) as visit_error:
                anc.record_anc_visit(
                    "patient-expired",
                    {"pregnancyId": pregnancy_id, "weightKg": 70},
                    "cookie",
                    path=self.db,
                )
        self.assertEqual(visit_error.exception.code, anc.ANC_CARD_DISABLED_CODE)

    def test_paid_renewal_re_enables_card(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy("patient-renew", {}, "cookie", path=self.db)
        pregnancy_id = created["pregnancy"]["pregnancyId"]
        renewal_period = "renewal-period-1"
        connection = anc._connect(self.db)
        try:
            connection.execute(
                """
                UPDATE anc_pregnancy
                SET fee_period_id = ?,
                    fee_enabled_period_id = ?,
                    fee_period_started_at = '2024-01-01T10:00:00+00:00',
                    fee_expires_at = '2025-01-01T10:00:00+00:00'
                WHERE pregnancy_id = ?
                """,
                (renewal_period, pregnancy_id, pregnancy_id),
            )
            connection.commit()
        finally:
            connection.close()

        fake_line = {"price_unit": 2000}
        fake_sale = {"name": "SO001", "invoice_ids": [11], "state": "sale"}
        odoo = MagicMock()
        odoo.read.return_value = [{"payment_state": "paid", "amount_residual": 0}]

        with (
            patch.object(anc.reception, "odoo_reader", return_value=odoo),
            patch.object(anc, "load_currency", return_value={"symbol": "₦", "name": "NGN"}),
            patch.object(anc, "find_existing_anc_sale", return_value=(fake_line, fake_sale)),
            patch.object(anc, "format_money", return_value={"amount": 2000, "formatted": "₦2,000.00"}),
            patch.object(anc, "payment_state_label", return_value="PAID"),
        ):
            payload = anc._charge_payload(
                "cookie",
                "patient-renew",
                pregnancy_id,
                user=_user(),
                odoo=odoo,
                path=self.db,
            )
        self.assertTrue(payload["cardEnabled"])
        self.assertFalse(payload["cardExpired"])
        self.assertTrue(anc.patient_anc_card_enabled("patient-renew", path=self.db))

    def test_old_paid_fee_does_not_auto_renew_without_new_period(self) -> None:
        with patch.object(anc, "require_anc_writer", return_value=_user()):
            created = anc.start_pregnancy("patient-no-autorenew", {}, "cookie", path=self.db)
        pregnancy_id = created["pregnancy"]["pregnancyId"]
        connection = anc._connect(self.db)
        try:
            connection.execute(
                """
                UPDATE anc_pregnancy
                SET fee_period_id = ?,
                    fee_enabled_period_id = ?,
                    fee_period_started_at = '2024-01-01T10:00:00+00:00',
                    fee_expires_at = '2025-01-01T10:00:00+00:00'
                WHERE pregnancy_id = ?
                """,
                (pregnancy_id, pregnancy_id, pregnancy_id),
            )
            connection.commit()
        finally:
            connection.close()

        fake_line = {"price_unit": 2000}
        fake_sale = {"name": "SO001", "invoice_ids": [11], "state": "sale"}
        odoo = MagicMock()
        odoo.read.return_value = [{"payment_state": "paid", "amount_residual": 0}]

        with (
            patch.object(anc.reception, "odoo_reader", return_value=odoo),
            patch.object(anc, "load_currency", return_value={"symbol": "₦", "name": "NGN"}),
            patch.object(anc, "find_existing_anc_sale", side_effect=[(fake_line, fake_sale), None]),
            patch.object(anc, "format_money", return_value={"amount": 2000, "formatted": "₦2,000.00"}),
            patch.object(anc, "payment_state_label", return_value="PAID"),
        ):
            payload = anc._charge_payload(
                "cookie",
                "patient-no-autorenew",
                pregnancy_id,
                user=_user(),
                odoo=odoo,
                path=self.db,
            )
        self.assertFalse(payload["cardEnabled"])
        self.assertTrue(payload["cardExpired"])
        self.assertTrue(payload["canCreate"])
        self.assertNotEqual(payload["feePeriodId"], pregnancy_id)
        self.assertFalse(anc.patient_anc_card_enabled("patient-no-autorenew", path=self.db))


class AncVisitTypeHelpers(unittest.TestCase):
    def test_anc_visit_type_detection(self) -> None:
        self.assertTrue(anc.is_anc_visit_type("ANC"))
        self.assertTrue(anc.is_anc_visit_type("anc"))
        self.assertFalse(anc.is_anc_visit_type("OPD"))
        self.assertFalse(anc.is_anc_visit_type("Follow Up"))


class ExistingRegistrationUnaffected(unittest.TestCase):
    def test_reception_still_offers_original_visit_types(self) -> None:
        import registration_patient as arrival

        self.assertIn("OPD", arrival.RECEPTION_START_VISIT_TYPES)
        self.assertIn("FOLLOW UP", arrival.RECEPTION_START_VISIT_TYPES)
        self.assertIn("EMERGENCY", arrival.RECEPTION_START_VISIT_TYPES)
        self.assertIn("IPD", arrival.RECEPTION_START_VISIT_TYPES)
        self.assertIn("ANC", arrival.RECEPTION_START_VISIT_TYPES)
        self.assertEqual(arrival.VISIT_LABELS["ANC"], "Antenatal Care (ANC)")

    def test_clinical_queue_includes_anc_without_emergency(self) -> None:
        import clinical_queue as queue

        self.assertTrue(queue.is_queue_visit_type("ANC"))
        self.assertTrue(queue.is_queue_visit_type("OPD"))
        self.assertFalse(queue.is_queue_visit_type("EMERGENCY"))
        self.assertFalse(queue.is_queue_visit_type("IPD"))


if __name__ == "__main__":
    unittest.main()
