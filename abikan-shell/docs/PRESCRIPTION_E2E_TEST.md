# Isolated prescription → Pharmacy end-to-end test

Date: **19 Aug 2026** (Africa/Lagos, UTC+1). Development / test environment.

Related: `ACCOUNTANT_PAYMENT_E2E_TEST.md`, `PHARMACY_BILLING_DISPENSING_TEST.md`, `CONSULTATION_SAVE_FIX.md`.

This test proves:

```
Doctor prescribing UI
  → OpenMRS Drug Order
  → Atomfeed encounter event
  → Odoo pharmacy sale (origin API FEED SYNC)
  → confirm → posted invoice + assigned picking
  → Accountant CASH payment
  → Pharmacy READY TO DISPENSE
```

Clinical did **not** write Odoo directly. Dispensing was **not** performed. Laboratory was **not** started. Architecture was **not** changed.

---

## Verdict

**PASS.** One isolated test patient, one OPD visit, one Consultation encounter, one Drug Order, one pharmacy sale, one posted invoice, and one CASH payment. Pharmacy shows **READY TO DISPENSE**. Stock on hand did not decrease.

---

## 1. Test patient

Created for this test. Not Adaeze, Aisha, Tunde, Ibrahim, Chinedu, Fatima, or Ngozi.

| Field | Value |
|---|---|
| Name | **ABIKAN E2E TEST PATIENT** |
| MRN | `ABC200016` |
| OpenMRS uuid | `f242364e-b70f-4fec-b29e-8ad4fbe147b5` |
| Sex / age (OpenMRS) | Male, 36 years |
| Odoo partner | id **22**, `ref=ABC200016`, uuid matches |
| Partner created | 2026-08-19 03:03:30 UTC (patient feed) |

---

## 2. Visit

Existing OpenMRS OPD visit. No second visit model.

| Field | Value |
|---|---|
| uuid | `6478a94e-1657-4abe-9271-7cf92b821576` |
| Type | OPD (`54f43754-c6ce-4472-890e-0f28acaeaea6`) |
| Location | OPD-1 (`5e232c47-8ff5-4c5c-8057-7e39a64fefa5`) |
| Start | `2026-08-19T02:58:36.000+0000` (**03:58** Africa/Lagos) |
| Stop | null (open) |

The first generated start was slightly *after* wall clock and would have hit the visit-window save guard. This isolated visit only was started ~5 minutes before then-now so the doctor could save. Ibrahim’s visit was not changed.

Clinical Today’s Patients listed: **ABIKAN E2E TEST PATIENT · ABC200016 · OPD · 03:58 · Open**.

---

## 3. Encounter

Simple consultation. No vitals, no diagnosis, no consultation fee. Prescribe saved through the existing Bahmni encounter write.

| Field | Value |
|---|---|
| uuid | `9a88a85d-a2db-4656-94bd-fb55c1b01688` |
| Type | Consultation (`d34fe3ab-5e07-11ef-8f7c-0242ac120002`) |
| Datetime | `2026-08-19T03:05:51.000+0000` (**04:05** Africa/Lagos) |
| Visit | `6478a94e-1657-4abe-9271-7cf92b821576` |
| Patient | ABC200016 |
| Orders on encounter | 1 (`5e744fe0-d516-4255-b45f-3e4209e11c45`) |
| Obs | 0 |

Encounter datetime is after visit start. The visit-not-started warning did not appear.

**Create consultation fee was not clicked.**

---

## 4. Drug Order

Created from the Doctor prescribing UI (`POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` with `drugOrders[]`). Not posted to Odoo from Clinical.

Closest catalogue drug: **Paracetamol 500 mg — TEST** (already configured). No new drug catalogue entry.

The UI has no free-text instruction field. Configured option **As directed** was used instead of a typed “ABIKAN E2E TEST” line.

| Field | Value |
|---|---|
| Order number | **ORD-7** |
| Order uuid | `5e744fe0-d516-4255-b45f-3e4209e11c45` |
| Patient | ABC200016 / `f242364e-…` |
| Visit | `6478a94e-…` |
| Encounter | `9a88a85d-…` |
| Drug | Paracetamol 500 mg — TEST (`1c88be47-1ea9-4908-a57f-dc5ebd47caec`) |
| Concept | Acetaminophen |
| Dose | 1 Tablet |
| Route | Oral |
| Frequency | Twice a day |
| Duration | 1 Days |
| Quantity | 2 Tablet |
| Instruction | As directed |
| Care setting | OUTPATIENT |
| Action | NEW |
| Status in Clinical | Ordered |
| Voided / stopped | no |
| Provider | Clinical Doctor (`doctor.abikan`) |

Dose is **1 Tablet** of the 500 mg TEST tablet, not a 500 mg dose unit. That matches the existing catalogue.

---

## 5. Atomfeed event

Processed by the existing encounter feed. Configuration was not changed. No replacement integration.

| Field | Value |
|---|---|
| `event_records.id` | **3905** |
| Event uuid | `ec5107fd-b70c-407b-9d9f-729dcf366c1a` |
| Title / category | Encounter |
| Timestamp | 2026-08-19 03:05:54 UTC |
| Object | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter/9a88a85d-…?includeAll=true` |
| Patient feed | event **3904** for `f242364e-…` at 03:03:24 UTC |
| Worker | `OpenERPSaleOrderEventWorker` on `encounter/recent` |
| Processed | **2026-08-19 03:06:00.200 UTC** |
| Marker after process | `lastReadEntryId=tag:atomfeed.ict4h.org:ec5107fd-…` |
| Failed events for this uuid | **0** |

Linkage used by Pharmacy: `sale.order.line.external_order_id` = OpenMRS order uuid `5e744fe0-…`. Encounter uuid is on `external_id`.

Atomfeed creates a **draft** pharmacy sale. It does **not** confirm or post the invoice. That is existing behaviour (same as Aisha ORD-4 → S00003).

---

## 6. Odoo sale / invoice

Not created from Clinical. Not created by hand as a new quotation.

| Sale | Value |
|---|---|
| id | **21** |
| name | **S00021** |
| origin | `API FEED SYNC` |
| shop | Pharmacy Counter |
| partner | 22 ABIKAN E2E TEST PATIENT [ABC200016] |
| `external_order_id` | `5e744fe0-d516-4255-b45f-3e4209e11c45` (ORD-7) |
| `external_id` | `9a88a85d-…` (encounter) |
| Product | 2385 Paracetamol 500 mg — TEST |
| Qty | 2.00 |
| `price_unit` | 1000.00 |
| Total | **2300.00** USD (includes 15% tax already on the product) |
| Created | 2026-08-19 03:06:00 UTC (~6s after the order) |
| After Atomfeed | **draft** |
| After confirm | **sale**, `invoice_status=invoiced` |

Confirm used the existing Odoo `sale.order.action_confirm` on **S00021 only** (same step as the 17 Aug Aisha E2E). Hospital EMR Pharmacy/Accountant UIs do not confirm pharmacy quotations. This is not a Clinical→Odoo shortcut.

| Invoice | Value |
|---|---|
| id | **29** |
| number | **INV/2026/00020** |
| type | out_invoice |
| state | posted |
| origin | S00021 |
| Created | 2026-08-19 03:09:22 UTC (on confirm, `is_invoice_automated=True`) |
| Total | 2300.00 |
| Residual before pay | 2300.00 |
| `payment_state` before pay | not_paid |
| Residual after pay | **0.00** |
| `payment_state` after pay | **paid** |

| Picking | Value |
|---|---|
| id | **4** |
| name | **WH/OUT/00003** |
| origin | S00021 |
| state | **assigned** (not done) |

Picking was **not** validated.

---

## 7. Payment

Accountant UI: `accountant.abikan` → Collect payment → INV/2026/00020 → **Cash** (journal CSH1 id 6) → Confirm payment.

Path: `POST /openmrs/abikan-api/accountant/payment` → Odoo `account.payment.register`. One payment only.

| Field | Value |
|---|---|
| id | **10** |
| number | **PCSH1/2026/00008** |
| amount | 2300.00 USD |
| journal | Cash CSH1 id 6 |
| type | inbound |
| state | posted |
| partner | 22 ABC200016 |
| date | 2026-08-19 |
| created | 2026-08-19 03:13:25 UTC |
| `ref` / request id | `1080f3c3-bf19-4e4c-a968-b893baedf1a3` |
| Reconciled invoice | INV/2026/00020 |

Patient Account after pay: billed **$2,300.00**, paid **$2,300.00**, outstanding **$0.00**. UI: “Payment recorded · PCSH1/2026/00008 · $2,300.00 · Cash”.

---

## 8. Pharmacy status

| When | Payment | Dispensing | Can dispense |
|---|---|---|---|
| After Atomfeed (draft SO) | UNPAID | UNPAID | no — proceed to cashier |
| After confirm + unpaid invoice | UNPAID | UNPAID | no — proceed to cashier |
| After CASH payment | **PAID** | **READY TO DISPENSE** | yes |

Browser (`pharmacy.abikan`, `#/pharmacy`):

- Department Pharmacy. No location picker.
- Needs attention: **ABIKAN E2E TEST PATIENT ABC200016 Paracetamol 500 mg — TEST 2 Tablets · PAID · READY TO DISPENSE**.
- Ready to Dispense counter: **1**.
- Dispense button was visible. **It was not clicked.**

API: `canDispense=true`, `blockReason=null`, `stockOnHand=88`, preview `stockAfter=86` (not applied).

---

## 9. Stock / reservation

Product **2385** Paracetamol 500 mg — TEST, WH/Stock location **8**.

| Moment | On hand | Reserved |
|---|---|---|
| Before prescription | **88.00** | 0.00 |
| After Atomfeed draft S00021 | 88.00 | 0.00 |
| After confirm (invoice + picking) | 88.00 | **2.00** |
| After CASH payment | **88.00** | **2.00** |

On-hand did **not** fall because the prescription was created or paid. Reservation of 2 is from confirm (`reservation_method=at_confirm`). Picking WH/OUT/00003 stays assigned.

---

## 10. Permissions

No department gained extra rights. Isolation checked after each logout/login.

| Actor | Prescribe | Pay | Dispense |
|---|---|---|---|
| `doctor.abikan` | yes (Clinical Prescribe) | no (403 accountant API; no Pay on chart) | no (403 pharmacy API) |
| `pharmacy.abikan` | no (Pharmacy workspace only; no prescribe UI) | no (403 accountant API; “Pharmacy does not collect payment”) | yes (READY TO DISPENSE; not used) |
| `accountant.abikan` | no (403 pharmacy queue; no Clinical) | yes (CASH on INV/2026/00020) | no (403 dispense API) |
| `reception.abikan` | no (`#/doctor` → “You do not have access to this department”) | no (403; copy says Reception does not collect payment) | no (403) |
| `nurse.abikan` | no (`#/doctor` → no access) | no (403) | no (403) |

Doctor Clinical: no location picker. Today’s Patients worked. No Pay / Dispense.

---

## 11. Duplicate protection

Prescribe was clicked twice in one tick. The button went to **Saving prescription…** / disabled. Network: **exactly one** `POST …/bahmnicore/bahmniencounter`. OpenMRS: **one** visit drug order (ORD-7 only). No second clinical prescription was created.

---

## 12. Browser test

| Step | Result |
|---|---|
| `doctor.abikan` → Clinical → patient → prescribe Paracetamol 500 mg — TEST | PASS |
| Logout → `pharmacy.abikan` → prescription UNPAID | PASS |
| Logout → `accountant.abikan` → CASH on INV/2026/00020 | PASS |
| Logout → `pharmacy.abikan` → PAID / READY TO DISPENSE | PASS |
| Logout → `reception.abikan` / `nurse.abikan` → cannot open Clinical | PASS |

Department label matched the signed-in account after every login. Dispense was not clicked.

---

## 13. npm test

```
cd abikan-shell && npm test
```

**63 passed, 0 failed.** This is not the E2E proof; live records above are.

---

## 14. npm build

```
cd abikan-shell && npm run build
```

**PASS** (`tsc --noEmit && vite build`). Bundle `index-Cxa_6lzP.js`. Build success is not E2E proof.

---

## 15. Records created

| Record | Id / name |
|---|---|
| OpenMRS patient | ABC200016 / `f242364e-b70f-4fec-b29e-8ad4fbe147b5` |
| Odoo partner | id 22 |
| OpenMRS visit | `6478a94e-1657-4abe-9271-7cf92b821576` |
| Consultation encounter | `9a88a85d-a2db-4656-94bd-fb55c1b01688` |
| Drug Order | ORD-7 / `5e744fe0-d516-4255-b45f-3e4209e11c45` |
| Atomfeed encounter event | `event_records` 3905 / `ec5107fd-…` |
| Atomfeed patient event | 3904 |
| Odoo sale | **S00021** id 21 |
| Odoo invoice | **INV/2026/00020** id 29 |
| Odoo payment | **PCSH1/2026/00008** id 10 |
| Delivery order | **WH/OUT/00003** id 4 (assigned, not done) |

---

## 16. Records intentionally not changed

| Record | Left as |
|---|---|
| Tunde Bakare / S00001 | draft, amount 0.00, product 110 |
| Adaeze, Aisha, Ibrahim, Chinedu, Fatima, Ngozi | existing charts / invoices / payments untouched |
| Ibrahim visit `481610eb-…` | not rewritten |
| Existing payments PCSH1/2026/00001–00007 and bank receipts | not modified |
| Product 110 Paracetamol 500 mg | not used |
| Beds | still 0 occupied (Nursing board unchanged by this test) |
| OpenMRS Dispensed / order stopped | not written |
| Drug catalogue | no new drug |
| Atomfeed / OpenMRS / Odoo config | not modified |
| `bahmni_sale.is_invoice_automated` | remains True |
| `bahmni_sale.is_delivery_automated` | remains off |

---

## 17. Exact point of failure if unsuccessful

**None.** Workflow stopped at READY TO DISPENSE as instructed.

### Known limitations (not failures)

1. Atomfeed leaves the pharmacy sale in **draft**. Invoice and reservation appear only after `action_confirm`. Hospital EMR has no Pharmacy “confirm quotation” button; this test used the same existing Odoo confirm as the 17 Aug pharmacy E2E, on S00021 only.
2. Instruction is a configured option (**As directed**), not free text.
3. Dose unit is Tablet of a 500 mg product, not “500 mg” as the dose unit.
4. Tax 15% is already on product 2385; due is 2300 USD, not 2000.
5. Currency remains USD on this installation.
6. Visit start for this isolated visit was set a few minutes before wall clock so the visit-window guard would allow save.

---

*End of test. Do not dispense ORD-7. Do not proceed to Laboratory.*
