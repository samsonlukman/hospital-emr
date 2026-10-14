"""File writers for Hospital Admin data exports.

CSV and Excel are the primary formats for large tables. JSON and PDF are
supported for the same filtered rows. These helpers never talk to OpenMRS or
Odoo; they only format rows already loaded by the export service.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Any
from xml.sax.saxutils import escape

FORMATS = ("csv", "xlsx", "pdf", "json")
CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "json": "application/json; charset=utf-8",
}
EXTENSIONS = {"csv": "csv", "xlsx": "xlsx", "pdf": "pdf", "json": "json"}
PDF_ROW_LIMIT = 1500


def format_label(fmt: str) -> str:
    return {"csv": "CSV", "xlsx": "Excel", "pdf": "PDF", "json": "JSON"}[fmt]


def validate_format(fmt: str) -> str:
    selected = (fmt or "").strip().lower()
    if selected not in FORMATS:
        raise ValueError("unsupported_format")
    return selected


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}"
    return str(value)


def render_export(
    *,
    fmt: str,
    title: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> bytes:
    selected = validate_format(fmt)
    if selected == "csv":
        return render_csv(columns, rows)
    if selected == "xlsx":
        return render_xlsx(title, columns, rows)
    if selected == "pdf":
        return render_pdf(title, columns, rows, meta)
    return render_json(title, columns, rows, meta)


def render_csv(columns: list[str], rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([cell_text(row.get(column)) for column in columns])
    return buffer.getvalue().encode("utf-8-sig")


def render_json(
    title: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> bytes:
    payload = {
        "title": title,
        "recordCount": len(rows),
        "filters": meta,
        "columns": columns,
        "rows": [{column: cell_text(row.get(column)) for column in columns} for row in rows],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def render_xlsx(title: str, columns: list[str], rows: list[dict[str, Any]]) -> bytes:
    sheet_name = _sheet_name(title)
    sheet = _sheet_xml(columns, rows)
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets><sheet name=\"{escape(sheet_name)}\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
        "</workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def _sheet_name(title: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in " -_" else "-" for ch in title).strip()
    return (cleaned or "Export")[:31]


def _col_letter(index: int) -> str:
    letters = ""
    remaining = index
    while remaining:
        remaining, rem = divmod(remaining - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_xml(columns: list[str], rows: list[dict[str, Any]]) -> str:
    cells: list[str] = []
    for col_index, heading in enumerate(columns, start=1):
        ref = f"{_col_letter(col_index)}1"
        cells.append(
            f'<c r="{ref}" t="inlineStr"><is><t>{escape(cell_text(heading))}</t></is></c>'
        )
    xml_rows = [f'<row r="1">{"".join(cells)}</row>']
    for row_index, row in enumerate(rows, start=2):
        cells = []
        for col_index, heading in enumerate(columns, start=1):
            ref = f"{_col_letter(col_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(cell_text(row.get(heading)))}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


def render_pdf(
    title: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> bytes:
    shown = rows[:PDF_ROW_LIMIT]
    note = ""
    if len(rows) > PDF_ROW_LIMIT:
        note = (
            f"Showing the first {PDF_ROW_LIMIT} of {len(rows)} rows. "
            "Use CSV or Excel for the full table."
        )
    filter_line = "  ".join(
        f"{key}: {value}"
        for key, value in (
            ("Date range", meta.get("periodLabel") or "All dates"),
            ("Department", meta.get("departmentLabel") or "All departments"),
            ("Status", meta.get("statusLabel") or "All"),
        )
        if value
    )
    pages = _pdf_pages(title, filter_line, note, columns, shown)
    return _assemble_pdf(pages)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_pages(
    title: str,
    filter_line: str,
    note: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> list[bytes]:
    page_width = 842
    page_height = 595
    left = 28
    usable = page_width - (left * 2)
    col_width = max(48, usable // max(len(columns), 1))
    char_limit = max(6, col_width // 6)
    header_lines = 5 if note else 4
    first_row_y = page_height - 36 - (header_lines * 14)
    rows_per_page = max(1, (first_row_y - 28) // 12)
    pages: list[bytes] = []
    for start in range(0, max(len(rows), 1), rows_per_page):
        chunk = rows[start : start + rows_per_page]
        commands = [
            "BT",
            "/F1 12 Tf",
            "28 560 Td",
            f"({_pdf_escape(title)}) Tj",
            "/F1 8 Tf",
            "0 -14 Td",
            f"({_pdf_escape(filter_line[:140])}) Tj",
        ]
        if note:
            commands.extend(["0 -14 Td", f"({_pdf_escape(note[:160])}) Tj"])
        commands.extend(["0 -18 Td", "/F1 8 Tf"])
        commands.append(_pdf_table_line(columns, col_width, char_limit, heading=True))
        for row in chunk:
            values = [cell_text(row.get(column)) for column in columns]
            commands.append("0 -12 Td")
            commands.append(_pdf_table_line(values, col_width, char_limit, heading=False))
        if not chunk:
            commands.extend(["0 -16 Td", "(No records matched these filters.) Tj"])
        commands.append("ET")
        pages.append("\n".join(commands).encode("latin-1", errors="replace"))
    return pages


def _pdf_table_line(
    values: list[str],
    col_width: int,
    char_limit: int,
    *,
    heading: bool,
) -> str:
    parts: list[str] = []
    for index, value in enumerate(values):
        text = value[:char_limit]
        x = index * col_width
        prefix = "0 Ts" if heading else "0 Ts"
        if index == 0:
            parts.append(f"({_pdf_escape(text)}) Tj")
        else:
            parts.append(f"{prefix} {x} 0 Td ({_pdf_escape(text)}) Tj -{x} 0 Td")
    return " ".join(parts)


def _assemble_pdf(pages: list[bytes]) -> bytes:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [3 + (index * 2) for index in range(len(pages))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode("ascii"))
    font_id = 3 + (len(pages) * 2)
    for index, content in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
            ).encode("ascii")
        )
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)
