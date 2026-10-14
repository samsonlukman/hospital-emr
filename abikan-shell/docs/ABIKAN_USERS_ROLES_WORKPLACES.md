# Hospital EMR users, roles and workplaces

Date: **19 Aug 2026**. Architecture + implementation. No clinical or financial records were created or changed. Updated for Reception terminology. Login reliability repair remains from 18 Aug 2026.

Staff should think in departments (Reception, Clinical, Nursing, Pharmacy, Laboratory, Radiology, Accountant). They should not pick OpenMRS rooms, OPD codes, or beds as a “workplace.”

---

## 1. Existing authentication architecture

Hospital EMR does **not** have its own user database.

| Layer | What it does |
|---|---|
| OpenMRS session | `GET /openmrs/ws/rest/v1/session` with HTTP Basic creates `JSESSIONID` |
| OpenMRS user | Roles and privileges |
| OpenMRS session location | Still required for visits/encounters. Hidden from staff |
| Hospital EMR API | Re-reads the same cookie. Checks privileges on every protected path |
| Odoo | Server-side service user only. Never a staff login |

There is no second authentication system.

**Login sequence (after the 18 Aug 2026 repair):** anonymous `GET /session` plants `JSESSIONID` → one Basic `GET /session` authenticates → roles/privileges from that payload → department resolved → hidden session location assigned → department home. Credential rejection is only `{ authenticated: false }` / 401 on that Basic call. Session-init failures are a different message. See `ABIKAN_UI_NAVIGATION.md`.

**Architectural constraint (not a workaround that destroys OpenMRS):** OpenMRS still needs a session location. Hospital EMR now sets that location automatically from the user’s department. Staff never see the location list.

---

## 2. OpenMRS users / roles discovered

Existing users (unchanged except `abikan.admin` user property):

| Username | Person | Roles |
|---|---|---|
| `abikan.admin` | Hospital EMR Development Admin | System Developer, SuperAdmin, Privilege Level: Full, Bahmni-App, Provider, … |
| `superman` | Super Man | System Developer, SuperAdmin, … |
| `registration` | registration bahmni-user | Registration-App |
| `dr_neha` | Neha Anand | Doctor (Bahmni stock role — too broad for Hospital EMR) |
| `reports-user` | Reports User | Reports-App |

Bahmni’s stock **Doctor** role includes `app:admin`, `app:registration`, `app:adt`, `Assign Beds`, and `app:lab-lite`. Hospital EMR does **not** assign that role to `abikan.doctor`.

---

## 3. Existing Hospital EMR RBAC (before this change)

Frontend `workspaceMap.ts` mixed **privilege** with **OpenMRS login location**:

- Registration required location name `Registration Desk`
- Doctor required a location name starting with `OPD`
- Nursing required Emergency / General Ward / Pediatric Ward / hospital rooms
- Lab, Radiology, Pharmacy, Accountant were already location-independent

The login screen and header loaded **every** location tagged `Login Location` (22 rows), including every hospital room.

Backend already had privilege checks on most writes (`require_accountant`, `require_pharmacist`, `require_nursing_user`, `require_admin_user`). Patient Account GET only required a session; it now requires a department privilege.

Privilege `abikan:accountant` was named in code but **did not exist** in OpenMRS until this task.

---

## 4. OPD-1 analysis

| Field | Value |
|---|---|
| Name | OPD-1 |
| UUID | `5e232c47-8ff5-4c5c-8057-7e39a64fefa5` |
| Created | 2024-08-19 08:50 UTC by `daemon` (Bahmni demo seed) |
| Parent | Bahmni Hospital |
| Tags | Login Location, Appointment Location |
| Retired | no |
| Visit usage | **9 visits** (Ibrahim Musa, Ngozi Eze, Fatima Abdullahi, Chinedu Okonkwo, Aisha Bello, Adaeze Okafor, …) |
| Role | Active OPD visit location for this hospital’s test patients |

OPD-1 is a real, in-use consultation location. It is **not** shown as a Hospital EMR workplace. It is the hidden session location for Clinical.

---

## 5. OPD-2 analysis

| Field | Value |
|---|---|
| Name | OPD-2 |
| UUID | `62b55a63-f3a0-4f7c-9ea6-a85f2e7cd09a` |
| Created | 2024-08-19 08:50 UTC by `daemon` (same seed as OPD-1) |
| Parent | Bahmni Hospital |
| Tags | Login Location, Appointment Location |
| Retired | no |
| Visit usage | **0 visits** |

OPD-2 is an unused duplicate demo location. **Not renamed, not retired, not deleted.**

**Recommendation D:** leave both OpenMRS locations unchanged. Hide both from Hospital EMR workplace selection. Keep OPD-1 as the silent Clinical session location. Do not merge until the hospital confirms they will never use a second OPD.

---

## 6. Development accounts

Password for this **development/test** environment only: `Admin123`.

Do **not** use a shared password for production staff.

Created/updated with `abikan-shell/scripts/provision-dev-users.py` (idempotent).

### Preferred interface-test accounts (`*.abikan`)

These are the accounts to use for daily UI testing.

| Username | Person | OpenMRS roles | Provider | Landing |
|---|---|---|---|---|
| `admin.abikan` | Hospital EMR Administrator | SuperAdmin, Provider | yes | Administration |
| `reception.abikan` | Reception Staff | Abikan:Reception | no | Reception |
| `registration.abikan` | Registration Staff | Abikan:Registration | no | Reception (compatibility) |
| `doctor.abikan` | Clinical Doctor | Abikan:Doctor | yes | Clinical |
| `nurse.abikan` | Nursing Staff | Abikan:Nursing | yes | Nursing |
| `pharmacy.abikan` | Pharmacy Staff | Abikan:Pharmacy | no | Pharmacy |
| `lab.abikan` | Laboratory Staff | Abikan:Laboratory | no | Laboratory |
| `radiology.abikan` | Radiology Staff | Abikan:Radiology | no | Radiology |
| `accountant.abikan` | Accountant Staff | Abikan:Accountant | no | Accountant |

Only `admin.abikan` has SuperAdmin. Department accounts have one Hospital EMR role. `registration.abikan` remains as a compatibility login and also opens Reception.

### Earlier accounts (`abikan.*`) — kept

These already existed and appear in historical invoices, prescriptions, and implementation notes (`abikan.admin` created charges). Hospital EMR code does **not** hardcode them as the only logins. OpenMRS usernames are unique, so they were **not renamed or deleted**.

| Username | Person | OpenMRS roles | Provider |
|---|---|---|---|
| `abikan.admin` | existing | unchanged SuperAdmin / System Developer | existing |
| `abikan.registration` | Hospital EMR Registration | Abikan:Registration | no |
| `abikan.doctor` | Hospital EMR Doctor | Abikan:Doctor | yes |
| `abikan.nurse` | Hospital EMR Nurse | Abikan:Nursing | yes |
| `abikan.pharmacy` | Hospital EMR Pharmacy | Abikan:Pharmacy | no |
| `abikan.lab` | Hospital EMR Laboratory | Abikan:Laboratory | no |
| `abikan.radiology` | Hospital EMR Radiology | Abikan:Radiology | no |
| `abikan.accountant` | Hospital EMR Accountant | Abikan:Accountant | no |

The provision script still signs in as `abikan.admin` (`ABIKAN_ADMIN_USER`).

User property `abikan.workplace` stores the default department so later accounts such as `nurse.maternity1` can be mapped without rewriting the UI.

See also `abikan-shell/docs/ABIKAN_UI_NAVIGATION.md` for department menus and the application shell.

---

## 7. Roles

New OpenMRS roles (narrower than Bahmni stock Doctor):

| Role | Inherits | Extra privileges |
|---|---|---|
| Abikan:Registration | Registration-App | — (compatibility; staff still see Reception) |
| Abikan:Reception | Registration-App | — (same intended permissions as Abikan:Registration) |
| Abikan:Doctor | Clinical-App, Provider | Get Allergies, Add Allergies, Edit Allergies, Remove Allergies |
| Abikan:Nursing | InPatient-App | Get Allergies, Add Allergies, Edit Allergies, Remove Allergies |
| Abikan:Pharmacy | Bahmni-App-User-Login | `bahmni:clinical:dispense` + patient/order reads |
| Abikan:Laboratory | Lab | patient/visit/order reads; no user-management privileges |
| Abikan:Radiology | Radiology-App | — |
| Abikan:Accountant | Bahmni-App-User-Login | `abikan:accountant` + patient reads |

New privilege created: **`abikan:accountant`**.

Existing privileges reused: `app:registration`, `app:clinical`, `app:adt`, `app:lab-lite`, `app:radiology-upload`, `bahmni:clinical:dispense`, `Assign Beds`, `Get Allergies`, `Add Allergies`, `Edit Allergies`, `Remove Allergies`.

OpenMRS requires role `inheritedRoles` / `privileges` to be posted **by UUID**. Name-only create left empty inherit lists; the provision script now posts UUIDs.

---

## 8. Default workplaces

| Account | Default workplace | Hidden OpenMRS session location | Landing hash |
|---|---|---|---|
| `admin.abikan` / `abikan.admin` | Administration | Registration Desk | `#/home` |
| `reception.abikan` | Reception | Registration Desk | `#/reception` |
| `registration.abikan` / `abikan.registration` | Reception | Registration Desk | `#/reception` |
| `doctor.abikan` / `abikan.doctor` | Clinical | **OPD-1** | `#/doctor` |
| `nurse.abikan` / `abikan.nurse` | Nursing | General Ward | `#/nursing` |
| `pharmacy.abikan` / `abikan.pharmacy` | Pharmacy | Registration Desk | `#/pharmacy` |
| `lab.abikan` / `abikan.lab` | Laboratory | Registration Desk | `#/laboratory` |
| `radiology.abikan` / `abikan.radiology` | Radiology | Registration Desk | `#/radiology` |
| `accountant.abikan` / `abikan.accountant` | Accountant | Registration Desk | `#/accountant` |

There is no “Select your workplace” step. Staff never see OPD-1, OPD-2, rooms, or beds as a workplace.

Admin may switch departments in the header: Reception, Clinical, Nursing, Pharmacy, Laboratory, Radiology, Accountant, Administration.

That list does **not** include Gold Room 203, Silver 207, OPD-1, OPD-2, or beds.

---

## 9. Permissions

| | Admin | Reception | Doctor | Nurse | Pharmacy | Lab | Radiology | Accountant |
|---|---|---|---|---|---|---|---|---|
| Reception | yes | yes | no | no | no | no | no | no |
| Clinical / Doctor | yes | no | yes | no | no | no | no | no |
| Admit patient (clinical) | yes | no | yes | no | no | no | no | no |
| Nursing board | yes | no | no | yes | no | no | no | no |
| Assign / transfer / discharge bed | yes | no | no | yes | no | no | no | no |
| Pharmacy dispense | yes | no | no | no | yes | no | no | no |
| Laboratory | yes | no | no | no | no | yes | no | no |
| Radiology | yes | no | no | no | no | no | yes | no |
| Accountant payments | yes | no | no | no | no | no | no | yes |
| Patient Account (view) | yes | yes | yes | yes* | yes | yes | yes | yes |
| Accommodation tariffs | yes | no | no | no | no | no | no | no |

\* Nurse may view Patient Account (payment status on the ward). Nurse cannot pay or change prices.

Frontend hides departments the user cannot open. Backend still enforces the same rules.

---

## 10. Backend authorization

Every protected `abikan-api` path checks the OpenMRS session.

| Result | When |
|---|---|
| 401 | No session / not signed in |
| 403 | Signed in, wrong department |

Examples (tested):

| Caller | Request | Result |
|---|---|---|
| (none) | POST `/accountant/payment` | **401** |
| `abikan.registration` | POST `/accountant/payment` | **403** |
| `abikan.registration` | POST `/pharmacy/…/dispense` | **403** |
| `abikan.pharmacy` | POST `/accountant/payment` | **403** |
| `abikan.nurse` | POST `/inpatient/accommodation/tariffs` | **403** |
| `abikan.doctor` | POST `/inpatient/assign` | **403** |
| `abikan.accountant` | POST `/pharmacy/…/dispense` | **403** |
| `abikan.registration` | GET `/accountant/dashboard` | **403** |
| `abikan.registration` | GET `/pharmacy/queue` | **403** |
| `abikan.accountant` | GET `/inpatient/accommodation/tariffs` | **403** |

Patient Account GET now requires a department privilege, not merely a session.

---

## 11. Workplace abstraction

File: `abikan-shell/src/config/workplaces.ts`

- **Workplace** = Hospital EMR department
- **Session location** = hidden OpenMRS location used for visits/encounters

Resolution order for default workplace:

1. SuperAdmin / System Developer → Administration
2. User property `abikan.workplace` if allowed
3. Single allowed department
4. If several privileges (legacy Bahmni Doctor): Clinical, then Nursing, then Registration, …

Later hospital accounts (`nurse.maternity1`, `accountant.2`) only need an OpenMRS user, the matching Hospital EMR role, and optional `abikan.workplace`.

---

## 12. Admin behaviour

`admin.abikan` and `abikan.admin` use SuperAdmin (the latter also has System Developer). No other development account has SuperAdmin.

- Lands on Administration (`#/home`)
- Administration dashboard: Users, Departments / Access, and System Settings are Coming soon. Accommodation Prices is implemented.
- Header **Switch department** lists departments, not rooms
- Can open Reception, Clinical, Nursing, Pharmacy, Laboratory, Radiology, Accountant, Patient Account, Nursing bed board, Accommodation prices
- User/role administration UI is **not** implemented in Hospital EMR; hospital user administration remains the user store
- Accommodation tariff management is **admin only**
- Ordinary staff do not get a department switcher

---

## 13. Security tests

Preferred `*.abikan` accounts authenticate and land in the matching department. Writes from the wrong department return 403. Unauthenticated payment returns 401. Allowed reads return 200, including Adaeze Okafor Patient Account (`ABC200003`).

| Caller | Request | Result |
|---|---|---|
| (none) | POST `/accountant/payment` | **401** |
| `registration.abikan` | POST `/accountant/payment` | **403** |
| `pharmacy.abikan` | POST `/accountant/payment` | **403** |
| `nurse.abikan` | POST `/inpatient/accommodation/tariffs` | **403** |
| `doctor.abikan` | POST `/inpatient/assign` | **403** |
| `accountant.abikan` | POST `/pharmacy/…/dispense` | **403** |

---

## 14. Regression tests

| Check | Result |
|---|---|
| `https://localhost/` | Hospital EMR |
| `https://localhost/abikan/` | Hospital EMR |
| `https://localhost/bahmni/` | 302 → `/bahmni/home/` |
| `/openmrs/ws/rest/v1/session` | 200 |
| `/openmrs/abikan-api/health` | 200 |
| `npm run build` | passed (`index-zoN4cbLz.js`) |
| Hidden session location | Clinical → OPD-1; Nursing → General Ward; Registration → Registration Desk (not shown in the UI) |
| Adaeze Patient Account | loads (no new invoices/payments created) |
| OPD-1 / OPD-2 / rooms / beds | not deleted or renamed |

Login no longer shows the 22-location list. After `npm run build`, copy `dist/index.html` over the proxy DocumentRoot (or restart the proxy) so `https://localhost/` uses the same bundle as `/abikan/`.

---

## 15. Known limitations

1. OpenMRS still stores a session location. Clinical visits for doctors are written at **OPD-1**. That is intentional.
2. Nursing’s hidden session location is **General Ward** (Bahmni demo ward, still a valid login/admission location). The Nursing screen lists the 16 hospital areas; staff pick a ward/room **on the board**, not as a workplace.
3. Pharmacy, Laboratory, Radiology, and Accountant have no dedicated OpenMRS login location. They silently use Registration Desk.
4. `abikan.admin` does not have privilege `abikan:accountant` on the user record; payment is allowed because SuperAdmin is an accountant role in the API.
5. Bahmni stock user `dr_neha` was not modified. If used in Hospital EMR, default workplace prefers Clinical because of multiple privileges.
6. OpenELIS and PACS still have their own logins. Not in scope.
7. Accommodation prices stay admin-only. No separate “billing admin” role was added.
8. `Admin123` is development-only.
9. On Patient Account, the admin header switcher may show Administration because that route is not a department. Switching still works.
10. Earlier `abikan.*` usernames remain in OpenMRS. Prefer `*.abikan` for new interface tests.
11. See `ABIKAN_UI_NAVIGATION.md` for the login sequence, first-click login cause, and department hash map. Menu items must use department-owned hashes (`#/pharmacy/ready`, not `#ready`). Unknown hashes must not become Administration.
12. Hospital EMR staff see **Reception**. OpenMRS **Registration Desk**, role **Abikan:Registration**, and user **registration.abikan** remain. Preferred UI account is **reception.abikan** (`Abikan:Reception`).

---

## 16. Recommended production account model

Do not copy `Admin123`.

For each real staff member:

1. Create an OpenMRS person + user
2. Assign **one** Hospital EMR role (`Abikan:Registration`, `Abikan:Doctor`, …)
3. Set user property `abikan.workplace` if they should land somewhere other than the role default
4. Create an OpenMRS **provider** for doctors (and nurses who write ADT)
5. Do **not** assign Bahmni stock `Doctor` if they must not administer, register, or assign beds
6. Do **not** assign SuperAdmin except to a tiny hospital IT group
7. Cashiers get `Abikan:Accountant` only — never `bahmni:clinical:dispense`
8. Keep OPD-1/OPD-2 in OpenMRS until the hospital decides; never show them as Hospital EMR workplaces

---

## Files changed

| File | Change |
|---|---|
| `abikan-shell/src/config/workplaces.ts` | Workplace model |
| `abikan-shell/src/config/workspaceMap.ts` | Privilege-only department gates |
| `abikan-shell/src/config/clinicalWorkspaces.ts` | Hide unauthorised / location-gated tiles |
| `abikan-shell/src/config/clinicalNav.ts` | Department nav (legacy admin list; staff no longer use this dump) |
| `abikan-shell/src/config/adminNav.ts` | Administration menu |
| `abikan-shell/src/config/departmentNav.ts` | Department → menu map |
| `abikan-shell/docs/ABIKAN_UI_NAVIGATION.md` | Shell, landing, menus |
| `abikan-shell/src/workspaces/Login/LoginWorkspace.tsx` | Credentials only; auto session location |
| `abikan-shell/src/App.tsx` | Landing route; workplace switch |
| `abikan-shell/src/components/Header.tsx` | Workplace, not location list |
| `abikan-shell/src/layouts/AppShell.tsx` | Workplace props |
| `abikan-shell/src/app/WorkspaceRouter.tsx` | Workplace switch; staff nav |
| `abikan-shell/src/services/openmrs/loadWorkspaceContext.ts` | Auto-assign hidden location |
| `abikan-shell/src/services/openmrs/location.ts` | `fetchLocationByName` |
| `abikan-shell/src/workspaces/ClinicalHome/ClinicalHomeWorkspace.tsx` | Administration home |
| `abikan-shell/src/workspaces/AccessDenied/AccessDeniedWorkspace.tsx` | Copy |
| `abikan-shell/src/workspaces/Doctor/DoctorWorkspace.tsx` | Copy |
| `abikan-shell/src/workspaces/Nursing/NursingWorkspace.tsx` | “Nursing”, not room name |
| `abikan-shell/server/patient-account/server.py` | Patient Account view gate |
| `abikan-shell/scripts/provision-dev-users.py` | Dev users/roles |
| `abikan-shell/docs/ABIKAN_USERS_ROLES_WORKPLACES.md` | This document |

OpenMRS data created: privilege `abikan:accountant`, seven Hospital EMR roles, original `abikan.*` users kept, preferred `*.abikan` users added. **No** patients, visits, encounters, invoices, payments, stock, beds, or location changes.

---

## Remaining decisions for the hospital

1. Confirm recommendation **D** for OPD-1 / OPD-2 (keep both, hide from Hospital EMR).
2. Whether Clinical should ever use a second OPD location.
3. Production passwords and named staff accounts.
4. Whether a future “billing admin” may edit accommodation prices without SuperAdmin.
