"""Daily visit number on the existing OpenMRS visit.

Stored as visit attribute "Daily Visit Number". Assigned once, under a
process lock, when Reception starts a visit. Not derived from list order.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import timedelta
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import server as core

ApiError = core.ApiError
OPENMRS_URL = core.OPENMRS_URL

ATTRIBUTE_TYPE_NAME = "Daily Visit Number"
ATTRIBUTE_TYPE_UUID = "b7e4c1a0-5d21-4f8a-9c3e-2a1f0e8d7c6b"
ATTRIBUTE_TYPE_DESCRIPTION = (
    "Sequential hospital visit number for the Africa/Lagos day. "
    "Not the hospital number."
)
ADMIN_USER = os.environ.get("ABIKAN_OPENMRS_ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ABIKAN_OPENMRS_ADMIN_PASSWORD", "")
VISIT_PAGE_SIZE = 100
VISIT_PAGE_CAP = 500
VISIT_REPRESENTATION = (
    "custom:(uuid,startDatetime,"
    "attributes:(uuid,value,display,attributeType:(uuid,name)))"
)

ALLOCATE_LOCK = threading.Lock()
IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}
_ATTRIBUTE_TYPE_UUID = ""


def format_daily_visit_number(value: int) -> str:
    if value < 1:
        raise ValueError("Daily visit number must be at least 1")
    return f"{value:03d}"


def parse_daily_visit_number(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.startswith("#"):
        text = text[1:].strip()
    if not re.fullmatch(r"[0-9]{1,6}", text):
        return None
    number = int(text)
    return number if number > 0 else None


def next_sequence_value(existing: list[Any]) -> int:
    values = [parsed for parsed in (parse_daily_visit_number(item) for item in existing) if parsed]
    return (max(values) if values else 0) + 1


def display_daily_visit_number(value: Any) -> str:
    parsed = parse_daily_visit_number(value)
    return format_daily_visit_number(parsed) if parsed else "—"


def sort_key(value: Any) -> tuple[int, int]:
    parsed = parse_daily_visit_number(value)
    if parsed is None:
        return (1, 0)
    return (0, parsed)


def daily_visit_number_from_visit(visit: dict[str, Any] | None) -> str:
    if not isinstance(visit, dict):
        return ""
    attributes = visit.get("attributes")
    rows = attributes if isinstance(attributes, list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        attribute_type = item.get("attributeType") if isinstance(item.get("attributeType"), dict) else {}
        name = str(attribute_type.get("name") or "").strip()
        uuid = str(attribute_type.get("uuid") or "").strip()
        if name != ATTRIBUTE_TYPE_NAME and uuid != ATTRIBUTE_TYPE_UUID:
            continue
        parsed = parse_daily_visit_number(item.get("value") or item.get("display"))
        if parsed:
            return format_daily_visit_number(parsed)
    return ""


def ignore_client_number(body: dict[str, Any] | None) -> None:
    """Client-supplied numbers are ignored. Assignment is server-side only."""
    return None


def begin_request(request_id: str) -> dict[str, Any] | None:
    if not request_id:
        return None
    with IDEMPOTENCY_LOCK:
        state = IDEMPOTENCY.get(request_id) or {}
        if state.get("status") == "pending":
            raise ApiError(
                409,
                "visit_in_progress",
                "This visit is already being started.",
            )
        if state.get("status") == "done" and isinstance(state.get("result"), dict):
            return state["result"]
        IDEMPOTENCY[request_id] = {"status": "pending"}
    return None


def finish_request(request_id: str, result: dict[str, Any] | None, *, ok: bool) -> None:
    if not request_id:
        return
    with IDEMPOTENCY_LOCK:
        if ok and result is not None:
            IDEMPOTENCY[request_id] = {"status": "done", "result": result}
        else:
            IDEMPOTENCY.pop(request_id, None)


def allocate_daily_visit_number(
    reader: Callable[[], list[Any]],
    persist: Callable[[str], None],
    *,
    lock: threading.Lock = ALLOCATE_LOCK,
) -> str:
    with lock:
        formatted = format_daily_visit_number(next_sequence_value(reader()))
        persist(formatted)
        return formatted


def _openmrs(
    path: str,
    cookie: str | None = None,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    admin: bool = False,
    fallback: str = "The visit number could not be saved.",
) -> Any:
    import base64

    headers = {"Accept": "application/json"}
    if admin:
        token = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    elif cookie:
        headers["Cookie"] = cookie
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(f"{OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=40) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        raise ApiError(502, "openmrs_error", fallback) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(502, "openmrs_error", fallback) from error


def ensure_attribute_type() -> str:
    global _ATTRIBUTE_TYPE_UUID
    if _ATTRIBUTE_TYPE_UUID:
        return _ATTRIBUTE_TYPE_UUID
    payload = _openmrs("/openmrs/ws/rest/v1/visitattributetype?v=custom:(uuid,name,retired)", admin=True)
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for item in rows or []:
        if not isinstance(item, dict) or item.get("retired"):
            continue
        if str(item.get("name") or "").strip() == ATTRIBUTE_TYPE_NAME:
            uuid = str(item.get("uuid") or "").strip()
            if uuid:
                _ATTRIBUTE_TYPE_UUID = uuid
                return uuid
    created = _openmrs(
        "/openmrs/ws/rest/v1/visitattributetype",
        admin=True,
        method="POST",
        payload={
            "uuid": ATTRIBUTE_TYPE_UUID,
            "name": ATTRIBUTE_TYPE_NAME,
            "description": ATTRIBUTE_TYPE_DESCRIPTION,
            "minOccurs": 0,
            "maxOccurs": 1,
            "datatypeClassname": "org.openmrs.customdatatype.datatype.FreeTextDatatype",
        },
        fallback="The visit number could not be prepared.",
    )
    uuid = str(created.get("uuid") or ATTRIBUTE_TYPE_UUID).strip()
    if not uuid:
        raise ApiError(502, "visit_number_failed", "The visit number could not be prepared.")
    _ATTRIBUTE_TYPE_UUID = uuid
    return uuid


def _todays_assigned_numbers(cookie: str) -> list[str]:
    import clinical_queue as queue

    today = queue.hospital_today()
    from_start = (today - timedelta(days=1)).isoformat()
    rows: list[str] = []
    start_index = 0
    while start_index < VISIT_PAGE_CAP:
        path = (
            f"/openmrs/ws/rest/v1/visit?fromStartDate={from_start}"
            f"&includeInactive=true"
            f"&limit={VISIT_PAGE_SIZE}"
            f"&startIndex={start_index}"
            f"&v={VISIT_REPRESENTATION}"
        )
        try:
            payload = _openmrs(path, cookie, fallback="The visit number could not be saved.")
        except ApiError:
            payload = _openmrs(path, admin=True, fallback="The visit number could not be saved.")
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list) or not results:
            break
        for item in results:
            if not isinstance(item, dict):
                continue
            if not queue.started_on_hospital_day(item.get("startDatetime"), today):
                continue
            number = daily_visit_number_from_visit(item)
            if number:
                rows.append(number)
        if len(results) < VISIT_PAGE_SIZE:
            break
        start_index += len(results)
    return rows


def _read_visit_number(visit_uuid: str, cookie: str) -> tuple[dict[str, Any], str]:
    path = f"/openmrs/ws/rest/v1/visit/{visit_uuid}?v={VISIT_REPRESENTATION}"
    try:
        visit = _openmrs(path, cookie, fallback="The visit number could not be saved.")
    except ApiError:
        visit = _openmrs(path, admin=True, fallback="The visit number could not be saved.")
    if not isinstance(visit, dict):
        return {}, ""
    return visit, daily_visit_number_from_visit(visit)


def _persist_on_visit(visit_uuid: str, cookie: str, number: str) -> None:
    _, stored = _read_visit_number(visit_uuid, cookie)
    if stored == number:
        return
    type_uuid = ensure_attribute_type()
    payload = {"attributes": [{"attributeType": type_uuid, "value": number}]}
    path = f"/openmrs/ws/rest/v1/visit/{visit_uuid}"
    try:
        _openmrs(
            path,
            cookie,
            method="POST",
            payload=payload,
            fallback="The visit number could not be saved.",
        )
    except ApiError:
        try:
            _openmrs(
                path,
                admin=True,
                method="POST",
                payload=payload,
                fallback="The visit number could not be saved.",
            )
        except ApiError:
            _, stored = _read_visit_number(visit_uuid, cookie)
            if stored == number:
                return
            raise
    _, stored = _read_visit_number(visit_uuid, cookie)
    if stored != number:
        raise ApiError(502, "visit_number_failed", "The visit number could not be saved.")


def assign_to_visit(visit_uuid: str, cookie: str) -> str:
    if not visit_uuid:
        raise ApiError(502, "visit_number_failed", "The visit number could not be saved.")
    ensure_attribute_type()
    return allocate_daily_visit_number(
        lambda: _todays_assigned_numbers(cookie),
        lambda number: _persist_on_visit(visit_uuid, cookie, number),
    )


def create_visit_with_number(cookie: str, visit_payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Create the OpenMRS visit and persist today's number before returning."""
    type_uuid = ensure_attribute_type()

    def persist(number: str) -> dict[str, Any]:
        payload = {
            **visit_payload,
            "attributes": [{"attributeType": type_uuid, "value": number}],
        }
        created = _openmrs(
            "/openmrs/ws/rest/v1/visit",
            cookie,
            method="POST",
            payload=payload,
            fallback="The visit could not be started.",
        )
        uuid = str(created.get("uuid") or "").strip()
        if not uuid:
            raise ApiError(502, "visit_failed", "The visit could not be started.")
        stored = daily_visit_number_from_visit(created)
        if stored != number:
            checked, stored = _read_visit_number(uuid, cookie)
            if stored != number:
                _persist_on_visit(uuid, cookie, number)
                checked, stored = _read_visit_number(uuid, cookie)
            if stored != number:
                raise ApiError(502, "visit_number_failed", "The visit number could not be saved.")
            created = checked or created
            created["uuid"] = uuid
        return created

    holder: dict[str, Any] = {}

    def write(number: str) -> None:
        holder["visit"] = persist(number)

    number = allocate_daily_visit_number(
        lambda: _todays_assigned_numbers(cookie),
        write,
    )
    created = holder.get("visit")
    if not isinstance(created, dict):
        raise ApiError(502, "visit_failed", "The visit could not be started.")
    return created, number
