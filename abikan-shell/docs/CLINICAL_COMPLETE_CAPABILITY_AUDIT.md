# Clinical complete capability audit

Date: **19 Aug 2026**. **Investigation only.** No frontend, backend, concepts, forms, observations, encounters, diagnoses, prescriptions, lab/radiology orders, Odoo, OpenELIS, PACS, or permissions were changed. No clinical or financial records were created or modified.

Related: `CLINICAL_CAPABILITIES_IMPLEMENTATION.md`, `CLINICAL_HISTORY_EXAMINATION_INVESTIGATION.md`, `CLINICAL_WRITE_API.md`, `CLINICAL_INVESTIGATION.md`, `CLINICAL_MEDICATION_IMPLEMENTATION.md`, `PRESCRIPTION_E2E_TEST.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `LABORATORY_BILLING_IMPLEMENTATION.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`, `INPATIENT_IMPLEMENTATION.md`.

Status used below (exactly one per capability):

| Mark | Meaning |
|---|---|
| ✅ WORKING | Existing and tested in Hospital EMR |
| 🟡 EXISTS BUT NOT EXPOSED | Bahmni/OpenMRS has it; Hospital EMR does not show or write it |
| 🔵 EXISTS BUT NEEDS TESTING | Technical path exists; not verified end-to-end in Hospital EMR |
| 🔜 COMING SOON | Intentionally not implemented in Hospital EMR |
| ❓ HOSPITAL DECISION | Hospital/doctor must say how it should work |
| ❌ NOT AVAILABLE | Does not exist in this installation |

Read-only checks: OpenMRS MySQL, Hospital EMR Clinical source, existing implementation docs, live container status. `npm test` (74 passed) and `npm run build` were run; they do not write clinical data.

---

## 1. Executive summary

Hospital EMR Clinical is a hospital-facing layer over **this** Bahmni/OpenMRS. It is not a new medical record.

A doctor can already: sign in, see today’s outpatient visits, search and open a patient, start or continue an OPD visit, record chief complaint / HPI / consultation note / vitals / coded diagnosis / prescription, create a consultation fee (not collect money), and request admission. Save uses one **Consultation** encounter on the open visit.

What the hospital should review is not “every EMR feature,” but:

1. What Hospital EMR already does.
2. What Bahmni/OpenMRS already has that Hospital EMR hides or leaves Coming Soon.
3. What this installation simply does not have (no general examination concept, empty lab order set, PACS unconfigured).

Do not invent examination fields, a second diagnosis model, or a second pharmacy because other products have them.

---

## 2. Current Clinical navigation

Inspected: `doctorNav.ts`, `hashRoute.ts`, `ConsultationWorkspace.tsx` `FLOW`, `WorkspaceRouter.tsx`.

```
Clinical  (#/doctor)   privilege app:clinical
├── Dashboard                 #/doctor                 WORKING
├── Today's Patients          #/doctor  (anchor #queue) / #/doctor/queue
├── My Patients               sidebar Soon             COMING SOON
├── Patients                  header search            WORKING (action)
└── Patient                   #/doctor/patient/{uuid}
    ├── Consultation fee      create charge only
    ├── Patient Account       view (no Pay)
    ├── Open full chart       Bahmni Clinical dashboard (link)
    ├── 1 Review              allergies, known diagnoses, current medications
    ├── 2 Consultation        chief complaint, HPI, clinical notes; exam/history Soon
    ├── 3 Vitals
    ├── 4 Previous visits     visit/encounter timeline (not HPI)
    ├── 5 Diagnose
    ├── 6 Order               lab/radiology read; Order buttons Soon
    ├── 7 Prescribe
    └── 8 Admission           Admit Patient; Refer / Follow-up Soon
```

Dashboard and Today’s Patients are the same Doctor workspace; `#/doctor/queue` scrolls to the table.

Header search placeholder says “name, ID or phone.” The API is `GET /openmrs/ws/rest/v1/patient?q=`. Name and hospital number are the usual OpenMRS search. Whether `phoneNumber` person attribute is included: **UNKNOWN** (not proven this session).

---

## 3. Patient / visit capabilities

| Capability | Hospital EMR | Bahmni/OpenMRS | Status | Notes |
|---|---|---|---|---|
| Today’s Patients | ✅ list from `/openmrs/abikan-api/consultation/todays-patients` | OpenMRS visits | ✅ WORKING | OPD, Special OPD, Follow Up. IPD and EMERGENCY excluded |
| Search by name | ✅ `patient?q=` | REST patient search | ✅ WORKING | Min 2 characters |
| Search by MRN | ✅ same `q=` | Identifier search | ✅ WORKING | Browser-tested ABC200016 |
| Search by phone | Placeholder mentions phone | `phoneNumber` attribute exists | ❓ / 🔵 | Not verified |
| Open patient | ✅ `#/doctor/patient/{uuid}` | Patient uuid | ✅ WORKING | |
| Open existing OPD visit | ✅ uses open visit on the chart | Visit `date_stopped` null | ✅ WORKING | Required to save |
| Start OPD visit | ✅ `POST /visit` OPD | Visit type OPD `54f43754-…` | ✅ WORKING | Location = session (OPD-1) |
| Previous visits | ✅ last 20 visits | `GET /visit?patient=` | ✅ WORKING | Type, date, location, open/closed |
| Visit status | ✅ Open vs closed | `stopDatetime` | ✅ WORKING | |
| Demographics | ✅ name, MRN, age, sex | `GET /patient/{uuid}` | ✅ WORKING | Address not on Clinical header |
| Patient location / admission | Admission shown only after admit; search does **not** show bed | ADT / beds API | 🟡 EXISTS BUT NOT EXPOSED | Nursing search shows bed; Doctor search does not |
| My Patients (this doctor) | 🔜 sidebar | Bahmni `activePatientsByProvider` | 🔜 COMING SOON | Bahmni Clinical search tab exists |
| Emergency visit on this list | Excluded | Visit type EMERGENCY exists | ❓ HOSPITAL DECISION | Emergency workspace also unimplemented |
| IPD on this list | Excluded | Visit type IPD exists | ❓ HOSPITAL DECISION | Nursing owns the ward board |
| Allow consult with no visit | Blocked | `allowConsultationWhenNoOpenVisit: false` | ✅ WORKING | Matches Bahmni |

---

## 4. Review capabilities

What the doctor sees **before/during** consultation (Hospital EMR Review + related sections).

| Information | Source | Hospital EMR | Status |
|---|---|---|---|
| Demographics | `GET /patient/{uuid}` | Identity header | ✅ WORKING |
| Allergies | `GET /patient/{uuid}/allergy` | Review bar + sticky | ✅ WORKING (read). **0** allergy rows live |
| Existing medications | `drugOrders/prescribedAndActive` + `/active` | Review + Prescribe table | ✅ WORKING. Status Ordered / Expired / Stopped. Not “Dispensed” |
| Previous diagnoses | `GET …/bahmnicore/diagnosis/search?patientUuid=` | Review + Diagnose | ✅ WORKING |
| Previous encounters | `GET /encounter?patient=` limit 12 | Previous visits | ✅ WORKING type + date only |
| Clinical timeline | Visits + encounters | Previous visits | ✅ WORKING chronology, not notes |
| Previous consultation notes | Latest HPI + Consultation Note via `GET /obs` | “On this chart” on Consultation | ✅ WORKING latest only. Full note history per visit **not** in the timeline |
| Previous vitals | `GET /obs` last 8 per vital concept | Vitals Latest + History tab | ✅ WORKING |
| Previous laboratory results | `GET …/bahmnicore/labOrderResults?patientUuid=` | Orders section | ✅ WORKING read if results exist |
| Previous laboratory orders | `GET …/bahmnicore/orders?orderTypeUuid=Lab` | Orders section | ✅ WORKING read |
| Previous radiology orders | same, Radiology Order type | Orders section | ✅ WORKING read |
| Previous radiology reports | Radiology Notes concept; RADIOLOGY encounters | Orders “Radiology results” | ✅ WORKING empty-state path. **0** notes historically; PACS unconfigured |
| Other observations | Whole `obs` table | Only vitals, complaint, HPI, note, diagnosis, disposition used | 🟡 dictionary has many unused concepts |
| Conditions (problem list) | `GET /condition`, `POST /emrapi/condition` | `fetchConditions` / `saveConditions` in code, **not** on Consultation UI | 🟡 EXISTS BUT NOT EXPOSED. Live `conditions` table **0** rows |
| Address / next of kin | Registration / Bahmni dashboard | Not on Clinical header | 🟡 EXISTS BUT NOT EXPOSED |
| Open full chart | Link | Bahmni Clinical dashboard | 🟡 EXISTS BUT NOT EXPOSED as Hospital EMR screens (escape hatch) |

---

## 5. Chief complaint

**Live set used by Hospital EMR (not CIEL 5219):**

| Piece | Concept | UUID | Type |
|---|---|---|---|
| Group | Chief Complaint Record | `da47a35d-5806-48b7-b467-e29902759491` | Set N/A |
| Coded | Chief Complaint Coded | `9bb0795c-4ff0-0305-1990-000000000002` | Coded **58 answers** |
| Other | Other generic | `9bb0795c-4ff0-0305-1990-000000000001` | Answer #58 |
| Free text | Chief complaint (text) | `160531AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text |
| Duration | Sign/symptom duration | `1731AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Numeric |
| Unit | Chief Complaint Duration | `9bb0795c-4ff0-0305-1990-000000000003` | Hours/Days/Weeks/Months/Years |

| Question | Finding | Status |
|---|---|---|
| Coded complaints | 58 answers including Fever, Cough, Abdominal pain, … Other generic | ✅ WORKING |
| Other | Other generic + required free text | ✅ WORKING |
| Free text without coded | Allowed | ✅ WORKING |
| Duration + units | Optional; unit required if a number is entered | ✅ WORKING |
| Multiple complaints | Forms 2 History and Examination has `addMore: true`. Hospital EMR UI is **one** group | 🟡 EXISTS BUT NOT EXPOSED (form add-more) / ❓ whether hospital wants several |
| Read-back | `GET /obs` group + members; UI “On this chart” | ✅ WORKING (ABC200016) |
| Same Consultation encounter | Yes | ✅ WORKING |
| CIEL Chief complaint 5219 | Exists, **0** answers | ❌ do not use as the complaint box |
| Config `Chief Complaint Data` | Named in `app.json`; concept **NOT PRESENT** | ❌ NOT AVAILABLE as that set |

---

## 6. History

For each: concept? form? used? Hospital EMR read? write? exposed? Coming Soon?

| Item | Concept | Form | Used (obs) | Hospital EMR read | Hospital EMR write | Exposed | Status |
|---|---|---|---|---|---|---|---|
| History of Present Illness | Yes `1390…` Text | On unused Forms 2 History and Examination | 1 obs (pass 3 TEST) | Yes | Yes | Consultation | ✅ WORKING |
| Past medical history | Set `1633…` (children: added, present, date, text) | Not on OPD form | 0 | No | No | Coming soon row | 🟡 EXISTS BUT NOT EXPOSED + 🔜 + ❓ |
| Past surgical history | Named concept **NOT PRESENT** | — | 0 | — | — | Coming soon (grouped with PMH) | ❌ NOT AVAILABLE as a named concept |
| Medication history | Set `160741…` (also retired `1281…`) | Not on OPD form | 0 | No | No | Coming soon | 🟡 + 🔜 + ❓ |
| Family history | `Family history comment` `160618…` exists. No “Family History” set | Not on OPD form | 0 | No | No | Coming soon | 🟡 + 🔜 + ❓ |
| Social history | Named “Social history” **NOT PRESENT** | — | 0 | No | No | Coming soon | ❌ as a named concept |
| Smoking | Smoking status `163201…` 8 answers | On unused History and Examination form | 0 | No | No | Not even a named Soon row | 🟡 EXISTS BUT NOT EXPOSED + ❓ |
| Review of systems | ConvSet `159615…` | Not on OPD form | 0 | No | No | Coming soon | 🟡 + 🔜 + ❓ |
| Visit timeline labelled History | — | — | — | Yes | No | Renamed **Previous visits** | ✅ WORKING (not HPI) |

Forms 2 **History and Examination** exists but is unused (`form_namespace_and_path` obs = **0**; dashboard `formGroup` empty). Do not treat it as a complete history pack.

---

## 7. Examination

**Do not create an Examination concept.** Inventory only.

| Item | This installation | Status |
|---|---|---|
| General / physical examination concept or set | **NOT PRESENT** as `Examination Notes`, `History and Examination` concept set, `General Physical Examination` | ❌ NOT AVAILABLE (configured workflow) |
| History and Examination Forms 2 | Exists; **no examination section** (complaint, HPI, smoking, images, videos) | ❌ not an exam form |
| Orthopaedic Examination form | Published; 3 text fields; **0** obs | 🟡 EXISTS BUT NOT EXPOSED + ❓ specialty |
| Obstetrics and Gynaecology form | Published; unused | 🟡 + ❓ |
| Diabetes / Hypertension / Malaria forms | Published; unused | 🟡 + ❓ disease templates |
| Dictionary fragments | Abdominal examination (text), Musculoskeletal examination (text), General/HEENT exam findings (coded), performance-status coded questions | 🟡 dictionary only, **0** obs, not on a live OPD form |
| Cardiovascular / respiratory / neurological exam sheets | No matching fully specified exam **forms**. Scattered CIEL “findings” / “performance status” only | ❌ as a configured OPD exam |
| Hospital EMR Examination | Coming soon row + copy that a general exam is not configured | 🔜 COMING SOON |
| Bahmni Observations tab `History and Examination` concept set | Configured in `extension.json`; concept **missing** | ❌ NOT AVAILABLE as Bahmni observations tab content |
| Bahmni Obstetrics / Gynaecology / Vitals concept sets | Named in config; concepts **missing** | ❌ those tabs have nothing to bind to |

**Hospital decision:** what “examination” means in this OPD (one note vs structured systems vs orthopaedic-only). Until then, do not invent fields.

---

## 8. Vitals

Hospital EMR writes **individual CIEL numerics**, not a missing `Vitals` concept set. Forms 2 Vitals uses **different** concepts and is unused.

| UI | Concept | UUID | Type | Unit | Doctor enter | Nurse enter | Saved | Read back |
|---|---|---|---|---|---|---|---|---|
| Systolic | Systolic blood pressure | `5085…` | Numeric | mmHg | Yes | No (`canRecord={false}`) | Yes | Yes |
| Diastolic | Diastolic blood pressure | `5086…` | Numeric | mmHg | Yes | No | Yes | Yes |
| Pulse | Pulse | `5087…` | Numeric | bpm | Yes | No | Yes | Yes (78 on ABC200016) |
| Temperature | Temperature (C) | `5088…` | Numeric | °C | Yes | No | Yes | Yes |
| Respiratory rate | Respiratory rate | `5242…` | Numeric | /min | Yes | No | Yes | Yes |
| SpO₂ | Arterial blood oxygen saturation (pulse oximeter) | `5092…` | Numeric | % | Yes | No | Yes | Yes |
| Weight | Weight (kg) | `5089…` | Numeric | kg | Yes | No | Yes | Yes |
| Height | Height (cm) | `5090…` | Numeric | cm | Yes | No | Yes | Yes |
| BMI | Calculated in UI from weight+height | Live concept `1342…` Numeric exists | — | Display only | Display only | **Not written** | Calculated | 🟡 concept exists; Hospital EMR does not save BMI |
| Second vitals | Forms 2 published; concept set missing | — | — | No | No | No | — | 🟡 / ❌ set missing |
| Posture | On unused Forms 2 Vitals | — | — | No | No | No | — | 🟡 |

Nurse vitals card: **read-only** this phase (“Recording will reuse the Doctor encounter transaction. Not enabled”).

---

## 9. Diagnosis

| Topic | Finding | Status |
|---|---|---|
| Search | `GET /openmrs/ws/rest/v1/bahmni/terminologies/concepts?term=&limit=20` | ✅ WORKING |
| Coded diagnosis | Select a hit; `bahmniDiagnoses[].codedAnswer.uuid` | ✅ WORKING |
| Available concepts | **37,269** non-retired Diagnosis-class concepts | ✅ WORKING (search, not a short hospital list) |
| Categories / ICD in UI | Search returns name/uuid/matchedName. No ICD column in Hospital EMR | 🟡 mappings exist on some concepts (e.g. ICD-10-WHO on save response) |
| Primary / secondary | First selected = Primary; others Secondary; “Make primary” | ✅ WORKING |
| Multiple diagnoses | Yes | ✅ WORKING |
| Free-text / “Other” diagnosis | Bahmni `allowOnlyCodedDiagnosis: **false**`. Mapper supports `freeTextAnswer`. **Hospital EMR has no free-text diagnosis path** — doctor must pick a search hit (“No matching diagnoses”) | 🟡 EXISTS BUT NOT EXPOSED |
| Why the doctor must select | **Hospital EMR UI choice**, not a hard OpenMRS rule on this server. Bahmni Clinical would allow non-coded | ❓ HOSPITAL DECISION whether to expose Bahmni’s free-text fallback |
| History | `diagnosis/search?patientUuid=` | ✅ WORKING |
| Stored on Consultation | Yes, `bahmniDiagnoses[]` on same POST | ✅ WORKING |
| Problem-list conditions | Separate EMR API; unused in Hospital EMR Consultation | 🟡 |

This is standard **coded** Bahmni search behaviour. The missing piece vs **this** Bahmni config is the non-coded fallback, not a new diagnosis engine.

---

## 10. Clinical notes

| Name | Concept | Form | API | Read | Write | Encounter | Hospital EMR | Status |
|---|---|---|---|---|---|---|---|---|
| Consultation Note | `d37294c5-…` Text | Not required | `observations[]` | Yes | Yes | Consultation | Clinical notes | ✅ WORKING |
| History of present illness | `1390…` | Unused form also contains it | same | Yes | Yes | Consultation | HPI | ✅ WORKING |
| Clinical Note / Assessment / Plan as separate concepts | **NOT PRESENT** as those names | — | — | — | — | — | — | ❌ |
| Examination Notes | **NOT PRESENT** | — | — | — | — | — | Coming soon Examination | ❌ do not reuse Consultation Note as exam unless hospital says so |
| Void/clear old note | Not implemented | — | would be voided obs | Partial | No void | — | Known limitation | 🔜 / ❓ |
| Letters (Admission, Referral, Death, Fitness) | Forms 2 published, unused | Forms 2 | No Hospital EMR renderer | No | No | — | 🟡 + ❓ |

---

## 11. Medications / prescriptions

**Clinical ordering (Doctor)** ≠ **Accountant payment** ≠ **Pharmacy dispensing**.

### Clinical ordering (Hospital EMR Prescribe)

| Piece | Status | Notes |
|---|---|---|
| List existing orders | ✅ | Merge prescribedAndActive + active |
| Medication history (obs set) | 🔜 / 🟡 | CIEL set unused; not the Drug Order list |
| Active / expired / stopped | ✅ | Clinical labels only |
| Search catalogue | ✅ | `GET /drug?q=` |
| Dose, route, frequency, duration, quantity, instructions | ✅ | From `GET …/config/drugOrders` |
| Validation | ✅ | Required fields in hospital language |
| Double-submit lock | ✅ | `prescribeLock` + saving state |
| Write | ✅ | `drugOrders[]` on `bahmniencounter` |
| OpenMRS Drug Order | ✅ | Isolated E2E ORD-7 |
| Care setting | ✅ | OUTPATIENT vs IPD from visit type |
| Dispensed on Doctor screen | Not shown | Dispense is Pharmacy/Odoo picking |

### Pharmacy dispensing

Unchanged isolated path: Drug Order → Atomfeed → Odoo sale/invoice → cashier pay → Pharmacy READY TO DISPENSE → dispense. Doctor cannot dispense.

### Accountant payment

Doctor does not pay. Pharmacy fee appears on Patient Account after the order is created. Doctor can open Patient Account (view).

---

## 12. Laboratory

**No ordering implemented in this audit. Billing not modified.**

| Topic | Finding | Status |
|---|---|---|
| Create Lab Order | Bahmni `orders[]` on encounter, type Lab Order `d3560b17-…` | 🟡 mechanism exists; Hospital EMR button **Coming soon** |
| Catalogue / All_Tests_and_Panels | Concept set exists; **0 set members** | ❌ usable OPD catalogue **NOT AVAILABLE** |
| Test class concepts | 622 Test + 84 LabSet in dictionary | 🟡 raw dictionary, not a hospital panel list |
| OpenELIS | Container up; Atomfeed architecture documented | 🔵 engine exists; doctor ordering not in Hospital EMR |
| Lab results | `GET labOrderResults` | ✅ Doctor **read** on consultation |
| Lab orders list | `GET bahmnicore/orders` | ✅ Doctor **read** |
| Doctor order button | Disabled Coming soon | 🔜 |
| Live orders | **1** Lab Order (prior billing TEST) | — |
| Lab fee | Laboratory workplace + Accountant; **not** Clinical | Doctor does not create lab fee here |
| Hospital test list + prices | Requested from hospital previously | ❓ HOSPITAL DECISION |

---

## 13. Radiology

**No new ordering. Billing not modified.**

| Topic | Finding | Status |
|---|---|---|
| Create Radiology Order | Same encounter `orders[]`, type `d3561dc0-…` | 🟡 mechanism exists; Hospital EMR **Coming soon** |
| Concepts | 255 Radiology/Imaging Procedure; TEST used Chest x-ray | 🟡 dictionary / billing TEST, not a hospital menu |
| Orders list | Doctor read on consultation | ✅ |
| Reports | Radiology Notes `ae6e5490-…`; **0** obs typical | ✅ empty read path |
| PACS | `GET /pacs/studies` HTTP **501** “PACS Server configuration is not defined”. dcm4chee up, empty. `pacsquery.pacsConfig` unset | ❌ usable PACS **NOT AVAILABLE** |
| Studies / MWL | Empty modality table documented | ❌ |
| Doctor order button | Coming soon | 🔜 |
| Live orders | **1** Radiology Order (prior billing TEST) | — |
| Radiology fee | Radiology workplace, not Clinical | Doctor does not create imaging fee here |

---

## 14. Allergies

| Topic | Finding | Status |
|---|---|---|
| Structure | OpenMRS **allergy** table / REST `GET /patient/{uuid}/allergy` — **not** obs | ✅ |
| Records | **0** rows | — |
| Read | Hospital EMR Review + sticky | ✅ WORKING |
| Write | REST typically allows POST; Hospital EMR has **no** allergy form | 🟡 EXISTS BUT NOT EXPOSED / 🔜 |
| Doctor access | View only | ✅ |

Do not add recording in this audit.

---

## 15. Admission / disposition

Live Disposition answers: Admit Patient, Discharge Patient, Transfer Patient, Undo Discharge.

| Action | Doctor Hospital EMR | Nurse | Bahmni | Status |
|---|---|---|---|---|
| Admit Patient | ✅ `POST …/inpatient/…/admit-decision` — **no ward/room/bed** | Assign bed | Disposition ADMIT | ✅ WORKING |
| Discharge decision | Not on Clinical | Discharge on Nursing | Disposition DISCHARGE | 🟡 EXISTS BUT NOT EXPOSED on Doctor |
| Transfer | Not on Clinical | Transfer bed on Nursing | Disposition TRANSFER | 🟡 / Nursing operational |
| Follow-up | Button Coming soon | — | **Visit type** Follow Up, not a disposition answer | 🔜 + ❓ |
| Refer | Button Coming soon | — | Referral letter **form** exists unused; **no** Refer disposition answer | 🔜 + ❓ / ❌ as disposition |
| Emergency | Not this list | — | Visit type EMERGENCY | ❓ Emergency workspace |
| Undo discharge | No | — | Disposition answer exists | 🟡 |

Doctor = clinical decision. Nurse = bed. Do not mix.

---

## 16. Billing initiation

| Charge | Doctor can CREATE from Clinical? | Doctor can PAY? | Who pays |
|---|---|---|---|
| Consultation fee | ✅ Create consultation fee | **No** | Accountant |
| Laboratory fee | **No** (Laboratory workplace) | **No** | Accountant |
| Radiology fee | **No** (Radiology workplace) | **No** | Accountant |
| Pharmacy fee | Indirect: prescribing creates the OpenMRS order → Atomfeed → invoice | **No** | Accountant then Pharmacy dispenses |
| Accommodation fee | **No** (admit only; Nursing/ADT + billing elsewhere) | **No** | Accountant |

Clinical shows payment **status** (Not billed / UNPAID / PAID) and “Please proceed to the cashier.” No Pay, Cash, Bank, or Receipt buttons. Patient Account is view.

---

## 17. Consultation encounter model

```
OpenMRS Visit (usually OPD, open)
    ↓
Consultation encounter  d34fe3ab-5e07-11ef-8f7c-0242ac120002
    location = session (OPD-1)
    provider = GET /provider?user=
    encounterDateTime = existing encounter time if reused, else now
    ↓
observations[]     vitals, Chief Complaint Record, HPI, Consultation Note
bahmniDiagnoses[]  coded diagnoses
drugOrders[]       prescriptions
orders[]           lab/radiology (Bahmni; Hospital EMR not writing yet)
disposition        Admit via Hospital EMR-api, not this payload today
```

| Rule | Behaviour |
|---|---|
| Visit window | If now &lt; visit.startDatetime, **no POST**, warning, Save disabled |
| PAID required to save? | **No** |
| Encounter reuse | Send `encounterUuid` when known; else 60-minute `EncounterSessionMatcher` |
| `bahmniencounter/find` | HTTP 500 on this install — not used |
| Second clinical model | None. No parallel notes table |

---

## 18. Existing Bahmni capabilities Hospital EMR does not expose

Bahmni Clinical (`/bahmni/clinical/`, “Open full chart”) still has boards Hospital EMR does not reproduce:

| Bahmni | Why Hospital EMR does not (yet) |
|---|---|
| Observations tab bound to History and Examination / Vitals / Second Vitals / Obstetrics / Gynaecology **concept sets** | Those **sets are missing**; tabs would be empty or misleading |
| Forms 2 (17 published forms) | `formGroup` empty; no Hospital EMR Forms 2 renderer; History and Examination is not an exam |
| Diagnosis **non-coded** entry | Config allows it; Hospital EMR search-only |
| Conditions / problem list | API exists; 0 rows; not on Consultation |
| Medications tab (full Bahmni treatment UI) | Hospital EMR has a thinner prescribe form on the same Drug Order API |
| Orders tab (lab/radiology/other) | Mechanism exists; catalogue/PACS gaps; Coming soon |
| Bacteriology tab | Tab in `extension.json`; Bacteriology concept **not found** |
| Disposition Discharge / Transfer / Undo | Answers exist; Hospital EMR only Admit |
| My Patients / Active by provider / by location | SQL search handlers exist |
| Dashboard: programs, enrolment, visit attributes, images | Not Clinical’s current job |
| Consultation images / videos | Concepts exist on unused form | ❓ |
| Smoking status | Concept + unused form | ❓ |
| Letters (referral, admission, death, fitness) | Forms 2 | ❓ |
| Disease templates (Diabetes, Hypertension, Malaria, Immunization) | Forms 2 unused | ❓ |

Hospital EMR **does** expose the useful overlap: visit, complaint, HPI, note, vitals, coded diagnosis, drugs, admit, fee create, read lab/rad.

---

## 19. Current doctor workflow (actual)

```
LOGIN  doctor.abikan  (app:clinical, session location OPD-1)
  ↓
CLINICAL  #/doctor
  ↓
TODAY'S PATIENTS  or  SEARCH
  ↓
OPEN PATIENT  #/doctor/patient/{uuid}
  ↓
OPEN VISIT  (existing)  or  START OPD VISIT
  ↓
REVIEW  allergies, diagnoses, medications
  ↓
CONSULTATION  chief complaint, HPI, consultation note
  ↓
VITALS
  ↓
PREVIOUS VISITS  (optional read)
  ↓
DIAGNOSE  search and select coded diagnosis
  ↓
ORDERS  read lab/rad; cannot order
  ↓
PRESCRIBE  OpenMRS Drug Order
  ↓
ADMISSION  optional Admit Patient (no bed)
  ↓
CONSULTATION FEE  optional create (no pay)
  ↓
SAVE  same Consultation encounter
```

**Gaps vs a typical OPD (only where this install can support them):** cannot type a diagnosis that is not in search; cannot order lab/rad from Hospital EMR; cannot record exam; cannot record PMH/ROS; cannot record allergy; cannot add a second chief-complaint group; previous notes are latest-only; nurse cannot record vitals in Hospital EMR yet.

---

## 20. Capability classification (master)

See the table in the audit response. Additional flags:

| Item | Status |
|---|---|
| Login / department isolation | ✅ WORKING |
| Visit-window save guard | ✅ WORKING |
| Encounter uuid reuse | ✅ WORKING (pass 3) |
| Prescription E2E through Pharmacy READY TO DISPENSE | ✅ WORKING (isolated) |
| BMI as saved obs | 🟡 concept exists, not written |
| Phone search | 🔵 UNKNOWN |
| Free-text diagnosis | 🟡 Bahmni allows; Hospital EMR does not |
| Multiple chief complaints | 🟡 form add-more; Hospital EMR one group |
| Lab/radiology **order** from Clinical | 🔜 (API underneath 🟡) |
| Examination | 🔜 because ❌ no suitable configured exam |
| PACS | ❌ |
| Lab panel set | ❌ empty |
| Surgical history concept | ❌ |

---

## 21. Missing capabilities (honest)

Missing **for this hospital OPD**, not “missing vs a textbook EMR”:

1. A defined **examination** (concept/form the hospital actually wants).
2. A **laboratory test list with prices** (set is empty).
3. **PACS** configuration if imaging is to be done here.
4. Hospital call on **free-text diagnosis**, **multiple complaints**, **PMH/ROS/smoking**, **allergy recording**, **Follow-up/Refer**.
5. Nurse vitals write (explicitly deferred).
6. Per-visit **note history** in the timeline.

---

## 22. Hospital decisions

Ask the doctor/hospital, with this inventory in hand:

1. Is coded-only diagnosis acceptable, or should Bahmni’s free-text diagnosis be exposed?
2. What is examination in this OPD?
3. Should PMH / drugs / family / social / ROS / smoking appear on every OPD visit?
4. May more than one chief complaint be recorded?
5. Should previous consultation notes appear on Previous visits?
6. When will the lab catalogue and prices be supplied?
7. Is radiology in scope before PACS is configured?
8. Follow-up as a visit vs a button? Refer as a letter vs something else?
9. Should Emergency visits appear on Today’s Patients?
10. Who records vitals — doctor only, or nurse on the same encounter?

---

## 23. Recommended next steps

1. **Show this inventory to the doctor.** Do not add features because other EMRs have them.
2. If they need **typed diagnosis**, expose Bahmni’s existing `freeTextAnswer` — do not invent a second diagnosis system.
3. If they need **examination**, decide the concept/form first; do not auto-create Examination Notes.
4. **Laboratory ordering** only after a real test list and prices.
5. **Radiology ordering** only after PACS (or a conscious “order without images” decision).
6. Do **not** rebuild Drug Order, consultation fee, admit/bed split, or Pharmacy/Atomfeed.

### What not to build because Bahmni/OpenMRS already provides it

- New chief complaint / HPI / Consultation Note concepts  
- New vitals concepts  
- New diagnosis search API  
- New drug-order engine  
- New visit/encounter model  
- New allergy table  
- New disposition answers for Admit  
- Embedding the History and Examination form **as if it were an exam**

---

## 24. npm tests and build

- `npm test`: **74 passed** (no application data written).
- `npm run build`: succeeded (frontend bundle only).

**Data changed this audit: none.**

---

*End of audit. Stop. No implementation.*
