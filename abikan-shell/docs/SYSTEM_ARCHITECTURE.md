# System architecture

This document is for Hospital Admin, implementers, and technical support. Staff desk manuals avoid these names.

Release: `v1.0.0-uat`.

Related: [Hospital deployment](HOSPITAL_DEPLOYMENT.md) · [Deployment secrets](DEPLOYMENT_SECRETS.md)

---

## Non-technical: how information moves

1. A staff member signs in to **Hospital EMR** in the browser.
2. Hospital EMR shows the **department** that person is allowed to use.
3. When they save clinical work (consultation, diagnosis, prescription, visit), it is stored in the **clinical chart**.
4. When they create a charge or collect payment, the **financial record** is stored in the billing system.
5. Laboratory **processing** (specimen, accession, result entry) happens in the laboratory system. Hospital EMR only shows orders and released results.
6. Imaging **files**, if a scanner is connected, live in the imaging archive. Hospital EMR does not show images in this release.
7. Ward notes, vitals, and MAR are recorded through Hospital EMR and stored as clinical observations / administrations on the admission.

Hospital EMR does **not** keep a second patient database. It does not invent a second invoice book.

---

## Technical: request path

```text
Staff browser
    → Bahmni proxy (ports 80 / 443)
        → Hospital EMR UI (`/` and `/abikan/` from `abikan-shell/dist`)
        → Hospital EMR API (`/openmrs/abikan-api` → abikan-api)
        → OpenMRS / Bahmni clinical apps
        → OpenELIS (`/openelis`)
        → other Bahmni paths (documents, IPD UI, and so on)

Hospital EMR API
    → OpenMRS REST (and MySQL for admin analytics)
    → OpenELIS (server-side read of accession status only)
    → Odoo XML-RPC (charges, invoices, payments, stock)
```

| System | Authoritative for |
|--------|-------------------|
| **OpenMRS** | Patient identity, visits, encounters, diagnoses, orders, observations, admissions, MAR administrations |
| **OpenELIS** | Specimen, accession, analysis, result validation |
| **Odoo** | Products, pricelists, sale orders, invoices, payments, pharmacy pickings / stock |
| **dcm4chee / PACS** | Imaging files when configured. **Not wired into Hospital EMR screens in this release** |
| **Hospital EMR API + UI** | Department workflow, RBAC for hospital jobs, department pricing writes, cashier, ward board helpers, schedule ensure, analytics, staff-admin audit |
| **Bahmni proxy** | Single staff entry, TLS, routing |

Staff administration audit (who created or disabled accounts) is SQLite in Docker volume `abikan-admin-audit`. Staff log sessions and staff attendance codes use `attendance.sqlite3` on the same volume. Attendance codes are assigned by Hospital Admin against the existing staff record.

---

## Why there is no duplicate clinical database

Hospital EMR reads and writes the existing engines. A nursing note is an observation on the admission encounter. A prescription is an OpenMRS drug order; the bill is an Odoo invoice. A laboratory result displayed in Hospital EMR is the result already posted to OpenMRS after OpenELIS validation.

---

## Observations and vitals

- **OPD vitals:** doctor saves with the consultation encounter on an open OPD visit.
- **Inpatient vitals:** nurse posts through Hospital EMR; each save creates **new** OpenMRS observations on the admission encounter. Time and author are server-owned. No overwrite, no client timestamp.

---

## MAR scheduling

Bahmni IPD does not always create slots when the doctor saves a drug order. On MAR load, Hospital EMR asks the installed IPD schedule service to create schedules for eligible **inpatient** orders. PRN / as-needed orders are refused for the scheduled sheet. Administration uses the medication administration module; actual time is server clock.

---

## Pharmacy

Atomfeed creates the commercial draft. Confirm / automated invoicing posts the invoice. Accountant payment is required. Pharmacist dispense validates the Odoo picking. Hospital EMR does not write an OpenMRS “Dispensed” observation in this release.

---

## Billing

See [BILLING_AND_PAYMENTS.md](BILLING_AND_PAYMENTS.md). Catalogue `list_price` is copied onto the charge line at creation. Historical `account.move` lines are not rewritten.

Company currency may remain **USD** while departmental pricelists and new charges use **NGN**.

---

## Docker services (summary)

Bahmni Standard compose plus Hospital EMR overlay (`docker-compose.override.yml`). Hospital LAN hardening is `docker-compose.hospital.yml` (do not apply on the development Mac).

Hospital UI updates: `git checkout v1.0.0-uat` then `npm ci && npm run build`. Dist is generated, not tracked.

Never run `docker compose down -v` on a hospital host.
