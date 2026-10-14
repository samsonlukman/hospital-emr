"""Hospital-managed HMO assignments.

The patient remains in OpenMRS. This small local registry stores only the
patient's coverage grouping and the selected HMO body.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import accountant
import patient_directory
import registration
import hospital_admin
from server import ApiError, require_session

HMO_DB_PATH = os.environ.get("ABIKAN_HMO_DB", "/var/lib/abikan/hmo.sqlite3")
SCHEMES = {
    "NHIA": (
        "Aiico Multishield",
        "Metro health",
        "Pro health",
        "Hygeia",
        "International health",
        "Sunu health",
        "Songhai",
        "Princeton",
        "United Health",
        "Police NHIA",
        "Integrated",
        "Axamazard",
        "Health care international",
        "Novo Health",
    ),
    "HMO (Private)": ("Prohealth", "Metro health", "Mayyoit", "United Health", "Reliance"),
}
READ_ROLES = {"SuperAdmin", "System Developer", "Abikan:Nursing", "Nurse"}
READ_PRIVILEGES = {"app:adt", "app:registration", "abikan:accountant", "app:admin"}


def _db(path: str | None = None) -> sqlite3.Connection:
    selected = Path(path or HMO_DB_PATH)
    selected.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(selected)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hmo_assignments (
          patient_uuid TEXT PRIMARY KEY,
          patient_name TEXT NOT NULL,
          hospital_number TEXT NOT NULL,
          scheme TEXT NOT NULL,
          body TEXT NOT NULL,
          assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          assigned_by TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _user(cookie: str) -> dict[str, Any]:
    require_session(cookie)
    return accountant.load_openmrs_user(cookie)


def _can_read(user: dict[str, Any]) -> bool:
    roles = set(user.get("roles") or [])
    privileges = set(user.get("privileges") or [])
    return (
        bool(roles & READ_ROLES)
        or bool(privileges & READ_PRIVILEGES)
        or registration.is_registrar(user)
        or accountant.is_accountant(user)
        or hospital_admin.is_hospital_admin(user)
    )


def _require_reader(cookie: str) -> dict[str, Any]:
    user = _user(cookie)
    if not _can_read(user):
        raise ApiError(403, "forbidden", "HMO records are not available to this department.")
    return user


def _require_writer(cookie: str) -> dict[str, Any]:
    user = _user(cookie)
    if not registration.is_registrar(user) and not hospital_admin.is_hospital_admin(user):
        raise ApiError(403, "forbidden", "Only Reception can add patients to the HMO list.")
    return user


def metadata(cookie: str) -> dict[str, Any]:
    _require_reader(cookie)
    return {"schemes": {key: list(value) for key, value in SCHEMES.items()}}


def list_assignments(cookie: str, query: str = "") -> dict[str, Any]:
    _require_reader(cookie)
    term = query.strip().casefold()
    with _db() as connection:
        rows = connection.execute(
            """
            SELECT patient_uuid, patient_name, hospital_number, scheme, body, assigned_at
            FROM hmo_assignments
            ORDER BY patient_name COLLATE NOCASE
            """
        ).fetchall()
    assignments = [
        dict(row)
        for row in rows
        if not term
        or term in str(row["patient_name"]).casefold()
        or term in str(row["hospital_number"]).casefold()
        or term in str(row["body"]).casefold()
    ]
    return {"assignments": assignments}


def assign_patient(body: dict[str, Any], cookie: str) -> dict[str, Any]:
    user = _require_writer(cookie)
    patient_uuid = str(body.get("patientUuid") or "").strip()
    scheme = str(body.get("scheme") or "").strip()
    hmo_body = str(body.get("body") or "").strip()
    if not patient_uuid:
        raise ApiError(422, "patient_required", "Choose a patient.")
    if scheme not in SCHEMES:
        raise ApiError(422, "scheme_required", "Choose NHIA or HMO (Private).")
    if hmo_body not in SCHEMES[scheme]:
        raise ApiError(422, "body_required", "Choose a body under the selected HMO type.")
    identity = patient_directory.load_patient_identity(patient_uuid)
    with _db() as connection:
        connection.execute(
            """
            INSERT INTO hmo_assignments
              (patient_uuid, patient_name, hospital_number, scheme, body, assigned_by)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(patient_uuid) DO UPDATE SET
              patient_name=excluded.patient_name,
              hospital_number=excluded.hospital_number,
              scheme=excluded.scheme,
              body=excluded.body,
              assigned_at=CURRENT_TIMESTAMP,
              assigned_by=excluded.assigned_by
            """,
            (
                patient_uuid,
                identity["name"],
                identity["mrn"],
                scheme,
                hmo_body,
                str(user.get("username") or ""),
            ),
        )
    return {
        "status": "ok",
        "assignment": {
            "patientUuid": patient_uuid,
            "patientName": identity["name"],
            "hospitalNumber": identity["mrn"],
            "scheme": scheme,
            "body": hmo_body,
        },
    }
