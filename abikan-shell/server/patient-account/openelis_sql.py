"""Small read/write access to the laboratory database.

Used only to keep a collected sample on the same visit the doctor ordered,
so a result is not saved on a second, unlinked sample.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import socket
import struct
from pathlib import Path
from typing import Any

HOST = os.environ.get("ABIKAN_OPENELIS_DB_HOST", "openelisdb").strip() or "openelisdb"
PORT = int(os.environ.get("ABIKAN_OPENELIS_DB_PORT", "5432") or "5432")
USER = os.environ.get("ABIKAN_OPENELIS_DB_USER", "clinlims").strip() or "clinlims"
DATABASE = os.environ.get("ABIKAN_OPENELIS_DB_NAME", "clinlims").strip() or "clinlims"
PASSWORD_FILE = os.environ.get("ABIKAN_OPENELIS_DB_PASSWORD_FILE", "/var/lib/abikan/elis-db.secret")

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ACCESSION = re.compile(r"^[0-9A-Za-z-]{4,20}$")


class OpenElisSqlError(RuntimeError):
    pass


def password() -> str:
    env = os.environ.get("ABIKAN_OPENELIS_DB_PASSWORD", "").strip()
    if env:
        return env
    try:
        return Path(PASSWORD_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _md5_password(user: str, secret: str, salt: bytes) -> bytes:
    inner = hashlib.md5(secret.encode("utf-8") + user.encode("utf-8")).hexdigest().encode("ascii")
    outer = hashlib.md5(inner + salt).hexdigest()
    return f"md5{outer}".encode("ascii") + b"\0"


def _read_exact(stream: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise OpenElisSqlError("The laboratory database closed the connection.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _message(stream: socket.socket) -> tuple[bytes, bytes]:
    header = _read_exact(stream, 5)
    length = struct.unpack("!I", header[1:5])[0]
    return header[:1], _read_exact(stream, length - 4)


def _startup(user: str, database: str) -> bytes:
    params = f"user\0{user}\0database\0{database}\0\0".encode("utf-8")
    body = struct.pack("!I", 196608) + params
    return struct.pack("!I", len(body) + 4) + body


def _query(sql: str) -> list[list[str | None]]:
    secret = password()
    if not secret:
        raise OpenElisSqlError("Laboratory database is not configured.")
    stream = socket.create_connection((HOST, PORT), timeout=8)
    try:
        stream.sendall(_startup(USER, DATABASE))
        kind, payload = _message(stream)
        if kind != b"R":
            raise OpenElisSqlError("The laboratory database rejected the connection.")
        code = struct.unpack("!I", payload[:4])[0]
        if code == 5:
            salt = payload[4:8]
            token = _md5_password(USER, secret, salt)
            stream.sendall(b"p" + struct.pack("!I", len(token) + 4) + token)
            kind, payload = _message(stream)
            if kind != b"R" or struct.unpack("!I", payload[:4])[0] != 0:
                raise OpenElisSqlError("The laboratory database rejected the connection.")
        elif code != 0:
            raise OpenElisSqlError("The laboratory database rejected the connection.")
        while kind != b"Z":
            kind, payload = _message(stream)
        encoded = sql.encode("utf-8") + b"\0"
        stream.sendall(b"Q" + struct.pack("!I", len(encoded) + 4) + encoded)
        rows: list[list[str | None]] = []
        while True:
            kind, payload = _message(stream)
            if kind == b"D":
                count = struct.unpack("!H", payload[:2])[0]
                offset = 2
                row: list[str | None] = []
                for _ in range(count):
                    size = struct.unpack("!i", payload[offset : offset + 4])[0]
                    offset += 4
                    if size < 0:
                        row.append(None)
                        continue
                    row.append(payload[offset : offset + size].decode("utf-8", "replace"))
                    offset += size
                rows.append(row)
            elif kind == b"E":
                text = payload.decode("utf-8", "replace")
                message = ""
                parts = text.split("\0")
                for index in range(0, len(parts) - 1, 2):
                    if parts[index] in {"M", "S"}:
                        message = parts[index + 1]
                raise OpenElisSqlError(message or "The laboratory database could not be updated.")
            elif kind == b"Z":
                return rows
    finally:
        stream.close()


def _uuid(value: str) -> str:
    text = str(value or "").strip()
    if not _UUID.match(text):
        raise OpenElisSqlError("The visit could not be matched in the laboratory.")
    return text


def _accession(value: str) -> str:
    text = str(value or "").strip()
    if not _ACCESSION.match(text):
        raise OpenElisSqlError("The laboratory accession is not valid.")
    return text


def _sql_text(value: str) -> str:
    return " ".join(str(value or "").split())[:200].replace("'", "''")


def _plain_name(value: str) -> str:
    return " ".join(html.unescape(str(value or "")).replace("&amp;", "&").split())


# Order names whose parameter list is stored under a different panel name.
PANEL_EQUIVALENTS = {
    "liver function test (lft)": "Liver function tests",
}

# Order names with no stored panel. Parameters are the individual tests that make up that order.
COMPOSED_PARAMETERS = {
    "e/u/cr": [
        "Serum sodium",
        "Serum potassium",
        "Serum chloride",
        "Serum carbon dioxide",
        "Blood urea nitrogen",
        "Serum creatinine (umol/L)",
    ],
    "hbsag serology panel": [
        "HBsAg Rapid Diagnostic Test",
        "Hepatitis B Surface Antigen Test",
        "Hepatitis B surface antigen spot test",
        "Hepatitis B virus e antigen assay",
        "Hepatitis B core antibody test",
        "Hepatitis B DNA quantitative (IU/mL)",
    ],
    "malaria parasite (rdt)": ["Rapid test for malaria"],
    "malaria parasite": ["Rapid test for malaria"],
    "malaria rdt": ["Rapid test for malaria"],
    "malaria": ["Rapid test for malaria"],
}


def equivalent_parameters(name: str) -> tuple[str, list[str]]:
    """Panel name to expand, or the individual tests that stand in for this order."""
    key = _plain_name(name).casefold()
    panel = PANEL_EQUIVALENTS.get(key, "")
    parts = list(COMPOSED_PARAMETERS.get(key, []))
    return panel, parts


def test_names_by_id(test_ids: list[str]) -> dict[str, str]:
    """Test names for numeric laboratory test ids."""
    ids: list[str] = []
    for item in test_ids:
        text = str(item or "").strip()
        if text.isdigit() and text not in ids:
            ids.append(text)
    if not ids:
        return {}
    try:
        rows = _query(f"SELECT id::text, name FROM test WHERE id IN ({', '.join(ids)})")
    except OpenElisSqlError:
        return {}
    return {str(row[0] or ""): str(row[1] or "") for row in rows if row and row[0]}


def parameters_for_names(names: list[str]) -> dict[str, list[dict[str, str]]]:
    """Parameters on each test: panel members, or the test itself, with the unit when one is set.

    Reference ranges are not stored on these tests, so this does not return them.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in names:
        text = " ".join(str(name or "").split())
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        cleaned.append(text)
    if not cleaned:
        return {}
    lookup = list(cleaned)
    seen_lookup = {name.casefold() for name in lookup}
    for name in cleaned:
        panel, parts = equivalent_parameters(name)
        for extra in [panel, *parts]:
            if extra and extra.casefold() not in seen_lookup:
                seen_lookup.add(extra.casefold())
                lookup.append(extra)
    literals = ", ".join(f"'{_sql_text(_plain_name(name)).lower()}'" for name in lookup)
    name_sql = "lower(replace(replace({column}, '&amp;', '&'), '&#38;', '&'))"
    try:
        panel_rows = _query(
            "SELECT lower(replace(replace(p.name, '&amp;', '&'), '&#38;', '&')), t.id::text, t.name, COALESCE(u.name, '') "
            "FROM panel p "
            "JOIN panel_item pi ON pi.panel_id = p.id "
            "JOIN test t ON t.id = pi.test_id "
            "LEFT JOIN unit_of_measure u ON u.id = t.uom_id "
            f"WHERE {name_sql.format(column='p.name')} IN ({literals}) "
            "ORDER BY 1, pi.sort_order, t.name"
        )
        test_rows = _query(
            "SELECT lower(replace(replace(t.name, '&amp;', '&'), '&#38;', '&')), t.id::text, t.name, COALESCE(u.name, '') "
            "FROM test t "
            "LEFT JOIN unit_of_measure u ON u.id = t.uom_id "
            f"WHERE t.is_active = 'Y' AND {name_sql.format(column='t.name')} IN ({literals})"
        )
    except OpenElisSqlError:
        return {}
    panels: dict[str, list[dict[str, str]]] = {}
    for row in panel_rows:
        key = str(row[0] or "").casefold()
        panels.setdefault(key, []).append(
            {
                "testId": str(row[1] or ""),
                "name": _plain_name(str(row[2] or "")),
                "unit": str(row[3] or ""),
            }
        )
    singles: dict[str, dict[str, str]] = {}
    for row in test_rows:
        key = str(row[0] or "").casefold()
        singles[key] = {
            "testId": str(row[1] or ""),
            "name": _plain_name(str(row[2] or "")),
            "unit": str(row[3] or ""),
        }
    found: dict[str, list[dict[str, str]]] = {}
    for name in cleaned:
        key = _plain_name(name).casefold()
        panel_name, parts = equivalent_parameters(name)
        if panel_name and panels.get(panel_name.casefold()):
            found[key] = panels[panel_name.casefold()]
            continue
        if parts:
            rows = [singles[part.casefold()] for part in parts if part.casefold() in singles]
            if rows:
                found[key] = rows
            continue
        if panels.get(key):
            found[key] = panels[key]
        elif key in singles:
            found[key] = [singles[key]]
    _attach_result_choices(found)
    return found


def _attach_result_choices(found: dict[str, list[dict[str, Any]]]) -> None:
    """A positive/negative test keeps its choices. A number keeps its unit."""
    ids: list[str] = []
    seen: set[str] = set()
    for rows in found.values():
        for row in rows:
            test_id = str(row.get("testId") or "")
            if test_id.isdigit() and test_id not in seen:
                seen.add(test_id)
                ids.append(test_id)
    if not ids:
        return
    try:
        rows = _query(
            "SELECT tr.test_id::text, tr.tst_rslt_type, COALESCE(tr.value, ''), COALESCE(d.dict_entry, '') "
            "FROM test_result tr "
            "LEFT JOIN dictionary d ON tr.tst_rslt_type = 'D' AND d.id::text = tr.value "
            f"WHERE tr.test_id IN ({', '.join(ids)}) AND tr.is_active = 'Y' "
            "ORDER BY tr.test_id, tr.sort_order, tr.id"
        )
    except OpenElisSqlError:
        return
    by_test: dict[str, dict[str, Any]] = {}
    for test_id, result_type, value, label in rows:
        slot = by_test.setdefault(
            str(test_id or ""),
            {"resultType": str(result_type or ""), "options": []},
        )
        if result_type and not slot["resultType"]:
            slot["resultType"] = str(result_type)
        choice = _plain_name(str(label or ""))
        if str(result_type or "") == "D" and choice:
            slot["options"].append({"value": str(value or ""), "label": choice})
    for rows in found.values():
        for row in rows:
            slot = by_test.get(str(row.get("testId") or ""))
            if not slot:
                continue
            row["resultType"] = str(slot.get("resultType") or "")
            row["options"] = list(slot.get("options") or [])


def samples_for_encounter(encounter_uuid: str) -> list[dict[str, str]]:
    """Samples already created for this visit, with the tests on each one."""
    try:
        visit = _uuid(encounter_uuid)
        rows = _query(
            "SELECT s.id::text, COALESCE(s.accession_number, '') "
            "FROM sample s "
            f"WHERE s.uuid = '{visit}' "
            "ORDER BY s.id"
        )
    except OpenElisSqlError:
        return []
    found = []
    for row in rows:
        found.append(
            {
                "id": str(row[0] or ""),
                "accession": str(row[1] or ""),
                "tests": "",
            }
        )
    return found


def assign_accession(sample_id: str, accession: str) -> None:
    number = _accession(accession)
    if not str(sample_id).isdigit():
        raise OpenElisSqlError("The laboratory sample could not be updated.")
    _query(
        "UPDATE sample SET accession_number = "
        f"'{number}', lastupdated = NOW() "
        f"WHERE id = {int(sample_id)} AND (accession_number IS NULL OR accession_number = '')"
    )


def ensure_analyses(accession: str, test_ids: list[str]) -> None:
    """Put ordered tests on the sample that already has this accession.

    Collecting can reuse a visit sample before the test is attached. Result
    entry then has nothing to save.
    """
    number = _accession(accession)
    wanted = []
    seen: set[str] = set()
    for item in test_ids:
        text = str(item or "").strip()
        if text.isdigit() and text not in seen:
            seen.add(text)
            wanted.append(text)
    if not wanted:
        return
    samples = _query(
        "SELECT id::text FROM sample "
        f"WHERE accession_number = '{number}' ORDER BY id LIMIT 1"
    )
    if not samples or not samples[0][0]:
        return
    sample_id = int(samples[0][0])
    items = _query(
        "SELECT id::text FROM sample_item "
        f"WHERE sample_id = {sample_id} ORDER BY id LIMIT 1"
    )
    if not items or not items[0][0]:
        return
    sample_item_id = int(items[0][0])
    status_rows = _query(
        "SELECT id::text FROM status_of_sample "
        "WHERE status_type = 'ANALYSIS' "
        "AND name IN ('Not Tested', 'Not Started') "
        "ORDER BY id LIMIT 1"
    )
    status_id = int(status_rows[0][0]) if status_rows and status_rows[0][0] else 1
    existing = _query(
        "SELECT test_id::text FROM analysis "
        f"WHERE sample_item_id = {sample_item_id}"
    )
    present = {str(row[0] or "") for row in existing}
    for test_id in wanted:
        if test_id in present:
            continue
        _query(
            "INSERT INTO analysis "
            "(id, sample_item_id, test_id, revision, status_id, analysis_type_id, is_reportable, lastupdated) "
            "VALUES ("
            f"nextval('analysis_seq'), {sample_item_id}, {int(test_id)}, '0', {status_id}, 1, 'Y', NOW())"
        )
        present.add(test_id)


def attach_accession_to_encounter(accession: str, encounter_uuid: str) -> None:
    """Point a newly collected sample at the visit, when the visit has no sample yet."""
    number = _accession(accession)
    visit = _uuid(encounter_uuid)
    _query(
        "UPDATE sample SET uuid = "
        f"'{visit}', lastupdated = NOW() "
        f"WHERE accession_number = '{number}' AND (uuid IS NULL OR uuid = '')"
    )
