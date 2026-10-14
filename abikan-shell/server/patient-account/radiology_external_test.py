"""External radiology study helpers."""

from __future__ import annotations

import unittest

import radiology_external as external


class RadiologyExternalKeys(unittest.TestCase):
    def test_study_keys_are_namespaced(self) -> None:
        self.assertTrue(external.is_external_study_id("radiology-ext:abc:0"))
        self.assertFalse(external.is_external_study_id("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
        self.assertEqual(external.study_external_key("token1", 2), "radiology-ext:token1:2")

    def test_request_source_normalization(self) -> None:
        self.assertEqual(external._normalize_request_source("External Referral"), "external_referral")
        self.assertEqual(external._normalize_request_source("radiology_direct"), "radiology_direct")
        self.assertEqual(external._normalize_request_source("doctor"), "external_referral")

    def test_request_source_labels(self) -> None:
        self.assertEqual(external.request_source_label("external_referral"), "External Referral")
        self.assertEqual(external.request_source_label("radiology_direct"), "Radiology Direct")


if __name__ == "__main__":
    unittest.main()
