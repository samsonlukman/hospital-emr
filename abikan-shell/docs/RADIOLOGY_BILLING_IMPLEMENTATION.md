# Radiology billing — implementation

Date: **17 Aug 2026** (UTC). Controlled isolated TEST only.

Related: `RADIOLOGY_WORKFLOW.md`, `LABORATORY_BILLING_IMPLEMENTATION.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `REGISTRATION_BILLING_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`.

This phase implements **billing only**:

```
Doctor (existing OpenMRS Radiology Order)
  → Radiology fee (Odoo sale order + posted invoice)
  → Patient Account UNPAID
  → Accountant payment (existing path)
  → Odoo invoice PAID
  → Radiology sees PAID
```

Odoo remains the financial source of truth. OpenMRS remains the clinical order source. dcm4chee remains the imaging archive. There is no Hospital EMR ledger and no second radiology database.

**PAID ≠ scan performed ≠ image acquired ≠ report available.**

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **WRITE** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION** · **NOT PRESENT** · **NOT TESTED**

---

## 1. Existing Radiology workflow

**CONFIRMED** · clinical path unchanged

```
Doctor consultation
  POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter  orders[]
        ↓
  OpenMRS Radiology Order
  Atomfeed encounter feed (pacs-integration consumes)
  Intended: HL7 ORM → dcm4chee modality worklist
        ↓
  Imaging at the modality (dcm4chee / PACS)
        ↓
  Viewer: Oviyam2  /oviyam2/oviyam?patientID={MRN}&accessionNumber={orderNumber}
        ↓
  Radiology Notes / RADIOLOGY document encounter (when recorded)
  Hospital EMR Radiology workplace (OpenMRS reads)
```

Hospital EMR routes `#/radiology`, `#/radiology/patient/{uuid}`, `#/radiology/order/{uuid}` kept. Doctor ordering from Hospital EMR remains **Coming Soon**. PACS/DICOM was not replaced or modified. No scan was performed for this TEST.

This TEST used the existing encounter write only to create one isolated Radiology Order. Payment did **not** trigger a scan, a worklist item, or a DICOM study.

---

## 2. OpenMRS order model

**CONFIRMED**

| Item | Value |
|---|---|
| Write | `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `orders[]` |
| Order type | **Radiology Order** `d3561dc0-5e07-11ef-8f7c-0242ac120002` |
| Read list | `GET /openmrs/ws/rest/v1/bahmnicore/orders?patientUuid=&orderTypeUuid=` |
| Read one | `GET /openmrs/ws/rest/v1/order/{uuid}` and `GET /openmrs/ws/rest/v1/bahmnicore/orders?orderUuid=` |
| Encounter type used for this TEST | **Consultation** `d34fe3ab-5e07-11ef-8f7c-0242ac120002` |
| Encounter type RADIOLOGY | `d3a89c59-5e07-11ef-8f7c-0242ac120002` — **not** used (reports / upload later) |
| Radiology Notes concept | `ae6e5490-ade9-486e-8268-9e4efd45b07e` — **0** obs after this TEST |

Hospital EMR did **not** invent a new ordering API. The TEST order used the existing encounter transaction.

This TEST: one Consultation encounter, one Radiology Order.

| Field | TEST value |
|---|---|
| Order uuid | `46e6031f-1fa9-4c48-a510-d32666cbc2ce` |
| Order number | **ORD-6** |
| Concept | **Chest x-ray, single view** `165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` (class Radiology/Imaging Procedure) |
| Encounter | `838290e9-0fd7-458f-9cb7-2b88bd614c4a` Consultation |
| Visit | `020a5cfe-7cd0-4959-8175-e0ee12b3b78b` OPD @ OPD-1 |
| Patient | Ngozi Eze `6b4fcdfe-b8fb-4be4-917a-e04ec032e9c9` ABC200007 |

Clinical order status on the existing order screen remains **Ordered**. That status is independent of payment.

---

## 3. PACS / DICOM architecture

**CONFIRMED** · **READ-ONLY** this phase

| Piece | This deployment |
|---|---|
| dcm4chee | `bahmni-standard-dcm4chee-1`, dcm4chee-2.18.1-psql. AE **DCM4CHEE** |
| Viewer | **Oviyam2**. OHIF is **NOT PRESENT** |
| pacs-integration | consumes OpenMRS encounter Atomfeed; intended HL7 ORM → MWL |
| pacsquery | `GET /openmrs/ws/rest/v1/pacs/studies?patientId=` → HTTP **501** `PACS Server configuration is not defined` |
| `pacsquery.pacsConfig` | **NULL** |
| Modalities | **0** |
| MWL items | **0** before and after this TEST |
| Patients / studies / series / instances | **0** before and after this TEST |
| pacs-integration `test_order` / `order_details` / `failed_events` | **0** before and after this TEST |

Creating ORD-6 did **not** create a DICOM study, MWL row, or pacs-integration `test_order`. Payment also did not. Empty `modality` remains a configuration gap (**CONFIRMED**). Exact reason the encounter feed did not write `test_order` for this order: **UNKNOWN** (no modalities; `order_type` table in pacs-integration is also empty).

Do not query PACS databases from the browser. Do not make payment create a DICOM study. Open Images stays disabled unless MRN + order number exist for Oviyam; this TEST did not open images.

---

## 4. Odoo Radiology catalogue

**CONFIRMED** · **READ-ONLY** except the isolated TEST product

| Item | Value |
|---|---|
| Category | **All / Services / Radiology** id **10** |
| Catalogue products in that category | **257**, all `list_price` **1.00**, type **service**, `invoice_policy` **order**, Tax **15%** |
| UUID mapping | `product.uuid` = OpenMRS concept uuid |
| Example (unmodified) | **Chest x-ray, single view** id **845**, uuid `165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`, $1.00, Tax 15% |
| `order.type` in Odoo | **Drug Order** only — Radiology Order is **not** on Atomfeed |

**Do not** enable Radiology Order on Atomfeed until approved prices exist. It would invoice **$1.00 + Tax 15%**.

Existing catalogue prices are placeholders. They must **not** be billed to patients.

Shop **Radiology Desk** did not exist before this phase. It was created for the TEST (id **5**), copied from Consultation Desk warehouse/pricelist. Existing shops were not modified.

---

## 5. Product mapping

**IMPLEMENTED**

Preferred:

```
OpenMRS Radiology Order UUID
  → Hospital EMR backend
  → sale.order.line.external_order_id = radiology:{orderUuid}
```

Product resolution:

1. Isolated TEST product: `default_code` = concept uuid **and** name contains ` — TEST`
2. Else catalogue `product.uuid` = concept uuid, **refused** if `list_price ≤ 1.01`

This TEST: concept `165152…` → product **2392** **Chest x-ray, single view — TEST** (`default_code` = that uuid). Catalogue **845** still owns `product.uuid` and was **not** modified.

Financial key is the order uuid, not patient name or room/location.

---

## 6. Price safety

**IMPLEMENTED**

Placeholder catalogue prices (`$1.00`) are refused with:

> Radiology price has not been configured.

No silent billing. No assumed tariff. TEST product **2392** has an explicit **$60.00** list price, no tax, no stock.

Production radiology tax and real tariffs: **REQUIRES ACCOUNTING CONFIGURATION**.

---

## 7. Charge creation

**IMPLEMENTED** · **WRITE**

```
POST /openmrs/abikan-api/radiology/patient/{patientUuid}/charge
{ "orderUuid": "...", "requestId": "..." }
```

Backend:

1. Authenticate OpenMRS session
2. Require Radiology privilege (`app:radiology-upload` or SuperAdmin)
3. Verify the order belongs to the patient and is a Radiology Order
4. Resolve the approved product (TEST override or non-placeholder catalogue price)
5. Verify Odoo partner mapping
6. Return existing charge if `radiology:{orderUuid}` already exists
7. Create `sale.order` through ORM on shop **Radiology Desk**
8. Confirm with `action_confirm` (same path as Registration / Consultation / Laboratory)
9. Let Odoo post the invoice
10. Return payment status from Odoo `payment_state` / `amount_residual`

Browser payload contains only identifiers. Odoo credentials stay in `abikan-api`.

TEST: **S00007**, shop Radiology Desk, line `radiology:46e6031f-…`, product 2392, tax **0**, total **60.00**. Created by `abikan.admin`.

---

## 8. Invoice creation

**CONFIRMED**

Odoo automated invoicing after confirm. No SQL. No manual `account.move` insert.

**INV/2026/00006** id **11**, origin S00007, tax **0**, residual 60.00 then **0**, `payment_state` **paid**. No stock picking.

Currency from Odoo: **USD** (`$60.00`). Company currency was not changed. NGN is a later Operations task.

---

## 9. Accountant payment

**UNCHANGED** path · **WRITE** one Cash receipt for this TEST

Existing `POST /openmrs/abikan-api/accountant/payment` with `account.payment.register`. Radiology UI has **no Pay button**.

| Check | Result |
|---|---|
| `registration` cannot pay | **403** |
| Cash journal | id **6** |
| Payment | **PCSH1/2026/00006** $60.00 |
| Second pay | **409** `invoice_already_paid` |

Radiology reads `payment_state` and `amount_residual`. Staff labels: **UNPAID** / **PARTIALLY PAID** / **PAID**. No `radiology.isPaid` ledger.

Partial payment UI is implemented; a live partial payment was **NOT TESTED**.

---

## 10. Patient Account integration

**IMPLEMENTED**

Shop name **Radiology Desk** and category **Radiology** → department **Radiology**.

Ngozi Patient Account after charge: Radiology **UNPAID**, $60.00 outstanding. After payment: Radiology **PAID**, $0.00 outstanding, payment history **PCSH1/2026/00006** Cash.

No second account screen. Description may include the TEST internal reference (`default_code`) because Odoo displays it on the product name — same limitation as Laboratory.

---

## 11. Permissions

**IMPLEMENTED**

| Actor | Radiology charge | Payment |
|---|---|---|
| `app:radiology-upload` / SuperAdmin | yes | no (unless also Accountant) |
| `app:registration` only | **403** | **403** |
| Unauthenticated | **401** | **401** |

Radiology staff must not collect payment, choose a journal, change price/tax, refund, or see Odoo credentials. No new OpenMRS role was created.

This TEST used `abikan.admin` for charge and payment. Dedicated radiology-only user **NOT TESTED**.

---

## 12. Duplicate protection

**IMPLEMENTED**

- Stable key `radiology:{orderUuid}`
- Odoo `sale.order.line` lookup before create
- Server lock on that key and `requestId`
- Duplicate POST returned `alreadyCreated: true`, still **S00007** / **INV/2026/00006** only

Pharmacy queue skips `radiology:` prefixes so this fee cannot appear as a prescription.

---

## 13. Test results

**CONFIRMED** isolated. Not John / Tunde / Adaeze / Aisha / Blessing / Chinedu / Fatima.

| Field | Before | After |
|---|---|---|
| Name | **Ngozi Eze** | same |
| MRN | `ABC200007` | same |
| OpenMRS uuid | `6b4fcdfe-b8fb-4be4-917a-e04ec032e9c9` | same |
| Partner | id **12**, no sale orders | S00007 / INV/2026/00006 / PCSH1/2026/00006 |
| Prior visit | closed OPD 13 Aug, unused | new OPD `020a5cfe-…` @ OPD-1 |
| Radiology orders | none | ORD-6 Chest x-ray, single view |
| Drug / lab orders | none | none |
| PACS studies | 0 | **0** |
| Radiology Notes | 0 | **0** |

| Step | Result | Label |
|---|---|---|
| Investigate mapping | product.uuid = concept uuid; all catalogue prices 1.00; no Radiology Order Atomfeed type | **CONFIRMED** |
| Isolated patient | Ngozi, no prior bills | **CONFIRMED** |
| One Radiology Order | ORD-6 Chest x-ray, single view | **CONFIRMED** |
| One charge | S00007 + INV/2026/00006 UNPAID tax 0 | **CONFIRMED** |
| Duplicate POST | reused S00007 | **CONFIRMED** |
| Patient Account | Radiology UNPAID then PAID | **CONFIRMED** |
| Accountant pay | PCSH1/2026/00006 Cash $60 | **CONFIRMED** |
| Radiology sees PAID | yes | **CONFIRMED** |
| Unauthenticated | 401 | **CONFIRMED** |
| Registration cannot charge or pay | 403 | **CONFIRMED** |
| Invalid patient / order | 404 | **CONFIRMED** |
| Second payment | 409 | **CONFIRMED** |
| Pharmacy / Registration / Consultation / Laboratory | unchanged | **CONFIRMED** |
| No scan / DICOM / report | PACS still empty; 0 Radiology Notes | **CONFIRMED** |
| `npm run build` | passed | **CONFIRMED** |
| Partial payment | code present | **NOT TESTED** |
| Odoo down | not executed | **NOT TESTED** |
| Visual UI click-through | POST the button calls was executed | **NOT TESTED** |

---

## 14. Known limitations

**CONFIRMED**

- Catalogue radiology prices remain 1.00 placeholders; production examinations without a TEST override or a real price cannot be billed (`missing_price`)
- SuperAdmin created the charge and paid
- Patient Account line may show the TEST internal code
- pacsquery is still unconfigured (HTTP 501)
- No hospital-wide imaging work queue (unchanged)
- Partial payment status is coded, not live-tested
- Visual click-through **NOT TESTED**

**COMING SOON** (out of this phase): Doctor radiology ordering UI, PACS configuration, MWL, scan acquisition, report entry, NGN conversion, Nigerian payment gateway, refunds, inpatient/ward.

---

## 15. Hospital decisions required

**REQUIRES HOSPITAL DECISION**

1. Must payment be received before the scan is performed?
2. Approved patient tariff for each radiology examination (not $1.00)
3. Whether unpaid orders should later be blocked in Radiology (they are **not** blocked now)
4. Dedicated radiology vs cashier OpenMRS users

**REQUIRES ACCOUNTING CONFIGURATION**

- Tax-exempt production radiology services without deleting Tax 15% (TEST product has no tax; production policy is not decided here)
- Real `list_price` on catalogue products **or** keep Hospital EMR TEST overrides until then

Do **not** add `order.type` Radiology Order to Atomfeed until prices and tax are approved — it would invoice $1.00 + 15% automatically.

---

## 16. Recommended next step

**REQUIRES ACCOUNTING CONFIGURATION** first: approve real radiology prices and tax policy.

Do **not** start inpatient / ward / room / bed from this phase.

Do **not** configure PACS or enter reports as a side effect of billing.

Later clinical work (separate phase): PACS connectivity, whether payment should gate imaging, Doctor ordering UI.

---

## UX

**IMPLEMENTED**

- Radiology workplace not redesigned
- Compact **Radiology examination** card: procedure name, price, UNPAID / PARTIALLY PAID / PAID, outstanding, proceed to cashier
- **Create radiology fee** / confirm: Radiology does not collect money
- Open Images / Write report remain as they were (Coming Soon unless Oviyam identifiers exist)
- Doctor ordering remains **Coming Soon**; no billing clutter added to Doctor
- Staff do not see sale orders, journals, or database ids on the fee card
- Paid copy states that payment does not mean the scan has been done

Supported staff payment states: **UNPAID**, **PARTIALLY PAID**, **PAID**. Clinical states beyond existing **Ordered** / empty study / empty report were **not** invented.

---

## Tax and currency

**CONFIRMED**

| Environment | Behavior |
|---|---|
| CURRENT TEST | Product 2392 tax-empty. INV/2026/00006 tax **0**. Catalogue 845 still has Tax 15%. Tax 15% master unchanged | **CONFIRMED** |
| REQUIRED PRODUCTION | Patient radiology services tax policy | **REQUIRES ACCOUNTING CONFIGURATION** |

USD from Odoo (`$60.00`). No hardcoded NGN/USD. NGN is a later Operations task.

---

## Security

**IMPLEMENTED**

Odoo credentials stay in `abikan-api`. Session required. Order must belong to the patient and be a Radiology Order. Price from Odoo. Placeholder prices refused.

---

## Protected records

**CONFIRMED** unchanged

ORD-1–5, S00001–S00006, INV/2026/00001–00005, PCSH1/2026/00001–00005, P00001, WH/IN/00001, WH/OUT/00001–00002, product **2385** quants unchanged, Registration **2389**, Consultation **2390**, Laboratory TEST **2391**, catalogue **845** and **1820**, Tax 15%, USD.

Pharmacy queue still Adaeze ORD-3 DISPENSED, Aisha ORD-4 DISPENSED, Tunde ORD-2 UNPAID. Blessing registration **PAID**. Chinedu consultation **PAID**. Fatima laboratory **PAID**. No OpenMRS Dispensed write. No DICOM write.

New TEST objects only: ORD-6, S00007, INV/2026/00006, PCSH1/2026/00006, product **2392**, shop **Radiology Desk** id **5**. Category **10** reused, not rebuilt.

---

## API

| Method | Path | Privilege |
|---|---|---|
| GET | `/openmrs/abikan-api/radiology/patient/{uuid}` | `app:radiology-upload` or SuperAdmin |
| POST | `/openmrs/abikan-api/radiology/patient/{uuid}/charge` `{ requestId, orderUuid? }` | same |

---

## Future Nigerian gateway

**COMING SOON** · **REQUIRES HOSPITAL DECISION**

```
Radiology charge
  → Accountant / Cashier
  → Nigerian provider
  → secure backend
  → same account.payment.register
  → invoice PAID
  → Radiology reads payment_state
```

Do not bypass Odoo.

---

## Stop

This phase stops at **Radiology sees PAID**.

Do **not** perform the scan. Do **not** modify PACS. Do **not** create a DICOM study. Do **not** write a report. Do **not** start inpatient / ward / room / bed. Do **not** change Pharmacy, Registration, Consultation, Laboratory, or Accountant payment.

---

*End of implementation.*
