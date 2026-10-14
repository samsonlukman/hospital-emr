# Pharmacy billing → payment → dispensing workflow

Investigation only. **16 Aug 2026.**

Status labels used throughout:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Verified from installed Odoo addons, odoo-connect, Bahmni Clinical, live PostgreSQL / MySQL, or REST |
| **UNKNOWN** | Cannot currently be confirmed from source or live data |
| **NOT SUPPORTED** | Installed source has no first-class path |
| **REQUIRES OPERATIONS CONFIGURATION** | Settings / masters / currency work later; not done here |
| **REQUIRES CONTROLLED TEST** | Needs an approved write; **not executed** |
| **ABIKAN FUTURE IMPLEMENTATION** | Product work; not implemented in this task |

Related:

- `docs/PHARMACY_INTEGRATION_INVESTIGATION.md` — Atomfeed → sale order
- `docs/PHARMACY_DISPENSING_BILLING_INVESTIGATION.md` — confirm / stock / Dispensed flag
- `docs/PHARMACY_PURCHASING_STOCK_INVESTIGATION.md` — purchase / WH/Stock
- `docs/ODOO_PHARMACY_CONFIGURATION.md` — shops / order types
- `docs/NEW_DRUG_CATALOGUE_WORKFLOW.md` — drug UUID ownership

**No writes were performed.** S00001 was not confirmed. ORD-1 and ORD-2 were not dispensed. No invoices, payments, stock moves, currency changes, role changes, Atomfeed, Docker, or Hospital EMR UI changes.

---

## Protected live objects (untouched)

| System | Record | Must remain |
|---|---|---|
| OpenMRS | ORD-1 John Adewale, Paracetamol 500 mg, NEW / Ordered | Unchanged |
| OpenMRS | ORD-2 Tunde Bakare uuid `270b6a0d-48d3-430d-b096-01e040b1cb5a`, Paracetamol 500 mg × 10 Tablet, Ordered | Unchanged |
| Odoo | `sale.order` **S00001** id 1, **draft**, origin `API FEED SYNC`, partner 11 Tunde Bakare, product 110 qty 10, price 0.00 | **Do not confirm** |
| Odoo | Product **2385** Paracetamol 500 mg — TEST, `list_price=1000`, `standard_price=400`, WH/Stock id 8 **100 Units** reserved 0 | **Do not consume** |
| Odoo | Supplier 18 Hospital EMR TEST Pharma Supplier; PO **P00001**; receipt **WH/IN/00001** | Unchanged |
| Odoo | Company currency **USD** id 2 | **Do not change** |

Live counts at investigation time: `account.move` = 0, `account.payment` = 0, `pos_order` = 0.

---

## Hospital intended vs installed (summary)

Hospital intends:

```
Doctor prescribes
    → Patient bill
    → Accountant collects payment
    → Receipt
    → Patient goes to Pharmacy
    → Pharmacist verifies payment
    → Dispense
    → Stock decreases
    → Prescription marked
```

Installed Bahmni/Odoo actually does:

```
OpenMRS Drug Order
    → Atomfeed
    → odoo-connect OpenERPSaleOrderEventWorker
    → POST /api/bahmni-saleorder  (emrsync)
    → order.save.service.create_orders
    → draft sale.order  origin='API FEED SYNC'     ← charge preview, NOT a posted bill
    → human Confirm in Odoo Sales
         ├── delivery _action_done   (stock out)     if bahmni_sale.is_delivery_automated=True
         └── account.move posted     (invoice)       if bahmni_sale.is_invoice_automated=True
    → payment is NOT automatic
    → OpenMRS Dispensed obs is a SEPARATE, currently unsafe, chart flag
```

**CONFIRMED gap:** the installed confirm path invoices **and** deducts stock in one click, **without requiring payment**. There is no “UNPAID → cannot dispense” gate.

---

## 1. Prescription → Sale Order

**CONFIRMED**

Pipeline (already proven with ORD-2 → S00001):

```
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter  drugOrders[]
  → OpenMRS orders + drug_order
  → Atomfeed /openmrs/ws/atomfeed/encounter/recent
  → odoo-connect OpenERPSaleOrderEventWorker
  → POST /api/bahmni-saleorder
  → api.event.worker.process_event  category=create.sale.order
  → order.save.service.create_orders
  → sale.order draft, origin='API FEED SYNC'
```

Join keys:

| Need | Field |
|---|---|
| Patient | Feed `customer_id` = MRN = `res.partner.ref`. Also `res.partner.uuid` = OpenMRS patient uuid |
| Product | `product.product.uuid` = OpenMRS drug uuid |
| Prescription line | `sale.order.line.external_order_id` = OpenMRS order uuid |
| Encounter | `sale.order.line.external_id` = OpenMRS encounter uuid |
| Shop | `order.type` “Drug Order” id 1 → `sale.shop` “Pharmacy Counter” id 1 → location 8 WH/Stock |

ORD-1 (John Adewale, partner 17 `ABC200012`) has **no** Odoo sale order: the first feed was ignored because `order.type` did not exist yet; the Atomfeed marker was consumed. **Do not rewind Atomfeed.**

OpenMRS prescription contains **no price**.

Line price on create (`_create_sale_order_line_function`):

1. `price_unit = product.list_price`
2. If a lot is allocated **and** `bahmni_sale.sale_price_markup=True`, may use `lot.sale_price` when > 0
3. Else, if the SO has a pricelist, `_get_display_price()` may replace `price_unit`

Live: pricelist **1 Public Pricelist**, **0 pricelist items** → price is product `list_price`. S00001 uses pricelist 1, shop 1, payment term 1. Product 110 `list_price=0.00` → S00001 amount 0.00. TEST product 2385 `list_price=1000` (USD, not naira).

Quantity: OpenMRS `quantity` + `quantityUnits` through `syncable.units.mapping`. Live mapping: **Tablet → Units**. Mismatch → qty 0 (logged warning).

---

## 2. Patient billing

**CONFIRMED**

| Question | Answer |
|---|---|
| Is the sale order itself the patient bill? | **No.** Draft `sale.order` is a **quotation / charge preview**. Posted patient bill is `account.move` with `move_type=out_invoice`. |
| Is a separate invoice created? | **Yes**, on confirm, because `bahmni_sale.is_invoice_automated=True`. `_create_invoices()` then `invoice.action_post()`. |
| When is the invoice created? | Inside `sale.order.action_confirm` after delivery automation. |
| Does the invoice come from sale order confirmation? | **Yes.** |
| Can an invoice exist while the SO remains draft? | **Not via this installed path.** Live `account.move` count = 0. S00001 `invoice_status=no`. Standard Odoo invoices confirmed orders (`invoice_policy=order` on products 110 and 2385). |
| Which model is the patient bill? | Intended: posted `account.move` (`out_invoice`). Until confirm: draft `sale.order` is the only charge document. |
| Which model is the invoice? | `account.move` |
| How is the patient identified? | `sale.order.partner_id` / `account.move.partner_id` = `res.partner` |
| How is MRN linked? | `res.partner.ref` = OpenMRS identifier (e.g. Tunde `ABC200006`, John `ABC200012`) |
| How are lines priced? | Odoo `product.list_price` (and pricelist / lot markup as above). OpenMRS has no price. |
| Is pricelist involved? | Shop copies pricelist 1 onto the SO. No extra items. Effectively list price. |
| Multiple prescriptions on one bill? | See §14. |
| Consultation fees + pharmacy on same bill? | See below. |

**NOT SUPPORTED today (configuration):** combining consultation fees and pharmacy items on one bill. Live `order.type` has **only** “Drug Order”. Lab / radiology / procedure order types are not mapped. Service products exist (1843) but are not driven by the Drug Order shop map.

Bahmni sale order also computes `prev_outstanding_balance` / `total_outstanding_balance` from `account.move.amount_residual_signed` for the partner. With zero invoices, that is 0.

**ABIKAN FUTURE IMPLEMENTATION:** Hospital EMR Accounting UI should display Odoo charges; it must not invent a second ledger.

---

## 3. Accountant workflow

**CONFIRMED** existing UI (Odoo, not Hospital EMR):

| Need | Where |
|---|---|
| Find a patient | Odoo Sales → Quotations / Customers; partner `ref` = MRN |
| See outstanding charges | Draft `sale.order` (quotation) **or**, after confirm, unpaid `account.move` residual. Sale form also shows computed outstanding from posted invoices. |
| Review prescription charges | Sale order lines (`name` includes product + OpenMRS qty + unit; `external_order_id` is the Rx uuid) |
| Generate / finalize a bill | Confirm quotation → automated posted invoice (`is_invoice_automated=True`) |
| Receive payment | Odoo Invoicing → Customers → Invoices → Register Payment (`account.payment.register` / `account.payment`). Confirm does **not** register payment. Group `bahmni_sale.group_redirect_to_payments_on_sale_confirm` has **0 users**. `auto_register_invoice_payment_for_dispensed=0`. |
| Produce a receipt | Print `account.report_payment_receipt` or Bahmni `bahmni_auto_payment_reconciliation.report_payment_invoice` (“Receipt”) on `account.payment` |

Odoo top-level menus that exist: Invoicing, Inventory, Purchase, Point of Sale, Sales, Bahmni.

POS config **Shop** id 1 exists with tenders Cash / Bank / Customer Account. **0 POS orders.** Atomfeed does **not** create POS tickets. POS is **not** the current outpatient pharmacy path.

Hospital EMR today:

- Pharmacy workspace reads **OpenMRS** queue only (`fetchPharmacyQueue`).
- Pharmacy “Billing” card is **ComingSoon** (“Invoice later”).
- Reception nav: Payments and Receipts are **soon**. There is **no** dedicated Accounting workspace.

**ABIKAN FUTURE IMPLEMENTATION:** hospital-friendly accountant screens over **server-side** Odoo APIs. Do not put Odoo credentials in browser JavaScript.

---

## 4. Invoice

**CONFIRMED**

| Item | Value |
|---|---|
| Model | `account.move` `move_type=out_invoice` |
| Created by | `sale.order._create_invoices` from confirm when `bahmni_sale.is_invoice_automated=True` |
| Posted by | `invoice.action_post()` in the same `_create_invoices` when that flag is True |
| Journal | Customer Invoices, code **INV**, id 1 |
| Origin | `invoice_origin` = sale order name (e.g. S00001); extra `order_id` on the Bahmni invoice vals |
| Currency | Pricelist currency = company **USD** |
| Tax | Tax 15% exists. S00001 tax amount is 0 because price is 0. TEST product 1000 would compute tax **if** the product/taxes_id applies — **REQUIRES CONTROLLED TEST** for the exact tax line on a TEST invoice |
| Paid? | `payment_state` / residual. No live invoices. Standard Odoo: `paid` when residual is 0 after reconciliation |

**UNKNOWN:** exact `payment_state` string (`paid` vs `in_payment`) for a cash register payment on this Odoo 16 build — standard behaviour, not live-tested.

---

## 5. Payment

**CONFIRMED** models (unused live):

| Model | Role |
|---|---|
| `account.payment` | Customer inbound payment |
| `account.payment.register` | Register Payment wizard |
| `account.payment.method` | Manual inbound / outbound only |
| `account.journal` type cash/bank | Cash **CSH1** id 6; Bank **BNK1** id 7 |
| `pos.payment` / `pos.order` | Unused (count 0) |

What makes an invoice paid: reconciling an inbound `account.payment` (or equivalent credit) against the invoice so residual is 0.

| Question | Answer |
|---|---|
| Is payment registered against the invoice? | **Intended yes** (standard Odoo reconcile). Not observed live. |
| Partial payment? | Standard Odoo **yes**. **REQUIRES CONTROLLED TEST**. |
| One payment covering multiple invoices? | Standard Odoo payment register **can**. **REQUIRES CONTROLLED TEST**. |
| Invoice cancel / refund? | Standard credit note (`out_refund`) / cancel if allowed. **REQUIRES CONTROLLED TEST**. No live refunds. |
| Payment reverse? | Standard Odoo payment cancel / reverse. **REQUIRES CONTROLLED TEST**. |
| Receipt automatic? | Printing is not automatic. Reports exist on `account.payment`. Confirm does not create a payment, so no receipt is generated by confirm. |
| Where is receipt information stored? | `account.payment` (`name`, `date`, `amount`, `journal_id`, `partner_id`, `create_uid`) plus reconciled `account.move` lines. |

`validate_payment()` on `sale.order` (Bahmni) would create a **cash** journal payment after invoicing. It is used only on the **Dispensed-feed auto-convert** path, which is **broken** (`ir.values` missing) and has `auto_register_invoice_payment_for_dispensed=0`. Do not rely on it.

Online payment providers (Stripe, PayPal, Flutterwave, …) are all **disabled**.

---

## 6. Receipt

**CONFIRMED** printable reports (never printed in this investigation):

| Report | Model | XML id / name |
|---|---|---|
| Invoices (with payments) | `account.move` | `account.report_invoice_with_payments` |
| Invoices without Payment | `account.move` | `account.report_invoice` |
| Payment Receipt | `account.payment` | `account.report_payment_receipt` |
| Bahmni **Receipt** | `account.payment` | `bahmni_auto_payment_reconciliation.report_payment_invoice` |
| Receipt Summary | `account.payment` | `bahmni_auto_payment_reconciliation.report_payment_summary` |
| PRO-FORMA Invoice | `sale.order` | `sale.report_saleorder_pro_forma` |

Bahmni Receipt template fields (from installed XML):

| Field | Source |
|---|---|
| Receipt / bill number | `account.payment.name` (sequence, e.g. typical `PAY/…`) |
| Patient name | `partner_id.name` |
| ID (MRN) | `partner_id.ref` |
| Date | `account.payment.date` |
| Net / paid / outstanding | computed `get_invoice_amount_details_for_print()` |
| Create timestamp | `create_date` |
| Consultant | label exists in the template; **UNKNOWN** whether it is populated from `sale.order.provider_name` on this build |

Invoice number (`account.move.name`, typically `INV/…`) is **distinct** from payment receipt number (`account.payment.name`).

**NOT SUPPORTED / not found:** QR code or dedicated pharmacy verification barcode on the receipt template (no `qr` / `qrcode` in the Bahmni receipt XML).

**UNKNOWN:** whether Operations will later add a QR. A unique verification reference **already exists** as the payment `name` plus invoice `name` plus `sale.order.line.external_order_id`.

Accountant / user: `create_uid` / `user_id` on the payment and invoice. Not shown as a dedicated “cashier” field on the Bahmni receipt XML excerpt.

---

## 7. Payment verification (Pharmacy)

**CONFIRMED** reliable relationship **after** invoice + payment exist:

```
OpenMRS patient uuid / MRN
    → res.partner.uuid / res.partner.ref
    → sale.order (partner_id, origin API FEED SYNC)
    → sale.order.line.external_order_id = OpenMRS drug order uuid
    → account.move (invoice_origin / invoice_ids / order_id)
    → account.payment (reconciled to that invoice)
```

Identifiers Pharmacy can use:

| Identifier | Exists today | Enough to prove “PAID”? |
|---|---|---|
| MRN | Yes (`res.partner.ref`) | No — only identifies the patient |
| OpenMRS drug order UUID | Yes (`external_order_id` on S00001 line = ORD-2 uuid) | No until invoice is paid |
| Odoo SO id / name | Yes (S00001 / id 1) | No — draft is unpaid |
| Invoice id / number | **None live** | Yes, once `payment_state` is paid |
| Payment id / name | **None live** | Yes, once reconciled |
| Receipt number | Payment `name` | Yes, as a human token pointing at `account.payment` |
| Partner id | Yes (11 / 17) | No |

**NOT SUPPORTED:** an installed “this prescription is paid” flag on OpenMRS or on the sale order. `require_payment=false` on S00001. Confirm does not check invoices.

**ABIKAN FUTURE IMPLEMENTATION:** server-side read:

`order uuid → sale.order.line → invoice → payment_state in (paid, in_payment)`

Display **PAID / READY TO DISPENSE** only from that read. Browser JS must not log into Odoo.

---

## 8. Pharmacy queue

**CONFIRMED**

Hospital EMR Pharmacy Desk today: OpenMRS active drug orders (`fetchPharmacyQueue`). Status from OpenMRS order / `orderAttributes` Dispensed.

Odoo Sales → Quotations is the operational “to bill / to confirm” queue.

**NOT SUPPORTED** in Hospital EMR today: paid/unpaid column, payment verification, stock column.

**ABIKAN FUTURE IMPLEMENTATION:** Pharmacy queue = OpenMRS Rx list **joined** (server-side) to Odoo SO / invoice / payment_state / `stock.quant`. Do not rebuild Odoo.

---

## 9. Dispensing

**CONFIRMED:** two different operations. They are **not** the same and are **not** linked on this stack.

### A. Operational dispense (stock + bill) — Odoo

Pharmacist / salesperson **confirms** the draft sale order.

`bahmni_sale` `sale.order.action_confirm`:

1. Pre-checks (qty > 0; lot only if `tracking=lot`)
2. `super().action_confirm(default_immediate_transfer=True)` → state `sale`, creates delivery picking
3. If `is_delivery_automated=True` (**live True**): force `quantity_done` and `picking._action_done()` → **stock decreases here**
4. If `is_invoice_automated=True` (**live True**): create and **post** invoice
5. Payment **not** created
6. OpenMRS **not** written
7. `sale.order.line.dispensed` **not** set by confirm

There is no separate `dispense` model.

### B. Chart flag “Dispensed” — OpenMRS

Privilege `bahmni:clinical:dispense` (on Privilege Level Full/High and SuperAdmin).

Concept uuid `d609e1fb-5e07-11ef-8f7c-0242ac120002`, boolean, short name `D`. Stored as an **observation** with `orderUuid`, **not** `order_attribute` (table empty).

odoo-connect maps that obs to feed `dispensed='true'`, then Odoo sets `line.dispensed=true` and, if `convert_dispensed`, calls `auto_validate_delivery()`.

**CONFIRMED broken:** `convert_dispensed` is read from **`ir.values`**, which **does not exist on Odoo 16**. A Dispensed feed event is expected to **exception**. Do not set OpenMRS Dispensed until that is fixed.

| Action | Marks OpenMRS Dispensed? | Moves stock? | Creates invoice? | Requires payment? |
|---|---|---|---|---|
| Confirm sale order | No | Yes (if delivery automation succeeds) | Yes (if invoice automation succeeds) | **No** |
| Clinical “D” checkbox | Yes (obs) | Intended via feed; **would crash Odoo** | Only if broken convert path were fixed **and** auto payment flag on | **No** |

Bahmni Clinical dispensing UI is the Treatment tab “D” flag, not a dedicated pharmacy counter app.

---

## 10. Stock deduction

**CONFIRMED** when stock **would** decrease:

| Event | Decreases stock? |
|---|---|
| Sale order creation (draft) | **No** |
| Sale order confirmation + `is_delivery_automated=True` + `picking._action_done()` | **Yes** — this is the live path |
| Delivery created but not validated | **No** (reservation possible; live `is_delivery_automated` skips waiting) |
| Invoice create / post | **No** |
| Payment | **No** |
| OpenMRS Dispensed obs | **No** (and currently unsafe) |

For TEST product 2385, **100 Units** at location 8: confirming a sale order for qty N of product 2385, with automated delivery succeeding, would reduce that quant to `100 − N`. **Not done here.**

`allow_negative_stock=0`. Confirming **S00001** (product 110, **0** stock) is expected to **fail** delivery. Do not confirm it.

`validate_delivery_when_order_confirmed=0` (legacy Odoo 10 pack-operation path skipped).

---

## 11. OpenMRS Dispensed state

**CONFIRMED**

- Boolean observation only.
- `orders.order_action` stays **NEW**.
- Hospital EMR already maps REST `orderAttributes` name Dispensed → UI **Dispensed**.
- Confirming Odoo does **not** set it.
- Setting it from Clinical would currently **break** the Odoo Dispensed feed worker.

**NOT SUPPORTED:** automatic OpenMRS Dispensed after Odoo stock out.

**ABIKAN FUTURE IMPLEMENTATION:** optionally write the obs **after** (1) `ir.values` / `convert_dispensed` is fixed or bypassed, and (2) Odoo delivery is done. Until then, treat OpenMRS Dispensed as a **chart flag to avoid**.

---

## 12. Partial dispensing

**CONFIRMED:** not a first-class workflow.

| Layer | Behaviour |
|---|---|
| OpenMRS Dispensed | Boolean. Cannot represent 5 of 10. |
| `drug_order.quantity` | Prescribed qty only. No qty-dispensed column in use. |
| Odoo draft line | A user **could** edit `product_uom_qty` before confirm. OpenMRS still says 10 Ordered. |
| Odoo picking / backorder | Standard Odoo supports partial delivery **if** delivery is not auto-completed. Live `is_delivery_automated=True` forces full `quantity_done = product_uom_qty`. |
| Partial invoice / payment | Standard Odoo possible after an invoice exists. Does not split the OpenMRS order. |

**NOT SUPPORTED:** “dispense 5, leave 5 Ordered” as a linked OpenMRS+Odoo operation.

**REQUIRES OPERATIONS CONFIGURATION** later if the hospital needs backorders: turn **off** `is_delivery_automated` and use Odoo partial picking. Still would not update OpenMRS qty.

---

## 13. Multiple drugs in one prescription

**CONFIRMED** from `order.save.service.create_orders`:

Feed groups lines by OpenMRS `type`. All **Drug Order** lines in one encounter go to **one** shop (Pharmacy Counter) and **one** sale order (create or append).

So Paracetamol + Amoxicillin + Artemether/Lumefantrine in **one encounter** → **one** `sale.order` with **three** lines (if all products exist and units map).

Accountant then sees **one** quotation / (after confirm) **one** invoice for that SO.

**REQUIRES CONTROLLED TEST** with the three TEST products to prove live tax/qty. Not executed.

If a drug’s OpenMRS unit has no `syncable.units.mapping` matching product UoM (e.g. Amoxicillin form Oral capsule vs mapping Tablet→Units only), that line may be created with **qty 0** and later **block confirm** (`product_uom_qty <= 0`).

---

## 14. Multiple prescriptions for one patient

**CONFIRMED** from the same `create_orders` search:

```
sale.order.search(partner_id, shop_id, state='draft', origin='API FEED SYNC')
```

If a matching **draft** exists → **append lines** to that SO (updates `care_setting` / `provider_name` to the latest encounter).

If none → **new** draft SO.

Therefore:

| Situation | Billing document |
|---|---|
| Same visit, multiple drugs | One SO |
| Later visit **while draft SO still open** | **Combined** onto that draft (even different doctor) |
| Later visit **after** SO is confirmed (`state=sale`) | **New** draft SO → billed separately |
| Pay separately | Only after they are separate invoices. Combined draft = one bill if confirmed together |

**UNKNOWN / REQUIRES CONTROLLED TEST:** if two draft SOs somehow exist for the same partner+shop, the code updates **all** in the search then `break`s after the first — first match wins for processing, but the `for order in sale_order_ids` writes provider onto each before breaking on the inner flow… actually it processes the first then breaks. Extra drafts would be leftover. Not observed live (only S00001).

John Adewale has **no** SO despite ORD-1 (feed ignored). A **new** prescription for John would create a **new** draft SO; it would **not** backfill ORD-1.

---

## 15. Cancellation / refund

**CONFIRMED** capabilities in source / standard Odoo; **none live-tested**.

| Event | Installed behaviour |
|---|---|
| Cancelled / discontinued OpenMRS order | Feed `voided` or `action=DISCONTINUE` → `_delete_sale_order_line` **only if the SO is still draft** |
| Revised OpenMRS order | `REVISE` updates the draft line |
| Cancel draft sale order | Standard Odoo cancel / unlink empty orders on dispensed-unlink path |
| Cancel confirmed SO | Standard Odoo; blocked or needs invoice handling once posted |
| Cancel posted invoice | Credit note / reverse. No live invoices |
| Refund payment | Reverse / credit. No live payments |
| Returned medication / stock return | Standard `stock.picking` return from a **done** delivery. No done pharmacy deliveries except purchase receipt WH/IN/00001 (**do not reverse that**) |

**NOT SUPPORTED as a hospital “return to pharmacy after pay” product flow** until designed: would be Odoo credit note + stock return + optional OpenMRS discontinue. **Do not perform.**

---

## 16. Roles

**CONFIRMED** existing privileges (not modified):

### OpenMRS

| Privilege / role | Relevance |
|---|---|
| `bahmni:clinical:dispense` | Chart Dispensed flag. On Privilege Level Full, High, SuperAdmin |
| No billing / cashier / pharmacy-named privileges found | Clinical chart does not own invoicing |

### Odoo groups (all have 4 users on this DB — typical admin duplication, not a hospital role map)

| Category | Groups |
|---|---|
| Invoicing | Billing (28), Billing Administrator (30) |
| Sales | Own Documents, All Documents, Administrator |
| Inventory | User, Administrator |
| Point of Sale | User, Administrator |
| Technical | Show Full Accounting Features (0 users) |

Redirect-to-payments-on-confirm group: **0 users**.

### Recommended separation (do **not** create yet)

| Role | Should | Should not |
|---|---|---|
| **Accountant** | View draft charges, confirm/finalize invoice **or** register payment on posted invoice, print receipt, authorized refund | Confirm delivery / deduct stock (if delivery is split from invoice) |
| **Pharmacist** | View Rx, verify payment (read), validate delivery / record operational dispense, view stock | Register patient payments; change prices; purchase |

Hospital EMR should eventually enforce this in **Hospital EMR roles** mapped to server-side OpenMRS/Odoo calls — not by copying Odoo groups into the browser.

---

## 17. Currency

**CONFIRMED**

| Item | Value |
|---|---|
| Company | Bahmni, currency id **2 USD**, symbol `$` |
| Journals | Cash / Bank have **no** journal-level currency override (company USD) |
| TEST list_price 1000 | **1000 USD**, not ₦1,000 |
| S00001 | 0.00 USD |

**REQUIRES OPERATIONS CONFIGURATION** for Nigerian production (later, not this task):

- Company currency / chart of accounts / journals / pricelist in NGN
- Possibly fiscal positions and tax
- Named POS terminal vs bank-transfer journals if the hospital needs them as separate cashbooks

**ABIKAN FUTURE IMPLEMENTATION:** display currency from Odoo company/pricelist (`res.currency.symbol` / `name`). **Do not hardcode ₦.**

Do **not** change currency during tests that share this database with protected records.

---

## 18. Security

**CONFIRMED / required**

- Browser JavaScript must **not** contain Odoo credentials.
- Atomfeed sale-order API uses **emrsync** server-side.
- Hospital EMR Pharmacy today is OpenMRS session reads only.
- No SSO between Hospital EMR and Odoo.

**ABIKAN FUTURE IMPLEMENTATION:**

```
Hospital EMR UI
    → Hospital EMR secure backend
        → OpenMRS (clinical)
        → Odoo (financial / inventory)
```

Writes (confirm SO, register payment, validate picking, optional Dispensed obs) go through the backend with service credentials and audit.

---

## 19. Hospital EMR architecture

Do **not** rebuild Odoo accounting, inventory, or purchasing inside Hospital EMR.

| Capability | A Hospital EMR UI over existing APIs | B Existing Bahmni/Odoo UI | C New secure backend | D Not currently possible |
|---|---|---|---|---|
| Prescription queue | **A** (already OpenMRS) | Bahmni Clinical also | Join Odoo paid state via **C** | — |
| Paid / unpaid | — | Odoo invoice `payment_state` | **C** then **A** | Not in OpenMRS |
| Payment verification | **A** display | Accountant in Odoo | **C** is mandatory | No installed pharmacy gate |
| Dispensing (stock) | **A** trigger | Odoo Sales Confirm / picking | **C** calls Odoo | OpenMRS D flag is not stock |
| Stock visibility | **A** | Odoo Inventory | **C** reads `stock.quant` | — |
| Drug catalogue | **A** OpenMRS + Odoo price | Both | **C** for price/stock | — |
| Low stock | **A** | Odoo | **C** | Needs reorder rules later |
| Batch / expiry | Later **A** | Odoo lots | **C** | TEST products tracking=`none` |
| Patient charges / bills | **A** Accounting workspace | Odoo Invoicing / Sales | **C** | Hospital EMR nav is ComingSoon |
| Payments / receipts | **A** | Odoo payment + PDF | **C** | No Hospital EMR printer yet |
| Outstanding balances | **A** | Odoo partner residual | **C** | Zero invoices live |
| UNPAID cannot dispense | Hospital EMR **workflow rule** via **C** | **Not in Odoo confirm** | **C** | **D** as installed backend |

Safest target:

- **OpenMRS** = clinical source of truth (Rx, visit, optional Dispensed chart flag).
- **Odoo** = financial and inventory source of truth (SO, invoice, payment, stock).
- **Hospital EMR** = hospital workflow UI (Pharmacy + Accounting) over a secure backend.
- Prefer **not** sending accountants and pharmacists to raw Odoo for daily counter work, but **keep** Odoo as the engine.

Hospital pay-then-dispense vs live `is_delivery_automated=True`:

| Option | Meaning | When to consider |
|---|---|---|
| **Ops later:** `is_delivery_automated=False` | Confirm → posted invoice, stock waits on picking. Pay, then pharmacist validates delivery. Closest to “bill → pay → dispense → stock”. | Recommended configuration discussion; **do not change now** |
| **Hospital EMR rule:** never confirm until paid | Draft SO is the bill-to-review; after payment, backend confirms (invoice **and** stock happen after pay). Invoice-after-pay is inverted vs classic AR, but matches current dual automation. | Works without config change; worse accounting sequence |
| Leave as-is | Confirm deducts stock before payment | **Does not match** Hospital EMR Hospital |

---

## 20. Controlled test plan — **DO NOT EXECUTE**

Goal: one end-to-end proof on **TEST** catalogue, without touching protected objects.

### Forbidden in that test (and in this investigation)

- Do not confirm **S00001**
- Do not use product **110** (0 stock, 0.00 price)
- Do not dispense ORD-1 or ORD-2
- Do not consume stock except the TEST product **after** explicit approval
- Do not change currency
- Do not set OpenMRS Dispensed until the `ir.values` crash is fixed
- Do not rewind Atomfeed

### Suggested TEST inputs

| Item | Value |
|---|---|
| Drug | OpenMRS uuid `1c88be47-1ea9-4908-a57f-dc5ebd47caec` / Odoo product **2385** Paracetamol 500 mg — TEST |
| Dose unit | **Tablet** (mapped to Units) |
| Qty | 10 Tablet → expect 10 Units |
| List price | 1000 **USD** |
| Stock before | 100 Units at WH/Stock 8 |
| Patient | A patient **without** an existing active order of this TEST drug. Do **not** add a second identical OpenMRS drug to a patient who already has it (`[Order.cannot.have.more.than.one]`). TEST Paracetamol is a **different** drug from ORD-1/ORD-2 Paracetamol 500 mg, so it **may** be prescribed for John or Tunde — but appending to **S00001** would happen if Tunde’s draft S00001 still exists. **Do not use Tunde while S00001 is draft** if the test must not modify S00001. Prefer a patient with **no** draft API FEED SYNC SO, or John Adewale (no SO today) **if** Operations accepts a new TEST Rx on John. |

### Expected state at each step (design only)

| Step | Action | Expected |
|---|---|---|
| 0 | Baseline | 2385 quant 100; S00001 draft; 0 invoices; 0 payments; ORD-1/ORD-2 Ordered |
| 1 | Create OpenMRS Drug Order for TEST Paracetamol, Tablet, qty 10 | New order uuid; status Ordered; **not** Dispensed |
| 2 | Wait for Atomfeed / odoo-connect | New **draft** `sale.order` origin `API FEED SYNC`; line `product_id=2385`, qty 10 Units, `price_unit=1000`, `external_order_id`=new order uuid; **S00001 unchanged** |
| 3 | Patient charge | SO `amount_untaxed` ≈ 10000 USD before tax; tax **REQUIRES CONTROLLED TEST** (15% may apply). Treat as USD. Draft is **not** a posted bill |
| 4 | Finalize bill | Confirm **the new SO only**. If `is_delivery_automated` stays True: picking done **and** invoice posted in one click. If delivery fails, whole confirm may roll back — **REQUIRES CONTROLLED TEST** |
| 5 | Pay bill | Register inbound payment on the new invoice, journal **Cash CSH1** (or Bank BNK1). Do not use POS unless that is the test’s point (it is not the feed path) |
| 6 | Receipt | Print Bahmni Receipt or `account.report_payment_receipt`. Number = payment `name`. Patient name + `partner.ref` |
| 7 | Verify payment | Invoice `payment_state` paid (or in_payment); residual 0; line still linked via `external_order_id` |
| 8 | Pharmacy “PAID / READY TO DISPENSE” | **Does not exist in Odoo UI.** Hospital EMR would compute it from step 7. After current confirm, stock may **already** have moved at step 4 |
| 9 | Dispense | If delivery already auto-done at confirm, operational dispense **already happened** at step 4. If Ops later disables auto delivery, pharmacist validates picking here |
| 10 | Stock | If confirm+auto delivery succeeded for qty 10: location 8 product 2385 **90**. Reserved 0. Product 110 still 0. P00001 untouched |
| 11 | OpenMRS Dispensed | Still **Ordered** unless someone sets the obs. **Do not set it** until convert_dispensed is fixed. Confirm does not set it |
| 12 | Invoice / payment | Posted invoice + posted payment; SO `state=sale`, `invoice_status` invoiced |
| 13 | Audit | OpenMRS encounter+order; Atomfeed consumed; Odoo SO chatter; stock move from 8; `account.move` + `account.payment` `create_uid` |

**Mismatch to hospital intent (document, do not “fix” in the test unless Ops changes config first):** with live flags, **stock decreases at confirm (step 4), before payment (step 5).** The test will prove that. A second test after `is_delivery_automated=False` would prove pay-then-stock.

---

## Status board

### CONFIRMED

- Prescription → draft sale order via Atomfeed / odoo-connect / `order.save.service`
- Patient = `res.partner.ref` MRN; product uuid shared; line `external_order_id` = order uuid
- Price from Odoo `list_price` (pricelist 1, no items); OpenMRS has no price
- Draft SO is not a posted bill; posted bill is `account.move` out_invoice created on confirm
- Invoice cannot be produced by the installed automation while the SO stays draft
- Confirm + live flags = delivery done + invoice posted; **payment not automatic**
- Cash journal 6 and Bank journal 7 exist (USD); POS tenders exist but unused by the feed
- Printable invoice and payment receipt reports exist; Bahmni Receipt uses name, MRN (`ref`), date, amounts
- OpenMRS Dispensed ≠ Odoo stock out; Dispensed feed worker is broken (`ir.values`)
- Stock decreases at automated delivery `_action_done` inside confirm
- Multiple Drug Order lines in one encounter → one SO; later encounters append to the same **draft** SO
- No unpaid-cannot-dispense enforcement
- Company currency USD; 1000 ≠ ₦1,000
- Hospital EMR Pharmacy is OpenMRS-read only; Accounting screens are ComingSoon
- Protected records still draft / 100 Units / 0 invoices / 0 payments

### UNKNOWN

- Exact Odoo 16 `payment_state` label after cash register payment
- Whether confirm-with-zero-stock rolls back the whole SO or leaves a failed picking (do **not** test on S00001)
- Whether Tax 15% applies to product 2385 on a real invoice
- Whether Bahmni Receipt “Consultant” is populated
- Exact Clinical HTML widget for the D checkbox (privilege and obs contract are known)
- Whether two concurrent draft SOs for one patient can appear in production

### NOT SUPPORTED

- Installed pay-before-dispense gate
- OpenMRS automatic Dispensed after Odoo confirm
- First-class partial qty (5 of 10) across OpenMRS + Odoo
- Consultation fee + pharmacy on one bill (only Drug Order type mapped)
- QR verification on the receipt
- Hospital EMR-native ledger, cashier, or stock engine
- Using POS as the Atomfeed pharmacy path

### REQUIRES OPERATIONS CONFIGURATION (later)

- Nigerian NGN currency, journals, and named Cash / POS / Transfer cashbooks
- `is_delivery_automated=False` if the hospital must invoice without deducting stock
- Additional `order.type` / shop maps for lab, radiology, consultation fees
- Capsule (and other) unit mappings if those forms are prescribed
- Fix or bypass `ir.values` / `convert_dispensed` before any OpenMRS Dispensed feed
- Reorder rules / low-stock
- Lot tracking if batch/expiry is required (TEST products are `tracking=none`)
- Role mapping: Odoo Billing vs Inventory vs Hospital EMR accountant vs pharmacist
- Pricing: product 110 is 0.00; production drugs need real `list_price`

### REQUIRES CONTROLLED TEST (not executed)

- Full TEST Paracetamol 2385 prescribe → SO → confirm → pay → receipt → stock 100→90
- Partial payment / multi-invoice payment
- Credit note / payment reverse / stock return
- Multi-drug encounter → one SO
- Second visit while draft vs after confirm
- Tax on TEST 1000 list price
- Confirm behaviour with zero stock (use a **throwaway** product, never S00001)

### ABIKAN FUTURE IMPLEMENTATION

- Accounting workspace: charges, bills, payments, receipts, outstanding (reads/writes via backend)
- Pharmacy: paid/unpaid, verify payment, dispense trigger, stock, catalogue, low stock
- Workflow rule: UNPAID cannot dispense
- Currency display from Odoo
- Optional OpenMRS Dispensed write **after** the feed crash is fixed and stock has moved
- Never put Odoo passwords in frontend JS
- Never duplicate Odoo AR / inventory / purchasing

---

## Direct answers (investigation)

1. **How a prescription becomes a patient bill** — OpenMRS Drug Order is synced to a **draft** Odoo `sale.order`. The posted bill is an `account.move` invoice created when that SO is **confirmed** (`is_invoice_automated=True`). The draft SO is only a charge preview.
2. **Who creates the bill** — Atomfeed/odoo-connect creates the quotation. A human in **Odoo Sales** (or a future Hospital EMR backend call to `action_confirm`) finalizes the invoice. Hospital EMR does not create bills today.
3. **Who collects payment** — Intended: accountant in **Odoo Invoicing** (Register Payment). Not automatic. Hospital EMR Reception Payments is ComingSoon.
4. **Where payment is recorded** — `account.payment` reconciled to `account.move`. Not POS (unused). Not OpenMRS.
5. **How the receipt is generated** — Print Odoo/Bahmni QWeb reports on `account.payment` (and/or the invoice PDF). Not auto-printed on confirm, because confirm does not pay.
6. **How Pharmacy verifies payment** — There is **no** installed pharmacy check. The reliable join is `external_order_id` → SO → invoice → `payment_state`. Hospital EMR must implement that as a **backend read**. A paper receipt number is the payment `name` / invoice `name`, not a QR.
7. **What actually constitutes dispensing** — Operationally: **Odoo sale order confirm** (delivery `_action_done`). Clinically: optional OpenMRS Dispensed **boolean obs**, currently unsafe to set. They are not the same operation.
8. **When stock decreases** — When the delivery picking is `_action_done`. Live that is **inside confirm** (`is_delivery_automated=True`). Not at SO create, invoice, payment, or OpenMRS Dispensed.
9. **Whether OpenMRS is marked Dispensed automatically** — **No.** Confirm does not write OpenMRS. The Dispensed feed path would crash this Odoo.
10. **Whether partial dispensing works** — **Not as a linked workflow.** OpenMRS flag is boolean. Odoo could change qty or (if auto-delivery is off) backorder; the chart would still show full Ordered or fully Dispensed.
11. **How multiple drugs are billed** — One encounter, all Drug Orders → **one** sale order / one bill after confirm.
12. **How multiple prescriptions are billed** — Appended to the existing **draft** SO for that patient+shop; **new** SO after the previous one is confirmed.
13. **How refunds work** — Standard Odoo credit note, payment reverse, stock return; OpenMRS discontinue only removes **draft** lines. Untested. No hospital-specific return flow.
14. **Financial source of truth** — **Odoo** (`sale.order`, `account.move`, `account.payment`, `stock.quant`).
15. **Clinical source of truth** — **OpenMRS** (orders, encounters, Dispensed obs).
16. **What Hospital EMR should display** — Pharmacy: Rx queue, paid/unpaid (from Odoo), stock, catalogue. Accounting: charges, invoices, payments, receipts, outstanding. Currency from Odoo.
17. **What Hospital EMR should write** — Through a **secure backend** only, and only after product approval: optional payment register, optional confirm / picking validate, never a second ledger. Do not write OpenMRS Dispensed until the feed is safe.
18. **What Odoo should handle** — Pricing, quotations, invoices, payments, receipts, stock, purchases, journals.
19. **What OpenMRS should handle** — Prescriptions, clinical dispensing flag (later), patient/MRN, drug catalogue UUID ownership.
20. **Exact safest end-to-end test** — New TEST Paracetamol 2385 Rx (not Tunde/S00001), verify new draft SO at 1000 USD × 10, confirm **that** SO only, register Cash payment, print receipt, expect stock 100→90 **at confirm** with current flags, OpenMRS still Ordered, S00001/ORD-1/ORD-2/P00001 untouched. **Do not execute until explicitly approved.** Prefer a follow-up test after `is_delivery_automated=False` if the hospital must prove pay-then-stock.

---

*End of investigation. No invoices, payments, confirms, dispenses, stock moves, currency changes, or UI/backend implementation were performed.*
