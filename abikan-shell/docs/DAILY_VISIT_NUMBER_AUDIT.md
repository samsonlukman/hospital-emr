# Daily visit number / Today's Patients audit

Date: **23 Aug 2026** (Africa/Lagos). **Investigation only.**

No code, configuration, OpenMRS, Odoo, Clinical, or Reception changes. No patients, visits, encounters, invoices, payments, or charges were created. No queue table, patient-number database, or visit type was added.

Related: `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`, `RECEPTION_CAPABILITY_AUDIT.md` §8 Queue, `CLINICAL_CONSULTATION_FEE_AUDIT.md` § Medical Officer vs Consultant, `CLINICAL_COMPLETE_CAPABILITY_AUDIT.md`.

Evidence: Hospital EMR source (`clinical_queue.py`, `registration_patient.py` `start_visit`, `visits.ts`, `DoctorWorkspace.tsx`, `clinicalEncounter.ts`, `ConsultationWorkspace.tsx`), read-only OpenMRS MySQL, and read-only REST (`/queue`, `/queueentry` → 404).

---

## Classification used

| Label | Meaning |
|---|---|
| **EXISTS AND WORKS** | Present and used on this stack |
| **EXISTS BUT NOT EXPOSED** | Present in OpenMRS/Bahmni or Hospital EMR source; staff do not see it |
| **EXISTS BUT NOT CONFIGURED** | Object exists; hospital values are empty, seed-only, or unused |
| **MISSING** | Not built on this installation |
| **REQUIRES HOSPITAL DECISION** | Policy, not a code gap alone |

The hospital's intended meaning, from the request, is:

**the sequential number of patients/visits registered for that hospital day**

That is **not** the hospital number (MRN), visit UUID, invoice number, encounter id, or a permanent patient number.

Example the hospital gave (one shared list, mixed visit types):

| Day | Number | Patient | Visit |
|---|---|---|---|
| 23 Aug 2026 | 001 | Fatima Abdullahi | General Outpatient |
| 23 Aug 2026 | 002 | Musa Ibrahim | General Outpatient |
| 23 Aug 2026 | 003 | John Doe | Follow-up |
| 24 Aug 2026 | 001 | … | … |

This audit treats that as the requirement to test against. It does **not** treat it as already implemented.

---

## 1. Existing OpenMRS / Bahmni visit numbering

### What a visit already stores

OpenMRS `visit` on this install has: `visit_id` (global autoincrement), `uuid`, `patient_id`, `visit_type_id`, `date_started`, `date_stopped`, `location_id`, creator/audit, voided. There is **no** daily-sequence column.

| Identifier | What it is | Daily visit number? | Status |
|---|---|---|---|
| Patient Identifier / MRN (`ABC200016`) | Permanent hospital number from idgen source **ABC** | **No. Must stay separate.** | **EXISTS AND WORKS** as MRN only |
| Visit UUID | Stable id of one visit | No | **EXISTS AND WORKS** as routing id |
| `visit_id` | Lifetime autoincrement (today's rows were 35–43) | No. Does not reset at midnight | **EXISTS AND WORKS** as internal id |
| Encounter `encounter_id` / UUID | One clinical event on a visit | No | **EXISTS AND WORKS** as encounter id |
| Visit start datetime | Clock time the visit was created | Day membership: yes. Sequence: no | **EXISTS AND WORKS** as timestamp |
| Visit type / location | OPD, Follow Up, IPD, EMERGENCY, … | No | **EXISTS AND WORKS** |
| Visit attribute **Visit Status** | Values seen: `OPD`, `IPD` (15 rows) | No | **EXISTS AND WORKS** as status text |
| Visit attribute **Admission Status** | Values seen: `Discharged` | No | **EXISTS AND WORKS** for IPD discharge |
| idgen source **ABC** | Next value **200019**, prefix `ABC` | No. This is the MRN generator | **EXISTS AND WORKS** for registration |
| Appointment `appointment_number` | All live rows are `0000` | No | **EXISTS BUT NOT CONFIGURED** |
| Dictionary concepts named “Visit number” / “Patient hospital visit number” | CIEL-style questions/tests | No observations stored (`0` obs) | **EXISTS BUT NOT CONFIGURED** |
| OpenMRS Queue module (`/queue`, `/queueentry`) | Waiting-room tickets | REST **404**. No queue tables | **MISSING** |

**Bahmni / OpenMRS does not already assign a daily visit number (001, 002, 003) on this installation.**

Things that look similar and must not be reused:

- **MRN** `ABC200016` / `ABC200017` — permanent patient identity.
- **Visit UUID** — not human-facing, not daily, not sequential.
- **Invoice / sale order** (`INV/2026/00028`, `S00029`) — money, not arrival order.
- **Encounter id** — created later, when a clinician saves, not when Reception starts the visit.
- **Appointment number** — unused (`0000`); appointments are not today's walk-in list.
- **Dictionary “Visit number”** — unused observations; even if filled, those concepts are not a hospital-day sequence.

### Visit attributes that exist

| Attribute type | Datatype | Live values | Daily number? |
|---|---|---|---|
| Visit Status | Free text | `OPD`, `IPD` | No |
| Admission Status | Free text | `Discharged` | No |

There is no visit attribute type for “today’s number”.

### Queue / waiting mechanisms

| Mechanism | Live result | Status |
|---|---|---|
| OpenMRS Queue / Queue Entry REST | 404 Unknown resource | **MISSING** |
| MySQL tables named `%queue%` | `event_records_queue`, `hl7_in_queue` only (integration, not patients) | **MISSING** as a clinic queue |
| Hospital EMR registration metadata `queueAvailable` | Hard-coded `False` | Documents that no queue API is wired |
| Appointment list as “waiting” | Staff accounts historically 403 on `/appointments`; Clinical no longer uses it | **EXISTS BUT NOT EXPOSED** |
| Pharmacy “queue” | Open prescriptions | Not a daily visit number |
| `PatientIdentityHeader.queueNumber` | Optional prop; **no caller passes it** | **EXISTS BUT NOT EXPOSED** (leftover from appointment-derived numbers, removed in the visit-queue work) |

**A hospital waiting-room queue module does not exist here.** Today's Patients is a filtered visit list, not a queue.

---

## 2. Existing Clinical Today's Patients

**EXISTS AND WORKS** as “outpatient visits that started today”. **MISSING** as a daily visit number.

```
Doctor workspace #/doctor  ( #/doctor/queue scrolls to the same table )
  → GET /openmrs/abikan-api/consultation/todays-patients
  → require_clinician
  → GET /openmrs/ws/rest/v1/visit?fromStartDate={Lagos yesterday}&includeInactive=true
  → keep visits whose startDatetime falls on the Africa/Lagos calendar day
  → keep visit types OPD, Special OPD, Follow Up only
  → sort by visitStart ascending
```

Implementation: `server/patient-account/clinical_queue.py` `build_todays_patients`. Frontend map: `todaysPatients.ts` → `DoctorWorkspace.tsx`.

### Answers required by this audit

| Question | Answer |
|---|---|
| Does it query today's OpenMRS visits? | **Yes.** Visit resource, not a queue table. `fromStartDate` is **yesterday** in Africa/Lagos so a visit just after midnight Lagos is not lost to UTC. Membership of “today” is decided in Python against Africa/Lagos. |
| Does it use encounters? | **No.** A visit appears as soon as it is created, before any Consultation encounter exists. |
| Does it use visit type? | **Yes.** Include: OPD, Special OPD, Follow Up. Exclude: IPD, EMERGENCY. |
| Does it use location? | **No.** Location is not a filter. OPD-1 vs Emergency does not decide membership; visit type does. |
| Does it already have an ordering/sequence? | **Sort only.** `visitStart` ascending. No stored rank, no `001` field. |
| Does Bahmni already assign a number that Hospital EMR is not displaying? | **No.** Visit payload has uuid, start/stop, type, patient, MRN. No daily number on the visit or in the Hospital EMR payload. |
| Can the current list calculate a daily number safely? | **Not safely as a stored hospital number.** It can compute a **display rank** (position in this filtered, sorted list). That rank is not concurrency-safe, is not shared with Reception’s fuller list, and can change if a visit is voided or if the include-set changes. |

Columns staff see today: Patient, MRN, Visit, Time, Status (Open / Ended), Open. No number column.

On **23 Aug 2026** (read-only MySQL, Africa/Lagos day), visits that started today:

| Start (UTC stored) | Type | Location | MRN | In Clinical Today's Patients? |
|---|---|---|---|---|
| 01:19:48 | OPD | OPD-1 | ABC200018 | Yes |
| 01:20:07 | Follow Up | OPD-1 | ABC200018 | Yes |
| 01:20:32 | Follow Up | OPD-1 | ABC200018 | Yes |
| 01:20:56 | IPD | Hawawu Maternity Ward | ABC200018 | **No** |
| 01:21:22 | IPD | Hawawu Maternity Ward | ABC200018 | **No** |
| 01:21:49 | OPD | OPD-1 | ABC200018 | Yes |
| 01:21:58 | EMERGENCY | Emergency | ABC200018 | **No** |
| 01:34:07 | Follow Up | OPD-1 | ABC200017 | Yes |
| 01:34:29 | EMERGENCY | Emergency | ABC200017 | **No** |

If Hospital EMR numbered **only** the Clinical list, today’s outpatient ranks would be 001–005. Reception’s “Today's patients” includes **all** visit types started today, so the same people would not share those ranks. One patient can also have **several** visits the same day (ABC200018 has six on 23 Aug). The hospital example shows one number per person-visit row, not one number per patient.

Clinical does **not** assign a doctor when the row appears. Opening the row calls `openConsultation(patientUuid)`. It does not start a visit or encounter.

---

## 3. Existing Reception Start Visit

**EXISTS AND WORKS.** The visit is created **immediately** in OpenMRS.

```
Reception patient → Start Visit
  → POST /openmrs/abikan-api/registration/patient/{uuid}/visit
  → require_registrar
  → POST /openmrs/ws/rest/v1/visit
       { patient, visitType, location, startDatetime: now UTC }
  → return { uuid, visitType, visitTypeLabel, location, locationUuid, startDatetime, open: true }
```

Implementation: `registration_patient.py` `start_visit`.

| Question | Answer | Status |
|---|---|---|
| Is the visit created immediately? | Yes. OpenMRS returns a visit uuid before Hospital EMR responds. | **EXISTS AND WORKS** |
| Does the create response contain a daily number? | **No.** Uuid, type, location, start time only. | **MISSING** |
| Does OpenMRS generate a visit sequence? | **No.** Only `visit_id` + uuid. `visit_id` is lifetime, not daily. | **MISSING** |
| Can start time determine the hospital day? | **Yes**, if converted to Africa/Lagos (Clinical already does this). Browser-local `todayDateString()` on Reception is a weaker rule. | Day: **EXISTS AND WORKS** on Clinical. Reception list: **EXISTS BUT** uses the workstation calendar date as `fromStartDate` |
| Can two visits start in the same second? | **Yes.** Live data: **four** visits share `2026-08-21 21:56:16`. Today's starts are 1–2 seconds apart under single-user testing. | Concurrency risk is real |
| Could two patients get the same calculated number? | **Yes**, if Hospital EMR ranks by start time only and two rows share a timestamp, or if Reception and Clinical use different include-sets. | Do **not** implement a client-side counter |

Reception dashboard “Today's patients” (`fetchTodaysVisits` in `visits.ts`):

- Source: `GET /visit?fromStartDate={browser today}&includeInactive=true`
- **All** visit types
- Shows hospital number, visit label, time, Active/Ended
- **No** daily number
- “Waiting / Active Visits” = open visits that started in that query, not a ticket queue

That list and Clinical Today's Patients are **not the same set**. A derived 001 on one screen would not match the other without a shared rule.

---

## 4. Does Bahmni already provide a daily visit number?

**MISSING.**

Searched: visit columns, visit attributes, idgen sources, patient identifier types, encounter ids, appointment numbers, CIEL “Visit number” concepts, Queue module, Bahmni registration metadata, Hospital EMR Clinical payload.

Nothing on this stack stores or returns `001` / `002` for “today’s visit”.

Bahmni Registration numbering that **does** exist is the **hospital number** (idgen ABC). That must remain `ABC200016`, never be shown as today’s visit number.

---

## 5. Does a queue already exist?

**MISSING** as a waiting-room / ticket module.

**EXISTS AND WORKS** as the intended staff workflow, if “queue” only means:

```
Reception starts today's visit
  → visit appears on Today's Patients (Clinical: outpatient types; Reception: all types)
  → doctor signs in
  → doctor opens the patient they are attending
  → consultation is saved under the logged-in provider
```

That workflow already works **without** a daily number and **without** Reception assigning a doctor.

Do **not** build a separate queue to satisfy this requirement. The missing piece is a **stable daily visit number**, not a second patient list.

If the hospital later wants call-next / skip / room assignment, that would be a new product decision. It is not required for “001 — Fatima — General Outpatient”.

---

## 6. How the attending provider is recorded

**EXISTS AND WORKS.** Unchanged since the previous Clinical audit.

```
Doctor saves consultation or prescription
  → fetchProviderUuidForUser(session userUuid)
  → GET /openmrs/ws/rest/v1/provider?user={userUuid}
  → saveConsultation → Bahmni encounter
       providers: [{ uuid: providerUuid }]
```

Source: `clinicalEncounter.ts` `fetchProviderUuidForUser` + `buildConsultationPayload`; `ConsultationWorkspace.tsx` `handleSave` / `handlePrescribe`.

Live MySQL: all **14** Consultation encounters have an `encounter_provider`. Providers seen: **Clinical Doctor** (4), **Hospital EMR Development Admin** (10). Reception Start Visit does **not** write a provider on the visit.

Implications for the intended doctor workflow:

| Step | Already true? |
|---|---|
| Reception creates today's visit | Yes |
| Patient receives today's visit number | **No** — number does not exist |
| Doctor sees today's patients | Yes (outpatient types) |
| Doctor selects the patient | Yes — Open on the row |
| Logged-in provider recorded as attending | **Yes**, when Consultation is saved — not at list time |
| Consultation recorded | Yes |
| Consultation fee created | Yes (separate Clinical fee card → Odoo) |

Do **not** add a Reception doctor picker for this phase. The attending doctor is the signed-in clinician at save time.

---

## 7. How provider identity appears in patient history

OpenMRS already stores enough to show an attending clinician **after** a Consultation encounter exists:

| Fact | Stored where | Hospital EMR “Previous visits” shows it? | Status |
|---|---|---|---|
| Visit date | `visit.date_started` | Yes (`startDate`) | **EXISTS AND WORKS** |
| Visit type | `visit_type.name` | Yes | **EXISTS AND WORKS** |
| Location | `location.name` | Yes | **EXISTS AND WORKS** |
| Open / closed | `date_stopped` | Yes (“Open”) | **EXISTS AND WORKS** |
| Encounter type + date | `encounter` | Yes (“Previous encounters”: `date · type`) | **EXISTS AND WORKS** |
| Attending provider | `encounter_provider` on Consultation | **No** | **EXISTS BUT NOT EXPOSED** |
| Consultation note / obs | encounter observations | Not on this timeline (hint says note text is unavailable here) | **EXISTS BUT NOT EXPOSED** on the list |
| Consultation fee / payment | Odoo sale/invoice keyed by visit | Fee card on the current chart only; not on Previous visits | **EXISTS BUT NOT EXPOSED** on history |
| Service / clinic name | Appointment speciality/service (seed General Medicine, ENT) | No | **EXISTS BUT NOT CONFIGURED** for this hospital |
| Daily visit number | — | — | **MISSING** |

`fetchPatientVisits` requests `uuid, startDatetime, stopDatetime, visitType, location` only. `fetchPatientEncounters` requests `uuid, encounterDatetime, encounterType` only. Neither asks for providers.

Do **not** create a new history table. The gap is display (and later, a stored daily number on the visit), not a missing medical record.

---

## 8. One shared daily sequence — is it feasible?

**Technically feasible.** OpenMRS has no conflicting daily-number convention on this install.

The hospital example mixes General Outpatient and Follow-up in **one** 001, 002, 003 list. That matches “one hospital-wide sequence for the day”, not “001 per visit type”.

What this stack does **today** is different:

| List | Types included | Would share one 001… list? |
|---|---|---|
| Hospital example | GOPD + Follow-up (Emergency / Admission not shown in the example) | One sequence |
| Clinical Today's Patients | OPD + Special OPD + Follow Up | Same idea, **excluding** Emergency and Admission |
| Reception Today's patients | **All** types started today | Wider than Clinical |
| OpenMRS visit types live | OPD, Follow Up, IPD, EMERGENCY, Special OPD | No numbering |

**REQUIRES HOSPITAL DECISION:**

1. **One shared sequence for every visit started that day** (OPD, Follow-up, Emergency, Admission), or
2. **One sequence for outpatient clinic visits only** (the current Clinical include-set), with Emergency / Admission unnumbered or numbered separately.

Do not guess. The example supports (1) for OPD + Follow-up and is silent on Emergency / Admission. Clinical already excludes those two by product rule.

Also decide:

3. **One number per visit**, even if the same patient appears twice (today’s TEST data does this), or **one number per patient per day**.
4. Whether Special OPD (retrospective entry) should receive a number. It is in the Clinical list but must not be used as “Consultant”.

A shared sequence is feasible **only if** Reception and Clinical use the **same include-set and the same assignment rule**. Display-rank on two different lists will disagree.

---

## 9. Daily number options (do not implement)

### A. Existing Bahmni / OpenMRS daily number

| | |
|---|---|
| Source of truth | None found |
| Concurrency | — |
| Survives refresh | — |
| Stable | — |
| Resets daily | — |
| Works across Reception and Clinical | — |
| Database changes | None — there is nothing to display |
| Verdict | **MISSING.** Cannot reuse. |

### B. Derive a display number from existing visit ordering

Compute `001` = first visit of the hospital day by `date_started` (and a tie-break), among a chosen type set.

| | |
|---|---|
| Source of truth | OpenMRS visits; number is computed at read time |
| Concurrency safety | **Weak.** Same-second starts already exist. Two counters in two browsers can invent the same rank. Rank by time after the fact can still collide without a deterministic tie-break (`visit_id` or uuid). |
| Survives refresh | Yes, **if** the include-set and sort stay fixed and no earlier visit is voided or created with an earlier start |
| Stable | **No** if an earlier visit is voided, back-dated, or inserted. A patient who was 003 can become 002. |
| Resets daily | Yes, because the filter is “started on this Lagos date” |
| Works across Reception and Clinical | **Only if both lists use the same visits.** They do not today. |
| Database changes | None |
| Verdict | Acceptable only as a **temporary display rank** on one agreed list. Not safe as a number staff write on paper or call in the waiting room. |

### C. Create a new daily visit sequence

Assign `001` once, at Start Visit, persist it on that visit (for example a new visit attribute, or a Hospital EMR table — **not recommended** if a visit attribute can hold it), increment with a real lock/transaction for that hospital date.

| | |
|---|---|
| Source of truth | The number stored on the visit |
| Concurrency safety | **Yes**, if assignment is server-side and atomic for `(hospital_date, sequence)` |
| Survives refresh | Yes |
| Stable | Yes for that visit. Voiding a visit leaves a gap (usual and honest) or requires a hospital rule |
| Resets daily | Yes, if the key is the Africa/Lagos date |
| Works across Reception and Clinical | Yes, both read the same stored value |
| Database changes | Yes — at least a visit attribute type (OpenMRS) **or** a Hospital EMR table. The hospital asked us **not** to create a new patient-number database. A visit attribute on the existing visit is the smallest OpenMRS-shaped option; it is still a change and was **not** done here. |
| Verdict | This is the only option that matches “the number identifies that day’s visit” under concurrent Reception use. **Do not implement until the hospital answers §11.** |

**Do not** implement a browser `let n = visits.length + 1` generator.

---

## 10. Recommended architecture

Recommended **after** the hospital decisions in §11, not now:

1. Keep OpenMRS **visits** as the only patient-for-today list. Do not add a queue module or a second patient store.
2. Keep **MRN** and **today’s visit number** as different fields everywhere staff can see them.
3. Assign the daily number **once**, on the server, when Reception (or Clinical start-OPD) creates the visit. Persist it on that visit.
4. Show the same number on Reception Today's patients, Clinical Today's Patients, and later on the chart header / history.
5. Use Africa/Lagos midnight as the reset.
6. Keep attending doctor as the **logged-in provider on Consultation save**. Do not assign doctors at Reception for this workflow.
7. Align Clinical and Reception “today” membership with the hospital’s sequence rule (all visits vs outpatient only). Until then, do not print a number from one list and expect the other desk to match.

Until those decisions exist, the honest staff UI is the current list: name, hospital number, visit type, time. Inventing 001 from sort order would look like a hospital number and would be wrong under concurrency.

---

## 11. What should NOT be built

- A queue table, queue module, or ticket-call system
- A new patient-number / MRN database
- A new visit type for “daily number”
- Using `ABC200016` (or any MRN) as today’s number
- Using visit UUID, `visit_id`, encounter id, or invoice number as today’s number
- A client-side incrementer
- Reception assignment of a doctor as a substitute for the number
- A new patient history table
- Changing Clinical Today's Patients filters “just so the numbers look sequential” without a hospital rule
- OpenMRS core modifications
- Dummy KPI counters for “queue position”

---

## 12. Hospital decisions still required

| # | Decision | Why it blocks implementation |
|---|---|---|
| 1 | Confirm the number means **today’s visit sequence**, not MRN / invoice / encounter | Avoids building the wrong identifier |
| 2 | **One shared sequence** for all visit types, or **outpatient only** (OPD / Follow-up / Special OPD) | Reception and Clinical lists disagree today |
| 3 | Emergency and Admission in that sequence or not | Clinical excludes them; Reception includes them |
| 4 | **One number per visit** vs **one per patient per day** | Same patient can have several visits today |
| 5 | Accept **display-rank (option B)** for a first UI, or require a **stored number (option C)** before staff use it on paper | Concurrency and stability |
| 6 | What to do if a visit is started in error and voided — gap vs reuse | Only matters for option C |

---

## 13. Testing

Investigation only. No data or code changes. JavaScript bundle hash unchanged (`index-CAyopUBh.js`).

| Command | Result |
|---|---|
| `npm test` | **103** passed, 0 failed |
| `npm run build` | Pass. `tsc --noEmit && vite build`. Bundle `index-CAyopUBh.js` |

---

## Findings index

| Finding | Classification |
|---|---|
| OpenMRS visit create (uuid, type, location, start) | **EXISTS AND WORKS** |
| Clinical Today's Patients from today's visits | **EXISTS AND WORKS** |
| Reception Start Visit immediate create | **EXISTS AND WORKS** |
| Attending provider on Consultation save | **EXISTS AND WORKS** |
| Previous visits date / type / location | **EXISTS AND WORKS** |
| Hospital number (MRN) via idgen ABC | **EXISTS AND WORKS** — must stay separate |
| Visit Status / Admission Status attributes | **EXISTS AND WORKS** — not a daily number |
| Encounter provider in history UI | **EXISTS BUT NOT EXPOSED** |
| Fee / payment on visit history | **EXISTS BUT NOT EXPOSED** |
| `queueNumber` header slot | **EXISTS AND WORKS** — shows today's visit number when present |
| Dictionary “Visit number” concepts | **EXISTS BUT NOT CONFIGURED** |
| Appointment number | **EXISTS BUT NOT CONFIGURED** |
| OpenMRS Queue module | **MISSING** |
| Bahmni daily visit number 001 / 002 / 003 | **EXISTS AND WORKS** — visit attribute, assigned at Reception Start Visit |
| Daily number on Start Visit response | **EXISTS AND WORKS** |
| Safe derived number across both desks | Not used. Stored number is the source of truth |
| Sequence scope (all types vs outpatient) | **DECIDED** — one shared sequence for all visit types |
| Stored sequence vs display rank | **DECIDED** — stored number, assigned at Start Visit |

---

## Daily Visit Number — Implementation

Date: **23 Aug 2026** (Africa/Lagos).

### Business rule

Every visit created by **Reception Start Visit** receives a sequential daily visit number.

- Separate from the hospital number (`ABC200016`), invoice numbers, encounter ids, and visit UUIDs.
- Resets to **001** at Africa/Lagos midnight.
- **One shared sequence** for General Outpatient, Follow-up, Emergency, and Admission.
- Assigned **once** when the visit is created. Not calculated from Today's Patients. Not entered by staff.
- Same patient, two visits the same day → two numbers.
- Clinical still excludes Emergency and Admission from Today's Patients. Those visits keep their hospital-wide number; the Clinical list may show `001`, `003`, `005`.

### Storage mechanism

**EXISTS AND WORKS.** OpenMRS visit attribute on the existing visit. No Hospital EMR table, no queue, no second visit store.

| Item | Value |
|---|---|
| Attribute type name | `Daily Visit Number` |
| UUID | `b7e4c1a0-5d21-4f8a-9c3e-2a1f0e8d7c6b` |
| Datatype | Free text (`001`, `002`, …) |
| Created how | Existing `visit_attribute_type` row, ensured via admin REST on first use |

Staff never see the attribute name. Historical visits without the attribute display **—**. They were not back-filled.

### Sequence generation

`next = max(stored Daily Visit Number values for the Africa/Lagos day) + 1`

This is **not** `COUNT(today's visits) + 1`. Unnumbered older visits do not consume the sequence.

Implementation: `server/patient-account/daily_visit_number.py`, called from existing `POST /openmrs/abikan-api/registration/patient/{uuid}/visit`.

### Atomicity / concurrency

- Process lock (`ALLOCATE_LOCK`) around “read today's stored numbers → create visit with attribute → confirm the value is on the visit”.
- One `abikan-api` process (ThreadingHTTPServer), same lock pattern as registration/consultation charges.
- Two concurrent Reception starts receive distinct numbers (unit test: 12 threads, 12 unique values).
- Client-supplied `dailyVisitNumber` / `visitNumber` is ignored.
- There is no API to edit the number after assignment. Doctor and Accountant Start Visit are **403**.

`requestId` on Start Visit (same pattern as registration fees): a retry with the same id returns the original visit and number. A new click generates a new id and a new visit.

### Timezone

Africa/Lagos via existing `clinical_queue.hospital_today`. A visit at 23 Aug 23:59 Lagos is 23 Aug. A visit at 24 Aug 00:00 Lagos is 24 Aug.

### Reception display

After a successful Start Visit:

- Title: **Visit successfully created.**
- Body: **Visit number: 001** (omitted if assignment failed).

Today's patients table: **No.** | Patient | Hospital number | Visit | …  
Sorted by the stored number. Missing numbers sort last as **—**.

The patient header shows the current visit's number when one exists (e.g. **003** next to hospital number **ABC200016**).

### Clinical display

Today's Patients includes the stored `dailyVisitNumber`. Sort is by that stored value. Include/exclude rules are unchanged (OPD, Special OPD, Follow Up only). The list is not renumbered.

### Patient-history display

Previous visits shows date, **Visit #001** or **—**, visit type, location, time. Attending provider is still recorded on Consultation save (`fetchProviderUuidForUser` → `providers: [{ uuid }]`). That mechanism was not changed. Provider name is still not on this timeline (**EXISTS BUT NOT EXPOSED**).

Clinical start-OPD and Special OPD retrospective paths were not altered. They receive a number only if they go through Reception Start Visit.

### Existing visits

Unnumbered. Display **—**. Not rewritten.

### Multiple visits, same patient

Each Start Visit gets the next number. Live: ABC200016 received **001**, **002**, **003** on 23 Aug.

### Test data created (TEST patients only)

No ORD-7, ordinary patients, lab, pharmacy, or paid invoices were touched.

| Number | Hospital number | Visit | Visit uuid | Notes |
|---|---|---|---|---|
| 001 | ABC200016 | OPD | `271181d6-b121-4f96-b795-ff5e49f370d5` | First assigned number today |
| 002 | ABC200016 | OPD | `a70cbb56-88f2-43bd-afa8-463e61c220e7` | Same patient, second visit |
| 003 | ABC200016 | Follow Up | `a3036eb0-d775-46d4-a59f-9f106148d08f` | Same patient, third visit |
| 004 | ABC200017 | Emergency | `41ee2b96-2d60-45b3-b203-97d4761ac4eb` | Hospital-wide sequence; **not** on Clinical list |
| 005 | ABC200017 | Follow Up | `035e53fa-bc1f-4ab6-ae5c-2237fbaf10ef` | **200** after persist-before-return fix; retry same `requestId` returned this visit again |

Client body `dailyVisitNumber: "999"` on the 005 create was ignored.

Clinical Today's Patients after 005: **001, 002, 003, 005** then **—** for older unnumbered outpatient visits. **004** Emergency correctly absent.

Browser: Reception list 001–005 then —; refresh unchanged; ABC200016 header **003**; Clinical list same stored numbers with the Emergency gap.

Day-boundary 001 on 24 Aug was not live-tested (system clock not changed). Covered by unit test (`23:59` Lagos vs `00:00` Lagos).

### What was not built

- Queue module / queue table
- Hospital EMR patient-number or visit database
- New visit types
- Historical back-fill
- Editable number
- Reception doctor assignment

### npm test / npm build

| Command | Result |
|---|---|
| `python3 -m unittest daily_visit_number_test.py` | **14** passed |
| `npm test` | **110** passed, 0 failed |
| `npm run build` | Pass. Bundle `index-DF9V4cR8.js` |
