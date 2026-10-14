# User roles and permissions

This matrix is from **server rules** in this release, not from a hidden menu. If the screen hides a button but the server allows it, the server wins. If the screen shows a link but the server refuses, the server wins.

Related: [Hospital Admin](DEPARTMENT_GUIDE_HOSPITAL_ADMIN.md) · [Department pricing](DEPARTMENT_PRICING.md)

Unauthenticated requests: **Sign in required.** Everything below is **NO**.

---

## How access is granted

Hospital Admin assigns **departments** on Staff accounts. That grants the hospital role for that desk.

**SuperAdmin** (technical) may open every department and is treated as a departmental actor on many server paths (including catalogue price writes).

**Hospital Admin** opens Administration and may set accommodation daily prices. They cannot write Reception, Laboratory, or Pharmacy catalogue prices.

Frontend Pharmacy and Radiology switches for SuperAdmin are offered on the department switcher; the server also accepts SuperAdmin on those APIs.

---

## Capability key

| Value | Meaning |
|-------|---------|
| **YES** | Allowed on the server for that job |
| **NO** | Refused |
| **READ ONLY** | Can view, cannot change |
| **OWN DEPT** | Only that department’s list |
| **N/A** | Not a function of this release |

**DELETE/VOID** of clinical notes, vitals, and MAR is **NO** for everyone (immutable). Radiology cannot cancel an order from the Radiology desk.

**APPROVE** of laboratory results is **not in Hospital EMR**. Validation is laboratory processing.

---

## Matrix

| Capability | SuperAdmin | Hospital Admin | Reception | Doctor | Nurse | Laboratory | Pharmacy | Accountant | Radiology |
|------------|:----------:|:--------------:|:---------:|:------:|:-----:|:----------:|:--------:|:----------:|:---------:|
| Open own department | YES | YES (Admin) | YES | YES | YES | YES | YES | YES | YES |
| Open other operational departments | YES | NO | NO | NO | NO | NO | NO | NO | NO |
| Register / edit demographics | YES | NO | YES | NO | NO | NO | NO | NO | NO |
| Start visit | YES | NO | YES | NO | NO | NO | NO | NO | NO |
| Create registration card charge | YES | NO | YES | NO | NO | NO | NO | NO | NO |
| Consultation write (notes, OPD vitals, diagnosis, Rx, lab/rad order) | YES | NO | NO | YES | NO | NO | NO | NO | NO |
| Patient allergies **write** | YES | NO | NO | YES | YES | NO | NO | NO | NO |
| Patient allergies **read** | YES | NO | NO | YES | YES | NO | YES | NO | NO |
| Admit decision | YES | NO | NO | YES | NO | NO | NO | NO | NO |
| Assign / transfer / discharge bed | YES | NO | NO | NO | YES | NO | NO | NO | NO |
| Nursing notes / inpatient vitals / MAR **write** | YES | NO | NO | NO | YES | NO | NO | NO | NO |
| Nursing notes / inpatient vitals / MAR **read** | YES | NO | NO | YES | YES* | NO | NO | NO | NO |
| Laboratory board | YES | NO | NO | NO | NO | YES | NO | NO | NO |
| Enter lab result in Hospital EMR | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| Dispense | YES | NO | NO | NO | NO | NO | YES | NO | NO |
| Collect payment | YES | NO | NO | NO | NO | NO | NO | YES | NO |
| Radiology price / report | YES | NO | NO | NO | NO | NO | NO | NO | YES |
| Reception card prices | YES | READ ONLY | YES | NO | NO | NO | NO | READ ONLY | NO |
| Laboratory test prices | YES | READ ONLY | NO | NO | NO | YES | NO | READ ONLY | NO |
| Pharmacy drug prices | YES | READ ONLY | NO | NO | NO | NO | YES | READ ONLY | NO |
| Accommodation tariffs | YES | YES | NO | NO | NO | NO | NO | NO | NO |
| Hospital overview | YES | YES | NO | NO | NO | NO | NO | NO | NO |
| Staff activity | YES | YES | NO | NO | NO | NO | NO | NO | NO |
| Staff accounts / department access | YES | YES | NO | NO | NO | NO | NO | NO | NO |
| Set / replace staff attendance code | YES | YES | NO | NO | NO | NO | NO | NO | NO |
| View staff log (Admin → Log) | YES | YES | NO | NO | NO | NO | NO | NO | NO |
| Create Hospital Administrator | YES | NO | NO | NO | NO | NO | NO | NO | NO |
| Patient Account (money view) | YES | YES† | YES | YES | YES | YES | YES | YES | YES |
| Delete / void clinical records | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| Refund | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

\* Nurse reads notes on the **active** admission. After discharge, Nursing may be unable to load notes; the doctor can still read history.

† Hospital Admin can open Patient Account if they also open a patient workspace; they do not collect payment.

Pharmacy **Receive / Adjust stock** needs the extra inventory right. Without it: view and dispense only.

---

## Unauthenticated

VIEW, CREATE, EDIT, DELETE, APPROVE, DISPENSE, ADMINISTER, PRICE MANAGEMENT, ANALYTICS, AUDIT, STAFF ADMIN: **NO**.
