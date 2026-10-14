# Hospital EMR hospital deployment architecture

Date: **27 Aug 2026**. This describes the stack as configured in Git and as observed on the development workstation. It is not a live hospital cutover.

Do not copy development `.env` files, development passwords, or the development databases onto a hospital server.

Related:

- Secrets variable names: `abikan-shell/docs/DEPLOYMENT_SECRETS.md`
- Installation steps: `HOSPITAL_SERVER_INSTALLATION.md`
- Staff UAT: `HOSPITAL_UAT_CHECKLIST.md`

---

## 1. Current architecture

Staff browsers talk to the Bahmni **proxy** on ports **80** and **443**. The proxy serves Hospital EMR (`/` and `/abikan/`) from `abikan-shell/dist`, forwards `/openmrs/abikan-api` to **abikan-api**, and forwards `/bahmni/`, OpenMRS, documents, and other Bahmni paths to the engine containers.

Hospital EMR API (`python:3.12-alpine`) bind-mounts `abikan-shell/server/patient-account`. It talks to OpenMRS (REST + MySQL for admin analytics), OpenELIS (server-side only), and Odoo (XML-RPC). Staff administration audit is SQLite in Docker volume `abikan-admin-audit`.

Clinical engines:

| Engine | Role |
|--------|------|
| OpenMRS + Bahmni web/apps | Chart, registration, clinical, IPD UI |
| OpenELIS + PostgreSQL | Laboratory processing |
| Odoo 16 + PostgreSQL | Billing, pharmacy stock, invoices, payments |
| dcm4chee + pacs-integration + PostgreSQL 9.6 | Imaging |
| Reports + MySQL | Bahmni reports |
| Metabase + MART | Optional analytics (enabled on the current development profiles) |

Compose files (from `bahmni-docker/bahmni-standard/`):

1. `docker-compose.yml` — Bahmni Standard
2. `docker-compose.override.yml` — Hospital EMR proxy, API, config bind-mounts (development and hospital)
3. `docker-compose.hospital.yml` — **optional**, hospital LAN hardening only. Do not apply on the development MacBook. Requires Docker Compose v2 `!reset` / `!override` so ports are replaced, not appended.

---

## 2. Docker services (live development, 27 Aug 2026)

`COMPOSE_PROFILES=bahmni-standard,metabase,bahmni-mart`. `RESTART_POLICY=unless-stopped` (openmrsdb is hardcoded `always`). `TZ=UTC` on this Mac; hospital should use `Africa/Lagos`.

**Host-published ports (all interfaces today):**

| Port | Service | Hospital recommendation |
|------|---------|-------------------------|
| 80, 443 | proxy | LAN only (staff entry) |
| 8069 | odoo | localhost/VPN only (`docker-compose.hospital.yml`) |
| 8787 | abikan-api | do not publish; proxy already routes it |
| 8055 | dcm4chee web | localhost/VPN only |
| 11112 | dcm4chee DICOM | off by default in the hospital overlay; uncomment only if a modality needs it |

**Internal only (Docker network):** OpenMRS 8080, OpenELIS 8052, MySQL 3306, PostgreSQL 5432, Metabase 3000, template-service, Bahmni web, appointments, IPD, reports, atomfeed, etc.

Health checks present today: `openelisdb`, `odoodb`, `template-service`. OpenMRS and abikan-api have **no** health check on the development overlay. The hospital overlay adds an abikan-api check against existing `GET /health` (no application change).

`metabasedb` was **Exited** while `metabase` was still Up — Metabase/MART are not required for core clinical UAT. Hospital profile example uses `bahmni-standard` only.

`odoo-10` is **not** in the `bahmni-standard` profile and is not running.

---

## 3. Persistent volumes

Named volumes (project `bahmni-standard`) survive `docker compose up/down` and reboot. They are **destroyed** by `docker compose down -v`. Never use `-v` on a hospital host.

| Volume | Contents |
|--------|----------|
| `openmrsdbdata` | OpenMRS MySQL (patients, encounters, orders, users) |
| `openelisdbdata` | OpenELIS PostgreSQL |
| `odoodbdata` | Odoo PostgreSQL (invoices, payments, stock) |
| `odooappdata`, `odoofilestore`, `odooconfig` | Odoo application + attachments |
| `reportsdbdata` | Reports MySQL |
| `pacsdbdata` | PACS + integration PostgreSQL |
| `dcm4chee-archive`, `dcm4chee-config` | Imaging archive |
| `bahmni-patient-images`, `bahmni-document-images`, `bahmni-lab-results`, `bahmni-uploaded-files` | Files |
| `bahmni-clinical-forms`, `bahmni-queued-reports`, `configuration_checksums`, `sms-token` | Config/runtime files |
| `bahmni-config` | Named Bahmni config volume (see portability) |
| `abikan-admin-audit` | Hospital EMR administration audit, staff notifications, messaging, and staff-log SQLite files |
| `metabase-data`, `mart-data` | Optional reporting |

**Bind mounts (need the Git tree on disk):**

- `abikan-config` → bahmni-web `bahmni_config`
- `abikan-shell/dist` → proxy `/abikan`
- `abikan-shell/server/patient-account` → abikan-api `/app`
- `proxy/inject-abikan-api.sh`
- `extra-odoo-addons` → Odoo extra addons
- `init_pacs_dbs.sh` into pacsdb init

These survive reboot. They do **not** live inside Docker volumes. Hospital backup must include `/opt/abikan` (or whatever clone path) **or** rely on Git plus secrets files.

OpenMRS/OpenELIS/reports currently use `CONFIG_VOLUME=bahmni-config` (named volume) while bahmni-web uses the Git bind-mount. Those can drift. Hospital `.env.hospital.example` sets `CONFIG_VOLUME=../../abikan-config` (repo `abikan-config`, relative to `bahmni-standard`) so one Git tree is authoritative.

---

## 4. Environment variables and secrets

**Git:** compose files, `*.example` templates, source, `abikan-config`, documentation.

**Host (mode 0600, never Git):** `.env`, `.env.abikan`.

**Docker volumes:** databases, files, audit SQLite.

**Browser:** only `VITE_BAHMNI_ORIGIN` (empty in production build so Hospital EMR and Bahmni share the same origin).

Required Hospital EMR backend (`.env.abikan`):

```text
ABIKAN_ENVIRONMENT=production   # or test for UAT
ABIKAN_OPENMRS_ADMIN_USER=
ABIKAN_OPENMRS_ADMIN_PASSWORD=
ABIKAN_OPENELIS_USER=
ABIKAN_OPENELIS_PASSWORD=
ABIKAN_ODOO_USER=
ABIKAN_ODOO_PASSWORD=
```

Production rejects missing values and well-known weak placeholders (`admin123`, `password`, …) for those six service variables. Staff OpenMRS passwords are **separate** and must still be unique hospital values.

Bahmni `.env` must set every `:?` password used by the enabled profiles (OpenMRS DB, MySQL root, OpenELIS, Odoo, reports, PACS, atomfeed). See `.env.example`.

---

## 5. Hardware (assumptions)

Assumptions: Bahmni Standard + Odoo 16 + OpenELIS + PACS + Hospital EMR; about **15–25** concurrent staff; images pulled from Docker Hub; no GPU; SSD/NVMe (HDDs will make OpenMRS/MySQL painful); UPS covering an orderly shutdown of 15–30 minutes.

| | UAT / first hospital server | Small hospital production | Substantial growth |
|--|-----------------------------|---------------------------|-------------------|
| CPU | 8 cores | 8–12 cores | 16 cores |
| RAM | 16 GB (tight if Metabase/MART on); **32 GB preferred** | **32 GB ECC** | 64 GB ECC |
| Disk | 512 GB NVMe | 1 TB NVMe, RAID1 | 2 TB+ RAID10 |
| Network | Gigabit Ethernet to switch | Same + management NIC optional | 2×1 Gb or 10 Gb later |
| GPU | None | None | None |
| UPS | Required | Required | Required |
| ECC | Useful | Recommended | Required |
| RAID | Optional for UAT | RAID1 for OS+data | RAID10 data |

Why 16 GB is minimum, not comfortable: this host already runs OpenMRS, OpenELIS, Odoo, several databases, reports, dcm4chee, proxy, and Hospital EMR together. Metabase/MART add more. Swap will freeze clinics.

Storage growth is mostly documents, images, PACS, and database WAL. Budget **50–150 GB/year** until imaging volume is measured, then revise.

---

## 6. Host operating system

**Recommend Ubuntu Server LTS (24.04)** with Docker Engine + Compose plugin, not Docker Desktop.

| Host | Verdict |
|------|---------|
| Ubuntu Server | Production/UAT. systemd starts Docker on boot; `unless-stopped` then starts containers. |
| Windows + Docker Desktop | Avoid for the hospital server. Licensing, Desktop not starting on boot, Linux VM layer. |
| macOS + Docker Desktop | Current **development** workstation only. |

Do not install an OS on the current Mac for this task.

---

## 7. Automatic startup (verified)

Observed restart policies: proxy, abikan-api, openmrs, odoo, odoodb → **`unless-stopped`**. openmrsdb → **`always`**.

| Event | Expected behaviour |
|-------|--------------------|
| Container crash | Docker restarts it (`unless-stopped` / `always`) |
| `docker compose stop` then reboot | `unless-stopped` will **not** start those containers until `compose up -d` again |
| Reboot with Docker enabled and containers left “running” | Docker starts, then `unless-stopped` containers start |
| Power cut | Same as reboot **if** the host BIOS/OS boots automatically and Docker is enabled |
| `docker compose down` (no `-v`) | Containers removed; volumes kept. Need `up -d` after reboot |

**Hospital must:** enable `docker.service`, set BIOS to power-on after AC restore, and leave the stack started with `up -d` (not a leftover `stop`). Prefer **not** to `compose stop` as the daily shutdown method.

Docker Desktop on the Mac does **not** equal a hospital auto-start story.

---

## 8. Backup and restore

**Daily (hospital):**

1. Run `backup_bahmni_standard.sh` (OpenMRS, reports, OpenELIS, Odoo, PACS DBs + files + Odoo filestore + dcm4chee archive). It also attempts Odoo 10 even when that profile is off — expect that step to fail; that is upstream, not Hospital EMR.
2. Run `backup_abikan_audit.sh` (staff-admin audit, notifications, messaging, and staff-log SQLite). The Bahmni script does **not** include this volume.
3. Copy `/opt/abikan` Git checkout **or** record the Git tag plus `.env` / `.env.abikan` (secrets) to the backup set.
4. Encrypt (age/gpg) and copy **off-server** (second disk, NAS, or admin laptop over VPN). Keep 14 daily + 8 weekly + 12 monthly as a starting retention.

**Restore:** follow Bahmni restore docs for `restore_bahmni_standard.sh` onto **empty** volumes. Restore Hospital EMR audit with a reverse of `backup_abikan_audit.sh` into `abikan-admin-audit`. Restore `.env` files from the encrypted secret bundle. Test restore on a spare host **before** go-live.

`docker compose down -v` is a wipe. Forbid it on hospital hosts.

---

## 9. Network and firewall

```text
Hospital server (Ubuntu + Docker)
    → Ethernet → hospital switch
        → LAN/Wi-Fi → staff PCs
        → Tailscale (admin only) → Abuja
```

Staff URL: `https://emr.hospital.lan/` (or the server LAN IP) through the **proxy** only.

Do **not** give staff OpenMRS 8080, OpenELIS, PostgreSQL, MySQL, Odoo 8069, or abikan-api 8787.

Firewall (host):

- Allow LAN → TCP 80, 443
- Allow LAN → TCP 11112 only after it is uncommented in `docker-compose.hospital.yml` for a modality
- Allow Tailscale interface → TCP 22 (SSH) and 443
- Deny WAN (if any NIC has a public IP): all inbound
- Deny LAN → 8069, 8787, 3306, 5432, 8055

No public Internet publishing of the EMR.

---

## 10. VPN (Tailscale recommended)

- Install Tailscale on the **hospital server** and on the **Abuja admin** device.
- Do not put the EMR on the public Internet.
- Hospital staff do **not** need Tailscale if they are on hospital LAN.
- SSH listen on Tailscale IP only (`sshd` `ListenAddress` or firewall).
- Revoke access by removing the node/user from the Tailscale tailnet ACL.
- Optional: Tailscale subnet router so admin can reach `https://emr.hospital.lan` without exposing 443 publicly.

Do not install Tailscale in this task.

---

## 11. Internet vs LAN UAT

| | Cloud UAT on the Internet | Server in Ilorin (LAN + VPN) |
|--|---------------------------|------------------------------|
| Staff access | Needs accounts, TLS, careful exposure | Native LAN |
| Data | Leaves the hospital | Stays on site |
| Abuja admin | Easy | Tailscale |
| Printers/PACS/Wi-Fi | Hard to mimic | Real |
| Risk | Easy to leave open | Physical theft/power |

**Recommend:** development on the Mac → hospital **LAN UAT** in Ilorin with Tailscale for Abuja → same hardware hardened for production. Skip public-cloud UAT unless a private VPC with no public EMR ports is mandatory. Do not put real patients on a public URL.

---

## 12. Deployment and update workflow

```text
Mac development → tests → commit → private GitHub
  → hospital UAT: git fetch && git checkout <tag>
  → npm ci && npm run build
  → docker compose up -d
  → hospital tests
  → approve tag
  → production: same tag (or the same server after UAT sign-off)
```

Hospital EMR UI updates by rebuilding `dist` (bind-mounted). Hospital EMR API updates by pulling source and `docker compose restart abikan-api`. Bahmni image tag changes are a **platform** upgrade; treat them separately from Hospital EMR UI/API.

No automatic production deploy.

---

## 13. Rollback

- Tag every UAT/production deploy: `git tag -a hospital-YYYYMMDD-<shortsha>`.
- Record Bahmni image tags from `.env`.
- Hospital EMR-only rollback: `git checkout` previous tag, `npm run build`, restart `proxy` and `abikan-api`. Clinical databases stay put.
- OpenMRS/Odoo **schema** upgrades are not safely reversed by checking out old code. Roll those back with a **database restore** from the pre-upgrade backup, or do not upgrade those images during a clinic day.
- Never restore a backup onto the live hospital volumes without a freeze window.

---

## 14. Clean hospital installation (future — do not run now)

1. New server, empty Docker volumes.
2. Clone `samsonlukman/abikan-emr` at a release tag.
3. New `.env` / `.env.abikan` from examples; unique passwords; `ABIKAN_ENVIRONMENT=production` (or `test` for UAT).
4. `TZ=Africa/Lagos`, `CONFIG_VOLUME` → Git `abikan-config`, `COMPOSE_PROFILES=bahmni-standard`.
5. `npm ci && npm run build`.
6. `docker compose ... -f docker-compose.hospital.yml up -d`.
7. Create hospital administrator and department users with **new** passwords. Do not use `Admin123`.
8. Do not restore development volumes. Do not copy development SQLite audit.

---

## 15. Docker commands

All from `bahmni-docker/bahmni-standard` unless noted. Never put passwords on the command line in documentation copies.

```bash
# Start (development Mac)
docker compose --env-file .env up -d

# Start (hospital)
docker compose --env-file .env \
  -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.hospital.yml \
  up -d

docker compose --env-file .env ps
docker compose --env-file .env logs -f proxy abikan-api openmrs
docker compose --env-file .env restart abikan-api
docker compose --env-file .env stop          # avoid on hospital; prefer reboot with unless-stopped
docker compose --env-file .env down          # keeps volumes
# docker compose --env-file .env down -v     # DESTROYS DATA — forbidden on hospital

df -h
docker system df
```

Update Abikan:

```bash
cd /opt/abikan   # clone root
git fetch && git checkout <tag>
cd abikan-shell && npm ci && npm run build
cd ../bahmni-docker/bahmni-standard
docker compose --env-file .env restart abikan-api proxy
```

Backup: `./backup_bahmni_standard.sh` then `./backup_abikan_audit.sh`.

---

## 16. Development password `Admin123` (do not copy)

This password remains on the **development Mac** and in **historical documentation**. It must not be used on hospital UAT or production. Hospital `.env.example` and `.env.hospital.example` do not contain it. Production Hospital EMR startup rejects `admin123` (and similar placeholders) for the six Hospital EMR **service** variables; staff OpenMRS passwords are separate and must still be unique.

**Development OpenMRS staff accounts** (this workstation only; same password): `admin.abikan`, `reception.abikan`, `registration.abikan`, `doctor.abikan`, `nurse.abikan`, `pharmacy.abikan`, `lab.abikan`, `radiology.abikan`, `accountant.abikan`, `hospitaladmin.abikan`, plus earlier `abikan.*` usernames. Stock Bahmni `admin` is also commonly `Admin123` in this environment.

**Development Compose `.env` (local, gitignored):** atomfeed and Snowstorm Lite values on this Mac still use it. Do not copy that file.

**Tracked development docs/scripts** (not hospital config): capability/implementation notes under `abikan-shell/docs/`, and `abikan-shell/scripts/verify-laboratory-e2e-readonly.py` (falls back to `Admin123` if env vars are unset). Do not run that script against a hospital server.

Hospital installation copies `.env.example` (blank passwords) and fills unique values. Never copy this Mac’s `.env` / `.env.abikan`.

---

## 17. Portability notes

Already relative (no `/Users/apple/...` in Compose). Remaining host dependencies:

- Git clone path must exist for bind mounts
- `abikan-shell/dist` must be built
- Local `.env` / `.env.abikan`
- Docker named volumes on that machine
- Development `TZ=UTC` and `CONFIG_VOLUME=bahmni-config` should not be copied to hospital

`abikan-shell/README.md` still shows Mac paths in examples only; runtime Compose does not.

---

## 18. Known limitations (UAT, not hidden)

These remain in the current implementation. They do not block hospital UAT. They must be reviewed before go-live where noted in the freeze report.

- A **new** laboratory result should be processed during hospital UAT. Do not treat an older development result as proof of the hospital OpenELIS path.
- The laboratory board can be slow (several seconds).
- Company currency remains **USD** while departmental invoices use **NGN** pricelists. Historical USD accommodation invoices stay USD; new accommodation invoices use the Hospital Accommodation (NGN) shop.
- Nursing Diagnoses may show unavailable. Care plan and intake/output are not shown.
- SuperAdmin retains existing write capabilities for department catalogue prices. Hospital Admin and SuperAdmin set accommodation tariffs; existing charges keep the amount captured at creation.
- Other wards may show tariff **0** until configured.
