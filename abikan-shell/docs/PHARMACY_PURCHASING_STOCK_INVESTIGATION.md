# Pharmacy purchasing and stock-receipt investigation

Status labels:

- **CONFIRMED** — verified from this installation’s Odoo 16 addons (`purchase`, `purchase_stock`, `stock`, `stock_account`, `product_expiry`, `bahmni_purchase`, `bahmni_stock`, `bahmni_product`), live PostgreSQL, or installed menus
- **UNKNOWN** — cannot currently be confirmed without a write
- **REQUIRES OPERATIONS CONFIGURATION** — later ops work; not done here
- **REQUIRES CONTROLLED TEST** — needs an approved write; **not executed**
- **ABIKAN FUTURE IMPLEMENTATION** — product work; not implemented in this task

This is investigation only. **No suppliers, purchase orders, receipts, quants, lots, invoices, payments, prescriptions, OpenMRS, Atomfeed, Docker, or Hospital EMR source were written.** S00001 was not confirmed. TEST and production product prices were not changed.

Related: `docs/PHARMACY_INTEGRATION_INVESTIGATION.md`, `docs/ODOO_PHARMACY_CONFIGURATION.md`, `docs/PHARMACY_DISPENSING_BILLING_INVESTIGATION.md`.

Date: **16 Aug 2026**.

Live objects left untouched:

| System | Record |
|---|---|
| Odoo sale | **S00001** id 1, **draft**, Tunde Bakare, origin `API FEED SYNC`, product **110** Paracetamol 500 mg × 10, price 0.00 |
| OpenMRS | ORD-1, ORD-2 only (2 drug orders) |
| TEST products | Odoo 2385–2388; OpenMRS drugs 540–543; UUIDs unchanged |
| Stock | `stock_quant` = 0, `stock_lot` = 0, `stock_picking` = 0, `purchase_order` = 0 |

---

## Architecture (installed)

```
Pharmaceutical supplier  (Odoo res.partner, supplier_rank > 0)
        │
        ▼
Odoo  purchase.order          RFQ (draft) → Confirm → Purchase Order
        │  button_confirm
        │    → button_approve  (company is one_step)
        │    → purchase_stock._create_picking()
        ▼
Odoo  stock.picking           type Receipts (id 1, code incoming)
        source: Partners/Vendors (id 4)
        dest:   WH/Stock (id 8)
        │  Validate  (Bahmni wizard, then super)
        ▼
Odoo  stock.quant             on-hand at WH/Stock
        │
        ▼
Pharmacy Counter sale.shop    warehouse 1, location_id 8, pricelist 1
        │
        ▼
Patient prescription feed     sale.order draft → confirm → delivery OUT from WH/Stock
```

OpenMRS is **not** on this path. Purchasing does not create prescriptions. Dispensing still uses the existing Drug Order → Atomfeed → sale.order pipeline.

---

## CONFIRMED

### 1. Supplier workflow

| Item | Value |
|---|---|
| Model | `res.partner` |
| Table | `res_partner` |
| Vendor vs customer | `supplier_rank` vs `customer_rank` (integers). A partner can be both. |
| Purchase UI filter | `bahmni_purchase` sets PO `partner_id` domain to `supplier_rank > 0` |
| Vendors menu context | `default_is_company=True`, `default_supplier_rank=1`, `search_default_supplier=1` |
| Manufacturer | extra boolean `res.partner.manufacturer` (`bahmni_product`). **0** manufacturers live |
| Must exist before PO? | **Yes.** `purchase.order.partner_id` is required |
| Multiple suppliers per drug? | **Yes.** `product.supplierinfo` (`seller_ids` on the product). Confirming a PO auto-adds the vendor if missing (max 10 sellers) |
| Live suppliers | **0** (`supplier_rank > 0` = 0). 10 customers, 17 partners total |
| Vendor pricelists live | **0** `product_supplierinfo` rows |
| Currency | company currency **USD** (`res.currency` id 2). Partner may set `property_purchase_currency_id` (unset) |
| Payment terms | optional `property_supplier_payment_term_id`; copied onto PO `payment_term_id`. Terms 1–10 exist (Immediate Payment = 1) |
| Company | `company_id` optional on partner; PO requires company **1 Bahmni** |
| Vendor stock location | default `property_stock_supplier` = **stock.location,4** (`Partners/Vendors`). Required at receipt time |

Hospital representation: one `res.partner` per pharmaceutical supplier, **Is a Company**, **Is a Vendor** (`supplier_rank ≥ 1`). Optional manufacturer partners are separate (`manufacturer=True`) and appear on PO lines / product master — not a substitute for the PO vendor.

Do **not** reuse patient partners (Tunde Bakare id 11, etc.) as suppliers.

### 2. Purchase order workflow

| Item | Value |
|---|---|
| Header model | `purchase.order` |
| Line model | `purchase.order.line` |
| Bahmni extra line fields | `mrp`, `manufacturer`, `prod_categ_id` |
| Installed modules | `purchase`, `purchase_stock`, `bahmni_purchase` **installed**. `purchase_requisition` **uninstalled** (no tender/blanket RFQ app) |

Required header fields (ir.model.fields + code):

| Field | Notes |
|---|---|
| `partner_id` | Vendor |
| `currency_id` | defaults to company USD |
| `company_id` | 1 |
| `date_order` | Order deadline, defaults now |
| `name` | sequence, default `New` then `P#####` |
| `picking_type_id` | Deliver To; defaults to warehouse incoming type **Receipts id 1** |

Required line fields:

| Field | Notes |
|---|---|
| `order_id` | parent |
| `product_id` | domain `purchase_ok=True` |
| `product_uom` | SQL constraint with `date_planned` |
| `product_qty` | |
| `price_unit` | vendor unit cost, **not** sale `list_price` |
| `name` | description |
| `date_planned` | expected arrival |

Product mapping: `purchase.order.line.product_id` → `product.product`. For TEST drugs that is ids **2385–2388**. UUID is not used on the PO; UUID only matters for OpenMRS Drug Order → sale order.

Warehouse / destination: **not** a field on `purchase.order`. Incoming location comes from `picking_type_id.default_location_dest_id` = **WH/Stock id 8**. Source on the picking is the vendor location (id 4).

Installed state machine (**CONFIRMED** `purchase.order.state`):

```
draft     RFQ
sent      RFQ Sent          (email; optional)
to approve                 (skipped: company po_double_validation = one_step)
purchase  Purchase Order    (button_confirm → button_approve)
done      Locked            (only if po_lock=lock; live po_lock=edit so confirm stays purchase)
cancel
```

Confirm path (**CONFIRMED**):

1. `bahmni_purchase.button_confirm` → `super()` then optionally rewrite product prices (see §8).
2. Standard `button_confirm`: `_add_supplier_to_product()`, then `_approval_allowed()` → `button_approve()`.
3. `purchase_stock.button_approve` → `state=purchase` then `_create_picking()`.
4. Picking: type Receipts, origin = PO name, `location_id` = vendor location 4, `location_dest_id` = 8.

Receipt of goods is a **separate** Validate on `stock.picking`. Confirming the PO does **not** put quantity on hand.

### 3. Product purchase requirements (TEST drugs)

Read-only live rows. **Not modified.**

| Odoo id | Name | purchase_ok | type | UoM / PO UoM | list_price | mrp | tracking | categ | purchase_method | seller_ids | use_expiration_date |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2385 | Paracetamol 500 mg — TEST | true | stockable `product` | Units / Units | 1000 | 0 | none | Tablet (18) | receive | none | unset |
| 2386 | Amoxicillin 500 mg — TEST | true | stockable `product` | Units / Units | 2500 | 0 | none | Oral capsule (21) | receive | none | unset |
| 2387 | Artemether/Lumefantrine — TEST | true | stockable `product` | Units / Units | 3500 | 0 | none | Tablet (18) | receive | none | unset |
| 2388 | Vitamin C 100 mg — TEST | true | stockable `product` | Units / Units | 800 | 0 | none | Tablet (18) | receive | none | unset |

| Question | Answer |
|---|---|
| Can they be purchased now? | **Yes.** `purchase_ok=true`, storable, UoM Units |
| Vendor record required on the product first? | **No.** PO vendor is the partner. Confirm **creates** `product.supplierinfo` |
| Vendor pricelist required? | **No.** `price_unit` is typed on the line. If a seller exists, onchange may copy its price |
| Vendor product code? | Optional `product.supplierinfo.product_code`. Empty today |
| Purchase UoM? | `uom_po_id` = 1 Units (same as sale UoM). Do not create a new UoM |
| Cost price? | `standard_price` is an `ir.property`. **0 rows** for these products (cost 0.00) |
| Stockable? | `type=product` / `detailed_type=product` |
| Company? | empty (same as production drugs) |

Production Paracetamol **110** is also `purchase_ok`. Do **not** purchase it in the TEST.

### 4. Warehouse / receiving

| Item | Live |
|---|---|
| Warehouse | id **1** `My Company` / code `WH`, company 1 |
| Reception steps | **`one_step`** — goods go straight to stock. `WH/Input` (9) and `WH/Quality Control` (10) exist but are **inactive** |
| Delivery steps | `ship_only` |
| Stock location | id **8** `WH/Stock` (`lot_stock_id`) |
| Incoming picking type | id **1** name **Receipts**, code `incoming`, sequence `WH/IN/#####` |
| Receipt source on type | empty; picking uses vendor location **4** |
| Receipt destination | **8 WH/Stock** |
| Lots on receipts type | `use_create_lots=true`, `use_existing_lots=false` |
| Backorders | `create_backorder=ask` |
| Pharmacy Counter shop | warehouse **1**, `location_id` **8**, pricelist **1** |
| Dedicated Pharmacy location | **Does not exist.** 16 locations; only internal active warehouse location is WH/Stock |

Incoming pharmaceutical stock **enters WH/Stock**. Outgoing Pharmacy deliveries also leave **WH/Stock**. That is consistent for this hospital **until** a separate Pharmacy location is created.

Inventory → Transfers is the stock UI for receipts. Invoicing → Vendors → Receipts is **`account.move` `in_receipt`** (accounting), **not** goods receipt.

### 5. Receiving workflow (goods receipt)

When a confirmed PO is received:

```
purchase.order (state=purchase)
    → stock.picking (Receipts, typically assigned)
        → user sets quantity_done on moves / move lines
        → button_validate
              bahmni_stock: if incoming/internal and not validation_confirmed
                    → stock.picking.validate.wizard
                    → Confirm → button_validate(context validation_confirmed)
              super().button_validate()
                    → _action_done
                    → stock.quant at dest location
              bahmni_stock.update_price_details_for_lots()  (no-op if tracking=none)
```

| Question | Answer |
|---|---|
| When is stock available? | After receipt picking `state=done`. PO confirm alone is not enough |
| Records created | `stock.picking`, `stock.move`, `stock.move.line`, then `stock.quant`. Vendor **bill** (`account.move` in_invoice/in_receipt) is **separate** and not auto-created by receipt |
| Lot/expiry required? | **Only if** `product.tracking` is `lot`/`serial`. TEST products are `none` |
| Accounting on receipt? | Category valuation is **`manual_periodic`**. Real-time stock journal entries are **not** expected on Validate. Inventory Valuation journal (id 8) and accounts 110100/110200/110300 exist but apply to **perpetual** valuation |
| Partial receipts? | **Yes.** `create_backorder=ask` |
| Backorders? | **Yes**, user is asked when qty_done < demand |
| Bahmni extra on lot-tracked receive | move line `cost_price` / `sale_price` / `mrp` / `expiration_date` copied onto `stock.lot` |

Odoo 10 leftovers remain on `bahmni_stock.stock_picking` (`pack_operation_ids`, `do_prepare_partial`). Incoming Validate still calls **Odoo 16** `super().button_validate()`. Exact wizard/backorder UI behaviour: **REQUIRES CONTROLLED TEST**.

### 6. Stock location / dedicated Pharmacy location

This installation **can** add an internal location (Inventory → Configuration → Locations) as a child of `WH` (view id 7) or of `WH/Stock` (id 8).

To use it as Pharmacy stock:

1. Create internal location e.g. `WH/Pharmacy` (not done).
2. Set `sale.shop` Pharmacy Counter `location_id` to that location (outgoing / lot search / feed batch helper).
3. Either set Receipts `default_location_dest_id` to the same location, **or** receive into WH/Stock and Internal Transfer (picking type id 5) into Pharmacy.

If Pharmacy is a **sibling** of Stock and receipts still dest to 8, Pharmacy on-hand stays 0 until transfer.

**Recommendation for the first stock test:** keep **WH/Stock id 8** for both receive and Pharmacy Counter. Do not create a location yet.

### 7. Lot / batch / expiry

| Item | Live |
|---|---|
| TEST tracking | **`none`** |
| Production Paracetamol 110 tracking | **`none`** |
| `stock.lot` rows | **0** |
| `use_expiration_date` on TEST | unset / false |
| Location `removal_strategy_id` | **NULL** on all locations |
| Removal methods installed | FIFO, LIFO, closest, **FEFO** (`product_removal` ids 1–4) |
| `product_expiry` module | **installed** |
| Manage Lots group | id 39, **5 users** (lots UI exists even if products are untracked) |
| Feed FEFO | `bahmni_sale` already sorts quants by `expiration_date` when lots exist (`allocate_quantity_from_multiple_batches=True`) |
| Confirm sale without lot | allowed when tracking=`none` (S00001 path) |

**For the first purchase test, tracking=none is acceptable** — it isolates PO → quant without lot UI.

**For real hospital pharmacy, Operations should eventually enable lot/batch + expiry** (`tracking=lot`, `use_expiration_date=true`, prefer FEFO on the Pharmacy location). Do **not** enable that on production drugs or TEST drugs in this task.

### 8. Purchase price vs sale price

| Store | Field | Role |
|---|---|---|
| Sale to patient | `product.template.list_price` | Pharmacy Counter pricelist **1** has no items → sale uses `list_price` |
| Product cost | `standard_price` (`ir.property` on product) | **empty** for TEST (0) |
| Vendor quote | `product.supplierinfo.price` | **0 rows** |
| This PO | `purchase.order.line.price_unit` | can differ from `list_price` |
| Bahmni MRP | `purchase.order.line.mrp`, `product.mrp` | 0 on TEST |
| Lot-level (if tracked) | `stock.lot.cost_price` / `sale_price` / `mrp` | unused while tracking=none |

Purchase price **does not automatically change** sale `list_price` unless Bahmni markup rewrite runs.

**Live risk:** `ir.config_parameter` `bahmni_purchase.update_product_prices_on_po_confirm` = **`True`**.

On PO confirm, `bahmni_purchase` computes `sale_price` from `price.markup.table`. Live markup table = **0 rows**, so `calculate_price_with_markup` returns the cost unchanged, then code sets `sale_price=None` and writes **only** `standard_price` and `mrp` — **not** `list_price`.

So today: confirming a TEST PO is expected to **keep** sale prices 1000/2500/3500/800 and **set** cost to the PO unit price. If anyone later adds markup rows, confirm **would overwrite `list_price`**. `bahmni_sale.sale_price_markup` is also True (sale-side).

PO line price is independent of `list_price`. Use a **lower** purchase cost in the test (e.g. 400 vs sale 1000).

Company currency is **USD**, not Naira. Numeric 400 means 400 in the company currency.

### 9. Stock valuation

| Item | Live |
|---|---|
| Cost method (company default `ir.property` “Cost Method Property”) | **`standard`** |
| Inventory valuation | **`manual_periodic`** (periodic, not real-time/AVCO/FIFO accounting) |
| Per-category overrides | empty `value_reference` on categories 1–37 → inherit company default |
| Stock valuation account | 110100 id 3 (default) |
| Interim received / delivered | 110200 id 4, 110300 id 5 |
| Inventory journal | id 8 `STJ` |
| COGS account | 500000 id 25 exists; expense category default is 600000 id 26 |
| FIFO/AVCO costing | **not** the live cost method |

Receipt with `manual_periodic` + `standard` updates quantities. It does **not** post a perpetual inventory valuation move. Vendor bill (when created later) is the accounting purchase. Do not change accounting in the first stock test.

### 10. Stock availability (what Pharmacy can read)

On-hand today: **0** quants.

| Need | Odoo source | Notes |
|---|---|---|
| On hand | `stock.quant.quantity` at location 8 (and children) | source of truth |
| Reserved | `stock.quant.reserved_quantity` | deliveries after SO confirm |
| Incoming | `product.product.incoming_qty` (ORM, location/warehouse context) | confirmed PO not yet received |
| Outgoing | `product.product.outgoing_qty` | confirmed deliveries |
| Forecast | `product.product.virtual_available` | on hand − outgoing + incoming |
| Free | standard `free_qty` is **overridden** by Bahmni | see below |

**Do not trust** Bahmni `product.product.actual_stock` or stored `free_qty` for integration. Installed `bahmni_product` declares them **without a compute method**. Live TEST `free_qty=0.00`, `actual_stock` NULL, and they will not follow receipts unless something else writes them.

**Safe read for a future server-side API:**

```
product.product.browse(2385).with_context(location=8).qty_available
stock.quant.search([('product_id','=',2385),('location_id','=',8)])
```

Key by `product.product.uuid` = OpenMRS drug uuid.

`restful_api` today only has POST `/api/bahmni-*` feed workers. **No stock GET.** Hospital EMR browser JS must not call Odoo. A later backend service should use a service user (not `emrsync` from the browser).

### 11. Purchasing UI (already installed)

Odoo **Purchase** app (menu id 236):

| Menu | Model |
|---|---|
| Purchase → Orders → Requests for Quotation | `purchase.order` (RFQ / all via context `quotation_only`) |
| Purchase → Orders → Purchase Orders | `purchase.order` domain `state in (purchase, done)` |
| Purchase → Orders → Vendors | `res.partner` supplier mode |
| Purchase → Configuration → Vendor Pricelists | `product.supplierinfo` |
| Purchase → Products | product templates/variants |
| Purchase → Reporting | purchase reports |

Odoo **Inventory** app (menu id 174):

| Menu | Use |
|---|---|
| Operations → Transfers | `stock.picking` including Receipts `WH/IN/…` |
| Operations → Lots/Serial Numbers | `stock.lot` |
| Operations → Inventory Adjustments | **do not use** for normal buying |
| Reporting → Stock | on-hand |
| Configuration → Warehouses / Locations / Operations Types | WH 1, loc 8, Receipts type 1 |

Do not change the UI.

### 12. Pharmacy architecture (Odoo vs Hospital EMR)

**CONFIRMED safest split**

| Layer | Owner |
|---|---|
| Supplier, RFQ, PO, goods receipt, quants, lots, vendor bills | **Odoo Purchase + Inventory** |
| Clinical prescription, drug catalogue uuid | **OpenMRS** |
| Patient bill after Drug Order feed | **Odoo Sales** (existing) |
| Hospital EMR Pharmacy today | OpenMRS Rx queue only |
| Hospital EMR Pharmacy later | **read** Odoo on-hand / reserved / incoming via **server-side** integration |
| Hospital EMR Procurement UI | optional later **read** of PO/receipt status; **no** browser stock writes |

Hospital EMR should **not** create purchase orders, validate pickings, or adjust quants from frontend JavaScript. Purchasing stays in Odoo until a dedicated server-side procurement API exists.

---

## UNKNOWN

1. Exact Bahmni receipt wizard clicks / whether Odoo 16 also shows the standard immediate-transfer or backorder wizard after the Bahmni wizard.
2. Whether `button_validate` + `manual_periodic` creates **any** `account.move` (expected: none; untested).
3. Whether Bahmni `free_qty` / `actual_stock` get written by some cron or UI not present in `bahmni_product` models.
4. Whether `_add_supplier_to_product` fails silently if the user lacks product write rights (code uses `sudo()` on the template write).
5. Internal transfer + dedicated Pharmacy location end-to-end (location does not exist).
6. Enabling `tracking=lot` on an existing TEST product that already has untracked quants (Odoo often forbids that). First receipt should stay `tracking=none`, or lots should be enabled **before** any quant exists.

---

## REQUIRES OPERATIONS CONFIGURATION

Not done in this task.

1. At least one pharmaceutical **TEST vendor** (`res.partner`, `supplier_rank ≥ 1`).
2. Optional: turn **off** `bahmni_purchase.update_product_prices_on_po_confirm` before any PO if Operations want **zero** writes to `standard_price`/`mrp`. Live value is True.
3. Optional later: `price.markup.table` rows — **do not add** before TEST sale prices are protected; they would rewrite `list_price` on PO confirm.
4. Optional later: dedicated `WH/Pharmacy` location + shop + receipt dest (or internal transfer procedure).
5. Optional later: `tracking=lot` + expiry + FEFO on **real** drugs, only on products with **zero** quants.
6. Optional later: `syncable.units.mapping` Capsule → Units (Amoxicillin TEST prescriptions only).
7. Do **not** install `bahmni_initializer`.
8. Do **not** change company currency or pricelist 1.

---

## REQUIRES CONTROLLED TEST

See §13. **Not executed.**

---

## ABIKAN FUTURE IMPLEMENTATION

1. Server-side Odoo read: on-hand / incoming / outgoing by `product.product.uuid` at location 8 (or future Pharmacy location).
2. Do not add Odoo passwords to Hospital EMR frontend.
3. Do not POST `/api/bahmni-saleorder` or invent a browser purchase API.
4. Optional later: Hospital EMR “Procurement” workplace that **displays** Odoo RFQ/PO/receipt state through the same backend.
5. Keep OpenMRS as the only prescription writer.

---

## 13. Controlled test plan (do not run yet)

Goal: one TEST drug, one TEST supplier, one PO, one full receipt, on-hand at Pharmacy WH/Stock. No patient prescription. No S00001. No production products.

### Records to create (future approval)

**A. Vendor** `res.partner`

| Field | Value |
|---|---|
| `name` | `Hospital EMR TEST Pharma Supplier` |
| `is_company` | true |
| `supplier_rank` | 1 |
| `customer_rank` | 0 |
| `company_id` | 1 or empty |
| `property_stock_supplier` | default location **4** (do not change) |
| `manufacturer` | false |

**B. Purchase order** `purchase.order`

| Field | Value |
|---|---|
| `partner_id` | TEST vendor |
| `company_id` | 1 |
| `currency_id` | 2 (USD) |
| `picking_type_id` | **1** Receipts |
| `payment_term_id` | 1 Immediate Payment (optional) |
| `order_line` | one line only |

**C. Line** `purchase.order.line`

| Field | Value |
|---|---|
| `product_id` | **2385** Paracetamol 500 mg — TEST |
| `product_qty` | **100** |
| `product_uom` | **1** Units |
| `price_unit` | **400** (purchase cost; sale stays 1000) |
| `date_planned` | now |
| `mrp` | leave 0 or 1000; do not use this to change `list_price` |

Do **not** add 2386–2388, product 110, or any production drug.

### Expected states

| Step | Expected |
|---|---|
| Create RFQ | `purchase.order` `state=draft`, name `P#####` |
| Confirm | `state=purchase` (`po_lock=edit`, not `done`) |
| Side effect | `product.supplierinfo` for 2385 + TEST vendor; `standard_price` → 400 if price-update param stays True; **`list_price` stays 1000** while markup table is empty |
| Picking | `stock.picking` type 1, origin PO name, src 4, dest **8**, moves qty 100 |
| Before Validate | `stock_quant` still 0 |
| Set done qty 100, Validate (+ Bahmni wizard Confirm) | picking `done` |
| After receipt | `stock.quant` product **2385** location **8** `quantity=100`, reserved 0 |
| Availability | `qty_available` with `location=8` = **100** |
| Pharmacy Counter | can later dispense 2385 from the same location |
| Untouched | S00001 draft; product 110 price 0; OpenMRS ORD-1/ORD-2; no invoices/payments; products 2386–2388 qty 0 |

### Rollback (after the future test)

1. If picking is `done`: return the receipt (Return on the picking) for 100 Units of 2385, or an inventory adjustment **only** for 2385 at location 8 down to 0. Do not use this for other products.
2. Cancel remaining backorder pickings.
3. Cancel or lock-then-leave the PO (`button_cancel` if no posted vendor bill).
4. Unlink the TEST `product.supplierinfo` row(s).
5. Clear TEST product `standard_price` / `mrp` if the confirm rewrite set them. **Restore `list_price=1000` if it changed.**
6. Archive the TEST vendor (`active=false`) or unlink if unused.
7. Confirm still: S00001 draft; `stock_quant` for 110 = 0; OpenMRS order count = 2.

---

## 14. Risks

1. **`update_product_prices_on_po_confirm=True`** plus a non-empty markup table would overwrite TEST **sale** prices. Markup is empty **today**.
2. PO confirm **always** writes `seller_ids` onto the product (standard Odoo). Limit the test to product 2385.
3. Receiving **product 110** would enable confirming S00001 with auto-delivery + auto-invoice. Do not stock 110 in this test.
4. `allow_negative_stock=0`. Receipt must succeed before any TEST sale confirm.
5. Currency is USD. Do not treat 400/1000 as Naira in accounting reports.
6. Bahmni receipt wizard + Odoo 10 leftover picking methods: Validate may look different from vanilla Odoo 16.
7. `manual_periodic` valuation: Operations may expect GL stock postings that will **not** appear.
8. `tracking=none` will not capture batch/expiry. Fine for this test; wrong as the long-term pharmacy model.
9. Amoxicillin TEST still has no Capsule → Units map (prescription-time issue, not purchase).
10. Inventory Adjustments would create stock **without** a supplier PO — do not use that as the hospital buying process.

---

## 15. Rollback plan (this investigation)

Nothing was written. No rollback.

If a later purchase test is run, use the rollback in §13.

Do not: confirm S00001; modify production drugs; modify OpenMRS; rewind Atomfeed; `docker compose down -v`; change pricelist 1; enable lots on products that already have quants.

---

## What must not be changed (standing)

- S00001
- ORD-1 / ORD-2
- Production Paracetamol 500 mg (OpenMRS + Odoo 110) and its price 0.00
- TEST product **sale** prices (1000 / 2500 / 3500 / 800) except the documented confirm side-effect on **cost**
- OpenMRS concepts and TEST drug UUIDs
- Tablet → Units mapping
- Pharmacy Counter pricelist 1 / location 8
- Docker / Atomfeed / Hospital EMR source
