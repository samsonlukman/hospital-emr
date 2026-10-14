# Consultation Save HTTP 500 — investigation

Date: **19 Aug 2026** (Africa/Lagos). Investigation complete.

**Fix implemented 19 Aug 2026:** see `CONSULTATION_SAVE_FIX.md`. Hospital EMR no longer POSTs when `now < visit.startDatetime`. The visit start was **not** changed. Timestamps are **not** clamped.

Status labels: **CONFIRMED** · **INFERRED** · **UNKNOWN**

Related: `CONSULTATION_SAVE_FIX.md`, `CONSULTATION_BILLING_IMPLEMENTATION.md`, `CLINICAL_WRITE_API.md`, `CLINICAL_VISIT_QUEUE_IMPLEMENTATION.md`.

**No data was created or modified** during this investigation. Evidence is from existing Tomcat / Hospital EMR API logs plus read-only GETs.

---

## 1. Exact reproduction

**CONFIRMED** from existing logs. The failing POST was **not** replayed.

| Item | Value |
|---|---|
| Staff action | Doctor chart → **Save consultation** |
| Patient | Ibrahim Musa, MRN **ABC200008** |
| Patient UUID | `0288bf42-11f4-48c8-a076-ea1e7f7ee8dd` |
| Open visit | `481610eb-78c8-488c-9ec4-f35a3e88f86e` |
| Visit start | `2026-08-19T07:40:00.000+0000` (08:40 Africa/Lagos) |
| Visit stop | `null` (still open) |
| Location | OPD-1 |
| Consultation fee | **PAID**, charge already exists |
| Consultation encounter on that visit | **none** (`encounters: []`, fee payload `encounter: null`) |
| Fail times (UTC) | `01:55:47`, `01:55:54`, `01:56:56`, `01:57:08`, `01:57:13`, `02:05:36` |
| Fail times (Lagos) | ~02:55–03:05, 19 Aug 2026 |

Sequence on this patient (Hospital EMR API access log, all **200** except an unrelated admit call):

1. `POST /openmrs/abikan-api/consultation/patient/{uuid}/charge` → **200** (fee created in Odoo)
2. Accountant payment (already **PAID** when re-read)
3. Doctor **Save consultation** → OpenMRS `POST …/bahmniencounter` → **500**
4. Chart reload GETs for the same patient UUID immediately after the 500s

Frontend action that triggers the failing call:

`ConsultationWorkspace.handleSaveConsultation` → `saveConsultation()` → `openmrsPost(BAHMNI_ENCOUNTER_URL, payload)`.

Save is enabled when there is an **open visit** and the draft has vitals, a diagnosis, or a prescription. **PAID / UNPAID is not checked.**

Authenticated user: Tomcat access logs do not record the OpenMRS username. **INFERRED** `doctor.abikan` (Doctor workspace is the only Hospital EMR UI that POSTs this endpoint from the browser; subsequent GETs match this chart). Credentials are not recorded here.

This investigation did **not** click Save again and did **not** POST `bahmniencounter`.

---

## 2. Endpoint

| Item | Value |
|---|---|
| HTTP method | **POST** |
| Path | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` |
| Client | Browser → reverse proxy → OpenMRS (`172.19.0.15` in Tomcat access log) |
| Hospital EMR API on this path | **Not involved** |

Not used on Save:

- `GET/POST /openmrs/abikan-api/consultation/patient/{uuid}`
- `POST /openmrs/abikan-api/consultation/patient/{uuid}/charge`
- Accountant payment endpoints
- Odoo XML-RPC

Tomcat access log (redacted host only):

```
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter HTTP/1.1  500  19878
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter HTTP/1.1  500  20102
```

Response size ~20 KB matches an OpenMRS REST error body that includes a stack trace (`error.detail`).

---

## 3. Request flow

```
Doctor UI — Save consultation
  → GET /openmrs/ws/rest/v1/provider?user={userUuid}   (provider UUID)
  → POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
       → BahmniEncounterController.update
       → BahmniEncounterTransactionServiceImpl.save
       → EmrEncounterServiceImpl.save
       → Encounter.save / ValidateUtil.validate
       → ValidationException
  → HTTP 500 JSON to the browser
  → OpenmrsRequestError → "Save consultation" error banner
```

**Where the 500 originates**

| Layer | Involved? | Notes |
|---|---|---|
| **OPENMRS ERROR** | **Yes — origin** | `org.openmrs.api.ValidationException` on encounter datetime vs visit window. `BaseRestController.handleException` maps it to **HTTP 500** on this install (not 400). |
| **BAHMNI ERROR** | Wrapper only | Bahmni REST controller and encounter-transaction service call OpenMRS `saveEncounter`. They do not invent the validation rule. |
| **ABIKAN ERROR** | Payload cause, not the HTTP 500 process | Hospital EMR sends `encounterDateTime = now` (`formatOpenmrsDateTime()`). Hospital EMR API returned **200** on fee GET/POST. No Hospital EMR 500 on consultation-fee routes at this time. |
| **ODOO ERROR** | **No** | Odoo is not on the save path. Fee was already PAID. |
| **NETWORK/PROXY ERROR** | **No** | Proxy forwarded OpenMRS 500. Connection succeeded. |

Failure occurs **during OpenMRS encounter validate/save**, before a new encounter UUID exists. Logs show `Encounter: [(no ID) …]`. Nothing is persisted.

---

## 4. Payload structure (redacted)

Built by `buildConsultationPayload` in `src/services/openmrs/clinicalEncounter.ts`. `encounterUuid` is **not** sent.

```json
{
  "patientUuid": "<patient uuid>",
  "visitUuid": "<open visit uuid>",
  "visitType": "OPD",
  "encounterTypeUuid": "d34fe3ab-5e07-11ef-8f7c-0242ac120002",
  "encounterDateTime": "<browser now as ISO-8601 with +0000>",
  "locationUuid": "<session location, OPD-1 in the failures>",
  "providers": [{ "uuid": "<provider uuid>" }],
  "observations": [ /* vitals concepts + numeric values */ ],
  "bahmniDiagnoses": [ /* optional coded diagnoses */ ],
  "orders": [],
  "drugOrders": [ /* optional; empty array if none */ ]
}
```

**Not in the payload:** payment status, invoice id, sale order, Odoo ids, consultation-fee amount, journal.

`encounterDateTime` defaults to `new Date().toISOString()` with `Z` replaced by `+0000`. The Doctor save handler does not pass a custom datetime.

---

## 5. HTTP status

**CONFIRMED:** OpenMRS Tomcat `localhost_access_log.2026-08-19.txt`:

- Failing saves: **500**
- A successful save the same morning (different patient): **200**

OpenMRS REST on this Bahmni stack treats `ValidationException` as an unhandled server error (500), not a client 400.

---

## 6. Server traceback / error

OpenMRS log (same message on every failing POST):

```
ERROR - BaseRestController.handleException(124) |2026-08-19T01:55:47,950|
'Encounter: [(no ID) Wed Aug 19 01:55:47 UTC 2026 Consultation OPD-1 15 (no Form)
 num Obs: [obs id is null] num Orders: 0 ]'
 failed to validate with reason:
 encounterDatetime: The encounter datetime should be between the visit start and stop dates.
org.openmrs.api.ValidationException
  at org.openmrs.validator.ValidateUtil.validate(ValidateUtil.java:88)
  at … saveEncounter …
  at org.openmrs.module.emrapi.encounter.EmrEncounterServiceImpl.save
  at org.openmrs.module.bahmniemrapi.encountertransaction.impl.BahmniEncounterTransactionServiceImpl.save
  at org.bahmni.module.bahmnicore.web.v1_0.controller.BahmniEncounterController.update
```

`(no ID)` = create, not an update of a stored encounter row. Controller method name is `update`; it is the bahmniencounter POST save.

Obs counts on the failed creates:

| UTC | num Obs | num Orders |
|---|---|---|
| 01:55:47, 01:55:54 | 1 | 0 |
| 01:57:12, 02:05:36 | 8 | 0 |

UI would surface `error.message` (the ValidationException text) or `Request failed with status 500` via `messageFromOpenmrsBody`. That string is not hospital language. Not fixed in this investigation.

---

## 7. OpenMRS response

**CONFIRMED** HTTP **500**. Body was not captured from the browser. From OpenMRS REST behaviour and ~20 KB size, the JSON is the usual:

```json
{
  "error": {
    "message": "…encounterDatetime: The encounter datetime should be between the visit start and stop dates.",
    "detail": "<stack trace>"
  }
}
```

Exact JSON was not stored. **INFERRED** shape; **CONFIRMED** status, validator message, and stack.

No encounter UUID was created. Ibrahim’s open visit still has **zero** encounters.

---

## 8. Odoo involvement

**CONFIRMED: Odoo is not involved in the 500.**

Consultation fee is a **separate** path:

| Action | Endpoint | When |
|---|---|---|
| Read fee / PAID | `GET /openmrs/abikan-api/consultation/patient/{uuid}` | Chart load; **200** |
| Create fee | `POST …/charge` `{ visitUuid, requestId }` | Doctor confirms fee; **200** for Ibrahim |
| Pay | Accountant `POST /openmrs/abikan-api/accountant/payment` | Cashier only |

Idempotency key: `consultation:{visitUuid}`. The visit is the chargeable event. The Consultation encounter is expected **later**, on clinical save (`consultation.py` header comment). Fee code does **not** create, update, or require an encounter UUID.

Ibrahim after the 500s (read-only GET):

- `hasCharge: true`
- `paymentStatus: "PAID"`
- `encounter: null`
- `canCreateCharge: false`

Financial source of truth remains Odoo. There is no second Hospital EMR ledger on this path.

---

## 9. Whether PAID changes the behaviour

**CONFIRMED: payment status is not in the save payload and is not a save-time branch.**

`ConsultationWorkspace` never reads `paymentStatus` / `hasCharge` for Save. `canWrite` is only `Boolean(openVisit)`.

### Live comparison (read-only)

| | Ibrahim Musa ABC200008 | Chinedu Okonkwo ABC200004 | Samson Mamah Luk ABC200000 |
|---|---|---|---|
| Fee | **PAID** | **PAID** | **UNPAID**, no charge |
| Open visit start | **19 Aug 07:40 UTC (future at save time)** | 17 Aug 02:09 UTC (past) | 19 Aug 00:18 UTC (past at 01:49) |
| Consultation on that visit | **none** | `88c5772e-…` (saved **while UNPAID**, 17 Aug) | `42c197a0-…` saved **01:49 UTC today, HTTP 200** |
| Save at ~01:55 UTC | **HTTP 500** | Not retried here | Already succeeded |

Same-day **UNPAID, no charge** patients (Emeka ABC200010, Kemi ABC200013, Yusuf ABC200014, Chioma ABC200015) also have **future** visit starts and **no** Consultation encounter. This investigation did **not** POST to prove they would 500. **INFERRED:** they would fail the same OpenMRS visit-window check if saved before visit start.

**CONFIRMED** from billing docs: Chinedu’s chart **was saved while UNPAID**. Payment later marked INV/2026/00004 PAID and did not close the visit or encounter.

**Root correlation:** the PAID patient who failed had a **future-dated visit start** (seeded 08:40 Lagos). The doctor billed and paid that visit, then saved clinical data **before** 08:40. PAID is coincidental, not causal.

What actually differs for Ibrahim vs a working save:

- `visitUuid` (future start vs start already in the past)
- `encounterDateTime` (= now, which is **before** Ibrahim’s visit start)
- Not payment fields, not a different endpoint, not Odoo

---

## 10. Existing encounter state

**Ibrahim, open visit `481610eb-…`:** no encounters. Save is a **create**.

Older closed OPD visit (17 Aug) has Consultation `653f4572-…`. That visit is stopped. Hospital EMR binds Save to `visits.find(v => v.open)`, so that old UUID is **not** sent.

**Create vs update**

| Question | Finding |
|---|---|
| Does the UI send `encounterUuid`? | **No** |
| Do logs show an existing encounter id? | **No** — `(no ID)` |
| Is this an update of a paid encounter? | **No** |
| Duplicate Consultation on the same visit? | **No** — none exists on the open visit |
| Does fee code switch to update after PAID? | **No** — fee is not on the save path |

Bahmni may later reuse a Consultation on the same visit when one exists (documented for Chinedu). That path was not reached here.

---

## 11. Root cause

**CONFIRMED**

Hospital EMR sends `encounterDateTime = now`. OpenMRS requires:

> The encounter datetime should be between the visit start and stop dates.

Ibrahim’s open visit starts **07:40 UTC**. Saves ran **01:55–02:05 UTC**. `now` is **before visit start**. Validation fails. OpenMRS returns **500**. No encounter is written.

Open visit is defined in Hospital EMR as `stopDatetime` empty. A visit scheduled later today still counts as open, so Save is enabled.

---

## 12. CONFIRMED findings

1. HTTP **500** on `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` (Tomcat access log).
2. OpenMRS `ValidationException` on `encounterDatetime` vs visit start/stop.
3. Failure is a **create** (`no ID`), type Consultation, location OPD-1, patient internal id 15 = Ibrahim Musa.
4. Failed with 1 observation and with 8 observations; `num Orders: 0`.
5. Ibrahim’s open visit has **no** Consultation encounter after the failures.
6. Ibrahim’s consultation fee is **PAID**; fee GET/POST were **200**; Odoo is not called on Save.
7. Save payload has no payment / invoice / Odoo fields.
8. Doctor Save does not gate on PAID.
9. Chinedu was saved **UNPAID** on 17 Aug; that encounter still exists; that visit start is in the past.
10. Samson ABC200000 saved **200** at 01:49 UTC on a visit that started 00:18 UTC (before save). Fee UNPAID / no charge.
11. Hospital EMR API consultation-fee routes did not 500.
12. Architecture still matches: Doctor documents in OpenMRS; Doctor may create a fee; Accountant collects; Clinical only **reads** PAID. The 500 does **not** mean payment is required to save. It means the datetime is outside the visit window.
13. Doctor cannot collect payment, edit price, choose journal, or mark paid (those stay on Accountant). Doctor **can** create the consultation fee (`POST …/charge`) — unchanged, not the 500.

---

## 13. INFERRED findings

1. Browser user was `doctor.abikan`.
2. 1-obs failures were a single vital or equivalent; 8-obs failures were the full vitals set. Diagnosis-only vs vitals both hit the same datetime validator.
3. Empty save was not attempted (UI requires vitals, diagnosis, or prescription).
4. Other today’s seeded OPD visits (starts 08:15–10:20 UTC, UNPAID, no encounter) would 500 if saved before those starts.
5. Saving Chinedu **now** would succeed (visit start in the past, still open). Not posted.
6. OpenMRS REST error JSON includes the validator message and a stack in `error.detail`.
7. `visitType: "OPD"` hardcoded in the payload is unrelated for Ibrahim (open visit is OPD).
8. `drugOrders` were empty or not persisted as orders (`num Orders: 0`). Prescription payload is not required to explain the 500.
9. Clamping `encounterDateTime` to visit start when start is still in the future might hit a **second** OpenMRS rule (no future encounters). Not tested.

---

## 14. UNKNOWN findings

1. Exact browser JSON body (not captured).
2. Proven username on the Tomcat request (not in access log).
3. Whether `bahmniDiagnoses` were present on the 1-obs calls.
4. Whether a future `encounterDateTime` equal to visit start would be accepted **before** wall-clock visit start.
5. Whether Bahmni SPA would fail the same way on Ibrahim (one 500 also came from `172.19.0.27` at 01:57:08 with the same validator — possibly another client, same rule).
6. Unrelated `POST …/admit-decision` **502** for Ibrahim — out of scope; not investigated; no data changed.

---

## 15. Recommended fix

Implemented in `CONSULTATION_SAVE_FIX.md` (19 Aug 2026). Summary of what was chosen:

**Do not** require PAID, call Odoo on save, invent a Hospital EMR ledger, or clamp `encounterDateTime` to visit start.

If `now < visit.startDatetime`, **do not call OpenMRS**. Show:

> Visit has not started yet. Please wait until the visit starts before saving.

If the visit has already started, keep the existing save path.

Clamping to visit start was rejected: it would invent a clinical timestamp and might hit a future-encounter validator.

---

## 16. Risks of the recommended fix

| Approach | Risk |
|---|---|
| Block save until visit start | Doctor cannot document at 03:00 for an 08:40 slot. Correct for OpenMRS; may surprise staff if the queue shows the patient as “today”. |
| Clamp to visit start | May fail a “no future encounter” rule; encounter time would not match when the doctor typed. |
| Move visit start to now | Changes clinical/visit data; **not** a save-path fix; forbidden during this investigation; wrong if start must remain the appointment time. |
| Require PAID to save | Violates billing/clinical separation; does not fix the validator; **must not** be done. |
| Send existing encounter UUID from a previous visit | Would attach data to the wrong visit. |

Queue UX: “Today’s patients” includes open visits whose start is later today. After the datetime guard, those rows should still be visible, but Save should explain the scheduled time.

---

## Security (item 10)

No permissions were changed.

| Actor | Still allowed | Still denied |
|---|---|---|
| Doctor | Save clinical documentation (once datetime is valid); create consultation fee | Collect payment, edit price, choose journal, mark invoice paid |
| Accountant | Collect payment | Clinical encounter save is not this workspace |

The current 500 does **not** come from a permission check.

---

## Billing / clinical separation (item 9)

Intended:

```
Doctor  → clinical encounter (OpenMRS)
Doctor  → consultation fee charge (Odoo sale + invoice)
Accountant → payment (Odoo PAID)
Clinical → reads PAID
```

**CONFIRMED** the implementation does not require payment to save, and save does not call Odoo. The PAID + 500 pairing is explained by a future visit start, not by a payment gate.

---

## Confirmation: no data changed

This investigation used:

- Docker / Tomcat / Hospital EMR API **log reads**
- Authenticated **GET** of patients, visits, encounters, fee status, system settings

It did **not**:

- POST `bahmniencounter`
- create or edit patients, visits, encounters, obs, diagnoses, orders
- create or edit invoices, payments, stock
- close or reopen visits
- change configuration
- implement the fix (that work is in `CONSULTATION_SAVE_FIX.md`; still no visit/encounter/invoice writes)
