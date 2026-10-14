"""Active-account enforcement tests. No live OpenMRS calls."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import server


def session_payload(*, authenticated: bool = True) -> dict:
    return {
        "authenticated": authenticated,
        "user": {"uuid": "user-1", "username": "staff.abikan"} if authenticated else None,
    }


class ActiveAccountEnforcement(unittest.TestCase):
    def test_active_user_existing_session_is_allowed(self) -> None:
        with (
            patch.object(server, "openmrs_get", return_value=session_payload()),
            patch.object(
                server,
                "openmrs_service_get",
                return_value={"uuid": "user-1", "retired": False},
            ) as state,
            patch.object(server, "invalidate_openmrs_session") as invalidate,
        ):
            result = server.require_session("JSESSIONID=active")
        self.assertTrue(result["authenticated"])
        state.assert_called_once()
        invalidate.assert_not_called()

    def test_disabled_user_existing_session_is_denied_and_invalidated(self) -> None:
        with (
            patch.object(server, "openmrs_get", return_value=session_payload()),
            patch.object(
                server,
                "openmrs_service_get",
                return_value={"uuid": "user-1", "retired": True},
            ),
            patch.object(server, "invalidate_openmrs_session") as invalidate,
        ):
            with self.assertRaises(server.ApiError) as caught:
                server.require_session("JSESSIONID=disabled")
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.code, "account_disabled")
        invalidate.assert_called_once_with("JSESSIONID=disabled")

    def test_disabled_user_fresh_login_is_denied_by_unauthenticated_session(self) -> None:
        with (
            patch.object(
                server,
                "openmrs_get",
                return_value=session_payload(authenticated=False),
            ),
            patch.object(server, "openmrs_service_get") as state,
        ):
            with self.assertRaises(server.ApiError) as caught:
                server.require_session("")
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.code, "unauthenticated")
        state.assert_not_called()

    def test_reenabled_user_fresh_session_is_allowed(self) -> None:
        with (
            patch.object(server, "openmrs_get", return_value=session_payload()),
            patch.object(
                server,
                "openmrs_service_get",
                return_value={"uuid": "user-1", "retired": False},
            ),
        ):
            result = server.require_session("JSESSIONID=fresh")
        self.assertEqual(result["user"]["username"], "staff.abikan")


if __name__ == "__main__":
    unittest.main()
