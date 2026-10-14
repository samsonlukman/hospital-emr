# Hospital EMR clinical write API

Source of truth: the Bahmni Clinical JavaScript installed in `bahmni-standard-bahmni-web-1`, plus live GET probes against this OpenMRS. Writes described here were **not assumed**. Vitals write verification is recorded at the bottom of this file after a real POST.

Do not invent parallel OpenMRS endpoints. Do not POST raw `/obs` or `/order` for consultation data.

## Source files

| Role | Installed path |
|---|---|
| Constants, mapper, consultation save | `/usr/local/apache2/htdocs/bahmni/clinical/clinical.min.317054d3.js` |
| `encounterService`, `conditionsService` | `/usr/local/apache2/htdocs/bahmni/clinical/clinical.min.web.d0669adc.js` |
| Config | `abikan-config/openmrs/apps/clinical/app.json` |

Local copies used during investigation: `/tmp/bahmni-js/clinical.min.317054d3.js`, `/tmp/bahmni-js/clinical.min.web.d0669adc.js`.

## How Bahmni saves a consultation

1. `$scope.save()` runs `preSavePromise()`.
2. `ObservationFilter` strips empty observations.
3. `Bahmni.Clinical.EncounterTransactionMapper.map(...)` builds `encounterData`.
4. `encounterService.getEncounterType(programUuid, loginLocationUuid)` sets `encounterTypeUuid`.
5. `encounterService.create(encounterData)` → `buildEncounter()` then **POST** `bahmniEncounterUrl`.
6. After success, `conditionsService.save(...)` posts conditions separately.

`allowConsultationWhenNoOpenVisit` is `false`. An open visit is required.

Default visit type: `OPD`. Default encounter type global property: `Consultation`.

OPD-1 and OPD-2 have **empty** `location_encountertype` mappings, so the default Consultation encounter type is used.

## Authentication

- Bahmni UI: `JSESSIONID` cookie, `withCredentials: true`.
- Abikan: same-origin `credentials: "include"`.
- Session location cookie: `bahmni.user.location`.
- App privilege checked at Clinical start: `app:clinical`.
- Provider: `GET /openmrs/ws/rest/v1/provider?user={userUuid}`. `buildEncounter` adds `{ uuid }` to `providers` when missing.

## Date/time format

Existing visits on this server use `YYYY-MM-DDTHH:mm:ss.SSS+0000` (example: `2026-08-13T10:10:00.000+0000`).

---

## 1. Consultation transaction

| | |
|---|---|
| Endpoint | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` |
| Method | **POST** |
| Source | `encounterService.create` → `$http.post(Bahmni.Common.Constants.bahmniEncounterUrl, encounter)` |
| Related | `POST .../bahmniencounter/find`, `GET .../bahmniencounter/{uuid}`, `DELETE .../bahmniencounter/{uuid}?reason=` |

### Required identifiers

| Field | Source |
|---|---|
| `patientUuid` | Patient UUID |
| `visitUuid` | Open visit UUID (`consultation.visitUuid`) |
| `visitType` | `"OPD"` when no retrospective entry (`defaultVisitType`) |
| `encounterTypeUuid` | Consultation `d34fe3ab-5e07-11ef-8f7c-0242ac120002` |
| `locationUuid` | Login / session location |
| `encounterDateTime` | Consultation datetime |
| `providers` | `[{ uuid }]` |

### Payload shape (from `EncounterTransactionMapper.map`)

```json
{
  "patientUuid": "<patient-uuid>",
  "visitUuid": "<open-visit-uuid>",
  "visitType": "OPD",
  "encounterTypeUuid": "d34fe3ab-5e07-11ef-8f7c-0242ac120002",
  "encounterDateTime": "2026-08-13T22:00:00.000+0000",
  "locationUuid": "<session-location-uuid>",
  "providers": [{ "uuid": "<provider-uuid>" }],
  "observations": [],
  "bahmniDiagnoses": [],
  "orders": [],
  "drugOrders": [],
  "disposition": null,
  "encounterUuid": null,
  "extensions": { "mdrtbSpecimen": [] },
  "context": { "patientProgramUuid": null }
}
```

`buildEncounter` keeps only `concept.uuid`, `concept.name`, `concept.dataType` on each observation and nested `groupMembers`.

### Response (used by Bahmni UI)

Bahmni reads `saveResponse.data.encounterUuid` and `saveResponse.data.encounterType`.

A bare GET on `/bahmniencounter` without an id returns 404. That does not mean POST is missing.

### Errors

Do not show success unless HTTP 2xx. Surface `error.message` / `error.detail` from the OpenMRS JSON body.

---

## 2. Observations (vitals, notes)

Saved only as `observations[]` on the encounter POST.

After `stripExtraConceptInfo`, each observation is:

```json
{
  "concept": {
    "uuid": "5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "name": "Pulse",
    "dataType": "Numeric"
  },
  "value": 72,
  "voided": false
}
```

The configured Bahmni concept set named `Vitals` is **missing** on this server. Hospital EMR writes the individual CIEL concepts already used for read:

| UI | Concept UUID | `name` sent | dataType | Units | Absolute | Normal |
|---|---|---|---|---|---|---|
| Systolic | `5085AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Systolic blood pressure | Numeric | mmHg | 0–250 | 100–140 |
| Diastolic | `5086AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Diastolic blood pressure | Numeric | mmHg | 0–150 | 60–90 |
| Pulse | `5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Pulse | Numeric | beats/min | 0–230 | 60–100 |
| Temperature | `5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Temperature (C) | Numeric | C | 25–47 | 35–37.7 |
| Weight | `5089AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Weight (kg) | Numeric | kg | 0–250 | — |
| Height | `5090AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Height (cm) | Numeric | cm | 10–272 | — |
| SpO₂ | `5092AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Arterial blood oxygen saturation (pulse oximeter) | Numeric | % | 0–100 | ≥95 |
| Respiratory rate | `5242AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Respiratory rate | Numeric | /min | 0–99 | 12–18 |

BMI is calculated in the UI from height + weight. It is **not** written as an observation (no confirmed Vitals set / BMI write path on this server).

### Clinical notes concepts that exist

| Concept | UUID | dataType | Use |
|---|---|---|---|
| Consultation Note | `d37294c5-5e07-11ef-8f7c-0242ac120002` | Text | Free-text note on the same encounter |
| History of present illness | `1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text | HPI text |
| Chief complaint | `5219AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Coded | Do not treat as free text |

`History and Examination` concept set: **missing**. Do not invent new concepts for surgical history, medication history, or examination.

Read-back: `GET /openmrs/ws/rest/v1/obs?patient=&concept=` (already used by Hospital EMR).

---

## 3. Diagnoses — `bahmniDiagnoses[]`

Saved **inside** the encounter POST. Do not use `/bahmnicore/visit/diagnosis` (404 on this server).

Source: `EncounterTransactionMapper.map` copies `consultation.newlyAddedDiagnoses` into `bahmniDiagnoses[]`. Search is `diagnosisService.getAllFor` → `GET Bahmni.Common.Constants.bahmniapiConceptUrl` (`/openmrs/ws/rest/v1/bahmni/terminologies/concepts`) with `term` and `limit` (`emrapiDiagnosisLimit`, 20). Read-back is `diagnosisService.getDiagnoses` → `GET /openmrs/ws/rest/v1/bahmnicore/diagnosis/search?patientUuid=`.

`Diagnosis.isPrimary()` / `isSecondary()` compare `order` to `"PRIMARY"` / `"SECONDARY"`. Certainty UI options are `CONFIRMED` and `PRESUMED`. Hospital EMR writes coded diagnoses only (`certainty: "CONFIRMED"`).

Mapper fields for a new diagnosis:

```json
{
  "codedAnswer": { "uuid": "<concept-uuid>" },
  "order": "PRIMARY",
  "certainty": "CONFIRMED",
  "existingObs": null,
  "diagnosisDateTime": null,
  "diagnosisStatusConcept": null,
  "voided": false,
  "comments": ""
}
```

`order` is Bahmni diagnosis rank (`PRIMARY` / `SECONDARY`), not an orderable. Non-coded: `codedAnswer.uuid` omitted, `freeTextAnswer` set. `allowOnlyCodedDiagnosis` is `false`. Hospital EMR does not offer free-text diagnosis in this increment.

Search (live GET 200):

`GET /openmrs/ws/rest/v1/bahmni/terminologies/concepts?term=malaria&limit=20`

Returns `{ conceptName, conceptUuid, matchedName }[]`. No ICD/code field is present on this search response.

Also: `GET /openmrs/ws/rest/v1/bahmnicore/diagnosis/delete?obsUuid=` (delete). Privilege for delete: `app:clinical:deleteDiagnosis`.

---

## 4. Laboratory and radiology — `orders[]`

Saved **inside** the encounter POST. Mapper keeps new / revised / discontinued orders:

```json
{
  "concept": { "name": "<concept-name>", "uuid": "<concept-uuid>" },
  "commentToFulfiller": "",
  "urgency": "STAT"
}
```

`urgency` is `"STAT"` only when marked urgent; otherwise omitted.

| Order type | UUID |
|---|---|
| Lab Order | `d3560b17-5e07-11ef-8f7c-0242ac120002` |
| Radiology Order | `d3561dc0-5e07-11ef-8f7c-0242ac120002` |
| Drug Order | `131168f4-15f5-102d-96e4-000c29c2a5d7` |

`All_Tests_and_Panels` exists but `setMembers` is **empty**. Do not invent test names. Search real concepts (lab class / radiology imaging procedure). Downstream: Atomfeed → OpenELIS / pacs-integration.

Read: `GET /openmrs/ws/rest/v1/bahmnicore/orders?patientUuid=&orderTypeUuid=`, `GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults`.

After submit, show **Ordered**, not Completed.

---

## 5. Prescriptions — `drugOrders[]`

Saved **inside** the encounter POST via `Bahmni.Clinical.DrugOrder.createFromUIObject`.

```json
{
  "careSetting": "OUTPATIENT",
  "drug": { "uuid": "<drug-uuid>" },
  "orderType": "Drug Order",
  "dosingInstructionType": "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions",
  "dosingInstructions": {
    "dose": 1,
    "doseUnits": "Tablet(s)",
    "route": "Oral",
    "frequency": "Twice a day",
    "asNeeded": false,
    "administrationInstructions": "{\"instructions\":\"As directed\"}",
    "quantity": 10,
    "quantityUnits": "Tablet(s)",
    "numberOfRefills": 0
  },
  "duration": 5,
  "durationUnits": "Day(s)"
}
```

Exact `dosingInstructionType` class string is `Bahmni.Clinical.Constants.flexibleDosingInstructionsClass` in the minified bundle. Confirm against `GET /openmrs/ws/rest/v1/bahmnicore/config/drugOrders` before first prescription write.

Drug search (live): `GET /openmrs/ws/rest/v1/drug?q=para`.

Read: `GET /openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive?patientUuid=` and `GET /openmrs/ws/rest/v1/bahmnicore/drugOrders/active?patientUuid=`. Do not use unfiltered `GET …/drugOrders?patientUuid=` as the clinical list — it returns `[]` for patients who still have real orders.

---

## 6. Disposition

Saved as `disposition` on the encounter POST (`encounterData.disposition = consultation.disposition`).

Live **Disposition** concept answers (use these only):

| Display | UUID |
|---|---|
| Admit Patient | `d36dd2e4-5e07-11ef-8f7c-0242ac120002` |
| Discharge Patient | `d36e1435-5e07-11ef-8f7c-0242ac120002` |
| Transfer Patient | `d36e564b-5e07-11ef-8f7c-0242ac120002` |
| Undo Discharge | `d5fe696d-5e07-11ef-8f7c-0242ac120002` |

Bahmni codes: `ADMIT`, `DISCHARGE`, `TRANSFER`, `UNDO_DISCHARGE`.

There is **no** Refer or Follow-up disposition answer. Follow Up is a visit type. Do not present Refer / Follow-up as disposition values.

Admission indicates intent. Ward/bed assignment is ADT (`POST /openmrs/ws/rest/v1/beds/{bedId}`). This server currently has **0 beds**.

Read: `GET /openmrs/ws/rest/v1/bahmnicore/disposition/visitWithLocale?visitUuid=`.

Discharge action also has `POST /openmrs/ws/rest/v1/bahmnicore/discharge`.

---

## 7. Conditions (separate write)

After the encounter save:

| | |
|---|---|
| Endpoint | `/openmrs/ws/rest/emrapi/condition` |
| Method | **POST** |
| Source | `conditionsService.save` |

```json
[
  {
    "uuid": null,
    "patientUuid": "<patient-uuid>",
    "concept": { "uuid": "<concept-uuid>" },
    "conditionNonCoded": null,
    "status": "ACTIVE",
    "onSetDate": "2026-08-13",
    "endDate": null,
    "endReason": null,
    "additionalDetail": null,
    "voided": false,
    "voidReason": null
  }
]
```

Rows with `onSetDate === null` are skipped by Bahmni. History: `GET /openmrs/ws/rest/emrapi/conditionhistory?patientUuid=`.

---

## 8. Visit create / close

| Method | Path | Purpose |
|---|---|---|
| POST | `/openmrs/ws/rest/v1/visit` | Create visit (`patient`, `visitType`, `location`, `startDatetime`) |
| POST | `/openmrs/ws/rest/v1/bahmnicore/visit/endVisit?visitUuid=` | Close visit |
| GET | `/openmrs/ws/rest/v1/visit?patient=&includeInactive=false` | Open visits |

Visit types on this server: OPD `54f43754-c6ce-4472-890e-0f28acaeaea6`, IPD, EMERGENCY, Special OPD, Follow Up.

At investigation time every existing visit was already closed (`startDatetime == stopDatetime`). Saving a consultation requires starting an open OPD visit first.

---

## 9. What Hospital EMR must not do

- POST `/openmrs/ws/rest/v1/obs` for consultation vitals
- POST `/openmrs/ws/rest/v1/order` for lab/radiology instead of `orders[]`
- POST `/openmrs/ws/rest/v1/encounter` instead of `bahmniencounter`
- Use `/bahmnicore/visit/diagnosis`
- Invent NHIA, card type, Visit Token, or History and Examination concepts
- Claim a write works without a 2xx from the server

---

## 10. Write verification log

Filled in after a real POST. Empty means not verified yet.

| Date | Patient | Action | HTTP | Result |
|---|---|---|---|---|
| 13 Aug 2026 | ABC200012 John Adewale `cbb26c0f-06bb-4252-aed9-fb461f0e9c15` | `POST /visit` OPD at OPD-1 | 201 | Open visit `f1444134-45f3-4377-8c2a-e6831bf7b910` (`stopDatetime` null) |
| 13 Aug 2026 | Same | `POST bahmniencounter` Pulse 76 + Temp 36.8 | 200 | Encounter `d723ece0-9298-4435-93b9-5be2656a559c` type Consultation. Pulse obs `391bcaeb-d5c2-4b1b-ac34-a7a817e4b327` read back as 76, creator `abikan.admin` |
| 13 Aug 2026 | ABC200006 Tunde Bakare `c4d470dc-507c-41a2-a5ef-9903a6c4e4a6` | `POST /visit` OPD at OPD-1 | 201 | Open visit `df41f3a9-56d6-4269-be57-efc4eba6f4a2` |
| 13 Aug 2026 | Same | `POST bahmniencounter` bahmniDiagnoses Typhoid fever PRIMARY + Chronic Hypertension in Obstetric Context SECONDARY | 200 | Encounter `d9644ab0-442f-41ed-b60a-aa8ff7c90b31`. Read-back `diagnosis/search` returned both, no duplicate existingObs |
