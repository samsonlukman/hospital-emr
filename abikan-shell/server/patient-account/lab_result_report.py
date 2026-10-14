"""Laboratory result sheet. Same columns as the laboratory report, with the hospital header."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from certificates import _assemble, _escape, _image_object
from server import ApiError

ASSETS = Path(__file__).resolve().parent / "assets"
HEADER = ASSETS / "certificate-header-birth.jpg"
WAT = ZoneInfo("Africa/Lagos")
FLAG_LABELS = {"L": "Low", "H": "High", "A": "Abnormal", "C": "Critical"}
HIGH_FLAGS = {"High", "Critical", "Abnormal"}
HIGH_INK = "0.75 0.13 0.13 rg"
BODY_INK = "0.1 0.15 0.2 rg"


def _display_result(row: dict[str, Any]) -> str:
    """Show Positive or Negative on the sheet, not the laboratory code behind it."""
    value = str(row.get("resultValue") or row.get("qualifiedResultValue") or "").strip()
    options = row.get("options") if isinstance(row.get("options"), list) else []
    for option in options:
        if not isinstance(option, dict):
            continue
        if str(option.get("value") or "").strip() != value:
            continue
        label = str(option.get("label") or "").strip()
        if label:
            return label
    return value


def result_pdf(order_uuid: str, patient_uuid: str | None, visit_uuid: str | None, cookie: str) -> tuple[bytes, str]:
    import laboratory

    source = laboratory.load_lab_order(order_uuid, patient_uuid, cookie)
    encounter = str(source.get("encounterUuid") or "").strip()
    patient = str(source.get("patientUuid") or patient_uuid or "").strip()
    siblings: list[dict[str, Any]] = []
    if encounter and patient:
        try:
            siblings = laboratory.list_lab_orders(patient, cookie)
        except Exception:
            siblings = []
        request_key = laboratory.order_request_key(source)
        siblings = [
            row
            for row in siblings
            if row.get("uuid") and laboratory.order_request_key(row) == request_key
        ]
    workflow = laboratory.build_lab_workflow(order_uuid, patient_uuid, visit_uuid or "", cookie)
    order = workflow.get("order") if isinstance(workflow.get("order"), dict) else {}
    tests = [row for row in workflow.get("tests") or [] if isinstance(row, dict)]
    ready = [row for row in tests if str(row.get("resultValue") or row.get("qualifiedResultValue") or "").strip()]
    if not ready:
        raise ApiError(
            422,
            "result_not_ready",
            "Save the completed tests before printing. Tests left blank are left off the sheet.",
        )
    ready_names = {
        str(row.get("orderedAs") or row.get("name") or "").strip().casefold()
        for row in ready
        if str(row.get("orderedAs") or row.get("name") or "").strip()
    }
    ready_names.update(
        str(row.get("name") or "").strip().casefold() for row in ready if str(row.get("name") or "").strip()
    )
    order_ids = [
        str(row.get("uuid") or "")
        for row in siblings
        if str(row.get("testName") or "").strip().casefold() in ready_names
    ]
    if not order_ids:
        order_ids = [str(source.get("uuid") or order_uuid)]
    try:
        reader = laboratory.odoo_reader()
        waiting = laboratory.orders_waiting_for_bill(reader, order_ids)
    except Exception:
        waiting = order_ids
    if waiting:
        raise ApiError(422, "bill_required", "Submit the bill before printing this result.")
    facts = laboratory.load_lab_order(order_uuid, patient_uuid, cookie)
    gender = {"M": "Male", "F": "Female", "O": "Other"}.get(str(facts.get("gender") or "").upper(), "")
    age = str(facts.get("age") or order.get("age") or "")
    age_sex = " / ".join(part for part in (age, gender) if part)
    printed = datetime.now(WAT).strftime("%d/%m/%Y %H:%M")
    validation = workflow.get("validation") if isinstance(workflow.get("validation"), dict) else {}
    try:
        validated_by = str(validation.get("validatedBy") or "") or laboratory.validator_name_for_order(facts, cookie)
    except Exception:
        validated_by = str(validation.get("validatedBy") or "")
    saved_notes = _saved_notes(facts, cookie)
    rows = []
    for row in ready:
        value = _display_result(row)
        if not value:
            continue
        low = str(row.get("referenceLow") or "").strip()
        high = str(row.get("referenceHigh") or "").strip()
        if low or high:
            reference = f"{low} - {high}"
        else:
            reference = ""
        name = str(row.get("name") or "Test")
        group = str(row.get("orderedAs") or "")
        note = str(row.get("note") or "")
        if not note.strip():
            note = saved_notes.get(name.casefold()) or saved_notes.get(group.casefold()) or ""
        rows.append(
            {
                "group": group,
                "name": name,
                "result": value,
                "unit": str(row.get("unit") or ""),
                "reference": reference,
                "flag": FLAG_LABELS.get(str(row.get("flag") or "").strip().upper(), ""),
                "note": note,
            }
        )
    pdf = render_result_pdf(
        header_jpeg=HEADER.read_bytes() if HEADER.is_file() else b"",
        patient=str(order.get("patientName") or facts.get("patientName") or "Patient"),
        mrn=str(order.get("mrn") or facts.get("mrn") or ""),
        age_sex=age_sex,
        accession=str(workflow.get("sample", {}).get("accession") or order.get("accession") or ""),
        tests=str(order.get("testName") or ""),
        printed=printed,
        validated_by=validated_by,
        rows=rows,
    )
    filename = f"laboratory-result-{(order.get('mrn') or order_uuid)[:24]}.pdf"
    return pdf, filename


def _saved_notes(order: dict[str, Any], cookie: str) -> dict[str, str]:
    import laboratory

    notes: dict[str, str] = {}
    try:
        saved = laboratory._saved_results_for_request(order, cookie)
    except Exception:
        return notes
    for item in saved:
        if not isinstance(item, dict):
            continue
        note = str(item.get("note") or "")
        if not note.strip():
            continue
        for key in (item.get("testName"), item.get("orderedAs"), item.get("name")):
            label = str(key or "").strip().casefold()
            if label and label not in notes:
                notes[label] = note
    return notes


def _wrap_text(value: str, width: int) -> list[str]:
    """Keep blank lines and wrap long report text without cutting it off."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    wrapped: list[str] = []
    for paragraph in text.split("\n"):
        if paragraph == "":
            wrapped.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            pieces = [word[index:index + width] for index in range(0, len(word), width)] or [""]
            for piece in pieces:
                candidate = piece if not current else f"{current} {piece}"
                if len(candidate) <= width:
                    current = candidate
                else:
                    if current:
                        wrapped.append(current)
                    current = piece
        wrapped.append(current)
    return wrapped or [""]


def _sections(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("group") or "").strip() or str(row.get("name") or "Test").strip() or "Test"
        if not sections or str(sections[-1]["title"]).casefold() != title.casefold():
            sections.append({"title": title, "rows": []})
        sections[-1]["rows"].append(row)
    return sections


def _write_lines(
    commands: list[str],
    *,
    x: float,
    y: float,
    lines: list[str],
    font: str,
    ink: str,
    leading: float,
) -> float:
    if not lines:
        return y
    commands.extend(["BT", font, ink])
    for line in lines:
        commands.append(f"1 0 0 1 {x:.1f} {y:.1f} Tm")
        commands.append(f"({_escape(line)}) Tj")
        y -= leading
    commands.append("ET")
    return y


def render_result_pdf(
    *,
    header_jpeg: bytes,
    patient: str,
    mrn: str,
    age_sex: str,
    accession: str,
    tests: str,
    printed: str,
    rows: list[dict[str, str]],
    validated_by: str = "",
) -> bytes:
    del tests
    if not header_jpeg.startswith(b"\xff\xd8"):
        raise ApiError(500, "result_unavailable", "The result could not be prepared.")
    page_h = 792
    commands: list[str] = []
    y = 0.0
    while page_h < 12000:
        commands, y = _compose_result_page(
            page_h=page_h,
            patient=patient,
            mrn=mrn,
            age_sex=age_sex,
            accession=accession,
            printed=printed,
            rows=rows,
            validated_by=validated_by,
        )
        if y >= 46:
            break
        page_h += int(46 - y) + 80
    stream = "\n".join(commands).encode("latin-1", "replace")
    content = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    image = _image_object(header_jpeg)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 612 {page_h}] >>".encode("ascii"),
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 "
            + str(page_h).encode("ascii")
            + b"] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> /XObject << /Im1 7 0 R >> >> /Contents 4 0 R >>"
        ),
        content,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        image,
    ]
    return _assemble(objects)


def _compose_result_page(
    *,
    page_h: int,
    patient: str,
    mrn: str,
    age_sex: str,
    accession: str,
    printed: str,
    rows: list[dict[str, str]],
    validated_by: str,
) -> tuple[list[str], float]:
    commands = [
        "q",
        f"612 0 0 122 0 {page_h - 122} cm",
        "/Im1 Do",
        "Q",
        "0.051 0.451 0.467 rg",
        f"0 {page_h - 122} 612 24 re f",
        "BT",
        "/F2 13 Tf",
        "1 1 1 rg",
        f"1 0 0 1 236 {page_h - 115} Tm",
        "(Laboratory Result) Tj",
        "ET",
    ]
    y = _write_lines(
        commands,
        x=36,
        y=page_h - 150,
        lines=[
            f"Patient: {patient}",
            f"Hospital number: {mrn}",
            f"Age / Sex: {age_sex}",
            f"Accession: {accession or '-'}",
            f"Printed: {printed}",
        ],
        font="/F1 9 Tf",
        ink=BODY_INK,
        leading=14,
    )
    y -= 18
    for section in _sections(rows):
        title_lines = _wrap_text(str(section["title"]), 70)
        bar_h = 16 + 13 * max(len(title_lines) - 1, 0)
        commands.extend(
            [
                "0.051 0.451 0.467 rg",
                f"28 {y - 4:.1f} 556 {bar_h:.1f} re f",
            ]
        )
        y = _write_lines(
            commands,
            x=36,
            y=y,
            lines=title_lines,
            font="/F2 11 Tf",
            ink="1 1 1 rg",
            leading=13,
        )
        y -= 8
        for row in section["rows"]:
            name = str(row.get("name") or "Test")
            if name.casefold() != str(section["title"]).casefold() or len(section["rows"]) > 1:
                y = _write_lines(
                    commands,
                    x=36,
                    y=y,
                    lines=_wrap_text(name, 80),
                    font="/F2 10 Tf",
                    ink="0.07 0.18 0.22 rg",
                    leading=13,
                )
                y -= 2
            flag = str(row.get("flag") or "")
            attention = flag in HIGH_FLAGS
            result_lines = _wrap_text(str(row.get("result") or "-"), 88)
            y = _write_lines(
                commands,
                x=36,
                y=y,
                lines=result_lines,
                font="/F2 10 Tf" if attention else "/F1 10 Tf",
                ink=HIGH_INK if attention else BODY_INK,
                leading=14,
            )
            meta = []
            if str(row.get("unit") or "").strip():
                meta.append(f"Unit: {row.get('unit')}")
            if str(row.get("reference") or "").strip():
                meta.append(f"Reference range: {row.get('reference')}")
            if flag:
                meta.append(flag)
            if meta:
                y -= 2
                y = _write_lines(
                    commands,
                    x=36,
                    y=y,
                    lines=_wrap_text("   ·   ".join(meta), 88),
                    font="/F2 9 Tf" if attention else "/F1 9 Tf",
                    ink=HIGH_INK if attention else "0.28 0.34 0.4 rg",
                    leading=12,
                )
            note = str(row.get("note") or "").strip("\n")
            if note.strip():
                y -= 4
                y = _write_lines(
                    commands,
                    x=36,
                    y=y,
                    lines=["Note"],
                    font="/F2 9 Tf",
                    ink="0.07 0.18 0.22 rg",
                    leading=12,
                )
                y = _write_lines(
                    commands,
                    x=36,
                    y=y,
                    lines=_wrap_text(note, 88),
                    font="/F1 10 Tf",
                    ink=BODY_INK,
                    leading=14,
                )
            y -= 8
        y -= 6
        commands.extend(
            [
                "0.75 0.8 0.84 RG",
                "0.8 w",
                f"28 {y:.1f} m 584 {y:.1f} l S",
            ]
        )
        y -= 16
    signature = " ".join(str(validated_by or "").split())
    if signature:
        y -= 6
        y = _write_lines(
            commands,
            x=36,
            y=y,
            lines=_wrap_text(f"Validated by: {signature}", 70),
            font="/F2 11 Tf",
            ink="0.07 0.18 0.22 rg",
            leading=14,
        )
        y -= 6
    y = _write_lines(
        commands,
        x=36,
        y=y,
        lines=["Hospital EMR"],
        font="/F1 8 Tf",
        ink="0.2 0.25 0.3 rg",
        leading=12,
    )
    return commands, y
