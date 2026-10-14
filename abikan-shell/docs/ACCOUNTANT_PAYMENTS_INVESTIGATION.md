# Accountant / Payments — Investigation

Date: **25 Aug 2026**.

**Investigation only.** No new payment system, Flutterwave, gateway, second ledger, tax change, or currency cutover. No invoices or payments were created or modified. Protected TEST orders and invoices were left as found.

Related: `ACCOUNTING_BILLING_WORKFLOW.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `ACCOUNTANT_PAYMENT_E2E_TEST.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `LABORATORY_BILLING_IMPLEMENTATION.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`.

Status labels:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Observed in this install (code + live read) |
| **IMPLEMENTED** | Hospital EMR already exposes it over Odoo |
| **STALE** | Earlier doc no longer matches live |
| **MISLEADING** | Shown to staff, but the number or label is wrong |
| **KEEP IN ODOO** | Do not rebuild in Hospital EMR |
| **REQUIRES ACCOUNTANT DECISION** | Hospital finance must choose |
| **REQUIRES HOSPITAL DECISION** | Operations / clinical policy |

Live session: `accountant.abikan` / `Admin123`. Reads only. Invalid payment POST with a fake patient UUID returned **404** before any Odoo write.

---

## Verdict

Hospital EMR already has a **thin cashier workspace over Odoo**. That is the correct product shape.

| Question | Answer |
|---|---|
| Does Hospital EMR need a second payment ledger? | **No.** Odoo `account.move` + `account.payment` remain the financial source of truth. |
| Does Hospital EMR need Flutterwave / a card gateway? | **No.** Do not add one. |
| Should cashiers work in Odoo Invoicing every day? | **No.** Daily collection belongs in Hospital EMR. Chart, tax, credit notes, and currency stay in Odoo. |
| Should Hospital EMR be rebuilt as a “substantial” billing product? | **No.** Keep the existing collect-payment screen. Fix honesty issues later (mixed-currency totals, duplicate nav). |
| What is missing for a Nigerian cashier? | Honest NGN vs USD display; POS/card as a hospital decision in Odoo; refunds remain in Odoo. |

**Do not begin a new Accountant architecture in the next implementation pass.** The next pass, if any, should be a **safe honesty cleanup** of the existing thin interface — not a payment-system rewrite.

---

## 1. Architecture (source of truth)

**CONFIRMED**

```
Department creates a charge (sale.order → posted account.move)
        ↓
Accountant records physical payment in Hospital EMR
        ↓
abikan-api POST /accountant/payment
        ↓
Odoo account.payment.register → account.payment + journal entry + reconcile
        ↓
invoice payment_state + amount_residual
        ↓
Patient Account / Pharmacy / Radiology / Laboratory read those fields
```

| System | Owns |
|---|---|
| OpenMRS | Patient, visit, clinical orders |
| Odoo | Partner, sale order, invoice, payment, residual, receipt PDF, tax, currency |
| Hospital EMR | Staff workflow: who may collect, which posted bills, how much, which cash/bank journal |

Hospital EMR does **not** insert `account.payment` rows, write `payment_state`, or store running balances.

---

## 2. Odoo invoice / charge lifecycle

**CONFIRMED**

1. Department (or Atomfeed) creates a **sale order** for the OpenMRS patient partner (`res.partner.uuid` / `ref` = hospital number).
2. Confirm creates and **posts** a customer invoice (`bahmni_sale.is_invoice_automated=True` on the pharmacy path; consultation / laboratory / radiology charges use the same Odoo invoice model via Hospital EMR-api).
3. Draft sale orders are **not** payable in Hospital EMR.
4. Cashier pays only when:
   - `move_type = out_invoice`
   - `state = posted`
   - `payment_state` in `{not_paid, partial}`
   - `amount_residual > 0`
   - partner matches the patient
5. Odoo Register Payment reconciles. Residual 0 → `paid`.

**Amount due is `amount_residual`.** Do not treat `amount_total` as owed (earlier TEST invoice residual/total mismatch still stands as a risk).

---

## 3. Accountant workspace today

**IMPLEMENTED** · live `accountant.abikan`

| Hash | What staff see |
|---|---|
| `#/accountant` | Cashier desk: today’s KPIs, outstanding bills, recent receipts |
| `#/accountant/outstanding` | Same desk, scrolls to Outstanding |
| `#/accountant/payments` | Same desk, scrolls to Recent receipts |
| `#/accountant/receipts` | Same desk, same receipts table |
| `#/accountant/patient/{uuid}` | **Collect payment** for one patient |
| Header **Patient Accounts** | Search → collect-payment hash |

Nav labels: Dashboard, Outstanding, Payments, Receipts, Patient Accounts.

**Redundant:** Outstanding / Payments / Receipts are not separate workspaces. They are aliases of the dashboard. **MISLEADING** if staff expect three different jobs.

Collect-payment screen:

- Unpaid / partially paid bills with checkboxes
- Paid and closed bills (including **REVERSED**)
- Amount + **Bank** or **Cash**
- Review → Confirm (copy: payment cannot be undone **here**)
- Link to read-only Patient Account
- **No** price edit, **no** refund, **no** POS, **no** Odoo deep-link

Session **LOCATION: Registration Desk** is shown on the patient header. That is the accountant login location, not a visit. **MISLEADING.**

---

## 4. Unpaid / partially paid / paid

**CONFIRMED** mapping from Odoo `payment_state`:

| Odoo | Hospital EMR label |
|---|---|
| `not_paid` | UNPAID |
| `partial` | PARTIALLY PAID |
| `in_payment` | PAYMENT PROCESSING / IN PAYMENT |
| `paid` | PAID |
| `reversed` | shown as closed (live INV/2026/00031 **REVERSED**) |

Live outstanding (21 bills), including:

- INV/2026/00036 Radiology **PARTIALLY PAID** · due **10.00 ₦**
- INV/2026/00035 Radiology **UNPAID** · **13,333.00 ₦**
- INV/2026/00030 Consultation **UNPAID** · **300.00 ₦**
- INV/2026/00022 Laboratory **UNPAID** · **1,500.00 ₦**
- INV/2026/00018 Accommodation **UNPAID** · **$20.00**

Partial payment is **IMPLEMENTED** in API and UI, and **CONFIRMED** live (00036). Multi-invoice payment is **IMPLEMENTED** in API; not re-executed in this investigation.

Pharmacy dispensing still treats `partial` as **UNPAID** for READY TO DISPENSE. **CONFIRMED** in code. Do not change that here.

---

## 5. How physical payments are recorded

**CONFIRMED**

The cashier takes cash or sees a bank transfer, then records it in Hospital EMR. That is **not** a card capture.

```
account.payment.register
  journal_id = Cash CSH1 or Bank BNK1
  amount ≤ selected residuals
  group_payment = True
  communication = requestId
  action_create_payments()
```

Payment does **not** validate pharmacy pickings, write OpenMRS Dispensed, or change Radiology/Lab fulfilment.

---

## 6. Cash vs POS vs bank transfer

**CONFIRMED**

| Channel | Odoo journal | In Hospital EMR cashier? | Live receipts |
|---|---|---|---|
| Cash | Cash **CSH1** id 6 (`type=cash`) | **Yes** | PCSH1/… |
| Bank transfer | Bank **BNK1** id 7 (`type=bank`) | **Yes** | PBNK1/… (e.g. 2026-08-21 **2,000.00 ₦**) |
| POS / card terminal | Point of Sale **POSS** id 9 (`type=general`) | **No** | None in Hospital EMR methods |
| Flutterwave / other gateway | `payment` addon historically disabled | **No** | None |

Hospital EMR only lists journals with `type` in `{cash, bank}`. POS is **KEEP IN ODOO** until the hospital configures a real tender and asks Hospital EMR to expose it.

Do **not** invent a third “POS” method in Hospital EMR that is not an Odoo journal.

---

## 7. Receipts

**IMPLEMENTED** · **CONFIRMED** live

| Item | Value |
|---|---|
| Numbers | Odoo payment name (`PCSH1/…`, `PBNK1/…`) |
| PDF | Existing Odoo payment receipt with Hospital EMR header/footer; standard Odoo Payment Receipt remains the technical fallback |
| GET | `/openmrs/abikan-api/accountant/payment/{id}/receipt` |
| Live | payment id 13 → **200** `application/pdf`, `Cache-Control: no-store` |

Hospital EMR does not invent receipt numbers. Accountant Patient Account shows a Receipt column; Doctor Patient Account does not collect and does not need Pay.

Stale API field `receiptsNote`: “Receipt viewing will be available in a later phase.” **Not shown** in the current UI. **STALE** payload only.

---

## 8. Refunds and reversals

**KEEP IN ODOO**

| Action | Where |
|---|---|
| Credit note / reverse invoice | Odoo `account.move.reversal` / `out_refund` |
| Reverse a payment | Odoo (Billing Administrator) |
| Pharmacy stock return | Odoo picking return after a done delivery |

Hospital EMR Collect payment has **no** Refund control. Confirm copy: cannot be undone **here**.

Live: INV/2026/00031 Obstetrics **REVERSED** ($15,000.00) appears under Paid and closed bills. That reversal happened in Odoo, not Hospital EMR.

Do **not** auto-refund from Radiology cancellation, Doctor, or Pharmacy. Coordinated refund rules do not exist.

---

## 9. Patient billing history and outstanding balances

**IMPLEMENTED** as Patient Account (read-only) plus cashier collect screen.

Patient Account (`#/patient-account/{uuid}`):

- Bills, payments, departmental filters
- Outstanding / paid / billed summaries
- Pharmacy payment vs dispense status
- Visit header only when opened with a visit hash; bills stay **patient-level**

**MISLEADING totals:** `build_account` and the accountant dashboard **sum invoice amounts across currencies**, then format in one currency (company **USD** on the dashboard, first posted invoice currency on the account).

Live dashboard KPI:

- 21 unpaid bills, mix of **₦** and **$**
- “Still unpaid” shown as **$45,574.00**

That number is **not** a real dollar (or naira) debt. It added 13,333 + 12,222 + … + 20 + 10 as if they shared a currency.

On ABC200016 collect screen, unpaid rows happened to be all NGN, so “Amount due **30,365.00 ₦**” is less mixed — but “Already paid **33,190.00 ₦**” still sits next to closed **$2,300.00** and **$15,000.00** lines.

**Do not** use these KPI cards as a financial report until they are currency-safe. Per-invoice residual from Odoo is trustworthy.

---

## 10. Duplicate payment / charge protection

**CONFIRMED**

| Guard | Behaviour |
|---|---|
| `requestId` idempotency | Same id returns original payment; concurrent → `409 payment_in_progress` |
| Already paid | `409 invoice_already_paid` (live-proven on INV/2026/00002 in the 17 Aug e2e) |
| Residual changed | `409 invoice_changed` if `expectedResiduals` mismatch |
| Wrong patient | `409 invoice_wrong_patient` |
| Overpay | `422 amount_exceeds_outstanding` |
| Draft SO | Not in the payable list |

Limitation: idempotency map is **in-memory**. API restart forgets ids. Odoo still rejects a second pay on a paid invoice.

Departmental charge `requestId`s (consultation / lab / radiology) are separate from payment ids. Do not conflate them.

---

## 11. NGN and currency

**CONFIRMED** · **REQUIRES ACCOUNTANT DECISION** for production cutover

| Item | Live |
|---|---|
| Company currency | **USD** |
| NGN `res.currency` | Exists; departmental charges **activate** it for consultation / radiology / some lab & registration invoices |
| Cashier dashboard `currency` | Company **USD** |
| Invoice lines | Mixed **₦** and **$** on the same patient |

Earlier investigation said “do not hardcode ₦.” Departments now post NGN invoices while the company is still USD. That is **live**, not hypothetical.

**Do not flip company currency on this database** after posted invoices. **KEEP IN ODOO** as a planned cutover.

Hospital EMR must display each invoice’s Odoo currency. It must **not** sum mixed currencies into one KPI.

Paying several invoices in **one** Register Payment when they have different currencies is unsafe. The wizard uses the first invoice’s currency. A later honesty pass should prevent mixed-currency selection — not invent FX.

---

## 12. Departmental charges vs collection

**CONFIRMED** (this supersedes the 17 Aug “consultation/lab/radiology not configured” sections of `ACCOUNTING_BILLING_WORKFLOW.md` for **charge creation**. Collection was always Accountant.)

| Department | Creates the charge | Sets the amount | Collects money |
|---|---|---|---|
| Doctor | Consultation fee (send bill to cashier) | Doctor enters NGN fee | **No** |
| Laboratory | Order → Odoo invoice | Catalogue / existing lab billing | **No** |
| Radiology | Order exists; Radiologist **Set Price** | Radiologist NGN | **No** |
| Pharmacy | Atomfeed drug order → invoice | Product list price | **No** |
| Reception | Registration charges (live unpaid NGN invoices on ABC200018) | Existing registration billing | **No** |
| Nursing / Accommodation | Daily stay invoices (live **USD** on Ibrahim / Emeka) | Accommodation billing | **No** |
| Accountant | **No new charge** | Cannot change prices | **Yes** |

Live unpaid on ABC200016 collect screen: Radiology, Consultation, Laboratory — all payable in Hospital EMR without opening Odoo.

---

## 13. Accountant permissions

**CONFIRMED**

| Who | Workspace | Payment POST |
|---|---|---|
| `abikan:accountant` (`accountant.abikan`, role `Abikan:Accountant`) | Yes | Yes |
| SuperAdmin / System Developer | Yes | Yes |
| Doctor / Radiology / Laboratory / Pharmacy / Reception / Nursing only | Access denied | 403 |

Odoo username/password stay in `abikan-api`. No `VITE_*` Odoo secrets.

Odoo **Billing Administrator** (credit notes) is **not** mapped to Hospital EMR. Refunds stay in Odoo until the hospital asks for a Hospital EMR refund workflow.

Live: `#/doctor` as accountant → **You do not have access to this department.**

---

## 14. What other departments can see

**CONFIRMED** (Doctor audit 25 Aug + this session)

| Role | Bills / payment status | Collect / Pay | Set Radiology price |
|---|---|---|---|
| Doctor | Patient Account read-only; consultation fee create; radiology price **read-only** | **No** | **No** |
| Radiologist | Price / Unpaid / Paid on the order | **No** | **Yes** |
| Laboratory | Payment status; does not collect | **No** | n/a |
| Pharmacy | UNPAID / PAID / READY / DISPENSED | **No** | n/a |
| Reception | Patient Account read-only | **No** | n/a |
| Accountant | Outstanding + collect | **Yes** | **No** |

Patient Account is shared read-only history. Accountant Collect payment is the only Hospital EMR **write** to `account.payment`.

---

## 15. Payment-entry UI vs deep-link Odoo

**Recommendation: keep the existing Hospital EMR payment-entry UI. Do not replace it with an Odoo deep-link.**

| Option | Fit |
|---|---|
| Cashiers live in Odoo Invoicing | Wrong. US chart, tax 15%, draft SOs, technical journals, mixed currency. Staff would see architecture, not “collect payment”. |
| Hospital EMR thin cashier (current) | Right. Register Payment through Odoo. Receipt PDF. Patient identity from OpenMRS. |
| New Hospital EMR ledger / Flutterwave | Forbidden. Second ledger and a gateway the hospital did not ask for. |

Hospital EMR **does** need a payment-entry UI. It already has one. It should stay a **wrapper**, not grow into accounting software.

---

## 16. Redundant or misleading Accountant UI

| Item | Finding | Later action (not this investigation) |
|---|---|---|
| Dashboard / Outstanding / Payments / Receipts | Four nav items, one screen | Merge or rename; keep one desk |
| “Still unpaid **$45,574.00**” | Mixed ₦ + $ summed as USD | Hide KPI or split by currency |
| Patient Account / collect “Already paid” | Same mixed-sum risk | Per-invoice only, or currency-safe totals |
| LOCATION Registration Desk | Session room, not a bill | Hide on cashier identity |
| `receiptsNote` API string | Stale “later phase” | Stop returning it |
| KPI cards on dashboard | Easy to treat as a daily cash-up | Only safe after currency honesty |
| Paid and closed includes REVERSED | Correct Odoo state; easy to misread as paid | Keep, maybe label Reversed more clearly later |

Do **not** remove Collect payment, receipts, or outstanding invoice rows. Those are the job.

---

## 17. What Hospital EMR should expose vs keep in Odoo

### Expose in Hospital EMR (already mostly done)

- Search patient by name / hospital number
- List posted unpaid / partial invoices
- Record cash or bank payment ≤ residual
- Print Odoo receipt
- Show payment status to clinical departments (read-only)
- Block departments from collecting

### Keep in Odoo (do not rebuild)

- Chart of accounts, journals, taxes, fiscal country
- Company currency cutover to NGN
- Credit notes, payment reversals, vendor bills
- Bank reconciliation, aged receivables, statutory reports
- POS configuration / card acquirers / Flutterwave
- Product list prices and 15% tax policy
- Draft quotations that are not yet posted invoices

---

## 18. What was **not** done

- No Flutterwave, Paystack, or other gateway
- No second ledger
- No new payment POST that succeeded
- No edits to ORD-6, ORD-14–21, or listed protected invoices
- No tax, journal, or currency configuration
- No Accountant UI rewrite

---

## Accountant — Honesty Pass

Date: **25 Aug 2026**.

Cleanup only. **Odoo remains the financial source of truth.** Hospital EMR remains a thin cashier over `account.payment.register`. No Accountant v2, Flutterwave, second ledger, refund UI, POS, or company-currency cutover.

### Mixed-currency totals

Dashboard and Patient Account no longer sum ₦ and $ into one number. Totals are grouped by Odoo currency and shown separately (`outstandingByCurrency`, `paidByCurrency`, `billedByCurrency`, `paymentsReceivedByCurrency`). No invented exchange rate.

### Same-currency payment restriction

Selecting invoices in different currencies is blocked in the UI and rejected by the API (`422 mixed_currency`: “Select invoices in the same currency.”). Currency is visible on each invoice row. One payment remains one currency. Existing residual, already-paid, and `requestId` checks remain. Odoo is still authoritative.

### Navigation

Primary nav is **Cashier** (`#/accountant`) and **Patient Accounts** (search). Outstanding / Payments / Receipts hashes remain compatibility aliases of the same desk. They are not separate workspaces.

### Location

Registration Desk is hidden on the Accountant collect-payment identity. It was the session location, not a cashier till. OpenMRS locations were not renamed.

### receiptsNote

Removed from the Hospital EMR response contract and types. Unused by the UI. Receipts already work.

### REVERSED vs PAID

`reversed` maps to **REVERSED**, not PAID. Reversed bills have their own section, are not collectible, and do not count as paid in summaries. No Refund button.

### Residual-based outstanding

Payable bills still use Odoo `amount_residual` on posted `not_paid` / `partial` invoices. Draft sale orders are not payable. Patient Account remains read-only for non-Accountant roles.

### Payment methods

Cash (CSH1) and Bank (BNK1) only. No Flutterwave, card, online, or POS.

### Receipts

Receipt number remains the Odoo payment name. The PDF is the existing Odoo payment receipt with an **Hospital EMR** header/footer. The download is labelled **Hospital EMR-receipt-…**. Existing and future receipts are rendered with the Hospital EMR layout; no company name, United States address, or source-system branding is shown. Hospital EMR does not invent receipt numbers.

### Security

`abikan:accountant` (or SuperAdmin) can collect. Doctor, Radiology, Laboratory, Pharmacy, Reception, and Nursing cannot. Odoo credentials stay server-side.

### Intentional non-changes

Refunds, POS, NGN company cutover, Radiology pricing, consultation-fee creation, Pharmacy dispense gating, and the Register Payment architecture were not changed. Protected TEST orders and invoices were not paid or edited.

---

*Odoo remains the financial source of truth. Hospital EMR remains the hospital cashier workflow over that ledger.*
