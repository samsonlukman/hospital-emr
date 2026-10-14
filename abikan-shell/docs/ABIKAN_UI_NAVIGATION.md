# Hospital EMR UI navigation

Date: **19 Aug 2026** (Pharmacy department UX, after Nursing). Previous: Nursing department UX, Reception terminology, 18 Aug 2026 login and navigation repair.

Staff should always know three things:

1. Where am I?
2. What can I do?
3. Where do I go next?

Hospital EMR is one hospital application with departments. The screens reuse existing work. This document describes the shell, landing pages, and menus — not the consultation, bed, or payment engines.

---

## Application shell

Every signed-in screen uses the same layout.

**Header**

- Hospital EMR
- Current department
- Patient search
- Notification indicator (no live alerts yet)
- User menu: display name, username, Sign out

Admin also sees **Switch department**. Other staff do not.

**Sidebar**

Only the current department’s functions. No room list, no OPD codes, no product names from other systems.

**Main**

The existing department screen.

---

## Login → department

There is no workplace picker on login.

| Username | Lands on |
|---|---|
| `admin.abikan` | Administration Home (`#/home`) |
| `reception.abikan` | Reception (`#/reception`) |
| `registration.abikan` | Reception (`#/reception`) — compatibility account |
| `doctor.abikan` | Clinical (`#/doctor`) |
| `nurse.abikan` | Nursing (`#/nursing`) |
| `pharmacy.abikan` | Pharmacy (`#/pharmacy`) |
| `lab.abikan` | Laboratory (`#/laboratory`) |
| `radiology.abikan` | Radiology (`#/radiology`) |
| `accountant.abikan` | Accountant (`#/accountant`) |

The session location used underneath is hidden. See `ABIKAN_USERS_ROLES_WORKPLACES.md`.

---

## Department menus

Items marked **Soon** have no screen yet. They are not fake workflows.

### Administration

- Dashboard
- Users — Coming soon
- Departments / Access — Coming soon
- Accommodation Prices
- System Settings — Coming soon

Admin opens other departments with **Switch department**, not a grid of rooms.

### Reception

- Dashboard
- Register Patient
- Patients
- Today's Visits
- Patient Accounts

Reception does not collect payment. After a registration fee is created, send the patient to Accountant.

The dashboard answers what Reception needs to do today using real visit data. Empty days say **No patients today**. There is no Pay button.

### Clinical

- Dashboard
- Patient Queue
- My Patients — Coming soon
- Patients

Consultation and the patient chart are unchanged. Clinical does not collect payment, assign beds, transfer, discharge, or dispense.

### Nursing

- Dashboard
- Ward Board
- Patients
- Admissions
- Transfers
- Discharges

The dashboard answers **who is where** using the existing bed board: occupied beds, available beds, and patients waiting for a bed. The Ward Board is the main workspace. Nursing can assign, transfer, and discharge with existing permissions. There is no payment button. Payment status, when shown, stays informational: PAID, PARTIALLY PAID, OUTSTANDING. See `NURSING_UI_IMPLEMENTATION.md`.

### Pharmacy

- Dashboard
- Prescriptions
- Ready to Dispense
- Dispensed
- Drug Catalogue — Coming soon
- Stock — Coming soon

`pharmacy.abikan` lands on `#/pharmacy`. Exclusive screens, not one scrolling page. Payment and dispensing stay separate: the pharmacist never collects payment. Counts come from the live prescription queue. See `PHARMACY_UI_IMPLEMENTATION.md`.

### Laboratory

- Dashboard
- Orders
- Pending — Coming soon
- Sample Collection — Coming soon
- Results — Coming soon

No invented OpenELIS workflow.

### Radiology

- Dashboard
- Orders
- Worklist — Coming soon
- Reports — Coming soon

No invented imaging worklist or reporting.

### Accountant

- Dashboard
- Outstanding
- Payments
- Receipts
- Patient Accounts

Payments still use the existing register-payment path. Accountant does not dispense, assign beds, edit the chart, prescribe, or change accommodation prices.

---

## Patient Account

A shared read model. Staff open it from a patient, or from Reception / Accountant search.

Language:

- Registration
- Consultation
- Laboratory
- Radiology
- Pharmacy
- Accommodation

Shown: Amount, Paid, Outstanding, Status.

Bills still come from the hospital finance system. Hospital EMR does not keep a second ledger.

---

## Admin department switcher

Only SuperAdmin / System Developer.

Departments listed:

- Administration
- Reception
- Clinical
- Nursing
- Pharmacy
- Laboratory
- Radiology
- Accountant

Never listed: OPD-1, OPD-2, Gold Room 203, Silver 207, beds, or other rooms.

---

## Permissions

Menus hide what the user cannot do. The server still returns **401** when not signed in and **403** when the department is wrong.

Examples:

- `registration.abikan` / `reception.abikan` cannot collect payment
- `pharmacy.abikan` cannot collect payment
- `nurse.abikan` cannot change accommodation prices
- `doctor.abikan` cannot assign beds
- `accountant.abikan` cannot dispense

---

## Responsive layout

The header wraps on tablet. The sidebar becomes a toggle menu under 900px. Primary actions stay visible. Do not treat this as a desktop-only product.

---

## What this task did not redesign

Consultation, nursing ward board behaviour, pharmacy dispense engine, Patient Account ledger, accountant payment posting, registration capture, laboratory, radiology imaging, and accommodation tariff storage. Those stay as they were, with department landing and navigation around them.

---

## Login and navigation repair (18 Aug 2026)

Feature development was paused to fix two staff-visible bugs: department menu items opening Administration, and valid Sign in sometimes failing on the first click.

### 1. Root cause of Administration redirects

Sidebar items used bare hashes such as `#ready` and `#orders`. Clicking them replaced `#/pharmacy` or `#/radiology` with `#ready` / `#orders`.

The hash parser treated any unknown value as `"home"`. `workplaceFromRoute("home")` is Administration. The shell then showed the Administration menu and title.

This was not a permission check. It was a routing bug that hid missing or mis-prefixed hashes by sending staff to Administration.

### 2. Routes fixed

Every department menu `href` is now department-owned:

| Item | Hash |
|---|---|
| Pharmacy Dashboard | `#/pharmacy` |
| Pharmacy Prescriptions | `#/pharmacy/prescriptions` |
| Pharmacy Ready to Dispense | `#/pharmacy/ready` (alias `#/pharmacy/ready-to-dispense`) |
| Pharmacy Dispensed | `#/pharmacy/dispensed` |
| Radiology Dashboard | `#/radiology` |
| Radiology Orders | `#/radiology/orders` |
| Laboratory Dashboard | `#/laboratory` |
| Laboratory Orders | `#/laboratory/orders` |
| Nursing Dashboard | `#/nursing` |
| Nursing Ward Board | `#/nursing/ward-board` (alias `#/nursing/wards`) |
| Nursing Patients | `#/nursing/patients` |
| Nursing Admissions | `#/nursing/admissions` |
| Nursing Transfers | `#/nursing/transfers` |
| Nursing Discharges | `#/nursing/discharges` (alias `#/nursing/discharge`) |
| Clinical Dashboard | `#/doctor` |
| Clinical Patient Queue | `#/doctor/queue` |
| Reception Dashboard | `#/reception` (also `#/registration-desk`) |
| Reception Today's Visits | `#/reception/visits` |
| Reception Patients | `#/reception/patients` |
| Reception patient | `#/reception/patient/{uuid}` (also `#/registration/patient/{uuid}`) |
| Reception Patient Account | `#/reception/account/{uuid}` (also `#/patient-account/{uuid}`) |
| Accountant Dashboard | `#/accountant` |
| Accountant Outstanding | `#/accountant/outstanding` |
| Accountant Payments | `#/accountant/payments` |
| Accountant Receipts | `#/accountant/receipts` |
| Administration Dashboard | `#/home` |
| Accommodation Prices | `#/accommodation-settings` |

Bare ids (`#ready`, `#orders`) parse as **unavailable**, not Administration.

### 3. Department route map

| Prefix | Owner |
|---|---|
| `#/pharmacy/*` | Pharmacy |
| `#/laboratory/*` | Laboratory |
| `#/radiology/*` | Radiology |
| `#/nursing/*` | Nursing |
| `#/doctor/*` | Clinical |
| `#/reception/*` | Reception |
| `#/registration-desk/*` and `#/registration/*` | Reception (compatibility) |
| `#/accountant/*` | Accountant |
| `#/home`, `#/accommodation-settings` | Administration |
| `#/patient-account/*` | Patient Account (allowed departments only) |

A route does not silently become another department. If the signed-in person cannot open that department, Hospital EMR shows access denied and keeps their own sidebar.

### 4. Coming Soon behaviour

Unfinished items are **disabled** in the menu (`kind: "soon"`) with a visible **Soon** mark. They are not links. They never navigate.

| Department | Coming Soon |
|---|---|
| Pharmacy | Drug Catalogue, Stock |
| Radiology | Worklist, Reports (the Radiology page also states this honestly) |
| Laboratory | Pending, Sample Collection, Results (the Laboratory page also states this) |
| Clinical | My Patients |
| Administration | Users, Departments / Access, System Settings |

No fake queues, PACS worklists, or OpenELIS screens were added.

### 5. Router fallback behaviour

Parser: `src/app/hashRoute.ts` `parseShellHash`.

Fallback: `src/config/routingPolicy.ts` `fallbackRouteForUser`.

| Who | Unknown hash (`#/not-a-department`) | `#/home` | Other department they cannot open |
|---|---|---|---|
| Normal staff | Rewrite to **their department home** | Rewrite to **their department home** | Stay on that hash, show **access denied**, keep their sidebar. Not Administration |
| SuperAdmin | Stay on the hash, show **Page not available** | Administration | Allowed if they switched or typed it |

Administration is resolved only for an Administration route (`#/home`, accommodation prices) when the user is SuperAdmin / System Developer, or when they use **Switch department**.

### 6. Root cause of first-click login failure

Observed: valid username/password, first Sign in showed a generic invalid-login message, second Sign in with the same credentials worked.

What actually authenticates: `GET /openmrs/ws/rest/v1/session` with HTTP Basic and `credentials: include`. Wrong password returns **200** `{ authenticated: false }`, not always 401. `JSESSIONID` is set on that response (or on the earlier anonymous session probe when the login page loads).

Roles and privileges are already on the session payload after a successful authenticate. The hidden session location is assigned **after** authentication, by name, for the resolved department.

The first click failed for a combination of real causes — not because the password was wrong:

1. **Catch-all error copy.** Login treated *every* thrown error as “username or password is incorrect,” including session-init, user-record, and location-assignment failures after OpenMRS had already authenticated.
2. **Work after authenticate.** Login used to fetch the user again by username and, in an earlier version, listed every login location. A failure there was shown as invalid login. The second click succeeded because `JSESSIONID` already existed from the first attempt.
3. **Destroying the anonymous session before authenticate.** A leftover-cookie cleanup called `DELETE /session` first. That removed the `JSESSIONID` planted by the page-load session probe. The following Basic GET then had to start a new servlet session. In the browser this made the first click more fragile; it was not a second submit of the password.
4. **Logout hash race (related).** After Sign out, hashchange still believed the session was ready and rewrote `#/home` back to the previous department. The next person could inherit a leftover hash (the login screen still showed). Department workspaces did not stay mounted, but the hash leaked.

This environment’s OpenMRS accepted a first Basic GET without a prior cookie when tested with a scripted client. The staff-visible bug was still the UI mapping plus extra work after authenticate. Hospital EMR does **not** auto-submit Sign in twice, sleep, store passwords, or skip authentication.

### 7. Login sequence after the fix

Conceptual states: IDLE → SIGNING IN → AUTHENTICATED → INITIALIZING SESSION → RESOLVING ROLE → ASSIGNING HIDDEN LOCATION IF REQUIRED → READY → DEPARTMENT HOME.

Implementation:

1. Idle: login form. Sign in is disabled until both fields have a value.
2. Signing in: button disabled, label **Signing in…**, in-flight guard blocks a second submit.
3. Plant / keep an anonymous servlet session (`GET /session` without Basic). If that session is already authenticated as someone else, destroy it and plant a new anonymous session.
4. Authenticate **once** with Basic. `{ authenticated: false }` → incorrect username or password. Network failure → unable to connect.
5. Read roles/privileges from the session payload (fallback: user record by uuid). Failure here is **session did not start**, not a bad password.
6. Resolve the department from role / `abikan.workplace`.
7. Assign the hidden session location for that department (`q=` lookup, then tagged login locations if needed). Failure here is **session did not start**.
8. Set the hash to the department home.
9. Reload workspace context and show that department once.

### 8. Error handling

| Situation | Staff message |
|---|---|
| OpenMRS rejects credentials (`authenticated: false` or 401 on login) | Incorrect username or password. |
| Network / server unavailable | Unable to connect. Please try again. |
| Authenticated, but user/location init fails | Signed in, but Hospital EMR could not start your session. Please try again. |
| Typed another department’s hash | You do not have access to this department. |
| SuperAdmin typed an unknown hash | Page not available. |

“Invalid login” is no longer used as a catch-all.

### 9. Logout behaviour

Sign out destroys the OpenMRS session and Hospital EMR cookies, sets React state to unauthenticated **before** changing the hash, and sets `#/home`.

Hashchange reads the latest session state from a ref so it cannot rewrite `#/home` back to the previous department.

`pharmacy.abikan` → Sign out → `radiology.abikan` Sign in once: Radiology only. Pharmacy workspace did not appear. Hash after logout is `#/home`.

### 10. Deep-link authorization

| Example | Result |
|---|---|
| `pharmacy.abikan` + `#/pharmacy` | Pharmacy |
| `pharmacy.abikan` + `#/pharmacy/ready-to-dispense` | Pharmacy, Ready to dispense section |
| `pharmacy.abikan` + `#/accountant` | Access denied, Pharmacy sidebar remains |
| `pharmacy.abikan` + `#/not-a-department` | Rewrite to Pharmacy |
| `admin.abikan` + `#/not-a-department` | Page not available, Administration sidebar remains |
| `admin.abikan` Switch department → Pharmacy | Pharmacy, including Ready to Dispense |

### 11. Account-by-account click-through (browser, 18 Aug 2026)

Password `Admin123`, development only. Live UI at `https://localhost/abikan/` and `https://localhost/`. No patients, visits, invoices, payments, stock, or beds were created or changed.

| Account | One-click Sign in | Visible items | Destination | Not Administration |
|---|---|---|---|---|
| `pharmacy.abikan` | yes (~1s after a prior wrong-password check) | Dashboard, Prescriptions, Ready to Dispense, Dispensed | Pharmacy home / sections | yes |
| | | Drug Catalogue, Stock | Disabled Soon | yes |
| `radiology.abikan` | yes (including after pharmacy leftover hash) | Dashboard, Orders | Radiology imaging orders | yes |
| | | Worklist, Reports | Disabled Soon (page also says Coming soon) | yes |
| `lab.abikan` | yes | Dashboard, Orders | Laboratory | yes |
| | | Pending, Sample Collection, Results | Disabled Soon | yes |
| `nurse.abikan` | yes | Dashboard, Ward Board, Patients, Admissions, Transfers, Discharges | Nursing dashboard / Ward Board / operational lists | yes |
| `doctor.abikan` | yes | Dashboard, Patient Queue | Clinical | yes |
| | | My Patients | Disabled Soon | yes |
| | | Patients | Focuses patient search | yes |
| `reception.abikan` | yes | Dashboard, Patients, Today's Visits | Reception (`#/reception`) | yes |
| | | Register Patient, Patient Accounts | Register dialog / search | yes |
| `registration.abikan` | yes | Same Reception menu | Reception (`#/reception`) | yes |
| `accountant.abikan` | yes | Dashboard, Outstanding, Payments, Receipts | Accountant | yes |
| | | Patient Accounts | Focuses patient search | yes |
| `admin.abikan` | yes | Dashboard | Administration | expected |
| | | Accommodation Prices | Accommodation prices screen | expected |
| | | Users, Departments / Access, System Settings | Disabled Soon | expected |
| | | Switch department → Pharmacy | Pharmacy | switch is explicit |

Wrong password (`pharmacy.abikan` / `WrongPass`): **Incorrect username or password.** Button showed **Signing in…** then re-enabled.

### 12. Build result

```
npm test   → 17 passed
npm run build → tsc --noEmit && vite build, success
bundle → dist/assets/index-D0tAI4Is.js
```

After build, `dist/index.html` was copied to the proxy DocumentRoot so `https://localhost/` matches `/abikan/`.

### 13. Runtime / browser result

Clicked Sign in (not only `curl`). Clicked every visible department menu item for the eight `*.abikan` accounts. Ready to Dispense and Radiology Orders stayed in their departments. Unknown hashes did not become Administration. Cross-department hashes showed access denied. Admin Switch department still works.

### 14. Known limitations

1. Pharmacy Prescriptions, Ready to Dispense, and Dispensed are exclusive department screens. See `PHARMACY_UI_IMPLEMENTATION.md`.
2. Nursing Transfers and Discharges are operational pages on current occupancy, not a second transfer/discharge database. See `NURSING_UI_IMPLEMENTATION.md`.
3. Laboratory and Radiology still have no hospital-wide queue; Orders is the existing department list/search, not invented OpenELIS or PACS.
4. First-click login was verified for each `*.abikan` account in this session. Intermittent network failures can still happen; they now say **Unable to connect**, not incorrect password.
5. `Admin123` remains development-only.
6. Doctor workflow expansion was not started.

Automated route tests: `abikan-shell/src/app/hashRoute.test.ts` (`npm test`).

---

## Files changed in this repair

| File | Change |
|---|---|
| `src/app/hashRoute.ts` | Department-owned parse; unknown ≠ Administration |
| `src/config/routingPolicy.ts` | Staff/admin fallback |
| `src/config/workplaces.ts` | `resolveRouteForUser` |
| `src/config/*Nav.ts` | Department hashes; Soon items |
| `src/app/WorkspaceRouter.tsx` | Access denied / page not available; section scroll |
| `src/workspaces/AccessDenied/*` | Access denied and page not available |
| `src/App.tsx` | Landing, logout state, hashchange ref |
| `src/workspaces/Login/LoginWorkspace.tsx` | Typed errors; Signing in…; in-flight guard |
| `src/services/openmrs/session.ts` | Anonymous session then one Basic authenticate |
| `src/services/openmrs/signIn.ts` | Distinct credential / network / session-init errors |
| `src/services/openmrs/loadWorkspaceContext.ts` | Prefer session user; no extra username search when possible |
| `src/app/hashRoute.test.ts` | Route + fallback tests |

---

## Reception terminology (19 Aug 2026)

Hospital EMR staff see **Reception**, not Registration, as the department name. Registration remains the name of the **Register Patient** action and of the **registration fee**.

OpenMRS location **Registration Desk** was not renamed. Historical visits, encounters, roles `Abikan:Registration`, and user `registration.abikan` were not deleted.

### Accounts

| Account | Role | Lands on | Notes |
|---|---|---|---|
| `reception.abikan` | `Abikan:Reception` | Reception `#/reception` | Preferred interface account. Password `Admin123` (this environment only). |
| `registration.abikan` | `Abikan:Registration` | Reception `#/reception` | Kept for compatibility. Same `app:registration` privilege. Person display is still “Registration Staff”. |

Both inherit Bahmni **Registration-App**. Hidden session location is still Registration Desk.

### Reception routes

| Hash | Result |
|---|---|
| `#/reception` | Reception dashboard |
| `#/reception/patients` | Same dashboard; focuses patient search |
| `#/reception/visits` | Same dashboard; today's visits table |
| `#/reception/patient/{uuid}` | Existing reception patient / registration-fee screen |
| `#/reception/account/{uuid}` | Patient Account (view). No Pay button |
| `#/registration-desk` | Same dashboard (compatibility) |
| `#/registration/patient/{uuid}` | Same patient screen (compatibility) |
| `#/reception/not-a-screen` | Reception, not Administration |
| `#/accountant` (as reception user) | Access denied, Reception sidebar remains |

### Dashboard

Today's overview uses real visit counts. Zero is allowed when the visit search returns none; the table then says **No patients today**. Patient Accounts is a **View** action (search), not an invented outstanding total. Quick actions: Register Patient, Find Patient, Today's Visits, Patient Accounts.

### Permissions (server)

| Call | `reception.abikan` |
|---|---|
| Unauthenticated payment | **401** |
| GET Patient Account | **200** (`readOnly: true`) |
| GET registration fee | **200** |
| POST payment | **403** |
| POST bed assign | **403** |
| POST accommodation tariffs | **403** |
| Dispense write | not allowed (405 read-only on the path tested) |

### Browser (19 Aug 2026)

`reception.abikan` one-click login → header **Reception**, sidebar Reception, no Registration Desk / OPD-1 / OPD-2. Menu items stay in Reception. Patient Account for Adaeze Okafor opens with no Pay. `pharmacy.abikan` and `accountant.abikan` still land in their departments. `admin.abikan` Switch department lists **Reception** (not Registration) and opens the Reception dashboard. `registration.abikan` still signs in and also sees Reception.

### Build

`npm test` → 20 passed. `npm run build` → `index-zoN4cbLz.js`.

### Known limitations

1. Internal workplace id remains `registration` so existing `abikan.workplace` values keep working. `reception` is accepted as an alias.
2. Patient Account still groups the fee under **Registration** because that is the billed service name.
3. “New patients” uses patients last updated today, not a separate registration ledger.
4. There is no Reception outstanding-bills total; staff search a patient instead.
5. Doctor/Clinical feature work was not started.

---

## Nursing department UX (19 Aug 2026)

Nursing is centred on the Ward Board. `nurse.abikan` lands on `#/nursing` with header **Nursing**. The hidden session location General Ward is not shown.

### Routes

| Hash | Result |
|---|---|
| `#/nursing` | Dashboard: occupied / available / new admissions from the live board, plus 16-area overview |
| `#/nursing/ward-board` | All 16 areas, 27 beds, Available or Occupied |
| `#/nursing/patients` | Admitted and waiting-for-a-bed list → existing chart |
| `#/nursing/admissions` | Patients the doctor has asked to admit; Assign Bed |
| `#/nursing/transfers` | “Transfers are managed from the Ward Board.” Current occupancy if any |
| `#/nursing/discharges` | “Discharges are managed from the Ward Board.” Current occupancy if any |
| `#/nursing/patient/{uuid}` | Existing nursing chart |
| `#/nursing/not-a-screen` | Nursing dashboard, not Administration |
| `#/accountant` (as nurse) | Access denied, Nursing sidebar remains |

### Browser

Clicked Sign in as `nurse.abikan`. Sidebar: Dashboard, Ward Board, Patients, Admissions, Transfers, Discharges. Dashboard showed Occupied 0, Available 27, New Admissions 0. Ward Board listed Hawawu Maternity Ward through Silver 206 with Bed 01… not room names. Assign Bed opened and was cancelled (no patients waiting). Search Adaeze Okafor showed **Not admitted**. Patient Account opened with no Pay. `pharmacy.abikan` still lands in Pharmacy. `accountant.abikan` still lands in Accountant.

No beds, admissions, transfers, discharges, or payments were written.

### Build

`npm test` → 22 passed. `npm run build` → `index-WVzrGlL-.js`.

Full write-up: `NURSING_UI_IMPLEMENTATION.md`.

---

## Pharmacy department UX (19 Aug 2026)

Pharmacy is centred on the counter queue. `pharmacy.abikan` lands on `#/pharmacy` with header **Pharmacy**. There is no location picker. Payment and dispensing stay separate.

### Routes

| Hash | Result |
|---|---|
| `#/pharmacy` | Dashboard: Prescriptions / Ready to Dispense / Dispensed from the live queue, plus Needs attention |
| `#/pharmacy/prescriptions` | Full prescription queue |
| `#/pharmacy/ready` | Paid prescriptions waiting to dispense |
| `#/pharmacy/dispensed` | Already handed over |
| `#/pharmacy/prescription/{orderUuid}` | Prescription detail |
| `#/pharmacy/patient/{uuid}` | Existing pharmacy patient chart |
| `#/pharmacy/not-a-screen` | Pharmacy dashboard, not Administration |
| `#/accountant` (as pharmacy user) | Access denied, Pharmacy sidebar remains |

### Browser

Clicked Sign in as `pharmacy.abikan`. Header **Pharmacy**. Sidebar: Dashboard, Prescriptions, Ready to Dispense, Dispensed; Drug Catalogue and Stock **Soon**. Dashboard: Prescriptions 3, Ready 0, Dispensed 2. Needs attention: Tunde Bakare UNPAID. Prescriptions listed Adaeze (PAID · DISPENSED), Aisha (PAID · DISPENSED), Tunde (UNPAID). Ready: nothing waiting. Dispensed: Adaeze and Aisha. Aisha detail: PAID / DISPENSED, no Dispense. Tunde detail: UNPAID, cashier copy, no Pay, View Patient Account (read-only). `#/pharmacy/not-a-screen` stayed Pharmacy. `#/accountant` access denied, Pharmacy sidebar. After logout, `nurse.abikan` still lands on Nursing and `accountant.abikan` still lands on Accountant.

No live dispense was performed. Aisha’s existing dispensed result was not changed.

### Build

`npm test` → 31 passed. `npm run build` → `index-Dee9OVW-.js`.

Full write-up: `PHARMACY_UI_IMPLEMENTATION.md`.
