"""A reference range belongs to the test, and a numeric result is marked from it."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import lab_reference_ranges


class ReferenceRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        lab_reference_ranges.DB_PATH = str(Path(self.folder.name) / "ranges.sqlite3")

    def tearDown(self) -> None:
        self.folder.cleanup()

    def test_a_range_is_kept_for_the_test_name(self) -> None:
        lab_reference_ranges.save_range("Packed Cell Volume", "36", "54", "lab.ada")
        found = lab_reference_ranges.ranges_for(["packed   cell volume"])
        self.assertEqual(found["packed cell volume"]["low"], "36")
        self.assertEqual(found["packed cell volume"]["high"], "54")

    def test_a_low_result_is_marked_low_and_critical_is_left_alone(self) -> None:
        low = {"resultValue": "20", "referenceLow": "36", "referenceHigh": "54", "flag": ""}
        lab_reference_ranges.apply_result_flag(low)
        self.assertEqual(low["flag"], "L")
        high = {"resultValue": "60", "referenceLow": "36", "referenceHigh": "54", "flag": ""}
        lab_reference_ranges.apply_result_flag(high)
        self.assertEqual(high["flag"], "H")
        inside = {"resultValue": "40", "referenceLow": "36", "referenceHigh": "54", "flag": "L"}
        lab_reference_ranges.apply_result_flag(inside)
        self.assertEqual(inside["flag"], "")
        critical = {"resultValue": "40", "referenceLow": "36", "referenceHigh": "54", "flag": "C"}
        lab_reference_ranges.apply_result_flag(critical)
        self.assertEqual(critical["flag"], "C")
        coded = {
            "resultValue": "Positive",
            "referenceLow": "36",
            "referenceHigh": "54",
            "flag": "",
            "options": [{"value": "Positive"}],
        }
        lab_reference_ranges.apply_result_flag(coded)
        self.assertEqual(coded["flag"], "")

    def test_a_one_sided_limit_marks_only_that_side(self) -> None:
        low_only = {"resultValue": "2", "referenceLow": "3.5", "referenceHigh": "", "flag": ""}
        lab_reference_ranges.apply_result_flag(low_only)
        self.assertEqual(low_only["flag"], "L")
        inside = {"resultValue": "4", "referenceLow": "3.5", "referenceHigh": "", "flag": "L"}
        lab_reference_ranges.apply_result_flag(inside)
        self.assertEqual(inside["flag"], "")

    def test_imported_ranges_stay_draft_until_approved(self) -> None:
        rows = lab_reference_ranges.list_ranges()
        haemoglobin = [row for row in rows if row["testName"] == "Haemoglobin" and row["purpose"] == "reference_interval"]
        self.assertGreater(len(haemoglobin), 10)
        self.assertTrue(all(row["status"] == "draft" for row in haemoglobin))
        self.assertTrue(all(row["sourceTitle"] for row in haemoglobin))
        chosen = lab_reference_ranges.select_reference(
            "Haemoglobin",
            sex="M",
            birth="12/10/1980",
            on_date="2026-10-12",
            unit="g/dL",
            specimen="Blood",
        )
        self.assertFalse(chosen["matched"])
        self.assertEqual(chosen["note"], lab_reference_ranges.NO_RANGE)

    def test_an_approved_range_follows_age_sex_and_unit(self) -> None:
        self._approve("Haemoglobin", "male")
        self._approve("Haemoglobin", "female")
        adult_male = lab_reference_ranges.select_reference(
            "Hemoglobin",
            sex="M",
            birth="12/10/1980",
            on_date="2026-10-12",
            unit="g/dL",
            specimen="Blood",
        )
        self.assertEqual(adult_male["low"], "13.2")
        self.assertEqual(adult_male["high"], "16.6")
        self.assertEqual(adult_male["publisher"], "Mayo Clinic Laboratories")
        seventeen = lab_reference_ranges.select_reference(
            "Hb",
            sex="male",
            birth="12/10/2009",
            on_date="2026-10-12",
            unit="g/dL",
        )
        self.assertEqual(seventeen["low"], "13.3")
        self.assertEqual(seventeen["high"], "16.9")
        newborn = lab_reference_ranges.select_reference(
            "Haemoglobin",
            sex="F",
            birth="28/09/2026",
            on_date="2026-10-12",
            unit="g/dL",
        )
        self.assertEqual(newborn["low"], "13.4")
        self.assertEqual(newborn["high"], "20.0")
        wrong_unit = lab_reference_ranges.select_reference(
            "Haemoglobin",
            sex="M",
            birth="12/10/1980",
            on_date="2026-10-12",
            unit="g/L",
        )
        self.assertFalse(wrong_unit["matched"])
        self.assertEqual(wrong_unit["note"], lab_reference_ranges.UNIT_NOTE)
        unknown_sex = lab_reference_ranges.select_reference(
            "Haemoglobin",
            sex="",
            birth="12/10/1980",
            on_date="2026-10-12",
            unit="g/dL",
        )
        self.assertFalse(unknown_sex["matched"])
        on = "2026-10-12"
        for days in range(0, 80):
            born = datetime.strptime(on, "%Y-%m-%d").date()
            birth = (born - timedelta(days=days)).strftime("%d/%m/%Y")
            chosen = lab_reference_ranges.select_reference(
                "Haemoglobin", sex="M", birth=birth, on_date=on, unit="g/dL", specimen="Blood"
            )
            self.assertNotEqual(chosen["note"], lab_reference_ranges.AMBIGUOUS, days)
        for years in range(0, 90):
            birth = f"12/10/{2026 - years}"
            chosen = lab_reference_ranges.select_reference(
                "Haemoglobin", sex="M", birth=birth, on_date=on, unit="g/dL", specimen="Blood"
            )
            self.assertNotEqual(chosen["note"], lab_reference_ranges.AMBIGUOUS, years)
            if years >= 18:
                self.assertEqual(chosen["text"], "13.2–16.6", years)

    def test_age_partitions_do_not_overlap(self) -> None:
        for name, sex in (
            ("Alkaline phosphatase", "male"),
            ("Alkaline phosphatase", "female"),
            ("Bicarbonate", "male"),
            ("Bicarbonate", "female"),
            ("AST", "male"),
            ("Chloride", ""),
            ("Platelet count", "female"),
            ("Neutrophils", "male"),
        ):
            self._approve(name, sex)
            for years in range(0, 40):
                chosen = lab_reference_ranges.select_reference(
                    name,
                    sex="M" if sex != "female" else "F",
                    birth=f"12/10/{2026 - years}",
                    on_date="2026-10-12",
                    unit="U/L" if name in {"Alkaline phosphatase", "AST"} else "mmol/L" if name in {"Bicarbonate", "Chloride"} else "x10(9)/L",
                )
                self.assertNotEqual(chosen["note"], lab_reference_ranges.AMBIGUOUS, (name, sex, years))

    def test_a_child_does_not_receive_an_adult_only_interval(self) -> None:
        self._approve("Sodium")
        infant = lab_reference_ranges.select_reference(
            "Serum sodium",
            sex="F",
            birth="12/04/2026",
            on_date="2026-10-12",
            unit="mmol/L",
            specimen="Serum",
        )
        self.assertFalse(infant["matched"])
        child = lab_reference_ranges.select_reference(
            "Sodium",
            sex="M",
            birth="12/10/2024",
            on_date="2026-10-12",
            unit="mmol/L",
        )
        self.assertEqual(child["text"], "135–145")

    def test_a_diagnostic_cutoff_is_not_approved_for_results(self) -> None:
        rows = lab_reference_ranges.list_ranges()
        cutoff = next(row for row in rows if row["purpose"] == "diagnostic_threshold" and row["testName"] == "Haemoglobin")
        with self.assertRaises(ValueError):
            lab_reference_ranges.apply_action({"action": "approve", "id": cutoff["id"]}, "lab.ada")
        chosen = lab_reference_ranges.select_reference(
            "Haemoglobin",
            sex="M",
            birth="12/10/1980",
            on_date="2026-10-12",
            unit="g/L",
        )
        self.assertFalse(chosen["matched"])

    def test_creatinine_has_no_invented_interval(self) -> None:
        rows = [
            row
            for row in lab_reference_ranges.list_ranges()
            if row["testName"] == "Creatinine"
        ]
        self.assertTrue(rows)
        self.assertTrue(all(not row["low"] and not row["high"] for row in rows))
        chosen = lab_reference_ranges.select_reference(
            "Serum creatinine (umol/L)",
            sex="M",
            birth="12/10/1980",
            on_date="2026-10-12",
            unit="umol/L",
        )
        self.assertFalse(chosen["matched"])

    def test_the_more_specific_approved_range_is_used(self) -> None:
        broad = lab_reference_ranges.apply_action(
            {
                "action": "save",
                "testName": "Demo enzyme",
                "low": "1",
                "high": "100",
                "unit": "U/L",
                "sex": "any",
                "sourceTitle": "Hospital verification study",
            },
            "lab.ada",
        )
        narrow = lab_reference_ranges.apply_action(
            {
                "action": "save",
                "testName": "Demo enzyme",
                "low": "8",
                "high": "40",
                "unit": "U/L",
                "sex": "male",
                "ageMin": "18",
                "ageMinUnit": "years",
                "sourceTitle": "Hospital verification study",
            },
            "lab.ada",
        )
        lab_reference_ranges.apply_action({"action": "approve", "id": broad["id"]}, "lab.ada")
        lab_reference_ranges.apply_action({"action": "approve", "id": narrow["id"]}, "lab.ada")
        man = lab_reference_ranges.select_reference(
            "Demo enzyme", sex="M", birth="12/10/1980", on_date="2026-10-12", unit="U/L"
        )
        self.assertEqual(man["text"], "8–40")
        child = lab_reference_ranges.select_reference(
            "Demo enzyme", sex="M", birth="12/10/2018", on_date="2026-10-12", unit="U/L"
        )
        self.assertEqual(child["text"], "1–100")

    def test_two_equal_approved_ranges_are_not_guessed(self) -> None:
        for low, high in (("1", "5"), ("2", "6")):
            saved = lab_reference_ranges.apply_action(
                {
                    "action": "save",
                    "testName": "Demo salt",
                    "low": low,
                    "high": high,
                    "unit": "mmol/L",
                    "sex": "female",
                    "sourceTitle": "Two different package inserts",
                },
                "lab.ada",
            )
            lab_reference_ranges.apply_action({"action": "approve", "id": saved["id"]}, "lab.ada")
        chosen = lab_reference_ranges.select_reference(
            "Demo salt", sex="F", birth="12/10/1990", on_date="2026-10-12", unit="mmol/L"
        )
        self.assertFalse(chosen["matched"])
        self.assertEqual(chosen["note"], lab_reference_ranges.AMBIGUOUS)

    def test_a_saved_result_keeps_its_own_range(self) -> None:
        self._approve("Sodium")
        tests = [
            {
                "name": "Sodium",
                "resultType": "N",
                "unit": "mmol/L",
                "savedReferenceLow": "130",
                "savedReferenceHigh": "150",
            }
        ]
        lab_reference_ranges.apply_to_tests(
            tests, sex="M", birth="12/10/1980", on_date="2026-10-12", specimen="Serum"
        )
        self.assertEqual(tests[0]["referenceLow"], "130")
        self.assertEqual(tests[0]["referenceSource"], "Saved with this result")

    def test_editing_an_approved_range_keeps_it_in_use(self) -> None:
        self._approve("Sodium")
        row = next(item for item in lab_reference_ranges.list_ranges() if item["testName"] == "Sodium" and item["status"] == "approved")
        saved = lab_reference_ranges.apply_action(
            {"action": "save", "id": row["id"], "low": "136", "high": "145", "unit": "mmol/L"},
            "lab.ada",
        )
        self.assertEqual(saved["status"], "approved")
        self.assertEqual(saved["low"], "136")
        chosen = lab_reference_ranges.select_reference(
            "Serum sodium",
            sex="F",
            birth="12/10/1990",
            on_date="2026-10-12",
            unit="mmol/L",
            specimen="Serum",
        )
        self.assertEqual(chosen["low"], "136")
        self.assertEqual(chosen["high"], "145")
        earlier_order = lab_reference_ranges.select_reference(
            "Serum sodium",
            sex="F",
            birth="12/10/1990",
            on_date="2020-01-15",
            unit="mmol/L",
            specimen="Serum",
        )
        self.assertEqual(earlier_order["low"], "136")

    def _approve(self, test_name: str, sex: str = "") -> None:
        for row in lab_reference_ranges.list_ranges():
            if row["testName"] != test_name or row["purpose"] != "reference_interval":
                continue
            if sex and row["sex"] != sex:
                continue
            if not row["low"] and not row["high"]:
                continue
            lab_reference_ranges.apply_action({"action": "approve", "id": row["id"]}, "lab.ada")


if __name__ == "__main__":
    unittest.main()
