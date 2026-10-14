# Clinical capabilities implementation

Date: **19 Aug 2026**. Pass 3: expose existing Bahmni/OpenMRS clinical capabilities in the Hospital EMR Consultation workspace. No new concepts, concept sets, or forms were created.

Related: `CLINICAL_HISTORY_EXAMINATION_INVESTIGATION.md`, `CLINICAL_WRITE_API.md`, `PRESCRIPTION_E2E_TEST.md`.

Product rule: use what this installation already provides. Present it in hospital language. Do not invent medical workflows.

---

## 1. Existing Bahmni/OpenMRS capabilities discovered

Confirmed live (not assumed from Bahmni default config names):

| Capability | Live source | Suitable to expose now |
|---|---|---|
| Chief complaint | Concept set **Chief Complaint Record** `da47a35d-5806-48b7-b467-e29902759491` with coded, text, duration, duration unit | Yes |
| History of present illness | Text concept **History of present illness** `1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Yes |
| Consultation note | Text concept **Consultation Note** `d37294c5-5e07-11ef-8f7c-0242ac120002` | Yes |
| Vitals | Individual CIEL numeric concepts already written by Hospital EMR | Already working |
| Diagnosis | `bahmniDiagnoses[]` on the Consultation encounter | Already working |
| Medications / prescribe | OpenMRS Drug Order via the same encounter POST | Already working |
| Allergies | `GET /openmrs/ws/rest/v1/patient/{uuid}/allergy` (0 rows live) | Read-only, already on Review |
| Visit / encounter timeline | Existing visit and encounter lists | Yes, renamed so it is not confused with HPI |
| Examination | No general examination concept or used form | Coming soon |
| Past medical / medication / family / social / ROS | CIEL sets exist in the dictionary, unused, not on the OPD form | Coming soon |
| Laboratory ordering | Hospital catalogue/prices not provided | Coming soon (read-only lists remain) |
| Radiology ordering | PACS unconfigured | Coming soon (read-only lists remain) |

The Forms 2 form named **History and Examination** `d60dd30a-229d-4645-9fc9-43d44dcefbd8` was **not** embedded. It contains chief complaint, HPI, smoking, images, and videos. It does **not** contain an examination section.

CIEL **Chief complaint** `5219AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` exists with **0** answers. It is not used.

---

## 2. Capabilities exposed in Hospital EMR

Consultation flow is now:

Review → Consultation → Vitals → Previous visits → Diagnose → Order → Prescribe → Admission

**Consultation** (new working section):

- Chief complaint (coded list already on this server, optional free text, optional duration)
- History of present illness
- Clinical notes (Consultation Note)
- Examination, past medical history, medication history, family history, social history, review of systems: **Coming soon**

Unchanged working areas: Review (including allergies), Vitals, Diagnosis, Medications / prescribe, Admit Patient, consultation fee create, laboratory and radiology **read** lists.

The old Assess “Coming soon” block that claimed documentation could not be saved has been replaced.

The old **History** nav item was the visit timeline. It is now **Previous visits**.

---

## 3. Concepts reused

| Hospital EMR label | Concept | UUID | Type |
|---|---|---|---|
| Coded complaint | Chief Complaint Coded | `9bb0795c-4ff0-0305-1990-000000000002` | Coded (58 answers, including **Other generic**) |
| Complaint in your own words | Chief complaint (text) | `160531AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text |
| Duration | Sign/symptom duration | `1731AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Numeric |
| Duration unit | Chief Complaint Duration | `9bb0795c-4ff0-0305-1990-000000000003` | Coded: Hours / Days / Weeks / Months / Years |
| Group | Chief Complaint Record | `da47a35d-5806-48b7-b467-e29902759491` | Set (N/A) |
| History of present illness | History of present illness | `1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text |
| Clinical notes | Consultation Note | `d37294c5-5e07-11ef-8f7c-0242ac120002` | Text |

Duration unit answers reused as they exist on this server:

| Unit | UUID |
|---|---|
| Hours | `1822AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` |
| Days | `1072AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` |
| Weeks | `1073AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` |
| Months | `1074AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` |
| Years | `1734AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` |

**Other generic** `9bb0795c-4ff0-0305-1990-000000000001` is the existing catch-all coded answer. Free text is required when it is selected. No extra complaint categories were invented.

---

## 4. Forms reused

None.

The published History and Examination Forms 2 form was inspected and left unused. Hospital EMR writes the same **concepts** that form would have used for complaint and HPI, as ordinary observations, not as a Forms 2 render.

---

## 5. Observations written

All documentation observations go in `observations[]` on:

`POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter`

Chief complaint is one **obs group**:

```
Chief Complaint Record
  Chief Complaint Coded          (concept uuid of the selected answer)
  Chief complaint (text)         (optional)
  Sign/symptom duration          (optional number)
  Chief Complaint Duration       (optional unit uuid)
```

HPI and Consultation Note are sibling text observations on the same encounter.

Vitals, diagnoses, and drug orders continue to use the existing payload fields. Empty `drugOrders: []` does not rewrite or discontinue existing prescriptions.

Read-back: `GET /openmrs/ws/rest/v1/obs?patient=&concept=` (same path Hospital EMR already uses for vitals).

---

## 6. Consultation encounter behaviour

- Encounter type remains **Consultation** `d34fe3ab-5e07-11ef-8f7c-0242ac120002`.
- If the open visit already has a Consultation encounter, Hospital EMR now sends that **`encounterUuid`** and the existing **`encounterDateTime`**.
- If none exists yet, `encounterUuid` is omitted and Bahmni’s 60-minute session matcher still applies.
- Visit-window guard is unchanged: if now is before `visit.startDatetime`, Hospital EMR does not POST, shows “Visit has not started yet…”, and keeps Save disabled.
- Payment is not required to save clinical information.

This stops a second Consultation encounter from being created when documentation is added to a visit that already has vitals, diagnosis, or a prescription.

---

## 7. Capabilities left Coming soon

| Section | Why |
|---|---|
| Examination | No general examination concept is configured. Orthopaedic Examination exists and is unused. Consultation Note is not reused as examination. |
| Past medical history | CIEL set exists, unused, not on the OPD form |
| Medication history | CIEL set exists, unused |
| Family history | Dictionary only |
| Social history | Smoking status exists on the unused Forms 2 form; not turned on here |
| Review of systems | CIEL convset exists, unused |
| Order laboratory test | Catalogue and prices not provided; billing untouched |
| Order radiology investigation | PACS unconfigured; billing untouched |
| Refer / Follow-up | Not disposition answers on this server |
| Allergy recording | Allergy **read** is already on Review. No new allergy form |

---

## 8. Permissions

Unchanged.

Doctor (`app:clinical` / `doctor.abikan`) can: open Clinical, view patients, document consultation, record supported observations, diagnose, prescribe, create the consultation fee, admit the patient.

Doctor cannot: pay, dispense, assign beds, edit tariffs, open Pharmacy administration, Accountant, Nursing administration, or Reception.

Nurse attempting `#/doctor` still sees “You do not have access to this department” and remains in Nursing.

No Pay / Cash / Bank / Payment / Receipt buttons were added to Clinical.

Admit Patient still does not offer ward, room, or bed.

---

## 9. Browser test

Account: `doctor.abikan` / `Admin123`.

Path: Sign in → Clinical → Today's Patients → search **ABC200016** → open consultation.

Entered and saved:

| Field | Value |
|---|---|
| Coded complaint | Fever (`140238AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`) |
| Free-text complaint | High fever at night |
| Duration | 3 Days |
| HPI | Hospital EMR clinical pass 3: fever started three days ago, worse at night. |
| Consultation note | Hospital EMR clinical pass 3 consultation note. Advise fluids and review. |
| Diagnosis | H/O: Malaria (existing diagnosis search) |
| Pulse | 78 (second save on the **same** encounter) |

POST `bahmniencounter` returned **HTTP 200**. Payload included `encounterUuid` `9a88a85d-a2db-4656-94bd-fb55c1b01688` (the existing E2E Consultation). `drugOrders` was `[]`.

OpenMRS GET read-back (not UI-only):

| Concept | Encounter | Value |
|---|---|---|
| History of present illness | `9a88a85d-…` | Hospital EMR clinical pass 3: fever started three days ago, worse at night. |
| Consultation Note | `9a88a85d-…` | Hospital EMR clinical pass 3 consultation note. Advise fluids and review. |
| Chief Complaint Record | `9a88a85d-…` | group; coded Fever; text High fever at night; duration 3 Days |
| Pulse | `9a88a85d-…` | 78 |

After reload, the Consultation section showed “On this chart” for Fever, HPI, and the note.

Also verified on the same screen:

- Paracetamol 500 mg — TEST still listed (ORD-7 not disturbed)
- Create consultation fee still present; no Pay / Cash / Bank / Receipt
- Admit Patient present; no ward / room / bed
- Laboratory and radiology order buttons still Coming soon
- Doctor menu is Clinical only (Dashboard, Today's Patients, My Patients soon, Patients)

Nurse isolation (same browser session before doctor login): `nurse.abikan` on `#/doctor` was denied.

---

## 10. npm tests

`npm test` in `abikan-shell`.

74 passed, including new `src/services/openmrs/clinicalDocumentation.test.ts` (observation mapping, Chief Complaint Record group shape, update-by-existing-uuid, Other generic validation, duration unit required).

Existing visit-window, prescription mapping, pharmacy, routing, and today's-patients tests remain green.

---

## 11. Build

`npm run build` succeeded (`tsc --noEmit && vite build`). Dist is what the proxy serves at `/abikan/`.

---

## 12. Data changed

One development test patient, already used for the isolated prescription E2E:

| | |
|---|---|
| Patient | ABIKAN E2E TEST PATIENT · MRN **ABC200016** |
| OpenMRS uuid | `f242364e-b70f-4fec-b29e-8ad4fbe147b5` |
| Visit | `6478a94e-1657-4abe-9271-7cf92b821576` (still the only visit, still open) |
| Encounter | **same** Consultation `9a88a85d-a2db-4656-94bd-fb55c1b01688` (datetime unchanged 2026-08-19 03:05:51) |

Added observations on that encounter only (complaint group, HPI, Consultation Note, Pulse 78, H/O: Malaria diagnosis). Visit encounter count remained **1**.

---

## 13. Data protected

| Record | Status |
|---|---|
| Drug Order **ORD-7** `5e744fe0-d516-4255-b45f-3e4209e11c45` | Unchanged, not voided |
| Odoo invoices / payments / pharmacy stock | Not touched |
| Beds / accommodation | Not touched |
| Laboratory / radiology billing | Not touched |
| Concepts / forms | None created |
| Other patients | Not written |

No Odoo changes were required.

---

## 14. Known limitations

1. Clearing a previously saved HPI or note in the UI does not void the old observation. The previous text remains until a new non-empty value is saved.
2. Diagnosis search returned **H/O: Malaria** among other hits. That is the existing terminology search, not a new diagnosis model.
3. `POST/GET …/bahmniencounter/find` remains HTTP 500 on this install. Encounter reuse uses the visit’s Consultation list and `GET …/bahmniencounter/{uuid}`.
4. Vitals “History” tab is still named History (latest vs previous vital readings). That is not HPI and is not the visit timeline.
5. Allergies are read-only. There is nothing to record on this database.
6. Smoking, images, and videos from the unused Forms 2 form were not turned on.

---

## 15. What the hospital can request later

If a doctor later says “I need X”, first check whether this Bahmni/OpenMRS already provides X.

Reasonable next requests, each a hospital decision:

1. **Examination** — a single free-text examination concept (would be **new**, because Examination Notes is missing), or enable Orthopaedic Examination only for that clinic.
2. Past medical / drug / family / social history, or review of systems, using the unused CIEL sets — only if the hospital wants those questions on every OPD visit.
3. Laboratory ordering once the test catalogue and prices are supplied.
4. Radiology ordering once PACS is configured.
5. Allergy recording (not only display).
6. Smoking status, consultation images, or videos from the existing Forms 2 form.
7. Voiding / replacing a chief complaint or note from Hospital EMR.

Until then, Hospital EMR should keep showing Coming soon rather than inventing a medical form.

---

*End of pass 3 implementation.*
