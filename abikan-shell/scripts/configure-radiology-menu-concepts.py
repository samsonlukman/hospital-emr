#!/usr/bin/env python3
"""Configure missing hospital Radiology/Imaging Procedure concepts.

Idempotent. Creates only hospital-approved names that have no safe existing
OpenMRS Radiology/Imaging Procedure concept. Adds them to All Radiology orders.
Creates an Odoo service product stub (list_price 0) so the existing Radiologist
pricing path can attach a charge. Does not set a hospital catalogue price.

Does not modify patients, visits, orders, invoices, or ORD-6/14/15/16/17/18/19.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import xmlrpc.client

from script_config import required_environment

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
ADMIN_USER = required_environment("ABIKAN_ADMIN_USER")
ADMIN_PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://localhost:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
ODOO_USER = required_environment("ABIKAN_ODOO_USER")
ODOO_PASSWORD = required_environment("ABIKAN_ODOO_PASSWORD")
CTX = ssl._create_unverified_context()

RADIOLOGY_CLASS = "c6664c16-16b4-4bf4-91da-93f2ac88a0eb"
NA_TYPE = "8d4a4c94-c2cc-11de-8d13-0010c6dffd0f"
ALL_RADIOLOGY_ORDERS = "05d53977-443c-4883-a1f8-ea265fdaaf39"
CATEGORY_NAME = "Radiology"

# Hospital-approved names with no safe existing Radiology/Imaging Procedure concept.
CREATE_NAMES = [
    "Abdominopelvic",
    "Biophysical Profile (BPP)",
    "Anomaly Scan",
    "Eye/Ocular",
    "Follicular Tracking",
    "Doppler Studies",
    "Thyroid/Neck",
    "Paediatric X-ray",
    "Retrograde Urethrography (RCUG)",
    "Thoracic Inlet",
    "Temporomandibular Joint",
    "Barium Follow Through",
    "Wrist/Hand/Finger X-ray",
]


def admin_headers() -> dict[str, str]:
    token = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def omrs(method: str, path: str, payload: dict | None = None) -> dict | list | None:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers=admin_headers(),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, context=CTX, timeout=60) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        raise RuntimeError(f"{method} {path} -> {error.code} {detail[:800]}") from error


def find_imaging_concept(name: str) -> dict | None:
    quoted = urllib.request.quote(name)
    data = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept?q={quoted}"
        "&v=custom:(uuid,display,conceptClass:(display),names:(name,conceptNameType))&limit=25",
    )
    rows = data.get("results") if isinstance(data, dict) else data
    needle = name.strip().lower()
    for row in rows or []:
        klass = ((row.get("conceptClass") or {}).get("display") or "").strip()
        if klass != "Radiology/Imaging Procedure":
            continue
        names = [str(item.get("name") or "") for item in (row.get("names") or [])]
        if str(row.get("display") or "").strip().lower() == needle or any(
            item.strip().lower() == needle for item in names
        ):
            return row
    return None


def create_imaging_concept(name: str) -> str:
    created = omrs(
        "POST",
        "/openmrs/ws/rest/v1/concept",
        {
            "names": [{"name": name, "locale": "en", "conceptNameType": "FULLY_SPECIFIED"}],
            "datatype": NA_TYPE,
            "conceptClass": RADIOLOGY_CLASS,
            "version": "Hospital EMR hospital radiology menu",
        },
    )
    uuid = created.get("uuid") if isinstance(created, dict) else None
    if not uuid:
        raise RuntimeError(f"Could not create concept {name}")
    return str(uuid)


def add_to_all_radiology_orders(uuids: list[str]) -> None:
    current = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept/{ALL_RADIOLOGY_ORDERS}?v=custom:(uuid,setMembers:(uuid))",
    )
    members = current.get("setMembers") if isinstance(current, dict) else []
    existing = [str(row.get("uuid")) for row in (members or []) if row.get("uuid")]
    seen = set(existing)
    merged = list(existing)
    added = 0
    for uuid in uuids:
        if uuid not in seen:
            seen.add(uuid)
            merged.append(uuid)
            added += 1
    if added:
        omrs(
            "POST",
            f"/openmrs/ws/rest/v1/concept/{ALL_RADIOLOGY_ORDERS}",
            {"set": True, "setMembers": [{"uuid": uuid} for uuid in merged]},
        )
    print(f"  All Radiology orders members: {len(merged)} (added {added})")


def odoo_models():
    common = xmlrpc.client.ServerProxy(
        f"{ODOO_URL}/xmlrpc/2/common",
        allow_none=True,
        context=ssl._create_unverified_context(),
    )
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        raise RuntimeError("Odoo login failed")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


def kw(models, uid, model, method, args, kwargs=None):
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, model, method, args, kwargs or {})


def radiology_category(models, uid) -> int:
    rows = kw(
        models,
        uid,
        "product.category",
        "search_read",
        [[("name", "=", CATEGORY_NAME)]],
        {"fields": ["id"], "limit": 1},
    )
    if rows:
        return int(rows[0]["id"])
    parents = kw(
        models,
        uid,
        "product.category",
        "search_read",
        [[("name", "=", "Services")]],
        {"fields": ["id"], "limit": 1},
    )
    parent_id = int(parents[0]["id"]) if parents else False
    return int(kw(models, uid, "product.category", "create", [{"name": CATEGORY_NAME, "parent_id": parent_id}]))


def ensure_product_stub(models, uid, category_id: int, concept_uuid: str, name: str) -> None:
    """Product reference only. list_price 0 is not a hospital fee."""
    found = kw(
        models,
        uid,
        "product.product",
        "search_read",
        [[("uuid", "=", concept_uuid)]],
        {"fields": ["id", "name", "list_price"], "limit": 1},
    )
    if found:
        return
    product_id = int(
        kw(
            models,
            uid,
            "product.product",
            "create",
            [
                {
                    "name": name,
                    "type": "service",
                    "categ_id": category_id,
                    "list_price": 0.0,
                    "uom_id": 1,
                    "uom_po_id": 1,
                    "sale_ok": True,
                    "purchase_ok": False,
                    "invoice_policy": "order",
                    "default_code": concept_uuid,
                    "uuid": concept_uuid,
                    "taxes_id": [(6, 0, [])],
                    "supplier_taxes_id": [(6, 0, [])],
                }
            ],
        )
    )
    kw(
        models,
        uid,
        "product.product",
        "write",
        [[product_id], {"uuid": concept_uuid, "list_price": 0.0, "taxes_id": [(6, 0, [])]}],
    )


def main() -> int:
    print("Configuring hospital Radiology menu concepts…")
    created: list[tuple[str, str]] = []
    reused: list[tuple[str, str]] = []
    uuids: list[str] = []
    for name in CREATE_NAMES:
        existing = find_imaging_concept(name)
        if existing and existing.get("uuid"):
            uuid = str(existing["uuid"])
            reused.append((name, uuid))
            print(f"  reused {name} {uuid}")
        else:
            uuid = create_imaging_concept(name)
            created.append((name, uuid))
            print(f"  created {name} {uuid}")
        uuids.append(uuid)

    add_to_all_radiology_orders(uuids)

    uid, models = odoo_models()
    category_id = radiology_category(models, uid)
    for name, uuid in created + reused:
        ensure_product_stub(models, uid, category_id, uuid, name)
    print(f"  Odoo product stubs checked: {len(created) + len(reused)}")

    print("CREATED_CONCEPTS = {")
    for name, uuid in created + reused:
        print(f'    "{name}": "{uuid}",')
    print("}")
    print(f"created={len(created)} reused={len(reused)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
