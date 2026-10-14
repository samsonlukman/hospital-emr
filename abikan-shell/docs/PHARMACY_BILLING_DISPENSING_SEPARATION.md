# Pharmacy: separate billing from dispensing

Investigation only. **17 Aug 2026.**

**No configuration was changed.** `bahmni_sale.is_delivery_automated` remains **True**. No sale order was confirmed. No invoice, payment, picking validation, or stock move was created.

Status labels:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Installed source and/or live database |
| **UNKNOWN** | Cannot be proven without a write |
| **NOT SUPPORTED** | No installed path |
| **REQUIRES CONFIGURATION** | Settings change later; **not applied** |
| **REQUIRES CONTROLLED TEST** | Approved write later; **not executed** |
| **ABIKAN FUTURE IMPLEMENTATION** | Product work; not built here |

Related: `docs/PHARMACY_BILLING_PAYMENT_DISPENSING_WORKFLOW.md`.

Protected objects left untouched: **S00001** draft; ORD-1 / ORD-2 Ordered; product **2385** 100 Units at WH/Stock 8; currency **USD**; P00001; supplier 18.

---

## 1. Current behaviour

**CONFIRMED** live flags (`ir.config_parameter`):

| Key | id | value |
|---|---|---|
| `bahmni_sale.is_delivery_automated` | 29 | `True` |
| `bahmni_sale.is_invoice_automated` | 31 | `True` |
| `validate_delivery_when_order_confirmed` | 19 | `0` |

Current confirm path (`bahmni_sale` `sale.order.action_confirm`):

```
Confirm quotation
  → pre-checks (qty > 0; lot only if tracking=lot)
  → super().action_confirm(default_immediate_transfer=True)
       → sale.order.state = sale
       → procurement creates stock.picking + stock.move
  → validate_delivery()          [no-op: other flag is 0]
  → if is_delivery_automated:    [LIVE: True]
       force quantity_done
       picking._action_done()    ← stock decreases HERE
  → if is_invoice_automated:     [LIVE: True]
       _create_invoices()
       invoice.action_post()     ← posted bill
  → payment is NOT created
```

Hospital wants bill → pay → pharmacy verify → then stock out. Live confirm does **stock + invoice together, before payment**.

---

## 2. Desired hospital behaviour

```
Doctor prescribes
  → draft sale.order (already works via Atomfeed)
  → Accountant confirms SO
       → posted invoice
       → delivery picking created but NOT validated
       → on-hand stock unchanged
  → Patient pays
       → account.payment
       → receipt
       → invoice payment_state = paid
  → Pharmacy verifies payment (Hospital EMR, server-side)
  → Pharmacist validates picking
       → stock decreases
       → qty_delivered updates
```

**PAID ≠ DISPENSED.** Payment only makes the prescription eligible. The pharmacist performs the stock-changing operation.

---

## 3. Source-code findings

Installed file: `/opt/bahmni-erp/bahmni-addons/bahmni_sale/models/sale_order.py` `action_confirm`.

The two flags are **independent `if` blocks**. Invoice automation does **not** require delivery automation.

```
res = super(... default_immediate_transfer=True).action_confirm()
self.validate_delivery()                          # gated by a DIFFERENT param (live 0)
if picking_ids and is_delivery_automated:         # lines 400–413
    ... picking._action_done()
if is_invoice_automated:                          # lines 414–428
    self._create_invoices()                       # posts when same flag True
```

`validate_delivery()` is leftover Odoo 10 (`pack_operation_product_ids`, `do_new_transfer`). It only runs when `validate_delivery_when_order_confirmed == '1'`. Live **0**. Leave it alone.

`auto_validate_delivery()` is only for the OpenMRS Dispensed feed path. Broken (`ir.values`). Not used on human confirm.

Standard Odoo 16 `sale.order.action_confirm` → `_action_confirm` → `sale_stock` `_action_launch_stock_rule` → `procurement.group.run` → outgoing **Delivery Orders** picking (type id 2, `reservation_method=at_confirm`, `create_backorder=ask`).

Bahmni `stock.picking.create` copies `sale.order.location_id` onto the picking (Pharmacy Counter → WH/Stock id 8).

`bahmni_stock` `button_validate`: extra wizard only for **internal** and **incoming**. Outgoing pharmacy deliveries use **standard** `super().button_validate()`.

**CONFIRMED:** no `account.payment` / `bahmni_account` / `bahmni_auto_payment_reconciliation` code validates a picking. Payment does not dispense.

---

## 4. `is_delivery_automated = True` (current)

**CONFIRMED**

After a successful confirm of a storable product with stock:

| Model | Expected state |
|---|---|
| `sale.order` | `sale` |
| `stock.picking` | `done` |
| `stock.move` | `done` |
| `stock.quant.quantity` | decreased |
| `account.move` | `posted` (`is_invoice_automated` still True) |
| `account.move.payment_state` | `not_paid` |
| `account.payment` | none |
| OpenMRS order | still Ordered |

If stock is insufficient (`allow_negative_stock=0`), `_action_done` is expected to fail. Whether the whole confirm rolls back is **REQUIRES CONTROLLED TEST**. Do **not** test this on S00001 (product 110 has 0 stock).

---

## 5. `is_delivery_automated = False` (proposed, **not applied**)

**CONFIRMED from source** (the `if` at line 400 is skipped):

Confirm still:

1. Runs the same pre-checks
2. Calls `super().action_confirm()` → SO `state=sale` → **creates** picking + moves
3. Calls `validate_delivery()` → no-op
4. **Does not** set `quantity_done` / **does not** call `_action_done`
5. Still creates and **posts** the invoice if `is_invoice_automated` stays True

Expected states after confirm (source-based; **REQUIRES CONTROLLED TEST** to lock exact picking/reservation labels):

| Model | Expected |
|---|---|
| `sale.order.state` | `sale` |
| `sale.order.invoice_status` | `invoiced` (after auto invoice) |
| `account.move.state` | `posted` |
| `account.move.payment_state` | `not_paid` |
| `stock.picking` | exists, **not** `done` |
| `stock.move` | exists, **not** `done` |
| `stock.quant.quantity` | **unchanged** (on-hand) |
| `sale.order.line.qty_delivered` | **0** (only counts `stock.move` state `done`) |

### How to turn the flag off correctly

`action_confirm` uses:

```python
bool(self.env['ir.config_parameter'].sudo().get_param('bahmni_sale.is_delivery_automated'))
```

`ir.config_parameter` values are strings. Odoo `set_param(key, False)` **deletes the row**. Then `get_param` returns `False` and `bool(False)` is False. That is the Settings checkbox path.

**Do not** SQL-update the value to the string `False`. In Python `bool("False")` is **True**, so automation would **stay on**.

| Method | Result |
|---|---|
| Settings: uncheck “Enable auto delivery…” then Save | `set_param(..., False)` → row **deleted** → automation off |
| `set_param('bahmni_sale.is_delivery_automated', False)` | same |
| `UPDATE ... SET value='False'` | **WRONG** — `bool("False")` is True |

### Picking state after confirm — **REQUIRES CONTROLLED TEST**

Bahmni always calls `super()` with `default_immediate_transfer=True`. That context **may** create the picking as `immediate_transfer=True` (skip classic reservation) or the procurement path may ignore it.

Either way, **on-hand quantity does not decrease** until `_action_done` / `button_validate`.

Likely picking states (standard Odoo 16 Delivery Orders, stock available):

- Classic reservation: `assigned` (Ready), `reserved_quantity` increased, `quantity` unchanged
- Immediate transfer: often treated as ready without reserve; `quantity` still unchanged

If stock is missing: `confirmed` / `waiting` / `partially_available`. Invoice can still post (`invoice_policy=order`).

---

## 6. Invoice behaviour

**CONFIRMED:** invoice automation is a **separate** flag.

| Flag | Keep for hospital bill-then-pay |
|---|---|
| `bahmni_sale.is_invoice_automated` | **True** (do not turn off for this design) |
| `bahmni_sale.is_delivery_automated` | proposed **False** |

With invoice automation on and delivery automation off:

- Invoice is **created** and **posted** on confirm
- Product `invoice_policy=order` on 110 and 2385 → invoice qty = ordered qty, **not** delivered qty
- Invoice does **not** wait for picking
- Draft invoice-while-SO-draft is still **not** this path

Tax 15% may apply to TEST 1000 — **REQUIRES CONTROLLED TEST**. Amounts are **USD**.

---

## 7. Payment behaviour

**CONFIRMED from source; no live payment exists**

After posted invoice, accountant uses Odoo Register Payment (`account.payment.register` → `account.payment`) on Cash **CSH1** id 6 or Bank **BNK1** id 7.

| Question | Answer |
|---|---|
| Can the patient pay before picking is validated? | **Yes.** Invoice and picking are independent after confirm. |
| Invoice `payment_state` after full reconcile | `paid` (or `in_payment` then `paid` — **REQUIRES CONTROLLED TEST** for the exact label on cash) |
| Partial pay | `partial` is a valid `payment_state` |
| Does payment validate the picking? | **No.** No installed hook. **This is the desired split.** |
| Does payment change stock? | **No.** |

`validate_payment()` on `sale.order` is only on the broken Dispensed-feed path. Not used here.

---

## 8. Picking behaviour

**CONFIRMED**

Operational dispense = validate the outgoing `stock.picking`.

| Topic | Installed behaviour |
|---|---|
| UI | Odoo Inventory / Sales → Delivery smart button → Validate |
| Method | `stock.picking.button_validate` → standard Odoo (outgoing skips Bahmni extra wizard) |
| Then | `_action_done` on moves → stock out |
| Reservation | Delivery type `reservation_method=at_confirm`. Exact reserved qty after confirm with automation off: **REQUIRES CONTROLLED TEST** |
| Available qty | On-hand `stock.quant.quantity` minus `reserved_quantity` |
| Partial qty | Set `quantity_done` / `qty_done` < demand |
| Backorder | Picking type `create_backorder=ask` → wizard; remaining qty on a new picking |
| Cancel | Standard `action_cancel` on a non-done picking; does not unpost the invoice |

`sale.order.line.qty_delivered` updates only from **done** outgoing moves.

---

## 9. Stock behaviour

**CONFIRMED**

| Event | `stock.quant.quantity` at WH/Stock 8 |
|---|---|
| Draft SO created | unchanged |
| Confirm + delivery automation **True** | decreases (if `_action_done` succeeds) |
| Confirm + delivery automation **False** | **unchanged** (on-hand). Reserve **may** increase |
| Register payment | unchanged |
| Validate picking | **decreases** by qty done |
| OpenMRS Dispensed obs | unchanged (and unsafe) |

TEST product 2385 today: quantity **100**, reserved **0**. A later test of qty 10 should leave quantity 100 after confirm (automation off), then 90 after validate. **Not executed.**

---

## 10. Dispensing behaviour

**CONFIRMED**

| Meaning | Authoritative field | Safe now? |
|---|---|---|
| Operational dispense (drugs left the shelf) | Outgoing `stock.picking.state == 'done'` and/or `sale.order.line.qty_delivered` | **Yes** — Odoo only |
| Chart flag | OpenMRS Dispensed boolean obs | **No** — downstream Odoo uses missing `ir.values` |

**Safest operational DISPENSED for Abikan:** Odoo picking / `qty_delivered`. Do **not** set OpenMRS Dispensed until that feed is fixed.

Pharmacist action after payment: validate the picking (Odoo backend / future Hospital EMR backend call). Not “confirm sale order” again (already `sale`). Not OpenMRS D.

---

## 11. Partial dispensing

**CONFIRMED** as standard Odoo; **NOT SUPPORTED** as a linked OpenMRS qty.

Example: prescribed 10, paid 10, hand out 5.

| Layer | After validating 5 of 10 |
|---|---|
| Invoice | Still 10 (`invoice_policy=order`). Already posted/paid. **Does not shrink.** |
| Payment | Unchanged |
| Picking | Original done for 5; backorder picking for 5 (`create_backorder=ask`) |
| `qty_delivered` | 5 |
| On-hand 2385 | 100 → 95 |
| OpenMRS | Still Ordered 10. Dispensed boolean cannot mean “half”. **Do not set it.** |

**REQUIRES CONTROLLED TEST** to confirm the backorder wizard on this build.

Hospital EMR can display: paid 10, delivered 5, remaining 5 (from Odoo moves / backorder). That is a Hospital EMR presentation over Odoo, not a new inventory engine.

---

## 12. Multiple drugs

**CONFIRMED** from procurement: one SO with Paracetamol + Amoxicillin + Vitamin C → typically **one** outgoing picking with **one move per product** (same warehouse / customer location).

With delivery automation off, the pharmacist can:

| Action | How |
|---|---|
| Dispense all | Validate picking with full `qty_done` on every move |
| Partial one drug | Lower `qty_done` on that move → backorder for remainder |
| Leave one item undispensed | `qty_done=0` on that move → backorder (or leave picking open if nothing is done) |
| Create a backorder | Standard wizard (`ask`) |

Invoice still covers **all** ordered lines at confirm (policy `order`). Payment is for the whole bill, not per drug, unless Operations later splits SOs (not current feed behaviour).

Unit-mapping risk remains: a line with qty 0 blocks confirm. Capsule→Units is still not mapped.

---

## 13. Payment verification

**CONFIRMED** join (unchanged):

```
OpenMRS drug order UUID
  = sale.order.line.external_order_id
  → sale.order
  → account.move (invoice_ids / invoice_origin / order_id)
  → payment_state
  → stock.picking (sale_id / picking_ids)
  → qty_delivered
```

### Strongest pharmacy lookup

| Identifier | Strength |
|---|---|
| OpenMRS drug order UUID / `external_order_id` | **Strongest clinical↔financial key.** One line, one Rx. |
| Sale order number (S0000x) | Strong for the visit/bill group; may contain several drugs |
| Invoice number | Strong once posted; proves the bill |
| Payment / receipt number (`account.payment.name`) | Strong proof of **payment**, not of which line |
| MRN | Patient only. Not enough. |

Safest server-side chain: **order UUID → line → SO → invoice `payment_state` → picking state / `qty_delivered`.**

Receipt number is a human token that resolves to `account.payment`, then to the invoice, then to the SO/lines. Use it as an optional scan/type-in, then verify the UUID chain.

### Hospital EMR display states (not implemented)

| Label | Server-side rule |
|---|---|
| **UNPAID** | No posted invoice, or `payment_state` in (`not_paid`, `partial`, `reversed`) |
| **PAID** | Invoice `payment_state` in (`paid`, `in_payment`) |
| **READY TO DISPENSE** | PAID **and** outgoing picking exists **and** picking not fully `done` (`qty_delivered` < `product_uom_qty`) |
| **DISPENSED** | `qty_delivered` ≥ `product_uom_qty` **or** no open outgoing picking (all `done`/`cancel`) |
| **PARTIALLY DISPENSED** | PAID and `0 < qty_delivered < product_uom_qty` |

Treat `in_payment` as paid-enough for pharmacy only if Operations accepts bank-clearing delay. Cash register payments are expected to become `paid` immediately — **REQUIRES CONTROLLED TEST**.

**NOT SUPPORTED** in Odoo: unpaid-cannot-validate-picking. `button_validate` does not read `payment_state`.

**ABIKAN FUTURE IMPLEMENTATION:** hide/disable Dispense unless READY TO DISPENSE. The stock write must still be Odoo `button_validate` / `_action_done` via the secure backend.

---

## 14. OpenMRS Dispensed

**CONFIRMED:** do not use it for this workflow yet.

- Boolean obs only; not qty
- Confirm / payment / picking do not write it
- Setting it would crash odoo-connect (`ir.values` / `convert_dispensed`)
- `order_attribute` table empty

OpenMRS should keep the **prescription** (Ordered / Stopped). Operational dispensed = **Odoo picking**.

Later, after the feed is fixed, Hospital EMR may write the obs **after** picking `done`. Not now.

---

## 15. Currency

**CONFIRMED:** company currency **USD** id 2. Do not change it in this work.

Nigerian production later (Operations, not this task): company currency / chart / journals / pricelist in NGN; Cash vs POS vs transfer cashbooks. Hospital EMR must display Odoo `res.currency`, not hardcode ₦. TEST `list_price` 1000 is **USD 1000**.

---

## 16. Configuration change

**REQUIRES CONFIGURATION — do not apply yet.**

| Item | Value |
|---|---|
| Record | `ir.config_parameter` id **29** |
| Key | `bahmni_sale.is_delivery_automated` |
| Current | `True` |
| Proposed | **off** via Settings checkbox or `set_param(..., False)` (row deleted) |
| Leave unchanged | `bahmni_sale.is_invoice_automated` = `True` (id 31) |
| UI | Odoo Settings → Bahmni sale: “Enable auto delivery on sale order confirm action” |
| Stored in | PostgreSQL `ir_config_parameter` (Odoo cache cleared on write/unlink) |
| Docker / OpenMRS / Atomfeed restart | **Not required** |
| Existing draft SOs (S00001) | **Not rewritten.** Flag is read **at confirm time**. S00001 stays draft. |
| New / later confirms | Use the new flag |
| Already-done deliveries | None for pharmacy SOs. No retroactive un-validate |

**Do not confirm S00001** after the change either (product 110, 0 stock, 0.00 price, ORD-2).

---

## 17. Controlled test — **DO NOT EXECUTE**

Use **new** TEST Paracetamol 2385 prescription only. Not S00001, ORD-1, ORD-2.

Prerequisite: apply `is_delivery_automated=False` **only when this test is approved**. Keep `is_invoice_automated=True`. Currency USD.

Do not use Tunde Bakare while S00001 is draft (feed would **append** to S00001). Prefer a patient with no draft `API FEED SYNC` SO (John Adewale has none today) **or** a new TEST patient.

| Step | Action | Expected |
|---|---|---|
| 0 | Baseline | 2385: qty 100 reserved 0; S00001 draft; 0 invoices; 0 payments; flag still True until the approved change |
| 1 | New OpenMRS Drug Order, TEST Paracetamol, 10 Tablet | New order uuid; Ordered; not Dispensed |
| 2 | Atomfeed | **New** draft SO; line product 2385 qty 10 `price_unit=1000`; `external_order_id`=new uuid; **S00001 unchanged** |
| 3 | Confirm **that** SO only | SO `sale`; invoice **posted** `not_paid`; picking **not** `done`; `qty_delivered=0`; **quantity still 100** |
| 4 | Register Cash payment (journal 6) | Invoice `paid` (or `in_payment`); receipt printable; picking still not `done`; stock still 100 |
| 5 | Hospital EMR would show PAID / READY TO DISPENSE | Not implemented; compute from invoice + picking |
| 6 | Validate picking qty 10 | Picking `done`; 2385 quantity **90**; `qty_delivered=10`; payment unchanged |
| 7 | OpenMRS | Still Ordered. **Do not** set Dispensed |

Optional second pass on a **different** TEST Rx: pay 10, validate 5, expect backorder 5, stock 95, invoice still 10 paid.

If step 3 decreases stock, **stop** — automation did not turn off (check for string `"False"` pitfall). Rollback immediately.

---

## 18. Rollback

If the flag was turned off via Settings / `set_param(..., False)`:

1. Settings: re-check “Enable auto delivery on sale order confirm action” and Save  
   **or** `set_param('bahmni_sale.is_delivery_automated', True)`
2. Row id 29 (or a new id if recreated) value `True`
3. No restart
4. Does **not** un-validate pickings already done
5. Does **not** unpost invoices
6. Next confirm returns to stock+invoice in one click

If a TEST confirm already created an invoice/picking: cancel the **TEST** picking if not done; do not touch S00001 / P00001 / WH/IN/00001. Credit-note/cancel the TEST invoice only if Operations approves. Restore 2385 to 100 only if a TEST picking was wrongly validated.

---

## 19. Hospital EMR implementation

Do **not** build a second inventory or accounting engine.

| Layer | Role |
|---|---|
| OpenMRS | Prescription (clinical). Do not use Dispensed yet |
| Odoo | Quotation, invoice, payment, receipt, picking, stock |
| Hospital EMR UI | Accountant: charges / pay / receipt. Pharmacy: UNPAID / PAID / READY / DISPENSED |
| Hospital EMR backend | Reads the UUID chain; registers payment if productized; calls Odoo picking validate **only when PAID** |

```
Hospital EMR UI  →  secure backend  →  OpenMRS / Odoo
```

Browser JavaScript must not contain Odoo credentials.

### What this config change does **not** give you

- It does **not** stop a user who can open Odoo Inventory from validating an unpaid picking
- It does **not** mark OpenMRS Dispensed
- It does **not** convert USD to naira
- It does **not** fix S00001 / product 110 / ORD-1 missing SO

Those remain Hospital EMR rules, Operations pricing, and later tests.

---

## Status board

### CONFIRMED

- Delivery automation and invoice automation are independent
- True: confirm validates picking and decreases stock, then posts invoice
- False (source): confirm still creates picking + posts invoice; skips `_action_done`
- Payment does not validate picking
- `qty_delivered` only counts done moves
- `invoice_policy=order` invoices full qty at confirm
- No Odoo unpaid-cannot-dispense gate
- OpenMRS Dispensed is unsafe
- Flag lives in `ir.config_parameter` id 29; `set_param(False)` deletes the row
- Writing the string `"False"` would **fail** to disable automation
- Protected records unchanged; flag still True

### UNKNOWN / REQUIRES CONTROLLED TEST

- Exact `stock.picking.state` and `reserved_quantity` after confirm with automation off
- Whether `default_immediate_transfer=True` marks the pharmacy picking as immediate
- Exact `payment_state` after cash register (`paid` vs `in_payment`)
- Backorder wizard on a 5-of-10 validate
- Tax on 1000 USD TEST line
- Confirm rollback when stock is zero (do not use S00001)

### NOT SUPPORTED

- Installed pay-before-validate enforcement
- OpenMRS partial qty
- QR receipt verification
- Automatic OpenMRS Dispensed after picking

### REQUIRES CONFIGURATION (later, approved)

- Turn **off** `bahmni_sale.is_delivery_automated` via Settings / `set_param(False)`
- Keep `is_invoice_automated` True
- Nigerian currency later (separate)

### ABIKAN FUTURE IMPLEMENTATION

- PAID / READY TO DISPENSE / DISPENSED from server-side Odoo reads
- Block Dispense unless paid
- Backend picking validate
- Optional OpenMRS Dispensed **after** feed fix

---

## Direct answers

1. **TRUE:** confirm creates picking, auto-validates it, stock decreases, then invoice posts. No payment.
2. **FALSE:** confirm creates picking **and** (if invoice flag stays True) posts invoice; picking stays open; on-hand stock unchanged until validate.
3. **Invoice stays automatic** if `is_invoice_automated` remains True. Independent flag.
4. **On-hand stock stays untouched** until picking validation. Reservation may still increase — test later.
5. **Yes.** Pay the posted invoice while the picking is waiting/ready.
6. **Yes.** Pharmacist validates the existing picking after payment.
7. **No.** Payment does not dispense. Desired.
8. **Safest DISPENSED:** Odoo outgoing picking `done` / `qty_delivered`. Not OpenMRS Dispensed.
9. **Partial:** Odoo backorder + `qty_delivered`. Invoice stays full. OpenMRS cannot store 5 of 10.
10. **Multiple drugs:** one picking, one move per product; validate all, some, or backorder.
11. **PAID:** yes, via `external_order_id` → invoice `payment_state`.
12. **DISPENSED:** yes, via picking / `qty_delivered`. Not via OpenMRS today.
13. **OpenMRS:** keep the prescription Ordered/Stopped. Do not write Dispensed yet.
14. **Odoo:** SO, invoice, payment, receipt, picking, stock.
15. **Abikan:** UNPAID / PAID / READY TO DISPENSE / DISPENSED (and remaining qty). Currency from Odoo.
16. **Config:** uncheck / `set_param('bahmni_sale.is_delivery_automated', False)`. Do not SQL `'False'`. Leave invoice automation on. **Not applied.**
17. **Test:** new 2385 Rx → new draft SO → confirm → invoice posted, stock 100 → pay → validate → stock 90. Not S00001/ORD-1/ORD-2. **Not executed.**
18. **Rollback:** `set_param(..., True)` or re-check the Settings box. No restart. Does not undo TEST invoices/pickings already created.

---

*End of investigation. `bahmni_sale.is_delivery_automated` is still True. No writes.*
