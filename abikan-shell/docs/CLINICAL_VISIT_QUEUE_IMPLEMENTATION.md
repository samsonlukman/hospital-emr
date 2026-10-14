# Clinical visit queue implementation

Date: **19 Aug 2026**.

Related: `CLINICAL_INVESTIGATION.md`.

This phase replaces the misleading appointment-based Doctor list with **Today's Patients**, driven by OpenMRS visits. Appointments are not deleted, renamed, or disabled. Consultation, billing, admission, Nursing, Pharmacy, Laboratory, Radiology, Reception, and Odoo were not redesigned.

---

## 1. Why appointments were removed from the primary queue

The previous dashboard called `GET /openmrs/ws/rest/v1/appointments`. That returns **403** for `doctor.abikan` (and every current Hospital EMR staff account) because none have **View Appointments**.

The UI then showed **No patients are currently waiting** and KPI **0 waiting**. That looked like an empty clinic. It was an authorization failure, not an empty day.

The primary Clinical question is: **which patients are here today for clinical attention?** OpenMRS visits already answer that. Appointments remain the scheduling module for a later Upcoming Appointments view, if privileges exist.

Doctors were **not** granted View Appointments to make the old list work.

---

## 2. Visit source of truth

OpenMRS visits. No Hospital EMR queue table, no second visit store, no Odoo, no browser local storage.

The read path is:

```
GET /openmrs/abikan-api/consultation/todays-patients
  → authenticated OpenMRS session
  → GET /openmrs/ws/rest/v1/visit?fromStartDate=<Lagos yesterday>&includeInactive=true
  → keep rows whose start datetime falls on the Africa/Lagos hospital day
  → keep outpatient visit types only
```

`fromStartDate` is yesterday in Africa/Lagos so a visit that starts just after midnight Lagos (still the previous calendar date in UTC) is not missed. Membership of "today" is decided in Python against Africa/Lagos, not by the browser clock.

---

## 3. Visit types included / excluded

Live `GET /visittype` names on this installation:

| Name | In Today's Patients |
|---|---|
| OPD | Yes |
| Special OPD | Yes |
| Follow Up | Yes |
| IPD | No — Nursing / ward, not the ordinary OPD doctor list |
| EMERGENCY | No — emergency remains a separate workflow; not redesigned here |

Matching is by visit type **name** from this installation, not guessed UUIDs.

An arbitrary active visit is not treated as a waiting patient.

---

## 4. Date / time handling

Timezone: **Africa/Lagos**.

Hospital day for this queue: **00:00 → 23:59:59**. This is not accommodation's 12:00 billing boundary.

A visit belongs to today by its OpenMRS **start** datetime converted to Africa/Lagos. Closed visits that started today still appear, with status **Ended**.

Clock times in the table are formatted in Africa/Lagos (`HH:mm`).

---

## 5. Queue data

Payload (routing ids are required to open the existing chart; they are not shown on screen):

```json
{
  "patients": [
    {
      "patient": "Adaeze Okafor",
      "mrn": "ABC200003",
      "visitType": "OPD",
      "visitStart": "2026-08-19T07:40:00.000+0000",
      "time": "08:40",
      "status": "Open",
      "patientUuid": "…",
      "visitUuid": "…"
    }
  ]
}
```

Status is only **Open** or **Ended**, from `stopDatetime`. WAITING / IN CONSULTATION / COMPLETED are not invented.

There is no "Patients Waiting" KPI.

---

## 6. Empty state

When there are no matching visits:

**No patients today.**

**Search for a patient to open their record.**

On 19 Aug 2026 the only visit that started today was Samson's **IPD** visit. That is excluded, so the doctor list is honestly empty. Reception still shows that one visit on its own Today's Visits list. Leftover open OPD visits from 13–17 Aug do **not** appear here, because they did not start today. They were not closed.

---

## 7. API

`GET /openmrs/abikan-api/consultation/todays-patients`

- Read-only
- Uses the caller's OpenMRS session cookie
- Returns only the fields above
- No Odoo
- No queue table
- No cache of mutable queue data

Implementation: `server/patient-account/clinical_queue.py`, routed in `server.py`.

---

## 8. Permissions

| Caller | Result |
|---|---|
| Unauthenticated | **401** Sign in required |
| `doctor.abikan` (`app:clinical`) | **200** |
| `admin.abikan` (SuperAdmin) | **200** (existing SuperAdmin clinical access) |
| `reception.abikan` | **403** This action requires the Doctor workspace |
| `nurse.abikan` | **403** |
| `pharmacy.abikan` | **403** |
| `accountant.abikan` | **403** |

Existing RBAC was not weakened. Creating the endpoint does not grant Clinical access to other departments.

---

## 9. Routes

Unchanged Clinical hashes:

| Hash | Screen |
|---|---|
| `#/doctor` | Clinical dashboard / Today's Patients |
| `#/doctor/queue` | Same screen, scrolls to the table |
| `#/doctor/patient/{uuid}` | Existing consultation |
| `#/doctor/not-a-screen` | Stays Clinical (dashboard) |
| `#/accountant` as doctor | Access denied, Clinical sidebar remains |

Opening a row calls `openConsultation(patientUuid)`. It does **not** start a visit or encounter.

Patient search (name and hospital number) remains in the header.

---

## 10. Browser testing (19 Aug 2026)

Account: `doctor.abikan` / `Admin123`.

| Check | Result |
|---|---|
| Lands on Clinical `#/doctor` | Yes. Header **Clinical**. No location picker |
| Today's Patients loads | Yes |
| Count from real visits | Yes. Today had 1 IPD visit (Samson); excluded. List empty |
| Appointment permission not required | Yes. Queue no longer calls `/appointments` |
| No misleading **0 waiting** | Yes. Copy is **No patients today.** |
| Search by name | **John** → ABC200012 - John Adewale |
| Search by MRN | **ABC200003** → Adaeze Okafor |
| Open patient | `#/doctor/patient/{uuid}` existing consultation |
| Existing OPD visit opens | John: **OPD · Open**, 13 Aug, OPD-1. No new visit created |
| Start OPD visit still available when none is open | Unchanged code path; not exercised with a write |
| Vitals | Record vitals still present. John's Pulse 76 / Temperature 36.8 from 13 Aug still shown |
| Diagnosis | Search diagnosis still present |
| Consultation fee | Create consultation fee still present. **No Pay** |
| Admit Patient | Present. Nursing assigns the bed. **No bed picker** |
| Logout | Returns to Sign in |
| Pharmacy login | `#/pharmacy` unchanged |
| Reception login | `#/reception` unchanged (Today's visits 1 = Samson's IPD) |
| Nursing login | `#/nursing` unchanged |
| Unknown Clinical route | `#/doctor/not-a-screen` stays Clinical |
| Clinical cannot open Administration/Accountant | `#/accountant` → access denied, Clinical nav remains |

No patients, visits, encounters, diagnoses, orders, admissions, invoices, or payments were created for this test.

---

## 11. npm test

Pass. 38 tests, including visit-type include/exclude, payload mapping, and Clinical hash routing.

---

## 12. npm build

Pass. `tsc --noEmit && vite build`. Bundle `index-BvH0JOzj.js`.

---

## 13. Existing clinical workflows preserved

Unchanged:

- Open/start OPD visit (`allowConsultationWhenNoOpenVisit` remains false)
- Vitals
- Coded diagnosis
- Encounter save
- Consultation fee create (Accountant collects later)
- Admit Patient (Nursing assigns bed)
- Patient search
- Patient Account link
- Open full chart

The consultation screen was not redesigned. Appointment-derived queue numbers were removed from the identity header because they were not real.

---

## 14. Known limitations

- Leftover **open OPD visits from previous days** are still open in OpenMRS. They do not appear in Today's Patients. The doctor can still find those patients with search. This phase does not close them.
- Samson's **open IPD visit** with 0 occupied beds remains. It is excluded from the OPD doctor list. Not cleaned up.
- If no OPD / Special OPD / Follow Up visit starts today, the list is empty even though older open OPD visits exist. That is intentional.
- WAITING / IN CONSULTATION / COMPLETED are not shown. Open vs Ended is all that OpenMRS visit stop time can support honestly.
- Follow Up and Special OPD are included when they start today, but Hospital EMR still only **starts** OPD visits from the consultation screen.
- EMERGENCY visits are not in this list.
- Appointments are not shown yet. They may appear later as a separate Upcoming Appointments view without replacing visits.
- `https://localhost/abikan/` is the verified Hospital EMR entry in this session.

STOP. Prescriptions, lab/radiology ordering, notes, follow-up, referral, emergency redesign, and My Patients are out of this phase.
