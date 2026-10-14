# Laboratory processing / result-return investigation

Date: **20 Aug 2026**. Engineering record. Staff-facing screens do not name source systems.

Related:

- `docs/LABORATORY_POST_IMPLEMENTATION_VERIFICATION.md` (earlier stopping point: OpenELIS sample, Not Tested, no accession)
- `docs/LABORATORY_WORKFLOW.md` (architecture of the existing laboratory application)
- `docs/LABORATORY_IMPLEMENTATION.md`

This file was first written as a read-only investigation while samples sat at Not Tested. Hospital staff then completed the existing OpenELIS workflow on the dedicated TEST patient. **This update is documentation only.** No code, configuration, catalogue, billing, OpenELIS, OpenMRS, or patient data was changed in this documentation pass. No second test was created.

**Classification:** the earlier **E. NOT ENOUGH EVIDENCE** finding is superseded.

**LABORATORY RESULT E2E: COMPLETE THROUGH RESULT RETURN**

- No new Hospital EMR laboratory result engine was required.
- OpenELIS remains the laboratory processing system.
- Hospital EMR successfully receives and displays the released result.
- The existing integration works end-to-end.
- Laboratory implementation is complete from ordering through result return.

---

## Successful final verification (20 Aug 2026)

The result was entered through the **existing OpenELIS UI**. It was **not** typed into Hospital EMR and **not** inserted into OpenMRS observations by hand. After OpenELIS validation, Hospital EMR displayed the returned value.

### Test record

| Field | Value |
|---|---|
| Patient | **ABC200016** — ABIKAN E2E TEST PATIENT |
| Test | **Malarial smear** |
| Result entered in OpenELIS | **Negative** |
| OpenELIS accession / lab number | **20082026-003** |
| Hospital EMR display | **Malarial smear \| Negative \| Today · 01:27** |

### Workflow performed

```
Hospital EMR Clinical
  → Laboratory Order
  → OpenMRS lab order
  → Atomfeed
  → OpenELIS sample
  → OpenELIS Samples to Collect
  → Collect Sample
  → OpenELIS generated accession number 20082026-003
  → Samples Collected
  → Awaiting Testing
  → Results Entry
  → Result entered: Negative
  → Awaiting Validation
  → Validation accepted
  → Completed
  → OpenMRS / Hospital EMR result returned
  → Doctor sees Malarial smear = Negative
```

### OpenELIS dashboard status transitions

Before collection:

| Queue | Count |
|---|---|
| Samples to Collect | 1 |
| Samples Collected | 0 |
| Awaiting Testing | 0 |
| Awaiting Validation | 0 |
| Completed | 0 |

After collection (accession **20082026-003** assigned by OpenELIS):

| Queue | Count |
|---|---|
| Samples to Collect | 0 |
| Samples Collected | 1 |
| Awaiting Testing | 1 |

After result entry (**Negative**):

| Queue | Count |
|---|---|
| Awaiting Testing | 0 |
| Awaiting Validation | 1 |

After validation accepted:

| Queue | Count |
|---|---|
| Awaiting Validation | 0 |
| Completed | 1 |

### Hospital EMR result screen — two Malarial smear rows

Do **not** alter or remove the earlier order.

| Row | What Hospital EMR showed | Meaning |
|---|---|---|
| 1 | **Today — Negative** | The successfully completed test (accession **20082026-003**) |
| 2 | **19 Aug 2026 — no result** | The earlier unprocessed Malarial smear order on this TEST chart |

---

## 1. Existing laboratory application

The operational laboratory application is **OpenELIS** (Bahmni Lab image `bahmni/openelis:1.0.0`), not Hospital EMR and not Bahmni Lab Lite.

| Piece | This installation |
|---|---|
| Application | OpenELIS (Bahmni Lab) |
| URL / path | `/openelis` → container `bahmni-standard-openelis-1` `openelis:8052/openelis` |
| Login | Separate OpenELIS login at `/openelis/LoginPage.do` (**not** the Hospital EMR / OpenMRS session) |
| Backend | Struts/JSP inside the OpenELIS WAR |
| Database | PostgreSQL `clinlims` on `bahmni-standard-openelisdb-1` |
| OpenMRS client | module `openelis-atomfeed-client-1.2.0.omod` (`elisatomfeedclient.started` = true) |
| Lab Lite `/lab` | Hidden in home config; **no `bahmni-lab` container** |

Hospital EMR does not process samples, enter results, or validate results. It links staff to OpenELIS as **Open laboratory processing** (`openelisUrl: "/openelis"`). After OpenELIS releases a result, Hospital EMR reads it from OpenMRS `labOrderResults`.

This E2E confirmed that staff workflow:

- Sample accession is performed **in OpenELIS** (Samples to Collect → Collect Sample).
- Result entry is performed **in OpenELIS**.
- Result validation is performed **in OpenELIS**.
- `lab.abikan` is a Hospital EMR / OpenMRS laboratory workplace account. It is **not** an OpenELIS login.

Bahmni Lab Lite is not the laboratory application here.

---

## 2. Sample lifecycle

Confirmed on this installation, including the completed TEST path:

```
Doctor consultation (Lab Order)
  → OpenMRS encounter atomfeed
  → OpenELIS creates sample with accession_number = null (Not Tested)
  → Laboratory staff sign into OpenELIS (separate login)
  → Samples to Collect → Collect Sample
  → OpenELIS assigns accession (DATENUM, e.g. 20082026-003)
  → Samples Collected / Awaiting Testing
  → Results Entry
  → Awaiting Validation
  → Validation accepted → Completed
  → OpenELIS → OpenMRS result return
  → GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults
  → Hospital EMR Doctor chart + Laboratory Results
```

Empty accession at ingest is **by design**. Staff collect the sample in OpenELIS; the feed does not invent an accession.

Site information (unchanged; still the rules the E2E followed):

| Setting | Value |
|---|---|
| `accessionStrategy` | `groupBySample` |
| `acessionFormat` | `DATENUM` (matches **20082026-003**) |
| `validate all results` | `true` (validation step was required and was used) |
| `ResultTechnicianName` | `true` |
| `trackPayment` | **`false`** |
| `useExternalPatientSource` | `true` |

---

## 3. Sample status after the E2E

Investigation snapshot **before** staff collection (20 Aug 2026, morning investigation): all TEST samples Not Tested, empty accession. That snapshot is historical.

**After** the manual OpenELIS E2E:

| Record | Status |
|---|---|
| Completed in-house TEST | Malarial smear, accession **20082026-003**, result **Negative**, validated, returned to Hospital EMR |
| Earlier TEST Malarial smear order | Still on the chart as **19 Aug 2026 — no result**. Not processed. Not removed. |
| Sample 29 Urine Toxicology | Not part of this E2E. Left as the outsourced / unprocessed path. |
| Sample 27 (ABC200005 Fatima Abdullahi) | Ordinary patient. Not used. Not touched. |

---

## 4. Sample accession workflow

**Proven:** OpenELIS dashboard **Samples to Collect** → **Collect Sample**. OpenELIS generated accession **20082026-003**.

Supporting screens in the same application (from the earlier investigation; Collect Sample was the path used for this E2E):

| Step | OpenELIS UI |
|---|---|
| Collect sample | Samples to Collect → Collect Sample |
| Dashboard | `/openelis/LabDashboard.do` |
| Result entry | Results Entry |
| Validation | Result Validation |

What changes **Not Tested / empty accession → accessioned**:

1. A laboratory user signs into **OpenELIS** (not Hospital EMR, not `lab.abikan`).
2. Opens **Samples to Collect**.
3. Collects the sample. OpenELIS assigns the accession number.
4. The row moves to Samples Collected / Awaiting Testing.

There is no Hospital EMR accession API. Do not invent one.

---

## 5. Laboratory user role

Two different accounts, two systems. This remains true after the E2E.

| Account | System | What it can do |
|---|---|---|
| `lab.abikan` | **OpenMRS / Hospital EMR** | Role **Abikan:Laboratory**. Privilege **`app:lab-lite`**. Laboratory board, payment status, **Open laboratory processing** link, chart reads. |
| Named OpenELIS staff account | **OpenELIS** | Collect sample, accession, result entry, and/or validation according to assigned roles |

`lab.abikan` **cannot** accession, test, enter, or validate in OpenELIS. There is no OpenELIS `login_user` for `lab.abikan`. OpenELIS does not use the OpenMRS session.

Stock OpenELIS credentials used during development are intentionally not recorded here. They are development identities, not hospital staff accounts. Rotate or disable them before hospital deployment and create individual named accounts through the OpenELIS user-management screen.

---

## 6. Required permissions

Unchanged from the investigation. Processing permissions live in OpenELIS, not in Hospital EMR.

| Action | Where | `lab.abikan` |
|---|---|---|
| Accession / sample collection | OpenELIS Intake / Collect Sample | No OpenELIS account |
| Result entry | OpenELIS Results entry | No OpenELIS account |
| Result validation | OpenELIS Validation | No OpenELIS account |

**CURRENT ROLE (lab.abikan):** OpenMRS `Abikan:Laboratory`  
**MISSING PERMISSION (for processing):** OpenELIS login + Intake / Results entry / Validation  
**EXPECTED PERMISSION:** an OpenELIS user with those roles  
**WHERE CONFIGURED:** OpenELIS User Admin, not Hospital EMR

Staff who completed this development E2E used an existing development OpenELIS login, not `lab.abikan`. Production processing must use individual named OpenELIS accounts.

---

## 7. Existing UI workflow

Hospital EMR Laboratory:

- Board and patient Results read OpenMRS orders + `labOrderResults`.
- Primary processing action: **Open laboratory processing** → `/openelis`.
- No Hospital EMR button collects the sample, enters the result, or validates. That is intentional and now proven sufficient.

OpenELIS:

- Login at `https://localhost/openelis/LoginPage.do`.
- Samples to Collect, Collect Sample, Results Entry, Validation, Completed — all used in this E2E.

---

## 8. Existing API workflow

Hospital EMR **reads**:

| Purpose | Call |
|---|---|
| Lab orders | `GET /openmrs/ws/rest/v1/bahmnicore/orders?patientUuid=&orderTypeUuid=d3560b17-5e07-11ef-8f7c-0242ac120002` |
| Lab results | `GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid=` |

Hospital EMR **does not write** accession, result, or validation. Those writes happen only in OpenELIS (form POSTs on Collect Sample / Results Entry / Result Validation).

The completed E2E used those OpenELIS writes. Nothing was inserted into OpenMRS `obs` outside that integration.

Earlier investigation feed probe (`GET …/openelis/ws/feed/patient/recent` → HTTP 401 with guessed Basic credentials) did **not** prevent result return once staff completed OpenELIS validation. The live path that mattered is the existing OpenELIS UI → integration worker → `labOrderResults` → Hospital EMR.

---

## 9. OpenELIS processing workflow

In-house path used for this E2E: **Malarial smear** (Microscopy MP), TEST patient ABC200016.

Payment does **not** gate OpenELIS (`trackPayment = false`). Accounts payment status is shown in Hospital EMR; it is not the processing switch.

---

## 10. Result-entry workflow

**Proven.** OpenELIS Results Entry. Value entered: **Negative**. Queue moved from Awaiting Testing to Awaiting Validation.

The result was **not** entered in Hospital EMR and **not** written directly to OpenMRS.

---

## 11. Result-validation workflow

**Proven.** `validate all results = true`. Validation accepted. Queue moved from Awaiting Validation to Completed.

---

## 12. OpenELIS → OpenMRS synchronization

**Proven by this E2E.** After validation, the result returned to OpenMRS and Hospital EMR displayed **Malarial smear = Negative**.

Designed path (now exercised):

```
OpenELIS validated result
  → OpenELIS accession / patient feed
  → OpenMRS OpenElisAccessionEventWorker
  → laboratory observation on the patient
  → GET bahmnicore/labOrderResults
  → Hospital EMR Doctor / Laboratory Results
```

Hospital EMR does not subscribe to OpenELIS. It reads OpenMRS after the existing worker writes the result.

---

## 13. Hospital EMR result display

**Proven.** After release, Hospital EMR showed:

**Malarial smear | Negative | Today · 01:27**

Doctor consultation and Laboratory patient views both use `fetchLabResults` → `labOrderResults`. No Hospital EMR-specific result table was added.

A second Malarial smear row remains: **19 Aug 2026**, no result. That is the earlier unprocessed order. Leave it.

---

## 14. Malarial smear test findings

### Completed TEST (this E2E)

- Patient: **ABIKAN E2E TEST PATIENT** ABC200016
- Test: Malarial smear
- OpenELIS accession: **20082026-003**
- Result: **Negative** (OpenELIS Results Entry, then Validation)
- Abikan: **Today · 01:27**, Negative

### Earlier unprocessed TEST order (leave in place)

- Same patient, Malarial smear, **19 Aug 2026**, no result in Hospital EMR
- Not this E2E. Do not delete or complete it in this documentation pass.

### Ordinary-patient sample 27 (not this E2E)

- ORD-5 / OpenELIS sample 27 is **Fatima Abdullahi ABC200005**, not the dedicated TEST patient.
- Not used for result return. Not touched.

---

## 15. Urine Toxicology findings

Unchanged. Outsourced on the Hospital EMR catalogue/board. OpenELIS sample 29 was not the in-house E2E path and was not processed in this verification.

---

## 16. Exact blocker

**None for in-house result return.** The previous blocker (could not log into OpenELIS / sample not accessioned) is closed for the dedicated TEST Malarial smear that staff collected as **20082026-003**.

Remaining operational notes (not E2E failures):

- `lab.abikan` still has no OpenELIS login; processing stays in OpenELIS.
- One earlier TEST Malarial smear order (19 Aug 2026) is still unprocessed.
- Urine Toxicology (outsourced) was not part of this E2E.
- Sample 27 (ordinary patient) was not part of this E2E.

---

## 17. Whether implementation is required

**No.** Do not build a Hospital EMR laboratory result-entry system.

OpenELIS remains responsible for sample collection, testing, result entry, and validation. Hospital EMR remains the staff-facing EMR layer and consumes the released result through the existing integration.

Laboratory implementation is **complete from ordering through result return**.

---

## 18. Recommended next step

None for the in-house result-return path. Optional later operational work (not required to prove E2E): OpenELIS accounts for named laboratory staff; process or leave the 19 Aug unprocessed Malarial smear; outsourced-test workflow when the hospital needs it.

---

## Data changed in this documentation pass

**None.** This update only changed `abikan-shell/docs/LABORATORY_PROCESSING_RESULT_INVESTIGATION.md`.

The completed E2E (already performed in OpenELIS before this documentation update) created accession **20082026-003** and result **Negative** through the existing laboratory application. That work was not a database bypass and was not repeated here.

---

## npm test / npm build

From `abikan-shell` after this documentation-only update (no application code changes):

| Command | Result |
|---|---|
| `npm test` | **81 passed**, 0 failed |
| `npm run build` | **succeeded** (`tsc --noEmit && vite build`) |
