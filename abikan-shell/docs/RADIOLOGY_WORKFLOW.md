# Hospital EMR radiology / imaging workflow

Source of truth: this Bahmni-standard deployment (OpenMRS 1.1.2, bahmnicore 1.2.0, pacsquery 1.4.0, dcm4chee 2.18.1-psql, pacs-integration 1.0.0), live **GET** probes, and read-only MySQL / PostgreSQL. No imaging orders, DICOM studies, or radiology reports were created during this investigation.

Do not invent a second radiology database. **dcm4chee** is the imaging archive and DICOM engine. **OpenMRS** is the clinical chart (orders, notes, document upload). **Hospital EMR** is the product UI around both. Do not rebuild a DICOM viewer.

Related: `docs/CLINICAL_WRITE_API.md` (how a doctor order is saved on a consultation). Radiology **writes** (placing imaging orders, fulfillment, report entry, DICOM upload) are **not** implemented in Hospital EMR.

Status labels used below:

- **CONFIRMED** — observed in this installation
- **UNKNOWN** — not established from source or live probes
- **COMING SOON** — Hospital EMR UI placeholder; no backend write

---

## Architecture (this installation)

```
Doctor consultation
  POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
  orders[]  (order type Radiology Order, optional urgency STAT)
        ↓
  OpenMRS order + encounter
  Atom feed  /openmrs/ws/atomfeed/encounter/recent
        ↓
  pacs-integration  (consumes encounter feed)
  Intended: HL7 ORM → dcm4chee modality worklist
        ↓
  Imaging performed at the modality
  Images stored in dcm4chee (PACS)
        ↓
  Viewer: Oviyam2  /oviyam2/oviyam?patientID={MRN}&accessionNumber={orderNumber}
  Archive UI: /dcm4chee-web3
        ↓
  Bahmni Orders app fulfillment  (Radiology Notes observation)
  and/or Document Upload encounter type RADIOLOGY
        ↓
  Doctor dashboard: radiology + radiologyOrders + pacsOrders
  Hospital EMR Radiology / Doctor chart  (OpenMRS reads)
```

This is the same principle as Laboratory: Hospital EMR reads OpenMRS; the departmental engine (here PACS) stays where it is.

**CONFIRMED:** there are currently **0** OpenMRS orders, **0** Radiology Notes obs, **0** RADIOLOGY encounters, **0** dcm4chee patients/studies/series/instances, **0** pacs-integration `test_order` / `order_details` rows, and **0** configured modalities.

---

## 1. Current Bahmni radiology architecture

**CONFIRMED**

| Piece | This deployment |
|---|---|
| dcm4chee | container `bahmni-standard-dcm4chee-1`, image `bahmni/dcm4chee:1.0.0` (dcm4chee-2.18.1-psql). Ports **8055** (web), **11112** (DICOM). AE title **DCM4CHEE** |
| PACS DB | postgres `pacs_db` / user `pacs_user` on `bahmni-standard-pacsdb-1` |
| pacs-integration | container `bahmni-standard-pacs-integration-1`, image `bahmni/pacs-integration:1.0.0`, DB `pacs_integration_db` |
| pacsquery module | `pacsquery-1.4.0.omod` (`pacsquery.started` = true) |
| Viewer | **Oviyam2** at `/oviyam2` → dcm4chee:8055. **OHIF is not installed** |
| Archive UI | `/dcm4chee-web3` → dcm4chee:8055 |
| Home white-label | tile **Radiology** → `/dcm4chee-web3` (must remain functional) |
| Home tile Radiology Upload | `../document-upload/?encounterType=RADIOLOGY&topLevelConcept=Radiology`, privilege `app:radiology-upload` |
| Orders app | `/bahmni/orders`, privilege `app:orders`, fulfillment **Radiology Order** |
| pacs-simulator | profile **not** running |

Login locations: Registration Desk, OPD-1, OPD-2, Emergency, General Ward, Pediatric Ward. **No Radiology login location.**

---

## 2. Existing radiology order flow

**CONFIRMED** (write path from clinical config and `CLINICAL_WRITE_API.md`; **no live orders exist**)

Doctor consultation saves:

```json
{
  "concept": { "name": "<concept-name>", "uuid": "<concept-uuid>" },
  "commentToFulfiller": "",
  "urgency": "STAT"
}
```

inside `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `orders[]`.

- Order type name: **Radiology Order**
- Order type UUID: `d3561dc0-5e07-11ef-8f7c-0242ac120002`
- Clinical `otherInvestigationsMap`: `"Radiology": "Radiology Order"`
- `enableRadiologyOrderOptions`: `["Urgent","NeedsPrint"]`
- Urgent maps to OpenMRS urgency **STAT**; otherwise the field is omitted (routine)

Where the order is stored: OpenMRS `orders` table (and the consultation encounter). **CONFIRMED 0 rows.**

Hospital-wide imaging queue: **not** on OpenMRS REST (`GET /order` getAll unsupported). Same limitation as Laboratory. Per-patient read:

```
GET /openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={uuid}&orderTypeUuid=d3561dc0-5e07-11ef-8f7c-0242ac120002
GET /openmrs/ws/rest/v1/bahmnicore/orders?orderUuid={uuid}
```

Live probe on John Adewale (`cbb26c0f-06bb-4252-aed9-fb461f0e9c15`): `[]` HTTP 200.

Concept class **Radiology/Imaging Procedure**: **255** concepts (do not hardcode names in the UI). Examples on this server include Chest x-ray, CT head/chest/abdomen, angiogram, bone scan.

---

## 3. OpenMRS integration

**CONFIRMED**

| Object | UUID / name |
|---|---|
| Order type Radiology Order | `d3561dc0-5e07-11ef-8f7c-0242ac120002` |
| Encounter type RADIOLOGY | `d3a89c59-5e07-11ef-8f7c-0242ac120002` |
| Encounter type Patient Document | `d3fafd5b-5e07-11ef-8f7c-0242ac120002` |
| Concept Radiology Notes | `ae6e5490-ade9-486e-8268-9e4efd45b07e` |
| Concept class Radiology/Imaging Procedure | 255 concepts |
| Concept class Image | 7 concepts; **0** obs |

Bahmni Clinical dashboard (`abikan-config/openmrs/apps/clinical/dashboard.json`):

- `radiology` display control
- `radiologyOrders` (`orderType`: Radiology Order)
- `pacs` / `pacsOrders` with Oviyam URL template (below)

Clinical extension **Pending Orders** requires privilege `app:radiologyOrders`.

---

## 4. Atomfeed / pacs-integration

**CONFIRMED**

`pacs-integration` `atomfeed.properties`:

- `openmrs.encounter.feed.uri=http://openmrs:8080/openmrs/ws/atomfeed/encounter/recent`
- Internal OpenMRS user `admin` (container credentials; not a Hospital EMR API)

Marker currently tracks that encounter feed.

Tables exist: `test_order` (order_uuid, test_name, test_uuid, order_number, comment, result, …), `order_details` (hl7_request, hl7_response, test_order_id), `modality` (name, description, ip, port, timeout), `order_type`.

Live counts:

- `test_order`: **0**
- `order_details`: **0**
- `failed_events`: **0**
- `modality`: **0**
- `order_type`: **0**

OpenMRS `event_records` category `lab` / title `radiology` is **catalogue**, not patient imaging orders.

**UNKNOWN:** the exact HL7 ORM mapping and failure mode when an order is created with an empty `modality` table. Empty modality is a **CONFIRMED** configuration gap: pacs-integration has nowhere to send ORM today.

Do not query `pacs_integration_db` or `pacs_db` from the Hospital EMR browser.

---

## 5. dcm4chee / DICOM

**CONFIRMED**

- AE: `DCM4CHEE` @ localhost:11112; also `CDRECORD` @ 10104
- **0** patients, **0** studies, **0** series, **0** instances, **0** MWL items in `pacs_db`
- Oviyam2 and dcm4chee-web3 both return HTTP 200 from inside the container

Imaging studies live in dcm4chee, not in OpenMRS. Do not copy DICOM files into Hospital EMR.

---

## 6. PACS viewer

**CONFIRMED**

Dashboard template (`dashboard.json` `pacs.dashboardConfig.pacsImageUrl`):

```
/oviyam2/oviyam?patientID={{patientID}}&accessionNumber={{orderNumber}}
```

- `patientID` is the **OpenMRS identifier (MRN)**, not the patient UUID
- `accessionNumber` is the **OpenMRS order number**
- Do not invent Study Instance UIDs

OHIF: **not present**.

Home white-label Radiology tile: `/dcm4chee-web3` (separate dcm4chee login). Must remain functional. Hospital EMR must not replace it.

Hospital EMR **Open Images** should use the Oviyam template **only** when a real MRN and order number exist. With zero orders, that action stays disabled.

---

## 7. DICOM study mapping / pacsquery

**CONFIRMED**

Java: `DicomStudiesQueryController` maps **GET** `/openmrs/ws/rest/v1/pacs/studies?patientId=&date=`.

Live:

```
GET /openmrs/ws/rest/v1/pacs/studies?patientId=ABC200012
→ HTTP 501
{"error":{"message":"PACS Server configuration is not defined"}}
```

Global property `pacsquery.pacsConfig` is **NULL**. Without it, C-FIND cannot run.

If configured, `SimpleImagingStudy` would expose: study UID, accession number, started, status, patient reference. Retrieve-tag GP (unset in practice until config exists): Study Date, Study Time, Modality, Study Instance UID, Placer Order Number, Accession Number, Requested Procedure Description.

`Dcm4cheServiceImpl` also contains the string **`patientId must be numeric`**. This installation’s MRNs look like `ABC200012`. **UNKNOWN** whether C-FIND would accept that identifier even after `pacsquery.pacsConfig` is set.

`GET /openmrs/ws/rest/v1/pacs` (without `/studies`) returns **Unknown resource** — that path is not the controller mapping.

Hospital EMR must not claim a live study list until `pacsquery.pacsConfig` is set and a real study exists.

There is no `#/radiology/study/{id}` route yet: there are no study identifiers to open.

---

## 8. Report storage

**CONFIRMED**

There is **no** structured radiologist report (Findings / Impression / Radiologist name) in OpenMRS or dcm4chee on this server.

Bahmni Orders app (`abikan-config/openmrs/apps/orders/app.json`):

- Fulfillment form concept: **Radiology Notes** (observation)
- Section title: “Radiology Order FulFillment Form”
- Privilege: `app:orders`
- Search: `emrapi.sqlSearch.activePatients` → `#/patient/{{patientUuid}}/fulfillment/Radiology Order`

Document upload (privilege `app:radiology-upload`): encounter type **RADIOLOGY**, top-level concept Radiology. This stores **uploaded files as OpenMRS documents**, not DICOM.

`VisitDocumentController`: `POST /rest/v1/bahmnicore/visitDocument` and `POST /rest/v1/bahmnicore/visitDocument/uploadDocument`. There is **no** working GET list on `v1/bahmnicore/visitDocument` (Unknown resource on GET).

Safe document **read**: `GET /openmrs/ws/rest/v1/encounter?patient={uuid}&encounterType=d3a89c59-5e07-11ef-8f7c-0242ac120002` → live `{"results":[]}`.

Radiology Notes obs: **0**. Image-class obs: **0**. RADIOLOGY encounters: **0**.

Do not invent Findings / Impression fields as live data. When Radiology Notes exist, show the observation text.

---

## 9. APIs discovered

| Method | Path | Result |
|---|---|---|
| GET | `/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid=&orderTypeUuid=d3561dc0-5e07-11ef-8f7c-0242ac120002` | HTTP 200 `[]` |
| GET | `/openmrs/ws/rest/v1/bahmnicore/orders?orderUuid=` | same service; used for order detail |
| GET | `/openmrs/ws/rest/v1/pacs/studies?patientId=` | HTTP **501** PACS configuration undefined |
| GET | `/openmrs/ws/rest/v1/pacs` | HTTP 404 Unknown resource |
| GET | `/openmrs/ws/rest/v1/encounter?patient=&encounterType=d3a89c59-…` | HTTP 200 `[]` |
| GET | `/openmrs/ws/rest/v1/bahmnicore/visitDocument?patientUuid=` | HTTP 404 Unknown resource |
| POST | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` | **write path** for future radiology orders — not called from Hospital EMR Radiology |
| POST | `/openmrs/ws/rest/v1/bahmnicore/visitDocument` | **write** — not called |

Patient identity, visits, and allergies use the same clinical reads as Doctor and Nursing.

---

## 10. Existing Bahmni source files

| Area | Location |
|---|---|
| pacsquery controller | `pacsquery-1.4.0.omod` `DicomStudiesQueryController` |
| pacsquery C-FIND | `pacsquery-api` `Dcm4cheServiceImpl`, `SimpleImagingStudy` |
| Visit documents | `bahmnicore-1.2.0.omod` `VisitDocumentController`, `BahmniPatientImageController` (`/rest/v1/patientImage`) |
| Orders SPA | `/usr/local/apache2/htdocs/bahmni/orders/orders.min.bbf3e60a.js` |
| Document upload SPA | `/usr/local/apache2/htdocs/bahmni/document-upload/document-upload.min.fff36055.js` |
| pacs-integration | container `bahmni-standard-pacs-integration-1` |

---

## 11. Relevant configuration files

| File | Role |
|---|---|
| `abikan-config/openmrs/apps/clinical/dashboard.json` | radiology, radiologyOrders, pacs/Oviyam URL |
| `abikan-config/openmrs/apps/clinical/extension.json` | `app:radiologyOrders` Pending Orders |
| `abikan-config/openmrs/apps/orders/app.json` | Radiology Notes fulfillment |
| `abikan-config/openmrs/apps/orders/extension.json` | Orders search → Radiology Order fulfillment |
| `abikan-config/openmrs/apps/home/extension.json` | Radiology Upload tile |
| `abikan-config/openmrs/apps/home/whiteLabel.json` | Radiology → `/dcm4chee-web3` |
| `abikan-config/openmrs/apps/documentUpload/extension-RADIOLOGY.json` | document upload privileges |
| pacs-integration `atomfeed.properties` | encounter feed consumer |
| GP `pacsquery.pacsConfig` | **NULL** — PACS C-FIND off |

Do not modify these files for this phase.

---

## 12. Authentication / session behaviour

**CONFIRMED**

- Hospital EMR uses the existing OpenMRS session cookie (`credentials: "include"`).
- Oviyam2 and dcm4chee-web3 are **separate web apps** on the dcm4chee container. Opening them may require a dcm4chee login. Hospital EMR must not pretend they share the OpenMRS session.
- pacs-integration talks to OpenMRS with its own `admin` feed credentials inside the Docker network.

---

## 13. Relevant permissions

Use existing privileges. **Do not create new ones.**

| Privilege | Use |
|---|---|
| `app:radiology-upload` | Home Radiology Upload tile; **Hospital EMR Radiology workspace gate** (`PRIVILEGES.radiology`) |
| `app:orders` | Bahmni Orders fulfillment |
| `app:radiologyOrders` | Clinical Pending Orders extension |
| `app:clinical:ordersTab` | Doctor Orders tab |

`abikan.admin` already has `app:radiology-upload`. Radiology is **location-independent** (no Radiology login location).

The Bahmni home Radiology (dcm4chee) tile and Radiology Upload application must remain functional.

---

## 14. What Hospital EMR can safely read

- Per-patient Radiology Orders via bahmnicore `orders`
- Single order via `orderUuid`
- Patient identity, visit, allergies (shared clinical APIs)
- RADIOLOGY encounters (document-upload encounters) — currently empty
- Radiology Notes obs — currently empty
- Honest PACS query failure (501 / unconfigured)
- Constructed Oviyam URL **only** from real MRN + order number

KPIs and the hospital work queue have **no** REST source. Show **—** / empty states.

---

## 15. What Hospital EMR will eventually need to write

**COMING SOON — do not implement in this phase**

- Place Radiology Order from Doctor consultation (`POST bahmniencounter` `orders[]`)
- Orders-app fulfillment (Radiology Notes)
- Document upload (`POST visitDocument`)
- Configuring `pacsquery.pacsConfig` and modalities (operations, not Hospital EMR product writes)

---

## 16. What is unsupported

- Hospital-wide imaging queue on OpenMRS REST
- Live PACS study list (`pacsquery.pacsConfig` unset; 0 studies)
- Structured Findings / Impression / Radiologist report model
- OHIF
- DICOM copy into Hospital EMR
- Radiology login location
- Hospital EMR writes of any kind in this phase
- `#/radiology/study/{id}` until a real study identifier exists

---

## 17. CONFIRMED vs UNKNOWN vs COMING SOON

### CONFIRMED

- Order type, encounter types, Radiology Notes concept, 255 imaging procedures
- Atomfeed encounter consumer in pacs-integration; empty modality table
- dcm4chee empty; Oviyam2 URL template; no OHIF
- GET bahmnicore orders (empty); GET pacs/studies → 501
- Privileges listed above
- Zero operational imaging data on this server

### UNKNOWN

- HL7 ORM success path with empty `modality`
- Whether C-FIND accepts non-numeric MRNs (`patientId must be numeric`)
- How Radiology Notes obs bind to a specific order in every fulfillment save
- Exact dcm4chee web login session vs OpenMRS cookie

### COMING SOON (Hospital EMR UI only)

- Scheduled / Awaiting Imaging / In Progress / Report Pending as **product** queue states (not backend enums today)
- Order imaging from Doctor
- Fulfill / write report from Radiology
- Open Images enabled by real order numbers
- Study detail route
- Hospital KPI counts

Live OpenMRS order existence is the only confirmed order status: **Ordered**. Do not present Scheduled / In Progress / Reported as backend truth.
