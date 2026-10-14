# Inpatient — ward, room, bed, admission, billing

Date: **17 Aug 2026** (UTC). **Investigation and architecture only. No writes.**

Related: `ADT_BED_WORKFLOW.md` (installed ADT APIs), `CLINICAL_WRITE_API.md`, `PHARMACY_WORKFLOW.md`, `LABORATORY_BILLING_IMPLEMENTATION.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `REGISTRATION_BILLING_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`.

This phase does **not** create wards, rooms, beds, admissions, tariffs, Odoo products, invoices, patients, visits, or encounters. Existing Registration, Consultation, Laboratory, Radiology, Pharmacy, Accountant, and Patient Account workflows are unchanged.

```
OpenMRS  — clinical source (visit, admission, location, bed assignment, orders)
Odoo     — financial source (tariff products, daily accommodation invoices, payments)
OpenELIS — laboratory processing
PACS     — imaging
Hospital EMR   — simple hospital UI on top of those engines
```

Do not create a parallel clinical database or a second financial ledger in Hospital EMR.

Status labels: **CONFIRMED** · **UNKNOWN** · **NOT PRESENT** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION**

---

## 1. Existing inpatient architecture

**CONFIRMED**

This installation already has Bahmni ADT / bed management. It is empty of real beds and empty of admissions.

```
Doctor consultation (usually OPD)
  disposition Admit Patient
        ↓
  To Admit queue
        ↓
  Nurse / ward clerk (privilege app:adt)
  chooses Ward → Room → Bed
        ↓
  POST bahmniencounter  encounter type ADMISSION  visit type IPD
  POST /beds/{bedId}    assign patient
        ↓
  Visit attribute Admission Status = Admitted
  Bed status OCCUPIED
        ↓
  Nursing / bed board
        ↓
  Transfer: TRANSFER encounter + assign new bed
  Discharge: POST /bahmnicore/discharge  (unassigns bed, then DISCHARGE encounter)
```

| Piece | This installation |
|---|---|
| Bed Management module | `bedmanagement-6.0.0.omod` **started** |
| Bahmni IPD | `bahmni-ipd-1.1.1.omod` **started** |
| EMR API | `emrapi-1.36.0.omod` |
| Medication administration | `medication-administration-1.0.0.omod` **started**, **0** rows |
| Operational UI | `/bahmni/bedmanagement/#/home` (home tile **Bed Management**, privilege `app:adt`) |
| Classic ADT | `/bahmni/adt/` still on disk; home tile points to bedmanagement |
| Admin beds OWA | `/openmrs/owa/bedmanagement/admissionLocations.html` |
| Hospital EMR Nursing | `#/nursing`, `#/nursing/patient/{uuid}` — **read-only** bed board + chart |

**CONFIRMED live:** **0** beds, **0** bed types, **0** ADMISSION / TRANSFER / DISCHARGE encounters, **0** IPD visits, **0** bed assignments.

Companion API detail remains in `ADT_BED_WORKFLOW.md`. Live probes on 17 Aug 2026 match that document.

---

## 2. Existing OpenMRS locations

**CONFIRMED** · **READ-ONLY** · none created or modified

There is **no** separate “Room” or “Bed” location tag. Hierarchy is ordinary parent/child locations plus tags.

Location tags (live):

| Tag | UUID | Used for |
|---|---|---|
| Admission Location | `9f79d118-4449-4c6e-845c-58b61d70c0bc` | Ward/room that may hold a bed grid |
| Login Location | `b8bbf83e-645f-451f-8efe-a0db56f09676` | Where staff sign in; ward list API uses this ∩ Admission |
| Visit Location | `d76dbe0e-5e07-11ef-8f7c-0242ac120002` | Hospital |
| Facility | `46abb48c-dbcd-427c-9b59-5162ec337353` | Hospital |
| Appointment Location | `e1e24b0d-5e07-11ef-8f7c-0242ac120002` | OPD-1, OPD-2 |
| Operation Theater | `c9f8f40c-5e07-11ef-8f7c-0242ac120002` | OTs |

Tree (names and UUIDs live):

```
Bahmni Hospital  72636eba-29bf-4d6c-97c4-4b04d87a95b5   Facility, Visit Location
├── Registration Desk  1973e910-…   Login
├── OPD-1              5e232c47-…   Login, Appointment
├── OPD-2              62b55a63-…   Login, Appointment
├── Emergency          b5da9afd-…   Login, Admission     ← ward list
│   ├── Emergency Ward 9212680d-…   Admission
│   └── Test Ward      78f9f969-…   Admission
│       └── Child test aebebbe6-…   Admission  (only layout cells; no real beds)
├── General Ward       8e6ad830-…   Login, Admission     ← ward list
│   ├── General Ward Room-1  046a84ac-…
│   └── General Ward Room-2  6f9ad5d9-…
├── Pediatric Ward     60864f46-…   Login, Admission     ← ward list
│   └── Pediatric Ward Room-1  df352801-…
├── General OT         44cc2e40-…   Operation Theater
└── Orthopaedic OT     9a1e5cd6-…   Operation Theater
```

`GET /openmrs/ws/rest/v1/admissionLocation` returns **only** the three login-capable admission locations: **Emergency**, **General Ward**, **Pediatric Ward**. Each has `totalBeds=0`, `occupiedBeds=0`, `bedLayouts=[]`.

Child rooms exist as Admission Locations but are **not** login locations, so they do not appear as wards.

**NOT PRESENT:** Hawawu Maternity Ward, Aisha Children Ward, Gold / Silver / Bronze / Platinum / Diamond rooms, Pre Labour Room.

**CONFIRMED:** Bahmni uses **locations** for ward and room. It does **not** use locations for the physical bed.

---

## 3. Existing Bahmni IPD architecture

**CONFIRMED**

| Config | Path | Notes |
|---|---|---|
| Classic ADT | `abikan-config/openmrs/apps/adt/app.json` | `defaultVisitType` **IPD**, `maxPatientsPerBed` **2**, `enableIPDFeature` true |
| IPD / bedmanagement | `abikan-config/openmrs/apps/ipd/app.json` | same IPD default; `hideStartNewVisitPopUp` **false**; ward list SQL `bedManagement.sqlGet.patientListForAdmissionLocation` |
| Queues | `ipd/extension.json`, `adt/extension.json` | To Admit / Admitted / To Discharge / All |
| IPD dashboard | same `ipd/app.json` | vitals, admission details, Ward Nursing Note, Observation Sheet, intake concepts, physician progress — **concept availability not verified as complete** |

`GET /openmrs/ws/rest/v1/ipd/wards` → HTTP **404** Unknown resource. Do not treat Bahmni IPD ward-stats REST as available.

IPD dashboard concept names (Ward Nursing Note, Observation Sheet, Post-Op monitoring, etc.) are **config intent**. Whether every concept set exists with members: **UNKNOWN** (same class of gap as Vitals). Do not invent nursing forms.

`maxPatientsPerBed` is **2**. That conflicts with the hospital rule that a bed must never hold two active patients. **REQUIRES HOSPITAL DECISION** to set this to **1** in a later configuration phase (not now).

---

## 4. Ward representation

**CONFIRMED**

A **ward** is an OpenMRS **location** tagged **Admission Location**. The staff-facing ward list is the subset that is also a **Login Location**.

Existing wards that appear on the board: Emergency, General Ward, Pediatric Ward.

Hospital special areas (not created):

| Hospital name | Installed equivalent | Recommendation |
|---|---|---|
| Hawawu Maternity Ward | **NOT PRESENT** | New admission+login location in a later config phase |
| Aisha Children Ward | Pediatric Ward exists (name differs) | **REQUIRES HOSPITAL DECISION:** rename Pediatric Ward vs create new and retire demo name |
| Emergency Room | Emergency exists | Reuse Emergency; add 2 beds later. Do not create a second Emergency location unless the hospital rejects the demo name |

Wards are **not** Odoo objects. Occupancy is OpenMRS. Price is Odoo.

---

## 5. Room representation

**CONFIRMED**

A **room** in this stack is a **child OpenMRS location** of a ward, also tagged Admission Location. Example: General Ward Room-1.

Beds are then mapped onto that room’s grid (`bed_location_map` row/column).

Hospital named rooms (Gold Room 203, Silver 207, …) are **NOT PRESENT**. They should eventually be OpenMRS locations, not Hospital EMR rows and not Odoo warehouses.

**REQUIRES HOSPITAL DECISION:** whether private rooms sit under one parent login ward (recommended: one “Private rooms” or reused General Ward as login, children = Gold 203, …) or each room is its own login location (awkward for queues, not recommended).

There is no OpenMRS “room type” field. Gold / Silver / Bronze is a **hospital tariff class**, not an installed location tag. Store class on the Odoo product / mapping, not as a new OpenMRS tag, unless the hospital later wants a location tag for filtering.

---

## 6. Bed representation

**CONFIRMED** — option **C**: a Bahmni bed-management model, **not** an OpenMRS Location.

| Table | Role | Rows now |
|---|---|---|
| `bed` | Physical bed: `bed_number`, `status`, `bed_type_id`, uuid | **0** |
| `bed_type` | Required before a bed can be created | **0** |
| `bed_location_map` | Grid cell on a location (row, column, optional `bed_id`) | **3** empty cells on **Child test** |
| `bed_patient_assignment_map` | Patient ↔ bed ↔ encounter, `start` / `end` | **0** |
| `bed_tag` / `bed_tag_map` | Optional tags | **0** |

```
Location (ward or room)
  └── BedLocationMapping (row, column)
        └── Bed (bedNumber, AVAILABLE | OCCUPIED)
              └── BedPatientAssignment (patient, encounter, start, end)
```

Create later via Admin OWA or `POST /openmrs/ws/rest/v1/bed` (`bedNumber`, `bedType`, `row`, `column`, `locationUuid`). **Do not create now.**

**Should beds be OpenMRS locations?** **No.** The installed engine already separates location (ward/room) from `bed`. Making each bed a location would fight Bahmni ADT.

---

## 7. Bed occupancy

**CONFIRMED** installed statuses on `bed.status`:

| Status | Supported now |
|---|---|
| AVAILABLE | **CONFIRMED** (enum + default) |
| OCCUPIED | **CONFIRMED** |
| RESERVED | **NOT PRESENT** |
| CLEANING / UNAVAILABLE | **NOT PRESENT** |
| OUT OF SERVICE | **NOT PRESENT** |

Optional `bed_tag` could mark “cleaning” without changing occupancy. That is a later enhancement (**COMING SOON**), not an installed workflow.

**Double booking**

- Occupancy is stored on the bed and derived as `occupiedBeds` / `totalBeds`.
- Transfer UI refuses a bed that already has `patients.length`.
- Config `maxPatientsPerBed` = **2** still allows two patients on one bed if someone uses the API that way.
- `assignPatientToBed` ends the previous assignment for that patient.

**Recommendation:** later set `maxPatientsPerBed` to **1**. Hospital EMR admit/transfer must refuse an occupied bed. Do not implement that write in this phase.

---

## 8. Admission

**CONFIRMED** — two different “admits”. Mixing them is the usual product mistake.

### A. Doctor intent (not admission)

`POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with disposition **Admit Patient** (`d36dd2e4-5e07-11ef-8f7c-0242ac120002`) on a **Consultation** encounter.

Does **not** create an ADMISSION encounter, IPD visit, bed assignment, or Admission Status.

Patient appears on **To Admit** (`emrapi.sqlSearch.patientsToAdmit`) while the visit is open and has no ADMISSION encounter.

### B. Real admission (Nursing / ADT)

Privilege `app:adt` plus **Assign Beds** for the button.

1. Select a bed (UI requires it even though `bedmanagement.mandatory` = **false**).
2. If current visit is not IPD: see §9.
3. `POST bahmniencounter` `encounterTypeUuid` = **ADMISSION** `d3785931-5e07-11ef-8f7c-0242ac120002`, `visitTypeUuid` = **IPD** `b7494a80-fdf9-49bb-bb40-396c47b40343`, `locationUuid` = session login location, optional Adt Notes.
4. `POST /openmrs/ws/rest/v1/beds/{bedId}` `{ patientUuid, encounterUuid }`.

| Field | Installed source |
|---|---|
| Who initiates intent | Doctor (disposition) |
| Who assigns ward/bed | Nurse / ADT, **not** the doctor |
| Registration | Does **not** admit. Starts **OPD** visits (`defaultVisitType` OPD) |
| Visit type | IPD |
| Encounter type | ADMISSION |
| Admission location | Session login location on the encounter |
| Bed | `bed_patient_assignment_map` + bed OCCUPIED |
| Admission datetime | Encounter / visit start |
| Admitting provider | Encounter providers (same as consultation) |
| Diagnosis | Existing diagnoses on the chart; not a required ADT field |
| Admission Status visit attribute | **Admitted** |

**NOT PRESENT:** any live admission to inspect.

---

## 9. OPD → IPD transition

**CONFIRMED** the installed stack already supports this. Do not invent a second workflow.

Typical hospital path:

```
Registration (OPD visit)
  → Doctor consultation
  → disposition Admit Patient
  → To Admit
  → Nursing assigns bed
  → ADMISSION encounter + IPD visit + bed OCCUPIED
```

Installed bed-management JS (`bedmanagement.min.6078b74d.js`):

- `defaultVisitType` = **IPD**
- `hideStartNewVisitPopUp` = **false** (IPD config)
- `enableAutoConvertToIPDVisit` not set → **false**
- If the current visit is **not** IPD: staff get `visitChangeConfirmation.html` (close current visit and start IPD), unless auto-convert is enabled
- If `hideStartNewVisitPopUp` is true: `closeCurrentVisitAndStartNewVisit()` without that dialog

So OPD does **not** silently become IPD. The ADT step can **end the OPD visit and start an IPD visit**. Exact visit-uuid continuity after confirm: **UNKNOWN** without a live write (forbidden in this phase). Architecture must treat IPD as the inpatient visit going forward.

Doctor disposition alone does **not** change visit type.

Emergency may skip OPD entirely: visit type **EMERGENCY** `493ebb53-b2bd-4ced-b444-e0965804d771` already exists, and Emergency is already a login + admission location.

---

## 10. Transfer

**CONFIRMED** in installed JS / Java. **0** live TRANSFER encounters.

```
POST bahmniencounter  encounterTypeUuid = TRANSFER  d3873bd5-5e07-11ef-8f7c-0242ac120002
POST /beds/{newBedId}  { patientUuid, encounterUuid }
```

`assignPatientToBed` ends the previous `bed_patient_assignment_map` row (`end` timestamp) and starts a new one. Old bed returns to AVAILABLE when it has no remaining occupants.

Preserved: patient, previous assignment (start/end), new bed, TRANSFER encounter (timestamp, location, provider).

Bed → bed, room → room, and ward → ward are the same API: the new bed’s location is the new room/ward. There is no separate “ward transfer” object.

Doctor disposition **Transfer Patient** is intent only, like Admit.

---

## 11. Discharge

**CONFIRMED** two layers. **0** live DISCHARGE encounters.

| Layer | What |
|---|---|
| Intent | Disposition Discharge Patient → **To Discharge** queue |
| Actual | `POST /openmrs/ws/rest/v1/bahmnicore/discharge` |

Java `BahmniDischargeController`: **unassign bed first**, then save DISCHARGE encounter `d37e03e0-5e07-11ef-8f7c-0242ac120002`. Bed becomes AVAILABLE.

There is **no** stored state machine “requested → preparation → ready → discharged”. Those would be Hospital EMR labels on:

| Staff label | Backend |
|---|---|
| Discharge requested | Disposition, no DISCHARGE encounter |
| Preparation | Nursing notes on the still-open visit (**COMING SOON**) |
| Ready | **NOT PRESENT** as a coded state |
| Discharged | DISCHARGE encounter + bed free; visit may remain open until ended |

Undo discharge exists as disposition `UNDO_DISCHARGE` when the visit is still open.

What happens to the bed: **released** (`unAssignPatientFromBed`). No cleaning status.

---

## 12. Nursing

**CONFIRMED** Hospital EMR Nursing is already the inpatient UI shell. It must not become a second chart.

Privilege: `app:adt`. Location-gated to **Emergency**, **General Ward**, **Pediatric Ward** (plus SuperAdmin). That list will need updating when hospital ward names exist (**COMING SOON**, not now).

| Already reads | Coming Soon (placeholders, no fake data) |
|---|---|
| Ward list + occupied/available/total from `admissionLocation` | Admit / assign bed from Hospital EMR |
| Bed board from `bedLayouts` (empty today — honest zeros) | Transfer |
| Open visits at login location | Discharge write |
| Patient identity, vitals, diagnoses, drug orders, allergies, encounters | MAR charting, tasks, care plan, I/O, notes write |
| Current bed if assigned | Discharge preparation steps |

Bed assignment from the Nursing screen is explicitly **not available yet**. Do not redesign Nursing; eventually add simple admit/transfer/discharge actions that call the same Bahmni APIs.

To Admit / Admitted / To Discharge SQL handlers exist but need session location (`${visit_location_uuid}`). Hospital EMR does not call them yet. **COMING SOON**.

---

## 13. Inpatient medications

**CONFIRMED** relationship; do not change Pharmacy.

| Layer | Engine |
|---|---|
| Prescribe | OpenMRS Drug Order on the IPD (or OPD) encounter. `care_setting` **Inpatient** `c365e560-c3ec-11e3-9c1a-0800200c9a66` exists. All **6** current orders are **Outpatient**. |
| Supply / bill / stock | Same Odoo pharmacy path (Atomfeed Drug Order → sale order → invoice → cashier → dispense → stock) |
| Give the dose on the ward | MAR tables `medication_administration*` (**0** rows). REST `GET /medicationadministration` = **404** Unknown resource |

Pharmacy counter dispensing is **not** MAR. MAR is **not** stock.

**Recommendation:** keep pharmacy billing/dispense as today. Later, Nursing MAR records that a dispensed dose was given. Do not auto-dispense on admit. Whether ward stock exists: **REQUIRES HOSPITAL DECISION**.

---

## 14. Inpatient laboratory

**CONFIRMED** there is no separate inpatient Lab Order type.

Lab Order `d3560b17-5e07-11ef-8f7c-0242ac120002` is the same object. Visit/encounter/ward come from the IPD visit and login location. OpenELIS still processes. Hospital EMR Laboratory billing already keys `lab:{orderUuid}` on the patient, so an inpatient lab charge still lands on the **same Patient Account**, department **Laboratory**.

Do not create a second lab ledger for IPD.

---

## 15. Inpatient radiology

**CONFIRMED** same pattern as laboratory.

Radiology Order type is unchanged. PACS/DICOM unchanged. Billing key `radiology:{orderUuid}` already ties the charge to the patient, not to OPD vs IPD.

Do not modify Radiology.

---

## 16. Accommodation billing

**NOT PRESENT** in Odoo or OpenMRS.

Live Odoo: no product category for ward/bed/room/accommodation/IPD. Shops are Pharmacy, Registration Desk, Consultation Desk, Laboratory, Radiology Desk only. OpenMRS has no daily bed charge object.

**Recommendation (do not implement now):**

```
Bed assignment (OpenMRS)
  → Hospital EMR backend (session auth)
  → Odoo service product (tariff class)
  → sale.order line per billable day
  → confirm → posted invoice
  → Accountant pays (existing account.payment.register)
  → Patient Account department Accommodation
  → Nursing / Registration see UNPAID / PAID
```

Same rules as other departments: no Odoo credentials in the browser; no second ledger; refuse unapproved placeholder prices (including ₦0.00 / $0.00 / $1.00 until an approved tariff is entered).

Keep **Accommodation** as its **own departmental invoices**, not mixed into Pharmacy/Lab/Radiology. That preserves a reliable PAID/UNPAID per department. A combined “inpatient package” would hide departmental status and is **REQUIRES HOSPITAL DECISION**.

---

## 17. Daily charges

**NOT PRESENT.** Recommend the safest model; do not assume hospital policy.

**Recommended technical model: calendar-day occupancy with a price snapshot**

1. OpenMRS assignment `start` / `end` is the occupancy interval.
2. For each hospital calendar date the bed is occupied, Hospital EMR backend may create **at most one** Odoo line.
3. Idempotency key: `accommodation:{assignmentUuid}:{YYYY-MM-DD}`.
4. `price_unit` copied from the Odoo product at charge time (snapshot). A later tariff change must **not** rewrite billed days.
5. Currency from Odoo. Do not hardcode ₦ or USD.
6. Tax: do not decide; **REQUIRES ACCOUNTING CONFIGURATION**. Do not calculate tax in Hospital EMR.

**REQUIRES HOSPITAL DECISION** (policy, not code):

| Question | Why it matters |
|---|---|
| Is the admission day billed? | Usually yes |
| Is the discharge day billed? | Often no if discharged before a census time |
| Census time | Typically midnight |
| Transfer on the same calendar day | Charge the bed at census, the higher tariff, or split — pick one |
| Partial-day / short stay | Same as admission+discharge policy |
| Readmission | New IPD visit + new assignments → new charges (same patient account) |

Do not implement a nightly job in this phase.

---

## 18. Room / bed tariff model

**NOT PRESENT.** Do **not** hardcode handwritten hospital prices.

Hospital rule (architecture only):

| Kind | Price means |
|---|---|
| Multi-bed room/ward | **Per occupied bed** |
| Single-bed room | **For the entire room** (still one `bed` row for occupancy) |

**Recommended Odoo shape (later):**

- Shop **Inpatient** / **Accommodation** (create later, like Radiology Desk)
- Category e.g. All / Services / Accommodation
- Service products, `invoice_policy=order`, no stock
- One product per **tariff class** (Maternity bed/day, Children bed/day, Emergency bed/day, Gold room/day, …) **or** per named room if Gold 203 and Gold 202 have different prices
- Mapping: OpenMRS **location uuid** (room or ward) → Odoo product. Multi-bed rooms share one product; each occupied bed-day is quantity 1
- Administrator edits `list_price`, validity, active flag in Odoo (or a later Hospital EMR admin screen that writes Odoo server-side)
- Initial approved price may be empty / 0 until entered; Hospital EMR must **refuse** to invoice placeholder 0 the same way Laboratory refuses $1.00

Effective date: Odoo pricelist date **or** simply “do not change list_price of a product that already has billed lines; create a new product / pricelist version”. Snapshot on the invoice line is the safety net.

**REQUIRES ACCOUNTING CONFIGURATION** for NGN, tax, and real tariffs. Current company currency is still **USD**.

---

## 19. Patient Account integration

**COMING SOON** (no accommodation invoices exist)

Reuse the existing Patient Account. Identify department from shop/category name **Accommodation** / **Inpatient** (same `identify_department` pattern).

Staff should eventually see:

```
Accommodation
  Hawawu Maternity Ward · Bed 01 · 17 Aug · 1 day · UNPAID
```

Not sale order ids. Not a second inpatient account screen.

Lab / Radiology / Pharmacy / Consultation charges during an IPD stay already appear on the same patient because they are keyed by patient partner, not by OPD.

---

## 20. Accountant integration

**COMING SOON** for accommodation lines; **UNCHANGED** payment engine.

Accountant continues to see outstanding invoices for the patient and collect via `account.payment.register`. No new payment ledger. No Pay button on Nursing.

Registration / Nursing / Doctor must not choose journals or refund.

---

## 21. Emergency considerations

**CONFIRMED** Emergency is already a login + admission location. Visit type **EMERGENCY** exists. **2** hospital beds are requested; **0** beds exist.

Architectural requirement (do not implement a bypass now):

The billing layer must be able to **skip financial gates** for an emergency admission **if** the hospital later chooses that policy — without rewriting ADT. That is a policy flag on charge creation / “pay before admit”, not a second admission engine.

**REQUIRES HOSPITAL DECISION:**

- A. Pay before admission
- B. Admit first, bill later
- C. Deposit before admission
- D. Emergency exception to A/C
- E. Insurance / HMO
- F. Corporate billing

Technical architecture can support A–D with: optional block on ADT until accommodation (or deposit) invoice is PAID, plus an Emergency location exception. E/F are Odoo partner payment terms / later work.

---

## 22. Maternity considerations

**CONFIRMED** clinical obstetrics exists as **observations**, not as a separate admission module.

- Concept set **Obstetrics** on the clinical dashboard / observation extensions
- Gynaecology set also configured
- Concept **Maternity hospital** exists as Misc
- **No** Hawawu location
- **No** maternity-specific ADT fields (gravida, labour, delivery) on the bed-management admit payload
- Programs on this server: **TB** and **HIV** only — **no** ANC program installed

Maternity admission should use the **same** ADT + bed assignment path. Obstetrics documentation stays on the clinical chart. Do not invent a second maternity EMR.

Special ward treatment: Hawawu is a **ward with 4 billed beds**, not a private room. **REQUIRES HOSPITAL DECISION** which obstetrics forms are mandatory at admission.

---

## 23. Children Ward considerations

**CONFIRMED**

- Pediatric Ward location already exists (name differs from Aisha Children Ward)
- Age is `person.birthdate` (already on the patient header)
- No bed-management age restriction
- Person attributes on this server: phone, email, local names — **no** guardian attribute
- Registration `relationshipTypeMap` includes **Parent** → patient (relationship types live; **0** relationship rows)
- Guardian / next-of-kin concepts exist as **obs questions** (including HIV disclosure wording), not as required admission fields
- **Next of kin details** is a concept ConvSet

Do **not** redesign demographics. If the hospital needs a guardian on the ward board, use existing **Parent** relationship or an observation — **REQUIRES HOSPITAL DECISION**. Do not block admission on age in software unless the hospital asks.

---

## 24. Exact hospital room inventory

**CONFIRMED** as the hospital-supplied physical list. **NOT PRESENT** in OpenMRS. **Do not create.**

Ward-specific (price = **per occupied bed**):

| # | Name | Beds | Kind |
|---|---|---|---|
| 1 | Hawawu Maternity Ward | 4 | Ward |
| 2 | Aisha Children Ward | 3 | Ward |
| 3 | Emergency Room | 2 | Ward / emergency |

Other rooms:

| # | Name | Beds | Price rule |
|---|---|---|---|
| 4 | Gold Room 203 | 1 | Entire room |
| 5 | Gold Room 202 | 1 | Entire room |
| 6 | Gold Room 204 | 1 | Entire room |
| 7 | Silver 207 | 2 | Per occupied bed |
| 8 | Bronze 208 | 3 | Per occupied bed |
| 9 | Gold Room 210 | 1 | Entire room |
| 10 | Gold Room 211 | 1 | Entire room |
| 11 | Platinum Room 209 | 1 | Entire room |
| 12 | Diamond 214 | 1 | Entire room |
| 13 | Pre Labour Room | 2 | Per occupied bed |
| 14 | Gold Room 212 | 1 | Entire room |
| 15 | Gold Room 213 | 1 | Entire room |
| 16 | Silver 206 | 2 | Per occupied bed |

Totals: **16** areas, **27** beds (9 single-bed rooms, 18 beds in multi-bed areas).

Do not add, remove, or invent beds. Do not load handwritten naira amounts into Odoo.

Demo locations (General Ward Room-1, Test Ward, Child test, OTs) are **not** on this list. **REQUIRES HOSPITAL DECISION** whether to retire/rename demo locations in a later config phase. Do not use Child test as a real ward.

---

## 25. Recommended data model

| Object | Source of truth | Notes |
|---|---|---|
| Hospital | OpenMRS location Bahmni Hospital | Already exists |
| Ward | OpenMRS location + Admission Location (+ Login if staff work there) | |
| Room | OpenMRS **child** location + Admission Location | |
| Bed | OpenMRS `bed` + `bed_location_map` | **Not** a location |
| Occupancy | `bed.status` + `bed_patient_assignment_map` | AVAILABLE / OCCUPIED only |
| Admission | ADMISSION encounter + IPD visit + Admission Status | |
| Bed assignment | `bed_patient_assignment_map` | start/end |
| Transfer | TRANSFER encounter + new assignment | |
| Discharge | `/bahmnicore/discharge` | unassigns bed |
| Room/bed tariff | **Odoo** service product + location→product map | Editable; snapshot on invoice line |
| Accommodation charge | Odoo `sale.order.line` `accommodation:{assignmentUuid}:{date}` then invoice | Same confirm path as other departments |
| Payment | Existing `account.payment.register` | |
| Lab / Radiology / Pharmacy on IPD | Existing departmental charges | Same patient account |

Hospital EMR stores **nothing** as a ledger. Optional later: a server-side mapping table is still worse than putting the map on the Odoo product (`uuid` / `default_code` = location uuid), consistent with lab/radiology.

---

## 26. Recommended workflow (staff)

Keep it as simple as the outpatient pattern.

```
Doctor: Admit?  →  Nursing: which bed?  →  Charge: accommodation by day
                                      →  Cashier: collect  →  Ward sees PAID
Pharmacy / Lab / Radiology: unchanged departmental charges on the same patient
```

Staff language: ward, room, bed, admit, transfer, discharge, unpaid, paid. Never OpenMRS, Odoo, UUID, sale order.

Doctor does not pick the bed. Nursing does not collect money. Cashier does not assign beds.

---

## 27. Security

**CONFIRMED** pattern to reuse

- Future Odoo writes stay in `abikan-api` (server-side). No credentials in JavaScript.
- Future admit/transfer/discharge authenticate the OpenMRS session and require `app:adt` + **Assign Beds**.
- Do not create new privileged users.
- Do not expose bed database ids on clinical screens (bed **number** is fine).
- Do not create new OpenMRS roles unless the hospital cannot assign `app:adt` to nurses.

---

## 28. Known limitations

**CONFIRMED**

- Zero real beds; Nursing board correctly shows 0
- Demo ward names ≠ hospital names
- `maxPatientsPerBed` = 2
- No accommodation products or shop
- IPD REST `/ipd/wards` not registered
- MAR REST not registered; tables empty
- No cleaning/reserved/out-of-service occupancy
- Company currency still USD; NGN later
- Queues are location-scoped; private rooms should not each be login locations
- Obstetrics / paediatric forms may be incomplete concept sets (**UNKNOWN** completeness)

---

## 29. Hospital decisions required

**REQUIRES HOSPITAL DECISION**

1. Pay before admission vs admit-then-bill vs deposit vs emergency exception vs HMO/corporate
2. Rename Pediatric Ward → Aisha Children Ward vs create new
3. Reuse Emergency vs rename to Emergency Room
4. Parent login location for private rooms
5. What to do with leftover Test Ward / Child test / General Ward Room-1/2 / OTs
6. Admission-day / discharge-day / same-day transfer billing rules
7. Whether all Gold rooms share one tariff
8. Set `maxPatientsPerBed` to 1
9. Mandatory obstetrics fields at maternity admission
10. Guardian display on children ward
11. Ward stock vs pharmacy counter for inpatient medicines
12. Whether unpaid accommodation should block admit (except emergency)

**REQUIRES ACCOUNTING CONFIGURATION**

- Approved tariffs (start from blank / unbillable until entered — not handwritten naira in code)
- Tax on accommodation
- NGN when Operations is ready
- Inpatient / Accommodation shop and products

---

## 30. Recommended implementation sequence

Do **not** start this sequence until this investigation is reviewed.

1. Hospital/accounting decisions above (policy + tariffs + location naming)
2. **Configuration (OpenMRS Admin / REST, not Hospital EMR invention):** bed type; hospital locations (wards/rooms); beds Bed 01…; `maxPatientsPerBed=1`; do not use Child test
3. **Hospital EMR read:** To Admit / Admitted / To Discharge with session location; real bed board; current bed on the patient
4. **Hospital EMR write (ADT only):** admit = ADMISSION encounter + `POST /beds/{id}`; then transfer; then discharge. No billing yet
5. **Accommodation TEST product** (isolated, named `— TEST`, explicit price, refuse placeholders) + daily charge job/endpoint + Patient Account department
6. Accountant pays using existing Cash path; Nursing sees PAID ≠ discharged
7. **Later, separate:** MAR, nursing notes, obstetrics forms, PACS, NGN, deposits/HMO

Stop after each numbered step for review. Do not create rooms or prices in the same change as ADT writes.

---

## Bed naming

**CONFIRMED** `bed.bed_number` is free text `varchar(50)`. **0** beds, so **no** installed convention.

**Recommend:** `Bed 01`, `Bed 02`, `Bed 03`, `Bed 04` (zero-padded) inside each room/ward. Do not encode the room name in the bed number (the location already has the room name). Do not use G01/P01 unless the hospital asks.

Single-bed rooms still get **one** bed row (e.g. Gold Room 203 / Bed 01) so occupancy and ADT stay uniform.

---

## APIs (read-only reference)

Already documented in `ADT_BED_WORKFLOW.md`. Do not call writes until an implementation phase is approved.

| Read | Endpoint |
|---|---|
| Wards | `GET /openmrs/ws/rest/v1/admissionLocation` |
| Layout | `GET /openmrs/ws/rest/v1/admissionLocation/{uuid}?v=full` |
| Beds | `GET /openmrs/ws/rest/v1/bed` (empty) |
| Patient bed | `GET /openmrs/ws/rest/v1/beds?patientUuid=` |
| Visit types | OPD, IPD, EMERGENCY, Special OPD, Follow Up |

---

## What this phase did not do

No rooms, beds, wards, admissions, tariffs, Odoo products, invoices, charges, patients, visits, encounters, location edits, OpenMRS/Odoo/OpenELIS/PACS/Docker/Atomfeed changes, or UI implementation.

---

*End of investigation.*
