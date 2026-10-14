# Hospital EMR

Hospital EMR Hospital EMR is the hospital information and clinical workflow platform for Hospital EMR.

Staff work in Hospital EMR. Existing clinical engines remain behind the product: OpenMRS/Bahmni for the chart, OpenELIS for laboratory processing, Odoo for billing and pharmacy stock, and the Hospital EMR API for hospital-specific workflows (accounts, nursing, laboratory board, pharmacy, administration analytics, and staff-administration audit).

This repository is source code for development. It is not a deployment, UAT, or production environment.

## Layout

| Path | Role |
|------|------|
| `abikan-shell/` | Staff UI (React) and Hospital EMR API (`server/patient-account`) |
| `abikan-config/` | Hospital Bahmni/OpenMRS configuration overlays |
| `bahmni-docker/` | Docker Compose stack (Bahmni Standard plus Hospital EMR services) |

## Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for the shell)
- Python 3.12+ (API tests; the API container also runs Python)
- Access to the Bahmni Standard images used by `bahmni-docker`

Do not put passwords in this file. Copy the example environment templates and fill them locally.

## Configuration

1. Copy `bahmni-docker/bahmni-standard/.env.example` to `bahmni-docker/bahmni-standard/.env`.
2. Copy `bahmni-docker/bahmni-standard/.env.abikan.example` to `bahmni-docker/bahmni-standard/.env.abikan` (mode `0600`).
3. Set every required identity and password through those local files or your secret mechanism.

`abikan-shell/.env.development` and `.env.production` contain only the Vite public origin (`VITE_BAHMNI_ORIGIN`). They are not service credentials.

See `abikan-shell/docs/DEPLOYMENT_SECRETS.md` for variable names and rules.

Hospital UAT/production (architecture, hardware, backups, LAN/VPN, checklists): `abikan-shell/docs/HOSPITAL_DEPLOYMENT.md`.

## Documentation

Staff and operations manuals (this release: `v1.0.1-uat`):

- [User manual](abikan-shell/docs/ABIKAN_EMR_USER_MANUAL.md)
- Department guides: [Reception](abikan-shell/docs/DEPARTMENT_GUIDE_RECEPTION.md) · [Doctor](abikan-shell/docs/DEPARTMENT_GUIDE_DOCTOR.md) · [Nursing](abikan-shell/docs/DEPARTMENT_GUIDE_NURSING.md) · [Laboratory](abikan-shell/docs/DEPARTMENT_GUIDE_LABORATORY.md) · [Pharmacy](abikan-shell/docs/DEPARTMENT_GUIDE_PHARMACY.md) · [Accountant](abikan-shell/docs/DEPARTMENT_GUIDE_ACCOUNTING.md) · [Radiology](abikan-shell/docs/DEPARTMENT_GUIDE_RADIOLOGY.md) · [Hospital Admin](abikan-shell/docs/DEPARTMENT_GUIDE_HOSPITAL_ADMIN.md) · [Inpatient](abikan-shell/docs/DEPARTMENT_GUIDE_INPATIENT.md)
- [Clinical workflows](abikan-shell/docs/CLINICAL_WORKFLOWS.md)
- [Billing and payments](abikan-shell/docs/BILLING_AND_PAYMENTS.md)
- [Roles and permissions](abikan-shell/docs/USER_ROLES_AND_PERMISSIONS.md)
- [System architecture](abikan-shell/docs/SYSTEM_ARCHITECTURE.md)
- [Troubleshooting](abikan-shell/docs/TROUBLESHOOTING.md)
- [UAT quick reference](abikan-shell/docs/UAT_QUICK_REFERENCE.md)
- [Hospital deployment](abikan-shell/docs/HOSPITAL_DEPLOYMENT.md)

## Development environment

From `bahmni-docker/bahmni-standard`:

```bash
docker compose --env-file .env up -d
```

Build the staff UI (the proxy serves `abikan-shell/dist`):

```bash
cd abikan-shell
npm install
npm run build
```

Open the local Hospital EMR entry (`https://localhost/abikan/` in this development setup). Sign in with a hospital staff account provisioned for that environment.

Vite for UI work:

```bash
cd abikan-shell
npm run dev
```

Rollback of the Hospital EMR proxy overlay is described in `abikan-shell/README.md`. Do not run `docker compose down -v` unless you intend to destroy local volumes.

## Tests and build

```bash
cd abikan-shell
npm test
npm run build
```

API tests:

```bash
cd abikan-shell/server/patient-account
python3 -m unittest discover -s . -p '*_test.py'
```

These suites use synthetic fixtures. Do not create real patients to run them.

## Security

Read `SECURITY.md` before committing. Secrets and real patient data must stay out of Git.

## Licence

Bahmni Docker and default-config files retain their upstream licences (`bahmni-docker/LICENSE`, `abikan-config/LICENSE`). Hospital EMR-specific code in this repository follows the same hospital development terms as the surrounding project.

If this workstation previously cloned `bahmni-docker` or `abikan-config` from upstream GitHub, that clone metadata is kept locally under `.nested-git/` and is not part of this repository.
