# Radiology — Department guide

This guide describes Radiology as it works in this release.

**Images are not shown in Hospital EMR.** Do not invent PACS or viewer steps.

Related: [Doctor](DEPARTMENT_GUIDE_DOCTOR.md) · [Billing](BILLING_AND_PAYMENTS.md) · [Radiology workflow notes](RADIOLOGY_WORKFLOW.md)

---

## What Radiology is for in Hospital EMR

**Screens:** Radiology (dashboard) · Worklist · patient imaging · examination detail

| You can | You cannot in this release |
|---------|----------------------------|
| See pending examinations (order without a report) | View or upload scan images in Hospital EMR |
| Set a naira price for that examination | Collect payment |
| Write or edit a free-text report | Cancel or delete the order from Radiology |
| See Price pending / Unpaid / Paid | Treat Paid as “scan done” |

The doctor orders from a hospital-approved ultrasound and radiography list (42 services). ECG, CT, MRI, and other names not on that list are **not currently available** on the Radiology menu.

---

## Worklist and report

**PURPOSE:** Price the examination and record the report.

**WHO DOES IT:** Radiology.

**STEP-BY-STEP**

1. Open **Worklist**. Empty state: *No pending Radiology examinations.*
2. Open the examination. Confirm patient, hospital number, visit, and examination name.
3. **Set Price** / **Save Price** in naira. *Accounts collects payment. You can still write the report if unpaid.*
4. **Write Report** or **Edit Report**. Free text. Save.

**WHAT HAPPENS AFTER SAVING:** The doctor can read the report on that visit and examination. Payment status updates after Accountant collects.

**COMMON ERRORS:** *Order unavailable.* Report not visible to the doctor — confirm you saved on the correct examination.

**WHAT TO DO IF SOMETHING FAILS:** Do not attach the report to a different order. Do not tell staff to open a hidden imaging archive as if it were Hospital EMR.

**SECURITY NOTES:** You do not collect payment. Do not share accounts.

---

## Imaging archive

The hospital may run a separate imaging archive. In this release Hospital EMR does **not** show studies, does not replace the archive screens, and does not require a scan to be paid before you can write a report.

**PAID does not mean the scan was performed.**

If a modality and archive are connected later, that is hospital imaging operations — **not currently available in this release** as a Hospital EMR workflow.

---

## What Radiology cannot do

- Collect payment
- Cancel the order from this desk
- Display images
- Change Reception, Laboratory, or Pharmacy catalogue prices
