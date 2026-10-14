# New drug / medication catalogue workflow

Status labels:

- **CONFIRMED** — verified from this installation’s OpenMRS REST / admin UI, MySQL, Odoo addons (`bahmni_api_feed.drug.data.service`, `restful_api` `/api/bahmni-drug`), odoo-connect `OpenERPDrugServiceEventWorker`, live atomfeed markers
- **UNKNOWN** — cannot currently be confirmed without a write
- **REQUIRES OPERATIONS CONFIGURATION** — later ops work; not done here
- **REQUIRES CONTROLLED TEST** — needs an approved write; **not executed**
- **ABIKAN FUTURE IMPLEMENTATION** — product work; not implemented in this task

This is investigation only. **Zero records were created or modified.** TEST and production drugs, prices, stock, P00001, S00001, ORD-1, ORD-2, OpenMRS, Atomfeed, Docker, and Hospital EMR source were not changed.

Related: `docs/PHARMACY_INTEGRATION_INVESTIGATION.md`, `docs/ODOO_PHARMACY_CONFIGURATION.md`, `docs/PHARMACY_PURCHASING_STOCK_INVESTIGATION.md`.

Date: **16 Aug 2026**.

Live catalogue (read-only):

| System | Count |
|---|---|
| OpenMRS `drug` retired=0 | **543** |
| Distinct OpenMRS concepts used by those drugs | **239** |
| Odoo `product.template` `type=product` (storable) | **543** |

That 1:1 storable-product count matches the OpenMRS drug catalogue. Many drugs share one concept (strength / form variants).

---

## Architecture (installed)

```
Hospital wants a new medication
        │
        ▼
OpenMRS concept  (class Drug, datatype N/A)
        │  reuse existing generic if it already exists
        ▼
OpenMRS drug     (conceptDrug.form or REST /drug)
        │  UUID assigned by OpenMRS (admin form has no UUID field)
        ▼
Atomfeed  GET /openmrs/ws/atomfeed/drug/recent
  content  /openmrs/ws/rest/v1/reference-data/drug/{uuid}
        │
        ▼
odoo-connect  OpenERPDrugServiceEventWorker
        │  POST /api/bahmni-drug   category=create.drug
        ▼
Odoo  drug.data.service.create_or_update_drug
        │  product.product.uuid = OpenMRS drug.uuid
        ▼
Odoo product (storable, purchase_ok, sale_ok, list_price 0.00 if new)
        │
        ├── Pricing / vendor / PO / receipt     (Odoo only)
        └── Doctor prescription                 (OpenMRS drug uuid)
                    │
                    ▼
              Atomfeed encounter → sale.order
              (maps product.product.uuid = drug.uuid)
```

**CONFIRMED:** this feed is live. Creating the four TEST OpenMRS drugs on 16 Aug 2026 wrote `event_records` category `drug`. Odoo marker `feed_uri=…/atomfeed/drug/recent` last entry is the Vitamin C TEST event `4457b325-…`. After that feed, Odoo TEST product 2385 has `drug=Acetaminophen` (OpenMRS `genericName`) and still `list_price=1000`.

The TEST catalogue was created **Odoo-first, then OpenMRS REST with a forced UUID**. That is a **test exception**. Production should **OpenMRS-first** so the feed creates the Odoo product.

---

## CONFIRMED

### 1. OpenMRS concept

Medication identity at terminology level is an OpenMRS **`concept`**.

| Item | Live |
|---|---|
| Model | `concept` + `concept_name` |
| Admin UI | `/openmrs/dictionary/concept.form` title **Creating New Concept** |
| Class for medicines | **Drug** uuid `8d490dfc-c2cc-11de-8d13-0010c6dffd0f` |
| Datatype for medicines | **N/A** uuid `8d4a4c94-c2cc-11de-8d13-0010c6dffd0f` (Acetaminophen live) |
| Required (form) | fully specified **name**, **conceptClass**, **datatype** |
| Optional | short name per locale (`shortNamesByLocale`), synonyms (extra names), description, `units` (numeric concepts; unused on Drug/N/A), set membership |
| Retire | concept `retired` flag (do not retire shared generics) |

Acetaminophen live names include synonyms (Mapap, Tylenol Extended Release, …). Those are **concept names**, not separate drugs.

**A new drug does not always need a new concept.** 543 drugs sit on 239 concepts. Paracetamol 500 mg and Paracetamol 500 mg — TEST both use Acetaminophen. Create a new concept only for a **new generic / molecule** that is not already in the dictionary.

### 2. OpenMRS drug

Prescribable product is OpenMRS **`drug`** (table `drug`). Doctors search and order **drugs**, not concepts.

| Field | Required? | Notes |
|---|---|---|
| `uuid` | yes in DB; **auto** in admin UI | unique `char(38)`. REST create **may** set it (TEST did). Admin form has **no uuid field** |
| `name` | yes (form) | what the doctor searches, e.g. `Paracetamol 500 mg` |
| `concept_id` | **yes** | generic / molecule |
| `dosage_form` | optional DB, expected in practice | concept, e.g. Tablet `1513A…` |
| `strength` | optional | string, e.g. `500 mg` |
| `combination` | default false | checkbox on form |
| `minimum_daily_dose` / `maximum_daily_dose` | optional | unused on live samples |
| `route` | optional | **NULL** on production Paracetamol / Amoxicillin |
| `dose_limit_units` | optional | unused |
| `retired` | default false | 0 retired drugs live |
| manufacturer | **not on OpenMRS drug** | Odoo `product.manufacturer` / PO line only |
| units | **not on the drug** | dose/qty units come from `bahmnicore/config/drugOrders` |

Admin create UI (**CONFIRMED** HTTP 200):

- List: `/openmrs/admin/concepts/conceptDrug.list`
- Form: `/openmrs/admin/concepts/conceptDrug.form`
- Fields: `name`, `concept`, `combination`, `dosageForm`, `strength`, `minimumDailyDose`, `maximumDailyDose`

Also:

- REST: `POST /openmrs/ws/rest/v1/drug` (used for TEST)
- Bahmni Admin CSV: entity **Drug**, `POST /openmrs/ws/rest/v1/bahmnicore/admin/upload/drug`

Bahmni Admin app (`admin.min.*.js`) is CSV / order set / beds — **not** the day-to-day single-drug form. There is **no** dedicated drug OWA on this server (`/openmrs/owa/index.html` = 404).

Authoritative records:

| Concern | Source |
|---|---|
| Terminology / generic | **Concept** |
| Prescribable product identity | **Drug** (uuid + name) |
| Strength as labelled | **Drug.strength** (string; not a concept) |
| Dosage form | **Drug.dosage_form** → form concept |
| What odoo-connect / sale orders key on | **Drug.uuid** |

### 3. Dosage forms

Stored as OpenMRS **concepts** referenced by `drug.dosage_form`. Live forms in use (retired=0 drugs):

Tablet 238, Injection 109, Oral solution 48, Powder for injection 32, Oral capsule 28, Drops 22, Solution 13, Inhalation powder 9, plus Cream, Ointment, Suppository, Gel, etc.

Odoo categories under `All / Saleable / Drugs / {form name}` were seeded from those names (Tablet id 18, Oral capsule id 21, …).

**Prescription units:** not stored on the drug. Live dose/dispensing units: Tablet, Capsule, ml, mg, IU, Drop, Tablespoon, Teaspoon, Unit, Puff. Bahmni `medication.json` `drugFormDefaults` keys **Tablet** and **Capsule** (not “Oral capsule”). ORD-1 used quantityUnits **Tablet** because form display is Tablet. Amoxicillin form **Oral capsule** does **not** auto-select Capsule.

**Dispensing / ERP:** feed sets Odoo `categ_id` from `dosageForm` **string**. OpenMRS unit name must still match `syncable.units.mapping` (today only **Tablet → Units**) or sale qty is forced to 0.

Do not create new dosage-form concepts unless a real form is missing.

### 4. UUID ownership

**CONFIRMED: OpenMRS owns the UUID. Odoo copies it.**

| Path | Who assigns uuid |
|---|---|
| Admin `conceptDrug.form` | OpenMRS generates (no uuid field) |
| REST `POST /drug` without uuid | OpenMRS generates |
| REST `POST /drug` **with** uuid | caller (TEST exception) |
| Odoo `drug.data.service` | **writes** `product.product.uuid = feed uuid` |
| Sale-order mapping | `product.product.uuid` **must equal** OpenMRS `drug.uuid` |

odoo-connect payload (`OpenMRSDrug` / `create.drug`): `uuid`, `name`, `shortName`, `genericName`, `dosageForm`, `strength`, `combination`, `maximumDose`, `minimumDose`.

`GET /openmrs/ws/rest/v1/reference-data/drug/{uuid}` (TEST Paracetamol):

```json
{
  "uuid": "1c88be47-…",
  "name": "Paracetamol 500 mg — TEST",
  "genericName": "Acetaminophen",
  "combination": false,
  "strength": "500 mg",
  "dosageForm": "Tablet",
  "shortName": null
}
```

### 5. Odoo product and automatic mapping

| Item | Value |
|---|---|
| Models | `product.product` (uuid unique) + `product.template` |
| Create path | Atomfeed → `POST /api/bahmni-drug` → `api.event.worker` category `create.drug` → `drug.data.service.create_or_update_drug` |
| Match | `product.product.uuid = vals["uuid"]` (includes archived, `active_test=False`) |
| If missing | `product.product.create` |
| If present | `write` (does **not** reset a non-zero `list_price`) |
| New `list_price` | **0.0** |
| `type` | `product` (storable) |
| `sale_ok` / `purchase_ok` | true |
| `drug` | OpenMRS genericName |
| `default_code` | shortName (often empty) |
| `categ_id` | category named like dosageForm |
| UoM | **not** in the feed; default Units (id 1) on this DB |
| tracking / expiry / company / vendor | **not** in the feed; tracking defaults `none` |
| Prices / cost | **not** in the feed except preserving existing `list_price` |

**Synchronization is automatic** for OpenMRS drug create/update, via the drug atomfeed (cron ~30s). It is **not** automatic in the other direction (Odoo → OpenMRS).

Creating an Odoo product by hand does **not** create an OpenMRS drug.

### 6. Pricing

**Pricing lives in Odoo only.** OpenMRS has no sale or purchase price on `drug`.

| Price | Where | When |
|---|---|---|
| Selling price | `product.template.list_price` (pricelist 1 has no items → uses list_price) | set in Odoo **after** the product exists; feed leaves new products at **0.00** |
| Purchase cost | PO `price_unit`; `standard_price` may be updated on PO confirm if `bahmni_purchase.update_product_prices_on_po_confirm=True` | at purchase |
| Vendor quote | `product.supplierinfo.price` | optional; created automatically on first PO confirm |
| Markup / MRP | `price.markup.table` (live **empty**); `mrp` fields | do not enable markup until sale prices are protected |
| TEST example | sale **1000**, cost **400** after P00001 | do not change |

Hospital real workflow: set **sale price in Odoo** after sync; set **purchase price on the PO** (and optionally vendor pricelist). Do not put tariffs in OpenMRS.

### 7. Supplier

**Not required to prescribe.** OpenMRS does not know suppliers.

Supplier is required only to **purchase** (`purchase.order.partner_id`, `supplier_rank > 0`). Optional `product.supplierinfo` before the first PO; confirm will add one.

### 8. Inventory

**Stock is not required to prescribe.** ORD-1 and ORD-2 exist with production Paracetamol 110 still at **0** on-hand. OpenMRS drug search does not check Odoo quants.

Stock **is** required to **confirm** the Odoo sale / deliver / invoice without negative stock (`allow_negative_stock=0`).

Order: catalogue → (optional) prescribe → purchase → receive → dispense.

### 9. Retiring a drug

| System | Action | Effect |
|---|---|---|
| OpenMRS | `drug.retired=true` | drops out of default `GET /drug?q=` search; existing `orders` stay readable |
| Odoo | archive product `active=false` and/or `sale_ok=false` | stops new POs/sales if used correctly |

**CONFIRMED gap:** `OpenMRSDrug` / `_fill_drug_object` do **not** send or apply `retired`. Retiring OpenMRS does **not** archive Odoo. Do **both**. Do not retire a shared **concept** just to stop one strength.

Existing prescriptions: ORD-1/ORD-2 keep `drug_inventory_id`; retiring the drug does not delete them.

### 10. Editing after use

| Field | After prescribed / purchased | Risk |
|---|---|---|
| OpenMRS `uuid` / Odoo `product.product.uuid` | **Never change** | breaks mapping and historical sale lines |
| Concept | dangerous if already prescribed | changes generic identity |
| Name | possible; keep searchable and distinct | feed will overwrite Odoo `name` |
| Strength / dosage form | avoid after live Rx | clinical mismatch; feed may move Odoo category |
| Sale `list_price` | **safe** in Odoo (TEST 1000 survived feed update) | do not let markup rewrite on PO confirm |
| `standard_price` / PO price | Odoo only | OK |
| UoM | dangerous after quants | qty conversion / mapping mismatch |
| `tracking` | enable **only** while qty=0 | Odoo often forbids lot tracking once untracked quants exist |
| `purchase_ok` / `sale_ok` | OK | operational flags |

---

## UNKNOWN

1. Exact Bahmni CSV Drug file columns on this `bahmnicore` version (endpoint exists; no sample file on disk).
2. Whether feed **updates** of a retired OpenMRS drug can be used to archive Odoo if payload is extended later (today it cannot).
3. Whether a brand-new dosage-form string creates a messy extra Odoo category (code will `create` under Drugs if the name is missing).
4. Time-to-visible in Odoo after OpenMRS save (cron 30s typical; not re-measured this task).
5. Whether OpenMRS concept UUID should be copied anywhere in Odoo (it is **not**; only drug uuid is).

---

## REQUIRES OPERATIONS CONFIGURATION

Not done here.

1. For a **new generic**, create the Drug/N/A concept before the drug.
2. After feed: set Odoo `list_price` (do not leave 0.00 as a tariff).
3. Add `syncable.units.mapping` for any OpenMRS unit the new drug will use beyond **Tablet**.
4. Optional vendor + first PO/receipt before dispensing.
5. Keep `price.markup.table` empty (or turn off `update_product_prices_on_po_confirm`) until sale prices are intentionally managed.
6. Do not install `bahmni_initializer` as a way to add drugs (wrong shop/unit seeds).

---

## REQUIRES CONTROLLED TEST

Not executed. Suggested later (separate approval):

1. Create a throwaway OpenMRS concept + drug **without** pre-creating Odoo (true production path).
2. Wait for drug atomfeed.
3. Confirm a **new** `product.product` appears with the **same uuid**, `list_price=0`, category from dosage form.
4. Set a TEST sale price in Odoo.
5. Search the drug in `GET /drug?q=`.
6. Do not prescribe into production patients until that path is proven.
7. Rollback: retire OpenMRS drug, archive Odoo product.

Do **not** use another Odoo-first UUID injection for production.

---

## ABIKAN FUTURE IMPLEMENTATION

Recommended **Pharmacy → Drug Catalogue** (backend-orchestrated):

| Action | How |
|---|---|
| Search / view | OpenMRS `GET /drug?q=` + Odoo stock/price via **server-side** read by uuid |
| Add drug | Backend: optional concept create, then `POST /drug`; poll Odoo product by uuid; then Odoo write `list_price` |
| Edit allowed fields | Name/strength via OpenMRS REST (feed updates Odoo name); prices via Odoo server-side |
| Retire | OpenMRS retire **and** Odoo archive in one backend operation |
| Supplier / purchase / stock / history | **Remain in Odoo**; Hospital EMR may **display** them |
| Prescribe | Remain OpenMRS / Doctor UI |

**Do not** write Odoo from browser JavaScript. **Do not** put Odoo passwords in frontend code. Use a server session (not `emrsync` in the browser).

Leave in **OpenMRS:** concepts, drugs, prescriptions, dosage forms, clinical units.

Leave in **Odoo:** products (once synced), prices, vendors, POs, receipts, quants, lots, patient invoices.

---

## Risks

1. **Odoo-first products** with a random uuid will **not** match a later OpenMRS-generated uuid. Sale orders will miss the product.
2. Feed **overwrites Odoo name / generic / category** on every OpenMRS drug update. Do not use Odoo name as an independent clinical label.
3. New products arrive at **list_price 0.00** — same trap as production Paracetamol 110.
4. Retire-in-OpenMRS-only leaves an Odoo product still `sale_ok`.
5. New OpenMRS unit names without `syncable.units.mapping` → draft sale qty 0.
6. Changing uuid after P00001 / S00001-style documents exist is unrecoverable without data repair.
7. Enabling lots after WH/Stock already has untracked qty is likely blocked.
8. CSV bulk upload can create many drugs at once and flood the drug feed — use only with a review process.

---

## Exact production procedure

**Safest path for a completely new medication** (do not run in this task):

1. **Search** OpenMRS concepts for the generic (e.g. Acetaminophen). Reuse if present.
2. If missing: **Dictionary → Creating New Concept**  
   - Fully specified name  
   - Class **Drug**  
   - Datatype **N/A**  
   - Optional synonyms / short name  
   - Do not invent CIEL uuids.
3. **Administration → Dictionary → Concept Drug** (`conceptDrug.form`)  
   - Name including strength (what doctors will type)  
   - Concept = generic  
   - Dosage form = existing form (Tablet, Oral capsule, …)  
   - Strength string  
   - Combination as appropriate  
   - Save and **let OpenMRS assign uuid**.
4. Wait for **drug atomfeed** (odoo-connect). Verify Odoo `product.product.uuid` **equals** the new `drug.uuid`, type storable, `purchase_ok`/`sale_ok`.
5. In **Odoo**, set **sale `list_price`**. Do not change company currency or pricelist 1 globally.
6. Optional: vendor + RFQ/PO + receipt into **WH/Stock id 8** (see purchasing investigation).
7. If the drug will be prescribed with a unit other than Tablet, add `syncable.units.mapping` **before** the first prescription you care about billing qty for.
8. Doctors may prescribe as soon as the OpenMRS drug exists (even at 0 stock). Pharmacy should not confirm the sale until stock exists.
9. To stop use: retire the **drug** in OpenMRS **and** archive the Odoo product. Leave the concept if other strengths remain.

**Do not** (production): create the Odoo product first; invent uuids; edit uuid; confirm S00001 as a catalogue test; change TEST prices; modify existing production drugs.
