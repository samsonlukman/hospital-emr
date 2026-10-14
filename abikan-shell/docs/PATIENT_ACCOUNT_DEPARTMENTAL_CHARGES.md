# Unified Patient Account + departmental charges

Investigation and architecture only. **17 Aug 2026.**

**No writes.** No UI, products, invoices, payments, tax, currency, users, or permission changes.

Related: `docs/ACCOUNTING_BILLING_WORKFLOW.md`, `docs/PHARMACY_BILLING_DISPENSING_TEST.md`.

Protected live objects unchanged (S00001, S00002, ORD-1–3, INV/2026/00001, PCSH1/2026/00001, P00001, pickings, 90 Units of product 2385, USD, Tax 15%).

Status labels: **CONFIRMED** · **UNKNOWN** · **POSSIBLE** · **REQUIRES CONFIGURATION** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTANT DECISION** · **REQUIRES TAX/LEGAL DECISION**

---

## 1. Unified Patient Account model

**CONFIRMED:** Hospital EMR can show one Patient Account **without** a second ledger.

The account is a **read model** assembled by a secure backend:

```
OpenMRS patient (uuid, MRN, name)
        │
        ▼
Odoo res.partner  (uuid, ref=MRN)
        │
        ├── sale.order / sale.order.line     (charges not yet invoiced)
        ├── account.move out_invoice         (bills)
        ├── account.move.line                (charge lines)
        ├── account.payment                  (receipts)
        └── stock.picking                    (pharmacy dispense only)
```

Example **display** (currency from Odoo, not hardcoded ₦):

```
Adaeze Okafor   MRN ABC200003
Partner 8

Pharmacy
  Paracetamol 500 mg — TEST × 10     [Odoo currency] 10,000 + tax 1,500
  Invoice INV/2026/00001             PAID
  Picking WH/OUT/00001               DISPENSED

Clinical / Lab / Radiology           (none yet)

Totals from Odoo invoices for this partner:
  amount_untaxed + amount_tax        (charges)
  amount_residual                    (outstanding)
  charges − residual                 (paid)   — or sum of reconciled payments
```

Live today: Adaeze has **one** posted invoice, **paid**, residual 0. That is the entire Patient Account until other departments create charges.

Hospital EMR must **not** store running balances. Refresh from Odoo on each open.

---

## 2. Departmental charges

**CONFIRMED** conceptual split:

| Event | Who | Odoo record | Not allowed |
|---|---|---|---|
| Create charge (“owes X”) | Department / feed / Hospital EMR backend | draft `sale.order` line (then invoice on confirm) | Marking paid |
| Collect money | Accountant / Cashier | `account.payment` | Departments |
| Complete service | Department | OpenMRS / picking / LIS / PACS | Treating PAID as done |

Creating a charge ≠ payment ≠ service completion.

Departments must not write `account.payment` or set `payment_state`.

---

## 3. Registration workflow

**NOT SUPPORTED** as an installed charge path. **POSSIBLE** via the same Odoo SO → invoice model.

Desired:

```
Register patient (OpenMRS)     already works
  → create Registration / Consultation charge (Odoo SO)
  → UNPAID
  → Accountant pays
  → PAID
  → Registration reads payment_state
```

No registration-fee or consultation-fee product with a real hospital price exists (search found no “Registration” / “OPD card” product). Service catalogue prices are mostly **1.00** placeholders.

| Step | Status |
|---|---|
| OpenMRS patient → Odoo partner | **CONFIRMED** (customer feed) |
| Auto charge on register | **NOT SUPPORTED** |
| Hospital EMR backend creates SO for a future service product | **POSSIBLE** |
| Registration staff collect cash | **REQUIRES HOSPITAL DECISION** — if yes, still Odoo payment, same journals |

Registration is **not** a financial authority unless the hospital later grants cashier rights. Those rights still go through Odoo.

---

## 4. Clinical workflow

**NOT SUPPORTED** today. **POSSIBLE** later.

| Need | Status |
|---|---|
| Consultation service product | Missing (no priced consult item) |
| `order.type` for consultation | Missing (only Drug Order) |
| Encounter-linked charge | **POSSIBLE:** Hospital EMR backend creates SO line with `external_id` = encounter uuid |
| Doctor marks paid | **Forbidden** |

Pay-before-consult: **REQUIRES HOSPITAL POLICY**.

---

## 5. Laboratory workflow

**CONFIRMED** catalogue; **billing path off**.

- Products: `All / Services / Lab / Test` and `…/Panel`, `type=service`, almost all have `product.product.uuid` = OpenMRS **concept** uuid (e.g. Blood sugar `9AAA…`).
- `list_price` typically **1.00** — not hospital tariffs.
- Tax 15% inherited like drugs.
- Feed ignores Lab Orders: no `order.type` named for them.
- No lab invoices. OpenELIS is result workflow, not the cashier.

**POSSIBLE** later: add `order.type` + shop map matching OpenMRS lab order type name, set real prices, then same SO → invoice → pay → Lab sees PAID → perform test.

Pay-before-test: **REQUIRES HOSPITAL POLICY**.

---

## 6. Radiology workflow

Same as lab.

- Category `All / Services / Radiology`, uuid = OpenMRS concept, price 1.00.
- No Radiology `order.type`. PACS does not bill.
- **POSSIBLE** after config. Pay-before-imaging: **REQUIRES HOSPITAL POLICY**.

---

## 7. Pharmacy workflow

**CONFIRMED.** Do not change.

```
OpenMRS Drug Order uuid
  → sale.order.line.external_order_id
  → sale.order → invoice → payment_state
  → picking / qty_delivered
```

On the Patient Account, Pharmacy lines are invoice lines (or draft SO lines) whose product category is `All / Saleable / Drugs/…` or whose `external_order_id` is a drug order.

Adaeze live row: ORD-3 → S00002 → INV/2026/00001 **PAID** → WH/OUT/00001 **DISPENSED**.

READY TO DISPENSE = PAID and picking not done. **CONFIRMED.**

---

## 8. Accountant / Cashier workflow

**CONFIRMED** as Odoo today; Hospital EMR later is a view + backend calls.

1. Search patient → OpenMRS or `res.partner.ref`
2. Patient Account → all invoices + draft SOs for `partner_id`
3. Review lines (product, qty, untaxed, tax, residual)
4. Confirm draft SOs if still quotations (`is_invoice_automated` posts invoice)
5. Register payment (`account.payment.register`)
6. Journal: Cash 6 / Bank 7 (USD now)
7. Print Bahmni Receipt / Payment Receipt
8. History: `account.payment` for partner
9. Outstanding: sum `amount_residual`
10. Refund: credit note / reverse — Billing Administrator

No Hospital EMR ledger.

---

## 9. Payment workflow

Charge stays UNPAID until an `account.payment` is reconciled to that invoice.

| Payment unit | Odoo | Departmental PAID? |
|---|---|---|
| One invoice | `payment_state` on that move | **Yes**, if that invoice is one department |
| Several invoices, one wizard | One `account.payment`, reconcile to several receivable lines | Each invoice gets its own `payment_state` |
| One invoice, many lines | Payment is **invoice-level**, not line-level | **Cannot** mark one line paid and another unpaid on the same invoice |

**CONFIRMED** from `account.payment.register.default_get`: `active_ids` may be many `account.move`; wizard collects posted receivable lines with residual.

---

## 10. Receipt workflow

Unchanged: print Odoo/Bahmni QWeb on `account.payment`. Number = payment move name (e.g. `PCSH1/2026/00001`). MRN = `partner.ref`. No QR.

Hospital EMR prints via backend. One receipt can correspond to a payment that settled several invoices — show those invoice numbers on the Patient Account, not a second receipt book.

---

## 11. Multiple invoices

**CONFIRMED** possible. One `res.partner` can have many `out_invoice`.

Hospital EMR lists all of them on one screen, grouped by department (see §20).

Live: Adaeze has one customer invoice. Tunde/John have none posted.

---

## 12. Multiple charges

**CONFIRMED** on one SO: multiple Drug Order lines append to the same **draft** SO (same shop).

**POSSIBLE** across departments only after each has `order.type` + shop. Different types → different SOs → different invoices (unless an accountant merges manually).

**Recommended for departmental PAID/UNPAID:** keep **one invoice per department (or per SO/shop)**. Then invoice `payment_state` **is** the department status.

Mixing consult + pharmacy on one invoice makes line-level PAID **NOT SUPPORTED** without inventing allocation.

---

## 13. Partial payment

**CONFIRMED** in Odoo (not re-executed):

| Situation | `payment_state` | `amount_residual` |
|---|---|---|
| Pay less than one invoice | `partial` | remainder |
| Pay some invoices in full, leave others | paid / not_paid per invoice | per invoice |

**Individual lines on a partially paid invoice are not independently paid.** Hospital EMR must **not** tell Pharmacy “PAID” if the pharmacy invoice is `partial` unless hospital policy says “any payment unlocks” — that would be **REQUIRES HOSPITAL DECISION** and is unsafe for stock.

Safest: READY TO DISPENSE only when **that pharmacy invoice** is `paid` (or `in_payment` if Operations accepts it).

---

## 14. Payment allocation

**CONFIRMED:** Odoo reconciliation allocates a payment to the **receivable lines selected in the wizard**, not to product lines.

If the cashier selects invoices A+B+C and enters 8500 covering all residuals, all three become `paid`.

If the cashier selects A+B+C and enters 10000 of 16500, Odoo applies the payment to those lines according to its reconcile batches (typically consumes residuals in the selected set). Exact leftover split if amount does not match a subset: **REQUIRES CONTROLLED TEST** — do not reimplement. Hospital EMR should **display** each invoice’s resulting `payment_state` and `amount_residual` after Odoo returns.

**Do not invent a Hospital EMR allocation engine.**

Cashier UX later: let the accountant **select which invoices** (departments) this payment applies to, then call Odoo with those `active_ids` and the amount. That is Odoo’s model, not a new ledger.

---

## 15. Outstanding balances

For one patient (`partner_id`):

| Display | Authoritative source |
|---|---|
| Outstanding | `SUM(amount_residual)` of posted `out_invoice` |
| Charge total | `SUM(amount_untaxed + amount_tax)` or Bahmni `invoice_total` if discounts used — **verify**; prefer untaxed+tax |
| Paid | charge total − outstanding, **or** sum of inbound `account.payment.amount` reconciled to those invoices |
| Draft not yet billed | draft `sale.order.amount_total` shown as **unbilled charges**, not as invoice residual |
| Currency | invoice / company `currency_id` |

**Never** use `amount_total` alone as “owed” (TEST invoice residual vs stored total).

---

## 16. Tax

Current: Tax 15% id 1, excluded, generic US/demo default. **Do not change.**

On the Patient Account, show per invoice:

- `amount_untaxed`
- `amount_tax`
- due = residual

Do not label it “VAT”. Production treatment: **REQUIRES TAX/LEGAL DECISION**.

Hospital EMR must not compute 15% itself.

---

## 17. Currency

Company **USD**. NGN exists inactive (id 121). **Do not change.**

Display: `res.currency.symbol` + amount with `decimal_places` from the invoice’s `currency_id`. Never hardcode ₦, NGN, or USD in the UI.

The ₦ figures in the hospital example are **policy illustrations**, not live data.

---

## 18. Department permissions

Suggested model — **REQUIRES HOSPITAL DECISION** before implementation:

| Role | Create charge | Collect payment | See status | Complete service |
|---|---|---|---|---|
| Registration | Registration/consult charge | No (unless later authorized) | Yes | Register patient |
| Doctor | Approved clinical charge | No | Yes | Consult if policy allows |
| Laboratory | Lab charge (or feed) | No | Yes | Test when policy says |
| Radiology | Imaging charge (or feed) | No | Yes | Image when policy says |
| Pharmacy | Via prescription feed | No | Yes | Dispense only if PAID |
| Accountant | No (except corrections) | **Yes** | All | Refunds if Billing Admin |

Pay-before-service per department: **REQUIRES HOSPITAL POLICY**. Do not hardcode.

---

## 19. Accountant permissions

Minimum Odoo groups (do not create users):

| Task | Group |
|---|---|
| View invoices, register payment, print, history, balances | Invoicing **Billing** (28) |
| Confirm SO (posts invoice on this stack) | Sales User: All Documents **or** service user in backend |
| Credit notes / refunds | **Billing Administrator** (30) |

Hospital EMR Accountant RBAC maps to backend operations; browser never holds Odoo credentials.

---

## 20. Odoo mapping (charge identity)

| Need | Field | Status |
|---|---|---|
| Patient | `res.partner.id` / `ref` / `uuid` | **CONFIRMED** |
| MRN | `res.partner.ref` | **CONFIRMED** |
| Service | `product.product` / invoice line name | **CONFIRMED** |
| OpenMRS order (pharmacy) | `sale.order.line.external_order_id` | **CONFIRMED** |
| Encounter | `sale.order.line.external_id` | **CONFIRMED** |
| Sale order | `sale.order` | **CONFIRMED** |
| Invoice | `account.move` | **CONFIRMED** |
| Invoice ↔ SO line | `sale_order_line_invoice_rel` | **CONFIRMED** |
| Payment | `account.payment` + reconcile | **CONFIRMED** |
| Date | `invoice_date` / `payment.create_date` | **CONFIRMED** |
| Lab/radio concept | `product.product.uuid` | **CONFIRMED** (concept uuid) |
| Lab/radio **order** uuid on SO line | same `external_order_id` **if** feed creates the line | **POSSIBLE** after `order.type` |

### Department identification

| Mechanism | Status |
|---|---|
| `product.category` (Drugs / Lab / Radiology / Services) | **CONFIRMED** on products; usable to group lines |
| `order.type` | **CONFIRMED** Drug Order only; **REQUIRES CONFIGURATION** for others |
| `sale.shop` | **CONFIRMED** Pharmacy Counter only |
| OpenMRS order type on the feed | **CONFIRMED** (ignored if type missing) |
| OpenMRS encounter type | **POSSIBLE** via `external_id` → OpenMRS |
| Invoice analytic / custom department field | **NOT SUPPORTED** today |
| New Hospital EMR table | **Do not** |

Safest grouping for the Patient Account: **invoice → sale order → shop / order.type if set, else product.category**.

---

## 21. OpenMRS mapping

| OpenMRS | Role |
|---|---|
| Patient uuid / MRN | Identity |
| Encounter | Visit context; `external_id` |
| Drug Order uuid | Pharmacy charge join |
| Lab / Radiology order uuid | Future charge join (same field) |
| Concepts | Service product uuid |
| Obs / diagnoses | Clinical only — not billed unless a charge is created |

OpenMRS does **not** store payment_state.

---

## 22. Secure backend architecture

```
Hospital EMR UI  (no Odoo secrets)
    → Hospital EMR backend (session + RBAC)
        → OpenMRS  patients, orders, encounters
        → Odoo     SO, invoices, payments, pickings, currency, tax
```

Never put Odoo credentials in React, Vite `VITE_*`, localStorage, or sessionStorage.

Writes: create charge SO, confirm, `payment.register`, print report, validate picking (Pharmacy only, after PAID).

---

## 23. Risks

1. Line-level PAID on a shared invoice is **not** in Odoo — keep invoices departmental.
2. Partial invoice must not unlock Pharmacy stock.
3. Lab/radio prices at 1.00 — do not bill them as-is.
4. `amount_total` can lie; use residual.
5. 15% tax and USD will confuse a naira Patient Account until Operations decides.
6. Registration/consult have no product yet — creating charges needs config first.
7. Second ledger temptation — reject it.

---

## 24. Recommended implementation sequence

1. **Hospital policies:** who may collect money; pay-before-service per department; combined vs departmental invoices (recommend **departmental invoices**).
2. **Accountant / tax / legal:** VAT; NGN cutover (not this DB yet); real service prices.
3. **Odoo config (later):** registration + consult + lab + radio products and `order.type`/shop maps; do not use list_price 1.00 in production.
4. **Hospital EMR Patient Account v1 (read-only):** partner invoices + draft SOs + payments + Pharmacy PAID/DISPENSED. Currency from Odoo.
5. **Hospital EMR Cashier v1:** pay selected invoices via backend; print receipt.
6. **Registration charge** once a product exists.
7. **Lab/radio/clinical charges** once mapped.
8. Refunds last.

No UI in this task.

---

## Live Patient Account sketch (Adaeze, authoritative USD)

| Dept | Charge | Invoice | Pay | Service |
|---|---|---|---|---|
| Pharmacy | Paracetamol TEST × 10, untaxed 10000, tax 1500 | INV/2026/00001 | **PAID** residual 0 | **DISPENSED** |
| Clinical | — | — | — | — |
| Laboratory | — | — | — | — |
| Radiology | — | — | — | — |
| Registration | — | — | — | — |

Outstanding **0**. Currency **USD**.

---

*End of architecture investigation. No writes.*
