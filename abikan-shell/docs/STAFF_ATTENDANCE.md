# Staff Log (attendance)

Hospital EMR records one hospital-day attendance session against the **existing staff record**. There is no second staff identity, no fingerprint hardware, and no biometric SDK.

Staff see **Staff Log**, not engines, codes of systems, or record identifiers.

## Who uses what

| Surface | Who | What they do |
|---------|-----|----------------|
| `/abikan/log` | Shared front-desk phone or tablet | Enter a staff code. The terminal then shows **SIGN IN** or **SIGN OUT**. Sign-in takes a photo |
| Administration → Log | Hospital Admin | See who signed in and out, filtered by date, staff, workplace, and status |
| Administration → Staff directory | Hospital Admin | Create or replace a staff attendance code on an existing staff record |

The terminal does not show other people’s history. Unknown codes cannot self-register.

## One session per day

Hospital local date uses `ABIKAN_HOSPITAL_TIMEZONE` (default `Africa/Lagos`). The server clock is the only clock that counts.

| State | Meaning |
|-------|---------|
| `NOT_SIGNED_IN` | No session yet today |
| `SIGNED_IN` | Signed in today, not yet signed out |
| `SIGNED_OUT` | Attendance completed for today |

Rules:

- Sign in creates today’s record if none exists.
- A second sign-in the same day returns the current record. It does not create another.
- Sign out is allowed only after a valid sign-in for today.
- After sign-out, neither sign-in nor sign-out can create another session that day. The completed record is returned.
- The next hospital calendar day starts a new session.
- Sign-in requires a live photo from the terminal camera. That photo is kept only for the current hospital day, then deleted. The rest of the attendance record stays.

## Staff codes

Hospital Admin assigns a unique 4–8 character staff code on the staff record. The code is **not** the person identifier and is not a second user account.

Invalid codes receive a generic refusal. The terminal never accepts an arbitrary staff identifier in place of the code. Repeated invalid attempts are throttled.

## Persistence

Attendance sessions and staff codes are stored in SQLite on the Hospital EMR persistent volume (`ABIKAN_ATTENDANCE_DB`, default `/var/lib/abikan/attendance.sqlite3`). Staff identity continues to come from the existing hospital staff directory.

## HTTP (technical)

Terminal (authorized by `ABIKAN_ATTENDANCE_TERMINAL_SECRET` / `X-Hospital EMR-Terminal-Key`, or Hospital Admin cookie):

- `GET /openmrs/abikan-api/attendance/terminal`
- `POST /openmrs/abikan-api/attendance/status` `{ "code": "482193" }`
- `POST /openmrs/abikan-api/attendance/sign-in` `{ "code": "482193", "photo": "<jpeg>" }`
- `POST /openmrs/abikan-api/attendance/sign-out` `{ "code": "482193" }`

Admin (Hospital Administration required):

- `GET /openmrs/abikan-api/admin/log`
- `GET /openmrs/abikan-api/admin/log/{session}/photo`
- `GET /openmrs/abikan-api/admin/log/summary`
- `GET /openmrs/abikan-api/admin/staff/{id}/attendance-code`
- `POST /openmrs/abikan-api/admin/staff/{id}/attendance-code`

## Authorization

- `/abikan/log` records a staff-code action. It does not open Administration.
- Admin → Log and staff-code assignment require Hospital Administration on the server, not only a hidden menu.
- Ordinary staff cannot set someone else’s staff code.

## What is not in this release

- Fingerprint hardware, phone biometric APIs, WebAuthn, or biometric SDKs
- Multiple shifts per calendar day
- Self-service code registration on the terminal
- Changing OpenMRS core or unrelated EMR modules

## Backup

| File | Contents |
|------|----------|
| `admin-audit.sqlite3` | Staff account and staff-code administration activity |
| `attendance.sqlite3` | Staff log sessions and staff attendance codes |
| `attendance-photos/` | Sign-in photos for the current hospital day only |

Hospital calendar days follow `ABIKAN_HOSPITAL_TIMEZONE`. Existing OpenMRS person/user records remain in the OpenMRS database backup.

Production terminals should set `ABIKAN_ATTENDANCE_TERMINAL_SECRET`. The browser may send `X-Hospital EMR-Terminal-Key`, or the hospital proxy can inject that header. The secret authorizes the shared device; the staff code identifies the person.
