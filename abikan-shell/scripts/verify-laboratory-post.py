#!/usr/bin/env python3
"""Post-implementation laboratory verification. Read-only except optional documented writes."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
import xmlrpc.client
from collections import Counter
from pathlib import Path

from script_config import required_environment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "patient-account"))
if Path("/app/lab_catalogue.py").exists():
    sys.path.insert(0, "/app")

import lab_catalogue  # noqa: E402

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "http://openmrs:8080").rstrip("/")
ADMIN_USER = required_environment("ABIKAN_ADMIN_USER")
ADMIN_PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
ODOO_URL = os.environ.get("ABIKAN_ODOO_URL", "http://odoo:8069").rstrip("/")
ODOO_DB = os.environ.get("ABIKAN_ODOO_DB", "odoo")
ODOO_USER = required_environment("ABIKAN_ODOO_USER")
ODOO_PASSWORD = required_environment("ABIKAN_ODOO_PASSWORD")
CTX = ssl._create_unverified_context()
ALL_SET = "d3e6fb5f-5e07-11ef-8f7c-0242ac120002"
TEST_CLASS = "8d4907b2-c2cc-11de-8d13-0010c6dffd0f"
LABSET_CLASS = "8d492026-c2cc-11de-8d13-0010c6dffd0f"
NA_TYPE = "8d4a4c94-c2cc-11de-8d13-0010c6dffd0f"


def admin_headers() -> dict[str, str]:
    import base64

    token = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def omrs(path: str):
    req = urllib.request.Request(f"{BASE}{path}", headers=admin_headers())
    with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


def odoo():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


def kw(models, uid, model, method, args, kwargs=None):
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, model, method, args, kwargs or {})


def main() -> int:
    mapping = lab_catalogue.load_map()
    runtime = lab_catalogue.load_runtime()
    csv_rows = lab_catalogue.load_csv_rows()
    entries = lab_catalogue.catalogue_entries()
    orderable = lab_catalogue.orderable_entries()
    actions = Counter(row["action"] for row in entries)
    report: dict = {
        "csv_rows": len(csv_rows),
        "map_items": len(mapping["items"]),
        "runtime_keys": len(runtime),
        "actions": dict(actions),
        "orderable": len(orderable),
        "outsourced": sum(1 for row in orderable if row.get("outsourced")),
        "skips": [row["sn"] for row in entries if row["action"] == "skip"],
        "skip_notes": {row["sn"]: row.get("note") for row in entries if row["action"] == "skip"},
        "missing_uuid": [row["sn"] for row in entries if row["action"] != "skip" and not row.get("conceptUuid")],
        "missing_price": [row["sn"] for row in orderable if not row.get("priceNgn")],
        "placeholder_csv": [row["sn"] for row in orderable if (row.get("priceNgn") or 0) <= 1.01],
    }

    uuids = [row["conceptUuid"] for row in orderable]
    report["duplicate_uuids"] = [u for u, n in Counter(uuids).items() if n > 1]
    report["duplicate_sns"] = [s for s, n in Counter(row["sn"] for row in entries).items() if n > 1]

    created = [row for row in entries if row["action"] == "create"]
    report["create_rows"] = len(created)
    report["create_names"] = [row.get("createName") or row.get("hospitalName") for row in created]

    # Live OpenMRS All_Tests_and_Panels
    panel = omrs(
        f"/openmrs/ws/rest/v1/concept/{ALL_SET}?v=custom:(uuid,display,set,setMembers:(uuid,display,retired,conceptClass:(display),datatype:(display)))"
    )
    members = panel.get("setMembers") or []
    member_uuids = [m.get("uuid") for m in members]
    report["all_tests_display"] = panel.get("display")
    report["all_tests_count"] = len(members)
    intended = sorted(set(uuids))
    actual = sorted(set(member_uuids))
    report["all_tests_extra"] = sorted(set(actual) - set(intended))
    report["all_tests_missing"] = sorted(set(intended) - set(actual))

    created_live = []
    for row in created:
        uuid = row.get("conceptUuid")
        if not uuid:
            continue
        concept = omrs(
            f"/openmrs/ws/rest/v1/concept/{uuid}?v=custom:(uuid,display,retired,set,datatype:(display,uuid),conceptClass:(display,uuid),setMembers:(uuid,display))"
        )
        created_live.append(
            {
                "sn": row["sn"],
                "name": concept.get("display"),
                "retired": concept.get("retired"),
                "class": (concept.get("conceptClass") or {}).get("display"),
                "classUuid": (concept.get("conceptClass") or {}).get("uuid"),
                "datatype": (concept.get("datatype") or {}).get("display"),
                "datatypeUuid": (concept.get("datatype") or {}).get("uuid"),
                "set": concept.get("set"),
                "members": [m.get("display") for m in (concept.get("setMembers") or [])],
                "expectedClass": row.get("conceptClass"),
            }
        )
    report["created_live"] = created_live
    report["created_class_mismatch"] = [
        c for c in created_live if c["expectedClass"] and c["class"] != c["expectedClass"]
    ]
    report["created_not_na"] = [c for c in created_live if c["datatypeUuid"] != NA_TYPE]
    report["created_retired"] = [c for c in created_live if c["retired"]]

    # Representative prices vs Odoo
    uid, models = odoo()
    samples = [
        ("2", "PCV cheap"),
        ("1", "FBC panel"),
        ("8", "Clotting outsourced panel"),
        ("16", "Microscopy MP in-house"),
        ("71", "IGF-1 expensive outsourced"),
        ("46", "Urine Toxicology outsourced"),
    ]
    price_rows = []
    for sn, label in samples:
        entry = next(row for row in entries if row["sn"] == sn)
        uuid = entry["conceptUuid"]
        found = kw(
            models,
            uid,
            "product.product",
            "search_read",
            [[("uuid", "=", uuid)]],
            {"fields": ["id", "name", "list_price", "uuid", "default_code", "categ_id"], "limit": 3},
        )
        hospital = [p for p in found if " — TEST" not in (p.get("name") or "")]
        product = hospital[0] if hospital else (found[0] if found else {})
        price_rows.append(
            {
                "label": label,
                "sn": sn,
                "csv": entry.get("priceNgn"),
                "odoo_name": product.get("name"),
                "odoo_price": product.get("list_price"),
                "match": abs(float(product.get("list_price") or 0) - float(entry.get("priceNgn") or -1)) < 0.01,
                "usd_name": "USD" in str(product.get("name") or "").upper(),
                "placeholder": float(product.get("list_price") or 0) <= 1.01,
            }
        )
    report["price_samples"] = price_rows

    pricelists = kw(
        models,
        uid,
        "product.pricelist",
        "search_read",
        [[("name", "=", "Hospital Laboratory")]],
        {"fields": ["id", "name", "currency_id"], "limit": 1},
    )
    report["pricelist"] = pricelists[0] if pricelists else None

    placeholder_products = kw(
        models,
        uid,
        "product.product",
        "search_read",
        [[("uuid", "in", intended), ("list_price", "<=", 1.01)]],
        {"fields": ["id", "name", "list_price", "uuid"], "limit": 20},
    )
    report["placeholder_odoo_hospital_uuid"] = [
        p for p in placeholder_products if " — TEST" not in (p.get("name") or "")
    ]

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
