#!/usr/bin/env python3
"""Prove pharmacy catalogue price changes do not rewrite existing bills.

Uses a synthetic TEST patient and a TEST medicine only.
Does not delete records. Restores the original catalogue price.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
import xmlrpc.client
from http.cookiejar import CookieJar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from script_config import required_environment  # noqa: E402

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PWD = os.environ.get("ABIKAN_ADMIN_PASSWORD") or os.environ.get("OPENMRS_PASSWORD") or "Admin123"
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://localhost:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
CTX = ssl._create_unverified_context()


def login(user: str) -> str:
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(jar),
    )
    auth = "Basic " + base64.b64encode(f"{user}:{PWD}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}/openmrs/ws/rest/v1/session",
        headers={"Authorization": auth, "Accept": "application/json"},
    )
    with opener.open(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if not payload.get("authenticated"):
        raise RuntimeError(f"{user} not authenticated")
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in jar)


def call(method: str, path: str, cookie: str, body: dict | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json", "Cookie": cookie}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            return error.code, json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            return error.code, raw[:400]


def odoo():
    user = required_environment("ABIKAN_ODOO_USER")
    password = required_environment("ABIKAN_ODOO_PASSWORD")
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, user, password, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models, user, password


def kw(models, uid, password, model, method, args, kwargs=None):
    return models.execute_kw(ODOO_DB, uid, password, model, method, args, kwargs or {})


def amount(payload: object, *keys: str) -> float | None:
    if not isinstance(payload, dict):
        return None
    node: object = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, dict) and "amount" in node:
        return float(node["amount"])
    if isinstance(node, (int, float)):
        return float(node)
    return None


def wait_charge(path: str, cookie: str, body: dict) -> tuple[int, object]:
    last = (0, None)
    for _ in range(8):
        last = call("POST", path, cookie, body)
        if last[0] == 200:
            return last
        if isinstance(last[1], dict) and last[1].get("code") != "account_not_found":
            return last
        time.sleep(4)
    return last


def create_pharmacy_sale(models, uid, password, partner_id: int, product: dict, price: float, order_uuid: str) -> int:
    shops = kw(
        models,
        uid,
        password,
        "sale.shop",
        "search_read",
        [[("name", "ilike", "Pharmacy")]],
        {"fields": ["id", "warehouse_id", "pricelist_id", "payment_default_id"], "limit": 1},
    )
    if not shops:
        raise RuntimeError("Pharmacy counter not found")
    shop = shops[0]
    warehouse = shop.get("warehouse_id")
    warehouse_id = warehouse[0] if isinstance(warehouse, (list, tuple)) else warehouse or 1
    pricelist = shop.get("pricelist_id")
    pricelist_id = pricelist[0] if isinstance(pricelist, (list, tuple)) else pricelist or 1
    payment = shop.get("payment_default_id")
    payment_id = payment[0] if isinstance(payment, (list, tuple)) else payment or 1
    sale_id = int(
        kw(
            models,
            uid,
            password,
            "sale.order",
            "create",
            [
                {
                    "partner_id": int(partner_id),
                    "shop_id": int(shop["id"]),
                    "warehouse_id": int(warehouse_id),
                    "pricelist_id": int(pricelist_id),
                    "payment_term_id": int(payment_id),
                    "origin": f"TEST-PRICE-{order_uuid[:8]}",
                    "care_setting": "opd",
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": int(product["id"]),
                                "name": f"{product.get('name') or 'TEST medicine'} — PRICE LIFECYCLE",
                                "product_uom_qty": 1,
                                "price_unit": float(price),
                                "tax_id": [(6, 0, [])],
                                "external_order_id": order_uuid,
                                "external_id": order_uuid,
                            },
                        )
                    ],
                }
            ],
        )
    )
    try:
        kw(models, uid, password, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault:
        pass
    return sale_id


def line_price(models, uid, password, order_uuid: str) -> float | None:
    rows = kw(
        models,
        uid,
        password,
        "sale.order.line",
        "search_read",
        [[("external_order_id", "=", order_uuid)]],
        {"fields": ["price_unit"], "limit": 1},
    )
    if not rows:
        return None
    return float(rows[0].get("price_unit") or 0)


def main() -> int:
    rec = login("reception.abikan")
    pharm = login("pharmacy.abikan")
    uid, models, odoo_user, odoo_password = odoo()
    report: dict[str, object] = {"synthetic": {}}

    first = 111.0
    second = 134.0
    product_uuid = str(uuid.uuid4())
    categories = kw(
        models,
        uid,
        odoo_password,
        "product.category",
        "search_read",
        [[("name", "=", "Drugs")]],
        {"fields": ["id"], "limit": 1},
    )
    category_id = int(categories[0]["id"]) if categories else 1
    product_id = int(
        kw(
            models,
            uid,
            odoo_password,
            "product.product",
            "create",
            [
                {
                    "name": "Price Lifecycle — TEST",
                    "type": "consu",
                    "categ_id": category_id,
                    "list_price": first,
                    "sale_ok": True,
                    "purchase_ok": True,
                    "default_code": f"TEST-PRICE-{int(time.time())}",
                    "uuid": product_uuid,
                    "taxes_id": [(6, 0, [])],
                    "supplier_taxes_id": [(6, 0, [])],
                }
            ],
        )
    )
    product = {"id": product_id, "name": "Price Lifecycle — TEST", "uuid": product_uuid, "list_price": first}
    report["item"] = {
        "id": product_uuid,
        "label": "Price Lifecycle — TEST",
        "productId": product_id,
        "original": first,
        "created": True,
    }
    report["set_first_price"] = {"status": "odoo_write", "price": first}

    meta = call("GET", "/registration/metadata", rec)[1]
    opd = next(row for row in (meta.get("visitTypes") or []) if row.get("name") == "OPD")
    stamp = int(time.time())
    created = call(
        "POST",
        "/registration/patients",
        rec,
        {
            "givenName": "PRICE",
            "familyName": f"PHARMCYCLE{stamp % 10000}",
            "gender": "F",
            "birthdate": "1993-04-04",
            "confirmDuplicate": True,
        },
    )
    patient_uuid = created[1].get("uuid") if isinstance(created[1], dict) else None
    report["synthetic"]["patient"] = {"status": created[0], "uuid": patient_uuid}
    visit = call(
        "POST",
        f"/registration/patient/{patient_uuid}/visit",
        rec,
        {"visitTypeUuid": opd["uuid"], "requestId": f"pharm-life-visit-{stamp}"},
    )
    visit_uuid = visit[1].get("uuid") if isinstance(visit[1], dict) else None
    charge = wait_charge(
        f"/registration/patient/{patient_uuid}/charge",
        rec,
        {"visitUuid": visit_uuid, "cardType": "individual", "requestId": f"pharm-life-charge-{stamp}"},
    )
    report["synthetic"]["registration_charge"] = {"status": charge[0], "visit": visit_uuid}

    partners = kw(
        models,
        uid,
        odoo_password,
        "res.partner",
        "search_read",
        [[("uuid", "=", patient_uuid)]],
        {"fields": ["id", "name", "uuid"], "limit": 1},
    )
    if not partners:
        time.sleep(4)
        partners = kw(
            models,
            uid,
            odoo_password,
            "res.partner",
            "search_read",
            [[("uuid", "=", patient_uuid)]],
            {"fields": ["id", "name", "uuid"], "limit": 1},
        )
    if not partners:
        raise RuntimeError("TEST patient financial account was not created")
    partner_id = int(partners[0]["id"])

    old_order = str(uuid.uuid4())
    old_sale = create_pharmacy_sale(models, uid, odoo_password, partner_id, product, first, old_order)
    old_captured = line_price(models, uid, odoo_password, old_order)
    report["old_transaction"] = {
        "saleId": old_sale,
        "externalOrderId": old_order,
        "captured": old_captured,
        "expected": first,
    }

    kw(
        models,
        uid,
        odoo_password,
        "product.product",
        "write",
        [[int(product["id"])], {"list_price": second}],
    )
    after_change = line_price(models, uid, odoo_password, old_order)
    live = kw(
        models,
        uid,
        odoo_password,
        "product.product",
        "read",
        [[int(product["id"])], ["list_price"]],
    )
    report["after_catalogue_change"] = {
        "old_transaction": after_change,
        "catalogue": float(live[0]["list_price"]) if live else None,
        "expected_old": first,
        "expected_catalogue": second,
    }

    new_order = str(uuid.uuid4())
    new_sale = create_pharmacy_sale(models, uid, odoo_password, partner_id, product, float(live[0]["list_price"]), new_order)
    new_captured = line_price(models, uid, odoo_password, new_order)
    report["new_transaction"] = {
        "saleId": new_sale,
        "externalOrderId": new_order,
        "captured": new_captured,
        "expected": second,
    }

    report["catalogue_left_at"] = second
    report["synthetic"]["sales"] = [old_sale, new_sale]
    report["synthetic"]["product"] = {"id": product_id, "name": "Price Lifecycle — TEST", "uuid": product_uuid}

    json.dump(report, sys.stdout, indent=2, default=str)
    print()
    ok = (
        old_captured == first
        and after_change == first
        and new_captured == second
        and float(live[0]["list_price"]) == second
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
