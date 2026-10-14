# Accommodation billing — investigation and architecture

Date: **17 Aug 2026** (UTC). **Investigation only. No writes.**

Related: `INPATIENT_WARD_ROOM_BED_INVESTIGATION.md`, `INPATIENT_IMPLEMENTATION.md`, `ADT_BED_WORKFLOW.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `PATIENT_ACCOUNT_DEPARTMENTAL_CHARGES.md`, `ACCOUNTING_BILLING_WORKFLOW.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `REGISTRATION_BILLING_IMPLEMENTATION.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `LABORATORY_BILLING_IMPLEMENTATION.md`, `RADIOLOGY_BILLING_IMPLEMENTATION.md`.

This phase does **not** create accommodation products, tariffs, invoices, sale orders, charges, payments, deposits, beds, rooms, admissions, patients, encounters, or visits. Odoo, OpenMRS, OpenELIS, PACS, Docker, Atomfeed, stock, tax, and currency were not modified.

```
OpenMRS / Bahmni  — wards, rooms, beds, assignments, admissions, transfers, discharges
Odoo              — future tariffs, sale orders, invoices, payments (unchanged today)
Hospital EMR            — simple hospital UI; future charge writer via the existing abikan-api
```

Status labels: **CONFIRMED** · **RECOMMENDED** · **UNKNOWN** · **NOT PRESENT** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION**

---

## Hospital policies already decided

**CONFIRMED** by the hospital (architecture only):

1. Bed assignment starts accommodation charging immediately. Sleep is not a trigger.
2. Deposits / partial payment are allowed. Full prepayment is not required for admission.
3. Emergency admission must not wait for payment.
4. Multi-bed areas: price per occupied bed / day. Single-bed rooms: price for the room / day.
5. Same-day transfer from a cheaper bed to a dearer bed charges only the difference for that day.
6. Prices must be editable. Handwritten / photographed naira figures must not be hardcoded.
7. 27 beds is the correct inventory. Do not invent a 28th bed.

---

## 1. Current Odoo accounting architecture

**CONFIRMED** on the installed Odoo 16 (Bahmni ERP)

| Item | Live value |
|---|---|
| Company | Bahmni, currency **USD** |
| Chart | Generic US (`l10n_generic_coa`). `l10n_ng` **not** installed |
| Sale tax default | Tax 15% (id 1), excluded |
| Invoice automation | `bahmni_sale.is_invoice_automated` **true** — `action_confirm` creates and **posts** the invoice |
| Delivery automation | `is_delivery_automated` **false** (pharmacy pickings stay reserved until Pharmacy) |
| Payment | `account.payment.register` (already used by Hospital EMR Accountant) |
| Journals | Cash CSH1 (id 6), Bank BNK1 (id 7) |
| Pricelist | Public Pricelist (id 1). **0** `product.pricelist.item` rows |
| Shops | Pharmacy Counter, Registration Desk, Consultation Desk, Laboratory, Radiology Desk |
| Accommodation shop / category / products | **NOT PRESENT** |

Existing departmental charge path (Registration, Consultation, Laboratory, Radiology):

```
Hospital EMR backend (OpenMRS session + privilege)
  → find res.partner by patient uuid / MRN
  → sale.order on the department shop
       line.external_order_id = {dept}:{clinicalKey}
       line.price_unit copied from product.list_price
       line.tax_id = []
  → action_confirm
  → posted account.move
  → Accountant pays via account.payment.register
  → Patient Account reads residual / payment_state
```

Pharmacy still uses Atomfeed Drug Order → sale order. Accommodation must **not** use Atomfeed. There is no OpenMRS “bed charge” order type.

**CONFIRMED** from installed `bahmni_sale` `action_confirm`: after confirm, `_create_invoices()` runs and each invoice is `action_post()`’d. Draft sale orders do not stay open as a running bill unless confirm is skipped — and skipping confirm would diverge from every other Hospital EMR department.

**CONFIRMED** from installed `sale.order.line`:

- `price_unit` is **stored**, `readonly=False`, computed from product / UoM / qty via the pricelist.
- Compute **does not** depend on `product.list_price` directly. Changing list price later does **not** rewrite posted invoice lines.
- Once `qty_invoiced > 0`, `_compute_price_unit` **refuses to change** the line price.
- Invoice lines copy `price_unit` at invoice creation (`_prepare_invoice_line`).

**CONFIRMED** `product.template.invoice_policy`: every product on this database is `order` (2392). 1847 are `type=service`. Service products do not create stock moves when invoiced on ordered quantity.

---

## 2. Existing accommodation-related models

**NOT PRESENT** in Odoo. **CONFIRMED** occupancy model in OpenMRS.

### Odoo

| Object | Status |
|---|---|
| Shop named Accommodation / Inpatient | **NOT PRESENT** |
| Product category containing accommodation / ward / bed / IPD | **NOT PRESENT** |
| Accommodation service products | **NOT PRESENT** |
| Dated pricelist items | **NOT PRESENT** (0 rows) |
| Down Payment (POS) product | **CONFIRMED** exists (`type=service`, `list_price=0`). This is a POS helper, **not** a hospital deposit |
| Odoo Sale “Down Payment” wizard | **CONFIRMED** in `sale.make.invoice.advance`. Unused by Hospital EMR. Creates `is_downpayment` sale lines |

`identify_department` already returns **Accommodation** if a future shop or category name contains `accommodation`. No such shop or category exists yet.

### OpenMRS / Bahmni (clinical occupancy — source of truth)

Table `bed_patient_assignment_map` **CONFIRMED** live:

| Column | Role |
|---|---|
| `uuid` | Unique assignment id |
| `patient_id` | Patient |
| `bed_id` | Physical bed |
| `date_started` | Assignment start (UTC datetime) |
| `date_stopped` | Assignment end (null while current) |
| `encounter_id` | ADMISSION or TRANSFER encounter |
| `voided` | Soft delete |

Ibrahim Musa isolated test (read-only): two historical rows, both ended.

| Assignment uuid | Bed | Started | Stopped |
|---|---|---|---|
| `4c84d23d-…` | Gold Room 203 Bed 01 (id 10) | 18:38:40 | 18:38:44 |
| `06ccfdb6-…` | Silver 207 Bed 02 (id 14) | 18:38:44 | 18:38:46 |

Transfer **ends** the previous assignment and **starts** a new one. History is kept. Discharge sets `date_stopped` via `unAssignPatientFromBed`.

`GET /openmrs/ws/rest/v1/bedPatientAssignment/{uuid}` **CONFIRMED** returns bed, patient, encounter. It does **not** return `date_started` / `date_stopped`. List-by-patient returns empty. Encounter datetime is a usable start proxy (seconds from `date_started` on the test). End can be inferred from the next TRANSFER / DISCHARGE encounter.

Bed states remain **AVAILABLE** / **OCCUPIED** only. `maxPatientsPerBed` is still **2** in Bahmni config. Hospital EMR already refuses a second occupant. Tightening the Bahmni config to 1 is **REQUIRES HOSPITAL DECISION** and must not be changed in this investigation.

---

## 3. Recommended accommodation product model

**RECOMMENDED** · **NOT PRESENT** today · do not create yet

Use the same **service product** pattern as Laboratory / Radiology / Consultation:

| Field | Value |
|---|---|
| `type` | `service` |
| `invoice_policy` | `order` |
| `sale_ok` | true |
| Stock | none |
| `taxes_id` | empty until accounting configures exemption (**REQUIRES ACCOUNTING CONFIGURATION**) |
| Shop | future **Accommodation** (like Radiology Desk) |
| Category | future `All / Services / Accommodation` |

**One product per hospital area** (16 products), not one product per bed:

| Area | Product meaning |
|---|---|
| Hawawu Maternity Ward | Price **per occupied bed / day** |
| Aisha Children Ward | Price **per occupied bed / day** |
| Emergency Room | Price **per occupied bed / day** |
| Silver 207, Silver 206, Bronze 208, Pre Labour Room | Price **per occupied bed / day** |
| Each Gold / Platinum / Diamond room | Price **per room / day** (still one bed row) |

Why not one “Gold class” product: Gold 203 and Gold 202 may later have different prices. Per-area products keep the admin screen “choose the room, enter the price”.

Why not one product per bed: four Hawawu beds share one tariff. Per-bed products would be 27 prices to maintain for 16 tariffs.

Mapping key **RECOMMENDED**: OpenMRS **location uuid** of the area → `product.product.default_code` or `product.product.uuid` (same style as Laboratory concept uuid). Name is never the join.

Refuse to charge when `list_price` is 0 / placeholder. Laboratory refuses `<= 1.01`. Accommodation should refuse **`<= 0`** once production billing is enabled, and also refuse the catalogue `$1.00` placeholders if any leaked product is reused. **Do not** invoice ₦0.00 / $0.00.

Maternity-specific delivery packages and paediatric extras are **not** accommodation. Do not auto-add them.

---

## 4. Recommended tariff model

**RECOMMENDED**

```
OpenMRS location (area)
  → Odoo service product (one per area)
  → product.list_price  = current approved daily tariff
  → currency            = company / pricelist currency (today USD)
```

Do **not** invent `abikan.accommodation.tariff`. Do **not** use product variants (unnecessary). Do **not** rely on pricelist items yet (none exist). A later dated `product.pricelist.item` can hold future prices; it is optional.

Administrator workflow (later, not now):

```
Accommodation settings
  → choose ward / room
  → “Price per bed” or “Price per room”
  → enter amount
  → save  (Hospital EMR backend writes product.list_price)
```

Until an approved price is saved, the product may exist at 0. Charging must fail with a staff message: *This room does not have an approved daily price yet.*

**REQUIRES ACCOUNTING CONFIGURATION** for the real amounts and for NGN.

---

## 5. Price snapshot strategy

**CONFIRMED** (Odoo behaviour) · **RECOMMENDED** (how Hospital EMR should use it)

| Layer | What is snapshotted |
|---|---|
| `sale.order.line.price_unit` | Copied from `list_price` / pricelist **at line create** (Hospital EMR already does this for Lab / Radiology) |
| Posted `account.move.line.price_unit` | Copied from the sale line at invoice time; independent afterwards |
| After `qty_invoiced > 0` | Sale line price is frozen by Odoo |

If Gold Room 203 is 20,000 today and 25,000 tomorrow:

- Yesterday’s posted invoice line stays 20,000. **CONFIRMED** Odoo does not rewrite it when `list_price` changes.
- Tomorrow’s new charge reads the new `list_price`.

**RECOMMENDED** extra safety:

1. Always set `price_unit` explicitly on the sale line (do not leave it to a later recompute).
2. Put the charged amount and the area name in the line `name` (staff-facing: “Gold Room 203 · 17 Aug”).
3. Do not write `product.list_price` as part of a patient charge.
4. Optional later: dated pricelist items. The invoice line remains the legal snapshot.

Currency on the invoice is `sale.order.pricelist_id.currency_id` (company currency today). **Do not hardcode ₦.**

---

## 6. Daily billing strategy

**RECOMMENDED** · **REQUIRES HOSPITAL DECISION** on the checkout hour

Do **not** use a generic hotel rolling 24-hour clock.

Hospital examples:

| Event | Expected |
|---|---|
| Assigned 11:00 | Charge starts immediately |
| Assigned 23:00 | Charge starts immediately |
| 23:00 → 08:00 | **One** accommodation day |
| Same-day transfer 10,000 → 20,000 | Day total **20,000**, not 30,000 |

A naive “one charge per calendar date overlapped” would bill 23:00–08:00 as **two** dates. That contradicts the hospital.

**RECOMMENDED rule — checkout-time occupancy:**

1. Assignment starts **Day 1 immediately** (any clock time).
2. The hospital chooses a **checkout time** in Africa/Lagos (proposal: **12:00**, not midnight). **REQUIRES HOSPITAL DECISION.**
3. Another day is charged only if the patient is **still assigned at that checkout time**.
4. Discharge before the next checkout → no extra day.
5. Same-day transfer does not start a new day; it only adjusts the Day-1 tariff (see §8).

Worked examples (checkout 12:00):

| Stay | Days |
|---|---|
| 11:00 → 15:00 same day | 1 |
| 23:00 → 08:00 next morning | 1 (never present at 12:00) |
| 23:00 → 15:00 next day | 2 (Day 1 at 23:00; Day 2 at 12:00) |
| 11:00 Monday → 11:00 Thursday | 4 (Mon assign + Tue/Wed/Thu checkout if still there Thursday 12:00 — if discharged Thursday 11:00, 3 days) |

Staff-facing language: “Each day in a bed is one accommodation charge. Moving rooms the same day updates that day’s price. Leaving before midday does not add another day.” Exact midday vs 08:00 vs midnight is the hospital decision.

Timezone: convert OpenMRS UTC `date_started` / inferred end to **Africa/Lagos** before applying checkout. **REQUIRES HOSPITAL DECISION** if the hospital wants a different zone.

Do not implement a nightly job in this investigation. When implemented, a backend job plus “catch up at discharge” is enough.

---

## 7. Bed assignment → billing relationship

**RECOMMENDED**

```
OpenMRS bed assignment (uuid, bed, location, date_started, date_stopped)
        │
        ▼
Hospital EMR backend (not the browser)
        │
        ▼
Odoo sale.order.line
  external_order_id = accommodation:{assignmentUuid}:{billingDate}
                  or accommodation:{assignmentUuid}:{billingDate}:upgrade
  external_id       = assignment uuid (or ADMISSION/TRANSFER encounter uuid)
  product           = area tariff
  qty               = 1
  price_unit        = snapshot
```

Trigger = **assignment start**, not sleep, not IPD visit alone, not doctor Admit Patient.

Doctor Admit Patient without a bed must **not** bill.

Assignment created and immediately cancelled / transferred: see §16.

Because `GET bedPatientAssignment/{uuid}` omits start/end, the implementation should:

- Capture assignment uuid + encounter uuid at assign / transfer time from the ADT write path, and/or
- Infer start from the ADMISSION / TRANSFER encounter datetime and end from the next TRANSFER / DISCHARGE.

Do **not** have Hospital EMR write OpenMRS SQL. Do **not** copy assignments into a Hospital EMR ledger.

---

## 8. Transfer billing

**RECOMMENDED** · matches hospital policy · do not implement yet

Day 1: Gold Room 203 at 10,000, already paid 10,000, transfer to Platinum Room 209 at 20,000.

| Odoo line (staff label) | Amount | Why |
|---|---|---|
| Gold Room 203 · that day | 10,000 | First assignment started the day |
| Platinum Room 209 · same-day difference | 10,000 | Bring the day to 20,000 |
| Next checkout still in Platinum | 20,000 | New day at the new tariff |

Do **not** charge another 20,000 on the transfer day.

Because this install **posts invoices on confirm**, do **not** rewrite a posted Gold invoice. **RECOMMENDED:** post a **second Accommodation invoice** for the difference (qty 1, `price_unit` = new tariff − already billed amount for that day). If the first invoice is unpaid, Accountant can pay both together (existing multi-invoice payment). If the first is paid, only the difference remains outstanding.

Idempotency for the difference: `accommodation:{newAssignmentUuid}:{billingDate}:upgrade`.

If the patient moves to a **cheaper** bed the same day: **REQUIRES HOSPITAL DECISION** (credit the difference vs keep the higher charge). The given policy only specifies an upgrade.

Preserve on the Patient Account (from OpenMRS + Odoo lines, not a new table):

- old bed, old tariff, assignment start/end
- new bed, new tariff, assignment start

---

## 9. Deposit architecture

**RECOMMENDED:** treat a deposit as a **partial payment against posted accommodation invoice(s)** using the existing Accountant path.

Example: accommodation 100,000, pay 50,000, outstanding 50,000.

| Mechanism | On this install | Consequence |
|---|---|---|
| **Partial `account.payment.register`** | **CONFIRMED** API exists (`amount` < residual → `payment_state=partial`). **NOT TESTED** live | Invoice stays visible. Residual is the outstanding. Receipt is a normal payment. **Simplest.** |
| Unapplied customer payment (no invoice) | Possible in raw Odoo; Hospital EMR cashier **rejects** amount without selected posted invoices | Partner credit that Patient Account does not currently show as “deposit”. Easy to lose. |
| Sale “Down Payment” wizard | **CONFIRMED** in Odoo source; unused | Extra down-payment lines later deducted. Staff see “Down Payment”, not “Deposit on room”. Diverges from Registration/Lab. |
| POS Down Payment product | **CONFIRMED** `list_price=0` | Wrong channel. Do not use. |
| Hospital EMR deposit ledger | **Must not exist** | Second ledger. |

**RECOMMENDED:** invoice Day 1 immediately so there is a posted bill to pay against. The 50,000 is a cashier partial payment. Nursing never collects it.

A deposit **before** any bed assignment (pay at Registration “for the admission”) is **REQUIRES HOSPITAL DECISION**. If needed later, still create a posted Accommodation invoice (or a dedicated advance invoice) and pay it through the same wizard — not a new ledger.

---

## 10. Partial payment architecture

**CONFIRMED** in Odoo and Hospital EMR Accountant · **NOT TESTED** live (no safe unpaid invoice was created)

- Cashier selects invoice(s), enters amount `> 0` and `<=` selected residual.
- Overpay is rejected.
- Resulting `payment_state` / `amount_residual` come from Odoo after reconcile.
- One payment can cover several invoices (`group_payment=True`).
- Payment is **invoice-level**, not line-level.

**RECOMMENDED** for accommodation:

- Outstanding = sum of Accommodation invoice residuals.
- PARTIALLY PAID = any accommodation invoice `partial`, or some paid and some not.
- Pharmacy READY TO DISPENSE must stay tied to the **pharmacy** invoice only. An accommodation partial must not unlock drugs.

Do not invent allocation across product lines.

---

## 11. Invoice grouping

**RECOMMENDED: A — its own Accommodation invoices**

| Option | Verdict |
|---|---|
| A. Separate Accommodation invoice | **RECOMMENDED.** Same as Registration / Consultation / Lab / Radiology. Invoice `payment_state` **is** the department status. |
| B. General inpatient invoice (mix stay + drugs + lab) | Reject. Line-level PAID is **NOT SUPPORTED**. Pharmacy would be blocked or unlocked incorrectly. |
| C. Combined with consultation | Reject. Different shops, different privileges, different timing. |
| D. Periodically grouped (weekly qty) | Possible later for long stays. **REQUIRES HOSPITAL DECISION.** |
| E. One running invoice for the whole admission | Conflicts with `is_invoice_automated` (invoice posts on confirm; appending days means more invoices or credit/rebill). |

**RECOMMENDED cadence for v1:**

- One posted Accommodation invoice per **charge event** (Day 1, each extra checkout day, each same-day upgrade).
- Patient Account groups them under **Accommodation**.
- Accountant sees them as ordinary outstanding bills.

30 daily invoices for a long stay is noisy. Start correct; offer weekly grouping only after the hospital asks.

---

## 12. Patient Account integration

**RECOMMENDED** · reuse the existing view · **COMING SOON** for live rows

No second account screen. `identify_department` already maps shop/category “accommodation”.

Staff should eventually see (currency from Odoo, not hardcoded ₦):

```
Accommodation
  Gold Room 203 · Bed 01 · 17 Aug · 1 day · amount · UNPAID / PAID
  Platinum Room 209 · Bed 01 · 17 Aug · difference · amount · UNPAID
```

Join:

```
invoice / sale line
  → shop Accommodation or category Accommodation
  → external_id = assignment uuid
  → OpenMRS assignment / encounter for ward, room, bed, dates
```

Outstanding on the overview remains `SUM(amount_residual)` of posted customer invoices. Draft SOs (if any) stay “unbilled”, not residual.

---

## 13. Accountant integration

**RECOMMENDED** · **UNCHANGED** payment engine

```
Patient → outstanding invoices → select → amount → cash/bank
  → account.payment.register → receipt PDF
```

Deposits and partials appear as the same payment list (`PCSH1/…`) with invoice `partial` / residual. No accommodation cashier.

Accountant does not assign beds. Nursing does not register payment.

---

## 14. Nursing visibility

**RECOMMENDED**

Nursing already has ward, room, bed, patient, assign / transfer / discharge. **No Pay button.**

If the hospital wants money awareness (**REQUIRES HOSPITAL DECISION**):

| Show | Do not show |
|---|---|
| PAID / PARTIALLY PAID / OUTSTANDING | Sale orders, invoice numbers, journals |
| Ward / room / bed | Odoo ids |

Read those labels from the existing Patient Account API. Do not let Nursing create or alter invoices.

If a tariff is missing, assignment must still succeed; show *Daily room price is not set yet* without blocking care.

---

## 15. Registration visibility

**RECOMMENDED:** no change required for billing architecture.

Registration already may open Patient Account. It must not select beds. Showing admitted / ward / bed on the registration card is optional later and is **not** required to bill.

---

## 16. Emergency

**CONFIRMED** as architecture · **not** a payment bypass implementation

```
Arrive → clinical care / admit → assign bed → charging may start → payment can follow
```

Technical requirements (do not code a “bypass flag” now):

- Assign bed must not call Odoo as a **prerequisite**.
- Missing tariff / unpaid invoices must not block ADT.
- Day-1 invoice can be created **after** assignment (best-effort). Failure retries later.

Registration payment gates stay as they are.

---

## 17. Maternity

**RECOMMENDED**

Hawawu Maternity Ward: 4 beds, **per occupied bed / day**. Delivery, theatre, and newborn packages are separate future products. Do not bundle them into accommodation.

---

## 18. Children Ward

**RECOMMENDED**

Aisha Children Ward: 3 beds, **per occupied bed / day**. Do not redesign guardian / paediatric registration for this bill.

---

## 19. Discharge

**REQUIRES HOSPITAL DECISION** for money policy · **RECOMMENDED** technically

| Question | Recommendation |
|---|---|
| Generate missing daily charges at discharge? | **Yes** (catch-up). Assignment end is known. |
| Leave unpaid invoices open? | **Yes.** Odoo residuals stay until paid or credited. |
| Require payment to discharge? | **No** as default. Conflicts with emergency and deposit policy. Mark **REQUIRES HOSPITAL DECISION** if the hospital later wants a soft warning only. |
| Emergency discharge with balance | Allow. Accountant follows up on the same invoices. |

Installed ADT already leaves the IPD visit open with Admission Status = Discharged. Billing must key off **assignment end**, not visit close.

---

## 20. Long-stay patients

**RECOMMENDED**

| Stay | v1 |
|---|---|
| 1 day | One invoice (plus optional same-day difference) |
| 3–7 days | One invoice per extra checkout day |
| 30 days | Same, unless the hospital chooses weekly qty later |

Avoid one giant invoice that is rewritten every night. Avoid charging 30 days up front (conflicts with deposit-as-you-go and tariff changes).

A scheduled backend job + discharge catch-up is enough. **REQUIRES HOSPITAL DECISION** before switching to weekly grouping.

---

## 21. Refund / correction strategy

**RECOMMENDED** · use installed Odoo credit notes · do not invent refund products

| Event | Financial action |
|---|---|
| Wrong bed, already invoiced | Credit note the wrong Accommodation invoice; charge the correct area |
| Assignment cancelled same day, already invoiced | Credit note |
| Assignment cancelled before any invoice | Nothing to reverse |
| Tariff typed wrong after post | Credit note + new invoice. Do not edit posted lines in SQL |
| Patient readmitted | New assignments → new keys. Old invoices stay |
| Pharmacy / lab during IPD | Unrelated departmental invoices |

Credit notes: `account.move` `out_refund` via Billing Administrator (already documented). **Not executed** in this investigation.

---

## 22. Idempotency

**RECOMMENDED** after verifying the occupancy model

| Charge | Key on `sale.order.line.external_order_id` |
|---|---|
| Day charge | `accommodation:{assignmentUuid}:{YYYY-MM-DD}` |
| Same-day upgrade | `accommodation:{assignmentUuid}:{YYYY-MM-DD}:upgrade` |

`YYYY-MM-DD` is the **hospital accommodation date** (Lagos date of Day 1, or the checkout date for extra days), not a hotel 24-hour stamp.

If assignment uuid is not in hand, **fallback** `accommodation:{admissionOrTransferEncounterUuid}:{date}` is **CONFIRMED** available (encounter uuid is returned by the existing ADT write).

Also keep the in-memory `requestId` pattern used by Lab / Accountant. After container restart, Odoo `external_order_id` is the durable lock.

Never create a second line with the same key. Search before create (Laboratory already does this).

---

## 23. Security

**RECOMMENDED** · same as existing departments

| Rule | |
|---|---|
| Browser | Patient uuid, assignment/encounter uuid, `requestId` only |
| Backend | OpenMRS session; Odoo ORM via `abikan-api` env credentials |
| Who may create a charge | Server-side after ADT, or a privileged retry. Not Nursing cash. Not the browser |
| Who may pay | Existing Accountant (`abikan:accountant` / SuperAdmin) |
| Validation | Patient matches partner; assignment belongs to patient; bed/area mapped; price approved; currency from Odoo; key unique |
| No SQL | No inserts into `account_move` / `sale_order` |
| No second ledger | No `abikan_accommodation_ledger` |

---

## 24. Exact Odoo records that would eventually be created

**RECOMMENDED** later · **not created now**

| Record | Purpose |
|---|---|
| `sale.shop` **Accommodation** | Departmental invoice grouping |
| `product.category` All / Services / Accommodation | `identify_department` |
| 16 `product.product` (service, `invoice_policy=order`, tax empty or as configured) | One per hospital area |
| `sale.order` + lines | Each charge event |
| Posted `account.move` `out_invoice` | Bill |
| `account.payment` via existing register | Deposit / partial / full |
| Optional later `product.pricelist.item` | Dated future prices |

Would reuse: `res.partner` (existing patient), Cash/Bank journals, Public Pricelist, company currency.

---

## 25. Exact Hospital EMR records that would eventually be created

**RECOMMENDED** later · **not created now**

| Piece | Role |
|---|---|
| `server/patient-account/accommodation.py` | Charge + retry, same style as `laboratory.py` |
| Routes e.g. internal create after assign / `POST …/accommodation/charge` retry | Server-side only |
| Patient Account already maps the department name | No new ledger |
| Optional Nursing balance chip | Read-only labels |
| Optional Accommodation Settings screen | Writes `list_price` server-side |

No Hospital EMR balance table. `requestId` stays ephemeral. Durable identity is Odoo `external_order_id`.

---

## 26. What should NOT be created

**CONFIRMED** for this investigation and for the future design

- Accommodation products, shops, tariffs, invoices, payments, deposits **in this phase**
- A 28th bed
- A second financial ledger
- Atomfeed “bed order” type
- Hardcoded ₦ amounts from photographs
- NGN company currency flip on this test database
- Removal or change of Tax 15%
- Pay button on Nursing / Doctor
- Payment prerequisite on assign / emergency admit
- Hotel rolling 24-hour billing without a hospital checkout decision
- Mixing accommodation onto Pharmacy / Lab invoices
- SQL accounting writes
- Maternity/delivery products disguised as room rent

---

## 27. Hospital decisions still required

**REQUIRES HOSPITAL DECISION**

1. Checkout time (proposal 12:00 Africa/Lagos) that makes 23:00–08:00 one day.
2. Same-day transfer to a **cheaper** bed: credit vs keep the higher charge.
3. Whether Nursing should see PAID / OUTSTANDING.
4. Whether discharge should **warn** on outstanding balance (must not block emergency).
5. Whether a deposit may be taken **before** bed assignment.
6. Long-stay grouping: daily invoices vs weekly.
7. Whether all Gold rooms share one price or each room is priced separately (architecture supports per-room; hospital may still choose one amount).
8. Set Bahmni `maxPatientsPerBed` to 1.
9. Dedicated cashier privilege assignment (`abikan:accountant`).

---

## 28. Accounting decisions still required

**REQUIRES ACCOUNTING CONFIGURATION**

1. Approved daily price for each of the 16 areas (start at 0 / unbillable).
2. Tax on accommodation (hospital direction: exempt). Do **not** remove company Tax 15%. Configure accommodation products with empty `taxes_id` and/or a patient fiscal position — accountant’s job.
3. Production currency NGN: new company/database or planned cutover. **Do not** convert existing USD INV/PCSH1/S0000x.
4. Revenue account / shop warehouse / payment term on the future Accommodation shop (copy the Laboratory shop pattern).
5. Who may edit tariffs.
6. Credit-note authority for wrong-bed corrections.

---

## 29. Recommended implementation sequence

**RECOMMENDED** · stop after this document until review

1. Hospital + accounting sign-off on checkout time, cheaper-bed transfers, tax, and “prices entered later”.
2. **Config only (later phase):** Accommodation shop, category, 16 service products at price 0, location-uuid mapping. Still no patient invoices.
3. Accountant enters real prices. Charging still refuses 0.
4. **Hospital EMR write:** after assign / transfer / discharge catch-up + daily job; keys above; `price_unit` snapshot; no ADT block on failure.
5. Patient Account shows Accommodation automatically via shop/category.
6. Accountant collects deposits/partials on those invoices (already built).
7. Optional Nursing OUTSTANDING chip.
8. Optional weekly grouping, NGN cutover, dated pricelists — later.

Do not start step 2 until this investigation is reviewed.

---

## Bed-assignment edge cases (billing)

**RECOMMENDED** · do not implement

| Event | Billing |
|---|---|
| Assigned then transferred minutes later | Day 1 on first tariff; upgrade difference if new tariff higher |
| Wrong bed | Credit + recharge. Assignment correction is ADT, not a silent price edit |
| Discharged same day | Day 1 only (checkout rule) |
| Readmitted | New assignment uuids → new keys |
| Tariff changed while occupied | Already billed days keep snapshot; next checkout day uses new `list_price` |
| Bed unavailable / occupied | ADT already refuses; no charge |
| Admission cancelled before assign | No assignment → no charge |
| Charge job runs twice | Same `external_order_id` → return existing |

---

## Doctor / Registration / Nursing (roles)

| Role | Accommodation |
|---|---|
| Doctor | Admit Patient only. No bed, no tariff, no invoice |
| Nursing | Assign / transfer / discharge. No payment. Optional balance label later |
| Registration | Identity / OPD. No bed pick. May open Patient Account |
| Accountant | Pay Accommodation invoices like any other bill |

---

*End of investigation. No configuration or data was changed.*
