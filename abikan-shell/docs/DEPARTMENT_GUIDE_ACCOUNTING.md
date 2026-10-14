# Accountant — Department guide

This guide describes the cashier as it works in this release.

Related: [Billing and payments](BILLING_AND_PAYMENTS.md) · [Reception](DEPARTMENT_GUIDE_RECEPTION.md) · [Pharmacy](DEPARTMENT_GUIDE_PHARMACY.md)

---

## What Accountant is for

Accountant collects money on posted bills and opens receipts.

**Screens:** Cashier · Patient Accounts (search) · one-patient collect screen · Patient Account (read-only money view)

```text
Department creates a charge
    → bill is posted
    → Accountant collects payment
    → receipt
    → department shows Paid (Pharmacy shows Ready to dispense)
```

---

## Logging in

Sign in with an account that has Accountant access. **Cashier** opens: *Search a patient to collect payment.*

---

## Finding the bill and collecting

**PURPOSE:** Record what was collected.

**WHO DOES IT:** Accountant.

**STEP-BY-STEP**

1. Search by name, hospital number, or phone.
2. Confirm identity.
3. Review bills that are still unpaid.
4. Collect the amount received.
5. Confirm. Open or print the receipt when offered.

**WHAT HAPPENS AFTER SAVING:** The bill shows paid (or remaining unpaid if only part was collected, where partial payment is offered). Pharmacy can then dispense a **fully** paid prescription. Laboratory and Radiology still must finish their own work.

**COMMON ERRORS:** Patient not found — try hospital number. Nothing to collect — the department may not have created the charge, or the bill is already paid. Mixed currencies — *Select invoices in the same currency.*

**WHAT TO DO IF SOMETHING FAILS:** Ask the originating department whether they created the fee. Do not mark a bill paid on paper only. Do not ask Pharmacy to dispense unpaid medication.

**SECURITY NOTES:** Do not share the cashier account. Do not skip identity.

---

## Billed, collected, outstanding

These words mean **money on bills**, not hospital “revenue.”

| Word | Meaning in Hospital EMR |
|------|-------------------|
| **Billed** / Amount | Amount on bills created so far |
| **Collected** / Paid | Amount already received |
| **Outstanding** / Still unpaid | Amount still unpaid **now** |

On **Patient Account**:

- **Amount** — *Billed so far*
- **Paid** — *Already received*
- **Outstanding** — *Still unpaid*

On **Cashier**: **Collected today** and **Still unpaid**.

Hospital Admin **Outstanding** is a **current snapshot**, not the balance as of a past date.

---

## Which bills you collect

Posted bills from:

- Registration cards (Individual Card, Family Card)
- Consultation fees
- Laboratory fees
- Radiology examination prices
- Pharmacy prescriptions
- Accommodation (daily ward/room charges)

Draft bills that are not posted are not collectable.

**Refunds are not currently available in this release.**

---

## Accommodation

Accommodation tariffs are set by **SuperAdmin** under Administration → **Accommodation Prices** (naira daily price per ward/room).

A charge can be created when Nursing assigns a bed. Changing today’s tariff does **not** rewrite a bill already posted.

New accommodation bills use the naira accommodation list. **Older accommodation bills that were in dollars stay in dollars.**

Wards without a configured tariff may show **0** until a price is set.

Unpaid accommodation does **not** block Nursing assign, transfer, or discharge. Still collect what is owed.

---

## Prices you cannot change

Accountant can **view** Reception, Laboratory, and Pharmacy prices. Accountant **cannot** change them.

Changing a catalogue price never rewrites an old bill. If a patient disputes an old amount, look at the bill from the day it was created.

---

## What Accountant cannot do

- Dispense medicines
- Record clinical notes, vitals, or MAR
- Enter laboratory or radiology results
- Create registration, laboratory, or consultation charges from the cashier screen
- Change department catalogue prices
- Process refunds in this release
