# Inpatient and ward operations

This guide is the shared ward picture. Detailed Nursing steps are in [Nursing](DEPARTMENT_GUIDE_NURSING.md). Doctor steps are in [Doctor](DEPARTMENT_GUIDE_DOCTOR.md).

---

## Who does what

| Role | What they do on an admission |
|------|------------------------------|
| **Doctor** | Clinical decisions, orders, prescriptions, **Admit Patient** |
| **Nurse** | Assign / transfer / discharge bed, notes, vitals, MAR |
| **Reception** | Registration and starting an **Admission** visit when that is the front-desk path |
| **Accountant** | Collect accommodation and other bills |
| **Pharmacy** | Dispense paid medicines (not MAR) |
| **Laboratory** | Specimen and results in laboratory processing |
| **Radiology** | Price and report (images not in Hospital EMR) |
| **Hospital Admin** | Staff and counts — not bedside care |

Do not assign a job the application does not support.

---

## Admission

```text
Doctor: Admit Patient
    → Admission requested
    → Nursing: Assign Bed
    → Occupied
```

Reception may also start an **Admission** visit and choose a ward. That does not replace Nursing bed assignment.

The doctor does not choose the bed and does not collect payment.

---

## Ward and bed

Nursing **Ward Board** shows ward, room, and bed as **Available** or **Occupied**.

**Transfer** moves an occupied patient to another bed. There is no transfer history list.

**Discharge** frees the bed. Nursing performs discharge. Doctor discharge decision is **not currently available in this release**.

Unpaid accommodation does not block assign, transfer, or discharge.

---

## Inpatient chart

Nursing opens the inpatient chart for notes, vitals, and MAR.

The doctor opens the same patient in Clinical and **reads** notes, vitals, and MAR. The doctor does not write those.

After discharge, history remains. Nursing cannot add new notes, vitals, or administrations.

---

## Vitals and MAR

See [Nursing](DEPARTMENT_GUIDE_NURSING.md).

- Time is automatic.
- Each vitals recording is new; history is kept.
- MAR is **scheduled inpatient** doses only. PRN is not on the sheet.
- Pharmacy dispense and MAR administer are different.

---

## Laboratory, pharmacy, accommodation

Laboratory and imaging orders still come from the doctor. Processing and reporting stay in those departments.

Pharmacy dispenses paid prescriptions. The ward does not dispense from MAR.

Accommodation: Hospital Admin sets the daily naira price. Nursing assigns the bed. The system creates the bill at the current price. Later price changes do not rewrite that bill. Old dollar bills stay in dollars. Tariff **0** means the ward is not configured yet.

---

## Discharge

```text
Nursing: confirm identity
    → Discharge
    → Bed released
    → Accountant: collect remaining bills
    → Records remain
```

Do not discharge a patient from another environment’s important fixtures during training. On UAT, discharge only the synthetic admission created for the test.
