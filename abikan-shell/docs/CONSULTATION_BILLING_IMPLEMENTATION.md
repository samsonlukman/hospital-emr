# Consultation billing — implementation

Date: **17 Aug 2026** (UTC). Controlled isolated TEST only.

Related: `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `ACCOUNTANT_PAYMENT_E2E_TEST.md`, `PATIENT_ACCOUNT_DEPARTMENTAL_CHARGES.md`, `REGISTRATION_BILLING_IMPLEMENTATION.md`, `PHARMACY_DISPENSING_IMPLEMENTATION.md`.

This phase implements:

```
Clinical / Doctor
  → open OPD visit
  → Consultation fee (Odoo sale order + posted invoice)
  → Patient Account UNPAID
  → Accountant payment (existing path)
  → Odoo invoice PAID
  → Clinical sees PAID
```

Odoo remains the financial source of truth. OpenMRS remains the clinical source of truth. There is no Hospital EMR ledger. Clinical does **not** collect money.

**PAID ≠ consultation completed.** Payment is an invoice state. The Consultation encounter remains an OpenMRS clinical record.

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **WRITE** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION** · **NOT PRESENT** · **NOT TESTED**

---

## 1. Existing consultation workflow

**CONFIRMED** · clinical path unchanged

| Step | What happens today |
|---|---|
| Home | Clinical Home → Doctor / Consultant (`#/doctor`) |
| Queue | Today's Queue. Opening a patient goes to `#/doctor/patient/{uuid}` |
| Consultation screen | `ConsultationWorkspace.tsx` — review, vitals, history, assess, diagnose, order, prescribe, disposition |
| Visit start | `POST /openmrs/ws/rest/v1/visit` via `startOpdVisit`. Visit type **OPD** `54f43754-c6ce-4472-890e-0f28acaeaea6`. Requires an open visit before save (`allowConsultationWhenNoOpenVisit` is false) |
| Encounter save | `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` via `saveConsultation` |
| Encounter type | **Consultation** `d34fe3ab-5e07-11ef-8f7c-0242ac120002`. Global property `bahmni.encounterType.default` = Consultation |
| Location | Login / session location (this test used **OPD-1**) |
| Provider | `GET /openmrs/ws/rest/v1/provider?user={userUuid}` |
| Patient | OpenMRS patient uuid + MRN |
| Clinical Home | Workspace picker only. No billing |

Bahmni Clinical SPA still exists. Hospital EMR does not replace the chart. This phase adds a **Consultation fee** status card on the existing Doctor consultation screen.

---

## 2. Existing encounter model

**CONFIRMED**

```
Patient
  → Visit (OPD / IPD / EMERGENCY / Special OPD / Follow Up)
       → Encounter type Consultation  (created on first bahmniencounter save)
            → observations, diagnoses, orders
```

Visit and encounter are **not** the same object.

- Starting a visit does **not** create a Consultation encounter.
- Saving vitals/diagnoses creates (or updates) the Consultation encounter.
- Subsequent saves in the same visit reuse the Consultation encounter on this install.

Live encounter types also include REG, ADMISSION, DISCHARGE, INVESTIGATION, LAB_RESULT, RADIOLOGY, TRANSFER, Patient Document, VALIDATION NOTES.

---

## 3. Existing consultation billing mechanisms

**NOT PRESENT** in Odoo. OpenMRS concepts exist but are **not** invoices.

| Search | Result | Label |
|---|---|---|
| Odoo product Consultation / Doctor Consultation / OPD Consultation / Medical Consultation / Clinical Consultation / Consultation Fee | none | **NOT PRESENT** |
| Odoo category Consultation / Clinical / OPD | none (before this TEST) | **NOT PRESENT** |
| Odoo shop Consultation | none (before this TEST) | **NOT PRESENT** |
| Odoo `order.type` | **Drug Order** only | **CONFIRMED** |
| OpenMRS concept **Consultation Fee** `9bb0795c-4ff0-0305-1990-000000000023` | Numeric Misc obs on a Bahmni form | **CONFIRMED** not billing |
| OpenMRS concept **Consultation fees** `30ece51c-9065-4f5a-bd4d-db5e299d8ff9` | Misc / N/A | **CONFIRMED** not billing |
| Bahmni `REGISTRATION FEES` / form `CONSULTATION_FEE_20` | clinical observation widget | **CONFIRMED** not an Odoo invoice |
| Atomfeed / odoo-connect Drug Order map | Pharmacy Counter only | **CONFIRMED** cannot carry consultation |

Do **not** treat the OpenMRS Consultation Fee concept as a charge. It is the same class of mistake as treating Bahmni `REGISTRATION FEES` as billing.

---

## 4. Consultation charge model

**IMPLEMENTED** · **WRITE** via Odoo ORM

Same departmental pattern as Registration. **Not** Pharmacy Drug Order. **Not** Atomfeed.

```
OpenMRS patient uuid / MRN
  → res.partner (uuid / ref)
  → sale.order (shop = Consultation Desk)
       line.external_order_id = consultation:{visitUuid}
       line.external_id = visitUuid
  → action_confirm
  → posted out_invoice  (bahmni_sale.is_invoice_automated = True)
  → Accountant account.payment.register
```

Why the visit, not the encounter, is the idempotency key:

- The chargeable hospital event is “this OPD visit’s consultation”.
- The Consultation encounter does not exist until the doctor saves clinical data.
- Multiple saves of the same consultation must not create multiple invoices.
- A later visit gets a new visit uuid and therefore a new charge.

Encounter uuid is read back when present and returned on the API. It is **not** the financial key. Name is never the financial key.

Staff-facing states: **UNPAID** / **PAID**, from `payment_state` + `amount_residual`. No `consultation.isPaid` field in Hospital EMR.

---

## 5. Odoo product / service

**IMPLEMENTED** · isolated TEST masters created on first Clinical GET/POST. Existing Pharmacy and Registration products were not modified.

| Object | Value | Label |
|---|---|---|
| `product.category` | **All / Services / Consultation** id **39** | **WRITE** (new) |
| `product.product` | **Consultation Fee — TEST** id **2390** | **WRITE** (new) |
| Type | `service` | **CONFIRMED** |
| Category | All / Services / Consultation | **CONFIRMED** |
| Price | `list_price` **75.00** (from Odoo, not React) | **CONFIRMED** TEST |
| UoM | Units (id 1) | **CONFIRMED** |
| Tax | none (`taxes_id` empty) | **CONFIRMED** |
| Invoice policy | `order` | **CONFIRMED** |
| `sale.shop` | **Consultation Desk** id **3**, `location_id` empty | **WRITE** (new) |

Production will eventually need an approved service product (name, price, tax-exempt, shop). That product must be configured in Odoo, not hardcoded in the UI.

**REQUIRES HOSPITAL DECISION** production fee amount. **REQUIRES ACCOUNTING CONFIGURATION** production product / tax-exempt setup.

Do not reuse Pharmacy Counter (would label Pharmacy and risk stock). Do not reuse Registration Desk (would label Registration).

---

## 6. Price source

**IMPLEMENTED**

React never sends a price. The backend reads `product.product.list_price` at charge time. Currency formatting comes from Odoo.

TEST list price **75.00** is isolated on product **2390**. It is not a hospital-approved production fee.

---

## 7. Tax behavior

**CONFIRMED**

| Environment | Behavior | Label |
|---|---|---|
| CURRENT TEST | Product 2390 has no customer tax. Invoice **INV/2026/00004** `amount_tax` **0**. Tax 15% (id 1) was **not** deleted or changed | **CONFIRMED** |
| REQUIRED PRODUCTION | Patient service products should be tax-exempt per hospital policy, without globally removing Tax 15% | **REQUIRES ACCOUNTING CONFIGURATION** |

Line `tax_id` is cleared on create, matching Registration.

---

## 8. Currency behavior

**CONFIRMED** · **READ-ONLY**

Company currency remains **USD**. Display amounts come from Odoo (`$75.00`). The application does not hardcode NGN or USD.

NGN cutover is a separate Operations/accounting task.

---

## 9. Patient linkage

**IMPLEMENTED**

| Key | Value |
|---|---|
| Patient | OpenMRS uuid → `res.partner.uuid` |
| MRN | → `res.partner.ref` |
| This test | Chinedu Okonkwo **ABC200004**, uuid `53818ff4-f122-4e3f-a7c9-463b84fd02c9`, partner id **9** |

Name is never the financial key. Missing partner → `409 account_not_found`.

---

## 10. Visit linkage

**IMPLEMENTED**

| Key | Value |
|---|---|
| Visit required | POST without visit → `422 visit_required` |
| Visit ownership | Visit patient uuid must match → `409 wrong_patient` |
| Missing visit | `404 visit_not_found` |
| Line key | `consultation:{visitUuid}` |
| Origin | sale order `origin` = visit uuid |
| This test | `1fa5e9f4-5ffa-41ab-90eb-c347cd2c5daa` OPD @ OPD-1, open |

A previous closed OPD visit on this patient (`074df499-8379-45b3-a7e5-e662350591ab`, 13 Aug, no encounters) was **not** reused.

---

## 11. Encounter linkage

**CONFIRMED** · optional, not the charge key

| When | Encounter |
|---|---|
| After visit start, before save | none |
| After charge create | still none |
| After clinical save (pulse 72, while invoice still UNPAID) | Consultation `88c5772e-4f4b-4ccb-8e98-04a7c86a3bae` |
| After payment | same encounter, not voided |

Saving the chart while UNPAID succeeded. Payment did not complete or close the encounter.

---

## 12. Invoice linkage

**CONFIRMED**

`sale.order.action_confirm` + installed `is_invoice_automated=True` posted **INV/2026/00004**. Origin **S00005**. Partner Chinedu Okonkwo. Tax **0**. Residual before pay **75.00**, after pay **0**. `payment_state` **paid**.

No SQL. No direct `account.move` create. No delivery picking (service product).

---

## 13. Accountant workflow

**UNCHANGED** · reused

Existing `POST /openmrs/abikan-api/accountant/payment` → `account.payment.register`.

Clinical has **no** Pay button, journal picker, or payment endpoint access from the Doctor screen.

This test: Cash journal id **6**, **PCSH1/2026/00004** $75.00. Second pay → **409 invoice_already_paid**.

`registration` user POST payment → **403**.

---

## 14. Payment status

**IMPLEMENTED** · Odoo is authoritative

| Source | Use |
|---|---|
| `account.move.payment_state` | `paid` / `in_payment` + residual ≤ 0.009 → **PAID**, else **UNPAID** |
| `amount_residual` | outstanding shown from Odoo |

No Hospital EMR `isPaid` column. Frontend does not permanently store payment status.

---

## 15. Clinical payment status

**IMPLEMENTED**

Doctor consultation screen shows:

- Consultation fee
- Amount from Odoo
- **UNPAID** or **PAID**
- If UNPAID: **Payment required** / Please proceed to the cashier
- If no charge yet: **Create consultation fee** (confirm dialog; Clinical does not collect money)

The clinical chart is **not** blocked when UNPAID.

---

## 16. Duplicate protection

**IMPLEMENTED**

1. Odoo line search `external_order_id = consultation:{visitUuid}` — existing sale is returned
2. Server lock on that key and optional `requestId`
3. Retry with a new `requestId` for the same visit still returns the existing charge (`alreadyCreated: true`)

Live: two duplicate POSTs reused **S00005** / **INV/2026/00004**. Exactly one consultation line exists.

---

## 17. Permissions

**IMPLEMENTED**

| Actor | Create / see consultation charge | Register payment |
|---|---|---|
| `app:clinical` or SuperAdmin / System Developer | yes | **no** (unless they also have Accountant rights) |
| `app:registration` only | **no** (403) | **no** (403) |
| Unauthenticated | 401 | 401 |
| Accountant (`abikan:accountant` or SuperAdmin) | no Clinical charge UI required | **yes** existing path |

This TEST used `abikan.admin` (SuperAdmin) for both charge create and payment. `registration` cannot create a consultation charge and cannot pay.

Dedicated `dr_neha` (Doctor role) password was not used. **NOT TESTED** for a clinical-only user without SuperAdmin.

Clinical cannot choose journal, refund, change price, tax, or currency.

---

## 18. Security

**IMPLEMENTED**

- Browser sends patient uuid, visit uuid, `requestId` only
- Odoo credentials stay in `abikan-api`
- Session required; Clinical privilege required for writes
- Visit must belong to the patient
- Price comes from the Odoo product, not from the browser
- Charge type is the Consultation shop + product, not a client-supplied ledger code
- No Odoo credentials in React, Vite env, storage, or API responses

---

## 19. UX decisions

**IMPLEMENTED**

- Existing Doctor consultation interface kept
- Compact **Consultation fee** card under the patient identity header
- Staff language: Consultation fee, Payment, PAID / UNPAID, Please proceed to the cashier
- No sale order / invoice / Odoo / Atomfeed / UUID shown on the Doctor screen
- Primary action: **Create consultation fee** only when none exists for the visit
- Confirm: “This sends the bill to the cashier. Clinical does not collect money.”
- Unpaid does **not** hide vitals, diagnosis, or Save consultation
- Payment failure on the fee card does not take over the whole chart

Visual click-through of the React confirm dialog was **NOT TESTED**. The POST the button calls was executed.

---

## 20. Test patient

**CONFIRMED** isolated patient with partner and **no** prior financial activity. Not Adaeze / Aisha / Tunde / John / Blessing.

| Field | Before | After |
|---|---|---|
| Name | **Chinedu Okonkwo** | same |
| MRN | `ABC200004` | same |
| OpenMRS uuid | `53818ff4-f122-4e3f-a7c9-463b84fd02c9` | same |
| Odoo partner | id **9**, no sale orders, no invoices, no payments, no pickings | **S00005** / **INV/2026/00004** / **PCSH1/2026/00004** |
| Prior visit | closed OPD `074df499-…` 13 Aug, **no encounters** | unused |
| New visit | none open | `1fa5e9f4-5ffa-41ab-90eb-c347cd2c5daa` OPD @ OPD-1 |
| Drug orders | none | none |

---

## 21. Test charge

**CONFIRMED** · **WRITE**

| Field | Value |
|---|---|
| Created by | OpenMRS user **abikan.admin** |
| Sale order | **S00005** id 5, shop Consultation Desk, tax 0, total 75.00 |
| Line key | `consultation:1fa5e9f4-5ffa-41ab-90eb-c347cd2c5daa` |
| Product | **2390** Consultation Fee — TEST |
| Picking | none |

---

## 22. Test invoice

**CONFIRMED**

**INV/2026/00004** id **7**, posted, then **paid**. Tax **0**. Residual after pay **0**.

---

## 23. Test payment

**CONFIRMED**

**PCSH1/2026/00004** id **4**, Cash, 75.00 USD, posted. Paid by `abikan.admin` via existing Accountant POST.

---

## 24. Final status

**CONFIRMED** Clinical GET returns **PAID**, outstanding `$0.00`, encounter still present. Patient Account department **Consultation**, payment history **PCSH1/2026/00004**.

---

## 25. Protected records

**CONFIRMED** unchanged

| Record | After this phase |
|---|---|
| ORD-1 / ORD-2 / ORD-3 / ORD-4 | Pharmacy queue still Adaeze ORD-3 DISPENSED, Aisha ORD-4 DISPENSED, Tunde ORD-2 UNPAID. Chinedu not in queue |
| S00001–S00004 | unchanged. New **S00005** only |
| INV/2026/00001–00003 | unchanged. New **INV/2026/00004** only |
| PCSH1/2026/00001–00003 | unchanged. New **PCSH1/2026/00004** only |
| P00001, WH/IN/00001, WH/OUT/00001, WH/OUT/00002 | unchanged |
| Product 2385 | stock **88**, tax 15% still on the product |
| Registration product 2389 | unchanged 50.00, no tax |
| Blessing registration | still **PAID** $50 |
| Tax 15% | amount 15, not deleted |
| Company currency | USD |
| OpenMRS Dispensed | not written. Chinedu has **no** drug orders |

---

## 26. Known limitations

**CONFIRMED**

- Odoo `write_uid` is the XML-RPC service user. Hospital EMR `recordedBy` is the OpenMRS username. No second audit table
- Patient Account description shows the TEST product name (existing invoice description behavior)
- SuperAdmin can both create the charge and pay. A dedicated doctor-only vs cashier-only split needs hospital user setup
- Odoo unavailable → expected 503; **NOT TESTED** by stopping Odoo
- Visual Doctor UI click-through **NOT TESTED**

**COMING SOON** (explicitly out of this phase)

- Laboratory billing
- Radiology billing
- Nigerian payment gateway
- Refunds
- OpenMRS Dispensed repair
- Currency migration to NGN

---

## 27. Hospital decisions

**REQUIRES HOSPITAL DECISION**

1. **When to create the charge.** The installed stack supports creating it as soon as an OPD visit exists (this TEST: doctor creates it from the consultation screen). It does **not** require a saved encounter. Registration-time auto-charge is not implemented.
2. **Must payment be received before the doctor continues?** This phase does **not** block the chart. The unpaid state already shows “Payment required / Please proceed to the cashier.” A future gate can use that status without rewriting billing.
3. **Emergency / exception bypass** if a payment gate is later enabled.
4. **Return visit / Follow Up pricing.** OpenMRS has a **Follow Up** visit type, distinct from OPD. Not priced in this phase.
5. **Different prices by doctor, specialty, clinic, or location.** Architecture is one Odoo service product / list price (or later additional products). UI does not hardcode prices.
6. **Production consultation fee amount** (replace TEST 75.00).
7. **Department label** is **Consultation** (not “Clinical”) so it sits beside Registration and Pharmacy.

**REQUIRES ACCOUNTING CONFIGURATION**

- Production tax-exempt consultation product without deleting Tax 15%
- Dedicated cashier / clinician OpenMRS users and `abikan:accountant` privilege
- NGN company currency when Operations is ready

---

## 28. Future Nigerian gateway architecture

**COMING SOON** · **REQUIRES HOSPITAL DECISION**

```
Department charge (Consultation / Registration / Pharmacy)
  → Accountant / Cashier
  → Nigerian payment gateway
  → secure Hospital EMR backend
  → same account.payment.register
  → invoice PAID
  → department reads payment_state
```

Do not bypass Odoo. Do not create a second Hospital EMR ledger.

---

## When should the charge be created?

What the existing system **supports** (not a policy choice):

| Option | Supported now? |
|---|---|
| A. Registration payment then auto consultation charge then consult | Not built. Registration fee is a separate visit-keyed invoice |
| B. Consultation begins (open visit) → doctor creates charge → cashier → consult continues | **IMPLEMENTED**. Chart remains usable while UNPAID |
| C. Charge created after registration paid, block doctor until paid | Charge creation does not depend on registration PAID. Blocking the chart is **not** implemented |

**REQUIRES HOSPITAL DECISION** which option is hospital policy. Billing records stay visit-keyed so the payment requirement can change in the UI without a new ledger.

---

## Multiple consultations / return visits

| Case | Behavior |
|---|---|
| Same visit, retry / refresh / second tab | Same `consultation:{visitUuid}` → existing invoice |
| Later visit | New visit uuid → new charge |
| Return / Follow Up visit type | Distinguishing visit type exists; separate price **not** implemented |

---

## API

| Method | Path | Privilege |
|---|---|---|
| GET | `/openmrs/abikan-api/consultation/patient/{uuid}` | `app:clinical` or SuperAdmin |
| POST | `/openmrs/abikan-api/consultation/patient/{uuid}/charge` body `{ visitUuid, requestId }` | same |

Browser must not call Odoo.

---

## Test results

| Step | Result | Label |
|---|---|---|
| Investigate live stack | No consultation Odoo product; OpenMRS Fee concept is an obs | **CONFIRMED** |
| Open Clinical / isolated patient | Chinedu, no open visit, not billed | **CONFIRMED** |
| Start OPD visit | `1fa5e9f4-…` at OPD-1 | **CONFIRMED** |
| Create exactly one fee | S00005 + INV/2026/00004 UNPAID, tax 0 | **CONFIRMED** |
| Duplicate POST | reused S00005 | **CONFIRMED** |
| Save consultation while UNPAID | encounter `88c5772e-…`, chart not blocked | **CONFIRMED** |
| Patient Account | Consultation UNPAID $75 | **CONFIRMED** |
| Accountant pay | PCSH1/2026/00004 | **CONFIRMED** |
| Invoice PAID residual 0 | yes | **CONFIRMED** |
| Clinical GET PAID | yes | **CONFIRMED** |
| Second payment | 409 already paid | **CONFIRMED** |
| Unauthenticated | 401 | **CONFIRMED** |
| Registration cannot charge or pay | 403 | **CONFIRMED** |
| Invalid visit | 404 | **CONFIRMED** |
| Missing visit on POST | 422 | **CONFIRMED** |
| Invalid patient | 404 | **CONFIRMED** |
| Wrong patient’s visit | 409 | **CONFIRMED** |
| Pharmacy queue | Chinedu absent; ORD-2/3/4 unchanged | **CONFIRMED** |
| OpenMRS prescriptions | Chinedu has none; Dispensed not written | **CONFIRMED** |
| Registration billing | Blessing still PAID $50 | **CONFIRMED** |
| `npm run build` | passed | **CONFIRMED** |
| Odoo down | not executed | **NOT TESTED** |
| Dedicated clinical-only user | no isolated password used | **NOT TESTED** |

---

## Stop

This phase stops at **Clinical sees PAID**.

Do **not** start Laboratory or Radiology billing. Do **not** implement a payment gateway. Do **not** change Pharmacy or Registration billing. Do **not** change Accountant payment. `bahmni_sale.is_invoice_automated` remains True.

---

*End of implementation.*
