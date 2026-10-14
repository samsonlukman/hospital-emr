# Admin Capability Audit

Date: **25 Aug 2026**  
Scope: read-only capability audit. No Admin workspace implementation.

## OpenELIS administration boundary — 26 Aug 2026

OpenELIS administration is separate from Hospital EMR Hospital Administration.

- **Hospital EMR Hospital Administrator** manages Hospital EMR/OpenMRS staff accounts and approved department access.
- **OpenELIS Laboratory Administrator** is a separate named OpenELIS account responsible for OpenELIS staff accounts and laboratory-side test configuration.
- Hospital Administrator receives no OpenELIS password, role, session, or superuser capability.
- Hospital EMR does not create OpenELIS users, store their passwords, automate OpenELIS forms, or provide a second laboratory administration screen.

On this installed `bahmni/openelis:1.0.0`, the dedicated trusted Laboratory Administrator uses the broad OpenELIS `Maintenance Admin` role with `is_admin = N`. That role includes user, role, test, specimen, range, section, site, report, and other OpenELIS configuration. It is not a narrow laboratory-only role and must be assigned only to a trusted hospital laboratory/technical administrator.

See `docs/OPENELIS_LABORATORY_ADMINISTRATION.md` for the account lifecycle, processing-role matrix, integrated test procedure, credential boundary, and known limitations.

## Executive finding

Hospital EMR does not currently have a hospital-administration role or a staff-management workflow.

What the UI calls **Administration** is the landing page for OpenMRS `SuperAdmin` / `System Developer`. It contains three placeholders — Users, Departments / Access, and System Settings — plus one implemented function: Accommodation Prices.

That technical account is too powerful to become the normal Hospital Administrator. It has clinical, financial, user, role, provider, location, configuration, and destructive privileges. A future Hospital Administrator should be a separate least-privilege role, not a renamed SuperAdmin and not `app:admin` with unrestricted REST access.

Recommended first scope:

1. Read-only staff directory and account/setup status.
2. Read-only department-access matrix.
3. Read-only approved-service readiness.
4. Only later, policy-approved staff create/disable/assignment actions with explicit backend authorization and a durable actor audit trail.

No Admin KPI dashboard is justified by the observed system.

## 1. Current Admin / SuperAdmin

### Current Administration route

- `#/home` resolves to the Administration workplace only for `SuperAdmin` / `System Developer`.
- The Administration navigation contains:
  - Dashboard — implemented route.
  - Users — coming soon.
  - Departments / Access — coming soon.
  - Accommodation Prices — implemented route.
  - System Settings — coming soon.
- There is no `admin` shell route, Admin component, staff-management component, role-management component, or provider-management component.
- There are no Hospital EMR Admin user/role/provider APIs.
- The only implemented administration-specific API is:
  - `GET /openmrs/abikan-api/inpatient/accommodation/tariffs`
  - `POST /openmrs/abikan-api/inpatient/accommodation/tariffs`
- Those endpoints authorize by OpenMRS role name `SuperAdmin` or `System Developer` and read/write Odoo accommodation product `list_price`.

Evidence:

- `src/config/adminNav.ts`
- `src/workspaces/ClinicalHome/ClinicalHomeWorkspace.tsx`
- `src/workspaces/Accommodation/AccommodationSettingsWorkspace.tsx`
- `src/app/WorkspaceRouter.tsx`
- `server/patient-account/accommodation.py`
- `server/patient-account/server.py`

### What SuperAdmin means in Hospital EMR

Frontend full-access detection is exactly:

- role `SuperAdmin`, or
- role `System Developer`.

It is tied directly to OpenMRS roles; it is not a Hospital EMR-only permission.

Full-access users:

- land on Administration;
- receive the department switcher;
- may select Reception, Clinical, Nursing, Pharmacy, Laboratory, Radiology, Accountant, and Administration;
- may open Patient Account;
- may collect payments because the Accountant backend explicitly accepts these roles;
- may set accommodation prices;
- are accepted by the Doctor, Laboratory, Radiology, Pharmacy, Registration, Nursing, Accountant, and accommodation backends.

`app:admin` is **not** the same as Hospital EMR full access. It appears in the OpenMRS/Bahmni app catalogue and grants Patient Account read access, but `isFullAccessAdmin` does not check it. Therefore `app:admin` must not be treated as the future Hospital Administrator contract.

### Current live SuperAdmin accounts

- `abikan.admin`
  - enabled;
  - roles include `System Developer`, `SuperAdmin`, `OT: FullAccess`, `Appointments:FullAccess`, `Privilege Level: Full`, `Bahmni-App`, and `Provider`;
  - provider `abikan.admin`, UUID `42ac4f6a-d3f9-4e59-ad9a-2c947e95d31b`;
  - 336 effective privileges.
- `admin.abikan`
  - enabled;
  - roles `SuperAdmin`, `Provider`;
  - provider `admin.abikan`, UUID `f54a23aa-9884-40ce-b09c-00094d91a3a8`;
  - 293 effective privileges.
- `superman`
  - enabled Bahmni demo/technical account;
  - roles include `System Developer` and `SuperAdmin`;
  - provider mapped.
- The built-in administrator has system ID `admin`, a blank username in the live user record, and roles `System Developer` and `Provider`.

Live `SuperAdmin` has 293 direct privileges, including user deletion, password editing, role/privilege management, provider management, location management, arbitrary concept/configuration management, clinical record writes/deletes, patient-data export, and `app:admin`.

`SuperAdmin` is not identical to `Privilege Level: Full`: the latter has 335 privileges and includes additional laboratory, appointments, theatre, and Hospital EMR custom privileges. However, Hospital EMR itself treats the `SuperAdmin` role as a cross-department bypass, so `admin.abikan` can still enter all Hospital EMR operational modules even when a department privilege is absent from its OpenMRS effective privilege list.

`System Developer` has no direct privileges in the REST role payload; OpenMRS treats it as its special technical unrestricted role. It must remain an IT/developer identity.

### Conclusion

SuperAdmin is currently a technical cross-department operator and OpenMRS administrator. It is being used as a substitute for an Admin role because no narrower role exists. It must not become the production Hospital Administrator.

## 2. Existing Users

Hospital EMR has no user database. Authentication, enabled/retired state, person, roles, privileges, passwords, and user properties live in OpenMRS.

All accounts below were read live and were enabled (`retired = false`).

### Preferred development accounts

| Username | Person | OpenMRS roles | `abikan.workplace` | Provider |
|---|---|---|---|---|
| `admin.abikan` | Hospital EMR Administrator | SuperAdmin, Provider | administration | `admin.abikan` |
| `reception.abikan` | Reception Staff | Abikan:Reception | reception | none |
| `registration.abikan` | Registration Staff | Abikan:Registration | registration | none |
| `doctor.abikan` | Clinical Doctor | Abikan:Doctor | clinical | `doctor.abikan` |
| `nurse.abikan` | Nursing Staff | Abikan:Nursing | nursing | `nurse.abikan` |
| `pharmacy.abikan` | Pharmacy Staff | Abikan:Pharmacy, Abikan:Pharmacy Inventory | pharmacy | none |
| `lab.abikan` | Laboratory Staff | Abikan:Laboratory | laboratory | none |
| `radiology.abikan` | Radiology Staff | Abikan:Radiology | radiology | `radiology.abikan` |
| `accountant.abikan` | Accountant Staff | Abikan:Accountant | accountant | none |

### Earlier compatibility accounts

The enabled `abikan.*` accounts remain:

- `abikan.registration` — Abikan:Registration; no provider.
- `abikan.doctor` — Abikan:Doctor; provider `abikan.doctor`.
- `abikan.nurse` — Abikan:Nursing; provider `abikan.nurse`.
- `abikan.pharmacy` — Abikan:Pharmacy + Abikan:Pharmacy Inventory; no provider.
- `abikan.lab` — Abikan:Laboratory; no provider.
- `abikan.radiology` — Abikan:Radiology; no provider.
- `abikan.accountant` — Abikan:Accountant; no provider.
- `abikan.admin` — technical full access; provider exists.

No user was created, retired, enabled, disabled, renamed, or edited during this audit.

### Password handling

- Hospital EMR signs into OpenMRS and holds the OpenMRS session cookie.
- There is no Hospital EMR password store, reset screen, recovery workflow, or password endpoint.
- The provisioning script can set the shared development password when creating development users. That is test setup, not a production workflow.
- Live SuperAdmin has `Edit User Passwords`; ordinary departmental accounts do not.

Password creation/reset/recovery should remain in controlled OpenMRS/IT administration unless the hospital defines an identity-verification policy.

## 3. Providers

OpenMRS provider records are separate from user records and link through the same person.

Observed provider mappings:

- Technical: `abikan.admin`, `admin.abikan`.
- Clinical: `doctor.abikan`, `abikan.doctor`.
- Nursing: `nurse.abikan`, `abikan.nurse`.
- Radiology: `radiology.abikan`.
- No provider: Reception/Registration, Pharmacy, Laboratory, Accountant, and `abikan.radiology`.

The Doctor consultation save requires a provider mapping. Radiology report attribution also has a provider-backed preferred account. Non-clinical staff do not need providers merely to sign in.

The live privilege catalogue does not contain privileges literally named `Add Providers` or `Edit Providers`. It exposes `Get Providers`, `View Providers`, `Manage Providers`, and provider-management API/dashboard privileges. SuperAdmin has `Manage Providers`; departmental users have `Get Providers` through inherited roles.

A future staff workflow must create a provider only for roles that clinically author records. “Create staff” must not automatically mean “create provider.”

## 4. Roles and Permissions

### Hospital EMR roles observed live

| Role | Inherits | Direct privileges |
|---|---|---|
| Abikan:Reception | Registration-App | none |
| Abikan:Registration | Registration-App | none |
| Abikan:Doctor | Clinical-App, Provider | none |
| Abikan:Nursing | InPatient-App | none |
| Abikan:Pharmacy | Bahmni-App-User-Login | dispense + patient, visit, encounter, order, concept and provider reads |
| Abikan:Pharmacy Inventory | Abikan:Pharmacy | `abikan:pharmacy:inventory` |
| Abikan:Laboratory | Lab | patient, visit, encounter, concept and provider reads |
| Abikan:Radiology | Radiology-App | `Get Orders` |
| Abikan:Accountant | Bahmni-App-User-Login | `abikan:accountant` + limited patient/visit/provider reads |

### Effective clinical privileges

- Doctor: Add/Edit/Get Orders, Observations, and Encounters.
- Radiology: Get Orders; Add/Edit/Get Observations and Encounters.
- Nursing: Add/Edit/Get Encounters; Get Observations; Assign Beds.
- Reception: Add/Edit/Get Encounters and Observations; patient and visit writes.
- Laboratory: Get Orders and Encounters; no observed Add/Edit Orders or Observations.
- Pharmacy: Get Orders and Encounters; dispense privilege; no observed Add/Edit clinical records.
- Accountant: no observed Orders, Observations, or Encounters privileges.

### Important inherited-privilege warning

Several preferred departmental development accounts still have effective `Edit Users` and `Get Users`, inherited from existing Bahmni/OpenMRS roles. The Laboratory role was corrected on 26 Aug 2026 by removing `Bahmni-App-User-Login`; live verification confirms `lab.abikan` no longer has either privilege while retaining its legitimate Laboratory reads. Broad OpenMRS privilege checks remain unsafe for Hospital EMR Admin authorization.

Future Admin operations need dedicated Hospital EMR privileges per action, for example separate view/create/disable/assign permissions, plus server-side validation of which roles may be assigned. No such privileges were created in this audit.

## 5. Departments

The implemented operational workplaces are static controlled configuration:

- Reception
- Clinical
- Nursing
- Pharmacy
- Laboratory
- Radiology
- Accountant
- Administration

Department access is represented by:

1. OpenMRS roles and effective privileges.
2. Static Hospital EMR privilege-to-workspace checks.
3. Optional OpenMRS user property `abikan.workplace` for the preferred landing department.
4. Static navigation per workplace.

There is no department table in Hospital EMR. `abikan.workplace` does not grant access; the matching privilege/role check still controls the workspace.

Administration is not a clinical department. It is a technical landing/workplace.

Recommendation:

- Do not let a normal Admin create, rename, or delete departments.
- Keep department definitions as controlled product/configuration.
- Staff-to-department assignment is a reasonable future capability only after the hospital defines who may assign which approved roles.
- Enabling/disabling a whole department is a policy and operational-safety decision, not a casual settings toggle.

## 6. Locations

The live OpenMRS installation has **32 non-retired locations**. Relevant groups include:

- Facility: Bahmni Hospital.
- Reception/session: Registration Desk.
- Clinical: OPD-1, OPD-2, Emergency.
- Existing demo wards/rooms: General Ward, Pediatric Ward, their child rooms, Emergency Ward, Test Ward, Child test.
- Hospital inpatient areas: Hawawu Maternity Ward, Aisha Children Ward, Emergency Room, Bronze 208, Silver 206/207, Gold Rooms 202/203/204/210/211/212/213, Platinum Room 209, Diamond 214, Pre Labour Room.
- Theatre locations: General OT, Orthopaedic OT.
- Unknown Location.

Read-only aggregate usage confirms these are not simply menu labels:

- OPD-1: 37 visits, 21 encounters, 46 observations.
- Bahmni Hospital: 9 visits.
- Emergency: 4 visits.
- Registration Desk: 2 visits and 8 appointments.
- Hawawu Maternity Ward: 2 visits.
- Encounter activity also exists in Bronze 208, Gold Rooms 202/203, Platinum Room 209, and Silver 207.
- Child test, Test Ward, and Unknown Location had no observed operational activity.

Current hidden session-location mapping:

- Reception → Registration Desk.
- Clinical → OPD-1.
- Nursing → General Ward.
- Pharmacy, Laboratory, Radiology, Accountant, Administration → Registration Desk.

Hospital EMR deliberately distinguishes workplace from location. Staff do not select OPD codes, rooms, beds, or Registration Desk as their department.

Location creation, tags, hierarchy, login-location status, admission-location status, and retirement should remain OpenMRS administration. A future Hospital EMR Admin may safely view the current operational mapping, but should not edit locations in the first scope.

No location was created, renamed, retired, deleted, or retagged.

## 7. Hospital Services

### Radiology

- The canonical staff-facing menu is the hospital-approved `hospitalName` list in `src/config/radiologyMenu.ts`.
- It contains exactly 42 approved names: 14 Ultrasound Scan and 28 Radiography / Fluoroscopy.
- Each orderable item maps to an OpenMRS Radiology/Imaging Procedure concept and the Radiology Order type.
- Odoo service products are mapped by concept UUID; configuration-created stubs have `list_price = 0`.
- The Radiologist currently enters the price for an unbilled examination. That per-order amount is copied to the Odoo sale line; the Accountant only collects.

The 42 names are approved controlled content, not an Admin free-text catalogue. Arbitrary concept creation must remain outside Hospital EMR. Whether prices become a managed catalogue instead of per-examination entry requires hospital policy.

### Laboratory

- Display metadata and hospital names come from `server/patient-account/data/laboratory_catalogue.csv`.
- Concept bindings come from the laboratory map/runtime JSON and OpenMRS concepts.
- The live charge uses the mapped Odoo product `list_price`; placeholder price `1.00` is refused.
- The CSV price is a fallback/display source when no live Odoo price is available.
- Laboratory staff process orders/results; there is no Laboratory price-edit screen.

The current split source means a future catalogue screen must not silently write one side and leave the other stale. Canonical naming and pricing ownership require an explicit decision.

### Consultation

- OpenMRS owns the visit and clinical authorship.
- Odoo owns the posted charge/invoice.
- The consultation product is a generic service stub.
- The Doctor currently enters a positive NGN fee for the visit; the amount is copied to the Odoo sale line.
- The Accountant cannot set it.

This is current departmental ownership, not evidence that Hospital Admin should edit consultation fees.

### Pharmacy

- Hospital catalogue metadata maps to OpenMRS Drug/Concept records.
- Odoo `product.product` owns sellable product, availability, stock, and `list_price`.
- The current Pharmacy workspace can add/edit a medicine, set availability, and change the development selling price.
- `Abikan:Pharmacy Inventory` separately authorizes stock receipt/adjustment.
- Stock receipt explicitly preserves selling price.

Pharmacy already owns catalogue changes in the operational UI. Moving or duplicating price control into Admin would create conflicting ownership. Final production price ownership is a hospital policy decision.

### Registration

- Individual Card: NGN 2,000.
- Family Card: NGN 5,000.
- These values live in controlled JSON configuration.
- Registration API setup synchronizes the matching Odoo service products/pricelist and Reception creates the fee for a visit.

There is no Admin registration-price screen. These are deployment-controlled values today.

### Accommodation

- Sixteen approved wards/rooms are static controlled configuration.
- Odoo accommodation product `list_price` is the live tariff.
- SuperAdmin/System Developer can edit these prices through the only implemented Administration settings screen.

This existing capability is real, but its policy owner and missing actor-level audit trail must be reviewed before production use.

## 8. Pricing Ownership

Observed current ownership:

- Consultation fee — Doctor enters a per-visit fee.
- Radiology examination fee — Radiologist enters a per-order fee.
- Laboratory fee — mapped Odoo product catalogue price; Laboratory does not edit it in Hospital EMR.
- Pharmacy selling price — Pharmacy can currently edit the Odoo product price from Drug Catalogue.
- Registration card fee — controlled JSON configuration synchronized to Odoo.
- Accommodation tariff — technical Admin edits Odoo product price.
- Accountant — collects residual on posted invoices; does not set prices.

There is no single coherent “Admin owns all prices” rule. Do not create one in code.

Required policy decisions:

- whether consultation and Radiology remain case-by-case departmental fees or become approved catalogues;
- who approves and who enters Laboratory and Pharmacy prices;
- whether registration/accommodation prices are operational configuration, finance configuration, or board-approved controlled data;
- whether one person may both change a price and collect payment.

## 9. Odoo Boundary

Hospital EMR currently reads or writes Odoo:

- products and product categories;
- pricelists;
- sale shops/orders/lines;
- customer invoices and residuals;
- customer payments and reconciled invoices;
- Cash (`CSH1`) and Bank (`BNK1`) payment journals;
- customers/patients;
- currencies and invoice currency;
- product taxes;
- stock products, locations, moves, pickings, and quantities;
- payment states including unpaid, partial, in payment, paid, and reversed.

Live read-only inventory observed:

- 1,810 products;
- 6 pricelists;
- 37 sale orders;
- 36 customer invoices;
- 19 payments;
- 9 journals;
- 1 credit/refund move;
- active EUR, NGN, and USD;
- company currency USD;
- active 15% sales and purchase taxes.

These observations reinforce that Odoo is an accounting and inventory system, not an Admin form model.

Keep Odoo-only:

- chart of accounts;
- journal setup and payment methods;
- company/currency/country configuration;
- taxes and fiscal policy;
- bank reconciliation;
- credit notes and payment reversals;
- POS and payment-acquirer configuration;
- vendor bills and supplier accounting;
- statutory, aged-receivable, and accounting reports;
- financial period/lock controls;
- unrestricted product/pricelist administration.

Hospital EMR may expose narrow operational actions already required by a department. It must not become an Odoo administration console.

## 10. RBAC Architecture

### Current flow

1. OpenMRS authenticates the user and owns the session.
2. Hospital EMR loads the OpenMRS user, roles, effective privileges, user properties, and hidden session location.
3. Frontend route guards map privileges/roles to workspaces.
4. Every protected `abikan-api` handler re-reads the OpenMRS session and applies its own department check.
5. Odoo credentials stay server-side; staff do not sign into Odoo through Hospital EMR.

### Duplication

Authorization is intentionally duplicated at two enforcement layers:

- frontend for navigation and clear access denial;
- backend for actual security.

The frontend is not authoritative.

### Current bypass

`SuperAdmin` / `System Developer` is explicitly accepted across most backend department guards. It therefore bypasses department separation. That is acceptable for a technical development account but not for a normal Hospital Administrator.

### Required future rule

No future Admin button may proxy arbitrary OpenMRS REST calls.

Every operation must have:

- a dedicated server endpoint;
- a dedicated narrow Hospital EMR privilege;
- an allow-list of assignable roles/fields;
- validation that prevents granting SuperAdmin/System Developer or arbitrary privileges;
- a durable audit event with real OpenMRS actor, target, before/after values, timestamp, and outcome.

## 11. Audit Logging

### OpenMRS / Bahmni

- Clinical resources expose creator/date/audit information.
- Bahmni Admin is configured with an existing Audit Log page under `app:admin`.
- The live audit log contained 101 events dated 12–24 Aug 2026.
- Logging is enabled (`bahmni.enableAuditLog=true`, `auditlog.started=true`) but is not mandatory (`auditlog.mandatory=false`).
- Observed coverage was mostly sign-ins and screen views, with only one clinical-edit event. It is not a complete before/after administration or configuration history.
- OpenMRS resources expose `auditInfo`, but that metadata is not a complete change history.

### Odoo

- Odoo records `create_uid`, `create_date`, `write_uid`, and `write_date` on models and has model chatter where enabled.
- Payments expose create user/date and reconciled invoices.
- Hospital EMR's Odoo writes use the server-side service account. Odoo therefore often records the service user, not the signed-in hospital staff member.
- No dedicated Odoo audit module was installed. `ir.logging` and `privacy.log` were empty.
- Existing evidence was 246 user login/access records, 5,297 chatter messages, and 81 tracked field changes. This is selective operational history, not a comprehensive immutable audit trail.

### Hospital EMR

- There is no durable Hospital EMR administrative audit-log store.
- Several responses include `recordedBy`, and some financial objects carry idempotency/request references.
- `recordedBy` in a response is not a durable audit trail.
- Accommodation price changes have no Hospital EMR actor event; Odoo sees the service account.

Before any sensitive Admin write is implemented, actor-level audit logging is a requirement, not an optional enhancement.

## 12. Candidate Admin Responsibilities

Classification:

- **A** — safe to expose in Hospital EMR with explicit read authorization.
- **B** — possible, but requires hospital policy, narrow write authorization, validation, and audit.
- **C** — should remain in OpenMRS/Bahmni/Odoo administration.
- **D** — unsafe to expose through Hospital EMR Admin.

### A — safe first-scope capabilities

- View a limited staff directory: name, username, enabled/disabled state, approved department roles, preferred workplace, and provider-ready/not-required status.
- View a department-access matrix derived from approved Hospital EMR roles.
- View approved operational departments; no create/rename/delete.
- View hidden department-to-session-location mapping; no location edit.
- View approved service readiness: approved name, department, concept mapped/not mapped, billing product mapped/not mapped, price configured/not configured.
- View administrative action history once a reliable scoped audit source exists.

### B — requires hospital policy before implementation

- Create a staff account.
- Disable/enable a staff account.
- Assign or remove an approved department role.
- Create/retire a provider relationship for a clinician.
- Set the preferred workplace.
- Change hospital identity/contact details.
- Enable/disable service availability.
- Change consultation, Radiology, Laboratory, Pharmacy, Registration, or Accommodation prices.
- Change the approved service catalogue.
- Allow Hospital Admin read access to patient billing or payments.
- Allow Hospital Admin any clinical read access.
- Department-wide enable/disable controls.
- Retain the existing accommodation-price write under a future Hospital Admin role.

### C — keep in source-system administration

- OpenMRS user password reset/recovery.
- OpenMRS location hierarchy/tags/login/admission configuration.
- Controlled OpenMRS concept, order type, encounter type, form, program, and provider administration.
- Bahmni app/implementer configuration.
- Odoo product/pricelist master administration outside a narrowly approved operational flow.
- Odoo chart of accounts, journals, taxes, currency, reconciliation, refunds/reversals, POS, reporting, and financial setup.
- PACS/DICOM configuration.
- OpenELIS/system laboratory dictionary administration.
- Server, container, proxy, certificate, backup, and database administration.

### D — unsafe to expose

- Arbitrary role or privilege creation/assignment.
- Granting `SuperAdmin`, `System Developer`, `app:admin`, or arbitrary technical privileges.
- Arbitrary OpenMRS REST/API access.
- Arbitrary concept or order-type creation.
- Editing/voiding/deleting clinical observations, diagnoses, encounters, or orders from Admin.
- Editing/voiding/deleting patients from Admin.
- Direct database administration or SQL.
- Direct Odoo model/method console.
- Credit-note/payment-reversal shortcuts without accounting controls.
- Viewing or exporting all patient clinical data merely because the user is “Admin.”
- Exposing infrastructure credentials, integration credentials, or service-account secrets.

## 13. Capabilities That Must Remain Outside Hospital EMR

Hospital EMR Admin must not expose:

- OpenMRS database or global-system administration.
- Arbitrary concept, form, order type, observation, encounter, or clinical-data manipulation.
- Arbitrary RBAC escalation.
- OpenMRS module, scheduler, implementation ID, REST, or global-property management.
- Odoo accounting configuration, chart of accounts, taxes, journals, bank reconciliation, credit notes, reversals, POS, statutory reports, or company currency.
- PACS, DICOM, OpenELIS system, server, container, proxy, certificate, backup, or database configuration.
- Password recovery without a hospital-approved identity process.

## 14. Security / Privacy

Current SuperAdmin has access to:

- patient demographics;
- visits, encounters, observations, diagnoses, orders, medications, and clinical notes through broad OpenMRS privileges;
- all implemented operational workspaces;
- Patient Account, billing, invoices, receipts, and payment entry;
- staff users, roles, privileges, providers, and locations;
- configuration and destructive OpenMRS operations.

That is technical full access, not least privilege.

A future Hospital Administrator should default to:

- staff/configuration metadata only;
- no patient search;
- no clinical notes, diagnoses, medications, observations, encounters, or orders;
- no billing/payment history unless separately approved;
- no payment collection;
- no department impersonation/switching.

Operational Admin and Clinical/Financial Admin should be separate permissions. A hospital title must not imply Doctor + Nurse + Radiologist + Pharmacist + Accountant.

Additional findings:

- Odoo credentials correctly remain server-side.
- Backend department checks prevent frontend-only authorization.
- Existing broad inherited `Edit Users` privileges make generic OpenMRS privilege reuse unsafe.
- Existing SuperAdmin bypasses must not be copied into a new Hospital Admin role.
- Staff information itself is sensitive and should be limited to fields required for account administration.

## 15. Hospital Decisions

The hospital must decide:

1. Is Hospital Administrator distinct from IT/System Administrator and SuperAdmin?
2. Who may view staff accounts and department assignments?
3. Who may create and disable staff, and is dual approval required?
4. Which approved roles may Hospital Admin assign? SuperAdmin/System Developer must be excluded.
5. Which staff types require provider records?
6. Who verifies identity for password reset/recovery?
7. May Hospital Admin see any patient clinical data?
8. May Hospital Admin see billing/payment data, or is that Finance only?
9. Who owns each price family: Consultation, Radiology, Laboratory, Pharmacy, Registration, Accommodation?
10. May the same person change prices and collect payments?
11. Who approves service availability or changes to an approved catalogue?
12. Are the 42 Radiology names immutable except through a formal clinical-governance process?
13. Who may manage OpenMRS locations, and is that IT/implementation rather than Hospital Admin?
14. What retention, review, and approval rules apply to staff/role/price audit logs?

## 16. Recommended Admin Workspace Scope

### Phase 1

Build no general settings console.

If implementation is approved, start with:

- **Staff** — read-only list and staff setup status.
- **Access** — read-only approved department-role matrix.
- **Services** — read-only approved-service mapping and price-readiness status.
- **Activity** — scoped administrative history only after a reliable source exists.

The home screen should be a small task-oriented index, not KPI cards. The audit found no trustworthy administrative KPI that staff need to act on.

### Phase 2, only after policy

- Create/disable staff.
- Assign approved department roles and preferred workplace.
- Create provider mapping when required.
- Controlled service availability.
- One or more explicitly owned price workflows.

Each write requires a dedicated privilege, allow-listed API, confirmation, idempotency where applicable, and durable actor audit.

### Do not carry forward

- Do not give Hospital Admin the current department switcher.
- Do not use SuperAdmin as the normal production account.
- Do not use `app:admin` as a blanket authorization.
- Do not replicate OpenMRS/Bahmni/Odoo administration.
- Do not add a department table merely to mirror static approved departments.

## Hospital Admin — Staff Accounts

Implemented scope:

- `#/staff-accounts` is a working Administration route.
- The directory loads existing enabled and disabled departmental users from OpenMRS.
- Staff can be searched by name or username and filtered by department or account status.
- The list shows human-readable name, username, department, role, account status, and clinical-profile status. It does not show passwords, technical identifiers, or raw privileges.
- Add Staff collects full name, username, one or more approved departments, initial sign-in password, and active status. No HR, patient, billing, or contact fields were added.
- The current OpenMRS user-create operation requires an initial password. Hospital EMR sends it directly to OpenMRS through the tightly controlled server-side administration identity after authorizing the signed-in Admin. It is not logged, stored, returned, shown after submission, or written to the administrative audit history. Password reset and recovery remain outside this workspace.
- Duplicate usernames are rejected before person/user creation. Create submissions carry an idempotency key to prevent browser double-submit duplication.
- OpenMRS Person and User remain the identity source of truth. No Hospital EMR user, password, permission, or provider table was created.
- Disable/enable changes only the OpenMRS User retired state. It never deletes a user or person, retires a provider, or edits historical clinical/financial records.
- Disabling requires explicit confirmation and states that the staff member cannot sign in. Historical authorship and provider attribution remain intact.
- Technical accounts, the acting Admin's own account, `SuperAdmin`, `System Developer`, and `Privilege Level: Full` accounts cannot be changed through this workflow.

Exact approved role mapping:

| Department shown to staff | OpenMRS role used internally | Role shown to staff | Provider required |
|---|---|---|---|
| Clinical | `Abikan:Doctor` | Doctor | Yes |
| Nursing | `Abikan:Nursing` | Nurse | Yes |
| Reception | `Abikan:Reception` (`Abikan:Registration` remains compatible for existing users) | Receptionist | No |
| Laboratory | `Abikan:Laboratory` | Laboratory Staff | No |
| Radiology | `Abikan:Radiology` | Radiologist | Yes |
| Pharmacy | `Abikan:Pharmacy` | Pharmacist | No |
| Accountant | `Abikan:Accountant` | Accountant | No |

Provider handling:

- Clinical, Nursing, and Radiology access requires an OpenMRS Provider.
- Provisioning first checks active providers by person and username identifier. It reuses an existing provider and creates at most one missing provider.
- Access updates ensure the required provider before changing roles. A provider is not retired when clinical access is later removed because historical attribution must remain valid.
- A provider failure is reported clearly. If the user was already created, Hospital EMR safely retires that new user account, records both the failed provider link and compensation, and reports that technical support must complete the clinical profile before enabling it. It does not delete or retire providers or people.

RBAC and actor attribution:

- Backend and frontend both accept only `abikan:admin:staff`, `SuperAdmin`, or `System Developer`.
- The normal production role is `Abikan:Hospital Admin`. Its final direct privileges are only `abikan:admin:staff` and `Get Providers`; the latter is required because this OpenMRS SessionController resolves the current provider on every session read and otherwise rejects the login. It has no user-edit, role-management, privilege-management, provider-management, `app:admin`, SuperAdmin, or System Developer authority.
- Doctor, Radiology, Accountant, Reception, and Nursing access do not satisfy the Admin guard.
- The browser never supplies role names or privileges. It supplies approved department IDs; the server owns and enforces the department-to-role allow-list.
- Generic role assignment, arbitrary privileges, SuperAdmin/System Developer, locations, concepts, accounting, and infrastructure settings are not accepted.
- The acting Admin's live OpenMRS session authorizes the Hospital EMR request. The allow-listed OpenMRS staff/person/provider operation then uses the existing server-side technical identity, so the Hospital Administrator does not need the privileges of every role being assigned.
- Hospital EMR durably records the real signed-in actor, target, action, before/after state, department changes, provider-link outcome, request ID, timestamp, and success/failure in a dedicated SQLite store. Passwords, cookies, authorization headers, tokens, and secrets are redacted and never supplied by callers.

Existing development users remain managed by their live identity and role/provider relationships; no username-specific application logic was added. `doctor.abikan`, `radiology.abikan`, and `accountant.abikan` are covered by the existing-user mapping tests. No existing account was changed or replaced.

Live verification on 25 Aug 2026 loaded 15 existing departmental accounts. `doctor.abikan`, `radiology.abikan`, and `accountant.abikan` were present, active, and mapped to Clinical/Doctor, Radiology/Radiologist, and Accountant/Accountant respectively. `doctor.abikan` and `radiology.abikan` had ready clinical profiles. The separate existing `abikan.radiology` account was correctly shown as needing a clinical profile; it was not modified.

## Hospital Admin — Department Access

Implemented scope:

- `#/department-access` is a working Administration route.
- It shows one row per staff member and approved department, with staff name, username, department, human-readable role, and account status.
- Search, department filter, and Active/Disabled filter are available.
- Edit Access supports multiple approved departmental roles without overwriting unrelated existing roles.
- Removing an approved department removes only its approved department role. Pharmacy inventory access is removed with Pharmacy access so it cannot preserve hidden Pharmacy access.
- At least one approved department must remain. Admin can disable an account when all operational access should stop.
- The selected default department must be one of the assigned departments and is stored in the existing `abikan.workplace` user property. The property remains a landing preference, not an authorization source.
- Departments are static approved configuration backed by existing roles. No department table, location rename, or location-management UI was added.
- Live verification loaded 16 department-access rows from the 15 existing accounts, including the existing multi-department access on `abikan.radiology`. No access was changed during verification.

Remaining policy decisions:

- Assign the prepared `Abikan:Hospital Admin` role only after the hospital names the authorized staff.
- Confirm the hospital's initial-password handoff and mandatory-change policy. Account creation is functional, but OpenMRS does not provide a Hospital EMR invite or forced-password-change workflow.
- Decide whether dual approval is required for create, disable, or department-access changes.
- Decide the required retention/review policy for administrative audit history before expanding beyond this scope.

## Hospital Admin — Role Provisioning

Hospital Admin manages **approved departmental roles**. Technical SuperAdmin controls the underlying OpenMRS privilege definitions. The Admin UI still exposes only the seven approved departments; it does not list privileges, SuperAdmin, or role-creation controls.

### Why the original assignment failed

Historically, Department Access posted allow-listed OpenMRS role UUIDs to `POST /openmrs/ws/rest/v1/user/{uuid}` using the signed-in Admin's session cookie.

OpenMRS then requires the assigner to already hold **every privilege of the role being assigned**. Custom Hospital EMR privileges created after SuperAdmin was first populated are **not** added to SuperAdmin automatically.

Live `admin.abikan` before the correction:

- UUID `e4fafa50-51a2-4b9a-81dd-a6615d014379`
- enabled
- roles `SuperAdmin`, `Provider`
- 293 privileges
- missing `abikan:accountant`, `abikan:pharmacy:inventory`, and `abikan:admin:staff`

Assigning Radiology + Reception + Accountant to `radiology.abikan` therefore failed with HTTP 502 wrapping OpenMRS `You must have privilege {0} in order to assign it.` The user was unchanged. No partial role write occurred.

`admin.abikan` was already the development SuperAdmin account. It was not confused with `Abikan:Hospital Admin`. The gap was SuperAdmin's frozen privilege catalogue, not a missing second permission system. `abikan.admin` could assign the same roles because it also has `System Developer` and `Privilege Level: Full`, which include the later custom privileges. Hospital Admin was not given those operational privileges.

### How development SuperAdmin provisioning was corrected

`scripts/provision-dev-users.py` now merges every privilege required by the approved Hospital EMR department roles onto the existing SuperAdmin role, without replacing SuperAdmin's existing privileges and without assigning `System Developer`.

After that merge, `admin.abikan` can assign the approved departmental roles through the technical path. The final Hospital Administrator path no longer depends on this SuperAdmin privilege merge: Hospital EMR authorizes the real actor, validates the seven approved department IDs, and performs only that bounded operation with its server-side technical identity. Privilege definitions remain technical/system administration. The Hospital Admin UI still cannot:

- assign arbitrary OpenMRS privileges
- create OpenMRS roles
- assign SuperAdmin / System Developer / Privilege Level: Full
- expose Edit Users, Get Orders, Add Observations, or similar toggles

Runtime authorization uses the signed-in OpenMRS session's roles and privileges. A user-search representation can lag behind a just-assigned department role; using that search would deny Accountant or Reception even when the staff member can already open those workspaces.

The assigner-must-hold-privileges limitation is resolved without granting departmental or technical authority to Hospital Admin. `Abikan:Hospital Admin` has only the dedicated Admin privilege plus the session-required provider read. The server-side orchestration identity performs the allow-listed OpenMRS role mutation; arbitrary roles and privileges remain rejected before that call.

### Approved departmental roles

| Department shown to staff | OpenMRS role | Runtime access |
|---|---|---|
| Clinical | `Abikan:Doctor` | Doctor workspace + Clinical API |
| Nursing | `Abikan:Nursing` | Nursing workspace + Nursing API |
| Reception | `Abikan:Reception` | Reception workspace + Reception API |
| Laboratory | `Abikan:Laboratory` | Laboratory workspace + Laboratory API |
| Radiology | `Abikan:Radiology` | Radiology workspace + Radiology API |
| Pharmacy | `Abikan:Pharmacy` | Pharmacy workspace + Pharmacy API |
| Accountant | `Abikan:Accountant` | Accountant workspace + Accountant API |

A staff member may hold several of these at once. Access updates replace the approved-department set and keep unrelated non-department roles. Adding Accountant to a Radiologist keeps Radiology. Removing Reception from Radiology + Reception + Accountant leaves Radiology + Accountant.

### Runtime access

Assigned departments appear as separate workspaces. Radiology does not become Accountant because Accountant was added; the user can switch to Accountant while Radiology remains the Radiology workspace.

- Radiology only → Radiology
- Radiology + Reception → Radiology, Reception
- Radiology + Accountant → Radiology, Accountant
- Radiology + Reception + Accountant → Radiology, Reception, Accountant
- Unassigned Doctor / Nursing / Laboratory / Pharmacy remain denied in navigation, route guards, and department APIs
- Department users cannot open Administration

### Provider handling

Clinical, Nursing, and Radiology still require an OpenMRS Provider. Existing providers for `doctor.abikan` and `radiology.abikan` are reused. `accountant.abikan` does not require a provider. No duplicate providers are created.

### Error handling

If OpenMRS refuses an assignment, Admin shows that department access could not be updated because the administrator account does not have permission to assign the role. Generic OpenMRS stack traces are not shown. Success is not reported when OpenMRS rejected the write.

### Remaining limitations

- System Settings remains Coming soon.
- `Abikan:Hospital Admin` is provisioned as a role but is not assigned to a live hospital user in this environment.
- OpenMRS still records only latest creator/modifier metadata, not a full before/after administrative history.
- Assigning Accountant does not grant SuperAdmin, user editing, or a second ledger. Odoo remains the ledger; Hospital EMR remains the Cash/Bank cashier wrapper.

### Live verification (25 Aug 2026)

`admin.abikan` after provisioning: still SuperAdmin + Provider; enabled; UUID unchanged; now includes `abikan:accountant`, `abikan:admin:staff`, and `abikan:pharmacy:inventory`.

Assignment of Radiology + Reception + Accountant to `radiology.abikan` as `admin.abikan` returned HTTP 200. OpenMRS roles were `Abikan:Radiology`, `Abikan:Reception`, and `Abikan:Accountant`. Radiology, Reception, and Accountant APIs returned 200. Doctor, Nursing, Laboratory, Pharmacy, and Admin APIs returned 403. SuperAdmin and raw privilege payloads were rejected by the Admin API.

Browser login as `radiology.abikan` showed Switch department: Reception, Radiology, Accountant. Radiology remained the Radiology worklist. Reception and Accountant opened as their own workspaces. `#/doctor` showed department access denied.

Remove Reception left Radiology and Accountant allowed and Reception denied. Restoring Reception restored all three.

The development baseline requires `radiology.abikan` to remain Radiology-only. After verification it was restored to `Abikan:Radiology` only. Radiology API 200; Reception and Accountant APIs 403. Existing providers for `radiology.abikan` and `doctor.abikan` were unchanged. `accountant.abikan` still has no provider.

No patients, visits, orders, invoices, or payments were modified. No new TEST staff account was created.

## Department Role Combination Investigation

Date: **25 Aug 2026 (continued)**

### Question

Are combinations such as Clinical + Radiology, Nursing + Radiology, or Clinical + Nursing blocked by OpenMRS/Bahmni, by Hospital EMR, or by configuration?

### Method

Read-only inspection of live OpenMRS role definitions (`GET /role/{uuid}?v=full`) and Hospital EMR backend allow-list code in `hospital_admin.py`. No roles or privileges were changed during this investigation. No existing development account departmental access was modified.

### Live OpenMRS role structure (approved Hospital EMR departments)

| Role | Inherits | Direct privileges |
|---|---|---|
| `Abikan:Doctor` | `Clinical-App`, `Provider` | none |
| `Abikan:Nursing` | `InPatient-App` | none |
| `Abikan:Reception` | `Registration-App` | none |
| `Abikan:Laboratory` | `Lab` | `Get Concepts`, `Get Encounters`, `Get People`, `Get Providers`, `Get Visits`, `View Patients` |
| `Abikan:Radiology` | `Radiology-App` | `Get Orders` |
| `Abikan:Pharmacy` | `Bahmni-App-User-Login` | `bahmni:clinical:dispense`, patient/visit/order read privileges |
| `Abikan:Accountant` | `Bahmni-App-User-Login` | `abikan:accountant`, patient/visit read privileges |
| `Abikan:Hospital Admin` | none | `abikan:admin:staff`, `Get Providers` (required by OpenMRS session loading) |

None of the Hospital EMR department roles inherit another Hospital EMR department role. Overlap between roles comes only from shared Bahmni base roles (`Bahmni-App-User-Login`, `Provider`, etc.) and is not a Hospital EMR-imposed mutual-exclusion rule.

### Findings by combination

| Combination | Allowed by Hospital EMR allow-list? | OpenMRS mutual-exclusion rule found? | Cause if blocked in practice |
|---|---|---|---|
| Clinical + Radiology | **Yes** — both department IDs pass `validate_departments` | **No** — OpenMRS allows multiple roles on one user | Assigner must hold privileges of both roles (OpenMRS configuration), not a combination matrix |
| Nursing + Radiology | **Yes** | **No** | Same assigner-privilege rule |
| Clinical + Nursing | **Yes** | **No** | Same assigner-privilege rule |
| Radiology + Reception + Accountant | **Yes** — already live-verified previously | **No** | Same assigner-privilege rule |

### Classification

**A. OpenMRS/Bahmni security restriction:** OpenMRS requires the assigner to hold every privilege contained in a role before assignment. That can block an under-privileged Hospital Admin from assigning a role, but it is **not** a rule forbidding specific department pairs.

**B. Hospital EMR product restriction:** Hospital EMR exposes only seven approved department IDs. There is **no hard-coded combination matrix** (no code forbids Doctor + Radiologist, Nurse + Radiologist, etc.). `reject_arbitrary_authority()` blocks raw `roles` / `privileges` from the browser.

**C. Provisioning/configuration problem:** If assignment fails, the usual cause is SuperAdmin (or the assigner) missing a later custom privilege such as `abikan:accountant`, not OpenMRS rejecting the pairing itself.

### Deliberate security boundaries

- **Technical SuperAdmin / System Developer** — hidden from staff directory; not assignable through Admin UI.
- **Hospital Administrator (`Abikan:Hospital Admin`)** — separate from department staff; does not inherit clinical/financial workspace privileges.
- **Department staff** — workspace access comes from session roles/privileges after approved assignment.

There is **no deliberate Hospital EMR boundary** preventing a staff member from holding both Clinical and Radiology (or Nursing and Radiology) if an authorized administrator assigns both approved roles.

## Hospital Administrator Account Model

Date: **25 Aug 2026**

### Three account classes

| Class | Example dev account | Purpose | Admin Workspace | Assign departments | Create Hospital Admin |
|---|---|---|---|---|---|
| Technical SuperAdmin | `admin.abikan`, `abikan.admin` | Underlying OpenMRS/Bahmni configuration | Yes | Yes | Yes (technical SuperAdmin only) |
| Hospital Administrator | `hospitaladmin.abikan`, `hospitaladmin.test` | Staff accounts + approved department access | Yes (via `abikan:admin:staff`) | Yes (seven approved only) | **No** |
| Department staff | `doctor.abikan`, `radiology.abikan`, … | Departmental workspaces | No | N/A | No |

### `Abikan:Hospital Admin` role

- **Exists:** yes (provisioned by `scripts/provision-dev-users.py`).
- **Inherits:** no OpenMRS/Bahmni app roles — not `System Developer`, not `SuperAdmin`, not `Clinical-App`.
- **Direct privileges:** `abikan:admin:staff` plus `Get Providers`, which is the minimum read needed by this installation's OpenMRS SessionController. No native user, person, provider, role, privilege, configuration, or `app:admin` management privilege is assigned.
- **Admin Workspace access:** yes — frontend checks `abikan:admin:staff` (or technical SuperAdmin).
- **Staff Accounts / Department Access:** yes — live HTTP 200 for `hospitaladmin.abikan` and `hospitaladmin.test`.
- **Create/enable/disable users:** yes — within approved workflow.
- **Assign approved departmental roles:** yes — only through the allow-listed Hospital EMR API and its server-side orchestration identity.
- **Assign another Hospital Administrator:** **no** — blocked at `POST /admin/staff` unless actor is technical SuperAdmin.
- **Assign SuperAdmin / System Developer:** blocked — not in department allow-list; raw role payloads rejected.
- **Accommodation Prices / technical settings:** **no** — HTTP 403 for Hospital Administrator-only accounts.

### Administrator creation UI

Technical SuperAdmin (`admin.abikan`) sees **Account type**:

- **Staff** — existing department checkbox flow.
- **Hospital Administrator** — separate option; no department checkboxes; no provider created.

Hospital Administrator-only users do **not** see the Hospital Administrator account type option (`capabilities.canCreateHospitalAdministrator: false`).

SuperAdmin, System Developer, and arbitrary OpenMRS roles are never exposed as selectable options.

### Live verification (25 Aug 2026)

**Provisioned development account:** `hospitaladmin.abikan` / `Admin123` — `Abikan:Hospital Admin` only; Admin APIs 200; operational department APIs denied; not SuperAdmin.

**UI/API-created test account:** `hospitaladmin.test` / `Temporary123` — created by `admin.abikan` through `POST /openmrs/abikan-api/admin/staff` with `accountType: hospital_administrator`.

Verified for `hospitaladmin.test`:

- account created with `Abikan:Hospital Admin` only
- can sign in
- Admin Staff + Department Access APIs return 200
- **not** SuperAdmin or System Developer (final hardened session has two privileges: `abikan:admin:staff` and session-required `Get Providers`)
- cannot create another Hospital Administrator (403 `hospital_administrator_creation_forbidden`)
- cannot open Accommodation Prices (403)
- raw `roles: ["SuperAdmin"]` in access payload rejected (422 `arbitrary_privilege_rejected`)

Verified for `hospitaladmin.abikan`:

- same Admin access boundary
- cannot create Hospital Administrator accounts (403)

Verified preserved accounts unchanged:

- `doctor.abikan` → `Abikan:Doctor`
- `radiology.abikan` → `Abikan:Radiology` only
- `accountant.abikan` → `Abikan:Accountant`
- `admin.abikan` → `SuperAdmin`, `Provider`

No patients, visits, orders, invoices, or payments were modified.

### Code changes (this phase)

- `hospital_admin.py` — Hospital Administrator account type, technical-SuperAdmin-only creation gate, staff directory serialization for Hospital Administrators, capability flag, preserve `Abikan:Hospital Admin` on department merge.
- `AdminDialogs.tsx` / `StaffAccountsWorkspace.tsx` — Account type UI for technical SuperAdmin.
- `provision-dev-users.py` — development `hospitaladmin.abikan` baseline account.
- Tests in `hospital_admin_test.py`, `adminView.test.ts`, `workspaceMap.test.ts`.

## Administration Security Hardening

Date: **26 Aug 2026**

### Final authority boundary

The final write path is:

```
signed-in OpenMRS session
  → active-user check
  → Hospital Admin / technical Admin authorization
  → approved account fields and seven-department allow-list
  → server-side technical OpenMRS operation
  → durable real-actor audit outcome
```

`Abikan:Hospital Admin` no longer receives native `Add Users`, `Edit Users`, `Manage Providers`, user-list, person-management, role-management, privilege-management, `app:admin`, SuperAdmin, or System Developer privileges. It receives:

- `abikan:admin:staff` — access to the bounded Hospital EMR staff workflow.
- `Get Providers` — required because the installed OpenMRS SessionController resolves the current provider while loading every authenticated session; removing it caused otherwise-valid Hospital Admin login/session reads to fail with 403.

Live direct requests as `hospitaladmin.abikan` after hardening:

- Hospital EMR Staff Accounts: HTTP 200.
- Native OpenMRS user update: HTTP 403.
- Native OpenMRS role update: HTTP 403.
- Operational department APIs: denied unless a separate approved department role is deliberately assigned to that staff account. Hospital Administrator account creation and access updates do not assign department roles.

Authenticated OpenMRS may still return some read-only REST catalogue responses according to its global REST policy. The Hospital Admin role has no privilege to mutate those catalogues or open the `app:admin` workflow. Preventing all authenticated users from reading globally readable OpenMRS REST catalogues would require a separate platform-wide OpenMRS/proxy policy change and was not introduced here.

### Approved role assignment

OpenMRS requires an assigning identity to hold all privileges inherited by the assigned role. Giving those Clinical, Nursing, Reception, Laboratory, Radiology, Pharmacy, and Accountant privileges to Hospital Admin would also grant operational workspace authority and was rejected.

The implementation uses the existing server-side technical identity for staff/person/provider/role operations only after:

1. validating the real actor's current active OpenMRS session;
2. requiring `abikan:admin:staff` or a technical role;
3. rejecting raw `role`, `roles`, `privilege`, or `privileges` fields;
4. mapping department IDs to the seven fixed role names on the server;
5. blocking self-change, technical-account change, and Hospital Administrator department assignment;
6. recording the real actor and before/after outcome durably.

The service identity is not returned to the browser and does not create a second permission model. OpenMRS roles and session privileges remain runtime authority for department workspaces.

Live `hospitaladmin.abikan` verification:

- Radiology + Reception + Accountant assigned successfully.
- Removing Reception left Radiology + Accountant.
- Restoring Reception restored all three.
- The development account was finally restored to Radiology-only.
- Clinical and Administration remained denied throughout.
- The existing Radiology provider UUID remained unchanged; no duplicate provider was created.

### Disabled users and sessions

Every non-health `abikan-api` request now centrally validates:

1. the OpenMRS session is authenticated; and
2. the exact OpenMRS User is not retired.

If the user was retired after login, Hospital EMR rejects the request with HTTP 401 `account_disabled`, sends an OpenMRS session invalidation request, performs no department operation, and requires a new login.

OpenMRS account disablement on this installation is a REST `DELETE /user/{uuid}?reason=…`, which retires the User without deleting it. Re-enable is `POST /user/{uuid}` with `retired: false`. Provider records and Person records are not retired or voided.

Controlled live verification with `hospitaladmin.test`:

- protected Admin request before disable: HTTP 200;
- disable through authorized technical Admin flow: HTTP 200;
- same existing session after disable: HTTP 401 `account_disabled`;
- fresh credential check while disabled: authenticated false;
- re-enable: HTTP 200;
- fresh login after re-enable: authenticated true;
- final account state: enabled.

Follow-up verification called OpenMRS directly **before** the first Hospital EMR backend request after disable. OpenMRS still returned HTTP 200 with `authenticated: true`; the subsequent protected Hospital EMR request returned 401 `account_disabled` and invalidated that session. Therefore Hospital EMR's backend revocation is reliable, but immediate revocation across browser-to-OpenMRS REST calls is not supplied by this OpenMRS installation. A supported OpenMRS session-revocation/filter mechanism or equivalent platform control remains required before hospital use; a frontend-only check is not sufficient.

### Durable administrative audit

Sensitive Admin mutations are stored in `/var/lib/abikan/admin-audit.sqlite3` on the dedicated `abikan-admin-audit` Docker volume. SQLite uses full synchronous writes and WAL mode. The volume is independent of the read-only application code mount and survives API container restarts.

Each operation starts with a durable `pending` row before the OpenMRS mutation, then finalizes to `success` or `failure`. A crash can therefore leave evidence of an interrupted action rather than silently losing it.

Recorded fields:

- UTC timestamp and event ID;
- real actor UUID/username;
- target user UUID/username;
- action;
- previous and new state;
- assigned/removed departments;
- enabled/disabled change;
- provider-link result;
- success/failure and error code;
- request/correlation ID.

Passwords, cookies, authorization headers, session values, tokens, and secrets are recursively redacted. Account-create callers also never pass the initial password to the audit function.

Recorded actions include `ADMIN_CREATE_USER`, `ADMIN_CREATE_HOSPITAL_ADMIN`, `ADMIN_DISABLE_USER`, `ADMIN_ENABLE_USER`, `ADMIN_UPDATE_DEPARTMENTS`, `ADMIN_ASSIGN_DEPARTMENT`, `ADMIN_REMOVE_DEPARTMENT`, and `ADMIN_PROVIDER_LINK`.

Live verification recorded 18 events across the controlled assignment/status sequence. Restarting `abikan-api` preserved exactly 18/18 events. A read-only Admin activity screen is deliberately deferred: the minimum requirement is durable recording, and exposing staff-security history needs an explicit retention/reviewer policy. Technical support can inspect the scoped store without exposing wholesale OpenMRS audit logs.

### Provider failure handling

OpenMRS does not provide one transaction spanning Person, User, role, and Provider creation.

- Existing active providers are reused by Person; duplicate provider identifiers for another Person are rejected.
- Provider link creation has its own durable audit event.
- If Provider creation fails after a new User was created, Hospital EMR retires that newly created User through the supported user-retire operation and returns an explicit failure. It does not claim success.
- If that safe compensation also fails, the API returns an immediate technical-support error and records both failures.
- A Person created before a User-create failure may remain as an orphan identity. It is not silently deleted or voided because automatic destructive compensation is less safe than a visible audited cleanup task.
- Access updates may create a missing Provider before role assignment. If the later role update fails, the Provider is retained for historical/safe reuse and both outcomes are audited; existing providers are never deleted.

## Platform-wide session revocation investigation

Date: **26 Aug 2026**

Scope: installed-platform investigation and controlled account-state testing only. No custom authentication module, proxy middleware, second session store, patient/clinical write, or financial write was introduced.

### Installed session architecture

- Deployment images: Bahmni OpenMRS `1.1.2`, Bahmni Web `1.1.0`, and Bahmni Proxy `1.1.0`.
- Live OpenMRS core: `2.5.14` (build `167b9d`).
- REST Web Services module: `2.44.0`.
- Bahmni Core module: `1.2.0`.
- The optional OpenMRS authentication/security module is not installed.
- Authentication is owned by OpenMRS. A browser first obtains a servlet session and authenticates through `GET /openmrs/ws/rest/v1/session` with Basic credentials. OpenMRS stores the authenticated `UserContext` in the Tomcat HTTP session represented by the HttpOnly `JSESSIONID`.
- The deployed web application uses Tomcat's servlet session manager. No deployment-specific remote session registry or user-to-all-sessions revocation service is configured. The inherited Tomcat session timeout is 30 minutes.
- Hospital EMR and Bahmni share the same OpenMRS session. The live cookie is HttpOnly with path `/openmrs`; both `/openmrs/abikan-api/...` and native `/openmrs/ws/rest/...` requests carry it.
- Deployed Bahmni JavaScript resolves its session service from `/openmrs/ws/rest/v1/session` and sends its clinical requests to the same `/openmrs/ws/rest` and `/openmrs/ws/rest/v1` paths. Bahmni does not add a separate authoritative authentication session.

### Disable, retire, and identity semantics

OpenMRS User has a `retired` state; this installation does not expose a separate User `disabled` flag. Hospital EMR's staff-facing mapping is:

```
Active   = OpenMRS User retired false
Disabled = OpenMRS User retired true
```

The Admin disable operation uses the supported REST user-retire operation. Re-enable sets `retired: false`. It does not void the Person and does not retire or delete Provider records. Historical authorship remains intact.

Fresh authentication for a retired user returns `authenticated: false`. However, OpenMRS 2.5.14 does not re-read the User's retired state on every request that already has an authenticated servlet session.

### Supported revocation capability

The installed REST module supports:

```
DELETE /openmrs/ws/rest/v1/session
```

That endpoint logs out and invalidates **the session identified by the request's own cookie**. It does not accept a target user UUID/username and does not invalidate every active session belonging to another user.

No supported endpoint or service was found in the installed OpenMRS/Bahmni versions for:

- listing all REST/Bahmni sessions for one user reliably;
- invalidating another user's servlet session;
- invalidating all sessions when a User is retired.

Legacy "logged-in users" tracking is not authoritative for REST/Bahmni logins and cannot safely satisfy this requirement. Tomcat internals/JMX, a custom servlet filter/module, a second revocation database, or proxy middleware would be custom platform architecture and were deliberately not introduced.

### Native interface exposure

The deployed reverse proxy exposes:

- `/openmrs` → the OpenMRS application, including REST and the native UI;
- `/bahmni` → Bahmni Web, including Home, Clinical, and Admin static entry points;
- `/openmrs/abikan-api` → Hospital EMR's backend.

Live unauthenticated reachability probes returned HTTP 200 for the OpenMRS UI/session entry and Bahmni Home/Clinical/Admin HTML entry points. Authorization still controls protected data/actions, but the interfaces are network-reachable. Hospital EMR also makes many browser-to-OpenMRS REST calls directly, so this is not merely a hidden-link concern.

### Controlled live result

The existing development-only `hospitaladmin.test` account was used; protected department and technical accounts were not changed.

1. Fresh login succeeded.
2. A permitted native OpenMRS Provider request returned HTTP 200.
3. Technical Admin disabled the account through the authorized Hospital EMR Admin flow.
4. The **existing** session immediately repeated the same native OpenMRS request: HTTP 200.
5. The same session called protected Hospital EMR Admin: HTTP 401 `account_disabled`.
6. Hospital EMR invalidated that session.
7. Reusing it against native OpenMRS then returned HTTP 401.
8. Fresh login while retired returned `authenticated: false`.
9. The account was re-enabled.
10. Fresh login succeeded and the account's final state was active.

This proves that account retirement alone does **not** revoke native sessions on this platform. Hospital EMR's backend check is effective, but it cannot invalidate a target session until that session presents its cookie to Hospital EMR.

### Decision and remaining risk

No implementation was made because the installed platform has no supported user-wide session-revocation mechanism. Implementing one would require unsupported/session-container internals, a custom OpenMRS module/filter, or a broader proxy/authentication redesign—explicit stop conditions for this task.

Immediate platform-wide revocation therefore remains **MUST FIX BEFORE HOSPITAL USE**. A deployment must choose and validate one supported future path:

1. adopt an OpenMRS-supported authentication/session module or platform upgrade that demonstrably invalidates all sessions when a User is retired; or
2. commission and maintain a reviewed OpenMRS module/filter that performs an authoritative active-user check for every native request; or
3. redesign deployment access so staff cannot use native interfaces and all protected traffic passes an authoritative active-user gate.

Reducing the 30-minute inactivity timeout limits idle-session exposure only; a session that keeps making requests can remain active. It is not immediate revocation and does not make this issue complete. Frontend polling or client-only logout is not authoritative.

### Deployment secret findings

- Hospital EMR's Compose override no longer contains service-credential fallbacks. It reads an ignored `.env.abikan` file generated from `.env.abikan.example`.
- The backend now requires an explicit `ABIKAN_ENVIRONMENT` and all OpenMRS/Odoo service identity variables at startup. Production rejects missing and well-known development/default values without logging supplied values.
- Runtime modules and controlled maintenance/provisioning scripts no longer contain credential fallbacks. Development scripts require credentials through environment variables.
- Secret-free `.env.example` templates now exist for the Standard and Lite platform stacks. Additional Compose password references fail interpolation when missing.
- Frontend source and Vite configuration contain no backend secret variables.
- `bahmni-docker` still tracks upstream `.env` and `.env.dev` development files. Existing remote development workflows consume `.env.dev`, so deleting them safely requires a coordinated workflow/host secret migration outside this repository task. They remain **development-only**, must not be used for hospital deployment, and every tracked value must be rotated before hospital use.
- Credential-bearing files remain in Git history. No destructive history rewrite or credential rotation was performed.

Full requirements are recorded in `docs/DEPLOYMENT_SECRETS.md`.

### Remaining deployment conditions

- Hospital EMR runtime fallbacks are removed, but unique deployment-managed credentials and rotation of all tracked development values are still required before hospital use.
- Retiring a user does not immediately invalidate that user's existing native OpenMRS session. All protected `abikan-api` requests deny and invalidate it, but direct OpenMRS REST remains usable until that check or normal session expiry. This is a remaining hospital-use blocker requiring an OpenMRS/platform-supported revocation control.
- Audit-log retention, backup, reviewer access, and incident-review policy still require an operational decision. Recording itself is durable and active.
- Some OpenMRS REST catalogue reads are globally available to authenticated users. Hospital Admin cannot mutate native users or roles and has no native Admin app privilege. Any future requirement to hide all globally readable technical catalogues must be implemented as a platform-wide OpenMRS/proxy policy, not by broadening Hospital Admin privileges.

## System Settings

System Settings remains **Coming soon** and non-clickable. No hospital, currency, location, PACS, DICOM, tax, accounting, server, or platform settings were implemented.

## 17. Explicit Non-Changes

The original audit made no application-code or operational configuration changes. The later implementation is limited to the Staff Accounts and Department Access sections documented above.

Across both phases, the following remain unchanged:

- no location changes;
- no concept, service, product, catalogue, availability, or price changes;
- no Odoo configuration or accounting changes;
- no patient, visit, encounter, observation, order, invoice, or payment writes;
- no changes to protected ORD-6, ORD-14–ORD-21, INV/2026/00006, or INV/2026/00031–00035.

The implementation did not assign the new Hospital Admin role to a live account and created no TEST staff account.

## 18. Tests / Build

- `npm test` — **passed**: 302 tests, 74 suites, 0 failures.
- `python3 -m unittest discover -s . -p '*_test.py'` — **passed**: 72 backend tests, including focused Administration/session/audit and deployment-configuration guards, no test-suite live writes.
- `npm run build` — **passed**: TypeScript check and Vite production build.
- Build emitted the existing advisory that the main JavaScript chunk is larger than 500 kB; it did not fail the build.
- Live role-provisioning verification — **passed** (prior): `admin.abikan` assigned Radiology + Reception + Accountant; runtime navigation and department APIs matched; `radiology.abikan` restored to Radiology-only.
- Live Hospital Administrator verification — **passed** (25 Aug 2026): `admin.abikan` created `hospitaladmin.test`; both Hospital Administrator accounts access Admin APIs; escalation to SuperAdmin/System Developer blocked; existing dev accounts preserved.
- Live security-hardening verification — **passed** (26 Aug 2026): `hospitaladmin.abikan` retained only `abikan:admin:staff` plus session-required `Get Providers`; direct native user/role updates returned 403; all seven approved role mappings passed unit coverage; Radiology + Reception + Accountant assignment/removal/restoration passed live; `radiology.abikan` was restored to Radiology-only; a disabled existing session returned 401 and was invalidated; re-enabled fresh login succeeded; audit history survived API restart; provider UUID remained unchanged.
- Live platform-wide revocation verification — **security requirement not met by installed OpenMRS** (26 Aug 2026): the controlled account's already-authenticated native Provider request still returned HTTP 200 immediately after retirement; Hospital EMR returned HTTP 401 and invalidated that presented session; native reuse then returned 401; fresh login while retired failed; re-enable and fresh login succeeded. No unsupported workaround was installed.

## Sources

- `src/config/workspaceMap.ts`
- `src/config/adminAccess.ts`
- `src/config/workplaces.ts`
- `src/config/workplaceSwitcher.ts`
- `src/config/adminNav.ts`
- `src/config/clinicalWorkspaces.ts`
- `src/app/WorkspaceRouter.tsx`
- `src/workspaces/ClinicalHome/ClinicalHomeWorkspace.tsx`
- `src/workspaces/Admin/StaffAccountsWorkspace.tsx`
- `src/workspaces/Admin/DepartmentAccessWorkspace.tsx`
- `src/workspaces/Accommodation/AccommodationSettingsWorkspace.tsx`
- `src/workspaces/Doctor/ConsultationFeeCard.tsx`
- `src/workspaces/Radiology/RadiologyFeeCard.tsx`
- `src/workspaces/Pharmacy/PharmacyWorkspace.tsx`
- `server/patient-account/server.py`
- `server/patient-account/hospital_admin.py`
- `server/patient-account/accommodation.py`
- `server/patient-account/accountant.py`
- `server/patient-account/consultation.py`
- `server/patient-account/radiology.py`
- `server/patient-account/laboratory.py`
- `server/patient-account/lab_catalogue.py`
- `server/patient-account/pharmacy.py`
- `server/patient-account/pharmacy_manage.py`
- `server/patient-account/pharmacy_inventory.py`
- `server/patient-account/registration.py`
- `server/patient-account/data/registration_fees.json`
- `scripts/provision-dev-users.py`
- `../abikan-config/openmrs/apps/admin/extension.json`
- `../abikan-config/openmrs/apps/home/extension.json`
- live read-only OpenMRS REST and Odoo XML-RPC observations on 25 Aug 2026.
