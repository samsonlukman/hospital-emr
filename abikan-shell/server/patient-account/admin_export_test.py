"""Hospital Admin data export — authorization, history, filters, and formats."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import admin_export as exports
import admin_export_formats as formats
import admin_export_store as store
import finance_summary as finance
from server import ApiError


ADMIN = {
    "uuid": "admin-1",
    "username": "hospitaladmin.abikan",
    "display": "Hospital Administrator",
    "roles": ["Abikan:Hospital Admin"],
    "privileges": ["abikan:admin:staff"],
}
DOCTOR = {
    "uuid": "doc-1",
    "username": "doctor.abikan",
    "roles": ["Abikan:Doctor"],
    "privileges": ["app:clinical"],
}


class FormatWriters(unittest.TestCase):
    def test_csv_xlsx_json_and_pdf_contain_filtered_rows(self) -> None:
        columns = ["Patient", "Hospital number"]
        rows = [{"Patient": "Ada Okafor", "Hospital number": "ABC200001"}]
        meta = {"periodLabel": "Today", "departmentLabel": "All departments", "statusLabel": "All"}
        csv_text = formats.render_csv(columns, rows).decode("utf-8-sig")
        self.assertIn("Patient,Hospital number", csv_text)
        self.assertIn("Ada Okafor,ABC200001", csv_text)
        json_text = formats.render_json("Patients", columns, rows, meta).decode("utf-8")
        self.assertIn("Ada Okafor", json_text)
        self.assertIn('"recordCount": 1', json_text)
        xlsx = formats.render_xlsx("Patients", columns, rows)
        self.assertTrue(xlsx.startswith(b"PK"))
        with zipfile.ZipFile(BytesIO(xlsx)) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("Ada Okafor", sheet)
        pdf = formats.render_pdf("Patients", columns, rows, meta)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"Ada Okafor", pdf)

    def test_pdf_caps_large_tables_and_points_staff_to_excel(self) -> None:
        columns = ["Row"]
        rows = [{"Row": str(index)} for index in range(formats.PDF_ROW_LIMIT + 25)]
        pdf = formats.render_pdf("Patients", columns, rows, {"periodLabel": "This month"})
        self.assertIn(b"Use CSV or Excel", pdf)
        self.assertNotIn(b"2500", pdf)


class ExportStore(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = str(Path(self.directory.name) / "admin-audit.sqlite3")
        self.root = str(Path(self.directory.name) / "exports")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_expired_file_is_removed_and_cannot_be_read(self) -> None:
        export_id = "exportready01"
        store.write_file(export_id, b"secret-rows", root=self.root)
        store.insert_export(
            actor=ADMIN,
            dataset="patients",
            dataset_label="Patients",
            fmt="csv",
            department="",
            department_label="All departments",
            status_filter="",
            period="today",
            period_label="Today",
            start_date="2026-09-07",
            end_date="2026-09-07",
            record_count=2,
            file_size=11,
            filename="Hospital EMR-Patients-Today.csv",
            content_type="text/csv",
            outcome="success",
            file_status="available",
            expires_at=store.default_expiry(now=datetime(2026, 9, 6, tzinfo=timezone.utc), hours=1),
            path=self.db,
            export_id=export_id,
        )
        removed = store.expire_due_files(
            path=self.db,
            root=self.root,
            now=datetime(2026, 9, 7, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(removed, 1)
        self.assertEqual(store.get_export(export_id, path=self.db)["file_status"], "expired")
        with self.assertRaises(FileNotFoundError):
            store.read_file(export_id, root=self.root)


class Authorization(unittest.TestCase):
    def test_non_admin_cannot_open_catalog_or_history(self) -> None:
        with patch.object(
            exports.administration,
            "require_hospital_admin",
            side_effect=ApiError(403, "forbidden", exports.EXPORT_FORBIDDEN),
        ):
            with self.assertRaises(ApiError) as error:
                exports.catalog("cookie")
            self.assertEqual(error.exception.status, 403)
            with self.assertRaises(ApiError) as error:
                exports.list_history("cookie")
            self.assertEqual(error.exception.status, 403)

    def test_non_admin_cannot_generate_or_download(self) -> None:
        with patch.object(
            exports.administration,
            "require_hospital_admin",
            side_effect=ApiError(403, "forbidden", exports.EXPORT_FORBIDDEN),
        ):
            with self.assertRaises(ApiError) as error:
                exports.generate_export({"dataset": "patients", "format": "csv"}, "cookie")
            self.assertEqual(error.exception.status, 403)
            with self.assertRaises(ApiError) as error:
                exports.download_export("missing", "cookie")
            self.assertEqual(error.exception.status, 403)


class Generation(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = str(Path(self.directory.name) / "admin-audit.sqlite3")
        self.root = str(Path(self.directory.name) / "exports")
        self.audit_db = self.db

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_successful_export_writes_history_filters_and_record_count(self) -> None:
        rows = (
            ["Name", "Hospital number"],
            [{"Name": "Ada", "Hospital number": "ABC1"}],
        )
        Path(self.root).mkdir(parents=True, exist_ok=True)
        with (
            patch.object(exports.administration, "require_hospital_admin", return_value=ADMIN),
            patch.object(exports.store, "expire_due_files", return_value=0),
            patch.object(exports.admin_audit, "start_admin_event", return_value="audit-1"),
            patch.object(exports.admin_audit, "finish_admin_event"),
            patch.object(exports, "_load_rows", return_value=rows),
            patch.dict("os.environ", {"ABIKAN_EXPORT_FILES_ROOT": self.root, "ABIKAN_ADMIN_AUDIT_DB": self.db}),
        ):
            payload = exports.generate_export(
                {
                    "dataset": "patients",
                    "format": "csv",
                    "period": "today",
                    "department": "",
                },
                "cookie",
            )
        record = payload["export"]
        self.assertEqual(record["datasetLabel"], "Patients")
        self.assertEqual(record["formatLabel"], "CSV")
        self.assertEqual(record["recordCount"], 1)
        self.assertEqual(record["outcome"], "success")
        self.assertEqual(record["departmentLabel"], "All departments")
        self.assertTrue(record["canDownload"])
        listed = store.list_exports(path=self.db)
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["exports"][0]["record_count"], 1)
        self.assertEqual(listed["exports"][0]["period_label"], "Today")

    def test_failed_export_is_recorded_without_file(self) -> None:
        Path(self.root).mkdir(parents=True, exist_ok=True)
        with (
            patch.object(exports.administration, "require_hospital_admin", return_value=ADMIN),
            patch.object(exports.store, "expire_due_files", return_value=0),
            patch.object(exports.admin_audit, "start_admin_event", return_value="audit-2"),
            patch.object(exports.admin_audit, "finish_admin_event"),
            patch.object(exports, "_load_rows", side_effect=RuntimeError("boom")),
            patch.dict("os.environ", {"ABIKAN_EXPORT_FILES_ROOT": self.root, "ABIKAN_ADMIN_AUDIT_DB": self.db}),
        ):
            with self.assertRaises(ApiError) as error:
                exports.generate_export({"dataset": "patients", "format": "json", "period": "today"}, "cookie")
        self.assertEqual(error.exception.code, "export_failed")
        listed = store.list_exports(path=self.db)
        self.assertEqual(listed["exports"][0]["outcome"], "failed")
        self.assertEqual(listed["exports"][0]["file_status"], "none")
        self.assertEqual(listed["exports"][0]["record_count"], 0)

    def test_expired_export_cannot_be_downloaded(self) -> None:
        export_id = "expiredfile01"
        store.insert_export(
            actor=ADMIN,
            dataset="revenue",
            dataset_label="Revenue by department",
            fmt="csv",
            department="",
            department_label="All departments",
            status_filter="",
            period="today",
            period_label="Today",
            start_date="2026-09-07",
            end_date="2026-09-07",
            record_count=9,
            file_size=20,
            filename="Hospital EMR-Revenue-Today.csv",
            content_type="text/csv",
            outcome="success",
            file_status="expired",
            expires_at="2026-09-07T00:00:00+00:00",
            path=self.db,
            export_id=export_id,
        )
        with (
            patch.object(exports.administration, "require_hospital_admin", return_value=ADMIN),
            patch.object(exports.store, "expire_due_files", return_value=0),
            patch.object(exports.store, "get_export", return_value=store.get_export(export_id, path=self.db)),
        ):
            with self.assertRaises(ApiError) as error:
                exports.download_export(export_id, "cookie")
        self.assertEqual(error.exception.status, 410)
        self.assertEqual(error.exception.code, "export_expired")


class FinancialReuse(unittest.TestCase):
    def test_invoice_export_uses_posted_odoo_domain_and_skips_reversed(self) -> None:
        odoo = MagicMock()
        odoo.search_read.side_effect = [
            [
                {
                    "id": 1,
                    "name": "INV/2026/00001",
                    "invoice_date": "2026-09-07",
                    "invoice_origin": "S0001",
                    "amount_total": 300.0,
                    "amount_residual": 300.0,
                    "payment_state": "not_paid",
                    "invoice_line_ids": [],
                    "partner_id": [4, "Ada"],
                },
                {
                    "id": 2,
                    "name": "INV/2026/00002",
                    "invoice_date": "2026-09-07",
                    "invoice_origin": "S0002",
                    "amount_total": 900.0,
                    "amount_residual": 0.0,
                    "payment_state": "reversed",
                    "invoice_line_ids": [],
                    "partner_id": [5, "Bola"],
                },
            ],
            [{"name": "S0001", "shop_id": [11, "Pharmacy Counter"]}],
        ]
        odoo.read.return_value = [{"id": 4, "name": "Ada", "ref": "ABC1"}]
        with patch.object(exports.analytics, "_hospital_currency", return_value={"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}):
            with patch.object(exports.core, "format_money", side_effect=lambda amount, _currency: {"formatted": f"₦{amount:.2f}"}):
                rows = exports._posted_invoices(
                    odoo,
                    "2026-09-07",
                    "2026-09-07",
                    status="posted",
                    department="",
                )
        self.assertEqual(odoo.search_read.call_args_list[0][0][1], finance.billed_domain("2026-09-07", "2026-09-07"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Invoice"], "INV/2026/00001")
        self.assertEqual(rows[0]["Department"], "Pharmacy")

    def test_revenue_export_reuses_billed_by_department(self) -> None:
        request = {
            "window": {"startDate": "2026-09-01", "endDate": "2026-09-07"},
            "department": "",
        }
        with (
            patch.object(exports.cashier, "odoo_reader", return_value=MagicMock()),
            patch.object(exports.analytics, "_hospital_currency", return_value={"code": "NGN", "symbol": "₦", "decimalPlaces": 2, "position": "before"}),
            patch.object(exports.finance, "billed_by_department", return_value={"Pharmacy": 300.0, "Consultation": 20000.0}) as billed,
            patch.object(exports.core, "format_money", side_effect=lambda amount, _currency: {"formatted": f"₦{amount:,.2f}"}),
        ):
            columns, rows = exports._load_revenue(request, "cookie")
        billed.assert_called_once()
        self.assertEqual(billed.call_args[0][1], "2026-09-01")
        self.assertEqual(billed.call_args[0][2], "2026-09-07")
        self.assertEqual(columns[0], "Department")
        pharmacy = next(row for row in rows if row["Department"] == "Pharmacy")
        self.assertEqual(pharmacy["Revenue generated"], "₦300.00")

    def test_refunds_use_posted_credit_notes_only(self) -> None:
        domain = finance.refund_domain("2026-09-01", "2026-09-07")
        self.assertIn(("move_type", "=", "out_refund"), domain)
        self.assertIn(("state", "=", "posted"), domain)


class Catalog(unittest.TestCase):
    def test_catalog_lists_supported_datasets_and_formats(self) -> None:
        with (
            patch.object(exports.administration, "require_hospital_admin", return_value=ADMIN),
            patch.object(exports.store, "expire_due_files", return_value=0),
        ):
            payload = exports.catalog("cookie")
        ids = {item["id"] for item in payload["datasets"]}
        self.assertIn("patients", ids)
        self.assertIn("revenue", ids)
        self.assertIn("invoices", ids)
        self.assertIn("payments", ids)
        self.assertEqual({item["id"] for item in payload["formats"]}, {"csv", "xlsx", "pdf", "json"})


if __name__ == "__main__":
    unittest.main()
