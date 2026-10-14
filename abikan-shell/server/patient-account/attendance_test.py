"""Staff attendance, staff-code assignment, and Admin log tests. No live OpenMRS writes."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import admin_audit
import attendance
import attendance_store as store
from server import ApiError

IBRAHIM = {
    "personUuid": "person-ibrahim",
    "userUuid": "user-ibrahim",
    "username": "pharmacy.abikan",
    "displayName": "Ibrahim Musa",
    "workplaceId": "pharmacy",
    "workplaceLabel": "Pharmacy",
    "preferredDepartment": {"id": "pharmacy", "label": "Pharmacy"},
    "departments": [{"id": "pharmacy", "label": "Pharmacy", "roleLabel": "Pharmacist"}],
    "staffCategory": "pharmacy",
    "staffCategoryLabel": "Pharmacy",
    "accountType": "staff",
}
AISHA = {
    "personUuid": "person-aisha",
    "userUuid": "user-aisha",
    "username": "nurse.abikan",
    "displayName": "Aisha Bello",
    "workplaceId": "nursing",
    "workplaceLabel": "Nursing",
    "preferredDepartment": {"id": "nursing", "label": "Nursing"},
    "departments": [{"id": "nursing", "label": "Nursing", "roleLabel": "Nurse"}],
    "staffCategory": "nursing",
    "staffCategoryLabel": "Nursing",
    "accountType": "staff",
}
ADMIN = {
    "uuid": "user-admin",
    "username": "admin.abikan",
    "roles": ["Abikan:Hospital Admin"],
    "privileges": ["abikan:admin:staff"],
}
TINY_JPEG = "data:image/jpeg;base64," + base64.b64encode(
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


def _staff_lookup(staff_id: str) -> dict:
    if staff_id in {IBRAHIM["personUuid"], IBRAHIM["userUuid"], IBRAHIM["username"]}:
        return dict(IBRAHIM)
    if staff_id in {AISHA["personUuid"], AISHA["userUuid"], AISHA["username"]}:
        return dict(AISHA)
    raise ApiError(404, "staff_not_found", "That staff record was not found.")


class AttendanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.db = str(Path(self.folder.name) / "attendance.sqlite3")
        self.audit = str(Path(self.folder.name) / "admin-audit.sqlite3")
        self.photos = str(Path(self.folder.name) / "attendance-photos")
        self.env = patch.dict(
            os.environ,
            {
                "ABIKAN_ENVIRONMENT": "development",
                "ABIKAN_ATTENDANCE_DB": self.db,
                "ABIKAN_ADMIN_AUDIT_DB": self.audit,
                "ABIKAN_ATTENDANCE_PHOTOS": self.photos,
                "ABIKAN_HOSPITAL_TIMEZONE": "Africa/Lagos",
                "ABIKAN_ATTENDANCE_TERMINAL_NAME": "Reception Attendance Terminal",
            },
            clear=False,
        )
        self.env.start()
        store.ATTENDANCE_DB_PATH = self.db
        admin_audit.AUDIT_DB_PATH = self.audit
        self.staff_patch = patch.object(attendance, "staff_snapshot", side_effect=_staff_lookup)
        self.staff_patch.start()
        self.admin_patch = patch.object(
            attendance.administration,
            "require_hospital_admin",
            return_value=ADMIN,
        )
        self.admin_patch.start()
        self.authority_patch = patch.object(
            attendance.administration,
            "reject_arbitrary_authority",
            return_value=None,
        )
        self.authority_patch.start()

    def tearDown(self) -> None:
        self.authority_patch.stop()
        self.admin_patch.stop()
        self.staff_patch.stop()
        self.env.stop()
        self.folder.cleanup()

    def _assign(self, person_uuid: str, code: str, replace: bool = False) -> dict:
        return attendance.set_staff_attendance_code(
            person_uuid,
            {"code": code, "replace": replace, "requestId": "req-code"},
            "cookie",
        )

    def _sign_in(self, code: str, now: datetime | None = None, extra: dict | None = None) -> dict:
        body = {"code": code, "photo": TINY_JPEG, **(extra or {})}
        if now is None:
            return attendance.sign_in(body, {}, "", "test-terminal")
        with patch.object(attendance, "server_now", return_value=now):
            return attendance.sign_in(body, {}, "", "test-terminal")

    def _sign_out(self, code: str, now: datetime | None = None, extra: dict | None = None) -> dict:
        body = {"code": code, **(extra or {})}
        if now is None:
            return attendance.sign_out(body, {}, "", "test-terminal")
        with patch.object(attendance, "server_now", return_value=now):
            return attendance.sign_out(body, {}, "", "test-terminal")

    def _status(self, code: str, now: datetime | None = None) -> dict:
        body = {"code": code}
        if now is None:
            return attendance.lookup_status(body, {}, "", "test-terminal")
        with patch.object(attendance, "server_now", return_value=now):
            return attendance.lookup_status(body, {}, "", "test-terminal")

    def test_invalid_code_is_rejected_without_staff_details(self) -> None:
        with self.assertRaises(ApiError) as caught:
            self._sign_in("999999")
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.code, "code_unknown")
        self.assertEqual(str(caught.exception), "That staff code is not recognized.")
        self.assertNotIn("Ibrahim", str(caught.exception))

    def test_status_lookup_does_not_create_a_session(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 4, 32, tzinfo=timezone.utc)
        status = self._status("482193", now)
        self.assertEqual(status["attendanceStatus"], "NOT_SIGNED_IN")
        self.assertEqual(status["availableAction"], "SIGN_IN")
        self.assertEqual(status["staff"]["displayName"], "Ibrahim Musa")
        self.assertIsNone(status["session"])
        listing = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
        self.assertEqual(listing["total"], 0)

    def test_status_lookup_offers_sign_out_after_sign_in(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", now)
        status = self._status("482193", now + timedelta(hours=2))
        self.assertEqual(status["attendanceStatus"], "SIGNED_IN")
        self.assertEqual(status["availableAction"], "SIGN_OUT")
        self.assertEqual(status["session"]["signInLocalTime"], "08:02:00")

    def test_status_lookup_after_sign_out_has_no_action(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", now)
        self._sign_out("482193", now + timedelta(hours=8))
        status = self._status("482193", now + timedelta(hours=9))
        self.assertEqual(status["attendanceStatus"], "SIGNED_OUT")
        self.assertEqual(status["availableAction"], "")
        self.assertEqual(status["message"], "Attendance completed for today")

    def test_person_uuid_cannot_be_used_as_a_staff_code(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        with self.assertRaises(ApiError) as caught:
            attendance.sign_in(
                {"personUuid": IBRAHIM["personUuid"], "staffId": IBRAHIM["personUuid"]},
                {},
                "",
                "test-terminal",
            )
        self.assertEqual(caught.exception.code, "invalid_staff_code")

    def test_sign_in_creates_one_session_with_server_timestamp(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 4, 32, tzinfo=timezone.utc)
        result = self._sign_in("482193", now)
        self.assertEqual(result["message"], "Signed in successfully")
        self.assertEqual(result["attendanceStatus"], "SIGNED_IN")
        self.assertEqual(result["staff"]["displayName"], "Ibrahim Musa")
        self.assertEqual(result["staff"]["workplaceLabel"], "Pharmacy")
        self.assertEqual(result["session"]["signInLocalTime"], "08:04:32")
        self.assertTrue(result["session"]["signInAt"].startswith("2026-09-18"))
        self.assertEqual(result["session"]["localDate"], "2026-09-18")
        self.assertFalse(result["alreadyRecorded"])
        self.assertTrue(result["session"]["hasPhoto"])
        dumped = json.dumps(result)
        self.assertNotIn("482193", dumped)
        self.assertNotIn("/9j/", dumped)

    def test_sign_in_requires_a_photo(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 4, 32, tzinfo=timezone.utc)
        with self.assertRaises(ApiError) as caught:
            with patch.object(attendance, "server_now", return_value=now):
                attendance.sign_in({"code": "482193"}, {}, "", "test-terminal")
        self.assertEqual(caught.exception.code, "photo_required")
        listing = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
        self.assertEqual(listing["total"], 0)

    def test_sign_in_photo_is_kept_for_today_only(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        day_one = datetime(2026, 9, 18, 7, 4, 32, tzinfo=timezone.utc)
        created = self._sign_in("482193", day_one)
        with patch.object(attendance, "server_now", return_value=day_one):
            listing = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
            data, content_type, filename = attendance.session_photo(created["session"]["id"], "cookie")
        self.assertTrue(listing["sessions"][0]["hasPhoto"])
        self.assertIn("/admin/log/", listing["sessions"][0]["photoHref"])
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8\xff"))
        self.assertEqual(filename, "sign-in.jpg")
        photo_files = list(Path(self.photos).rglob("*"))
        self.assertTrue(any(item.is_file() for item in photo_files))
        next_day = datetime(2026, 9, 19, 7, 0, tzinfo=timezone.utc)
        with patch.object(attendance, "server_now", return_value=next_day):
            later = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
            with self.assertRaises(ApiError) as caught:
                attendance.session_photo(created["session"]["id"], "cookie")
        self.assertEqual(later["total"], 1)
        self.assertEqual(later["sessions"][0]["displayName"], "Ibrahim Musa")
        self.assertEqual(later["sessions"][0]["signInLocalTime"], "08:04:32")
        self.assertFalse(later["sessions"][0]["hasPhoto"])
        self.assertNotIn("photoHref", later["sessions"][0])
        self.assertEqual(caught.exception.code, "photo_not_found")
        self.assertFalse(any(item.is_file() for item in Path(self.photos).rglob("*")))

    def test_does_not_trust_client_timestamp(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 15, tzinfo=timezone.utc)
        result = self._sign_in(
            "482193",
            now,
            extra={"timestamp": "1999-01-01T00:00:00Z", "occurredAt": "1999-01-01T00:00:00Z"},
        )
        self.assertTrue(result["session"]["signInAt"].startswith("2026-09-18"))
        self.assertEqual(result["session"]["localDate"], "2026-09-18")

    def test_second_sign_in_same_day_returns_current_status(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        first = self._sign_in("482193", now)
        second = self._sign_in("482193", now + timedelta(hours=2))
        self.assertTrue(second["alreadyRecorded"])
        self.assertEqual(second["message"], "Already signed in today")
        self.assertEqual(second["session"]["id"], first["session"]["id"])
        self.assertEqual(second["session"]["signInLocalTime"], first["session"]["signInLocalTime"])
        listing = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
        self.assertEqual(listing["total"], 1)

    def test_sign_out_requires_sign_in_today(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        with self.assertRaises(ApiError) as caught:
            self._sign_out("482193", datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc))
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.code, "sign_in_required")

    def test_sign_out_completes_the_day(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", now)
        done = self._sign_out("482193", now + timedelta(hours=9, minutes=10))
        self.assertEqual(done["message"], "Attendance completed for today")
        self.assertEqual(done["attendanceStatus"], "SIGNED_OUT")
        self.assertEqual(done["session"]["signInLocalTime"], "08:02:00")
        self.assertEqual(done["session"]["signOutLocalTime"], "17:12:00")
        self.assertFalse(done["alreadyRecorded"])

    def test_after_sign_out_cannot_sign_in_or_out_again(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", now)
        first_out = self._sign_out("482193", now + timedelta(hours=8))
        again_in = self._sign_in("482193", now + timedelta(hours=9))
        again_out = self._sign_out("482193", now + timedelta(hours=10))
        self.assertTrue(again_in["alreadyRecorded"])
        self.assertEqual(again_in["attendanceStatus"], "SIGNED_OUT")
        self.assertEqual(again_in["session"]["id"], first_out["session"]["id"])
        self.assertTrue(again_out["alreadyRecorded"])
        self.assertEqual(again_out["session"]["signOutLocalTime"], first_out["session"]["signOutLocalTime"])
        listing = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
        self.assertEqual(listing["total"], 1)

    def test_next_calendar_day_can_sign_in_again(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        first_day = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", first_day)
        self._sign_out("482193", first_day + timedelta(hours=8))
        next_day = datetime(2026, 9, 19, 7, 5, tzinfo=timezone.utc)
        again = self._sign_in("482193", next_day)
        self.assertFalse(again["alreadyRecorded"])
        self.assertEqual(again["session"]["localDate"], "2026-09-19")
        self.assertEqual(again["attendanceStatus"], "SIGNED_IN")

    def test_invalid_codes_are_rate_limited(self) -> None:
        now = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)
        for _ in range(store.THROTTLE_MAX_FAILURES):
            with self.assertRaises(ApiError) as caught:
                self._sign_in("000000", now)
            self.assertEqual(caught.exception.code, "code_unknown")
        with self.assertRaises(ApiError) as blocked:
            self._sign_in("000000", now + timedelta(seconds=1))
        self.assertEqual(blocked.exception.status, 429)
        self.assertEqual(blocked.exception.code, "too_many_attempts")
        self.assertNotIn("Ibrahim", str(blocked.exception))

    def test_admin_log_filters_by_date_staff_workplace_and_status(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        self._assign(AISHA["personUuid"], "193482")
        now = datetime(2026, 9, 18, 7, 2, 14, tzinfo=timezone.utc)
        self._sign_in("482193", now)
        self._sign_in("193482", now + timedelta(minutes=13))
        self._sign_out("482193", now + timedelta(hours=8))
        today = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
        self.assertEqual(today["displayDate"], "18 September 2026")
        self.assertEqual(today["total"], 2)
        pharmacy = attendance.list_sessions(
            "cookie", "/admin/log?date=2026-09-18&department=pharmacy"
        )
        self.assertEqual(pharmacy["total"], 1)
        self.assertEqual(pharmacy["sessions"][0]["workplaceLabel"], "Pharmacy")
        signed_out = attendance.list_sessions(
            "cookie", "/admin/log?date=2026-09-18&status=SIGNED_OUT"
        )
        self.assertEqual(signed_out["total"], 1)
        self.assertEqual(signed_out["sessions"][0]["displayName"], "Ibrahim Musa")
        search = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18&q=aisha")
        self.assertEqual(search["total"], 1)
        yesterday = attendance.list_sessions("cookie", "/admin/log?date=2026-09-17")
        self.assertEqual(yesterday["total"], 0)
        self.assertEqual(yesterday["nextDate"], "2026-09-18")

    def test_workplace_snapshot_is_not_rewritten(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", now)

        def moved(staff_id: str) -> dict:
            row = _staff_lookup(staff_id)
            if staff_id == IBRAHIM["personUuid"]:
                row = dict(row)
                row["workplaceId"] = "administration"
                row["workplaceLabel"] = "Administration"
                row["preferredDepartment"] = {"id": "administration", "label": "Administration"}
            return row

        self.staff_patch.stop()
        moved_patch = patch.object(attendance, "staff_snapshot", side_effect=moved)
        moved_patch.start()
        try:
            historic = attendance.list_sessions("cookie", "/admin/log?date=2026-09-18")
            self.assertEqual(historic["sessions"][0]["workplaceLabel"], "Pharmacy")
            later_time = datetime(2026, 10, 1, 7, 0, tzinfo=timezone.utc)
            later = self._sign_in("482193", later_time)
            self.assertEqual(later["staff"]["workplaceLabel"], "Administration")
            self.assertEqual(later["session"]["workplaceLabel"], "Administration")
        finally:
            moved_patch.stop()
            self.staff_patch = patch.object(attendance, "staff_snapshot", side_effect=_staff_lookup)
            self.staff_patch.start()

    def test_staff_code_assignment_is_audited(self) -> None:
        assigned = self._assign(IBRAHIM["personUuid"], "482193")
        status = attendance.staff_attendance_code(IBRAHIM["personUuid"], "cookie")
        self.assertTrue(status["attendanceCode"]["hasCode"])
        self.assertEqual(status["attendanceCode"]["code"], "482193")
        self.assertEqual(status["attendanceCode"]["audit"][0]["actionLabel"], "Set staff attendance code")
        dumped = json.dumps(assigned)
        events = admin_audit.list_admin_events(limit=10, offset=0)
        self.assertTrue(any(row["action"] == "ADMIN_ATTENDANCE_CODE_SET" for row in events["events"]))
        for row in events["events"]:
            self.assertNotIn("482193", json.dumps(row))
        self.assertIn("attendanceCode", dumped)

    def test_cannot_assign_same_code_to_another_staff(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        with self.assertRaises(ApiError) as caught:
            self._assign(AISHA["personUuid"], "482193")
        self.assertEqual(caught.exception.code, "code_in_use")

    def test_replace_code_invalidates_the_old_one(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        attendance.set_staff_attendance_code(
            IBRAHIM["personUuid"],
            {"code": "193482", "replace": True, "requestId": "req-2"},
            "cookie",
        )
        with self.assertRaises(ApiError) as caught:
            self._sign_in("482193")
        self.assertEqual(caught.exception.code, "code_unknown")
        signed = self._sign_in("193482", datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc))
        self.assertEqual(signed["staff"]["displayName"], "Ibrahim Musa")

    def test_ordinary_staff_cannot_set_codes_or_read_admin_log(self) -> None:
        self.admin_patch.stop()
        denied = patch.object(
            attendance.administration,
            "require_hospital_admin",
            side_effect=ApiError(403, "forbidden", "This action requires Hospital Administration."),
        )
        denied.start()
        try:
            with self.assertRaises(ApiError) as setting:
                attendance.set_staff_attendance_code(
                    IBRAHIM["personUuid"],
                    {"code": "111111", "requestId": "r"},
                    "cookie",
                )
            self.assertEqual(setting.exception.status, 403)
            with self.assertRaises(ApiError) as listing:
                attendance.list_sessions("cookie", "/admin/log")
            self.assertEqual(listing.exception.status, 403)
            with self.assertRaises(ApiError) as photo:
                attendance.session_photo("session-1", "cookie")
            self.assertEqual(photo.exception.status, 403)
        finally:
            denied.stop()
            self.admin_patch = patch.object(
                attendance.administration,
                "require_hospital_admin",
                return_value=ADMIN,
            )
            self.admin_patch.start()

    def test_sessions_persist_in_sqlite(self) -> None:
        self._assign(IBRAHIM["personUuid"], "482193")
        now = datetime(2026, 9, 18, 7, 2, tzinfo=timezone.utc)
        self._sign_in("482193", now)
        self.assertTrue(Path(self.db).is_file())
        reopened = store.search_sessions(local_date="2026-09-18", path=self.db)
        self.assertEqual(reopened[1], 1)
        self.assertEqual(reopened[0][0]["displayName"], "Ibrahim Musa")

    def test_terminal_config_is_code_based(self) -> None:
        payload = attendance.terminal_config()
        self.assertEqual(payload["title"], "Staff Log")
        self.assertEqual(payload["prompt"], "Enter your staff code.")
        self.assertEqual(payload["timezone"], "Africa/Lagos")
        self.assertNotIn("fingerprint", json.dumps(payload).lower())
        self.assertNotIn("biometric", json.dumps(payload).lower())

    def test_server_source_registers_attendance_routes(self) -> None:
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        self.assertIn('parts == ["attendance", "terminal"]', source)
        self.assertIn('["attendance", "status"]', source)
        self.assertIn('["attendance", "sign-in"]', source)
        self.assertIn('["attendance", "sign-out"]', source)
        self.assertIn("staff_log.lookup_status", source)
        self.assertIn("staff_log.sign_in", source)
        self.assertIn("staff_log.sign_out", source)
        self.assertIn('parts == ["admin", "log"]', source)
        self.assertIn("staff_log.session_photo", source)
        self.assertIn("staff_log.set_staff_attendance_code", source)
        self.assertNotIn("staff_log.identify", source)
        self.assertNotIn("enroll_biometric", source)
        self.assertNotIn('parts == ["attendance", "identify"]', source)


class AttendanceTimeTests(unittest.TestCase):
    def test_hospital_timezone_converts_utc_to_lagos(self) -> None:
        moment = datetime(2026, 9, 18, 7, 4, 32, tzinfo=timezone.utc)
        with patch.dict(os.environ, {"ABIKAN_HOSPITAL_TIMEZONE": "Africa/Lagos"}, clear=False):
            utc, local_date, local_time, _display = attendance.local_parts(moment)
        self.assertEqual(local_date, "2026-09-18")
        self.assertEqual(local_time, "08:04:32")
        self.assertEqual(utc.tzinfo, timezone.utc)
        self.assertEqual(moment.astimezone(ZoneInfo("Africa/Lagos")).hour, 8)


if __name__ == "__main__":
    unittest.main()
