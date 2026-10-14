import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import laboratory_custom as custom
from server import ApiError


class CustomLabTestStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "laboratory_custom_tests.json"
        self.user = {"username": "lab.tech", "display": "Lab Tech"}

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_creates_test_with_columns_and_property_rows(self) -> None:
        with (
            patch.object(custom, "_store_path", return_value=self.path),
            patch.object(custom, "require_hospital_test_manager", return_value=self.user),
        ):
            payload = custom.create_custom_test(
                {
                    "name": "Custom Panel A",
                    "price": 2500,
                    "columns": ["WBC", "RBC"],
                    "properties": [
                        {"name": "Unit", "values": ["10^9/L", "10^12/L"]},
                        {"name": "Reference", "values": ["4-11", "4-6"]},
                    ],
                },
                "cookie",
            )
            listed = custom.list_custom_tests("cookie")

        self.assertEqual(payload["test"]["name"], "Custom Panel A")
        self.assertEqual(payload["test"]["columns"], ["WBC", "RBC"])
        self.assertEqual(len(payload["test"]["properties"]), 2)
        self.assertEqual(listed["tests"][0]["price"], 2500.0)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["tests"]), 1)

    def test_rejects_blank_test_name(self) -> None:
        with (
            patch.object(custom, "_store_path", return_value=self.path),
            patch.object(custom, "require_hospital_test_manager", return_value=self.user),
            self.assertRaises(ApiError) as raised,
        ):
            custom.create_custom_test(
                {"name": " ", "columns": ["A"], "properties": [{"name": "Unit", "values": ["x"]}]},
                "cookie",
            )
        self.assertEqual(raised.exception.status, 422)

    def test_rejects_duplicate_names(self) -> None:
        body = {
            "name": "Panel X",
            "columns": ["Result"],
            "properties": [{"name": "Unit", "values": ["mg/dL"]}],
        }
        with (
            patch.object(custom, "_store_path", return_value=self.path),
            patch.object(custom, "require_hospital_test_manager", return_value=self.user),
        ):
            custom.create_custom_test(body, "cookie")
            with self.assertRaises(ApiError) as raised:
                custom.create_custom_test(body, "cookie")
        self.assertEqual(raised.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
