# Pharmacy dispensing, stock, and billing investigation

Status labels:

- **CONFIRMED** — verified from this installation’s Odoo addons, odoo-connect classes, Bahmni Clinical JS, live PostgreSQL / MySQL, or REST
- **UNKNOWN** — cannot currently be confirmed
- **REQUIRES CONTROLLED TEST** — needs an approved write (not done here)
- **REQUIRES OPERATIONS CONFIGURATION** — stock / price / settings work later; not done here
- **ABIKAN FUTURE IMPLEMENTATION** — product work; not implemented in this task

This is investigation only. **S00001 was not confirmed.** No stock, lots, invoices, payments, OpenMRS Dispensed flag, Docker, Atomfeed, Odoo config, or Hospital EMR source were changed.

Related: `docs/PHARMACY_INTEGRATION_INVESTIGATION.md`, `docs/ODOO_PHARMACY_CONFIGURATION.md`.

Date: **16 Aug 2026**.

Live objects used as the reference (left untouched):

| System | Record |
|---|---|
| OpenMRS | ORD-2 `270b6a0d-48d3-430d-b096-01e040b1cb5a` Paracetamol 500 mg × 10 Tablet, Ordered |
| Patient | Tunde Bakare MRN `ABC200006` uuid `c4d470dc-507c-41a2-a5ef-9903a6c4e4a6` |
| Odoo | `sale.order` **S00001** id 1, **draft**, origin `API FEED SYNC`, shop Pharmacy Counter, qty 10 Units, price 0.00, `external_order_id` = ORD-2 uuid |

---

## Architecture (installed)

```
Doctor / Bahmni encounter
        │  POST bahmniencounter  drugOrders[]
        ▼
OpenMRS  orders + drug_order     (clinical Rx source of truth)
        │  optional obs concept "Dispensed" (boolean, orderUuid)
        ▼
Atomfeed  encounter/recent
        ▼
odoo-connect  OpenERPSaleOrderEventWorker
        ▼
Odoo  sale.order draft  (S00001)
        │
        ├── pharmacist confirms in Odoo   ← stock + invoice live here
        │         sale.order.action_confirm
        │              → stock.picking / stock.move
        │              → account.move (if delivery loop succeeds)
        │              → payment is NOT automatic on this server
        │
        └── OpenMRS "Dispensed" checkbox   ← chart flag only
                  → new encounter event
                  → Odoo line.dispensed = true
                  → may auto_validate_delivery (BROKEN on Odoo 16: ir.values)

Hospital EMR Pharmacy today:  OpenMRS reads (queue / Rx / Ordered|Stopped|Dispensed)
Hospital EMR Pharmacy later:  OpenMRS Rx  +  server-side Odoo stock/billing reads
```

Where Hospital EMR should read (see §8):

| Need | Source |
|---|---|
| Patient, MRN, prescription, dose, Ordered/Stopped | **OpenMRS** |
| Chart flag Dispensed | **OpenMRS** obs / `orderAttributes` |
| Stock on hand, lot, expiry | **Odoo** (server-side) |
| Sale order state, qty handed, invoice, payment | **Odoo** (server-side) |

---

## 1. Sale order confirmation

**CONFIRMED** from installed `bahmni_sale/models/sale_order.py` `action_confirm`.

| Item | Value |
|---|---|
| Model | `sale.order` |
| Method | `action_confirm` (overrides standard sale) |
| UI | Odoo Sales → Quotations → Confirm |
| S00001 today | `state=draft`, `invoice_status=no`, `picking_policy=direct` |

### Pre-checks (before `super()`)

For each product line:

1. `product_uom_qty <= 0` → `UserError` (S00001 qty is 10 — passes).
2. `product.tracking == 'lot'` **and** no `lot_id` → `UserError`. Paracetamol **tracking=`none`** — lot **not** required.
3. Duplicate `lot_id` on the same SO → `UserError` (no lot on S00001).
4. `product_uom_qty > lot.product_qty` if a lot is set → `UserError` (no lot).

### State transition

```
draft  →  super().action_confirm(default_immediate_transfer=True)
       →  sale (Odoo 16: state `sale`)
```

Standard Odoo then launches stock rules for **storable** products (`type=product`). That **creates** `stock.picking` (Delivery Orders, type id 2, `reservation_method=at_confirm`) and `stock.move` from shop/warehouse stock location.

Bahmni picking `create` copies `sale.order.location_id` onto the picking (`WH/Stock` id 8 for S00001).

### After `super()`

1. `validate_delivery()` — only if `validate_delivery_when_order_confirmed` = `'1'`. **Live value: 0.** This Odoo **10** path (`pack_operation_product_ids`, `do_new_transfer`, `stock.production.lot`) is **skipped**.
2. If `bahmni_sale.is_delivery_automated` (**live: True**) and `picking_ids` exist:
   - set `immediate_transfer`
   - `move.quantity_done = product_uom_qty`
   - `picking._action_done()`
3. If `bahmni_sale.is_invoice_automated` (**live: True**):
   - `_create_invoices()` then `invoice.action_post()`
   - open Payments window **only** if the user is in `bahmni_sale.group_redirect_to_payments_on_sale_confirm`
   - **Live: that group has zero users.** Confirm does **not** open or register payment.

### What confirmation does **not** do

**CONFIRMED**

- Does not write OpenMRS. ORD-2 stays Ordered.
- Does not set `sale.order.line.dispensed`.
- Does not require payment first (`require_payment=false` on S00001).
- Does not call POS.

`auto_validate_delivery()` is a **different** method used only when an Atomfeed event arrives with `dispensed='true'` **and** `convert_dispensed` is on. It is not used when a human confirms S00001.

---

## 2. Stock requirements (Paracetamol 500 mg)

**CONFIRMED** live product id 110:

| Need | Live |
|---|---|
| Product type | `product` (storable) |
| `sale_ok` | true |
| UoM | Units (id 1) — mapped from OpenMRS `Tablet` |
| Tracking | `none` |
| Warehouse | 1 My Company / WH |
| Pharmacy location | `sale.shop.location_id` = 8 `WH/Stock` |
| `stock.quant` for product 110 | **0** |
| `stock.lot` | **0** |
| `allow_negative_stock` | **0** |

**REQUIRES OPERATIONS CONFIGURATION** before a **successful** confirm/delivery: receive at least 10 Units of product 110 into `WH/Stock`.

### If S00001 is confirmed while stock is zero

**CONFIRMED from code path, exact exception UNKNOWN:**

1. Pre-checks pass (qty 10, tracking none).
2. `super().action_confirm()` **will try to create** a delivery picking and reserve. With 0 quants, reservation will not become fully assigned (`reservation_method=at_confirm`).
3. `is_delivery_automated=True` then forces `quantity_done=10` and `_action_done()`.
4. Odoo 16 will not complete a delivery from an empty location when negative stock is not allowed.

**REQUIRES CONTROLLED TEST:** whether that `UserError` rolls back the whole `action_confirm` (S00001 stays **draft**, no picking persisted) or leaves `state=sale` with a failed/unvalidated picking.

Until that test, treat “confirm with zero stock” as **unsafe for a success path**, and **possibly** safe as a failed transaction — do not assume rollback.

---

## 3. Batch / lot

**CONFIRMED**

| Question | Answer |
|---|---|
| Mandatory on confirm? | **Only if** `product.tracking == 'lot'` (or serial). Paracetamol is `none`. |
| Feed warning “No batch/lot for product 110”? | Informational. Feed still created the line **without** `lot_id`. |
| Auto-select on feed? | Yes, if `stock.quant` qty > 0 at shop location. Sorted by `expiration_date` (**FEFO**). Expired lots skipped. |
| Pharmacist select? | Yes, on the quotation line (`lot_id`) when lots exist. Onchange copies expiry and optional lot `sale_price`. |
| Expiry required? | No. Lots without `expiration_date` are still eligible in the feed helper. |
| `allocate_quantity_from_multiple_batches` | True — splits lines across lots when stock exists; unused today. |

Odoo 10 `validate_delivery._find_batch` also sorts by `life_date` FEFO, but that method is **not** run (`validate_delivery_when_order_confirmed=0`).

**Do not create a lot for this investigation.** Lots become relevant if Operations later sets tracking to `lot`.

---

## 4. What “dispensing” means here

**CONFIRMED:** two different meanings. They are **not** wired together on this Odoo 16 stack.

### A. Operational dispense (stock out + bill) — **Odoo**

Pharmacist confirms the **draft sale order**. That is the installed stock/billing action. There is no separate `dispense` model.

### B. Chart flag “Dispensed” — **OpenMRS**

Bahmni Clinical Treatment tab, gated by privilege **`bahmni:clinical:dispense`**.

Config: `GET /bahmnicore/config/drugOrders` → `orderAttributes[]` one row:

| Field | Value |
|---|---|
| name | `Dispensed` |
| uuid | `d609e1fb-5e07-11ef-8f7c-0242ac120002` |
| dataType | Boolean |
| shortName | `D` |

Write: `DrugOrder.getOrderAttributesAsObs()` posts an **observation** `{ value: true/false, orderUuid, concept.uuid }` on the next `POST bahmniencounter`. It is **not** stored in `order_attribute` (`order_attribute` = 0 rows, `order_attribute_type` empty).

OpenMRS `orders.order_action` stays **NEW**. There is no core order state named Dispensed.

Hospital EMR already maps REST `orderAttributes` name Dispensed → UI status **Dispensed**.

odoo-connect: if an encounter observation named `Dispensed` (ignore case) has boolean true and `orderUuid` = the drug order, payload `dispensed='true'`. Odoo then sets `sale.order.line.dispensed` and, if `convert_dispensed`, calls `auto_validate_delivery()`.

**CONFIRMED broken on this DB:** `convert_dispensed` is read from **`ir.values`**, which **does not exist**. A Dispensed feed event is expected to **exception** (JSON 417 / failed atomfeed). `auto_register_invoice_payment_for_dispensed` is **0**.

So:

| Action | Marks OpenMRS Dispensed? | Moves stock? |
|---|---|---|
| Confirm S00001 in Odoo | **No** | Intended yes |
| Clinical “D” checkbox | **Yes** (obs) | Intended via feed; **currently would crash Odoo** |

**UNKNOWN:** exact Clinical HTML control binding (minified JS exposes `dispensePrivilege` and `orderAttributes[].value`; template not extracted here).

Payment is **not** required before either path.

---

## 5. Partial dispensing

**CONFIRMED:** no first-class partial qty on OpenMRS.

| Layer | Behaviour |
|---|---|
| OpenMRS Dispensed | Boolean only. 5 of 10 is not representable. |
| `drug_order.quantity` | Prescribed qty (10). No “qty dispensed” column used. |
| Odoo draft line | Pharmacist **could** edit `product_uom_qty` to 5 before confirm. That is an Odoo-only change; ORD-2 still says 10 Tablet Ordered. |
| Remaining OpenMRS qty | **None** as a field. |
| Subsequent dispense | Second OpenMRS Dispensed event would set `dispensed=true` on the existing line if it was false; it does not add a “remaining 5”. |
| Stock / billing | Only whatever qty is on the Odoo line at confirm. |

Hospital EMR’s “Partially dispensed” chip is already documented as **not** a backend status.

**UNKNOWN / not a supported workflow:** splitting one OpenMRS order across two Odoo deliveries.

---

## 6. Billing

**CONFIRMED** intended path when confirm **succeeds**:

```
draft SO
  → action_confirm
  → picking + (automated) delivery
  → _create_invoices  (because is_invoice_automated=True)
  → account.move.action_post()
  → payment NOT automatic
```

| Item | Live |
|---|---|
| Invoice model | `account.move` `out_invoice` |
| Trigger | End of `sale.order.action_confirm` if `bahmni_sale.is_invoice_automated` |
| Amount | SO line `price_unit` × qty (S00001 = **0.00**) |
| Price source | Product `list_price` (0.00); pricelist/lot only when lots exist |
| Tax | Line has **Tax 15%** (id 1); tax amount is **0.00** because price is 0 |
| Invoice policy | Product `invoice_policy=order` — ordered qty is invoiceable after confirm, not waiting on delivery qty |
| Payment method | Cash journal id 6 exists; **not** used on confirm |
| Payment status | None until someone registers payment |
| Payment before dispense? | **No** |

`validate_payment()` (invoice wizard + cash `account.payment.post`) runs only on the **Dispensed Atomfeed** path when `auto_register_invoice_payment_for_dispensed=1`. Live **0**, and that path currently crashes earlier on `ir.values`.

If automated delivery **raises**, `_create_invoices` in the same method **does not run**. Then either full rollback (**UNKNOWN**) or sale without invoice (**UNKNOWN**).

No NHIA / insurance addon.

---

## 7. Patient ↔ customer mapping

**CONFIRMED** Tunde Bakare:

| OpenMRS | Odoo `res.partner` id 11 |
|---|---|
| Name | Tunde Bakare |
| MRN | `ABC200006` = `res.partner.ref` (feed `customer_id`) |
| Patient uuid | `c4d470dc-507c-41a2-a5ef-9903a6c4e4a6` = `res.partner.uuid` |

Future pharmacy transactions identify the customer by **MRN** on the sale-order feed, and by `partner_id` on S00001. Do not change this mapping.

---

## 8. What Hospital EMR should read later

**ABIKAN FUTURE IMPLEMENTATION** — do not implement now. No Odoo credentials in the browser.

### OpenMRS (already usable)

- Patient identity, allergies
- Active prescriptions (`/bahmnicore/drugOrders/active`)
- Dose / route / frequency / qty / Ordered vs Stopped
- Chart Dispensed flag (`orderAttributes`)

### Odoo (server-side proxy later)

- `qty_available` at Pharmacy Counter location
- Lots / expiry if tracking is enabled
- `sale.order` state, line qty, price, `external_order_id`
- Invoice (`account.move`) and payment state

### Writes later (not now)

- Do **not** create sale orders from Hospital EMR JS.
- Do **not** POST OpenMRS Dispensed from the browser until the Odoo `ir.values` crash is resolved.
- Preferred operational dispense: confirm/adjust the Odoo SO via a **backend** using a service account; optionally then set OpenMRS Dispensed for the chart.

---

## 9. Controlled test plan for S00001

**Not executed.** Needs explicit approval.

### A. What happens if S00001 is confirmed **now** (stock = 0)

**CONFIRMED intent:** pre-checks pass → create delivery picking → force `_action_done` of 10 Units from empty `WH/Stock`.

**REQUIRES CONTROLLED TEST:** exact error and whether S00001 remains draft.

### B. Records that would be created **if** confirm fully succeeded

| Model | Likely |
|---|---|
| `stock.picking` | Delivery from WH/Stock |
| `stock.move` / `stock.move.line` | 10 Units product 110 |
| `stock.quant` | would go negative or fail — **fail expected** |
| `account.move` | posted customer invoice **0.00** (only if delivery block does not raise) |
| `account.payment` | **none** |

### C. Data that may change

S00001 `state` draft→sale; `invoice_status`; chatter. **ORD-2 would not change.**

### D. Rollback (only if something persisted)

Do **not** run unless a test actually writes:

1. If invoice posted: reverse / credit note (do not delete accounting casually).
2. Cancel/unreserve picking if still not `done`.
3. Cancel sale order if Odoo allows from that state.
4. Never delete partner, product, shop, or ORD-2.

If the confirm **raises inside one transaction**, rollback is automatic — re-read counts.

### E. Must stock exist first?

**For a successful delivery: yes.** Receive ≥ 10 Units of product 110 at location 8 first.

**For a failure-mode test: no**, but that is a different test.

### F. Invoice / payment on confirm?

Invoice **attempted** after delivery automation (`is_invoice_automated=True`). Payment **not** automatic.

### G. Would it alter ORD-2?

**CONFIRMED no.**

### Recommended next test (after approval)

1. **Do not** confirm S00001 on empty stock if the goal is a clean success.
2. Operations: inventory receipt of Paracetamol 500 mg × ≥10 at `WH/Stock` (do not change `list_price` unless billing is in scope).
3. Confirm **only S00001**.
4. Verify picking, quant movement, invoice 0.00, ORD-2 still Ordered, no payment.
5. Still do **not** set OpenMRS Dispensed (Odoo 16 crash risk).

---

## Status tables

### CONFIRMED

- S00001 is the ORD-2 quotation; left draft.
- Confirm = `sale.order.action_confirm` with automated delivery + automated invoice post.
- Paracetamol tracking none → lot not required.
- Stock at WH/Stock is 0.
- OpenMRS Dispensed is a boolean obs, privilege `bahmni:clinical:dispense`.
- Odoo confirm does not mark OpenMRS Dispensed.
- Dispensed Atomfeed path reads missing `ir.values`.
- Patient map is `ref=MRN` + `uuid`.
- Price 0.00; tax 15% currently 0.
- No payment on confirm.

### UNKNOWN

- Exact UserError / rollback if confirm with 0 stock.
- Whether Odoo 16 `_action_done` can ever complete with 0 qty reserved.
- Clinical template widget for the D checkbox (JS contract is confirmed).
- Whether POS is an alternate outpatient counter (0 POS orders).

### REQUIRES CONTROLLED TEST

- Confirm S00001 after stock receipt.
- Optional: confirm-with-zero-stock failure mode.
- OpenMRS Dispensed feed **after** `convert_dispensed` is fixed — not before.

### REQUIRES OPERATIONS CONFIGURATION

- Inventory at `WH/Stock` for product 110.
- Real `list_price` / lot `sale_price` before meaningful invoices.
- Do not install `bahmni_initializer` as a substitute for that.
- Fix or avoid `ir.values` / `convert_dispensed` before using the Dispensed checkbox.

### ABIKAN FUTURE IMPLEMENTATION

- Server-side Odoo stock/billing read API.
- Pharmacist confirm/dispense through that API, not browser Odoo login.
- Do not treat “Partially dispensed” as OpenMRS truth.

---

## What this task did not change

No confirm of S00001. No stock, lots, invoices, payments, OpenMRS order updates, Odoo/OpenMRS/Docker/Atomfeed/Hospital EMR source changes.
