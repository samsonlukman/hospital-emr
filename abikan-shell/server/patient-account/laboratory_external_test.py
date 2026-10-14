"""External laboratory patient helpers — unit tests, no live OpenMRS."""

from __future__ import annotations

import unittest

import laboratory
import laboratory_external as external


class LaboratoryExternalIdentifiers(unittest.TestCase):
    def test_display_and_openmrs_identifiers(self) -> None:
        self.assertEqual(external.display_external_id(1), "EXT-LAB-000001")
        self.assertEqual(external.display_external_id(42), "EXT-LAB-000042")
        self.assertEqual(external.openmrs_identifier_for(1), "EXTLAB000001")
        self.assertEqual(external.openmrs_identifier_for(99), "EXTLAB000099")

    def test_is_external_openmrs_identifier(self) -> None:
        self.assertTrue(external.is_external_openmrs_identifier("EXTLAB000001"))
        self.assertTrue(external.is_external_openmrs_identifier("extlab000012"))
        self.assertFalse(external.is_external_openmrs_identifier("ABC200012"))
        self.assertFalse(external.is_external_openmrs_identifier(""))


class LaboratoryExternalSources(unittest.TestCase):
    def test_request_source_normalization(self) -> None:
        self.assertEqual(external._normalize_request_source("External Referral"), "external_referral")
        self.assertEqual(external._normalize_request_source("laboratory_direct"), "laboratory_direct")
        self.assertEqual(external._normalize_request_source("direct"), "laboratory_direct")
        self.assertEqual(external._normalize_request_source("doctor"), "external_referral")

    def test_laboratory_source_labels(self) -> None:
        self.assertEqual(laboratory.request_source_label("laboratory_direct"), "Laboratory Direct")
        self.assertEqual(laboratory.request_source_label("external_referral"), "External Referral")
        self.assertEqual(laboratory.request_source_label("doctor_order"), "Doctor Order")

    def test_request_source_of_markers(self) -> None:
        self.assertEqual(
            laboratory.request_source_of("[Lab Direct] fasting sample"),
            "laboratory_direct",
        )
        self.assertEqual(
            laboratory.request_source_of("[External Referral] outside clinic"),
            "external_referral",
        )
        self.assertEqual(laboratory.request_source_of("routine panel"), "doctor_order")

    def test_direct_order_comment_markers(self) -> None:
        self.assertEqual(laboratory.direct_order_comment(""), "[Lab Direct]")
        self.assertEqual(
            laboratory.direct_order_comment("fasting", source="external_referral"),
            "[External Referral] fasting",
        )


if __name__ == "__main__":
    unittest.main()
