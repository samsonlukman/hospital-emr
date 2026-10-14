"""Nurses are told when a ward dose reaches its time."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import medication_administration as mar
import notifications as notes


PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VISIT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SLOT = "cccccccc-cccc-cccc-cccc-cccccccccccc"


class DueDoseNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-due-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        notes.reset_for_tests(path=self.db)

    def tearDown(self) -> None:
        notes.reset_for_tests(path=self.db)
        Path(self.db).unlink(missing_ok=True)

    def test_a_due_ward_dose_is_announced_once_and_cleared_when_it_is_no_longer_due(self) -> None:
        due = [(
            SLOT,
            PATIENT,
            VISIT,
            "Musiliu Rofiat",
            "ABC205104",
            "Nifedipine",
            "10",
            "mg",
            "Twice a day",
            "2026-10-14 14:00:00",
            "Tablet",
        )]
        with patch("openmrs_sql.fetch_all", return_value=due):
            self.assertEqual(mar.publish_due_dose_notifications(path=self.db), 1)
            self.assertEqual(mar.publish_due_dose_notifications(path=self.db), 0)
        with (
            patch.object(notes.core, "require_session"),
            patch.object(
                notes.reception,
                "load_openmrs_user",
                return_value={"username": "nurse", "roles": ["Abikan:Nursing"], "privileges": []},
            ),
        ):
            listed = notes.list_for_session("cookie", path=self.db)
        self.assertEqual(listed["pendingCount"], 1)
        message = listed["notifications"][0]["message"]
        self.assertIn("Nifedipine", message)
        self.assertIn("10 mg", message)
        self.assertIn("Twice a day", message)
        self.assertIn("3:00 PM", message)
        self.assertIn("Musiliu Rofiat", message)
        self.assertEqual(listed["notifications"][0]["actionHref"], f"#/nursing/patient/{PATIENT}")

        with patch("openmrs_sql.fetch_all", return_value=[]):
            mar.publish_due_dose_notifications(path=self.db)
        with (
            patch.object(notes.core, "require_session"),
            patch.object(
                notes.reception,
                "load_openmrs_user",
                return_value={"username": "nurse", "roles": ["Abikan:Nursing"], "privileges": []},
            ),
        ):
            cleared = notes.list_for_session("cookie", path=self.db)
        self.assertEqual(cleared["pendingCount"], 0)

    def test_an_injection_is_not_announced_as_a_tablet(self) -> None:
        due = [(
            SLOT,
            PATIENT,
            VISIT,
            "Taiwo Hassan",
            "ABC204835",
            "PARACETAMOL INJECTION",
            "1",
            "Tablet",
            "Once a day",
            "2026-10-14 14:00:00",
            "Injection",
        )]
        with patch("openmrs_sql.fetch_all", return_value=due):
            mar.publish_due_dose_notifications(path=self.db)
        with (
            patch.object(notes.core, "require_session"),
            patch.object(
                notes.reception,
                "load_openmrs_user",
                return_value={"username": "nurse", "roles": ["Abikan:Nursing"], "privileges": []},
            ),
        ):
            listed = notes.list_for_session("cookie", path=self.db)
        message = listed["notifications"][0]["message"]
        self.assertIn("1 Injection", message)
        self.assertNotIn("Tablet", message)
