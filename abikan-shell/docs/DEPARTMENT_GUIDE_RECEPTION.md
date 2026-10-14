# Reception — Department guide

This guide describes Reception as it works in this release. Payment is collected at Accountant, not at Reception.

Related: [User manual](ABIKAN_EMR_USER_MANUAL.md) · [Billing](BILLING_AND_PAYMENTS.md) · [Department pricing](DEPARTMENT_PRICING.md)

---

## What Reception is for

Reception finds or registers the patient, starts the right kind of visit, bills the registration card, and sends the patient to Clinical, Emergency, or the ward as needed.

**Screens:** Dashboard · Search Patients · Register Patient · Today's Visits · Pricing · Patient Accounts (search)

---

## Logging in

**PURPOSE:** Open the Reception desk.

**WHO DOES IT:** Staff with Reception or Registration access.

**STEP-BY-STEP**

1. Open Hospital EMR and enter your hospital username and password.
2. Select **Sign in**.
3. You open **Reception**. You do not pick a room.

**WHAT HAPPENS AFTER SAVING:** Your session stays in Reception until you sign out or switch departments (only if your account has more than one).

**COMMON ERRORS:** *Could not sign in* — incorrect username or password.

**WHAT TO DO IF SOMETHING FAILS:** Try again. If it still fails, contact Hospital Admin. Do not use someone else’s account.

**SECURITY NOTES:** Use only your own password. Sign out when you leave the desk.

---

## Finding an existing patient

**PURPOSE:** Open the correct person. Avoid a second registration.

**WHO DOES IT:** Reception.

**STEP-BY-STEP**

1. Use **Search by name, hospital number, or phone** (type at least two characters).
2. Confirm **name and hospital number**.
3. Open the patient.

**Search Patients** and **Patient Accounts** focus the same search.

**WHAT HAPPENS AFTER SAVING:** The patient record opens. No new hospital number is created.

**COMMON ERRORS:** Two people with similar names; phone not stored so phone search finds nothing.

**WHAT TO DO IF SOMETHING FAILS:** Search again by hospital number. If you still cannot find them, do not register until you have checked with a supervisor.

**SECURITY NOTES:** Never open a record that is not this patient.

---

## Registering a new patient

**PURPOSE:** Create a hospital record and assign a hospital number.

**WHO DOES IT:** Reception.

**STEP-BY-STEP**

1. Search first.
2. Open **Register Patient**.
3. Choose **Individual Card** or **Family Card**. The fee is billed after the visit starts. Reception does not collect payment.
4. Enter first name, last name, sex, date of birth or age, and contact and address as required.
5. Watch **Existing patients** after you type three or more characters of the first and last name. Open an existing record if it is the same person.
6. Select **Save**.

You do not type the hospital number. It is assigned when the patient is saved.

**WHAT HAPPENS AFTER SAVING:** A hospital number is assigned (for example an ABC number). You can start a visit and create the card fee.

**COMMON ERRORS:** *Similar patients found* — the system found possible matches.

**WHAT TO DO IF SOMETHING FAILS:** Open the existing record unless you are sure this is a new person. Use **Register anyway** only when a supervisor agrees it is a different person.

**SECURITY NOTES:** Do not invent a hospital number. Do not register a duplicate to “make a new visit.”

---

## Starting a visit

**PURPOSE:** Record why the patient is here today.

**WHO DOES IT:** Reception.

**STEP-BY-STEP**

1. Open the patient.
2. Select **Start visit**.
3. Choose one:

| What you select | Meaning |
|-----------------|---------|
| **General Outpatient** | Regular outpatient consultation |
| **Follow-up** | Returning for previous treatment or condition |
| **Emergency** | Urgent care |
| **Admission** | Patient is being admitted — select the **ward** shown on the screen |

4. Confirm.

**WHAT HAPPENS AFTER SAVING:** The visit is created. You may see **Visit successfully created** and a visit number. Today's Visits lists visits that **started today**.

Outpatient and follow-up visits started today appear on the doctor’s **Today's Patients**. Emergency and admission visits do not appear on that outpatient list.

**COMMON ERRORS:** *This patient already has an open visit.* Start another only if they are arriving for a different kind of care.

**WHAT TO DO IF SOMETHING FAILS:** Check Today's Visits and the patient screen. Do not create extra visits to “reset” the list.

**SECURITY NOTES:** Do not start a visit on the wrong patient.

---

## Registration card fee

**PURPOSE:** Send the Individual Card or Family Card bill to Accountant.

**WHO DOES IT:** Reception, after a visit exists.

**STEP-BY-STEP**

1. On the patient screen, open **Registration card fee**.
2. Confirm Individual Card or Family Card.
3. Select **Create registration fee** and confirm. Copy: *This sends the bill to Accountant. Reception does not collect payment.*

**WHAT HAPPENS AFTER SAVING:** Status shows **Not billed yet**, **UNPAID**, or **PAID**. When paid: *Payment received* — the receipt is on Patient Account.

One fee per visit. Submitting again reuses the existing charge.

**COMMON ERRORS:** Trying to collect cash in Reception.

**WHAT TO DO IF SOMETHING FAILS:** Direct the patient to Accountant. Open **Patient Account** to see whether the bill exists.

**SECURITY NOTES:** Reception cannot collect payment. Do not record payment on paper as if Hospital EMR received it.

---

## Card pricing

**PURPOSE:** Set the selling price of Individual Card and Family Card for **new** fees.

**WHO DOES IT:** Reception (read and write). Accountant and Hospital Admin can view. SuperAdmin can also change these prices.

**STEP-BY-STEP**

1. Open **Pricing**.
2. Change the naira amount if required.
3. Save. Add a reason when asked.

**WHAT HAPPENS AFTER SAVING:** New card fees use the new price. Price history stores the old price, new price, who changed it, and when.

**COMMON ERRORS:** Expecting an old unpaid or paid bill to change.

**WHAT TO DO IF SOMETHING FAILS:** That is correct behaviour. Yesterday’s bill keeps yesterday’s amount. See [Department pricing](DEPARTMENT_PRICING.md).

**SECURITY NOTES:** Do not change prices unless you are authorised. Changing a price does not rewrite existing bills.

---

## Directing the patient and Patient Account

After the visit starts, send the patient to Clinical (or Emergency / the ward as started).

**Patient Account** is read-only: billed so far, already received, still unpaid. Tell the patient to pay at **Accountant**.

---

## What Reception can and cannot do

| Can | Cannot |
|-----|--------|
| Search, register, edit name and contact | Collect payment |
| Start the four visit types above | Create a consultation fee |
| Create the registration card fee | Diagnose, prescribe, order tests, or dispense |
| Change Individual Card and Family Card prices | Change laboratory or pharmacy prices |
| Open Patient Account (read only) | Edit clinical notes, vitals, or nursing records |

---

## Known Reception limits

- There is no separate waiting-room queue. **Today's Visits** are visits that started today.
- An unpaid card fee does **not** block the doctor from opening the chart.
- Phone search only works when a phone number is stored.
