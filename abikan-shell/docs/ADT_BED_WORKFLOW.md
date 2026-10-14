# Hospital EMR ADT and bed workflow

Source of truth: the **installed** Bahmni ADT / bed-management UI, OpenMRS modules, configuration, live **GET** probes, and read-only MySQL on this deployment. No admissions, transfers, discharges, or beds were created during this investigation.

Do not invent a parallel ADT database. Hospital EMR must eventually call the same APIs Bahmni already uses.

Related: `docs/CLINICAL_WRITE_API.md` (consultation / disposition write). Disposition **Admit** is intent only. It is not admission and it is not bed assignment.

---

## Architecture (this installation)

```
Doctor consultation
  POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
  disposition.code = ADMIT
        ↓
  "To Admit" queue
  (SQL: obs "Admit Patient" AND visit has no ADMISSION encounter)
        ↓
  ADT / Bed Management UI  (nurse / ward clerk — privilege app:adt)
  chooses Ward → Room → Bed   (doctor does not pick the bed)
        ↓
  1) POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
     encounterTypeUuid = ADMISSION
     visitType = IPD (config defaultVisitType)
        ↓
  2) POST /openmrs/ws/rest/v1/beds/{bedId}
     { "patientUuid": "...", "encounterUuid": "..." }
        ↓
  Inpatient visit + visit attribute Admission Status = Admitted
  Bed status OCCUPIED
        ↓
  Nursing workspace / bed board
```

This diagram matches the installed Bahmni bed-management JavaScript (`createEncounterAndContinue` then `bedService.assignBed`). It does **not** match “doctor picks a bed”.

---

## Installed modules and UIs

| Piece | Where | Version / path |
|---|---|---|
| Bed Management module | OpenMRS | `bedmanagement-6.0.0.omod` |
| EMR API | OpenMRS | `emrapi-1.36.0.omod` |
| Bahmni Core | OpenMRS | `bahmnicore-1.2.0.omod` |
| Bahmni IPD (MAR / tasks) | OpenMRS | `bahmni-ipd-1.1.1.omod` |
| Classic ADT Angular app | `bahmni-standard-bahmni-web-1` | `/usr/local/apache2/htdocs/bahmni/adt/` |
| Bed Management Angular app | same | `/usr/local/apache2/htdocs/bahmni/bedmanagement/` |
| IPD micro-frontend | container `ipd` | `/usr/local/apache2/htdocs/ipd/` |
| Admin bed OWA | OpenMRS OWA | `/openmrs/owa/bedmanagement/admissionLocations.html` |

Home tile **Bed Management** (`abikan-config/openmrs/apps/home/extension.json`) points to `../bedmanagement/#/home` with privilege `app:adt`. That is the operational ADT UI on this site, not `/bahmni/adt`.

Config:

- `abikan-config/openmrs/apps/adt/app.json` — classic ADT (`defaultVisitType`: IPD, `maxPatientsPerBed`: 2, `enableIPDFeature`: true)
- `abikan-config/openmrs/apps/ipd/app.json` — IPD dashboard + ward list SQL
- `abikan-config/openmrs/apps/ipd/extension.json` — To Admit / Admitted / To Discharge queues → `#/bedManagement/patient/{{patientUuid}}`
- `abikan-config/openmrs/apps/admin/extension.json` — Admin → Beds OWA

---

## 1. Ward model

A **ward** is an OpenMRS **location** tagged `Admission Location`.

Tag UUID (live): `9f79d118-4449-4c6e-845c-58b61d70c0bc`.

`AdmissionLocationResource` will not run unless that tag exists. Error string in the class: `Server must be configured with a Location Tag named 'Admission Location'.`

### Live admission locations

`GET /openmrs/ws/rest/v1/admissionLocation` returned **three** wards (also tagged Login Location):

| Ward | UUID | totalBeds | occupiedBeds | bedLayouts |
|---|---|---|---|---|
| Emergency | `b5da9afd-b29a-4cbf-91c9-ccf2aa5f799e` | 0 | 0 | `[]` |
| General Ward | `8e6ad830-21be-488b-87af-5e480334342c` | 0 | 0 | `[]` |
| Pediatric Ward | `60864f46-e903-44b2-a59a-dd25d41eafbd` | 0 | 0 | `[]` |

Other locations tagged **only** `Admission Location` (not in that list):

- Emergency Ward, Test Ward (children of Emergency)
- General Ward Room-1, General Ward Room-2
- Pediatric Ward Room-1
- Child test (`aebebbe6-42ef-4cd4-89e6-41f3e4b4970f`)

Observed behaviour: the ward list API returns the login-capable admission locations, not every tagged room. Rooms are child locations intended to hold the bed grid.

Wards are **not** hardcoded as G01/P01. Bed numbers live on the `bed` table when beds exist.

---

## 2. Bed model

OpenMRS tables (module `bedmanagement`):

| Table | Role | Rows now |
|---|---|---|
| `bed` | Physical bed: `bed_number`, `status` (AVAILABLE / OCCUPIED), `bed_type_id`, uuid | **0** |
| `bed_type` | Required before creating a bed | **0** |
| `bed_location_map` | Places a bed (or an empty cell) on a location grid: row, column, optional `bed_id` | **3** |
| `bed_patient_assignment_map` | Patient ↔ bed ↔ encounter, with start/end | **0** |
| `bed_tag` / `bed_tag_map` | Optional tags on a bed | **0** |

The three `bed_location_map` rows are on **Child test**, rows 1–3, column 1, **`bed_id` NULL**. Those are empty layout cells, not beds. They do not appear on Emergency / General Ward / Pediatric Ward layouts.

### Objects

```
Location (ward or room, tag Admission Location)
  └── BedLocationMapping (row, column, optional bed)
        └── Bed (bedNumber, status AVAILABLE|OCCUPIED, bedType)
              └── BedPatientAssignment (patient, encounter, start, end)
                    └── Patient
```

`BedStatus` enum in Java: `AVAILABLE`, `OCCUPIED` only.

Occupancy is **stored** on the bed (`status`) and **also derived** as `occupiedBeds` / `totalBeds` on `AdmissionLocation`. `totalBeds` counts real `Bed` rows mapped to that location, not empty layout cells.

A patient has **one current assignment**: `unAssignPatientFromBed` ends current assignments; `assignPatientToBed` creates a new one and can end the previous (`prevAssignment` in `BedManagementServiceImpl`). Config `maxPatientsPerBed` is **2**, so a bed is allowed more than one occupant in this Bahmni config, but transfer still moves the patient by assigning a different bed.

After discharge, `BahmniDischargeController` calls `unAssignPatientFromBed` **before** saving the discharge encounter. The bed returns to `AVAILABLE`.

Bed numbers are **data in OpenMRS**, created through:

- Admin OWA `/openmrs/owa/bedmanagement/admissionLocations.html`, or
- `POST /openmrs/ws/rest/v1/bed`

They are not Bahmni JSON config.

---

## 3. Admission lifecycle

Two different “admits” exist. Mixing them is the usual product mistake.

### A. Doctor disposition — intent only

Same mechanism as consultation save:

`POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter`

with `disposition` on the **Consultation** encounter (not ADMISSION).

Live Disposition answers:

| Display | UUID | Bahmni code |
|---|---|---|
| Admit Patient | `d36dd2e4-5e07-11ef-8f7c-0242ac120002` | `ADMIT` |
| Discharge Patient | `d36e1435-5e07-11ef-8f7c-0242ac120002` | `DISCHARGE` |
| Transfer Patient | `d36e564b-5e07-11ef-8f7c-0242ac120002` | `TRANSFER` |
| Undo Discharge | `d5fe696d-5e07-11ef-8f7c-0242ac120002` | `UNDO_DISCHARGE` |

This does **not**:

- create an ADMISSION encounter
- start an IPD visit by itself
- assign a bed
- set visit attribute `Admission Status`

The patient then appears on **To Admit** if the visit is still open and has no ADMISSION encounter.

SQL handler `emrapi.sqlSearch.patientsToAdmit` (global property, live):

- open visit at `${visit_location_uuid}`
- obs coded **Admit Patient**
- visit **not** already having an encounter of type **ADMISSION**

### B. Real admission — ADT / bed management

Installed JS (`bedmanagement.min.6078b74d.js`):

1. Nurse must select a bed (`SELECT_BED_TO_ADMIT_PATIENT_DEFAULT_MESSAGE` if missing).
2. Optional visit-type check: if the current visit is not IPD and `hideStartNewVisitPopUp` is false, Bahmni may prompt to convert / start IPD (`defaultVisitType`: **IPD**).
3. `encounterService.create(getEncounterData(ADMISSION, visitTypeUuid))`  
   → **POST** `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter`  
   **same EncounterTransactionMapper / encounterService.create() as consultation.**
4. On success: `bedService.assignBed(bed.bedId, patientUuid, encounterUuid)`  
   → **POST** `/openmrs/ws/rest/v1/beds/{bedId}`

`getEncounterData` payload from the installed JS:

```json
{
  "patientUuid": "<patient-uuid>",
  "encounterTypeUuid": "<ADMISSION uuid>",
  "visitTypeUuid": "<IPD or current visit type uuid>",
  "locationUuid": "<session login location>",
  "observations": []
}
```

`observations` are optional ADT notes (`conceptName` **Adt Notes** in config) filtered to non-empty values. Provider is added by `encounterService.buildEncounter` the same way as consultation.

Encounter type **ADMISSION** (live): `d3785931-5e07-11ef-8f7c-0242ac120002`.

Visit type **IPD** (live): `b7494a80-fdf9-49bb-bb40-396c47b40343`.

After a successful ADMISSION encounter, EMRAPI’s admitted queue uses visit attribute:

- type: **Admission Status**
- value: **Admitted**

`emrapi.sqlSearch.admittedPatients` selects open visits with that attribute. It does **not** join the bed table. A patient can be “admitted” in the queue sense without a bed if step 2 failed; Bahmni UI always attempts bed assign immediately after the encounter.

Forward after admit (IPD config): `#` (stay). Classic ADT config forwards to the bed screen: `#/patient/{{patientUuid}}/visit/{{visitUuid}}/encounter/{{encounterUuid}}/bed`.

---

## 4. Transfer lifecycle

Installed JS `$scope.transferConfirmation`:

1. A **different** bed must be selected (`SELECT_BED_TO_TRANSFER_MESSAGE` if same bed / none).
2. `GET /openmrs/ws/rest/v1/beds/{newBedId}` — refuse if `patients.length` (occupied).
3. `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with `encounterTypeUuid` = **TRANSFER**.
4. `POST /openmrs/ws/rest/v1/beds/{newBedId}` `{ patientUuid, encounterUuid }`.

Encounter type **TRANSFER** (live): `d3873bd5-5e07-11ef-8f7c-0242ac120002`.

`BedManagementServiceImpl.assignPatientToBed` ends the previous assignment. The old bed becomes available when it has no remaining current assignments.

Doctor disposition **Transfer Patient** is again intent (To-transfer style queues are not a separate home tile here; transfer is done from the admitted patient in bed management).

---

## 5. Discharge lifecycle

Two layers again.

### Doctor / disposition intent

Disposition **Discharge Patient** on a consultation encounter. SQL `emrapi.sqlSearch.patientsToDischarge`:

- open visit at login location
- already has an **ADMISSION** encounter
- obs **Discharge Patient**
- **no** DISCHARGE encounter yet

This is “doctor requested discharge”, not the discharge itself.

### Actual discharge — ADT

Installed JS `$scope.dischargeConfirmation`:

`encounterService.discharge(getEncounterData(DISCHARGE))`

which is **not** `bahmniencounter`. It is:

**POST** `/openmrs/ws/rest/v1/bahmnicore/discharge`

Java: `BahmniDischargeController.discharge(BahmniEncounterTransaction)`:

1. `bedManagementService.unAssignPatientFromBed(patient)`
2. `bahmniEncounterTransactionService.save(transaction)`

So discharge **does** use the encounter-transaction object, on a **different** URL, and **unassigns the bed first**.

Encounter type **DISCHARGE** (live): `d37e03e0-5e07-11ef-8f7c-0242ac120002`.

Forward (ADT config): `#/patient/search`. IPD config: `#`.

There is **no** separate Bahmni state machine named “Discharge requested → Preparation → Ready → Discharged” in the backend. Those would be Hospital EMR UI states mapped onto:

| Hospital EMR-friendly label | Actual backend |
|---|---|
| Discharge requested | Disposition / obs Discharge Patient, no DISCHARGE encounter |
| Discharge preparation | Nursing documentation on the still-open IPD visit (not a coded ADT state) |
| Ready for discharge | Not a stored OpenMRS state on this server |
| Discharged | DISCHARGE encounter + bed unassigned; visit may still be open until ended |

Undo discharge: disposition code `UNDO_DISCHARGE`, encounter type DISCHARGE, only when `visitSummary.isDischarged()` and the visit is still open (`adt/extension.json` `bahmniAdtUndoDischarge`).

---

## 6. APIs

### Reads (safe; used / probed)

| Purpose | Method | Endpoint | Notes |
|---|---|---|---|
| Ward list + occupancy | GET | `/openmrs/ws/rest/v1/admissionLocation` | `ward`, `totalBeds`, `occupiedBeds` |
| Ward + layout | GET | `/openmrs/ws/rest/v1/admissionLocation/{uuid}?v=full` | adds `bedLayouts` |
| List beds | GET | `/openmrs/ws/rest/v1/bed` | empty `results` today |
| Bed / occupancy / patients | GET | `/openmrs/ws/rest/v1/beds/{bedId}` | `BedDetailsResource`; **GET all `/beds` is not supported** |
| Patient’s current bed | GET | `/openmrs/ws/rest/v1/beds?patientUuid={uuid}&v=full` | `bedService.getAssignedBedForPatient` |
| Bed for a visit (incl. after discharge) | GET | `/openmrs/ws/rest/v1/beds?patientUuid=&visitUuid=&s=bedDetailsFromVisit` | search handler `bedDetailsFromVisit` |
| Bed types | GET | `/openmrs/ws/rest/v1/bedtype` | empty today |
| Bed tags | GET | `/openmrs/ws/rest/v1/bedTag` | empty today |
| Visit summary (admitted / discharged) | GET | `/openmrs/ws/rest/v1/bahmnicore/visit/summary?visitUuid=` | `admissionDetails` / `dischargeDetails` |
| Disposition history | GET | `/openmrs/ws/rest/v1/bahmnicore/disposition/visitWithLocale?visitUuid=` | |
| To Admit / Admitted / To Discharge | GET | `/openmrs/ws/rest/v1/bahmnicore/sql?q=emrapi.sqlSearch.…` | needs session location (`${visit_location_uuid}`). Calling without that parameter 500s |
| Login locations | GET | `/openmrs/ws/rest/v1/location?tag=Login+Location` | |
| Locations tagged admission | GET | `/openmrs/ws/rest/v1/location?tag=Admission+Location` | 9 locations live |
| Encounter types | GET | `/openmrs/ws/rest/v1/encountertype` | includes ADMISSION, DISCHARGE, TRANSFER |
| Visit types | GET | `/openmrs/ws/rest/v1/visittype` | OPD, IPD, EMERGENCY, Follow Up, Special OPD |
| Open visits | GET | `/openmrs/ws/rest/v1/visit?includeInactive=false&location=` | Hospital EMR already uses this |

`GET /openmrs/ws/rest/v1/bedPatientAssignment` — list not supported (GET by uuid only).

`GET /openmrs/ws/rest/v1/ipd/wards…` — **not registered** as a REST resource on this instance (`Unknown resource: v1/ipd`). Controllers exist in `bahmni-ipd-1.1.1` (`IPDWardController` mapping `/rest/v1/ipd/wards`). Do not treat IPD ward stats as available until that path is confirmed in a later MAR/tasks investigation.

### Writes (documented from source — **not executed**)

#### Create bed (admin / setup, not nursing workflow)

| | |
|---|---|
| Endpoint | `/openmrs/ws/rest/v1/bed` |
| Method | POST |
| Java | `BedResource.create` |
| Required | `bedNumber`, `bedType`, `row`, `column`, `locationUuid` |
| Error | `Required parameters: bedNumber, bedType, row, column, locationUuid`; `Already bed assign to give row & column`; `Invalid bed type name` |

Bed type first: `POST /openmrs/ws/rest/v1/bedtype` with `name`, `displayName`.

Admission location layout: `POST` / `POST update` `/openmrs/ws/rest/v1/admissionLocation` (`setBedLayoutForAdmissionLocation(rows, columns)`).

**Do not call these until the hospital asks to configure beds.**

#### Assign / transfer bed

| | |
|---|---|
| Endpoint | `/openmrs/ws/rest/v1/beds/{bedId}` |
| Method | POST |
| Java | `BedDetailsResource.update` → `assignPatientToBed(patient, encounter, bedId)` |
| Required body | `{ "patientUuid": "<uuid>", "encounterUuid": "<uuid>" }` |
| Effect | Occupies bed, stores assignment linked to the ADMISSION or TRANSFER encounter |

`bedId` in the URL is the numeric bed id (`bed.bedId` in the UI), not only uuid. Uuid GET is also implemented (`getBedDetailsByUuid`).

#### Unassign (used by discharge)

Implemented as delete on `BedDetailsResource` and as `unAssignPatientFromBed` inside the discharge controller. Nursing UI should use **discharge**, not a raw unassign, for a real discharge.

#### Admit / transfer encounter

| | |
|---|---|
| Endpoint | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` |
| Method | POST |
| Same class path | `encounterService.create` → `BahmniEncounterTransaction` |
| Admit | `encounterTypeUuid` = ADMISSION |
| Transfer | `encounterTypeUuid` = TRANSFER |
| Optional | `visitTypeUuid` / `visitUuid`, `locationUuid`, `providers`, `observations` (Adt Notes) |

#### Discharge

| | |
|---|---|
| Endpoint | `/openmrs/ws/rest/v1/bahmnicore/discharge` |
| Method | POST |
| Java | `BahmniDischargeController` |
| Body | Same `BahmniEncounterTransaction` shape (`patientUuid`, `encounterTypeUuid` = DISCHARGE, `locationUuid`, `observations`, …) |
| Side effect | Unassign bed, then save encounter |

Doctor disposition continues to use **bahmniencounter**, not this URL.

---

## 7. Payloads (from installed JS / Java)

### Assign bed

```http
POST /openmrs/ws/rest/v1/beds/12
Content-Type: application/json

{
  "patientUuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "encounterUuid": "ffffffff-1111-2222-3333-444444444444"
}
```

`12` is `bedId` (integer). Response is `BedDetails` (`bedId`, `bedNumber`, `bedType`, `patients`, location).

### Admit encounter then assign

```http
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
```

```json
{
  "patientUuid": "<patient-uuid>",
  "encounterTypeUuid": "d3785931-5e07-11ef-8f7c-0242ac120002",
  "visitTypeUuid": "b7494a80-fdf9-49bb-bb40-396c47b40343",
  "locationUuid": "<session-location-uuid>",
  "providers": [{ "uuid": "<provider-uuid>" }],
  "observations": []
}
```

Then POST `/beds/{bedId}` with `patientUuid` + `encounterUuid` from the response (`response.data.patientUuid`, `response.data.encounterUuid`).

### Discharge

```http
POST /openmrs/ws/rest/v1/bahmnicore/discharge
```

```json
{
  "patientUuid": "<patient-uuid>",
  "encounterTypeUuid": "d37e03e0-5e07-11ef-8f7c-0242ac120002",
  "locationUuid": "<session-location-uuid>",
  "providers": [{ "uuid": "<provider-uuid>" }],
  "observations": []
}
```

Exact optional fields follow `encounterService.buildEncounter` (same as consultation). Do not POST this until a write increment is approved.

---

## 8. Relevant source files

| Role | Path |
|---|---|
| Bed management UI (admit/transfer/discharge + assignBed) | `/usr/local/apache2/htdocs/bahmni/bedmanagement/bedmanagement.min.6078b74d.js` |
| ADT UI (same shared services) | `/usr/local/apache2/htdocs/bahmni/adt/adt.min.0d2323fa.js` |
| Admit confirmation template | `.../bedmanagement/views/admitConfirmation.html` |
| ADT action buttons | `.../bedmanagement/views/adt.html` |
| `BedResource` / `AdmissionLocationResource` / `BedDetailsResource` | `bedmanagement-6.0.0.omod` |
| `BedManagementService.assignPatientToBed` | `bedmanagement-api-6.0.0.jar` |
| `BahmniDischargeController` | `bahmnicore-1.2.0` `org.bahmni.module.bahmnicore.web.v1_0.controller` |
| `BahmniDispositionController` | same (`/rest/v1/bahmnicore/disposition`) |
| Encounter transaction | same module as consultation (`BahmniEncounterController`) |
| IPD MAR / ward stats (later) | `bahmni-ipd-1.1.1` `IPDWardController`, `IPDMedicationAdministrationController`, `IPDScheduleController` |
| Queues | global properties `emrapi.sqlSearch.patientsToAdmit`, `.admittedPatients`, `.patientsToDischarge` |

Local copies used while investigating: `/tmp/bahmni-adt/`.

---

## 9. Permissions

App entry:

| Privilege | Used for |
|---|---|
| `app:adt` | Home Bed Management tile, ADT/IPD extensions, Hospital EMR `canOpenNursing` |
| `app:clinical` + `app:clinical:dispositionTab` | Doctor disposition tab |
| `app:admin` | Admin → Beds OWA |

Bed-management module privileges (live `privilege` table):

| Privilege |
|---|
| Assign Beds |
| Get Beds / Edit Beds |
| Get Bed Type / Edit Bed Type |
| Get Bed Tags / Edit Bed Tags |
| Get Admission Locations / Edit Admission Locations |

Admit / Transfer / Discharge buttons in the UI are wrapped with `show-if-privilege="Assign Beds"` (`Bahmni.IPD.Constants.assignBedsPrivilege`).

`abikan.admin` already has `app:adt` (from the earlier account setup). Nursing users will need `app:adt` and typically **Assign Beds** before Hospital EMR should expose write actions.

---

## 10. What Hospital EMR should display (now)

Safe reads only:

- Current login location as the working ward when it is an admission location
- Ward list + occupied/available/total from `GET /admissionLocation` (zeros are real)
- Bed board from `bedLayouts` when beds exist; otherwise **No beds configured**
- Open visits at the login location (already implemented)
- On a patient: identity, vitals, diagnoses, drug orders, allergies from the **shared** record
- Bed assignment only if `GET /beds?patientUuid=` returns one
- To Admit / Admitted / To Discharge **counts and lists** from the SQL handlers **once** called with a valid session location (do not fake them)
- Doctor disposition as recorded diagnoses/disposition history — not as a live ADT state

Do not display invented G01/P01 beds, occupancy 18/24, or MAR Given/Missed unless IPD medication-administration APIs are connected later.

---

## 11. What Hospital EMR should eventually write

When a write increment is approved, reuse Bahmni — do not add a new engine:

| Hospital EMR action | Call |
|---|---|
| Doctor Admit | Already specified: disposition on `POST bahmniencounter` |
| Confirm admission + assign bed | `POST bahmniencounter` (ADMISSION) then `POST /beds/{bedId}` |
| Transfer bed | `POST bahmniencounter` (TRANSFER) then `POST /beds/{newBedId}` |
| Discharge | `POST /bahmnicore/discharge` |
| Nursing vitals | Same `POST bahmniencounter` observations as Doctor (see clinical write doc) |
| MAR / nursing tasks | Bahmni IPD module (`/rest/v1/ipd/...`) — **not confirmed live** on this host; investigate in the MAR increment |
| Care plan / I/O / notes | Only after concept sets are confirmed (IPD dashboard config names Ward Nursing Note, Observation Sheet, Intake/Output concepts — many may be missing, same class of problem as Vitals concept set) |

Doctor remains responsible for **whether** to admit. Nursing / ADT remains responsible for **which ward and bed**.

---

## Current configuration (why the bed board is empty)

1. **Zero rows in `bed`.** No physical beds exist.
2. **Zero `bed_type`.** A bed cannot be created until a type exists (`BedResource`: required `bedType`).
3. Wards and rooms exist and are tagged `Admission Location`.
4. The only layout cells are three empty mappings on leftover location **Child test**, with `bed_id` NULL — not attached to General Ward / Pediatric Ward / Emergency.
5. Global property `bedmanagement.mandatory` = `false` (admission encounter can exist without a bed; Bahmni UI still requires selecting a bed to press Admit).
6. No ADMISSION / DISCHARGE / TRANSFER encounters on this database (only Consultation encounters were found).
7. Visit attribute type **Admission Status** exists; no visit currently has value `Admitted`.

### What must be configured before Hospital EMR can show a real bed board

Do this only when the hospital asks (separate, approved task):

1. Create at least one **bed type** (`POST /bedtype` or Admin OWA).
2. Decide whether beds sit on the **ward** or on **room** children (Bahmni’s UI uses ward → room → bed; rooms already exist).
3. Set a layout (rows × columns) on those locations.
4. Create beds with `bedNumber`, type, row, column, `locationUuid` (`POST /bed` or Admin → Beds).
5. Confirm `GET /admissionLocation/{uuid}?v=full` returns non-empty `bedLayouts` with `bedNumber` and `status`.

Do **not** hardcode G01/G02 in Hospital EMR. Consume `bedNumber` from OpenMRS.

---

## Nursing access to admitted patients

- App privilege: `app:adt`
- Location: a login location that is also an admission location (Emergency, General Ward, Pediatric Ward)
- Queues are **location-scoped** (`visit.location_id` = session location)
- Admitted patients are those with visit attribute Admission Status = Admitted, not merely “anyone in the hospital”
- The IPD micro-frontend (`enableIPDFeature: true`) is Bahmni’s nursing chart (vitals form, nursing note concepts, drug chart, nursing tasks). Hospital EMR’s Nursing workspace is the product UI for the same patients; it must not create a second chart

---

## What to build next

1. **Hospital decision:** configure real beds (types + layout + numbers) through Bahmni Admin OWA / REST — not in Hospital EMR code.
2. **Hospital EMR read:** To Admit / Admitted / To Discharge via `bahmnicore/sql` with the session location; current bed via `GET /beds?patientUuid=`.
3. **First write increment (later, approved):** admit = `bahmniencounter` ADMISSION + `POST /beds/{id}` after a bed exists.
4. **Then:** transfer and `POST /bahmnicore/discharge`.
5. **Separately:** IPD MAR (`bahmni-ipd` medication administration / slots) once those URLs are confirmed live.

Do not implement those writes in the same change as this document.
