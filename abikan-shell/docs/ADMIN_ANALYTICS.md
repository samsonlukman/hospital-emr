# Hospital Admin analytics and staff activity

Date: **27 Aug 2026**. P0 only.

Hospital Overview and Staff Activity read existing records. They do not create a second audit log, analytics warehouse, or copy of clinical data.

## Screens

- Administration home (`#/home`) keeps the existing task tiles.
- **Hospital overview** `#/admin/analytics`
- **Staff activity** `#/admin/audit`

## Privileges

Assigned to `Abikan:Hospital Admin` in addition to `abikan:admin:staff`:

- `abikan:admin:analytics`
- `abikan:admin:audit-read`

Hospital Admin does **not** receive `app:admin`, Nursing, Laboratory, Pharmacy, Accountant, or Doctor privileges.

Technical SuperAdmin may open the screens. Doctor, Nurse, Laboratory, Pharmacy, and Accountant cannot.

## Timezone

All date windows use **Africa/Lagos**.

OpenMRS stores datetimes in UTC. “Today” is the Lagos calendar day, converted to UTC instants before querying:

```text
Lagos 27 Aug 00:00  →  UTC 26 Aug 23:00
Lagos 28 Aug 00:00  →  UTC 27 Aug 23:00  (exclusive end)
```

Weeks start Monday. Custom ranges are inclusive of both Lagos dates.

Odoo invoice `invoice_date` and payment `date` are calendar dates as stored. They are filtered as hospital business dates in the selected Lagos range. They are not converted from UTC instants.

## Metric definitions

| Metric | Source | Time field |
|---|---|---|
| Patients registered | OpenMRS `patient` where not voided | `date_created` |
| Outpatient visits | OpenMRS `visit` types OPD, Special OPD, Follow Up | `date_started` |
| Consultations | Encounter type Consultation | `encounter_datetime` |
| Admissions | Encounter type ADMISSION | `encounter_datetime` |
| Discharges | Encounter type DISCHARGE | `encounter_datetime` |
| Current occupancy | `bed` + `bed_patient_assignment_map` where `date_stopped` is null | Snapshot now |
| Laboratory orders | OpenMRS order type Lab Order, excluding `order_action` DISCONTINUE | `date_activated` (else `date_created`) |
| Prescriptions | OpenMRS order type Drug Order, excluding `order_action` DISCONTINUE | `date_activated` (else `date_created`) |
| Dispensed | Odoo done outgoing `stock.picking` linked to prescription `sale.order.line.external_order_id` | `date_done` |
| Billed | Posted Odoo customer invoices (`account.move`) | `invoice_date` |
| Collected | Posted inbound Odoo `account.payment` | payment `date` |
| Outstanding | Sum of posted invoice `amount_residual` | **Current** snapshot |

Unavailable is shown when a source cannot be read. It is never converted to zero.

## Occupancy and outstanding

These are **current** figures. The date filter does not change them. The screen says so.

Historical occupancy and aged outstanding are not implemented.

## Staff activity

Reads `/var/lib/abikan/admin-audit.sqlite3` (`admin_audit_event`).

This is staff-account administration only: create, disable, enable, department assignment, clinical-profile link.

It is not Bahmni `audit_log` and does not include screen-view events.

Passwords, cookies, tokens, and secrets stay redacted.

## Security

Overview cards are aggregates. They do not include patient names, hospital numbers, diagnoses, notes, vital values, or invoice lists.

Staff activity shows staff usernames because the screen is about administration changes.

OpenELIS credentials and history are not used.

## Endpoints

```text
GET /openmrs/abikan-api/admin/analytics/overview
GET /openmrs/abikan-api/admin/analytics/reception
GET /openmrs/abikan-api/admin/analytics/inpatient
GET /openmrs/abikan-api/admin/audit
```

Query: `period=today|yesterday|this_week|last_week|this_month|last_month|custom&from=YYYY-MM-DD&to=YYYY-MM-DD`

## Known limitations

- Actor identity for clinical work is often a service account; this P0 does not reconstruct who recorded a note or dispensed a medicine.
- Laboratory **processing** volume is not shown. Only OpenMRS laboratory **orders**.
- New vs returning patients is not shown.
- Odoo payment `date` follows the finance calendar date as stored; midnight around UTC vs Lagos can differ from clinical timestamps.
- Occupancy is current beds in use, not occupancy during the selected month.
- OpenMRS `orders` uses `order_action` (NEW / DISCONTINUE). There is no `action` column on this hospital's orders table.

## Not in this version

Patient-level clinical audit, OpenELIS named-staff audit, diagnosis analytics, nursing activity, MAR/vitals detail, pharmacy detail beyond dispensed movements, historical occupancy, and aged receivables.
