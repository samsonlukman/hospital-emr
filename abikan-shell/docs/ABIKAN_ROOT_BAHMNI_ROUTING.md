# Hospital EMR root / Bahmni routing

Date: **18 Aug 2026**. This is a proxy/entry-point change only. Hash routing, clinical workflows, accounting, OpenMRS, Odoo, OpenELIS, and PACS were not redesigned.

Staff should land on Hospital EMR at the hospital address. Bahmni remains available at an explicit path.

---

## 1. Previous routing

The front door is Apache in the `proxy` container (`bahmni/proxy`), not nginx. Config: `/usr/local/apache2/conf/bahmni-proxy.conf`. DocumentRoot: `/usr/local/apache2/htdocs`. HTTP 80 redirects to HTTPS 443.

| URL | What served it |
|---|---|
| `/` | Apache `DirectoryIndex index.html` — the Bahmni tile launcher shipped in the proxy image (`<title>Bahmni</title>`). Not a redirect. Not the Bahmni clinical apps. |
| `/abikan/` | Bind-mounted `abikan-shell/dist` at `htdocs/abikan` |
| `/bahmni/` | Already existed: `ProxyPass /bahmni http://bahmni-web:8091/bahmni`. The directory has **no** `index.html`, so `/bahmni/` returned **403**. Real home was `/bahmni/home/` |
| `/openmrs/` | `ProxyPass /openmrs http://openmrs:8080/openmrs` |
| `/openmrs/abikan-api/` | Injected: `ProxyPass /openmrs/abikan-api http://abikan-api:8787/` |

Separate existing redirect: `Redirect permanent /home /bahmni/home/`.

Vite `base` was and remains `"/abikan/"`. Built HTML loads `/abikan/assets/…`. Hash routes (`#/doctor`, `#/nursing`, …) live in `hashRoute.ts` and do not depend on pathname.

---

## 2. New routing

| URL | Result |
|---|---|
| `https://localhost/` | **Hospital EMR** |
| `https://localhost/abikan/` | **Hospital EMR** (compatibility) |
| `https://localhost/bahmni/` | **Bahmni** (302 → `/bahmni/home/`) |
| `https://localhost/bahmni/home/` | Bahmni home (unchanged) |
| `https://localhost/openmrs/…` | OpenMRS (unchanged) |
| `https://localhost/openmrs/abikan-api/…` | Hospital EMR API (unchanged) |

Hash routes work at both entry points:

- `https://localhost/#/registration-desk`
- `https://localhost/abikan/#/registration-desk`

History-based routing was not introduced.

---

## 3. How `/` serves Hospital EMR

On every proxy start, `inject-abikan-api.sh` copies:

`htdocs/abikan/index.html` → `htdocs/index.html`

Apache then serves that file as DocumentRoot `DirectoryIndex`. The HTML still points at `/abikan/assets/…` and `/abikan/abikan-logo.png`.

If the previous root file was the Bahmni launcher (title not `Hospital EMR`), it is copied once to `htdocs/bahmni-landing.html` inside the container. That file is a rollback copy, not a staff link.

Vite `base` was **not** changed. Changing it to `/` would have broken `/abikan/` asset URLs.

---

## 4. How `/abikan/` remains available

Unchanged. `docker-compose.override.yml` still bind-mounts:

`abikan-shell/dist` → `/usr/local/apache2/htdocs/abikan:ro`

The same built app is therefore reachable at `/abikan/` and, via the copied `index.html`, at `/`.

Hospital EMR in-app navigation uses hash hrefs (`#/doctor`, …), not `/abikan/`. No src links needed retargeting to `/`.

Legacy clinical links already use `/bahmni/registration/…`, `/bahmni/clinical/…`, and similar via `bahmniUrl()` in `appConfig.ts`. No new navigation UI was added.

---

## 5. How `/bahmni/` exposes Bahmni

`ProxyPass /bahmni` was already present. Bahmni apps were not moved.

`bahmni-web` has no `index.html` under `/bahmni/`, so the exact paths `/bahmni` and `/bahmni/` 403’d. The inject script now adds:

```
RedirectMatch ^/bahmni/?$ /bahmni/home/
ProxyPassMatch ^/bahmni/?$ !
```

`ProxyPassMatch !` must sit **before** `ProxyPass /bahmni`, otherwise Apache proxies the exact path and the redirect never runs.

Subpaths are unchanged:

- `/bahmni/home/`
- `/bahmni/clinical/`
- `/bahmni/registration/`
- `/bahmni/admin/`
- `/bahmni/adt/`
- `/bahmni/bedmanagement/`
- `/bahmni/orders/`
- `/bahmni/reports/`

---

## 6. Asset / base-path handling

| Choice | Why |
|---|---|
| Keep `base: "/abikan/"` | One asset URL works from both `/` and `/abikan/` |
| Copy only `index.html` to DocumentRoot | Root HTML can load `/abikan/assets/…` without dual Vite builds |
| Do not use `base: "./"` | Avoided; relative assets from `/` vs `/abikan/` are easy to get wrong |
| Do not rewrite asset URLs in nginx/Apache | Unnecessary if Vite base stays `/abikan/` |

Built `dist/index.html` (18 Aug 2026):

- `/abikan/assets/index-B-GZv85J.js`
- `/abikan/assets/index-CNmSQjIQ.css`
- `/abikan/abikan-logo.png`

`import.meta.env.BASE_URL` remains `/abikan/` (logo in Sidebar, BrandBar, Login).

HTML entry points send:

`Cache-Control: no-cache, no-store, must-revalidate`

so browsers that previously cached the Bahmni launcher at `/` re-fetch. Hashed `/abikan/assets/…` files are not covered by that LocationMatch and stay cacheable.

---

## 7. API / session handling

Unchanged paths:

- `/openmrs/ws/rest/…`
- `/openmrs/abikan-api/…`

Hospital EMR calls these as absolute same-origin URLs, so they work from `/` and from `/abikan/`.

OpenMRS `JSESSIONID` is HttpOnly. The proxy already copies it to `reporting_session` for `/openmrs/*`. Cookie path is OpenMRS, not `/abikan/`, so the session is shared across Hospital EMR root, `/abikan/`, and Bahmni.

No new login system. Existing OpenMRS session is reused.

---

## 8. Files changed

| File | Change |
|---|---|
| `bahmni-docker/bahmni-standard/proxy/inject-abikan-api.sh` | Copy Hospital EMR `index.html` to DocumentRoot; redirect exact `/bahmni/` to `/bahmni/home/`; no-cache headers on HTML entries. Existing abikan-api ProxyPass inject kept. |
| `bahmni-docker/bahmni-standard/docker-compose.override.yml` | Comment only: root and `/abikan/` serve Hospital EMR; Bahmni stays at `/bahmni/`. |
| `abikan-shell/docs/ABIKAN_ROOT_BAHMNI_ROUTING.md` | This document. |

Not changed:

- `abikan-shell/vite.config.ts` (`base` still `/abikan/`)
- `abikan-shell/src/app/hashRoute.ts`
- `abikan-shell/src/app/WorkspaceRouter.tsx`
- `abikan-shell/src/App.tsx`
- `abikan-shell/src/config/workspaceMap.ts`
- OpenMRS, Odoo, OpenELIS, PACS, clinical or financial data

---

## 9. Build result

From `abikan-shell/`:

```
npm run build
```

Result: `tsc --noEmit && vite build` succeeded.

```
dist/index.html                   0.53 kB
dist/assets/index-CNmSQjIQ.css   64.04 kB
dist/assets/index-B-GZv85J.js   402.66 kB
```

Proxy was restarted (not `docker compose down -v`):

```
docker compose --env-file .env restart proxy
```

from `bahmni-docker/bahmni-standard`.

---

## 10. Browser and URL verification

Live host: `https://localhost/` (port 80 → 443).

### Curl

| Request | Result |
|---|---|
| `GET /` | 200, `<title>Hospital EMR</title>`, scripts `/abikan/assets/…`, `Cache-Control: no-cache, no-store, must-revalidate` |
| `GET /abikan/` | 200, same Hospital EMR HTML |
| `GET /abikan/assets/index-B-GZv85J.js` | 200 `text/javascript` |
| `GET /abikan/assets/index-CNmSQjIQ.css` | 200 `text/css` |
| `GET /abikan/abikan-logo.png` | 200 |
| `GET /bahmni` and `GET /bahmni/` | 302 → `/bahmni/home/` |
| `GET /bahmni/home/` | 200, `<title>Bahmni Home</title>` |
| `GET /bahmni/clinical/` `/registration/` `/admin/` `/adt/` `/bedmanagement/` `/orders/` `/reports/` | 200 |
| `GET /openmrs/` | 200 |
| `GET /openmrs/ws/rest/v1/session` | 200 JSON |
| `GET /openmrs/abikan-api/health` | 200 |
| `GET /openmrs/abikan-api/inpatient/board` (no cookie) | 401 (expected) |

### Browser

Signed in as `abikan.admin` at `https://localhost/` (OpenMRS session). Workplace: Registration Desk.

| Check | Result |
|---|---|
| `/` after login | Hospital EMR Clinical Home |
| `/#/registration-desk` | Reception Dashboard |
| `/#/doctor` | Doctor / Consultant (queue loaded; refresh kept session) |
| `/#/nursing` | Nursing / Ward |
| `/#/laboratory` | Laboratory |
| `/#/radiology` | Radiology |
| `/#/pharmacy` | Pharmacy |
| `/#/accountant` | Accountant / Cashier |
| `/#/accommodation-settings` | Accommodation prices |
| `/#/patient-account/{uuid}` | Patient Account for Adaeze Okafor (bills via abikan-api) |
| `/abikan/#/nursing` | Same Hospital EMR app; session still valid |
| `/bahmni/` | Redirects to `/bahmni/home/#/dashboard`, title Bahmni Home |
| Session after Bahmni | `/openmrs/ws/rest/v1/session` still `authenticated: true` for `abikan.admin` |

A browser that had previously cached the old `/` launcher could still show Bahmni until a hard refresh. No-cache headers on `/` and `/abikan/` were added so that does not stick.

---

## 11. Known limitations

1. **Vite base stays `/abikan/`.** Assets always load from `/abikan/assets/…`, even when the page URL is `/`. That is intentional.
2. **`/abikan/` is kept** as a second entry. It is not removed.
3. **`/bahmni/` is a redirect**, not a new Bahmni install. Internal Bahmni routes are still `/bahmni/home/`, `/bahmni/clinical/`, etc.
4. **Old Bahmni tile page** is no longer at `/`. A copy may exist in the proxy container as `bahmni-landing.html` (not linked in the UI).
5. **HTML cache.** Staff browsers that visited `/` before this change may need one hard refresh if they still see the old launcher. Subsequent loads should not cache that HTML.
6. **Bahmni `bahmni.user` cookie.** Hospital EMR now writes the same JSON-string username that Bahmni `$bahmniCookieStore` expects (`JSON.stringify(username)`). A leftover plain username is rewritten on workspace load. See **Open Full Chart — Bahmni Navigation** in `CLINICAL_INVESTIGATION.md`.
7. **Local Vite dev** (`npm run dev`, port 5173) still uses `base: "/abikan/"`. This document describes the Docker proxy front door.
8. **Rollback:** restore the previous `inject-abikan-api.sh` (or remove the root copy / `/bahmni/` redirect blocks), then `docker compose --env-file .env up -d proxy`. Do not `docker compose down -v`.

---

## What was not done

- No history routing.
- No Hospital EMR UI or menu redesign.
- No OpenMRS / Odoo / OpenELIS / PACS URL or credential changes.
- No patient, invoice, payment, stock, bed, or tariff data changes.
