"""Reusable Family Cards for Reception.

A Family Card belongs to a household, not to one patient. Each member stays
an independent clinical record. The card fee is charged once, when the card
is first created — never when another relative is registered.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from admin_audit import AUDIT_DB_PATH

import server as core

ApiError = core.ApiError

FAMILY_LOCK = threading.Lock()
FEE_PENDING = "pending"
FEE_BILLED = "billed"
FAMILY_MODES = {"none", "existing", "new"}
FAMILY_CARD_ISSUED_MESSAGE = (
    "This family already has a Family Card. No new card fee is created."
)
FAMILY_EXISTS_MESSAGE = (
    "A family with this name already exists. Use the existing Family Card "
    "instead of creating another."
)
DEFAULT_RELATIONSHIP = "Family member"
RELATIONSHIPS = (
    "Self",
    "Spouse",
    "Child",
    "Parent",
    "Sibling",
    "Family member",
    "Other",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None = None) -> str:
    return (moment or _now()).astimezone(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


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
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hospital_family_member (
            patient_uuid TEXT PRIMARY KEY,
            family_id TEXT NOT NULL,
            relationship TEXT NOT NULL,
            member_name TEXT NOT NULL,
            member_identifier TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            linked_by_username TEXT NOT NULL,
            FOREIGN KEY (family_id) REFERENCES hospital_family(family_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hospital_family_event (
            event_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            actor_uuid TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            actor_display TEXT NOT NULL,
            event_type TEXT NOT NULL,
            family_id TEXT NOT NULL,
            patient_uuid TEXT NOT NULL,
            card_number TEXT NOT NULL,
            new_card_created INTEGER NOT NULL,
            fee_generated INTEGER NOT NULL,
            from_family_id TEXT NOT NULL,
            relationship TEXT NOT NULL,
            notes TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS hospital_family_name_idx ON hospital_family(family_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS hospital_family_member_family_idx "
        "ON hospital_family_member(family_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS hospital_family_member_name_idx "
        "ON hospital_family_member(member_name)"
    )
    return connection


def _next_card_number(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT card_number FROM hospital_family ORDER BY card_number DESC"
    ).fetchone()
    highest = 0
    if row:
        match = re.search(r"(\d+)$", str(row["card_number"] or ""))
        if match:
            highest = int(match.group(1))
    return f"FAM-{highest + 1:03d}"


def _record_event(
    connection: sqlite3.Connection,
    *,
    user: dict[str, Any],
    event_type: str,
    family_id: str,
    patient_uuid: str,
    card_number: str,
    new_card_created: bool,
    fee_generated: bool,
    from_family_id: str = "",
    relationship: str = "",
    notes: str = "",
) -> None:
    actor = _actor(user)
    connection.execute(
        """
        INSERT INTO hospital_family_event (
            event_id, created_at, actor_uuid, actor_username, actor_display,
            event_type, family_id, patient_uuid, card_number, new_card_created,
            fee_generated, from_family_id, relationship, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            _iso(),
            actor["uuid"],
            actor["username"],
            actor["display"],
            event_type,
            family_id,
            patient_uuid,
            card_number,
            1 if new_card_created else 0,
            1 if fee_generated else 0,
            from_family_id,
            relationship,
            notes,
        ),
    )


def _member_count(connection: sqlite3.Connection, family_id: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS total FROM hospital_family_member WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    return int(row["total"] if row else 0)


def _family_row(connection: sqlite3.Connection, family_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM hospital_family WHERE family_id = ? AND archived = 0",
        (family_id,),
    ).fetchone()


def _member_row(connection: sqlite3.Connection, patient_uuid: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM hospital_family_member WHERE patient_uuid = ?",
        (patient_uuid,),
    ).fetchone()


def _serialize_family(
    connection: sqlite3.Connection,
    family: sqlite3.Row,
    *,
    include_members: bool = False,
) -> dict[str, Any]:
    payload = {
        "familyId": family["family_id"],
        "familyName": family["family_name"],
        "cardNumber": family["card_number"],
        "memberCount": _member_count(connection, family["family_id"]),
        "feeStatus": family["fee_status"],
        "feePatientUuid": family["fee_patient_uuid"],
        "createdAt": family["created_at"],
        "createdBy": family["created_by_display"] or family["created_by_username"],
    }
    if include_members:
        rows = connection.execute(
            """
            SELECT patient_uuid, relationship, member_name, member_identifier,
                   linked_at, linked_by_username
            FROM hospital_family_member
            WHERE family_id = ?
            ORDER BY linked_at ASC
            """,
            (family["family_id"],),
        ).fetchall()
        payload["members"] = [
            {
                "patientUuid": row["patient_uuid"],
                "relationship": row["relationship"],
                "name": row["member_name"],
                "identifier": row["member_identifier"],
                "linkedAt": row["linked_at"],
                "linkedBy": row["linked_by_username"],
            }
            for row in rows
        ]
    return payload


def serialize_membership(
    family: dict[str, Any] | None,
    patient_uuid: str,
    relationship: str = "",
) -> dict[str, Any] | None:
    if not family:
        return None
    return {
        **family,
        "relationship": relationship,
        "isFeePatient": family.get("feePatientUuid") == patient_uuid,
    }


def get_family(family_id: str, *, path: str | None = None) -> dict[str, Any] | None:
    family_id = _text(family_id)
    if not family_id:
        return None
    with FAMILY_LOCK:
        connection = _connect(path)
        try:
            row = _family_row(connection, family_id)
            if not row:
                return None
            return _serialize_family(connection, row, include_members=True)
        finally:
            connection.close()


def family_for_patient(patient_uuid: str, *, path: str | None = None) -> dict[str, Any] | None:
    patient_uuid = _text(patient_uuid)
    if not patient_uuid:
        return None
    try:
        with FAMILY_LOCK:
            connection = _connect(path)
            try:
                member = _member_row(connection, patient_uuid)
                if not member:
                    return None
                family = _family_row(connection, member["family_id"])
                if not family:
                    return None
                payload = _serialize_family(connection, family, include_members=True)
                payload["relationship"] = member["relationship"]
                payload["isFeePatient"] = family["fee_patient_uuid"] == patient_uuid
                return payload
            finally:
                connection.close()
    except OSError:
        return None


def find_similar_families(household_name: str, *, path: str | None = None) -> list[dict[str, Any]]:
    needle = _normalize_name(household_name)
    if not needle:
        return []
    with FAMILY_LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                "SELECT * FROM hospital_family WHERE archived = 0"
            ).fetchall()
            matches = []
            for row in rows:
                if _normalize_name(row["family_name"]) == needle:
                    matches.append(_serialize_family(connection, row))
            return matches
        finally:
            connection.close()


def search_families(query: str, *, extra_patient_uuids: list[str] | None = None, path: str | None = None) -> list[dict[str, Any]]:
    needle = _text(query)
    extra = [item for item in (extra_patient_uuids or []) if _text(item)]
    with FAMILY_LOCK:
        connection = _connect(path)
        try:
            seen: dict[str, dict[str, Any]] = {}
            if needle:
                like = f"%{needle}%"
                rows = connection.execute(
                    """
                    SELECT DISTINCT f.*
                    FROM hospital_family f
                    LEFT JOIN hospital_family_member m ON m.family_id = f.family_id
                    WHERE f.archived = 0
                      AND (
                        f.family_name LIKE ? COLLATE NOCASE
                        OR f.card_number LIKE ? COLLATE NOCASE
                        OR m.member_name LIKE ? COLLATE NOCASE
                        OR m.member_identifier LIKE ? COLLATE NOCASE
                      )
                    ORDER BY f.created_at DESC
                    """,
                    (like, like, like, like),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM hospital_family
                    WHERE archived = 0
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                ).fetchall()
            for row in rows:
                seen[row["family_id"]] = _serialize_family(connection, row)
            for patient_uuid in extra:
                member = _member_row(connection, patient_uuid)
                if not member:
                    continue
                family = _family_row(connection, member["family_id"])
                if family:
                    seen[family["family_id"]] = _serialize_family(connection, family)
            return list(seen.values())
        finally:
            connection.close()


def charge_decision(patient_uuid: str, *, path: str | None = None) -> dict[str, Any]:
    family = family_for_patient(patient_uuid, path=path)
    if not family:
        return {
            "inFamily": False,
            "family": None,
            "canChargeFamilyFee": False,
            "familyCardIssued": False,
            "blockReason": None,
            "forcedCardType": None,
        }
    is_fee_patient = family.get("feePatientUuid") == patient_uuid
    billed = family.get("feeStatus") == FEE_BILLED
    issued = billed or not is_fee_patient
    can_charge = is_fee_patient and not billed
    return {
        "inFamily": True,
        "family": family,
        "canChargeFamilyFee": can_charge,
        "familyCardIssued": issued,
        "blockReason": FAMILY_CARD_ISSUED_MESSAGE if issued else None,
        "forcedCardType": "family" if can_charge else ("family" if issued else None),
    }


def prepare_family_registration(body: dict[str, Any], *, path: str | None = None) -> dict[str, Any]:
    mode = _text(body.get("familyMode") or "none").lower()
    if mode in {"", "individual"}:
        mode = "none"
    if mode not in FAMILY_MODES:
        raise ApiError(
            422,
            "family_mode_invalid",
            "Choose Individual Card, an existing Family Card, or a new family.",
        )
    relationship = _text(body.get("familyRelationship")) or DEFAULT_RELATIONSHIP
    if mode == "none":
        return {"mode": "none"}
    if mode == "existing":
        family_id = _text(body.get("familyId"))
        if not family_id:
            raise ApiError(
                422,
                "family_required",
                "Select an existing family before registering this patient.",
            )
        family = get_family(family_id, path=path)
        if not family:
            raise ApiError(404, "family_not_found", "This family was not found.")
        return {"mode": "existing", "family": family, "relationship": relationship}
    household = _text(body.get("householdName"))
    if not household:
        last = _text(body.get("familyName"))
        household = f"{last} Family".strip() if last else ""
    if not household:
        raise ApiError(
            422,
            "family_name_required",
            "Enter a family name for the new Family Card.",
        )
    similar = find_similar_families(household, path=path)
    if similar and not body.get("confirmCreateFamily"):
        return {
            "mode": "new",
            "householdName": household,
            "relationship": relationship,
            "conflict": True,
            "families": similar,
        }
    return {
        "mode": "new",
        "householdName": household,
        "relationship": relationship,
        "conflict": False,
        "families": similar,
    }


def apply_registration(
    patient_uuid: str,
    plan: dict[str, Any],
    user: dict[str, Any],
    *,
    member_name: str = "",
    member_identifier: str = "",
    path: str | None = None,
) -> dict[str, Any]:
    mode = plan.get("mode") or "none"
    if mode == "none":
        return {
            "family": None,
            "newCardCreated": False,
            "feeWillBeGenerated": False,
        }
    if mode == "existing":
        family = link_member(
            plan["family"]["familyId"],
            patient_uuid,
            plan.get("relationship") or DEFAULT_RELATIONSHIP,
            user,
            member_name=member_name,
            member_identifier=member_identifier,
            path=path,
        )
        return {
            "family": family,
            "newCardCreated": False,
            "feeWillBeGenerated": False,
        }
    family = create_family(
        plan["householdName"],
        patient_uuid,
        plan.get("relationship") or DEFAULT_RELATIONSHIP,
        user,
        member_name=member_name,
        member_identifier=member_identifier,
        path=path,
    )
    return {
        "family": family,
        "newCardCreated": True,
        "feeWillBeGenerated": True,
    }


def create_family(
    household_name: str,
    first_patient_uuid: str,
    relationship: str,
    user: dict[str, Any],
    *,
    member_name: str = "",
    member_identifier: str = "",
    path: str | None = None,
) -> dict[str, Any]:
    household_name = _text(household_name)
    first_patient_uuid = _text(first_patient_uuid)
    relationship = _text(relationship) or DEFAULT_RELATIONSHIP
    if not household_name or not first_patient_uuid:
        raise ApiError(422, "family_name_required", "Enter a family name for the new Family Card.")
    actor = _actor(user)
    with FAMILY_LOCK:
        connection = _connect(path)
        try:
            existing = _member_row(connection, first_patient_uuid)
            if existing:
                raise ApiError(
                    409,
                    "family_membership_exists",
                    "This patient already belongs to a family.",
                )
            family_id = uuid.uuid4().hex
            card_number = _next_card_number(connection)
            created_at = _iso()
            connection.execute(
                """
                INSERT INTO hospital_family (
                    family_id, card_number, family_name, created_at,
                    created_by_uuid, created_by_username, created_by_display,
                    fee_status, fee_patient_uuid, archived
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    family_id,
                    card_number,
                    household_name,
                    created_at,
                    actor["uuid"],
                    actor["username"],
                    actor["display"],
                    FEE_PENDING,
                    first_patient_uuid,
                ),
            )
            connection.execute(
                """
                INSERT INTO hospital_family_member (
                    patient_uuid, family_id, relationship, member_name,
                    member_identifier, linked_at, linked_by_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    first_patient_uuid,
                    family_id,
                    relationship,
                    _text(member_name),
                    _text(member_identifier),
                    created_at,
                    actor["username"],
                ),
            )
            _record_event(
                connection,
                user=user,
                event_type="family_created",
                family_id=family_id,
                patient_uuid=first_patient_uuid,
                card_number=card_number,
                new_card_created=True,
                fee_generated=False,
                relationship=relationship,
                notes="Family Card created. Fee is billed after the first visit.",
            )
            _record_event(
                connection,
                user=user,
                event_type="patient_registered",
                family_id=family_id,
                patient_uuid=first_patient_uuid,
                card_number=card_number,
                new_card_created=True,
                fee_generated=False,
                relationship=relationship,
                notes="First family member registered.",
            )
            connection.commit()
            row = _family_row(connection, family_id)
            payload = _serialize_family(connection, row, include_members=True) if row else {}
            payload["relationship"] = relationship
            payload["isFeePatient"] = True
            return payload
        finally:
            connection.close()


def link_member(
    family_id: str,
    patient_uuid: str,
    relationship: str,
    user: dict[str, Any],
    *,
    member_name: str = "",
    member_identifier: str = "",
    confirm_transfer: bool = False,
    path: str | None = None,
) -> dict[str, Any]:
    family_id = _text(family_id)
    patient_uuid = _text(patient_uuid)
    relationship = _text(relationship) or DEFAULT_RELATIONSHIP
    actor = _actor(user)
    with FAMILY_LOCK:
        connection = _connect(path)
        try:
            family = _family_row(connection, family_id)
            if not family:
                raise ApiError(404, "family_not_found", "This family was not found.")
            existing = _member_row(connection, patient_uuid)
            from_family_id = ""
            if existing:
                if existing["family_id"] == family_id:
                    raise ApiError(
                        409,
                        "family_membership_exists",
                        "This patient already belongs to this family.",
                    )
                if not confirm_transfer:
                    raise ApiError(
                        409,
                        "family_transfer_required",
                        "This patient already belongs to another family. Confirm to move them.",
                    )
                from_family_id = existing["family_id"]
                connection.execute(
                    "DELETE FROM hospital_family_member WHERE patient_uuid = ?",
                    (patient_uuid,),
                )
                event_type = "member_transferred"
                notes = "Patient moved to another family. No Family Card fee was created."
            else:
                event_type = "member_linked"
                notes = "Patient added to an existing Family Card. No Family Card fee was created."
            linked_at = _iso()
            connection.execute(
                """
                INSERT INTO hospital_family_member (
                    patient_uuid, family_id, relationship, member_name,
                    member_identifier, linked_at, linked_by_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_uuid,
                    family_id,
                    relationship,
                    _text(member_name),
                    _text(member_identifier),
                    linked_at,
                    actor["username"],
                ),
            )
            _record_event(
                connection,
                user=user,
                event_type=event_type,
                family_id=family_id,
                patient_uuid=patient_uuid,
                card_number=family["card_number"],
                new_card_created=False,
                fee_generated=False,
                from_family_id=from_family_id,
                relationship=relationship,
                notes=notes,
            )
            if not existing:
                _record_event(
                    connection,
                    user=user,
                    event_type="patient_registered",
                    family_id=family_id,
                    patient_uuid=patient_uuid,
                    card_number=family["card_number"],
                    new_card_created=False,
                    fee_generated=False,
                    relationship=relationship,
                    notes="Registration recorded under an existing Family Card.",
                )
            connection.commit()
            payload = _serialize_family(connection, family, include_members=True)
            payload["relationship"] = relationship
            payload["isFeePatient"] = family["fee_patient_uuid"] == patient_uuid
            payload["transferred"] = bool(from_family_id)
            return payload
        finally:
            connection.close()


def mark_fee_billed(
    family_id: str,
    user: dict[str, Any],
    *,
    patient_uuid: str = "",
    path: str | None = None,
) -> dict[str, Any] | None:
    family_id = _text(family_id)
    if not family_id:
        return None
    with FAMILY_LOCK:
        connection = _connect(path)
        try:
            family = _family_row(connection, family_id)
            if not family:
                return None
            if family["fee_status"] != FEE_BILLED:
                connection.execute(
                    "UPDATE hospital_family SET fee_status = ? WHERE family_id = ?",
                    (FEE_BILLED, family_id),
                )
                _record_event(
                    connection,
                    user=user,
                    event_type="fee_billed",
                    family_id=family_id,
                    patient_uuid=_text(patient_uuid) or family["fee_patient_uuid"],
                    card_number=family["card_number"],
                    new_card_created=True,
                    fee_generated=True,
                    notes="Family Card fee sent to billing.",
                )
                connection.commit()
                family = _family_row(connection, family_id)
            return _serialize_family(connection, family) if family else None
        finally:
            connection.close()


def require_family_manager(cookie: str) -> dict[str, Any]:
    import registration as reception

    core.require_session(cookie)
    user = reception.load_openmrs_user(cookie)
    if reception.is_registrar(user):
        return user
    import hospital_admin as admin

    if admin.is_hospital_admin(user):
        return user
    raise ApiError(403, "forbidden", "This action requires Reception access.")


def _enrich_members(family: dict[str, Any], cookie: str) -> dict[str, Any]:
    members = family.get("members") if isinstance(family.get("members"), list) else []
    if not members:
        return family
    try:
        import registration_patient as arrival
    except Exception:
        return family
    enriched = []
    for member in members:
        row = dict(member)
        patient_uuid = _text(row.get("patientUuid"))
        if not patient_uuid:
            enriched.append(row)
            continue
        try:
            profile = arrival.read_patient_profile(patient_uuid, cookie)
        except Exception:
            enriched.append(row)
            continue
        name = " ".join(
            part
            for part in (
                _text(profile.get("givenName")),
                _text(profile.get("middleName")),
                _text(profile.get("familyName")),
            )
            if part
        )
        row["name"] = name or row.get("name") or ""
        row["identifier"] = _text(profile.get("identifier")) or row.get("identifier") or ""
        row["age"] = profile.get("age")
        row["sex"] = _text(profile.get("gender"))
        enriched.append(row)
    family = dict(family)
    family["members"] = enriched
    family["memberCount"] = len(enriched)
    return family


def list_families_response(cookie: str, query: str = "") -> dict[str, Any]:
    require_family_manager(cookie)
    extra_uuids: list[str] = []
    term = _text(query)
    if term:
        try:
            import registration_patient as arrival

            extra_uuids = [
                match["uuid"]
                for match in arrival.search_patient_matches(cookie, term)
                if match.get("uuid")
            ]
        except Exception:
            extra_uuids = []
    families = search_families(term, extra_patient_uuids=extra_uuids)
    return {"status": "ok", "families": families, "query": term}


def get_family_response(family_id: str, cookie: str) -> dict[str, Any]:
    require_family_manager(cookie)
    family = get_family(family_id)
    if not family:
        raise ApiError(404, "family_not_found", "This family was not found.")
    return {"status": "ok", "family": _enrich_members(family, cookie)}


def get_patient_family_response(patient_uuid: str, cookie: str) -> dict[str, Any]:
    require_family_manager(cookie)
    family = family_for_patient(patient_uuid)
    if not family:
        return {"status": "ok", "family": None}
    return {"status": "ok", "family": _enrich_members(family, cookie)}


def add_or_transfer_member(family_id: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_family_manager(cookie)
    patient_uuid = _text(body.get("patientUuid"))
    if not patient_uuid:
        raise ApiError(422, "patient_required", "Select a patient to add to this family.")
    relationship = _text(body.get("relationship")) or DEFAULT_RELATIONSHIP
    member_name = _text(body.get("memberName"))
    member_identifier = _text(body.get("memberIdentifier"))
    if not member_name:
        try:
            import registration_patient as arrival

            profile = arrival.read_patient_profile(patient_uuid, cookie)
            member_name = " ".join(
                part
                for part in (
                    _text(profile.get("givenName")),
                    _text(profile.get("familyName")),
                )
                if part
            )
            member_identifier = member_identifier or _text(profile.get("identifier"))
        except Exception:
            member_name = ""
    family = link_member(
        family_id,
        patient_uuid,
        relationship,
        user,
        member_name=member_name,
        member_identifier=member_identifier,
        confirm_transfer=bool(body.get("confirmTransfer")),
    )
    return {"status": "ok", "family": _enrich_members(family, cookie)}


def create_family_for_existing_patient(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = require_family_manager(cookie)
    patient_uuid = _text(body.get("patientUuid"))
    if not patient_uuid:
        raise ApiError(422, "patient_required", "Select a patient for the new family.")
    if family_for_patient(patient_uuid):
        raise ApiError(
            409,
            "family_membership_exists",
            "This patient already belongs to a family.",
        )
    plan = prepare_family_registration({**body, "familyMode": "new"})
    if plan.get("conflict"):
        return {
            "status": "error",
            "code": "family_exists",
            "message": FAMILY_EXISTS_MESSAGE,
            "families": plan.get("families") or [],
        }
    member_name = _text(body.get("memberName"))
    member_identifier = _text(body.get("memberIdentifier"))
    family = apply_registration(
        patient_uuid,
        plan,
        user,
        member_name=member_name,
        member_identifier=member_identifier,
    )
    return {
        "status": "ok",
        **family,
        "family": _enrich_members(family["family"], cookie) if family.get("family") else None,
    }
