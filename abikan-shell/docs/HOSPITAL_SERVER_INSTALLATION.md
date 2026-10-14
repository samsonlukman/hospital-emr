# Hospital EMR Hospital Server Installation Checklist

Use this on a **new** hospital or UAT server. Do not run a volume reset against the current development Mac.

Secrets stay in local files (mode `0600`). Never commit them. Never copy the development Mac `.env` files.

---

## Before arriving at the hospital

- [ ] Confirm GitHub access to `samsonlukman/abikan-emr` (deploy key or admin account).
- [ ] Agree a Git **tag** to install (never “whatever is on main” without a tag).
- [ ] Generate hospital passwords (password manager). Unique values for OpenMRS, OpenELIS, Odoo, MySQL root, PACS, atomfeed, and Hospital EMR service accounts. **Not** `Admin123`.
- [ ] Decide LAN IP / DNS name (example: `emr.hospital.lan`).
- [ ] Decide UPS, RAID, and off-server backup target.
- [ ] Pack Ubuntu Server LTS installer, Ethernet cable, and written BIOS/power-on-after-AC notes.
- [ ] Read `HOSPITAL_DEPLOYMENT.md` and `DEPLOYMENT_SECRETS.md`.

## At the hospital

- [ ] Place the server on Ethernet to the hospital switch (not consumer Wi-Fi as the only path).
- [ ] Confirm UPS is on the same circuit as the server.
- [ ] Confirm the switch/router will not port-forward 22/80/443/8069 to the Internet.

## Server setup

- [ ] Install **Ubuntu Server LTS**.
- [ ] Create an admin user; disable password SSH if using keys.
- [ ] Set hostname; set timezone `Africa/Lagos`.
- [ ] Enable automatic security updates for the OS (not Docker image auto-upgrade).
- [ ] BIOS: restore power after AC loss.
- [ ] Install Docker Engine + Compose plugin. Enable `docker.service`.
- [ ] Confirm `docker run hello-world` (or equivalent) works.
- [ ] Create `/opt/abikan` owned by the admin user.

## Network setup

- [ ] Static DHCP reservation or static LAN IP.
- [ ] Internal DNS or hosts file on staff PCs: name → LAN IP.
- [ ] Host firewall: LAN 80/443; Tailscale SSH; deny the rest (see `HOSPITAL_DEPLOYMENT.md`).
- [ ] Do not publish MySQL, PostgreSQL, 8787, 8069, or dcm4chee 8055 to the LAN.
- [ ] Leave DICOM 11112 unpublished unless a modality requires it (commented in the hospital overlay).

## Docker / Hospital EMR deployment

- [ ] `git clone git@github.com:samsonlukman/abikan-emr.git /opt/abikan` (or HTTPS with a credential helper).
- [ ] `git checkout <tag>`.
- [ ] Copy `bahmni-docker/bahmni-standard/.env.example` → `.env`.
- [ ] Apply keys from `.env.hospital.example` (`COMPOSE_PROFILES`, `TZ`, `CONFIG_VOLUME`, `RESTART_POLICY`).
- [ ] Fill every blank password in `.env`.
- [ ] Copy `.env.abikan.example` → `.env.abikan` (`chmod 600`).
- [ ] Set `ABIKAN_ENVIRONMENT=test` (UAT) or `production`.
- [ ] Fill Hospital EMR service identities (not development defaults).
- [ ] `cd /opt/abikan/abikan-shell && npm ci && npm run build`.
- [ ] From `bahmni-docker/bahmni-standard`:

```bash
docker compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker-compose.hospital.yml \
  up -d
```

- [ ] `docker compose --env-file .env ps` — core services Up. Investigate anything Restarting.
- [ ] Wait for OpenMRS (first boot can take many minutes).
- [ ] Open `https://<lan-ip>/` — Hospital EMR sign-in, not a stack trace.

## Database initialization

- [ ] First start uses **empty** volumes (clean hospital). Do not restore development dumps.
- [ ] Confirm OpenMRS, OpenELIS, and Odoo finished first-run without using development passwords.
- [ ] Do not run `docker compose down -v`.

## Secrets

- [ ] `.env` and `.env.abikan` are `0600` and not in Git (`git status` clean of those files).
- [ ] No `Admin123` for hospital staff or service accounts.
- [ ] Browser bundle was built with production Vite settings (empty `VITE_BAHMNI_ORIGIN`).
- [ ] Rotate any value that was ever used on the development Mac if it was reused.

## Backups

- [ ] Create `/var/backups/abikan` (or encrypted disk).
- [ ] Dry-run `./backup_bahmni_standard.sh` and `./backup_abikan_audit.sh` after first stable night.
- [ ] Copy one backup off-server. Encrypt it.
- [ ] Schedule daily backup (cron/systemd timer) **after** UAT data rules are agreed.
- [ ] Plan a restore test on a spare machine before go-live.

## VPN

- [ ] Install Tailscale on the server and on the Abuja admin device (when that work is scheduled).
- [ ] Restrict SSH to Tailscale.
- [ ] Do not require Tailscale for ward/reception PCs on LAN.
- [ ] Document how to revoke a device.

## Staff devices

- [ ] Supported browser (current Chrome/Edge/Firefox).
- [ ] Trust or install the hospital TLS certificate (Bahmni proxy default is not a public CA).
- [ ] Bookmarks to the LAN hostname only (not `:8069` or `:8787`).
- [ ] Printers and barcode scanners on LAN as required by Reception/Pharmacy.

## Testing / UAT / go-live

- [ ] Follow `HOSPITAL_UAT_CHECKLIST.md` with **synthetic** patients on UAT.
- [ ] Sign-off from Reception, Clinical, Nursing, Laboratory, Pharmacy, Accounts, Administration.
- [ ] Production: new credentials and empty volumes **or** promote the UAT server only after wiping synthetic patients by policy (prefer a clean production if UAT was messy).
- [ ] Confirm UPS + reboot test: power cycle, Docker starts, `https://emr.hospital.lan` returns.
