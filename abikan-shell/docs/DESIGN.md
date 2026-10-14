# Hospital EMR design system

This is the visual language for every Hospital EMR workspace. The Registration Dashboard is the benchmark.

The product should feel like a hospital workstation: dark navigation, a light working surface, restrained colour, and one icon family.

## Product chrome

- **Sidebar** (`--color-sidebar` `#121e33`): hospital identity, grouped navigation with Lucide line icons, bright blue active item, “Soon” for unfinished work, signed-in user at the bottom
- **Header**: hamburger, product name, page title, welcome name, patient search, notifications, location, signed-in user, sign out
- **Workspace**: light grey canvas (`#f4f6f8`) with white cards
- **Footer**: hospital copyright and product version

Do not invent a different chrome per module.

## Icon system

Use `AppIcon` and `IconWell` only. The icon family is Lucide (`lucide-react`), stroke 1.75.

Sizes:

- Navigation: 20px
- Quick actions: 26px
- KPI cards: 36px

The Nigerian Naira mark is a Lucide-matched stroke icon (`naira`). Do not mix other icon libraries or emoji.

## Semantic colours

| Meaning | Token | Use |
|---------|--------|-----|
| Registration | `--color-registration` `#2563eb` | New patients, Individual Card, register actions |
| Appointments | `--color-appointments` `#16a34a` | Calendar, Family Card, search |
| Visits | `--color-visits` `#d97706` | Open visits, new appointment |
| Collections | `--color-collection` `#7c3aed` | Money, daily collection, create visit |
| Payment / teal | `--color-teal` `#0d7377` | Record payment, sign out |

Apply colour on the icon, icon well, a thin accent, and the action link. Do not flood entire cards.

## Other colours

| Token | Value | Use |
|-------|--------|-----|
| `--color-sidebar` | `#121e33` | Left navigation |
| `--color-nav-active` | `#2563eb` | Active nav item |
| `--color-bg` | `#f4f6f8` | Page background |
| `--color-surface` | `#ffffff` | Cards, header, dialogs |
| `--color-ink` | `#1a2332` | Body text |
| `--color-ink-muted` | `#5b6675` | Supporting text |
| `--color-navy` | `#121e33` | Titles |
| `--color-link` | `#1d4ed8` | Patient names |
| `--color-success` | `#15803d` | Checked in |
| `--color-info` | `#1d4ed8` | Scheduled |
| `--color-danger` | `#b42318` | Cancelled / error |

## Money

Always Nigerian Naira via `formatNaira()`.

Examples: `₦0`, `₦2,000`, `₦5,000`. Never `$`.

Never invent collection figures. Until billing is connected, collection is `₦0`.

## Typography

Source Sans 3, 16px body. Page title ~1.7rem. Section titles 1.05rem. KPI values ~2rem. No display type.

## Spacing

4 / 8 / 12 / 16 / 20 / 24 / 32 / 40. Sidebar 248px. Content up to 1240px.

## Components

- `AppIcon` / `IconWell` — one icon language
- `Button` — primary / secondary / ghost
- `KpiCard` — operational counts and collection
- `Card` — tables and groups
- `SectionHeader` — panel titles
- `Badge` — appointment and registration status
- `QuickAction` — large workstation shortcuts
- `CardTypeChoice` — Individual ₦2,000 / Family ₦5,000
- `CollectionSummary` — honest daily totals
- `WorkspaceTile` — Clinical Home launcher cards
- `Sidebar` + `Header` — product chrome
- `PatientSearch` — real OpenMRS search
- `CardTypeDialog` — card selection before Bahmni registration
- `Alert`, `StatusDot`, `.abikan-table`, `.abikan-field`

## Empty states

Prefer `₦0` and “No appointments scheduled for today.” over invented figures or patients.

Registration type is shown as `—` until OpenMRS provides a real type.

## Future workspaces

Emergency, wards, pharmacy, laboratory, and billing must reuse this chrome and these components. Change content, not the product look.
