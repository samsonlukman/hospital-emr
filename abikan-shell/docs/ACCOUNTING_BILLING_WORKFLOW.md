# Accounting / cashier — Nigerian hospital billing investigation

Investigation only. **17 Aug 2026.**

**Superseded in part by** `ACCOUNTANT_PAYMENTS_INVESTIGATION.md` (**25 Aug 2026**). That later investigation is the source of truth for the Accountant workspace, payment collection, mixed-currency KPIs, and departmental charges that now post invoices. Sections below that say consultation / laboratory / radiology charges are “not configured” are **stale**.

**No writes.** Tax, currency, invoices, payments, journals, products, stock, sale orders, OpenMRS, Pharmacy flags, and Hospital EMR UI were not changed.

Protected objects left as the Pharmacy test left them: S00001 draft; S00002 sale / paid / delivered; ORD-1–3; INV/2026/00001 paid; PCSH1/2026/00001; P00001; WH/IN/00001; WH/OUT/00001 done; product 2385 WH/Stock **90**; currency **USD**.

Related: `docs/PHARMACY_BILLING_DISPENSING_TEST.md`, `docs/PHARMACY_BILLING_DISPENSING_SEPARATION.md`, `docs/PHARMACY_BILLING_PAYMENT_DISPENSING_WORKFLOW.md`.

Status labels:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Installed source and/or live database |
| **UNKNOWN** | Cannot be proven from this install |
| **REQUIRES CONFIGURATION** | Odoo/Bahmni settings later; not applied |
| **REQUIRES ACCOUNTANT DECISION** | Hospital finance must choose |
| **REQUIRES HOSPITAL DECISION** | Clinical/ops policy |
| **REQUIRES TAX/LEGAL DECISION** | Not inferable from software |

---

## 1. Accounting architecture

**CONFIRMED**

| Item | Value |
|---|---|
| Odoo | **16.0** (20240826) |
| Company | id 1 **Bahmni** |
| Chart | `l10n_generic_coa` (generic). Fiscal country **United States** (id 233) |
| Nigerian localization | **Not installed.** No `l10n_ng` module in the addon list |

Installed finance-related addons: `account`, `account_payment`, `bahmni_account`, `bahmni_auto_payment_reconciliation`, `bahmni_sale`, `bahmni_api_feed`, `sale`, `sale_stock`, `stock_account`, `point_of_sale`, `payment` (providers disabled).

### Core models

| Model | Role | Important fields |
|---|---|---|
| `res.company` | Company | `currency_id`, `account_sale_tax_id`, `account_purchase_tax_id`, `account_fiscal_country_id` |
| `res.currency` | Currency | `name`, `symbol`, `rounding`, `decimal_places`, `active` |
| `res.partner` | Customer / supplier | `name`, `ref` (MRN), `uuid` (OpenMRS), `phone`, `vat`, `customer_rank` |
| `account.account` | Chart accounts | e.g. 121000 Receivable, 400000 Product Sales, 251000 Tax Received, 101501 Cash |
| `account.journal` | Journals | `type` sale/purchase/cash/bank/general, `code`, `currency_id` (empty = company currency) |
| `account.move` | Invoice / bill / entry / credit note | `move_type`, `state`, `payment_state`, `amount_untaxed`, `amount_tax`, `amount_total`, `amount_residual`, `partner_id`, `invoice_origin`, Bahmni `order_id` |
| `account.move.line` | Invoice/journal lines | `product_id`, `quantity`, `price_unit`, `debit`/`credit`, tax links |
| `account.payment` | Payment | `amount`, `payment_type`, `partner_id`, `move_id`, `is_reconciled` (name lives on the linked move) |
| `account.payment.register` | Register Payment wizard | `journal_id`, `amount` |
| `account.payment.method` | Manual inbound/outbound | |
| `account.payment.method.line` | Method on a journal | |
| `account.tax` | Tax | `type_tax_use`, `amount_type`, `amount`, `price_include` |
| `account.fiscal.position` | Tax mapping by customer | **0 records** |
| `sale.order` / `sale.order.line` | Quotation / charge preview | `external_order_id`, `external_id`, `price_unit`, taxes |
| `stock.picking` | Operational dispense | `state`, `sale_id` |

Bahmni extras on `account.move`: `discount_type`, `discount`, `round_off_amount`, `invoice_total` (computed), `order_id`.

`action_post` rewrites the payment-term line debit/credit to `(amount_total - discount) + round_off_amount`. That contributed to the TEST invoice residual vs stored-total mismatch.

---

## 2. Patient / customer mapping

**CONFIRMED**

```
OpenMRS patient
  identifier (MRN)  →  res.partner.ref
  person uuid       →  res.partner.uuid
  display name      →  res.partner.name
```

Atomfeed customer feed upserts on `ref`. Sale-order feed looks up `res.partner` where `ref == customer_id` (MRN). Missing partner → `UserError("Patient Id not found in Odoo")`.

Live: 10 partners with both `ref` and `uuid` (the ABC20000x patients). No duplicate `ref` or `uuid`. One OpenMRS patient maps to **one** Odoo partner on this database.

Phone, mobile, street, city are **empty** on the test patients. Address mapping addon exists but is unused for these records.

**CONFIRMED** usable later by Abikan: search partner by `ref` (MRN) or `uuid`.

---

## 3. Pharmacy billing

**CONFIRMED** (already proven with ORD-3 → S00002 → INV/2026/00001)

```
OpenMRS Drug Order
  → Atomfeed encounter
  → odoo-connect create.sale.order
  → order.save.service.create_orders
  → draft sale.order (origin API FEED SYNC)
  → human/backend confirm
  → posted account.move (is_invoice_automated=True)
  → picking created, not auto-validated (is_delivery_automated=False)
```

| Question | Answer |
|---|---|
| Line identity | `sale.order.line.external_order_id` = OpenMRS drug order UUID |
| Encounter | `sale.order.line.external_id` = encounter UUID |
| Product | `product.product.uuid` = OpenMRS drug UUID |
| Patient | `sale.order.partner_id` via MRN |
| Quantity | OpenMRS qty + `syncable.units.mapping` (Tablet → Units) |
| Price | `product.list_price` (pricelist 1 has no items). OpenMRS has **no** price |
| Tax | `sale.order.line._compute_tax_id()` from `product.taxes_id` |
| Invoice | `_create_invoices()` + `action_post()` on confirm |

Hospital EMR **can** use `external_order_id` for Pharmacy payment verification. **CONFIRMED.**

---

## 4. Invoice workflow

**CONFIRMED**

1. Draft SO is the charge preview (not a posted bill).
2. Confirm SO → invoice created and **posted** (`bahmni_sale.is_invoice_automated=True`).
3. Accountant does **not** need a second “Create Invoice” click on this path.
4. Register Payment on the posted invoice.
5. Print receipt from the payment.

UI today: Odoo **Sales** (quotations) and **Invoicing → Customers → Invoices / Payments**. Hospital EMR Accounting is Coming soon.

Who confirms: a user with Sales/Invoicing rights (today: Odoo admin). Who collects: same, via Register Payment. Future: Hospital EMR Accountant via secure backend.

---

## 5. Payment workflow

**CONFIRMED** on INV/2026/00001

`account.payment.register` (context `active_model=account.move`) → `account.payment` + journal entry `account.move` (`move_type=entry`) → reconcile → invoice `payment_state=paid`, `amount_residual=0`.

Journals used: Cash CSH1. Bank BNK1 is available, unused in the test. POS is **not** this path.

Payment does **not** validate the picking. **CONFIRMED.**

---

## 6. Receipt workflow

**CONFIRMED** reports (unchanged; not reprinted here):

| Report | Model |
|---|---|
| Invoices / Invoices without Payment | `account.move` |
| Payment Receipt | `account.payment` |
| Bahmni **Receipt** | `account.payment` — name, `partner.ref` (MRN), date, amounts |
| Receipt Summary | `account.payment` |

Numbers: invoice `INV/…`, payment move `PCSH1/…` (Cash sequence). No QR on the Bahmni template.

**ABIKAN later:** expose the Bahmni Receipt (or Payment Receipt) PDF via the backend. Do not invent a second receipt number.

---

## 7. Outstanding balances

**CONFIRMED** `account.move.payment_state`:

| Value | Meaning |
|---|---|
| `not_paid` | Posted, residual > 0, no payment |
| `partial` | Some residual remains |
| `in_payment` | Payment posted, not fully reconciled / in transit |
| `paid` | Residual 0 |
| `reversed` | Reversed |
| `invoicing_legacy` | Migration |

**Safest fields for Hospital EMR**

| Need | Field |
|---|---|
| Amount still owed | `account.move.amount_residual` (and `amount_residual_signed`) |
| Tax exclusive charges | `amount_untaxed` |
| Tax amount | `amount_tax` |
| Paid? | `payment_state` |
| Partner AR | sum of open `amount_residual_signed` for the partner (Bahmni SO already does this SQL) |

**Do not treat `amount_total` as the amount owed.**

Live evidence: at post, INV/2026/00001 had stored `amount_total=10000` and `amount_residual=11500`. After payment, `amount_total` now reads **11500** and residual 0. Bahmni discount/`action_post` can desync stored total from receivable. **CONFIRMED** risk.

There is no separate `overpaid` state. Overpay would typically leave partner credit (negative residual / credit note). **REQUIRES CONTROLLED TEST** later.

---

## 8. Refunds

**CONFIRMED** as standard Odoo; **not executed**

| Action | Model |
|---|---|
| Credit note | `account.move` `out_refund` via `account.move.reversal` |
| Cancel draft invoice | if never posted / allowed |
| Reverse payment | cancel/reverse `account.payment` |
| Stock return | return picking from a **done** delivery (pharmacy refund of drugs) |

OpenMRS discontinue only unlinks **draft** sale lines. After confirm+pay+dispense, a refund is Odoo credit note ± stock return, plus optional OpenMRS stop. **No hospital-specific refund product** is installed.

Pharmacy refund is **not** automatic when a credit note is issued.

---

## 9. Tax configuration

### Why TEST Paracetamol got 15%

**CONFIRMED** chain:

1. Company `account_sale_tax_id` = **Tax 15%** (`account.tax` id **1**).
2. Odoo default: new `product.template` gets that sales tax.
3. Drug feed `drug.data.service.create_or_update_drug` does **not** set `taxes_id`. Create inherits the company default.
4. Product 2385 template has `product_taxes_rel` → tax id 1.
5. Sale line `_compute_tax_id()` copies it. S00002 line: `price_tax=1500`, `price_total=11500`.
6. Invoice line also taxed; tax line credits account **251000 Tax Received** (id 16).

This is **not** a Nigerian VAT module. It is the **generic demo/default 15% sales tax** from `l10n_generic_coa` on a company whose fiscal country is the **United States**.

**2386 of 2388** product templates have Tax 15%. Only POS “Tips” and “Down Payment (POS)” do not. S00001’s Paracetamol 110 also has the tax; amount is 0 because `list_price` is 0.

| Tax | id | Use | Type | Amount | Price include | Account |
|---|---|---|---|---|---|---|
| Tax 15% | 1 | sale | percent | 15 | **No** (excluded) | 251000 Tax Received |
| Purchase Tax 15% | 2 | purchase | percent | 15 | No | 131000 Tax Paid |

Fiscal positions: **none**. Customer-level tax exemption is **not** configured.

No Bahmni setting named “hospital VAT off”.

### Hospital policy vs law

| Layer | Status |
|---|---|
| Technical: default 15% on almost every product | **CONFIRMED** |
| Hospital wants patient charges with no automatic tax | **REQUIRES HOSPITAL DECISION** + **REQUIRES ACCOUNTANT DECISION** |
| Whether Nigerian patient hospital services are VAT-able | **REQUIRES TAX/LEGAL DECISION** — do not invent |

If policy becomes “no automatic tax on patient charges”, **REQUIRES CONFIGURATION** later (not now), for example:

- Clear company `account_sale_tax_id` and/or
- Remove tax from pharmacy/service products and/or
- Fiscal position “Patient — no VAT” on patient partners

**Hospital EMR must not strip tax in the UI or backend math.** Changing tax is an Odoo accountant operation after those decisions.

---

## 10. Currency configuration

**CONFIRMED**

| Item | Value |
|---|---|
| Company currency | **USD** id **2**, symbol `$`, 2 decimals |
| Active currencies | USD, EUR only |
| **NGN** | id **121**, symbol **₦**, 2 decimals, **`active=false`** |
| Journals | `currency_id` empty → company USD |
| Pricelist 1 | Public Pricelist (company currency) |

Sale orders / invoices **can** use another currency in standard Odoo if that currency is active and a pricelist/journal is set. **Not configured** here.

Changing `res.company.currency_id` on this database after posted invoices, payments, and stock valuation is **not safe**. Existing INV/2026/00001 and PCSH1/2026/00001 are USD.

**REQUIRES ACCOUNTANT DECISION** + **REQUIRES CONFIGURATION:** Nigerian production should use NGN. Safer approaches: new company/database with NGN from day one, or a planned cutover designed by an accountant. **Do not flip USD→NGN on this test DB.**

Hospital EMR must display `res.currency` from Odoo. **Do not hardcode ₦.**

---

## 11. Payment journals

**CONFIRMED** (unchanged)

| id | Name | type | code | Currency | Default account | Suspense |
|---|---|---|---|---|---|---|
| 1 | Customer Invoices | sale | INV | company | 400000 Product Sales | — |
| 6 | Cash | cash | CSH1 | company | 101501 Cash | 101401 Bank Suspense |
| 7 | Bank | bank | BNK1 | company | 101404 Bank | 101401 Bank Suspense |
| 9 | Point of Sale | general | POSS | company | — | — |

Payment methods: Manual inbound/outbound on journals 6 and 7. Outstanding payment/receipt accounts on method lines are **empty** (Odoo uses journal defaults).

POS tenders: Cash (j6), Bank (j7), Customer Account. Unused by Atomfeed.

| Intended Nigerian channel | Current fit | Later |
|---|---|---|
| Cash | Journal 6 usable (still USD) | Keep; currency NGN later |
| Bank transfer | Journal 7 is a generic bank | **REQUIRES CONFIGURATION** — named transfer journal / bank account |
| POS / card | POS “Bank” tender, not a terminal network | **REQUIRES HOSPITAL DECISION** + config |
| Other (e.g. mobile money) | None | **REQUIRES HOSPITAL DECISION** |

Do not create journals in this task.

---

## 12. Consultation billing

**NOT configured.**

No `order.type` for consultation. No consultation fee product with a real price (only incidental service concepts at `list_price=1.00`). Doctor write path does not create an Odoo charge.

**Possible later (not built):**

- Service product “OPD Consultation” with `list_price` set by accountant
- `order.type` + shop map **or** Hospital EMR backend creates a sale order line
- Or receptionist posts a charge in Hospital EMR → Odoo SO

**REQUIRES HOSPITAL DECISION** (what is charged, when) and **REQUIRES ACCOUNTANT DECISION** (price, tax). **REQUIRES CONFIGURATION** after that.

---

## 13. Laboratory billing

**CONFIRMED** catalogue exists; **billing path not enabled.**

- Many service products under `All / Services / Lab / Test` and `…/Panel`, typically `list_price=1.00` (saleable concept feed).
- `order.type` has **only Drug Order**. Lab orders in an encounter are **ignored** (`Order Type - X is not defined`).
- OpenELIS sale-order worker exists in odoo-connect; **no** live lab sale orders (only S00001/S00002, both pharmacy).
- Failed lab-feed events from 12 Aug are session errors, not invoices.

**REQUIRES CONFIGURATION:** `order.type` “Lab Order” (exact OpenMRS type name) + shop + real prices. **REQUIRES HOSPITAL DECISION** when to bill (order vs result). Do not invent prices.

---

## 14. Radiology billing

Same pattern as lab.

- Service products under `All / Services / Radiology`, `list_price` typically 1.00.
- No Radiology `order.type` / shop map.
- PACS/dcm4chee is imaging, not billing.
- No radiology invoices.

**REQUIRES CONFIGURATION** after hospital/accountant decisions. Do not modify dcm4chee.

---

## 15. Multiple charges

**CONFIRMED** from `create_orders`:

- Lines are grouped by OpenMRS `type`.
- Same type + same patient + same shop + **draft** SO → **one** SO (append).
- Different `order.type` → different shop if mapped → **separate** SOs → separate invoices after confirm.
- Today only Drug Order → Pharmacy Counter → pharmacy-only bills.

One SO **can** hold mixed products if they are added to the same shop/order. That is not automatic for lab/consult today.

Odoo can register **one payment against multiple invoices**.

| Policy | Status |
|---|---|
| One combined patient bill | **REQUIRES HOSPITAL DECISION** (needs shared shop or a combining step) |
| Separate departmental invoices, one cashier payment | Possible with current Odoo payment register |
| Current live behaviour | **Pharmacy only**, one SO per draft window |

---

## 16. Accountant permissions

**CONFIRMED** existing groups (not modified):

| Group | Category | Typical need |
|---|---|---|
| Invoicing / **Billing** (28) | View/create customer invoices, register payment, print | Minimum cashier |
| Invoicing / **Billing Administrator** (30) | Credit notes, more accounting | Authorized refunds |
| Sales User: All Documents | Confirm quotations | Needed while invoice is created **on SO confirm** |
| Technical: Show Full Accounting Features | Chart, journals | Not for daily cashier |
| Redirect to Payments on Confirm (65) | 0 users | Optional |

A future **Hospital EMR Accountant** role should map, server-side, to Billing (+ Sales confirm if Hospital EMR does not confirm via a service user) and optionally Billing Administrator for refunds.

Do **not** put those Odoo groups in browser JS. The backend uses a service account; Hospital EMR RBAC decides who may call pay/refund.

---

## 17. Hospital EMR architecture

```
Hospital EMR Accounting / Cashier UI
        ↓
Hospital EMR secure backend  (session + RBAC)
        ↓
Odoo  (invoices, payments, receipts, balances, tax, currency)
OpenMRS (patient, MRN, clinical orders)
```

| Hospital EMR should | Hospital EMR must not |
|---|---|
| Display partner, MRN, invoices, residual, payment_state, currency symbol from Odoo | Second ledger |
| Trigger confirm / register payment / print report via backend | Odoo passwords in frontend |
| Join Pharmacy PAID via `external_order_id` | Invent totals or tax |
| Show UNPAID / PAID / READY / DISPENSED | Treat PAID as DISPENSED |
| | Hardcode ₦ or 15% |
| | Write `account.move` rows in SQL |

Odoo = financial source of truth. OpenMRS = clinical/patient source of truth.

---

## 18. Nigerian production configuration

Do **not** implement now.

| Area | Later owner |
|---|---|
| Company legal name, TIN, address | **REQUIRES HOSPITAL ADMIN** + **REQUIRES ODOO CONFIGURATION** |
| Currency NGN (not a casual flip on this DB) | **REQUIRES ACCOUNTANT DECISION** + **REQUIRES CONFIGURATION** |
| Whether patient charges have VAT | **REQUIRES TAX/LEGAL DECISION** then accountant config |
| Cash / transfer / POS journals in NGN | **REQUIRES HOSPITAL DECISION** + **REQUIRES CONFIGURATION** |
| Chart of accounts / tax reports | **REQUIRES ACCOUNTANT DECISION** (generic US COA is wrong for NG production) |
| Service products and real prices | **REQUIRES HOSPITAL** + **REQUIRES ACCOUNTANT** |
| Invoice/receipt sequences | **REQUIRES ACCOUNTANT DECISION** |
| Combined vs split bills | **REQUIRES HOSPITAL DECISION** |

---

## 19. Risks

1. Default **15%** on nearly all products — inappropriate until policy is decided.
2. **`amount_total` is unsafe** as “amount due” (TEST invoice proved it).
3. **USD** on a Nigerian hospital DB; flipping currency after postings is dangerous.
4. Lab/radiology **saleable products at ₦/USD 1.00** — do not bill them as-is.
5. Only **Drug Order** is mapped — other departments silently drop off the feed.
6. Bahmni discounts/`action_post` can rewrite receivable lines.
7. No unpaid-cannot-dispense gate in Odoo itself.
8. OpenMRS Dispensed feed still unsafe.

---

## 20. Recommended implementation order

1. **Decisions (no code):** tax/legal on patient VAT; NGN cutover plan; cash vs transfer vs POS; combined vs departmental bills; consultation/lab/radio price list.
2. **Odoo config (accountant, not Hospital EMR):** apply tax policy; do **not** change currency on this test DB until a cutover plan exists.
3. **Hospital EMR Accounting v1:** list a patient’s draft SOs + posted invoices; show residual + `payment_state` + currency from Odoo; register payment on existing journals; print Bahmni receipt; never compute tax.
4. **Pharmacy join:** UNPAID / PAID / READY TO DISPENSE / DISPENSED from invoice + picking (already designed).
5. **Later departments:** `order.type` + shop + real service prices, then the same cashier UI.
6. **Refunds / NGN production** after accountant sign-off.

---

## Pharmacy payment verification (unchanged)

```
OpenMRS order UUID
  = sale.order.line.external_order_id
  → sale.order
  → account.move (invoice_ids)
  → payment_state, amount_residual
  → stock.picking / qty_delivered
```

| Label | Rule |
|---|---|
| UNPAID | no posted invoice or `payment_state` in `not_paid`/`partial` |
| PAID | `paid` or `in_payment` |
| READY TO DISPENSE | PAID and picking not fully done |
| DISPENSED | picking `done` / `qty_delivered` |

**PAID ≠ DISPENSED.** **CONFIRMED** by the controlled test.

---

*End of investigation. No configuration or data was changed.*
