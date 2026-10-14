# Nursing UI implementation

Date: **19 Aug 2026**.

Related: `INPATIENT_IMPLEMENTATION.md`, `ACCOMMODATION_BILLING_IMPLEMENTATION.md`, `ABIKAN_USERS_ROLES_WORKPLACES.md`, `ABIKAN_UI_NAVIGATION.md`.

This phase is the Nursing **experience**. It does not add a second bed table, admission table, patient table, or billing ledger. OpenMRS / Bahmni remains the admission and bed engine. Accommodation billing and Patient Account stay as they were.

The first question after login is **who is where?**

---

## Login

| Account | Password | Lands on |
|---|---|---|
| `nurse.abikan` | `Admin123` (this environment only) | Nursing `#/nursing` |

There is no location picker. The header says **Nursing**. The hidden session location remains **General Ward** and is not shown.

---

## Navigation

Sidebar:

- Dashboard → `#/nursing`
- Ward Board → `#/nursing/ward-board` (alias `#/nursing/wards`)
- Patients → `#/nursing/patients`
- Admissions → `#/nursing/admissions`
- Transfers → `#/nursing/transfers`
- Discharges → `#/nursing/discharges` (alias `#/nursing/discharge`)

Unknown `#/nursing/…` stays in Nursing (dashboard). It does not become Administration.

`#/accountant` as a nurse: access denied, Nursing sidebar remains.

Patient chart: `#/nursing/patient/{uuid}` — existing shared nursing chart.

---

## Dashboard (`#/nursing`)

Operational overview from `GET /openmrs/abikan-api/inpatient/board`:

| Card | Source |
|---|---|
| Occupied Beds | `occupiedBeds` |
| Available Beds | `availableBeds` |
| New Admissions | length of `awaiting` |

Zeros are real bed state, not invented KPIs. There is no Pending Discharges card because the board does not provide a discharge queue.

Then **Ward overview**: all 16 configured areas with occupied / available counts.

Quick actions: Ward Board, Assign Bed, Transfer Patient, Discharge Patient.

---

## Ward Board (`#/nursing/ward-board`)

Main workspace. Layout:

**Ward → Room → Bed → Patient**

Each configured area is a section. Beds are labelled **Bed 01**, **Bed 02**, … not the room name. Gold Room 203 shows as the area; its bed is Bed 01.

States shown: **Available** and **Occupied** only.

- Occupied bed → existing nursing chart
- Available bed → Assign Bed
- Occupied bed also has Transfer and Discharge

Browser check on 19 Aug 2026: 16 areas, 27 beds, all Available, 0 occupied. Names match the configured hospital areas. No 28th bed.

---

## Bed assignment

Doctor: **Admit Patient**. Nurse: **Assign Bed**.

The nurse sees patient, hospital number, admission status (Admit requested), ward, room, and available beds as radio buttons.

If the bed was taken immediately before assignment, the existing API returns a conflict. The UI shows:

> This bed has just been assigned to another patient. Please choose another bed.

Then the board refreshes. The dialog stays open. Nursing does not calculate prices or collect payment.

Emergency bed assignment is not blocked on unpaid bills. That rule already exists in the backend. This phase did not add a new bypass.

---

## Transfer

Existing `POST /openmrs/abikan-api/inpatient/transfer`.

The nurse sees current location (ward — bed) and chooses ward, room, and an available bed, then **Transfer Patient**. The backend frees the old bed and occupies the new one.

There is no historical transfer list in the current data. `#/nursing/transfers` says **Transfers are managed from the Ward Board** and lists patients currently on a bed so the action can be taken there. Nothing is invented.

Accommodation billing during transfer is unchanged. The nurse does not enter ₦ amounts. Payment status on the chart, when present, is PAID / PARTIALLY PAID / OUTSTANDING. There is no Pay button.

---

## Discharge

Existing `POST /openmrs/abikan-api/inpatient/discharge`.

Confirmation:

> Discharge this patient and release their bed?

After success:

> Patient discharged. Bed released.

Unpaid accommodation does not block discharge (existing hospital policy). `#/nursing/discharges` has no invented discharge history.

---

## Patients and search

`#/nursing/patients` lists occupied patients and patients waiting for a bed (name, hospital number, age, sex, ward, room, bed, status). Clicking opens the existing chart.

Header search is by name or hospital number. In Nursing, a result that is not on the board is labelled **Not admitted**. It is not shown as occupying a bed.

Verified: Adaeze Okafor `ABC200003` → **Not admitted** → chart Location / Ward / Status **Not admitted**. Hidden location General Ward was not shown.

---

## Patient Account

Nursing may **view** the existing Patient Account. `GET` for Adaeze returned **200**, `readOnly: true`.

No Pay, Register Payment, Refund, or Edit Tariff in the Nursing UI. Payment remains Accountant.

Accommodation on the nursing chart, when the stay payload includes it, stays informational: PAID / PARTIALLY PAID / OUTSTANDING.

---

## Permissions

`nurse.abikan` can view the board, assign, transfer, and discharge according to existing privileges, open the nursing chart, and view Patient Account.

Cannot collect payment, edit tariffs, dispense, or open Administration.

| Call | Result |
|---|---|
| Unauthenticated `GET /inpatient/board` | **401** |
| Unauthenticated `POST /accountant/payment` | **401** |
| `nurse.abikan` `GET /inpatient/board` | **200** (16 areas, 27 beds) |
| `nurse.abikan` `GET` Patient Account | **200** |
| `nurse.abikan` `POST /accountant/payment` | **403** |
| `nurse.abikan` `POST /inpatient/accommodation/tariffs` | **403** |
| `nurse.abikan` `POST /pharmacy/prescription/…/dispense` | **403** |
| `nurse.abikan` `GET /accountant/dashboard` | **403** |

---

## Browser click-through (19 Aug 2026)

`https://localhost/abikan/`. No admission, transfer, discharge, or payment was written.

1. Login `nurse.abikan` → Nursing, no location picker, department **Nursing**
2. Dashboard: Occupied 0, Available 27, New Admissions 0; 16 area cards
3. Ward Board: 16 areas, 27 beds, Available / Occupied only, Bed 01 not “Room 203”
4. Assign Bed on Hawawu Maternity Ward Bed 01: ward locked, radio beds, honest “no patients waiting”; Cancel
5. Patients / Admissions / Transfers / Discharges: real empty states, not Administration
6. `#/nursing/not-a-screen` → Nursing dashboard
7. Search Adaeze → Not admitted → chart → Patient Account, no Pay
8. `#/accountant` → access denied, Nursing sidebar
9. Sign out
10. `pharmacy.abikan` → Pharmacy
11. `accountant.abikan` → Accountant

---

## Tests and build

```
npm test   → 22 passed
npm run build → tsc --noEmit && vite build, success
bundle → dist/assets/index-WVzrGlL-.js
```

After build, `dist/index.html` was copied to the proxy DocumentRoot so `https://localhost/` matches `/abikan/`.

---

## Data changed

None. No patients, visits, admissions, transfers, discharges, invoices, payments, tariffs, beds, OPD-1, or OPD-2 were created or modified.

---

## Known limitations

1. Transfers and discharges have no historical list from the current APIs. Those pages are operational (current occupancy) plus honest copy pointing at the Ward Board.
2. Pending discharges is not a dashboard number; the board does not expose that queue.
3. In this hospital, a ward/room location is one OpenMRS location. The assign dialog shows Ward and Room as the same name.
4. Cleaning / Reserved / Maintenance / Out of Service are not shown; the engine only has Available and Occupied.
5. Nursing does not create the clinical admit decision. Assign Bed requires a patient already waiting, or the chart of a patient the doctor has asked to admit.
6. Nursing Notes and scheduled-dose Medication Administration are implemented. Nursing tasks, care plan, and intake/output remain Coming soon; PRN medication administration is deferred.
7. Doctor/Clinical expansion was not started.
8. `Admin123` is development-only.
