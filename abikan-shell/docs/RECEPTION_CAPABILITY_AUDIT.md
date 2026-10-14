# Reception Phase 2 — implemented arrival workflow

Date: **21 Aug 2026** (Africa/Lagos). Phase 1 audit findings are preserved below.

**PATIENT DATA:** OpenMRS/Bahmni  
**PATIENT IDENTIFIER:** OpenMRS/Bahmni (source **ABC**, prefix **ABC**)  
**VISITS:** OpenMRS/Bahmni  
**PAYMENTS:** Odoo / Accounts  
**RECEPTION:** Hospital EMR hospital-facing interface  

No Hospital EMR patient, MRN, visit, encounter, queue, or payment table was created. Laboratory, Pharmacy, Radiology, Nursing, and Clinical workflows were not redesigned. Consultation fee remains in Clinical. Reception does not collect money. ORD-7 and ordinary hospital patients were not modified.

Medical Officer vs Consultant mapping (investigation only, 22 Aug 2026) is in **Medical Officer vs Consultant — Final Mapping** below. Special OPD is retrospective data entry, not Consultant.

---

## Sources of truth

| Work | System |
|---|---|
| Patients, names, sex, birthdate, phone, address, extra identifiers | OpenMRS |
| Hospital number | OpenMRS identifier source **ABC** (`generateIdentifier.form?source=1`) |
| Visits, visit types, locations | OpenMRS |
| Registration/card charges and payments | Odoo (Registration Desk shop, Hospital Registration NGN pricelist) |
| Hospital screens | Hospital EMR |

Bahmni `defaultIdentifierPrefix` is still **GAN**. That setting is unused. Hospital EMR does not generate ABC numbers in React or in a Hospital EMR database. The identifier OpenMRS actually returns is **ABC** (proven: new isolated patient **ABC200017**).

---

## 1. Patient registration

**EXISTS AND WORKING** in Hospital EMR at `#/reception/register`.

Reception → Register Patient opens a Hospital EMR form. Save calls `POST /openmrs/abikan-api/registration/patients`, which creates the person/patient through OpenMRS REST after OpenMRS generates the hospital number. There is no Hospital EMR patient record.

Edit uses the same form at `#/reception/register/{uuid}` → `POST /openmrs/abikan-api/registration/patient/{uuid}` → OpenMRS **patient** update (`Edit Patients`). See **Patient Edit — False Access Error**.

---

## 2. Available registration fields

Exposed from live OpenMRS metadata, not an invented schema:

- Name (first, middle, last)
- Sex (Male / Female / Other)
- Date of birth, age in years, estimated-date checkbox
- Person attributes actually on this server: Phone, Other phone, Email, Local family name, Local middle name
- Address fields from the OpenMRS address template: Address, Area / landmark, City / town, State, Local government area, Postal code, Country
- Extra identifier: Previous hospital number (`Old Identification Number`). The unused OpenMRS-named identifier type is hidden from staff.

**Next of kin:** relationship types exist in Bahmni config but this installation returns **0** live relationship types. The Next of kin block is hidden until OpenMRS has types. Do not invent a next-of-kin table.

---

## 3. Patient identifier / MRN handling

OpenMRS source **ABC**, prefix **ABC**, next after this phase: **ABC200018**.

Hospital EMR never invents a number. `GET /openmrs/module/idgen/generateIdentifier.form?source=1` is called on the registrar session at save time. The value OpenMRS returns is stored as the preferred Patient Identifier at Registration Desk.

GAN vs ABC mismatch is documented, not “fixed” by a new generator.

---

## 4. Existing patient search

Header search still uses `GET /openmrs/ws/rest/v1/patient?q=`.

Proven: name and hospital number. Phone is a searchable OpenMRS attribute; the search box offers it. Few stored phones exist, so phone hits will be rare until numbers are entered.

Enter no longer leaves Hospital EMR for Bahmni find-patient from Reception.

---

## 5. Duplicate-prevention behavior

No second duplicate database.

Before create, Hospital EMR searches OpenMRS by name (and phone if entered). Matching patients are shown. Save is blocked with `possible_duplicate` (409) unless the receptionist chooses **Register anyway**.

Proven: registering `Hospital EMRRecv Phase2225617` again returned 409 and `ABC200017`.

---

## 6–11. Visit types and locations

Reception Start Visit offers only the four normal arrival types. **Special OPD** remains in OpenMRS for retrospective data entry and is **not** a Reception choice. Medical Officer / Consultant are providers, not visit types.

Locations come from existing OpenMRS **Login Location** rows. Hospital EMR does not create or rename locations. Reception is only asked when the place is an operational decision.

| Staff label | OpenMRS visit type | Location used | Reception sees |
|---|---|---|---|
| General Outpatient | OPD | Existing **OPD-1** (Clinical default) | No location field |
| Follow-up | Follow Up | Existing **OPD-1** | No location field |
| Emergency | EMERGENCY | Existing **Emergency** | No location field |
| Admission | IPD | Selected ward | **Ward** selector (four valid wards) |

OPD-2 is not offered and is never a fallback. If OPD-1 cannot be resolved, start visit is blocked. Unrelated locations (Registration Desk, rooms, Emergency Room, Special OPD) are not offered. See **Reception outpatient location hidden**.

Clinical Today's Patients still includes OPD / Special OPD / Follow Up when the visit starts today, and still excludes IPD and EMERGENCY. That Clinical rule was not changed.

A patient with an already-open visit can still start another kind of care. The screen says so.

---

## Live Verification — Reception Access and Visit Locations

Date: **23 Aug 2026** (Africa/Lagos). No new patients, visits, invoices, or charges were created. TEST patient **ABC200016** was read only.

### 1. Reception access issue

The message **“This action requires Reception access.”** is the backend 403 copy from `require_registrar`. Other departments see it when they call Reception APIs. The frontend denied screen uses different copy: “You do not have access to this department.”

Live: `reception.abikan` opening `#/reception` and `#/reception/patient/{ABC200016}` **succeeds**. The workspace is not blocked for the Reception user.

### 2. Root cause

Frontend and backend both required privilege **`app:registration`**.

`reception.abikan` has role **`Abikan:Reception`**, which inherits Bahmni **Registration-App** and therefore **`app:registration`** (29 live privileges; confirmed on session and `/user`).

The **Reception role itself was omitted** from the allow-list. Backend `REGISTRATION_ROLES` was only SuperAdmin / System Developer. The frontend guard checked only `app:registration`, not `Abikan:Reception` / `Abikan:Registration`. If the privilege list failed to flatten, a Receptionist would be denied even with the correct role.

This is a route-level guard **and** API authorization. Both used the same privilege name; both omitted the existing Reception roles.

### 3. Fix

No new privilege. Existing role + existing privilege only.

- Backend `is_registrar`: allow `Abikan:Reception` and `Abikan:Registration` in addition to `app:registration` and SuperAdmin / System Developer.
- Frontend `canOpenRegistration`: same roles, same privilege.

Other departments were not granted Reception access.

### 4. Reception RBAC verification

| Actor | Check | Result | Where |
|---|---|---|---|
| Reception `reception.abikan` | Workspace `#/reception` | Allowed | **Browser** |
| Reception | Search ABC200016 | Found | **Browser** |
| Reception | Register Patient form | Allowed (not submitted) | **Browser** |
| Reception | Start visit UI | Allowed; Start disabled until a place is chosen when several exist | **Browser** |
| Reception | Card fee create control | Present (not clicked) | **Browser** |
| Reception | `GET …/registration/metadata` | **200** | **API** |
| Reception | `GET …/registration/patient/{ABC200016}` | **200** | **API** |
| Reception | Payment `POST …/accountant/payment` | **403** Accountant workspace | **API** |
| Accountant | Reception metadata | **403** Reception access | **API** |
| Accountant | `GET …/accountant/payments` | **200** | **API** |
| Doctor | `#/reception` | “You do not have access to this department” | **Browser** |
| Doctor | Reception metadata | **403** | **API** |
| Doctor | Clinical today's patients + patient search | **200** | **API** |
| Nurse / Pharmacy / Laboratory | Reception metadata | **403** | **API** |
| Unauthenticated | Reception metadata | **401** | **API** |

### 5. General Outpatient

**Browser** on ABC200016: General Outpatient selected. Location selector offers **OPD-1** and **OPD-2** only. No Emergency, no ward. Start visit stays disabled until a place is chosen.

A new OPD visit was **not** started. ABC200016 already has an **open OPD at OPD-1** (21 Aug 2026 and 19 Aug 2026). **API** read of those visits: type **OPD**, location **OPD-1**.

Clinical can search ABC200016 (**API** 200 as `doctor.abikan`).

### 6. Follow-up

**Browser**: Follow-up offers **OPD-1 / OPD-2** only. No Emergency, no ward.

No new Follow Up visit started. Existing **open Follow Up at OPD-1** (21 Aug 2026) on ABC200016. **API** type **Follow Up**.

### 7. Emergency

**Browser**: location auto-set — “This visit will start at Emergency.” No OPD selector. No wards. Start visit enabled (not clicked).

Existing **open EMERGENCY at Emergency** (21 Aug 2026) on ABC200016. **API** type **EMERGENCY**, location **Emergency**. Clinical Today's Patients exclusion was not changed.

### 8. Admission

**Browser**: selector is **Aisha Children Ward, General Ward, Hawawu Maternity Ward, Pediatric Ward**. Not offered: OPD-1, OPD-2, Emergency, Emergency Room, Gold/Silver/Bronze rooms, Pre Labour Room. Start visit disabled until a ward is chosen. Not clicked. No bed assignment.

ABC200016 has no IPD visit from this phase. Mapping is from live metadata + UI.

### 9. Special OPD

**Browser** Start Visit does not offer Special Clinic or Special OPD. OpenMRS Special OPD type is untouched. ABC200016 still has a leftover **open Special OPD at OPD-1** (21 Aug 2026) from an earlier phase.

### 10. Location mapping

Confirmed live (metadata **API** + **browser**):

| Reception choice | OpenMRS type | Locations | UI |
|---|---|---|---|
| General Outpatient | OPD | OPD-1, OPD-2 | Choose |
| Follow-up | Follow Up | OPD-1, OPD-2 | Choose |
| Emergency | EMERGENCY | Emergency | Auto |
| Admission | IPD | four wards above | Choose |

OPD-1 / OPD-2 have no other display names. Not renamed.

### 11. Limitations

- ABC200016 already has several **open** visits. Further start-visit writes were skipped so this check would not add more open visits.
- Card fee create and payment collect were not re-run. Payment remains Accountant-only (**403** from Reception).
- Clinical still hides Emergency and IPD from Today's Patients.

---

## Reception outpatient location hidden

Date: **23 Aug 2026** (Africa/Lagos). No OpenMRS locations were created, renamed, or retired. Visit types, Clinical, providers, billing, and Reception RBAC were not changed.

Reception is only asked for a place when it is a real operational decision. Outpatient and Emergency locations stay on the existing OpenMRS rows; Reception never sees their names.

| Reception choice | Visit type | Location under the hood | What Reception sees |
|---|---|---|---|
| General Outpatient | OPD | Existing **OPD-1** (`5e232c47-8ff5-4c5c-8057-7e39a64fefa5`) | Title, helper, Start visit. No Location / Visit starts at / OPD-1 / OPD-2 |
| Follow-up | Follow Up | Existing **OPD-1** | Title, helper, Start visit. No location information |
| Emergency | EMERGENCY | Existing **Emergency** (`b5da9afd-b29a-4cbf-91c9-ccf2aa5f799e`) | Title, helper, Start visit. No location field named Emergency |
| Admission | IPD | Selected ward | Ward selector only |

Wards shown: Aisha Children Ward, General Ward, Hawawu Maternity Ward, Pediatric Ward. Not shown: OPD-1, OPD-2, Emergency, Emergency Room, Gold/Silver/Bronze rooms, Pre Labour Room, inpatient rooms.

If OPD-1 cannot be resolved, the visit is not created. There is no fallback to OPD-2, Registration Desk, or another location.

Special OPD / Special Clinic remain hidden in Reception. Special OPD is untouched in OpenMRS.

The patient header no longer shows a Location line. After OpenMRS confirms a new visit, the screen shows **“Visit successfully created.”** That banner is set only after `startRegistrationVisit` succeeds. A failed start clears it. `startingVisit` blocks a second submit while the first is in flight; a later refresh does not call start again.

Header search A → B used to keep Patient A on screen because App only stored the route name (`registration-patient`). Switching `#/reception/patient/{A}` → `{B}` did not re-render. App now stores the hash, and `RegistrationPatientWorkspace` remounts on `key={patientUuid}` so header, demographics, visits, fee, and route all belong to the selected patient without a refresh.

### Live verification (23 Aug 2026)

Signed in as `reception.abikan` at `https://localhost/abikan/`. Isolated TEST patients only.

| Check | Result |
|---|---|
| General Outpatient UI (ABC200016, ABC200017) | Start visit enabled. No Location, Visit starts at, OPD-1, OPD-2, or location selector |
| Follow-up on ABC200017 | Start visit created **Follow Up @ OPD-1** (open). Banner: **Visit successfully created.** No location copy |
| Emergency on ABC200017 | Start visit created **EMERGENCY @ Emergency** (open). Banner: **Visit successfully created.** No location copy |
| Admission UI (ABC200017) | Ward selector. Options only: Aisha Children Ward, General Ward, Hawawu Maternity Ward, Pediatric Ward. Start visit stayed disabled until a ward is chosen. No IPD visit started |
| Search A → B → A | ABC200016 (ABIKAN E2E TEST PATIENT) → ABC200017 (Hospital EMRRecv Phase2225617) → ABC200016. Header, hospital number, and patient-specific fee state updated each time. No refresh |

A second General Outpatient visit was not started. Both TEST patients already had an open OPD at OPD-1. Start visit for that choice uses the same path as Follow-up and Emergency.

### Tests and build

- `npm test`: **98 passed**
- `npm run build`: `dist/assets/index-BUpBtg7b.js`

### Test data created this pass

| Patient | What was created | What was not created |
|---|---|---|
| ABC200017 | Open **Follow Up** at OPD-1; open **EMERGENCY** at Emergency | No new patient, invoice, card fee, or admission |
| ABC200016 | None | Already had open OPD / Follow Up / EMERGENCY visits |

ORD-7 and ordinary hospital patients were not modified.

---

## Patient Edit — False Access Error

Date: **23 Aug 2026** (Africa/Lagos). TEST patient **ABC200016** only. No new patient, visit, or invoice. ORD-7 not touched.

### Symptom

Reception (`reception.abikan`) edited a patient and saved. The form kept the new value (and the page still said “Update the details already stored…”). The same save also showed **“This action requires Reception access.”** The receptionist could not tell whether the save worked.

### Which request returned 403

| Step | Request | Status |
|---|---|---|
| A. Load edit form | `GET /openmrs/abikan-api/registration/patient/{uuid}/profile` | **200** |
| A. Metadata | `GET /openmrs/abikan-api/registration/metadata` | **200** |
| B/C. Patient update | `POST /openmrs/abikan-api/registration/patient/{uuid}` | **403** `{ code: forbidden, message: This action requires Reception access. }` |
| Follow-up | `GET …/profile` (same Reception session) | **200** |

This was **not** a follow-up charge GET. The **update POST itself** returned 403. Hospital EMR `require_registrar` had already passed (profile and metadata were 200). The 403 was remapped from OpenMRS.

### Why the update looked saved / why it failed

Reception already has **`Abikan:Reception`**, **`app:registration`**, **Add Patients**, and **Edit Patients**. It does **not** have **Edit People** / **Add People**.

Hospital EMR wrote through `POST /openmrs/ws/rest/v1/person/{uuid}`. OpenMRS answered:

`Privileges required: Edit People, Add People`

`_openmrs_error` turned every OpenMRS 403 into **“This action requires Reception access.”** That is `require_registrar` copy, so the UI contradicted a receptionist who was already in Reception.

`POST /openmrs/ws/rest/v1/patient/{uuid}` with `{ person: … }` returns **200** for the same user. That is the resource Bahmni Registration uses.

### Fix

No new OpenMRS privilege. Reception RBAC unchanged.

- `update_patient` now POSTs to the **patient** resource (`Edit Patients`), not the person resource (`Edit People`).
- Existing person-attribute UUIDs are sent so a save updates the row instead of adding a second email/phone.
- OpenMRS 403s are no longer rewritten as Reception-access denials. Only `require_registrar` uses that sentence.
- After a successful edit the form stays open, reloads the saved profile, and shows **“Patient updated successfully.”** It does not navigate into a second request that can overwrite that state.

### Live persistence (ABC200016)

Field used: **Email** (`abc200016.verify@abikan.test`). Confirmed in OpenMRS patient GET after Hospital EMR save, and again after refresh.

### RBAC after the fix

| Actor | Reception patient edit POST | Result |
|---|---|---|
| Reception `reception.abikan` | Allowed | **200** |
| Doctor | Forbidden | **403** Reception access |
| Accountant | Forbidden | **403** Reception access |
| Nurse | Forbidden | **403** Reception access |
| Pharmacy | Forbidden | **403** Reception access |
| Laboratory | Forbidden | **403** Reception access |
| Unauthenticated | — | **401** |

### Tests

- Browser (`reception.abikan`): Save → **“Patient updated successfully.”** Email remains visible. No access error. Refresh → email still `abc200016.verify@abikan.test`.
- `npm test`: **98 passed**
- `npm run build`: `dist/assets/index-BuKJ3ZFZ.js`

---

## 12. Registration / card fees

Approved hospital values live in `abikan-shell/server/patient-account/data/registration_fees.json` and are created as Odoo products:

| Card | Odoo product | Amount |
|---|---|---|
| Individual Card | `registration-individual` | ₦2,000 |
| Family Card | `registration-family` | ₦5,000 |

Registration Desk shop now uses **Hospital Registration (NGN)**. The old TEST $50 product is unused for new charges. Amounts are not the billing source of truth in React; the UI reads the metadata/charge API.

Reception creates the charge after a visit exists. There is no Pay control.

---

## 13. Accountant payment handoff

Proven isolated path:

1. Reception created Individual Card ₦2,000 on **ABC200017** visit `278d8165-b369-47da-b249-bfa930cdfbcf`
2. Odoo invoice **INV/2026/00025** (Registration, UNPAID)
3. Reception payment POST → **403**
4. Doctor payment POST → **403**
5. Accountant collected via existing Accounts payment → invoice posted
6. Reception charge status → **PAID**

---

## 14. Consultation fee remains in Clinical

Not moved. Doctor still creates the consultation fee in Clinical. Accountant still collects it. Reception has no consultation-fee field.

---

## 15. Queue status

`/queue` is still 404. No waiting-room database was built. “Waiting” is open visits that started today on Reception Today's Visits.

**Future work:** a real queue only if the hospital adopts a usable OpenMRS/Bahmni queue module.

---

## 16. Clinical handoff

| Reception start | Clinical Today's Patients (unchanged rules) |
|---|---|
| OPD today at OPD-1 | Shown |
| Special OPD today at OPD-1 | Shown |
| Follow Up today at OPD-1 | Shown |
| Emergency today at Emergency | **Not shown** (intentional Clinical exclusion) |

Clinical visit-start and consultation-fee behavior were not changed.

---

## 17. RBAC

Unchanged privileges. Reception APIs require `app:registration`.

| Actor | Register / edit patient | Start visit | Create card charge | Collect payment |
|---|---|---|---|---|
| Unauthenticated | 401 | 401 | 401 | 401 |
| Reception | allowed | allowed | allowed | **403** |
| Accountant | **403** | **403** | **403** | allowed |
| Doctor | **403** | Clinical OPD start unchanged | **403** | **403** |
| Nurse / Laboratory / Pharmacy | **403** | **403** | **403** | **403** |

Reception cannot dispense, order lab, write clinical notes, prescribe, diagnose, change lab results, or change pharmacy inventory. Those screens stay department-gated.

---

## 18. What remains for future phases

- Next of kin when OpenMRS relationship types are configured
- Phone search will only find patients who have a stored phone
- Standalone queue / calling
- Clinical Emergency list (do not change without an explicit request)
- GAN vs ABC Bahmni config cleanup (hospital/ops decision; do not invent a third scheme)
- Family Card live payment was not re-invoiced after Individual was proven; the Family product and ₦5,000 price exist
- Consultation fee amount editable by the doctor (explicitly out of this phase)

---

## Navigation

```
Reception
├── Dashboard
├── Search Patients
├── Register Patient
└── Today's Visits
```

Patient → Start Visit → visit type → location if more than one → Start visit → optional card fee → Accountant.

---

## Isolated TEST data created in this phase

| Record | Value |
|---|---|
| Existing TEST patient used | ABC200016 / `f242364e-b70f-4fec-b29e-8ad4fbe147b5` |
| New isolated patient | **ABC200017** Hospital EMRRecv Phase2225617 / `71f9788f-67f7-441c-b520-11979cbc37ec` |
| OpenMRS visits on ABC200016 (21 Aug 2026) | Follow Up, Special OPD, EMERGENCY, OPD at the locations above |
| OpenMRS visit on ABC200017 | OPD at OPD-1 `278d8165-b369-47da-b249-bfa930cdfbcf` |
| Invoice | INV/2026/00025 Individual Card ₦2,000 — paid by accountant.abikan |
| ORD-7 | not modified |

---

## Tests

- `npm test`: **92 passed**
- `npm run build`: `dist/assets/index--lHPsDjy.js`
- Browser: Reception dashboard, Register Patient form (Individual/Family ₦2,000 / ₦5,000, OpenMRS fields, no payment controls), header search ABC200016, patient Start visit types/locations, Patient Account link

---

## Medical Officer vs Consultant — Final Mapping

Date: **22 Aug 2026** (Africa/Lagos). **Investigation only.** No UI, OpenMRS, Odoo, providers, visit types, specialties, patients, visits, invoices, or charges were created or changed.

Hospital requirement under review: Medical Officers handle general consultations; Consultants handle specialist consultations (Gynaecology, Cardiology, Neurosurgery, and similar). The doctor who conducts the consultation determines the consultation fee. Accountant collects all money. Reception starts the visit and must stay simple. The mapping must stay inside the existing Bahmni/OpenMRS model.

Related live evidence: OpenMRS MySQL (`visit_type`, `provider`, `provider_attribute*`, `appointment_speciality`, `appointment_service`, `encounter_type`, `location`, `providermanagement_provider_role`), Bahmni `abikan-config/openmrs/apps/clinical/app.json`, `abikan-config/openmrs/apps/appointments/app.json`, Hospital EMR Clinical charge path (`consultation.py`, `ConsultationFeeCard.tsx`), `CONSULTATION_BILLING_IMPLEMENTATION.md`.

---

### 1. Providers

**How providers are represented.** OpenMRS `provider` rows linked to a `person` (and usually a login `user`). This installation has **12** providers, including Bahmni demo accounts and Hospital EMR staff (`doctor.abikan` / Clinical Doctor, `abikan.doctor` / Hospital EMR Doctor).

**How names are retrieved.** From the provider’s person name (`provider.display` / `person.display`: given name + family name). Hospital EMR Clinical save already loads the logged-in user’s provider with `GET /openmrs/ws/rest/v1/provider?user={userUuid}`.

**Roles.** OpenMRS user roles exist (`Abikan:Doctor`, `Doctor`, `Provider`, appointment privileges). These are **login rights**, not Medical Officer vs Consultant. REST `providerRole` is not available (404). The `providermanagement_provider_role` table exists and is **empty**.

**Specialties on the provider.** None. No provider is tagged Gynaecology, Cardiology, Neurosurgery, or any other specialty.

**Provider attributes.** Three attribute types exist:

| Attribute | Purpose in this install | Live values |
|---|---|---|
| `practitioner_type` | “list of practitioners”; dropdown options are only `,Doctor` | Only **Neha Anand** (`identifier: doctor`) = `Doctor` |
| `Available for appointments` | Boolean | Only Neha Anand = `true` |
| `Login Locations` | Location datatype | **Unused** on every provider |

Hospital EMR Clinical users have **no** provider attributes.

**Can the system distinguish Medical Officer vs Consultant today?** **No.** Every configured practitioner type is the single value `Doctor`. No Medical Officer or Consultant value exists. No provider-management role exists for either.

**Locations / clinics.** Providers are not bound to clinics. Locations are Registration Desk, OPD-1, OPD-2, Emergency, and wards — not Gynaecology, Cardiology, or Neurosurgery. Appointment rows that exist all name **Neha Anand** and use **General Medicine** or **ENT** services, not Hospital EMR doctors.

| Finding | Classification |
|---|---|
| Provider + person name | **EXISTS AND WORKS** |
| Logged-in doctor attached to the Consultation encounter | **EXISTS AND WORKS** |
| Provider-management roles | **EXISTS BUT NOT CONFIGURED** (table empty) |
| `practitioner_type` Medical Officer / Consultant | **EXISTS BUT NOT CONFIGURED** (only `Doctor`) |
| Provider specialty / clinic location | **MISSING** |
| Reception pick of a specific provider | **EXISTS BUT NOT EXPOSED IN ABIKAN** |

---

### 2. What `Special OPD` actually is

Do **not** treat Special OPD as Consultant. The live record proves otherwise.

| Source | Value |
|---|---|
| OpenMRS visit type name | `Special OPD` |
| OpenMRS description | **Visit for retrospective data entry** |
| Retired | No |
| Bahmni Clinical `defaultVisitType` | `OPD` |
| Bahmni Clinical `visitTypeForRetrospectiveEntries` | **`Special OPD`** |

That is the retrospective-entry visit type used when a clinician back-dates notes. It is not a specialist clinic, not a consultant roster, and not a specialty.

Other live visit-type descriptions (for contrast):

| Visit type | OpenMRS description |
|---|---|
| OPD | Visit for Out patient |
| IPD | Visit for patients being admitted |
| EMERGENCY | Visit for emergency patients |
| Follow Up | Visit for patients coming for a follow up |
| Special OPD | Visit for retrospective data entry |

Reception no longer offers Special OPD as a Start Visit choice. Leftover visits of that type show as **Retrospective visit**, not Special Clinic.

| Finding | Classification |
|---|---|
| Special OPD as retrospective-entry visit type | **EXISTS AND WORKS** |
| Special OPD as Consultant / specialist care | **MISSING** (it does not represent that) |

**Recommendation:** do **not** use Special OPD for Consultant.

---

### 3. Cleanest existing representation

Medical Officer vs Consultant is **who sees the patient**, not a second visit type and not a patient category.

| Hospital idea | Cleanest existing object | Why |
|---|---|---|
| Medical Officer | OpenMRS **Provider**, later tagged `practitioner_type` = Medical Officer | The consulting doctor is already a provider. The visit type for general outpatient care is already **OPD**. |
| Consultant | OpenMRS **Provider**, later tagged Consultant, plus Bahmni **appointment speciality / appointment service** for the clinic | Specialties already exist as appointment metadata, not as visit types. |
| General consultation (the visit) | Visit type **OPD** | “Visit for Out patient.” |
| Specialist clinic slot | `appointment_speciality` + `appointment_service` | Bahmni Appointments already has `enableSpecialities: true`. |
| Follow-up (the visit) | Visit type **Follow Up** | Distinct from OPD; not a patient class. |
| Emergency / admission | Visit types **EMERGENCY** / **IPD** | Already used that way. |

What was checked and rejected as the primary mapping:

| Mechanism | Verdict |
|---|---|
| Visit type `Special OPD` | Retrospective data entry. **Not Consultant.** |
| Encounter type | One live type: **Consultation**. No MO vs Consultant split. |
| Location | OPD-1 / OPD-2 / Emergency / wards. No specialty clinics. |
| OpenMRS Provider role | Mechanism exists; **no roles configured**. |
| Clinical Gynaecology form | Observation concept set on the chart, not a Reception clinic and not a provider specialty. |

Live appointment catalogue (seeded Bahmni data, not a hospital consultant list):

| Speciality | Services |
|---|---|
| General Medicine | OPD Consultation, Follow-up Consultation, Procedure |
| ENT | OPD Consultation, Follow-up Consultation, Procedure |

Gynaecology, Cardiology, and Neurosurgery are **not** appointment specialities on this server. Gynaecology appears only as a Clinical observation form.

| Finding | Classification |
|---|---|
| OPD = general outpatient visit | **EXISTS AND WORKS** |
| Provider as the consulting doctor | **EXISTS AND WORKS** |
| Appointment speciality / service as clinic | **EXISTS BUT NOT CONFIGURED** for this hospital’s specialties |
| Appointments in Hospital EMR Reception | **EXISTS BUT NOT EXPOSED IN ABIKAN** (`reception.abikan` has no appointment privilege; earlier `/appointments` was 403) |
| MO vs Consultant values | **MISSING** in current data; mechanism to store them is **EXISTS BUT NOT CONFIGURED** |
| Whether Reception must route to a named consultant | **REQUIRES HOSPITAL DECISION** |

Do not create a new Hospital EMR MO/Consultant table, specialty database, or parallel visit types. Configure the existing provider attribute and (if the hospital uses clinics) existing appointment specialities.

---

### 4. What Reception eventually needs to select

Keep the desk short. The dimensions the hospital named are already separate objects:

```
Find patient
  → Existing patient  OR  Register patient
  → Start visit
       Visit kind: General Outpatient (OPD) / Follow-up / Emergency / Admission
       Place: existing location (OPD-1, Emergency, ward)
  → Patient reaches Clinical when a doctor opens that visit
```

**Medical Officer vs Consultant is not a visit type.** It is the provider who conducts the consultation. The simplest existing workflow is:

1. Reception starts **OPD**, **Follow Up**, **EMERGENCY**, or **IPD**.
2. The Medical Officer or Consultant who opens the chart is the logged-in Clinical provider.
3. That provider creates the consultation fee in Clinical.
4. Accountant collects.

If the hospital later needs Reception to **send the patient to a named clinic or consultant**, the existing Bahmni objects to reuse are **appointment service / speciality** or an existing **provider** — not a new questionnaire and not Special OPD.

A two-step Reception control (“Medical Officer / Consultant”, then pick a consultant) would only be justified after the hospital configures those providers and specialties. It is not required by the current data model, and it should stay optional so the desk does not become a form.

Do **not** ask Reception to choose Special OPD in order to mean Consultant.

| Finding | Classification |
|---|---|
| Find / register / start visit | **EXISTS AND WORKS** |
| Visit kind + location | **EXISTS AND WORKS** |
| Reception provider / clinic picker | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Auto-routing to a consultant list | **MISSING** until hospital configures providers/specialties |

---

### 5. How a specific Consultant / specialty should be selected

Use objects that already exist:

1. **Hospital configures** OpenMRS providers for each Medical Officer and Consultant (names already work).
2. **Hospital sets** `practitioner_type` options to include Medical Officer and Consultant (the attribute type already exists).
3. **If clinics matter**, hospital adds appointment specialities/services (Gynaecology, Cardiology, Neurosurgery, …) beside the existing General Medicine and ENT rows.
4. Reception, later, may pick that **provider** or **appointment service**. Clinical still records the logged-in provider on the Consultation encounter.

Do not invent Hospital EMR specialty rows. Do not create visit types named Consultant or Gynaecology. Do not rename Special OPD.

| Finding | Classification |
|---|---|
| Appointment speciality table | **EXISTS AND WORKS** (General Medicine, ENT only) |
| Needed hospital specialties | **EXISTS BUT NOT CONFIGURED** |
| Clinical Gynaecology form as a clinic selector | Wrong object — chart observations, not arrival routing |

---

### 6. Where the consultation fee is determined

The field is **not** on Reception. It stays in Clinical.

| Question | Answer |
|---|---|
| Where is it stored? | Odoo sale order + customer invoice. Idempotency key `consultation:{visitUuid}`. Shop **Consultation Desk**. Product **Consultation Fee — TEST**. |
| How is the charge created? | Logged-in Clinical user, privilege `app:clinical`, `POST /openmrs/abikan-api/consultation/patient/{uuid}/charge` with `{ visitUuid, requestId }` only. |
| Which provider creates it? | The **logged-in Clinical doctor**, not a Reception-selected consultant. |
| Can the amount differ between doctors? | **Not today.** React has no amount field. Backend copies one product `list_price` (**$75.00** TEST). |
| Does Odoo support different amounts later? | Yes, as additional service products or a changed `list_price` — documented as not implemented (`CONSULTATION_BILLING_IMPLEMENTATION.md` §27 item 5). |
| Can Accountant collect? | **Yes.** Same Accounts payment path as other departmental charges. Reception and Doctor payment POSTs remain 403. |

Desired rule — the consulting doctor **chooses the amount** — is **not** how the current fee works. Today the doctor only **creates** the fixed TEST charge. Changing that is a hospital/product decision, not a Reception change.

| Finding | Classification |
|---|---|
| Clinical create → Accounts collect | **EXISTS AND WORKS** |
| One shared TEST amount | **EXISTS AND WORKS** (TEST only) |
| Doctor-entered or per-doctor amount | **MISSING** in Hospital EMR; Odoo can hold more products later |
| Production MO vs Consultant prices | **REQUIRES HOSPITAL DECISION** |
| Moving the fee to Reception | Do not. Current split is correct. |

---

### 7. Follow-up is a visit, not a patient category

OpenMRS visit type **Follow Up**: “Visit for patients coming for a follow up.” Bahmni appointment services also have Follow-up Consultation rows under General Medicine and ENT.

A person is **new or existing** because they are or are not already an OpenMRS patient. That is independent of who sees them and independent of Follow-up vs first visit.

| Hospital combination | Existing representation |
|---|---|
| Existing + Medical Officer | Existing patient + OPD visit + MO provider (provider tag not configured) |
| Existing + Consultant | Existing patient + OPD visit + Consultant provider / appointment service (not configured) |
| Existing + Follow-up | Existing patient + visit type **Follow Up** (and/or a Follow-up appointment service) |
| Existing + Emergency | Existing patient + visit type **EMERGENCY** |
| New + Medical Officer | Register patient + OPD visit + MO provider |
| New + Consultant | Register patient + OPD visit + Consultant provider / service |

Do not add a “Follow-up patient” class. Do not collapse Consultant into Follow Up or Special OPD.

| Finding | Classification |
|---|---|
| Follow Up visit type | **EXISTS AND WORKS** |
| Follow-up appointment services | **EXISTS BUT NOT CONFIGURED** for this hospital’s clinics |
| Follow-up as a patient category | **MISSING** on purpose — do not create one |

---

### 8. Answers

**1. What existing concept should represent Medical Officer?**  
OpenMRS **Provider**, with `practitioner_type` set to Medical Officer once the hospital configures that option. The general consultation **visit** remains **OPD**.  
**EXISTS BUT NOT CONFIGURED** for the label; provider + OPD visit **EXISTS AND WORKS**.

**2. What existing concept should represent Consultant?**  
OpenMRS **Provider**, with `practitioner_type` set to Consultant, and — when a clinic must be named — Bahmni **appointment speciality / appointment service**.  
**EXISTS BUT NOT CONFIGURED** (no Consultant providers; specialties are only General Medicine and ENT).

**3. Should `Special OPD` be used for Consultant?**  
**No.** It is retrospective data entry (`visitTypeForRetrospectiveEntries`). Using it for specialist care would be incorrect.

**4. What should Reception eventually select?**  
Patient (existing or register), then visit kind (General Outpatient / Follow-up / Emergency / Admission) and place. That is enough for the patient to reach Clinical. A Medical Officer / Consultant control is only needed if the hospital requires Reception to route the patient, and only after those providers exist.

**5. How should a specific Consultant / specialty be selected?**  
From existing **providers** and, if used, existing **appointment specialities/services**. Hospital adds Gynaecology / Cardiology / Neurosurgery there. Hospital EMR must not invent a specialty list.

**6. Where should the consultation fee be determined?**  
In **Clinical**, by the Medical Officer or Consultant who conducts the consultation. Reception must not collect it or become the fee screen.

**7. How does Accounts receive the charge?**  
Existing path: Clinical creates the Odoo sale/invoice (`consultation:{visitUuid}`) → Patient Account shows UNPAID → Accountant collects → PAID. **EXISTS AND WORKS.**

**8. What should Hospital EMR NOT create?**

- Visit types named Medical Officer, Consultant, or a specialty
- A new meaning for **Special OPD**
- A Hospital EMR provider, specialty, clinic, or fee table
- A Follow-up **patient** category
- A Reception questionnaire for specialty history
- A second consultation-fee ledger
- New OpenMRS providers, visit types, or specialties from application code (those are hospital configuration)

---

### 9. Classification roll-up

| Item | Classification |
|---|---|
| Provider as the consulting doctor | **EXISTS AND WORKS** |
| OPD / Follow Up / Emergency / IPD as visit kinds | **EXISTS AND WORKS** |
| Consultation encounter (one type for all doctors) | **EXISTS AND WORKS** |
| Clinical consultation fee create → Accountant collect | **EXISTS AND WORKS** |
| Special OPD = retrospective entry | **EXISTS AND WORKS** |
| Special OPD = Consultant | Do not use |
| `practitioner_type` MO vs Consultant | **EXISTS BUT NOT CONFIGURED** |
| Provider-management roles | **EXISTS BUT NOT CONFIGURED** |
| Hospital specialties beyond General Medicine / ENT | **EXISTS BUT NOT CONFIGURED** |
| Appointment service / provider picker in Reception | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Per-doctor consultation amount | **MISSING** |
| MO vs Consultant in current provider data | **MISSING** |
| Whether Reception must route to a named consultant | **REQUIRES HOSPITAL DECISION** |
| Production consultation amounts (MO vs Consultant) | **REQUIRES HOSPITAL DECISION** |

---

### Tests (this investigation)

- `npm test`: **94 passed**
- `npm run build`: `dist/assets/index-IAXECGQs.js`
- No application code, OpenMRS, or Odoo data changed.

### STOP

This investigation stops here. Do not implement a Reception Medical Officer / Consultant picker, do not retarget Special OPD, do not create providers or specialties, and do not change the consultation-fee implementation until the hospital decides whether Reception must route and what the production fees are.

---

# Reception Phase 1 — capability and workflow audit

Date: **21 Aug 2026** (Africa/Lagos). **Investigation only.** (Historical. Phase 2 above is the implemented state.)

No UI, OpenMRS, Odoo, billing, Clinical, Laboratory, Pharmacy, Nursing, Radiology, configuration, or production data were changed. No new patients, visits, or invoices were created. Ordinary hospital patients were not modified. The dedicated TEST patient **ABIKAN E2E TEST PATIENT** `ABC200016` (`f242364e-b70f-4fec-b29e-8ad4fbe147b5`) was read only.

Related: `REGISTRATION_BILLING_IMPLEMENTATION.md`, `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `ABIKAN_USERS_ROLES_WORKPLACES.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`.

Status labels (exactly one per finding):

| Label | Meaning |
|---|---|
| **EXISTS AND WORKING** | Present and observed to work |
| **EXISTS BUT NOT CONFIGURED** | Software exists; settings or data are missing or mismatched |
| **EXISTS BUT NOT EXPOSED IN ABIKAN** | Bahmni/OpenMRS/Odoo has it; Hospital EMR does not show or write it |
| **COMING SOON** | Hospital EMR placeholder; no working path |
| **REQUIRES HOSPITAL DECISION** | Cannot proceed honestly without hospital input |
| **MISSING** | Not present in this installation |

Live checks: OpenMRS MySQL, REST, FHIR, departmental sessions (`reception.abikan`, `doctor.abikan`, others), Odoo XML-RPC. `npm test` and `npm run build` were run after this document; they do not write clinical or financial data.

---

## Executive summary

Reception in Hospital EMR is a **desk over OpenMRS patients/visits and Odoo registration invoices**. It is not a complete arrival desk.

What actually works today:

```
Search existing patient (name or hospital number)
  → open Reception patient screen
  → Start visit (OPD only, at hidden Registration Desk location)
  → Create registration fee (TEST product only)
  → send patient to Accountant to pay
  → Doctor can search the same patient
  → if the visit started today and is OPD / Special OPD / Follow Up,
    it also appears on Clinical Today's Patients
```

What does **not** work as a hospital arrival workflow:

- New registration is **Bahmni Registration SPA**, not a Hospital EMR form.
- Hospital EMR cannot choose visit type (Special OPD, Follow Up, Emergency, IPD) or location.
- There is **no** queue module. “Waiting” is “open visits that started today.”
- Reception **creates** a registration charge and **does not collect** payment.
- Consultation fees are created in **Clinical**, not Reception.
- Emergency is a real visit type but is **intentionally excluded** from Clinical Today's Patients.
- **0** visits started on 21 Aug 2026, so both Reception Today's Visits and Clinical Today's Patients were empty during this audit. The TEST patient still has an **open OPD visit from 19 Aug** at OPD-1; leftover open visits do not appear on either “today” list.

**Do not build** a second patient database, MRN system, visit store, encounter model, queue table, or payment ledger.

---

## 1. Current Reception navigation

**EXISTS AND WORKING** as a Hospital EMR department. Several items are search-focus or Bahmni hand-off, not native screens.

| Nav item | Route / action | What it actually does | Status |
|---|---|---|---|
| Dashboard | `#/reception` | KPIs + today's visit table + quick actions | **EXISTS AND WORKING** |
| Register Patient | dialog → Bahmni `/bahmni/registration/index.html#/patient/new?cardType=` | Leaves Hospital EMR | **EXISTS BUT NOT EXPOSED IN ABIKAN** (register is Bahmni) |
| Patients | `#/reception/patients` | Focuses header search; **same dashboard** | Not a patient directory |
| Today's Visits | `#/reception/visits` | Scrolls to today's visit table | **EXISTS AND WORKING** |
| Patient Accounts | action `search` | Focuses header search | **EXISTS AND WORKING** (then open account) |
| Aliases | `#/registration`, `#/registration-desk` | Same desk | **EXISTS AND WORKING** |
| Patient | `#/reception/patient/{uuid}` | Fee + start OPD visit | **EXISTS AND WORKING** |

Hidden session location for Reception: **Registration Desk**. Staff do not pick a room.

Bahmni home still has Registration (`app:registration`). Print card templates live under `abikan-config/openmrs/apps/registration/registrationCardLayout/`. Hospital EMR does not call them.

---

## 2. Current Reception capabilities

Do not treat a route or button as a working feature.

| Capability | In Hospital EMR? | Proof | Status |
|---|---|---|---|
| Dashboard | Yes | `RegistrationDeskWorkspace` | **EXISTS AND WORKING** |
| Patient search | Yes | Header `GET /patient?q=` | **EXISTS AND WORKING** |
| Search by name | Yes | `ABIKAN E2E` → ABC200016 | **EXISTS AND WORKING** |
| Search by MRN | Yes | `ABC200016` → 1 hit | **EXISTS AND WORKING** |
| Search by phone | Placeholder says “phone”; **0** `phoneNumber` attributes in the database; `q=080` → `[]` | **EXISTS BUT NOT CONFIGURED** (unproven) |
| Open existing patient | Yes | Select hit → `#/reception/patient/{uuid}` | **EXISTS AND WORKING** |
| Register new patient | Dialog only; save is Bahmni SPA | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Edit demographics | “Open patient file” → Bahmni | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Generate MRN | idgen source **ABC**, next **200017**; `idgen_auto_generation_option` is **empty**; config prefix **GAN** | **EXISTS BUT NOT CONFIGURED** |
| Create visit | **Start visit** → `POST /visit` type **OPD** only | **EXISTS AND WORKING** (OPD only) |
| Select visit type | No | **MISSING** in Hospital EMR |
| Select location | No; uses session location | **MISSING** in Hospital EMR |
| OPD | Default | **EXISTS AND WORKING** |
| Special OPD | Visit type exists; 0 live visits; not in Hospital EMR start | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Follow Up | Same | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Emergency | Visit type exists; 0 live visits; Clinical list excludes it | **EXISTS BUT NOT EXPOSED IN ABIKAN** + **REQUIRES HOSPITAL DECISION** |
| IPD / admission registration | IPD exists (3 visits); Nursing/ADT, not Reception start | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Queue | No `queue` / `queueentry` REST; no queue tables | **MISSING** |
| Patient account | Link on desk and patient screen | **EXISTS AND WORKING** (read) |
| Consultation fee | Clinical `ConsultationFeeCard` | **EXISTS AND WORKING** elsewhere; Reception **MISSING** (by design) |
| Other fees | Registration fee only | **EXISTS AND WORKING** (TEST product) |
| Collect payment | Explicitly no Pay button | **MISSING** (Accountant) |
| Referral | None | **MISSING** |
| Follow-up appointment | Appointments SPA exists; Reception **403**; Clinical Appointments tile Coming soon | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Print receipts | Patient Account / Accountant “Print receipt” | **EXISTS BUT NOT EXPOSED IN ABIKAN** as a Reception action |
| Print patient information / card | Bahmni print templates | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Individual vs Family card | Dialog labels only; sessionStorage + query param; **one** Odoo TEST product | **EXISTS BUT NOT CONFIGURED** |

KPI honesty:

| KPI | Source | Caveat |
|---|---|---|
| Today's Patients | Visits with `fromStartDate` = browser local today | Empty on 21 Aug (no visits started today) |
| Waiting / Active Visits | Subset of those still open | Not a waiting-room queue |
| New Patients | FHIR Patient `_sort=-_lastUpdated`, then filter date = today | Last-updated, not “first registered today” |
| Patient Accounts | Button “View” | Not a count |

Enter in the search box (without picking a hit) still forwards to **Bahmni find-patient** unless the workspace sets `hospitalNumberSearch` (Reception does not). Picking a typeahead hit stays in Hospital EMR.

---

## 3. Patient registration

Hospital EMR does **not** POST a patient. Register Patient opens Bahmni Registration.

### Bahmni form (config + live dictionary)

`abikan-config/openmrs/apps/registration/app.json`:

| Field | Config | Live OpenMRS | Status |
|---|---|---|---|
| Given / middle / family name | Middle shown; last name mandatory; letters-only patterns | `person_name` | **EXISTS AND WORKING** in Bahmni |
| Birth date / time | `showBirthTime: true` | `person.birthdate` | **EXISTS AND WORKING** |
| Sex | Standard person | `gender` | **EXISTS AND WORKING** |
| Identifier | `defaultIdentifierPrefix`: **GAN**; required type Patient Identifier | Live source is **ABC** `ABC`+sequence | **EXISTS BUT NOT CONFIGURED** (GAN vs ABC) |
| Phone | `primaryContact` **hidden**; pattern 8–10 digits starting 91 | Attribute `phoneNumber` searchable, **0** values stored | **EXISTS BUT NOT CONFIGURED** |
| Email | Additional information | Attribute exists, searchable | **EXISTS BUT NOT CONFIGURED** |
| Address | Hierarchy; `address1` ≥ 2 chars | Template is **State / District / Pin Code / City** (Indian layout) | **EXISTS BUT NOT CONFIGURED** for this hospital |
| Next of kin / relationships | `relationshipTypeMap` Parent/Doctor | Relationship types exist; **need live count** unused for most demo patients | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Extra attrs (caste, cluster, RationCard, familyIncome, landHolding, class default General) | Listed in app.json | **Those person_attribute_types are not on this server** (only phone, alt phone, email, local names) | **EXISTS BUT NOT CONFIGURED** |
| Second page | Nutritional Values, Fee Information (`REGISTRATION FEES` required obs) | Encounter type **REG**: **0** encounters. Fee obs is **not** an Odoo invoice | **EXISTS BUT NOT CONFIGURED** |

### What Hospital EMR saves vs displays

| Data | Saved by Hospital EMR? |
|---|---|
| Demographics, MRN, address, relationships | **No** — Bahmni/OpenMRS |
| Card type Individual/Family | sessionStorage + URL query only; **not** an OpenMRS field; **not** two prices |
| Registration fee | Hospital EMR API → Odoo after a visit exists |
| Visit | Hospital EMR can `POST /visit` OPD |

### MRN

- Type: **Patient Identifier** `d3153eb0-5e07-11ef-8f7c-0242ac120002` (required).
- Source: **ABC**, prefix `ABC`, next sequence **200017**, min length 4 (values look like `ABC200016`).
- `idgen_auto_generation_option`: **0 rows** — automatic generation is not wired in the idgen options table.
- Identifier index on `identifier` is **not unique**. Duplicate MRNs are possible at database level. Currently **0** duplicate identifier strings.

### Duplicates

OpenMRS will create two patients with the same name. There is no blocking similar-patient API on the path Hospital EMR uses (`GET /patient?q=`). Bahmni Registration historically warns on similar names; that is **Bahmni SPA**, not Hospital EMR, and was not re-tested with a new save (would create a patient).

Phone cannot be used as a duplicate key: **no phones stored**.

---

## 4. Patient search

| Path | Behaviour | Status |
|---|---|---|
| Hospital EMR header | `GET /openmrs/ws/rest/v1/patient?q=&limit=8` after 2 characters | **EXISTS AND WORKING** |
| Reception select | `openRegistrationPatient` | **EXISTS AND WORKING** |
| Submit without a hit | Navigates to Bahmni `/search` | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| FHIR recent list | Dashboard “new patients” | **EXISTS AND WORKING** (last updated) |
| Phone | Searchable attribute; no data; numeric stub search empty | **EXISTS BUT NOT CONFIGURED** |
| `bahmnicore/search/patient` | HTTP **404** | **MISSING** |

`reception.abikan` search of ABC200016: HTTP 200, 1 result.

---

## 5. MRN / identifier handling

| Item | Live | Status |
|---|---|---|
| Primary type GP | `bahmni.primaryIdentifierType` = Patient Identifier | **EXISTS AND WORKING** |
| Extra types | NULL | Unused |
| OpenMRS Identification Number / Old Identification Number | Present, not required | Unused by Hospital EMR |
| Display | `ABC200016 - ABIKAN E2E TEST PATIENT` | **EXISTS AND WORKING** |
| Generation | Sequence ABC exists; auto-option table empty; config says GAN | **EXISTS BUT NOT CONFIGURED** |

Hospital EMR does not allocate identifiers itself. Do not build a second MRN scheme.

---

## 6. Visit creation

### Hospital EMR Reception

```
POST /openmrs/ws/rest/v1/visit
{
  patient, visitType: OPD uuid 54f43754-…,
  location: session location uuid (Registration Desk),
  startDatetime: now
}
```

No stop datetime (open visit). No provider on the visit. No encounter created. No queue entry.

If an open visit already exists, **Start visit is hidden** (`visitUuid` from charge payload or any open visit). Reception will not start a second visit from this screen.

### Bahmni Registration

`defaultVisitType`: **OPD**. Visit type/location UI is the Bahmni second page, not Hospital EMR.

### Clinical

Doctor `startOpdVisit` is the **same OPD POST**, but session location is **OPD-1**. Clinical save requires an **open** visit whose start datetime is not in the future (`visitHasStarted`). Missing start does not block. Payload still sends `visitType: "OPD"` even if the visit were another type.

---

## 7. Visit types

Live `GET /visittype` (not retired):

| Name | UUID | Live visits (not voided) | Hospital EMR Reception create | Clinical Today's Patients |
|---|---|---|---|---|
| OPD | `54f43754-c6ce-4472-890e-0f28acaeaea6` | **22** | Yes | **Included** |
| IPD | `b7494a80-fdf9-49bb-bb40-396c47b40343` | **3** | No | **Excluded** (Nursing) |
| EMERGENCY | `493ebb53-b2bd-4ced-b444-e0965804d771` | **0** | No | **Excluded** (intentional product rule) |
| Special OPD | `f3185c75-2c8c-476a-bf95-c77e8bb42edd` | **0** | No | **Included** if created |
| Follow Up | `9772f68d-9fc5-4470-9b87-2b6139011cad` | **0** | No | **Included** if created |
| LAB VISIT | retired | — | — | — |

**14** visits are still open (including TEST ABC200016 OPD @ OPD-1 started **19 Aug 2026**). They are not “today’s” work on 21 Aug.

Emergency exclusion is **code**, not a missing visit type: `QUEUE_VISIT_TYPES = {opd, special opd, follow up}`. Whether Emergency should appear in Reception or Clinical is **REQUIRES HOSPITAL DECISION**.

---

## 8. Queue

| Check | Result | Status |
|---|---|---|
| OpenMRS Queue module REST | `/queue`, `/queueentry` → 404 | **MISSING** |
| Queue tables | None | **MISSING** |
| Appointments as queue | `GET /appointments` **403** for `reception.abikan` (no View Appointments). Admin can read appointments. | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| Reception “waiting” | Open visits that **started today** | Not a queue |
| Clinical Today's Patients | Same visit source, outpatient types only, Africa/Lagos day | **EXISTS AND WORKING** (empty on 21 Aug) |

**Do not invent a second queue.** If the hospital wants a waiting room, first decide whether visits-started-today is enough, or appointments, or a future queue module.

Reception cannot add/remove a queue ticket. Starting or ending a visit is the only status.

---

## 9. Fees

**CREATE CHARGE ≠ COLLECT PAYMENT.**

| Fee | Who creates | Who collects | Product | Status |
|---|---|---|---|---|
| Registration | Reception (`app:registration`) `POST …/registration/patient/{uuid}/charge` | Accountant | **Registration Fee — TEST** id 2389, **$50**, tax empty, shop Registration Desk | **EXISTS AND WORKING** (TEST only) |
| Consultation | Doctor | Accountant | Consultation Fee — TEST $75 | **EXISTS AND WORKING** in Clinical |
| Laboratory / Pharmacy / Radiology / Accommodation | Those desks | Accountant | Separate | Out of Reception |
| Bahmni `REGISTRATION FEES` obs | Registration second page | Nobody (not an invoice) | — | **EXISTS BUT NOT CONFIGURED** as billing |

Registration charge rules (unchanged this audit):

- Requires an OpenMRS visit belonging to the patient.
- Key `registration:{visitUuid}`. Duplicate POST reuses the sale order.
- Price from Odoo, not the browser. Individual/Family ₦2000/₦5000 in `registrationCharges.ts` are **not** billed (dialog does not even show the naira amounts).
- Currency: shop uses **Public Pricelist (USD)**. Laboratory is already NGN.
- Production tariff: **REQUIRES HOSPITAL DECISION** / accounting configuration.

Reception has **no** Pay button. `reception.abikan` POST accountant payment is **403** (prior security tests).

---

## 10. Patient accounts

| Item | Live | Status |
|---|---|---|
| Partner | OpenMRS uuid → `res.partner.uuid`; MRN → `ref` | **EXISTS AND WORKING** |
| TEST partner | id **22**, ABC200016 | Present |
| TEST registration lines | **0** (`registration:` prefix) | No registration fee on TEST |
| TEST other sales | S00021–S00025 (lab/pharmacy/consultation-style; not created this audit) | Pre-existing |
| Hospital EMR Patient Account | Reception may open (privilege `app:registration`) | **EXISTS AND WORKING** |
| Payment status on Reception patient screen | UNPAID / PAID from Odoo `payment_state` | **EXISTS AND WORKING** |

---

## 11. Payment handoff

```
Reception Create registration fee
  → Odoo sale.order + posted invoice (UNPAID)
  → Patient Account shows Registration outstanding
  → Accountant POST /accountant/payment
  → invoice PAID
  → Reception patient screen reads PAID
```

Proven on **Blessing Adeyemi** ABC200009 (17 Aug billing TEST): S00004 / INV/2026/00003 / PCSH1/2026/00003. **Not repeated** this audit.

Receipt numbers are Odoo payment/invoice names (`PCSH1/…`, `INV/…`). Print is Accountant / Patient Account, not Reception.

---

## 12. Clinical handoff

```
Reception search/open
  → Start visit (OPD @ Registration Desk)   [if no open visit]
  → Doctor Today's Patients  (if visit started today AND type OPD/Special OPD/Follow Up)
  → or Doctor search
  → Consultation chart
  → save blocked until visit start datetime ≤ now
```

| Check | 21 Aug proof |
|---|---|
| Search TEST patient | **Works** |
| Open TEST in Reception | Open OPD `6478a94e-…` @ **OPD-1** from 19 Aug still open |
| Start visit on TEST | Button **hidden** (open visit already exists). Not clicked |
| Clinical Today's Patients | HTTP 200, **0** patients (nothing started today) |
| Clinical search TEST | Same OpenMRS patient search; chart can open; visit already started so save is not blocked by future start |

Location of the visit is **not** filtered on the doctor list. An OPD started at Registration Desk **would** appear if it started today. Prior billing TEST used that pattern (Blessing @ Registration Desk).

Clinical does **not** require payment before save.

---

## 13. Accounting handoff

Documented and previously tested; not re-invoiced:

Reception creates charge → Accounts sees outstanding → Accountant collects → status returns.

Reception cannot collect. Doctor cannot collect. No new payment workflow is required.

---

## 14. Emergency / Special OPD / Follow-up

| Type | OpenMRS | Created from Hospital EMR Reception | Clinical today list | Live use |
|---|---|---|---|---|
| OPD | Yes | Yes | Yes | 22 visits |
| Special OPD | Yes | No | Yes (if created) | **0** |
| Follow Up | Yes | No | Yes (if created) | **0** |
| Emergency | Yes | No | **No** (excluded) | **0** |
| IPD | Yes | No | **No** | 3 |

Emergency workspace on Clinical Home is **Coming soon** (`app:emergency`). Reception does not open it.

This audit does **not** decide hospital policy. It reports: types exist; Hospital EMR only starts OPD; Clinical hides Emergency and IPD from the ordinary doctor list **on purpose**.

---

## 15. RBAC

Live sessions (`*:Admin123`). Privileges not changed.

| Role | Search | Register (Add Patients) | Edit demographics | Create visit (Add Visits) | Create registration charge | Collect payment | Open clinical chart / edit clinical |
|---|---|---|---|---|---|---|---|
| **Reception** `reception.abikan` / `registration.abikan` | Yes | Yes (Bahmni) | Yes (Bahmni SPA) | Yes (Hospital EMR OPD + Bahmni) | **Yes** | **No** | No Hospital EMR Clinical (`app:clinical` absent). Can open Patient Account |
| **Doctor** | Yes | **No** | No | Yes (Clinical Start OPD) | No | No | **Yes** |
| **Accountant** | Yes | **No** | No | **No** | **No** | **Yes** | No |
| **Nurse** | Yes | **No** | No | Privilege Add Visits exists; Hospital EMR Nursing does not register or start OPD from Reception | No | No | ADT/ward, not OPD consultation |
| **Pharmacy** | Yes | **No** | No | **No** | No | No | No |
| **Laboratory** | Yes | **No** | No | **No** | No | No | No |

`Abikan:Reception` and `Abikan:Registration` both inherit **Registration-App** (same intended rights). Preferred UI user: `reception.abikan`.

Appointments: Reception **403**. Doctor also lacked View Appointments in the earlier clinical-queue work.

---

## 16. Existing Bahmni / OpenMRS capabilities to reuse

| Capability | Reuse |
|---|---|
| `POST/GET /patient`, person, attributes, identifiers | Yes |
| idgen ABC sequence | Yes (after prefix/auto-gen is aligned) |
| `POST/GET /visit`, visit types, locations | Yes |
| Encounter types (Consultation, REG, ADMISSION, …) | Yes; do not invent |
| Bahmni Registration SPA | Current new-patient path |
| Bahmni print card HTML | Optional later; do not copy into a second print engine first |
| Appointments module | Later; needs privilege + product decision |
| FHIR Patient | Recent-registration KPI only |
| Odoo partner + Registration Desk shop + charge API | Yes |
| Accountant payment + Patient Account | Yes |

---

## 17. What Hospital EMR already exposes

- Reception dashboard and today's visits (started today).
- Header search → Reception patient.
- Start **OPD** visit when none is open.
- Create **registration fee** (TEST price) and show UNPAID/PAID.
- Link to Patient Account and Bahmni patient file.
- Honest copy: payment at Accountant.

---

## 18. What is missing

- Native Hospital EMR registration form (fields, next of kin, Nigerian address).
- Visit type and location choice at Reception.
- Special OPD / Follow Up / Emergency / IPD from Reception.
- Queue / waiting-room mechanism.
- Phone search with real phone data; duplicate blocking.
- Working automatic MRN (auto-generation option empty; GAN vs ABC).
- Production registration tariff (NGN) and Individual vs Family products.
- Reception print card / receipt.
- Appointments / referral / follow-up booking.
- REG encounter / Fee Information as billing (should stay unused).
- Emergency on Clinical Today's Patients (excluded by design until hospital says otherwise).
- Today's lists showing leftover **open** visits from previous days.

---

## 19. What should NOT be built

| Candidate | Verdict |
|---|---|
| New patient database | **No.** OpenMRS person/patient |
| New MRN system | **No.** idgen ABC |
| New visit database | **No.** OpenMRS visit |
| New encounter model | **No.** |
| New queue table in Hospital EMR | **No.** Reuse visits (and later appointments/queue module if the hospital chooses) |
| New payment system | **No.** Odoo + Accountant |
| Treating Bahmni REGISTRATION FEES obs as money | **No.** |

Preferred architecture remains: OpenMRS = patient/visit; Odoo = money; Hospital EMR = hospital UI.

---

## 20. Minimal hospital decisions required

Keep this short. The system cannot answer these:

1. **Which fields are mandatory** at first registration (phone? address? next of kin? photo)? Current Bahmni form still carries Indian extra fields that are not even in this dictionary.
2. **Which visit types does Reception actually start** — OPD only, or also Special OPD, Follow Up, Emergency, IPD?
3. **Should Emergency patients appear** on Clinical Today's Patients, on a separate Emergency desk, or both?
4. **Does Reception create the consultation fee**, or only the registration card fee (current: Clinical creates consultation)?
5. **Does Reception ever collect cash**, or always send the patient to Accountant (current: always Accountant)?
6. **How should “waiting” work** — visits started today is enough, or a real queue / appointments?
7. **Should a second patient with the same phone or similar name be blocked?**
8. **Real registration price** (and whether Individual vs Family are two tariffs). Currency NGN vs USD.

---

## 21. Recommended next implementation phase

Do **not** start with a new patient or visit engine.

Suggested order after this audit is reviewed:

1. Hospital answers §20 (especially visit types, Emergency, who bills consultation, mandatory fields).
2. Align MRN: ABC prefix in Bahmni config; idgen auto-generation option; stop advertising GAN.
3. Keep Bahmni Registration for demographics **or** replace with a small Hospital EMR form that POSTs the existing patient REST — one path, not two conflicting forms.
4. Reception visit start: allow the hospital-approved visit types (still OpenMRS `POST /visit`).
5. Production registration product/price in Odoo (reuse charge API). Keep payment on Accountant unless the hospital reverses that.
6. Only then: print card, appointments, or a waiting list — each as reuse, not a new database.

**TEST patient note:** ABC200016 already has an open OPD visit. Do not start another visit or create a registration charge on that patient unless a later isolated TEST explicitly says so.

---

## TEST patient trace (read-only, 21 Aug 2026)

| Step | Result |
|---|---|
| A. Search ABC200016 / ABIKAN E2E | **EXISTS AND WORKING** |
| A. Open record | Identity M, DOB 1990-01-15, no address, no phone |
| A. Create visit | **Not done** — open OPD already exists (19 Aug, OPD-1) |
| A. Clinical Today's Patients | Empty today; TEST not listed (visit did not start today) |
| A. Clinical search / chart | Patient exists; leftover open visit would allow save |
| B. New patient | **Not created** (existing TEST sufficient) |
| Financial writes | **None** |

---

## Classification roll-up

### EXISTS AND WORKING

- Reception dashboard, today's visit table, header search (name/MRN), open patient, OPD start visit, registration fee TEST path, Patient Account link, RBAC split vs Accountant/Doctor, Clinical visit list API, Odoo Registration Desk shop.

### EXISTS BUT NOT CONFIGURED

- MRN auto-generation option; GAN vs ABC prefix; phone attribute unused; Indian address template; extra Bahmni attributes absent; Individual/Family as two prices; production NGN tariff; REG / Fee Information obs.

### EXISTS BUT NOT EXPOSED IN ABIKAN

- Bahmni Registration create/edit/print card; visit types other than OPD; appointments; Special OPD/Follow Up create; print receipt from Reception.

### COMING SOON

- Clinical Appointments workspace; Emergency workspace.

### REQUIRES HOSPITAL DECISION

- Mandatory fields; visit types Reception uses; Emergency on Clinical list; who creates consultation fee; whether Reception collects money; queue vs visits; duplicate rules; real prices.

### MISSING

- OpenMRS queue module; native Hospital EMR registration form; phone-search proof; unique MRN constraint; leftover-open-visit “today” list; referral.

---

## STOP

This phase stops here. Do not implement Reception until this audit is reviewed.

Documentation path: `abikan-shell/docs/RECEPTION_CAPABILITY_AUDIT.md`
