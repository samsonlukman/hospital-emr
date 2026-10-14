"""Reception visit start and returning-patient card fee."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import registration as reception
import registration_patient as arrival
from server import ApiError


PATIENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OPD_VISIT = "11111111-1111-4111-8111-111111111111"
IPD_VISIT = "22222222-2222-4222-8222-222222222222"
CLOSED_VISIT = "33333333-3333-4333-8333-333333333333"
FUTURE_VISIT = "44444444-4444-4444-8444-444444444444"
VISIT_TYPE = "opd-type-uuid"
LOCATION = "opd-1-uuid"


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


class LatestOpenVisitTests(unittest.TestCase):
    def test_open_means_empty_stop_datetime_for_this_patient_only(self) -> None:
        payload = {
            "results": [
                {
                    "uuid": "other-patient-open",
                    "startDatetime": "2026-09-02T10:00:00.000+0000",
                    "stopDatetime": None,
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_B},
                },
                {
                    "uuid": CLOSED_VISIT,
                    "startDatetime": "2026-09-01T08:00:00.000+0000",
                    "stopDatetime": "2026-09-01T12:00:00.000+0000",
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_A},
                },
                {
                    "uuid": OPD_VISIT,
                    "startDatetime": "2026-09-02T09:00:00.000+0000",
                    "stopDatetime": None,
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_A},
                },
            ]
        }
        with (
            patch.object(reception, "_openmrs_json", return_value=payload),
            patch.object(reception, "load_visit", side_effect=lambda uuid, patient, _cookie: open_visit(uuid, patient)) as loaded,
        ):
            found = reception.latest_open_visit(PATIENT_A, "JSESSIONID=rec")

        self.assertEqual(found["uuid"], OPD_VISIT)
        loaded.assert_called_once_with(OPD_VISIT, PATIENT_A, "JSESSIONID=rec")

    def test_future_dated_visit_without_stop_is_still_open(self) -> None:
        payload = {
            "results": [
                {
                    "uuid": FUTURE_VISIT,
                    "startDatetime": "2026-09-03T08:00:00.000+0000",
                    "stopDatetime": None,
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_A},
                }
            ]
        }
        with (
            patch.object(reception, "_openmrs_json", return_value=payload),
            patch.object(
                reception,
                "load_visit",
                return_value=open_visit(FUTURE_VISIT, startDatetime="2026-09-03T08:00:00.000+0000"),
            ),
        ):
            found = reception.latest_open_visit(PATIENT_A, "JSESSIONID=rec")
        self.assertEqual(found["uuid"], FUTURE_VISIT)

    def test_closed_visit_is_not_open(self) -> None:
        payload = {
            "results": [
                {
                    "uuid": CLOSED_VISIT,
                    "startDatetime": "2026-09-01T08:00:00.000+0000",
                    "stopDatetime": "2026-09-01T12:00:00.000+0000",
                    "visitType": {"name": "OPD"},
                    "location": {"name": "OPD-1"},
                    "patient": {"uuid": PATIENT_A},
                }
            ]
        }
        with patch.object(reception, "_openmrs_json", return_value=payload):
            self.assertIsNone(reception.latest_open_visit(PATIENT_A, "JSESSIONID=rec"))


class StartVisitTests(unittest.TestCase):
    def test_existing_open_visit_is_returned_and_not_created(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=open_visit()),
            patch.object(arrival, "load_visit_types") as types,
        ):
            result = arrival.start_visit(
                PATIENT_A,
                {"visitTypeUuid": VISIT_TYPE, "locationUuid": LOCATION},
                "JSESSIONID=rec",
            )

        types.assert_not_called()
        self.assertEqual(result["status"], "existing")
        self.assertFalse(result["created"])
        self.assertEqual(result["code"], reception.VISIT_ALREADY_OPEN_CODE)
        self.assertEqual(result["message"], reception.VISIT_ALREADY_OPEN_MESSAGE)
        self.assertEqual(result["uuid"], OPD_VISIT)

    def test_closed_visit_allows_a_new_visit(self) -> None:
        created = {
            "uuid": "new-visit",
            "startDatetime": "2026-09-02T11:00:00.000+0000",
        }
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
                        "uuid": VISIT_TYPE,
                        "name": "OPD",
                        "label": "General Outpatient",
                        "bucket": "outpatient",
                    }
                ],
            ),
            patch.object(arrival, "load_login_locations", return_value=[{"uuid": LOCATION, "name": "OPD-1"}]),
            patch.object(
                arrival,
                "locations_for_visit",
                return_value=[{"uuid": LOCATION, "name": "OPD-1"}],
            ),
            patch("daily_visit_number.ignore_client_number"),
            patch("daily_visit_number.begin_request", return_value=None),
            patch("daily_visit_number.create_visit_with_number", return_value=(created, "012")) as create,
            patch("daily_visit_number.finish_request"),
        ):
            result = arrival.start_visit(
                PATIENT_A,
                {"visitTypeUuid": VISIT_TYPE, "locationUuid": LOCATION, "requestId": "req-1"},
                "JSESSIONID=rec",
            )

        create.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["created"])
        self.assertEqual(result["uuid"], "new-visit")
        self.assertNotIn("canCreateCharge", result)

    def test_existing_patient_visit_does_not_require_a_card_sale(self) -> None:
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
                        "uuid": VISIT_TYPE,
                        "name": "OPD",
                        "label": "General Outpatient",
                        "bucket": "outpatient",
                    }
                ],
            ),
            patch.object(arrival, "load_login_locations", return_value=[{"uuid": LOCATION, "name": "OPD-1"}]),
            patch.object(
                arrival,
                "locations_for_visit",
                return_value=[{"uuid": LOCATION, "name": "OPD-1"}],
            ),
            patch("daily_visit_number.ignore_client_number"),
            patch("daily_visit_number.begin_request", return_value=None),
            patch("daily_visit_number.create_visit_with_number", return_value=(created, "013")),
            patch("daily_visit_number.finish_request"),
            patch.object(reception, "odoo_reader") as odoo,
            patch.object(reception, "find_patient_registration_sale") as sale,
            patch.object(reception, "card_catalog") as cards,
        ):
            result = arrival.start_visit(
                PATIENT_A,
                {"visitTypeUuid": VISIT_TYPE, "locationUuid": LOCATION, "requestId": "req-nocard"},
                "JSESSIONID=rec",
            )
        odoo.assert_not_called()
        sale.assert_not_called()
        cards.assert_not_called()
        self.assertTrue(result["created"])
        self.assertEqual(result["uuid"], "new-visit")

    def test_future_dated_open_visit_is_reused(self) -> None:
        future = open_visit(FUTURE_VISIT, startDatetime="2026-09-03T08:00:00.000+0000")
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(reception, "latest_open_visit", return_value=future),
            patch("daily_visit_number.create_visit_with_number") as create,
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": VISIT_TYPE}, "JSESSIONID=rec")

        create.assert_not_called()
        self.assertEqual(result["uuid"], FUTURE_VISIT)
        self.assertEqual(result["code"], reception.VISIT_ALREADY_OPEN_CODE)

    def test_admitted_occupied_patient_does_not_create_opd(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=True),
            patch.object(
                arrival,
                "_admission_visit_context",
                return_value={"visitUuid": IPD_VISIT},
            ),
            patch.object(
                reception,
                "load_visit",
                return_value=open_visit(IPD_VISIT, visitType="IPD", location="Ward"),
            ),
            patch("daily_visit_number.create_visit_with_number") as create,
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": VISIT_TYPE}, "JSESSIONID=rec")

        create.assert_not_called()
        self.assertEqual(result["code"], reception.ADMISSION_IN_PROGRESS_CODE)
        self.assertEqual(result["uuid"], IPD_VISIT)
        self.assertFalse(result["created"])

    def test_open_ipd_visit_is_reused_without_creating_opd(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(
                reception,
                "latest_open_visit",
                return_value=open_visit(IPD_VISIT, visitType="IPD"),
            ),
            patch("daily_visit_number.create_visit_with_number") as create,
        ):
            result = arrival.start_visit(PATIENT_A, {"visitTypeUuid": VISIT_TYPE}, "JSESSIONID=rec")
        create.assert_not_called()
        self.assertEqual(result["code"], reception.ADMISSION_IN_PROGRESS_CODE)
        self.assertEqual(result["uuid"], IPD_VISIT)
        self.assertFalse(result["created"])

    def test_unauthorized_user_cannot_start_a_visit(self) -> None:
        with patch.object(
            arrival,
            "require_registrar",
            side_effect=ApiError(403, "forbidden", "This action requires Reception access."),
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.start_visit(PATIENT_A, {"visitTypeUuid": VISIT_TYPE}, "JSESSIONID=doc")
        self.assertEqual(caught.exception.status, 403)


class ReturningPatientCardFeeTests(unittest.TestCase):
    def test_prior_card_sale_blocks_another_card_fee(self) -> None:
        visit = open_visit()
        prior = ({"external_order_id": "registration:old-visit"}, {"id": 9, "origin": "old-visit", "state": "sale"})
        payload = {
            "status": "ok",
            "canCreateCharge": False,
            "cardAlreadyRegistered": True,
            "hasCharge": True,
        }

        class FakeOdoo:
            pass

        with (
            patch.object(reception, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(reception, "load_visit", return_value=visit),
            patch.object(reception, "load_openmrs_patient", return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"}),
            patch.object(reception, "odoo_reader", return_value=FakeOdoo()),
            patch.object(reception, "find_partner", return_value={"id": 44}),
            patch.object(reception, "find_existing_sale", return_value=None),
            patch.object(reception, "find_patient_registration_sale", return_value=prior),
            patch.object(reception, "_charge_payload", return_value=dict(payload)),
            patch.object(reception, "execute") as execute,
        ):
            result = reception.create_registration_charge(
                PATIENT_A,
                {"visitUuid": OPD_VISIT, "cardType": "individual", "requestId": "fee-1"},
                "JSESSIONID=rec",
            )

        execute.assert_not_called()
        self.assertTrue(result["cardAlreadyRegistered"])
        self.assertFalse(result["canCreateCharge"])
        self.assertEqual(result["code"], reception.CARD_ALREADY_REGISTERED_CODE)
        self.assertEqual(result["message"], reception.CARD_ALREADY_REGISTERED_MESSAGE)

    def test_charge_payload_does_not_offer_card_fee_when_patient_already_has_a_card(self) -> None:
        visit = open_visit()
        prior_sale = {"id": 9, "origin": "old-visit", "state": "sale", "amount_total": 2000, "invoice_ids": []}
        prior_line = {"external_order_id": "registration:old-visit"}

        class FakeOdoo:
            def search_read(self, *_args, **_kwargs):
                return []

            def read(self, *_args, **_kwargs):
                return []

        with (
            patch.object(reception, "load_openmrs_patient", return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"}),
            patch.object(reception, "odoo_reader", return_value=FakeOdoo()),
            patch.object(reception, "ensure_registration_masters", return_value={"products": {"individual": {"name": "Individual Card", "list_price": 2000}}}),
            patch.object(reception, "registration_currency", return_value=dict(reception.NGN_CURRENCY)),
            patch.object(reception, "find_partner", return_value={"id": 44}),
            patch.object(reception, "find_existing_sale", return_value=None),
            patch.object(reception, "find_patient_registration_sale", return_value=(prior_line, prior_sale)),
            patch.object(reception, "related_invoice", return_value={"payment_state": "paid", "amount_residual": 0, "amount_total": 2000, "amount_tax": 0}),
            patch.object(reception, "card_catalog", return_value=[{"id": "individual", "label": "Individual Card"}]),
            patch.object(reception, "_admission_active", return_value=False),
        ):
            payload = reception._charge_payload("JSESSIONID=rec", PATIENT_A, visit)

        self.assertFalse(payload["canCreateCharge"])
        self.assertTrue(payload["cardAlreadyRegistered"])
        self.assertEqual(payload["blockReason"], reception.CARD_ALREADY_REGISTERED_MESSAGE)

    def test_new_patient_without_a_card_can_still_create_one_after_a_visit(self) -> None:
        visit = open_visit()

        class FakeOdoo:
            pass

        with (
            patch.object(reception, "load_openmrs_patient", return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"}),
            patch.object(reception, "odoo_reader", return_value=FakeOdoo()),
            patch.object(reception, "ensure_registration_masters", return_value={"products": {"individual": {"name": "Individual Card", "list_price": 2000}}}),
            patch.object(reception, "registration_currency", return_value=dict(reception.NGN_CURRENCY)),
            patch.object(reception, "find_partner", return_value={"id": 44}),
            patch.object(reception, "find_existing_sale", return_value=None),
            patch.object(reception, "find_patient_registration_sale", return_value=None),
            patch.object(reception, "card_catalog", return_value=[{"id": "individual", "label": "Individual Card"}]),
            patch.object(reception, "_admission_active", return_value=False),
        ):
            payload = reception._charge_payload("JSESSIONID=rec", PATIENT_A, visit)

        self.assertTrue(payload["canCreateCharge"])
        self.assertFalse(payload["cardAlreadyRegistered"])

    def test_patient_sale_lookup_stays_on_this_partner(self) -> None:
        class FakeOdoo:
            def __init__(self) -> None:
                self.domain: list[object] | None = None

            def search_read(self, model, domain, fields, limit=200):
                if model == "sale.order":
                    self.domain = domain
                    if domain == [("partner_id", "=", 44)]:
                        return [{"id": 9, "partner_id": [44, "Ada"], "origin": "old-visit", "state": "sale"}]
                    return []
                return [
                    {
                        "id": 3,
                        "order_id": [9, "SO"],
                        "external_order_id": "registration:old-visit",
                    }
                ]

        own = FakeOdoo()
        found = reception.find_patient_registration_sale(own, 44)
        self.assertIsNotNone(found)
        self.assertEqual(own.domain, [("partner_id", "=", 44)])
        self.assertEqual(found[1]["id"], 9)

        other = FakeOdoo()
        self.assertIsNone(reception.find_patient_registration_sale(other, 99))
        self.assertEqual(other.domain, [("partner_id", "=", 99)])

    def test_unauthorized_user_cannot_create_a_card_fee(self) -> None:
        with patch.object(
            reception,
            "require_registrar",
            side_effect=ApiError(403, "forbidden", "This action requires Reception access."),
        ):
            with self.assertRaises(ApiError) as caught:
                reception.create_registration_charge(
                    PATIENT_A,
                    {"visitUuid": OPD_VISIT, "cardType": "individual"},
                    "JSESSIONID=doc",
                )
        self.assertEqual(caught.exception.status, 403)

    def test_finance_outage_does_not_block_visit_context(self) -> None:
        visit = open_visit()
        with (
            patch.object(reception, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(reception, "latest_open_visit", return_value=visit),
            patch.object(
                reception,
                "_charge_payload",
                side_effect=ApiError(503, "odoo_error", "Financial service is unavailable."),
            ),
            patch.object(
                reception,
                "_charge_unavailable_payload",
                return_value={
                    "status": "ok",
                    "visit": visit,
                    "canCreateCharge": False,
                    "blockReason": reception.CARD_FEE_UNAVAILABLE_MESSAGE,
                },
            ) as fallback,
        ):
            payload = reception.build_registration(PATIENT_A, "JSESSIONID=rec")
        fallback.assert_called_once()
        self.assertEqual(payload["visit"]["uuid"], OPD_VISIT)
        self.assertFalse(payload["canCreateCharge"])


class VisitContextTests(unittest.TestCase):
    def test_existing_patient_visit_context_does_not_use_odoo_or_card_fee(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(
                reception,
                "load_openmrs_patient",
                return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"},
            ),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(
                arrival,
                "_visit_type_options",
                return_value=[{"uuid": VISIT_TYPE, "name": "OPD", "label": "General Outpatient", "locations": []}],
            ),
            patch.object(reception, "odoo_reader") as odoo,
            patch.object(reception, "find_patient_registration_sale") as sale,
            patch.object(reception, "card_catalog") as cards,
        ):
            payload = arrival.build_visit_context(PATIENT_A, "JSESSIONID=rec")
        odoo.assert_not_called()
        sale.assert_not_called()
        cards.assert_not_called()
        self.assertTrue(payload["canStartVisit"])
        self.assertIsNone(payload["visit"])
        self.assertEqual(payload["visitTypes"][0]["name"], "OPD")
        self.assertNotIn("canCreateCharge", payload)
        self.assertNotIn("cards", payload)

    def test_open_visit_is_returned_for_this_patient_only(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(
                reception,
                "load_openmrs_patient",
                return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"},
            ),
            patch.object(reception, "latest_open_visit", return_value=open_visit()),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(arrival, "_visit_type_options", return_value=[]),
        ):
            payload = arrival.build_visit_context(PATIENT_A, "JSESSIONID=rec")
        self.assertFalse(payload["canStartVisit"])
        self.assertEqual(payload["code"], reception.VISIT_ALREADY_OPEN_CODE)
        self.assertEqual(payload["visit"]["uuid"], OPD_VISIT)
        self.assertEqual(payload["message"], reception.VISIT_ALREADY_OPEN_MESSAGE)

    def test_admitted_patient_does_not_offer_a_new_opd_visit(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(
                reception,
                "load_openmrs_patient",
                return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"},
            ),
            patch.object(reception, "latest_open_visit", return_value=None),
            patch.object(arrival, "_patient_occupied", return_value=True),
            patch.object(arrival, "_admission_visit_context", return_value={"visitUuid": IPD_VISIT}),
            patch.object(
                reception,
                "load_visit",
                return_value=open_visit(IPD_VISIT, visitType="IPD"),
            ),
            patch.object(arrival, "_visit_type_options", return_value=[]),
        ):
            payload = arrival.build_visit_context(PATIENT_A, "JSESSIONID=rec")
        self.assertFalse(payload["canStartVisit"])
        self.assertTrue(payload["admissionActive"])
        self.assertEqual(payload["visit"]["uuid"], IPD_VISIT)
        self.assertEqual(payload["code"], reception.ADMISSION_IN_PROGRESS_CODE)

    def test_open_ipd_visit_is_admission_even_without_bed_scan(self) -> None:
        with (
            patch.object(arrival, "require_registrar", return_value={"username": "rec.abikan"}),
            patch.object(
                reception,
                "load_openmrs_patient",
                return_value={"uuid": PATIENT_A, "name": "Ada", "mrn": "ABC1"},
            ),
            patch.object(
                reception,
                "latest_open_visit",
                return_value=open_visit(IPD_VISIT, visitType="IPD"),
            ),
            patch.object(arrival, "_patient_occupied", return_value=False),
            patch.object(arrival, "_admission_visit_context", return_value=None),
            patch.object(arrival, "_visit_type_options", return_value=[]),
        ):
            payload = arrival.build_visit_context(PATIENT_A, "JSESSIONID=rec")
        self.assertFalse(payload["canStartVisit"])
        self.assertTrue(payload["admissionActive"])
        self.assertEqual(payload["code"], reception.ADMISSION_IN_PROGRESS_CODE)

    def test_unauthorized_user_cannot_read_visit_context(self) -> None:
        with patch.object(
            arrival,
            "require_registrar",
            side_effect=ApiError(403, "forbidden", "This action requires Reception access."),
        ):
            with self.assertRaises(ApiError) as caught:
                arrival.build_visit_context(PATIENT_A, "JSESSIONID=doc")
        self.assertEqual(caught.exception.status, 403)


class LoadVisitIsolationTests(unittest.TestCase):
    def test_load_visit_rejects_another_patients_visit(self) -> None:
        with patch.object(
            reception,
            "_openmrs_json",
            return_value={
                "uuid": OPD_VISIT,
                "startDatetime": "2026-09-02T08:00:00.000+0000",
                "stopDatetime": None,
                "visitType": {"name": "OPD"},
                "location": {"name": "OPD-1"},
                "patient": {"uuid": PATIENT_A},
            },
        ):
            with self.assertRaises(ApiError) as caught:
                reception.load_visit(OPD_VISIT, PATIENT_B, "JSESSIONID=rec")
            self.assertEqual(caught.exception.code, "wrong_patient")
            loaded = reception.load_visit(OPD_VISIT, PATIENT_A, "JSESSIONID=rec")
        self.assertEqual(loaded["uuid"], OPD_VISIT)


class NewRegistrationListTests(unittest.TestCase):
    def test_lists_patients_registered_in_hospital_time(self) -> None:
        from datetime import datetime

        created = datetime(2026, 10, 11, 15, 5)
        with (
            patch.object(reception, "require_registrar", return_value={"uuid": "user"}),
            patch(
                "openmrs_sql.fetch_all",
                side_effect=[[(1,)], [(PATIENT_A, "Ada Okonkwo", "ABC1", created)]],
            ),
        ):
            payload = reception.list_new_registrations(
                "JSESSIONID=x",
                "/openmrs/abikan-api/reception/registrations?period=today",
            )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["items"][0]["patientName"], "Ada Okonkwo")
        self.assertEqual(payload["items"][0]["mrn"], "ABC1")
        self.assertEqual(payload["items"][0]["time"], "4:05 pm")
        self.assertEqual(payload["items"][0]["date"], "2026-10-11")
        self.assertEqual(payload["total"], 1)
        self.assertTrue(payload["singleDay"])
