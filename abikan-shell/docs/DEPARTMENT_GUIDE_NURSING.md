# Nursing — Department guide

This guide describes Nursing as it works in this release. It is a safety-critical document. Do not bypass identification, times, or administration windows.

Related: [Inpatient / ward](DEPARTMENT_GUIDE_INPATIENT.md) · [Doctor](DEPARTMENT_GUIDE_DOCTOR.md) · [Pharmacy](DEPARTMENT_GUIDE_PHARMACY.md)

---

## What Nursing is for

Nursing runs the ward: who is on a bed, who is waiting for a bed, notes, vitals, and scheduled medication administration.

**Screens:** Dashboard · Ward Board · Patients · Admissions · Transfers · Discharges · inpatient chart

Pharmacy **dispenses** medicine. Nursing **administers** scheduled inpatient doses. These are different jobs.

---

## Logging in

**PURPOSE:** Open the ward.

**WHO DOES IT:** Staff with Nursing access.

**STEP-BY-STEP**

1. Sign in with your hospital username.
2. **Nursing** opens. You do not pick a ward as a workplace.

**SECURITY NOTES:** Use only your account. Your name is recorded on notes, vitals, and administrations.

---

## Ward Board, Patients, Admissions

**PURPOSE:** See occupancy and open the right chart.

**WHO DOES IT:** Nursing.

**Dashboard** shows occupied beds, available beds, and patients waiting for a bed, plus ward overview counts.

**Ward Board** shows **Ward → Room → Bed → Patient**. Beds are **Available** or **Occupied**. Occupied beds open the chart and offer **Transfer** and **Discharge**. Available beds open **Assign Bed**.

**Patients** lists occupied patients and those with **Admit requested**.

**Admissions** lists patients the doctor has asked to admit. Nursing assigns the bed.

**Transfers** and **Discharges** are shortcuts for people **currently on a bed**. They are not a history list.

**STEP-BY-STEP (open a chart)**

1. Confirm name and hospital number.
2. Open the patient from the board or Patients.
3. Check **Ward**, **Bed**, and status (**Occupied**, **Admit requested**, or **Not admitted**).

**SECURITY NOTES:** Always match the person at the bedside to the hospital number on the screen.

---

## Assign bed, transfer, discharge

**PURPOSE:** Place the patient, move the patient, or free the bed.

**WHO DOES IT:** Nursing (bed assignment rights).

### Assign bed

1. Open **Admissions**, an available bed, or the patient chart.
2. Confirm **Admit requested** when the doctor has asked to admit.
3. Choose the ward and bed shown.
4. Select **Assign Bed**.

**WHAT HAPPENS AFTER SAVING:** The bed is occupied. You may see *Admitted to …* Accommodation billing may start. Nursing does not collect payment. Unpaid accommodation does **not** block assign.

If the bed was just taken: *This bed has just been assigned to another patient. Please choose another bed.*

You can assign from the chart in an emergency even if the doctor has not requested admit. Use that only when the hospital requires it.

### Transfer

1. From the occupied bed or Transfers, select **Transfer**.
2. Choose the new ward and bed.
3. Select **Transfer Patient**.

There is no separate transfer history screen.

### Discharge

1. Confirm identity.
2. Select **Discharge**. Confirm: *Discharge this patient and release their bed?*

**WHAT HAPPENS AFTER SAVING:** *Patient discharged. Bed released.* Historical notes, vitals, and MAR remain readable where the system allows. You cannot record new notes, vitals, or administrations after discharge.

Unpaid accommodation does **not** block discharge. Send the family to Accountant for any unpaid bills.

**WHAT NOT TO DO:** Do not discharge the wrong patient. Do not try to “delete” the stay.

---

## Inpatient chart

Header shows name, hospital number, age, ward, bed, and allergy line.

Sections that **work** in this release: **Alerts** (including allergies), current condition, **Vitals**, **Medication Administration (MAR)**, **Nursing tasks**, **Inpatient Nursing Notes**, doctor instructions (read-only), admission and discharge actions.

**Not currently available in this release:** Care plan and intake/output. Those modules are not shown.

**Diagnoses** may show **Diagnoses unavailable**. That is a known limit. Do not invent a diagnosis.

**Open full chart** opens the wider clinical chart. Daily ward work stays in Hospital EMR.

**Patient Account** is read-only.

---

## Allergies

**PURPOSE:** See and record substances the patient reacts to. The list belongs to the **patient**, not to one visit or one admission.

**WHERE TO VIEW:** Inpatient chart → **Alerts**, and the sticky header when you scroll. The doctor and pharmacy see the same list.

**WHO CAN CREATE OR EDIT:** Nursing and the doctor. Pharmacy can view and cannot change it. Reception, Laboratory, Accountant, and Radiology cannot record allergies.

**STEP-BY-STEP**

1. Open the inpatient chart → **Alerts**.
2. Confirm identity.
3. Select **Record allergy**.
4. Choose type (medicine, food, environment, or other).
5. Enter the substance. For a medicine you may search the catalogue or type the name.
6. Optionally add severity, reaction, and a comment.
7. Save. Use **Edit** or **Remove** only to correct that same allergy.

**WHAT HAPPENS AFTER SAVING:** The change is stored on the shared clinical chart. A later visit does not clear it.

**WHAT NOT TO DO:** Do not invent an allergy. Do not record it only in a nursing note.

---

## Nursing Notes

**PURPOSE:** Record an observation during this admission.

**WHO DOES IT:** Nursing, while the patient has an active bed and admission.

**STEP-BY-STEP**

1. Open the inpatient chart.
2. Confirm identity.
3. Select **+ Nursing Note**.
4. Write the observation, care, and response.
5. Select **Save Nursing Note**.

**WHAT HAPPENS AFTER SAVING:** The note is stored with **your name** and the **current date and time**, recorded automatically. You cannot edit or delete it. A later note does not replace an earlier one.

**WHO CAN READ:** Nursing during the active admission. The doctor can read current and historical notes.

After discharge, Nursing may see **Nursing notes unavailable** on the chart. The doctor can still read historical notes.

**COMMON ERRORS:** Saving a note on the wrong patient. Trying to change an old note.

**WHAT TO DO IF SOMETHING FAILS:** Write a new note. Do not ask anyone to change the time.

**SECURITY NOTES:** Time and author cannot be typed by you. Do not share an account so that another nurse’s name is recorded as yours.

---

## Vitals

**PURPOSE:** Record inpatient observations.

**WHO DOES IT:** Nursing during an active admission. Doctor reviews only.

**STEP-BY-STEP**

1. Open the inpatient chart → **Vitals**.
2. Confirm identity.
3. Enter the measurements you took.
4. Review warnings for unusual values. Unusual values can still be saved when they are true.
5. Confirm. Copy: observations are **added** and do **not** replace earlier readings.

### Measurements in this release

| Measurement | Unit |
|-------------|------|
| Temperature | °C |
| Pulse | bpm |
| Respiratory Rate | /min |
| Systolic blood pressure | mmHg |
| Diastolic blood pressure | mmHg |
| SpO₂ | % |
| Weight | kg |
| Height | cm |

BMI may display from weight and height. It is **calculated on screen and is not saved** as a stored observation.

Both systolic and diastolic must be entered together. Systolic must be higher than diastolic. Values outside the allowed range are refused.

**WHAT HAPPENS AFTER SAVING:** Time is recorded automatically. Each recording is a **new** observation. History is kept. Later measurements do not overwrite earlier ones.

After discharge you can read history. You cannot record new vitals (*Vitals can be recorded during an active admission*).

**OPD versus ward:** The doctor may record outpatient vitals on an OPD visit. Those are not the same as ward vitals. The condition summary may show a latest reading from a wider history; the **Vitals** section shows this admission’s recordings.

**WHAT NOT TO DO:** Do not change timestamps. Do not record another nurse’s work under your name.

---

## Medication administration (MAR)

**PURPOSE:** Give or document a **scheduled inpatient** dose.

**WHO DOES IT:** Nursing during an active admission.

```text
Doctor prescribes an inpatient medicine
    → the ward schedule is created from that order
    → the scheduled dose appears on MAR
    → Nurse administers (or records not given)
    → administration is stored on the shared clinical chart
```

Nursing **cannot** create a medication order from MAR. If the sheet is empty, the doctor has not prescribed a schedulable inpatient medicine, the order is when-needed (PRN), or the schedule could not be created.

**When-needed (PRN) medicines are not added to the scheduled medication sheet.** They cannot be administered from MAR in this release.

Outpatient-only orders and incomplete prescriptions also do not become scheduled slots.

### Window

Normal window: **30 minutes before** the scheduled time through **60 minutes after**.

- Inside the window: **Administer** for **Given** (note optional).
- Outside the window: use **Administer outside scheduled window**. A **reason is required**, including when the dose was given.
- **Not done**, **Refused**, and **Held** always need a reason.

**Actual time is recorded automatically.** You cannot type or change it. Scheduled time and actual time are stored separately.

### Outcomes

| You select | Meaning |
|------------|---------|
| **Given** | Dose administered |
| **Not done** | Dose not given |
| **Refused** | Patient refused |
| **Held** | Held |

A finished slot cannot be administered again. After discharge the sheet is **historical** — readable, no new administrations.

**Duplicate protection:** Repeating the same save does not create a second administration.

**Patient isolation:** A slot for another patient is refused (*This scheduled dose is for another patient*).

**COMMON ERRORS:** *This dose is outside the normal administration window.* *Medication administration unavailable.* Empty MAR because the order is PRN or not inpatient.

**WHAT TO DO IF SOMETHING FAILS:** Confirm you are on the correct patient and admission. Use the outside-window action with a true clinical reason when the time is outside the window. Do not invent a scheduled time. Do not administer from Pharmacy.

**SECURITY NOTES:** Do not bypass the window. Do not administer after discharge. Do not record a dose you did not give.

---

## Nursing tasks

**PURPOSE:** See what this admission still needs.

**WHAT GENERATES A TASK**

| Task | Source | Outstanding when | What you do | Complete when |
|------|--------|------------------|-------------|---------------|
| Assign a bed | Admission / stay | Doctor asked to admit and no bed is assigned | Admission → Assign Bed | The patient occupies a bed |
| Record vitals | Vitals on this admission | No vitals saved on this admission yet | Vitals → Record | At least one vitals set is saved |
| Administer scheduled medication | MAR | A scheduled dose is due in the normal window | Medication → Administer | That dose is recorded |
| Review a dose outside the window | MAR | A scheduled dose is early or late | Medication → Administer outside scheduled window | That dose is recorded |
| Write a nursing note | Nursing notes | No note on this admission yet | Notes → Save | At least one note is saved |

There is **no separate task list** stored in Hospital EMR. The list is built from the ward record each time you open it.

**WHAT “No nursing tasks waiting” MEANS:** First vitals, the first nursing note, and any due scheduled doses for this admission are complete. Later vitals, later notes, and later doses still belong in their own sections. The empty state is not a claim that the patient needs no further nursing care.

---

## What Nursing cannot do

- Collect payment
- Change accommodation tariffs or department catalogue prices
- Dispense from Pharmacy
- Write diagnoses or prescriptions
- Create a medication order from MAR
- Request admission (doctor) or process laboratory specimens
- Edit or delete saved notes, vitals, or MAR rows
- Administer PRN as scheduled MAR
- Backdate times

---

## Known Nursing limits

- Diagnoses may show unavailable
- Care plan and intake/output are not available and are not shown
- No transfer or discharge history list
- Ward and room may show the same name in assign/transfer
- Wards without an accommodation tariff show **0** until a price is set. Nursing does not enter a price. Hospital Admin sets the daily price. The bill created at assignment keeps that day’s amount.
