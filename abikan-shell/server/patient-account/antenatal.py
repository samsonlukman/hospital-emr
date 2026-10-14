"""Antenatal Care (ANC) — pregnancy episodes and visit assessments.

Patients, MRNs, and ANC visits stay in OpenMRS. Pregnancy episodes and the
ANC card live in the Hospital EMR hospital store (same SQLite used for Family Cards),
keyed by patient UUID and linked to OpenMRS visit UUIDs.

Model: Patient → Pregnancy (ANC episode) → ANC visits.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
import xmlrpc.client
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

from admin_audit import AUDIT_DB_PATH

import registration as reception
import server as core

ApiError = core.ApiError
OdooReader = core.OdooReader
ODOO_DB = core.ODOO_DB
ODOO_PASSWORD = core.ODOO_PASSWORD
as_float = core.as_float
find_partner = core.find_partner
format_money = core.format_money
load_currency = core.load_currency
load_openmrs_patient = core.load_openmrs_patient
many2one_id = core.many2one_id
payment_state_label = core.payment_state_label

ANC_VISIT_TYPE_NAME = "ANC"
ANC_PRODUCT_NAME = "Antenatal Care"
ANC_PRODUCT_CODE = "antenatal-care"
ANC_DEFAULT_AMOUNT = 2000.0
ANC_CARD_VALIDITY_DAYS = 365
ANC_LIST_PAGE_SIZES = {50, 100}
ANC_LIST_DEFAULT_PAGE_SIZE = 50
# One-time / renewal antenatal card fee — charged once per validity period.
ANC_EXTERNAL_PREFIX = "anc-registration:"
ANC_ALREADY_REGISTERED_CODE = "anc_already_registered"
ANC_ALREADY_REGISTERED_MESSAGE = (
    "This patient already has an antenatal registration fee for the current period. "
    "Continue with antenatal visits."
)
ANC_NOT_ENROLLED_CODE = "anc_not_enrolled"
ANC_NOT_ENROLLED_MESSAGE = (
    "Create the antenatal card in Antenatal Care before starting an antenatal visit."
)
ANC_CARD_EXISTS_CODE = "pregnancy_already_active"
ANC_CARD_EXISTS_MESSAGE = (
    "This patient already has an antenatal card. After one year the card is disabled "
    "until it is enabled again."
)
ANC_CARD_EXPIRED_CODE = "anc_card_expired"
ANC_CARD_EXPIRED_MESSAGE = (
    "This antenatal card has expired. Create the antenatal fee and collect payment "
    "to enable it for another year."
)
ANC_CARD_DISABLED_CODE = "anc_card_disabled"
ANC_CARD_DISABLED_MESSAGE = (
    "This antenatal card is disabled. Pay the antenatal fee to enable it again."
)

CLINICAL_PRIVILEGE = "app:clinical"
CLINICAL_ROLES = {
    "SuperAdmin",
    "System Developer",
    "Abikan:Clinical",
    "Abikan:Doctor",
    "Doctor",
    "Clinician",
}
NURSING_ROLES = {"SuperAdmin", "System Developer", "Abikan:Nursing", "Nurse"}

ANC_LOCK = threading.Lock()
IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY: dict[str, dict[str, Any]] = {}

PREGNANCY_FIELDS = (
    "gravida",
    "para",
    "abortions",
    "livingChildren",
    "previousPregnancyHistory",
    "lmp",
    "edd",
    "gestationalAgeWeeks",
    "previousCaesarean",
    "significantObstetricHistory",
    "bloodGroup",
    "genotype",
    "occupation",
    "nextOfKin",
    "nextOfKinPhone",
    "bookingDate",
    "gestationalAgeAtBooking",
    "heightCm",
    "notes",
)

VISIT_FIELDS = (
    "visitDate",
    "gestationalAgeWeeks",
    "weightKg",
    "systolic",
    "diastolic",
    "pulse",
    "temperatureC",
    "fundalHeightCm",
    "fetalHeartRate",
    "presentation",
    "urinalysis",
    "laboratoryFindings",
    "ultrasoundFindings",
    "supplements",
    "vaccinations",
    "keyFindings",
    "treatment",
    "nextAppointment",
    "clinician",
)


def reset_for_tests() -> None:
    with IDEMPOTENCY_LOCK:
        IDEMPOTENCY.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None = None) -> str:
    return (moment or _now()).astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str | None) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _format_lagos(moment: datetime | None) -> str:
    if not moment:
        return ""
    local = moment.astimezone(ZoneInfo("Africa/Lagos"))
    return f"{local.day} {local.strftime('%b %Y · %H:%M')}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _actor(user: dict[str, Any]) -> dict[str, str]:
    username = _text(user.get("username"))
    return {
        "uuid": _text(user.get("uuid")),
        "username": username,
        "display": _text(user.get("display")) or username,
    }


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or os.environ.get("ABIKAN_ADMIN_AUDIT_DB") or AUDIT_DB_PATH)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        if not db_path.exists():
            raise
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS anc_pregnancy (
            pregnancy_id TEXT PRIMARY KEY,
            patient_uuid TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'transferred')),
            created_at TEXT NOT NULL,
            created_by_uuid TEXT NOT NULL,
            created_by_username TEXT NOT NULL,
            created_by_display TEXT NOT NULL,
            completed_at TEXT,
            card_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_anc_pregnancy_patient
        ON anc_pregnancy (patient_uuid, status, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_anc_pregnancy_created
        ON anc_pregnancy (created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS anc_visit (
            visit_id TEXT PRIMARY KEY,
            pregnancy_id TEXT NOT NULL,
            patient_uuid TEXT NOT NULL,
            openmrs_visit_uuid TEXT,
            created_at TEXT NOT NULL,
            created_by_uuid TEXT NOT NULL,
            created_by_username TEXT NOT NULL,
            created_by_display TEXT NOT NULL,
            visit_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (pregnancy_id) REFERENCES anc_pregnancy (pregnancy_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_anc_visit_pregnancy
        ON anc_visit (pregnancy_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_anc_visit_openmrs
        ON anc_visit (openmrs_visit_uuid)
        WHERE openmrs_visit_uuid IS NOT NULL AND openmrs_visit_uuid != ''
        """
    )
    _migrate_fee_period_columns(connection)
    return connection


def _migrate_fee_period_columns(connection: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(anc_pregnancy)")}
    if "fee_period_id" not in columns:
        connection.execute("ALTER TABLE anc_pregnancy ADD COLUMN fee_period_id TEXT")
    if "fee_period_started_at" not in columns:
        connection.execute("ALTER TABLE anc_pregnancy ADD COLUMN fee_period_started_at TEXT")
    if "fee_expires_at" not in columns:
        connection.execute("ALTER TABLE anc_pregnancy ADD COLUMN fee_expires_at TEXT")
    if "fee_enabled_period_id" not in columns:
        connection.execute("ALTER TABLE anc_pregnancy ADD COLUMN fee_enabled_period_id TEXT")
    # Backfill validity for older cards: one year from creation.
    rows = connection.execute(
        """
        SELECT pregnancy_id, created_at, fee_period_id, fee_period_started_at,
               fee_expires_at, fee_enabled_period_id
        FROM anc_pregnancy
        WHERE fee_expires_at IS NULL OR TRIM(fee_expires_at) = ''
           OR fee_enabled_period_id IS NULL OR TRIM(fee_enabled_period_id) = ''
        """
    ).fetchall()
    for row in rows:
        started = _parse_iso(row["fee_period_started_at"]) or _parse_iso(row["created_at"]) or _now()
        expires = _parse_iso(row["fee_expires_at"]) or (started + timedelta(days=ANC_CARD_VALIDITY_DAYS))
        period = _text(row["fee_period_id"]) or row["pregnancy_id"]
        enabled_period = _text(row["fee_enabled_period_id"]) or period
        connection.execute(
            """
            UPDATE anc_pregnancy
            SET fee_period_id = COALESCE(NULLIF(fee_period_id, ''), ?),
                fee_period_started_at = COALESCE(NULLIF(fee_period_started_at, ''), ?),
                fee_expires_at = COALESCE(NULLIF(fee_expires_at, ''), ?),
                fee_enabled_period_id = COALESCE(NULLIF(fee_enabled_period_id, ''), ?)
            WHERE pregnancy_id = ?
            """,
            (
                period,
                _iso(started),
                _iso(expires),
                enabled_period,
                row["pregnancy_id"],
            ),
        )
    connection.commit()


def _signed_in_staff(cookie: str) -> dict[str, Any]:
    """Names of roles and privileges, not the raw sign-in objects."""
    import accountant as cashier

    return cashier.load_openmrs_user(cookie)


def require_anc_reader(cookie: str) -> dict[str, Any]:
    """Reception, doctors, nursing, or admin may read ANC cards."""
    try:
        return reception.require_registrar(cookie)
    except ApiError:
        pass
    user = _signed_in_staff(cookie)
    privileges = {str(item) for item in (user.get("privileges") or [])}
    roles = {str(item) for item in (user.get("roles") or [])}
    if CLINICAL_PRIVILEGE in privileges or roles & (CLINICAL_ROLES | NURSING_ROLES | reception.REGISTRATION_ROLES):
        return user
    raise ApiError(403, "forbidden", "You do not have access to antenatal records.")


def require_anc_writer(cookie: str) -> dict[str, Any]:
    """Doctors and nursing update the ANC card. Reception may start the card and visit."""
    try:
        return reception.require_registrar(cookie)
    except ApiError:
        pass
    user = _signed_in_staff(cookie)
    privileges = {str(item) for item in (user.get("privileges") or [])}
    roles = {str(item) for item in (user.get("roles") or [])}
    if CLINICAL_PRIVILEGE in privileges or roles & (CLINICAL_ROLES | NURSING_ROLES):
        return user
    raise ApiError(403, "forbidden", "You do not have access to update antenatal records.")


def is_anc_visit_type(name: str | None) -> bool:
    return _text(name).upper() == ANC_VISIT_TYPE_NAME


def parse_anc_amount(value: Any) -> float:
    """Reception-settable ANC fee in naira. Default catalogue is ₦2,000."""
    if value is None or value == "":
        return ANC_DEFAULT_AMOUNT
    if isinstance(value, bool):
        raise ApiError(422, "amount_invalid", "Enter a valid antenatal fee in naira.")
    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        text = _text(value).replace(",", "")
        text = text.removeprefix("₦").removeprefix("NGN").strip()
        if not text or any(ch in text.upper() for ch in ("$", "USD", "EUR", "GBP")):
            raise ApiError(422, "amount_invalid", "Enter a valid antenatal fee in naira.")
        try:
            amount = float(text)
        except ValueError as error:
            raise ApiError(422, "amount_invalid", "Enter a valid antenatal fee in naira.") from error
    if amount <= 0:
        raise ApiError(422, "amount_invalid", "Antenatal fee must be greater than zero.")
    if amount > 10_000_000:
        raise ApiError(422, "amount_invalid", "Enter a valid antenatal fee in naira.")
    return round(amount, 2)


def _card_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if not row:
        return {}
    try:
        payload = json.loads(row["card_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _visit_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if not row:
        return {}
    try:
        payload = json.loads(row["visit_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _pick_fields(body: dict[str, Any], allowed: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in allowed:
        if key not in body:
            continue
        value = body.get(key)
        if value is None:
            result[key] = None
        elif isinstance(value, (int, float, bool)):
            result[key] = value
        else:
            result[key] = _text(value)
    return result


def _serialize_pregnancy(row: sqlite3.Row, visits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    card = _card_dict(row)
    visit_rows = visits if visits is not None else []
    latest = visit_rows[-1] if visit_rows else None
    fee = _fee_validity(row)
    return {
        "pregnancyId": row["pregnancy_id"],
        "patientUuid": row["patient_uuid"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "completedAt": row["completed_at"] or "",
        "createdBy": {
            "uuid": row["created_by_uuid"],
            "username": row["created_by_username"],
            "display": row["created_by_display"],
        },
        "card": card,
        "visitCount": len(visit_rows),
        "latestVisit": latest,
        "visits": visit_rows,
        **fee,
    }


def _row_get(row: sqlite3.Row, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _fee_validity(row: sqlite3.Row, *, now: datetime | None = None) -> dict[str, Any]:
    moment = now or _now()
    started = _parse_iso(_text(_row_get(row, "fee_period_started_at"))) or _parse_iso(row["created_at"])
    expires = _parse_iso(_text(_row_get(row, "fee_expires_at")))
    if not expires and started:
        expires = started + timedelta(days=ANC_CARD_VALIDITY_DAYS)
    period_id = _text(_row_get(row, "fee_period_id")) or row["pregnancy_id"]
    active = row["status"] == "active"
    enabled = bool(active and expires and moment < expires)
    return {
        "feePeriodId": period_id,
        "feePeriodStartedAt": _iso(started) if started else row["created_at"],
        "expiresAt": _iso(expires) if expires else "",
        "expiresAtLabel": _format_lagos(expires),
        "cardEnabled": enabled,
        "cardExpired": bool(active and not enabled),
        "validityDays": ANC_CARD_VALIDITY_DAYS,
    }


def _activate_fee_period(
    connection: sqlite3.Connection,
    pregnancy_id: str,
    *,
    fee_period_id: str | None = None,
    started_at: datetime | None = None,
) -> None:
    start = started_at or _now()
    expires = start + timedelta(days=ANC_CARD_VALIDITY_DAYS)
    period = _text(fee_period_id)
    if not period:
        row = _pregnancy(connection, pregnancy_id)
        period = _text(_row_get(row, "fee_period_id")) if row else ""
        if not period and row:
            period = row["pregnancy_id"]
    connection.execute(
        """
        UPDATE anc_pregnancy
        SET fee_period_id = ?,
            fee_period_started_at = ?,
            fee_expires_at = ?,
            fee_enabled_period_id = ?
        WHERE pregnancy_id = ?
        """,
        (period, _iso(start), _iso(expires), period, pregnancy_id),
    )
    connection.commit()


def _begin_renewal_period(connection: sqlite3.Connection, pregnancy_id: str) -> str:
    """Open a new unpaid fee period after expiry. Does not re-enable the card."""
    period_id = str(uuid.uuid4())
    connection.execute(
        "UPDATE anc_pregnancy SET fee_period_id = ? WHERE pregnancy_id = ?",
        (period_id, pregnancy_id),
    )
    connection.commit()
    return period_id


def _payment_is_paid(status: str | None) -> bool:
    return _text(status).upper() == "PAID"


def _period_awaits_payment_unlock(row: sqlite3.Row, period_id: str) -> bool:
    """True when this fee period has not yet unlocked the card."""
    enabled_for = _text(_row_get(row, "fee_enabled_period_id"))
    return bool(period_id) and enabled_for != period_id


def _serialize_visit(row: sqlite3.Row) -> dict[str, Any]:
    payload = _visit_dict(row)
    return {
        "visitId": row["visit_id"],
        "pregnancyId": row["pregnancy_id"],
        "patientUuid": row["patient_uuid"],
        "openmrsVisitUuid": row["openmrs_visit_uuid"] or "",
        "createdAt": row["created_at"],
        "createdBy": {
            "uuid": row["created_by_uuid"],
            "username": row["created_by_username"],
            "display": row["created_by_display"],
        },
        **payload,
    }


def _list_visits(connection: sqlite3.Connection, pregnancy_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM anc_visit
        WHERE pregnancy_id = ?
        ORDER BY created_at ASC, rowid ASC
        """,
        (pregnancy_id,),
    ).fetchall()
    return [_serialize_visit(row) for row in rows]


def _active_pregnancy(connection: sqlite3.Connection, patient_uuid: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM anc_pregnancy
        WHERE patient_uuid = ? AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (patient_uuid,),
    ).fetchone()


def _latest_pregnancy(connection: sqlite3.Connection, patient_uuid: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM anc_pregnancy
        WHERE patient_uuid = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (patient_uuid,),
    ).fetchone()


def _pregnancy(connection: sqlite3.Connection, pregnancy_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM anc_pregnancy WHERE pregnancy_id = ?",
        (pregnancy_id,),
    ).fetchone()


def patient_has_anc(patient_uuid: str, path: str | None = None) -> bool:
    with ANC_LOCK:
        connection = _connect(path)
        try:
            row = connection.execute(
                "SELECT 1 FROM anc_pregnancy WHERE patient_uuid = ? LIMIT 1",
                (patient_uuid,),
            ).fetchone()
            return bool(row)
        finally:
            connection.close()


def get_patient_anc_summary(patient_uuid: str, cookie: str, path: str | None = None) -> dict[str, Any]:
    user = require_anc_reader(cookie)
    with ANC_LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                """
                SELECT * FROM anc_pregnancy
                WHERE patient_uuid = ?
                ORDER BY created_at DESC
                """,
                (patient_uuid,),
            ).fetchall()
            pregnancies = []
            for row in rows:
                visits = _list_visits(connection, row["pregnancy_id"])
                pregnancies.append(_serialize_pregnancy(row, visits))
            active = next((item for item in pregnancies if item["status"] == "active"), None)
        finally:
            connection.close()

    fee = None
    if active:
        try:
            fee = get_anc_registration_charge(patient_uuid, active["pregnancyId"], cookie, user=user)
        except ApiError:
            fee = None
    return {
        "status": "ok",
        "hasAnc": bool(pregnancies),
        "enrolled": bool(active),
        "cardEnabled": bool(active and active.get("cardEnabled")),
        "cardExpired": bool(active and active.get("cardExpired")),
        "expiresAt": (active or {}).get("expiresAt") or "",
        "expiresAtLabel": (active or {}).get("expiresAtLabel") or "",
        "activePregnancy": active,
        "pregnancies": pregnancies,
        "defaultFeeAmount": ANC_DEFAULT_AMOUNT,
        "fee": fee,
        "canCreateFee": bool(fee and fee.get("canCreate")),
        "feeAlreadyRegistered": bool(fee and (fee.get("hasCharge") or fee.get("alreadyRegistered"))),
    }


def parse_anc_list_query(raw_path: str) -> dict[str, Any]:
    query = parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
    raw_limit = (query.get("limit") or [str(ANC_LIST_DEFAULT_PAGE_SIZE)])[0]
    raw_start = (query.get("startIndex") or ["0"])[0]
    term = _text((query.get("q") or [""])[0])[:80]
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = ANC_LIST_DEFAULT_PAGE_SIZE
    if limit not in ANC_LIST_PAGE_SIZES:
        raise ApiError(422, "invalid_page_size", "Choose 50 or 100 patients per page.")
    try:
        start_index = max(0, int(raw_start))
    except (TypeError, ValueError):
        start_index = 0
    return {"q": term, "limit": limit, "startIndex": start_index}


def _serialize_anc_list_row(
    row: sqlite3.Row,
    patient: dict[str, str] | None,
) -> dict[str, Any]:
    created = _parse_iso(row["created_at"])
    identity = patient or {}
    fee = _fee_validity(row)
    return {
        "patientUuid": row["patient_uuid"],
        "pregnancyId": row["pregnancy_id"],
        "name": identity.get("name") or "Unnamed patient",
        "hospitalNumber": identity.get("mrn") or "",
        "status": row["status"],
        "enrolledAt": row["created_at"],
        "enrolledAtLabel": _format_lagos(created),
        "cardEnabled": fee["cardEnabled"],
        "cardExpired": fee["cardExpired"],
        "expiresAt": fee["expiresAt"],
        "expiresAtLabel": fee["expiresAtLabel"],
    }


def list_anc_cards(cookie: str, raw_path: str = "", path: str | None = None) -> dict[str, Any]:
    """Paginated Reception list of patients who have an ANC card.

    Cards stay on this list permanently. Records are never auto-deleted.
    """
    require_anc_reader(cookie)
    page = parse_anc_list_query(raw_path)
    uuid_filter: list[str] | None = None
    term = page["q"]
    if term:
        import registration_patient as arrival

        matches = arrival.search_patient_matches(cookie, term)
        uuid_filter = [str(item.get("uuid") or "") for item in matches if item.get("uuid")]
        if not uuid_filter:
            return {
                "status": "ok",
                "q": term,
                "limit": page["limit"],
                "startIndex": page["startIndex"],
                "total": 0,
                "hasMore": False,
                "patients": [],
            }

    with ANC_LOCK:
        connection = _connect(path)
        try:
            count_sql = """
                SELECT COUNT(*)
                FROM anc_pregnancy p
                INNER JOIN (
                    SELECT patient_uuid, MAX(created_at) AS max_created
                    FROM anc_pregnancy
                    GROUP BY patient_uuid
                ) latest
                  ON p.patient_uuid = latest.patient_uuid
                 AND p.created_at = latest.max_created
            """
            count_params: list[Any] = []
            page_sql = """
                SELECT p.*
                FROM anc_pregnancy p
                INNER JOIN (
                    SELECT patient_uuid, MAX(created_at) AS max_created
                    FROM anc_pregnancy
                    GROUP BY patient_uuid
                ) latest
                  ON p.patient_uuid = latest.patient_uuid
                 AND p.created_at = latest.max_created
            """
            page_params: list[Any] = []
            if uuid_filter is not None:
                placeholders = ",".join("?" for _ in uuid_filter)
                count_sql += f" WHERE p.patient_uuid IN ({placeholders})"
                page_sql += f" WHERE p.patient_uuid IN ({placeholders})"
                count_params.extend(uuid_filter)
                page_params.extend(uuid_filter)
            page_sql += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
            page_params.extend([page["limit"], page["startIndex"]])
            total = int(connection.execute(count_sql, count_params).fetchone()[0])
            rows = connection.execute(page_sql, page_params).fetchall()
        finally:
            connection.close()

    patients = []
    for row in rows:
        identity = None
        try:
            identity = load_openmrs_patient(row["patient_uuid"], cookie)
        except ApiError:
            identity = None
        patients.append(_serialize_anc_list_row(row, identity))

    start_index = page["startIndex"]
    return {
        "status": "ok",
        "q": term,
        "limit": page["limit"],
        "startIndex": start_index,
        "total": total,
        "hasMore": start_index + len(patients) < total,
        "patients": patients,
    }


def get_pregnancy(patient_uuid: str, pregnancy_id: str, cookie: str, path: str | None = None) -> dict[str, Any]:
    require_anc_reader(cookie)
    with ANC_LOCK:
        connection = _connect(path)
        try:
            row = _pregnancy(connection, pregnancy_id)
            if not row or row["patient_uuid"] != patient_uuid:
                raise ApiError(404, "pregnancy_not_found", "That antenatal record was not found.")
            visits = _list_visits(connection, pregnancy_id)
            return {
                "status": "ok",
                "pregnancy": _serialize_pregnancy(row, visits),
            }
        finally:
            connection.close()


def start_pregnancy(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
    *,
    path: str | None = None,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actor_user = user or require_anc_writer(cookie)
    actor = _actor(actor_user)
    card = _pick_fields(body.get("card") if isinstance(body.get("card"), dict) else body, PREGNANCY_FIELDS)
    if not card.get("bookingDate"):
        card["bookingDate"] = date.today().isoformat()

    with ANC_LOCK:
        connection = _connect(path)
        try:
            existing = _active_pregnancy(connection, patient_uuid) or _latest_pregnancy(
                connection, patient_uuid
            )
            if existing:
                if existing["status"] != "active":
                    connection.execute(
                        """
                        UPDATE anc_pregnancy
                        SET status = 'active', completed_at = NULL
                        WHERE pregnancy_id = ?
                        """,
                        (existing["pregnancy_id"],),
                    )
                    connection.commit()
                    existing = _pregnancy(connection, existing["pregnancy_id"]) or existing
                visits = _list_visits(connection, existing["pregnancy_id"])
                return {
                    "status": "ok",
                    "created": False,
                    "code": ANC_CARD_EXISTS_CODE,
                    "message": ANC_CARD_EXISTS_MESSAGE,
                    "pregnancy": _serialize_pregnancy(existing, visits),
                }
            pregnancy_id = str(uuid.uuid4())
            created_at = _iso()
            started = _parse_iso(created_at) or _now()
            expires = started + timedelta(days=ANC_CARD_VALIDITY_DAYS)
            connection.execute(
                """
                INSERT INTO anc_pregnancy (
                    pregnancy_id, patient_uuid, status, created_at,
                    created_by_uuid, created_by_username, created_by_display, card_json,
                    fee_period_id, fee_period_started_at, fee_expires_at, fee_enabled_period_id
                ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pregnancy_id,
                    patient_uuid,
                    created_at,
                    actor["uuid"],
                    actor["username"],
                    actor["display"],
                    json.dumps(card, ensure_ascii=False),
                    pregnancy_id,
                    created_at,
                    _iso(expires),
                    pregnancy_id,
                ),
            )
            connection.commit()
            row = _pregnancy(connection, pregnancy_id)
            return {
                "status": "ok",
                "created": True,
                "pregnancy": _serialize_pregnancy(row, []),
            }
        finally:
            connection.close()


def patient_is_enrolled(patient_uuid: str, path: str | None = None) -> bool:
    with ANC_LOCK:
        connection = _connect(path)
        try:
            return _active_pregnancy(connection, patient_uuid) is not None
        finally:
            connection.close()


def patient_anc_card_enabled(patient_uuid: str, path: str | None = None) -> bool:
    """True when the patient has an active ANC card that has not expired."""
    with ANC_LOCK:
        connection = _connect(path)
        try:
            active = _active_pregnancy(connection, patient_uuid)
            if not active:
                return False
            return bool(_fee_validity(active)["cardEnabled"])
        finally:
            connection.close()


def require_anc_card_enabled(patient_uuid: str, path: str | None = None) -> None:
    if patient_anc_card_enabled(patient_uuid, path=path):
        return
    if patient_is_enrolled(patient_uuid, path=path):
        raise ApiError(409, ANC_CARD_DISABLED_CODE, ANC_CARD_DISABLED_MESSAGE)
    raise ApiError(409, ANC_NOT_ENROLLED_CODE, ANC_NOT_ENROLLED_MESSAGE)


def enroll_patient(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
    *,
    path: str | None = None,
) -> dict[str, Any]:
    """Register the patient for Antenatal Care: open pregnancy + card fields.

    Does not create a visit fee here — call create_anc_registration_charge once.
    """
    user = require_anc_writer(cookie)
    started = start_pregnancy(patient_uuid, body, cookie, path=path, user=user)
    summary = get_patient_anc_summary(patient_uuid, cookie, path=path)
    return {
        "status": "ok",
        "created": bool(started.get("created")),
        "code": started.get("code"),
        "message": started.get("message")
        or (
            "Antenatal card is ready. Create the antenatal fee, then start the visit."
            if started.get("created")
            else ANC_CARD_EXISTS_MESSAGE
        ),
        "pregnancy": started.get("pregnancy") or summary.get("activePregnancy"),
        "summary": summary,
    }


def update_pregnancy_card(
    patient_uuid: str,
    pregnancy_id: str,
    body: dict[str, Any],
    cookie: str,
    path: str | None = None,
) -> dict[str, Any]:
    require_anc_writer(cookie)
    updates = _pick_fields(body.get("card") if isinstance(body.get("card"), dict) else body, PREGNANCY_FIELDS)
    status = _text(body.get("status")).lower()
    with ANC_LOCK:
        connection = _connect(path)
        try:
            row = _pregnancy(connection, pregnancy_id)
            if not row or row["patient_uuid"] != patient_uuid:
                raise ApiError(404, "pregnancy_not_found", "That antenatal record was not found.")
            card = _card_dict(row)
            card.update(updates)
            completed_at = row["completed_at"]
            next_status = row["status"]
            if status in {"active", "completed", "transferred"}:
                next_status = status
                if status == "completed" and not completed_at:
                    completed_at = _iso()
                if status == "active":
                    completed_at = None
                    # Only one active pregnancy per patient.
                    connection.execute(
                        """
                        UPDATE anc_pregnancy
                        SET status = 'completed', completed_at = COALESCE(completed_at, ?)
                        WHERE patient_uuid = ? AND status = 'active' AND pregnancy_id != ?
                        """,
                        (_iso(), patient_uuid, pregnancy_id),
                    )
            connection.execute(
                """
                UPDATE anc_pregnancy
                SET card_json = ?, status = ?, completed_at = ?
                WHERE pregnancy_id = ?
                """,
                (json.dumps(card, ensure_ascii=False), next_status, completed_at, pregnancy_id),
            )
            connection.commit()
            refreshed = _pregnancy(connection, pregnancy_id)
            visits = _list_visits(connection, pregnancy_id)
            return {"status": "ok", "pregnancy": _serialize_pregnancy(refreshed, visits)}
        finally:
            connection.close()


def record_anc_visit(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
    path: str | None = None,
) -> dict[str, Any]:
    user = require_anc_writer(cookie)
    actor = _actor(user)
    pregnancy_id = _text(body.get("pregnancyId"))
    openmrs_visit_uuid = _text(body.get("openmrsVisitUuid") or body.get("visitUuid"))
    visit_payload = _pick_fields(body.get("visit") if isinstance(body.get("visit"), dict) else body, VISIT_FIELDS)
    if not visit_payload.get("visitDate"):
        visit_payload["visitDate"] = date.today().isoformat()
    if not visit_payload.get("clinician"):
        visit_payload["clinician"] = actor["display"] or actor["username"]

    with ANC_LOCK:
        connection = _connect(path)
        try:
            if pregnancy_id:
                row = _pregnancy(connection, pregnancy_id)
            else:
                row = _active_pregnancy(connection, patient_uuid)
            if not row or row["patient_uuid"] != patient_uuid:
                raise ApiError(
                    404,
                    "pregnancy_not_found",
                    "Create the antenatal card before recording a visit.",
                )
            if row["status"] != "active":
                raise ApiError(
                    409,
                    "pregnancy_not_active",
                    "This antenatal card is not active. Enable the card after one year if it is disabled.",
                )
            if not _fee_validity(row)["cardEnabled"]:
                raise ApiError(409, ANC_CARD_DISABLED_CODE, ANC_CARD_DISABLED_MESSAGE)
            pregnancy_id = row["pregnancy_id"]
            if openmrs_visit_uuid:
                existing = connection.execute(
                    "SELECT * FROM anc_visit WHERE openmrs_visit_uuid = ?",
                    (openmrs_visit_uuid,),
                ).fetchone()
                if existing:
                    # Update the assessment for this OpenMRS visit rather than duplicating.
                    merged = _visit_dict(existing)
                    merged.update(visit_payload)
                    connection.execute(
                        """
                        UPDATE anc_visit
                        SET visit_json = ?,
                            created_by_uuid = ?,
                            created_by_username = ?,
                            created_by_display = ?
                        WHERE visit_id = ?
                        """,
                        (
                            json.dumps(merged, ensure_ascii=False),
                            actor["uuid"],
                            actor["username"],
                            actor["display"],
                            existing["visit_id"],
                        ),
                    )
                    connection.commit()
                    visits = _list_visits(connection, pregnancy_id)
                    return {
                        "status": "ok",
                        "created": False,
                        "visit": _serialize_visit(
                            connection.execute(
                                "SELECT * FROM anc_visit WHERE visit_id = ?",
                                (existing["visit_id"],),
                            ).fetchone()
                        ),
                        "pregnancy": _serialize_pregnancy(row, visits),
                    }

            visit_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO anc_visit (
                    visit_id, pregnancy_id, patient_uuid, openmrs_visit_uuid,
                    created_at, created_by_uuid, created_by_username, created_by_display, visit_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    visit_id,
                    pregnancy_id,
                    patient_uuid,
                    openmrs_visit_uuid or None,
                    _iso(),
                    actor["uuid"],
                    actor["username"],
                    actor["display"],
                    json.dumps(visit_payload, ensure_ascii=False),
                ),
            )
            connection.commit()
            visits = _list_visits(connection, pregnancy_id)
            visit_row = connection.execute(
                "SELECT * FROM anc_visit WHERE visit_id = ?",
                (visit_id,),
            ).fetchone()
            return {
                "status": "ok",
                "created": True,
                "visit": _serialize_visit(visit_row),
                "pregnancy": _serialize_pregnancy(row, visits),
            }
        finally:
            connection.close()


def execute(
    odoo: OdooReader,
    model: str,
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    return odoo.models.execute_kw(
        ODOO_DB,
        odoo.uid,
        ODOO_PASSWORD,
        model,
        method,
        args,
        kwargs or {},
    )


def charge_key(pregnancy_id: str, fee_period_id: str | None = None) -> str:
    period = _text(fee_period_id) or pregnancy_id
    if period == pregnancy_id:
        return f"{ANC_EXTERNAL_PREFIX}{pregnancy_id}"
    return f"{ANC_EXTERNAL_PREFIX}{pregnancy_id}:{period}"


def ensure_anc_masters(odoo: OdooReader) -> dict[str, Any]:
    """Ensure Antenatal Care product exists. Default list price ₦2,000."""
    masters = reception.ensure_registration_masters(odoo)
    shop = masters["shop"]
    category_id = masters.get("category_id")
    products = odoo.search_read(
        "product.product",
        [("default_code", "=", ANC_PRODUCT_CODE)],
        ["id", "name", "list_price", "default_code", "categ_id"],
        limit=1,
    )
    if not products:
        products = odoo.search_read(
            "product.product",
            [("name", "=", ANC_PRODUCT_NAME)],
            ["id", "name", "list_price", "default_code", "categ_id"],
            limit=1,
        )
    if products:
        product = products[0]
        if as_float(product.get("list_price")) <= 0:
            execute(
                odoo,
                "product.product",
                "write",
                [[int(product["id"])], {"list_price": ANC_DEFAULT_AMOUNT}],
            )
            product["list_price"] = ANC_DEFAULT_AMOUNT
        return {"shop": shop, "product": product, "pricelist_id": masters.get("pricelist_id")}

    values: dict[str, Any] = {
        "name": ANC_PRODUCT_NAME,
        "default_code": ANC_PRODUCT_CODE,
        "type": "service",
        "list_price": ANC_DEFAULT_AMOUNT,
        "sale_ok": True,
        "purchase_ok": False,
    }
    if category_id:
        values["categ_id"] = category_id
    product_id = int(execute(odoo, "product.product", "create", [values]))
    product_rows = odoo.read(
        "product.product",
        [product_id],
        ["id", "name", "list_price", "default_code", "categ_id"],
    )
    return {
        "shop": shop,
        "product": product_rows[0]
        if product_rows
        else {"id": product_id, "name": ANC_PRODUCT_NAME, "list_price": ANC_DEFAULT_AMOUNT},
        "pricelist_id": masters.get("pricelist_id"),
    }


def find_existing_anc_sale(
    odoo: OdooReader,
    pregnancy_id: str,
    fee_period_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Antenatal card fee sale for this pregnancy fee period."""
    period = _text(fee_period_id) or pregnancy_id
    key = charge_key(pregnancy_id, period)
    domain: list[Any]
    if period == pregnancy_id:
        domain = [
            "|",
            ("external_order_id", "=", key),
            "&",
            ("external_id", "=", pregnancy_id),
            ("external_order_id", "=like", f"{ANC_EXTERNAL_PREFIX}%"),
        ]
    else:
        domain = [("external_order_id", "=", key)]
    lines = odoo.search_read(
        "sale.order.line",
        domain,
        ["id", "order_id", "price_unit", "name", "product_id", "external_order_id"],
        limit=10,
    )
    for line in lines:
        external = _text(line.get("external_order_id"))
        if period == pregnancy_id:
            if external and external != key and ":" in external[len(ANC_EXTERNAL_PREFIX) :]:
                # Newer period-specific sale — ignore for legacy period lookup.
                continue
            if external and not external.startswith(ANC_EXTERNAL_PREFIX) and external != pregnancy_id:
                continue
        elif external != key:
            continue
        order_id = many2one_id(line.get("order_id"))
        if not order_id:
            continue
        sales = odoo.read(
            "sale.order",
            [order_id],
            ["id", "name", "state", "invoice_ids", "origin", "amount_total"],
        )
        if sales:
            return line, sales[0]
    return None


def _confirm_sale(odoo: OdooReader, sale_id: int) -> None:
    try:
        execute(odoo, "sale.order", "action_confirm", [[sale_id]])
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "odoo_charge_failed",
            "The antenatal fee could not be created. Refresh and try again.",
        ) from error


def _sale_payment_status(odoo: OdooReader, sale: dict[str, Any]) -> str | None:
    invoice_ids = [int(item) for item in (sale.get("invoice_ids") or [])]
    if not invoice_ids:
        return None
    invoices = odoo.read("account.move", invoice_ids[:1], ["payment_state", "amount_residual"])
    if not invoices:
        return None
    return payment_state_label(invoices[0].get("payment_state"))


def _charge_payload(
    cookie: str,
    patient_uuid: str,
    pregnancy_id: str,
    *,
    user: dict[str, Any],
    odoo: OdooReader | None = None,
    default_amount: float = ANC_DEFAULT_AMOUNT,
    path: str | None = None,
) -> dict[str, Any]:
    del cookie
    odoo = odoo or reception.odoo_reader()
    currency = load_currency(odoo, None)
    with ANC_LOCK:
        connection = _connect(path)
        try:
            row = _pregnancy(connection, pregnancy_id)
            if not row or row["patient_uuid"] != patient_uuid:
                raise ApiError(404, "pregnancy_not_found", "That antenatal record was not found.")
            fee = _fee_validity(row)
            period_id = str(fee["feePeriodId"])
            existing = find_existing_anc_sale(odoo, pregnancy_id, period_id)
            payment_status = _sale_payment_status(odoo, existing[1]) if existing else None

            # Expired card: paid fee for the current period unlocks another year.
            # A paid fee that already unlocked this period must not renew itself —
            # open a fresh renewal period instead.
            if fee["cardExpired"] and existing and _payment_is_paid(payment_status):
                if _period_awaits_payment_unlock(row, period_id):
                    _activate_fee_period(connection, pregnancy_id, fee_period_id=period_id)
                    row = _pregnancy(connection, pregnancy_id)
                    fee = _fee_validity(row)
                    period_id = str(fee["feePeriodId"])
                    existing = find_existing_anc_sale(odoo, pregnancy_id, period_id)
                    payment_status = (
                        _sale_payment_status(odoo, existing[1]) if existing else None
                    )
                else:
                    period_id = _begin_renewal_period(connection, pregnancy_id)
                    row = _pregnancy(connection, pregnancy_id)
                    fee = _fee_validity(row)
                    existing = None
                    payment_status = None

            base = {
                "status": "ok",
                "pregnancyId": pregnancy_id,
                "patientUuid": patient_uuid,
                "feeName": ANC_PRODUCT_NAME,
                "defaultAmount": default_amount,
                "feePeriodId": period_id,
                "cardEnabled": fee["cardEnabled"],
                "cardExpired": fee["cardExpired"],
                "expiresAt": fee["expiresAt"],
                "expiresAtLabel": fee["expiresAtLabel"],
                "validityDays": ANC_CARD_VALIDITY_DAYS,
                "recordedBy": user.get("username") or "",
            }

            if fee["cardEnabled"]:
                if not existing:
                    return {
                        **base,
                        "hasCharge": False,
                        "alreadyRegistered": False,
                        "feeAmount": format_money(default_amount, currency),
                        "paymentStatus": None,
                        "canCreate": True,
                        "message": (
                            f"Antenatal card fee. The card stays enabled for {ANC_CARD_VALIDITY_DAYS} days "
                            "from creation. After that, pay again to renew."
                        ),
                    }
                line, sale = existing
                amount = as_float(line.get("price_unit"))
                return {
                    **base,
                    "hasCharge": True,
                    "alreadyRegistered": True,
                    "feeAmount": format_money(amount, currency),
                    "paymentStatus": payment_status,
                    "saleName": sale.get("name") or "",
                    "canCreate": False,
                    "code": ANC_ALREADY_REGISTERED_CODE,
                    "message": ANC_ALREADY_REGISTERED_MESSAGE,
                }

            # Expired / disabled: renew with payment for the current fee period.
            if existing and not _payment_is_paid(payment_status):
                line, sale = existing
                amount = as_float(line.get("price_unit"))
                return {
                    **base,
                    "hasCharge": True,
                    "alreadyRegistered": False,
                    "feeAmount": format_money(amount, currency),
                    "paymentStatus": payment_status,
                    "saleName": sale.get("name") or "",
                    "canCreate": False,
                    "code": ANC_CARD_EXPIRED_CODE,
                    "message": (
                        "Antenatal card expired. Ask the patient to pay this antenatal fee at Accountant "
                        "to enable the card for another year."
                    ),
                }
            if fee["cardExpired"] and not existing:
                # Ensure a distinct renewal period before creating the next fee.
                if not _period_awaits_payment_unlock(row, period_id):
                    period_id = _begin_renewal_period(connection, pregnancy_id)
                    row = _pregnancy(connection, pregnancy_id)
                    fee = _fee_validity(row)
                    base["feePeriodId"] = period_id
                    base["cardEnabled"] = fee["cardEnabled"]
                    base["cardExpired"] = fee["cardExpired"]
                    base["expiresAt"] = fee["expiresAt"]
                    base["expiresAtLabel"] = fee["expiresAtLabel"]
            return {
                **base,
                "hasCharge": False,
                "alreadyRegistered": False,
                "feeAmount": format_money(default_amount, currency),
                "paymentStatus": None,
                "canCreate": True,
                "code": ANC_CARD_EXPIRED_CODE,
                "message": ANC_CARD_EXPIRED_MESSAGE,
            }
        finally:
            connection.close()


def get_anc_registration_charge(
    patient_uuid: str,
    pregnancy_id: str,
    cookie: str,
    *,
    user: dict[str, Any] | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    actor = user or reception.require_registrar(cookie)
    if not pregnancy_id:
        raise ApiError(422, "pregnancy_required", "Create the antenatal card before the antenatal fee.")
    try:
        odoo = reception.odoo_reader()
        masters = ensure_anc_masters(odoo)
        default_amount = as_float(masters["product"].get("list_price")) or ANC_DEFAULT_AMOUNT
        return _charge_payload(
            cookie,
            patient_uuid,
            pregnancy_id,
            user=actor,
            odoo=odoo,
            default_amount=default_amount,
            path=path,
        )
    except ApiError:
        raise
    except Exception as error:
        raise ApiError(503, "odoo_error", "Financial service is unavailable.") from error


def create_anc_registration_charge(
    patient_uuid: str,
    body: dict[str, Any],
    cookie: str,
    *,
    path: str | None = None,
) -> dict[str, Any]:
    """Reception creates the antenatal card fee for the current or renewal period."""
    user = reception.require_registrar(cookie)
    pregnancy_id = _text(body.get("pregnancyId"))
    if not pregnancy_id:
        with ANC_LOCK:
            connection = _connect(path)
            try:
                active = _active_pregnancy(connection, patient_uuid)
                pregnancy_id = active["pregnancy_id"] if active else ""
            finally:
                connection.close()
    if not pregnancy_id:
        raise ApiError(
            422,
            "pregnancy_required",
            "Create the antenatal card before creating the antenatal fee.",
        )

    with ANC_LOCK:
        connection = _connect(path)
        try:
            row = _pregnancy(connection, pregnancy_id)
            if not row or row["patient_uuid"] != patient_uuid:
                raise ApiError(404, "pregnancy_not_found", "That antenatal record was not found.")
            fee = _fee_validity(row)
            period_id = str(fee["feePeriodId"])
            # Expired card: keep an unpaid renewal bill, otherwise open a new period.
            if fee["cardExpired"]:
                existing_period = find_existing_anc_sale(
                    reception.odoo_reader(), pregnancy_id, period_id
                )
                if existing_period:
                    pay = _sale_payment_status(reception.odoo_reader(), existing_period[1])
                    if _payment_is_paid(pay) and not _period_awaits_payment_unlock(row, period_id):
                        period_id = _begin_renewal_period(connection, pregnancy_id)
                elif not _period_awaits_payment_unlock(row, period_id):
                    period_id = _begin_renewal_period(connection, pregnancy_id)
        finally:
            connection.close()

    request_id = _text(body.get("requestId"))
    visit_key = charge_key(pregnancy_id, period_id)
    keys = [visit_key]
    if request_id:
        keys.append(request_id)
    with IDEMPOTENCY_LOCK:
        for key in keys:
            state = IDEMPOTENCY.get(key) or {}
            if state.get("status") == "pending":
                raise ApiError(409, "charge_in_progress", "This antenatal fee is already being created.")
            if state.get("status") == "done":
                payload = get_anc_registration_charge(
                    patient_uuid, pregnancy_id, cookie, user=user, path=path
                )
                payload["alreadyCreated"] = True
                return payload
        for key in keys:
            IDEMPOTENCY[key] = {"status": "pending"}
    try:
        patient = load_openmrs_patient(patient_uuid, cookie)
        odoo = reception.odoo_reader()
        partner = find_partner(odoo, patient)
        if not partner:
            raise ApiError(
                409,
                "account_not_found",
                "This patient has no financial account yet. Try again in a moment.",
            )
        existing = find_existing_anc_sale(odoo, pregnancy_id, period_id)
        if existing:
            _line, sale = existing
            if sale.get("state") == "draft":
                _confirm_sale(odoo, int(sale["id"]))
            payload = _charge_payload(
                cookie, patient_uuid, pregnancy_id, user=user, odoo=odoo, path=path
            )
            payload["alreadyCreated"] = True
            payload["canCreate"] = False
            with IDEMPOTENCY_LOCK:
                for key in keys:
                    IDEMPOTENCY[key] = {"status": "done"}
            return payload
        amount = parse_anc_amount(body.get("amount"))
        masters = ensure_anc_masters(odoo)
        product = masters["product"]
        shop = masters["shop"]
        product_id = int(product["id"])
        shop_id = int(shop["id"])
        warehouse_id = many2one_id(shop.get("warehouse_id")) or 1
        pricelist_id = many2one_id(shop.get("pricelist_id")) or masters.get("pricelist_id") or 1
        sale_id = int(
            execute(
                odoo,
                "sale.order",
                "create",
                [
                    {
                        "partner_id": int(partner["id"]),
                        "shop_id": shop_id,
                        "warehouse_id": warehouse_id,
                        "pricelist_id": pricelist_id,
                        "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                        "origin": pregnancy_id,
                        "care_setting": "opd",
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": product_id,
                                    "name": product.get("name") or ANC_PRODUCT_NAME,
                                    "product_uom_qty": 1,
                                    "price_unit": amount,
                                    "tax_id": [(6, 0, [])],
                                    "external_order_id": visit_key,
                                    "external_id": pregnancy_id,
                                },
                            )
                        ],
                    }
                ],
            )
        )
        sale_rows = odoo.read("sale.order", [sale_id], ["order_line"])
        line_ids = [int(item) for item in ((sale_rows[0].get("order_line") if sale_rows else None) or [])]
        if line_ids:
            execute(
                odoo,
                "sale.order.line",
                "write",
                [line_ids, {"tax_id": [(6, 0, [])], "price_unit": amount}],
            )
        _confirm_sale(odoo, sale_id)
        with IDEMPOTENCY_LOCK:
            for key in keys:
                IDEMPOTENCY[key] = {"status": "done"}
        payload = _charge_payload(
            cookie,
            patient_uuid,
            pregnancy_id,
            user=user,
            odoo=odoo,
            default_amount=amount,
            path=path,
        )
        payload["alreadyCreated"] = False
        payload["recordedBy"] = user.get("username") or ""
        return payload
    except ApiError:
        with IDEMPOTENCY_LOCK:
            for key in keys:
                current = IDEMPOTENCY.get(key) or {}
                if current.get("status") == "pending":
                    IDEMPOTENCY.pop(key, None)
        raise
    except Exception:
        with IDEMPOTENCY_LOCK:
            for key in keys:
                current = IDEMPOTENCY.get(key) or {}
                if current.get("status") == "pending":
                    IDEMPOTENCY.pop(key, None)
        raise


# Back-compat aliases used by older call sites during the visit-fee mistake.
get_anc_charge = get_anc_registration_charge
create_anc_charge = create_anc_registration_charge


def ensure_openmrs_anc_visit_type(cookie: str) -> dict[str, Any] | None:
    """Create the OpenMRS ANC visit type when missing. Safe no-op if unauthorized."""
    import registration_patient as arrival

    rows = arrival._results(
        arrival._openmrs_json(
            "/openmrs/ws/rest/v1/visittype?v=custom:(uuid,name,display,retired,description)",
            cookie,
            fallback="Visit types could not be loaded.",
        )
    )
    for row in rows:
        name = _text(row.get("name") or row.get("display"))
        if name.upper() == ANC_VISIT_TYPE_NAME and not row.get("retired"):
            return row
    try:
        created = arrival._openmrs_json(
            "/openmrs/ws/rest/v1/visittype",
            cookie,
            method="POST",
            payload={
                "name": ANC_VISIT_TYPE_NAME,
                "description": "Antenatal Care outpatient visits",
            },
            fallback="The antenatal visit type could not be created.",
        )
        return created if isinstance(created, dict) else None
    except ApiError:
        return None
