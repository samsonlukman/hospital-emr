# Accountant payment end-to-end test

Date: **17 Aug 2026** (UTC). Controlled isolated TEST only.

Related: `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `PHARMACY_BILLING_DISPENSING_TEST.md`.

This test proves:

```
OpenMRS TEST prescription
  → Atomfeed → draft sale.order
  → confirm → posted UNPAID invoice + assigned picking (on-hand stock unchanged)
  → Hospital EMR cashier POST → Odoo account.payment.register
  → invoice PAID / residual 0
  → Patient Account PAID
  → Pharmacy READY TO DISPENSE
```

Payment did **not** validate the picking, reduce on-hand stock, or write OpenMRS Dispensed.

Status labels: **CONFIRMED** · **FAILED** · **BLOCKED** · **NOT TESTED** · **UNEXPECTED**

---

## Verdict

**CONFIRMED.** One isolated TEST invoice was created and paid through Hospital EMR. Pharmacy is **READY TO DISPENSE**. Dispensing was not performed.

---

## 1. Test patient

**CONFIRMED** — existing patient with an Odoo partner and no sale order. Not created. Not John Adewale / Tunde Bakare / Adaeze Okafor.

| Field | Value |
|---|---|
| Name | Aisha Bello |
| MRN | `ABC200011` |
| OpenMRS uuid | `30f5ee44-063b-405b-8797-4285c65aeaff` |
| Odoo partner | id **16** |
| New visit | `43036153-db2d-4ab9-bbef-973db24c5672` (OPD, OPD-1, open) |

A new visit was required because she had none.

---

## 2. Test prescription

**CONFIRMED**

Write: `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with `drugOrders[]`. Exactly **one** prescription.

| Field | Value |
|---|---|
| Order number | **ORD-4** |
| Order uuid | `8e62a279-22e8-4e55-b97b-19d0bf438891` |
| Encounter uuid | `f057e5f5-3381-4fb8-9726-1b999678fa02` |
| Visit uuid | `43036153-db2d-4ab9-bbef-973db24c5672` |
| Drug | Paracetamol 500 mg — TEST |
| OpenMRS drug uuid | `1c88be47-1ea9-4908-a57f-dc5ebd47caec` |
| Qty | **2 Tablet** |
| Dose | 1 Tablet, Oral, Twice a day, 1 Day |
| `order_action` | NEW |
| `date_stopped` | NULL |
| `fulfiller_status` | NULL |
| `orderAttributes` | none |
| Created | 2026-08-17 00:53:58 UTC |

---

## 3. Sale order

**CONFIRMED** — created by Atomfeed / odoo-connect. Not created manually.

| Field | Value |
|---|---|
| id | **3** |
| name | **S00003** |
| partner | Aisha Bello [ABC200011] |
| origin | `API FEED SYNC` |
| shop | Pharmacy Counter |
| product | 2385 Paracetamol 500 mg — TEST |
| qty | 2.00 Units |
| `price_unit` | 1000.00 |
| `external_order_id` | `8e62a279-22e8-4e55-b97b-19d0bf438891` (ORD-4) |
| Initial state | **draft** |
| After confirm | **sale** |
| `invoice_status` after confirm | **invoiced** |
| Untaxed | 2000.00 USD |
| Tax | 300.00 USD (Tax 15% already on product 2385) |
| `amount_total` | **2300.00** USD |
| Created | 2026-08-17 00:54:00 UTC (~2s after the order) |

S00001 remained **draft**. S00002 remained **sale**.

---

## 4. Invoice

**CONFIRMED** — created automatically on confirm (`is_invoice_automated=True`).

| Field | Value |
|---|---|
| id | 3 |
| number | **INV/2026/00002** |
| type | `out_invoice` |
| state | **posted** |
| origin | S00003 |
| department (Hospital EMR) | Pharmacy |
| `amount_untaxed` | 2000.00 |
| `amount_tax` | 300.00 |
| `amount_total` | **2300.00** |
| `amount_residual` before pay | **2300.00** |
| `payment_state` after confirm | `not_paid` / Hospital EMR **UNPAID** |
| `payment_state` after pay | **paid** / Hospital EMR **PAID** |
| residual after pay | 0.00 |
| currency | USD |

Unlike INV/2026/00001, stored `amount_total` matched residual (2300). Amounts were read from Odoo, not calculated in Hospital EMR.

---

## 5. Payment

**CONFIRMED**

Path:

```
Hospital EMR POST /openmrs/abikan-api/accountant/payment
  → account.payment.register
  → action_create_payments()
```

`account.payment` was **not** created directly. SQL and manual reconciliation were **not** used.

| Field | Value |
|---|---|
| id | 2 |
| number | **PCSH1/2026/00002** |
| amount | **2300.00 USD** |
| journal | Cash **CSH1** id 6 (existing; not reconfigured) |
| method | Manual inbound |
| partner | 16 Aisha Bello |
| state | posted |
| reconciled invoice | INV/2026/00002 (id 3) |
| requestId | `3ad48834-c684-4bed-b9e9-ad982a1aaaae` |
| recordedBy (OpenMRS) | abikan.admin |
| created | 2026-08-17 00:55:27 UTC |

The cashier dashboard GET showed this invoice as the only unpaid bill before payment. The payment POST is the same write the Cashier screen uses. A visual click-through of the React form was **NOT TESTED**; the production backend path was.

---

## 6. Payment journal

**CONFIRMED** — existing Cash journal id 6. Bank BNK1 id 7 was present and unused. Journals were not created or renamed.

---

## 7. Patient Account result

**CONFIRMED** — refreshed in the payment response and again on an independent GET.

| Check | Before pay | After pay |
|---|---|---|
| Outstanding | $2,300.00 | $0.00 |
| Already paid | $0.00 | $2,300.00 |
| Invoice | UNPAID | **PAID** residual $0.00 |
| Pharmacy row | UNPAID | **PAID** / **READY TO DISPENSE** |
| Payment history | empty | **PCSH1/2026/00002** $2,300.00 Cash → INV/2026/00002 |

No Hospital EMR ledger was created.

---

## 8. Pharmacy result

**CONFIRMED**

| Display | Value |
|---|---|
| Payment | PAID |
| Dispensing | **READY TO DISPENSE** |
| Picking | WH/OUT/00002 `assigned` |

---

## 9. Stock before / after

Product 2385, location **8 WH/Stock**:

| When | quantity | reserved |
|---|---|---|
| Baseline / pre-confirm | **90.00** | 0.00 |
| After confirm | **90.00** | **2.00** |
| After payment | **90.00** | 2.00 |

On-hand 90 after confirm and after payment: **CONFIRMED.**  
Reservation 2 after confirm: **CONFIRMED** (expected; not a quantity decrease).  
Vendors −100 and Customers +10 (from the earlier Adaeze dispense) unchanged.

---

## 10. Picking state

| Stage | Picking | state |
|---|---|---|
| After confirm | **WH/OUT/00002** id 3 | **assigned** |
| After payment | WH/OUT/00002 | **assigned** |

`immediate_transfer` false. `qty_delivered` still 0. **Not validated.**

Protected WH/IN/00001 and WH/OUT/00001 stayed `done`.

---

## 11. OpenMRS Dispensed state

**CONFIRMED** untouched

| Check | Result |
|---|---|
| ORD-4 `order_action` | NEW |
| ORD-4 `date_stopped` | NULL |
| REST `orderAttributes` | none |
| `order_attribute` rows | 0 |
| obs concept 128 (Dispensed) | 0 |

ORD-1, ORD-2, ORD-3 still NEW / not stopped.

---

## 12. Duplicate-payment result

**CONFIRMED**

Second POST with a **new** `requestId` against INV/2026/00002:

| Result | Value |
|---|---|
| HTTP | **409** |
| code | `invoice_already_paid` |
| message | `INV/2026/00002 is already paid.` |
| Payment count after | still **2** (PCSH1/2026/00001 + PCSH1/2026/00002) |

---

## 13. Security result

| Check | Result | Label |
|---|---|---|
| Unauthenticated GET dashboard | 401 `unauthenticated` | **CONFIRMED** |
| Unauthenticated POST payment | 401 `unauthenticated` | **CONFIRMED** |
| `registration` user POST payment | 403 `forbidden` | **CONFIRMED** |
| Payment count after 403 | still 2 | **CONFIRMED** |
| Browser / Vite / `dist` Odoo credentials | none (`VITE_BAHMNI_ORIGIN` only) | **CONFIRMED** |
| Odoo username/password in payment JSON | not present | **CONFIRMED** |

---

## 14. Build result

**CONFIRMED**

```
npm run build
tsc --noEmit && vite build
✓ built in 623ms
```

No source changes were required for this test. Registration, Doctor, Nursing, Laboratory, Radiology, Pharmacy, Patient Account, and Accountant routes were not broken by the test records.

---

## 15. Protected records

**CONFIRMED** untouched

| Record | Final state |
|---|---|
| ORD-1 | NEW `e7eb086a-ce26-42d2-87ba-0c17f22e3a1b` |
| ORD-2 | NEW `270b6a0d-48d3-430d-b096-01e040b1cb5a` |
| ORD-3 | NEW `e7dafc6a-86cd-44e3-a8bf-4e3232bdfc7f` |
| S00001 | draft, amount 0.00 |
| S00002 | sale, invoiced |
| INV/2026/00001 | posted, paid, residual 0 |
| PCSH1/2026/00001 | 11500.00 USD Cash |
| P00001 | purchase (not modified) |
| WH/IN/00001 | done |
| WH/OUT/00001 | done |
| Product 2385 WH/Stock on-hand | **90 Units** (reserved 2 for the new TEST picking only) |
| Tax 15% / currency USD / Pharmacy Counter / Cash journal | unchanged |

---

## 16. Unexpected behaviour

| Item | Label |
|---|---|
| INV/2026/00002 `amount_total` equals residual 2300 | **CONFIRMED** (the earlier Adaeze 10000 vs 11500 mismatch did **not** repeat) |
| Visual React cashier click-through | **NOT TESTED** — same Hospital EMR POST used by the UI was executed |
| Partial payment / multi-invoice | **NOT TESTED** (out of scope) |
| Dedicated `abikan:accountant` privilege user | **NOT TESTED** — privilege still not created in OpenMRS |

Nothing in the stop list occurred:

- Stock did **not** decrease
- Picking was **not** validated
- OpenMRS Dispensed was **not** written
- Protected records were **not** edited
- Tax, currency, journals, and TEST catalogue were **not** changed

---

## New live objects from this test (keep)

| Object | id / name |
|---|---|
| OpenMRS ORD-4 | `8e62a279-22e8-4e55-b97b-19d0bf438891` |
| Odoo S00003 | id 3, state `sale` |
| Invoice INV/2026/00002 | posted, **paid**, residual 0 |
| Payment PCSH1/2026/00002 | 2300 USD Cash |
| Picking WH/OUT/00002 | **assigned** (do not validate in this phase) |
| Product 2385 WH/Stock | on-hand **90**, reserved **2** |

---

## Stop

This phase stops at **READY TO DISPENSE**.

Do **not** validate WH/OUT/00002. Do **not** write OpenMRS Dispensed. The earlier Adaeze test already proved paid → picking validate → stock 100 → 90.

---

*End of test. `bahmni_sale.is_delivery_automated` remains disabled. `bahmni_sale.is_invoice_automated` remains True.*
