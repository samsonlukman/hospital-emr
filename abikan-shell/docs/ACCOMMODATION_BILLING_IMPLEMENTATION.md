# Accommodation billing — implementation

Date: **18 Aug 2026** (Africa/Lagos). Related: `ACCOMMODATION_BILLING_INVESTIGATION.md`, `INPATIENT_IMPLEMENTATION.md`, `PATIENT_ACCOUNT_IMPLEMENTATION.md`, `ACCOUNTANT_CASHIER_IMPLEMENTATION.md`, `PATIENT_ACCOUNT_DEPARTMENTAL_CHARGES.md`.

```
OpenMRS / Bahmni  — wards, rooms, beds, assignments, admissions, transfers, discharges
Odoo              — Accommodation shop, 16 service products, sale orders, invoices, payments
Hospital EMR            — simple hospital UI + secure charge writer
```

Hospital services remain tax-exempt on these products only. Company **Tax 15%**, company **USD**, and protected financial records were not changed.

---

## 1. Products created

**IMPLEMENTED** · created only if missing · list prices were not overwritten

| Record | Value |
|---|---|
| Shop | **Accommodation** (warehouse / pricelist / payment term copied from Consultation Desk) |
| Category | `All / Services / Accommodation` |
| Products | **16** service products, `invoice_policy=order`, no stock, empty `taxes_id` |
| Mapping | `product.product.default_code` = OpenMRS **area location uuid** |
| Staff name | `Accommodation — {ward or room}` |
| Initial price | **0** (unconfigured). Charging refuses 0 |

No 28th bed. No handwritten naira prices. No TEST product overrides in the catalogue.

| Area | Beds | How it is priced |
|---|---:|---|
| Hawawu Maternity Ward | 4 | Price per occupied bed |
| Aisha Children Ward | 3 | Price per occupied bed |
| Emergency Room | 2 | Price per occupied bed |
| Silver 207, Silver 206, Bronze 208, Pre Labour Room | 2 / 2 / 3 / 2 | Price per occupied bed |
| Each Gold / Platinum / Diamond room | 1 | Price per room |

---

## 2. Tariff configuration

**IMPLEMENTED** · SuperAdmin / System Developer only

`#/accommodation-settings` → choose ward/room → enter daily price → Save.

- Multi-bed areas show **Price per occupied bed**.
- Single-bed rooms show **Price per room**.
- A price of 0 means “not ready to bill”.
- Saving writes `product.list_price` and keeps sales tax empty.
- Changing a price does **not** rewrite posted bills (`price_unit` snapshot).

Doctors, nurses, registration, pharmacy, laboratory, and radiology cannot open this screen.

**REQUIRES ACCOUNTING CONFIGURATION** for approved production amounts and for NGN.

---

## 3. Backend endpoints

All routes require an authenticated OpenMRS session. Odoo credentials stay in `abikan-api`.

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/openmrs/abikan-api/inpatient/accommodation/tariffs` | SuperAdmin | List 16 areas and prices |
| POST | `/openmrs/abikan-api/inpatient/accommodation/tariffs` | SuperAdmin | Save one daily price |
| POST | `/openmrs/abikan-api/inpatient/accommodation/catch-up` | Ward or admin | Create missing extra days |
| POST | `/openmrs/abikan-api/inpatient/accommodation/charge` | Ward or admin | Retry billing for the current stay |
| POST | `/openmrs/abikan-api/inpatient/assign` | Ward | Assign bed, then best-effort Day 1 charge |
| POST | `/openmrs/abikan-api/inpatient/transfer` | Ward | Transfer, then upgrade / next-day rules |
| POST | `/openmrs/abikan-api/inpatient/discharge` | Ward | Discharge, then catch-up extras |
| GET | `/openmrs/abikan-api/inpatient/patient/{uuid}` | Ward or doctor | Stay + catch-up + payment label |
| POST | `/openmrs/abikan-api/accountant/payment` | Accountant | Unchanged deposit / partial / full |

`asOf` on assign / transfer / discharge / catch-up is SuperAdmin-only, for isolated time tests. Staff screens never send it.

---

## 4. Bed assignment integration

**IMPLEMENTED**

Billing starts only after a successful Bahmni bed assignment (`POST /beds/{bedId}`).

Does **not** start from:

- Doctor **Admit Patient**
- an open IPD visit alone
- sleeping or nursing notes

If Odoo is down or the tariff is missing, the bed write still succeeds. The stay payload includes a staff message such as “Accommodation tariff has not been configured for this room.”

Bahmni `GET admissionLocation` `bedUuid` is **not stable** between reads. Numeric `bedId` is stable (Gold Room 203 remains id **10**). Hospital EMR looks up beds by `bedId` when the browser sends it, and still posts to `/beds/{bedId}`.

---

## 5. First-day billing

On assign:

1. Resolve the area product from the location uuid.
2. Refuse a missing or zero tariff (clinical assign still succeeds).
3. Create one Accommodation sale order, qty 1, `price_unit` set explicitly, `tax_id` empty.
4. Confirm → posted invoice (`is_invoice_automated`).
5. Line name: `{area} · {bed} · {d Mon}` e.g. `Gold Room 203 · Bed 01 · 17 Aug`.

Idempotency key: `accommodation:{admissionOrTransferEncounterUuid}:{YYYY-MM-DD}`.

Bahmni `GET /bedPatientAssignment/{uuid}` still omits start/end dates. The ADMISSION / TRANSFER encounter uuid is the durable assignment key (**CONFIRMED** available on the ADT write).

---

## 6. Daily billing

Accommodation day boundary: **12:00 Africa/Lagos** (server-side).

- Day 1 = Lagos date of the assignment start, charged immediately.
- Another day is charged only if the patient is still assigned at the next **12:00**.
- 23:00 → 08:00 is **one** day.
- Extra days are created on stay load, discharge, transfer catch-up, or `POST …/catch-up`.

There is no nightly cron in this phase. Opening the patient or discharging is enough for v1. A scheduled catch-up can be added later.

---

## 7. Transfer billing

**Same accommodation day** (before the next 12:00 after the stay’s Day 1):

- Dearer room: keep the original invoice; post a second invoice for the difference. Line: `{new area} · same-day upgrade · {date}`. Key: `…:{date}:upgrade`.
- Cheaper room: keep the original charge. No automatic credit. Staff message: accounting must decide whether a credit is needed.

**After the day has changed:**

- Previous days stay historical.
- Extra days already billed are not rewritten.
- The new room’s tariff applies from the next unbilled checkout day.

A new ADMISSION after discharge is a new stay. Old invoices are not reused as “already billed for this date.”

---

## 8. Discharge billing

Discharge:

1. Reads the assignment that is ending (captured **before** the Bahmni discharge).
2. Creates any missing extra days under the 12:00 rule.
3. Never blocks discharge for unpaid bills.

Outstanding Accommodation invoices stay on Patient Account for the Accountant.

---

## 9. Partial payment

**UNCHANGED** Accountant path: `account.payment.register`.

A deposit is a partial payment against posted Accommodation invoice(s).

| Bill | Paid | Odoo | Patient Account |
|---|---|---|---|
| 100 | 50 | `payment_state=partial`, residual 50 | Accommodation · Paid 50 · Outstanding 50 |

The invoice is not marked PAID. Nursing never collects money.

---

## 10. Patient Account

No second account. Shop/category **Accommodation** already maps to department **Accommodation**.

Staff see the line description (ward/room, bed, date, or “same-day upgrade”), amount, payment status, and outstanding. Invoice line names are preferred over raw product names.

Currency comes from Odoo (USD on this company). ₦ is not hardcoded.

---

## 11. Accountant

No separate accommodation cashier. Accommodation invoices appear with other departmental bills. Cash/bank, amount, receipt PDF: existing workspace.

---

## 12. Nursing

Ward board and patient stay unchanged except:

- Optional **PAID / PARTIALLY PAID / OUTSTANDING**
- Warning if the daily price is not set
- **No Pay button**, no amount, no journal, no Odoo ids

---

## 13. Emergency

Assign bed → charge attempted → payment later.

Missing tariff / unpaid bill / Odoo down must not block emergency assignment or discharge.

---

## 14. Security

- Browser never receives Odoo credentials.
- Financial writes use Odoo ORM via `abikan-api`.
- Tariff writes: SuperAdmin / System Developer only.
- Payments: existing Accountant privilege / SuperAdmin.
- Charge create runs after ADT on the server, not from a Nursing cash action.

---

## 15. Idempotency

| Layer | Key |
|---|---|
| Request | `requestId` (in-memory; same pattern as Laboratory) |
| Durable | `sale.order.line.external_order_id` = `accommodation:{encounterUuid}:{date}` or `…:upgrade` |

A container restart cannot create a second line with the same key. Search-before-create.

---

## 16. Tests

Isolated patients only: **Ibrahim Musa** `ABC200008` and **Emeka Nwosu** `ABC200010`. Not Adaeze, Aisha, Tunde, John, Blessing, Chinedu, Fatima, or Ngozi.

TEST tariffs used during the run (then reset to 0): Gold Room 203 **10**, Platinum Room 209 **20**, Hawawu **5**, Silver 207 **8** (company USD).

| # | Case | Result |
|---|---|---|
| 1 | Single-bed assign (Gold 203) | **PASS** |
| 2 | Multi-bed assign (Hawawu) | **PASS** |
| 3 | First charge $10, tax 0, department Accommodation | **PASS** |
| 4 | Partial $5 → `partial`, outstanding $5 | **PASS** |
| 5 | Remaining $5 → `paid` | **PASS** |
| 6 | Outstanding after upgrade $10 | **PASS** |
| 7 | Same-day 10 → 20 (original + upgrade) | **PASS** |
| 8 | Next-day transfer | First run **404** (stale Bahmni layout `bedUuid`). Retest with live board + `bedId` **200**. Extra-day catch-up implemented |
| 9 | Discharge before 12:00 | First run created a second day on **readmit** (wrong stay boundary). **Fixed**: current stay starts at the latest ADMISSION. Retest: discharge did not add a day |
| 10 | Discharge after 12:00 (`asOf`) | **PASS** · bed released with outstanding |
| 11 | Overnight / before next noon | **PASS** · no extra day |
| 12 | 11pm → 8am (`asOf` 08:00) | **PASS** · still one day |
| 13 | Long stay (`asOf` +6 days) | **PASS** · extra daily invoices |
| 14 | Duplicate catch-up | **PASS** · same invoice |
| 15 | Retry after restart-safe key | **PASS** |
| 16 | Missing tariff (Gold 202 at 0) | **PASS** · assign succeeded, no invoice |
| 17 | Emergency without payment | **PASS** |
| 18 | Historical tariff 10 → 25 | **PASS** · first invoice stayed $10 |
| 19 | Two patients, Hawawu Bed 01 and 02 | **PASS** |
| 20 | Second occupant of same bed | **PASS** · 409, bed not taken |

Cheaper same-day move: original $20 kept, `policy_required`, no credit. **PASS**.

After tests: all **27** beds **AVAILABLE**. Isolated TEST tariffs reset to **0**.

New isolated invoices on Ibrahim / Emeka (e.g. `INV/2026/00007` onward) are TEST accommodation bills, not protected records.

---

## 17. Protected records

Not modified:

- ORD-1 through ORD-6
- S00001 through S00007
- INV/2026/00001 through INV/2026/00006
- PCSH1/2026/00001 through PCSH1/2026/00006
- P00001
- pharmacy stock, Tax 15%, company USD
- existing test pharmacy / registration / consultation / lab / radiology products
- existing 27 beds and 16 hospital locations
- Adaeze still shows only `INV/2026/00001`

---

## 18. Known limitations

1. **No nightly job.** Extra days appear when a stay is opened, on transfer/discharge, or via catch-up. A 30-day stay with nobody opening the chart will not post days 2–30 until catch-up.
2. **One invoice per charge event.** A long stay creates many Accommodation invoices. Weekly grouping is not built.
3. **Cheaper same-day move** does not credit. Accounting must decide.
4. **Bahmni layout `bedUuid` is unstable.** Use `bedId` for writes. Staff picking from the current board is safe.
5. **Assignment REST omits dates.** Encounter datetime is the start proxy.
6. **`asOf`** is an admin test hook, not a staff control.
7. Isolated retests on Ibrahim/Emeka accumulated several TEST invoices. Do not treat those as production tariffs.
8. Production prices are still **0**. Charging will report “tariff has not been configured” until an administrator enters approved amounts.

---

## 19. Future improvements

- Approved production prices (accounting)
- NGN cutover (separate Operations/Accounting phase)
- Optional dated pricelist items
- Nightly catch-up job
- Weekly grouping for long stays
- Credit-note workflow for cheaper-room and wrong-bed corrections
- Tighten Bahmni `maxPatientsPerBed` to 1 (hospital decision)
- Dedicated cashier user with `abikan:accountant`

---

## Staff workflow (what people actually do)

| Role | What they do |
|---|---|
| Doctor | Admit Patient. No bed, no price, no invoice |
| Nurse | Assign / transfer / discharge. May see Paid / Outstanding. No Pay |
| Administrator | Accommodation prices |
| Accountant | Collect deposit, partial, or full on Accommodation bills |
| Registration | Identity / OPD. May open Patient Account. No bed pick |

The complexity stays in the backend.
