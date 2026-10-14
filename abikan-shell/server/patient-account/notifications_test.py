"""Staff notification SQLite store — Phase 1 + Phase 2."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import inpatient
import notifications as notes
import patient_call as paging
import registration_patient as arrival
from server import ApiError

COOKIE = "JSESSIONID=clinical"
PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VISIT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
DOCTOR = {"uuid": "doc-1", "username": "dr.amina", "privileges": ["app:clinical"], "roles": ["Abikan:Doctor"]}
RECEPTION = {
    "uuid": "rec-1",
    "username": "reception",
    "privileges": ["app:registration"],
    "roles": ["Abikan:Reception"],
}
NURSE = {
    "uuid": "nurse-1",
    "username": "nurse.ada",
    "privileges": [inpatient.ADT_PRIVILEGE],
    "roles": ["Abikan:Nursing"],
}
PHARMACY = {
    "uuid": "pharm-1",
    "username": "pharmacy",
    "privileges": ["app:pharmacy"],
    "roles": ["Abikan:Pharmacy"],
}


class NotificationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-note-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        notes.reset_for_tests(path=self.db)

    def tearDown(self) -> None:
        notes.reset_for_tests(path=self.db)
        Path(self.db).unlink(missing_ok=True)

    def test_emit_list_ack_and_read(self) -> None:
        created = notes.emit(
            event_type=notes.EVENT_PATIENT_CALLED,
            title="Patient Call",
            message="Dr. Amina is calling Ahmed Bello.",
            sender_username="dr.amina",
            sender_display="Dr. Amina",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_REGISTRATION,
            patient_uuid=PATIENT,
            visit_uuid=VISIT,
            mrn="ABC200100",
            patient_name="Ahmed Bello",
            priority=notes.PRIORITY_HIGH,
            speak=True,
            ttl_seconds=900,
            idempotency_key="patient_called:request:req-1",
            path=self.db,
        )
        self.assertFalse(created["duplicate"])
        note_id = created["notification"]["id"]

        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)
        self.assertEqual(listed["notifications"][0]["id"], note_id)

        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=PHARMACY),
        ):
            denied = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(denied["pendingCount"], 0)
        self.assertEqual(denied["notifications"], [])

        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            read = notes.mark_read(note_id, COOKIE, path=self.db)
            self.assertFalse(read["duplicate"])
            self.assertEqual(read["notification"]["status"], "read")
            acked = notes.acknowledge(note_id, COOKIE, path=self.db)
            self.assertFalse(acked["duplicate"])
            self.assertEqual(acked["notification"]["status"], "acked")
            listed_after = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed_after["activeCount"], 0)

    def test_attention_to_reception_department_reaches_reception(self) -> None:
        created = notes.emit(
            event_type=notes.EVENT_DEPARTMENT_ATTENTION_REQUESTED,
            title="Incoming call",
            message="Pharmacy needs Reception.",
            sender_username="pharmacy.abikan",
            sender_display="Pharmacy",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace="reception",
            priority=notes.PRIORITY_URGENT,
            speak=True,
            path=self.db,
        )
        self.assertFalse(created["duplicate"])
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)

    def test_superadmin_does_not_receive_nursing_department_calls(self) -> None:
        admin = {
            "uuid": "admin-1",
            "username": "admin.abikan",
            "privileges": ["app:adt", "app:clinical", "bahmni:clinical:dispense"],
            "roles": ["SuperAdmin"],
        }
        notes.emit(
            event_type=notes.EVENT_DEPARTMENT_ATTENTION_REQUESTED,
            title="Incoming call",
            message="Pharmacy needs Nursing.",
            sender_username="pharmacy.abikan",
            sender_display="Pharmacy",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_NURSING,
            priority=notes.PRIORITY_URGENT,
            speak=True,
            path=self.db,
        )
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=admin),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 0)

    def test_nursing_role_receives_nursing_calls_without_adt_privilege(self) -> None:
        role_only = {
            "uuid": "nurse-role",
            "username": "nurse.role",
            "privileges": [],
            "roles": ["Abikan:Nursing"],
        }
        notes.emit(
            event_type=notes.EVENT_DEPARTMENT_ATTENTION_REQUESTED,
            title="Incoming call",
            message="Pharmacy needs Nursing.",
            sender_username="pharmacy.abikan",
            sender_display="Pharmacy",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_NURSING,
            priority=notes.PRIORITY_URGENT,
            speak=True,
            path=self.db,
        )
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=role_only),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)

    def test_idempotency_key_dedupes(self) -> None:
        first = notes.emit(
            event_type=notes.EVENT_PATIENT_CALLED,
            title="Patient Call",
            message="Dr. Amina is calling Ahmed.",
            sender_username="dr.amina",
            sender_display="Dr. Amina",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_REGISTRATION,
            idempotency_key="same-key",
            path=self.db,
        )
        second = notes.emit(
            event_type=notes.EVENT_PATIENT_CALLED,
            title="Patient Call",
            message="Dr. Amina is calling Ahmed.",
            sender_username="dr.amina",
            sender_display="Dr. Amina",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_REGISTRATION,
            idempotency_key="same-key",
            path=self.db,
        )
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["notification"]["id"], second["notification"]["id"])

    def test_expired_notifications_are_excluded(self) -> None:
        created = notes.emit(
            event_type=notes.EVENT_PATIENT_CALLED,
            title="Patient Call",
            message="Dr. Amina is calling Ahmed.",
            sender_username="dr.amina",
            sender_display="Dr. Amina",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_REGISTRATION,
            ttl_seconds=1,
            idempotency_key="expire-me",
            path=self.db,
        )
        note_id = created["notification"]["id"]
        # Force expiry.
        with notes.LOCK:
            connection = notes._connect(self.db)
            try:
                connection.execute(
                    "UPDATE staff_notification SET expires_at_epoch = ? WHERE id = ?",
                    (time.time() - 10, note_id),
                )
                connection.commit()
            finally:
                connection.close()
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["activeCount"], 0)

    def test_survives_reconnect_to_same_sqlite_file(self) -> None:
        notes.emit(
            event_type=notes.EVENT_PATIENT_CALLED,
            title="Patient Call",
            message="Dr. Amina is calling Ahmed.",
            sender_username="dr.amina",
            sender_display="Dr. Amina",
            recipient_scope=notes.SCOPE_WORKPLACE,
            recipient_workplace=notes.WORKPLACE_REGISTRATION,
            idempotency_key="persist-1",
            path=self.db,
        )
        # New connection path — simulates API process restart using same file.
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)
        self.assertTrue(Path(self.db).exists())


class PatientCallCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        paging.reset_for_tests()

    def tearDown(self) -> None:
        paging.reset_for_tests()

    def _create(self, body: dict[str, object] | None = None) -> dict[str, object]:
        payload = {
            "patientUuid": PATIENT,
            "visitUuid": VISIT,
            "patientName": "Ahmed Bello",
            "mrn": "ABC200100",
            "dailyVisitNumber": "012",
            "requestId": "req-1",
        }
        if body:
            payload.update(body)
        with (
            patch.object(paging.clinical, "require_clinician", return_value=DOCTOR),
            patch.object(paging, "_assert_visit_callable", return_value={"uuid": VISIT}),
            patch.object(
                paging,
                "clinical_queue_row",
                return_value={
                    "patientName": "Ahmed Bello",
                    "mrn": "ABC200100",
                    "dailyVisitNumber": "012",
                },
            ),
            patch.object(paging, "_doctor_display", return_value="Dr. Amina Bello"),
        ):
            return paging.create_patient_call(payload, COOKIE)

    def test_doctor_creates_and_reception_lists(self) -> None:
        result = self._create()
        self.assertFalse(result["duplicate"])
        self.assertIn("Dr. Amina Bello is calling Ahmed Bello", result["call"]["message"])
        with patch.object(paging.reception, "require_registrar", return_value=RECEPTION):
            with patch.object(paging.reception, "load_openmrs_user", return_value=RECEPTION):
                with patch.object(paging.staff_notes.core, "require_session"):
                    listed = paging.list_pending_calls(COOKIE)
        self.assertEqual(listed["pendingCount"], 1)

    def test_duplicate_request_id(self) -> None:
        first = self._create({"requestId": "same"})
        second = self._create({"requestId": "same"})
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["call"]["id"], second["call"]["id"])

    def test_ack(self) -> None:
        created = self._create()
        with (
            patch.object(paging.reception, "require_registrar", return_value=RECEPTION),
            patch.object(paging.reception, "load_openmrs_user", return_value=RECEPTION),
            patch.object(paging.staff_notes.core, "require_session"),
        ):
            acked = paging.acknowledge_call(created["call"]["id"], COOKIE)
            listed = paging.list_pending_calls(COOKIE)
        self.assertEqual(acked["call"]["status"], "acked")
        self.assertEqual(listed["pendingCount"], 0)

    def test_create_requires_clinician(self) -> None:
        with patch.object(
            paging.clinical,
            "require_clinician",
            side_effect=ApiError(403, "forbidden", "Clinical access required."),
        ):
            with self.assertRaises(ApiError) as raised:
                paging.create_patient_call(
                    {"patientUuid": PATIENT, "visitUuid": VISIT, "requestId": "x"},
                    COOKIE,
                )
        self.assertEqual(raised.exception.status, 403)


CLINICIAN = {
    "uuid": "doc-1",
    "username": "dr.amina",
    "privileges": ["app:clinical"],
    "roles": ["Abikan:Doctor"],
}
NURSE = {
    "uuid": "nurse-1",
    "username": "nurse.ada",
    "privileges": ["app:adt"],
    "roles": ["Abikan:Nursing"],
}


class VisitStartedNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-visit-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        notes.reset_for_tests(path=self.db)

    def tearDown(self) -> None:
        notes.reset_for_tests(path=self.db)
        Path(self.db).unlink(missing_ok=True)

    def _emit(self, request_id: str = "visit-req-1") -> dict[str, object]:
        return notes.emit_visit_started(
            patient_uuid=PATIENT,
            visit_uuid=VISIT,
            patient_name="Ahmed Bello",
            mrn="ABC200100",
            sender_username="reception",
            sender_display="Reception",
            daily_visit_number="012",
            request_id=request_id,
            path=self.db,
        )

    def test_emit_targets_clinical_with_correct_payload(self) -> None:
        created = self._emit()
        self.assertFalse(created["duplicate"])
        note = created["notification"]
        self.assertEqual(note["eventType"], notes.EVENT_VISIT_STARTED)
        self.assertEqual(note["recipientWorkplace"], notes.WORKPLACE_CLINICAL)
        self.assertEqual(note["priority"], notes.PRIORITY_HIGH)
        self.assertFalse(note["speak"])
        self.assertEqual(note["patientUuid"], PATIENT)
        self.assertEqual(note["visitUuid"], VISIT)
        self.assertEqual(note["mrn"], "ABC200100")
        self.assertEqual(note["patientName"], "Ahmed Bello")
        self.assertIn("ready for consultation", note["message"])
        self.assertEqual(
            note["actionHref"],
            f"#/doctor/patient/{PATIENT}/visit/{VISIT}",
        )

        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=CLINICIAN),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)

    def test_reception_does_not_receive_visit_started(self) -> None:
        self._emit()
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=RECEPTION),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 0)
        self.assertEqual(listed["notifications"], [])

    def test_pharmacy_does_not_receive_visit_started(self) -> None:
        self._emit()
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=PHARMACY),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 0)

    def test_duplicate_request_id_does_not_create_duplicates(self) -> None:
        first = self._emit("same-visit-req")
        second = self._emit("same-visit-req")
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["notification"]["id"], second["notification"]["id"])


class AdmitRequestedNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="abikan-admit-", suffix=".sqlite3", delete=False)
        handle.close()
        self.db = handle.name
        notes.reset_for_tests(path=self.db)

    def tearDown(self) -> None:
        notes.reset_for_tests(path=self.db)
        Path(self.db).unlink(missing_ok=True)

    def _emit(self, request_id: str = "admit-req-1") -> dict[str, object]:
        return notes.emit_admit_requested(
            patient_uuid=PATIENT,
            visit_uuid=VISIT,
            patient_name="Fatima Yusuf",
            mrn="ABC200200",
            sender_username="dr.amina",
            sender_display="Amina Bello",
            request_id=request_id,
            path=self.db,
        )

    def test_emit_targets_nursing_with_correct_payload(self) -> None:
        created = self._emit()
        self.assertFalse(created["duplicate"])
        note = created["notification"]
        self.assertEqual(note["eventType"], notes.EVENT_ADMIT_REQUESTED)
        self.assertEqual(note["recipientWorkplace"], notes.WORKPLACE_NURSING)
        self.assertEqual(note["priority"], notes.PRIORITY_URGENT)
        self.assertTrue(note["speak"])
        self.assertEqual(note["patientUuid"], PATIENT)
        self.assertEqual(note["visitUuid"], VISIT)
        self.assertEqual(note["mrn"], "ABC200200")
        self.assertIn("requested admission for Fatima Yusuf", note["message"])
        self.assertTrue(note["message"].startswith("Dr."))
        self.assertEqual(note["actionHref"], f"#/nursing/patient/{PATIENT}")

        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=NURSE),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["pendingCount"], 1)

    def test_unrelated_roles_do_not_receive_admit_requested(self) -> None:
        self._emit()
        for user in (RECEPTION, CLINICIAN, PHARMACY):
            with (
                patch.object(notes.core, "require_session"),
                patch.object(notes.reception, "load_openmrs_user", return_value=user),
            ):
                listed = notes.list_for_session(COOKIE, path=self.db)
            self.assertEqual(listed["pendingCount"], 0, msg=user["username"])

    def test_duplicate_request_id_does_not_create_duplicates(self) -> None:
        first = self._emit("same-admit-req")
        second = self._emit("same-admit-req")
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["notification"]["id"], second["notification"]["id"])


class VisitStartedTriggerTests(unittest.TestCase):
    """Domain trigger: start_visit emits only after a successful create."""

    PATIENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    VISIT_TYPE = "opd-type-uuid"
    LOCATION = "opd-1-uuid"

    def test_successful_visit_start_emits_notification(self) -> None:
        import registration as reception
        import registration_patient as arrival

        created = {"uuid": "new-visit", "startDatetime": "2026-09-02T11:00:00.000+0000"}
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(
                arrival,
                "load_visit_types",
                return_value=[
                    {
                        "uuid": self.VISIT_TYPE,
                        "name": "OPD",
                        "label": "General Outpatient",
                        "bucket": "outpatient",
                    }
                ],
            ),
            patch.object(arrival, "load_login_locations", return_value=[{"uuid": self.LOCATION, "name": "OPD-1"}]),
            patch.object(
                arrival,
                "locations_for_visit",
                return_value=[{"uuid": self.LOCATION, "name": "OPD-1"}],
            ),
            patch("daily_visit_number.ignore_client_number"),
            patch("daily_visit_number.begin_request", return_value=None),
            patch("daily_visit_number.create_visit_with_number", return_value=(created, "012")),
            patch("daily_visit_number.finish_request"),
            patch.object(arrival, "_emit_visit_started_notification") as emit,
        ):
            result = arrival.start_visit(
                self.PATIENT,
                {
                    "visitTypeUuid": self.VISIT_TYPE,
                    "locationUuid": self.LOCATION,
                    "requestId": "req-visit-1",
                },
                "JSESSIONID=rec",
            )

        self.assertTrue(result["created"])
        emit.assert_called_once()
        kwargs = emit.call_args.kwargs
        self.assertEqual(kwargs["patient_uuid"], self.PATIENT)
        self.assertEqual(kwargs["visit_uuid"], "new-visit")
        self.assertEqual(kwargs["request_id"], "req-visit-1")
        self.assertEqual(kwargs["daily_visit_number"], "012")

    def test_existing_open_visit_does_not_emit(self) -> None:
        import registration as reception
        import registration_patient as arrival

        open_visit = {
            "uuid": "existing-visit",
            "startDatetime": "2026-09-02T08:00:00.000+0000",
            "open": True,
            "visitType": "OPD",
            "location": "OPD-1",
            "patient": {"uuid": self.PATIENT},
        }
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=open_visit),
            patch.object(arrival, "_emit_visit_started_notification") as emit,
        ):
            result = arrival.start_visit(
                self.PATIENT,
                {"visitTypeUuid": self.VISIT_TYPE, "locationUuid": self.LOCATION},
                "JSESSIONID=rec",
            )

        self.assertEqual(result["status"], "existing")
        self.assertFalse(result["created"])
        emit.assert_not_called()

    def test_failed_visit_start_does_not_emit(self) -> None:
        import registration as reception
        import registration_patient as arrival

        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(
                arrival,
                "load_visit_types",
                return_value=[
                    {
                        "uuid": self.VISIT_TYPE,
                        "name": "OPD",
                        "label": "General Outpatient",
                        "bucket": "outpatient",
                    }
                ],
            ),
            patch.object(arrival, "load_login_locations", return_value=[{"uuid": self.LOCATION, "name": "OPD-1"}]),
            patch.object(
                arrival,
                "locations_for_visit",
                return_value=[{"uuid": self.LOCATION, "name": "OPD-1"}],
            ),
            patch("daily_visit_number.ignore_client_number"),
            patch("daily_visit_number.begin_request", return_value=None),
            patch(
                "daily_visit_number.create_visit_with_number",
                side_effect=ApiError(502, "visit_failed", "The visit could not be started."),
            ),
            patch("daily_visit_number.finish_request"),
            patch.object(arrival, "_emit_visit_started_notification") as emit,
            self.assertRaises(ApiError),
        ):
            arrival.start_visit(
                self.PATIENT,
                {
                    "visitTypeUuid": self.VISIT_TYPE,
                    "locationUuid": self.LOCATION,
                    "requestId": "req-fail",
                },
                "JSESSIONID=rec",
            )
        emit.assert_not_called()


class AdmitRequestedTriggerTests(unittest.TestCase):
    """Domain trigger: create_admit_decision emits only after a successful write."""

    PATIENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    IPD_VISIT = "22222222-2222-4222-8222-222222222222"
    ADMISSION = "33333333-3333-4333-8333-333333333333"
    LOCATION = "opd-1-uuid"

    def test_successful_admit_request_emits_notification(self) -> None:
        import inpatient

        doctor = {
            "uuid": "doc-user",
            "username": "dr.amina",
            "privileges": ["app:clinical"],
            "roles": ["Abikan:Doctor"],
        }
        brief = {"uuid": self.PATIENT, "name": "Fatima", "mrn": "ABC1", "sex": "F", "age": "30"}
        stay = {
            "status": "ok",
            "patient": brief,
            "assignment": None,
            "awaiting": True,
            "visitUuid": self.IPD_VISIT,
            "admissionEncounterUuid": self.ADMISSION,
        }
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor),
            patch.object(inpatient, "_patient_brief", return_value=brief),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=None),
            patch.object(inpatient, "_admit_location_uuid", return_value=self.LOCATION),
            patch.object(inpatient, "_provider_uuid", return_value="provider-1"),
            patch.object(inpatient, "_create_ipd_visit", return_value=self.IPD_VISIT),
            patch.object(inpatient, "_create_admission_encounter_on_visit", return_value=self.ADMISSION),
            patch.object(inpatient, "_end_open_non_ipd_visits"),
            patch.object(inpatient, "build_patient_stay", return_value=stay),
            patch.object(inpatient, "_emit_admit_requested_notification") as emit,
        ):
            result = inpatient.create_admit_decision(
                self.PATIENT,
                {"locationUuid": self.LOCATION, "requestId": "req-admit-1"},
                "JSESSIONID=doc",
            )

        self.assertTrue(result["awaiting"])
        emit.assert_called_once()
        kwargs = emit.call_args.kwargs
        self.assertEqual(kwargs["patient_uuid"], self.PATIENT)
        self.assertEqual(kwargs["visit_uuid"], self.IPD_VISIT)
        self.assertEqual(kwargs["request_id"], "req-admit-1")

    def test_already_requested_does_not_emit(self) -> None:
        import inpatient

        doctor = {"uuid": "doc-user", "privileges": ["app:clinical"], "roles": ["Abikan:Doctor"]}
        brief = {"uuid": self.PATIENT, "name": "Fatima", "mrn": "ABC1"}
        existing = {
            "uuid": self.ADMISSION,
            "visit": {"uuid": self.IPD_VISIT, "stopDatetime": None},
        }
        already = {
            "status": "ok",
            "alreadyRequested": True,
            "awaiting": True,
            "message": "Admission already requested. Nursing will assign a bed.",
            "visitUuid": self.IPD_VISIT,
        }
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor),
            patch.object(inpatient, "_patient_brief", return_value=brief),
            patch.object(inpatient, "current_assignment", return_value=None),
            patch.object(inpatient, "_open_ipd_admission", return_value=existing),
            patch.object(inpatient, "build_patient_stay", return_value=already),
            patch.object(inpatient, "_emit_admit_requested_notification") as emit,
            patch.object(inpatient, "_create_ipd_visit") as create,
        ):
            result = inpatient.create_admit_decision(
                self.PATIENT,
                {"locationUuid": self.LOCATION, "requestId": "req-again"},
                "JSESSIONID=doc",
            )

        self.assertTrue(result.get("alreadyRequested"))
        create.assert_not_called()
        emit.assert_not_called()

    def test_failed_admit_does_not_emit(self) -> None:
        import inpatient

        doctor = {"uuid": "doc-user", "privileges": ["app:clinical"], "roles": ["Abikan:Doctor"]}
        brief = {"uuid": self.PATIENT, "name": "Fatima", "mrn": "ABC1"}
        with (
            patch.object(inpatient, "require_clinical_user", return_value=doctor),
            patch.object(inpatient, "_patient_brief", return_value=brief),
            patch.object(inpatient, "current_assignment", return_value={"bedNumber": "02"}),
            patch.object(inpatient, "_emit_admit_requested_notification") as emit,
            patch.object(inpatient, "_create_ipd_visit") as create,
            self.assertRaises(ApiError) as caught,
        ):
            inpatient.create_admit_decision(
                self.PATIENT,
                {"locationUuid": self.LOCATION, "requestId": "req-fail-admit"},
                "JSESSIONID=doc",
            )
        self.assertEqual(caught.exception.code, "already_admitted")
        create.assert_not_called()
        emit.assert_not_called()


class ExpireAdmitAlertTests(NotificationStoreTests):
    def test_canceling_an_admission_drops_the_waiting_alert(self) -> None:
        notes.emit_admit_requested(
            patient_uuid=PATIENT,
            visit_uuid=VISIT,
            patient_name="Ada Bello",
            mrn="ABC1",
            sender_username="dr.amina",
            sender_display="Amina",
            path=self.db,
        )
        removed = notes.expire_patient_event(PATIENT, notes.EVENT_ADMIT_REQUESTED, path=self.db)
        self.assertEqual(removed, 1)
        with (
            patch.object(notes.core, "require_session"),
            patch.object(notes.reception, "load_openmrs_user", return_value=NURSE),
        ):
            listed = notes.list_for_session(COOKIE, path=self.db)
        self.assertEqual(listed["notifications"], [])


if __name__ == "__main__":
    unittest.main()
