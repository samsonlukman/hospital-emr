# Laboratory billing — implementation

Date: **17 Aug 2026** (UTC). Controlled isolated TEST only.

Related: `LABORATORY_WORKFLOW.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `REGISTRATION_BILLING_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`.

This phase implements **billing only**:

```
Doctor (existing OpenMRS Lab Order)
  → Laboratory fee (Odoo sale order + posted invoice)
  → Patient Account UNPAID
  → Accountant payment (existing path)
  → Odoo invoice PAID
  → Laboratory sees PAID
```

Odoo remains the financial source of truth. OpenMRS remains the clinical order source. OpenELIS remains the laboratory processing engine. There is no Hospital EMR ledger and no second lab database.

**PAID ≠ sample collected ≠ processing ≠ result ready ≠ verified.**

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **WRITE** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION** · **NOT PRESENT** · **NOT TESTED**

---

## 1. Existing laboratory architecture

**CONFIRMED** · unchanged

```
Doctor consultation
  POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter  orders[]
        ↓
  OpenMRS Lab Order
  Atomfeed encounter feed
        ↓
  OpenELIS sample / analysis
        ↓
  Results (OpenELIS) → accession feed → OpenMRS LAB_RESULT
        ↓
  GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults
  Hospital EMR Laboratory workplace
```

Hospital EMR routes `#/laboratory`, `#/laboratory/patient/{uuid}`, `#/laboratory/order/{uuid}` kept. Doctor ordering from Hospital EMR remains **Coming Soon**. OpenELIS was not replaced. Lab Lite is still not running.

---

## 2. Existing lab order mechanism

**CONFIRMED**

| Item | Value |
|---|---|
| Write | `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `orders[]` |
| Order type | **Lab Order** `d3560b17-5e07-11ef-8f7c-0242ac120002` |
| Read | `GET /openmrs/ws/rest/v1/bahmnicore/orders?patientUuid=&orderTypeUuid=` |
| Order by uuid | `GET /openmrs/ws/rest/v1/order/{uuid}` |
| Results | `GET /openmrs/ws/rest/v1/bahmnicore/labOrderResults?patientUuid=` |

Hospital EMR did **not** invent a new ordering API. The TEST order used the existing encounter transaction.

---

## 3. OpenMRS lab order model

**CONFIRMED**

Each `orders[]` item becomes one OpenMRS order row (one test or one panel concept). One encounter can hold several lab orders. A panel is a **LabSet** concept, still one order.

This TEST: one Consultation encounter, one Lab Order.

| Field | TEST value |
|---|---|
| Order uuid | `887d629b-c085-4340-89a7-b58ad02254bc` |
| Order number | **ORD-5** |
| Concept | **Malarial smear** `32AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` (class Test) |
| Encounter | `826762fe-2be1-4a4b-8edf-b7b68e1f12b4` Consultation |
| Visit | `9446e9e1-abc8-4c4e-aa10-f7b77e011859` OPD @ OPD-1 |
| Patient | Fatima Abdullahi `a9d97d4c-3ddf-4d28-8cfb-3008ffdfdd78` |
| Accession on order | empty at order time |
| Fulfiller status | null |
| Action | NEW |

---

## 4. OpenELIS relationship

**CONFIRMED** · **READ-ONLY** from Hospital EMR

The existing Atomfeed pipeline **naturally** created OpenELIS rows for this new Lab Order:

| Table | Count after TEST |
|---|---|
| `sample` | 1 |
| `analysis` | 1 |
| `result` | **0** |

Hospital EMR did not insert those rows, did not enter results, and did not change OpenELIS configuration or users.

OpenMRS `labOrderResults` for Fatima shows the ordered test with **no result value**. That is not “result available”.

---

## 5. Odoo service products

**CONFIRMED** catalogue · **not used for this invoice**

| Fact | Value |
|---|---|
| Lab / Test products | 622 |
| Lab / Panel products | 84 |
| Type | service |
| Price | **all** `list_price=1.00` |
| Tax | Tax 15% on catalogue rows |
| Invoice policy | order |
| UoM | Units |
| Mapping field | `product.product.uuid` = OpenMRS concept uuid |

Example catalogue row **not modified**: product **1820** Malarial smear, uuid `32AAAAAAAAAAAAAAAA…`, price 1.00, tax 15%.

`order.type` remains **Drug Order** only. No Laboratory shop map was added to Atomfeed. Enabling `order.type` = Lab Order would bill catalogue tests at $1.00 + tax as Pharmacy-style feed invoices. That was **not** done.

---

## 6. Test → product mapping

**IMPLEMENTED**

Production (when Operations sets a real price):

```
OpenMRS order.concept.uuid  →  product.product.uuid
```

This TEST (isolated; catalogue price 1.00 is refused):

```
OpenMRS order.concept.uuid
  → product.product.default_code = concept uuid
     AND name contains " — TEST"
```

If neither a TEST override nor a non-placeholder priced product exists → `409 missing_mapping` / `missing_price`. No guessed invoice.

Name is not the mapping key. Patient name is never used.

---

## 7. Charge creation mechanism

**IMPLEMENTED** · **WRITE** via Odoo ORM

Same departmental pattern as Registration / Consultation. **Not** Drug Order. **Not** Atomfeed.

```
OpenMRS Lab Order
  → sale.order (shop = Laboratory)
       line.external_order_id = lab:{orderUuid}
       line.external_id = orderUuid
       product from mapping above
  → action_confirm
  → posted out_invoice
  → existing Accountant account.payment.register
```

Privilege: `app:lab-lite` or SuperAdmin. Browser sends patient uuid, optional order uuid, `requestId`.

Multiple unbilled tests on one **Create laboratory fee** POST share **one** sale order / invoice. A later new order gets a new charge. This TEST had exactly one order.

---

## 8. Odoo model

**IMPLEMENTED**

| Object | Value | Label |
|---|---|---|
| Category | **All / Services / Laboratory** id **40** | **WRITE** (new) |
| Shop | **Laboratory** id **4**, no stock location | **WRITE** (new) |
| Product | **Malarial smear — TEST** id **2391**, service, 40.00, no tax, `default_code` = concept uuid | **WRITE** (new) |
| Sale order | **S00006** | **WRITE** |
| Invoice | **INV/2026/00005** | **WRITE** (via confirm) |
| Payment | **PCSH1/2026/00005** | existing Accountant wizard |

Catalogue product 1820, Tax 15%, and company currency were **not** modified.

---

## 9. Patient linkage

**IMPLEMENTED**

OpenMRS uuid → `res.partner.uuid`; MRN → `res.partner.ref`.

Test: **Fatima Abdullahi** `ABC200005`, partner id **10**. No duplicate partner.

---

## 10. Lab order linkage

**IMPLEMENTED**

`external_order_id = lab:{orderUuid}`

TEST: `lab:887d629b-c085-4340-89a7-b58ad02254bc`

---

## 11. Visit / encounter linkage

**IMPLEMENTED** · recorded, not the idempotency key

Sale `origin` = visit uuid. Payload also returns encounter uuid. New visit + new order → new charge. Same order cannot create a second invoice.

---

## 12. Invoice linkage

**CONFIRMED**

**INV/2026/00005** id **9**, origin S00006, tax **0**, residual 40.00 then **0**, `payment_state` **paid**. No stock picking.

---

## 13. Department mapping

**IMPLEMENTED**

Shop name **Laboratory** and category **Laboratory** → Patient Account department **Laboratory**.

Existing catalogue path `All / Services / Lab / Test` also maps to **Laboratory** if those products are invoiced later. Registration, Consultation, and Pharmacy remain distinct.

---

## 14. Accountant integration

**UNCHANGED**

Existing `POST /openmrs/abikan-api/accountant/payment`. Laboratory UI has no Pay button. `registration` cannot pay (403). Second pay → **409 invoice_already_paid**.

---

## 15. Payment verification

**IMPLEMENTED**

`payment_state` in `{paid, in_payment}` **and** residual ≤ 0.009 → **PAID**. Otherwise **UNPAID** (including partial). No `labOrder.isPaid` in Hospital EMR.

---

## 16. Duplicate protection

**IMPLEMENTED**

Odoo line lookup `lab:{orderUuid}` + server lock on that key and `requestId`. Duplicate POST returned `alreadyCreated: true`, still **S00006** only.

---

## 17. Permissions

**IMPLEMENTED**

| Actor | Lab charge | Payment |
|---|---|---|
| `app:lab-lite` / SuperAdmin | yes | no (unless also Accountant) |
| `app:registration` only | 403 | 403 |
| Unauthenticated | 401 | 401 |

This TEST used `abikan.admin` for charge and payment. Dedicated lab-only user **NOT TESTED**.

---

## 18. Security

**IMPLEMENTED**

Odoo credentials stay in `abikan-api`. Session required. Order must belong to the patient. Price from Odoo. No guessed mapping.

---

## 19. Tax behavior

**CONFIRMED**

| Environment | Behavior |
|---|---|
| CURRENT TEST | Product 2391 tax-empty. INV/2026/00005 tax **0**. Catalogue 1820 still has Tax 15%. Tax 15% master unchanged | **CONFIRMED** |
| REQUIRED PRODUCTION | Patient lab services tax-exempt without deleting Tax 15% | **REQUIRES ACCOUNTING CONFIGURATION** |

---

## 20. Currency behavior

**CONFIRMED** · **READ-ONLY**

USD from Odoo (`$40.00`). No hardcoded NGN/USD. NGN is a later Operations task.

---

## 21. UX decisions

**IMPLEMENTED**

- Laboratory workplace not redesigned
- Compact **Laboratory tests** card: test name, amount, PAID / UNPAID
- Unpaid: **Payment required** / Please proceed to the cashier
- **Create laboratory fee** / confirm: Laboratory does not collect money
- Collect sample / Enter result remain **Coming Soon** (not fake states)
- Doctor ordering remains **Coming Soon**; no billing clutter added to Doctor
- Staff do not see sale orders, Atomfeed, or OpenELIS identifiers on the fee card

Visual click-through **NOT TESTED**. The POST the button calls was executed.

Supported staff states in this phase: **UNPAID**, **PAID**, plus existing order/result empty states. Sample collected / processing / verified are **not** invented.

---

## 22. Sample collection relationship

**CONFIRMED**

Payment does not collect a sample. Collect sample stays Coming Soon. OpenELIS may already have a sample from the order feed; Hospital EMR does not treat that as a staff “SAMPLE COLLECTED” state in this phase.

**REQUIRES HOSPITAL DECISION:** whether unpaid should later block collection. Not blocked now.

---

## 23. Test patient

**CONFIRMED** isolated. Not John / Tunde / Adaeze / Aisha / Blessing / Chinedu.

| Field | Before | After |
|---|---|---|
| Name | **Fatima Abdullahi** | same |
| MRN | `ABC200005` | same |
| OpenMRS uuid | `a9d97d4c-3ddf-4d28-8cfb-3008ffdfdd78` | same |
| Partner | id **10**, no sale orders | S00006 / INV/2026/00005 / PCSH1/2026/00005 |
| Prior visit | closed OPD 13 Aug, no encounters | unused |
| Lab orders | none | ORD-5 Malarial smear |
| Drug orders | none | none |

---

## 24. Test order

**CONFIRMED** · **WRITE** via existing Bahmni encounter API

ORD-5, Lab Order, Malarial smear, encounter `826762fe-…`, visit `9446e9e1-…`.

---

## 25. Test charge

**CONFIRMED** · **WRITE**

**S00006**, shop Laboratory, line `lab:887d629b-…`, product 2391, tax 0, total 40.00. Created by `abikan.admin`.

---

## 26. Test invoice

**CONFIRMED**

**INV/2026/00005**, posted, then paid, tax 0.

---

## 27. Test payment

**CONFIRMED**

**PCSH1/2026/00005**, Cash, 40.00 USD.

---

## 28. Laboratory PAID result

**CONFIRMED**

Laboratory GET: **PAID**. Patient Account: Laboratory **PAID**, outstanding `$0.00`.

---

## 29. OpenELIS impact

**CONFIRMED** natural feed only

1 sample, 1 analysis, **0 results**. No result entry. No OpenELIS config change.

---

## 30. Protected records

**CONFIRMED** unchanged

ORD-1–4, S00001–S00005, INV/2026/00001–00004, PCSH1/2026/00001–00004, P00001, WH/IN/00001, WH/OUT/00001–00002, product **2385** stock **88**, Registration **2389**, Consultation **2390**, catalogue **1820**, Tax 15%, USD.

Pharmacy queue still Adaeze / Aisha / Tunde. Blessing registration **PAID**. Chinedu consultation **PAID**. No OpenMRS Dispensed write.

New TEST objects only: ORD-5, S00006, INV/2026/00005, PCSH1/2026/00005, product **2391**, shop **Laboratory**, category **40**.

---

## 31. Known limitations

**CONFIRMED**

- Catalogue lab prices remain 1.00 placeholders; production tests without a TEST override or a real price cannot be billed (`missing_price`)
- SuperAdmin created the charge and paid
- Odoo-down **NOT TESTED**
- Visual UI click-through **NOT TESTED**
- Hospital-wide lab work queue still absent (unchanged)
- Patient Account description may include the TEST internal reference (`default_code`) because Odoo displays it on the product name

**COMING SOON** (out of this phase): Radiology billing, gateway, refunds, sample collection, result entry, verification, NGN, Doctor lab ordering UI.

---

## 32. Hospital decisions

**REQUIRES HOSPITAL DECISION**

1. Must payment be received before sample collection?
2. Production prices for each test/panel (replace 1.00 placeholders and TEST 40.00).
3. One invoice per order vs grouping several tests from the same visit (this build groups unbilled tests on one Create fee click).
4. Different prices by location / urgency (STAT).

**REQUIRES ACCOUNTING CONFIGURATION**

- Tax-exempt production lab products without deleting Tax 15%
- Real `list_price` on catalogue products **or** keep Hospital EMR TEST overrides until then
- Dedicated lab vs cashier OpenMRS users

Do **not** add `order.type` Lab Order to Atomfeed until prices and tax are approved — it would invoice $1.00 + 15% automatically.

---

## 33. Future Nigerian gateway

**COMING SOON** · **REQUIRES HOSPITAL DECISION**

```
Laboratory charge
  → Accountant / Cashier
  → Nigerian provider
  → secure backend
  → same account.payment.register
  → invoice PAID
  → Laboratory reads payment_state
```

Do not bypass Odoo.

---

## API

| Method | Path | Privilege |
|---|---|---|
| GET | `/openmrs/abikan-api/laboratory/patient/{uuid}` | `app:lab-lite` or SuperAdmin |
| POST | `/openmrs/abikan-api/laboratory/patient/{uuid}/charge` `{ requestId, orderUuid? }` | same |

---

## Test results

| Step | Result | Label |
|---|---|---|
| Investigate mapping | product.uuid = concept uuid; all prices 1.00; no Lab Order type | **CONFIRMED** |
| Isolated patient | Fatima, no prior bills | **CONFIRMED** |
| One Lab Order | ORD-5 Malarial smear | **CONFIRMED** |
| One charge | S00006 + INV/2026/00005 UNPAID tax 0 | **CONFIRMED** |
| Duplicate POST | reused S00006 | **CONFIRMED** |
| Patient Account | Laboratory UNPAID then PAID | **CONFIRMED** |
| Accountant pay | PCSH1/2026/00005 | **CONFIRMED** |
| Laboratory sees PAID | yes | **CONFIRMED** |
| Unauthenticated | 401 | **CONFIRMED** |
| Registration cannot charge | 403 | **CONFIRMED** |
| Invalid patient / order | 404 | **CONFIRMED** |
| Second payment | 409 | **CONFIRMED** |
| Pharmacy / Registration / Consultation | unchanged | **CONFIRMED** |
| No lab result entered | result empty | **CONFIRMED** |
| `npm run build` | passed | **CONFIRMED** |
| Odoo down | not executed | **NOT TESTED** |

---

## Stop

This phase stops at **Laboratory sees PAID**.

Do **not** start Radiology billing, payment gateway, refunds, sample collection writes, result entry, or OpenELIS redesign. Do **not** change Pharmacy, Registration, Consultation, or Accountant payment.

---

*End of implementation.*
