# Radiology Capability Audit

Date: **25 Aug 2026** (Africa/Lagos). All **42** hospital-approved Ultrasound and Radiography/Fluoroscopy names are orderable in Doctor → Orders → Radiology.

Selected visit (`patientUuid` + `visitUuid`) remains authoritative. No Hospital EMR-only concepts were created. Missing names were added as OpenMRS **Radiology/Imaging Procedure** concepts. Laterality or area is asked only when the dictionary has no generic concept for that hospital line.

CT, MRI, ECG, echo, mammogram, and pathology from the same paper form are **not** Radiology in this phase. PACS, DICOM, and reporting were not built. ORD-6 was not modified.

Related documents (not superseded): `RADIOLOGY_WORKFLOW.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`, `CLINICAL_DOCUMENTATION_AUDIT.md`.

Status labels (exactly one per finding):

| Label | Meaning |
|---|---|
| **EXISTS AND WORKS** | Present in this installation and observed to work |
| **EXISTS BUT NOT EXPOSED** | Bahmni/OpenMRS/PACS/Odoo has it; Hospital EMR does not show or write it |
| **EXISTS BUT NOT CONFIGURED** | Software/tables/APIs exist; required settings or data are missing |
| **MISSING** | Not present in this installation |
| **REQUIRES HOSPITAL DECISION** | Cannot proceed honestly without a hospital/accounting choice |

Live checks: OpenMRS MySQL, OpenMRS REST, Odoo PostgreSQL, dcm4chee / pacs-integration PostgreSQL, HTTP probes, departmental sessions (`*:Admin123`). `npm test` and `npm run build` do not write clinical or imaging data.

---

## Radiology Capability

This hospital already has the **engines** for radiology. It does not yet have a **working in-hospital imaging service**.

Do not assume a dictionary concept means the hospital offers that examination.

| Capability | Status |
|---|---|
| OpenMRS **Radiology Order** type | **EXISTS AND WORKS** |
| Orderable imaging concepts (CIEL dictionary) | **EXISTS AND WORKS** as dictionary, **not** as a hospital menu |
| Doctor can **read** radiology orders in Hospital EMR | **EXISTS AND WORKS** (patient-level list) |
| Doctor can **create** a radiology order from Hospital EMR | **EXISTS BUT NOT EXPOSED** (button: Coming soon) |
| Doctor can create a radiology order from Bahmni Clinical | **EXISTS BUT NOT EXPOSED** in Hospital EMR; Bahmni Clinical orders tab **EXISTS AND WORKS** for `doctor.abikan` |
| Radiology Notes / result form | **EXISTS BUT NOT CONFIGURED** (0 observations) |
| RADIOLOGY document-upload encounter | **EXISTS BUT NOT CONFIGURED** (0 encounters) |
| PACS (dcm4chee) process | **EXISTS AND WORKS** as software |
| PACS as a hospital imaging service | **EXISTS BUT NOT CONFIGURED** (0 studies, 0 modalities) |
| Hospital radiology catalogue / NGN tariff | **MISSING** |
| In-house vs outsourced | **MISSING** / **REQUIRES HOSPITAL DECISION** |
| Structured radiologist report fields | **MISSING** |
| FHIR DiagnosticReport rows | **MISSING** (table exists, 0 rows) |
| OHIF viewer | **MISSING** |
| Radiology login location | **MISSING** |
| Hospital-wide imaging queue API | **MISSING** |

Intended Bahmni chain (designed, not proven end-to-end):

```
Doctor places Radiology Order on a Consultation
  → OpenMRS order (encounter → visit)
  → payment/billing where the hospital requires it
  → pacs-integration → modality worklist
  → acquisition → dcm4chee
  → Radiology Notes and/or RADIOLOGY document
  → doctor sees the result
```

ORD-6 proved the **order + TEST fee** path. It did **not** create a PACS worklist row, a study, or a report.

**Do not build a second radiology database.** Reuse OpenMRS orders, Odoo `radiology:{orderUuid}` charges, and dcm4chee.

---

## Radiology Orders

### How a doctor currently orders imaging

| Path | Status |
|---|---|
| Bahmni Clinical → Orders tab → **Radiology** (`otherInvestigationsMap`) | **EXISTS AND WORKS** in Bahmni; Hospital EMR does not call it |
| `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `orders[]` | **EXISTS AND WORKS** (proven by ORD-6) |
| Hospital EMR Doctor **Order radiology investigation** | **EXISTS BUT NOT EXPOSED** (disabled Coming soon) |
| Reception / Nurse order screen | **MISSING** (correctly; do not add) |

Order options in Bahmni Clinical config: `enableRadiologyOrderOptions`: Urgent, NeedsPrint. Urgent maps to OpenMRS urgency **STAT**.

### Storage

Orders live in the OpenMRS `orders` table. They are **not** Drug Orders.

| Field | Live |
|---|---|
| Order type | **Radiology Order** `d3561dc0-5e07-11ef-8f7c-0242ac120002` |
| Java class | `org.openmrs.Order` (same class as Lab Order and Procedure Order) |
| Investigation identity | Order `concept_id` — a **Radiology/Imaging Procedure** concept |
| Encounter | `orders.encounter_id` — **yes** |
| Visit on the order row | **No.** Visit is on the encounter (`encounter.visit_id`) |
| Fulfiller status | Column exists; ORD-6 is **NULL** |

REST `GET /order/{uuid}` returns `encounter`, not `visit`. Visit is recovered as:

**Patient → Visit → Encounter → Order**

`GET /order` getAll is unsupported (HTTP 400). Same limitation as Laboratory. There is no hospital-wide REST worklist.

### Other order types (for contrast)

| Type | UUID | Class | Live rows |
|---|---|---|---|
| Drug Order | `131168f4-…` | `DrugOrder` | 8 |
| Test Order | `52a447d3-…` | `TestOrder` | 0 used as radiology |
| Lab Order | `d3560b17-…` | `Order` | 4 |
| Radiology Order | `d3561dc0-…` | `Order` | **1** (ORD-6) |
| Procedure Order | `3f224d3e-…` | `Order` | 0 |
| Endoscopy Order | — | — | **MISSING** (mapped in Clinical config, type not created) |

### Dictionary vs hospital services

Concept class **Radiology/Imaging Procedure**: **255** active concepts.

**Radiology Orders** set `9bb0795c-…`: **19** Bahmni order-UI sections (not a priced menu):

Head, Face, Head and Neck, Chest, Upper extremity, Abdomen, Hip, Back, Pelvis, Lower limb, Angiography, CT Scan, Fluoroscopy, Ultrasound, Magnetic Resonance Imaging, Echo, Nuclear medicine, Laparoscopy, Other Radiology Orders.

**All Radiology orders** `05d53977-…`: **266** members.

Keyword counts inside Radiology/Imaging Procedure (name contains; overlapping):

| Keyword | Approx. count | Status as a hospital service |
|---|---|---|
| X-ray / radiograph | 132 | Dictionary **EXISTS AND WORKS**; hospital offer **REQUIRES HOSPITAL DECISION** |
| Ultrasound / sonograph | 33 | same |
| CT | 38 | same |
| MRI | 9 | same |
| Mammogram | 1 (`163591…`) | **REQUIRES HOSPITAL DECISION** |
| Echo-named imaging | 2 | **REQUIRES HOSPITAL DECISION** |

**ECG** (`12-lead electrocardiogram`) is class **Procedure**, not in the Radiology Orders set. **REQUIRES HOSPITAL DECISION** whether ECG is an imaging service.

Do **not** invent hospital examinations from this dictionary. Angiography, nuclear medicine, and laparoscopy may not be offered here.

### The only live radiology order

Do not perform a scan against this order. Do not modify it.

| Field | Value |
|---|---|
| Order number | **ORD-6** |
| Order UUID | `46e6031f-1fa9-4c48-a510-d32666cbc2ce` |
| Patient | Ngozi Eze, ABC200007 (isolated billing TEST — do not use as ordinary clinical work) |
| Concept | Chest x-ray, single view `165152…` |
| Encounter | Consultation `838290e9-…` |
| Visit | OPD `020a5cfe-…` @ OPD-1, 17 Aug 2026 |
| Urgency | ROUTINE |
| Fulfiller status | NULL |
| Comment | Isolated radiology billing TEST. Do not perform scan. |
| Images / notes | None |

ABC200016 (preferred TEST chart): **0** radiology orders on today #001, 23 Aug #001–#003, or the leftover OPD visit.

---

## Radiology vs Laboratory

Bahmni already distinguishes them. Do **not** create a second generic “investigation” system.

| | Laboratory | Radiology |
|---|---|---|
| Order type | **Lab Order** `d3560b17-…` | **Radiology Order** `d3561dc0-…` |
| Concept / service | `All_Tests_and_Panels` (82) + hospital lab CSV | Radiology/Imaging Procedure (255) + Radiology Orders set. **No hospital CSV** |
| Department / engine | OpenELIS / Laboratory Lite | dcm4chee + Bahmni Orders / document-upload |
| Workflow | Order → lab processing → `labOrderResults` | Order → (intended) PACS → Radiology Notes / documents |
| Result type | Structured numeric/coded lab results | Free-text **Radiology Notes**; optional Image-class files; DICOM in PACS |
| Existing UI | Hospital EMR Lab order panel **writes**; results **read** | Hospital EMR **reads** orders/notes; write is Coming soon |
| Billing | Hospital Laboratory pricelist (NGN) | Radiology Desk shop; 257 × $1.00 placeholders + TEST $60 |

Lab results API: `GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid=`. There is **no** equivalent radiology results API. Notes are ordinary `obs`.

---

## Radiology Results

There is **no** structured Findings / Impression / radiologist-name model. Do not invent one.

| Mechanism | Concept / object | Live rows | Status |
|---|---|---|---|
| Radiology Notes observation | `ae6e5490-…` Text / Misc | **0** | **EXISTS BUT NOT CONFIGURED** |
| RADIOLOGY encounter | Encounter type `d3a89c59-…` | **0** | **EXISTS BUT NOT CONFIGURED** |
| Diagnostic Images | `4e7ac8d1-…` Complex / Image | **0** obs | **EXISTS BUT NOT CONFIGURED** |
| Radiology Report | `e41ef81f-…` N/A / Image | **0** obs | **EXISTS BUT NOT CONFIGURED** |
| FHIR DiagnosticReport | `fhir_diagnostic_report` | **0** | **EXISTS BUT NOT CONFIGURED** |
| DICOM SR | — | — | **MISSING** |
| PACS study metadata | `/pacs/studies` | HTTP **501** | **EXISTS BUT NOT CONFIGURED** |

If a note existed, it would have:

- Patient (via encounter)
- Encounter UUID
- Obs datetime
- Optional `obs.order_id` (not required by the current Hospital EMR mapper)
- Performing / reporting provider from the encounter / observation, **not** a dedicated radiologist field
- Result status only as fulfiller status or “note present”

Hospital EMR Clinical “Radiology results” already **reads** Radiology Notes. The empty state **EXISTS AND WORKS**. There is nothing to display.

---

## Radiology Forms

| Form | Detail | Status |
|---|---|---|
| Bahmni Orders fulfillment | Title **Radiology Order FulFillment Form** / **Radiology Results**. Concepts: `["Radiology Notes"]`. `scope: "latest"`, `numberOfVisits: 2` | **EXISTS BUT NOT CONFIGURED** (never used; 0 notes) |
| HTML form named Radiology / X-ray | No matching published form | **MISSING** |
| Published OpenMRS forms | Vitals, History and Examination, Malaria, etc. — none are radiology result forms | Unused for imaging |
| Document upload | `encounterType=RADIOLOGY`, privilege `app:radiology-upload` | **EXISTS BUT NOT CONFIGURED** (0 RADIOLOGY encounters) |

Dictionary concepts without use are **unused**. Do **not** build a custom React result form in this phase.

The fulfillment form’s `scope: "latest"` is the same class of “latest across visits” display Bahmni uses on some observation boards. That is **not** a reason for Hospital EMR to treat notes as the patient’s latest complaint-style value when the doctor is working a selected visit.

---

## Radiology Worklist

| Surface | Status |
|---|---|
| Hospital EMR Radiology dashboard worklist | **MISSING** in Hospital EMR (“Coming soon”). Honest empty. |
| Hospital-wide OpenMRS REST queue | **MISSING** (`GET /order` getAll unsupported) |
| Bahmni Orders patient search → fulfillment | **EXISTS BUT NOT EXPOSED** to `radiology.abikan` (no `app:orders`) |
| Bahmni Clinical **Pending Orders** | Privilege `app:radiologyOrders` — SuperAdmin only | **EXISTS BUT NOT CONFIGURED** for Doctor / Radiology |
| dcm4chee modality worklist | 0 MWL items | **EXISTS BUT NOT CONFIGURED** |
| pacs-integration `test_order` | 0 rows; 0 modalities; 0 order_type | **EXISTS BUT NOT CONFIGURED** |

Radiology staff today: search a patient, open that person’s imaging chart. There is no hospital queue.

---

## Radiology Billing

Do **not** create new billing logic. Do **not** move radiology payment to Reception.

| Item | Live | Status |
|---|---|---|
| Odoo category All / Services / Radiology | 258 active products | Catalogue **EXISTS BUT NOT CONFIGURED** |
| Placeholder prices | **257** at $1.00 (Hospital EMR refuses `list_price ≤ 1.01`) | Production **MISSING** |
| Isolated TEST product | id **2392** “Chest x-ray, single view — TEST” $60, `default_code` = concept uuid | **EXISTS AND WORKS** |
| Shop | **Radiology Desk** `sale.shop` id **5** | **EXISTS AND WORKS** |
| Charge key | `radiology:{orderUuid}` | **EXISTS AND WORKS** |
| S00007 / INV/2026/00006 | TEST chest x-ray, **paid**, residual 0, shop 5, origin = ORD-6 visit | Isolated TEST **EXISTS AND WORKS** |
| Hospital Radiology pricelist | **MISSING** (Laboratory / Pharmacy / Registration / Consultation pricelists exist; Radiology Desk uses Public / USD list_price) | **REQUIRES HOSPITAL DECISION** |
| Atomfeed auto-invoice Radiology Order | **Not enabled** (Drug Order only) | Correct until real prices exist |
| Payment-before-scan | **Not enforced** | **REQUIRES HOSPITAL DECISION** |
| Radiology collects cash | No. Staff see UNPAID / PAID. Accountant pays | **EXISTS AND WORKS** |

PAID ≠ scan performed ≠ image stored ≠ report available.

---

## Radiology Roles / Permissions

Privileges were **not** changed.

| Who | Can order imaging | Can view orders | Can enter results | Can charge fee | Can pay |
|---|---|---|---|---|---|
| `doctor.abikan` | Bahmni Clinical yes; Hospital EMR Coming soon | Hospital EMR Clinical **yes** (read) | No | No | No |
| `radiology.abikan` | No | Hospital EMR Radiology **yes** (read) | Bahmni document-upload **yes**; Bahmni Orders fulfillment **no** (`app:orders` missing) | **Yes** (`app:radiology-upload`) | No |
| `accountant.abikan` | No | No Radiology workplace | No | No | **Yes** |
| `reception.abikan` | No | No | No | No | No |
| `nurse.abikan` | No | No | No | No | No |
| `lab.abikan` | No | No | No | No | No |

`Abikan:Radiology` inherits **Radiology-App**: Get/Add/Edit Patients, Visits, Encounters, Observations, Concepts, plus `app:radiology-upload`. No `app:orders`, no `app:clinical`, no `app:radiologyOrders`.

Do **not** grant Reception clinical radiology permissions. Do **not** create a new Radiology role in this phase.

Granting `app:orders` to radiology staff is **REQUIRES HOSPITAL DECISION**.

---

## Patient / Visit / Encounter Scope

OpenMRS relationship:

**Patient → Visit → Encounter → Order / Observation**

`orders` and `obs` have `encounter_id`. They do not store `visitUuid`.

| Object | Scope | Rule |
|---|---|---|
| New Radiology Order | Encounter / visit | Must be written on the **selected visit’s** Consultation (same as lab write) |
| Existing Radiology Order | Encounter / visit | Belongs to the encounter’s visit. May be **listed** as patient history |
| Radiology Notes | Encounter / visit | Must not be substituted from another visit as “this visit’s result” |
| RADIOLOGY document encounter | Encounter / visit | Same |
| PACS study | Patient + accession / order number | Not visit-native. Viewer uses MRN + order number |
| Known / previous imaging | Patient-level history | Legitimate on a Radiology desk or a labelled history list |
| Consultation fee | Visit | Unrelated (`consultation:{visitUuid}`) |
| Radiology fee | Order (`radiology:{orderUuid}`) | Origin may store visit uuid; key is the order |

### How Bahmni itself handles this

| Bahmni surface | Scope |
|---|---|
| Clinical **visit** page `pacsOrders` | Orders of type Radiology Order **on that visit** |
| Clinical **dashboard** `radiologyOrders` / `pacs` | Last **4 visits** (patient history) |
| Orders fulfillment Radiology Notes | `scope: "latest"`, `numberOfVisits: 2` |
| Document upload | Patient search → documents on a visit |

Bahmni already separates **this visit’s work** from **recent imaging history**. Hospital EMR should keep that distinction.

### Selected-visit behaviour (TEST data)

ABC200016 today Visit #001 `2857db49-…` has **no** radiology orders or notes.

The leftover OPD visit `6478a94e-…` has laboratory orders (malarial smear), **not** radiology.

Therefore the Clinical observation-scope bug **cannot be visually reproduced** for radiology on ABC200016: there is no older imaging result to leak.

The **code path is still patient-level**, same family as the old complaint/HPI bug:

- `fetchRadiologyOrders(patientUuid)` — `GET bahmnicore/orders?patientUuid=&orderTypeUuid=`
- `fetchRadiologyNotes(patientUuid)` — `GET /obs?patient=&concept=Radiology Notes`
- Neither call receives `visitUuid`
- `bahmnicore/orders` list does **not** return `visitUuid` or `encounterUuid`
- Doctor empty copy says “No imaging orders **on this visit** yet” while the query is **all visits**

If a future visit for this patient received a radiology order, opening a later empty visit would currently list that older order as if it belonged to the selected visit.

**Do not change the query in this investigation phase.** Filtering by visit needs encounter→visit resolution (the list API does not include visit). That is a small later fix, not a new database.

Laboratory reads are the same patient-level pattern. Out of scope here.

Radiology **desk** copy (“Imaging requested for this patient”) is the correct patient-level wording for a departmental workplace.

---

## Existing Bahmni APIs

Authentication: OpenMRS session (`JSESSIONID`) or HTTP Basic. Same as the rest of Hospital EMR.

| Purpose | Method | Endpoint | Source | Visit / encounter |
|---|---|---|---|---|
| Place order | POST | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `orders[]` | OpenMRS | Body includes `patientUuid` + `visitUuid` |
| List radiology orders | GET | `/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid=&orderTypeUuid=` | OpenMRS | Patient only; no visit in response |
| One order (Bahmni) | GET | `/openmrs/ws/rest/v1/bahmnicore/orders?orderUuid=` | OpenMRS | No visit in response |
| One order (REST) | GET | `/openmrs/ws/rest/v1/order/{uuid}` | OpenMRS | `encounter`; visit via encounter |
| Encounter + nested orders | GET | `/openmrs/ws/rest/v1/encounter/{uuid}?v=custom:(visit,orders)` | OpenMRS | Visit on encounter |
| Radiology notes | GET | `/openmrs/ws/rest/v1/obs?patient=&concept=ae6e5490-…` | OpenMRS | Encounter on obs; visit indirect |
| RADIOLOGY encounters | GET | `/openmrs/ws/rest/v1/encounter?patient=&encounterType=` | OpenMRS | Patient + type |
| PACS studies | GET | `/openmrs/ws/rest/v1/pacs/studies?patientId=` | pacsquery | HTTP **501** — `pacsquery.pacsConfig` NULL |
| Hospital-wide orders | GET | `/openmrs/ws/rest/v1/order` | OpenMRS | Unsupported |
| Radiology fee read | GET | `/openmrs/abikan-api/radiology/patient/{uuid}` | Hospital EMR → Odoo | Order-keyed |
| Radiology fee write | POST | `/openmrs/abikan-api/radiology/patient/{uuid}/charge` | Hospital EMR → Odoo | `radiology:{orderUuid}` |
| Viewer | GET | `/oviyam2/oviyam?patientID={MRN}&accessionNumber={orderNumber}` | Oviyam2 | Patient + order number |
| Archive UI | GET | `/dcm4chee-web3` | dcm4chee | HTTP 200 login |
| Document upload | Bahmni app | `/document-upload/?encounterType=RADIOLOGY` | OpenMRS VisitDocument | Visit documents |
| Orders fulfillment | Bahmni app | `/bahmni/orders/#/patient/{uuid}/fulfillment/Radiology Order` | OpenMRS obs | Privilege `app:orders` |

No new endpoints were added during this investigation.

---

## Existing Hospital EMR Integration

| Surface | What it does | Status |
|---|---|---|
| Home tile Radiology | Privilege `app:radiology-upload` | **EXISTS AND WORKS** |
| `#/radiology` | Search prompt; worklist/reports Coming soon | **EXISTS AND WORKS** (honest empty) |
| `#/radiology/patient/{uuid}` | Patient-level orders, notes, PACS, fee card | **EXISTS AND WORKS** (reads) |
| `#/radiology/order/{uuid}` | One order; Open Images; Write report Coming soon | Partial |
| Doctor Orders → Radiology orders / results | Patient-level read; order button Coming soon | Read **EXISTS AND WORKS**; write **EXISTS BUT NOT EXPOSED**; visit filter **EXISTS BUT NOT EXPOSED** |
| Radiology fee card | Charge API for mapped products with real prices | TEST **EXISTS AND WORKS** |

Staff language: “imaging orders”, “Open Images”, “Open full chart”. Source-system names stay out of the UI.

---

## Duplication Analysis

Do **not** create:

| Duplicate | Why not |
|---|---|
| Doctor “Radiology” module + existing Orders → Radiology | Same OpenMRS Radiology Order rows |
| “Results” + “Radiology Results” stores | Same Radiology Notes / documents |
| New imaging catalogue database | Map a hospital list onto existing concepts/products later |
| New PACS | dcm4chee already runs |
| New report engine | Radiology Notes + document upload |
| Reception radiology order screen | Bahmni workflow is clinical order, not reception |

What already exists and should be reused:

1. Radiology Order type + `bahmniencounter` `orders[]`
2. Concept class Radiology/Imaging Procedure (technical dictionary only)
3. dcm4chee + Oviyam2 + `/dcm4chee-web3`
4. pacs-integration encounter Atomfeed consumer (idle until modalities exist)
5. Odoo Radiology category, Radiology Desk, `radiology:{orderUuid}`, Accountant payment
6. Hospital EMR Radiology workplace reads
7. Doctor Orders section already split Laboratory / Radiology

Laboratory and Radiology are **different** order types. Showing both under Orders is grouping in the UI, not merging the engines.

---

## Recommended Hospital EMR UX

Supported by the actual Bahmni workflow. **Not implemented in this phase.**

### Doctor Workspace (selected visit)

Keep radiology **inside Orders**. Do not add a second Doctor Radiology module.

```
Orders
├── Laboratory     (already writable)
└── Radiology      (read now; write later)
```

When write is enabled later:

- POST existing `bahmniencounter` `orders[]` with the **selected** `visitUuid`
- Offer only a **hospital-approved** subset of concepts — not 255 CIEL rows
- Empty state must mean “none on this visit”, and the query must match that sentence
- Patient-wide previous imaging, if shown, must be labelled as history (same idea as Known Diagnoses)

### Radiology workplace (department)

Keep `#/radiology` as the staff desk (search patient, fee, later worklist/report). This is the analogue of Laboratory, not a second doctor module.

### Reception

Stay with patient, visit, visit number, routing. **Do not** add a radiology order screen.

### Nurse

No radiology interaction today. Do not grant new privileges.

### Results for doctors

Once notes or documents exist, show them on the ordering visit, and show older ones as previous imaging. Until then, keep the honest empty state.

### Sequence (after hospital decisions)

1. Hospital service list, in-house vs outsourced, NGN prices, tax, payment-before-scan, who reports.
2. Accounting configuration on existing Odoo products. Keep Radiology Order off Atomfeed until prices are real.
3. Doctor order write on the selected visit. Visit-filter the Doctor list (or relabel it as chart history).
4. Reuse `radiology:{orderUuid}` + Accountant.
5. Operations: `pacsquery.pacsConfig`, modalities, MWL. One dedicated TEST study only if the hospital agrees — not ORD-6 / Ngozi unless they explicitly allow it.
6. Result return via Radiology Notes / document upload. No new result table.
7. Worklist / report UX only after there is something to process.

---

## Order → result lifecycle

| Step | Status |
|---|---|
| Doctor decides imaging is needed | Clinical judgement |
| Radiology order on the consultation / selected visit | Bahmni **EXISTS AND WORKS**; Hospital EMR **EXISTS BUT NOT EXPOSED** |
| Billing / payment if applicable | TEST path **EXISTS AND WORKS**; production prices **MISSING** |
| Radiology worklist | **MISSING** / **EXISTS BUT NOT CONFIGURED** |
| Procedure / acquisition | **EXISTS BUT NOT CONFIGURED** (no modalities) |
| Images in PACS | **MISSING** (0 studies) |
| Result / report | **EXISTS BUT NOT CONFIGURED** (0 notes, 0 documents) |
| Doctor sees result | Read path **EXISTS AND WORKS**; nothing to show |

Do not invent missing steps. Do not treat payment as proof of a scan.

---

## Images / files

| Store | Live |
|---|---|
| DICOM studies / series / instances / files | **0** |
| Modality worklist / MPPS | **0** |
| AE titles | DCM4CHEE localhost:11112; CDRECORD localhost:10104 |
| Oviyam2 | HTTP 200 |
| dcm4chee-web3 | HTTP 200 |
| OHIF | HTTP 404 **MISSING** |
| PDF / attachment reports | 0 Image-class observations |
| External PACS reference | Compose default `DCM4CHEE@dcm4chee:11112`; unused until modalities exist |

Do **not** build a PACS.

---

## Reception / Nurse

| Role | Radiology responsibility today |
|---|---|
| Reception | None. Do not add ordering. |
| Nurse | None in Hospital EMR Nursing. No `app:radiology-upload`. |

---

## Test data

| Patient | Radiology |
|---|---|
| ABC200016 | **0** orders, **0** notes, **0** RADIOLOGY encounters |
| ABC200017 / ABC200018 / ABC200013 / ABC200015 | Not used; no new records created |
| ABC200007 Ngozi / ORD-6 | Isolated billing TEST only. Do not perform. Do not treat as ordinary chart work |

No clinical results were fabricated.

---

## Security

No privileges were broadened.

Reception must not gain clinical radiology permissions.

Radiology fee write is gated by `app:radiology-upload` (or SuperAdmin / System Developer). Payment stays on Accountant.

---

## STOP

Implementation is **not** started. Hospital configuration and decisions are required:

| Blocker | Label |
|---|---|
| No hospital radiology service list / tariff | **REQUIRES HOSPITAL DECISION** |
| 257 Odoo products at $1.00 cannot be billed | **EXISTS BUT NOT CONFIGURED** |
| Radiology Desk still USD; Laboratory already NGN | **REQUIRES HOSPITAL DECISION** |
| Payment before scan? | **REQUIRES HOSPITAL DECISION** |
| ECG / echo / mammography / CT / MRI / outsourced scope | **REQUIRES HOSPITAL DECISION** |
| Who enters the report (Bahmni Orders vs Hospital EMR) | **REQUIRES HOSPITAL DECISION** |
| Whether radiology staff receive `app:orders` | **REQUIRES HOSPITAL DECISION** |
| `pacsquery.pacsConfig` NULL; 0 modalities | **EXISTS BUT NOT CONFIGURED** |
| 0 studies, 0 reports | **MISSING** |
| Fulfillment form unused (`scope: latest`) | **EXISTS BUT NOT CONFIGURED** |
| Doctor visit-scoped radiology list | **EXISTS BUT NOT EXPOSED** (API has the encounter→visit link; list call does not filter) |
| Hospital EMR Doctor imaging write | **EXISTS BUT NOT EXPOSED** |

A proposed Hospital EMR UI that dumped 255 CIEL concepts, created a second order store, or built a PACS would **duplicate** Bahmni. That is rejected.

Non-blockers (do not rebuild): Radiology Order type, dcm4chee process, Oviyam / archive HTTP, TEST fee path, Accountant payment, Hospital EMR Radiology read workspace, Doctor Orders → Radiology **read**.

---

## Hospital-Approved Radiology and Ultrasound Menu

Source: the hospital’s supplied diagnostic referral form. This is the **initial approved Radiology menu**. It is not the 255-concept OpenMRS dictionary.

Do not add CT, MRI, or other imaging because a concept exists.

### Ultrasound Scan

1. Obstetrics (Pregnancy)
2. Pelvic
3. Breast
4. Abdominopelvic
5. Biophysical Profile (BPP)
6. Thyroid/Neck
7. Anomaly Scan
8. Eye/Ocular
9. Scrotal/Testicular
10. Musculoskeletal
11. Follicular Tracking
12. Prostate
13. Transvaginal
14. Doppler Studies

### Radiography / Fluoroscopy

1. Abdominal X-ray
2. Cervical Neck X-ray
3. Chest X-ray
4. Lumbosacral Spine
5. Paranasal Sinuses
6. Facial Bones/Mandible
7. Pelvic X-ray
8. Knee Joint
9. Ankle Joint
10. Paediatric X-ray
11. Hysterosalpingography (HSG)
12. Intravenous Urography (IVU)
13. Retrograde Urethrography (RCUG)
14. Barium Enema
15. Skull X-ray
16. Thoracolumbar Spine
17. Shoulder X-ray
18. Humeral X-ray
19. Forearm X-ray
20. Tibia & Fibula X-ray
21. Elbow X-ray
22. Wrist/Hand/Finger X-ray
23. Femoral X-ray
24. Thoracic Inlet
25. Micturating (Voiding) Cystourethrography (MCUG)
26. Temporomandibular Joint
27. Barium Meal
28. Barium Follow Through

### Other Diagnostic Services on Hospital Form

These appear on the same paper form. They are **not** Radiology in this phase and must not appear in the Radiology menu.

| Form section | Services | Why not Radiology here |
|---|---|---|
| Cardiology | ECG Resting; Echocardiogram Resting | ECG is class Procedure, not in Radiology Orders. Echo concepts exist as imaging but the hospital listed them under Cardiology. **REQUIRES HOSPITAL DECISION** for a later Cardiology workflow. |
| Pathology | Pap Smear; FNAC; Histology | Laboratory / histopathology, not imaging orders. |
| Special Service | Mammogram; DNA | Mammogram has an OpenMRS imaging concept (`163591…`) but the hospital listed it as Special Service, not Radiography. DNA is not imaging. **REQUIRES HOSPITAL DECISION** later. |

Do not implement these in this phase.

### Recommended Doctor grouping (not built)

```
Radiology
├── Ultrasound Scan
└── Radiography / Fluoroscopy
```

Use the hospital names above. Do not nest further. Do not dump 255 CIEL concepts. Contrast studies (HSG, IVU, barium, MCUG) stay under Radiography / Fluoroscopy as on the form.

---

## OpenMRS Concept Mapping

Live class **Radiology/Imaging Procedure** only. No concepts were created.

Match labels: **EXACT** · **CLOSE** · **AMBIGUOUS** · **MISSING**

Do not map two clinically different hospital services to one concept. Laterality-only concepts (left/right) are not a safe stand-in for a single hospital line that does not specify side.

### Ultrasound (14)

| Hospital service | OpenMRS concept | UUID | Existing? | Match | Notes |
|---|---|---|---|---|---|
| Obstetrics (Pregnancy) | Obstetric ultrasound | `159618…` | Yes | **EXACT** | Do not use this for BPP or anomaly scan. |
| Pelvic | Ultrasound of pelvis | `161283…` | Yes | **EXACT** | Do not use “limited” `161282…` or transvaginal. |
| Breast | Ultrasound of left breast / right breast | `161289…` / `161290…` | Yes (two) | **AMBIGUOUS** | No single “breast ultrasound”. Do not pick left only. |
| Abdominopelvic | — | — | No combined concept | **MISSING** | Abdomen `845…` and pelvis `161283…` exist as **two** exams. Do not map to CT abdomen/pelvis. |
| Biophysical Profile (BPP) | — | — | No | **MISSING** | Do not substitute Obstetric ultrasound. |
| Thyroid/Neck | Ultrasound of thyroid / Ultrasound of head and neck | `65b41d2f-…` / `161285…` | Yes (two) | **AMBIGUOUS** | Hospital line is one service; concepts are two territories. |
| Anomaly Scan | — | — | No | **MISSING** | Do not substitute Obstetric ultrasound. |
| Eye/Ocular | — | — | No | **MISSING** | CT of orbits exists — do not map ultrasound to CT. |
| Scrotal/Testicular | Ultrasound of scrotum and testicle | `161279…` | Yes | **EXACT** | |
| Musculoskeletal | Ultrasound of extremity | `161277…` | Yes | **CLOSE** | No MSK-named concept. Extremity is the closest; joints/tendons beyond a limb are not named. |
| Follicular Tracking | — | — | No | **MISSING** | Do not substitute Pelvic or Transvaginal. |
| Prostate | Ultrasound of prostate / Ultrasonography by transrectal approach | `ee40db9c-…` / `161164…` | Yes (two) | **AMBIGUOUS** | Transabdominal vs TRUS. Hospital must choose. |
| Transvaginal | Ultrasound of pelvis, transvaginal | `161278…` | Yes | **EXACT** | Not generic pelvic. |
| Doppler Studies | Several (obstetric doppler, renal artery, limb veins) | e.g. `6092cbe6-…` | Yes (many) | **AMBIGUOUS** | Form does not name the vessel. Do not pick obstetric doppler silently. |

### Radiography / Fluoroscopy (28)

| Hospital service | OpenMRS concept | UUID | Existing? | Match | Notes |
|---|---|---|---|---|---|
| Abdominal X-ray | X-ray, abdomen | `101A…` | Yes | **EXACT** | View-specific abdomen films also exist. Generic name matches the form. |
| Cervical Neck X-ray | X-ray of cervical spine, two or three views | `161301…` | Yes | **CLOSE** | Other cervical view sets exist. |
| Chest X-ray | Chest x-ray, single view | `165152…` | Yes | **CLOSE** | Used by ORD-6. Also `X-ray, chest` `12A…` and PA/lateral. Views **REQUIRES HOSPITAL DECISION**. |
| Lumbosacral Spine | X-ray of lumbosacral spine, two to three views | `165126…` | Yes | **EXACT** | Distinct from lumbar-only films. |
| Paranasal Sinuses | X-ray of paranasal sinuses, three views | `161341…` | Yes | **EXACT** | |
| Facial Bones/Mandible | Facial bones three views / mandible three views / Panorex | `161305…` / `165121…` / `161347…` | Yes (several) | **AMBIGUOUS** | Form is one line; concepts are different bones. |
| Pelvic X-ray | X-ray, pelvis | `392A…` | Yes | **EXACT** | View-specific pelvis films also exist. |
| Knee Joint | Left / right / both knee, several view sets | e.g. `161350…` | Yes (laterality) | **AMBIGUOUS** | No generic “X-ray, knee”. |
| Ankle Joint | Left / right / both ankle | e.g. `161266…` | Yes (laterality) | **AMBIGUOUS** | No generic ankle concept. |
| Paediatric X-ray | — | — | No | **MISSING** | Do not map to `X-ray, other`. Age is not a concept here. |
| Hysterosalpingography (HSG) | Hysterosalpingography (HSG), six views | `165136…` | Yes | **EXACT** | |
| Intravenous Urography (IVU) | X-ray of kidney with intravenous contrast, six to eight views | `165096…` | Yes | **CLOSE** | Synonym **Intravenous pyelogram (IVP)**. IVU/IVP are used interchangeably; confirm locally. |
| Retrograde Urethrography (RCUG) | — | — | No | **MISSING** | Retrograde **cystography** `165146…` is bladder, not urethra. Do not map. |
| Barium Enema | Barium enema | `164956…` | Yes | **EXACT** | Alternate: Flouroscopy of colon with barium `165144…`. Keep the named barium enema. |
| Skull X-ray | X-ray of skull | `386A…` | Yes | **EXACT** | 2-view and 4-view variants exist. |
| Thoracolumbar Spine | X-ray of thoracic and lumbar spine, two views | `161335…` | Yes | **CLOSE** | 4-view and standing-scoliosis variants exist. |
| Shoulder X-ray | X-ray, shoulder | `394A…` | Yes | **EXACT** | Laterality-specific shoulder films also exist. |
| Humeral X-ray | Left / right / bilateral upper arm (synonym humerus) | `161337…` / `161338…` / `161340…` | Yes (laterality) | **AMBIGUOUS** | No generic humerus concept. Do not use `X-ray, arm`. |
| Forearm X-ray | Left / right / bilateral forearm | `161324…` / `161325…` / `161326…` | Yes (laterality) | **AMBIGUOUS** | |
| Tibia & Fibula X-ray | Left / right lower leg | `161329…` / `161327…` | Yes (laterality) | **AMBIGUOUS** | Named as lower leg, not tibia+fibula. No generic. |
| Elbow X-ray | Left / right / bilateral elbow | `161302…` / `161303…` / `161304…` | Yes (laterality) | **AMBIGUOUS** | |
| Wrist/Hand/Finger X-ray | Hand / wrist (several); no finger film | `X-ray, hand` `382A…` plus laterality | Partial | **AMBIGUOUS** | Three sites on one form line. Do not collapse to hand. |
| Femoral X-ray | Left / right / bilateral femur | `161306…` / `161307…` / `161308…` | Yes (laterality) | **AMBIGUOUS** | |
| Thoracic Inlet | — | — | No | **MISSING** | Soft-tissue neck film is not thoracic inlet. |
| MCUG | Voiding urethrocystography | `164552…` | Yes | **EXACT** | Synonym **Voiding cystourethrogram**. |
| Temporomandibular Joint | — | — | No | **MISSING** | TMJ names in the dictionary are diagnoses, not imaging procedures. |
| Barium Meal | x-ray, upper gastrointestinal series | `159600…` | Yes | **EXACT** | Synonym **barium meal**. |
| Barium Follow Through | — | — | No | **MISSING** | Do not map to barium meal or barium enema. |

### Order type

Every mapped concept above is class **Radiology/Imaging Procedure**. Bahmni Clinical `otherInvestigationsMap` sends Radiology picks as **Radiology Order** `d3561dc0-5e07-11ef-8f7c-0242ac120002` (`org.openmrs.Order`).

They must **not** be Drug Order, Lab Order, Test Order, or a Hospital EMR-only order type.

ORD-6 confirms: concept `165152…` stored as Radiology Order on a Consultation encounter.

### Existing order API (not implemented in this phase)

```
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
```

Required: `patientUuid`, **selected** `visitUuid`, Consultation `encounterTypeUuid`, `locationUuid`, `providers`, `orders[]`.

Each imaging order:

```json
{
  "concept": { "name": "<concept-name>", "uuid": "<concept-uuid>" },
  "commentToFulfiller": "",
  "urgency": "STAT"
}
```

`urgency` is `"STAT"` only when marked urgent; otherwise omit.

Visit association:

**Patient → Visit → Encounter → Radiology Order**

`orders.encounter_id` → `encounter.visit_id`. The order row has no `visitUuid`. Do not attach to the first open visit, the most recent visit, a billed visit, or another patient. When write is implemented, the Doctor route `patientUuid` + `visitUuid` is authoritative.

Do not POST raw `/order`.

---

## Odoo TEST Product Mapping

Billing architecture **unchanged**:

```
Radiology Order → Radiology Desk (sale.shop id 5) → Odoo → Accountant
charge key: radiology:{orderUuid}
```

No Reception billing. No second ledger. No Doctor Pay button. Prices and currency were **not** changed.

Live Radiology category: **258** active products. **257** placeholders at **$1.00 USD** (Hospital EMR refuses `list_price ≤ 1.01`). **1** TEST-priced product.

Catalogue products store `product.product.uuid` = OpenMRS concept uuid. They are **not** TEST products.

| Hospital service | OpenMRS concept | Odoo product | Product ID | TEST price | Currency | Match | Status |
|---|---|---|---|---:|---|---|---|
| Obstetrics (Pregnancy) | Obstetric ultrasound | Catalogue placeholder | 1489 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Pelvic | Ultrasound of pelvis | Catalogue placeholder | 1384 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Breast | Left / right breast US | Placeholders 1352 / 1347 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Abdominopelvic | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Biophysical Profile (BPP) | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Thyroid/Neck | Thyroid / head and neck | Placeholders 689 / 1374 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Anomaly Scan | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Eye/Ocular | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Scrotal/Testicular | Ultrasound of scrotum and testicle | Catalogue placeholder | 1404 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Musculoskeletal | Ultrasound of extremity | Catalogue placeholder | 1416 | — | USD | CLOSE concept | **MISSING TEST PRODUCT** |
| Follicular Tracking | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Prostate | Prostate / TRUS | Placeholders 686 / 1408 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Transvaginal | Ultrasound of pelvis, transvaginal | Catalogue placeholder | 1411 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Doppler Studies | Several doppler products | e.g. 672 obstetric doppler | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Abdominal X-ray | X-ray, abdomen | Catalogue placeholder | 1506 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Cervical Neck X-ray | Cervical spine 2–3 views | Catalogue placeholder | 1274 | — | USD | CLOSE concept | **MISSING TEST PRODUCT** |
| Chest X-ray | Chest x-ray, single view | **Chest x-ray, single view — TEST** | **2392** | **60.00** | **USD** | CLOSE concept | **EXISTS** (isolated TEST) |
| Chest X-ray (catalogue) | same concept | Chest x-ray, single view | 845 | 1.00 | USD | — | Placeholder; billing refuses it |
| Lumbosacral Spine | LS spine 2–3 views | Catalogue placeholder | 946 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Paranasal Sinuses | PNS three views | Catalogue placeholder | 1363 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Facial Bones/Mandible | Several | e.g. 1261 / 969 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Pelvic X-ray | X-ray, pelvis | Catalogue placeholder | 630 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Knee Joint | Laterality-specific | e.g. 1308 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Ankle Joint | Laterality-specific | e.g. 1463 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Paediatric X-ray | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| HSG | HSG six views | Catalogue placeholder | 909 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| IVU | Kidney IV contrast 6–8 views | Catalogue placeholder | 847 | — | USD | CLOSE concept | **MISSING TEST PRODUCT** |
| RCUG | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Barium Enema | Barium enema | Catalogue placeholder | 1069 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Skull X-ray | X-ray of skull | Catalogue placeholder | 641 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Thoracolumbar Spine | T/L spine two views | Catalogue placeholder | 1388 | — | USD | CLOSE concept | **MISSING TEST PRODUCT** |
| Shoulder X-ray | X-ray, shoulder | Catalogue placeholder | 627 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Humeral X-ray | Laterality-specific | e.g. 1379 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Forearm X-ray | Laterality-specific | e.g. 1448 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Tibia & Fibula X-ray | Laterality-specific lower leg | e.g. 1424 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Elbow X-ray | Laterality-specific | e.g. 1271 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Wrist/Hand/Finger X-ray | Partial (hand/wrist) | e.g. 646 hand | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Femoral X-ray | Laterality-specific | e.g. 1255 | — | — | USD | AMBIGUOUS | **MISSING TEST PRODUCT** |
| Thoracic Inlet | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| MCUG | Voiding urethrocystography | Catalogue placeholder | 1052 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Temporomandibular Joint | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |
| Barium Meal | Upper GI series (syn. barium meal) | Catalogue placeholder | 1494 | — | USD | EXACT concept | **MISSING TEST PRODUCT** |
| Barium Follow Through | — | — | — | — | — | MISSING concept | **MISSING TEST PRODUCT** |

No prices were invented. Do not treat $1.00 catalogue rows as TEST prices.

### ORD-6 (read only)

| Step | Live |
|---|---|
| OpenMRS | Radiology Order **ORD-6** `46e6031f-…`, concept **Chest x-ray, single view** `165152…`, Consultation `838290e9-…`, visit `020a5cfe-…`, patient ABC200007 |
| Radiology Desk | Shop id **5** |
| Odoo | Sale **S00007**, line product **2392** TEST $60, origin = visit uuid, key `radiology:46e6031f-…` |
| Invoice | **INV/2026/00006** paid, residual 0 |

Do not perform the scan. Do not modify the order.

---

## Final Service Readiness

| Code | Meaning |
|---|---|
| **A** | Hospital-approved + safe OpenMRS concept + TEST product |
| **B** | Hospital-approved + safe OpenMRS concept + missing TEST product |
| **C** | Hospital-approved + no safe OpenMRS concept |
| **D** | Ambiguous mapping; hospital must decide |

### A — ready for later TEST ordering (1)

| Service | Concept | TEST product |
|---|---|---|
| Chest X-ray | Chest x-ray, single view `165152…` | 2392 · $60 USD |

Hospital should still confirm whether “Chest X-ray” means single view, PA/lateral, or another protocol.

### B — concept usable; no TEST product (18)

Obstetrics (Pregnancy); Pelvic; Scrotal/Testicular; Musculoskeletal (CLOSE); Transvaginal; Abdominal X-ray; Cervical Neck X-ray (CLOSE); Lumbosacral Spine; Paranasal Sinuses; Pelvic X-ray; HSG; IVU (CLOSE); Barium Enema; Skull X-ray; Thoracolumbar Spine (CLOSE); Shoulder X-ray; MCUG; Barium Meal.

### C — missing concept (10)

Abdominopelvic; Biophysical Profile (BPP); Anomaly Scan; Eye/Ocular; Follicular Tracking; Paediatric X-ray; Retrograde Urethrography (RCUG); Thoracic Inlet; Temporomandibular Joint; Barium Follow Through.

### D — hospital must choose (13)

Breast (left vs right); Thyroid/Neck; Prostate (TA vs TRUS); Doppler Studies (territory); Facial Bones/Mandible; Knee Joint; Ankle Joint; Humeral X-ray; Forearm X-ray; Tibia & Fibula X-ray; Elbow X-ray; Wrist/Hand/Finger X-ray; Femoral X-ray.

Plus Chest X-ray **views** if they reject single-view as the hospital protocol.

### Counts

| Readiness | n |
|---|---|
| A | 1 |
| B | 18 |
| C | 10 |
| D | 13 |
| **Approved Radiology/US lines** | **42** |

1 + 18 + 10 + 13 = 42. Good. Update the B/C headings.

### Hospital decisions still required before a Doctor picker

1. Confirm Chest X-ray protocol (single view vs PA/lateral vs generic `X-ray, chest`).
2. Laterality rule for limb films (always ask left/right, or create generic concepts — **do not invent concepts in this phase**).
3. Breast, Thyroid/Neck, Prostate, Doppler, Facial Bones/Mandible, Wrist/Hand/Finger: one hospital line vs several OpenMRS exams.
4. Whether to **configure** missing concepts (BPP, anomaly, ocular, follicular, paediatric, RCUG, thoracic inlet, TMJ, barium follow-through, abdominopelvic) — hospital + implementer, not Hospital EMR invention.
5. TEST products for the B (and later A) list; NGN vs USD; tax. Do not use $1.00 placeholders.
6. Cardiology / Pathology / Special Service workflows remain separate.

The five earlier clinical clarification questions are **superseded**. The hospital has now approved the names as supplied and a radiologist-set price per order.

---

## Hospital Decision — Final Radiology Workflow

Date: **24 Aug 2026**.

- **Hospital scan names are authoritative.** The 42 Ultrasound and Radiography / Fluoroscopy names on the supplied referral form are the menu.
- **Side or Area is asked only when OpenMRS has no generic concept** for that hospital line (for example Knee Joint → Right / Left / Bilateral). The Doctor still sees the hospital name, not the OpenMRS concept name.
- **Radiologist sets price per order/visit.** The Doctor does not enter a price. The existing TEST product `Chest x-ray, single view — TEST` ($60 USD) is **not** a hospital-wide price.
- **Accountant collects payment.** Radiology and Clinical do not collect money. Charge key remains `radiology:{orderUuid}`.
- **NGN is used for new Radiology charges.** Company currency is unchanged. Pharmacy, Registration, Laboratory, and Consultation billing currencies are unchanged.
- **Existing ORD-6 TEST product remains historical and unchanged.** Order `46e6031f-…`, product 2392, S00007 / INV/2026/00006 stay as isolated TEST evidence.
- **Selected visitUuid remains authoritative.** Write path is `POST /bahmnicore/bahmniencounter` `orders[]` on the Consultation encounter of the selected visit. No first-open / latest / billed fallback.

### What Hospital EMR can order today

**All 42** hospital-approved services. See **Hospital-Approved 42-Service Radiology Menu** below.

PACS, DICOM, and the Radiology Worklist were not added.

`radiology.abikan` still does **not** have OpenMRS **Get Orders** (REST `GET /order/{uuid}` is 403). The Radiology Desk already reads `bahmnicore/orders` and **Get Visits**. Pricing uses those existing reads. **Get Orders** and `app:orders` were not granted.

---

## Hospital-Approved 42-Service Radiology Menu

Date: **25 Aug 2026**. Development configuration so every hospital-approved name can be ordered through the existing Doctor → Radiology path.

Orders still use `POST /openmrs/abikan-api/radiology/patient/{patientUuid}/orders` with the **selected** `visitUuid`. No patient-only fallback. No Radiologist appointment. No catalogue prices. Radiologist still sets NGN per order. Radiology Notes remain the report.

### How each service was resolved

| Code | Meaning |
|---|---|
| **A** | Existing safe Radiology/Imaging Procedure concept reused |
| **C** | New OpenMRS Radiology/Imaging Procedure concept created with the hospital name |
| **D** | Existing laterality- or site-specific concepts; Doctor chooses Side or Area |

No service remained **E**. No concept was chosen because the name was only vaguely similar.

| Hospital Service | Category | OpenMRS Concept | Match | Configuration | Ordering Option |
|---|---|---|---|---|---|
| Obstetrics (Pregnancy) | Ultrasound Scan | Obstetric ultrasound `159618…` | EXACT | Reused | — |
| Pelvic | Ultrasound Scan | Ultrasound of pelvis `161283…` | EXACT | Reused | — |
| Breast | Ultrasound Scan | Ultrasound of right/left breast `161290…` / `161289…` | CLOSE | Reused | Side: Right / Left (no bilateral concept) |
| Abdominopelvic | Ultrasound Scan | Abdominopelvic `32f23df0-…` | EXACT | Created | — |
| Biophysical Profile (BPP) | Ultrasound Scan | Biophysical Profile (BPP) `555f0bdd-…` | EXACT | Created | — |
| Thyroid/Neck | Ultrasound Scan | Thyroid/Neck `4b374fce-…` | EXACT | Created | — |
| Anomaly Scan | Ultrasound Scan | Anomaly Scan `012ba652-…` | EXACT | Created | — |
| Eye/Ocular | Ultrasound Scan | Eye/Ocular `4497c384-…` | EXACT | Created | — |
| Scrotal/Testicular | Ultrasound Scan | Ultrasound of scrotum and testicle `161279…` | EXACT | Reused | — |
| Musculoskeletal | Ultrasound Scan | Ultrasound of extremity `161277…` | CLOSE | Reused | — |
| Follicular Tracking | Ultrasound Scan | Follicular Tracking `b83c6817-…` | EXACT | Created | — |
| Prostate | Ultrasound Scan | Ultrasound of prostate `ee40db9c-…` | EXACT | Reused | — |
| Transvaginal | Ultrasound Scan | Ultrasound of pelvis, transvaginal `161278…` | EXACT | Reused | — |
| Doppler Studies | Ultrasound Scan | Doppler Studies `c3e07bb5-…` | EXACT | Created | — |
| Abdominal X-ray | Radiography / Fluoroscopy | X-ray, abdomen `101A…` | EXACT | Reused | — |
| Cervical Neck X-ray | Radiography / Fluoroscopy | X-ray of cervical spine, two or three views `161301…` | CLOSE | Reused | — |
| Chest X-ray | Radiography / Fluoroscopy | Chest x-ray, single view `165152…` | CLOSE | Reused | — |
| Lumbosacral Spine | Radiography / Fluoroscopy | X-ray of lumbosacral spine, two to three views `165126…` | EXACT | Reused | — |
| Paranasal Sinuses | Radiography / Fluoroscopy | X-ray of paranasal sinuses, three views `161341…` | EXACT | Reused | — |
| Facial Bones/Mandible | Radiography / Fluoroscopy | Facial bones three views `161305…` / mandible three views `165121…` | CLOSE | Reused | Area: Facial Bones / Mandible |
| Pelvic X-ray | Radiography / Fluoroscopy | X-ray, pelvis `392A…` | EXACT | Reused | — |
| Knee Joint | Radiography / Fluoroscopy | Right / left / bilateral knee 1–2 views `161349…` / `161350…` / `161352…` | CLOSE | Reused | Side: Right / Left / Bilateral |
| Ankle Joint | Radiography / Fluoroscopy | Right / left / both ankle 2 views `161267…` / `161266…` / `161268…` | CLOSE | Reused | Side: Right / Left / Bilateral |
| Paediatric X-ray | Radiography / Fluoroscopy | Paediatric X-ray `e00d6245-…` | EXACT | Created | — |
| Hysterosalpingography (HSG) | Radiography / Fluoroscopy | HSG, six views `165136…` | EXACT | Reused | — |
| Intravenous Urography (IVU) | Radiography / Fluoroscopy | Kidney IV contrast 6–8 views `165096…` | CLOSE | Reused | — |
| Retrograde Urethrography (RCUG) | Radiography / Fluoroscopy | Retrograde Urethrography (RCUG) `11444779-…` | EXACT | Created | — |
| Barium Enema | Radiography / Fluoroscopy | Barium enema `164956…` | EXACT | Reused | — |
| Skull X-ray | Radiography / Fluoroscopy | X-ray of skull `386A…` | EXACT | Reused | — |
| Thoracolumbar Spine | Radiography / Fluoroscopy | T/L spine two views `161335…` | CLOSE | Reused | — |
| Shoulder X-ray | Radiography / Fluoroscopy | X-ray, shoulder `394A…` | EXACT | Reused | — |
| Humeral X-ray | Radiography / Fluoroscopy | Right / left / bilateral upper arm `161338…` / `161337…` / `161340…` | CLOSE | Reused | Side: Right / Left / Bilateral |
| Forearm X-ray | Radiography / Fluoroscopy | Right / left / bilateral forearm `161325…` / `161324…` / `161326…` | CLOSE | Reused | Side: Right / Left / Bilateral |
| Tibia & Fibula X-ray | Radiography / Fluoroscopy | Right / left lower leg two views `161327…` / `161329…` | CLOSE | Reused | Side: Right / Left (no bilateral lower-leg concept) |
| Elbow X-ray | Radiography / Fluoroscopy | Right / left / bilateral elbow `161303…` / `161302…` / `161304…` | CLOSE | Reused | Side: Right / Left / Bilateral |
| Wrist/Hand/Finger X-ray | Radiography / Fluoroscopy | Wrist/Hand/Finger X-ray `7a9da21d-…` | EXACT | Created | — |
| Femoral X-ray | Radiography / Fluoroscopy | Right / left / bilateral femur `161307…` / `161306…` / `161308…` | CLOSE | Reused | Side: Right / Left / Bilateral |
| Thoracic Inlet | Radiography / Fluoroscopy | Thoracic Inlet `1b85a1cc-…` | EXACT | Created | — |
| Micturating (Voiding) Cystourethrography (MCUG) | Radiography / Fluoroscopy | Voiding urethrocystography `164552…` | EXACT | Reused | — |
| Temporomandibular Joint | Radiography / Fluoroscopy | Temporomandibular Joint `b870eda8-…` | EXACT | Created | — |
| Barium Meal | Radiography / Fluoroscopy | Upper GI series `159600…` | EXACT | Reused | — |
| Barium Follow Through | Radiography / Fluoroscopy | Barium Follow Through `00f0b2b0-…` | EXACT | Created | — |

### Concepts reused

The original 19 safe mappings, plus **Prostate** → Ultrasound of prostate (generic hospital line; transrectal ultrasound was not selected). Laterality and Facial Bones/Mandible options reuse existing imaging concepts already in **All Radiology orders**.

### Concepts created

13 hospital-named Radiology/Imaging Procedure concepts (N/A datatype), added to **All Radiology orders** (266 → 279). Odoo received product **stubs** (`uuid` = concept, `list_price` 0) so the existing Radiologist charge path can attach `radiology:{orderUuid}`. Those zeros are **not** hospital fees.

Abdominopelvic; Biophysical Profile (BPP); Anomaly Scan; Eye/Ocular; Follicular Tracking; Doppler Studies; Thyroid/Neck; Paediatric X-ray; Retrograde Urethrography (RCUG); Thoracic Inlet; Temporomandibular Joint; Barium Follow Through; Wrist/Hand/Finger X-ray.

### Duplicate concepts avoided

Did **not** map Abdominopelvic to abdomen or pelvis ultrasound, or to CT abdomen/pelvis. Did **not** map Anomaly Scan or BPP to Obstetric ultrasound. Did **not** map RCUG to retrograde cystography. Did **not** map Barium Follow Through to barium meal. Did **not** map Doppler Studies to obstetric or renal Doppler. Did **not** map Wrist/Hand/Finger to generic hand. Did **not** map Thyroid/Neck to thyroid-only or head-and-neck-only. Did **not** create generic limb films when laterality concepts already exist.

### Ambiguous services

| Hospital service | Resolution |
|---|---|
| Breast | Side Right / Left. No bilateral breast ultrasound concept. |
| Thyroid/Neck | Created one hospital-named concept. Not thyroid-only or neck-only. |
| Prostate | Reused generic Ultrasound of prostate. Not TRUS. |
| Doppler Studies | Created one hospital-named concept. No vessel picked. |
| Facial Bones/Mandible | Area Facial Bones / Mandible. Panorex excluded. |
| Knee, Ankle, Humeral, Forearm, Elbow, Femoral | Side Right / Left / Bilateral using the standard 1–2 view concepts. |
| Tibia & Fibula X-ray | Side Right / Left using lower-leg films. No bilateral lower-leg concept; Bilateral was not invented. |
| Wrist/Hand/Finger X-ray | Created one hospital-named concept. Not collapsed to hand. |

Doctor still sees the hospital name. Side or Area appears only when required. After ordering, lists show `Knee Joint — Right` so laterality does not leak between orders.

### Unresolved

None of the 42 remains unavailable.

### Protected TEST records

ORD-6, ORD-14, ORD-15, ORD-16, ORD-17, ORD-18, ORD-19 and INV/2026/00006, 00031, 00032, 00033, 00034 were not modified.

### Live verification (25 Aug 2026)

Doctor (`doctor.abikan`) opened ABC200016, selected Visit **#002** (`a70cbb56-…`), and confirmed both categories with all 42 hospital names. No “Not available yet”. No Doctor price field.

Through the existing Doctor order path:

| Order | Examination | Visit | Concept |
|---|---|---|---|
| ORD-20 `dd38e74a-…` | Abdominopelvic | #002 `a70cbb56-…` | Created hospital concept |
| ORD-21 `3a1ac447-…` | Thoracic Inlet | #002 `a70cbb56-…` | Created hospital concept |

Visit #001 still showed only ORD-19 and ORD-14. No leak onto ABC200018.

Radiologist (`radiology.abikan`) saw both new orders on Visit #002, Price pending, Report pending. Set **₦13,333** on ORD-20 through the existing Set Price path. Charge key `radiology:dd38e74a-…`. Sale S00036 / INV/2026/00035 unpaid. The product stub list price was not billed. ORD-21 left Price pending. No report written. Payment not collected.

ORD-16 Radiology Notes (`TEST RADIOLOGY REPORT — DEVELOPMENT ONLY`) and ORD-19 (`TEST REPORT — DEVELOPMENT ONLY`) remain bound to those orders.

---

## Tests / build

`npm test` — 227 passed. `npm run build` succeeded.

Isolated TEST orders created on ABC200016 (do not treat as scans; do not delete unless a safe cleanup path exists):

- ORD-14 Obstetrics (Pregnancy) on Visit #001 — first pricing attempt used Public USD because `many2one_id` dropped the NGN pricelist id. **Corrected 24 Aug 2026:** INV/2026/00031 fully refunded via Odoo `account.move.reversal` (`refund_method=cancel`) → `payment_state=reversed`, residual 0. Credit note `RINV/2026/00001`. Sale S00032 cancelled. Charge key `radiology:c09b9e2f-…` released. Radiology now shows **Price pending**. Not re-priced. Not ORD-6.
- ORD-15 Pelvic on Visit #002 — ₦2,500, Radiology Desk NGN pricelist, INV/2026/00032 unpaid. Unchanged by the ORD-14 correction.

ORD-6 / product 2392 / S00007 / INV/2026/00006 remain $60 USD paid on ABC200007.
