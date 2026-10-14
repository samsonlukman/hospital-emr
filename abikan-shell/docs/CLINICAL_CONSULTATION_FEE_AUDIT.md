# Clinical consultation fee — investigation

Date: **23 Aug 2026** (Africa/Lagos). **Investigation only.**

No Clinical UI, consultation-fee logic, Odoo, OpenMRS, products, invoices, charges, patients, or visits were created or changed.

Related: `CONSULTATION_BILLING_IMPLEMENTATION.md` (17 Aug 2026 implementation), `RECEPTION_CAPABILITY_AUDIT.md` § Medical Officer vs Consultant — Final Mapping (22 Aug 2026).

Evidence: current Hospital EMR source (`consultation.py`, `ConsultationFeeCard.tsx`, `consultation.ts`, `accountant.py`, `server.py`), plus read-only OpenMRS MySQL and Odoo PostgreSQL. The Clinical GET was **not** called (it can write TEST masters if they are missing).

---

## Consultation Fee — Current Flow and Doctor-Entered Fee

### Classification used

| Label | Meaning |
|---|---|
| **EXISTS AND WORKS** | Present and used on this stack |
| **EXISTS BUT NOT CONFIGURED** | Object exists; hospital values are empty or seed-only |
| **EXISTS BUT NOT EXPOSED IN ABIKAN** | Present in OpenMRS/Odoo; Hospital EMR does not show or use it |
| **MISSING** | Not built |
| **REQUIRES HOSPITAL DECISION** | Policy or production amount/currency, not a code gap alone |

---

### 1. How consultation fees currently work

**EXISTS AND WORKS** (fixed TEST amount, Clinical create → Accountant collect).

```
Doctor opens chart (#/doctor/patient/{uuid})
  → Consultation fee card (display only)
  → Create consultation fee → Confirm fee
  → POST /openmrs/abikan-api/consultation/patient/{uuid}/charge
       body: { visitUuid, requestId }   ← no amount
  → abikan-api require_clinician (app:clinical)
  → Odoo sale.order at shop Consultation Desk
       line.external_order_id = consultation:{visitUuid}
       price_unit = product.list_price
  → action_confirm
  → posted customer invoice (bahmni_sale automated invoicing)
  → Patient Account shows department Consultation, UNPAID
  → Accountant POST /openmrs/abikan-api/accountant/payment
  → Odoo account.payment.register
  → invoice payment_state paid
  → Clinical GET reads Odoo → PAID
```

Staff-facing field: **Consultation fee** on the Doctor consultation screen (`ConsultationFeeCard`), under the patient header. It shows the formatted amount and UNPAID / PAID / Not billed yet. Primary action is **Create consultation fee**. There is no amount input and no Pay button.

| Step | Current behavior | Classification |
|---|---|---|
| Field location | Clinical consultation screen only | **EXISTS AND WORKS** |
| API | GET `…/consultation/patient/{uuid}` · POST `…/charge` | **EXISTS AND WORKS** |
| Browser payload | `{ visitUuid, requestId }` only | **EXISTS AND WORKS** |
| Amount from React | None | **MISSING** (by design today) |
| Amount source | Odoo `product.product` **Consultation Fee — TEST** `list_price` **75.00** | **EXISTS AND WORKS** |
| Charge creator | Logged-in Clinical user | **EXISTS AND WORKS** |
| Invoice | Confirm sale → posted `out_invoice` | **EXISTS AND WORKS** |
| Accountant collect | Existing payment path; residual from the invoice | **EXISTS AND WORKS** |
| Status back to Hospital EMR | Odoo `payment_state` + `amount_residual` | **EXISTS AND WORKS** |
| Reception pricing or collect | Not in this path | Do not add |
| Clinical Pay | Not present | Do not add |

Live TEST charges (already existed; not created this pass):

| Sale | Line key | Product | Unit price | Currency | Invoice | Payment |
|---|---|---|---|---|---|---|
| S00005 | `consultation:1fa5e9f4-…` (Chinedu ABC200004) | Consultation Fee — TEST | 75.00 | USD | INV/2026/00004 | paid |
| S00020 | `consultation:481610eb-…` (Ibrahim ABC200008) | Consultation Fee — TEST | 75.00 | USD | INV/2026/00019 | paid |

Both lines use the same product and the same **75.00**. `sale.order.provider_name` is empty. `create_uid` is Odoo **admin** (XML-RPC service user), not the doctor.

---

### 2. Where the current $75 comes from

**EXISTS AND WORKS** as a TEST catalogue price. It is **not** a hospital-approved production fee.

| Source | Value | Used when |
|---|---|---|
| Odoo product **2390** `list_price` | **75.00** | Every create. Backend: `price = as_float(product.get("list_price"))` then `price_unit` |
| Python `TEST_LIST_PRICE = 75.0` | 75.0 | Only if the TEST product is **missing** and `ensure_consultation_masters` creates it |
| React | No amount | Never |
| Pricelist | **Public Pricelist** (USD, id 1) on shop **Consultation Desk** | Sale currency / shop |
| Company currency | **USD** (Bahmni company) | Display formatting (`load_currency(reader, None)` uses company currency, not the invoice currency) |

`$75` is therefore an **Odoo list price**, copied onto the sale line. It is not hardcoded in the Clinical UI. Changing the Odoo list price would change every **future** charge and the pre-create preview. It would not rewrite already posted invoices.

---

### 3. How the doctor is identified

| Identity | Used for consultation **save** | Used for consultation **fee** |
|---|---|---|
| Logged-in Hospital EMR user | Session / workspace context | Privilege check only (`app:clinical`) |
| OpenMRS user | Same session | `require_clinician` → username on first-create response as `recordedBy` |
| OpenMRS provider | `GET /openmrs/ws/rest/v1/provider?user={userUuid}` then encounter `providers: [{ uuid }]` | **Not used** |
| Provider UUID | Written on the Consultation encounter | **Not stored on the charge** |
| Visit | Required for save | **Charge key** `consultation:{visitUuid}` |
| Encounter | Created/updated on clinical save | Read back if present; **not** the financial key |

| Finding | Classification |
|---|---|
| Logged-in doctor on the Consultation encounter | **EXISTS AND WORKS** |
| Charge created only by a Clinical session | **EXISTS AND WORKS** |
| Charge tied to the provider | **MISSING** |
| Durable “who billed this” on the Odoo order | **MISSING** (`provider_name` unused; `recordedBy` is response-only; Odoo `create_uid` is the service user) |

The fee belongs to **the visit**, not to a named Medical Officer or Consultant row. That is enough for billing. It is not enough for “this invoice was Dr X’s fee” without a later write to `sale.order.provider_name` or equivalent.

---

### 4. How the charge reaches Odoo

**EXISTS AND WORKS.** Same departmental pattern as Registration. Not Atomfeed. Not Pharmacy Drug Order.

1. Clinician POST with visit uuid.
2. Server finds `res.partner` by OpenMRS patient uuid / MRN.
3. `ensure_consultation_masters` loads (or would create) category **All / Services / Consultation**, product **Consultation Fee — TEST**, shop **Consultation Desk**.
4. Creates `sale.order` (`shop_id` Consultation Desk, `pricelist_id` from that shop, `origin` = visit uuid, `care_setting` = `opd`).
5. One service line: qty 1, `price_unit` = list price, `tax_id` empty, `external_order_id` = `consultation:{visitUuid}`.
6. `action_confirm`. Automated invoicing posts the customer invoice.

Odoo remains the ledger. Hospital EMR does not insert `account.move` or payment rows for this charge.

---

### 5. How Accountant collects it

**EXISTS AND WORKS.** No consultation-specific cashier screen.

Patient Account lists posted invoices and labels shop/category **Consultation**. Accountant selects the unpaid invoice, enters an amount (defaults to that invoice’s outstanding), chooses a journal, and POSTs `accountant/payment`. Odoo `account.payment.register` records the payment.

Clinical and Reception payment POSTs remain 403. The Doctor screen only says “Please proceed to the cashier.”

After pay, Clinical GET maps `payment_state` in `{paid, in_payment}` and residual ≈ 0 → **PAID**.

Accountant does not care that the product list price is 75. It collects **the invoice residual**. A different `price_unit` on a future invoice would be collected the same way.

---

### 6. Whether variable doctor-entered fees can use the existing architecture

**Yes**, without a second ledger.

| Question | Answer | Classification |
|---|---|---|
| 1. Can the existing fee field accept a doctor-entered amount? | **No.** It is a read-only fact (`charge.feeAmount.formatted`) plus Create. | **MISSING** (UI + POST body) |
| 2. Is the current Odoo product suitable for variable charges? | **Yes as a generic service line.** Keep one product; override `price_unit`. Do not create a product per amount. The TEST name/price are not production-ready. | **EXISTS AND WORKS** (line price) · **REQUIRES HOSPITAL DECISION** (production product/name) |
| 3. Can the integration supply invoice line price per consultation? | **Yes.** Create already writes `sale.order.line.price_unit`. Today that value is copied from `list_price`. A validated doctor amount can be written instead. | **EXISTS BUT NOT EXPOSED IN ABIKAN** |
| 4. Is $75 hardcoded? | In React: **no**. In Python: only as fallback when creating a missing TEST product. Live price is Odoo 75.00. | **EXISTS AND WORKS** |
| 5. Price from Odoo or Hospital EMR? | **Odoo** list price today. Display currency from **company** USD. | **EXISTS AND WORKS** |
| 6. Can two consultations have different amounts? | Different **visits** can, if `price_unit` differs. Today both live charges are 75. Same visit cannot have two charges. | **EXISTS AND WORKS** (visit key) · amount variety **MISSING** |
| 7. Can the same doctor set different amounts for different patients? | Same as above: per visit, not per doctor. Identity is not required for different amounts. | **MISSING** (entry) · architecture allows it |
| 8. Is the amount validated? | **No amount is sent.** No min/max/decimal check. | **MISSING** |
| 9. Where should validation occur? | **Server first** (positive, finite, decimal places, hospital max). UI should prevent obvious mistakes. Do not trust the browser alone. | Implementation item |
| 10. Can Accountant collect a variable amount without modification? | **Yes.** Collection uses invoice residual, not the product list price. | **EXISTS AND WORKS** |

Medical Officer vs Consultant classification is **not** required for variable fees. The consulting doctor enters the amount for that visit.

---

### 7. What must change to support variable fees

Do **not** implement in this investigation. Required later:

1. **Clinical UI** — amount field on the existing Consultation fee card (Create still sends the bill; still no Pay).
2. **POST body** — `{ visitUuid, requestId, amount }` (name as hospital language in the UI; keep the JSON field internal).
3. **`create_consultation_charge`** — validate amount; set `price_unit` to that amount; do **not** rewrite `product.list_price` (that would change every future preview and every other visit).
4. **GET preview** — before create, show the doctor’s entered amount (or a blank “enter the fee”), not only $75.
5. **Currency** — see §9. Do not ship production variable USD fees if the rest of the hospital is NGN.
6. **Unpaid correction** — new, explicit path (see §8). Today a second POST does not change the amount.
7. **Optional audit** — write OpenMRS username or provider display onto `sale.order.provider_name` (column exists, unused). Not required for the fee to work.

| Must not change | Why |
|---|---|
| One Odoo invoice ledger | No Hospital EMR fee table |
| `consultation:{visitUuid}` | One charge per visit |
| Accountant payment API | Already amount-agnostic |
| Reception | Must not price or collect consultation |
| Clinical Pay button | Doctor must not collect money |
| New visit types / doctor-category table | Unrelated to the fee mechanism |

---

### 8. How duplicate charges are prevented

**EXISTS AND WORKS** for create. **MISSING** for amount correction.

| Event | What happens |
|---|---|
| Doctor opens the chart twice | GET only. No charge until Confirm fee. |
| Confirm / save fee twice (same or new `requestId`) | In-memory lock → `409 charge_in_progress` or `alreadyCreated`. Odoo search `external_order_id = consultation:{visitUuid}` returns the existing sale. Draft sales are confirmed; posted ones are reused. |
| Refresh after create | GET finds the existing line. Create is not called. |
| Two tabs, same visit | Same Odoo key. Second create returns the first invoice. |
| Later visit | New visit uuid → new key → new invoice. |

One-charge-per-visit rule: **yes**, the Odoo line key. Process restart drops the in-memory lock; the Odoo key still holds.

In-memory lock alone is **not** enough. The Odoo key is the real guard. Keep it.

---

### 9. How fee editing should work

| Capability | Today | Classification |
|---|---|---|
| Set the fee once | Create copies list price 75 | **EXISTS AND WORKS** |
| Edit before payment | Second POST returns the same invoice; amount unchanged | **MISSING** |
| Edit after payment | Same reuse; invoice stays paid at 75 | **MISSING** (correct: must stay blocked) |
| Replace amount | No PATCH / update route | **MISSING** |
| Second charge for the same visit | Prevented | **EXISTS AND WORKS** |

Important current Odoo behavior: confirm + automated invoicing **posts the invoice immediately**. Even an unpaid consultation invoice is already **posted**, not draft. There is no Hospital EMR API to rewrite a posted invoice line, cancel it, or issue a credit note.

**Recommended rule (do not implement yet):**

- **Before first create:** doctor enters the amount, then creates the charge.
- **After create, before payment:** doctor may **correct** the fee through an explicit Clinical action that accounting-safely replaces the unpaid posted invoice (credit note or cancel-and-recreate) **while keeping** `consultation:{visitUuid}` as the single live charge. Silent overwrite of a posted invoice is unsafe. A second `consultation:{visit}` line is forbidden.
- **After payment:** Clinical must not change the amount. Show PAID. Corrections go through Accountant refund / credit note / adjustment in Odoo.

Hospital expected rule matches this. Current code cannot correct an unpaid amount at all.

---

### 10. Medical Officer vs Consultant (unchanged)

**The system still cannot distinguish them.** This does **not** block doctor-entered fees.

Re-checked 23 Aug 2026 (read-only):

| Mechanism | Live state | Classification |
|---|---|---|
| Providers + person names | 12 providers, including `doctor.abikan` / `abikan.doctor` | **EXISTS AND WORKS** |
| `providermanagement_provider_role` | **0 rows** | **EXISTS BUT NOT CONFIGURED** |
| `practitioner_type` options | `handler_config` = `,Doctor` only | **EXISTS BUT NOT CONFIGURED** |
| `practitioner_type` values | Only **Neha Anand** = `Doctor`. Hospital EMR doctors have none | **EXISTS BUT NOT CONFIGURED** |
| Appointment specialities | General Medicine, ENT only | **EXISTS BUT NOT CONFIGURED** for this hospital |
| Appointment services | GM/ENT OPD, Follow-up, Procedure | Seed data, not a consultant roster |
| Special OPD | Retrospective data entry | Do not use as Consultant |

The fee should belong to **the doctor conducting this consultation** (logged-in Clinical user / their provider on the encounter), whether or not they are later tagged Medical Officer or Consultant.

---

### 11. Currency

| Item | Live value | Classification |
|---|---|---|
| Clinical TEST consultation | **USD 75.00** | **EXISTS AND WORKS** (TEST) |
| Odoo company currency | **USD** | **EXISTS AND WORKS** |
| Consultation shop pricelist | **Public Pricelist** · **USD** | **EXISTS AND WORKS** |
| NGN currency | Active (`res.currency` NGN ₦) | **EXISTS AND WORKS** |
| NGN pricelists already in use | Hospital Pharmacy, Hospital Registration, Hospital Laboratory | **EXISTS AND WORKS** |
| Consultation on NGN | **No** | **MISSING** for production |
| Radiology Desk / Accommodation shops | Still Public Pricelist **USD** | Out of scope here |

Hospital EMR display for the consultation card uses **company** currency. That is correct while company and consultation invoices are both USD. If Consultation Desk moves to NGN while the company stays USD, amounts would be formatted with the wrong symbol unless `load_currency` is given the invoice/sale `currency_id`.

**Production requirement:** consultation must use **NGN** before go-live, consistent with Registration / Pharmacy / Laboratory. Amount, pricelist, and display currency are an accounting cutover. **Do not change currency in this investigation.**

**REQUIRES HOSPITAL DECISION:** production NGN amount policy (typical MO fee, typical Consultant fee, or fully free-typed per visit). The mechanism does not need those labels to exist first.

---

### 12. Answers

**1. How consultation fees currently work.**  
Doctor creates a fixed Odoo service invoice for the open visit. Accountant collects. Clinical shows PAID/UNPAID from Odoo. **EXISTS AND WORKS.**

**2. Where the current $75 comes from.**  
Odoo product **Consultation Fee — TEST** list price 75.00 USD, copied to `price_unit`. React sends no amount.

**3. How the doctor is identified.**  
Clinical session + OpenMRS user for permission. Provider UUID is used on encounter save only. The charge is visit-keyed and does not store the provider.

**4. How the charge reaches Odoo.**  
`POST …/charge` → sale order on Consultation Desk → confirm → posted invoice. Key `consultation:{visitUuid}`.

**5. How Accountant collects it.**  
Existing Patient Account + `accountant/payment` against the invoice residual.

**6. Whether variable doctor-entered fees can use the existing architecture.**  
**Yes.** Same product, same shop, same key, same Accountant path; supply `price_unit` per visit.

**7. What must change to support variable fees.**  
Clinical amount field; validated amount on POST; write `price_unit`; unpaid correction path; NGN cutover for production. Do not add a ledger or Reception pricing.

**8. How duplicate charges are prevented.**  
Odoo `external_order_id` plus in-memory lock. One charge per visit. **EXISTS AND WORKS.**

**9. How fee editing should work before payment.**  
Today: cannot. Recommended: explicit correct-unpaid-fee that replaces the posted unpaid invoice without a second visit key.

**10. What should happen after payment.**  
Do not let Clinical change the paid invoice. Use Accountant refund/adjustment.

**11. Whether currency must be changed to NGN.**  
**Yes before production.** Consultation is still USD. NGN exists and is already used by other hospital shops. **REQUIRES HOSPITAL DECISION** on amounts; **REQUIRES ACCOUNTING CONFIGURATION** on shop/pricelist/company.

**12. What should NOT be built.**

- A second billing/fee ledger in Hospital EMR
- Reception consultation pricing or collection
- A Pay button or cash collection in Clinical
- New visit types for Medical Officer / Consultant
- A Hospital EMR doctor-category table
- One Odoo product per amount
- Silent edits to paid invoices
- Treating Special OPD, OpenMRS “Consultation Fee” concepts, or Bahmni fee widgets as invoices

---

### Recommended implementation plan (not started)

1. Accounting: move Consultation Desk to an NGN pricelist; keep a single service product; retire TEST 75 USD for production. Format Clinical amounts from the invoice/sale currency.
2. Clinical: doctor-entered amount on the existing fee card; Confirm still creates the Odoo charge only.
3. API: accept and validate `amount`; set line `price_unit`; never write `list_price` from the doctor.
4. Keep `consultation:{visitUuid}` as the only create idempotency key.
5. Add an explicit unpaid correction that accounting-safely replaces the posted unpaid invoice.
6. After PAID: Clinical read-only; Accountant handles refunds.
7. Optionally store the consulting doctor on `sale.order.provider_name`.
8. Do not wait for Medical Officer / Consultant provider tags.

---

### Tests (this investigation)

- `npm test`: **98 passed**
- `npm run build`: `dist/assets/index-BUpBtg7b.js` (unchanged; no application code was modified)
- No application code, OpenMRS, or Odoo data changed.
- No patients, visits, prescriptions, invoices, payments, products, or charges were created.

### STOP (investigation)

The investigation above is retained. Implementation of doctor-entered NGN fees follows.

---

## Doctor-Entered Consultation Fee — Implementation

Date: **23 Aug 2026** (Africa/Lagos).

Existing Clinical → `abikan-api` → Odoo → Accountant path. No second ledger. Reception does not set the fee. Clinical has no Pay button. Company currency remains **USD**. Pharmacy, Registration, and Laboratory shops were not changed.

### UI change

The Consultation fee card now has a naira amount field before create:

- Label **Consultation fee**
- Prefix **₦**
- Helper: “Amount is in Nigerian naira (NGN).”
- **Create consultation fee** → confirm dialog shows the entered NGN amount
- After create: amount and PAID/UNPAID only. No edit. No Pay.

### API change

Same endpoint: `POST /openmrs/abikan-api/consultation/patient/{uuid}/charge`

Body: `{ visitUuid, requestId, amount }`

GET accepts optional `?visitUuid=` so the card reads the visit on the chart. If omitted, an open visit that already has a consultation charge is preferred.

### Validation

Authoritative on the server (`parse_consultation_amount`). Frontend `parseConsultationAmount` matches for staff feedback.

Rejected before create: empty, missing, 0, negative, text, `$75` / USD, malformed `5.00.1`. Optional leading `₦` or `NGN` is stripped and is not stored as part of the number.

### Odoo `price_unit`

New charges write `price_unit` = validated doctor amount, then write the line again after create so a pricelist does not replace it. Product `list_price` is **not** the billed amount.

Idempotency key remains `consultation:{visitUuid}`. A second POST (even with a different amount) returns `alreadyCreated` and does not add a line.

### NGN handling

Company currency was **not** changed (still USD). Consultation uses a dedicated **Hospital Consultation** NGN pricelist on shop **Consultation Desk**, the same shop-pricelist pattern as Registration / Pharmacy / Laboratory.

Display uses the invoice/sale currency, or NGN before a charge exists.

### Product used

The TEST product could not be reused as the hospital-facing product without renaming a row still attached to historical $75 invoices.

| Product | ID | List price | Use |
|---|---|---|---|
| Consultation Fee — TEST | **2390** | 75.00 | Historical TEST invoices only. Not written. |
| Consultation Fee | **2443** | 0.00 (catalogue placeholder) | New charges. Amount comes from the doctor. |

Pricelist **Hospital Consultation** (id **5**, NGN). Shop **Consultation Desk** now points at that pricelist. Historical sales keep Public Pricelist / USD.

### Accountant verification

Unchanged payment path. Invoice **INV/2026/00028** ₦5,000.00 NGN collected as **PCSH1/2026/00012** Cash. Clinical then showed **PAID**.

### RBAC verification

| Actor | Create consultation fee |
|---|---|
| `doctor.abikan` | 200 |
| `reception.abikan` | 403 |
| `nurse.abikan` | 403 |
| `pharmacy.abikan` | 403 |
| `lab.abikan` | 403 |
| `accountant.abikan` | 403 |
| Unauthenticated | 401 |
| `doctor.abikan` pay | 403 |

### Test records created

Isolated TEST patient **ABC200017** / Hospital EMRRecv Phase2225617. Existing open OPD visit `278d8165-b369-47da-b249-bfa930cdfbcf`. No new patient or visit.

| Record | ID / name | Amount |
|---|---|---|
| Sale | **S00029** | ₦5,000.00 NGN |
| Line key | `consultation:278d8165-b369-47da-b249-bfa930cdfbcf` | 5000.00 |
| Invoice | **INV/2026/00028** (id 42) | posted, then paid |
| Payment | **PCSH1/2026/00012** (id 15) | ₦5,000.00 |
| Product | **2443** Consultation Fee | list_price 0 |
| Pricelist | Hospital Consultation | NGN |

Duplicate POST with amount 9000 returned the same ₦5,000 invoice. Still one consultation line for that visit.

Historical TEST invoices **INV/2026/00004** and **INV/2026/00019** remain **USD 75.00**, product **2390**, unpaid/paid state unchanged.

ORD-7, ordinary hospital patients, laboratory tests, and unrelated pharmacy orders were not touched.

### Live UI

`doctor.abikan` on `#/doctor/patient/71f9788f-67f7-441c-b520-11979cbc37ec`: Consultation fee **₦5,000.00**, **PAID**, “Payment received”, no amount field, no Pay button, no $75.

### npm test / build

- `npm test`: **103 passed**
- `npm run build`: `dist/assets/index-CAyopUBh.js`

### Limitations

- No Clinical edit after create. Wrong unpaid amount needs a later accounting correction (credit note / cancel-and-recreate). Not built.
- After payment, Clinical cannot change the amount. Refunds stay on Accountant / Odoo.
- Medical Officer vs Consultant is still not configured. The logged-in doctor enters the fee.
- Company currency remains USD. Only the consultation shop/pricelist is NGN.
- Unpaid correction workflow is future work.

### STOP

This phase stops here. Do not add a Clinical Pay button, Reception pricing, a second ledger, or silent edits to paid invoices.

---

## Medical Officer vs Consultant — Provider Configuration

Date: **23 Aug 2026** (Africa/Lagos). **Investigation only.** Live OpenMRS/Bahmni was re-read. No providers, roles, attributes, specialties, services, visit types, patients, visits, invoices, payments, or consultation charges were created or changed. Consultation-fee billing and Accountant were not changed.

Related earlier write-up: `RECEPTION_CAPABILITY_AUDIT.md` § Medical Officer vs Consultant — Final Mapping (22 Aug 2026). That picture is still accurate.

---

### 1. How providers are currently represented

**EXISTS AND WORKS.**

An OpenMRS **provider** is a person, usually with a login **user**. Clinical save already loads that provider with `GET /openmrs/ws/rest/v1/provider?user={userUuid}` and writes `providers: [{ uuid }]` on the Consultation encounter.

This install still has **12** non-retired providers:

| Identifier | Username | Person name | Provider UUID | Hospital EMR Clinical? |
|---|---|---|---|---|
| `doctor.abikan` | `doctor.abikan` | Clinical Doctor | `17dec510-ef20-4282-9d9e-4d33d4693675` | Yes (`Abikan:Doctor`) |
| `abikan.doctor` | `abikan.doctor` | Hospital EMR Doctor | `0daee656-7b40-4b54-92dd-563b8f69cb66` | Yes (`Abikan:Doctor`) |
| `doctor` | `dr_neha` | Neha Anand | `05d6752c-5e08-11ef-8f7c-0242ac120002` | Bahmni demo (`Doctor` role) |
| `abikan.admin` | `abikan.admin` | Hospital EMR Development Admin | `42ac4f6a-d3f9-4e59-ad9a-2c947e95d31b` | SuperAdmin, not a hospital MO/Consultant |
| `admin.abikan` | `admin.abikan` | Hospital EMR Administrator | `f54a23aa-9884-40ce-b09c-00094d91a3a8` | Admin |
| `superman` | `superman` | Super Man | `d7a67c17-5e07-11ef-8f7c-0242ac120002` | Bahmni demo admin |
| `abikan.nurse` / `nurse.abikan` | matching users | Nurse / Nursing Staff | `63e93ad6-…` / `0496e78c-…` | Nursing, not Clinical |
| `registration` | `registration` | registration bahmni-user | `05c2bedc-…` | Reception/registration |
| `LABMANAGER` / `LABSYSTEM` | Lab Manager / Lab System | unnamed | `d4042a2f-…` / `da793d37-…` | Lab system |
| `UNKNOWN` | none | Unknown Provider | `f9badd80-…` | Placeholder |

`Abikan:Doctor` is a **login right** (Clinical workspace + `app:clinical`). It is not Medical Officer vs Consultant.

---

### 2. How Medical Officers can be represented

**EXISTS BUT NOT CONFIGURED.**

Use the existing OpenMRS **provider** for that person, then set existing attribute **`practitioner_type`** to **Medical Officer** once the hospital adds that option.

The visit for general outpatient care remains **OPD** (“Visit for Out patient”). Follow-up remains visit type **Follow Up**. Do not create a Medical Officer visit type.

The doctor who opens the chart is already the consulting provider. That is enough for the fee (already doctor-entered NGN). The attribute is a **label**, not a second identity system.

---

### 3. How Consultants can be represented

**EXISTS BUT NOT CONFIGURED.**

Use the same OpenMRS **provider**, with `practitioner_type` = **Consultant**.

When the hospital must name the clinic (Gynaecology, Cardiology, Neurosurgery), use existing Bahmni **appointment speciality** + **appointment service**, then attach that provider to the service/appointment. Do **not** use visit type **Special OPD**. That type is still “Visit for retrospective data entry” (`visitTypeForRetrospectiveEntries` in Bahmni Clinical). It was not renamed and must not be used as Consultant.

Provider-management **roles** (`providermanagement_provider_role`) exist as tables and are **empty**. REST `GET /openmrs/ws/rest/v1/providerRole` is still **404**. Do not depend on that module unless the hospital later enables it. `practitioner_type` is already on every provider and is the cleaner existing switch.

---

### 4. How specialties / services can be represented

**EXISTS AND WORKS** for the seed catalogue. **EXISTS BUT NOT CONFIGURED** for this hospital’s specialist clinics.

Bahmni Appointments has `enableSpecialities: true`. Live rows:

| Speciality | Services | Location |
|---|---|---|
| General Medicine | OPD Consultation, Follow-up Consultation, Procedure | none |
| ENT | OPD Consultation, Follow-up Consultation, Procedure | none |

Gynaecology, Cardiology, and Neurosurgery do **not** exist as specialities, services, locations, or visit types.

Nine existing appointments all use provider identifier **`doctor`** (Neha Anand) on General Medicine or ENT services. No Hospital EMR doctor is on an appointment.

Hospital path later, without a Hospital EMR table:

```
appointment_speciality  (e.g. Gynaecology)
  → appointment_service (e.g. Gynaecology OPD Consultation)
      → provider (the Consultant)
```

No specialties or services were created in this phase.

---

### 5. Whether existing Bahmni/OpenMRS configuration is sufficient

**Yes**, as a model. **No**, as live hospital data.

The objects already exist: provider, `practitioner_type`, appointment speciality/service, Consultation encounter provider, OPD / Follow Up visits. Hospital EMR does not need a doctor, consultant, or specialty table.

What is missing is **hospital configuration** of those objects, not a new Hospital EMR mechanism.

---

### 6. What is currently configured

| Item | Live state | Classification |
|---|---|---|
| Provider + person + user | 12 providers | **EXISTS AND WORKS** |
| Clinical save uses logged-in provider UUID | `fetchProviderUuidForUser` | **EXISTS AND WORKS** |
| Consultation fee by the conducting doctor | Doctor-entered NGN | **EXISTS AND WORKS** |
| User role `Abikan:Doctor` | Login to Clinical | **EXISTS AND WORKS** |
| `practitioner_type` options | `handler_config` = `,Doctor` only | **EXISTS BUT NOT CONFIGURED** |
| `practitioner_type` values | Only Neha Anand = `Doctor` | **EXISTS BUT NOT CONFIGURED** |
| Login Locations attribute | Unused on every provider | **EXISTS BUT NOT CONFIGURED** |
| Available for appointments | Only Neha Anand = true | **EXISTS BUT NOT CONFIGURED** |
| Provider-management roles | 0 rows; REST 404 | **EXISTS BUT NOT CONFIGURED** |
| Appointment specialities | General Medicine, ENT | **EXISTS BUT NOT CONFIGURED** for this hospital |
| Gynaecology / Cardiology / Neurosurgery | Absent | **MISSING** |
| Provider bound to a specialty clinic location | Locations are OPD/Emergency/wards, not clinics | **MISSING** |
| Special OPD as Consultant | It is retrospective entry | Do not use |
| MO vs Consultant on Hospital EMR doctors | No evidence | **MISSING** |
| Appointment / provider picker in Reception | Bahmni Appointments exists; Hospital EMR Reception does not show it | **EXISTS BUT NOT EXPOSED IN ABIKAN** |

---

### 7. What is missing

- `practitioner_type` values **Medical Officer** and **Consultant**
- Any Hospital EMR doctor tagged as either
- Hospital specialties beyond General Medicine and ENT
- Evidence that a given TEST account is a Medical Officer or a Consultant — do not assume `doctor.abikan` is a Medical Officer
- A production decision on whether Reception must route to a named Consultant

---

### 8. What the hospital needs to configure before production

1. Add **Medical Officer** and **Consultant** to `practitioner_type` options (keep or retire the seed `Doctor` value as they wish).
2. Create OpenMRS users/providers for real Medical Officers and Consultants (or reuse existing people). Do not invent a Hospital EMR roster.
3. Set each consulting doctor’s `practitioner_type`.
4. If clinics must be named: add appointment specialities/services (Gynaecology, Cardiology, Neurosurgery, …) and attach the Consultant providers.
5. Decide whether Reception only starts **OPD / Follow-up / Emergency / Admission**, or later also picks an appointment service / named provider.
6. Decide production consultation amounts. The fee mechanism already accepts the doctor’s NGN amount and does not need MO vs Consultant labels.

No provider record was written in this phase. There is not enough evidence to classify anyone permanently.

---

### 9. Whether Reception needs to select a provider/service

**Not now.** **REQUIRES HOSPITAL DECISION** later.

Current architecture is enough:

```
Reception starts the visit (General Outpatient / Follow-up / Emergency / Admission)
  → patient reaches Clinical
  → logged-in provider conducts the consultation
  → that provider enters the consultation fee
  → Accountant collects
```

Reception must not maintain a doctor/specialty database. A Reception “Medical Officer / Consultant” or clinic picker is only justified after those providers and services exist, and only if the hospital requires desk routing. That is a future UX decision, not a blocker for fees or Clinical save.

---

### 10. Whether Clinical needs any UI change

**Not in this phase.**

Clinical already identifies the consulting doctor as the logged-in user’s provider. That identity can later show Medical Officer / Consultant or a specialty **if** `practitioner_type` and appointment metadata are populated. Do not change the Consultation encounter payload or the fee API for this mapping.

Optional later (not built): read-only line on the chart such as the provider’s configured type. Not required for billing.

---

### 11. What should NOT be built

- Hospital EMR Doctor / Consultant / Specialty tables
- Visit types named Medical Officer, Consultant, Gynaecology, or similar
- A new meaning for **Special OPD**
- A second provider identity or fee ledger
- Reception as the hospital’s doctor directory
- Classifying TEST accounts as Medical Officer or Consultant without hospital evidence
- Changes to Odoo billing or Accountant for this mapping

---

### Recommended mapping (summary)

| Hospital idea | Existing object | Classification |
|---|---|---|
| Medical Officer | Provider + `practitioner_type` = Medical Officer; visit **OPD** | **EXISTS BUT NOT CONFIGURED** |
| Consultant | Provider + `practitioner_type` = Consultant; clinic via **appointment speciality/service** | **EXISTS BUT NOT CONFIGURED** |
| General consultation | Visit type **OPD** | **EXISTS AND WORKS** |
| Specialist clinic name | `appointment_speciality` / `appointment_service` | **EXISTS BUT NOT CONFIGURED** for this hospital |
| Who billed | Logged-in Clinical provider; doctor-entered NGN fee | **EXISTS AND WORKS** |
| Special OPD | Retrospective data entry | Do not use |

### Tests (this investigation)

- `npm test`: **103 passed**
- `npm run build`: `dist/assets/index-CAyopUBh.js` (unchanged; no application code was modified)
- No application code or OpenMRS/Odoo data was changed.

### STOP

This investigation stops here. Do not add a Reception Medical Officer / Consultant picker, do not retarget Special OPD, do not create providers or specialties, and do not change consultation-fee billing.
