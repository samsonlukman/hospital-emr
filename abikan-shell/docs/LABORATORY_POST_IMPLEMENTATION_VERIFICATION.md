# Laboratory post-implementation verification

Date: **19–20 Aug 2026**. Verification and correction only. Radiology, Pharmacy implementation, and unrelated Clinical work were not started. The Laboratory workflow was not redesigned. No second result engine was added. No OpenMRS observations were written to fake a result.

Staff-facing screens were not given OpenMRS, Bahmni, Odoo, or laboratory-application names.

---

## 1. Catalogue verification

Live OpenMRS + runtime map vs hospital CSV:

| Check | Result |
|---|---|
| Hospital CSV rows | **80** |
| Map rows | **85** (80 plus priced-each expansions) |
| Runtime keys / orderables | **82** |
| Outsourced | **30** |
| `All_Tests_and_Panels` members | **82**, extra=[], missing=[] |
| Duplicate concept ids / S/Ns | none |
| Missing uuid or ₦ price | none |
| ₦1.00 placeholders | none |
| Combo skips | S/N **45** Hormonal Profile; **61** Total T3 & T4 as one line; **64** CA combo. Not invented as panels. |

**22** newly created concepts: Test or LabSet, datatype N/A, not retired, members only where the hospital name already listed them.

**Confirmed name-collision defect (not remapped in this pass):** S/N 42 Inorganic Phosphate, 56 Testosterone, 57 Progesterone, 58 Estradiol were bound to **Drug** concepts because the configure script matched any concept with the same name. No safe Test-class duplicate with the same fully specified name exists. Those four remain Drug-class orderables in the catalogue. The matcher now only reuses Test/LabSet names so this will not be repeated.

---

## 2. Price verification

Hospital CSV = Odoo Hospital Laboratory pricelist (currency **NGN**) = Clinical catalogue display. No USD in Clinical laboratory search. No ₦1.00 hospital laboratory products.

| Item | CSV | Clinical | Odoo |
|---|---|---|---|
| PCV | ₦1,500 | ₦1,500 | 1,500.00 |
| FBC | ₦5,000 | ₦5,000 | 5,000.00 |
| Clotting Profile (outsourced) | ₦15,000 | ₦15,000 · Outsourced | 15,000.00 |
| Microscopy MP | ₦1,500 | ₦1,500 | 1,500.00 |
| IGF-1 | ₦80,000 | (catalogue) | 80,000.00 |
| Urine Toxicology | ₦15,000 | ₦15,000 · Outsourced | 15,000.00 |

Accountant laboratory invoices use NGN (symbol may still print after the number). Unrelated pharmacy invoice INV/2026/00020 remains USD; it was not globally rewritten.

---

## 3. Clinical verification

`doctor.abikan` lands in **Clinical**. Patient search finds ABC200016. Existing chart still shows chief complaint, HPI, consultation note, vitals, diagnosis, prescription, admission, and consultation fee. **Open full chart** is the chart link. No Pay on the laboratory order panel.

Order → Laboratory:

- Catalogue search (FBC list includes ₦5,000 panel and outsourced clotting)
- Multi-select supported (search and add one or more tests)
- Submit copy: payment is not collected here
- New in-house order **ORD-10** saved on the existing Consultation encounter

---

## 4. Accountant verification

Previous ORD-8 path unchanged: **INV/2026/00021** ₦15,000 Laboratory **PAID** (receipt **PCSH1/2026/00009**). No second payment was taken.

New in-house charge: **INV/2026/00022** ₦1,500 Laboratory **UNPAID**. Left unpaid on purpose.

ORD-9 Malarial smear (duplicate in-house order during this pass) has no separate invoice.

---

## 5. Laboratory workspace verification

`lab.abikan` (and `abikan.lab`) can load the laboratory board. Dashboard / pending / processing / completed / search hashes stay in Laboratory (`#/lab…` aliases included). Unknown laboratory hashes stay in Laboratory, not Administration.

Board shows payment **UNPAID / PAID** and **Outsourced** where applicable. No cashier Pay. Laboratory can create a fee bill for Accounts; it cannot collect payment (`POST /accountant/payment` → **403**). SuperAdmin can open the board.

---

## 6. In-house test selected

**Microscopy MP** (hospital S/N 16), reused concept **Malarial smear** `32AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`.

Why this test: it is in-house, already in the laboratory application (test 849), already proven on ORD-5, and is not one of the 22 new concepts.

---

## 7. OpenMRS order result

Dedicated TEST patient **ABC200016** `f242364e-b70f-4fec-b29e-8ad4fbe147b5`

| Field | Value |
|---|---|
| Visit | `6478a94e-1657-4abe-9271-7cf92b821576` (existing OPD) |
| Encounter | `9a88a85d-a2db-4656-94bd-fb55c1b01688` Consultation |
| ORD-10 | `07cf32a8-c31b-4d61-906f-30a83785ce96` Malarial smear, 19 Aug 2026 23:19:32 UTC |
| ORD-9 | `a915d836-e429-4443-afc1-5401f16f037c` same test, 23:18:28 UTC (extra order from this pass) |
| Charge | INV/2026/00022 ₦1,500 UNPAID (ORD-10) |

---

## 8. Atomfeed result

OpenMRS `event_records` Encounter events exist for ORD-8 (`413306d1-…` 22:50:04), ORD-9 (`70776d91-…` 23:18:29), ORD-10 (`c4331b61-…` 23:19:32).

Before this pass the laboratory-application encounter marker was stuck at 17 Aug 2026 (`cd05a38a-…`) after OpenMRS timeouts. After restarting the laboratory application the markers advanced to the latest patient, encounter, and lab catalogue events.

---

## 9. OpenELIS processing result

**Proved:** new hospital concepts do need the existing laboratory catalogue feed. After catch-up, OpenELIS test count went **622 → 640**, and `external_reference` includes both Malarial smear `32AAA…` and Urine Toxicology `b61e3305-…`.

**Additional confirmed gap:** the feed created the 18 new tests **without specimen types**. Encounter processing then failed with:

`NullPointerException` at `GroupBySampleTypeFeedProcessor.groupOrdersBySampleType` for Consultation `9a88a85d-…` (this encounter includes ORD-8 plus the in-house MP orders).

After specimen types were added from the hospital CSV (Blood / Urine / Sputum / HVS / Semen / Other), failed events were retried. OpenELIS then created:

| Sample | Analysis | Test | Status | Patient |
|---|---|---|---|---|
| 28 | 470 | Malarial smear | Not Tested (4) | ABC200016 |
| 29 | 471 | Urine Toxicology/Drug Test | Not Tested (4) | ABC200016 |

Sample **27** / analysis **469** (ORD-5 Malarial smear, 17 Aug) is unchanged. No accession numbers on 27–29.

The in-house MP order **is** visible in the laboratory application as sample 28 / analysis 470.

---

## 10. Result-return result

`labOrderResults` lists ORD-8 / ORD-9 / ORD-10 with **result = null** and tabular **values = []**. Nothing was entered through the laboratory processing application. Nothing was written into OpenMRS obs.

---

## 11. Exact failure point if incomplete

**Blocked at laboratory sample collection / accession / result entry in the existing laboratory application.**

Samples exist as **Not Tested** with **empty accession**. The same is true of the earlier working Malarial smear TEST sample. Result entry and return to the doctor require that existing application’s collection and validation steps. This pass did not invent a result API or type a result into the database.

---

## 12. Fixes made

1. Restarted the laboratory application so atomfeed workers could run after OpenMRS timeouts.
2. Inserted `sampletype_test` rows for OpenELIS tests **1406–1423** using hospital CSV specimens mapped to existing specimen types (Blood Specimen, Urine, Sputum, High vaginal swab, Semen, Other Specimen). Did not change dictionary tests or the Malarial smear row.
3. Reset failed-event retry counts from 10 (exhausted) to 0 so the existing retry job could reprocess Consultation `9a88a85d-…`.
4. `configure-laboratory-catalogue.py` `find_concept_by_name` now only reuses **Test** / **LabSet** concepts.

Not remapped: the four Drug-class hormone/phosphate bindings (uncertain unique names). Not filled: E/U/Cr, hospital LFT, and HBsAg Serology Panel still have **0** panel members in OpenELIS.

---

## 13. Regression results

| Area | Result |
|---|---|
| Pharmacy | `pharmacy.abikan` queue **200**. **ORD-7** still **PAID** / **READY TO DISPENSE**. Not dispensed. |
| Nursing | `nurse.abikan` ward board **200** (areas, total/occupied/available beds). Laboratory board **403**. Payment **403**. No admit/transfer/discharge performed. |
| Reception | `reception.abikan` patient account **200**. Laboratory board **403**. Payment **403**. |

---

## 14. Security results

| Call | Result |
|---|---|
| Unauthenticated catalogue / board / payment | **401** |
| Doctor catalogue | **200** |
| Doctor board / payment | **403** |
| Lab board | **200** |
| Lab create order / payment | **403** |
| Accountant catalogue / create order | **403** |
| Accountant patient account | **200** |
| Pharmacy / nurse / reception laboratory writes | **403** |
| Admin laboratory board | **200** |

---

## 15. Test data created

TEST patient only. ORD-7 / INV/2026/00020 / pharmacy stock not changed.

| Record | Id |
|---|---|
| ORD-9 | `a915d836-e429-4443-afc1-5401f16f037c` |
| ORD-10 | `07cf32a8-c31b-4d61-906f-30a83785ce96` |
| Visit / encounter | as §7 |
| INV/2026/00022 | ₦1,500 UNPAID |
| OpenELIS samples | 28 (MP), 29 (urine toxicology) |
| Result | none |

---

## 16. npm test

`npm test` in `abikan-shell`: **81 passed**, 0 failed (includes laboratory hash, NGN catalogue, and payment-visibility regressions).

## 17. npm build

`npm run build`: **succeeded** (`tsc --noEmit && vite build`).

These do not prove live laboratory-application integration.

---

## 18. Remaining limitations

1. Result return is unproven until accession and a real result are entered in the existing laboratory application.
2. Four Drug-class catalogue bindings (phosphate / testosterone / progesterone / estradiol).
3. E/U/Cr, hospital LFT, HBsAg Serology Panel remain empty panels in OpenELIS.
4. New tests need specimen types when the catalogue feed creates them; the configure script still does not push specimen into OpenMRS.
5. Accountant may still print ₦ after the amount. Pharmacy USD invoices were not converted.
6. ORD-9 is an extra unpaid/unbilled MP order on the TEST chart from this pass.
