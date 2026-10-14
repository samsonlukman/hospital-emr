#!/usr/bin/env python3
"""Configure mapped hospital pharmacy items for development / testing.

Idempotent. Creates missing OpenMRS drugs OpenMRS-first, waits for the drug
atomfeed to create the Odoo product, then sets a temporary NGN 100 selling
price. Does not import spreadsheet quantities. Does not change Laboratory
prices, TEST pharmacy products, patients, visits, or ORD-7.

Usage:

    python3 scripts/configure-pharmacy-catalogue.py
    python3 scripts/configure-pharmacy-catalogue.py --odoo-only
    python3 scripts/configure-pharmacy-catalogue.py --apply-test-stock
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client
from pathlib import Path

from script_config import required_environment

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = Path(os.environ.get("ABIKAN_PHARMACY_CODE", ROOT / "server" / "patient-account"))
if not (CODE_DIR / "pharmacy_catalogue.py").exists() and Path("/app/pharmacy_catalogue.py").exists():
    CODE_DIR = Path("/app")
sys.path.insert(0, str(CODE_DIR))

import pharmacy_catalogue  # noqa: E402

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
ADMIN_USER = required_environment("ABIKAN_ADMIN_USER")
ADMIN_PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://localhost:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
ODOO_USER = required_environment("ABIKAN_ODOO_USER")
ODOO_PASSWORD = required_environment("ABIKAN_ODOO_PASSWORD")
CTX = ssl._create_unverified_context()

MAPPING = pharmacy_catalogue.load_map()
PRICELIST_NAME = "Hospital Pharmacy"
SHOP_NAME = "Pharmacy Counter"
TEST_STOCK_DRUG_UUID = "7e0766e1-b679-4eb3-ab93-d63910ad6eb4"  # Cetirizine 10 mg
TEST_STOCK_QTY = 2.0
TEST_STOCK_NOTE = "ABIKAN PHARMACY CATALOGUE E2E TEST STOCK — not hospital inventory"


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


def find_drug_by_name(name: str) -> str | None:
    quoted = urllib.parse.quote(name)
    data = omrs(
        "GET",
        f"/openmrs/ws/rest/v1/drug?q={quoted}&v=custom:(uuid,display,name,retired)&limit=20",
    )
    rows = data.get("results") if isinstance(data, dict) else data
    needle = name.strip().lower()
    for row in rows or []:
        if row.get("retired"):
            continue
        display = (row.get("display") or row.get("name") or "").strip().lower()
        if display == needle:
            return row.get("uuid")
    return None


def create_drug(item: dict) -> str:
    name = item["createName"]
    existing = find_drug_by_name(name)
    if existing:
        return existing
    body = {
        "name": name,
        "concept": item["conceptUuid"],
        "combination": False,
        "dosageForm": item["dosageFormUuid"],
        "strength": item["strength"],
    }
    created = omrs("POST", "/openmrs/ws/rest/v1/drug", body)
    uuid = created.get("uuid") if isinstance(created, dict) else None
    if not uuid:
        raise RuntimeError(f"Could not create drug {name}")
    return uuid


def odoo():
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
    return currency_id


def ensure_pharmacy_pricelist(models, uid, currency_id: int) -> int:
    rows = kw(
        models,
        uid,
        "product.pricelist",
        "search_read",
        [[("name", "=", PRICELIST_NAME)]],
        {"fields": ["id", "currency_id"], "limit": 1},
    )
    if rows:
        pricelist_id = int(rows[0]["id"])
        kw(models, uid, "product.pricelist", "write", [[pricelist_id], {"currency_id": currency_id}])
        return pricelist_id
    return int(kw(models, uid, "product.pricelist", "create", [{"name": PRICELIST_NAME, "currency_id": currency_id}]))


def ensure_pharmacy_shop(models, uid, pricelist_id: int) -> None:
    shops = kw(models, uid, "sale.shop", "search_read", [[("name", "=", SHOP_NAME)]], {"fields": ["id", "pricelist_id"], "limit": 1})
    if not shops:
        raise RuntimeError("Pharmacy Counter shop is missing")
    kw(models, uid, "sale.shop", "write", [[int(shops[0]["id"])], {"pricelist_id": pricelist_id}])
    lab = kw(models, uid, "sale.shop", "search_read", [[("name", "=", "Laboratory")]], {"fields": ["id", "pricelist_id"], "limit": 1})
    if lab:
        lab_list = lab[0].get("pricelist_id") or [None, ""]
        lab_name = str(lab_list[1] or "")
        if "Hospital Laboratory" not in lab_name:
            raise RuntimeError("Laboratory shop pricelist changed unexpectedly; stopping")


def find_product(models, uid, drug_uuid: str) -> dict | None:
    found = kw(
        models,
        uid,
        "product.product",
        "search_read",
        [[("uuid", "=", drug_uuid)]],
        {"fields": ["id", "name", "list_price", "qty_available", "taxes_id"], "limit": 1, "context": {"active_test": False}},
    )
    return found[0] if found else None


def wait_for_product(models, uid, drug_uuid: str, name: str, timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = find_product(models, uid, drug_uuid)
        if found:
            return found
        time.sleep(5)
    raise RuntimeError(f"Odoo product not created yet for {name} ({drug_uuid})")


def set_development_price(models, uid, product: dict) -> None:
    name = str(product.get("name") or "")
    if "TEST" in name.upper() and "—" in name:
        raise RuntimeError(f"Refusing to change TEST product {name}")
    kw(
        models,
        uid,
        "product.product",
        "write",
        [
            [int(product["id"])],
            {
                "list_price": pharmacy_catalogue.DEVELOPMENT_PRICE_NGN,
                "taxes_id": [(6, 0, [])],
                "supplier_taxes_id": [(6, 0, [])],
            },
        ],
    )


def apply_test_stock(models, uid) -> str:
    product = find_product(models, uid, TEST_STOCK_DRUG_UUID)
    if not product:
        raise RuntimeError("Cetirizine product missing; cannot apply TEST stock")
    locs = kw(models, uid, "stock.location", "search_read", [[("complete_name", "=", "WH/Stock")]], {"fields": ["id"], "limit": 1})
    if not locs:
        raise RuntimeError("WH/Stock location missing")
    location_id = int(locs[0]["id"])
    quants = kw(
        models,
        uid,
        "stock.quant",
        "search_read",
        [[("product_id", "=", int(product["id"])), ("location_id", "=", location_id)]],
        {"fields": ["id", "quantity", "reserved_quantity"], "limit": 1},
    )
    on_hand = float(quants[0]["quantity"]) if quants else 0.0
    reserved = float(quants[0]["reserved_quantity"]) if quants else 0.0
    if on_hand > 0:
        return f"left existing on-hand {on_hand} (reserved {reserved}); did not import spreadsheet qty"
    values = {
        "product_id": int(product["id"]),
        "location_id": location_id,
        "inventory_quantity": TEST_STOCK_QTY,
    }
    if quants:
        quant_id = int(quants[0]["id"])
        kw(models, uid, "stock.quant", "write", [[quant_id], values])
    else:
        quant_id = int(kw(models, uid, "stock.quant", "create", [values]))
    try:
        kw(models, uid, "stock.quant", "action_apply_inventory", [[quant_id]])
    except xmlrpc.client.Fault as error:
        # Odoo returns None; XML-RPC cannot marshal it. The write may still have applied.
        if "cannot marshal None" not in str(error):
            raise
    after = kw(
        models,
        uid,
        "stock.quant",
        "search_read",
        [[("product_id", "=", int(product["id"])), ("location_id", "=", location_id)]],
        {"fields": ["quantity"], "limit": 1},
    )
    qty = float(after[0]["quantity"]) if after else 0.0
    if qty < TEST_STOCK_QTY:
        raise RuntimeError(f"TEST stock apply failed; on-hand is {qty}")
    return f"set {qty} on {product['name']} at WH/Stock ({TEST_STOCK_NOTE})"


def main() -> int:
    odoo_only = "--odoo-only" in sys.argv
    apply_stock = "--apply-test-stock" in sys.argv
    print("Configuring hospital pharmacy catalogue (development prices)…")
    runtime = pharmacy_catalogue.load_runtime()
    created = 0
    reused = 0
    skipped = 0

    if not odoo_only:
        for item in MAPPING["items"]:
            sn = str(item["sn"])
            action = item.get("action")
            if action == "skip":
                skipped += 1
                continue
            if action == "reuse":
                uuid = item["drugUuid"]
                found = omrs("GET", f"/openmrs/ws/rest/v1/drug/{uuid}?v=custom:(uuid,display,retired)")
                if not isinstance(found, dict) or not found.get("uuid"):
                    raise RuntimeError(f"Reuse drug missing for {sn}: {uuid}")
                if found.get("retired"):
                    raise RuntimeError(f"Reuse drug retired for {sn}: {uuid}")
                runtime[sn] = uuid
                reused += 1
                continue
            if action == "create":
                uuid = runtime.get(sn) or find_drug_by_name(item["createName"])
                if not uuid:
                    uuid = create_drug(item)
                    created += 1
                    print(f"  created {item['createName']} {uuid}")
                else:
                    reused += 1
                    print(f"  already present {item['createName']} {uuid}")
                runtime[sn] = uuid
                item["drugUuid"] = uuid
        try:
            pharmacy_catalogue.RUNTIME_PATH.write_text(json.dumps({"drugBySn": runtime}, indent=2), encoding="utf-8")
        except OSError as error:
            print(f"  warning: could not write runtime map ({error})")
    else:
        for item in MAPPING["items"]:
            sn = str(item["sn"])
            if item.get("action") == "skip":
                skipped += 1
                continue
            uuid = runtime.get(sn) or item.get("drugUuid")
            if uuid:
                item["drugUuid"] = uuid
                reused += 1

    uid, models = odoo()
    ngn_id = ensure_ngn(models, uid)
    pricelist_id = ensure_pharmacy_pricelist(models, uid, ngn_id)
    ensure_pharmacy_shop(models, uid, pricelist_id)

    priced = 0
    for item in MAPPING["items"]:
        if item.get("action") == "skip":
            continue
        uuid = item.get("drugUuid") or runtime.get(str(item["sn"]))
        if not uuid:
            raise RuntimeError(f"No drug uuid for hospital row {item['sn']}")
        if uuid in pharmacy_catalogue.TEST_DRUG_UUIDS:
            raise RuntimeError("Mapped item collided with a TEST drug")
        name = item.get("openmrsName") or item.get("createName")
        product = wait_for_product(models, uid, uuid, name)
        set_development_price(models, uid, product)
        priced += 1
        print(f"  priced {product['name']} {pharmacy_catalogue.PRICE_LABEL}")

    stock_note = "not applied"
    if apply_stock:
        stock_note = apply_test_stock(models, uid)
        print(f"  test stock: {stock_note}")

    print(
        f"Done. reused={reused} created={created} skipped={skipped} "
        f"odoo_prices={priced} pricelist={pricelist_id} stock={stock_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
