# Hospital EMR laboratory workflow

Source of truth: this Bahmni-standard deployment (OpenMRS 1.1.2, OpenELIS 1.0.0, bahmnicore 1.2.0, openelis-atomfeed-client 1.2.0), live **GET** probes, and read-only MySQL / PostgreSQL. No laboratory orders, samples, or results were created during this investigation.

Do not invent a second laboratory database. OpenELIS is the laboratory engine. OpenMRS is the clinical chart. Hospital EMR is the product UI around both.

Related: `docs/CLINICAL_WRITE_API.md` (how a doctor order is saved on a consultation). Laboratory **writes** (sample collection, result entry, verification) are **not** implemented in Hospital EMR.

## P0 worklist and correlation behavior — 26 Aug 2026

The Hospital EMR backend now reads:

`POST /openelis/ws/rest/accession/{encounterUuid}` with server-held integration credentials.

The response's `testDetails[].status` is authoritative for board grouping. Hospital EMR preserves the source term and maps only installed terms:

- Pending: `Not started`, `Not Tested`, `SampleEntered`, `Test Entered`
- Processing: `Testing Started`, `Testing finished`, `Technical Acceptance`, `Technical Acceptance RO`
- Completed: `Results final`, `Finalized`, `Finalized RO`, `Marked As Done`
- Any unrecognized, rejected, cancelled, unavailable, or safely unmatched state: Unknown / review required, not an invented stage

The OpenMRS order `accessionNumber` contains the source encounter UUID in this integration. It is not a laboratory accession or analysis status and is no longer used to classify work.

OpenELIS does not carry the OpenMRS order UUID on an analysis. When an encounter contains duplicate orders for the same test concept, Hospital EMR keeps both OpenMRS orders as separate rows and marks their result mapping ambiguous. A finalized laboratory state may appear under Completed, but neither order claims the first-wins returned result as safely correlated. New same-test duplicates on one Consultation are blocked; historical ORD-9 and ORD-10 are unchanged.

OpenELIS result return remains unchanged:

`OpenELIS Finalized → OpenMRS LAB_RESULT → bahmnicore/labOrderResults → Hospital EMR`

Hospital EMR performs no OpenELIS write operation.

### Laboratory order detail — 26 Aug 2026

The worklist and the order detail page now share one server read path:

`GET /openmrs/abikan-api/laboratory/order/{orderUuid}?patient={patientUuid}&visit={visitUuid}`

- Requires Laboratory workspace authorization (`require_lab_user`).
- Loads the exact OpenMRS order UUID through `load_lab_order` (same helper as the board).
- Validates optional `patient` and `visit` query parameters; mismatches return safe 409 responses.
- Does not call `bahmnicore/orders` from the browser and does not expose OpenELIS credentials.
- Worklist **Open** carries `patientUuid` + `visitUuid` + `orderUuid` in the hash query string.

Sample collection and result entry remain in OpenELIS only.

**Deployment:** the `abikan-api` container loads Python modules at startup. After changing `server.py` or `laboratory.py`, restart that service (`docker compose restart abikan-api`). If Action → Open shows “This laboratory order was not found” while the worklist loads, check the detail request: a generic `404` with code `not_found` means the running API process is stale, not that the OpenMRS order is missing.

Status labels used below:

- **CONFIRMED** — observed in this installation
- **UNKNOWN** — not established from source or live probes
- **COMING SOON** — Hospital EMR UI placeholder; no backend write

---

## Architecture (this installation)

```
Doctor consultation
  POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
  orders[]  (order type Lab Order, optional urgency STAT)
        ↓
  OpenMRS order + encounter
  Atom feed  /openmrs/ws/atomfeed/encounter/recent
  Atom feed  /openmrs/ws/atomfeed/patient/recent
  Atom feed  /openmrs/ws/atomfeed/lab/recent   (test/panel/sample catalogue)
        ↓
  OpenELIS atomfeed client  (openelis container)
  Patient identity  ST number = OpenMRS Patient Identifier (e.g. ABC200012)
  Sample + analysis created in OpenELIS
        ↓
  OpenELIS screens (not Hospital EMR, not Lab Lite)
  Sample entry → Results entry → Validation
        ↓
  OpenELIS accession atom feed
  openelis-atomfeed-client on OpenMRS
        ↓
  LAB_RESULT / INVESTIGATION encounters + obs on the OpenMRS patient
        ↓
  GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid=
  Doctor chart / Hospital EMR Laboratory patient view
```

**CONFIRMED:** Bahmni Lab Lite (`/lab`, privilege `app:lab-lite`) is configured in home `extension.json` as **hidden**. The proxy still has `ProxyPass /lab http://bahmni-lab:80/lab`, but **no `bahmni-lab` container is running**. The operational laboratory application is **OpenELIS** at `/openelis`.

---

## 1. Current Bahmni laboratory architecture

**CONFIRMED**

| Piece | This deployment |
|---|---|
| OpenELIS | container `bahmni-standard-openelis-1`, image `bahmni/openelis:1.0.0`, proxied `/openelis` → `openelis:8052/openelis` |
| OpenELIS DB | `clinlims` on `bahmni-standard-openelisdb-1` |
| OpenMRS lab client | `openelis-atomfeed-client-1.2.0.omod` (`elisatomfeedclient.started` = true) |
| Bahmni Core | `bahmnicore-1.2.0.omod` — orders + `labOrderResults` |
| Clinical Orders tab | privilege `app:clinical:ordersTab`; `enableLabOrderOptions`: `Urgent`, `NeedsPrint` |
| Orders app | `/bahmni/orders` — this config’s extension is **Radiology Order** fulfillment, not OpenELIS |
| Lab Lite MFE | home tile `bahmni.lab` **hidden**; `/lab` backend **not running** |
| Login locations | Registration Desk, OPD-1, OPD-2, Emergency, General Ward, Pediatric Ward. **No Laboratory location** |

Home white-label still lists OpenELIS as an external app (`/openelis`).

---

## 2. OpenELIS integration

**CONFIRMED**

OpenELIS consumes OpenMRS atom feeds (from `atomfeed.properties` in the OpenELIS war):

| Feed | URI |
|---|---|
| Patients | `http://openmrs:8080/openmrs/ws/atomfeed/patient/recent` |
| Encounters (includes lab orders on a consultation) | `http://openmrs:8080/openmrs/ws/atomfeed/encounter/recent` |
| Lab catalogue | `http://openmrs:8080/openmrs/ws/atomfeed/lab/recent` |

OpenELIS marker table currently tracks those three feeds. OpenMRS `event_records` category `lab` is **catalogue** events (`test`, `panel`, `sample`, `department`, `radiology`, `all-samples`), not patient orders.

Results return the other way: OpenMRS `OpenElisAccessionEventWorker` reads an accession payload (`OpenElisAccession` / `OpenElisTestDetail`) and writes OpenMRS encounters (`LAB_RESULT`, accession notes). Encounter types **CONFIRMED** live:

| Name | UUID |
|---|---|
| INVESTIGATION | `d3b3a2b9-5e07-11ef-8f7c-0242ac120002` |
| LAB_RESULT | `d3bf1623-5e07-11ef-8f7c-0242ac120002` |

OpenELIS web UI is Struts/JSP (`SampleEntry`, `ResultsEntry`, `ResultValidation`, dashboard). `web.xml` maps `/ws/*` (atomfeed), not a documented public REST work-queue API for Hospital EMR.

Live probe of `http://openelis:8052/openelis/ws/feed/patient/recent` returned **HTTP 401** (auth required). **UNKNOWN:** exact OpenELIS accession JSON URL path beyond what `openelis-atomfeed-client` already consumes internally.

---

## 3. Laboratory order flow

**CONFIRMED**

1. Doctor saves consultation with `orders[]` on `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` (same EncounterTransaction as vitals).
2. Order type **Lab Order** UUID: `d3560b17-5e07-11ef-8f7c-0242ac120002`.
3. Payload fields from clinical mapper (see clinical write doc):

```json
{
  "concept": { "name": "<concept-name>", "uuid": "<concept-uuid>" },
  "commentToFulfiller": "",
  "urgency": "STAT"
}
```

`urgency` is `"STAT"` only when marked Urgent; otherwise omitted (routine).

4. OpenELIS creates the accession/sample from the encounter feed.

**CONFIRMED on this database:** `orders` table in OpenMRS has **0** rows. OpenELIS `orders` / `sample` / `analysis` / `result` have **0** rows. There are currently **no laboratory orders to display**.

Concept set `All_Tests_and_Panels` exists (`d3e6fb5f-5e07-11ef-8f7c-0242ac120002`) but `setMembers` is **empty**. OpenMRS has 622 concepts class **Test** and 84 **LabSet**. OpenELIS has 622 tests and 84 panels (catalogue synced). Do not hardcode test names in Hospital EMR.

---

## 4. Sample flow

**CONFIRMED (OpenELIS model)**

```
Location-tagged tests in OpenMRS catalogue
  → OpenELIS type_of_sample (37 active specimen types)
  → sample + sample_item
  → analysis (test on that sample)
```

Specimen types are **data in OpenELIS**, including Blood Specimen, Urine, Serum, Plasma, Sputum, Feces, Whole blood sample, and others. **Do not hardcode** a short Blood/Urine/Stool list in Hospital EMR as the hospital catalogue.

Sample / analysis statuses in `status_of_sample` (not Hospital EMR UI labels):

| OpenELIS name | Meaning (from `description`) |
|---|---|
| SampleEntered | Sample entered |
| Test Entered | No tests have been run for this order |
| Testing Started | Some tests have been run |
| Testing finished | All tests have been run |
| Technical Acceptance | Technician accepted the result |
| Technical Rejected | Technician did not accept |
| Finalized | Results are final |
| Biologist Rejection | Biologist did not accept |
| Test Canceled / SampleCanceled | Cancelled |

There is **no** OpenMRS REST resource that lists “samples awaiting collection” for the hospital.

**COMING SOON** in Abikan: Collect Sample write.

**UNKNOWN:** whether Bahmni/OpenELIS on this site uses a distinct “collected vs not collected” flag beyond SampleEntered. Zero samples exist to observe.

---

## 5. Result flow

**CONFIRMED**

| Step | Where |
|---|---|
| Result entry | OpenELIS `ResultsEntry` / `LogbookResults` (role **Results entry**) |
| Technician name required | site_information `ResultTechnicianName` = **true** |
| Invalid-range alert | `alertWhenInvalidResult` = **true** |
| Validation required for all results | `validate all results` = **true** |
| Validation UI | OpenELIS `ResultValidation` (role **Validation**) |
| Modify after entry | separate role **Results modifier**; `modify results role` = **true**; note required |
| Return to EMR | accession feed → `LAB_RESULT` encounter + obs |
| Doctor / Hospital EMR read | `GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid=` |

`LabOrderResult` fields (from `bahmni-emr-api`): `orderUuid`, `accessionUuid`, `accessionDateTime`, `testName`, `testUnitOfMeasurement`, `testUuid`, `panelName`, `minNormal`, `maxNormal`, `result`, `abnormal`, `notes`, `provider`, `referredOut`, `resultDateTime`, `uploadedFileName`, `action`, accession notes.

Abnormal is a **boolean from OpenMRS/OpenELIS**, not a High/Low/Critical enum. Display that flag. Do not invent critical thresholds in Hospital EMR.

Draft / Entered / Verified / Released are **not** OpenMRS REST states. Closest OpenELIS names: Test Entered, Technical Acceptance, Finalized. Do not present Hospital EMR-invented result-status enums as live data.

Reference ranges: OpenELIS `result_limits` has **56** rows. They must come from the lab system, never from Hospital EMR constants.

---

## 6. Patient identity mapping

**CONFIRMED**

- OpenMRS patient UUID is the Hospital EMR identity (`#/laboratory/patient/{uuid}`).
- OpenELIS `patient_identity` type **ST** holds the OpenMRS identifier (ABC200000 … ABC200012). 11 ST rows; John Adewale is **ABC200012** in both systems.
- Accession payload also carries `patientUuid` and `patientIdentifier` (`OpenElisAccession`).
- Do not create a second MRN.

---

## 7. APIs discovered

### Reads (safe; probed)

| Purpose | Method | Endpoint | Live result |
|---|---|---|---|
| Lab orders for a patient | GET | `/openmrs/ws/rest/v1/bahmnicore/orders?patientUuid={uuid}&orderTypeUuid=d3560b17-5e07-11ef-8f7c-0242ac120002` | `[]` for John Adewale |
| Order by uuid | GET | `/openmrs/ws/rest/v1/bahmnicore/orders?orderUuid=` | controller supports `orderUuid` |
| Lab results for a patient | GET | `/openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid=` | `{ results: [], tabularResult: { dates, orders, values } }` |
| Order types | GET | `/openmrs/ws/rest/v1/ordertype` | includes Lab Order |
| Standard order list | GET | `/openmrs/ws/rest/v1/order` | **getAll not supported** (needs a patient) |
| OpenMRS REST `v1/lab` | GET | `/openmrs/ws/rest/v1/lab` | **Unknown resource** |
| Lab Lite | GET | `/lab` | proxy target **not running** |
| OpenELIS UI | | `/openelis` | Struts app, separate login |
| Atom feeds | GET | `/openmrs/ws/atomfeed/{patient\|encounter\|lab}/recent` | 200 XML |

`GET /openmrs/ws/rest/v1/order?t=laborder` is **not** a valid search handler.

There is **no CONFIRMED hospital-wide pending-order queue API** on OpenMRS. OpenELIS dashboard is the operational queue, behind OpenELIS auth, not OpenMRS REST.

### Writes (from source — **not executed**)

| Action | Mechanism | Hospital EMR |
|---|---|---|
| Doctor order | `POST …/bahmnicore/bahmniencounter` `orders[]` | **COMING SOON** (already documented in clinical write API) |
| Sample collection | OpenELIS SampleEntry | **COMING SOON** — no Hospital EMR write |
| Result entry | OpenELIS ResultsEntry | **COMING SOON** |
| Verification | OpenELIS ResultValidation | **COMING SOON** |

Do not POST to OpenELIS from Hospital EMR until a supported API is confirmed. Do not write `obs` / `order` directly.

---

## 8. Relevant Bahmni source files

| Role | Path |
|---|---|
| Lab results REST | `bahmnicore` `BahmniLabOrderResultController` `/rest/v1/bahmnicore/labOrderResults` |
| Orders REST | `BahmniOrderController` `/rest/v1/bahmnicore/orders` |
| Accession → EMR | `openelis-atomfeed-client` `OpenElisAccessionEventWorker` |
| Clinical order save | Bahmni Clinical JS `orders[]` on encounter transaction |
| Home tiles | `abikan-config/openmrs/apps/home/extension.json`, `whiteLabel.json` |
| Clinical lab display | `abikan-config/openmrs/apps/clinical/dashboard.json` `labResults` type `labOrders` |
| Proxy | `/usr/local/apache2/conf/bahmni-proxy.conf` |
| OpenELIS atomfeed | `/run/bahmni-lab/bahmni-lab/WEB-INF/classes/atomfeed.properties` |

---

## 9. OpenELIS source / API information

**CONFIRMED**

- UI pages under `/run/bahmni-lab/bahmni-lab/pages/` (`sample`, `result`, `resultvalidation`, `dashboard`, `patient`, …).
- Roles: Intake, Results entry, Results modifier, Validation, LabDashboard, Reports, …
- Modules include `SampleEntry`, `SampleConfirmationEntry`, `ResultsEntry`, `ResultValidation`, `ResultValidation:All Sections`.
- OpenELIS has its own `system_user` / `login_user` and separate session. OpenMRS/Hospital EMR accounts do not sign in without a corresponding OpenELIS account.
- The hospital's dedicated named OpenELIS Laboratory Administrator is created manually through OpenELIS Manage Users with `Maintenance Admin` and `is_admin = N`. This broad role provides user and catalogue administration; it is not granted to Hospital EMR Hospital Admin.
- Individual processing accounts receive only the roles needed for Intake, Results entry, Validation, and dashboard access. See `OPENELIS_LABORATORY_ADMINISTRATION.md`.

---

## 10. Authentication / session

**CONFIRMED**

- Hospital EMR uses the OpenMRS session cookie (`credentials: include`) for `bahmnicore` GETs.
- OpenELIS atomfeed uses configured OpenMRS user `admin` / password from `atomfeed.properties` (internal).
- OpenELIS UI is a **separate** login at `/openelis`.
- OpenELIS passwords are not stored or synchronized by Hospital EMR.
- Lab Lite would have used OpenMRS `app:lab-lite`; it is not running here.

---

## 11. Permissions

**CONFIRMED** existing privileges (do not create new ones):

| Privilege | Use |
|---|---|
| `app:lab-lite` | Bahmni Lab Entry tile (hidden). **Hospital EMR Laboratory gate.** `abikan.admin` has this. |
| `app:clinical:ordersTab` | Doctor Orders tab |
| `app:orders` | Bahmni Orders app (radiology fulfillment in this config) |
| Get Orders / Add Orders / Edit Orders / Delete Orders | OpenMRS order privileges |
| OpenELIS **Validation** / **Results entry** | LIS-side; not OpenMRS privileges |

Hospital EMR Laboratory opens when the signed-in OpenMRS user has `app:lab-lite`. There is **no** Laboratory login location, so access is **not** location-gated (creating a location would violate the safety rules for this task).

---

## 12. What Hospital EMR can safely read

- Patient identity (existing OpenMRS patient APIs)
- Per-patient lab orders: `GET …/bahmnicore/orders?patientUuid=&orderTypeUuid=`
- Per-patient results: `GET …/bahmnicore/labOrderResults?patientUuid=`
- Order urgency when present (`STAT`)
- Result value, unit, min/max, `abnormal` boolean, provider, accession, date

Hospital KPIs (pending orders, samples in processing, urgent count) **cannot** be filled from a confirmed API today. Show **—** or an empty work queue.

---

## 13. What Hospital EMR will eventually need to write

| Hospital EMR action | Intended backend | Status |
|---|---|---|
| Order laboratory test (Doctor) | `POST bahmniencounter` `orders[]` | Documented; not in this UI increment |
| Collect sample | OpenELIS sample entry — **UNKNOWN** REST | COMING SOON |
| Enter result | OpenELIS results entry — **UNKNOWN** REST | COMING SOON |
| Verify / release | OpenELIS validation — **UNKNOWN** REST | COMING SOON |

Until those APIs are confirmed, keep using OpenELIS for processing and Hospital EMR for workplace chrome + chart reads.

---

## 14. What is not currently supported

- Hospital-wide laboratory work queue via OpenMRS REST
- Lab Lite MFE (`/lab` container not running)
- `All_Tests_and_Panels` members (empty) — search real Test/LabSet concepts when ordering later
- Hospital EMR sample collection / result entry / verification writes
- High / Low / Critical as first-class OpenMRS enums
- Routine / Urgent / STAT as three stored values (only omitted vs `STAT` is confirmed on the write path)
- Laboratory login location
- OpenELIS SSO with OpenMRS

---

## Doctor ↔ laboratory (product)

```
Doctor
  ↓
Order Laboratory Test   (consultation orders[] — later)
  ↓
OpenELIS receives order (atomfeed)
  ↓
Sample collected / processed / verified in OpenELIS
  ↓
Results on OpenMRS patient (LAB_RESULT)
  ↓
Hospital EMR Doctor chart + Hospital EMR Laboratory patient view
  (same GET labOrderResults — no copy of the data)
```

The doctor does not pick a specimen type or enter results in the installed Bahmni clinical workflow.

---

## Operating boundary

Doctor ordering, the authoritative OpenELIS worklist status, and result return are implemented. Sample collection, accession, result entry, and validation remain in OpenELIS.

Future additions must preserve these boundaries:

1. OpenMRS maintains clinical concepts and `All_Tests_and_Panels` orderability.
2. The catalogue feed creates/updates the corresponding OpenELIS test.
3. The named OpenELIS Laboratory Administrator completes laboratory-side specimen, section, result, unit, and range configuration.
4. Hospital EMR provides ordering, worklist context, billing visibility, and returned-result display; it does not become a second processing engine.

There is no supported OpenELIS write API for Hospital EMR user management or processing in this installed version. Do not scrape forms or write `clinlims` directly.
