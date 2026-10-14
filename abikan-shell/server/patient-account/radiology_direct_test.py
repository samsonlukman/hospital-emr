"""Radiology direct study and history helpers."""

from __future__ import annotations

import unittest

import radiology as imaging


class RadiologyRequestSource(unittest.TestCase):
    def test_doctor_order_is_default(self) -> None:
        self.assertEqual(imaging.request_source_of(comment="Chest pain"), imaging.SOURCE_DOCTOR_ORDER)
        self.assertEqual(imaging.request_source_label(imaging.SOURCE_DOCTOR_ORDER), "Doctor Order")

    def test_direct_marker_and_radiology_encounter(self) -> None:
        self.assertEqual(
            imaging.request_source_of(comment="[Radiology Direct] Fall"),
            imaging.SOURCE_RADIOLOGY_DIRECT,
        )
        self.assertEqual(
            imaging.request_source_of(encounter_type_uuid=imaging.RADIOLOGY_ENCOUNTER_TYPE),
            imaging.SOURCE_RADIOLOGY_DIRECT,
        )
        self.assertEqual(
            imaging.request_source_label(imaging.SOURCE_RADIOLOGY_DIRECT),
            "Radiology Direct",
        )

    def test_direct_comment_preserves_indication(self) -> None:
        self.assertEqual(
            imaging.direct_study_comment("Trauma series"),
            "[Radiology Direct] Trauma series",
        )
        self.assertEqual(
            imaging.clinical_indication_text("[Radiology Direct] Trauma series"),
            "Trauma series",
        )


if __name__ == "__main__":
    unittest.main()
