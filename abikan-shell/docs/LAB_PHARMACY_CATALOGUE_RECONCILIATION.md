# Laboratory and pharmacy catalogue reconciliation

Date: **19 Aug 2026**. **Investigation only.** No OpenMRS, Bahmni, Odoo, OpenELIS, stock, prices, products, concepts, orders, invoices, payments, configuration, or patient records were created or changed. The hospital Excel files were read, not imported.

Source files (unchanged):

| File | Path | Sheet | Data rows |
|---|---|---|---|
| Laboratory | `abikan-shell/Hospital EMR Hospital Laboratory Test Catalogue.xlsx` | Laboratory Catalogue | **80** tests (S/N 1–80) |
| Pharmacy | `abikan-shell/Medicines Stock.xlsx` | Sheet1 | **100** medicines/products |

Status used in the master tables (exactly one per hospital row):

| Status | Meaning |
|---|---|
| EXACT MATCH | Same identity already configured as a usable hospital orderable/product (name, type, and mapping ready) |
| LIKELY MATCH — VERIFY | A dictionary or product record exists that may be the same thing; names, strength, form, or panel members differ |
| EXISTS BUT NOT CONFIGURED | OpenMRS/OpenELIS/Odoo record exists, but it is not a usable hospital catalogue item |
| EXISTS BUT INCOMPLETE | Identity can be mapped, but price, stock, strength, or form is incomplete |
| MISSING | No corresponding OpenMRS drug/test or Odoo product |
| DUPLICATE / POSSIBLE DUPLICATE | Hospital file overlaps another hospital row, or several system records compete |
| REQUIRES HOSPITAL CLARIFICATION | Cannot map without the hospital deciding what the row means |

A CIEL/Bahmni **dictionary** concept is not a hospital test. A default Odoo product at **₦1.00** is not a hospital price.

---

## 1. Executive summary

This installation has a **generic Bahmni laboratory dictionary** (622 Test + 84 LabSet concepts, synced to OpenELIS) and a **generic OpenMRS drug catalogue** (543 drugs, mirrored as Odoo storable products). It does **not** currently contain this hospital’s laboratory catalogue or this hospital’s medicine stock list.

`All_Tests_and_Panels` has **0** members. Odoo laboratory catalogue prices are **1.00** except one isolated TEST product. Odoo pharmacy `list_price` is **0.00** except isolated TEST medicines. Odoo on-hand stock that is not a TEST artefact is **empty**.

The hospital laboratory file is a priced service catalogue (including outsourced and blood-bank rows). The hospital pharmacy file is titled **Medicines Stock**, includes **Available Qty** and “Out of Stock”, and has almost no composition, manufacturer, or selling price. Treat it as a **stock-style list**, not as approved Odoo inventory and not as a price list, until the hospital says otherwise.

**Do not import these files yet.** Reuse the existing architecture (OpenMRS orderables → OpenELIS / Drug Order → Atomfeed → Odoo). Connect this hospital’s confirmed items onto that path after the questions in §16 are answered.

---

## 2. Laboratory source-file summary

Columns: S/N, Department, Laboratory Test, Type, Price (₦), Specimen, TAT, Available?

Departments: Haematology 15, Microbiology 17, Clinical Chemistry 40, Molecular Biology 5, Blood Bank 3.

| Type as written | Count |
|---|---|
| Single | 51 |
| Panel | 16 |
| Combined | 4 |
| Single/Panel | 2 |
| Special test | 2 |
| Blood Bank Service | 2 |
| Service/Panel, Panel/Service, Panel/Screen | 3 |

Availability: **Yes** 52, **Outsource** (any spelling) 27, **Not stat** 1 (AFP).

Price notes in the file (not single ₦ amounts):

- Hormonal Profile — **₦8,000 each**
- Total T3 & T4 — **₦8,000 each**
- CA-125 / CA-19-9 / CA-15-3 — **₦15,000 each**
- Grouping & Cross Match — **per unit**
- DNA tests — per person / Father & Child
- AFP and Procalcitonin stored as Excel numbers `15000.0` / `35000.0`

The file does **not** list panel component tests (except names that already contain them, e.g. PT/PTTK, Viral Marker (LVS, HBsAg, HCV)).

---

## 3. Existing laboratory configuration

| Layer | Live finding | Class |
|---|---|---|
| OpenMRS Test concepts | 622, not retired | B — dictionary, unused as hospital menu |
| OpenMRS LabSet concepts | 84, not retired | B |
| `All_Tests_and_Panels` | uuid `d3e6fb5f-5e07-11ef-8f7c-0242ac120002`, **0 members** | D as a usable hospital catalogue |
| Bahmni Clinical Orders tab | Configured (`orders`, `enableLabOrderOptions` Urgent/NeedsPrint) | C — tab exists, nothing to order from the hospital list |
| Lab Order type | `d3560b17-5e07-11ef-8f7c-0242ac120002` | A — mechanism |
| OpenELIS tests/panels | 622 tests, 84 panels, 37 specimen types | B — synced dictionary |
| OpenELIS work | 1 sample_item from isolated billing TEST (Malarial smear); **0 results** | C |
| OpenMRS lab orders | **1** (ORD-5 Malarial smear, TEST patient) | C |
| LAB_RESULT / INVESTIGATION encounters | **0** | D results |
| Odoo Lab/Test + Lab/Panel products | 1263 + 87 templates; **1350 at list_price 1.00** | C / placeholder |
| Odoo Laboratory shop | sale.shop **Laboratory** exists | A for departmental billing |
| `order.type` Lab Order | **Not present** (only Drug Order) | D for Atomfeed lab billing |
| Hospital EMR Laboratory fee | Maps `product.uuid` = concept uuid; **refuses price 1.00** | A path, C until real prices |
| Isolated TEST product | Malarial smear — TEST, list_price **40.00**, category Laboratory | TEST only — do not treat as catalogue |

**Usable hospital laboratory catalogue: no.**

A. Existing and usable: Lab Order API, Laboratory shop, fee endpoint (once a non-placeholder priced product exists), OpenELIS feed for a real order (proven on Malarial smear).

B. Existing but unused: 622+84 dictionary/OpenELIS items, Odoo uuid-mapped services at ₦1.

C. Existing but incomplete: billing refuses ₦1; Orders tab empty; no results pipeline proven with a hospital test.

D. Missing: hospital names as orderables, hospital prices, panel membership as the hospital uses it, HbA1c / several hormones / several cultures.

E. Ambiguous: LVS, genotype, “each” prices, blood pints, outsourced vs in-house.

---

## 4. Laboratory reconciliation

Matching rules used:

- Exact fully specified OpenMRS name → **EXISTS BUT NOT CONFIGURED** (not in `All_Tests_and_Panels`; Odoo price 1.00).
- Same clinical test, different name or several candidates → **LIKELY MATCH — VERIFY**.
- No concept → **MISSING**.
- Hospital row is not a single test, or meaning is unclear → **REQUIRES HOSPITAL CLARIFICATION**.
- Hospital row restates another hospital row → **DUPLICATE / POSSIBLE DUPLICATE**.
- **EXACT MATCH** requires a configured hospital orderable. Count: **0**.

Do not treat Complete blood count as proven equal to this hospital’s FBC until components are confirmed. Do not treat Basic metabolic panel as E/U/Cr (it includes glucose, calcium, CO₂).

Full row table: **§14**.

---

## 5. Laboratory panel analysis

Hospital file does not enumerate components for most panels. Existing LabSet members are dictionary members, not this hospital’s SOP.

| Hospital panel | Hospital price | Existing LabSet | Existing members (OpenMRS) | Match? |
|---|---|---|---|---|
| Full Blood Count (FBC) | 5,000 | Complete blood count `1019…` (also Complete blood count (auto) `163700…`) | HCT, Hb, MCHC, MCH, MCV, platelets, RBC, RDW, WBC, neutrophils %, lymphocytes %, combined mono/eos/baso % | **LIKELY — VERIFY.** Two CBC sets. Hospital did not list members. |
| Grouping & Cross Match – per unit | 15,000 | Blood grouping test `161473…` (typing + Rh); Blood cross-matching `161233…` | Grouping ≠ crossmatch. “Per unit” is a blood-bank charge | **REQUIRES CLARIFICATION** |
| Clotting Profile (PT/PTTK) | 15,000 Outsource | **Coagulation profile** `163436…` = PTT, PT, INR. **Clotting Panel** `163702…` = bleeding time + clotting time | Hospital name is PT/PTTK. Do **not** use Clotting Panel | **LIKELY — VERIFY** Coagulation profile |
| Viral Marker (LVS, HBsAg, HCV) | 7,500 | None with those three members | Components exist separately (HBsAg, Anti-HCV; LVS unclear) | **MISSING** as a panel |
| HBsAg Serology Panel | 12,500 | None named that way | Several HBsAg tests, not a hospital panel | **REQUIRES CLARIFICATION** |
| Urine / Stool / HVS / Wound / Sputum M/C/S | 8,000 each | Urine C/S `161156…`; Stool culture bacterial `163603…`; Pus C/S `161484…`; no HVS; no sputum MCS | Microscopy vs culture vs sensitivity not defined | **LIKELY / MISSING** by specimen |
| Blood Culture | 20,000 | Culture and sensitivity, blood `161155…` | Not proven equal to “Single/Panel” | **LIKELY — VERIFY** |
| E/U/Cr | 7,000 | **No E/U/Cr set.** Basic metabolic panel `162630…` is Na, K, CO₂, Cl, BUN, glucose, creatinine, calcium | **Not the same panel** | **REQUIRES CLARIFICATION** |
| Lipid Profile | 10,000 | Lipid panel `1010…` | Total cholesterol, HDL, LDL, **VLDL**, triglycerides (mmol/L) | **LIKELY — VERIFY** (VLDL and units) |
| Liver Function Test (LFT) | 10,000 | Liver function tests `953…` | Total bilirubin, SGPT, SGOT, ALP, total protein, **plus HBsAg and HCV** | **LIKELY — VERIFY.** Hepatitis serology on this LFT set is probably **wrong** for this hospital |
| Hormonal Profile | 8,000 each | No single profile | FSH exists; LH, testosterone, estradiol, serum progesterone **missing** | **REQUIRES CLARIFICATION** / overlap with rows 53–58 |
| Thyroid Function – Free T3, Free T4 & TSH | 20,000 Outsource | Thyroid panel `161506…` | Thyroid function test, T3, T4, TSH — **not labelled Free** | **LIKELY — VERIFY** |
| Total T3 & T4 | 8,000 each Outsource | T3 `161503…`, T4 `161504…` | Two tests, not one panel | **REQUIRES CLARIFICATION** |
| Anti-TG & Anti-TPO | 40,000 Outsource | **None** | — | **MISSING** |
| Prospective Donor Viral Marker Screening, Grouping & Crossmatch | 15,000 | None as one orderable | — | **REQUIRES CLARIFICATION** |

Do not invent missing components.

---

## 6. Laboratory price comparison

| Finding | Detail |
|---|---|
| Hospital prices | Supplied for all 80 rows (some “each” / per unit) |
| Odoo dictionary lab products | **1.00** (placeholder). Hospital EMR Laboratory billing **refuses** this |
| Isolated TEST | Malarial smear — TEST **40.00** — not a hospital price |
| Same price | **0** hospital tests |
| Different price | Every dictionary match (hospital ₦1,500–₦500,000 vs Odoo 1.00) |
| Existing price missing as a real tariff | All non-TEST lab products |
| Hospital price missing | **0** rows (file has a price column on every test) |
| Price requires confirmation | “each” rows; per-unit crossmatch; outsourced vs in-house; whether ₦ is patient price including tax |

**Do not update any prices.**

---

## 7. Laboratory integration assessment

Intended path (already designed; not rebuilt):

```
Doctor → OpenMRS Lab Order (orders[] on Consultation)
  → Atomfeed encounter
  → OpenELIS sample / analysis
  → OpenELIS result → OpenMRS LAB_RESULT
  → Hospital EMR Laboratory workplace (read)
  → Laboratory fee (Odoo sale + invoice) → Accountant payment
```

| Question | Answer this install | Do not |
|---|---|---|
| Can an OpenMRS Lab Order be created? | **Yes**, via `bahmniencounter` `orders[]`. Hospital EMR Clinical order button is Coming Soon. Isolated TEST ORD-5 exists | Do not create another order |
| Are these 80 tests orderable today? | **No.** `All_Tests_and_Panels` is empty. Concepts may exist; they are not the hospital menu | Do not add set members in this audit |
| Does OpenELIS receive orders? | **Yes** for ORD-5 (1 sample_item). Catalogue feed has 3006 `event_records` category `lab` | Do not send a new order |
| Can results return? | Engine exists. **0** LAB_RESULT encounters, **0** OpenELIS results | Do not enter results |
| Can Odoo bill the service? | Laboratory shop + uuid mapping **yes**. Catalogue price 1.00 is **refused**. TEST used a separate 40.00 product | Do not change prices |
| Atomfeed Lab Order type? | **Not configured** (`order.type` is Drug Order only). Lab fees are departmental POST, not drug-order feed | Do not add order.type here |

Missing mappings: each hospital test → one OpenMRS concept → Odoo product with a real `list_price` → (for panels) LabSet members the hospital actually reports.

---

## 8. Pharmacy source-file summary

Title row: **Medicines Stock**. Columns: Medicine Name, Medicine Company, Medicine Composition, Medicine Category, Medicine Group, Unit, Available Qty.

| Field | What the file actually contains |
|---|---|
| Company | **Empty** on every row |
| Composition | Empty or `-` |
| Medicine Group | **Empty** |
| Category | Tablet, Injection, Syrup, Nasal, Goute, Drip, Suspension, capsule, Consumables, Topical Gel |
| Unit | Often blank; some mismatch category (Vicryl 6/0 unit Ampule; Vicryl 5/0 unit Tablet; Gentamycin eye unit L) |
| Available Qty | Integers, `0`, or `0  (Out of Stock)` |
| Prices | **Not present** |

**What the file is:** **REQUIRES CLARIFICATION.** It looks like a **physical stock / availability report** (title, quantities, Out of Stock), mixed with **catalogue names**, including consumables (needles, catheters, gauze, pampers, blades). It is **not** proven to be current Odoo inventory.

Hospital pharmacy selling prices were **not supplied**.

---

## 9. Existing pharmacy configuration

| Layer | Live finding |
|---|---|
| OpenMRS drugs retired=0 | **543** |
| Odoo storable products | **543** (1:1 with drugs). Mapping `product.product.uuid` = OpenMRS drug uuid |
| Odoo list_price | **539 at 0.00**; 4 with a price (isolated TESTs, e.g. Paracetamol 500 mg — TEST **1000**, Vitamin C 100 mg — TEST **800**) |
| Stock location | `WH/Stock` |
| On-hand (internal, non-zero) | **Paracetamol 500 mg — TEST only**: qty **88**, reserved **2** |
| Partners/Customers / Vendors quants | TEST paracetamol 12 and -100 (valuation artefacts) — not hospital stock |
| Drug Order | Working (isolated ORD-7 → Pharmacy READY TO DISPENSE) |
| `order.type` | Drug Order |
| sale.shop | Pharmacy Counter |

There is **no** hospital brand catalogue (Marcfix, Amatem, LYNTRIAXONE, Astymin, …) in OpenMRS/Odoo.

---

## 10. Pharmacy reconciliation

Rules: same generic + same strength + same form → can map. Brand without composition → **MISSING** or **REQUIRES HOSPITAL CLARIFICATION**. Missing strength when several OpenMRS strengths exist → **REQUIRES HOSPITAL CLARIFICATION** or **LIKELY MATCH — VERIFY**. Consumables are not OpenMRS drugs.

**EXACT MATCH count: 0** — even identity-clear rows have Odoo price 0.00 and stock 0.

Identity-clear OpenMRS/Odoo rows (still incomplete commercially): Cetirizine 10 mg, Phenytoin 100 mg, Mannitol 20%, Artesunate 60 mg, Telmisartan 80 mg.

Full row table: **§14**.

---

## 11. Pharmacy price comparison

**Hospital pharmacy selling prices were not supplied.**

Odoo catalogue drug `list_price` is **0.00** except isolated TEST products. There is nothing valid to compare. Do not invent prices. Do not change Odoo prices.

---

## 12. Pharmacy stock comparison

| Item | Hospital file | Odoo WH/Stock on-hand | Reserved | Classification |
|---|---|---|---|---|
| Every listed medicine/consumable | Quantities 0–1000 | **0** (product usually absent) | 0 | **Stock discrepancy requires reconciliation** — do **not** conclude Odoo is wrong |
| Paracetamol 500 mg — TEST | **Not in hospital file** | **88** | **2** | TEST stock only; do not overwrite |
| Hospital “Out of Stock” / 0 | Many rows | 0 | 0 | Still not proof the file is a physical count |

Do **not** copy hospital quantities into Odoo.

---

## 13. Existing pharmacy workflow

```
Doctor → Prescription UI
  → OpenMRS Drug Order
  → Atomfeed encounter
  → Odoo Pharmacy sale
  → Invoice
  → Accountant payment
  → Pharmacy READY TO DISPENSE
  → Dispense
```

Confirmed from isolated E2E **19 Aug 2026** (not re-run this audit):

| Stage | Status |
|---|---|
| Doctor prescribe | Working (ORD-7 Paracetamol 500 mg — TEST) |
| OpenMRS Drug Order | Working |
| Atomfeed → Odoo sale | Working |
| Invoice + cashier pay | Working |
| Pharmacy READY TO DISPENSE | Working |
| Dispense | **Not** performed in that test |

This audit did not prescribe, dispense, or create a sale.

---

## 14. Master reconciliation tables

### Laboratory (all 80 hospital tests)

Odoo price for every dictionary product below is **1.00** unless noted. Existing ID is OpenMRS concept uuid.

| # | Hospital Test | Type | Price | Specimen | TAT | Existing Match | ID | Status | Action |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Full Blood Count (FBC) | Panel | 5,000 | Blood | 30 min | Complete blood count (also CBC auto) | `1019…` / `163700…` | LIKELY MATCH — VERIFY | Confirm members; pick one set; add to All_Tests_and_Panels; set price 5,000 |
| 2 | PCV | Single | 1,500 | Blood | 30 min | Hematocrit | `1015…` | LIKELY MATCH — VERIFY | Confirm PCV = haematocrit |
| 3 | ESR | Single | 5,000 | Blood | 1h 30 | Erythrocyte sedimentation rate (also Sedimentation test LabSet) | `855…` / `161425…` | LIKELY MATCH — VERIFY | Pick Test vs LabSet |
| 4 | Blood Grouping | Single | 2,000 | Blood | 30 min | Blood grouping test (LabSet: typing + Rh) | `161473…` | LIKELY MATCH — VERIFY | Hospital typed Single; existing is a set |
| 5 | Grouping & Cross Match – per unit | Service/Panel | 15,000 | Blood | 1 h | Blood cross-matching + grouping concepts | `161233…` | REQUIRES HOSPITAL CLARIFICATION | Per-unit blood-bank charge vs lab test |
| 6 | Genotype | Single | 3,000 | Blood | 24 h | No haemoglobin genotype. Electrophoresis / sickle screen exist | — | REQUIRES HOSPITAL CLARIFICATION | AA/AS/SS vs electrophoresis |
| 7 | Peripheral Blood Film with FBC | Combined | 10,000 | Blood | 2–5 d | Peripheral smear + CBC exist separately | — | REQUIRES HOSPITAL CLARIFICATION | Combined orderable does not exist |
| 8 | Clotting Profile (PT/PTTK) | Panel | 15,000 | Blood | 24 h Outsource | Coagulation profile (PT, PTT, INR). Not Clotting Panel | `163436…` | LIKELY MATCH — VERIFY | Do not use Clotting Panel `163702…` |
| 9 | VDRL | Single | 2,500 | Blood | 30 min | VDRL | `299…` | EXISTS BUT NOT CONFIGURED | Add to orderables; price 2,500; VDRL titre is a different concept |
| 10 | HBsAg | Single | 2,500 | Blood | 30 min | HBsAg Rapid Diagnostic Test; HBsAg Test; spot test | `165301…` / `159430…` | LIKELY MATCH — VERIFY | Which assay |
| 11 | Anti-HCV | Single | 2,500 | Blood | 30 min | Anti-HCV rapid diagnostic test | `165302…` | LIKELY MATCH — VERIFY | Rapid vs other HCV tests |
| 12 | LVS | Single | 2,500 | Blood | 30 min | None named LVS. Viral Marker lists LVS with HBsAg, HCV | — | REQUIRES HOSPITAL CLARIFICATION | Confirm if HIV (or other) |
| 13 | Rheumatoid Factor | Single | 15,000 | Blood | 24 h Outsource | Rheumatoid factor | `161470…` | LIKELY MATCH — VERIFY | Also LabSet `161479…` |
| 14 | Viral Marker (LVS, HBsAg, HCV) | Panel | 7,500 | Blood | 30 min | No such LabSet | — | MISSING | After LVS meaning; then configure panel members |
| 15 | HBsAg Serology Panel | Panel | 12,500 | Blood | 2–5 h | No named panel | — | REQUIRES HOSPITAL CLARIFICATION | List components |
| 16 | Microscopy MP | Single | 1,500 | Blood | 30 min | Malarial smear | `32…` | LIKELY MATCH — VERIFY | Used in billing TEST; also malaria smear qualitative |
| 17 | Malaria Parasite (RDT) | Single | 1,500 | Blood | 30 min | No malaria RDT concept | — | MISSING | Do not silently use smear |
| 18 | Urine M/C/S | Panel | 8,000 | Urine | 3–5 d | Culture and sensitivity, urine | `161156…` | LIKELY MATCH — VERIFY | M vs C vs S |
| 19 | Stool M/C/S | Panel | 8,000 | Stool | 3–5 d | Stool culture (bacterial) | `163603…` | LIKELY MATCH — VERIFY | May omit sensitivity/microscopy |
| 20 | HVS M/C/S | Panel | 8,000 | Swab | 3–5 d | None | — | MISSING | |
| 21 | Blood Culture | Single/Panel | 20,000 | Blood | 7 d | Culture and sensitivity, blood | `161155…` | LIKELY MATCH — VERIFY | Type Single/Panel |
| 22 | Wound M/C/S | Panel | 8,000 | Swab | 3–5 d | Pus culture and sensitivity | `161484…` | LIKELY MATCH — VERIFY | Wound vs pus |
| 23 | Sputum M/C/S | Panel | 8,000 | Sputum | 3–5 d | AFB concepts exist; not MCS | — | MISSING | Do not map to AFB |
| 24 | Urinalysis with Microscopy | Combined | 3,000 | Urine | 3–5 d | Urinalysis order + Urine microscopy | `302…` + `56…` | LIKELY MATCH — VERIFY | Two concepts; TAT 3–5 d vs dipstick |
| 25 | Stool Microscopy | Single | 3,000 | Stool | 3–5 d | Stool microscopy with concentration | `161447…` | LIKELY MATCH — VERIFY | |
| 26 | Seminal Fluid Analysis | Single | 10,000 | Semen | 24 h | Semen analysis / Semen analysis test | `161467…` / `161468…` | LIKELY MATCH — VERIFY | |
| 27 | Seminal Fluid Analysis + MCS | Combined | 15,000 | Semen | 3–5 d | No combined orderable | — | REQUIRES HOSPITAL CLARIFICATION | |
| 28 | Typhoid/Widal | Single | 5,000 | Blood | 3 h | Widal test | `306…` | LIKELY MATCH — VERIFY | |
| 29 | H. pylori | Single | 7,500 | Blood | 3 h | H. pylori Ab in **serum**; stool antigen also exists | `163620…` | LIKELY MATCH — VERIFY | Blood vs stool |
| 30 | Fungal Studies | Single/Panel | 20,000 | Swab/Skin | 7 d Outsource | Skin fungal test | `161463…` | LIKELY MATCH — VERIFY | |
| 31 | Chlamydia | Single | 12,000 | Swab | 24 h Outsource | Several PCR/IF concepts | e.g. `1034…` | LIKELY MATCH — VERIFY | Which method |
| 32 | Gonorrhea | Single | 12,000 | Swab | 24 h Outsource | N. gonorrhoeae PCR | `1036…` / `1038…` | LIKELY MATCH — VERIFY | |
| 33 | E/U/Cr | Panel | 7,000 | Blood | 3–5 h | No E/U/Cr set. BMP is **not** equivalent | Na `1132…` K `1133…` BUN `857…` creatinine `790…` | REQUIRES HOSPITAL CLARIFICATION | List members; do not use BMP |
| 34 | Lipid Profile | Panel | 10,000 | Blood | 24 h | Lipid panel | `1010…` | LIKELY MATCH — VERIFY | Confirm VLDL + mmol/L |
| 35 | Liver Function Test (LFT) | Panel | 10,000 | Blood | 24 h | Liver function tests | `953…` | LIKELY MATCH — VERIFY | Existing set includes **HBsAg + HCV** — likely wrong |
| 36 | Random Blood Sugar (RBS) | Single | 1,500 | Blood | 30 min | Serum glucose (not named random) | `887…` | LIKELY MATCH — VERIFY | Also mmol variant |
| 37 | Fasting Blood Sugar (FBS) | Single | 1,500 | Blood | 30 min | Fasting blood glucose (mg/dL) | `160912…` | LIKELY MATCH — VERIFY | Also mmol concept |
| 38 | 2-Hour Post-Prandial Blood Sugar (2HPP) | Single | 3,000 | Blood | 2h 30 Outsource | PP glucose 2 hours after meal | `167177…` | LIKELY MATCH — VERIFY | Also a PP panel |
| 39 | Faecal Occult Blood | Single | 5,000 | Stool | 24 h Outsource | Fecal occult blood test | `159362…` | LIKELY MATCH — VERIFY | |
| 40 | HCG Quantitative | Single | 12,000 | Blood | 24 h Outsource | HCG measurement / Serum HCG LabSet | `160922…` / `161509…` | LIKELY MATCH — VERIFY | Quantitative vs qualitative |
| 41 | Calcium | Single | 4,000 | Blood | 2–3 h | Serum calcium (two unit concepts) | `159497…` / `166038…` | LIKELY MATCH — VERIFY | Units |
| 42 | Inorganic Phosphate | Single | 4,000 | Blood | 2–3 h | None (G6PD phosphate is unrelated) | — | MISSING | |
| 43 | Uric Acid | Single | 4,000 | Blood | 2–3 h Outsource | uric acid, serum | `159825…` | LIKELY MATCH — VERIFY | |
| 44 | Glycated Haemoglobin (HbA1c) | Single | 10,000 | Blood | 2–3 h | None | — | MISSING | Do not invent |
| 45 | Hormonal Profile | Panel | 8,000 each | Blood | 24 h | Not one panel; overlaps FSH/prolactin rows | — | DUPLICATE / POSSIBLE DUPLICATE | Decide profile vs individual hormones |
| 46 | Urine Toxicology/Drug Test | Panel/Screen | 15,000 | Urine | 2 h Outsource | None | — | MISSING | |
| 47 | Albumin | Single | 4,000 | Blood | 2 h | Serum albumin | `848…` | LIKELY MATCH — VERIFY | Also an LFT member |
| 48 | Bilirubin – Direct & Total | Combined | 4,000 | Blood | 2–3 h | Direct bilirubin + Total bilirubin | `1297…` + `655…` | LIKELY MATCH — VERIFY | No combined orderable |
| 49 | Magnesium | Single | 5,000 | Blood | 2 h Outsource | Serum magnesium (two units) | `159643…` / `166397…` | LIKELY MATCH — VERIFY | |
| 50 | Urinalysis Only | Single | 1,500 | Urine | 30 min | Urinalysis order | `302…` | DUPLICATE / POSSIBLE DUPLICATE | vs row 24; confirm dipstick vs microscopy |
| 51 | Serum Pregnancy Test | Single | 2,000 | Blood | 30 min | Serum Pregnancy Test, Qualitative | `1945…` | EXISTS BUT NOT CONFIGURED | Configure + price; vs HCG quantitative |
| 52 | Urine Pregnancy Test | Single | 2,000 | Urine | 30 min | Urine pregnancy test | `45…` | EXISTS BUT NOT CONFIGURED | Configure + price |
| 53 | Prolactin | Single | 8,000 | Blood | 2–3 h | Serum prolactin | `161516…` | LIKELY MATCH — VERIFY | |
| 54 | FSH | Single | 8,000 | Blood | 2–3 h | Follicle stimulating hormone test | `161489…` | LIKELY MATCH — VERIFY | Also FSH panel |
| 55 | LH | Single | 8,000 | Blood | 2–3 h | None | — | MISSING | |
| 56 | Testosterone | Single | 8,000 | Blood | 2–3 h | None | — | MISSING | |
| 57 | Progesterone | Single | 8,000 | Blood | 2–3 h | Progesterone Receptor Assay is **not** serum progesterone | — | MISSING | Do not map to receptor assay |
| 58 | Estradiol | Single | 8,000 | Blood | 2–3 h | None (estrogen urine/receptor are different) | — | MISSING | |
| 59 | C-Reactive Protein (CRP) | Single | 12,000 | Blood | 24 h Outsource | C-reactive protein | `161500…` | LIKELY MATCH — VERIFY | |
| 60 | Thyroid Function – Free T3, Free T4 & TSH | Panel | 20,000 | Blood | 24 h Outsource | Thyroid panel (T3, T4, TSH, not Free) | `161506…` | LIKELY MATCH — VERIFY | Free vs total |
| 61 | Total T3 & T4 | Panel | 8,000 each | Blood | 24 h Outsource | T3 + T4 tests | `161503…` `161504…` | REQUIRES HOSPITAL CLARIFICATION | Two prices vs one panel |
| 62 | PSA | Single | 10,000 | Blood | 2–3 h | Several PSA (total vs free) | e.g. `160913…` | LIKELY MATCH — VERIFY | Which PSA |
| 63 | CEA | Single | 15,000 | Blood | 24 h Outsource | CEA measurement | `160915…` | LIKELY MATCH — VERIFY | |
| 64 | CA-125 / CA-19-9 / CA-15-3 | Single | 15,000 each | Blood | 24 h Outsource | Three separate tests exist | `160919…` `160921…` `160920…` | REQUIRES HOSPITAL CLARIFICATION | Three orderables, not one |
| 65 | D-Dimer Assay | Single | 15,000 | Blood | 24 h Outsource | D-dimer | `166018…` | LIKELY MATCH — VERIFY | |
| 66 | Alpha-Fetoprotein (AFP) | Single | 15,000 | Blood | 24 h Not stat | Alpha-1-fetoprotein measurement | `160917…` | LIKELY MATCH — VERIFY | |
| 67 | Vitamin D | Single | 15,000 | Blood | 24 h Outsource | 25-hydroxyvitamin **D3** only | `17bd7da1-…` | LIKELY MATCH — VERIFY | D3 vs total D |
| 68 | Procalcitonin | Single | 35,000 | Blood | 24 h Outsource | Procalcitonin measurement | `165953…` | LIKELY MATCH — VERIFY | |
| 69 | Serum Potassium | Single | 3,000 | Blood | 2–3 h | Serum potassium | `1133…` | EXISTS BUT NOT CONFIGURED | Also an E/U/Cr component |
| 70 | AMH | Single | 25,000 | Blood | 24 h Outsource | None | — | MISSING | |
| 71 | IGF-1 Assay | Single | 80,000 | Blood | 24 h Outsource | None | — | MISSING | |
| 72 | Anti-TG & Anti-TPO | Panel | 40,000 | Blood | 24 h Outsource | None | — | MISSING | |
| 73 | Hepatitis B Viral Load | Single | 35,000 | Blood | 24 h Outsource | Hepatitis B DNA quantitative; HBV DNA test | `a8c0a4d6-…` / `161234…` | LIKELY MATCH — VERIFY | Which assay |
| 74 | HIV Viral Load | Single | 35,000 | Blood | 24 h Outsource | HIV viral load | `856…` | LIKELY MATCH — VERIFY | Qualitative also exists |
| 75 | Hepatitis C Viral Load | Single | 38,000 | Blood | 24 h Outsource | HCV viral load, qualitative (not clearly quantitative RNA) | `166137…` | LIKELY MATCH — VERIFY | |
| 76 | DNA/Paternity Testing – per person | Special | 250,000 | All samples | 2 months Outsource | None | — | MISSING | Service, not a dictionary test |
| 77 | DNA/Paternity Testing – Father & Child | Special | 500,000 | All samples | 2 months Outsource | None | — | MISSING | |
| 78 | Positive Blood Pint | Blood Bank Service | 25,000 | Blood | 2 h | None | — | MISSING | Blood bank / inventory, not a lab test |
| 79 | Negative Blood Pint | Blood Bank Service | 35,000 | Blood | 2 h | None | — | MISSING | |
| 80 | Prospective Donor Viral Marker Screening, Grouping & Crossmatch | Panel/Service | 15,000 | Blood | 2 h | None as one item | — | REQUIRES HOSPITAL CLARIFICATION | Composite service |

### Pharmacy (all 100 hospital medicines)

Odoo on-hand is **0** and list_price **0.00** unless stated. “Odoo product” exists when the OpenMRS drug exists (uuid map).

| # | Hospital Medicine | Composition | Unit | Hospital Qty | Existing OpenMRS | Existing Odoo | Status | Action |
|---|---|---|---|---|---|---|---|---|
| 1 | Marcfix tab | — | Tablet | 9 | None | None | MISSING | Identify generic; then OpenMRS-first drug |
| 2 | Sodium Bicarbonate | — | Injection | 0 (Out of Stock) | Sodium bicarbonate as per IP `d969e5ee-…` | Mapped uuid, price 0, stock 0 | LIKELY MATCH — VERIFY | Confirm injection vs “as per IP” |
| 3 | Astymin injection | — | Injection | 0 (Out of Stock) | None | None | MISSING | Brand; composition needed |
| 4 | Caffein | — | Injection | 0 (Out of Stock) | None | None | MISSING | Spelling/strength |
| 5 | Cabergoline | — | Tablet | 0 (Out of Stock) | None | None | MISSING | Strength |
| 6 | Amatem Forte softgel | — | Tablet | 34 | None | None | MISSING | Brand (likely artemether/lumefantrine) |
| 7 | LYNTRIAXONE | — | Injection | 74 | Ceftriaxone 1 g / 250 mg / 500 mg | Those products | REQUIRES HOSPITAL CLARIFICATION | Brand + which strength |
| 8 | Abidec drop | — | ml | 9 | None | None | MISSING | Brand multivitamin drops |
| 9 | Meropenum | — | Injection | 17 | None (no meropenem) | None | MISSING | Spelling meropenem; strength |
| 10 | Otrivin Child | — | ml | 2 | None | None | MISSING | Brand xylometazoline? |
| 11 | Ceftazidime | — | Injection | 1 | Ceftazidime 1 g `73736189-…` or 250 mg | Both | REQUIRES HOSPITAL CLARIFICATION | Which strength |
| 12 | Vitamin D3 1000iu | — | Tablet | 8 | Only Calcium 500mg + D3 250iu combo | Combo only | MISSING | 1000 IU is not the combo |
| 13 | Gentamycin eye | — | L | 4 | Gentamicin 0.30% `aa4c5063-…` | Mapped | LIKELY MATCH — VERIFY | Eye drop vs 0.30%; unit L is wrong |
| 14 | Rivaroxaban 10mg | - | Tablet | 0 (Out of Stock) | None | None | MISSING | |
| 15 | D/SALINE 1LITRE | - | — | 3 | None | None | MISSING | IV fluid, not a tablet drug |
| 16 | Calcimax | - | ml | 1 | None | None | MISSING | Brand |
| 17 | Aminophylline | - | — | 1000 | None | None | MISSING | Strength/form |
| 18 | Clarithromycin | - | Tablet | 30 | None | None | MISSING | Strength |
| 19 | shaltoux | - | — | 0 | None | None | MISSING | Brand |
| 20 | cetirizine 10mg | - | — | 131 | Cetirizine 10 mg `7e0766e1-…` | Mapped, price 0, stock 0 | EXISTS BUT INCOMPLETE | Set selling price; reconcile stock 131 vs 0 |
| 21 | neurocalm | - | — | 90 | None | None | MISSING | Brand |
| 22 | Cyclogest | - | Tablet | 0 (Out of Stock) | None | None | MISSING | Usually pessary; category Tablet |
| 23 | Propranolol | - | — | 14 | 10 / 40 / 80 mg | All three | REQUIRES HOSPITAL CLARIFICATION | Strength |
| 24 | Chloramphenicol injection | - | Injection | 14 | None | None | MISSING | |
| 25 | Levofloxacin IV | - | — | 13 | None | None | MISSING | |
| 26 | Glycopyrrolate inj | - | — | 3 | Glycopyrrolate 0.2 mg/ml `cf4fb32b-…` | Mapped | LIKELY MATCH — VERIFY | Confirm strength |
| 27 | Catheter size 14 | - | — | 2 | None | None | MISSING | Consumable — pharmacy vs stores |
| 28 | Rosuvastatin | - | — | 90 | None | None | MISSING | Strength |
| 29 | Losartan | - | — | 42 | None | None | MISSING | Strength |
| 30 | Primolut N | - | — | 18 | None (norethisterone not as this brand) | None | MISSING | Brand |
| 31 | Tranexamic Acid tab | - | — | 11 | Tranexamic acid 500 mg `319e7f86-…` (also 100 mg/ml inj) | Mapped | LIKELY MATCH — VERIFY | Confirm 500 mg tablet |
| 32 | Tissue paper | - | — | 29 | None | None | MISSING | Consumable |
| 33 | lactulose | - | — | 6 | Lactulose 10 g/15 ml `ee7fb75f-…` | Mapped | LIKELY MATCH — VERIFY | |
| 34 | Loratyn | - | — | 0 | None (no loratadine drug) | None | MISSING | Brand? |
| 35 | COFTA | - | — | 0 | None | None | MISSING | |
| 36 | Rulox Antacid | - | — | 5 | None | None | MISSING | |
| 37 | GESTID | - | — | 4 | None | None | MISSING | |
| 38 | Amoxiclav 457mg | - | — | 5 | No 400/57. Closest 200+28.5 /5 ml `3b777d92-…` | Those | REQUIRES HOSPITAL CLARIFICATION | 457 mg ≠ existing strengths |
| 39 | Tetracycline | - | — | 0 | None | None | MISSING | |
| 40 | 23G NEEDLE | - | Consumable | 17 | None | None | MISSING | Consumable |
| 41 | Progesterone 100mg | - | — | 0 (Out of Stock) | None | None | MISSING | |
| 42 | BIOFLOR | - | — | 10 | None | None | MISSING | |
| 43 | Vicryl 6/0 | - | Ampule | 3 | None | None | MISSING | Suture; unit Ampule is wrong |
| 44 | ventolin nebules | - | — | 10 | Salbutamol 5mg/ml `5cfee6e7-…` (also other salbutamol) | Mapped | LIKELY MATCH — VERIFY | Brand Ventolin; nebule vs 5mg/ml |
| 45 | Nitroglycerin | - | — | 15 | Nitroglycerin 0.5 mg tablet `527c3a11-…` (also 5 mg/ml) | Both | LIKELY MATCH — VERIFY | Hospital category Tablet → likely 0.5 mg |
| 46 | Quinine Tablet | - | — | 40 | Quinine 300 mg `7493f5df-…` | Mapped | LIKELY MATCH — VERIFY | Confirm 300 mg |
| 47 | Torsemide inj | - | — | 10 | None | None | MISSING | |
| 48 | 21G NEEDLE | - | Consumable | 10 | None | None | MISSING | Consumable |
| 49 | Loratidine syrup | - | — | 1 | None | None | MISSING | Spelling; no loratadine |
| 50 | oxytocin | - | — | 4 | Oxytocin 5 IU/ml or 10 IU/ml | Both | REQUIRES HOSPITAL CLARIFICATION | Strength |
| 51 | Dobutamine | - | — | 3 | Dobutamine 50 mg/ml `113e95b6-…` | Mapped | LIKELY MATCH — VERIFY | |
| 52 | Vicryl 5/0 | - | Tablet | 3 | None | None | MISSING | Unit Tablet is wrong |
| 53 | Chlorpromazine tab | - | — | 4 | None | None | MISSING | Strength |
| 54 | Clofenac 100mg | - | — | 167 | Diclofenac 50 mg tablet only (not 100 mg) | 50 mg | REQUIRES HOSPITAL CLARIFICATION | Brand Clofenac; 100 vs 50 |
| 55 | Astymin | - | mg | 0 (Out of Stock) | None | None | MISSING | Syrup; duplicate brand vs #3/#69 |
| 56 | Anusol | - | — | 7 | None | None | MISSING | Category Tablet may be wrong |
| 57 | Bicalutamide | - | — | 4 | None | None | MISSING | Strength |
| 58 | Ducolax | - | — | 3 | Bisacodyl 5 mg tablet `9bd253c7-…` | Mapped | LIKELY MATCH — VERIFY | Brand |
| 59 | Gentamycin ointment | - | Consumable | 1 | Gentamicin 0.30% | Mapped | LIKELY MATCH — VERIFY | Ointment vs drop vs 0.30% |
| 60 | Vitamin B2 | - | — | 11 | Riboflavin 5 mg `179b7880-…` | Mapped | LIKELY MATCH — VERIFY | Confirm 5 mg |
| 61 | silk 0 | - | — | 4 | None | None | MISSING | Suture |
| 62 | Phenytoin 100mg | - | — | 100 | Phenytoin 100 mg `1cdc4c03-…` | Mapped, price 0, stock 0 | EXISTS BUT INCOMPLETE | Price + stock 100 vs 0 |
| 63 | Marcfix | - | — | 4 | None | None | MISSING | Same brand as #1, suspension |
| 64 | Midazolam | - | — | 7 | Several (1, 2, 5 mg/ml; 7.5, 15 mg) | All | REQUIRES HOSPITAL CLARIFICATION | Strength/form |
| 65 | C Q | - | Injection | 15 | Possibly Chloroquine — not proven | Chloroquine tablets exist | REQUIRES HOSPITAL CLARIFICATION | What is C Q? |
| 66 | tube | - | — | 1 | None | None | REQUIRES HOSPITAL CLARIFICATION | Which tube |
| 67 | Cotten wool big size | - | Consumable | 0 (Out of Stock) | None | None | MISSING | Consumable |
| 68 | Glibenclamide 5mg | - | — | 95 | None | None | MISSING | |
| 69 | Astymin | - | — | 78 | None | None | MISSING | Capsule; third Astymin line |
| 70 | Aldomet | - | — | 98 | Methyldopa 250 mg or 500 mg | Both | REQUIRES HOSPITAL CLARIFICATION | Brand; strength |
| 71 | Chewable Vitamin C 1000mg | - | — | 20 | Ascorbic acid 100 mg / 500 mg only; TEST 100 mg | Those | REQUIRES HOSPITAL CLARIFICATION | 1000 mg not in catalogue |
| 72 | Pampas | - | — | 0 (Out of Stock) | None | None | MISSING | Likely nappies |
| 73 | Astyfer | - | Capsule | 78 | None | None | MISSING | Brand |
| 74 | mannitol 20% | - | — | 9 | Mannitol 20% `bc05b168-…` | Mapped, price 0, stock 0 | EXISTS BUT INCOMPLETE | Price + stock 9 vs 0 |
| 75 | Artesunate 60mg | - | — | 27 | Artesunate 60 mg `20645ef9-…` | Mapped, price 0, stock 0 | EXISTS BUT INCOMPLETE | Price + stock 27 vs 0 |
| 76 | Tavanic | - | Drip | 0 (Out of Stock) | None (no levofloxacin) | None | MISSING | Brand levofloxacin |
| 77 | Progesterone per mil | - | — | 2 | None | None | REQUIRES HOSPITAL CLARIFICATION | Per ml of what |
| 78 | guaze | - | — | 48 | None | None | MISSING | Gauze consumable |
| 79 | Linagliptin | - | — | 8 | None | None | MISSING | Strength |
| 80 | Metolazone | - | — | 0 (Out of Stock) | None | None | MISSING | |
| 81 | Dapagliflozin | - | — | 0 (Out of Stock) | None | None | MISSING | |
| 82 | Terbinafine 250mg | - | — | 8 | None | None | MISSING | |
| 83 | Plastic Bell 1.5 | - | — | 6 | None | None | MISSING | Device |
| 84 | Plastic Bell 1.3 | - | — | 3 | None | None | MISSING | |
| 85 | Plastic Bell 1.4 | - | — | 2 | None | None | MISSING | |
| 86 | Telmisartan 80mg | - | — | 74 | Telmisartan 80 mg `9baee6b8-…` | Mapped, price 0, stock 0 | EXISTS BUT INCOMPLETE | Price + stock 74 vs 0 |
| 87 | insulin syring | - | — | 7 | Insulin vials exist; **no syringe** | Insulin products only | MISSING | Consumable vs insulin |
| 88 | Tab Ranitidine | - | — | 200 | Ranitidine 150 mg `3bfc0a0a-…` (also inj) | Mapped | LIKELY MATCH — VERIFY | Confirm 150 mg |
| 89 | Feeding Tube size 8 | - | — | 0 (Out of Stock) | None | None | MISSING | Consumable |
| 90 | Catheter size 10 | - | — | 3 | None | None | MISSING | |
| 91 | Catheter size 8 | - | — | 0 (Out of Stock) | None | None | MISSING | |
| 92 | Surgical blade size 15 | - | — | 57 | None | None | MISSING | |
| 93 | Skin Traction Kit | - | — | 0 (Out of Stock) | None | None | MISSING | |
| 94 | Multivitamin | - | — | 15 | None named Multivitamin | None | REQUIRES HOSPITAL CLARIFICATION | Too generic |
| 95 | olanzapine 5mg | - | — | 2 | None | None | MISSING | |
| 96 | ondasetron | - | — | 30 | Ondansetron 4 mg `eb7f981e-…` | Mapped | LIKELY MATCH — VERIFY | Spelling; confirm 4 mg |
| 97 | ondansetron | - | — | 13 | Ondansetron 2 mg/ml `081dab88-…` | Mapped | LIKELY MATCH — VERIFY | Injection vs tablet #96 |
| 98 | silk 2/0 | - | — | 8 | None | None | MISSING | Suture |
| 99 | amitryiptyline | - | — | 257 | Amitriptyline 10/25/50/75 mg | All four | REQUIRES HOSPITAL CLARIFICATION | Spelling; which strength |
| 100 | Antalgex T | - | — | 396 | None | None | MISSING | Brand (tramadol combo?) |

Paracetamol 500 mg exists in OpenMRS/Odoo (`e8265115-…` and TEST `1c88be47-…`) but is **not** in the hospital stock file.

---

## 15. Summary counts

Counted from the tables above. Not estimated.

### LABORATORY (hospital rows = **80**, S/N 1–80)

| Bucket | Count |
|---|---|
| Total supplied | **80** |
| Exact matches | **0** |
| Likely matches requiring verification | **46** |
| Existing but not configured (exact dictionary name) | **4** (VDRL, Serum Pregnancy Test, Urine Pregnancy Test, Serum potassium) |
| Missing | **18** |
| Duplicates / possible duplicates | **2** (Hormonal Profile vs individual hormones; Urinalysis Only vs Urinalysis with Microscopy) |
| Clarifications required | **10** |

Check: 0+46+4+18+2+10 = **80**.

### PHARMACY (hospital rows = **100**)

| Bucket | Count |
|---|---|
| Total supplied | **100** |
| Exact matches | **0** |
| Likely matches requiring verification | **15** |
| Existing but incomplete | **5** (Cetirizine 10 mg, Phenytoin 100 mg, Mannitol 20%, Artesunate 60 mg, Telmisartan 80 mg) |
| Missing | **66** |
| Duplicates / possible duplicates | **0** as identical lines (Astymin/Marcfix are **different forms**, counted as missing brands) |
| Stock discrepancies | **100** hospital rows vs Odoo (plus TEST paracetamol in Odoo not in the file) |
| Clarifications required | **14** |

Check: 0+15+5+66+0+14 = **100**.

---

## 16. Hospital clarification questions

Only questions this reconciliation actually raised:

1. Is **Medicines Stock.xlsx** a physical stock count, a catalogue, or both? May we **not** load quantities into Odoo until that is answered?
2. What are the approved **pharmacy selling prices**? (None were in the file.)
3. For branded lines (Marcfix, Amatem, LYNTRIAXONE, Astymin, Aldomet, Ventolin, Clofenac, Ducolax, Primolut, Antalgex T, …), what is the **generic, strength, and form**? Are brand and generic separate sellable products?
4. For drugs with several OpenMRS strengths (ceftriaxone, ceftazidime, propranolol, oxytocin, midazolam, methyldopa, amitriptyline), **which strength** does the hospital stock?
5. Should **consumables** (needles, catheters, gauze, sutures, pampers, blades, feeding tubes, plastic bells, tissue, cotton wool, insulin syringes) live in Pharmacy stock or a separate stores list?
6. What does **C Q**, **tube**, **Progesterone per mil**, and **Multivitamin** mean?
7. Are laboratory prices in the Excel the **approved patient prices** (and is tax included)?
8. Which tests marked **Outsource** should appear on the doctor’s order list vs be sent out?
9. Is **AFP “Not stat”** still orderable?
10. What is **LVS**?
11. What does **Genotype** report (AA/AS/SS vs electrophoresis)?
12. For each **panel**, what are the **component tests** the hospital actually reports? Especially FBC, E/U/Cr, LFT (must hepatitis stay in LFT?), Lipid (include VLDL?), Viral Marker, HBsAg serology, thyroid free vs total, clotting PT/PTTK.
13. Is **Hormonal Profile ₦8,000 each** the same as the listed FSH/LH/… rows?
14. Are **CA-125 / CA-19-9 / CA-15-3** three orderables at ₦15,000 each?
15. Are **blood pints** and **donor screening** laboratory tests or blood-bank / theatre services?
16. Confirm **Amoxiclav 457 mg** (400/57) vs the OpenMRS co-amoxiclav strengths that exist.
17. Confirm **Clofenac 100 mg** vs OpenMRS Diclofenac **50 mg** only.
18. Confirm **Vitamin C chewable 1000 mg** vs OpenMRS 100/500 mg.

---

## 17. Reuse recommendations

### A. CAN REUSE NOW

- OpenMRS **Lab Order** type and `bahmniencounter` `orders[]`
- OpenELIS atomfeed (proven on Malarial smear)
- Hospital EMR Laboratory **fee** path (Laboratory shop, uuid mapping, refuse ₦1.00)
- Accountant payment (unchanged)
- OpenMRS **Drug Order** + Atomfeed + Pharmacy Counter + READY TO DISPENSE (proven ORD-7)
- `product.product.uuid` = OpenMRS drug/concept uuid
- Dictionary concepts that are **likely** the hospital tests (after verification), including VDRL, pregnancy tests, serum potassium, cetirizine 10 mg, phenytoin 100 mg, mannitol 20%, artesunate 60 mg, telmisartan 80 mg
- Do **not** reuse Basic metabolic panel as E/U/Cr
- Do **not** reuse Clotting Panel as PT/PTTK
- Do **not** reuse LFT set as-is without removing unexpected HBsAg/HCV members (or hospital confirms them)
- Do **not** reuse TEST products/prices/stock as the hospital catalogue

### B. NEEDS CONFIGURATION

After hospital confirmation, using **existing** architecture only:

- Put confirmed tests/panels into `All_Tests_and_Panels` (and OpenELIS will follow the lab feed)
- Set Odoo `list_price` on the mapped uuid products to the confirmed ₦ prices (not 1.00)
- Create OpenMRS concepts/drugs **only** where MISSING (HbA1c, LH, meropenem, hospital brands once composition is known, HVS MCS, etc.) — OpenMRS-first, then atomfeed to Odoo
- LabSet membership that matches **this hospital’s** panels
- Doctor lab ordering UI (already Coming Soon) once the set is non-empty
- Pharmacy: new drugs OpenMRS-first; then Odoo price and a **separate, approved** stock count

### C. NEEDS HOSPITAL DECISION

Everything in §16. Especially: stock file meaning; pharmacy prices; LVS; panel components; outsourced tests; blood bank vs lab; brand vs generic; consumables location; “each” hormone/tumour-marker rows.

---

## 18. Configuration requirements (later — not done)

| Requirement | System | Not in this phase |
|---|---|---|
| Hospital orderable set | OpenMRS `All_Tests_and_Panels` | Do not add members now |
| Real lab prices | Odoo products (uuid = concept) | Do not write list_price now |
| Missing lab concepts | OpenMRS dictionary | Do not create |
| Missing drugs | OpenMRS drug then atomfeed | Do not create |
| Stock | Odoo WH/Stock after a count | Do not import Excel qty |
| Lab Order `order.type` | Only if Atomfeed billing is wanted | Departmental fee already exists |

---

## 19. Items requiring approval

- Treating Excel lab ₦ figures as live patient tariffs
- Importing pharmacy **quantities**
- Mapping LFT dictionary set (includes hepatitis tests) to hospital LFT
- Mapping BMP to E/U/Cr
- Selling outsourced tests on the OPD order list
- Creating blood-pint products as laboratory tests
- Creating a second product database for brands

---

## 20. Final recommendation

1. Show this inventory to the laboratory and pharmacy leads.
2. Get answers to §16 before any import.
3. Reuse OpenMRS + OpenELIS + Odoo uuid mapping. **Do not** build a second lab database, drug-order system, billing system, or inventory system.
4. Laboratory: configure confirmed concepts into `All_Tests_and_Panels`, then prices, then ordering.
5. Pharmacy: identify generic/strength/form for each stock line; create missing drugs OpenMRS-first; set prices; take a **controlled stock count** into Odoo — do not paste this Excel.

**STOP. No implementation in this phase.**

---

## Appendix: npm

`npm test` and `npm run build` may be run; they do not write hospital data. Recorded in the audit response.

**Data changed this audit: none.**
