# Clinical Today's Patients / attending doctor workflow audit

Date: **23 Aug 2026** (Africa/Lagos). **Investigation only.**

No Clinical, Reception, OpenMRS, or Odoo code was changed. No queue, provider table, specialty table, patients, visits, invoices, charges, or payments were created.

Related: `DAILY_VISIT_NUMBER_AUDIT.md`, `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`, `CLINICAL_CONSULTATION_FEE_AUDIT.md` § Medical Officer vs Consultant, `RECEPTION_CAPABILITY_AUDIT.md` §8 Queue.

Evidence: current Hospital EMR source plus read-only live REST/MySQL against existing TEST visits from the daily-number work.

---

## Classification used

| Label | Meaning |
|---|---|
| **EXISTS AND WORKS** | Present and used on this stack |
| **EXISTS BUT NOT EXPOSED** | Stored in OpenMRS/Odoo; Hospital EMR does not show or use it |
| **EXISTS BUT NOT CONFIGURED** | Object exists; hospital values are seed-only or empty |
| **MISSING** | Not built |
| **REQUIRES HOSPITAL DECISION** | Policy, not a code gap alone |

---

## Executive finding

Reception already creates the visit and assigns a daily number. Clinical already lists today's outpatient visits with that number. The doctor already becomes the attending clinician **when they save a Consultation encounter**.

The gap is **visit identity after Open**.

Today's Patients knows `visitUuid` (row `id` is the visit). **Open discards it** and navigates to `#/doctor/patient/{patientUuid}` only. The chart then binds to the **first open visit** returned by `GET /visit?patient=`. For ABC200016 that is **#003 Follow-up**, even if the doctor clicked **#001**.

Patient UUID alone is **not** enough. A patient can have several open visits the same day.

---

## 1. Current Today's Patients source

**EXISTS AND WORKS.**

```
Clinical #/doctor  ( #/doctor/queue scrolls to the same table )
  → GET /openmrs/abikan-api/consultation/todays-patients
  → require_clinician  (privilege app:clinical)
  → GET /openmrs/ws/rest/v1/visit?fromStartDate={Lagos yesterday}&includeInactive=true
  → keep visits whose startDatetime is the Africa/Lagos calendar day
  → keep visit types OPD, Special OPD, Follow Up
  → read Daily Visit Number from the visit attribute
  → sort by stored daily number (unnumbered last)
```

Implementation: `clinical_queue.py` `build_todays_patients`. Frontend: `doctorQueue.ts` → `todaysPatients.ts` → `DoctorWorkspace.tsx`.

It queries **OpenMRS visits**, not encounters, not appointments, not a queue table.

| Question | Live answer |
|---|---|
| Which API? | `GET /openmrs/abikan-api/consultation/todays-patients` |
| What records? | Visit rows started today (Africa/Lagos), outpatient types only |
| How is today determined? | Server `hospital_today()` in Africa/Lagos. `fromStartDate` is **yesterday** so a visit just after midnight Lagos is not lost to UTC |
| Included types | OPD, Special OPD, Follow Up |
| Excluded types | IPD, EMERGENCY (unchanged this phase) |
| Daily number | Stored visit attribute `Daily Visit Number`. Not recalculated |
| Sort | Stored number ascending. Missing numbers (`—`) last. Same missing key is a tie — load order |
| Same start time | **001 / 002 / 003** all display **04:16**. The number distinguishes the rows. Start time does not |
| Auto-update after Reception? | **No.** The list loads once on mount. No poll. The doctor must open Clinical again or refresh |
| Can the doctor distinguish by number? | **On the list, yes.** No., name, hospital number, visit type, time, Open/Ended are shown |

Live **23 Aug 2026** (`doctor.abikan`, 9 rows):

| No. | Hospital number | Visit | Time | Status | Visit uuid (first 8) |
|---|---|---|---|---|---|
| 001 | ABC200016 | OPD | 04:16 | Open | `271181d6` |
| 002 | ABC200016 | OPD | 04:16 | Open | `a70cbb56` |
| 003 | ABC200016 | Follow Up | 04:16 | Open | `a3036eb0` |
| 005 | ABC200017 | Follow Up | 04:17 | Open | `035e53fa` |
| — | ABC200017 | Follow Up | 02:34 | Open | `028691fa` |
| — | ABC200018 | OPD / Follow Up ×4 | 02:19–02:21 | Open | … |

**004** ABC200017 Emergency is hospital-wide numbered and correctly **absent** from this list.

---

## 2. How the doctor selects a patient

**EXISTS AND WORKS** as “open this patient.” **MISSING** as “open this visit.”

```
Today's Patients row
  → Open  → openConsultation(row.patientUuid)
  → #/doctor/patient/{patientUuid}
  → ConsultationWorkspace(patientUuid)
  → fetchPatientVisits(patientUuid)
  → openVisit = visits.find(visit => visit.open)   // first open in REST order
```

`row.visitUuid` is mapped and used only as the React row key. It is **not** put in the hash and **not** passed into the chart.

Header search uses the same `openConsultation(patientUuid)`.

| Question | Answer | Status |
|---|---|---|
| How does the doctor open a patient? | **Open** on the row (or header search) | **EXISTS AND WORKS** |
| Correct patient? | Yes. Hash is that patient's uuid | **EXISTS AND WORKS** |
| Selected visit preserved? | **No.** Hash has no visit uuid | **MISSING** |
| Working against the correct visit? | Only if the first open visit happens to be the one they clicked | Ambiguous |
| Multiple visits same patient distinguishable on the list? | Yes — daily number + visit type | **EXISTS AND WORKS** |
| Number visible when selecting? | Yes, in the **No.** column. Header after open shows the **bound** visit's number, not the clicked row | Partial |
| Can Clinical handle two visits the same day? | List: yes. Chart: **no visit picker**; one “current” open visit | **MISSING** visit selection |

Live `GET /visit?patient={ABC200016}` order (newest first):

1. **#003** Follow Up `a3036eb0-…` **OPEN** ← `visits.find(open)` binds here
2. **#002** OPD `a70cbb56-…` OPEN
3. **#001** OPD `271181d6-…` OPEN
4. Older leftover open visits (19–21 Aug), unnumbered

Clicking **#001** still opens the patient and binds consultation, fee, admit, and header number to **#003**.

Refreshing `#/doctor/patient/{uuid}` does not “switch” visits because no visit was selected. It re-picks the first open visit again (**#003** today).

---

## 3. Attending provider

**EXISTS AND WORKS.** Unchanged. Not on the visit. On the Consultation **encounter**.

```
doctor.abikan signs in
  → session user uuid 8e24b990-e90d-4bb3-8c3e-13eabbb7f9ae
  → GET /provider?user={userUuid}
  → provider 17dec510-ef20-4282-9d9e-4d33d4693675  “Clinical Doctor”
  → saveConsultation
  → POST /bahmnicore/bahmniencounter
       providers: [{ uuid: providerUuid }]
       visitUuid: openVisit.uuid
       encounterTypeUuid: Consultation (d34fe3ab-…)
```

Source: `clinicalEncounter.ts` `fetchProviderUuidForUser` + `buildConsultationPayload`. Called from `ConsultationWorkspace` save / prescribe.

| Question | Live answer | Status |
|---|---|---|
| Where stored? | `encounter_provider` on the Consultation encounter | **EXISTS AND WORKS** |
| Reliably on the encounter? | All **3** Consultation encounters for ABC200016 have a provider | **EXISTS AND WORKS** |
| On the visit itself? | **No** | Not used |
| Can history retrieve it? | Yes from OpenMRS. Hospital EMR encounter fetch does **not** request providers | **EXISTS BUT NOT EXPOSED** |
| Two doctors, two visits, same patient, same day? | OpenMRS can store different `encounter_provider` per encounter/visit. Hospital EMR currently sends both doctors to the **same** first-open visit | Ambiguous until visit selection exists |
| Displayed provider = who saved? | The logged-in provider at save time. History does not show the name | **EXISTS BUT NOT EXPOSED** |

ABC200016 Consultation encounters (all on older OPD visit `6478a94e-…`, not on #001–#003):

| When | Visit | Provider |
|---|---|---|
| 19 Aug 03:05 | `6478a94e` | Clinical Doctor |
| 20 Aug 21:13 | `6478a94e` | Clinical Doctor |
| 20 Aug 23:00 | `6478a94e` | Clinical Doctor |

Today's #001 and #003 have **0** encounters (no consultation saved on them). Not created this audit.

Reception does **not** assign a doctor. That remains correct.

---

## 4. Patient history — what exists vs what Hospital EMR shows

Previous visits: date, **Visit #nnn** or **—**, visit type, open/closed, location, clock. Previous encounters: date · type only.

| Fact | Stored where | Hospital EMR | Status |
|---|---|---|---|
| Daily visit number | Visit attribute | Previous visits + Today's Patients + header | **EXISTS AND EXPOSED** |
| Date | `visit.date_started` | Yes | **EXISTS AND EXPOSED** |
| Visit type | `visit_type.name` | Yes | **EXISTS AND EXPOSED** |
| Location | `location.name` | Yes | **EXISTS AND EXPOSED** |
| Service / specialty | Appointment service / speciality (General Medicine, ENT) | Not on visits; not on Clinical | **EXISTS BUT NOT CONFIGURED** for this hospital; **EXISTS BUT NOT EXPOSED** |
| Attending doctor | `encounter_provider` | Not requested, not shown | **EXISTS BUT NOT EXPOSED** |
| Consultation note / HPI / complaint | Observations on Consultation encounter | Shown as “on this chart” from **patient-level** obs, not scoped to the current visit | **EXISTS AND EXPOSED** (patient-wide, not visit-safe) |
| Consultation fee | Odoo `consultation:{visitUuid}` | Fee card for the **bound** visit only | **EXISTS AND EXPOSED** on the current chart; **EXISTS BUT NOT EXPOSED** on the history list |
| Payment status | Odoo invoice `payment_state` | Fee card UNPAID / PAID | Same as fee |

Do **not** create a history table. The missing pieces are visit selection + displaying `encounter_provider` and fee/payment on the existing timeline.

---

## 5. Multiple visits / same patient (ABC200016)

Critical. Live visits today:

| No. | Type | Visit uuid | Encounters | Fee (GET `?visitUuid=`) |
|---|---|---|---|---|
| 001 | OPD | `271181d6-b121-4f96-b795-ff5e49f370d5` | 0 | No charge |
| 002 | OPD | `a70cbb56-88f2-43bd-afa8-463e61c220e7` | — | Not queried |
| 003 | Follow Up | `a3036eb0-d775-46d4-a59f-9f106148d08f` | 0 | **UNPAID charge already exists** |

If the doctor clicks **#003** (or **#001**, or **#002**):

| Question | What actually happens |
|---|---|
| Is visit UUID preserved? | **No** |
| Does consultation attach to #003? | **Yes, coincidentally** — because #003 is the first open visit in REST order, not because it was clicked |
| Does the fee attach to #003? | **Yes, same reason.** UI passes `openVisit.uuid` (#003). Default GET without `visitUuid` also prefers a billed open visit, which is #003 |
| Does history identify #003? | History lists all three with #001 / #002 / #003. It does not mark which one is “active” beyond header **003** |
| Could consultation attach to another open visit? | **Yes.** If #003 were closed, the next `find(open)` would be #002. Clicking #001 would still not select #001 |

`buildConsultationPayload` also sends `visitType: "OPD"` even when the bound visit is Follow Up. Encounter still goes on `visitUuid`. Not changed this audit.

Consultation notes/HPI load by **patient**, not visit. Opening any of the three can show notes from the 19–20 Aug OPD visit.

**Conclusion:** the list can distinguish the three rows. The chart cannot. Patient UUID is insufficient.

---

## 6. General Outpatient vs Consultant service

**Do not implement Consultant selection this phase.**

| Mechanism | Live | Usable for “MO vs Consultant clinic”? |
|---|---|---|
| Visit type OPD / Follow Up / Emergency / IPD | Used by Reception Start Visit | Kind of arrival, **not** clinic |
| Special OPD | Retrospective entry. In Clinical list if started today | **Do not** use as Consultant |
| Visit attributes | Visit Status, Admission Status, Daily Visit Number | No service field |
| Appointment speciality | General Medicine, ENT only | **EXISTS BUT NOT CONFIGURED** (no Gynaecology / Cardiology / Neurosurgery) |
| Appointment service | GM OPD / Follow-up / Procedure; ENT OPD / Follow-up / Procedure | Seed data |
| Appointment → visit link | `patient_appointment_fulfilling_encounter_map` = **0** rows | Not connected |
| `GET /appointments` | **403** for `doctor.abikan` / `reception.abikan`. Admin **200** (9 seed appointments, all `appointment_number` `0000`, provider Neha Anand) | **EXISTS BUT NOT EXPOSED** |
| Reception Start Visit | Visit type + ward for Admission only | **No service / clinic / named doctor** |
| Clinical Today's Patients | No service filter | **MISSING** |

Bahmni Appointments can represent “Gynaecology OPD Consultation” **after** the hospital adds specialities/services and staff have View Appointments. That is **not** wired to today's walk-in visits.

`practitioner_type` still cannot distinguish Medical Officer vs Consultant (previous audit). Clinical already records whoever is logged in.

---

## 7. Queue

**MISSING** as a waiting-room module.

Live (this audit):

- `GET /openmrs/ws/rest/v1/queue` → **404**
- `GET /openmrs/ws/rest/v1/queueentry` → **404**

Today's Patients **is** the current waiting workflow:

Reception starts visit → visit appears on Clinical Today's Patients (after refresh) → doctor opens the patient they are attending.

Do not build a queue.

---

## 8. What the doctor sees today

| Shown | Missing for “who am I attending?” |
|---|---|
| Daily number | Auto-refresh after Reception |
| Patient name | Service / clinic |
| Hospital number | Attending doctor (none yet — correct) |
| Visit type (OPD / Follow Up) | Which of this patient's open visits will open |
| Clock time (can collide) | Visit uuid (hidden, unused) |
| Open / Ended | |

The intended card:

> #001 · Fatima Abdullahi · ABC200016 · General Outpatient

is **almost** what the table already is. The dangerous gap is not the columns. It is that **Open ignores the row's visit**.

---

## 9. Consultation start / encounter / fee

When the doctor opens a patient and documents:

| Item | Value used |
|---|---|
| Visit UUID | First open visit from `GET /visit?patient=` — **not** the Today's Patients row |
| Encounter type | Consultation `d34fe3ab-5e07-11ef-8f7c-0242ac120002` |
| Provider | Logged-in user's OpenMRS provider |
| Encounter ↔ visit | `visitUuid` on the Bahmni encounter POST. Yes, associated |
| Fee visit | `ConsultationFeeCard` sends `openVisit?.uuid` (same first-open visit). Create requires `visitUuid`. Key `consultation:{visitUuid}` |
| Can fee and encounter use different visits? | **Yes, if** GET fee is called without `visitUuid` (prefers billed open visit) while save uses first open. Today both happen to be #003. If first-open were #001 and #003 already had a sale, default GET would show #003's fee on a chart saving to #001 |

`startOpdVisit` from the chart POSTs a new OPD visit **without** going through Reception numbering. Out of this workflow; not changed.

---

## 10. Security (unchanged)

| Actor | Today's Patients | Open chart | Save consultation / create fee | Odoo payment |
|---|---|---|---|---|
| `doctor.abikan` | **200** | Allowed (`app:clinical`) | Allowed | **403** (prior) |
| `reception.abikan` | **403** | Clinical hash denied | **403** | Denied |
| `nurse.abikan` | **403** | Clinical denied | **403** | Denied |
| `accountant.abikan` | **403** | Clinical denied | **403** | Allowed (`POST …/accountant/payment`) |

Nursing inpatient read still **200**. RBAC was not modified.

---

## 11. Live checks (read-only)

Existing daily-number TEST visits only. No new records.

| Check | Result |
|---|---|
| A. Doctor opens Today's Patients | **200**, 9 outpatient rows |
| B. Daily numbers visible/correct | 001–003, 005; 004 Emergency omitted; older rows **—** |
| C. Open a specific patient/visit | Opens **patient**. Hash has no visit |
| D. Visit UUID preserved | **No.** Bound visit = first open = **#003** |
| E. Encounter provider mechanism | Still `fetchProviderUuidForUser` → `providers: [{ uuid }]`. Live provider **Clinical Doctor**. Today's #001/#003 have no encounter yet |
| F. History | Shows Visit #001 / #002 / #003, type, date, location. No doctor name. No fee |
| G. Multiple visits distinguished | List: yes. Chart: **no** |
| H. Refresh | Re-binds to first open (#003). Does not keep a clicked #001 |

`/queue` and `/queueentry` still **404**.

---

## 12. What should stay in Bahmni / OpenMRS

- Visits, visit types, visit attributes (including Daily Visit Number)
- Consultation encounter + `encounter_provider`
- Appointment speciality / service **when** the hospital later names clinics
- idgen hospital number
- Odoo fee/payment keyed by visit

Hospital EMR should not add a doctor table, specialty database, queue, or history table.

---

## 13. What needs hospital configuration (later)

| Item | Status |
|---|---|
| Medical Officer vs Consultant on providers | **EXISTS BUT NOT CONFIGURED** (`practitioner_type`) |
| Gynaecology / Cardiology / Neurosurgery clinics | **EXISTS BUT NOT CONFIGURED** (add appointment speciality/service) |
| Whether walk-in Today's Patients should filter by clinic | **REQUIRES HOSPITAL DECISION** |
| Whether Emergency should appear on Clinical | **REQUIRES HOSPITAL DECISION** (still excluded) |

---

## 14. Recommended next implementation phase

**Visit-preserving Open.** Do not build a queue. Do not add Consultant pickers yet.

1. Pass `visitUuid` from Today's Patients into the Clinical hash (and header search stays patient-only, or asks when several open visits exist).
2. Bind consultation save, fee create, admit, and the header number to **that** visit.
3. If the chosen visit is closed or missing, say so; do not silently take another open visit.
4. Then expose attending provider on Previous visits from existing `encounter_provider`.
5. Only after that: clinic/service routing via existing appointment speciality/service, if the hospital configures them.

Until (1)–(3), a doctor who selects #001 is attending #003.

This gap is now closed. See **Visit-Preserving Clinical Open — Implementation** below.

---

## Findings index

| Finding | Classification |
|---|---|
| Today's Patients from today's OpenMRS visits | **EXISTS AND WORKS** |
| Daily visit number on the list | **EXISTS AND WORKS** |
| Sort by stored number | **EXISTS AND WORKS** |
| Open correct **patient** | **EXISTS AND WORKS** |
| Logged-in provider on Consultation save | **EXISTS AND WORKS** |
| Fee keyed by visit uuid when UI sends one | **EXISTS AND WORKS** |
| RBAC Clinical vs Reception / Nurse / Accountant | **EXISTS AND WORKS** |
| Attending provider on history | **EXISTS BUT NOT EXPOSED** |
| Fee/payment on history list | **EXISTS BUT NOT EXPOSED** |
| Appointment services / specialities | **EXISTS BUT NOT CONFIGURED** |
| Appointments as Clinical list | **EXISTS BUT NOT EXPOSED** (403 for staff) |
| Preserve selected visit uuid | **EXISTS AND WORKS** (implemented this phase) |
| Open a previous visit from the chart list | **EXISTS AND WORKS** (same Open route) |
| OpenMRS Queue module | **MISSING** |
| Service on the visit / Reception Start Visit | **MISSING** |
| Auto-refresh after Reception | **MISSING** |
| MO vs Consultant / named clinics | **REQUIRES HOSPITAL DECISION** + configuration |

---

## Visit-Preserving Clinical Open — Implementation

Date: **23 Aug 2026**. This phase implements visit identity. It does **not** add Consultant routing, a queue, provider tables, or new visit types.

### Previous problem

Today's Patients already had the correct `visitUuid` on each row. **Open** discarded it and navigated to `#/doctor/patient/{patientUuid}`. The chart then bound consultation, fee, admission, and the header number to `visits.find(open)` — the first open visit from `GET /visit?patient=`.

For ABC200016 that was **#003**, even when the doctor clicked **#001**.

### Selected visit routing

Open now writes:

`#/doctor/patient/{patientUuid}/visit/{visitUuid}`

This matches the existing path style used for invoices. The visit is the existing OpenMRS visit. No visit database was added.

Header search still calls `openConsultation(patientUuid)` with no visit. That hash has **no** leftover visit from the previous patient.

### Visit validation

`bindConsultationVisit` loads **only** the selected visit. It does not fall back to the first open visit when the selected visit is missing.

If the selected visit is not in the last 20 visits, the chart fetches that visit by id and checks that it belongs to the open patient. Missing or mismatched visits show a staff-facing error. Another visit is never substituted.

Backend:

- Consultation fee GET/POST: `load_visit` already rejected a visit that belongs to another patient (`409`). GET without `visitUuid` no longer picks a billed or first-open visit.
- Laboratory orders and admission reject a visit that does not belong to the patient.

### Chart behavior

When a visit is in the route, the header number, visit type, consultation save, prescription, laboratory order, admission, and consultation fee all use that visit.

A closed selected visit can be viewed. It cannot be written to. The chart does not start a different open visit.

### Refresh behavior

The visit id is in the hash, so a browser refresh keeps the same patient **and** the same visit.

### Multiple-visit behavior

ABC200016 #001, #002, and #003 are separate rows. Each Open writes a different visit into the hash. The patient id stays the same.

Previous visits on the chart are now the same Open: clicking a row opens that exact visit.

### Consultation binding

`saveConsultation` receives `openVisit.uuid` where `openVisit` is the **selected** visit when it is still open. Provider mapping is unchanged: logged-in doctor → OpenMRS user → provider on the Consultation encounter.

### Fee binding

The fee card is rendered only when a visit is selected. GET and create always send that visit. Key remains `consultation:{visitUuid}`. Product, pricelist, Accountant, and payment were not changed.

### Provider behavior

Unchanged. The attending doctor is still stored on the encounter, not the visit.

### Tests

`consultationVisit.test.ts` covers route contents, selected-visit load, multiple visits for one patient, refresh-style hash read, patient/visit mismatch, header-search clearing the previous visit, consultation/fee using the selected visit, and no first-open fallback.

### Live verification (23 Aug 2026)

Existing TEST patient ABC200016. No new patients, visits, invoices, charges, or payments.

| Check | Result |
|---|---|
| A. Today's Patients numbers | 001 / 002 / 003 visible for ABC200016 |
| B. Open #001 | Hash ends `/visit/271181d6-…`. Header **001**, type OPD, fee create (no charge) |
| D. Open #002 | Hash `/visit/a70cbb56-…`. Header **002**, “This visit” on #002 |
| F. Open #003 | Hash `/visit/a3036eb0-…`. Header **003**, type Follow Up, fee **Payment required** (existing UNPAID on this visit only) |
| G. Refresh / reopen #001 | Stays on #001, not #003 |
| H/I. Consultation + fee context | Selected visit only. GET without `visitUuid` returns no visit. Wrong-patient visit → **409** |
| Header search | Opens `#/doctor/patient/{patientUuid}` with no leftover visit |

The hospital stack was restarting when this phase began. Live UI was verified after OpenMRS came back.

---

## Patient History — Attending Provider

Date: **23 Aug 2026**. This phase reads existing OpenMRS Consultation `encounter_provider` data. It does **not** add a history table, move the provider onto the visit, or change how consultation save records the logged-in doctor.

### Existing provider source

Unchanged:

logged-in Hospital EMR doctor → OpenMRS user → provider UUID → Consultation encounter → `encounter_provider`

Live leftover OPD visit `6478a94e-…` for ABC200016 has **three** Consultation encounters. Each stores provider **Clinical Doctor** (`17dec510-…`). Role display is **Unknown**. Laboratory encounters on the same visit have a system provider and are ignored.

### How history retrieves provider

`GET /visit?patient=` (already used for Previous Visits) now asks for each visit’s encounters and `encounterProviders`. No new API and no new database.

The attending name is the **person display** on the **latest Consultation encounter** for that visit — the same “latest Consultation” rule already used when saving. Login ids such as `doctor.abikan` are not shown.

### How provider is associated with the correct visit

Providers are read from the encounters **nested on that visit**. #001, #002, and #003 for ABC200016 have **no** Consultation encounters, so they show **Attended by: —**. The older leftover visit shows **Clinical Doctor**. The logged-in doctor is never copied onto other visits.

### Daily visit number display

Unchanged: stored Daily Visit Number → `Visit #001`. Historical visits without the attribute stay **—**.

### Visit type display

Previous Visits now uses the existing Reception wording: General Outpatient, Follow-up, Emergency, Admission. Special OPD remains **Retrospective visit**.

### Behavior when no provider exists

**Attended by: —**

### Multiple Consultation encounters

OpenMRS allows several Consultation encounters on one visit. Hospital EMR uses the latest by encounter datetime. On this stack all three leftover encounters have the same provider. If one encounter listed several named providers, the first named person is shown. Encounter roles are **Unknown**, so role cannot be used to pick “the clinician.”

### Current visit

The selected visit uses the same field. “Attended by” appears in the header only after a Consultation encounter on **that** visit has a provider. Opening the chart does not invent one.

### Fee / payment on history

**EXISTS BUT NOT EXPOSED.** Fee remains `consultation:{visitUuid}` on the fee card. History does not add a second billing query.

### Service / specialty

Not shown. Appointment services are still not linked to these visits.

### Tests

`visitAttendingProvider.test.ts`: latest Consultation provider, per-visit association, laboratory ignored, empty state, daily number beside attending, no cross-patient leak.

### Build result

Recorded in §15.

### Live verification

Existing TEST data only. Browser: `doctor.abikan` on bundle `index--3UiuVkD.js`. No new patients, visits, invoices, or payments.

ABC200016 Previous Visits (View all):

| Date | Number | Type | Attended by |
|---|---|---|---|
| 23 Aug 2026 | #003 | Follow-up | — |
| 23 Aug 2026 | #002 | General Outpatient | — |
| 23 Aug 2026 | #001 | General Outpatient | — |
| 21 Aug 2026 | — | General Outpatient / Emergency / Retrospective / Follow-up | — |
| 19 Aug 2026 | — | General Outpatient (`6478a94e-…`) | **Clinical Doctor** |

Opening that 19 Aug visit shows header **Attended by: Clinical Doctor**. Opening #001 does not.

| Check | Result |
|---|---|
| A/B. Chart + Previous Visits | ABC200016 #001 hash `/visit/271181d6-…`; history lists visits |
| C. Visit numbers | #001 / #002 / #003 match stored numbers. Older visits stay **—** |
| D. Attending on leftover consult visit | **Clinical Doctor** (matches `encounter_provider`) |
| E. #001–#003 do not inherit that doctor | **Attended by: —** |
| F. No Consultation provider | **—** |
| G. Switch to ABC200017 | Five visits, all **Attended by: —**. No leftover Clinical Doctor |

---

## Doctor Dashboard — Hospital-Facing Visit Labels

Date: **23 Aug 2026**. UX-only. OpenMRS visit types, visit creation, daily numbers, Clinical filtering, consultation save, attending-provider, billing, and Reception were not changed.

### Why this existed

Today's Patients printed the stored OpenMRS name (`OPD`, `Follow Up`). Reception and Previous Visits already used `receptionVisitTypeLabel`. Doctors saw two names for the same visit.

### Display mapping (existing Reception function)

| Stored OpenMRS name | Doctor-facing label |
|---|---|
| OPD | General Outpatient |
| Follow Up | Follow-up |
| EMERGENCY | Emergency |
| IPD | Admission |
| Special OPD | Retrospective visit |

API rows still carry `visitType: "OPD"`. Only the table cell, sticky caption, identity header, and Previous Visits call the existing mapper. No second mapping table.

### Unchanged

- Visit uuid in the Open hash
- Daily Visit Number
- Today's Patients include/exclude rules (still OPD, Special OPD, Follow Up)
- Consultation encounter / provider recording
- Fee key `consultation:{visitUuid}`

### Tests

`todaysPatients.test.ts` and `consultationVisit.test.ts`: stored type stays `OPD` / `Follow Up`; doctor-facing labels match Reception; selected visit uuid and daily number stay the same.

### Live verification

Existing TEST rows only. Bundle `index-BNmOlfiM.js`.

| Check | Result |
|---|---|
| Today's Patients labels | OPD → **General Outpatient**, Follow Up → **Follow-up** |
| Daily numbers | Unchanged (001 / 002 / 003) |
| Open hash | Still `#/doctor/patient/{patientUuid}/visit/{visitUuid}` |
| Previous Visits | Already used Reception labels |
| Active visit header | **General Outpatient** / **Follow-up**, not OPD |
| Consultation / attending / fee | Unchanged |

---

## 15. Testing

| Command | Result |
|---|---|
| `npm test` | **131 passed**, 0 failed |
| `npm run build` | Succeeded. Bundle `dist/assets/index-BNmOlfiM.js` |
