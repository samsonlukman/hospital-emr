# Billing and payments

Staff language. The billing engine stores the commercial record. Hospital EMR is the cashier and department charge screens.

Related: [Accountant](DEPARTMENT_GUIDE_ACCOUNTING.md) · [Department pricing](DEPARTMENT_PRICING.md)

---

## How a bill is born

```text
Catalogue selling price (today)
    → department creates a charge
    → posted bill
    → Accountant collects payment
    → collected
```

| Step | Meaning |
|------|---------|
| **Catalogue price** | Current selling price on the hospital item |
| **Charge** | That price copied onto this visit / order / day |
| **Bill** | Posted amount the cashier can collect |
| **Payment** | Money recorded as received |
| **Collection** | Same as payment from the cashier’s point of view |

Hospital EMR does not keep a second ledger.

---

## Price snapshot

**Changing today’s catalogue price does not change yesterday’s bill.**

The amount is copied when the charge is created. Later price edits leave that bill, its payments, and its outstanding amount unchanged.

Price history (who changed a catalogue price) is separate from the bill.

---

## Billed, collected, outstanding

Do **not** call these “revenue.” They are bill totals.

| Term | Meaning |
|------|---------|
| **Billed** | Amount on bills created |
| **Collected** | Amount received |
| **Outstanding** | Amount still unpaid **now** |

Hospital overview **Outstanding** and **Current occupancy** are snapshots of now, not historical values for the selected date range.

---

## Who creates the charge

| Charge | Who creates it | When |
|--------|----------------|------|
| Individual Card / Family Card | Reception | After a visit exists |
| Consultation fee | Doctor | On the visit |
| Laboratory fee | With the laboratory order | When the doctor submits |
| Radiology price | Radiology | Per examination |
| Pharmacy | From the prescription | Commercial record after prescribe |
| Accommodation | After ward assignment | Daily room charge |

Only Accountant **collects**.

**Paid does not mean** the consultation is finished, the specimen is collected, the medicine is dispensed, or the scan was performed.

Pharmacy dispenses only when the prescription bill is **fully** paid. Partial payment is not ready to dispense.

---

## Currency

- Staff pricing screens and new departmental bills use **naira (₦)**.
- The financial **company currency may still be US dollars**.
- **Historical accommodation invoices in dollars stay in dollars.** New accommodation uses the naira accommodation list.
- If Patient Account mixes currencies, collect same-currency bills together.

---

## Accommodation

Hospital Admin (or SuperAdmin) sets the daily naira price for each ward or room.

Nursing assigns the patient to a bed. The system creates the applicable bill using the **current** price at that moment. That amount is then historical: a later price change does not rewrite it. Future assignments or later applicable days use the new price.

Unconfigured wards may show **0**. Unpaid accommodation does not block Nursing assign, transfer, or discharge. Historical dollar accommodation bills stay in dollars.

---

## Refunds

**Not currently available in this release.**
