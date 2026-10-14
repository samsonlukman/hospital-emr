# Clinical history and examination investigation

Date: **19 Aug 2026**. Investigation only. No patients, visits, encounters, observations, diagnoses, orders, admissions, invoices, payments, concepts, forms, or configuration were created or changed.

Related: `CLINICAL_INVESTIGATION.md`, `CLINICAL_WRITE_API.md`, `CONSULTATION_SAVE_FIX.md`, `PRESCRIPTION_E2E_TEST.md`.

Status labels: **CONFIRMED** · **NOT PRESENT** · **NOT USED** · **REQUIRES HOSPITAL DECISION**

---

## Verdict

This installation already stores clinical documentation as **OpenMRS observations** on a **Consultation** encounter, via `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `observations[]`. That is the correct write path. Do not add a second encounter type for notes.

What the hospital **does not** have is a live, used History vs Examination form. The Bahmni Forms 2 form named **History and Examination** exists, but it is **not an examination form**. No patient on this server has history or examination observations. Hospital EMR’s Assess section is still **Coming soon**.

Recommended next implementation: **B** — a thin Hospital EMR presentation over a small set of **existing** OpenMRS concepts on the **existing Consultation encounter**. Do not invent a Nigerian OPD exam sheet. Do not turn on CIEL review-of-systems / systemic exam panels unless the hospital asks for them.

---

## 1. Existing forms

**CONFIRMED** — 17 published Forms 2 records in OpenMRS `form` / `GET /openmrs/ws/rest/v1/form`. `form_field` count is **0** (these are file-backed Forms 2, not HTML Form Entry). JSON lives in the OpenMRS container at `/home/bahmni/clinical_forms/{uuid}.json`.

| Form | UUID | What it actually contains |
|---|---|---|
| **History and Examination** | `d60dd30a-229d-4645-9fc9-43d44dcefbd8` | Chief complaint group, HPI text, smoking status, images, videos. **No examination fields.** |
| Vitals | `b2d254df-e612-40c8-a90c-fbf446ea22e6` | Pulse, SpO2, RR, temperature, BP, posture (Forms 2 concepts, **not** the CIEL vitals Hospital EMR already writes) |
| Second Vitals | `f192096c-2bdf-460b-a353-25a1725e88bc` | Published; not inspected in detail |
| Orthopaedic Examination | `0c7a636f-df5d-4d7e-9a84-91a168ceec9e` | Three **text** fields: musculoskeletal exam, range of motion, radiographic examination |
| Follow Up | `7d416b24-2031-4e68-8870-12f4a2659cf5` | Return visit date, reason for visit |
| Obstetrics and Gynaecology | `0368058f-…` | Specialty form |
| Diabetes / Hypertension intake & progress | four forms | Disease templates |
| Malaria, Immunization Incident Record | | Disease / programme |
| Admission Letter, Death Note, Referral letter, Registration Details, Fitness Certificate | | Letters / admin |

**CONFIRMED not used in Hospital EMR Consultation.** Clinical `dashboard.json` Forms 2 sections have **empty** `formGroup` / `formNames` arrays. Observation tab config points at a **concept set** named `History and Examination`, not at this Forms 2 form.

**CONFIRMED** no observation has `form_namespace_and_path` set. Forms 2 has never been filled on this database.

Disk CSV templates under `abikan-config/openmrs/templates/` (including “Detailed History and Examination”) are **not loaded** as concepts. Names such as `Detailed History, Past History` are **NOT PRESENT**.

---

## 2. Existing concepts

Checked live in OpenMRS (fully specified English names, not retired).

### Present and relevant to OPD documentation

| Staff meaning | Concept | UUID | Type | Notes |
|---|---|---|---|---|
| History of present illness | History of present illness | `1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text | On the Forms 2 History and Examination form. Already named in `clinicalConcepts.ts`. |
| Clinical notes | Consultation Note | `d37294c5-5e07-11ef-8f7c-0242ac120002` | Text | Bahmni/Hospital EMR concept. Already named in `clinicalConcepts.ts`. |
| Chief complaint (structured) | Chief Complaint Record | `da47a35d-5806-48b7-b467-e29902759491` | Set (N/A) | Group on the Forms 2 form. |
| Chief complaint coded | Chief Complaint Coded | `9bb0795c-4ff0-0305-1990-000000000002` | Coded | **58** answers (pain, fever, cough, …). Child of the set. |
| Chief complaint free text | Chief complaint (text) | `160531AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text | Child of the set. |
| Duration | Sign/symptom duration | `1731AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Numeric | Child of the set. |
| Duration unit | Chief Complaint Duration | `9bb0795c-4ff0-0305-1990-000000000003` | Coded | Hours / Days / Weeks / Months / Years. |
| Smoking | Smoking status | `163201AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Coded | 8 answers. On the Forms 2 form. |
| Images / video | Consultation Images / Image / Consultation Videos / Patient Video | Bahmni `9bb0795c-…` uuids | Complex | On the Forms 2 form. Out of scope unless the hospital asks. |

CIEL **Chief complaint** `5219AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` also exists (Coded). It has **0** answers on this server. Do not treat it as a free-text box. The form uses **Chief Complaint Coded**, not 5219.

### Present in the CIEL dictionary but **not** on a hospital OPD form

These exist as dictionary concepts/sets. They are **not** wired into Hospital EMR, **not** on the Forms 2 History and Examination form, and **not** used in any observation.

| Concept | UUID | Type |
|---|---|---|
| Past medical history | `1633AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Set (coded diagnosis + text + dates) |
| Medication history | `160741AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Set (many children) |
| Review of systems | `159615AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | ConvSet of coded ROS questions |
| Family history comment / family history of … | several CIEL questions | Text / coded / finding |
| Abdominal examination (text) | `160947AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text |
| Musculoskeletal examination (text) | `163048AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | Text (also on Orthopaedic Examination form) |

ROS children include general, HEENT, cardiopulmonary, gastrointestinal, genitourinary, musculoskeletal, CNS, developmental, obstetrical. That is **dictionary**, not evidence that this hospital documents a full ROS at every OPD visit.

### Named in Bahmni config but **NOT PRESENT** as concepts

| Configured name | Where named | Live concept |
|---|---|---|
| History and Examination | Clinical `extension.json` observation tab; dashboard `conceptNames` | **NOT PRESENT** (no concept set) |
| History and Examination Notes | `visit.json` discharge clinical notes | **NOT PRESENT** |
| Examination Notes | dashboard `HistoryAndExamination` | **NOT PRESENT** |
| Chief Complaint Data | `app.json` conceptSetUI; dashboard | **NOT PRESENT** (the live set is **Chief Complaint Record**) |
| Smoking History | dashboard | **NOT PRESENT** (live concept is **Smoking status**) |
| Vitals / Second Vitals / Obstetrics / Gynaecology | observation tab concept sets | **NOT PRESENT** as concept sets |

Hospital EMR already writes **individual CIEL vital concepts**, not a Vitals concept set. That remains true.

---

## 3. Existing observations

**CONFIRMED** — entire OpenMRS `obs` table, non-voided, grouped by concept:

| Concept | Count | Role |
|---|---|---|
| Pulse | 3 | Vitals |
| Temperature (C) | 2 | Vitals |
| SpO₂, Height, Weight, Respiratory rate | 1 each | Vitals |
| Visit Diagnoses / Coded Diagnosis / certainty / order / Bahmni diagnosis flags | 2 each | Diagnosis |
| Disposition / Disposition Set | 2 | Admit |

**Zero** observations for:

- History of present illness
- Consultation Note
- Chief Complaint Record / Coded / text / duration
- Smoking status
- Past medical history
- Review of systems
- Any examination text
- Images / video
- Any Forms 2 `form_namespace_and_path`

Allergy table: **0** rows. Hospital EMR already reads `GET /openmrs/ws/rest/v1/patient/{uuid}/allergy` (not history obs).

---

## 4. Existing history data

**NOT PRESENT** as clinical history documentation.

What Hospital EMR currently labels **History** on the consultation screen is a **visit/encounter timeline** (dates, visit type, location). Hint on screen: “Encounter type and date only. Note text is not available in this view.”

That is not history of presenting complaint.

---

## 5. Existing examination data

**NOT PRESENT** for general OPD.

The only examination-shaped form is **Orthopaedic Examination** (three text boxes). Unused. No observations.

The form named History and Examination contains **no** general, systemic, or physical examination controls.

---

## 6. How the data is stored

**CONFIRMED**

```
OpenMRS obs
  on encounter (Consultation)
  concept + value (numeric / text / coded / set members)
  optional form_namespace_and_path  (unused here)
```

Bahmni Forms 2, when used, still writes **obs**. Classic Bahmni Observations tab writes **obs** from concept sets.

Hospital EMR Consultation save already posts:

```
POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
  observations[]     vitals today
  bahmniDiagnoses[]  diagnosis
  drugOrders[]       prescription
```

History/examination, if implemented, belong in **`observations[]`** on that same POST. Do not POST raw `/obs`. Do not create a parallel notes table.

---

## 7. Encounter relationship

**CONFIRMED** — use the existing **Consultation** encounter type `d34fe3ab-5e07-11ef-8f7c-0242ac120002`.

History/examination observations can safely be added to the **same** Consultation encounter as vitals, diagnosis, and drug orders. That is how Bahmni’s own mapper works (`observations` + `bahmniDiagnoses` + `drugOrders` on one transaction).

Do **not** create a second encounter type or a second visit model for notes.

Live example: ABC200016 E2E visit `6478a94e-…` has **one** Consultation encounter `9a88a85d-…` with 0 obs and 1 drug order. Notes for that same visit should target that encounter (or the session match described below), not a new type.

---

## 8. Encounter session behaviour

**CONFIRMED** from installed `EncounterSessionMatcher` and global properties:

| Property | Value |
|---|---|
| `emr.encounterMatcher` | `org.bahmni.module.bahmnicore.matcher.EncounterSessionMatcher` |
| `bahmni.encountersession.duration` | **60** minutes |
| `bahmni.encounterType.default` | Consultation |

Matcher behaviour:

1. If the POST includes **`encounterUuid`**, that encounter is updated.
2. If not, Bahmni looks for a matching Consultation on the **same visit** (type / location / provider / time window of 60 minutes).

Hospital EMR today does **not** send `encounterUuid` (`buildConsultationPayload`). Multiple saves can still land on one encounter **inside 60 minutes**. Outside that window they become a **new** Consultation encounter. That already happened: Tunde ABC200006 has two Consultation encounters on one visit (13 Aug 22:33 and 16 Aug 20:41).

`POST …/bahmniencounter/find` returned **HTTP 500** in this investigation; `GET …/bahmniencounter/{uuid}?includeAll=true` works (used for the E2E encounter).

For history/examination implementation: keep using `bahmniencounter`. Prefer sending the current visit’s Consultation `encounterUuid` when known, so notes, vitals, diagnosis, and the prescription stay on one chart encounter. Do not invent a new session model.

---

## 9. Current Hospital EMR UI

Consultation flow: Review → Vitals → **History** → **Assess** → Diagnose → Order → Prescribe → Disposition.

| Section | What it is today | History / exam relevance |
|---|---|---|
| Review | Allergies, diagnoses, medications sticky bar | Allergy is a separate OpenMRS allergy API, not history obs |
| Vitals | WORKING — 8 CIEL numerics | Not examination notes |
| **History** (`#history`) | Visit timeline + previous encounter type/date | **Name clash.** This is chart chronology, not HPI |
| **Assess** (`#assess`) | Coming soon: rows labelled History, Examination, Clinical notes | **Natural place** for documentation |
| Diagnose | WORKING | Separate from notes |
| Order | Coming soon (lab/radiology order buttons) | — |
| Prescribe | WORKING | — |
| Disposition | Admit Patient WORKING; Refer / Follow-up Coming soon | — |
| Consultation fee | Create fee only; no Pay | Unrelated |

Copy already on Assess: “Where the doctor documents history, examination and notes.” “Documentation from Hospital EMR is not enabled yet. Nothing is saved from this screen.”

Do not embed Bahmni Forms 2 in this screen yet: Hospital EMR has no Forms 2 renderer, and the published History and Examination form is the wrong clinical shape (no examination; includes images/video).

---

## 10. Recommended implementation approach

**B. Thin Hospital EMR presentation over existing OpenMRS concepts / the existing Consultation encounter.**

Not **A** (reuse Bahmni forms directly):

- The Forms 2 form named History and Examination is not an examination form.
- Clinical observation-tab concept set `History and Examination` is **missing**.
- Forms 2 is unpublished to the Hospital EMR consultation (`formGroup` empty; zero form-path obs).
- Embedding Forms 2 would pull smoking, images, and videos into every OPD note without a hospital decision.

Not **C** (configure new forms/concepts) as the first move:

- HPI text and Consultation Note already exist and are unused.
- Chief Complaint Record already exists if a structured complaint is wanted.
- Creating a new “Hospital EMR Examination” concept or a new form is a **hospital** choice, not a software gap that must be filled first.

### Suggested shape (for the next implementation phase — not built here)

Keep History and Examination as **two fields** on Assess, plus optional Clinical notes. Map to existing concepts, for example:

| Hospital EMR label | Existing concept | Why |
|---|---|---|
| History | History of present illness (text) | Matches HPI; already on the Bahmni form |
| Examination | **REQUIRES HOSPITAL DECISION** — see below | No examination concept/form is in use |
| Clinical notes | Consultation Note (text) | Already exists; free-text catch-all |

Do **not** add cardiovascular / respiratory / neurological checklists because CIEL happens to contain those terms.

Write via the existing `observations[]` on `bahmniencounter`, same Consultation encounter, same visit-window save guard.

---

## 11. Missing hospital decisions

Stop before creating concepts or forms until the hospital answers:

1. **What is History in OPD?** HPI only, or also past medical / drug / family / social / ROS?
2. **What is Examination in OPD?** One free-text box, or structured systems? Orthopaedic-only vs general?
3. **May Examination reuse Consultation Note**, or must it be a separate concept (which would be **new**, because Examination Notes is missing)?
4. **Chief complaint:** coded list of 58 answers, free text, both, or skip for v1?
5. **Smoking, images, videos:** in the first OPD note, or later?
6. **Should the visit-timeline section stay named History**, or be renamed so staff are not shown two different “History” meanings?

Until (2) and (3) are answered, do not invent an examination form.

---

## 12. Known limitations

1. Bahmni default config names (`History and Examination` concept set, `Examination Notes`, `Chief Complaint Data`) do **not** match live metadata.
2. Forms 2 Vitals uses different concept UUIDs than the CIEL vitals Hospital EMR already writes. Do not switch vitals to Forms 2 in this work.
3. `bahmniencounter/find` HTTP 500 on this install; encounter reload should use `GET …/bahmniencounter/{uuid}` and existing visit/encounter lists.
4. Hospital EMR save does not yet send `encounterUuid`; 60-minute session matching is the only automatic merge.
5. Disease CSV templates on disk are not the live OPD record.
6. No existing filled chart to copy as “what this hospital documents.”

---

## Requested checklist

| Topic | Result |
|---|---|
| Chief / presenting complaint | **Chief Complaint Record** + coded/text children exist. Unused. CIEL 5219 exists with no answers. |
| History of presenting complaint / HPI | **History of present illness** text exists. Unused. |
| Past medical / surgical / drug / family / social | PMH and medication-history **sets** exist in CIEL. Surgical history as a named concept **NOT PRESENT**. Unused. |
| Allergy history | OpenMRS **allergy** API (0 rows). Not obs. |
| Review of systems | CIEL convset exists. Unused. Not on the OPD form. |
| General / systemic / physical examination | **NOT PRESENT** as a used form. Orthopaedic Examination exists, unused. |
| Assessment / clinical notes / examination findings | Consultation Note exists. Examination Notes **NOT PRESENT**. |
| History vs Examination in config | Form **name** combines them; **content** is history + media only. Hospital EMR UI already splits the words on Assess. |
| Same Consultation encounter | **Yes.** Use `observations[]` on `bahmniencounter`. |
| Reuse existing forms as-is | **No** for the default History and Examination Forms 2 form. **Yes** to reuse its HPI / complaint **concepts**. |

---

*End of investigation. History and Examination were not implemented.*
