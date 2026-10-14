# Troubleshooting

For hospital staff. Do not change hidden records or share accounts.

---

## I cannot log in

**Possible cause:** Wrong username or password; account disabled; network.

**Check:** Caps lock. Your own username. Hospital address.

**Do:** Try again. Ask Hospital Admin whether the account is disabled.

**Contact Hospital Admin:** After two or three failures, or if many staff fail at once.

**Do not:** Use another person’s account or a development password.

---

## The EMR is unavailable / Unable to connect

**Possible cause:** Network, power, or the hospital system is down.

**Check:** Another computer on the hospital network. Whether others are affected.

**Do:** Wait and try again. If everyone is down, contact Hospital Admin.

**Do not:** Recreate patients on paper without a supervisor’s downtime plan.

---

## I cannot find the patient

**Possible cause:** Spelling; they were never registered; you searched phone but no phone is stored.

**Check:** Hospital number. Alternate spelling. Ask Reception.

**Do:** Search again. Register only after a supervisor agrees this is a new person.

**Do not:** Create a duplicate record to “get on with it.”

---

## The patient is not appearing in my department

**Possible cause:** Wrong visit type; not admitted; not ordered; not paid (Pharmacy).

**Check:**

- **Doctor Today's Patients:** visit must be General Outpatient or Follow-up **started today**. Emergency and admission are excluded.
- **Nursing:** doctor admit and/or bed assignment.
- **Laboratory:** doctor submitted the order.
- **Pharmacy Ready to dispense:** bill must be **fully** paid.
- **Radiology:** an imaging order exists.

**Do:** Ask the department that starts that step.

**Do not:** Start extra visits or extra registrations to force the list.

---

## The medication is not appearing on MAR

**Possible cause:** When-needed (PRN) medicine; outpatient order; not admitted; schedule not created yet.

**Check:** The patient is occupied on a bed. The prescription is an inpatient scheduled order, not PRN.

**Do:** PRN is **not** on the scheduled sheet in this release. Use the doctor and hospital policy outside MAR. Reload the chart.

**Do not:** Administer from Pharmacy as if it were MAR.

---

## I cannot administer the medication

**Possible cause:** Outside the window; already recorded; discharged; wrong patient.

**Check:** Scheduled versus actual window (30 minutes early / 60 minutes late). Slot status. Admission still active.

**Do:** Use **Administer outside scheduled window** with a true reason when the time is outside the window. Confirm identity.

**Do not:** Change the clock or ask anyone to backdate.

---

## The medication is outside the administration window

**Possible cause:** You are more than 30 minutes early or more than 60 minutes late.

**Do:** Use the outside-window action and record the clinical reason. Time is stored automatically.

**Do not:** Skip the reason or record a false time.

---

## The laboratory order is not visible

**Possible cause:** Order not submitted; different patient; board still loading.

**Check:** Doctor consultation orders. Hospital number. Wait several seconds and refresh — the board can be slow.

**Do:** Ask the doctor to confirm submit.

**Do not:** Create a new patient.

---

## The laboratory result is not visible

**Possible cause:** Specimen not collected; result not validated; processing not finished.

**Check:** Laboratory processing, not only Hospital EMR.

**Do:** Complete collection, testing, and validation in laboratory processing. Process a **new** result during UAT.

**Do not:** Type a result into Hospital EMR or invent a value.

---

## The prescription is not available for dispensing

**Possible cause:** Unpaid or partial payment; already dispensed; no stock.

**Check:** Accountant. Stock on the prescription.

**Do:** Send the patient to pay. Do not dispense unpaid medication.

**Do not:** Bypass the block.

---

## The patient has not paid

**Possible cause:** Charge not created; cashier not collected.

**Check:** Patient Account. Which department should have created the fee.

**Do:** Reception / Doctor / Radiology / Pharmacy path as appropriate, then Accountant.

**Do not:** Treat unpaid as dispensed or as a completed laboratory result.

---

## The accommodation charge looks wrong

**Possible cause:** Tariff was **0**; old bill in dollars; price changed after the bill.

**Check:** Whether the bill is old. Whether that ward has a tariff.

**Do:** Collect the billed amount. Ask SuperAdmin to set missing tariffs for **new** days. Do not expect an old bill to change.

**Do not:** Edit hidden financial records.

---

## The price I changed did not change an old bill

**Possible cause:** This is how the system works.

**Do:** Explain that the bill keeps the price from the day it was created.

**Do not:** Create a fake second bill to “fix” history unless a supervisor starts a formal correction process.

---

## The EMR is slow

**Possible cause:** Laboratory board load; busy hour; workstation.

**Check:** Whether only Laboratory is slow (known). Whether all screens are slow.

**Do:** Wait for the laboratory board. Try again. Tell Hospital Admin if the whole system is unusable.

**Do not:** Click submit repeatedly on payments or dispense.

---

## Diagnoses unavailable on Nursing

**Possible cause:** Known limit of this release.

**Do:** Continue notes, vitals, MAR, and the real nursing tasks list. Ask the doctor for the diagnosis.

**Do not:** Invent a diagnosis. Care plan and intake/output are not available.

---

## When to contact Hospital Admin

- Nobody can sign in
- A staff account must be disabled
- A department is missing from someone who should have it
- The system is down
- Repeated errors after you confirmed identity and payment

## What never to do

- Share accounts
- Change times
- Bypass payment
- Fabricate results
- Manipulate hidden records
