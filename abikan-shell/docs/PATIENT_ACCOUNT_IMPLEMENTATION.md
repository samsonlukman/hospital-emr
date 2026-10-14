# Patient Account — Phase 1 implementation

Read-only financial workspace. **17 Aug 2026.**

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION**

Related: `PATIENT_ACCOUNT_DEPARTMENTAL_CHARGES.md`, `ACCOUNTING_BILLING_WORKFLOW.md`, `PHARMACY_BILLING_DISPENSING_SEPARATION.md`.

Hospital EMR is a **view**. OpenMRS is the clinical source of truth. Odoo is the financial source of truth. This phase does not create invoices, payments, receipts, partners, stock moves, tax changes, or currency changes.

---

## 1. Routes

**IMPLEMENTED**

| Hash | Workspace |
|---|---|
| `#/patient-account/{patientUuid}` | Patient Account overview |
| `#/patient-account/{patientUuid}/invoice/{invoiceId}` | Read-only invoice detail |

Existing workspace routes are unchanged.

Entry points reuse current patient context (no second search):

- Patient workspace nav: Doctor, Nursing, Laboratory, Radiology, Pharmacy
- Order / prescription pages when a patient UUID is present
- Registration Desk tables: **Account** next to the existing Bahmni patient link
- Header search on the Patient Account page opens another account

---

## 2. Backend endpoints

**IMPLEMENTED** · **READ-ONLY**

Service: `abikan-api` (Python stdlib HTTP + XML-RPC).

Browser calls same-origin:

```
GET /openmrs/abikan-api/patient-account/{patientUuid}
GET /openmrs/abikan-api/patient-account/{patientUuid}/invoice/{invoiceId}
GET /openmrs/abikan-api/health
```

The path is under `/openmrs/` so the OpenMRS `JSESSIONID` cookie is sent. Apache (production) and Vite (dev) proxy that prefix to `abikan-api`. `POST` / `PUT` / `PATCH` / `DELETE` return 405.

Odoo credentials stay in the container environment. They are never sent to the browser.

---

## 3. Odoo models used

**CONFIRMED** on the installed Odoo 16, read only:

| Model | Fields used |
|---|---|
| `res.partner` | `name`, `ref`, `uuid` |
| `account.move` | `name`, `move_type`, `state`, `payment_state`, `amount_untaxed`, `amount_tax`, `amount_total`, `amount_residual`, `invoice_date`, `invoice_origin`, `currency_id`, `invoice_line_ids` |
| `account.move.line` | `name`, `quantity`, `price_unit`, `price_subtotal`, `price_total`, `tax_ids`, `product_id`, `sale_line_ids`, `move_id`, `currency_id` |
| `sale.order` | `name`, `state`, `origin`, amounts, `currency_id`, `invoice_ids`, `picking_ids`, `shop_id`, `order_line` |
| `sale.order.line` | `product_id`, `product_uom_qty`, `price_unit`, `order_id`, `external_order_id`, `external_id`, `invoice_lines` |
| `account.payment` | `name`, `amount`, `date`, `journal_id`, `currency_id`, `reconciled_invoice_ids`, `payment_method_id`, `state` |
| `stock.picking` | `name`, `sale_id`, `state`, `origin` |
| `product.product` | `name`, `categ_id` |
| `product.category` | `name`, `complete_name` |
| `account.tax` | `name`, `amount` |
| `res.currency` | `name`, `symbol`, `decimal_places`, `position` |
| `res.company` | `currency_id` (fallback when a patient has no invoice currency) |

`sale.order.order_type` is **not** present on this install. `order.type` exists as a model but is not the department join used here.

Vendor bills (`in_invoice`) are excluded.

---

## 4. OpenMRS data used

**CONFIRMED**

| Data | Use |
|---|---|
| Session `GET /openmrs/ws/rest/v1/session` | Server-side authorization |
| Patient `uuid`, display, identifiers | Identity + MRN |
| Existing `PatientIdentityHeader` fetch | Name, MRN, age, sex in the UI |

OpenMRS **Dispensed** observations are **not** read and **not** written.

---

## 5. Patient matching

**CONFIRMED** · **IMPLEMENTED**

```
OpenMRS patient uuid
  → OpenMRS MRN (preferred identifier, else first identifier, else display prefix)
  → Odoo res.partner.uuid = patient uuid
  → else res.partner.ref = MRN
```

Name is never the primary key. If no partner exists, the UI shows **Financial account not found.** No partner is created.

---

## 6. Invoice mapping

**CONFIRMED** · **IMPLEMENTED**

Domain: `move_type = out_invoice` and `partner_id =` the matched partner.

Displayed values come from Odoo:

- Number, date, state, `payment_state`
- `amount_untaxed`, `amount_tax`, `amount_total`, `amount_residual`
- Currency from `currency_id`

**Outstanding** is `amount_residual`. It is not assumed equal to `amount_total`.

**Paid** on an invoice is derived as `amount_total - amount_residual` from those two Odoo fields.

Posted invoices only are summed for the overview KPIs.

---

## 7. Payment mapping

**CONFIRMED** · **IMPLEMENTED**

Customer inbound `account.payment` rows for the partner.

Related invoice uses Odoo `reconciled_invoice_ids`. On the current database this field is populated (example: `PCSH1/2026/00001` → `INV/2026/00001`). Allocation is **not** inferred when that field is empty; the UI says allocation is not exposed.

Receipt PDF / print is **COMING SOON**. Existing payment references are listed; Hospital EMR does not generate a second receipt.

---

## 8. Pharmacy mapping

**CONFIRMED** · **IMPLEMENTED**

```
OpenMRS drug order uuid
  = sale.order.line.external_order_id
  → sale.order
  → account.move (invoice_ids / invoice_origin)
  → account.payment
  → stock.picking (sale_id)
```

Live example left untouched: Adaeze Okafor / `S00002` / `INV/2026/00001` / `PCSH1/2026/00001` / `WH/OUT/00001`.

---

## 9. Department identification

**IMPLEMENTED** from confirmed installed data only.

A row is labelled **Pharmacy** when:

1. `sale.order.shop_id` name contains `Pharmacy` (live shop is **Pharmacy Counter**), or
2. product category complete name contains `Drug` (live category `All / Saleable / Drugs / Tablet`)

Otherwise the UI shows **Department not identified**.

Registration, Clinical, Laboratory and Radiology are **not** labelled. Those charge paths are not installed. Empty department cards are not invented.

---

## 10. Currency handling

**CONFIRMED** · **IMPLEMENTED** · **READ-ONLY**

Symbol, code, decimal places and position are read from `res.currency`. The UI prints the server-formatted string. The shell does not hardcode `₦`, `NGN`, or `USD`.

The test company currency remains **USD**. It was not changed. Production Naira is **REQUIRES HOSPITAL DECISION**.

---

## 11. Tax handling

**CONFIRMED** · **IMPLEMENTED** · **READ-ONLY**

Invoice tax is `account.move.amount_tax`. Line tax names come from `account.tax.name`. The 15% demo tax was not removed and is not treated as Nigerian VAT. Hospital EMR does not recalculate tax.

---

## 12. Security

**IMPLEMENTED**

| Layer | Rule |
|---|---|
| Browser | Receives display JSON only. No Odoo URL, user, or password. |
| Vite | No `VITE_*` Odoo secrets. |
| API | Odoo credentials from container env (`ABIKAN_ODOO_*`). |
| Cookie | OpenMRS session cookie forwarded server-side to `/openmrs/ws/rest/v1/session`. |
| Methods | GET only. |
| Cache | `Cache-Control: no-store` on financial responses. |

---

## 13. Authorization

**IMPLEMENTED**

Server: authenticated OpenMRS session required (401 otherwise).

UI: `canOpenPatientAccount` — SuperAdmin / System Developer, or any of registration, clinical, ADT, lab-lite, radiology, pharmacy, admin privileges. Not location-locked.

---

## 14. Empty states

**IMPLEMENTED**

| Condition | Message |
|---|---|
| No Odoo partner | Financial account not found. |
| Partner, no invoices and no sale orders | No financial activity recorded. |
| Department with no records | Filter / card omitted |
| No payments | No payments recorded. |

---

## 15. Error states

**IMPLEMENTED**

| Code | Meaning |
|---|---|
| 401 `unauthenticated` | No OpenMRS session |
| 404 `patient_not_found` / `invoice_not_found` | Unknown patient or invoice |
| 422 `mrn_missing` | Patient has no MRN |
| 502 `openmrs_error` | Clinical service unavailable |
| 503 `odoo_error` / `odoo_config` | Financial service unavailable |
| 405 `read_only` | Write attempted |

---

## 16. Performance

**IMPLEMENTED**

One browser request loads the account. The API batches Odoo `search_read` / `read` for partner, invoices, orders, lines, payments, pickings, products, categories, taxes and currencies. Invoice detail reuses the same aggregation and selects one invoice.

Financial JSON is not cached.

---

## 17. Future payment gateway integration

**COMING SOON** · **REQUIRES HOSPITAL DECISION**

Not implemented: Paystack, Flutterwave, Moniepoint, Interswitch, cashier UI, collect payment, refunds, receipt printing.

Intended later path:

```
Hospital EMR → Nigerian provider → secure backend → Odoo payment
```

Odoo remains the ledger.

---

## 18. Known limitations

| Item | Status |
|---|---|
| Registration / consultation / lab / radiology invoices | None on this database. Honest empty. |
| Partial payment example | **NOT TESTED** — no real partial invoice exists. None was created. |
| `sale.order.order_type` | Missing on this Odoo 16. Shop + drug category used instead. |
| OpenMRS Dispensed | Unsafe / unused. Picking `state` is the dispense source. |
| Line-level paid on a shared invoice | Not supported by Odoo `payment_state`. Prefer one invoice per department later. |
| Stock on-hand in this UI | Not shown. |
| Receipt viewing | **COMING SOON** |
| Dedicated read-only Odoo user | **REQUIRES HOSPITAL DECISION** — API currently uses the configured Odoo user (default `admin`) server-side only. |
| Apache inject script | Re-applies `ProxyPass /openmrs/abikan-api` if the proxy image is recreated. |

Protected live records were not modified: `ORD-1`–`ORD-3`, `S00001`, `S00002`, `INV/2026/00001`, `PCSH1/2026/00001`, `P00001`, `WH/IN/00001`, `WH/OUT/00001`, TEST products, tax, currency, Pharmacy Counter stock.

### Verified against live data (read-only)

| Case | Patient | Result |
|---|---|---|
| No Odoo partner | Samson Mamah Luk `ABC200000` | Financial account not found. |
| Partner, no invoices or sale orders | John Adewale `ABC200012` | No financial activity recorded. |
| Pharmacy invoice paid + picking done | Adaeze Okafor `ABC200003` | Pharmacy · `INV/2026/00001` · PAID · DISPENSED · residual `$0.00` (USD from Odoo) |
| Unbilled draft sale order | Tunde Bakare `ABC200006` | Pharmacy · `S00001` · UNBILLED / UNPAID · amount `$0.00` from Odoo |
| Multiple posted invoices | — | No second posted invoice exists. UI lists invoices separately; none were created. |
| Partial payment | — | **NOT TESTED**. No real partial invoice. None was created. |
