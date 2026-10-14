"""Laboratory reference ranges.

The catalogue lives with Hospital EMR because scientists review and approve it here.
Result entry then posts the chosen limits with the result. OpenELIS keeps the
result. Analyser limits are not copied in, and a draft is never used on a result.

Age is the completed age on the date the test was ordered. A missing birth date
or order date does not fall back to an adult interval. A male interval is never
used for a female patient, and a different unit is never substituted.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = os.environ.get("ABIKAN_LAB_RANGES_DB", "/var/lib/abikan/lab-reference-ranges.sqlite3")
LOCK = threading.Lock()
SEED_VERSION = "2026-10-12-1"

NO_RANGE = "No approved reference range."
AMBIGUOUS = "More than one approved range matches this patient. None was applied."
UNIT_NOTE = "No approved range uses this unit."

STATUSES = {"draft", "pending_review", "approved", "inactive"}
SEXES = {"male", "female", "any"}
AGE_UNITS = {"", "days", "weeks", "months", "years"}


def test_key(name: str) -> str:
    return " ".join(str(name or "").casefold().split())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(connection)
    _import_legacy(connection)
    _import_seed(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS lab_reference_range (
            id TEXT PRIMARY KEY,
            test_key TEXT NOT NULL,
            test_name TEXT NOT NULL,
            aliases TEXT NOT NULL DEFAULT '[]',
            specimen TEXT NOT NULL DEFAULT '',
            result_type TEXT NOT NULL DEFAULT 'numeric',
            purpose TEXT NOT NULL DEFAULT 'reference_interval',
            low_value TEXT NOT NULL DEFAULT '',
            high_value TEXT NOT NULL DEFAULT '',
            low_inclusive INTEGER NOT NULL DEFAULT 1,
            high_inclusive INTEGER NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT '',
            age_min_value INTEGER,
            age_min_unit TEXT NOT NULL DEFAULT '',
            age_min_inclusive INTEGER NOT NULL DEFAULT 1,
            age_max_value INTEGER,
            age_max_unit TEXT NOT NULL DEFAULT '',
            age_max_inclusive INTEGER NOT NULL DEFAULT 1,
            age_text TEXT NOT NULL DEFAULT '',
            sex TEXT NOT NULL DEFAULT 'any',
            condition TEXT NOT NULL DEFAULT '',
            method TEXT NOT NULL DEFAULT '',
            expected_values TEXT NOT NULL DEFAULT '[]',
            descriptive_text TEXT NOT NULL DEFAULT '',
            source_title TEXT NOT NULL DEFAULT '',
            source_publisher TEXT NOT NULL DEFAULT '',
            source_version TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            source_accessed TEXT NOT NULL DEFAULT '',
            limitations TEXT NOT NULL DEFAULT '',
            conflict_group TEXT NOT NULL DEFAULT '',
            conflict_note TEXT NOT NULL DEFAULT '',
            effective_from TEXT NOT NULL DEFAULT '',
            effective_to TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            modified_by TEXT NOT NULL DEFAULT '',
            modified_at TEXT NOT NULL DEFAULT '',
            reviewed_by TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT NOT NULL DEFAULT '',
            approved_by TEXT NOT NULL DEFAULT '',
            approved_at TEXT NOT NULL DEFAULT '',
            supersedes_id TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS lab_reference_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            range_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            at TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS lab_reference_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS lab_reference_range_test ON lab_reference_range (test_key, status);
        """
    )


def _audit(connection: sqlite3.Connection, range_id: str, action: str, actor: str, detail: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO lab_reference_audit (range_id, action, actor, at, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (range_id, action, actor, _now(), json.dumps(detail, sort_keys=True)),
    )


def _import_legacy(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lab_reference_ranges'"
    ).fetchone()
    if not existing:
        return
    rows = connection.execute(
        "SELECT test_key, test_name, low, high, updated_by, updated_at FROM lab_reference_ranges"
    ).fetchall()
    for row in rows:
        key = str(row["test_key"] or "")
        range_id = f"legacy:{key}"
        if connection.execute("SELECT 1 FROM lab_reference_range WHERE id = ?", (range_id,)).fetchone():
            continue
        when = str(row["updated_at"] or _now())
        actor = str(row["updated_by"] or "")
        connection.execute(
            """
            INSERT INTO lab_reference_range (
                id, test_key, test_name, low_value, high_value, status,
                limitations, source_title, created_by, created_at, modified_by, modified_at
            ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)
            """,
            (
                range_id,
                key,
                str(row["test_name"] or ""),
                str(row["low"] or ""),
                str(row["high"] or ""),
                "Previously saved in Hospital EMR without a cited source. It is not used until a scientist approves a sourced range.",
                "Previously saved without a cited source",
                actor,
                when,
                actor,
                when,
            ),
        )
        _audit(
            connection,
            range_id,
            "imported_unsourced",
            actor or "Catalogue import",
            {"low": str(row["low"] or ""), "high": str(row["high"] or ""), "status": "draft"},
        )
    connection.commit()


def _import_seed(connection: sqlite3.Connection) -> None:
    current = connection.execute("SELECT value FROM lab_reference_meta WHERE key = 'seed'").fetchone()
    if current and str(current["value"]) == SEED_VERSION:
        return
    from lab_reference_seed import proposed_rows

    when = _now()
    for row in proposed_rows():
        if connection.execute("SELECT 1 FROM lab_reference_range WHERE id = ?", (row["id"],)).fetchone():
            continue
        _insert_row(connection, row, actor="Catalogue import", when=when, status="draft")
        _audit(
            connection,
            row["id"],
            "proposed",
            "Catalogue import",
            {"status": "draft", "low": row["low"], "high": row["high"], "source": row["source_title"]},
        )
    connection.execute(
        """
        INSERT INTO lab_reference_meta (key, value) VALUES ('seed', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (SEED_VERSION,),
    )
    connection.commit()


def _insert_row(connection: sqlite3.Connection, row: dict[str, Any], *, actor: str, when: str, status: str) -> None:
    connection.execute(
        """
        INSERT INTO lab_reference_range (
            id, test_key, test_name, aliases, specimen, result_type, purpose,
            low_value, high_value, low_inclusive, high_inclusive, unit,
            age_min_value, age_min_unit, age_min_inclusive,
            age_max_value, age_max_unit, age_max_inclusive, age_text,
            sex, condition, method, expected_values, descriptive_text,
            source_title, source_publisher, source_version, source_url, source_accessed,
            limitations, conflict_group, conflict_note,
            effective_from, effective_to, status,
            created_by, created_at, modified_by, modified_at, supersedes_id
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        (
            row["id"],
            test_key(str(row["test_name"])),
            row["test_name"],
            json.dumps(row.get("aliases") or []),
            row.get("specimen") or "",
            row.get("result_type") or "numeric",
            row.get("purpose") or "reference_interval",
            row.get("low") or "",
            row.get("high") or "",
            1 if row.get("low_inclusive", True) else 0,
            1 if row.get("high_inclusive", True) else 0,
            row.get("unit") or "",
            row.get("age_min_value"),
            row.get("age_min_unit") or "",
            1 if row.get("age_min_inclusive", True) else 0,
            row.get("age_max_value"),
            row.get("age_max_unit") or "",
            1 if row.get("age_max_inclusive", True) else 0,
            row.get("age_text") or "",
            row.get("sex") or "any",
            row.get("condition") or "",
            row.get("method") or "",
            json.dumps(row.get("expected_values") or []),
            row.get("descriptive_text") or "",
            row.get("source_title") or "",
            row.get("source_publisher") or "",
            row.get("source_version") or "",
            row.get("source_url") or "",
            row.get("source_accessed") or "",
            row.get("limitations") or "",
            row.get("conflict_group") or "",
            row.get("conflict_note") or "",
            row.get("effective_from") or "",
            row.get("effective_to") or "",
            status,
            actor,
            when,
            actor,
            when,
            row.get("supersedes_id") or "",
        ),
    )


def _load(connection: sqlite3.Connection, range_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM lab_reference_range WHERE id = ?", (range_id,)).fetchone()
    if not row:
        raise ValueError("That reference range was not found.")
    return row


def _history(connection: sqlite3.Connection, range_id: str) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT action, actor, at FROM lab_reference_audit
        WHERE range_id = ? ORDER BY id DESC LIMIT 12
        """,
        (range_id,),
    ).fetchall()
    return [{"action": str(row["action"]), "actor": str(row["actor"]), "at": str(row["at"])} for row in rows]


def _public(row: sqlite3.Row, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    low = str(row["low_value"] or "")
    high = str(row["high_value"] or "")
    expected = json.loads(row["expected_values"] or "[]")
    aliases = json.loads(row["aliases"] or "[]")
    return {
        "id": str(row["id"]),
        "testName": str(row["test_name"] or ""),
        "aliases": aliases if isinstance(aliases, list) else [],
        "specimen": str(row["specimen"] or ""),
        "resultType": str(row["result_type"] or ""),
        "purpose": str(row["purpose"] or ""),
        "low": low,
        "high": high,
        "lowInclusive": bool(row["low_inclusive"]),
        "highInclusive": bool(row["high_inclusive"]),
        "unit": str(row["unit"] or ""),
        "rangeText": _range_text(low, high, bool(row["low_inclusive"]), bool(row["high_inclusive"])),
        "ageText": str(row["age_text"] or ""),
        "ageMin": "" if row["age_min_value"] is None else str(row["age_min_value"]),
        "ageMinUnit": str(row["age_min_unit"] or ""),
        "ageMinInclusive": bool(row["age_min_inclusive"]),
        "ageMax": "" if row["age_max_value"] is None else str(row["age_max_value"]),
        "ageMaxUnit": str(row["age_max_unit"] or ""),
        "ageMaxInclusive": bool(row["age_max_inclusive"]),
        "sex": str(row["sex"] or "any"),
        "condition": str(row["condition"] or ""),
        "appliesTo": _applies_to(row),
        "method": str(row["method"] or ""),
        "expectedValues": expected if isinstance(expected, list) else [],
        "descriptiveText": str(row["descriptive_text"] or ""),
        "sourceTitle": str(row["source_title"] or ""),
        "sourcePublisher": str(row["source_publisher"] or ""),
        "sourceVersion": str(row["source_version"] or ""),
        "sourceUrl": str(row["source_url"] or ""),
        "sourceAccessed": str(row["source_accessed"] or ""),
        "limitations": str(row["limitations"] or ""),
        "conflictGroup": str(row["conflict_group"] or ""),
        "conflictNote": str(row["conflict_note"] or ""),
        "effectiveFrom": str(row["effective_from"] or ""),
        "effectiveTo": str(row["effective_to"] or ""),
        "status": str(row["status"] or ""),
        "statusLabel": _status_label(str(row["status"] or "")),
        "createdBy": str(row["created_by"] or ""),
        "createdAt": str(row["created_at"] or ""),
        "modifiedBy": str(row["modified_by"] or ""),
        "modifiedAt": str(row["modified_at"] or ""),
        "reviewedBy": str(row["reviewed_by"] or ""),
        "reviewedAt": str(row["reviewed_at"] or ""),
        "approvedBy": str(row["approved_by"] or ""),
        "approvedAt": str(row["approved_at"] or ""),
        "supersedesId": str(row["supersedes_id"] or ""),
        "history": history or [],
        "usedOnResults": str(row["status"] or "") == "approved" and str(row["purpose"] or "") == "reference_interval",
    }


def _status_label(status: str) -> str:
    return {
        "draft": "Draft",
        "pending_review": "Pending review",
        "approved": "Approved",
        "inactive": "Inactive",
    }.get(status, status)


def _applies_to(row: sqlite3.Row) -> str:
    sex = {"male": "Male", "female": "Female", "any": "Any sex"}.get(str(row["sex"] or ""), "Any sex")
    parts = [sex]
    if str(row["age_text"] or "").strip():
        parts.append(str(row["age_text"]).strip())
    if str(row["specimen"] or "").strip():
        parts.append(str(row["specimen"]).strip())
    condition = str(row["condition"] or "").replace("_", " ").strip()
    if condition:
        parts.append(condition)
    return ", ".join(parts)


def _range_text(low: str, high: str, low_inclusive: bool, high_inclusive: bool) -> str:
    low = str(low or "").strip()
    high = str(high or "").strip()
    if low and high:
        return f"{low}–{high}"
    if low:
        return f"{low} or higher" if low_inclusive else f"above {low}"
    if high:
        return f"below {high}" if not high_inclusive else f"{high} or lower"
    return ""


def list_ranges(query: str = "", status: str = "") -> list[dict[str, Any]]:
    needle = test_key(query)
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM lab_reference_range
                ORDER BY test_name COLLATE NOCASE, sex, age_text
                """
            ).fetchall()
            history_rows = connection.execute(
                "SELECT range_id, action, actor, at FROM lab_reference_audit ORDER BY id DESC"
            ).fetchall()
        finally:
            connection.close()
    history: dict[str, list[dict[str, str]]] = {}
    for item in history_rows:
        bucket = history.setdefault(str(item["range_id"]), [])
        if len(bucket) < 8:
            bucket.append({"action": str(item["action"]), "actor": str(item["actor"]), "at": str(item["at"])})
    listed = []
    for row in rows:
        if status and str(row["status"]) != status:
            continue
        if needle:
            haystack = " ".join(
                [
                    test_key(str(row["test_name"] or "")),
                    test_key(str(row["aliases"] or "")),
                    test_key(str(row["source_title"] or "")),
                ]
            )
            if needle not in haystack:
                continue
        listed.append(_public(row, history.get(str(row["id"]), [])))
    return listed


def _clean_sex(value: str) -> str:
    text = str(value or "any").strip().casefold()
    if text in {"m", "male"}:
        return "male"
    if text in {"f", "female"}:
        return "female"
    if text in {"", "any", "all", "u", "o", "unknown"}:
        return "any"
    raise ValueError("Choose male, female, or any sex.")


def _optional_int(value: Any, label: str) -> int | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError as error:
        raise ValueError(f"Enter a whole number for {label}.") from error
    if number < 0:
        raise ValueError(f"Enter a whole number for {label}.")
    return number


def _apply_edits(connection: sqlite3.Connection, row: sqlite3.Row, body: dict[str, Any], actor: str) -> None:
    status = str(row["status"] or "")
    if status == "inactive":
        raise ValueError("This range is inactive. Revise the current range instead.")
    low = str(body.get("low") if "low" in body else row["low_value"]).strip()
    high = str(body.get("high") if "high" in body else row["high_value"]).strip()
    _check_limits(low, high)
    sex = _clean_sex(body.get("sex") if "sex" in body else row["sex"])
    unit = str(body.get("unit") if "unit" in body else row["unit"]).strip()
    specimen = str(body.get("specimen") if "specimen" in body else row["specimen"]).strip()
    method = str(body.get("method") if "method" in body else row["method"]).strip()
    limitations = str(body.get("limitations") if "limitations" in body else row["limitations"]).strip()
    source_title = str(body.get("sourceTitle") if "sourceTitle" in body else row["source_title"]).strip()
    source_publisher = str(body.get("sourcePublisher") if "sourcePublisher" in body else row["source_publisher"]).strip()
    source_version = str(body.get("sourceVersion") if "sourceVersion" in body else row["source_version"]).strip()
    source_url = str(body.get("sourceUrl") if "sourceUrl" in body else row["source_url"]).strip()
    age_min = _optional_int(body.get("ageMin") if "ageMin" in body else row["age_min_value"], "the minimum age")
    age_max = _optional_int(body.get("ageMax") if "ageMax" in body else row["age_max_value"], "the maximum age")
    age_min_unit = str(body.get("ageMinUnit") if "ageMinUnit" in body else row["age_min_unit"] or "").strip().casefold()
    age_max_unit = str(body.get("ageMaxUnit") if "ageMaxUnit" in body else row["age_max_unit"] or "").strip().casefold()
    if age_min_unit not in AGE_UNITS or age_max_unit not in AGE_UNITS:
        raise ValueError("Age uses days, weeks, months, or years.")
    if age_min is not None and not age_min_unit:
        raise ValueError("Choose the unit for the minimum age.")
    if age_max is not None and not age_max_unit:
        raise ValueError("Choose the unit for the maximum age.")
    age_text = str(row["age_text"] or "")
    if "ageMin" in body or "ageMax" in body or "ageMinUnit" in body or "ageMaxUnit" in body:
        age_text = _edited_age_text(age_min, age_min_unit, age_max, age_max_unit)
    when = _now()
    next_status = "approved" if status == "approved" else "draft"
    reviewed_by = str(row["reviewed_by"] or "") if next_status == "approved" else ""
    reviewed_at = str(row["reviewed_at"] or "") if next_status == "approved" else ""
    connection.execute(
        """
        UPDATE lab_reference_range SET
            low_value = ?, high_value = ?, unit = ?, sex = ?, specimen = ?, method = ?,
            limitations = ?, source_title = ?, source_publisher = ?, source_version = ?, source_url = ?,
            age_min_value = ?, age_min_unit = ?, age_max_value = ?, age_max_unit = ?, age_text = ?,
            status = ?, modified_by = ?, modified_at = ?,
            reviewed_by = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (
            low,
            high,
            unit,
            sex,
            specimen,
            method,
            limitations,
            source_title,
            source_publisher,
            source_version,
            source_url,
            age_min,
            age_min_unit,
            age_max,
            age_max_unit,
            age_text,
            next_status,
            actor,
            when,
            reviewed_by,
            reviewed_at,
            row["id"],
        ),
    )
    _audit(connection, str(row["id"]), "edited", actor, {"low": low, "high": high, "status": next_status})


def _edited_age_text(age_min: int | None, age_min_unit: str, age_max: int | None, age_max_unit: str) -> str:
    if age_min is None and age_max is None:
        return ""
    if age_min is not None and age_max is not None and age_min_unit == age_max_unit:
        return f"{age_min}-{age_max} {age_max_unit}"
    parts = []
    if age_min is not None:
        parts.append(f"from {age_min} {age_min_unit}")
    if age_max is not None:
        parts.append(f"to {age_max} {age_max_unit}")
    return " ".join(parts)


def _check_limits(low: str, high: str) -> None:
    low_number = _number(low)
    high_number = _number(high)
    if low and low_number is None:
        raise ValueError("The low limit must be a number.")
    if high and high_number is None:
        raise ValueError("The high limit must be a number.")
    if low_number is not None and high_number is not None and low_number > high_number:
        raise ValueError("The low limit cannot be above the high limit.")


def apply_action(body: dict[str, Any], actor: str) -> dict[str, Any]:
    action = str(body.get("action") or "save").strip().casefold()
    name = actor.strip() or "Laboratory"
    with LOCK:
        connection = _connect()
        try:
            if action == "save" and not str(body.get("id") or "").strip():
                saved = _create(connection, body, name)
            else:
                row = _load(connection, str(body.get("id") or "").strip())
                if action == "save":
                    _apply_edits(connection, row, body, name)
                    saved = str(row["id"])
                elif action == "submit":
                    saved = _transition(connection, row, name, "pending_review", {"draft"})
                elif action == "approve":
                    saved = _approve(connection, row, name)
                elif action == "inactivate":
                    saved = _transition(connection, row, name, "inactive", {"approved", "pending_review", "draft"})
                elif action == "revise":
                    saved = _revise(connection, row, name)
                else:
                    raise ValueError("Choose save, submit, approve, inactivate, or revise.")
            connection.commit()
            fresh = _load(connection, saved)
            history = _history(connection, saved)
        finally:
            connection.close()
    return _public(fresh, history)


def _create(connection: sqlite3.Connection, body: dict[str, Any], actor: str) -> str:
    test_name = " ".join(str(body.get("testName") or "").split())
    if len(test_name) < 2:
        raise ValueError("Choose the test this range is for.")
    low = str(body.get("low") or "").strip()
    high = str(body.get("high") or "").strip()
    _check_limits(low, high)
    range_id = uuid.uuid4().hex
    when = _now()
    row = {
        "id": range_id,
        "test_name": test_name,
        "aliases": [],
        "specimen": str(body.get("specimen") or "").strip(),
        "result_type": "categorical" if str(body.get("resultType") or "") == "categorical" else "numeric",
        "purpose": "reference_interval",
        "low": low,
        "high": high,
        "low_inclusive": True,
        "high_inclusive": True,
        "unit": str(body.get("unit") or "").strip(),
        "age_min_value": _optional_int(body.get("ageMin"), "the minimum age"),
        "age_min_unit": str(body.get("ageMinUnit") or "").strip().casefold(),
        "age_min_inclusive": True,
        "age_max_value": _optional_int(body.get("ageMax"), "the maximum age"),
        "age_max_unit": str(body.get("ageMaxUnit") or "").strip().casefold(),
        "age_max_inclusive": True,
        "age_text": "",
        "sex": _clean_sex(str(body.get("sex") or "any")),
        "condition": "",
        "method": str(body.get("method") or "").strip(),
        "expected_values": [],
        "descriptive_text": "",
        "source_title": str(body.get("sourceTitle") or "").strip(),
        "source_publisher": str(body.get("sourcePublisher") or "").strip(),
        "source_version": str(body.get("sourceVersion") or "").strip(),
        "source_url": str(body.get("sourceUrl") or "").strip(),
        "source_accessed": "",
        "limitations": str(body.get("limitations") or "").strip()
        or "Entered by laboratory staff. No independent source was cited yet.",
        "conflict_group": "",
        "conflict_note": "",
        "supersedes_id": "",
    }
    row["age_text"] = _edited_age_text(
        row["age_min_value"], row["age_min_unit"], row["age_max_value"], row["age_max_unit"]
    )
    if row["age_min_unit"] not in AGE_UNITS or row["age_max_unit"] not in AGE_UNITS:
        raise ValueError("Age uses days, weeks, months, or years.")
    _insert_row(connection, row, actor=actor, when=when, status="draft")
    _audit(connection, range_id, "created", actor, {"low": low, "high": high, "status": "draft"})
    return range_id


def _transition(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    actor: str,
    status: str,
    allowed_from: set[str],
) -> str:
    current = str(row["status"] or "")
    if current not in allowed_from:
        raise ValueError("That reference range cannot be moved from its current state.")
    when = _now()
    reviewed_by = actor if status == "pending_review" else str(row["reviewed_by"] or "")
    reviewed_at = when if status == "pending_review" else str(row["reviewed_at"] or "")
    connection.execute(
        """
        UPDATE lab_reference_range
        SET status = ?, modified_by = ?, modified_at = ?, reviewed_by = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (status, actor, when, reviewed_by, reviewed_at, row["id"]),
    )
    _audit(connection, str(row["id"]), status, actor, {"status": status})
    return str(row["id"])


def _approve(connection: sqlite3.Connection, row: sqlite3.Row, actor: str) -> str:
    if str(row["status"] or "") not in {"draft", "pending_review"}:
        raise ValueError("Only a draft or a range pending review can be approved.")
    if str(row["purpose"] or "") != "reference_interval":
        raise ValueError("This cutoff is kept for background. It is not approved for the result sheet.")
    if str(row["conflict_note"] or "").strip() and str(row["purpose"] or "") == "reference_interval":
        pass
    if str(row["conflict_group"] or "").strip():
        raise ValueError("Sources disagree for this partition. Resolve the conflict before approval.")
    if not str(row["source_title"] or "").strip():
        raise ValueError("Add the source before approving this range.")
    result_type = str(row["result_type"] or "")
    low = str(row["low_value"] or "").strip()
    high = str(row["high_value"] or "").strip()
    expected = json.loads(row["expected_values"] or "[]")
    if result_type == "numeric" and not low and not high:
        raise ValueError("Enter a limit before approving this range.")
    if result_type == "categorical" and not expected and not str(row["descriptive_text"] or "").strip():
        raise ValueError("Enter the expected result before approving this range.")
    when = _now()
    connection.execute(
        """
        UPDATE lab_reference_range
        SET status = 'approved', approved_by = ?, approved_at = ?, modified_by = ?, modified_at = ?
        WHERE id = ?
        """,
        (actor, when, actor, when, row["id"]),
    )
    previous = str(row["supersedes_id"] or "").strip()
    if previous:
        connection.execute(
            """
            UPDATE lab_reference_range
            SET status = 'inactive', effective_to = ?, modified_by = ?, modified_at = ?
            WHERE id = ? AND status = 'approved'
            """,
            (when[:10], actor, when, previous),
        )
        _audit(connection, previous, "inactive", actor, {"replacedBy": str(row["id"])})
    _audit(connection, str(row["id"]), "approved", actor, {"status": "approved", "low": low, "high": high})
    return str(row["id"])


def _revise(connection: sqlite3.Connection, row: sqlite3.Row, actor: str) -> str:
    if str(row["status"] or "") != "approved":
        raise ValueError("Revise an approved range when the limits need to change.")
    range_id = uuid.uuid4().hex
    when = _now()
    clone = dict(row)
    clone["id"] = range_id
    clone["supersedes_id"] = str(row["id"])
    payload = {
        "id": range_id,
        "test_name": clone["test_name"],
        "aliases": json.loads(clone["aliases"] or "[]"),
        "specimen": clone["specimen"],
        "result_type": clone["result_type"],
        "purpose": clone["purpose"],
        "low": clone["low_value"],
        "high": clone["high_value"],
        "low_inclusive": bool(clone["low_inclusive"]),
        "high_inclusive": bool(clone["high_inclusive"]),
        "unit": clone["unit"],
        "age_min_value": clone["age_min_value"],
        "age_min_unit": clone["age_min_unit"],
        "age_min_inclusive": bool(clone["age_min_inclusive"]),
        "age_max_value": clone["age_max_value"],
        "age_max_unit": clone["age_max_unit"],
        "age_max_inclusive": bool(clone["age_max_inclusive"]),
        "age_text": clone["age_text"],
        "sex": clone["sex"],
        "condition": clone["condition"],
        "method": clone["method"],
        "expected_values": json.loads(clone["expected_values"] or "[]"),
        "descriptive_text": clone["descriptive_text"],
        "source_title": clone["source_title"],
        "source_publisher": clone["source_publisher"],
        "source_version": clone["source_version"],
        "source_url": clone["source_url"],
        "source_accessed": clone["source_accessed"],
        "limitations": clone["limitations"],
        "conflict_group": clone["conflict_group"],
        "conflict_note": clone["conflict_note"],
        "supersedes_id": str(row["id"]),
    }
    _insert_row(connection, payload, actor=actor, when=when, status="draft")
    _audit(connection, range_id, "revised", actor, {"supersedes": str(row["id"]), "status": "draft"})
    return range_id


def save_range(test_name: str, low: str, high: str, updated_by: str) -> dict[str, str]:
    """Keep a staff entry as a draft. It is not approved and is not used on results."""
    name = " ".join(str(test_name or "").split())
    key = test_key(name)
    if not key:
        raise ValueError("test name required")
    low_text = str(low or "").strip()
    high_text = str(high or "").strip()
    range_id = f"legacy:{key}"
    with LOCK:
        connection = _connect()
        try:
            if not low_text and not high_text:
                connection.execute("DELETE FROM lab_reference_range WHERE id = ?", (range_id,))
                connection.execute("DELETE FROM lab_reference_ranges WHERE test_key = ?", (key,))
                connection.commit()
                return {"testName": name, "low": "", "high": ""}
            when = _now()
            actor = str(updated_by or "").strip()
            _ensure_legacy_table(connection)
            connection.execute(
                """
                INSERT INTO lab_reference_ranges (test_key, test_name, low, high, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(test_key) DO UPDATE SET
                    test_name = excluded.test_name,
                    low = excluded.low,
                    high = excluded.high,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (key, name, low_text, high_text, actor, when),
            )
            if connection.execute("SELECT 1 FROM lab_reference_range WHERE id = ?", (range_id,)).fetchone():
                connection.execute(
                    """
                    UPDATE lab_reference_range
                    SET test_name = ?, low_value = ?, high_value = ?, status = 'draft',
                        modified_by = ?, modified_at = ?, approved_by = '', approved_at = ''
                    WHERE id = ?
                    """,
                    (name, low_text, high_text, actor, when, range_id),
                )
            else:
                _insert_row(
                    connection,
                    {
                        "id": range_id,
                        "test_name": name,
                        "aliases": [],
                        "low": low_text,
                        "high": high_text,
                        "limitations": "Entered by laboratory staff. No independent source was cited yet.",
                        "source_title": "",
                    },
                    actor=actor,
                    when=when,
                    status="draft",
                )
            _audit(connection, range_id, "edited", actor, {"low": low_text, "high": high_text, "status": "draft"})
            connection.commit()
        finally:
            connection.close()
    return {"testName": name, "low": low_text, "high": high_text}


def _ensure_legacy_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_reference_ranges (
            test_key TEXT PRIMARY KEY,
            test_name TEXT NOT NULL,
            low TEXT NOT NULL,
            high TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ranges_for(names: list[str]) -> dict[str, dict[str, str]]:
    keys = [test_key(name) for name in names if test_key(name)]
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                f"""
                SELECT test_key, test_name, low_value, high_value
                FROM lab_reference_range
                WHERE test_key IN ({placeholders}) AND status != 'inactive'
                ORDER BY modified_at DESC
                """,
                tuple(keys),
            ).fetchall()
        finally:
            connection.close()
    found: dict[str, dict[str, str]] = {}
    for row in rows:
        key = str(row["test_key"])
        if key in found:
            continue
        found[key] = {
            "testName": str(row["test_name"] or ""),
            "low": str(row["low_value"] or ""),
            "high": str(row["high_value"] or ""),
        }
    return found


def _number(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def apply_result_flag(item: dict[str, Any]) -> None:
    """Mark a numeric result Low or High from the limits already on that result."""
    if str(item.get("flag") or "").strip().upper() == "C":
        return
    options = item.get("options")
    if isinstance(options, list) and options:
        return
    low = _number(item.get("referenceLow"))
    high = _number(item.get("referenceHigh"))
    value = _number(item.get("resultValue") or item.get("qualifiedResultValue"))
    if value is None or (low is None and high is None):
        return
    low_inclusive = item.get("referenceLowInclusive", True) is not False
    high_inclusive = item.get("referenceHighInclusive", True) is not False
    if low is not None and (value < low if low_inclusive else value <= low):
        item["flag"] = "L"
    elif high is not None and (value > high if high_inclusive else value >= high):
        item["flag"] = "H"
    elif str(item.get("flag") or "").strip().upper() in {"", "L", "H"}:
        item["flag"] = ""


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    head = text[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(head if fmt == "%Y-%m-%d" else text[:10], fmt).date()
        except ValueError:
            continue
    if len(text) >= 10 and text[2] == "/" and text[5] == "/":
        try:
            return datetime.strptime(text[:10], "%d/%m/%Y").date()
        except ValueError:
            return None
    return None


def _completed(birth: date, on: date, unit: str) -> int | None:
    if birth > on:
        return None
    if unit == "days":
        return (on - birth).days
    if unit == "weeks":
        return (on - birth).days // 7
    if unit == "months":
        months = (on.year - birth.year) * 12 + on.month - birth.month
        if on.day < birth.day:
            months -= 1
        return months
    if unit == "years":
        return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))
    return None


def _age_matches(row: sqlite3.Row, birth: date | None, on: date | None) -> bool:
    has_min = row["age_min_value"] is not None and str(row["age_min_unit"] or "")
    has_max = row["age_max_value"] is not None and str(row["age_max_unit"] or "")
    if not has_min and not has_max:
        return True
    if birth is None or on is None:
        return False
    if has_min:
        amount = _completed(birth, on, str(row["age_min_unit"]))
        if amount is None:
            return False
        bound = int(row["age_min_value"])
        if bool(row["age_min_inclusive"]):
            if amount < bound:
                return False
        elif amount <= bound:
            return False
    if has_max:
        amount = _completed(birth, on, str(row["age_max_unit"]))
        if amount is None:
            return False
        bound = int(row["age_max_value"])
        if bool(row["age_max_inclusive"]):
            if amount > bound:
                return False
        elif amount >= bound:
            return False
    return True


def _sex_matches(row_sex: str, patient_sex: str) -> bool:
    wanted = _patient_sex(patient_sex)
    if row_sex == "any":
        return True
    return bool(wanted) and row_sex == wanted


def _patient_sex(value: str) -> str:
    text = str(value or "").strip().casefold()
    if text in {"m", "male"}:
        return "male"
    if text in {"f", "female"}:
        return "female"
    return ""


def _unit_key(unit: str) -> str:
    text = str(unit or "").strip().casefold().replace(" ", "")
    text = text.replace("×", "x").replace("µ", "u").replace("μ", "u")
    text = text.replace("10(9)/l", "10^9/l").replace("x10(9)/l", "10^9/l").replace("x10^9/l", "10^9/l")
    text = text.replace("10(12)/l", "10^12/l").replace("x10(12)/l", "10^12/l").replace("x10^12/l", "10^12/l")
    text = text.replace("gm/dl", "g/dl")
    return text


def _units_match(range_unit: str, result_unit: str) -> bool:
    if not str(result_unit or "").strip():
        return True
    if not str(range_unit or "").strip():
        return False
    return _unit_key(range_unit) == _unit_key(result_unit)


def _specimen_matches(range_specimen: str, given: str) -> bool:
    left = test_key(range_specimen)
    right = test_key(given)
    if not left or not right:
        return True
    if left == right or left in right or right in left:
        return True
    whole = ("whole blood", "edta")
    serum = ("serum", "plasma")
    if right == "blood" and (any(part in left for part in whole) or any(part in left for part in serum)):
        return True
    if left == "blood" and (any(part in right for part in whole) or any(part in right for part in serum)):
        return True
    return False


def _name_matches(row: sqlite3.Row, name: str) -> bool:
    key = test_key(name)
    if not key:
        return False
    if key == str(row["test_key"] or ""):
        return True
    try:
        aliases = json.loads(row["aliases"] or "[]")
    except json.JSONDecodeError:
        aliases = []
    return any(test_key(str(alias)) == key for alias in aliases if isinstance(alias, str) or alias)


def _effective(row: sqlite3.Row, on: date | None) -> bool:
    current = on or datetime.now(timezone.utc).date()
    start = _parse_date(row["effective_from"])
    end = _parse_date(row["effective_to"])
    if start and current < start:
        return False
    if end and current > end:
        return False
    return True


def _span_days(row: sqlite3.Row) -> tuple[float, float]:
    scale = {"days": 1.0, "weeks": 7.0, "months": 30.437, "years": 365.25}

    def edge(value: Any, unit: str, inclusive: bool, side: str) -> float:
        if value is None or not unit:
            return 0.0 if side == "min" else float("inf")
        days = float(value) * scale.get(unit, 1.0)
        if side == "min" and not inclusive:
            days += 0.001
        if side == "max" and not inclusive:
            days -= 0.001
        return days

    return (
        edge(row["age_min_value"], str(row["age_min_unit"] or ""), bool(row["age_min_inclusive"]), "min"),
        edge(row["age_max_value"], str(row["age_max_unit"] or ""), bool(row["age_max_inclusive"]), "max"),
    )


def _dominates(specific: sqlite3.Row, general: sqlite3.Row) -> bool:
    """True when both match and the first is a stricter partition of the second."""
    if str(specific["sex"]) != str(general["sex"]):
        if not (str(specific["sex"]) in {"male", "female"} and str(general["sex"]) == "any"):
            return False
    tighter = str(specific["sex"]) != "any" and str(general["sex"]) == "any"
    left = _span_days(specific)
    right = _span_days(general)
    if left[0] < right[0] or left[1] > right[1]:
        return False
    if left != right:
        tighter = True
    if str(specific["condition"] or "") != str(general["condition"] or ""):
        if str(specific["condition"] or "") and not str(general["condition"] or ""):
            tighter = True
        else:
            return False
    return tighter


def _reduce(candidates: list[sqlite3.Row]) -> list[sqlite3.Row]:
    kept: list[sqlite3.Row] = []
    for candidate in candidates:
        if any(_dominates(other, candidate) for other in candidates if other["id"] != candidate["id"]):
            continue
        kept.append(candidate)
    return kept


def select_reference(
    test_name: str,
    *,
    sex: str = "",
    birth: Any = None,
    on_date: Any = None,
    unit: str = "",
    specimen: str = "",
    condition: str = "",
) -> dict[str, Any]:
    """Choose one approved reference interval, or say why none was used."""
    born = _parse_date(birth)
    ordered = _parse_date(on_date)
    patient_condition = str(condition or "").strip().casefold()
    with LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM lab_reference_range
                WHERE status = 'approved' AND purpose = 'reference_interval'
                """
            ).fetchall()
        finally:
            connection.close()
    named = [row for row in rows if _name_matches(row, test_name)]
    fitting = []
    unit_blocked = False
    for row in named:
        if not _effective(row, ordered):
            continue
        if not _sex_matches(str(row["sex"] or "any"), sex):
            continue
        if str(row["condition"] or "").strip() and str(row["condition"]).casefold() != patient_condition:
            continue
        if not _age_matches(row, born, ordered):
            continue
        if not _specimen_matches(str(row["specimen"] or ""), specimen):
            continue
        if not _units_match(str(row["unit"] or ""), unit):
            unit_blocked = True
            continue
        fitting.append(row)
    fitting = _reduce(fitting)
    if not fitting:
        return _empty(UNIT_NOTE if unit_blocked else NO_RANGE)
    if len(fitting) > 1:
        return _empty(AMBIGUOUS)
    return _matched(fitting[0])


def _empty(note: str) -> dict[str, Any]:
    return {
        "matched": False,
        "low": "",
        "high": "",
        "lowInclusive": True,
        "highInclusive": True,
        "unit": "",
        "text": "",
        "source": "",
        "sourceDetail": "",
        "publisher": "",
        "version": "",
        "url": "",
        "accessed": "",
        "method": "",
        "limitations": "",
        "note": note,
        "id": "",
    }


def _matched(row: sqlite3.Row) -> dict[str, Any]:
    low = str(row["low_value"] or "")
    high = str(row["high_value"] or "")
    expected = json.loads(row["expected_values"] or "[]")
    text = _range_text(low, high, bool(row["low_inclusive"]), bool(row["high_inclusive"]))
    if not text and str(row["result_type"]) == "categorical" and isinstance(expected, list) and expected:
        text = "Expected: " + ", ".join(str(item) for item in expected)
    elif not text and str(row["descriptive_text"] or "").strip():
        text = str(row["descriptive_text"]).strip()
    return {
        "matched": True,
        "low": low,
        "high": high,
        "lowInclusive": bool(row["low_inclusive"]),
        "highInclusive": bool(row["high_inclusive"]),
        "unit": str(row["unit"] or ""),
        "text": text,
        "source": str(row["source_title"] or ""),
        "sourceDetail": " ".join(
            part
            for part in (
                str(row["source_publisher"] or ""),
                str(row["source_version"] or ""),
                str(row["method"] or ""),
            )
            if part
        ),
        "publisher": str(row["source_publisher"] or ""),
        "version": str(row["source_version"] or ""),
        "url": str(row["source_url"] or ""),
        "accessed": str(row["source_accessed"] or ""),
        "method": str(row["method"] or ""),
        "limitations": str(row["limitations"] or ""),
        "note": "",
        "id": str(row["id"]),
    }


def apply_to_tests(tests: list[dict[str, Any]], *, sex: str, birth: Any, on_date: Any, specimen: str = "") -> None:
    """Put an approved range on each result row. A range already saved with the result stays."""
    for test in tests:
        if not isinstance(test, dict):
            continue
        saved_low = str(test.get("savedReferenceLow") or "").strip()
        saved_high = str(test.get("savedReferenceHigh") or "").strip()
        if saved_low or saved_high:
            test["referenceLow"] = saved_low
            test["referenceHigh"] = saved_high
            test["referenceText"] = _range_text(saved_low, saved_high, True, True)
            test["referenceSource"] = "Saved with this result"
            test["referenceNote"] = ""
            test["referenceLowInclusive"] = True
            test["referenceHighInclusive"] = True
            continue
        options = test.get("options")
        coded = (isinstance(options, list) and bool(options)) or str(test.get("resultType") or "").strip().upper() in {
            "D",
            "A",
            "R",
        }
        chosen = select_reference(
            str(test.get("name") or ""),
            sex=sex,
            birth=birth,
            on_date=on_date,
            unit="" if coded else str(test.get("unit") or ""),
            specimen=specimen or str(test.get("specimen") or ""),
        )
        if coded and not chosen["matched"]:
            test["referenceLow"] = ""
            test["referenceHigh"] = ""
            test["referenceText"] = ""
            test["referenceSource"] = ""
            test["referenceNote"] = NO_RANGE
            test["unit"] = ""
            continue
        test["referenceLow"] = chosen["low"]
        test["referenceHigh"] = chosen["high"]
        test["referenceLowInclusive"] = chosen["lowInclusive"]
        test["referenceHighInclusive"] = chosen["highInclusive"]
        test["referenceText"] = chosen["text"]
        test["referenceSource"] = chosen["source"]
        test["referencePublisher"] = chosen["publisher"]
        test["referenceVersion"] = chosen["version"]
        test["referenceUrl"] = chosen["url"]
        test["referenceAccessed"] = chosen["accessed"]
        test["referenceMethod"] = chosen["method"]
        test["referenceLimitations"] = chosen["limitations"]
        test["referenceNote"] = "" if chosen["matched"] else chosen["note"]
        test["referenceId"] = chosen["id"]
        if chosen["matched"] and chosen["unit"] and not str(test.get("unit") or "").strip():
            test["unit"] = chosen["unit"]
