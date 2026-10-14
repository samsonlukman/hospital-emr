"""Durable Administration audit tests using a temporary SQLite file."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import admin_audit


class DurableAdminAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "admin-audit.sqlite3")
        self.actor = {"uuid": "admin-1", "username": "hospitaladmin.abikan"}

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_pending_event_is_finalized_and_survives_new_connections(self) -> None:
        event_id = admin_audit.start_admin_event(
            actor=self.actor,
            target_user_uuid="user-1",
            target_username="doctor.test",
            action="ADMIN_DISABLE_USER",
            previous_state={"enabled": True},
            new_state={"enabled": False},
            details={},
            request_id="request-1",
            path=self.path,
        )
        admin_audit.finish_admin_event(
            event_id,
            outcome="success",
            new_state={"enabled": False},
            details={"retired": True},
            path=self.path,
        )
        first_read = admin_audit.read_admin_events(path=self.path)
        second_read = admin_audit.read_admin_events(path=self.path)
        self.assertEqual(len(first_read), 1)
        self.assertEqual(second_read[0]["event_id"], event_id)
        self.assertEqual(second_read[0]["outcome"], "success")
        self.assertEqual(second_read[0]["previous_state"], {"enabled": True})
        self.assertEqual(second_read[0]["new_state"], {"enabled": False})

    def test_password_cookie_and_secret_are_redacted(self) -> None:
        admin_audit.record_admin_event(
            actor=self.actor,
            target_username="doctor.test",
            action="ADMIN_CREATE_USER",
            previous_state=None,
            new_state={
                "initialPassword": "Temporary123",
                "nested": {"cookie": "JSESSIONID=secret", "safe": "clinical"},
            },
            details={"authorization": "Basic secret", "token": "secret"},
            outcome="failure",
            error_code="test",
            request_id="request-2",
            path=self.path,
        )
        event = admin_audit.read_admin_events(path=self.path)[0]
        serialized = str(event)
        self.assertNotIn("Temporary123", serialized)
        self.assertNotIn("JSESSIONID", serialized)
        self.assertNotIn("Basic secret", serialized)
        self.assertEqual(event["new_state"]["nested"]["safe"], "clinical")

    def test_failure_outcome_and_request_id_are_durable(self) -> None:
        admin_audit.record_admin_event(
            actor=self.actor,
            target_username="doctor.test",
            action="ADMIN_CREATE_USER",
            outcome="failure",
            error_code="duplicate_username",
            request_id="request-3",
            path=self.path,
        )
        event = admin_audit.read_admin_events(path=self.path)[0]
        self.assertEqual(event["outcome"], "failure")
        self.assertEqual(event["error_code"], "duplicate_username")
        self.assertEqual(event["request_id"], "request-3")


if __name__ == "__main__":
    unittest.main()
