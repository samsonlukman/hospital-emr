"""Hospital laboratory catalogue management.

Authorized Laboratory users select existing master Test/LabSet concepts into the
hospital ordering subset. They do not invent free-text tests, and there is no
request/review/approval queue.

Master catalogue = OpenMRS Test/LabSet concepts (already linked to OpenELIS via
concept UUID / external_reference). Hospital catalogue = curated enabled subset.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import department_pricing as pricing
import lab_catalogue
import laboratory as lab_billing
import server as core
from hospital_admin import is_hospital_admin, is_technical_superadmin
from server import ApiError

STORE_LOCK = threading.Lock()
DICTIONARY_USER = os.environ.get("ABIKAN_OPENMRS_ADMIN_USER", "")
DICTIONARY_PASSWORD = os.environ.get("ABIKAN_OPENMRS_ADMIN_PASSWORD", "")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def can_manage_hospital_tests(user: dict[str, Any]) -> bool:
    return (
        lab_billing.is_lab_user(user)
        or is_hospital_admin(user)
        or is_technical_superadmin(user)
    )


def require_hospital_test_manager(cookie: str) -> dict[str, Any]:
    core.require_session(cookie)
    user = lab_billing.load_openmrs_user(cookie)
    if can_manage_hospital_tests(user):
        return user
    raise ApiError(
        403,
        "forbidden",
        "Only Laboratory staff can manage the hospital test catalogue.",
    )


def _openmrs(
    method: str,
    path: str,
    cookie: str,
    payload: dict[str, Any] | None = None,
    *,
    dictionary: bool = False,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if dictionary:
        if not DICTIONARY_USER or not DICTIONARY_PASSWORD:
            raise ApiError(
                503,
                "dictionary_unavailable",
                "Hospital test management is not configured on this server.",
            )
        token = base64.b64encode(f"{DICTIONARY_USER}:{DICTIONARY_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    else:
        headers["Cookie"] = cookie
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{core.OPENMRS_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        if error.code == 403:
            if dictionary:
                raise ApiError(
                    502,
                    "dictionary_forbidden",
                    "The hospital test catalogue could not be updated.",
                ) from error
            raise ApiError(
                403,
                "forbidden",
                "This action requires the Laboratory workspace.",
            ) from error
        if error.code == 404:
            raise ApiError(404, "not_found", "That laboratory test was not found.") from error
        raise ApiError(
            502,
            "openmrs_error",
            "The laboratory catalogue could not be updated.",
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ApiError(
            502,
            "openmrs_error",
            "The laboratory catalogue could not be updated.",
        ) from error


def _is_lab_concept(row: dict[str, Any]) -> bool:
    if row.get("retired"):
        return False
    concept_class = row.get("conceptClass")
    if not isinstance(concept_class, dict):
        return False
    return str(concept_class.get("display") or "").strip() in {"Test", "LabSet"}


def _concept_names(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    display = _text(row.get("display"))
    if display:
        names.append(display)
    for entry in row.get("names") or []:
        if not isinstance(entry, dict):
            continue
        name = _text(entry.get("name"))
        if name and name not in names:
            names.append(name)
    return names


def _type_label(concept_class: str) -> str:
    return "Panel" if concept_class == "LabSet" else "Test"


def _serialize_master_hit(row: dict[str, Any], *, already_enabled: bool) -> dict[str, Any]:
    concept_class = str((row.get("conceptClass") or {}).get("display") or "Test").strip() or "Test"
    names = _concept_names(row)
    primary = names[0] if names else _text(row.get("display"))
    synonyms = [name for name in names[1:] if name.lower() != primary.lower()]
    return {
        "conceptUuid": _text(row.get("uuid")),
        "name": primary,
        "conceptClass": concept_class,
        "type": _type_label(concept_class),
        "synonyms": synonyms[:6],
        "alreadyEnabled": already_enabled,
    }


def _looks_like_uuid(value: str) -> bool:
    text = value.strip()
    if len(text) < 32:
        return False
    return bool(re.fullmatch(r"[0-9A-Fa-f-]{32,36}", text))


def _enabled_concept_uuids() -> set[str]:
    return {
        str(row.get("conceptUuid") or "").strip()
        for row in lab_catalogue.orderable_entries()
        if str(row.get("conceptUuid") or "").strip()
    }


def search_master_tests(cookie: str, raw_query: str) -> dict[str, Any]:
    """Search the master laboratory catalogue (Test / LabSet concepts)."""
    require_hospital_test_manager(cookie)
    term = _text(raw_query)
    if len(term) < 2:
        return {"status": "ok", "q": term, "tests": []}

    enabled = _enabled_concept_uuids()
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    if _looks_like_uuid(term):
        try:
            payload = _openmrs(
                "GET",
                f"/openmrs/ws/rest/v1/concept/{quote(term)}"
                "?v=custom:(uuid,display,conceptClass:(display),names:(name,conceptNameType),retired)",
                cookie,
            )
        except ApiError as error:
            if error.code == "not_found":
                return {"status": "ok", "q": term, "tests": []}
            raise
        if isinstance(payload, dict) and _is_lab_concept(payload):
            uuid = _text(payload.get("uuid"))
            if uuid and uuid not in seen:
                seen.add(uuid)
                hits.append(_serialize_master_hit(payload, already_enabled=uuid in enabled))
        return {"status": "ok", "q": term, "tests": hits}

    quoted = quote(term)
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept?q={quoted}"
        "&v=custom:(uuid,display,conceptClass:(display),names:(name,conceptNameType),retired)"
        "&limit=80",
        cookie,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    for row in rows or []:
        if not isinstance(row, dict) or not _is_lab_concept(row):
            continue
        uuid = _text(row.get("uuid"))
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        hits.append(_serialize_master_hit(row, already_enabled=uuid in enabled))

    needle = term.lower()
    exact: list[dict[str, Any]] = []
    prefix: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for row in hits:
        name = str(row.get("name") or "").lower()
        syns = " ".join(row.get("synonyms") or []).lower()
        if name == needle or needle in (row.get("conceptUuid") or "").lower():
            exact.append(row)
        elif name.startswith(needle) or any(s.startswith(needle) for s in syns.split()):
            prefix.append(row)
        else:
            other.append(row)
    ordered = exact + prefix + other
    return {"status": "ok", "q": term, "tests": ordered[:40]}


def load_master_concept(cookie: str, concept_uuid: str) -> dict[str, Any]:
    uuid = _text(concept_uuid)
    if not uuid:
        raise ApiError(422, "concept_required", "Select a test from the master catalogue.")
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept/{quote(uuid)}"
        "?v=custom:(uuid,display,conceptClass:(display),names:(name,conceptNameType),retired)",
        cookie,
    )
    if not isinstance(payload, dict) or not payload.get("uuid"):
        raise ApiError(404, "not_found", "That laboratory test was not found in the master catalogue.")
    if not _is_lab_concept(payload):
        raise ApiError(
            422,
            "invalid_concept",
            "Choose a laboratory test or panel from the master catalogue.",
        )
    return payload


def _orderable_set_uuid() -> str:
    mapping = lab_catalogue.load_map()
    return _text(mapping.get("allTestsAndPanelsUuid")) or lab_catalogue.ALL_TESTS_AND_PANELS_UUID


def _ensure_orderable_member(cookie: str, concept_uuid: str) -> None:
    set_uuid = _orderable_set_uuid()
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept/{quote(set_uuid)}?v=custom:(uuid,setMembers:(uuid))",
        cookie,
        dictionary=True,
    )
    members = payload.get("setMembers") if isinstance(payload, dict) else []
    member_uuids = [
        _text(row.get("uuid"))
        for row in (members or [])
        if isinstance(row, dict) and _text(row.get("uuid"))
    ]
    if concept_uuid in member_uuids:
        return
    member_uuids.append(concept_uuid)
    _openmrs(
        "POST",
        f"/openmrs/ws/rest/v1/concept/{quote(set_uuid)}",
        cookie,
        {"set": True, "setMembers": [{"uuid": value} for value in member_uuids]},
        dictionary=True,
    )


def _remove_orderable_member(cookie: str, concept_uuid: str) -> None:
    set_uuid = _orderable_set_uuid()
    payload = _openmrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept/{quote(set_uuid)}?v=custom:(uuid,setMembers:(uuid))",
        cookie,
        dictionary=True,
    )
    members = payload.get("setMembers") if isinstance(payload, dict) else []
    member_uuids = [
        _text(row.get("uuid"))
        for row in (members or [])
        if isinstance(row, dict) and _text(row.get("uuid")) and _text(row.get("uuid")) != concept_uuid
    ]
    _openmrs(
        "POST",
        f"/openmrs/ws/rest/v1/concept/{quote(set_uuid)}",
        cookie,
        {"set": True, "setMembers": [{"uuid": value} for value in member_uuids]},
        dictionary=True,
    )


def _ensure_fee_product_available(concept_uuid: str, name: str) -> None:
    """Ensure a hospital fee product exists so pricing can be set later.

    Does not invent a selling price: new products start at 0.00.
    """
    try:
        odoo = lab_billing.odoo_reader()
    except ApiError:
        return
    try:
        ensure_lab_fee_product(odoo, concept_uuid, name=name, list_price=0.0)
    except ApiError:
        # Ordering must still work; pricing can be completed later.
        return


def ensure_lab_fee_product(
    odoo: lab_billing.OdooReader,
    concept_uuid: str,
    *,
    name: str,
    list_price: float | None = None,
) -> dict[str, Any]:
    """Create or return the hospital fee product for an existing catalogue concept."""
    needle = (concept_uuid or "").strip()
    if not needle:
        raise ApiError(404, "not_found", "That laboratory test was not found in the hospital list.")
    mapped = lab_billing.find_lab_pricing_products(odoo, [needle])
    if needle in mapped:
        return mapped[needle]
    masters = lab_billing.ensure_lab_masters(odoo)
    category_id = int(masters["category_id"])
    price = float(list_price) if list_price is not None else 0.0
    values = lab_catalogue.lab_product_write_values(
        name=name,
        category_id=category_id,
        catalogue_price=price,
        existing_list_price=None,
        reset_prices=True,
    )
    product_id = int(
        lab_billing.execute(
            odoo,
            "product.product",
            "create",
            [
                {
                    **values,
                    "default_code": needle,
                    "uuid": needle,
                    "uom_id": 1,
                    "uom_po_id": 1,
                }
            ],
        )
    )
    lab_billing.execute(
        odoo,
        "product.product",
        "write",
        [[product_id], {"uuid": needle, "taxes_id": [(6, 0, [])], "supplier_taxes_id": [(6, 0, [])]}],
    )
    found = odoo.read(
        "product.product",
        [product_id],
        ["id", "name", "list_price", "type", "uuid", "default_code"],
    )
    if not found:
        raise ApiError(502, "fee_create_failed", "The hospital fee for this test could not be created.")
    return found[0]


def list_hospital_tests(cookie: str, query: str = "") -> dict[str, Any]:
    user = require_hospital_test_manager(cookie)
    currency = dict(lab_billing.NGN_CURRENCY)
    reader = None
    try:
        reader = lab_billing.odoo_reader()
        currency = lab_billing.lab_currency(reader)
    except ApiError:
        reader = None
    items: list[dict[str, Any]] = []
    for row in lab_catalogue.search_entries(query, include_unorderable=False):
        live = None
        if reader and row.get("conceptUuid"):
            try:
                product = lab_billing.find_lab_product(reader, row["conceptUuid"])
                live = lab_billing.as_float(product.get("list_price"))
            except ApiError:
                live = None
        serialized = lab_catalogue.serialize_entry(row, live_price=live, currency=currency)
        serialized["enabled"] = True
        serialized["managed"] = bool(row.get("managed"))
        items.append(serialized)
    return {
        "status": "ok",
        "canManage": can_manage_hospital_tests(user),
        "currency": {
            "code": currency.get("code") or "NGN",
            "symbol": currency.get("symbol") or "₦",
        },
        "tests": items,
        "message": (
            "These tests are available for New Lab Order. Add from the master catalogue "
            "when the hospital starts offering another existing laboratory test."
        ),
    }


def enable_hospital_test(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    """Immediately add an existing master test to the hospital catalogue."""
    user = require_hospital_test_manager(cookie)
    actor = pricing._actor(cookie, user)
    concept_uuid = _text(body.get("conceptUuid") or body.get("uuid"))
    concept = load_master_concept(cookie, concept_uuid)
    concept_uuid = _text(concept.get("uuid"))
    names = _concept_names(concept)
    display_name = names[0] if names else _text(concept.get("display"))
    concept_class = str((concept.get("conceptClass") or {}).get("display") or "Test").strip() or "Test"

    existing = lab_catalogue.entry_by_concept(concept_uuid)
    if existing and existing.get("orderable"):
        return {
            "status": "ok",
            "alreadyEnabled": True,
            "message": "Already available",
            "test": lab_catalogue.serialize_entry(existing),
        }

    managed_item = {
        "sn": f"M-{concept_uuid[:8]}",
        "conceptUuid": concept_uuid,
        "hospitalName": display_name,
        "openmrsName": display_name,
        "conceptClass": concept_class,
        "type": _type_label(concept_class),
        "department": "Laboratory",
        "enabled": True,
        "addedAt": _now(),
        "addedBy": actor.get("username") or "",
        "addedByDisplay": actor.get("display") or actor.get("username") or "",
    }

    with STORE_LOCK:
        store = lab_catalogue.load_managed_store()
        items = [row for row in (store.get("items") or []) if isinstance(row, dict)]
        disabled = {
            str(value).strip()
            for value in (store.get("disabledConceptUuids") or [])
            if str(value or "").strip()
        }
        disabled.discard(concept_uuid)
        replaced = False
        for row in items:
            if str(row.get("conceptUuid") or "").strip() == concept_uuid:
                row.update(managed_item)
                replaced = True
                break
        if not replaced:
            items.append(managed_item)
        lab_catalogue.save_managed_store({"items": items, "disabledConceptUuids": sorted(disabled)})

    _ensure_orderable_member(cookie, concept_uuid)
    _ensure_fee_product_available(concept_uuid, display_name)

    enabled = lab_catalogue.entry_by_concept(concept_uuid)
    if not enabled:
        raise ApiError(
            502,
            "enable_failed",
            "The test was selected but could not be added to the hospital catalogue.",
        )
    return {
        "status": "ok",
        "alreadyEnabled": False,
        "message": f"{display_name} added to hospital laboratory catalogue.",
        "test": lab_catalogue.serialize_entry(enabled),
    }


def disable_hospital_test(concept_uuid: str, cookie: str) -> dict[str, Any]:
    """Remove a test from hospital ordering only. Does not delete master definitions."""
    require_hospital_test_manager(cookie)
    needle = _text(concept_uuid)
    if not needle:
        raise ApiError(422, "concept_required", "Choose a hospital test to remove.")

    existing = None
    for row in lab_catalogue.catalogue_entries():
        if row.get("conceptUuid") == needle:
            existing = row
            break
    if not existing:
        raise ApiError(404, "not_found", "That laboratory test is not in the hospital catalogue.")
    if not existing.get("orderable"):
        return {
            "status": "ok",
            "message": "That test is already unavailable for new orders.",
            "test": lab_catalogue.serialize_entry(existing),
        }

    with STORE_LOCK:
        store = lab_catalogue.load_managed_store()
        items = [row for row in (store.get("items") or []) if isinstance(row, dict)]
        disabled = {
            str(value).strip()
            for value in (store.get("disabledConceptUuids") or [])
            if str(value or "").strip()
        }
        disabled.add(needle)
        for row in items:
            if str(row.get("conceptUuid") or "").strip() == needle:
                row["enabled"] = False
        lab_catalogue.save_managed_store({"items": items, "disabledConceptUuids": sorted(disabled)})

    try:
        _remove_orderable_member(cookie, needle)
    except ApiError:
        # Hospital catalogue disable still applies even if set membership update fails.
        pass

    name = existing.get("hospitalName") or existing.get("openmrsName") or "Test"
    return {
        "status": "ok",
        "message": f"{name} removed from hospital ordering. Existing orders and results are unchanged.",
        "conceptUuid": needle,
    }


def create_laboratory_test(_body: dict[str, Any], _cookie: str) -> dict[str, Any]:
    """Removed: Hospital EMR must not invent orderable laboratory tests."""
    raise ApiError(
        403,
        "test_create_forbidden",
        "Laboratory tests cannot be created by typing a name. "
        "Open Hospital Tests and add an existing test from the master catalogue.",
    )
