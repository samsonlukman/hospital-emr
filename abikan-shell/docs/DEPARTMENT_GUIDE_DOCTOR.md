# Doctor — Department guide

This guide describes Clinical (Doctor) as it works in this release.

Related: [User manual](ABIKAN_EMR_USER_MANUAL.md) · [Nursing](DEPARTMENT_GUIDE_NURSING.md) · [Laboratory](DEPARTMENT_GUIDE_LABORATORY.md) · [Pharmacy](DEPARTMENT_GUIDE_PHARMACY.md)

---

## What Clinical is for

The doctor sees today’s outpatients, records the consultation, diagnoses, orders laboratory and imaging tests, prescribes, and may request admission.

**Screens:** Dashboard · Today's Patients · My Patients · Patients (search) · Consultation

Dashboard and Today's Patients show the same **Today's Patients** list.

---

## Logging in and finding patients

**PURPOSE:** Open today’s work.

**WHO DOES IT:** Staff with Clinical access.

**STEP-BY-STEP**

1. Sign in with your hospital username. Clinical opens.
2. Use **Today's Patients** for outpatient and follow-up visits that **started today**.
3. Use **My Patients** for people you have already attended (after a saved consultation).
4. Use header search for any patient.

**WHAT HAPPENS AFTER SAVING:** Opening a name continues that visit’s consultation.

**COMMON ERRORS:** An emergency or admission visit does not appear on Today's Patients. That is by design.

**WHAT TO DO IF SOMETHING FAILS:** Search by hospital number. Ask Reception whether the visit was started as General Outpatient or Follow-up.

**SECURITY NOTES:** Confirm name and hospital number before you write.

---

## Consultation

**PURPOSE:** Record this visit’s clinical work.

**WHO DOES IT:** Doctor.

Consultation flow: **Review → Vitals → Consultation → Previous visits → Diagnose → Order → Prescribe → Admission**

### What is shown

| Section | What you do |
|---------|-------------|
| **Review** | See allergies, known diagnoses, and medications. **Record**, edit, or remove allergies here (patient-wide, not visit-specific) |
| **Vitals** | Record **outpatient** vitals when an open OPD visit is selected |
| **Consultation** | Chief complaint, complaint in your own words, duration, history of present illness, clinical notes |
| **Previous visits** | Visit list and previous encounter type and date. Note text is not available in this view |
| **Diagnosis** | Search and record diagnosis |
| **Orders** | Laboratory orders and results; radiology orders and reports |
| **Prescribe** | Search medicines and prescribe. If allergies are recorded, a warning is shown. It does not block the prescription. |
| **Admission** | **Admit Patient** — decision only. Nursing assigns the bed |

**Not currently available in this release** on this screen:

- Examination
- Review of Systems
- Past Medical History, Medication History, Family History, Social History
- Refer / Follow-up as a disposition
- Doctor discharge decision
- **Open full chart** (available on Nursing, Laboratory, and Pharmacy patient screens)

**STEP-BY-STEP**

1. Confirm patient and visit.
2. Record complaint, history, and notes.
3. Record outpatient vitals if needed (open OPD visit required).
4. Record diagnosis.
5. Order laboratory or imaging tests if needed.
6. Prescribe if needed.
7. Select **Save consultation**.

**Admitted patients:** If the patient already has a bed, you do **not** start another visit to prescribe or order tests. Those actions use the current admission.

**WHAT HAPPENS AFTER SAVING:** Notes, vitals (OPD), diagnoses, and prescriptions for this visit are stored. Payment is **not** required to save.

**COMMON ERRORS:** *Visit has not started* — Reception has not started a visit (outpatient). *This patient is waiting for a bed* — Nursing must assign a bed before inpatient orders. *Medications unavailable* / search unavailable — try again; if it persists, contact Hospital Admin.

**WHAT TO DO IF SOMETHING FAILS:** For outpatients, do not start a second visit yourself unless you have Reception access. Ask Reception to start the correct visit. For admitted patients, do not start an outpatient visit just to prescribe.

**SECURITY NOTES:** Do not save on the wrong visit. Previous-visit encounter lines do not show note text.

---

## Outpatient vitals versus inpatient vitals

| | Outpatient (this screen) | Inpatient (ward) |
|--|--------------------------|------------------|
| Who records | Doctor, on an open OPD visit | Nurse, during an active admission |
| Who reviews | Doctor | Doctor **reads only** on consultation when the patient is admitted |
| If you select an inpatient visit | The OPD vitals card is hidden | Inpatient vitals panel is read-only |

Doctors do **not** have Nursing write permission. Do not ask a nurse to change a time. Time is recorded automatically.

---

## Laboratory orders and results

**PURPOSE:** Order hospital laboratory tests and later review results.

**WHO DOES IT:** Doctor orders. Laboratory processes. Accountant collects the fee.

**STEP-BY-STEP**

1. In **Orders**, search the hospital laboratory list.
2. Add tests and submit. A laboratory fee is sent to Accounts.
3. Tell the patient that fees are paid at Accounts.
4. When Laboratory has released a result, it appears under **Laboratory results**.

**WHAT HAPPENS AFTER SAVING:** The order exists for Laboratory. Processing happens in laboratory processing, not on this screen. Results return here when released.

**COMMON ERRORS:** Result still empty — the specimen may not have been processed yet. *Laboratory orders unavailable* / *Laboratory results unavailable* — reload; if it continues, tell Hospital Admin.

**WHAT TO DO IF SOMETHING FAILS:** Check Laboratory. Do not invent a result. Do not enter results in Hospital EMR.

**SECURITY NOTES:** Payment is not required to place the order. **Paid does not mean the result is ready.**

---

## Radiology orders and reports

**PURPOSE:** Request an approved hospital examination and later read the report.

**WHO DOES IT:** Doctor orders. Radiology sets price and writes the report.

**STEP-BY-STEP**

1. In **Orders**, choose the hospital ultrasound or radiography name.
2. Submit. Imaging fees are paid at Accounts.
3. Read **Radiology reports** when Radiology has saved a report.

**WHAT HAPPENS AFTER SAVING:** Radiology sees the examination. Images are **not** shown in Hospital EMR in this release.

**COMMON ERRORS:** *Radiology reports unavailable* or *No report recorded for this examination.*

**WHAT TO DO IF SOMETHING FAILS:** Ask Radiology. Do not treat a missing image viewer as a failed order.

**SECURITY NOTES:** You do not collect imaging payment.

---

## Prescriptions

**PURPOSE:** Prescribe medication for this visit, or for the current admission if the patient is already on the ward.

**Lifecycle in this release:**

```text
Doctor prescribes
    → prescription / drug order
    → bill created for Accounts
    → Accountant collects payment
    → Pharmacy sees Ready to dispense
    → Pharmacy dispenses
    → patient receives the medicine
```

If the patient is later admitted, scheduled inpatient doses appear on Nursing **MAR**. That is **administration**, not dispensing. Pharmacy still dispenses the supply.

**When-needed (PRN) medicines are not added to the scheduled medication sheet.**

**COMMON ERRORS:** Expecting Pharmacy to dispense before payment. The system blocks unpaid dispensing.

---

## Admission

**PURPOSE:** Ask Nursing to admit the patient.

**WHO DOES IT:** Doctor.

**STEP-BY-STEP**

1. Open **Admission**.
2. Select **Admit Patient**. Copy: *The doctor decides to admit. Nursing assigns the bed. This does not collect payment.*

**WHAT HAPPENS AFTER SAVING:** *Admission requested. Nursing will assign a bed.* You do not choose the bed.

**WHAT TO DO IF SOMETHING FAILS:** Check Nursing Admissions. Do not invent a bed assignment.

After admission, on consultation you can **read** nursing notes, inpatient vitals, and MAR. You cannot record them.

---

## Consultation fee

On an active visit, the doctor can **Create consultation fee** in naira. Status **UNPAID** / **PAID**. Copy: *Please proceed to the cashier.*

You cannot collect payment. An unpaid fee does **not** block saving the consultation.

---

## Inpatient visibility

When the patient is admitted (or after discharge, for history):

- Inpatient vitals — **read only**
- Nursing notes — **read only**
- MAR — **read only**

Nursing notes after discharge remain readable to the doctor even when Nursing can no longer add a note.

---

## What the doctor cannot do

- Collect payment
- Assign, transfer, or discharge a bed (Nursing)
- Record inpatient vitals, nursing notes, or MAR
- Enter laboratory results
- Dispense medicines
- Change department catalogue prices
- Open Hospital Administration analytics
