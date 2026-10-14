"""HTTP route registration tests — catches missing laboratory order detail route."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import laboratory
import inpatient
import medication_administration
import server


def _handler(path: str) -> server.Handler:
    conn = Mock()
    conn.makefile.return_value = io.BytesIO()
    handler = server.Handler(conn, ("127.0.0.1", 5000), Mock())
    handler.path = path
    handler.wfile = io.BytesIO()
    handler.request_version = "HTTP/1.1"
    handler.command = "GET"
    return handler


class LaboratoryOrderRouteTests(unittest.TestCase):
    def test_server_source_registers_laboratory_order_get_route(self) -> None:
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        self.assertIn('parts[1] == "order"', source)
        self.assertIn("build_lab_order", source)

    def test_get_laboratory_order_route_dispatches_to_build_lab_order(self) -> None:
        captured: dict[str, object] = {}

        def send(status: int, payload: dict[str, object]) -> None:
            captured["status"] = status
            captured["payload"] = payload

        order = {
            "uuid": "c2421f0b-fa94-4ae8-a493-4f657ab7793d",
            "orderNumber": "ORD-8",
            "testName": "Urine Toxicology/Drug Test",
            "patientUuid": "f242364e-b70f-4fec-b29e-8ad4fbe147b5",
            "visitUuid": "6478a94e-1657-4abe-9271-7cf92b821576",
            "encounterUuid": "9a88a85d-a2db-4656-94bd-fb55c1b01688",
            "patientName": "ABIKAN E2E TEST PATIENT",
            "mrn": "ABC200016",
            "ordered": "2026-08-19T22:50:03.000+0000",
            "urgency": "Routine",
            "comment": "",
            "provider": "Doctor",
            "accession": "",
        }

        handler = _handler(
            "/openmrs/abikan-api/laboratory/order/c2421f0b-fa94-4ae8-a493-4f657ab7793d"
            "?patient=f242364e-b70f-4fec-b29e-8ad4fbe147b5"
            "&visit=6478a94e-1657-4abe-9271-7cf92b821576"
        )

        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(
                laboratory,
                "build_lab_order",
                return_value={"status": "ok", "order": order},
            ) as build,
            patch.object(handler, "_cookie", return_value="JSESSIONID=lab-session"),
            patch.object(handler, "_send", side_effect=send),
        ):
            handler.do_GET()

        build.assert_called_once_with(
            "c2421f0b-fa94-4ae8-a493-4f657ab7793d",
            "f242364e-b70f-4fec-b29e-8ad4fbe147b5",
            "6478a94e-1657-4abe-9271-7cf92b821576",
            "JSESSIONID=lab-session",
        )
        self.assertEqual(captured.get("status"), 200)
        payload = captured.get("payload")
        assert isinstance(payload, dict)
        self.assertEqual(payload.get("status"), "ok")
        loaded = payload.get("order")
        assert isinstance(loaded, dict)
        self.assertEqual(loaded.get("uuid"), "c2421f0b-fa94-4ae8-a493-4f657ab7793d")

    def test_missing_laboratory_order_route_returns_generic_not_found(self) -> None:
        captured: dict[str, object] = {}

        def send(status: int, payload: dict[str, object]) -> None:
            captured["status"] = status
            captured["payload"] = payload

        handler = _handler("/openmrs/abikan-api/laboratory/order-not-a-route")

        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(handler, "_cookie", return_value="JSESSIONID=lab-session"),
            patch.object(handler, "_send", side_effect=send),
        ):
            handler.do_GET()

        self.assertEqual(captured.get("status"), 404)
        payload = captured.get("payload")
        assert isinstance(payload, dict)
        self.assertEqual(payload.get("code"), "not_found")


class NursingNotesRouteTests(unittest.TestCase):
    def test_get_nursing_notes_route_dispatches(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/nursing-notes"
        )
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(
                inpatient,
                "build_nursing_notes",
                return_value={"status": "ok", "notes": []},
            ) as build,
            patch.object(handler, "_cookie", return_value="JSESSIONID=doctor"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_GET()
        build.assert_called_once_with("patient-uuid", "JSESSIONID=doctor")
        self.assertEqual(captured["status"], 200)

    def test_post_nursing_notes_route_dispatches_only_note_and_request(self) -> None:
        captured: dict[str, object] = {}
        payload = {"note": "Patient resting.", "requestId": "request-1"}
        raw = json.dumps(payload).encode("utf-8")
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/nursing-notes"
        )
        handler.command = "POST"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(
                inpatient,
                "create_nursing_note",
                return_value={"status": "ok", "note": {"uuid": "note-uuid"}},
            ) as create,
            patch.object(handler, "_cookie", return_value="JSESSIONID=nurse"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, response: captured.update(
                    {"status": status, "payload": response}
                ),
            ),
        ):
            handler.do_POST()
        create.assert_called_once_with(
            "patient-uuid",
            payload,
            "JSESSIONID=nurse",
        )
        self.assertEqual(captured["status"], 200)

    def test_update_and_delete_methods_cannot_write_nursing_notes(self) -> None:
        for method in ("PUT", "PATCH", "DELETE"):
            captured: dict[str, object] = {}
            handler = _handler(
                "/openmrs/abikan-api/inpatient/patient/patient-uuid/nursing-notes"
            )
            handler.command = method
            handler.headers = {"Content-Length": "2"}
            handler.rfile = io.BytesIO(b"{}")
            with (
                patch.object(
                    server,
                    "require_session",
                    return_value={"authenticated": True},
                ),
                patch.object(inpatient, "create_nursing_note") as create,
                patch.object(handler, "_cookie", return_value="JSESSIONID=nurse"),
                patch.object(
                    handler,
                    "_send",
                    side_effect=lambda status, response: captured.update(
                        {"status": status, "payload": response}
                    ),
                ),
            ):
                handler.do_POST()
            create.assert_not_called()
            self.assertEqual(captured["status"], 405)
            self.assertEqual(captured["payload"]["code"], "immutable_record")


class MedicationAdministrationRouteTests(unittest.TestCase):
    def test_get_route_dispatches_to_guarded_mar_read(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/medication-administration"
        )
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(
                medication_administration,
                "build_mar",
                return_value={"status": "ok", "orders": []},
            ) as build,
            patch.object(handler, "_cookie", return_value="JSESSIONID=doctor"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_GET()
        build.assert_called_once_with(
            "patient-uuid",
            "JSESSIONID=doctor",
            visit_uuid=None,
            admission_encounter_uuid=None,
        )
        self.assertEqual(captured["status"], 200)

    def test_get_route_passes_selected_historical_admission(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/"
            "medication-administration?visitUuid=visit-1&admissionEncounterUuid=admission-1"
        )
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(
                medication_administration,
                "build_mar",
                return_value={"status": "ok", "orders": []},
            ) as build,
            patch.object(handler, "_cookie", return_value="JSESSIONID=doctor"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_GET()
        build.assert_called_once_with(
            "patient-uuid",
            "JSESSIONID=doctor",
            visit_uuid="visit-1",
            admission_encounter_uuid="admission-1",
        )
        self.assertEqual(captured["status"], 200)

    def test_post_route_accepts_only_slot_outcome_and_reason(self) -> None:
        captured: dict[str, object] = {}
        payload = {"slotUuid": "slot-1", "outcome": "given", "reason": ""}
        raw = json.dumps(payload).encode("utf-8")
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/medication-administration"
        )
        handler.command = "POST"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch.object(
                medication_administration,
                "create_scheduled_administration",
                return_value={"status": "ok", "slot": {"uuid": "slot-1"}},
            ) as create,
            patch.object(handler, "_cookie", return_value="JSESSIONID=nurse"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, response: captured.update(
                    {"status": status, "payload": response}
                ),
            ),
        ):
            handler.do_POST()
        create.assert_called_once_with(
            "patient-uuid",
            payload,
            "JSESSIONID=nurse",
        )
        self.assertEqual(captured["status"], 200)

    def test_post_medication_schedule_route_dispatches_to_guarded_create(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/medication-schedule"
        )
        handler.command = "POST"
        handler.headers = {"Content-Length": "2"}
        handler.rfile = io.BytesIO(b"{}")
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch(
                "medication_schedule.create_medication_schedules",
                return_value={"status": "ok", "createdOrderUuids": ["order-1"]},
            ) as create,
            patch.object(handler, "_cookie", return_value="JSESSIONID=doctor"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_POST()
        create.assert_called_once_with("patient-uuid", "JSESSIONID=doctor")
        self.assertEqual(captured["status"], 200)

    def test_put_patch_and_delete_are_rejected(self) -> None:
        for method in ("PUT", "PATCH", "DELETE"):
            captured: dict[str, object] = {}
            handler = _handler(
                "/openmrs/abikan-api/inpatient/patient/patient-uuid/medication-administration"
            )
            handler.command = method
            handler.headers = {"Content-Length": "2"}
            handler.rfile = io.BytesIO(b"{}")
            with (
                patch.object(
                    server,
                    "require_session",
                    return_value={"authenticated": True},
                ),
                patch.object(
                    medication_administration,
                    "create_scheduled_administration",
                ) as create,
                patch.object(handler, "_cookie", return_value="JSESSIONID=nurse"),
                patch.object(
                    handler,
                    "_send",
                    side_effect=lambda status, response: captured.update(
                        {"status": status, "payload": response}
                    ),
                ),
            ):
                handler.do_POST()
            create.assert_not_called()
            self.assertEqual(captured["status"], 405)
            self.assertEqual(captured["payload"]["code"], "immutable_record")


class InpatientVitalsRouteTests(unittest.TestCase):
    def test_get_route_passes_selected_admission(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler(
            "/openmrs/abikan-api/inpatient/patient/patient-uuid/vitals"
            "?visitUuid=visit-1&admissionEncounterUuid=admission-1"
        )
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch(
                "inpatient_vitals.build_vitals",
                return_value={"status": "ok", "readings": []},
            ) as build,
            patch.object(handler, "_cookie", return_value="JSESSIONID=doctor"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_GET()
        build.assert_called_once_with(
            "patient-uuid",
            "JSESSIONID=doctor",
            visit_uuid="visit-1",
            admission_encounter_uuid="admission-1",
        )
        self.assertEqual(captured["status"], 200)

    def test_post_route_dispatches_to_create(self) -> None:
        captured: dict[str, object] = {}
        payload = {"temperature": 37.2, "requestId": "request-1"}
        raw = json.dumps(payload).encode("utf-8")
        handler = _handler("/openmrs/abikan-api/inpatient/patient/patient-uuid/vitals")
        handler.command = "POST"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch(
                "inpatient_vitals.create_vitals",
                return_value={"status": "ok", "duplicate": False},
            ) as create,
            patch.object(handler, "_cookie", return_value="JSESSIONID=nurse"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, response: captured.update(
                    {"status": status, "payload": response}
                ),
            ),
        ):
            handler.do_POST()
        create.assert_called_once_with("patient-uuid", payload, "JSESSIONID=nurse")
        self.assertEqual(captured["status"], 200)

    def test_put_patch_and_delete_are_rejected(self) -> None:
        for method in ("PUT", "PATCH", "DELETE"):
            captured: dict[str, object] = {}
            handler = _handler(
                "/openmrs/abikan-api/inpatient/patient/patient-uuid/vitals"
            )
            handler.command = method
            handler.headers = {"Content-Length": "2"}
            handler.rfile = io.BytesIO(b"{}")
            with (
                patch.object(
                    server,
                    "require_session",
                    return_value={"authenticated": True},
                ),
                patch("inpatient_vitals.create_vitals") as create,
                patch.object(handler, "_cookie", return_value="JSESSIONID=nurse"),
                patch.object(
                    handler,
                    "_send",
                    side_effect=lambda status, response: captured.update(
                        {"status": status, "payload": response}
                    ),
                ),
            ):
                handler.do_POST()
            create.assert_not_called()
            self.assertEqual(captured["status"], 405)
            self.assertEqual(captured["payload"]["code"], "immutable_record")


class PharmacyChargeRouteTests(unittest.TestCase):
    def test_server_source_registers_pharmacy_charge_route(self) -> None:
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        self.assertIn('parts[3] == "charge"', source)
        self.assertIn("create_pharmacy_charge", source)


class ReceptionVisitContextRouteTests(unittest.TestCase):
    def test_get_visit_context_does_not_use_card_charge_builder(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler("/openmrs/abikan-api/registration/patient/patient-a/visit")
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch(
                "registration_patient.build_visit_context",
                return_value={
                    "status": "ok",
                    "patient": {"uuid": "patient-a", "name": "Ada", "mrn": "ABC1"},
                    "visit": None,
                    "canStartVisit": True,
                    "admissionActive": False,
                },
            ) as build,
            patch("registration.build_registration") as charge,
            patch.object(handler, "_cookie", return_value="JSESSIONID=rec"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_GET()
        build.assert_called_once_with("patient-a", "JSESSIONID=rec")
        charge.assert_not_called()
        self.assertEqual(captured["status"], 200)
        payload = captured["payload"]
        assert isinstance(payload, dict)
        self.assertTrue(payload["canStartVisit"])
        self.assertNotIn("canCreateCharge", payload)


class ReceptionVisitRouteTests(unittest.TestCase):
    def test_existing_open_visit_returns_structured_conflict(self) -> None:
        captured: dict[str, object] = {}
        raw = json.dumps({"visitTypeUuid": "opd", "locationUuid": "opd-1"}).encode("utf-8")
        handler = _handler("/openmrs/abikan-api/registration/patient/patient-a/visit")
        handler.command = "POST"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        existing = {
            "status": "existing",
            "created": False,
            "code": "visit_already_open",
            "message": "Patient already has an open visit. Continue with the existing visit.",
            "uuid": "visit-a",
            "open": True,
        }
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch(
                "registration_patient.start_visit",
                return_value=existing,
            ) as start,
            patch.object(handler, "_cookie", return_value="JSESSIONID=rec"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_POST()
        start.assert_called_once()
        self.assertEqual(captured["status"], 409)
        payload = captured["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["code"], "visit_already_open")
        self.assertEqual(payload["uuid"], "visit-a")
        self.assertEqual(
            payload["message"],
            "Patient already has an open visit. Continue with the existing visit.",
        )


class ReceptionCloseVisitRouteTests(unittest.TestCase):
    def test_server_source_registers_close_visit_route(self) -> None:
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        self.assertIn('parts[5] == "close"', source)
        self.assertIn("close_visit", source)

    def test_post_close_visit_dispatches_to_close_visit(self) -> None:
        captured: dict[str, object] = {}
        handler = _handler(
            "/openmrs/abikan-api/registration/patient/patient-a/visit/visit-a/close"
        )
        handler.command = "POST"
        handler.headers = {"Content-Length": "2"}
        handler.rfile = io.BytesIO(b"{}")
        with (
            patch.object(server, "require_session", return_value={"authenticated": True}),
            patch(
                "registration_patient.close_visit",
                return_value={
                    "status": "ok",
                    "uuid": "visit-a",
                    "open": False,
                    "stopDatetime": "2026-09-03T11:00:00.000+0000",
                    "message": "Visit closed successfully.",
                },
            ) as close,
            patch.object(handler, "_cookie", return_value="JSESSIONID=rec"),
            patch.object(
                handler,
                "_send",
                side_effect=lambda status, payload: captured.update(
                    {"status": status, "payload": payload}
                ),
            ),
        ):
            handler.do_POST()
        close.assert_called_once_with("patient-a", "visit-a", "JSESSIONID=rec")
        self.assertEqual(captured["status"], 200)
        payload = captured["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["uuid"], "visit-a")
        self.assertFalse(payload["open"])


class AllergyRouteTests(unittest.TestCase):
    def test_server_source_registers_patient_allergy_routes(self) -> None:
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        self.assertIn('parts[2] == "allergies"', source)
        self.assertIn("list_allergies", source)
        self.assertIn("create_allergy", source)
        self.assertIn("update_allergy", source)
        self.assertIn("void_allergy", source)


if __name__ == "__main__":
    unittest.main()
