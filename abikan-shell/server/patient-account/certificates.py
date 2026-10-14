"""Birth and death certificates for Hospital Administration.

The letterhead matches the hospital certificate. Values are stored here.
A death certificate also marks the patient Dead.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import hospital_admin
import patient_directory
import patient_life_status
from server import ApiError

DB_PATH = os.environ.get("ABIKAN_CERT_DB", "/var/lib/abikan/certificates.sqlite3")
ASSETS = Path(__file__).resolve().parent / "assets"
KINDS = ("birth", "death")
GENDERS = ("Male", "Female")


def _db(path: str | None = None) -> sqlite3.Connection:
    selected = Path(path or DB_PATH)
    selected.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(selected)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS certificates (
          patient_uuid TEXT NOT NULL,
          kind TEXT NOT NULL,
          reference_no TEXT NOT NULL,
          occurred_at TEXT NOT NULL,
          child_name TEXT NOT NULL DEFAULT '',
          patient_name TEXT NOT NULL DEFAULT '',
          gender TEXT NOT NULL DEFAULT '',
          weight TEXT NOT NULL DEFAULT '',
          mother_name TEXT NOT NULL DEFAULT '',
          father_name TEXT NOT NULL DEFAULT '',
          case_id TEXT NOT NULL DEFAULT '',
          guardian_name TEXT NOT NULL DEFAULT '',
          address TEXT NOT NULL DEFAULT '',
          report TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_by TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (patient_uuid, kind)
        )
        """
    )
    connection.commit()
    return connection


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _kind(value: Any) -> str:
    kind = _text(value, 20).lower()
    if kind not in KINDS:
        raise ApiError(422, "certificate_kind", "Choose a birth certificate or a death certificate.")
    return kind


def _gender(value: Any) -> str:
    text = _text(value, 20)
    match = next((item for item in GENDERS if item.lower() == text.lower()), "")
    if not match:
        raise ApiError(422, "gender_required", "Choose Male or Female.")
    return match


def _occurred(value: Any) -> str:
    text = _text(value, 32).replace(" ", "T")
    if len(text) == 10:
        text += "T00:00"
    try:
        datetime.strptime(text[:16], "%Y-%m-%dT%H:%M")
    except ValueError as error:
        raise ApiError(422, "certificate_date", "Enter the date and time.") from error
    return text[:16]


def display_stamp(value: str) -> str:
    moment = datetime.strptime(value[:16], "%Y-%m-%dT%H:%M")
    return moment.strftime("%m/%d/%Y %I:%M %p")


def weight_label(value: str) -> str:
    text = value.strip()
    if not text or any(character.isalpha() for character in text):
        return text
    return f"{text}kg"


def _patient_name(record: dict[str, Any], *, with_number: bool) -> str:
    family = str(record.get("familyName") or "").strip()
    given = str(record.get("givenName") or "").strip()
    middle = str(record.get("middleName") or "").strip()
    name = " ".join(part for part in (family, given, middle) if part).strip()
    if not name:
        name = "Unnamed patient"
    number = str(record.get("identifier") or "").strip()
    if with_number and number:
        return f"{name} ({number})"
    return name


def _address(record: dict[str, Any]) -> str:
    address = record.get("address") if isinstance(record.get("address"), dict) else {}
    parts = [
        address.get("address1"),
        address.get("address2"),
        address.get("cityVillage"),
        address.get("stateProvince"),
    ]
    return ", ".join(str(part).strip() for part in parts if str(part or "").strip())


def _sex(record: dict[str, Any]) -> str:
    key = str(record.get("gender") or "").strip().upper()
    if key == "M":
        return "Male"
    if key == "F":
        return "Female"
    return ""


def _blank(kind: str, record: dict[str, Any]) -> dict[str, str]:
    sex = _sex(record)
    address = _address(record)
    if kind == "birth":
        birth = str(record.get("birthdate") or "")
        return {
            "referenceNo": "",
            "occurredAt": f"{birth}T00:00" if birth else "",
            "childName": _patient_name(record, with_number=False),
            "gender": sex,
            "weight": "",
            "motherName": "",
            "fatherName": "",
            "caseId": "",
            "address": address,
        }
    death = str(record.get("deathDate") or "")
    return {
        "referenceNo": "",
        "occurredAt": f"{death}T09:00" if death else "",
        "patientName": _patient_name(record, with_number=True),
        "gender": sex,
        "caseId": "",
        "guardianName": "",
        "address": address,
        "report": "",
    }


def _row_form(row: sqlite3.Row) -> dict[str, str]:
    kind = row["kind"]
    common = {
        "referenceNo": row["reference_no"],
        "occurredAt": row["occurred_at"],
        "gender": row["gender"],
        "caseId": row["case_id"],
        "address": row["address"],
    }
    if kind == "birth":
        return {
            **common,
            "certificateId": row["patient_uuid"],
            "childName": row["child_name"],
            "weight": row["weight"],
            "motherName": row["mother_name"],
            "fatherName": row["father_name"],
        }
    return {
        **common,
        "patientName": row["patient_name"],
        "guardianName": row["guardian_name"],
        "report": row["report"],
    }


def _next_reference(connection: sqlite3.Connection, kind: str) -> str:
    prefix = "BRRN" if kind == "birth" else "DRRN"
    highest = 0
    for row in connection.execute("SELECT reference_no FROM certificates WHERE kind = ?", (kind,)):
        suffix = str(row["reference_no"] or "")[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1}"


def load(cookie: str, patient_uuid: str, *, db_path: str | None = None) -> dict[str, Any]:
    hospital_admin.require_hospital_admin(cookie)
    record = patient_directory.load_patient_record(patient_uuid, cookie)
    connection = _db(db_path)
    try:
        saved = {
            row["kind"]: _row_form(row)
            for row in connection.execute(
                "SELECT * FROM certificates WHERE patient_uuid = ?",
                (patient_uuid,),
            )
        }
    finally:
        connection.close()
    alive = bool(record.get("alive", True))
    return {
        "status": "ok",
        "patient": {
            "uuid": patient_uuid,
            "name": _patient_name(record, with_number=False),
            "hospitalNumber": str(record.get("identifier") or ""),
            "alive": alive,
            "status": "Alive" if alive else "Dead",
        },
        "birth": saved.get("birth") or _blank("birth", record),
        "death": saved.get("death") or _blank("death", record),
        "saved": {"birth": "birth" in saved, "death": "death" in saved},
    }


def _fields(kind: str, body: dict[str, Any], connection: sqlite3.Connection) -> dict[str, str]:
    reference = _text(body.get("referenceNo"), 40) or _next_reference(connection, kind)
    occurred = _occurred(body.get("occurredAt"))
    gender = _gender(body.get("gender"))
    address = _text(body.get("address"), 400)
    case_id = _text(body.get("caseId"), 40)
    if kind == "birth":
        child = _text(body.get("childName"), 160)
        if not child:
            raise ApiError(422, "name_required", "Enter the child's name.")
        return {
            "reference_no": reference,
            "occurred_at": occurred,
            "child_name": child,
            "patient_name": "",
            "gender": gender,
            "weight": _text(body.get("weight"), 20),
            "mother_name": _text(body.get("motherName"), 160),
            "father_name": _text(body.get("fatherName"), 160),
            "case_id": case_id,
            "guardian_name": "",
            "address": address,
            "report": "",
        }
    patient = _text(body.get("patientName"), 160)
    if not patient:
        raise ApiError(422, "name_required", "Enter the patient's name.")
    return {
        "reference_no": reference,
        "occurred_at": occurred,
        "child_name": "",
        "patient_name": patient,
        "gender": gender,
        "weight": "",
        "mother_name": "",
        "father_name": "",
        "case_id": case_id,
        "guardian_name": _text(body.get("guardianName"), 160),
        "address": address,
        "report": _text(body.get("report"), 800),
    }


def save(cookie: str, body: dict[str, Any], *, db_path: str | None = None) -> dict[str, Any]:
    actor = hospital_admin.require_hospital_admin(cookie)
    kind = _kind((body or {}).get("kind"))
    if kind == "birth":
        patient_uuid = _text((body or {}).get("certificateId"), 64) or f"birth-{uuid4()}"
        if not patient_uuid.startswith("birth-"):
            raise ApiError(422, "certificate_required", "This birth certificate could not be saved. Try again.")
    else:
        patient_uuid = _text((body or {}).get("patientUuid"), 64)
        if not patient_uuid:
            raise ApiError(422, "patient_required", "Choose the patient for this death certificate.")
        patient_directory.load_patient_record(patient_uuid, cookie)
    connection = _db(db_path)
    try:
        fields = _fields(kind, body or {}, connection)
        connection.execute(
            """
            INSERT INTO certificates (
              patient_uuid, kind, reference_no, occurred_at, child_name, patient_name,
              gender, weight, mother_name, father_name, case_id, guardian_name,
              address, report, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(patient_uuid, kind) DO UPDATE SET
              reference_no = excluded.reference_no,
              occurred_at = excluded.occurred_at,
              child_name = excluded.child_name,
              patient_name = excluded.patient_name,
              gender = excluded.gender,
              weight = excluded.weight,
              mother_name = excluded.mother_name,
              father_name = excluded.father_name,
              case_id = excluded.case_id,
              guardian_name = excluded.guardian_name,
              address = excluded.address,
              report = excluded.report,
              updated_at = CURRENT_TIMESTAMP,
              updated_by = excluded.updated_by
            """,
            (
                patient_uuid,
                kind,
                fields["reference_no"],
                fields["occurred_at"],
                fields["child_name"],
                fields["patient_name"],
                fields["gender"],
                fields["weight"],
                fields["mother_name"],
                fields["father_name"],
                fields["case_id"],
                fields["guardian_name"],
                fields["address"],
                fields["report"],
                str(actor.get("username") or actor.get("display") or ""),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    if kind == "death":
        patient_life_status.update_life_status(
            patient_uuid,
            {
                "alive": False,
                "deathDate": fields["occurred_at"][:10],
                "requestId": f"death-certificate-{patient_uuid}-{fields['occurred_at'][:10]}",
            },
            cookie,
        )
    if kind == "birth":
        return {
            "status": "ok",
            "message": "Birth certificate saved.",
            "birth": _stored(patient_uuid, "birth", db_path=db_path),
        }
    payload = load(cookie, patient_uuid, db_path=db_path)
    payload["message"] = "Death certificate saved. The patient status is Dead."
    return payload


def _stored(patient_uuid: str, kind: str, *, db_path: str | None) -> dict[str, str]:
    connection = _db(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM certificates WHERE patient_uuid = ? AND kind = ?",
            (patient_uuid, kind),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ApiError(404, "certificate_missing", "Save the certificate before downloading it.")
    return _row_form(row)


def pdf_bytes(cookie: str, patient_uuid: str, kind: str, *, db_path: str | None = None) -> tuple[bytes, str]:
    hospital_admin.require_hospital_admin(cookie)
    selected = _kind(kind)
    form = _stored(patient_uuid, selected, db_path=db_path)
    return render_pdf(selected, form), f"{form['referenceNo']}.pdf"


def render_pdf(kind: str, form: dict[str, str]) -> bytes:
    title = "Birth Record" if kind == "birth" else "Death Record"
    date_label = "Birth Date" if kind == "birth" else "Death Date"
    if kind == "birth":
        rows = [
            ("Child Name :", form.get("childName") or "", "Gender :", form.get("gender") or ""),
            ("Weight :", weight_label(form.get("weight") or ""), "Mother Name :", form.get("motherName") or ""),
            ("Case ID :", form.get("caseId") or "", "Father Name :", form.get("fatherName") or ""),
            ("Address :", form.get("address") or "", "", ""),
        ]
    else:
        rows = [
            ("Patient Name :", form.get("patientName") or "", "Case ID :", form.get("caseId") or ""),
            ("Gender :", form.get("gender") or "", "Guardian Name :", form.get("guardianName") or ""),
            ("Address :", form.get("address") or "", "Report :", form.get("report") or ""),
        ]
    header = ASSETS / f"certificate-header-{kind}.jpg"
    if not header.is_file():
        raise ApiError(500, "certificate_unavailable", "The certificate could not be prepared.")
    return _compose(
        header.read_bytes(),
        reference=form.get("referenceNo") or "",
        date_label=date_label,
        stamp=display_stamp(form["occurredAt"]) if form.get("occurredAt") else "",
        rows=rows,
        title_unused=title,
    )


def _label_x(text: str, right_edge: float) -> float:
    return round(right_edge - (len(text) * 7.5 * 0.48), 1)


def _escape(value: str) -> str:
    encoded = value.encode("latin-1", "replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _compose(
    jpeg: bytes,
    *,
    reference: str,
    date_label: str,
    stamp: str,
    rows: list[tuple[str, str, str, str]],
    title_unused: str,
) -> bytes:
    del title_unused
    page_h = 792
    header_h = 122
    top = 146
    row_h = 16.5
    box_h = 18 + row_h * max(len(rows), 1)
    commands = [
        "q",
        f"612 0 0 {header_h} 0 {page_h - header_h} cm",
        "/Im1 Do",
        "Q",
        "BT",
        "/F1 9 Tf",
        "0.067 0.067 0.067 rg",
        f"1 0 0 1 14 {page_h - 136} Tm",
        f"(Reference No: {_escape(reference)}) Tj",
        f"1 0 0 1 245 {page_h - 136} Tm",
        f"({_escape(date_label)}: {_escape(stamp)}) Tj",
        "ET",
        "0.976 0.980 0.984 rg",
        f"14.6 {page_h - top - box_h} 582.8 {box_h} re f",
        "0.631 0.631 0.667 RG",
        "0.8 w",
        f"14.6 {page_h - top - box_h} 582.8 {box_h} re S",
    ]
    for index, (left_label, left_value, right_label, right_value) in enumerate(rows):
        baseline = page_h - (160 + index * row_h)
        commands.extend(
            [
                "BT",
                "/F1 7.5 Tf",
                "0.067 0.067 0.067 rg",
                f"1 0 0 1 {_label_x(left_label, 144.4)} {baseline} Tm",
                f"({_escape(left_label)}) Tj",
                "/F2 8.6 Tf",
                f"1 0 0 1 152 {baseline} Tm",
                f"({_escape(left_value)}) Tj",
            ]
        )
        if right_label:
            commands.extend(
                [
                    "/F1 7.5 Tf",
                    f"1 0 0 1 {_label_x(right_label, 424.9)} {baseline} Tm",
                    f"({_escape(right_label)}) Tj",
                    "/F2 8.6 Tf",
                    f"1 0 0 1 432 {baseline} Tm",
                    f"({_escape(right_value)}) Tj",
                ]
            )
        commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")
    image = _image_object(jpeg)
    content = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> /XObject << /Im1 7 0 R >> >> "
        b"/Contents 4 0 R >>",
        content,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        image,
    ]
    return _assemble(objects)


def _image_object(jpeg: bytes) -> bytes:
    header = jpeg[:20]
    if header[0:2] != b"\xff\xd8":
        raise ApiError(500, "certificate_unavailable", "The certificate could not be prepared.")
    width, height = _jpeg_size(jpeg)
    return (
        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n"
    ).encode("ascii") + jpeg + b"\nendstream"


def _jpeg_size(data: bytes) -> tuple[int, int]:
    index = 2
    while index + 8 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in {0xC0, 0xC1, 0xC2}:
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        if marker == 0xD8 or marker == 0xD9:
            index += 2
            continue
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        index += 2 + length
    return 1224, 244


def _assemble(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii")
    )
    return bytes(output)
