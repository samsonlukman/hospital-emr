"""Doctor laboratory orders are found from visits, before any bill exists."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import lab_result_report
import laboratory

LAB = laboratory.LAB_ORDER_TYPE_UUID


class LabOrderUuidsFromVisitsTest(unittest.TestCase):
    def test_keeps_lab_orders_newest_first(self) -> None:
        visits = [
            {
                "uuid": "visit-old",
                "startDatetime": "2026-10-01T08:00:00.000+0000",
                "encounters": [
                    {
                        "orders": [
                            {
                                "uuid": "lab-old",
                                "dateActivated": "2026-10-01T09:00:00.000+0000",
                                "orderType": {"uuid": LAB, "display": "Lab Order"},
                            },
                            {
                                "uuid": "drug-1",
                                "dateActivated": "2026-10-03T09:00:00.000+0000",
                                "orderType": {"uuid": "drug", "display": "Drug Order"},
                            },
                            {
                                "uuid": "voided-lab",
                                "voided": True,
                                "dateActivated": "2026-10-03T10:00:00.000+0000",
                                "orderType": {"uuid": LAB, "display": "Lab Order"},
                            },
                        ]
                    }
                ],
            },
            {
                "uuid": "visit-new",
                "startDatetime": "2026-10-03T08:00:00.000+0000",
                "encounters": [
                    {
                        "orders": [
                            {
                                "uuid": "lab-new",
                                "dateActivated": "2026-10-03T11:00:00.000+0000",
                                "orderType": {"display": "Lab Order"},
                            }
                        ]
                    }
                ],
            },
        ]
        self.assertEqual(
            laboratory.lab_order_uuids_from_visits(visits),
            ["lab-new", "lab-old"],
        )


class TopOrderedTestsTest(unittest.TestCase):
    def test_returns_the_busiest_tests_for_the_period(self) -> None:
        window = {
            "utcStartNaive": "2026-10-12 00:00:00",
            "utcEndNaive": "2026-10-13 00:00:00",
            "period": "today",
            "label": "Today",
            "timezone": "Africa/Lagos",
            "startDate": "2026-10-12",
            "endDate": "2026-10-12",
            "weekStartsOn": "Monday",
        }
        with (
            patch.object(laboratory, "require_lab_user", return_value={"username": "lab"}),
            patch("admin_analytics._window_from_query", return_value=window),
            patch("openmrs_sql.fetch_int", return_value=12),
            patch("openmrs_sql.fetch_all", return_value=[("Malaria parasite", 5), ("PCV", 3)]),
        ):
            payload = laboratory.top_ordered_tests("cookie", {"period": ["today"]})
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["total"], 12)
        self.assertEqual(payload["period"]["label"], "Today")
        self.assertEqual(payload["tests"], [{"name": "Malaria parasite", "count": 5}, {"name": "PCV", "count": 3}])


class ResultFlagColorTest(unittest.TestCase):
    def _sheet(self, flag: str) -> str:
        captured: dict[str, bytes] = {}

        def assemble(objects: list[bytes]) -> bytes:
            captured["content"] = objects[3]
            return b"%PDF"

        with (
            patch.object(lab_result_report, "_image_object", return_value=b"image"),
            patch.object(lab_result_report, "_assemble", side_effect=assemble),
        ):
            lab_result_report.render_result_pdf(
                header_jpeg=b"\xff\xd8",
                patient="A",
                mrn="1",
                age_sex="30 / Female",
                accession="A1",
                tests="PCV",
                printed="12/10/2026",
                rows=[{"name": "PCV", "result": "60", "unit": "%", "reference": "36 - 54", "flag": flag, "group": ""}],
            )
        return captured["content"].decode("latin-1")

    def test_high_flag_prints_in_red(self) -> None:
        sheet = self._sheet("High")
        self.assertIn(lab_result_report.HIGH_INK, sheet)
        self.assertIn("High", sheet)

    def test_sheet_names_the_validator(self) -> None:
        captured: dict[str, bytes] = {}

        def assemble(objects: list[bytes]) -> bytes:
            captured["content"] = objects[3]
            return b"%PDF"

        with (
            patch.object(lab_result_report, "_image_object", return_value=b"image"),
            patch.object(lab_result_report, "_assemble", side_effect=assemble),
        ):
            lab_result_report.render_result_pdf(
                header_jpeg=b"\xff\xd8",
                patient="A",
                mrn="1",
                age_sex="30 / Female",
                accession="A1",
                tests="PCV",
                printed="12/10/2026",
                validated_by="Ada Okonkwo",
                rows=[{"name": "PCV", "result": "40", "unit": "%", "reference": "36 - 54", "flag": "", "group": ""}],
            )
        sheet = captured["content"].decode("latin-1")
        self.assertIn("(Validated by: Ada Okonkwo)", sheet)

    def test_report_keeps_every_line_of_a_result(self) -> None:
        captured: dict[str, bytes] = {}

        def assemble(objects: list[bytes]) -> bytes:
            captured["content"] = objects[3]
            return b"%PDF"

        long_result = (
            "Numerous trophozoites of Plasmodium falciparum seen.\n"
            "No gametocytes. Repeat film in 24 hours if symptoms continue."
        )
        with (
            patch.object(lab_result_report, "_image_object", return_value=b"image"),
            patch.object(lab_result_report, "_assemble", side_effect=assemble),
        ):
            lab_result_report.render_result_pdf(
                header_jpeg=b"\xff\xd8",
                patient="A",
                mrn="1",
                age_sex="30 / Female",
                accession="A1",
                tests="Malaria",
                printed="12/10/2026",
                validated_by="Ada Okonkwo",
                rows=[
                    {
                        "name": "Malaria parasite",
                        "result": long_result,
                        "unit": "",
                        "reference": "",
                        "flag": "",
                        "group": "Malaria parasite",
                        "note": "Collected before treatment.\nSee the blood film comment.",
                    }
                ],
            )
        sheet = captured["content"].decode("latin-1")
        self.assertIn("(Malaria parasite)", sheet)
        self.assertIn("(Numerous trophozoites of Plasmodium falciparum seen.)", sheet)
        self.assertIn("(No gametocytes. Repeat film in 24 hours if symptoms continue.)", sheet)
        self.assertIn("(Collected before treatment.)", sheet)
        self.assertIn("(See the blood film comment.)", sheet)
        self.assertNotIn("...", sheet)

    def test_low_flag_is_not_red(self) -> None:
        sheet = self._sheet("Low")
        self.assertNotIn(lab_result_report.HIGH_INK, sheet)
        self.assertIn("Low", sheet)


class ValidatorNameTest(unittest.TestCase):
    def test_sheet_uses_the_person_who_released_the_result(self) -> None:
        order = {"uuid": "order-1"}
        laboratory.WORKFLOW_VALIDATORS["order-1"] = "Ada Okonkwo"
        try:
            with patch.object(laboratory, "_orders_on_same_request", return_value=[order]):
                self.assertEqual(laboratory.validator_name_for_order(order, "printer-cookie"), "Ada Okonkwo")
        finally:
            laboratory.WORKFLOW_VALIDATORS.pop("order-1", None)

    def test_printing_does_not_name_the_person_at_the_printer(self) -> None:
        import inspect

        source = inspect.getsource(lab_result_report.result_pdf)
        self.assertNotIn("signed_in_staff_name", source)


if __name__ == "__main__":
    unittest.main()
