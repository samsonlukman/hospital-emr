# Hospital staff UAT checklist

Do **not** run this against real patients. Use synthetic names (for example **ABIKAN UAT TEST PATIENT**) on a hospital UAT environment with non-development passwords.

Do not use the current development database as UAT.

Each row: role that performs it, expected result, pass/fail.

---

## Access and safety

| Check | Role | Expected |
|-------|------|----------|
| Sign in with department account | Each department | Opens that department, not another |
| Doctor cannot open Administration analytics/audit | Doctor | Denied / returned to Clinical |
| Nurse cannot open Administration analytics/audit | Nurse | Denied |
| Laboratory / Pharmacy / Accounts cannot open Administration | Those roles | Denied |
| Unauthenticated request to admin APIs | — | Sign-in required |
| Sign out | Any | Session ends |

---

## Reception → Registration

| Check | Role | Expected |
|-------|------|----------|
| Register a **synthetic** patient | Reception | Hospital number issued; no engine jargon on screen |
| Start an outpatient visit (not IPD) | Reception | Visit type is outpatient |
| Find the patient by name / hospital number | Reception | Correct person |

---

## Doctor → Consultation

| Check | Role | Expected |
|-------|------|----------|
| Open today’s patients / the synthetic visit | Doctor | Correct visit, not another patient’s |
| Record consultation notes | Doctor | Saved on that visit |
| Record diagnosis | Doctor | Saved on that visit |
| Prescribe medication | Doctor | Drug order on that visit |
| Place a laboratory order | Doctor | Lab order placed (OpenMRS order) |
| Request admission if in scope | Doctor | Admission decision recorded |
| Open full chart when needed | Doctor | Chart opens; staff wording not “Open in Bahmni Clinical” |

---

## Nursing → Inpatient

| Check | Role | Expected |
|-------|------|----------|
| Assign bed | Nursing | Occupancy reflects assignment |
| Write a nursing note | Nursing | Note stored; immutable after save (per current product) |
| Record vitals | Nursing | Valid ranges enforced |
| See medication schedule | Nursing | Schedule for active admission |
| Record MAR administration | Nursing | Outcome stored for that slot |
| Doctor can **read** notes/vitals/MAR | Doctor | Read only where designed |
| Nurse cannot administer after discharge | Nursing | Blocked |

Do not discharge important fixtures from other environments. On UAT, only discharge the synthetic admission created for this test.

---

## Laboratory

| Check | Role | Expected |
|-------|------|----------|
| Worklist shows the synthetic order | Laboratory | Correct patient, visit, order |
| Open order in Hospital EMR | Laboratory | Same identities |
| Process in OpenELIS (UAT) | Laboratory | Processing completes |
| Result returns to Hospital EMR/clinical | Laboratory / Doctor | Result visible for that order |
| Laboratory does not collect payment | Laboratory | No cashier actions in Lab |

---

## Pharmacy

| Check | Role | Expected |
|-------|------|----------|
| Prescription appears | Pharmacy | Correct patient and medicines |
| Payment state visible | Pharmacy / Accounts | Unpaid vs ready as designed |
| Dispense when allowed | Pharmacy | Movement completes |
| Stock not invented | Pharmacy | Catalogue/inventory behaviour unchanged |

---

## Billing

| Check | Role | Expected |
|-------|------|----------|
| Invoice for the synthetic visit | Accounts | Billed amount in naira |
| Collect payment | Accounts | Posted payment; not “paid” inferred only from invoice state |
| Receipt | Accounts | Hospital receipt, not engine jargon |

---

## Discharge and history

| Check | Role | Expected |
|-------|------|----------|
| Discharge synthetic admission | Nursing | Bed freed; history remains |
| Historical notes/vitals/MAR | Nursing / Doctor | Still readable for that stay |
| Outpatient history | Doctor | Visit remains findable |

---

## Administration

| Check | Role | Expected |
|-------|------|----------|
| Hospital overview loads | Hospital Admin | Aggregates only; no patient names |
| Date filter Today / This month | Hospital Admin | Ilorin dates; occupancy labelled current |
| Staff activity | Hospital Admin | Staff-admin events; secrets redacted |
| Create a UAT staff account | Hospital Admin | Account works; password not visible later |
| Disable that account | Hospital Admin | Cannot sign in |
| Doctor still denied analytics | Doctor | Denied |

---

## Known limitations (do not treat as pass/fail failures)

These are current product limits. Record them; do not hide them.

| Limitation | What staff may see |
|------------|--------------------|
| Fresh laboratory result | Process a **new** result during this UAT. Do not rely only on an older result from another environment. |
| Laboratory board speed | The laboratory board can take several seconds to load. |
| Currency on bills | New departmental bills use naira. The financial company currency may still be US dollars. Older accommodation invoices that were in dollars stay in dollars. |
| Nursing Diagnoses | Diagnoses may show as unavailable. |
| Nursing Care plan / intake | Not available and not shown. |
| SuperAdmin prices | SuperAdmin can still change department catalogue prices. Hospital Admin sets accommodation tariffs. |
| Ward tariffs | Wards without a configured tariff show **0** until a price is set. |

---

## Sign-off

| Department | Name | Date | Pass |
|------------|------|------|------|
| Reception | | | |
| Clinical | | | |
| Nursing | | | |
| Laboratory | | | |
| Pharmacy | | | |
| Accounts | | | |
| Administration | | | |

Record every synthetic patient/order created and whether it was discharged.
