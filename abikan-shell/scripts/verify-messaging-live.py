#!/usr/bin/env python3
"""Exercise live department and staff attention requests for every department account."""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
API = os.environ.get("ABIKAN_API_URL", "http://127.0.0.1:8787").rstrip("/")
PASSWORD = (
    os.environ.get("ABIKAN_ADMIN_PASSWORD")
    or os.environ.get("OPENMRS_PASSWORD")
    or "Admin123"
)
TLS = ssl._create_unverified_context()

USERS = {
    "reception.abikan": "reception",
    "doctor.abikan": "clinical",
    "nurse.abikan": "nursing",
    "lab.abikan": "laboratory",
    "pharmacy.abikan": "pharmacy",
    "accountant.abikan": "accountant",
    "radiology.abikan": "radiology",
    "admin.abikan": "administration",
}
WORKPLACES = tuple(dict.fromkeys(USERS.values()))


def login(username: str) -> str:
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=TLS),
        urllib.request.HTTPCookieProcessor(jar),
    )
    token = base64.b64encode(f"{username}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(
        f"{BASE}/openmrs/ws/rest/v1/session",
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
    )
    with opener.open(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if not payload.get("authenticated"):
        raise RuntimeError(f"{username}: authentication failed")
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in jar)


def request(method: str, path: str, cookie: str, body: dict | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json", "Cookie": cookie}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"body": raw[:300]}
        return error.code, payload


def attention(cookie: str, conversation: str) -> tuple[int, dict]:
    return request("POST", f"/messages/conversations/{conversation}/attention", cookie, {})


def main() -> int:
    cookies: dict[str, str] = {}
    failures: list[dict] = []
    counts = {"department": 0, "staff": 0}

    for username in USERS:
        try:
            cookies[username] = login(username)
        except Exception as error:  # noqa: BLE001
            failures.append({"check": "login", "user": username, "error": str(error)})

    for username, current_workplace in USERS.items():
        cookie = cookies.get(username)
        if not cookie:
            continue
        status, staff_payload = request("GET", "/messages/staff", cookie)
        staff = staff_payload.get("staff", []) if isinstance(staff_payload, dict) else []
        if status != 200 or not staff:
            failures.append({
                "check": "staff_directory",
                "user": username,
                "status": status,
                "response": staff_payload,
            })
            continue

        status, workplace_payload = request("GET", "/messages/workplaces", cookie)
        if status != 200:
            failures.append({
                "check": "department_directory",
                "user": username,
                "status": status,
                "response": workplace_payload,
            })

        for workplace in WORKPLACES:
            if workplace == current_workplace:
                continue
            status, created = request(
                "POST",
                "/messages/conversations",
                cookie,
                {"type": "department", "workplace": workplace},
            )
            conversation = (created.get("conversation") or {}).get("id")
            attention_status, attention_payload = (
                attention(cookie, conversation) if status == 200 and conversation else (0, {})
            )
            counts["department"] += 1
            if status != 200 or attention_status != 200:
                failures.append({
                    "check": "department_call",
                    "user": username,
                    "target": workplace,
                    "createStatus": status,
                    "attentionStatus": attention_status,
                    "response": attention_payload or created,
                })

        for target in staff:
            target_username = target.get("username")
            if not target_username or target_username.lower() == username.lower():
                continue
            status, created = request(
                "POST",
                "/messages/conversations",
                cookie,
                {"type": "direct", "username": target_username},
            )
            conversation = (created.get("conversation") or {}).get("id")
            attention_status, attention_payload = (
                attention(cookie, conversation) if status == 200 and conversation else (0, {})
            )
            counts["staff"] += 1
            if status != 200 or attention_status != 200:
                failures.append({
                    "check": "staff_call",
                    "user": username,
                    "target": target_username,
                    "createStatus": status,
                    "attentionStatus": attention_status,
                    "response": attention_payload or created,
                })

    report = {
        "usersTested": len(cookies),
        "callsAttempted": counts,
        "failures": failures,
        "passed": not failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
