# Pharmacy UI implementation

Date: **19 Aug 2026**.

Related: `PHARMACY_DISPENSING_IMPLEMENTATION.md`, `ABIKAN_UI_NAVIGATION.md`, `ABIKAN_USERS_ROLES_WORKPLACES.md`.

This phase is the Pharmacy **experience**. It does not add a second prescription table, stock ledger, payment system, or dispensing engine. OpenMRS remains the prescription source. Odoo remains the financial and stock source of truth. Hospital EMR is the staff-facing application and secure orchestration layer.

The first questions after login are:

1. What needs attention?
2. What has been paid?
3. What can I dispense?
4. What has already been dispensed?

---

## Login

| Account | Password | Lands on |
|---|---|---|
| `pharmacy.abikan` | `Admin123` (this environment only) | Pharmacy `#/pharmacy` |

There is no location picker. The header says **Pharmacy**. Hidden session location is not shown. Staff never see Pharmacy Counter, OpenMRS, Odoo, sale orders, invoice IDs, picking IDs, or UUIDs on ordinary screens.

---

## Navigation

Sidebar:

- Dashboard → `#/pharmacy`
- Prescriptions → `#/pharmacy/prescriptions`
- Ready to Dispense → `#/pharmacy/ready` (alias `#/pharmacy/ready-to-dispense`)
- Dispensed → `#/pharmacy/dispensed`
- Drug Catalogue — Coming soon
- Stock — Coming soon

Unknown `#/pharmacy/…` stays in Pharmacy (dashboard). It does not become Administration.

`#/accountant` as a pharmacist: access denied, Pharmacy sidebar remains.

Patient chart: `#/pharmacy/patient/{uuid}`.

Prescription detail: `#/pharmacy/prescription/{orderUuid}`.

Coming Soon items are disabled menu marks. They do not open Administration and they are not fake catalogue or stock screens.

---

## Dashboard (`#/pharmacy`)

Operational overview from `GET /openmrs/abikan-api/pharmacy/queue`:

| Card | Source |
|---|---|
| Prescriptions | `ready.length + other.length` |
| Ready to Dispense | `ready.length` |
| Dispensed | rows whose dispensing status is `DISPENSED` |

Zeros are real queue state. There is no **Dispensed Today** card because the queue payload has order time, not a dispensed-at timestamp.

Then **Needs attention**: unpaid, partially paid, and ready-to-dispense rows.

Empty: **No prescriptions requiring attention.**

Browser check on 19 Aug 2026: Prescriptions 3, Ready 0, Dispensed 2. Needs attention showed Tunde Bakare, UNPAID, “Please proceed to the cashier.”

---

## Prescription queue (`#/pharmacy/prescriptions`)

All queue rows. Each line shows:

Patient, hospital number, medication, quantity, date/time, payment status, dispensing status.

Staff labels: **UNPAID**, **PAID**, **PARTIALLY PAID**, **READY TO DISPENSE**, **DISPENSED**.

Search by name or hospital number on this list. Empty search: **No prescriptions found.**

---

## Payment status

The pharmacist does not decide whether something is paid. Odoo does.

Existing rule, unchanged:

- `paid` / `in_payment` and residual = 0 → eligible for dispensing
- Partial payment → **PARTIALLY PAID**, not ready to dispense

There is no `prescription.isPaid` in Hospital EMR. There is no second financial state.

---

## Ready to Dispense (`#/pharmacy/ready`)

Only rows the backend already classifies as **READY TO DISPENSE**.

Multiple medicines for the same patient are grouped on one card. Each line still dispenses through the existing per-prescription endpoint.

Primary actions: **View Prescription** and **Dispense**.

This environment had **nothing waiting** because the paid test prescriptions are already dispensed. That empty state is real.

---

## Dispense

Existing endpoint, reused:

`POST /openmrs/abikan-api/pharmacy/prescription/{orderUuid}/dispense`

Browser body is `{ requestId }` only. Odoo credentials stay server-side.

Confirmation dialog:

- Patient
- Hospital number
- Medication
- Quantity
- “This will mark the prescription as dispensed and update pharmacy stock.”
- Cancel / Confirm Dispense

Success: **Medication dispensed successfully.**

Staff errors:

| Backend | Staff copy |
|---|---|
| `already_dispensed` | Already dispensed. |
| `insufficient_stock` | Not enough stock to dispense this medication. |
| `unpaid` | Payment required before dispensing. Please proceed to the cashier. |

The server remains authoritative. Disabling the button is not security.

**This phase did not perform a live dispense.** Aisha Bello’s existing dispensed result was left untouched. Insufficient stock was not live-tested.

---

## Dispensed (`#/pharmacy/dispensed`)

Completed rows from the same queue. Browser check: Adaeze Okafor and Aisha Bello, both **PAID · DISPENSED**.

**Dispensed by** is shown only when the existing payload already includes `recordedBy`. No second Hospital EMR audit table was added.

For staff, **DISPENSED** means the Odoo picking is done / delivered quantity completed. OpenMRS “Dispensed” is still not written.

---

## Prescription detail (`#/pharmacy/prescription/{orderUuid}`)

Patient: name, hospital number, age, sex.

Prescription: medication, strength, quantity, instructions, date.

Payment: **PAID** / **UNPAID** / **PARTIALLY PAID**.

Dispensing: **READY TO DISPENSE** / **DISPENSED** (or **UNPAID** when payment is still required).

Unpaid / partially paid:

> Payment required before dispensing. Please proceed to the cashier.

No Pay button. **View Patient Account** is read-only.

---

## Patient Account

Pharmacy may open Patient Account. It is read-only. Invoice numbers, sale-order names, and payment references are hidden for Pharmacy staff. Payment language stays **PAID** / **UNPAID** / **PARTIALLY PAID**. There is no Pay button.

---

## Permissions

`pharmacy.abikan` can view prescriptions, payment status, the ready queue, dispense through the existing endpoint, view completed dispensing, open the patient chart where permitted, and view Patient Account.

Cannot collect payment, register payments, edit invoices, edit tariffs, refund, assign beds, transfer, discharge, administer users, or open Administration.

| Call | Result |
|---|---|
| Unauthenticated `GET /pharmacy/queue` | **401** |
| Unauthenticated `POST /accountant/payment` | **401** |
| `pharmacy.abikan` `GET /pharmacy/queue` | **200** (3 rows) |
| `pharmacy.abikan` `GET` Patient Account | **200** |
| `pharmacy.abikan` `POST /accountant/payment` | **403** |
| `pharmacy.abikan` `POST /inpatient/accommodation/tariffs` | **403** |
| `pharmacy.abikan` `GET /accountant/dashboard` | **403** |
| `pharmacy.abikan` `POST /inpatient/assign` | **403** |

UI hiding is not security. The server still enforces residual = 0 before dispense.

---

## Browser click-through (19 Aug 2026)

`https://localhost/abikan/`. No dispense, payment, stock, tariff, or bed write.

1. Login `pharmacy.abikan` → Pharmacy, no location picker, department **Pharmacy**
2. Dashboard: Prescriptions 3, Ready 0, Dispensed 2; Tunde unpaid in Needs attention
3. Prescriptions: Adaeze DISPENSED, Aisha DISPENSED, Tunde UNPAID
4. Ready: Nothing waiting to dispense
5. Dispensed: Adaeze and Aisha
6. Aisha detail: PAID / DISPENSED, already dispensed, no Pay
7. Patient Account: read-only, no Pay
8. Tunde detail: UNPAID, cashier copy, no Dispense
9. `#/pharmacy/not-a-screen` → Pharmacy dashboard
10. `#/accountant` → access denied, Pharmacy sidebar
11. Sign out
12. `nurse.abikan` → Nursing
13. `accountant.abikan` → Accountant

Confirmation dialog: implemented. Not Confirm-clicked, because nothing was ready without consuming protected stock.

---

## Tests and build

```
npm test   → 31 passed
npm run build → tsc --noEmit && vite build, success
bundle → dist/assets/index-Dee9OVW-.js
```

After build, `dist/index.html` was copied to the proxy DocumentRoot so `https://localhost/` matches `/abikan/`.

---

## Data changed

None. No prescriptions, invoices, payments, stock, or OpenMRS dispensed flags were created or modified. Aisha’s existing dispensed result remains.

---

## Known limitations

1. There is no **Dispensed Today** count. The queue does not provide a dispensed-at time.
2. Ready to Dispense was empty in this hospital at click-through because the paid test prescriptions are already dispensed.
3. Insufficient stock is enforced by the existing backend and mapped in the UI. It was **not live-tested**.
4. Duplicate dispense protection is existing backend behaviour. It was not re-proven by consuming stock.
5. OpenMRS “Dispensed” is still not written. Staff **DISPENSED** means the Odoo picking is done.
6. Full quantity or nothing. Partial dispensing was not added.
7. Drug Catalogue and Stock remain Coming Soon. Hospital EMR does not keep its own stock quantity.
8. One OpenMRS drug order is one queue line. Several medicines for one patient are grouped on Ready to Dispense; each line still uses the existing per-order dispense endpoint.
9. Confirmation Cancel/Confirm was not live-clicked against a ready prescription in this pass.
10. Doctor/Clinical expansion was not started.
11. `Admin123` is development-only.
