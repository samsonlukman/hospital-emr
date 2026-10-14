# Inpatient — ward, room, bed implementation

Date: **17 Aug 2026** (UTC).

Related: `INPATIENT_WARD_ROOM_BED_INVESTIGATION.md`, `ADT_BED_WORKFLOW.md`, `CLINICAL_WRITE_API.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `REGISTRATION_BILLING_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `PHARMACY_BILLING_IMPLEMENTATION.md`, `LABORATORY_BILLING_IMPLEMENTATION.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`.

Hospital EMR is the hospital-facing interface. OpenMRS / Bahmni remains the clinical and bed-management engine. Odoo remains the financial engine. This phase does **not** create accommodation tariffs, invoices, deposits, or a second ledger.

```
OpenMRS / Bahmni  — visits, admissions, locations, beds
Odoo              — invoices, payments, stock (unchanged in this phase)
Hospital EMR            — simple ward board, admit, assign, transfer, discharge
```

Status labels: **CONFIRMED** · **IMPLEMENTED** · **WRITE** · **READ-ONLY** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION**

---

## 1. What was created

**IMPLEMENTED**

| Kind | What |
|---|---|
| OpenMRS locations | 16 hospital ward/room locations under Bahmni Hospital, tagged Login Location + Admission Location |
| Bed type | **Standard** |
| Beds | 27 Bahmni `bed` rows (Bed 01, Bed 02, … per area), initially AVAILABLE |
| Layout | One column of cells per area (`POST /admissionLocation/{uuid}` then `POST /bed`) |
| Hospital EMR API | Ward board, patient stay, admit decision, assign, transfer, discharge |
| Hospital EMR UI | Nursing ward board + patient assign/transfer/discharge; Doctor **Admit Patient** |

Not created: Odoo products, tariffs, sale orders, invoices, payments, stock moves, extra privileged users, a parallel bed table, or accommodation charges.

---

## 2. Existing OpenMRS locations reused

**CONFIRMED** · **READ-ONLY** · none renamed or deleted

Parent used for the new areas:

| Location | UUID |
|---|---|
| Bahmni Hospital | `72636eba-29bf-4d6c-97c4-4b04d87a95b5` |

Tags reused (not created):

| Tag | UUID |
|---|---|
| Admission Location | `9f79d118-4449-4c6e-845c-58b61d70c0bc` |
| Login Location | `b8bbf83e-645f-451f-8efe-a0db56f09676` |

Demo / leftover admission locations were **left in place** and are **hidden** from the Hospital EMR ward board:

- Emergency (login + admission, 0 beds) — not the hospital Emergency Room
- General Ward, General Ward Room-1, General Ward Room-2
- Pediatric Ward, Pediatric Ward Room-1
- Emergency Ward, Test Ward, Child test (empty layout cells only)
- OPD-1, OPD-2, Registration Desk, OTs

No exact name collision with the hospital inventory. **Emergency** vs **Emergency Room** are different locations. **Emergency Room** was created new.

---

## 3. New locations created

**IMPLEMENTED** · 16 hospital areas, children of Bahmni Hospital

| Area | UUID |
|---|---|
| Hawawu Maternity Ward | `f0f005dd-c95d-47f1-894a-b263783dd5e6` |
| Aisha Children Ward | `652ff562-62e2-4a0c-8564-f17df728d731` |
| Emergency Room | `0a6ba74e-6ef3-4906-8e84-236303fa2679` |
| Gold Room 203 | `5f5fe128-3575-48e8-a496-3e057b4fdfda` |
| Gold Room 202 | `ea1f2988-b000-4b76-b717-eb22611e85eb` |
| Gold Room 204 | `cf44c30d-8d9f-49e8-a0c1-ce57619f1e57` |
| Silver 207 | `4decab9e-62ef-48b1-8503-c79210abfeab` |
| Bronze 208 | `bac29e77-fc4f-4fdd-8d5c-4690ca670b19` |
| Gold Room 210 | `03f4a978-bbcf-4d6a-ba81-9f6791a37e2d` |
| Gold Room 211 | `1c8b96c6-e8b7-4303-b74a-284ec62c6a88` |
| Platinum Room 209 | `41d5b1a3-8fdb-4820-bb00-9df4cf44383d` |
| Diamond 214 | `dc70601e-22d0-49dc-ae85-cec2d698c2d1` |
| Pre Labour Room | `7291117d-ae8d-481f-8c09-95d973e83f78` |
| Gold Room 212 | `76e48736-2a67-4b1e-b3e4-b9712d545770` |
| Gold Room 213 | `fae357f1-c85f-4bd1-a996-bed4decad692` |
| Silver 206 | `9971567f-8dbb-4cab-89f2-9269204758f1` |

Beds are **not** OpenMRS locations. Each area is both the login workplace and the admission location that holds the bed grid. There is no extra “room” location under a ward, because the hospital inventory names the area itself (ward or private room).

---

## 4. New beds created

**IMPLEMENTED**

Bed type **Standard** uuid `1576cca8-8706-4da0-81ba-8c052f6ab836`.

Created through the installed Bahmni bed-management API:

1. `POST /openmrs/ws/rest/v1/admissionLocation/{locationUuid}` `{ "row": N, "column": 1 }`
2. `POST /openmrs/ws/rest/v1/bed` `{ bedNumber, bedType: "Standard", row, column, locationUuid }`

Numeric bed ids **1–27**. Example: Hawawu Bed 01 id **1** uuid `6c58f3e7-74db-431e-a4ba-d67c4240135a`. Gold Room 203 Bed 01 id **10** uuid `7e6a1fb9-a187-4946-b964-572f5826a2ef`.

All beds started **AVAILABLE**. No patient, admission, visit, or encounter was created during configuration.

---

## 5. Bed count

**CONFIRMED**

| Area | Beds |
|---|---|
| Hawawu Maternity Ward | 4 |
| Aisha Children Ward | 3 |
| Emergency Room | 2 |
| Gold Room 203 | 1 |
| Gold Room 202 | 1 |
| Gold Room 204 | 1 |
| Silver 207 | 2 |
| Bronze 208 | 3 |
| Gold Room 210 | 1 |
| Gold Room 211 | 1 |
| Platinum Room 209 | 1 |
| Diamond 214 | 1 |
| Pre Labour Room | 2 |
| Gold Room 212 | 1 |
| Gold Room 213 | 1 |
| Silver 206 | 2 |
| **Total** | **27** |

The implementation brief wrote “TOTAL = 28”. The per-area list sums to **27**. No extra bed was invented. **REQUIRES HOSPITAL DECISION** if a 28th bed exists on the floor and was omitted from the inventory.

After the isolated clinical test: **27 beds, 0 occupied**.

---

## 6. Ward structure

**IMPLEMENTED**

```
Bahmni Hospital
├── Hawawu Maternity Ward          4 beds
├── Aisha Children Ward            3 beds
├── Emergency Room                 2 beds
├── Gold Room 203 … 213            1 bed each (as listed)
├── Silver 207 / Silver 206        2 beds each
├── Bronze 208                     3 beds
├── Platinum Room 209              1 bed
├── Diamond 214                    1 bed
└── Pre Labour Room                2 beds
```

The installed model associates each bed with the area location via `bed_location_map`. Hospital EMR presents that as ward/room + bed. Demo Emergency / General Ward / Pediatric Ward remain in OpenMRS but are not shown on the Hospital EMR board.

---

## 7. Bed naming

**IMPLEMENTED**

Multi-bed areas: **Bed 01**, **Bed 02**, **Bed 03**, …  
Single-bed rooms: **Bed 01**

Staff never see bed uuids, location uuids, or numeric bed ids.

---

## 8. Admission workflow

**IMPLEMENTED** · installed Bahmni ADT

```
Doctor: Admit Patient
  POST bahmniencounter  Consultation + disposition Admit Patient
        ↓
Nursing: patient appears as waiting for a bed (To Admit)
        ↓
Nursing: Assign bed
  1. End open non-IPD visit if present
  2. POST bahmniencounter  encounter type ADMISSION, visit type IPD,
     location = the bed’s area
  3. POST /beds/{bedId}  { patientUuid, encounterUuid }
        ↓
Bed OCCUPIED · IPD visit · Admission Status = Admitted
```

The doctor does **not** choose the bed. Payment is **not** a prerequisite.

---

## 9. Bed assignment workflow

**IMPLEMENTED** · **WRITE** · server-side only

`POST /openmrs/abikan-api/inpatient/assign`

Before write the API checks:

- signed-in user has ward privileges
- patient is not already on a bed
- bed exists in the hospital inventory
- bed is still available (`GET /beds/{bedId}` patients list empty)

If another user takes the bed between display and submit, staff see:

> This bed has just been assigned to another patient. Please choose another bed.

Hospital EMR refuses a second occupant even though Bahmni config `maxPatientsPerBed` is still **2**. Changing that config to 1 is **REQUIRES HOSPITAL DECISION**.

Emergency path: Nursing may assign a bed from the patient chart without a prior doctor admit decision.

---

## 10. Transfer workflow

**IMPLEMENTED** · **WRITE**

`POST /openmrs/abikan-api/inpatient/transfer`

Staff see:

```
Current: Gold Room 203 — Bed 01
Transfer to: Silver 207 — Bed 02
```

Backend:

1. Confirm current assignment
2. Confirm destination available
3. `POST bahmniencounter` encounter type **TRANSFER**
4. `POST /beds/{newBedId}`

The installed bed service ends the previous assignment. Old bed becomes AVAILABLE. New bed becomes OCCUPIED. A TRANSFER encounter is stored.

---

## 11. Discharge workflow

**IMPLEMENTED** · **WRITE**

`POST /openmrs/abikan-api/inpatient/discharge`

Uses the installed API:

`POST /openmrs/ws/rest/v1/bahmnicore/discharge`

which unassigns the bed first, then saves a **DISCHARGE** encounter.

Staff confirmation:

> Patient discharged. Bed released.

Installed behaviour **CONFIRMED** on this server: the IPD visit may remain **open** with visit attribute **Admission Status = Discharged**. Bahmni undo-discharge expects that visit to stay open. Hospital EMR does **not** close the visit.

---

## 12. Nursing workflow

**IMPLEMENTED**

Nursing / Ward (`#/nursing`):

- Hospital-wide board of the 16 areas (demo wards hidden)
- Occupied / available / total
- Click available bed → Assign bed (choose a patient waiting for a bed, or search the chart)
- Click occupied bed → patient chart
- Waiting-for-a-bed list (installed To Admit search across login locations)
- On-the-ward list (occupied beds)

Patient chart (`#/nursing/patient/{uuid}`):

- Assign bed / Transfer patient / Discharge patient
- Open full chart (existing clinical record)
- Patient Account link (read-only financial view)
- **No Pay button**
- Inpatient Nursing Notes list and **+ Nursing Note** action while actively admitted
- Inpatient **Vitals** — Nurse records, Doctor reviews

Care plan and tasks remain **COMING SOON**.

### Inpatient Nursing Notes

**IMPLEMENTED** · immutable · admission-bound

- Each note is a new OpenMRS General patient note observation on the patient's validated Admission encounter.
- Nurses can read and create notes only while the patient has an active bed assignment and open IPD admission. Doctors can read current and historical inpatient Nursing Notes.
- Other workspaces are denied by the Hospital EMR API. The endpoint accepts only `note` and `requestId`; patient, admission, author, and time cannot be selected by the browser.
- The authenticated nurse's OpenMRS user UUID, person UUID, and person display snapshot are stored in server-owned observation metadata. The observation time is generated by the server.
- Notes are append-only. PUT, PATCH, and DELETE receive `405 immutable_record`; corrections require a new note.
- A persisted request marker makes a repeated save return the original note instead of creating a duplicate.
- The existing constrained server service identity performs the OpenMRS write because Nursing does not have the broad Add Observations privilege. Consequently, OpenMRS `obs.creator` is the technical service user; the clinical author shown by Hospital EMR is the authenticated nurse identity preserved in the server-owned metadata. This limitation is intentional and auditable.

### Inpatient Nursing Vitals

**IMPLEMENTED** · append-only · admission-bound

- Vitals remain ordinary OpenMRS numeric observations on the installed CIEL concepts already used by Bahmni Clinical: Temperature `5088…`, Pulse `5087…`, Respiratory rate `5242…`, Systolic `5085…`, Diastolic `5086…`, SpO2 `5092…`, Weight `5089…`, and Height `5090…`. There is no Hospital EMR vitals table.
- Reads use `GET /inpatient/patient/{uuid}/vitals` and are scoped to a validated IPD visit and Admission encounter, following the MAR historical-access model. The active admission is selected by default; Nursing and Doctor may also read a selected discharged admission. Writes use `POST` on the same path.
- Nursing can record only while the patient has an active bed assignment and open IPD admission. After discharge, historical vitals remain readable; new recordings return `409 not_admitted`. Doctor remains read-only (`403` on POST). Other workspaces are denied.
- Each recording creates **new** OpenMRS observations via `POST /openmrs/ws/rest/v1/obs` on the Admission encounter. Observation UUIDs are never reused, so a later set of readings does not overwrite an earlier set. Bahmni Encounter Transaction is not used for this write because posting the same numeric concept onto one encounter can replace the previous value.
- The browser sends only the numeric values and `requestId`. Patient, admission, nurse identity, and observation time are set by the server. The authenticated nurse's user UUID, person UUID, and person display are stored in server-owned observation comments (`ABIKAN_VITALS:v1:`). OpenMRS `obs.creator` is the technical service user for the same privilege reason as Nursing Notes.
- Unusual values may show the concept's existing normal-range warning. Hospital EMR does not diagnose from a vital. Input is rejected when it is non-numeric, incomplete blood pressure, or outside the concept absolute range.
- There is no edit or delete workflow. PUT, PATCH, and DELETE receive `405 immutable_record`. The installed OpenMRS void/amend path is not exposed. A later recording is the correction.
- Units are the staff labels already bound to those concepts (°C, bpm, /min, mmHg, %, kg, cm). Values are not converted.

### Medication Administration

**IMPLEMENTED** · slot-based · immutable

- OpenMRS Drug Order remains the prescription. The installed Bahmni IPD Schedule supplies due-dose slots. The installed Medication Administration model records what happened.
- Hospital EMR does not derive times from frequency and does not create a second order, schedule, or administration store.
- Reads are scoped to a validated inpatient visit and Admission encounter. The active admission is selected by default; Doctor and Nursing may also read a selected discharged admission. The backend confirms the patient, visit, exact order, order encounter visit, inpatient care setting, and slot relationship.
- Writes still require the current active Admission encounter. A discharged admission is read-only even when it has remaining `SCHEDULED` slots.
- Nursing confirms patient, medication, prescribed dose, route, and scheduled time. The browser sends only slot UUID, outcome, reason, and whether the explicit outside-window workflow was selected.
- The backend owns actual time and derives the authenticated Nursing user, person, and provider. The provider is stored as the clinical performer; the user/person/name snapshot is preserved in server-owned administration-note metadata.
- The installed endpoint requires an internal `Get Orders` dependency not assigned to Nursing. As with Nursing Notes, the already-constrained service identity performs the final OpenMRS write after Hospital EMR Nursing authorization and validation. No broad privilege was granted.
- Slot states are the installed `SCHEDULED`, `COMPLETED`, `NOT_DONE`, `STOPPED`, and `MISSED` values.
- Given maps to administration `completed`; Not done and Refused map to `not-done`; Held maps to `stopped`. Refused/Held remain distinct in immutable server metadata and staff display. A reason is required for every non-given outcome.
- The installed IPD dashboard configuration supplies a 30-minute early relevance period and a 60-minute late threshold (`nursingTasks.timeInMinutesFromNowToShowTaskAsRelevant = 30`, `drugChart.timeInMinutesFromNowToShowPastTaskAsLate = 60`, and `drugChartSlider.timeInMinutesToDisableSlotPostScheduledTime = 60`). Normal administration is therefore accepted from 30 minutes before through 60 minutes after the scheduled time.
- A `SCHEDULED` dose before or after that normal window is rejected by the Hospital EMR backend unless Nursing explicitly chooses **Administer outside scheduled window** and records a reason. The exception, reason, timing difference, authenticated nurse, and server time are retained in immutable administration metadata. The scheduled slot time is never overwritten.
- The installed IPD interface can accept a user-selected `administeredDateTime`, but it does not expose a distinct, validated late-documentation workflow that reliably preserves both occurrence time and documentation time. Hospital EMR therefore does not permit backdating: normal and outside-window administration always record the application clock as the actual time. A hospital-approved late-documentation/amendment workflow remains a limitation.
- Scheduled time remains on the slot. Actual time remains on the administration record and is displayed separately. The browser cannot supply an actual-time field.
- A finalized slot is the duplicate key. The installed service returns the existing administration for a repeated submission; separate slots remain separate legitimate doses.
- Doctors read the same validated sheet through the narrow Hospital EMR proxy without receiving broad IPD privileges. The Doctor UI is read-only.
- No PUT, PATCH, or DELETE route is exposed. Finalized administrations are never silently replaced.
- PRN/adhoc administration is not included in this scheduled-dose increment. No synthetic PRN slots are invented.

---

## 13. Doctor workflow

**IMPLEMENTED** · admit only

On the existing consultation page, **Admit Patient** writes the Admit disposition. It does not pick a bed, start IPD, or collect payment.

Refer and Follow-up stay **COMING SOON** (no matching disposition answers on this install).

Doctor discharge remains **COMING SOON**. Nursing performs the actual discharge.

An open visit is required before Admit Patient. The existing “Start OPD visit” action is unchanged.

---

## 14. Permissions

**IMPLEMENTED** · existing privileges only · no new users

| Workspace | View board / stay | Admit decision | Assign / transfer / discharge | Payment |
|---|---|---|---|---|
| Doctor (`app:clinical`) | stay | yes | no | no |
| Nursing / ADT (`app:adt`) | yes | no | yes | no |
| SuperAdmin | yes | yes | yes | cashier workspace only |
| Registration | no | no | no | no (unless already authorised elsewhere) |
| Accountant | no | no | no | existing cashier path |
| Pharmacy / Lab / Radiology | no | no | no | their own fee paths |

Login to a hospital ward/room (or SuperAdmin from any location) opens Nursing. Demo Emergency / General Ward / Pediatric Ward still count as nursing workplaces so existing logins keep working.

---

## 15. Emergency policy

**CONFIRMED** as architecture · **not** an automatic payment bypass

Emergency patients may be admitted immediately. Assign bed does **not** call Odoo and does **not** require a paid invoice. Registration payment gates were **not** changed.

**COMING SOON** for any later “emergency waive / deposit” product rule.

---

## 16. Deposit policy

**REQUIRES ACCOUNTING CONFIGURATION** · **COMING SOON** · not implemented

Patients may pay a deposit. They do not have to pay the entire account before admission. Accountant collects payment. Nursing does not.

This phase does not assume full prepayment. Assign / transfer / discharge never look at invoice balance.

---

## 17. Accommodation billing policy (reserved)

**COMING SOON** · **REQUIRES ACCOUNTING CONFIGURATION** · **not implemented**

Hospital policy (do not code yet):

- Bed assignment starts the accommodation charge immediately.
- The patient does not have to sleep for the charge to exist.
- Assigned 11:00 → charge starts at 11:00.
- Assigned 23:00 → charge starts at 23:00.
- 23:00 → 08:00 is one accommodation day.

Patient Account should later show Accommodation alongside Consultation, Pharmacy, Laboratory, Radiology, and other services — still on the **same Odoo ledger**.

`identify_department` will label an Odoo shop/category containing “accommodation” as **Accommodation** when those products exist. No shop, product, or tariff was created now.

The OpenMRS bed assignment (patient, area, bed, start/end) is the clinical fact later billing will join. Do not copy it into a second database.

---

## 18. Same-day transfer billing policy

**COMING SOON** · **REQUIRES ACCOUNTING CONFIGURATION** · **not implemented**

If a patient moves from a ₦10,000/day bed to a ₦20,000/day bed on the same day:

| | |
|---|---|
| Initial charge | ₦10,000 |
| Already paid | ₦10,000 |
| New tariff | ₦20,000 |
| Additional amount | ₦10,000 |

Charge only the difference. Do not charge ₦20,000 again.

---

## 19. Security

**IMPLEMENTED**

- Browser calls same-origin `/openmrs/abikan-api/inpatient/…` with the OpenMRS session cookie.
- Hospital EMR API forwards that session to installed OpenMRS / Bahmni REST.
- Browser never calls Odoo, never contains Odoo credentials, never writes OpenMRS SQL.
- Privileges are enforced server-side.
- Staff errors name the task, not stack traces, model names, or endpoints.

---

## 20. Test results

**CONFIRMED** · one isolated clinical test · patient **Ibrahim Musa** (ABC200008)

Not used: Adaeze, Aisha, Tunde, John, or other protected financial test patients.

Physical configuration before the clinical test:

- 16 hospital areas
- 27 beds, all AVAILABLE
- 0 occupants

Clinical path:

| Step | Result |
|---|---|
| Start open OPD visit | yes |
| Doctor Admit Patient | Consultation encounter + Admit disposition |
| Nurse assign Gold Room 203 Bed 01 | ADMISSION encounter, IPD visit, bed OCCUPIED |
| Ward stay shows patient | Gold Room 203 · Bed 01 |
| Transfer to Silver 207 Bed 02 | TRANSFER encounter; Gold 203 AVAILABLE; Silver 207 Bed 02 OCCUPIED |
| Discharge | DISCHARGE encounter; Silver 207 Bed 02 AVAILABLE |
| Financial records | none created |

After discharge:

- All 27 beds AVAILABLE
- IPD visit still open with **Admission Status = Discharged** (installed Bahmni behaviour)
- OpenMRS clinical records for this test patient were modified (intended)

---

## 21. Regression results

**CONFIRMED**

`npm test` passed **321/321** frontend tests.

`python3 -m unittest discover -p '*_test.py'` passed **133/133** backend tests.

`npm run build` (`tsc --noEmit && vite build`) **passed**.

Existing routes unchanged: Registration, Doctor, Nursing, Laboratory, Radiology, Pharmacy, Patient Account, Accountant, Consultation.

Protected Odoo records unchanged after the inpatient test:

| Record | State |
|---|---|
| S00001 | draft |
| S00002–S00007 | sale |
| INV/2026/00001–00006 | posted / paid |
| PCSH1/2026/00001–00006 | present |
| WH/IN/00001, WH/OUT/00001, WH/OUT/00002 | present |
| Tax 15% | 15% |
| Currency | USD (unchanged) |

No new sale orders, invoices, payments, products, or stock moves.

Nursing Notes verification on the designated development inpatient **ABC200016**:

- A clearly marked development note was created on Admission encounter `aaf674d5-128d-4697-8a13-71c2590340e4`.
- Persisted note UUID: `bb536c49-b5db-48b8-ade4-f42667962500`.
- Authenticated author snapshot: **Nursing Staff**, with the nurse user UUID and person UUID preserved.
- A second POST with the same request ID returned the same note UUID and did not create another observation.
- The note was visible to Nursing and Doctor sessions; the Laboratory session received `403 forbidden`.
- The later inpatient audit created the named synthetic account `nurse.audit2` (**Hospital EMR Audit Nurse Two**) and confirmed that its server-derived user, person, provider, and display identity are preserved.

Medication Administration verification on the same designated development inpatient:

- Order **ORD-28** (`66f8ace5-b4ae-4b3e-9490-500903b2c7dd`) and schedule `4a4b22c8-ef90-4230-9d95-4292e26df9a8` supplied four installed slots.
- Nursing recorded first slot `63bf22b6-a732-4f77-ba86-84ad1dfba5c8` as Given. Saved administration: `6013d8db-9af0-4269-83cf-cab7e155b1bd`; resulting slot state: `COMPLETED`.
- Scheduled time remained 27 Aug 2026 06:00 Africa/Lagos. Server-owned actual time was 27 Aug 2026 00:27 Africa/Lagos.
- The saved record retained the exact patient, active Admission encounter, order, slot, prescribed dose/route, and authenticated nurse user/person identity.
- Refresh preserved the record. Reposting the same slot returned `duplicate: true` with the same administration UUID and did not create a second administration.
- Doctor displayed the completed record and remaining slots read-only; a Doctor POST received `403 forbidden`. Laboratory read access also received `403 forbidden`.
- At 390 px the card layout remained inside the viewport with no page-level horizontal overflow.
- The comprehensive audit finalized the three remaining synthetic slots to verify the installed state mappings: Refused → `NOT_DONE` (`8f0fce5c-cfef-44ca-a73a-54fa8107b496`), Held → `STOPPED` (`3f035d3c-0033-4905-a51a-a27f47eb2c2e`), and Not done → `NOT_DONE` (`34d3a46d-d3d6-4053-b7bf-48f7c5983cfb`). Reasons and Hospital EMR outcomes remained distinguishable in the administration metadata.
- Timing correction fixture: **ORD-29** (`3d085532-1a49-453b-84ba-dbb9726b1f54`), Amoxicillin 500 mg — TEST. Slot `0cd07cd2-7daf-4ec9-9afb-f35de6626808` was scheduled inside the 30-minute early window and recorded as administration `2df98e37-211e-4572-bd36-ab623d8acb2f`; its scheduled time remained unchanged and its actual time matched the application clock.
- After API restart, the remaining ORD-29 future slot `06fa2a18-01f7-41bf-a4be-09c7063a6460` (about 24 hours later, ~1415 minutes early) returned `409 outside_administration_window` on the normal action, `422 outside_window_reason_required` when `outsideWindow` was set without a reason, and `422 server_fields_only` when `actualTime` or `actualAdministrationTime` was supplied. The slot remained `SCHEDULED` with no administration.
- A further in-window development order **ORD-31** (`654f9258-f4a2-48c8-b31c-34679778259b`), Artemether/Lumefantrine — TEST, was created on the same active ABC200016 admission. Slot `b3616f44-da40-4500-b5f0-1a337dfdfbc8` was eligible (`minutesFromScheduled: 0`) and recorded as administration `b3ef0f73-8316-4860-a322-f7dc8c97576d`. Scheduled time was unchanged; actual time matched the application clock; performer was the authenticated nurse. The ORD-29 future slot remained `SCHEDULED`.
- Historical-access fixture: **ABC200020 — ABIKAN MAR HISTORY TEST PATIENT** (`b4dcc25a-b280-4eba-8fe6-b1674e3879fb`), IPD visit `1e1a676b-af6e-4427-b56f-561eaa4ce56f`, Admission encounter `306d2db0-e3db-4b20-871f-990c137adfe2`, and **ORD-30** (`7ad4ef28-c631-4b81-ae8e-772ef1b192f3`), Vitamin C 100 mg — TEST.
- Historical fixture slot `7d5606af-1f5a-4d9c-9575-53858ba4020c` was recorded as administration `335cef18-e6db-4e3b-a101-c8c388af6beb`, then the admission was discharged normally. After API restart, Nursing and Doctor both still read the same medication, dose, route, scheduled time, actual time, status, and performer with `activeAdmission: false`. Remaining historical slot `f19ca7d0-5c36-4f2c-b248-78c14a0f50f4` stayed `SCHEDULED` and was not writable: Nursing POST returned `409 not_admitted`, Doctor POST returned `403 forbidden`. Laboratory, Accountant, and Pharmacy GET returned `403 forbidden`. ABC200016 was not discharged.
- The audit also created named-Nurse note `f89a6009-9e12-46cb-990d-7b8e325096c6` and verified cross-session Doctor visibility.
- A concurrent duplicate-note audit exposed two observations for one request ID (`e87f4737-7c65-481d-8d28-9fff074c6fba` and `9a461e67-e9b7-42c4-957d-28efb08793ca`). The backend now serializes the existing check/write/confirm sequence. After restart, the same two-request test persisted only `684d7624-511e-4751-9739-f312c157c07b`.

---

## 22. Known limitations

**CONFIRMED**

- Per-area inventory totals **27** beds, not 28.
- Demo Emergency / General Ward / Pediatric Ward / Child test remain in OpenMRS.
- Bahmni `maxPatientsPerBed` is still 2; Hospital EMR assignment refuses a second occupant.
- Bed states on this install are **AVAILABLE** and **OCCUPIED** only. CLEANING / RESERVED / OUT OF SERVICE are **not** invented.
- After discharge the IPD visit may stay open with Admission Status = Discharged.
- Historical MAR remains readable after discharge. Historical Nursing Notes remain Doctor-readable; Nursing Notes GET still requires an active admission for Nursing.
- The installed IPD interface accepts a user-selected administration time, but it does not expose a distinct, validated late-documentation workflow that reliably preserves both occurrence time and documentation time. Hospital EMR therefore does not permit backdating.
- Development measurements showed the ward board at about 2.4–2.6 seconds and the inpatient stay response at about 6.2–7.3 seconds. The patient workspace also requests the ward board independently of the header patient search.
- To Admit on the ward board uses the installed SQL search at each login location (hospital-wide). Global obs search by Disposition concept returns no rows on this REST stack.
- Nursing care plans and tasks are still **COMING SOON**.
- Doctor Refer / Follow-up / discharge decision are still **COMING SOON**.
- Accommodation tariff, daily charge, deposit, and Patient Account accommodation lines are **COMING SOON**.

---

## 23. Next recommended phase

**COMING SOON** · do not start automatically

```
ACCOMMODATION TARIFF
  → DAILY CHARGE (starts at bed assignment)
  → SAME-DAY TRANSFER (charge the difference only)
  → DEPOSIT (not full prepayment)
  → PATIENT ACCOUNT (Accommodation line)
  → ACCOUNTANT PAYMENT
  → BALANCE
```

Still: OpenMRS for the stay, Odoo for money, Hospital EMR for the simple hospital UI.

---

## Hospital EMR API (for implementers)

| Method | Path | Privilege |
|---|---|---|
| GET | `/openmrs/abikan-api/inpatient/board` | `app:adt` |
| GET | `/openmrs/abikan-api/inpatient/patient/{uuid}` | `app:adt` or `app:clinical` |
| POST | `/openmrs/abikan-api/inpatient/patient/{uuid}/admit-decision` | `app:clinical` |
| POST | `/openmrs/abikan-api/inpatient/assign` | `app:adt` |
| POST | `/openmrs/abikan-api/inpatient/transfer` | `app:adt` |
| POST | `/openmrs/abikan-api/inpatient/discharge` | `app:adt` |

Nursing Notes endpoints:

- `GET /openmrs/abikan-api/inpatient/patient/{uuid}/nursing-notes` — Nursing (`app:adt`) for an active admission, or Doctor (`app:clinical`) for current and historical notes.
- `POST /openmrs/abikan-api/inpatient/patient/{uuid}/nursing-notes` — Nursing only; creates one immutable admission-bound note.
- `GET /openmrs/abikan-api/inpatient/patient/{uuid}/vitals` — Nursing or Doctor. Defaults to the active admission; optional `visitUuid` / `admissionEncounterUuid` select a historical inpatient stay. Unauthorized departments remain `403`.
- `POST /openmrs/abikan-api/inpatient/patient/{uuid}/vitals` — Nursing only, and only while the admission is active. Body: numeric vitals plus `requestId`. Patient, admission, nurse, and time are server-owned.
- `GET /openmrs/abikan-api/inpatient/patient/{uuid}/medication-administration` — Nursing or Doctor. Defaults to the active admission; optional `visitUuid` / `admissionEncounterUuid` select a historical inpatient stay. Unauthorized departments remain `403`.
- `POST /openmrs/abikan-api/inpatient/patient/{uuid}/medication-administration` — Nursing only, and only while the admission is active. Body: `slotUuid`, `outcome`, `reason`, optional `outsideWindow`.
- PUT, PATCH, and DELETE are explicitly rejected.

Medication Administration endpoints:

- `GET /openmrs/abikan-api/inpatient/patient/{uuid}/medication-administration` — Nursing or Doctor. Defaults to the active admission; optional `visitUuid` / `admissionEncounterUuid` select a historical inpatient stay. Unauthorized departments remain `403`.
- `POST /openmrs/abikan-api/inpatient/patient/{uuid}/medication-administration` — Nursing only, and only while the admission is active. Body: `slotUuid`, `outcome`, `reason`, optional `outsideWindow`.
- PUT, PATCH, and DELETE are explicitly rejected.

The browser must never POST these payloads to Odoo or to OpenMRS REST directly.
