# Hospital EMR — User Manual

This manual describes **Hospital EMR as it exists in the frozen hospital UAT release** (`v1.0.0-uat`). It is for hospital staff and trainers.

It is not a product brochure. If something is not available in this release, this package says so.

**Release:** `v1.0.0-uat` · commit `2ea80c40c02cd42aa33fba47a0aa9dc1cc7d9ff6`

---

## What is Hospital EMR?

Hospital EMR is the hospital’s daily work system for Hospital EMR.

Staff sign in once and open **their department**. They register patients, see today’s visits, record consultations, order tests and medicines, nurse admitted patients, dispense paid prescriptions, collect payment, and review hospital activity.

Hospital EMR is the **staff-facing workflow layer**. It does not replace the hospital’s clinical and financial records. Those remain in the systems already used for the chart, laboratory processing, billing, and imaging.

| What staff use | What it is for |
|----------------|----------------|
| **Hospital EMR** | Department screens, hospital language, daily steps, department pricing, cashier, ward board, MAR, analytics |
| **Clinical chart engine** | Patient identity, visits, diagnoses, prescriptions, observations, admissions |
| **Laboratory processing** | Specimen collection, accession, testing, result entry, validation |
| **Billing and stock** | Invoices, payments, receipts, pharmacy stock movements |
| **Imaging archive** | Scan files, when a modality is connected. **Images are not shown inside Hospital EMR in this release.** |

Staff should think in hospital tasks: register, consult, collect specimen, dispense, collect payment. They should not need to know the names of the engines behind the screens.

---

## Who uses it

| Department (staff name) | Typical work in Hospital EMR |
|-------------------------|------------------------|
| **Reception** | Find or register a patient, start a visit, bill a registration card, set card prices |
| **Clinical (Doctor)** | Today’s patients, consultation, diagnosis, laboratory and imaging orders, prescriptions, admit decision |
| **Nursing** | Ward board, assign / transfer / discharge, nursing notes, inpatient vitals, medication administration |
| **Laboratory** | See ordered tests, payment state, open laboratory processing, set test prices |
| **Pharmacy** | See prescriptions, dispense after payment, catalogue and drug prices, inventory when permitted |
| **Accountant** | Find a patient, collect payment, print or open a receipt |
| **Radiology** | Worklist, set an examination price, write a report |
| **Hospital Admin** | Staff accounts, department access, hospital overview, staff activity |
| **SuperAdmin** | Technical hospital-wide access, including accommodation prices and every department |

An account only opens the departments assigned to it. Signing in does not let a nurse collect payment or a doctor change laboratory prices.

---

## How the hospital works in Hospital EMR

### Clinical workflow

1. Reception finds or registers the patient and starts a visit.
2. The doctor opens that visit, records the consultation, and may diagnose, order tests or imaging, prescribe, or request admission.
3. Laboratory, Pharmacy, and Radiology work from those orders.
4. The doctor reviews results and reports on the same visit.
5. If admitted, Nursing assigns a bed and records notes, vitals, and scheduled medicines. The doctor can prescribe and order tests on that admission without starting another visit.
6. Nursing discharges the patient and frees the bed.
7. The visit and records remain available for later care.

Payment is **not** required before the doctor can save a consultation or place an order. Unpaid work is visible. Collection happens at **Accountant**.

### Financial workflow

1. A department creates a **charge** (registration card, consultation fee, laboratory fee, imaging price, pharmacy prescription, accommodation).
2. That charge becomes a bill the cashier can collect.
3. Accountant records **payment**.
4. The department screen then shows **Paid** (or pharmacy **Ready to dispense**).
5. Completing the service is a separate step (dispense, process a specimen, write a report).

**Paid does not mean the work is finished.**

Changing today’s catalogue price does **not** change a bill already created.

New departmental bills use **naira (₦)**. The financial company currency may still be US dollars. Older accommodation bills that were in dollars stay in dollars. See [BILLING_AND_PAYMENTS.md](BILLING_AND_PAYMENTS.md).

### Administrative workflow

Hospital Admin creates and disables staff accounts, assigns departments, and reviews hospital counts and staff-administration activity.

Hospital Admin does **not** process specimens, write clinical notes, or collect payment (unless that person also has those department rights).

**System Settings** is not available in this release.

---

## How information moves (staff view)

```text
Patient arrives
    → Reception: find or register, start visit, card fee
    → Clinical: consultation, orders, prescription, admit if needed
        → Laboratory: see order → process in laboratory processing → result returns
        → Pharmacy: wait for payment → dispense
        → Radiology: price and report (images not in Hospital EMR)
    → Doctor reviews results and reports
    → Nursing: bed, notes, vitals, scheduled medicines
    → Nursing: discharge
    → Accountant: collect any unpaid bills
    → Records remain on the patient
```

Only steps that this release supports are listed. Details are in [CLINICAL_WORKFLOWS.md](CLINICAL_WORKFLOWS.md).

---

## Signing in

1. Open the hospital Hospital EMR address on a supported browser.
2. Enter **your hospital username** and **your own password**.
3. Select **Sign in**.
4. Hospital EMR opens **your department**. You do not pick a room or ward as a workplace.

Wrong username or password: **Could not sign in** — *Incorrect username or password.*

If the network cannot be reached: **Unable to connect** — try again. If that continues, tell Hospital Admin.

**Do not share accounts. Do not use another person’s password. Do not use development passwords on the hospital system.**

Sign out when you leave the desk.

---

## Finding a patient

Most departments use the header search:

**Search by name, hospital number, or phone** (type at least two characters).

Always confirm **name and hospital number** before you record, order, dispense, administer, or collect money.

---

## Patient Account

**Patient Account** is a read-only money view: billed so far, already received, still unpaid, and department bills.

Reception, Clinical, Nursing, Laboratory, Pharmacy, Radiology, and Accountant can open it when they can already open that patient. **Only Accountant collects payment.**

---

## Open full chart

Some department patient screens offer **Open full chart**. That opens the full clinical chart for extra detail.

Use it when you need the wider chart. Daily work stays in Hospital EMR. Do not treat extra chart screens as Hospital EMR department procedures.

**Open full chart** is not shown on the Doctor consultation screen in this release. It is available on Nursing, Laboratory, and Pharmacy patient screens.

---

## What staff should never do

- Share a username or password
- Register a new patient without searching first
- Record work on the wrong hospital number
- Change times on vitals or medication administration (time is recorded automatically)
- Bypass payment to dispense (the system blocks unpaid dispensing)
- Enter or invent laboratory results in Hospital EMR (results are entered in laboratory processing)
- Dispense a medicine from the ward MAR, or administer a dose from Pharmacy
- Delete or “fix” records in hidden systems
- Use development passwords on the hospital server

---

## Known limitations (this release)

These are accepted UAT limits, not hidden defects.

- A **new** laboratory result should be processed during hospital UAT. Do not rely only on an older result from another environment.
- The laboratory board can take several seconds to load.
- New departmental bills use naira. The company currency may still be US dollars. Older accommodation invoices in dollars stay in dollars.
- Nursing **Diagnoses** may show as unavailable.
- Care plan and intake/output are not available and are not shown. Nursing tasks only list real ward work (bed, first vitals, MAR, first note). Doctor and Nursing can record patient allergies on the shared clinical chart.
- SuperAdmin can still change department catalogue prices. Hospital Admin and SuperAdmin can change accommodation tariffs; existing bills stay at the amount captured when they were created.
- Wards without a configured accommodation tariff show **0** until a price is set.
- When-needed (PRN) medicines are **not** added to the scheduled medication sheet.
- Radiology **images are not shown in Hospital EMR**.
- **System Settings** is not currently available in this release.
- Doctor **Refer**, **Follow-up disposition**, and **doctor discharge decision** are not currently available in this release. Nursing performs discharge from the ward.
- Examination, Review of Systems, Family History, and Social History are **not currently available** on the Doctor consultation screen.
- Cashier **refunds** are not currently available in this release.
- Four laboratory tests remain unordered from Hospital EMR (Inorganic Phosphate, Testosterone, Progesterone, Estradiol) because they have no safe hospital catalogue mapping.

---

## Department manuals

| Manual | Audience |
|--------|----------|
| [Reception](DEPARTMENT_GUIDE_RECEPTION.md) | Front desk |
| [Doctor](DEPARTMENT_GUIDE_DOCTOR.md) | Clinical |
| [Nursing](DEPARTMENT_GUIDE_NURSING.md) | Ward |
| [Inpatient / ward](DEPARTMENT_GUIDE_INPATIENT.md) | Shared ward operations |
| [Laboratory](DEPARTMENT_GUIDE_LABORATORY.md) | Laboratory |
| [Pharmacy](DEPARTMENT_GUIDE_PHARMACY.md) | Pharmacy |
| [Accountant](DEPARTMENT_GUIDE_ACCOUNTING.md) | Cashier / accounts |
| [Radiology](DEPARTMENT_GUIDE_RADIOLOGY.md) | Imaging desk |
| [Hospital Admin](DEPARTMENT_GUIDE_HOSPITAL_ADMIN.md) | Administration |

## Other guides in this package

| Document | Use |
|----------|-----|
| [UAT Quick Reference](UAT_QUICK_REFERENCE.md) | One-page printout |
| [Clinical workflows](CLINICAL_WORKFLOWS.md) | Journey diagrams |
| [Billing and payments](BILLING_AND_PAYMENTS.md) | Charges, bills, payment |
| [Roles and permissions](USER_ROLES_AND_PERMISSIONS.md) | Who can do what |
| [Troubleshooting](TROUBLESHOOTING.md) | When something goes wrong |
| [System architecture](SYSTEM_ARCHITECTURE.md) | How the stack fits together (technical) |

## Hospital install and UAT (already published)

Do not treat these as staff desk manuals. They remain the install and sign-off set.

- [Hospital UAT checklist](HOSPITAL_UAT_CHECKLIST.md)
- [Hospital deployment](HOSPITAL_DEPLOYMENT.md)
- [Hospital server installation](HOSPITAL_SERVER_INSTALLATION.md)
- [Deployment secrets](DEPLOYMENT_SECRETS.md) (variable names only)
- [Department pricing](DEPARTMENT_PRICING.md)
- [Hospital overview analytics](ADMIN_ANALYTICS.md)
- [Inpatient implementation notes](INPATIENT_IMPLEMENTATION.md)
