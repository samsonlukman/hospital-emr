#!/usr/bin/env python3
"""Create missing Odoo financial accounts for active OpenMRS patients.

Use after a SQL hospital register replace that bypassed patient atomfeed.

  python3 sync_openmrs_patients_to_odoo_partners.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

_VENDOR = __import__("pathlib").Path(__file__).resolve().parents[1] / "server" / "patient-account" / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
_APP_VENDOR = __import__("pathlib").Path("/app/vendor")
if _APP_VENDOR.is_dir() and str(_APP_VENDOR) not in sys.path:
    sys.path.insert(0, str(_APP_VENDOR))


def _connect_openmrs():
    import pymysql

    return pymysql.connect(
        host=os.environ.get("ABIKAN_OPENMRS_DB_HOST", "openmrsdb"),
        port=int(os.environ.get("ABIKAN_OPENMRS_DB_PORT", "3306") or 3306),
        user=os.environ.get("ABIKAN_OPENMRS_DB_USER", "openmrs-user"),
        password=os.environ.get("ABIKAN_OPENMRS_DB_PASSWORD", ""),
        database=os.environ.get("ABIKAN_OPENMRS_DB_NAME", "openmrs"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
    )


def _odoo():
    import xmlrpc.client

    url = (os.environ.get("ABIKAN_ODOO_URL") or "http://odoo:8069").rstrip("/")
    db = os.environ.get("ABIKAN_ODOO_DB") or "odoo"
    user = os.environ.get("ABIKAN_ODOO_USER") or "abikan_odoo"
    password = os.environ.get("ABIKAN_ODOO_PASSWORD") or ""
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, password, {})
    if not uid:
        raise SystemExit("Odoo authentication failed")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return db, uid, password, models


def load_active_patients() -> list[dict[str, str]]:
    conn = _connect_openmrs()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT per.uuid,
                       pi.identifier,
                       TRIM(CONCAT(IFNULL(pn.given_name,''),' ',IFNULL(pn.family_name,'')))
                FROM patient p
                JOIN person per ON per.person_id=p.patient_id
                JOIN patient_identifier pi
                  ON pi.patient_id=p.patient_id AND pi.preferred=1 AND pi.voided=0
                JOIN person_name pn
                  ON pn.person_id=p.patient_id AND pn.preferred=1 AND pn.voided=0
                WHERE p.voided=0 AND per.voided=0
                ORDER BY p.patient_id
                """
            )
            rows = []
            for uuid, ident, name in cursor.fetchall():
                clean = " ".join(str(name or ident or "").split()).strip() or str(ident)
                rows.append({"uuid": str(uuid), "ref": str(ident), "name": clean[:128]})
            return rows
    finally:
        conn.close()


def sync_partners(patients: list[dict[str, str]]) -> dict[str, Any]:
    db, uid, password, models = _odoo()
    have: set[str] = set()
    for row in models.execute_kw(
        db,
        uid,
        password,
        "res.partner",
        "search_read",
        [[("uuid", "!=", False)]],
        {"fields": ["uuid"], "limit": 200000},
    ):
        if row.get("uuid"):
            have.add(str(row["uuid"]))
    missing = [row for row in patients if row["uuid"] not in have]
    created = 0
    errors = 0
    for row in missing:
        try:
            models.execute_kw(
                db,
                uid,
                password,
                "res.partner",
                "create",
                [
                    {
                        "name": row["name"] or row["ref"],
                        "ref": row["ref"],
                        "uuid": row["uuid"],
                        "customer_rank": 1,
                        "company_type": "person",
                        "is_company": False,
                    }
                ],
            )
            created += 1
        except Exception as error:  # pragma: no cover
            errors += 1
            if errors <= 5:
                print(f"partner_create_failed ref={row['ref']}: {error}", file=sys.stderr)
    return {"active_patients": len(patients), "missing": len(missing), "created": created, "errors": errors}


def main() -> int:
    patients = load_active_patients()
    print(f"active_patients={len(patients)}")
    stats = sync_partners(patients)
    print(json.dumps(stats))
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
