# Laboratory implementation

Date: **19 Aug 2026**. This pass makes Laboratory usable in Hospital EMR from the hospital’s initial catalogue. It does **not** add a second laboratory, billing, or result engine. Pharmacy and the Nigerian payment gateway were not changed.

Staff-facing screens never name OpenMRS, Bahmni, Odoo, or the laboratory processing application.

---

## P0 correctness update — 26 Aug 2026

- The Laboratory board now reads the supported server-side accession resource for each source encounter. Its grouping uses the exact laboratory status (`Not started`, `Testing Started`, `Results final`, and other installed OpenELIS terms); it no longer treats the OpenMRS order `accessionNumber`/encounter UUID as processing evidence.
- A finalized Malarial smear is now present in Completed. The two same-test orders remain independent rows, but both are explicitly marked **order match needs review** because the installed integration collapsed them into one analysis. Neither worklist row claims the first-wins OpenMRS result as a safely correlated per-order result. Doctor/Laboratory result tables preserve the returned value and add **Needs review** for every duplicate same-test row on that accession.
- New duplicate same-test orders on the same Consultation are rejected. The same test may still be ordered on a different Consultation.
- Inorganic Phosphate, Testosterone, Progesterone, and Estradiol are unavailable because this dictionary has no safe matching Laboratory/Diagnostic concepts. Their same-name Drug concepts were removed from `All_Tests_and_Panels`; no replacement concepts were invented.
- `Abikan:Laboratory` no longer inherits `Bahmni-App-User-Login`, which supplied `Edit Users` and `Get Users`. It retains `Lab`, `app:lab-lite`, patient, visit, encounter, concept, provider, and order reads required by the workplace.
- OpenELIS remains the processing system. Hospital EMR does not collect specimens, enter results, validate results, scrape Struts forms, or write OpenELIS tables.
- OpenELIS staff and catalogue administration remains in OpenELIS. The hospital's dedicated named Laboratory Administrator uses `Maintenance Admin` with `is_admin = N`; this is a broad trusted role, not a Hospital EMR role. See `OPENELIS_LABORATORY_ADMINISTRATION.md`.

---

## 1. Hospital catalogue source

Initial source (hospital-supplied):

- `abikan-shell/laboratory_catalogue.csv`
- Working copy used by the API: `abikan-shell/server/patient-account/data/laboratory_catalogue.csv`

**80** hospital rows (S/N 1–80), with name, type, price in ₦, specimen, turnaround time, and availability (including outsourced).

Concept binding and reuse/create decisions:

- `abikan-shell/server/patient-account/data/laboratory_catalogue_map.json`
- Runtime concept ids after configuration: `abikan-shell/server/patient-account/data/laboratory_catalogue_runtime.json`

The React app does **not** hardcode the test list. Clinical search loads `GET /openmrs/abikan-api/laboratory/catalogue`.

The hospital may add, remove, or change tests later. See §17.

---

## 2. Tests configured

| Count | Meaning |
|---|---|
| 80 | Hospital CSV rows |
| 85 | Map rows (80 plus expansions for priced-each combinations) |
| **82** | Orderable tests/panels configured and priced |
| 3 | Hospital combo rows not ordered as a single priced-each item |

Expansions (hospital said “each”; ordered as separate tests):

- S/N 61 Total T3 & T4 → Total T3 and Total T4 at ₦8,000 each
- S/N 64 CA-125 / CA-19-9 / CA-15-3 → three tests at ₦15,000 each

S/N 45 Hormonal Profile is not a single orderable. Staff order the individual hormones.

---

## 3. Existing concepts reused

**56** hospital items reuse an existing dictionary concept/orderable where the identity was clear enough to map.

Examples:

- Full Blood Count → Complete blood count
- PCV → Hematocrit
- Clotting Profile (PT/PTTK) → Coagulation profile (not bleeding/clotting-time panel)
- Malaria microscopy → Malarial smear
- Blood group / genotype / many chemistry and serology singles

---

## 4. New concepts created

**26** map rows were `create`. On this installation **22** new concepts were actually created. **4** `create` names already existed and were reused rather than duplicated.

Created examples include: Peripheral Blood Film with FBC, Viral Marker (LVS, HBsAg, HCV), HBsAg Serology Panel, Malaria RDT, HVS M/C/S, Sputum M/C/S, Urinalysis with Microscopy, Seminal Fluid Analysis + MCS, E/U/Cr, hospital LFT, HbA1c, Urine Toxicology/Drug Test, Bilirubin Direct & Total, LH, AMH, IGF-1, Anti-TG & Anti-TPO, DNA/paternity rows, blood pints, donor screening.

`All_Tests_and_Panels` was filled with **82** members so the existing orderables set is no longer empty.

---

## 5. Panel handling

Individual tests and panels/profiles are both orderable.

Components were **not** invented.

- Viral Marker members were taken only from the hospital panel name (LVS, HBsAg, HCV).
- E/U/Cr, hospital LFT, and HBsAg Serology Panel are orderable LabSets **without** invented member lists.
- Dictionary LFT (includes HBsAg/HCV) was **not** reused for the hospital LFT.
- Basic metabolic panel was **not** used for E/U/Cr.

---

## 6. Price mapping

Hospital CSV prices are the initial approved patient prices.

- Currency shown to staff: **NGN / ₦**
- Odoo Laboratory shop uses pricelist **Hospital Laboratory** in NGN
- Each configured test is an Odoo **service** product keyed by the concept id (`uuid` / `default_code`)
- Placeholder catalogue prices of **1.00** are refused
- Isolated TEST products (` — TEST`) do not override hospital prices

**82** Odoo laboratory prices were written from the hospital file.

---

## 7. Availability handling

CSV `Available?` is respected.

- A row marked unavailable is not offered as a normal orderable
- This initial file has no `No` / unavailable rows; outsourced rows remain orderable and flagged

---

## 8. Outsourced-test handling

**30** configured items are outsourced.

- Search and the selected list show **Outsourced**
- The clinical order comment records that the test is sent out
- Laboratory board shows the same flag
- Hospital EMR does not pretend these are processed in-house and does not invent a separate outsourced workflow

---

## 9. Clinical ordering workflow

**Clinical → Patient → Order → Laboratory** is implemented (no longer Coming Soon).

The doctor can:

1. Open a patient and an open visit
2. Search the hospital catalogue
3. See name, type, specimen, and ₦ price
4. Add one or more tests/panels
5. Submit
6. See that the order was saved

The order is a Lab Order on the existing **Consultation** encounter for that visit. Vitals, diagnosis, HPI, notes, and prescriptions are not rewritten by this submit (orders-only save).

The doctor **cannot** collect payment, mark the bill paid, dispense, or enter results.

A laboratory fee is created at submit time and sent to Accounts. Payment is not required to create the clinical order.

---

## 10. Accountant workflow

No separate laboratory cashier screen.

Existing path: **Accountant → outstanding charges → payment → receipt**.

Live check on the dedicated test patient: invoice **INV/2026/00021**, department Laboratory, **₦15,000.00**, then Cash receipt **PCSH1/2026/00009**. After payment the laboratory fee for that order is **PAID**.

---

## 11. Laboratory workflow

Routes (and `#/lab…` aliases) stay inside Laboratory:

- `#/laboratory` Dashboard
- `#/laboratory/pending` Pending Orders
- `#/laboratory/processing` Processing / In Progress
- `#/laboratory/completed` Completed Results
- `#/laboratory/patients` Search Patient
- `#/laboratory/patient/{id}`
- `#/laboratory/order/{id}` and `#/lab/orders/{id}`

Unknown Laboratory hashes stay in Laboratory. They do not open Administration.

Laboratory staff see payment status **UNPAID / PAID / PARTIALLY PAID**. They do not collect payment.

Sample collection and result entry are not rebuilt. Staff open **Open laboratory processing** (existing laboratory application).

Board listing uses billed laboratory fees plus the patient’s clinical orders. OpenMRS will not list all Lab Orders without a patient; that limitation is handled without a second order database.

---

## 12. OpenELIS integration

Existing architecture is unchanged:

- Lab Order on the chart
- Atomfeed towards the laboratory application
- Results return on the chart via the existing result read (`labOrderResults`)
- Hospital EMR displays those results in Clinical and Laboratory; it does not store a second result file

**20 Aug 2026 verification:** the catalogue feed **does** land new hospital tests in the laboratory application once the worker catches up (tests 622 → 640). Encounter processing then needs a **specimen type** on each new test. After that, ORD-10 Malarial smear created sample **28** / analysis **470**, and ORD-8 created sample **29** / analysis **471**. Both are **Not Tested**, with no accession. Result return is still not proven. See `LABORATORY_POST_IMPLEMENTATION_VERIFICATION.md`.

---

## 13. End-to-end test

Dedicated test patient only: **ABC200016** / ABIKAN E2E TEST PATIENT  
`f242364e-b70f-4fec-b29e-8ad4fbe147b5`

Existing pharmacy prescription ORD-7 was not modified. No other patients, stock, or historic invoices were edited.

| Stage | Result |
|---|---|
| Doctor catalogue | **82** tests, all NGN, FBC **₦5,000**, no ₦1.00 placeholders |
| Doctor order | **ORD-8** Urine Toxicology/Drug Test on an existing OPD visit / Consultation encounter |
| Charge | **₦15,000.00 NGN**, UNPAID |
| Accountant | INV/2026/00021 Laboratory outstanding **₦15,000** |
| Payment | Cash **PCSH1/2026/00009**, then laboratory fee **PAID** |
| Laboratory board | Sees ORD-8, outsourced, pending, payment status |
| Laboratory processing / result | **20 Aug 2026:** in-house Microscopy MP **ORD-10** created laboratory sample **28**. Result value still empty. |

Highest verified stage: **order + NGN charge + Accounts payment + Laboratory visibility + OpenELIS sample (Not Tested)**. Result return still requires accession and result entry in the existing laboratory application.

---

## 14. Security tests

| Actor | Result |
|---|---|
| Unauthenticated catalogue/board | **401** |
| Doctor catalogue / create order | **200** |
| Doctor laboratory board | **403** |
| Accountant catalogue / create order | **403** |
| Laboratory board / patient fee | **200** (view and fee; no Pay control) |
| SuperAdmin | May open Laboratory (same as other departments) |
| Nursing / Reception | No laboratory ordering or result editing added |

Doctor still has no payment controls. Laboratory still has no cashier.

---

## 15. Data changed

**Configuration only, plus one dedicated test path:**

| Area | What changed |
|---|---|
| OpenMRS concepts | 22 new hospital lab concepts; 4 create-names reused; `All_Tests_and_Panels` now 82 members |
| Runtime map | `laboratory_catalogue_runtime.json` written |
| Odoo | NGN currency activated for use; pricelist **Hospital Laboratory**; **82** laboratory service prices; Laboratory shop pointed at that pricelist |
| Test patient ABC200016 | OPD visit (reused or started if missing), Lab Order **ORD-8**, sale/invoice **INV/2026/00021**, payment **PCSH1/2026/00009** |

**Not changed:** other patients, historic results, ORD-7 / pharmacy stock, unrelated invoices, company base currency (still USD in Odoo; laboratory fees use NGN), Radiology, Reception, Nursing, login, RBAC model beyond Laboratory SuperAdmin access in the shell.

---

## 16. Known limitations

1. **Historical note:** result return was not yet proven at this earlier checkpoint. It was later proven through OpenELIS validation; see `LABORATORY_PROCESSING_RESULT_INVESTIGATION.md`. The four unsafe Drug-class bindings were removed and remain unavailable.
2. **Three combo rows** are not single orderables (Hormonal Profile; Total T3 & T4 as one line; CA-125/19-9/15-3 as one line). Order the named parts.
3. **E/U/Cr, hospital LFT, HBsAg Serology Panel** are orderable without component lists.
4. **LVS** is mapped as HIV screening because the hospital Viral Marker line lists LVS with HBsAg and HCV. Confirm with the hospital if that is wrong.
5. **Genotype** is mapped as haemoglobin electrophoresis.
6. **Thyroid Function – Free T3, Free T4 & TSH** uses the dictionary T3/T4/TSH concept; free vs total was not re-defined.
7. **Urinalysis Only** and **Urinalysis with Microscopy** are different concepts and prices.
8. Department-wide pending list is driven from laboratory fees plus patient orders. OpenMRS will not return a global Lab Order search without a patient.
9. Odoo company currency remains USD; staff-facing laboratory amounts are forced to NGN. Accountant invoice formatting may still place ₦ after the number on some rows until a wider currency change is approved.
10. No Hospital EMR catalogue editor in this pass.

---

## 17. How future catalogue updates should be made

Do **not** change React to add a test or price.

An integrated test requires both OpenMRS orderability and OpenELIS processing configuration. Creating a test only in OpenELIS does not make it orderable in Hospital EMR.

Authorized OpenMRS catalogue maintenance (not ward staff and not Hospital EMR Hospital Admin) should:

1. Update `server/patient-account/data/laboratory_catalogue.csv` (name, type, ₦ price, specimen, TAT, availability).
2. Update `laboratory_catalogue_map.json`:
   - `reuse` with an existing concept id when the test is the same thing
   - `create` with `createName` only when nothing safe exists
   - `skip` when a combo must be ordered as parts
3. Run `python3 scripts/configure-laboratory-catalogue.py` (OpenMRS + Odoo). If host Odoo XML-RPC fails, run `--odoo-only` from the API container on the Docker network.
4. Allow the existing laboratory feed to create/update the corresponding OpenELIS test.
5. The named OpenELIS Laboratory Administrator verifies and completes specimen, section, result type, unit, result choices, reference ranges, and approved analyte/reflex configuration in OpenELIS.
6. Confirm the test appears in Clinical search with the new ₦ price.
7. Use controlled development data to verify order → OpenELIS processing → validation → result return.

Prices can also be corrected on the Odoo laboratory service (same product already mapped by concept). Membership of **All Tests and Panels** is maintained by the script so doctors can order the test.

When a test is withdrawn, mark it unavailable in the CSV (or retire the concept / stop selling the Odoo service). Do not delete historical orders.

Do not manually create an OpenELIS-only duplicate, write OpenELIS tables, or assume the legacy OpenELIS Test screen creates the complete integrated orderable. Full procedure: `docs/OPENELIS_LABORATORY_ADMINISTRATION.md`.

---

## 18. Files of record

- Clinical order UI: `src/components/LabOrderPanel.tsx`
- Laboratory workplace: `src/workspaces/Laboratory/`
- Catalogue loader: `server/patient-account/lab_catalogue.py`
- Orders, fees, board: `server/patient-account/laboratory.py`
- Configure: `scripts/configure-laboratory-catalogue.py`
- Post-implementation verification: `docs/LABORATORY_POST_IMPLEMENTATION_VERIFICATION.md`
