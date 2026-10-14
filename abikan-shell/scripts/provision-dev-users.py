#!/usr/bin/env python3
"""Create development Hospital EMR OpenMRS roles and users.

Idempotent. Does not modify patients, visits, invoices, beds, or locations.
Password is for this development environment only.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from script_config import required_environment


BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
ADMIN_USER = ""
ADMIN_PASSWORD = ""
DEV_PASSWORD = ""

CTX = ssl._create_unverified_context()

ACCOUNTS = [
    {
        "username": "abikan.admin",
        "given": "Hospital EMR",
        "family": "Administrator",
        "workplace": "administration",
        "roles": [],
        "existing": True,
        "provider": False,
    },
    {
        "username": "admin.abikan",
        "given": "Hospital EMR",
        "family": "Administrator",
        "workplace": "administration",
        "roles": ["SuperAdmin", "Provider"],
        "provider": True,
    },
    {
        "username": "hospitaladmin.abikan",
        "given": "Hospital",
        "family": "Administrator",
        "workplace": "administration",
        "roles": ["Abikan:Hospital Admin"],
        "provider": False,
    },
    {
        "username": "registration.abikan",
        "given": "Registration",
        "family": "Staff",
        "workplace": "registration",
        "roles": ["Abikan:Registration"],
        "provider": False,
    },
    {
        "username": "reception.abikan",
        "given": "Reception",
        "family": "Staff",
        "workplace": "reception",
        "roles": ["Abikan:Reception"],
        "provider": False,
    },
    {
        "username": "doctor.abikan",
        "given": "Clinical",
        "family": "Doctor",
        "workplace": "clinical",
        "roles": ["Abikan:Doctor"],
        "provider": True,
    },
    {
        "username": "nurse.abikan",
        "given": "Nursing",
        "family": "Staff",
        "workplace": "nursing",
        "roles": ["Abikan:Nursing"],
        "provider": True,
    },
    {
        "username": "pharmacy.abikan",
        "given": "Pharmacy",
        "family": "Staff",
        "workplace": "pharmacy",
        "roles": ["Abikan:Pharmacy", "Abikan:Pharmacy Inventory"],
        "provider": False,
    },
    {
        "username": "lab.abikan",
        "given": "Laboratory",
        "family": "Staff",
        "workplace": "laboratory",
        "roles": ["Abikan:Laboratory"],
        "provider": False,
    },
    {
        "username": "radiology.abikan",
        "given": "Radiology",
        "family": "Staff",
        "workplace": "radiology",
        "roles": ["Abikan:Radiology"],
        "provider": True,
    },
    {
        "username": "accountant.abikan",
        "given": "Accountant",
        "family": "Staff",
        "workplace": "accountant",
        "roles": ["Abikan:Accountant"],
        "provider": False,
    },
]

# Existing OpenMRS allergy privileges. Attached to Doctor/Nursing only so
# OpenMRS authorization matches Hospital EMR canWrite. Get Allergies is required
# by the OpenMRS allergy save path (it re-reads the record after write).
# Stored in OpenMRS MySQL role_privilege and therefore survives container
# restart on the DB volume.
ALLERGY_WRITE_PRIVILEGES = [
    "Get Allergies",
    "Add Allergies",
    "Edit Allergies",
    "Remove Allergies",
]

ROLES = [
    {
        "name": "Abikan:Registration",
        "description": "Hospital EMR Reception department (compatibility role name)",
        "inherited": ["Registration-App"],
        "privileges": [],
    },
    {
        "name": "Abikan:Reception",
        "description": "Hospital EMR Reception department",
        "inherited": ["Registration-App"],
        "privileges": [],
    },
    {
        "name": "Abikan:Doctor",
        "description": "Hospital EMR Clinical / Doctor department",
        "inherited": ["Clinical-App", "Provider"],
        "privileges": list(ALLERGY_WRITE_PRIVILEGES),
    },
    {
        "name": "Abikan:Nursing",
        "description": "Hospital EMR Nursing department",
        "inherited": ["InPatient-App"],
        "privileges": list(ALLERGY_WRITE_PRIVILEGES),
    },
    {
        "name": "Abikan:Pharmacy",
        "description": "Hospital EMR Pharmacy department",
        "inherited": ["Bahmni-App-User-Login"],
        "privileges": [
            "bahmni:clinical:dispense",
            "Get Patients",
            "Get People",
            "Get Visits",
            "Get Encounters",
            "Get Orders",
            "Get Concepts",
            "View Patients",
            "Get Providers",
        ],
    },
    {
        "name": "Abikan:Pharmacy Inventory",
        "description": "Authorized to receive and adjust pharmacy stock",
        "inherited": ["Abikan:Pharmacy"],
        "privileges": [
            "abikan:pharmacy:inventory",
        ],
    },
    {
        "name": "Abikan:Laboratory",
        "description": "Hospital EMR Laboratory department",
        # Bahmni-App-User-Login grants Edit Users and Get Users. Laboratory
        # needs the Lab workflow role only; the remaining read privileges are
        # listed explicitly below.
        "inherited": ["Lab"],
        "privileges": [
            "Get People",
            "Get Visits",
            "Get Encounters",
            "Get Concepts",
            "View Patients",
            "Get Providers",
        ],
    },
    {
        "name": "Abikan:Radiology",
        "description": "Hospital EMR Radiology department",
        "inherited": ["Radiology-App"],
        "privileges": [
            "Get Orders",
        ],
    },
    {
        "name": "Abikan:Accountant",
        "description": "Hospital EMR Accountant / Cashier department",
        "inherited": ["Bahmni-App-User-Login"],
        "privileges": [
            "abikan:accountant",
            "Get Patients",
            "Get People",
            "Get Visits",
            "View Patients",
            "Get Providers",
        ],
    },
    {
        "name": "Abikan:Hospital Admin",
        "description": "Hospital staff accounts and approved department access",
        "inherited": [],
        "privileges": [
            "abikan:admin:staff",
            "abikan:admin:analytics",
            "abikan:admin:audit-read",
            # OpenMRS SessionController resolves the current provider on every
            # session read and rejects otherwise-valid logins without this.
            "Get Providers",
        ],
    },
]


def request(method: str, path: str, body: dict | None = None) -> dict | list:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": _basic(),
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {error.code}: {detail[:800]}") from error


def _basic() -> str:
    import base64

    token = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
    return f"Basic {token}"


def get(path: str) -> dict | list:
    return request("GET", path)


def post(path: str, body: dict) -> dict | list:
    return request("POST", path, body)


def role_uuid(name: str) -> str | None:
    payload = get(f"/openmrs/ws/rest/v1/role?q={urllib.parse.quote(name)}&v=custom:(name,uuid)&limit=50")
    for row in payload.get("results") or []:
        if row.get("name") == name:
            return row.get("uuid")
    return None


def user_by_username(username: str) -> dict | None:
    payload = get(
        f"/openmrs/ws/rest/v1/user?username={urllib.parse.quote(username)}"
        "&v=custom:(uuid,username,retired,roles:(name),userProperties,person:(uuid,display))"
    )
    for row in payload.get("results") or []:
        if row.get("username") == username and not row.get("retired"):
            return row
    return None


def privilege_uuid(name: str, privs: dict[str, str]) -> str | None:
    if name in privs:
        return privs[name]
    try:
        payload = get(f"/openmrs/ws/rest/v1/privilege/{urllib.parse.quote(name, safe='')}")
    except RuntimeError as error:
        if "-> 404" in str(error):
            return None
        raise
    uuid = payload.get("uuid") if isinstance(payload, dict) else None
    if uuid:
        privs[name] = str(uuid)
        return str(uuid)
    return None


def ensure_privilege(name: str, description: str) -> None:
    _roles, privs = catalogs()
    if privilege_uuid(name, privs):
        print(f"privilege exists: {name}")
        return
    post(
        "/openmrs/ws/rest/v1/privilege",
        {"name": name, "description": description},
    )
    print(f"privilege created: {name}")


def catalogs() -> tuple[dict[str, str], dict[str, str]]:
    roles = {
        row["name"]: row["uuid"]
        for row in get("/openmrs/ws/rest/v1/role?v=custom:(name,uuid)&limit=200").get("results") or []
        if row.get("name")
    }
    privs: dict[str, str] = {}
    admin = user_by_username(ADMIN_USER) or {}
    if admin.get("uuid"):
        full = get(
            f"/openmrs/ws/rest/v1/user/{admin['uuid']}?v=custom:(privileges:(name,uuid))"
        )
        for item in full.get("privileges") or []:
            if item.get("name") and item.get("uuid"):
                privs[item["name"]] = item["uuid"]
    payload = get("/openmrs/ws/rest/v1/privilege?v=custom:(name,uuid)&limit=500")
    for item in payload.get("results") or []:
        if item.get("name") and item.get("uuid"):
            privs[item["name"]] = item["uuid"]
    return roles, privs


def ensure_role(spec: dict) -> str:
    roles, privs = catalogs()
    existing = roles.get(spec["name"]) or role_uuid(spec["name"])
    missing_roles = [name for name in spec["inherited"] if name not in roles]
    missing_privs = [name for name in spec["privileges"] if not privilege_uuid(name, privs)]
    if missing_roles or missing_privs:
        raise RuntimeError(f"{spec['name']} missing {missing_roles} {missing_privs}")
    body = {
        "name": spec["name"],
        "description": spec["description"],
        "inheritedRoles": [{"uuid": roles[name], "name": name} for name in spec["inherited"]],
        "privileges": [{"uuid": privs[name], "name": name} for name in spec["privileges"]],
    }
    if existing:
        request("POST", f"/openmrs/ws/rest/v1/role/{existing}", body)
        print(f"role updated: {spec['name']}")
        return existing
    created = post("/openmrs/ws/rest/v1/role", body)
    print(f"role created: {spec['name']}")
    return created.get("uuid") or role_uuid(spec["name"])


def ensure_person(given: str, family: str) -> str:
    created = post(
        "/openmrs/ws/rest/v1/person",
        {
            "names": [{"givenName": given, "familyName": family, "preferred": True}],
            "gender": "U",
        },
    )
    uuid = created.get("uuid")
    if not uuid:
        raise RuntimeError(f"person create failed for {given} {family}: {created}")
    return uuid


def ensure_provider(person_uuid: str, identifier: str) -> None:
    payload = get(
        f"/openmrs/ws/rest/v1/provider?q={urllib.parse.quote(identifier)}"
        "&v=custom:(uuid,identifier,retired)&limit=10"
    )
    for row in payload.get("results") or []:
        if row.get("identifier") == identifier and not row.get("retired"):
            print(f"provider exists: {identifier}")
            return
    post(
        "/openmrs/ws/rest/v1/provider",
        {"person": person_uuid, "identifier": identifier},
    )
    print(f"provider created: {identifier}")


def role_privilege_names(role_uuid: str, roles: dict[str, str], seen: set[str] | None = None) -> set[str]:
    """Flatten a role's direct and inherited privilege names."""
    if seen is None:
        seen = set()
    if not role_uuid or role_uuid in seen:
        return set()
    seen.add(role_uuid)
    full = get(f"/openmrs/ws/rest/v1/role/{role_uuid}?v=full")
    names = {
        str(item["name"])
        for item in (full.get("privileges") or [])
        if isinstance(item, dict) and item.get("name")
    }
    for inherited in full.get("inheritedRoles") or []:
        if not isinstance(inherited, dict):
            continue
        inherited_uuid = inherited.get("uuid") or roles.get(str(inherited.get("name") or ""))
        names |= role_privilege_names(str(inherited_uuid or ""), roles, seen)
    return names


def ensure_superadmin_can_assign_approved_roles() -> None:
    """OpenMRS only lets an account assign a role if it already holds every privilege of that role.

    SuperAdmin is a fixed privilege catalogue. Custom Hospital EMR privileges created later are
    not added automatically, which is why admin.abikan could not assign Accountant.
    Merge those privileges onto SuperAdmin without replacing the existing SuperAdmin set.
    """
    roles, privs = catalogs()
    superadmin_uuid = roles.get("SuperAdmin") or role_uuid("SuperAdmin")
    if not superadmin_uuid:
        raise RuntimeError("SuperAdmin role is missing")
    needed: set[str] = set()
    for spec in ROLES:
        needed.update(spec["privileges"])
    full = get(f"/openmrs/ws/rest/v1/role/{superadmin_uuid}?v=custom:(privileges:(uuid,name))")
    existing = [
        {"uuid": item["uuid"], "name": item["name"]}
        for item in (full.get("privileges") or [])
        if isinstance(item, dict) and item.get("uuid") and item.get("name")
    ]
    have = {item["name"] for item in existing}
    missing = sorted(name for name in needed if name not in have)
    unresolved = [name for name in missing if not privilege_uuid(name, privs)]
    if unresolved:
        raise RuntimeError(f"SuperAdmin cannot receive unknown privileges: {unresolved}")
    if not missing:
        print("SuperAdmin already has approved-role assignment privileges")
        return
    # OpenMRS can 500 if the entire SuperAdmin catalogue is posted in one request.
    # Add only the missing privileges, one at a time, keeping the existing set.
    added: list[str] = []
    for name in missing:
        full = get(f"/openmrs/ws/rest/v1/role/{superadmin_uuid}?v=custom:(privileges:(uuid,name))")
        existing = [
            {"uuid": item["uuid"], "name": item["name"]}
            for item in (full.get("privileges") or [])
            if isinstance(item, dict) and item.get("uuid") and item.get("name")
        ]
        if name in {item["name"] for item in existing}:
            continue
        try:
            request(
                "POST",
                f"/openmrs/ws/rest/v1/role/{superadmin_uuid}",
                {"privileges": existing + [{"uuid": privs[name], "name": name}]},
            )
        except RuntimeError as error:
            print(f"SuperAdmin privilege skip {name}: {error}")
            continue
        added.append(name)
    print(f"SuperAdmin privileges merged: {', '.join(added)}")


def ensure_user(account: dict, roles_by_name: dict[str, str]) -> None:
    existing = user_by_username(account["username"])
    properties = {"abikan.workplace": account["workplace"]}
    role_refs = []
    for name in account["roles"]:
        uuid = roles_by_name.get(name)
        if not uuid:
            raise RuntimeError(f"missing role {name} for {account['username']}")
        role_refs.append({"uuid": uuid, "name": name})
    if existing:
        body = {
            "userProperties": {
                **(existing.get("userProperties") or {}),
                **properties,
            }
        }
        if role_refs:
            body["roles"] = role_refs
        request("POST", f"/openmrs/ws/rest/v1/user/{existing['uuid']}", body)
        print(f"user updated: {account['username']}")
        person_uuid = (existing.get("person") or {}).get("uuid")
        if account.get("provider") and person_uuid:
            ensure_provider(person_uuid, account["username"])
        return

    person_uuid = ensure_person(account["given"], account["family"])
    post(
        "/openmrs/ws/rest/v1/user",
        {
            "username": account["username"],
            "password": DEV_PASSWORD,
            "person": person_uuid,
            "roles": role_refs,
            "userProperties": properties,
        },
    )
    print(f"user created: {account['username']}")
    if account.get("provider"):
        ensure_provider(person_uuid, account["username"])


def main() -> int:
    global ADMIN_USER, ADMIN_PASSWORD, DEV_PASSWORD
    ADMIN_USER = required_environment("ABIKAN_ADMIN_USER")
    ADMIN_PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
    DEV_PASSWORD = required_environment("ABIKAN_DEV_PASSWORD")
    session = get("/openmrs/ws/rest/v1/session")
    if not session.get("authenticated"):
        print("Admin sign-in failed.", file=sys.stderr)
        return 1
    ensure_privilege("abikan:accountant", "Hospital EMR Accountant / Cashier")
    ensure_privilege(
        "abikan:pharmacy:inventory",
        "Hospital EMR Pharmacy inventory receive and adjust",
    )
    ensure_privilege(
        "abikan:admin:staff",
        "Hospital EMR Hospital Admin staff accounts and department access",
    )
    ensure_privilege(
        "abikan:admin:analytics",
        "Hospital EMR Hospital Admin hospital overview analytics",
    )
    ensure_privilege(
        "abikan:admin:audit-read",
        "Hospital EMR Hospital Admin staff administration audit history",
    )
    for spec in ROLES:
        ensure_role(spec)
    ensure_superadmin_can_assign_approved_roles()
    roles_by_name, _privs = catalogs()
    for account in ACCOUNTS:
        ensure_user(account, roles_by_name)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
