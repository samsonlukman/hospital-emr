# Clinical documentation audit

Date: **23 Aug 2026** (Africa/Lagos).

Investigation against the live OpenMRS/Bahmni installation, then a **UX-only** change: optional sections are collapsed by default. No new clinical database, concepts, forms, consultant routing, or billing changes.

Related: `CLINICAL_HISTORY_EXAMINATION_INVESTIGATION.md`, `CLINICAL_COMPLETE_CAPABILITY_AUDIT.md`, `CLINICAL_CAPABILITIES_IMPLEMENTATION.md`, `CLINICAL_WRITE_API.md`.

Classification: **EXISTS AND WORKS** · **EXISTS BUT NOT EXPOSED** · **EXISTS BUT NOT CONFIGURED** · **MISSING** · **REQUIRES HOSPITAL DECISION**

---

## UX decision

**Optional clinical sections are collapsed by default.**

The doctor sees the title and can open it. Closed does **not** mean a negative finding. Blank means not documented.

Core, already working on the selected visit:

- Chief complaint
- History of present illness
- Clinical notes
- Diagnosis, orders, and prescription (existing workspace sections)

Optional, collapsed, **not writable** in this phase:

- Examination
- Review of Systems
- Past Medical History
- Medication History
- Family History
- Social History

No field was invented. No “No / None / Negative / Normal” default was written.

---

## Shared storage (already in use)

Clinical notes already written from Hospital EMR stay on the **Consultation** encounter of the **selected** visit:

```
patientUuid + visitUuid  (Today's Patients Open)
  → Consultation encounter
  → observations[]
  → encounter_provider (logged-in doctor)
```

Write path remains `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter`. Visit-preserving Open is unchanged.

Live ABC200016 leftover visit `6478a94e-…` already has one Consultation encounter with Chief Complaint Record, HPI, Consultation Note, Pulse, and Visit Diagnoses. Today’s #001 has **no** Consultation encounter yet.

Published Forms 2 records exist. **No** observation on this server has `form_namespace_and_path`. Forms 2 has never been filled here. Clinical `dashboard.json` `formGroup` / `formNames` are **empty**.

No field on the published History and Examination or Orthopaedic Examination forms is marked mandatory.

---

## Examination

| Question | Live answer |
|---|---|
| Classification | **MISSING** as a general OPD examination. **EXISTS BUT NOT CONFIGURED** for Orthopaedic Examination only. **REQUIRES HOSPITAL DECISION** before any write UI. |
| Bahmni/OpenMRS form? | Forms 2 **History and Examination** `d60dd30a-…` is **not** an exam form (complaint, HPI, smoking, images, videos). **Orthopaedic Examination** `0c7a636f-…` has three optional text fields. |
| Concepts | **Examination Notes**, **History and Examination** concept set, **General Physical Examination**: **NOT PRESENT**. Dictionary fragments exist (abdominal / musculoskeletal exam text) with **0** observations. |
| Encounter | Would be Consultation if ever written. None exist. |
| Writable / readable today | Not as a general exam. Orthopaedic form unused. |
| Visit association | N/A — nothing stored. |
| Bahmni UI | Observations tab names a missing **History and Examination** concept set. Dashboard `Examination Notes` is also missing. |
| Hospital vs seed | Bahmni default / seed form names. Not used on this hospital’s OPD chart. |

**Implementation:** collapsed title only. No examination fields.

Do not reuse Consultation Note as examination unless the hospital says so.

---

## Past Medical History

| Question | Live answer |
|---|---|
| Classification | **EXISTS BUT NOT EXPOSED** (CIEL set, unused) plus **EXISTS AND WORKS** for known diagnoses already on the chart. **REQUIRES HOSPITAL DECISION** before turning the CIEL set into an OPD form. |
| Form? | Not on History and Examination. Not on any used OPD form. |
| Concepts | Set `1633…` (added, present, date, text). **0** observations. |
| Encounter | Unused. |
| Already on the chart | Known diagnoses / conditions already show in the review bar. That is diagnosis, not a past-history form. |
| Required? | No. |

**Implementation:** collapsed. Copy points at known diagnoses already on the chart. No second history form.

---

## Medication History

| Question | Live answer |
|---|---|
| Classification | **EXISTS AND WORKS** as the existing medication / prescription list. **EXISTS BUT NOT EXPOSED** as unused CIEL set `160741…` (**0** obs). |
| Form? | No used medication-history form. |
| Source of truth | Existing drug orders / Medications section. Do not duplicate Pharmacy. |
| Required? | No. |

**Implementation:** collapsed. Copy points to **Medications**. No second medicine list and no CIEL medication-history form.

---

## Review of Systems

| Question | Live answer |
|---|---|
| Classification | **EXISTS BUT NOT CONFIGURED**. CIEL ConvSet `159615…` (9 coded systems). **0** observations. Not on the OPD form. **REQUIRES HOSPITAL DECISION**. |
| Answers include | Dictionary answer **Negative** on ROS general. That is not a form default. Hospital EMR must not tick it automatically. |
| Required? | No. |

**Implementation:** collapsed. No checklist. Closed does not mean every system is negative.

---

## Family History

| Question | Live answer |
|---|---|
| Classification | **EXISTS BUT NOT CONFIGURED** (dictionary) / **MISSING** as a hospital relationship list. **REQUIRES HOSPITAL DECISION**. |
| Form? | None on the OPD consultation. |
| Concepts | `Family history comment` `160618…` (text). ConvSet `Patient's family history list` `160593…` (many children). Status answers include “not taken / none / unknown”. **0** observations. |
| Relationships | `relationship_type` and `relationship` tables are **empty**. There is no family tree to show. |
| Required? | No. |

**Implementation:** collapsed. No custom family-history database.

---

## Social History

| Question | Live answer |
|---|---|
| Classification | **MISSING** as a named Social History concept. **EXISTS BUT NOT EXPOSED** for Smoking status on the unused History and Examination form (**0** obs, not mandatory). **REQUIRES HOSPITAL DECISION**. |
| Form? | Smoking only, on an unused Forms 2 form. |
| Named “Social history” | Not present. Patient-generated social-history text `162143…` is dictionary-only, unused. |
| Required? | No. |

**Implementation:** collapsed. Smoking was **not** turned on. That would invent a hospital social-history workflow from seed form content.

---

## What was implemented

Collapsed optional titles in Consultation, after HPI and before Clinical notes.

Core complaint / HPI / notes, diagnosis, orders, prescription, consultation fee, attending provider, and selected `visitUuid` were not changed.

---

## Required fields discovered

None for these optional sections.

Chief complaint still uses the existing Hospital EMR rule: free text is required only when **Other** is selected; duration unit is required only when a duration number is entered. That is existing consultation validation, not a new form rule.

---

## Tests and build

| Command | Result |
|---|---|
| `npm test` | **134 passed**, 0 failed |
| `npm run build` | Succeeded. Bundle `dist/assets/index-CYsNwmI0.js` |

`optionalClinicalSections.test.ts`: collapsed by default, never required, no invented exam/family/social forms, medication history not duplicated, staff copy has no system jargon.

---

## Live verification

Existing TEST patient only. No new patients, visits, invoices, or payments.

| Check | Result |
|---|---|
| Optional titles visible, closed | All six closed. No Coming Soon stack. No inputs |
| Expand Examination | Honest “not configured” copy only |
| Core documentation | Complaint / HPI / notes still on the chart |
| Visit | `#/doctor/patient/…/visit/271181d6-…` (#001) |
| Fee / attending / save | Unchanged |

---

## Stopped here

Writable examination, ROS, past history, family history, and social history were **not** implemented. The live dictionary and unused Forms 2 records are not a hospital OPD form. Enabling them would invent clinical architecture.

Medical Officer / Consultant routing was not started.

---

## Bahmni Clinical Capabilities — Six Optional Sections

Date: **24 Aug 2026** (Africa/Lagos). **Investigation only.** No forms, concepts, tables, OpenMRS configuration, patients, visits, encounters, invoices, charges, or payments were created or changed. No Doctor Workspace code was changed.

Read-only live REST (`doctor.abikan`), MySQL counts, Forms 2 JSON on disk, and Bahmni clinical/registration config. Existing TEST patient ABC200016 (`f242364e-…`) only.

The question is whether Hospital EMR can **expose** what already works, rather than invent six forms.

---

### 1. Examination

**Classification:** **MISSING** as a hospital physical-examination workflow. Dictionary text fragments and an unused Orthopaedic form are **EXISTS BUT NOT CONFIGURED**. **REQUIRES HOSPITAL DECISION** before any write UI.

This is **not** the same as chief complaint, HPI, smoking, images, or Consultation Note.

| Expected finding | Live concept / form | Used? | Obs |
|---|---|---|---|
| General examination | `General examination (text)` `163042…` | No form, not on OPD | **0** |
| Cardiovascular | `Cardiac examination (text)` `163046…` | No form | **0** |
| Respiratory | No “Respiratory examination” concept. Closest: `Chest examination (text)` `160689…` | No form | **0** |
| Abdominal | `Abdominal examination (text)` `160947…` | No form | **0** |
| Neurological | No usable “Neurological examination (text)”. `Neurologic exam findings` `1129…` is coded with **0 answers** | Unusable | **0** |
| Musculoskeletal | `Musculoskeletal examination (text)` `163048…` | On unused Orthopaedic form | **0** |
| Other | HEENT exam findings `1122…` (**0 answers**). Range of Motion / Radiographic Examination on Orthopaedic form | Unused | **0** |
| General exam note | **Examination Notes** — **NOT PRESENT** | Bahmni dashboard names it | — |
| Concept set | **History and Examination** set — **NOT PRESENT** | Observations tab still names it | — |

**Forms**

- Forms 2 **History and Examination** `d60dd30a-…`: complaint, HPI, smoking, images, videos. **No physical examination fields.**
- Forms 2 **Orthopaedic Examination** `0c7a636f-…`: three optional text boxes (MSK, range of motion, radiographic). **0** obs. Specialty seed, not general OPD.
- Clinical `dashboard.json` `formGroup` / `formNames`: **empty**.
- `form_namespace_and_path` on all obs: **0**.

**Bahmni UI:** Observations tab default concept is **History and Examination** (missing set). Dashboard “History and Examinations” names **Chief Complaint Data**, **Examination Notes**, **Smoking History** — those names are also **NOT PRESENT**. A doctor opening Bahmni Observations would not get a working exam sheet.

**APIs:** Ordinary `obs` / `bahmniencounter` could write those text concepts if someone chose to. Nothing does today.

**Level:** If written, examination findings belong on a **Consultation encounter of a specific visit**. They are not patient demographics.

**Writable / readable as a hospital exam?** No.

---

### 2. Review of Systems

**Classification:** **EXISTS BUT NOT CONFIGURED**. **REQUIRES HOSPITAL DECISION**. Not safe to treat as a live OPD form.

| Item | Live |
|---|---|
| Form | None on the used consultation. Not on History and Examination. |
| Concept | ConvSet `Review of systems` `159615…` — 9 coded children (general, HEENT, cardiopulmonary, GI, GU, MSK, CNS, developmental, obstetrical) |
| Observations | **0** for the set and for ROS general |
| Answers | ROS general and HEENT include **Negative** plus symptoms (fever, rash, rhinorrhoea, …) |
| Configured for this hospital? | Dictionary only. Not in `formGroup`. Not used. |
| Bahmni UI | No ROS observations tab. |
| Writable? | Technically via obs. Not hospital-configured. |
| Readable? | Nothing to read. |

**Level:** Symptom review is **encounter / visit** documentation, not a permanent patient attribute.

**Safety:** “Negative” is a **dictionary answer**, not a form default. Exposing the set as a checklist would tempt staff to tick Negative for every system. Blank / collapsed must stay **not documented**.

Do not turn this unused ConvSet into a form because the concepts exist.

---

### 3. Past Medical History

**Classification:** Known diagnoses **EXISTS AND WORKS**. CIEL Past medical history set **EXISTS BUT NOT EXPOSED** (unused). OpenMRS Conditions **EXISTS BUT NOT CONFIGURED** (table empty). **REQUIRES HOSPITAL DECISION** before any second history form.

**What “Known diagnoses” actually is**

Hospital EMR Review bar calls `GET /openmrs/ws/rest/v1/bahmnicore/diagnosis/search?patientUuid=`.

Live ABC200016: **one** row.

| Field | Value |
|---|---|
| Display | **H/O: Malaria** (CIEL `139197…`, ICD-10 **Z86.1** — personal history of infectious disease) |
| Storage | Visit Diagnoses observation `c19012b7-…` |
| Encounter | Consultation `9a88a85d-…` |
| Visit | Leftover OPD `6478a94e-…` (not today’s #001) |
| Order / certainty | PRIMARY / CONFIRMED |
| Provider | Clinical Doctor |

That is **encounter-level** diagnosis, returned **patient-wide**. It is the same object the doctor saves under Diagnosis (`bahmniDiagnoses` on `bahmniencounter`).

**What it is not**

| Source | Live |
|---|---|
| OpenMRS `condition` / problem list | **0** rows. Hospital EMR `fetchConditions` exists; the Review bar does **not** use it. |
| EMRAPI condition | Endpoint **500** on this stack. |
| CIEL Past medical history set `1633…` | 4 children (added, present, date, text). **0** obs. Not on any used form. |

The coded diagnosis is already a **history-of** term (`H/O: Malaria`). Asking the doctor to type “Malaria” again under Past Medical History would be the same fact twice.

**Display vs enter**

- **Display:** keep Known Diagnoses (existing diagnosis search). That is the hospital’s past/current problem list today.
- **Enter:** continue Diagnosis on the selected visit. Do **not** add a Past Medical History form unless the hospital wants a different structure (dates, “still present”, free-text PMH) that diagnoses do not cover.

**Level:** Stored on an encounter; shown as a **patient-level** list. Conditions (unused) would have been the true patient-level problem list.

---

### 4. Medication History

**Classification:** Prescription / drug-order history **EXISTS AND WORKS**. CIEL Medication history set **EXISTS BUT NOT EXPOSED** (unused). **Do not create a second medicine list.**

**Where medicines come from**

| Source | Role |
|---|---|
| `GET …/bahmnicore/drugOrders/prescribedAndActive` | Patient-wide orders grouped by visit. **Source of truth.** |
| `GET …/bahmnicore/drugOrders/active` | Currently active only. Live ABC200016: **0**. |
| Medications + Prescribe on the chart | Same orders. Write via `bahmniencounter` `drugOrders[]`. |
| Review bar “Current medications” | Same list, **Ordered** only (expired/stopped hidden). |
| Pharmacy | Dispenses those orders after payment. Does not own a separate history table. |
| CIEL Medication history `160741…` | 14-member obs set. **0** obs. Not on a form. |

Live ABC200016 `prescribedAndActive`: **3** Drug Orders, all on leftover visit `6478a94e-…`:

| Medicine | State |
|---|---|
| Cetirizine 10 mg | Active (not stopped) |
| Cetirizine 10 mg | Stopped |
| Paracetamol 500 mg — TEST | Auto-expired |

MySQL: **8** non-voided drug orders hospital-wide; **0** medication-history observations.

**Level:** Orders belong to an **encounter / visit**. The prescribedAndActive API already presents them as **patient history**.

**Display vs enter**

- **Display history:** reuse `prescribedAndActive` (including stopped / expired). That *is* medication history.
- **Display current:** keep the Review bar filter.
- **Enter:** Prescribe on the selected visit only.
- **Do not** open the CIEL medication-history obs set. That would duplicate Pharmacy / Clinical orders.

---

### 5. Family History

**Classification:** Clinical family-history concepts **EXISTS BUT NOT CONFIGURED**. Administrative relationships **MISSING**. **REQUIRES HOSPITAL DECISION**.

**Clinical family history** (Mother → Diabetes)

| Item | Live |
|---|---|
| Form | None |
| Concepts | `Family history comment` `160618…` (text). ConvSet `Patient's family history list` `160593…` (diagnosis, relative, dates, comment, …). Status answers: not taken / none / unknown. |
| Observations | **0** |
| Bahmni UI | No family-history observations tab. |

**Administrative relationship** (Next of kin → Brother)

| Item | Live |
|---|---|
| `relationship_type` | **0** rows |
| `relationship` | **0** rows |
| REST `/relationshiptype` | Empty |
| REST `/relationship?person=` | Empty for ABC200016 |
| Registration `relationshipTypeMap` | Seed names Doctor / Parent — **cannot work** with an empty type table |
| Person attributes | email, phone, local name only. **No next of kin.** |

These two are **not** the same. Neither is in use.

**Level:** Relationships would be **patient-level**. Family-history obs, if ever used, would be **encounter** groups unless the hospital treats them as persistent.

**Do not** build a custom family-history table. There is nothing to expose yet.

---

### 6. Social History

**Classification:** Named Social History **MISSING**. Smoking **EXISTS BUT NOT EXPOSED** (unused form field). Alcohol / occupation / living situation **EXISTS BUT NOT CONFIGURED** (isolated unused concepts). Bahmni “occupation” patient attribute **EXISTS BUT NOT CONFIGURED** (attribute type absent). **REQUIRES HOSPITAL DECISION**.

| Topic | Live | On a used form? | Obs | Person attribute? |
|---|---|---|---|---|
| Social history (named) | Not present. Patient-generated text `162143…` unused | No | **0** | No |
| Smoking | `Smoking status` `163201…`, 8 answers | Unused History and Examination only | **0** | No |
| Alcohol | `Alcohol use status` `159449…` (In the past / Currently / Never) | No | **0** | No |
| Substance | `Substance use` `160246…` | No | **0** | No |
| Occupation | Concept `1542…` — **0 coded answers**. Bahmni dashboard/visit.json list `occupation` | No | **0** | **Not** in `person_attribute_type` (only email/phone/local name) |
| Living situation | `Living situation (text)` `167224…` | No | **0** | No |
| Civil / marital | `Civil status` `1054…` | Registration-style; not a social-history form | — | No |

ABC200016 person attributes: email and phone only.

**Level:** Smoking/alcohol obs would be **encounter** if written. Occupation as a person attribute would be **patient-level** — that attribute does not exist here.

An isolated concept is not a hospital social-history workflow. Do not turn smoking on just because it sits on the unused Forms 2 file.

---

## Duplication Analysis

Populated from this installation. Not assumptions.

| Proposed section | Existing source on this stack | Same fact? | Duplicate if we add a form? | Recommended treatment |
|---|---|---|---|---|
| Examination | No used exam. HPI / Consultation Note / vitals are **not** exam | No | Inventing a schema, not duplicating | Keep **unavailable**. Hospital must choose exam fields first. |
| Review of Systems | Unused CIEL ConvSet. Not the same as HPI | No overlap with current chart | A checklist would be **new** data, easy to fake as all-Negative | Keep **unavailable**. Do not auto-Negative. |
| Past Medical History | **Known Diagnoses** = Bahmni visit diagnoses (`H/O: Malaria` on leftover Consultation). Conditions unused. CIEL PMH set unused | **Yes** for coded diseases | Entering Hypertension in both places would be two records of one fact | **Expose / link Known Diagnoses.** Do not add a PMH form. |
| Medication History | **Medications** + `prescribedAndActive` (3 orders on leftover visit). Pharmacy dispenses those orders. CIEL med-history set unused | **Yes** for prescribed drugs | A second list would fight Pharmacy / Prescribe | **Expose existing orders** (history = all; current = Ordered). No new form. |
| Family History | Unused CIEL sets. Empty relationship tables. Not next-of-kin | No existing clinical or admin data | A new table would invent both | Keep **unavailable**. Do not confuse with next of kin. |
| Social History | Unused smoking field on unused form. Isolated alcohol/occupation. No occupation attribute | Partial only as unused smoking | Turning smoking on is a new workflow, not reuse of hospital data | Keep **unavailable** until the hospital names the questions. |

**Already working — do not restyle as new sections**

| Chart area | Source | Level |
|---|---|---|
| Chief complaint / HPI / notes | Consultation obs on selected visit | Encounter / visit |
| Diagnosis | `bahmniDiagnoses` → Visit Diagnoses | Encounter; listed patient-wide |
| Orders / prescription | Lab / drug orders | Encounter / visit |
| Vitals | CIEL vital obs | Encounter |
| Current medications | Same drug orders, Ordered only | Patient-wide filter |
| Known diagnoses | Same diagnosis search | Patient-wide list |
| Attending doctor | Consultation `encounter_provider` | Encounter / visit |
| Consultation fee | `consultation:{visitUuid}` | Visit — unchanged |

---

## Recommended Hospital EMR Clinical UX

Principle: comprehensive record, small surface. Optional titles stay **collapsed by default**. Closed means **not documented**, never Negative / None / Normal.

Do **not** make six editable forms.

| Section | In Hospital EMR now | Next safe step | Eventually editable? | Level if ever written |
|---|---|---|---|---|
| Examination | Collapsed, unavailable copy | Leave unavailable | Only after the hospital picks a general exam (one note vs systems vs ortho-only). Do not reuse Consultation Note unless they say so. | Encounter / visit |
| Review of Systems | Collapsed, unavailable copy | Leave unavailable | Only if the hospital wants that CIEL checklist (or a shorter one). Never default Negative. | Encounter / visit |
| Past Medical History | Collapsed, points at Known Diagnoses | **Link / show existing diagnoses** — no new fields | No second entry form unless they want dates/“still present” beyond Visit Diagnoses | Display patient-wide; new diagnoses stay on the selected visit |
| Medication History | Collapsed, points at Medications | **Show existing `prescribedAndActive` history** (stopped/expired included) | Prescribe remains the only write path | Display patient-wide; new orders on selected visit |
| Family History | Collapsed, unavailable copy | Leave unavailable | Only after they decide clinical history vs next of kin, and configure types or a form | Relationships = patient; obs groups = encounter unless they say otherwise |
| Social History | Collapsed, unavailable copy | Leave unavailable | Only after they name smoking / alcohol / occupation / living, and whether those are encounter notes or person attributes | Smoking/alcohol = encounter; occupation attribute would be patient-level (not configured) |

**Keep using for entry (unchanged)**

Chief complaint, HPI, consultation notes, diagnosis, orders, prescription, vitals — always on `patientUuid` + **selected** `visitUuid`. Attending provider stays logged-in doctor → encounter provider. Fee unchanged.

**Do not implement those display links in this investigation.** The next implementation phase should start with reuse (diagnoses + medication orders), not new forms.

---

## Investigation verification (24 Aug 2026)

| Check | Result |
|---|---|
| Code / config / records changed | **None** |
| ABC200016 Known Diagnoses | `H/O: Malaria` on leftover Consultation / visit `6478a94e-…` |
| Conditions / allergies / relationships | **0** |
| Drug orders on that patient | 3 via prescribedAndActive; 0 currently active |
| Exam / ROS / PMH set / family / smoking / alcohol / occupation obs | **0** |
| Forms 2 ever filled | **No** |
| `npm test` / `npm run build` | **134 passed**. Build succeeded. Bundle unchanged (`index-CYsNwmI0.js`). No architecture change. |

---

## Bahmni Clinical Forms Exposed in Hospital EMR

Date: **24 Aug 2026**. Intent: expose Examination, Review of Systems, Family History, and Social History from Bahmni/OpenMRS — not from a new Hospital EMR record.

**STOP.** Nothing was configured or made writable. There is no configured general-OPD form to wrap.

This is not “ignore those areas.” It is: **do not invent a hospital form** when Bahmni has dictionary fragments and unused seed files, but no consultation template.

No OpenMRS configuration, concepts, Forms 2 files, observation-template members, patients, visits, or observations were changed.

---

### What “a Bahmni form” means on this stack

| Technology | Live |
|---|---|
| **Forms 1.0 / HTML Form Entry** | **Not used.** All 17 `form` rows have **0** `form_field`. `htmlxform` count **0**. |
| **Forms 2.0** | 17 published seed JSON files. Clinical `formGroup` / `formNames` are **empty**. **0** obs have `form_namespace_and_path`. Never filled. |
| **Observation templates (concept sets)** | Parent ConvSet **All Observation Templates** `d4739519-…` exists. **Members: 0.** Nothing is in “All Observation Templates.” |
| **Clinical consultation tabs** | `extension.json` names History and Examination, Vitals, Second Vitals, Obstetrics, Gynaecology, Discharge Summary. Those **concept sets are missing** (except a Discharge Summary *image* concept). |
| **Hospital EMR form renderer** | None. Complaint / HPI / notes already write **individual existing concepts** via `bahmniencounter`. That is not a Forms 2 engine. |

Hospital clinical workflow for these four areas is **not** Forms 1.0. Migrating the hospital onto Forms 2.0 was **not** done.

---

### Standard / disk templates (not installed)

On disk under `abikan-config/openmrs/templates/` (CSV). **Not loaded** as live concepts (`Detailed History and Examination` **NOT PRESENT**).

| Disk template | Relevance | Safe for general OPD? |
|---|---|---|
| Detailed History and Examination Intake / Progress | Family History (text), Alcohol Use, Smoker, Occupational History, **Past History**, socio-economic | **No.** Not loaded. Past History would **duplicate Known Diagnoses**. Importing would **create new concepts**. |
| COPD / CHD / CHF “Physical Examination” | Disease follow-up + vitals + free-text exam | **No.** Specialty / programme, not general OPD. |
| Generic “Family History” rows | Disease-template answers (asthma, early MI) | **No.** Not a family-history form. |

Do **not** import these blindly.

---

### Examination

| | |
|---|---|
| **Existing source** | None configured. Forms 2 **History and Examination** is complaint / HPI / smoking / media — **not** an exam. **Orthopaedic Examination** is three unused specialty text fields. |
| **Concepts in dictionary** | General / cardiac / chest / abdominal / MSK / skin **text** findings exist. Neurologic / HEENT / skin **coded** findings have **0 answers**. **Examination Notes** missing. |
| **Form technology** | No Forms 1.0. No observation-template member. Orthopaedic Forms 2 unused. |
| **Read / write** | **0** exam obs. Nothing to read. Writing would mean **choosing** which dictionary fields are “the OPD exam.” |
| **Visit / encounter** | If written, Consultation encounter on the **selected** visit. |
| **Required fields** | None (no form). Orthopaedic fields are not mandatory. |
| **UI** | Remains collapsed. Unavailable copy. |
| **Exposed?** | **No.** |

Could not safely expose: assembling those text concepts into a Hospital EMR sheet; embedding Orthopaedic as “the” exam; treating History and Examination Forms 2 as physical examination.

---

### Review of Systems

| | |
|---|---|
| **Existing source** | CIEL ConvSet `Review of systems` `159615…` (9 coded systems). **Not** in All Observation Templates. **Not** on any used form. |
| **Concepts** | General, HEENT, cardiopulmonary, GI, GU, MSK, CNS, developmental, obstetrical. Answers include symptoms **and Negative**. |
| **Form technology** | Dictionary ConvSet only. |
| **Read / write** | **0** obs. |
| **Visit / encounter** | Would be encounter-level if ever used. |
| **Required fields** | None. |
| **UI** | Collapsed. Closed ≠ Negative. |
| **Exposed?** | **No.** |

Could not safely expose: turning the unused ConvSet into a live checklist without a hospital decision (which systems, whether obstetric/developmental belong on every OPD visit). Auto-Negative is forbidden.

---

### Family History

| | |
|---|---|
| **Existing source** | Unused CIEL comment + `Patient's family history list` ConvSet. **Not** a form. **Not** in All Observation Templates. |
| **Concepts** | Comment, relative, diagnosis, dates, status (not taken / none / unknown). |
| **Relationships** | **0** types, **0** rows. That is next-of-kin / admin — **kept separate**, and also unused. |
| **Form technology** | None. |
| **Read / write** | **0** obs. |
| **Visit / encounter** | Obs groups would be encounter-level unless the hospital later treats them as persistent. Relationships would be patient-level. |
| **Required fields** | None. |
| **UI** | Collapsed. Unavailable. |
| **Exposed?** | **No.** |

Could not safely expose: a custom relative→disease table; Registration next-of-kin (does not exist).

---

### Social History

| | |
|---|---|
| **Existing source** | Smoking status on unused History and Examination Forms 2. Alcohol / occupation / living situation are isolated unused concepts. |
| **Concepts** | Smoking (8 answers, unused). Alcohol use status (Past / Current / Never), **0** obs. Occupation concept has **0 answers** and is **not** a person attribute. |
| **Form technology** | Smoking only, on a form Hospital EMR does not render and Clinical does not include. |
| **Read / write** | **0** social-history obs. |
| **Visit / encounter** | Smoking/alcohol would be encounter obs. Occupation as a person attribute would be patient-level — **not configured**. |
| **Required fields** | Smoking is not mandatory on that unused form. |
| **UI** | Collapsed. Unavailable. |
| **Exposed?** | **No.** |

Could not safely expose: smoking alone as “Social History”; occupation with no answers; isolated living-situation text.

---

### What was reused vs configured vs still unavailable

| Area | Reused | Configured this phase | Still unavailable |
|---|---|---|---|
| Examination | — | Nothing | Yes |
| Review of Systems | — | Nothing | Yes |
| Family History | — | Nothing | Yes |
| Social History | — | Nothing | Yes |
| Known Diagnoses | Already the past-diagnosis display | Unchanged | — |
| Medications | Already the medicine history | Unchanged | — |
| Complaint / HPI / notes / diagnosis / orders / Rx / vitals | Existing selected-visit path | Unchanged | — |

**Why STOP (not a workaround):** no appropriate configured Bahmni form; available concepts are incomplete or unused; All Observation Templates is empty; exposing them would require a **hospital clinical decision** (which fields, Forms 2 vs concept-set template, obstetric ROS on every OPD visit). Building a Hospital EMR field list would invent a second form engine. Importing disk “Detailed History” would create new concepts and a Past History that duplicates Known Diagnoses.

**Hospital decision still required before any write UI**

1. A general OPD examination: one note vs named systems vs ortho-only.  
2. Whether the CIEL ROS ConvSet is the hospital checklist.  
3. Clinical family history (obs) vs next of kin (relationships) — and then configure one.  
4. Which social questions (smoking / alcohol / occupation / living) and whether they are encounter notes or person attributes.

Until those exist as a **configured** Bahmni template (members of All Observation Templates and/or a Clinical `formGroup` form), Hospital EMR will not show those titles in the Doctor Workspace.

Selected visit, attending provider, fee, diagnoses, and medications were not changed. Reception and Accounts were not given documentation access.

---

## Doctor Workspace — unavailable sections hidden (24 Aug 2026)

The four unavailable areas are **hidden**, not collapsed:

- Examination
- Review of Systems
- Family History
- Social History

Doctors no longer see cards, “not configured” copy, or disabled placeholders for those titles. This is UI-only. The audit above still records why they cannot be exposed yet.

Past Medical History and Medication History titles are also not shown as empty cards. **Known Diagnoses** and **Medications** remain the working displays.

Unchanged: Chief Complaint, HPI, Consultation Notes, Known Diagnoses, Medications, Vitals, Diagnosis, Orders, Prescription, consultation fee, attending doctor, selected patient + visit, visit number, Previous Visits.

No OpenMRS, Bahmni, concepts, observations, visits, billing, or RBAC changes.

---

## Doctor Workspace — Redundancy and Field Guidance Audit

Date: **24 Aug 2026**. Live inspection: ABC200016 selected visit **#001 today** `2857db49-…`. No new patients, visits, encounters, invoices, charges, or payments. Unavailable sections (Examination, ROS, Family History, Social History, Past Medical History, Medication History) were **not** reintroduced.

### Distinctions that remain (not duplicates)

| Pair | Distinction |
|---|---|
| Chief complaint vs HPI vs Clinical notes | Complaint = today's presenting reason (coded + optional words + duration). HPI = narrative of that problem. Notes = other consultation content (plan, advice). Three OpenMRS concepts. |
| Known diagnoses vs Diagnosis | Known diagnoses = patient-wide Bahmni diagnosis search (safety glance). Diagnosis = add a diagnosis/impression **for this visit**. Same read API; different job. |
| Current medications vs Medications / Prescribe | Alert shows **active** orders only. Medications table shows all statuses. Prescribe writes **new** drug orders. |
| Orders vs Prescription | Orders = investigations (lab now; imaging not yet). Prescription = medicines. |
| Daily visit number vs Hospital number | **001** is today's queue number (visit attribute). **ABC200016** is the permanent hospital number. |
| Visit type vs Location | Type = General Outpatient / Follow-up / etc. Location = **OPD-1** (the visit's place). |
| Attending doctor vs Logged-in doctor | Attended by = Consultation encounter provider on **that visit**. Header user = who is signed in. Empty attending stays **—**. No self-select field. |
| Current visit vs Previous visits | Selected `visitUuid` is authoritative. Previous visits lists other visits; current row is marked **This visit**. |

### Source of truth

| Area | Source | Hospital EMR DB? |
|---|---|---|
| Patient | OpenMRS patient | No |
| Selected visit | OpenMRS visit (`patientUuid` + `visitUuid`) | No |
| Daily visit number | OpenMRS visit attribute **Daily Visit Number** | No |
| Visit type | OpenMRS visit type (staff label mapped) | No |
| Location (header) | OpenMRS **visit** location | No |
| Attending doctor | OpenMRS Consultation `encounter_provider` on that visit | No |
| Chief complaint / HPI / notes | OpenMRS observations (existing concepts) | No |
| Known diagnoses / Diagnosis list | `GET …/bahmnicore/diagnosis/search` | No |
| Medications | `prescribedAndActive` / drug orders | No |
| Vitals | OpenMRS vital observations (patient-level latest) | No |
| Orders | OpenMRS lab orders; radiology not orderable here | No |
| Consultation fee | Odoo charge keyed by visit | No |

### Redundancies found

1. **Sticky bar said “Visit” twice** — `Visit #001 · General Outpatient` and `Visit {date}`. The date is not a visit number. **Fixed:** one sticky line: number · type · date.
2. **Header labeled the date as “Visit”** next to the large **001**. **Fixed:** date is now **Visit date**. Number stays the large queue figure. Hospital number stays the MRN.
3. **Header “Location” used the logged-in session location**, not the visit location (other departments already prefer the visit). **Fixed:** Clinical header uses the **selected visit** location.
4. **Known diagnoses and the Diagnosis recorded list** show the same patient-wide diagnoses. **Kept** — glance vs working list when adding a new diagnosis.
5. **Current medications and the Medications table** overlap. **Kept** — alert is active-only; table includes stopped/expired and is where prescribing happens.
6. **Consultation description** lists the three fields that sit immediately below. **Left unchanged** — short section intro, not a second form.
7. **Orders** repeated “imaging cannot be ordered” in the section description and the footer. **Fixed:** footer now only says laboratory fees are paid at Accounts.
8. **Previous visits** said “This is not the history of present illness.” **Fixed:** shortened to “Earlier visits on this chart.”
9. **HPI field label “This visit”** sounded like visit selection. **Fixed:** label is **History**.
10. **“Clinical notes” + inner label “Consultation note”** said the same thing. **Fixed:** inner label is **Notes**.
11. **Vitals** description is patient-level (“this patient”) but the empty state said “this visit.” Latest pulse on today’s #001 was from **19 Aug**. **Fixed:** empty state is “No vitals recorded.” Description unchanged.

### Helper / placeholder text

| Field | Added or changed | Not added (already clear or would lecture) |
|---|---|---|
| Chief complaint | Helper: **Main reason for today's visit.** | Coded search and “own words” placeholders kept |
| HPI | Label **History**. Placeholder unchanged: “What happened, when it started, and how it has changed.” | No second paragraph |
| Clinical notes | Label **Notes**. Placeholder unchanged: “Plan, advice, or other notes for this consultation.” | — |
| Diagnosis | Section helper: **Record the diagnosis or impression for this visit.** | Search placeholder kept |
| Medications | **Medicines already on this chart. Prescribe new ones below.** | Prescribe field labels unchanged |
| Orders | Description kept. Footer trimmed | Lab search helper already on the order panel |
| Vitals, fee, attending, visit number | — | Doctors already know these |

Placeholders are UI only. They are not saved.

### Removed / changed UI

- Duplicate sticky “Visit {date}” span
- Header date no longer labeled “Visit”
- Session location no longer shown as this visit’s location
- Previous-visits defensive HPI sentence
- Repeated imaging sentence in the Orders footer
- “This visit” / “Consultation note” inner labels

### Intentionally unchanged

- Selected visit binding
- Daily visit number allocation
- Attending-doctor source (no “select yourself” field)
- Known diagnoses + Diagnosis both visible
- Medications table + Prescribe composer in one section
- Consultation fee / billing
- RBAC
- Hidden unavailable sections

### Unresolved (superseded)

Complaint / HPI / notes read-scope is fixed in **Clinical Observation Scope** below. Vitals remain patient-level latest by design.

Previous encounters remain a thin type+date list. Not a second chart.

---

## Clinical Observation Scope

Date: **24 Aug 2026**. Live ABC200016. No new patients, visits, invoices, charges, or payments. No clinical observations were written.

OpenMRS relationship used:

**Patient → Visit → Encounter → Observation**

`obs` has `encounter_id`. Encounter has `visit_id`. Observations do not store `visitUuid` themselves.

### Bug found

Opening today’s **Visit #001** `2857db49-c8fa-46d0-be38-2213f4cc54bc` showed Fever, HPI, and consultation notes that belong to leftover OPD visit `6478a94e-1657-4abe-9271-7cf92b821576` / Consultation `9a88a85d-…` (19 Aug 2026).

| Field | Shown on today’s #001 (wrong) | Actual observation | Encounter | Actual visit |
|---|---|---|---|---|
| Chief complaint | Fever · High fever at night | Group `cb5a7803-…` (coded `e4bc4a6b-…`) | `9a88a85d-…` Consultation | `6478a94e-…` leftover OPD |
| HPI | “Hospital EMR clinical pass 3: fever started…” | `3022d328-…` History of present illness `1390…` | same | same |
| Clinical notes | “Hospital EMR clinical pass 3 consultation note…” | `0a0d60c6-…` Consultation Note `d37294c5-…` | same | same |

**Why:** `GET /obs?patient=&concept=` then `latestObs()`. That is latest-patient-observation logic. Today’s #001 has **no** Consultation encounter and **no** those observations.

**Save risk before the fix:** the draft kept those observation UUIDs. Editing HPI on #001 could have updated the leftover visit’s HPI.

### Correct rule

Complaint, HPI, and notes are **encounter-specific** (and therefore visit-specific). Read them from encounters on the **selected visit**. If that visit has none, show an empty state. Do not substitute another visit.

### Retrieval rule after the fix

`GET /visit/{selectedVisitUuid}` with nested encounter obs. Map only if `visit.uuid` matches and `patient.uuid` matches. Latest obs **within that visit** if the visit has more than one Consultation.

Save still uses `bahmniencounter` with the **selected** `visitUuid`. New text on an empty visit creates **new** observations (no foreign UUIDs). Editing a visit that already has notes keeps that visit’s observation UUIDs.

### Scope table

| Area | Source | Scope | Retrieval rule |
|---|---|---|---|
| Chief Complaint | OpenMRS `Chief Complaint Record` `da47a35d-…` | Encounter / visit | Selected visit’s encounters only |
| HPI | OpenMRS `History of present illness` `1390…` | Encounter / visit | Selected visit’s encounters only |
| Clinical Notes | OpenMRS `Consultation Note` `d37294c5-…` | Encounter / visit | Selected visit’s encounters only |
| Vitals | OpenMRS vital concepts (e.g. Pulse `5087…`) | Encounter-stored; **display** latest patient | Patient-level latest. Description already says “this patient.” New vitals still save on the selected visit. |
| Known Diagnoses | Bahmni diagnosis search | Patient-wide history | Keep. ABC200016 `H/O: Malaria` is on leftover Consultation — correct as known history. |
| Diagnosis (new) | Bahmni diagnosis on Consultation | Selected visit / encounter | Write on selected visit. Do not invent a second list. |
| Medications / Current medications | `prescribedAndActive` | Patient-level active + chart history | Keep. New prescriptions save on the selected visit. |
| Orders | `bahmnicore/orders?patientUuid=` | Patient-level list | Keep. New lab orders already send selected `visitUuid`. |
| Prescription | Same drug-order write as Medications | Selected visit / encounter | Unchanged write path. |
| Provider | Consultation `encounter_provider` | Encounter on that visit | Unchanged. |
| Consultation Fee | Odoo `consultation:{visitUuid}` | Visit | Unchanged. |

### ABC200016 existing data (nothing created)

| Data | Today #001 `2857db49` | 23 Aug #001 `271181d6` | 23 Aug #002 `a70cbb56` | 23 Aug #003 `a3036eb0` | Older OPD `6478a94e` |
|---|---|---|---|---|---|
| Chief complaint | none | none | none | none | Fever · High fever at night · 3 days |
| HPI | none | none | none | none | Hospital EMR clinical pass 3… |
| Clinical notes | none | none | none | none | Hospital EMR clinical pass 3 consultation note… |
| Vitals | none on this visit | none | none | none | Pulse 78 on leftover Consultation |
| Diagnosis | none on this visit | none | none | none | Primary `H/O: Malaria` (also Known Diagnoses) |
| Orders | none | none | none | none | Malarial smear (LAB_RESULT) |
| Prescription | none on this visit | none | none | none | Existing drug orders on leftover visit |

### Verification

- Today’s #001: empty complaint / HPI / notes. Known diagnoses still `H/O: Malaria`. Latest vitals still Pulse 78 (patient-level). Fee still visit-keyed.
- Leftover visit `6478a94e-…`: still shows that visit’s Fever / HPI / notes.
- Switching visits reloads documentation (`loadClinical` depends on `selectedVisitUuid`). Draft resets first so another visit’s observation UUIDs are not kept.
- Header search still drops the previous patient’s visit from the hash.
- Live patient switch: ABC200016 Visit #001 → search ABC200017 → Hospital EMRRecv Phase2225617. No Fever, leftover HPI/notes, `H/O: Malaria`, Pulse 78, or ABC200016 identity. Route is patient-only until a visit is opened (`#/doctor/patient/{patientUuid}`).
- No OpenMRS model change. No Hospital EMR observation database.

### Tests / build

See `clinicalDocumentation.test.ts` (visit-scoped read / empty / no latest fallback / no cross-patient / save without foreign UUIDs) and `observationScope.test.ts`.
