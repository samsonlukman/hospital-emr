# Clinical medication implementation

Date: **19 Aug 2026**.

This phase repairs the Doctor medication **read** path and adds the smallest OpenMRS Drug Order **prescribe** workflow. Pharmacy dispensing, Odoo, Atomfeed, laboratory, radiology, notes, emergency, and inpatient MAR were not redesigned.

Related: `CLINICAL_WRITE_API.md`, `CLINICAL_INVESTIGATION.md`, `PHARMACY_UI_IMPLEMENTATION.md`.

---

## 1. Existing medication source

The source of truth is **OpenMRS Drug Orders**.

Live representation (Bahmni):

- Nested `drugOrder` plus flattened fields on `GET /openmrs/ws/rest/v1/bahmnicore/drugOrders/active?patientUuid=`
- `{ visitDrugOrders: [...] }` on `GET /openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive?patientUuid=`

Each order is linked in OpenMRS to:

| Link | How it appears |
|---|---|
| Patient | `patientUuid` on the request; patient on the order |
| Visit | `visit.uuid` on prescribedAndActive wrappers |
| Encounter | `encounterUuid` when present |
| Provider | `provider.name` when present |
| Order type | `Drug Order` |
| Drug | OpenMRS `drug` (`uuid`, name, strength, form) |

Pharmacy and Doctor both ultimately read this OpenMRS Drug Order. Pharmacy's **queue** additionally joins Odoo `sale.order.line.external_order_id` to the OpenMRS order UUID for payment and dispense. Doctor does **not** call the Pharmacy queue.

---

## 2. Why Doctor previously showed empty medications

The consultation screen called:

```
GET /openmrs/ws/rest/v1/bahmnicore/drugOrders?patientUuid=
```

On this installation that unfiltered list returns **`[]`** for patients who still have real orders (Tunde ORD-2, Adaeze ORD-3, Aisha ORD-4, John ORD-1).

Pharmacy does **not** use that list. Ready to Dispense reads Odoo lines keyed by OpenMRS order UUID, then loads `GET /order/{uuid}` and `GET /bahmnicore/drugOrders/{uuid}`. The Pharmacy patient helper already used `/drugOrders/active`.

So the Doctor list was empty because of the **wrong Bahmni list endpoint**, not because OpenMRS had no orders, and not because Pharmacy had a second medication database.

Aisha's order is past `autoExpireDate`, so `/active` is also empty for her. `prescribedAndActive` still returns ORD-4. The Doctor read now merges both.

---

## 3. Read-path fix

Doctor, Nursing, and Radiology `fetchDrugOrders` now:

1. `GET …/drugOrders/prescribedAndActive?patientUuid=`
2. `GET …/drugOrders/active?patientUuid=`
3. Flatten nested `drugOrder`
4. Deduplicate by order UUID
5. Map clinical fields only

The consultation **Medications** table shows:

Drug · Dose · Route · Frequency · Duration · Status

Status is **clinical** only:

| OpenMRS | Shown |
|---|---|
| `dateStopped` or action `DISCONTINUE` | Stopped |
| `autoExpireDate` in the past | Expired |
| otherwise | Ordered |

**Dispensed is not shown** merely because a Drug Order exists. Hospital EMR Pharmacy records dispense on the Odoo picking, not on the OpenMRS `Dispensed` order attribute. Joining that Pharmacy/Odoo state onto the Doctor chart would mix ledgers. If OpenMRS later stores a true dispensed attribute, it can be used then.

UUIDs, order numbers, Atomfeed, sale orders, and invoice numbers are not shown on the Doctor screen.

---

## 4. Drug catalogue source

Existing OpenMRS drug catalogue. Search:

```
GET /openmrs/ws/rest/v1/drug?q=
```

Dose units, routes, frequencies, duration units, dispensing units, and instruction phrases come from:

```
GET /openmrs/ws/rest/v1/bahmnicore/config/drugOrders
```

No Hospital EMR drug table. Retired catalogue rows are omitted. If a medicine is missing from this catalogue, it is a catalogue-content issue, not something Hospital EMR invents.

Live search for `para` includes Paracetamol strengths already configured (including a test 500 mg tablet). Dose/route/frequency are **not** stored as a second catalogue; they are chosen from the Bahmni config names (`Tablet`, `Oral`, `Twice a day`, `Days`, …).

---

## 5. Prescription UI

Consultation → **Medications** → search medicine → dose, route, frequency, duration, quantity, optional instruction → **Add to prescription** → review → **Prescribe**.

There is no Pay, Cash, Bank, journal, receipt, or dispense control on this screen.

An open visit is required. Hospital EMR does not silently start a visit or encounter only to prescribe. Saving uses the same `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` path as vitals and diagnosis (`drugOrders[]` on the existing consultation encounter POST). Bahmni may attach a Consultation encounter on that visit, as it already does for other consultation writes.

---

## 6. OpenMRS Drug Order creation

Payload shape (names from live config, not the older `Tablet(s)` / `Day(s)` example):

```json
{
  "careSetting": "OUTPATIENT",
  "drug": { "uuid": "<drug-uuid>" },
  "orderType": "Drug Order",
  "dosingInstructionType": "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions",
  "dosingInstructions": {
    "dose": 1,
    "doseUnits": "Tablet",
    "route": "Oral",
    "frequency": "Twice a day",
    "asNeeded": false,
    "administrationInstructions": "{\"instructions\":\"As directed\"}",
    "quantity": 10,
    "quantityUnits": "Tablet",
    "numberOfRefills": 0
  },
  "duration": 5,
  "durationUnits": "Days"
}
```

IPD visit type uses `careSetting: INPATIENT`. Emergency is not redesigned; if an emergency visit is open, the existing encounter POST is used without an emergency bypass.

Validation (plain language, only against configured options):

- Choose a medicine.
- Enter a dose.
- Choose how the medicine is given.
- Choose how often the medicine is given.
- Enter how long the medicine should be taken.
- Enter a quantity.

Double submit is blocked with an in-flight lock and disabled buttons. There is no second prescription ledger or client-generated order UUID.

---

## 7. Patient / visit / encounter linkage

A prescription is posted only when:

- patient UUID is the open chart
- an **open visit** exists on that patient
- the signed-in user has a provider record

Those values go on the existing Bahmni encounter POST (`patientUuid`, `visitUuid`, `providers[]`, location, consultation encounter type). No extra Hospital EMR prescription row.

---

## 8. Permissions

Existing OpenMRS / Hospital EMR privileges were not widened.

| Role | View medications | Prescribe | Dispense | Collect payment |
|---|---|---|---|---|
| Doctor (`app:clinical`) | yes | yes, via consultation encounter POST | no | no |
| Pharmacy | yes, existing queue / patient chart | no | yes, existing Pharmacy workflow | no |
| Reception | no prescribe UI | no | no | no |
| Nursing | yes, read-only chart list | no | no | no |
| Accountant | no prescribe UI | no | no | yes, existing payment |

---

## 9. Pharmacy integration

Expected downstream path (unchanged):

Doctor → OpenMRS Drug Order → existing Atomfeed → Pharmacy/Odoo → invoice → Accountant payment → Ready to Dispense → Dispense

This phase did **not** create a live test Drug Order, so **end-to-end Atomfeed → Pharmacy was not verified here**.

Implementation is complete, but live end-to-end prescription → Atomfeed → Pharmacy verification requires an isolated test prescription.

---

## 10. Payment separation

Clinical does not collect payment for medicines. Consultation billing is unchanged. Pharmacy still dispenses only through the existing paid / ready path.

---

## 11. Browser tests

Account: `doctor.abikan` / `Admin123`.

Checked against existing patients who already had OpenMRS Drug Orders (no new clinical writes):

1. Login → Clinical. Pass.
2. Today's Patients still loads (five OPD visits from 19 Aug 2026). Pass.
3. Search still opens a patient (Tunde ABC200006, Aisha ABC200011). Pass.
4. Consultation still opens. Pass.
5. Medications table shows existing orders: Tunde **Paracetamol 500 mg · 1 Tablet · Oral · Twice a day · 5 Days · Ordered**. Aisha **Paracetamol 500 mg — TEST · Expired** (no longer treated as empty). Pass.
6. No UUID / invoice / sale-order / OpenMRS language on the Medications section. Pass.
7. Prescribe form is available when a visit is open; search for `para` returns the existing catalogue (Paracetamol 500/650 mg, injection, suppositories, TEST tablet). Pass.
8. Validation: **Choose a medicine.** when Add to prescription is used without a drug. Pass.
9. No Pay or dispense controls on Clinical. Pass.
10. Pharmacy (`pharmacy.abikan`): queue still shows Tunde UNPAID; Clinical hash is denied. Accountant (`accountant.abikan`): payment workplace still loads; Clinical hash is denied. Nursing (`nurse.abikan`): ward board still loads; Clinical hash is denied. Pass.

Prescribe **submit** was not clicked against a live patient.

---

## 12. npm test

Pass. 53 tests in `abikan-shell` (`todaysPatients`, `pharmacyView`, `hashRoute`, `drugOrderMap`).

---

## 13. npm build

Pass. `tsc --noEmit && vite build`. Bundle `index-DzzoG0Zw.js`.

---

## 14. Data changed

**None** in this phase. Existing patients, prescriptions, Pharmacy/Odoo invoices, stock, OpenELIS, and PACS were not modified.

---

## 15. Known limitations

- The unfiltered Bahmni `GET …/drugOrders?patientUuid=` remains empty on this installation; Hospital EMR no longer uses it for display.
- Doctor status is clinical (Ordered / Stopped / Expired). Pharmacy payment and dispense states stay on Pharmacy.
- OpenMRS `orderAttributes.Dispensed` is not written by Hospital EMR Pharmacy, so it is not used as a clinical “Dispensed” flag.
- Quantity is suggested only for day- and week-based frequencies from the existing frequency-per-day config. Other duration units must be entered by the doctor.
- Emergency prescribing is not a separate workflow. Inpatient MAR / administration charting is not in this phase.
- Catalogue completeness is whatever OpenMRS already contains.

---

## 16. Next recommended phase

After an isolated test prescription (if product owners want live Atomfeed confirmation): laboratory ordering, or inpatient MAR, as separate phases. Do not fold those into this medication foundation.
