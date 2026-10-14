# Consultation save — visit-window fix

Date: **19 Aug 2026** (Africa/Lagos).

Related: `CONSULTATION_SAVE_500_INVESTIGATION.md`.

This change only stops Hospital EMR from posting a Consultation encounter whose datetime is before the visit start. It does not change payment, Odoo, prescriptions, orders, notes, or visit records.

---

## Root cause

OpenMRS rejects `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` when:

`encounterDateTime < visit.startDatetime`

Hospital EMR set `encounterDateTime` to **now**. Ibrahim Musa’s open OPD visit starts **08:40 Africa/Lagos**. A save around **02:55–03:05** Africa/Lagos produced OpenMRS `ValidationException` and HTTP **500**. No encounter was stored.

## Why it was not a payment problem

- Save does not read PAID / UNPAID.
- Save does not call Odoo or the consultation-fee API.
- Chinedu’s chart was saved earlier **while UNPAID**.
- Ibrahim’s fee was already **PAID**; the 500 still happened because the visit start was in the future.

Payment remains Accountant-only. Clinical documentation must not depend on payment.

---

## Behavior before

1. Doctor opens an open visit (including one that starts later today).
2. Save is enabled once vitals, a diagnosis, or a prescription is drafted.
3. Hospital EMR POSTs `bahmniencounter` with `encounterDateTime = now`.
4. If now is before visit start, OpenMRS returns HTTP 500.
5. The doctor could see a system error. No encounter was created.

## Behavior after

1. Hospital EMR compares **now** with the visit’s OpenMRS `startDatetime`.
2. If now is **before** visit start:
   - **Save consultation** stays disabled.
   - The doctor sees: *Visit has not started yet. Please wait until the visit starts before saving.*
   - No `bahmniencounter` POST is sent.
3. If now is **at or after** visit start: existing save behaviour is unchanged (`encounterDateTime` remains now; no clamp).
4. PAID / UNPAID still does not affect save.

The visit start is not edited. A new visit is not started automatically.

---

## Timezone handling

Hospital zone: **Africa/Lagos** (UTC+1, no daylight saving).

Visit start comes from OpenMRS as an absolute instant, usually `YYYY-MM-DDTHH:mm:ss.SSS+0000`. `parseOpenmrsDateTime` normalises `+0000` to `+00:00` then compares instants.

`now < start` does not depend on the browser’s display timezone once both values are instants. Tests construct “now” as Africa/Lagos wall times (`+01:00`) so the Ibrahim 08:40 case is explicit.

Hospital EMR does **not** rewrite `encounterDateTime` to the visit start.

---

## User-facing message

```
Visit has not started yet. Please wait until the visit starts before saving.
```

No OpenMRS, HTTP, or 500 language.

---

## Tests

`src/services/openmrs/visitWindow.test.ts`

| Case | Result |
|---|---|
| now 03:00 Africa/Lagos, start 08:40 | save blocked |
| now 08:39:59 Africa/Lagos | save blocked |
| now 08:40:00 Africa/Lagos | save allowed |
| now 09:15 Africa/Lagos | save allowed |
| January 08:40 Africa/Lagos = 07:40 UTC | same offset (no DST) |
| OpenMRS `+0000` vs Lagos `+01:00` | same instant |

Also: `npm test` (full suite) and `npm run build`.

---

## Data safety

This fix does not create or modify patients, visits, encounters, invoices, or payments. Ibrahim’s visit start remains 08:40 Africa/Lagos.

Browser checks (19 Aug 2026, ~03:45 Africa/Lagos), existing records only:

| Check | Result |
|---|---|
| Ibrahim Musa, visit 08:40, fee PAID | Warning shown. Save disabled. No `bahmniencounter` POST. Open visit still has **zero** encounters. Start time unchanged. |
| Chinedu Okonkwo, visit already started | No visit-not-started warning. Save copy is the previous “Add vitals…” hint. Save stays disabled until there is a draft. **Not** posted. |
| Today's Patients | Still lists today’s OPD visits |
| Patient search | Chinedu found |
| Vitals / Diagnosis / Consultation fee / Admit Patient | Present. No Pay button |
| Nursing on `#/doctor` | Access denied |
| Doctor on pharmacy / nursing / accountant / reception | Access denied |

No new `POST …/bahmniencounter` in OpenMRS access logs after this fix.

---

## Known limitations

- A patient can appear on **Today’s Patients** before the visit clock time. Save waits until that time.
- Doctors cannot document before a scheduled visit start. Starting the visit at actual arrival (`Start OPD visit`) already uses now and is unaffected.
- The guard does not change visit stop handling. Closed visits still require an open visit, as before.
- Prescription **E2E** is still pending and was not run in this task. The same visit-window guard applies to that save path so it cannot POST before visit start.
