# Hospital EMR — UAT quick reference

Print this page. Release **v1.0.0-uat**. Use **synthetic** patients only. Do not use development passwords on the hospital server.

| Department | Primary responsibility | Main workflow |
|------------|------------------------|---------------|
| **Reception** | Registration and visits | Search → register if new → start visit → card fee → send to Clinical. Pay at Accountant |
| **Doctor** | Consultation, diagnosis, orders | Today's Patients → consult → diagnose / order / prescribe → Admit Patient if needed |
| **Nursing** | Ward, vitals, notes, MAR | Ward Board → assign bed → notes / vitals / scheduled MAR → discharge |
| **Laboratory** | Orders and results visibility | See order → process in laboratory processing → result returns to Doctor |
| **Pharmacy** | Dispense after payment | Paid → Ready to dispense → Dispense. Do not administer MAR |
| **Accountant** | Collect payment | Search → collect → receipt. Billed / collected / outstanding are bill totals, not “revenue” |
| **Radiology** | Price and report | Worklist → set naira price → write report. Images not in Hospital EMR |
| **Hospital Admin** | Staff and counts | Staff accounts · overview · staff activity. Occupancy and outstanding are **now** |
| **Inpatient** | Shared ward path | Doctor admits → Nurse beds and documents → Accountant collects accommodation |

## Safety

- Confirm name and hospital number every time.
- Do not share accounts.
- Do not change times (vitals and MAR are automatic).
- Do not dispense unpaid medication.
- Do not enter laboratory results in Hospital EMR.
- Pharmacy dispenses. Nursing administers scheduled inpatient doses. PRN is not on MAR.

## Money

New bills: **naira**. Old accommodation bills in dollars stay in dollars. Changing a price does not change an old bill.

## Known UAT limits

- Prove a **new** laboratory result here.
- Laboratory board can be slow.
- Nursing Diagnoses may be unavailable. Care plan and intake/output are not shown.
- Hospital Admin sets accommodation tariffs. Existing bills keep the amount captured at creation. SuperAdmin can still change department catalogue prices.
- Unconfigured ward tariff may be **0**.
- System Settings, doctor discharge decision, refunds, and radiology images: **not currently available in this release**.

Full manuals: start at [ABIKAN_EMR_USER_MANUAL.md](ABIKAN_EMR_USER_MANUAL.md). Sign-off: [HOSPITAL_UAT_CHECKLIST.md](HOSPITAL_UAT_CHECKLIST.md).
