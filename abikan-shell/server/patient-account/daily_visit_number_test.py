"""Daily visit number allocation — no OpenMRS writes."""

from __future__ import annotations

import threading
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import daily_visit_number as daily


class FormatAndParse(unittest.TestCase):
    def test_formats_three_digits(self) -> None:
        self.assertEqual(daily.format_daily_visit_number(1), "001")
        self.assertEqual(daily.format_daily_visit_number(12), "012")
        self.assertEqual(daily.format_daily_visit_number(100), "100")

    def test_parse_accepts_padded_and_plain(self) -> None:
        self.assertEqual(daily.parse_daily_visit_number("001"), 1)
        self.assertEqual(daily.parse_daily_visit_number("12"), 12)
        self.assertIsNone(daily.parse_daily_visit_number("ABC200016"))
        self.assertIsNone(daily.parse_daily_visit_number(""))
        self.assertIsNone(daily.parse_daily_visit_number("—"))

    def test_missing_display_is_honest(self) -> None:
        self.assertEqual(daily.display_daily_visit_number(None), "—")
        self.assertEqual(daily.display_daily_visit_number("001"), "001")


class Sequence(unittest.TestCase):
    def test_starts_at_one_when_none_assigned(self) -> None:
        self.assertEqual(daily.next_sequence_value([]), 1)

    def test_uses_max_stored_number_not_visit_count(self) -> None:
        self.assertEqual(daily.next_sequence_value(["001", None, "003", "—"]), 4)

    def test_unnumbered_visits_do_not_consume_the_sequence(self) -> None:
        self.assertEqual(daily.next_sequence_value([None, "", "—"]), 1)

    def test_hospital_date_resets_the_sequence(self) -> None:
        first = daily.next_sequence_value(["001", "002"])
        next_day = daily.next_sequence_value([])
        self.assertEqual(first, 3)
        self.assertEqual(next_day, 1)

    def test_lagos_day_boundary(self) -> None:
        import clinical_queue as queue

        before = datetime(2026, 8, 23, 22, 59, tzinfo=timezone.utc)
        after = datetime(2026, 8, 23, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(queue.hospital_today(before).isoformat(), "2026-08-23")
        self.assertEqual(queue.hospital_today(after).isoformat(), "2026-08-24")
        self.assertEqual(before.astimezone(ZoneInfo("Africa/Lagos")).date().isoformat(), "2026-08-23")


class PersistenceAndConcurrency(unittest.TestCase):
    def test_allocate_persists_before_return(self) -> None:
        store: list[str] = []
        number = daily.allocate_daily_visit_number(lambda: list(store), store.append)
        self.assertEqual(number, "001")
        self.assertEqual(store, ["001"])

    def test_concurrent_allocation_never_duplicates(self) -> None:
        store: list[str] = []
        lock = threading.Lock()
        barrier = threading.Barrier(12)

        def worker() -> None:
            barrier.wait()
            daily.allocate_daily_visit_number(lambda: list(store), store.append, lock=lock)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(store), [daily.format_daily_visit_number(i) for i in range(1, 13)])
        self.assertEqual(len(set(store)), 12)

    def test_client_supplied_number_is_ignored(self) -> None:
        self.assertIsNone(daily.ignore_client_number({"dailyVisitNumber": "999", "visitNumber": "002"}))
        store: list[str] = ["001"]
        number = daily.allocate_daily_visit_number(lambda: list(store), store.append)
        self.assertEqual(number, "002")


class Retrieval(unittest.TestCase):
    def test_reads_stored_attribute_only(self) -> None:
        visit = {
            "attributes": [
                {"attributeType": {"name": "Visit Status"}, "value": "OPD"},
                {"attributeType": {"name": "Daily Visit Number"}, "value": "003"},
            ]
        }
        self.assertEqual(daily.daily_visit_number_from_visit(visit), "003")

    def test_historical_visit_without_number(self) -> None:
        self.assertEqual(daily.daily_visit_number_from_visit({"attributes": []}), "")
        self.assertEqual(daily.sort_key(""), (1, 0))
        self.assertEqual(daily.sort_key("003"), (0, 3))

    def test_clinical_keeps_hospital_wide_gaps(self) -> None:
        rows = ["001", "", "003"]
        ordered = sorted(rows, key=daily.sort_key)
        self.assertEqual(ordered, ["001", "003", ""])


if __name__ == "__main__":
    unittest.main()
