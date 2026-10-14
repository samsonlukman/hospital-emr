# Pharmacy integration investigation

Status labels:

- **CONFIRMED** — verified from installed source, live REST, MySQL, PostgreSQL, or container logs on this server
- **UNKNOWN** — cannot currently be confirmed
- **COMING SOON** — Hospital EMR behaviour that does not exist yet (do not treat as backend truth)

This is an investigation record. It does not implement dispensing, change the Pharmacy UI, seed stock, create invoices, or change Docker / OpenMRS / Odoo configuration.

Related: `docs/CLINICAL_WRITE_API.md`, `docs/PHARMACY_WORKFLOW.md`.

Date of live verification: **16 Aug 2026**.

---

## Status summary

| Area | Result |
|---|---|
| Doctor write path | **CONFIRMED** `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `drugOrders[]` |
| OpenMRS storage | **CONFIRMED** `orders` + `drug_order`. Live row **ORD-1** |
| Atomfeed | **CONFIRMED** encounter feed entry → odoo-connect marker advanced |
| odoo-connect transform | **CONFIRMED** `OpenERPSaleOrderEventWorker` → `POST /api/bahmni-saleorder` category `create.sale.order` |
| Odoo sale order created | **CONFIRMED no.** Log: `Order Type - Drug Order is not defined. Ignoring Drug Order` |
| Stock / invoice / picking | **CONFIRMED** still 0 after the prescription |
| Hospital EMR Pharmacy GET used today | **CONFIRMED** `GET /bahmnicore/drugOrders?patientUuid=` returns `[]` even for ORD-1 |
| Working OpenMRS read | **CONFIRMED** `GET /bahmnicore/drugOrders/active?patientUuid=` returns ORD-1 |
| Unified OpenMRS↔Odoo login | **CONFIRMED none** |

---

## Architecture (this installation)

```
Doctor / Bahmni Clinical / Hospital EMR consultation save
        │
        ▼
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
  drugOrders[]
        │
        ▼
OpenMRS  orders + drug_order     (clinical source of truth)
        │
        ▼
Atom feed  GET /openmrs/ws/atomfeed/encounter/recent
  category Encounter
  content  /openmrs/ws/rest/v1/bahmnicore/bahmniencounter/{uuid}?includeAll=true
        │
        ▼
odoo-connect  OpenERPSaleOrderEventWorker  (cron ~every 30s)
  GET encounter JSON
  GET visit JSON
  MapERPOrders → parameters { category: create.sale.order, customer_id: MRN, orders: { openERPOrders: [...] } }
        │
        ▼
Odoo 16  POST /api/bahmni-saleorder   (restful_api, auth=user, session of emrsync)
  api.event.worker.process_event
  order.save.service.create_orders
        │
        ├── if order.type name matches  → sale.order (draft, origin API FEED SYNC)
        │                                 + sale.order.line (external_order_id = OpenMRS order uuid)
        └── THIS SERVER: order.type empty → WARNING, ignore, HTTP 200, marker consumed
                                             NO sale.order, NO retry
        │
        ▼
Odoo operational engine (intended, not live for this Rx)
  Sales quotations / POS / stock.picking / account.move
        │
        ▼
Hospital EMR Pharmacy  (pharmacist UI — OpenMRS reads today; Odoo reads not wired)
```

---

## CONFIRMED

### 1. Prescription creation flow

Bahmni Clinical `$scope.save()` → `EncounterTransactionMapper.map` → `encounterService.create` → **POST** `Bahmni.Common.Constants.bahmniEncounterUrl`.

Installed JS: `/usr/local/apache2/htdocs/bahmni/clinical/clinical.min.317054d3.js`

Drug-order object builder: `Bahmni.Clinical.DrugOrder.createFromUIObject`.

OpenMRS pre-save: `DrugOrderSaveCommandImpl` (`EncounterDataPreSaveCommand`) in `bahmnicore`. Overlapping active orders of the same drug raise `[Order.cannot.have.more.than.one]`.

Persistence: OpenMRS `orders` (type **Drug Order** uuid `131168f4-15f5-102d-96e4-000c29c2a5d7`) + `drug_order`.

An open visit is required (`allowConsultationWhenNoOpenVisit` is false). Live test used existing OPD visit `f1444134-45f3-4377-8c2a-e6831bf7b910` at **OPD-1**.

### 2. Exact OpenMRS / Bahmni API

| Role | Method | Path | Notes |
|---|---|---|---|
| **Write prescription** | **POST** | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` | Same EncounterTransaction as vitals/diagnoses. Controller path is Bahmni encounter, not `/order` |
| Pre-save | Java | `DrugOrderSaveCommandImpl.update` | Overlap / chain dates |
| Config | GET | `/openmrs/ws/rest/v1/bahmnicore/config/drugOrders` | HTTP 200 |
| Active orders | GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/active?patientUuid=` | **Returns ORD-1** |
| Prescribed list | GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders?patientUuid=` | **Returns `[]` for ORD-1** unless additional filters match Bahmni’s visit-window logic. Do not use this as the pharmacy queue |
| By id | GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/{orderUuid}` | Returns BahmniDrugOrder wrapper |
| Core REST | GET | `/openmrs/ws/rest/v1/order?patient=&t=drugorder&v=full` | Returns ORD-1 |
| Encounter (what Atomfeed fetches) | GET | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter/{uuid}?includeAll=true` | Includes `patientId` (MRN), `drugOrders[]` |
| Drug search | GET | `/openmrs/ws/rest/v1/drug?q=` | Catalogue 539 |
| Visit-wise | GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive?patientUuid=` | Returns `{ visitDrugOrders: ... }` |

Controller: `org.bahmni.module.bahmnicore.web.v1_0.controller.BahmniDrugOrderController`.

Service: `BahmniDrugOrderService` / `BahmniDrugOrderServiceImpl`.

Contract: `org.openmrs.module.bahmniemrapi.drugorder.contract.BahmniDrugOrder`.

There is **no hospital-wide prescription queue** on OpenMRS REST. Pharmacy must iterate patients or use another index. Same limitation as Laboratory / Radiology.

### 3. Drug-order payload structure

Live config names on this server (not the older `Tablet(s)` / `Day(s)` examples):

| Config key | Count | Values used in the live order |
|---|---|---|
| doseUnits / dispensingUnits | 10 | **Tablet** |
| routes | 15 | **Oral** |
| frequencies | 23 | **Twice a day** |
| durationUnits | 8 | **Days** |
| dosingInstructions | 8 | **As directed** |
| orderAttributes | 1 | **Dispensed** (not set on ORD-1) |

`dosingInstructionType` (from Bahmni JS constant `flexibleDosingInstructionsClass`):

`org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions`

Write payload shape actually stored on ORD-1:

```json
{
  "patientUuid": "<patient-uuid>",
  "visitUuid": "<open-visit-uuid>",
  "visitType": "OPD",
  "encounterTypeUuid": "d34fe3ab-5e07-11ef-8f7c-0242ac120002",
  "encounterDateTime": "YYYY-MM-DDTHH:mm:ss.SSS+0000",
  "locationUuid": "<session location, e.g. OPD-1>",
  "providers": [{ "uuid": "<provider-uuid>" }],
  "observations": [],
  "bahmniDiagnoses": [],
  "orders": [],
  "drugOrders": [
    {
      "careSetting": "OUTPATIENT",
      "drug": { "uuid": "<openmrs drug uuid>" },
      "orderType": "Drug Order",
      "dosingInstructionType": "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions",
      "dosingInstructions": {
        "dose": 1,
        "doseUnits": "Tablet",
        "route": "Oral",
        "frequency": "Twice a day",
        "asNeeded": false,
        "administrationInstructions": "{\"instructions\":\"As directed\"}",
        "quantity": 10,
        "quantityUnits": "Tablet",
        "numberOfRefills": 0
      },
      "duration": 5,
      "durationUnits": "Days"
    }
  ]
}
```

`administrationInstructions` is `JSON.stringify({ instructions, additionalInstructions })` from `createFromUIObject`. If `quantityUnits` is omitted, Bahmni JS defaults to `"Unit(s)"`.

Care setting: OpenMRS `Outpatient` uuid `6f0c9a92-6f24-11e3-af88-005056821db0` (payload string `OUTPATIENT`).

Orderer: encounter `providers[]`. Stored provider on ORD-1: `42ac4f6a-d3f9-4e59-ad9a-2c947e95d31b` (Hospital EMR Development Admin).

Start / stop: `date_activated` / `scheduledDate` / `auto_expire_date` (duration 5 Days → expire ~5 days later). `date_stopped` null. `order_action` **NEW**. `fulfiller_status` **NULL**. `urgency` **ON_SCHEDULED_DATE**.

Order attributes: concept **Dispensed** exists in drug-order config. Table `order_attribute` has **0** rows. Dispensed is **not** required to create a prescription.

Lifecycle observed:

| State | How it appears |
|---|---|
| Ordered / active | `date_stopped` null, `auto_expire_date` in the future, `action` NEW |
| Stopped / discontinue | `action` DISCONTINUE or `date_stopped` set (Odoo then unlinks draft sale lines) |
| Revised | `action` REVISE + `previousOrderUuid` (Odoo updates draft line) |
| Dispensed (chart flag) | order attribute Dispensed = true → Atomfeed re-emits; Odoo sets `sale.order.line.dispensed` |
| Expired | `auto_expire_date` passed — **not live-tested** |

### 4. Atomfeed event flow

Producer: OpenMRS Atomfeed module (`Patient AOP` feed title on encounter/recent).

| Job enum | Feed URI (this server) | Worker |
|---|---|---|
| SALEORDER_FEED | `http://openmrs:8080/openmrs/ws/atomfeed/encounter/recent` | `OpenERPSaleOrderEventWorker` |
| CUSTOMER_FEED | `…/atomfeed/patient/recent` | `OpenERPCustomerServiceEventWorker` |
| DRUG_FEED | `…/atomfeed/drug/recent` | `OpenERPDrugServiceEventWorker` |
| SALEABLE_FEED | `…/atomfeed/saleable/recent` | `OpenERPSaleableResourceWorker` |
| LAB_TEST / LAB_PANEL / RADIOLOGY | `…/atomfeed/lab/recent` | lab/radiology workers |
| OPENELIS_SALEORDER_FEED | OpenELIS patient feed | `OpenElisSaleOrderEventWorker` |

Encounter entry (live for ORD-1):

- title: `Encounter`
- category term: `Encounter`
- id: `tag:atomfeed.ict4h.org:c03ea525-1073-4723-926f-caf55433b7a1`
- content: `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter/5cf62360-4b05-4a1e-b42e-4fc1bba91138?includeAll=true`

Consumer: container `bahmni-standard-odoo-connect-1`, image `bahmni/odoo-connect:1.0.0`.

Scheduler: `scheduler.sale.order.cron.expression` default `0/30 * * * * ?` (every 30 seconds). Initial delay 60s.

Markers table (Odoo Postgres) is the atomfeed-client cursor. After ORD-1, encounter marker **was** `c03ea525-1073-4723-926f-caf55433b7a1`.

`drugorder.uri` = `http://openmrs:8080/openmrs/ws/rest/v1/bahmnicore/drugOrders` — used by `MapERPOrders.fetchPreviousDrugOrder` on REVISE, not for the initial create.

Retry / failure:

- Worker `process()` wraps failures in `RuntimeException`. Atomfeed-client writes `failed_events` and retries on the failed-events Quartz job (`openerpSaleOrderFeedQuartzFailedJob`).
- `openerp.maxFailedEvents=1000`.
- Existing 97 `failed_events` are **lab catalogue** `ResponseCookie.getValue()` NPEs from 12 Aug 2026, not this prescription.
- When Odoo is unreachable: connect job logs `AtomFeedClientException` / timeout (seen historically on 12 Aug). Event is not marked consumed until success.
- **Silent drop (live):** Odoo returned HTTP **200** for `/api/bahmni-saleorder` while ignoring the Drug Order. Marker advanced. **No `failed_events` row. No retry.**

`shouldERPConsumeEvent()` is true if the encounter has `drugOrders` **or** `orders` (lab/radiology/procedure also go through the same sale-order worker).

### 5. odoo-connect transformation

Class: `org.bahmni.feed.openerp.domain.encounter.MapERPOrders`.

RPC: resource `atom.event.worker`, operation `process_event`. On Odoo 16 this is REST:

1. Login `POST /web/session/authenticate` as configured `openerp.user` (**emrsync**).
2. `POST http://odoo:8069/api/bahmni-saleorder` with JSON parameters.

Parameters:

| Key | Source |
|---|---|
| `category` | `create.sale.order` |
| `customer_id` | encounter `patientId` = **MRN** (`ABC200012`), not UUID |
| `encounter_id` | encounter UUID |
| `locationName` | encounter location display (`OPD-1`) |
| `orders` | JSON `{ id, openERPOrders: [ OpenERPOrder, ... ] }` |
| `feed_uri` / `last_read_entry_id` / `feed_uri_for_last_read_entry` | atomfeed cursor |

Each `OpenERPOrder`:

| Field | Mapping |
|---|---|
| `orderId` | OpenMRS drug order uuid |
| `previousOrderId` | `previousOrderUuid` |
| `encounterId` | encounter uuid |
| `productId` | OpenMRS **drug** uuid |
| `productName` | drug name |
| `quantity` / `quantityUnits` | dosingInstructions |
| `action` | NEW / REVISE / DISCONTINUE |
| `type` | orderType string **Drug Order** |
| `visitType` | from visit attribute `Visit Status` (OPD/IPD) |
| `providerName` | first encounter provider |
| `dispensed` | `"true"` if an observation concept named Dispensed is true, else `"false"` |
| `conceptName` | drug concept name (Acetaminophen) |
| `voided` | order voided |
| `dateCreated` | dateActivated |

Odoo `api.event.worker.process_event` dispatches:

| category | handler |
|---|---|
| `create.sale.order` | `order.save.service.create_orders` |
| `create.customer` | partner upsert on `res.partner.ref` |
| `create.drug` | `drug.data.service.create_or_update_drug` |
| lab/radiology/saleable | `reference.data.service` |

### 6. Odoo models / records created (intended vs live)

`order.save.service.create_orders` **CONFIRMED** behaviour from installed Python `/opt/bahmni-erp/bahmni-addons/bahmni_api_feed/models/order_save_service.py`:

1. Find `res.partner` where `ref == customer_id` (MRN). Missing partner → `UserError("Patient Id not found in Odoo")` → would fail the event. **John Adewale exists** (`ref=ABC200012`, `uuid` = OpenMRS patient uuid).
2. Group by `order['type']`. Look up `order.type` by **name**. If missing → **warning and `continue`**. **This is what happened.**
3. Else resolve `sale.shop` via `order.type.shop.map` (order type + `location_name`), else first shop.
4. Split dispensed vs non-dispensed.
5. Non-dispensed: find draft `sale.order` for that partner + shop + `origin='API FEED SYNC'`, or create one.
6. Create/update `sale.order.line` with `external_order_id` = OpenMRS order uuid, `external_id` = encounter uuid, `dispensed` flag, `product_id` matched by **`product.product.uuid` == OpenMRS drug uuid**.
7. Quantity: if no `syncable.units.mapping` for `quantityUnits`, quantity is forced to **0**. This server has **0** syncable unit rows.
8. Lots: `get_available_batch_details` reads `stock.quant` at the shop location. **0 quants** → line created without `lot_id` (or qty 0).
9. Dispensed path may call `sale.order.auto_validate_delivery()` and `validate_payment()` if `convert_dispensed` / `auto_register_invoice_payment_for_dispensed` are on. `convert_dispensed` is read from **`ir.values`**, a table that **does not exist** on this Odoo 16 database. `auto_register_invoice_payment_for_dispensed` config value is **0**.

Intended records (not created for ORD-1):

| Model | When | Key fields |
|---|---|---|
| `sale.order` | first non-dispensed line for shop | `partner_id`, `shop_id` (required), `origin=API FEED SYNC`, `state=draft`, `care_setting` opd/ipd, `provider_name`, `location_id`, `warehouse_id`, `partner_uuid` (computed), `pricelist_id` |
| `sale.order.line` | each OpenMRS order | `product_id`, `product_uom_qty`, `price_unit` (list_price / pricelist / lot sale_price), `external_order_id`, `external_id`, `dispensed`, `lot_id`, `expiry_date` |
| `stock.picking` / `stock.move` | only after order confirm / `auto_validate_delivery` | standard Odoo delivery |
| `account.move` | `_create_invoices` if `bahmni_sale.is_invoice_automated` | customer invoice |
| `account.payment` | `validate_payment` on dispensed auto-invoice | cash journal |
| Pharmacy-specific ledger | **none** | no separate dispensing model; `sale.order.line.dispensed` is the flag |

Live counts after ORD-1 (unchanged from empty operational tables):

| Table | Count |
|---|---|
| `sale_order` / `sale_order_line` | 0 |
| `account_move` | 0 |
| `stock_quant` / `stock_lot` / `stock_picking` / `stock_move` | 0 |
| `pos_order` | 0 |
| `order_type` | **0** |
| `sale_shop` | **0** |
| `order_type_shop_map` | **0** |
| `syncable_units_mapping` | **0** |
| `bahmni_initializer` module | **uninstalled** |

Seed XML that was **never loaded** (`bahmni_initializer/data/`):

- `sale.shop` name **Pharmacy**, warehouse 1, location 8 (`WH/Stock`)
- `order.type` names **Drug Order**, **Lab Order**, **Radiology Order**
- mappings with `location_name` **General Ward** only (not OPD-1)

Even after that seed, an OPD-1 prescription would not match `location_name=General Ward` and would fall back to “first shop”.

Product match for the test drug **does** exist: `product.product` id 110, `uuid=e8265115-66d3-459c-852e-b9963b2e38eb`, `list_price=0.00`, `drug=Acetaminophen`, UoM Units. `product.template.uuid` is empty; matching uses **`product.product.uuid`** (2381 of 2384 filled).

### 7. Stock model

| Concept | This server |
|---|---|
| Drug products | 539 `product.template` `type=product` (matches OpenMRS drug count) |
| Services | 1843 `type=service` |
| Variants | `product.product` 2384 rows; uuid on variant |
| SKU / code | `default_code` from OpenMRS shortName (often empty on sample drugs) |
| Generic name | `product.template.drug` |
| On hand | `stock.quant.quantity` — **0 rows** |
| Reserved / free | `product.product.free_qty` (Bahmni field) — no quants |
| Lots / expiry | `stock.lot` + `expiration_date` — **0 lots** |
| Warehouse | 1: **My Company** / code **WH** |
| Locations | 16 standard; internal stock = `WH/Stock` id **8** |
| Reorder | `stock_warehouse_orderpoint` — **0** |
| UoM | `uom.uom` id 1 **Units** on the Paracetamol product |
| Negative stock | `allow_negative_stock` = 0 |

Do not label Hospital EMR stock Low / Out of Stock from OpenMRS quantity. OpenMRS `drug_order.quantity` is prescribed amount, not on-hand.

### 8. Billing model

| Piece | This server |
|---|---|
| Price source | `product.template.list_price` (0.00 on Paracetamol 500 mg); optional lot `sale_price` if `bahmni_sale.sale_price_markup` True (**it is True**) |
| Pricelist | `sale.order.pricelist_id` from partner or shop |
| Sale order | draft quotation, origin `API FEED SYNC` — **0 live** |
| Invoice | `account.move` via `_create_invoices`; `bahmni_sale.is_invoice_automated` = True — **0 live** |
| Payment | `account.payment`; `bahmni_auto_payment_reconciliation.enabled` = True — **0 live** |
| Patient account | `res.partner` + `account.move.amount_residual_signed` as outstanding (`sale.order._total_receivable`) |
| Discount | `sale.order.discount_type` none/fixed/percentage, `disc_acc_id` |
| Receipt | standard Odoo invoice/payment print — **0 live** |
| POS | module installed; `pos_config` name **Shop**; `pos_order` **0** |
| Insurance / NHIA | **no** matches in installed `bahmni_*` addons |

`auto_validate_delivery` / `validate_delivery` still call Odoo **10** APIs (`pack_operation_product_ids`, `stock.production.lot`, `do_new_transfer`). On Odoo 16 this path is **not trustworthy** even after shops are seeded.

### 9. Existing Odoo pharmacy UI

Landing `http://localhost:8069/` (or `erp-` host via proxy) opens Odoo **Discuss**. That is the default Odoo 16 home (`mail`), **not** a pharmacy workflow.

There is **no** “Pharmacy” application. Operational menus that exist:

| Top menu | Useful children | Action |
|---|---|---|
| **Sales** | Quotations | `sale.action_quotations_with_onboarding` id 435 → `/web#action=435&model=sale.order` |
| Sales | Orders | `sale.action_orders` id 434 |
| Sales | Orders to Invoice | id 437 |
| **Inventory** | Transfers, Products, Stock, Adjustments | `stock.action_picking_tree_all` id 327 |
| **Invoicing** | Customer Invoices | `account.action_move_out_invoice_type` id 244 |
| **Point of Sale** | Dashboard / Shop | `point_of_sale.action_pos_config_kanban` id 413 |
| **Purchase** | Purchase Orders | id 384 |
| **Bahmni → Bahmni Masters** | Shop, Order Type, Order Type–Shop mapping, Syncable Units, Event Records | ids 452, 460, 462, … |

Can a pharmacist process this prescription in Odoo today? **No.** The feed arrived and was ignored. There is no quotation to confirm, no stock to deliver, no invoice.

Dispensing in the installed design is: pharmacist work on the **draft sale order** (and/or POS), then optionally set OpenMRS **Dispensed** so a later encounter event marks lines dispensed and may auto-confirm. That loop is not operational here.

### 10. Authentication boundaries

| System | Session |
|---|---|
| Hospital EMR / Bahmni Clinical | OpenMRS `JSESSIONID` / REST session. User `abikan.admin` **cannot** be assumed to be an Odoo user |
| Odoo UI | Separate cookie after `/web/login`. Users: `admin`, `emrsync` |
| odoo-connect | Service login as **emrsync** via `/web/session/authenticate`, then `auth="user"` JSON routes under `/api/bahmni-*` |
| `restful_api` | Installed. Routes are **write** feeds from connect, not a general read API for Hospital EMR. `auth="user"` — requires an Odoo session |

**CONFIRMED: no SSO** and no shared session between OpenMRS and Odoo.

Hospital EMR must **never** put Odoo credentials in frontend code. A future unified pharmacy experience needs a **server-side** service account (or a new backend proxy) that reads Odoo with `emrsync`/equivalent and returns stock/billing DTOs to the browser under the OpenMRS session.

### 11. Controlled test results

**Patient:** John Adewale, UUID `cbb26c0f-06bb-4252-aed9-fb461f0e9c15`, MRN `ABC200012`.  
**Visit:** open OPD `f1444134-45f3-4377-8c2a-e6831bf7b910` at OPD-1 `5e232c47-8ff5-4c5c-8057-7e39a64fefa5`.  
**Drug:** Paracetamol 500 mg, OpenMRS/Odoo uuid `e8265115-66d3-459c-852e-b9963b2e38eb` (harmless, already in both catalogues).  
**No stock, invoices, or Dispensed flag were created.**

Baseline immediately before the duplicate POST (16 Aug 2026 20:02 UTC): OpenMRS already had **1** `orders` / **1** `drug_order`; Odoo `sale_order=0`, `failed_events=97`.

Live prescription **ORD-1** (created 16 Aug 2026 19:59:40 UTC by `abikan.admin`, real Bahmni encounter path):

| Field | Value |
|---|---|
| Order uuid | `e7eb086a-ce26-42d2-87ba-0c17f22e3a1b` |
| Encounter | `5cf62360-4b05-4a1e-b42e-4fc1bba91138` Consultation |
| Dose | 1 Tablet, Oral, Twice a day × 5 Days, qty 10 Tablet |
| Instructions | As directed |
| Dispensed attribute | none |
| `GET …/drugOrders?patientUuid=` | `[]` |
| `GET …/drugOrders/active?patientUuid=` | ORD-1 |
| Atomfeed | entry `c03ea525-…` at 19:59:42Z |
| odoo-connect marker | advanced to that entry |
| Odoo 20:00:04Z | `POST /api/bahmni-saleorder` **200** |
| Odoo log | `Processing 1 orders from encounter(5cf62360-…) for customer ABC200012` |
| Odoo log | `Order Type - Drug Order is not defined. Ignoring Drug Order for Customer John Adewale [ABC200012]` |
| `sale_order` after | **0** |
| New `failed_events` | **none** |

A second identical `POST bahmniencounter` at 20:02:04 UTC returned **HTTP 400** `[Order.cannot.have.more.than.one]`. **No second prescription was created.**

---

## UNKNOWN

- Whether Bahmni Clinical UI would show ORD-1 on the Treatment tab (not opened in this task).
- Exact `GET /drugOrders?patientUuid=` visit-window parameters that would return ORD-1 (numberOfVisits 1 and 10 still returned `[]`; `/active` works).
- Whether POS “Shop” is intended as the outpatient pharmacy counter vs Sales quotations — **0** POS orders, no live evidence.
- Whether `bahmni_sale.is_delivery_automated` actually moves stock on Odoo 16 confirm (delivery helper still uses Odoo 10 stock APIs).
- Partial dispense / quantity handed over as a first-class field (not in `drug_order`; would be Odoo line qty).
- Insurance / NHIA billing on this stack (no addon evidence).
- Whether `abikan.admin` can log into Odoo (separate user table; not tested; do not assume).
- Behaviour if Odoo is down **during** this exact prescription (historical timeouts exist; not reproduced).

---

## COMING SOON

- Hospital EMR pharmacist queue that actually lists ORD-1 (current client calls the GET that returns `[]`).
- Hospital-wide queue (no OpenMRS API).
- Stock availability, batch/expiry, reorder warnings in Hospital EMR.
- Dispensing writes (OpenMRS Dispensed attribute and/or Odoo confirm).
- Billing / payment UI in Hospital EMR.
- SSO / unified session.
- Reports.

Do not implement those in this investigation.

---

## Recommended Hospital EMR architecture

**D — combination**, grounded in this installation:

| Concern | Source | How Hospital EMR should talk to it |
|---|---|---|
| Create / revise / stop prescription | **OpenMRS only** | `POST bahmniencounter` `drugOrders[]` (Doctor workspace). Never create `sale.order` from the browser |
| Prescription queue / chart | **OpenMRS** | `GET /bahmnicore/drugOrders/active?patientUuid=` (and/or `/order?t=drugorder`). Do **not** rely on `GET /drugOrders?patientUuid=` alone |
| Patient identity | **OpenMRS** (partner already synced to Odoo `res.partner.ref`) | Existing clinical session |
| Stock, lots, expiry, warehouse | **Odoo** | Future **server-side** read (service user). Not the Hospital EMR SPA |
| Price, quotation, invoice, payment | **Odoo** | Same server-side read; writes stay on Odoo confirm/payment or a later carefully designed proxy |
| Dispense | **OpenMRS Dispensed attribute** (re-triggers Atomfeed) **and/or** Odoo sale confirm | Only after `order.type` + `sale.shop` exist. Do not invent a third ledger |

Reject:

- **A** (OpenMRS only) — no on-hand qty, price, or invoice in OpenMRS.
- **B** (read OpenMRS + Odoo, write nowhere) — fine for a read-only increment, not for dispensing.
- **C** (write OpenMRS, ignore Odoo reads) — pharmacist would never see stock or billing; and today Odoo does not even create the sale order.

Keep Odoo as the operational engine. The pharmacist should see Hospital EMR Pharmacy, not Discuss / Sales / Inventory. That requires a backend façade, not embedding Odoo in the SPA.

---

## Risks

1. **Masters missing:** `bahmni_initializer` uninstalled → empty `order.type` / `sale.shop`. Feeds succeed and **drop** prescriptions. Easy to miss: HTTP 200, marker moves, empty Sales.
2. **Hospital EMR read bug:** Pharmacy service uses `GET /bahmnicore/drugOrders?patientUuid=`, which returned `[]` for the live order. The UI will look empty even when ORD-1 exists.
3. **No hospital-wide queue** — same as lab/radiology.
4. **Zero stock and zero prices** — a future sale line would be qty 0 (no unit mapping) and price 0.00.
5. **Silent 200** is worse than a failed event; operations will not see retries.
6. **Odoo 10 leftovers** in `auto_validate_delivery` / `ir.values` / `convert_dispensed` — auto-dispense/invoice from the Dispensed flag is not proven on Odoo 16.
7. **Two logins** — leaking `emrsync` to the browser would expose ERP write APIs (`/api/bahmni-saleorder` and siblings).
8. **Shop mapping location names** in seed XML are **General Ward**, while this prescription was from **OPD-1**.
9. Overlap rule `[Order.cannot.have.more.than.one]` — repeating the same drug on an active order fails; revise/stop first.
10. Do not treat IPD `medication_administration` as counter dispensing (0 rows; REST unknown resource).

---

## Exact next implementation step

**Do not implement dispensing writes. Do not change Odoo/OpenMRS config in the product increment that follows unless operations explicitly seed masters.**

1. **Hospital EMR Pharmacy read path (no UI redesign):** switch `fetchPharmacyOrders` from `GET /bahmnicore/drugOrders?patientUuid=` to **`GET /bahmnicore/drugOrders/active?patientUuid=`** (keep `GET /drugOrders/{uuid}` for detail). Verify ORD-1 appears for John Adewale. Still no hospital-wide queue — patient search remains the entry.
2. **Block dispensing** until operations install/seed:
   - `order.type` named exactly `Drug Order`
   - `sale.shop` (Pharmacy) + `order.type.shop.map`
   - optionally `syncable.units.mapping` for `Tablet`
   Then re-trace ORD-1 **only if** a new prescription is required; do not spam orders.
3. **After masters exist:** add a **server-side** Odoo read (not frontend) for `sale.order` by `partner.ref` / `sale.order.line.external_order_id`, plus `stock.quant` by `product.product.uuid`. Still no browser Odoo password.
4. Only then design dispense: prefer the installed Atomfeed path (set Dispensed on the OpenMRS order **or** confirm the Odoo quotation), never a parallel Hospital EMR stock table.

---

## Source files inspected (this server)

| Area | Location |
|---|---|
| Clinical JS mapper | `bahmni-web` `clinical.min.317054d3.js` `DrugOrder.createFromUIObject` |
| Write command | `bahmnicore` `DrugOrderSaveCommandImpl` |
| REST controller | `BahmniDrugOrderController` |
| Connect workers | `/var/run/bahmni-erp-connect/bahmni-erp-connect/WEB-INF/classes/org/bahmni/feed/openerp/...` |
| Connect properties | runtime `erp-atomfeed.properties` (do not commit secrets) |
| Odoo REST | `openerp-client` `OdooRESTClient` / `RestClient` → `/api/bahmni-saleorder` |
| Odoo feed | `bahmni_api_feed` `api_event_worker.py`, `order_save_service.py`, `drug_data_service.py` |
| Odoo sale | `bahmni_sale` `sale_order.py`, `sale_order_line.py` |
| Odoo product | `bahmni_product` `product.py` |
| Seed (not installed) | `bahmni_initializer` `data/sale_shop.xml`, `data/order_type.xml` |
| REST addon | `restful_api` `models/api_data_feed.py` |
| Hospital EMR client (unchanged) | `abikan-shell/src/services/openmrs/pharmacy.ts` |
