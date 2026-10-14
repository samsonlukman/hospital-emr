# OpenELIS laboratory administration

Date: **26 Aug 2026**. Applies to `bahmni/openelis:1.0.0` in this deployment.

OpenELIS remains the laboratory processing system and source of truth for specimens, analyses, result entry, validation, and its audit trail. This document does not create an OpenELIS API or a Hospital EMR laboratory administration screen.

## Administrative model

The two administration boundaries are separate:

```text
Hospital EMR Technical SuperAdmin
  → Hospital Administrator
  → Hospital EMR/OpenMRS staff accounts and approved department access

OpenELIS technical administrator
  → dedicated named OpenELIS Laboratory Administrator
  → named OpenELIS laboratory staff accounts
  → Intake / Results entry / Validation
  → OpenELIS-side test configuration
```

Hospital EMR Hospital Administrator does not receive OpenELIS credentials or privileges. OpenELIS passwords are never stored by Hospital EMR.

## Dedicated Laboratory Administrator

Create the hospital's administrator manually in **OpenELIS → Administration → Manage Users**. A current OpenELIS technical administrator performs this one-time action. Do not reuse the stock development `admin` or `user` identities.

Required account properties:

- a unique, named username (OpenELIS limit: 20 characters);
- the administrator's real first and last name;
- an independently managed OpenELIS password;
- `is_admin = N` — do not make the account an OpenELIS superuser;
- enabled, active, and unlocked;
- role **Maintenance Admin**.

`Maintenance Admin` is the installed role that provides the required user and catalogue administration. Adding `User Admin` is redundant because `Maintenance Admin` already grants `UnifiedSystemUser`.

This is a broad trusted role, not a laboratory-only least-privilege role. It grants 28 modules, including tests, panels, specimens, units, ranges, sections, users, roles, system modules, site information, report administration, dictionary, organization, analyzer names, and reflex configuration. The hospital must treat the holder as an OpenELIS technical/laboratory administrator.

Do not assign routine processing roles to the administrator unless that person also performs that duty. If they do, add only the required operational role.

## Staff accounts and roles

Every person performing laboratory work receives an individual OpenELIS account. Never process clinical work using `admin`, `user`, `atomfeed`, or another shared identity.

| Staff duty | Roles |
|---|---|
| Specimen intake / accession | `Intake`, `LabDashboard` |
| Results entry | `Results entry`, `LabDashboard` |
| Result validation | `Validation`, `LabDashboard` |
| Modify an already-entered result | `Results modifier` only after explicit approval |

Do not grant `Maintenance Admin` or `User Admin` to ordinary laboratory staff.

The installed user-management screen does not enforce a narrow role allow-list. A Maintenance Administrator can assign all roles. The control is therefore the hospital's trusted-administrator policy and periodic account review, not a technical restriction in this OpenELIS version.

## Staff account procedure

### Create

1. Hospital Administrator creates or enables the person's Hospital EMR/OpenMRS account and grants Laboratory department access.
2. Laboratory Administrator signs into OpenELIS with their named administrator account.
3. Open **Administration → Manage Users → Add**.
4. Enter the person's unique username, real name, initial password, active/enabled state, and timeout.
5. Assign only the roles required by the person's current duties.
6. Give the initial password directly to that person using the hospital's approved confidential channel.
7. The person signs in and confirms only their assigned workflow is available.

The Hospital EMR and OpenELIS usernames should match where practical, but passwords remain independent. Store neither the initial nor current OpenELIS password in Hospital EMR.

### Change, transfer, or terminate

- Role change: edit the OpenELIS user and add/remove only the approved operational roles.
- Transfer out of Laboratory: remove operational roles or disable the OpenELIS account; separately remove Hospital EMR Laboratory access.
- Temporary absence: disable the OpenELIS login rather than sharing it.
- Termination: disable the Hospital EMR/OpenMRS account and the OpenELIS account as two explicit checklist steps.
- Replacement: create a new named account; never rename or reuse the departed person's identity.
- Password reset: use OpenELIS **Manage Users**. Do not send the password through Hospital EMR.

There is no automatic Hospital EMR-to-OpenELIS synchronization or SSO in this deployment.

## Integrated test creation

Creating a local OpenELIS test does **not** make it orderable in Hospital EMR. The integrated catalogue direction is:

```text
OpenMRS Test/LabSet concept
  → OpenMRS laboratory atom feed
  → OpenELIS test/panel
  → Laboratory Administrator completes OpenELIS-side configuration
```

For an integrated hospital test, use this sequence:

1. Obtain an approved clinical definition: name, code where applicable, specimen, result datatype, units, section, reference ranges, price, and whether it is performed in-house.
2. An authorized OpenMRS catalogue maintainer reuses an exact safe `Test`/`LabSet` concept or creates the approved concept. Approximate and Drug-class concepts are forbidden.
3. Add the concept to the correct specimen and department sets and to `All_Tests_and_Panels`.
4. Allow the existing laboratory feed to create/update the corresponding OpenELIS test or panel.
5. Laboratory Administrator verifies and completes OpenELIS-side configuration:
   - test/panel identity and active state;
   - specimen association;
   - laboratory section;
   - result type and result choices;
   - unit of measure;
   - normal and valid reference ranges;
   - analyte/reflex configuration when clinically approved.
6. Configure the approved patient price through the existing Hospital EMR catalogue/Odoo maintenance procedure.
7. Verify with controlled development data: Doctor search → order → feed receipt → specimen processing → named result entry → named validation → result return.

Do not manually create a duplicate OpenELIS test before its OpenMRS concept is established. The legacy OpenELIS Test screen states that it is incomplete for adding a test and forces `orderable=true`; it is not the authority for Hospital EMR orderability.

### Supported OpenELIS screens

| Configuration | Module / screen |
|---|---|
| Tests | `Test` → `/TestMenu.do` |
| Panels | `Panel`, `PanelItem` |
| Specimens | `TypeOfSample` |
| Test/specimen association | `TypeOfSampleTest` |
| Units | `UnitOfMeasure` |
| Result format | `TypeOfTestResult` |
| Coded result choices | `TestResult` |
| Reference and valid ranges | `ResultLimits` |
| Laboratory sections | `TestSection` |

There is no supported OpenELIS UI for populating `test_code` (LOINC, SNOMED, billing, or analyzer code rows) in this build. Do not write that table directly.

## Four unavailable tests

Inorganic Phosphate, Testosterone, Progesterone, and Estradiol remain unavailable. Exact safe OpenMRS `Test`/`LabSet` concepts were not found; same-name concepts are Drug class. They remain `skip`, have no runtime concept binding, and are excluded from `All_Tests_and_Panels`.

Before enabling one, the hospital must approve either an exact existing laboratory concept or creation of a new clinically defined Test concept. `Serum phosphorous` and `Progesterone Receptor Assay` must not be treated as automatic substitutes.

## Security and credential boundary

- Laboratory Administrator credentials stay in OpenELIS and the hospital's approved secret/password process.
- No OpenELIS password appears in frontend code, browser storage, Hospital EMR staff records, Docker images, or public environment variables.
- `atomfeed` remains an integration identity and is not used for human work.
- OpenELIS actions must use the real worker's named session so result and validation attribution remains meaningful.
- Laboratory Administrator has no automatic Hospital EMR Administration, OpenMRS SuperAdmin, Odoo accounting, server, container, database, or host access.
- Infrastructure and database recovery remain OpenELIS technical-administrator responsibilities.

## Current limitations

- User creation and password management are supported only through the OpenELIS UI; there is no supported write REST API.
- Maintenance Admin is broad and can assign unrestricted OpenELIS roles. This deployment relies on selecting a trusted administrator and operating controls.
- OpenELIS and Hospital EMR accounts are not synchronized.
- OpenELIS has a 20-character username limit.
- OpenMRS remains the authority for tests orderable by doctors; OpenELIS remains the authority for processing configuration and results.
- Adding test codes to OpenELIS `test_code` is not supported through the installed UI.
- No account or test was created during this documentation task because browser automation, form scraping, and direct database writes are prohibited.
