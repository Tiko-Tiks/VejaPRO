# WORKLOG 2026-02-07 (UI + Security Review)

## Context
- Request: review code for vulnerabilities and possible improvements, then improve design (expert-first).
- Workspace: `c:\Users\Administrator\Desktop\VejaPRO`
- Date: 2026-02-07

## Scope covered
- Frontend static portals:
  - `backend/app/static/gallery.html`
  - `backend/app/static/contractor.html`
  - `backend/app/static/expert.html`
- Backend/API security posture review:
  - `backend/app/api/v1/projects.py`
  - `backend/app/core/config.py`
  - `backend/app/main.py`

## What was completed

### 1) `gallery.html` design refresh (already in current worktree)
- Typography switched to `Space Grotesk`.
- New visual system: updated colors, shadows, radii, gradients.
- Sticky header/filters improved with blur and glass-style treatment.
- Hero section extended with:
  - kicker label
  - 3 stat cards (`#statProjects`, `#statFeatured`, `#statLocations`)
- Gallery card rhythm improved:
  - dense grid layout
  - featured-card emphasis
  - updated badges and overlays
- JS improvements:
  - `updateHeroStats()` added and wired into loading/reset flow
  - featured class applied per-item
  - overlay generation moved from string HTML to DOM-node creation

### 2) `contractor.html` design refresh (already in current worktree)
- Typography switched to `Space Grotesk`.
- Updated design tokens, gradients, shadow system, sticky header.
- Hero/page header and auth panel restyled.
- Stats cards improved with top-accent indicator.
- Projects panel and filter chips modernized.
- Project rows now have status accent borders:
  - `status-row-PAID`
  - `status-row-SCHEDULED`
  - `status-row-PENDING_EXPERT`
  - `status-row-CERTIFIED`
  - `status-row-ACTIVE`
- Render output includes status-row class in row markup.

### 3) `expert.html` design + security hardening (implemented now)
- Design aligned with contractor style system:
  - `Space Grotesk`
  - updated color/shadow tokens
  - layered gradient background
  - glass-like cards and improved hierarchy
  - status-row accents
- Security hardening in frontend script:
  - removed inline `onclick` usage for modal close and action buttons
  - removed dynamic `innerHTML` rendering for project list and modal body
  - replaced with safe DOM construction (`createElement`, `textContent`, `appendChild`)
  - added `safeExternalUrl()` validation before opening evidence URLs
  - added project ID normalization via `normalizeProjectId()`
  - added status sanitization via `normalizeStatus()`
  - migrated token storage from `localStorage` to `sessionStorage`
  - added one-time legacy token migration from `localStorage`

## Security findings (not yet fixed in backend)

### HIGH
1. Public project creation endpoint:
   - `backend/app/api/v1/projects.py:269`
   - `POST /projects` has no auth dependency.

2. Admin token endpoint exposure risk when enabled:
   - `backend/app/api/v1/projects.py:631`
   - `GET /admin/token` can mint admin JWT if feature flag is enabled.

3. Remaining frontend XSS/token-theft surfaces outside `expert.html`:
   - `backend/app/static/contractor.html` still has dynamic `innerHTML` and inline handlers.
   - `backend/app/static/client.html` still has dynamic `innerHTML`.
   - `backend/app/static/admin.html` and others still rely on long-lived `localStorage` token patterns.

### MEDIUM
1. API rate limiting disabled by default:
   - `backend/app/core/config.py:79` (`rate_limit_api_enabled: bool = False`)

2. Cache policy mismatch for authenticated portal pages:
   - `_public_headers` uses `Cache-Control: public, max-age=300` in `backend/app/main.py:78`
   - `/contractor` and `/expert` currently use those headers:
     - `backend/app/main.py:245`
     - `backend/app/main.py:250`

## Validation done
- Reviewed diffs and code paths for:
  - `gallery.html`
  - `contractor.html`
  - `expert.html`
  - relevant backend files above
- Confirmed `expert.html` no longer contains:
  - inline `onclick=`
  - unsafe `innerHTML` rendering paths for projects/modal
- Confirmed `expert.html` now uses `sessionStorage` for token persistence.

## Validation limits
- Browser smoke tests were not executed in this step.
- Direct JS syntax check extraction from HTML script block was partially blocked by command policy in this environment.
- Validation is based on static diff/code inspection.

## Additional changes (after initial worklog)

### 4) RBAC hardening + portal UI refresh (committed `6074f90`)
- RBAC hardening across projects.py — stricter role checks
- Portal UI refreshed (audit, calendar, calls, client)
- transition_service.py — improved error handling
- New test file: `backend/tests/test_rbac_hardening.py`

### 5) Page cache disabled + normalize LT UI copy (committed `46ecfce`)
- Disabled page cache for authenticated portal pages
- Normalized Lithuanian UI copy across portals

### 6) Fix marketing flag tests (committed `81a5fa1`)
- Fixed marketing flag tests for RBAC assignments

### 7) Full i18n Lithuanian translation (committed `04bcdec`)
- All 9 HTML files translated to Lithuanian:
  - `landing.html` — hero texts, feature cards, process steps (kokybė, įrengimas, užklausa, mokėjimai, sąmata, depozitą, etc.)
  - `admin.html` — full EN→LT: nav, token section, quick links, notes, all JS messages
  - `projects.html` — full EN→LT: nav, forms, table headers, 5 modals (assign, details, token, payment, transition), ~50 JS strings
  - `client.html` — full EN→LT: access, project overview, consent, evidence, activity, all JS STATUS_LABELS/HINTS
  - `audit.html` — full EN→LT: filters, table headers, export, saved views, JSON modal, JS messages
  - `calls.html` — full EN→LT: form, filters, table, edit modal, JS messages
  - `calendar.html` — full EN→LT: form, filters, table, edit modal, JS messages
  - `margins.html` — full EN→LT: form, table, JS messages
  - `contractor.html` — "Subrangovo" → "Rangovo" title fix
- All files use `<html lang="lt">`
- Consistent nav across admin pages: Apžvalga, Projektai, Skambučiai, Kalendorius, Auditas, Maržos
- All Lithuanian diacritics correct: ą, č, ę, ė, į, š, ų, ū, ž

## Recommended next actions
1. Apply same DOM-safe rendering + `sessionStorage` migration pattern to `contractor.html`.
2. Harden backend auth exposure:
   - protect or disable `GET /api/v1/admin/token` in non-local environments.
   - consider requiring admin auth + IP allowlist + short TTL + one-time usage policy.
3. Enable API rate limiting by default for production profile.
4. Serve `/contractor` and `/expert` with `no-store` response headers.
5. Run browser smoke checks (desktop + mobile) for gallery/contractor/expert after merge.
6. Fix 11 failing tests (admin IP, Stripe payload, gallery).

