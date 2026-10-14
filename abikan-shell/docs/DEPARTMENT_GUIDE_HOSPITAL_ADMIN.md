# Hospital Admin — Department guide

This guide describes Hospital Administration as it works in this release.

Related: [Roles](USER_ROLES_AND_PERMISSIONS.md) · [Hospital overview](ADMIN_ANALYTICS.md) · [Deployment](HOSPITAL_DEPLOYMENT.md)

---

## What Hospital Admin is for

**Screens:** Dashboard · Analytics (Hospital overview) · Audit log (Staff activity) · Staff accounts · Department access · Accommodation Prices · System Settings (**Coming soon**)

Hospital Admin manages **staff and hospital counts**. It does not replace Reception, Clinical, Nursing, Laboratory, Pharmacy, Radiology, or Accountant.

---

## Who can open Administration

| Account | Access |
|---------|--------|
| **Hospital Administrator** | Home, staff accounts, department access, hospital overview, staff activity |
| **SuperAdmin** | All of the above, every department, and **Accommodation Prices** write |
| Doctor, Nurse, Laboratory, Pharmacy, Accountant | Denied unless they also have admin rights |

Frontend hiding is not enough. The server also requires the matching administration rights.

---

## Staff accounts

**PURPOSE:** Create and disable hospital users.

**WHO DOES IT:** Hospital Admin. Only SuperAdmin can create another Hospital Administrator.

**STEP-BY-STEP**

1. Open **Staff accounts**.
2. **Add staff**: full name, username, initial sign-in password (at least 8 characters), and account type.
3. Assign departments with the checkboxes. Do not invent extra technical rights here.
4. Save. The initial password is **not shown again** and is not stored on Staff activity.

**Clinical profile:** some departments need a clinical profile (**Ready**, **Clinical profile needed**, or **Not required**). The system links it when the department requires it.

You can disable or enable an account. A disabled account cannot sign in.

**SECURITY NOTES:** Give each person their own account. Do not reuse development passwords. Do not write passwords into email or this manual. Tell the staff member to change the initial password according to hospital policy.

---

## Department access

**Approved access only.** Departments and roles are the hospital options on the screen. Technical permissions cannot be assigned here.

Hospital Administrator rows cannot have department access changed here — that is technical support.

---

## Hospital overview (Analytics)

**PURPOSE:** See hospital-wide counts.

**WHO DOES IT:** Hospital Admin.

**STEP-BY-STEP**

1. Open **Analytics**.
2. Choose **Today**, **Yesterday**, **This week**, **Last week**, **This month**, **Last month**, or a custom range. Dates use **Ilorin time**.

| Label | Date filter? |
|-------|----------------|
| Patients registered | Yes |
| Outpatient visits (Reception subsection) | Yes |
| Consultations | Yes |
| Admissions | Yes |
| Discharges | Yes |
| Laboratory orders | Yes |
| Prescriptions | Yes |
| Dispensed | Yes |
| Billed | Yes (₦) |
| Collected | Yes (₦) |
| **Current occupancy** | **No — now** |
| **Current occupancy rate** | **No — now** |
| **Outstanding** | **No — now** |

**Current occupancy** and **Current outstanding** are **snapshots of now**. They do not mean occupancy or unpaid amounts as of the selected dates.

If a figure cannot be read, the screen shows **Unavailable**, not a fake zero.

These counts are **not** “revenue.” Billed, collected, and outstanding are bill totals.

**Not shown:** named patients, new versus returning split, aged receivables, historical occupancy.

---

## Staff activity

**PURPOSE:** See who changed staff accounts and access.

**Recorded:** created staff / hospital administrator, disabled or enabled account, updated / assigned / removed department access, linked clinical profile.

**Not recorded:** clinical chart views, patient care, laboratory processing, payments.

Passwords, cookies, and secrets are **not displayed**.

---

## Accommodation Prices

Hospital Admin and SuperAdmin set the **daily naira price** for each ward or room.

When Nursing assigns a patient to a bed, the system creates the accommodation bill using the **current** price at that moment. Changing a price later does **not** change bills already created. The next assignment or next applicable day uses the new price.

Wards without a tariff show **0** until configured. Nursing does not type a price and does not create the bill by hand.

---

## System Settings

**Not currently available in this release** (Coming soon).

---

## What Hospital Admin cannot do (unless also given that department)

- Collect payment
- Record clinical or nursing data
- Process specimens or dispense
- Change Reception / Laboratory / Pharmacy catalogue prices (view only)

Hospital Admin **can** change accommodation tariffs. SuperAdmin can also change department catalogue prices and accommodation tariffs. Use price changes carefully: they apply to future charges only.
