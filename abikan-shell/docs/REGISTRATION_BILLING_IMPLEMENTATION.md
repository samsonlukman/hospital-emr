# Registration billing — implementation

Date: **17 Aug 2026** (UTC). Controlled isolated TEST only.

Related: `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `ACCOUNTANT_PAYMENT_E2E_TEST.md`, `PATIENT_ACCOUNT_DEPARTMENTAL_CHARGES.md`, `PHARMACY_DISPENSING_IMPLEMENTATION.md`.

This phase implements:

```
Registration
  → registration / visit
  → Registration fee (Odoo sale order + posted invoice)
  → Patient Account UNPAID
  → Accountant payment (existing path)
  → Odoo invoice PAID
  → Registration sees PAID
```

Odoo remains the financial source of truth. OpenMRS remains the clinical source of truth. There is no Hospital EMR ledger. Registration does **not** collect money.

Status labels: **CONFIRMED** · **IMPLEMENTED** · **READ-ONLY** · **WRITE** · **UNKNOWN** · **COMING SOON** · **REQUIRES HOSPITAL DECISION** · **REQUIRES ACCOUNTING CONFIGURATION** · **NOT TESTED**

---

## 1. Existing Registration workflow

**CONFIRMED** · largely unchanged

| Step | What happens today |
|---|---|
| Desk | `#/registration-desk` — search, recent registrations, visits, appointments |
| New patient | Bahmni Registration SPA `/bahmni/registration/index.html#/patient/new` |
| Search | Bahmni find-patient, **or** Hospital EMR header search → `#/registration/patient/{uuid}` |
| Patient create | OpenMRS `patient` / `person` / identifier (MRN) via Bahmni |
| Visit | OpenMRS `visit`. Bahmni `defaultVisitType` = **OPD**. This test started one OPD visit at Registration Desk |
| Encounter | **Not required** for the fee. Bahmni second-page obs (including concept **REGISTRATION FEES**) is a clinical form, **not** an Odoo invoice |
| Location | Login location / visit location. No Pharmacy location is involved |

Hospital EMR does **not** replace Bahmni demographics. This phase adds a patient fee screen after the patient exists.

**CONFIRMED:** Bahmni `REGISTRATION FEES` in `app.json` is an observation widget. It does not create `sale.order` or `account.move`. Do not treat it as billing.

---

## 2. Registration charge model

**IMPLEMENTED** · **WRITE** via Odoo ORM

One **departmental** invoice per registration visit:

```
OpenMRS patient uuid / MRN
  → res.partner (uuid / ref)
  → sale.order (shop = Registration Desk)
       line.external_order_id = registration:{visitUuid}
       line.external_id = visitUuid
  → action_confirm
  → posted out_invoice  (bahmni_sale.is_invoice_automated = True)
  → Accountant account.payment.register
```

Not a Drug Order. Not Atomfeed. Pharmacy order type is not used.

Staff-facing states: **UNPAID** / **PAID**, from `payment_state` + `amount_residual`. No local `isPaid` field.

---

## 3. Odoo integration

**IMPLEMENTED** · **WRITE**

| Object | Role |
|---|---|
| `product.category` **All / Services / Registration** (id 38) | Department grouping |
| `product.product` **Registration Fee — TEST** (id **2389**) | Service, `invoice_policy=order`, `list_price=50.00`, **no customer tax** |
| `sale.shop` **Registration Desk** (id **2**) | Departmental shop. `location_id` empty (not WH/Stock) |
| `sale.order` **S00004** | Charge |
| `account.move` **INV/2026/00003** | Invoice |
| `account.payment` **PCSH1/2026/00003** | Cashier payment (existing wizard) |

Why not Atomfeed: the installed feed only maps OpenMRS **Drug Order** → Pharmacy Counter. Registration has no such order type. Forcing Drug Order would mislabel the bill as Pharmacy and risk stock.

Masters are created idempotently on first Registration GET/POST if missing. Pharmacy products, Tax 15%, and company currency were **not** modified.

---

## 4. Patient / visit linkage

**IMPLEMENTED**

| Key | Value |
|---|---|
| Patient | OpenMRS uuid → `res.partner.uuid`; MRN → `res.partner.ref` |
| Visit | Required. Charge is refused without a visit (`422 visit_required` / `404 visit_not_found`) |
| Visit ownership | Visit patient uuid must match |
| Line key | `external_order_id = registration:{visitUuid}` |
| Origin | sale order `origin` = visit uuid |

Name is never the financial key.

---

## 5. Invoice linkage

**CONFIRMED**

`sale.order.action_confirm` + installed `is_invoice_automated=True` posts `INV/2026/00003`. Invoice origin **S00004**. Partner Blessing Adeyemi. Tax **0**. Residual before pay **50.00**, after pay **0**.

No SQL. No direct `account.move` create.

---

## 6. Accountant workflow

**UNCHANGED** · reused

Existing `POST /openmrs/abikan-api/accountant/payment` → `account.payment.register`.

Registration has **no** Pay button, journal picker, or payment endpoint access.

Live: `registration` user POST payment → **403**. `abikan.admin` paid INV/2026/00003 → **PCSH1/2026/00003**. Second pay → **409 invoice_already_paid**.

Cashier desk department label uses shop name: **Registration**.

---

## 7. Payment status

**IMPLEMENTED** · **READ-ONLY** from Odoo

| Condition | Staff label |
|---|---|
| No invoice yet | Not billed yet (Create fee) |
| Posted invoice, residual > 0 | **UNPAID** |
| `payment_state` in `{paid, in_payment}` and residual 0 | **PAID** |
| Partial | **UNPAID** (same hospital rule as Pharmacy) |

Frontend does not store payment as durable state.

---

## 8. Registration permissions

**IMPLEMENTED**

| Who | Create fee | Collect payment |
|---|---|---|
| `app:registration` | yes | **no** |
| SuperAdmin / System Developer | yes | yes (existing cashier rule) |
| `abikan:accountant` only | **no** (not tested with a dedicated user) | yes |
| Unauthenticated | **401** | **401** |

OpenMRS roles were **not** modified. Registration users do not gain Accountant rights.

---

## 9. Duplicate protection

**IMPLEMENTED**

1. Confirm step in the UI; submit disabled while in flight
2. Server lock on `registration:{visitUuid}` and optional `requestId`
3. Search existing sale line by `external_order_id` before create
4. Same `requestId` after success returns the current charge (`alreadyCreated: true`)
5. New `requestId` for the same visit also returns the existing charge — **no second invoice**

Live: one sale **S00004**, one invoice **INV/2026/00003**. **CONFIRMED.**

---

## 10. Tax behavior

**CONFIRMED** on this TEST product · **REQUIRES ACCOUNTING CONFIGURATION** for production

| Item | Result |
|---|---|
| Company default sale tax | Tax 15% **unchanged** |
| Pharmacy product 2385 taxes | **unchanged** |
| Registration Fee — TEST `taxes_id` | **empty** |
| INV/2026/00003 `amount_tax` | **0.00** |

Hospital policy: patient services should not add tax. Production should keep service products tax-empty (or a Nigerian exempt fiscal position). Do **not** delete Tax 15% globally. Who: hospital accountant / Odoo implementer. **REQUIRES ACCOUNTING CONFIGURATION.**

---

## 11. Currency behavior

**CONFIRMED** · **READ-ONLY**

Company currency remains **USD**. Amounts are formatted from `res.currency`. The UI does not hardcode `₦` or `$` for the fee. Fake Naira card prices were removed from the charge path.

Production Naira cutover remains a separate operations task. **REQUIRES HOSPITAL DECISION.**

TEST list price **50.00** is a controlled placeholder, not a hospital tariff. **REQUIRES HOSPITAL DECISION** for the real fee.

---

## 12. Patient Account behavior

**CONFIRMED** · no redesign

Blessing after payment:

| Field | Value |
|---|---|
| Department | **Registration** |
| Invoice | INV/2026/00003 **PAID** |
| Outstanding | $0.00 |
| Tax | $0.00 |
| Pharmacy section | empty (no pharmacy rows) |
| Payment | PCSH1/2026/00003 $50.00 Cash |

Receipts use the existing Odoo/Bahmni payment PDF. No second receipt book.

---

## 13. UX decisions

**IMPLEMENTED**

- Route `#/registration/patient/{uuid}` — identity, fee, UNPAID/PAID, cashier instruction
- Primary action **Create registration fee** only when no charge exists for the visit
- Confirmation before the Odoo write
- No Pay / Register Payment on Registration
- New Registration still opens Bahmni; copy now says the cashier collects the fee
- Hardcoded ₦2,000 / ₦5,000 card prices removed from the fee workflow
- Fake “Today’s Collection” Naira KPI replaced with **Pay at the cashier**
- Individual vs Family remains a Bahmni form hint only — **not** two Odoo products. **REQUIRES HOSPITAL DECISION**
- Opening an existing patient does **not** auto-create a fee

Visual click-through of the React confirm dialog was **NOT TESTED**. The POST the button calls was executed.

---

## 14. Security

**IMPLEMENTED**

- Browser sends patient uuid, visit uuid, `requestId` only
- Odoo credentials stay in `abikan-api`
- Session required; Registration privilege required for writes
- Visit must belong to the patient
- Price comes from the Odoo product, not from the browser
- Charge type is the Registration shop + product, not a client-supplied ledger code

---

## 15–18. Test objects and payment

**CONFIRMED** isolated patient with partner and **no** prior financial activity. Not Aisha / Adaeze / Tunde / John.

| Field | Value |
|---|---|
| Patient | **Blessing Adeyemi** |
| MRN | `ABC200009` |
| OpenMRS uuid | `0835d7d4-02a2-4275-83ec-329b7128da8e` |
| Odoo partner | id **14** |
| Visit | `86cf60ce-624c-4cd4-9ae8-1f6f9283ce88` OPD @ Registration Desk |
| Charge created by | OpenMRS user **registration** |
| Sale order | **S00004** id 4, shop Registration Desk, tax 0, total 50.00 |
| Invoice | **INV/2026/00003** id 5, posted, then **paid** |
| Payment | **PCSH1/2026/00003** id 3, Cash, 50.00 USD |
| Paid by | `abikan.admin` via existing Accountant POST |

No delivery picking was created (service product). Pharmacy stock 2385 remained **88**.

---

## 19. Test results

| Step | Result | Label |
|---|---|---|
| Open Registration / patient | Blessing, no fee yet | **CONFIRMED** |
| Start visit | One OPD visit | **CONFIRMED** |
| Create fee | S00004 + INV/2026/00003 UNPAID, tax 0 | **CONFIRMED** |
| Exactly one charge | Duplicate POST reused S00004 | **CONFIRMED** |
| Patient Account | Registration UNPAID $50 | **CONFIRMED** |
| Accountant pay | PCSH1/2026/00003 | **CONFIRMED** |
| Invoice PAID residual 0 | yes | **CONFIRMED** |
| Registration GET PAID | yes | **CONFIRMED** |
| Second payment | 409 already paid | **CONFIRMED** |
| Unauthenticated | 401 | **CONFIRMED** |
| Registration cannot pay | 403 | **CONFIRMED** |
| Invalid visit | 404 | **CONFIRMED** |
| Missing visit on POST | 422 | **CONFIRMED** |
| Pharmacy queue | Blessing absent; ORD-2/3/4 unchanged | **CONFIRMED** |
| OpenMRS prescriptions | ORD-1–4 still NEW; Blessing has none | **CONFIRMED** |
| `npm run build` | passed | **CONFIRMED** |
| Odoo down | not executed | **NOT TESTED** |
| Dedicated user without `app:registration` | no isolated user | **NOT TESTED** |

---

## 20. Protected records

**CONFIRMED** unchanged

ORD-1–4, S00001–S00003, INV/2026/00001–00002, PCSH1/2026/00001–00002, P00001, WH/IN/00001, WH/OUT/00001, WH/OUT/00002, product 2385 stock **88**, Tax 15%, USD.

---

## 21. Known limitations and hospital decisions

**REQUIRES HOSPITAL DECISION**

- Must registration block until PAID before clinical service? This phase does **not** block Doctor/Pharmacy on an unpaid registration fee.
- Return-visit / follow-up fees — not implemented.
- Individual vs Family as different Odoo prices — not implemented.
- Production fee amount (not 50.00 TEST).
- NGN cutover.

**REQUIRES ACCOUNTING CONFIGURATION**

- Keep patient service products tax-exempt without deleting Tax 15%.
- Dedicated cashier / registrar OpenMRS users and `abikan:accountant` privilege.

**COMING SOON**

- Laboratory / Radiology / Consultation billing
- Nigerian payment gateway (must still land on `account.payment.register`)
- Registration visit start from the desk “Create Visit” tile (patient screen can start a visit)

**CONFIRMED** limitation: Odoo `write_uid` on S00004 is the XML-RPC service user. Hospital EMR `recordedBy` is the OpenMRS registrar (`registration`). No second audit table.

---

## Future Nigerian gateway

**COMING SOON** · **REQUIRES HOSPITAL DECISION**

```
Hospital EMR cashier
  → Nigerian provider
  → secure backend
  → same account.payment.register
  → invoice PAID
  → Registration / Pharmacy / other departments read payment_state
```

Do not bypass Odoo.

---

## Stop

This phase stops at **Registration sees PAID**.

Do **not** start Laboratory, Radiology, or Consultation billing. Do **not** implement a payment gateway. `bahmni_sale.is_invoice_automated` remains True. `bahmni_sale.is_delivery_automated` remains disabled.

---

*End of implementation.*
