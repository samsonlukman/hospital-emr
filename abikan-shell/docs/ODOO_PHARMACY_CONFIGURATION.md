# Odoo Pharmacy configuration plan

Status labels:

- **CONFIRMED** — verified from this installation’s Odoo addons, odoo-connect classes, live PostgreSQL / MySQL, or container logs
- **UNKNOWN** — cannot currently be confirmed
- **REQUIRES OPERATIONS CONFIGURATION** — a record or setting Operations must create later; **not created in this task**

This document is investigation and planning only. No `order.type`, `sale.shop`, sale orders, invoices, stock, prices, OpenMRS, Atomfeed, Docker, or databases were written.

Related: `docs/PHARMACY_INTEGRATION_INVESTIGATION.md`.

Date of live verification: **16 Aug 2026**.

Live prescription used as the reference event:

| Field | Value |
|---|---|
| Patient | John Adewale |
| MRN | `ABC200012` |
| OpenMRS order | `ORD-1` uuid `e7eb086a-ce26-42d2-87ba-0c17f22e3a1b` |
| Drug | Paracetamol 500 mg |
| OpenMRS / Odoo drug uuid | `e8265115-66d3-459c-852e-b9963b2e38eb` |
| Quantity | 10 **Tablet** |
| Encounter location | **OPD-1** |
| Status | Ordered (`dispensed` = `"false"`) |

Odoo log for that event:

```
Order Type - Drug Order is not defined. Ignoring Drug Order for Customer John Adewale [ABC200012]
POST /api/bahmni-saleorder  HTTP 200
```

---

## Status summary

| Item | Result |
|---|---|
| Order Type model | **CONFIRMED** `order.type` |
| `"Drug Order"` name match | **CONFIRMED** exact, case-sensitive |
| Live `order.type` rows | **CONFIRMED** 0 |
| Sale Shop model | **CONFIRMED** `sale.shop` |
| Live `sale.shop` rows | **CONFIRMED** 0 |
| Product mapping field | **CONFIRMED** `product.product.uuid` = OpenMRS drug uuid |
| Paracetamol mapped | **CONFIRMED** product id 110 |
| Price source | **CONFIRMED** Odoo `list_price` (then pricelist / lot); not OpenMRS |
| Live Paracetamol `list_price` | **CONFIRMED** `0.00` |
| Stock on hand | **CONFIRMED** 0 quants / 0 lots |
| Sale order created for ORD-1 | **CONFIRMED** no |
| Why HTTP 200 on ignore | **CONFIRMED** skip is not an exception |
| ORD-1 will auto-retry after config | **CONFIRMED** no (marker already consumed) |
| A **new** prescription can create a sale order after masters exist | **CONFIRMED** yes, if shop + units mapping are also valid |

---

## 1. Order Type model

**CONFIRMED**

| Item | Value |
|---|---|
| Odoo model | `order.type` |
| Python | `bahmni_api_feed/models/order_type.py` |
| Table | `order_type` |
| Required fields | `name` (Char, unique) |
| Optional fields | `description` (Text) |
| Code / identifier | **none** |
| Company field | **none** |
| Sale shop field | **none** on this model |
| Product / category field | **none** |
| SQL constraint | `order_type_unique_name` on `name` |

UI: Sales → Configuration → Order Type (`bahmni_api_feed` views). Access is unrestricted in `ir.model.access.csv` (no group).

`order.type` is only a named lookup key. It does **not** itself point at a warehouse, shop, or product category.

### How odoo-connect searches for `"Drug Order"`

**CONFIRMED**

1. OpenMRS `order_type.name` for drug orders is **`Drug Order`**.
2. `MapERPOrders` copies `OpenMRSDrugOrder.orderType` onto `OpenERPOrder.type`.
3. Odoo `order.save.service.create_orders` groups payload orders by `order['type']`, then:

```python
self.env['order.type'].search([('name', '=', orderType)])
```

That is an exact equality search. The name **must** be `Drug Order` — not `Drug`, `DrugOrder`, `drug order`, or `Pharmacy`.

If no row matches: warning + `continue`. The rest of the payload is not processed for that type.

Initializer seed (module **uninstalled** on this server) uses exactly:

| name | description purpose |
|---|---|
| `Drug Order` | medications |
| `Lab Order` | lab |
| `Radiology Order` | imaging |

Lab / Radiology types are **not** required for the Pharmacy drug-order path. They are required later if those feeds should create sale orders.

**REQUIRES OPERATIONS CONFIGURATION:** create one `order.type` with `name` = `Drug Order`.

---

## 2. Required `"Drug Order"` configuration

**CONFIRMED** minimum for the lookup to stop ignoring the event:

| Field | Required | Value |
|---|---|---|
| `name` | yes | `Drug Order` (exact) |
| `description` | no | any text |

That alone is **not** enough to create a sale order. After the type exists, `create_orders` immediately calls `_get_shop_and_location_id`. If there is no `order.type.shop.map` **and** `sale.shop` is empty, Python does `shop_records[0]` and raises `IndexError`. That **would** fail the event (JSON `status: 417`) instead of silently ignoring it.

**REQUIRES OPERATIONS CONFIGURATION:** `order.type` **and** at least one `sale.shop` before any new prescription is allowed to hit Odoo.

---

## 3. Sale Shop model

**CONFIRMED**

| Item | Value |
|---|---|
| Odoo model | `sale.shop` |
| Python | `bahmni_sale/models/shop.py` |
| Table | `sale_shop` |
| What it represents | A Bahmni **billing / dispensing counter**: warehouse, stock location, default payment term, optional pricelist. It is **not** a separate Pharmacy app. |
| Physical pharmacy | **Yes, conceptually** — one shop ≈ one pharmacy counter that issues stock and quotations. It is not an OpenMRS location. |
| Multiple shops | **Yes.** `sale.order.shop_id` is Many2one. Different `order.type.shop.map` rows can send OPD vs ward orders to different shops. |

### Fields

| Field | Python required | DB required | Form view | Live usable value on this server |
|---|---|---|---|---|
| `name` | yes | yes | yes | convention: `Pharmacy` (name is **not** searched by the feed) |
| `payment_default_id` | yes | yes | shown | id **1** `Immediate Payment` exists |
| `warehouse_id` | no | no | **required="1"** | id **1** `My Company` / code `WH` |
| `location_id` | no | no | **required="1"** | id **8** `WH/Stock` (warehouse `lot_stock_id`) |
| `pricelist_id` | no | no | optional | id **1** `Public Pricelist` exists |
| `company_id` | no (defaults to company) | no | multi-company only | company id **1** `Bahmni` |
| `project_id` | no | no | analytic group | unused |

`sale.order.shop_id` is **required**. Every quotation created by the feed must have a shop.

Help text in the shop form: *Each quotation or sales order must be linked to a shop. The shop also defines the warehouse from which the products will be delivered.*

### Order type ↔ shop mapping

**CONFIRMED** model `order.type.shop.map`

| Field | Required |
|---|---|
| `order_type` | yes |
| `shop_id` | yes |
| `location_name` | no — OpenMRS **encounter location display name** (e.g. `OPD-1`) |
| `location_id` | no — Odoo `stock.location` used on the sale order |

Lookup in `_get_shop_and_location_id`:

1. `(order_type, location_name = encounter location)` — e.g. `Drug Order` + `OPD-1`
2. else `(order_type, location_name is NULL)`
3. else **first** `sale.shop` in the database

Initializer seed maps Drug / Lab / Radiology → shop `Pharmacy` with `location_name` = **`General Ward`** only. **ORD-1 was from OPD-1.** Copying that seed verbatim would miss the named map and fall through to (2) or (3).

Bahmni wiki (same algorithm): start with a default mapping that has **blank** Order Location Name, then add location-specific maps.

### Live warehouse / location (already exist — do not recreate)

| Record | id | Name |
|---|---|---|
| `stock.warehouse` | 1 | My Company (`WH`), `lot_stock_id` = 8 |
| `stock.location` | 8 | `WH/Stock` (internal) |
| Delivery picking type | 2 | Delivery Orders, source location 8 |

`order.picking.type.mapping` table **does not exist** on this database. `create_orders` does **not** use that model for the main path; it copies `sale.shop.warehouse_id`.

---

## 4. Required Pharmacy `sale.shop` configuration

**REQUIRES OPERATIONS CONFIGURATION** — minimum valid shop for a Drug Order:

| Field | Minimum | Recommended for Hospital EMR |
|---|---|---|
| `name` | any non-empty (e.g. `Pharmacy`) | `Pharmacy` or `Hospital EMR Pharmacy` |
| `payment_default_id` | required | id 1 Immediate Payment |
| `warehouse_id` | required by UI; needed for SO warehouse | id 1 |
| `location_id` | required by UI; used for batch/quant search | id 8 `WH/Stock` |
| `pricelist_id` | optional | id 1 if list prices will be used via pricelist |
| `company_id` | optional | 1 Bahmni |

Plus mapping:

| Record | Minimum | Recommended |
|---|---|---|
| `order.type.shop.map` | optional if a shop exists (fallback = first shop) | **create** `Drug Order` → Pharmacy shop with **`location_name` empty (NULL)** as default, **and** a row with `location_name` = `OPD-1` (and later OPD-2 / wards as needed) |
| map `location_id` | optional | 8 `WH/Stock` |

Do **not** rely on shop name matching `"Pharmacy"`. The feed never searches shops by name.

---

## 5. Product mapping

**CONFIRMED**

odoo-connect sets `OpenERPOrder.productId` = `OpenMRSDrugOrder.getDrugUuid()` = OpenMRS **drug** uuid (not concept uuid, not order uuid).

Odoo lookup:

```python
self.env['product.product'].search([('uuid', '=', order['productId'])])
```

| Candidate field | Used for drug orders? |
|---|---|
| `product.product.uuid` | **yes — this is the mapping** |
| `product.template.uuid` | no (fallback only when `productId` is empty, and that fallback searches **template name** = `conceptName`) |
| `default_code` | **no** |
| `ir.model.data` external ID | **no** |
| Product name | **no** for coded drugs |

If no `product.product` matches the uuid, the line is skipped (`_filter_products_undefined`) and a warning is logged. The HTTP call can still return 200.

### Paracetamol 500 mg (re-verified)

| Field | Live value |
|---|---|
| `product.product` id | 110 |
| `product.product.uuid` | `e8265115-66d3-459c-852e-b9963b2e38eb` |
| `product.template.uuid` | empty |
| `default_code` | empty |
| `ir.model.data` | none |
| name | Paracetamol 500 mg |
| `drug` | Acetaminophen |
| `type` | `product` (storable) |
| `sale_ok` / `purchase_ok` | true |
| `tracking` | `none` |
| `uom_id` | 1 Units |
| `categ_id` | 18 `All / Saleable / Drugs / Tablet` |
| `list_price` | **0.00** |

2381 of 2384 `product.product` rows have a uuid. Mapping for this drug is already correct. **Do not recreate the product.**

---

## 6. Price mapping

**CONFIRMED** — OpenMRS does **not** send a price.

Line creation order:

1. `price_unit = product.product.list_price` (template list price).
2. If a **lot** is assigned and the shop/partner has a pricelist: `_get_display_price()` (pricelist).
3. If `bahmni_sale.sale_price_markup` is True (**live: True**) and `stock.lot.sale_price > 0`: use **lot sale price**.
4. If **no lot / no batch** (this server): the no-batch branch **does not** apply the pricelist. Price stays `list_price`.

Live:

| Source | Value |
|---|---|
| Paracetamol `list_price` | 0.00 |
| Partner John pricelist property | none in `ir_property` |
| `sale.shop.pricelist_id` | no shops |
| `stock.lot` | 0 rows |
| OpenMRS | no price field on the payload |

So a successful sale order for ORD-1-class drugs would currently bill **0.00** until Operations sets `list_price` and/or lot `sale_price` / pricelist.

**REQUIRES OPERATIONS CONFIGURATION** for real billing amounts. **Do not change prices in this task.**

There is no NHIA / insurance pricing in the installed Bahmni sale addons.

---

## 7. Stock requirements

**CONFIRMED** — configuration needed before Odoo can reserve or deduct pharmacy stock. **Do not create stock in this task.**

| Requirement | Live state | Needed for |
|---|---|---|
| Product type `product` (storable) | Paracetamol already `product` | stock moves |
| Unit of measure | Units (id 1) | lines / moves |
| Shop `location_id` internal location | no shop; WH/Stock id 8 exists | quant search |
| `stock.quant` qty > 0 at shop location | **0 quants** | batch allocation and delivery |
| Lot tracking | **all 539** storable products `tracking=none` | lots optional on confirm |
| Expiry | lots support `expiration_date`; unused while no lots | batch FEFO sort |
| `allow_negative_stock` | **0** | delivery will not force-assign if stock missing |
| Reordering rules | 0 | not required for first SO |

Feed behaviour with empty stock:

- `get_available_batch_details` finds no quants → line created **without** `lot_id`.
- `action_confirm` requires `lot_id` **only if** `product.tracking == 'lot'`. Current drugs are `none`, so confirm does not demand a batch.
- Confirm **does** reject `product_uom_qty <= 0`.
- `bahmni_sale.is_delivery_automated` is **True**: after confirm, Odoo tries to set `quantity_done` and `_action_done` on pickings. With 0 stock and `allow_negative_stock=0`, delivery is expected to fail.
- `validate_delivery_when_order_confirmed` is **0**. The older `auto_validate_delivery()` path still uses Odoo 10 APIs (`pack_operation_product_ids`, `do_new_transfer`) and is **not trustworthy on Odoo 16**.

**REQUIRES OPERATIONS CONFIGURATION** (later, not for the first draft quotation): inventory at `WH/Stock` for each dispensed product. Enabling lot tracking is optional and would then require lots on every confirm.

---

## 8. Billing flow

**CONFIRMED** from installed `bahmni_sale` + `order.save.service`. No live sale/invoice records exist (`sale_order=0`, customer invoices=0).

### Non-dispensed (ORD-1 / Hospital EMR “Ordered”)

Intended:

```
Atomfeed → draft sale.order (origin='API FEED SYNC', state=draft)
        → pharmacist confirms in Odoo
        → stock.picking (if delivery automated)
        → account.move invoice (if invoice automated)
        → payment (manual, or payment screen if user in redirect group)
```

The feed **does not** confirm the quotation for Ordered prescriptions.

On `sale.order.action_confirm` (Odoo UI / RPC):

1. Reject qty ≤ 0.
2. Reject missing lot if tracking is `lot`.
3. `super().action_confirm()` — standard quotation → sale.
4. If `bahmni_sale.is_delivery_automated` (**True**): validate pickings immediately.
5. If `bahmni_sale.is_invoice_automated` (**True**): `_create_invoices()`.
6. Optionally open Payments if the user is in `bahmni_sale.group_redirect_to_payments_on_sale_confirm`.

### Dispensed (`dispensed='true'`)

Would try `auto_validate_delivery()` then `validate_payment()` when:

- `ir.values` `sale.config.settings.convert_dispensed` is set — **`ir.values` does not exist on this Odoo 16 database**
- `auto_register_invoice_payment_for_dispensed` is `'1'` — live value **0**

A Dispensed event hitting the current `convert_dispensed` lookup is expected to **crash** (`ir.values` missing), which would return JSON `status: 417` and leave a **failed atomfeed event**. Do not enable OpenMRS “Dispensed” until that path is re-verified.

Hospital EMR must **not** set Dispensed from browser JavaScript. That is a later server-side integration topic.

---

## 9. odoo-connect request / response

**CONFIRMED**

Pipeline:

```
OpenMRS encounter atomfeed
  → OpenERPSaleOrderEventWorker
  → GET bahmniencounter JSON + visit JSON
  → MapERPOrders.getParameters
  → OdooRESTClient POST {odooURL}  (live: /api/bahmni-saleorder)
  → restful_api.bahmni_saleorder_creation  auth="user"  (session: emrsync)
  → api.event.worker.process_event
  → order.save.service.create_orders
```

### Request body (JSON-RPC / REST parameters)

| Key | Source |
|---|---|
| `category` | always `create.sale.order` |
| `customer_id` | encounter `patientId` = **MRN** `ABC200012` (not UUID) |
| `encounter_id` | encounter uuid |
| `locationName` | encounter location display (`OPD-1`) |
| `orders` | JSON `{ id, openERPOrders: [ ... ] }` |
| `feed_uri` / `last_read_entry_id` / `feed_uri_for_last_read_entry` | atomfeed cursor |

Each `openERPOrders[]` element (drug):

| Field | Source |
|---|---|
| `type` | OpenMRS order type name → `Drug Order` |
| `orderId` | drug order uuid |
| `productId` | **drug** uuid |
| `productName` | drug name |
| `quantity` / `quantityUnits` | dosing instructions (`10` / `Tablet`) |
| `dispensed` | `"true"` only if a Dispensed observation is true; else `"false"` |
| `visitType` | visit type string (lowercased in Odoo to `opd`/`ipd`) |
| `providerName` | first encounter provider |
| `conceptName` | drug concept name |
| `voided` / `action` / `previousOrderId` | order lifecycle |

Patient lookup: `res.partner.search([('ref', '=', customer_id)])`. John Adewale **exists** (`ref=ABC200012`, uuid matches OpenMRS). Missing partner raises `UserError("Patient Id not found in Odoo")`.

Product lookup: see §5.

Quantity: see §10 (units mapping).

Sale order create (non-dispensed): draft SO with `origin='API FEED SYNC'`, `shop_id`, `warehouse_id` from shop, `location_id` from mapping, `payment_term_id` from shop, `company_id` hardcoded **1**, `pricelist_id` from shop if set else partner pricelist.

### HTTP response

Odoo controller (`restful_api`):

```python
return {'status': 200, 'message': request.env['api.event.worker'].process_event(json_data)}
```

On exception:

```python
return {"status": 417, "error": "Expectation Failed: " + str(e)}
```

`type="json"` still yields **HTTP 200** for both dicts. odoo-connect `ResponseChecker`:

- Non-2xx HTTP → fail event
- JSON-RPC `result.error` present → fail event (so a **raised** Python exception becomes failed atomfeed)
- `result` without `error` → **success**, marker advances

`process_event` for `create.sale.order` **always** returns `"Sale order has been created successfully."` if `create_orders` does not raise — even when every order type was skipped.

---

## 10. Failure behaviour

**CONFIRMED**

| Situation | Odoo behaviour | Atomfeed |
|---|---|---|
| Missing `order.type` named `Drug Order` | warning, `continue`, no SO | **success / consumed** (ORD-1) |
| Type exists, **no** `sale.shop` | `IndexError` on first shop | fail (JSON 417 in result) |
| Patient MRN not in `res.partner.ref` | `UserError` | fail, retry |
| Product uuid missing | line skipped; SO may still be created for other lines | success if no exception |
| No `syncable.units.mapping` for `Tablet` | quantity forced to **0**; draft line still created | success |
| Confirm with qty 0 | `UserError` in Odoo UI | n/a (feed already done) |
| Confirm with no stock, delivery automated | picking `_action_done` likely fails | n/a |
| Dispensed + `ir.values` missing | exception in `create_orders` | fail |
| Empty JSON body | controller returns nothing useful | **UNKNOWN** |

**Why ORD-1 returned HTTP 200:** ignore is a log + `continue`, not an exception. Connect treats HTTP 2xx + no `result.error` as success and **does not retry**.

Re-feeding ORD-1 after Operations creates masters: **UNKNOWN** without a failed-event replay or a **new** encounter (revise / new prescription). Do not rewind Atomfeed in this task.

---

## 11. Exact records Operations must create

**REQUIRES OPERATIONS CONFIGURATION** — create later, not now.

### Must create before a new Drug Order can become a sale order

1. **`order.type`**
   - `name` = `Drug Order`
2. **`sale.shop`**
   - `name` = `Pharmacy` (or Hospital EMR label)
   - `payment_default_id` = 1
   - `warehouse_id` = 1
   - `location_id` = 8
   - `pricelist_id` = 1 (recommended)
   - `company_id` = 1 (optional; default)
3. **`order.type.shop.map`** (strongly recommended, not strictly required if a shop exists)
   - `order_type` → Drug Order
   - `shop_id` → that shop
   - `location_name` = NULL (default for any OpenMRS location)
   - `location_id` = 8
   - additional row: `location_name` = `OPD-1`
4. **`syncable.units.mapping`**
   - `name` = **`Tablet`** (this server’s OpenMRS unit; **not** only `Tablet(s)`)
   - `unit_of_measure` = UoM id 1 `Units` (must equal the product’s `uom_id` or quantity is forced to 0)

### Must exist already (do not recreate)

| Record | Status |
|---|---|
| Partner John Adewale `ref=ABC200012` | exists |
| Product Paracetamol 500 mg uuid match | exists |
| Warehouse 1 / location 8 | exist |
| Payment term 1 | exists |
| Pricelist 1 | exists |
| Company 1 Bahmni | exists |

### Later (billing / stock) — not required for a **draft** quotation

5. Product `list_price` (and/or lots with `sale_price`) > 0
6. `stock.quant` at `WH/Stock` for drugs to be dispensed
7. Optional: `Lab Order` / `Radiology Order` types + maps if those feeds should bill
8. Optional: extra unit maps (`Capsule`, `ml`, …) matching **live** OpenMRS names

### Do **not** do as the first configuration step

- Install `bahmni_initializer` blindly — it seeds `location_name=General Ward` and units `Tablet(s)`, which **do not match** this hospital’s OPD-1 / `Tablet` data.
- Create sale orders, invoices, or inventory in this investigation.
- Change OpenMRS, Atomfeed, Docker, roles, or Hospital EMR SPA writes.

---

## 12. Exact fields required

### `order.type`

| Field | Required | Value |
|---|---|---|
| name | **yes** | `Drug Order` |
| description | no | optional |

### `sale.shop`

| Field | Required | Value |
|---|---|---|
| name | **yes** | e.g. `Pharmacy` |
| payment_default_id | **yes** | 1 |
| warehouse_id | **yes in UI** | 1 |
| location_id | **yes in UI** | 8 |
| pricelist_id | no | 1 recommended |
| company_id | no | 1 |
| project_id | no | leave empty |

### `order.type.shop.map`

| Field | Required | Value |
|---|---|---|
| order_type | **yes** | Drug Order record |
| shop_id | **yes** | Pharmacy shop |
| location_name | no | NULL default; `OPD-1` for this clinic |
| location_id | no | 8 |

### `syncable.units.mapping`

| Field | Required | Value |
|---|---|---|
| name | **yes** | OpenMRS `quantityUnits` string, e.g. `Tablet` |
| unit_of_measure | no in model, **yes in practice** | must equal `product.uom_id` (Units / id 1) |

### Draft `sale.order` created by the feed (not created by Operations)

| Field | Set by feed |
|---|---|
| partner_id | partner with `ref` = MRN |
| shop_id | from mapping / first shop |
| warehouse_id | shop warehouse |
| location_id | mapping location |
| payment_term_id | shop payment term |
| pricelist_id | shop pricelist if set |
| origin | `API FEED SYNC` |
| state | `draft` |
| care_setting | `opd` / `ipd` |
| provider_name | encounter provider |
| company_id | hardcoded 1 |

### `sale.order.line`

| Field | Set by feed |
|---|---|
| product_id | `product.product` where uuid = drug uuid |
| product_uom_qty | OpenMRS qty **only if** units mapping matches product UoM; else **0** |
| price_unit | `list_price` (0.00 today) |
| external_order_id | OpenMRS order uuid |
| external_id | encounter uuid |
| dispensed | false for Ordered |
| lot_id | only if quants exist at shop location |

---

## 13. Risks

**CONFIRMED** unless marked UNKNOWN.

1. **Silent success:** missing order type consumes the atomfeed event. ORD-1 will not recreate itself after config.
2. **Initializer mismatch:** `General Ward` vs `OPD-1`; `Tablet(s)` vs `Tablet`. Installing `bahmni_initializer` as-is is the wrong seed for this hospital.
3. **Qty 0 quotations:** without `syncable.units.mapping` for `Tablet`, a draft SO can appear but **cannot be confirmed**.
4. **Zero prices:** `list_price` 0.00 → invoices of 0.00 if confirmed with automation on.
5. **Auto delivery + auto invoice are already True:** the first successful confirm will try to deliver and invoice immediately. With 0 stock that confirm/delivery can fail; with stock it will deduct and invoice in one click.
6. **`convert_dispensed` / `ir.values`:** Dispensed OpenMRS events can crash Odoo 16. Keep prescriptions Ordered until that path is fixed or avoided.
7. **Hardcoded `company_id: 1`:** safe today (only company is Bahmni id 1); breaks if a second company is added.
8. **Odoo 10 leftovers** in `auto_validate_delivery` / `validate_delivery` (`pack_operation_product_ids`).
9. **No Hospital EMR SSO / no browser Odoo writes:** Pharmacy UI must keep reading OpenMRS for the queue. Odoo stock/billing reads later via **server-side** integration only.
10. **Replaying ORD-1:** **UNKNOWN** safe method. Prefer a **new** test prescription after masters exist.
11. **Shop fallback crash:** creating `Drug Order` without any `sale.shop` turns today’s silent ignore into a failed feed.

---

## 14. Recommended configuration sequence

**REQUIRES OPERATIONS CONFIGURATION** — execute only after explicit approval. This task does not perform these steps.

1. Create `order.type` `Drug Order`.
2. Create `sale.shop` Pharmacy with warehouse 1, location 8, payment term 1, pricelist 1.
3. Create `order.type.shop.map`: Drug Order → Pharmacy, `location_name` NULL, `location_id` 8.
4. Add map row `location_name=OPD-1` (same shop / location).
5. Create `syncable.units.mapping` `Tablet` → Units (id 1). Add other live OpenMRS unit names as they appear.
6. **Do not** install `bahmni_initializer` unless its XML is edited to match this hospital.
7. **Do not** change prices or stock yet if the goal is only “does a quotation appear?”.
8. Write a **new** OpenMRS drug order (do not expect ORD-1 to retry). Trace Odoo log + `sale.order` count.
9. Only after a draft SO exists with qty 10: set `list_price` / lots, then receive inventory at WH/Stock, then confirm one order in Odoo and watch picking + invoice.
10. Keep Hospital EMR from posting sale orders or Dispensed flags from the browser. Plan a later **server-side** Odoo read API.

---

## 15. Target architecture (source-backed)

**CONFIRMED** as the correct eventual design for this installation:

```
ABIKAN PHARMACY  (queue UI — OpenMRS reads today)
        │
        ▼
OpenMRS prescription   POST bahmnicore/bahmniencounter  drugOrders[]
        │
        ▼
Atomfeed encounter feed
        │
        ▼
odoo-connect  POST /api/bahmni-saleorder
        │
        ▼
Odoo  order.type + sale.shop + product.uuid
        → sale.order / stock / invoice
        │
        ▼
Hospital EMR reads resulting state via a future **server-side** integration
```

Hospital EMR must **not** create Odoo sale orders from browser JavaScript. Any Odoo access from Hospital EMR must go through a secure backend. That integration is **not** implemented in this task.

---

## What this task did **not** change

No writes to: `order.type`, `sale.shop`, sale orders, invoices, stock, product prices, inventory, Odoo config parameters, OpenMRS, Atomfeed, Docker, databases, roles, or privileges.
