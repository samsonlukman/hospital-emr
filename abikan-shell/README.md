# Hospital EMR Shell

Hospital EMR Shell is the user-facing hospital product layer for **Hospital EMR**.

Bahmni and OpenMRS remain the EMR engine. This application does not rebuild Registration, Clinical, Appointments, OpenELIS, Odoo, or Radiology. It decides **which workplace** a signed-in user should see, then opens the existing Bahmni applications.

```
User + privileges + location
        ↓
Hospital EMR workspace
        ↓
Existing Bahmni / OpenELIS / Odoo / dcm4chee
```

## Why it exists

Bahmni Home is a module picker. Selecting Emergency or General Ward does not change the workplace. Hospital EMR Shell uses the current OpenMRS session so receptionists, clinicians, and later nurses each get a workspace that matches their work.

The first implemented workspace is **Registration Desk** (Reception Dashboard).

## How authentication works

The shell does **not** have its own login.

1. It calls `GET /openmrs/ws/rest/v1/session` with `credentials: "include"`.
2. The browser sends the existing OpenMRS `JSESSIONID` cookie.
3. If the session is missing or unauthenticated, the user is sent to Bahmni login:

   `/bahmni/home/index.html#/login`

Sign in and choose a location there, then return to the shell.

## How the current user is loaded

After the session is authenticated:

```
GET /openmrs/ws/rest/v1/user?username={username}&v=custom:(username,uuid,roles:(name),privileges:(name,retired),userProperties)
```

The shell uses username, UUID, roles, and privileges from this response. Nothing is hardcoded.

## How the current location is loaded

The session location UUID comes from `session.sessionLocation` (with the `bahmni.user.location` cookie as a fallback). Then:

```
GET /openmrs/ws/rest/v1/location/{uuid}?v=full
```

The shell stores the location UUID, name, and **tags**. Tags are the long-term way to distinguish Registration Desk, OPD, Emergency, and wards. The first workspace still requires the location name `Registration Desk` plus the `app:registration` privilege, as specified for this prototype.

Location changes use the same OpenMRS session API Bahmni uses (`POST /openmrs/ws/rest/v1/session` with `sessionLocation`). The header location list comes from locations tagged `Login Location`. The shell also reloads the session when the window is focused again, in case the location was changed elsewhere.

Sign out calls `DELETE /openmrs/ws/rest/v1/session` and returns to Bahmni login.

## How privileges are used

Bahmni authorizes screens by privilege, not by role name. The shell follows that:

- `app:registration` is required for the Registration Desk workspace.
- Future workspaces will match other privileges (`app:clinical`, `app:adt`, and so on).
- Role names are loaded so later mappings can use them, but they are not required for this prototype.

## How workspace routing works

`https://localhost/abikan/` always opens **Clinical Home**, the Hospital EMR workspace launcher.

Hash routes:

- `#/home` — Clinical Home
- `#/registration-desk` — Registration Desk, only when location is Registration Desk and the user has `app:registration`
- `#/doctor` — Doctor / Consultant, when the location is clinical and the user has `app:clinical`
- `#/doctor/patient/{uuid}` — Hospital EMR consultation for that patient
- `#/workspace` — Coming Soon for the current location

Capability rules live in `src/config/workspaceMap.ts`. The launcher catalog lives in `src/config/clinicalWorkspaces.ts`. A workspace card is shown only when the current location matches or the user has the related privilege. Unimplemented workspaces are marked Coming Soon.

Other outcomes:

- Registration Desk without `app:registration` → access denied (still inside Hospital EMR)
- Emergency, OPD, General Ward, Pediatric Ward → Coming Soon (still inside Hospital EMR)
- Unauthenticated → Bahmni login
- API failure → a calm error, not a raw stack trace

Users return to Clinical Home from the sidebar. They are not sent through `/bahmni/home`.

To add a workspace later:

1. Add a catalog entry in `clinicalWorkspaces.ts`.
2. Add a capability rule to `workspaceMap`.
3. Add a folder under `src/workspaces/`.
4. Render it from `src/app/WorkspaceRouter.tsx`.

Do not put location-specific logic in the OpenMRS client.

## How it launches Bahmni

Buttons use same-window navigation to existing routes:

| Action | URL |
|--------|-----|
| Register patient | `/bahmni/registration/index.html#/patient/new` |
| Find patient | `/bahmni/registration/index.html#/search` |
| Appointments | `/appointments` |
| Patient dashboard | `/bahmni/clinical/index.html#/default/patient/{uuid}/dashboard` |

In local development those paths are prefixed with `https://localhost` (`VITE_BAHMNI_ORIGIN`). The production build uses an empty origin so Hospital EMR and Bahmni share `https://localhost`.

## How to run

The production URL, served by the existing Bahmni proxy, is:

**https://localhost/abikan/**

Sign in at `https://localhost/bahmni/home` if you do not have a session, then open `/abikan/`. Clinical Home is the Hospital EMR launcher. Registration Desk opens from there. No Vite process is required.

The proxy mounts `abikan-shell/dist` read-only at `/usr/local/apache2/htdocs/abikan`. After UI changes:

```bash
cd /Users/apple/Hospital EMREMR/abikan-shell
npm run build
```

Refresh the browser. Recreating the proxy is not required for a rebuild.

Vite remains available for local UI work:

```bash
cd /Users/apple/Hospital EMREMR/abikan-shell
npm run dev
```

**https://localhost:5173/abikan/**

The Clinical Service tile on Bahmni Home still points to `/bahmni/home`. Do not change that until `/abikan/` is approved as the hospital entry.

### Rollback

Remove the `proxy.volumes` block from `bahmni-docker/bahmni-standard/docker-compose.override.yml`, then recreate only the proxy:

```bash
cd /Users/apple/Hospital EMREMR/bahmni-docker/bahmni-standard
docker compose --env-file .env up -d proxy
```

Do not run `docker compose down -v`. Bahmni Home, OpenMRS, and hospital data stay in place.

## Design system

Visual rules for every future workspace are in `docs/DESIGN.md`.

## What this prototype does not do

- It does not change Bahmni Home or `whiteLabel.json`. The Clinical Service tile still opens `/bahmni/home`.
- It does not implement Emergency, ward, pharmacy, laboratory, or admin workspaces.
- It does not invent patient queues or fake patient lists.
- It does not replace Bahmni Registration.
