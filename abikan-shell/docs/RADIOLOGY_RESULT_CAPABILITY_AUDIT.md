# Radiology Result & Reporting Capability Audit

Date: **24 Aug 2026** (Africa/Lagos). Investigation, development configuration of existing `radiology.abikan`, a **controlled Radiology Notes persist**, then the **Hospital EMR reporting UI**.

Related (not superseded): `RADIOLOGY_CAPABILITY_AUDIT.md`, `RADIOLOGY_WORKFLOW.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`.

Related (not superseded): `RADIOLOGY_CAPABILITY_AUDIT.md`, `RADIOLOGY_WORKFLOW.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`.

Status labels in §2:

| Label | Meaning |
|---|---|
| **EXISTS AND USED** | Present and observed with live data or a working staff path |
| **EXISTS BUT UNUSED** | Present (concept, table, app, privilege) with **zero** live use |
| **CONFIGURED BUT EMPTY** | App/config points at it; required data or settings are missing |
| **NOT CONFIGURED** | Software exists; a required setting is absent |
| **NOT AVAILABLE** | Not installed, or not reachable on this site |

Live checks: OpenMRS MySQL, REST as `radiology.abikan` / `doctor.abikan` / `admin.abikan`. ORD-6, ORD-14, ORD-15 and their invoices were **not modified**. Development added a provider and **Get Orders** on `Abikan:Radiology`, then created **ORD-16** + one synthetic Radiology Notes observation (see § Development Configuration and § Controlled Radiology Notes Persistence Test).

---

## 1. Current Workflow

What already happens:

```
Doctor (Hospital EMR Orders → Radiology)
  → Radiology Order on the selected visit’s Consultation
  → Radiologist opens the patient / request in Radiology Desk
  → Radiologist enters an order-specific NGN amount
  → Charge key radiology:{orderUuid} on Radiology Desk
  → Accountant collects payment
```

What does **not** happen after that:

- No scan is performed (PACS empty; no modalities).
- Payment is **not** a gate on performing or reporting.
- One **development** Radiology Notes row exists (ORD-16, synthetic TEST text). ORD-6 / ORD-14 / ORD-15 still have **0** notes. `fulfiller_status` remains NULL on those historical orders.

Live orders:

| Order | Patient | Visit | Encounter type | `fulfiller_status` | Notes obs |
|---|---|---|---|---|---|
| ORD-6 | ABC200007 | OPD | Consultation | NULL | 0 |
| ORD-14 | ABC200016 Visit #001 | OPD | Consultation | NULL | 0 |
| ORD-15 | ABC200016 Visit #002 | OPD | Consultation | NULL | 0 |
| ORD-16 | ABC200018 (new OPD visit) | OPD | Consultation | NULL | **1** (synthetic TEST) |

---

## 2. Radiology Results

| Capability | Status | Evidence | Reusable? |
|---|---|---|---|
| **Radiology Notes** concept | **EXISTS BUT UNUSED** | UUID `ae6e5490-ade9-486e-8268-9e4efd45b07e`, class Misc, datatype **Text**. **0** observations. | **Yes** — free-text report body |
| Radiology order fulfillment form (concept set) | **EXISTS BUT UNUSED** | Set `Radiology order fulfillment form` → `Summary` → **Radiology Notes** + **Diagnostic Images**. 0 obs on members. | **Yes** as the Bahmni result shape |
| Bahmni Orders fulfillment UI | **CONFIGURED BUT EMPTY** | `orders/app.json`: title “Radiology Order FulFillment Form”, section “Radiology Results”, `conceptNames: ["Radiology Notes"]`, `scope: "latest"`, `numberOfVisits: 2`. Privilege **`app:orders`**. Never used (0 notes). | **Yes**, if the hospital grants `app:orders` |
| Orders search → fulfillment | **EXISTS BUT UNUSED** for Radiology staff | `orders/extension.json` forwards to `#/patient/{uuid}/fulfillment/Radiology Order`. Requires `app:orders`. `radiology.abikan` does not have it. Only SuperAdmin / full-privilege admin users do. | After a permission decision |
| Diagnostic Images (complex Image) | **EXISTS BUT UNUSED** | UUID `4e7ac8d1-…`, class Image, datatype Complex, ImageUrlHandler. **0** obs. | Optional image attachment beside notes, not DICOM |
| **Radiology Report** concept | **EXISTS BUT UNUSED** | UUID `e41ef81f-…`, class Image. **0** obs. | Possible document-upload target; unused |
| **Radiology results** (CIEL 1392) | **EXISTS BUT UNUSED** | Finding / Text. **0** obs. Not referenced by the Orders fulfillment config. | Do not use unless the hospital chooses it over Radiology Notes |
| Form2 clinical forms | **NOT AVAILABLE** for radiology reporting | 17 published forms (Vitals, Malaria, etc.). **None** are a radiology report form. | No |
| RADIOLOGY encounter type | **EXISTS BUT UNUSED** | UUID `d3a89c59-…`. **0** encounters. | **Yes** for document-upload style files on a visit |
| Document-upload app | **CONFIGURED BUT EMPTY** | Home tile `../document-upload/?encounterType=RADIOLOGY&topLevelConcept=Radiology`, privilege `app:radiology-upload`. App HTTP 200. **0** RADIOLOGY encounters. Dictionary has **no** fully specified concept named `Radiology` (the query string name). | Privilege exists; concept name is a configuration gap |
| Patient Document encounters | **EXISTS BUT UNUSED** | Encounter type exists. **0** encounters. | Not the radiology report path |
| Observations (`obs`) | **EXISTS AND USED** for other chart data; **unused** for radiology reports | `obs.order_id` column exists (nullable). Radiology Notes query returns **0**. | **Yes** — this is the report store |
| Encounter + visit | **EXISTS AND USED** | All three live orders sit on **Consultation** encounters of an **OPD visit**. | **Yes** |
| FHIR DiagnosticReport | **EXISTS BUT UNUSED** | Tables present; **0** rows. FHIR R4 search for ABC200016: Bundle `total: 0`. | Do not introduce as a second store |
| DICOM studies | **CONFIGURED BUT EMPTY** | dcm4chee `patient/study/series/instance` = **0**. | Later; not required to store a written report |
| PACS query API | **NOT CONFIGURED** | Module `pacsquery-1.4.0` started. GP `pacsquery.pacsConfig` **NULL**. Direct OpenMRS: HTTP **501** `PACS Server configuration is not defined`. `radiology.abikan` gets HTTP **403**. | After operations set pacsConfig |
| dcm4chee process | **EXISTS AND USED** as software | Container up 23h. Archive UI `/dcm4chee-web3` HTTP 302 login. | Archive only; empty |
| Oviyam2 | **EXISTS BUT UNUSED** | `/oviyam2/` HTTP 200 (separate JBoss login). 0 studies to show. | Viewer only, after a study exists |
| OHIF | **NOT AVAILABLE** | `/ohif/` HTTP 404. No container. | No |
| pacs-integration / MWL | **NOT CONFIGURED** | `modality` 0, `order_type` 0, `test_order` 0, `mwl_item` 0, `failed_events` 0. Creating ORD-14/15 did not create a worklist row. | After modalities are configured |
| pacs-simulator | **NOT AVAILABLE** | Profile not running. | No |
| Radiology worklist (Hospital EMR) | **EXISTS AND WORKS** | Derived from OpenMRS Radiology orders + Radiology Notes + Odoo charges. No second order store. | This phase |
| Order fulfillment status | **EXISTS BUT UNUSED** | Column `orders.fulfiller_status`. All 3 live orders **NULL**. `order_action` = **NEW**. Accession number NULL (order number used instead). | Optional later; do not invent extra states |
| Completed / cancelled orders | **NOT AVAILABLE** as used workflow | No discontinued radiology orders. No COMPLETED/CANCELLED fulfiller values in use. | Schema can store them; nothing writes them today |

---

## 3. Order → Visit → Result Relationship

Actual OpenMRS shape on this install:

```
Patient
  → Visit                    (selected visitUuid — Hospital EMR already requires this)
    → Encounter              (Consultation for ordering; RADIOLOGY unused)
      → Radiology Order      (orders.encounter_id)
      → Observation          (obs.encounter_id; optional obs.order_id)
```

Proven on live TEST orders:

- The order does **not** store `visitUuid`. Visit is reached **only** through the encounter.
- ORD-14 → Consultation `5028d1c2-…` → Visit #001 `2857db49-…`.
- ORD-15 → Consultation `17aa6cac-…` → Visit #002 `a70cbb56-…`.

A result **can** be associated with all three of:

| Bind | How |
|---|---|
| Patient | `obs.person_id` / encounter.patient |
| Selected visit | encounter.`visit_id` (must be the **order’s** visit, not “latest visit”) |
| Radiology order | `obs.order_id` (column exists; **never populated** yet because there are no notes) |

Until this development configuration, `radiology.abikan` could **not** resolve an order UUID while saving (`Get Orders` missing). After the configuration below, ORD-16 proves Radiology Notes + `obs.order_id`. See § Controlled Radiology Notes Persistence Test.

Do **not** treat a patient-only notes list as “this visit’s result”. Notes saved on another visit would leak across Hospital EMR’s selected-visit rule.

Bahmni Clinical widgets that would *display* notes if any existed:

| Surface | Scope in config | Selected-visit safe? |
|---|---|---|
| Visit page `clinicalNotes` includes “Radiology Notes” | `scope: latest`, `numberOfVisits: 1` | Intended as **this visit** |
| Visit page `pacsOrders` | That visit’s Radiology Orders | **Yes** (orders, not reports) |
| Dashboard `radiologyOrders` / `pacs` | Last **4 visits** | Patient history, not selected visit |
| Orders fulfillment form | `scope: latest`, `numberOfVisits: 2` | **Not** selected-visit authoritative |

Hospital EMR Doctor **Radiology results** today calls `GET /obs?patient=&concept=Radiology Notes` **without** `visitUuid`. That is patient-level. The representation also omits `order`, so even if notes existed they would not show which order they belong to.

---

## 4. Radiology Permissions

Account: `radiology.abikan` / role **Abikan:Radiology** (inherits **Radiology-App**).

Live session privileges (REST), not granted in this audit:

| Privilege | Present? |
|---|---|
| `app:radiology-upload` | **Yes** |
| Get/Add/Edit Patients, Visits, Encounters, Observations | **Yes** |
| Get Concepts | **Yes** |
| `app:orders` | **No** |
| `app:clinical` | **No** |
| `app:radiologyOrders` | **No** |
| Get Orders / Add Orders | **Get Orders: Yes** (granted on `Abikan:Radiology` in development). **Add Orders: No**. `app:orders`: **No**. |

What that means in practice:

| Action | Currently possible? |
|---|---|
| Open Hospital EMR Radiology Desk | **Yes** (`app:radiology-upload`) |
| List imaging orders (`bahmnicore/orders`) | **Yes** (proven ORD-14/15) |
| Read selected visit + nested orders (`GET /visit/{uuid}`) | **Yes** |
| REST `GET /order/{uuid}` | **Yes** after Get Orders (ORD-14 returned 200 as `radiology.abikan`) |
| Set NGN price / create `radiology:{orderUuid}` charge | **Yes** (existing Hospital EMR API) |
| Collect payment | **No** (Accountant) |
| Open Bahmni Orders fulfillment | **No** — needs `app:orders` |
| Open Bahmni document-upload | **Yes** (privilege present; no successful uploads exist) |
| Create/update Radiology Notes via Bahmni Orders UI | **No** (no `app:orders`) |
| Create observations via REST in principle | Privilege **Add Observations** is present. Validation POSTs reached the API (400 / 200). **No Radiology Notes row was persisted.** Provider + `Get Orders` block a safe report write today. |
| Query PACS studies | **No** — 403 for this user; 501 for admin until `pacsquery.pacsConfig` is set |
| Bahmni Clinical Pending Orders | **No** (`app:radiologyOrders`) |

**Get Orders** is not required to *list* or *price* orders (existing Hospital EMR path). It **is** required to resolve `orderUuid` when saving Radiology Notes. Development granted Get Orders to `Abikan:Radiology` only.

**`app:orders`** is required for the **existing Bahmni result form**. Granting it is a **hospital configuration decision**. Do not grant it automatically.

---

## 5. Existing Bahmni Result Workflow

Bahmni already has a designed result path. It is **not in use**.

1. Staff with `app:orders` open **Orders** → patient → **Radiology Order** fulfillment.
2. The form is an observation form whose only configured concept is **Radiology Notes** (free text). The concept set also allows **Diagnostic Images** (file URL), but the app.json section names only Radiology Notes.
3. Saving would create OpenMRS observations (and typically an encounter). Intended display: Clinical visit notes + dashboard history.

It is **usable as a design**, not as a live hospital workflow:

- 1 synthetic Radiology Notes row (ORD-16). 0 image obs, 0 RADIOLOGY encounters. Historical ORD-6/14/15 still have 0 notes.
- Radiology staff cannot open the fulfillment app today.
- There is no structured Findings / Impression form. Free text is what exists.
- Form2 has no radiology report template.
- FHIR DiagnosticReport is empty and unused.

**Do not build a Hospital EMR reporting database.** OpenMRS already has:

| Needed field | Existing column / relation |
|---|---|
| Report text | `obs.value_text` on Radiology Notes |
| Report date | `obs.obsDatetime` |
| Author | `obs.creator` / encounter provider |
| Patient | encounter / person |
| Visit | `encounter.visit_id` |
| Radiology order | `obs.order_id` |

That is sufficient for a written report. Images (DICOM) are a **different** store (dcm4chee), currently empty.

---

## 6. Doctor Visibility

### Bahmni Clinical (`doctor.abikan` has `app:clinical`)

Would show reports **if any existed**:

- Visit: Radiology Notes inside “clinical notes”; PACS/order control for this visit’s imaging orders.
- Dashboard: last 4 visits of radiology orders + Oviyam links.

Would **not** show:

- Pending Orders tab (`app:radiologyOrders` missing).
- Live images (0 studies; Oviyam would open empty).

### Hospital EMR Doctor Workspace (selected visit)

| Shown today | Detail |
|---|---|
| Ordered examinations | **Yes** — visit-scoped list |
| Hospital scan names | **Yes** |
| Price / payment status | **Yes** — Price pending / Unpaid / Paid (from Odoo). If charge API fails: Ordered |
| Clinical order status (completed / resulted) | **No** — Study and Report columns are always **—** |
| Results / report text | **Empty state only** — “Results appear here when radiology records a report.” Source: patient-level Radiology Notes (0 rows) |
| Attachments / DICOM | **No** |

Doctor does not collect payment. Copy already says fees are paid at Accounts.

---

## 7. PACS / Imaging Infrastructure

| Piece | Current state |
|---|---|
| `bahmni-standard-dcm4chee-1` | Up. AE intended `DCM4CHEE@dcm4chee:11112` |
| `/dcm4chee-web3` | HTTP 302 to login. Separate dcm4chee session (not OpenMRS cookie) |
| Oviyam2 `/oviyam2` | HTTP 200. Separate JBoss session |
| Studies / series / instances / MWL | **0** |
| Modalities (`pacs_integration.modality`) | **0** |
| `pacsquery.pacsConfig` | **NULL** |
| `GET /openmrs/ws/rest/v1/pacs/studies` | **501** (admin); **403** (radiology.abikan) |
| OHIF | **Not installed** |
| pacs-simulator | **Not running** |

**This environment cannot receive, store, or display a real examination image today.** Written reports do not depend on PACS. Do not configure PACS in order to start reporting.

Hospital EMR “Open Images” is enabled only when MRN + order number exist; it still would open an empty viewer. Order workspace **Write report** is disabled Coming soon.

---

## 8. Hospital EMR Gap

### ALREADY EXISTS

- Doctor order on **selected visit** (Consultation `orders[]`).
- Radiology Desk can **see** those orders and **set NGN price**.
- Accountant payment via `radiology:{orderUuid}`.
- Radiology Notes **concept** and Bahmni fulfillment **config**.
- `obs` can hold text, date, author, encounter/visit, and optional `order_id`.
- Doctor empty state for results (read path exists; nothing to show).
- Radiologist privileges to **add observations and encounters** (privilege present; write path investigated below — not safe yet).
- Document-upload **privilege** and RADIOLOGY **encounter type**.

### MISSING

- Any live report (0 notes, 0 files, 0 DICOM).
- Hospital EMR **Write report** UI (button is Coming soon).
- Hospital-wide worklist.
- Structured report fields (Findings / Impression).
- FHIR DiagnosticReport content.
- OHIF.
- Payment-before-scan rule (not configured; do not invent).

### REQUIRES HOSPITAL CONFIGURATION

- Whether Radiology staff receive **`app:orders`** to use Bahmni fulfillment, **or** Hospital EMR writes the same Radiology Notes observation.
- Whether **Get Orders** is ever granted (not required for the existing list/price path).
- Document-upload `topLevelConcept=Radiology` — **no dictionary concept with that exact name**.
- PACS: `pacsquery.pacsConfig`, modalities, MWL — **later**, not a reporting blocker.
- Whether `fulfiller_status` should be set (Completed / Received, etc.). Nothing sets it now.

### REQUIRES ABIKAN UI

If the hospital keeps results in OpenMRS (recommended):

1. Radiologist: enter **Radiology Notes** for a **specific order** on the **order’s visit** (not a new database).
2. Doctor: show those notes **scoped to the selected visit**, bound to the order — not a patient-wide dump.
3. Do not enable PACS/Oviyam as if images exist.

Do **not** require Hospital EMR UI if the hospital instead grants `app:orders` and uses Bahmni fulfillment — then Hospital EMR only needs a **visit-safe read**.

---

## Add Observations Write Capability

Investigation date: **24 Aug 2026**. No Radiology Notes observation was created. No report UI. No new API, concept, table, privilege, or `app:orders`. Payment is **not** a prerequisite for reporting.

### Existing Write Path

Hospital EMR already writes clinical observations through **one** endpoint:

| | |
|---|---|
| Endpoint | `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` |
| Used for | Vitals, Chief complaint, HPI, Consultation Note, diagnoses, lab/radiology **orders**, prescriptions |
| Code | `saveConsultation` → `buildConsultationPayload` in `src/services/openmrs/clinicalEncounter.ts`; notes/HPI in `clinicalDocumentation.ts`; radiology **orders** in `server/patient-account/radiology.py` `create_radiology_orders` |
| Staff docs | `docs/CLINICAL_WRITE_API.md` — do **not** POST raw `/obs` or `/encounter` for consultation data |

Payload fields that already exist:

```
patientUuid, visitUuid, encounterTypeUuid (Consultation d34fe3ab-…),
locationUuid, providers: [{ uuid }], encounterUuid?,
observations[], bahmniDiagnoses[], orders[], drugOrders[]
```

Each observation today:

```
{ concept: { uuid, name, dataType }, value, voided, uuid? }
```

`EncounterObservation` in Hospital EMR does **not** currently send `orderUuid`. Bahmni EMR-API **does** accept it: `EncounterTransaction.Observation.orderUuid` → `ObsMapper.getOrderByUuid` → `obs.setOrder`. Pharmacy already documents this for the Dispensed boolean obs (`{ value, orderUuid, concept.uuid }` on the same POST).

Raw OpenMRS:

| Endpoint | What we learned without persisting a report |
|---|---|
| `POST /openmrs/ws/rest/v1/obs` | Allowed by HTTP method. Empty body **400** (missing `obsDatetime`, `person`, `concept`) — **not 403**. `order` is a **creatable** REST property (`ObsResource1_8.getCreatableProperties`). |
| `POST /obs` with `person` + Radiology Notes concept | **400** for `radiology.abikan`: `Privileges required: Get People` while converting `person`. This account has **Get Patients**, not **Get People**. |
| `POST /bahmnicore/bahmniencounter` `{}` | HTTP **500** (empty body). |
| `POST /bahmnicore/bahmniencounter` with `patientUuid` + `visitUuid` + Consultation type, **no** `encounterUuid`, **no** providers, empty `observations` | HTTP **200** — **creates a new Consultation** on that visit. |

Conclusion: the existing write mechanism to reuse is **bahmniencounter `observations[]`**, not a new API and not raw `/obs` (blocked for this user by **Get People**). Privilege **Add Observations** is real (requests reach validation / save). Privilege alone does **not** make a Radiology Notes report safe.

### Radiology Notes Concept

Unchanged. Not created or edited.

| Field | Value |
|---|---|
| Fully specified name | Radiology Notes (also SHORT) |
| UUID | `ae6e5490-ade9-486e-8268-9e4efd45b07e` |
| Datatype | **Text** (free text) |
| Class | Misc |
| Set? | No (leaf) |
| Retired | No |
| Live observations | **0** |
| Intended as an observation | **Yes** — Bahmni Orders fulfillment `conceptNames: ["Radiology Notes"]`; member of concept set **Summary** `cf1844e6-…` → parent **Radiology order fulfillment form** `2e820990-…` (with Diagnostic Images) |
| Used anywhere today | Config only (`orders/app.json`, Clinical visit widget). **0** obs. |

Suitable as the report body. Do not invent a second concept.

### Encounter Requirement

A Radiology Notes observation **must** sit on an encounter. Visit is reached only through that encounter.

| Option | Evidence | Safe for selected visit? |
|---|---|---|
| **Existing Consultation that already holds the Radiology Order** | ORD-14 → Consultation `5028d1c2-…` → Visit #001 `2857db49-…`. ORD-15 → Consultation `17aa6cac-…` → Visit #002 `a70cbb56-…`. | **Yes**, if that encounter’s `visit_id` is the selected visit |
| New Consultation on the **same** `visitUuid` (omit `encounterUuid`) | Validation POST as `radiology.abikan` created encounter `a7e59ed8-…` on Visit #001, 0 obs, 0 providers, creator `radiology.abikan`. **Voided immediately** (`void_reason`: Investigation probe rollback). ORD-14 still on encounter `5028d1c2-…`. | Visit-bound, but **pollutes** the visit with an extra empty Consultation. Do not use this as the write pattern. |
| New **RADIOLOGY** encounter | Type exists (`d3a89c59-…`). **0** live rows. Creating one would be a persist. | Not required. Do not introduce it for notes. |
| LAB_RESULT | Used by OpenELIS lab obs with `order_id`. Not a radiology path. | No |

**Safest existing place:** the **Consultation encounter of the selected visit that already contains the Radiology Order**. Send `visitUuid` **and** that `encounterUuid`. Do **not** create an encounter when saving a report.

Hospital EMR `saveConsultation` already does this when `encounterUuid` is set. Omitting it creates a new Consultation (proven).

### Order Binding

Schema: `obs.order_id` nullable. REST representation field: `order` (uuid, orderNumber, encounter, …).

Live proof (lab, not radiology):

| Obs UUID | Concept | `order` UUID | Order | Encounter type |
|---|---|---|---|---|
| `a7e41d80-b03f-4031-abdb-dc3af2f97964` | Malarial smear | `a915d836-e429-4443-afc1-5401f16f037c` | ORD-9 | LAB_RESULT |

Write mapping in installed EMR-API 1.36 (`ObsMapper.mapObservationProperties`):

1. Observation JSON includes `orderUuid` (non-empty).
2. `OrderService.getOrderByUuid(orderUuid)` — annotated **`@Authorized("Get Orders")`**.
3. `obs.setOrder(order)` → `obs.order_id`.

Read mapping: `ObservationMapper` copies `obs.getOrder().getUuid()` back to `orderUuid`.

`GET /obs?order={orderUuid}` returns **0** even as `admin.abikan` for ORD-9. REST `ObsResource1_8.doSearch` only handles `patient`, then `encounter`, then `q`. The `order` query parameter is **not implemented**. Do not use it.

`GET /obs/{uuid}?v=full` **does** return nested `order` (proven as `radiology.abikan` on the lab obs). `GET /visit/{visitUuid}` nested `encounters.obs.order` is present (Consultation Note / HPI on ORD-14’s visit had `order: null`, as expected).

Radiology Notes + `order_id` has **never been persisted**. The API can populate it **only if** the writer can call `getOrderByUuid`. `radiology.abikan` has **no Get Orders** (`GET /order/{uuid}` is already 403). **Do not invent a custom order-reference field.**

### Visit Binding

Guaranteed **if and only if** the observation’s encounter belongs to the selected `visitUuid`.

| Mechanism | Selected-visit safe? |
|---|---|
| `POST bahmniencounter` with **both** `visitUuid` and the order’s `encounterUuid` | **Yes** |
| `POST bahmniencounter` with only `visitUuid` | Lands on that visit, but **creates another Consultation** (proven). Unsafe as a pattern. |
| `GET /obs?patient=&concept=Radiology Notes` (current `fetchRadiologyNotes`) | **No** — patient-wide. Representation omits `order` in the Hospital EMR query. |
| `GET /obs?encounter=` | Returns **all** obs on that encounter; `concept` was **ignored** (ORD-14 Consultation returned HPI + Consultation Note when `concept=Radiology Notes`). Filter in Hospital EMR. |
| `GET /visit/{selectedVisitUuid}` nested obs with `concept` + `order` | **Yes** — radiology user can already GET this visit. Filter: concept UUID + order UUID. |

Do **not** recommend latest note, first open visit, billed visit, or patient-only retrieval.

### Radiology Role

Account `radiology.abikan` (user `6d76e166-…`, person “Radiology Staff”, role **Abikan:Radiology**). Privileges **not** changed.

| Action | Result |
|---|---|
| Add Observations / Edit Observations | **Yes** (privilege). Empty `/obs` POST is 400, not 403. |
| Add Encounters / Edit Encounters | **Yes**. Empty bahmniencounter on a real visit **created** a Consultation (then voided). |
| Attach obs to an encounter | **Yes in principle** via bahmniencounter `observations[]` + `encounterUuid`. Not proven with Radiology Notes text. |
| Attach obs to an order (`orderUuid`) | **Blocked** — `Get Orders` **No**. EMR-API looks up the order with `OrderService.getOrderByUuid`. |
| Read an observation | **Yes** (`Get Observations`). Nested `order` on a known obs UUID works even without Get Orders. |
| Create / update via Bahmni Orders UI | **No** — no `app:orders`. Not granted. |
| Provider for bahmniencounter | **`GET /provider?user={radiology user}` → `results: []`**. No OpenMRS provider. |
| `Get People` | **No** — raw `POST /obs` cannot resolve `person`. |
| `Get Patients` / `Get Visits` / `Get Encounters` / `Get Concepts` / `Get Providers` | **Yes** |
| Delete Encounters | Privilege **No**; REST `DELETE` of the probe encounter still **voided** (HTTP 204) under Edit Encounters. |

Hospital EMR `fetchProviderUuidForUser` / `saveConsultation` **require** `providers: [{ uuid }]`. Without a provider row they throw *“This account is not set up as a clinician.”* The Bahmni API accepted **empty** `providers` (probe encounter). Author would then be **creator** only.

`doctor.abikan` **has** provider `17dec510-ef20-4282-9d9e-4d33d4693675`, plus Get Orders and Get People. That is why consultation writes work for doctors.

### Existing Hospital EMR Observation Infrastructure

| Piece | Reuse? |
|---|---|
| `POST bahmniencounter` + selected `visitUuid` + existing Consultation `encounterUuid` | **Yes** — same as vitals / HPI / notes / radiology **order** create |
| Observation shape `{ concept: { uuid, name, dataType: "Text" }, value }` | **Yes** — same as Consultation Note / HPI |
| `orderUuid` on the observation | **Must add to the payload**; type `EncounterObservation` does not include it yet. Not a new HTTP API. |
| `fetchProviderUuidForUser` | **Yes, after** hospital creates a provider for `radiology.abikan` |
| `fetchRadiologyNotes(patientUuid)` | **Do not reuse as-is** — patient-level, omits visit and (in the query) `order` |
| Visit GET nested obs (already used for Doctor documentation) | **Yes** — visit-safe read |
| New Hospital EMR reporting table / new OpenMRS concept | **No** |

### Safe Report Storage Model

Supported by schema + EMR-API + lab analogue. **Not** proven with a Radiology Notes persist. **Not** currently writable by `radiology.abikan` with order binding.

Intended OpenMRS row (do not build a parallel store):

| Field | Source |
|---|---|
| Concept | Radiology Notes `ae6e5490-…` |
| Value | Report text (`value_text`) |
| Encounter | Consultation of the **selected** visit that owns the order |
| `obs.order_id` | Radiology Order UUID via observation `orderUuid` (**requires Get Orders** for the writer) |
| Patient | Encounter / person |
| Visit | `encounter.visit_id` |

If Get Orders is never granted, `order_id` **cannot** be populated through the existing API. Do not work around that with a comment, extra concept, or Hospital EMR table. That is a **hospital permission decision**.

### Result author

Consultation today: logged-in Hospital EMR user → OpenMRS user → **provider** on the encounter.

| Stamp | Automatic? | Enough for a report? |
|---|---|---|
| `obs.creator` / `auditInfo.creator` | Yes (probe encounter creator = `radiology.abikan`) | Identifies the OpenMRS user |
| Encounter `providers` | Only if a provider UUID is sent | Missing today for Radiology |
| `obs.obsDatetime` | Bahmni sets “now” when omitted | Report time |
| `encounterDatetime` | Set on the Consultation | Existing encounter clock; do not replace the order encounter’s date just to timestamp a report |
| `dateCreated` | Yes | Audit |

Reuse the **same provider mapping** (`GET /provider?user=`). Do **not** create a Radiologist identity table. Hospital must **create an OpenMRS provider** linked to `radiology.abikan`. This investigation did not create one.

### Report date

OpenMRS already records observation datetime, creator, and encounter datetime. No custom date field is required.

### Doctor Read Path

**Do not implement yet.** Existing APIs:

| API | Visit + order safe? |
|---|---|
| `GET /visit/{selectedVisitUuid}?v=custom:(uuid,patient:(uuid),encounters:(uuid,encounterType,obs:(uuid,concept:(uuid,display),order:(uuid),value,obsDatetime)))` then keep rows where concept = Radiology Notes **and** `order.uuid` = the Radiology Order | **Yes**, if `order_id` was set on write. `radiology.abikan` and `doctor.abikan` can GET visits. |
| `GET /obs?patient=&concept=Radiology Notes` | **No** — patient-wide. Current Doctor empty state uses this. |
| `GET /obs?order=` | **Does not work** on this REST version. |
| Bahmni visit widget `clinicalNotes` / Radiology Notes | Configured `scope: latest`, `numberOfVisits: 1` — intended as that visit, not Hospital EMR’s selected-visit + order filter. |

If write cannot set `order_id`, Doctor **cannot** distinguish two imaging reports on the same visit without patient-wide or encounter-wide leakage. That is a **blocker**, not something to paper over.

ORD-16 proved `order_id` **can** be set. Visit GET + concept + order UUID is the safe read.

### Blockers

Resolved in this development environment (see § Development Configuration):

1. Provider for `radiology.abikan` — `01a06b87-…` linked to the existing user.
2. **Get Orders** on role `Abikan:Radiology`. **`app:orders` still absent.**
3. Radiology Notes persist with `order_id` — ORD-16 synthetic note.

Still open (do not treat as write blockers):

- **`Get People` is missing.** Raw `POST /obs` cannot set `person`. Irrelevant — bahmniencounter is the write path.
- Current Hospital EMR Doctor read is visit + order scoped for radiology reports.

Not blockers:

- Payment before scan/report — **not** required.
- PACS / DICOM / `app:orders` / new concepts / new tables.

### Recommended Next Implementation

**Write path is proven.** Hospital EMR Write report + Doctor visit/order-scoped read are implemented below.

---

## Radiology Reporting — Implementation

Hospital EMR records a free-text radiology report on the existing OpenMRS chart. There is **no** custom reporting database, report table, report ID, author table, or visit-report join. There is **no** PACS, DICOM, OHIF, dcm4chee, image viewer, or modality worklist in this workflow.

### Radiology Notes reused

Concept **Radiology Notes** `ae6e5490-ade9-486e-8268-9e4efd45b07e` (Text). The Radiologist types findings and impression. The placeholder is not saved. No default clinical text (Normal / NAD / Negative / Impression / Findings).

### Existing Consultation encounter reused

Write is `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with the **existing** Consultation `encounterUuid` that already holds the Radiology order. `encounterUuid` is never omitted. A second Consultation is not created. A RADIOLOGY encounter is not created.

### `order_id` binding

The observation includes `orderUuid` = the Radiology order. OpenMRS stores `obs.order_id` on that order. A report for one order is not read as another order’s report.

### Selected visit binding

The payload includes the selected `visitUuid`. Reads use `GET /visit/{selectedVisitUuid}` nested observations, then filter Radiology Notes + that order UUID. `GET /obs?patient=&concept=` is not the authoritative lookup. A report on Visit #001 does not appear on Visit #002.

### Radiology provider

The signed-in user (`radiology.abikan`) maps to the existing OpenMRS provider. There is no author dropdown. Displayed “Reported by” comes from the persisted observation creator when available.

### Radiology Desk report workflow

Same Radiology Desk. Order → Price → Payment → Report. **Write Report** / **View Report** / **Edit Report** on the request. Payment does not gate writing a report. Pricing and accountant collection are unchanged.

Create: no observation UUID. Update: re-fetch the visit notes immediately before save and POST the existing observation UUID so a second Radiology Notes row is not created.

### Doctor report display

Doctor Workspace loads notes for **selected visit** only. Each imaging order on that visit shows its own report, or “No report recorded for this examination.” Status **Report pending** / **Report available** is derived from whether that observation exists. Existing doctor order status is unchanged.

### What this does not add

- Custom reporting store
- PACS / DICOM / structured radiology templates
- Payment-before-report enforcement
- Clinical fulfillment states (`fulfiller_status`, completed, cancelled)
- `app:orders` / Bahmni Orders fulfillment UI

---

---

## Development Configuration

Development OpenMRS only. Existing account **reused**. No second Radiology user. `provision-dev-users.py` updated so a later provision run keeps this shape.

| Item | Result |
|---|---|
| User | **`radiology.abikan`** `6d76e166-f381-4534-93e7-3b93c6c519d2` (unchanged) |
| Person | Radiology Staff `4e12bb7b-e5d3-4a43-80c1-1d6b4ebf6d22` (existing) |
| Role | `Abikan:Radiology` still inherits **Radiology-App** |
| Provider | **Created** `01a06b87-5fb5-43ef-a0c5-0d3a4fe1472b`, identifier `radiology.abikan`, same person as the user. Pattern matches `doctor.abikan` (`17dec510-…`, identifier `doctor.abikan`). `doctor.abikan` was **not** modified. |
| `GET /provider?user=6d76e166-…` | **`results: [{ uuid: 01a06b87-…, identifier: radiology.abikan }]`** (was `[]`) |
| Privilege granted | **Get Orders** `d05118c6-2490-4d78-a41a-390e3596a241` on `Abikan:Radiology` only |
| `app:orders` | **Not granted** (confirmed absent on the session) |
| Add Orders | **Not granted** |
| Other departments | **Unchanged.** After the role POST: `doctor.abikan` still has Get Orders (via Clinical/Provider, not this change); `reception.abikan`, `nurse.abikan`, `accountant.abikan` still lack Get Orders and `app:orders`. Direct privileges on `Abikan:Doctor` / Reception / Nursing / Accountant unchanged. |

Verification before any new clinical report:

| Check | Result |
|---|---|
| `radiology.abikan` session | Authenticated |
| Radiology Desk `GET /openmrs/abikan-api/radiology/patient/{ABC200016}` | HTTP 200, ORD-14 / ORD-15 listed, payment statuses unchanged |
| Provider lookup | Non-empty (above) |
| `GET /order/c09b9e2f-…` (ORD-14) | HTTP **200** (was 403) |
| Price path | Desk still returns examinations + `canCreateCharge`; **no new charge posted** |
| `app:orders` | Absent |

---

## Controlled Radiology Notes Persistence Test

Synthetic development data. **Not** ORD-6 / ORD-14 / ORD-15. No invoices created.

### TEST order

Doctor workflow: start OPD visit on TEST patient **ABC200018** (`26b50a91-0e06-4153-b872-530a9c67a4c8`, Test Testing), then `POST /openmrs/abikan-api/radiology/patient/{uuid}/orders` as `doctor.abikan` with hospital service **Musculoskeletal** (`us-msk`, concept `161277…`).

| Object | UUID / value |
|---|---|
| Patient | ABC200018 `26b50a91-0e06-4153-b872-530a9c67a4c8` |
| Selected visit | `0b99c191-5e6d-4784-8ecf-cb747cfccef3` (new OPD, location OPD-1) |
| Consultation encounter | `5f8a2f36-6772-425e-9933-bf03b9219162` (**one** encounter on that visit) |
| Radiology Order | **ORD-16** `a6e20ad8-7b64-49fc-9c87-8cb8a57d227d` |
| Examination | Musculoskeletal |

Chain: Patient → selected Visit → Consultation → Radiology Order. Encounter count after order: **1**.

### Radiology Notes write

`radiology.abikan` `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with **existing** `encounterUuid` (not omitted). Raw `POST /obs` not used.

| Field | Value |
|---|---|
| Concept | Radiology Notes `ae6e5490-ade9-486e-8268-9e4efd45b07e` Text |
| Value | `TEST RADIOLOGY REPORT — DEVELOPMENT ONLY` |
| `orderUuid` | ORD-16 `a6e20ad8-…` |
| `providers` | Radiology provider `01a06b87-…` |
| HTTP | **200** |
| Returned encounter | **Same** `5f8a2f36-…` (no second Consultation, no RADIOLOGY encounter) |
| Observation UUID | `16742ff2-0e53-410e-a532-177ab4b716f6` |

### Order binding

MySQL `obs.order_id` → ORD-16. REST `GET /obs/{uuid}?v=full` nested `order.uuid` = `a6e20ad8-…`, `orderNumber` ORD-16.

### Visit binding

`GET /visit/0b99c191-…` nested obs: exactly **one** Radiology Notes row, `order` = ORD-16, encounter = the Consultation above.

### Provider attribution

| Stamp | Value |
|---|---|
| `obs.creator` | `radiology.abikan` |
| OpenMRS user | `6d76e166-…` |
| Provider | `01a06b87-…` identifier `radiology.abikan` |
| Encounter providers after save | **doctor.abikan** (original orderer) **and** **radiology.abikan** (report save). No custom author field. |

### Doctor / visit-safe read-back

Authoritative: visit GET + filter concept UUID + order UUID. Patient-only `GET /obs?patient=&concept=` was **not** used as the proof.

| Query | Radiology Notes found |
|---|---|
| Selected visit `0b99c191-…` + ORD-16 | **1** — correct text, encounter, order |
| Same patient ABC200018, other OPD visit `43518247-…` | **0** |
| Other patient ABC200016 Visit #001 (ORD-14) `2857db49-…` | **0** |
| Other patient ABC200016 Visit #002 (ORD-15) `a70cbb56-…` | **0** |

### Cleanup

OpenMRS REST void exists, but the synthetic **ORD-16** order and note were **left in place** so the next UI task can read a real visit/order-bound report. They are labelled TEST in this document. **Not** voided.

ORD-6, ORD-14, ORD-15, INV/2026/00006, INV/2026/00031, INV/2026/00032 were not modified. No database rows were deleted.

---

## 9. Recommended Next Step

**Reporting UI is in Hospital EMR.** Radiology Desk writes Radiology Notes on the existing Consultation; Doctor Workspace reads the same visit + order.

Do **not**:

- start PACS, DICOM, Oviyam, or OHIF
- create a Hospital EMR reporting database
- invent Findings/Impression fields
- grant `app:orders`
- assume the scan must be paid first
- use FHIR DiagnosticReport as the store
- use patient-only note retrieval

| Option | Status |
|---|---|
| **A. Bahmni Orders fulfillment** | Still unused; Radiology still lacks `app:orders` |
| **B. Hospital EMR Write report** | **Implemented.** Radiology Notes on the existing Consultation, scoped to selected visit + order. |

---

## Investigation constraints

ORD-6, ORD-14, ORD-15, INV/2026/00031 (reversed), INV/2026/00032, and INV/2026/00006 were not modified.

Earlier validation POST created empty Consultation `a7e59ed8-…` on Visit #001; it remains **voided**.

This configuration pass created: OpenMRS provider for `radiology.abikan`; **Get Orders** on `Abikan:Radiology`; new OPD visit `0b99c191-…`; ORD-16; Radiology Notes obs `16742ff2-…`. No charges or payments.

---

## Radiologist Workspace — UX Audit

Date: **24 Aug 2026**. Investigation plus **safe copy / hierarchy / stale-state cleanup only**. No OpenMRS, Odoo, Radiology Notes, pricing, payment, provider, or RBAC changes. No worklist, PACS, DICOM, or structured templates.

### Current workspace structure

| Surface | Route | What the Radiologist sees |
|---|---|---|
| **Radiology Desk** | `#/radiology` | Radiology Worklist is the home screen. Pending examinations first. No KPI cards. |
| **Nav** | Radiology + Worklist (soon) | Dashboard / Orders / Reports duplicates removed. `#/radiology/orders` still parses as the desk. |
| **Patient chart** | `#/radiology/patient/{uuid}` | Identity (name, hospital number, age, sex). Radiology orders table. |
| **Order** | `#/radiology/order/{uuid}` | Examination title. Patient / hospital number / daily visit number / visit type / location (only if useful) / order date / order number / STAT / indication / ordered-by. Price card. Radiology Report. |

Search in the shell header is the entry to a patient. Opening a row opens that exact order.

### Order list (patient chart)

Columns: Visit, Examination, Ordered, Price / payment, Report, Action.

- **Visit** uses Reception labels: `Visit #001 · General Outpatient`. OPD-1 is not shown.
- **Examination** is the hospital menu name (e.g. Musculoskeletal, Obstetrics (Pregnancy)), not the raw concept name.
- **Price / payment**: amount from the existing Odoo charge when present, plus **Price pending** / **Unpaid** / **Paid**.
- **Report**: **Report pending** or **Report available**.
- **Action**: Write Report or View Report (opens the order).

Dropped from the list: Study (always empty), Priority (noise except STAT on the order), duplicate Reports table, PACS UIDs, allergies/diagnoses/meds, first-open-visit header.

The patient chart list is the **basic per-patient worklist**. It is not a hospital-wide queue.

### Redundancies found and removed

- Home: empty orders table + Reports card + Dashboard/Orders/Reports all pointing at the same desk.
- Patient chart: Doctor chrome (alerts, meds, diagnoses), visit fallback, PACS studies, previous imaging “Encounter”, a second reports table duplicating the order list, Patient Account link, Price card repeating the list’s price/payment.
- Order: identity repeated in header, facts, fee card, and report panel; price and payment twice; fake “Order status: Ordered”; Study —; Accession jargon; “Signed in at Registration Desk”; live Oviyam/dcm4chee controls; disabled **Open Images** that looked like an action; **Send fee to Accounts**.

Left on purpose: patient name + hospital number on the order (no identity header there); examination as the page title and in the list.

### Terminology decisions

| Staff language | Not used |
|---|---|
| Radiology Report | Notes, Clinical Notes, Consultation Notes, Radiology Notes (UI) |
| Set Price / Save Price | Send fee to Accounts, Process, Submit |
| Write Report / View Report / Edit Report / Save Report | Fulfill, Manage |
| Price pending / Unpaid / Paid | Ordered, UNPAID/PAID all-caps, Partially paid as its own staff state |
| Report pending / Report available | Completed, Verified, Approved, Signed, Final, Preliminary |
| Daily visit number `001` | OPD-1 as the visit |
| Visit type General Outpatient | OPD as the only label, or location as “Visit” |
| Location (only when not the internal outpatient room) | OPD-1 labelled as visit type |
| Accounts collects payment | Radiologist as cashier |

### Visit / order identity

Authoritative chain: Patient → Visit → Consultation → Radiology Order → Radiology Report.

- Opening an order keeps `patientUuid`, `visitUuid`, `orderUuid` from that order.
- Missing visit, or visit belonging to another patient: **reject** (“This order is not on the selected visit”). No first-open / latest / billed / first-order fallback.
- Patient and order screens remount on UUID change so the previous chart cannot linger.

### Pricing UX

Radiologist sets NGN on the **order**. Doctor does not. Accountant does not create the price.

- Empty field, no $60 ORD-6 default, no catalogue placeholder.
- Rejects empty, zero, negative, foreign currency, malformed.
- **Set Price** → confirm **Save Price** / Cancel. Duplicate submit blocked while saving.
- Already priced: amount + payment state, no second price field.
- Helper: amount is naira; Accounts collects; report can still be written if unpaid.

### Payment UX

From Odoo charge data only:

| Odoo | Staff |
|---|---|
| No charge | Price pending |
| UNPAID or PARTIALLY PAID | Unpaid |
| PAID | Paid |

Radiology does not collect payment. Write Report stays available when unpaid. Unpaid copy: cashier still needs to collect; you can still write the report. Paid does not mean the scan was done.

### Report UX

Existing Radiology Notes observation on the Consultation, `order_id` = this order.

- Heading **Radiology Report**. Helper: this examination only; not the doctor’s clinical notes.
- Empty: **No report recorded for this examination.** Placeholder: **Enter the radiology findings and impression.**
- Write Report / Edit Report / Save Report / Cancel. Cancel clears the draft and does not save.
- **Reported by: [name]** only when a human-readable provider/person name exists. Login ids such as `radiology.abikan` are not shown.
- Date/time from the observation when present.

### Empty / loading / error states

| Situation | Copy |
|---|---|
| Desk | Search a patient… |
| No orders | No radiology orders / This patient has no radiology orders yet. |
| Orders fail | Orders unavailable. Try again in a moment. |
| No price | No price set. |
| No report | No report recorded for this examination. |
| Order missing | This radiology order was not found. |
| Visit mismatch | This order is not on the selected visit. |
| Worklist empty | No pending Radiology examinations. |

“Not configured” is not used for empty clinical data.

### Patient-switch safety

Patient UUID change clears identity, orders, notes, and charges before reload. Order UUID change clears order, visit, price card, and report panel.

Expected live check: ABC200018 / ORD-16 report is visible; switch to ABC200016 and ORD-16 disappears; switch back and it returns. Another visit on the same patient does not inherit the report.

### Doctor / Radiology / Accountant consistency

- Same hospital examination names (menu `hospitalName`) in Doctor order panel, Radiologist list/order, and the Odoo charge `examinationName`.
- Same visit labels as Reception: hospital number, daily visit number on the visit, General Outpatient not OPD-1.
- Same Odoo amount: Radiologist price → existing radiology charge → Accountant collects. No second currency or price path.
- Doctor reads the same visit+order Radiology Notes as **Radiology Report**. Doctor does not set price or write the report.
- Doctor order table actions stay off (no Write Report from consultation).

### Remaining limitations

- Imaging images are not shown in Hospital EMR until a real PACS/DICOM integration exists. Unfinished Images UI was removed (see Imaging UI — Deferred).
- Report status is only presence/absence of Radiology Notes. No verified/signed workflow.
- Author is the OpenMRS user/provider on the observation, not a Radiologist table.
- The worklist lists valid Radiology orders on any visit age. Pagination is used instead of a date window.
- Historical ORD-6 USD TEST product remains isolated and is not a default price.

---

## Radiology Worklist — Implementation

Date: **25 Aug 2026**. The Radiologist home screen is the worklist. It is a derived view. No worklist table, appointment table, or second Radiology order store was added.

### Pending work

An examination is pending when it is a valid Radiology order on a visit and has **no** Radiology Notes observation for that order.

Radiology Notes present → **Report available**.

No invented states: Unattended, In Progress, Completed, Verified, Signed, Final, or Cancelled.

### Data sources

| Fact | Source |
|---|---|
| Orders | Existing OpenMRS Radiology orders on **all** visits (`GET /visit?includeInactive=true` + encounter orders, paginated). Patient-level `bahmnicore/orders` fills gaps. |
| Visit | Same visit: daily visit number, visit type. OPD-1 is not shown as the visit. |
| Report | Existing Radiology Notes (`order_id` = Radiology order) on that visit |
| Price / payment | Existing Odoo charge `radiology:{orderUuid}` |

`GET /openmrs/abikan-api/radiology/worklist` is Radiology-only. It does not create rows.

### Identity

Each row carries `patientUuid` + `visitUuid` + `orderUuid`. Open uses `#/radiology/order/{orderUuid}?patient=…&visit=…`. If the loaded order does not match, the page rejects it. No patient-only, first-open, latest, or billed-order fallback.

### Pricing / payment / report

- **Doctor** creates the order. No price input. May see Price pending / Unpaid / Partially paid / Paid.
- **Radiologist** sets the NGN price through the existing fee card.
- **Accountant** collects payment on the existing charge. The worklist does not collect money. A report can be written while unpaid.
- **Radiologist** writes or edits the Radiology Report on the existing order-detail screen.

### Filters and ordering

Search: patient, hospital number, or examination. Category: Ultrasound Scan / Radiography / Fluoroscopy. Report: Pending / Reported / both.

Pending examinations are newest first. STAT is shown only when the order urgency is STAT.

### Empty state

**No pending Radiology examinations.** Not “No patients” or “No appointments.”

### Security and leakage

Radiology role required. Patient switch replaces the list. ORD-16 and ORD-17 stay independent on the same visit. Visit #001 and Visit #002 stay independent on the same patient. ABC200018 data does not remain when ABC200016 is selected.

### Limitations

No date window. No PACS. No Radiologist appointment. No new report model.

Doctor does not set Radiology prices. Radiologist sets Radiology prices. Accountant collects payment.

ORD-16, ORD-6, ORD-14, ORD-15, and invoices INV/2026/00006, INV/2026/00031, INV/2026/00032 were not modified in this UX pass.

---

## Radiology Worklist — No Date Limit

Date: **25 Aug 2026**.

The worklist no longer uses `fromStartDate` or a 30-day visit window. It pages `GET /visit?includeInactive=true` until the OpenMRS page is exhausted (safety cap 2000 visits, not a clinical cutoff).

Pending = valid Radiology order on a visit with no Radiology Notes for that order. Reported = Radiology Notes exist for that order. Visit age does not hide either.

This installation’s oldest Radiology order is **ORD-6** (17 Aug 2026, ABC200007, report pending). No TEST order is currently older than 30 days (today 25 Aug 2026). ORD-6 and today’s pending orders (ORD-22–ORD-25) both appear. ORD-16 remains **Report available**. Identities stay `patientUuid` + `visitUuid` + `orderUuid`. No archival table. No second queue database.

---

## Radiology Order Cancellation — Capability Audit

Date: **25 Aug 2026**. Investigation only. **No Delete/Cancel button was added.** No OpenMRS order was voided or discontinued. Protected fixtures were not modified.

### Classification: **C**

Only a privileged Bahmni/OpenMRS orders workflow can cancel. Radiology must not get that permission.

| Mechanism | What exists | Safe for Radiology? |
|---|---|---|
| OpenMRS `order_action` | Schema: `NEW`, `DISCONTINUE`. This hospital has **1** discontinued order (not Radiology). All Radiology orders are `NEW`. | No |
| `date_stopped` / `previous_order_id` | Columns exist. No Radiology row uses them. | No |
| `fulfiller_status` COMPLETED / CANCELLED | Unused. No Radiology row has a fulfiller value. | No — do not invent this as a Radiology UI state |
| REST `DELETE /order/{uuid}` (void) | HTTP OPTIONS advertises DELETE. Radiology session has **Get Orders** only. | No |
| Bahmni Clinical Orders tab | `app:clinical:ordersTab` + **Add Orders** / **Edit Orders** on `doctor.abikan` | Privileged Clinical workflow. Not Radiology. |

`radiology.abikan` privileges related to orders: **Get Orders** only. Not present: Add Orders, Edit Orders, Delete Orders, `app:orders`, `app:clinical:ordersTab`.

**Do not grant** `Edit Orders`, `Delete Orders`, or `app:orders` to Radiology so a Cancel button can appear.

### Financial safety

Cancelling an OpenMRS order does **not** update Odoo. Radiology charges are confirmed sales with invoices (`radiology:{orderUuid}`). Observed states:

- No charge — nothing in Odoo to reverse.
- Price set / unpaid — posted invoice remains (e.g. INV/2026/00033–00035).
- Partial — residual remains (e.g. INV/2026/00036).
- Paid — payment stays unless Accounts posts a credit note.
- Report available — Radiology Notes stay on the order.

Do not auto-cancel, refund, or delete an Odoo invoice from Radiology. Coordinated billing rules do not exist. **STOP** rather than invent them.

Pharmacy discontinue only unlinks **draft** sale lines. Posted Radiology invoices are not drafts.

### Report safety

An order with Radiology Notes must not be casually deleted. Voiding an order must not delete observations. `order_id` on Radiology Notes, the encounter, and the visit stay as clinical history.

### What would be required before a Cancel action

1. A product decision that Radiology (or only a privileged Clinical user) may discontinue, not delete.
2. The existing OpenMRS discontinue/void path — no new “Cancelled” status.
3. Explicit permission review. Do not auto-grant `Edit Orders`.
4. Coordinated Accounts rules for unpaid / partial / paid charges (credit note, not silent delete).
5. A rule that reported orders cannot be discontinued from Radiology.
6. A new synthetic TEST order for any destructive test. Never ORD-6, ORD-14–ORD-21, or INV/2026/00006, 00031–00035.

Until those exist, Radiology keeps **no** Delete/Cancel control.

---

## Imaging UI — Deferred

Date: **25 Aug 2026**. UI cleanup only. No OpenMRS, Odoo, Radiology Notes, orders, prices, or invoices were changed. dcm4chee / PACS configuration was not touched.

Radiology **Reports** are supported today: the Radiologist writes and edits Radiology Notes on the order; the Doctor reads that report. Price and payment stay on the existing Odoo charge.

Radiology **images** (the scan itself) are not integrated in Hospital EMR. This hospital’s imaging equipment is not connected. PACS/DICOM is required for real image viewing. The unfinished Hospital EMR “Images — Coming soon” / placeholder / Open Images UI was **removed** so staff only see working capabilities: examination, price, payment, and Radiology Report.

No image upload, image table, attachment store, or viewer was added. That would be a false PACS replacement.

This does **not** remove hospital imaging capability. When the modality → DICOM/PACS path is actually available, Hospital EMR can add a proper **View Images** integration. Until then, do not show an empty Images section.

ORD-16 and ORD-19 TEST reports were left intact. Protected orders and invoices were not modified.

---

## Radiology Development Test Orders

Date: **24 Aug 2026**. Development TEST records only. Created through the existing Doctor → Radiology order API, Radiologist NGN price API, and Radiology Notes report write. **No** direct OpenMRS row inserts. **No** new patients. **No** Radiologist appointment. **No** worklist. **No** application-code change.

ORD-6, ORD-14, ORD-15, ORD-16, INV/2026/00006, INV/2026/00031, and INV/2026/00032 were read after creation and were **unchanged**.

| Test | Order | Patient | Visit | Examination | Price | Payment | Report |
|---|---|---|---|---|---|---|---|
| **A** — price pending | **ORD-17** `b43c54b2-696d-4925-86ce-06455000330e` | ABC200018 Test Testing `26b50a91-…` | Existing OPD `0b99c191-…` (same visit as ORD-16). No daily visit number stored. General Outpatient. Consultation `5f8a2f36-…` **reused**. | Skull X-ray | None | Price pending | Report pending |
| **B** — priced, unpaid | **ORD-18** `6db4d95b-b581-4ed2-8076-0c15d0ae5d51` | ABC200018 | Existing OPD Visit **#003** `43518247-…`. Consultation `e28092c8-…` created by the order write (visit had none). | Pelvic | **₦11,111** (Radiologist-entered TEST amount) | Unpaid. Charge `radiology:6db4d95b-…` → S00034 / **INV/2026/00033**. Not collected. | Report pending |
| **C** — priced and reported | **ORD-19** `dc2cdf49-dba1-471b-b010-04343cbf79c9` | ABC200016 ABIKAN E2E TEST PATIENT `f242364e-…` | Existing OPD Visit **#001** `2857db49-…`. Consultation `5028d1c2-…` **reused** (same encounter as ORD-14). | Lumbosacral Spine | **₦12,222** (Radiologist-entered TEST amount) | Unpaid. Charge `radiology:dc2cdf49-…` → S00035 / **INV/2026/00034**. Not collected. | Report available. Radiology Notes `0b531c24-…`: `TEST REPORT — DEVELOPMENT ONLY` |
| **D** — two exams, one visit | ORD-16 (unchanged) + **ORD-17** | ABC200018 | `0b99c191-…` | Musculoskeletal + Skull X-ray | ORD-16 none; ORD-17 none | Both Price pending | ORD-16 report stays on ORD-16 only. ORD-17 has no report. |
| **E** — two visits, one patient | **ORD-18** on Visit #003; ORD-16/17 on the other OPD | ABC200018 | `43518247-…` vs `0b99c191-…` | Pelvic vs Skull / Musculoskeletal | Separate | Separate | ORD-16 report does **not** appear on Visit #003. ORD-18 does **not** appear on the ORD-16 visit. |

Also on ABC200016 Visit #001: ORD-14 Obstetrics (Pregnancy) remains Price pending / Report pending beside ORD-19. Visit #002 still shows only ORD-15 Pelvic ₦2,500 Unpaid / Report pending.

### How they were created

1. `doctor.abikan` `POST /openmrs/abikan-api/radiology/patient/{uuid}/orders` with selected `visitUuid`, hospital `serviceId`, and existing Consultation `encounterUuid` when one already existed.
2. `radiology.abikan` `POST /openmrs/abikan-api/radiology/patient/{uuid}/charge` `{ orderUuid, amount }` for ORD-18 (11111) and ORD-19 (12222). Not catalogue placeholders. Not ORD-6 $60.
3. `radiology.abikan` `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with **existing** Consultation `5028d1c2-…`, Radiology Notes, `orderUuid` = ORD-19. Not `POST /obs`. Not a second encounter.

Leave these TEST orders in place for the future Radiologist worklist. Do not delete rows. Do not treat them as real clinical findings.
