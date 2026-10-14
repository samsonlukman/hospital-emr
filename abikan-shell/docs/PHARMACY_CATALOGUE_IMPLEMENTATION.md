# Pharmacy catalogue implementation

Date: **20 Aug 2026** (Africa/Lagos). Development / testing only.

Related: `PHARMACY_UI_IMPLEMENTATION.md`, `PRESCRIPTION_E2E_TEST.md`, `LAB_PHARMACY_CATALOGUE_RECONCILIATION.md`, `PHARMACY_DISPENSING_IMPLEMENTATION.md`, `PHARMACY_BILLING_PAYMENT_DISPENSING_WORKFLOW.md`.

This phase makes the hospital’s supplied medicine list usable for **development and testing**. It does **not** build a second pharmacy, inventory, accounting, or dispensing system.

```
Doctor
  → OpenMRS Drug Order
  → Atomfeed
  → Odoo Pharmacy sale
  → Odoo invoice
  → Accountant Cash payment
  → Pharmacy PAID / READY TO DISPENSE
  → Dispense (Odoo picking)
```

Clinical does not write Odoo. Pharmacy does not collect payment. Spreadsheet quantities were **not** imported. Temporary selling prices are **₦100** and are **not** hospital-approved production prices.

Laboratory was not changed. ORD-7 was **not** dispensed.

---

## Investigation inventory

Hospital source: `abikan-shell/Medicines Stock.xlsx` (Sheet1, **100** named rows). Working copy: `server/patient-account/data/pharmacy_catalogue.csv`. Binding: `server/patient-account/data/pharmacy_catalogue_map.json`. Runtime drug UUIDs: `server/patient-account/data/pharmacy_catalogue_runtime.json`.

| Bucket | Finding |
|---|---|
| **A. Already usable** | OpenMRS Drug Order → Atomfeed → Odoo Pharmacy Counter → invoice → Accountant Cash → Pharmacy READY TO DISPENSE → Dispense. Pharmacy UI (dashboard, prescriptions, ready, dispensed). RBAC. Isolated TEST product **Paracetamol 500 mg — TEST**. Hospital Pharmacy (NGN) pricelist. |
| **B. Existing but incomplete** | Generic Bahmni drug dictionary mirrored in Odoo. Many ordinary products had no usable hospital selling price. Hospital list has names and rough quantities, not approved prices or confirmed stock. Pharmacy **Stock** remains Coming soon; current stock is shown on Drug Catalogue. |
| **C. Missing** | 79 hospital rows that cannot be mapped without inventing composition, strength, or form. Approved production prices. Confirmed physical stock. |
| **D. Duplicate / name collision** | Same generic in several strengths or forms (Ceftriaxone, Ceftazidime, Oxytocin, Midazolam, Methyldopa, Amitriptyline). Gentamycin eye **and** ointment. Astymin injection / syrup / capsule. Ondansetron tablet **vs** injection (kept as two mappings). TEST paracetamol **vs** ordinary paracetamol. |
| **E. Needs mapping** | 21 rows mapped (16 reused existing OpenMRS drugs, 5 new drugs created OpenMRS-first). Binding lives in configuration data, not React. |

---

## 1. Hospital pharmacy list

| Field | Value |
|---|---|
| File | `abikan-shell/Medicines Stock.xlsx` |
| Rows | **100** (S/N 1–100) |
| Typical columns | Medicine Name, Medicine Category, Available Qty |
| Selling prices in file | Not reliable. Not used as production prices. |
| Quantities in file | Not confirmed physical stock. **Not imported.** |

The list mixes branded names, generics, IV fluids, and consumables (needles, sutures, catheters, gauze). Consumables are not OpenMRS Drug Orders.

---

## 2. Number of items mapped

**21** of 100.

| Action | Count |
|---|---|
| Reuse existing OpenMRS drug / Odoo product | 16 |
| Create new OpenMRS drug (then atomfeed → Odoo) | 5 |
| Skip (stop conditions) | 79 |

---

## 3. Existing items reused

Temporary development price ₦100. Spreadsheet quantity **not** imported. TEST paracetamol was **not** used as a mapping target.

| S/N | Hospital name | OpenMRS drug | uuid |
|---|---|---|---|
| 12 | Vitamin D3 1000iu | Cholecalciferol 1000 IU Tablet | `658899ad-f703-4827-80a6-26dea4924640` |
| 20 | cetirizine 10mg | Cetirizine 10 mg Tablet | `7e0766e1-b679-4eb3-ab93-d63910ad6eb4` |
| 26 | Glycopyrrolate inj | Glycopyrrolate 0.2 mg/ml Injection | `cf4fb32b-721a-4b67-b58d-4dc7ebd24b8e` |
| 31 | Tranexamic Acid tab | Tranexamic acid 500 mg Tablet | `319e7f86-b715-4e0e-b7e0-fa6958e2e8ad` |
| 33 | lactulose | Lactulose 10 g/15 ml | `ee7fb75f-c246-44b1-8dda-9aa48355500d` |
| 45 | Nitroglycerin (Tablet) | Nitroglycerin 0.5 mg sublingual | `527c3a11-76ed-4dd7-9dab-b621eb200d99` |
| 46 | Quinine Tablet | Quinine 300 mg Tablet | `7493f5df-fd4c-461d-9003-3ddd7632e04f` |
| 51 | Dobutamine | Dobutamine 50 mg/ml | `113e95b6-f87c-43a2-909d-5083ca969d60` |
| 60 | Vitamin B2 | Riboflavin 5 mg Tablet | `179b7880-5437-4547-884f-dddcc31681b8` |
| 62 | Phenytoin 100mg | Phenytoin 100 mg Tablet | `1cdc4c03-5df4-49be-b279-3430c325bb18` |
| 74 | mannitol 20% | Mannitol 20% | `bc05b168-40ad-43c5-8291-0147ca8e7b33` |
| 75 | Artesunate 60mg | Artesunate 60 mg | `20645ef9-4c72-4036-b210-7bd515e27ebc` |
| 86 | Telmisartan 80mg | Telmisartan 80 mg Tablet | `9baee6b8-3bd1-4cf3-8fae-f751b0bcdd03` |
| 88 | Tab Ranitidine | Ranitidine 150 mg Tablet | `3bfc0a0a-9de2-4b3f-a344-02edaf5cea05` |
| 96 | ondasetron (Tablet) | Ondansetron 4 mg Tablet | `eb7f981e-0748-4da0-bd42-c49dbd153c0d` |
| 97 | ondansetron (Injection) | Ondansetron 2 mg/ml Injection | `081dab88-0929-4148-98e7-f9143a760e8d` |

Strength and form were not collapsed: tablet Tranexamic acid is not the injection; tablet Nitroglycerin is not the injection; tablet Ondansetron is not the injection; Vitamin D3 1000 IU is not the Calcium + D3 250 IU combo.

---

## 4. New items created

Created **OpenMRS-first**, then allowed the existing drug atomfeed to create the Odoo product. Stock left at **0**. Price set to temporary ₦100 after the product existed.

| S/N | Hospital name | Created OpenMRS drug | uuid | Odoo product id |
|---|---|---|---|---|
| 14 | Rivaroxaban 10mg | Rivaroxaban 10 mg Tablet | `9bd94bb7-acac-4806-a58f-3110ea8d08d6` | 2435 |
| 41 | Progesterone 100mg inj | Progesterone 100 mg Injection | `40141cea-3ebb-4fd4-aec8-8a9e1beee5ac` | 2436 |
| 68 | Glibenclamide 5mg | Glibenclamide 5 mg Tablet | `f25316a0-34d0-4af7-9dec-c191fa1660b7` | 2437 |
| 82 | Terbinafine 250mg | Terbinafine 250 mg Tablet | `828c7da4-69ac-4061-923c-8de98bff4005` | 2438 |
| 95 | olanzapine 5mg | Olanzapine 5 mg Tablet | `1174a178-dc07-4d64-b35d-c1dc4695d928` | 2439 |

These five had an explicit generic, strength, and form, and no existing matching drug.

---

## 5. Unresolved items

**79** skipped. Full reasons are in `pharmacy_catalogue_map.json`. Counts:

| Skip reason | Count | Examples |
|---|---|---|
| `brand_without_composition` | 22 | Marcfix, Astymin, Amatem Forte, Primolut N, Tavanic |
| `consumable_not_drug_order` | 20 | Catheters, needles, sutures, gauze, feeding tubes |
| `missing_strength_or_form` | 17 | Cabergoline, Meropenem, Clarithromycin, Losartan, Linagliptin |
| `multiple_strengths_or_forms` | 10 | LYNTRIAXONE, Ceftazidime, Propranolol, oxytocin, Midazolam, Aldomet, amitriptyline, Amoxiclav 457mg, Clofenac 100mg, Chewable Vitamin C 1000mg |
| `ambiguous_identity` | 4 | C Q, tube, Progesterone per mil, Multivitamin |
| `would_collapse_distinct_forms` | 2 | Gentamycin eye **and** Gentamycin ointment |
| `brand_to_generic_unconfirmed` | 2 | Ducolax, ventolin nebules |
| `composition_not_confirmed` | 1 | Sodium Bicarbonate (“as per IP” already exists; hospital composition not supplied) |
| `not_a_prescribable_drug` | 1 | D/SALINE 1LITRE |

Do not invent composition. Do not collapse 250 mg with 1 g. Do not map a brand to a generic without hospital confirmation.

---

## 6. Temporary development pricing

Mapped reuse and create products: Odoo `list_price` = **100.00 NGN**.

Pharmacy Counter shop pricelist: **Hospital Pharmacy (NGN)** (id 3). Sales for mapped items use NGN, not USD Public Pricelist.

Label used in configuration:

**DEVELOPMENT PRICE — NOT FINAL HOSPITAL PRICE**

Cetirizine 10 mg (the isolated E2E medicine) billed at ₦100 × qty 2 = **₦200** on S00024 / INV/2026/00023, with taxes stripped on these development pharmacy lines.

---

## 7. Why prices are temporary

The hospital list does not contain reliable selling prices. Waiting for approved prices would block development of prescribe → pay → dispense. ₦100 is a workflow placeholder only. It is **not** the hospital’s approved price and must be replaced before go-live.

Unrelated products were not repriced:

| Product | Price after this phase |
|---|---|
| Paracetamol 500 mg — TEST | **₦1000** (unchanged) |
| Full Blood Count (FBC) | **₦5000** (Laboratory unchanged) |
| Laboratory shop | still **Hospital Laboratory (NGN)** |

---

## 8. Stock handling

Odoo remains the inventory source of truth. Hospital EMR Pharmacy reads Odoo/OpenMRS state. There is no second stock ledger in React or local storage.

Ordinary mapped products: on-hand left at **0** unless a controlled TEST quantity was required.

Isolated E2E TEST stock only:

| Product | Location | Qty applied | Note |
|---|---|---|---|
| Cetirizine 10 mg (product 159) | WH/Stock | **2** | `ABIKAN PHARMACY CATALOGUE E2E TEST STOCK — not hospital inventory` |

That quantity was then consumed by ORD-11 dispensing (see §15 and §17).

ORD-7 TEST paracetamol stock was **not** altered for this catalogue pass (88 on hand, 2 reserved).

---

## 9. Why spreadsheet quantities were not imported

The Available Qty column is not a confirmed physical count. Importing it would overwrite or invent hospital inventory. Production stock reconciliation is a later hospital activity. The configure script (`scripts/configure-pharmacy-catalogue.py`) has `importSpreadsheetQuantities: false` and only applies the two-unit Cetirizine TEST stock when run with `--apply-test-stock`.

---

## 10. OpenMRS drug mapping

Doctors continue to search live OpenMRS `GET /drug?q=`. The hospital list is **not** hardcoded in Pharmacy or Clinical React components.

Configuration:

- `server/patient-account/data/pharmacy_catalogue.csv` — hospital rows
- `server/patient-account/data/pharmacy_catalogue_map.json` — reuse / create / skip
- `server/patient-account/data/pharmacy_catalogue_runtime.json` — created drug UUIDs
- `server/patient-account/pharmacy_catalogue.py` — loaders
- `scripts/configure-pharmacy-catalogue.py` — idempotent OpenMRS-first create + Odoo NGN 100

New drugs use existing concepts where the identity was explicit (for example Glibenclamide 5 mg uses the existing Glyburide/Glibenclamide concept).

---

## 11. Odoo product mapping

Odoo products for reused drugs already existed via the drug atomfeed. New drugs followed the same feed. After the product existed, the script set `list_price=100`, removed sale taxes on those lines, and pointed Pharmacy Counter at **Hospital Pharmacy (NGN)**.

Do not treat Odoo `qty_available` in Hospital EMR UI as a second catalogue. Drug Catalogue reads live Odoo stock; the **Stock** nav item remains Coming soon.

---

## 12. Prescription flow

Unchanged:

```
Clinical prescribe UI
  → POST Bahmni encounter drug order
  → OpenMRS Drug Order
  → Atomfeed
  → Odoo pharmacy sale (Pharmacy Counter)
```

No Hospital EMR-specific prescription database. No Clinical write to Odoo.

ORD-11 used a **new** Consultation encounter (`a2c7a6cd-d07f-4064-894b-019a337888e5`). The ORD-7 encounter was not updated (that encounter 500s on save because of a duplicate bacteriology uuid and must stay untouched).

---

## 13. Payment flow

Unchanged:

```
UNPAID → Accountant receives Cash → PAID → Pharmacy eligible to dispense
```

Pharmacy has no Pay / Cash / Bank / Receipt controls. Accountant `POST /openmrs/abikan-api/accountant/payment` remains the payment write.

ORD-11: invoice **INV/2026/00023** (id 34), Cash journal, receipt **PCSH1/2026/00010**, ₦200. INV/2026/00022 (₦1500, likely laboratory on the same test patient) was **not** paid in this pass.

---

## 14. Dispensing flow

Existing path, unchanged:

```
POST /openmrs/abikan-api/pharmacy/prescription/{orderUuid}/dispense
  body: { requestId }
  → Odoo stock.picking.button_validate
```

Pharmacy confirmation copy: “This will mark the prescription as dispensed and update pharmacy stock.”

ORD-11 was dispensed by `pharmacy.abikan` from the Pharmacy dashboard. ORD-7 was **not** clicked.

---

## 15. Stock movement

Observed on Cetirizine 10 mg, product 159, WH/Stock, qty 2, sale **S00024**, picking **WH/OUT/00004**:

| Stage | On hand | Reserved | Picking |
|---|---|---|---|
| After TEST stock apply / before sale | 2 | 0 | — |
| After Atomfeed draft sale | 2 | 0 | — |
| After `sale.order` confirm | 2 | 2 | WH/OUT/00004 **assigned** |
| After Accountant Cash payment | 2 | 2 | still **assigned** |
| After Pharmacy Dispense | **0** | **0** | WH/OUT/00004 **done** |

**Payment does not reduce on-hand.** Sale creation does not reduce on-hand. Confirm **reserves**. Dispense (picking validate) **delivers** and reduces on-hand.

ORD-7 picking WH/OUT/00003 remains **assigned**. TEST paracetamol remains 88 on hand, 2 reserved.

---

## 16. Security

RBAC was not weakened. Live checks on 20 Aug 2026:

| Caller | Action | Result |
|---|---|---|
| Unauthenticated | `GET /pharmacy/queue` | **401** |
| Unauthenticated | `POST /accountant/payment` | **401** |
| `pharmacy.abikan` | `GET /pharmacy/queue` | **200** (can view and dispense) |
| `pharmacy.abikan` | `POST /accountant/payment` | **403** Accountant workspace |
| `accountant.abikan` | `GET /accountant/dashboard` | **200** |
| `accountant.abikan` | `GET /pharmacy/queue` | **403** Pharmacy workspace |
| `accountant.abikan` | `POST …/dispense` | **403** Pharmacy workspace |
| `doctor.abikan` | `POST …/dispense` | **403** |
| `doctor.abikan` | `POST /accountant/payment` | **403** |
| `nurse.abikan` | `POST …/dispense` | **403** |
| `reception.abikan` | `POST …/dispense` | **403** |
| `nurse.abikan` / `reception.abikan` | `POST /accountant/payment` | **403** |

Pharmacy UI: no Administration, no Accountant, no Pay button. Drug Catalogue is search / add / edit. Stock remains Coming soon.

Doctor can prescribe through Clinical. Doctor cannot dispense or collect payment.

---

## 17. E2E test

Isolated prescription **ORD-11**. **ORD-7 was not used and was not dispensed.**

Existing dedicated test patient only (not ordinary hospital patients).

| Field | Value |
|---|---|
| Patient | **ABIKAN E2E TEST PATIENT** ABC200016 `f242364e-b70f-4fec-b29e-8ad4fbe147b5` |
| Visit | `6478a94e-1657-4abe-9271-7cf92b821576` (existing open OPD) |
| Encounter | `a2c7a6cd-d07f-4064-894b-019a337888e5` (new Consultation; not the ORD-7 encounter) |
| Drug order | **ORD-11** `36f35686-d4f1-472a-af73-5f59795283aa` |
| Medicine | Cetirizine 10 mg Tablet `7e0766e1-b679-4eb3-ab93-d63910ad6eb4` · qty **2** |
| Odoo sale | **S00024** id 24 · confirmed · Hospital Pharmacy (NGN) · **₦200** |
| Invoice | **INV/2026/00023** id 34 · posted · paid |
| Payment | **PCSH1/2026/00010** Cash ₦200 · 20 Aug 2026 |
| Pharmacy after pay | PAID / READY TO DISPENSE / `canDispense=true` |
| Pharmacy after dispense | PAID / **DISPENSED** / `canDispense=false` / delivered 2 |
| Picking | WH/OUT/00004 **assigned** → **done** |
| Stock before dispense | on hand 2, reserved 2 |
| Stock after dispense | on hand **0**, reserved **0** |

Clinical did not write Odoo. Accountant collected payment. Pharmacy dispensed.

ORD-7 remains:

| Field | Value |
|---|---|
| Order | ORD-7 `5e744fe0-d516-4255-b45f-3e4209e11c45` |
| Medicine | Paracetamol 500 mg — TEST |
| Status | **PAID** / **READY TO DISPENSE** / `canDispense=true` |
| Picking | WH/OUT/00003 still **assigned** |

---

## 18. Remaining limitations

- 79 hospital rows are unresolved until the hospital supplies composition, strength, form, or a confirmed brand→generic mapping.
- Consumables are not Drug Orders; they need a later hospital decision, not a guessed catalogue.
- ₦100 is a development price on mapped and newly added items only.
- Ordinary mapped products still have **zero** stock except controlled TEST quantities and inventory receipts recorded in Pharmacy → Inventory.
- Pharmacy **Inventory** is live for receive, adjustment, and history. Drug Catalogue remains search, add, and edit of product information. Catalogue Edit cannot overwrite shelf quantity.
- Saving a new prescription onto the original ORD-7 Consultation encounter still 500s (duplicate bacteriology uuid). New prescriptions on this test patient need a new encounter.
- Pharmacists do not receive OpenMRS **Manage Concepts**. New OpenMRS Drug records are written by the Hospital EMR API using the existing dictionary identity after Pharmacy RBAC succeeds.

---

## 19. Go-live steps (prices and stock)

1. Hospital supplies **approved NGN selling prices** for every mapped product.
2. Replace temporary ₦100 on those Odoo products / Hospital Pharmacy pricelist items. Do not treat ₦100 as production.
3. Do **not** use the spreadsheet Available Qty as the stock figure.
4. Hospital performs a **physical count** and records it in Odoo.
5. Resolve skipped rows with hospital pharmacists: strength, form, brand composition, which Ceftriaxone, whether consumables are billed, and so on.
6. Keep TEST products and ORD-7 out of production data cleanup until that dedicated test is formally closed.
7. Leave Laboratory prices and the Laboratory shop on Hospital Laboratory (NGN).

Configure later with the same files (`pharmacy_catalogue_map.json` + `configure-pharmacy-catalogue.py` pattern), not by editing React.

---

## Pharmacy catalogue management

Date: **20 Aug 2026** (Africa/Lagos).

THE HOSPITAL CATALOGUE IS THE BUSINESS SOURCE FOR WHICH MEDICINES THE HOSPITAL CARRIES.

ODOO IS THE UNDERLYING INVENTORY/FINANCIAL SYSTEM.

ABIKAN IS THE HOSPITAL-FACING INTERFACE.

TEMPORARY PRICES ARE NOT PRODUCTION PRICES.

TEST STOCK IS NOT PRODUCTION STOCK.

This is not a second independent catalogue. Add/edit follows the existing path:

```
Authorized Pharmacy staff in Hospital EMR
  → OpenMRS Drug (create or reuse)
  → Atomfeed
  → Odoo pharmacy product
  → development price in Odoo
```

Staff never enter OpenMRS UUIDs, Odoo product ids, or Atomfeed ids.

### Catalogue editing vs stock

**CATALOGUE EDITING** is for medicine/product information:

- Medicine / generic name
- Brand name
- Strength
- Dosage form
- Selling price (development price until go-live)
- Active / inactive

**STOCK MANAGEMENT** is a separate workflow in **Pharmacy → Inventory**. The Drug Catalogue Edit form has no quantity field and cannot overwrite shelf quantity. Receive Stock, stock adjustment, and history live on Inventory, not on catalogue edit.

**STOCK SOURCE:** Odoo. The catalogue only **displays** live on-hand quantity. Hospital EMR has no local stock table.

**DISPENSING:** The existing prescription → payment → picking workflow still reduces Odoo stock. That path was not changed.

The previous Cetirizine TEST stock of 2 units was controlled development stock. It was consumed by the isolated ORD-13 E2E (2 → reserved 2 → paid still 2 → dispensed 0). This inventory phase received a new controlled quantity on Cetirizine; it did not recreate that earlier TEST stock of 2 through the catalogue editor.

### Where it appears

Pharmacy workspace (queue screens unchanged):

```
Pharmacy
├── Queue (Dashboard, Prescriptions, Ready to Dispense, Dispensed)
├── Drug Catalogue     #/pharmacy/catalogue
│   ├── Search
│   ├── Add Medicine
│   └── Edit Medicine
├── Inventory          #/pharmacy/inventory
│   ├── Receive Stock
│   ├── Adjust Stock
│   └── View History
└── Dispensing History (Dispensed)
```

**Stock** is implemented as **Inventory**. No Pay button. Clinical prescribe is unchanged.

Each row shows name, optional hospital list name, optional brand, strength, form, **read-only** live shelf quantity, development selling price, and Available / Not available. Edit does not include a stock quantity input.

### Who can add/edit

| Caller | View catalogue | Add/edit | View stock | Dispense | Receive / adjust | Pay patient |
|---|---|---|---|---|---|---|
| `pharmacy.abikan` | Yes | Yes | Yes | Yes | Yes (inventory permission) | **403** |
| Pharmacist without inventory permission | Yes | Yes | Yes | Yes | **403** | **403** |
| `accountant.abikan` | **403** | **403** | **403** | **403** | **403** | Yes |
| `doctor.abikan` | **403** | **403** | **403** | **403** | **403** | **403** (prescribe in Clinical only) |
| `nurse.abikan` | **403** | **403** | **403** | **403** | **403** | **403** |
| `reception.abikan` | **403** | **403** | **403** | **403** | **403** | **403** |
| Unauthenticated | **401** | **401** | **401** | **401** | **401** | **401** |

RBAC was not weakened. Pharmacists are not given OpenMRS **Manage Concepts**. After `require_pharmacist`, OpenMRS Drug create/retire uses the same dictionary identity as `configure-pharmacy-catalogue.py` (`abikan.admin`). Odoo **price** writes stay server-side. Catalogue add/edit **ignores** any stock field. Dedicated TEST paracetamol (`1c88be47-…`) cannot be edited from this screen.

### Catalogue data flow

1. Hospital list (spreadsheet → `pharmacy_catalogue_map.json`) is the business source for mapped items.
2. Medicines added in Drug Catalogue are stored as OpenMRS drugs, then listed via Odoo `ir.config_parameter` `abikan.pharmacy.hospital_catalogue` (the API volume is read-only, so new rows are not written into the JSON map).
3. `GET /pharmacy/catalogue` unions mapped JSON + managed extras, then overlays live Odoo price, stock, and active flag.
4. React does not hardcode medicine names.

**22** items visible after adding **Loratadine 10 mg Tablet** (`1d9d6afb-0699-492d-aa75-c58895082556`). Ondansetron **4 mg Tablet** and Ondansetron **2 mg/ml Injection** remain separate rows.

### OpenMRS / Odoo relationship

Odoo does not decide which medicines the hospital carries. It holds inventory, selling price, and the sale/invoice/picking for dispensing. OpenMRS remains the drug dictionary and the clinical Drug Order. Atomfeed creates the Odoo product from the OpenMRS **drug** uuid.

If the generic is not already a Drug-class concept, add is refused (`missing_generic`). Ambiguous generics are refused. That is intentional: Hospital EMR does not invent CIEL concepts.

### Temporary development pricing

Selling price for mapped items and for newly added test medicines is **₦100**.

**DEVELOPMENT PRICE — NOT FINAL HOSPITAL PRICE**

The Drug Catalogue and the add/edit dialog state this in staff language. ₦100 is not a hospital-approved price.

TEST paracetamol remains **₦1000**. Laboratory prices were not changed.

### TEST stock

Controlled TEST stock only, for the isolated dispensing proof. Not hospital inventory. Spreadsheet quantities were not imported. ORD-7 / TEST paracetamol stock was not changed (88 on hand, 2 reserved).

| Product | Odoo id | Location | Qty | Note |
|---|---|---|---|---|
| Cetirizine 10 mg | 159 | WH/Stock | **2** | `TEST/DEVELOPMENT STOCK — not production stock` |

Set from Drug Catalogue **Edit** by `pharmacy.abikan` **before** stock was removed from catalogue editing. That quantity was then consumed by ORD-13. Catalogue Edit can no longer set it. Loratadine was added at shelf quantity **0**.

### Isolated dispensing proof (ORD-13)

Dedicated TEST patient only: **ABIKAN E2E TEST PATIENT** ABC200016. **ORD-7 was not dispensed.**

Clinical prescribe payload unchanged (`POST bahmnicore/bahmniencounter`). A new Consultation encounter was used (`286ab96e-…`). The ORD-7 encounter was not updated. Already-dispensed ORD-11 Cetirizine was discontinued on the TEST patient so the same mapped product could be prescribed again.

| Field | Value |
|---|---|
| Order | **ORD-13** `c26f23c6-8b3e-4f26-8580-c8788bd175c6` |
| Medicine | Cetirizine 10 mg Tablet · qty **2** |
| Encounter | `286ab96e-dbc5-49f4-bc61-e928f5e7f967` (new; not ORD-7) |
| Sale | **S00025** · Hospital Pharmacy (NGN) · ₦200 |
| Invoice | **INV/2026/00024** · Cash **PCSH1/2026/00011** |
| Picking | **WH/OUT/00005** |

Observed Odoo WH/Stock values (read live, not assumed):

| Stage | On hand | Reserved | Picking |
|---|---|---|---|
| 7. Before sale / after TEST stock | **2** | **0** | — |
| Sale created (draft) | **2** | **0** | — |
| 8. After confirmation | **2** | **2** | WH/OUT/00005 **assigned** |
| 9. After Accountant Cash payment | **2** | **2** | still **assigned** |
| Ready to dispense | **2** | **2** | **assigned** |
| 10. After Pharmacy Dispense | **0** | **0** | WH/OUT/00005 **done** |

**CONFIRM → RESERVE. PAYMENT → NO STOCK REDUCTION. DISPENSE → ACTUAL STOCK REDUCTION.**

ORD-13 after dispense: **PAID / DISPENSED** / `canDispense=false`. Pharmacy confirmed from Ready to Dispense (Cetirizine only).

### Existing ORD-7 status

Unchanged:

| Field | Value |
|---|---|
| Order | ORD-7 `5e744fe0-d516-4255-b45f-3e4209e11c45` |
| Medicine | Paracetamol 500 mg — TEST |
| Status | **PAID / READY TO DISPENSE** / `canDispense=true` |
| Picking | WH/OUT/00003 still **assigned** |
| Stock | 88 on hand, 2 reserved, price ₦1000 |

Laboratory was not changed.

### Remaining production work

- Replace ₦100 with hospital-approved NGN prices.
- Physical count into Odoo. Do not import spreadsheet Available Qty.
- Resolve 79 skipped hospital rows with pharmacists (composition, strength, form, brand→generic).
- Consumables need a later hospital decision.
- Keep TEST products, ORD-7, and this TEST stock out of production cleanup until formally closed.

---

## Tests

```
cd abikan-shell
npm test
npm run build
```

---

## Pharmacy inventory / stock management

Date: **21 Aug 2026** (Africa/Lagos). Development / testing only.

**CATALOGUE:** What medicines the hospital carries.

**INVENTORY:** How much physical stock exists and how it changes.

**PURCHASE PRICE:** What the hospital paid per unit for a particular stock receipt.

**SELLING PRICE:** What the hospital charges the patient.

**SUPPLIER PAYMENT:** Not part of this Inventory phase.

**ODOO:** Authoritative inventory system.

**ABIKAN:** Hospital-facing interface.

Laboratory, Clinical prescribing, patient payment, Pharmacy dispensing, and ORD-7 were not changed.

### 1. Catalogue vs inventory

| | Drug Catalogue | Inventory |
|---|---|---|
| Question | What medicines does this hospital carry? | How much of each medicine is physically on the shelf? |
| Fields | Name, brand, strength, form, selling price, active/inactive | On hand, reserved, available, status |
| Writes | OpenMRS drug + Odoo selling price / active flag | Odoo stock movements only |
| Stock quantity | Displayed read-only | Changed by Receive, Adjust, and existing Dispense |

The Drug Catalogue Edit form has **no** editable stock quantity and **no** catalogue-wide purchase price. Purchase price belongs to each receive transaction because different receipts can cost different amounts.

### 2. Inventory section

Location: **Pharmacy → Inventory** (`#/pharmacy/inventory`). Alias `#/pharmacy/stock`.

List columns: Medicine, Brand where available, Strength, Form, On Hand, Reserved, Available, Status.

Actions: Receive Stock, Adjust Stock, View History.

If the medicine is not in the hospital list yet, Inventory links to the existing Drug Catalogue **Add medicine** form (`#/pharmacy/catalogue/add`). Inventory does not create medicines itself. After the medicine is added, staff return to Inventory to receive stock.

Stock numbers are read from Odoo `stock.quant` at **WH/Stock**. There is no local stock table, no React stock ledger, and no duplicate inventory database.

### 3. Receive Stock

Meaning: the medicine has physically arrived and is being added to pharmacy inventory.

Not: paying a supplier, raising a purchase order, or posting a vendor bill.

Required: product, quantity received (> 0), purchase price per unit (> 0).

Optional: supplier, invoice/reference, note.

Example: Cetirizine on hand 0, receive 10 at ₦300 → on hand 10, receipt cost ₦3,000.

Selling price is not overwritten.

There is no **Pay Supplier** button.

### 4. Purchase price vs selling price

Selling price stays on the catalogue / Odoo `list_price` (development ₦100 for mapped items).

Purchase price is stored on the **receipt movement** (`stock.move.price_unit`). A later receipt at ₦350 does not replace an earlier receipt at ₦300.

Odoo product category **Drugs** uses **standard costing** and **manual periodic** valuation. `product.standard_price` is therefore **not** used as a single permanent purchase price (that would clobber earlier receipts). Hospital EMR does not write `standard_price` when receiving.

Where Odoo also writes `stock.valuation.layer` for a receipt, that layer is additional evidence of quantity. On this installation those layers currently store `unit_cost` **0** because the Drugs category uses **standard costing + periodic valuation**. The **authoritative per-receipt purchase price** is `stock.move.price_unit` on the incoming receipt (verified ₦300 on WH/IN/00004). Hospital EMR history displays that move price, not a local ledger.

Limitation: this hospital’s costing method is not AVCO/FIFO. Per-receipt cost is preserved on the incoming stock move (and on any valuation layer Odoo creates for that move). It is **not** a second Hospital EMR ledger.

### 5. Supplier payment separation

Supplier and invoice/reference may be recorded on the receipt.

Hospital EMR does **not** create a purchase order, vendor bill, or supplier payment in this phase.

Patient payment through Accounts is unchanged and is a different workflow.

### 6. Stock adjustment

Staff cannot type a new on-hand total as a silent overwrite.

Required: product, current on-hand (read-only), Increase or Decrease, quantity, reason.

Optional: reference, note.

Typical reasons: Incorrect opening stock, Physical stock count, Damaged stock, Expired stock, Lost/missing stock, Correction.

The resulting quantity is calculated. Decrease below zero is refused (`allow_negative_stock` is off). Decrease below reserved quantity is refused.

Odoo mechanism: `stock.quant.inventory_quantity` + `action_apply_inventory`, which creates an inventory-adjustment `stock.move`. The reason is written onto that move.

### 7. Inventory history

Hospital EMR displays Odoo `stock.move` history for the product at WH/Stock.

Captured where available: product, previous quantity, movement quantity, resulting quantity, type (Receive Stock / Stock Adjustment / Dispensing), purchase price and total cost for receipts, supplier, reason, user, date/time, reference.

User on XML-RPC writes is the integration account unless the receipt note recorded the signed-in pharmacy username (Receive Stock does).

Stock transfer is **not** implemented in this phase.

### 8. Odoo as inventory source

```
Hospital EMR Pharmacy Inventory UI
  → abikan-api
      receive  → stock.picking type Receipts (Vendors → WH/Stock) + stock.move.price_unit
      adjust   → stock.quant inventory apply (Inventory adjustment location)
      dispense → existing outgoing stock.picking.button_validate (unchanged)
      read     → stock.quant / stock.move
```

OpenMRS is not written for inventory. No local stock table.

### 9. Permissions

Separate privileges:

| Privilege / role | Purpose |
|---|---|
| `bahmni:clinical:dispense` + `Abikan:Pharmacy` | View catalogue, add/edit catalogue, view stock, dispense |
| `abikan:pharmacy:inventory` + `Abikan:Pharmacy Inventory` | Receive stock and adjust stock |

Development users `pharmacy.abikan` and `abikan.pharmacy` have **both** roles so inventory can be tested. Hospitals must not give every dispenser unrestricted receive/adjust access.

Pharmacists are **not** given OpenMRS Manage Concepts.

Accountant / Doctor / Nurse / Reception: receive and adjust **403**. Unauthenticated **401**.

### 10. Test stock movements

Controlled product: **Cetirizine 10 mg Tablet** (Odoo product **159**, uuid `7e0766e1-b679-4eb3-ab93-d63910ad6eb4`).

Dedicated TEST paracetamol (ORD-7) cannot be received or adjusted from this screen.

Live controlled sequence (21 Aug 2026), verified in Odoo `stock.quant` at WH/Stock:

| Step | Result |
|---|---|
| Start | 0 on hand |
| Receive 10 @ ₦300, supplier ABC Pharmacy Ltd, ref INV-123 | 10 on hand. Receipt cost ₦3,000. Incoming `WH/IN/00004`, `stock.move.price_unit` **300**. Selling `list_price` still **₦100**. No vendor bill. No new purchase order. |
| Adjust decrease 3, reason Correction, note TEST stock correction | 7 on hand |
| Adjust increase 5, same reason | **12** on hand |

Dispensing was **not** re-run in this phase (ORD-7 left PAID / READY TO DISPENSE). The existing confirm → reserve → pay (no stock drop) → dispense (stock drops) path was not changed.

### 11. Dispensing relationship

Unchanged:

Prescription → Sale/Order → Confirm (stock reserved) → Patient payment (stock still reserved) → Pharmacy dispense (stock decreases).

Payment does not reduce stock. Dispensing does.

### 12. Error handling

Refused: invalid product, zero/negative receipt, missing purchase price, missing adjustment reason, negative stock, decrease below reserved, unauthorized callers, TEST paracetamol inventory writes.

If Odoo rejects a movement, Hospital EMR shows the failure and does not pretend the shelf quantity changed.

### 13. Production considerations

- Replace development selling prices before go-live.
- Do not treat TEST receipts as production stock.
- Assign `Abikan:Pharmacy Inventory` only to staff authorized to receive and adjust.
- Physical counts should use Adjust Stock with reason **Physical stock count**.
- Supplier payment / procurement remains a later phase.
- Do not import spreadsheet Available Qty.

---

## PHARMACY DEVELOPMENT STATUS

**PHARMACY CATALOGUE MANAGEMENT + INVENTORY RECEIVE/ADJUST + TEST DISPENSING STOCK: COMPLETE FOR THIS PHASE**

THE HOSPITAL CATALOGUE IS THE BUSINESS SOURCE FOR WHICH MEDICINES THE HOSPITAL CARRIES.

INVENTORY IS HOW MUCH PHYSICAL STOCK EXISTS AND HOW IT CHANGES.

ODOO IS THE UNDERLYING INVENTORY/FINANCIAL SYSTEM.

ABIKAN IS THE HOSPITAL-FACING INTERFACE.

TEMPORARY PRICES ARE NOT PRODUCTION PRICES.

TEST STOCK IS NOT PRODUCTION STOCK.

SUPPLIER PAYMENT IS NOT PART OF THIS PHASE.
