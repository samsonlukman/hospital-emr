# Deployment secrets

This document defines configuration handling for development and hospital deployment. It intentionally contains variable names only.

## Rules

- Never commit populated environment files, credentials, tokens, private keys, or generated secret material.
- Use unique credentials for each hospital deployment.
- Keep development identities and credentials separate from hospital identities.
- Populate secrets through the deployment's existing secret mechanism or a local environment file with mode `0600`.
- Do not expose backend secrets through `VITE_*`, React source, public assets, image build arguments, or logs.
- Missing required production configuration must stop startup; it must not select a development fallback.

## Hospital EMR backend

Required in `bahmni-standard/.env.abikan` or the equivalent deployment secret injection:

```text
ABIKAN_ENVIRONMENT
ABIKAN_OPENMRS_ADMIN_USER
ABIKAN_OPENMRS_ADMIN_PASSWORD
ABIKAN_OPENELIS_USER
ABIKAN_OPENELIS_PASSWORD
ABIKAN_ODOO_USER
ABIKAN_ODOO_PASSWORD
```

`ABIKAN_ENVIRONMENT` must be explicitly set to `development`, `test`, or `production`. In production, the backend rejects missing values and well-known development/default values without logging the supplied values. The OpenELIS identity is server-side and read-only for supported accession/worklist APIs; it must never be bundled into browser code.

Hospital Admin analytics reads OpenMRS MySQL through the API container. Compose supplies `ABIKAN_OPENMRS_DB_*` from the existing OpenMRS database variables. Those values stay server-side. If they are missing, overview counts show Unavailable rather than zero.

For local development, copy `bahmni-standard/.env.abikan.example` to `.env.abikan`, set development-only values, and keep the file ignored. The current workstation file is local-only and has mode `0600`.

Maintenance and development scripts require their identity/password variables explicitly. `scripts/provision-dev-users.py` is development-only and requires:

```text
ABIKAN_ADMIN_USER
ABIKAN_ADMIN_PASSWORD
ABIKAN_DEV_PASSWORD
```

Catalogue and verification scripts also require the applicable `ABIKAN_ADMIN_*` and `ABIKAN_ODOO_*` values. They no longer contain credential fallbacks and do not print passwords.

## Bahmni platform

Use `bahmni-standard/.env.example` or `bahmni-lite/.env.example` as the variable template. Blank values include required deployment identities and secrets for:

- OpenMRS and atomfeed;
- OpenELIS;
- Odoo integration;
- application and reporting databases;
- database administrator/root accounts;
- PACS services;
- analytics/reporting services;
- mail and SMS, when enabled;
- terminology services;
- Lite-only Crater services.

Docker Compose uses required-variable expansion for service passwords that must exist. Optional integrations may remain blank only while their service/profile is disabled.

## Tracked development files and history

The `bahmni-docker` repository currently tracks `.env` and `.env.dev` files for Lite and Standard. They contain upstream development/default credentials and are also referenced by existing remote development workflows.

They must not be treated as hospital secrets or copied into a hospital deployment. Removing them safely requires coordinated migration of the remote development workflows and hosts to an external secret source. That infrastructure dependency was not guessed or changed during this remediation.

Because credential-bearing files exist in Git history:

- consider every tracked value a public development value;
- rotate it before any hospital deployment;
- rotate it immediately if it was reused outside isolated development;
- do not rewrite history without a separate coordinated repository-maintenance task.

Stock OpenELIS UI password values were removed from tracked Laboratory documentation on 26 Aug 2026. The tracked Standard `.env` / `.env.dev` integration values remain part of the wider upstream development-environment migration described above; they are not approved hospital credentials. A hospital deployment must inject new values externally, rotate or disable stock OpenELIS accounts, and create named OpenELIS administrator/staff accounts.

## Frontend

The browser configuration contains only `VITE_BAHMNI_ORIGIN` and Vite's public base URL. These values are routing configuration, not secrets. Backend credentials must never be added under a `VITE_*` name because Vite embeds them in browser JavaScript.

## Deployment checklist

1. Create deployment environment files from the committed examples.
2. Populate every required blank value through deployment-managed secrets.
3. Set `ABIKAN_ENVIRONMENT=production`.
4. Confirm no populated environment file is tracked by Git.
5. Run Compose configuration validation before starting services.
6. Start Hospital EMR and confirm configuration validation succeeds.
7. Scan the frontend source and production bundle for backend secret variable names.
8. Rotate all development/default credentials before hospital access is enabled.

Hospital LAN architecture, hardware, backups, and installation/UAT checklists: `HOSPITAL_DEPLOYMENT.md`, `HOSPITAL_SERVER_INSTALLATION.md`, `HOSPITAL_UAT_CHECKLIST.md`.

## Verification on 26 Aug 2026

- Standard and Lite development Compose configuration: passed.
- Standard and Lite blank deployment templates: correctly rejected.
- Hospital EMR backend startup with explicit ignored development configuration: passed.
- Backend/configuration tests: 72 passed.
- Frontend tests: 302 passed across 74 suites.
- Production frontend build: passed; no backend secret variable names or configured high-entropy secret values were found in the bundle.
