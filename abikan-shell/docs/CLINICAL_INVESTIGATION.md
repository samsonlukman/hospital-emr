# Clinical investigation (Doctor / Pass 1)

Date: **19 Aug 2026**.

**This is investigation only.** No OpenMRS, Odoo, Bahmni, or Hospital EMR UI/configuration was changed. No visits, encounters, diagnoses, orders, admissions, invoices, or payments were created.

Related: `CLINICAL_WRITE_API.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `INPATIENT_IMPLEMENTATION.md`, `PHARMACY_DISPENSING_IMPLEMENTATION.md`, `LABORATORY_WORKFLOW.md`, `RADIOLOGY_WORKFLOW.md`, `ABIKAN_UI_NAVIGATION.md`, `ABIKAN_USERS_ROLES_WORKPLACES.md`, `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`.

Status used below:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Directly observed in this installation (code + live GET, or a prior documented 2xx write) |
| **INFERRED** | Logically derived from observed behaviour |
| **NOT PRESENT** | Explicitly checked and absent |
| **UNKNOWN** | Could not be established safely without a write or privileged API |

Feature classes for existing Hospital EMR screens: **WORKING** · **PARTIALLY WORKING** · **COMING SOON** · **READ-ONLY** · **BROKEN** · **UNKNOWN**.

---

## 1. Current Clinical architecture

**CONFIRMED**

Hospital EMR Clinical is a staff-facing layer over OpenMRS/Bahmni. Odoo is not the clinical record.

```
doctor.abikan
  privilege app:clinical
  hidden session location OPD-1
  lands on #/doctor
        ↓
  DoctorWorkspace          today's patients (OpenMRS visits)
  ConsultationWorkspace    #/doctor/patient/{uuid}
        ↓
  OpenMRS / Bahmni         visits, encounters, obs, diagnoses, orders, ADT
  Hospital EMR-api               consultation fee, admit decision
  Odoo                     consultation / lab / radiology / pharmacy invoices
```

Bahmni Clinical SPA remains at `/bahmni/clinical/…`. Hospital EMR labels the link **Open full chart**. It is an escape hatch, not the Pass 1 product.

**CONFIRMED** `allowConsultationWhenNoOpenVisit` is `false` in `abikan-config/openmrs/apps/clinical/app.json`. Default visit type **OPD**. Default encounter type **Consultation**.

**CONFIRMED** Clinical Home (`ClinicalHomeWorkspace`) is **not** the doctor landing page. Doctors use `DoctorWorkspace`. `clinicalNav.ts` is unused; live nav is `doctorNav.ts`.

---

## 2. Existing Doctor UI

Account: `doctor.abikan` / `Admin123` (development only). Role `Abikan:Doctor`. Provider exists: `doctor.abikan - Clinical Doctor`. Privilege `app:clinical` plus clinical tabs (consultation, diagnosis, orders, treatment, disposition, history). **NOT PRESENT:** `View Appointments`, `app:adt`, `app:appointments`.

Header: **Clinical**. No location picker. OPD-1 is hidden.

### Navigation

| Item | Hash | Class |
|---|---|---|
| Dashboard | `#/doctor` | **WORKING** (Today's Patients from visits — see `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`) |
| Patient Queue | `#/doctor/queue` | Same screen, scrolls to Today's Patients |
| My Patients | `#/doctor/my-patients` | **WORKING** (Consultation `encounter_provider`) |
| Patients | focuses search | **WORKING** (existing patient search) |

Unknown `#/doctor/…` stays Clinical (established department routing). `#/accountant` as doctor: access denied.

### Feature matrix (Hospital EMR Doctor)

| Feature | Class | Evidence |
|---|---|---|
| Login → Clinical | **WORKING** | Workplace `clinical` → `#/doctor` |
| Open patient by search | **WORKING** | `openConsultation` |
| Today's Patients | **WORKING** | OpenMRS visits via `GET /openmrs/abikan-api/consultation/todays-patients` |
| My Patients | **WORKING** | Consultation `encounter_provider` via `GET /openmrs/abikan-api/consultation/my-patients` |
| Appointment queue | **NOT USED** for the primary list | Appointments remain the scheduling module; they are not the Doctor queue |
| KPI Patients Waiting / Completed Today | **REMOVED** | Those counts were appointment-based and became **0 waiting** after 403 |
| Start OPD visit | **WORKING** (code + prior 201) | `POST /visit` visit type OPD |
| Record vitals | **WORKING** (code + prior 200 + live GET of Pulse 76 on John Adewale) | Individual CIEL concepts on `bahmniencounter` |
| Save consultation (vitals + diagnoses) | **WORKING** (code + prior 200) | Requires open visit and a non-empty draft |
| Diagnosis search + save | **WORKING** (code + live GET search + Tunde read-back) | `bahmniDiagnoses[]` |
| History / examination / notes | **COMING SOON** | Placeholders; concepts exist but UI does not write them |
| Visit / encounter timeline | **READ-ONLY** | Type and date only; **no note text** |
| Lab / radiology display | **READ-ONLY** | Empty on patients inspected today |
| Lab / radiology order buttons | **COMING SOON** | Disabled |
| Medication list | **PARTIALLY WORKING** | `GET bahmnicore/drugOrders` returned **[]** for Aisha even though Pharmacy has her prescription |
| Add prescription | **COMING SOON** | Disabled; payload field unused |
| Consultation fee | **WORKING** | GET Tunde: fee **$75**, **UNPAID**, `canCreateCharge: true`, no Pay button |
| Admit Patient | **WORKING** (code + inpatient implementation) | Hospital EMR `POST …/admit-decision` |
| Refer / Follow-up | **COMING SOON** | Not disposition answers on this server |
| Open full chart | **WORKING** | External Bahmni URL |
| Patient Account | **READ-ONLY** | Doctor GET Tunde account **200** |
| Inpatient ward board | **BROKEN** for doctor | `GET /inpatient/board` **403** (`app:adt` required). Stay GET is allowed |
| Emergency workspace | **COMING SOON** | Tile in `clinicalWorkspaces.ts`, not a department nav |
| Appointments workspace | **COMING SOON** | Privilege `app:appointments`; not on doctor nav |

---

## 3. Visit architecture

**CONFIRMED** live `GET /openmrs/ws/rest/v1/visittype`:

| Name | UUID |
|---|---|
| OPD | `54f43754-c6ce-4472-890e-0f28acaeaea6` |
| IPD | `b7494a80-fdf9-49bb-bb40-396c47b40343` |
| EMERGENCY | `493ebb53-b2bd-4ced-b444-e0965804d771` |
| Special OPD | `f3185c75-2c8c-476a-bf95-c77e8bb42edd` |
| Follow Up | `9772f68d-9fc5-4470-9b87-2b6139011cad` |

### Who creates the visit?

| Actor | What they create | CONFIRMED |
|---|---|---|
| Reception | Can start **OPD** via the same `startOpdVisit` helper (`RegistrationPatientWorkspace`) | Code |
| Doctor | **Start OPD visit** on the consultation screen when none is open | Code + prior 201 |
| Nursing (bed assign) | Ends open **non-IPD** visits, then starts **IPD** with an ADMISSION encounter | `inpatient.py` `assign_bed` |
| Bahmni Clinical SPA | Can also start visits (not Hospital EMR) | Config `defaultVisitType: OPD` |
| Automatic on patient open | **NOT PRESENT** | `allowConsultationWhenNoOpenVisit: false`; Hospital EMR shows a warning and a button |

**CONFIRMED** Hospital EMR Doctor always starts visit type **OPD** at the hidden session location (OPD-1). It does not start IPD, EMERGENCY, Follow Up, or Special OPD.

### Open vs closed

A visit is open when `stopDatetime` is null.

**CONFIRMED** existing open OPD visits (still open on 19 Aug 2026):

| Patient | MRN | Started | Location | Visit UUID |
|---|---|---|---|---|
| Tunde Bakare | ABC200006 | 13 Aug 2026 | OPD-1 | `df41f3a9-…` |
| John Adewale | ABC200012 | 13 Aug 2026 | OPD-1 | `f1444134-…` |
| Adaeze Okafor | ABC200003 | 16 Aug 2026 | OPD-1 | `62196804-…` |
| Aisha Bello | ABC200011 | 17 Aug 2026 | OPD-1 | `43036153-…` |

**CONFIRMED** `GET /visit?fromStartDate=2026-08-19` returned **one** visit: IPD, open, Samson Mamah Luk, location Bahmni Hospital. Occupied beds on the nursing board were **0**. **INFERRED:** leftover IPD visit without a current bed assignment.

**CONFIRMED** Follow Up visits: **0**. EMERGENCY visits: **0**.

### Visit ↔ encounter

**CONFIRMED** Consultation encounters belong to a visit (`visitUuid` on `bahmniencounter`). One visit can hold **multiple** Consultation encounters (Tunde: Consultation on 13 Aug and 16 Aug; John: two Consultation encounters). That is normal Bahmni behaviour, not a bug.

If the doctor opens a patient **with** an open visit: vitals/diagnoses can be saved onto that visit. If **without**: Hospital EMR blocks save and offers **Start OPD visit**.

Closing visits: `POST bahmnicore/visit/endVisit` is used by Nursing when converting to IPD. Doctor UI does **not** end visits. **UNKNOWN** whether abandoned open OPD visits from 13–17 Aug should be closed as hospital policy.

---

## 4. Encounter architecture

**CONFIRMED** live `GET /encountertype`:

| Name | UUID | Typical creator |
|---|---|---|
| Consultation | `d34fe3ab-5e07-11ef-8f7c-0242ac120002` | Doctor save / admit decision / Bahmni Clinical |
| REG | `d352e230-…` | Registration |
| ADMISSION | `d3785931-…` | Nursing bed assign |
| TRANSFER | `d3873bd5-…` | Nursing transfer |
| DISCHARGE | `d37e03e0-…` | Nursing discharge (`bahmnicore/discharge`) |
| INVESTIGATION | `d3b3a2b9-…` | Lab/imaging pipeline |
| LAB_RESULT | `d3bf1623-…` | OpenELIS → OpenMRS |
| RADIOLOGY | `d3a89c59-…` | Imaging pipeline |
| Patient Document | `d3fafd5b-…` | Documents |
| VALIDATION NOTES | `d409e1af-…` | Lab validation |

The consultation encounter is the one with type **Consultation**. Provider is the OpenMRS provider linked to the signed-in user. Location is the session location (OPD-1 for Doctor).

**CONFIRMED** Admit decision also writes a **Consultation** encounter with `disposition.code = ADMIT`, not an ADMISSION encounter. ADMISSION is created later by Nursing.

**CONFIRMED** Hospital EMR Doctor save does **not** send `orders[]`, `drugOrders[]`, or `disposition` on the consultation save. Admit uses a separate Hospital EMR POST.

---

## 5. Consultation workflow

**CONFIRMED** screen sections: Review → Vitals → History → Assess → Diagnose → Order → Prescribe → Disposition.

What the doctor can document **in Hospital EMR today**:

| Field | Mechanism | Class |
|---|---|---|
| Vitals (8 numerics) | `observations[]` CIEL concepts | **WORKING** |
| BMI | Calculated in UI, **not** written | **READ-ONLY** display |
| Coded diagnosis | `bahmniDiagnoses[]` | **WORKING** |
| Consultation Note | Concept `d37294c5-…` exists | **COMING SOON** |
| History of present illness | Concept `1390…` exists | **COMING SOON** |
| Chief complaint | Concept `5219…` coded — do not treat as free text | **NOT PRESENT** in Hospital EMR UI |
| History and Examination set | **Missing** on server (`CLINICAL_WRITE_API.md`) | **NOT PRESENT** |
| Plan / assessment free text | No dedicated concept confirmed for “plan” | **NOT PRESENT** |

Save path: `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter`. Do **not** POST raw `/obs` or `/encounter`.

**CONFIRMED** empty save is skipped (no vitals draft and no diagnosis draft). Leave-guard exists when dirty.

**CONFIRMED** unpaid consultation fee does **not** block chart save (`CONSULTATION_BILLING_IMPLEMENTATION.md`). **PAID ≠ consultation completed.**

---

## 6. Diagnosis workflow

**CONFIRMED**

| Piece | This installation |
|---|---|
| Search | `GET /openmrs/ws/rest/v1/bahmni/terminologies/concepts?term=&limit=20` |
| Live probe | `term=malaria` → 200, four concepts (e.g. Cerebral malaria). No ICD code on the search row |
| Save | `bahmniDiagnoses[]` on the same encounter POST |
| Rank | First draft = PRIMARY, further = SECONDARY |
| Certainty | Hospital EMR writes **CONFIRMED** only |
| Free-text diagnosis | Allowed by Bahmni (`allowOnlyCodedDiagnosis: false`); **NOT PRESENT** in Hospital EMR UI |
| Read-back | `GET /bahmnicore/diagnosis/search?patientUuid=` |
| Delete | `GET …/diagnosis/delete?obsUuid=` privilege `app:clinical:deleteDiagnosis` — **NOT PRESENT** in Hospital EMR UI |
| `/bahmnicore/visit/diagnosis` | 404 — do not use |

**CONFIRMED** Tunde Bakare: Typhoid fever **PRIMARY CONFIRMED**, Chronic Hypertension in Obstetric Context **SECONDARY CONFIRMED**, encounter `d9644ab0-…` (prior documented write, 13 Aug 2026).

Hospital EMR already supports diagnosis. Do **not** create a second diagnosis model. Reuse `bahmniDiagnoses[]`.

Conditions (`POST /emrapi/condition`) exist in Bahmni and in unused Hospital EMR helper `saveConditions`. Doctor UI does **not** call it. **INFERRED:** conditions are a later chart feature, not Pass 1.

---

## 7. Prescription workflow

**CONFIRMED** order type **Drug Order** `131168f4-15f5-102d-96e4-000c29c2a5d7`.

How a doctor **should** create a drug order (Bahmni + `CLINICAL_WRITE_API.md`):

`POST bahmniencounter` → `drugOrders[]` (dose, units, route, frequency, duration, quantity, instructions, `careSetting: OUTPATIENT`).

How it becomes pharmacy work (**CONFIRMED** later pharmacy work, not this investigation’s writes):

```
OpenMRS Drug Order (order UUID)
  → Atomfeed encounter/drug
  → Odoo sale order (Pharmacy Counter)
  → Invoice
  → Accountant payment
  → PAID
  → Pharmacy Ready to Dispense
  → POST /openmrs/abikan-api/pharmacy/prescription/{orderUuid}/dispense
  → Odoo picking done = staff DISPENSED
```

Hospital EMR Pharmacy already consumes `external_order_id` = OpenMRS order UUID. **That chain must not be broken.** Hospital EMR Doctor must not invent a second prescription table.

**CONFIRMED today:**

- Hospital EMR Doctor **does not** write `drugOrders[]` (Coming Soon button).
- `GET bahmnicore/drugOrders?patientUuid=` returned **[]** for Aisha, Adaeze, Tunde, John.
- `GET bahmnicore/drugOrders/active?patientUuid=` for Aisha returned **[]**.
- Pharmacy queue still lists those three patients’ Paracetamol lines (Odoo-backed).

**INFERRED:** the consultation medication list is the wrong read for “what Pharmacy sees.” Pass 1 should not treat an empty Hospital EMR medication list as “no prescription exists.”

Where Hospital EMR should interact later: **one** `bahmniencounter` save that includes `drugOrders[]`, then let Atomfeed/Odoo/Pharmacy proceed. Do not POST raw `/order`. Do not write OpenMRS “Dispensed.”

---

## 8. Laboratory workflow

**CONFIRMED** order type **Lab Order** `d3560b17-5e07-11ef-8f7c-0242ac120002`.

Doctor create path (Bahmni): `orders[]` on `bahmniencounter`, optional `urgency: STAT`. Downstream Atomfeed → OpenELIS. Results return as LAB_RESULT / INVESTIGATION encounters; Hospital EMR reads `GET bahmnicore/labOrderResults`.

**CONFIRMED** this probe: Tunde, John, Aisha, Adaeze — **0** lab orders. John labOrderResults empty.

**CONFIRMED** Hospital EMR Doctor order button is **Coming Soon**. Laboratory workspace can create **charges** for existing orders (`POST …/laboratory/…/charge`); that is billing, not ordering. Clinical must not collect payment.

Do **not** enable new Atomfeed order types. Do **not** create lab products in this investigation (none were created).

---

## 9. Radiology workflow

**CONFIRMED** order type **Radiology Order** `d3561dc0-5e07-11ef-8f7c-0242ac120002`.

Same encounter `orders[]` pattern. PACS/Oviyam is a later imaging concern. Hospital EMR Radiology workspace already has order **display** and billing for existing orders.

**CONFIRMED** patients inspected: **0** radiology orders. Doctor order button **Coming Soon**.

Do not configure PACS in Pass 1.

---

## 10. Admission workflow

**CONFIRMED** intended split is already implemented:

| Role | Action | API | OpenMRS result |
|---|---|---|---|
| Doctor | **Admit Patient** | `POST /openmrs/abikan-api/inpatient/patient/{uuid}/admit-decision` `{ visitUuid, locationUuid }` | Consultation encounter + disposition **Admit Patient** |
| Nursing | **Assign Bed** | `POST /openmrs/abikan-api/inpatient/assign` | End non-IPD visits, **IPD** visit, **ADMISSION** encounter, bed OCCUPIED |
| Accountant | Payment | Existing payment API | Odoo invoice; **not** a prerequisite for assign |

**CONFIRMED** doctor GET stay for Tunde: `assignment` null, not awaiting. Admit is available once an open visit exists.

**CONFIRMED** payment is **not** required for admit or assign (`INPATIENT_IMPLEMENTATION.md`). Accommodation billing is attempted **after** a successful bed write and must not roll back ADT.

**CONFIRMED** Emergency path: Nursing may assign a bed **without** a prior doctor admit decision (`assign_bed` does not check ADMIT disposition).

**CONFIRMED** doctor cannot load the ward board (`GET /inpatient/board` **403**). Doctor **can** load a patient stay (`GET /inpatient/patient/{uuid}` **200**). After admit, Nursing sees the patient on **Admissions** / awaiting; after assign, on the Ward Board as Occupied.

Doctor does not choose the bed. Doctor does not start IPD. Doctor does not discharge.

---

## 11. Emergency workflow

**CONFIRMED** visit type **EMERGENCY** exists. **0** EMERGENCY visits.

**CONFIRMED** three locations with “Emergency” in the name:

| Location | Tags | Role |
|---|---|---|
| Emergency | Login + Admission | Bahmni leftover; hidden from hospital ward board |
| Emergency Room | Login + Admission | Hospital area, 2 beds, on the Nursing board |
| Emergency Ward | Admission only | Leftover, hidden |

**CONFIRMED** Hospital EMR Emergency **workspace** is a placeholder (`clinicalWorkspaces.ts`). It is not a staff department like Nursing/Pharmacy.

**CONFIRMED** consultation billing: emergency payment-later is **REQUIRES HOSPITAL DECISION**, not implemented.

What Hospital EMR should eventually expose (not Pass 1): start or recognise an **EMERGENCY** visit, allow immediate Nursing assign, show payment as later. Do **not** implement a bypass in this investigation.

---

## 12. Patient chart

Doctor consultation **is** the current Hospital EMR chart. Classification of what a doctor needs:

| Information | Class | Notes |
|---|---|---|
| Demographics (name, MRN, age, sex) | **ALREADY AVAILABLE** | `fetchPatientIdentity` |
| Open visit | **ALREADY AVAILABLE** | |
| Allergies | **ALREADY AVAILABLE** | OpenMRS allergy API; often none-recorded |
| Vitals history | **ALREADY AVAILABLE** | Per-concept obs |
| Diagnoses | **ALREADY AVAILABLE** | Tunde has two |
| Encounter list | **ALREADY AVAILABLE** | Type + date; notes **MISSING** |
| Medications | **UNSAFE TO REUSE** as-is | Empty list vs real Pharmacy orders |
| Lab results | **ALREADY AVAILABLE** (empty) | Read path works |
| Radiology results | **ALREADY AVAILABLE** (empty / notes obs) | |
| Previous admissions / stay | **ALREADY AVAILABLE** | Stay GET; board **MISSING** for doctor |
| Clinical notes / HPI / exam | **COMING SOON** / **MISSING** | |
| Appointments | **MISSING** (privilege) | |
| Current location OPD-1 | Hidden by product rule — **do not show** | |

Bahmni full chart remains the completeness backstop until Hospital EMR notes/orders exist.

---

## 13. Doctor queue

**CONFIRMED (investigation):** the previous source `GET /openmrs/ws/rest/v1/appointments` returns **403** without `View Appointments`. The UI then showed empty **0 waiting**, which was misleading.

**IMPLEMENTED (19 Aug 2026):** the primary Clinical list is **Today's Patients**, from OpenMRS visits. See `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`.

Appointments were **not** disabled. They remain the hospital's scheduling mechanism. Doctors were **not** granted View Appointments. The appointment API was **not** changed.

Leftover open OPD visits from 13–17 Aug and Samson's open IPD visit were **not** closed or mutated. They simply do not appear as "today" unless their start datetime falls on the Africa/Lagos hospital day.

---

## 14. Appointment findings

**CONFIRMED** OPD-1 and OPD-2 are tagged **Appointment Location**.

**CONFIRMED** Appointments module API is privilege-gated and **no current Hospital EMR staff user** (including SuperAdmin on `admin.abikan`) has `View Appointments`.

**UNKNOWN** whether any appointment rows exist in the database (could not list them via REST). No SQL was run.

**Recommendation:** Hospital EMR should **not** depend on appointments for Pass 1. A future Appointments department can use the existing module once privileges exist. Relationship to visit: **UNKNOWN** on this install (no visible appointments).

---

## 15. Follow-up findings

**CONFIRMED** Follow Up is a **visit type**, not a disposition. Disposition answers are only Admit / Discharge / Transfer / Undo Discharge.

**CONFIRMED** **0** Follow Up visits.

**INFERRED:** a follow-up is a new (or continued) visit of type Follow Up, not a flag on OPD. Doctor UI **Coming Soon** “Follow-up” must not invent a disposition.

Do not implement follow-up in Pass 1.

---

## 16. Department responsibility boundaries

| Department | Owns | Does not own |
|---|---|---|
| **Reception** | Identity, register patient, start OPD visit when appropriate, registration fee | Payment, consultation documentation, beds, dispense |
| **Doctor** | Consultation, vitals, diagnosis, (later) prescriptions / lab / radiology orders, admit **decision**, consultation fee **create** | Payment, bed assignment, stock, tariffs, user admin |
| **Nursing** | Ward board, assign / transfer / discharge, operational stay | Admit decision (except emergency assign-without-decision), payment, prescribe |
| **Pharmacy** | Ready / dispense using existing Odoo picking | Creating drug orders, marking invoices paid |
| **Laboratory** | Processing/results in OpenELIS; Hospital EMR charge for existing orders | Creating the clinical lab order (Doctor) |
| **Radiology** | Imaging workflow / charge for existing orders | Creating the clinical radiology order (Doctor); PACS redesign |
| **Accountant** | Payments | Dispense, admit, prescribe, edit tariffs |
| **OpenMRS** | Patient, visits, encounters, obs, diagnoses, orders, ADT | Money, stock |
| **Odoo** | Invoices, payments, pharmacy stock | Clinical chart |

No overlapping ledger. Clinical **never** collects payment.

---

## 17. Billing relationship

Established pattern (already live for several departments):

```
Department creates charge (Odoo sale order + invoice)
  → Accountant records payment
  → Department sees PAID / UNPAID / PARTIALLY PAID
```

| Charge | Trigger today | Key | Doctor role |
|---|---|---|---|
| Registration | Reception after visit | `registration:{visitUuid}` | None |
| Consultation | Doctor **Create consultation fee** | `consultation:{visitUuid}` | Create only; no Pay |
| Laboratory | Laboratory workspace after an OpenMRS lab **order** exists | `laboratory:{orderUuid}` | Order (future); not charge |
| Radiology | Radiology workspace after an OpenMRS radiology **order** exists | `radiology:{orderUuid}` | Order (future); not charge |
| Pharmacy | Automatic from Drug Order Atomfeed | `external_order_id` = order UUID | Prescribe (future); never pay or dispense |
| Accommodation | After Nursing assign/transfer | Stay-based | None |

**CONFIRMED** Tunde consultation fee: not yet created, **$75**, create allowed. Chart save is independent of that fee.

Do not add Pay buttons. Do not create a Hospital EMR financial ledger.

---

## 18. What Hospital EMR should own

- Department landing and language (Clinical, not OPD-1)
- Queue of **real** patients to see (visits, not a fake appointment KPI)
- Consultation screen: visit gate, vitals, diagnosis, save, fee status, admit decision
- Later: notes, prescriptions, lab/radiology **order** UI that posts through `bahmniencounter`
- Orchestration: admit-decision and departmental charges
- Honest empty/error states

---

## 19. What OpenMRS / Bahmni should own

- Patient, visit, encounter, obs, diagnosis, order, bed, admission
- Bahmni Clinical SPA as the full chart until Hospital EMR covers notes/orders
- Terminology / drug / test concepts
- Atomfeed to OpenELIS, PACS integration, odoo-connect

Do **not** rebuild these in Hospital EMR.

---

## 20. What Odoo should own

- Consultation / lab / radiology / pharmacy / accommodation invoices
- Payments
- Pharmacy stock and picking

Do **not** rebuild these in Hospital EMR.

---

## 21. Minimum Pass 1 Doctor workflow

Adapted to **this** installation (not the ideal appointment-based sketch).

```
Doctor login
  → Clinical dashboard
  → Today's patients from **visits** (plus search)
  → Open patient
  → Open OPD visit (start if missing)
  → Review identity, allergies, vitals, diagnoses, stay
  → Record vitals
  → Record coded diagnosis
  → Create consultation fee (cashier collects later)
  → Admit Patient if required (Nursing assigns bed)
  → Save consultation
  → Open full chart only when notes/orders are still needed in Bahmni
```

**Out of Pass 1 (present as Coming Soon, not fake):**

- Prescribe (must use `drugOrders[]` later so Pharmacy Atomfeed keeps working)
- Order laboratory
- Order radiology
- Clinical notes / HPI / exam
- Follow-up visit type
- Emergency visit type / Emergency department
- Appointments

**Pass 1 is complete enough** when a doctor can find a patient, open/start an OPD visit, record vitals and a diagnosis, save, raise the consultation fee, and request admission — without knowing Bahmni or Odoo.

That is smaller than “full EMR” and larger than the current queue (which does not work).

---

## 22. Future Clinical features

Do not design these now:

ICU, surgery, anaesthesia, theatre, physiotherapy, dental, oncology, cardiology, blood bank, advanced nursing (MAR, I/O), pharmacy inventory UI, PACS, OpenELIS redesign, appointment booking, follow-up clinic, emergency bypass policy.

---

## 23. Risks / unknowns

| Item | Label |
|---|---|
| Appointment queue 403 for all Hospital EMR users | **CONFIRMED** risk; Pass 1 must not use it |
| Several OPD visits left open since 13–17 Aug | **CONFIRMED**; hospital policy on closing is **UNKNOWN** |
| Open IPD visit (Samson) with 0 occupied beds | **CONFIRMED** inconsistency |
| Doctor medication list empty vs Pharmacy queue | **CONFIRMED** mismatch |
| `drugOrders/active?patientUuids=` (plural) returned HTTP 500 HTML | **CONFIRMED** bad call shape; singular `patientUuid` returns 200 [] |
| Whether any appointments exist in MySQL | **UNKNOWN** (REST forbidden) |
| Live Admit Patient click in this session | **NOT TESTED** (no write) |
| Live consultation save in this session | **NOT TESTED** (prior 13 Aug writes remain) |
| Emergency payment-later policy | **REQUIRES HOSPITAL DECISION** |
| Provider missing on a future doctor user | Would block save/admit (`provider_missing`) |
| Multiple Consultation encounters per visit | **CONFIRMED** normal; UI does not explain “today’s encounter” vs earlier ones |

---

## 24. Recommended implementation sequence

Do **not** start this until the investigation is reviewed.

1. **Queue honesty — done 19 Aug 2026**  
   Today's Patients from OpenMRS visits. See `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`. Appointments left in place as scheduling, not the primary queue.

2. **Keep the working consultation core**  
   Visit gate, vitals, diagnosis, save, consultation fee, Admit Patient. Do not rebuild `bahmniencounter`.

3. **Chart reads that match Pharmacy**  
   If Pass 1 shows medications, use a read that actually returns Drug Orders (investigate `external_order_id` / order REST), or hide the list rather than show a false empty.

4. **Prescriptions (Pass 2)**  
   `drugOrders[]` on the existing encounter POST. Confirm `GET bahmnicore/config/drugOrders` before first write. Isolated test patient. Must produce an Odoo sale order via existing Atomfeed — do not add a second pharmacy path.

5. **Lab then radiology orders (Pass 2/3)**  
   `orders[]` on the same POST. Charges stay in Laboratory/Radiology workspaces. Clinical still has no Pay button.

6. **Notes**  
   Reuse **Consultation Note** and **HPI** concepts only. Do not invent History and Examination.

7. **Follow-up / Emergency**  
   New visit types in the start-visit action, after OPD Pass 1 is stable. Emergency assign-without-decision already exists in Nursing.

8. **Appointments**  
   Only after `View Appointments` exists on a real booking workflow. Optional overlay on the visit queue, not a replacement clinical record.

---

## Open Full Chart — Bahmni Navigation

Date: **24 Aug 2026**. Navigation/session-cookie fix only. No patients, visits, clinical writes, invoices, or RBAC changes.

### Original failure

Doctor Workspace → **Open full chart** opened

`/bahmni/clinical/index.html#/default/patient/{patientUuid}/dashboard`

Bahmni Clinical failed with:

`SyntaxError: Unexpected token 'd', "doctor.abikan" is not valid JSON`

The patient UUID in the URL was already correct. The link does not write storage.

### Root cause

| | |
|---|---|
| SOURCE | Hospital EMR `createSession` wrote cookie `bahmni.user` |
| KEY | `bahmni.user` |
| RAW VALUE | plain username (`doctor.abikan`) |
| EXPECTED | JSON string username (`"doctor.abikan"`), same as Bahmni login `$bahmniCookieStore.put(currentUser, username)` |
| PARSER | Bahmni `$bahmniCookieStore.get`: `angular.fromJson(decodeURIComponent($.cookie("bahmni.user")))` in `clinical.min.317054d3.js` / home sessionService `loadCredentials` |

`bahmni.user.location` was already JSON (`{name, uuid}`) and parsed. `localStorage.LoginInformation` was empty and was not the failure. `JSESSIONID` was unchanged (HttpOnly OpenMRS session).

This was not introduced by visit-preserving Clinical routing. It was already noted for Bahmni Registration after Hospital EMR login.

### Fix

Hospital EMR writes `JSON.stringify(username)` into `bahmni.user`, matching `angular.toJson(username)`. Workspace load rewrites a leftover plain username so a current session does not need a second login. Hospital EMR still reads both encodings. Authentication remains OpenMRS session + existing cookies. No tokens in the URL. No Bahmni Clinical rewrite. Usernames are not hardcoded.

### Verification

Live on 24 Aug 2026, as `doctor.abikan`, no clinical or financial writes:

- Doctor Workspace → **Open full chart** on ABC200016 opened that patient’s Bahmni dashboard (`f242364e-…`).
- Logout showed the same doctor at OPD-1. Cookie `bahmni.user` was the JSON string username. No SyntaxError banner.
- A second patient dashboard (`71f9788f-…` / ABC200017) opened without a stale ABC200016 chart.
- Refresh of the Bahmni page still showed ABC200017.
- Return to Hospital EMR kept Visit #001 selected.
- Reception / Accountant / Nurse cookies use the same encoding; Clinical privilege is unchanged.

Tests: `bahmniUserCookie.test.ts`.

---

## Patient Account — Visit Context

Date: **24 Aug 2026**. Presentation and selected-visit context only. No OpenMRS locations, visit types, patients, visits, or billing data were changed.

### Original behaviour

Doctor Workspace → **Patient Account** opened `#/patient-account/{patientUuid}` with no selected visit.

The header then independently chose the first open visit (or the first visit in the list) and showed:

- **Visit:** raw OpenMRS visit type (`OPD`) and date
- **Location:** `OPD-1` (visit location, or the doctor’s session location if no open visit)

That made `OPD-1` look like the visit. `OPD-1` is the stored OpenMRS location used automatically for General Outpatient and Follow-up. It is not the visit type.

Bills and payments were already patient-level and were left that way.

### Root cause

| | |
|---|---|
| Route | `#/patient-account/{patientUuid}` — patient only |
| Bills API | `fetchPatientAccount(patientUuid)` — patient-level |
| Header visit | `visits.find(open)` then `visits[0]` |
| Visit label | `visitType` (`OPD`) — not the Reception wording |
| Location | `openVisit.location` or session `OPD-1` |

Patient Account did **not** receive the Doctor Workspace `visitUuid`.

### Final display

- **Bills / payments:** remain patient-level.
- **Header visit:** visit-level only when the doctor opened Account from a selected visit (`#/patient-account/{patientUuid}/visit/{visitUuid}`).
- **Copy:** `Visit #001 · General Outpatient` (stored daily visit number + Reception visit wording).
- **Location:** hidden on this screen. `OPD-1` is an implementation location, not useful on a financial page. It is not renamed.

If header search opens a patient without a selected visit, Patient Account does not invent one. Switching patients drops the previous visit from the hash.

Tests: `patientAccountVisit.test.ts`.

---

## Doctor Workspace — My Patients

Date: **25 Aug 2026**.

**My Patients** is patients this logged-in doctor actually attended. It is not Today's Patients, not hospital-wide search, and not a directory of everyone registered.

### Definition

A patient appears when the session doctor is a **Consultation** `encounter_provider` for that patient.

Source of truth:

```
Consultation encounter
  → encounter_provider
  → OpenMRS provider
  → OpenMRS user (the logged-in doctor)
```

Not used: chart viewing, Reception registration, Radiology/Lab/Pharmacy orderer, Today's Patients membership, or a custom doctor–patient table.

`GET /openmrs/abikan-api/consultation/my-patients` resolves the session user → provider, then reads existing visits and keeps Consultation encounters for **that provider only**. OpenMRS `GET /encounter?provider=` returns 500 on this installation. Bahmni `emrapi.sqlSearch.activePatientsByProvider` exists but is **not** used: it is limited to **open** visits at a location, is not Consultation-only, returns a visit UUID per row, and would silently select a visit.

### Sorting, search, empty state

- Default sort: most recent Consultation encounter for this doctor first.
- Search is **within this list** only (name or hospital number). Hospital-wide search stays on the header Patients action.
- Empty: **No patients have been attended by you yet.** Helper: “Patients appear here after you save a Consultation for them.”

### Patient / visit navigation

Open goes to `#/doctor/patient/{patientUuid}` with **no** visit selected. Previous visits stay on the chart. A visit is selected only when the doctor opens `#/doctor/patient/{patientUuid}/visit/{visitUuid}`.

The chart does not fall back to first-open, latest, or billed visit.

### Multi-doctor and multi-visit

The same patient can appear for every doctor who has a Consultation provider relationship. Nobody “owns” the patient. Several consultations still list the patient **once**, using the most recent consultation as the summary. Previous visits continue to show each visit.

### Security

Filtering is server-side from the session provider. The UI does not accept a provider query. Doctor A does not receive Doctor B’s patients. Radiology / Reception cannot call this endpoint (`require_clinician`).

Live check: Clinical Doctor (`doctor.abikan`) sees **ABC200016**. Opening that row does not put a visit in the hash.

---

## Doctor Workspace — Full Audit

Date: **25 Aug 2026**.

Audit of the live Doctor Workspace after the Radiology and My Patients work. This is **cleanup only**: no new clinical forms, databases, billing stores, visit model, or Radiology workflows. Accountant / Payments is in `ACCOUNTANT_PAYMENTS_INVESTIGATION.md`.

### Navigation

| Item | Hash | Role |
|---|---|---|
| Dashboard | `#/doctor` | Same Today's Patients desk (landing page) |
| Today's Patients | `#/doctor/queue` | Today's outpatient visits. **Open** selects that row's visit. |
| My Patients | `#/doctor/my-patients` | Consultation `encounter_provider` for the session doctor. **Open** is patient-only. |
| Patients | header search | Find a patient outside those lists. Opens `#/doctor/patient/{patientUuid}` with **no** visit. |

Unknown `#/doctor/…` stays Clinical. There is no Hospital EMR link to Bahmni Clinical.

### Responsibilities

The doctor reviews the patient, documents the consultation, records diagnosis, orders investigations, prescribes, reviews results, and selects the visit.

The doctor does **not** collect payment, set Radiology prices, fulfil Pharmacy / Laboratory / Radiology, manage PACS, manage users, or register patients.

Consultation fee **create** (send bill to cashier) remains. That is not collecting money.

### Patient / visit model

- Patient-only: `#/doctor/patient/{patientUuid}` — no silent visit selection.
- Selected visit: `#/doctor/patient/{patientUuid}/visit/{visitUuid}`.
- Documentation (chief complaint, history, clinical notes) is **selected-visit only**. Empty copy names the visit. There is no patient-wide `latestObs()` fallback.
- Vitals **display** is latest patient-level observations, labelled **Latest recorded observations for this patient.** New vitals still write to the selected open visit.
- Known Diagnoses / medications / laboratory orders and results are patient-level chart data.
- Radiology orders and reports on the chart are **selected-visit** only.

Hospital number (e.g. ABC200016) is not the visit. Visit copy is `Visit #001 · General Outpatient`. **OPD-1** is hidden as a visit label.

**Attended by** is the Consultation encounter provider, not the logged-in user, searcher, or Radiology orderer.

### Source of truth

| Area | Source |
|---|---|
| Patient / visit | OpenMRS |
| Chief complaint / HPI / clinical notes | OpenMRS observations on the selected visit |
| Known Diagnoses / visit diagnosis save | OpenMRS / Bahmni diagnosis |
| Medications / prescription | OpenMRS drug orders |
| Laboratory list / results | Existing Laboratory / OpenELIS reads (patient-level) |
| Laboratory order write | Selected visit |
| Radiology orders / reports | OpenMRS Radiology orders + Radiology Notes, visit-scoped |
| Vitals display | OpenMRS observations (latest for the patient) |
| Vitals write | Selected open visit |
| Attending doctor | OpenMRS Consultation `encounter_provider` |
| Consultation fee / Radiology payment labels | Odoo via Hospital EMR-api (read-only payment status on Clinical) |

No Hospital EMR clinical database.

### Redundancy findings

| Area | Finding | Action |
|---|---|---|
| Dashboard vs Today's Patients | Same desk, two nav entries (`#/doctor` and `#/doctor/queue`) | Keep |
| Back control | Said Today's Patients even from My Patients / Search | Rename → **← Clinical** |
| Section nav vs screen | Nav listed Consultation before Vitals; screen is Vitals then Consultation | Rename (reorder nav to match screen) |
| Refer / Follow-up | Disabled Coming soon; hospital has no Refer/Follow-up disposition | Remove |
| Clinical notes empty copy | “No clinical notes recorded.” did not name the visit | Rename |
| Laboratory empty copy | Said “this visit” while the list is patient-level | Rename |
| Previous visits description | Said “Earlier visits” while the current visit is listed | Rename |
| Diagnosis recorded list vs Known Diagnoses | Same OpenMRS diagnoses: alert is at-a-glance; Diagnose has Primary/Secondary | Keep |
| Medications vs Prescribe | History list plus prescribe form in one section | Keep |
| Radiology table vs reports | Table is status scan; reports show the note text | Keep |
| Radiology Visit column on the chart | Repeated the selected visit | Remove (chart only) |
| Identity sticky + header | Duplicate while scrolling | Keep |
| Consultation fee title + field label | Inner label repeats the card title | Keep |
| Patient Account | Read-only navigation; bills remain patient-level | Keep |
| Examination / ROS / Family / Social / PMH / Medication History | No hospital OPD forms | Keep hidden |
| Open full chart | Must not return | Keep absent |
| Laboratory Open / Radiology Write Report | Fulfilment belongs to those departments | Keep hidden (`showAction={false}`) |
| Consultation fee create | Established send-to-cashier, not Pay | Keep |
| Lab catalogue price on order picker | Read-only display; doctor does not set it | Keep |
| Vitals wording | Already explicit patient-level latest | Keep |

### Changes made

- Chart back control: **← Clinical** / **Back to Clinical**.
- Visit missing/mismatch copy: return to Clinical, not Today's Patients.
- Section nav order matches the screen: Review → Vitals → Consultation → Previous visits → …
- Removed Refer / Follow-up Coming soon. **Admit Patient** remains.
- Clinical notes empty: **No clinical notes recorded for this visit.**
- Laboratory empty: **No laboratory orders recorded for this patient.**
- Previous visits: **All visits on this chart. Choose one to open it.**
- Diagnose empty: **No diagnoses recorded for this patient.**
- Doctor Radiology table hides the Visit column (already on this visit).
- Narrow layout: wrap the chart top bar; order tables scroll inside the wrap at ~390px.

### Intentional non-changes

- Dashboard and Today's Patients both remain.
- Patient Account link remains (read-only; no Pay on that screen).
- Consultation fee create remains.
- Radiology ordering, pricing, reporting, and PACS remain unchanged.
- Laboratory list stays patient-level (no new visit-filter). Doctor still cannot process specimens.
- My Patients source remains Consultation `encounter_provider`.
- No new clinical concepts, forms, or databases.
- RBAC unchanged. Doctor still cannot open Radiology / Laboratory / Pharmacy / Reception / Accountant workplaces. Patient Account remains allowed as read-only.
- Accountant / Payments not started.

### Security

`app:clinical` opens Clinical and Patient Account. It does **not** open Radiology Worklist, Set Price, Accountant Pay, Pharmacy dispense, Laboratory fulfilment, or Reception registration. No RBAC change in this audit.

### Responsive

At ~390px: section chips wrap, identity remains readable, save bar stacks, orders stack to one column, page has no horizontal overflow. Order tables scroll inside the table wrap. No mobile redesign.

---

## What was inspected (read-only)

- Hospital EMR Doctor/Consultation/Clinical Home code and nav
- `clinicalEncounter.ts`, `clinicalPatient.ts`, `doctorQueue.ts`, `clinicalConcepts.ts`
- `consultation.py`, `inpatient.py` admit/assign
- Existing docs listed at the top
- Live **GET** as `doctor.abikan`, `pharmacy.abikan`, `reception.abikan`, `admin.abikan`: session, visit types, encounter types, order types, visits, encounters, diagnoses, obs, drugOrders, lab/radiology orders, lab results, diagnosis search, consultation fee, patient account, inpatient stay/board, appointments, Emergency locations, Pharmacy queue

**No POST / PUT / PATCH / DELETE** against clinical or financial records. Session authenticate was `GET /session` with Basic (existing login mechanism).

---

## Confirmation

No data or configuration was changed. Existing test consultations (John vitals, Tunde diagnoses), pharmacy dispensing results, invoices, payments, beds, and visits were left as found.
