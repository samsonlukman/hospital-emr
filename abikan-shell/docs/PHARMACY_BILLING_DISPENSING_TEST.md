# Pharmacy bill → pay → dispense controlled test

Date: **16–17 Aug 2026** (UTC). Live transactions. Results are from OpenMRS MySQL, Odoo PostgreSQL, and Odoo XML-RPC — not inferred.

Related: `docs/PHARMACY_BILLING_DISPENSING_SEPARATION.md`.

Hospital EMR UI was **not** changed. OpenMRS Dispensed was **not** written. Currency was **not** changed. S00001, ORD-1, ORD-2, P00001, and product 110 were **not** modified.

---

## Verdict

**CONFIRMED:** with `is_delivery_automated` off and `is_invoice_automated` on, this installation supports:

```
OpenMRS prescription
  → draft sale.order
  → confirm → posted invoice + unvalidated picking (on-hand stock unchanged)
  → Cash payment → invoice paid (picking still open)
  → validate picking → stock 100 → 90
  → OpenMRS remains Ordered
```

The setting was **left off**. Invoice automation remains **True**.

---

## 1. Configuration before test

| Key | id | value | Effective `bool(get_param)` |
|---|---|---|---|
| `bahmni_sale.is_delivery_automated` | 29 | `True` | **True** |
| `bahmni_sale.is_invoice_automated` | 31 | `True` | **True** |

Company currency: **USD** id 2.

---

## 2. Configuration after test

Disabled with Odoo `ir.config_parameter.set_param('bahmni_sale.is_delivery_automated', False)` (XML-RPC as admin). That **deleted** row 29. The string `"False"` was **not** written.

| Check | Result | Label |
|---|---|---|
| `get_param('bahmni_sale.is_delivery_automated')` | Python `False` | **CONFIRMED** |
| `bool(get_param(...))` | `False` | **CONFIRMED** |
| Row 29 in `ir.config_parameter` | **gone** | **CONFIRMED** |
| `bahmni_sale.is_invoice_automated` | still `True` (id 31) | **CONFIRMED** |
| Docker restart | not required, not done | **CONFIRMED** |

Left in this state on purpose.

---

## 3. Test patient

**Not** John Adewale / ORD-1. **Not** Tunde Bakare / ORD-2.

| Field | Value |
|---|---|
| Name | Adaeze Okafor |
| MRN | `ABC200003` |
| OpenMRS uuid | `93da7c9f-1de7-4d8b-be5e-2e49deb5c9d2` |
| Odoo partner | id **8** |
| New visit | `62196804-6c5b-4f04-a0ae-d4c1035046f6` (OPD, OPD-1, open) |

A new visit was required because her previous OPD visit was already stopped. One visit, one encounter, one drug order.

---

## 4. OpenMRS prescription

| Field | Value |
|---|---|
| Order number | **ORD-3** |
| Order uuid | `e7dafc6a-86cd-44e3-a8bf-4e3232bdfc7f` |
| Encounter uuid | `53fa8f3d-d04b-477e-84a8-4733eb6863ea` |
| Visit uuid | `62196804-6c5b-4f04-a0ae-d4c1035046f6` |
| Drug | Paracetamol 500 mg — TEST |
| OpenMRS drug uuid | `1c88be47-1ea9-4908-a57f-dc5ebd47caec` |
| Qty | 10 Tablet |
| Dose | 1 Tablet, Oral, Twice a day, 5 Days |
| `order_action` | NEW |
| `date_stopped` | NULL |
| `fulfiller_status` | NULL |
| `orderAttributes` | none |
| Created | 2026-08-16 23:28:29 UTC |

Write: `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with `drugOrders[]`. Exactly **one** prescription. **CONFIRMED.**

---

## 5. Atomfeed event

| Field | Value |
|---|---|
| Feed | `http://openmrs:8080/openmrs/ws/atomfeed/encounter/recent` |
| Marker after consume | `tag:atomfeed.ict4h.org:583cda1d-1695-4597-859a-14b6a0b2a845` |
| Content | encounter `53fa8f3d-d04b-477e-84a8-4733eb6863ea` |
| Sale order created | **S00002** id 2 at 2026-08-16 23:28:31 UTC (~2s after the order) |
| Manual SO create | **not done** |
| Extra SOs | **none** (only S00001 + S00002) |
| This event in `failed_events` | **no** (existing failed rows are old lab-feed errors from 12 Aug) |

**CONFIRMED.**

---

## 6. Sale order

| Field | Value |
|---|---|
| id | **2** |
| name | **S00002** |
| partner | Adaeze Okafor [ABC200003] |
| origin | `API FEED SYNC` |
| product | 2385 Paracetamol 500 mg — TEST |
| qty | 10.00 Units |
| `price_unit` | 1000.00 |
| `external_order_id` | `e7dafc6a-86cd-44e3-a8bf-4e3232bdfc7f` (ORD-3) |
| Initial state | **draft** |
| After confirm | **sale** |
| `invoice_status` after confirm | **invoiced** |
| `delivery_status` after picking | **full** |
| Untaxed | 10000.00 USD |
| Tax | 1500.00 USD (Tax 15% already on product 2385) |
| `amount_total` | **11500.00** USD |

Draft-before-confirm: **CONFIRMED.**  
Price 1000 × 10: **CONFIRMED.**  
Total 10000: **UNEXPECTED** — product already has Tax 15%, so SO total is **11500**. Tax was not removed (product change forbidden).

S00001 remained **draft** throughout.

---

## 7. Invoice

Created automatically on confirm (`is_invoice_automated=True`).

| Field | Value |
|---|---|
| id | 1 |
| number | **INV/2026/00001** |
| type | `out_invoice` |
| state | **posted** |
| origin | S00002 |
| `amount_untaxed` | 10000.00 |
| `amount_tax` | 1500.00 |
| stored `amount_total` | **10000.00** |
| `amount_residual` before pay | **11500.00** |
| `payment_state` after confirm | `not_paid` |
| `payment_state` after pay | **paid** |
| residual after pay | 0.00 |
| created | 2026-08-16 23:28:47 UTC |

Invoice created + posted: **CONFIRMED.**

`amount_total` 10000 vs residual/tax 11500: **UNEXPECTED** (Bahmni invoice `amount_total` does not match the receivable 11500). Payment used the wizard default **11500** (residual). After that, `payment_state=paid`.

---

## 8. Payment

| Field | Value |
|---|---|
| id | 1 |
| number | **PCSH1/2026/00001** (journal entry `account.move` id 2) |
| amount | **11500.00 USD** |
| journal | Cash **CSH1** id 6 |
| method | Manual inbound |
| type | inbound |
| partner | 8 Adaeze Okafor |
| state | posted / reconciled |
| POS | not used |
| created | 2026-08-16 23:29:27 UTC |

**CONFIRMED.** No other payments exist.

---

## 9. Picking

| Stage | Picking | state | `quantity_done` | `qty_delivered` |
|---|---|---|---|---|
| Before confirm | none for S00002 | — | — | 0 |
| After confirm | **WH/OUT/00001** id 2 | **assigned** | 0 | 0 |
| After payment | WH/OUT/00001 | **assigned** | 0 | 0 |
| After validate | WH/OUT/00001 | **done** | 10 | 10 |

| Field | Value |
|---|---|
| type | Delivery Orders (id 2) |
| origin | S00002 |
| `sale_id` | 2 |
| `immediate_transfer` | **false** |
| created | 2026-08-16 23:28:47 UTC (same second as invoice) |
| `date_done` | 2026-08-16 23:29:58 UTC |

Purchase receipt **WH/IN/00001** stayed `done` / origin P00001. **CONFIRMED** not touched.

Validate used `action_set_quantities_to_reservation` then `button_validate` on picking **2 only**. XML-RPC raised a marshal error because `action_set_quantities_to_reservation` returns `None`; the write still applied (`quantity_done` became 10) and `button_validate` returned True. **CONFIRMED** dispensed via normal Odoo validate, not by editing `stock.quant`.

---

## 10. Stock before

Product 2385, location **8 WH/Stock**:

| When | quantity | reserved |
|---|---|---|
| Baseline / pre-confirm | **100.00** | 0.00 |
| After confirm | **100.00** | **10.00** |
| After payment | **100.00** | 10.00 |

On-hand 100 after confirm: **CONFIRMED.**  
Reservation 10 after confirm: **CONFIRMED** (expected; not a quantity decrease).  
Location 4 Vendors balancing quant −100 (from P00001) unchanged.

---

## 11. Stock after

After picking validate:

| Location | quantity | reserved |
|---|---|---|
| 8 WH/Stock | **90.00** | 0.00 |
| 5 Partners/Customers | **10.00** | 0.00 |
| 4 Partners/Vendors | −100.00 | 0.00 |

100 → 90 at WH/Stock: **CONFIRMED.**  
+10 at Customers is standard Odoo delivery destination, not a second consumption. Product 110 still has no WH/Stock quant.

---

## 12. Delivered quantity

`sale.order.line` S00002: `qty_delivered=10.00`, `qty_invoiced=10.00`.  
`sale.order.delivery_status=full`. **CONFIRMED.**

---

## 13. OpenMRS Dispensed state

| Check | Result | Label |
|---|---|---|
| ORD-3 `order_action` | NEW | **CONFIRMED** Ordered |
| ORD-3 `date_stopped` | NULL | **CONFIRMED** |
| REST `orderAttributes` | none | **CONFIRMED** |
| obs concept 128 (Dispensed) | 0 rows | **CONFIRMED** not written |
| `order_attribute` | 0 rows | **CONFIRMED** |

Intentional. Dispensed feed path remains unsafe.

ORD-1 and ORD-2 still NEW / not stopped. **CONFIRMED.**

---

## 14. Exact timestamps (UTC)

| Event | Time |
|---|---|
| Visit + encounter datetime | 2026-08-16 23:28:27 |
| Encounter `date_created` | 2026-08-16 23:28:29 |
| ORD-3 created / activated | 2026-08-16 23:28:29 |
| S00002 created | 2026-08-16 23:28:31.024592 |
| Pre-confirm snapshot | 2026-08-16 23:28:42 |
| S00002 confirmed / invoice + picking created | 2026-08-16 23:28:47 |
| Payment created | 2026-08-16 23:29:27.775154 |
| Picking validated / `date_done` | 2026-08-16 23:29:58 |
| Post-dispense snapshot | 2026-08-16 23:30:05 |

---

## 15. Warnings

1. **Tax 15%** is already on product 2385. SO total is 11500 USD, not 10000. Do not treat 1000 as ₦1,000.
2. Invoice stored `amount_total=10000` while receivable/residual was **11500**. Hospital EMR must use residual / tax-inclusive due, not the stored `amount_total` blindly.
3. Confirm **reserves** 10 Units (`reserved_quantity=10`) while on-hand stays 100. Available-to-promise drops before dispense.
4. `action_set_quantities_to_reservation` returns `None` over XML-RPC (`allow_none`). Callers should ignore that fault if `quantity_done` updated, then call `button_validate`.
5. Historical `failed_events` (lab feed, 12 Aug) are unrelated. Not cleaned.

---

## 16. Unexpected behaviour

| Item | Label |
|---|---|
| Invoice `amount_total` 10000 vs residual 11500 | **UNEXPECTED** (Bahmni amount field) |
| Payment 11500 instead of planned 10000 | **CONFIRMED** necessary to reach `paid` |
| Picking `immediate_transfer=false` despite confirm context `default_immediate_transfer=True` | **CONFIRMED** — reservation path used |
| Stock at Customers +10 after delivery | **CONFIRMED** standard Odoo; WH/Stock 90 |
| Delivery automation disabled by deleting the parameter | **CONFIRMED** as designed |

Nothing in the stop list occurred:

- Stock did **not** decrease before picking validate
- Invoice was created and posted
- Payment registered; picking stayed `assigned`
- Picking validated after payment; stock 100→90
- One prescription, one new SO
- S00001, ORD-1, ORD-2, P00001 unchanged
- Currency still USD
- OpenMRS Dispensed not written

---

## Protected records (final)

| Record | Final state |
|---|---|
| S00001 | draft, amount 0.00, product 110 |
| ORD-1 | NEW, uuid `e7eb086a-ce26-42d2-87ba-0c17f22e3a1b` |
| ORD-2 | NEW, uuid `270b6a0d-48d3-430d-b096-01e040b1cb5a` |
| P00001 | purchase |
| WH/IN/00001 | done |
| Supplier 18 | untouched |
| Pharmacy Counter / Drug Order / Tablet→Units | untouched |
| Currency | USD id 2 |

---

## Final live objects from this test (keep)

| Object | id / name |
|---|---|
| OpenMRS ORD-3 | `e7dafc6a-86cd-44e3-a8bf-4e3232bdfc7f` |
| Odoo S00002 | id 2, state `sale` |
| Invoice INV/2026/00001 | posted, paid |
| Payment PCSH1/2026/00001 | 11500 USD Cash |
| Picking WH/OUT/00001 | done |
| Product 2385 WH/Stock | **90 Units** |

---

## Hospital EMR backend states (for later UI)

Do not implement yet. Proven fields:

| Display | Read |
|---|---|
| UNPAID | invoice missing or `payment_state` in `not_paid` / `partial` |
| PAID | `account.move.payment_state` in `paid` / `in_payment` |
| READY TO DISPENSE | PAID and outgoing picking not `done` (`qty_delivered` < qty) |
| DISPENSED | `qty_delivered` ≥ ordered qty and/or picking `done` |
| Join | `sale.order.line.external_order_id` = OpenMRS order uuid |

Clinical source of truth: OpenMRS order. Financial/stock source of truth: Odoo.

---

*End of test. `bahmni_sale.is_delivery_automated` remains disabled. `bahmni_sale.is_invoice_automated` remains True.*
