# Laboratory — Department guide

This guide describes Laboratory as it works in this release.

**Hospital EMR does not perform laboratory processing.** Specimen collection, accession, testing, result entry, and validation happen in **laboratory processing** (the hospital laboratory system). Hospital EMR shows orders, payment state, and released results.

Related: [Doctor](DEPARTMENT_GUIDE_DOCTOR.md) · [Billing](BILLING_AND_PAYMENTS.md) · [OpenELIS administration notes](OPENELIS_LABORATORY_ADMINISTRATION.md) (technical)

---

## What Laboratory is for in Hospital EMR

**Screens:** Dashboard · Pending Orders · Processing · Completed Results · Search Patient · Test Pricing

| In Hospital EMR | In laboratory processing |
|-----------|--------------------------|
| See which tests the doctor ordered | Collect the specimen |
| See unpaid / paid | Accession and process the sample |
| Open **Open laboratory processing** | Enter and validate the result |
| See a result after it is released | Source of the result |
| Set hospital test selling prices | Catalogue of processing methods |

Hospital EMR **does not write** processing records. Do not try to type a result in Hospital EMR.

---

## Logging in

Sign in with your **Hospital EMR** laboratory username. That opens the Laboratory board.

Laboratory processing uses a **separate sign-in**. Your Hospital EMR account does not log you into processing. Hospital-specific processing accounts and roles are set by the laboratory administrator. See hospital OpenELIS training — this manual does not invent those clicks.

---

## How an order appears

```text
Doctor creates a laboratory order on the visit
    → Laboratory sees the order on the board
    → Patient pays at Accountant (when billed)
    → Laboratory collects and processes in laboratory processing
    → Validated result returns
    → Doctor and Laboratory see the result in Hospital EMR
```

Payment is **not** required for the doctor to place the order. **Paid does not mean the sample was collected. Paid does not mean the result is ready.**

---

## Pending, Processing, Completed

**PURPOSE:** Know which orders need work and which have results.

**WHO DOES IT:** Laboratory.

**STEP-BY-STEP**

1. Open **Pending Orders** for new work.
2. Open **Processing** for work already in progress.
3. Open **Completed Results** for released results.
4. Open an order. Confirm **patient, hospital number, visit, and test**.
5. Select **Open laboratory processing** to collect, accession, test, enter, and validate — using your processing account and hospital procedure.

The board groups orders by processing status. Unrecognised states are shown honestly, not invented.

The board can take **several seconds** to load. That is a known limit.

**WHAT HAPPENS AFTER SAVING (in processing):** After the result is validated and released, it appears in Hospital EMR for Laboratory and the doctor. Hospital EMR does not store a second result file.

**COMMON ERRORS:** Order not on the board — the doctor may not have submitted, or you opened a different patient. Result empty — processing not finished. *Orders unavailable* / *Results unavailable* — reload; if it continues, tell Hospital Admin.

**WHAT TO DO IF SOMETHING FAILS:** Confirm the hospital number with the doctor. Do not fabricate a result. Do not skip validation.

**SECURITY NOTES:** Never enter another patient’s result. Never use a shared processing login for clinical work.

---

## Specimen collection, accession, testing, validation

These steps are **not performed in Hospital EMR**.

Follow your hospital’s laboratory processing training for:

- Samples to collect
- Collect sample
- Accession
- Results entry
- Validation / completion

This release does not document those screens as Hospital EMR procedures. If a new test was added to the hospital list, the laboratory administrator may still need to finish specimen and range setup in processing, or samples can sit untested.

**Hospital UAT:** process a **new** result on this hospital stack. Do not treat an old result from another environment as proof.

---

## Test pricing

**PURPOSE:** Set the selling price of hospital laboratory tests for **new** fees.

**WHO DOES IT:** Laboratory (read and write). Accountant and Hospital Admin can view. SuperAdmin can also change these prices.

**STEP-BY-STEP**

1. Open **Test Pricing**.
2. Find the hospital test (this is the ordering list, not the full processing dictionary).
3. Change the naira price and save.

**WHAT HAPPENS AFTER SAVING:** New charges use the new price. Bills already created do **not** change.

Four tests are **not currently available to order** from Abikan: Inorganic Phosphate, Testosterone, Progesterone, Estradiol.

Some tests are marked **Outsourced**. There is no separate outsourced workflow in Hospital EMR.

---

## What Laboratory cannot do

- Collect payment (*Please proceed to the cashier. Laboratory does not collect money.*)
- Enter or validate results in Hospital EMR
- Collect specimens in Hospital EMR
- Change Reception or Pharmacy prices
- Open Administration analytics

---

## Known Laboratory limits

- Fresh result should be proven during hospital UAT
- Board can be slow
- Hospital EMR does not write to laboratory processing
- Paid ≠ collected ≠ resulted
