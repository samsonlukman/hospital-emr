# Radiology & Ultrasound — Hospital Decisions

Date: **24 August 2026**.

This sheet is for the medical director, radiologist, and implementation contact.

It is **not** a request to approve the Radiology menu again. That menu is already taken from the hospital’s supplied diagnostic referral form.

Please answer only the questions below. Tick or circle one option where choices are given. Leave TEST prices blank if they are not yet decided.

Do **not** start Radiology ordering until these answers are received.

---

## Already Approved

The hospital has already approved **42** Ultrasound and Radiography / Fluoroscopy services on the supplied referral form.

Those 42 services are the Radiology menu. They do not need to be re-approved.

**Ultrasound Scan**

1. Obstetrics (Pregnancy)
2. Pelvic
3. Breast
4. Abdominopelvic
5. Biophysical Profile (BPP)
6. Thyroid/Neck
7. Anomaly Scan
8. Eye/Ocular
9. Scrotal/Testicular
10. Musculoskeletal
11. Follicular Tracking
12. Prostate
13. Transvaginal
14. Doppler Studies

**Radiography / Fluoroscopy**

1. Abdominal X-ray
2. Cervical Neck X-ray
3. Chest X-ray
4. Lumbosacral Spine
5. Paranasal Sinuses
6. Facial Bones/Mandible
7. Pelvic X-ray
8. Knee Joint
9. Ankle Joint
10. Paediatric X-ray
11. Hysterosalpingography (HSG)
12. Intravenous Urography (IVU)
13. Retrograde Urethrography (RCUG)
14. Barium Enema
15. Skull X-ray
16. Thoracolumbar Spine
17. Shoulder X-ray
18. Humeral X-ray
19. Forearm X-ray
20. Tibia & Fibula X-ray
21. Elbow X-ray
22. Wrist/Hand/Finger X-ray
23. Femoral X-ray
24. Thoracic Inlet
25. Micturating (Voiding) Cystourethrography (MCUG)
26. Temporomandibular Joint
27. Barium Meal
28. Barium Follow Through

The same paper form also lists Cardiology, Pathology, and Special Service items. Those are **not** part of this Radiology implementation. See the note at the end of this document.

---

## Questions Requiring Clinical Clarification

Nine questions only. Please choose one answer for each.

Recommended answers are suggestions from the clinical mapping review. The hospital’s choice is final.

| # | Service | Question | Hospital decision |
|---|---|---|---|
| 1 | Chest X-ray | Should this mean **A.** Single view, **B.** PA + lateral / two views, or **C.** Other (please write the protocol)? | A / B / C: ________ |
| 2 | Limb X-rays (Knee, Ankle, Humerus, Forearm, Tibia & Fibula, Elbow, Femur) | Should the doctor select **Left**, **Right**, or **Bilateral**? | Recommended: Left / Right / Bilateral. Decision: ________ |
| 3 | Breast Ultrasound | Should this allow **A.** Left, **B.** Right, **C.** Both breasts? | Recommended: Breast, then laterality Left / Right / Bilateral. Decision: ________ |
| 4 | Thyroid/Neck | Does this mean **A.** Thyroid ultrasound only, **B.** Thyroid + neck soft tissues, or **C.** Two separate examinations? | A / B / C: ________ |
| 5 | Prostate | Which should “Prostate” mean? **A.** Transabdominal, **B.** TRUS / transrectal, **C.** Both (shown as two separate choices) | A / B / C: ________ |
| 6 | Doppler Studies | Which Doppler examinations does the hospital actually offer? Examples only — not a proposed menu: carotid, lower limb, upper limb, renal, obstetric/fetal, other. | Please list the Doppler types performed: ________ |
| 7 | Facial Bones/Mandible | Should this stay **one** selection, or should doctors choose **A.** Facial Bones and **B.** Mandible separately? | Recommended: separate if they are performed or billed differently. Decision: ________ |
| 8 | Wrist/Hand/Finger X-ray | Should the hospital offer **A.** Wrist, **B.** Hand, **C.** Finger, **D.** All three as separate selections? | Recommended: separate if they are performed or billed differently. Decision: ________ |
| 9 | Musculoskeletal Ultrasound | Is this a **general** ultrasound of an extremity / soft tissue, or does the hospital use **specific** anatomical examinations? | General / Specific. If specific, list the anatomical options: ________ |

Do not invent extra Doppler or musculoskeletal lists. Use only what the hospital writes above.

---

## OpenMRS Configuration Required

These **10** services are already on the hospital’s approved menu. Their names are clear. They do **not** need to be redefined clinically.

They cannot be offered for ordering until matching services are configured in the hospital’s existing clinical system (OpenMRS / Bahmni).

Do **not** create these as Hospital EMR-only concepts. They should be configured in the hospital’s OpenMRS/Bahmni installation.

1. Abdominopelvic
2. Biophysical Profile (BPP)
3. Anomaly Scan
4. Eye/Ocular
5. Follicular Tracking
6. Paediatric X-ray
7. Retrograde Urethrography (RCUG)
8. Thoracic Inlet
9. Temporomandibular Joint
10. Barium Follow Through

**Question**

These services are on the hospital’s approved menu, but the current OpenMRS installation does not contain a safe matching concept. Should these services be configured in OpenMRS before they become available for ordering?

**Yes / No:** ________

If **Yes**, configuration is an OpenMRS/Bahmni task for the implementation team. If **No**, those ten services stay on the approved paper menu but will not be available to order in Hospital EMR until they are configured.

---

## TEST Pricing Required

This is for **TEST** work only. It is not the hospital’s production tariff.

Today only **one** approved service has a usable TEST product and price:

| Service | Current TEST price |
|---|---|
| Chest X-ray | 60 USD (existing isolated TEST product) |

The other catalogue rows at $1.00 are placeholders and must not be used as TEST prices.

**41** approved services still need a TEST price before they can be billed in TEST.

Preferred TEST currency is **NGN**, because the live hospital workflow is Nigerian. Please write the currency if you prefer something else.

Do **not** treat this table as production pricing. Production tariff, tax, and outsourced rates come later.

| Service | TEST price (NGN) |
|---|---:|
| Obstetrics (Pregnancy) | |
| Pelvic | |
| Breast | |
| Abdominopelvic | |
| Biophysical Profile (BPP) | |
| Thyroid/Neck | |
| Anomaly Scan | |
| Eye/Ocular | |
| Scrotal/Testicular | |
| Musculoskeletal | |
| Follicular Tracking | |
| Prostate | |
| Transvaginal | |
| Doppler Studies | |
| Abdominal X-ray | |
| Cervical Neck X-ray | |
| Lumbosacral Spine | |
| Paranasal Sinuses | |
| Facial Bones/Mandible | |
| Pelvic X-ray | |
| Knee Joint | |
| Ankle Joint | |
| Paediatric X-ray | |
| Hysterosalpingography (HSG) | |
| Intravenous Urography (IVU) | |
| Retrograde Urethrography (RCUG) | |
| Barium Enema | |
| Skull X-ray | |
| Thoracolumbar Spine | |
| Shoulder X-ray | |
| Humeral X-ray | |
| Forearm X-ray | |
| Tibia & Fibula X-ray | |
| Elbow X-ray | |
| Wrist/Hand/Finger X-ray | |
| Femoral X-ray | |
| Thoracic Inlet | |
| Micturating (Voiding) Cystourethrography (MCUG) | |
| Temporomandibular Joint | |
| Barium Meal | |
| Barium Follow Through | |

If a clinical answer above splits one line into two or more examinations (for example Wrist and Hand, or two Prostate examinations), please give a TEST price for each examination the hospital will offer.

Chest X-ray already has a TEST price. Confirm only whether that existing TEST amount should stay, or be replaced with an NGN TEST amount: ________

---

## Later Production Decisions

These are **not** required to answer this mapping sheet. They will be asked separately before go-live.

- Production NGN tariff
- Tax
- In-house vs outsourced
- Payment timing (for example payment before the scan)
- Radiology report workflow
- Radiology staff permissions
- PACS / machine configuration

Do not fill production prices in the TEST table above.

---

## Services That Are Not Radiology

These services appear on the same supplied hospital form. They will be handled as separate workflows and are **not** part of the current Radiology implementation.

**Cardiology**

- ECG Resting
- Echocardiogram Resting

**Pathology**

- Pap Smear
- FNAC
- Histology

**Special Service**

- Mammogram
- DNA

No further confirmation is needed on this point.

---

## How to reply

Please return:

1. Answers to the **9** clinical questions
2. **Yes / No** on configuring the **10** missing services in OpenMRS
3. TEST prices (NGN preferred) for the **41** services that do not yet have a usable TEST product, plus any extra lines created by the clinical answers

After these answers, the implementation team can prepare TEST products and OpenMRS configuration. Radiology ordering in Hospital EMR will not start until then.
