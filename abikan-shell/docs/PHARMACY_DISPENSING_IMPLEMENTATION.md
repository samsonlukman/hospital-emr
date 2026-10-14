# Pharmacy dispensing — implementation

Date: **17 Aug 2026** (UTC). Controlled isolated TEST only.

Related: `PHARMACY_WORKFLOW.md`, `PHARMACY_BILLING_PAYMENT_DISPENSING_WORKFLOW.md`, `PHARMACY_BILLING_DISPENSING_SEPARATION.md`, `PHARMACY_DISPENSING_BILLING_INVESTIGATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `ACCOUNTANT_PAYMENT_E2E_TEST.md`.

This phase implements:

```
PAID
  → READY TO DISPENSE
  → pharmacist confirms
  → Odoo picking validation
  → DISPENSED
```

Odoo remains the stock source of truth. OpenMRS remains the clinical chart. Hospital EMR is the hospital UI. There is no Hospital EMR stock ledger.

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **WRITE** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **NOT TESTED**

---

## 1. Pharmacy queue

**IMPLEMENTED**

| Hash | Screen |
|---|---|
| `#/pharmacy` | Pharmacy desk — Ready to dispense first |
| `#/pharmacy/patient/{patientUuid}` | One patient |
| `#/pharmacy/prescription/{orderUuid}` | One prescription — Dispense |

Header search on Pharmacy opens the patient screen. There is no payment button.

**Ready to dispense** lists only prescriptions whose backend status is `READY TO DISPENSE`.

**Other prescriptions** lists real statuses only:

- `UNPAID`
- `DISPENSED`
- `STOPPED`
- `PAID` (invoice paid, delivery not yet created) — rare; not shown as ready

No fake KPI cards. No invented statuses.

---

## 2. READY TO DISPENSE rules

**IMPLEMENTED** · server recalculates from Odoo on every GET

A prescription is **READY TO DISPENSE** only when all of these are true:

1. OpenMRS drug order exists and is not stopped
2. An Odoo sale-order line exists with `external_order_id` = OpenMRS order UUID
3. A posted customer invoice exists
4. Invoice `payment_state` is `paid` or `in_payment`
5. Invoice `amount_residual` is `0` (partial payment is **not** ready)
6. An outgoing delivery exists and is not `done` / cancelled
7. Delivered quantity is still below ordered quantity

Staff see **PAID** for money and **READY TO DISPENSE** for the counter queue. They never see sale-order, invoice, or picking identifiers.

---

## 3. Payment verification

**IMPLEMENTED** · **READ-ONLY** against Odoo

Payment status is never taken from the pharmacist, a checkbox, a note, or React state.

Path:

```
OpenMRS order UUID
  → sale.order.line.external_order_id
  → sale.order
  → account.move (posted out_invoice)
  → payment_state + amount_residual
```

The GET screen may show PAID. The POST dispense endpoint **re-reads** the invoice immediately before the stock write. If the invoice is no longer fully paid, the response is `409 unpaid` with: “Payment is required before dispensing. Complete payment at the cashier.”

Pharmacy cannot collect payment. Accountant / Cashier remains a separate permission.

---

## 4. Stock verification

**IMPLEMENTED** · **READ-ONLY** against Odoo `stock.quant`

Location: **WH/Stock** (internal location `complete_name = WH/Stock`). This is the Pharmacy Counter warehouse location already established. Stock is not summed from other locations.

Display for the pharmacist:

- Available: on-hand quantity at WH/Stock
- To dispense: prescribed quantity

On-hand includes quantity reserved for this delivery. That matches the controlled test (90 on-hand, 2 reserved, pharmacist sees 90).

The backend also re-reads on-hand immediately before validation. If on-hand is below the prescribed quantity, it returns `409 insufficient_stock` and does **not** dispense a smaller amount.

React never calculates stock. There is no Hospital EMR stock table.

---

## 5. Dispense endpoint

**IMPLEMENTED** · **WRITE**

```
POST /openmrs/abikan-api/pharmacy/prescription/{orderUuid}/dispense
```

Browser body (optional): `{ "requestId": "<uuid>" }`.

The browser must **not** send a picking id, sale-order id, invoice id, product id, or quantity to apply. The server resolves:

```
orderUuid
  → OpenMRS order + patient
  → sale.order.line.external_order_id
  → sale.order
  → outgoing stock.picking
```

Also implemented (read):

| Method | Path |
|---|---|
| GET | `/openmrs/abikan-api/pharmacy/queue` |
| GET | `/openmrs/abikan-api/pharmacy/patient/{patientUuid}` |
| GET | `/openmrs/abikan-api/pharmacy/prescription/{orderUuid}` |

Odoo credentials stay in `abikan-api`. Unauthenticated → `401`. User without Pharmacy permission → `403`.

---

## 6. Odoo operation

**CONFIRMED** · **WRITE** via ORM only

```
stock.picking.action_set_quantities_to_reservation
stock.picking.button_validate
```

If `button_validate` returns the standard immediate-transfer wizard, the server calls `stock.immediate.transfer.process`. If it returns a backorder wizard, the server stops with `409 partial_not_supported`.

Do **not**:

- write `stock.quant`
- write `stock.move`
- write picking `state`
- write `qty_delivered`
- use SQL

`action_set_quantities_to_reservation` may return `None` over XML-RPC (`allow_none`). That is ignored if validation then succeeds. Success is accepted only after a re-read shows `picking.state = done`.

Live test on **WH/OUT/00002**: `button_validate` returned success; picking became `done`; `quantity_done = 2`; `qty_delivered = 2`. **CONFIRMED.**

---

## 7. Partial dispensing policy

**IMPLEMENTED** as full quantity only · **COMING SOON** for partials

This phase dispenses the **full prescribed quantity** or nothing.

If stock is insufficient, the pharmacist sees **Insufficient stock** with requested vs available. The server does not create a backorder and does not silently dispense 6 of 10.

If Odoo still offers `stock.backorder.confirmation`, Hospital EMR refuses it.

Partial dispensing is a later workflow. **REQUIRES HOSPITAL DECISION** on how remaining quantity, payment, and the chart should behave.

---

## 8. Double-dispensing protection

**IMPLEMENTED**

1. Frontend: Dispense is disabled while the request is in flight; confirmation is required first.
2. Server in-memory lock keyed by OpenMRS order UUID (and optional `requestId`).
3. Immediate re-read of `stock.picking.state` before `button_validate`.
4. If already `done`, or `qty_delivered >= qty`, return `409 already_dispensed` without another stock write.
5. Retry with the **same** `requestId` after success returns the current DISPENSED payload (`alreadyDispensed: true`) and does not validate again.

Live:

| Attempt | Result |
|---|---|
| First POST ORD-4 | `200` DISPENSED, stock 88, delivered 2 |
| Same `requestId` | `200` `alreadyDispensed: true`, stock still 88 |
| New `requestId` | `409 already_dispensed`, stock still 88 |

**CONFIRMED** no second stock transaction. The in-memory lock is per API process and is lost on restart; Odoo picking state remains the durable guard.

---

## 9. Payment race protection

**IMPLEMENTED**

The screen can be stale. Immediately before validation the server re-reads:

- invoice `payment_state`
- invoice `amount_residual`

Unpaid / partial / reversed → `409 unpaid`. No stock write.

Live unpaid block used existing ORD-2 / Tunde (draft S00001 was **not** confirmed): `409 unpaid`. **CONFIRMED.**

A live “became unpaid after the page opened” reversal was **NOT TESTED** (would modify a posted payment).

---

## 10. Stock race protection

**IMPLEMENTED**

On-hand is re-read immediately before validation. The actual reservation/consumption is Odoo’s `button_validate`. If Odoo rejects the move, Hospital EMR returns `502 odoo_dispense_failed` and does not show success.

Two pharmacists both seeing Available 10 for two different 10-tablet prescriptions: Odoo must reject the invalid one. **NOT TESTED** live (would require extra stock/prescriptions).

---

## 11. OpenMRS Dispensed limitation

**CONFIRMED** · not written

The installed Odoo 16 Dispensed Atomfeed path reads missing `ir.values` (`convert_dispensed`). Writing the OpenMRS Dispensed observation is unsafe until that path is fixed separately.

This phase:

- does **not** write OpenMRS Dispensed
- does **not** change `order_action`
- derives staff-facing **DISPENSED** from `stock.picking.state = done` and/or `qty_delivered >= ordered qty`

Live after dispense:

| Check | Result |
|---|---|
| ORD-4 `action` | **NEW** |
| `dateStopped` | null |
| `orderAttributes` | null |
| Dispensed obs for Aisha | none |

OpenMRS remains Ordered. Hospital EMR Pharmacy and Patient Account show DISPENSED from Odoo. **CONFIRMED.**

---

## 12. Permissions

**IMPLEMENTED**

| Actor | Dispense | Collect payment |
|---|---|---|
| Privilege `bahmni:clinical:dispense` | yes | no (unless they also have cashier rights) |
| SuperAdmin / System Developer | yes (backend) | yes (existing cashier rule) |
| Privilege `abikan:accountant` only | **no** | yes |
| `registration` user | **no** | **no** |

Frontend Pharmacy workspace is still gated by `bahmni:clinical:dispense` only (`canOpenPharmacy`). Accountant permission does not open Pharmacy.

OpenMRS roles were **not** modified. SuperAdmin was **not** granted to anyone new.

Live: `registration` GET queue and POST dispense → `403 forbidden`. **CONFIRMED.**

A dedicated pharmacist user (dispense without SuperAdmin) is **NOT TESTED**. `abikan.admin` has SuperAdmin **and** `bahmni:clinical:dispense`.

---

## 13. Audit / source of truth

**CONFIRMED** · Odoo records only · no second ledger

| Question | Where to look |
|---|---|
| Who dispensed? | Odoo picking `write_uid` (this install: XML-RPC **Administrator**) plus Hospital EMR response `recordedBy` (OpenMRS username, not stored in Odoo) |
| When? | `stock.picking.date_done` |
| Which patient? | Sale order partner / OpenMRS patient on the order |
| Which prescription? | `sale.order.line.external_order_id` = OpenMRS order UUID |
| What quantity / product? | `stock.move` on the picking (`quantity_done`, product) |

Mapping OpenMRS users onto Odoo users so `write_uid` is the named pharmacist is **REQUIRES HOSPITAL DECISION** / **COMING SOON**. Do not invent a Hospital EMR dispensing history table.

---

## 14. Patient Account behaviour

**CONFIRMED** · financial state unchanged

After dispensing Aisha / INV/2026/00002:

| Field | Value |
|---|---|
| Invoice | **PAID**, residual 0 |
| Payment | **PCSH1/2026/00002** posted, $2,300.00, unchanged |
| Pharmacy | **DISPENSED** |

Payment and dispensing stay separate events. Patient Account remains read-only. Accountant workflow was not modified.

---

## 15. UX decisions

**IMPLEMENTED**

- One primary action: **Dispense**, only when the server says `canDispense`
- Confirmation dialog before the stock write (patient, hospital number, drug, quantity, PAID, stock before/after)
- Disabled/blocked states always include a reason (“Payment is required…”, “already been dispensed”, insufficient stock)
- Allergies stay in the clinical alert bar, not a tab. Missing allergies = **Not recorded**
- No sale-order / invoice / picking / UUID / Atomfeed copy in the UI
- Ready-to-dispense cards wrap at 1024px so Dispense does not require horizontal scroll
- Buttons already use 44px minimum height
- Inventory, Low Stock, Reports remain **COMING SOON**

Visual click-through of the React confirmation dialog was **NOT TESTED**. The POST the button calls was executed against the live API.

---

## 16. Test results

**CONFIRMED** controlled object **WH/OUT/00002** / **ORD-4**

| Step | Result |
|---|---|
| A. Pharmacy queue | ORD-4 in Ready to dispense, **PAID** / **READY TO DISPENSE** |
| B. Open prescription | Aisha Bello, ABC200011, Paracetamol 500 mg — TEST, 2 Tablets, PAID, available 90, to dispense 2 |
| C–D. Confirm Dispense | API POST (UI confirmation implemented; visual click **NOT TESTED**) |
| E. Odoo validate | WH/OUT/00002 `button_validate` |
| F. After | picking **done**, delivered **2**, stock **88**, invoice **PAID**, payment unchanged, ORD-4 still **NEW**, no Dispensed obs |
| G–I. Refresh | GET remains **DISPENSED**; queue Ready list empty of ORD-4 |

Failure tests:

| Case | Result | Label |
|---|---|---|
| No session GET/POST | `401 unauthenticated` | **CONFIRMED** |
| `registration` GET/POST | `403 forbidden` | **CONFIRMED** |
| Unpaid ORD-2 POST | `409 unpaid` (S00001 not confirmed) | **CONFIRMED** |
| Second dispense | no second stock move | **CONFIRMED** |
| Insufficient stock | not executed (would change product 2385) | **NOT TESTED** |
| Odoo down | not executed | **NOT TESTED** |
| Dedicated `abikan:accountant` user without dispense | privilege still not created in OpenMRS | **NOT TESTED** |

`npm run build` (tsc + vite): **passed**.

---

## 17. Protected records

**CONFIRMED** unchanged

| Record | State after this phase |
|---|---|
| ORD-1 | NEW |
| ORD-2 | NEW |
| ORD-3 | NEW |
| S00001 | draft, amount 0.00 |
| S00002 | sale |
| INV/2026/00001 | posted, paid, residual 0 |
| PCSH1/2026/00001 | 11500.00 USD Cash |
| P00001 | purchase (not modified) |
| WH/IN/00001 | done |
| WH/OUT/00001 | done (already completed earlier) |
| Tax 15% / currency USD / Pharmacy Counter / Cash journal | unchanged |

---

## 18. Known limitations

**CONFIRMED** / **COMING SOON**

1. OpenMRS chart still says Ordered after a successful counter dispense. Staff-facing DISPENSED is Odoo-derived until `ir.values` / Dispensed feed is fixed.
2. Odoo `write_uid` is the XML-RPC service user (Administrator), not the named pharmacist.
3. In-memory idempotency is per `abikan-api` process.
4. Queue is built from sale-order lines that have `external_order_id` (up to 200). Prescriptions that never reached Odoo do not appear.
5. Partial dispensing is not offered.
6. Pharmacy still has no payment collection (intentional).
7. Inventory / low-stock / reports screens remain **COMING SOON**.

---

## 19. Future improvements

**COMING SOON** · **REQUIRES HOSPITAL DECISION** where noted

1. Fix Odoo 16 `ir.values` / `convert_dispensed`, then optionally write OpenMRS Dispensed **after** picking `done`.
2. Partial / short supply workflow (remaining quantity, payment, chart).
3. Map OpenMRS pharmacist → Odoo user for picking `write_uid`.
4. Dedicated pharmacist role without SuperAdmin.
5. Durable server-side idempotency beyond process memory.
6. Inventory and low-stock workplace (Odoo reads only).

---

## Live objects from this test (keep)

| Object | Result |
|---|---|
| ORD-4 `8e62a279-22e8-4e55-b97b-19d0bf438891` | OpenMRS still NEW |
| S00003 | sale, `qty_delivered = 2` |
| INV/2026/00002 | posted, **PAID**, residual 0 |
| PCSH1/2026/00002 | posted, 2300 USD Cash, unchanged |
| WH/OUT/00002 | **done**, `date_done` 2026-08-17 01:38:51 UTC |
| Product 2385 WH/Stock | on-hand **88**, reserved **0** |

---

## Stop

This phase stops at **DISPENSED** for the paid pharmacy prescription.

Do **not** proceed to Registration billing or other department charge workflows. Do **not** write OpenMRS Dispensed. `bahmni_sale.is_delivery_automated` remains disabled. `bahmni_sale.is_invoice_automated` remains True.

---

*End of implementation.*
