# Pharmacy — Department guide

This guide describes Pharmacy as it works in this release.

Pharmacy **dispenses** a paid prescription. Nursing **administers** a scheduled inpatient dose on MAR. Do not mix these jobs.

Related: [Doctor](DEPARTMENT_GUIDE_DOCTOR.md) · [Accountant](DEPARTMENT_GUIDE_ACCOUNTING.md) · [Nursing](DEPARTMENT_GUIDE_NURSING.md)

---

## What Pharmacy is for

**Screens:** Dashboard · Prescriptions · Ready to Dispense · Dispensed · Drug Catalogue · Drug Pricing · Inventory

```text
Doctor prescribes
    → bill is created
    → Accountant collects payment
    → Ready to dispense
    → Pharmacy dispenses
    → stock is updated
```

---

## Logging in and finding work

Sign in with your Pharmacy username.

**Dashboard** puts **Ready to dispense** first.

**Prescriptions** lists prescription work. **Ready to Dispense** is paid and waiting. **Dispensed** is already given out.

Confirm **patient, hospital number, and medicine** before you dispense.

---

## Payment state

| What you see | Meaning |
|--------------|---------|
| Unpaid / payment required | Do **not** dispense. Send the patient to Accountant |
| Partial payment | **Not** ready to dispense in this release |
| Ready to dispense | Posted bill is fully paid; stock movement not yet completed |
| Dispensed | You have completed dispense; stock has moved |

Pharmacy has **no payment button**.

---

## Dispensing

**PURPOSE:** Give the patient the prescribed medicine and update stock.

**WHO DOES IT:** Pharmacy.

**STEP-BY-STEP**

1. Open the prescription. Confirm identity and medicine.
2. Check payment is **Ready to dispense**.
3. Check available stock.
4. Select **Dispense**. Confirm: *This will mark the prescription as dispensed and update pharmacy stock.*

This release dispenses the **full** quantity. Partial dispense is not offered.

**WHAT HAPPENS AFTER SAVING:** Status becomes **Dispensed**. Repeating the action does not dispense twice (*This medication has already been dispensed*).

**COMMON ERRORS**

- *Payment required before dispensing. Please proceed to the cashier.*
- *This medication has already been dispensed.*
- *Not enough stock to dispense this medication.*

**WHAT TO DO IF SOMETHING FAILS:** Do not override payment. Do not dispense unpaid medication. Do not invent stock. If stock is short, use Inventory (if you have that right) or tell Hospital Admin.

**SECURITY NOTES:** Do not share accounts. Do not dispense on the wrong hospital number.

---

## Drug Catalogue and Drug Pricing

**Drug Catalogue** adds and edits hospital medicines, including selling price.

**Drug Pricing** changes selling prices for **new** sales. Staff see **₦**.

Changing today’s price does **not** change a bill already created.

Pharmacy can write pharmacy prices. Reception and Laboratory cannot. Accountant and Hospital Admin can view. SuperAdmin can also change these prices.

---

## Inventory

**Inventory** shows stock. **Receive stock** and **Adjust stock** require the hospital inventory right. Adjustment reasons include incorrect opening stock, physical count, damaged, expired, lost/missing, and correction.

Purchase orders and supplier payment are **not currently available in this release**.

---

## Prescription versus MAR

| Pharmacy | Nursing MAR |
|----------|-------------|
| Dispense the supply after **payment** | Administer a **scheduled inpatient** dose |
| Updates stock | Records Given / Not done / Refused / Held |
| Counter | Ward |

Do not present MAR rows as pharmacy dispensing.

---

## What Pharmacy cannot do

- Collect payment
- Administer MAR
- Enter laboratory results
- Change Reception or Laboratory prices
- Dispense unpaid or partially paid prescriptions
