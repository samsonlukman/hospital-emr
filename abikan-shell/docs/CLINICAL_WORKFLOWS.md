# Clinical and hospital workflows

These diagrams describe **this release only**. Steps that are not implemented are marked.

For staff how-to, use the department manuals. For money, use [BILLING_AND_PAYMENTS.md](BILLING_AND_PAYMENTS.md).

---

## 1. New patient

```text
Reception: Search first
    ↓ (no safe match)
Reception: Register Patient
    → choose Individual Card or Family Card
    → enter name, sex, birth date or age, contact, address
    → Save
    → hospital number is assigned
    ↓
Reception: Start visit
    ↓
Reception: Create registration fee (after a visit exists)
    ↓
Accountant: Collect payment when the patient is ready
    ↓
Direct the patient to Clinical (or Emergency / ward as started)
```

If similar patients appear, open the existing record unless you are sure this is a new person. See [Reception](DEPARTMENT_GUIDE_RECEPTION.md).

---

## 2. Returning patient

```text
Reception: Search by name, hospital number, or phone
    ↓
Open the existing patient
    ↓
Start a new visit only if they need a different kind of care
    ↓
Card fee is per visit when Reception creates it
    ↓
Clinical: Today's Patients (outpatient visits started today)
    or search if the visit type is Emergency or Admission
```

---

## 3. OPD consultation

```text
Reception starts General Outpatient or Follow-up
    ↓
Doctor: Today's Patients → open the name
    ↓
Review allergies / known problems (Doctor or Nursing can record a patient allergy)
    ↓
Record OPD vitals on this open outpatient visit (if needed)
    ↓
Chief complaint, history of present illness, clinical notes
    ↓
Diagnosis (optional)
    ↓
Laboratory and / or radiology orders (optional)
    ↓
Prescription (optional)
    ↓
Admit Patient (optional)
    ↓
Save consultation
    ↓
Create consultation fee (optional) → Accountant collects
```

**Not currently available on this screen:** Examination, Review of Systems, Past Medical History, Medication History, Family History, Social History, Refer, doctor follow-up disposition, doctor discharge decision.

---

## 3a. Inpatient clinical orders

An occupied admission already has a ward visit. The doctor does **not** start another outpatient visit to prescribe or order tests.

```text
Active admission (bed assigned)
    ↓
Existing inpatient visit + consultation
    ↓
Doctor: prescribe / laboratory / imaging
    ↓
Orders stay on that admission
    ↓
Medication schedule → Nursing MAR
Laboratory fee → Accounts → laboratory processing → result returns
```

If the patient is only waiting for a bed, inpatient orders wait until Nursing assigns one. Outpatient clinic visits still need an open outpatient visit.

---

## 4. Laboratory

```text
Doctor: Order → Laboratory → submit tests
    → laboratory fee is sent to Accounts
    ↓
Laboratory: Pending Orders (and patient search)
    ↓
Laboratory staff: Open laboratory processing
    → collect specimen, accession, test, enter result, validate
    (those steps are not done inside Hospital EMR)
    ↓
Result returns to Hospital EMR
    ↓
Doctor: Laboratory results on the same visit
```

Hospital EMR does **not** collect the specimen or enter the result. See [Laboratory](DEPARTMENT_GUIDE_LABORATORY.md).

A new result should be processed during hospital UAT.

---

## 5. Pharmacy

```text
Doctor: Prescribe
    ↓
Charge / invoice is created for the prescription
    ↓
Accountant: Collect payment (full payment)
    ↓
Pharmacy: Ready to Dispense
    ↓
Pharmacist: Confirm identity → Dispense
    ↓
Stock moves; status becomes Dispensed
    ↓
Patient receives the medicine at the pharmacy
```

Unpaid and partly paid prescriptions are **not** ready to dispense. This is not the same as Nursing MAR.

---

## 6. Admission

```text
Doctor: Admit Patient
    → "Admission requested. Nursing will assign a bed."
    ↓
Nursing: Admissions (Admit requested)
    ↓
Nursing: Assign Bed
    → inpatient stay starts
    → accommodation charge may be created
    ↓
Accountant: Collect accommodation when billed
```

Reception can also start an **Admission** visit and choose a ward. That is a Reception visit start, not the Doctor admit button.

Doctor does **not** choose the bed. Nursing does **not** decide the clinical admission.

---

## 7. Nursing (inpatient chart)

```text
Ward Board or Patients → open the patient
    ↓
Confirm name and hospital number
    ↓
Implemented:
    Nursing Notes
    Vitals
    Medication Administration (scheduled doses)
    Assign / Transfer / Discharge
    ↓
Coming soon (not stored):
    Nursing tasks
    Care plan
    Intake and output
```

---

## 8. Vitals

**Outpatient (Doctor)**

```text
Open OPD visit
    ↓
Consultation → Vitals
    ↓
Enter measurements → Save consultation
```

**Inpatient (Nursing)**

```text
Admitted patient with a bed
    ↓
Inpatient chart → Vitals → Record vitals
    ↓
Review and record
    → time and nurse are stored automatically
    → a new reading is added; earlier readings stay
```

Doctor can **read** inpatient vitals. Doctor cannot record inpatient vitals.

---

## 9. MAR (scheduled medication)

```text
Doctor prescribes an inpatient scheduled medicine
    ↓
Schedule / dose slots are prepared for the admission
    ↓
Nurse: Medication Administration
    ↓
Within the normal window: Administer (Given / Not done / Refused / Held)
    ↓
Outside the window: Administer outside scheduled window + reason
    ↓
Actual time is recorded automatically
```

When-needed (PRN) medicines are **not** added to the scheduled sheet. Pharmacy dispense is a different workflow.

---

## 10. Radiology

```text
Doctor: Order → Radiology → submit examination
    ↓
Radiology: Worklist
    ↓
Set price in naira (Accounts collects)
    ↓
Write or edit the report (free text)
    ↓
Doctor: Radiology reports on the visit
```

**Images are not currently available in Hospital EMR.** Connecting a scanner and viewing files needs hospital imaging setup outside this manual. Do not invent a PACS procedure from Hospital EMR.

---

## 11. Discharge

```text
Nursing: Ward Board (or Discharges list) → Discharge
    → confirm
    → bed is released
    ↓
Historical notes, vitals, and MAR remain readable
    (Nursing cannot add new notes / vitals / administrations after discharge)
    ↓
Doctor can still read historical inpatient records on the consultation
```

Doctor discharge decision is **not currently available**. Unpaid accommodation does **not** block discharge.

---

## 12. Billing and payment

```text
Department creates a charge
    ↓
Bill appears for Accountant
    ↓
Accountant: Collect payment → receipt
    ↓
Department screen shows Paid
    (Pharmacy: Ready to Dispense, then Dispense)
```

See [BILLING_AND_PAYMENTS.md](BILLING_AND_PAYMENTS.md).
