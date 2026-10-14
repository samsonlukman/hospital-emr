# Accountant / Cashier — Phase 2 implementation

Odoo-native cashier workspace. **17 Aug 2026.**

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **WRITE** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION**

Related: `ACCOUNTANT_PAYMENTS_INVESTIGATION.md` (25 Aug 2026 — what to expose vs keep in Odoo), `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTING_BILLING_WORKFLOW.md`, `PHARMACY_BILLING_DISPENSING_SEPARATION.md`.

Hospital EMR is the hospital workflow. Odoo remains the financial source of truth. OpenMRS remains the clinical source of truth. There is no Hospital EMR ledger.

---

## 1. Accountant route

**IMPLEMENTED**

| Hash | Workspace |
|---|---|
| `#/accountant` | Cashier desk |
| `#/accountant/patient/{patientUuid}` | Collect payment for one patient |

Header search on this workspace opens `#/accountant/patient/{uuid}`. The existing Patient Account remains at `#/patient-account/{uuid}`.

Clinical Home shows **Accountant / Cashier** for SuperAdmin / System Developer, or a user who later receives privilege `abikan:accountant`.

---

## 2. Backend endpoints

**IMPLEMENTED**

Same `abikan-api` service. Browser calls stay under `/openmrs/abikan-api/` so the OpenMRS session cookie is sent.

| Method | Path | Purpose |
|---|---|---|
| GET | `/accountant/dashboard` | Journals, today's posted payments, outstanding invoices, recent payments |
| GET | `/accountant/journals` | Authorized cash/bank journals |
| GET | `/accountant/payments` | Recent posted customer payments |
| GET | `/accountant/payment/{id}` | One posted payment |
| GET | `/accountant/payment/{id}/receipt` | Odoo PDF (Bahmni Receipt, else Payment Receipt) |
| POST | `/accountant/payment` | Register payment through Odoo |

Patient Account GET routes are unchanged and remain read-only. Other POST/PUT/PATCH/DELETE paths still return 405.

---

## 3. Odoo payment mechanism

**CONFIRMED** · **WRITE** via ORM only

```
account.payment.register
  context: active_model=account.move, active_ids=[invoice ids]
  create({ journal_id, amount, payment_date, group_payment=True, communication=requestId })
  action_create_payments()
```

Odoo creates `account.payment`, the journal entry, and reconciliation. Hospital EMR does not insert `account.payment`, `account.move`, or reconciliation rows, and does not write `payment_state` or `amount_residual`.

---

## 4. Invoice eligibility

**IMPLEMENTED** · server recalculates from Odoo

An invoice may be paid only when all of these are true:

- `move_type = out_invoice`
- `state = posted`
- `partner_id` matches the OpenMRS patient → MRN/`uuid` partner
- `payment_state` is `not_paid` or `partial`
- `amount_residual` > 0

Already-paid invoices are rejected. Draft sale orders (for example `S00001`) are not payable.

---

## 5. Multiple invoice payment

**IMPLEMENTED** in the API · **NOT TESTED** live

The wizard is created with every selected `account.move` id and `group_payment=True`. Odoo allocates one inbound payment across those invoices.

There is only one posted customer invoice on this database (`INV/2026/00001`), so a live multi-invoice payment was not executed.

---

## 6. Partial payment

**IMPLEMENTED** in the API · **NOT TESTED** live

The cashier may enter an amount greater than 0 and less than or equal to the selected Odoo residual sum. Overpayment is rejected. Partial payment must not be treated as Pharmacy **READY TO DISPENSE**; that status still requires `payment_state` in `{paid, in_payment}`.

No safe unpaid invoice exists for a live partial-payment test. None was created.

---

## 7. Payment journal handling

**CONFIRMED** · **IMPLEMENTED**

Journals are read from Odoo `account.journal` where `type` is `cash` or `bank`.

Live: **Cash CSH1** (id 6), **Bank BNK1** (id 7). Names and codes are not hardcoded in the UI. Journals were not renamed, and no journal was created. Currency was not changed.

The journal id from the browser is accepted only if it is in that authorized set.

---

## 8. Receipt handling

**CONFIRMED** · **IMPLEMENTED**

Existing reports (not modified):

| Report | Technical name |
|---|---|
| Bahmni **Receipt** | `bahmni_auto_payment_reconciliation.report_payment_invoice` |
| Payment Receipt | `account.report_payment_receipt` |

The API authenticates to Odoo **server-side** and proxies `/report/pdf/.../{paymentId}`. The browser never receives Odoo credentials. Verified against existing `PCSH1/2026/00001` (PDF returned).

Hospital EMR does not invent receipt numbers.

---

## 9. Security

**IMPLEMENTED**

- Odoo username/password stay in `abikan-api` environment
- No `VITE_*` Odoo secrets
- Payment body is re-validated on the server (patient, invoices, residuals, journal, amount)
- Financial JSON and PDFs use `Cache-Control: no-store`

---

## 10. Authorization

**IMPLEMENTED** · **REQUIRES HOSPITAL DECISION** for a dedicated cashier user

| Who | Workspace | Payment POST |
|---|---|---|
| SuperAdmin / System Developer | Yes | Yes |
| Privilege `abikan:accountant` | Yes | Yes |
| Registration / Doctor / Nursing / Lab / Radiology / Pharmacy only | No | 403 |

OpenMRS roles and privileges were **not** created or changed. `abikan:accountant` is a Hospital EMR capability name. The hospital must add and assign that privilege in OpenMRS when a cashier account is created.

Limitation: until that privilege exists, only SuperAdmin / System Developer can pay. That is documented rather than granting payment rights to clinical users.

---

## 11. Idempotency

**IMPLEMENTED**

1. Client sends a `requestId` (UUID). Submit is disabled while the request is in flight.
2. Server stores the request in process memory.
3. A second POST with the same `requestId` returns the original Odoo payment (re-read), and does not call `action_create_payments` again.
4. A concurrent POST with the same id while pending returns `409 payment_in_progress`.
5. Immediately before write, invoice residuals are re-read. Optional `expectedResiduals` must still match Odoo (`409 invoice_changed`).

Limitation: the map is in-memory. An API container restart forgets request ids. Odoo remains the financial authority; a new request id against an already-paid invoice is rejected as `invoice_already_paid`.

---

## 12. Audit trail

**CONFIRMED** in Odoo · no second audit system

Odoo already stores payment user (`create_uid`), date, journal, payment name, and `reconciled_invoice_ids`. Hospital EMR stores only the technical `requestId` (also sent as wizard `communication`) for idempotency.

---

## 13. Patient Account refresh

**IMPLEMENTED**

After a successful Odoo payment the API re-reads the Patient Account from Odoo and returns it. The cashier screen replaces local state with that payload. Balances are not computed in React.

---

## 14. Pharmacy integration

**UNCHANGED**

```
Invoice paid / in_payment
  + picking not done  → READY TO DISPENSE
  + picking done      → DISPENSED
Partial payment       → still UNPAID for dispensing
```

Payment does not validate pickings, change stock, or write OpenMRS Dispensed.

---

## 15. Error handling

| Code | Meaning |
|---|---|
| 401 | Not signed in |
| 403 | Not an Accountant |
| 409 `invoice_already_paid` / `invoice_changed` / `invoice_wrong_patient` / `payment_in_progress` | Safe reject, no write |
| 422 | Invalid amount, journal, invoices, or request id |
| 502 `odoo_payment_failed` | Odoo rejected the wizard; no success UI |
| 503 `receipt_unavailable` | Report PDF could not be fetched |

Success is shown only after Odoo returns a posted `account.payment`.

---

## 16. Test results

| Case | Result |
|---|---|
| A. View unpaid posted invoice | **No such invoice exists.** Attention list is empty. Honest empty state. |
| B. View paid invoice | Adaeze `INV/2026/00001` · PAID · residual 0. Cashier checkboxes disabled. |
| C. Partial payment | **NOT TESTED.** No safe unpaid invoice. None created. |
| D. Multiple invoices | **NOT TESTED.** Only one posted invoice exists. |
| E. Payment success | **NOT EXECUTED.** Creating a payment would require a new isolated invoice. |
| F. Patient Account refresh | Implemented; not exercised by a new payment. |
| G. Pharmacy READY TO DISPENSE | Not exercised. Adaeze remains DISPENSED (`WH/OUT/00001` done). |
| H. Duplicate submission | Idempotency implemented; not exercised by a live write. |
| I. Unauthorized | Unauthenticated GET dashboard and POST payment return 401. |
| Already-paid write guard | POST against `INV/2026/00001` returns `409 invoice_already_paid`. Payment count stayed 1. |
| Receipt | Existing `PCSH1/2026/00001` Bahmni Receipt PDF **CONFIRMED** (24,673 bytes). |
| Journals | Cash CSH1, Bank BNK1 read from Odoo. |

**Blocker for a live payment test:** the only posted customer invoice is protected `INV/2026/00001` (already paid). `S00001` is a draft sale order, not an invoice. A new isolated posted invoice is required before a cashier payment can be proven end-to-end. This phase did not create one.

---

## 17. Known limitations

| Item | Status |
|---|---|
| Live unpaid / partial / multi-invoice payment | **NOT TESTED** — no safe records |
| Dedicated cashier OpenMRS user | **REQUIRES HOSPITAL DECISION** |
| Privilege `abikan:accountant` | Not created in OpenMRS |
| In-memory idempotency | Lost on API restart |
| Nigerian payment gateway | **COMING SOON** |
| Registration / lab / radiology charge creation | **COMING SOON** |
| Refunds | Not in this phase |
| Overpayment | Rejected |

Protected records were not modified: ORD-1–3, S00001, S00002, INV/2026/00001, PCSH1/2026/00001, P00001, pickings, tax, currency, stock.

---

## 18. Future Nigerian payment gateway

**COMING SOON** · **REQUIRES HOSPITAL DECISION**

```
Hospital EMR cashier
  → Nigerian provider (Paystack / Flutterwave / Moniepoint / Interswitch)
  → secure backend
  → same account.payment.register path
  → Patient Account re-read
```

The Patient Account and cashier selection UI should not need to be rebuilt. Only the collection step changes.
