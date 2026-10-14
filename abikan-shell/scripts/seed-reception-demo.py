#!/usr/bin/env python3
"""Create local demo patients, today's appointments, and today's visits."""

from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar

from script_config import required_environment

BASE = os.environ.get("ABIKAN_OPENMRS_URL", "https://localhost").rstrip("/")
AUTH_USER = required_environment("ABIKAN_ADMIN_USER")
AUTH_PASSWORD = required_environment("ABIKAN_ADMIN_PASSWORD")
AUTH = f"{AUTH_USER}:{AUTH_PASSWORD}"
IDENTIFIER_TYPE = "d3153eb0-5e07-11ef-8f7c-0242ac120002"
REG_DESK = "1973e910-160e-42ef-9daf-3f020f62c4cf"
HOSPITAL = "72636eba-29bf-4d6c-97c4-4b04d87a95b5"
OPD_VISIT = "54f43754-c6ce-4472-890e-0f28acaeaea6"
PROVIDER = "05d6752c-5e08-11ef-8f7c-0242ac120002"
SERVICES = [
    "85b10577-7831-47be-b8f2-c84edfbc4eab",
    "8fd5e339-a342-4be7-8800-33d2e4774051",
    "3fe02e14-382a-41e5-b27d-26467ec6b887",
]

PATIENTS = [
    ("Adaeze", "Okafor", "F", "1992-03-15"),
    ("Chinedu", "Okonkwo", "M", "1985-07-22"),
    ("Fatima", "Abdullahi", "F", "1998-11-04"),
    ("Tunde", "Bakare", "M", "1974-01-19"),
    ("Ngozi", "Eze", "F", "2006-05-30"),
    ("Ibrahim", "Musa", "M", "1989-09-12"),
    ("Blessing", "Adeyemi", "F", "1981-02-08"),
    ("Emeka", "Nwosu", "M", "1995-06-17"),
    ("Aisha", "Bello", "F", "2000-08-25"),
    ("John", "Adewale", "M", "1968-12-03"),
]

ctx = ssl._create_unverified_context()
opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ctx),
    urllib.request.HTTPCookieProcessor(CookieJar()),
)


def request(path: str, data=None, method: str | None = None):
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method=method)
    try:
        with opener.open(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")


def login() -> None:
    req = urllib.request.Request(f"{BASE}/openmrs/ws/rest/v1/session")
    req.add_header(
        "Authorization",
        "Basic " + base64.b64encode(AUTH.encode()).decode(),
    )
    with opener.open(req) as resp:
        payload = json.load(resp)
    if not payload.get("authenticated"):
        raise SystemExit("Could not sign in to OpenMRS")


def next_identifier() -> str:
    status, payload = request(
        "/openmrs/module/idgen/generateIdentifier.form?source=1&comment=abikan-demo"
    )
    if status != 200 or not payload or not payload.get("identifiers"):
        raise RuntimeError(f"Could not generate identifier: {payload}")
    return payload["identifiers"][0]


def create_patient(given: str, family: str, gender: str, birthdate: str) -> dict:
    identifier = next_identifier()
    status, payload = request(
        "/openmrs/ws/rest/v1/patient",
        {
            "identifiers": [
                {
                    "identifier": identifier,
                    "identifierType": IDENTIFIER_TYPE,
                    "location": REG_DESK,
                    "preferred": True,
                }
            ],
            "person": {
                "gender": gender,
                "birthdate": birthdate,
                "names": [
                    {
                        "givenName": given,
                        "familyName": family,
                        "preferred": True,
                    }
                ],
            },
        },
    )
    if status not in (200, 201) or not isinstance(payload, dict):
        raise RuntimeError(f"Patient {given} {family} failed ({status}): {payload}")
    return {"uuid": payload["uuid"], "identifier": identifier, "name": f"{given} {family}"}


def create_appointment(patient_uuid: str, hour: int, minute: int, service_uuid: str) -> dict:
    start = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(minutes=15)
    status, payload = request(
        "/openmrs/ws/rest/v1/appointment",
        {
            "patientUuid": patient_uuid,
            "serviceUuid": service_uuid,
            "startDateTime": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "endDateTime": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "providers": [{"uuid": PROVIDER}],
            "locationUuid": REG_DESK,
            "appointmentKind": "Scheduled",
            "comments": "Hospital EMR reception demo",
        },
    )
    if status not in (200, 201) or not isinstance(payload, dict):
        raise RuntimeError(f"Appointment failed ({status}): {payload}")
    return payload


def change_status(appointment_uuid: str, status_name: str) -> None:
    status, payload = request(
        f"/openmrs/ws/rest/v1/appointments/{appointment_uuid}/status-change",
        {"toStatus": status_name},
    )
    if status not in (200, 201, 204):
        status, payload = request(
            f"/openmrs/ws/rest/v1/appointment/{appointment_uuid}/changeStatus?toStatus={status_name}",
            {},
        )
    if status not in (200, 201, 204):
        print(f"  status {status_name} not set ({status}): {str(payload)[:160]}")


def create_visit(patient_uuid: str, hour: int) -> dict:
    start = datetime.now().replace(hour=hour, minute=10, second=0, microsecond=0)
    status, payload = request(
        "/openmrs/ws/rest/v1/visit",
        {
            "patient": patient_uuid,
            "visitType": OPD_VISIT,
            "location": HOSPITAL,
            "startDatetime": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
        },
    )
    if status not in (200, 201) or not isinstance(payload, dict):
        raise RuntimeError(f"Visit failed ({status}): {payload}")
    return payload


def main() -> None:
    login()
    created = []
    for given, family, gender, birthdate in PATIENTS:
        patient = create_patient(given, family, gender, birthdate)
        created.append(patient)
        print(f"Patient {patient['identifier']} {patient['name']}")

    hours = [8, 9, 10, 11, 12, 13, 14, 15]
    statuses = ["Scheduled", "CheckedIn", "Scheduled", "Completed", "Scheduled", "Cancelled", "CheckedIn", "Scheduled"]
    for index, hour in enumerate(hours):
        patient = created[index]
        appointment = create_appointment(
            patient["uuid"], hour, 0, SERVICES[index % len(SERVICES)]
        )
        print(f"Appointment {hour:02d}:00 {patient['name']} {appointment.get('status')}")
        if statuses[index] != "Scheduled":
            change_status(appointment.get("uuid", ""), statuses[index])

    for index, hour in enumerate([8, 9, 10, 11, 13, 14]):
        visit = create_visit(created[index]["uuid"], hour)
        print(f"Visit {hour:02d}:10 {created[index]['name']} {visit.get('uuid')}")

    print(f"\nCreated {len(created)} patients, 8 appointments, 6 visits.")


if __name__ == "__main__":
    main()
