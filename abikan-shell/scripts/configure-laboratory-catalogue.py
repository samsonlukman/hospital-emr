#!/usr/bin/env python3
"""Configure the hospital laboratory catalogue on this installation.

Idempotent. Creates missing OpenMRS orderables, fills All_Tests_and_Panels,
and seeds Odoo service prices in NGN when a product is new or still at the
placeholder selling price. Does not overwrite a staff-managed selling price
set through Department Pricing.

Use --reset-prices only when you intentionally want catalogue CSV prices
written over existing selling prices.

Does not modify patients, visits, prescriptions, stock, or existing invoices.

Usage (from the workstation, OpenMRS and Odoo running):

    python3 scripts/configure-laboratory-catalogue.py
    python3 scripts/configure-laboratory-catalogue.py --reset-prices
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import xmlrpc.client
from pathlib import Path

from script_config import required_environment

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = Path(os.environ.get("ABIKAN_LAB_CODE", ROOT / "server" / "patient-account"))
if not (CODE_DIR / "lab_catalogue.py").exists() and Path("/app/lab_catalogue.py").exists():
    CODE_DIR = Path("/app")
sys.path.insert(0, str(CODE_DIR))

import lab_catalogue  # noqa: E402

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
ADMIN_USER = required_environment("ABIKAN_ADMIN_USER")
ADMIN_PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://localhost:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
ODOO_USER = ""
ODOO_PASSWORD = ""
CTX = ssl._create_unverified_context()

MAPPING = lab_catalogue.load_map()
TEST_CLASS = MAPPING["testClassUuid"]
LABSET_CLASS = MAPPING["labSetClassUuid"]
NA_TYPE = MAPPING["naDatatypeUuid"]
ALL_SET = MAPPING["allTestsAndPanelsUuid"]
CATEGORY_NAME = "Laboratory"


def admin_headers() -> dict[str, str]:
    import base64

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
        raise RuntimeError(f"{method} {path} -> {error.code} {detail[:500]}") from error


def find_concept_by_name(name: str, concept_class: str | None = None) -> str | None:
    quoted = urllib.request.quote(name)
    data = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/concept?q={quoted}&v=custom:(uuid,display,conceptClass:(display),names:(name,conceptNameType))&limit=20",
    )
    rows = data.get("results") if isinstance(data, dict) else data
    needle = name.strip().lower()
    allowed = {concept_class} if concept_class else {"Test", "LabSet"}
    for row in rows or []:
        klass = ((row.get("conceptClass") or {}).get("display") or "").strip()
        if klass not in allowed:
            continue
        names = [n.get("name", "") for n in (row.get("names") or [])]
        if row.get("display", "").strip().lower() == needle or any(n.strip().lower() == needle for n in names):
            return row.get("uuid")
    return None


def create_concept(name: str, concept_class: str) -> str:
    existing = find_concept_by_name(name, concept_class)
    if existing:
        return existing
    class_uuid = LABSET_CLASS if concept_class == "LabSet" else TEST_CLASS
    body = {
        "names": [
            {"name": name, "locale": "en", "conceptNameType": "FULLY_SPECIFIED"},
        ],
        "datatype": NA_TYPE,
        "conceptClass": class_uuid,
        "set": concept_class == "LabSet",
        "version": "Hospital EMR hospital laboratory catalogue",
    }
    created = omrs("POST", "/openmrs/ws/rest/v1/concept", body)
    uuid = created.get("uuid") if isinstance(created, dict) else None
    if not uuid:
        raise RuntimeError(f"Could not create concept {name}")
    return uuid


def set_members(set_uuid: str, member_uuids: list[str]) -> None:
    omrs(
        "POST",
        f"/openmrs/ws/rest/v1/concept/{set_uuid}",
        {"set": True, "setMembers": [{"uuid": uuid} for uuid in member_uuids]},
    )


def odoo():
    global ODOO_USER, ODOO_PASSWORD
    ODOO_USER = required_environment("ABIKAN_ODOO_USER")
    ODOO_PASSWORD = required_environment("ABIKAN_ODOO_PASSWORD")
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True, context=ssl._create_unverified_context())
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        # host port mapping may be via proxy; try docker published 8069 without ssl context default
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        raise RuntimeError("Odoo login failed")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


def kw(models, uid, model, method, args, kwargs=None):
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, model, method, args, kwargs or {})


def ensure_ngn(models, uid) -> int:
    rows = kw(
        models,
        uid,
        "res.currency",
        "search_read",
        [[("name", "=", "NGN")]],
        {"fields": ["id", "active"], "limit": 1, "context": {"active_test": False}},
    )
    if not rows:
        raise RuntimeError("NGN currency is missing from Odoo")
    currency_id = int(rows[0]["id"])
    if not rows[0].get("active"):
        kw(models, uid, "res.currency", "write", [[currency_id], {"active": True}])
    rates = kw(models, uid, "res.currency.rate", "search_read", [[("currency_id", "=", currency_id)]], {"fields": ["id", "rate"], "limit": 1})
    if not rates:
        kw(models, uid, "res.currency.rate", "create", [{"currency_id": currency_id, "rate": 1.0}])
    return currency_id


def ensure_lab_category(models, uid) -> int:
    rows = kw(models, uid, "product.category", "search_read", [[("name", "=", CATEGORY_NAME)]], {"fields": ["id"], "limit": 1})
    if rows:
        return int(rows[0]["id"])
    parents = kw(models, uid, "product.category", "search_read", [[("name", "=", "Services")]], {"fields": ["id"], "limit": 1})
    parent_id = int(parents[0]["id"]) if parents else False
    return int(kw(models, uid, "product.category", "create", [{"name": CATEGORY_NAME, "parent_id": parent_id}]))


def ensure_ngn_pricelist(models, uid, currency_id: int) -> int:
    name = "Hospital Laboratory"
    rows = kw(models, uid, "product.pricelist", "search_read", [[("name", "=", name)]], {"fields": ["id", "currency_id"], "limit": 1})
    if rows:
        pricelist_id = int(rows[0]["id"])
        kw(models, uid, "product.pricelist", "write", [[pricelist_id], {"currency_id": currency_id}])
        return pricelist_id
    return int(kw(models, uid, "product.pricelist", "create", [{"name": name, "currency_id": currency_id}]))


def ensure_lab_shop(models, uid, pricelist_id: int) -> None:
    shops = kw(models, uid, "sale.shop", "search_read", [[("name", "=", "Laboratory")]], {"fields": ["id"], "limit": 1})
    if shops:
        kw(models, uid, "sale.shop", "write", [[int(shops[0]["id"])], {"pricelist_id": pricelist_id}])


def upsert_lab_product(
    models,
    uid,
    category_id: int,
    concept_uuid: str,
    name: str,
    price: float,
    *,
    reset_prices: bool = False,
) -> None:
    found = kw(
        models,
        uid,
        "product.product",
        "search_read",
        [[("uuid", "=", concept_uuid)]],
        {"fields": ["id", "name", "list_price"], "limit": 1},
    )
    existing_price = None
    if found:
        try:
            existing_price = float(found[0].get("list_price") or 0)
        except (TypeError, ValueError):
            existing_price = 0.0
    values = lab_catalogue.lab_product_write_values(
        name=name,
        category_id=category_id,
        catalogue_price=price,
        existing_list_price=existing_price,
        reset_prices=reset_prices,
    )
    if found:
        product_id = int(found[0]["id"])
        kw(models, uid, "product.product", "write", [[product_id], values])
        return
    by_code = kw(
        models,
        uid,
        "product.product",
        "search_read",
        [[("default_code", "=", concept_uuid), ("name", "not ilike", " — TEST")]],
        {"fields": ["id", "list_price"], "limit": 1},
    )
    if by_code:
        try:
            code_price = float(by_code[0].get("list_price") or 0)
        except (TypeError, ValueError):
            code_price = 0.0
        values = lab_catalogue.lab_product_write_values(
            name=name,
            category_id=category_id,
            catalogue_price=price,
            existing_list_price=code_price,
            reset_prices=reset_prices,
        )
        kw(models, uid, "product.product", "write", [[int(by_code[0]["id"])], {**values, "uuid": concept_uuid}])
        return
    create_values = lab_catalogue.lab_product_write_values(
        name=name,
        category_id=category_id,
        catalogue_price=price,
        existing_list_price=None,
        reset_prices=reset_prices,
    )
    product_id = int(
        kw(
            models,
            uid,
            "product.product",
            "create",
            [{**create_values, "default_code": concept_uuid, "uuid": concept_uuid, "uom_id": 1, "uom_po_id": 1}],
        )
    )
    kw(models, uid, "product.product", "write", [[product_id], {"uuid": concept_uuid, "taxes_id": [(6, 0, [])]}])


def main() -> int:
    odoo_only = "--odoo-only" in sys.argv
    openmrs_only = "--openmrs-only" in sys.argv
    reset_prices = "--reset-prices" in sys.argv
    if odoo_only and openmrs_only:
        raise SystemExit("Choose only one of --odoo-only or --openmrs-only.")
    print("Configuring hospital laboratory catalogue…")
    by_sn: dict[str, dict] = {str(item["sn"]): item for item in MAPPING["items"]}
    runtime = lab_catalogue.load_runtime()
    created = 0
    reused = 0
    skipped = 0

    if not odoo_only:
        for item in MAPPING["items"]:
            sn = str(item["sn"])
            action = item.get("action")
            if action == "skip":
                runtime.pop(sn, None)
                skipped += 1
                continue
            if action == "reuse":
                uuid = item["conceptUuid"]
                found = omrs("GET", f"/openmrs/ws/rest/v1/concept/{uuid}?v=custom:(uuid,display)")
                if not isinstance(found, dict) or not found.get("uuid"):
                    raise RuntimeError(f"Reuse concept missing for {sn}: {uuid}")
                runtime[sn] = uuid
                reused += 1
                continue
            if action == "create":
                name = item["createName"]
                uuid = runtime.get(sn) or find_concept_by_name(name, item.get("conceptClass") or "Test")
                if not uuid:
                    uuid = create_concept(name, item.get("conceptClass") or "Test")
                    created += 1
                    print(f"  created {name} {uuid}")
                else:
                    reused += 1
                runtime[sn] = uuid
                item["conceptUuid"] = uuid

        # Panel members from hospital-named components only.
        for item in MAPPING["items"]:
            if item.get("action") != "create" or not item.get("memberSns"):
                continue
            set_uuid = runtime[str(item["sn"])]
            member_uuids = []
            for member_sn in item["memberSns"]:
                member_uuids.append(runtime[str(member_sn)])
            set_members(set_uuid, member_uuids)
            print(f"  set members for {item['createName']}")

        orderable_uuids = []
        seen = set()
        for item in MAPPING["items"]:
            if item.get("action") == "skip":
                continue
            uuid = runtime.get(str(item["sn"])) or item.get("conceptUuid")
            if uuid and uuid not in seen:
                seen.add(uuid)
                orderable_uuids.append(uuid)
        set_members(ALL_SET, orderable_uuids)
        print(f"  All_Tests_and_Panels members: {len(orderable_uuids)}")

        try:
            lab_catalogue.RUNTIME_PATH.write_text(json.dumps({"conceptBySn": runtime}, indent=2), encoding="utf-8")
        except OSError as error:
            print(f"  warning: could not write runtime map ({error})")
    else:
        for item in MAPPING["items"]:
            sn = str(item["sn"])
            if item.get("action") == "skip":
                skipped += 1
                continue
            uuid = runtime.get(sn) or item.get("conceptUuid")
            if uuid:
                item["conceptUuid"] = uuid
                reused += 1

    if openmrs_only:
        print(f"Done. reused={reused} created={created} skipped={skipped} odoo_prices=unchanged")
        return 0

    uid, models = odoo()
    ngn_id = ensure_ngn(models, uid)
    category_id = ensure_lab_category(models, uid)
    pricelist_id = ensure_ngn_pricelist(models, uid, ngn_id)
    ensure_lab_shop(models, uid, pricelist_id)

    entries = lab_catalogue.catalogue_entries()
    priced = 0
    for row in entries:
        if row["action"] == "skip" or not row.get("conceptUuid") or not row.get("priceNgn"):
            continue
        upsert_lab_product(
            models,
            uid,
            category_id,
            row["conceptUuid"],
            row["hospitalName"] or row["openmrsName"],
            float(row["priceNgn"]),
            reset_prices=reset_prices,
        )
        priced += 1
    price_mode = "reset" if reset_prices else "preserve-staff-prices"
    print(
        f"Done. reused={reused} created={created} skipped={skipped} "
        f"odoo_products={priced} price_mode={price_mode} ngn_pricelist={pricelist_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
