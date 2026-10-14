"""Reception can close a completed OPD visit. IPD and clinical records stay intact."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import registration as reception
import registration_patient as arrival
from server import ApiError


PATIENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OPD_VISIT = "11111111-1111-4111-8111-111111111111"
IPD_VISIT = "22222222-2222-4222-8222-222222222222"
CLOSED_VISIT = "33333333-3333-4333-8333-333333333333"
COOKIE = "JSESSIONID=rec"


def open_visit(uuid: str = OPD_VISIT, patient: str = PATIENT_A, **overrides: object) -> dict[str, object]:
    row = {
        "uuid": uuid,
        "startDatetime": "2026-09-02T08:00:00.000+0000",
        "open": True,
        "visitType": "OPD",
        "location": "OPD-1",
        "patient": {"uuid": patient},
    }
    row.update(overrides)
    return row


class CloseVisitAuthorizationTests(unittest.TestCase):
    def test_reception_can_close_an_open_opd_visit(self) -> None:
        closed = open_visit(open=False)
        posts: list[tuple[str, dict[str, object]]] = []
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}) as gate,
            patch.object(reception, "load_visit", side_effect=[open_visit(), closed]),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(arrival, "_now_openmrs", return_value="2026-09-03T11:00:00.000+0000"),
            patch.object(
                arrival,
                "_openmrs_json",
                side_effect=lambda path, cookie, **kwargs: posts.append((path, kwargs.get("payload") or {}))
                or {"uuid": OPD_VISIT, "stopDatetime": "2026-09-03T11:00:00.000+0000"},
            ),
        ):
            result = arrival.close_visit(PATIENT_A, OPD_VISIT, COOKIE)
        gate.assert_called_once_with(COOKIE)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["uuid"], OPD_VISIT)
        self.assertEqual(result["stopDatetime"], "2026-09-03T11:00:00.000+0000")
        self.assertFalse(result["open"])
        self.assertEqual(result["message"], arrival.CLOSE_VISIT_SUCCESS_MESSAGE)
        self.assertEqual(len(posts), 1)
        self.assertIn(f"/visit/{OPD_VISIT}", posts[0][0])
        self.assertEqual(posts[0][1], {"stopDatetime": "2026-09-03T11:00:00.000+0000"})

    def test_unauthorized_roles_cannot_close(self) -> None:
        with patch.object(
            arrival,
            "require_registrar",
            side_effect=ApiError(403, "forbidden", "This action requires Reception access."),
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.close_visit(PATIENT_A, OPD_VISIT, "JSESSIONID=doc")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.code, "forbidden")


class CloseVisitSafetyTests(unittest.TestCase):
    def test_already_closed_visit_cannot_be_closed_again(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}),
            patch.object(reception, "load_visit", return_value=open_visit(CLOSED_VISIT, open=False)),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(arrival, "_openmrs_json") as post,
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.close_visit(PATIENT_A, CLOSED_VISIT, COOKIE)
        post.assert_not_called()
        self.assertEqual(caught.exception.code, arrival.VISIT_ALREADY_CLOSED_CODE)

    def test_ipd_cannot_be_closed_by_opd_close_visit(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}),
            patch.object(reception, "load_visit", return_value=open_visit(IPD_VISIT, visitType="IPD")),
            patch.object(arrival, "_patient_occupied", return_value=True),
            patch.object(arrival, "_admission_visit_context", return_value={"visitUuid": IPD_VISIT}),
            patch.object(arrival, "_openmrs_json") as post,
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.close_visit(PATIENT_A, IPD_VISIT, COOKIE)
        post.assert_not_called()
        self.assertEqual(caught.exception.code, arrival.CANNOT_CLOSE_ADMISSION_CODE)

    def test_active_ipd_visit_is_left_open(self) -> None:
        allowed, code, _message = arrival.can_close_outpatient_visit(
            open_visit(IPD_VISIT, visitType="IPD"),
            admission_active=True,
            admission_visit_uuid=IPD_VISIT,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, arrival.CANNOT_CLOSE_ADMISSION_CODE)

    def test_admission_in_progress_blocks_opd_close_even_if_visit_uuid_differs(self) -> None:
        allowed, code, _message = arrival.can_close_outpatient_visit(
            open_visit(OPD_VISIT, visitType="OPD"),
            admission_active=True,
            admission_visit_uuid=IPD_VISIT,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, arrival.CANNOT_CLOSE_ADMISSION_CODE)
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}),
            patch.object(reception, "load_visit", return_value=open_visit()),
            patch.object(arrival, "_patient_occupied", return_value=True),
            patch.object(arrival, "_admission_visit_context", return_value={"visitUuid": IPD_VISIT}),
            patch.object(arrival, "_openmrs_json") as post,
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.close_visit(PATIENT_A, OPD_VISIT, COOKIE)
        post.assert_not_called()
        self.assertEqual(caught.exception.code, arrival.CANNOT_CLOSE_ADMISSION_CODE)

    def test_wrong_patient_is_rejected_before_close(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}),
            patch.object(
                reception,
                "load_visit",
                side_effect=ApiError(409, "wrong_patient", "This visit does not belong to this patient."),
            ),
            patch.object(arrival, "_openmrs_json") as post,
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.close_visit(PATIENT_B, OPD_VISIT, COOKIE)
        post.assert_not_called()
        self.assertEqual(caught.exception.code, "wrong_patient")

    def test_close_does_not_rewrite_encounters_or_consultation(self) -> None:
        source = Path(arrival.__file__).read_text(encoding="utf-8")
        close_fn = source.split("def close_visit", 1)[1].split("\n\n\n", 1)[0]
        self.assertIn("stopDatetime", close_fn)
        self.assertNotIn("/encounter", close_fn)
        self.assertNotIn("bahmnicore/visit/endVisit", close_fn)
        self.assertNotIn("obs", close_fn)
        self.assertNotIn("admin_audit", close_fn)

    def test_closed_visit_allows_a_later_create_visit(self) -> None:
        created = {"uuid": "new-opd", "startDatetime": "2026-09-03T12:00:00.000+0000"}
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(
                arrival,
                "load_visit_types",
                return_value=[
                    {"uuid": "opd-type", "name": "OPD", "label": "General Outpatient", "bucket": "outpatient"}
                ],
            ),
            patch.object(arrival, "load_login_locations", return_value=[{"uuid": "opd-1", "name": "OPD-1"}]),
            patch.object(arrival, "locations_for_visit", return_value=[{"uuid": "opd-1", "name": "OPD-1"}]),
            patch("daily_visit_number.ignore_client_number"),
            patch("daily_visit_number.begin_request", return_value=None),
            patch("daily_visit_number.create_visit_with_number", return_value=(created, "022")),
            patch("daily_visit_number.finish_request"),
        ):
            result = arrival.start_visit(
                PATIENT_A,
                {"visitTypeUuid": "opd-type", "locationUuid": "opd-1", "requestId": "after-close"},
                COOKIE,
            )
        self.assertTrue(result["created"])
        self.assertEqual(result["uuid"], "new-opd")

    def test_open_visit_still_blocks_a_duplicate_create(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "reception.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=open_visit()),
            patch("daily_visit_number.create_visit_with_number") as create,
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": "opd-type"}, COOKIE)
        create.assert_not_called()
        self.assertEqual(result["code"], reception.VISIT_ALREADY_OPEN_CODE)

    def test_no_24_hour_scheduler_or_expiry_is_introduced(self) -> None:
        source = Path(arrival.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"24.?hour|visitExpireHours|auto.?clos|scheduler")
        server = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        self.assertIn('parts[5] == "close"', server)
        self.assertIn("close_visit", server)
        self.assertNotRegex(server, r"visitExpireHours|Close Stale Visits")


if __name__ == "__main__":
    unittest.main()
