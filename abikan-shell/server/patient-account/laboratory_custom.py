"""Hospital EMR-local custom laboratory tests (not OpenELIS master catalogue).

Laboratory staff can define a test form with named result columns and property
rows. These are stored in Hospital EMR for hospital use; they are not invented inside
the master lab engine.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laboratory_manage import require_hospital_test_manager
from server import ApiError

STORE_LOCK = threading.Lock()
DATA_DIR = Path(__file__).resolve().parent / "data"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_path() -> Path:
    override = os.environ.get("ABIKAN_LAB_CUSTOM_TESTS")
    if override:
        return Path(override)
    audit = os.environ.get("ABIKAN_ADMIN_AUDIT_DB")
    if audit:
        return Path(audit).resolve().parent / "laboratory_custom_tests.json"
    return DATA_DIR / "laboratory_custom_tests.json"


def _load() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("tests") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _save(rows: list[dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updatedAt": _now(), "tests": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_price(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        raise ApiError(422, "invalid_body", "Enter a price of zero or more, or leave price blank.") from None
    if amount < 0:
        raise ApiError(422, "invalid_body", "Enter a price of zero or more, or leave price blank.")
    return round(amount, 2)


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    price = row.get("price")
    return {
        "id": _text(row.get("id")),
        "name": _text(row.get("name")),
        "price": price,
        "priceLabel": None if price is None else f"₦{float(price):,.2f}",
        "columns": list(row.get("columns") or []),
        "properties": list(row.get("properties") or []),
        "createdAt": _text(row.get("createdAt")),
        "createdBy": _text(row.get("createdBy")),
        "source": "abikan",
    }


def list_custom_tests(cookie: str) -> dict[str, Any]:
    require_hospital_test_manager(cookie)
    with STORE_LOCK:
        rows = sorted(_load(), key=lambda row: _text(row.get("name")).lower())
    return {
        "tests": [_serialize(row) for row in rows],
        "message": "These tests were created in Hospital EMR for this hospital.",
    }


def create_custom_test(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_hospital_test_manager(cookie)
    name = _text(body.get("name"))
    if not name:
        raise ApiError(422, "invalid_body", "Enter a test name.")

    columns_raw = body.get("columns")
    if not isinstance(columns_raw, list) or not columns_raw:
        raise ApiError(422, "invalid_body", "Name at least one result column.")
    columns = [_text(item) for item in columns_raw]
    if not any(columns):
        raise ApiError(422, "invalid_body", "Name at least one result column.")

    properties_raw = body.get("properties")
    if not isinstance(properties_raw, list) or not properties_raw:
        raise ApiError(422, "invalid_body", "Add at least one property name in the Name column.")
    properties: list[dict[str, Any]] = []
    for item in properties_raw:
        if not isinstance(item, dict):
            continue
        prop_name = _text(item.get("name"))
        if not prop_name:
            continue
        values_raw = item.get("values")
        values = [_text(value) for value in values_raw] if isinstance(values_raw, list) else []
        while len(values) < len(columns):
            values.append("")
        properties.append({"name": prop_name, "values": values[: len(columns)]})
    if not properties:
        raise ApiError(422, "invalid_body", "Add at least one property name in the Name column.")

    row = {
        "id": str(uuid.uuid4()),
        "name": name,
        "price": _parse_price(body.get("price")),
        "columns": columns,
        "properties": properties,
        "createdAt": _now(),
        "createdBy": _text(user.get("username") or user.get("display")),
    }
    with STORE_LOCK:
        rows = _load()
        if any(_text(existing.get("name")).lower() == name.lower() for existing in rows):
            raise ApiError(
                409,
                "duplicate_test",
                "A custom test with this name already exists. Choose a different name.",
            )
        rows.append(row)
        _save(rows)
    return {
        "test": _serialize(row),
        "message": "Test created in Hospital EMR. It is ready for hospital use from this screen.",
    }
