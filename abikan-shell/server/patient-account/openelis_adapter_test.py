from __future__ import annotations

import unittest
from unittest.mock import patch

from openelis_adapter import OpenElisAdapter


class OpenElisAdapterTest(unittest.TestCase):
    @patch("openelis_adapter.OPENELIS_PASSWORD", "password")
    @patch("openelis_adapter.OPENELIS_USER", "admin")
    def test_resolves_patient_from_openelis_xml(self) -> None:
        adapter = OpenElisAdapter()
        with patch.object(
            adapter,
            "_request",
            return_value=(
                "application/xml",
                "<fieldmessage><formfield><result><patient>"
                "<first>ABIKAN</first><middle>UAT</middle><last>TEST PATIENT</last>"
                "<ST>ABC200021</ST><id>28</id></patient></result>"
                "</formfield><message>valid</message></fieldmessage>",
            ),
        ):
            self.assertEqual(
                adapter.resolve_patient("ABC200021"),
                {"id": "28", "identifier": "ABC200021", "name": "ABIKAN UAT TEST PATIENT"},
            )

    @patch("openelis_adapter.OPENELIS_PASSWORD", "password")
    @patch("openelis_adapter.OPENELIS_USER", "admin")
    def test_collection_payload_contains_xml_sample_and_patient(self) -> None:
        adapter = OpenElisAdapter()
        with patch.object(
            adapter,
            "_request",
            side_effect=[
                (
                    "application/xml",
                    "<fieldmessage><formfield><result><patient><ST>ABC200021</ST>"
                    "<id>28</id></patient></result></formfield>"
                    "<message>valid</message></fieldmessage>",
                ),
                ("text/html", "Sample saved"),
            ],
        ) as request:
            result = adapter.collect_sample(
                patient_identifier="ABC200021",
                sample_type_id="341",
                test_ids=["849"],
                sample_source_id="2",
                received_date="14/09/2026",
                accession="01092026-099",
            )
        self.assertEqual(result["accession"], "01092026-099")
        _, values = request.call_args_list[1].args[:2]
        self.assertIn("patientPK", values)
        self.assertIn("sampleID='341'", values["sampleXML"])
        self.assertIn("tests='849'", values["sampleXML"])

    @patch("openelis_adapter.OPENELIS_PASSWORD", "password")
    @patch("openelis_adapter.OPENELIS_USER", "admin")
    def test_result_payload_preserves_multiple_result_rows(self) -> None:
        adapter = OpenElisAdapter()
        with patch.object(adapter, "_request", return_value=("text/html", "Results saved")) as request:
            adapter.save_results(
                accession="01092026-099",
                results=[
                    {"testId": "849", "analysisId": "1", "resultValue": "Positive"},
                    {"testId": "850", "analysisId": "2", "resultValue": "12"},
                ],
            )
        values = request.call_args.args[1]
        self.assertEqual(values["testResult[1].testId"], "849")
        self.assertEqual(values["testResult[2].resultValue"], "12")


if __name__ == "__main__":
    unittest.main()
