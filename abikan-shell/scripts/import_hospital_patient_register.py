#!/usr/bin/env python3
"""Replace the OpenMRS patient register with the hospital CSV export.

Intended for abikan-server (production) inside bahmni-standard-abikan-api-1:

  python3 import_hospital_patient_register.py /path/to/Patient\\ List\\ \\(2\\).csv

- Voids existing OpenMRS patients (does not delete clinical history rows)
- Ends active bed assignments
- Ends open visits for patients being voided (prevents ward leftovers)
- Voids open lab/drug/radiology orders for patients being voided
- Clears Hospital EMR Family Card memberships
- Creates person attribute type cardType when missing
- Imports patients with phone, address, death flag, and card type
- Groups * FAMILY guardian values onto shared Family Cards
- Rebuilds the patient search index so new hospital numbers appear in search
- Creates Odoo financial accounts (billing partners) for imported patients
"""

from __future__ import annotations

import argparse
import calendar
import csv
import os
import re
import sqlite3
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Prefer Hospital EMR API vendor copy of PyMySQL when running in-container.
_VENDOR = Path(__file__).resolve().parents[1] / "server" / "patient-account" / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
_APP_VENDOR = Path("/app/vendor")
if _APP_VENDOR.is_dir() and str(_APP_VENDOR) not in sys.path:
    sys.path.insert(0, str(_APP_VENDOR))

AS_OF = date(2026, 9, 8)
IDENTIFIER_TYPE_ID = 3  # Patient Identifier
REG_LOCATION_ID = 3  # Registration Desk
CREATOR = 1
VOID_REASON = "Hospital register replaced from Patient List CSV"
CARD_ATTR = "cardType"
PHONE_ATTR = "phoneNumber"


def _connect_openmrs():
    try:
        import pymysql
    except ImportError as error:  # pragma: no cover
        raise SystemExit("pymysql is required inside the Hospital EMR API container") from error
    return pymysql.connect(
        host=os.environ.get("ABIKAN_OPENMRS_DB_HOST", "openmrsdb"),
        port=int(os.environ.get("ABIKAN_OPENMRS_DB_PORT", "3306") or 3306),
        user=os.environ.get("ABIKAN_OPENMRS_DB_USER", "openmrs-user"),
        password=os.environ.get("ABIKAN_OPENMRS_DB_PASSWORD", ""),
        database=os.environ.get("ABIKAN_OPENMRS_DB_NAME", "openmrs"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )


def _audit_db() -> Path:
    return Path(os.environ.get("ABIKAN_ADMIN_AUDIT_DB") or "/var/lib/abikan/admin-audit.sqlite3")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clip(value: str, limit: int) -> str:
    text = _text(value)
    return text[:limit] if len(text) > limit else text


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", _text(value))


def subtract_ymd(as_of: date, years: int, months: int, days: int) -> date:
    year = as_of.year - years
    month = as_of.month - months
    day = as_of.day - days
    while month <= 0:
        month += 12
        year -= 1
    while day <= 0:
        month -= 1
        if month <= 0:
            month += 12
            year -= 1
        day += calendar.monthrange(year, month)[1]
    day = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def birthdate_from_age(age_text: str) -> date | None:
    years = months = days = 0
    found = False
    for part in (_text(age_text) or "").split(","):
        part = part.strip().lower()
        nums = re.findall(r"\d+", part)
        if not nums:
            continue
        found = True
        n = int(nums[0])
        if "year" in part:
            years = n
        elif "month" in part:
            months = n
        elif "day" in part:
            days = n
    if not found:
        return None
    # Some hospital rows stored a calendar birth year as "Year" (e.g. 2001 Year, 9 Month, 29 Day).
    if years > 120:
        month = months if 1 <= months <= 12 else 1
        day = days if days >= 1 else 1
        day = min(day, calendar.monthrange(years, month)[1])
        try:
            return date(years, month, day)
        except ValueError:
            return None
    return subtract_ymd(AS_OF, years, months, days)


def parse_name(raw: str) -> tuple[str, str, str]:
    name = re.sub(r"\s*\(\d+\)\s*$", "", _normalize_spaces(raw))
    parts = [p for p in name.split(" ") if p]
    if not parts:
        return "Unknown", "Patient", ""
    if len(parts) == 1:
        return parts[0], parts[0], ""
    family = parts[0]
    given = parts[1]
    middle = " ".join(parts[2:]) if len(parts) > 2 else ""
    return family, given, middle


def parse_gender(raw: str) -> str:
    key = _text(raw).casefold()
    if key.startswith("m"):
        return "M"
    if key.startswith("f"):
        return "F"
    return ""  # missing → empty / display as —


def parse_card(guardian: str) -> tuple[str | None, str | None]:
    """Return (card_type, family_name_hint).

    card_type is 'family', 'individual', or None when unknown / no card.
    """
    text = _normalize_spaces(guardian)
    upper = text.upper()
    if not upper:
        return None, None
    if "INDIVIDUAL" in upper:
        return "individual", None
    if "FAMILY" in upper and "CARD" in upper:
        return "family", None
    if upper.endswith(" FAMILY") or upper == "FAMILY" or re.search(r"\bFAMILY$", upper):
        # e.g. ALADE FAMILY — treat as Family Card household name
        return "family", text.title() if text != text.upper() else text
    if upper in {"NO CARD", "NOCARD", "NIL", "NONE", "N/A", "NA", "0", "NULL"}:
        return None, None
    # Schemes / folders / free text — leave card type blank
    return None, None


def load_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader, start=1):
            family, given, middle = parse_name(raw.get("Patient Name") or "")
            card_type, family_hint = parse_card(raw.get("Guardian Name") or "")
            if card_type == "family" and not family_hint:
                family_hint = f"{family} Family"
            gender = parse_gender(raw.get("Gender") or "")
            birth = birthdate_from_age(raw.get("Age") or "")
            dead = _text(raw.get("Dead")).casefold().startswith("y")
            rows.append(
                {
                    "index": index,
                    "family_name": _clip(family, 50),
                    "given_name": _clip(given, 50),
                    "middle_name": _clip(middle, 50),
                    "gender": gender,
                    "birthdate": birth,
                    "phone": _clip(raw.get("Phone") or "", 50),
                    "address": _clip(raw.get("Address") or "", 255),
                    "dead": dead,
                    "card_type": card_type,
                    "family_hint": family_hint,
                    "display": _normalize_spaces(
                        re.sub(r"\s*\(\d+\)\s*$", "", raw.get("Patient Name") or "")
                    ),
                }
            )
    return rows


def ensure_card_attr(cursor) -> int:
    cursor.execute(
        "SELECT person_attribute_type_id FROM person_attribute_type "
        "WHERE name=%s AND retired=0 LIMIT 1",
        (CARD_ATTR,),
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])
    attr_uuid = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO person_attribute_type (
          name, description, format, foreign_key, searchable, creator, date_created,
          retired, uuid, sort_weight
        ) VALUES (%s, %s, %s, NULL, 1, %s, NOW(), 0, %s, 12)
        """,
        (
            CARD_ATTR,
            "Hospital card type: family or individual",
            "java.lang.String",
            CREATOR,
            attr_uuid,
        ),
    )
    return int(cursor.lastrowid)


def phone_attr_id(cursor) -> int | None:
    cursor.execute(
        "SELECT person_attribute_type_id FROM person_attribute_type "
        "WHERE name=%s AND retired=0 LIMIT 1",
        (PHONE_ATTR,),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def clear_register(cursor) -> dict[str, int]:
    cursor.execute("SELECT COUNT(*) FROM patient WHERE voided=0")
    before = int(cursor.fetchone()[0])
    cursor.execute(
        """
        UPDATE bed_patient_assignment_map
        SET date_stopped = NOW()
        WHERE date_stopped IS NULL
        """
    )
    beds = cursor.rowcount
    # Free bed status when module tracks occupancy on bed table
    try:
        cursor.execute(
            """
            UPDATE bed b
            JOIN bed_patient_assignment_map m ON m.bed_id = b.bed_id
            SET b.status = 'AVAILABLE'
            WHERE m.date_stopped IS NOT NULL
              AND b.status = 'OCCUPIED'
              AND NOT EXISTS (
                SELECT 1 FROM bed_patient_assignment_map live
                WHERE live.bed_id = b.bed_id AND live.date_stopped IS NULL
              )
            """
        )
    except Exception:
        pass
    # Close leftover open visits before voiding patients so Nursing/Lab/Pharmacy
    # desks do not keep showing old register stays.
    cursor.execute(
        """
        UPDATE visit v
        JOIN patient p ON p.patient_id = v.patient_id
        SET v.date_stopped = UTC_TIMESTAMP()
        WHERE p.voided = 0
          AND v.voided = 0
          AND v.date_stopped IS NULL
        """
    )
    visits_stopped = cursor.rowcount
    cursor.execute(
        """
        UPDATE orders o
        JOIN patient p ON p.patient_id = o.patient_id
        SET
          o.voided = 1,
          o.voided_by = %s,
          o.date_voided = UTC_TIMESTAMP(),
          o.void_reason = %s
        WHERE p.voided = 0
          AND o.voided = 0
        """,
        (CREATOR, VOID_REASON),
    )
    orders_voided = cursor.rowcount
    cursor.execute(
        """
        UPDATE patient p
        JOIN person per ON per.person_id = p.patient_id
        SET
          p.voided = 1,
          p.voided_by = %s,
          p.date_voided = NOW(),
          p.void_reason = %s,
          per.voided = 1,
          per.voided_by = %s,
          per.date_voided = NOW(),
          per.void_reason = %s
        WHERE p.voided = 0
        """,
        (CREATOR, VOID_REASON, CREATOR, VOID_REASON),
    )
    voided = cursor.rowcount
    return {
        "before": before,
        "voided": voided,
        "beds_stopped": beds,
        "visits_stopped": visits_stopped,
        "orders_voided": orders_voided,
    }


def rebuild_patient_search_index() -> bool:
    """Ask OpenMRS to rebuild Lucene patient search after a SQL register replace."""
    import base64
    import urllib.error
    import urllib.request

    base = (os.environ.get("ABIKAN_OPENMRS_URL") or "http://openmrs:8080").rstrip("/")
    user = os.environ.get("ABIKAN_OPENMRS_ADMIN_USER") or ""
    password = os.environ.get("ABIKAN_OPENMRS_ADMIN_PASSWORD") or ""
    if not user or not password:
        print("search_index_rebuild skipped: missing OpenMRS admin credentials", file=sys.stderr)
        return False
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(
        f"{base}/openmrs/ws/rest/v1/searchindexupdate",
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            print(f"search_index_rebuild status={response.status}")
            return 200 <= int(response.status) < 300 or int(response.status) == 204
    except urllib.error.HTTPError as error:
        print(f"search_index_rebuild failed status={error.code}", file=sys.stderr)
        return False
    except Exception as error:  # pragma: no cover
        print(f"search_index_rebuild failed: {error}", file=sys.stderr)
        return False


def clear_families() -> None:
    path = _audit_db()
    if not path.exists():
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM hospital_family_event")
        conn.execute("DELETE FROM hospital_family_member")
        conn.execute("DELETE FROM hospital_family")
        conn.commit()
    finally:
        conn.close()


def next_identifier_start(cursor) -> int:
    cursor.execute("SELECT next_sequence_value FROM idgen_seq_id_gen WHERE id=1")
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 200064


def set_identifier_sequence(cursor, next_value: int) -> None:
    cursor.execute(
        "UPDATE idgen_seq_id_gen SET next_sequence_value=%s WHERE id=1",
        (next_value,),
    )


def insert_patients(cursor, rows: list[dict[str, Any]], card_type_id: int, phone_type_id: int | None) -> list[dict[str, Any]]:
    start = next_identifier_start(cursor)
    created: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for offset, row in enumerate(rows):
        person_uuid = str(uuid.uuid4())
        name_uuid = str(uuid.uuid4())
        ident_uuid = str(uuid.uuid4())
        seq = start + offset
        identifier = f"ABC{seq}"
        gender = row["gender"] or None
        birth = row["birthdate"]
        dead = 1 if row["dead"] else 0
        death_date = now if row["dead"] else None
        cursor.execute(
            """
            INSERT INTO person (
              gender, birthdate, birthdate_estimated, dead, death_date,
              creator, date_created, voided, uuid, deathdate_estimated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, 0)
            """,
            (
                gender,
                birth,
                1 if birth else 0,
                dead,
                death_date,
                CREATOR,
                now,
                person_uuid,
            ),
        )
        person_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO patient (patient_id, creator, date_created, voided, allergy_status)
            VALUES (%s, %s, %s, 0, 'Unknown')
            """,
            (person_id, CREATOR, now),
        )
        cursor.execute(
            """
            INSERT INTO person_name (
              preferred, person_id, given_name, middle_name, family_name,
              creator, date_created, voided, uuid
            ) VALUES (1, %s, %s, %s, %s, %s, %s, 0, %s)
            """,
            (
                person_id,
                row["given_name"] or "Unknown",
                row["middle_name"] or None,
                row["family_name"] or "Unknown",
                CREATOR,
                now,
                name_uuid,
            ),
        )
        cursor.execute(
            """
            INSERT INTO patient_identifier (
              patient_id, identifier, identifier_type, preferred, location_id,
              creator, date_created, voided, uuid
            ) VALUES (%s, %s, %s, 1, %s, %s, %s, 0, %s)
            """,
            (
                person_id,
                identifier,
                IDENTIFIER_TYPE_ID,
                REG_LOCATION_ID,
                CREATOR,
                now,
                ident_uuid,
            ),
        )
        if row["phone"] and phone_type_id:
            cursor.execute(
                """
                INSERT INTO person_attribute (
                  person_id, value, person_attribute_type_id, creator, date_created, voided, uuid
                ) VALUES (%s, %s, %s, %s, %s, 0, %s)
                """,
                (person_id, row["phone"], phone_type_id, CREATOR, now, str(uuid.uuid4())),
            )
        if row["card_type"]:
            cursor.execute(
                """
                INSERT INTO person_attribute (
                  person_id, value, person_attribute_type_id, creator, date_created, voided, uuid
                ) VALUES (%s, %s, %s, %s, %s, 0, %s)
                """,
                (
                    person_id,
                    row["card_type"],
                    card_type_id,
                    CREATOR,
                    now,
                    str(uuid.uuid4()),
                ),
            )
        if row["address"]:
            cursor.execute(
                """
                INSERT INTO person_address (
                  person_id, preferred, address1, creator, date_created, voided, uuid
                ) VALUES (%s, 1, %s, %s, %s, 0, %s)
                """,
                (person_id, row["address"], CREATOR, now, str(uuid.uuid4())),
            )
        created.append(
            {
                **row,
                "uuid": person_uuid,
                "identifier": identifier,
                "person_id": person_id,
            }
        )
    set_identifier_sequence(cursor, start + len(rows))
    return created


def rebuild_families(created: list[dict[str, Any]]) -> int:
    path = _audit_db()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # Ensure tables exist (same schema as hospital_family.py)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hospital_family (
                family_id TEXT PRIMARY KEY,
                card_number TEXT NOT NULL UNIQUE,
                family_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by_uuid TEXT NOT NULL,
                created_by_username TEXT NOT NULL,
                created_by_display TEXT NOT NULL,
                fee_status TEXT NOT NULL CHECK (fee_status IN ('pending', 'billed')),
                fee_patient_uuid TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS hospital_family_member (
                patient_uuid TEXT PRIMARY KEY,
                family_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                member_name TEXT NOT NULL DEFAULT '',
                member_identifier TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL,
                linked_by_username TEXT NOT NULL,
                FOREIGN KEY (family_id) REFERENCES hospital_family(family_id)
            );
            """
        )
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in created:
            if row.get("card_type") != "family":
                continue
            hint = _normalize_spaces(row.get("family_hint") or "")
            if not hint:
                continue
            key = hint.casefold()
            groups[key].append(row)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        card_seq = 1
        families = 0
        for _key, members in groups.items():
            family_name = members[0]["family_hint"]
            family_id = uuid.uuid4().hex
            card_number = f"FAM-{card_seq:03d}"
            card_seq += 1
            first = members[0]
            conn.execute(
                """
                INSERT INTO hospital_family (
                    family_id, card_number, family_name, created_at,
                    created_by_uuid, created_by_username, created_by_display,
                    fee_status, fee_patient_uuid, archived
                ) VALUES (?, ?, ?, ?, '', 'import', 'Hospital import', 'billed', ?, 0)
                """,
                (family_id, card_number, family_name, now, first["uuid"]),
            )
            for member in members:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO hospital_family_member (
                        patient_uuid, family_id, relationship, member_name,
                        member_identifier, linked_at, linked_by_username
                    ) VALUES (?, ?, 'Family member', ?, ?, ?, 'import')
                    """,
                    (
                        member["uuid"],
                        family_id,
                        member["display"],
                        member["identifier"],
                        now,
                    ),
                )
            families += 1
        conn.commit()
        return families
    finally:
        conn.close()


def sync_odoo_partners(created: list[dict[str, Any]]) -> dict[str, Any]:
    """Create Odoo billing partners for SQL-imported patients (atomfeed was bypassed)."""
    import xmlrpc.client

    url = (os.environ.get("ABIKAN_ODOO_URL") or "http://odoo:8069").rstrip("/")
    db = os.environ.get("ABIKAN_ODOO_DB") or "odoo"
    user = os.environ.get("ABIKAN_ODOO_USER") or "abikan_odoo"
    password = os.environ.get("ABIKAN_ODOO_PASSWORD") or ""
    if not password:
        print("odoo_partner_sync skipped: missing Odoo password", file=sys.stderr)
        return {"created": 0, "errors": 0, "skipped": True}
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, password, {})
    if not uid:
        print("odoo_partner_sync skipped: Odoo authentication failed", file=sys.stderr)
        return {"created": 0, "errors": 0, "skipped": True}
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    have = {
        str(row.get("uuid") or "")
        for row in models.execute_kw(
            db,
            uid,
            password,
            "res.partner",
            "search_read",
            [[("uuid", "!=", False)]],
            {"fields": ["uuid"], "limit": 200000},
        )
        if row.get("uuid")
    }
    made = 0
    errors = 0
    for row in created:
        uuid = str(row.get("uuid") or "")
        if not uuid or uuid in have:
            continue
        name = " ".join(str(row.get("display") or row.get("identifier") or uuid).split()).strip()[:128]
        try:
            models.execute_kw(
                db,
                uid,
                password,
                "res.partner",
                "create",
                [
                    {
                        "name": name or row["identifier"],
                        "ref": row["identifier"],
                        "uuid": uuid,
                        "customer_rank": 1,
                        "company_type": "person",
                        "is_company": False,
                    }
                ],
            )
            made += 1
            have.add(uuid)
        except Exception as error:  # pragma: no cover
            errors += 1
            if errors <= 5:
                print(f"odoo_partner_sync failed for {row.get('identifier')}: {error}", file=sys.stderr)
    return {"created": made, "errors": errors, "skipped": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}", file=sys.stderr)
        return 1

    rows = load_csv(args.csv_path)
    card_counts = defaultdict(int)
    for row in rows:
        card_counts[row["card_type"] or "null"] += 1
    print(f"csv_rows={len(rows)} card_types={dict(card_counts)}")
    if args.dry_run:
        print("dry-run only")
        return 0

    clear_families()
    print("cleared_family_cards")

    conn = _connect_openmrs()
    try:
        with conn.cursor() as cursor:
            stats = clear_register(cursor)
            print("cleared_patients", stats)
            card_type_id = ensure_card_attr(cursor)
            phone_type_id = phone_attr_id(cursor)
            print("cardType_attr_id", card_type_id, "phone_attr_id", phone_type_id)
            created = insert_patients(cursor, rows, card_type_id, phone_type_id)
            print(f"imported={len(created)} first={created[0]['identifier']} last={created[-1]['identifier']}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    families = rebuild_families(created)
    print(f"family_cards={families}")
    partner_stats = sync_odoo_partners(created)
    print(f"odoo_partners={partner_stats}")
    if partner_stats.get("errors"):
        print(
            "WARNING: some financial accounts were not created. "
            "Run sync_openmrs_patients_to_odoo_partners.py to finish.",
            file=sys.stderr,
        )
    if not rebuild_patient_search_index():
        print(
            "WARNING: patient search index was not rebuilt. "
            "New hospital numbers may be missing from top search until rebuild succeeds.",
            file=sys.stderr,
        )
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
